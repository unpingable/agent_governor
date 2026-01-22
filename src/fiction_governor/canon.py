"""
Canon: The facts ledger for fiction.

Stores what has actually happened in the story - events, relationships,
established facts. Unlike the bible (decisions), canon can become stale
if the manuscript is edited.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import CanonEvent, Relationship


class Canon:
    """
    The facts ledger for fiction.

    Tracks events, relationships, and established facts about the story.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.canon_dir = project_dir / ".fiction-gov" / "canon"

        self._events: list[CanonEvent] = []
        self._relationships: dict[str, Relationship] = {}  # "char_a|char_b" -> Relationship

        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create canon directory structure if needed."""
        self.canon_dir.mkdir(parents=True, exist_ok=True)

        if not (self.canon_dir / "events.json").exists():
            (self.canon_dir / "events.json").write_text("[]")

        if not (self.canon_dir / "relationships.json").exists():
            (self.canon_dir / "relationships.json").write_text("[]")

    def _load(self) -> None:
        """Load canon from disk."""
        # Events
        events_data = json.loads((self.canon_dir / "events.json").read_text())
        self._events = [CanonEvent.from_dict(e) for e in events_data]

        # Relationships
        rels_data = json.loads((self.canon_dir / "relationships.json").read_text())
        self._relationships = {}
        for r in rels_data:
            rel = Relationship.from_dict(r)
            key = self._relationship_key(rel.character_a, rel.character_b)
            self._relationships[key] = rel

    def _save(self) -> None:
        """Save canon to disk."""
        events_data = [e.to_dict() for e in self._events]
        (self.canon_dir / "events.json").write_text(json.dumps(events_data, indent=2))

        rels_data = [r.to_dict() for r in self._relationships.values()]
        (self.canon_dir / "relationships.json").write_text(json.dumps(rels_data, indent=2))

    def _relationship_key(self, char_a: str, char_b: str) -> str:
        """Create a consistent key for a relationship (alphabetical order)."""
        chars = sorted([char_a.lower(), char_b.lower()])
        return f"{chars[0]}|{chars[1]}"

    # Event methods
    def add_event(
        self,
        chapter: int,
        summary: str,
        characters: list[str] | None = None,
        location: str | None = None,
        establishes: list[str] | None = None,
        manuscript_ref: str | None = None,
        quote: str | None = None,
    ) -> CanonEvent:
        """Add a canon event."""
        event = CanonEvent(
            chapter=chapter,
            summary=summary,
            characters=characters or [],
            location=location,
            establishes=establishes or [],
            manuscript_ref=manuscript_ref,
            quote=quote,
        )
        self._events.append(event)
        self._save()
        return event

    def get_event(self, event_id: UUID) -> CanonEvent | None:
        """Get an event by ID."""
        for event in self._events:
            if event.id == event_id:
                return event
        return None

    def events_by_chapter(self, chapter: int) -> list[CanonEvent]:
        """Get all events in a chapter."""
        return [e for e in self._events if e.chapter == chapter]

    def events_with_character(self, character: str) -> list[CanonEvent]:
        """Get all events involving a character."""
        char_lower = character.lower()
        return [
            e for e in self._events
            if any(c.lower() == char_lower for c in e.characters)
        ]

    def events_at_location(self, location: str) -> list[CanonEvent]:
        """Get all events at a location."""
        loc_lower = location.lower()
        return [
            e for e in self._events
            if e.location and e.location.lower() == loc_lower
        ]

    def last_location(self, character: str) -> tuple[str | None, int]:
        """
        Get the last known location of a character.

        Returns (location, chapter) or (None, 0) if unknown.
        """
        char_events = self.events_with_character(character)
        if not char_events:
            return None, 0

        # Sort by chapter (descending) and get most recent with location
        for event in sorted(char_events, key=lambda e: e.chapter, reverse=True):
            if event.location:
                return event.location, event.chapter

        return None, 0

    def all_events(self) -> list[CanonEvent]:
        """Get all events, sorted by chapter."""
        return sorted(self._events, key=lambda e: e.chapter)

    def search_events(self, query: str) -> list[CanonEvent]:
        """Search events by summary text."""
        query_lower = query.lower()
        return [
            e for e in self._events
            if query_lower in e.summary.lower()
            or (e.quote and query_lower in e.quote.lower())
        ]

    # Relationship methods
    def set_relationship(
        self,
        character_a: str,
        character_b: str,
        status: str,
        as_of_chapter: int,
        dynamics: list[str] | None = None,
    ) -> Relationship:
        """Set or update a relationship between characters."""
        key = self._relationship_key(character_a, character_b)

        # Get existing relationship history if any
        existing = self._relationships.get(key)
        history = existing.history.copy() if existing else []

        # Add old status to history if it changed
        if existing and existing.status != status:
            history.append(f"Ch{existing.as_of_chapter}: {existing.status}")

        rel = Relationship(
            character_a=character_a,
            character_b=character_b,
            status=status,
            dynamics=dynamics or [],
            history=history,
            as_of_chapter=as_of_chapter,
        )
        self._relationships[key] = rel
        self._save()
        return rel

    def get_relationship(self, character_a: str, character_b: str) -> Relationship | None:
        """Get the relationship between two characters."""
        key = self._relationship_key(character_a, character_b)
        return self._relationships.get(key)

    def relationships_for_character(self, character: str) -> list[Relationship]:
        """Get all relationships involving a character."""
        char_lower = character.lower()
        return [
            r for r in self._relationships.values()
            if r.character_a.lower() == char_lower
            or r.character_b.lower() == char_lower
        ]

    def all_relationships(self) -> list[Relationship]:
        """Get all relationships."""
        return list(self._relationships.values())

    # Formatting
    def format_chapter(self, chapter: int) -> str:
        """Format a chapter's events for prompt."""
        events = self.events_by_chapter(chapter)
        if not events:
            return f"## Chapter {chapter}\n\nNo events recorded."

        lines = [f"## Chapter {chapter}\n"]
        for event in events:
            lines.append(f"- {event.summary}")
            if event.characters:
                lines.append(f"  Characters: {', '.join(event.characters)}")
            if event.location:
                lines.append(f"  Location: {event.location}")
            if event.quote:
                lines.append(f"  > {event.quote}")

        return "\n".join(lines)

    def format_recent(self, num_chapters: int = 2) -> str:
        """Format recent chapters for prompt."""
        if not self._events:
            return "No events recorded yet."

        max_chapter = max(e.chapter for e in self._events)
        start_chapter = max(1, max_chapter - num_chapters + 1)

        sections = []
        for ch in range(start_chapter, max_chapter + 1):
            sections.append(self.format_chapter(ch))

        return "\n\n".join(sections)

    def format_character_history(self, character: str) -> str:
        """Format a character's history for prompt."""
        events = self.events_with_character(character)
        if not events:
            return f"No recorded events for {character}."

        lines = [f"## {character}'s History\n"]
        for event in sorted(events, key=lambda e: e.chapter):
            lines.append(f"Ch{event.chapter}: {event.summary}")
            if event.location:
                lines.append(f"  at {event.location}")

        # Add relationships
        rels = self.relationships_for_character(character)
        if rels:
            lines.append("\n### Relationships")
            for rel in rels:
                other = rel.character_b if rel.character_a.lower() == character.lower() else rel.character_a
                lines.append(f"- {other}: {rel.status}")
                for dyn in rel.dynamics:
                    lines.append(f"    - {dyn}")

        return "\n".join(lines)

    def format_for_prompt(self) -> str:
        """Format entire canon for prompt (summary version)."""
        if not self._events:
            return "# Story Canon\n\nNo events recorded yet."

        lines = ["# Story Canon\n"]

        # Events by chapter
        chapters = sorted(set(e.chapter for e in self._events))
        for ch in chapters:
            lines.append(f"\n## Chapter {ch}")
            for event in self.events_by_chapter(ch):
                lines.append(f"- {event.summary}")

        # Key relationships
        if self._relationships:
            lines.append("\n## Relationships")
            for rel in self._relationships.values():
                lines.append(f"- {rel.character_a} & {rel.character_b}: {rel.status}")

        return "\n".join(lines)

    # Validation helpers
    def character_can_be_at(
        self,
        character: str,
        location: str,
        chapter: int,
    ) -> tuple[bool, str]:
        """
        Check if a character can plausibly be at a location.

        Returns (can_be_there, reason).
        """
        last_loc, last_ch = self.last_location(character)

        if last_loc is None:
            # No prior location established
            return True, "No prior location established"

        if last_loc.lower() == location.lower():
            return True, f"Still at {location}"

        # Simple check: if they were elsewhere in the same chapter, that's a problem
        if last_ch == chapter and last_loc.lower() != location.lower():
            return False, f"Was at {last_loc} earlier in chapter {chapter}"

        # Otherwise, allow (could have traveled between chapters)
        return True, f"Could have traveled from {last_loc} (ch{last_ch})"

    def has_event_matching(self, summary_fragment: str) -> CanonEvent | None:
        """Check if an event matching a description exists."""
        fragment_lower = summary_fragment.lower()
        for event in self._events:
            if fragment_lower in event.summary.lower():
                return event
        return None
