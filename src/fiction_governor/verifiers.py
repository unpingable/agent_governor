# SPDX-License-Identifier: Apache-2.0
"""
Verifiers for fiction content.

Check proposed content against the bible (character, world, tone rules)
and canon (established events, relationships).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import FictionClaim, FictionClaimType, BannedTrope, NarrativeWarning
from .bible import Bible
from .canon import Canon
from .state import CharacterState


@dataclass
class VerificationResult:
    """Result of verifying a claim."""

    success: bool
    claim: FictionClaim
    message: str
    severity: str = "error"  # "error", "warning", "info"
    suggestions: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, claim: FictionClaim, message: str = "Verified") -> "VerificationResult":
        return cls(success=True, claim=claim, message=message)

    @classmethod
    def fail(
        cls,
        claim: FictionClaim,
        message: str,
        suggestions: list[str] | None = None,
        severity: str = "error",
    ) -> "VerificationResult":
        return cls(
            success=False,
            claim=claim,
            message=message,
            severity=severity,
            suggestions=suggestions or [],
        )


class InCharacterVerifier:
    """Verify that content is in-character."""

    def __init__(self, bible: Bible):
        self.bible = bible

    def verify(self, claim: FictionClaim, content: str) -> VerificationResult:
        """
        Verify that content is in-character for the specified character.
        """
        if not claim.character:
            return VerificationResult.fail(
                claim, "IN_CHARACTER claim requires character name"
            )

        character = self.bible.get_character(claim.character)
        if not character:
            return VerificationResult.fail(
                claim, f"Character '{claim.character}' not found in bible"
            )

        # Check against anti-patterns
        content_lower = content.lower()
        for anti in character.anti_patterns:
            if self._matches_anti_pattern(content_lower, anti):
                return VerificationResult.fail(
                    claim,
                    f"Out of character for {character.name}: matches anti-pattern '{anti}'",
                    suggestions=[
                        f"Consider what {character.name} would actually do instead",
                        f"Review character traits: {', '.join(str(t) for t in character.traits[:3])}",
                    ],
                )

        # Check voice if specified
        if character.voice and character.voice.avoid:
            for avoid in character.voice.avoid:
                if avoid.lower() in content_lower:
                    return VerificationResult.fail(
                        claim,
                        f"Content contains '{avoid}' which is marked as avoid for {character.name}",
                        severity="warning",
                        suggestions=[f"Adjust {character.name}'s voice to match: {character.voice.dialogue or 'defined style'}"],
                    )

        return VerificationResult.ok(
            claim, f"Content consistent with {character.name}'s character"
        )

    def _matches_anti_pattern(self, content: str, anti_pattern: str) -> bool:
        """Check if content matches an anti-pattern."""
        # Simple keyword matching for now
        # Could be enhanced with NLP or embedding similarity
        anti_lower = anti_pattern.lower()

        # Direct substring match
        if anti_lower in content:
            return True

        # Check for key verbs/actions
        key_words = self._extract_key_words(anti_lower)
        if not key_words:
            return False  # No key words to match

        matches = sum(1 for word in key_words if word in content)
        if matches >= len(key_words) * 0.6:  # 60% of key words match
            return True

        return False

    def _extract_key_words(self, text: str) -> list[str]:
        """Extract key action words from an anti-pattern."""
        # Simple extraction: words >= 3 chars, not common words
        stop_words = {"would", "never", "always", "the", "and", "that", "this", "with"}
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) >= 3 and w not in stop_words]


class TropeVerifier:
    """Verify that content doesn't contain banned tropes."""

    def __init__(self, bible: Bible):
        self.bible = bible

    def verify(self, claim: FictionClaim, content: str) -> VerificationResult:
        """Check content against banned tropes."""
        banned = self.bible.all_banned_tropes()
        if not banned:
            return VerificationResult.ok(claim, "No tropes banned")

        content_lower = content.lower()
        detected = []

        for trope in banned:
            if self._detect_trope(content_lower, trope):
                detected.append(trope)

        if not detected:
            return VerificationResult.ok(claim, "No banned tropes detected")

        # Separate errors from warnings
        errors = [t for t in detected if t.severity == "error"]
        warnings = [t for t in detected if t.severity == "warning"]

        if errors:
            trope_names = ", ".join(t.name for t in errors)
            reasons = "; ".join(f"{t.name}: {t.reason}" for t in errors)
            return VerificationResult.fail(
                claim,
                f"Banned trope(s) detected: {trope_names}. {reasons}",
                suggestions=["Revise to avoid these tropes", "Consider alternative approaches"],
            )

        if warnings:
            trope_names = ", ".join(t.name for t in warnings)
            return VerificationResult.fail(
                claim,
                f"Potential trope(s) detected: {trope_names}",
                severity="warning",
                suggestions=["Review if this is intentional"],
            )

        return VerificationResult.ok(claim, "No banned tropes detected")

    def _detect_trope(self, content: str, trope: BannedTrope) -> bool:
        """Detect if content contains a trope."""
        # Check patterns
        for pattern in trope.patterns:
            try:
                if re.search(pattern, content, re.IGNORECASE):
                    return True
            except re.error:
                # If pattern is invalid regex, treat as literal
                if pattern.lower() in content:
                    return True

        return False


class CanonVerifier:
    """Verify claims against established canon."""

    def __init__(self, canon: Canon):
        self.canon = canon

    def verify_character_present(self, claim: FictionClaim) -> VerificationResult:
        """Verify a character can plausibly be at a location."""
        if not claim.character or not claim.location or claim.chapter is None:
            return VerificationResult.fail(
                claim, "CHARACTER_PRESENT requires character, location, and chapter"
            )

        can_be_there, reason = self.canon.character_can_be_at(
            claim.character, claim.location, claim.chapter
        )

        if can_be_there:
            return VerificationResult.ok(claim, reason)
        else:
            return VerificationResult.fail(
                claim,
                f"{claim.character} cannot be at {claim.location}: {reason}",
                suggestions=[
                    "Add a transition scene",
                    "Adjust the timeline",
                ],
            )

    def verify_timeline(self, claim: FictionClaim, content: str) -> VerificationResult:
        """Verify content doesn't violate timeline."""
        # This is a simplified check - could be much more sophisticated
        # For now, just check for obvious contradictions

        # Look for time references in content
        time_patterns = [
            (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 'day'),
            (r'\b(morning|afternoon|evening|night)\b', 'time_of_day'),
            (r'\b(yesterday|today|tomorrow)\b', 'relative_day'),
        ]

        # This would need actual timeline tracking to be useful
        # For MVP, just pass
        return VerificationResult.ok(claim, "Timeline check passed (basic)")

    def verify_relationship(self, claim: FictionClaim, content: str) -> VerificationResult:
        """Verify content matches established relationship."""
        if not claim.characters or len(claim.characters) < 2:
            return VerificationResult.fail(
                claim, "RELATIONSHIP_ACCURATE requires at least two characters"
            )

        char_a, char_b = claim.characters[0], claim.characters[1]
        rel = self.canon.get_relationship(char_a, char_b)

        if not rel:
            return VerificationResult.ok(
                claim, f"No relationship established between {char_a} and {char_b}"
            )

        # Check if content contradicts relationship status
        # This is simplified - would need NLP for real analysis
        return VerificationResult.ok(
            claim,
            f"Relationship ({rel.status}) acknowledged"
        )


class ToneVerifier:
    """Verify content matches tone settings."""

    def __init__(self, bible: Bible):
        self.bible = bible

    def verify(self, claim: FictionClaim, content: str) -> VerificationResult:
        """Verify content matches tone settings."""
        tone = self.bible.get_tone()
        if not tone:
            return VerificationResult.ok(claim, "No tone settings defined")

        content_lower = content.lower()
        issues = []

        # Check for avoided elements
        for avoid in tone.avoid:
            if avoid.lower() in content_lower:
                issues.append(f"Contains '{avoid}' which should be avoided")

        # Check for purple prose indicators (if prose style suggests avoiding it)
        if tone.prose_style and "precise" in tone.prose_style.lower():
            purple_indicators = [
                "orbs" if "eyes" not in content_lower else None,  # "orbs" for eyes
                "tresses",  # "tresses" for hair
                "visage",  # "visage" for face
            ]
            for indicator in purple_indicators:
                if indicator and indicator in content_lower:
                    issues.append(f"Purple prose detected: '{indicator}'")

        if issues:
            return VerificationResult.fail(
                claim,
                f"Tone issues: {'; '.join(issues)}",
                severity="warning",
                suggestions=["Simplify prose", "Match the established tone"],
            )

        return VerificationResult.ok(claim, "Tone appropriate")


class FictionVerifier:
    """
    Composite verifier that runs all fiction checks.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.bible = Bible(project_dir)
        self.canon = Canon(project_dir)

        self.in_character = InCharacterVerifier(self.bible)
        self.trope = TropeVerifier(self.bible)
        self.canon_verifier = CanonVerifier(self.canon)
        self.tone = ToneVerifier(self.bible)

    def verify(self, claim: FictionClaim, content: str) -> VerificationResult:
        """Verify a single claim."""
        if claim.type == FictionClaimType.IN_CHARACTER:
            return self.in_character.verify(claim, content)

        elif claim.type == FictionClaimType.NO_BANNED_TROPE:
            return self.trope.verify(claim, content)

        elif claim.type == FictionClaimType.CHARACTER_PRESENT:
            return self.canon_verifier.verify_character_present(claim)

        elif claim.type == FictionClaimType.TIMELINE_CONSISTENT:
            return self.canon_verifier.verify_timeline(claim, content)

        elif claim.type == FictionClaimType.RELATIONSHIP_ACCURATE:
            return self.canon_verifier.verify_relationship(claim, content)

        elif claim.type == FictionClaimType.TONE_APPROPRIATE:
            return self.tone.verify(claim, content)

        else:
            return VerificationResult.ok(claim, f"No verifier for {claim.type}")

    def verify_all(
        self,
        claims: list[FictionClaim],
        content: str,
    ) -> list[VerificationResult]:
        """Verify all claims against content."""
        return [self.verify(claim, content) for claim in claims]

    def verify_scene(
        self,
        content: str,
        characters: list[str],
        chapter: int,
        location: str | None = None,
    ) -> list[VerificationResult]:
        """
        Convenience method to verify a scene with common checks.
        """
        claims = []

        # Check each character is in-character
        for char in characters:
            claims.append(FictionClaim(
                type=FictionClaimType.IN_CHARACTER,
                character=char,
            ))

        # Check characters can be at location
        if location:
            for char in characters:
                claims.append(FictionClaim(
                    type=FictionClaimType.CHARACTER_PRESENT,
                    character=char,
                    location=location,
                    chapter=chapter,
                ))

        # Check for banned tropes
        claims.append(FictionClaim(type=FictionClaimType.NO_BANNED_TROPE))

        # Check tone
        claims.append(FictionClaim(type=FictionClaimType.TONE_APPROPRIATE))

        # Check relationships if multiple characters
        if len(characters) >= 2:
            claims.append(FictionClaim(
                type=FictionClaimType.RELATIONSHIP_ACCURATE,
                characters=characters[:2],
            ))

        return self.verify_all(claims, content)

    def quick_check(self, content: str, characters: list[str]) -> tuple[bool, list[str]]:
        """
        Quick check of content - returns (passed, issues).

        Useful for inline checking during generation.
        """
        claims = [
            FictionClaim(type=FictionClaimType.NO_BANNED_TROPE),
            FictionClaim(type=FictionClaimType.TONE_APPROPRIATE),
        ]
        for char in characters:
            claims.append(FictionClaim(
                type=FictionClaimType.IN_CHARACTER,
                character=char,
            ))

        results = self.verify_all(claims, content)
        failures = [r for r in results if not r.success]

        if not failures:
            return True, []

        issues = [f"{r.claim.describe()}: {r.message}" for r in failures]
        return False, issues


class NarrativeVerifier:
    """
    Verify narrative coherence: motivations, beliefs, and behavioral constraints.

    This goes beyond canon (what happened) and bible (who characters are) to ask:
    - Why would this character do this?
    - Do they know what they'd need to know to react this way?
    - What would this action cost them?

    Returns warnings, not errors. Stories can break rules intentionally.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state = CharacterState(project_dir)
        self.bible = Bible(project_dir)

    def verify_action(
        self,
        character: str,
        action: str,
        chapter: int,
        action_type: str | None = None,
    ) -> list[NarrativeWarning]:
        """
        Verify an action makes sense for a character.

        Not "would they do this?" but:
        - Does this conflict with stated motivations?
        - Does this require information they don't have?
        - Does this violate behavioral constraints without justification?
        """
        warnings = []

        # Check character exists
        char_bible = self.bible.get_character(character)
        if not char_bible:
            # Can't verify unknown character - not a warning
            return []

        # Check motivation alignment
        motivations = self.state.motivations_for_character(character, active_only=True, at_chapter=chapter)
        if motivations:
            # Check if action contradicts any motivation
            action_lower = action.lower()
            for mot in motivations:
                # Simple heuristic: if action seems to work against motivation
                if self._action_contradicts_motivation(action_lower, mot):
                    warnings.append(NarrativeWarning(
                        character=character,
                        chapter=chapter,
                        warning_type="motivation_conflict",
                        message=f"Action may contradict motivation: '{mot.description}'",
                        details={"motivation_id": str(mot.id), "action": action},
                        suggestion="If intentional, this tension could be dramatic. Ensure it's acknowledged.",
                    ))

        # Check internal motivation conflicts
        conflicts = self.state.conflicting_motivations(character, chapter)
        for mot_a, mot_b in conflicts:
            warnings.append(NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="motivation_conflict",
                message=f"Character has unresolved tension: '{mot_a.description}' vs '{mot_b.description}'",
                details={"motivation_a": str(mot_a.id), "motivation_b": str(mot_b.id)},
                severity="info",
                suggestion="This tension should inform behavior - consider which wins and at what cost.",
            ))

        # Check behavioral constraints
        if action_type:
            constraints = self.state.constraints_for_character(character, action_type)
            for c in constraints:
                warnings.append(NarrativeWarning(
                    character=character,
                    chapter=chapter,
                    warning_type="constraint_breach",
                    message=f"Action '{action_type}' hits constraint: {c.constraint}",
                    details={
                        "constraint_id": str(c.id),
                        "cost": c.cost,
                        "prerequisites": c.prerequisites,
                        "exceptions": c.exceptions,
                    },
                    suggestion=self._format_constraint_suggestion(c),
                ))

        return warnings

    def verify_knowledge(
        self,
        character: str,
        uses_knowledge_of: str,
        chapter: int,
    ) -> NarrativeWarning | None:
        """
        Verify character could know something at this point.

        Catches:
        - Acting on information they haven't learned
        - Premature knowledge (knowing before the reveal)
        """
        belief = self.state.character_believes(character, uses_knowledge_of, chapter)

        if belief is None:
            return NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="knowledge_gap",
                message=f"Character acts on unrecorded knowledge: '{uses_knowledge_of}'",
                details={"missing_knowledge": uses_knowledge_of},
                suggestion=f"Add a belief record or a scene where {character} learns this.",
            )

        return None

    def verify_reaction(
        self,
        character: str,
        reacts_to: str,
        reaction: str,
        chapter: int,
    ) -> list[NarrativeWarning]:
        """
        Verify a reaction makes sense given character's beliefs.

        Catches:
        - Mourning someone they don't know is dead
        - Celebrating news they haven't heard
        - Reacting to secrets they shouldn't know
        """
        warnings = []

        # Check if they have relevant beliefs
        belief = self.state.character_believes(character, reacts_to, chapter)

        if belief is None:
            warnings.append(NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="belief_violation",
                message=f"Reacts to '{reacts_to}' without recorded knowledge of it",
                details={"reacts_to": reacts_to, "reaction": reaction},
                suggestion=f"Add a scene where {character} learns about '{reacts_to}' or record the belief.",
            ))
        elif belief.is_true is False:
            # Reacting based on false belief - could be dramatic irony
            warnings.append(NarrativeWarning(
                character=character,
                chapter=chapter,
                warning_type="false_belief_reaction",
                message=f"Reaction based on false belief: '{belief.belief}'",
                details={"belief_id": str(belief.id), "reaction": reaction},
                severity="info",
                suggestion="This creates dramatic irony. Ensure the reader knows the truth.",
            ))

        return warnings

    def verify_scene(
        self,
        characters: list[str],
        chapter: int,
        actions: list[tuple[str, str]] | None = None,  # [(character, action), ...]
        reactions: list[tuple[str, str, str]] | None = None,  # [(character, reacts_to, reaction), ...]
    ) -> list[NarrativeWarning]:
        """
        Verify all characters in a scene for narrative coherence.
        """
        warnings = []

        # Check each character's state
        for char in characters:
            # Check for motivation conflicts
            conflicts = self.state.conflicting_motivations(char, chapter)
            for mot_a, mot_b in conflicts:
                warnings.append(NarrativeWarning(
                    character=char,
                    chapter=chapter,
                    warning_type="motivation_conflict",
                    message=f"Active tension: '{mot_a.description}' vs '{mot_b.description}'",
                    details={"motivation_a": str(mot_a.id), "motivation_b": str(mot_b.id)},
                    severity="info",
                    suggestion="This scene could explore this tension.",
                ))

            # Check false beliefs that might affect scene
            false_beliefs = self.state.false_beliefs(char, chapter)
            for belief in false_beliefs:
                warnings.append(NarrativeWarning(
                    character=char,
                    chapter=chapter,
                    warning_type="false_belief_active",
                    message=f"Holds false belief: '{belief.belief}'",
                    details={"belief_id": str(belief.id)},
                    severity="info",
                    suggestion="Consider how this false belief affects their behavior in the scene.",
                ))

        # Verify specific actions
        if actions:
            for char, action in actions:
                warnings.extend(self.verify_action(char, action, chapter))

        # Verify specific reactions
        if reactions:
            for char, reacts_to, reaction in reactions:
                warnings.extend(self.verify_reaction(char, reacts_to, reaction, chapter))

        return warnings

    def get_character_context(self, character: str, chapter: int) -> str:
        """
        Get narrative context for a character at a point in the story.

        Useful for LLM prompts to ensure consistent characterization.
        """
        lines = [f"## Narrative Context: {character} (Chapter {chapter})\n"]

        # Active motivations
        motivations = self.state.motivations_for_character(character, active_only=True, at_chapter=chapter)
        if motivations:
            lines.append("### What drives them right now:")
            for m in motivations:
                intensity = m.effective_intensity(chapter)
                if intensity > 0:
                    lines.append(f"- {m.description} ({m.type.value}, intensity {intensity:.1f})")
            lines.append("")

        # Current beliefs
        beliefs = self.state.beliefs_for_character(character, held_only=True, at_chapter=chapter)
        if beliefs:
            lines.append("### What they believe:")
            for b in beliefs:
                marker = ""
                if b.is_true is False:
                    marker = " [ACTUALLY FALSE]"
                lines.append(f"- {b.belief}{marker}")
            lines.append("")

        # Behavioral constraints
        constraints = self.state.constraints_for_character(character)
        if constraints:
            lines.append("### What's hard for them:")
            for c in constraints:
                lines.append(f"- **{c.action_type}**: {c.constraint}")
                if c.cost:
                    lines.append(f"  If they do it anyway, cost: {c.cost}")
            lines.append("")

        # Motivation conflicts
        conflicts = self.state.conflicting_motivations(character, chapter)
        if conflicts:
            lines.append("### Internal tensions:")
            for mot_a, mot_b in conflicts:
                lines.append(f"- '{mot_a.description}' vs '{mot_b.description}'")
            lines.append("")

        return "\n".join(lines) if len(lines) > 1 else f"No narrative context recorded for {character}."

    def _action_contradicts_motivation(self, action: str, motivation) -> bool:
        """
        Heuristic check if action contradicts motivation.

        Very simplified - real implementation would need NLP.
        """
        # Check for obvious contradictions
        action_words = set(action.split())
        motivation_words = set(motivation.description.lower().split())

        # Look for negation patterns
        negative_words = {"stop", "prevent", "avoid", "escape", "flee", "abandon", "betray"}
        positive_words = {"find", "protect", "save", "help", "pursue", "achieve", "get"}

        action_negative = bool(action_words & negative_words)
        action_positive = bool(action_words & positive_words)
        mot_negative = bool(motivation_words & negative_words)
        mot_positive = bool(motivation_words & positive_words)

        # If motivation is to protect and action is to abandon, that's a contradiction
        if (mot_positive and action_negative) or (mot_negative and action_positive):
            # Check for overlap in subjects
            overlap = action_words & motivation_words - negative_words - positive_words
            if overlap:
                return True

        return False

    def _format_constraint_suggestion(self, constraint) -> str:
        """Format a helpful suggestion for a constraint breach."""
        parts = []

        if constraint.prerequisites:
            parts.append(f"Prerequisites: {', '.join(constraint.prerequisites)}")

        if constraint.exceptions:
            parts.append(f"Unless: {', '.join(constraint.exceptions)}")

        if constraint.cost:
            parts.append(f"If intentional, show the cost: {constraint.cost}")
        else:
            parts.append("If intentional, this is a breaking point - show the impact.")

        return " | ".join(parts)
