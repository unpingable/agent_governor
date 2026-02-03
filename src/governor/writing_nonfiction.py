"""
Writing Nonfiction — Epistemic control for nonfiction writing.

NfClaimLevel: SOFT/HARD/NORM claim hierarchy with promotion rules.
PromotionGate: Validates claim level promotions.
VelocityController: Tracks claim/evidence velocity balance.
EpScorer: Epistemic honesty perception scoring.
ReScorer: Epistemic risk exposure scoring.
HedgeCalibrator: Distinguishes epistemic vs social hedges.
AhScorer: Alternative hypothesis engagement scoring.
NleadChecker: Normativity lead detection.
NonfictionFailureDetector: Identifies failure modes.

Key insight from nonfic.md: claims must be earned through evidence,
not declared through governance artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .writing_patterns import (
    ANXIETY_HEDGE_PATTERNS,
    CAUSAL_HUMILITY_PATTERNS,
    FALSIFIER_PATTERNS,
    GOVERNANCE_ARTIFACT_PATTERNS,
    HEDGE_PATTERNS,
    NORMATIVE_PATTERNS,
    STRAWMAN_PATTERNS,
    count_categorized_patterns,
    count_pattern_matches,
)


# =============================================================================
# Constants
# =============================================================================

# Maximum tokens between claim and supporting evidence
MAX_GAP_TOKENS_HARD: int = 150
MAX_GAP_TOKENS_NORM: int = 100

# Minimum evidence shown before normative claims
MIN_EVIDENCE_BEFORE_NORM: float = 0.4

# Governance visibility ceiling
GV_CEILING: float = 0.3

# Epistemic/social hedge ranges
EPISTEMIC_HEDGE_MIN: float = 0.1
EPISTEMIC_HEDGE_MAX: float = 0.4
SOCIAL_HEDGE_CEILING: float = 0.1

# Score floors
RE_FLOOR: float = 0.4
AH_FLOOR: float = 0.3


# =============================================================================
# NfClaimLevel
# =============================================================================


class NfClaimLevel(str, Enum):
    """Claim levels for nonfiction writing."""

    SOFT = "soft"  # Speculative, no evidence required
    HARD = "hard"  # Requires explicit evidence within gap
    NORM = "norm"  # Normative, requires HARD base + value premise


# =============================================================================
# NfClaimNode
# =============================================================================


@dataclass
class NfClaimNode:
    """A claim in the nonfiction claim graph."""

    id: str
    text: str
    level: NfClaimLevel = NfClaimLevel.SOFT
    token_index: int = 0
    dependencies: list[str] = field(default_factory=list)  # claim IDs
    evidence_links: list[str] = field(default_factory=list)  # evidence IDs
    value_premise: str | None = None  # for NORM claims

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "level": self.level.value,
            "token_index": self.token_index,
            "dependencies": self.dependencies,
            "evidence_links": self.evidence_links,
            "value_premise": self.value_premise,
        }


# =============================================================================
# PromotionGate
# =============================================================================


@dataclass
class PromotionResult:
    """Result of claim promotion check."""

    can_promote: bool = False
    reason: str = ""
    missing_requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_promote": self.can_promote,
            "reason": self.reason,
            "missing_requirements": self.missing_requirements,
        }


class PromotionGate:
    """Validates claim level promotions.

    From nonfic.md:
    - SOFT→HARD: explicit support within MAX_GAP_TOKENS_HARD, all dependencies HARD
    - HARD→NORM: HARD base + explicit value premise, gap < MAX_GAP_TOKENS_NORM
    """

    def __init__(
        self,
        max_gap_hard: int = MAX_GAP_TOKENS_HARD,
        max_gap_norm: int = MAX_GAP_TOKENS_NORM,
    ) -> None:
        self._max_gap_hard = max_gap_hard
        self._max_gap_norm = max_gap_norm

    def can_promote(
        self,
        claim: NfClaimNode,
        target_level: NfClaimLevel,
        evidence_gap: int,
        dependencies_met: bool = True,
    ) -> PromotionResult:
        """Check if claim can be promoted to target level.

        Args:
            claim: The claim to promote
            target_level: Target level (HARD or NORM)
            evidence_gap: Tokens since last evidence
            dependencies_met: Whether all dependencies are at required level

        Returns:
            PromotionResult indicating success or missing requirements
        """
        missing: list[str] = []

        if target_level == NfClaimLevel.SOFT:
            # Demotion or no-op always allowed
            return PromotionResult(can_promote=True, reason="SOFT always allowed")

        if target_level == NfClaimLevel.HARD:
            if claim.level == NfClaimLevel.HARD:
                return PromotionResult(can_promote=True, reason="Already HARD")

            if evidence_gap > self._max_gap_hard:
                missing.append(f"evidence_gap ({evidence_gap}) > max ({self._max_gap_hard})")

            if not dependencies_met:
                missing.append("not all dependencies are HARD")

            if not claim.evidence_links:
                missing.append("no evidence links")

            if missing:
                return PromotionResult(
                    can_promote=False,
                    reason="Requirements not met for SOFT→HARD",
                    missing_requirements=missing,
                )
            return PromotionResult(can_promote=True, reason="SOFT→HARD requirements met")

        if target_level == NfClaimLevel.NORM:
            if claim.level != NfClaimLevel.HARD:
                missing.append("must be HARD before promoting to NORM")

            if evidence_gap > self._max_gap_norm:
                missing.append(f"evidence_gap ({evidence_gap}) > max ({self._max_gap_norm})")

            if not claim.value_premise:
                missing.append("no value premise specified")

            if missing:
                return PromotionResult(
                    can_promote=False,
                    reason="Requirements not met for HARD→NORM",
                    missing_requirements=missing,
                )
            return PromotionResult(can_promote=True, reason="HARD→NORM requirements met")

        return PromotionResult(can_promote=False, reason=f"Unknown level: {target_level}")


# =============================================================================
# VelocityController
# =============================================================================


@dataclass
class VelocityResult:
    """Result of velocity check."""

    claim_velocity: float = 0.0  # claims per 100 tokens
    evidence_velocity: float = 0.0  # evidence per 100 tokens
    is_stable: bool = True
    velocity_ratio: float = 0.0  # v_c / v_e

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_velocity": self.claim_velocity,
            "evidence_velocity": self.evidence_velocity,
            "is_stable": self.is_stable,
            "velocity_ratio": self.velocity_ratio,
        }


class VelocityController:
    """Tracks claim/evidence velocity balance.

    From nonfic.md: Stable condition is v_c <= k * v_e
    where k depends on trust level.
    """

    def __init__(self, k_factor: float = 1.5) -> None:
        self._k_factor = k_factor
        self._claims: list[int] = []  # token indices
        self._evidence: list[int] = []  # token indices
        self._current_token: int = 0

    def record_claim(self, token_index: int) -> None:
        """Record a claim at token index."""
        self._claims.append(token_index)
        self._current_token = max(self._current_token, token_index)

    def record_evidence(self, token_index: int) -> None:
        """Record evidence at token index."""
        self._evidence.append(token_index)
        self._current_token = max(self._current_token, token_index)

    def check_velocity(self, window_tokens: int = 500) -> VelocityResult:
        """Check velocity balance in recent window.

        Args:
            window_tokens: Token window to analyze

        Returns:
            VelocityResult with velocities and stability
        """
        cutoff = self._current_token - window_tokens
        recent_claims = sum(1 for t in self._claims if t > cutoff)
        recent_evidence = sum(1 for t in self._evidence if t > cutoff)

        # Normalize to per 100 tokens
        v_c = (recent_claims / window_tokens) * 100 if window_tokens > 0 else 0
        v_e = (recent_evidence / window_tokens) * 100 if window_tokens > 0 else 0

        # Stable if v_c <= k * v_e
        ratio = v_c / v_e if v_e > 0 else float('inf') if v_c > 0 else 0
        is_stable = v_c <= self._k_factor * v_e

        return VelocityResult(
            claim_velocity=v_c,
            evidence_velocity=v_e,
            is_stable=is_stable,
            velocity_ratio=ratio,
        )

    def reset(self) -> None:
        """Reset velocity tracking."""
        self._claims = []
        self._evidence = []
        self._current_token = 0


# =============================================================================
# EpScorer (Epistemic Honesty Perception)
# =============================================================================


@dataclass
class EpResult:
    """Result of Ep (epistemic honesty perception) scoring."""

    governance_visibility: float = 0.0
    claim_evidence_coupling: float = 1.0
    hedge_calibration: float = 1.0
    ep_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "governance_visibility": self.governance_visibility,
            "claim_evidence_coupling": self.claim_evidence_coupling,
            "hedge_calibration": self.hedge_calibration,
            "ep_score": self.ep_score,
        }


class EpScorer:
    """Scores Ep (epistemic honesty perception).

    Composite of:
    - Cp: claim-evidence coupling (low = making claims without evidence)
    - Gv: governance visibility (high = governance artifacts)
    - Hedge calibration (healthy = epistemic hedges, not social hedges)
    """

    def calculate_ep(self, text: str, velocity_result: VelocityResult | None = None) -> EpResult:
        """Calculate Ep score for text."""
        # Governance visibility
        counts = count_categorized_patterns(text, GOVERNANCE_ARTIFACT_PATTERNS)
        gv = 0.0
        for count in counts.values():
            gv += min(count * 0.15, 0.4)
        gv = min(gv, 1.0)

        # Claim-evidence coupling from velocity
        if velocity_result:
            cp = 1.0 - min(velocity_result.velocity_ratio / 3.0, 1.0) if velocity_result.velocity_ratio > 1 else 1.0
        else:
            cp = 1.0

        # Hedge calibration (simple: ratio of causal humility to anxiety hedges)
        epistemic_hedges = count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS)
        anxiety_hedges = count_pattern_matches(text, ANXIETY_HEDGE_PATTERNS)
        total_hedges = epistemic_hedges + anxiety_hedges
        if total_hedges > 0:
            hc = epistemic_hedges / total_hedges
        else:
            hc = 1.0

        # Combined Ep
        ep = (1.0 - gv) * 0.4 + cp * 0.3 + hc * 0.3
        ep = max(0.0, min(1.0, ep))

        return EpResult(
            governance_visibility=gv,
            claim_evidence_coupling=cp,
            hedge_calibration=hc,
            ep_score=ep,
        )


# =============================================================================
# ReScorer (Epistemic Risk Exposure)
# =============================================================================


@dataclass
class ReResult:
    """Result of Re (epistemic risk exposure) scoring."""

    falsifier_count: int = 0
    causal_humility_count: int = 0
    anxiety_hedge_count: int = 0
    re_score: float = 0.5
    below_floor: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "falsifier_count": self.falsifier_count,
            "causal_humility_count": self.causal_humility_count,
            "anxiety_hedge_count": self.anxiety_hedge_count,
            "re_score": self.re_score,
            "below_floor": self.below_floor,
        }


class ReScorer:
    """Scores Re (epistemic risk exposure).

    From nonfic.md:
    Positive: falsifiers, boundary conditions, causal humility, observable predictions
    Negative: anxiety hedges, preemptive defense, inoculation markers
    """

    def __init__(self, floor: float = RE_FLOOR) -> None:
        self._floor = floor

    def calculate_re(self, text: str) -> ReResult:
        """Calculate Re score for text."""
        falsifier_count = count_pattern_matches(text, FALSIFIER_PATTERNS)
        humility_count = count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS)
        anxiety_count = count_pattern_matches(text, ANXIETY_HEDGE_PATTERNS)

        # Also check for preemptive defense (governance artifact)
        gov_counts = count_categorized_patterns(text, GOVERNANCE_ARTIFACT_PATTERNS)
        preemptive = gov_counts.get("preemptive_defense", 0)

        # Re starts at 0.5 (neutral)
        re = 0.5
        re += falsifier_count * 0.08
        re += humility_count * 0.05
        re -= anxiety_count * 0.10
        re -= preemptive * 0.08

        re = max(0.0, min(1.0, re))

        return ReResult(
            falsifier_count=falsifier_count,
            causal_humility_count=humility_count,
            anxiety_hedge_count=anxiety_count,
            re_score=re,
            below_floor=re < self._floor,
        )


# =============================================================================
# HedgeCalibrator
# =============================================================================


@dataclass
class HedgeCalibrationResult:
    """Result of hedge calibration check."""

    epistemic_count: int = 0
    social_count: int = 0
    epistemic_density: float = 0.0
    social_density: float = 0.0
    is_calibrated: bool = True
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "epistemic_count": self.epistemic_count,
            "social_count": self.social_count,
            "epistemic_density": self.epistemic_density,
            "social_density": self.social_density,
            "is_calibrated": self.is_calibrated,
            "issues": self.issues,
        }


class HedgeCalibrator:
    """Classifies hedges as epistemic (appropriate) vs social (anxiety).

    From nonfic.md:
    - Epistemic hedges: healthy range [0.1, 0.4]
    - Social hedges: ceiling 0.1
    """

    def __init__(
        self,
        epistemic_min: float = EPISTEMIC_HEDGE_MIN,
        epistemic_max: float = EPISTEMIC_HEDGE_MAX,
        social_ceiling: float = SOCIAL_HEDGE_CEILING,
    ) -> None:
        self._epistemic_min = epistemic_min
        self._epistemic_max = epistemic_max
        self._social_ceiling = social_ceiling

    def classify_hedges(self, text: str) -> HedgeCalibrationResult:
        """Classify hedges in text.

        Epistemic hedges: causal humility patterns
        Social hedges: anxiety hedge patterns + generic hedges
        """
        word_count = max(len(text.split()), 1)

        epistemic = count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS)
        social = count_pattern_matches(text, ANXIETY_HEDGE_PATTERNS)
        generic_hedges = count_pattern_matches(text, HEDGE_PATTERNS)

        # Generic hedges that are not clearly epistemic are likely social
        social += max(0, generic_hedges - epistemic)

        epistemic_density = epistemic / word_count
        social_density = social / word_count

        issues: list[str] = []
        calibrated = True

        if epistemic_density < self._epistemic_min:
            issues.append(f"epistemic hedges too low ({epistemic_density:.3f} < {self._epistemic_min})")
            # Not a hard fail, just a note

        if epistemic_density > self._epistemic_max:
            issues.append(f"epistemic hedges too high ({epistemic_density:.3f} > {self._epistemic_max})")

        if social_density > self._social_ceiling:
            issues.append(f"social hedges too high ({social_density:.3f} > {self._social_ceiling})")
            calibrated = False

        return HedgeCalibrationResult(
            epistemic_count=epistemic,
            social_count=social,
            epistemic_density=epistemic_density,
            social_density=social_density,
            is_calibrated=calibrated,
            issues=issues,
        )


# =============================================================================
# AhScorer (Alternative Hypothesis Engagement)
# =============================================================================


@dataclass
class AhResult:
    """Result of Ah (alternative hypothesis engagement) scoring."""

    steelman_quality: float = 0.0
    strawman_count: int = 0
    ah_score: float = 0.5
    below_floor: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "steelman_quality": self.steelman_quality,
            "strawman_count": self.strawman_count,
            "ah_score": self.ah_score,
            "below_floor": self.below_floor,
        }


class AhScorer:
    """Scores Ah (alternative hypothesis engagement).

    From nonfic.md: Good engagement means steelmanning alternatives,
    not strawmanning them.
    """

    def __init__(self, floor: float = AH_FLOOR) -> None:
        self._floor = floor

    def calculate_ah(self, text: str) -> AhResult:
        """Calculate Ah score for text."""
        strawman_count = count_pattern_matches(text, STRAWMAN_PATTERNS)

        # Steelman quality: presence of falsifiers and constraint engagement
        falsifier_count = count_pattern_matches(text, FALSIFIER_PATTERNS)
        steelman = min(falsifier_count * 0.15, 0.5)

        # Ah starts at 0.5, improved by steelmen, penalized by strawmen
        ah = 0.5
        ah += steelman
        ah -= strawman_count * 0.15

        ah = max(0.0, min(1.0, ah))

        return AhResult(
            steelman_quality=steelman,
            strawman_count=strawman_count,
            ah_score=ah,
            below_floor=ah < self._floor,
        )


# =============================================================================
# NleadChecker (Normativity Lead)
# =============================================================================


@dataclass
class NleadResult:
    """Result of normativity lead check."""

    first_norm_token: int | None = None
    evidence_mass_at_norm: float = 0.0
    lead_ratio: float = 0.0
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_norm_token": self.first_norm_token,
            "evidence_mass_at_norm": self.evidence_mass_at_norm,
            "lead_ratio": self.lead_ratio,
            "is_valid": self.is_valid,
        }


class NleadChecker:
    """Checks normativity lead (normative claims shouldn't come before evidence).

    From nonfic.md: MIN_EVIDENCE_BEFORE_NORM = 0.4
    40% of evidence should be shown before first normative claim.
    """

    def __init__(self, min_evidence_ratio: float = MIN_EVIDENCE_BEFORE_NORM) -> None:
        self._min_evidence_ratio = min_evidence_ratio

    def check_nlead(
        self,
        text: str,
        total_evidence_count: int = 0,
        evidence_before_norm: int = 0,
    ) -> NleadResult:
        """Check normativity lead in text.

        Args:
            text: Text to check
            total_evidence_count: Total evidence pieces planned
            evidence_before_norm: Evidence shown before first normative

        Returns:
            NleadResult
        """
        # Find first normative pattern
        words = text.split()
        first_norm_token = None

        for i, word in enumerate(words):
            for pattern in NORMATIVE_PATTERNS:
                if pattern.search(word) or pattern.search(" ".join(words[max(0, i-2):i+2])):
                    first_norm_token = i
                    break
            if first_norm_token is not None:
                break

        if first_norm_token is None:
            # No normative claim found
            return NleadResult(is_valid=True)

        # Calculate evidence ratio
        if total_evidence_count > 0:
            ratio = evidence_before_norm / total_evidence_count
        else:
            ratio = 0.0

        is_valid = ratio >= self._min_evidence_ratio

        return NleadResult(
            first_norm_token=first_norm_token,
            evidence_mass_at_norm=ratio,
            lead_ratio=first_norm_token / len(words) if words else 0.0,
            is_valid=is_valid,
        )


# =============================================================================
# NonfictionSubRegime
# =============================================================================


class NonfictionSubRegime(str, Enum):
    """Sub-regimes within nonfiction."""

    EXPOSITION = "exposition"
    INFERENCE = "inference"
    SYNTHESIS = "synthesis"
    NORMATIVE = "normative"


# =============================================================================
# NonfictionFailureDetector
# =============================================================================


class NonfictionFailureMode(str, Enum):
    """Failure modes for nonfiction writing."""

    PROPAGANDA = "propaganda"  # Advocacy disguised as nonfiction
    COMMITTEE = "committee"  # Balance theater, governance visible
    HOT_TAKE = "hot_take"  # Claims outpace evidence
    SYNTHESIS_ADDICTION = "synthesis_addiction"  # Never reaches conclusions
    ACADEMIC_THEATER = "academic_theater"  # Empty rigor, no content
    ADVOCACY_DRIFT = "advocacy_drift"  # Normative claims without grounding


@dataclass
class NonfictionMetrics:
    """Aggregated nonfiction metrics for failure detection."""

    ep_score: float = 1.0
    re_score: float = 0.5
    ah_score: float = 0.5
    gv_score: float = 0.0
    velocity_ratio: float = 1.0
    normative_density: float = 0.0
    conclusion_strength: float = 0.5


@dataclass
class FailureModeResult:
    """Result of failure mode detection."""

    detected_modes: list[NonfictionFailureMode] = field(default_factory=list)
    severity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_modes": [m.value for m in self.detected_modes],
            "severity": self.severity,
        }


class NonfictionFailureDetector:
    """Detects nonfiction failure modes.

    From nonfic.md: 6 failure modes that indicate governance visibility
    or epistemic dishonesty.
    """

    def detect_failures(self, metrics: NonfictionMetrics) -> FailureModeResult:
        """Detect failure modes from aggregated metrics."""
        modes: list[NonfictionFailureMode] = []

        # PROPAGANDA: low Re, high normative density
        if metrics.re_score < 0.4 and metrics.normative_density > 0.3:
            modes.append(NonfictionFailureMode.PROPAGANDA)

        # COMMITTEE: high governance visibility
        if metrics.gv_score > 0.4:
            modes.append(NonfictionFailureMode.COMMITTEE)

        # HOT_TAKE: velocity ratio way too high
        if metrics.velocity_ratio > 3.0:
            modes.append(NonfictionFailureMode.HOT_TAKE)

        # SYNTHESIS_ADDICTION: low conclusion strength, cycling
        if metrics.conclusion_strength < 0.3 and metrics.ep_score > 0.5:
            modes.append(NonfictionFailureMode.SYNTHESIS_ADDICTION)

        # ACADEMIC_THEATER: high Ep but low content signal
        if metrics.ep_score > 0.7 and metrics.ah_score < 0.3:
            modes.append(NonfictionFailureMode.ACADEMIC_THEATER)

        # ADVOCACY_DRIFT: high normative density without grounding
        if metrics.normative_density > 0.2 and metrics.re_score < 0.5:
            modes.append(NonfictionFailureMode.ADVOCACY_DRIFT)

        severity = len(modes) * 0.2
        severity = min(severity, 1.0)

        return FailureModeResult(detected_modes=modes, severity=severity)
