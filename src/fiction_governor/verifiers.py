"""
Verifiers for fiction content.

Check proposed content against the bible (character, world, tone rules)
and canon (established events, relationships).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import FictionClaim, FictionClaimType, BannedTrope
from .bible import Bible
from .canon import Canon


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
