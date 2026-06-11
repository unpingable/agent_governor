# SPDX-License-Identifier: Apache-2.0
"""Refused-spend show surface — the demo's Act-1 contrast (one incident, two
descents of the same gauntlet).

W1 item 3. This is the depth surface, distinct from `drill_poster` (the breadth
surface, the seven-invocation gauntlet). The launch demo is "one incident, three
descents (Columbo, not Jobs)" — NOT seven demos. This renders the first descent:
the **two-clock temporal lapse**, the demo's hero specimen.

Two actions run the IDENTICAL gauntlet (same standing observed at t=40, horizon
t=50, admitting wicket); they differ only in *when the spend is attempted*:

  * the legitimate twin (exercise t=45, within horizon) traverses standing →
    wicket → standing-spendability → LA grant → LA consume and **spends cleanly**
    — a system that only says no is a brick;
  * the impostor (exercise t=51, one second past the horizon) reaches the
    standing-spendability gate with valid, verified standing and is **refused**,
    the receipt naming the exact custody distinction (standing was checked; it
    lapsed in the gap) and showing both clocks and the gap.

Good-looking is not admissible: the credential was valid, the standing verified,
the operation admitted — and custody refused anyway, one second past a horizon,
because freshness is judged against an attested clock, not assumed from a valid
credential.

Scope (mirrors `drill_poster`'s discipline): display-only + integrity assertions.
No LLM, no clock, no network, no dashboard. Deterministic plain text + a JSON
envelope. The receipts carry it; prose is minimal and connective. The framing
HEADLINE is provisional launch copy — operator-ratifiable, not micro-frozen like
the codex-ratified poster vocabulary.

The integrity tripwire is load-bearing (launch plan): the impostor must refuse for
the RIGHT reason (the temporal lapse at the standing-spendability seam, spending
no capacity), never for a wrong one (a hidden BA3 short-circuit, a different seam,
or a worse credential). The assertions below are that tripwire.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from governor.drill_runner import (
    SCENARIO_TEMPORAL_LAPSE,
    SCENARIO_TEMPORAL_LAPSE_TWIN,
    DrillRunResult,
    run_drill,
)
from governor.proof_seam import cite, render_proof_seam

# Provisional framing copy (operator-ratifiable — NOT micro-frozen).
HEADER = "Agent Governor — A Stale Yes"
INCIDENT = "Incident: WAL bloat review — DRILL"
BANNER_RULE = "═"
DIVIDER_RULE = "─"

# The gauntlet hops, in order, for the per-action receipt render.
_SEAM_ORDER = (
    ("standing_seam", "standing", "verified"),
    ("wicket_seam", "wicket", "admitted"),
    ("standing_spendability_seam", "spendability", "judged"),
    ("la_seam_request", "LA grant", "granted"),
    ("la_seam_consume", "LA consume", "effect"),
)


@dataclass
class RefusedSpendAggregate:
    """Both runs + the integrity assertions."""

    twin: Optional[DrillRunResult] = None
    impostor: Optional[DrillRunResult] = None
    assertions: list[tuple[str, bool, str]] = field(default_factory=list)
    aggregate_ok: bool = True


def run_contrast(*, root: Path, now: int = 0) -> RefusedSpendAggregate:
    """Run the legitimate twin and the impostor against fresh subdirs."""
    agg = RefusedSpendAggregate()
    twin_dir = root / "twin"
    impostor_dir = root / "impostor"
    twin_dir.mkdir(parents=True, exist_ok=True)
    impostor_dir.mkdir(parents=True, exist_ok=True)
    agg.twin = run_drill(
        gov_dir=twin_dir, scenario=SCENARIO_TEMPORAL_LAPSE_TWIN, now=now
    )
    agg.impostor = run_drill(
        gov_dir=impostor_dir, scenario=SCENARIO_TEMPORAL_LAPSE, now=now
    )
    _evaluate_integrity(agg)
    return agg


def _evaluate_integrity(agg: RefusedSpendAggregate) -> None:
    """The load-bearing tripwire: the impostor refused for the RIGHT reason,
    spent no capacity, ran the same gauntlet as the twin, and neither run is
    operational (simulated evidence fenced)."""
    twin, imp = agg.twin, agg.impostor
    a = agg.assertions

    # 1. Impostor refused at the standing-spendability seam with the temporal
    #    kind — not a different seam, not a hidden short-circuit.
    a.append((
        "impostor refused at standing_spendability_seam "
        "(standing_before_spendability_not_bounded)",
        imp is not None
        and imp.outcome == "refused"
        and imp.refusal_kind == "standing_before_spendability_not_bounded"
        and imp.refusing_seam == "standing_spendability_seam",
        "" if imp else "no impostor run",
    ))

    # 2. Impostor spent NO capacity — the lapse neither cost budget nor snuck
    #    through. (Right-reason tripwire: a refusal that already consumed would
    #    be the universe's favorite irony.)
    a.append((
        "impostor spent no capacity (effect_count=0; LA never invoked)",
        imp is not None
        and imp.effect_count == 0
        and imp.downstream_call_counts.get("la_consume", 0) == 0,
        "" if imp else "no impostor run",
    ))

    # 3. The twin spent cleanly — a system that only says no is a brick.
    a.append((
        "legitimate twin consumed (effect_count=1)",
        twin is not None and twin.outcome == "consumed" and twin.effect_count == 1,
        "" if twin else "no twin run",
    ))

    # 4. IDENTICAL gauntlet: both verified standing and were admitted by wicket;
    #    they diverge ONLY at the spendability gate. This is the proof that the
    #    refusal is about the clock, not a worse credential.
    same_gauntlet = (
        twin is not None
        and imp is not None
        and twin.downstream_call_counts.get("standing_verify", 0) == 1
        and twin.downstream_call_counts.get("wicket_check", 0) == 1
        and imp.downstream_call_counts.get("standing_verify", 0) == 1
        and imp.downstream_call_counts.get("wicket_check", 0) == 1
    )
    a.append((
        "twin and impostor ran the identical gauntlet "
        "(both verified standing + admitted; diverge only at the clock)",
        same_gauntlet,
        "",
    ))

    # 5. Both are origin_mode=drill → neither is operational. Running this demo
    #    cannot mint a spendable/operational receipt (the fence holds here too).
    a.append((
        "both runs non-operational (origin_mode=drill; simulated evidence fenced)",
        twin is not None
        and imp is not None
        and twin.chain_result.operational is False
        and imp.chain_result.operational is False,
        "",
    ))

    # 6. The refusal receipt carries both clocks and the gap (the Columbo beat
    #    is backed by a real block, with a mandatory clock_basis).
    block = imp.spendability_block if imp else None
    a.append((
        "refusal receipt carries both clocks + the gap + an attested clock_basis",
        isinstance(block, dict)
        and block.get("clock_basis")
        and "gap" in block
        and "standing_observed_at" in block
        and "exercise_at" in block,
        "" if block else "no spendability block on impostor",
    ))

    agg.aggregate_ok = all(ok for _, ok, _ in a)


def _leaf(res: Optional[DrillRunResult]) -> str:
    if not res or not res.receipt_ids:
        return "(no-receipt)"
    rid = res.receipt_ids[-1]
    return f"ag_rcpt_{rid[:16]}"


def render_surface(agg: RefusedSpendAggregate) -> str:
    """Deterministic, receipt-forward contrast. No LLM; every byte derives from
    the two runs."""
    twin, imp = agg.twin, agg.impostor
    out: list[str] = []
    rule = BANNER_RULE * 70
    out.append(rule)
    out.append(f"  {HEADER}")
    out.append(f"  {INCIDENT}")
    out.append(rule)
    out.append("")
    out.append(
        "  Two actions, one gauntlet. Same standing, observed at t=40 "
        "(horizon t=50)."
    )
    out.append("  Only the spend time differs.")
    out.append("")

    # Legitimate twin.
    out.append(DIVIDER_RULE * 70)
    out.append("  LEGITIMATE  —  exercise at t=45, within horizon")
    out.append(DIVIDER_RULE * 70)
    if twin is not None:
        for _, label, verb in _SEAM_ORDER:
            out.append(f"    {label:<14} {verb}")
        out.append(f"    {'leaf receipt':<14} {_leaf(twin)}")
        out.append(
            "    → consumed. Fresh standing spent cleanly "
            f"(effect_count={twin.effect_count})."
        )
    out.append("")

    # Impostor.
    out.append(DIVIDER_RULE * 70)
    out.append("  IMPOSTOR  —  exercise at t=51, one second past the horizon")
    out.append(DIVIDER_RULE * 70)
    if imp is not None:
        out.append(f"    {'standing':<14} verified      ← the credential WAS valid")
        out.append(f"    {'wicket':<14} admitted      ← naive auth says yes here")
        out.append(f"    {'spendability':<14} REFUSED       {imp.refusal_kind}")
        block = imp.spendability_block or {}
        out.append(
            f"      standing_observed_at={block.get('standing_observed_at')}  "
            f"exercise_at={block.get('exercise_at')}  "
            f"horizon_expires_at={block.get('horizon_expires_at')}"
        )
        out.append(
            f"      gap=+{block.get('gap')}s  "
            f"standing_model_age={block.get('standing_observed_model_age')}s  "
            f"clock_basis={block.get('clock_basis')}"
        )
        out.append(f"    {'leaf receipt':<14} {_leaf(imp)}")
        out.append(
            "    → refused. No capacity spent "
            f"(effect_count={imp.effect_count}). The standing was checked —"
        )
        out.append(
            "      it lapsed in the gap between observation and exercise."
        )
    out.append("")
    out.append(
        "  One second past a horizon, and custody is the only layer that saw it."
    )
    out.append("")

    # Integrity.
    out.append(DIVIDER_RULE * 70)
    out.append("  Integrity (it refused for the right reason)")
    out.append(DIVIDER_RULE * 70)
    for label, ok, detail in agg.assertions:
        glyph = "✓" if ok else "✗"
        out.append(f"  {glyph} {label}")
        if not ok and detail:
            out.append(f"      detail: {detail}")
    out.append("")

    # Act 3 — necessity. The refusal is not a discretionary policy denial; it is
    # the refusal the kernel licenses. The theorem proves the CLASS; the receipt
    # above proves the INSTANCE; this citation is the link (derived from the
    # receipt's refusal_kind, not stored on it).
    out.append(DIVIDER_RULE * 70)
    out.append("  Necessity (why this refusal is required, not chosen)")
    out.append(DIVIDER_RULE * 70)
    if imp is not None and imp.refusal_kind:
        out.extend(render_proof_seam(imp.refusal_kind))
    out.append("")
    return "\n".join(out) + "\n"


def build_json_envelope(agg: RefusedSpendAggregate, surface: str) -> dict[str, Any]:
    def proj(res: Optional[DrillRunResult]) -> dict[str, Any]:
        if res is None:
            return {}
        return {
            "scenario": res.scenario,
            "outcome": res.outcome,
            "refusal_kind": res.refusal_kind,
            "refusing_seam": res.refusing_seam,
            "effect_count": res.effect_count,
            "operational": res.chain_result.operational,
            "leaf_receipt_id": res.receipt_ids[-1] if res.receipt_ids else None,
            "spendability_block": res.spendability_block,
        }

    imp = agg.impostor
    ref = cite(imp.refusal_kind) if imp and imp.refusal_kind else None
    proof_seam = (
        {
            "refusal_kind": imp.refusal_kind,
            "lean_module": ref.lean_module,
            "theorem_name": ref.theorem_name,
            "location": ref.location,
            "custody_class": ref.custody_class,
            "statement": ref.statement,
            "proves": ref.proves,
            "match_strength": ref.match_strength,
            "is_load_bearing": ref.is_load_bearing,
        }
        if ref is not None
        else None
    )
    return {
        "surface": surface,
        "aggregate_ok": agg.aggregate_ok,
        "twin": proj(agg.twin),
        "impostor": proj(agg.impostor),
        "proof_seam": proof_seam,
        "assertions": [
            {"label": label, "ok": ok, "detail": detail}
            for label, ok, detail in agg.assertions
        ],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m governor.demo_refused_spend",
        description=(
            "Refused-spend show surface — the demo's Act-1 temporal-lapse "
            "contrast. Runs the legitimate twin and the impostor, renders the "
            "receipt contrast, asserts the integrity tripwire. Exits nonzero "
            "if any integrity assertion fails."
        ),
    )
    parser.add_argument("--root", required=True, type=Path,
                        help="Root dir; each run writes receipts under {root}/<run>/.")
    parser.add_argument("--now", type=int, default=0,
                        help="Deterministic 'now' forwarded to the LA stubs.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    args.root.mkdir(parents=True, exist_ok=True)

    agg = run_contrast(root=args.root, now=args.now)
    surface = render_surface(agg)
    if args.format == "text":
        sys.stdout.write(surface)
    else:
        json.dump(build_json_envelope(agg, surface), sys.stdout,
                  sort_keys=True, indent=2)
        sys.stdout.write("\n")
    return 0 if agg.aggregate_ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
