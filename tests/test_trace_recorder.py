# SPDX-License-Identifier: Apache-2.0
"""Tests for governor.trace_recorder — receipt-only trace recording."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from governor.trace_recorder import ReceiptRecorder


# =============================================================================
# Helpers
# =============================================================================


def _write_receipt_line(gov_dir: Path, receipt: dict) -> None:
    """Append a receipt line to the JSONL log."""
    receipts_dir = gov_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / "gate_receipts.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(receipt) + "\n")


def _make_receipt(gate: str = "sim", verdict: str = "pass", ts: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "receipt_id": "r1",
        "schema_version": 2,
        "timestamp": ts,
        "gate": gate,
        "verdict": verdict,
        "subject_hash": "abc",
        "evidence_hash": "def",
        "policy_hash": "ghi",
    }


# =============================================================================
# Tests
# =============================================================================


class TestReceiptRecorder:
    def test_poll_picks_up_new_lines(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        # Write a receipt after recorder init
        _write_receipt_line(gov_dir, _make_receipt())

        events = recorder.poll()
        assert len(events) == 1
        assert events[0].event_type == "emit"
        assert events[0].payload["kind"] == "receipt"
        assert events[0].payload["data"]["gate"] == "sim"

    def test_each_receipt_becomes_emit_event(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        _write_receipt_line(gov_dir, _make_receipt(gate="a"))
        _write_receipt_line(gov_dir, _make_receipt(gate="b"))
        _write_receipt_line(gov_dir, _make_receipt(gate="c"))

        events = recorder.poll()
        assert len(events) == 3
        gates = [e.payload["data"]["gate"] for e in events]
        assert gates == ["a", "b", "c"]

    def test_monotonic_seq_across_polls(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        _write_receipt_line(gov_dir, _make_receipt())
        events1 = recorder.poll()

        _write_receipt_line(gov_dir, _make_receipt())
        events2 = recorder.poll()

        assert events1[0].seq == 0
        assert events2[0].seq == 1

    def test_t_ms_is_real_elapsed(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        _write_receipt_line(gov_dir, _make_receipt())
        events = recorder.poll()

        # t_ms should be >= 0 (some real time has passed since init)
        assert events[0].t_ms >= 0

    def test_finalize_writes_valid_artifact(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="incident_42")

        _write_receipt_line(gov_dir, _make_receipt(gate="evidence_gate"))
        _write_receipt_line(gov_dir, _make_receipt(gate="pre_commit"))

        out_dir = tmp_path / "artifact"
        artifact = recorder.finalize(out_dir)

        assert artifact.path == out_dir
        assert len(artifact.events) == 2
        assert artifact.header.provenance["source"] == "recorded-receipts"
        assert artifact.header.provenance["scenario"] == "incident_42"

        # Receipts output stream written
        receipts = artifact.read_output("receipts")
        assert len(receipts) == 2

    def test_finalize_does_final_poll(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        # Write AFTER init but don't poll manually
        _write_receipt_line(gov_dir, _make_receipt())

        # Finalize should pick it up
        artifact = recorder.finalize(tmp_path / "out")
        assert len(artifact.events) == 1

    def test_empty_poll_returns_no_events(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")
        events = recorder.poll()
        assert events == []

    def test_start_position_tracks_correctly(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        # Write a receipt BEFORE recorder init
        _write_receipt_line(gov_dir, _make_receipt(gate="pre_existing"))

        recorder = ReceiptRecorder(gov_dir, scenario="test")

        # This should NOT appear (it was written before recorder started)
        events = recorder.poll()
        assert len(events) == 0

        # New receipt AFTER init should appear
        _write_receipt_line(gov_dir, _make_receipt(gate="new"))
        events = recorder.poll()
        assert len(events) == 1
        assert events[0].payload["data"]["gate"] == "new"

    def test_scenario_propagated(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="deploy_rollback")

        _write_receipt_line(gov_dir, _make_receipt())
        events = recorder.poll()

        assert events[0].scenario == "deploy_rollback"

    def test_missing_receipt_file(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Don't create receipts dir

        recorder = ReceiptRecorder(gov_dir, scenario="test")
        events = recorder.poll()
        assert events == []

    def test_artifact_can_be_reloaded(self, tmp_path: Path) -> None:
        """Verify the artifact written by finalize can be loaded back."""
        from governor.replay import RunArtifact

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        recorder = ReceiptRecorder(gov_dir, scenario="test")
        _write_receipt_line(gov_dir, _make_receipt())
        _write_receipt_line(gov_dir, _make_receipt(verdict="block"))

        artifact = recorder.finalize(tmp_path / "out")
        loaded = RunArtifact.load(tmp_path / "out")

        assert len(loaded.events) == 2
        assert loaded.header.provenance["source"] == "recorded-receipts"
