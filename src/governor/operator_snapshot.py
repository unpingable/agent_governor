# SPDX-License-Identifier: Apache-2.0
"""
Shared operator logic: dataclasses and pure functions for doctor + trace.

This module is imported by both cli_operator.py (CLI glue) and daemon.py
(RPC handlers). It must NOT import from cli_operator or daemon to avoid
circular dependencies.

Import chain:
    daemon.py → operator_snapshot.py → status_rollup.py → cli_operator._load_*
    cli_operator.py → operator_snapshot.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Dataclasses (moved from cli_operator.py)
# ---------------------------------------------------------------------------

@dataclass
class CheckItem:
    """One doctor check result."""
    name: str
    status: str  # "ok", "info", "warn", "error"
    summary: str
    next_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "next_commands": self.next_commands,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckItem:
        return cls(
            name=d["name"],
            status=d["status"],
            summary=d["summary"],
            next_commands=d.get("next_commands", []),
        )


@dataclass
class TraceEvent:
    """One unified timeline event."""
    ts: str  # ISO 8601
    source: str  # receipt, scar, scope, violation
    kind: str  # event-type-specific
    summary: str
    ref: str  # ID for the event
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "source": self.source,
            "kind": self.kind,
            "summary": self.summary,
            "ref": self.ref,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceEvent:
        return cls(
            ts=d["ts"],
            source=d["source"],
            kind=d["kind"],
            summary=d["summary"],
            ref=d["ref"],
            detail=d.get("detail", {}),
        )


# ---------------------------------------------------------------------------
# Trace helpers (moved from cli_operator.py)
# ---------------------------------------------------------------------------

def _safe_parse_ts(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp, returning epoch on failure."""
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


_SOURCE_PRIORITY = {"receipt": 0, "scar": 1, "scope": 2, "violation": 3}


def _trace_sort_key(event: TraceEvent) -> tuple:
    """Sort key: newest first, then source priority, then ref."""
    ts = _safe_parse_ts(event.ts)
    return (-ts.timestamp(), _SOURCE_PRIORITY.get(event.source, 99), event.ref)


# ---------------------------------------------------------------------------
# Trace event collectors (moved from cli_operator.py)
# ---------------------------------------------------------------------------

def _probe_file(gov_dir: Path, filename: str) -> bool:
    """Check if a subsystem state file exists without loading it."""
    return (gov_dir / filename).exists()


def _collect_receipt_events(gov_dir: Path, limit: int) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    try:
        if not (gov_dir / "receipts").exists():
            return events
        from .gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        for r in system.query(limit=limit):
            events.append(TraceEvent(
                ts=r.timestamp,
                source="receipt",
                kind=r.verdict,
                summary=f"{r.gate}: {r.verdict}",
                ref=r.receipt_id[:12],
                detail={"gate": r.gate, "full_id": r.receipt_id},
            ))
    except Exception:
        pass
    return events


def _collect_scar_events(gov_dir: Path, limit: int) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    try:
        if not _probe_file(gov_dir, "scars.json"):
            return events
        from .scars import ScarLedger
        data = json.loads((gov_dir / "scars.json").read_text())
        ledger = ScarLedger.from_dict(data)
        for fe in ledger.get_failure_history(limit=limit):
            ts = fe.timestamp if hasattr(fe, "timestamp") else ""
            fid = fe.failure_id if hasattr(fe, "failure_id") else ""
            region = fe.region if hasattr(fe, "region") else ""
            events.append(TraceEvent(
                ts=ts,
                source="scar",
                kind="failure",
                summary=f"failure in {region}",
                ref=fid,
                detail={"region": region},
            ))
    except Exception:
        pass
    return events


def _collect_scope_events(gov_dir: Path, limit: int) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    try:
        if not _probe_file(gov_dir, "scope.json"):
            return events
        from .scope import ScopeGovernor
        sg = ScopeGovernor.load(gov_dir)
        history = sg.get_escalation_history()
        for er in history[-limit:]:
            ts = er.timestamp if hasattr(er, "timestamp") else ""
            verdict = er.verdict.value if hasattr(er.verdict, "value") else str(er.verdict)
            eid = er.escalation_id if hasattr(er, "escalation_id") else ""
            kind = f"escalation_{verdict}"
            events.append(TraceEvent(
                ts=ts,
                source="scope",
                kind=kind,
                summary=f"scope escalation: {verdict}",
                ref=eid,
                detail={"verdict": verdict},
            ))
    except Exception:
        pass
    return events


def _collect_violation_events(gov_dir: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    try:
        from .violation_resolver import ViolationResolver
        resolver = ViolationResolver(gov_dir)
        pending = resolver.get_pending()
        if pending:
            events.append(TraceEvent(
                ts=pending.timestamp,
                source="violation",
                kind="pending",
                summary="pending violation",
                ref=pending.id,
            ))
        for exc in resolver.list_exceptions():
            events.append(TraceEvent(
                ts=exc.created_at,
                source="violation",
                kind="exception",
                summary=f"exception ({exc.scope})",
                ref=exc.id,
                detail={"scope": exc.scope},
            ))
    except Exception:
        pass
    return events


# ---------------------------------------------------------------------------
# classify_rollup — pure function, no I/O
# ---------------------------------------------------------------------------

def classify_rollup(rollup: "StatusRollup") -> list[CheckItem]:  # noqa: F821
    """Classify rollup sections into doctor checks. Pure — no I/O.

    Accepts a StatusRollup (from status_rollup.py) and returns a list of
    CheckItem with status/summary/next_commands for each subsystem.
    """
    checks: list[CheckItem] = []

    # 1. Envelope
    env = rollup.envelope
    if env["ok"]:
        checks.append(CheckItem("envelope", "ok", env["mode"]))
    else:
        checks.append(CheckItem("envelope", "error", env["error"],
                                ["governor envelope"]))

    # 2. Regime
    reg = rollup.regime
    if not reg["ok"]:
        checks.append(CheckItem("regime", "error", reg["error"],
                                ["governor regime status"]))
    else:
        name = reg["name"].upper()
        if name in ("DUCTILE", "UNSTABLE"):
            checks.append(CheckItem("regime", "error", name,
                                    ["governor regime status"]))
        elif name == "WARM":
            checks.append(CheckItem("regime", "warn", name,
                                    ["governor regime status"]))
        else:
            checks.append(CheckItem("regime", "ok", name))

    # 3. Drift
    dft = rollup.drift
    if not dft["ok"]:
        checks.append(CheckItem("drift", "error", dft["error"],
                                ["governor drift status"]))
    else:
        level = dft["alert_level"].upper()
        q = dft["quarantined"]
        if level == "QUARANTINE":
            checks.append(CheckItem("drift", "error",
                                    f"{level} ({q} quarantined)",
                                    ["governor drift status",
                                     "governor drift quarantined"]))
        elif level in ("WATCH", "WARN", "WARN_DRIFT"):
            checks.append(CheckItem("drift", "warn",
                                    f"{level} ({q} quarantined)",
                                    ["governor drift status"]))
        else:
            checks.append(CheckItem("drift", "ok",
                                    f"{level} ({q} quarantined)"))

    # 4. Scars
    sc = rollup.scars
    if not sc["ok"]:
        checks.append(CheckItem("scars", "error", sc["error"],
                                ["governor scar list"]))
    else:
        health = sc["health"]
        detail = f"{health} ({sc['hard']} hard, {sc['soft']} soft)"
        if health == "CONSTRAINED":
            checks.append(CheckItem("scars", "error", detail,
                                    ["governor scar list --hard"]))
        elif health == "CAUTIOUS":
            checks.append(CheckItem("scars", "warn", detail,
                                    ["governor scar list"]))
        else:
            checks.append(CheckItem("scars", "ok", detail))

    # 5. Correlator
    cor = rollup.correlator
    if not cor["ok"]:
        checks.append(CheckItem("correlator", "error", cor["error"],
                                ["governor correlator status"]))
    else:
        if cor["capture"]:
            checks.append(CheckItem("correlator", "error",
                                    f"{cor['regime']} (CAPTURE)",
                                    ["governor correlator status"]))
        elif cor["indicators"]:
            checks.append(CheckItem("correlator", "warn",
                                    f"{cor['regime']} ({len(cor['indicators'])} indicators)",
                                    ["governor correlator status"]))
        else:
            checks.append(CheckItem("correlator", "ok", cor["regime"]))

    # 6. Scope
    scp = rollup.scope
    if not scp["ok"]:
        checks.append(CheckItem("scope", "error", scp["error"],
                                ["governor scope status"]))
    else:
        if not scp.get("configured"):
            checks.append(CheckItem("scope", "info", "not configured",
                                    ["governor scope set"]))
        else:
            denied = scp["escalations_denied"]
            allowed = scp["escalations_allowed"]
            total = denied + allowed
            if total > 0 and denied / total > 0.5:
                checks.append(CheckItem("scope", "warn",
                                        f"high denial rate ({denied}/{total})",
                                        ["governor scope status",
                                         "governor scope history"]))
            else:
                checks.append(CheckItem("scope", "ok",
                                        f"{scp['grants']} grants"))

    # 7. Stability
    stb = rollup.stability
    if not stb["ok"]:
        checks.append(CheckItem("stability", "error", stb["error"],
                                ["governor conditioning status"]))
    else:
        rec = stb["recommendation"].lower()
        if rec in ("brittle", "multimodal"):
            checks.append(CheckItem("stability", "warn", rec,
                                    ["governor conditioning status"]))
        else:
            checks.append(CheckItem("stability", "ok", rec))

    # 8. Violations
    vio = rollup.violations
    if not vio["ok"]:
        checks.append(CheckItem("violations", "error", vio["error"],
                                ["governor gate pending"]))
    else:
        if vio["pending"] > 0:
            checks.append(CheckItem("violations", "error",
                                    f"{vio['pending']} pending",
                                    ["governor gate pending"]))
        else:
            checks.append(CheckItem("violations", "ok", "none"))

    # 9. Recent receipts
    rcpt = rollup.recent_receipts
    if not rcpt["ok"]:
        checks.append(CheckItem("receipts", "error", rcpt["error"],
                                ["governor receipts"]))
    else:
        blocks = [r for r in rcpt.get("items", []) if r["verdict"] == "block"]
        if blocks:
            checks.append(CheckItem("receipts", "warn",
                                    f"{len(blocks)} recent blocks",
                                    ["governor receipts --verdict block --last 5"]))
        else:
            checks.append(CheckItem("receipts", "ok", "no recent blocks"))

    return checks


def count_checks(checks: list[CheckItem]) -> dict[str, int]:
    """Count checks by status. Returns {"ok": N, "info": N, "warn": N, "error": N}."""
    counts = {"ok": 0, "info": 0, "warn": 0, "error": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts


def classify_overall_state(counts: dict[str, int]) -> str:
    """Compute overall state label from check counts.

    Returns "Nominal", "Degraded", or "Unsafe".
    """
    if counts.get("error", 0) > 0:
        return "Unsafe"
    if counts.get("warn", 0) > 0:
        return "Degraded"
    return "Nominal"


# ---------------------------------------------------------------------------
# collect_trace_events — unified trace from all sources
# ---------------------------------------------------------------------------

def collect_trace_events(
    gov_dir: Path,
    limit: int = 20,
    source: str | None = None,
) -> list[TraceEvent]:
    """Collect, filter, sort, and truncate trace events from all sources.

    Returns newest-first, deterministically ordered events.
    """
    fetch_limit = limit * 2

    all_events: list[TraceEvent] = []
    all_events.extend(_collect_receipt_events(gov_dir, fetch_limit))
    all_events.extend(_collect_scar_events(gov_dir, fetch_limit))
    all_events.extend(_collect_scope_events(gov_dir, fetch_limit))
    all_events.extend(_collect_violation_events(gov_dir))

    if source:
        all_events = [e for e in all_events if e.source == source]

    all_events.sort(key=_trace_sort_key)
    return all_events[:limit]
