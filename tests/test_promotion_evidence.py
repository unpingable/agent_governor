# SPDX-License-Identifier: Apache-2.0
"""P4.0b-prep — promotion evidence substrate tests (refusals first).

The substrate turns the gate's *trusted* booleans (walkable / fresh /
operator_basis_present) into *checked* hash-chain + clock-witness facts. These
tests pin the refusals the operator named — missing/orphan/wrong-trial/stale
evidence, missing/failed replay, missing/auto operator basis — BEFORE the single
all-pass path. Cold-start (evidence_count=0) must still refuse.
"""

from __future__ import annotations

import pytest

from governor.clock_witness import MonotonicReading
from governor.promotion_gate import (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_EVIDENCE_STALE,
    PROMOTION_OPERATOR_BASIS_ABSENT,
    PROMOTION_REPLAY_HOLDOUT_FAILED,
    PROMOTION_REPLAY_HOLDOUT_MISSING,
    PROMOTION_VERDICT_ELIGIBLE,
    PROMOTION_VERDICT_REFUSED,
)
from governor.promotion_evidence import (
    PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO,
    ActivationReceipt,
    LiveSurvivalObservationReceipt,
    MalformedPromotionInputsError,
    OperatorBasisReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
    assemble_promotion_inputs,
    evaluate_promotion_from_evidence,
)

TUNABLE = "decomposition_size/max_slices"
ALLOWED = frozenset({TUNABLE})
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"
HORIZON = 10_000  # ns


def _reading(ns: int) -> MonotonicReading:
    return MonotonicReading(source=SRC, epoch=EPOCH, ns=ns)


def _candidate() -> PromotionCandidate:
    return PromotionCandidate(trial_id="trial-1", tunable_name=TUNABLE, trial_value=4)


def _activation() -> ActivationReceipt:
    return ActivationReceipt(
        trial_id="trial-1",
        tunable_name=TUNABLE,
        trial_value=4,
        prior_baseline_value=8,
        activated_at=_reading(1_000),
    )


def _obs(
    obs_id: str,
    *,
    trial_id: str = "trial-1",
    ns: int = 2_000,
    in_bounds: bool = True,
    activation_hash: str | None = None,
    disqualifying: tuple[str, ...] = (),
) -> LiveSurvivalObservationReceipt:
    return LiveSurvivalObservationReceipt(
        trial_id=trial_id,
        observation_id=obs_id,
        observed_at=_reading(ns),
        in_bounds=in_bounds,
        activation_receipt_hash=activation_hash
        if activation_hash is not None
        else _activation().content_hash,
        disqualifying_events=disqualifying,
    )


def _replay(*, passed: bool = True, trial_id: str = "trial-1") -> ReplayHoldoutReceipt:
    return ReplayHoldoutReceipt(
        trial_id=trial_id,
        replay_subject=TUNABLE,
        passed=passed,
        corpus_hash="sha256:cafe",
        frozen_corpus_hash="sha256:cafe",
        harness_version="replay_harness-v1",
        comparator_baseline_id="baseline-prior",
        falsification_basis="non-regression vs prior baseline",
    )


def _operator(*, not_auto: bool = True, trial_id: str = "trial-1") -> OperatorBasisReceipt:
    return OperatorBasisReceipt(
        trial_id=trial_id,
        operator_actor="jbeck",
        promotion_basis="trial held in-bounds across window",
        scope="self_governance",
        explicitly_not_auto_baseline=not_auto,
    )


def _bundle(**overrides) -> PromotionEvidenceBundle:
    base = dict(
        candidate=_candidate(),
        activation=_activation(),
        observations=(_obs("o1", ns=2_000), _obs("o2", ns=2_100), _obs("o3", ns=2_200)),
        replay=_replay(),
        operator_basis=_operator(),
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED,
        open_nondischarge_claim_ids=(),
        kernel_fuse_ratification_side_effect=False,
    )
    base.update(overrides)
    return PromotionEvidenceBundle(**base)


# --- The all-pass path: a real walked chain reaches the gate's ELIGIBLE -------


def test_full_valid_chain_is_eligible():
    result = evaluate_promotion_from_evidence(_bundle())
    assert result.eligible is True
    assert result.refusals == ()
    assert result.verdict == PROMOTION_VERDICT_ELIGIBLE


# --- Cold start preserved: empty bundle still refuses -------------------------


def test_cold_start_empty_evidence_refuses():
    bundle = _bundle(
        activation=None, observations=(), replay=None, operator_basis=None
    )
    result = evaluate_promotion_from_evidence(bundle)
    assert result.eligible is False
    assert result.verdict == PROMOTION_VERDICT_REFUSED
    # Zero observations is INSUFFICIENT + NOT_WALKABLE, NOT stale (nothing to age).
    assert PROMOTION_EVIDENCE_INSUFFICIENT in result.refusals
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in result.refusals
    assert PROMOTION_OPERATOR_BASIS_ABSENT in result.refusals
    assert PROMOTION_EVIDENCE_STALE not in result.refusals


# --- Walkability refusals (computed hash chain, not asserted) -----------------


def test_missing_activation_is_not_walkable():
    result = evaluate_promotion_from_evidence(_bundle(activation=None))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals


def test_observation_without_activation_is_not_walkable():
    # Observations present but no activation to bind to.
    result = evaluate_promotion_from_evidence(
        _bundle(activation=None, observations=(_obs("o1"),))
    )
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals


def test_observation_for_wrong_trial_is_not_walkable():
    wrong = _obs("o-wrong", trial_id="trial-OTHER")
    result = evaluate_promotion_from_evidence(_bundle(observations=(wrong,)))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals


def test_observation_with_orphan_hash_is_not_walkable():
    # The binding claim is a string the caller could lie about — it is CHECKED.
    orphan = _obs("o-orphan", activation_hash="sha256:not-the-activation")
    result = evaluate_promotion_from_evidence(_bundle(observations=(orphan,)))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in result.refusals


# --- Count / freshness refusals ----------------------------------------------


def test_insufficient_in_bounds_observations_is_insufficient():
    # Three observations, but two are out of bounds → only 1 counts, N=3.
    obs = (
        _obs("o1"),
        _obs("o2", in_bounds=False),
        _obs("o3", disqualifying=("rollback_trigger_fired",)),
    )
    result = evaluate_promotion_from_evidence(_bundle(observations=obs))
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_INSUFFICIENT in result.refusals


def test_stale_observation_is_stale():
    # Observation far older than the horizon relative to evaluation_reading.
    stale = _obs("o-stale", ns=2_000)
    result = evaluate_promotion_from_evidence(
        _bundle(
            observations=(stale,),
            required_count=1,
            evaluation_reading=_reading(2_000 + HORIZON + 1),
        )
    )
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_STALE in result.refusals


def test_incompatible_clock_basis_cannot_witness_freshness():
    # Observation on a different epoch (e.g. a reboot) cannot be proven fresh.
    other_epoch = LiveSurvivalObservationReceipt(
        trial_id="trial-1",
        observation_id="o-epoch",
        observed_at=MonotonicReading(source=SRC, epoch="boot:OTHER", ns=2_000),
        in_bounds=True,
        activation_receipt_hash=_activation().content_hash,
    )
    result = evaluate_promotion_from_evidence(
        _bundle(observations=(other_epoch,), required_count=1)
    )
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_STALE in result.refusals


# --- Replay/holdout refusals (separate witness, never folded) -----------------


def test_missing_replay_is_refused():
    result = evaluate_promotion_from_evidence(_bundle(replay=None))
    assert result.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in result.refusals


def test_replay_for_wrong_trial_counts_as_missing():
    result = evaluate_promotion_from_evidence(
        _bundle(replay=_replay(trial_id="trial-OTHER"))
    )
    assert result.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in result.refusals


def test_failed_replay_is_refused():
    result = evaluate_promotion_from_evidence(_bundle(replay=_replay(passed=False)))
    assert result.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_FAILED in result.refusals


# --- Operator basis refusals (incl. the red-line auto-promote fence) ---------


def test_missing_operator_basis_is_absent():
    result = evaluate_promotion_from_evidence(_bundle(operator_basis=None))
    assert result.eligible is False
    assert PROMOTION_OPERATOR_BASIS_ABSENT in result.refusals


def test_operator_basis_wrong_trial_is_absent():
    result = evaluate_promotion_from_evidence(
        _bundle(operator_basis=_operator(trial_id="trial-OTHER"))
    )
    assert result.eligible is False
    assert PROMOTION_OPERATOR_BASIS_ABSENT in result.refusals


def test_operator_basis_claiming_auto_promote_is_refused():
    """The red line: an operator basis asserting auto-promotion is not a valid
    basis. This is the one refusal the gate cannot express."""
    result = evaluate_promotion_from_evidence(
        _bundle(operator_basis=_operator(not_auto=False))
    )
    assert result.eligible is False
    assert PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO in result.refusals


# --- The never-folded property holds end-to-end ------------------------------


def test_perfect_replay_does_not_rescue_missing_live_evidence():
    result = evaluate_promotion_from_evidence(
        _bundle(observations=())  # no live evidence; replay perfect
    )
    assert result.eligible is False
    assert PROMOTION_EVIDENCE_INSUFFICIENT in result.refusals


def test_perfect_live_does_not_rescue_missing_replay():
    result = evaluate_promotion_from_evidence(_bundle(replay=None))
    assert result.eligible is False
    assert PROMOTION_REPLAY_HOLDOUT_MISSING in result.refusals


# --- Walkability is a COMPUTED hash, demonstrated -----------------------------


def test_observation_hash_binds_to_computed_activation_hash():
    # The good observations in _bundle() use _activation().content_hash; assert
    # that is genuinely the activation's content hash (not a magic string).
    act = _activation()
    obs = _obs("o1")
    assert obs.activation_receipt_hash == act.content_hash
    # And a one-field change to the activation changes the hash (content-addressed).
    mutated = ActivationReceipt(
        trial_id="trial-1",
        tunable_name=TUNABLE,
        trial_value=5,  # changed
        prior_baseline_value=8,
        activated_at=_reading(1_000),
    )
    assert mutated.content_hash != act.content_hash


# --- Construction discipline --------------------------------------------------


def test_malformed_bundle_required_count_refused_at_construction():
    with pytest.raises(MalformedPromotionInputsError):
        _bundle(required_count=0)


def test_observation_with_empty_binding_hash_refused_at_construction():
    with pytest.raises(MalformedPromotionInputsError):
        LiveSurvivalObservationReceipt(
            trial_id="trial-1",
            observation_id="o1",
            observed_at=_reading(2_000),
            in_bounds=True,
            activation_receipt_hash="",
        )
