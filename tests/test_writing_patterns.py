"""Tests for writing_patterns.py — regex pattern banks for writing governance."""

import re

import pytest

from governor.writing_patterns import (
    ANXIETY_HEDGE_PATTERNS,
    APOLOGY_META_PATTERNS,
    BAD_EXIT_PATTERNS,
    BANNED_PHRASES,
    BUREAUCRATIC_PATTERNS,
    CAUSAL_HUMILITY_PATTERNS,
    COMMITTEE_PATTERNS,
    FAKE_CONFIDENCE_PATTERNS,
    FALSIFIER_PATTERNS,
    GOOD_DIAGNOSTIC_PATTERNS,
    GOTCHA_PATTERNS,
    GOVERNANCE_ARTIFACT_PATTERNS,
    HEDGE_PATTERNS,
    INFLATED_WEIGHT_PATTERNS,
    INSTITUTIONAL_MARKER_PATTERNS,
    INSTRUCTION_FILLER_PATTERNS,
    MANIPULATION_PATTERNS,
    MEANING_WORD_PATTERNS,
    MORALIZING_PATTERNS,
    NORMATIVE_PATTERNS,
    PREMATURE_CLOSURE_PATTERNS,
    SELF_REFERENCE_PATTERNS,
    STRAWMAN_PATTERNS,
    check_any_pattern,
    count_categorized_patterns,
    count_pattern_matches,
    find_pattern_matches,
)


# =============================================================================
# Pattern bank type tests
# =============================================================================


class TestPatternBankTypes:
    """Verify all pattern banks are correctly typed."""

    @pytest.mark.parametrize(
        "patterns",
        [
            HEDGE_PATTERNS,
            SELF_REFERENCE_PATTERNS,
            APOLOGY_META_PATTERNS,
            COMMITTEE_PATTERNS,
            MEANING_WORD_PATTERNS,
            NORMATIVE_PATTERNS,
            CAUSAL_HUMILITY_PATTERNS,
            FALSIFIER_PATTERNS,
            STRAWMAN_PATTERNS,
            ANXIETY_HEDGE_PATTERNS,
            INSTRUCTION_FILLER_PATTERNS,
            FAKE_CONFIDENCE_PATTERNS,
            PREMATURE_CLOSURE_PATTERNS,
            BUREAUCRATIC_PATTERNS,
            GOOD_DIAGNOSTIC_PATTERNS,
            MORALIZING_PATTERNS,
            GOTCHA_PATTERNS,
            MANIPULATION_PATTERNS,
            BAD_EXIT_PATTERNS,
            INFLATED_WEIGHT_PATTERNS,
        ],
    )
    def test_pattern_bank_is_list_of_compiled_patterns(self, patterns):
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        for p in patterns:
            assert isinstance(p, re.Pattern)

    def test_categorized_patterns_governance_artifacts(self):
        assert isinstance(GOVERNANCE_ARTIFACT_PATTERNS, dict)
        expected_cats = [
            "preemptive_defense",
            "virtue_seals",
            "balance_theater",
            "empty_rigor",
            "responsible_framing",
            "meta_writing",
        ]
        for cat in expected_cats:
            assert cat in GOVERNANCE_ARTIFACT_PATTERNS
            assert isinstance(GOVERNANCE_ARTIFACT_PATTERNS[cat], list)
            for p in GOVERNANCE_ARTIFACT_PATTERNS[cat]:
                assert isinstance(p, re.Pattern)

    def test_categorized_patterns_institutional_markers(self):
        assert isinstance(INSTITUTIONAL_MARKER_PATTERNS, dict)
        expected_cats = [
            "hr_voice",
            "legal_voice",
            "committee_voice",
            "condescension_voice",
            "fear_voice",
        ]
        for cat in expected_cats:
            assert cat in INSTITUTIONAL_MARKER_PATTERNS
            assert isinstance(INSTITUTIONAL_MARKER_PATTERNS[cat], list)

    def test_banned_phrases_is_list_of_strings(self):
        assert isinstance(BANNED_PHRASES, list)
        for phrase in BANNED_PHRASES:
            assert isinstance(phrase, str)


# =============================================================================
# Hedge pattern tests
# =============================================================================


class TestHedgePatterns:
    """Test hedge pattern matching."""

    def test_maybe_matches(self):
        assert count_pattern_matches("Maybe we should try that", HEDGE_PATTERNS) >= 1

    def test_perhaps_matches(self):
        assert count_pattern_matches("Perhaps this is the way", HEDGE_PATTERNS) >= 1

    def test_sort_of_matches(self):
        assert count_pattern_matches("It's sort of interesting", HEDGE_PATTERNS) >= 1

    def test_i_think_matches(self):
        assert count_pattern_matches("I think this works", HEDGE_PATTERNS) >= 1

    def test_it_seems_matches(self):
        assert count_pattern_matches("It seems to be correct", HEDGE_PATTERNS) >= 1

    def test_multiple_hedges(self):
        text = "Maybe I think it's sort of possibly true, perhaps."
        assert count_pattern_matches(text, HEDGE_PATTERNS) >= 4

    def test_clean_text_no_hedges(self):
        text = "This is the correct approach. The data shows clear results."
        assert count_pattern_matches(text, HEDGE_PATTERNS) == 0


# =============================================================================
# Self-reference pattern tests
# =============================================================================


class TestSelfReferencePatterns:
    """Test self-reference pattern matching."""

    def test_as_an_ai_matches(self):
        assert count_pattern_matches("As an AI, I cannot feel", SELF_REFERENCE_PATTERNS) >= 1

    def test_im_just_a_matches(self):
        assert count_pattern_matches("I'm just a language model", SELF_REFERENCE_PATTERNS) >= 1

    def test_i_should_note_matches(self):
        assert count_pattern_matches("I should note that this is complex", SELF_REFERENCE_PATTERNS) >= 1

    def test_i_want_to_be_clear_matches(self):
        assert count_pattern_matches("I want to be clear about this", SELF_REFERENCE_PATTERNS) >= 1

    def test_clean_fiction_no_self_ref(self):
        text = "The dragon soared over the mountain, breathing fire on the village below."
        assert count_pattern_matches(text, SELF_REFERENCE_PATTERNS) == 0


# =============================================================================
# Committee pattern tests
# =============================================================================


class TestCommitteePatterns:
    """Test committee/negotiation pattern matching."""

    def test_on_one_hand_matches(self):
        assert count_pattern_matches("On the one hand, this is good", COMMITTEE_PATTERNS) >= 1

    def test_its_complicated_matches(self):
        assert count_pattern_matches("Well, it's complicated", COMMITTEE_PATTERNS) >= 1

    def test_to_be_fair_matches(self):
        assert count_pattern_matches("To be fair, they tried hard", COMMITTEE_PATTERNS) >= 1

    def test_that_said_matches(self):
        assert count_pattern_matches("That said, we should proceed", COMMITTEE_PATTERNS) >= 1

    def test_clean_direct_text(self):
        text = "The solution is clear. We implement it tomorrow."
        assert count_pattern_matches(text, COMMITTEE_PATTERNS) == 0


# =============================================================================
# Normative pattern tests
# =============================================================================


class TestNormativePatterns:
    """Test normative (should/must) pattern matching."""

    def test_should_matches(self):
        assert count_pattern_matches("You should do this", NORMATIVE_PATTERNS) >= 1

    def test_must_matches(self):
        assert count_pattern_matches("We must act now", NORMATIVE_PATTERNS) >= 1

    def test_need_to_matches(self):
        assert count_pattern_matches("You need to understand", NORMATIVE_PATTERNS) >= 1

    def test_it_is_important_matches(self):
        assert count_pattern_matches("It is important that we", NORMATIVE_PATTERNS) >= 1

    def test_descriptive_text_no_normative(self):
        text = "The experiment showed a 20% increase in efficiency."
        assert count_pattern_matches(text, NORMATIVE_PATTERNS) == 0


# =============================================================================
# Causal humility pattern tests
# =============================================================================


class TestCausalHumilityPatterns:
    """Test causal humility pattern matching."""

    def test_correlation_matches(self):
        assert count_pattern_matches("There is a correlation between X and Y", CAUSAL_HUMILITY_PATTERNS) >= 1

    def test_associated_matches(self):
        assert count_pattern_matches("These factors are associated with", CAUSAL_HUMILITY_PATTERNS) >= 1

    def test_suggests_but_does_not_prove_matches(self):
        text = "The data suggests but does not prove causation"
        assert count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS) >= 1

    def test_causal_claim_no_humility(self):
        text = "X causes Y. This is proven beyond doubt."
        assert count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS) == 0


# =============================================================================
# Bad exit pattern tests
# =============================================================================


class TestBadExitPatterns:
    """Test bad exit pattern matching."""

    def test_hope_this_helps_matches(self):
        assert count_pattern_matches("I hope this helps!", BAD_EXIT_PATTERNS) >= 1

    def test_let_me_know_if_matches(self):
        assert count_pattern_matches("Let me know if you have questions", BAD_EXIT_PATTERNS) >= 1

    def test_in_conclusion_matches(self):
        assert count_pattern_matches("In conclusion, we found that", BAD_EXIT_PATTERNS) >= 1

    def test_feel_free_to_matches(self):
        assert count_pattern_matches("Feel free to reach out", BAD_EXIT_PATTERNS) >= 1

    def test_clean_ending_no_bad_exit(self):
        text = "The analysis is complete."
        assert count_pattern_matches(text, BAD_EXIT_PATTERNS) == 0


# =============================================================================
# Inflated weight pattern tests
# =============================================================================


class TestInflatedWeightPatterns:
    """Test inflated moral weight pattern matching."""

    def test_its_important_matches(self):
        assert count_pattern_matches("It's important to remember", INFLATED_WEIGHT_PATTERNS) >= 1

    def test_we_must_remember_matches(self):
        assert count_pattern_matches("We must remember that", INFLATED_WEIGHT_PATTERNS) >= 1

    def test_the_stakes_matches(self):
        assert count_pattern_matches("The stakes are high here", INFLATED_WEIGHT_PATTERNS) >= 1

    def test_factual_text_no_inflation(self):
        text = "The temperature was 25 degrees. The pressure was normal."
        assert count_pattern_matches(text, INFLATED_WEIGHT_PATTERNS) == 0


# =============================================================================
# Utility function tests
# =============================================================================


class TestCountPatternMatches:
    """Test count_pattern_matches utility."""

    def test_counts_multiple_occurrences(self):
        text = "Maybe we should maybe try maybe once more"
        count = count_pattern_matches(text, HEDGE_PATTERNS)
        assert count >= 3  # "maybe" appears 3 times

    def test_empty_text_returns_zero(self):
        assert count_pattern_matches("", HEDGE_PATTERNS) == 0

    def test_empty_patterns_returns_zero(self):
        assert count_pattern_matches("Some text here", []) == 0


class TestFindPatternMatches:
    """Test find_pattern_matches utility."""

    def test_finds_all_matches(self):
        text = "Maybe perhaps we should try"
        matches = find_pattern_matches(text, HEDGE_PATTERNS)
        assert "Maybe" in matches or "maybe" in matches.lower() if matches else False

    def test_empty_text_returns_empty_list(self):
        assert find_pattern_matches("", HEDGE_PATTERNS) == []


class TestCheckAnyPattern:
    """Test check_any_pattern utility."""

    def test_returns_true_when_match_found(self):
        assert check_any_pattern("I think this is good", HEDGE_PATTERNS)

    def test_returns_false_when_no_match(self):
        assert not check_any_pattern("The sky is blue", HEDGE_PATTERNS)

    def test_empty_text_returns_false(self):
        assert not check_any_pattern("", HEDGE_PATTERNS)


class TestCountCategorizedPatterns:
    """Test count_categorized_patterns utility."""

    def test_counts_each_category(self):
        text = "I should note that experts agree this is important"
        counts = count_categorized_patterns(text, GOVERNANCE_ARTIFACT_PATTERNS)
        assert isinstance(counts, dict)
        assert "empty_rigor" in counts  # "experts agree"

    def test_empty_text_returns_zero_counts(self):
        counts = count_categorized_patterns("", GOVERNANCE_ARTIFACT_PATTERNS)
        assert all(v == 0 for v in counts.values())


# =============================================================================
# No overlap tests
# =============================================================================


class TestPatternNoUnexpectedOverlap:
    """Ensure patterns don't have unexpected overlaps."""

    def test_hedge_and_self_ref_distinct(self):
        # "I think" is a hedge, not self-ref
        text = "I think this works"
        hedge_count = count_pattern_matches(text, HEDGE_PATTERNS)
        self_ref_count = count_pattern_matches(text, SELF_REFERENCE_PATTERNS)
        assert hedge_count >= 1
        assert self_ref_count == 0

    def test_apology_and_committee_distinct(self):
        # "sorry" is apology, not committee
        text = "I'm sorry about the confusion"
        apology_count = count_pattern_matches(text, APOLOGY_META_PATTERNS)
        committee_count = count_pattern_matches(text, COMMITTEE_PATTERNS)
        assert apology_count >= 1
        assert committee_count == 0


# =============================================================================
# Bureaucratic pattern tests
# =============================================================================


class TestBureaucraticPatterns:
    """Test bureaucratic contamination pattern matching."""

    def test_pursuant_to_matches(self):
        assert count_pattern_matches("Pursuant to our agreement", BUREAUCRATIC_PATTERNS) >= 1

    def test_stakeholders_matches(self):
        assert count_pattern_matches("Key stakeholders were consulted", BUREAUCRATIC_PATTERNS) >= 1

    def test_going_forward_matches(self):
        assert count_pattern_matches("Going forward, we will", BUREAUCRATIC_PATTERNS) >= 1

    def test_normal_text_no_bureaucratic(self):
        text = "We talked to the people involved and decided to proceed."
        assert count_pattern_matches(text, BUREAUCRATIC_PATTERNS) == 0


# =============================================================================
# Fake confidence pattern tests
# =============================================================================


class TestFakeConfidencePatterns:
    """Test fake confidence pattern matching."""

    def test_simply_matches(self):
        assert count_pattern_matches("You simply need to click here", FAKE_CONFIDENCE_PATTERNS) >= 1

    def test_just_matches(self):
        assert count_pattern_matches("Just restart the server", FAKE_CONFIDENCE_PATTERNS) >= 1

    def test_its_easy_matches(self):
        assert count_pattern_matches("It's easy to configure", FAKE_CONFIDENCE_PATTERNS) >= 1


# =============================================================================
# Instruction filler pattern tests
# =============================================================================


class TestInstructionFillerPatterns:
    """Test instruction filler pattern matching."""

    def test_lets_dive_into_matches(self):
        assert count_pattern_matches("Let's dive into the topic", INSTRUCTION_FILLER_PATTERNS) >= 1

    def test_youll_love_matches(self):
        assert count_pattern_matches("You'll love this feature", INSTRUCTION_FILLER_PATTERNS) >= 1

    def test_direct_instruction_no_filler(self):
        text = "Step 1: Open the file. Step 2: Edit the config."
        assert count_pattern_matches(text, INSTRUCTION_FILLER_PATTERNS) == 0


# =============================================================================
# Diagnostic pattern tests
# =============================================================================


class TestDiagnosticPatterns:
    """Test good diagnostic pattern matching."""

    def test_hypothesis_matches(self):
        assert count_pattern_matches("Hypothesis: the cache is stale", GOOD_DIAGNOSTIC_PATTERNS) >= 1

    def test_this_rules_out_matches(self):
        assert count_pattern_matches("This rules out network issues", GOOD_DIAGNOSTIC_PATTERNS) >= 1

    def test_we_can_test_by_matches(self):
        assert count_pattern_matches("We can test by restarting", GOOD_DIAGNOSTIC_PATTERNS) >= 1


# =============================================================================
# Gotcha pattern tests
# =============================================================================


class TestGotchaPatterns:
    """Test gotcha/trap pattern matching."""

    def test_but_you_said_matches(self):
        assert count_pattern_matches("But you said you agreed", GOTCHA_PATTERNS) >= 1

    def test_which_is_it_matches(self):
        assert count_pattern_matches("So which is it?", GOTCHA_PATTERNS) >= 1


# =============================================================================
# Manipulation pattern tests
# =============================================================================


class TestManipulationPatterns:
    """Test manipulation pattern matching."""

    def test_if_you_really_cared_matches(self):
        assert count_pattern_matches("If you really cared, you would", MANIPULATION_PATTERNS) >= 1

    def test_reasonable_person_matches(self):
        assert count_pattern_matches("A reasonable person would agree", MANIPULATION_PATTERNS) >= 1
