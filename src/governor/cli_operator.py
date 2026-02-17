# SPDX-License-Identifier: Apache-2.0
"""
CLI operator surface: front-door commands for the governor.

Four read-only commands that collapse subsystem state into obvious workflows:
  - dashboard (status --full): one-page dashboard
  - doctor: walk subsystems, report non-nominal, suggest next commands
  - explain: static lookup of diagnostic codes
  - trace: unified timeline of receipts, scars, scope, violations
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Canonical glyphs — one casing, everywhere
# ---------------------------------------------------------------------------
GLYPH_OK = "[ok]"
GLYPH_INFO = "[info]"
GLYPH_WARN = "[WARN]"
GLYPH_ERR = "[err]"

# Map receipt verdicts to operator glyphs
_RECEIPT_VERDICT_GLYPH = {
    "pass": GLYPH_OK,
    "warn": GLYPH_WARN,
    "block": GLYPH_ERR,
    "fail": GLYPH_ERR,
}

MAX_WIDTH = 80


# ---------------------------------------------------------------------------
# Dataclasses
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(s: str, width: int = MAX_WIDTH - 4) -> str:
    """Truncate string for text display, keeping full detail for JSON."""
    if len(s) <= width:
        return s
    return s[: width - 1] + "\u2026"


def _section_err(name: str, error: str) -> dict[str, Any]:
    """Standard error section for JSON."""
    return {"ok": False, "error": error}


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


def _probe_file(gov_dir: Path, filename: str) -> bool:
    """Check if a subsystem state file exists without loading it."""
    return (gov_dir / filename).exists()


# ---------------------------------------------------------------------------
# Loaders — each returns {"ok": bool, ...}, never raises, never mutates
# ---------------------------------------------------------------------------

def _load_envelope(gov_dir: Path) -> dict[str, Any]:
    try:
        from .envelopes import get_current_envelope
        config = get_current_envelope(gov_dir)
        return {"ok": True, "mode": config.mode.value}
    except Exception as e:
        return _section_err("envelope", str(e))


def _load_regime(gov_dir: Path) -> dict[str, Any]:
    try:
        if not _probe_file(gov_dir, "regime.json"):
            return {"ok": True, "name": "elastic", "warnings": []}
        from .regime import RegimeDetector
        data = json.loads((gov_dir / "regime.json").read_text())
        detector = RegimeDetector.from_dict(data)
        state = detector.get_state()
        warnings = []
        name = state.get("regime", "elastic")
        if hasattr(detector, "current_regime"):
            name = detector.current_regime.value
        return {"ok": True, "name": name, "warnings": warnings}
    except Exception as e:
        return _section_err("regime", str(e))


def _load_drift(gov_dir: Path) -> dict[str, Any]:
    try:
        if not _probe_file(gov_dir, "drift_detector.json"):
            return {"ok": True, "alert_level": "none", "quarantined": 0}
        from .drift import DriftDetector
        data = json.loads((gov_dir / "drift_detector.json").read_text())
        detector = DriftDetector.from_dict(data)
        alert = "none"
        if hasattr(detector, "current_alert"):
            alert = detector.current_alert
            if hasattr(alert, "value"):
                alert = alert.value
        quarantined = len(detector.quarantined_premises())
        return {"ok": True, "alert_level": str(alert).lower(), "quarantined": quarantined}
    except Exception as e:
        return _section_err("drift", str(e))


def _load_scars(gov_dir: Path) -> dict[str, Any]:
    try:
        if not _probe_file(gov_dir, "scars.json"):
            return {"ok": True, "health": "NOMINAL", "hard": 0, "soft": 0}
        from .scars import ScarLedger
        data = json.loads((gov_dir / "scars.json").read_text())
        ledger = ScarLedger.from_dict(data)
        summary = ledger.get_summary()
        metrics = ledger.get_metrics()
        return {
            "ok": True,
            "health": summary["health"],
            "hard": metrics["hard_scars"],
            "soft": metrics["soft_scars"],
        }
    except Exception as e:
        return _section_err("scars", str(e))


def _load_scope(gov_dir: Path) -> dict[str, Any]:
    try:
        if not _probe_file(gov_dir, "scope.json"):
            return {
                "ok": True, "configured": False, "level": None,
                "grants": 0, "escalations_allowed": 0, "escalations_denied": 0,
            }
        from .scope import ScopeGovernor
        sg = ScopeGovernor.load(gov_dir)
        metrics = sg.get_metrics()
        return {
            "ok": True,
            "configured": True,
            "level": metrics.get("run_scope_level"),
            "grants": metrics.get("grants_active", 0),
            "escalations_allowed": metrics.get("escalations_allowed", 0),
            "escalations_denied": metrics.get("escalations_denied", 0),
        }
    except Exception as e:
        return _section_err("scope", str(e))


def _load_correlator(gov_dir: Path) -> dict[str, Any]:
    try:
        from .correlator_telemetry import CorrelatorTelemetry
        ct = CorrelatorTelemetry.load(gov_dir)
        metrics = ct.get_metrics()
        diag = ct.get_latest_diagnostic()
        regime = metrics.get("regime", "unknown")
        capture = False
        indicators: list[str] = []
        if diag:
            capture = diag.gate_met and len(diag.indicators_triggered) > 0
            indicators = [i.value if hasattr(i, "value") else str(i)
                          for i in diag.indicators_triggered]
        return {
            "ok": True,
            "regime": regime,
            "capture": capture,
            "indicators": indicators,
        }
    except Exception as e:
        return _section_err("correlator", str(e))


def _load_stability(gov_dir: Path) -> dict[str, Any]:
    try:
        from .semantic_stability import StabilityStore
        store = StabilityStore(gov_dir)
        results = store.query(limit=1)
        if not results:
            return {"ok": True, "recommendation": "no audits", "stiffness": None}
        latest = results[0]
        return {
            "ok": True,
            "recommendation": latest.recommendation,
            "stiffness": round(latest.fingerprint.stiffness, 3),
        }
    except Exception as e:
        return _section_err("stability", str(e))


def _load_violations(gov_dir: Path) -> dict[str, Any]:
    try:
        from .violation_resolver import ViolationResolver
        resolver = ViolationResolver(gov_dir)
        pending = resolver.get_pending()
        count = 1 if pending else 0
        return {"ok": True, "pending": count}
    except Exception as e:
        return _section_err("violations", str(e))


def _load_recent_receipts(gov_dir: Path, limit: int = 5) -> dict[str, Any]:
    try:
        # Probe before constructing — GateReceiptSystem creates dirs on init
        if not (gov_dir / "receipts").exists():
            return {"ok": True, "items": []}
        from .gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        results = system.query(limit=limit)
        items = []
        for r in results:
            items.append({
                "gate": r.gate,
                "verdict": r.verdict,
                "receipt_id": r.receipt_id[:12],
                "timestamp": r.timestamp,
            })
        return {"ok": True, "items": items}
    except Exception as e:
        return _section_err("recent_receipts", str(e))


# ---------------------------------------------------------------------------
# Trace event collectors
# ---------------------------------------------------------------------------

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
# Explain table
# ---------------------------------------------------------------------------

@dataclass
class ExplainEntry:
    """One code explanation."""
    category: str
    code: str
    short: str
    detail: str
    see_also: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "category": self.category,
            "code": self.code,
            "short": self.short,
            "detail": self.detail,
        }
        if self.see_also:
            d["see_also"] = self.see_also
        return d


EXPLANATIONS: list[ExplainEntry] = [
    # regime
    ExplainEntry("regime", "ELASTIC",
                 "Normal operation",
                 "All signals nominal. Governor enforcing with standard thresholds.",
                 "governor regime status"),
    ExplainEntry("regime", "WARM",
                 "Elevated activity",
                 "Tool gain or claim frequency rising. Governor may tighten thresholds.",
                 "governor regime status"),
    ExplainEntry("regime", "DUCTILE",
                 "Under stress",
                 "Multiple signals elevated. Some constraints may be relaxed to avoid deadlock.",
                 "governor regime status"),
    ExplainEntry("regime", "UNSTABLE",
                 "Critical",
                 "System near operational limits. Immediate human review recommended.",
                 "governor regime status"),
    # scars
    ExplainEntry("scars", "NOMINAL",
                 "No active scars",
                 "No past failures constraining current operation.",
                 "governor scar list"),
    ExplainEntry("scars", "CAUTIOUS",
                 "Soft scars active",
                 "Past failures detected but annealed. Actions have elevated cost multipliers.",
                 "governor scar list"),
    ExplainEntry("scars", "CONSTRAINED",
                 "Hard scars active",
                 "Past failures produced hard vetoes. Some actions fully blocked until anneal.",
                 "governor scar list --hard"),
    # gate_verdict
    ExplainEntry("gate_verdict", "PASS",
                 "Gate passed",
                 "Evidence satisfied all kernel constraints. Receipt emitted.",
                 "governor receipts --verdict pass"),
    ExplainEntry("gate_verdict", "WARN",
                 "Gate warning",
                 "Evidence partially satisfied. Allowed but flagged for review.",
                 "governor receipts --verdict warn"),
    ExplainEntry("gate_verdict", "BLOCK",
                 "Gate blocked",
                 "Evidence failed kernel constraints. Action prevented.",
                 "governor receipts --verdict block"),
    ExplainEntry("gate_verdict", "FAIL",
                 "Gate hard failure",
                 "Internal error or unrecoverable constraint violation.",
                 "governor receipts --verdict fail"),
    # correlator
    ExplainEntry("correlator", "LEVERAGE",
                 "Normal correlator regime",
                 "Governor adds value without distorting agent behavior.",
                 "governor correlator status"),
    ExplainEntry("correlator", "SHEAR",
                 "Authority-throughput tension",
                 "Blocking authority reduces throughput. May indicate over-constraint.",
                 "governor correlator status"),
    ExplainEntry("correlator", "CAPTURE",
                 "Capture detected",
                 "Governor's constraints may be shaping agent behavior to serve the governor's own metrics rather than the user's goals.",
                 "governor correlator status"),
    ExplainEntry("correlator", "GOVERNOR_CAPTURE_DETECTED",
                 "Binding capture declaration",
                 "T/A gate met with active indicators. Capture is declared, not merely suspected.",
                 "governor correlator status"),
    # stability
    ExplainEntry("stability", "STABLE",
                 "Prompt-output mapping stable",
                 "Perturbation audit shows low stiffness and consistent outputs.",
                 "governor conditioning status"),
    ExplainEntry("stability", "BRITTLE",
                 "High prompt sensitivity",
                 "Small perturbations cause large output divergence. May indicate fragile prompts.",
                 "governor conditioning status"),
    ExplainEntry("stability", "MULTIMODAL",
                 "Multiple output modes",
                 "Same prompt produces qualitatively different outputs. Basin entropy is high.",
                 "governor conditioning status"),
    ExplainEntry("stability", "CALIBRATING",
                 "Insufficient data",
                 "Not enough audit results to determine stability. Run more audits.",
                 "governor conditioning status"),
    # drift
    ExplainEntry("drift", "NONE",
                 "No drift detected",
                 "Premise recurrence, attention, and coherence signals all nominal.",
                 "governor drift status"),
    ExplainEntry("drift", "WATCH",
                 "Drift watch",
                 "Early drift signals detected. Monitoring escalated.",
                 "governor drift status"),
    ExplainEntry("drift", "WARN_DRIFT",
                 "Drift warning",
                 "Multiple drift signals elevated. Premises may be shifting.",
                 "governor drift status"),
    ExplainEntry("drift", "QUARANTINE",
                 "Premises quarantined",
                 "Active quarantine of suspicious premises. Review required.",
                 "governor drift quarantined"),
]

# Build lookup indexes
_BY_QUALIFIED: dict[str, ExplainEntry] = {}
_BY_BARE: dict[str, list[ExplainEntry]] = {}
_CATEGORIES: dict[str, list[ExplainEntry]] = {}

for _e in EXPLANATIONS:
    qualified = f"{_e.category}:{_e.code}"
    _BY_QUALIFIED[qualified.lower()] = _e
    bare = _e.code.lower()
    _BY_BARE.setdefault(bare, []).append(_e)
    _CATEGORIES.setdefault(_e.category, []).append(_e)


def _lookup_code(code: str) -> list[ExplainEntry]:
    """Look up a code. Returns matches (0, 1, or >1 for ambiguous)."""
    normalized = code.strip().lower()
    # Try qualified first
    if ":" in normalized:
        entry = _BY_QUALIFIED.get(normalized)
        return [entry] if entry else []
    # Bare lookup
    return _BY_BARE.get(normalized, [])


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def dashboard_command(gov_dir: Path, as_json: bool) -> int:
    """Operator dashboard (status --full). Returns exit code."""
    sections = {
        "envelope": _load_envelope(gov_dir),
        "regime": _load_regime(gov_dir),
        "drift": _load_drift(gov_dir),
        "scars": _load_scars(gov_dir),
        "scope": _load_scope(gov_dir),
        "correlator": _load_correlator(gov_dir),
        "stability": _load_stability(gov_dir),
        "violations": _load_violations(gov_dir),
        "recent_receipts": _load_recent_receipts(gov_dir),
    }

    if as_json:
        output = {"schema_version": 1}
        output.update(sections)
        print(json.dumps(output, indent=2))
        return 0

    # Text output
    print("Governor Dashboard")

    # Envelope
    env = sections["envelope"]
    if env["ok"]:
        print(f"  Envelope:    {env['mode']}")
    else:
        print(f"  {GLYPH_ERR} Envelope:    {_truncate(env['error'])}")

    # Regime
    reg = sections["regime"]
    if reg["ok"]:
        print(f"  Regime:      {reg['name'].upper()}")
    else:
        print(f"  {GLYPH_ERR} Regime:      {_truncate(reg['error'])}")

    # Drift
    dft = sections["drift"]
    if dft["ok"]:
        print(f"  Drift:       {dft['alert_level']} ({dft['quarantined']} quarantined)")
    else:
        print(f"  {GLYPH_ERR} Drift:       {_truncate(dft['error'])}")

    # Scars
    sc = sections["scars"]
    if sc["ok"]:
        print(f"  Scars:       {sc['health']} ({sc['hard']} hard, {sc['soft']} soft)")
    else:
        print(f"  {GLYPH_ERR} Scars:       {_truncate(sc['error'])}")

    # Scope
    scp = sections["scope"]
    if scp["ok"]:
        if scp.get("configured"):
            lvl = scp["level"] or "?"
            a = scp["escalations_allowed"]
            d = scp["escalations_denied"]
            print(f"  Scope:       level {lvl} ({scp['grants']} grants, {a}/{d} allow/deny)")
        else:
            print("  Scope:       not configured")
    else:
        print(f"  {GLYPH_ERR} Scope:       {_truncate(scp['error'])}")

    # Correlator
    cor = sections["correlator"]
    if cor["ok"]:
        cap = "CAPTURE" if cor["capture"] else "no capture"
        print(f"  Correlator:  {cor['regime']} ({cap})")
    else:
        print(f"  {GLYPH_ERR} Correlator:  {_truncate(cor['error'])}")

    # Stability
    stb = sections["stability"]
    if stb["ok"]:
        stiff = f" (stiffness {stb['stiffness']})" if stb["stiffness"] is not None else ""
        print(f"  Stability:   {stb['recommendation'].upper()}{stiff}")
    else:
        print(f"  {GLYPH_ERR} Stability:   {_truncate(stb['error'])}")

    # Violations
    vio = sections["violations"]
    if vio["ok"]:
        print(f"  Violations:  {vio['pending']} pending")
    else:
        print(f"  {GLYPH_ERR} Violations:  {_truncate(vio['error'])}")

    # Recent receipts
    rcpt = sections["recent_receipts"]
    if rcpt["ok"] and rcpt["items"]:
        print()
        print("  Recent Receipts:")
        for item in rcpt["items"]:
            glyph = _RECEIPT_VERDICT_GLYPH.get(item["verdict"], f"[{item['verdict']}]")
            gate = item["gate"]
            rid = item["receipt_id"]
            ts = item["timestamp"]
            print(f"    {glyph:>6} {gate:<20} {rid}  {ts}")
    elif rcpt["ok"]:
        print()
        print("  Recent Receipts: none")
    else:
        print()
        print(f"  {GLYPH_ERR} Recent Receipts: {_truncate(rcpt['error'])}")

    return 0


def doctor_command(gov_dir: Path, as_json: bool, strict: bool) -> int:
    """Doctor: walk subsystems, report non-nominal. Returns exit code."""
    checks: list[CheckItem] = []

    # 1. Envelope — always ok
    env = _load_envelope(gov_dir)
    if env["ok"]:
        checks.append(CheckItem("envelope", "ok", env["mode"]))
    else:
        checks.append(CheckItem("envelope", "error", env["error"],
                                ["governor envelope"]))

    # 2. Regime
    reg = _load_regime(gov_dir)
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
    dft = _load_drift(gov_dir)
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
    sc = _load_scars(gov_dir)
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
    cor = _load_correlator(gov_dir)
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
    scp = _load_scope(gov_dir)
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
    stb = _load_stability(gov_dir)
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
    vio = _load_violations(gov_dir)
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

    # 9. Recent receipts — warn if recent blocks
    rcpt = _load_recent_receipts(gov_dir)
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

    # Compute counts
    counts = {"ok": 0, "info": 0, "warn": 0, "error": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1

    if as_json:
        output = {
            "schema_version": 1,
            "checks": [c.to_dict() for c in checks],
            "counts": counts,
        }
        print(json.dumps(output, indent=2))
    else:
        for c in checks:
            glyph = {
                "ok": GLYPH_OK,
                "info": GLYPH_INFO,
                "warn": GLYPH_WARN,
                "error": GLYPH_ERR,
            }.get(c.status, GLYPH_ERR)
            line = f"  {glyph:>6} {c.name:<14} {_truncate(c.summary, 50)}"
            print(line)
            for cmd in c.next_commands:
                print(f"         -> {cmd}")

        print()
        parts = []
        if counts["ok"]:
            parts.append(f"{counts['ok']} ok")
        if counts["info"]:
            parts.append(f"{counts['info']} info")
        if counts["warn"]:
            parts.append(f"{counts['warn']} warn")
        if counts["error"]:
            parts.append(f"{counts['error']} error")
        print(f"  {', '.join(parts)}")

    # Exit code
    has_errors = counts["error"] > 0
    has_warns = counts["warn"] > 0
    if has_errors:
        return 1
    if strict and has_warns:
        return 1
    return 0


def explain_command(code: str, as_json: bool, list_all: bool) -> int:
    """Explain a diagnostic code. Returns exit code."""
    if list_all:
        if as_json:
            output = {
                "schema_version": 1,
                "categories": {},
            }
            for cat, entries in _CATEGORIES.items():
                output["categories"][cat] = [e.to_dict() for e in entries]
            print(json.dumps(output, indent=2))
        else:
            for cat, entries in _CATEGORIES.items():
                print(f"{cat}:")
                for e in entries:
                    print(f"  {e.code:<30} {e.short}")
                print()
        return 0

    if not code:
        print("Usage: governor explain <CODE>", file=sys.stderr)
        print("       governor explain --list", file=sys.stderr)
        return 2

    matches = _lookup_code(code)
    if not matches:
        print(f"Unknown code: {code}", file=sys.stderr)
        print("Run `governor explain --list` for all codes.", file=sys.stderr)
        return 1

    if len(matches) > 1:
        # Ambiguous — require qualified form
        qualified = [f"{m.category}:{m.code}" for m in matches]
        print(f"Ambiguous code: {code}", file=sys.stderr)
        print(f"Did you mean: {', '.join(qualified)}?", file=sys.stderr)
        return 1

    entry = matches[0]
    if as_json:
        output = {"schema_version": 1, "entry": entry.to_dict()}
        print(json.dumps(output, indent=2))
    else:
        print(f"{entry.category}:{entry.code}")
        print(f"  {entry.short}")
        print()
        # Word-wrap detail to ~76 cols (indented by 2)
        words = entry.detail.split()
        line = " "
        for w in words:
            if len(line) + len(w) + 1 > 76:
                print(f" {line}")
                line = " " + w
            else:
                line += " " + w
        if line.strip():
            print(f" {line}")
        if entry.see_also:
            print()
            print(f"  See: {entry.see_also}")

    return 0


def trace_command(gov_dir: Path, as_json: bool, last: int, source: str | None) -> int:
    """Unified timeline. Returns exit code."""
    fetch_limit = last * 2

    # Collect from all sources
    all_events: list[TraceEvent] = []
    all_events.extend(_collect_receipt_events(gov_dir, fetch_limit))
    all_events.extend(_collect_scar_events(gov_dir, fetch_limit))
    all_events.extend(_collect_scope_events(gov_dir, fetch_limit))
    all_events.extend(_collect_violation_events(gov_dir))

    # Filter by source
    if source:
        all_events = [e for e in all_events if e.source == source]

    # Sort deterministically
    all_events.sort(key=_trace_sort_key)

    # Truncate
    all_events = all_events[:last]

    if not all_events:
        if as_json:
            print(json.dumps({"schema_version": 1, "events": []}, indent=2))
        else:
            print("No events recorded.")
        return 0

    if as_json:
        output = {
            "schema_version": 1,
            "events": [e.to_dict() for e in all_events],
        }
        print(json.dumps(output, indent=2))
    else:
        for e in all_events:
            ts_short = e.ts[:19] if len(e.ts) >= 19 else e.ts
            src = e.source[:8]
            print(f"  {ts_short:<20} {src:<10} {e.kind:<16} {_truncate(e.summary, 30)}")

    return 0
