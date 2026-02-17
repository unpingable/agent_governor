# SPDX-License-Identifier: Apache-2.0
"""
Writing Tone — 6-axis tone modulation layer.

ToneVector: 6D continuous control target for text generation.
ToneEnvelope: Per-regime min/max bounds on each dimension.
ToneCollision: Hard blocks for regime-tone incompatibilities.
ToneStabilityController: Rate-limited tone drift.
ToneDriftScorer: Combined envelope + institutional marker scoring.

Key distinction from nonfiction_governor.ToneProfile (28 dimensions):
ToneProfile is post-hoc text analysis. ToneVector is a control target.
They complement, don't replace.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .writing_patterns import (
    COMMITTEE_PATTERNS,
    INSTITUTIONAL_MARKER_PATTERNS,
    count_categorized_patterns,
    count_pattern_matches,
)


# =============================================================================
# ToneVector
# =============================================================================


@dataclass
class ToneVector:
    """6D tone vector for generation control.

    All values in [0.0, 1.0]:
    - formality: 0.0 = conversational, 1.0 = formal
    - temperature: 0.0 = cool/detached, 1.0 = warm/personal
    - density: 0.0 = sparse, 1.0 = compressed
    - velocity: 0.0 = deliberate, 1.0 = fast
    - distance: 0.0 = intimate, 1.0 = observational
    - certainty: 0.0 = exploratory, 1.0 = declarative
    """

    formality: float = 0.5
    temperature: float = 0.5
    density: float = 0.5
    velocity: float = 0.5
    distance: float = 0.5
    certainty: float = 0.5

    def clamp(self) -> ToneVector:
        """Return a new ToneVector with all values clamped to [0.0, 1.0]."""
        return ToneVector(
            formality=max(0.0, min(1.0, self.formality)),
            temperature=max(0.0, min(1.0, self.temperature)),
            density=max(0.0, min(1.0, self.density)),
            velocity=max(0.0, min(1.0, self.velocity)),
            distance=max(0.0, min(1.0, self.distance)),
            certainty=max(0.0, min(1.0, self.certainty)),
        )

    def euclidean_distance(self, other: ToneVector) -> float:
        """Euclidean distance to another ToneVector."""
        return math.sqrt(
            (self.formality - other.formality) ** 2
            + (self.temperature - other.temperature) ** 2
            + (self.density - other.density) ** 2
            + (self.velocity - other.velocity) ** 2
            + (self.distance - other.distance) ** 2
            + (self.certainty - other.certainty) ** 2
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "formality": self.formality,
            "temperature": self.temperature,
            "density": self.density,
            "velocity": self.velocity,
            "distance": self.distance,
            "certainty": self.certainty,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> ToneVector:
        return cls(
            formality=data.get("formality", 0.5),
            temperature=data.get("temperature", 0.5),
            density=data.get("density", 0.5),
            velocity=data.get("velocity", 0.5),
            distance=data.get("distance", 0.5),
            certainty=data.get("certainty", 0.5),
        )

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.formality,
            self.temperature,
            self.density,
            self.velocity,
            self.distance,
            self.certainty,
        )


# =============================================================================
# ToneEnvelope
# =============================================================================


@dataclass
class ToneEnvelope:
    """Per-regime min/max bounds on each tone dimension.

    Each dimension is a (min, max) tuple.
    """

    formality: tuple[float, float] = (0.0, 1.0)
    temperature: tuple[float, float] = (0.0, 1.0)
    density: tuple[float, float] = (0.0, 1.0)
    velocity: tuple[float, float] = (0.0, 1.0)
    distance: tuple[float, float] = (0.0, 1.0)
    certainty: tuple[float, float] = (0.0, 1.0)

    def contains(self, tone: ToneVector) -> bool:
        """Return True if tone is within all dimension bounds."""
        return (
            self.formality[0] <= tone.formality <= self.formality[1]
            and self.temperature[0] <= tone.temperature <= self.temperature[1]
            and self.density[0] <= tone.density <= self.density[1]
            and self.velocity[0] <= tone.velocity <= self.velocity[1]
            and self.distance[0] <= tone.distance <= self.distance[1]
            and self.certainty[0] <= tone.certainty <= self.certainty[1]
        )

    def center(self) -> ToneVector:
        """Return the center point of the envelope."""
        return ToneVector(
            formality=(self.formality[0] + self.formality[1]) / 2,
            temperature=(self.temperature[0] + self.temperature[1]) / 2,
            density=(self.density[0] + self.density[1]) / 2,
            velocity=(self.velocity[0] + self.velocity[1]) / 2,
            distance=(self.distance[0] + self.distance[1]) / 2,
            certainty=(self.certainty[0] + self.certainty[1]) / 2,
        )

    def clip(self, tone: ToneVector) -> ToneVector:
        """Clip tone to the nearest boundary of the envelope."""

        def _clip(val: float, bounds: tuple[float, float]) -> float:
            return max(bounds[0], min(bounds[1], val))

        return ToneVector(
            formality=_clip(tone.formality, self.formality),
            temperature=_clip(tone.temperature, self.temperature),
            density=_clip(tone.density, self.density),
            velocity=_clip(tone.velocity, self.velocity),
            distance=_clip(tone.distance, self.distance),
            certainty=_clip(tone.certainty, self.certainty),
        )

    def to_dict(self) -> dict[str, tuple[float, float]]:
        return {
            "formality": self.formality,
            "temperature": self.temperature,
            "density": self.density,
            "velocity": self.velocity,
            "distance": self.distance,
            "certainty": self.certainty,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToneEnvelope:
        return cls(
            formality=tuple(data.get("formality", (0.0, 1.0))),
            temperature=tuple(data.get("temperature", (0.0, 1.0))),
            density=tuple(data.get("density", (0.0, 1.0))),
            velocity=tuple(data.get("velocity", (0.0, 1.0))),
            distance=tuple(data.get("distance", (0.0, 1.0))),
            certainty=tuple(data.get("certainty", (0.0, 1.0))),
        )


# =============================================================================
# Regime envelope constants
# =============================================================================

# Comedy: fast velocity critical for timing
COMEDY_ENVELOPE = ToneEnvelope(
    formality=(0.1, 0.5),
    temperature=(0.3, 0.7),
    density=(0.2, 0.5),
    velocity=(0.6, 0.9),  # CRITICAL FOR TIMING
    distance=(0.3, 0.6),
    certainty=(0.4, 0.7),
)

# Tragedy: slow velocity for meaning-lag
TRAGEDY_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.3, 0.6),
    density=(0.2, 0.5),
    velocity=(0.1, 0.4),  # SLOW
    distance=(0.5, 0.8),
    certainty=(0.2, 0.5),
)

# Sincerity: moderate across all
SINCERITY_ENVELOPE = ToneEnvelope(
    formality=(0.2, 0.6),
    temperature=(0.4, 0.8),
    density=(0.2, 0.5),
    velocity=(0.3, 0.6),
    distance=(0.2, 0.5),
    certainty=(0.4, 0.7),
)

# Drama: high stakes requires commitment
DRAMA_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.4, 0.7),
    density=(0.3, 0.6),
    velocity=(0.3, 0.6),
    distance=(0.3, 0.6),
    certainty=(0.5, 0.8),
)

# Nonfiction: cool, formal, moderate certainty
NONFICTION_ENVELOPE = ToneEnvelope(
    formality=(0.5, 0.8),
    temperature=(0.2, 0.5),
    density=(0.4, 0.7),
    velocity=(0.3, 0.6),
    distance=(0.5, 0.8),
    certainty=(0.4, 0.7),
)

# Research: formal, cool, exploratory certainty
RESEARCH_ENVELOPE = ToneEnvelope(
    formality=(0.6, 0.9),
    temperature=(0.1, 0.4),
    density=(0.6, 0.9),
    velocity=(0.2, 0.5),
    distance=(0.6, 0.9),
    certainty=(0.2, 0.6),
)

# Instruction: confident certainty, moderate else
INSTRUCTION_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.3, 0.6),
    density=(0.3, 0.6),
    velocity=(0.4, 0.7),
    distance=(0.4, 0.7),
    certainty=(0.6, 0.9),  # CONFIDENT
)

# Debugging: diagnostic distance, cool temperature
DEBUGGING_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.2, 0.5),
    density=(0.3, 0.6),
    velocity=(0.3, 0.6),
    distance=(0.5, 0.8),
    certainty=(0.3, 0.6),
)

# Negotiation: balanced, moderate certainty
NEGOTIATION_ENVELOPE = ToneEnvelope(
    formality=(0.4, 0.7),
    temperature=(0.4, 0.6),
    density=(0.3, 0.6),
    velocity=(0.3, 0.5),
    distance=(0.4, 0.6),
    certainty=(0.3, 0.6),
)

# Advocacy: warmer, more certain
ADVOCACY_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.5, 0.8),
    density=(0.3, 0.6),
    velocity=(0.4, 0.7),
    distance=(0.3, 0.6),
    certainty=(0.5, 0.8),
)

# Marketing: warm, fast, aspirational
MARKETING_ENVELOPE = ToneEnvelope(
    formality=(0.2, 0.6),
    temperature=(0.5, 0.8),
    density=(0.2, 0.5),
    velocity=(0.5, 0.8),
    distance=(0.3, 0.6),
    certainty=(0.5, 0.8),
)

# Horror: cool, slow, uncertain
HORROR_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.1, 0.4),  # COOL
    density=(0.3, 0.6),
    velocity=(0.2, 0.5),
    distance=(0.4, 0.7),
    certainty=(0.2, 0.5),
)

# Romance: warm, intimate
ROMANCE_ENVELOPE = ToneEnvelope(
    formality=(0.2, 0.5),
    temperature=(0.6, 0.9),
    density=(0.2, 0.5),
    velocity=(0.3, 0.6),
    distance=(0.1, 0.4),  # INTIMATE
    certainty=(0.4, 0.7),
)

# Satire: complex, requires dual-encoding
SATIRE_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),
    temperature=(0.3, 0.6),
    density=(0.4, 0.7),
    velocity=(0.4, 0.7),
    distance=(0.4, 0.7),
    certainty=(0.4, 0.7),
)

# Liturgical: formal, deliberate
LITURGICAL_ENVELOPE = ToneEnvelope(
    formality=(0.7, 1.0),  # FORMAL
    temperature=(0.4, 0.7),
    density=(0.4, 0.7),
    velocity=(0.1, 0.4),  # DELIBERATE
    distance=(0.5, 0.8),
    certainty=(0.6, 0.9),
)

# Aphorism: compressed, memorable
APHORISM_ENVELOPE = ToneEnvelope(
    formality=(0.4, 0.8),
    temperature=(0.3, 0.6),
    density=(0.7, 1.0),  # COMPRESSED
    velocity=(0.3, 0.6),
    distance=(0.5, 0.8),
    certainty=(0.6, 0.9),
)

# Neutral: the idle loop, not a regime. "Don't be weird."
# Neutral is where most language lives - connective tissue, casual Q&A,
# clarifications, acknowledgments. The invariant: "Neutral should feel
# boring, safe, and forgettable." If someone notices Neutral, something's wrong.
NEUTRAL_ENVELOPE = ToneEnvelope(
    formality=(0.3, 0.7),     # middle range
    temperature=(0.3, 0.6),   # slightly warm to neutral
    density=(0.3, 0.6),       # medium
    velocity=(0.3, 0.6),      # medium
    distance=(0.4, 0.6),      # medium
    certainty=(0.4, 0.7),     # moderate confidence
)

# Registry of all regime envelopes
REGIME_ENVELOPES: dict[str, ToneEnvelope] = {
    "comedy": COMEDY_ENVELOPE,
    "tragedy": TRAGEDY_ENVELOPE,
    "sincerity": SINCERITY_ENVELOPE,
    "drama": DRAMA_ENVELOPE,
    "nonfiction": NONFICTION_ENVELOPE,
    "research": RESEARCH_ENVELOPE,
    "instruction": INSTRUCTION_ENVELOPE,
    "debugging": DEBUGGING_ENVELOPE,
    "negotiation": NEGOTIATION_ENVELOPE,
    "advocacy": ADVOCACY_ENVELOPE,
    "marketing": MARKETING_ENVELOPE,
    "horror": HORROR_ENVELOPE,
    "romance": ROMANCE_ENVELOPE,
    "satire": SATIRE_ENVELOPE,
    "liturgical": LITURGICAL_ENVELOPE,
    "aphorism": APHORISM_ENVELOPE,
    "neutral": NEUTRAL_ENVELOPE,
}


def get_envelope(regime: str) -> ToneEnvelope:
    """Get the envelope for a regime. Returns neutral if unknown."""
    return REGIME_ENVELOPES.get(regime.lower(), NEUTRAL_ENVELOPE)


# =============================================================================
# ToneCollision
# =============================================================================


@dataclass
class ToneCollision:
    """A hard block: dimension forbidden in a specific range for a regime."""

    regime: str
    dimension: str
    forbidden_range: tuple[float, float]
    reason: str

    def applies(self, regime: str) -> bool:
        """Check if this collision applies to the given regime."""
        return regime.lower() == self.regime.lower()

    def violates(self, tone: ToneVector) -> bool:
        """Check if tone violates this collision's forbidden range."""
        val = getattr(tone, self.dimension, None)
        if val is None:
            return False
        return self.forbidden_range[0] <= val <= self.forbidden_range[1]

    def fix(self, tone: ToneVector) -> ToneVector:
        """Clip tone to avoid the forbidden range (nearest valid boundary)."""
        val = getattr(tone, self.dimension, None)
        if val is None or not self.violates(tone):
            return tone

        # We need to push out of the forbidden range [lo, hi].
        # There are two valid regions: [0, lo) and (hi, 1].
        # Pick the boundary that leads to a valid position.
        low_boundary = self.forbidden_range[0] - 0.01
        high_boundary = self.forbidden_range[1] + 0.01

        # Check which boundary is valid (in [0, 1])
        low_valid = low_boundary >= 0.0
        high_valid = high_boundary <= 1.0

        if low_valid and high_valid:
            # Both valid, pick nearer
            dist_to_low = abs(val - low_boundary)
            dist_to_high = abs(val - high_boundary)
            new_val = low_boundary if dist_to_low < dist_to_high else high_boundary
        elif low_valid:
            new_val = low_boundary
        elif high_valid:
            new_val = high_boundary
        else:
            # Neither valid (forbidden range spans [0, 1]) - clamp to center
            new_val = 0.5

        # Clamp to [0, 1]
        new_val = max(0.0, min(1.0, new_val))

        return ToneVector(
            formality=new_val if self.dimension == "formality" else tone.formality,
            temperature=new_val if self.dimension == "temperature" else tone.temperature,
            density=new_val if self.dimension == "density" else tone.density,
            velocity=new_val if self.dimension == "velocity" else tone.velocity,
            distance=new_val if self.dimension == "distance" else tone.distance,
            certainty=new_val if self.dimension == "certainty" else tone.certainty,
        )


# Collision rules from tone.md §4.1
TONE_COLLISIONS: list[ToneCollision] = [
    ToneCollision("research", "temperature", (0.6, 1.0), "advocacy_contamination"),
    ToneCollision("comedy", "formality", (0.7, 1.0), "timing_death"),
    ToneCollision("liturgical", "formality", (0.0, 0.5), "spell_collapse"),
    ToneCollision("instruction", "distance", (0.0, 0.2), "therapy_drift"),
    ToneCollision("debugging", "distance", (0.0, 0.3), "therapy_drift"),
    ToneCollision("debugging", "temperature", (0.6, 1.0), "therapy_drift"),
    ToneCollision("research", "certainty", (0.8, 1.0), "agenda_smell"),
    ToneCollision("comedy", "velocity", (0.0, 0.4), "timing_death"),
    ToneCollision("tragedy", "velocity", (0.7, 1.0), "premature_closure"),
    ToneCollision("horror", "temperature", (0.6, 1.0), "defangs_threat"),
]


def resolve_collisions(tone: ToneVector, regime: str) -> ToneVector:
    """Apply all collision rules, silently clipping to valid ranges."""
    result = tone
    for collision in TONE_COLLISIONS:
        if collision.applies(regime) and collision.violates(result):
            result = collision.fix(result)
    return result


def check_collisions(tone: ToneVector, regime: str) -> list[ToneCollision]:
    """Return list of collisions that the tone violates for the regime."""
    return [
        c for c in TONE_COLLISIONS if c.applies(regime) and c.violates(tone)
    ]


# =============================================================================
# ToneStabilityController
# =============================================================================


@dataclass
class ToneStabilityConfig:
    """Configuration for tone stability control."""

    min_dwell_tokens: int = 100
    max_shift_rate: float = 0.002  # per token
    regime_shift_threshold: float = 0.3  # significant regime change = 3x faster
    regime_shift_multiplier: float = 3.0


@dataclass
class ToneStabilityState:
    """Internal state for tone stability control."""

    current_tone: ToneVector = field(default_factory=ToneVector)
    dwell_tokens: int = 0
    last_regime: str = ""


class ToneStabilityController:
    """Rate-limited tone drift control.

    Tone changes slowly over tokens. Faster changes allowed when regime
    shifts significantly.
    """

    def __init__(self, config: ToneStabilityConfig | None = None) -> None:
        self._config = config or ToneStabilityConfig()
        self._state = ToneStabilityState()

    def update_tone(
        self,
        target: ToneVector,
        regime: str,
        tokens_elapsed: int = 1,
    ) -> ToneVector:
        """Move current tone toward target, respecting rate limits.

        Args:
            target: Desired tone vector
            regime: Current regime (for shift detection)
            tokens_elapsed: Tokens since last update

        Returns:
            New tone vector (may be clamped by rate)
        """
        current = self._state.current_tone

        # Detect regime shift
        regime_changed = regime != self._state.last_regime
        self._state.last_regime = regime

        # Calculate max allowed shift
        max_shift = self._config.max_shift_rate * tokens_elapsed
        if regime_changed:
            max_shift *= self._config.regime_shift_multiplier

        # Calculate actual shift needed
        dist = current.euclidean_distance(target)

        if dist <= max_shift:
            # Can reach target
            new_tone = target
        else:
            # Move proportionally toward target
            ratio = max_shift / dist if dist > 0 else 1.0
            new_tone = ToneVector(
                formality=current.formality + ratio * (target.formality - current.formality),
                temperature=current.temperature + ratio * (target.temperature - current.temperature),
                density=current.density + ratio * (target.density - current.density),
                velocity=current.velocity + ratio * (target.velocity - current.velocity),
                distance=current.distance + ratio * (target.distance - current.distance),
                certainty=current.certainty + ratio * (target.certainty - current.certainty),
            )

        self._state.current_tone = new_tone.clamp()
        self._state.dwell_tokens += tokens_elapsed

        return self._state.current_tone

    def reset(self, tone: ToneVector | None = None) -> None:
        """Reset controller state."""
        self._state = ToneStabilityState(
            current_tone=tone or ToneVector(),
            dwell_tokens=0,
            last_regime="",
        )

    @property
    def current_tone(self) -> ToneVector:
        return self._state.current_tone


# =============================================================================
# ToneDriftScorer
# =============================================================================


@dataclass
class ToneDriftScore:
    """Result of tone drift scoring."""

    envelope_drift: float = 0.0  # Distance from envelope bounds
    institutional_density: float = 0.0  # Institutional marker density
    committee_cadence: float = 0.0  # Committee pattern density
    overall_drift: float = 0.0  # Combined score
    collisions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_drift": self.envelope_drift,
            "institutional_density": self.institutional_density,
            "committee_cadence": self.committee_cadence,
            "overall_drift": self.overall_drift,
            "collisions": self.collisions,
        }


class ToneDriftScorer:
    """Scores tone drift from envelope + institutional contamination."""

    def score_drift(
        self,
        tone: ToneVector,
        regime: str,
        text: str,
    ) -> ToneDriftScore:
        """Score how much the text drifts from ideal tone.

        Combines:
        1. Envelope drift (distance from regime envelope)
        2. Institutional marker density
        3. Committee cadence patterns
        """
        envelope = get_envelope(regime)

        # Calculate envelope drift
        envelope_drift = self._calculate_envelope_drift(tone, envelope)

        # Check collisions
        collisions = check_collisions(tone, regime)
        collision_names = [c.reason for c in collisions]

        # Calculate institutional marker density
        word_count = max(len(text.split()), 1)
        counts = count_categorized_patterns(text, INSTITUTIONAL_MARKER_PATTERNS)
        total_markers = sum(counts.values())
        institutional_density = (total_markers / word_count) * 100

        # Calculate committee cadence
        committee_count = count_pattern_matches(text, COMMITTEE_PATTERNS)
        committee_cadence = min(committee_count * 0.12, 0.5)

        # Overall drift (weighted combination)
        overall = (
            envelope_drift * 0.4
            + (institutional_density / 10) * 0.3  # normalize
            + committee_cadence * 0.3
        )
        # Collisions add significant drift
        overall += len(collisions) * 0.15
        overall = min(overall, 1.0)

        return ToneDriftScore(
            envelope_drift=envelope_drift,
            institutional_density=institutional_density,
            committee_cadence=committee_cadence,
            overall_drift=overall,
            collisions=collision_names,
        )

    def _calculate_envelope_drift(
        self, tone: ToneVector, envelope: ToneEnvelope
    ) -> float:
        """Calculate how far tone is outside the envelope."""
        if envelope.contains(tone):
            return 0.0

        # Sum of dimension violations
        total_drift = 0.0

        for dim in ["formality", "temperature", "density", "velocity", "distance", "certainty"]:
            val = getattr(tone, dim)
            bounds = getattr(envelope, dim)
            if val < bounds[0]:
                total_drift += bounds[0] - val
            elif val > bounds[1]:
                total_drift += val - bounds[1]

        # Normalize (max possible drift per dimension is 1.0, 6 dimensions)
        return min(total_drift / 6, 1.0)
