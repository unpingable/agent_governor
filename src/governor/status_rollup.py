# SPDX-License-Identifier: Apache-2.0
"""
StatusRollup: single truth object for the operator one-pager.

build_status_rollup() assembles all subsystem state into one frozen dataclass.
Renderers are dumb formatters — they never call loaders or compute aggregates.
dashboard_command, status (bare), and future consumers all share this builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROLLUP_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Dataclass — frozen, serializable, no methods that touch disk
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StatusRollup:
    """Complete operator-visible state snapshot.

    Every field is pre-computed by build_status_rollup().
    Renderers consume this; they never call loaders.
    """
    schema_version: int
    envelope: dict[str, Any]
    regime: dict[str, Any]
    drift: dict[str, Any]
    scars: dict[str, Any]
    scope: dict[str, Any]
    correlator: dict[str, Any]
    stability: dict[str, Any]
    violations: dict[str, Any]
    recent_receipts: dict[str, Any]
    lanes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "envelope": self.envelope,
            "regime": self.regime,
            "drift": self.drift,
            "scars": self.scars,
            "scope": self.scope,
            "correlator": self.correlator,
            "stability": self.stability,
            "violations": self.violations,
            "recent_receipts": self.recent_receipts,
            "lanes": self.lanes,
        }


# ---------------------------------------------------------------------------
# Builder — calls loaders, returns frozen rollup
# ---------------------------------------------------------------------------

def _load_lanes(gov_dir: Path) -> dict[str, Any]:
    """Load lane routing summary. Never raises."""
    try:
        from .lanes import LaneRouter, ArtifactReuseStore
        artifact_dir = gov_dir / "artifacts"
        if artifact_dir.exists():
            store = ArtifactReuseStore(artifact_dir)
            artifact_stats = store.stats()
        else:
            artifact_stats = {"total": 0}
        # Construct a default router to read config
        lr = LaneRouter()
        return {
            "ok": True,
            "autopilot_level": lr.autopilot_level,
            "policy_version": lr.policy_version,
            "budget_total_usd": lr.budget_total_usd,
            "artifact_count": artifact_stats.get("total", 0),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_status_rollup(gov_dir: Path) -> StatusRollup:
    """Assemble all subsystem state into a frozen StatusRollup.

    Imports loaders from cli_operator to avoid duplication.
    Each loader returns {"ok": bool, ...} and never raises.
    """
    from .cli_operator import (
        _load_envelope,
        _load_regime,
        _load_drift,
        _load_scars,
        _load_scope,
        _load_correlator,
        _load_stability,
        _load_violations,
        _load_recent_receipts,
    )

    return StatusRollup(
        schema_version=ROLLUP_SCHEMA_VERSION,
        envelope=_load_envelope(gov_dir),
        regime=_load_regime(gov_dir),
        drift=_load_drift(gov_dir),
        scars=_load_scars(gov_dir),
        scope=_load_scope(gov_dir),
        correlator=_load_correlator(gov_dir),
        stability=_load_stability(gov_dir),
        violations=_load_violations(gov_dir),
        recent_receipts=_load_recent_receipts(gov_dir),
        lanes=_load_lanes(gov_dir),
    )


# ---------------------------------------------------------------------------
# Renderers — dumb formatters, no computation, no loader calls
# ---------------------------------------------------------------------------

_MAX_WIDTH = 80

_RECEIPT_VERDICT_GLYPH = {
    "pass": "[ok]",
    "warn": "[WARN]",
    "block": "[err]",
    "fail": "[err]",
}


def _truncate(s: str, width: int = _MAX_WIDTH - 4) -> str:
    if len(s) <= width:
        return s
    return s[: width - 1] + "\u2026"


def render_json(rollup: StatusRollup) -> str:
    """Render rollup as JSON string. Pure formatting."""
    return json.dumps(rollup.to_dict(), indent=2)


def render_text(rollup: StatusRollup) -> str:
    """Render rollup as human-readable text. Pure formatting."""
    lines: list[str] = []
    lines.append("Governor Dashboard")

    # Envelope
    env = rollup.envelope
    if env["ok"]:
        lines.append(f"  Envelope:    {env['mode']}")
    else:
        lines.append(f"  [err] Envelope:    {_truncate(env['error'])}")

    # Regime
    reg = rollup.regime
    if reg["ok"]:
        lines.append(f"  Regime:      {reg['name'].upper()}")
    else:
        lines.append(f"  [err] Regime:      {_truncate(reg['error'])}")

    # Drift
    dft = rollup.drift
    if dft["ok"]:
        lines.append(f"  Drift:       {dft['alert_level']} ({dft['quarantined']} quarantined)")
    else:
        lines.append(f"  [err] Drift:       {_truncate(dft['error'])}")

    # Scars
    sc = rollup.scars
    if sc["ok"]:
        lines.append(f"  Scars:       {sc['health']} ({sc['hard']} hard, {sc['soft']} soft)")
    else:
        lines.append(f"  [err] Scars:       {_truncate(sc['error'])}")

    # Scope
    scp = rollup.scope
    if scp["ok"]:
        if scp.get("configured"):
            lvl = scp["level"] or "?"
            a = scp["escalations_allowed"]
            d = scp["escalations_denied"]
            lines.append(f"  Scope:       level {lvl} ({scp['grants']} grants, {a}/{d} allow/deny)")
        else:
            lines.append("  Scope:       not configured")
    else:
        lines.append(f"  [err] Scope:       {_truncate(scp['error'])}")

    # Correlator
    cor = rollup.correlator
    if cor["ok"]:
        cap = "CAPTURE" if cor["capture"] else "no capture"
        lines.append(f"  Correlator:  {cor['regime']} ({cap})")
    else:
        lines.append(f"  [err] Correlator:  {_truncate(cor['error'])}")

    # Stability
    stb = rollup.stability
    if stb["ok"]:
        stiff = f" (stiffness {stb['stiffness']})" if stb["stiffness"] is not None else ""
        lines.append(f"  Stability:   {stb['recommendation'].upper()}{stiff}")
    else:
        lines.append(f"  [err] Stability:   {_truncate(stb['error'])}")

    # Violations
    vio = rollup.violations
    if vio["ok"]:
        lines.append(f"  Violations:  {vio['pending']} pending")
    else:
        lines.append(f"  [err] Violations:  {_truncate(vio['error'])}")

    # Lanes
    ln = rollup.lanes
    if ln["ok"]:
        lines.append(
            f"  Lanes:       autopilot {ln['autopilot_level']}"
            f" (v{ln['policy_version']}, {ln['artifact_count']} artifacts)"
        )
    else:
        lines.append(f"  [err] Lanes:       {_truncate(ln['error'])}")

    # Recent receipts
    rcpt = rollup.recent_receipts
    if rcpt["ok"] and rcpt["items"]:
        lines.append("")
        lines.append("  Recent Receipts:")
        for item in rcpt["items"]:
            glyph = _RECEIPT_VERDICT_GLYPH.get(item["verdict"], f"[{item['verdict']}]")
            gate = item["gate"]
            rid = item["receipt_id"]
            ts = item["timestamp"]
            lines.append(f"    {glyph:>6} {gate:<20} {rid}  {ts}")
    elif rcpt["ok"]:
        lines.append("")
        lines.append("  Recent Receipts: none")
    else:
        lines.append("")
        lines.append(f"  [err] Recent Receipts: {_truncate(rcpt['error'])}")

    return "\n".join(lines)
