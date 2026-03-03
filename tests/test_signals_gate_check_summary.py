# SPDX-License-Identifier: Apache-2.0
"""Tests for GATE_CHECK_SUMMARY signal — first live production signal."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from governor.signals.gate_check_summary import (
    DERIVATION_VERSION,
    SIGNAL_ID,
    SIGNAL_VERSION,
    build_gate_check_summary,
    build_gate_check_error_summary,
    try_emit_gate_check_summary,
)
from governor.signals.envelope import QualityStatus


# ── build_gate_check_summary ────────────────────────────────────────────────


class TestBuildGateCheckSummary:
    def test_ok_verdict(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=3,
            violations_count=0,
            warnings_count=1,
            session_id="gov_test123",
        )
        assert env.signal_id == SIGNAL_ID
        assert env.signal_version == SIGNAL_VERSION
        assert env.value == 1.0
        assert env.quality_status == QualityStatus.OK.value
        assert env.values["verdict"] == "OK"
        assert env.values["claims_count"] == 3
        assert env.values["violations_count"] == 0
        assert env.values["warnings_count"] == 1
        assert env.session_id == "gov_test123"

    def test_blocked_verdict(self):
        env = build_gate_check_summary(
            verdict="BLOCKED",
            claims_count=2,
            violations_count=3,
            warnings_count=0,
        )
        assert env.values["verdict"] == "BLOCKED"
        assert env.values["violations_count"] == 3
        assert env.value == 1.0  # still 1.0 — it happened

    def test_warn_verdict(self):
        env = build_gate_check_summary(
            verdict="WARN",
            claims_count=1,
            violations_count=0,
            warnings_count=2,
        )
        assert env.values["verdict"] == "WARN"
        assert env.value == 1.0

    def test_with_timing(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
            duration_ns=5_000_000,
        )
        assert env.values["duration_ns"] == 5_000_000

    def test_without_timing(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
        )
        assert "duration_ns" not in env.values

    def test_oracle_flag(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
            has_oracle_evidence=True,
        )
        assert env.values["has_oracle_evidence"] is True

    def test_oracle_flag_default_false(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
        )
        assert env.values["has_oracle_evidence"] is False

    def test_envelope_metadata(self):
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
        )
        assert env.emitter == "governor.signals.gate_check_summary"
        assert env.subject_type == "gate_invocation"
        assert env.unit == "event"
        assert env.derivation == "direct"
        assert env.derivation_version == DERIVATION_VERSION
        assert env.phase == "2.5"

    def test_zero_claims_zero_violations_still_emits(self):
        """Empty gate check is a valid event — value=1.0, not unavailable."""
        env = build_gate_check_summary(
            verdict="OK",
            claims_count=0,
            violations_count=0,
            warnings_count=0,
        )
        assert env.value == 1.0
        assert env.quality_status == QualityStatus.OK.value


# ── build_gate_check_error_summary ──────────────────────────────────────────


class TestBuildGateCheckErrorSummary:
    def test_error_produces_unavailable(self):
        env = build_gate_check_error_summary(
            error_type="ValueError",
            error_message="something broke",
            session_id="gov_err123",
        )
        assert env.signal_id == SIGNAL_ID
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        assert env.quality_reasons == ["gate_exception"]
        assert env.values["verdict"] == "ERROR"
        assert env.values["error_type"] == "ValueError"
        assert env.values["error_message"] == "something broke"
        assert env.values["claims_count"] == 0

    def test_error_with_timing(self):
        env = build_gate_check_error_summary(
            error_type="RuntimeError",
            error_message="timeout",
            duration_ns=10_000_000,
        )
        assert env.values["duration_ns"] == 10_000_000

    def test_error_message_capped(self):
        env = build_gate_check_error_summary(
            error_type="X",
            error_message="a" * 1000,
        )
        assert len(env.values["error_message"]) <= 500

    def test_error_type_capped(self):
        env = build_gate_check_error_summary(
            error_type="T" * 500,
            error_message="msg",
        )
        assert len(env.values["error_type"]) <= 200


# ── try_emit_gate_check_summary ─────────────────────────────────────────────


class TestTryEmit:
    def test_emits_to_sink(self):
        sink = MagicMock()
        env = build_gate_check_summary(
            verdict="OK", claims_count=1, violations_count=0, warnings_count=0,
        )
        try_emit_gate_check_summary(sink, env)
        sink.emit.assert_called_once_with(env)

    def test_none_sink_is_noop(self):
        env = build_gate_check_summary(
            verdict="OK", claims_count=0, violations_count=0, warnings_count=0,
        )
        # Should not raise
        try_emit_gate_check_summary(None, env)

    def test_sink_exception_does_not_raise(self):
        sink = MagicMock()
        sink.emit.side_effect = OSError("disk full")
        env = build_gate_check_summary(
            verdict="OK", claims_count=0, violations_count=0, warnings_count=0,
        )
        # Should not raise
        try_emit_gate_check_summary(sink, env)


# ── Content hash determinism ────────────────────────────────────────────────


class TestContentHash:
    def test_same_inputs_same_hash(self):
        kwargs = dict(
            verdict="BLOCKED",
            claims_count=2,
            violations_count=1,
            warnings_count=0,
            duration_ns=42,
            session_id="gov_stable",
            emitted_at="2026-03-03T00:00:00+00:00",
        )
        e1 = build_gate_check_summary(**kwargs)
        e2 = build_gate_check_summary(**kwargs)
        assert e1.content_hash() == e2.content_hash()

    def test_different_verdict_different_hash(self):
        common = dict(
            claims_count=1,
            violations_count=0,
            warnings_count=0,
            emitted_at="2026-03-03T00:00:00+00:00",
        )
        e1 = build_gate_check_summary(verdict="OK", **common)
        e2 = build_gate_check_summary(verdict="BLOCKED", **common)
        assert e1.content_hash() != e2.content_hash()


# ── CLI integration (end-to-end) ────────────────────────────────────────────


class TestCLIIntegration:
    def test_gate_check_emits_signal_to_jsonl(self, tmp_path):
        """governor gate check writes GATE_CHECK_SUMMARY to signals.jsonl."""
        from click.testing import CliRunner
        from governor.cli import cli

        # Initialize governor dir
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--root", str(tmp_path),
            "gate", "check", "This is perfectly fine text.",
        ])
        assert result.exit_code == 0, result.output

        signals_jsonl = gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists(), "signals.jsonl not created"

        lines = [l for l in signals_jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1

        parsed = json.loads(lines[-1])
        assert parsed["signal_id"] == "GATE_CHECK_SUMMARY"
        assert parsed["values"]["verdict"] in ("OK", "WARN", "BLOCKED")
        assert "duration_ns" in parsed["values"]

    def test_signal_ingestable_by_store(self, tmp_path):
        """GATE_CHECK_SUMMARY can be ingested into SignalStore and queried."""
        from click.testing import CliRunner
        from governor.cli import cli
        from governor.signal_store import SignalStore

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--root", str(tmp_path),
            "gate", "check", "The tests all pass.",
        ])
        assert result.exit_code == 0, result.output

        signals_jsonl = gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists()

        store = SignalStore(tmp_path / "test.db")
        ingested = store.ingest_from_jsonl(signals_jsonl)
        assert ingested.inserted >= 1

        rows = store.query(signal_name="GATE_CHECK_SUMMARY")
        assert len(rows) >= 1
        assert rows[0]["signal_name"] == "GATE_CHECK_SUMMARY"

    def test_no_signal_when_gov_dir_missing(self, tmp_path):
        """No governor dir → no signal emitted, no crash."""
        from click.testing import CliRunner
        from governor.cli import cli

        runner = CliRunner()
        # Run without governor init — no .governor/ dir
        result = runner.invoke(cli, [
            "--root", str(tmp_path),
            "gate", "check", "Hello world.",
        ])
        # Should still work (gate check doesn't require governor init)
        assert result.exit_code == 0, result.output

        signals_jsonl = tmp_path / ".governor" / "signals" / "signals.jsonl"
        assert not signals_jsonl.exists()
