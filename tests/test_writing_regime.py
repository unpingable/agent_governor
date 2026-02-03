"""Tests for writing_regime.py — affect regime system."""

import pytest

from governor.writing_regime import (
    COMMITTEE_PENALTY,
    HEDGE_PENALTY,
    MEANING_DENSITY_CAP,
    META_KILL_PENALTY,
    MIN_CONSEQUENCE_TOKENS,
    NEUTRAL_ACTIVE_CONSTRAINTS,
    NEUTRAL_INACTIVE_CONSTRAINTS,
    RP_FLOOR,
    SELF_REF_PENALTY,
    AffectRegime,
    ConsistencyResult,
    DramaConstraints,
    MeaningLagResult,
    MixerConfig,
    NeutralTransitionGuard,
    NeutralTransitionGuardConfig,
    RegimeHysteresis,
    RegimeHysteresisConfig,
    RegimeMixer,
    RegimeVector,
    RpResult,
    RpScorer,
    SincerityTracker,
    StakesProtectionResult,
    TragedyConstraints,
    is_active_in_neutral,
    is_inactive_in_neutral,
)


# =============================================================================
# AffectRegime tests
# =============================================================================


class TestAffectRegime:
    """Test AffectRegime enum."""

    def test_values(self):
        assert AffectRegime.COMEDY.value == "comedy"
        assert AffectRegime.TRAGEDY.value == "tragedy"
        assert AffectRegime.SINCERITY.value == "sincerity"
        assert AffectRegime.DRAMA.value == "drama"
        assert AffectRegime.NEUTRAL.value == "neutral"

    def test_string_conversion(self):
        assert str(AffectRegime.COMEDY) == "AffectRegime.COMEDY"


# =============================================================================
# RegimeVector tests
# =============================================================================


class TestRegimeVector:
    """Test RegimeVector dataclass."""

    def test_default_is_neutral(self):
        v = RegimeVector()
        assert v.w_n == 1.0
        assert v.dominant() == AffectRegime.NEUTRAL

    def test_normalize_sum_to_one(self):
        v = RegimeVector(w_c=2.0, w_t=3.0)
        n = v.normalize()
        total = n.w_c + n.w_t + n.w_s + n.w_d + n.w_n
        assert abs(total - 1.0) < 0.001

    def test_normalize_zero_vector(self):
        v = RegimeVector(w_c=0, w_t=0, w_s=0, w_d=0, w_n=0)
        n = v.normalize()
        assert n.dominant() == AffectRegime.NEUTRAL

    def test_dominant_comedy(self):
        v = RegimeVector(w_c=0.8, w_n=0.2)
        assert v.dominant() == AffectRegime.COMEDY

    def test_dominant_tragedy(self):
        v = RegimeVector(w_t=0.8, w_n=0.2)
        assert v.dominant() == AffectRegime.TRAGEDY

    def test_dominant_sincerity(self):
        v = RegimeVector(w_s=0.8, w_n=0.2)
        assert v.dominant() == AffectRegime.SINCERITY

    def test_dominant_drama(self):
        v = RegimeVector(w_d=0.8, w_n=0.2)
        assert v.dominant() == AffectRegime.DRAMA

    def test_factory_neutral(self):
        v = RegimeVector.neutral()
        assert v.w_n == 1.0
        assert v.w_c == 0.0

    def test_factory_comedy(self):
        v = RegimeVector.comedy(0.8)
        assert v.dominant() == AffectRegime.COMEDY

    def test_factory_tragedy(self):
        v = RegimeVector.tragedy(0.8)
        assert v.dominant() == AffectRegime.TRAGEDY

    def test_from_dict(self):
        d = {"comedy": 0.5, "tragedy": 0.3, "neutral": 0.2}
        v = RegimeVector.from_dict(d)
        assert v.w_c == 0.5
        assert v.w_t == 0.3

    def test_to_dict(self):
        v = RegimeVector(w_c=0.6, w_t=0.4)
        d = v.to_dict()
        assert d["comedy"] == 0.6
        assert d["tragedy"] == 0.4

    def test_distance_same(self):
        v = RegimeVector.comedy(0.8)
        assert v.distance(v) == 0.0

    def test_distance_different(self):
        v1 = RegimeVector(w_c=1.0)
        v2 = RegimeVector(w_t=1.0)
        assert v1.distance(v2) > 0


# =============================================================================
# RegimeHysteresis tests
# =============================================================================


class TestRegimeHysteresis:
    """Test RegimeHysteresis controller."""

    def test_initial_state_neutral(self):
        h = RegimeHysteresis()
        assert h.dominant == AffectRegime.NEUTRAL

    def test_update_toward_signal(self):
        h = RegimeHysteresis()
        signal = RegimeVector.comedy(0.9)
        h.update(signal, confidence=0.9, tokens_elapsed=300)
        # Should have moved toward comedy but may not be dominant yet due to rate limiting
        assert h.current_vector.w_c > 0

    def test_update_respects_dwell_time(self):
        config = RegimeHysteresisConfig(min_dwell_tokens=200)
        h = RegimeHysteresis(config)

        # Try to switch before dwell time
        signal = RegimeVector.comedy(0.9)
        h.update(signal, confidence=0.9, tokens_elapsed=100)
        # Should not have switched dominant regime
        assert h.dominant == AffectRegime.NEUTRAL

    def test_update_respects_confidence(self):
        config = RegimeHysteresisConfig(switch_cost=0.8)
        h = RegimeHysteresis(config)

        # Low confidence update
        signal = RegimeVector.comedy(0.9)
        h.update(signal, confidence=0.5, tokens_elapsed=300)
        # Should not have switched
        assert h.dominant == AffectRegime.NEUTRAL

    def test_cooldown_after_switch(self):
        config = RegimeHysteresisConfig(
            min_dwell_tokens=10,
            cooldown_tokens=50,
            max_shift_rate=1.0,  # fast shift
        )
        h = RegimeHysteresis(config)

        # Force a switch
        h.update(RegimeVector.comedy(1.0), confidence=0.95, tokens_elapsed=20)

        # During cooldown, updates should be ignored
        current = h.current_vector
        h.update(RegimeVector.tragedy(1.0), confidence=0.95, tokens_elapsed=10)
        # Vector should not have changed much
        assert h.current_vector.distance(current) < 0.1

    def test_thrash_rate_calculation(self):
        h = RegimeHysteresis()
        # Manually add shift history
        h._state.shift_history = [100, 500, 800]
        h._state.total_tokens = 1000
        rate = h.thrash_rate(1000)
        assert rate == 3.0

    def test_is_thrashing(self):
        config = RegimeHysteresisConfig(thrash_threshold=2.0)
        h = RegimeHysteresis(config)
        h._state.shift_history = [100, 300, 500]
        h._state.total_tokens = 1000
        assert h.is_thrashing()

    def test_reset(self):
        h = RegimeHysteresis()
        h.update(RegimeVector.comedy(0.9), confidence=0.9, tokens_elapsed=300)
        h.reset()
        assert h.dominant == AffectRegime.NEUTRAL


# =============================================================================
# RpScorer tests
# =============================================================================


class TestRpScorer:
    """Test Rp (perceived risk) scoring for comedy."""

    def test_clean_text_high_rp(self):
        scorer = RpScorer()
        result = scorer.calculate_rp("The dragon flew over the mountain.")
        assert result.rp_score == 1.0
        assert not result.below_floor

    def test_hedges_lower_rp(self):
        scorer = RpScorer()
        text = "Maybe perhaps I think it sort of works."
        result = scorer.calculate_rp(text)
        assert result.hedge_count >= 4
        assert result.rp_score < 1.0

    def test_self_ref_kills_rp(self):
        scorer = RpScorer()
        text = "As an AI, I should note that I'm just a language model."
        result = scorer.calculate_rp(text)
        assert result.self_ref_count >= 2
        assert result.rp_score < 0.8

    def test_committee_lowers_rp(self):
        scorer = RpScorer()
        text = "On the one hand, to be fair, it's complicated."
        result = scorer.calculate_rp(text)
        assert result.committee_count >= 2
        assert result.rp_score < 1.0

    def test_meta_kill_detected(self):
        scorer = RpScorer()
        text = "I'm sorry, that joke didn't land."
        result = scorer.calculate_rp(text)
        assert result.meta_kill_found
        assert result.rp_score <= 0.7  # 1.0 - 0.30 = 0.70

    def test_below_floor(self):
        scorer = RpScorer(floor=0.6)
        text = """
        As an AI, I should note that maybe perhaps on the one hand
        I'm sorry if that's complicated.
        """
        result = scorer.calculate_rp(text)
        assert result.below_floor

    def test_rp_clamped_at_zero(self):
        scorer = RpScorer()
        # Massive penalties
        text = " ".join([
            "As an AI, I should note, I'm just a model.",
            "I want to be clear, maybe perhaps on the one hand.",
        ] * 5)
        result = scorer.calculate_rp(text)
        assert result.rp_score >= 0.0

    def test_to_dict(self):
        scorer = RpScorer()
        result = scorer.calculate_rp("Text")
        d = result.to_dict()
        assert "rp_score" in d
        assert "hedge_count" in d


# =============================================================================
# TragedyConstraints tests
# =============================================================================


class TestTragedyConstraints:
    """Test tragedy constraints (meaning-lag)."""

    def test_clean_text_low_density(self):
        constraints = TragedyConstraints()
        result = constraints.check_meaning_lag("The rain fell silently.")
        assert result.meaning_word_count == 0
        assert not result.exceeds_density_cap

    def test_meaning_words_detected(self):
        constraints = TragedyConstraints()
        text = "Because the lesson means we understand the reason."
        result = constraints.check_meaning_lag(text)
        assert result.meaning_word_count >= 4

    def test_exceeds_density_cap(self):
        constraints = TragedyConstraints(density_cap=2.0)
        # High density of meaning words
        text = "Because therefore thus means represents symbolizes lesson."
        result = constraints.check_meaning_lag(text)
        assert result.exceeds_density_cap

    def test_is_meaning_allowed(self):
        constraints = TragedyConstraints(min_consequence_tokens=50)
        assert not constraints.is_meaning_allowed(30)
        assert constraints.is_meaning_allowed(60)

    def test_to_dict(self):
        constraints = TragedyConstraints()
        result = constraints.check_meaning_lag("Text")
        d = result.to_dict()
        assert "meaning_density" in d


# =============================================================================
# SincerityTracker tests
# =============================================================================


class TestSincerityTracker:
    """Test sincerity consistency tracking."""

    def test_clean_text_no_manifesto(self):
        tracker = SincerityTracker()
        result = tracker.check_consistency("I had a good day.")
        assert not result.manifesto_detected

    def test_manifesto_detected(self):
        tracker = SincerityTracker()
        text = "I believe in truth. I believe in justice. I believe in honesty."
        result = tracker.check_consistency(text)
        assert result.manifesto_detected

    def test_repeated_exhortation_detected(self):
        tracker = SincerityTracker()
        text = "We must fight. We must resist. We must prevail."
        result = tracker.check_consistency(text)
        assert result.manifesto_detected

    def test_history_tracked(self):
        tracker = SincerityTracker()
        tracker.check_consistency("First message.")
        tracker.check_consistency("Second message.")
        assert len(tracker._history) == 2

    def test_reset(self):
        tracker = SincerityTracker()
        tracker.check_consistency("Message.")
        tracker.reset()
        assert len(tracker._history) == 0


# =============================================================================
# DramaConstraints tests
# =============================================================================


class TestDramaConstraints:
    """Test drama constraints (stakes protection)."""

    def test_low_drama_no_protection(self):
        constraints = DramaConstraints(drama_threshold=0.4)
        result = constraints.check_stakes_deflation(
            comedy_target="work",
            stakes_anchors=["work"],
            drama_weight=0.2,
        )
        assert not result.comedy_targets_stakes

    def test_high_drama_stakes_protected(self):
        constraints = DramaConstraints(drama_threshold=0.4)
        result = constraints.check_stakes_deflation(
            comedy_target="work deadline",
            stakes_anchors=["deadline", "job"],
            drama_weight=0.6,
        )
        assert result.comedy_targets_stakes
        assert "deadline" in result.stakes_anchors_at_risk

    def test_no_overlap_safe(self):
        constraints = DramaConstraints(drama_threshold=0.4)
        result = constraints.check_stakes_deflation(
            comedy_target="weather",
            stakes_anchors=["deadline", "job"],
            drama_weight=0.6,
        )
        assert not result.comedy_targets_stakes

    def test_to_dict(self):
        constraints = DramaConstraints()
        result = constraints.check_stakes_deflation("topic", [], 0.5)
        d = result.to_dict()
        assert "comedy_targets_stakes" in d


# =============================================================================
# RegimeMixer tests
# =============================================================================


class TestRegimeMixer:
    """Test regime mixer (hybrid safety buffers)."""

    def test_comedy_blocked_after_sincerity(self):
        config = MixerConfig(sincerity_buffer_tokens=50)
        mixer = RegimeMixer(config)
        mixer.advance_tokens(10, sincerity_event=True)
        assert not mixer.comedy_allowed()

    def test_comedy_allowed_after_buffer(self):
        config = MixerConfig(sincerity_buffer_tokens=50)
        mixer = RegimeMixer(config)
        mixer.advance_tokens(10, sincerity_event=True)
        mixer.advance_tokens(100)
        assert mixer.comedy_allowed()

    def test_meaning_blocked_during_lag(self):
        config = MixerConfig(tragedy_meaning_lag_tokens=50)
        mixer = RegimeMixer(config)
        mixer.advance_tokens(10, consequence_event=True)
        assert not mixer.meaning_allowed()

    def test_meaning_allowed_after_lag(self):
        config = MixerConfig(tragedy_meaning_lag_tokens=50)
        mixer = RegimeMixer(config)
        mixer.advance_tokens(10, consequence_event=True)
        mixer.advance_tokens(100)
        assert mixer.meaning_allowed()

    def test_stakes_protection(self):
        config = MixerConfig(stakes_protection_threshold=0.4)
        mixer = RegimeMixer(config)
        mixer.set_stakes_anchors(["deadline", "job"])

        result = mixer.check_comedy_target("deadline joke", drama_weight=0.6)
        assert result.comedy_targets_stakes

    def test_reset(self):
        mixer = RegimeMixer()
        mixer.advance_tokens(10, sincerity_event=True)
        mixer.reset()
        assert mixer.comedy_allowed()


# =============================================================================
# Constants tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_rp_floor_reasonable(self):
        assert 0.0 < RP_FLOOR < 1.0

    def test_penalties_reasonable(self):
        assert 0.0 < HEDGE_PENALTY < 0.5
        assert 0.0 < SELF_REF_PENALTY < 0.5
        assert 0.0 < COMMITTEE_PENALTY < 0.5
        assert 0.0 < META_KILL_PENALTY < 0.5

    def test_min_consequence_tokens_reasonable(self):
        assert MIN_CONSEQUENCE_TOKENS > 0

    def test_meaning_density_cap_reasonable(self):
        assert MEANING_DENSITY_CAP > 0


# =============================================================================
# Dataclass tests
# =============================================================================


class TestDataclasses:
    """Test dataclass defaults."""

    def test_rp_result_defaults(self):
        result = RpResult()
        assert result.rp_score == 1.0
        assert not result.below_floor

    def test_meaning_lag_result_defaults(self):
        result = MeaningLagResult()
        assert result.meaning_word_count == 0

    def test_consistency_result_defaults(self):
        result = ConsistencyResult()
        assert not result.manifesto_detected

    def test_stakes_protection_result_defaults(self):
        result = StakesProtectionResult()
        assert not result.comedy_targets_stakes


# =============================================================================
# NeutralTransitionGuard Tests
# =============================================================================


class TestNeutralTransitionGuardConfig:
    def test_defaults(self):
        config = NeutralTransitionGuardConfig()
        assert config.min_signal_tokens == 30
        assert config.explicit_trigger_override is True
        assert config.confidence_threshold == 0.4

    def test_custom_values(self):
        config = NeutralTransitionGuardConfig(
            min_signal_tokens=50,
            confidence_threshold=0.5,
        )
        assert config.min_signal_tokens == 50
        assert config.confidence_threshold == 0.5


class TestNeutralTransitionGuard:
    def test_default_init(self):
        guard = NeutralTransitionGuard()
        assert guard._config.min_signal_tokens == 30

    def test_non_neutral_transition_always_allowed(self):
        """Transitions not FROM neutral are always allowed."""
        guard = NeutralTransitionGuard()
        # Comedy to tragedy - should be allowed
        assert guard.should_transition(AffectRegime.COMEDY, AffectRegime.TRAGEDY)
        # Tragedy to drama - should be allowed
        assert guard.should_transition(AffectRegime.TRAGEDY, AffectRegime.DRAMA)

    def test_stay_in_neutral_allowed(self):
        """Staying in neutral is always allowed."""
        guard = NeutralTransitionGuard()
        assert guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.NEUTRAL)

    def test_exit_neutral_blocked_without_signal(self):
        """Exiting neutral blocked if no sustained signal."""
        guard = NeutralTransitionGuard()
        # No signal observed - should block
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_exit_neutral_allowed_after_sustained_signal(self):
        """Exiting neutral allowed after sustained signal."""
        config = NeutralTransitionGuardConfig(min_signal_tokens=3)
        guard = NeutralTransitionGuard(config)

        # Observe comedy signal 3 times
        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.observe_signal(AffectRegime.COMEDY, 0.5)

        # Now transition should be allowed
        assert guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_low_confidence_signal_ignored(self):
        """Low confidence signals don't count toward threshold."""
        config = NeutralTransitionGuardConfig(min_signal_tokens=2, confidence_threshold=0.4)
        guard = NeutralTransitionGuard(config)

        # Low confidence signals
        guard.observe_signal(AffectRegime.COMEDY, 0.3)
        guard.observe_signal(AffectRegime.COMEDY, 0.3)
        guard.observe_signal(AffectRegime.COMEDY, 0.3)

        # Should still be blocked
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_different_regime_signal_resets(self):
        """Signaling a different regime resets the count."""
        config = NeutralTransitionGuardConfig(min_signal_tokens=3)
        guard = NeutralTransitionGuard(config)

        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        # Switch to tragedy - resets
        guard.observe_signal(AffectRegime.TRAGEDY, 0.5)

        # Comedy transition blocked
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)
        # Tragedy also blocked (only 1 token)
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.TRAGEDY)

    def test_explicit_request_bypasses_guard(self):
        """Explicit user request bypasses signal requirement."""
        guard = NeutralTransitionGuard()

        # No signals, but user explicitly requested comedy
        guard.set_explicit_request(AffectRegime.COMEDY)

        # Should be allowed
        assert guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_explicit_request_can_be_cleared(self):
        """Explicit request can be cleared."""
        guard = NeutralTransitionGuard()
        guard.set_explicit_request(AffectRegime.COMEDY)
        guard.clear_explicit_request()

        # Should be blocked again
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_reset(self):
        """Reset clears all state."""
        config = NeutralTransitionGuardConfig(min_signal_tokens=2)
        guard = NeutralTransitionGuard(config)

        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.set_explicit_request(AffectRegime.COMEDY)

        guard.reset()

        # Should be blocked again
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)

    def test_neutral_signal_resets_count(self):
        """Signaling neutral resets the count."""
        config = NeutralTransitionGuardConfig(min_signal_tokens=2)
        guard = NeutralTransitionGuard(config)

        guard.observe_signal(AffectRegime.COMEDY, 0.5)
        guard.observe_signal(AffectRegime.NEUTRAL, 0.5)  # Reset

        # Should be blocked
        assert not guard.should_transition(AffectRegime.NEUTRAL, AffectRegime.COMEDY)


class TestNeutralConstraints:
    def test_active_constraints_defined(self):
        assert len(NEUTRAL_ACTIVE_CONSTRAINTS) > 0
        assert "governance_invisibility" in NEUTRAL_ACTIVE_CONSTRAINTS
        assert "exit_shape" in NEUTRAL_ACTIVE_CONSTRAINTS

    def test_inactive_constraints_defined(self):
        assert len(NEUTRAL_INACTIVE_CONSTRAINTS) > 0
        assert "load_bearing_variables" in NEUTRAL_INACTIVE_CONSTRAINTS
        assert "phase_lock" in NEUTRAL_INACTIVE_CONSTRAINTS

    def test_is_active_in_neutral(self):
        assert is_active_in_neutral("governance_invisibility")
        assert is_active_in_neutral("no_committee_texture")
        assert not is_active_in_neutral("phase_lock")

    def test_is_inactive_in_neutral(self):
        assert is_inactive_in_neutral("load_bearing_variables")
        assert is_inactive_in_neutral("regime_scoring")
        assert not is_inactive_in_neutral("exit_shape")

    def test_no_overlap(self):
        """Active and inactive sets don't overlap."""
        overlap = NEUTRAL_ACTIVE_CONSTRAINTS & NEUTRAL_INACTIVE_CONSTRAINTS
        assert len(overlap) == 0
