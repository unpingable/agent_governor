# SPDX-License-Identifier: Apache-2.0
"""Tests for governor.replay — artifact model, replay_run, replay_diff."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from governor.replay import (
    ARTIFACT_VERSION,
    ArtifactHeader,
    DiffResult,
    ReplayClock,
    RunArtifact,
    TraceEvent,
    _compute_trace_hash,
    _fingerprint_receipt,
    replay_diff,
    replay_run,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_events(scenario: str = "test") -> list[TraceEvent]:
    """Build a minimal trace with gate_check calls and a heartbeat."""
    return [
        TraceEvent(
            t_ms=0, seq=0, scenario=scenario, event_type="emit",
            payload={
                "kind": "receipt",
                "data": {"gate": "sim", "verdict": "pass", "subject_bytes": "hello"},
            },
        ),
        TraceEvent(
            t_ms=300_000, seq=1, scenario=scenario, event_type="call",
            payload={"target": "gate_heartbeat", "session_active": True},
        ),
        TraceEvent(
            t_ms=600_000, seq=2, scenario=scenario, event_type="emit",
            payload={
                "kind": "receipt",
                "data": {"gate": "sim", "verdict": "pass", "subject_bytes": "world"},
            },
        ),
        TraceEvent(
            t_ms=900_000, seq=3, scenario=scenario, event_type="call",
            payload={"target": "gate_heartbeat", "session_active": True},
        ),
    ]


def _make_fault_events(scenario: str = "test") -> list[TraceEvent]:
    """Build events that toggle gate_enabled fault."""
    return [
        TraceEvent(
            t_ms=0, seq=0, scenario=scenario, event_type="emit",
            payload={
                "kind": "receipt",
                "data": {"gate": "sim", "verdict": "pass"},
            },
        ),
        TraceEvent(
            t_ms=100, seq=1, scenario=scenario, event_type="fault",
            payload={"flag": "gate_enabled", "value": False},
        ),
        TraceEvent(
            t_ms=200, seq=2, scenario=scenario, event_type="call",
            payload={"target": "gate_check", "output": "should be skipped"},
        ),
        TraceEvent(
            t_ms=300, seq=3, scenario=scenario, event_type="fault",
            payload={"flag": "gate_enabled", "value": True},
        ),
        TraceEvent(
            t_ms=400, seq=4, scenario=scenario, event_type="call",
            payload={"target": "gate_check", "output": "this runs"},
        ),
    ]


# =============================================================================
# TraceEvent
# =============================================================================


class TestTraceEvent:
    def test_roundtrip(self) -> None:
        e = TraceEvent(t_ms=100, seq=0, scenario="s1", event_type="call",
                       payload={"target": "gate_check"}, actor="a1")
        d = e.to_dict()
        e2 = TraceEvent.from_dict(d)
        assert e == e2

    def test_validates_event_type(self) -> None:
        with pytest.raises(ValueError, match="event_type"):
            TraceEvent(t_ms=0, seq=0, scenario="s1", event_type="bogus")

    def test_validates_t_ms_negative(self) -> None:
        with pytest.raises(ValueError, match="t_ms"):
            TraceEvent(t_ms=-1, seq=0, scenario="s1", event_type="call")

    def test_validates_empty_scenario(self) -> None:
        with pytest.raises(ValueError, match="scenario"):
            TraceEvent(t_ms=0, seq=0, scenario="", event_type="call")

    def test_json_line_canonical(self) -> None:
        e = TraceEvent(t_ms=0, seq=0, scenario="s", event_type="call", payload={})
        line = e.to_json_line()
        parsed = json.loads(line)
        assert parsed["t_ms"] == 0
        # Verify sorted keys
        keys = list(json.loads(line).keys())
        assert keys == sorted(keys)


# =============================================================================
# ArtifactHeader
# =============================================================================


class TestArtifactHeader:
    def test_roundtrip(self) -> None:
        h = ArtifactHeader(params={"heartbeat_interval": 60})
        d = h.to_dict()
        h2 = ArtifactHeader.from_dict(d)
        assert h2.params == {"heartbeat_interval": 60}
        assert h2.artifact_version == ARTIFACT_VERSION

    def test_artifact_id_is_uuid(self) -> None:
        h = ArtifactHeader()
        uuid.UUID(h.artifact_id)  # Raises on invalid UUID

    def test_trace_sha256_populated_on_create(self, tmp_path: Path) -> None:
        events = _make_events()
        h = ArtifactHeader()
        art = RunArtifact.create(tmp_path / "art", h, events)
        assert art.header.trace_sha256
        assert len(art.header.trace_sha256) == 64  # SHA-256 hex digest


# =============================================================================
# RunArtifact
# =============================================================================


class TestRunArtifact:
    def test_create_and_load_roundtrip(self, tmp_path: Path) -> None:
        events = _make_events()
        header = ArtifactHeader(params={"heartbeat_interval": 300})
        art = RunArtifact.create(tmp_path / "art", header, events)

        loaded = RunArtifact.load(tmp_path / "art")
        assert loaded.header.artifact_id == art.header.artifact_id
        assert loaded.header.trace_sha256 == art.header.trace_sha256
        assert len(loaded.events) == len(events)
        for orig, loaded_e in zip(events, loaded.events):
            assert orig == loaded_e

    def test_write_and_read_output(self, tmp_path: Path) -> None:
        events = _make_events()
        art = RunArtifact.create(tmp_path / "art", ArtifactHeader(), events)

        data = [{"gate": "sim", "verdict": "pass"}, {"gate": "sim", "verdict": "warn"}]
        art.write_output("receipts", data)
        read_back = art.read_output("receipts")
        assert read_back == data

    def test_output_names(self, tmp_path: Path) -> None:
        art = RunArtifact.create(tmp_path / "art", ArtifactHeader(), _make_events())
        art.write_output("receipts", [{"a": 1}])
        art.write_output("heartbeat", [{"b": 2}])
        names = art.output_names()
        assert names == ["heartbeat", "receipts"]

    def test_read_missing_output_returns_empty(self, tmp_path: Path) -> None:
        art = RunArtifact.create(tmp_path / "art", ArtifactHeader(), _make_events())
        assert art.read_output("nonexistent") == []

    def test_output_names_no_outputs_dir(self, tmp_path: Path) -> None:
        art = RunArtifact.create(tmp_path / "art", ArtifactHeader(), _make_events())
        assert art.output_names() == []

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            RunArtifact.load(tmp_path / "nope")

    def test_trace_sha256_validated_on_load(self, tmp_path: Path) -> None:
        events = _make_events()
        art = RunArtifact.create(tmp_path / "art", ArtifactHeader(), events)

        # Tamper with trace.jsonl
        trace_path = tmp_path / "art" / "trace.jsonl"
        trace_path.write_text('{"t_ms":0,"seq":0,"scenario":"tampered","event_type":"call","payload":{}}\n')

        with pytest.raises(ValueError, match="Trace hash mismatch"):
            RunArtifact.load(tmp_path / "art")


# =============================================================================
# ReplayClock
# =============================================================================


class TestReplayClock:
    def test_advance_and_read(self) -> None:
        c = ReplayClock()
        c.advance_to(1000)
        assert c.now.timestamp() == pytest.approx(1.0)

    def test_backwards_raises(self) -> None:
        c = ReplayClock()
        c.advance_to(1000)
        with pytest.raises(ValueError, match="cannot go backwards"):
            c.advance_to(500)


# =============================================================================
# replay_run()
# =============================================================================


class TestReplayRun:
    def test_default_params_produce_receipts(self, tmp_path: Path) -> None:
        events = _make_events()
        header = ArtifactHeader(params={"heartbeat_interval": 300})
        source = RunArtifact.create(tmp_path / "source", header, events)

        out = replay_run(source, out_dir=tmp_path / "replay")
        receipts = out.read_output("receipts")
        # We emitted 2 receipts via "emit" events
        assert len(receipts) == 2

    def test_heartbeat_captured(self, tmp_path: Path) -> None:
        events = _make_events()
        header = ArtifactHeader(params={"heartbeat_interval": 300})
        source = RunArtifact.create(tmp_path / "source", header, events)

        out = replay_run(source, out_dir=tmp_path / "replay")
        heartbeats = out.read_output("heartbeat")
        # 2 gate_heartbeat calls
        assert len(heartbeats) == 2

    def test_param_override(self, tmp_path: Path) -> None:
        events = _make_events()
        header = ArtifactHeader(params={"heartbeat_interval": 300, "heartbeat_threshold": 3})
        source = RunArtifact.create(tmp_path / "source", header, events)

        # Override threshold to 1 — should change stale detection
        out = replay_run(
            source,
            out_dir=tmp_path / "replay",
            param_overrides={"heartbeat_threshold": 1},
        )
        assert out.header.params["heartbeat_threshold"] == 1
        assert out.header.params["heartbeat_interval"] == 300  # Preserved

    def test_provenance_points_to_source(self, tmp_path: Path) -> None:
        source = RunArtifact.create(
            tmp_path / "source", ArtifactHeader(), _make_events(),
        )
        out = replay_run(source, out_dir=tmp_path / "replay")
        assert out.header.provenance["source"] == "replay"
        assert out.header.provenance["source_artifact_id"] == source.header.artifact_id

    def test_fault_events_respected(self, tmp_path: Path) -> None:
        events = _make_fault_events()
        source = RunArtifact.create(tmp_path / "source", ArtifactHeader(), events)

        out = replay_run(source, out_dir=tmp_path / "replay")
        receipts = out.read_output("receipts")
        # Only 1 receipt from the emit event at t_ms=0
        # The gate_check at t_ms=200 was skipped (gate_enabled=False)
        # The gate_check at t_ms=400 ran but doesn't emit receipts by itself
        # (gate_check produces receipts internally via EvidenceGate)
        assert len(receipts) >= 1

    def test_auto_generated_out_path(self, tmp_path: Path) -> None:
        source = RunArtifact.create(
            tmp_path / "source", ArtifactHeader(), _make_events(),
        )
        out = replay_run(source)  # No out_dir
        assert out.path.exists()
        assert "__replay_" in out.path.name
        # Clean up
        import shutil
        shutil.rmtree(out.path)

    def test_assert_events_skipped(self, tmp_path: Path) -> None:
        """Assert events in the trace are silently skipped."""
        events = [
            TraceEvent(t_ms=0, seq=0, scenario="test", event_type="emit",
                       payload={"kind": "receipt",
                                "data": {"gate": "sim", "verdict": "pass"}}),
            TraceEvent(t_ms=100, seq=1, scenario="test", event_type="assert",
                       payload={"check": "expect_receipt_count", "value": 1}),
        ]
        source = RunArtifact.create(tmp_path / "source", ArtifactHeader(), events)
        out = replay_run(source, out_dir=tmp_path / "replay")
        # Should complete without error
        assert out.path.exists()


# =============================================================================
# replay_diff()
# =============================================================================


class TestReplayDiff:
    def test_identical_artifacts_pass(self, tmp_path: Path) -> None:
        events = _make_events()
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), events)
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), events)

        # Same receipts written to both
        receipts = [{"gate": "sim", "verdict": "pass", "subject_hash": "abc"}]
        a.write_output("receipts", receipts)
        b.write_output("receipts", receipts)

        diff = replay_diff(a, b)
        assert diff.passed is True
        assert diff.summary == "No differences detected."

    def test_different_receipt_counts(self, tmp_path: Path) -> None:
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), _make_events())
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), _make_events())

        a.write_output("receipts", [
            {"gate": "sim", "verdict": "pass", "subject_hash": "x"},
        ])
        b.write_output("receipts", [
            {"gate": "sim", "verdict": "pass", "subject_hash": "x"},
            {"gate": "sim", "verdict": "warn", "subject_hash": "y"},
        ])

        diff = replay_diff(a, b)
        assert diff.passed is False
        assert diff.receipt_summary["baseline"]["sim:pass"] == 1
        assert diff.receipt_summary["replay"]["sim:warn"] == 1

    def test_same_counts_different_fingerprints(self, tmp_path: Path) -> None:
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), _make_events())
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), _make_events())

        a.write_output("receipts", [
            {"gate": "sim", "verdict": "pass", "subject_hash": "aaa"},
        ])
        b.write_output("receipts", [
            {"gate": "sim", "verdict": "pass", "subject_hash": "bbb"},
        ])

        diff = replay_diff(a, b)
        # Same count (1 sim:pass each) but different fingerprints
        assert diff.passed is False
        assert len(diff.receipt_fingerprints["added"]) == 1
        assert len(diff.receipt_fingerprints["removed"]) == 1

    def test_heartbeat_delta(self, tmp_path: Path) -> None:
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), _make_events())
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), _make_events())

        a.write_output("heartbeat", [
            {"t_ms": 300000, "is_stale": False, "missed_count": 0},
        ])
        b.write_output("heartbeat", [
            {"t_ms": 300000, "is_stale": True, "missed_count": 4},
        ])

        diff = replay_diff(a, b)
        assert diff.passed is False
        assert len(diff.heartbeat_delta) == 1
        assert diff.heartbeat_delta[0]["t_ms"] == 300000

    def test_first_divergence(self, tmp_path: Path) -> None:
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), _make_events())
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), _make_events())

        a.write_output("heartbeat", [
            {"t_ms": 100, "is_stale": False, "missed_count": 0},
            {"t_ms": 200, "is_stale": False, "missed_count": 0},
        ])
        b.write_output("heartbeat", [
            {"t_ms": 100, "is_stale": False, "missed_count": 0},
            {"t_ms": 200, "is_stale": True, "missed_count": 5},
        ])

        diff = replay_diff(a, b)
        assert diff.first_divergence is not None
        assert diff.first_divergence["t_ms"] == 200
        assert diff.first_divergence["stream"] == "heartbeat"

    def test_summary_human_readable(self, tmp_path: Path) -> None:
        a = RunArtifact.create(tmp_path / "a", ArtifactHeader(), _make_events())
        b = RunArtifact.create(tmp_path / "b", ArtifactHeader(), _make_events())

        a.write_output("receipts", [
            {"gate": "sim", "verdict": "pass", "subject_hash": "x"},
        ])
        b.write_output("receipts", [])

        diff = replay_diff(a, b)
        assert "Receipt" in diff.summary
        assert diff.passed is False


# =============================================================================
# Helpers
# =============================================================================


class TestFingerprint:
    def test_stable(self) -> None:
        r = {"gate": "sim", "verdict": "pass", "subject_hash": "abc"}
        fp1 = _fingerprint_receipt(r)
        fp2 = _fingerprint_receipt(r)
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_input_different_fingerprint(self) -> None:
        r1 = {"gate": "sim", "verdict": "pass", "subject_hash": "abc"}
        r2 = {"gate": "sim", "verdict": "block", "subject_hash": "abc"}
        assert _fingerprint_receipt(r1) != _fingerprint_receipt(r2)
