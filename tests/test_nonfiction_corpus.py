# SPDX-License-Identifier: Apache-2.0
"""Tests for nonfiction governor corpus."""

import pytest
from pathlib import Path

from nonfiction_governor.corpus import Corpus
from nonfiction_governor.types import Source, Concept, Position, SourceType, Author


@pytest.fixture
def corpus_dir(tmp_path):
    """Create a temporary corpus directory."""
    return tmp_path / ".nonfiction"


@pytest.fixture
def corpus(corpus_dir):
    """Create a corpus."""
    corpus_dir.mkdir()
    return Corpus(corpus_dir)


class TestCorpusSources:
    """Tests for corpus source management."""

    def test_add_source(self, corpus):
        """Can add a source to corpus."""
        source = corpus.add_source(
            title="Test Paper",
            authors=["John Smith"],
            year=2024,
        )
        assert source.title == "Test Paper"
        assert corpus.has_source(source.citation_key)

    def test_add_canonical_source(self, corpus):
        """Can add canonical (your own) source."""
        source = corpus.add_source(
            title="My Paper",
            authors=["Me"],
            year=2024,
            canonical=True,
        )
        assert source.is_canonical
        assert source in corpus.canonical_sources()

    def test_add_external_source(self, corpus):
        """Can add external reference."""
        source = corpus.add_source(
            title="Their Paper",
            authors=["Them"],
            year=2024,
            canonical=False,
        )
        assert not source.is_canonical
        assert source in corpus.external_sources()

    def test_get_source_by_key(self, corpus):
        """Can retrieve source by citation key."""
        corpus.add_source(
            title="Test",
            authors=["Smith"],
            year=2024,
            citation_key="smith2024",
        )
        source = corpus.get_source("smith2024")
        assert source is not None
        assert source.title == "Test"

    def test_get_nonexistent_source(self, corpus):
        """Returns None for nonexistent source."""
        assert corpus.get_source("nonexistent") is None

    def test_has_source(self, corpus):
        """has_source returns correct boolean."""
        corpus.add_source(title="Test", citation_key="test1")
        assert corpus.has_source("test1")
        assert not corpus.has_source("test2")

    def test_all_sources(self, corpus):
        """all_sources returns all sources."""
        corpus.add_source(title="Paper 1", citation_key="p1", canonical=True)
        corpus.add_source(title="Paper 2", citation_key="p2", canonical=False)
        all_sources = corpus.all_sources()
        assert len(all_sources) == 2

    def test_persistence(self, corpus_dir):
        """Corpus persists to disk."""
        corpus1 = Corpus(corpus_dir)
        corpus1.add_source(title="Test", citation_key="test1")

        # Load in new instance
        corpus2 = Corpus(corpus_dir)
        assert corpus2.has_source("test1")


class TestCorpusConcepts:
    """Tests for corpus concept management."""

    def test_add_concept(self, corpus):
        """Can add concept to corpus."""
        concept = corpus.add_concept(
            term="NLAI",
            definition="Language is a proposal, not an authority",
        )
        assert concept.term == "NLAI"

    def test_add_concept_with_source(self, corpus):
        """Can link concept to source."""
        corpus.add_source(title="Paper", citation_key="source1", canonical=True)
        concept = corpus.add_concept(
            term="NLAI",
            definition="...",
            source_key="source1",
        )

        assert concept.source_key == "source1"
        # Source should track concept
        source = corpus.get_source("source1")
        assert "NLAI" in source.concepts_defined

    def test_get_concept(self, corpus):
        """Can retrieve concept by term."""
        corpus.add_concept(term="test", definition="test def")
        concept = corpus.get_concept("test")
        assert concept is not None
        assert concept.definition == "test def"

    def test_find_concept_in_text(self, corpus):
        """Can find concepts mentioned in text."""
        corpus.add_concept(term="NLAI", definition="...")
        corpus.add_concept(term="epistemic", definition="...")

        found = corpus.find_concept("The NLAI principle requires epistemic humility")
        terms = [c.term for c in found]
        assert "NLAI" in terms
        assert "epistemic" in terms

    def test_all_concepts(self, corpus):
        """all_concepts returns all concepts."""
        corpus.add_concept(term="term1", definition="def1")
        corpus.add_concept(term="term2", definition="def2")
        assert len(corpus.all_concepts()) == 2


class TestCorpusPositions:
    """Tests for corpus position management."""

    def test_add_position(self, corpus):
        """Can add position to corpus."""
        pos = corpus.add_position(
            claim="AI agents need governance",
        )
        assert pos.claim == "AI agents need governance"

    def test_add_position_with_source(self, corpus):
        """Can link position to source."""
        corpus.add_source(title="Paper", citation_key="source1", canonical=True)
        pos = corpus.add_position(
            claim="Test claim",
            source_key="source1",
        )

        assert pos.source_key == "source1"
        source = corpus.get_source("source1")
        assert str(pos.id) in source.positions_taken

    def test_get_position(self, corpus):
        """Can retrieve position by ID."""
        pos = corpus.add_position(claim="Test")
        retrieved = corpus.get_position(pos.id)
        assert retrieved is not None
        assert retrieved.claim == "Test"

    def test_current_positions(self, corpus):
        """current_positions excludes superseded."""
        pos1 = corpus.add_position(claim="Old claim")
        pos2 = corpus.add_position(claim="New claim")

        current = corpus.current_positions()
        assert len(current) == 2

        # Supersede pos1
        corpus.revise_position(pos1.id, "Revised claim")

        current = corpus.current_positions()
        assert len(current) == 2  # pos2 and new revision

    def test_positions_by_tag(self, corpus):
        """Can filter positions by tag."""
        corpus.add_position(claim="Claim 1", tags=["epistemology"])
        corpus.add_position(claim="Claim 2", tags=["design"])
        corpus.add_position(claim="Claim 3", tags=["epistemology", "design"])

        epist = corpus.positions_by_tag("epistemology")
        assert len(epist) == 2

    def test_revise_position(self, corpus):
        """Can revise (supersede) a position."""
        old = corpus.add_position(claim="Old claim")
        new = corpus.revise_position(old.id, "New claim")

        assert new is not None
        assert new.supersedes == str(old.id)

        # Old position should be marked superseded
        old_updated = corpus.get_position(old.id)
        assert old_updated.superseded_by == str(new.id)
        assert not old_updated.is_current


class TestCorpusVerification:
    """Tests for corpus verification helpers."""

    def test_check_valid_citation(self, corpus):
        """Valid citation key passes."""
        corpus.add_source(title="Test", citation_key="test1")
        valid, message = corpus.check_citation("test1")
        assert valid

    def test_check_invalid_citation(self, corpus):
        """Invalid citation key fails."""
        valid, message = corpus.check_citation("nonexistent")
        assert not valid
        assert "nonexistent" in message

    def test_check_term_usage_undefined(self, corpus):
        """Undefined terms are OK."""
        valid, message = corpus.check_term_usage("random", "random text")
        assert valid

    def test_check_term_usage_with_anti_pattern(self, corpus):
        """Anti-patterns are flagged."""
        corpus.add_concept(
            term="NLAI",
            definition="...",
            anti_patterns=["trust the agent"],
        )

        valid, message = corpus.check_term_usage(
            "NLAI",
            "We can trust the agent to follow NLAI",
        )
        assert not valid
        assert "anti-pattern" in message

    def test_find_conflicts_anti_patterns(self, corpus):
        """find_conflicts detects anti-pattern usage."""
        corpus.add_concept(
            term="receipt",
            definition="...",
            anti_patterns=["just trust"],
        )

        conflicts = corpus.find_conflicts("We can just trust the output")
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == "misuses_term"


class TestCorpusExport:
    """Tests for corpus export functionality."""

    def test_to_bibtex(self, corpus):
        """Can export as BibTeX."""
        corpus.add_source(
            title="Paper 1",
            authors=["Smith"],
            year=2024,
            citation_key="smith2024",
        )
        corpus.add_source(
            title="Paper 2",
            authors=["Doe"],
            year=2023,
            citation_key="doe2023",
        )

        bibtex = corpus.to_bibtex()
        assert "@article{smith2024" in bibtex
        assert "@article{doe2023" in bibtex

    def test_format_for_prompt(self, corpus):
        """Can format corpus for LLM prompt."""
        corpus.add_source(title="My Paper", citation_key="me2024", canonical=True)
        corpus.add_concept(term="NLAI", definition="Language is a proposal")
        corpus.add_position(claim="Agents need governance")

        prompt = corpus.format_for_prompt()
        assert "Corpus" in prompt
        assert "NLAI" in prompt
        assert "governance" in prompt
