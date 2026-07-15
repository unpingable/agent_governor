# SPDX-License-Identifier: Apache-2.0
"""
Core types for the fiction governor.

These define the vocabulary for fiction constraints:
- Characters and their traits
- World rules and magic systems
- Banned tropes
- Canon events
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class FictionClaimType(Enum):
    """Types of claims that can be made about fiction content."""

    # Scene claims
    SCENE_CONTINUES = "scene_continues"
    """This scene follows logically from established events."""

    CHARACTER_PRESENT = "character_present"
    """Character is plausibly in this scene location."""

    TIMELINE_CONSISTENT = "timeline_consistent"
    """Events don't violate temporal order."""

    # Character claims
    IN_CHARACTER = "in_character"
    """Dialogue/action matches character bible."""

    RELATIONSHIP_ACCURATE = "relationship_accurate"
    """Characters interact per established relationship."""

    # World claims
    MAGIC_VALID = "magic_valid"
    """Magic use follows established rules."""

    WORLD_CONSISTENT = "world_consistent"
    """Setting details match established world."""

    # Style claims
    TONE_APPROPRIATE = "tone_appropriate"
    """Prose matches tone decisions."""

    NO_BANNED_TROPE = "no_banned_trope"
    """Content doesn't match banned patterns."""

    # Meta claims
    STYLE_CHOICE = "style_choice"
    """New decision about style/character/world."""

    CANON_UPDATE = "canon_update"
    """Recording what happened in new content."""


@dataclass
class FictionClaim:
    """A claim about fiction content."""

    type: FictionClaimType
    character: str | None = None
    characters: list[str] | None = None
    location: str | None = None
    chapter: int | None = None
    content: str | None = None
    rule_name: str | None = None

    def describe(self) -> str:
        """Human-readable description of the claim."""
        if self.type == FictionClaimType.IN_CHARACTER:
            return f"in_character({self.character})"
        elif self.type == FictionClaimType.CHARACTER_PRESENT:
            return f"character_present({self.character} at {self.location})"
        elif self.type == FictionClaimType.NO_BANNED_TROPE:
            return "no_banned_trope"
        elif self.type == FictionClaimType.TONE_APPROPRIATE:
            return "tone_appropriate"
        elif self.type == FictionClaimType.TIMELINE_CONSISTENT:
            return f"timeline_consistent(ch{self.chapter})"
        elif self.type == FictionClaimType.RELATIONSHIP_ACCURATE:
            chars = ", ".join(self.characters or [])
            return f"relationship_accurate({chars})"
        elif self.type == FictionClaimType.MAGIC_VALID:
            return "magic_valid"
        elif self.type == FictionClaimType.WORLD_CONSISTENT:
            return f"world_consistent({self.rule_name or 'general'})"
        else:
            return self.type.value


@dataclass
class CharacterTrait:
    """A character trait with optional nuance."""

    trait: str
    """The core trait (e.g., 'cynical', 'brave')."""

    nuance: str | None = None
    """Qualifier or exception (e.g., 'but privately romantic')."""

    note: str | None = None
    """Additional guidance for writing this trait."""

    def __str__(self) -> str:
        result = self.trait
        if self.nuance:
            result += f" (but {self.nuance})"
        return result


@dataclass
class CharacterVoice:
    """How a character speaks and thinks."""

    internal_monologue: str | None = None
    """Style of internal thoughts (e.g., 'sardonic, self-deprecating')."""

    dialogue: str | None = None
    """Style of spoken dialogue (e.g., 'clipped, deflects with humor')."""

    avoid: list[str] = field(default_factory=list)
    """Patterns to avoid in this character's voice."""


@dataclass
class Character:
    """A character in the story with their bible entry."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    role: str | None = None
    """Role in story (e.g., 'protagonist', 'antagonist', 'supporting')."""

    traits: list[CharacterTrait] = field(default_factory=list)
    voice: CharacterVoice | None = None

    anti_patterns: list[str] = field(default_factory=list)
    """Things this character would NEVER do."""

    notes: str | None = None
    """Free-form notes about the character."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_trait(self, trait: str, nuance: str | None = None, note: str | None = None) -> None:
        """Add a trait to this character."""
        self.traits.append(CharacterTrait(trait=trait, nuance=nuance, note=note))

    def add_anti_pattern(self, pattern: str) -> None:
        """Add something this character would never do."""
        self.anti_patterns.append(pattern)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "role": self.role,
            "traits": [
                {"trait": t.trait, "nuance": t.nuance, "note": t.note}
                for t in self.traits
            ],
            "voice": {
                "internal_monologue": self.voice.internal_monologue,
                "dialogue": self.voice.dialogue,
                "avoid": self.voice.avoid,
            } if self.voice else None,
            "anti_patterns": self.anti_patterns,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Character":
        voice = None
        if data.get("voice"):
            v = data["voice"]
            voice = CharacterVoice(
                internal_monologue=v.get("internal_monologue"),
                dialogue=v.get("dialogue"),
                avoid=v.get("avoid", []),
            )

        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            role=data.get("role"),
            traits=[
                CharacterTrait(
                    trait=t["trait"],
                    nuance=t.get("nuance"),
                    note=t.get("note"),
                )
                for t in data.get("traits", [])
            ],
            voice=voice,
            anti_patterns=data.get("anti_patterns", []),
            notes=data.get("notes"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def format_for_prompt(self) -> str:
        """Format character bible for inclusion in LLM prompt."""
        lines = [f"### {self.name}"]
        if self.role:
            lines.append(f"Role: {self.role}")

        if self.traits:
            lines.append("Traits:")
            for t in self.traits:
                lines.append(f"  - {t}")
                if t.note:
                    lines.append(f"    Note: {t.note}")

        if self.voice:
            lines.append("Voice:")
            if self.voice.internal_monologue:
                lines.append(f"  - Internal: {self.voice.internal_monologue}")
            if self.voice.dialogue:
                lines.append(f"  - Dialogue: {self.voice.dialogue}")
            if self.voice.avoid:
                lines.append(f"  - Avoid: {', '.join(self.voice.avoid)}")

        if self.anti_patterns:
            lines.append("Would NEVER:")
            for ap in self.anti_patterns:
                lines.append(f"  - {ap}")

        return "\n".join(lines)


@dataclass
class WorldRule:
    """A rule about how the world works."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    category: str | None = None
    """Category (e.g., 'magic', 'society', 'geography')."""

    rule: str = ""
    """The rule itself."""

    implications: list[str] = field(default_factory=list)
    """What this rule implies for the story."""

    exceptions: list[str] = field(default_factory=list)
    """Known exceptions to this rule."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "category": self.category,
            "rule": self.rule,
            "implications": self.implications,
            "exceptions": self.exceptions,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldRule":
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            category=data.get("category"),
            rule=data["rule"],
            implications=data.get("implications", []),
            exceptions=data.get("exceptions", []),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class BannedTrope:
    """A trope that should not appear in the story."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    """Name of the trope (e.g., 'chosen_one', 'love_triangle')."""

    reason: str = ""
    """Why this trope is banned."""

    patterns: list[str] = field(default_factory=list)
    """Text patterns that indicate this trope."""

    examples: list[str] = field(default_factory=list)
    """Examples of what this trope looks like."""

    severity: str = "error"
    """'error' (reject) or 'warning' (flag but allow)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "reason": self.reason,
            "patterns": self.patterns,
            "examples": self.examples,
            "severity": self.severity,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BannedTrope":
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            reason=data["reason"],
            patterns=data.get("patterns", []),
            examples=data.get("examples", []),
            severity=data.get("severity", "error"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class ToneSettings:
    """Tone and style settings for the story."""

    genre: str | None = None
    """Primary genre (e.g., 'literary fantasy')."""

    not_genres: list[str] = field(default_factory=list)
    """Genres to avoid (e.g., 'YA', 'cozy')."""

    prose_style: str | None = None
    """Description of prose style (e.g., 'precise, sensory')."""

    pacing: str | None = None
    """Pacing notes (e.g., 'slow burn')."""

    avoid: list[str] = field(default_factory=list)
    """Specific style elements to avoid."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "genre": self.genre,
            "not_genres": self.not_genres,
            "prose_style": self.prose_style,
            "pacing": self.pacing,
            "avoid": self.avoid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToneSettings":
        return cls(
            genre=data.get("genre"),
            not_genres=data.get("not_genres", []),
            prose_style=data.get("prose_style"),
            pacing=data.get("pacing"),
            avoid=data.get("avoid", []),
        )

    def format_for_prompt(self) -> str:
        """Format tone settings for LLM prompt."""
        lines = ["### Tone & Style"]
        if self.genre:
            lines.append(f"Genre: {self.genre}")
        if self.not_genres:
            lines.append(f"NOT: {', '.join(self.not_genres)}")
        if self.prose_style:
            lines.append(f"Prose: {self.prose_style}")
        if self.pacing:
            lines.append(f"Pacing: {self.pacing}")
        if self.avoid:
            lines.append(f"Avoid: {', '.join(self.avoid)}")
        return "\n".join(lines)


@dataclass
class CanonEvent:
    """An event that happened in the story (fact)."""

    id: UUID = field(default_factory=uuid4)
    chapter: int = 0
    summary: str = ""
    """Brief summary of what happened."""

    characters: list[str] = field(default_factory=list)
    """Characters involved in this event."""

    location: str | None = None
    """Where this event took place."""

    establishes: list[str] = field(default_factory=list)
    """What this event establishes for the story."""

    manuscript_ref: str | None = None
    """Reference to manuscript (e.g., 'chapter_03.md:45-78')."""

    quote: str | None = None
    """Key quote from the manuscript."""

    timestamp_in_story: str | None = None
    """When this happened in story time (if specified)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "chapter": self.chapter,
            "summary": self.summary,
            "characters": self.characters,
            "location": self.location,
            "establishes": self.establishes,
            "manuscript_ref": self.manuscript_ref,
            "quote": self.quote,
            "timestamp_in_story": self.timestamp_in_story,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonEvent":
        return cls(
            id=UUID(data["id"]),
            chapter=data["chapter"],
            summary=data["summary"],
            characters=data.get("characters", []),
            location=data.get("location"),
            establishes=data.get("establishes", []),
            manuscript_ref=data.get("manuscript_ref"),
            quote=data.get("quote"),
            timestamp_in_story=data.get("timestamp_in_story"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class Relationship:
    """The relationship between two characters."""

    id: UUID = field(default_factory=uuid4)
    character_a: str = ""
    character_b: str = ""
    status: str = ""
    """Current status (e.g., 'strangers', 'friends', 'enemies')."""

    dynamics: list[str] = field(default_factory=list)
    """Key dynamics (e.g., 'A doesn't trust B', 'B admires A')."""

    history: list[str] = field(default_factory=list)
    """History of their relationship."""

    as_of_chapter: int = 0
    """Chapter this relationship status is current as of."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "character_a": self.character_a,
            "character_b": self.character_b,
            "status": self.status,
            "dynamics": self.dynamics,
            "history": self.history,
            "as_of_chapter": self.as_of_chapter,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":
        return cls(
            id=UUID(data["id"]),
            character_a=data["character_a"],
            character_b=data["character_b"],
            status=data["status"],
            dynamics=data.get("dynamics", []),
            history=data.get("history", []),
            as_of_chapter=data.get("as_of_chapter", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


# ============================================================================
# NARRATIVE CONSTRAINT TYPES
# These track character state changes over time: motivations, beliefs, costs
# ============================================================================


class MotivationType(Enum):
    """Categories of character motivation."""

    GOAL = "goal"
    """Explicit objective the character is pursuing."""

    DRIVE = "drive"
    """Implicit force pushing the character (fear, desire, need)."""

    FEAR = "fear"
    """What the character is trying to avoid."""

    INCENTIVE = "incentive"
    """External pressure or reward shaping behavior."""


@dataclass
class Motivation:
    """
    A character motivation at a point in time.

    Motivations are stateful, time-indexed, and can conflict or decay.
    They explain WHY a character does things, not WHAT they are.
    """

    id: UUID = field(default_factory=uuid4)
    character: str = ""
    type: MotivationType = MotivationType.GOAL

    description: str = ""
    """What the motivation is (e.g., 'find her missing brother')."""

    intensity: int = 5
    """How strongly this motivation drives behavior (1-10)."""

    as_of_chapter: int = 0
    """When this motivation was established or last updated."""

    conflicts_with: list[str] = field(default_factory=list)
    """IDs of motivations this conflicts with (creates tension)."""

    resolved_at_chapter: int | None = None
    """Chapter where this motivation was resolved/achieved (None if active)."""

    resolution: str | None = None
    """How it was resolved (e.g., 'achieved', 'abandoned', 'replaced')."""

    decay_rate: float = 0.0
    """How quickly this motivation fades per chapter (0 = never, 1 = immediately)."""

    source_event: str | None = None
    """What triggered this motivation (reference to canon event)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self) -> bool:
        """Whether this motivation is still driving behavior."""
        return self.resolved_at_chapter is None

    def effective_intensity(self, at_chapter: int) -> float:
        """Calculate intensity after decay at a given chapter."""
        if not self.is_active:
            return 0.0
        chapters_elapsed = max(0, at_chapter - self.as_of_chapter)
        decayed = self.intensity * ((1 - self.decay_rate) ** chapters_elapsed)
        return max(0.0, decayed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "character": self.character,
            "type": self.type.value,
            "description": self.description,
            "intensity": self.intensity,
            "as_of_chapter": self.as_of_chapter,
            "conflicts_with": self.conflicts_with,
            "resolved_at_chapter": self.resolved_at_chapter,
            "resolution": self.resolution,
            "decay_rate": self.decay_rate,
            "source_event": self.source_event,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Motivation":
        return cls(
            id=UUID(data["id"]),
            character=data["character"],
            type=MotivationType(data["type"]),
            description=data["description"],
            intensity=data.get("intensity", 5),
            as_of_chapter=data.get("as_of_chapter", 0),
            conflicts_with=data.get("conflicts_with", []),
            resolved_at_chapter=data.get("resolved_at_chapter"),
            resolution=data.get("resolution"),
            decay_rate=data.get("decay_rate", 0.0),
            source_event=data.get("source_event"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


class TransmissionKind(str, Enum):
    """How a character came to hold a belief — the transmission path.

    Closed vocabulary (2026-07-15). Free-form ``Belief.source`` let a belief
    assert its own basis: ``source="witnessed"`` was a string nobody checked
    against canon, so "the character knows something they never witnessed"
    was unrepresentable-as-an-error rather than caught. That is an
    unauthorized projection across an epistemic boundary — the same crime the
    rest of the constellation refuses, in nicer prose.

    ``UNSPECIFIED`` is the honest unknown (legacy beliefs, unmigrated notes).
    It is a member so that absence of a path is *sayable*; it never counts as
    a verified path, and the verifier reports it rather than passing it.
    """

    WITNESSED = "witnessed"  # present at a canon event — CHECKABLE against presence
    TOLD_BY = "told_by"  # another character told them — CHECKABLE (teller + timing)
    INFERRED = "inferred"  # reasoned from other knowledge — self-declared, not checked
    ASSUMED = "assumed"  # assumed without basis (may be false) — self-declared
    UNSPECIFIED = "unspecified"  # honest unknown; never a verified path


@dataclass(frozen=True)
class TransmissionPath:
    """A structured claim about how a belief was acquired.

    Refuses at construction when the claimed kind lacks its referent — a
    ``WITNESSED`` path with no event to check against is not a weaker claim,
    it is an uncheckable one, and this vocabulary exists precisely so that
    uncheckable claims cannot masquerade as checked. Same law as
    ``operator_mode`` and the six-axis vocabulary: the class is earned by its
    evidence, never asserted by its name.
    """

    kind: TransmissionKind
    event_id: UUID | None = None  # WITNESSED: the canon event attended
    teller: str | None = None  # TOLD_BY: who told them
    at_chapter: int | None = None  # TOLD_BY: when the telling happened
    note: str | None = None  # free text — display only, never load-bearing

    def __post_init__(self) -> None:
        if self.kind is TransmissionKind.WITNESSED and self.event_id is None:
            raise ValueError(
                "TransmissionKind.WITNESSED requires event_id — a witnessed "
                "claim with no canon event to check is uncheckable, not weak"
            )
        if self.kind is TransmissionKind.TOLD_BY and not self.teller:
            raise ValueError(
                "TransmissionKind.TOLD_BY requires teller — an unattributed "
                "telling has no path to verify"
            )

    @property
    def is_checkable(self) -> bool:
        """Whether this path makes a claim canon can adjudicate."""
        return self.kind in (TransmissionKind.WITNESSED, TransmissionKind.TOLD_BY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "event_id": str(self.event_id) if self.event_id else None,
            "teller": self.teller,
            "at_chapter": self.at_chapter,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransmissionPath":
        return cls(
            kind=TransmissionKind(data["kind"]),
            event_id=UUID(data["event_id"]) if data.get("event_id") else None,
            teller=data.get("teller"),
            at_chapter=data.get("at_chapter"),
            note=data.get("note"),
        )

    @classmethod
    def unspecified(cls, note: str | None = None) -> "TransmissionPath":
        """The honest unknown — an unmigrated or unstated path."""
        return cls(kind=TransmissionKind.UNSPECIFIED, note=note)


def migrate_legacy_source(source: str | None) -> TransmissionPath:
    """Map a legacy free-form ``Belief.source`` onto the closed vocabulary.

    Deliberately conservative: only the self-declaring kinds (inferred /
    assumed) are recognized outright, because they claim no external backing
    and so cannot launder one. A legacy ``"witnessed"`` or ``"told by X"``
    string CANNOT become a checkable path — it names no event and its teller
    was never bound to a scene — so it degrades to ``UNSPECIFIED`` carrying
    the original text as a display note. That is the honest reading: the old
    string was never evidence, and promoting it now would manufacture custody
    the data never had. Re-authoring those beliefs with real referents is the
    author's act, not a migration's.
    """

    if source is None or not source.strip():
        return TransmissionPath.unspecified()
    text = source.strip().lower()
    if text == "inferred":
        return TransmissionPath(kind=TransmissionKind.INFERRED, note=source)
    if text in ("assumed", "assumption"):
        return TransmissionPath(kind=TransmissionKind.ASSUMED, note=source)
    return TransmissionPath.unspecified(note=source)


@dataclass
class Belief:
    """
    What a character believes to be true (may differ from world truth).

    The crucial distinction: what is true in the world vs what this
    character believes. This catches impossible reactions, premature
    knowledge, and emotional responses that assume facts not yet learned.
    """

    id: UUID = field(default_factory=uuid4)
    character: str = ""

    belief: str = ""
    """What the character believes (e.g., 'Marcus is dead')."""

    is_true: bool | None = None
    """Whether this belief is actually true in the world (None = unknown)."""

    confidence: int = 5
    """How certain the character is (1-10)."""

    learned_at_chapter: int = 0
    """When the character learned/formed this belief."""

    source: str | None = None
    """How they learned it, free text (e.g., 'witnessed', 'told by X').

    DISPLAY ONLY as of 2026-07-15. Retained untouched so authored prose
    survives, but it is not the basis for any check — a string cannot be its
    own evidence. The typed ``transmission`` below carries the checkable
    claim. (Same split as nightshift's typed refusal beside its free-text
    ``blocked[]``.)
    """

    transmission: "TransmissionPath | None" = None
    """The typed, checkable transmission path. ``None`` on beliefs authored
    before the vocabulary existed; ``from_dict`` migrates legacy ``source``
    conservatively rather than inventing custody (see
    :func:`migrate_legacy_source`)."""

    contradicts_belief: str | None = None
    """ID of a belief this replaces (character changed their mind)."""

    invalidated_at_chapter: int | None = None
    """Chapter where character learned this was wrong (None if still held)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_held(self) -> bool:
        """Whether character still holds this belief."""
        return self.invalidated_at_chapter is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "character": self.character,
            "belief": self.belief,
            "is_true": self.is_true,
            "confidence": self.confidence,
            "learned_at_chapter": self.learned_at_chapter,
            "source": self.source,
            "transmission": self.transmission.to_dict() if self.transmission else None,
            "contradicts_belief": self.contradicts_belief,
            "invalidated_at_chapter": self.invalidated_at_chapter,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Belief":
        # Legacy beliefs carry only free-form `source`. Migrate conservatively
        # so an old string never becomes a checkable claim it never earned.
        raw = data.get("transmission")
        if raw is not None:
            transmission = TransmissionPath.from_dict(raw)
        elif "source" in data:
            transmission = migrate_legacy_source(data.get("source"))
        else:
            transmission = None
        return cls(
            id=UUID(data["id"]),
            character=data["character"],
            belief=data["belief"],
            is_true=data.get("is_true"),
            confidence=data.get("confidence", 5),
            learned_at_chapter=data.get("learned_at_chapter", 0),
            source=data.get("source"),
            transmission=transmission,
            contradicts_belief=data.get("contradicts_belief"),
            invalidated_at_chapter=data.get("invalidated_at_chapter"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class BehavioralConstraint:
    """
    What makes an action HARD for a character (not what's forbidden).

    Not "would they do this?" but:
    - What would make this action hard?
    - What cost would this impose?
    - What prior justification would be required?

    This keeps the system from policing creativity while flagging cheap moves.
    """

    id: UUID = field(default_factory=uuid4)
    character: str = ""

    action_type: str = ""
    """Category of action (e.g., 'violence', 'deception', 'betrayal', 'vulnerability')."""

    constraint: str = ""
    """What makes this hard (e.g., 'requires extreme provocation')."""

    cost: str | None = None
    """What it costs the character to do this (e.g., 'psychological damage', 'relationship rupture')."""

    prerequisites: list[str] = field(default_factory=list)
    """What must happen first (e.g., 'must be backed into corner', 'must see no alternative')."""

    exceptions: list[str] = field(default_factory=list)
    """When this constraint doesn't apply (e.g., 'if family is threatened')."""

    as_of_chapter: int = 0
    """Chapter this constraint was established."""

    source: str | None = None
    """Why this constraint exists (links to background/trauma/values)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "character": self.character,
            "action_type": self.action_type,
            "constraint": self.constraint,
            "cost": self.cost,
            "prerequisites": self.prerequisites,
            "exceptions": self.exceptions,
            "as_of_chapter": self.as_of_chapter,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BehavioralConstraint":
        return cls(
            id=UUID(data["id"]),
            character=data["character"],
            action_type=data["action_type"],
            constraint=data["constraint"],
            cost=data.get("cost"),
            prerequisites=data.get("prerequisites", []),
            exceptions=data.get("exceptions", []),
            as_of_chapter=data.get("as_of_chapter", 0),
            source=data.get("source"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class NarrativeWarning:
    """
    A gentle intervention about potential narrative issues.

    Not "this is wrong" but "this might need justification."
    """

    character: str
    chapter: int
    warning_type: str
    """Type: 'motivation_conflict', 'belief_violation', 'constraint_breach', 'knowledge_gap'."""

    message: str
    """The warning message."""

    details: dict[str, Any] = field(default_factory=dict)
    """Additional context (e.g., conflicting motivation IDs, missing belief)."""

    severity: str = "warning"
    """'warning' (flag but allow) or 'error' (requires justification)."""

    suggestion: str | None = None
    """How to resolve this (e.g., 'Add a scene where X learns Y')."""


# ============================================================================
# PLOT THREAD TYPES
# Track narrative threads: Chekhov's guns, foreshadowing, mysteries, arcs
# ============================================================================


class ThreadType(Enum):
    """Types of narrative threads."""

    CHEKHOV_GUN = "chekhov_gun"
    """Setup that must pay off (gun on wall in Act 1 must fire in Act 3)."""

    FORESHADOWING = "foreshadowing"
    """Hint at future events (subtle, may not be explicit payoff)."""

    MYSTERY = "mystery"
    """Question raised that needs answering."""

    CHARACTER_ARC = "character_arc"
    """Character growth/change trajectory."""

    SUBPLOT = "subplot"
    """Secondary story thread."""

    PROMISE = "promise"
    """Implicit promise to reader (genre expectations, etc.)."""

    SETUP = "setup"
    """General setup that needs payoff."""


class ThreadStatus(Enum):
    """Status of a plot thread."""

    PLANTED = "planted"
    """Thread has been introduced."""

    DEVELOPING = "developing"
    """Thread is being built upon."""

    RESOLVED = "resolved"
    """Thread has paid off / been resolved."""

    ABANDONED = "abandoned"
    """Thread was dropped (may be intentional or a plot hole)."""

    OVERDUE = "overdue"
    """Thread should have paid off by now."""


@dataclass
class PlotThread:
    """
    A narrative thread that needs tracking.

    Chekhov's principle: if you show a gun in Act 1, it must fire by Act 3.
    This tracks setups and their payoffs to catch dangling threads.
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    """Short name for the thread (e.g., 'mysterious letter', 'Elena's past')."""

    thread_type: ThreadType = ThreadType.SETUP
    """What kind of thread this is."""

    status: ThreadStatus = ThreadStatus.PLANTED
    """Current status of the thread."""

    description: str = ""
    """What the thread is about."""

    planted_chapter: int = 0
    """Chapter where this thread was introduced."""

    planted_text: str | None = None
    """Quote or reference to where it was planted."""

    characters: list[str] = field(default_factory=list)
    """Characters involved in this thread."""

    expected_payoff_by: int | None = None
    """Chapter by which this should resolve (None = no deadline)."""

    importance: int = 5
    """How important this thread is (1-10, affects overdue urgency)."""

    developments: list[dict[str, Any]] = field(default_factory=list)
    """List of {chapter, description} for thread developments."""

    resolved_chapter: int | None = None
    """Chapter where this was resolved (None if unresolved)."""

    resolution: str | None = None
    """How it was resolved."""

    notes: str | None = None
    """Author notes about this thread."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self) -> bool:
        """Whether this thread is still open."""
        return self.status in (ThreadStatus.PLANTED, ThreadStatus.DEVELOPING)

    @property
    def is_overdue(self) -> bool:
        """Whether this thread has passed its expected payoff."""
        if self.expected_payoff_by is None:
            return False
        return self.is_active and self.status != ThreadStatus.RESOLVED

    def add_development(self, chapter: int, description: str) -> None:
        """Add a development to this thread."""
        self.developments.append({
            "chapter": chapter,
            "description": description,
            "added_at": datetime.now(timezone.utc).isoformat(),
        })
        self.status = ThreadStatus.DEVELOPING

    def resolve(self, chapter: int, resolution: str) -> None:
        """Mark this thread as resolved."""
        self.resolved_chapter = chapter
        self.resolution = resolution
        self.status = ThreadStatus.RESOLVED

    def check_overdue(self, current_chapter: int) -> bool:
        """Check if thread is overdue and update status."""
        if self.expected_payoff_by and current_chapter > self.expected_payoff_by:
            if self.is_active:
                self.status = ThreadStatus.OVERDUE
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "thread_type": self.thread_type.value,
            "status": self.status.value,
            "description": self.description,
            "planted_chapter": self.planted_chapter,
            "planted_text": self.planted_text,
            "characters": self.characters,
            "expected_payoff_by": self.expected_payoff_by,
            "importance": self.importance,
            "developments": self.developments,
            "resolved_chapter": self.resolved_chapter,
            "resolution": self.resolution,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlotThread":
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            thread_type=ThreadType(data["thread_type"]),
            status=ThreadStatus(data["status"]),
            description=data["description"],
            planted_chapter=data.get("planted_chapter", 0),
            planted_text=data.get("planted_text"),
            characters=data.get("characters", []),
            expected_payoff_by=data.get("expected_payoff_by"),
            importance=data.get("importance", 5),
            developments=data.get("developments", []),
            resolved_chapter=data.get("resolved_chapter"),
            resolution=data.get("resolution"),
            notes=data.get("notes"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def format_for_prompt(self) -> str:
        """Format thread for LLM prompt context."""
        lines = [f"- {self.name} ({self.thread_type.value})"]
        lines.append(f"  Status: {self.status.value}")
        lines.append(f"  {self.description}")
        if self.expected_payoff_by:
            lines.append(f"  Expected payoff by chapter {self.expected_payoff_by}")
        if self.developments:
            latest = self.developments[-1]
            lines.append(f"  Latest: Ch{latest['chapter']} - {latest['description']}")
        return "\n".join(lines)


@dataclass
class SceneProposal:
    """
    A proposed scene awaiting approval.

    Part of the fiction-gov workflow: propose -> verify -> approve/reject.
    """

    id: UUID = field(default_factory=uuid4)
    chapter: int = 0
    scene_number: int | None = None

    title: str = ""
    """Brief title for the scene."""

    summary: str = ""
    """What happens in this scene."""

    characters: list[str] = field(default_factory=list)
    """Characters in this scene."""

    location: str | None = None
    """Where the scene takes place."""

    content: str | None = None
    """The actual prose content (if written)."""

    threads_advanced: list[str] = field(default_factory=list)
    """IDs of plot threads this scene advances."""

    threads_resolved: list[str] = field(default_factory=list)
    """IDs of plot threads this scene resolves."""

    canon_events: list[str] = field(default_factory=list)
    """Events this scene would establish."""

    status: str = "pending"
    """Status: 'pending', 'approved', 'rejected', 'revised'."""

    verification_result: dict[str, Any] | None = None
    """Result of fiction-gov verification."""

    rejection_reason: str | None = None
    """Why this was rejected (if rejected)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "chapter": self.chapter,
            "scene_number": self.scene_number,
            "title": self.title,
            "summary": self.summary,
            "characters": self.characters,
            "location": self.location,
            "content": self.content,
            "threads_advanced": self.threads_advanced,
            "threads_resolved": self.threads_resolved,
            "canon_events": self.canon_events,
            "status": self.status,
            "verification_result": self.verification_result,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneProposal":
        return cls(
            id=UUID(data["id"]),
            chapter=data["chapter"],
            scene_number=data.get("scene_number"),
            title=data["title"],
            summary=data["summary"],
            characters=data.get("characters", []),
            location=data.get("location"),
            content=data.get("content"),
            threads_advanced=data.get("threads_advanced", []),
            threads_resolved=data.get("threads_resolved", []),
            canon_events=data.get("canon_events", []),
            status=data.get("status", "pending"),
            verification_result=data.get("verification_result"),
            rejection_reason=data.get("rejection_reason"),
            created_at=datetime.fromisoformat(data["created_at"]),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
        )
