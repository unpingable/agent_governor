"""
Unified check aggregation for VS Code extension integration.

Aggregates findings from SecurityVerifier and ContinuityChecker into a single
JSON-serializable format suitable for editor diagnostics. All line/character
positions are 0-based to match the LSP/VS Code convention.

Usage:
    from governor.check import run_check
    result = run_check(content, "path/to/file.py")
    print(result.to_dict())
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class Position:
    """0-based line and character offset."""

    line: int
    character: int

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass
class Range:
    """Start/end positions for a finding."""

    start: Position
    end: Position

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class CheckFinding:
    """A single finding from security or continuity checking."""

    code: str
    message: str
    severity: str  # "error", "warning", "info"
    source: str  # "security", "continuity"
    range: Range
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "source": self.source,
            "range": self.range.to_dict(),
        }
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class CheckResult:
    """Aggregated result of all checks on a piece of content."""

    status: str  # "pass", "warn", "error"
    findings: list[CheckFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }


# =============================================================================
# Conversion: SecurityFinding -> CheckFinding
# =============================================================================

# security.Severity -> check severity
_SECURITY_SEVERITY_MAP = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "info",
}


def security_finding_to_check(finding: Any) -> CheckFinding:
    """Convert a SecurityFinding to a CheckFinding.

    SecurityFinding uses 1-based line_number; CheckFinding uses 0-based.
    """
    line_0 = max(finding.line_number - 1, 0)
    end_char = len(finding.line_content) if finding.line_content else 0
    code = f"SECURITY.{finding.vuln_type.value.upper()}"
    severity = _SECURITY_SEVERITY_MAP.get(finding.severity.value, "info")

    return CheckFinding(
        code=code,
        message=finding.message,
        severity=severity,
        source="security",
        range=Range(
            start=Position(line=line_0, character=0),
            end=Position(line=line_0, character=end_char),
        ),
        suggestion=finding.suggestion,
    )


# =============================================================================
# Conversion: Violation -> CheckFinding
# =============================================================================

# continuity.Severity -> check severity
_CONTINUITY_SEVERITY_MAP = {
    "reject": "error",
    "correct": "warning",
    "warn": "info",
}


def _locate_pattern_in_text(text: str, pattern: str) -> tuple[int, int, int] | None:
    """Find a pattern in text, return (line_0, start_char, end_char) or None."""
    flags = re.IGNORECASE
    escaped = re.escape(pattern)
    match = re.search(escaped, text, flags)
    if match is None:
        return None
    # Count newlines before match start to find line number
    before = text[: match.start()]
    line_0 = before.count("\n")
    # Character offset within that line
    last_nl = before.rfind("\n")
    start_char = match.start() - (last_nl + 1) if last_nl >= 0 else match.start()
    end_char = start_char + (match.end() - match.start())
    return (line_0, start_char, end_char)


def continuity_violation_to_check(violation: Any, text: str) -> CheckFinding:
    """Convert a continuity Violation to a CheckFinding.

    Attempts to locate the violation in the text using evidence strings.
    Falls back to line 0 if the pattern cannot be found.
    """
    code = f"CONTINUITY.{violation.anchor_type.value.upper()}.{violation.anchor_id}"
    severity = _CONTINUITY_SEVERITY_MAP.get(violation.severity.value, "info")

    # Try to locate the violation in text using evidence
    located = None
    for ev in violation.evidence:
        # Evidence strings often look like "Pattern 'X' matched in output"
        # or "Concept 'X' matched in output"
        m = re.search(r"(?:Pattern|Concept)\s+'([^']+)'", ev)
        if m:
            located = _locate_pattern_in_text(text, m.group(1))
            if located is not None:
                break
        # Also try to locate the forbidden pattern directly
        for word in ev.split("'"):
            if len(word) >= 3 and word not in ("Pattern", "Concept", " matched in output"):
                located = _locate_pattern_in_text(text, word)
                if located is not None:
                    break
        if located is not None:
            break

    if located is not None:
        line_0, start_char, end_char = located
    else:
        line_0, start_char, end_char = 0, 0, 0

    return CheckFinding(
        code=code,
        message=violation.description,
        severity=severity,
        source="continuity",
        range=Range(
            start=Position(line=line_0, character=start_char),
            end=Position(line=line_0, character=end_char),
        ),
    )


# =============================================================================
# Orchestration
# =============================================================================


def run_check(
    content: str,
    file_path: str = "<unknown>",
    *,
    run_security: bool = True,
    run_continuity: bool = True,
    governor_dir: Path | None = None,
) -> CheckResult:
    """Run security and/or continuity checks, return aggregated result.

    Works without a .governor/ directory (security-only, continuity skipped
    gracefully if no anchors are registered).
    """
    findings: list[CheckFinding] = []

    # Security scan
    if run_security:
        from .security import SecurityVerifier

        verifier = SecurityVerifier()
        for sf in verifier.scan_content(content, file_path):
            findings.append(security_finding_to_check(sf))

    # Continuity check
    if run_continuity:
        from .continuity import AnchorRegistry, ContinuityChecker

        registry = AnchorRegistry()
        if governor_dir is not None:
            anchors_path = governor_dir / "continuity" / "anchors.json"
            if anchors_path.exists():
                registry = AnchorRegistry.load(anchors_path)

        anchors = registry.all()
        if anchors:
            checker = ContinuityChecker()
            report = checker.check(content, anchors)
            for v in report.violations:
                findings.append(continuity_violation_to_check(v, content))

    # Compute status
    has_error = any(f.severity == "error" for f in findings)
    has_warning = any(f.severity == "warning" for f in findings)
    if has_error:
        status = "error"
    elif has_warning:
        status = "warn"
    else:
        status = "pass"

    # Summary
    if not findings:
        summary = "No issues found."
    else:
        error_count = sum(1 for f in findings if f.severity == "error")
        warn_count = sum(1 for f in findings if f.severity == "warning")
        info_count = sum(1 for f in findings if f.severity == "info")
        parts = []
        if error_count:
            parts.append(f"{error_count} error(s)")
        if warn_count:
            parts.append(f"{warn_count} warning(s)")
        if info_count:
            parts.append(f"{info_count} info")
        summary = f"Found {len(findings)} issue(s): {', '.join(parts)}."

    return CheckResult(status=status, findings=findings, summary=summary)
