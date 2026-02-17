# SPDX-License-Identifier: Apache-2.0
"""Tests for nonfiction governor verifiers."""

import pytest
from pathlib import Path

from nonfiction_governor.corpus import Corpus
from nonfiction_governor.types import WritingClaim, ClaimStrength
from nonfiction_governor.verifiers import (
    CitationVerifier,
    TerminologyVerifier,
    ConsistencyVerifier,
    NonfictionVerifier,
)


@pytest.fixture
def corpus_dir(tmp_path):
    """Create a temporary corpus directory."""
    d = tmp_path / ".nonfiction"
    d.mkdir()
    return d


@pytest.fixture
def corpus(corpus_dir):
    """Create a corpus with test data."""
    corpus = Corpus(corpus_dir)

    # Add sources
    corpus.add_source(title="My Paper", citation_key="beck2024", canonical=True)
    corpus.add_source(title="Other Paper", citation_key="smith2023", canonical=False)

    # Add concepts
    corpus.add_concept(
        term="NLAI",
        definition="Language is a proposal, not an authority",
        source_key="beck2024",
        anti_patterns=["trust the agent", "agents are authoritative"],
    )
    corpus.add_concept(
        term="receipt",
        definition="Cryptographic proof of verification",
        source_key="beck2024",
    )

    # Add positions
    corpus.add_position(
        claim="AI agents need governance to prevent hallucination",
        source_key="beck2024",
        tags=["epistemology"],
    )

    return corpus


class TestCitationVerifier:
    """Tests for CitationVerifier."""

    def test_extract_bracketed_citation(self, corpus):
        """Extracts [@key] style citations."""
        verifier = CitationVerifier(corpus)

        citations = verifier.extract_citations("This is true [@beck2024].")
        assert "beck2024" in citations

    def test_extract_multiple_citations(self, corpus):
        """Extracts multiple citations from brackets."""
        verifier = CitationVerifier(corpus)

        citations = verifier.extract_citations("See [@beck2024; @smith2023].")
        assert "beck2024" in citations
        assert "smith2023" in citations

    def test_extract_inline_citation(self, corpus):
        """Extracts @key style inline citations."""
        verifier = CitationVerifier(corpus)

        citations = verifier.extract_citations("As @beck2024 shows, this is true.")
        assert "beck2024" in citations

    def test_verify_valid_citation(self, corpus):
        """Valid citation passes verification."""
        verifier = CitationVerifier(corpus)

        result = verifier.verify_citation("beck2024")
        assert result.valid

    def test_verify_invalid_citation(self, corpus):
        """Invalid citation fails verification."""
        verifier = CitationVerifier(corpus)

        result = verifier.verify_citation("nonexistent")
        assert not result.valid
        assert "nonexistent" in result.message

    def test_verify_text_citations(self, corpus):
        """Can verify all citations in text."""
        verifier = CitationVerifier(corpus)

        results = verifier.verify_text_citations(
            "According to [@beck2024], we need governance. See also @unknown."
        )

        valid_count = sum(1 for r in results if r.valid)
        invalid_count = sum(1 for r in results if not r.valid)

        assert valid_count == 1
        assert invalid_count == 1

    def test_assertion_requires_citation(self, corpus):
        """Strong assertions require citations."""
        verifier = CitationVerifier(corpus)

        claim = WritingClaim(
            assertion="LLMs always hallucinate",
            strength=ClaimStrength.ASSERTION,
            cites=[],  # No citations!
        )

        result = verifier.check_citation_completeness(claim)
        assert not result.valid
        assert "require citations" in result.message.lower()

    def test_assertion_with_citation_passes(self, corpus):
        """Assertions with valid citations pass."""
        verifier = CitationVerifier(corpus)

        claim = WritingClaim(
            assertion="LLMs hallucinate",
            strength=ClaimStrength.ASSERTION,
            cites=["beck2024"],
        )

        result = verifier.check_citation_completeness(claim)
        assert result.valid

    def test_hypothesis_without_citation_ok(self, corpus):
        """Hypotheses don't require citations."""
        verifier = CitationVerifier(corpus)

        claim = WritingClaim(
            assertion="Perhaps LLMs could improve",
            strength=ClaimStrength.HYPOTHESIS,
            cites=[],
        )

        result = verifier.check_citation_completeness(claim)
        assert result.valid


class TestTerminologyVerifier:
    """Tests for TerminologyVerifier."""

    def test_undefined_term_ok(self, corpus):
        """Undefined terms are OK to use."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_term_usage("random", "some random context")
        assert result.valid

    def test_correct_term_usage(self, corpus):
        """Correct term usage passes."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_term_usage(
            "NLAI",
            "The NLAI principle requires verification",
        )
        assert result.valid

    def test_term_with_anti_pattern(self, corpus):
        """Anti-pattern usage fails."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_term_usage(
            "NLAI",
            "Following NLAI, we can trust the agent completely",
        )
        assert not result.valid
        assert "anti-pattern" in result.message

    def test_find_terminology_issues(self, corpus):
        """Can find all terminology issues in text."""
        verifier = TerminologyVerifier(corpus)

        results = verifier.find_terminology_issues(
            "NLAI means we can trust the agent without verification"
        )

        issues = [r for r in results if not r.valid]
        assert len(issues) > 0

    def test_new_term_with_definition(self, corpus):
        """New term with definition passes."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_new_term(
            "epistemic gate",
            definition="A verification checkpoint",
        )
        assert result.valid

    def test_new_term_without_definition(self, corpus):
        """New term without definition fails."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_new_term("epistemic gate", definition=None)
        assert not result.valid
        assert "definition" in result.message.lower()

    def test_existing_term_reuse(self, corpus):
        """Reusing existing term is OK."""
        verifier = TerminologyVerifier(corpus)

        result = verifier.verify_new_term(
            "NLAI",
            definition="Language is a proposal, not an authority",
        )
        assert result.valid


class TestConsistencyVerifier:
    """Tests for ConsistencyVerifier."""

    def test_consistent_claim(self, corpus):
        """Claim consistent with corpus passes."""
        verifier = ConsistencyVerifier(corpus)

        result = verifier.check_consistency(
            "AI agents benefit from governance structures"
        )
        assert result.valid

    def test_verify_valid_extension(self, corpus):
        """Valid extension of existing position passes."""
        verifier = ConsistencyVerifier(corpus)

        pos = corpus.current_positions()[0]
        result = verifier.verify_extension(
            "Governance should include verification steps",
            str(pos.id),
        )
        assert result.valid

    def test_extend_nonexistent_position(self, corpus):
        """Extending nonexistent position fails."""
        verifier = ConsistencyVerifier(corpus)

        result = verifier.verify_extension(
            "Some claim",
            "nonexistent-id",
        )
        assert not result.valid

    def test_extend_superseded_position(self, corpus):
        """Extending superseded position fails."""
        verifier = ConsistencyVerifier(corpus)

        old_pos = corpus.current_positions()[0]
        corpus.revise_position(str(old_pos.id), "New claim")

        result = verifier.verify_extension(
            "Some extension",
            str(old_pos.id),
        )
        assert not result.valid
        assert "superseded" in result.message.lower()


class TestNonfictionVerifier:
    """Tests for combined NonfictionVerifier."""

    def test_verify_writing_claim_complete(self, corpus):
        """Can verify a complete writing claim."""
        verifier = NonfictionVerifier(corpus)

        claim = WritingClaim(
            assertion="AI agents need governance",
            strength=ClaimStrength.ASSERTION,
            cites=["beck2024"],
        )

        results = verifier.verify_writing_claim(claim)
        errors = [r for r in results if not r.valid]
        assert len(errors) == 0

    def test_verify_writing_claim_missing_citation(self, corpus):
        """Detects missing citations."""
        verifier = NonfictionVerifier(corpus)

        claim = WritingClaim(
            assertion="All agents hallucinate",
            strength=ClaimStrength.ASSERTION,
            cites=[],  # Missing!
        )

        results = verifier.verify_writing_claim(claim)
        errors = [r for r in results if not r.valid]
        assert len(errors) > 0

    def test_verify_text_citations_and_terms(self, corpus):
        """Can verify text for citations and terminology."""
        verifier = NonfictionVerifier(corpus)

        # Good text
        results = verifier.verify_text(
            "According to [@beck2024], the NLAI principle requires verification."
        )
        errors = [r for r in results if not r.valid]
        assert len(errors) == 0

    def test_verify_text_with_issues(self, corpus):
        """Detects issues in text."""
        verifier = NonfictionVerifier(corpus)

        # Bad text: unknown citation, anti-pattern usage
        results = verifier.verify_text(
            "According to [@unknown], we can trust the agent following NLAI."
        )
        errors = [r for r in results if not r.valid]
        assert len(errors) > 0

    def test_verify_all_claims(self, corpus):
        """Can verify multiple claims at once."""
        verifier = NonfictionVerifier(corpus)

        claims = [
            WritingClaim(assertion="Claim 1", cites=["beck2024"]),
            WritingClaim(assertion="Claim 2", cites=["smith2023"]),
        ]

        results = verifier.verify_all(claims)
        # Should have results for each claim
        assert len(results) >= len(claims)
