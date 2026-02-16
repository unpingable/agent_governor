"""Invariant: confidence.sanity

If all claims are marked "low" confidence in factual mode, the run
is effectively "I have no idea but here's some text." That's WARN at best.

Also: high-confidence claims with only weak evidence strength → FAIL.
"""

from __future__ import annotations

from typing import Any

from receipt_kernel.invariants._helpers import get_run_mode, load_evidence_json
from receipt_kernel.types import InvariantResult, Reason, Verdict


# Evidence strength hierarchy (orthogonal to retention class).
# Strong: tool outputs, primary sources, structured measurements
# Medium: cached summaries, secondhand extracts
# Weak: model self-report, freeform text with no provenance
STRENGTH_RANK = {"strong": 3, "medium": 2, "weak": 1}


class ConfidenceSanityInvariant:
    """Verify confidence levels are sane relative to evidence strength."""

    invariant_id = "confidence.sanity"

    def __init__(self, *, require_in_modes: tuple[str, ...] = ("factual", "mixed")):
        self._modes = require_in_modes

    def evaluate(self, ctx: dict[str, Any]) -> InvariantResult:
        store = ctx.get("store")
        run_id = ctx.get("run_id")
        if store is None or not run_id:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.UNKNOWN,
                reasons=[Reason(code="CONTEXT_MISSING", msg="store/run_id not provided")],
            )

        mode = get_run_mode(store, str(run_id))
        if mode is None:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.FAIL,
                reasons=[Reason(code="RUN_MODE_MISSING", msg="RUN_START.meta.mode is required")],
            )

        if mode not in self._modes:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.PASS,
                reasons=[],
                meta={"mode": mode, "skipped": True},
            )

        claims_doc = load_evidence_json(store, str(run_id), "claims_map")
        if claims_doc is None:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.UNKNOWN,
                reasons=[Reason(code="CLAIMS_MAP_MISSING", msg="cannot verify confidence without claims_map")],
                meta={"mode": mode},
            )

        claims = claims_doc.get("claims") or []
        if not claims:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.PASS,
                reasons=[],
                meta={"mode": mode, "claim_count": 0},
            )

        reasons: list[Reason] = []
        counts = {"high": 0, "medium": 0, "low": 0, "unspecified": 0}

        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                continue
            cid = c.get("id", f"idx:{i}")
            confidence = str(c.get("confidence", "")).lower()
            if confidence in counts:
                counts[confidence] += 1
            else:
                counts["unspecified"] += 1

            # High confidence with only weak evidence strength → flag
            if confidence == "high":
                strength = str(c.get("evidence_strength", "")).lower()
                if strength and STRENGTH_RANK.get(strength, 0) < STRENGTH_RANK["medium"]:
                    reasons.append(Reason(
                        code="HIGH_CONFIDENCE_WEAK_EVIDENCE",
                        msg=f"claim {cid}: high confidence but evidence_strength={strength}",
                    ))

        # All-low in factual mode is suspect
        total = counts["high"] + counts["medium"] + counts["low"] + counts["unspecified"]
        substantive = counts["high"] + counts["medium"]
        if total > 0 and substantive == 0:
            reasons.append(Reason(
                code="ALL_LOW_CONFIDENCE",
                msg=f"all {total} claims are low/unspecified confidence in {mode} mode",
            ))

        has_high_weak = any(r.code == "HIGH_CONFIDENCE_WEAK_EVIDENCE" for r in reasons)
        has_all_low = any(r.code == "ALL_LOW_CONFIDENCE" for r in reasons)

        if has_high_weak:
            verdict = Verdict.FAIL
        elif has_all_low:
            verdict = Verdict.WARN
        elif reasons:
            verdict = Verdict.WARN
        else:
            verdict = Verdict.PASS

        return InvariantResult(
            invariant_id=self.invariant_id,
            verdict=verdict,
            reasons=reasons,
            meta={"mode": mode, "counts": counts},
        )
