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


@dataclass
class SourceRef:
    """A source reference found in text."""
    ref_type: str
    identifier: str
    raw: str  # the full matched text

    @property
    def normalized(self) -> str:
        """Normalized form for comparison (e.g., 'doi:10.1234/foo')."""
        return f"{self.ref_type}:{self.identifier}"


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
    """Extract all source reference tokens from text."""
    refs: list[SourceRef] = []
    seen: set[str] = set()
    for ref_type, pattern in _SOURCE_REF_PATTERNS:
        for m in pattern.finditer(text):
            identifier = m.group(1).rstrip(".,;:")
            normalized = f"{ref_type}:{identifier}"
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
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

    # Normalize accepted sources for comparison
    accepted_lower = {s.lower() for s in accepted_sources}
    candidate_lower = {c.lower() for c in overlay.candidate_sources}

    # Classify each referenced source
    for ref in overlay.referenced_sources:
        normalized = ref.normalized.lower()
        if normalized in accepted_lower:
            overlay.matched_refs.append(ref)
        elif normalized not in candidate_lower:
            overlay.floating_refs.append(ref)

    return overlay
