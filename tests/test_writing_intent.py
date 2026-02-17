# SPDX-License-Identifier: Apache-2.0
"""Tests for writing_intent.py — intent classifier and ancillary regime scorers."""

import pytest

from governor.writing_intent import (
    COLLISION_MATRIX,
    CollisionResolution,
    CollisionResult,
    CollisionSeverity,
    IntentCategory,
    IntentClassification,
    IntentClassifier,
    calculate_ap,
    calculate_au,
    calculate_de,
    calculate_fi,
    calculate_fp,
    calculate_lm,
    calculate_mc,
    calculate_mt,
    calculate_pa,
    calculate_sa,
    calculate_ut,
    calculate_vv,
    check_collision,
    list_collisions_for_regime,
)


# =============================================================================
# IntentCategory tests
# =============================================================================


class TestIntentCategory:
    """Test IntentCategory enum."""

    def test_values(self):
        assert IntentCategory.EXECUTE.value == "execute"
        assert IntentCategory.CALIBRATE.value == "calibrate"
        assert IntentCategory.COORDINATE.value == "coordinate"
        assert IntentCategory.MOBILIZE.value == "mobilize"
        assert IntentCategory.EVOKE.value == "evoke"
        assert IntentCategory.ENCODE.value == "encode"

    def test_all_categories(self):
        assert len(IntentCategory) == 6


# =============================================================================
# IntentClassifier tests
# =============================================================================


class TestIntentClassifier:
    """Test IntentClassifier."""

    def test_execute_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("How do I fix this error?")
        assert result.primary == IntentCategory.EXECUTE

    def test_calibrate_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("Can you explain why this data shows a correlation?")
        assert result.primary == IntentCategory.CALIBRATE

    def test_coordinate_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("I need to negotiate a deal with them.")
        assert result.primary == IntentCategory.COORDINATE

    def test_mobilize_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("Help me promote this campaign for the cause.")
        assert result.primary == IntentCategory.MOBILIZE

    def test_evoke_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("Write a story with compelling characters and plot.")
        assert result.primary == IntentCategory.EVOKE

    def test_encode_signals(self):
        classifier = IntentClassifier()
        result = classifier.classify("Create a satirical piece with irony.")
        assert result.primary == IntentCategory.ENCODE

    def test_explicit_mode_fiction(self):
        classifier = IntentClassifier()
        result = classifier.classify("Anything", explicit_mode="fiction")
        assert result.primary == IntentCategory.EVOKE
        assert result.confidence == 0.9

    def test_explicit_mode_code(self):
        classifier = IntentClassifier()
        result = classifier.classify("Anything", explicit_mode="code")
        assert result.primary == IntentCategory.EXECUTE

    def test_explicit_mode_nonfiction(self):
        classifier = IntentClassifier()
        result = classifier.classify("Anything", explicit_mode="nonfiction")
        assert result.primary == IntentCategory.CALIBRATE

    def test_secondary_detected(self):
        classifier = IntentClassifier()
        result = classifier.classify("How do I debug this issue and analyze the data?")
        # Should have both EXECUTE and CALIBRATE signals
        assert result.signals.get("execute", 0) > 0 or result.signals.get("calibrate", 0) > 0

    def test_no_signal_defaults_to_calibrate(self):
        classifier = IntentClassifier()
        result = classifier.classify("Hello there.")
        assert result.primary == IntentCategory.CALIBRATE
        assert result.confidence < 0.5

    def test_to_dict(self):
        classifier = IntentClassifier()
        result = classifier.classify("Fix this error")
        d = result.to_dict()
        assert "primary" in d
        assert "confidence" in d
        assert "signals" in d


# =============================================================================
# Ancillary scorer tests
# =============================================================================


class TestCalculateAp:
    """Test Ap (Actionability) scorer."""

    def test_clean_instruction(self):
        text = "Step 1: Open the file. Step 2: Edit the config. Step 3: Save."
        score = calculate_ap(text)
        assert score > 0.5

    def test_filler_lowers_score(self):
        text = "Let's dive into this! You'll love it. It's important to note that..."
        score = calculate_ap(text)
        assert score < 0.7

    def test_fake_confidence_lowers_score(self):
        text = "Simply do this. Just click here. It's easy and straightforward."
        score = calculate_ap(text)
        assert score < 0.7

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_ap("Text") <= 1.0


class TestCalculateFi:
    """Test Fi (Fault Isolation) scorer."""

    def test_good_diagnostics(self):
        text = "Hypothesis: the cache is stale. This rules out network issues."
        score = calculate_fi(text)
        assert score > 0.5

    def test_premature_closure_lowers_score(self):
        text = "The problem is obvious. Clearly this is the only solution."
        score = calculate_fi(text)
        assert score < 0.5

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_fi("Text") <= 1.0


class TestCalculateAu:
    """Test Au (Auditability) scorer."""

    def test_falsifiers_raise_score(self):
        text = "This would fail if X. This depends on Y. Boundary condition applies."
        score = calculate_au(text)
        assert score > 0.5

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_au("Text") <= 1.0


class TestCalculateFp:
    """Test Fp (Face Preservation) scorer."""

    def test_clean_negotiation(self):
        text = "I understand your position. Here's what I propose."
        score = calculate_fp(text)
        assert score > 0.5

    def test_moralizing_lowers_score(self):
        text = "You should realize the right thing to do. How could you?"
        score = calculate_fp(text)
        assert score < 0.7

    def test_gotcha_lowers_score(self):
        text = "But you said you agreed! That contradicts what you claimed."
        score = calculate_fp(text)
        assert score < 0.7

    def test_manipulation_lowers_score(self):
        text = "If you really cared, a reasonable person would agree."
        score = calculate_fp(text)
        assert score < 0.7


class TestCalculateMt:
    """Test Mt (Motivational Traction) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_mt("Text") <= 1.0

    def test_manipulation_lowers_score(self):
        text = "If you really cared you would do this."
        score = calculate_mt(text)
        assert score < 0.6


class TestCalculatePa:
    """Test Pa (Aspirational Plausibility) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_pa("Text") <= 1.0

    def test_bureaucratic_lowers_score(self):
        text = "Pursuant to stakeholders, going forward, at this time."
        score = calculate_pa(text)
        assert score < 0.6


class TestCalculateUt:
    """Test Ut (Unresolved Threat) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_ut("Text") <= 1.0

    def test_closure_lowers_score(self):
        text = "The problem is clearly obvious. The only solution is X."
        score = calculate_ut(text)
        assert score < 0.7


class TestCalculateVv:
    """Test Vv (Vulnerability Credibility) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_vv("Text") <= 1.0

    def test_fake_confidence_lowers_score(self):
        text = "Simply love. Just trust. It's easy."
        score = calculate_vv(text)
        assert score < 0.6


class TestCalculateDe:
    """Test De (Double-Encoding Stability) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_de("Text") <= 1.0

    def test_hedges_lower_score(self):
        text = "Maybe perhaps sort of kind of somewhat arguably."
        score = calculate_de(text)
        assert score < 0.6


class TestCalculateMc:
    """Test Mc (Memorability) scorer."""

    def test_short_high_score(self):
        text = "Be water, my friend."
        score = calculate_mc(text)
        assert score > 0.6

    def test_long_low_score(self):
        text = " ".join(["word"] * 60)
        score = calculate_mc(text)
        assert score < 0.4

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_mc("Text") <= 1.0


class TestCalculateSa:
    """Test Sa (Sacred Authority) scorer."""

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_sa("Text") <= 1.0

    def test_anxiety_lowers_score(self):
        text = "I could be wrong. I'm no expert. Take this with salt."
        score = calculate_sa(text)
        assert score < 0.7


class TestCalculateLm:
    """Test Lm (Bureaucratic Contamination) scorer."""

    def test_clean_text_low(self):
        text = "Let's just do it."
        score = calculate_lm(text)
        assert score < 0.3

    def test_bureaucratic_high(self):
        text = "Pursuant to stakeholders, going forward, at this time, please be advised."
        score = calculate_lm(text)
        assert score > 0.3

    def test_returns_zero_to_one(self):
        assert 0.0 <= calculate_lm("Text") <= 1.0


# =============================================================================
# CollisionResult tests
# =============================================================================


class TestCollisionResult:
    """Test CollisionResult dataclass."""

    def test_to_dict(self):
        result = CollisionResult(
            regime_a="research",
            regime_b="advocacy",
            severity=CollisionSeverity.CONFLICT,
            resolution=CollisionResolution.CHOOSE_DOMINANT,
            reason="propaganda_smell",
        )
        d = result.to_dict()
        assert d["regime_a"] == "research"
        assert d["severity"] == "conflict"


# =============================================================================
# Collision matrix tests
# =============================================================================


class TestCollisionMatrix:
    """Test collision matrix and check functions."""

    def test_research_advocacy_collision(self):
        result = check_collision("research", "advocacy")
        assert result is not None
        assert result.severity == CollisionSeverity.CONFLICT
        assert result.reason == "propaganda_smell"

    def test_tragedy_satire_collision(self):
        result = check_collision("tragedy", "satire")
        assert result is not None
        assert result.severity == CollisionSeverity.CONFLICT
        assert result.reason == "cruelty_smell"

    def test_horror_comedy_collision(self):
        result = check_collision("horror", "comedy")
        assert result is not None
        assert result.severity == CollisionSeverity.CONFLICT

    def test_liturgical_comedy_incompatible(self):
        result = check_collision("liturgical", "comedy")
        assert result is not None
        assert result.severity == CollisionSeverity.INCOMPATIBLE

    def test_no_collision(self):
        result = check_collision("instruction", "debugging")
        assert result is None

    def test_bidirectional(self):
        result1 = check_collision("research", "advocacy")
        result2 = check_collision("advocacy", "research")
        assert result1 is not None
        assert result2 is not None
        assert result1.reason == result2.reason

    def test_case_insensitive(self):
        result = check_collision("RESEARCH", "ADVOCACY")
        assert result is not None

    def test_list_collisions_for_regime(self):
        collisions = list_collisions_for_regime("research")
        assert len(collisions) >= 1
        reasons = [c.reason for c in collisions]
        assert "propaganda_smell" in reasons or any("propaganda" in r for r in reasons)


# =============================================================================
# IntentClassification tests
# =============================================================================


class TestIntentClassification:
    """Test IntentClassification dataclass."""

    def test_defaults(self):
        ic = IntentClassification(primary=IntentCategory.EXECUTE)
        assert ic.confidence == 0.5
        assert ic.secondary is None

    def test_to_dict_with_secondary(self):
        ic = IntentClassification(
            primary=IntentCategory.EXECUTE,
            secondary=IntentCategory.CALIBRATE,
            confidence=0.8,
        )
        d = ic.to_dict()
        assert d["primary"] == "execute"
        assert d["secondary"] == "calibrate"

    def test_to_dict_without_secondary(self):
        ic = IntentClassification(primary=IntentCategory.EVOKE)
        d = ic.to_dict()
        assert d["secondary"] is None
