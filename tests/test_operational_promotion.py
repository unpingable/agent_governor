# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3c — operational promotion tests.

Evidence is written through the REAL producers to a tmp store (the 3a/3b pattern), then
``operational_promote`` runs the full act: discover → prepare → mint → durable
supersession write. The hard line under test: a baseline reaches disk ONLY through the
explicit operator-present act, and never via discovery or prepare; missing/stale/
out-of-bounds/wrong-trial/off-surface evidence refuses with ZERO writes.
"""

from __future__ import annotations

import inspect

from governor.clock_witness import MonotonicReading
from governor.control_baseline import ControlBaselineStore
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.operator_basis import REVIEW_BASIS_REVIEWED, OperatorBasisFacts
from governor import promotion_discovery, promotion_mint_input
from governor.promotion_discovery import discover_promotion_bundle
from governor.promotion_evidence import ActivationReceipt, PromotionCandidate
from governor.promotion_evidence_store import (
    ActivationReceiptStore,
    ObservationReceiptStore,
    OperatorBasisReceiptStore,
    ReplayHoldoutReceiptStore,
)
from governor.promotion_gate import (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_OFF_SURFACE_TUNABLE,
    PROMOTION_OPERATOR_BASIS_ABSENT,
)
from governor.promotion_mint import revert_promoted_baseline
from governor.promotion_mint_input import prepare_mint_input
from governor.operational_promotion import (
    OperationalPromotionOutcome,
    PromotionReceiptStore,
    operational_promote,
)
from governor.replay_holdout import ReplayHoldoutFacts

TUNABLE = "decomposition_size/max_slices"
ALLOWED = frozenset({TUNABLE})
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"
HORIZON = 10_000
BOUND = SurvivalBound(metric="refusal_rate", trip_comparator="gt", threshold=0.2)


def _reading(ns: int) -> MonotonicReading:
    return MonotonicReading(source=SRC, epoch=EPOCH, ns=ns)


def _candidate(trial_id="trial-1", trial_value=4) -> PromotionCandidate:
    return PromotionCandidate(trial_id=trial_id, tunable_name=TUNABLE, trial_value=trial_value)


def _activation(trial_id="trial-1", trial_value=4) -> ActivationReceipt:
    return ActivationReceipt(
        trial_id=trial_id, tunable_name=TUNABLE, trial_value=trial_value,
        prior_baseline_value=8, activated_at=_reading(1_000),
    )


def _populate_full(root, *, refusal_rate=0.1, operator_reviewed_at_ns=4_000, prior_baseline_hash=None):
    """Write a complete, eligible evidence corpus through the REAL producers.

    ``prior_baseline_hash`` binds the supersession lineage into the basis bundle hash, so
    the operator basis is reviewed against the SAME bundle the mint will consume (the
    operator reviews the bundle-including-lineage, not a bare one)."""
    ActivationReceiptStore(root).put(_activation())
    obs = ObservationReceiptStore(root)
    for i in range(3):
        obs.put(
            observation_id=f"o{i}",
            facts=ObservationFacts(
                trial_id="trial-1", observed_at=_reading(2_000 + i * 100),
                metrics=(("refusal_rate", refusal_rate),), disqualifying_events=(),
            ),
            bound=BOUND,
            activation_receipt_hash=_activation().content_hash,
        )
    ReplayHoldoutReceiptStore(root).put(
        ReplayHoldoutFacts(
            trial_id="trial-1", candidate_id="cand-1", comparator_baseline_id="baseline-prior",
            replay_subject=TUNABLE, replay_harness_id="nonregression_harness", harness_version="v1",
            corpus_id="corpus-A", corpus_hash="sha256:cafe", frozen_corpus_hash="sha256:cafe",
            corpus_frozen_at="2026-06-14T00:00:00Z", started_at=_reading(1_000),
            completed_at=_reading(2_000), child_exit=0, exit_observed=True,
            raw_result_hash="sha256:beef", result_non_regression=True,
        )
    )
    bbh = discover_promotion_bundle(
        root, _candidate(), required_count=3, evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON, allowed_tunable_surface=ALLOWED,
        promote_reading=_reading(4_500), operator_review_horizon_ns=HORIZON,
        prior_baseline_hash=prior_baseline_hash,
    ).basis_bundle_hash
    OperatorBasisReceiptStore(root).put(
        OperatorBasisFacts(
            trial_id="trial-1", operator_id="jbeck",
            promotion_basis="trial held in-bounds across window", scope="self_governance",
            basis_bundle_hash=bbh, reviewed_at=_reading(operator_reviewed_at_ns),
            transition_request_hash="sha256:transition", prior_authority_hash="sha256:prior",
            evidence_bundle_hashes=(bbh,), reviewed_verdict=REVIEW_BASIS_REVIEWED,
            explicitly_not_auto_baseline=True,
        )
    )


def _promote(root, *, candidate=None, baseline_name="promoted-max-slices", minted_by="jbeck", **ov):
    base = dict(
        required_count=3, evaluation_reading=_reading(5_000), freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED, promote_reading=_reading(4_500),
        operator_review_horizon_ns=HORIZON,
    )
    base.update(ov)
    return operational_promote(
        root, candidate or _candidate(), baseline_name=baseline_name, minted_by=minted_by, **base
    )


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# --- ACCEPTANCE: eligible real evidence -> persisted superseding baseline ----------


def test_eligible_real_evidence_mints_and_persists(tmp_path):
    _populate_full(tmp_path)
    out = _promote(tmp_path)
    assert isinstance(out, OperationalPromotionOutcome)
    assert out.promoted is True
    assert out.refusals == ()
    assert out.receipt is not None and out.baseline is not None
    # Persisted to durable stores.
    assert ControlBaselineStore(tmp_path).get(out.baseline.baseline_id) is not None
    assert PromotionReceiptStore(tmp_path).get(out.receipt.receipt_id) is not None
    # The baseline names the receipt; the receipt names its baseline.
    assert out.baseline.creation_receipt_id == out.receipt.receipt_id
    assert out.receipt.new_baseline_id == out.baseline.baseline_id
    assert out.receipt.minted_by == "jbeck"


def test_promotion_is_supersession_of_prior(tmp_path):
    store = ControlBaselineStore(tmp_path)
    from governor.control_baseline import admit_baseline
    prior = admit_baseline(
        name="prior", config_hashes={TUNABLE: "sha256:old"},
        creation_receipt_id="rcpt-prior", admitted_by="jbeck",
    )
    store.put(prior)
    _populate_full(tmp_path, prior_baseline_hash=prior.baseline_id)
    out = _promote(tmp_path, prior_baseline=prior)
    assert out.promoted is True
    assert out.baseline.supersedes == prior.baseline_id
    # Prior survives — supersession, not deletion.
    assert store.get(prior.baseline_id) is not None
    assert prior.baseline_id in store.list_ids()
    assert out.baseline.baseline_id in store.list_ids()


# --- ACCEPTANCE: refusals write NOTHING --------------------------------------------


def test_missing_evidence_refuses_no_write(tmp_path):
    # Empty chamber — the live-root specimen shape.
    out = _promote(tmp_path)
    assert out.promoted is False
    assert PROMOTION_EVIDENCE_NOT_WALKABLE in out.refusals
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_stale_operator_review_refuses_no_write(tmp_path):
    # Operator reviewed long before promotion; review lapses past its horizon.
    _populate_full(tmp_path, operator_reviewed_at_ns=4_000)
    out = _promote(tmp_path, promote_reading=_reading(4_000 + HORIZON + 1))
    assert out.promoted is False
    assert PROMOTION_OPERATOR_BASIS_ABSENT in out.refusals
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_out_of_bounds_observation_refuses_no_write(tmp_path):
    # refusal_rate 0.5 trips the 0.2 bound -> no in-bounds survival evidence.
    _populate_full(tmp_path, refusal_rate=0.5)
    out = _promote(tmp_path)
    assert out.promoted is False
    assert PROMOTION_EVIDENCE_INSUFFICIENT in out.refusals
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_wrong_trial_refuses_no_write(tmp_path):
    _populate_full(tmp_path)
    out = _promote(tmp_path, candidate=_candidate(trial_id="trial-does-not-exist"))
    assert out.promoted is False
    assert out.refusals  # not walkable / missing
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_off_surface_tunable_refuses_no_write(tmp_path):
    # "Wrong profile/config": the candidate's tunable is not on the allowed surface.
    _populate_full(tmp_path)
    out = _promote(tmp_path, allowed_tunable_surface=frozenset({"some_other_knob"}))
    assert out.promoted is False
    assert PROMOTION_OFF_SURFACE_TUNABLE in out.refusals
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


# --- Act inputs are the operator's, mandatory, and NOT evidence refusals -----------


def test_missing_act_inputs_raise_before_disk_read(tmp_path):
    import pytest

    _populate_full(tmp_path)
    with pytest.raises(ValueError, match="baseline_name"):
        _promote(tmp_path, baseline_name="")
    with pytest.raises(ValueError, match="minted_by"):
        _promote(tmp_path, minted_by="")
    # A caller error must not have written anything.
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_no_fiat_parameter_exists(tmp_path):
    # There is no force/allow-missing/override knob to cure refused evidence.
    params = set(inspect.signature(operational_promote).parameters)
    for forbidden in ("force", "allow_missing", "override", "skip_gate", "bypass"):
        assert forbidden not in params


# --- NEGATIVE PRIORITY: no path from discovery/prepare to a write ------------------


def test_discovery_alone_does_not_mint(tmp_path):
    _populate_full(tmp_path)
    before = _files(tmp_path)
    discover_promotion_bundle(
        tmp_path, _candidate(), required_count=3, evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON, allowed_tunable_surface=ALLOWED,
        promote_reading=_reading(4_500), operator_review_horizon_ns=HORIZON,
    )
    assert _files(tmp_path) == before
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_prepare_alone_does_not_mint(tmp_path):
    _populate_full(tmp_path)
    before = _files(tmp_path)
    prepare_mint_input(
        tmp_path, _candidate(), required_count=3, evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON, allowed_tunable_surface=ALLOWED,
        promote_reading=_reading(4_500), operator_review_horizon_ns=HORIZON,
    )
    assert _files(tmp_path) == before
    assert ControlBaselineStore(tmp_path).list_ids() == []
    assert PromotionReceiptStore(tmp_path).list_ids() == []


def test_read_only_modules_carry_no_write_path_import(tmp_path):
    # Static guard: the read-only modules do not reference the write path at all.
    for mod in (promotion_discovery, promotion_mint_input):
        src = inspect.getsource(mod)
        assert "operational_promote" not in src
        assert "PromotionReceiptStore" not in src
        assert "ControlBaselineStore" not in src
        assert "admit_baseline" not in src


# --- Weak<->strong operator basis: unreachable-by-construction on the disk path ----


def test_disk_path_cannot_produce_weak_strong_mismatch(tmp_path):
    # The store derives the bundle's weak operator-basis via facts.project() and surfaces
    # the same strong facts. So on the disk path the weak shadow is ALWAYS the projection
    # of the strong object casting it — the mint's OPERATOR_BASIS_WEAK_STRONG_MISMATCH is
    # structurally unreachable here. (The refusal itself is covered at the mint unit level
    # in test_promotion_mint.py.) We assert the projection invariant end-to-end.
    _populate_full(tmp_path)
    mi = prepare_mint_input(
        tmp_path, _candidate(), required_count=3, evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON, allowed_tunable_surface=ALLOWED,
        promote_reading=_reading(4_500), operator_review_horizon_ns=HORIZON,
    )
    assert mi.bundle.operator_basis == mi.operator_basis_facts.project()
    out = _promote(tmp_path)
    from governor.promotion_mint import OPERATOR_BASIS_WEAK_STRONG_MISMATCH
    assert OPERATOR_BASIS_WEAK_STRONG_MISMATCH not in out.refusals
    assert out.promoted is True


# --- Idempotence + revert-as-supersession ------------------------------------------


def test_idempotent_repromote_no_second_baseline(tmp_path):
    _populate_full(tmp_path)
    out1 = _promote(tmp_path)
    out2 = _promote(tmp_path)
    assert out1.promoted and out2.promoted
    assert out1.baseline.baseline_id == out2.baseline.baseline_id
    assert out1.receipt.receipt_id == out2.receipt.receipt_id
    # Same content-addressed id -> same file -> exactly one baseline, one receipt.
    assert ControlBaselineStore(tmp_path).list_ids() == [out1.baseline.baseline_id]
    assert PromotionReceiptStore(tmp_path).list_ids() == [out1.receipt.receipt_id]


def test_revert_is_supersession_not_delete(tmp_path):
    store = ControlBaselineStore(tmp_path)
    from governor.control_baseline import admit_baseline
    prior = admit_baseline(
        name="prior", config_hashes={TUNABLE: "sha256:old"},
        creation_receipt_id="rcpt-prior", admitted_by="jbeck",
    )
    store.put(prior)
    _populate_full(tmp_path, prior_baseline_hash=prior.baseline_id)
    out = _promote(tmp_path, prior_baseline=prior)
    assert out.promoted
    reverted = revert_promoted_baseline(
        out.baseline, prior, creation_receipt_id="rcpt-revert", admitted_by="jbeck"
    )
    store.put(reverted)
    ids = store.list_ids()
    # Three distinct baselines: prior, promoted, revert. None deleted.
    assert prior.baseline_id in ids
    assert out.baseline.baseline_id in ids
    assert reverted.baseline_id in ids
    assert reverted.supersedes == out.baseline.baseline_id
