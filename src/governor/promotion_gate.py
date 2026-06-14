# SPDX-License-Identifier: Apache-2.0
"""P4 promotion-eligibility gate (P4.0a) — the dual-witness refusal predicate.

Ratified entry, Checkpoint 1 (2026-06-13, crosswalk divergence #2): promoting a
surviving annealing trial value (e.g. ``max_slices=4``) into a named
``ControlBaseline`` requires a **dual gate**. Two witnesses, evaluated
independently and **never folded into one** — different epistemology, different
receipt:

  * **live survival witness** — did the trial survive *reality*? ``evidence_count
    >= N`` of in-bounds, FRESH, walkable-from-activation observation receipts
    (scars-style count, never wall-clock).
  * **replay/holdout falsification witness** — does promotion avoid *known
    regression*? A Phase C1 ``REPLAY_HARNESS`` non-regression pass against a
    FROZEN corpus, carrying its own ``ReplayHoldoutReceipt`` (frozen corpus hash,
    harness version, comparator baseline id, verdict). Scoped strictly as a
    *promotion falsification gate* — not a tuning optimizer, not a selection
    surface. No post-hoc case selection, no mutation on failure, no claim that
    replay proves optimality.

**This module is P4.0a: substrate-agnostic and pure.** The gate's only verb is
*refuse* — it grants nothing, mints nothing, performs no IO — so it is safe to
build before the receipt substrate (Checkpoint 2, convergence_tuning disposition)
is decided. Minting the ``ControlBaseline`` on an eligible verdict, and emitting a
receipt on both paths, is **P4.0b** (gated on Checkpoint 2). This split mirrors
``standing_spendability`` (pure ``evaluate_*`` + a later gate that emits).

Design commitments inherited from the campaign:

  * **Two witnesses, never soup.** ``LiveSurvivalWitness`` and
    ``ReplayHoldoutVerdict`` are separate fields; the predicate never adds a
    replay pass into the evidence count, and a passing live witness alone does NOT
    promote.
  * **Freshness witness is upstream.** Per "witnesses expose; policy decides",
    the two-clock freshness computation lives in ``standing_spendability`` /
    ``clock_witness``; this gate consumes its *verdict* (``fresh: bool``) rather
    than re-deriving the clock math.
  * **Closed refusal vocabulary.** No stringly-typed buckets; all refusals come
    from ``PROMOTION_REFUSAL_KINDS``.
  * **Dual-failure preservation.** The predicate collects ALL failing reasons in
    canonical order — refusal kinds never collapse into a single "not eligible".

See ``working/P4-promotion-plan-2026-06-13.md`` (seven questions + predicate),
``working/crosswalk-self-governance-spec.md`` (divergence #2 resolved), and
``specs/gaps/GOV_GAP_CONTROL_BASELINE_001.md`` (Phase-4 promotion, AC5b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- Verdicts (drawn from the existing gate vocabulary; no new verdict invented) ---
PROMOTION_VERDICT_ELIGIBLE = "pass"
PROMOTION_VERDICT_REFUSED = "block"

# --- Closed refusal vocabulary -------------------------------------------------
# Live survival witness failures.
PROMOTION_EVIDENCE_INSUFFICIENT = "promotion_evidence_insufficient"
PROMOTION_EVIDENCE_STALE = "promotion_evidence_stale"
PROMOTION_EVIDENCE_NOT_WALKABLE = "promotion_evidence_not_walkable"
# Replay/holdout falsification witness failures (a separate witness — never folded).
PROMOTION_REPLAY_HOLDOUT_MISSING = "promotion_replay_holdout_missing"
PROMOTION_REPLAY_HOLDOUT_FAILED = "promotion_replay_holdout_failed"
PROMOTION_REPLAY_CORPUS_HASH_MISMATCH = "promotion_replay_corpus_hash_mismatch"
PROMOTION_REPLAY_HARNESS_NOT_WALKABLE = "promotion_replay_harness_not_walkable"
# Structural / authority failures.
PROMOTION_OPEN_NONDISCHARGE_CLAIM = "promotion_open_nondischarge_claim"
PROMOTION_OFF_SURFACE_TUNABLE = "promotion_off_surface_tunable"
PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT = (
    "promotion_kernel_fuse_ratification_side_effect"
)
PROMOTION_OPERATOR_BASIS_ABSENT = "promotion_operator_basis_absent"

PROMOTION_REFUSAL_KINDS = frozenset(
    {
        PROMOTION_EVIDENCE_INSUFFICIENT,
        PROMOTION_EVIDENCE_STALE,
        PROMOTION_EVIDENCE_NOT_WALKABLE,
        PROMOTION_REPLAY_HOLDOUT_MISSING,
        PROMOTION_REPLAY_HOLDOUT_FAILED,
        PROMOTION_REPLAY_CORPUS_HASH_MISMATCH,
        PROMOTION_REPLAY_HARNESS_NOT_WALKABLE,
        PROMOTION_OPEN_NONDISCHARGE_CLAIM,
        PROMOTION_OFF_SURFACE_TUNABLE,
        PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT,
        PROMOTION_OPERATOR_BASIS_ABSENT,
    }
)

# Canonical refusal ordering — stable output (live witness, then replay witness,
# then structural/authority), so dual failures surface in a predictable order.
_REFUSAL_ORDER = (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_STALE,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_REPLAY_HOLDOUT_MISSING,
    PROMOTION_REPLAY_HOLDOUT_FAILED,
    PROMOTION_REPLAY_CORPUS_HASH_MISMATCH,
    PROMOTION_REPLAY_HARNESS_NOT_WALKABLE,
    PROMOTION_OPEN_NONDISCHARGE_CLAIM,
    PROMOTION_OFF_SURFACE_TUNABLE,
    PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT,
    PROMOTION_OPERATOR_BASIS_ABSENT,
)


class MalformedPromotionInputsError(ValueError):
    """Promotion inputs were structurally malformed — e.g. a negative
    ``required_count`` or ``evidence_count``. A promotion gate cannot evaluate a
    bound it cannot read; this is refused at construction, never coerced into a
    permissive pass."""


@dataclass(frozen=True)
class LiveSurvivalWitness:
    """Did the trial survive reality? Count of in-bounds post-activation
    observation receipts, plus the upstream freshness and walkability verdicts.

    ``evidence_count`` / ``required_count`` are the scars-style count and its
    threshold N. ``fresh`` is the two-clock freshness verdict computed UPSTREAM
    (standing_spendability / clock_witness) — this gate consumes it, it does not
    re-derive clock math. ``walkable_from_activation`` asserts the evidence chains
    back to the P3.1 activation receipt.
    """

    evidence_count: int
    required_count: int
    fresh: bool
    walkable_from_activation: bool

    def __post_init__(self) -> None:
        if self.evidence_count < 0:
            raise MalformedPromotionInputsError(
                f"evidence_count must be >= 0, got {self.evidence_count}"
            )
        if self.required_count < 1:
            raise MalformedPromotionInputsError(
                f"required_count (N) must be >= 1, got {self.required_count}"
            )


@dataclass(frozen=True)
class ReplayHoldoutVerdict:
    """Does promotion avoid known regression? The separate replay/holdout witness.

    Absence of this object (``replay=None`` on the inputs) is the *missing receipt*
    refusal — a passing live witness alone does not promote. When present, all
    three structural facts must hold: ``passed`` (non-regression), ``corpus_hash``
    matches the frozen corpus recorded before evaluation, and the harness version
    is walkable (the verdict binds to a known harness).
    """

    passed: bool
    corpus_hash: str
    frozen_corpus_hash: str
    harness_version: str
    comparator_baseline_id: str

    @property
    def corpus_hash_matches_frozen(self) -> bool:
        return bool(self.corpus_hash) and self.corpus_hash == self.frozen_corpus_hash

    @property
    def harness_walkable(self) -> bool:
        return bool(self.harness_version)


@dataclass(frozen=True)
class PromotionInputs:
    """The full set of witnessed facts the promotion gate evaluates.

    These are *gate inputs* (witnessed facts), not agent-provided prose (NLAI): the
    gate evaluates them mechanically. ``replay`` is ``None`` when no replay/holdout
    receipt exists at all (→ missing-receipt refusal). ``promoted_tunables`` must be
    exactly the one allowlisted tunable for P4; anything else is off-surface.
    """

    live: LiveSurvivalWitness
    replay: Optional[ReplayHoldoutVerdict]
    open_nondischarge_claim_ids: tuple[str, ...]
    promoted_tunables: tuple[str, ...]
    allowed_tunable_surface: frozenset[str]
    kernel_fuse_ratification_side_effect: bool
    operator_basis_present: bool


@dataclass(frozen=True)
class PromotionEligibility:
    """The verdict. ``eligible`` iff ``refusals`` is empty. ``refusals`` carries
    EVERY failing reason in canonical order (dual failures never collapse)."""

    eligible: bool
    refusals: tuple[str, ...]

    @property
    def verdict(self) -> str:
        return PROMOTION_VERDICT_ELIGIBLE if self.eligible else PROMOTION_VERDICT_REFUSED


def evaluate_promotion_eligibility(inputs: PromotionInputs) -> PromotionEligibility:
    """Pure, total promotion-eligibility predicate.

    Implements the ratified ``PromotionEligible`` shape::

            live_evidence_count >= N
        AND live_receipts_fresh
        AND live_receipts_walkable_from_activation
        AND replay_holdout_non_regression_passed
        AND no_open_NonDischargeClaim
        AND no_off_surface_tunable
        AND no_kernel_fuse_ratification_side_effect
        AND operator_basis_present

    The two witnesses are evaluated independently and never folded: a passing live
    survival witness with a missing/failed replay witness is REFUSED, and vice
    versa. All failing reasons are returned (not just the first).
    """
    refusals: set[str] = set()

    # --- Live survival witness (did the trial survive reality?) ---
    live = inputs.live
    if live.evidence_count < live.required_count:
        refusals.add(PROMOTION_EVIDENCE_INSUFFICIENT)
    if not live.fresh:
        refusals.add(PROMOTION_EVIDENCE_STALE)
    if not live.walkable_from_activation:
        refusals.add(PROMOTION_EVIDENCE_NOT_WALKABLE)

    # --- Replay/holdout falsification witness (does promotion avoid regression?) ---
    # A SEPARATE witness — never folded into the evidence count above.
    replay = inputs.replay
    if replay is None:
        refusals.add(PROMOTION_REPLAY_HOLDOUT_MISSING)
    else:
        if not replay.passed:
            refusals.add(PROMOTION_REPLAY_HOLDOUT_FAILED)
        if not replay.corpus_hash_matches_frozen:
            refusals.add(PROMOTION_REPLAY_CORPUS_HASH_MISMATCH)
        if not replay.harness_walkable:
            refusals.add(PROMOTION_REPLAY_HARNESS_NOT_WALKABLE)

    # --- Structural / authority witnesses ---
    if inputs.open_nondischarge_claim_ids:
        refusals.add(PROMOTION_OPEN_NONDISCHARGE_CLAIM)
    # Off-surface: promotion must be exactly the one allowlisted tunable.
    off_surface = any(
        t not in inputs.allowed_tunable_surface for t in inputs.promoted_tunables
    )
    if off_surface or len(inputs.promoted_tunables) != 1:
        refusals.add(PROMOTION_OFF_SURFACE_TUNABLE)
    if inputs.kernel_fuse_ratification_side_effect:
        refusals.add(PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT)
    if not inputs.operator_basis_present:
        refusals.add(PROMOTION_OPERATOR_BASIS_ABSENT)

    ordered = tuple(k for k in _REFUSAL_ORDER if k in refusals)
    return PromotionEligibility(eligible=not ordered, refusals=ordered)
