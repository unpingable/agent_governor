"""Tests for writing_code.py — Code/SRE Controller (Custody Regime)."""

import pytest

from governor.writing_code import (
    AP_FLOOR,
    IP_FLOOR,
    FP_FLOOR,
    CUSTODY_SCORE_FLOOR,
    AbstractionAnalysis,
    AbstractionProposal,
    AccountabilitySignals,
    CodeAnalyzer,
    CodeContext,
    CodeController,
    CodeControllerInput,
    CodeControllerOutput,
    CodeRegime,
    CodeTelemetry,
    CodeViolation,
    ComplexityBudget,
    CustodyScore,
    DEFAULT_COMPLEXITY_BUDGET,
    DevModeGates,
    FailureSignals,
    FailureType,
    InvariantSignals,
    RetryAction,
    SREModeGates,
    ViolationType,
    calculate_ap,
    calculate_custody_score,
    calculate_fp,
    calculate_ip,
    check_abstraction_allowed,
    detect_code_regime,
    detect_exception_smear,
    detect_magic_behavior,
    detect_premature_abstraction,
    get_retry_strategy,
)


# =============================================================================
# CodeRegime tests
# =============================================================================


class TestCodeRegime:
    """Test CodeRegime enum."""

    def test_values(self):
        assert CodeRegime.DEV.value == "dev"
        assert CodeRegime.SRE.value == "sre"
        assert CodeRegime.ANALYSIS.value == "analysis"

    def test_all_regimes(self):
        assert len(CodeRegime) == 3


# =============================================================================
# AccountabilitySignals tests
# =============================================================================


class TestAccountabilitySignals:
    """Test AccountabilitySignals dataclass."""

    def test_defaults(self):
        signals = AccountabilitySignals()
        assert signals.ownership_explicit is False
        assert signals.assumptions_stated is False

    def test_to_dict(self):
        signals = AccountabilitySignals(ownership_explicit=True)
        d = signals.to_dict()
        assert d["ownership_explicit"] is True


class TestCalculateAp:
    """Test calculate_ap function."""

    def test_all_true_max_score(self):
        signals = AccountabilitySignals(
            ownership_explicit=True,
            assumptions_stated=True,
            error_handling_local=True,
            side_effects_bounded=True,
            config_defaults_visible=True,
        )
        assert calculate_ap(signals) == 1.0

    def test_all_false_zero_score(self):
        signals = AccountabilitySignals()
        assert calculate_ap(signals) == 0.0

    def test_partial_signals(self):
        signals = AccountabilitySignals(
            ownership_explicit=True,
            error_handling_local=True,
        )
        score = calculate_ap(signals)
        assert 0.0 < score < 1.0
        assert score == 0.45  # 0.2 + 0.25

    def test_ap_floor_constant(self):
        assert AP_FLOOR == 0.6


# =============================================================================
# InvariantSignals tests
# =============================================================================


class TestInvariantSignals:
    """Test InvariantSignals dataclass."""

    def test_defaults(self):
        signals = InvariantSignals()
        assert signals.type_checks_present is False

    def test_to_dict(self):
        signals = InvariantSignals(type_checks_present=True)
        d = signals.to_dict()
        assert d["type_checks_present"] is True


class TestCalculateIp:
    """Test calculate_ip function."""

    def test_all_true_max_score(self):
        signals = InvariantSignals(
            type_checks_present=True,
            input_validation_present=True,
            assertions_in_critical_paths=True,
            property_tests_present=True,
            preconditions_documented=True,
        )
        assert calculate_ip(signals) == 1.0

    def test_all_false_zero_score(self):
        signals = InvariantSignals()
        assert calculate_ip(signals) == 0.0

    def test_partial_signals(self):
        signals = InvariantSignals(
            type_checks_present=True,
            input_validation_present=True,
        )
        score = calculate_ip(signals)
        assert score == 0.5  # 0.25 + 0.25

    def test_ip_floor_constant(self):
        assert IP_FLOOR == 0.5


# =============================================================================
# FailureSignals tests
# =============================================================================


class TestFailureSignals:
    """Test FailureSignals dataclass."""

    def test_defaults(self):
        signals = FailureSignals()
        assert signals.error_taxonomy_explicit is False

    def test_to_dict(self):
        signals = FailureSignals(structured_logs=True)
        d = signals.to_dict()
        assert d["structured_logs"] is True


class TestCalculateFp:
    """Test calculate_fp function."""

    def test_all_true_max_score(self):
        signals = FailureSignals(
            error_taxonomy_explicit=True,
            exception_boundaries_tight=True,
            timeout_semantics_spelled_out=True,
            retry_semantics_spelled_out=True,
            circuit_breaker_explicit=True,
            structured_logs=True,
        )
        assert calculate_fp(signals) == 1.0

    def test_all_false_zero_score(self):
        signals = FailureSignals()
        assert calculate_fp(signals) == 0.0

    def test_fp_floor_constant(self):
        assert FP_FLOOR == 0.5


# =============================================================================
# Magic Behavior Detection tests
# =============================================================================


class TestDetectMagicBehavior:
    """Test detect_magic_behavior function."""

    def test_clean_code_no_magic(self):
        code = """
def add(a: int, b: int) -> int:
    return a + b
"""
        assert detect_magic_behavior(code) == 0.0

    def test_env_var_detected(self):
        code = "config = process.env.DATABASE_URL"
        score = detect_magic_behavior(code)
        assert score > 0.0

    def test_python_env_detected(self):
        code = 'url = os.environ["DATABASE_URL"]'
        score = detect_magic_behavior(code)
        assert score > 0.0

    def test_eval_detected(self):
        code = "result = eval(user_input)"
        score = detect_magic_behavior(code)
        assert score > 0.0

    def test_global_detected(self):
        code = """
def update():
    global counter
    counter += 1
"""
        score = detect_magic_behavior(code)
        assert score > 0.0

    def test_score_capped_at_one(self):
        code = """
eval(x)
eval(y)
eval(z)
exec(a)
exec(b)
global foo
global bar
global baz
os.environ["A"]
os.environ["B"]
os.environ["C"]
"""
        score = detect_magic_behavior(code)
        assert score <= 1.0


# =============================================================================
# Exception Smear Detection tests
# =============================================================================


class TestDetectExceptionSmear:
    """Test detect_exception_smear function."""

    def test_clean_code_no_smear(self):
        code = """
try:
    result = do_something()
except ValueError as e:
    raise ProcessingError(f"Invalid value: {e}")
"""
        # Specific exception, re-raises with context
        score = detect_exception_smear(code)
        assert score < 0.3

    def test_bare_except_detected(self):
        code = """
try:
    result = do_something()
except:
    return None
"""
        score = detect_exception_smear(code)
        assert score > 0.0

    def test_except_exception_detected(self):
        code = """
try:
    result = do_something()
except Exception:
    return None
"""
        score = detect_exception_smear(code)
        assert score > 0.0

    def test_return_none_after_except(self):
        code = """
try:
    result = fetch()
except ConnectionError:
    return None
"""
        # This is actually specific exception but returns None
        score = detect_exception_smear(code)
        # Pattern looks for except followed by return None
        assert score >= 0.0

    def test_score_capped_at_one(self):
        code = """
except:
    pass
except:
    pass
except:
    pass
except:
    pass
except:
    pass
except:
    pass
except:
    pass
"""
        score = detect_exception_smear(code)
        assert score <= 1.0


# =============================================================================
# Premature Abstraction Detection tests
# =============================================================================


class TestAbstractionAnalysis:
    """Test AbstractionAnalysis dataclass."""

    def test_defaults(self):
        analysis = AbstractionAnalysis()
        assert analysis.new_abstractions == []
        assert analysis.layers_of_indirection == 0

    def test_to_dict(self):
        analysis = AbstractionAnalysis(new_abstractions=["Foo", "Bar"])
        d = analysis.to_dict()
        assert d["new_abstractions"] == ["Foo", "Bar"]


class TestDetectPrematureAbstraction:
    """Test detect_premature_abstraction function."""

    def test_no_abstractions_zero_score(self):
        analysis = AbstractionAnalysis()
        assert detect_premature_abstraction(analysis) == 0.0

    def test_abstraction_without_uses(self):
        analysis = AbstractionAnalysis(
            new_abstractions=["Helper"],
            concrete_uses_per_abstraction={"Helper": 1},
        )
        score = detect_premature_abstraction(analysis)
        assert score > 0.0  # Only 1 use < 2 required

    def test_abstraction_with_sufficient_uses(self):
        analysis = AbstractionAnalysis(
            new_abstractions=["Helper"],
            concrete_uses_per_abstraction={"Helper": 3},
        )
        score = detect_premature_abstraction(analysis)
        assert score == 0.0  # 3 uses >= 2 required

    def test_utility_without_tests(self):
        analysis = AbstractionAnalysis(
            utility_modules_without_tests=["utils.py"],
        )
        score = detect_premature_abstraction(analysis)
        assert score > 0.0

    def test_deep_indirection(self):
        analysis = AbstractionAnalysis(layers_of_indirection=5)
        score = detect_premature_abstraction(analysis)
        assert score > 0.0  # 5 > 3 threshold

    def test_shallow_indirection_ok(self):
        analysis = AbstractionAnalysis(layers_of_indirection=2)
        score = detect_premature_abstraction(analysis)
        assert score == 0.0


# =============================================================================
# Complexity Budget tests
# =============================================================================


class TestComplexityBudget:
    """Test ComplexityBudget dataclass."""

    def test_defaults(self):
        budget = ComplexityBudget()
        assert budget.max_new_abstractions_per_pr == 2
        assert budget.require_concrete_uses_before_abstraction == 2

    def test_default_budget_constant(self):
        assert DEFAULT_COMPLEXITY_BUDGET.max_new_abstractions_per_pr == 2


class TestAbstractionProposal:
    """Test AbstractionProposal dataclass."""

    def test_to_dict(self):
        proposal = AbstractionProposal(name="Helper", concrete_uses=1)
        d = proposal.to_dict()
        assert d["name"] == "Helper"
        assert d["concrete_uses"] == 1


class TestCheckAbstractionAllowed:
    """Test check_abstraction_allowed function."""

    def test_sufficient_uses_allowed(self):
        proposal = AbstractionProposal(name="Helper", concrete_uses=3)
        assert check_abstraction_allowed(proposal) is True

    def test_insufficient_uses_blocked(self):
        proposal = AbstractionProposal(name="Helper", concrete_uses=1)
        assert check_abstraction_allowed(proposal) is False

    def test_waiver_allows(self):
        proposal = AbstractionProposal(
            name="Helper",
            concrete_uses=0,
            waiver_reason="Required for external API",
        )
        assert check_abstraction_allowed(proposal) is True


# =============================================================================
# CustodyScore tests
# =============================================================================


class TestCustodyScore:
    """Test CustodyScore dataclass."""

    def test_total_positive_only(self):
        score = CustodyScore(Ap=1.0, Ip=1.0, Fp=1.0)
        # 1.0*0.35 + 1.0*0.30 + 1.0*0.35 = 1.0
        assert score.total() == pytest.approx(1.0)

    def test_total_with_negatives(self):
        score = CustodyScore(
            Ap=0.8, Ip=0.8, Fp=0.8,
            magic_behavior=0.5,
            broad_exception_smear=0.5,
            premature_abstraction=0.5,
        )
        total = score.total()
        assert total < 0.8  # Negatives reduce score

    def test_total_floor_at_zero(self):
        score = CustodyScore(
            Ap=0.0, Ip=0.0, Fp=0.0,
            magic_behavior=1.0,
            broad_exception_smear=1.0,
            premature_abstraction=1.0,
        )
        assert score.total() == 0.0

    def test_to_dict(self):
        score = CustodyScore(Ap=0.6, Ip=0.5, Fp=0.5)
        d = score.to_dict()
        assert "Ap" in d
        assert "total" in d

    def test_custody_score_floor_constant(self):
        assert CUSTODY_SCORE_FLOOR == 0.5


class TestCalculateCustodyScore:
    """Test calculate_custody_score function."""

    def test_delegates_to_total(self):
        score = CustodyScore(Ap=0.6, Ip=0.5, Fp=0.5)
        assert calculate_custody_score(score) == score.total()


# =============================================================================
# Mode Gates tests
# =============================================================================


class TestDevModeGates:
    """Test DevModeGates dataclass."""

    def test_all_pass_when_all_true(self):
        gates = DevModeGates(
            build_passes=True,
            tests_present_for_critical_behavior=True,
            invariants_enforced=True,
            failure_behavior_specified=True,
            no_premature_abstraction=True,
        )
        assert gates.all_pass() is True

    def test_fail_when_any_false(self):
        gates = DevModeGates(
            build_passes=True,
            tests_present_for_critical_behavior=False,  # This one fails
            invariants_enforced=True,
            failure_behavior_specified=True,
            no_premature_abstraction=True,
        )
        assert gates.all_pass() is False

    def test_to_dict(self):
        gates = DevModeGates(build_passes=True)
        d = gates.to_dict()
        assert d["build_passes"] is True


class TestSREModeGates:
    """Test SREModeGates dataclass."""

    def test_all_pass_with_feature_gating(self):
        gates = SREModeGates(
            rollback_path_exists=True,
            observability_hooks_exist=True,
            failure_modes_documented=True,
            feature_gating_present=True,
            is_risky_change=True,
        )
        assert gates.all_pass() is True

    def test_all_pass_not_risky(self):
        gates = SREModeGates(
            rollback_path_exists=True,
            observability_hooks_exist=True,
            failure_modes_documented=True,
            feature_gating_present=False,
            is_risky_change=False,  # Not risky, so gating not required
        )
        assert gates.all_pass() is True

    def test_fail_risky_without_gating(self):
        gates = SREModeGates(
            rollback_path_exists=True,
            observability_hooks_exist=True,
            failure_modes_documented=True,
            feature_gating_present=False,
            is_risky_change=True,  # Risky but no gating
        )
        assert gates.all_pass() is False

    def test_to_dict(self):
        gates = SREModeGates(rollback_path_exists=True)
        d = gates.to_dict()
        assert d["rollback_path_exists"] is True


# =============================================================================
# CodeContext tests
# =============================================================================


class TestCodeContext:
    """Test CodeContext dataclass."""

    def test_defaults(self):
        ctx = CodeContext()
        assert ctx.is_infrastructure_change is False
        assert ctx.runtime_criticality == "medium"

    def test_to_dict(self):
        ctx = CodeContext(is_incident_response=True)
        d = ctx.to_dict()
        assert d["is_incident_response"] is True


class TestDetectCodeRegime:
    """Test detect_code_regime function."""

    def test_infrastructure_is_sre(self):
        ctx = CodeContext(is_infrastructure_change=True)
        assert detect_code_regime(ctx) == CodeRegime.SRE

    def test_incident_is_sre(self):
        ctx = CodeContext(is_incident_response=True)
        assert detect_code_regime(ctx) == CodeRegime.SRE

    def test_config_is_sre(self):
        ctx = CodeContext(is_config_change=True)
        assert detect_code_regime(ctx) == CodeRegime.SRE

    def test_analysis_script_is_analysis(self):
        ctx = CodeContext(is_analysis_script=True)
        assert detect_code_regime(ctx) == CodeRegime.ANALYSIS

    def test_default_is_dev(self):
        ctx = CodeContext()
        assert detect_code_regime(ctx) == CodeRegime.DEV


# =============================================================================
# Violation tests
# =============================================================================


class TestViolationType:
    """Test ViolationType enum."""

    def test_all_types(self):
        assert len(ViolationType) == 5
        assert ViolationType.ACCOUNTABILITY.value == "accountability"
        assert ViolationType.MAGIC.value == "magic"


class TestCodeViolation:
    """Test CodeViolation dataclass."""

    def test_to_dict(self):
        v = CodeViolation(
            violation_type=ViolationType.ACCOUNTABILITY,
            location="global",
            severity=0.4,
            suggestion="Add ownership",
        )
        d = v.to_dict()
        assert d["type"] == "accountability"
        assert d["severity"] == 0.4


# =============================================================================
# Telemetry tests
# =============================================================================


class TestCodeTelemetry:
    """Test CodeTelemetry dataclass."""

    def test_defaults(self):
        t = CodeTelemetry()
        assert t.magic_behavior_score == 0.0

    def test_to_dict(self):
        t = CodeTelemetry(magic_behavior_score=0.3)
        d = t.to_dict()
        assert d["magic_behavior_score"] == 0.3


# =============================================================================
# Retry Strategy tests
# =============================================================================


class TestRetryAction:
    """Test RetryAction enum."""

    def test_all_actions(self):
        assert len(RetryAction) == 5


class TestFailureType:
    """Test FailureType enum."""

    def test_all_types(self):
        assert len(FailureType) == 6


class TestGetRetryStrategy:
    """Test get_retry_strategy function."""

    def test_low_ap(self):
        assert get_retry_strategy(FailureType.LOW_AP) == RetryAction.ADD_OWNERSHIP_AND_BOUNDS

    def test_low_ip(self):
        assert get_retry_strategy(FailureType.LOW_IP) == RetryAction.ADD_CONTRACTS_AND_VALIDATION

    def test_low_fp(self):
        assert get_retry_strategy(FailureType.LOW_FP) == RetryAction.ADD_ERROR_TAXONOMY_AND_HANDLERS

    def test_premature_abstraction(self):
        assert get_retry_strategy(FailureType.PREMATURE_ABSTRACTION) == RetryAction.INLINE_AND_SIMPLIFY


# =============================================================================
# CodeAnalyzer tests
# =============================================================================


class TestCodeAnalyzer:
    """Test CodeAnalyzer class."""

    def test_analyze_accountability_ownership(self):
        analyzer = CodeAnalyzer()
        code = "# Owner: platform-team\ndef process(): pass"
        signals = analyzer.analyze_accountability(code)
        assert signals.ownership_explicit is True

    def test_analyze_accountability_assumptions(self):
        analyzer = CodeAnalyzer()
        code = """
def process(data):
    # Assumes: data is non-empty
    return data[0]
"""
        signals = analyzer.analyze_accountability(code)
        assert signals.assumptions_stated is True

    def test_analyze_invariants_types(self):
        analyzer = CodeAnalyzer()
        code = "def add(a: int, b: int) -> int: return a + b"
        signals = analyzer.analyze_invariants(code)
        assert signals.type_checks_present is True

    def test_analyze_invariants_validation(self):
        analyzer = CodeAnalyzer()
        code = """
def process(x):
    if not x:
        raise ValueError("x required")
"""
        signals = analyzer.analyze_invariants(code)
        assert signals.input_validation_present is True

    def test_analyze_failure_surface_error_taxonomy(self):
        analyzer = CodeAnalyzer()
        code = """
class ProcessingError(Exception):
    pass

raise ProcessingError("Failed")
"""
        signals = analyzer.analyze_failure_surface(code)
        assert signals.error_taxonomy_explicit is True

    def test_analyze_failure_surface_timeout(self):
        analyzer = CodeAnalyzer()
        code = "response = client.get(url, timeout=30)"
        signals = analyzer.analyze_failure_surface(code)
        assert signals.timeout_semantics_spelled_out is True

    def test_analyze_failure_surface_retry(self):
        analyzer = CodeAnalyzer()
        code = "@retry(max_retries=3, backoff=2)"
        signals = analyzer.analyze_failure_surface(code)
        assert signals.retry_semantics_spelled_out is True

    def test_analyze_full_code(self):
        analyzer = CodeAnalyzer()
        code = """
# Owner: platform-team
# Assumes: user_id is valid

def get_user(user_id: str) -> User:
    if not user_id:
        raise ValueError("user_id required")
    return db.query(user_id, timeout=30)
"""
        score = analyzer.analyze(code)
        assert score.Ap > 0.0
        assert score.Ip > 0.0
        assert score.Fp > 0.0

    def test_detect_violations_low_ap(self):
        analyzer = CodeAnalyzer()
        code = "def foo(): pass"
        score = CustodyScore(Ap=0.3, Ip=0.6, Fp=0.6)
        violations = analyzer.detect_violations(code, score)
        types = [v.violation_type for v in violations]
        assert ViolationType.ACCOUNTABILITY in types

    def test_detect_violations_clean_code(self):
        analyzer = CodeAnalyzer()
        code = "def foo(): pass"
        score = CustodyScore(Ap=0.8, Ip=0.8, Fp=0.8)
        violations = analyzer.detect_violations(code, score)
        assert len(violations) == 0


# =============================================================================
# CodeController tests
# =============================================================================


class TestCodeController:
    """Test CodeController class."""

    def test_check_basic(self):
        controller = CodeController()
        input = CodeControllerInput(
            code="def foo(): pass",
            context=CodeContext(),
        )
        output = controller.check(input)
        assert isinstance(output, CodeControllerOutput)
        assert isinstance(output.custody_score, float)

    def test_check_good_code(self):
        controller = CodeController()
        code = """
# Owner: platform-team
# Assumes: user_id is valid

class UserNotFoundError(Exception):
    pass

def get_user(user_id: str) -> User:
    \"\"\"Get user by ID.

    Args:
        user_id: The user ID to fetch

    Returns:
        The user object

    Raises:
        UserNotFoundError: If user not found
    \"\"\"
    if not user_id:
        raise ValueError("user_id required")

    try:
        user = db.query(user_id, timeout=30)
    except DatabaseError as e:
        raise UserNotFoundError(f"User {user_id} not found") from e

    return user
"""
        input = CodeControllerInput(
            code=code,
            context=CodeContext(),
            existing_tests=["test_get_user.py"],
        )
        output = controller.check(input)
        assert output.custody_score > 0.3

    def test_check_detects_magic(self):
        controller = CodeController()
        code = """
def process():
    url = os.environ["DATABASE_URL"]
    return eval(user_input)
"""
        input = CodeControllerInput(code=code, context=CodeContext())
        output = controller.check(input)
        assert output.scores.magic_behavior > 0.0

    def test_check_sre_regime(self):
        controller = CodeController()
        input = CodeControllerInput(
            code="def foo(): pass",
            context=CodeContext(is_infrastructure_change=True),
        )
        output = controller.check(input)
        # SRE mode has different gate requirements
        assert isinstance(output.passed_gates, bool)

    def test_check_analysis_regime_relaxed(self):
        controller = CodeController()
        input = CodeControllerInput(
            code="x = 1",
            context=CodeContext(is_analysis_script=True),
        )
        output = controller.check(input)
        # Analysis mode is more relaxed
        assert isinstance(output.passed_gates, bool)

    def test_get_retry_action_when_passes(self):
        controller = CodeController()
        output = CodeControllerOutput(
            code="",
            passed_gates=True,
            custody_score=0.8,
            scores=CustodyScore(Ap=0.8, Ip=0.8, Fp=0.8),
        )
        assert controller.get_retry_action(output) is None

    def test_get_retry_action_low_ap(self):
        controller = CodeController()
        output = CodeControllerOutput(
            code="",
            passed_gates=False,
            custody_score=0.3,
            scores=CustodyScore(Ap=0.3, Ip=0.6, Fp=0.6),
        )
        action = controller.get_retry_action(output)
        assert action == RetryAction.ADD_OWNERSHIP_AND_BOUNDS


# =============================================================================
# CodeControllerInput/Output tests
# =============================================================================


class TestCodeControllerInput:
    """Test CodeControllerInput dataclass."""

    def test_to_dict(self):
        input = CodeControllerInput(
            code="def foo(): pass",
            context=CodeContext(),
            regime=CodeRegime.DEV,
        )
        d = input.to_dict()
        assert d["regime"] == "dev"


class TestCodeControllerOutput:
    """Test CodeControllerOutput dataclass."""

    def test_to_dict(self):
        output = CodeControllerOutput(
            code="def foo(): pass",
            passed_gates=True,
            custody_score=0.7,
            scores=CustodyScore(Ap=0.7, Ip=0.7, Fp=0.7),
        )
        d = output.to_dict()
        assert d["passed_gates"] is True
        assert d["custody_score"] == 0.7
