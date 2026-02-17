# SPDX-License-Identifier: Apache-2.0
"""Tests for dashboard_ux.py — Run-centric governance dashboard backend."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from governor.dashboard_ux import (
    BUILTIN_ACTIONS,
    BUILTIN_TEMPLATES,
    CANCEL_ACK_TIMEOUT_MS,
    CANCEL_TERM_TIMEOUT_MS,
    CancelRequest,
    ControlField,
    ControlRender,
    DashboardStore,
    DashboardSummary,
    ReportSection,
    RunReport,
    RunState,
    RunSummary,
    RunTemplate,
    RunVerdict,
    StreamEvent,
    StreamEventType,
    UIAction,
    build_controls_schema,
    generate_report,
    make_dashboard_event,
    make_heartbeat,
    make_progress,
)


# ===========================================================================
# Enum tests
# ===========================================================================

class TestEnums:
    """Tests for all enums."""

    def test_stream_event_type_values(self):
        assert StreamEventType.RUN_STARTED.value == "run_started"
        assert StreamEventType.HEARTBEAT.value == "heartbeat"
        assert len(StreamEventType) == 9

    def test_run_verdict_values(self):
        assert RunVerdict.PASS.value == "pass"
        assert RunVerdict.FAIL.value == "fail"
        assert RunVerdict.CANCELLED.value == "cancelled"
        assert RunVerdict.ERROR.value == "error"
        assert RunVerdict.PENDING.value == "pending"
        assert len(RunVerdict) == 5

    def test_run_state_values(self):
        assert RunState.CREATED.value == "created"
        assert RunState.RUNNING.value == "running"
        assert RunState.CANCELLING.value == "cancelling"
        assert RunState.COMPLETED.value == "completed"
        assert len(RunState) == 7

    def test_control_render_values(self):
        assert ControlRender.DROPDOWN.value == "dropdown"
        assert ControlRender.TEXTAREA.value == "textarea"
        assert ControlRender.TAG_INPUT.value == "tag-input"
        assert len(ControlRender) == 6


# ===========================================================================
# CancelRequest tests
# ===========================================================================

class TestCancelRequest:
    """Tests for cancellation contract."""

    def test_creation(self):
        cr = CancelRequest(run_id="run-1")
        assert cr.run_id == "run-1"
        assert cr.requested_at
        assert cr.acknowledged_at is None
        assert cr.terminated_at is None
        assert cr.escalated is False

    def test_acknowledge(self):
        cr = CancelRequest(run_id="run-1")
        cr.acknowledge()
        assert cr.acknowledged_at is not None

    def test_terminate(self):
        cr = CancelRequest(run_id="run-1")
        cr.terminate()
        assert cr.terminated_at is not None

    def test_not_timed_out_initially(self):
        cr = CancelRequest(run_id="run-1")
        assert cr.is_timed_out() is False

    def test_not_timed_out_after_termination(self):
        cr = CancelRequest(run_id="run-1")
        cr.terminate()
        assert cr.is_timed_out() is False

    def test_timed_out_after_timeout(self):
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
        cr = CancelRequest(run_id="run-1", requested_at=old_time)
        assert cr.is_timed_out() is True

    def test_to_dict(self):
        cr = CancelRequest(run_id="run-1")
        cr.acknowledge()
        d = cr.to_dict()
        assert d["run_id"] == "run-1"
        assert d["acknowledged_at"] is not None
        assert d["escalated"] is False

    def test_cancel_timeouts(self):
        assert CANCEL_ACK_TIMEOUT_MS == 2000
        assert CANCEL_TERM_TIMEOUT_MS == 10000


# ===========================================================================
# StreamEvent tests
# ===========================================================================

class TestStreamEvent:
    """Tests for SSE streaming events."""

    def test_creation(self):
        e = StreamEvent(
            event_type=StreamEventType.RUN_STARTED,
            data={"run_id": "r1", "manifest": {}},
        )
        assert e.event_type == StreamEventType.RUN_STARTED
        assert e.event_id  # Auto-generated
        assert e.ts

    def test_to_sse(self):
        e = StreamEvent(
            event_type=StreamEventType.EVENT,
            data={"kind": "tool_invocation"},
            event_id="evt-1",
        )
        sse = e.to_sse()
        assert "id: evt-1" in sse
        assert "event: event" in sse
        assert "data:" in sse
        assert "tool_invocation" in sse

    def test_to_dict(self):
        e = StreamEvent(
            event_type=StreamEventType.CLAIM,
            data={"claim_id": "c1", "type": "test_result"},
        )
        d = e.to_dict()
        assert d["event_type"] == "claim"
        assert d["data"]["claim_id"] == "c1"

    def test_heartbeat(self):
        hb = make_heartbeat()
        assert hb.event_type == StreamEventType.HEARTBEAT
        assert "ts" in hb.data

    def test_progress(self):
        p = make_progress("r1", event_count=42, elapsed_ms=1234.5, stage="verify")
        assert p.event_type == StreamEventType.PROGRESS
        assert p.data["run_id"] == "r1"
        assert p.data["event_count"] == 42
        assert p.data["elapsed_ms"] == 1234.5
        assert p.data["stage"] == "verify"

    def test_all_event_types_sseable(self):
        for et in StreamEventType:
            e = StreamEvent(event_type=et, data={})
            sse = e.to_sse()
            assert f"event: {et.value}" in sse


# ===========================================================================
# RunTemplate tests
# ===========================================================================

class TestRunTemplate:
    """Tests for run templates."""

    def test_creation(self):
        t = RunTemplate(name="test", description="Test template")
        assert t.name == "test"
        assert t.manifest_defaults == {}

    def test_to_dict(self):
        t = RunTemplate(
            name="smoke",
            description="Smoke test",
            manifest_defaults={"profile": "strict"},
            example_task="Run tests",
            expected_outcome="All pass",
        )
        d = t.to_dict()
        assert d["name"] == "smoke"
        assert d["manifest_defaults"]["profile"] == "strict"

    def test_from_dict(self):
        d = {
            "name": "test",
            "description": "desc",
            "manifest_defaults": {"k": "v"},
            "example_task": "task",
            "expected_outcome": "ok",
            "last_successful_run_id": "r1",
        }
        t = RunTemplate.from_dict(d)
        assert t.name == "test"
        assert t.last_successful_run_id == "r1"

    def test_roundtrip(self):
        t = RunTemplate(
            name="rt", description="round trip",
            manifest_defaults={"profile": "strict"},
        )
        restored = RunTemplate.from_dict(t.to_dict())
        assert restored.name == t.name

    def test_builtin_templates(self):
        assert len(BUILTIN_TEMPLATES) == 3
        names = {t.name for t in BUILTIN_TEMPLATES}
        assert "smoke_test" in names
        assert "security_scan" in names
        assert "interferometry" in names


# ===========================================================================
# Controls schema tests
# ===========================================================================

class TestControlsSchema:
    """Tests for the controls schema builder."""

    def test_build_schema(self):
        schema = build_controls_schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "x-actions" in schema

    def test_schema_has_required_fields(self):
        schema = build_controls_schema()
        props = schema["properties"]
        assert "profile" in props
        assert "backend" in props
        assert "task" in props
        assert "scope" in props
        assert "seed" in props

    def test_profile_field(self):
        schema = build_controls_schema()
        profile = schema["properties"]["profile"]
        assert profile["x-render"] == "dropdown"
        assert "greenfield" in profile["enum"]
        assert profile["default"] == "established"

    def test_backend_field_dynamic(self):
        schema = build_controls_schema()
        backend = schema["properties"]["backend"]
        assert backend["x-dynamic"] == "/v1/backends"

    def test_seed_is_advanced(self):
        schema = build_controls_schema()
        seed = schema["properties"]["seed"]
        assert seed.get("x-advanced") is True

    def test_actions(self):
        schema = build_controls_schema()
        actions = schema["x-actions"]
        assert "start" in actions
        assert "cancel" in actions
        assert "rerun" in actions
        assert "compare" in actions

    def test_control_field_to_schema(self):
        f = ControlField(
            name="test",
            field_type="string",
            render=ControlRender.DROPDOWN,
            label="Test",
            description="Test field",
            enum_values=["a", "b"],
            default="a",
        )
        s = f.to_schema()
        assert s["type"] == "string"
        assert s["x-render"] == "dropdown"
        assert s["x-label"] == "Test"
        assert s["enum"] == ["a", "b"]


# ===========================================================================
# UIAction tests
# ===========================================================================

class TestUIAction:
    """Tests for UI actions."""

    def test_to_dict(self):
        a = UIAction(
            name="start", method="POST", endpoint="/v2/runs",
            precondition="no active run", feedback="show progress",
        )
        d = a.to_dict()
        assert d["name"] == "start"
        assert d["method"] == "POST"
        assert d["endpoint"] == "/v2/runs"

    def test_builtin_actions(self):
        assert len(BUILTIN_ACTIONS) == 4
        names = {a.name for a in BUILTIN_ACTIONS}
        assert names == {"start", "cancel", "rerun", "compare"}


# ===========================================================================
# RunSummary tests
# ===========================================================================

class TestRunSummary:
    """Tests for run summaries."""

    def test_creation(self):
        s = RunSummary(
            run_id="r1", created_at="2025-01-01",
            model="llama3", profile="strict",
            verdict=RunVerdict.PASS,
        )
        assert s.run_id == "r1"
        assert s.verdict == RunVerdict.PASS
        assert s.claim_count == 0

    def test_to_dict(self):
        s = RunSummary(
            run_id="r1", created_at="2025-01-01",
            model="m", profile="p", verdict=RunVerdict.FAIL,
            claim_count=5, violation_count=2, duration_ms=1234.567,
        )
        d = s.to_dict()
        assert d["verdict"] == "fail"
        assert d["claim_count"] == 5
        assert d["duration_ms"] == 1234.6

    def test_from_dict(self):
        d = {
            "run_id": "r1", "created_at": "x",
            "model": "m", "profile": "p",
            "verdict": "pass", "claim_count": 3,
        }
        s = RunSummary.from_dict(d)
        assert s.verdict == RunVerdict.PASS
        assert s.claim_count == 3

    def test_roundtrip(self):
        s = RunSummary(
            run_id="r1", created_at="x",
            model="m", profile="p",
            verdict=RunVerdict.CANCELLED,
        )
        restored = RunSummary.from_dict(s.to_dict())
        assert restored.verdict == RunVerdict.CANCELLED


# ===========================================================================
# DashboardSummary tests
# ===========================================================================

class TestDashboardSummary:
    """Tests for aggregate dashboard stats."""

    def test_creation(self):
        ds = DashboardSummary(total_runs=10, passed=7, failed=2, cancelled=1)
        assert ds.pass_rate == 0.0

    def test_to_dict(self):
        ds = DashboardSummary(
            total_runs=100, passed=80, failed=15, cancelled=5,
            pass_rate=0.8, total_claims=500, total_violations=30,
        )
        d = ds.to_dict()
        assert d["total_runs"] == 100
        assert d["pass_rate"] == 0.8
        assert d["active_run"] is None


# ===========================================================================
# Report generation tests
# ===========================================================================

class TestReportGeneration:
    """Tests for post-hoc report generation."""

    def test_empty_report(self):
        r = generate_report("run-1")
        assert r.run_id == "run-1"
        assert r.verdict == "pending"
        assert len(r.sections) == 4
        assert r.manifest_hash

    def test_passing_report(self):
        r = generate_report(
            "run-1",
            manifest={"profile": "strict", "model": "llama3"},
            events=[{"kind": "tool_invocation"}, {"kind": "test_run"}],
            claims=[{"type": "test_result", "subject": "pytest", "predicate": "passed"}],
        )
        assert r.verdict == "pass"
        assert len(r.sections) == 4

    def test_failing_report(self):
        r = generate_report(
            "run-1",
            events=[{"kind": "tool_invocation"}],
            violations=[{"severity": "blocking", "summary": "Secret detected"}],
        )
        assert r.verdict == "fail"

    def test_report_to_dict(self):
        r = generate_report("run-1")
        d = r.to_dict()
        assert d["run_id"] == "run-1"
        assert "sections" in d
        assert "manifest_hash" in d

    def test_report_to_markdown(self):
        r = generate_report(
            "run-1",
            manifest={"profile": "strict"},
            events=[{"kind": "event"}],
            claims=[{"type": "file_changed", "subject": "auth.py"}],
        )
        md = r.to_markdown()
        assert "# Run Report: run-1" in md
        assert "**PASS**" in md
        assert "manifest_hash" in md.lower() or "Manifest hash" in md

    def test_report_deterministic_hash(self):
        manifest = {"profile": "strict", "model": "llama3"}
        r1 = generate_report("run-1", manifest=manifest)
        r2 = generate_report("run-1", manifest=manifest)
        assert r1.manifest_hash == r2.manifest_hash

    def test_report_section(self):
        s = ReportSection(title="Test", content={"key": "value"})
        d = s.to_dict()
        assert d["title"] == "Test"
        assert d["content"]["key"] == "value"


# ===========================================================================
# DashboardStore tests
# ===========================================================================

class TestDashboardStore:
    """Tests for dashboard persistence."""

    def test_record_run(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        summary = RunSummary(
            run_id="r1", created_at="2025-01-01",
            model="llama3", profile="strict",
            verdict=RunVerdict.PASS, claim_count=5,
        )
        store.record_run(summary)
        assert store.summaries_path.exists()

    def test_list_runs(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        for i in range(3):
            store.record_run(RunSummary(
                run_id=f"r{i}", created_at=f"2025-01-0{i+1}",
                model="m", profile="strict",
                verdict=RunVerdict.PASS,
            ))
        runs = store.list_runs()
        assert len(runs) == 3

    def test_list_runs_with_filter(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        store.record_run(RunSummary(
            run_id="r1", created_at="x",
            model="m", profile="strict",
            verdict=RunVerdict.PASS,
        ))
        store.record_run(RunSummary(
            run_id="r2", created_at="x",
            model="m", profile="research",
            verdict=RunVerdict.FAIL,
        ))

        strict_runs = store.list_runs(profile="strict")
        assert len(strict_runs) == 1
        assert strict_runs[0].run_id == "r1"

        failed_runs = store.list_runs(verdict="fail")
        assert len(failed_runs) == 1
        assert failed_runs[0].run_id == "r2"

    def test_list_runs_limit(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        for i in range(10):
            store.record_run(RunSummary(
                run_id=f"r{i}", created_at="x",
                model="m", profile="p",
                verdict=RunVerdict.PASS,
            ))
        runs = store.list_runs(limit=3)
        assert len(runs) == 3

    def test_get_run(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        store.record_run(RunSummary(
            run_id="r1", created_at="x",
            model="m", profile="p",
            verdict=RunVerdict.PASS,
        ))
        r = store.get_run("r1")
        assert r is not None
        assert r.verdict == RunVerdict.PASS

    def test_get_run_missing(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        assert store.get_run("nope") is None

    def test_dashboard_summary(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        store.record_run(RunSummary(
            run_id="r1", created_at="x", model="m", profile="p",
            verdict=RunVerdict.PASS, claim_count=5, violation_count=0,
        ))
        store.record_run(RunSummary(
            run_id="r2", created_at="x", model="m", profile="p",
            verdict=RunVerdict.FAIL, claim_count=3, violation_count=2,
        ))
        store.record_run(RunSummary(
            run_id="r3", created_at="x", model="m", profile="p",
            verdict=RunVerdict.CANCELLED, claim_count=1, violation_count=0,
        ))

        ds = store.dashboard_summary()
        assert ds.total_runs == 3
        assert ds.passed == 1
        assert ds.failed == 1
        assert ds.cancelled == 1
        assert abs(ds.pass_rate - 1/3) < 0.01
        assert ds.total_claims == 9
        assert ds.total_violations == 2

    def test_dashboard_summary_empty(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        ds = store.dashboard_summary()
        assert ds.total_runs == 0
        assert ds.pass_rate == 0.0

    def test_save_report(self, tmp_path: Path):
        store = DashboardStore(tmp_path)
        report = generate_report("run-1", manifest={"profile": "strict"})
        path = store.save_report(report)
        assert path.exists()
        # Also saves markdown
        md_path = path.with_suffix(".md")
        assert md_path.exists()


# ===========================================================================
# Telemetry event tests
# ===========================================================================

class TestMakeDashboardEvent:
    """Tests for telemetry event creation."""

    def test_basic_event(self):
        e = make_dashboard_event("run_started", run_id="r1")
        assert e["type"] == "dashboard_ux"
        assert e["action"] == "run_started"
        assert e["run_id"] == "r1"
        assert e["ts"]

    def test_event_with_details(self):
        e = make_dashboard_event("cancel", run_id="r1", details={"reason": "timeout"})
        assert e["details"]["reason"] == "timeout"


# ===========================================================================
# Golden-file schema tests
# ===========================================================================

class TestGoldenSchemas:
    """Tests that serialized schemas remain stable."""

    def test_stream_event_schema(self):
        e = StreamEvent(event_type=StreamEventType.EVENT, data={})
        d = e.to_dict()
        assert set(d.keys()) == {"event_type", "event_id", "ts", "data"}

    def test_run_template_schema(self):
        t = RunTemplate(name="t", description="d")
        d = t.to_dict()
        expected = {"name", "description", "manifest_defaults", "example_task",
                     "expected_outcome", "last_successful_run_id"}
        assert set(d.keys()) == expected

    def test_run_summary_schema(self):
        s = RunSummary(run_id="r", created_at="x", model="m", profile="p", verdict=RunVerdict.PASS)
        d = s.to_dict()
        expected = {"run_id", "created_at", "model", "profile", "verdict",
                     "claim_count", "violation_count", "duration_ms", "task"}
        assert set(d.keys()) == expected

    def test_dashboard_summary_schema(self):
        ds = DashboardSummary()
        d = ds.to_dict()
        expected = {"total_runs", "passed", "failed", "cancelled", "pass_rate",
                     "total_claims", "total_violations", "active_run"}
        assert set(d.keys()) == expected

    def test_cancel_request_schema(self):
        cr = CancelRequest(run_id="r")
        d = cr.to_dict()
        expected = {"run_id", "requested_at", "acknowledged_at", "terminated_at", "escalated"}
        assert set(d.keys()) == expected

    def test_run_report_schema(self):
        r = RunReport(run_id="r")
        d = r.to_dict()
        expected = {"run_id", "generated_at", "verdict", "sections", "manifest_hash"}
        assert set(d.keys()) == expected

    def test_ui_action_schema(self):
        a = BUILTIN_ACTIONS[0]
        d = a.to_dict()
        expected = {"name", "method", "endpoint", "precondition", "feedback"}
        assert set(d.keys()) == expected

    def test_controls_schema_structure(self):
        s = build_controls_schema()
        assert "$schema" in s
        assert "type" in s
        assert "properties" in s
        assert "x-actions" in s

    def test_dashboard_event_schema(self):
        e = make_dashboard_event("test")
        expected = {"type", "action", "run_id", "details", "ts"}
        assert set(e.keys()) == expected
