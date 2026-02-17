# SPDX-License-Identifier: Apache-2.0
"""Tests for convergence telemetry: field helpers, collector methods, instrumentation, analysis."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from governor.telemetry import (
    AnchorStats,
    ConvergenceReport,
    ContinuityResultFields,
    ContinuityTraceFields,
    TelemetryBackend,
    TelemetryCollector,
    TelemetryConfig,
    TelemetryEvent,
    TelemetryEventType,
    TelemetryLevel,
    analyze_convergence,
)
from governor.continuity import (
    Anchor,
    AnchorType,
    ConvergenceBudget,
    ConvergenceExecutor,
    ContinuityChecker,
    CorrectionLadder,
    ContinuityReport,
    GenerationProvider,
    Severity,
    Violation,
    create_convergence_executor,
)


# =============================================================================
# Helpers
# =============================================================================


class _CaptureBackend(TelemetryBackend):
    """Backend that captures events in a list."""

    def __init__(self):
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class _FailingBackend(TelemetryBackend):
    """Backend that always raises."""

    def record(self, event: TelemetryEvent) -> None:
        raise RuntimeError("backend exploded")


class _SimpleProvider:
    """Provider that returns items from a list in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if self._index >= len(self._responses):
            return self._responses[-1]
        result = self._responses[self._index]
        self._index += 1
        return result


class _ErrorProvider:
    """Provider that raises on first call then succeeds."""

    def __init__(self, success_text: str):
        self._called = False
        self._text = success_text

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if not self._called:
            self._called = True
            raise RuntimeError("generation failed")
        return self._text


def _make_anchor(aid: str, required: list[str] | None = None, forbidden: list[str] | None = None) -> Anchor:
    return Anchor(
        id=aid,
        anchor_type=AnchorType.REQUIREMENT,
        description=f"Anchor {aid}",
        required_patterns=required or [],
        forbidden_patterns=forbidden or [],
        severity=Severity.CORRECT,
    )


def _make_trace_event(
    run_id: str = "abc123",
    attempt: int = 0,
    error_total: float = 0.5,
    error_by_anchor: dict | None = None,
    action: str = "none",
    tokens: int = 100,
    latency_ms: float = 50.0,
    delta_total: float | None = None,
    delta_by_anchor: dict | None = None,
    mode: str = "fiction",
    anchors_hash: str = "hash123",
) -> TelemetryEvent:
    fields: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "attempt": attempt,
        "error_total": error_total,
        "error_by_anchor": error_by_anchor or {},
        "violations": [],
        "action": action,
        "action_params": {},
        "tokens": tokens,
        "latency_ms": latency_ms,
        "prompt_hash": "phash",
        "anchors_hash": anchors_hash,
    }
    if delta_total is not None:
        fields["delta_total"] = delta_total
    if delta_by_anchor:
        fields["delta_by_anchor"] = delta_by_anchor
    return TelemetryEvent(
        timestamp="2026-01-15T00:00:00+00:00",
        event_type=TelemetryEventType.CONTINUITY_TRACE,
        level=TelemetryLevel.INFO,
        fields=fields,
    )


def _make_result_event(
    run_id: str = "abc123",
    attempts: int = 1,
    final_status: str = "ACCEPTED",
    residual_error_total: float = 0.0,
    residual_error_by_anchor: dict | None = None,
    action_path: list[str] | None = None,
    total_tokens: int = 100,
    total_latency_ms: float = 50.0,
    monotone: bool = True,
    oscillation_detected: bool = False,
    deadzone_actions: list[str] | None = None,
    interference_edges: list[dict] | None = None,
    mode: str = "fiction",
    anchors_hash: str = "hash123",
    timestamp: str = "2026-01-15T00:00:00+00:00",
) -> TelemetryEvent:
    return TelemetryEvent(
        timestamp=timestamp,
        event_type=TelemetryEventType.CONTINUITY_RESULT,
        level=TelemetryLevel.INFO if final_status == "ACCEPTED" else TelemetryLevel.WARN,
        fields={
            "run_id": run_id,
            "mode": mode,
            "attempts": attempts,
            "final_status": final_status,
            "residual_error_total": residual_error_total,
            "residual_error_by_anchor": residual_error_by_anchor or {},
            "action_path": action_path or ["none"],
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency_ms,
            "monotone": monotone,
            "oscillation_detected": oscillation_detected,
            "deadzone_actions": deadzone_actions or [],
            "interference_edges": interference_edges or [],
            "anchors_hash": anchors_hash,
        },
    )


# =============================================================================
# TestContinuityTraceFields
# =============================================================================


class TestContinuityTraceFields:
    def test_defaults(self):
        f = ContinuityTraceFields()
        assert f.run_id == ""
        assert f.attempt == 0
        assert f.delta_total is None

    def test_to_dict(self):
        f = ContinuityTraceFields(run_id="r1", mode="fiction", attempt=1, error_total=0.5)
        d = f.to_dict()
        assert d["run_id"] == "r1"
        assert d["mode"] == "fiction"
        assert d["error_total"] == 0.5
        assert "delta_total" not in d  # None omitted

    def test_from_dict(self):
        d = {"run_id": "r2", "attempt": 3, "error_total": 0.25, "delta_total": -0.1}
        f = ContinuityTraceFields.from_dict(d)
        assert f.run_id == "r2"
        assert f.attempt == 3
        assert f.delta_total == -0.1

    def test_roundtrip(self):
        f = ContinuityTraceFields(
            run_id="r1", mode="code", attempt=2, error_total=0.333333,
            error_by_anchor={"a1": 2.0}, delta_total=-0.1, delta_by_anchor={"a1": -1.0},
            tokens=50, latency_ms=25.123, prompt_hash="ph", anchors_hash="ah",
        )
        d = f.to_dict()
        f2 = ContinuityTraceFields.from_dict(d)
        assert f2.run_id == f.run_id
        assert f2.delta_total == round(f.delta_total, 6)

    def test_delta_none_omitted(self):
        f = ContinuityTraceFields(attempt=0)
        d = f.to_dict()
        assert "delta_total" not in d

    def test_float_rounding(self):
        f = ContinuityTraceFields(error_total=0.33333333, latency_ms=100.12345)
        d = f.to_dict()
        assert d["error_total"] == 0.333333
        assert d["latency_ms"] == 100.12

    def test_empty_collections(self):
        f = ContinuityTraceFields()
        d = f.to_dict()
        assert d["error_by_anchor"] == {}
        assert d["violations"] == []

    def test_missing_fields_from_dict(self):
        f = ContinuityTraceFields.from_dict({})
        assert f.run_id == ""
        assert f.attempt == 0
        assert f.delta_total is None


# =============================================================================
# TestContinuityResultFields
# =============================================================================


class TestContinuityResultFields:
    def test_defaults(self):
        f = ContinuityResultFields()
        assert f.final_status == "REFUSED"
        assert f.monotone is False

    def test_to_dict(self):
        f = ContinuityResultFields(run_id="r1", final_status="ACCEPTED", monotone=True)
        d = f.to_dict()
        assert d["final_status"] == "ACCEPTED"
        assert d["monotone"] is True

    def test_from_dict(self):
        d = {"run_id": "r1", "final_status": "ESCALATED", "attempts": 5}
        f = ContinuityResultFields.from_dict(d)
        assert f.final_status == "ESCALATED"
        assert f.attempts == 5

    def test_roundtrip(self):
        f = ContinuityResultFields(
            run_id="r1", mode="fiction", attempts=3, final_status="ACCEPTED",
            residual_error_total=0.1, action_path=["none", "soft_reprompt"],
            total_tokens=500, total_latency_ms=200.0, monotone=True,
        )
        d = f.to_dict()
        f2 = ContinuityResultFields.from_dict(d)
        assert f2.run_id == f.run_id
        assert f2.action_path == f.action_path

    def test_all_statuses(self):
        for status in ("ACCEPTED", "REFUSED", "ESCALATED"):
            f = ContinuityResultFields(final_status=status)
            assert f.to_dict()["final_status"] == status

    def test_float_rounding(self):
        f = ContinuityResultFields(
            residual_error_total=0.33333333, total_latency_ms=100.12345
        )
        d = f.to_dict()
        assert d["residual_error_total"] == 0.333333
        assert d["total_latency_ms"] == 100.12

    def test_interference_edges(self):
        edges = [{"from_anchor": "a1", "to_anchor": "a2"}]
        f = ContinuityResultFields(interference_edges=edges)
        d = f.to_dict()
        assert d["interference_edges"] == edges

    def test_missing_fields_from_dict(self):
        f = ContinuityResultFields.from_dict({})
        assert f.run_id == ""
        assert f.monotone is False


# =============================================================================
# TestCollectorMethods
# =============================================================================


class TestCollectorMethods:
    def test_trace_emitted(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        c.record_continuity_trace(run_id="r1", attempt=0)
        assert len(cap.events) == 1
        assert cap.events[0].event_type == TelemetryEventType.CONTINUITY_TRACE

    def test_trace_fields_match(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        c.record_continuity_trace(
            run_id="r1", mode="fiction", attempt=2,
            error_total=0.5, tokens=200, latency_ms=75.0,
        )
        f = cap.events[0].fields
        assert f["run_id"] == "r1"
        assert f["mode"] == "fiction"
        assert f["attempt"] == 2
        assert f["error_total"] == 0.5
        assert f["tokens"] == 200

    def test_result_emitted(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        c.record_continuity_result(run_id="r1", final_status="ACCEPTED")
        assert len(cap.events) == 1
        assert cap.events[0].event_type == TelemetryEventType.CONTINUITY_RESULT

    def test_accepted_is_info(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        c.record_continuity_result(final_status="ACCEPTED")
        assert cap.events[0].level == TelemetryLevel.INFO

    def test_refused_is_warn(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        c.record_continuity_result(final_status="REFUSED")
        assert cap.events[0].level == TelemetryLevel.WARN

    def test_no_backend_noop(self):
        c = TelemetryCollector()
        # Should not raise
        c.record_continuity_trace(run_id="r1")
        c.record_continuity_result(run_id="r1")
        assert c.event_count == 2

    def test_failing_backend_swallowed(self):
        c = TelemetryCollector()
        c.add_backend(_FailingBackend())
        # Should not raise
        c.record_continuity_trace(run_id="r1")
        c.record_continuity_result(run_id="r1")

    def test_redaction(self):
        config = TelemetryConfig(redact_prompts=True)
        cap = _CaptureBackend()
        c = TelemetryCollector(config=config)
        c.add_backend(cap)
        c.record_continuity_trace(run_id="r1", prompt_hash="secret_hash")
        # prompt_hash is kept (already opaque)
        assert "prompt_hash" in cap.events[0].fields


# =============================================================================
# TestInstrumentedExecutor
# =============================================================================


class TestInstrumentedExecutor:
    def _make_executor(self, provider, collector=None, **kwargs):
        return ConvergenceExecutor(
            provider=provider,
            budget=ConvergenceBudget(max_attempts=5),
            collector=collector,
            **kwargs,
        )

    def test_first_try_converge(self):
        """Output that passes on first attempt."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello world"])
        ex = self._make_executor(provider, collector=c, mode="fiction")
        result = ex.converge_generate("test prompt", [anchor])
        assert result.converged
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert len(traces) == 1
        assert len(results) == 1
        assert results[0].fields["final_status"] == "ACCEPTED"

    def test_retry_traces(self):
        """Multiple attempts emit multiple traces."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["no match", "hello world"])
        ex = self._make_executor(provider, collector=c, mode="code")
        result = ex.converge_generate("test", [anchor])
        assert result.converged
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        assert len(traces) == 2

    def test_fail_closed_refused(self):
        """Exhausted budget emits REFUSED result."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["never_found"])
        provider = _SimpleProvider(["no match"] * 10)
        ex = ConvergenceExecutor(
            provider=provider,
            budget=ConvergenceBudget(max_attempts=2),
            collector=c,
            mode="fiction",
        )
        result = ex.converge_generate("test", [anchor])
        assert not result.converged
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert len(results) == 1
        assert results[0].fields["final_status"] in ("REFUSED", "ESCALATED")

    def test_run_id_shared(self):
        """All events from one run share the same run_id."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["no match", "hello world"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        run_ids = {e.fields["run_id"] for e in cap.events}
        assert len(run_ids) == 1

    def test_attempt_numbers(self):
        """Trace attempt numbers increment from 0."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["miss", "miss", "hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        attempts = [t.fields["attempt"] for t in traces]
        assert attempts == [0, 1, 2]

    def test_error_total_computed(self):
        """error_total is 1-score."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        # Passed on first try, score=1.0, error=0.0
        assert traces[0].fields["error_total"] == 0.0

    def test_delta_computed(self):
        """Delta is computed for attempt > 0."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["miss", "hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        assert "delta_total" not in traces[0].fields  # attempt 0
        assert "delta_total" in traces[1].fields  # attempt 1

    def test_delta_none_for_attempt_0(self):
        """Attempt 0 has no delta."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        assert "delta_total" not in traces[0].fields

    def test_action_path(self):
        """Result includes action path."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["miss", "hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        ap = results[0].fields["action_path"]
        assert isinstance(ap, list)
        assert len(ap) == 2  # two attempts

    def test_monotone_detection(self):
        """Monotone flag is True when error decreases every step."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        # First miss (1 violation), then hit (0 violations)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["miss", "hello"])
        ex = self._make_executor(provider, collector=c)
        ex.converge_generate("test", [anchor])
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert results[0].fields["monotone"] is True

    def test_no_collector_backward_compat(self):
        """Executor works without collector (backward compat)."""
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex = ConvergenceExecutor(provider=provider)
        result = ex.converge_generate("test", [anchor])
        assert result.converged

    def test_anchors_hash_deterministic(self):
        """Same anchors produce same hash across invocations."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex1 = self._make_executor(provider, collector=c)
        ex1.converge_generate("test", [anchor])

        cap2 = _CaptureBackend()
        c2 = TelemetryCollector()
        c2.add_backend(cap2)
        provider2 = _SimpleProvider(["hello"])
        ex2 = self._make_executor(provider2, collector=c2)
        ex2.converge_generate("test", [anchor])

        h1 = cap.events[0].fields["anchors_hash"]
        h2 = cap2.events[0].fields["anchors_hash"]
        assert h1 == h2

    def test_collector_exception_swallowed(self):
        """Broken collector doesn't crash executor."""
        mock_collector = MagicMock()
        mock_collector.record_continuity_trace.side_effect = RuntimeError("boom")
        mock_collector.record_continuity_result.side_effect = RuntimeError("boom")
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex = ConvergenceExecutor(
            provider=provider,
            collector=mock_collector,
        )
        result = ex.converge_generate("test", [anchor])
        assert result.converged

    def test_create_convenience_with_collector(self):
        """create_convergence_executor forwards collector and mode."""
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        provider = _SimpleProvider(["hello"])
        ex = create_convergence_executor(provider=provider, collector=c, mode="nonfiction")
        ex.converge_generate("test", [anchor])
        assert cap.events[0].fields["mode"] == "nonfiction"


# =============================================================================
# TestOneShotGateTelemetry
# =============================================================================


class TestOneShotGateTelemetry:
    def _make_hooks(self, anchors):
        """Create GovernorHooks with mocked context and anchors."""
        from governor.chat_bridge import GovernorHooks
        from governor.context_manager import GovernorContext
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gov_dir = root / ".governor"
            gov_dir.mkdir()
            ctx = GovernorContext(
                context_id="test-ctx",
                mode="fiction",
                root=root,
                governor_dir=gov_dir,
                created_at="2026-01-15T00:00:00+00:00",
            )
            hooks = GovernorHooks(ctx)
            # Monkey-patch _load_mode_anchors to return our test anchors
            hooks._load_mode_anchors = lambda: anchors
            yield hooks

    def test_emits_events(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        for hooks in self._make_hooks([anchor]):
            hooks.check_response("hello world", collector=c)
        traces = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_TRACE]
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert len(traces) == 1
        assert len(results) == 1

    def test_no_violations_accepted(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        for hooks in self._make_hooks([anchor]):
            hooks.check_response("hello world", collector=c)
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert results[0].fields["final_status"] == "ACCEPTED"

    def test_violations_refused(self):
        cap = _CaptureBackend()
        c = TelemetryCollector()
        c.add_backend(cap)
        anchor = _make_anchor("a1", required=["hello"])
        for hooks in self._make_hooks([anchor]):
            hooks.check_response("no match here", collector=c)
        results = [e for e in cap.events if e.event_type == TelemetryEventType.CONTINUITY_RESULT]
        assert results[0].fields["final_status"] == "REFUSED"

    def test_no_collector_ok(self):
        """check_response works without collector."""
        anchor = _make_anchor("a1", required=["hello"])
        for hooks in self._make_hooks([anchor]):
            result = hooks.check_response("hello world")
            assert result == []

    def test_collector_failure_swallowed(self):
        """Broken collector doesn't crash check_response."""
        mock_collector = MagicMock()
        mock_collector.record_continuity_trace.side_effect = RuntimeError("boom")
        anchor = _make_anchor("a1", required=["hello"])
        for hooks in self._make_hooks([anchor]):
            # Should not raise
            result = hooks.check_response("hello world", collector=mock_collector)
            assert result == []


# =============================================================================
# TestAnalyzeConvergence
# =============================================================================


class TestAnalyzeConvergence:
    def test_empty_events(self):
        report = analyze_convergence([])
        assert report.total_runs == 0
        assert report.acceptance_rate == 0.0

    def test_single_accepted(self):
        events = [
            _make_trace_event(run_id="r1", attempt=0, error_total=0.0),
            _make_result_event(run_id="r1", final_status="ACCEPTED", attempts=1),
        ]
        report = analyze_convergence(events)
        assert report.total_runs == 1
        assert report.accepted == 1
        assert report.acceptance_rate == 1.0

    def test_refused_and_escalated(self):
        events = [
            _make_result_event(run_id="r1", final_status="REFUSED"),
            _make_result_event(run_id="r2", final_status="ESCALATED"),
            _make_result_event(run_id="r3", final_status="ACCEPTED"),
        ]
        report = analyze_convergence(events)
        assert report.total_runs == 3
        assert report.refused == 1
        assert report.escalated == 1
        assert report.accepted == 1

    def test_avg_attempts(self):
        events = [
            _make_result_event(run_id="r1", attempts=3),
            _make_result_event(run_id="r2", attempts=1),
        ]
        report = analyze_convergence(events)
        assert report.avg_attempts == 2.0

    def test_efficiency(self):
        events = [
            _make_trace_event(run_id="r1", attempt=0, error_total=1.0),
            _make_trace_event(run_id="r1", attempt=1, error_total=0.0),
            _make_result_event(
                run_id="r1", final_status="ACCEPTED",
                residual_error_total=0.0, total_tokens=100,
            ),
        ]
        report = analyze_convergence(events)
        # efficiency = tokens / error_reduction = 100 / 1.0 = 100.0
        assert report.efficiency == 100.0

    def test_monotone_rate(self):
        events = [
            _make_result_event(run_id="r1", monotone=True),
            _make_result_event(run_id="r2", monotone=False),
        ]
        report = analyze_convergence(events)
        assert report.monotone_rate == 0.5

    def test_oscillation_rate(self):
        events = [
            _make_result_event(run_id="r1", oscillation_detected=True),
            _make_result_event(run_id="r2", oscillation_detected=False),
            _make_result_event(run_id="r3", oscillation_detected=True),
        ]
        report = analyze_convergence(events)
        assert abs(report.oscillation_rate - 2 / 3) < 0.01

    def test_windup(self):
        events = [
            # Trace attempt 0 with error 0.5, result with residual 0.5 after 3 attempts
            _make_trace_event(run_id="r1", attempt=0, error_total=0.5),
            _make_result_event(
                run_id="r1", final_status="REFUSED",
                residual_error_total=0.5, attempts=3,
            ),
        ]
        report = analyze_convergence(events)
        assert report.windup_count == 1

    def test_anchor_stats_violations(self):
        events = [
            _make_trace_event(
                run_id="r1", attempt=0, error_by_anchor={"a1": 2.0, "a2": 1.0}
            ),
            _make_result_event(run_id="r1"),
        ]
        report = analyze_convergence(events)
        assert "a1" in report.anchor_stats
        assert report.anchor_stats["a1"].violation_count == 2
        assert report.anchor_stats["a2"].violation_count == 1

    def test_anchor_action_success_rates(self):
        events = [
            _make_trace_event(
                run_id="r1", attempt=0,
                error_by_anchor={"a1": 2.0}, action="none",
            ),
            _make_trace_event(
                run_id="r1", attempt=1,
                error_by_anchor={"a1": 0.0}, action="soft_reprompt",
            ),
            _make_result_event(run_id="r1"),
        ]
        report = analyze_convergence(events)
        stats = report.anchor_stats.get("a1")
        assert stats is not None
        # soft_reprompt reduced a1 from 2 to 0 → success
        assert "soft_reprompt" in stats.action_success_rates
        assert stats.action_success_rates["soft_reprompt"] == 1.0

    def test_interference_graph(self):
        events = [
            _make_result_event(
                run_id="r1",
                interference_edges=[{"from_anchor": "a1", "to_anchor": "a2"}],
            ),
            _make_result_event(
                run_id="r2",
                interference_edges=[{"from_anchor": "a1", "to_anchor": "a2"}],
            ),
        ]
        report = analyze_convergence(events)
        assert "a1\u2192a2" in report.interference_graph
        assert report.interference_graph["a1\u2192a2"] == 2

    def test_since_filter(self):
        events = [
            _make_result_event(run_id="r1", timestamp="2026-01-01T00:00:00+00:00"),
            _make_result_event(run_id="r2", timestamp="2026-01-20T00:00:00+00:00"),
        ]
        report = analyze_convergence(events, since="2026-01-10T00:00:00+00:00")
        assert report.total_runs == 1


# =============================================================================
# TestConvergenceReport
# =============================================================================


class TestConvergenceReport:
    def test_to_dict(self):
        r = ConvergenceReport(total_runs=5, accepted=3, refused=1, escalated=1)
        d = r.to_dict()
        assert d["total_runs"] == 5
        assert d["accepted"] == 3

    def test_anchor_stats_nested(self):
        r = ConvergenceReport(
            anchor_stats={"a1": AnchorStats(anchor_id="a1", violation_count=3)}
        )
        d = r.to_dict()
        assert d["anchor_stats"]["a1"]["violation_count"] == 3

    def test_defaults(self):
        r = ConvergenceReport()
        assert r.total_runs == 0
        assert r.efficiency == 0.0
        assert r.anchor_stats == {}


# =============================================================================
# TestEnumUpdate
# =============================================================================


class TestEnumUpdate:
    def test_count_is_12(self):
        assert len(TelemetryEventType) == 12

    def test_new_values_exist(self):
        assert TelemetryEventType.CONTINUITY_TRACE.value == "continuity_trace"
        assert TelemetryEventType.CONTINUITY_RESULT.value == "continuity_result"
