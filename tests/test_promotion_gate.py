# SPDX-License-Identifier: Apache-2.0
"""P4.0a promotion-eligibility gate — refusal-first tests.

Checkpoint 1 (RATIFIED 2026-06-13): promotion requires a DUAL gate — a live
survival witness AND a replay/holdout falsification witness, never folded. The
gate's only verb is refuse; these tests pin the refusals first, then the single
all-pass path, then the never-folded property.
"""

from __future__ import annotations

import pytest

from governor.promotion_gate import (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_EVIDENCE_STALE,
    PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT,
    PROMOTION_OFF_SURFACE_TUNABLE,
    PROMOTION_OPEN_NONDISCHARGE_CLAIM,
    PROMOTION_OPERATOR_BASIS_ABSENT,
    PROMOTION_REFUSAL_KINDS,
    PROMOTION_REPLAY_CORPUS_HASH_MISMATCH,
    PROMOTION_REPLAY_HARNESS_NOT_WALKABLE,
    PROMOTION_REPLAY_HOLDOUT_FAILED,
    PROMOTION_REPLAY_HOLDOUT_MISSING,
    PROMOTION_VERDICT_ELIGIBLE,
    PROMOTION_VERDICT_REFUSED,
    LiveSurvivalWitness,
    MalformedPromotionInputsError,
    PromotionInputs,
    ReplayHoldoutVerdict,
    evaluate_promotion_eligibility,
)

ALLOWED = frozenset({"decomposition_size/max_slices"})


def _good_live() -> LiveSurvivalWitness:
    return LiveSurvivalWitness(
        evidence_count=5,
        required_count=3,
        fresh=True,
        walkable_from_activation=True,
    )


def _good_replay() -> ReplayHoldoutVerdict:
    return ReplayHoldoutVerdict(
        passed=True,
        corpus_hash="sha256:cafe",
        frozen_corpus_hash="sha256:cafe",
        harness_version="replay_harness-v1",
        comparator_baseline_id="baseline-prior",
    )


def _inputs(**overrides) -> PromotionInputs:
    base = dict(
        live=_good_live(),
        replay=_good_replay(),
        open_nondischarge_claim_ids=(),
        promoted_tunables=("decomposition_size/max_slices",),
        allowed_tunable_surface=ALLOWED,
        kernel_fuse_ratification_side_effect=False,
        operator_basis_present=True,
    )
    base.update(overrides)
    return PromotionInputs(**base)


# --- The all-pass path (exactly one) -----------------------------------------


def test_all_witnesses_pass_is_eligible():
    result = evaluate_promotion_eligibility(_inputs())
    assert result.eligible is True
    assert result.refusals == ()
    assert result.verdict == PROMOTION_VERDICT_ELIGIBLE


# --- Operator's first named refusal: live passes, replay receipt missing -----


def test_evidence_sufficient_but_no_replay_receipt_is_refused():
    """evidence_count >= N but no replay/holdout receipt => promotion refused,
    prior baseline unchanged (the gate grants nothing)."""
    result = evaluate_promotion_eligibility(_inputs(replay=None))
    assert result.eligible is False
    assert result.verdict == PROMOTION_VERDICT_REFUSED
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in result.refusals


# --- Replay witness refusals --------------------------------------------------


def test_replay_failed_is_refused():
    replay = ReplayHoldoutVerdict(
        passed=False,
        corpus_hash="sha256:cafe",
        frozen_corpus_hash="sha256:cafe",
        harness_version="replay_harness-v1",
        comparator_baseline_id="baseline-prior",
    )
    result = evaluate_promotion_eligibility(_inputs(replay=replay))
    assert result.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_FAILED in result.refusals


def test_replay_corpus_hash_mismatch_is_refused():
    replay = ReplayHoldoutVerdict(
        passed=True,
        corpus_hash="sha256:beef",
        frozen_corpus_hash="sha256:cafe",
        harness_version="replay_harness-v1",
        comparator_baseline_id="baseline-prior",
    )
    result = evaluate_promotion_eligibility(_inputs(replay=replay))
    assert result.eligible is False
    assert PROMOTION_REPLAY_CORPUS_HASH_MISMATCH in result.refusals


def test_replay_harness_not_walkable_is_refused():
    replay = ReplayHoldoutVerdict(
        passed=True,
        corpus_hash="sha256:cafe",
        frozen_corpus_hash="sha256:cafe",
        harness_version="",
        comparator_baseline_id="baseline-prior",
    )
    result = evaluate_promotion_eligibility(_inputs(replay=replay))
    assert result.eligible is False
    assert PROMOTION_REPLAY_HARNESS_NOT_WALKABLE in result.refusals


# --- Live survival witness refusals ------------------------------------------


def test_insufficient_evidence_is_refused():
    live = LiveSurvivalWitness(
        evidence_count=2, required_count=3, fresh=True, walkable_from_activation=True
    )
    result = evaluate_promotion_eligibility(_inputs(live=live))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_INSUFFICIENT in result.refusals


def test_stale_evidence_is_refused():
    live = LiveSurvivalWitness(
        evidence_count=5, required_count=3, fresh=False, walkable_from_activation=True
    )
    result = evaluate_promotion_eligibility(_inputs(live=live))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_STALE in result.refusals


def test_non_walkable_evidence_is_refused():
    live = LiveSurvivalWitness(
        evidence_count=5, required_count=3, fresh=True, walkable_from_activation=False
    )
    result = evaluate_promotion_eligibility(_inputs(live=live))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals


# --- Structural / authority refusals -----------------------------------------


def test_open_nondischarge_claim_is_refused():
    result = evaluate_promotion_eligibility(
        _inputs(open_nondischarge_claim_ids=("claim-self_governance-1",))
    )
    assert result.eligible is False
    assert PROMOTION_OPEN_NONDISCHARGE_CLAIM in result.refusals


def test_off_surface_tunable_is_refused():
    result = evaluate_promotion_eligibility(
        _inputs(promoted_tunables=("decomposition_size/max_slices", "refusal_rate_cap"))
    )
    assert result.eligible is False
    assert PROMOTION_OFF_SURFACE_TUNABLE in result.refusals


def test_unlisted_single_tunable_is_off_surface():
    result = evaluate_promotion_eligibility(
        _inputs(promoted_tunables=("some_other_knob",))
    )
    assert result.eligible is False
    assert PROMOTION_OFF_SURFACE_TUNABLE in result.refusals


def test_kernel_fuse_ratification_side_effect_is_refused():
    result = evaluate_promotion_eligibility(
        _inputs(kernel_fuse_ratification_side_effect=True)
    )
    assert result.eligible is False
    assert PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT in result.refusals


def test_absent_operator_basis_is_refused():
    result = evaluate_promotion_eligibility(_inputs(operator_basis_present=False))
    assert result.eligible is False
    assert PROMOTION_OPERATOR_BASIS_ABSENT in result.refusals


# --- The never-folded property -----------------------------------------------


def test_two_witnesses_never_folded_replay_does_not_rescue_live():
    """A perfect replay witness cannot rescue a failed live witness, and vice
    versa — the two are scored independently."""
    # Live fails (insufficient), replay perfect.
    live_fail = LiveSurvivalWitness(
        evidence_count=0, required_count=3, fresh=True, walkable_from_activation=True
    )
    r1 = evaluate_promotion_eligibility(_inputs(live=live_fail))
    assert r1.eligible is False
    assert PROMOTION_EVIDENCE_INSUFFICIENT in r1.refusals

    # Replay fails (missing), live perfect.
    r2 = evaluate_promotion_eligibility(_inputs(replay=None))
    assert r2.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in r2.refusals


def test_dual_failures_do_not_collapse():
    """Multiple independent failures all surface — refusal kinds never collapse to
    a single 'not eligible'."""
    live = LiveSurvivalWitness(
        evidence_count=0, required_count=3, fresh=False, walkable_from_activation=False
    )
    result = evaluate_promotion_eligibility(
        _inputs(live=live, replay=None, operator_basis_present=False)
    )
    assert result.eligible is False
    for kind in (
        PROMOTION_EVIDENCE_INSUFFICIENT,
        PROMOTION_EVIDENCE_STALE,
        PROMOTION_EVIDENCE_NOT_WALKABLE,
        PROMOTION_REPLAY_HOLDOUT_MISSING,
        PROMOTION_OPERATOR_BASIS_ABSENT,
    ):
        assert kind in result.refusals
    # Refusals are ordered and unique.
    assert len(result.refusals) == len(set(result.refusals))


# --- Vocabulary + construction discipline ------------------------------------


def test_all_emitted_refusals_are_in_closed_vocabulary():
    live = LiveSurvivalWitness(
        evidence_count=0, required_count=3, fresh=False, walkable_from_activation=False
    )
    result = evaluate_promotion_eligibility(
        _inputs(
            live=live,
            replay=None,
            open_nondischarge_claim_ids=("c1",),
            promoted_tunables=("x", "y"),
            kernel_fuse_ratification_side_effect=True,
            operator_basis_present=False,
        )
    )
    assert set(result.refusals) <= PROMOTION_REFUSAL_KINDS


def test_malformed_inputs_refused_at_construction():
    with pytest.raises(MalformedPromotionInputsError):
        LiveSurvivalWitness(
            evidence_count=-1, required_count=3, fresh=True, walkable_from_activation=True
        )
    with pytest.raises(MalformedPromotionInputsError):
        LiveSurvivalWitness(
            evidence_count=5, required_count=0, fresh=True, walkable_from_activation=True
        )
