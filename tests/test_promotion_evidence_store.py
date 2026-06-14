# SPDX-License-Identifier: Apache-2.0
"""P4.0c — ActivationReceipt store tests (one producer, one storage seam).

Roundtrip + content_hash stability, orphan (clean miss), and tamper refusal from
disk. The store is the IO seam for the chain root only — no observations, no
replay, no operator basis, no baseline, no N.
"""

from __future__ import annotations

import json

import pytest

from governor.clock_witness import MonotonicReading
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.promotion_evidence import (
    ActivationReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
    OperatorBasisReceipt,
    evaluate_promotion_from_evidence,
)
from governor.promotion_evidence_store import (
    ActivationReceiptStore,
    ActivationReceiptTamperError,
    ObservationReceiptStore,
    ObservationReceiptTamperError,
)

TUNABLE = "decomposition_size/max_slices"
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"


def _activation(trial_id: str = "trial-1", trial_value=4) -> ActivationReceipt:
    return ActivationReceipt(
        trial_id=trial_id,
        tunable_name=TUNABLE,
        trial_value=trial_value,
        prior_baseline_value=8,
        activated_at=MonotonicReading(source=SRC, epoch=EPOCH, ns=1_000),
    )


# --- Roundtrip + content_hash stability --------------------------------------


def test_put_then_get_roundtrips(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded == original


def test_content_hash_stable_across_persist_load(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    before = original.content_hash
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded is not None
    assert loaded.content_hash == before


def test_put_returns_path_under_layout(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation())
    assert path.exists()
    assert path.parent == tmp_path / "promotion_evidence" / "activations"
    assert store.list_trial_keys() == [path.stem]


# --- Orphan: a clean miss, not an error --------------------------------------


def test_get_unknown_trial_is_clean_miss(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    assert store.get("never-activated") is None


# --- Tamper refusal from disk ------------------------------------------------


def test_tampered_field_with_stale_hash_is_refused(tmp_path):
    """Edit a field on disk but leave the stored content_hash → the recomputed
    hash no longer matches → refused."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation(trial_value=4))

    d = json.loads(path.read_text())
    d["trial_value"] = 99  # tamper: change the promoted value, keep old hash
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


def test_tampered_hash_field_is_refused(tmp_path):
    """Corrupt the stored content_hash directly → mismatch → refused."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation())

    d = json.loads(path.read_text())
    d["content_hash"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


def test_trial_id_swapped_in_file_is_refused(tmp_path):
    """A file placed at trial-1's key but carrying a different trial_id (swap /
    key collision) is refused even if its own self-hash is internally consistent."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation(trial_id="trial-1"))

    # Rebuild a *self-consistent* receipt for a different trial, write its bytes
    # into trial-1's file (so the self-hash passes but the trial_id check fails).
    other = _activation(trial_id="trial-OTHER")
    path.write_text(json.dumps(other.to_dict(), sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


# --- The store integrates with the walk layer (round-tripped receipt binds) ---


def test_loaded_activation_hash_matches_for_observation_binding(tmp_path):
    """A persisted+loaded activation produces the same content_hash an observation
    must bind to — the store does not break walkability."""
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded is not None
    assert loaded.content_hash == original.content_hash


# ============================================================================
# P4.0e — ObservationReceiptStore: producer persists, evaluator re-derives.
# ============================================================================

BOUND = SurvivalBound(metric="refusal_rate", trip_comparator="gt", threshold=0.2)


def _facts(
    trial_id: str = "trial-1", ns: int = 2_000, refusal_rate: float = 0.1, disq=()
) -> ObservationFacts:
    return ObservationFacts(
        trial_id=trial_id,
        observed_at=MonotonicReading(source=SRC, epoch=EPOCH, ns=ns),
        metrics=(("refusal_rate", refusal_rate),),
        disqualifying_events=disq,
    )


def _put_obs(store, obs_id, *, facts=None, act_hash=None):
    return store.put(
        observation_id=obs_id,
        facts=facts if facts is not None else _facts(),
        bound=BOUND,
        activation_receipt_hash=act_hash
        if act_hash is not None
        else _activation().content_hash,
    )


# --- Roundtrip: producer derives, evaluator re-derives, they agree -----------


def test_observation_roundtrip_in_bounds(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    _put_obs(store, "o1")
    loaded = store.load_for_trial("trial-1")
    assert len(loaded) == 1
    assert loaded[0].in_bounds is True
    assert loaded[0].observation_id == "o1"
    assert loaded[0].activation_receipt_hash == _activation().content_hash


def test_tripped_observation_persists_as_not_in_bounds(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    _put_obs(store, "o-trip", facts=_facts(refusal_rate=0.95))  # trips the bound
    loaded = store.load_for_trial("trial-1")
    assert loaded[0].in_bounds is False  # derived, honest


# --- The headline: producer-derived is NOT producer-trusted ------------------


def test_restamped_in_bounds_is_refused_on_load(tmp_path):
    """A tripped observation re-stamped in_bounds=true on disk is caught: the
    evaluator re-derives from facts+bound and refuses the mismatch. content_hash
    covers inputs only, so editing just the conclusion does not reseal it."""
    store = ObservationReceiptStore(tmp_path)
    path = _put_obs(store, "o-trip", facts=_facts(refusal_rate=0.95))

    d = json.loads(path.read_text())
    assert d["in_bounds"] is False
    d["in_bounds"] = True  # the lie: claim survival
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ObservationReceiptTamperError):
        store.load_for_trial("trial-1")


def test_tampered_facts_is_refused_on_load(tmp_path):
    """Editing a fact (and not re-running derivation) breaks content_hash."""
    store = ObservationReceiptStore(tmp_path)
    path = _put_obs(store, "o1")

    d = json.loads(path.read_text())
    d["facts"]["metrics"] = [["refusal_rate", 0.95]]  # tamper the input
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ObservationReceiptTamperError):
        store.load_for_trial("trial-1")


def test_swapped_trial_id_is_refused_on_load(tmp_path):
    """A file under trial-1's key whose facts carry a different trial_id is
    refused (even though its own content_hash is internally consistent)."""
    store = ObservationReceiptStore(tmp_path)
    _put_obs(store, "o1")  # creates trial-1 dir
    # Place a self-consistent OTHER-trial observation into trial-1's directory.
    other_store = ObservationReceiptStore(tmp_path)
    other_path = other_store.put(
        observation_id="o-other",
        facts=_facts(trial_id="trial-OTHER"),
        bound=BOUND,
        activation_receipt_hash=_activation("trial-OTHER").content_hash,
    )
    target = store.directory / __import__("hashlib").sha256(
        b"trial-1"
    ).hexdigest() / "o-other.json"
    target.write_text(other_path.read_text())

    with pytest.raises(ObservationReceiptTamperError):
        store.load_for_trial("trial-1")


# --- Orphan: clean miss ------------------------------------------------------


def test_load_unknown_trial_is_clean_miss(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    assert store.load_for_trial("never-observed") == []


# --- End to end: evidence_count moves off zero ONLY through real receipts -----


def _bundle_with_loaded(observations, *, required_count=3, eval_ns=5_000):
    return PromotionEvidenceBundle(
        candidate=PromotionCandidate(
            trial_id="trial-1", tunable_name=TUNABLE, trial_value=4
        ),
        activation=_activation(),
        observations=tuple(observations),
        replay=ReplayHoldoutReceipt(
            trial_id="trial-1",
            replay_subject=TUNABLE,
            passed=True,
            corpus_hash="sha256:cafe",
            frozen_corpus_hash="sha256:cafe",
            harness_version="replay_harness-v1",
            comparator_baseline_id="baseline-prior",
        ),
        operator_basis=OperatorBasisReceipt(
            trial_id="trial-1",
            operator_actor="jbeck",
            promotion_basis="held in-bounds across window",
            scope="self_governance",
            explicitly_not_auto_baseline=True,
        ),
        required_count=required_count,
        evaluation_reading=MonotonicReading(source=SRC, epoch=EPOCH, ns=eval_ns),
        freshness_horizon_ns=10_000,
        allowed_tunable_surface=frozenset({TUNABLE}),
    )


def test_evidence_count_moves_off_zero_through_real_observations(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    for i in range(3):
        _put_obs(store, f"o{i}", facts=_facts(ns=2_000 + i))
    loaded = store.load_for_trial("trial-1")
    assert len(loaded) == 3

    result = evaluate_promotion_from_evidence(_bundle_with_loaded(loaded))
    # Three walked + fresh + derived-in-bounds receipts -> eligible (synthetic
    # fixture; NOT the real max_slices=4 trial, which still has no evidence).
    assert result.eligible is True
    assert result.refusals == ()


def test_tripped_observations_do_not_count(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    for i in range(3):
        _put_obs(store, f"o{i}", facts=_facts(ns=2_000 + i, refusal_rate=0.95))
    loaded = store.load_for_trial("trial-1")
    result = evaluate_promotion_from_evidence(_bundle_with_loaded(loaded))
    assert result.eligible is False
    assert "promotion_evidence_insufficient" in result.refusals


def test_wrong_activation_binding_is_not_walkable(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    _put_obs(store, "o1", act_hash="sha256:not-the-activation")
    loaded = store.load_for_trial("trial-1")
    result = evaluate_promotion_from_evidence(_bundle_with_loaded(loaded))
    assert result.eligible is False
    assert "promotion_evidence_not_walkable" in result.refusals


def test_stale_observation_is_not_counted(tmp_path):
    store = ObservationReceiptStore(tmp_path)
    _put_obs(store, "o1", facts=_facts(ns=2_000))
    loaded = store.load_for_trial("trial-1")
    # evaluation_reading far beyond horizon -> stale.
    result = evaluate_promotion_from_evidence(
        _bundle_with_loaded(loaded, required_count=1, eval_ns=2_000 + 10_000 + 1)
    )
    assert result.eligible is False
    assert "promotion_evidence_stale" in result.refusals
