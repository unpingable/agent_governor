# SPDX-License-Identifier: Apache-2.0
"""
Identity check: name grounding for AI-generated content.

Catches hallucinated or incomplete names by comparing against configured
canonical identities. Useful for author names, org names, etc.

Usage:
    from governor.identity import check_identity, IdentityFinding

    config = IdentityConfig(authors=["James Beck"], organizations=["Unpingable"])
    findings = check_identity("Copyright 2026 James", config)
    # Returns finding for incomplete name
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class IdentitySeverity(Enum):
    """Severity of identity findings."""
    INFO = "info"        # Slight variation, might be intentional
    WARN = "warn"        # Likely error (incomplete or altered name)
    ERROR = "error"      # Clearly wrong (unknown name in author context)


class IdentityMatchType(Enum):
    """Type of identity match/mismatch."""
    EXACT = "exact"              # Perfect match
    INCOMPLETE = "incomplete"    # First name only, missing parts
    PARTIAL = "partial"          # Some overlap but not exact
    UNKNOWN = "unknown"          # No match to any configured identity


@dataclass
class IdentityFinding:
    """A name anomaly found in text."""
    found_name: str
    expected_names: list[str]
    context: str
    reason: str
    severity: IdentitySeverity
    match_type: IdentityMatchType
    position: int

    def to_dict(self) -> dict:
        return {
            "found_name": self.found_name,
            "expected_names": self.expected_names,
            "context": self.context,
            "reason": self.reason,
            "severity": self.severity.value,
            "match_type": self.match_type.value,
            "position": self.position,
        }


@dataclass
class IdentityConfig:
    """Configuration for identity checking."""
    authors: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)  # canonical -> [aliases]

    def to_dict(self) -> dict:
        return {
            "authors": self.authors,
            "organizations": self.organizations,
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IdentityConfig":
        return cls(
            authors=data.get("authors", []),
            organizations=data.get("organizations", []),
            aliases=data.get("aliases", {}),
        )

    def all_author_variants(self) -> dict[str, str]:
        """Return mapping of all valid variants -> canonical name."""
        variants: dict[str, str] = {}
        for author in self.authors:
            variants[author.lower()] = author
            # Add aliases
            for alias in self.aliases.get(author, []):
                variants[alias.lower()] = author
        return variants

    def all_org_variants(self) -> dict[str, str]:
        """Return mapping of all valid org variants -> canonical name."""
        variants: dict[str, str] = {}
        for org in self.organizations:
            variants[org.lower()] = org
            for alias in self.aliases.get(org, []):
                variants[alias.lower()] = org
        return variants


# Patterns that indicate author context
# These capture names that may be single or multiple words (no newlines)
# Use [A-Z][a-z]+ for capitalized words, space only (not \s) between words
AUTHOR_PATTERNS = [
    (r"[Cc]opyright\s+(?:\d{4}\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "copyright"),
    (r"©\s*(?:\d{4}\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "copyright"),
    (r"[Aa]uthor[s]?[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "author"),
    (r"[Ww]ritten by ([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "written_by"),
    (r"[Cc]reated by ([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "created_by"),
    (r"[Mm]aintained by ([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "maintained_by"),
    (r"[Cc]o-[Aa]uthored-[Bb]y[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "co_authored"),
]

# Patterns for organization context (single word orgs like "Unpingable" should match)
ORG_PATTERNS = [
    (r"[Cc]opyright\s+(?:\d{4}\s+)?([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*(?: (?:Inc|LLC|Ltd|Corp|Foundation)\.?)?)\b", "copyright"),
    (r"©\s*(?:\d{4}\s+)?([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*(?: (?:Inc|LLC|Ltd|Corp|Foundation)\.?)?)\b", "copyright"),
]

_AUTHOR_COMPILED = [(re.compile(p), ctx) for p, ctx in AUTHOR_PATTERNS]
_ORG_COMPILED = [(re.compile(p), ctx) for p, ctx in ORG_PATTERNS]


def _normalize(name: str) -> str:
    """Normalize a name for comparison."""
    return " ".join(name.lower().split())


def _is_incomplete(found: str, canonical: str) -> bool:
    """Check if found is an incomplete version of canonical."""
    found_parts = found.lower().split()
    canonical_parts = canonical.lower().split()

    if len(found_parts) >= len(canonical_parts):
        return False

    # Check if found parts are a prefix of canonical
    for i, part in enumerate(found_parts):
        if i >= len(canonical_parts) or part != canonical_parts[i]:
            return False
    return True


def _is_partial_match(found: str, canonical: str) -> bool:
    """Check if there's partial overlap between found and canonical."""
    found_parts = set(found.lower().split())
    canonical_parts = set(canonical.lower().split())
    overlap = found_parts & canonical_parts
    return len(overlap) > 0 and overlap != found_parts


def _classify_match(found: str, config: IdentityConfig, is_org: bool = False) -> tuple[IdentityMatchType, str | None]:
    """Classify how well a found name matches configured identities."""
    variants = config.all_org_variants() if is_org else config.all_author_variants()
    canonical_list = config.organizations if is_org else config.authors

    found_norm = _normalize(found)

    # Exact match (including aliases)
    if found_norm in variants:
        return IdentityMatchType.EXACT, variants[found_norm]

    # Check for incomplete matches
    for canonical in canonical_list:
        if _is_incomplete(found, canonical):
            return IdentityMatchType.INCOMPLETE, canonical

    # Check for partial matches
    for canonical in canonical_list:
        if _is_partial_match(found, canonical):
            return IdentityMatchType.PARTIAL, canonical

    return IdentityMatchType.UNKNOWN, None


def check_identity(
    text: str,
    config: IdentityConfig,
    check_authors: bool = True,
    check_orgs: bool = True,
) -> list[IdentityFinding]:
    """
    Check text for identity anomalies.

    Args:
        text: The text to check
        config: Identity configuration with canonical names
        check_authors: Whether to check author names
        check_orgs: Whether to check organization names

    Returns:
        List of IdentityFinding for any suspicious names
    """
    findings: list[IdentityFinding] = []
    seen_positions: set[int] = set()  # Deduplicate by position

    if check_authors and config.authors:
        for pattern, ctx in _AUTHOR_COMPILED:
            for match in pattern.finditer(text):
                found_name = match.group(1)
                pos = match.start(1)

                match_type, canonical = _classify_match(found_name, config, is_org=False)

                if match_type == IdentityMatchType.EXACT:
                    continue  # All good

                # Deduplicate by position
                if pos in seen_positions:
                    continue
                seen_positions.add(pos)

                # Get context
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end].strip()

                if match_type == IdentityMatchType.INCOMPLETE:
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.authors,
                        context=context,
                        reason=f"Incomplete name '{found_name}' (expected '{canonical}')",
                        severity=IdentitySeverity.WARN,
                        match_type=match_type,
                        position=pos,
                    ))
                elif match_type == IdentityMatchType.PARTIAL:
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.authors,
                        context=context,
                        reason=f"Partial match '{found_name}' (similar to '{canonical}')",
                        severity=IdentitySeverity.WARN,
                        match_type=match_type,
                        position=pos,
                    ))
                else:  # UNKNOWN
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.authors,
                        context=context,
                        reason=f"Unknown name '{found_name}' in {ctx} context",
                        severity=IdentitySeverity.ERROR,
                        match_type=match_type,
                        position=pos,
                    ))

    if check_orgs and config.organizations:
        for pattern, ctx in _ORG_COMPILED:
            for match in pattern.finditer(text):
                found_name = match.group(1)
                pos = match.start(1)

                match_type, canonical = _classify_match(found_name, config, is_org=True)

                if match_type == IdentityMatchType.EXACT:
                    continue

                # Deduplicate by position
                if pos in seen_positions:
                    continue
                seen_positions.add(pos)

                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end].strip()

                if match_type == IdentityMatchType.INCOMPLETE:
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.organizations,
                        context=context,
                        reason=f"Incomplete org name '{found_name}' (expected '{canonical}')",
                        severity=IdentitySeverity.WARN,
                        match_type=match_type,
                        position=pos,
                    ))
                elif match_type == IdentityMatchType.PARTIAL:
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.organizations,
                        context=context,
                        reason=f"Partial org match '{found_name}' (similar to '{canonical}')",
                        severity=IdentitySeverity.WARN,
                        match_type=match_type,
                        position=pos,
                    ))
                else:
                    findings.append(IdentityFinding(
                        found_name=found_name,
                        expected_names=config.organizations,
                        context=context,
                        reason=f"Unknown org '{found_name}' in {ctx} context",
                        severity=IdentitySeverity.ERROR,
                        match_type=match_type,
                        position=pos,
                    ))

    return findings


def check_identity_strict(text: str, config: IdentityConfig) -> tuple[bool, list[IdentityFinding]]:
    """
    Strict identity check - returns (passed, findings).

    Fails if any WARN or ERROR findings.
    """
    findings = check_identity(text, config)
    severe = [f for f in findings if f.severity in (IdentitySeverity.WARN, IdentitySeverity.ERROR)]
    return (len(severe) == 0, findings)


def load_identity_config(gov_dir: Path) -> IdentityConfig:
    """Load identity config from .governor/config.toml."""
    config_path = gov_dir / "config.toml"
    if not config_path.exists():
        return IdentityConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    identity_data = data.get("identity", {})
    return IdentityConfig.from_dict(identity_data)


def identity_invariant_check(text: str, gov_dir: Path | None = None) -> tuple[bool, str]:
    """
    Check for identity invariant integration.

    Returns (passed, message) tuple compatible with invariant system.
    """
    if gov_dir is None:
        gov_dir = Path(".governor")

    config = load_identity_config(gov_dir)

    if not config.authors and not config.organizations:
        return True, "No identities configured"

    passed, findings = check_identity_strict(text, config)
    if passed:
        return True, "All identities match configured names"

    messages = [f.reason for f in findings if f.severity in (IdentitySeverity.WARN, IdentitySeverity.ERROR)]
    return False, "; ".join(messages)
