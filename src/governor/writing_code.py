"""
Writing Code — Code/SRE Controller (Custody Regime).

The governance polarity inverts for code:
- In prose, governance must be invisible (reader trusts what escaped supervision)
- In code, governance must be visible and local (maintainer trusts explicit contracts)

Key variables:
- Aₚ (Accountability Clarity): Who owns this? What happens on error?
- Iₚ (Invariant-Implementation Coupling): Are constraints enforced?
- Fₚ (Failure Surface Explicitness): How does this fail?

Core rule: Prose hides governance to preserve trust. Code surfaces governance to preserve custody.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Pattern


# =============================================================================
# Code Regime
# =============================================================================


class CodeRegime(str, Enum):
    """Code/SRE operating regime."""

    DEV = "dev"  # Development: custody controller
    SRE = "sre"  # SRE/Ops: stability controller
    ANALYSIS = "analysis"  # Analysis scripts: relaxed constraints


# =============================================================================
# Accountability Clarity (Aₚ)
# =============================================================================


@dataclass
class AccountabilitySignals:
    """Signals for Aₚ (Accountability Clarity).

    Can an operator safely take responsibility for this output?
    """

    ownership_explicit: bool = False  # team/service annotations present
    assumptions_stated: bool = False  # preconditions documented near code
    error_handling_local: bool = False  # failures handled where they occur
    side_effects_bounded: bool = False  # mutations are explicit and contained
    config_defaults_visible: bool = False  # no magic values

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownership_explicit": self.ownership_explicit,
            "assumptions_stated": self.assumptions_stated,
            "error_handling_local": self.error_handling_local,
            "side_effects_bounded": self.side_effects_bounded,
            "config_defaults_visible": self.config_defaults_visible,
        }


def calculate_ap(signals: AccountabilitySignals) -> float:
    """Calculate Aₚ (Accountability Clarity) score.

    Args:
        signals: Accountability signals detected in code

    Returns:
        Score in [0, 1]
    """
    score = 0.0
    if signals.ownership_explicit:
        score += 0.2
    if signals.assumptions_stated:
        score += 0.2
    if signals.error_handling_local:
        score += 0.25
    if signals.side_effects_bounded:
        score += 0.2
    if signals.config_defaults_visible:
        score += 0.15
    return score


AP_FLOOR = 0.6


# =============================================================================
# Invariant-Implementation Coupling (Iₚ)
# =============================================================================


@dataclass
class InvariantSignals:
    """Signals for Iₚ (Invariant-Implementation Coupling).

    How strongly invariants are tied to enforcement mechanisms.
    """

    type_checks_present: bool = False  # static analysis catches violations
    input_validation_present: bool = False  # contracts at boundaries
    assertions_in_critical_paths: bool = False
    property_tests_present: bool = False  # where feasible
    preconditions_documented: bool = False  # explicit pre/postconditions

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_checks_present": self.type_checks_present,
            "input_validation_present": self.input_validation_present,
            "assertions_in_critical_paths": self.assertions_in_critical_paths,
            "property_tests_present": self.property_tests_present,
            "preconditions_documented": self.preconditions_documented,
        }


def calculate_ip(signals: InvariantSignals) -> float:
    """Calculate Iₚ (Invariant-Implementation Coupling) score.

    An invariant that isn't enforced is narrative.
    Narrative is for postmortems, not production.

    Args:
        signals: Invariant signals detected in code

    Returns:
        Score in [0, 1]
    """
    score = 0.0
    if signals.type_checks_present:
        score += 0.25
    if signals.input_validation_present:
        score += 0.25
    if signals.assertions_in_critical_paths:
        score += 0.2
    if signals.property_tests_present:
        score += 0.15
    if signals.preconditions_documented:
        score += 0.15
    return score


IP_FLOOR = 0.5


# =============================================================================
# Failure Surface Explicitness (Fₚ)
# =============================================================================


@dataclass
class FailureSignals:
    """Signals for Fₚ (Failure Surface Explicitness).

    How legible failure behavior is to a responder.
    Prefer loud, local failure over quiet, smeared failure.
    """

    error_taxonomy_explicit: bool = False  # programmer vs runtime vs dependency
    exception_boundaries_tight: bool = False  # no catch-all without context
    timeout_semantics_spelled_out: bool = False
    retry_semantics_spelled_out: bool = False
    circuit_breaker_explicit: bool = False
    structured_logs: bool = False  # stable keys, not prose

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_taxonomy_explicit": self.error_taxonomy_explicit,
            "exception_boundaries_tight": self.exception_boundaries_tight,
            "timeout_semantics_spelled_out": self.timeout_semantics_spelled_out,
            "retry_semantics_spelled_out": self.retry_semantics_spelled_out,
            "circuit_breaker_explicit": self.circuit_breaker_explicit,
            "structured_logs": self.structured_logs,
        }


def calculate_fp(signals: FailureSignals) -> float:
    """Calculate Fₚ (Failure Surface Explicitness) score.

    Args:
        signals: Failure signals detected in code

    Returns:
        Score in [0, 1]
    """
    score = 0.0
    if signals.error_taxonomy_explicit:
        score += 0.2
    if signals.exception_boundaries_tight:
        score += 0.2
    if signals.timeout_semantics_spelled_out:
        score += 0.15
    if signals.retry_semantics_spelled_out:
        score += 0.15
    if signals.circuit_breaker_explicit:
        score += 0.15
    if signals.structured_logs:
        score += 0.15
    return score


FP_FLOOR = 0.5


# =============================================================================
# Magic Behavior Detection
# =============================================================================

# Patterns that indicate implicit/magic behavior
MAGIC_PATTERNS: list[Pattern[str]] = [
    re.compile(r"process\.env\.\w+"),  # env var without default
    re.compile(r"os\.environ\["),  # Python env access
    re.compile(r"os\.getenv\([^,)]+\)(?!\s*or)"),  # getenv without default
    re.compile(r"config\[['\"]\w+['\"]\]"),  # config access without validation
    re.compile(r"\bglobal\s+\w+"),  # Python global statement
    re.compile(r"\beval\s*\("),  # dynamic code execution
    re.compile(r"\bexec\s*\("),  # dynamic code execution
    re.compile(r"Function\s*\("),  # JS dynamic function
    re.compile(r"__proto__"),  # prototype manipulation
    re.compile(r"setattr\s*\("),  # dynamic attribute setting
    re.compile(r"getattr\s*\([^,]+\)(?!\s*,)"),  # getattr without default
]


def detect_magic_behavior(code: str) -> float:
    """Detect magic/implicit behavior in code.

    Magic behavior includes:
    - Environment variables without defaults
    - Config access without validation
    - Global state
    - Dynamic code execution
    - Prototype manipulation

    Args:
        code: The code to analyze

    Returns:
        Score in [0, 1] where higher = more magic behavior
    """
    score = 0.0
    for pattern in MAGIC_PATTERNS:
        matches = pattern.findall(code)
        score += len(matches) * 0.1
    return min(1.0, score)


# =============================================================================
# Exception Smear Detection
# =============================================================================

# Patterns that indicate exception smearing (catch-all-and-log)
EXCEPTION_SMEAR_PATTERNS: list[Pattern[str]] = [
    # catch Exception and log
    re.compile(r"except\s+Exception\s*:", re.IGNORECASE),
    re.compile(r"except\s*:", re.IGNORECASE),  # bare except
    re.compile(r"catch\s*\(\s*(Exception|Error|e|\w+)\s*\)\s*\{[^}]*log", re.IGNORECASE),
    # catch-all in JS
    re.compile(r"\.catch\s*\(\s*\(\s*\)\s*=>"),  # empty catch
    re.compile(r"\.catch\s*\(\s*_\s*=>"),  # catch and ignore
    # return null/None after exception
    re.compile(r"except[^:]*:\s*\n\s*return\s+None", re.IGNORECASE),
    re.compile(r"catch[^{]*\{[^}]*return\s+(null|undefined)", re.IGNORECASE),
    # pass in except
    re.compile(r"except[^:]*:\s*\n\s*pass\b"),
]


def detect_exception_smear(code: str) -> float:
    """Detect exception smearing in code.

    Exception smearing is when code catches broadly and:
    - Logs and continues
    - Returns null/None
    - Swallows the error

    This is the code equivalent of committee prose.

    Args:
        code: The code to analyze

    Returns:
        Score in [0, 1] where higher = more exception smearing
    """
    score = 0.0
    for pattern in EXCEPTION_SMEAR_PATTERNS:
        matches = pattern.findall(code)
        score += len(matches) * 0.15
    return min(1.0, score)


# =============================================================================
# Premature Abstraction Detection
# =============================================================================


@dataclass
class AbstractionAnalysis:
    """Analysis of abstractions in code."""

    new_abstractions: list[str] = field(default_factory=list)
    concrete_uses_per_abstraction: dict[str, int] = field(default_factory=dict)
    utility_modules_without_tests: list[str] = field(default_factory=list)
    layers_of_indirection: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_abstractions": self.new_abstractions,
            "concrete_uses_per_abstraction": self.concrete_uses_per_abstraction,
            "utility_modules_without_tests": self.utility_modules_without_tests,
            "layers_of_indirection": self.layers_of_indirection,
        }


def detect_premature_abstraction(analysis: AbstractionAnalysis) -> float:
    """Detect premature abstraction in code.

    Premature abstraction is the code equivalent of premature closure in prose.
    It includes:
    - Abstract helpers before concrete use
    - Parameterization without demonstrated need
    - Clever reuse that hides invariants

    Rule: If the maintainer hasn't felt the pain yet, don't "solve" it.

    Args:
        analysis: Analysis of abstractions in the code

    Returns:
        Score in [0, 1] where higher = more premature abstraction
    """
    score = 0.0

    # Abstractions without concrete uses
    for abstraction, uses in analysis.concrete_uses_per_abstraction.items():
        if uses < 2:
            score += 0.2

    # Utility modules without tests
    score += len(analysis.utility_modules_without_tests) * 0.15

    # Deep indirection
    if analysis.layers_of_indirection > 3:
        score += (analysis.layers_of_indirection - 3) * 0.1

    return min(1.0, score)


# =============================================================================
# Complexity Budget
# =============================================================================


@dataclass
class ComplexityBudget:
    """Complexity budget configuration.

    Controls the rate at which complexity can be added.
    """

    max_new_abstractions_per_pr: int = 2
    max_cognitive_complexity_delta: int = 10
    require_concrete_uses_before_abstraction: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_new_abstractions_per_pr": self.max_new_abstractions_per_pr,
            "max_cognitive_complexity_delta": self.max_cognitive_complexity_delta,
            "require_concrete_uses_before_abstraction": self.require_concrete_uses_before_abstraction,
        }


DEFAULT_COMPLEXITY_BUDGET = ComplexityBudget()


@dataclass
class AbstractionProposal:
    """A proposal to add a new abstraction."""

    name: str
    concrete_uses: int
    waiver_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "concrete_uses": self.concrete_uses,
            "waiver_reason": self.waiver_reason,
        }


def check_abstraction_allowed(
    proposal: AbstractionProposal,
    budget: ComplexityBudget = DEFAULT_COMPLEXITY_BUDGET,
) -> bool:
    """Check if a new abstraction is allowed.

    Args:
        proposal: The abstraction proposal
        budget: The complexity budget

    Returns:
        True if allowed, False otherwise
    """
    if proposal.concrete_uses >= budget.require_concrete_uses_before_abstraction:
        return True
    if proposal.waiver_reason:
        return True  # explicit waiver granted
    return False


# =============================================================================
# Custody Score
# =============================================================================


@dataclass
class CustodyScore:
    """Aggregate custody score for code.

    The load-bearing variable for code is:
    "Can I safely take custody of this?"
    """

    Ap: float  # accountability clarity
    Ip: float  # invariant-implementation coupling
    Fp: float  # failure surface explicitness

    # Negative factors
    magic_behavior: float = 0.0
    broad_exception_smear: float = 0.0
    premature_abstraction: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "Ap": self.Ap,
            "Ip": self.Ip,
            "Fp": self.Fp,
            "magic_behavior": self.magic_behavior,
            "broad_exception_smear": self.broad_exception_smear,
            "premature_abstraction": self.premature_abstraction,
            "total": self.total(),
        }

    def total(self) -> float:
        """Calculate total custody score."""
        positive = self.Ap * 0.35 + self.Ip * 0.30 + self.Fp * 0.35

        negative = (
            self.magic_behavior * 0.15
            + self.broad_exception_smear * 0.20
            + self.premature_abstraction * 0.15
        )

        return max(0.0, positive - negative)


CUSTODY_SCORE_FLOOR = 0.5


def calculate_custody_score(score: CustodyScore) -> float:
    """Calculate total custody score.

    Args:
        score: The custody score components

    Returns:
        Total score in [0, 1]
    """
    return score.total()


# =============================================================================
# Mode Gates
# =============================================================================


@dataclass
class DevModeGates:
    """Gates for development mode.

    Objective: Produce code that is adoptable + debuggable.
    """

    build_passes: bool = False
    tests_present_for_critical_behavior: bool = False
    invariants_enforced: bool = False  # Iₚ above threshold
    failure_behavior_specified: bool = False  # Fₚ above threshold
    no_premature_abstraction: bool = False  # dC/dt below cap

    def to_dict(self) -> dict[str, Any]:
        return {
            "build_passes": self.build_passes,
            "tests_present_for_critical_behavior": self.tests_present_for_critical_behavior,
            "invariants_enforced": self.invariants_enforced,
            "failure_behavior_specified": self.failure_behavior_specified,
            "no_premature_abstraction": self.no_premature_abstraction,
        }

    def all_pass(self) -> bool:
        """Check if all gates pass."""
        return (
            self.build_passes
            and self.tests_present_for_critical_behavior
            and self.invariants_enforced
            and self.failure_behavior_specified
            and self.no_premature_abstraction
        )


@dataclass
class SREModeGates:
    """Gates for SRE mode.

    Objective: Minimize change risk and maximize recoverability.
    """

    rollback_path_exists: bool = False
    rollback_path_tested: bool = False
    observability_hooks_exist: bool = False  # SLIs/log keys
    failure_modes_documented: bool = False
    feature_gating_present: bool = False  # flag/canary for risky changes
    is_risky_change: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_path_exists": self.rollback_path_exists,
            "rollback_path_tested": self.rollback_path_tested,
            "observability_hooks_exist": self.observability_hooks_exist,
            "failure_modes_documented": self.failure_modes_documented,
            "feature_gating_present": self.feature_gating_present,
            "is_risky_change": self.is_risky_change,
        }

    def all_pass(self) -> bool:
        """Check if all gates pass."""
        return (
            self.rollback_path_exists
            and self.observability_hooks_exist
            and self.failure_modes_documented
            and (self.feature_gating_present or not self.is_risky_change)
        )


# =============================================================================
# Code Context and I/O
# =============================================================================


@dataclass
class CodeContext:
    """Context for code analysis."""

    is_infrastructure_change: bool = False
    is_incident_response: bool = False
    is_config_change: bool = False
    is_analysis_script: bool = False
    touched_files: list[str] = field(default_factory=list)
    runtime_criticality: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_infrastructure_change": self.is_infrastructure_change,
            "is_incident_response": self.is_incident_response,
            "is_config_change": self.is_config_change,
            "is_analysis_script": self.is_analysis_script,
            "touched_files": self.touched_files,
            "runtime_criticality": self.runtime_criticality,
        }


def detect_code_regime(context: CodeContext) -> CodeRegime:
    """Detect the code regime from context.

    Args:
        context: The code context

    Returns:
        The detected code regime
    """
    if context.is_infrastructure_change:
        return CodeRegime.SRE
    if context.is_incident_response:
        return CodeRegime.SRE
    if context.is_config_change:
        return CodeRegime.SRE
    if context.is_analysis_script:
        return CodeRegime.ANALYSIS
    return CodeRegime.DEV


class ViolationType(str, Enum):
    """Types of code violations."""

    ACCOUNTABILITY = "accountability"
    INVARIANT = "invariant"
    FAILURE = "failure"
    ABSTRACTION = "abstraction"
    MAGIC = "magic"


@dataclass
class CodeViolation:
    """A code violation."""

    violation_type: ViolationType
    location: str
    severity: float
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.violation_type.value,
            "location": self.location,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


@dataclass
class CodeTelemetry:
    """Telemetry for code analysis."""

    invariants_added_vs_enforced: float = 0.0
    exception_boundary_width: float = 0.0
    diff_complexity: float = 0.0
    new_concept_count: int = 0
    magic_behavior_score: float = 0.0
    exception_smear_score: float = 0.0
    premature_abstraction_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariants_added_vs_enforced": self.invariants_added_vs_enforced,
            "exception_boundary_width": self.exception_boundary_width,
            "diff_complexity": self.diff_complexity,
            "new_concept_count": self.new_concept_count,
            "magic_behavior_score": self.magic_behavior_score,
            "exception_smear_score": self.exception_smear_score,
            "premature_abstraction_score": self.premature_abstraction_score,
        }


@dataclass
class CodeControllerInput:
    """Input to the code controller."""

    code: str
    context: CodeContext
    regime: CodeRegime | None = None
    repo_conventions: dict[str, Any] | None = None
    existing_tests: list[str] | None = None
    existing_invariants: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "context": self.context.to_dict(),
            "regime": self.regime.value if self.regime else None,
            "repo_conventions": self.repo_conventions,
            "existing_tests": self.existing_tests,
            "existing_invariants": self.existing_invariants,
        }


@dataclass
class CodeControllerOutput:
    """Output from the code controller."""

    code: str  # potentially augmented
    passed_gates: bool
    custody_score: float

    scores: CustodyScore
    violations: list[CodeViolation] = field(default_factory=list)
    augmentations_applied: list[str] = field(default_factory=list)
    telemetry: CodeTelemetry = field(default_factory=CodeTelemetry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "passed_gates": self.passed_gates,
            "custody_score": self.custody_score,
            "scores": self.scores.to_dict(),
            "violations": [v.to_dict() for v in self.violations],
            "augmentations_applied": self.augmentations_applied,
            "telemetry": self.telemetry.to_dict(),
        }


# =============================================================================
# Retry Strategy
# =============================================================================


class RetryAction(str, Enum):
    """Retry actions for code domain."""

    ADD_OWNERSHIP_AND_BOUNDS = "add_ownership_and_bounds"
    ADD_CONTRACTS_AND_VALIDATION = "add_contracts_and_validation"
    ADD_ERROR_TAXONOMY_AND_HANDLERS = "add_error_taxonomy_and_handlers"
    INLINE_AND_SIMPLIFY = "inline_and_simplify"
    ADD_TESTS = "add_tests"


class FailureType(str, Enum):
    """Types of custody failures."""

    LOW_AP = "low_Ap"
    LOW_IP = "low_Ip"
    LOW_FP = "low_Fp"
    PREMATURE_ABSTRACTION = "premature_abstraction"
    HIGH_MAGIC = "high_magic"
    HIGH_SMEAR = "high_smear"


def get_retry_strategy(failure: FailureType) -> RetryAction:
    """Get retry strategy for a failure type.

    In code, the retry loop should be structural augmentation, not rephrasing.

    Args:
        failure: The type of failure

    Returns:
        The retry action to take
    """
    strategies = {
        FailureType.LOW_AP: RetryAction.ADD_OWNERSHIP_AND_BOUNDS,
        FailureType.LOW_IP: RetryAction.ADD_CONTRACTS_AND_VALIDATION,
        FailureType.LOW_FP: RetryAction.ADD_ERROR_TAXONOMY_AND_HANDLERS,
        FailureType.PREMATURE_ABSTRACTION: RetryAction.INLINE_AND_SIMPLIFY,
        FailureType.HIGH_MAGIC: RetryAction.ADD_OWNERSHIP_AND_BOUNDS,
        FailureType.HIGH_SMEAR: RetryAction.ADD_ERROR_TAXONOMY_AND_HANDLERS,
    }
    return strategies.get(failure, RetryAction.ADD_TESTS)


# =============================================================================
# Code Analyzer
# =============================================================================


class CodeAnalyzer:
    """Analyzer for code custody scoring.

    Analyzes code to produce custody scores and detect violations.
    """

    def __init__(self) -> None:
        self._ownership_patterns = [
            re.compile(r"@owner\s*[:=]", re.IGNORECASE),
            re.compile(r"# ?Owner:", re.IGNORECASE),
            re.compile(r"// ?Owner:", re.IGNORECASE),
            re.compile(r"@team\s*[:=]", re.IGNORECASE),
        ]
        self._assumption_patterns = [
            re.compile(r"# ?Assumes?:", re.IGNORECASE),
            re.compile(r"// ?Assumes?:", re.IGNORECASE),
            re.compile(r"# ?Precondition:", re.IGNORECASE),
            re.compile(r"# ?Requires?:", re.IGNORECASE),
            re.compile(r":param\s+\w+:", re.IGNORECASE),
            re.compile(r"Args?:\s*\n", re.IGNORECASE),
        ]
        self._type_annotation_patterns = [
            re.compile(r":\s*(str|int|float|bool|list|dict|tuple|set)\b"),
            re.compile(r"->\s*\w+"),
            re.compile(r":\s*\w+\["),  # Generic types
            re.compile(r"@dataclass"),
            re.compile(r"class\s+\w+\(.*Protocol.*\)"),
        ]
        self._validation_patterns = [
            re.compile(r"if\s+not\s+\w+\s*:"),
            re.compile(r"raise\s+ValueError"),
            re.compile(r"raise\s+TypeError"),
            re.compile(r"assert\s+"),
            re.compile(r"\.validate\("),
        ]
        self._assertion_patterns = [
            re.compile(r"\bassert\s+"),
            re.compile(r"\.assertEqual"),
            re.compile(r"\.assertTrue"),
            re.compile(r"expect\("),
        ]
        self._error_taxonomy_patterns = [
            re.compile(r"class\s+\w+Error\s*\("),
            re.compile(r"class\s+\w+Exception\s*\("),
            re.compile(r"raise\s+\w+Error\("),
            re.compile(r"raise\s+\w+Exception\("),
        ]
        self._timeout_patterns = [
            re.compile(r"timeout\s*[=:]"),
            re.compile(r"Timeout\s*\("),
            re.compile(r"\.timeout\s*="),
        ]
        self._retry_patterns = [
            re.compile(r"@retry"),
            re.compile(r"\.retry\("),
            re.compile(r"max_retries"),
            re.compile(r"backoff"),
        ]
        self._circuit_breaker_patterns = [
            re.compile(r"circuit.?breaker", re.IGNORECASE),
            re.compile(r"@circuit"),
            re.compile(r"CircuitBreaker"),
        ]
        self._structured_log_patterns = [
            re.compile(r"logger\.\w+\([^)]*,\s*extra\s*="),
            re.compile(r"structlog"),
            re.compile(r"log\.WithField"),
            re.compile(r'logging\..*\{["\']'),  # Format strings with keys
        ]

    def analyze_accountability(self, code: str) -> AccountabilitySignals:
        """Analyze code for accountability signals.

        Args:
            code: The code to analyze

        Returns:
            AccountabilitySignals detected
        """
        return AccountabilitySignals(
            ownership_explicit=any(p.search(code) for p in self._ownership_patterns),
            assumptions_stated=any(p.search(code) for p in self._assumption_patterns),
            error_handling_local=self._check_local_error_handling(code),
            side_effects_bounded=self._check_side_effects_bounded(code),
            config_defaults_visible=self._check_config_defaults(code),
        )

    def analyze_invariants(self, code: str) -> InvariantSignals:
        """Analyze code for invariant enforcement signals.

        Args:
            code: The code to analyze

        Returns:
            InvariantSignals detected
        """
        return InvariantSignals(
            type_checks_present=any(p.search(code) for p in self._type_annotation_patterns),
            input_validation_present=any(p.search(code) for p in self._validation_patterns),
            assertions_in_critical_paths=any(p.search(code) for p in self._assertion_patterns),
            property_tests_present=self._check_property_tests(code),
            preconditions_documented=any(p.search(code) for p in self._assumption_patterns),
        )

    def analyze_failure_surface(self, code: str) -> FailureSignals:
        """Analyze code for failure surface explicitness.

        Args:
            code: The code to analyze

        Returns:
            FailureSignals detected
        """
        return FailureSignals(
            error_taxonomy_explicit=any(p.search(code) for p in self._error_taxonomy_patterns),
            exception_boundaries_tight=self._check_exception_boundaries(code),
            timeout_semantics_spelled_out=any(p.search(code) for p in self._timeout_patterns),
            retry_semantics_spelled_out=any(p.search(code) for p in self._retry_patterns),
            circuit_breaker_explicit=any(p.search(code) for p in self._circuit_breaker_patterns),
            structured_logs=any(p.search(code) for p in self._structured_log_patterns),
        )

    def analyze(self, code: str) -> CustodyScore:
        """Analyze code and produce custody score.

        Args:
            code: The code to analyze

        Returns:
            CustodyScore with all components
        """
        accountability = self.analyze_accountability(code)
        invariants = self.analyze_invariants(code)
        failure = self.analyze_failure_surface(code)

        return CustodyScore(
            Ap=calculate_ap(accountability),
            Ip=calculate_ip(invariants),
            Fp=calculate_fp(failure),
            magic_behavior=detect_magic_behavior(code),
            broad_exception_smear=detect_exception_smear(code),
            premature_abstraction=0.0,  # Requires AbstractionAnalysis
        )

    def detect_violations(self, code: str, score: CustodyScore) -> list[CodeViolation]:
        """Detect code violations based on custody score.

        Args:
            code: The code to analyze
            score: The custody score

        Returns:
            List of violations detected
        """
        violations = []

        if score.Ap < AP_FLOOR:
            violations.append(CodeViolation(
                violation_type=ViolationType.ACCOUNTABILITY,
                location="global",
                severity=AP_FLOOR - score.Ap,
                suggestion="Add ownership annotations, document assumptions, make config defaults explicit",
            ))

        if score.Ip < IP_FLOOR:
            violations.append(CodeViolation(
                violation_type=ViolationType.INVARIANT,
                location="global",
                severity=IP_FLOOR - score.Ip,
                suggestion="Add type annotations, input validation, assertions in critical paths",
            ))

        if score.Fp < FP_FLOOR:
            violations.append(CodeViolation(
                violation_type=ViolationType.FAILURE,
                location="global",
                severity=FP_FLOOR - score.Fp,
                suggestion="Add explicit error taxonomy, tighten exception boundaries, add timeout/retry semantics",
            ))

        if score.magic_behavior > 0.3:
            violations.append(CodeViolation(
                violation_type=ViolationType.MAGIC,
                location="global",
                severity=score.magic_behavior,
                suggestion="Make config explicit, remove dynamic code execution, add default values",
            ))

        if score.broad_exception_smear > 0.3:
            violations.append(CodeViolation(
                violation_type=ViolationType.FAILURE,
                location="exception_handlers",
                severity=score.broad_exception_smear,
                suggestion="Tighten exception boundaries, add error taxonomy, avoid catch-all",
            ))

        return violations

    def _check_local_error_handling(self, code: str) -> bool:
        """Check if error handling is local (not smeared)."""
        # If there are try blocks, check they have specific exception types
        try_count = len(re.findall(r"\btry\s*:", code))
        broad_except = len(re.findall(r"except\s*:", code))
        if try_count > 0:
            return broad_except < try_count / 2
        return True

    def _check_side_effects_bounded(self, code: str) -> bool:
        """Check if side effects are bounded."""
        # Simple heuristic: look for explicit mutation patterns
        mutation_patterns = [
            re.compile(r"# ?Mutates:", re.IGNORECASE),
            re.compile(r"# ?Side effects:", re.IGNORECASE),
            re.compile(r"->.*None"),  # Functions returning None often have side effects
        ]
        return any(p.search(code) for p in mutation_patterns)

    def _check_config_defaults(self, code: str) -> bool:
        """Check if config has visible defaults."""
        # Look for patterns like: config.get("key", default)
        default_patterns = [
            re.compile(r"\.get\s*\([^,]+,\s*[^)]+\)"),
            re.compile(r"os\.getenv\s*\([^,]+,\s*[^)]+\)"),
            re.compile(r"or\s+['\"]"),  # "value" or "default"
            re.compile(r"default\s*="),
        ]
        return any(p.search(code) for p in default_patterns)

    def _check_property_tests(self, code: str) -> bool:
        """Check if property tests are present."""
        property_patterns = [
            re.compile(r"@given\("),
            re.compile(r"@hypothesis"),
            re.compile(r"from hypothesis"),
            re.compile(r"@property_test"),
        ]
        return any(p.search(code) for p in property_patterns)

    def _check_exception_boundaries(self, code: str) -> bool:
        """Check if exception boundaries are tight."""
        broad = len(re.findall(r"except\s*:", code)) + len(re.findall(r"except\s+Exception\s*:", code))
        specific = len(re.findall(r"except\s+\w+Error\s*:", code)) + len(re.findall(r"except\s+\w+Exception\s*:", code))
        # Tight if specific exceptions outnumber broad ones
        return specific > broad


# =============================================================================
# Code Controller
# =============================================================================


class CodeController:
    """Controller for code custody regime.

    Applies the custody regime to code generation and SRE contexts.
    """

    def __init__(self) -> None:
        self.analyzer = CodeAnalyzer()

    def check(self, input: CodeControllerInput) -> CodeControllerOutput:
        """Check code against custody regime.

        Args:
            input: The code controller input

        Returns:
            CodeControllerOutput with scores, violations, and telemetry
        """
        # Detect regime if not specified
        regime = input.regime or detect_code_regime(input.context)

        # Analyze code
        score = self.analyzer.analyze(input.code)

        # Detect violations
        violations = self.analyzer.detect_violations(input.code, score)

        # Check gates
        if regime == CodeRegime.DEV:
            gates = DevModeGates(
                build_passes=True,  # Assume true for now
                tests_present_for_critical_behavior=bool(input.existing_tests),
                invariants_enforced=score.Ip >= IP_FLOOR,
                failure_behavior_specified=score.Fp >= FP_FLOOR,
                no_premature_abstraction=score.premature_abstraction < 0.3,
            )
            passed_gates = gates.all_pass()
        elif regime == CodeRegime.SRE:
            gates = SREModeGates(
                rollback_path_exists=True,  # Would need external check
                observability_hooks_exist=score.Fp >= 0.4,
                failure_modes_documented=score.Fp >= FP_FLOOR,
                feature_gating_present=False,
                is_risky_change=input.context.runtime_criticality in ("high", "critical"),
            )
            passed_gates = gates.all_pass()
        else:
            # Analysis mode: relaxed gates
            passed_gates = score.total() >= 0.3

        # Build telemetry
        telemetry = CodeTelemetry(
            magic_behavior_score=score.magic_behavior,
            exception_smear_score=score.broad_exception_smear,
            premature_abstraction_score=score.premature_abstraction,
        )

        return CodeControllerOutput(
            code=input.code,
            passed_gates=passed_gates,
            custody_score=score.total(),
            scores=score,
            violations=violations,
            telemetry=telemetry,
        )

    def get_retry_action(self, output: CodeControllerOutput) -> RetryAction | None:
        """Get retry action for failed custody check.

        Args:
            output: The code controller output

        Returns:
            RetryAction or None if no action needed
        """
        if output.passed_gates:
            return None

        # Determine primary failure
        if output.scores.Ap < AP_FLOOR:
            return get_retry_strategy(FailureType.LOW_AP)
        if output.scores.Ip < IP_FLOOR:
            return get_retry_strategy(FailureType.LOW_IP)
        if output.scores.Fp < FP_FLOOR:
            return get_retry_strategy(FailureType.LOW_FP)
        if output.scores.magic_behavior > 0.3:
            return get_retry_strategy(FailureType.HIGH_MAGIC)
        if output.scores.broad_exception_smear > 0.3:
            return get_retry_strategy(FailureType.HIGH_SMEAR)

        return RetryAction.ADD_TESTS
