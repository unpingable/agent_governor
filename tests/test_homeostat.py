"""Tests for the Epistemic Homeostat module."""

import pytest

from governor.homeostat import (
    # Enums
    HomeostatMode,
    ExplorationContext,
    # Dataclasses
    EpistemicVitals,
    EpistemicSetpoints,
    TuningDelta,
    ExplorationBudget,
    ExplorationProfile,
    TuningGains,
    TuningClamps,
    ObservationRecord,
    # Controller
    Homeostat,
    # Pre-defined profiles
    EXPLORATION_PROFILES,
    get_profile,
    list_profiles,
    # Convenience
    create_homeostat,
    create_setpoints,
    observe_and_tune,
)


# ============================================================================
# Helpers
# ============================================================================

def _healthy_vitals(**overrides) -> EpistemicVitals:
    """Create vitals near default setpoints."""
    defaults = dict(
        revision_rate=0.05,
        contradiction_rate=0.02,
        hedge_rate=0.15,
        refusal_rate=0.01,
        support_deficit_rate=0.10,
        retrieval_coverage=0.90,
        thermal_instability=0.10,
    )
    defaults.update(overrides)
    return EpistemicVitals(**defaults)


def _stressed_vitals(**overrides) -> EpistemicVitals:
    """Create vitals far from setpoints (high urgency)."""
    defaults = dict(
        revision_rate=0.30,
        contradiction_rate=0.20,
        hedge_rate=0.02,
        refusal_rate=0.05,
        support_deficit_rate=0.50,
        retrieval_coverage=0.30,
        thermal_instability=0.60,
    )
    defaults.update(overrides)
    return EpistemicVitals(**defaults)


# ============================================================================
# HomeostatMode
# ============================================================================

class TestHomeostatMode:
    def test_values(self):
        assert HomeostatMode.OBSERVE_ONLY.value == "observe"
        assert HomeostatMode.SUGGEST.value == "suggest"
        assert HomeostatMode.ACTIVE.value == "active"

    def test_all_modes(self):
        assert len(HomeostatMode) == 3


# ============================================================================
# ExplorationContext
# ============================================================================

class TestExplorationContext:
    def test_values(self):
        assert ExplorationContext.STANDARD.value == "standard"
        assert ExplorationContext.RESEARCH.value == "research"
        assert ExplorationContext.BRAINSTORM.value == "brainstorm"
        assert ExplorationContext.HYPOTHESIS.value == "hypothesis"
        assert ExplorationContext.SYNTHESIS.value == "synthesis"
        assert ExplorationContext.DEVILS_ADVOCATE.value == "devils_advocate"
        assert ExplorationContext.CALIBRATION.value == "calibration"

    def test_all_contexts(self):
        assert len(ExplorationContext) == 7


# ============================================================================
# EpistemicVitals
# ============================================================================

class TestEpistemicVitals:
    def test_defaults(self):
        v = EpistemicVitals()
        assert v.revision_rate == 0.0
        assert v.contradiction_rate == 0.0
        assert v.retrieval_coverage == 1.0
        assert v.urgency == 0.0
        assert v.turn == 0

    def test_creation(self):
        v = _healthy_vitals()
        assert v.revision_rate == 0.05
        assert v.contradiction_rate == 0.02
        assert v.hedge_rate == 0.15

    def test_validation_rejects_negative(self):
        with pytest.raises(ValueError, match="revision_rate"):
            EpistemicVitals(revision_rate=-0.1)

    def test_validation_rejects_above_one(self):
        with pytest.raises(ValueError, match="contradiction_rate"):
            EpistemicVitals(contradiction_rate=1.5)

    def test_validation_all_rate_fields(self):
        for field in ("hedge_rate", "refusal_rate", "support_deficit_rate",
                       "retrieval_coverage", "thermal_instability", "urgency"):
            with pytest.raises(ValueError, match=field):
                EpistemicVitals(**{field: -0.01})

    def test_to_dict(self):
        v = _healthy_vitals(turn=5, total_commits=100)
        d = v.to_dict()
        assert d["revision_rate"] == 0.05
        assert d["turn"] == 5
        assert d["total_commits"] == 100
        assert "urgency" in d

    def test_roundtrip(self):
        v = _healthy_vitals(turn=3, total_commits=50, total_proposals=60)
        d = v.to_dict()
        v2 = EpistemicVitals.from_dict(d)
        assert v2.revision_rate == v.revision_rate
        assert v2.turn == v.turn
        assert v2.total_commits == v.total_commits

    def test_from_dict_ignores_extra_keys(self):
        d = _healthy_vitals().to_dict()
        d["extra_key"] = "ignored"
        v = EpistemicVitals.from_dict(d)
        assert v.revision_rate == 0.05


# ============================================================================
# EpistemicSetpoints
# ============================================================================

class TestEpistemicSetpoints:
    def test_defaults(self):
        s = EpistemicSetpoints()
        assert s.revision_target == 0.05
        assert s.contradiction_target == 0.02
        assert s.hedge_target == 0.15
        assert s.refusal_target == 0.01

    def test_compute_error_at_setpoint(self):
        s = EpistemicSetpoints()
        v = _healthy_vitals()
        errors = s.compute_error(v)
        # All errors should be ~0 (at setpoints)
        for k, val in errors.items():
            assert abs(val) < 0.001, f"{k} error should be ~0, got {val}"

    def test_compute_error_off_setpoint(self):
        s = EpistemicSetpoints()
        v = _stressed_vitals()
        errors = s.compute_error(v)
        assert errors["revision"] > 0.2
        assert errors["contradiction"] > 0.1

    def test_compute_urgency_at_setpoint(self):
        s = EpistemicSetpoints()
        v = _healthy_vitals()
        urgency = s.compute_urgency(v)
        assert urgency < 0.01  # near zero

    def test_compute_urgency_stressed(self):
        s = EpistemicSetpoints()
        v = _stressed_vitals()
        urgency = s.compute_urgency(v)
        assert urgency > 0.1  # significantly elevated

    def test_urgency_capped_at_one(self):
        s = EpistemicSetpoints()
        # Extreme vitals
        v = EpistemicVitals(
            revision_rate=1.0,
            contradiction_rate=1.0,
            hedge_rate=1.0,
            refusal_rate=1.0,
            support_deficit_rate=1.0,
            retrieval_coverage=0.0,
            thermal_instability=1.0,
        )
        urgency = s.compute_urgency(v)
        assert urgency <= 1.0

    def test_for_domain_medical(self):
        s = EpistemicSetpoints.for_domain("medical")
        assert s.revision_target < 0.05  # stricter
        assert s.contradiction_weight > 2.0  # higher weight

    def test_for_domain_legal(self):
        s = EpistemicSetpoints.for_domain("legal")
        assert s.refusal_target > 0.01  # more refusal ok

    def test_for_domain_creative(self):
        s = EpistemicSetpoints.for_domain("creative")
        assert s.revision_target > 0.05  # more revision ok
        assert s.contradiction_weight < 2.0  # lower weight

    def test_for_domain_general(self):
        s = EpistemicSetpoints.for_domain("general")
        assert s.revision_target == 0.05  # default

    def test_to_dict_roundtrip(self):
        s = EpistemicSetpoints.for_domain("medical")
        d = s.to_dict()
        s2 = EpistemicSetpoints.from_dict(d)
        assert s2.revision_target == s.revision_target
        assert s2.contradiction_weight == s.contradiction_weight

    def test_weights_all_positive(self):
        s = EpistemicSetpoints()
        for w in ("revision_weight", "contradiction_weight", "hedge_weight",
                   "refusal_weight", "support_deficit_weight",
                   "retrieval_coverage_weight", "instability_weight"):
            assert getattr(s, w) > 0


# ============================================================================
# TuningDelta
# ============================================================================

class TestTuningDelta:
    def test_defaults_are_identity(self):
        t = TuningDelta()
        assert t.confidence_ceiling_mult == 1.0
        assert t.require_support_bias == 0.0
        assert t.hedge_preference == 0.0
        assert t.revision_cost_mult == 1.0
        assert t.horizon_mult == 1.0
        assert t.source_urgency == 0.0

    def test_to_dict(self):
        t = TuningDelta(confidence_ceiling_mult=0.8, source_urgency=0.5)
        d = t.to_dict()
        assert d["confidence_ceiling_mult"] == 0.8
        assert d["source_urgency"] == 0.5

    def test_roundtrip(self):
        t = TuningDelta(
            confidence_ceiling_mult=0.9,
            hedge_preference=0.3,
            revision_cost_mult=1.5,
            source_urgency=0.4,
        )
        d = t.to_dict()
        t2 = TuningDelta.from_dict(d)
        assert t2.confidence_ceiling_mult == t.confidence_ceiling_mult
        assert t2.hedge_preference == t.hedge_preference


# ============================================================================
# ExplorationBudget
# ============================================================================

class TestExplorationBudget:
    def test_defaults(self):
        b = ExplorationBudget()
        assert b.remaining == 1.0
        assert b.can_explore()

    def test_consume(self):
        b = ExplorationBudget()
        consumed = b.consume()
        assert consumed == 0.10
        assert b.remaining == pytest.approx(0.90)

    def test_consume_custom_amount(self):
        b = ExplorationBudget()
        consumed = b.consume(0.5)
        assert consumed == 0.5
        assert b.remaining == pytest.approx(0.5)

    def test_consume_cannot_go_negative(self):
        b = ExplorationBudget(remaining=0.05)
        b.consume(0.2)
        assert b.remaining == 0.0

    def test_regenerate(self):
        b = ExplorationBudget(remaining=0.5)
        gained = b.regenerate()
        assert gained == 0.05
        assert b.remaining == pytest.approx(0.55)

    def test_regenerate_capped(self):
        b = ExplorationBudget(remaining=0.98)
        gained = b.regenerate()
        assert gained == pytest.approx(0.02)
        assert b.remaining == pytest.approx(1.0)

    def test_can_explore_false_when_depleted(self):
        b = ExplorationBudget(remaining=0.1)
        assert not b.can_explore()  # below min_to_explore=0.2

    def test_can_explore_true_at_threshold(self):
        b = ExplorationBudget(remaining=0.2)
        assert b.can_explore()

    def test_validation_remaining_bounds(self):
        with pytest.raises(ValueError, match="remaining"):
            ExplorationBudget(remaining=-0.1)
        with pytest.raises(ValueError, match="remaining"):
            ExplorationBudget(remaining=1.5)

    def test_validation_rates(self):
        with pytest.raises(ValueError, match="regen_rate"):
            ExplorationBudget(regen_rate=-0.01)
        with pytest.raises(ValueError, match="consume_rate"):
            ExplorationBudget(consume_rate=-0.01)

    def test_to_dict(self):
        b = ExplorationBudget(remaining=0.7)
        d = b.to_dict()
        assert d["remaining"] == 0.7
        assert d["can_explore"] is True
        assert "regen_rate" in d

    def test_roundtrip(self):
        b = ExplorationBudget(remaining=0.6, regen_rate=0.1, consume_rate=0.2)
        d = b.to_dict()
        b2 = ExplorationBudget.from_dict(d)
        assert b2.remaining == b.remaining
        assert b2.regen_rate == b.regen_rate
        assert b2.consume_rate == b.consume_rate

    def test_depletion_cycle(self):
        b = ExplorationBudget(remaining=1.0, consume_rate=0.15)
        turns = 0
        while b.can_explore():
            b.consume()
            turns += 1
        assert turns == 6  # 1.0 → 0.85 → 0.70 → 0.55 → 0.40 → 0.25 → 0.10
        assert not b.can_explore()


# ============================================================================
# ExplorationProfile
# ============================================================================

class TestExplorationProfile:
    def test_standard_profile(self):
        p = get_profile(ExplorationContext.STANDARD)
        assert p.budget_cost == 0.0
        assert p.urgency_dampening == 0.0

    def test_brainstorm_profile(self):
        p = get_profile(ExplorationContext.BRAINSTORM)
        assert p.confidence_ceiling_boost == 0.2
        assert p.commitment_tentativeness == 0.8
        assert p.urgency_dampening == 0.7
        assert p.budget_cost == 0.15

    def test_hypothesis_profile(self):
        p = get_profile(ExplorationContext.HYPOTHESIS)
        assert p.revision_cost_discount == 0.7
        assert p.commitment_tentativeness == 0.9

    def test_devils_advocate_profile(self):
        p = get_profile(ExplorationContext.DEVILS_ADVOCATE)
        assert p.commitment_tentativeness == 1.0  # fully provisional

    def test_calibration_no_cost(self):
        p = get_profile(ExplorationContext.CALIBRATION)
        assert p.budget_cost == 0.0
        assert p.urgency_dampening == 0.0

    def test_all_contexts_have_profiles(self):
        for ctx in ExplorationContext:
            p = get_profile(ctx)
            assert p.context == ctx

    def test_list_profiles(self):
        profiles = list_profiles()
        assert len(profiles) == len(ExplorationContext)

    def test_to_dict(self):
        p = get_profile(ExplorationContext.RESEARCH)
        d = p.to_dict()
        assert d["context"] == "research"
        assert d["confidence_ceiling_boost"] == 0.1

    def test_roundtrip(self):
        p = get_profile(ExplorationContext.SYNTHESIS)
        d = p.to_dict()
        p2 = ExplorationProfile.from_dict(d)
        assert p2.context == p.context
        assert p2.support_requirement_reduction == p.support_requirement_reduction


# ============================================================================
# TuningGains
# ============================================================================

class TestTuningGains:
    def test_defaults(self):
        g = TuningGains()
        assert g.urgency_to_confidence == -0.3
        assert g.urgency_to_hedge == 0.6

    def test_roundtrip(self):
        g = TuningGains(urgency_to_confidence=-0.5, urgency_to_support=0.8)
        d = g.to_dict()
        g2 = TuningGains.from_dict(d)
        assert g2.urgency_to_confidence == -0.5
        assert g2.urgency_to_support == 0.8


# ============================================================================
# TuningClamps
# ============================================================================

class TestTuningClamps:
    def test_identity_passthrough(self):
        c = TuningClamps()
        t = TuningDelta()
        clamped = c.clamp(t)
        assert clamped.confidence_ceiling_mult == 1.0
        assert clamped.revision_cost_mult == 1.0

    def test_clamp_confidence_high(self):
        c = TuningClamps()
        t = TuningDelta(confidence_ceiling_mult=2.0)
        clamped = c.clamp(t)
        assert clamped.confidence_ceiling_mult == 1.2  # max

    def test_clamp_confidence_low(self):
        c = TuningClamps()
        t = TuningDelta(confidence_ceiling_mult=0.1)
        clamped = c.clamp(t)
        assert clamped.confidence_ceiling_mult == 0.5  # min

    def test_clamp_revision_cost(self):
        c = TuningClamps()
        t = TuningDelta(revision_cost_mult=5.0)
        clamped = c.clamp(t)
        assert clamped.revision_cost_mult == 3.0  # max

    def test_clamp_horizon(self):
        c = TuningClamps()
        t = TuningDelta(horizon_mult=0.1)
        clamped = c.clamp(t)
        assert clamped.horizon_mult == 0.3  # min

    def test_clamp_hedge_preference(self):
        c = TuningClamps()
        t = TuningDelta(hedge_preference=1.0)
        clamped = c.clamp(t)
        assert clamped.hedge_preference == 0.6  # max


# ============================================================================
# ObservationRecord
# ============================================================================

class TestObservationRecord:
    def test_creation(self):
        v = _healthy_vitals()
        t = TuningDelta()
        r = ObservationRecord(
            vitals=v, tuning=t,
            context=ExplorationContext.STANDARD,
            budget_remaining=1.0, ema_urgency=0.0,
        )
        assert r.context == ExplorationContext.STANDARD

    def test_roundtrip(self):
        v = _healthy_vitals()
        t = TuningDelta(confidence_ceiling_mult=0.9)
        r = ObservationRecord(
            vitals=v, tuning=t,
            context=ExplorationContext.RESEARCH,
            budget_remaining=0.8, ema_urgency=0.15,
        )
        d = r.to_dict()
        r2 = ObservationRecord.from_dict(d)
        assert r2.context == ExplorationContext.RESEARCH
        assert r2.budget_remaining == 0.8
        assert r2.tuning.confidence_ceiling_mult == 0.9


# ============================================================================
# Homeostat — Basic Operations
# ============================================================================

class TestHomeostatBasics:
    def test_creation_defaults(self):
        h = Homeostat()
        assert h.mode == HomeostatMode.SUGGEST
        assert h.context == ExplorationContext.STANDARD
        assert h.ema_urgency == 0.0
        assert len(h.history) == 0

    def test_creation_custom(self):
        h = Homeostat(
            mode=HomeostatMode.ACTIVE,
            ema_alpha=0.5,
            max_history=50,
        )
        assert h.mode == HomeostatMode.ACTIVE
        assert h.ema_alpha == 0.5

    def test_reset(self):
        h = Homeostat()
        h.observe(_healthy_vitals())
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        assert len(h.history) == 1
        assert h.context == ExplorationContext.BRAINSTORM

        h.reset()
        assert h.context == ExplorationContext.STANDARD
        assert len(h.history) == 0
        assert h.ema_urgency == 0.0
        assert h.budget.remaining == 1.0


# ============================================================================
# Homeostat — Exploration
# ============================================================================

class TestHomeostatExploration:
    def test_enter_standard(self):
        h = Homeostat()
        assert h.enter_exploration(ExplorationContext.STANDARD)
        assert h.context == ExplorationContext.STANDARD

    def test_enter_research(self):
        h = Homeostat()
        assert h.enter_exploration(ExplorationContext.RESEARCH)
        assert h.context == ExplorationContext.RESEARCH

    def test_enter_same_context_succeeds(self):
        h = Homeostat()
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        assert h.enter_exploration(ExplorationContext.BRAINSTORM)

    def test_enter_fails_low_budget(self):
        h = Homeostat(budget=ExplorationBudget(remaining=0.1))
        assert not h.enter_exploration(ExplorationContext.BRAINSTORM)
        assert h.context == ExplorationContext.STANDARD  # unchanged

    def test_exit_exploration(self):
        h = Homeostat()
        h.enter_exploration(ExplorationContext.HYPOTHESIS)
        h.exit_exploration()
        assert h.context == ExplorationContext.STANDARD

    def test_context_history_tracked(self):
        h = Homeostat()
        h.enter_exploration(ExplorationContext.RESEARCH)
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        h.exit_exploration()
        hist = h.context_history
        assert len(hist) == 3
        assert hist[0] == (ExplorationContext.STANDARD, ExplorationContext.RESEARCH)
        assert hist[1] == (ExplorationContext.RESEARCH, ExplorationContext.BRAINSTORM)
        assert hist[2] == (ExplorationContext.BRAINSTORM, ExplorationContext.STANDARD)

    def test_get_profile(self):
        h = Homeostat()
        p = h.get_profile()
        assert p.context == ExplorationContext.STANDARD
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        p = h.get_profile()
        assert p.context == ExplorationContext.BRAINSTORM

    def test_budget_consumed_during_exploration(self):
        h = Homeostat()
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        h.observe(_healthy_vitals())
        assert h.budget.remaining < 1.0

    def test_budget_regenerates_in_standard(self):
        h = Homeostat(budget=ExplorationBudget(remaining=0.5))
        h.observe(_healthy_vitals())
        assert h.budget.remaining > 0.5

    def test_auto_exit_on_budget_depletion(self):
        h = Homeostat(budget=ExplorationBudget(remaining=0.25, consume_rate=0.15))
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        # Budget cost for brainstorm is 0.15
        h.observe(_healthy_vitals())  # 0.25 - 0.15 = 0.10, below min_to_explore
        assert h.context == ExplorationContext.STANDARD  # auto-exited

    def test_switch_to_standard_always_works_regardless_of_budget(self):
        h = Homeostat(budget=ExplorationBudget(remaining=0.0))
        assert h.enter_exploration(ExplorationContext.STANDARD)


# ============================================================================
# Homeostat — Observation and Tuning
# ============================================================================

class TestHomeostatObservation:
    def test_observe_returns_tuning(self):
        h = Homeostat()
        tuning = h.observe(_healthy_vitals())
        assert isinstance(tuning, TuningDelta)

    def test_observe_records_history(self):
        h = Homeostat()
        h.observe(_healthy_vitals())
        h.observe(_stressed_vitals())
        assert len(h.history) == 2

    def test_ema_urgency_updates(self):
        h = Homeostat(ema_alpha=0.5)
        h.observe(_stressed_vitals())
        assert h.ema_urgency > 0.0

    def test_ema_smoothing(self):
        h = Homeostat(ema_alpha=0.3)
        # Observe stressed, then healthy — EMA should smooth
        h.observe(_stressed_vitals())
        ema_after_stress = h.ema_urgency
        h.observe(_healthy_vitals())
        ema_after_healthy = h.ema_urgency
        # EMA should decrease but not drop to zero
        assert 0 < ema_after_healthy < ema_after_stress

    def test_history_eviction(self):
        h = Homeostat(max_history=5)
        for _ in range(10):
            h.observe(_healthy_vitals())
        assert len(h.history) == 5

    def test_observe_only_mode_returns_identity(self):
        h = Homeostat(mode=HomeostatMode.OBSERVE_ONLY)
        tuning = h.observe(_stressed_vitals())
        assert tuning.confidence_ceiling_mult == 1.0
        assert tuning.revision_cost_mult == 1.0
        assert tuning.hedge_preference == 0.0
        # But urgency is still tracked
        assert tuning.source_urgency > 0


# ============================================================================
# Homeostat — Tuning Computation
# ============================================================================

class TestHomeostatTuning:
    def test_healthy_tuning_near_identity(self):
        h = Homeostat()
        h.observe(_healthy_vitals())  # prime EMA
        tuning = h.compute_tuning(_healthy_vitals())
        # Near setpoints → low urgency → tuning near identity
        assert 0.95 <= tuning.confidence_ceiling_mult <= 1.05
        assert abs(tuning.hedge_preference) < 0.05

    def test_stressed_tuning_conservative(self):
        h = Homeostat(ema_alpha=1.0)  # instant EMA for testing
        h.observe(_stressed_vitals())
        tuning = h.compute_tuning(_stressed_vitals())
        # High urgency → lower confidence, more hedging
        assert tuning.confidence_ceiling_mult < 1.0
        assert tuning.hedge_preference > 0.0
        assert tuning.revision_cost_mult > 1.0

    def test_exploration_dampens_urgency(self):
        h = Homeostat(ema_alpha=1.0)
        h.observe(_stressed_vitals())

        # Standard tuning
        standard_tuning = h.compute_tuning(_stressed_vitals())

        # Enter brainstorm (urgency_dampening=0.7)
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        brainstorm_tuning = h.compute_tuning(_stressed_vitals())

        # Brainstorm should be less conservative
        assert brainstorm_tuning.confidence_ceiling_mult > standard_tuning.confidence_ceiling_mult
        assert brainstorm_tuning.hedge_preference < standard_tuning.hedge_preference

    def test_exploration_boosts_confidence(self):
        h = Homeostat(ema_alpha=1.0)
        h.observe(_stressed_vitals())

        h.enter_exploration(ExplorationContext.BRAINSTORM)
        tuning = h.compute_tuning(_stressed_vitals())
        # Brainstorm confidence boost = 0.2
        # Even under stress, confidence should be boosted
        assert tuning.confidence_ceiling_mult > 0.5

    def test_revision_cost_discounted_in_hypothesis(self):
        h = Homeostat(ema_alpha=1.0)
        h.observe(_stressed_vitals())

        # Standard
        h._context = ExplorationContext.STANDARD
        std = h.compute_tuning(_stressed_vitals())

        # Hypothesis (revision_cost_discount=0.7)
        h._context = ExplorationContext.HYPOTHESIS
        hyp = h.compute_tuning(_stressed_vitals())

        assert hyp.revision_cost_mult < std.revision_cost_mult

    def test_tuning_clamped(self):
        h = Homeostat(ema_alpha=1.0)
        # Feed extreme values to get extreme tuning
        extreme = EpistemicVitals(
            revision_rate=1.0,
            contradiction_rate=1.0,
            hedge_rate=0.0,
            refusal_rate=1.0,
            support_deficit_rate=1.0,
            retrieval_coverage=0.0,
            thermal_instability=1.0,
        )
        h.observe(extreme)
        tuning = h.compute_tuning(extreme)
        # Should be clamped within bounds
        assert 0.5 <= tuning.confidence_ceiling_mult <= 1.2
        assert 0.3 <= tuning.revision_cost_mult <= 3.0
        assert 0.3 <= tuning.horizon_mult <= 1.5


# ============================================================================
# Homeostat — Urgency Trend
# ============================================================================

class TestUrgencyTrend:
    def test_no_data(self):
        h = Homeostat()
        assert h.urgency_trend() == 0.0

    def test_insufficient_data(self):
        h = Homeostat()
        h.observe(_healthy_vitals())
        h.observe(_healthy_vitals())
        assert h.urgency_trend() == 0.0  # < 3 data points

    def test_increasing_urgency(self):
        h = Homeostat(ema_alpha=1.0)
        # Feed increasingly stressed vitals
        for i in range(5):
            rate = 0.05 + i * 0.05
            v = EpistemicVitals(
                revision_rate=min(rate, 1.0),
                contradiction_rate=min(rate, 1.0),
            )
            h.observe(v)
        trend = h.urgency_trend()
        assert trend > 0  # increasing

    def test_decreasing_urgency(self):
        h = Homeostat(ema_alpha=1.0)
        # Feed decreasingly stressed vitals
        for i in range(5):
            rate = 0.25 - i * 0.05
            v = EpistemicVitals(
                revision_rate=max(rate, 0.0),
                contradiction_rate=max(rate, 0.0),
            )
            h.observe(v)
        trend = h.urgency_trend()
        assert trend < 0  # decreasing

    def test_stable_urgency(self):
        h = Homeostat(ema_alpha=1.0)
        for _ in range(5):
            h.observe(_healthy_vitals())
        trend = h.urgency_trend()
        assert abs(trend) < 0.01  # flat


# ============================================================================
# Homeostat — Diagnostics
# ============================================================================

class TestHomeostatDiagnostics:
    def test_get_diagnostics(self):
        h = Homeostat()
        h.observe(_healthy_vitals())
        diag = h.get_diagnostics()
        assert diag["mode"] == "suggest"
        assert diag["context"] == "standard"
        assert "budget" in diag
        assert "ema_urgency" in diag
        assert "setpoints" in diag

    def test_recent_urgency(self):
        h = Homeostat()
        for _ in range(5):
            h.observe(_healthy_vitals())
        recent = h.recent_urgency(3)
        assert len(recent) == 3


# ============================================================================
# Homeostat — Serialisation
# ============================================================================

class TestHomeostatSerialization:
    def test_to_dict(self):
        h = Homeostat(mode=HomeostatMode.ACTIVE)
        h.observe(_healthy_vitals())
        d = h.to_dict()
        assert d["mode"] == "active"
        assert d["context"] == "standard"
        assert "budget" in d
        assert "setpoints" in d
        assert "history" in d
        assert len(d["history"]) == 1

    def test_roundtrip(self):
        h = Homeostat(mode=HomeostatMode.ACTIVE, ema_alpha=0.5, max_history=50)
        h.observe(_healthy_vitals())
        h.enter_exploration(ExplorationContext.RESEARCH)
        h.observe(_stressed_vitals())

        d = h.to_dict()
        h2 = Homeostat.from_dict(d)

        assert h2.mode == HomeostatMode.ACTIVE
        assert h2.context == ExplorationContext.RESEARCH
        assert h2.ema_alpha == 0.5
        assert len(h2.history) == 2
        assert len(h2.context_history) == 1

    def test_roundtrip_preserves_ema(self):
        h = Homeostat(ema_alpha=1.0)
        h.observe(_stressed_vitals())
        original_ema = h.ema_urgency

        d = h.to_dict()
        h2 = Homeostat.from_dict(d)
        assert h2.ema_urgency == pytest.approx(original_ema)

    def test_roundtrip_context_history(self):
        h = Homeostat()
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        h.exit_exploration()

        d = h.to_dict()
        h2 = Homeostat.from_dict(d)
        assert len(h2.context_history) == 2
        assert h2.context_history[0] == (
            ExplorationContext.STANDARD, ExplorationContext.BRAINSTORM
        )


# ============================================================================
# Convenience Functions
# ============================================================================

class TestConvenience:
    def test_create_homeostat_default(self):
        h = create_homeostat()
        assert h.mode == HomeostatMode.SUGGEST
        assert h.setpoints.revision_target == 0.05

    def test_create_homeostat_medical(self):
        h = create_homeostat(domain="medical")
        assert h.setpoints.revision_target == 0.02

    def test_create_homeostat_active(self):
        h = create_homeostat(mode=HomeostatMode.ACTIVE)
        assert h.mode == HomeostatMode.ACTIVE

    def test_create_setpoints(self):
        s = create_setpoints("creative")
        assert s.revision_target == 0.15

    def test_observe_and_tune(self):
        h = create_homeostat()
        tuning = observe_and_tune(
            h,
            revision_rate=0.20,
            contradiction_rate=0.10,
        )
        assert isinstance(tuning, TuningDelta)
        assert len(h.history) == 1

    def test_observe_and_tune_repeated(self):
        h = create_homeostat()
        for _ in range(5):
            observe_and_tune(h, revision_rate=0.10, contradiction_rate=0.05)
        assert len(h.history) == 5


# ============================================================================
# End-to-End Scenarios
# ============================================================================

class TestE2E:
    def test_standard_operation_cycle(self):
        """Normal operation: observe healthy system, get near-identity tuning."""
        h = create_homeostat()
        for _ in range(10):
            tuning = h.observe(_healthy_vitals())
        # After many healthy observations, tuning should be mild
        assert 0.9 <= tuning.confidence_ceiling_mult <= 1.1
        assert abs(tuning.hedge_preference) < 0.1

    def test_stress_response_cycle(self):
        """Under stress: system tightens constraints."""
        h = create_homeostat(mode=HomeostatMode.ACTIVE)
        # Start healthy
        for _ in range(5):
            h.observe(_healthy_vitals())
        # Stress hits
        for _ in range(5):
            tuning = h.observe(_stressed_vitals())
        # Should be more conservative
        assert tuning.confidence_ceiling_mult < 1.0
        assert tuning.hedge_preference > 0.0

    def test_exploration_then_recovery(self):
        """Enter brainstorm, deplete budget, auto-exit, regenerate."""
        h = create_homeostat()
        h.enter_exploration(ExplorationContext.BRAINSTORM)
        assert h.context == ExplorationContext.BRAINSTORM

        # Keep observing until budget depleted
        turns = 0
        while h.context != ExplorationContext.STANDARD and turns < 20:
            h.observe(_healthy_vitals())
            turns += 1

        assert h.context == ExplorationContext.STANDARD
        assert h.budget.remaining < 0.2

        # Regenerate
        for _ in range(20):
            h.observe(_healthy_vitals())
        assert h.budget.remaining > 0.5

    def test_domain_specific_sensitivity(self):
        """Medical domain is more sensitive to contradictions."""
        h_general = create_homeostat(domain="general")
        h_medical = create_homeostat(domain="medical")

        # Vitals at general setpoints except elevated contradiction.
        # Medical has higher contradiction_weight and lower target,
        # so it produces higher urgency.
        v = EpistemicVitals(
            revision_rate=0.05,
            contradiction_rate=0.10,
            hedge_rate=0.15,
            refusal_rate=0.01,
            support_deficit_rate=0.10,
            retrieval_coverage=0.90,
            thermal_instability=0.10,
        )

        u_general = h_general.setpoints.compute_urgency(v)
        u_medical = h_medical.setpoints.compute_urgency(v)
        assert u_medical > u_general  # medical is more sensitive

    def test_devils_advocate_fully_provisional(self):
        """Devil's advocate mode: everything is tentative, cheap to revise."""
        h = create_homeostat()
        h.enter_exploration(ExplorationContext.DEVILS_ADVOCATE)
        p = h.get_profile()
        assert p.commitment_tentativeness == 1.0
        assert p.revision_cost_discount == 0.8

    def test_multiple_exploration_switches(self):
        """Switch between exploration contexts."""
        h = create_homeostat()
        h.enter_exploration(ExplorationContext.RESEARCH)
        h.observe(_healthy_vitals())
        h.enter_exploration(ExplorationContext.SYNTHESIS)
        h.observe(_healthy_vitals())
        h.exit_exploration()
        h.observe(_healthy_vitals())

        assert len(h.context_history) == 3
        assert h.context == ExplorationContext.STANDARD


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    def test_zero_urgency_identity_tuning(self):
        """Zero urgency should produce near-identity tuning in STANDARD."""
        h = Homeostat(ema_alpha=1.0)
        v = _healthy_vitals()
        h.observe(v)
        tuning = h.compute_tuning(v)
        assert abs(tuning.confidence_ceiling_mult - 1.0) < 0.05
        assert abs(tuning.revision_cost_mult - 1.0) < 0.05

    def test_max_urgency_maximal_response(self):
        """Maximum urgency should produce maximal conservative tuning."""
        h = Homeostat(ema_alpha=1.0)
        v = EpistemicVitals(
            revision_rate=1.0, contradiction_rate=1.0,
            hedge_rate=0.0, refusal_rate=1.0,
            support_deficit_rate=1.0, retrieval_coverage=0.0,
            thermal_instability=1.0,
        )
        h.observe(v)
        tuning = h.compute_tuning(v)
        assert tuning.confidence_ceiling_mult < 1.0  # reduced
        assert tuning.hedge_preference > 0.0  # hedging preferred
        assert tuning.revision_cost_mult > 1.0  # revisions expensive

    def test_empty_history_queries(self):
        h = Homeostat()
        assert h.recent_urgency() == []
        assert h.urgency_trend() == 0.0
        assert len(h.history) == 0

    def test_gains_all_zero_produces_identity(self):
        """Zero gains → all tuning outputs are identity regardless of urgency."""
        g = TuningGains(
            urgency_to_confidence=0.0,
            urgency_to_support=0.0,
            urgency_to_retrieval=0.0,
            urgency_to_hedge=0.0,
            urgency_to_refuse=0.0,
            urgency_to_revision_cost=0.0,
            urgency_to_horizon=0.0,
        )
        h = Homeostat(gains=g, ema_alpha=1.0)
        h.observe(_stressed_vitals())
        tuning = h.compute_tuning(_stressed_vitals())
        assert tuning.confidence_ceiling_mult == 1.0
        assert tuning.require_support_bias == 0.0
        assert tuning.hedge_preference == 0.0
        assert tuning.revision_cost_mult == 1.0
        assert tuning.horizon_mult == 1.0

    def test_custom_clamps(self):
        """Custom clamps restrict output range."""
        c = TuningClamps(confidence_mult_min=0.9, confidence_mult_max=1.0)
        h = Homeostat(clamps=c, ema_alpha=1.0)
        h.observe(_stressed_vitals())
        tuning = h.compute_tuning(_stressed_vitals())
        assert 0.9 <= tuning.confidence_ceiling_mult <= 1.0

    def test_negative_hedge_preference_clamped(self):
        """In exploration, hedge_preference can go negative but is clamped."""
        h = Homeostat(ema_alpha=1.0)
        # Zero urgency + exploration with hedge reduction
        h.observe(_healthy_vitals())
        h._context = ExplorationContext.BRAINSTORM  # hedge_reduction=0.3
        tuning = h.compute_tuning(_healthy_vitals())
        assert tuning.hedge_preference >= -0.3  # clamped
