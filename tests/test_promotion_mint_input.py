# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3b — discovery-backed mint INPUT path tests.

Receipts are written through the REAL producers; prepare_mint_input gathers the inputs
an explicit mint would consume — and NEVER mints. The hard line under test:
discovery may FEED mint eligibility; it may NOT trigger promotion; minting remains an
explicit operator-present act (a separate call that independently re-derives).
"""

from __future__ import annotations

from dataclasses import fields

from governor.clock_witness import MonotonicReading
from governor.control_baseline import ControlBaselineStore
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.operator_basis import REVIEW_BASIS_REVIEWED, OperatorBasisFacts
from governor.promotion_discovery import discover_promotion_bundle
from governor.promotion_evidence import ActivationReceipt, PromotionCandidate
from governor.promotion_evidence_store import (
    ActivationReceiptStore,
    ObservationReceiptStore,
    OperatorBasisReceiptStore,
    ReplayHoldoutReceiptStore,
)
from governor.promotion_mint import mint_promotion
from governor.promotion_mint_input import (
    MintInput,
    MintInputRefusal,
    prepare_mint_input,
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


def _populate_full(root):
    ActivationReceiptStore(root).put(_activation())
    obs = ObservationReceiptStore(root)
    for i in range(3):
        obs.put(
            observation_id=f"o{i}",
            facts=ObservationFacts(
                trial_id="trial-1", observed_at=_reading(2_000 + i * 100),
                metrics=(("refusal_rate", 0.1),), disqualifying_events=(),
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
    # bundle hash the operator reviews (discover with operator absent to obtain it)
    bbh = discover_promotion_bundle(
        root, _candidate(), required_count=3, evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON, allowed_tunable_surface=ALLOWED,
        promote_reading=_reading(4_500), operator_review_horizon_ns=HORIZON,
    ).basis_bundle_hash
    OperatorBasisReceiptStore(root).put(
        OperatorBasisFacts(
            trial_id="trial-1", operator_id="jbeck",
            promotion_basis="trial held in-bounds across window", scope="self_governance",
            basis_bundle_hash=bbh, reviewed_at=_reading(4_000),
            transition_request_hash="sha256:transition", prior_authority_hash="sha256:prior",
            evidence_bundle_hashes=(bbh,), reviewed_verdict=REVIEW_BASIS_REVIEWED,
            explicitly_not_auto_baseline=True,
        )
    )


def _prepare(root, *, candidate=None, **overrides):
    base = dict(
        required_count=3, evaluation_reading=_reading(5_000), freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED, promote_reading=_reading(4_500),
        operator_review_horizon_ns=HORIZON,
    )
    base.update(overrides)
    return prepare_mint_input(root, candidate or _candidate(), **base)


# --- Eligible discovery yields mint input -------------------------------------


def test_prepare_returns_mint_input_on_eligible(tmp_path):
    _populate_full(tmp_path)
    mi = _prepare(tmp_path)
    assert isinstance(mi, MintInput)
    assert mi.operator_basis_facts.operator_id == "jbeck"  # the STRONG facts, surfaced
    assert mi.bundle.activation is not None
    assert mi.source_root == str(tmp_path)


# --- prepare NEVER mints / writes / carries act inputs ------------------------


def test_prepare_does_not_mint_or_write(tmp_path):
    _populate_full(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    mi = _prepare(tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert before == after  # no writes
    # No baseline was minted anywhere.
    assert ControlBaselineStore(tmp_path).list_ids() == []
    # MintInput carries no minting capability and no act inputs.
    field_names = {f.name for f in fields(MintInput)}
    assert "baseline_name" not in field_names  # the act inputs are NOT pre-decided
    assert "minted_by" not in field_names
    assert not hasattr(mi, "mint")
    assert not hasattr(mi, "baseline")


# --- Refuses unless eligible (no mint input produced) -------------------------


def test_prepare_refuses_when_discovery_not_eligible(tmp_path):
    mi = _prepare(tmp_path)  # empty root
    assert isinstance(mi, MintInputRefusal)
    assert "promotion_operator_basis_absent" in mi.refusals
    assert "promotion_evidence_insufficient" in mi.refusals


def test_prepare_refuses_off_surface(tmp_path):
    _populate_full(tmp_path)
    mi = _prepare(tmp_path, allowed_tunable_surface=frozenset({"other"}))
    assert isinstance(mi, MintInputRefusal)
    assert "promotion_off_surface_tunable" in mi.refusals


# --- The wiring: input FEEDS a SEPARATE explicit mint that RE-DERIVES ----------


def test_mint_input_feeds_explicit_mint_which_redrives(tmp_path):
    """Discovery feeds mint eligibility; the mint is a SEPARATE explicit operator-present
    call that supplies the act inputs (baseline_name, minted_by) and independently
    re-derives the gate + strong operator-basis binding from prepare's inputs.

    prepare did not mint (asserted above); THIS call does — synthetic fixtures, tmp_path,
    nothing persisted to an operational store. Demonstrates the contract, not a real
    promotion."""
    _populate_full(tmp_path)
    mi = _prepare(tmp_path)
    assert isinstance(mi, MintInput)

    result = mint_promotion(
        mi.bundle,
        mi.operator_basis_facts,
        promote_reading=mi.promote_reading,
        operator_review_horizon_ns=mi.operator_review_horizon_ns,
        baseline_name="self_governance/max_slices",  # operator-present ACT input
        minted_by="jbeck",  # operator-present ACT input
        prior_baseline=mi.prior_baseline,
    )
    assert result.minted is True  # the mint re-derived prepare's inputs and agreed
    assert result.receipt.basis_bundle_hash == mi.basis_bundle_hash


def test_mint_redrive_refuses_if_inputs_tampered(tmp_path):
    """The mint re-derives, so prepare cannot smuggle eligibility past it: hand-swap the
    strong facts to a different operator and the mint's weak<->strong consistency gate
    refuses (the bundle's projected shadow no longer matches)."""
    _populate_full(tmp_path)
    mi = _prepare(tmp_path)
    tampered = OperatorBasisFacts(
        trial_id=mi.operator_basis_facts.trial_id,
        operator_id="someone-else",  # != the projected shadow in mi.bundle
        promotion_basis=mi.operator_basis_facts.promotion_basis,
        scope=mi.operator_basis_facts.scope,
        basis_bundle_hash=mi.operator_basis_facts.basis_bundle_hash,
        reviewed_at=mi.operator_basis_facts.reviewed_at,
        transition_request_hash=mi.operator_basis_facts.transition_request_hash,
        prior_authority_hash=mi.operator_basis_facts.prior_authority_hash,
        evidence_bundle_hashes=mi.operator_basis_facts.evidence_bundle_hashes,
        reviewed_verdict=mi.operator_basis_facts.reviewed_verdict,
        explicitly_not_auto_baseline=mi.operator_basis_facts.explicitly_not_auto_baseline,
    )
    result = mint_promotion(
        mi.bundle, tampered,
        promote_reading=mi.promote_reading,
        operator_review_horizon_ns=mi.operator_review_horizon_ns,
        baseline_name="x", minted_by="jbeck", prior_baseline=mi.prior_baseline,
    )
    assert result.minted is False
    assert "operator_basis_weak_strong_mismatch" in result.refusals
