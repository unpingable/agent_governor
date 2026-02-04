"""
CharacterState: The stateful tracking layer for narrative constraints.

Unlike Bible (static decisions) and Canon (events), CharacterState tracks
things that change over time:
- Motivations: what characters want and why (can conflict, decay, resolve)
- Beliefs: what characters think is true (may differ from world truth)
- Constraints: what makes certain actions hard for characters

This is the "who knows what, when" and "why would they do that" layer.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import (
    Motivation,
    MotivationType,
    Belief,
    BehavioralConstraint,
    NarrativeWarning,
)


class CharacterState:
    """
    Tracks the evolving internal state of characters.

    Bible says WHO they are (static).
    Canon says WHAT happened (facts).
    CharacterState says WHY they act and WHAT they believe (stateful).
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state_dir = project_dir / ".fiction-gov" / "state"

        self._motivations: dict[str, Motivation] = {}  # id -> Motivation
        self._beliefs: dict[str, Belief] = {}  # id -> Belief
        self._constraints: dict[str, BehavioralConstraint] = {}  # id -> Constraint

        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create state directory structure if needed."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        files = ["motivations.json", "beliefs.json", "constraints.json"]
        for f in files:
            path = self.state_dir / f
            if not path.exists():
                path.write_text("[]")

    def _load(self) -> None:
        """Load state from disk."""
        # Motivations
        mots_data = json.loads((self.state_dir / "motivations.json").read_text())
        self._motivations = {m["id"]: Motivation.from_dict(m) for m in mots_data}

        # Beliefs
        beliefs_data = json.loads((self.state_dir / "beliefs.json").read_text())
        self._beliefs = {b["id"]: Belief.from_dict(b) for b in beliefs_data}

        # Constraints
        cons_data = json.loads((self.state_dir / "constraints.json").read_text())
        self._constraints = {c["id"]: BehavioralConstraint.from_dict(c) for c in cons_data}

    def _save(self) -> None:
        """Save state to disk."""
        mots_data = [m.to_dict() for m in self._motivations.values()]
        (self.state_dir / "motivations.json").write_text(json.dumps(mots_data, indent=2))

        beliefs_data = [b.to_dict() for b in self._beliefs.values()]
        (self.state_dir / "beliefs.json").write_text(json.dumps(beliefs_data, indent=2))

        cons_data = [c.to_dict() for c in self._constraints.values()]
        (self.state_dir / "constraints.json").write_text(json.dumps(cons_data, indent=2))

    # =========================================================================
    # MOTIVATION METHODS
    # =========================================================================

    def add_motivation(
        self,
        character: str,
        description: str,
        type: MotivationType = MotivationType.GOAL,
        intensity: int = 5,
        as_of_chapter: int = 0,
        decay_rate: float = 0.0,
        source_event: str | None = None,
    ) -> Motivation:
        """Add a motivation for a character."""
        mot = Motivation(
            character=character,
            description=description,
            type=type,
            intensity=intensity,
            as_of_chapter=as_of_chapter,
            decay_rate=decay_rate,
            source_event=source_event,
        )
        self._motivations[str(mot.id)] = mot
        self._save()
        return mot

    def get_motivation(self, motivation_id: str | UUID) -> Motivation | None:
        """Get a motivation by ID."""
        return self._motivations.get(str(motivation_id))

    def motivations_for_character(
        self,
        character: str,
        active_only: bool = True,
        at_chapter: int | None = None,
    ) -> list[Motivation]:
        """Get motivations for a character, optionally filtered."""
        char_lower = character.lower()
        result = [
            m for m in self._motivations.values()
            if m.character.lower() == char_lower
        ]

        if active_only:
            result = [m for m in result if m.is_active]

        if at_chapter is not None:
            # Only include motivations that existed by this chapter
            result = [m for m in result if m.as_of_chapter <= at_chapter]
            # Exclude resolved motivations (if resolved before this chapter)
            result = [
                m for m in result
                if m.resolved_at_chapter is None or m.resolved_at_chapter > at_chapter
            ]

        return sorted(result, key=lambda m: -m.intensity)

    def resolve_motivation(
        self,
        motivation_id: str | UUID,
        chapter: int,
        resolution: str = "achieved",
    ) -> Motivation | None:
        """Mark a motivation as resolved."""
        mot = self.get_motivation(motivation_id)
        if not mot:
            return None

        mot.resolved_at_chapter = chapter
        mot.resolution = resolution
        self._save()
        return mot

    def add_motivation_conflict(
        self,
        motivation_id: str | UUID,
        conflicts_with_id: str | UUID,
    ) -> bool:
        """Mark two motivations as conflicting."""
        mot = self.get_motivation(motivation_id)
        if not mot:
            return False

        conflict_id = str(conflicts_with_id)
        if conflict_id not in mot.conflicts_with:
            mot.conflicts_with.append(conflict_id)
            self._save()
        return True

    def conflicting_motivations(self, character: str, at_chapter: int) -> list[tuple[Motivation, Motivation]]:
        """Find pairs of conflicting active motivations for a character."""
        active = self.motivations_for_character(character, active_only=True, at_chapter=at_chapter)
        conflicts = []

        for mot in active:
            for conflict_id in mot.conflicts_with:
                conflict = self.get_motivation(conflict_id)
                if conflict and conflict.is_active:
                    # Avoid duplicates (A conflicts B, B conflicts A)
                    pair = tuple(sorted([mot, conflict], key=lambda m: str(m.id)))
                    if pair not in conflicts:
                        conflicts.append(pair)

        return conflicts

    # =========================================================================
    # BELIEF METHODS
    # =========================================================================

    def add_belief(
        self,
        character: str,
        belief: str,
        learned_at_chapter: int,
        is_true: bool | None = None,
        confidence: int = 5,
        source: str | None = None,
    ) -> Belief:
        """Add a belief for a character."""
        b = Belief(
            character=character,
            belief=belief,
            is_true=is_true,
            confidence=confidence,
            learned_at_chapter=learned_at_chapter,
            source=source,
        )
        self._beliefs[str(b.id)] = b
        self._save()
        return b

    def get_belief(self, belief_id: str | UUID) -> Belief | None:
        """Get a belief by ID."""
        return self._beliefs.get(str(belief_id))

    def beliefs_for_character(
        self,
        character: str,
        held_only: bool = True,
        at_chapter: int | None = None,
    ) -> list[Belief]:
        """Get beliefs for a character, optionally filtered."""
        char_lower = character.lower()
        result = [
            b for b in self._beliefs.values()
            if b.character.lower() == char_lower
        ]

        if held_only:
            result = [b for b in result if b.is_held]

        if at_chapter is not None:
            # Only include beliefs learned by this chapter
            result = [b for b in result if b.learned_at_chapter <= at_chapter]
            # Exclude invalidated beliefs (if invalidated before this chapter)
            result = [
                b for b in result
                if b.invalidated_at_chapter is None or b.invalidated_at_chapter > at_chapter
            ]

        return sorted(result, key=lambda b: -b.confidence)

    def invalidate_belief(
        self,
        belief_id: str | UUID,
        chapter: int,
    ) -> Belief | None:
        """Mark a belief as invalidated (character learned it was wrong)."""
        belief = self.get_belief(belief_id)
        if not belief:
            return None

        belief.invalidated_at_chapter = chapter
        self._save()
        return belief

    def character_believes(
        self,
        character: str,
        about: str,
        at_chapter: int,
    ) -> Belief | None:
        """Check if character has a belief about something at a given chapter."""
        beliefs = self.beliefs_for_character(character, held_only=True, at_chapter=at_chapter)
        about_lower = about.lower()

        for belief in beliefs:
            if about_lower in belief.belief.lower():
                return belief

        return None

    def false_beliefs(self, character: str, at_chapter: int | None = None) -> list[Belief]:
        """Get beliefs the character holds that are actually false."""
        beliefs = self.beliefs_for_character(character, held_only=True, at_chapter=at_chapter)
        return [b for b in beliefs if b.is_true is False]

    # =========================================================================
    # CONSTRAINT METHODS
    # =========================================================================

    def add_constraint(
        self,
        character: str,
        action_type: str,
        constraint: str,
        cost: str | None = None,
        prerequisites: list[str] | None = None,
        exceptions: list[str] | None = None,
        as_of_chapter: int = 0,
        source: str | None = None,
    ) -> BehavioralConstraint:
        """Add a behavioral constraint for a character."""
        c = BehavioralConstraint(
            character=character,
            action_type=action_type,
            constraint=constraint,
            cost=cost,
            prerequisites=prerequisites or [],
            exceptions=exceptions or [],
            as_of_chapter=as_of_chapter,
            source=source,
        )
        self._constraints[str(c.id)] = c
        self._save()
        return c

    def get_constraint(self, constraint_id: str | UUID) -> BehavioralConstraint | None:
        """Get a constraint by ID."""
        return self._constraints.get(str(constraint_id))

    def constraints_for_character(
        self,
        character: str,
        action_type: str | None = None,
    ) -> list[BehavioralConstraint]:
        """Get constraints for a character, optionally filtered by action type."""
        char_lower = character.lower()
        result = [
            c for c in self._constraints.values()
            if c.character.lower() == char_lower
        ]

        if action_type:
            type_lower = action_type.lower()
            result = [c for c in result if c.action_type.lower() == type_lower]

        return result

    def action_cost(self, character: str, action_type: str) -> list[BehavioralConstraint]:
        """Get constraints that would make an action costly for a character."""
        return self.constraints_for_character(character, action_type)

    # =========================================================================
    # VALIDATION / WARNING GENERATION
    # =========================================================================

    def check_action(
        self,
        character: str,
        action: str,
        chapter: int,
        action_type: str | None = None,
    ) -> list[NarrativeWarning]:
        """
        Check if an action would violate character state.

        Returns warnings (not errors) - these flag potential issues,
        not definitive problems.
        """
        warnings = []

        # Check motivation conflicts
        conflicts = self.conflicting_motivations(character, chapter)
        if conflicts:
            for mot_a, mot_b in conflicts:
                warnings.append(NarrativeWarning(
                    character=character,
                    chapter=chapter,
                    warning_type="motivation_conflict",
                    message=f"Character has conflicting motivations: '{mot_a.description}' vs '{mot_b.description}'",
                    details={"motivation_a": str(mot_a.id), "motivation_b": str(mot_b.id)},
                    suggestion="This tension could be dramatic - ensure the scene acknowledges it",
                ))

        # Check behavioral constraints if action type provided
        if action_type:
            constraints = self.constraints_for_character(character, action_type)
            for c in constraints:
                warnings.append(NarrativeWarning(
                    character=character,
                    chapter=chapter,
                    warning_type="constraint_breach",
                    message=f"Action '{action_type}' conflicts with constraint: {c.constraint}",
                    details={
                        "constraint_id": str(c.id),
                        "cost": c.cost,
                        "prerequisites": c.prerequisites,
                        "exceptions": c.exceptions,
                    },
                    suggestion=f"If intentional, ensure prerequisites met or mark as breaking point. Cost: {c.cost or 'unstated'}",
                ))

        return warnings

    def check_knowledge(
        self,
        character: str,
        knows_about: str,
        chapter: int,
    ) -> NarrativeWarning | None:
        """
        Check if character could plausibly know something at a given chapter.

        Returns a warning if they're acting on knowledge they don't have.
        """
        belief = self.character_believes(character, knows_about, chapter)

        if belief is None:
            return NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="knowledge_gap",
                message=f"Character appears to act on knowledge they don't have: '{knows_about}'",
                details={"missing_knowledge": knows_about},
                severity="warning",
                suggestion=f"Add a scene where {character} learns this, or add a belief record",
            )

        return None

    def check_reaction(
        self,
        character: str,
        reacting_to: str,
        reaction: str,
        chapter: int,
    ) -> list[NarrativeWarning]:
        """
        Check if a reaction makes sense given character's beliefs.

        E.g., character can't mourn someone they don't know is dead.
        """
        warnings = []

        # Check if they have relevant beliefs
        belief = self.character_believes(character, reacting_to, chapter)
        if belief is None:
            warnings.append(NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="belief_violation",
                message=f"Character reacts to '{reacting_to}' but has no recorded belief about it",
                details={"reacting_to": reacting_to, "reaction": reaction},
                suggestion=f"Either add a belief about '{reacting_to}' or add a discovery scene",
            ))
        elif belief.is_true is False:
            # Character believes something false - their reaction might be based on wrong info
            warnings.append(NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="false_belief_reaction",
                message=f"Character's reaction based on false belief: '{belief.belief}'",
                details={"belief_id": str(belief.id), "reaction": reaction},
                severity="warning",
                suggestion="This could be dramatic irony - ensure the reader knows the truth",
            ))

        return warnings

    # =========================================================================
    # FORMATTING FOR PROMPTS
    # =========================================================================

    def format_character_state(self, character: str, at_chapter: int | None = None) -> str:
        """Format a character's current state for LLM prompt."""
        lines = [f"## {character}'s Internal State\n"]

        # Active motivations
        motivations = self.motivations_for_character(character, active_only=True, at_chapter=at_chapter)
        if motivations:
            lines.append("### Active Motivations")
            for m in motivations:
                intensity = m.effective_intensity(at_chapter) if at_chapter else m.intensity
                lines.append(f"- [{m.type.value.upper()}] {m.description} (intensity: {intensity:.1f})")
                if m.conflicts_with:
                    lines.append("  *Conflicts with other motivations*")
            lines.append("")

        # Current beliefs
        beliefs = self.beliefs_for_character(character, held_only=True, at_chapter=at_chapter)
        if beliefs:
            lines.append("### Current Beliefs")
            for b in beliefs:
                truth_marker = ""
                if b.is_true is False:
                    truth_marker = " [FALSE]"
                elif b.is_true is None:
                    truth_marker = " [?]"
                lines.append(f"- {b.belief}{truth_marker} (confidence: {b.confidence}/10)")
                if b.source:
                    lines.append(f"  Source: {b.source}")
            lines.append("")

        # Behavioral constraints
        constraints = self.constraints_for_character(character)
        if constraints:
            lines.append("### Behavioral Constraints")
            for c in constraints:
                lines.append(f"- **{c.action_type}**: {c.constraint}")
                if c.cost:
                    lines.append(f"  Cost: {c.cost}")
                if c.prerequisites:
                    lines.append(f"  Requires: {', '.join(c.prerequisites)}")
                if c.exceptions:
                    lines.append(f"  Exception: {', '.join(c.exceptions)}")
            lines.append("")

        return "\n".join(lines) if len(lines) > 1 else f"No recorded state for {character}."

    def format_all_for_prompt(self, at_chapter: int | None = None) -> str:
        """Format all character states for prompt."""
        characters = set()
        for m in self._motivations.values():
            characters.add(m.character)
        for b in self._beliefs.values():
            characters.add(b.character)
        for c in self._constraints.values():
            characters.add(c.character)

        if not characters:
            return "# Character States\n\nNo character state recorded yet."

        sections = ["# Character States\n"]
        for char in sorted(characters):
            sections.append(self.format_character_state(char, at_chapter))

        return "\n".join(sections)
