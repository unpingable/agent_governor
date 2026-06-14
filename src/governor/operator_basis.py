# SPDX-License-Identifier: Apache-2.0
"""P4.0g — operator-basis witness: DERIVE operator_basis_present structurally.

The third and last promotion producer, and the obnoxious one. It must capture
"a qualified operator reviewed THIS basis bundle before THIS transition" WITHOUT
turning operator mood into evidence, and without ever becoming a promotion verdict.

> OperatorBasisReceipt does NOT establish PromotionEligible. It establishes only that
> the operator reviewed the basis bundle the promotion gate must independently evaluate.

**The seam, Lean-backed (see `working/P4.0g-operator-basis-lean-spike-2026-06-14.md`).**
A bare `operator_basis_present: bool` is *homeless*: `Bool` has nowhere to put the bundle
(`OperatorBasisGateInput.lean: bare_bool_ignores_bundle`). So `present` is **derived
structurally** from the typed pair `(consumed_bundle_hash, OperatorBasisFacts)`:

  * **pre-state binding** — `basis_bundle_hash == consumed_bundle_hash` (the operator
    reviewed exactly what is being promoted; bundle A reviewed ≠ bundle B consumed →
    refused). `AmendmentFragment` shape: witness valid in S, not S′. [annex]
  * **before-the-transition** — `reviewed_at` strictly before `promote_at`; post-hoc
    attestation does not authorize (`RetroactiveLegitimation`). [annex]
  * **fresh** — review within the horizon at promote time (`Freshness`); a stale review
    is witnessed-but-not-binding. [annex]
  * **attest ≠ propose** — the operator's `reviewed_verdict` is `basis_reviewed|refused`,
    never `eligible`; a refused or auto-claiming review is refused (`AttestationLedger`).

**Consume-relative** by nature: unlike `in_bounds`/replay-verdict (derivable from facts
alone), `operator_basis_present` needs consume-time inputs (the consumed bundle + promote
clock). That is the Lean's consumer-relativity (`no_global_section_when_consumers_disagree`)
made concrete: the stamp has no consumer-independent section. Single-rooted (AG's
qualified operator = genesis root) it is legitimate; that is the only regime P4 runs in.

Scope (P4.0g): facts/type/store + structural derivation + refusal tests + synthetic
eligible path. No `ControlBaseline` mint, no `PromotionReceipt`, no Checkpoint-3, no real
`max_slices=4` promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .clock_witness import MonotonicReading

# --- Operator's attested review verdict (an INPUT, not derived) ---------------
REVIEW_BASIS_REVIEWED = "basis_reviewed"
REVIEW_REFUSED = "refused"
REVIEW_VERDICTS = frozenset({REVIEW_BASIS_REVIEWED, REVIEW_REFUSED})

# --- Closed refusal vocabulary (why operator_basis_present is NOT derivable) ---
OPERATOR_BASIS_MISSING_BINDING = "operator_basis_missing_binding"
OPERATOR_BASIS_VERDICT_REFUSED = "operator_basis_verdict_refused"
OPERATOR_BASIS_CLAIMS_AUTO = "operator_basis_claims_auto"
OPERATOR_BASIS_BUNDLE_MISMATCH = "operator_basis_bundle_mismatch"
OPERATOR_BASIS_CLOCK_INCOMPATIBLE = "operator_basis_clock_incompatible"
OPERATOR_BASIS_POST_ATTESTATION = "operator_basis_post_attestation"
OPERATOR_BASIS_STALE = "operator_basis_stale"

OPERATOR_BASIS_REFUSAL_REASONS = frozenset(
    {
        OPERATOR_BASIS_MISSING_BINDING,
        OPERATOR_BASIS_VERDICT_REFUSED,
        OPERATOR_BASIS_CLAIMS_AUTO,
        OPERATOR_BASIS_BUNDLE_MISMATCH,
        OPERATOR_BASIS_CLOCK_INCOMPATIBLE,
        OPERATOR_BASIS_POST_ATTESTATION,
        OPERATOR_BASIS_STALE,
    }
)

# Canonical order — bindings, attestation nature, then temporal.
_REASON_ORDER = (
    OPERATOR_BASIS_MISSING_BINDING,
    OPERATOR_BASIS_VERDICT_REFUSED,
    OPERATOR_BASIS_CLAIMS_AUTO,
    OPERATOR_BASIS_BUNDLE_MISMATCH,
    OPERATOR_BASIS_CLOCK_INCOMPATIBLE,
    OPERATOR_BASIS_POST_ATTESTATION,
    OPERATOR_BASIS_STALE,
)


class MalformedOperatorBasisError(ValueError):
    """Operator-basis facts were structurally malformed (bad types / unknown review
    verdict). Refused at construction — a basis the gate cannot read is not a basis."""


def _reading_block(r: MonotonicReading) -> dict[str, Any]:
    return {"source": r.source, "epoch": r.epoch, "ns": r.ns}


@dataclass(frozen=True)
class OperatorBasisFacts:
    """What a qualified operator attested. ``reviewed_verdict`` is the operator's
    attested review (`basis_reviewed|refused`) — an INPUT, not a derived promotion
    verdict. ``basis_bundle_hash`` is the bundle the operator reviewed; at consume it
    must equal the bundle being promoted. ``reviewed_at`` is monotonic-witnessed so
    before-the-transition and freshness are checkable, not vibes.
    """

    trial_id: str
    operator_id: str
    promotion_basis: str
    scope: str
    basis_bundle_hash: str
    reviewed_at: MonotonicReading
    transition_request_hash: str
    prior_authority_hash: str
    evidence_bundle_hashes: tuple[str, ...]
    reviewed_verdict: str
    explicitly_not_auto_baseline: bool

    def __post_init__(self) -> None:
        if self.reviewed_verdict not in REVIEW_VERDICTS:
            raise MalformedOperatorBasisError(
                f"reviewed_verdict must be one of {sorted(REVIEW_VERDICTS)}, "
                f"got {self.reviewed_verdict!r}"
            )
        if not isinstance(self.explicitly_not_auto_baseline, bool):
            raise MalformedOperatorBasisError("explicitly_not_auto_baseline must be bool")
        if not isinstance(self.reviewed_at, MonotonicReading):
            raise MalformedOperatorBasisError("reviewed_at must be a MonotonicReading")
        if not isinstance(self.evidence_bundle_hashes, tuple):
            raise MalformedOperatorBasisError("evidence_bundle_hashes must be a tuple")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "operator_id": self.operator_id,
            "promotion_basis": self.promotion_basis,
            "scope": self.scope,
            "basis_bundle_hash": self.basis_bundle_hash,
            "reviewed_at": _reading_block(self.reviewed_at),
            "transition_request_hash": self.transition_request_hash,
            "prior_authority_hash": self.prior_authority_hash,
            "evidence_bundle_hashes": list(self.evidence_bundle_hashes),
            "reviewed_verdict": self.reviewed_verdict,
            "explicitly_not_auto_baseline": self.explicitly_not_auto_baseline,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OperatorBasisFacts":
        at = d["reviewed_at"]
        return cls(
            trial_id=d["trial_id"],
            operator_id=d["operator_id"],
            promotion_basis=d["promotion_basis"],
            scope=d["scope"],
            basis_bundle_hash=d["basis_bundle_hash"],
            reviewed_at=MonotonicReading(
                source=at["source"], epoch=at["epoch"], ns=at["ns"]
            ),
            transition_request_hash=d["transition_request_hash"],
            prior_authority_hash=d["prior_authority_hash"],
            evidence_bundle_hashes=tuple(d.get("evidence_bundle_hashes", ())),
            reviewed_verdict=d["reviewed_verdict"],
            explicitly_not_auto_baseline=d["explicitly_not_auto_baseline"],
        )


@dataclass(frozen=True)
class OperatorBasisVerdict:
    """Derived. ``present`` iff ``reasons`` is empty; ``reasons`` carries every failing
    reason in canonical order. ``present`` is exactly the gate's
    ``operator_basis_present`` — derived, never stamped."""

    present: bool
    reasons: tuple[str, ...]


def derive_operator_basis_present(
    facts: OperatorBasisFacts,
    *,
    consumed_bundle_hash: str,
    promote_reading: MonotonicReading,
    freshness_horizon_ns: int,
) -> OperatorBasisVerdict:
    """Pure, total, CONSUME-relative derivation of ``operator_basis_present``.

    Present iff: every binding present; the operator's review verdict is
    ``basis_reviewed`` (not refused) and not auto-claiming; the reviewed bundle equals
    the consumed bundle (pre-state binding); the review clock is compatible with the
    promote clock; the review is strictly before promote (post-attestation refused); and
    the review is fresh within the horizon. All failing reasons returned.
    """
    reasons: set[str] = set()

    if not (
        facts.operator_id
        and facts.basis_bundle_hash
        and facts.transition_request_hash
        and facts.prior_authority_hash
    ):
        reasons.add(OPERATOR_BASIS_MISSING_BINDING)

    if facts.reviewed_verdict != REVIEW_BASIS_REVIEWED:
        reasons.add(OPERATOR_BASIS_VERDICT_REFUSED)
    if not facts.explicitly_not_auto_baseline:
        reasons.add(OPERATOR_BASIS_CLAIMS_AUTO)

    # Pre-state binding: the operator reviewed exactly what is being promoted.
    if not consumed_bundle_hash or facts.basis_bundle_hash != consumed_bundle_hash:
        reasons.add(OPERATOR_BASIS_BUNDLE_MISMATCH)

    # Temporal: compatible basis, strictly-before, fresh. Same source+epoch required
    # (clock_witness discipline); we compare ns directly to distinguish the three
    # outcomes (incompatible / post-attestation / stale) instead of letting a single
    # subtraction conflate them.
    r, p = facts.reviewed_at, promote_reading
    if r.source != p.source or r.epoch != p.epoch:
        reasons.add(OPERATOR_BASIS_CLOCK_INCOMPATIBLE)
    elif r.ns >= p.ns:
        reasons.add(OPERATOR_BASIS_POST_ATTESTATION)
    elif (p.ns - r.ns) > freshness_horizon_ns:
        reasons.add(OPERATOR_BASIS_STALE)

    ordered = tuple(x for x in _REASON_ORDER if x in reasons)
    return OperatorBasisVerdict(present=not ordered, reasons=ordered)


__all__ = [
    "REVIEW_BASIS_REVIEWED",
    "REVIEW_REFUSED",
    "REVIEW_VERDICTS",
    "OPERATOR_BASIS_MISSING_BINDING",
    "OPERATOR_BASIS_VERDICT_REFUSED",
    "OPERATOR_BASIS_CLAIMS_AUTO",
    "OPERATOR_BASIS_BUNDLE_MISMATCH",
    "OPERATOR_BASIS_CLOCK_INCOMPATIBLE",
    "OPERATOR_BASIS_POST_ATTESTATION",
    "OPERATOR_BASIS_STALE",
    "OPERATOR_BASIS_REFUSAL_REASONS",
    "MalformedOperatorBasisError",
    "OperatorBasisFacts",
    "OperatorBasisVerdict",
    "derive_operator_basis_present",
]
