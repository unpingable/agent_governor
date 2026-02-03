"""
Writing Constraints — 11 structural constraint categories from writingconstraints.md.

Cross-cutting constraint checks that apply across all writing regimes.
Each constraint category has its own checker with regime-specific behavior.

Key insight from writingconstraints.md: constraints are not style preferences,
they are structural requirements that prevent audience trust collapse.

Section 14 addition: Institutional Resistance to Causal Narration — detects
techniques that prevent causal narratives from forming (not lying, just
preventing facts from linking).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .writing_patterns import (
    BAD_EXIT_PATTERNS,
    INFLATED_WEIGHT_PATTERNS,
    count_pattern_matches,
)


# =============================================================================
# 1. Audience Model
# =============================================================================


class AudienceRelation(str, Enum):
    """How the text positions itself relative to the audience."""

    PEER = "peer"  # Equal footing, shared context
    TEACHER = "teacher"  # Explaining to learners
    EXPERT = "expert"  # Speaking to specialists
    ADVOCATE = "advocate"  # Persuading to action
    COMPANION = "companion"  # Alongside the reader


@dataclass
class AudienceModel:
    """Audience constraint model.

    From writingconstraints.md: The audience model must be internally consistent.
    Failures: condescension (explain what's obvious), exclusion (assume expertise
    that isn't there), presumption (assume agreement that isn't there).
    """

    relation: AudienceRelation
    assumed_expertise: float = 0.5  # 0=novice, 1=expert
    assumed_alignment: float = 0.5  # 0=hostile, 1=aligned
    shared_context: float = 0.5  # 0=none, 1=extensive

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation.value,
            "assumed_expertise": self.assumed_expertise,
            "assumed_alignment": self.assumed_alignment,
            "shared_context": self.shared_context,
        }


@dataclass
class AudienceCheckResult:
    """Result of audience constraint check."""

    condescension_score: float = 0.0  # Over-explaining
    exclusion_score: float = 0.0  # Under-explaining
    presumption_score: float = 0.0  # Assuming agreement
    is_valid: bool = True
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condescension_score": self.condescension_score,
            "exclusion_score": self.exclusion_score,
            "presumption_score": self.presumption_score,
            "is_valid": self.is_valid,
            "violations": self.violations,
        }


# Patterns that suggest condescension
CONDESCENSION_PATTERNS = [
    r"\bas you (probably )?know\b",
    r"\bof course\b",
    r"\bobviously\b",
    r"\bclearly\b",
    r"\bit'?s (really )?simple\b",
    r"\bjust\b.*\bjust\b",  # "just do X, just click Y"
    r"\bany(one|body) can\b",
]

# Patterns that suggest presumption
PRESUMPTION_PATTERNS = [
    r"\bwe (all )?(know|agree|believe)\b",
    r"\beveryone (knows|agrees|understands)\b",
    r"\bno one (would|could) (disagree|deny)\b",
    r"\bthe right thing to do\b",
    r"\bcommon sense\b",
]


def check_audience(
    text: str,
    model: AudienceModel,
    explanation_density: float = 0.0,
) -> AudienceCheckResult:
    """Check text against audience model constraints.

    Args:
        text: The text to check
        model: The audience model defining expectations
        explanation_density: Ratio of explanatory content (0-1)

    Returns:
        AudienceCheckResult with scores and violations
    """
    import re

    violations = []
    word_count = max(len(text.split()), 1)

    # Check for condescension patterns
    condescension_count = 0
    for pattern in CONDESCENSION_PATTERNS:
        condescension_count += len(re.findall(pattern, text, re.IGNORECASE))

    condescension_score = min(condescension_count * 0.15, 1.0)

    # Higher expertise assumption + high explanation density = condescension
    if model.assumed_expertise > 0.7 and explanation_density > 0.5:
        condescension_score = min(condescension_score + 0.3, 1.0)
        violations.append("over_explaining_to_experts")

    # Check for presumption patterns
    presumption_count = 0
    for pattern in PRESUMPTION_PATTERNS:
        presumption_count += len(re.findall(pattern, text, re.IGNORECASE))

    presumption_score = min(presumption_count * 0.20, 1.0)

    # Low alignment assumption + presumption patterns = worse
    if model.assumed_alignment < 0.3 and presumption_count > 0:
        presumption_score = min(presumption_score + 0.2, 1.0)
        violations.append("presuming_agreement_with_hostile_audience")

    # Exclusion: complex jargon without shared context
    # (simplified check - would need jargon detection)
    exclusion_score = 0.0
    if model.shared_context < 0.3 and model.assumed_expertise > 0.7:
        exclusion_score = 0.3
        violations.append("assuming_shared_context_that_may_not_exist")

    is_valid = (
        condescension_score < 0.5
        and exclusion_score < 0.5
        and presumption_score < 0.5
    )

    if condescension_score >= 0.5:
        violations.append("high_condescension")
    if presumption_score >= 0.5:
        violations.append("high_presumption")

    return AudienceCheckResult(
        condescension_score=condescension_score,
        exclusion_score=exclusion_score,
        presumption_score=presumption_score,
        is_valid=is_valid,
        violations=violations,
    )


# =============================================================================
# 2. Commitment Demand
# =============================================================================


class CommitmentType(str, Enum):
    """Types of reader commitment requested."""

    ATTENTION = "attention"  # Time to read/listen
    BELIEF = "belief"  # Accept a claim
    ACTION = "action"  # Do something
    IDENTITY = "identity"  # Change self-concept
    RELATIONSHIP = "relationship"  # Ongoing engagement


@dataclass
class CommitmentDemand:
    """A demand for reader commitment.

    From writingconstraints.md: Every commitment has a cost.
    Escalation must be earned. Can't ask for identity change in first paragraph.
    """

    commitment_type: CommitmentType
    magnitude: float = 0.5  # 0=trivial, 1=major
    position_in_text: float = 0.0  # 0=start, 1=end
    earned_trust: float = 0.0  # Trust accumulated before this point

    def cost(self) -> float:
        """Calculate commitment cost."""
        base_costs = {
            CommitmentType.ATTENTION: 0.1,
            CommitmentType.BELIEF: 0.3,
            CommitmentType.ACTION: 0.5,
            CommitmentType.IDENTITY: 0.8,
            CommitmentType.RELATIONSHIP: 0.6,
        }
        return base_costs.get(self.commitment_type, 0.5) * self.magnitude

    def to_dict(self) -> dict[str, Any]:
        return {
            "commitment_type": self.commitment_type.value,
            "magnitude": self.magnitude,
            "position_in_text": self.position_in_text,
            "earned_trust": self.earned_trust,
            "cost": self.cost(),
        }


@dataclass
class CommitmentCheckResult:
    """Result of commitment constraint check."""

    total_cost: float = 0.0
    trust_budget: float = 0.0
    overspend: float = 0.0
    escalation_violations: list[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost": self.total_cost,
            "trust_budget": self.trust_budget,
            "overspend": self.overspend,
            "escalation_violations": self.escalation_violations,
            "is_valid": self.is_valid,
        }


def check_commitments(
    demands: list[CommitmentDemand],
    initial_trust: float = 0.1,
) -> CommitmentCheckResult:
    """Check commitment demands against trust budget.

    Args:
        demands: List of commitment demands in order
        initial_trust: Starting trust level (0-1)

    Returns:
        CommitmentCheckResult with budget analysis
    """
    violations = []
    total_cost = 0.0
    trust_budget = initial_trust

    # Sort by position
    sorted_demands = sorted(demands, key=lambda d: d.position_in_text)

    for demand in sorted_demands:
        cost = demand.cost()
        total_cost += cost

        # Check escalation
        if demand.commitment_type == CommitmentType.IDENTITY:
            if demand.position_in_text < 0.5:
                violations.append("identity_commitment_too_early")
        if demand.commitment_type == CommitmentType.ACTION:
            if demand.position_in_text < 0.3 and demand.magnitude > 0.5:
                violations.append("major_action_request_too_early")

        # Trust accumulates with position (simplified model)
        trust_budget = initial_trust + demand.position_in_text * 0.5

    overspend = max(0.0, total_cost - trust_budget)
    is_valid = overspend < 0.2 and len(violations) == 0

    return CommitmentCheckResult(
        total_cost=total_cost,
        trust_budget=trust_budget,
        overspend=overspend,
        escalation_violations=violations,
        is_valid=is_valid,
    )


# =============================================================================
# 3. Authority Source
# =============================================================================


class AuthoritySource(str, Enum):
    """Source of authority claimed by the text."""

    EXPERTISE = "expertise"  # Domain knowledge
    EXPERIENCE = "experience"  # Personal history
    POSITION = "position"  # Role/title
    EVIDENCE = "evidence"  # Cited sources
    REASONING = "reasoning"  # Logical argument
    TRADITION = "tradition"  # Established practice
    CONSENSUS = "consensus"  # Expert agreement


@dataclass
class AuthorityProfile:
    """Authority profile for the text.

    From writingconstraints.md: Authority must be appropriate to regime.
    Research claims evidence. Instruction claims expertise. Fiction claims craft.
    """

    primary: AuthoritySource
    secondary: AuthoritySource | None = None
    strength: float = 0.5  # 0=weak, 1=strong

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "secondary": self.secondary.value if self.secondary else None,
            "strength": self.strength,
        }


# Regime-authority compatibility
REGIME_AUTHORITY_COMPATIBILITY: dict[str, set[AuthoritySource]] = {
    "research": {AuthoritySource.EVIDENCE, AuthoritySource.REASONING, AuthoritySource.CONSENSUS},
    "nonfiction": {AuthoritySource.EVIDENCE, AuthoritySource.REASONING, AuthoritySource.EXPERIENCE},
    "instruction": {AuthoritySource.EXPERTISE, AuthoritySource.EXPERIENCE, AuthoritySource.EVIDENCE},
    "debugging": {AuthoritySource.EXPERTISE, AuthoritySource.EVIDENCE, AuthoritySource.REASONING},
    "negotiation": {AuthoritySource.REASONING, AuthoritySource.POSITION, AuthoritySource.EXPERIENCE},
    "advocacy": {AuthoritySource.EVIDENCE, AuthoritySource.EXPERIENCE, AuthoritySource.REASONING},
    "marketing": {AuthoritySource.EXPERIENCE, AuthoritySource.CONSENSUS, AuthoritySource.EVIDENCE},
    "comedy": {AuthoritySource.EXPERIENCE, AuthoritySource.REASONING},
    "tragedy": {AuthoritySource.EXPERIENCE, AuthoritySource.TRADITION},
    "horror": {AuthoritySource.EXPERIENCE},
    "romance": {AuthoritySource.EXPERIENCE},
    "satire": {AuthoritySource.REASONING, AuthoritySource.EVIDENCE},
    "liturgical": {AuthoritySource.TRADITION, AuthoritySource.CONSENSUS},
    "aphorism": {AuthoritySource.EXPERIENCE, AuthoritySource.TRADITION},
}


@dataclass
class AuthorityCheckResult:
    """Result of authority constraint check."""

    compatible: bool = True
    overclaiming: bool = False
    weak_blend: bool = False
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "overclaiming": self.overclaiming,
            "weak_blend": self.weak_blend,
            "violations": self.violations,
        }


def check_authority(
    profile: AuthorityProfile,
    regime: str,
) -> AuthorityCheckResult:
    """Check authority profile against regime requirements.

    Args:
        profile: The authority profile being claimed
        regime: The active writing regime

    Returns:
        AuthorityCheckResult with compatibility analysis
    """
    violations = []
    regime_lower = regime.lower()

    # Get compatible sources for regime
    compatible_sources = REGIME_AUTHORITY_COMPATIBILITY.get(
        regime_lower, set(AuthoritySource)
    )

    # Check primary compatibility
    compatible = profile.primary in compatible_sources
    if not compatible:
        violations.append(f"primary_authority_{profile.primary.value}_incompatible_with_{regime_lower}")

    # Check secondary compatibility
    if profile.secondary and profile.secondary not in compatible_sources:
        violations.append(f"secondary_authority_{profile.secondary.value}_incompatible_with_{regime_lower}")

    # Check overclaiming (high strength without strong source)
    overclaiming = False
    if profile.strength > 0.8:
        if profile.primary in {AuthoritySource.CONSENSUS, AuthoritySource.TRADITION}:
            # These require actual backing
            overclaiming = True
            violations.append("high_strength_claim_needs_backing")

    # Check weak blend (two weak sources don't make strong)
    weak_blend = False
    if profile.secondary and profile.strength > 0.7:
        weak_sources = {AuthoritySource.EXPERIENCE, AuthoritySource.POSITION}
        if profile.primary in weak_sources and profile.secondary in weak_sources:
            weak_blend = True
            violations.append("weak_authority_blend")

    return AuthorityCheckResult(
        compatible=compatible,
        overclaiming=overclaiming,
        weak_blend=weak_blend,
        violations=violations,
    )


# =============================================================================
# 4. Silence Discipline
# =============================================================================


class SilenceReason(str, Enum):
    """Reason for deliberate silence."""

    NOT_KNOWN = "not_known"  # Genuinely don't know
    NOT_APPROPRIATE = "not_appropriate"  # Know but shouldn't say
    NOT_HELPFUL = "not_helpful"  # Would derail
    NOT_EARNED = "not_earned"  # Reader hasn't earned this
    STRATEGIC = "strategic"  # Withholding for effect


@dataclass
class SilenceDecision:
    """A decision to not say something.

    From writingconstraints.md: Silence is a choice. What you don't say
    shapes meaning as much as what you do. Silence must be intentional.
    """

    reason: SilenceReason
    topic: str
    regime: str
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason.value,
            "topic": self.topic,
            "regime": self.regime,
            "is_valid": self.is_valid,
        }


# Regime-specific silence rules
VALID_SILENCE_REASONS: dict[str, set[SilenceReason]] = {
    "research": {SilenceReason.NOT_KNOWN, SilenceReason.NOT_HELPFUL},
    "nonfiction": {SilenceReason.NOT_KNOWN, SilenceReason.NOT_HELPFUL, SilenceReason.NOT_APPROPRIATE},
    "instruction": {SilenceReason.NOT_HELPFUL, SilenceReason.NOT_APPROPRIATE},
    "horror": {SilenceReason.STRATEGIC, SilenceReason.NOT_EARNED},
    "tragedy": {SilenceReason.STRATEGIC, SilenceReason.NOT_EARNED},
    "comedy": {SilenceReason.NOT_HELPFUL},
    "satire": {SilenceReason.STRATEGIC},
}


def check_silence(decision: SilenceDecision) -> bool:
    """Check if silence decision is valid for regime.

    Args:
        decision: The silence decision to check

    Returns:
        True if valid, False otherwise
    """
    regime_lower = decision.regime.lower()
    valid_reasons = VALID_SILENCE_REASONS.get(regime_lower, set(SilenceReason))
    return decision.reason in valid_reasons


# =============================================================================
# 5. Repetition Discipline
# =============================================================================


class RepetitionType(str, Enum):
    """Type of repetition."""

    ACCIDENTAL = "accidental"  # Unintended (always bad)
    STRUCTURAL = "structural"  # Parallel structure
    SEMANTIC = "semantic"  # Restating for clarity
    RHETORICAL = "rhetorical"  # For emphasis/rhythm


@dataclass
class RepetitionAnalysis:
    """Analysis of text repetition.

    From writingconstraints.md: Accidental repetition is always a flaw.
    Semantic repetition only appropriate in instruction.
    Structural/rhetorical must serve regime purpose.
    """

    type: RepetitionType
    phrase: str
    count: int
    regime: str
    is_valid: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "phrase": self.phrase,
            "count": self.count,
            "regime": self.regime,
            "is_valid": self.is_valid,
            "reason": self.reason,
        }


# Regime-specific repetition rules
ALLOWED_REPETITION: dict[str, set[RepetitionType]] = {
    "instruction": {RepetitionType.SEMANTIC, RepetitionType.STRUCTURAL},
    "research": {RepetitionType.STRUCTURAL},
    "liturgical": {RepetitionType.RHETORICAL, RepetitionType.STRUCTURAL},
    "aphorism": set(),  # No repetition
    "comedy": {RepetitionType.RHETORICAL},
    "tragedy": {RepetitionType.STRUCTURAL, RepetitionType.RHETORICAL},
    "advocacy": {RepetitionType.RHETORICAL, RepetitionType.STRUCTURAL},
}


def check_repetition(analysis: RepetitionAnalysis) -> bool:
    """Check if repetition is valid for regime.

    Args:
        analysis: The repetition to check

    Returns:
        True if valid, False otherwise
    """
    # Accidental is always invalid
    if analysis.type == RepetitionType.ACCIDENTAL:
        return False

    regime_lower = analysis.regime.lower()
    allowed = ALLOWED_REPETITION.get(regime_lower, {RepetitionType.STRUCTURAL})
    return analysis.type in allowed


# =============================================================================
# 6. Error Posture
# =============================================================================


class ErrorPosture(str, Enum):
    """How errors are handled/acknowledged."""

    INVISIBLE = "invisible"  # Don't show working
    ACKNOWLEDGED = "acknowledged"  # Admit uncertainty
    TRANSPARENT = "transparent"  # Show full reasoning
    CELEBRATED = "celebrated"  # Errors are learning


@dataclass
class ErrorPostureConfig:
    """Error posture configuration.

    From writingconstraints.md: Error posture must match regime.
    Research requires transparency. Instruction can hide working.
    Fiction should be invisible.
    """

    posture: ErrorPosture
    regime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "posture": self.posture.value,
            "regime": self.regime,
        }


# Default error posture by regime
DEFAULT_ERROR_POSTURE: dict[str, ErrorPosture] = {
    "research": ErrorPosture.TRANSPARENT,
    "nonfiction": ErrorPosture.ACKNOWLEDGED,
    "instruction": ErrorPosture.ACKNOWLEDGED,
    "debugging": ErrorPosture.TRANSPARENT,
    "comedy": ErrorPosture.INVISIBLE,
    "tragedy": ErrorPosture.INVISIBLE,
    "horror": ErrorPosture.INVISIBLE,
    "romance": ErrorPosture.INVISIBLE,
    "satire": ErrorPosture.INVISIBLE,
    "liturgical": ErrorPosture.INVISIBLE,
    "aphorism": ErrorPosture.INVISIBLE,
    "negotiation": ErrorPosture.ACKNOWLEDGED,
    "advocacy": ErrorPosture.ACKNOWLEDGED,
    "marketing": ErrorPosture.INVISIBLE,
}


def get_error_posture(regime: str) -> ErrorPosture:
    """Get default error posture for regime.

    Args:
        regime: The active writing regime

    Returns:
        The appropriate error posture
    """
    return DEFAULT_ERROR_POSTURE.get(regime.lower(), ErrorPosture.ACKNOWLEDGED)


# =============================================================================
# 7. Exit Shape
# =============================================================================


@dataclass
class ExitCheckResult:
    """Result of exit shape check.

    From writingconstraints.md: How you end shapes how reader remembers.
    Bad exits: moral bow, recap that wasn't asked, unearned CTA,
    "hope this helps", offering more than asked.
    """

    bad_patterns_found: list[str] = field(default_factory=list)
    commitment_delta: float = 0.0  # Change in commitment asked at exit
    is_clean: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "bad_patterns_found": self.bad_patterns_found,
            "commitment_delta": self.commitment_delta,
            "is_clean": self.is_clean,
        }


def check_exit_shape(text: str, exit_portion: float = 0.2) -> ExitCheckResult:
    """Check the exit portion of text for bad patterns.

    Args:
        text: Full text
        exit_portion: What fraction of end to check (default 20%)

    Returns:
        ExitCheckResult with analysis
    """
    words = text.split()
    exit_start = int(len(words) * (1 - exit_portion))
    exit_text = " ".join(words[exit_start:])

    bad_patterns_found = []
    for pattern in BAD_EXIT_PATTERNS:
        # BAD_EXIT_PATTERNS are already compiled Pattern objects
        if pattern.search(exit_text):
            bad_patterns_found.append(pattern.pattern)

    is_clean = len(bad_patterns_found) == 0

    return ExitCheckResult(
        bad_patterns_found=bad_patterns_found,
        commitment_delta=0.0,  # Would need commitment tracking
        is_clean=is_clean,
    )


# =============================================================================
# 8. Temporal Consistency
# =============================================================================


@dataclass
class TemporalConsistencyResult:
    """Result of temporal consistency check.

    From writingconstraints.md: Tense shifts must be intentional.
    Flashbacks must be signaled. Timeline must be recoverable.
    """

    tense_shifts: int = 0
    signaled_shifts: int = 0
    unsignaled_shifts: int = 0
    is_consistent: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tense_shifts": self.tense_shifts,
            "signaled_shifts": self.signaled_shifts,
            "unsignaled_shifts": self.unsignaled_shifts,
            "is_consistent": self.is_consistent,
        }


# Patterns that signal temporal shifts
TEMPORAL_SIGNAL_PATTERNS = [
    r"\b(earlier|later|before|after|meanwhile|previously|subsequently)\b",
    r"\b(at that time|back then|in those days|years (ago|later))\b",
    r"\b(flashback|flash forward)\b",
    r"\b(now|then|soon|eventually)\b",
]


def check_temporal_consistency(
    text: str,
    tense_shift_count: int = 0,
) -> TemporalConsistencyResult:
    """Check temporal consistency of text.

    Args:
        text: The text to check
        tense_shift_count: Number of detected tense shifts (from external parser)

    Returns:
        TemporalConsistencyResult with analysis
    """
    import re

    # Count temporal signals
    signal_count = 0
    for pattern in TEMPORAL_SIGNAL_PATTERNS:
        signal_count += len(re.findall(pattern, text, re.IGNORECASE))

    # Assume unsignaled shifts are bad
    signaled = min(signal_count, tense_shift_count)
    unsignaled = max(0, tense_shift_count - signal_count)

    is_consistent = unsignaled == 0

    return TemporalConsistencyResult(
        tense_shifts=tense_shift_count,
        signaled_shifts=signaled,
        unsignaled_shifts=unsignaled,
        is_consistent=is_consistent,
    )


# =============================================================================
# 9. Moral Weight
# =============================================================================


@dataclass
class MoralWeightResult:
    """Result of moral weight check.

    From writingconstraints.md: Moral weight must be calibrated.
    Inflating minor issues damages credibility.
    Deflating major issues is negligence.
    """

    inflated_count: int = 0
    deflated_count: int = 0
    calibration_score: float = 1.0  # 1.0 = perfectly calibrated
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inflated_count": self.inflated_count,
            "deflated_count": self.deflated_count,
            "calibration_score": self.calibration_score,
            "violations": self.violations,
        }


def check_moral_weight(text: str) -> MoralWeightResult:
    """Check text for moral weight miscalibration.

    Args:
        text: The text to check

    Returns:
        MoralWeightResult with calibration analysis
    """
    violations = []

    # Check for inflated weight patterns
    inflated_count = count_pattern_matches(text, INFLATED_WEIGHT_PATTERNS)

    if inflated_count > 2:
        violations.append("excessive_moral_inflation")

    calibration_score = max(0.0, 1.0 - inflated_count * 0.15)

    return MoralWeightResult(
        inflated_count=inflated_count,
        deflated_count=0,  # Would need context to detect
        calibration_score=calibration_score,
        violations=violations,
    )


# =============================================================================
# 10. Legibility Budget
# =============================================================================


@dataclass
class LegibilityBudget:
    """Legibility budget tracking.

    From writingconstraints.md: Each piece of cognitive work has a cost.
    Unrequested complexity costs double. Budget is finite.
    """

    total_budget: float = 1.0
    spent: float = 0.0
    unrequested_cost: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.total_budget - self.spent)

    @property
    def is_overdrawn(self) -> bool:
        return self.spent > self.total_budget

    def spend(self, amount: float, requested: bool = True) -> bool:
        """Spend from legibility budget.

        Args:
            amount: Amount to spend
            requested: Whether this complexity was requested (2x if not)

        Returns:
            True if spend succeeded, False if overdrawn
        """
        actual = amount if requested else amount * 2
        if not requested:
            self.unrequested_cost += actual
        self.spent += actual
        return not self.is_overdrawn

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "spent": self.spent,
            "remaining": self.remaining,
            "unrequested_cost": self.unrequested_cost,
            "is_overdrawn": self.is_overdrawn,
        }


# =============================================================================
# 11. Premature Solution (Meta-Invariant)
# =============================================================================


@dataclass
class PrematureSolutionResult:
    """Result of premature solution check.

    From writingconstraints.md: The meta-invariant. Solution before problem
    is defined = failure. Solution before problem is felt = failure.
    """

    problem_established: bool = False
    problem_felt: bool = False
    solution_offered: bool = False
    is_premature: bool = False
    violation_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_established": self.problem_established,
            "problem_felt": self.problem_felt,
            "solution_offered": self.solution_offered,
            "is_premature": self.is_premature,
            "violation_type": self.violation_type,
        }


def check_premature_solution(
    problem_position: float | None,
    felt_position: float | None,
    solution_position: float | None,
) -> PrematureSolutionResult:
    """Check for premature solution offering.

    Args:
        problem_position: Position where problem is stated (0-1), None if not stated
        felt_position: Position where problem is felt (0-1), None if not felt
        solution_position: Position where solution is offered (0-1), None if not offered

    Returns:
        PrematureSolutionResult with analysis
    """
    problem_established = problem_position is not None
    problem_felt = felt_position is not None
    solution_offered = solution_position is not None

    is_premature = False
    violation_type = None

    if solution_offered:
        if not problem_established:
            is_premature = True
            violation_type = "solution_without_problem"
        elif problem_position is not None and solution_position is not None:
            if solution_position < problem_position:
                is_premature = True
                violation_type = "solution_before_problem"

        if not problem_felt and problem_established:
            # Problem stated but not felt - less severe
            if felt_position is None:
                is_premature = True
                violation_type = "solution_before_felt"

    return PrematureSolutionResult(
        problem_established=problem_established,
        problem_felt=problem_felt,
        solution_offered=solution_offered,
        is_premature=is_premature,
        violation_type=violation_type,
    )


# =============================================================================
# Aggregate Constraint Check
# =============================================================================


@dataclass
class StructuralConstraintResults:
    """Aggregate results from all structural constraint checks."""

    audience: AudienceCheckResult | None = None
    commitment: CommitmentCheckResult | None = None
    authority: AuthorityCheckResult | None = None
    exit_shape: ExitCheckResult | None = None
    temporal: TemporalConsistencyResult | None = None
    moral_weight: MoralWeightResult | None = None
    premature_solution: PrematureSolutionResult | None = None
    legibility: LegibilityBudget | None = None
    causal_narration: CausalNarrationResult | None = None

    @property
    def all_valid(self) -> bool:
        """Check if all constraint checks passed."""
        checks = []
        if self.audience:
            checks.append(self.audience.is_valid)
        if self.commitment:
            checks.append(self.commitment.is_valid)
        if self.authority:
            checks.append(self.authority.compatible and not self.authority.overclaiming)
        if self.exit_shape:
            checks.append(self.exit_shape.is_clean)
        if self.temporal:
            checks.append(self.temporal.is_consistent)
        if self.moral_weight:
            checks.append(len(self.moral_weight.violations) == 0)
        if self.premature_solution:
            checks.append(not self.premature_solution.is_premature)
        if self.legibility:
            checks.append(not self.legibility.is_overdrawn)
        if self.causal_narration:
            checks.append(not self.causal_narration.is_suspicious)
        return all(checks) if checks else True

    @property
    def violations(self) -> list[str]:
        """Collect all violations from sub-checks."""
        result = []
        if self.audience:
            result.extend(self.audience.violations)
        if self.commitment:
            result.extend(self.commitment.escalation_violations)
        if self.authority:
            result.extend(self.authority.violations)
        if self.exit_shape:
            result.extend(self.exit_shape.bad_patterns_found)
        if self.moral_weight:
            result.extend(self.moral_weight.violations)
        if self.premature_solution and self.premature_solution.violation_type:
            result.append(self.premature_solution.violation_type)
        if self.causal_narration and self.causal_narration.is_suspicious:
            result.extend(self.causal_narration.detection_notes)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_valid": self.all_valid,
            "violations": self.violations,
            "audience": self.audience.to_dict() if self.audience else None,
            "commitment": self.commitment.to_dict() if self.commitment else None,
            "authority": self.authority.to_dict() if self.authority else None,
            "exit_shape": self.exit_shape.to_dict() if self.exit_shape else None,
            "temporal": self.temporal.to_dict() if self.temporal else None,
            "moral_weight": self.moral_weight.to_dict() if self.moral_weight else None,
            "premature_solution": self.premature_solution.to_dict() if self.premature_solution else None,
            "legibility": self.legibility.to_dict() if self.legibility else None,
            "causal_narration": self.causal_narration.to_dict() if self.causal_narration else None,
        }


def check_all(
    text: str,
    regime: str,
    audience_model: AudienceModel | None = None,
    authority_profile: AuthorityProfile | None = None,
    commitments: list[CommitmentDemand] | None = None,
    check_causal_narration: bool = True,
) -> StructuralConstraintResults:
    """Run all structural constraint checks.

    Args:
        text: The text to check
        regime: The active writing regime
        audience_model: Optional audience model
        authority_profile: Optional authority profile
        commitments: Optional list of commitment demands
        check_causal_narration: Whether to run causal narration detection (default True)

    Returns:
        StructuralConstraintResults with all check results
    """
    results = StructuralConstraintResults()

    # Audience check
    if audience_model:
        results.audience = check_audience(text, audience_model)

    # Commitment check
    if commitments:
        results.commitment = check_commitments(commitments)

    # Authority check
    if authority_profile:
        results.authority = check_authority(authority_profile, regime)

    # Exit shape check
    results.exit_shape = check_exit_shape(text)

    # Moral weight check
    results.moral_weight = check_moral_weight(text)

    # Causal narration resistance check
    if check_causal_narration:
        results.causal_narration = detect_causal_narration_resistance(text)

    return results


# =============================================================================
# 12. Institutional Resistance to Causal Narration
# =============================================================================


class CausalNarrationTechnique(str, Enum):
    """Primary techniques for preventing causal narratives from forming.

    From structconst.md §14: These don't lower Eₚ by lying. They lower it
    by preventing the formation of narrative that would require honesty about.
    """

    TICKET_SUBSTITUTION = "ticket_substitution"  # Ticket numbers instead of explanations
    COMPLEXITY_DIFFUSION = "complexity_diffusion"  # "Complex situation, many factors"
    TIME_BOUNDING = "time_bounding"  # "That was then" - severs before/after
    PERSONNEL_CHURN = "personnel_churn"  # "New leadership" - resets accountability
    SCOPE_SHRINKING = "scope_shrinking"  # "Out of context" - prevents linking
    MORAL_REFRAMING = "moral_reframing"  # "Speculation is harmful" - meta suppression


class CausalNarrationFailureMode(str, Enum):
    """Extended failure modes that often co-occur with primary techniques.

    From structconst.md §14.4: Adjacent failure modes that prevent
    causality from congealing into obligation.
    """

    CAUSAL_SATURATION = "causal_saturation"  # Too many causes = undecidable
    COUNTERFACTUAL_POISONING = "counterfactual_poisoning"  # "Can't know otherwise"
    RESPONSIBILITY_VIRTUALIZATION = "responsibility_virtualization"  # "System failed"
    POST_HOC_LEGIBILITY = "post_hoc_legibility"  # Hindsight-only explanations
    NARRATIVE_FORK_SUPPRESSION = "narrative_fork_suppression"  # Premature consensus
    ASYMMETRIC_BURDEN = "asymmetric_burden"  # Selective evidence standards
    LATENCY_LAUNDERING = "latency_laundering"  # Delay used to deny linkage
    EPISTEMIC_DELEGATION = "epistemic_delegation"  # "Experts are looking into it"
    MORAL_LOAD_SHEDDING = "moral_load_shedding"  # Inquiry framed as harmful
    PROCEDURAL_OVERFITTING = "procedural_overfitting"  # Audits pass, failures repeat


# Pattern banks for each technique
TICKET_SUBSTITUTION_PATTERNS = [
    r"\b(see|per|ref|reference|as per) (ticket|issue|jira|bug|task)[\s#-]*\d+\b",
    r"\btracked (in|under|via)\b",
    r"\b(this|that) (is|was) (a )?(separate|different) (issue|ticket|matter)\b",
    r"\bplease (file|open|create) (a )?(ticket|issue)\b",
]

COMPLEXITY_DIFFUSION_PATTERNS = [
    r"\bcomplex (situation|issue|matter|problem)\b",
    r"\bmany (factors|considerations|variables)\b",
    r"\bmultifaceted\b",
    r"\bnuanced\b",
    r"\bit'?s (complicated|not (that )?simple)\b",
    r"\bthere (are|were) (many|multiple|various) (reasons|causes|factors)\b",
    r"\ba (combination|confluence) of (factors|things)\b",
]

TIME_BOUNDING_PATTERNS = [
    r"\bthat was (then|a different time|before)\b",
    r"\b(things|circumstances) (have|had) changed\b",
    r"\b(at that time|back then|in (those|that) (era|period))\b",
    r"\bdifferent context\b",
    r"\bwe'?ve moved (on|past|beyond)\b",
    r"\bhistorical (context|circumstances)\b",
    r"\bwater under the bridge\b",
]

PERSONNEL_CHURN_PATTERNS = [
    r"\b(new|different) (leadership|management|team|administration)\b",
    r"\b(under|with) (new|previous|prior) (leadership|management)\b",
    r"\b(those|the) people (are|have) (gone|left|moved on)\b",
    r"\bno longer (here|with us|on the team)\b",
    r"\breorganization\b",
    r"\bfresh start\b",
]

SCOPE_SHRINKING_PATTERNS = [
    r"\bout of (scope|context)\b",
    r"\bthat'?s (outside|beyond|not within) (our|the|my) (scope|purview|remit)\b",
    r"\bseparate (issue|matter|concern)\b",
    r"\bnot (relevant|related|connected) (to|here)\b",
    r"\blet'?s (focus|stay focused) (on|within)\b",
    r"\bwe'?re (getting|going) off (topic|track)\b",
]

MORAL_REFRAMING_PATTERNS = [
    r"\bspeculation (is|would be) (harmful|unhelpful|dangerous)\b",
    r"\b(let'?s|we should) not (speculate|assign blame|point fingers)\b",
    r"\b(finger[- ]?pointing|blame[- ]?game)\b",
    r"\b(this|that) (isn'?t|is not) (helpful|productive|constructive)\b",
    r"\bretraumatizing\b",
    r"\b(move|moving) forward (positively|constructively)\b",
    r"\bharm(ful)? to (revisit|re-?litigate|dwell (on|upon))\b",
]

# Extended failure mode patterns
CAUSAL_SATURATION_PATTERNS = [
    r"\b(many|multiple|numerous|various|several) (contributing )?(factors|causes|reasons)\b",
    r"\bperfect storm\b",
    r"\bconvergence of\b",
    r"\bno (single|one) (cause|factor|reason)\b",
]

COUNTERFACTUAL_POISONING_PATTERNS = [
    r"\bcan'?t (know|say) what would have\b",
    r"\bimpossible to (know|determine) (if|whether)\b",
    r"\bunknowable\b",
    r"\bcounterfactual\b",
    r"\bwould have happened (anyway|regardless)\b",
]

RESPONSIBILITY_VIRTUALIZATION_PATTERNS = [
    r"\b(the )?(system|process|culture|organization) (failed|broke down)\b",
    r"\bsystemic (issue|failure|problem)\b",
    r"\bcultural (issue|problem)\b",
    r"\bno (one|single) (person|individual) (is|was) (responsible|to blame)\b",
    r"\bshared (responsibility|accountability)\b",
    r"\binstitutional (failure|breakdown)\b",
]

EPISTEMIC_DELEGATION_PATTERNS = [
    r"\bexperts are (looking into|investigating|reviewing)\b",
    r"\babove (my|our) pay grade\b",
    r"\b(defer|deferring) to (the )?(experts|specialists)\b",
    r"\b(that|this) (is|requires) (a )?(specialist|expert)\b",
    r"\b(we|I) (trust|rely on) (the )?(experts|process)\b",
]

MORAL_LOAD_SHEDDING_PATTERNS = [
    r"\b(harmful|hurtful) to (ask|inquire|investigate|revisit)\b",
    r"\bretraumatiz(e|ing)\b",
    r"\b(move|moving) (on|forward) (for|to) heal\b",
    r"\b(closure|healing) (requires|means) (not|leaving)\b",
    r"\b(let|leave) (it|the past) (go|rest)\b",
]


@dataclass
class CausalNarrationResult:
    """Result of causal narration resistance detection.

    From structconst.md §14: Breaking causal narration doesn't require lying.
    It just requires preventing facts from linking. Fog doesn't need defense.
    """

    techniques_detected: list[CausalNarrationTechnique] = field(default_factory=list)
    failure_modes_detected: list[CausalNarrationFailureMode] = field(default_factory=list)
    technique_counts: dict[str, int] = field(default_factory=dict)
    failure_mode_counts: dict[str, int] = field(default_factory=dict)
    fog_score: float = 0.0  # Overall fog density (0=clear, 1=impenetrable)
    is_suspicious: bool = False
    detection_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "techniques_detected": [t.value for t in self.techniques_detected],
            "failure_modes_detected": [f.value for f in self.failure_modes_detected],
            "technique_counts": self.technique_counts,
            "failure_mode_counts": self.failure_mode_counts,
            "fog_score": self.fog_score,
            "is_suspicious": self.is_suspicious,
            "detection_notes": self.detection_notes,
        }


# Technique to pattern bank mapping
_TECHNIQUE_PATTERNS: dict[CausalNarrationTechnique, list[str]] = {
    CausalNarrationTechnique.TICKET_SUBSTITUTION: TICKET_SUBSTITUTION_PATTERNS,
    CausalNarrationTechnique.COMPLEXITY_DIFFUSION: COMPLEXITY_DIFFUSION_PATTERNS,
    CausalNarrationTechnique.TIME_BOUNDING: TIME_BOUNDING_PATTERNS,
    CausalNarrationTechnique.PERSONNEL_CHURN: PERSONNEL_CHURN_PATTERNS,
    CausalNarrationTechnique.SCOPE_SHRINKING: SCOPE_SHRINKING_PATTERNS,
    CausalNarrationTechnique.MORAL_REFRAMING: MORAL_REFRAMING_PATTERNS,
}

# Failure mode to pattern bank mapping
_FAILURE_MODE_PATTERNS: dict[CausalNarrationFailureMode, list[str]] = {
    CausalNarrationFailureMode.CAUSAL_SATURATION: CAUSAL_SATURATION_PATTERNS,
    CausalNarrationFailureMode.COUNTERFACTUAL_POISONING: COUNTERFACTUAL_POISONING_PATTERNS,
    CausalNarrationFailureMode.RESPONSIBILITY_VIRTUALIZATION: RESPONSIBILITY_VIRTUALIZATION_PATTERNS,
    CausalNarrationFailureMode.EPISTEMIC_DELEGATION: EPISTEMIC_DELEGATION_PATTERNS,
    CausalNarrationFailureMode.MORAL_LOAD_SHEDDING: MORAL_LOAD_SHEDDING_PATTERNS,
}


def detect_causal_narration_resistance(text: str) -> CausalNarrationResult:
    """Detect institutional resistance to causal narration.

    From structconst.md §14: Detects techniques that prevent facts from linking.
    These don't deny facts - they prevent narrative formation.

    Args:
        text: The text to analyze

    Returns:
        CausalNarrationResult with detection analysis
    """
    import re

    techniques_detected: list[CausalNarrationTechnique] = []
    failure_modes_detected: list[CausalNarrationFailureMode] = []
    technique_counts: dict[str, int] = {}
    failure_mode_counts: dict[str, int] = {}
    detection_notes: list[str] = []

    # Check primary techniques
    for technique, patterns in _TECHNIQUE_PATTERNS.items():
        count = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            count += matches
        if count > 0:
            techniques_detected.append(technique)
            technique_counts[technique.value] = count

    # Check failure modes
    for mode, patterns in _FAILURE_MODE_PATTERNS.items():
        count = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            count += matches
        if count > 0:
            failure_modes_detected.append(mode)
            failure_mode_counts[mode.value] = count

    # Calculate fog score
    total_detections = sum(technique_counts.values()) + sum(failure_mode_counts.values())
    word_count = max(len(text.split()), 1)
    fog_density = total_detections / (word_count / 100)  # per 100 words
    fog_score = min(fog_density * 0.2, 1.0)  # normalize to 0-1

    # Determine suspicion threshold
    is_suspicious = (
        len(techniques_detected) >= 2
        or len(failure_modes_detected) >= 2
        or total_detections >= 5
        or fog_score > 0.4
    )

    # Add detection notes for significant findings
    if CausalNarrationTechnique.MORAL_REFRAMING in techniques_detected:
        detection_notes.append("moral_reframing_detected: inquiry may be framed as harmful")
    if CausalNarrationTechnique.COMPLEXITY_DIFFUSION in techniques_detected:
        detection_notes.append("complexity_diffusion_detected: causality may be intentionally obscured")
    if CausalNarrationFailureMode.RESPONSIBILITY_VIRTUALIZATION in failure_modes_detected:
        detection_notes.append("responsibility_virtualization_detected: blame acknowledged but cannot land")
    if CausalNarrationFailureMode.COUNTERFACTUAL_POISONING in failure_modes_detected:
        detection_notes.append("counterfactual_poisoning_detected: evaluation of decisions blocked")

    return CausalNarrationResult(
        techniques_detected=techniques_detected,
        failure_modes_detected=failure_modes_detected,
        technique_counts=technique_counts,
        failure_mode_counts=failure_mode_counts,
        fog_score=fog_score,
        is_suspicious=is_suspicious,
        detection_notes=detection_notes,
    )


# Detection mapping: institutional techniques → existing detectors
# From structconst.md §14.5
CAUSAL_NARRATION_DETECTION_MAPPING: dict[str, str] = {
    "time_bound_resets": "temporal_discontinuity",
    "procedural_closure_without_explanation": "premature_closure",
    "role_churn_as_explanation": "authority_mismatch",
    "scope_shrinking_on_linkage": "exit_shape_violation",
    "moralization_of_inquiry": "meta_level_suppression",
    "causal_saturation": "low_claim_evidence_coupling",
    "responsibility_virtualization": "passive_voice_governance_leak",
    "epistemic_delegation": "authority_source_mismatch",
}
