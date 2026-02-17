# SPDX-License-Identifier: Apache-2.0
"""
Corpus ledger for non-fiction writing.

The corpus is your body of work - canonical papers that establish
terminology and positions. New writing must be consistent with the corpus.

This is analogous to the "bible" in fiction_governor, but for academic writing:
- Canonical sources (your papers) = decisions about terminology/positions
- External references = supporting evidence
- Concepts = character traits (must be used consistently)
- Positions = world rules (cannot be contradicted)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import Source, Concept, Position, SourceType
from .doi import fetch_source, DOIFetchError


@dataclass
class CorpusConflict:
    """A conflict between new writing and the corpus."""

    conflict_type: str
    """Type: 'contradicts_position', 'misuses_term', 'uncited_claim'."""

    description: str
    """Human-readable description of the conflict."""

    source_key: str | None = None
    """Citation key of the source involved."""

    position_id: str | None = None
    """ID of the position being contradicted."""

    concept_term: str | None = None
    """Term being misused."""

    severity: str = "error"
    """'error' (blocks) or 'warning' (flags)."""


class Corpus:
    """
    The corpus of your canonical work.

    Manages:
    - Canonical sources (your papers)
    - External references
    - Concepts (defined terminology)
    - Positions (established theses)

    Persists to .nonfiction/corpus.json
    """

    def __init__(self, corpus_dir: Path):
        self.corpus_dir = Path(corpus_dir)
        self.corpus_file = self.corpus_dir / "corpus.json"

        self._sources: dict[str, Source] = {}  # keyed by citation_key
        self._concepts: dict[str, Concept] = {}  # keyed by term
        self._positions: dict[str, Position] = {}  # keyed by id

        self._load()

    def _load(self) -> None:
        """Load corpus from disk."""
        if not self.corpus_file.exists():
            return

        data = json.loads(self.corpus_file.read_text())

        for source_data in data.get("sources", []):
            source = Source.from_dict(source_data)
            if source.citation_key:
                self._sources[source.citation_key] = source

        for concept_data in data.get("concepts", []):
            concept = Concept.from_dict(concept_data)
            self._concepts[concept.term] = concept

        for position_data in data.get("positions", []):
            position = Position.from_dict(position_data)
            self._positions[str(position.id)] = position

    def _save(self) -> None:
        """Save corpus to disk."""
        self.corpus_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "sources": [s.to_dict() for s in self._sources.values()],
            "concepts": [c.to_dict() for c in self._concepts.values()],
            "positions": [p.to_dict() for p in self._positions.values()],
        }

        self.corpus_file.write_text(json.dumps(data, indent=2))

    # =========================================================================
    # Sources
    # =========================================================================

    def add_source(
        self,
        source: Source | None = None,
        doi: str | None = None,
        canonical: bool = False,
        citation_key: str | None = None,
        **kwargs,
    ) -> Source:
        """
        Add a source to the corpus.

        Can provide a Source object directly, or a DOI to fetch.

        Args:
            source: A Source object
            doi: DOI to fetch metadata for
            canonical: Whether this is a canonical (your own) source
            citation_key: Override citation key
            **kwargs: Additional fields for Source

        Returns:
            The added Source
        """
        if source is None and doi:
            # Fetch from DOI
            try:
                source = fetch_source(doi, canonical=canonical, citation_key=citation_key)
            except DOIFetchError as e:
                # Create minimal source with DOI
                source = Source(
                    doi=doi,
                    citation_key=citation_key or doi.replace("/", "_").replace(".", "_"),
                    source_type=SourceType.CANONICAL if canonical else SourceType.EXTERNAL,
                )
        elif source is None:
            # Create from kwargs
            from .types import Author
            authors = kwargs.pop("authors", [])
            if authors and isinstance(authors[0], str):
                authors = [Author(name=name) for name in authors]
            source = Source(
                authors=authors,
                source_type=SourceType.CANONICAL if canonical else SourceType.EXTERNAL,
                citation_key=citation_key,
                **kwargs,
            )

        # Override source type if canonical specified
        if canonical:
            source.source_type = SourceType.CANONICAL

        # Ensure citation key
        if not source.citation_key:
            if source.doi:
                source.citation_key = source.doi.replace("/", "_").replace(".", "_")
            else:
                source.citation_key = f"source_{len(self._sources)}"

        self._sources[source.citation_key] = source
        self._save()
        return source

    def add_canonical_doi(self, doi: str, citation_key: str | None = None) -> Source:
        """Convenience: add one of your papers by DOI."""
        return self.add_source(doi=doi, canonical=True, citation_key=citation_key)

    def add_reference(self, doi: str, citation_key: str | None = None) -> Source:
        """Convenience: add an external reference by DOI."""
        return self.add_source(doi=doi, canonical=False, citation_key=citation_key)

    def get_source(self, citation_key: str) -> Source | None:
        """Get a source by citation key."""
        return self._sources.get(citation_key)

    def get_source_by_doi(self, doi: str) -> Source | None:
        """Get a source by DOI."""
        from .doi import normalize_doi
        normalized = normalize_doi(doi)
        for source in self._sources.values():
            if source.doi and normalize_doi(source.doi) == normalized:
                return source
        return None

    def canonical_sources(self) -> list[Source]:
        """Get all canonical sources (your papers)."""
        return [s for s in self._sources.values() if s.is_canonical]

    def external_sources(self) -> list[Source]:
        """Get all external references."""
        return [s for s in self._sources.values() if not s.is_canonical]

    def all_sources(self) -> list[Source]:
        """Get all sources."""
        return list(self._sources.values())

    def has_source(self, citation_key: str) -> bool:
        """Check if a source exists."""
        return citation_key in self._sources

    # =========================================================================
    # Concepts
    # =========================================================================

    def add_concept(
        self,
        concept: Concept | None = None,
        term: str | None = None,
        definition: str | None = None,
        source_key: str | None = None,
        **kwargs,
    ) -> Concept:
        """
        Add a concept (defined term) to the corpus.

        Args:
            concept: A Concept object
            term: The term being defined
            definition: The definition
            source_key: Citation key of source that defines this
            **kwargs: Additional fields for Concept
        """
        if concept is None:
            concept = Concept(
                term=term or "",
                definition=definition or "",
                source_key=source_key,
                **kwargs,
            )

        self._concepts[concept.term] = concept

        # Link to source if provided
        if concept.source_key and concept.source_key in self._sources:
            source = self._sources[concept.source_key]
            if concept.term not in source.concepts_defined:
                source.concepts_defined.append(concept.term)

        self._save()
        return concept

    def get_concept(self, term: str) -> Concept | None:
        """Get a concept by term."""
        return self._concepts.get(term)

    def find_concept(self, text: str) -> list[Concept]:
        """Find concepts mentioned in text."""
        found = []
        for concept in self._concepts.values():
            if concept.matches(text):
                found.append(concept)
        return found

    def all_concepts(self) -> list[Concept]:
        """Get all concepts."""
        return list(self._concepts.values())

    # =========================================================================
    # Positions
    # =========================================================================

    def add_position(
        self,
        position: Position | None = None,
        claim: str | None = None,
        source_key: str | None = None,
        **kwargs,
    ) -> Position:
        """
        Add a position (thesis/claim) to the corpus.

        Args:
            position: A Position object
            claim: The thesis statement
            source_key: Citation key of source that establishes this
            **kwargs: Additional fields for Position
        """
        if position is None:
            position = Position(
                claim=claim or "",
                source_key=source_key,
                **kwargs,
            )

        self._positions[str(position.id)] = position

        # Link to source if provided
        if position.source_key and position.source_key in self._sources:
            source = self._sources[position.source_key]
            if str(position.id) not in source.positions_taken:
                source.positions_taken.append(str(position.id))

        self._save()
        return position

    def get_position(self, position_id: str | UUID) -> Position | None:
        """Get a position by ID."""
        return self._positions.get(str(position_id))

    def current_positions(self) -> list[Position]:
        """Get all current (non-superseded) positions."""
        return [p for p in self._positions.values() if p.is_current]

    def positions_by_tag(self, tag: str) -> list[Position]:
        """Get positions by tag."""
        return [p for p in self._positions.values() if tag in p.tags and p.is_current]

    def all_positions(self) -> list[Position]:
        """Get all positions."""
        return list(self._positions.values())

    def revise_position(
        self,
        old_position_id: str | UUID,
        new_claim: str,
        source_key: str | None = None,
        **kwargs,
    ) -> Position | None:
        """
        Revise a position (supersede with new claim).

        Args:
            old_position_id: ID of position being revised
            new_claim: New thesis statement
            source_key: Citation key of source that establishes revision
        """
        old_id = str(old_position_id)
        old_position = self._positions.get(old_id)
        if not old_position:
            return None

        # Create new position
        new_position = Position(
            claim=new_claim,
            source_key=source_key,
            supersedes=old_id,
            tags=old_position.tags.copy(),
            **kwargs,
        )

        # Mark old as superseded
        old_position.superseded_by = str(new_position.id)

        self._positions[str(new_position.id)] = new_position
        self._save()
        return new_position

    # =========================================================================
    # Verification helpers
    # =========================================================================

    def check_citation(self, citation_key: str) -> tuple[bool, str]:
        """
        Check if a citation key is valid.

        Returns (valid, message).
        """
        if citation_key in self._sources:
            return True, f"Valid citation: {citation_key}"
        return False, f"Unknown citation key: {citation_key}"

    def check_term_usage(self, term: str, context: str) -> tuple[bool, str]:
        """
        Check if a term is used correctly.

        Returns (valid, message).
        """
        concept = self._concepts.get(term)
        if not concept:
            return True, f"Term '{term}' not in corpus (OK to use freely)"

        # Check for anti-patterns in context
        for anti_pattern in concept.anti_patterns:
            if anti_pattern.lower() in context.lower():
                return False, f"Term '{term}' used with anti-pattern '{anti_pattern}'"

        return True, f"Term '{term}' used correctly"

    def find_conflicts(self, text: str) -> list[CorpusConflict]:
        """
        Find potential conflicts between text and corpus.

        Returns list of conflicts (for further verification).
        """
        conflicts = []

        # Check concept anti-patterns
        for concept in self._concepts.values():
            for anti_pattern in concept.anti_patterns:
                if anti_pattern.lower() in text.lower():
                    conflicts.append(CorpusConflict(
                        conflict_type="misuses_term",
                        description=f"Text uses '{anti_pattern}' which is an anti-pattern for '{concept.term}'",
                        concept_term=concept.term,
                        severity="warning",
                    ))

        # Note: deeper contradiction checking would require NLP/LLM
        # This provides structural checks only

        return conflicts

    # =========================================================================
    # Export
    # =========================================================================

    def to_bibtex(self) -> str:
        """Export all sources as BibTeX."""
        entries = []
        for source in sorted(self._sources.values(), key=lambda s: s.citation_key or ""):
            entries.append(source.to_bibtex())
        return "\n\n".join(entries)

    def format_for_prompt(self) -> str:
        """Format corpus for LLM prompt."""
        lines = ["# Corpus (Your Canonical Work)"]

        if self.canonical_sources():
            lines.append("\n## Your Papers")
            for source in self.canonical_sources():
                lines.append(f"- [@{source.citation_key}] {source.title}")

        if self._concepts:
            lines.append("\n## Defined Terminology")
            for concept in self._concepts.values():
                lines.append(concept.format_for_prompt())

        if self.current_positions():
            lines.append("\n## Established Positions")
            for position in self.current_positions():
                lines.append(position.format_for_prompt())

        return "\n".join(lines)
