# SPDX-License-Identifier: Apache-2.0
"""Tests for governor_sim.runner."""

from datetime import datetime, timezone

import pytest

from governor_sim.runner import InprocRunner, RunResult, SimClock, _compare
from governor_sim.schema import TraceEvent


class TestSimClock:
    def test_initial_epoch(self):
        clock = SimClock()
        assert clock.now == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_advance(self):
        clock = SimClock()
        clock.advance_to(60_000)
        assert clock.now == datetime(1970, 1, 1, 0, 1, 0, tzinfo=timezone.utc)

    def test_backwards_raises(self):
        clock = SimClock()
        clock.advance_to(1000)
        with pytest.raises(ValueError, match="cannot go backwards"):
            clock.advance_to(500)


class TestRunResult:
    def test_passed_when_no_errors_and_all_pass(self):
        r = RunResult(assertion_results=[{"passed": True}, {"passed": True}])
        assert r.passed is True

    def test_failed_on_assertion_failure(self):
        r = RunResult(assertion_results=[{"passed": True}, {"passed": False}])
        assert r.passed is False

    def test_failed_on_error(self):
        r = RunResult(errors=["boom"])
        assert r.passed is False

    def test_empty_passes(self):
        r = RunResult()
        assert r.passed is True


class TestCompare:
    def test_eq(self):
        assert _compare(3, "eq", 3) is True
        assert _compare(3, "eq", 4) is False

    def test_gte(self):
        assert _compare(3, "gte", 3) is True
        assert _compare(4, "gte", 3) is True
        assert _compare(2, "gte", 3) is False

    def test_unknown_op(self):
        with pytest.raises(ValueError, match="unknown comparison"):
            _compare(1, "approx", 1)


class TestInprocRunner:
    def test_gate_check_produces_receipt(self, tmp_path):
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="test", event_type="call",
                payload={"target": "gate_check", "output": "hello world", "task": "greet"},
            ),
        ]
        result = runner.run(events)
        assert result.events_processed == 1
        assert result.passed is True
        api = runner._get_api()
        assert api.receipt_count() >= 1

    def test_heartbeat_reports_stale_after_gap(self, tmp_path):
        """Emit one receipt, then check heartbeat 20 minutes later."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="test", event_type="emit",
                payload={
                    "kind": "receipt",
                    "data": {
                        "gate": "evidence_gate",
                        "verdict": "pass",
                        "subject_kind": "sim_event",
                        "subject_bytes": "",
                        "evidence_bundle": {},
                        "gate_config": {},
                    },
                },
            ),
            TraceEvent(
                t_ms=1_200_000, seq=1, scenario="test", event_type="assert",
                payload={"check": "expect_stale", "value": True, "session_active": True},
            ),
        ]
        result = runner.run(events)
        assert result.events_processed == 2
        assert result.assertion_results[0]["passed"] is True

    def test_fault_injection_skips_gate(self, tmp_path):
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="test", event_type="fault",
                payload={"flag": "gate_enabled", "value": False},
            ),
            TraceEvent(
                t_ms=100, seq=1, scenario="test", event_type="call",
                payload={"target": "gate_check", "output": "should be skipped"},
            ),
            TraceEvent(
                t_ms=200, seq=2, scenario="test", event_type="assert",
                payload={"check": "expect_receipt_count", "value": 0},
            ),
        ]
        result = runner.run(events)
        assert result.events_processed == 3
        assert result.assertion_results[0]["passed"] is True

    def test_assert_expect_fault_state(self, tmp_path):
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="test", event_type="fault",
                payload={"flag": "gate_enabled", "value": False},
            ),
            TraceEvent(
                t_ms=100, seq=1, scenario="test", event_type="assert",
                payload={"check": "expect_fault_state", "flag": "gate_enabled", "value": False},
            ),
        ]
        result = runner.run(events)
        assert result.assertion_results[0]["passed"] is True

    def test_params_override_heartbeat_config(self, tmp_path):
        """Header params flow through to SimAPI heartbeat config."""
        runner = InprocRunner(
            work_dir=tmp_path,
            params={"heartbeat_interval": 60, "heartbeat_grace": 10, "heartbeat_threshold": 2},
        )
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="test", event_type="emit",
                payload={
                    "kind": "receipt",
                    "data": {"gate": "evidence_gate", "verdict": "pass"},
                },
            ),
            # 130s later with interval=60, grace=10, threshold=2:
            # missed = floor((130 - 10) / 60) = 2  →  stale (threshold=2)
            TraceEvent(
                t_ms=130_000, seq=1, scenario="test", event_type="assert",
                payload={"check": "expect_stale", "value": True, "session_active": True},
            ),
        ]
        result = runner.run(events)
        assert result.assertion_results[0]["passed"] is True

    def test_subject_bytes_type_error(self, tmp_path):
        """Non-str, non-bytes subject_bytes raises TypeError, not silent coerce."""
        from governor_sim.api import SimAPI
        api = SimAPI(gov_dir=tmp_path / ".governor")
        (tmp_path / ".governor" / "receipts").mkdir(parents=True)
        with pytest.raises(TypeError, match="subject_bytes must be str"):
            api.emit_receipt({"subject_bytes": 42})
