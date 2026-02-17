# SPDX-License-Identifier: Apache-2.0
"""
Code Interferometry — code-specific divergence analysis.

Builds on top of interferometry.py. Takes an InterferometryRun and produces
a CodeDivergenceReport with risk markers, anchor conflicts, and tier
determination.

Core rule: **Interferometry is instrumentation, not selection.**
Any "winner" UX language is forbidden.

Tier 0: invisible background (deferred)
Tier 1: auto-triggered warnings (divergence_entropy, risk markers, conflicts)
Tier 2: explicit compare (user-initiated)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .check import CheckFinding, Position, Range
from .continuity import Anchor, AnchorRegistry, ConstraintClass, ContinuityChecker
from .interferometry import InterferometryRun, ModelRun
from .security import SecurityVerifier, VulnerabilityType


# ============================================================================
# Enums
# ============================================================================


class RiskCategory(str, Enum):
    SECURITY = "security"
    EDGE_CASE = "edge_case"
    ARCHITECTURAL = "architectural"


class RiskMarkerType(str, Enum):
    # Security (8)
    SQL_INJECTION = "sql_injection"
    SHELL_EXEC = "shell_exec"
    UNSAFE_DESER = "unsafe_deser"
    AUTH_BYPASS = "auth_bypass"
    INPUT_UNSANITIZED = "input_unsanitized"
    CRYPTO_MISUSE = "crypto_misuse"
    SSRF_CANDIDATE = "ssrf_candidate"
    PATH_TRAVERSAL = "path_traversal"
    # Edge-Case (6)
    NULL_UNHANDLED = "null_unhandled"
    PARTIAL_ERROR = "partial_error"
    BOUNDARY = "boundary"
    CONCURRENCY = "concurrency"
    TIMEOUT_MISSING = "timeout_missing"
    RESOURCE_LEAK = "resource_leak"
    # Architectural (5)
    ANCHOR_VIOLATION = "anchor_violation"
    INTERFACE_BREAK = "interface_break"
    NEW_COUPLING = "new_coupling"
    PATTERN_BYPASS = "pattern_bypass"
    DECISION_CONFLICT = "decision_conflict"


MARKER_CATEGORIES: dict[RiskMarkerType, RiskCategory] = {
    # Security
    RiskMarkerType.SQL_INJECTION: RiskCategory.SECURITY,
    RiskMarkerType.SHELL_EXEC: RiskCategory.SECURITY,
    RiskMarkerType.UNSAFE_DESER: RiskCategory.SECURITY,
    RiskMarkerType.AUTH_BYPASS: RiskCategory.SECURITY,
    RiskMarkerType.INPUT_UNSANITIZED: RiskCategory.SECURITY,
    RiskMarkerType.CRYPTO_MISUSE: RiskCategory.SECURITY,
    RiskMarkerType.SSRF_CANDIDATE: RiskCategory.SECURITY,
    RiskMarkerType.PATH_TRAVERSAL: RiskCategory.SECURITY,
    # Edge-Case
    RiskMarkerType.NULL_UNHANDLED: RiskCategory.EDGE_CASE,
    RiskMarkerType.PARTIAL_ERROR: RiskCategory.EDGE_CASE,
    RiskMarkerType.BOUNDARY: RiskCategory.EDGE_CASE,
    RiskMarkerType.CONCURRENCY: RiskCategory.EDGE_CASE,
    RiskMarkerType.TIMEOUT_MISSING: RiskCategory.EDGE_CASE,
    RiskMarkerType.RESOURCE_LEAK: RiskCategory.EDGE_CASE,
    # Architectural
    RiskMarkerType.ANCHOR_VIOLATION: RiskCategory.ARCHITECTURAL,
    RiskMarkerType.INTERFACE_BREAK: RiskCategory.ARCHITECTURAL,
    RiskMarkerType.NEW_COUPLING: RiskCategory.ARCHITECTURAL,
    RiskMarkerType.PATTERN_BYPASS: RiskCategory.ARCHITECTURAL,
    RiskMarkerType.DECISION_CONFLICT: RiskCategory.ARCHITECTURAL,
}


class AnchorConflictType(str, Enum):
    HARD = "hard"
    SOFT = "soft"


# ============================================================================
# Mapping constants
# ============================================================================

# Map SecurityVerifier vuln_type strings → RiskMarkerType
_SECURITY_TO_MARKER: dict[str, RiskMarkerType] = {
    VulnerabilityType.SQL_INJECTION.value: RiskMarkerType.SQL_INJECTION,
    VulnerabilityType.COMMAND_INJECTION.value: RiskMarkerType.SHELL_EXEC,
    VulnerabilityType.INSECURE_DESERIALIZATION.value: RiskMarkerType.UNSAFE_DESER,
    VulnerabilityType.XSS.value: RiskMarkerType.INPUT_UNSANITIZED,
    VulnerabilityType.PATH_TRAVERSAL.value: RiskMarkerType.PATH_TRAVERSAL,
    VulnerabilityType.INSECURE_HASH.value: RiskMarkerType.CRYPTO_MISUSE,
    VulnerabilityType.INSECURE_RANDOM.value: RiskMarkerType.CRYPTO_MISUSE,
    VulnerabilityType.SECRET_LEAK.value: RiskMarkerType.AUTH_BYPASS,
    VulnerabilityType.HARDCODED_CREDENTIAL.value: RiskMarkerType.AUTH_BYPASS,
}

# Regex patterns for edge-case detection
_EDGE_CASE_PATTERNS: list[tuple[re.Pattern[str], RiskMarkerType, str]] = [
    # Null handling
    (re.compile(r'(?:is\s+None|==\s*None|is\s+null|==\s*null|\.get\(|\.or_default|Optional)', re.IGNORECASE),
     RiskMarkerType.NULL_UNHANDLED,
     "Null/None handling pattern detected"),
    # Broad exception catches
    (re.compile(r'except\s*(?:Exception|BaseException|\w*Error)?\s*(?:as\s+\w+)?\s*:\s*\n\s*(?:pass|\.\.\.)', re.MULTILINE),
     RiskMarkerType.PARTIAL_ERROR,
     "Broad exception catch that silences errors"),
    # Boundary conditions
    (re.compile(r'(?:len\s*\(\s*\w+\s*\)\s*[-+]\s*1|range\s*\(\s*\d+\s*,\s*len|index\s*[-+]\s*1|\[\s*-1\s*\])'),
     RiskMarkerType.BOUNDARY,
     "Boundary/off-by-one pattern"),
    # Concurrency
    (re.compile(r'(?:threading\.|asyncio\.|Lock\(\)|async\s+def|await\s|\.acquire\(\)|\.release\(\))'),
     RiskMarkerType.CONCURRENCY,
     "Concurrency pattern"),
    # Timeout missing
    (re.compile(r'(?:requests\.(?:get|post|put|delete|patch)\s*\([^)]*\)|urlopen\s*\(|socket\.\w+\s*\()(?!.*timeout)'),
     RiskMarkerType.TIMEOUT_MISSING,
     "Network call without explicit timeout"),
    # Resource lifecycle
    (re.compile(r'(?:open\s*\(|connect\s*\(|cursor\s*\(|socket\.\w+\s*\()(?!.*\bwith\b)'),
     RiskMarkerType.RESOURCE_LEAK,
     "Resource opened without context manager"),
]


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class RiskMarker:
    """A risk marker found in code output from a model."""

    marker_type: RiskMarkerType
    category: RiskCategory
    model_id: str
    file_path: str
    line_number: int
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "marker_type": self.marker_type.value,
            "category": self.category.value,
            "model_id": self.model_id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
        }
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class AnchorConflict:
    """A conflict between model output and an anchor constraint."""

    anchor_id: str
    conflict_type: AnchorConflictType
    model_id: str
    description: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "conflict_type": self.conflict_type.value,
            "model_id": self.model_id,
            "description": self.description,
            "evidence": self.evidence,
        }


@dataclass
class CodeArtifact:
    """Structured code output from a single model."""

    model_id: str
    files: list[dict[str, str]] = field(default_factory=list)
    build_intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "files": self.files,
            "build_intent": self.build_intent,
        }


@dataclass
class CodeDivergenceReport:
    """Complete code-specific divergence analysis result."""

    interferometry_run_id: str
    artifacts: list[CodeArtifact] = field(default_factory=list)
    risk_markers: list[RiskMarker] = field(default_factory=list)
    anchor_conflicts: list[AnchorConflict] = field(default_factory=list)
    divergence_entropy: float = 0.0
    risk_marker_union: list[RiskMarker] = field(default_factory=list)
    risk_marker_unique: dict[str, list[RiskMarker]] = field(default_factory=dict)
    tier: int = 0
    tier_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interferometry_run_id": self.interferometry_run_id,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "risk_markers": [m.to_dict() for m in self.risk_markers],
            "anchor_conflicts": [c.to_dict() for c in self.anchor_conflicts],
            "divergence_entropy": round(self.divergence_entropy, 4),
            "risk_marker_union": [m.to_dict() for m in self.risk_marker_union],
            "risk_marker_unique": {
                k: [m.to_dict() for m in v]
                for k, v in self.risk_marker_unique.items()
            },
            "tier": self.tier,
            "tier_reasons": self.tier_reasons,
        }

    def has_security_markers(self) -> bool:
        return any(
            m.category == RiskCategory.SECURITY for m in self.risk_markers
        )

    def has_hard_conflicts(self) -> bool:
        return any(
            c.conflict_type == AnchorConflictType.HARD
            for c in self.anchor_conflicts
        )


@dataclass
class CodeInterferometryConfig:
    """Configuration for code interferometry analysis."""

    divergence_threshold: float = 0.3
    risk_markers_trigger: bool = True
    anchor_conflicts_trigger: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_threshold": self.divergence_threshold,
            "risk_markers_trigger": self.risk_markers_trigger,
            "anchor_conflicts_trigger": self.anchor_conflicts_trigger,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodeInterferometryConfig:
        return cls(
            divergence_threshold=data.get("divergence_threshold", 0.3),
            risk_markers_trigger=data.get("risk_markers_trigger", True),
            anchor_conflicts_trigger=data.get("anchor_conflicts_trigger", True),
        )


# ============================================================================
# Functions
# ============================================================================


_CODE_BLOCK_RE = re.compile(
    r'```(\w*)\n(.*?)```',
    re.DOTALL,
)


def extract_code_blocks(response: str) -> list[dict[str, Any]]:
    """Extract fenced code blocks from a model response.

    Returns list of {language, content, start_line}.
    """
    blocks: list[dict[str, Any]] = []
    for match in _CODE_BLOCK_RE.finditer(response):
        language = match.group(1) or "unknown"
        content = match.group(2)
        # Calculate start line (0-based line in the response)
        start_line = response[:match.start()].count('\n')
        blocks.append({
            "language": language,
            "content": content,
            "start_line": start_line,
        })
    return blocks


def extract_risk_markers(
    code: str,
    file_path: str = "<model_output>",
    model_id: str = "",
) -> list[RiskMarker]:
    """Extract risk markers from code using SecurityVerifier + edge-case patterns.

    Reuses SecurityVerifier.scan_content() for security markers.
    Uses regex patterns for edge-case markers.
    """
    markers: list[RiskMarker] = []

    # Security markers via SecurityVerifier
    verifier = SecurityVerifier()
    findings = verifier.scan_content(code, file_path=file_path)
    for finding in findings:
        vuln_key = finding.vuln_type.value
        marker_type = _SECURITY_TO_MARKER.get(vuln_key)
        if marker_type is not None:
            markers.append(RiskMarker(
                marker_type=marker_type,
                category=RiskCategory.SECURITY,
                model_id=model_id,
                file_path=file_path,
                line_number=finding.line_number,
                message=finding.message,
                suggestion=None,
            ))

    # Edge-case markers via regex patterns
    lines = code.split('\n')
    for line_num, line in enumerate(lines, 1):
        for pattern, marker_type, message in _EDGE_CASE_PATTERNS:
            if pattern.search(line):
                markers.append(RiskMarker(
                    marker_type=marker_type,
                    category=RiskCategory.EDGE_CASE,
                    model_id=model_id,
                    file_path=file_path,
                    line_number=line_num,
                    message=message,
                ))

    return markers


def check_anchor_compatibility(
    code: str,
    anchors: list[Anchor],
    model_id: str = "",
) -> list[AnchorConflict]:
    """Check code against anchor constraints.

    Returns AnchorConflict for each violated anchor.
    Hard conflicts come from invariant anchors, soft from preference anchors.
    """
    if not anchors:
        return []

    checker = ContinuityChecker()
    report = checker.check(code, anchors)

    conflicts: list[AnchorConflict] = []
    for violation in report.violations:
        anchor = next(
            (a for a in anchors if a.id == violation.anchor_id),
            None,
        )
        conflict_type = AnchorConflictType.HARD
        if anchor is not None and anchor.constraint_class == ConstraintClass.PREFERENCE:
            conflict_type = AnchorConflictType.SOFT

        conflicts.append(AnchorConflict(
            anchor_id=violation.anchor_id,
            conflict_type=conflict_type,
            model_id=model_id,
            description=violation.description,
            evidence="; ".join(violation.evidence) if violation.evidence else "",
        ))

    return conflicts


def _compute_marker_union_and_unique(
    markers: list[RiskMarker],
) -> tuple[list[RiskMarker], dict[str, list[RiskMarker]]]:
    """Compute the union lens and per-model unique markers.

    Union: all markers (deduplicated by type + file + line).
    Unique: markers that only one model produced.
    """
    # Deduplicate for union: key is (marker_type, file_path, line_number)
    seen: dict[tuple[str, str, int], RiskMarker] = {}
    per_model: dict[str, list[RiskMarker]] = {}

    for m in markers:
        key = (m.marker_type.value, m.file_path, m.line_number)
        if key not in seen:
            seen[key] = m
        if m.model_id not in per_model:
            per_model[m.model_id] = []
        per_model[m.model_id].append(m)

    union = list(seen.values())

    # Unique: markers whose (type, file, line) appears in only one model
    key_to_models: dict[tuple[str, str, int], set[str]] = {}
    for m in markers:
        key = (m.marker_type.value, m.file_path, m.line_number)
        if key not in key_to_models:
            key_to_models[key] = set()
        key_to_models[key].add(m.model_id)

    unique: dict[str, list[RiskMarker]] = {}
    for m in markers:
        key = (m.marker_type.value, m.file_path, m.line_number)
        if len(key_to_models.get(key, set())) == 1:
            if m.model_id not in unique:
                unique[m.model_id] = []
            unique[m.model_id].append(m)

    return union, unique


def compute_code_divergence(
    irun: InterferometryRun,
    anchors: list[Anchor] | None = None,
    config: CodeInterferometryConfig | None = None,
) -> CodeDivergenceReport:
    """Analyze an InterferometryRun for code-specific divergence.

    Iterates irun.runs, extracts code blocks, runs risk markers and anchor
    compatibility checks. Produces a CodeDivergenceReport.
    """
    if config is None:
        config = CodeInterferometryConfig()
    if anchors is None:
        anchors = []

    all_markers: list[RiskMarker] = []
    all_conflicts: list[AnchorConflict] = []
    artifacts: list[CodeArtifact] = []

    for run in irun.runs:
        blocks = extract_code_blocks(run.response)
        files = [
            {"path": f"block_{i}", "language": b["language"], "content": b["content"]}
            for i, b in enumerate(blocks)
        ]
        artifact = CodeArtifact(
            model_id=run.model_id,
            files=files,
        )
        artifacts.append(artifact)

        # Extract risk markers from each code block
        for block in blocks:
            block_markers = extract_risk_markers(
                block["content"],
                file_path=f"<{run.model_id}>",
                model_id=run.model_id,
            )
            all_markers.extend(block_markers)

        # Check full response code against anchors
        full_code = "\n".join(b["content"] for b in blocks)
        if full_code and anchors:
            conflicts = check_anchor_compatibility(
                full_code, anchors, model_id=run.model_id,
            )
            all_conflicts.extend(conflicts)

    union, unique = _compute_marker_union_and_unique(all_markers)

    report = CodeDivergenceReport(
        interferometry_run_id=irun.id,
        artifacts=artifacts,
        risk_markers=all_markers,
        anchor_conflicts=all_conflicts,
        divergence_entropy=irun.signals.disagreement_rate,
        risk_marker_union=union,
        risk_marker_unique=unique,
    )

    tier, reasons = determine_tier(report, config)
    report.tier = tier
    report.tier_reasons = reasons

    return report


def determine_tier(
    report: CodeDivergenceReport,
    config: CodeInterferometryConfig | None = None,
) -> tuple[int, list[str]]:
    """Determine the interferometry tier for a report.

    Returns (tier, reasons).
    Tier 0: no issues detected.
    Tier 1: auto-triggered (divergence, risk markers, or anchor conflicts).
    Tier 2 is user-initiated only and never auto-assigned.
    """
    if config is None:
        config = CodeInterferometryConfig()

    reasons: list[str] = []

    if report.divergence_entropy > config.divergence_threshold:
        reasons.append(
            f"Divergence entropy {report.divergence_entropy:.2f} exceeds threshold {config.divergence_threshold}"
        )

    if config.risk_markers_trigger and len(report.risk_marker_union) > 0:
        security_count = sum(
            1 for m in report.risk_marker_union if m.category == RiskCategory.SECURITY
        )
        edge_count = sum(
            1 for m in report.risk_marker_union if m.category == RiskCategory.EDGE_CASE
        )
        parts = []
        if security_count:
            parts.append(f"{security_count} security")
        if edge_count:
            parts.append(f"{edge_count} edge-case")
        reasons.append(f"Risk markers found: {', '.join(parts) or 'markers present'}")

    if config.anchor_conflicts_trigger and len(report.anchor_conflicts) > 0:
        hard = sum(
            1 for c in report.anchor_conflicts
            if c.conflict_type == AnchorConflictType.HARD
        )
        soft = len(report.anchor_conflicts) - hard
        parts = []
        if hard:
            parts.append(f"{hard} hard")
        if soft:
            parts.append(f"{soft} soft")
        reasons.append(f"Anchor conflicts: {', '.join(parts)}")

    tier = 1 if reasons else 0
    return tier, reasons


def code_divergence_to_findings(report: CodeDivergenceReport) -> list[CheckFinding]:
    """Convert a CodeDivergenceReport to CheckFindings for VS Code integration.

    Produces findings with source="interferometry" that flow through the
    existing DiagnosticProvider pipeline.
    """
    findings: list[CheckFinding] = []

    for marker in report.risk_marker_union:
        line = max(0, marker.line_number - 1)  # Convert to 0-based
        severity = "error" if marker.category == RiskCategory.SECURITY else "warning"

        findings.append(CheckFinding(
            code=f"interfer-{marker.marker_type.value}",
            message=f"[{marker.model_id}] {marker.message}",
            severity=severity,
            source="interferometry",
            range=Range(
                start=Position(line=line, character=0),
                end=Position(line=line, character=80),
            ),
            suggestion=marker.suggestion,
        ))

    for conflict in report.anchor_conflicts:
        severity = "error" if conflict.conflict_type == AnchorConflictType.HARD else "warning"
        findings.append(CheckFinding(
            code=f"interfer-anchor-{conflict.anchor_id}",
            message=f"[{conflict.model_id}] Anchor conflict: {conflict.description}",
            severity=severity,
            source="interferometry",
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=80),
            ),
        ))

    return findings


def format_tier1_banner(report: CodeDivergenceReport) -> str:
    """Format a plain-language Tier 1 warning banner.

    This is what users see in the WebUI / VS Code notification.
    No "winner" language — instrumentation only.
    """
    if report.tier == 0:
        return ""

    parts: list[str] = []

    security_markers = [
        m for m in report.risk_marker_union
        if m.category == RiskCategory.SECURITY
    ]
    edge_markers = [
        m for m in report.risk_marker_union
        if m.category == RiskCategory.EDGE_CASE
    ]
    hard_conflicts = [
        c for c in report.anchor_conflicts
        if c.conflict_type == AnchorConflictType.HARD
    ]

    if security_markers:
        count = len(security_markers)
        parts.append(f"{count} security marker{'s' if count != 1 else ''} flagged")

    if edge_markers:
        count = len(edge_markers)
        parts.append(f"{count} edge-case marker{'s' if count != 1 else ''} found")

    if hard_conflicts:
        count = len(hard_conflicts)
        parts.append(f"{count} anchor conflict{'s' if count != 1 else ''}")

    total_unique = sum(len(v) for v in report.risk_marker_unique.values())
    if total_unique:
        parts.append(f"{total_unique} marker{'s' if total_unique != 1 else ''} spotted by only one model")

    if not parts:
        parts.append("Models disagreed")

    return "Models disagreed. " + ". ".join(parts) + "."
