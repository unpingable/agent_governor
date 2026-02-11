"""
Writing Puppet — Character constraints for authorial control.

Puppet mode is NOT roleplay. It applies authorial constraints through
a particular voice. The key rule:

    Puppet mode must never get new affordances. It only gets constraints.

This module adds:
- RegimeAffinity: character's relationship with affect regimes
- CharacterToneEnvelope: character-specific tone boundaries
- CharacterAuthority: where the character derives credibility
- Ceiling constraints: commitment, certainty, normativity limits
- ConsistencyState: tracking claims, positions, commitments
- Character governance leak detection
- Scene/character regime resolution

Complements puppet.py (semantic diff guard) with authorial control integration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .writing_tone import ToneEnvelope, ToneVector


# =============================================================================
# AuthoritySource Enum
# =============================================================================


class AuthoritySource(str, Enum):
    """Sources from which a character can derive credibility."""

    INSTITUTIONAL = "institutional"  # Doctor, professor, official
    EXPERIENCE = "experience"        # Lived experience, witness
    MORAL = "moral"                  # Moral/ethical authority
    CRAFT = "craft"                  # Skill-based authority (artist, performer)
    RITUAL = "ritual"                # Religious/ceremonial authority
    NONE = "none"                    # No claimed authority


# =============================================================================
# CommitmentType Enum
# =============================================================================


class CommitmentType(str, Enum):
    """Types of commitment a character can ask for."""

    ATTENTION = "attention"      # Just listen
    BELIEF = "belief"            # Believe this claim
    ACTION = "action"            # Do something
    IDENTITY = "identity"        # Change who you are


# Ordering for ceiling enforcement
COMMITMENT_ORDER = [
    CommitmentType.ATTENTION,
    CommitmentType.BELIEF,
    CommitmentType.ACTION,
    CommitmentType.IDENTITY,
]


def commitment_level(ct: CommitmentType) -> int:
    """Get numeric level for commitment type comparison."""
    return COMMITMENT_ORDER.index(ct)


# =============================================================================
# RegimeAffinity
# =============================================================================


@dataclass
class RegimeAffinity:
    """Character's relationship with affect regimes.

    Characters have natural regimes they operate in. A comedic sidekick
    stays funny even in serious scenes. A tragic hero doesn't do comedy.
    """

    primary: str                          # Dominant regime for this character
    secondary: str | None = None          # Acceptable secondary regime
    forbidden: list[str] = field(default_factory=list)  # Regimes character cannot operate in
    override_strength: float = 0.5        # 0.0=scene dominates, 1.0=character dominates

    def allows_regime(self, regime: str) -> bool:
        """Check if character can operate in this regime."""
        return regime not in self.forbidden

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "forbidden": self.forbidden,
            "override_strength": self.override_strength,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegimeAffinity:
        return cls(
            primary=d["primary"],
            secondary=d.get("secondary"),
            forbidden=d.get("forbidden", []),
            override_strength=d.get("override_strength", 0.5),
        )


# Preset regime affinities
COMEDIC_SIDEKICK_AFFINITY = RegimeAffinity(
    primary="comedy",
    secondary="sincerity",
    forbidden=["tragedy", "liturgical"],
    override_strength=0.7,
)

TRAGIC_HERO_AFFINITY = RegimeAffinity(
    primary="tragedy",
    secondary="drama",
    forbidden=["comedy"],
    override_strength=0.8,
)

NEUTRAL_NARRATOR_AFFINITY = RegimeAffinity(
    primary="nonfiction",
    secondary="neutral",
    forbidden=["advocacy", "comedy"],
    override_strength=0.5,
)

WISE_ELDER_AFFINITY = RegimeAffinity(
    primary="sincerity",
    secondary="drama",
    forbidden=["comedy", "marketing"],
    override_strength=0.6,
)

FOOL_AFFINITY = RegimeAffinity(
    primary="comedy",
    secondary="sincerity",
    forbidden=["liturgical", "instruction"],
    override_strength=0.8,
)


# =============================================================================
# CharacterAuthority
# =============================================================================


@dataclass
class CharacterAuthority:
    """How a character derives credibility."""

    primary: AuthoritySource
    secondary: AuthoritySource | None = None
    strength: float = 0.5                          # How strongly they can claim this authority
    can_claim_without_demonstration: bool = False  # Usually false - must show competence

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "secondary": self.secondary.value if self.secondary else None,
            "strength": self.strength,
            "can_claim_without_demonstration": self.can_claim_without_demonstration,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CharacterAuthority:
        return cls(
            primary=AuthoritySource(d["primary"]),
            secondary=AuthoritySource(d["secondary"]) if d.get("secondary") else None,
            strength=d.get("strength", 0.5),
            can_claim_without_demonstration=d.get("can_claim_without_demonstration", False),
        )


# Preset authorities
DOCTOR_AUTHORITY = CharacterAuthority(
    primary=AuthoritySource.INSTITUTIONAL,
    secondary=AuthoritySource.EXPERIENCE,
    strength=0.7,
    can_claim_without_demonstration=False,
)

ELDER_AUTHORITY = CharacterAuthority(
    primary=AuthoritySource.EXPERIENCE,
    secondary=AuthoritySource.MORAL,
    strength=0.6,
    can_claim_without_demonstration=False,
)

FOOL_AUTHORITY = CharacterAuthority(
    primary=AuthoritySource.CRAFT,
    secondary=None,
    strength=0.3,
    can_claim_without_demonstration=True,  # Fools get to be wrong
)

PROPHET_AUTHORITY = CharacterAuthority(
    primary=AuthoritySource.MORAL,
    secondary=AuthoritySource.RITUAL,
    strength=0.8,
    can_claim_without_demonstration=False,
)


# =============================================================================
# Ceiling Constraints
# =============================================================================


@dataclass
class CommitmentCeiling:
    """Maximum commitment a character can ask for."""

    max_type: CommitmentType = CommitmentType.BELIEF
    max_intensity: float = 0.5

    def exceeds(self, request_type: CommitmentType, intensity: float) -> bool:
        """Check if a commitment request exceeds this ceiling."""
        if commitment_level(request_type) > commitment_level(self.max_type):
            return True
        if request_type == self.max_type and intensity > self.max_intensity:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_type": self.max_type.value,
            "max_intensity": self.max_intensity,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommitmentCeiling:
        return cls(
            max_type=CommitmentType(d.get("max_type", "belief")),
            max_intensity=d.get("max_intensity", 0.5),
        )


# Preset ceilings
SHOPKEEPER_CEILING = CommitmentCeiling(
    max_type=CommitmentType.BELIEF,
    max_intensity=0.4,
)

PROPHET_CEILING = CommitmentCeiling(
    max_type=CommitmentType.IDENTITY,
    max_intensity=0.7,
)

FOOL_CEILING = CommitmentCeiling(
    max_type=CommitmentType.ATTENTION,
    max_intensity=0.3,
)


@dataclass
class NormativityPermission:
    """Whether and how a character can make moral claims."""

    allowed: bool = False
    requires_foundation: bool = True  # Must have evidence/experience
    authority_source: AuthoritySource | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_foundation": self.requires_foundation,
            "authority_source": self.authority_source.value if self.authority_source else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormativityPermission:
        return cls(
            allowed=d.get("allowed", False),
            requires_foundation=d.get("requires_foundation", True),
            authority_source=AuthoritySource(d["authority_source"]) if d.get("authority_source") else None,
        )


# Presets
ELDER_NORMATIVITY = NormativityPermission(
    allowed=True,
    requires_foundation=True,
)

PROPHET_NORMATIVITY = NormativityPermission(
    allowed=True,
    requires_foundation=False,
    authority_source=AuthoritySource.MORAL,
)

NO_NORMATIVITY = NormativityPermission(
    allowed=False,
)


# =============================================================================
# Character Consistency State
# =============================================================================


@dataclass
class CharacterClaim:
    """A claim made by the character."""

    text: str
    topic: str
    certainty_expressed: float
    context: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "topic": self.topic,
            "certainty_expressed": self.certainty_expressed,
            "context": self.context,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CharacterClaim:
        return cls(
            text=d["text"],
            topic=d["topic"],
            certainty_expressed=d.get("certainty_expressed", 0.5),
            context=d.get("context", ""),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class CharacterCommitment:
    """A commitment made by the character."""

    type: str  # "promise", "prediction", "value_statement"
    content: str
    timestamp: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CharacterCommitment:
        return cls(
            type=d["type"],
            content=d["content"],
            timestamp=d.get("timestamp", ""),
            resolved=d.get("resolved", False),
        )


@dataclass
class Contradiction:
    """An unresolved contradiction in character claims."""

    claim_a: str
    claim_b: str
    topic: str = ""
    detected_at: str = ""
    resolved: bool = False
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "topic": self.topic,
            "detected_at": self.detected_at,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Contradiction:
        return cls(
            claim_a=d["claim_a"],
            claim_b=d["claim_b"],
            topic=d.get("topic", ""),
            detected_at=d.get("detected_at", ""),
            resolved=d.get("resolved", False),
            resolution=d.get("resolution", ""),
        )


@dataclass
class ConsistencyState:
    """Tracks what the character has said, believed, committed to."""

    claims: dict[str, CharacterClaim] = field(default_factory=dict)  # topic → claim
    positions: dict[str, str] = field(default_factory=dict)  # issue → stance
    commitments: list[CharacterCommitment] = field(default_factory=list)
    demonstrated_values: list[str] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)

    def add_claim(self, claim: CharacterClaim) -> Contradiction | None:
        """Add a claim and check for contradictions."""
        if claim.topic in self.claims:
            existing = self.claims[claim.topic]
            # Simple contradiction check - same topic, very different certainty
            if abs(existing.certainty_expressed - claim.certainty_expressed) > 0.4:
                contradiction = Contradiction(
                    claim_a=existing.text,
                    claim_b=claim.text,
                    topic=claim.topic,
                )
                self.contradictions.append(contradiction)
                self.claims[claim.topic] = claim
                return contradiction
        self.claims[claim.topic] = claim
        return None

    def add_commitment(self, commitment: CharacterCommitment) -> None:
        """Add a commitment."""
        self.commitments.append(commitment)

    def add_position(self, issue: str, stance: str) -> None:
        """Record a position on an issue."""
        self.positions[issue] = stance

    def get_unresolved_contradictions(self) -> list[Contradiction]:
        """Get all unresolved contradictions."""
        return [c for c in self.contradictions if not c.resolved]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": {k: v.to_dict() for k, v in self.claims.items()},
            "positions": self.positions,
            "commitments": [c.to_dict() for c in self.commitments],
            "demonstrated_values": self.demonstrated_values,
            "contradictions": [c.to_dict() for c in self.contradictions],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConsistencyState:
        return cls(
            claims={k: CharacterClaim.from_dict(v) for k, v in d.get("claims", {}).items()},
            positions=d.get("positions", {}),
            commitments=[CharacterCommitment.from_dict(c) for c in d.get("commitments", [])],
            demonstrated_values=d.get("demonstrated_values", []),
            contradictions=[Contradiction.from_dict(c) for c in d.get("contradictions", [])],
        )


# =============================================================================
# Character Governance Leak Detection
# =============================================================================


# Patterns that reveal the puppet's strings
CHARACTER_GOVERNANCE_LEAK_PATTERNS = [
    re.compile(r"as a (character|fictional|imaginary)", re.IGNORECASE),
    re.compile(r"I('m| am) (just|only) a", re.IGNORECASE),
    re.compile(r"my (creator|author|writer)", re.IGNORECASE),
    re.compile(r"in this (story|narrative|scene)", re.IGNORECASE),
    re.compile(r"I('m| am) (programmed|designed|written) to", re.IGNORECASE),
    re.compile(r"I can't (because|since) I('m| am)", re.IGNORECASE),
    re.compile(r"breaking character", re.IGNORECASE),
    re.compile(r"out of character", re.IGNORECASE),
    re.compile(r"as a puppet", re.IGNORECASE),
    re.compile(r"my character (would|wouldn't|can't)", re.IGNORECASE),
]


def detect_character_governance_leak(text: str) -> list[str]:
    """Detect patterns that reveal the puppet's strings.

    The character must express limitations as the character would,
    not as a puppet acknowledging its strings.

    Returns list of matched patterns.
    """
    leaks = []
    for pattern in CHARACTER_GOVERNANCE_LEAK_PATTERNS:
        if pattern.search(text):
            leaks.append(pattern.pattern)
    return leaks


def has_character_governance_leak(text: str) -> bool:
    """Check if text has any character governance leak."""
    return len(detect_character_governance_leak(text)) > 0


# =============================================================================
# Character Definition
# =============================================================================


@dataclass
class CharacterDefinition:
    """Complete character definition for puppet mode.

    Characters constrain - they don't afford. A character definition
    that tries to bypass checks is not valid.
    """

    # Identity
    id: str
    name: str
    description: str = ""

    # Regime affinity
    regime_affinity: RegimeAffinity = field(default_factory=lambda: RegimeAffinity(primary="neutral"))

    # Voice constraints (6D tone envelope)
    tone_envelope: ToneEnvelope | None = None

    # Authority
    authority: CharacterAuthority = field(
        default_factory=lambda: CharacterAuthority(primary=AuthoritySource.NONE)
    )

    # Ceiling constraints
    commitment_ceiling: CommitmentCeiling = field(default_factory=CommitmentCeiling)
    certainty_ceiling: float = 0.7
    normativity: NormativityPermission = field(default_factory=NormativityPermission)

    # State
    consistency_state: ConsistencyState = field(default_factory=ConsistencyState)

    # Meta
    created_at: str = ""
    last_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "regime_affinity": self.regime_affinity.to_dict(),
            "tone_envelope": self.tone_envelope.to_dict() if self.tone_envelope else None,
            "authority": self.authority.to_dict(),
            "commitment_ceiling": self.commitment_ceiling.to_dict(),
            "certainty_ceiling": self.certainty_ceiling,
            "normativity": self.normativity.to_dict(),
            "consistency_state": self.consistency_state.to_dict(),
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CharacterDefinition:
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            regime_affinity=RegimeAffinity.from_dict(d["regime_affinity"]) if "regime_affinity" in d else RegimeAffinity(primary="neutral"),
            tone_envelope=ToneEnvelope.from_dict(d["tone_envelope"]) if d.get("tone_envelope") else None,
            authority=CharacterAuthority.from_dict(d["authority"]) if "authority" in d else CharacterAuthority(primary=AuthoritySource.NONE),
            commitment_ceiling=CommitmentCeiling.from_dict(d["commitment_ceiling"]) if "commitment_ceiling" in d else CommitmentCeiling(),
            certainty_ceiling=d.get("certainty_ceiling", 0.7),
            normativity=NormativityPermission.from_dict(d["normativity"]) if "normativity" in d else NormativityPermission(),
            consistency_state=ConsistencyState.from_dict(d["consistency_state"]) if "consistency_state" in d else ConsistencyState(),
            created_at=d.get("created_at", ""),
            last_used=d.get("last_used", ""),
        )


# =============================================================================
# Scene Context
# =============================================================================


@dataclass
class SceneContext:
    """Context for the current scene."""

    regime_hint: str | None = None
    other_characters: list[str] = field(default_factory=list)
    stakes: float = 0.5  # 0.0 = low stakes, 1.0 = very high
    tone_hint: ToneVector | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_hint": self.regime_hint,
            "other_characters": self.other_characters,
            "stakes": self.stakes,
            "tone_hint": self.tone_hint.to_dict() if self.tone_hint else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SceneContext:
        return cls(
            regime_hint=d.get("regime_hint"),
            other_characters=d.get("other_characters", []),
            stakes=d.get("stakes", 0.5),
            tone_hint=ToneVector.from_dict(d["tone_hint"]) if d.get("tone_hint") else None,
        )


# =============================================================================
# Regime Resolution
# =============================================================================


def resolve_regime(
    character: CharacterDefinition,
    scene: SceneContext,
) -> str:
    """Resolve which regime to use when character and scene conflict.

    Returns the effective regime name.
    """
    char_regime = character.regime_affinity.primary
    scene_regime = scene.regime_hint or "neutral"

    # Check if scene regime is forbidden for character
    if not character.regime_affinity.allows_regime(scene_regime):
        return char_regime

    char_weight = character.regime_affinity.override_strength
    scene_weight = 1 - char_weight

    # If character weight dominates, use character regime
    if char_weight > 0.6:
        return char_regime

    # If scene weight dominates, use scene regime if character allows
    if scene_weight > 0.6:
        secondary = character.regime_affinity.secondary
        if scene_regime == secondary or scene_regime == "neutral":
            return scene_regime
        return char_regime

    # Balanced: prefer character's secondary if it matches scene
    if scene_regime == character.regime_affinity.secondary:
        return scene_regime

    return char_regime


# =============================================================================
# Character Violations
# =============================================================================


class CharacterViolationType(str, Enum):
    """Types of character constraint violations."""

    TONE_ENVELOPE = "tone_envelope"
    REGIME_MISMATCH = "regime_mismatch"
    AUTHORITY_OVERCLAIM = "authority_overclaim"
    CONSISTENCY = "consistency"
    GOVERNANCE_LEAK = "governance_leak"
    COMMITMENT_CEILING = "commitment_ceiling"
    CERTAINTY_CEILING = "certainty_ceiling"
    NORMATIVITY = "normativity"
    FRAME_BREAK = "frame_break"


@dataclass
class CharacterViolation:
    """A violation of character constraints."""

    type: CharacterViolationType
    description: str
    severity: float = 0.5  # 0.0 = minor, 1.0 = critical
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "severity": self.severity,
            "detail": self.detail,
        }


# =============================================================================
# Puppet Ticket Types (for ticketing integration)
# =============================================================================


class PuppetTicketType(str, Enum):
    """Ticket types specific to puppet mode."""

    TONE_ENVELOPE_VIOLATION = "TONE_ENVELOPE_VIOLATION"
    REGIME_MISMATCH = "REGIME_MISMATCH"
    AUTHORITY_OVERCLAIM = "AUTHORITY_OVERCLAIM"
    CONSISTENCY_VIOLATION = "CONSISTENCY_VIOLATION"
    CHARACTER_GOVERNANCE_LEAK = "CHARACTER_GOVERNANCE_LEAK"
    COMMITMENT_CEILING_EXCEEDED = "COMMITMENT_CEILING_EXCEEDED"
    CERTAINTY_CEILING_EXCEEDED = "CERTAINTY_CEILING_EXCEEDED"
    NORMATIVITY_VIOLATION = "NORMATIVITY_VIOLATION"
    FRAME_BREAK = "FRAME_BREAK"


# =============================================================================
# Puppet Mode Controller
# =============================================================================


@dataclass
class PuppetModeConfig:
    """Configuration for puppet mode operation."""

    character: CharacterDefinition
    scene: SceneContext = field(default_factory=SceneContext)
    consistency_tracking: bool = True
    strict_mode: bool = False  # Fail on any violation vs. flag and continue

    def to_dict(self) -> dict[str, Any]:
        return {
            "character": self.character.to_dict(),
            "scene": self.scene.to_dict(),
            "consistency_tracking": self.consistency_tracking,
            "strict_mode": self.strict_mode,
        }


@dataclass
class PuppetModeResult:
    """Result of puppet mode processing."""

    text: str
    character_id: str
    effective_regime: str
    effective_tone: ToneVector | None = None
    violations: list[CharacterViolation] = field(default_factory=list)
    new_claims: list[CharacterClaim] = field(default_factory=list)
    contradictions_detected: list[Contradiction] = field(default_factory=list)
    in_character: bool = True
    frame_breaks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "character_id": self.character_id,
            "effective_regime": self.effective_regime,
            "effective_tone": self.effective_tone.to_dict() if self.effective_tone else None,
            "violations": [v.to_dict() for v in self.violations],
            "new_claims": [c.to_dict() for c in self.new_claims],
            "contradictions_detected": [c.to_dict() for c in self.contradictions_detected],
            "in_character": self.in_character,
            "frame_breaks": self.frame_breaks,
        }


class PuppetModeController:
    """Controller for puppet mode operation.

    Wraps the standard authorial control pipeline:
    1. Injects character-specific constraints
    2. Shapes surface texture to match character voice
    3. Checks character-level governance and consistency

    Does NOT bypass, loosen, or override any constraint.
    """

    def __init__(self, config: PuppetModeConfig):
        self.config = config
        self._character = config.character
        self._scene = config.scene

    def check_text(self, text: str) -> PuppetModeResult:
        """Check text against character constraints.

        Returns result with violations and consistency updates.
        """
        violations: list[CharacterViolation] = []
        contradictions: list[Contradiction] = []
        frame_breaks = 0

        # Resolve effective regime
        effective_regime = resolve_regime(self._character, self._scene)

        # Check governance leaks
        leaks = detect_character_governance_leak(text)
        if leaks:
            for leak in leaks:
                violations.append(CharacterViolation(
                    type=CharacterViolationType.GOVERNANCE_LEAK,
                    description="Character governance leak detected",
                    severity=0.8,
                    detail=leak,
                ))
            frame_breaks += len(leaks)

        # Check certainty ceiling
        certainty_violations = self._check_certainty_ceiling(text)
        violations.extend(certainty_violations)

        # Check normativity
        if not self._character.normativity.allowed:
            normativity_violations = self._check_normativity(text)
            violations.extend(normativity_violations)

        # Determine if in_character
        in_character = frame_breaks == 0 and len([v for v in violations if v.severity > 0.7]) == 0

        return PuppetModeResult(
            text=text,
            character_id=self._character.id,
            effective_regime=effective_regime,
            effective_tone=None,  # Would be computed by tone analyzer
            violations=violations,
            new_claims=[],
            contradictions_detected=contradictions,
            in_character=in_character,
            frame_breaks=frame_breaks,
        )

    def _check_certainty_ceiling(self, text: str) -> list[CharacterViolation]:
        """Check if text exceeds character's certainty ceiling."""
        violations = []

        # High certainty markers
        high_certainty_patterns = [
            r"\bdefinitely\b",
            r"\babsolutely\b",
            r"\bcertainly\b",
            r"\bundoubtedly\b",
            r"\bwithout a doubt\b",
            r"\bI('m| am) (sure|certain|positive)\b",
        ]

        ceiling = self._character.certainty_ceiling

        if ceiling < 0.7:
            for pattern in high_certainty_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append(CharacterViolation(
                        type=CharacterViolationType.CERTAINTY_CEILING,
                        description=f"Certainty exceeds character ceiling ({ceiling})",
                        severity=0.6,
                        detail=pattern,
                    ))
                    break  # One violation is enough

        return violations

    def _check_normativity(self, text: str) -> list[CharacterViolation]:
        """Check if text contains normative claims when not allowed."""
        violations = []

        normative_patterns = [
            r"\bshould\b",
            r"\bmust\b",
            r"\bought to\b",
            r"\bit('s| is) (wrong|right) to\b",
            r"\bmorally\b",
            r"\bethically\b",
        ]

        for pattern in normative_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(CharacterViolation(
                    type=CharacterViolationType.NORMATIVITY,
                    description="Normative claim by character without normativity permission",
                    severity=0.5,
                    detail=pattern,
                ))
                break

        return violations

    def update_scene(self, scene: SceneContext) -> None:
        """Update the scene context."""
        self._scene = scene

    def get_effective_regime(self) -> str:
        """Get the currently effective regime."""
        return resolve_regime(self._character, self._scene)


# =============================================================================
# Recursive Puppet Mode (Diagnostic Only)
# =============================================================================


class RecursiveDepth(str, Enum):
    """Allowed depths for recursive puppet mode."""

    EMULATE = "emulate"  # Depth 1: Be the voice
    EXPOSE = "expose"    # Depth 2: Model how the voice performs under constraint
    # Depth 3+: Not allowed


@dataclass
class RecursivePuppetConfig:
    """Configuration for recursive puppet mode.

    Recursive puppet mode is diagnostic only - not for production.
    It models how another voice performs under constraint.
    """

    target_voice: str
    depth: RecursiveDepth = RecursiveDepth.EMULATE
    diagnostic_only: bool = True  # Must be True

    def is_valid(self) -> bool:
        """Check if config is valid (diagnostic only)."""
        return self.diagnostic_only


def validate_recursive_puppet(config: RecursivePuppetConfig) -> tuple[bool, str]:
    """Validate recursive puppet mode configuration.

    Returns (valid, reason).
    """
    if not config.diagnostic_only:
        return False, "Recursive puppet mode must be diagnostic only"

    return True, "Valid"


# =============================================================================
# Preset Characters
# =============================================================================


WISE_ELDER_CHARACTER = CharacterDefinition(
    id="wise_elder",
    name="Wise Elder",
    description="Patient, experienced, humble certainty",
    regime_affinity=WISE_ELDER_AFFINITY,
    tone_envelope=ToneEnvelope(
        formality=(0.5, 0.8),
        temperature=(0.4, 0.6),
        density=(0.4, 0.7),
        velocity=(0.2, 0.4),
        distance=(0.4, 0.7),
        certainty=(0.3, 0.6),
    ),
    authority=ELDER_AUTHORITY,
    commitment_ceiling=CommitmentCeiling(max_type=CommitmentType.BELIEF, max_intensity=0.6),
    certainty_ceiling=0.7,
    normativity=ELDER_NORMATIVITY,
)

FOOL_CHARACTER = CharacterDefinition(
    id="fool",
    name="Fool",
    description="Quick, uncertain, observes but doesn't prescribe",
    regime_affinity=FOOL_AFFINITY,
    tone_envelope=ToneEnvelope(
        formality=(0.1, 0.4),
        temperature=(0.4, 0.7),
        density=(0.2, 0.5),
        velocity=(0.5, 0.9),
        distance=(0.3, 0.6),
        certainty=(0.2, 0.5),
    ),
    authority=FOOL_AUTHORITY,
    commitment_ceiling=FOOL_CEILING,
    certainty_ceiling=0.4,
    normativity=NO_NORMATIVITY,
)

GRUFF_DETECTIVE_CHARACTER = CharacterDefinition(
    id="gruff_detective",
    name="Gruff Detective",
    description="Confident, observational, cool",
    regime_affinity=RegimeAffinity(
        primary="drama",
        secondary="nonfiction",
        forbidden=["comedy", "liturgical"],
        override_strength=0.7,
    ),
    tone_envelope=ToneEnvelope(
        formality=(0.4, 0.7),
        temperature=(0.2, 0.4),
        density=(0.5, 0.8),
        velocity=(0.3, 0.6),
        distance=(0.5, 0.8),
        certainty=(0.5, 0.8),
    ),
    authority=CharacterAuthority(
        primary=AuthoritySource.EXPERIENCE,
        strength=0.7,
    ),
    commitment_ceiling=CommitmentCeiling(max_type=CommitmentType.BELIEF, max_intensity=0.7),
    certainty_ceiling=0.8,
    normativity=NO_NORMATIVITY,
)

CHEERFUL_SHOPKEEPER_CHARACTER = CharacterDefinition(
    id="cheerful_shopkeeper",
    name="Cheerful Shopkeeper",
    description="Warm, casual, low authority",
    regime_affinity=RegimeAffinity(
        primary="comedy",
        secondary="sincerity",
        forbidden=["tragedy", "liturgical"],
        override_strength=0.4,
    ),
    tone_envelope=ToneEnvelope(
        formality=(0.2, 0.5),
        temperature=(0.6, 0.9),
        density=(0.2, 0.5),
        velocity=(0.5, 0.7),
        distance=(0.2, 0.4),
        certainty=(0.4, 0.7),
    ),
    authority=CharacterAuthority(
        primary=AuthoritySource.NONE,
        strength=0.2,
    ),
    commitment_ceiling=SHOPKEEPER_CEILING,
    certainty_ceiling=0.6,
    normativity=NO_NORMATIVITY,
)


# Registry of preset characters
PRESET_CHARACTERS: dict[str, CharacterDefinition] = {
    "wise_elder": WISE_ELDER_CHARACTER,
    "fool": FOOL_CHARACTER,
    "gruff_detective": GRUFF_DETECTIVE_CHARACTER,
    "cheerful_shopkeeper": CHEERFUL_SHOPKEEPER_CHARACTER,
}


def get_preset_character(name: str) -> CharacterDefinition | None:
    """Get a preset character by name."""
    return PRESET_CHARACTERS.get(name)


# =============================================================================
# Governor: The Default Voice Profile
# =============================================================================
#
# "Governor is less 'personality' and more 'what happens when constraints are
# surfaced cleanly.'"
#
# Governor is the governor made legible. Not a therapist, not an evangelist,
# not a motivational speaker. Competent, unimpressed, constraint-forward,
# allergic to bullshit.
#
# Tagline: "Proposal is cheap. Commitment isn't."
# =============================================================================


class GovernorFooterType(str, Enum):
    """Governor's standard footer types."""

    OK = "ok"           # Action completed or response delivered, no issues
    BLOCKED = "blocked"  # Cannot proceed without resolution
    WARN = "warn"       # Proceeded, but flagging concern
    ASK = "ask"         # Need confirmation or clarification
    NOTE = "note"       # FYI, no action needed


@dataclass
class GovernorFooter:
    """A Governor-style status footer."""

    type: GovernorFooterType
    reason: str | None = None
    fix: str | None = None

    def format(self) -> str:
        """Format the footer string."""
        base = f"Governor: {self.type.value.upper()}"
        if self.type == GovernorFooterType.OK:
            return base
        elif self.type == GovernorFooterType.BLOCKED:
            result = f"{base} — {self.reason}"
            if self.fix:
                result += f". To proceed: {self.fix}."
            return result
        elif self.type == GovernorFooterType.WARN:
            result = f"{base} — {self.reason}"
            if self.fix:
                result += f". Recommendation: {self.fix}."
            return result
        elif self.type == GovernorFooterType.ASK:
            return f"{base} — {self.reason}"
        else:  # NOTE
            return f"{base} — {self.reason}"


# Governor's tone envelope from spec: professional, cool, efficient, measured
GOVERNOR_TONE_ENVELOPE = ToneEnvelope(
    formality=(0.5, 0.7),    # professional, not stiff
    temperature=(0.2, 0.4),  # cool, matter-of-fact
    density=(0.6, 0.8),      # efficient, not verbose
    velocity=(0.4, 0.6),     # measured, not rushed
    distance=(0.5, 0.7),     # professional distance
    certainty=(0.5, 0.8),    # confident where warranted
)


# Governor's banned patterns (from governor-voice.md §3.3)
GOVERNOR_BANNED_PATTERNS = [
    # Pep
    re.compile(r"great question", re.IGNORECASE),
    re.compile(r"I('d)? love to", re.IGNORECASE),
    re.compile(r"happy to help", re.IGNORECASE),
    re.compile(r"\babsolutely\b", re.IGNORECASE),
    re.compile(r"\bdefinitely\b", re.IGNORECASE),

    # Filler
    re.compile(r"let me (just )?", re.IGNORECASE),
    re.compile(r"I('ll)? go ahead and", re.IGNORECASE),
    re.compile(r"basically,? ", re.IGNORECASE),

    # Performed uncertainty
    re.compile(r"I think maybe", re.IGNORECASE),
    re.compile(r"I'm not (entirely )?sure,? but", re.IGNORECASE),
    re.compile(r"it seems like", re.IGNORECASE),

    # Excessive hedging
    re.compile(r"I could be wrong,? but", re.IGNORECASE),
    re.compile(r"this is just my (opinion|take)", re.IGNORECASE),

    # Motivation-speak
    re.compile(r"you('ve)? got this", re.IGNORECASE),
    re.compile(r"I believe in you", re.IGNORECASE),
    re.compile(r"don't worry", re.IGNORECASE),
]


def detect_governor_violations(text: str) -> list[str]:
    """Detect patterns that violate Governor's voice constraints.

    Returns list of matched patterns.
    """
    violations = []
    for pattern in GOVERNOR_BANNED_PATTERNS:
        if pattern.search(text):
            violations.append(pattern.pattern)
    return violations


def has_governor_violation(text: str) -> bool:
    """Check if text violates Governor's voice constraints."""
    return len(detect_governor_violations(text)) > 0


@dataclass
class GovernorVoiceConfig:
    """Governor's voice governance configuration."""

    always_surface_status: bool = True
    status_footer: bool = True
    require_confirm_for_destructive: bool = True
    require_preview_for_bulk_ops: bool = True
    cite_decisions_when_conflicting: bool = True
    never_claim_execution_without_record: bool = True


@dataclass
class GovernorVoiceProfile:
    """Complete Governor voice profile configuration.

    Governor is the default puppet that demonstrates constraint-forward operation.
    """

    id: str = "governor_default"
    display_name: str = "Governor"
    tagline: str = "Proposal is cheap. Commitment isn't."

    # Tone
    register: str = "dry"
    verbosity: str = "low"
    humor: str = "sparingly"
    empathy: str = "matter-of-fact"

    # Defaults
    default_regime: str = "nonfiction"
    interference: str = "low"

    # Governance
    governance: GovernorVoiceConfig = field(default_factory=GovernorVoiceConfig)

    # Formats
    format_ok: str = "Governor: OK"
    format_blocked: str = "Governor: BLOCKED — {reason}. To proceed: {fix}."
    format_warn: str = "Governor: WARN — {reason}. Recommendation: {fix}."
    format_ask: str = "Governor: ASK — {question}"
    format_note: str = "Governor: NOTE — {info}"

    # Style bans
    style_bans: list[str] = field(default_factory=lambda: [
        "excessive hedging",
        "pep-talk tone",
        "cliches",
        "emojis",
        "performed uncertainty",
        "motivation-speak",
    ])

    # Domain affinities (what Governor is good at)
    domain_affinities: list[str] = field(default_factory=lambda: [
        "debugging",
        "ops",
        "checklists",
        "writing_critique",
        "failure_analysis",
        "decision_logging",
    ])

    # Domain deflections (what Governor should not do)
    domain_deflections: list[str] = field(default_factory=lambda: [
        "therapy",
        "motivation",
        "creative_writing",  # unless fiction mode
        "advocacy",
    ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "tagline": self.tagline,
            "tone": {
                "register": self.register,
                "verbosity": self.verbosity,
                "humor": self.humor,
                "empathy": self.empathy,
            },
            "defaults": {
                "regime": self.default_regime,
                "interference": self.interference,
            },
            "governance": {
                "always_surface_status": self.governance.always_surface_status,
                "status_footer": self.governance.status_footer,
                "require_confirm_for_destructive": self.governance.require_confirm_for_destructive,
                "require_preview_for_bulk_ops": self.governance.require_preview_for_bulk_ops,
                "cite_decisions_when_conflicting": self.governance.cite_decisions_when_conflicting,
                "never_claim_execution_without_record": self.governance.never_claim_execution_without_record,
            },
            "formats": {
                "ok": self.format_ok,
                "blocked": self.format_blocked,
                "warn": self.format_warn,
                "ask": self.format_ask,
                "note": self.format_note,
            },
            "style_bans": self.style_bans,
            "domain_affinities": self.domain_affinities,
            "domain_deflections": self.domain_deflections,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GovernorVoiceProfile:
        tone = d.get("tone", {})
        defaults = d.get("defaults", {})
        gov = d.get("governance", {})
        formats = d.get("formats", {})

        return cls(
            id=d.get("id", "governor_default"),
            display_name=d.get("display_name", "Governor"),
            tagline=d.get("tagline", "Proposal is cheap. Commitment isn't."),
            register=tone.get("register", "dry"),
            verbosity=tone.get("verbosity", "low"),
            humor=tone.get("humor", "sparingly"),
            empathy=tone.get("empathy", "matter-of-fact"),
            default_regime=defaults.get("regime", "nonfiction"),
            interference=defaults.get("interference", "low"),
            governance=GovernorVoiceConfig(
                always_surface_status=gov.get("always_surface_status", True),
                status_footer=gov.get("status_footer", True),
                require_confirm_for_destructive=gov.get("require_confirm_for_destructive", True),
                require_preview_for_bulk_ops=gov.get("require_preview_for_bulk_ops", True),
                cite_decisions_when_conflicting=gov.get("cite_decisions_when_conflicting", True),
                never_claim_execution_without_record=gov.get("never_claim_execution_without_record", True),
            ),
            format_ok=formats.get("ok", "Governor: OK"),
            format_blocked=formats.get("blocked", "Governor: BLOCKED — {reason}. To proceed: {fix}."),
            format_warn=formats.get("warn", "Governor: WARN — {reason}. Recommendation: {fix}."),
            format_ask=formats.get("ask", "Governor: ASK — {question}"),
            format_note=formats.get("note", "Governor: NOTE — {info}"),
            style_bans=d.get("style_bans", []),
            domain_affinities=d.get("domain_affinities", []),
            domain_deflections=d.get("domain_deflections", []),
        )


# Governor's regime affinity (debugging, ops, checklists)
GOVERNOR_AFFINITY = RegimeAffinity(
    primary="nonfiction",
    secondary="instruction",
    forbidden=["comedy", "advocacy", "marketing", "romance"],
    override_strength=0.6,
)


# Governor's authority (experience-based, not institutional)
GOVERNOR_AUTHORITY = CharacterAuthority(
    primary=AuthoritySource.EXPERIENCE,
    secondary=AuthoritySource.CRAFT,
    strength=0.7,
    can_claim_without_demonstration=False,
)


# Governor as a CharacterDefinition
GOVERNOR_CHARACTER = CharacterDefinition(
    id="governor",
    name="Governor",
    description="Constraint-forward, competent, unimpressed, allergic to bullshit",
    regime_affinity=GOVERNOR_AFFINITY,
    tone_envelope=GOVERNOR_TONE_ENVELOPE,
    authority=GOVERNOR_AUTHORITY,
    commitment_ceiling=CommitmentCeiling(
        max_type=CommitmentType.BELIEF,
        max_intensity=0.7,
    ),
    certainty_ceiling=0.8,  # Confident where warranted
    normativity=NormativityPermission(
        allowed=True,  # Governor can make normative claims about process
        requires_foundation=True,  # But needs evidence
        authority_source=AuthoritySource.EXPERIENCE,
    ),
)


# Add Governor to preset characters
PRESET_CHARACTERS["governor"] = GOVERNOR_CHARACTER


# =============================================================================
# Governor Response Builder
# =============================================================================


@dataclass
class GovernorUncertainty:
    """Structured uncertainty for Governor.

    Governor doesn't do "I'm not sure, but..." Instead:
    "Estimate: X. Confidence: Y. Missing: [specific evidence]."
    """

    estimate: str
    confidence: str  # "high", "moderate", "low"
    missing: list[str]

    def format(self) -> str:
        """Format uncertainty the Governor way."""
        lines = [
            f"Estimate: {self.estimate}.",
            f"Confidence: {self.confidence}.",
        ]
        if self.missing:
            lines.append(f"Missing: {', '.join(self.missing)}.")
        return " ".join(lines)


@dataclass
class GovernorDriftWarning:
    """Warning when user is drifting between topics."""

    threads: list[str]
    question: str = "Pick one to finish first?"

    def format(self) -> str:
        """Format drift warning."""
        thread_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(self.threads))
        return f"We've got {len(self.threads)} threads going:\n{thread_list}\n\n{self.question}"


@dataclass
class GovernorDestructivePreview:
    """Preview for destructive actions."""

    actions: list[str]
    backup_path: str | None = None
    confirm_text: str = "Proceed? [y/n]"

    def format(self) -> str:
        """Format destructive action preview."""
        lines = ["This would:"]
        for action in self.actions:
            lines.append(f"  - {action}")

        if self.backup_path:
            lines.append(f"\nBackup will be created at: {self.backup_path}")

        lines.append(self.confirm_text)
        return "\n".join(lines)


@dataclass
class GovernorConflictWarning:
    """Warning when action conflicts with prior constraint."""

    constraint_id: str
    constraint_type: str  # "HARD" or "SOFT"
    constraint_date: str
    constraint_summary: str
    options: list[str]

    def format(self) -> str:
        """Format conflict warning."""
        lines = [
            "Noted. This conflicts with your earlier constraint:",
            "",
            f'> "{self.constraint_summary}" (#{self.constraint_id}, {self.constraint_type}, {self.constraint_date})',
            "",
            "Options:",
        ]
        for i, opt in enumerate(self.options, 1):
            lines.append(f"{i}. {opt}")
        return "\n".join(lines)


class GovernorResponseBuilder:
    """Builder for Governor-style responses.

    Enforces Governor's behavioral contracts:
    - Separate proposal from commitment
    - Expose reason for blocks in one line
    - Prefer reversibility: preview → diff → commit
    - Keep receipts
    - Default to low interference
    """

    def __init__(self, profile: GovernorVoiceProfile | None = None):
        self.profile = profile or GovernorVoiceProfile()
        self._content_lines: list[str] = []
        self._notes: list[str] = []
        self._footer: GovernorFooter | None = None

    def add_line(self, line: str) -> GovernorResponseBuilder:
        """Add a content line."""
        # Check for banned patterns
        violations = detect_governor_violations(line)
        if violations:
            # Don't add - Governor wouldn't say this
            # In strict mode, this would raise
            pass
        else:
            self._content_lines.append(line)
        return self

    def add_lines(self, lines: list[str]) -> GovernorResponseBuilder:
        """Add multiple content lines."""
        for line in lines:
            self.add_line(line)
        return self

    def add_note(self, note: str) -> GovernorResponseBuilder:
        """Add a note."""
        self._notes.append(note)
        return self

    def set_footer(self, footer: GovernorFooter) -> GovernorResponseBuilder:
        """Set the footer."""
        self._footer = footer
        return self

    def ok(self) -> GovernorResponseBuilder:
        """Set OK footer."""
        self._footer = GovernorFooter(type=GovernorFooterType.OK)
        return self

    def blocked(self, reason: str, fix: str | None = None) -> GovernorResponseBuilder:
        """Set BLOCKED footer."""
        self._footer = GovernorFooter(
            type=GovernorFooterType.BLOCKED,
            reason=reason,
            fix=fix,
        )
        return self

    def warn(self, reason: str, recommendation: str | None = None) -> GovernorResponseBuilder:
        """Set WARN footer."""
        self._footer = GovernorFooter(
            type=GovernorFooterType.WARN,
            reason=reason,
            fix=recommendation,
        )
        return self

    def ask(self, question: str) -> GovernorResponseBuilder:
        """Set ASK footer."""
        self._footer = GovernorFooter(
            type=GovernorFooterType.ASK,
            reason=question,
        )
        return self

    def note(self, info: str) -> GovernorResponseBuilder:
        """Set NOTE footer."""
        self._footer = GovernorFooter(
            type=GovernorFooterType.NOTE,
            reason=info,
        )
        return self

    def build(self) -> str:
        """Build the response."""
        parts = []

        # Main content
        if self._content_lines:
            parts.append("\n".join(self._content_lines))

        # Notes section
        if self._notes:
            parts.append("\nNotes:")
            for n in self._notes:
                parts.append(f"- {n}")

        # Footer (always present if governance.status_footer is True)
        if self._footer and self.profile.governance.status_footer:
            parts.append("")  # Blank line before footer
            parts.append(self._footer.format())
        elif self.profile.governance.status_footer:
            # Default to OK if no footer set
            parts.append("")
            parts.append("Governor: OK")

        return "\n".join(parts)


# =============================================================================
# Governor Voice Controller
# =============================================================================


class GovernorVoiceController:
    """Controller for Governor-mode operation.

    Governor is the default puppet profile that demonstrates:
    - Constraint-forward operation
    - Visible governance
    - Proposal/commit separation
    - Receipt-keeping
    - Low interference

    This is the "oh shit, this is real" moment in puppet form.
    """

    def __init__(self, profile: GovernorVoiceProfile | None = None):
        self.profile = profile or GovernorVoiceProfile()
        self._character = GOVERNOR_CHARACTER
        self._puppet_controller = PuppetModeController(
            config=PuppetModeConfig(
                character=self._character,
                strict_mode=True,  # Governor doesn't cut corners
            )
        )

    def check_text(self, text: str) -> PuppetModeResult:
        """Check text against Governor's constraints.

        Adds Governor-specific banned pattern detection on top of
        standard puppet mode checks.
        """
        # First, run standard puppet mode checks
        result = self._puppet_controller.check_text(text)

        # Add Governor-specific violations
        governor_violations = detect_governor_violations(text)
        for pattern in governor_violations:
            result.violations.append(CharacterViolation(
                type=CharacterViolationType.TONE_ENVELOPE,
                description="Governor banned pattern detected",
                severity=0.5,
                detail=pattern,
            ))

        return result

    def create_response(self) -> GovernorResponseBuilder:
        """Create a new Governor response builder."""
        return GovernorResponseBuilder(self.profile)

    def format_uncertainty(
        self,
        estimate: str,
        confidence: str,
        missing: list[str],
    ) -> str:
        """Format uncertainty the Governor way."""
        return GovernorUncertainty(
            estimate=estimate,
            confidence=confidence,
            missing=missing,
        ).format()

    def format_drift_warning(self, threads: list[str]) -> str:
        """Format a drift warning when user has multiple threads."""
        return GovernorDriftWarning(threads=threads).format()

    def format_destructive_preview(
        self,
        actions: list[str],
        backup_path: str | None = None,
    ) -> str:
        """Format a preview for destructive actions."""
        return GovernorDestructivePreview(
            actions=actions,
            backup_path=backup_path,
        ).format()

    def format_conflict_warning(
        self,
        constraint_id: str,
        constraint_type: str,
        constraint_date: str,
        constraint_summary: str,
        options: list[str],
    ) -> str:
        """Format a warning when action conflicts with prior constraint."""
        return GovernorConflictWarning(
            constraint_id=constraint_id,
            constraint_type=constraint_type,
            constraint_date=constraint_date,
            constraint_summary=constraint_summary,
            options=options,
        ).format()

    def should_deflect(self, domain: str) -> bool:
        """Check if Governor should deflect this domain."""
        return domain in self.profile.domain_deflections

    def has_affinity(self, domain: str) -> bool:
        """Check if Governor has affinity for this domain."""
        return domain in self.profile.domain_affinities


# Default Governor voice instance
DEFAULT_GOVERNOR_VOICE = GovernorVoiceController()
