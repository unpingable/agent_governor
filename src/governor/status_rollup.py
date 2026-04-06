# SPDX-License-Identifier: Apache-2.0
"""
StatusRollup: single truth object for the operator one-pager.

build_status_rollup() assembles all subsystem state into one frozen dataclass.
Renderers are dumb formatters — they never call loaders or compute aggregates.
dashboard_command, status (bare), and future consumers all share this builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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
    override_pressure: dict[str, Any]

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
            "override_pressure": self.override_pressure,
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


def _load_override_pressure(gov_dir: Path) -> dict[str, Any]:
    """Load override pressure summary. Never raises."""
    try:
        from .overrides import OverrideManager
        mgr = OverrideManager(gov_dir=gov_dir)
        records = mgr.pressure()
        high = [r for r in records if r.pressure == "high"]
        medium = [r for r in records if r.pressure == "medium"]
        return {
            "ok": True,
            "total": len(records),
            "high": len(high),
            "medium": len(medium),
            "records": [
                {
                    "scope_key": r.scope_key,
                    "anchor_id": r.anchor_id,
                    "override_count": r.override_count,
                    "pressure": r.pressure,
                    "renewal_rate": r.renewal_rate,
                }
                for r in records
                if r.pressure in ("high", "medium")
            ],
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
        override_pressure=_load_override_pressure(gov_dir),
    )


# ---------------------------------------------------------------------------
# Renderers — dumb formatters, no computation, no loader calls
# ---------------------------------------------------------------------------

def render_json(rollup: StatusRollup) -> str:
    """Render rollup as JSON string. Pure formatting."""
    return json.dumps(rollup.to_dict(), indent=2)


def render_text(rollup: StatusRollup) -> str:
    """Render rollup as findings-first text. Pure formatting.

    Format: top-line state, compact state summary, findings, next actions,
    details pointer.  OK checks are suppressed.
    """
    from .operator_snapshot import classify_rollup, count_checks, classify_overall_state

    checks = classify_rollup(rollup)
    counts = count_checks(checks)
    state = classify_overall_state(counts)

    lines: list[str] = []
    lines.append(f"Governor: {state}")
    lines.append("")

    # Compact state line — the 4 most important subsystem modes
    env_mode = rollup.envelope.get("mode", "?") if rollup.envelope["ok"] else "err"
    regime = (rollup.regime.get("name", "?").upper()
              if rollup.regime["ok"] else "err")
    drift = rollup.drift.get("alert_level", "?") if rollup.drift["ok"] else "err"
    scars_health = rollup.scars.get("health", "?") if rollup.scars["ok"] else "err"
    lines.append(
        f"  envelope={env_mode}  regime={regime}"
        f"  drift={drift}  scars={scars_health}"
    )
    lines.append("")

    findings = [c for c in checks if c.status != "ok"]

    if not findings:
        lines.append("  No findings.")
    else:
        _sev = {"error": 0, "warn": 1, "info": 2}
        lines.append("  Findings:")
        for c in sorted(findings, key=lambda x: _sev.get(x.status, 3)):
            glyph = {"error": "[err]", "warn": "[WARN]", "info": "[info]"
                      }.get(c.status, "[info]")
            summary = c.summary if len(c.summary) <= 50 else c.summary[:49] + "\u2026"
            lines.append(f"    {glyph:>6} {c.name}: {summary}")

        # Next actions (deduplicated, from error/warn findings only)
        next_cmds: list[str] = []
        for c in sorted(findings, key=lambda x: _sev.get(x.status, 3)):
            if c.status in ("error", "warn"):
                for cmd in c.next_commands[:1]:
                    if cmd not in next_cmds:
                        next_cmds.append(cmd)

        if next_cmds:
            lines.append("")
            lines.append("  Next:")
            for cmd in next_cmds[:3]:
                lines.append(f"    {cmd}")

    lines.append("")
    lines.append("  Details: governor status --json")

    return "\n".join(lines)


def render_bare(rollup: StatusRollup) -> str:
    """Render rollup as a minimal "what now" summary. Pure formatting.

    Three sections max: state line, top 2 findings, one next command.
    For the bare ``governor`` invocation — one finger, one button.
    """
    from .operator_snapshot import classify_rollup, count_checks, classify_overall_state

    checks = classify_rollup(rollup)
    counts = count_checks(checks)
    state = classify_overall_state(counts)

    lines: list[str] = []
    lines.append(f"Governor: {state}")

    findings = [c for c in checks if c.status != "ok"]

    if not findings:
        lines.append("No findings.")
        lines.append("")
        lines.append("  governor status --full")
    else:
        _sev = {"error": 0, "warn": 1, "info": 2}
        ranked = sorted(findings, key=lambda x: _sev.get(x.status, 3))

        for c in ranked[:2]:
            glyph = {"error": "[err]", "warn": "[WARN]", "info": "[info]"
                      }.get(c.status, "[info]")
            summary = c.summary if len(c.summary) <= 50 else c.summary[:49] + "\u2026"
            lines.append(f"  {glyph:>6} {c.name}: {summary}")

        # One next command — from the highest-severity finding
        for c in ranked:
            if c.status in ("error", "warn") and c.next_commands:
                lines.append("")
                lines.append(f"  {c.next_commands[0]}")
                break
        else:
            lines.append("")
            lines.append("  governor status --full")

    return "\n".join(lines)
