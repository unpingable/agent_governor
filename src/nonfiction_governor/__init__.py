"""
Non-Fiction Governor - Constraint system for academic writing.

Maintains consistency with your corpus of prior work:
- Canonical sources (your papers) define terminology and positions
- New writing must cite sources and use terms correctly
- Cannot contradict established positions without explicit revision
"""

from .types import (
    Source,
    SourceType,
    Author,
    Concept,
    Position,
    WritingClaim,
    ClaimStrength,
    NonfictionClaim,
    NonfictionClaimType,
    # Convenience constructors
    source,
    concept,
    position,
    writing_claim,
)

from .corpus import Corpus, CorpusConflict

from .doi import (
    fetch_doi_metadata,
    fetch_source,
    normalize_doi,
    is_zenodo_doi,
    DOIFetchError,
    DOIMetadata,
)

from .verifiers import (
    CitationVerifier,
    TerminologyVerifier,
    ConsistencyVerifier,
    NonfictionVerifier,
    VerificationResult,
)


__all__ = [
    # Types
    "Source",
    "SourceType",
    "Author",
    "Concept",
    "Position",
    "WritingClaim",
    "ClaimStrength",
    "NonfictionClaim",
    "NonfictionClaimType",
    # Convenience constructors
    "source",
    "concept",
    "position",
    "writing_claim",
    # Corpus
    "Corpus",
    "CorpusConflict",
    # DOI
    "fetch_doi_metadata",
    "fetch_source",
    "normalize_doi",
    "is_zenodo_doi",
    "DOIFetchError",
    "DOIMetadata",
    # Verifiers
    "CitationVerifier",
    "TerminologyVerifier",
    "ConsistencyVerifier",
    "NonfictionVerifier",
    "VerificationResult",
]

__version__ = "0.1.0"
