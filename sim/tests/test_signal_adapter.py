# SPDX-License-Identifier: Apache-2.0
"""Tests for sim → signal pipeline.

Golden test: one sim fixture → receipts → EXPOSURE_PROXY signal →
stored in signals.jsonl → queryable via SignalStore.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor_sim.runner import InprocRunner
from governor_sim.schema import TraceEvent
from governor_sim.signal_adapter import SimRunContext, derive_signals_from_run


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_gate_check_event(t_ms: int, seq: int, output: str, **kwargs) -> TraceEvent:
    """Shorthand for a gate_check call event."""
    return TraceEvent(
        t_ms=t_ms, seq=seq, scenario="test_signal", event_type="call",
        payload={"target": "gate_check", "output": output, "task": "test"},
        session_id="sim-signal-test", run_id="run-signal-001",
        **kwargs,
    )


def _make_receipt_event(t_ms: int, seq: int, gate: str = "evidence_gate",
                        independence_class: str = "tool") -> TraceEvent:
    """Shorthand for a receipt emit event."""
    return TraceEvent(
        t_ms=t_ms, seq=seq, scenario="test_signal", event_type="emit",
        payload={
            "kind": "receipt",
            "data": {
                "gate": gate,
                "verdict": "pass",
                "subject_kind": "sim_event",
                "subject_bytes": f"event_{seq}",
                "evidence_bundle": {
                    "independence_class": independence_class,
                    "source_channel": "cli",
                },
                "gate_config": {},
            },
        },
        session_id="sim-signal-test", run_id="run-signal-001",
    )


# ── SimRunContext ────────────────────────────────────────────────────────────

class TestSimRunContext:
    def test_frozen(self):
        ctx = SimRunContext(
            run_id="r1", session_id="s1", scenario="sc1",
            window_start="2026-01-01T00:00:00Z", window_end="2026-01-01T01:00:00Z",
        )
        with pytest.raises(AttributeError):
            ctx.run_id = "r2"  # type: ignore[misc]


# ── derive_signals_from_run (unit) ───────────────────────────────────────────

class TestDeriveSignals:
    def test_no_receipts_returns_empty(self, tmp_path):
        """No receipts → no signals (missing != zero)."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        ctx = SimRunContext(
            run_id="r1", session_id="s1", scenario="empty",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(gov_dir, ctx)
        assert result == []

    def test_with_receipts_returns_exposure_proxy(self, tmp_path):
        """Receipts present → one EXPOSURE_PROXY signal."""
        # Run a sim that produces receipts
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "hello"),
            _make_receipt_event(100, 1, gate="evidence_gate"),
            _make_gate_check_event(500, 2, "world"),
            _make_receipt_event(600, 3, gate="evidence_gate"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-001", session_id="sim-test", scenario="basic",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        assert len(result) == 1

        env = result[0]
        assert env.signal_id == "EXPOSURE_PROXY"
        assert env.phase == "2.4A"
        assert env.quality_status in ("ok", "partial")
        assert env.value is not None
        assert env.value > 0

    def test_signal_has_sim_provenance(self, tmp_path):
        """Signal envelope carries sim run context in source_versions."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "test"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-prov", session_id="sess-prov", scenario="provenance",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        assert len(result) == 1

        env = result[0]
        assert env.emitter == "governor_sim.signal_adapter"
        assert env.session_id == "sess-prov"
        assert env.source_versions.get("run_id") == "run-prov"
        assert env.source_versions.get("scenario") == "provenance"

    def test_signal_written_to_jsonl(self, tmp_path):
        """Signal is persisted to signals.jsonl after derivation."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "persist"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-persist", session_id="s1", scenario="persist",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        derive_signals_from_run(runner.gov_dir, ctx)

        jsonl_path = runner.gov_dir / "signals" / "signals.jsonl"
        assert jsonl_path.exists()
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["signal_id"] == "EXPOSURE_PROXY"

    def test_signal_values_are_stable(self, tmp_path):
        """Same receipts → same signal values (deterministic derivation).

        content_hash differs between calls because emitted_at uses wall
        clock (each emission is a unique event). But the computed values
        must be identical — same receipts, same counts, same weights.
        """
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "stable"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-stable", session_id="s1", scenario="stable",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        r1 = derive_signals_from_run(runner.gov_dir, ctx)
        r2 = derive_signals_from_run(runner.gov_dir, ctx)

        # Values (the computed payload) must be identical
        assert r1[0].values == r2[0].values
        assert r1[0].value == r2[0].value
        assert r1[0].quality_status == r2[0].quality_status
        assert r1[0].signal_id == r2[0].signal_id


# ── InprocRunner integration (emit_signals=True) ────────────────────────────

class TestRunnerSignalIntegration:
    def test_emit_signals_false_by_default(self, tmp_path):
        """Default: no signals emitted."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "no signals"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)
        assert runner.emitted_signals == []

        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert not signals_jsonl.exists()

    def test_emit_signals_true_produces_signal(self, tmp_path):
        """emit_signals=True → signals emitted post-run."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "with signals"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        assert len(runner.emitted_signals) == 1
        assert runner.emitted_signals[0].signal_id == "EXPOSURE_PROXY"

        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists()

    def test_emitted_signal_ingestable_by_store(self, tmp_path):
        """Signal emitted by runner can be ingested into SignalStore."""
        from governor.signal_store import SignalStore

        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "ingest test"),
            _make_receipt_event(100, 1, gate="evidence_gate"),
            _make_receipt_event(200, 2, gate="evidence_gate"),
        ]
        runner.run(events)

        # Ingest into SignalStore
        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        db_path = tmp_path / "signals.db"
        store = SignalStore(db_path)
        ingested = store.ingest_from_jsonl(signals_jsonl)

        assert ingested.inserted == 1
        assert store.count() == 1

        # Query it
        rows = store.query(signal_name="EXPOSURE_PROXY")
        assert len(rows) == 1
        assert rows[0]["signal_name"] == "EXPOSURE_PROXY"
        assert rows[0]["phase"] == "2.4A"

    def test_runner_infers_context_from_events(self, tmp_path):
        """Runner uses event metadata (run_id, session_id, scenario) if not overridden."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="inferred_scenario", event_type="call",
                payload={"target": "gate_check", "output": "test", "task": "t"},
                session_id="inferred_session", run_id="inferred_run",
            ),
            TraceEvent(
                t_ms=100, seq=1, scenario="inferred_scenario", event_type="emit",
                payload={
                    "kind": "receipt",
                    "data": {
                        "gate": "evidence_gate", "verdict": "pass",
                        "subject_kind": "sim_event", "subject_bytes": "x",
                        "evidence_bundle": {}, "gate_config": {},
                    },
                },
                session_id="inferred_session", run_id="inferred_run",
            ),
        ]
        runner.run(events)

        assert len(runner.emitted_signals) == 1
        env = runner.emitted_signals[0]
        assert env.session_id == "inferred_session"
        assert env.source_versions.get("run_id") == "inferred_run"
        assert env.source_versions.get("scenario") == "inferred_scenario"

    def test_no_receipts_no_signal(self, tmp_path):
        """Run with no receipt-producing events → no signals (missing != zero)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="empty", event_type="fault",
                payload={"flag": "gate_enabled", "value": False},
            ),
        ]
        runner.run(events)
        assert runner.emitted_signals == []


# ── Golden: full fixture scenario → signal → CLI-queryable ──────────────────

class TestGoldenFixtureToSignal:
    def test_healthy_fixture_produces_exposure_proxy(self, tmp_path):
        """Golden: the healthy fixture scenario produces receipts that
        derive into a queryable EXPOSURE_PROXY signal."""
        from governor.signal_store import SignalStore
        from governor_sim.dsl import load_scenario, compile_scenario

        fixture_path = (
            Path(__file__).parent.parent
            / "fixtures" / "phase_a" / "healthy"
            / "healthy__external_checks__steady__high_exposure__v0.json"
        )
        if not fixture_path.exists():
            pytest.skip(f"fixture not found: {fixture_path}")

        spec = load_scenario(fixture_path)
        header, events = compile_scenario(spec)

        runner = InprocRunner(
            work_dir=tmp_path,
            params=header.params,
            emit_signals=True,
        )
        result = runner.run(events)
        assert result.events_processed > 0

        # Signal emitted
        assert len(runner.emitted_signals) == 1
        env = runner.emitted_signals[0]
        assert env.signal_id == "EXPOSURE_PROXY"
        assert env.value is not None
        assert env.value > 0
        assert env.quality_status in ("ok", "partial")
        assert env.emitter == "governor_sim.signal_adapter"
        assert env.window_kind == "sim_run"

        # Signal is in JSONL
        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists()

        # Signal is ingestable and queryable
        db_path = tmp_path / "golden.db"
        store = SignalStore(db_path)
        ingested = store.ingest_from_jsonl(signals_jsonl)
        assert ingested.inserted == 1

        rows = store.query(signal_name="EXPOSURE_PROXY")
        assert len(rows) == 1
        assert rows[0]["signal_name"] == "EXPOSURE_PROXY"
        assert rows[0]["value"] > 0

        # Full envelope retrievable
        detail = store.get(rows[0]["signal_hash"])
        assert detail is not None
        assert detail["signal_name"] == "EXPOSURE_PROXY"
