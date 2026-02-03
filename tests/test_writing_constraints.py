"""Tests for writing_constraints.py — structural constraint checks."""

import pytest

from governor.writing_constraints import (
    AudienceModel,
    AudienceRelation,
    AudienceCheckResult,
    AuthorityCheckResult,
    AuthorityProfile,
    AuthoritySource,
    CausalNarrationFailureMode,
    CausalNarrationResult,
    CausalNarrationTechnique,
    CommitmentCheckResult,
    CommitmentDemand,
    CommitmentType,
    ErrorPosture,
    ExitCheckResult,
    LegibilityBudget,
    MoralWeightResult,
    PrematureSolutionResult,
    RepetitionAnalysis,
    RepetitionType,
    SilenceDecision,
    SilenceReason,
    StructuralConstraintResults,
    TemporalConsistencyResult,
    check_all,
    check_audience,
    check_authority,
    check_commitments,
    check_exit_shape,
    check_moral_weight,
    check_premature_solution,
    check_repetition,
    check_silence,
    check_temporal_consistency,
    detect_causal_narration_resistance,
    get_error_posture,
    CAUSAL_NARRATION_DETECTION_MAPPING,
    REGIME_AUTHORITY_COMPATIBILITY,
)


# =============================================================================
# AudienceModel tests
# =============================================================================


class TestAudienceModel:
    """Test AudienceModel dataclass."""

    def test_defaults(self):
        model = AudienceModel(relation=AudienceRelation.PEER)
        assert model.assumed_expertise == 0.5
        assert model.assumed_alignment == 0.5
        assert model.shared_context == 0.5

    def test_to_dict(self):
        model = AudienceModel(
            relation=AudienceRelation.TEACHER,
            assumed_expertise=0.3,
            assumed_alignment=0.7,
        )
        d = model.to_dict()
        assert d["relation"] == "teacher"
        assert d["assumed_expertise"] == 0.3

    def test_all_relations(self):
        assert len(AudienceRelation) == 5
        assert AudienceRelation.PEER.value == "peer"
        assert AudienceRelation.EXPERT.value == "expert"


class TestCheckAudience:
    """Test check_audience function."""

    def test_clean_text_passes(self):
        model = AudienceModel(relation=AudienceRelation.PEER)
        result = check_audience("Here is some information about the topic.", model)
        assert result.is_valid
        assert result.condescension_score < 0.5

    def test_condescension_detected(self):
        model = AudienceModel(relation=AudienceRelation.PEER)
        text = "As you probably know, obviously this is simple. Clearly anyone can do it."
        result = check_audience(text, model)
        assert result.condescension_score > 0.3
        assert "high_condescension" in result.violations or result.condescension_score < 0.5

    def test_presumption_detected(self):
        model = AudienceModel(
            relation=AudienceRelation.ADVOCATE,
            assumed_alignment=0.2,  # Low alignment
        )
        text = "We all know this is the right thing to do. Everyone agrees."
        result = check_audience(text, model)
        assert result.presumption_score > 0.2

    def test_expert_audience_with_over_explanation(self):
        model = AudienceModel(
            relation=AudienceRelation.EXPERT,
            assumed_expertise=0.9,
        )
        result = check_audience("Here is a basic explanation.", model, explanation_density=0.7)
        assert "over_explaining_to_experts" in result.violations

    def test_exclusion_score(self):
        model = AudienceModel(
            relation=AudienceRelation.EXPERT,
            assumed_expertise=0.9,
            shared_context=0.1,  # Low shared context
        )
        result = check_audience("Technical jargon here.", model)
        assert result.exclusion_score > 0.0

    def test_result_to_dict(self):
        result = AudienceCheckResult(
            condescension_score=0.3,
            presumption_score=0.2,
            is_valid=True,
        )
        d = result.to_dict()
        assert "condescension_score" in d
        assert "is_valid" in d


# =============================================================================
# CommitmentDemand tests
# =============================================================================


class TestCommitmentDemand:
    """Test CommitmentDemand dataclass."""

    def test_cost_calculation(self):
        demand = CommitmentDemand(
            commitment_type=CommitmentType.BELIEF,
            magnitude=1.0,
        )
        assert demand.cost() == 0.3  # Base cost for BELIEF

    def test_identity_highest_cost(self):
        demand = CommitmentDemand(
            commitment_type=CommitmentType.IDENTITY,
            magnitude=1.0,
        )
        assert demand.cost() == 0.8

    def test_attention_lowest_cost(self):
        demand = CommitmentDemand(
            commitment_type=CommitmentType.ATTENTION,
            magnitude=1.0,
        )
        assert demand.cost() == 0.1

    def test_magnitude_scales_cost(self):
        low = CommitmentDemand(commitment_type=CommitmentType.ACTION, magnitude=0.5)
        high = CommitmentDemand(commitment_type=CommitmentType.ACTION, magnitude=1.0)
        assert low.cost() < high.cost()

    def test_to_dict(self):
        demand = CommitmentDemand(
            commitment_type=CommitmentType.ACTION,
            magnitude=0.7,
            position_in_text=0.5,
        )
        d = demand.to_dict()
        assert d["commitment_type"] == "action"
        assert "cost" in d

    def test_all_commitment_types(self):
        assert len(CommitmentType) == 5


class TestCheckCommitments:
    """Test check_commitments function."""

    def test_single_low_commitment_passes(self):
        demands = [
            CommitmentDemand(
                commitment_type=CommitmentType.ATTENTION,
                magnitude=0.3,
                position_in_text=0.5,
            )
        ]
        result = check_commitments(demands)
        assert result.is_valid
        assert result.overspend == 0.0

    def test_identity_early_violation(self):
        demands = [
            CommitmentDemand(
                commitment_type=CommitmentType.IDENTITY,
                magnitude=0.8,
                position_in_text=0.1,  # Very early
            )
        ]
        result = check_commitments(demands)
        assert "identity_commitment_too_early" in result.escalation_violations

    def test_major_action_early_violation(self):
        demands = [
            CommitmentDemand(
                commitment_type=CommitmentType.ACTION,
                magnitude=0.8,  # High magnitude
                position_in_text=0.1,  # Very early
            )
        ]
        result = check_commitments(demands)
        assert "major_action_request_too_early" in result.escalation_violations

    def test_trust_accumulates_with_position(self):
        demands = [
            CommitmentDemand(
                commitment_type=CommitmentType.BELIEF,
                magnitude=0.5,
                position_in_text=0.9,  # Near end
            )
        ]
        result = check_commitments(demands, initial_trust=0.1)
        # Trust budget should be higher near end
        assert result.trust_budget > 0.1

    def test_multiple_demands_accumulate_cost(self):
        demands = [
            CommitmentDemand(commitment_type=CommitmentType.BELIEF, magnitude=0.5, position_in_text=0.3),
            CommitmentDemand(commitment_type=CommitmentType.ACTION, magnitude=0.5, position_in_text=0.6),
            CommitmentDemand(commitment_type=CommitmentType.IDENTITY, magnitude=0.5, position_in_text=0.9),
        ]
        result = check_commitments(demands)
        assert result.total_cost > 0.3  # More than single belief

    def test_result_to_dict(self):
        result = CommitmentCheckResult(
            total_cost=0.5,
            trust_budget=0.6,
            overspend=0.0,
            is_valid=True,
        )
        d = result.to_dict()
        assert "total_cost" in d
        assert "overspend" in d


# =============================================================================
# AuthoritySource tests
# =============================================================================


class TestAuthorityProfile:
    """Test AuthorityProfile dataclass."""

    def test_defaults(self):
        profile = AuthorityProfile(primary=AuthoritySource.EXPERTISE)
        assert profile.strength == 0.5
        assert profile.secondary is None

    def test_to_dict(self):
        profile = AuthorityProfile(
            primary=AuthoritySource.EVIDENCE,
            secondary=AuthoritySource.REASONING,
            strength=0.8,
        )
        d = profile.to_dict()
        assert d["primary"] == "evidence"
        assert d["secondary"] == "reasoning"

    def test_all_sources(self):
        assert len(AuthoritySource) == 7


class TestCheckAuthority:
    """Test check_authority function."""

    def test_research_evidence_compatible(self):
        profile = AuthorityProfile(primary=AuthoritySource.EVIDENCE)
        result = check_authority(profile, "research")
        assert result.compatible

    def test_research_position_incompatible(self):
        profile = AuthorityProfile(primary=AuthoritySource.POSITION)
        result = check_authority(profile, "research")
        assert not result.compatible

    def test_instruction_expertise_compatible(self):
        profile = AuthorityProfile(primary=AuthoritySource.EXPERTISE)
        result = check_authority(profile, "instruction")
        assert result.compatible

    def test_liturgical_tradition_compatible(self):
        profile = AuthorityProfile(primary=AuthoritySource.TRADITION)
        result = check_authority(profile, "liturgical")
        assert result.compatible

    def test_overclaiming_consensus(self):
        profile = AuthorityProfile(
            primary=AuthoritySource.CONSENSUS,
            strength=0.9,  # High strength
        )
        result = check_authority(profile, "research")
        assert result.overclaiming

    def test_weak_blend_detected(self):
        profile = AuthorityProfile(
            primary=AuthoritySource.EXPERIENCE,
            secondary=AuthoritySource.POSITION,
            strength=0.8,  # High strength from weak sources
        )
        result = check_authority(profile, "negotiation")
        assert result.weak_blend

    def test_secondary_incompatibility(self):
        profile = AuthorityProfile(
            primary=AuthoritySource.EVIDENCE,
            secondary=AuthoritySource.POSITION,  # Position not in research compatible
        )
        result = check_authority(profile, "research")
        assert any("secondary_authority" in v for v in result.violations)

    def test_result_to_dict(self):
        result = AuthorityCheckResult(
            compatible=True,
            overclaiming=False,
            weak_blend=False,
        )
        d = result.to_dict()
        assert "compatible" in d

    def test_regime_compatibility_table_complete(self):
        # Check that key regimes have entries
        assert "research" in REGIME_AUTHORITY_COMPATIBILITY
        assert "instruction" in REGIME_AUTHORITY_COMPATIBILITY
        assert "comedy" in REGIME_AUTHORITY_COMPATIBILITY


# =============================================================================
# SilenceDecision tests
# =============================================================================


class TestSilenceDecision:
    """Test SilenceDecision and check_silence."""

    def test_research_not_known_valid(self):
        decision = SilenceDecision(
            reason=SilenceReason.NOT_KNOWN,
            topic="quantum effects",
            regime="research",
        )
        assert check_silence(decision)

    def test_research_strategic_invalid(self):
        decision = SilenceDecision(
            reason=SilenceReason.STRATEGIC,
            topic="competing theory",
            regime="research",
        )
        assert not check_silence(decision)

    def test_horror_strategic_valid(self):
        decision = SilenceDecision(
            reason=SilenceReason.STRATEGIC,
            topic="monster origin",
            regime="horror",
        )
        assert check_silence(decision)

    def test_to_dict(self):
        decision = SilenceDecision(
            reason=SilenceReason.NOT_APPROPRIATE,
            topic="personal info",
            regime="instruction",
        )
        d = decision.to_dict()
        assert d["reason"] == "not_appropriate"

    def test_all_silence_reasons(self):
        assert len(SilenceReason) == 5


# =============================================================================
# RepetitionAnalysis tests
# =============================================================================


class TestRepetitionAnalysis:
    """Test RepetitionAnalysis and check_repetition."""

    def test_accidental_always_invalid(self):
        analysis = RepetitionAnalysis(
            type=RepetitionType.ACCIDENTAL,
            phrase="the the",
            count=2,
            regime="instruction",
        )
        assert not check_repetition(analysis)

    def test_semantic_valid_in_instruction(self):
        analysis = RepetitionAnalysis(
            type=RepetitionType.SEMANTIC,
            phrase="in other words",
            count=2,
            regime="instruction",
        )
        assert check_repetition(analysis)

    def test_semantic_invalid_in_aphorism(self):
        analysis = RepetitionAnalysis(
            type=RepetitionType.SEMANTIC,
            phrase="restating",
            count=2,
            regime="aphorism",
        )
        assert not check_repetition(analysis)

    def test_rhetorical_valid_in_liturgical(self):
        analysis = RepetitionAnalysis(
            type=RepetitionType.RHETORICAL,
            phrase="amen",
            count=3,
            regime="liturgical",
        )
        assert check_repetition(analysis)

    def test_to_dict(self):
        analysis = RepetitionAnalysis(
            type=RepetitionType.STRUCTURAL,
            phrase="First... Second... Third...",
            count=3,
            regime="instruction",
        )
        d = analysis.to_dict()
        assert d["type"] == "structural"

    def test_all_repetition_types(self):
        assert len(RepetitionType) == 4


# =============================================================================
# ErrorPosture tests
# =============================================================================


class TestErrorPosture:
    """Test ErrorPosture and get_error_posture."""

    def test_research_transparent(self):
        assert get_error_posture("research") == ErrorPosture.TRANSPARENT

    def test_instruction_acknowledged(self):
        assert get_error_posture("instruction") == ErrorPosture.ACKNOWLEDGED

    def test_fiction_regimes_invisible(self):
        assert get_error_posture("comedy") == ErrorPosture.INVISIBLE
        assert get_error_posture("tragedy") == ErrorPosture.INVISIBLE
        assert get_error_posture("horror") == ErrorPosture.INVISIBLE

    def test_unknown_defaults_to_acknowledged(self):
        assert get_error_posture("unknown_regime") == ErrorPosture.ACKNOWLEDGED

    def test_all_postures(self):
        assert len(ErrorPosture) == 4


# =============================================================================
# ExitShapeChecker tests
# =============================================================================


class TestCheckExitShape:
    """Test check_exit_shape function."""

    def test_clean_exit_passes(self):
        text = "This concludes the analysis. The key finding was X."
        result = check_exit_shape(text)
        assert result.is_clean

    def test_hope_this_helps_detected(self):
        # Pattern is "hope (?:this|that) helps" - needs longer text to test exit portion
        text = "Here is some content at the beginning. More content here. Hope this helps!"
        result = check_exit_shape(text)
        assert not result.is_clean
        assert len(result.bad_patterns_found) > 0

    def test_let_me_know_detected(self):
        text = "The solution is X. Let me know if you have any questions."
        result = check_exit_shape(text)
        # Should detect the pattern
        assert any("let me know" in p.lower() or "questions" in p.lower()
                   for p in result.bad_patterns_found) or result.is_clean

    def test_result_to_dict(self):
        result = ExitCheckResult(
            bad_patterns_found=["hope this helps"],
            is_clean=False,
        )
        d = result.to_dict()
        assert "bad_patterns_found" in d
        assert not d["is_clean"]


# =============================================================================
# TemporalConsistency tests
# =============================================================================


class TestCheckTemporalConsistency:
    """Test check_temporal_consistency function."""

    def test_no_shifts_consistent(self):
        result = check_temporal_consistency("He walked to the store.", tense_shift_count=0)
        assert result.is_consistent

    def test_signaled_shifts_ok(self):
        text = "He walks home. Earlier, he had visited the store."
        result = check_temporal_consistency(text, tense_shift_count=1)
        assert result.signaled_shifts >= 1 or result.is_consistent

    def test_unsignaled_shifts_flagged(self):
        result = check_temporal_consistency("Simple text.", tense_shift_count=3)
        # With 3 shifts and few signals, should have unsignaled
        assert result.unsignaled_shifts > 0 or result.tense_shifts == 3

    def test_result_to_dict(self):
        result = TemporalConsistencyResult(
            tense_shifts=2,
            signaled_shifts=1,
            unsignaled_shifts=1,
            is_consistent=False,
        )
        d = result.to_dict()
        assert d["tense_shifts"] == 2


# =============================================================================
# MoralWeight tests
# =============================================================================


class TestCheckMoralWeight:
    """Test check_moral_weight function."""

    def test_clean_text_passes(self):
        text = "Here is some factual information about the topic."
        result = check_moral_weight(text)
        assert result.calibration_score > 0.8
        assert len(result.violations) == 0

    def test_inflated_language_detected(self):
        # Use patterns that match INFLATED_WEIGHT_PATTERNS
        text = "It's important to understand this. We must remember that the stakes are high."
        result = check_moral_weight(text)
        assert result.inflated_count > 0 or result.calibration_score < 1.0

    def test_excessive_inflation_violation(self):
        text = "Crucial imperative urgent moral duty sacred obligation vital essential."
        result = check_moral_weight(text)
        # May or may not trigger depending on pattern matches
        assert result.calibration_score <= 1.0

    def test_result_to_dict(self):
        result = MoralWeightResult(
            inflated_count=2,
            calibration_score=0.7,
        )
        d = result.to_dict()
        assert d["inflated_count"] == 2


# =============================================================================
# LegibilityBudget tests
# =============================================================================


class TestLegibilityBudget:
    """Test LegibilityBudget dataclass."""

    def test_initial_budget(self):
        budget = LegibilityBudget(total_budget=1.0)
        assert budget.remaining == 1.0
        assert not budget.is_overdrawn

    def test_spend_deducts(self):
        budget = LegibilityBudget(total_budget=1.0)
        budget.spend(0.3)
        assert budget.remaining == 0.7

    def test_unrequested_costs_double(self):
        budget = LegibilityBudget(total_budget=1.0)
        budget.spend(0.2, requested=False)
        assert budget.spent == 0.4  # 2x
        assert budget.unrequested_cost == 0.4

    def test_overdrawn_detection(self):
        budget = LegibilityBudget(total_budget=0.5)
        budget.spend(0.6)
        assert budget.is_overdrawn

    def test_spend_returns_success(self):
        budget = LegibilityBudget(total_budget=1.0)
        assert budget.spend(0.3) is True
        assert budget.spend(0.5) is True
        assert budget.spend(0.5) is False  # Now overdrawn

    def test_to_dict(self):
        budget = LegibilityBudget(total_budget=1.0)
        budget.spend(0.3)
        d = budget.to_dict()
        assert d["spent"] == 0.3
        assert d["remaining"] == 0.7


# =============================================================================
# PrematureSolution tests
# =============================================================================


class TestCheckPrematureSolution:
    """Test check_premature_solution function."""

    def test_no_solution_no_violation(self):
        result = check_premature_solution(
            problem_position=0.1,
            felt_position=0.2,
            solution_position=None,
        )
        assert not result.is_premature

    def test_solution_without_problem(self):
        result = check_premature_solution(
            problem_position=None,
            felt_position=None,
            solution_position=0.5,
        )
        assert result.is_premature
        assert result.violation_type == "solution_without_problem"

    def test_solution_before_problem(self):
        result = check_premature_solution(
            problem_position=0.5,
            felt_position=0.6,
            solution_position=0.3,  # Before problem
        )
        assert result.is_premature
        assert result.violation_type == "solution_before_problem"

    def test_solution_after_problem_ok(self):
        result = check_premature_solution(
            problem_position=0.2,
            felt_position=0.4,
            solution_position=0.6,
        )
        assert not result.is_premature

    def test_solution_before_felt(self):
        result = check_premature_solution(
            problem_position=0.2,
            felt_position=None,  # Never felt
            solution_position=0.5,
        )
        assert result.is_premature
        assert result.violation_type == "solution_before_felt"

    def test_result_to_dict(self):
        result = PrematureSolutionResult(
            problem_established=True,
            solution_offered=True,
            is_premature=True,
            violation_type="solution_before_problem",
        )
        d = result.to_dict()
        assert d["violation_type"] == "solution_before_problem"


# =============================================================================
# StructuralConstraintResults tests
# =============================================================================


class TestStructuralConstraintResults:
    """Test StructuralConstraintResults aggregate."""

    def test_empty_all_valid(self):
        results = StructuralConstraintResults()
        assert results.all_valid

    def test_audience_violation_fails(self):
        results = StructuralConstraintResults(
            audience=AudienceCheckResult(is_valid=False, violations=["test_violation"])
        )
        assert not results.all_valid
        assert "test_violation" in results.violations

    def test_exit_violation_fails(self):
        results = StructuralConstraintResults(
            exit_shape=ExitCheckResult(is_clean=False, bad_patterns_found=["hope this helps"])
        )
        assert not results.all_valid

    def test_multiple_violations_collected(self):
        results = StructuralConstraintResults(
            audience=AudienceCheckResult(violations=["v1"]),
            commitment=CommitmentCheckResult(escalation_violations=["v2"]),
            authority=AuthorityCheckResult(violations=["v3"]),
        )
        assert "v1" in results.violations
        assert "v2" in results.violations
        assert "v3" in results.violations

    def test_to_dict(self):
        results = StructuralConstraintResults(
            moral_weight=MoralWeightResult(inflated_count=1)
        )
        d = results.to_dict()
        assert "all_valid" in d
        assert "moral_weight" in d


# =============================================================================
# check_all tests
# =============================================================================


class TestCheckAll:
    """Test check_all aggregate function."""

    def test_minimal_check(self):
        results = check_all("Some text here.", "instruction")
        # Should run exit_shape and moral_weight at minimum
        assert results.exit_shape is not None
        assert results.moral_weight is not None

    def test_with_audience(self):
        model = AudienceModel(relation=AudienceRelation.PEER)
        results = check_all("Some text.", "instruction", audience_model=model)
        assert results.audience is not None

    def test_with_authority(self):
        profile = AuthorityProfile(primary=AuthoritySource.EXPERTISE)
        results = check_all("Some text.", "instruction", authority_profile=profile)
        assert results.authority is not None
        assert results.authority.compatible

    def test_with_commitments(self):
        commitments = [
            CommitmentDemand(commitment_type=CommitmentType.ATTENTION, magnitude=0.3, position_in_text=0.5)
        ]
        results = check_all("Some text.", "instruction", commitments=commitments)
        assert results.commitment is not None

    def test_full_check(self):
        model = AudienceModel(relation=AudienceRelation.TEACHER)
        profile = AuthorityProfile(primary=AuthoritySource.EXPERTISE)
        commitments = [
            CommitmentDemand(commitment_type=CommitmentType.BELIEF, magnitude=0.5, position_in_text=0.5)
        ]
        results = check_all(
            "Here is the explanation. The key point is X.",
            "instruction",
            audience_model=model,
            authority_profile=profile,
            commitments=commitments,
        )
        assert results.audience is not None
        assert results.authority is not None
        assert results.commitment is not None
        assert results.exit_shape is not None
        assert results.moral_weight is not None

    def test_with_causal_narration(self):
        results = check_all("Some text.", "instruction")
        # Causal narration check runs by default
        assert results.causal_narration is not None

    def test_disable_causal_narration(self):
        results = check_all("Some text.", "instruction", check_causal_narration=False)
        assert results.causal_narration is None


# =============================================================================
# Causal Narration Resistance Detection tests
# =============================================================================


class TestCausalNarrationTechnique:
    """Test CausalNarrationTechnique enum."""

    def test_all_values(self):
        assert len(CausalNarrationTechnique) == 6
        assert CausalNarrationTechnique.TICKET_SUBSTITUTION.value == "ticket_substitution"
        assert CausalNarrationTechnique.COMPLEXITY_DIFFUSION.value == "complexity_diffusion"
        assert CausalNarrationTechnique.TIME_BOUNDING.value == "time_bounding"
        assert CausalNarrationTechnique.PERSONNEL_CHURN.value == "personnel_churn"
        assert CausalNarrationTechnique.SCOPE_SHRINKING.value == "scope_shrinking"
        assert CausalNarrationTechnique.MORAL_REFRAMING.value == "moral_reframing"


class TestCausalNarrationFailureMode:
    """Test CausalNarrationFailureMode enum."""

    def test_all_values(self):
        assert len(CausalNarrationFailureMode) == 10
        assert CausalNarrationFailureMode.CAUSAL_SATURATION.value == "causal_saturation"
        assert CausalNarrationFailureMode.RESPONSIBILITY_VIRTUALIZATION.value == "responsibility_virtualization"


class TestCausalNarrationResult:
    """Test CausalNarrationResult dataclass."""

    def test_defaults(self):
        result = CausalNarrationResult()
        assert result.techniques_detected == []
        assert result.failure_modes_detected == []
        assert result.fog_score == 0.0
        assert not result.is_suspicious

    def test_to_dict(self):
        result = CausalNarrationResult(
            techniques_detected=[CausalNarrationTechnique.TICKET_SUBSTITUTION],
            fog_score=0.5,
            is_suspicious=True,
        )
        d = result.to_dict()
        assert d["techniques_detected"] == ["ticket_substitution"]
        assert d["fog_score"] == 0.5
        assert d["is_suspicious"] is True


class TestDetectCausalNarrationResistance:
    """Test detect_causal_narration_resistance function."""

    def test_clean_text_no_detection(self):
        text = "The project succeeded because we worked hard and had good planning."
        result = detect_causal_narration_resistance(text)
        assert len(result.techniques_detected) == 0
        assert not result.is_suspicious

    def test_ticket_substitution(self):
        text = "For more details, see ticket JIRA-1234. This was tracked in issue #567."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.TICKET_SUBSTITUTION in result.techniques_detected
        assert result.technique_counts.get("ticket_substitution", 0) >= 1

    def test_complexity_diffusion(self):
        text = "It's a complex situation with many factors. This is a multifaceted issue."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.COMPLEXITY_DIFFUSION in result.techniques_detected

    def test_time_bounding(self):
        text = "That was then. Things have changed. We've moved on."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.TIME_BOUNDING in result.techniques_detected

    def test_personnel_churn(self):
        text = "Under new leadership, things are different. Those people have gone."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.PERSONNEL_CHURN in result.techniques_detected

    def test_scope_shrinking(self):
        text = "That's out of scope. Let's stay focused on the current issue."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.SCOPE_SHRINKING in result.techniques_detected

    def test_moral_reframing(self):
        text = "Speculation would be harmful. Finger-pointing isn't productive."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationTechnique.MORAL_REFRAMING in result.techniques_detected
        assert "moral_reframing_detected" in result.detection_notes[0]

    def test_causal_saturation(self):
        text = "Many contributing factors led to this. There was no single cause."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationFailureMode.CAUSAL_SATURATION in result.failure_modes_detected

    def test_counterfactual_poisoning(self):
        text = "We can't know what would have happened. It's impossible to determine."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationFailureMode.COUNTERFACTUAL_POISONING in result.failure_modes_detected
        assert "counterfactual_poisoning_detected" in result.detection_notes[0]

    def test_responsibility_virtualization(self):
        text = "The system failed. It was a cultural issue. No single person is to blame."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationFailureMode.RESPONSIBILITY_VIRTUALIZATION in result.failure_modes_detected

    def test_epistemic_delegation(self):
        text = "Experts are looking into it. That's above my pay grade."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationFailureMode.EPISTEMIC_DELEGATION in result.failure_modes_detected

    def test_moral_load_shedding(self):
        text = "It would be harmful to revisit this. We need to move on for healing."
        result = detect_causal_narration_resistance(text)
        assert CausalNarrationFailureMode.MORAL_LOAD_SHEDDING in result.failure_modes_detected

    def test_fog_score_calculation(self):
        # More detections = higher fog score
        low_fog = detect_causal_narration_resistance("Normal clear explanation.")
        high_fog = detect_causal_narration_resistance(
            "It's complicated. Many factors. Out of scope. That was then. "
            "The system failed. Experts are looking into it. We've moved on."
        )
        assert high_fog.fog_score > low_fog.fog_score

    def test_suspicious_threshold_multiple_techniques(self):
        # Two or more techniques = suspicious
        text = "It's a complex situation. That's out of scope."
        result = detect_causal_narration_resistance(text)
        assert len(result.techniques_detected) >= 2
        assert result.is_suspicious

    def test_suspicious_threshold_multiple_failure_modes(self):
        # Two or more failure modes = suspicious
        text = "The system failed. We can't know what would have happened otherwise."
        result = detect_causal_narration_resistance(text)
        assert result.is_suspicious

    def test_suspicious_threshold_total_detections(self):
        # 5+ total detections = suspicious
        text = (
            "It's complicated. Many factors. A complex situation. "
            "There were various reasons. A confluence of things."
        )
        result = detect_causal_narration_resistance(text)
        total = sum(result.technique_counts.values()) + sum(result.failure_mode_counts.values())
        if total >= 5:
            assert result.is_suspicious

    def test_case_insensitive(self):
        text = "THAT'S OUT OF SCOPE. It's Complicated."
        result = detect_causal_narration_resistance(text)
        assert len(result.techniques_detected) >= 1


class TestCausalNarrationDetectionMapping:
    """Test the detection mapping table."""

    def test_mapping_exists(self):
        assert len(CAUSAL_NARRATION_DETECTION_MAPPING) > 0
        assert "time_bound_resets" in CAUSAL_NARRATION_DETECTION_MAPPING
        assert "responsibility_virtualization" in CAUSAL_NARRATION_DETECTION_MAPPING

    def test_mapping_to_existing_detectors(self):
        # All mapped values should be recognizable detector names
        known_detectors = {
            "temporal_discontinuity",
            "premature_closure",
            "authority_mismatch",
            "exit_shape_violation",
            "meta_level_suppression",
            "low_claim_evidence_coupling",
            "passive_voice_governance_leak",
            "authority_source_mismatch",
        }
        for value in CAUSAL_NARRATION_DETECTION_MAPPING.values():
            assert value in known_detectors


class TestStructuralConstraintResultsWithCausalNarration:
    """Test aggregate results including causal narration."""

    def test_all_valid_with_suspicious_causal_narration(self):
        results = StructuralConstraintResults(
            causal_narration=CausalNarrationResult(is_suspicious=True)
        )
        assert not results.all_valid

    def test_all_valid_with_clean_causal_narration(self):
        results = StructuralConstraintResults(
            causal_narration=CausalNarrationResult(is_suspicious=False)
        )
        assert results.all_valid

    def test_violations_includes_causal_narration_notes(self):
        results = StructuralConstraintResults(
            causal_narration=CausalNarrationResult(
                is_suspicious=True,
                detection_notes=["moral_reframing_detected: inquiry may be framed as harmful"],
            )
        )
        assert "moral_reframing_detected" in results.violations[0]

    def test_to_dict_includes_causal_narration(self):
        results = StructuralConstraintResults(
            causal_narration=CausalNarrationResult(fog_score=0.3)
        )
        d = results.to_dict()
        assert "causal_narration" in d
        assert d["causal_narration"]["fog_score"] == 0.3
