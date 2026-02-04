"""
Chrono check: temporal grounding for AI-generated content.

Catches common year/date hallucinations where the model's training cutoff
causes it to use stale years (e.g., writing "2025" when it's actually 2026).

Usage:
    from governor.chrono import check_chrono, ChronoFinding

    findings = check_chrono("Copyright 2025 James Beck", current_year=2026)
    # Returns findings for suspicious dates
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ChronoSeverity(Enum):
    """Severity of chrono findings."""
    INFO = "info"        # Plausible but worth noting
    WARN = "warn"        # Likely error (past year in current context)
    ERROR = "error"      # Almost certainly wrong (far future/past)


@dataclass
class ChronoFinding:
    """A temporal anomaly found in text."""
    year: int
    context: str          # Surrounding text snippet
    reason: str           # Why it's flagged
    severity: ChronoSeverity
    position: int         # Character offset in original text

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "context": self.context,
            "reason": self.reason,
            "severity": self.severity.value,
            "position": self.position,
        }


# Patterns that suggest a year should be current (not historical)
# Be conservative - only flag things that clearly should be current
CURRENT_YEAR_PATTERNS = [
    r"copyright\s+\d{4}",
    r"©\s*\d{4}",
    r"as\s+of\s+\d{4}",
    r"updated?\s+\d{4}",
    r"dated?\s+\d{4}",
    r"version\s+.*\d{4}",
    r"current.*\d{4}",
    r"\d{4}-\d{2}-\d{2}",  # ISO dates (timestamps are usually current)
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}",
]

# Compiled patterns for efficiency
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_CURRENT_CONTEXT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CURRENT_YEAR_PATTERNS]


def get_current_year() -> int:
    """Get the current year from system time."""
    return datetime.now(timezone.utc).year


def check_chrono(
    text: str,
    current_year: int | None = None,
    max_future_years: int = 2,
    check_context: bool = True,
) -> list[ChronoFinding]:
    """
    Check text for temporal anomalies.

    Args:
        text: The text to check
        current_year: Override current year (defaults to system time)
        max_future_years: How far in the future is plausible
        check_context: Whether to use context patterns for severity

    Returns:
        List of ChronoFinding for any suspicious dates
    """
    if current_year is None:
        current_year = get_current_year()

    findings: list[ChronoFinding] = []

    for match in _YEAR_PATTERN.finditer(text):
        year = int(match.group())
        pos = match.start()

        # Get surrounding context (up to 40 chars each side)
        start = max(0, pos - 40)
        end = min(len(text), pos + 44)  # 4 digit year + 40
        context = text[start:end].strip()

        # Check if this looks like it should be current year
        in_current_context = False
        if check_context:
            # Check a wider window for context patterns
            context_start = max(0, pos - 20)
            context_end = min(len(text), pos + 24)
            context_window = text[context_start:context_end].lower()
            for pattern in _CURRENT_CONTEXT_PATTERNS:
                if pattern.search(context_window):
                    in_current_context = True
                    break

        # Evaluate the year
        if year > current_year + max_future_years:
            # Far future - almost certainly wrong
            findings.append(ChronoFinding(
                year=year,
                context=context,
                reason=f"Year {year} is {year - current_year} years in the future",
                severity=ChronoSeverity.ERROR,
                position=pos,
            ))
        elif year < current_year - 1 and in_current_context:
            # Past year in context that suggests current - likely stale
            findings.append(ChronoFinding(
                year=year,
                context=context,
                reason=f"Year {year} appears stale (current: {current_year})",
                severity=ChronoSeverity.WARN,
                position=pos,
            ))
        elif year == current_year - 1 and in_current_context:
            # Off by one in current context - the classic training cutoff error
            findings.append(ChronoFinding(
                year=year,
                context=context,
                reason=f"Year {year} may be off-by-one (current: {current_year})",
                severity=ChronoSeverity.WARN,
                position=pos,
            ))

    return findings


def check_chrono_strict(text: str, current_year: int | None = None) -> tuple[bool, list[ChronoFinding]]:
    """
    Strict chrono check - returns (passed, findings).

    Fails if any WARN or ERROR findings.
    """
    findings = check_chrono(text, current_year)
    severe = [f for f in findings if f.severity in (ChronoSeverity.WARN, ChronoSeverity.ERROR)]
    return (len(severe) == 0, findings)


# Invariant integration
def chrono_invariant_check(text: str) -> tuple[bool, str]:
    """
    Check for chrono invariant integration.

    Returns (passed, message) tuple compatible with invariant system.
    """
    passed, findings = check_chrono_strict(text)
    if passed:
        return True, "No temporal anomalies detected"

    messages = [f.reason for f in findings if f.severity in (ChronoSeverity.WARN, ChronoSeverity.ERROR)]
    return False, "; ".join(messages)
