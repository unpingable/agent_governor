# SPDX-License-Identifier: Apache-2.0
"""P4.0g — operator-basis producer/store tests.

operator_basis_present is DERIVED structurally from the typed pair
(consumed_bundle_hash, OperatorBasisFacts) — never a detached bool. The three most
important tests (operator's call): bundle A reviewed ≠ bundle B consumed → refused;
reviewed_at ≥ promote_at → refused; restamped verdict → tamper. Then the store and the
full eligible pipeline (only with all three loaded receipts).
"""

from __future__ import annotations

import json

import pytest

from governor.clock_witness import MonotonicReading
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.operator_basis import (
    OPERATOR_BASIS_BUNDLE_MISMATCH,
    OPERATOR_BASIS_CLAIMS_AUTO,
    OPERATOR_BASIS_CLOCK_INCOMPATIBLE,
    OPERATOR_BASIS_MISSING_BINDING,
    OPERATOR_BASIS_POST_ATTESTATION,
    OPERATOR_BASIS_REFUSAL_REASONS,
    OPERATOR_BASIS_STALE,
    OPERATOR_BASIS_VERDICT_REFUSED,
    REVIEW_BASIS_REVIEWED,
    REVIEW_REFUSED,
    MalformedOperatorBasisError,
    OperatorBasisFacts,
    derive_operator_basis_present,
)
from governor.promotion_evidence import (
    ActivationReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    evaluate_promotion_from_evidence,
)
from governor.promotion_evidence_store import (
    ObservationReceiptStore,
    OperatorBasisReceiptStore,
    OperatorBasisReceiptTamperError,
    ReplayHoldoutReceiptStore,
)
from governor.replay_holdout import ReplayHoldoutFacts

TUNABLE = "decomposition_size/max_slices"
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"
BUNDLE_A = "sha256:reviewed-bundle"
HORIZON = 10_000


def _reading(ns: int, source: str = SRC, epoch: str = EPOCH) -> MonotonicReading:
    return MonotonicReading(source=source, epoch=epoch, ns=ns)


def _facts(**overrides) -> OperatorBasisFacts:
    base = dict(
        trial_id="trial-1",
        operator_id="jbeck",
        promotion_basis="reviewed live + replay evidence, in-bounds",
        scope="self_governance",
        basis_bundle_hash=BUNDLE_A,
        reviewed_at=_reading(2_000),
        transition_request_hash="sha256:transition",
        prior_authority_hash="sha256:prior",
        evidence_bundle_hashes=("sha256:act", "sha256:obs", "sha256:replay"),
        reviewed_verdict=REVIEW_BASIS_REVIEWED,
        explicitly_not_auto_baseline=True,
    )
    base.update(overrides)
    return OperatorBasisFacts(**base)


def _derive(facts, *, consumed=BUNDLE_A, promote_ns=5_000, horizon=HORIZON, promote=None):
    return derive_operator_basis_present(
        facts,
        consumed_bundle_hash=consumed,
        promote_reading=promote if promote is not None else _reading(promote_ns),
        freshness_horizon_ns=horizon,
    )


# --- The single present path --------------------------------------------------


def test_all_good_is_present():
    v = _derive(_facts())
    assert v.present is True
    assert v.reasons == ()


# --- #1 (most important): bundle A reviewed != bundle B consumed -> refused ---


def test_reviewed_bundle_must_equal_consumed_bundle():
    v = _derive(_facts(basis_bundle_hash="sha256:bundle-A"), consumed="sha256:bundle-B")
    assert v.present is False
    assert OPERATOR_BASIS_BUNDLE_MISMATCH in v.reasons


# --- #2: reviewed_at >= promote_at -> post-attestation refused ----------------


def test_review_at_or_after_promote_is_post_attestation():
    v = _derive(_facts(reviewed_at=_reading(5_000)), promote_ns=5_000)  # equal
    assert v.present is False
    assert OPERATOR_BASIS_POST_ATTESTATION in v.reasons
    after = _derive(_facts(reviewed_at=_reading(6_000)), promote_ns=5_000)  # after
    assert OPERATOR_BASIS_POST_ATTESTATION in after.reasons


# --- temporal: stale + incompatible clock ------------------------------------


def test_stale_review_refused():
    v = _derive(_facts(reviewed_at=_reading(2_000)), promote_ns=2_000 + HORIZON + 1)
    assert v.present is False
    assert OPERATOR_BASIS_STALE in v.reasons


def test_incompatible_clock_basis_refused():
    v = _derive(_facts(reviewed_at=_reading(2_000, epoch="boot:OTHER")))
    assert v.present is False
    assert OPERATOR_BASIS_CLOCK_INCOMPATIBLE in v.reasons


# --- attestation nature: refused verdict / auto-claim / missing binding -------


def test_refused_review_is_not_present():
    v = _derive(_facts(reviewed_verdict=REVIEW_REFUSED))
    assert OPERATOR_BASIS_VERDICT_REFUSED in v.reasons


def test_auto_claiming_basis_refused():
    v = _derive(_facts(explicitly_not_auto_baseline=False))
    assert OPERATOR_BASIS_CLAIMS_AUTO in v.reasons


def test_missing_binding_refused():
    v = _derive(_facts(transition_request_hash=""))
    assert OPERATOR_BASIS_MISSING_BINDING in v.reasons


def test_reasons_in_closed_vocabulary():
    v = _derive(
        _facts(
            transition_request_hash="",
            reviewed_verdict=REVIEW_REFUSED,
            explicitly_not_auto_baseline=False,
            basis_bundle_hash="x",
            reviewed_at=_reading(9_999),
        ),
        consumed="y",
        promote_ns=5_000,
    )
    assert set(v.reasons) <= OPERATOR_BASIS_REFUSAL_REASONS


def test_malformed_verdict_refused_at_construction():
    with pytest.raises(MalformedOperatorBasisError):
        _facts(reviewed_verdict="looks_fine")


# --- Store: roundtrip + #3 (restamp) + tamper + swap -------------------------


def test_store_roundtrip_emits_receipt_when_structural_passes(tmp_path):
    store = OperatorBasisReceiptStore(tmp_path)
    store.put(_facts())
    receipt = store.load_for_trial(
        "trial-1",
        consumed_bundle_hash=BUNDLE_A,
        promote_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
    )
    assert receipt is not None
    assert receipt.operator_actor == "jbeck"
    assert receipt.explicitly_not_auto_baseline is True


def test_store_bundle_mismatch_returns_none(tmp_path):
    store = OperatorBasisReceiptStore(tmp_path)
    store.put(_facts(basis_bundle_hash="sha256:bundle-A"))
    receipt = store.load_for_trial(
        "trial-1",
        consumed_bundle_hash="sha256:bundle-B",  # different consumed bundle
        promote_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
    )
    assert receipt is None  # gate will see operator-basis absent


def test_restamped_verdict_is_tamper(tmp_path):
    """reviewed_verdict is an attested INPUT (in the hash); restamping refused ->
    basis_reviewed is a content tamper, caught by integrity."""
    store = OperatorBasisReceiptStore(tmp_path)
    path = store.put(_facts(reviewed_verdict=REVIEW_REFUSED))
    d = json.loads(path.read_text())
    d["reviewed_verdict"] = REVIEW_BASIS_REVIEWED  # the lie
    path.write_text(json.dumps(d, sort_keys=True, indent=2))
    with pytest.raises(OperatorBasisReceiptTamperError):
        store.load_for_trial(
            "trial-1",
            consumed_bundle_hash=BUNDLE_A,
            promote_reading=_reading(5_000),
            freshness_horizon_ns=HORIZON,
        )


def test_tampered_bundle_hash_is_tamper(tmp_path):
    store = OperatorBasisReceiptStore(tmp_path)
    path = store.put(_facts())
    d = json.loads(path.read_text())
    d["basis_bundle_hash"] = "sha256:swapped"
    path.write_text(json.dumps(d, sort_keys=True, indent=2))
    with pytest.raises(OperatorBasisReceiptTamperError):
        store.load_for_trial(
            "trial-1",
            consumed_bundle_hash="sha256:swapped",
            promote_reading=_reading(5_000),
            freshness_horizon_ns=HORIZON,
        )


def test_swapped_trial_id_is_tamper(tmp_path):
    store = OperatorBasisReceiptStore(tmp_path)
    store.put(_facts(trial_id="trial-1"))
    other_path = store.put(_facts(trial_id="trial-OTHER"))
    target = (
        store.directory
        / __import__("hashlib").sha256(b"trial-1").hexdigest()
    ).with_suffix(".json")
    target.write_text(other_path.read_text())
    with pytest.raises(OperatorBasisReceiptTamperError):
        store.load_for_trial(
            "trial-1",
            consumed_bundle_hash=BUNDLE_A,
            promote_reading=_reading(5_000),
            freshness_horizon_ns=HORIZON,
        )


def test_unknown_trial_is_clean_miss(tmp_path):
    store = OperatorBasisReceiptStore(tmp_path)
    assert (
        store.load_for_trial(
            "nope",
            consumed_bundle_hash=BUNDLE_A,
            promote_reading=_reading(5_000),
            freshness_horizon_ns=HORIZON,
        )
        is None
    )


# --- End to end: eligible only with all three loaded receipts ----------------


def _activation() -> ActivationReceipt:
    return ActivationReceipt(
        trial_id="trial-1",
        tunable_name=TUNABLE,
        trial_value=4,
        prior_baseline_value=8,
        activated_at=_reading(500),
    )


def _observations(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    bound = SurvivalBound(metric="refusal_rate", trip_comparator="gt", threshold=0.2)
    for i in range(3):
        store.put(
            observation_id=f"o{i}",
            facts=ObservationFacts(
                trial_id="trial-1",
                observed_at=_reading(1_000 + i),
                metrics=(("refusal_rate", 0.1),),
            ),
            bound=bound,
            activation_receipt_hash=_activation().content_hash,
        )
    return store.load_for_trial("trial-1")


def _replay(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    store.put(
        ReplayHoldoutFacts(
            trial_id="trial-1",
            candidate_id="cand-1",
            comparator_baseline_id="baseline-prior",
            replay_subject=TUNABLE,
            replay_harness_id="nonregression_harness",
            harness_version="v1",
            corpus_id="corpus-A",
            corpus_hash="sha256:cafe",
            frozen_corpus_hash="sha256:cafe",
            corpus_frozen_at="2026-06-14T00:00:00Z",
            started_at=_reading(600),
            completed_at=_reading(700),
            child_exit=0,
            exit_observed=True,
            raw_result_hash="sha256:beef",
            result_non_regression=True,
        )
    )
    return store.load_for_trial("trial-1")


def _bundle(observations, replay, operator_basis):
    return PromotionEvidenceBundle(
        candidate=PromotionCandidate(
            trial_id="trial-1", tunable_name=TUNABLE, trial_value=4
        ),
        activation=_activation(),
        observations=tuple(observations),
        replay=replay,
        operator_basis=operator_basis,
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=frozenset({TUNABLE}),
    )


def test_full_pipeline_eligible_with_all_three_loaded(tmp_path):
    obs, replay = _observations(tmp_path), _replay(tmp_path)
    ob_store = OperatorBasisReceiptStore(tmp_path)
    ob_store.put(_facts())
    operator_basis = ob_store.load_for_trial(
        "trial-1",
        consumed_bundle_hash=BUNDLE_A,
        promote_reading=_reading(6_000),
        freshness_horizon_ns=HORIZON,
    )
    assert operator_basis is not None
    result = evaluate_promotion_from_evidence(_bundle(obs, replay, operator_basis))
    assert result.eligible is True  # synthetic fixture, not the real trial


def test_full_pipeline_refuses_when_operator_basis_bundle_mismatch(tmp_path):
    obs, replay = _observations(tmp_path), _replay(tmp_path)
    ob_store = OperatorBasisReceiptStore(tmp_path)
    ob_store.put(_facts(basis_bundle_hash="sha256:bundle-A"))
    operator_basis = ob_store.load_for_trial(
        "trial-1",
        consumed_bundle_hash="sha256:bundle-B",  # mismatch -> None
        promote_reading=_reading(6_000),
        freshness_horizon_ns=HORIZON,
    )
    assert operator_basis is None
    result = evaluate_promotion_from_evidence(_bundle(obs, replay, operator_basis))
    assert result.eligible is False
    assert "promotion_operator_basis_absent" in result.refusals
