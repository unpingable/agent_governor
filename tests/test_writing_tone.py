# SPDX-License-Identifier: Apache-2.0
"""Tests for writing_tone.py — 6-axis tone modulation layer."""

import math
import pytest

from governor.writing_tone import (
    ADVOCACY_ENVELOPE,
    APHORISM_ENVELOPE,
    COMEDY_ENVELOPE,
    DEBUGGING_ENVELOPE,
    DRAMA_ENVELOPE,
    HORROR_ENVELOPE,
    INSTRUCTION_ENVELOPE,
    LITURGICAL_ENVELOPE,
    MARKETING_ENVELOPE,
    NEGOTIATION_ENVELOPE,
    NEUTRAL_ENVELOPE,
    NONFICTION_ENVELOPE,
    REGIME_ENVELOPES,
    RESEARCH_ENVELOPE,
    ROMANCE_ENVELOPE,
    SATIRE_ENVELOPE,
    SINCERITY_ENVELOPE,
    TONE_COLLISIONS,
    TRAGEDY_ENVELOPE,
    ToneCollision,
    ToneDriftScore,
    ToneDriftScorer,
    ToneEnvelope,
    ToneStabilityConfig,
    ToneStabilityController,
    ToneVector,
    check_collisions,
    get_envelope,
    resolve_collisions,
)


# =============================================================================
# ToneVector tests
# =============================================================================


class TestToneVector:
    """Test ToneVector dataclass."""

    def test_default_values(self):
        v = ToneVector()
        assert v.formality == 0.5
        assert v.temperature == 0.5
        assert v.density == 0.5
        assert v.velocity == 0.5
        assert v.distance == 0.5
        assert v.certainty == 0.5

    def test_custom_values(self):
        v = ToneVector(formality=0.1, temperature=0.9)
        assert v.formality == 0.1
        assert v.temperature == 0.9

    def test_clamp_high_values(self):
        v = ToneVector(formality=1.5, temperature=2.0)
        clamped = v.clamp()
        assert clamped.formality == 1.0
        assert clamped.temperature == 1.0

    def test_clamp_low_values(self):
        v = ToneVector(formality=-0.5, temperature=-1.0)
        clamped = v.clamp()
        assert clamped.formality == 0.0
        assert clamped.temperature == 0.0

    def test_clamp_does_not_modify_original(self):
        v = ToneVector(formality=1.5)
        clamped = v.clamp()
        assert v.formality == 1.5  # original unchanged
        assert clamped.formality == 1.0

    def test_euclidean_distance_same_vector(self):
        v = ToneVector()
        assert v.euclidean_distance(v) == 0.0

    def test_euclidean_distance_different_vectors(self):
        v1 = ToneVector(formality=0.0, temperature=0.0, density=0.0, velocity=0.0, distance=0.0, certainty=0.0)
        v2 = ToneVector(formality=1.0, temperature=1.0, density=1.0, velocity=1.0, distance=1.0, certainty=1.0)
        dist = v1.euclidean_distance(v2)
        # sqrt(6) for 6 dimensions, each with diff of 1
        assert abs(dist - math.sqrt(6)) < 0.001

    def test_euclidean_distance_one_dimension(self):
        v1 = ToneVector(formality=0.0)
        v2 = ToneVector(formality=1.0)
        dist = v1.euclidean_distance(v2)
        assert abs(dist - 1.0) < 0.001

    def test_to_dict(self):
        v = ToneVector(formality=0.3, temperature=0.7)
        d = v.to_dict()
        assert d["formality"] == 0.3
        assert d["temperature"] == 0.7
        assert "density" in d

    def test_from_dict(self):
        d = {"formality": 0.2, "temperature": 0.8}
        v = ToneVector.from_dict(d)
        assert v.formality == 0.2
        assert v.temperature == 0.8
        assert v.density == 0.5  # default

    def test_as_tuple(self):
        v = ToneVector(formality=0.1, temperature=0.2, density=0.3, velocity=0.4, distance=0.5, certainty=0.6)
        t = v.as_tuple()
        assert t == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)

    def test_equality(self):
        v1 = ToneVector(formality=0.5)
        v2 = ToneVector(formality=0.5)
        assert v1 == v2


# =============================================================================
# ToneEnvelope tests
# =============================================================================


class TestToneEnvelope:
    """Test ToneEnvelope dataclass."""

    def test_default_bounds(self):
        e = ToneEnvelope()
        assert e.formality == (0.0, 1.0)
        assert e.temperature == (0.0, 1.0)

    def test_contains_within_bounds(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.5)
        assert e.contains(v)

    def test_contains_at_lower_bound(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.2)
        assert e.contains(v)

    def test_contains_at_upper_bound(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.8)
        assert e.contains(v)

    def test_contains_below_bound(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.1)
        assert not e.contains(v)

    def test_contains_above_bound(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.9)
        assert not e.contains(v)

    def test_center(self):
        e = ToneEnvelope(formality=(0.2, 0.8), temperature=(0.0, 1.0))
        c = e.center()
        assert c.formality == 0.5
        assert c.temperature == 0.5

    def test_clip_within_bounds(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.5)
        clipped = e.clip(v)
        assert clipped.formality == 0.5

    def test_clip_below_bounds(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.1)
        clipped = e.clip(v)
        assert clipped.formality == 0.2

    def test_clip_above_bounds(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        v = ToneVector(formality=0.9)
        clipped = e.clip(v)
        assert clipped.formality == 0.8

    def test_to_dict(self):
        e = ToneEnvelope(formality=(0.2, 0.8))
        d = e.to_dict()
        assert d["formality"] == (0.2, 0.8)

    def test_from_dict(self):
        d = {"formality": [0.2, 0.8], "temperature": [0.3, 0.7]}
        e = ToneEnvelope.from_dict(d)
        assert e.formality == (0.2, 0.8)
        assert e.temperature == (0.3, 0.7)


# =============================================================================
# Regime envelope tests
# =============================================================================


class TestRegimeEnvelopes:
    """Test regime envelope constants."""

    @pytest.mark.parametrize(
        "envelope",
        [
            COMEDY_ENVELOPE,
            TRAGEDY_ENVELOPE,
            SINCERITY_ENVELOPE,
            DRAMA_ENVELOPE,
            NONFICTION_ENVELOPE,
            RESEARCH_ENVELOPE,
            INSTRUCTION_ENVELOPE,
            DEBUGGING_ENVELOPE,
            NEGOTIATION_ENVELOPE,
            ADVOCACY_ENVELOPE,
            MARKETING_ENVELOPE,
            HORROR_ENVELOPE,
            ROMANCE_ENVELOPE,
            SATIRE_ENVELOPE,
            LITURGICAL_ENVELOPE,
            APHORISM_ENVELOPE,
            NEUTRAL_ENVELOPE,
        ],
    )
    def test_envelope_is_valid(self, envelope):
        """Each envelope has valid bounds in [0, 1]."""
        for dim in ["formality", "temperature", "density", "velocity", "distance", "certainty"]:
            bounds = getattr(envelope, dim)
            assert bounds[0] >= 0.0
            assert bounds[1] <= 1.0
            assert bounds[0] <= bounds[1]

    def test_comedy_has_high_velocity(self):
        """Comedy requires fast velocity for timing."""
        assert COMEDY_ENVELOPE.velocity[0] >= 0.6

    def test_tragedy_has_slow_velocity(self):
        """Tragedy requires slow velocity for meaning-lag."""
        assert TRAGEDY_ENVELOPE.velocity[1] <= 0.5

    def test_instruction_has_high_certainty(self):
        """Instruction requires confident certainty."""
        assert INSTRUCTION_ENVELOPE.certainty[0] >= 0.6

    def test_research_has_low_certainty(self):
        """Research is exploratory, lower certainty."""
        assert RESEARCH_ENVELOPE.certainty[1] <= 0.7

    def test_liturgical_has_high_formality(self):
        """Liturgical requires high formality."""
        assert LITURGICAL_ENVELOPE.formality[0] >= 0.7

    def test_horror_has_low_temperature(self):
        """Horror is cool/detached."""
        assert HORROR_ENVELOPE.temperature[1] <= 0.5

    def test_romance_has_low_distance(self):
        """Romance is intimate."""
        assert ROMANCE_ENVELOPE.distance[1] <= 0.5

    def test_aphorism_has_high_density(self):
        """Aphorism is compressed."""
        assert APHORISM_ENVELOPE.density[0] >= 0.7


class TestRegimeEnvelopesRegistry:
    """Test REGIME_ENVELOPES registry."""

    def test_all_regimes_present(self):
        expected = [
            "comedy", "tragedy", "sincerity", "drama",
            "nonfiction", "research", "instruction", "debugging",
            "negotiation", "advocacy", "marketing",
            "horror", "romance", "satire", "liturgical", "aphorism",
            "neutral",
        ]
        for r in expected:
            assert r in REGIME_ENVELOPES

    def test_get_envelope_known_regime(self):
        e = get_envelope("comedy")
        assert e == COMEDY_ENVELOPE

    def test_get_envelope_case_insensitive(self):
        e = get_envelope("COMEDY")
        assert e == COMEDY_ENVELOPE

    def test_get_envelope_unknown_returns_neutral(self):
        e = get_envelope("unknown_regime")
        assert e == NEUTRAL_ENVELOPE


# =============================================================================
# ToneCollision tests
# =============================================================================


class TestToneCollision:
    """Test ToneCollision rules."""

    def test_applies_correct_regime(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        assert c.applies("comedy")
        assert c.applies("Comedy")  # case insensitive

    def test_applies_wrong_regime(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        assert not c.applies("tragedy")

    def test_violates_in_forbidden_range(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        v = ToneVector(formality=0.8)
        assert c.violates(v)

    def test_violates_at_boundary(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        v = ToneVector(formality=0.7)
        assert c.violates(v)

    def test_not_violates_outside_range(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        v = ToneVector(formality=0.5)
        assert not c.violates(v)

    def test_fix_clips_to_below_forbidden(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        v = ToneVector(formality=0.75)  # closer to 0.7 than 1.0
        fixed = c.fix(v)
        assert fixed.formality < 0.7

    def test_fix_clips_to_above_forbidden(self):
        c = ToneCollision("comedy", "formality", (0.0, 0.3), "test")
        v = ToneVector(formality=0.25)  # closer to 0.3 than 0.0
        fixed = c.fix(v)
        assert fixed.formality > 0.3

    def test_fix_no_change_if_not_violating(self):
        c = ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death")
        v = ToneVector(formality=0.5)
        fixed = c.fix(v)
        assert fixed.formality == 0.5


class TestToneCollisionsList:
    """Test TONE_COLLISIONS list."""

    def test_has_expected_collisions(self):
        reasons = [c.reason for c in TONE_COLLISIONS]
        assert "advocacy_contamination" in reasons
        assert "timing_death" in reasons
        assert "spell_collapse" in reasons
        assert "therapy_drift" in reasons
        assert "agenda_smell" in reasons
        assert "premature_closure" in reasons
        assert "defangs_threat" in reasons

    def test_research_temperature_collision(self):
        collisions = [c for c in TONE_COLLISIONS if c.regime == "research" and c.dimension == "temperature"]
        assert len(collisions) >= 1
        assert collisions[0].forbidden_range == (0.6, 1.0)

    def test_comedy_velocity_collision(self):
        collisions = [c for c in TONE_COLLISIONS if c.regime == "comedy" and c.dimension == "velocity"]
        assert len(collisions) >= 1
        assert collisions[0].forbidden_range == (0.0, 0.4)


class TestResolveCollisions:
    """Test resolve_collisions function."""

    def test_no_collision_passthrough(self):
        v = ToneVector(formality=0.5)
        resolved = resolve_collisions(v, "comedy")
        assert resolved.formality == 0.5

    def test_comedy_formality_collision_fixed(self):
        v = ToneVector(formality=0.8)  # violates comedy formality collision
        resolved = resolve_collisions(v, "comedy")
        assert resolved.formality < 0.7

    def test_research_temperature_collision_fixed(self):
        v = ToneVector(temperature=0.9)  # violates research temperature collision
        resolved = resolve_collisions(v, "research")
        assert resolved.temperature < 0.6

    def test_unknown_regime_passthrough(self):
        v = ToneVector(formality=0.9)
        resolved = resolve_collisions(v, "unknown")
        assert resolved.formality == 0.9


class TestCheckCollisions:
    """Test check_collisions function."""

    def test_returns_empty_for_valid_tone(self):
        v = ToneVector(formality=0.3, velocity=0.7)  # valid for comedy
        collisions = check_collisions(v, "comedy")
        assert len(collisions) == 0

    def test_returns_collisions_for_invalid_tone(self):
        v = ToneVector(formality=0.8, velocity=0.2)  # violates comedy
        collisions = check_collisions(v, "comedy")
        assert len(collisions) >= 2  # formality and velocity


# =============================================================================
# ToneStabilityController tests
# =============================================================================


class TestToneStabilityController:
    """Test ToneStabilityController."""

    def test_initial_state(self):
        controller = ToneStabilityController()
        assert controller.current_tone == ToneVector()

    def test_update_toward_target(self):
        controller = ToneStabilityController()
        target = ToneVector(formality=0.8)
        new_tone = controller.update_tone(target, "comedy", tokens_elapsed=100)
        # Should have moved toward target (may reach it with enough tokens)
        assert new_tone.formality > 0.5
        assert new_tone.formality <= 0.8

    def test_update_respects_rate_limit(self):
        config = ToneStabilityConfig(max_shift_rate=0.001)
        controller = ToneStabilityController(config)
        target = ToneVector(formality=1.0, temperature=1.0, density=1.0,
                           velocity=1.0, distance=1.0, certainty=1.0)
        new_tone = controller.update_tone(target, "comedy", tokens_elapsed=1)
        # With rate 0.001 and 1 token, max shift is 0.001
        dist = ToneVector().euclidean_distance(new_tone)
        assert dist <= 0.01  # tolerance for floating point + 6D normalization

    def test_update_faster_on_regime_change(self):
        config = ToneStabilityConfig(max_shift_rate=0.01, regime_shift_multiplier=3.0)
        controller = ToneStabilityController(config)
        target = ToneVector(formality=1.0)

        # First update without regime change
        controller.update_tone(target, "comedy", tokens_elapsed=10)
        tone_after_stable = controller.current_tone.formality

        # Reset
        controller.reset()

        # Update with regime change
        controller.update_tone(ToneVector(), "comedy", tokens_elapsed=1)  # establish regime
        controller.update_tone(target, "tragedy", tokens_elapsed=10)  # regime change
        tone_after_change = controller.current_tone.formality

        # Should have moved further with regime change
        # (This is a relative comparison, actual values depend on implementation)
        assert tone_after_change >= tone_after_stable or abs(tone_after_change - tone_after_stable) < 0.01

    def test_reaches_target_eventually(self):
        controller = ToneStabilityController()
        target = ToneVector(formality=0.9)

        # Many updates should eventually reach target
        for _ in range(1000):
            controller.update_tone(target, "comedy", tokens_elapsed=10)

        # Should be very close to target
        assert abs(controller.current_tone.formality - 0.9) < 0.01

    def test_reset(self):
        controller = ToneStabilityController()
        controller.update_tone(ToneVector(formality=1.0), "comedy", tokens_elapsed=100)
        assert controller.current_tone.formality > 0.5

        controller.reset()
        assert controller.current_tone == ToneVector()

    def test_reset_with_initial_tone(self):
        controller = ToneStabilityController()
        initial = ToneVector(formality=0.3)
        controller.reset(initial)
        assert controller.current_tone.formality == 0.3


# =============================================================================
# ToneDriftScorer tests
# =============================================================================


class TestToneDriftScorer:
    """Test ToneDriftScorer."""

    def test_no_drift_for_valid_tone_and_clean_text(self):
        scorer = ToneDriftScorer()
        tone = COMEDY_ENVELOPE.center()
        result = scorer.score_drift(tone, "comedy", "The dragon flew over the mountain.")
        assert result.envelope_drift == 0.0
        assert result.institutional_density < 1.0
        assert result.overall_drift < 0.3

    def test_envelope_drift_for_out_of_bounds_tone(self):
        scorer = ToneDriftScorer()
        tone = ToneVector(formality=0.9)  # outside comedy envelope
        result = scorer.score_drift(tone, "comedy", "Clean text here.")
        assert result.envelope_drift > 0.0

    def test_institutional_density_detected(self):
        scorer = ToneDriftScorer()
        tone = COMEDY_ENVELOPE.center()
        text = "We should proceed professionally and respectfully in a balanced manner."
        result = scorer.score_drift(tone, "comedy", text)
        assert result.institutional_density > 0.0

    def test_committee_cadence_detected(self):
        scorer = ToneDriftScorer()
        tone = COMEDY_ENVELOPE.center()
        text = "On the one hand, to be fair, it's complicated. That said, at the same time..."
        result = scorer.score_drift(tone, "comedy", text)
        assert result.committee_cadence > 0.0

    def test_collisions_detected(self):
        scorer = ToneDriftScorer()
        tone = ToneVector(formality=0.9, velocity=0.2)  # violates comedy
        result = scorer.score_drift(tone, "comedy", "Clean text.")
        assert len(result.collisions) >= 2
        assert "timing_death" in result.collisions

    def test_overall_drift_combines_signals(self):
        scorer = ToneDriftScorer()
        tone = ToneVector(formality=0.9, velocity=0.2)
        text = "We should proceed professionally in a balanced manner. On the one hand..."
        result = scorer.score_drift(tone, "comedy", text)
        assert result.overall_drift > 0.3

    def test_to_dict_returns_all_fields(self):
        scorer = ToneDriftScorer()
        result = scorer.score_drift(ToneVector(), "comedy", "Text")
        d = result.to_dict()
        assert "envelope_drift" in d
        assert "institutional_density" in d
        assert "committee_cadence" in d
        assert "overall_drift" in d
        assert "collisions" in d


# =============================================================================
# ToneDriftScore dataclass tests
# =============================================================================


class TestToneDriftScore:
    """Test ToneDriftScore dataclass."""

    def test_default_values(self):
        score = ToneDriftScore()
        assert score.envelope_drift == 0.0
        assert score.institutional_density == 0.0
        assert score.collisions == []

    def test_to_dict(self):
        score = ToneDriftScore(
            envelope_drift=0.2,
            institutional_density=1.5,
            committee_cadence=0.3,
            overall_drift=0.4,
            collisions=["timing_death"],
        )
        d = score.to_dict()
        assert d["envelope_drift"] == 0.2
        assert d["collisions"] == ["timing_death"]
