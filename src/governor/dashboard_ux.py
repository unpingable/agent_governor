# SPDX-License-Identifier: Apache-2.0
"""
Dashboard UX — Run-centric governance dashboard backend.

Backend logic for the v2 dashboard: run management, streaming event types,
controls schema, run templates, cancellation contract, report generation.

Spec: AG2_DASHBOARD_UX_SPEC.md (Layer 4, Item #11 of AG2 build order)

Design principle: UI renders governance state. UI cannot override governance
state. Profile is UX; anchors are law. All state lives in artifacts.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StreamEventType(str, Enum):
    """Stable event types for SSE streaming."""
    RUN_STARTED = "run_started"
    EVENT = "event"
    CLAIM = "claim"
    VIOLATION = "violation"
    PROGRESS = "progress"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"
    HEARTBEAT = "heartbeat"


class RunVerdict(str, Enum):
    """Verdict for a completed run."""
    PASS = "pass"
    FAIL = "fail"
    CANCELLED = "cancelled"
    ERROR = "error"
    PENDING = "pending"


class RunState(str, Enum):
    """Current state of a run."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETING = "completing"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ControlRender(str, Enum):
    """Widget render hints for controls schema."""
    DROPDOWN = "dropdown"
    TEXTAREA = "textarea"
    TAG_INPUT = "tag-input"
    NUMBER = "number"
    TOGGLE = "toggle"
    READONLY = "readonly"


# ---------------------------------------------------------------------------
# Cancel contract
# ---------------------------------------------------------------------------

CANCEL_ACK_TIMEOUT_MS = 2000
CANCEL_TERM_TIMEOUT_MS = 10000


@dataclass
class CancelRequest:
    """Cancellation request for an active run."""
    run_id: str
    requested_at: str = ""
    acknowledged_at: str | None = None
    terminated_at: str | None = None
    escalated: bool = False

    def __post_init__(self):
        if not self.requested_at:
            self.requested_at = datetime.now(timezone.utc).isoformat()

    def acknowledge(self) -> None:
        self.acknowledged_at = datetime.now(timezone.utc).isoformat()

    def terminate(self) -> None:
        self.terminated_at = datetime.now(timezone.utc).isoformat()

    def is_timed_out(self) -> bool:
        """Check if cancel has exceeded termination timeout."""
        if self.terminated_at:
            return False
        try:
            req = datetime.fromisoformat(self.requested_at)
            if req.tzinfo is None:
                req = req.replace(tzinfo=timezone.utc)
            elapsed_ms = (datetime.now(timezone.utc) - req).total_seconds() * 1000
            return elapsed_ms > CANCEL_TERM_TIMEOUT_MS
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "requested_at": self.requested_at,
            "acknowledged_at": self.acknowledged_at,
            "terminated_at": self.terminated_at,
            "escalated": self.escalated,
        }


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

@dataclass
class StreamEvent:
    """An event in the SSE stream."""
    event_type: StreamEventType
    data: dict[str, Any]
    event_id: str = ""
    ts: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = uuid.uuid4().hex[:12]
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_sse(self) -> str:
        """Format as Server-Sent Events text."""
        lines = []
        lines.append(f"id: {self.event_id}")
        lines.append(f"event: {self.event_type.value}")
        lines.append(f"data: {json.dumps(self.data)}")
        lines.append("")  # Empty line terminates the event
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "ts": self.ts,
            "data": self.data,
        }


def make_heartbeat() -> StreamEvent:
    """Create a heartbeat event."""
    return StreamEvent(
        event_type=StreamEventType.HEARTBEAT,
        data={"ts": datetime.now(timezone.utc).isoformat()},
    )


def make_progress(
    run_id: str, event_count: int, elapsed_ms: float, stage: str = ""
) -> StreamEvent:
    """Create a progress event."""
    return StreamEvent(
        event_type=StreamEventType.PROGRESS,
        data={
            "run_id": run_id,
            "event_count": event_count,
            "elapsed_ms": round(elapsed_ms, 1),
            "stage": stage,
        },
    )


# ---------------------------------------------------------------------------
# Run templates
# ---------------------------------------------------------------------------

@dataclass
class RunTemplate:
    """A known-good run template for reproducibility."""
    name: str
    description: str
    manifest_defaults: dict[str, Any] = field(default_factory=dict)
    example_task: str = ""
    expected_outcome: str = ""
    last_successful_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "manifest_defaults": self.manifest_defaults,
            "example_task": self.example_task,
            "expected_outcome": self.expected_outcome,
            "last_successful_run_id": self.last_successful_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunTemplate:
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            manifest_defaults=d.get("manifest_defaults", {}),
            example_task=d.get("example_task", ""),
            expected_outcome=d.get("expected_outcome", ""),
            last_successful_run_id=d.get("last_successful_run_id"),
        )


BUILTIN_TEMPLATES = [
    RunTemplate(
        name="smoke_test",
        description="Verify setup works: run pytest, report results.",
        manifest_defaults={"profile": "strict"},
        example_task="Run pytest, report results",
        expected_outcome="All tests pass, no violations",
    ),
    RunTemplate(
        name="security_scan",
        description="Baseline security scan of the codebase.",
        manifest_defaults={"profile": "production"},
        example_task="Scan for vulnerabilities in the codebase",
        expected_outcome="No critical findings",
    ),
    RunTemplate(
        name="interferometry",
        description="Compare model outputs for a given task.",
        manifest_defaults={"profile": "research"},
        example_task="Compare model outputs for {task}",
        expected_outcome="Divergence report with shared and unique claims",
    ),
]


# ---------------------------------------------------------------------------
# Controls schema
# ---------------------------------------------------------------------------

@dataclass
class ControlField:
    """A single control field in the controls schema."""
    name: str
    field_type: str  # "string", "integer", "array", "boolean"
    render: ControlRender
    label: str
    description: str = ""
    enum_values: list[str] = field(default_factory=list)
    default: Any = None
    dynamic_endpoint: str = ""
    advanced: bool = False

    def to_schema(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.field_type,
            "x-render": self.render.value,
            "x-label": self.label,
        }
        if self.description:
            d["x-description"] = self.description
        if self.enum_values:
            d["enum"] = self.enum_values
        if self.default is not None:
            d["default"] = self.default
        if self.dynamic_endpoint:
            d["x-dynamic"] = self.dynamic_endpoint
        if self.advanced:
            d["x-advanced"] = True
        return d


def build_controls_schema() -> dict[str, Any]:
    """Build the controls schema for the dashboard left panel."""
    fields = [
        ControlField(
            name="profile",
            field_type="string",
            render=ControlRender.DROPDOWN,
            label="Profile",
            description="Governance strictness preset. Cannot modify anchors.",
            enum_values=["greenfield", "established", "production", "hotfix", "refactor"],
            default="established",
        ),
        ControlField(
            name="backend",
            field_type="string",
            render=ControlRender.DROPDOWN,
            label="Backend",
            description="Model backend for execution.",
            dynamic_endpoint="/v1/backends",
        ),
        ControlField(
            name="task",
            field_type="string",
            render=ControlRender.TEXTAREA,
            label="Task",
            description="What to do. Becomes prompt_hash in manifest.",
        ),
        ControlField(
            name="scope",
            field_type="array",
            render=ControlRender.TAG_INPUT,
            label="File scope",
            description="Paths to include. Empty = entire repo.",
        ),
        ControlField(
            name="seed",
            field_type="integer",
            render=ControlRender.NUMBER,
            label="Seed",
            description="Optional. For reproducible runs.",
            advanced=True,
        ),
    ]

    properties = {}
    for f in fields:
        properties[f.name] = f.to_schema()

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "x-actions": ["start", "cancel", "rerun", "compare"],
    }


# ---------------------------------------------------------------------------
# UI Actions
# ---------------------------------------------------------------------------

@dataclass
class UIAction:
    """A dashboard action with defined API contract."""
    name: str
    method: str
    endpoint: str
    precondition: str
    feedback: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "endpoint": self.endpoint,
            "precondition": self.precondition,
            "feedback": self.feedback,
        }


BUILTIN_ACTIONS = [
    UIAction(
        name="start",
        method="POST",
        endpoint="/v2/runs",
        precondition="no active run",
        feedback="switch to run detail view, show progress",
    ),
    UIAction(
        name="cancel",
        method="POST",
        endpoint="/v2/runs/{run_id}/cancel",
        precondition="active run exists",
        feedback="STOP button turns to 'Cancelling...', then run shows CANCELLED verdict",
    ),
    UIAction(
        name="rerun",
        method="POST",
        endpoint="/v2/runs",
        precondition="at least one completed run",
        feedback="new run starts, previous run remains in list",
    ),
    UIAction(
        name="compare",
        method="POST",
        endpoint="/v2/runs/compare",
        precondition="at least two backends configured",
        feedback="switch to comparison view (interferometry results)",
    ),
]


# ---------------------------------------------------------------------------
# Run summary + dashboard
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    """Summary of a completed run for the dashboard list."""
    run_id: str
    created_at: str
    model: str
    profile: str
    verdict: RunVerdict
    claim_count: int = 0
    violation_count: int = 0
    duration_ms: float = 0.0
    task: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "model": self.model,
            "profile": self.profile,
            "verdict": self.verdict.value,
            "claim_count": self.claim_count,
            "violation_count": self.violation_count,
            "duration_ms": round(self.duration_ms, 1),
            "task": self.task,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunSummary:
        return cls(
            run_id=d["run_id"],
            created_at=d.get("created_at", ""),
            model=d.get("model", ""),
            profile=d.get("profile", ""),
            verdict=RunVerdict(d.get("verdict", "pending")),
            claim_count=d.get("claim_count", 0),
            violation_count=d.get("violation_count", 0),
            duration_ms=d.get("duration_ms", 0.0),
            task=d.get("task", ""),
        )


@dataclass
class DashboardSummary:
    """Aggregate dashboard statistics."""
    total_runs: int = 0
    passed: int = 0
    failed: int = 0
    cancelled: int = 0
    pass_rate: float = 0.0
    total_claims: int = 0
    total_violations: int = 0
    active_run: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "passed": self.passed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "pass_rate": round(self.pass_rate, 3),
            "total_claims": self.total_claims,
            "total_violations": self.total_violations,
            "active_run": self.active_run,
        }


# ---------------------------------------------------------------------------
# Report generation (post-hoc from events.jsonl)
# ---------------------------------------------------------------------------

@dataclass
class ReportSection:
    """A section in a run report."""
    title: str
    content: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "content": self.content}


@dataclass
class RunReport:
    """Post-hoc report generated from run artifacts."""
    run_id: str
    generated_at: str = ""
    verdict: str = ""
    sections: list[ReportSection] = field(default_factory=list)
    manifest_hash: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "sections": [s.to_dict() for s in self.sections],
            "manifest_hash": self.manifest_hash,
        }

    def to_markdown(self) -> str:
        """Render report as markdown."""
        lines: list[str] = []
        lines.append(f"# Run Report: {self.run_id}")
        lines.append(f"\nVerdict: **{self.verdict.upper()}**")
        lines.append(f"Generated: {self.generated_at}")
        if self.manifest_hash:
            lines.append(f"Manifest hash: `{self.manifest_hash}`")
        lines.append("")

        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            if isinstance(section.content, dict):
                for k, v in section.content.items():
                    lines.append(f"- **{k}**: {v}")
            lines.append("")

        lines.append("---")
        lines.append(f"*Report generated from events.jsonl. "
                      f"Hash: {self.manifest_hash}*")
        return "\n".join(lines)


def generate_report(
    run_id: str,
    manifest: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    claims: list[dict[str, Any]] | None = None,
    violations: list[dict[str, Any]] | None = None,
) -> RunReport:
    """Generate a post-hoc report from run artifacts.

    Reports consume events.jsonl — they never drive execution.
    """
    manifest = manifest or {}
    events = events or []
    claims = claims or []
    violations = violations or []

    # Compute manifest hash
    manifest_json = json.dumps(manifest, sort_keys=True)
    manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()[:16]

    # Verdict
    if violations:
        verdict = "fail"
    elif not events:
        verdict = "pending"
    else:
        verdict = "pass"

    sections: list[ReportSection] = []

    # Section 1: Run Summary
    sections.append(ReportSection(
        title="Run Summary",
        content={
            "run_id": run_id,
            "profile": manifest.get("profile", "unknown"),
            "model": manifest.get("model", "unknown"),
            "event_count": len(events),
            "claim_count": len(claims),
            "violation_count": len(violations),
            "verdict": verdict,
        },
    ))

    # Section 2: Claims & Evidence
    claim_summary: dict[str, Any] = {}
    for i, c in enumerate(claims):
        key = c.get("type", f"claim_{i}")
        claim_summary[key] = c.get("subject", c.get("predicate", ""))
    sections.append(ReportSection(
        title="Claims & Evidence",
        content=claim_summary if claim_summary else {"status": "No claims extracted"},
    ))

    # Section 3: Violations
    violation_summary: dict[str, Any] = {}
    for i, v in enumerate(violations):
        key = f"violation_{i}"
        violation_summary[key] = v.get("summary", v.get("message", str(v)))
    sections.append(ReportSection(
        title="Violations",
        content=violation_summary if violation_summary else {"status": "No violations detected"},
    ))

    # Section 4: Reproducibility
    sections.append(ReportSection(
        title="Reproducibility",
        content={
            "manifest_hash": manifest_hash,
            "repro_command": f"governor instrument replay {run_id}",
        },
    ))

    return RunReport(
        run_id=run_id,
        verdict=verdict,
        sections=sections,
        manifest_hash=manifest_hash,
    )


# ---------------------------------------------------------------------------
# Run store (lightweight — wraps instrument system)
# ---------------------------------------------------------------------------

class DashboardStore:
    """Lightweight run store for dashboard summaries.

    Wraps the instrument system's run store with dashboard-specific
    aggregation and filtering.
    """

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.dashboard_dir = self.governor_dir / "dashboard"
        self.summaries_path = self.dashboard_dir / "summaries.json"

    def _ensure_dirs(self) -> None:
        self.dashboard_dir.mkdir(parents=True, exist_ok=True)

    def _load_summaries(self) -> list[dict[str, Any]]:
        if not self.summaries_path.exists():
            return []
        try:
            return json.loads(self.summaries_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_summaries(self, summaries: list[dict[str, Any]]) -> None:
        self._ensure_dirs()
        self.summaries_path.write_text(json.dumps(summaries, indent=2) + "\n")

    def record_run(self, summary: RunSummary) -> None:
        """Record a run summary."""
        summaries = self._load_summaries()
        summaries.append(summary.to_dict())
        self._save_summaries(summaries)

    def list_runs(
        self,
        profile: str = "",
        verdict: str = "",
        limit: int = 50,
    ) -> list[RunSummary]:
        """List run summaries with optional filters."""
        summaries = self._load_summaries()

        if profile:
            summaries = [s for s in summaries if s.get("profile") == profile]
        if verdict:
            summaries = [s for s in summaries if s.get("verdict") == verdict]

        # Most recent first
        summaries.reverse()
        summaries = summaries[:limit]

        return [RunSummary.from_dict(s) for s in summaries]

    def get_run(self, run_id: str) -> RunSummary | None:
        """Get a specific run summary."""
        summaries = self._load_summaries()
        for s in summaries:
            if s["run_id"] == run_id:
                return RunSummary.from_dict(s)
        return None

    def dashboard_summary(self) -> DashboardSummary:
        """Compute aggregate dashboard statistics."""
        summaries = self._load_summaries()
        total = len(summaries)
        passed = sum(1 for s in summaries if s.get("verdict") == "pass")
        failed = sum(1 for s in summaries if s.get("verdict") == "fail")
        cancelled = sum(1 for s in summaries if s.get("verdict") == "cancelled")
        total_claims = sum(s.get("claim_count", 0) for s in summaries)
        total_violations = sum(s.get("violation_count", 0) for s in summaries)
        pass_rate = passed / total if total > 0 else 0.0

        return DashboardSummary(
            total_runs=total,
            passed=passed,
            failed=failed,
            cancelled=cancelled,
            pass_rate=pass_rate,
            total_claims=total_claims,
            total_violations=total_violations,
        )

    def save_report(self, report: RunReport) -> Path:
        """Save a generated report."""
        self._ensure_dirs()
        reports_dir = self.dashboard_dir / "reports"
        reports_dir.mkdir(exist_ok=True)

        json_path = reports_dir / f"{report.run_id}.json"
        json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")

        md_path = reports_dir / f"{report.run_id}.md"
        md_path.write_text(report.to_markdown())

        return json_path


# ---------------------------------------------------------------------------
# Telemetry event
# ---------------------------------------------------------------------------

def make_dashboard_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a telemetry event for dashboard actions."""
    return {
        "type": "dashboard_ux",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
