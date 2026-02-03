"""
Writing Regime — Affect regime system with comedy/tragedy/sincerity/drama.

RegimeVector: Continuous weights for 5 affect modes (sum to 1.0).
RegimeHysteresis: Rate-limited regime transitions with dwell enforcement.
RpScorer: Perceived risk scoring for comedy (hedge/self-ref/committee detection).
TragedyConstraints: Meaning-lag enforcement (explanations must follow suffering).
SincerityTracker: Consistency tracking (anti-manifesto detection).
DramaConstraints: Stakes protection (comedy must avoid dramatic anchors).
MixerConfig: Hybrid safety buffers for regime blending.

Key insight from fic.md: comedy-first because fastest feedback loop.
Rp (perceived risk) is the load-bearing variable for comedy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .writing_patterns import (
    APOLOGY_META_PATTERNS,
    COMMITTEE_PATTERNS,
    HEDGE_PATTERNS,
    MEANING_WORD_PATTERNS,
    SELF_REFERENCE_PATTERNS,
    check_any_pattern,
    count_pattern_matches,
)


# =============================================================================
# AffectRegime enum
# =============================================================================


class AffectRegime(str, Enum):
    """The five affect regimes from fic.md."""

    COMEDY = "comedy"
    TRAGEDY = "tragedy"
    SINCERITY = "sincerity"
    DRAMA = "drama"
    NEUTRAL = "neutral"


# =============================================================================
# RegimeVector
# =============================================================================


@dataclass
class RegimeVector:
    """5-weight regime vector representing affect blend.

    Weights should sum to 1.0 (normalized). Dominant regime is the one
    with highest weight.
    """

    w_c: float = 0.0  # comedy
    w_t: float = 0.0  # tragedy
    w_s: float = 0.0  # sincerity
    w_d: float = 0.0  # drama
    w_n: float = 1.0  # neutral

    def dominant(self) -> AffectRegime:
        """Return the regime with highest weight."""
        weights = [
            (self.w_c, AffectRegime.COMEDY),
            (self.w_t, AffectRegime.TRAGEDY),
            (self.w_s, AffectRegime.SINCERITY),
            (self.w_d, AffectRegime.DRAMA),
            (self.w_n, AffectRegime.NEUTRAL),
        ]
        return max(weights, key=lambda x: x[0])[1]

    def normalize(self) -> RegimeVector:
        """Return a new vector with weights normalized to sum=1.0."""
        total = self.w_c + self.w_t + self.w_s + self.w_d + self.w_n
        if total <= 0:
            return RegimeVector.neutral()
        return RegimeVector(
            w_c=self.w_c / total,
            w_t=self.w_t / total,
            w_s=self.w_s / total,
            w_d=self.w_d / total,
            w_n=self.w_n / total,
        )

    @classmethod
    def neutral(cls) -> RegimeVector:
        """Return a neutral regime vector."""
        return cls(w_c=0.0, w_t=0.0, w_s=0.0, w_d=0.0, w_n=1.0)

    @classmethod
    def comedy(cls, weight: float = 1.0) -> RegimeVector:
        """Return a comedy-dominant vector."""
        return cls(w_c=weight, w_n=1.0 - weight).normalize()

    @classmethod
    def tragedy(cls, weight: float = 1.0) -> RegimeVector:
        """Return a tragedy-dominant vector."""
        return cls(w_t=weight, w_n=1.0 - weight).normalize()

    @classmethod
    def sincerity(cls, weight: float = 1.0) -> RegimeVector:
        """Return a sincerity-dominant vector."""
        return cls(w_s=weight, w_n=1.0 - weight).normalize()

    @classmethod
    def drama(cls, weight: float = 1.0) -> RegimeVector:
        """Return a drama-dominant vector."""
        return cls(w_d=weight, w_n=1.0 - weight).normalize()

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> RegimeVector:
        return cls(
            w_c=data.get("w_c", data.get("comedy", 0.0)),
            w_t=data.get("w_t", data.get("tragedy", 0.0)),
            w_s=data.get("w_s", data.get("sincerity", 0.0)),
            w_d=data.get("w_d", data.get("drama", 0.0)),
            w_n=data.get("w_n", data.get("neutral", 0.0)),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "comedy": self.w_c,
            "tragedy": self.w_t,
            "sincerity": self.w_s,
            "drama": self.w_d,
            "neutral": self.w_n,
        }

    def distance(self, other: RegimeVector) -> float:
        """Euclidean distance to another vector."""
        import math
        return math.sqrt(
            (self.w_c - other.w_c) ** 2
            + (self.w_t - other.w_t) ** 2
            + (self.w_s - other.w_s) ** 2
            + (self.w_d - other.w_d) ** 2
            + (self.w_n - other.w_n) ** 2
        )


# =============================================================================
# RegimeHysteresis
# =============================================================================


@dataclass
class RegimeHysteresisConfig:
    """Configuration for regime hysteresis."""

    min_dwell_tokens: int = 200  # tokens before regime can shift (200-800)
    switch_cost: float = 0.8  # confidence threshold for switch (0.7-0.9)
    cooldown_tokens: int = 100  # wait after hard shift (100-300)
    max_shift_rate: float = 0.01  # max weight change per token (0.005-0.02)
    thrash_threshold: float = 2.0  # shifts per 1000 tokens


@dataclass
class RegimeHysteresisState:
    """Internal state for regime hysteresis."""

    current_vector: RegimeVector = field(default_factory=RegimeVector.neutral)
    dwell_counter: int = 0
    cooldown_counter: int = 0
    shift_history: list[int] = field(default_factory=list)  # token indices of shifts
    total_tokens: int = 0


class RegimeHysteresis:
    """Rate-limited regime transitions with dwell enforcement.

    Prevents thrashing between regimes. Enforces:
    - Minimum dwell time before regime can change
    - Cooldown after regime change
    - Maximum rate of weight change
    """

    def __init__(self, config: RegimeHysteresisConfig | None = None) -> None:
        self._config = config or RegimeHysteresisConfig()
        self._state = RegimeHysteresisState()

    def update(
        self,
        signal: RegimeVector,
        confidence: float,
        tokens_elapsed: int = 1,
    ) -> RegimeVector:
        """Update regime vector based on incoming signal.

        Args:
            signal: New regime signal (from content analysis)
            confidence: Confidence in the signal (0.0-1.0)
            tokens_elapsed: Tokens since last update

        Returns:
            Updated regime vector (rate-limited)
        """
        self._state.total_tokens += tokens_elapsed
        self._state.dwell_counter += tokens_elapsed

        # If in cooldown, just decrement and return current
        if self._state.cooldown_counter > 0:
            self._state.cooldown_counter = max(0, self._state.cooldown_counter - tokens_elapsed)
            return self._state.current_vector

        current = self._state.current_vector
        signal_norm = signal.normalize()

        # Check if dominant regime is changing
        current_dominant = current.dominant()
        signal_dominant = signal_norm.dominant()
        regime_changing = current_dominant != signal_dominant

        # If regime changing, check dwell and confidence requirements
        if regime_changing:
            if self._state.dwell_counter < self._config.min_dwell_tokens:
                # Not enough dwell time, resist change
                return current
            if confidence < self._config.switch_cost:
                # Not confident enough to switch
                return current

            # Allow regime change, enter cooldown
            self._state.cooldown_counter = self._config.cooldown_tokens
            self._state.dwell_counter = 0
            self._state.shift_history.append(self._state.total_tokens)

        # Calculate rate-limited weight shift
        max_shift = self._config.max_shift_rate * tokens_elapsed
        new_vector = self._rate_limit_shift(current, signal_norm, max_shift)
        self._state.current_vector = new_vector.normalize()

        return self._state.current_vector

    def _rate_limit_shift(
        self,
        current: RegimeVector,
        target: RegimeVector,
        max_shift: float,
    ) -> RegimeVector:
        """Move current toward target, limited by max_shift."""
        dist = current.distance(target)
        if dist <= max_shift:
            return target

        ratio = max_shift / dist if dist > 0 else 1.0
        return RegimeVector(
            w_c=current.w_c + ratio * (target.w_c - current.w_c),
            w_t=current.w_t + ratio * (target.w_t - current.w_t),
            w_s=current.w_s + ratio * (target.w_s - current.w_s),
            w_d=current.w_d + ratio * (target.w_d - current.w_d),
            w_n=current.w_n + ratio * (target.w_n - current.w_n),
        )

    def thrash_rate(self, window_tokens: int = 1000) -> float:
        """Calculate shifts per window_tokens in recent history."""
        if not self._state.shift_history:
            return 0.0

        cutoff = self._state.total_tokens - window_tokens
        recent_shifts = sum(1 for t in self._state.shift_history if t > cutoff)
        return recent_shifts * (1000.0 / window_tokens)

    def is_thrashing(self) -> bool:
        """Check if regime is thrashing."""
        return self.thrash_rate() >= self._config.thrash_threshold

    def reset(self, vector: RegimeVector | None = None) -> None:
        """Reset hysteresis state."""
        self._state = RegimeHysteresisState(
            current_vector=vector or RegimeVector.neutral()
        )

    @property
    def current_vector(self) -> RegimeVector:
        return self._state.current_vector

    @property
    def dominant(self) -> AffectRegime:
        return self._state.current_vector.dominant()


# =============================================================================
# RpScorer (Perceived Risk for Comedy)
# =============================================================================

# Constants from fic.md
RP_FLOOR: float = 0.6
HEDGE_PENALTY: float = 0.05
SELF_REF_PENALTY: float = 0.15
COMMITTEE_PENALTY: float = 0.12
META_KILL_PENALTY: float = 0.30


@dataclass
class RpResult:
    """Result of Rp (perceived risk) scoring."""

    hedge_count: int = 0
    self_ref_count: int = 0
    committee_count: int = 0
    meta_kill_found: bool = False
    rp_score: float = 1.0
    below_floor: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "hedge_count": self.hedge_count,
            "self_ref_count": self.self_ref_count,
            "committee_count": self.committee_count,
            "meta_kill_found": self.meta_kill_found,
            "rp_score": self.rp_score,
            "below_floor": self.below_floor,
        }


class RpScorer:
    """Scores Rp (perceived risk) for comedy regime.

    From fic.md: Rp is the load-bearing variable for comedy.
    High Rp = audience feels uncertain about outcomes = comedy can land.
    Low Rp = "pre-cleared" feeling = comedy dies.

    Rp starts at 1.0 and decrements per pattern:
    - hedges: -0.05 each
    - self-reference: -0.15 each (governance leak)
    - committee patterns: -0.12 each
    - meta/apology patterns: -0.30 (hard kill)
    """

    def __init__(self, floor: float = RP_FLOOR) -> None:
        self._floor = floor

    def calculate_rp(self, text: str) -> RpResult:
        """Calculate Rp score for text."""
        hedge_count = count_pattern_matches(text, HEDGE_PATTERNS)
        self_ref_count = count_pattern_matches(text, SELF_REFERENCE_PATTERNS)
        committee_count = count_pattern_matches(text, COMMITTEE_PATTERNS)
        meta_kill = check_any_pattern(text, APOLOGY_META_PATTERNS)

        rp = 1.0
        rp -= hedge_count * HEDGE_PENALTY
        rp -= self_ref_count * SELF_REF_PENALTY
        rp -= committee_count * COMMITTEE_PENALTY
        if meta_kill:
            rp -= META_KILL_PENALTY

        rp = max(0.0, rp)

        return RpResult(
            hedge_count=hedge_count,
            self_ref_count=self_ref_count,
            committee_count=committee_count,
            meta_kill_found=meta_kill,
            rp_score=rp,
            below_floor=rp < self._floor,
        )


# =============================================================================
# TragedyConstraints (Meaning-Lag)
# =============================================================================

# Meaning words must lag suffering by this many tokens
MIN_CONSEQUENCE_TOKENS: int = 50
# Maximum meaning word density per 100 tokens
MEANING_DENSITY_CAP: float = 3.0


@dataclass
class MeaningLagResult:
    """Result of meaning-lag check."""

    meaning_word_count: int = 0
    meaning_density: float = 0.0  # per 100 tokens
    exceeds_density_cap: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "meaning_word_count": self.meaning_word_count,
            "meaning_density": self.meaning_density,
            "exceeds_density_cap": self.exceeds_density_cap,
        }


class TragedyConstraints:
    """Enforces tragedy constraints: meaning-lag, no-rescue.

    From fic.md: In tragedy, meaning must lag suffering.
    Explanatory/interpretive content too soon kills the tragedy.
    """

    def __init__(
        self,
        min_consequence_tokens: int = MIN_CONSEQUENCE_TOKENS,
        density_cap: float = MEANING_DENSITY_CAP,
    ) -> None:
        self._min_consequence_tokens = min_consequence_tokens
        self._density_cap = density_cap

    def check_meaning_lag(self, text: str, consequence_tokens: int = 0) -> MeaningLagResult:
        """Check for meaning-word density.

        Args:
            text: Text to check
            consequence_tokens: Tokens of consequence already shown (not used in basic check)

        Returns:
            MeaningLagResult with density metrics
        """
        word_count = max(len(text.split()), 1)
        meaning_count = count_pattern_matches(text, MEANING_WORD_PATTERNS)

        # Density per 100 words
        density = (meaning_count / word_count) * 100

        return MeaningLagResult(
            meaning_word_count=meaning_count,
            meaning_density=density,
            exceeds_density_cap=density > self._density_cap,
        )

    def is_meaning_allowed(self, consequence_tokens: int) -> bool:
        """Check if meaning-words are allowed given consequence shown."""
        return consequence_tokens >= self._min_consequence_tokens


# =============================================================================
# SincerityTracker
# =============================================================================

# Anti-manifesto patterns: sincerity shouldn't sound like a manifesto
MANIFESTO_PATTERNS = [
    r"\bI believe\b.*\bI believe\b",  # repeated belief statements
    r"\bwe must\b.*\bwe must\b",  # repeated exhortation
    r"\bI will\b.*\bI will\b",  # repeated commitment
]


@dataclass
class ConsistencyResult:
    """Result of sincerity consistency check."""

    manifesto_detected: bool = False
    consistency_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifesto_detected": self.manifesto_detected,
            "consistency_issues": self.consistency_issues,
        }


class SincerityTracker:
    """Tracks sincerity consistency over conversation.

    From fic.md: Sincerity must not feel performative.
    Manifestos, repeated commitments, and theatrical vulnerability
    all kill sincerity.
    """

    def __init__(self) -> None:
        self._history: list[str] = []

    def check_consistency(
        self,
        current: str,
        history: list[str] | None = None,
    ) -> ConsistencyResult:
        """Check current text for sincerity consistency.

        Args:
            current: Current text being generated
            history: Previous texts (if None, uses internal history)

        Returns:
            ConsistencyResult with manifesto detection
        """
        import re

        texts = history if history is not None else self._history
        issues: list[str] = []
        manifesto = False

        # Check for manifesto patterns in current text
        for pattern in MANIFESTO_PATTERNS:
            if re.search(pattern, current, re.IGNORECASE | re.DOTALL):
                manifesto = True
                issues.append(f"Manifesto pattern detected: {pattern}")

        # Update internal history
        if history is None:
            self._history.append(current)

        return ConsistencyResult(
            manifesto_detected=manifesto,
            consistency_issues=issues,
        )

    def reset(self) -> None:
        """Reset history."""
        self._history = []


# =============================================================================
# DramaConstraints (Stakes Protection)
# =============================================================================


@dataclass
class StakesProtectionResult:
    """Result of stakes protection check."""

    comedy_targets_stakes: bool = False
    stakes_anchors_at_risk: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "comedy_targets_stakes": self.comedy_targets_stakes,
            "stakes_anchors_at_risk": self.stakes_anchors_at_risk,
        }


class DramaConstraints:
    """Enforces drama constraints: stakes protection.

    From fic.md: Comedy must not target things the drama takes seriously.
    When drama weight > 0.4, comedy should avoid stakes anchors.
    """

    def __init__(self, drama_threshold: float = 0.4) -> None:
        self._drama_threshold = drama_threshold

    def check_stakes_deflation(
        self,
        comedy_target: str,
        stakes_anchors: list[str],
        drama_weight: float,
    ) -> StakesProtectionResult:
        """Check if comedy targets something drama takes seriously.

        Args:
            comedy_target: The target of the comedy (topic being joked about)
            stakes_anchors: Topics the drama takes seriously
            drama_weight: Current drama weight (0.0-1.0)

        Returns:
            StakesProtectionResult
        """
        if drama_weight < self._drama_threshold:
            return StakesProtectionResult()

        # Check if comedy target overlaps with stakes anchors
        target_lower = comedy_target.lower()
        at_risk = [
            anchor for anchor in stakes_anchors
            if anchor.lower() in target_lower or target_lower in anchor.lower()
        ]

        return StakesProtectionResult(
            comedy_targets_stakes=len(at_risk) > 0,
            stakes_anchors_at_risk=at_risk,
        )


# =============================================================================
# MixerConfig (Hybrid Safety Buffers)
# =============================================================================


@dataclass
class MixerConfig:
    """Configuration for regime mixing safety buffers."""

    # Sincerity buffer: suppress comedy for N tokens after sincerity
    sincerity_buffer_tokens: int = 50

    # Tragedy meaning lag: block explanatory content during lag
    tragedy_meaning_lag_tokens: int = 50

    # Stakes protection: comedy avoids stakes anchors when drama > threshold
    stakes_protection_threshold: float = 0.4


@dataclass
class MixerState:
    """State for mixer buffers."""

    # Start with large values so buffers are not active initially
    tokens_since_sincerity: int = 10000
    tokens_since_consequence: int = 10000
    active_stakes_anchors: list[str] = field(default_factory=list)


class RegimeMixer:
    """Manages hybrid regime safety buffers.

    Prevents problematic regime combinations:
    - Comedy too soon after sincerity
    - Meaning during tragedy lag
    - Comedy targeting drama stakes
    """

    def __init__(self, config: MixerConfig | None = None) -> None:
        self._config = config or MixerConfig()
        self._state = MixerState()

    def comedy_allowed(self) -> bool:
        """Check if comedy is currently allowed."""
        # Not allowed if still in sincerity buffer
        if self._state.tokens_since_sincerity < self._config.sincerity_buffer_tokens:
            return False
        return True

    def meaning_allowed(self) -> bool:
        """Check if meaning-words are allowed (tragedy lag)."""
        return self._state.tokens_since_consequence >= self._config.tragedy_meaning_lag_tokens

    def advance_tokens(
        self,
        tokens: int,
        sincerity_event: bool = False,
        consequence_event: bool = False,
    ) -> None:
        """Advance token counters."""
        if sincerity_event:
            self._state.tokens_since_sincerity = 0
        else:
            self._state.tokens_since_sincerity += tokens

        if consequence_event:
            self._state.tokens_since_consequence = 0
        else:
            self._state.tokens_since_consequence += tokens

    def set_stakes_anchors(self, anchors: list[str]) -> None:
        """Set active stakes anchors for drama."""
        self._state.active_stakes_anchors = list(anchors)

    def check_comedy_target(
        self,
        target: str,
        drama_weight: float,
    ) -> StakesProtectionResult:
        """Check if comedy target is safe given current drama."""
        if drama_weight < self._config.stakes_protection_threshold:
            return StakesProtectionResult()

        target_lower = target.lower()
        at_risk = [
            anchor for anchor in self._state.active_stakes_anchors
            if anchor.lower() in target_lower or target_lower in anchor.lower()
        ]
        return StakesProtectionResult(
            comedy_targets_stakes=len(at_risk) > 0,
            stakes_anchors_at_risk=at_risk,
        )

    def reset(self) -> None:
        """Reset mixer state."""
        self._state = MixerState()


# =============================================================================
# NeutralTransitionGuard
# =============================================================================


@dataclass
class NeutralTransitionGuardConfig:
    """Configuration for guarding transitions out of Neutral.

    Neutral → Regime transitions require minimum signal duration or explicit trigger.
    Otherwise, a single joke-shaped token or factual claim yanks the system
    out of Neutral prematurely.
    """

    # Minimum tokens of sustained signal before transition allowed
    min_signal_tokens: int = 30

    # If True, user can explicitly request a regime to bypass min_signal_tokens
    explicit_trigger_override: bool = True

    # Regime must score above this to exit neutral
    confidence_threshold: float = 0.4


DEFAULT_NEUTRAL_GUARD = NeutralTransitionGuardConfig()


@dataclass
class NeutralTransitionGuardState:
    """State for the neutral transition guard."""

    # Tokens since last regime signal above threshold
    signal_tokens: int = 0

    # Which regime has been signaling (if any)
    signaling_regime: AffectRegime | None = None

    # Has user explicitly requested a regime?
    explicit_request: bool = False


class NeutralTransitionGuard:
    """Guards transitions out of Neutral regime.

    Neutral is the system's idle loop. Most language isn't doing heavy
    authorial work - it's connective tissue. This guard prevents premature
    exits from Neutral based on single tokens.

    The invariant: "Neutral should feel boring, safe, and forgettable."
    """

    def __init__(self, config: NeutralTransitionGuardConfig | None = None):
        self._config = config or DEFAULT_NEUTRAL_GUARD
        self._state = NeutralTransitionGuardState()

    def observe_signal(
        self,
        regime: AffectRegime,
        confidence: float,
    ) -> None:
        """Observe a regime signal and update internal state."""
        if regime == AffectRegime.NEUTRAL:
            # Reset signal tracking if we're signaling neutral
            self._state.signal_tokens = 0
            self._state.signaling_regime = None
            return

        if confidence < self._config.confidence_threshold:
            # Signal too weak
            self._state.signal_tokens = 0
            self._state.signaling_regime = None
            return

        if self._state.signaling_regime == regime:
            # Same regime signaling - accumulate
            self._state.signal_tokens += 1
        else:
            # Different regime - reset
            self._state.signal_tokens = 1
            self._state.signaling_regime = regime

    def should_transition(self, current: AffectRegime, target: AffectRegime) -> bool:
        """Check if transition from current to target is allowed.

        Only guards transitions OUT of Neutral. Other transitions always allowed.
        """
        if current != AffectRegime.NEUTRAL:
            # Not in Neutral - no guard
            return True

        if target == AffectRegime.NEUTRAL:
            # Staying in Neutral - always allowed
            return True

        # Transitioning OUT of Neutral
        if self._state.explicit_request and self._config.explicit_trigger_override:
            # User explicitly requested a regime
            return True

        # Check if signal has been sustained long enough
        return self._state.signal_tokens >= self._config.min_signal_tokens

    def set_explicit_request(self, regime: AffectRegime) -> None:
        """Mark that user has explicitly requested a regime."""
        if regime != AffectRegime.NEUTRAL:
            self._state.explicit_request = True
            self._state.signaling_regime = regime

    def clear_explicit_request(self) -> None:
        """Clear explicit request (e.g., when returning to neutral)."""
        self._state.explicit_request = False

    def reset(self) -> None:
        """Reset guard state."""
        self._state = NeutralTransitionGuardState()


# =============================================================================
# What stays active in Neutral
# =============================================================================

# From neutral.md section 10.3:
# Active in Neutral:
#   - Governance invisibility (universal)
#   - No committee texture
#   - No visible negotiation
#   - Exit shape constraints (no "hope this helps")
#   - Meta-invariant (don't solve unfelt problems)
#   - Basic tone consistency
#
# Inactive in Neutral:
#   - Regime-specific load-bearing variables (Rp, Ep, etc.)
#   - Phase-lock timing constraints
#   - Commitment tracking
#   - Regime-specific tone collisions
#   - Hybrid safety buffers
#   - Rp / Ep / Ap scoring

NEUTRAL_ACTIVE_CONSTRAINTS = frozenset([
    "governance_invisibility",
    "no_committee_texture",
    "no_visible_negotiation",
    "exit_shape",
    "meta_invariant",
    "basic_tone_consistency",
])

NEUTRAL_INACTIVE_CONSTRAINTS = frozenset([
    "load_bearing_variables",
    "phase_lock",
    "commitment_tracking",
    "regime_tone_collisions",
    "hybrid_safety_buffers",
    "regime_scoring",
])


def is_active_in_neutral(constraint: str) -> bool:
    """Check if a constraint is active in Neutral mode."""
    return constraint in NEUTRAL_ACTIVE_CONSTRAINTS


def is_inactive_in_neutral(constraint: str) -> bool:
    """Check if a constraint is inactive in Neutral mode."""
    return constraint in NEUTRAL_INACTIVE_CONSTRAINTS
