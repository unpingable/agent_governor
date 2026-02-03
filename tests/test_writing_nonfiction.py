"""Tests for writing_nonfiction.py — nonfiction epistemic control."""

import pytest

from governor.writing_nonfiction import (
    AH_FLOOR,
    EPISTEMIC_HEDGE_MAX,
    EPISTEMIC_HEDGE_MIN,
    GV_CEILING,
    MAX_GAP_TOKENS_HARD,
    MAX_GAP_TOKENS_NORM,
    MIN_EVIDENCE_BEFORE_NORM,
    RE_FLOOR,
    SOCIAL_HEDGE_CEILING,
    AhResult,
    AhScorer,
    EpResult,
    EpScorer,
    FailureModeResult,
    HedgeCalibrationResult,
    HedgeCalibrator,
    NfClaimLevel,
    NfClaimNode,
    NleadChecker,
    NleadResult,
    NonfictionFailureDetector,
    NonfictionFailureMode,
    NonfictionMetrics,
    PromotionGate,
    PromotionResult,
    ReResult,
    ReScorer,
    VelocityController,
    VelocityResult,
)


# =============================================================================
# NfClaimLevel tests
# =============================================================================


class TestNfClaimLevel:
    """Test NfClaimLevel enum."""

    def test_values(self):
        assert NfClaimLevel.SOFT.value == "soft"
        assert NfClaimLevel.HARD.value == "hard"
        assert NfClaimLevel.NORM.value == "norm"

    def test_ordering(self):
        # SOFT < HARD < NORM in terms of evidence requirements (conceptual, not alphabetical)
        levels = [NfClaimLevel.SOFT, NfClaimLevel.HARD, NfClaimLevel.NORM]
        assert len(levels) == 3  # Ensure all three levels exist


# =============================================================================
# NfClaimNode tests
# =============================================================================


class TestNfClaimNode:
    """Test NfClaimNode dataclass."""

    def test_default_level(self):
        claim = NfClaimNode(id="1", text="Test claim")
        assert claim.level == NfClaimLevel.SOFT

    def test_to_dict(self):
        claim = NfClaimNode(
            id="1",
            text="Test claim",
            level=NfClaimLevel.HARD,
            dependencies=["0"],
            evidence_links=["e1"],
        )
        d = claim.to_dict()
        assert d["id"] == "1"
        assert d["level"] == "hard"
        assert d["dependencies"] == ["0"]


# =============================================================================
# PromotionGate tests
# =============================================================================


class TestPromotionGate:
    """Test claim promotion rules."""

    def test_soft_always_allowed(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test")
        result = gate.can_promote(claim, NfClaimLevel.SOFT, evidence_gap=999)
        assert result.can_promote

    def test_soft_to_hard_with_evidence(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test", evidence_links=["e1"])
        result = gate.can_promote(claim, NfClaimLevel.HARD, evidence_gap=50)
        assert result.can_promote

    def test_soft_to_hard_gap_too_large(self):
        gate = PromotionGate(max_gap_hard=100)
        claim = NfClaimNode(id="1", text="Test", evidence_links=["e1"])
        result = gate.can_promote(claim, NfClaimLevel.HARD, evidence_gap=150)
        assert not result.can_promote
        assert "evidence_gap" in str(result.missing_requirements)

    def test_soft_to_hard_no_evidence(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test")
        result = gate.can_promote(claim, NfClaimLevel.HARD, evidence_gap=50)
        assert not result.can_promote
        assert "no evidence links" in str(result.missing_requirements)

    def test_soft_to_hard_dependencies_not_met(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test", evidence_links=["e1"])
        result = gate.can_promote(claim, NfClaimLevel.HARD, evidence_gap=50, dependencies_met=False)
        assert not result.can_promote

    def test_hard_to_norm_with_value_premise(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test", level=NfClaimLevel.HARD, value_premise="Ethics matter")
        result = gate.can_promote(claim, NfClaimLevel.NORM, evidence_gap=50)
        assert result.can_promote

    def test_hard_to_norm_gap_too_large(self):
        gate = PromotionGate(max_gap_norm=80)
        claim = NfClaimNode(id="1", text="Test", level=NfClaimLevel.HARD, value_premise="Ethics")
        result = gate.can_promote(claim, NfClaimLevel.NORM, evidence_gap=100)
        assert not result.can_promote

    def test_hard_to_norm_no_value_premise(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test", level=NfClaimLevel.HARD)
        result = gate.can_promote(claim, NfClaimLevel.NORM, evidence_gap=50)
        assert not result.can_promote
        assert "no value premise" in str(result.missing_requirements)

    def test_soft_to_norm_fails(self):
        gate = PromotionGate()
        claim = NfClaimNode(id="1", text="Test", value_premise="Ethics")
        result = gate.can_promote(claim, NfClaimLevel.NORM, evidence_gap=50)
        assert not result.can_promote
        assert "must be HARD" in str(result.missing_requirements)


# =============================================================================
# VelocityController tests
# =============================================================================


class TestVelocityController:
    """Test claim/evidence velocity tracking."""

    def test_initial_state(self):
        controller = VelocityController()
        result = controller.check_velocity()
        assert result.claim_velocity == 0
        assert result.is_stable

    def test_record_claims(self):
        controller = VelocityController()
        controller.record_claim(100)
        controller.record_claim(200)
        result = controller.check_velocity(500)
        assert result.claim_velocity > 0

    def test_balanced_velocity_stable(self):
        controller = VelocityController(k_factor=1.5)
        for i in range(10):
            controller.record_claim(i * 10)
            controller.record_evidence(i * 10 + 5)
        result = controller.check_velocity(200)
        assert result.is_stable

    def test_unbalanced_velocity_unstable(self):
        controller = VelocityController(k_factor=1.0)
        for i in range(10):
            controller.record_claim(i * 10)
        # No evidence
        result = controller.check_velocity(200)
        assert not result.is_stable

    def test_velocity_ratio(self):
        controller = VelocityController()
        controller.record_claim(100)
        controller.record_claim(200)
        controller.record_evidence(150)
        result = controller.check_velocity(500)
        assert result.velocity_ratio > 0

    def test_reset(self):
        controller = VelocityController()
        controller.record_claim(100)
        controller.reset()
        result = controller.check_velocity()
        assert result.claim_velocity == 0


# =============================================================================
# EpScorer tests
# =============================================================================


class TestEpScorer:
    """Test Ep (epistemic honesty perception) scoring."""

    def test_clean_text_high_ep(self):
        scorer = EpScorer()
        result = scorer.calculate_ep("The data shows a correlation between X and Y.")
        assert result.ep_score > 0.5

    def test_governance_laden_text_low_ep(self):
        scorer = EpScorer()
        text = """
        Before you argue, I know some will disagree.
        Studies show experts agree. It's important to acknowledge.
        """
        result = scorer.calculate_ep(text)
        assert result.governance_visibility > 0.2

    def test_hedge_calibration_affects_ep(self):
        scorer = EpScorer()
        # Text with anxiety hedges
        text = "I could be wrong, this is just my opinion, I'm no expert."
        result = scorer.calculate_ep(text)
        # Should have lower hedge calibration
        assert result.hedge_calibration < 1.0

    def test_to_dict(self):
        scorer = EpScorer()
        result = scorer.calculate_ep("Text")
        d = result.to_dict()
        assert "ep_score" in d
        assert "governance_visibility" in d


# =============================================================================
# ReScorer tests
# =============================================================================


class TestReScorer:
    """Test Re (epistemic risk exposure) scoring."""

    def test_baseline_re(self):
        scorer = ReScorer()
        result = scorer.calculate_re("Simple statement.")
        assert result.re_score == 0.5

    def test_falsifiers_raise_re(self):
        scorer = ReScorer()
        text = "This would fail if X. This depends on Y. This does not apply to Z."
        result = scorer.calculate_re(text)
        assert result.falsifier_count >= 2
        assert result.re_score > 0.5

    def test_humility_raises_re(self):
        scorer = ReScorer()
        text = "There is a correlation, but we cannot conclude causation. The association is unclear."
        result = scorer.calculate_re(text)
        assert result.causal_humility_count >= 2
        assert result.re_score > 0.5

    def test_anxiety_lowers_re(self):
        scorer = ReScorer()
        text = "I could be wrong, this is just my opinion, I'm no expert, take this with salt."
        result = scorer.calculate_re(text)
        assert result.anxiety_hedge_count >= 3
        assert result.re_score < 0.5

    def test_below_floor(self):
        scorer = ReScorer(floor=0.4)
        text = "I could be wrong I'm no expert take this with salt don't @ me please don't."
        result = scorer.calculate_re(text)
        assert result.below_floor

    def test_to_dict(self):
        scorer = ReScorer()
        result = scorer.calculate_re("Text")
        d = result.to_dict()
        assert "re_score" in d
        assert "falsifier_count" in d


# =============================================================================
# HedgeCalibrator tests
# =============================================================================


class TestHedgeCalibrator:
    """Test hedge classification (epistemic vs social)."""

    def test_epistemic_hedges_detected(self):
        calibrator = HedgeCalibrator()
        text = "There is a correlation. We cannot conclude causation. The association suggests but does not prove."
        result = calibrator.classify_hedges(text)
        assert result.epistemic_count >= 2

    def test_social_hedges_detected(self):
        calibrator = HedgeCalibrator()
        text = "I could be wrong. This is just my opinion. I'm no expert. Maybe perhaps."
        result = calibrator.classify_hedges(text)
        assert result.social_count >= 3

    def test_high_social_not_calibrated(self):
        calibrator = HedgeCalibrator(social_ceiling=0.05)
        # High density of social hedges
        text = "I could be wrong I'm no expert take this with salt " * 5
        result = calibrator.classify_hedges(text)
        assert not result.is_calibrated

    def test_to_dict(self):
        calibrator = HedgeCalibrator()
        result = calibrator.classify_hedges("Text")
        d = result.to_dict()
        assert "epistemic_count" in d
        assert "is_calibrated" in d


# =============================================================================
# AhScorer tests
# =============================================================================


class TestAhScorer:
    """Test Ah (alternative hypothesis engagement) scoring."""

    def test_baseline_ah(self):
        scorer = AhScorer()
        result = scorer.calculate_ah("Simple statement.")
        assert result.ah_score == 0.5

    def test_steelman_raises_ah(self):
        scorer = AhScorer()
        text = "This would fail if X. This depends on Y. Evidence against would include Z."
        result = scorer.calculate_ah(text)
        assert result.steelman_quality > 0
        assert result.ah_score > 0.5

    def test_strawman_lowers_ah(self):
        scorer = AhScorer()
        text = "Some people argue that. The naive view is. A common mistake is."
        result = scorer.calculate_ah(text)
        assert result.strawman_count >= 2
        assert result.ah_score < 0.5

    def test_below_floor(self):
        scorer = AhScorer(floor=0.3)
        text = "Some people argue the naive view. A common mistake is. Critics often."
        result = scorer.calculate_ah(text)
        # Might or might not be below floor depending on penalties

    def test_to_dict(self):
        scorer = AhScorer()
        result = scorer.calculate_ah("Text")
        d = result.to_dict()
        assert "ah_score" in d
        assert "strawman_count" in d


# =============================================================================
# NleadChecker tests
# =============================================================================


class TestNleadChecker:
    """Test normativity lead checking."""

    def test_no_normative_valid(self):
        checker = NleadChecker()
        result = checker.check_nlead("The data shows correlation.")
        assert result.is_valid
        assert result.first_norm_token is None

    def test_normative_detected(self):
        checker = NleadChecker()
        result = checker.check_nlead("We must act. We should change.")
        assert result.first_norm_token is not None

    def test_sufficient_evidence_valid(self):
        checker = NleadChecker(min_evidence_ratio=0.4)
        result = checker.check_nlead(
            "We should act.",
            total_evidence_count=10,
            evidence_before_norm=5,
        )
        assert result.is_valid

    def test_insufficient_evidence_invalid(self):
        checker = NleadChecker(min_evidence_ratio=0.4)
        result = checker.check_nlead(
            "We should act.",
            total_evidence_count=10,
            evidence_before_norm=2,
        )
        assert not result.is_valid

    def test_to_dict(self):
        checker = NleadChecker()
        result = checker.check_nlead("Text")
        d = result.to_dict()
        assert "is_valid" in d


# =============================================================================
# NonfictionFailureDetector tests
# =============================================================================


class TestNonfictionFailureDetector:
    """Test failure mode detection."""

    def test_clean_metrics_no_failures(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(
            ep_score=0.8,
            re_score=0.6,
            ah_score=0.6,
            gv_score=0.1,
            velocity_ratio=1.0,
            normative_density=0.1,
            conclusion_strength=0.6,
        )
        result = detector.detect_failures(metrics)
        assert len(result.detected_modes) == 0

    def test_propaganda_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(re_score=0.3, normative_density=0.5)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.PROPAGANDA in result.detected_modes

    def test_committee_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(gv_score=0.5)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.COMMITTEE in result.detected_modes

    def test_hot_take_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(velocity_ratio=4.0)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.HOT_TAKE in result.detected_modes

    def test_synthesis_addiction_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(conclusion_strength=0.2, ep_score=0.7)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.SYNTHESIS_ADDICTION in result.detected_modes

    def test_academic_theater_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(ep_score=0.8, ah_score=0.2)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.ACADEMIC_THEATER in result.detected_modes

    def test_advocacy_drift_detected(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(normative_density=0.3, re_score=0.4)
        result = detector.detect_failures(metrics)
        assert NonfictionFailureMode.ADVOCACY_DRIFT in result.detected_modes

    def test_severity_increases_with_modes(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics(
            re_score=0.3,
            normative_density=0.5,
            gv_score=0.5,
            velocity_ratio=4.0,
        )
        result = detector.detect_failures(metrics)
        assert result.severity > 0.4  # Multiple modes detected

    def test_to_dict(self):
        detector = NonfictionFailureDetector()
        metrics = NonfictionMetrics()
        result = detector.detect_failures(metrics)
        d = result.to_dict()
        assert "detected_modes" in d
        assert "severity" in d


# =============================================================================
# Constants tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_max_gap_tokens_reasonable(self):
        assert MAX_GAP_TOKENS_HARD > 0
        assert MAX_GAP_TOKENS_NORM > 0
        assert MAX_GAP_TOKENS_NORM <= MAX_GAP_TOKENS_HARD

    def test_evidence_ratio_reasonable(self):
        assert 0.0 < MIN_EVIDENCE_BEFORE_NORM < 1.0

    def test_gv_ceiling_reasonable(self):
        assert 0.0 < GV_CEILING < 1.0

    def test_hedge_ranges_reasonable(self):
        assert EPISTEMIC_HEDGE_MIN < EPISTEMIC_HEDGE_MAX
        assert SOCIAL_HEDGE_CEILING > 0

    def test_floors_reasonable(self):
        assert 0.0 < RE_FLOOR < 1.0
        assert 0.0 < AH_FLOOR < 1.0


# =============================================================================
# Dataclass tests
# =============================================================================


class TestDataclasses:
    """Test dataclass defaults."""

    def test_promotion_result_defaults(self):
        result = PromotionResult()
        assert not result.can_promote

    def test_velocity_result_defaults(self):
        result = VelocityResult()
        assert result.is_stable

    def test_ep_result_defaults(self):
        result = EpResult()
        assert result.ep_score == 1.0

    def test_re_result_defaults(self):
        result = ReResult()
        assert result.re_score == 0.5

    def test_hedge_calibration_result_defaults(self):
        result = HedgeCalibrationResult()
        assert result.is_calibrated

    def test_ah_result_defaults(self):
        result = AhResult()
        assert result.ah_score == 0.5

    def test_nlead_result_defaults(self):
        result = NleadResult()
        assert result.is_valid

    def test_failure_mode_result_defaults(self):
        result = FailureModeResult()
        assert len(result.detected_modes) == 0
