"""
Governor adapters: thin wrappers connecting domain governors to the executor.

Phase A4: Governors remain dumb libraries. The executor speaks to them via
a narrow interface (Invariant). This module provides factory functions that
wrap governor verifiers as Invariant objects.

Design principles:
- No cross-imports between governor packages
- Each adapter is a factory function returning an Invariant
- Adapters read files from kwargs (files_touched, root) and run checks
- Governors don't know about the executor; executor doesn't know about governors
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .invariants import Invariant, InvariantType, InvariantResult


# =============================================================================
# Adapter result (shared by all adapters for diagnostics)
# =============================================================================


@dataclass
class AdapterFinding:
    """A finding from a governor adapter check."""

    source: str  # Which adapter produced this (e.g., "security", "cfi")
    file_path: str
    message: str
    severity: str = "error"  # "error" | "warning" | "info"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "file_path": self.file_path,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


# =============================================================================
# File reading helper
# =============================================================================


def _read_text_files(
    files: list[str],
    root: Path,
    extensions: set[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Read text content from files. Returns list of (relative_path, content).

    Skips binary files and files that can't be read.
    If extensions is provided, only reads files with those extensions.
    """
    results = []
    for f in files:
        if extensions:
            suffix = Path(f).suffix.lower()
            if suffix not in extensions:
                continue
        path = root / f
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            results.append((f, content))
        except (UnicodeDecodeError, OSError, PermissionError):
            continue
    return results


# Text file extensions for content analysis
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".r", ".sql", ".sh", ".bash", ".zsh",
    ".md", ".txt", ".rst", ".adoc", ".tex", ".html", ".css",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".env", ".dockerfile", ".makefile",
}

# Prose extensions for nonfiction/fiction checks
PROSE_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc", ".tex", ".html",
}


# =============================================================================
# Security adapter
# =============================================================================


def security_invariant(
    verifier: Any,
    min_severity: str = "high",
    invariant_id: str = "security_scan",
    on_violation: str = "block",
) -> Invariant:
    """
    Wrap a SecurityVerifier as an Invariant.

    Scans touched files for vulnerabilities. Blocks on findings at or above
    min_severity (critical > high > medium > low).

    Args:
        verifier: SecurityVerifier instance (from governor.security)
        min_severity: Minimum severity to treat as violation
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    threshold = severity_rank.get(min_severity.lower(), 3)

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])

        all_findings: list[AdapterFinding] = []
        for f in files:
            path = root / f
            if not path.exists() or not path.is_file():
                continue
            try:
                findings = verifier.scan_file(path)
            except Exception:
                continue
            for finding in findings:
                sev = finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity)
                rank = severity_rank.get(sev.lower(), 0)
                if rank >= threshold:
                    all_findings.append(AdapterFinding(
                        source="security",
                        file_path=f,
                        message=finding.message,
                        severity=sev,
                        details={
                            "vuln_type": finding.vuln_type.value if hasattr(finding.vuln_type, "value") else str(finding.vuln_type),
                            "line_number": finding.line_number,
                        },
                    ))

        if all_findings:
            return InvariantResult(
                passed=False,
                message=f"Security: {len(all_findings)} finding(s) at {min_severity}+ severity",
                invariant_id=invariant_id,
                details={"findings": [f.to_dict() for f in all_findings[:20]]},
            )
        return InvariantResult(
            passed=True,
            message="No security issues found",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.FORBIDDEN,
        rule=f"No security vulnerabilities at {min_severity}+ severity",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# CFI adapter (nonfiction frame intrusion)
# =============================================================================


def cfi_invariant(
    detector: Any,
    max_faults: int = 0,
    file_extensions: set[str] | None = None,
    invariant_id: str = "cfi_check",
    on_violation: str = "warn",
) -> Invariant:
    """
    Wrap a CFIDetector as an Invariant.

    Checks touched prose files for contextual frame intrusion. Default is
    warn-only (CFI v0 is advisory).

    Args:
        detector: CFIDetector instance (from nonfiction_governor.cfi)
        max_faults: Maximum tolerated faults before violation
        file_extensions: Which file extensions to scan (default: prose files)
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """
    exts = file_extensions or PROSE_EXTENSIONS

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])

        file_contents = _read_text_files(files, root, exts)
        all_faults: list[AdapterFinding] = []

        for rel_path, content in file_contents:
            try:
                result = detector.check(content)
            except Exception:
                continue
            for fault in result.faults:
                all_faults.append(AdapterFinding(
                    source="cfi",
                    file_path=rel_path,
                    message=fault.detail,
                    severity=fault.severity if hasattr(fault, "severity") else "warning",
                    details={
                        "fault_type": fault.fault_type.value if hasattr(fault.fault_type, "value") else str(fault.fault_type),
                        "frame": fault.frame.value if fault.frame and hasattr(fault.frame, "value") else None,
                    },
                ))

        if len(all_faults) > max_faults:
            return InvariantResult(
                passed=False,
                message=f"CFI: {len(all_faults)} fault(s) detected (max {max_faults})",
                invariant_id=invariant_id,
                details={"faults": [f.to_dict() for f in all_faults[:20]]},
            )
        return InvariantResult(
            passed=True,
            message=f"CFI: {len(all_faults)} fault(s), within tolerance",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.CONSISTENCY,
        rule=f"No more than {max_faults} contextual frame intrusion fault(s)",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Fiction adapter
# =============================================================================


def fiction_invariant(
    verifier: Any,
    characters: list[str] | None = None,
    file_extensions: set[str] | None = None,
    invariant_id: str = "fiction_check",
    on_violation: str = "block",
) -> Invariant:
    """
    Wrap a fiction CombinedVerifier as an Invariant.

    Runs quick_check on touched prose files against character/trope/tone rules.

    Args:
        verifier: CombinedVerifier instance (from fiction_governor.verifiers)
        characters: Character names to check against
        file_extensions: Which file extensions to scan (default: prose files)
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """
    exts = file_extensions or PROSE_EXTENSIONS

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])
        chars = characters or []

        file_contents = _read_text_files(files, root, exts)
        all_issues: list[str] = []

        for rel_path, content in file_contents:
            try:
                passed, issues = verifier.quick_check(content, chars)
            except Exception:
                continue
            if not passed:
                all_issues.extend(f"[{rel_path}] {issue}" for issue in issues)

        if all_issues:
            return InvariantResult(
                passed=False,
                message=f"Fiction: {len(all_issues)} issue(s) found",
                invariant_id=invariant_id,
                details={"issues": all_issues[:20]},
            )
        return InvariantResult(
            passed=True,
            message="Fiction checks passed",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.CONSISTENCY,
        rule="Fiction content must pass character, trope, and tone checks",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Nonfiction citation adapter
# =============================================================================


def nonfiction_citation_invariant(
    verifier: Any,
    invariant_id: str = "nonfiction_citations",
    on_violation: str = "warn",
) -> Invariant:
    """
    Wrap a CitationVerifier as an Invariant.

    Extracts citations from touched prose files and verifies each exists
    in the corpus.

    Args:
        verifier: CitationVerifier instance (from nonfiction_governor.verifiers)
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])

        file_contents = _read_text_files(files, root, PROSE_EXTENSIONS)
        bad_citations: list[AdapterFinding] = []

        for rel_path, content in file_contents:
            try:
                citation_keys = verifier.extract_citations(content)
            except Exception:
                continue
            for key in citation_keys:
                try:
                    result = verifier.verify_citation(key)
                except Exception:
                    continue
                if not result.valid:
                    bad_citations.append(AdapterFinding(
                        source="nonfiction_citation",
                        file_path=rel_path,
                        message=result.message,
                        severity="warning",
                        details={"citation_key": key},
                    ))

        if bad_citations:
            return InvariantResult(
                passed=False,
                message=f"Citations: {len(bad_citations)} invalid citation(s)",
                invariant_id=invariant_id,
                details={"findings": [f.to_dict() for f in bad_citations[:20]]},
            )
        return InvariantResult(
            passed=True,
            message="All citations valid",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.EVIDENCE,
        rule="All citations must reference valid corpus entries",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Tone adapter (nonfiction style enforcement)
# =============================================================================


def tone_invariant(
    checker: Any,
    file_extensions: set[str] | None = None,
    invariant_id: str = "tone_check",
    on_violation: str = "warn",
) -> Invariant:
    """
    Wrap a ToneChecker as an Invariant.

    Checks touched prose files against a locked tone profile. Violations
    include specific suggestions (e.g., "break up long sentences").

    Args:
        checker: ToneChecker instance (from nonfiction_governor.tone)
        file_extensions: Which file extensions to scan (default: prose files)
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """
    exts = file_extensions or PROSE_EXTENSIONS

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])

        file_contents = _read_text_files(files, root, exts)
        all_violations: list[AdapterFinding] = []

        for rel_path, content in file_contents:
            try:
                result = checker.check(content)
            except Exception:
                continue
            if not result.valid:
                for v in result.violations:
                    msg = v.message if hasattr(v, "message") else str(v)
                    suggestion = v.suggestion if hasattr(v, "suggestion") else ""
                    all_violations.append(AdapterFinding(
                        source="tone",
                        file_path=rel_path,
                        message=msg,
                        severity="warning",
                        details={
                            "dimension": v.dimension if hasattr(v, "dimension") else "",
                            "suggestion": suggestion,
                        },
                    ))

        if all_violations:
            suggestions = [
                v.details.get("suggestion", "")
                for v in all_violations if v.details.get("suggestion")
            ]
            msg = f"Tone: {len(all_violations)} violation(s)"
            if suggestions:
                msg += f" — {'; '.join(suggestions[:3])}"
            return InvariantResult(
                passed=False,
                message=msg,
                invariant_id=invariant_id,
                details={"violations": [v.to_dict() for v in all_violations[:20]]},
            )
        return InvariantResult(
            passed=True,
            message="Tone profile satisfied",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.CONSISTENCY,
        rule="Prose must match the locked tone profile",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Continuity adapter (anchor enforcement)
# =============================================================================


def continuity_invariant(
    registry: Any,
    checker: Any | None = None,
    min_severity: str = "correct",
    file_extensions: set[str] | None = None,
    invariant_id: str = "continuity_check",
    on_violation: str = "block",
) -> Invariant:
    """
    Wrap an AnchorRegistry + ContinuityChecker as an Invariant.

    One-shot gate (no retry — that's ConvergenceExecutor's job).
    Reads file contents, checks each against all anchors.
    Blocks on violations at or above min_severity.

    Args:
        registry: AnchorRegistry instance (from governor.continuity)
        checker: ContinuityChecker instance (default: creates one)
        min_severity: Minimum severity to treat as violation ("warn", "correct", "reject")
        file_extensions: Which file extensions to scan (default: text files)
        invariant_id: Invariant identifier
        on_violation: "block" or "warn"
    """
    severity_rank = {"reject": 3, "correct": 2, "warn": 1}
    threshold = severity_rank.get(min_severity.lower(), 2)
    exts = file_extensions or TEXT_EXTENSIONS

    def verify(**kwargs: Any) -> InvariantResult:
        from .continuity import ContinuityChecker, Severity

        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])
        chk = checker
        if chk is None:
            chk = ContinuityChecker()

        anchors = registry.all()
        if not anchors:
            return InvariantResult(
                passed=True,
                message="Continuity: no anchors registered",
                invariant_id=invariant_id,
            )

        file_contents = _read_text_files(files, root, exts)
        all_findings: list[AdapterFinding] = []

        for rel_path, content in file_contents:
            try:
                report = chk.check(content, anchors)
            except Exception:
                continue
            for v in report.violations:
                sev_val = v.severity.value if hasattr(v.severity, "value") else str(v.severity)
                rank = severity_rank.get(sev_val.lower(), 0)
                if rank >= threshold:
                    all_findings.append(AdapterFinding(
                        source="continuity",
                        file_path=rel_path,
                        message=v.description,
                        severity=sev_val,
                        details={
                            "anchor_id": v.anchor_id,
                            "anchor_type": v.anchor_type.value if hasattr(v.anchor_type, "value") else str(v.anchor_type),
                            "evidence": v.evidence,
                        },
                    ))

        if all_findings:
            return InvariantResult(
                passed=False,
                message=f"Continuity: {len(all_findings)} violation(s) at {min_severity}+ severity",
                invariant_id=invariant_id,
                details={"findings": [f.to_dict() for f in all_findings[:20]]},
            )
        return InvariantResult(
            passed=True,
            message="Continuity: all anchors satisfied",
            invariant_id=invariant_id,
        )

    return Invariant(
        id=invariant_id,
        type=InvariantType.CONSISTENCY,
        rule="Output must satisfy all registered continuity anchors",
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Generic content adapter
# =============================================================================


# Type for custom check functions: (content, file_path) → (passed, message)
ContentCheckFn = Callable[[str, str], tuple[bool, str]]


def content_invariant(
    check_fn: ContentCheckFn,
    name: str,
    rule: str,
    file_extensions: set[str] | None = None,
    invariant_type: InvariantType = InvariantType.CONSISTENCY,
    invariant_id: str | None = None,
    on_violation: str = "block",
) -> Invariant:
    """
    Create an Invariant from any content check function.

    The check function receives (content, relative_path) and returns
    (passed, message). This is the escape hatch for custom checks that
    don't fit the governor patterns.

    Args:
        check_fn: Function (content, path) → (passed, message)
        name: Human-readable name for the check
        rule: Rule description
        file_extensions: Which file extensions to scan
        invariant_type: InvariantType category
        invariant_id: Invariant identifier (default: derived from name)
        on_violation: "block" or "warn"
    """
    inv_id = invariant_id or f"content_{name.lower().replace(' ', '_')}"
    exts = file_extensions or TEXT_EXTENSIONS

    def verify(**kwargs: Any) -> InvariantResult:
        root = kwargs.get("root", Path("."))
        files = kwargs.get("files_touched", [])

        file_contents = _read_text_files(files, root, exts)
        failures: list[AdapterFinding] = []

        for rel_path, content in file_contents:
            try:
                passed, message = check_fn(content, rel_path)
            except Exception as e:
                failures.append(AdapterFinding(
                    source=name,
                    file_path=rel_path,
                    message=f"Check error: {e}",
                    severity="error",
                ))
                continue
            if not passed:
                failures.append(AdapterFinding(
                    source=name,
                    file_path=rel_path,
                    message=message,
                    severity="error",
                ))

        if failures:
            return InvariantResult(
                passed=False,
                message=f"{name}: {len(failures)} failure(s)",
                invariant_id=inv_id,
                details={"failures": [f.to_dict() for f in failures[:20]]},
            )
        return InvariantResult(
            passed=True,
            message=f"{name}: all checks passed",
            invariant_id=inv_id,
        )

    return Invariant(
        id=inv_id,
        type=invariant_type,
        rule=rule,
        verify=verify,
        on_violation=on_violation,
    )


# =============================================================================
# Adapter set builder
# =============================================================================


@dataclass
class AdapterConfig:
    """Configuration for building an adapter set."""

    security_verifier: Any | None = None
    security_min_severity: str = "high"

    cfi_detector: Any | None = None
    cfi_max_faults: int = 0

    fiction_verifier: Any | None = None
    fiction_characters: list[str] = field(default_factory=list)

    citation_verifier: Any | None = None

    tone_checker: Any | None = None

    continuity_registry: Any | None = None
    """AnchorRegistry instance (from governor.continuity)."""

    continuity_checker: Any | None = None
    """ContinuityChecker instance (from governor.continuity). Uses default if None."""

    custom_checks: list[tuple[ContentCheckFn, str, str]] = field(default_factory=list)
    """List of (check_fn, name, rule) tuples."""


def build_adapter_set(config: AdapterConfig) -> list[Invariant]:
    """
    Build a list of Invariant objects from an AdapterConfig.

    Only creates adapters for verifiers that are provided (non-None).
    Returns a list suitable for adding to an InvariantSet.

    Example:
        config = AdapterConfig(
            security_verifier=SecurityVerifier(),
            cfi_detector=CFIDetector(),
        )
        invariants = build_adapter_set(config)
        inv_set = InvariantSet()
        for inv in invariants:
            inv_set.add(inv)
    """
    result: list[Invariant] = []

    if config.security_verifier is not None:
        result.append(security_invariant(
            verifier=config.security_verifier,
            min_severity=config.security_min_severity,
        ))

    if config.cfi_detector is not None:
        result.append(cfi_invariant(
            detector=config.cfi_detector,
            max_faults=config.cfi_max_faults,
        ))

    if config.fiction_verifier is not None:
        result.append(fiction_invariant(
            verifier=config.fiction_verifier,
            characters=config.fiction_characters,
        ))

    if config.citation_verifier is not None:
        result.append(nonfiction_citation_invariant(
            verifier=config.citation_verifier,
        ))

    if config.tone_checker is not None:
        result.append(tone_invariant(
            checker=config.tone_checker,
        ))

    if config.continuity_registry is not None:
        result.append(continuity_invariant(
            registry=config.continuity_registry,
            checker=config.continuity_checker,
        ))

    for check_fn, name, rule in config.custom_checks:
        result.append(content_invariant(
            check_fn=check_fn,
            name=name,
            rule=rule,
        ))

    return result
