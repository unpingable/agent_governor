"""
Tests for structured telemetry (Deferred 4, B2).

Covers: TelemetryConfig, TelemetryEvent, field dataclasses,
StructuredLogger, TelemetryCollector, analysis, export, edge cases.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from governor.telemetry import (
    TelemetryEventType,
    TelemetryLevel,
    LEVEL_ORDER,
    TelemetryConfig,
    TelemetryEvent,
    ProposalFields,
    VerificationFields,
    LLMCallFields,
    AutonomousIterationFields,
    ErrorFields,
    CostReport,
    PerformanceReport,
    LogStats,
    StructuredLogger,
    TelemetryBackend,
    LoggingBackend,
    TelemetryCollector,
    analyze_costs,
    analyze_performance,
    export_events,
    get_collector,
    get_logger,
    hash_prompt,
    _percentile,
)


# =============================================================================
# TestTelemetryConfig
# =============================================================================


class TestTelemetryConfig:
    """Tests for TelemetryConfig."""

    def test_defaults(self):
        c = TelemetryConfig()
        assert c.logging_enabled is True
        assert c.log_dir == "logs"
        assert c.log_retention_days == 30
        assert c.log_max_size_mb == 50.0
        assert c.prometheus_enabled is False
        assert c.redact_file_contents is True
        assert c.redact_prompts is False
        assert c.min_level == "info"

    def test_to_dict(self):
        c = TelemetryConfig(log_retention_days=7)
        d = c.to_dict()
        assert d["log_retention_days"] == 7
        assert "logging_enabled" in d

    def test_from_dict(self):
        d = {"logging_enabled": False, "log_retention_days": 14, "min_level": "warn"}
        c = TelemetryConfig.from_dict(d)
        assert c.logging_enabled is False
        assert c.log_retention_days == 14
        assert c.min_level == "warn"

    def test_from_dict_missing_fields(self):
        c = TelemetryConfig.from_dict({})
        assert c.logging_enabled is True
        assert c.log_dir == "logs"

    def test_roundtrip(self):
        c = TelemetryConfig(redact_prompts=True, log_max_size_mb=10.0)
        d = c.to_dict()
        c2 = TelemetryConfig.from_dict(d)
        assert c2.redact_prompts is True
        assert c2.log_max_size_mb == 10.0

    def test_save_and_load(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        c = TelemetryConfig(log_retention_days=5, redact_prompts=True)
        c.save(gov_dir)
        c2 = TelemetryConfig.load(gov_dir)
        assert c2.log_retention_days == 5
        assert c2.redact_prompts is True

    def test_load_missing(self, tmp_path):
        c = TelemetryConfig.load(tmp_path)
        assert c.logging_enabled is True  # defaults

    def test_min_level_enum(self):
        c = TelemetryConfig(min_level="warn")
        assert c.min_level_enum == TelemetryLevel.WARN

    def test_min_level_enum_invalid(self):
        c = TelemetryConfig(min_level="bogus")
        assert c.min_level_enum == TelemetryLevel.INFO  # fallback


# =============================================================================
# TestTelemetryEvent
# =============================================================================


class TestTelemetryEvent:
    """Tests for TelemetryEvent."""

    def test_creation(self):
        ev = TelemetryEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO,
        )
        assert ev.event_type == TelemetryEventType.PROPOSAL
        assert ev.level == TelemetryLevel.INFO
        assert len(ev.event_id) == 12

    def test_to_dict(self):
        ev = TelemetryEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type=TelemetryEventType.ERROR,
            level=TelemetryLevel.ERROR,
            event_id="abc123",
            agent_id="agent-1",
            duration_ms=42.5,
        )
        d = ev.to_dict()
        assert d["event_type"] == "error"
        assert d["level"] == "error"
        assert d["agent_id"] == "agent-1"
        assert d["duration_ms"] == 42.5

    def test_to_dict_optional_fields_omitted(self):
        ev = TelemetryEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO,
        )
        d = ev.to_dict()
        assert "agent_id" not in d
        assert "session_id" not in d
        assert "duration_ms" not in d

    def test_from_dict(self):
        d = {
            "timestamp": "2025-01-01T00:00:00Z",
            "event_type": "llm_call",
            "level": "warn",
            "event_id": "xyz",
            "fields": {"model": "gpt-4"},
            "agent_id": "a1",
            "session_id": "s1",
            "duration_ms": 100.0,
        }
        ev = TelemetryEvent.from_dict(d)
        assert ev.event_type == TelemetryEventType.LLM_CALL
        assert ev.level == TelemetryLevel.WARN
        assert ev.fields["model"] == "gpt-4"
        assert ev.agent_id == "a1"

    def test_from_dict_unknown_type(self):
        d = {"timestamp": "t", "event_type": "unknown_type", "level": "info"}
        ev = TelemetryEvent.from_dict(d)
        assert ev.event_type == TelemetryEventType.ERROR  # fallback

    def test_from_dict_unknown_level(self):
        d = {"timestamp": "t", "event_type": "error", "level": "critical"}
        ev = TelemetryEvent.from_dict(d)
        assert ev.level == TelemetryLevel.INFO  # fallback

    def test_roundtrip(self):
        ev = TelemetryEvent(
            timestamp="2025-06-15T12:00:00Z",
            event_type=TelemetryEventType.VERIFICATION,
            level=TelemetryLevel.WARN,
            event_id="r1",
            fields={"proposal_id": "p1", "success": True},
            agent_id="agent-x",
            duration_ms=55.0,
        )
        d = ev.to_dict()
        ev2 = TelemetryEvent.from_dict(d)
        assert ev2.event_type == ev.event_type
        assert ev2.fields == ev.fields
        assert ev2.agent_id == ev.agent_id

    def test_to_json_line(self):
        ev = TelemetryEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO,
            event_id="abc",
        )
        line = ev.to_json_line()
        d = json.loads(line)
        assert d["event_id"] == "abc"
        assert "\n" not in line

    def test_event_id_auto_generated(self):
        ev1 = TelemetryEvent(timestamp="t", event_type=TelemetryEventType.ERROR, level=TelemetryLevel.ERROR)
        ev2 = TelemetryEvent(timestamp="t", event_type=TelemetryEventType.ERROR, level=TelemetryLevel.ERROR)
        assert ev1.event_id != ev2.event_id


# =============================================================================
# TestFieldDataclasses
# =============================================================================


class TestFieldDataclasses:
    """Tests for field helper dataclasses."""

    def test_proposal_fields_roundtrip(self):
        pf = ProposalFields(proposal_id="p1", claim_count=3, claim_types=["file_exists"], outcome="verified")
        d = pf.to_dict()
        pf2 = ProposalFields.from_dict(d)
        assert pf2.proposal_id == "p1"
        assert pf2.claim_count == 3

    def test_verification_fields_roundtrip(self):
        vf = VerificationFields(proposal_id="p1", claim_index=2, success=True, receipt_type="FileSnapshot")
        d = vf.to_dict()
        vf2 = VerificationFields.from_dict(d)
        assert vf2.success is True
        assert vf2.receipt_type == "FileSnapshot"

    def test_llm_call_fields_roundtrip(self):
        lf = LLMCallFields(model="gpt-4", input_tokens=100, output_tokens=50, cost_usd=0.01)
        d = lf.to_dict()
        lf2 = LLMCallFields.from_dict(d)
        assert lf2.model == "gpt-4"
        assert lf2.cost_usd == 0.01

    def test_autonomous_iteration_fields_roundtrip(self):
        af = AutonomousIterationFields(session_id="s1", iteration=5, done=True, files_modified=["a.py"])
        d = af.to_dict()
        af2 = AutonomousIterationFields.from_dict(d)
        assert af2.iteration == 5
        assert af2.done is True
        assert af2.files_modified == ["a.py"]

    def test_error_fields_roundtrip(self):
        ef = ErrorFields(error_type="ValueError", message="bad input", module="claims")
        d = ef.to_dict()
        ef2 = ErrorFields.from_dict(d)
        assert ef2.error_type == "ValueError"
        assert ef2.module == "claims"

    def test_field_defaults(self):
        pf = ProposalFields(proposal_id="x")
        assert pf.claim_count == 0
        assert pf.claim_types == []
        assert pf.outcome == ""


# =============================================================================
# TestStructuredLogger
# =============================================================================


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def _make_event(self, event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO, ts=None):
        return TelemetryEvent(
            timestamp=ts or datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            level=level,
            fields={"test": True},
        )

    def test_write_creates_file(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event())
        files = logger.list_log_files()
        assert len(files) >= 1

    def test_write_appends(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event())
        logger.write(self._make_event())
        events = logger.read_events()
        assert len(events) == 2

    def test_read_filter_by_type(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event(TelemetryEventType.PROPOSAL))
        logger.write(self._make_event(TelemetryEventType.ERROR, TelemetryLevel.ERROR))
        logger.write(self._make_event(TelemetryEventType.PROPOSAL))
        events = logger.read_events(event_type=TelemetryEventType.PROPOSAL)
        assert len(events) == 2

    def test_read_filter_by_since(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event(ts="2025-01-01T00:00:00Z"))
        logger.write(self._make_event(ts="2025-06-01T00:00:00Z"))
        logger.write(self._make_event(ts="2025-12-01T00:00:00Z"))
        events = logger.read_events(since="2025-06-01T00:00:00Z")
        assert len(events) == 2

    def test_read_last_n(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        for i in range(10):
            logger.write(self._make_event(ts=f"2025-01-{i+1:02d}T00:00:00Z"))
        events = logger.read_events(last_n=3)
        assert len(events) == 3
        assert events[0].timestamp == "2025-01-08T00:00:00Z"

    def test_rotate_retention(self, tmp_path):
        log_dir = tmp_path / "logs"
        config = TelemetryConfig(log_retention_days=5)
        logger = StructuredLogger(log_dir, config)

        # Create old file
        old_file = log_dir / "governor-20240101.jsonl"
        old_file.write_text('{"timestamp":"t","event_type":"error","level":"info"}\n')

        # Create recent file
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        recent_file = log_dir / f"governor-{today}.jsonl"
        recent_file.write_text('{"timestamp":"t","event_type":"error","level":"info"}\n')

        deleted = logger.rotate_logs()
        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_size_rotation(self, tmp_path):
        log_dir = tmp_path / "logs"
        config = TelemetryConfig(log_max_size_mb=0.0001)  # Very small limit
        logger = StructuredLogger(log_dir, config)

        # Write enough to trigger rotation
        for _ in range(50):
            logger.write(self._make_event())

        files = logger.list_log_files()
        assert len(files) >= 2  # At least one rotation

    def test_list_log_files_sorted(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "governor-20250301.jsonl").write_text("")
        (log_dir / "governor-20250101.jsonl").write_text("")
        (log_dir / "governor-20250201.jsonl").write_text("")
        logger = StructuredLogger(log_dir)
        files = logger.list_log_files()
        names = [f.name for f in files]
        assert names == ["governor-20250101.jsonl", "governor-20250201.jsonl", "governor-20250301.jsonl"]

    def test_stats(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event(TelemetryEventType.PROPOSAL, ts="2025-01-01T00:00:00Z"))
        logger.write(self._make_event(TelemetryEventType.ERROR, TelemetryLevel.ERROR, ts="2025-01-02T00:00:00Z"))
        stats = logger.stats()
        assert stats.total_events == 2
        assert stats.by_type.get("proposal") == 1
        assert stats.by_type.get("error") == 1
        assert stats.by_level.get("info") == 1
        assert stats.by_level.get("error") == 1
        assert stats.oldest == "2025-01-01T00:00:00Z"
        assert stats.newest == "2025-01-02T00:00:00Z"

    def test_min_level_filtering(self, tmp_path):
        config = TelemetryConfig(min_level="warn")
        logger = StructuredLogger(tmp_path / "logs", config)
        logger.write(self._make_event(level=TelemetryLevel.DEBUG))
        logger.write(self._make_event(level=TelemetryLevel.INFO))
        logger.write(self._make_event(level=TelemetryLevel.WARN))
        logger.write(self._make_event(level=TelemetryLevel.ERROR))
        events = logger.read_events()
        assert len(events) == 2  # only WARN and ERROR written

    def test_empty_log_dir(self, tmp_path):
        logger = StructuredLogger(tmp_path / "nonexistent_logs")
        # list_log_files creates dir on init
        events = logger.read_events()
        assert events == []

    def test_read_with_until(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        logger.write(self._make_event(ts="2025-01-01T00:00:00Z"))
        logger.write(self._make_event(ts="2025-06-01T00:00:00Z"))
        logger.write(self._make_event(ts="2025-12-01T00:00:00Z"))
        events = logger.read_events(until="2025-06-01T00:00:00Z")
        assert len(events) == 2


# =============================================================================
# TestTelemetryCollector
# =============================================================================


class _InMemoryBackend(TelemetryBackend):
    """Test backend that records events in memory."""

    def __init__(self):
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class _FailingBackend(TelemetryBackend):
    """Backend that always raises."""

    def record(self, event: TelemetryEvent) -> None:
        raise RuntimeError("Backend failure")


class TestTelemetryCollector:
    """Tests for TelemetryCollector."""

    def test_creation_enabled(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        config = TelemetryConfig(logging_enabled=True)
        c = TelemetryCollector(config=config, gov_dir=gov_dir)
        assert len(c.backends) == 1

    def test_creation_disabled(self):
        config = TelemetryConfig(logging_enabled=False)
        c = TelemetryCollector(config=config)
        assert len(c.backends) == 0

    def test_record_proposal(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_proposal(proposal_id="p1", claim_count=3, outcome="verified")
        assert len(backend.events) == 1
        assert backend.events[0].event_type == TelemetryEventType.PROPOSAL
        assert backend.events[0].fields["proposal_id"] == "p1"

    def test_record_verification(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_verification(proposal_id="p1", success=True, duration_ms=50.0)
        assert backend.events[0].event_type == TelemetryEventType.VERIFICATION
        assert backend.events[0].level == TelemetryLevel.INFO  # success

    def test_record_verification_failure_is_warn(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_verification(proposal_id="p1", success=False, error="bad claim")
        assert backend.events[0].level == TelemetryLevel.WARN

    def test_record_llm_call(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_llm_call(model="gpt-4", input_tokens=100, cost_usd=0.01)
        assert backend.events[0].event_type == TelemetryEventType.LLM_CALL
        assert backend.events[0].fields["model"] == "gpt-4"

    def test_record_autonomous_iteration(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_autonomous_iteration(session_id="s1", iteration=5, step_success=True, done=True)
        assert backend.events[0].fields["iteration"] == 5
        assert backend.events[0].fields["done"] is True

    def test_record_error(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        c.record_error(error_type="ValueError", message="bad", module="claims")
        assert backend.events[0].event_type == TelemetryEventType.ERROR
        assert backend.events[0].level == TelemetryLevel.ERROR

    def test_record_error_from_exception(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        try:
            raise ValueError("test error")
        except ValueError as e:
            c.record_error(exc=e)
        assert backend.events[0].fields["error_type"] == "ValueError"
        assert "test error" in backend.events[0].fields["message"]
        assert backend.events[0].fields["traceback"] != ""

    def test_multi_backend(self):
        b1 = _InMemoryBackend()
        b2 = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(b1)
        c.add_backend(b2)
        c.record_proposal(proposal_id="p1")
        assert len(b1.events) == 1
        assert len(b2.events) == 1

    def test_failure_swallowed(self):
        failing = _FailingBackend()
        good = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(failing)
        c.add_backend(good)
        c.record_proposal(proposal_id="p1")  # Should not raise
        assert len(good.events) == 1

    def test_event_count(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        c.add_backend(backend)
        assert c.event_count == 0
        c.record_proposal(proposal_id="p1")
        c.record_proposal(proposal_id="p2")
        assert c.event_count == 2

    def test_redaction_file_contents(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False, redact_file_contents=True))
        c.add_backend(backend)
        # Manually test the redaction method
        fields = {"file_contents": "secret data", "other": "ok"}
        result = c._redact_fields(fields)
        assert result["file_contents"] == "[REDACTED]"
        assert result["other"] == "ok"

    def test_redaction_prompts(self):
        backend = _InMemoryBackend()
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False, redact_prompts=True))
        c.add_backend(backend)
        fields = {"prompt": "secret prompt", "prompt_hash": "abc123"}
        result = c._redact_fields(fields)
        assert result["prompt"] == "[REDACTED]"
        assert result["prompt_hash"] == "abc123"  # hash preserved

    def test_no_backends_is_noop(self):
        c = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        # Should not raise
        c.record_proposal(proposal_id="p1")
        c.record_verification(proposal_id="p1")
        c.record_llm_call()
        c.record_autonomous_iteration()
        c.record_error()
        assert c.event_count == 5


# =============================================================================
# TestAnalyzeCosts
# =============================================================================


class TestAnalyzeCosts:
    """Tests for analyze_costs."""

    def _llm_event(self, model="gpt-4", cost=0.01, operation="generate", input_t=100, output_t=50, ts=None):
        return TelemetryEvent(
            timestamp=ts or "2025-06-01T00:00:00Z",
            event_type=TelemetryEventType.LLM_CALL,
            level=TelemetryLevel.INFO,
            fields=LLMCallFields(
                model=model, cost_usd=cost, operation=operation,
                input_tokens=input_t, output_tokens=output_t,
            ).to_dict(),
        )

    def test_empty(self):
        r = analyze_costs([])
        assert r.total_cost_usd == 0.0
        assert r.total_calls == 0

    def test_single_model(self):
        events = [self._llm_event(cost=0.05)]
        r = analyze_costs(events)
        assert r.total_cost_usd == pytest.approx(0.05)
        assert r.total_calls == 1
        assert r.by_model["gpt-4"] == pytest.approx(0.05)

    def test_multi_model(self):
        events = [
            self._llm_event(model="gpt-4", cost=0.05),
            self._llm_event(model="claude", cost=0.03),
            self._llm_event(model="gpt-4", cost=0.02),
        ]
        r = analyze_costs(events)
        assert r.total_cost_usd == pytest.approx(0.10)
        assert r.by_model["gpt-4"] == pytest.approx(0.07)
        assert r.by_model["claude"] == pytest.approx(0.03)

    def test_operations(self):
        events = [
            self._llm_event(operation="generate", cost=0.05),
            self._llm_event(operation="verify", cost=0.02),
        ]
        r = analyze_costs(events)
        assert r.by_operation["generate"] == pytest.approx(0.05)
        assert r.by_operation["verify"] == pytest.approx(0.02)

    def test_since_filter(self):
        events = [
            self._llm_event(cost=0.01, ts="2025-01-01T00:00:00Z"),
            self._llm_event(cost=0.05, ts="2025-06-01T00:00:00Z"),
        ]
        r = analyze_costs(events, since="2025-05-01T00:00:00Z")
        assert r.total_cost_usd == pytest.approx(0.05)
        assert r.total_calls == 1

    def test_non_llm_ignored(self):
        events = [
            self._llm_event(cost=0.05),
            TelemetryEvent(
                timestamp="2025-01-01T00:00:00Z",
                event_type=TelemetryEventType.PROPOSAL,
                level=TelemetryLevel.INFO,
            ),
        ]
        r = analyze_costs(events)
        assert r.total_calls == 1

    def test_token_totals(self):
        events = [
            self._llm_event(input_t=100, output_t=50),
            self._llm_event(input_t=200, output_t=100),
        ]
        r = analyze_costs(events)
        assert r.total_input_tokens == 300
        assert r.total_output_tokens == 150


# =============================================================================
# TestAnalyzePerformance
# =============================================================================


class TestAnalyzePerformance:
    """Tests for analyze_performance."""

    def test_empty(self):
        r = analyze_performance([])
        assert r.total_proposals == 0
        assert r.verification_latency_p50 == 0.0

    def test_percentiles(self):
        events = []
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            events.append(TelemetryEvent(
                timestamp="2025-01-01T00:00:00Z",
                event_type=TelemetryEventType.VERIFICATION,
                level=TelemetryLevel.INFO,
                duration_ms=float(ms),
            ))
        r = analyze_performance(events)
        assert r.verification_latency_p50 == 50.0
        assert r.verification_latency_p95 >= 90.0

    def test_approval_rate(self):
        events = [
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "verified", "claim_count": 2}),
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "verified", "claim_count": 3}),
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "rejected", "claim_count": 1}),
        ]
        r = analyze_performance(events)
        assert r.total_proposals == 3
        assert r.total_verified == 2
        assert r.total_rejected == 1
        assert r.approval_rate == pytest.approx(2 / 3)

    def test_avg_claims(self):
        events = [
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "verified", "claim_count": 4}),
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "applied", "claim_count": 6}),
        ]
        r = analyze_performance(events)
        assert r.avg_claims_per_proposal == pytest.approx(5.0)

    def test_mixed_types(self):
        events = [
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "verified"}),
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.ERROR, level=TelemetryLevel.ERROR),
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.VERIFICATION, level=TelemetryLevel.INFO,
                           duration_ms=42.0),
        ]
        r = analyze_performance(events)
        assert r.total_proposals == 1
        assert r.verification_latency_p50 == 42.0

    def test_applied_counts_as_verified(self):
        events = [
            TelemetryEvent(timestamp="t", event_type=TelemetryEventType.PROPOSAL, level=TelemetryLevel.INFO,
                           fields={"outcome": "applied"}),
        ]
        r = analyze_performance(events)
        assert r.total_verified == 1


# =============================================================================
# TestExportEvents
# =============================================================================


class TestExportEvents:
    """Tests for export_events."""

    def _events(self):
        return [
            TelemetryEvent(
                timestamp="2025-01-01T00:00:00Z",
                event_type=TelemetryEventType.PROPOSAL,
                level=TelemetryLevel.INFO,
                event_id="e1",
                fields={"proposal_id": "p1", "claim_count": 2},
            ),
            TelemetryEvent(
                timestamp="2025-01-02T00:00:00Z",
                event_type=TelemetryEventType.LLM_CALL,
                level=TelemetryLevel.INFO,
                event_id="e2",
                fields={"model": "gpt-4", "cost_usd": 0.01},
            ),
        ]

    def test_export_json(self, tmp_path):
        out = tmp_path / "export.json"
        count = export_events(self._events(), out, fmt="json")
        assert count == 2
        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["event_id"] == "e1"

    def test_export_csv(self, tmp_path):
        out = tmp_path / "export.csv"
        count = export_events(self._events(), out, fmt="csv")
        assert count == 2
        content = out.read_text()
        assert "timestamp" in content
        assert "fields.proposal_id" in content

    def test_export_empty(self, tmp_path):
        out = tmp_path / "empty.json"
        count = export_events([], out, fmt="json")
        assert count == 0
        data = json.loads(out.read_text())
        assert data == []

    def test_export_empty_csv(self, tmp_path):
        out = tmp_path / "empty.csv"
        count = export_events([], out, fmt="csv")
        assert count == 0

    def test_export_with_list_fields(self, tmp_path):
        events = [TelemetryEvent(
            timestamp="t", event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO, event_id="e1",
            fields={"claim_types": ["file_exists", "tests_pass"]},
        )]
        out = tmp_path / "export.csv"
        count = export_events(events, out, fmt="csv")
        assert count == 1
        content = out.read_text()
        assert "file_exists" in content


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:
    """Tests for convenience functions."""

    def test_get_collector_no_dir(self):
        c = get_collector(None)
        assert len(c.backends) == 0
        assert c.event_count == 0

    def test_get_collector_with_dir(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        config = TelemetryConfig(logging_enabled=True)
        config.save(gov_dir)
        c = get_collector(gov_dir)
        assert len(c.backends) == 1

    def test_get_logger(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        logger = get_logger(gov_dir)
        assert isinstance(logger, StructuredLogger)

    def test_hash_prompt(self):
        h1 = hash_prompt("hello world")
        h2 = hash_prompt("hello world")
        h3 = hash_prompt("different")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16


# =============================================================================
# TestEdgeCases
# =============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_corrupt_config(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "telemetry.json").write_text("{bad json")
        c = TelemetryConfig.load(gov_dir)
        assert c.logging_enabled is True  # defaults

    def test_empty_logs_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        logger = StructuredLogger(log_dir)
        stats = logger.stats()
        assert stats.total_events == 0

    def test_large_fields(self, tmp_path):
        logger = StructuredLogger(tmp_path / "logs")
        ev = TelemetryEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO,
            fields={"big": "x" * 10000},
        )
        logger.write(ev)
        events = logger.read_events()
        assert len(events) == 1
        assert len(events[0].fields["big"]) == 10000

    def test_no_log_dir_on_read(self, tmp_path):
        logger = StructuredLogger(tmp_path / "nonexistent")
        # list_log_files handles missing dir gracefully since __init__ creates it
        files = logger.list_log_files()
        assert isinstance(files, list)


# =============================================================================
# TestPercentile
# =============================================================================


class TestPercentile:
    """Tests for the _percentile helper."""

    def test_empty(self):
        assert _percentile([], 0.5) == 0.0

    def test_single(self):
        assert _percentile([42.0], 0.5) == 42.0

    def test_p50(self):
        assert _percentile([10, 20, 30, 40, 50], 0.5) == 30

    def test_p99(self):
        vals = list(range(1, 101))
        assert _percentile(vals, 0.99) == 99


# =============================================================================
# TestReportDataclasses
# =============================================================================


class TestReportDataclasses:
    """Tests for report dataclasses."""

    def test_cost_report_to_dict(self):
        r = CostReport(total_cost_usd=1.5, total_calls=10, by_model={"gpt-4": 1.0})
        d = r.to_dict()
        assert d["total_cost_usd"] == 1.5
        assert d["by_model"]["gpt-4"] == 1.0

    def test_performance_report_to_dict(self):
        r = PerformanceReport(approval_rate=0.8, total_proposals=5)
        d = r.to_dict()
        assert d["approval_rate"] == 0.8

    def test_log_stats_to_dict(self):
        r = LogStats(total_events=100, by_type={"proposal": 50})
        d = r.to_dict()
        assert d["total_events"] == 100


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:
    """Tests for telemetry enums."""

    def test_event_type_values(self):
        assert TelemetryEventType.PROPOSAL.value == "proposal"
        assert TelemetryEventType.LLM_CALL.value == "llm_call"
        assert TelemetryEventType.AUTONOMOUS_ITERATION.value == "autonomous_iteration"

    def test_level_values(self):
        assert TelemetryLevel.DEBUG.value == "debug"
        assert TelemetryLevel.ERROR.value == "error"

    def test_level_order(self):
        assert LEVEL_ORDER[TelemetryLevel.DEBUG] < LEVEL_ORDER[TelemetryLevel.INFO]
        assert LEVEL_ORDER[TelemetryLevel.INFO] < LEVEL_ORDER[TelemetryLevel.WARN]
        assert LEVEL_ORDER[TelemetryLevel.WARN] < LEVEL_ORDER[TelemetryLevel.ERROR]

    def test_all_event_types_in_enum(self):
        assert len(TelemetryEventType) == 12

    def test_all_levels_in_enum(self):
        assert len(TelemetryLevel) == 4


# =============================================================================
# TestExecutorIntegration
# =============================================================================


class TestExecutorIntegration:
    """Tests for executor telemetry integration."""

    def test_executor_with_collector(self, tmp_path):
        from governor.executor import AutonomousExecutor, ExecutorConfig, StepResult
        from governor.execution import ExecutionBudget

        backend = _InMemoryBackend()
        collector = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        collector.add_backend(backend)

        executor = AutonomousExecutor(
            config=ExecutorConfig(checkpoint_interval=100),
            collector=collector,
        )

        call_count = 0

        def step_fn(state, iteration):
            nonlocal call_count
            call_count += 1
            return StepResult(success=True, message="done", done=True, tokens_used=50, cost_usd=0.001)

        state = executor.execute(
            step_fn=step_fn,
            task="test",
            budget=ExecutionBudget(max_iterations=5),
        )

        assert call_count == 1
        assert len(backend.events) == 1
        assert backend.events[0].event_type == TelemetryEventType.AUTONOMOUS_ITERATION
        assert backend.events[0].fields["step_success"] is True
        assert backend.events[0].fields["done"] is True

    def test_executor_without_collector(self, tmp_path):
        from governor.executor import AutonomousExecutor, ExecutorConfig, StepResult
        from governor.execution import ExecutionBudget

        executor = AutonomousExecutor(
            config=ExecutorConfig(checkpoint_interval=100),
        )

        def step_fn(state, iteration):
            return StepResult(success=True, done=True)

        # Should work fine without collector
        state = executor.execute(
            step_fn=step_fn,
            task="test",
            budget=ExecutionBudget(max_iterations=5),
        )
        assert state.status.value == "completed"
