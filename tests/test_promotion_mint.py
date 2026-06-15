# SPDX-License-Identifier: Apache-2.0
"""P4.0b — the promotion mint: 6 acceptance criteria + 9 negative tests.

Synthetic fixtures only (the real ``max_slices=4`` trial has zero evidence on disk).
Spec: ``specs/governor/promotion-evidence.md`` § "P4.0b-prep". The fence under test:
operator basis authorizes attribution; it does not legitimize promotion and cannot cure
missing evidence — a failing predicate refuses regardless of operator basis, and a
failing operator basis refuses regardless of a clean predicate.
"""

from __future__ import annotations

from governor.basis_bundle import compute_basis_bundle_hash
from governor.clock_witness import MonotonicReading
from governor.control_baseline import ControlBaselineStore
from governor.operator_basis import OperatorBasisFacts
from governor.promotion_evidence import (
    ActivationReceipt,
    LiveSurvivalObservationReceipt,
    OperatorBasisReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
)
from governor.promotion_mint import (
    PromotionReceipt,
    mint_promotion,
    revert_promoted_baseline,
)

TUNABLE = "decomposition_size/max_slices"
ALLOWED = frozenset({TUNABLE})
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"
HORIZON = 10_000


def _reading(ns: int) -> MonotonicReading:
    return MonotonicReading(source=SRC, epoch=EPOCH, ns=ns)


def _activation(trial_id: str = "trial-1", trial_value: int = 4) -> ActivationReceipt:
    return ActivationReceipt(
        trial_id=trial_id,
        tunable_name=TUNABLE,
        trial_value=trial_value,
        prior_baseline_value=8,
        activated_at=_reading(1_000),
    )


def _obs(obs_id, *, trial_id="trial-1", ns=2_000, in_bounds=True, activation_hash=None):
    return LiveSurvivalObservationReceipt(
        trial_id=trial_id,
        observation_id=obs_id,
        observed_at=_reading(ns),
        in_bounds=in_bounds,
        activation_receipt_hash=(
            activation_hash if activation_hash is not None else _activation(trial_id).content_hash
        ),
    )


def _replay(trial_id="trial-1", *, passed=True) -> ReplayHoldoutReceipt:
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


def _operator_receipt(trial_id="trial-1", *, not_auto=True) -> OperatorBasisReceipt:
    return OperatorBasisReceipt(
        trial_id=trial_id,
        operator_actor="jbeck",
        promotion_basis="trial held in-bounds across window",
        scope="self_governance",
        explicitly_not_auto_baseline=not_auto,
    )


def _bundle(trial_id="trial-1", trial_value=4, **overrides) -> PromotionEvidenceBundle:
    base = dict(
        candidate=PromotionCandidate(trial_id=trial_id, tunable_name=TUNABLE, trial_value=trial_value),
        activation=_activation(trial_id, trial_value),
        observations=tuple(
            _obs(
                f"o{i}",
                trial_id=trial_id,
                ns=2_000 + i * 100,
                activation_hash=_activation(trial_id, trial_value).content_hash,
            )
            for i in range(3)
        ),
        replay=_replay(trial_id),
        operator_basis=_operator_receipt(trial_id),
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED,
        open_nondischarge_claim_ids=(),
        kernel_fuse_ratification_side_effect=False,
    )
    base.update(overrides)
    return PromotionEvidenceBundle(**base)


def _operator_facts(bundle, *, prior_hash=None, reviewed_ns=4_000, **overrides) -> OperatorBasisFacts:
    """A STRONG operator basis whose reviewed bundle hash == the computed consumed hash."""
    consumed = compute_basis_bundle_hash(bundle, prior_baseline_hash=prior_hash)
    base = dict(
        trial_id=bundle.candidate.trial_id,
        operator_id="jbeck",
        promotion_basis="trial held in-bounds across window",
        scope="self_governance",
        basis_bundle_hash=consumed,
        reviewed_at=_reading(reviewed_ns),
        transition_request_hash="sha256:transition",
        prior_authority_hash="sha256:prior-authority",
        evidence_bundle_hashes=(consumed,),
        reviewed_verdict="basis_reviewed",
        explicitly_not_auto_baseline=True,
    )
    base.update(overrides)
    return OperatorBasisFacts(**base)


_PROMOTE = _reading(4_500)  # strictly after reviewed_at (4_000), within HORIZON


# ============================ ACCEPTANCE (6) ===============================


def test_acc1_eligible_mints_receipt_and_baseline():
    bundle = _bundle()
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="self_governance/max_slices",
        minted_by="jbeck",
    )
    assert result.minted is True
    assert result.refusals == ()
    assert isinstance(result.receipt, PromotionReceipt)
    assert result.baseline is not None
    # The receipt binds the baseline; the baseline's admission receipt is the receipt.
    assert result.receipt.new_baseline_id == result.baseline.baseline_id
    assert result.baseline.creation_receipt_id == result.receipt.receipt_id
    assert result.receipt.evidence_count == 3


def test_acc2_baselines_diffable_and_lineage(tmp_path):
    store = ControlBaselineStore(tmp_path)
    a = mint_promotion(
        _bundle(trial_id="trial-1", trial_value=4),
        _operator_facts(_bundle(trial_id="trial-1", trial_value=4)),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="b/4",
        minted_by="jbeck",
    )
    store.put(a.baseline)
    b_bundle = _bundle(trial_id="trial-2", trial_value=5)
    b = mint_promotion(
        b_bundle,
        _operator_facts(b_bundle, prior_hash=a.baseline.baseline_id),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="b/5",
        minted_by="jbeck",
        prior_baseline=a.baseline,
    )
    store.put(b.baseline)
    # Diffable from config hashes alone; distinct ids; lineage resolves.
    assert a.baseline.baseline_id != b.baseline.baseline_id
    assert a.baseline.config_hashes != b.baseline.config_hashes
    assert b.baseline.supersedes == a.baseline.baseline_id
    assert store.get(b.baseline.supersedes).baseline_id == a.baseline.baseline_id


def test_acc3_exactly_once_idempotent(tmp_path):
    store = ControlBaselineStore(tmp_path)
    bundle = _bundle()
    kwargs = dict(
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="self_governance/max_slices",
        minted_by="jbeck",
    )
    r1 = mint_promotion(bundle, _operator_facts(bundle), **kwargs)
    r2 = mint_promotion(bundle, _operator_facts(bundle), **kwargs)
    # Identical justification ⇒ identical receipt_id and baseline_id (content-addressed).
    assert r1.receipt.receipt_id == r2.receipt.receipt_id
    assert r1.baseline.baseline_id == r2.baseline.baseline_id
    store.put(r1.baseline)
    store.put(r2.baseline)
    assert len(store.list_ids()) == 1  # re-mint did not create a second baseline


def test_acc4_ineligible_does_not_mint_prior_stays(tmp_path):
    store = ControlBaselineStore(tmp_path)
    # Stale: observations far behind the evaluation_reading, beyond horizon.
    stale = _bundle(
        observations=tuple(
            _obs(f"o{i}", ns=2_000 + i)  # default activation hash binds
            for i in range(3)
        ),
        evaluation_reading=_reading(1_000_000),  # way past horizon
    )
    result = mint_promotion(
        stale,
        _operator_facts(stale),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert result.baseline is None
    assert store.list_ids() == []  # prior baseline state untouched


def test_acc5_revert_promoted_is_supersession():
    promoted = mint_promotion(
        _bundle(),
        _operator_facts(_bundle()),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="promoted",
        minted_by="jbeck",
    ).baseline
    # A revert target standing in for the prior baseline.
    prior = mint_promotion(
        _bundle(trial_id="t-prior", trial_value=8),
        _operator_facts(_bundle(trial_id="t-prior", trial_value=8)),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="prior",
        minted_by="jbeck",
    ).baseline
    reverted = revert_promoted_baseline(
        promoted, prior, creation_receipt_id="sha256:revert-ceremony", admitted_by="jbeck"
    )
    assert reverted.supersedes == promoted.baseline_id  # new ceremony, not a silent undo
    assert reverted.creation_receipt_id == "sha256:revert-ceremony"


def test_acc6_bundle_binding_consumed_equals_reviewed():
    bundle = _bundle()
    # operator reviewed exactly the consumed bundle → binds → mint
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="b",
        minted_by="jbeck",
    )
    assert result.minted is True
    assert result.receipt.basis_bundle_hash == compute_basis_bundle_hash(bundle)


# ============================ NEGATIVE (9) =================================


def test_neg1_refuses_when_predicate_ineligible():
    # Insufficient evidence: require 5 but only 3 in-bounds observations.
    bundle = _bundle(required_count=5)
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "promotion_evidence_insufficient" in result.refusals


def test_neg2_refuses_consumed_ne_reviewed_bundle():
    bundle = _bundle()
    # Operator reviewed a DIFFERENT bundle hash than what is consumed.
    facts = _operator_facts(bundle, basis_bundle_hash="sha256:some-other-bundle")
    result = mint_promotion(
        bundle,
        facts,
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "operator_basis_bundle_mismatch" in result.refusals


def test_neg3_bundle_hash_excludes_operator_basis():
    with_ob = _bundle(operator_basis=_operator_receipt())
    without_ob = _bundle(operator_basis=None)
    assert compute_basis_bundle_hash(with_ob) == compute_basis_bundle_hash(without_ob)


def test_neg4_bundle_hash_excludes_clocks():
    a = _bundle(evaluation_reading=_reading(5_000))
    b = _bundle(evaluation_reading=_reading(9_999))
    assert compute_basis_bundle_hash(a) == compute_basis_bundle_hash(b)


def test_neg5_bundle_hash_order_invariant():
    obs = tuple(
        _obs(f"o{i}", ns=2_000 + i * 100, activation_hash=_activation().content_hash)
        for i in range(3)
    )
    forward = _bundle(observations=obs)
    reversed_ = _bundle(observations=tuple(reversed(obs)))
    assert compute_basis_bundle_hash(forward) == compute_basis_bundle_hash(reversed_)


def test_neg6_frozen_open_claims_is_content_and_blocks():
    clean = _bundle(open_nondischarge_claim_ids=())
    with_claim = _bundle(open_nondischarge_claim_ids=("claim-1",))
    # The snapshot is CONTENT: a different debt state is a different reviewed bundle.
    assert compute_basis_bundle_hash(clean) != compute_basis_bundle_hash(with_claim)
    # And an open claim blocks the mint via the predicate (recomputed at the gate).
    result = mint_promotion(
        with_claim,
        _operator_facts(with_claim),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "promotion_open_nondischarge_claim" in result.refusals


def test_neg7_slow_replay_does_not_stale_operator_basis():
    """Keeper: replay is frozen INTO the reviewed bundle (upstream), so a long replay
    does not enter the operator-review freshness window. Review fresh + observations
    fresh ⇒ mint, regardless of how long the (already-frozen) replay took."""
    bundle = _bundle()
    # Operator reviewed at 4_000, promote at 4_001 — a 1ns review window; horizon tiny.
    facts = _operator_facts(bundle, reviewed_ns=4_000)
    result = mint_promotion(
        bundle,
        facts,
        promote_reading=_reading(4_001),
        operator_review_horizon_ns=10,  # tiny review window; replay duration irrelevant
        baseline_name="b",
        minted_by="jbeck",
    )
    assert result.minted is True


def test_neg8_promoted_rollback_is_supersession_not_undo():
    promoted = mint_promotion(
        _bundle(),
        _operator_facts(_bundle()),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="promoted",
        minted_by="jbeck",
    ).baseline
    prior = mint_promotion(
        _bundle(trial_id="t-prior", trial_value=8),
        _operator_facts(_bundle(trial_id="t-prior", trial_value=8)),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="prior",
        minted_by="jbeck",
    ).baseline
    # No delete path exists on the store; revert can ONLY be a new admitted ceremony.
    assert not hasattr(ControlBaselineStore, "delete")
    reverted = revert_promoted_baseline(
        promoted, prior, creation_receipt_id="sha256:revert", admitted_by="jbeck"
    )
    assert reverted.supersedes == promoted.baseline_id


def test_neg9_mint_does_not_touch_kernel_fuse_or_ratification():
    bundle = _bundle(kernel_fuse_ratification_side_effect=True)
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "promotion_kernel_fuse_ratification_side_effect" in result.refusals


# ============== WEAK<->STRONG OPERATOR-BASIS ALIGNMENT (2026-06-15) ==============


def test_weak_is_lossy_projection_of_strong():
    """The weak receipt is a pure readout of the strong facts (no independent field).
    The canonical happy-path bundle receipt IS exactly project(strong facts)."""
    facts = _operator_facts(_bundle())
    weak = facts.project()
    assert weak.trial_id == facts.trial_id
    assert weak.operator_actor == facts.operator_id
    assert weak.promotion_basis == facts.promotion_basis
    assert weak.scope == facts.scope
    assert weak.explicitly_not_auto_baseline == facts.explicitly_not_auto_baseline
    assert weak == _operator_receipt(_bundle().candidate.trial_id)


def test_neg10_weak_strong_mismatch_refuses():
    """A hand-constructed weak shadow that satisfies the gate but does NOT match the
    strong facts the mint binds is a substitution attempt — refused. (The seam.)"""
    bundle = _bundle(
        operator_basis=OperatorBasisReceipt(
            trial_id="trial-1",
            operator_actor="someone-else",  # != strong facts operator_id "jbeck"
            promotion_basis="trial held in-bounds across window",
            scope="self_governance",
            explicitly_not_auto_baseline=True,
        )
    )
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),  # operator_id="jbeck"
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "operator_basis_weak_strong_mismatch" in result.refusals


def test_matching_weak_shadow_mints():
    """When the bundle's weak shadow IS the projection of the strong facts, the mint
    proceeds (no mismatch). Explicit positive for the alignment gate."""
    bundle = _bundle()
    facts = _operator_facts(bundle)
    bundle = _bundle(operator_basis=facts.project())  # shadow == projection
    result = mint_promotion(
        bundle,
        facts,
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="b",
        minted_by="jbeck",
    )
    assert result.minted is True
    assert "operator_basis_weak_strong_mismatch" not in result.refusals


def test_strong_present_but_no_weak_shadow_is_absent_not_mismatch():
    """No weak shadow in the bundle ⇒ the gate refuses operator-basis-ABSENT (distinct
    from mismatch). The bundle must carry the projection; strong-facts-alone do not mint."""
    bundle = _bundle(operator_basis=None)
    result = mint_promotion(
        bundle,
        _operator_facts(bundle),
        promote_reading=_PROMOTE,
        operator_review_horizon_ns=HORIZON,
        baseline_name="x",
        minted_by="jbeck",
    )
    assert result.minted is False
    assert "promotion_operator_basis_absent" in result.refusals
    assert "operator_basis_weak_strong_mismatch" not in result.refusals
