# SPDX-License-Identifier: Apache-2.0
"""P0 shadow pass — read-only classification of promotion evidence through the
admission gate. Five acceptance boundaries (the operator's scope, 2026-06-16):

1. Shadow classification cannot alter eligibility or refusal (decision_effect=none on
   report + every finding; the passed-through gate verdict is mirrored verbatim; the
   module carries no write path).
2. Adapter failure becomes an observable shadow_error finding — never a raise, never a
   promotion refusal.
3. Exploration-quarantine and reliance-refusal stay distinct for the same projected
   violation (the normal-form leash survives projection).
4. A clean, well-formed real-shaped bundle projects to all-ADMITTED — the
   licensed-conversion witness P0 lacked.
5. Absent pieces (empty chamber) are recorded absent; the shadow refuses nothing.
"""

from __future__ import annotations

from pathlib import Path

from governor.clock_witness import MonotonicReading
from governor.normal_form import (
    AdmissionIntent,
    AdmissionStatus,
    ClaimManifest,
    ClaimSpecies,
)
from governor.promotion_evidence import (
    ActivationReceipt,
    LiveSurvivalObservationReceipt,
    OperatorBasisReceipt,
    PromotionCandidate,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
)
from governor.promotion_gate import PromotionEligibility
from governor import promotion_shadow
from governor.promotion_shadow import (
    SHADOW_DECISION_EFFECT,
    ShadowReport,
    _safe_project_and_classify,
    shadow_classify_bundle,
    shadow_classify_discovered,
)

TUNABLE = "decomposition_size/max_slices"
ALLOWED = frozenset({TUNABLE})
SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"
HORIZON = 10_000


def _reading(ns: int) -> MonotonicReading:
    return MonotonicReading(source=SRC, epoch=EPOCH, ns=ns)


def _activation(trial_id="trial-1", trial_value=4) -> ActivationReceipt:
    return ActivationReceipt(
        trial_id=trial_id,
        tunable_name=TUNABLE,
        trial_value=trial_value,
        prior_baseline_value=8,
        activated_at=_reading(1_000),
    )


def _obs(obs_id, *, trial_id="trial-1", ns=2_000):
    return LiveSurvivalObservationReceipt(
        trial_id=trial_id,
        observation_id=obs_id,
        observed_at=_reading(ns),
        in_bounds=True,
        activation_receipt_hash=_activation(trial_id).content_hash,
    )


def _replay(trial_id="trial-1") -> ReplayHoldoutReceipt:
    return ReplayHoldoutReceipt(
        trial_id=trial_id,
        replay_subject=TUNABLE,
        passed=True,
        corpus_hash="sha256:cafe",
        frozen_corpus_hash="sha256:cafe",
        harness_version="replay_harness-v1",
        comparator_baseline_id="baseline-prior",
        falsification_basis="non-regression vs prior baseline",
    )


def _operator_receipt(trial_id="trial-1") -> OperatorBasisReceipt:
    return OperatorBasisReceipt(
        trial_id=trial_id,
        operator_actor="jbeck",
        promotion_basis="trial held in-bounds across window",
        scope="self_governance",
        explicitly_not_auto_baseline=True,
    )


def _clean_bundle(trial_id="trial-1") -> PromotionEvidenceBundle:
    return PromotionEvidenceBundle(
        candidate=PromotionCandidate(trial_id=trial_id, tunable_name=TUNABLE, trial_value=4),
        activation=_activation(trial_id),
        observations=tuple(_obs(f"o{i}", trial_id=trial_id, ns=2_000 + i * 100) for i in range(3)),
        replay=_replay(trial_id),
        operator_basis=_operator_receipt(trial_id),
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED,
    )


def _empty_bundle(trial_id="trial-empty") -> PromotionEvidenceBundle:
    """The cold-start chamber: a candidate but no receipts on any of the four stores."""
    return PromotionEvidenceBundle(
        candidate=PromotionCandidate(trial_id=trial_id, tunable_name=TUNABLE, trial_value=4),
        activation=None,
        observations=(),
        replay=None,
        operator_basis=None,
        required_count=3,
        evaluation_reading=_reading(5_000),
        freshness_horizon_ns=HORIZON,
        allowed_tunable_surface=ALLOWED,
    )


# --- Boundary 4: clean bundle -> all ADMITTED (licensed-conversion witness) ----


def test_clean_bundle_all_admitted():
    report = shadow_classify_bundle(_clean_bundle())
    assert isinstance(report, ShadowReport)
    # one activation + three observations + one replay + one operator_basis = 6 findings
    assert len(report.findings) == 6
    present = [f for f in report.findings if f.present]
    assert len(present) == 6
    for f in present:
        assert f.classification is AdmissionStatus.ADMITTED, (f.evidence_kind, f.reasons)
        assert f.shadow_error is None
    # the witness: nothing the gate relies on is an unlicensed conversion
    assert report.would_refuse == ()
    assert report.would_quarantine == ()


def test_species_projection_is_type_determined():
    report = shadow_classify_bundle(_clean_bundle())
    by_kind = {f.evidence_kind.split(":")[0]: f for f in report.findings}
    assert by_kind["activation"].declared_species is ClaimSpecies.OBSERVED
    assert by_kind["observation"].declared_species is ClaimSpecies.OBSERVED
    assert by_kind["replay"].declared_species is ClaimSpecies.OBSERVED
    assert by_kind["operator_basis"].declared_species is ClaimSpecies.NORMATIVE


# --- Boundary 1: shadow alters nothing -----------------------------------------


def test_decision_effect_is_none_everywhere():
    report = shadow_classify_bundle(_clean_bundle())
    assert report.decision_effect == SHADOW_DECISION_EFFECT == "none"
    for f in report.findings:
        assert f.decision_effect == "none"


def test_gate_eligibility_is_mirrored_verbatim_not_recomputed():
    elig = PromotionEligibility(eligible=False, refusals=("promotion_evidence_insufficient",))
    report = shadow_classify_bundle(_clean_bundle(), eligibility=elig)
    # mirrored verbatim — the shadow does not "fix" the gate's refusal even though it
    # classifies every piece as ADMITTED. Conversion-legitimacy != domain-eligibility.
    assert report.gate_eligible is False
    assert report.gate_refusals == ("promotion_evidence_insufficient",)
    # and the shadow's own verdict is independent: all admitted, zero would-refuse
    assert report.would_refuse == ()
    # the passed-in eligibility object is untouched (frozen; identity preserved)
    assert elig.eligible is False
    assert elig.refusals == ("promotion_evidence_insufficient",)


def test_no_eligibility_means_no_mirror():
    report = shadow_classify_bundle(_clean_bundle())
    assert report.gate_eligible is None
    assert report.gate_refusals == ()


def test_module_carries_no_write_path():
    """Static discipline (mirrors promotion_discovery's read-only test): the shadow
    source imports/contains no mutation surface."""
    src = Path(promotion_shadow.__file__).read_text()
    for forbidden in (
        "ControlBaselineStore",
        "mint_promotion",
        "operational_promote",
        ".write(",
        "open(",
        "to_dict(",  # no serialization-to-disk
    ):
        assert forbidden not in src, f"shadow must not reference {forbidden!r}"


# --- Boundary 5: empty chamber -> recorded absent, refuses nothing -------------


def test_empty_chamber_records_absent_refuses_nothing():
    report = shadow_classify_bundle(_empty_bundle())
    assert len(report.findings) == 4  # activation/observation/replay/operator_basis slots
    for f in report.findings:
        assert f.present is False
        assert f.classification is None
        assert f.reasons == ("absent",)
        assert f.decision_effect == "none"
    # the shadow refuses nothing — absence is the gate's to refuse, not the shadow's
    assert report.would_refuse == ()
    assert report.would_quarantine == ()


# --- Boundary 2: adapter failure -> observable shadow_error, never a refusal ----


def test_adapter_failure_becomes_shadow_error(monkeypatch):
    def _boom(_obs):
        raise ValueError("synthetic projection failure")

    monkeypatch.setattr(promotion_shadow, "project_observation", _boom)
    report = shadow_classify_bundle(_clean_bundle())
    errored = report.shadow_errors
    assert len(errored) == 3  # the three observations
    for f in errored:
        assert f.shadow_error is not None
        assert "synthetic projection failure" in f.shadow_error
        assert f.classification is None  # an error is NOT a refusal
        assert f.decision_effect == "none"
    # crucially: an adapter failure is not a promotion refusal
    assert report.would_refuse == ()


def test_adapter_failure_does_not_raise_out_or_touch_gate_verdict():
    # even with a broken projector, the passed-through gate verdict is untouched
    elig = PromotionEligibility(eligible=True, refusals=())
    import governor.promotion_shadow as mod

    original = mod.project_replay
    try:
        mod.project_replay = lambda _r: (_ for _ in ()).throw(RuntimeError("kaboom"))
        report = shadow_classify_bundle(_clean_bundle(), eligibility=elig)
    finally:
        mod.project_replay = original
    assert report.gate_eligible is True
    assert report.gate_refusals == ()
    assert any(f.shadow_error and "kaboom" in f.shadow_error for f in report.findings)


# --- Boundary 3: exploration-quarantine vs reliance-refusal stay distinct -------


def _overclaiming_manifest() -> ClaimManifest:
    """A hypothetical future evidence piece that overclaims: testimony presented as
    settled fact. None of the four current receipt types do this — this is the
    tripwire the shadow exists to catch before such a piece is wired into reliance."""
    return ClaimManifest(
        species=ClaimSpecies.TESTIMONIAL,
        value="some-agent-said-so",
        scope="trial-1",
        consumer="promotion",
        presented_as_fact=True,
    )


def test_same_violation_quarantines_in_exploration_refuses_in_reliance():
    explore = _safe_project_and_classify(
        kind="hypothetical",
        identity="h1",
        projector=_overclaiming_manifest,
        intent=AdmissionIntent.EXPLORATION,
    )
    rely = _safe_project_and_classify(
        kind="hypothetical",
        identity="h1",
        projector=_overclaiming_manifest,
        intent=AdmissionIntent.RELIANCE,
    )
    assert explore.classification is AdmissionStatus.QUARANTINED
    assert rely.classification is AdmissionStatus.REFUSED
    # same reason class, two times — the leash distinction survives projection
    assert "testimonial_promoted_to_fact" in explore.reasons
    assert "testimonial_promoted_to_fact" in rely.reasons
    assert explore.decision_effect == rely.decision_effect == "none"


def test_clean_bundle_under_exploration_is_candidate_not_admitted():
    report = shadow_classify_bundle(_clean_bundle(), intent=AdmissionIntent.EXPLORATION)
    present = [f for f in report.findings if f.present]
    for f in present:
        assert f.classification is AdmissionStatus.CANDIDATE  # nothing relied upon yet
    assert report.would_refuse == ()
    assert report.would_quarantine == ()


# --- discovered convenience: gate verdict passed through, not recomputed --------


def test_shadow_classify_discovered_passes_through_gate_verdict():
    class _FakeDiscovered:
        bundle = _clean_bundle()
        eligibility = PromotionEligibility(eligible=False, refusals=("promotion_replay_holdout_missing",))
        source_root = "/tmp/fake-root"

    report = shadow_classify_discovered(_FakeDiscovered())
    assert report.source == "/tmp/fake-root"
    assert report.gate_eligible is False
    assert report.gate_refusals == ("promotion_replay_holdout_missing",)
    # shadow's own conversion verdict is independent and clean
    assert report.would_refuse == ()
