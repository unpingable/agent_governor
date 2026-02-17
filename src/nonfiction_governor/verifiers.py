# SPDX-License-Identifier: Apache-2.0
"""
Verifiers for non-fiction writing.

Verify that new writing:
- Cites valid sources
- Uses terminology correctly
- Doesn't contradict established positions
"""

import re
from dataclasses import dataclass, field
from typing import Any

from .corpus import Corpus, CorpusConflict
from .types import (
    NonfictionClaim,
    NonfictionClaimType,
    WritingClaim,
    ClaimStrength,
)


@dataclass
class VerificationResult:
    """Result of verifying a claim."""

    valid: bool
    claim: NonfictionClaim | WritingClaim
    message: str
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class CitationVerifier:
    """
    Verify that citations are valid.

    Checks:
    - Citation keys exist in corpus
    - Canonical vs external sources
    - Citation completeness (strong claims need citations)
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def extract_citations(self, text: str) -> list[str]:
        """
        Extract citation keys from text.

        Supports Pandoc-style citations:
        - [@key]
        - [@key1; @key2]
        - @key (inline)
        """
        citations = []

        # Bracketed citations: [@key] or [@key1; @key2]
        bracketed = re.findall(r"\[@([^\]]+)\]", text)
        for bracket in bracketed:
            # Split by ; for multiple citations
            for cite in bracket.split(";"):
                cite = cite.strip()
                if cite.startswith("@"):
                    cite = cite[1:]
                if cite:
                    citations.append(cite)

        # Inline citations: @key (word boundary)
        inline = re.findall(r"(?<![\\@])@(\w+)", text)
        citations.extend(inline)

        return list(set(citations))

    def verify_citation(self, citation_key: str) -> VerificationResult:
        """Verify a single citation key exists."""
        claim = NonfictionClaim(
            type=NonfictionClaimType.CITES_SOURCE,
            citation_keys=[citation_key],
        )

        source = self.corpus.get_source(citation_key)
        if source:
            msg = f"Valid citation: {source.title}" if source.title else f"Valid citation: {citation_key}"
            return VerificationResult(valid=True, claim=claim, message=msg)

        return VerificationResult(
            valid=False,
            claim=claim,
            message=f"Unknown citation key: {citation_key}",
            suggestions=[
                "Add this source to the corpus with: corpus.add_reference(doi='...')",
                f"Or check spelling of '{citation_key}'",
            ],
        )

    def verify_text_citations(self, text: str) -> list[VerificationResult]:
        """Verify all citations in text."""
        citations = self.extract_citations(text)
        return [self.verify_citation(key) for key in citations]

    def check_citation_completeness(
        self,
        claim: WritingClaim,
        require_canonical: bool = False,
    ) -> VerificationResult:
        """
        Check if a claim has sufficient citations.

        Strong assertions require citations.
        Can optionally require canonical (your own) sources.
        """
        nf_claim = NonfictionClaim(
            type=NonfictionClaimType.CITES_SOURCE,
            assertion=claim.assertion,
            citation_keys=claim.cites,
        )

        # Assertions and arguments require citations
        if claim.strength in (ClaimStrength.ASSERTION, ClaimStrength.ARGUMENT):
            if not claim.cites:
                return VerificationResult(
                    valid=False,
                    claim=nf_claim,
                    message=f"{claim.strength.value.title()} claims require citations",
                    suggestions=["Add relevant citations with [@citation_key]"],
                )

        # Check all citations are valid
        for cite in claim.cites:
            source = self.corpus.get_source(cite)
            if not source:
                return VerificationResult(
                    valid=False,
                    claim=nf_claim,
                    message=f"Unknown citation: {cite}",
                )

            if require_canonical and not source.is_canonical:
                return VerificationResult(
                    valid=False,
                    claim=nf_claim,
                    message=f"Citation '{cite}' is external, but canonical source required",
                    warnings=[f"Consider citing your own work instead of or in addition to '{cite}'"],
                )

        return VerificationResult(
            valid=True,
            claim=nf_claim,
            message=f"Claim properly cited ({len(claim.cites)} citation(s))",
        )


class TerminologyVerifier:
    """
    Verify that defined terms are used correctly.

    Checks:
    - Terms are used with correct meaning
    - Anti-patterns are not present
    - New terms are introduced properly
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def verify_term_usage(
        self,
        term: str,
        context: str,
    ) -> VerificationResult:
        """Verify a term is used correctly in context."""
        claim = NonfictionClaim(
            type=NonfictionClaimType.USES_TERM,
            term=term,
        )

        concept = self.corpus.get_concept(term)
        if not concept:
            return VerificationResult(
                valid=True,
                claim=claim,
                message=f"Term '{term}' not in corpus (free to use)",
                warnings=["Consider defining this term if it's important to your work"],
            )

        # Check for anti-patterns
        for anti_pattern in concept.anti_patterns:
            if anti_pattern.lower() in context.lower():
                return VerificationResult(
                    valid=False,
                    claim=claim,
                    message=f"Term '{term}' used with anti-pattern '{anti_pattern}'",
                    suggestions=[
                        f"The term '{term}' should not be used with '{anti_pattern}'",
                        f"Definition: {concept.definition}",
                    ],
                )

        return VerificationResult(
            valid=True,
            claim=claim,
            message=f"Term '{term}' used correctly",
        )

    def find_terminology_issues(self, text: str) -> list[VerificationResult]:
        """Find all terminology issues in text."""
        results = []

        # Check all defined concepts
        for concept in self.corpus.all_concepts():
            if concept.matches(text):
                result = self.verify_term_usage(concept.term, text)
                if not result.valid or result.warnings:
                    results.append(result)

        return results

    def verify_new_term(
        self,
        term: str,
        definition: str | None = None,
    ) -> VerificationResult:
        """Verify introduction of a new term."""
        claim = NonfictionClaim(
            type=NonfictionClaimType.INTRODUCES_CONCEPT,
            term=term,
        )

        # Check if term already defined
        existing = self.corpus.get_concept(term)
        if existing:
            if definition and definition != existing.definition:
                return VerificationResult(
                    valid=False,
                    claim=claim,
                    message=f"Term '{term}' already defined differently",
                    suggestions=[
                        f"Existing definition: {existing.definition}",
                        "Use the existing definition or explicitly revise it",
                    ],
                )
            return VerificationResult(
                valid=True,
                claim=claim,
                message=f"Term '{term}' already defined (reusing)",
            )

        # New term should have definition
        if not definition:
            return VerificationResult(
                valid=False,
                claim=claim,
                message=f"New term '{term}' requires a definition",
                suggestions=["Provide a definition when introducing new terminology"],
            )

        return VerificationResult(
            valid=True,
            claim=claim,
            message=f"New term '{term}' properly introduced",
        )


class ConsistencyVerifier:
    """
    Verify consistency with established positions.

    Checks:
    - New claims don't contradict corpus positions
    - Extensions are properly attributed
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def check_consistency(
        self,
        claim_text: str,
        positions_to_check: list[str] | None = None,
    ) -> VerificationResult:
        """
        Check if a claim is consistent with corpus positions.

        Note: Deep semantic checking would require an LLM.
        This performs structural checks only.
        """
        claim = NonfictionClaim(
            type=NonfictionClaimType.CONSISTENT_WITH_CORPUS,
            assertion=claim_text,
        )

        # Get positions to check
        if positions_to_check:
            positions = [
                self.corpus.get_position(pid)
                for pid in positions_to_check
                if self.corpus.get_position(pid)
            ]
        else:
            positions = self.corpus.current_positions()

        # Structural conflict detection (limited without NLP)
        conflicts = self.corpus.find_conflicts(claim_text)

        if conflicts:
            error_conflicts = [c for c in conflicts if c.severity == "error"]
            warning_conflicts = [c for c in conflicts if c.severity == "warning"]

            if error_conflicts:
                return VerificationResult(
                    valid=False,
                    claim=claim,
                    message=error_conflicts[0].description,
                    warnings=[c.description for c in warning_conflicts],
                )

            return VerificationResult(
                valid=True,
                claim=claim,
                message="Claim consistent with corpus (structural check)",
                warnings=[c.description for c in warning_conflicts],
            )

        return VerificationResult(
            valid=True,
            claim=claim,
            message="Claim consistent with corpus (structural check passed)",
        )

    def verify_extension(
        self,
        claim_text: str,
        extends_position_id: str,
    ) -> VerificationResult:
        """Verify that a claim properly extends a position."""
        claim = NonfictionClaim(
            type=NonfictionClaimType.EXTENDS_POSITION,
            assertion=claim_text,
            position_id=extends_position_id,
        )

        position = self.corpus.get_position(extends_position_id)
        if not position:
            return VerificationResult(
                valid=False,
                claim=claim,
                message=f"Position '{extends_position_id}' not found in corpus",
            )

        if not position.is_current:
            return VerificationResult(
                valid=False,
                claim=claim,
                message=f"Position '{extends_position_id}' has been superseded",
                suggestions=[
                    f"This position was superseded by: {position.superseded_by}",
                    "Extend the current position instead",
                ],
            )

        return VerificationResult(
            valid=True,
            claim=claim,
            message=f"Claim extends position: {position.claim[:50]}...",
        )


class NonfictionVerifier:
    """
    Combined verifier for non-fiction writing.

    Brings together citation, terminology, and consistency verification.
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self.citation = CitationVerifier(corpus)
        self.terminology = TerminologyVerifier(corpus)
        self.consistency = ConsistencyVerifier(corpus)

    def verify_writing_claim(self, claim: WritingClaim) -> list[VerificationResult]:
        """Verify a writing claim comprehensively."""
        results = []

        # Check citations
        results.append(self.citation.check_citation_completeness(claim))

        # Check terminology in assertion
        term_issues = self.terminology.find_terminology_issues(claim.assertion)
        results.extend(term_issues)

        # Check consistency
        results.append(self.consistency.check_consistency(claim.assertion))

        # Check extension if specified
        if claim.extends_position:
            results.append(
                self.consistency.verify_extension(claim.assertion, claim.extends_position)
            )

        # Check new term introduction
        if claim.introduces_concept:
            results.append(
                self.terminology.verify_new_term(claim.introduces_concept)
            )

        return results

    def verify_text(self, text: str) -> list[VerificationResult]:
        """
        Verify a block of text.

        Performs structural verification:
        - Citation validity
        - Terminology usage
        - Basic consistency checks
        """
        results = []

        # Verify all citations
        results.extend(self.citation.verify_text_citations(text))

        # Check terminology
        results.extend(self.terminology.find_terminology_issues(text))

        # Consistency check on whole text
        results.append(self.consistency.check_consistency(text))

        return results

    def verify_all(
        self,
        claims: list[WritingClaim],
    ) -> list[VerificationResult]:
        """Verify multiple claims."""
        results = []
        for claim in claims:
            results.extend(self.verify_writing_claim(claim))
        return results
