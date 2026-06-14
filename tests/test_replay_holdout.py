# SPDX-License-Identifier: Apache-2.0
"""P4.0f — replay/holdout producer/store tests.

The verdict is DERIVED from facts, persisted, and RE-DERIVED on load. The headline is
the same as P4.0e: producer-derived ≠ producer-trusted — a refused run re-stamped
passed is caught on load. Plus the derivation refusals (binding / corpus-frozen /
exit-observed / regression) and an end-to-end "valid replay plugs into the gate" path.
"""

from __future__ import annotations

import json

import pytest

from governor.clock_witness import MonotonicReading
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.promotion_evidence import (
    ActivationReceipt,
    OperatorBasisReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    evaluate_promotion_from_evidence,
)
from governor.promotion_evidence_store import (
    ObservationReceiptStore,
    ReplayHoldoutReceiptStore,
    ReplayHoldoutReceiptTamperError,
)
from governor.replay_holdout import (
    REPLAY_CHILD_EXIT_NOT_OBSERVED,
    REPLAY_CORPUS_NOT_FROZEN,
    REPLAY_HARNESS_RUN_FAILED,
    REPLAY_MISSING_COMPARATOR_BASELINE,
    REPLAY_MISSING_HARNESS_IDENTITY,
    REPLAY_REFUSAL_REASONS,
    REPLAY_REGRESSION_DETECTED,
    REPLAY_VERDICT_PASSED,
    REPLAY_VERDICT_REFUSED,
    MalformedReplayFactsError,
    ReplayHoldoutFacts,
    derive_replay_verdict,
)

TUNABLE = "decomposition_size/max_slices"
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"


def _reading(ns: int) -> MonotonicReading:
    return MonotonicReading(source=SRC, epoch=EPOCH, ns=ns)


def _facts(**overrides) -> ReplayHoldoutFacts:
    base = dict(
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
        started_at=_reading(1_000),
        completed_at=_reading(2_000),
        child_exit=0,
        exit_observed=True,
        raw_result_hash="sha256:beef",
        result_non_regression=True,
    )
    base.update(overrides)
    return ReplayHoldoutFacts(**base)


# --- Derivation: the single pass path ----------------------------------------


def test_clean_run_derives_passed():
    v = derive_replay_verdict(_facts())
    assert v.verdict == REPLAY_VERDICT_PASSED
    assert v.passed is True
    assert v.reasons == ()


def test_duration_ns_is_licensed_subtraction():
    assert _facts().duration_ns() == 1_000


# --- Derivation refusals ------------------------------------------------------


def test_missing_comparator_baseline_refuses():
    v = derive_replay_verdict(_facts(comparator_baseline_id=""))
    assert v.verdict == REPLAY_VERDICT_REFUSED
    assert REPLAY_MISSING_COMPARATOR_BASELINE in v.reasons


def test_floating_corpus_refuses():
    # corpus evaluated differs from the frozen corpus.
    v = derive_replay_verdict(_facts(corpus_hash="sha256:beef"))
    assert REPLAY_CORPUS_NOT_FROZEN in v.reasons
    assert v.passed is False


def test_unfrozen_corpus_refuses():
    v = derive_replay_verdict(_facts(frozen_corpus_hash=""))
    assert REPLAY_CORPUS_NOT_FROZEN in v.reasons


def test_missing_harness_identity_refuses():
    assert REPLAY_MISSING_HARNESS_IDENTITY in derive_replay_verdict(
        _facts(harness_version="")
    ).reasons


def test_exit_not_observed_refuses():
    v = derive_replay_verdict(_facts(exit_observed=False))
    assert REPLAY_CHILD_EXIT_NOT_OBSERVED in v.reasons


def test_failed_child_exit_refuses():
    v = derive_replay_verdict(_facts(child_exit=1))
    assert REPLAY_HARNESS_RUN_FAILED in v.reasons


def test_regression_detected_refuses():
    v = derive_replay_verdict(_facts(result_non_regression=False))
    assert REPLAY_REGRESSION_DETECTED in v.reasons


def test_claimed_pass_with_failed_exit_still_refuses():
    # The harness "passed" but the run did not exit clean -> not an admissible pass.
    v = derive_replay_verdict(_facts(result_non_regression=True, child_exit=2))
    assert v.passed is False
    assert REPLAY_HARNESS_RUN_FAILED in v.reasons


def test_reasons_in_closed_vocabulary():
    v = derive_replay_verdict(
        _facts(
            comparator_baseline_id="",
            harness_version="",
            exit_observed=False,
            result_non_regression=False,
            frozen_corpus_hash="",
        )
    )
    assert set(v.reasons) <= REPLAY_REFUSAL_REASONS


def test_malformed_facts_refused_at_construction():
    with pytest.raises(MalformedReplayFactsError):
        _facts(child_exit=True)  # bool is not an int exit code
    with pytest.raises(MalformedReplayFactsError):
        _facts(result_non_regression="yes")


# --- Store: roundtrip + producer-derived ≠ producer-trusted ------------------


def test_store_roundtrip_passed(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    store.put(_facts())
    receipt = store.load_for_trial("trial-1")
    assert receipt is not None
    assert receipt.passed is True
    assert receipt.comparator_baseline_id == "baseline-prior"


def test_store_refused_run_loads_as_failed_not_error(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    store.put(_facts(result_non_regression=False))  # legitimate regression
    receipt = store.load_for_trial("trial-1")
    assert receipt is not None
    assert receipt.passed is False  # honest fail, not a raise


def test_restamped_verdict_is_refused_on_load(tmp_path):
    """A refused run re-stamped verdict=passed is caught: re-derivation disagrees with
    the stored verdict. content_hash covers inputs only, so editing only the verdict
    leaves it intact — the re-derive is what catches it."""
    store = ReplayHoldoutReceiptStore(tmp_path)
    path = store.put(_facts(child_exit=1))  # refused
    d = json.loads(path.read_text())
    assert d["verdict"] == REPLAY_VERDICT_REFUSED
    d["verdict"] = REPLAY_VERDICT_PASSED  # the lie
    path.write_text(json.dumps(d, sort_keys=True, indent=2))
    with pytest.raises(ReplayHoldoutReceiptTamperError):
        store.load_for_trial("trial-1")


def test_tampered_facts_is_refused_on_load(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    path = store.put(_facts())
    d = json.loads(path.read_text())
    d["comparator_baseline_id"] = "baseline-OTHER"  # tamper an input
    path.write_text(json.dumps(d, sort_keys=True, indent=2))
    with pytest.raises(ReplayHoldoutReceiptTamperError):
        store.load_for_trial("trial-1")


def test_corpus_hash_tampered_after_run_is_refused(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    path = store.put(_facts())
    d = json.loads(path.read_text())
    d["corpus_hash"] = "sha256:swapped"
    path.write_text(json.dumps(d, sort_keys=True, indent=2))
    with pytest.raises(ReplayHoldoutReceiptTamperError):
        store.load_for_trial("trial-1")


def test_swapped_trial_id_is_refused_on_load(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    store.put(_facts(trial_id="trial-1"))  # creates the dir
    other_path = store.put(_facts(trial_id="trial-OTHER"))  # under OTHER's key
    # Move OTHER's self-consistent bytes into trial-1's slot.
    target = store.directory / __import__("hashlib").sha256(b"trial-1").hexdigest()
    target = target.with_suffix(".json")
    target.write_text(other_path.read_text())
    with pytest.raises(ReplayHoldoutReceiptTamperError):
        store.load_for_trial("trial-1")


def test_unknown_trial_is_clean_miss(tmp_path):
    store = ReplayHoldoutReceiptStore(tmp_path)
    assert store.load_for_trial("never-replayed") is None


# --- End to end: a valid loaded replay plugs into the gate -------------------


def _activation() -> ActivationReceipt:
    return ActivationReceipt(
        trial_id="trial-1",
        tunable_name=TUNABLE,
        trial_value=4,
        prior_baseline_value=8,
        activated_at=_reading(500),
    )


def _live_observations(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    bound = SurvivalBound(metric="refusal_rate", trip_comparator="gt", threshold=0.2)
    for i in range(3):
        store.put(
            observation_id=f"o{i}",
            facts=ObservationFacts(
                trial_id="trial-1",
                observed_at=_reading(2_000 + i),
                metrics=(("refusal_rate", 0.1),),
            ),
            bound=bound,
            activation_receipt_hash=_activation().content_hash,
        )
    return store.load_for_trial("trial-1")


def _bundle(observations, replay):
    return PromotionEvidenceBundle(
        candidate=PromotionCandidate(
            trial_id="trial-1", tunable_name=TUNABLE, trial_value=4
        ),
        activation=_activation(),
        observations=tuple(observations),
        replay=replay,
        operator_basis=OperatorBasisReceipt(
            trial_id="trial-1",
            operator_actor="jbeck",
            promotion_basis="held in-bounds",
            scope="self_governance",
            explicitly_not_auto_baseline=True,
        ),
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=10_000,
        allowed_tunable_surface=frozenset({TUNABLE}),
    )


def test_valid_replay_receipt_plugs_into_gate(tmp_path):
    obs = _live_observations(tmp_path)
    replay = ReplayHoldoutReceiptStore(tmp_path)
    replay.put(_facts())
    loaded_replay = replay.load_for_trial("trial-1")
    result = evaluate_promotion_from_evidence(_bundle(obs, loaded_replay))
    assert result.eligible is True  # synthetic fixture, not the real trial


def test_missing_replay_keeps_gate_refusing(tmp_path):
    obs = _live_observations(tmp_path)
    result = evaluate_promotion_from_evidence(_bundle(obs, None))
    assert result.eligible is False
    assert "promotion_replay_holdout_missing" in result.refusals


def test_failed_replay_keeps_gate_refusing(tmp_path):
    obs = _live_observations(tmp_path)
    replay = ReplayHoldoutReceiptStore(tmp_path)
    replay.put(_facts(result_non_regression=False))
    loaded_replay = replay.load_for_trial("trial-1")
    result = evaluate_promotion_from_evidence(_bundle(obs, loaded_replay))
    assert result.eligible is False
    assert "promotion_replay_holdout_failed" in result.refusals
