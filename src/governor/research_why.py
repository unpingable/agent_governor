"""
Research Why Overlay: per-turn analysis of what was injected vs what was referenced.

Parses assistant output for source ref tokens and CANDIDATE_SOURCE lines,
compares against accepted sources, and produces a structured "why" analysis.

This is pure text analysis — no model cooperation required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Source ref patterns — same tokens the capture classifier uses
_SOURCE_REF_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("doi", re.compile(r"(?:doi:\s*|DOI:\s*|https?://doi\.org/)(10\.\d{4,}/[^\s,;)\]]+)")),
    ("arxiv", re.compile(r"(?:arxiv:\s*|arXiv:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)),
    ("cve", re.compile(r"(CVE-\d{4}-\d{4,})", re.IGNORECASE)),
    ("rfc", re.compile(r"(?:RFC\s+|rfc:\s*)(\d{3,})", re.IGNORECASE)),
    ("pypi", re.compile(r"(?:pypi:\s*|pip install\s+)([a-zA-Z0-9_-]+)", re.IGNORECASE)),
]

# CANDIDATE_SOURCE line pattern
_CANDIDATE_PATTERN = re.compile(
    r"CANDIDATE_SOURCE:\s*(\S+)",
    re.IGNORECASE,
)


# arXiv DOI prefix — doi:10.48550/arXiv.XXXX.XXXXX is the same paper as arxiv:XXXX.XXXXX
_ARXIV_DOI_PREFIX = "10.48550/arxiv."


def canonicalize_ref(ref_type: str, identifier: str) -> tuple[str, str]:
    """Canonicalize a source ref to prevent alias mismatches.

    doi:10.48550/arXiv.2001.08361 → arxiv:2001.08361
    Keeps the original form in SourceRef.raw for display.
    """
    if ref_type == "doi" and identifier.lower().startswith(_ARXIV_DOI_PREFIX):
        # Extract the arXiv ID from the DOI
        arxiv_id = identifier[len(_ARXIV_DOI_PREFIX):]
        return ("arxiv", arxiv_id)
    return (ref_type, identifier)


def canonical_form(ref_string: str) -> str:
    """Canonicalize a 'type:identifier' string for comparison.

    Returns a fully lowercased canonical form. DOIs are case-insensitive per spec.

    >>> canonical_form("doi:10.48550/arXiv.2001.08361")
    'arxiv:2001.08361'
    >>> canonical_form("doi:10.1234/FOO")
    'doi:10.1234/foo'
    """
    if ":" not in ref_string:
        return ref_string.lower()
    ref_type, identifier = ref_string.split(":", 1)
    ref_type, identifier = canonicalize_ref(ref_type.strip().lower(), identifier.strip())
    return f"{ref_type}:{identifier}".lower()


@dataclass
class SourceRef:
    """A source reference found in text."""
    ref_type: str
    identifier: str
    raw: str  # the full matched text

    @property
    def normalized(self) -> str:
        """Normalized form for comparison (e.g., 'doi:10.1234/foo').

        arXiv DOIs are canonicalized: doi:10.48550/arXiv.X → arxiv:X
        """
        canon_type, canon_id = canonicalize_ref(self.ref_type, self.identifier)
        return f"{canon_type}:{canon_id}"


@dataclass
class WhyOverlay:
    """Per-turn analysis of what was injected vs what was referenced.

    Fields are structured for direct rendering in the UI.
    """
    # What was injected into the system prompt
    injected_source_count: int = 0
    injected_sources: list[str] = field(default_factory=list)
    injected_claim_count: int = 0
    injected_claim_ids: list[str] = field(default_factory=list)

    # What the assistant output referenced
    referenced_sources: list[SourceRef] = field(default_factory=list)
    candidate_sources: list[str] = field(default_factory=list)

    # Floating refs: cited but not in accepted sources and not candidates
    floating_refs: list[SourceRef] = field(default_factory=list)

    # Matched refs: cited AND in accepted sources
    matched_refs: list[SourceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "injected": {
                "source_count": self.injected_source_count,
                "sources": self.injected_sources,
                "claim_count": self.injected_claim_count,
                "claim_ids": self.injected_claim_ids,
            },
            "referenced": {
                "sources": [
                    {"ref_type": r.ref_type, "identifier": r.identifier, "raw": r.raw}
                    for r in self.referenced_sources
                ],
                "candidates": self.candidate_sources,
            },
            "floating": [
                {"ref_type": r.ref_type, "identifier": r.identifier, "raw": r.raw}
                for r in self.floating_refs
            ],
            "matched": [
                {"ref_type": r.ref_type, "identifier": r.identifier, "raw": r.raw}
                for r in self.matched_refs
            ],
        }


def extract_source_refs(text: str) -> list[SourceRef]:
    """Extract all source reference tokens from text.

    Deduplicates using canonical form — doi:10.48550/arXiv.2001.08361 and
    arxiv:2001.08361 are treated as the same ref (the first occurrence wins).
    """
    refs: list[SourceRef] = []
    seen: set[str] = set()
    for ref_type, pattern in _SOURCE_REF_PATTERNS:
        for m in pattern.finditer(text):
            identifier = m.group(1).rstrip(".,;:")
            # Dedup on canonical form so arXiv DOIs and arXiv IDs collapse
            canon_type, canon_id = canonicalize_ref(ref_type, identifier)
            canonical = f"{canon_type}:{canon_id}".lower()
            if canonical not in seen:
                seen.add(canonical)
                refs.append(SourceRef(
                    ref_type=ref_type,
                    identifier=identifier,
                    raw=m.group(0),
                ))
    return refs


def extract_candidate_sources(text: str) -> list[str]:
    """Extract CANDIDATE_SOURCE: lines from assistant output."""
    candidates: list[str] = []
    seen: set[str] = set()
    for m in _CANDIDATE_PATTERN.finditer(text):
        ref = m.group(1)
        if ref.lower() not in seen:
            seen.add(ref.lower())
            candidates.append(ref)
    return candidates


def build_why_overlay(
    assistant_text: str,
    accepted_sources: list[str],
    accepted_claim_ids: list[str],
) -> WhyOverlay:
    """Build a WhyOverlay for a single assistant turn.

    Args:
        assistant_text: The assistant's response text.
        accepted_sources: Source refs injected into the system prompt
                         (e.g., ["doi:10.1234/foo", "pypi:numpy"]).
        accepted_claim_ids: Claim IDs injected (e.g., ["C-ABC123"]).

    Returns:
        WhyOverlay with injected/referenced/floating/matched analysis.
    """
    overlay = WhyOverlay(
        injected_source_count=len(accepted_sources),
        injected_sources=list(accepted_sources),
        injected_claim_count=len(accepted_claim_ids),
        injected_claim_ids=list(accepted_claim_ids),
    )

    # Parse assistant output
    overlay.referenced_sources = extract_source_refs(assistant_text)
    overlay.candidate_sources = extract_candidate_sources(assistant_text)

    # Canonicalize accepted sources for comparison (handles arXiv/DOI aliases)
    accepted_canonical = {canonical_form(s) for s in accepted_sources}
    candidate_canonical = {canonical_form(c) for c in overlay.candidate_sources}

    # Classify each referenced source
    for ref in overlay.referenced_sources:
        canonical = ref.normalized.lower()
        if canonical in accepted_canonical:
            overlay.matched_refs.append(ref)
        elif canonical not in candidate_canonical:
            overlay.floating_refs.append(ref)

    return overlay
