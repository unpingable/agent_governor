# SPDX-License-Identifier: Apache-2.0
"""
Bible: The decisions ledger for fiction.

Stores persistent decisions about characters, world, tone, and banned tropes.
These don't decay - they persist until explicitly revised.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import (
    Character,
    CharacterTrait,
    CharacterVoice,
    WorldRule,
    BannedTrope,
    ToneSettings,
)


# Common tropes with detection patterns
COMMON_TROPES = {
    "chosen_one": BannedTrope(
        name="chosen_one",
        reason="Protagonist should earn their role, not be destined",
        patterns=[
            r"you are the chosen",
            r"the prophecy spoke of",
            r"destined to save",
            r"born to be",
            r"the one foretold",
        ],
        severity="error",
    ),
    "love_triangle": BannedTrope(
        name="love_triangle",
        reason="Romantic tension shouldn't come from 'which one will they choose'",
        patterns=[
            r"couldn't choose between",
            r"torn between .* and .*",
            r"both of them loved",
        ],
        severity="warning",
    ),
    "magical_pregnancy": BannedTrope(
        name="magical_pregnancy",
        reason="No surprise/magical pregnancies as plot devices",
        patterns=[
            r"discovered she was pregnant",
            r"the child would be special",
            r"conceived by magic",
        ],
        severity="error",
    ),
    "bury_your_gays": BannedTrope(
        name="bury_your_gays",
        reason="Queer characters deserve meaningful arcs, not tragic deaths for straight characters' development",
        patterns=[],  # Hard to detect with patterns
        severity="error",
    ),
    "noble_savage": BannedTrope(
        name="noble_savage",
        reason="No exoticized 'wise indigenous' or 'magical minority' characters",
        patterns=[
            r"ancient wisdom of .* people",
            r"her people had always known",
            r"mystical connection to the land",
        ],
        severity="error",
    ),
    "women_in_refrigerators": BannedTrope(
        name="women_in_refrigerators",
        reason="Female characters don't exist solely to be harmed for male character motivation",
        patterns=[],  # Structural, hard to detect
        severity="error",
    ),
    "instant_forgiveness": BannedTrope(
        name="instant_forgiveness",
        reason="Forgiveness should be earned, not granted instantly after an apology",
        patterns=[
            r"I forgive you",
            r"all is forgiven",
            r"let's forget it ever happened",
        ],
        severity="warning",
    ),
    "not_like_other_girls": BannedTrope(
        name="not_like_other_girls",
        reason="Female characters shouldn't be defined by rejecting femininity",
        patterns=[
            r"not like other girls",
            r"never fit in with",
            r"always preferred .* to dresses",
        ],
        severity="warning",
    ),
}


class Bible:
    """
    The decisions ledger for fiction.

    Stores characters, world rules, tone settings, and banned tropes.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.bible_dir = project_dir / ".fiction-gov" / "bible"

        self._characters: dict[str, Character] = {}
        self._world_rules: dict[str, WorldRule] = {}
        self._banned_tropes: dict[str, BannedTrope] = {}
        self._tone: ToneSettings | None = None

        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create bible directory structure if needed."""
        self.bible_dir.mkdir(parents=True, exist_ok=True)

        files = [
            "characters.json",
            "world_rules.json",
            "banned_tropes.json",
            "tone.json",
        ]
        for f in files:
            path = self.bible_dir / f
            if not path.exists():
                if f == "tone.json":
                    path.write_text("{}")
                else:
                    path.write_text("[]")

    def _load(self) -> None:
        """Load bible from disk."""
        # Characters
        chars_data = json.loads((self.bible_dir / "characters.json").read_text())
        self._characters = {
            c["name"].lower(): Character.from_dict(c) for c in chars_data
        }

        # World rules
        rules_data = json.loads((self.bible_dir / "world_rules.json").read_text())
        self._world_rules = {
            r["name"].lower(): WorldRule.from_dict(r) for r in rules_data
        }

        # Banned tropes
        tropes_data = json.loads((self.bible_dir / "banned_tropes.json").read_text())
        self._banned_tropes = {
            t["name"].lower(): BannedTrope.from_dict(t) for t in tropes_data
        }

        # Tone
        tone_data = json.loads((self.bible_dir / "tone.json").read_text())
        if tone_data:
            self._tone = ToneSettings.from_dict(tone_data)

    def _save(self) -> None:
        """Save bible to disk."""
        # Characters
        chars_data = [c.to_dict() for c in self._characters.values()]
        (self.bible_dir / "characters.json").write_text(json.dumps(chars_data, indent=2))

        # World rules
        rules_data = [r.to_dict() for r in self._world_rules.values()]
        (self.bible_dir / "world_rules.json").write_text(json.dumps(rules_data, indent=2))

        # Banned tropes
        tropes_data = [t.to_dict() for t in self._banned_tropes.values()]
        (self.bible_dir / "banned_tropes.json").write_text(json.dumps(tropes_data, indent=2))

        # Tone
        tone_data = self._tone.to_dict() if self._tone else {}
        (self.bible_dir / "tone.json").write_text(json.dumps(tone_data, indent=2))

    # Character methods
    def add_character(self, name: str, role: str | None = None) -> Character:
        """Add a new character to the bible."""
        char = Character(name=name, role=role)
        self._characters[name.lower()] = char
        self._save()
        return char

    def get_character(self, name: str) -> Character | None:
        """Get a character by name."""
        return self._characters.get(name.lower())

    def update_character(self, character: Character) -> None:
        """Update a character in the bible."""
        self._characters[character.name.lower()] = character
        self._save()

    def add_character_trait(
        self,
        name: str,
        trait: str,
        nuance: str | None = None,
        note: str | None = None,
    ) -> Character | None:
        """Add a trait to a character."""
        char = self.get_character(name)
        if not char:
            return None

        char.add_trait(trait, nuance, note)
        self._save()
        return char

    def add_character_anti_pattern(self, name: str, pattern: str) -> Character | None:
        """Add an anti-pattern to a character."""
        char = self.get_character(name)
        if not char:
            return None

        char.add_anti_pattern(pattern)
        self._save()
        return char

    def set_character_voice(
        self,
        name: str,
        internal_monologue: str | None = None,
        dialogue: str | None = None,
        avoid: list[str] | None = None,
    ) -> Character | None:
        """Set a character's voice."""
        char = self.get_character(name)
        if not char:
            return None

        char.voice = CharacterVoice(
            internal_monologue=internal_monologue,
            dialogue=dialogue,
            avoid=avoid or [],
        )
        self._save()
        return char

    def all_characters(self) -> list[Character]:
        """Get all characters."""
        return list(self._characters.values())

    # World rule methods
    def add_world_rule(
        self,
        name: str,
        rule: str,
        category: str | None = None,
        implications: list[str] | None = None,
    ) -> WorldRule:
        """Add a world rule."""
        world_rule = WorldRule(
            name=name,
            rule=rule,
            category=category,
            implications=implications or [],
        )
        self._world_rules[name.lower()] = world_rule
        self._save()
        return world_rule

    def get_world_rule(self, name: str) -> WorldRule | None:
        """Get a world rule by name."""
        return self._world_rules.get(name.lower())

    def all_world_rules(self) -> list[WorldRule]:
        """Get all world rules."""
        return list(self._world_rules.values())

    def world_rules_by_category(self, category: str) -> list[WorldRule]:
        """Get world rules by category."""
        return [r for r in self._world_rules.values() if r.category == category]

    # Banned trope methods
    def ban_trope(
        self,
        name: str,
        reason: str,
        patterns: list[str] | None = None,
        severity: str = "error",
    ) -> BannedTrope:
        """Ban a trope."""
        # Check if it's a common trope
        if name.lower() in COMMON_TROPES and not patterns:
            trope = COMMON_TROPES[name.lower()]
            trope.reason = reason  # Allow custom reason
            trope.severity = severity
        else:
            trope = BannedTrope(
                name=name,
                reason=reason,
                patterns=patterns or [],
                severity=severity,
            )

        self._banned_tropes[name.lower()] = trope
        self._save()
        return trope

    def ban_common_trope(self, name: str, reason: str | None = None) -> BannedTrope | None:
        """Ban a common trope by name (uses predefined patterns)."""
        if name.lower() not in COMMON_TROPES:
            return None

        trope = COMMON_TROPES[name.lower()]
        if reason:
            trope.reason = reason

        self._banned_tropes[name.lower()] = trope
        self._save()
        return trope

    def get_banned_trope(self, name: str) -> BannedTrope | None:
        """Get a banned trope by name."""
        return self._banned_tropes.get(name.lower())

    def all_banned_tropes(self) -> list[BannedTrope]:
        """Get all banned tropes."""
        return list(self._banned_tropes.values())

    def unban_trope(self, name: str) -> bool:
        """Remove a trope from the banned list."""
        if name.lower() in self._banned_tropes:
            del self._banned_tropes[name.lower()]
            self._save()
            return True
        return False

    # Tone methods
    def set_tone(
        self,
        genre: str | None = None,
        not_genres: list[str] | None = None,
        prose_style: str | None = None,
        pacing: str | None = None,
        avoid: list[str] | None = None,
    ) -> ToneSettings:
        """Set tone settings."""
        self._tone = ToneSettings(
            genre=genre,
            not_genres=not_genres or [],
            prose_style=prose_style,
            pacing=pacing,
            avoid=avoid or [],
        )
        self._save()
        return self._tone

    def get_tone(self) -> ToneSettings | None:
        """Get tone settings."""
        return self._tone

    # Formatting for prompts
    def format_for_prompt(self) -> str:
        """Format entire bible for LLM prompt."""
        sections = ["# Story Bible\n"]

        # Characters
        if self._characters:
            sections.append("## Characters\n")
            for char in self._characters.values():
                sections.append(char.format_for_prompt())
                sections.append("")

        # World rules
        if self._world_rules:
            sections.append("## World Rules\n")
            for rule in self._world_rules.values():
                sections.append(f"### {rule.name}")
                sections.append(f"{rule.rule}")
                if rule.implications:
                    sections.append("Implications:")
                    for imp in rule.implications:
                        sections.append(f"  - {imp}")
                sections.append("")

        # Tone
        if self._tone:
            sections.append(self._tone.format_for_prompt())
            sections.append("")

        # Banned tropes
        if self._banned_tropes:
            sections.append("## Banned Tropes\n")
            for trope in self._banned_tropes.values():
                sections.append(f"- **{trope.name}**: {trope.reason}")
            sections.append("")

        return "\n".join(sections)

    def format_character_for_prompt(self, name: str) -> str | None:
        """Format a single character for prompt."""
        char = self.get_character(name)
        if not char:
            return None
        return char.format_for_prompt()
