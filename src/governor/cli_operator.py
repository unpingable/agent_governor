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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Re-export shared types for backward compatibility (tests import from here)
from .operator_snapshot import (  # noqa: F401
    CheckItem,
    TraceEvent,
    _safe_parse_ts,
    _trace_sort_key,
    _SOURCE_PRIORITY,
    classify_rollup,
    count_checks,
    collect_trace_events,
    # Collectors re-exported for any direct callers
    _collect_receipt_events,
    _collect_scar_events,
    _collect_scope_events,
    _collect_violation_events,
)


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
# Helpers
# ---------------------------------------------------------------------------

_FALLBACK_BANNER = "WARNING: daemon unreachable — showing local state"


def _print_fallback_banner(backend: str, as_json: bool) -> None:
    """Print fallback warning when auto backend tried daemon and failed.

    Only prints in human mode (not JSON) and only when GOV_BACKEND was
    "auto" (i.e. backend chooser tried RPC and fell back).  When
    GOV_BACKEND=local, silence is correct — the user asked for local.
    """
    if as_json:
        return
    import os
    forced = os.environ.get("GOV_BACKEND", "auto").strip().lower()
    if forced == "local":
        return
    # If we reached here it means auto tried RPC and failed
    print(f"\n  {_FALLBACK_BANNER}\n", file=sys.stderr)


def _truncate(s: str, width: int = MAX_WIDTH - 4) -> str:
    """Truncate string for text display, keeping full detail for JSON."""
    if len(s) <= width:
        return s
    return s[: width - 1] + "\u2026"


def _section_err(name: str, error: str) -> dict[str, Any]:
    """Standard error section for JSON."""
    return {"ok": False, "error": error}


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
# Rendering helpers (used by doctor_command and dashboard_command)
# ---------------------------------------------------------------------------

def _render_doctor_text(checks: list[CheckItem], counts: dict[str, int]) -> None:
    """Render doctor checks as text to stdout."""
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


def _render_doctor_json(checks: list[CheckItem], counts: dict[str, int]) -> None:
    """Render doctor checks as JSON to stdout."""
    output = {
        "schema_version": 1,
        "checks": [c.to_dict() for c in checks],
        "counts": counts,
    }
    print(json.dumps(output, indent=2))


def _doctor_exit_code(counts: dict[str, int], strict: bool) -> int:
    """Compute doctor exit code from counts."""
    if counts["error"] > 0:
        return 1
    if strict and counts["warn"] > 0:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def dashboard_command(gov_dir: Path, as_json: bool) -> int:
    """Operator dashboard (status --full). Returns exit code.

    Tries daemon RPC first, falls back to local file reads.
    """
    from .cli_backend import get_operator_backend, sync_rpc_call

    backend = get_operator_backend(gov_dir)

    if backend == "rpc":
        from .daemon import default_socket_path
        snapshot = sync_rpc_call(
            default_socket_path(gov_dir), "operator.snapshot", {}
        )
        if snapshot and "rollup" in snapshot:
            from .status_rollup import StatusRollup, render_json, render_text
            rollup = StatusRollup(**snapshot["rollup"])
            if as_json:
                print(render_json(rollup))
            else:
                print(render_text(rollup))
            return 0

    # Local fallback
    _print_fallback_banner(backend, as_json)
    from .status_rollup import build_status_rollup, render_json, render_text

    rollup = build_status_rollup(gov_dir)

    if as_json:
        print(render_json(rollup))
    else:
        print(render_text(rollup))

    return 0


def doctor_command(gov_dir: Path, as_json: bool, strict: bool) -> int:
    """Doctor: walk subsystems, report non-nominal. Returns exit code.

    Tries daemon RPC first, falls back to local file reads.
    """
    from .cli_backend import get_operator_backend, sync_rpc_call

    backend = get_operator_backend(gov_dir)

    if backend == "rpc":
        from .daemon import default_socket_path
        snapshot = sync_rpc_call(
            default_socket_path(gov_dir), "operator.snapshot", {}
        )
        if snapshot and "checks" in snapshot:
            checks = [CheckItem.from_dict(c) for c in snapshot["checks"]]
            counts = snapshot["counts"]
            if as_json:
                _render_doctor_json(checks, counts)
            else:
                _render_doctor_text(checks, counts)
            return _doctor_exit_code(counts, strict)

    # Local fallback
    _print_fallback_banner(backend, as_json)
    from .status_rollup import build_status_rollup
    rollup = build_status_rollup(gov_dir)
    checks = classify_rollup(rollup)
    counts = count_checks(checks)

    if as_json:
        _render_doctor_json(checks, counts)
    else:
        _render_doctor_text(checks, counts)

    return _doctor_exit_code(counts, strict)


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
    """Unified timeline. Returns exit code.

    Tries daemon RPC first, falls back to local file reads.
    """
    from .cli_backend import get_operator_backend, sync_rpc_call

    backend = get_operator_backend(gov_dir)

    if backend == "rpc":
        from .daemon import default_socket_path
        result = sync_rpc_call(
            default_socket_path(gov_dir),
            "trace.tail",
            {"limit": last, "source": source},
        )
        if result and "events" in result:
            events = [TraceEvent.from_dict(e) for e in result["events"]]
            return _render_trace(events, as_json)

    # Local fallback
    _print_fallback_banner(backend, as_json)
    events = collect_trace_events(gov_dir, limit=last, source=source)
    return _render_trace(events, as_json)


def _render_trace(all_events: list[TraceEvent], as_json: bool) -> int:
    """Render trace events to stdout. Returns exit code."""
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
