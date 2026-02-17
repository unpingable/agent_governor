# SPDX-License-Identifier: Apache-2.0
"""Tests for nonfiction governor types."""

import pytest
from uuid import UUID

from nonfiction_governor.types import (
    Source,
    SourceType,
    Author,
    Concept,
    Position,
    WritingClaim,
    ClaimStrength,
    NonfictionClaim,
    NonfictionClaimType,
    source,
    concept,
    position,
    writing_claim,
)


class TestAuthor:
    """Tests for Author dataclass."""

    def test_create_author(self):
        """Can create an author."""
        a = Author(name="John Smith")
        assert a.name == "John Smith"

    def test_author_with_orcid(self):
        """Author can have ORCID."""
        a = Author(name="Jane Doe", orcid="0000-0001-2345-6789")
        assert a.orcid == "0000-0001-2345-6789"

    def test_author_str(self):
        """Author string representation is name."""
        a = Author(name="Alice Bob")
        assert str(a) == "Alice Bob"

    def test_author_serialization(self):
        """Author can be serialized and deserialized."""
        a = Author(name="Test", orcid="123", affiliation="University")
        data = a.to_dict()
        restored = Author.from_dict(data)
        assert restored.name == a.name
        assert restored.orcid == a.orcid
        assert restored.affiliation == a.affiliation


class TestSource:
    """Tests for Source dataclass."""

    def test_create_source(self):
        """Can create a source."""
        s = Source(title="Test Paper")
        assert s.title == "Test Paper"
        assert isinstance(s.id, UUID)

    def test_source_with_doi(self):
        """Source can have DOI."""
        s = Source(doi="10.1234/test", title="Paper")
        assert s.doi == "10.1234/test"

    def test_source_type_defaults_to_external(self):
        """Source type defaults to external."""
        s = Source(title="Test")
        assert s.source_type == SourceType.EXTERNAL

    def test_canonical_source(self):
        """Can create canonical source."""
        s = Source(title="My Paper", source_type=SourceType.CANONICAL)
        assert s.is_canonical

    def test_external_source_not_canonical(self):
        """External sources are not canonical."""
        s = Source(title="Their Paper", source_type=SourceType.EXTERNAL)
        assert not s.is_canonical

    def test_auto_citation_key(self):
        """Citation key is generated from author and year."""
        s = Source(
            title="Test",
            authors=[Author(name="John Smith")],
            year=2024,
        )
        assert s.citation_key == "smith2024"

    def test_explicit_citation_key(self):
        """Explicit citation key overrides auto-generation."""
        s = Source(
            title="Test",
            authors=[Author(name="John Smith")],
            year=2024,
            citation_key="mykey",
        )
        assert s.citation_key == "mykey"

    def test_source_serialization(self):
        """Source can be serialized and deserialized."""
        s = Source(
            doi="10.1234/test",
            title="Test Paper",
            authors=[Author(name="Test Author")],
            year=2024,
            source_type=SourceType.CANONICAL,
            citation_key="test2024",
        )
        data = s.to_dict()
        restored = Source.from_dict(data)
        assert restored.doi == s.doi
        assert restored.title == s.title
        assert restored.is_canonical

    def test_bibtex_output(self):
        """Source can generate BibTeX."""
        s = Source(
            title="Test Paper",
            authors=[Author(name="John Smith"), Author(name="Jane Doe")],
            year=2024,
            doi="10.1234/test",
            citation_key="smith2024",
        )
        bibtex = s.to_bibtex()
        assert "@article{smith2024" in bibtex
        assert "title = {Test Paper}" in bibtex
        assert "John Smith and Jane Doe" in bibtex

    def test_format_citation_single_author(self):
        """Format citation with single author."""
        s = Source(
            title="Test",
            authors=[Author(name="John Smith")],
            year=2024,
        )
        assert s.format_citation() == "Smith (2024)"

    def test_format_citation_two_authors(self):
        """Format citation with two authors."""
        s = Source(
            title="Test",
            authors=[Author(name="John Smith"), Author(name="Jane Doe")],
            year=2024,
        )
        assert s.format_citation() == "Smith & Doe (2024)"

    def test_format_citation_many_authors(self):
        """Format citation with many authors uses et al."""
        s = Source(
            title="Test",
            authors=[Author(name="A One"), Author(name="B Two"), Author(name="C Three")],
            year=2024,
        )
        assert "et al." in s.format_citation()


class TestConcept:
    """Tests for Concept dataclass."""

    def test_create_concept(self):
        """Can create a concept."""
        c = Concept(term="NLAI", definition="Language is a proposal")
        assert c.term == "NLAI"

    def test_concept_matches_term(self):
        """Concept matches text containing term."""
        c = Concept(term="NLAI", definition="...")
        assert c.matches("The NLAI principle states that")
        assert not c.matches("Some other text")

    def test_concept_matches_alias(self):
        """Concept matches aliases."""
        c = Concept(term="NLAI", definition="...", aliases=["Language is a proposal"])
        assert c.matches("Language is a proposal, not authority")

    def test_concept_serialization(self):
        """Concept can be serialized and deserialized."""
        c = Concept(
            term="test",
            definition="test def",
            source_key="source1",
            aliases=["alias1"],
            anti_patterns=["bad"],
        )
        data = c.to_dict()
        restored = Concept.from_dict(data)
        assert restored.term == c.term
        assert restored.aliases == c.aliases
        assert restored.anti_patterns == c.anti_patterns

    def test_concept_format_for_prompt(self):
        """Concept can be formatted for prompt."""
        c = Concept(
            term="NLAI",
            definition="Language is a proposal",
            aliases=["proposal principle"],
            anti_patterns=["trust"],
        )
        formatted = c.format_for_prompt()
        assert "NLAI" in formatted
        assert "proposal principle" in formatted
        assert "trust" in formatted


class TestPosition:
    """Tests for Position dataclass."""

    def test_create_position(self):
        """Can create a position."""
        p = Position(claim="AI agents need governance")
        assert p.claim == "AI agents need governance"

    def test_position_is_current_by_default(self):
        """New positions are current."""
        p = Position(claim="test")
        assert p.is_current

    def test_position_superseded(self):
        """Superseded positions are not current."""
        p = Position(claim="test", superseded_by="new-id")
        assert not p.is_current

    def test_position_with_tags(self):
        """Position can have tags."""
        p = Position(claim="test", tags=["epistemology", "design"])
        assert "epistemology" in p.tags

    def test_position_serialization(self):
        """Position can be serialized and deserialized."""
        p = Position(
            claim="test claim",
            source_key="source1",
            tags=["tag1"],
            supporting_evidence=["evidence1"],
        )
        data = p.to_dict()
        restored = Position.from_dict(data)
        assert restored.claim == p.claim
        assert restored.tags == p.tags

    def test_position_format_for_prompt(self):
        """Position can be formatted for prompt."""
        p = Position(
            claim="AI agents need governance",
            source_key="beck2024",
            implications=["Must verify all claims"],
        )
        formatted = p.format_for_prompt()
        assert "AI agents need governance" in formatted
        assert "beck2024" in formatted


class TestWritingClaim:
    """Tests for WritingClaim dataclass."""

    def test_create_writing_claim(self):
        """Can create a writing claim."""
        c = WritingClaim(assertion="LLMs hallucinate")
        assert c.assertion == "LLMs hallucinate"

    def test_writing_claim_with_citations(self):
        """Writing claim can have citations."""
        c = WritingClaim(
            assertion="LLMs hallucinate",
            cites=["smith2024", "doe2023"],
        )
        assert "smith2024" in c.cites

    def test_writing_claim_strength_default(self):
        """Default strength is assertion."""
        c = WritingClaim(assertion="test")
        assert c.strength == ClaimStrength.ASSERTION

    def test_writing_claim_format_with_citations(self):
        """Can format claim with Pandoc-style citations."""
        c = WritingClaim(
            assertion="LLMs hallucinate",
            cites=["smith2024"],
        )
        formatted = c.format_with_citations()
        assert "[@smith2024]" in formatted

    def test_writing_claim_format_multiple_citations(self):
        """Can format claim with multiple citations."""
        c = WritingClaim(
            assertion="LLMs hallucinate",
            cites=["smith2024", "doe2023"],
        )
        formatted = c.format_with_citations()
        assert "@smith2024" in formatted
        assert "@doe2023" in formatted


class TestConvenienceConstructors:
    """Tests for convenience constructor functions."""

    def test_source_constructor(self):
        """source() creates Source."""
        s = source(doi="10.1234/test", title="Test", canonical=True)
        assert s.doi == "10.1234/test"
        assert s.is_canonical

    def test_source_with_author_strings(self):
        """source() accepts author names as strings."""
        s = source(title="Test", authors=["John Smith", "Jane Doe"], year=2024)
        assert len(s.authors) == 2
        assert s.authors[0].name == "John Smith"

    def test_concept_constructor(self):
        """concept() creates Concept."""
        c = concept("NLAI", "Language is a proposal", source_key="beck2024")
        assert c.term == "NLAI"
        assert c.source_key == "beck2024"

    def test_position_constructor(self):
        """position() creates Position."""
        p = position("AI needs governance", source_key="beck2024", tags=["design"])
        assert p.claim == "AI needs governance"
        assert "design" in p.tags

    def test_writing_claim_constructor(self):
        """writing_claim() creates WritingClaim."""
        c = writing_claim("LLMs hallucinate", cites=["smith2024"])
        assert c.assertion == "LLMs hallucinate"
        assert "smith2024" in c.cites


class TestNonfictionClaim:
    """Tests for NonfictionClaim (verification claims)."""

    def test_cites_source_claim(self):
        """Can create cites_source claim."""
        c = NonfictionClaim(
            type=NonfictionClaimType.CITES_SOURCE,
            citation_keys=["smith2024"],
        )
        assert "smith2024" in c.describe()

    def test_uses_term_claim(self):
        """Can create uses_term claim."""
        c = NonfictionClaim(
            type=NonfictionClaimType.USES_TERM,
            term="NLAI",
        )
        assert "NLAI" in c.describe()

    def test_extends_position_claim(self):
        """Can create extends_position claim."""
        c = NonfictionClaim(
            type=NonfictionClaimType.EXTENDS_POSITION,
            position_id="abc123",
        )
        assert "abc123" in c.describe()
