# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3a — real evidence substrate (read-only) tests.

Receipts are written through the REAL producer stores onto a real (temp) disk root,
then discovered read-only. The acceptance shape: real receipts are discoverable;
missing/stale/out-of-bounds/wrong-trial/off-surface refuse (the gate derives it);
discovery performs no mint/no write; a hand-built fixture has no path into discovery.

Doctrine under test: real evidence substrate increases CUSTODY, not PERMISSION —
discovery is not admissibility.
"""

from __future__ import annotations

import inspect

from governor.clock_witness import MonotonicReading
from governor.observation_admissibility import ObservationFacts, SurvivalBound
from governor.operator_basis import REVIEW_BASIS_REVIEWED, OperatorBasisFacts
from governor.promotion_discovery import (
    DiscoveredEvidence,
    discover_promotion_bundle,
)
from governor.promotion_evidence import ActivationReceipt, PromotionCandidate
from governor.promotion_evidence_store import (
    ActivationReceiptStore,
    ObservationReceiptStore,
    OperatorBasisReceiptStore,
    ReplayHoldoutReceiptStore,
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
        trial_id=trial_id,
        tunable_name=TUNABLE,
        trial_value=trial_value,
        prior_baseline_value=8,
        activated_at=_reading(1_000),
    )


def _write_activation(root, *, trial_id="trial-1", trial_value=4):
    ActivationReceiptStore(root).put(_activation(trial_id, trial_value))


def _write_observations(root, *, trial_id="trial-1", n=3, refusal_rate=0.1, ns0=2_000):
    store = ObservationReceiptStore(root)
    act_hash = _activation(trial_id).content_hash
    for i in range(n):
        store.put(
            observation_id=f"o{i}",
            facts=ObservationFacts(
                trial_id=trial_id,
                observed_at=_reading(ns0 + i * 100),
                metrics=(("refusal_rate", refusal_rate),),
                disqualifying_events=(),
            ),
            bound=BOUND,
            activation_receipt_hash=act_hash,
        )


def _write_replay(root, *, trial_id="trial-1"):
    ReplayHoldoutReceiptStore(root).put(
        ReplayHoldoutFacts(
            trial_id=trial_id,
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
    )


def _write_operator_basis(root, *, trial_id="trial-1", basis_bundle_hash, reviewed_ns=4_000):
    OperatorBasisReceiptStore(root).put(
        OperatorBasisFacts(
            trial_id=trial_id,
            operator_id="jbeck",
            promotion_basis="trial held in-bounds across window",
            scope="self_governance",
            basis_bundle_hash=basis_bundle_hash,
            reviewed_at=_reading(reviewed_ns),
            transition_request_hash="sha256:transition",
            prior_authority_hash="sha256:prior",
            evidence_bundle_hashes=(basis_bundle_hash,),
            reviewed_verdict=REVIEW_BASIS_REVIEWED,
            explicitly_not_auto_baseline=True,
        )
    )


def _discover(root, *, candidate=None, allowed=ALLOWED, eval_ns=5_000, **overrides):
    base = dict(
        required_count=3,
        evaluation_reading=_reading(eval_ns),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=allowed,
        promote_reading=_reading(4_500),
        operator_review_horizon_ns=HORIZON,
    )
    base.update(overrides)
    return discover_promotion_bundle(root, candidate or _candidate(), **base)


def _populate_full(root):
    """Write a complete, eligible evidence set through the real producers. Returns the
    computed basis_bundle_hash (discovered before operator basis is written)."""
    _write_activation(root)
    _write_observations(root)
    _write_replay(root)
    # Discover once (operator absent) purely to obtain the bundle hash the operator
    # must have reviewed — mirrors the real flow (operator reviews the assembled bundle).
    bbh = _discover(root).basis_bundle_hash
    _write_operator_basis(root, basis_bundle_hash=bbh)
    return bbh


# --- Eligible: real receipts discovered read-only reach the gate's ELIGIBLE ----


def test_discovers_eligible_from_real_stores(tmp_path):
    _populate_full(tmp_path)
    d = _discover(tmp_path)
    assert isinstance(d, DiscoveredEvidence)
    assert d.eligible is True
    assert d.refusals == ()
    assert d.bundle.activation is not None
    assert len(d.bundle.observations) == 3
    assert d.source_root == str(tmp_path)  # custody provenance


# --- Read-only: discovery mints nothing and writes nothing --------------------


def test_discovery_is_read_only_no_mint_no_write(tmp_path):
    _populate_full(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    d = _discover(tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert before == after  # no files created/changed by discovery
    # DiscoveredEvidence carries no minting capability.
    assert not hasattr(d, "baseline")
    assert not hasattr(d, "receipt")
    assert not hasattr(d, "mint")


# --- Missing evidence refuses (the gate, not discovery, derives it) -----------


def test_empty_root_refuses_cold_start(tmp_path):
    d = _discover(tmp_path)
    assert d.eligible is False
    assert "promotion_evidence_insufficient" in d.refusals
    assert "promotion_evidence_not_walkable" in d.refusals
    assert "promotion_replay_holdout_missing" in d.refusals
    assert "promotion_operator_basis_absent" in d.refusals


def test_missing_operator_basis_refuses(tmp_path):
    _write_activation(tmp_path)
    _write_observations(tmp_path)
    _write_replay(tmp_path)
    d = _discover(tmp_path)  # no operator basis written
    assert d.eligible is False
    assert "promotion_operator_basis_absent" in d.refusals


def test_missing_replay_refuses(tmp_path):
    _write_activation(tmp_path)
    _write_observations(tmp_path)
    d = _discover(tmp_path)  # no replay
    assert d.eligible is False
    assert "promotion_replay_holdout_missing" in d.refusals


# --- Stale evidence refuses ----------------------------------------------------


def test_stale_observations_refuse(tmp_path):
    _populate_full(tmp_path)
    # Evaluate far beyond the freshness horizon -> observations stale.
    d = _discover(tmp_path, eval_ns=10_000_000)
    assert d.eligible is False
    assert "promotion_evidence_stale" in d.refusals


# --- Out-of-bounds evidence refuses (derived in_bounds, not stamped) ----------


def test_out_of_bounds_observation_refuses(tmp_path):
    _write_activation(tmp_path)
    _write_observations(tmp_path, refusal_rate=0.95)  # trips the bound -> in_bounds False
    _write_replay(tmp_path)
    bbh = _discover(tmp_path).basis_bundle_hash
    _write_operator_basis(tmp_path, basis_bundle_hash=bbh)
    d = _discover(tmp_path)
    assert d.eligible is False
    assert "promotion_evidence_insufficient" in d.refusals  # zero in-bounds observations


# --- Wrong trial refuses (nothing on disk for it) -----------------------------


def test_wrong_trial_refuses(tmp_path):
    _populate_full(tmp_path)  # populates trial-1
    d = _discover(tmp_path, candidate=_candidate(trial_id="trial-2", trial_value=4))
    assert d.eligible is False
    assert "promotion_evidence_not_walkable" in d.refusals


# --- Wrong config/surface refuses ---------------------------------------------


def test_off_surface_tunable_refuses(tmp_path):
    _populate_full(tmp_path)
    d = _discover(tmp_path, allowed=frozenset({"some_other_tunable"}))
    assert d.eligible is False
    assert "promotion_off_surface_tunable" in d.refusals


# --- Fixtures cannot masquerade as live evidence ------------------------------


def test_fixture_cannot_masquerade_as_live(tmp_path):
    """The discovery API takes a disk ``root`` + candidate — never a hand-built bundle or
    receipt. A synthetic in-memory fixture has no parameter through which to enter."""
    params = inspect.signature(discover_promotion_bundle).parameters
    # No parameter accepts pre-built evidence (bundle / receipts / observations).
    forbidden = {"bundle", "receipts", "observations", "activation", "replay", "operator_basis"}
    assert forbidden.isdisjoint(params.keys())
    # And an empty real root refuses regardless of any in-memory fixtures the caller holds.
    d = _discover(tmp_path)
    assert d.eligible is False
    assert d.source_root == str(tmp_path)


def test_discovery_does_not_admit_only_reports(tmp_path):
    """Discovery is not admissibility: a fully eligible discovery still only REPORTS a
    gate verdict; it exposes no promote/mint path. (Custody, not permission.)"""
    _populate_full(tmp_path)
    d = _discover(tmp_path)
    assert d.eligible is True
    # The only thing discovery yields is a verdict + bundle + provenance — no act.
    public = {a for a in dir(d) if not a.startswith("_")}
    assert public == {"bundle", "basis_bundle_hash", "source_root", "eligibility", "eligible", "refusals"}
