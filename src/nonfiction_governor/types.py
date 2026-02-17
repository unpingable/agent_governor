# SPDX-License-Identifier: Apache-2.0
"""
Core types for the non-fiction governor.

These define the vocabulary for academic/non-fiction writing constraints:
- Sources (your canonical papers)
- References (external citations)
- Concepts (defined terminology)
- Positions (normative claims/theses)
- WritingClaims (claims in new writing that must be backed by citations)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class SourceType(Enum):
    """Type of source material."""

    CANONICAL = "canonical"
    """Your own papers - first-class authority on terminology and positions."""

    EXTERNAL = "external"
    """External references - supporting evidence only."""

    LOCAL = "local"
    """Local file (not published) - notes, drafts, etc."""


class ClaimStrength(Enum):
    """Strength of a claim in writing."""

    ASSERTION = "assertion"
    """Strong claim presented as fact (requires strong citation)."""

    ARGUMENT = "argument"
    """Reasoned argument (requires supporting evidence)."""

    HYPOTHESIS = "hypothesis"
    """Tentative claim (requires framing as such)."""

    OBSERVATION = "observation"
    """Empirical observation (requires data/evidence)."""

    DEFINITION = "definition"
    """Defining a term (requires canonical source or explicit introduction)."""


class NonfictionClaimType(Enum):
    """Types of claims that can be made in non-fiction writing."""

    # Citation claims
    CITES_SOURCE = "cites_source"
    """This claim is backed by a citation."""

    USES_TERM = "uses_term"
    """Uses a defined term correctly."""

    # Consistency claims
    CONSISTENT_WITH_CORPUS = "consistent_with_corpus"
    """Claim doesn't contradict canonical positions."""

    EXTENDS_POSITION = "extends_position"
    """Claim extends/builds on a canonical position."""

    # Structure claims
    FOLLOWS_ARGUMENT = "follows_argument"
    """This follows logically from previous claims."""

    INTRODUCES_CONCEPT = "introduces_concept"
    """Introduces a new term/concept (must be defined)."""


@dataclass
class Author:
    """An author of a source."""

    name: str
    """Full name."""

    orcid: str | None = None
    """ORCID identifier if available."""

    affiliation: str | None = None
    """Institutional affiliation."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "orcid": self.orcid,
            "affiliation": self.affiliation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Author":
        return cls(
            name=data["name"],
            orcid=data.get("orcid"),
            affiliation=data.get("affiliation"),
        )

    def __str__(self) -> str:
        return self.name


@dataclass
class Source:
    """
    A source document (paper, article, etc.).

    For canonical sources (your papers), this also tracks concepts defined
    and positions taken.
    """

    id: UUID = field(default_factory=uuid4)

    # Identity
    doi: str | None = None
    """DOI (e.g., '10.5281/zenodo.12345')."""

    url: str | None = None
    """URL if no DOI available."""

    local_path: str | None = None
    """Path to local file if available."""

    # Metadata
    title: str = ""
    authors: list[Author] = field(default_factory=list)
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    """Journal, conference, or repository (e.g., 'Zenodo')."""

    # Citation
    citation_key: str | None = None
    """BibTeX-style key (e.g., 'beck2024epistemic')."""

    # Classification
    source_type: SourceType = SourceType.EXTERNAL

    # For canonical sources: what this paper establishes
    concepts_defined: list[str] = field(default_factory=list)
    """Terms/concepts this paper defines (by citation_key of Concept)."""

    positions_taken: list[str] = field(default_factory=list)
    """Positions this paper establishes (by citation_key of Position)."""

    # Metadata
    fetched_at: datetime | None = None
    """When metadata was fetched from DOI resolver."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        # Generate citation key if not provided
        if not self.citation_key and self.authors and self.year:
            first_author = self.authors[0].name.split()[-1].lower()
            self.citation_key = f"{first_author}{self.year}"

    @property
    def is_canonical(self) -> bool:
        """Is this a canonical (your own) source?"""
        return self.source_type == SourceType.CANONICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "doi": self.doi,
            "url": self.url,
            "local_path": self.local_path,
            "title": self.title,
            "authors": [a.to_dict() for a in self.authors],
            "abstract": self.abstract,
            "year": self.year,
            "venue": self.venue,
            "citation_key": self.citation_key,
            "source_type": self.source_type.value,
            "concepts_defined": self.concepts_defined,
            "positions_taken": self.positions_taken,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        return cls(
            id=UUID(data["id"]),
            doi=data.get("doi"),
            url=data.get("url"),
            local_path=data.get("local_path"),
            title=data.get("title", ""),
            authors=[Author.from_dict(a) for a in data.get("authors", [])],
            abstract=data.get("abstract"),
            year=data.get("year"),
            venue=data.get("venue"),
            citation_key=data.get("citation_key"),
            source_type=SourceType(data.get("source_type", "external")),
            concepts_defined=data.get("concepts_defined", []),
            positions_taken=data.get("positions_taken", []),
            fetched_at=datetime.fromisoformat(data["fetched_at"]) if data.get("fetched_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def to_bibtex(self) -> str:
        """Generate BibTeX entry."""
        authors_str = " and ".join(a.name for a in self.authors)
        entry_type = "article"  # Default, could be smarter

        lines = [
            f"@{entry_type}{{{self.citation_key},",
            f"  title = {{{self.title}}},",
            f"  author = {{{authors_str}}},",
        ]

        if self.year:
            lines.append(f"  year = {{{self.year}}},")
        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")
        if self.url:
            lines.append(f"  url = {{{self.url}}},")
        if self.venue:
            lines.append(f"  journal = {{{self.venue}}},")

        lines.append("}")
        return "\n".join(lines)

    def format_citation(self) -> str:
        """Format as inline citation."""
        if self.authors:
            first_author = self.authors[0].name.split()[-1]
            if len(self.authors) > 2:
                return f"{first_author} et al. ({self.year})"
            elif len(self.authors) == 2:
                second_author = self.authors[1].name.split()[-1]
                return f"{first_author} & {second_author} ({self.year})"
            else:
                return f"{first_author} ({self.year})"
        return f"({self.year})" if self.year else "(n.d.)"


@dataclass
class Concept:
    """
    A defined term or concept.

    Concepts establish vocabulary that must be used consistently.
    """

    id: UUID = field(default_factory=uuid4)

    term: str = ""
    """The canonical term."""

    definition: str = ""
    """The definition."""

    source_key: str | None = None
    """Citation key of the source that defines this."""

    aliases: list[str] = field(default_factory=list)
    """Other names for this concept."""

    related_terms: list[str] = field(default_factory=list)
    """Related concepts (by term)."""

    anti_patterns: list[str] = field(default_factory=list)
    """Terms that should NOT be used as synonyms."""

    notes: str | None = None
    """Additional guidance on using this term."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(self, text: str) -> bool:
        """Check if text uses this concept (or an alias)."""
        text_lower = text.lower()
        if self.term.lower() in text_lower:
            return True
        return any(alias.lower() in text_lower for alias in self.aliases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "term": self.term,
            "definition": self.definition,
            "source_key": self.source_key,
            "aliases": self.aliases,
            "related_terms": self.related_terms,
            "anti_patterns": self.anti_patterns,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Concept":
        return cls(
            id=UUID(data["id"]),
            term=data["term"],
            definition=data.get("definition", ""),
            source_key=data.get("source_key"),
            aliases=data.get("aliases", []),
            related_terms=data.get("related_terms", []),
            anti_patterns=data.get("anti_patterns", []),
            notes=data.get("notes"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def format_for_prompt(self) -> str:
        """Format concept for LLM prompt."""
        lines = [f"**{self.term}**: {self.definition}"]
        if self.aliases:
            lines.append(f"  Aliases: {', '.join(self.aliases)}")
        if self.anti_patterns:
            lines.append(f"  Do NOT use: {', '.join(self.anti_patterns)}")
        if self.notes:
            lines.append(f"  Note: {self.notes}")
        return "\n".join(lines)


@dataclass
class Position:
    """
    A normative position or thesis established in your work.

    Positions are claims that new writing should not contradict
    (unless explicitly revising them).
    """

    id: UUID = field(default_factory=uuid4)

    claim: str = ""
    """The thesis statement."""

    source_key: str | None = None
    """Citation key of the source that establishes this."""

    supporting_evidence: list[str] = field(default_factory=list)
    """Key points supporting this position."""

    implications: list[str] = field(default_factory=list)
    """What this position implies."""

    supersedes: str | None = None
    """ID of position this supersedes (if revised)."""

    superseded_by: str | None = None
    """ID of position that supersedes this (if revised)."""

    tags: list[str] = field(default_factory=list)
    """Tags for categorization."""

    notes: str | None = None
    """Additional context."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_current(self) -> bool:
        """Is this position still current (not superseded)?"""
        return self.superseded_by is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "claim": self.claim,
            "source_key": self.source_key,
            "supporting_evidence": self.supporting_evidence,
            "implications": self.implications,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "tags": self.tags,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        return cls(
            id=UUID(data["id"]),
            claim=data["claim"],
            source_key=data.get("source_key"),
            supporting_evidence=data.get("supporting_evidence", []),
            implications=data.get("implications", []),
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            tags=data.get("tags", []),
            notes=data.get("notes"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def format_for_prompt(self) -> str:
        """Format position for LLM prompt."""
        lines = [f"**Position**: {self.claim}"]
        if self.source_key:
            lines.append(f"  Source: [@{self.source_key}]")
        if self.implications:
            lines.append("  Implies:")
            for imp in self.implications:
                lines.append(f"    - {imp}")
        return "\n".join(lines)


@dataclass
class WritingClaim:
    """
    A claim made in new writing that must be backed by citations.
    """

    id: UUID = field(default_factory=uuid4)

    assertion: str = ""
    """The claim being made."""

    strength: ClaimStrength = ClaimStrength.ASSERTION
    """How strong is this claim?"""

    cites: list[str] = field(default_factory=list)
    """Citation keys backing this claim."""

    extends_position: str | None = None
    """ID of Position this extends (if any)."""

    introduces_concept: str | None = None
    """Term being introduced (if introducing new concept)."""

    context: str | None = None
    """Surrounding text for context."""

    location: str | None = None
    """Location in document (e.g., 'section 2.1')."""

    verified: bool = False
    """Has this claim been verified against the corpus?"""

    warnings: list[str] = field(default_factory=list)
    """Warnings from verification."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "assertion": self.assertion,
            "strength": self.strength.value,
            "cites": self.cites,
            "extends_position": self.extends_position,
            "introduces_concept": self.introduces_concept,
            "context": self.context,
            "location": self.location,
            "verified": self.verified,
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WritingClaim":
        return cls(
            id=UUID(data["id"]),
            assertion=data["assertion"],
            strength=ClaimStrength(data.get("strength", "assertion")),
            cites=data.get("cites", []),
            extends_position=data.get("extends_position"),
            introduces_concept=data.get("introduces_concept"),
            context=data.get("context"),
            location=data.get("location"),
            verified=data.get("verified", False),
            warnings=data.get("warnings", []),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def format_with_citations(self) -> str:
        """Format claim with Pandoc-style citations."""
        if not self.cites:
            return self.assertion

        cite_str = "; ".join(f"@{c}" for c in self.cites)
        return f"{self.assertion} [{cite_str}]"


@dataclass
class NonfictionClaim:
    """A typed claim about non-fiction content (for verification)."""

    type: NonfictionClaimType

    # Claim-specific fields
    assertion: str | None = None
    """The assertion being verified."""

    citation_keys: list[str] | None = None
    """Citation keys involved."""

    term: str | None = None
    """Term being used/defined."""

    position_id: str | None = None
    """Position being extended/checked."""

    def describe(self) -> str:
        """Human-readable description."""
        if self.type == NonfictionClaimType.CITES_SOURCE:
            cites = ", ".join(self.citation_keys or [])
            return f"cites_source([{cites}])"
        elif self.type == NonfictionClaimType.USES_TERM:
            return f"uses_term({self.term})"
        elif self.type == NonfictionClaimType.CONSISTENT_WITH_CORPUS:
            return "consistent_with_corpus"
        elif self.type == NonfictionClaimType.EXTENDS_POSITION:
            return f"extends_position({self.position_id})"
        elif self.type == NonfictionClaimType.INTRODUCES_CONCEPT:
            return f"introduces_concept({self.term})"
        else:
            return self.type.value


# Convenience constructors

def source(
    doi: str | None = None,
    title: str = "",
    authors: list[str] | None = None,
    year: int | None = None,
    canonical: bool = False,
    **kwargs,
) -> Source:
    """Create a Source with convenience defaults."""
    author_objs = [Author(name=name) for name in (authors or [])]
    return Source(
        doi=doi,
        title=title,
        authors=author_objs,
        year=year,
        source_type=SourceType.CANONICAL if canonical else SourceType.EXTERNAL,
        **kwargs,
    )


def concept(
    term: str,
    definition: str,
    source_key: str | None = None,
    aliases: list[str] | None = None,
) -> Concept:
    """Create a Concept."""
    return Concept(
        term=term,
        definition=definition,
        source_key=source_key,
        aliases=aliases or [],
    )


def position(
    claim: str,
    source_key: str | None = None,
    supporting_evidence: list[str] | None = None,
    tags: list[str] | None = None,
) -> Position:
    """Create a Position."""
    return Position(
        claim=claim,
        source_key=source_key,
        supporting_evidence=supporting_evidence or [],
        tags=tags or [],
    )


def writing_claim(
    assertion: str,
    cites: list[str] | None = None,
    strength: ClaimStrength = ClaimStrength.ASSERTION,
) -> WritingClaim:
    """Create a WritingClaim."""
    return WritingClaim(
        assertion=assertion,
        cites=cites or [],
        strength=strength,
    )
