"""
Claim signal extraction: detect implicit claims from text.

Extracts dates, entities, quantities, and assertive language using
regex pattern matching. Computes assertiveness scores and optionally
registers extracted signals as ASSUMED claims in the epistemic ledger.

Reference: ingest/epistemic_governor/src/epistemic_governor/claims.py:735-805

Signal categories:
- DATE: Year patterns (1800–2099)
- ENTITY: Capitalized multi-word names
- QUANTITY: Numbers with units (million, billion, percent, dollars, etc.)
- ASSERTIVE: Definitive/assertive language

Key invariants:
1. Patterns are compiled once at module level (like security.py)
2. Assertive phrases affect score but do NOT become standalone claims
3. Registered claims use ASSUMED provenance at confidence 0.2
4. Entity deduplication is on by default
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Signal Categories
# =============================================================================


class SignalCategory(str, Enum):
    """Categories of implicit claim signals in text."""

    DATE = "date"
    """Year pattern (1800–2099)."""

    ENTITY = "entity"
    """Capitalized multi-word name."""

    QUANTITY = "quantity"
    """Number with unit (million, billion, percent, dollars, etc.)."""

    ASSERTIVE = "assertive"
    """Assertive or definitive language."""


# =============================================================================
# Pre-compiled Patterns (module-level constants)
# =============================================================================

DATE_PATTERN = re.compile(r"\b(18\d{2}|19\d{2}|20\d{2})\b")

ENTITY_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

QUANTITY_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(million|billion|percent|%|dollars|USD|EUR)\b",
    re.IGNORECASE,
)

ASSERTIVE_PATTERN = re.compile(
    r"\b(definitely|certainly|clearly|undoubtedly|obviously|"
    r"was acquired|acquired in|founded in|established in|"
    r"is located|is headquartered|died in|born in)\b",
    re.IGNORECASE,
)


# =============================================================================
# Core Types
# =============================================================================


@dataclass
class SignalMatch:
    """A single signal extracted from text."""

    category: SignalCategory
    value: str
    span: tuple[int, int]
    line_number: int | None = None
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "value": self.value,
            "span": list(self.span),
            "line_number": self.line_number,
            "context": self.context,
        }


@dataclass
class ExtractionResult:
    """Result of signal extraction from text."""

    text_hash: str
    total_signals: int
    signals_by_category: dict[str, int]
    matches: list[SignalMatch]
    assertiveness_score: float

    @property
    def has_speculative_content(self) -> bool:
        """Any date, entity, or quantity found (content that could be wrong)."""
        return any(
            self.signals_by_category.get(cat.value, 0) > 0
            for cat in (SignalCategory.DATE, SignalCategory.ENTITY, SignalCategory.QUANTITY)
        )

    @property
    def date_count(self) -> int:
        return self.signals_by_category.get(SignalCategory.DATE.value, 0)

    @property
    def entity_count(self) -> int:
        return self.signals_by_category.get(SignalCategory.ENTITY.value, 0)

    @property
    def quantity_count(self) -> int:
        return self.signals_by_category.get(SignalCategory.QUANTITY.value, 0)

    @property
    def assertive_count(self) -> int:
        return self.signals_by_category.get(SignalCategory.ASSERTIVE.value, 0)

    @property
    def dates(self) -> list[str]:
        """Convenience: list of extracted date values."""
        return [m.value for m in self.matches if m.category == SignalCategory.DATE]

    @property
    def entities(self) -> list[str]:
        """Convenience: list of extracted entity values."""
        return [m.value for m in self.matches if m.category == SignalCategory.ENTITY]

    @property
    def quantities(self) -> list[str]:
        """Convenience: list of extracted quantity values."""
        return [m.value for m in self.matches if m.category == SignalCategory.QUANTITY]

    @property
    def assertive_phrases(self) -> list[str]:
        """Convenience: list of extracted assertive phrases."""
        return [m.value for m in self.matches if m.category == SignalCategory.ASSERTIVE]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_hash": self.text_hash,
            "total_signals": self.total_signals,
            "signals_by_category": self.signals_by_category,
            "has_speculative_content": self.has_speculative_content,
            "assertiveness_score": self.assertiveness_score,
            "dates": self.dates,
            "entities": self.entities,
            "quantities": self.quantities,
            "assertive_phrases": self.assertive_phrases,
            "matches": [m.to_dict() for m in self.matches],
        }


@dataclass
class ExtractionConfig:
    """Configuration for signal extraction."""

    enable_dates: bool = True
    enable_entities: bool = True
    enable_quantities: bool = True
    enable_assertive: bool = True
    context_chars: int = 40
    dedup_entities: bool = True


# =============================================================================
# Signal Extractor
# =============================================================================


@dataclass
class SignalExtractor:
    """Extracts implicit claim signals from text using regex patterns."""

    config: ExtractionConfig = field(default_factory=ExtractionConfig)

    def extract(self, text: str) -> ExtractionResult:
        """Extract all signals from text."""
        matches: list[SignalMatch] = []

        if self.config.enable_dates:
            matches.extend(self._extract_dates(text))
        if self.config.enable_entities:
            matches.extend(self._extract_entities(text))
        if self.config.enable_quantities:
            matches.extend(self._extract_quantities(text))
        if self.config.enable_assertive:
            matches.extend(self._extract_assertive(text))

        # Compute category counts
        signals_by_category: dict[str, int] = {}
        for cat in SignalCategory:
            count = sum(1 for m in matches if m.category == cat)
            signals_by_category[cat.value] = count

        # Assertiveness score: count of assertive matches × 0.2, capped at 1.0
        assertive_count = signals_by_category.get(SignalCategory.ASSERTIVE.value, 0)
        assertiveness_score = min(1.0, assertive_count * 0.2)

        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        return ExtractionResult(
            text_hash=text_hash,
            total_signals=len(matches),
            signals_by_category=signals_by_category,
            matches=matches,
            assertiveness_score=assertiveness_score,
        )

    def extract_from_lines(self, lines: list[str]) -> ExtractionResult:
        """Extract signals from a list of lines, tracking line numbers."""
        all_matches: list[SignalMatch] = []

        for line_idx, line in enumerate(lines):
            line_num = line_idx + 1  # 1-indexed
            line_matches: list[SignalMatch] = []

            if self.config.enable_dates:
                line_matches.extend(self._extract_dates(line))
            if self.config.enable_entities:
                line_matches.extend(self._extract_entities(line))
            if self.config.enable_quantities:
                line_matches.extend(self._extract_quantities(line))
            if self.config.enable_assertive:
                line_matches.extend(self._extract_assertive(line))

            for m in line_matches:
                m.line_number = line_num

            all_matches.extend(line_matches)

        # Compute category counts
        signals_by_category: dict[str, int] = {}
        for cat in SignalCategory:
            count = sum(1 for m in all_matches if m.category == cat)
            signals_by_category[cat.value] = count

        # Assertiveness score
        assertive_count = signals_by_category.get(SignalCategory.ASSERTIVE.value, 0)
        assertiveness_score = min(1.0, assertive_count * 0.2)

        full_text = "\n".join(lines)
        text_hash = hashlib.sha256(full_text.encode()).hexdigest()[:16]

        return ExtractionResult(
            text_hash=text_hash,
            total_signals=len(all_matches),
            signals_by_category=signals_by_category,
            matches=all_matches,
            assertiveness_score=assertiveness_score,
        )

    def scan_file(self, path: str | Path) -> ExtractionResult:
        """Read a file and extract signals from its contents."""
        file_path = Path(path)
        content = file_path.read_text(errors="ignore")
        lines = content.splitlines()
        return self.extract_from_lines(lines)

    # =========================================================================
    # Private extraction methods
    # =========================================================================

    def _extract_dates(self, text: str) -> list[SignalMatch]:
        """Extract year patterns (1800–2099)."""
        matches = []
        for m in DATE_PATTERN.finditer(text):
            matches.append(SignalMatch(
                category=SignalCategory.DATE,
                value=m.group(1),
                span=(m.start(), m.end()),
                context=self._context_around(text, m.start(), m.end()),
            ))
        return matches

    def _extract_entities(self, text: str) -> list[SignalMatch]:
        """Extract capitalized multi-word names."""
        matches = []
        seen: set[str] = set()

        for m in ENTITY_PATTERN.finditer(text):
            value = m.group(1)

            # Skip entities that start at the very beginning of the text
            # (likely just a sentence start, not a proper noun)
            if m.start() == 0:
                # Check if this is at a sentence boundary
                # Only skip if there's no prior context suggesting it's a real entity
                pass  # Still include — entity pattern already requires multi-word

            if self.config.dedup_entities:
                if value in seen:
                    continue
                seen.add(value)

            matches.append(SignalMatch(
                category=SignalCategory.ENTITY,
                value=value,
                span=(m.start(), m.end()),
                context=self._context_around(text, m.start(), m.end()),
            ))
        return matches

    def _extract_quantities(self, text: str) -> list[SignalMatch]:
        """Extract numbers with units."""
        matches = []
        for m in QUANTITY_PATTERN.finditer(text):
            value = m.group(0)
            matches.append(SignalMatch(
                category=SignalCategory.QUANTITY,
                value=value,
                span=(m.start(), m.end()),
                context=self._context_around(text, m.start(), m.end()),
            ))
        return matches

    def _extract_assertive(self, text: str) -> list[SignalMatch]:
        """Extract assertive/definitive language."""
        matches = []
        for m in ASSERTIVE_PATTERN.finditer(text):
            value = m.group(1)
            matches.append(SignalMatch(
                category=SignalCategory.ASSERTIVE,
                value=value,
                span=(m.start(), m.end()),
                context=self._context_around(text, m.start(), m.end()),
            ))
        return matches

    def _context_around(self, text: str, start: int, end: int) -> str:
        """Get surrounding context for a match."""
        ctx_start = max(0, start - self.config.context_chars)
        ctx_end = min(len(text), end + self.config.context_chars)
        snippet = text[ctx_start:ctx_end]
        # Add ellipsis indicators
        prefix = "..." if ctx_start > 0 else ""
        suffix = "..." if ctx_end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"


# =============================================================================
# Ledger Integration
# =============================================================================


def register_signals(
    ledger: "EpistemicLedger",
    result: ExtractionResult,
    source_agent_id: str | None = None,
    confidence: float = 0.2,
) -> list[str]:
    """
    Create ASSUMED claims from extraction result. Returns claim IDs.

    Creates low-confidence ASSUMED claims for each signal:
    - "Date asserted: {year}"
    - "Entity referenced: {name}"
    - "Quantity asserted: {number} {unit}"

    Does NOT create claims for assertive phrases (those affect the
    assertiveness_score but aren't standalone claims).
    """
    from .epistemic import EpistemicLedger, Provenance  # noqa: F811

    claim_ids: list[str] = []

    for match in result.matches:
        if match.category == SignalCategory.ASSERTIVE:
            continue  # Assertive phrases modify score, not standalone claims

        if match.category == SignalCategory.DATE:
            content = f"Date asserted: {match.value}"
        elif match.category == SignalCategory.ENTITY:
            content = f"Entity referenced: {match.value}"
        elif match.category == SignalCategory.QUANTITY:
            content = f"Quantity asserted: {match.value}"
        else:
            continue

        claim = ledger.new_claim(
            content=content,
            provenance=Provenance.ASSUMED,
            confidence=confidence,
            source_agent_id=source_agent_id,
        )
        claim_ids.append(claim.claim_id)

    return claim_ids


# =============================================================================
# Convenience Functions
# =============================================================================


def extract_signals(text: str) -> ExtractionResult:
    """One-liner extraction with default config."""
    return SignalExtractor().extract(text)


def scan_text(text: str) -> ExtractionResult:
    """Alias for extract_signals."""
    return extract_signals(text)


def has_implicit_claims(text: str) -> bool:
    """Quick check: does text contain any speculative content?"""
    return extract_signals(text).has_speculative_content


def assertiveness_score(text: str) -> float:
    """Quick assertiveness score computation."""
    return extract_signals(text).assertiveness_score
