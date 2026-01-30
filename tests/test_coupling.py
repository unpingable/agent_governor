"""Tests for the Governor Coupling module (Homeostat → Ultrastability)."""

import pytest

from governor.coupling import (
    # Enums
    IntentVerdict,
    # Dataclasses
    ParameterMapping,
    ParameterProposal,
    TuningIntent,
    ChangeResult,
    IntentOutcome,
    # Controller
    GovernorCoupling,
    # Pre-defined
    DEFAULT_MAPPINGS,
    # Convenience
    create_coupling,
)

from governor.homeostat import TuningDelta, ExplorationContext
from governor.ultrastability import (
    UltrastabilityController,
    RegulatoryParameters,
    ParameterSpec,
    AdaptationVerdict,
    Pathology,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_controller(**overrides) -> UltrastabilityController:
    """Create a controller with default parameters."""
    return UltrastabilityController(**overrides)


def _identity_delta() -> TuningDelta:
    """TuningDelta that produces no changes (all neutral)."""
    return TuningDelta()


def _stressed_delta() -> TuningDelta:
    """TuningDelta representing high urgency (conservative tightening)."""
    return TuningDelta(
        confidence_ceiling_mult=0.8,      # lower confidence → raise evidence
        require_support_bias=0.3,          # more support → raise independence
        revision_cost_mult=1.5,            # expensive revisions
        hedge_preference=0.4,              # prefer hedging → lower glass threshold
        horizon_mult=0.7,                  # shorter horizon → shorter timeout
        source_urgency=0.6,
    )


def _exploration_delta() -> TuningDelta:
    """TuningDelta from exploration mode (loosening)."""
    return TuningDelta(
        confidence_ceiling_mult=1.15,      # boost confidence
        require_support_bias=-0.2,         # reduce support requirement
        revision_cost_mult=0.5,            # cheap revisions
        hedge_preference=-0.2,             # less hedging → raise glass threshold
        horizon_mult=1.3,                  # longer horizon → longer timeout
        source_urgency=0.1,
    )


# ============================================================================
# IntentVerdict
# ============================================================================

class TestIntentVerdict:
    def test_values(self):
        assert IntentVerdict.ACCEPTED.value == "accepted"
        assert IntentVerdict.PARTIAL.value == "partial"
        assert IntentVerdict.REJECTED.value == "rejected"
        assert IntentVerdict.FROZEN.value == "frozen"
        assert IntentVerdict.NO_MAPPINGS.value == "no_mappings"

    def test_count(self):
        assert len(IntentVerdict) == 5


# ============================================================================
# ParameterMapping
# ============================================================================

class TestParameterMapping:
    def test_compute_delta_multiplier(self):
        m = ParameterMapping(
            tuning_field="confidence_ceiling_mult",
            parameter_name="evidence_threshold",
            gain=-0.1,
            neutral=1.0,
        )
        tuning = TuningDelta(confidence_ceiling_mult=0.8)
        # (0.8 - 1.0) * -0.1 = 0.02
        assert m.compute_delta(tuning) == pytest.approx(0.02)

    def test_compute_delta_bias(self):
        m = ParameterMapping(
            tuning_field="require_support_bias",
            parameter_name="independence_threshold",
            gain=0.1,
            neutral=0.0,
        )
        tuning = TuningDelta(require_support_bias=0.3)
        # (0.3 - 0.0) * 0.1 = 0.03
        assert m.compute_delta(tuning) == pytest.approx(0.03)

    def test_compute_delta_neutral_produces_zero(self):
        m = ParameterMapping(
            tuning_field="confidence_ceiling_mult",
            parameter_name="evidence_threshold",
            gain=-0.1,
            neutral=1.0,
        )
        tuning = TuningDelta(confidence_ceiling_mult=1.0)
        assert m.compute_delta(tuning) == pytest.approx(0.0)

    def test_roundtrip(self):
        m = ParameterMapping(
            tuning_field="hedge_preference",
            parameter_name="glass_threshold",
            gain=-5.0,
            description="test",
        )
        d = m.to_dict()
        m2 = ParameterMapping.from_dict(d)
        assert m2.tuning_field == "hedge_preference"
        assert m2.gain == -5.0
        assert m2.description == "test"


# ============================================================================
# Default Mappings
# ============================================================================

class TestDefaultMappings:
    def test_count(self):
        assert len(DEFAULT_MAPPINGS) == 5

    def test_all_map_to_known_parameters(self):
        known = {"evidence_threshold", "independence_threshold", "resolution_cost",
                 "glass_threshold", "claim_timeout_ms"}
        mapped = {m.parameter_name for m in DEFAULT_MAPPINGS}
        assert mapped == known

    def test_all_map_from_tuning_fields(self):
        for m in DEFAULT_MAPPINGS:
            assert hasattr(TuningDelta(), m.tuning_field)


# ============================================================================
# TuningIntent
# ============================================================================

class TestTuningIntent:
    def test_from_identity_delta_produces_no_proposals(self):
        intent = TuningIntent.from_tuning_delta(_identity_delta())
        assert len(intent.proposals) == 0

    def test_from_stressed_delta_produces_proposals(self):
        intent = TuningIntent.from_tuning_delta(_stressed_delta())
        assert len(intent.proposals) > 0
        # Should have proposals for evidence_threshold, independence_threshold, etc.
        params = {p.parameter_name for p in intent.proposals}
        assert "evidence_threshold" in params

    def test_from_delta_context(self):
        intent = TuningIntent.from_tuning_delta(
            _stressed_delta(), context="brainstorm"
        )
        assert intent.source_context == "brainstorm"
        assert intent.source_urgency == 0.6

    def test_timestamp_auto_set(self):
        intent = TuningIntent(proposals=[])
        assert intent.timestamp != ""

    def test_roundtrip(self):
        intent = TuningIntent.from_tuning_delta(_stressed_delta(), context="research")
        d = intent.to_dict()
        intent2 = TuningIntent.from_dict(d)
        assert intent2.source_context == "research"
        assert intent2.source_urgency == intent.source_urgency
        assert len(intent2.proposals) == len(intent.proposals)

    def test_custom_mappings(self):
        mappings = [ParameterMapping(
            tuning_field="confidence_ceiling_mult",
            parameter_name="evidence_threshold",
            gain=-1.0,
            neutral=1.0,
        )]
        tuning = TuningDelta(confidence_ceiling_mult=0.5)
        intent = TuningIntent.from_tuning_delta(tuning, mappings=mappings)
        assert len(intent.proposals) == 1
        assert intent.proposals[0].delta == pytest.approx(0.5)


# ============================================================================
# IntentOutcome
# ============================================================================

class TestIntentOutcome:
    def test_any_accepted(self):
        o = IntentOutcome(verdict=IntentVerdict.ACCEPTED, accepted_count=2)
        assert o.any_accepted

    def test_none_accepted(self):
        o = IntentOutcome(verdict=IntentVerdict.REJECTED, accepted_count=0)
        assert not o.any_accepted

    def test_roundtrip(self):
        o = IntentOutcome(
            verdict=IntentVerdict.PARTIAL,
            changes=[
                ChangeResult(
                    parameter_name="evidence_threshold",
                    accepted=True,
                    old_value=0.7,
                    new_value=0.72,
                    proposed_delta=0.02,
                    actual_delta=0.02,
                ),
                ChangeResult(
                    parameter_name="glass_threshold",
                    accepted=False,
                    reject_reason="at bounds",
                ),
            ],
            accepted_count=1,
            rejected_count=1,
        )
        d = o.to_dict()
        o2 = IntentOutcome.from_dict(d)
        assert o2.verdict == IntentVerdict.PARTIAL
        assert o2.accepted_count == 1
        assert len(o2.changes) == 2
        assert o2.changes[0].accepted
        assert not o2.changes[1].accepted


# ============================================================================
# GovernorCoupling — Basic
# ============================================================================

class TestCouplingBasics:
    def test_creation(self):
        c = _make_controller()
        gc = GovernorCoupling(c)
        assert gc.total_submissions == 0
        assert gc.controller is c

    def test_create_coupling_convenience(self):
        gc = create_coupling()
        assert gc.controller is not None
        assert len(gc.mappings) == 5

    def test_create_coupling_with_controller(self):
        c = _make_controller()
        gc = create_coupling(c)
        assert gc.controller is c


# ============================================================================
# GovernorCoupling — Submit
# ============================================================================

class TestCouplingSubmit:
    def test_identity_delta_no_mappings(self):
        gc = create_coupling()
        outcome = gc.submit_tuning_delta(_identity_delta())
        assert outcome.verdict == IntentVerdict.NO_MAPPINGS
        assert outcome.accepted_count == 0

    def test_stressed_delta_accepted(self):
        gc = create_coupling()
        outcome = gc.submit_tuning_delta(_stressed_delta())
        # Some proposals should be accepted
        assert outcome.verdict in (IntentVerdict.ACCEPTED, IntentVerdict.PARTIAL)
        assert outcome.accepted_count > 0

    def test_parameters_actually_changed(self):
        c = _make_controller()
        gc = GovernorCoupling(c)

        old_evidence = c.parameters.value("evidence_threshold")
        gc.submit_tuning_delta(_stressed_delta())
        new_evidence = c.parameters.value("evidence_threshold")

        # Stressed delta lowers confidence → should raise evidence threshold
        assert new_evidence != old_evidence

    def test_frozen_controller_rejects_all(self):
        c = _make_controller()
        c.freeze("test freeze")
        gc = GovernorCoupling(c)

        outcome = gc.submit_tuning_delta(_stressed_delta())
        assert outcome.verdict == IntentVerdict.FROZEN
        assert "test freeze" in outcome.freeze_reason

    def test_empty_intent_no_mappings(self):
        gc = create_coupling()
        intent = TuningIntent(proposals=[])
        outcome = gc.submit(intent)
        assert outcome.verdict == IntentVerdict.NO_MAPPINGS

    def test_unknown_parameter_rejected(self):
        c = _make_controller()
        gc = GovernorCoupling(c)
        intent = TuningIntent(proposals=[
            ParameterProposal(
                parameter_name="nonexistent_param",
                delta=1.0,
                source_field="test",
                source_value=1.0,
            )
        ])
        outcome = gc.submit(intent)
        assert outcome.verdict == IntentVerdict.REJECTED
        assert outcome.changes[0].reject_reason == "unknown parameter: nonexistent_param"

    def test_submission_logged(self):
        gc = create_coupling()
        gc.submit_tuning_delta(_stressed_delta())
        assert gc.total_submissions == 1
        assert len(gc.history) == 1

    def test_multiple_submissions(self):
        gc = create_coupling()
        gc.submit_tuning_delta(_stressed_delta())
        gc.submit_tuning_delta(_exploration_delta())
        gc.submit_tuning_delta(_identity_delta())
        assert gc.total_submissions == 3


# ============================================================================
# GovernorCoupling — Bounds Enforcement
# ============================================================================

class TestCouplingBounds:
    def test_change_clamped_to_step(self):
        """Proposed delta larger than step should be clamped."""
        # evidence_threshold has step=0.05
        c = _make_controller()
        gc = GovernorCoupling(c)

        # Create a mapping with very large gain
        mappings = [ParameterMapping(
            tuning_field="confidence_ceiling_mult",
            parameter_name="evidence_threshold",
            gain=-10.0,       # large gain → large delta
            neutral=1.0,
        )]
        gc.mappings = mappings

        tuning = TuningDelta(confidence_ceiling_mult=0.5)
        # delta = (0.5 - 1.0) * -10.0 = 5.0 (way over step=0.05)
        outcome = gc.submit_tuning_delta(tuning)
        # Should still work, but clamped
        if outcome.accepted_count > 0:
            change = [c for c in outcome.changes if c.accepted][0]
            assert abs(change.actual_delta) <= 0.05 + 1e-9

    def test_at_ceiling_no_change(self):
        """Parameter at ceiling can't increase further."""
        specs = [ParameterSpec(
            name="evidence_threshold",
            current=1.0,      # at ceiling
            floor=0.3,
            ceiling=1.0,
            step=0.05,
        )]
        c = UltrastabilityController(parameters=RegulatoryParameters(specs))
        gc = GovernorCoupling(c, mappings=[ParameterMapping(
            tuning_field="confidence_ceiling_mult",
            parameter_name="evidence_threshold",
            gain=-0.1,
            neutral=1.0,
        )])

        # Try to increase (confidence down → evidence up)
        tuning = TuningDelta(confidence_ceiling_mult=0.8)
        outcome = gc.submit_tuning_delta(tuning)
        # Should be rejected — already at ceiling
        assert outcome.changes[0].accepted is False
        assert "at bounds" in outcome.changes[0].reject_reason or "no effective" in outcome.changes[0].reject_reason

    def test_at_floor_no_decrease(self):
        """Parameter at floor can't decrease further."""
        specs = [ParameterSpec(
            name="glass_threshold",
            current=5.0,       # at floor
            floor=5.0,
            ceiling=50.0,
            step=2.0,
        )]
        c = UltrastabilityController(parameters=RegulatoryParameters(specs))
        gc = GovernorCoupling(c, mappings=[ParameterMapping(
            tuning_field="hedge_preference",
            parameter_name="glass_threshold",
            gain=-5.0,         # positive hedge → decrease glass
            neutral=0.0,
        )])

        # Positive hedge_preference → negative delta on glass_threshold
        tuning = TuningDelta(hedge_preference=0.5)
        outcome = gc.submit_tuning_delta(tuning)
        assert outcome.changes[0].accepted is False


# ============================================================================
# GovernorCoupling — Adaptation Records
# ============================================================================

class TestCouplingRecords:
    def test_accepted_changes_logged_in_controller(self):
        c = _make_controller()
        gc = GovernorCoupling(c)
        gc.submit_tuning_delta(_stressed_delta())

        # Controller should have adaptation records
        records = c.history.records
        assert len(records) > 0
        assert all("coupling:" in r.reason for r in records)

    def test_rejected_changes_not_logged(self):
        c = _make_controller()
        c.freeze("frozen")
        gc = GovernorCoupling(c)
        gc.submit_tuning_delta(_stressed_delta())

        # No records should be added (frozen)
        assert len(c.history.records) == 0


# ============================================================================
# GovernorCoupling — Diagnostics
# ============================================================================

class TestCouplingDiagnostics:
    def test_get_diagnostics(self):
        gc = create_coupling()
        gc.submit_tuning_delta(_stressed_delta())
        diag = gc.get_diagnostics()
        assert diag["total_submissions"] == 1
        assert "acceptance_rate" in diag
        assert "controller_frozen" in diag
        assert diag["mapping_count"] == 5

    def test_acceptance_rate_empty(self):
        gc = create_coupling()
        assert gc.acceptance_rate() == 0.0

    def test_acceptance_rate_all_accepted(self):
        gc = create_coupling()
        gc.submit_tuning_delta(_stressed_delta())
        # At least some accepted
        rate = gc.acceptance_rate()
        assert rate > 0.0

    def test_acceptance_rate_frozen(self):
        c = _make_controller()
        c.freeze("test")
        gc = GovernorCoupling(c)
        gc.submit_tuning_delta(_stressed_delta())
        gc.submit_tuning_delta(_stressed_delta())
        assert gc.acceptance_rate() == 0.0


# ============================================================================
# GovernorCoupling — Serialisation
# ============================================================================

class TestCouplingSerialization:
    def test_roundtrip(self):
        c = _make_controller()
        gc = GovernorCoupling(c)
        gc.submit_tuning_delta(_stressed_delta())
        gc.submit_tuning_delta(_exploration_delta())

        d = gc.to_dict()
        gc2 = GovernorCoupling.from_dict(d, controller=c)

        assert gc2.total_submissions == 2
        assert len(gc2.mappings) == len(gc.mappings)

    def test_roundtrip_preserves_verdicts(self):
        c = _make_controller()
        gc = GovernorCoupling(c)
        gc.submit_tuning_delta(_stressed_delta())

        d = gc.to_dict()
        gc2 = GovernorCoupling.from_dict(d, controller=c)

        _, outcome = gc2.history[0]
        assert outcome.verdict in IntentVerdict

    def test_history_eviction(self):
        gc = create_coupling()
        gc.max_history = 3
        for _ in range(5):
            gc.submit_tuning_delta(_stressed_delta())
        assert gc.total_submissions == 3


# ============================================================================
# End-to-End
# ============================================================================

class TestE2E:
    def test_full_pipeline_standard(self):
        """Homeostat under stress → coupling → controller accepts changes."""
        from governor.homeostat import Homeostat, EpistemicVitals, HomeostatMode

        h = Homeostat(mode=HomeostatMode.ACTIVE, ema_alpha=1.0)
        c = UltrastabilityController()
        gc = GovernorCoupling(c)

        # Stressed vitals
        vitals = EpistemicVitals(
            revision_rate=0.30,
            contradiction_rate=0.20,
            hedge_rate=0.02,
            refusal_rate=0.05,
        )
        tuning = h.observe(vitals)

        # Submit through coupling
        outcome = gc.submit_tuning_delta(tuning, context=h.context.value)
        assert outcome.verdict != IntentVerdict.FROZEN
        # Some parameters should have changed
        assert outcome.accepted_count > 0 or outcome.verdict == IntentVerdict.REJECTED

    def test_full_pipeline_exploration(self):
        """Exploration mode → tuning with boosts → coupling → accepted."""
        from governor.homeostat import Homeostat, EpistemicVitals, HomeostatMode

        h = Homeostat(mode=HomeostatMode.ACTIVE, ema_alpha=1.0)
        c = UltrastabilityController()
        gc = GovernorCoupling(c)

        h.enter_exploration(ExplorationContext.BRAINSTORM)

        vitals = EpistemicVitals(revision_rate=0.10, contradiction_rate=0.05)
        tuning = h.observe(vitals)
        outcome = gc.submit_tuning_delta(tuning, context=h.context.value)

        # Should have processed without freezing
        assert outcome.verdict != IntentVerdict.FROZEN

    def test_frozen_pipeline(self):
        """Frozen controller rejects all intents regardless of urgency."""
        from governor.homeostat import Homeostat, EpistemicVitals, HomeostatMode

        h = Homeostat(mode=HomeostatMode.ACTIVE, ema_alpha=1.0)
        c = UltrastabilityController()
        c.freeze("pathology detected", [Pathology.OSCILLATION])
        gc = GovernorCoupling(c)

        vitals = EpistemicVitals(revision_rate=0.50, contradiction_rate=0.40)
        tuning = h.observe(vitals)
        outcome = gc.submit_tuning_delta(tuning)

        assert outcome.verdict == IntentVerdict.FROZEN

    def test_unfreeze_then_accept(self):
        """After unfreeze, intents are processed normally."""
        c = UltrastabilityController()
        c.freeze("test pathology")
        gc = GovernorCoupling(c)

        # Frozen → rejected
        outcome1 = gc.submit_tuning_delta(_stressed_delta())
        assert outcome1.verdict == IntentVerdict.FROZEN

        # Unfreeze
        c.unfreeze("human review completed")

        # Now should work
        outcome2 = gc.submit_tuning_delta(_stressed_delta())
        assert outcome2.verdict != IntentVerdict.FROZEN

    def test_repeated_submissions_move_parameters(self):
        """Multiple submissions accumulate parameter changes."""
        c = _make_controller()
        gc = GovernorCoupling(c)

        initial_evidence = c.parameters.value("evidence_threshold")
        for _ in range(5):
            gc.submit_tuning_delta(_stressed_delta())

        final_evidence = c.parameters.value("evidence_threshold")
        # After multiple stressed submissions, evidence threshold should have moved
        assert final_evidence != initial_evidence

    def test_parameters_stay_within_bounds(self):
        """Even after many submissions, parameters never exceed bounds."""
        c = _make_controller()
        gc = GovernorCoupling(c)

        for _ in range(50):
            gc.submit_tuning_delta(_stressed_delta())

        for spec in c.parameters.all_specs:
            assert spec.floor <= spec.current <= spec.ceiling, (
                f"{spec.name}: {spec.current} not in [{spec.floor}, {spec.ceiling}]"
            )
