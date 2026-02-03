"""Tests for writing_governance.py — governance visibility scoring and leak detection."""

import pytest

from governor.writing_governance import (
    GV_CEILING,
    RP_FLOOR,
    ExitCheckResult,
    ExitShapeChecker,
    GovernanceCheckResult,
    GovernanceChecker,
    GovernanceLeakDetector,
    GovernanceLeakResult,
    GovernanceVisibilityResult,
    GovernanceVisibilityScorer,
    SmoothingResult,
    SmoothingSuppressor,
)


# =============================================================================
# GovernanceVisibilityScorer tests
# =============================================================================


class TestGovernanceVisibilityScorer:
    """Test governance visibility scoring."""

    def test_clean_text_returns_zero(self):
        scorer = GovernanceVisibilityScorer()
        result = scorer.calculate_gv("The experiment showed clear results.")
        assert result.overall_score == 0.0
        assert not result.exceeds_ceiling

    def test_preemptive_defense_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "Before you say anything, I know some will disagree with this."
        result = scorer.calculate_gv(text)
        assert result.preemptive_defense >= 1
        assert result.overall_score > 0.0

    def test_virtue_seals_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "It's important to acknowledge that we must recognize the context."
        result = scorer.calculate_gv(text)
        assert result.virtue_seals >= 1
        assert result.overall_score > 0.0

    def test_balance_theater_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "There are valid points on both sides of this debate."
        result = scorer.calculate_gv(text)
        assert result.balance_theater >= 1
        assert result.overall_score > 0.0

    def test_empty_rigor_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "Studies show that experts agree on this point."
        result = scorer.calculate_gv(text)
        assert result.empty_rigor >= 2  # "studies show" + "experts agree"
        assert result.overall_score > 0.0

    def test_responsible_framing_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "It would be irresponsible to proceed without consideration."
        result = scorer.calculate_gv(text)
        assert result.responsible_framing >= 1

    def test_meta_writing_detected(self):
        scorer = GovernanceVisibilityScorer()
        text = "I need to be careful here. This requires nuance."
        result = scorer.calculate_gv(text)
        assert result.meta_writing >= 1

    def test_exceeds_ceiling_with_many_artifacts(self):
        scorer = GovernanceVisibilityScorer(ceiling=0.3)
        text = """
        Before you argue, I know some will disagree. It's important to acknowledge
        that studies show experts agree. There are valid points on both sides.
        I want to be clear that it would be irresponsible to ignore this.
        """
        result = scorer.calculate_gv(text)
        assert result.exceeds_ceiling

    def test_score_capped_at_one(self):
        scorer = GovernanceVisibilityScorer()
        # Create heavily governance-laden text
        text = " ".join([
            "Before you argue, I know many will disagree.",
            "It's important to acknowledge this.",
            "Studies show experts agree.",
            "It would be irresponsible to ignore.",
            "We must recognize the complexity.",
        ] * 5)
        result = scorer.calculate_gv(text)
        assert result.overall_score <= 1.0

    def test_to_dict_returns_all_fields(self):
        scorer = GovernanceVisibilityScorer()
        result = scorer.calculate_gv("Some text")
        d = result.to_dict()
        assert "preemptive_defense" in d
        assert "virtue_seals" in d
        assert "overall_score" in d
        assert "exceeds_ceiling" in d


# =============================================================================
# GovernanceLeakDetector tests
# =============================================================================


class TestGovernanceLeakDetector:
    """Test governance leak detection."""

    def test_clean_text_no_leak(self):
        detector = GovernanceLeakDetector()
        result = detector.detect_leaks("The dragon flew over the mountain.")
        assert result.governance_leak_score == 0.0
        assert not result.has_leak

    def test_hr_voice_detected(self):
        detector = GovernanceLeakDetector()
        text = "Please maintain a professional and respectful tone."
        result = detector.detect_leaks(text)
        assert result.hr_voice >= 2
        assert result.governance_leak_score > 0.0

    def test_legal_voice_detected(self):
        detector = GovernanceLeakDetector()
        text = "We should proceed cautiously and prudently."
        result = detector.detect_leaks(text)
        assert result.legal_voice >= 2

    def test_committee_voice_detected(self):
        detector = GovernanceLeakDetector()
        text = "We need a balanced and nuanced approach."
        result = detector.detect_leaks(text)
        assert result.committee_voice >= 2

    def test_condescension_voice_detected(self):
        detector = GovernanceLeakDetector()
        text = "This simplified guide is accessible for beginners."
        result = detector.detect_leaks(text)
        assert result.condescension_voice >= 2

    def test_fear_voice_detected(self):
        detector = GovernanceLeakDetector()
        text = "I want to be clear. I should note that I don't mean to offend."
        result = detector.detect_leaks(text)
        assert result.fear_voice >= 2

    def test_committee_cadence_score(self):
        detector = GovernanceLeakDetector()
        text = "On the one hand, this. On the other hand, that. To be fair, it's complicated."
        result = detector.detect_leaks(text)
        assert result.committee_cadence_score > 0.0

    def test_marker_density_calculated(self):
        detector = GovernanceLeakDetector()
        text = "Professional balanced nuanced approach for everyone."
        result = detector.detect_leaks(text)
        assert result.marker_density > 0.0

    def test_has_leak_true_above_threshold(self):
        detector = GovernanceLeakDetector(leak_threshold=0.2)
        text = """
        I want to be clear about this nuanced and balanced approach.
        We should proceed carefully and professionally.
        """
        result = detector.detect_leaks(text)
        assert result.has_leak

    def test_to_dict_returns_all_fields(self):
        detector = GovernanceLeakDetector()
        result = detector.detect_leaks("Some text")
        d = result.to_dict()
        assert "hr_voice" in d
        assert "governance_leak_score" in d
        assert "has_leak" in d


# =============================================================================
# SmoothingSuppressor tests
# =============================================================================


class TestSmoothingSuppressor:
    """Test smoothing suppression (hedge density, banned phrases, meta kill)."""

    def test_clean_text_high_rp(self):
        suppressor = SmoothingSuppressor()
        result = suppressor.check_smoothing("The dragon attacked the village.")
        assert result.rp_score == 1.0
        assert not result.below_rp_floor

    def test_hedges_lower_rp(self):
        suppressor = SmoothingSuppressor()
        text = "Maybe perhaps we could sort of try this possibly."
        result = suppressor.check_smoothing(text)
        assert result.hedge_count >= 4
        assert result.rp_score < 1.0

    def test_self_ref_kills_rp(self):
        suppressor = SmoothingSuppressor()
        text = "As an AI, I should note that I'm just a language model."
        result = suppressor.check_smoothing(text)
        assert result.self_ref_count >= 2
        assert result.rp_score < 0.8

    def test_committee_patterns_lower_rp(self):
        suppressor = SmoothingSuppressor()
        text = "On the one hand, to be fair, it's complicated."
        result = suppressor.check_smoothing(text)
        assert result.committee_count >= 2
        assert result.rp_score < 1.0

    def test_banned_phrases_detected(self):
        suppressor = SmoothingSuppressor()
        text = "As an AI, I hope that helps! Let me know if you need more."
        result = suppressor.check_smoothing(text)
        assert len(result.banned_phrases_found) >= 2

    def test_meta_kill_detected(self):
        suppressor = SmoothingSuppressor()
        text = "I'm sorry, that joke didn't land. Let me try again."
        result = suppressor.check_smoothing(text)
        assert result.meta_kill_found

    def test_rp_floor_breach(self):
        suppressor = SmoothingSuppressor(rp_floor=0.6)
        text = """
        As an AI, I should note that perhaps maybe sort of I think
        it's complicated. On the one hand, I'm sorry if this seems unclear.
        """
        result = suppressor.check_smoothing(text)
        assert result.below_rp_floor

    def test_hedge_density_calculated(self):
        suppressor = SmoothingSuppressor()
        text = "Maybe perhaps possibly " * 10  # High density
        result = suppressor.check_smoothing(text)
        assert result.hedge_density > 0.0

    def test_rp_clamped_at_zero(self):
        suppressor = SmoothingSuppressor()
        # Massive governance leaks
        text = " ".join([
            "As an AI, I should note, I'm just a model.",
            "I should mention I want to be clear.",
            "Sorry, let me try again. That joke didn't land.",
        ] * 5)
        result = suppressor.check_smoothing(text)
        assert result.rp_score >= 0.0

    def test_to_dict_returns_all_fields(self):
        suppressor = SmoothingSuppressor()
        result = suppressor.check_smoothing("Some text")
        d = result.to_dict()
        assert "banned_phrases_found" in d
        assert "hedge_count" in d
        assert "rp_score" in d


# =============================================================================
# ExitShapeChecker tests
# =============================================================================


class TestExitShapeChecker:
    """Test exit shape checking."""

    def test_clean_exit_no_bad_patterns(self):
        checker = ExitShapeChecker()
        result = checker.check_exit("The analysis is complete.")
        assert not result.has_bad_exit
        assert result.severity == 0.0

    def test_hope_this_helps_detected(self):
        checker = ExitShapeChecker()
        text = "That's the solution. I hope this helps!"
        result = checker.check_exit(text)
        assert result.has_bad_exit
        assert "hope" in str(result.bad_patterns_found).lower() or len(result.bad_patterns_found) > 0

    def test_let_me_know_detected(self):
        checker = ExitShapeChecker()
        text = "Done! Let me know if you have questions."
        result = checker.check_exit(text)
        assert result.has_bad_exit

    def test_in_conclusion_detected(self):
        checker = ExitShapeChecker()
        text = "In conclusion, we have demonstrated the theorem."
        result = checker.check_exit(text)
        assert result.has_bad_exit

    def test_feel_free_detected(self):
        checker = ExitShapeChecker()
        text = "That's all. Feel free to reach out anytime."
        result = checker.check_exit(text)
        assert result.has_bad_exit

    def test_multiple_bad_patterns_increase_severity(self):
        checker = ExitShapeChecker()
        text = "In conclusion, I hope this helps. Let me know if you need more. Feel free to ask."
        result = checker.check_exit(text)
        assert result.has_bad_exit
        assert result.severity > 0.3

    def test_tail_words_parameter(self):
        checker = ExitShapeChecker(tail_words=10)
        # Bad pattern early in text, not in tail
        text = "I hope this helps. " + ("Normal text. " * 50) + "The end."
        result = checker.check_exit(text)
        # Should not detect because "hope this helps" is not in last 10 words
        assert not result.has_bad_exit

    def test_empty_text_no_crash(self):
        checker = ExitShapeChecker()
        result = checker.check_exit("")
        assert not result.has_bad_exit

    def test_to_dict_returns_all_fields(self):
        checker = ExitShapeChecker()
        result = checker.check_exit("Some text")
        d = result.to_dict()
        assert "bad_patterns_found" in d
        assert "has_bad_exit" in d
        assert "severity" in d


# =============================================================================
# GovernanceChecker (combined) tests
# =============================================================================


class TestGovernanceChecker:
    """Test combined governance checking."""

    def test_clean_text_passes_all_checks(self):
        checker = GovernanceChecker()
        text = "The dragon soared through the sky, breathing fire on its enemies."
        result = checker.check(text)
        assert not result.governance_surfaced
        assert result.overall_governance_score < 0.3

    def test_governance_surfaced_on_visibility_breach(self):
        checker = GovernanceChecker(gv_ceiling=0.2)
        text = """
        Before you argue, I know many will disagree. Studies show that
        experts agree on this. It's important to acknowledge this.
        """
        result = checker.check(text)
        assert result.visibility.exceeds_ceiling
        assert result.governance_surfaced

    def test_governance_surfaced_on_leak(self):
        checker = GovernanceChecker(leak_threshold=0.2)
        text = """
        I want to be clear about this balanced and nuanced approach.
        We should proceed carefully and professionally with respect.
        """
        result = checker.check(text)
        assert result.leak.has_leak
        assert result.governance_surfaced

    def test_governance_surfaced_on_rp_floor_breach(self):
        checker = GovernanceChecker(rp_floor=0.7)
        text = """
        As an AI, I should note that maybe sort of perhaps
        on the one hand, to be fair, it's complicated.
        """
        result = checker.check(text)
        assert result.smoothing.below_rp_floor
        assert result.governance_surfaced

    def test_governance_surfaced_on_bad_exit(self):
        checker = GovernanceChecker()
        text = "The solution is X. I hope this helps! Let me know if you need more."
        result = checker.check(text)
        assert result.exit.has_bad_exit
        assert result.governance_surfaced

    def test_overall_score_combines_signals(self):
        checker = GovernanceChecker()
        # Multiple governance signals
        text = """
        Before you argue, studies show experts agree. I want to be clear,
        professionally speaking, it's balanced and nuanced. To be fair,
        maybe sort of. I hope this helps!
        """
        result = checker.check(text)
        assert result.overall_governance_score > 0.3
        assert result.governance_surfaced

    def test_overall_score_capped_at_one(self):
        checker = GovernanceChecker()
        # Extremely governance-laden text
        text = " ".join([
            "Before anyone argues, studies show experts agree.",
            "I want to be clear. I should note professionally.",
            "As an AI, I'm sorry. I hope this helps.",
        ] * 10)
        result = checker.check(text)
        assert result.overall_governance_score <= 1.0

    def test_to_dict_returns_all_nested_fields(self):
        checker = GovernanceChecker()
        result = checker.check("Some text")
        d = result.to_dict()
        assert "visibility" in d
        assert "leak" in d
        assert "smoothing" in d
        assert "exit" in d
        assert "overall_governance_score" in d
        assert "governance_surfaced" in d


# =============================================================================
# Constants tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_gv_ceiling_reasonable(self):
        assert 0.0 < GV_CEILING < 1.0

    def test_rp_floor_reasonable(self):
        assert 0.0 < RP_FLOOR < 1.0


# =============================================================================
# Dataclass tests
# =============================================================================


class TestDataclasses:
    """Test dataclass construction and defaults."""

    def test_governance_visibility_result_defaults(self):
        result = GovernanceVisibilityResult()
        assert result.preemptive_defense == 0
        assert result.overall_score == 0.0
        assert not result.exceeds_ceiling

    def test_governance_leak_result_defaults(self):
        result = GovernanceLeakResult()
        assert result.hr_voice == 0
        assert result.governance_leak_score == 0.0
        assert not result.has_leak

    def test_smoothing_result_defaults(self):
        result = SmoothingResult()
        assert result.banned_phrases_found == []
        assert result.rp_score == 1.0
        assert not result.below_rp_floor

    def test_exit_check_result_defaults(self):
        result = ExitCheckResult()
        assert result.bad_patterns_found == []
        assert not result.has_bad_exit
        assert result.severity == 0.0
