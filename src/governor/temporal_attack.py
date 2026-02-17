# SPDX-License-Identifier: Apache-2.0
"""Temporal attack surface scanner — Δt-aware security analysis (AG2 Parallel Track).

Detects temporal vulnerability patterns: race windows, fail-open defaults,
commitment-before-verification, log-not-gate, unbounded retry, and more.

Static detection of temporal antipatterns in code and infra-as-code.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ===================================================================
# Enums
# ===================================================================

class TemporalMarkerType(Enum):
    """Types of temporal vulnerability markers."""
    # Code-level markers
    TOCTOU_RACE = "TOCTOU_RACE"
    FAIL_OPEN_DEFAULT = "FAIL_OPEN_DEFAULT"
    COMMIT_BEFORE_VERIFY = "COMMIT_BEFORE_VERIFY"
    LOG_NOT_GATE = "LOG_NOT_GATE"
    UNBOUNDED_RETRY = "UNBOUNDED_RETRY"
    APPROVAL_NO_CONTEXT = "APPROVAL_NO_CONTEXT"
    ASYNC_ENFORCEMENT = "ASYNC_ENFORCEMENT"
    LONG_LIVED_CREDENTIAL = "LONG_LIVED_CREDENTIAL"
    BURST_CAPACITY = "BURST_CAPACITY"
    # Development-time debt markers
    TYPE_IGNORE_NO_ISSUE = "TYPE_IGNORE_NO_ISSUE"
    CATCH_ALL_CONTINUE = "CATCH_ALL_CONTINUE"
    ASYNC_NO_TIMEOUT = "ASYNC_NO_TIMEOUT"
    FEATURE_FLAG_NO_TTL = "FEATURE_FLAG_NO_TTL"
    # Ops/infra markers
    ALERT_NO_RUNBOOK = "ALERT_NO_RUNBOOK"
    HEALTH_CHECK_TOO_SLOW = "HEALTH_CHECK_TOO_SLOW"
    MANUAL_ONLY_REMEDIATION = "MANUAL_ONLY_REMEDIATION"
    CONFIG_NO_DRIFT_CHECK = "CONFIG_NO_DRIFT_CHECK"
    EVIDENCE_NO_EXPIRY = "EVIDENCE_NO_EXPIRY"


class TemporalDomain(Enum):
    """Domain classification for temporal markers."""
    CODE = "code"
    OPS = "ops"
    BOTH = "both"


class MarkerSeverity(Enum):
    """Severity of a temporal marker finding."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ===================================================================
# Configuration
# ===================================================================

# Marker metadata: domain, default severity, Δt concept
MARKER_META: dict[TemporalMarkerType, dict[str, Any]] = {
    TemporalMarkerType.TOCTOU_RACE: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.HIGH,
        "delta_t": "T_check < T_act gap",
        "description": "Check-then-act without atomicity",
    },
    TemporalMarkerType.FAIL_OPEN_DEFAULT: {
        "domain": TemporalDomain.BOTH,
        "severity": MarkerSeverity.HIGH,
        "delta_t": "C_j = fail-open under uncertainty",
        "description": "Timeout/exception handler that allows action",
    },
    TemporalMarkerType.COMMIT_BEFORE_VERIFY: {
        "domain": TemporalDomain.BOTH,
        "severity": MarkerSeverity.CRITICAL,
        "delta_t": "T_commit < T_verify",
        "description": "Irreversible action before validation completes",
    },
    TemporalMarkerType.LOG_NOT_GATE: {
        "domain": TemporalDomain.BOTH,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "A_j = ∞ (no enforcement)",
        "description": "Security violation logged but not blocked",
    },
    TemporalMarkerType.UNBOUNDED_RETRY: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "W_j inflation",
        "description": "Retry loop without backoff or limit",
    },
    TemporalMarkerType.APPROVAL_NO_CONTEXT: {
        "domain": TemporalDomain.BOTH,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "κ_j exhaustion",
        "description": "Approval with insufficient context",
    },
    TemporalMarkerType.ASYNC_ENFORCEMENT: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.HIGH,
        "delta_t": "W_j + A_j gap",
        "description": "Detection and response in different processes",
    },
    TemporalMarkerType.LONG_LIVED_CREDENTIAL: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "Large T_commit window",
        "description": "Token/session with no expiry or long TTL",
    },
    TemporalMarkerType.BURST_CAPACITY: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Single-burst objective completion",
        "description": "Rate limiter with large bucket or no burst limit",
    },
    TemporalMarkerType.TYPE_IGNORE_NO_ISSUE: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Type drift accumulation",
        "description": "type: ignore without issue reference",
    },
    TemporalMarkerType.CATCH_ALL_CONTINUE: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "Evidence erasure",
        "description": "Broad except that swallows and continues",
    },
    TemporalMarkerType.ASYNC_NO_TIMEOUT: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "Unbounded W_j",
        "description": "Async operation without timeout",
    },
    TemporalMarkerType.FEATURE_FLAG_NO_TTL: {
        "domain": TemporalDomain.CODE,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Stale cache window",
        "description": "Feature flag without expiration",
    },
    TemporalMarkerType.ALERT_NO_RUNBOOK: {
        "domain": TemporalDomain.OPS,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "Human W_j bottleneck",
        "description": "Alert configured without runbook reference",
    },
    TemporalMarkerType.HEALTH_CHECK_TOO_SLOW: {
        "domain": TemporalDomain.OPS,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Detection latency",
        "description": "Health check interval too long",
    },
    TemporalMarkerType.MANUAL_ONLY_REMEDIATION: {
        "domain": TemporalDomain.OPS,
        "severity": MarkerSeverity.MEDIUM,
        "delta_t": "Human response bottleneck",
        "description": "Remediation path requires manual action only",
    },
    TemporalMarkerType.CONFIG_NO_DRIFT_CHECK: {
        "domain": TemporalDomain.OPS,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Drift accumulation",
        "description": "Configuration without drift detection",
    },
    TemporalMarkerType.EVIDENCE_NO_EXPIRY: {
        "domain": TemporalDomain.BOTH,
        "severity": MarkerSeverity.LOW,
        "delta_t": "Stale evidence",
        "description": "Evidence or credential with no expiration",
    },
}


# ===================================================================
# Dataclasses
# ===================================================================

@dataclass
class TemporalMarker:
    """A detected temporal vulnerability marker."""
    marker_type: TemporalMarkerType
    severity: MarkerSeverity
    domain: TemporalDomain
    line: int = 0
    column: int = 0
    file_path: str = ""
    snippet: str = ""
    delta_t: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "marker_type": self.marker_type.value,
            "severity": self.severity.value,
            "domain": self.domain.value,
            "line": self.line,
            "column": self.column,
            "file_path": self.file_path,
            "snippet": self.snippet,
            "delta_t": self.delta_t,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TemporalMarker:
        return cls(
            marker_type=TemporalMarkerType(d["marker_type"]),
            severity=MarkerSeverity(d["severity"]),
            domain=TemporalDomain(d["domain"]),
            line=d.get("line", 0),
            column=d.get("column", 0),
            file_path=d.get("file_path", ""),
            snippet=d.get("snippet", ""),
            delta_t=d.get("delta_t", ""),
            description=d.get("description", ""),
        )


@dataclass
class ScanResult:
    """Result of a temporal attack surface scan."""
    file_path: str
    markers: list[TemporalMarker] = field(default_factory=list)
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @property
    def marker_count(self) -> int:
        return len(self.markers)

    @property
    def critical_count(self) -> int:
        return sum(1 for m in self.markers if m.severity == MarkerSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for m in self.markers if m.severity == MarkerSeverity.HIGH)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "markers": [m.to_dict() for m in self.markers],
            "marker_count": self.marker_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScanResult:
        return cls(
            file_path=d["file_path"],
            markers=[TemporalMarker.from_dict(m) for m in d.get("markers", [])],
            ts=d.get("ts", ""),
        )


@dataclass
class TemporalScanState:
    """Aggregate state across multiple scans."""
    results: list[ScanResult] = field(default_factory=list)
    total_markers: int = 0
    marker_counts: dict[str, int] = field(default_factory=dict)

    def record(self, result: ScanResult) -> None:
        self.results.append(result)
        self.total_markers += result.marker_count
        for m in result.markers:
            key = m.marker_type.value
            self.marker_counts[key] = self.marker_counts.get(key, 0) + 1

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "total_markers": self.total_markers,
            "marker_counts": dict(self.marker_counts),
        }

    @classmethod
    def from_dict(cls, d: dict) -> TemporalScanState:
        return cls(
            results=[ScanResult.from_dict(r) for r in d.get("results", [])],
            total_markers=d.get("total_markers", 0),
            marker_counts=d.get("marker_counts", {}),
        )


# ===================================================================
# Scanner patterns
# ===================================================================

# TOCTOU: check-then-act patterns
TOCTOU_PATTERNS = [
    re.compile(r"if\s+(os\.path\.exists|os\.path\.isfile|os\.path\.isdir)\s*\("),
    re.compile(r"if\s+not\s+(os\.path\.exists|os\.path\.isfile)\s*\("),
    re.compile(r"if\s+\w+\.exists\(\)\s*:"),
]

# Fail-open: exception handlers that allow action
FAIL_OPEN_PATTERNS = [
    re.compile(r"except\s*(TimeoutError|Timeout|ConnectionError|Exception)\s*:?\s*$"),
]
FAIL_OPEN_ALLOW_PATTERNS = [
    re.compile(r"\b(allow|permit|grant|approve|continue|pass)\b"),
]

# Log-not-gate: warning without enforcement
LOG_NOT_GATE_PATTERNS = [
    re.compile(r"(logger\.(warning|warn)|logging\.(warning|warn)|print\s*\(\s*[\"'].*(?:reject|denied|violation|fail))"),
]

# Unbounded retry
UNBOUNDED_RETRY_PATTERNS = [
    re.compile(r"while\s+True\s*:"),
]
RETRY_GUARD_PATTERNS = [
    re.compile(r"\b(max_retries|retry_count|backoff|jitter|break|return)\b"),
]

# Catch-all continue
CATCH_ALL_PATTERNS = [
    re.compile(r"except\s*:\s*$"),
    re.compile(r"except\s+Exception\s*:\s*$"),
    re.compile(r"except\s+BaseException\s*:\s*$"),
]

# Type ignore without issue
TYPE_IGNORE_PATTERN = re.compile(r"#\s*type:\s*ignore(?!\s*\[)")
TYPE_IGNORE_WITH_CODE = re.compile(r"#\s*type:\s*ignore\[")

# Async without timeout
ASYNC_NO_TIMEOUT_PATTERNS = [
    re.compile(r"asyncio\.(wait|gather|sleep)\s*\((?!.*timeout)"),
    re.compile(r"await\s+\w+\.\w+\((?!.*timeout)"),
]

# Feature flag without TTL
FEATURE_FLAG_PATTERNS = [
    re.compile(r"(feature_flag|flag|toggle)\s*[\[\(]"),
]


# ===================================================================
# Core scanner functions
# ===================================================================

def _make_marker(
    marker_type: TemporalMarkerType,
    line: int,
    snippet: str,
    file_path: str = "",
) -> TemporalMarker:
    meta = MARKER_META[marker_type]
    return TemporalMarker(
        marker_type=marker_type,
        severity=meta["severity"],
        domain=meta["domain"],
        line=line,
        file_path=file_path,
        snippet=snippet.strip()[:200],
        delta_t=meta["delta_t"],
        description=meta["description"],
    )


def scan_toctou(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect check-then-act patterns without atomicity."""
    markers = []
    for i, line in enumerate(lines):
        for pat in TOCTOU_PATTERNS:
            if pat.search(line):
                # Check if next non-empty line does file operations
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and re.search(r"\b(open|write|create|mkdir|remove|unlink)\b", next_line):
                        markers.append(_make_marker(
                            TemporalMarkerType.TOCTOU_RACE, i + 1, line, file_path,
                        ))
                        break
    return markers


def scan_fail_open(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect fail-open exception handlers."""
    markers = []
    for i, line in enumerate(lines):
        for pat in FAIL_OPEN_PATTERNS:
            if pat.search(line):
                # Check handler body for allow actions
                for j in range(i + 1, min(i + 5, len(lines))):
                    handler_line = lines[j]
                    for allow_pat in FAIL_OPEN_ALLOW_PATTERNS:
                        if allow_pat.search(handler_line):
                            markers.append(_make_marker(
                                TemporalMarkerType.FAIL_OPEN_DEFAULT,
                                i + 1, line, file_path,
                            ))
                            break
    return markers


def scan_log_not_gate(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect advisory logging without enforcement."""
    markers = []
    for i, line in enumerate(lines):
        for pat in LOG_NOT_GATE_PATTERNS:
            if pat.search(line):
                # Check if next lines continue instead of blocking
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and not re.search(r"\b(raise|return|sys\.exit|abort|break)\b", next_line):
                        if re.search(r"(apply|execute|commit|deploy|proceed)", next_line):
                            markers.append(_make_marker(
                                TemporalMarkerType.LOG_NOT_GATE,
                                i + 1, line, file_path,
                            ))
                            break
    return markers


def scan_unbounded_retry(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect retry loops without backoff or limits."""
    markers = []
    for i, line in enumerate(lines):
        for pat in UNBOUNDED_RETRY_PATTERNS:
            if pat.search(line):
                # Check loop body for guards
                has_guard = False
                for j in range(i + 1, min(i + 15, len(lines))):
                    for guard_pat in RETRY_GUARD_PATTERNS:
                        if guard_pat.search(lines[j]):
                            has_guard = True
                            break
                    if has_guard:
                        break
                if not has_guard:
                    markers.append(_make_marker(
                        TemporalMarkerType.UNBOUNDED_RETRY,
                        i + 1, line, file_path,
                    ))
    return markers


def scan_catch_all(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect broad exception handlers that swallow and continue."""
    markers = []
    for i, line in enumerate(lines):
        for pat in CATCH_ALL_PATTERNS:
            if pat.search(line):
                # Check if handler just continues
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    if next_line in ("pass", "continue", "..."):
                        markers.append(_make_marker(
                            TemporalMarkerType.CATCH_ALL_CONTINUE,
                            i + 1, line, file_path,
                        ))
                        break
    return markers


def scan_type_ignore(lines: list[str], file_path: str = "") -> list[TemporalMarker]:
    """Detect type: ignore without issue reference."""
    markers = []
    for i, line in enumerate(lines):
        if TYPE_IGNORE_PATTERN.search(line) and not TYPE_IGNORE_WITH_CODE.search(line):
            markers.append(_make_marker(
                TemporalMarkerType.TYPE_IGNORE_NO_ISSUE,
                i + 1, line, file_path,
            ))
    return markers


def scan_text(text: str, file_path: str = "") -> ScanResult:
    """Scan text for all temporal antipatterns."""
    lines = text.split("\n")
    markers: list[TemporalMarker] = []

    markers.extend(scan_toctou(lines, file_path))
    markers.extend(scan_fail_open(lines, file_path))
    markers.extend(scan_log_not_gate(lines, file_path))
    markers.extend(scan_unbounded_retry(lines, file_path))
    markers.extend(scan_catch_all(lines, file_path))
    markers.extend(scan_type_ignore(lines, file_path))

    return ScanResult(file_path=file_path, markers=markers)


def scan_file(path: Path) -> ScanResult:
    """Scan a file for temporal antipatterns."""
    if not path.exists():
        return ScanResult(file_path=str(path))
    text = path.read_text(errors="replace")
    return scan_text(text, str(path))


def scan_directory(
    directory: Path,
    extensions: set[str] | None = None,
) -> list[ScanResult]:
    """Scan all matching files in a directory."""
    exts = extensions or {".py", ".js", ".ts", ".go", ".java", ".yaml", ".yml", ".toml"}
    results = []
    if not directory.exists():
        return results
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in exts:
            result = scan_file(path)
            if result.markers:
                results.append(result)
    return results


# ===================================================================
# Approval fatigue analysis
# ===================================================================

@dataclass
class FatigueSignals:
    """Signals indicating approval fatigue risk."""
    queue_depth: int = 0
    similar_approvals_in_window: int = 0
    avg_review_time_seconds: float = 0.0
    approvals_per_hour: float = 0.0

    def fatigue_score(self) -> float:
        """Compute fatigue risk score [0, 1]."""
        score = 0.0
        if self.queue_depth > 10:
            score += 0.3
        elif self.queue_depth > 5:
            score += 0.15
        if self.similar_approvals_in_window > 5:
            score += 0.3
        if self.avg_review_time_seconds > 0 and self.avg_review_time_seconds < 30:
            score += 0.2  # Too fast = rubber stamp
        if self.approvals_per_hour > 20:
            score += 0.2
        return min(1.0, score)

    def to_dict(self) -> dict:
        return {
            "queue_depth": self.queue_depth,
            "similar_approvals_in_window": self.similar_approvals_in_window,
            "avg_review_time_seconds": self.avg_review_time_seconds,
            "approvals_per_hour": self.approvals_per_hour,
            "fatigue_score": self.fatigue_score(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> FatigueSignals:
        return cls(
            queue_depth=d.get("queue_depth", 0),
            similar_approvals_in_window=d.get("similar_approvals_in_window", 0),
            avg_review_time_seconds=d.get("avg_review_time_seconds", 0.0),
            approvals_per_hour=d.get("approvals_per_hour", 0.0),
        )


# ===================================================================
# Events
# ===================================================================

def make_temporal_event(
    action: str,
    details: dict | None = None,
) -> dict:
    return {
        "type": "temporal_attack_surface",
        "action": action,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": details or {},
    }


def make_scan_event(result: ScanResult) -> dict:
    return make_temporal_event("scan", {
        "file": result.file_path,
        "marker_count": result.marker_count,
        "critical": result.critical_count,
        "high": result.high_count,
    })


# ===================================================================
# Store
# ===================================================================

class TemporalAttackStore:
    """Persistence for temporal scan state."""

    def __init__(self, governor_dir: Path | None = None):
        base = governor_dir or Path(".governor")
        self.temporal_dir = base / "temporal_attack"

    def save(self, state: TemporalScanState, run_id: str = "default") -> None:
        self.temporal_dir.mkdir(parents=True, exist_ok=True)
        path = self.temporal_dir / f"{run_id}.json"
        path.write_text(json.dumps(state.to_dict(), indent=2))

    def load(self, run_id: str = "default") -> TemporalScanState | None:
        path = self.temporal_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return TemporalScanState.from_dict(json.loads(path.read_text()))

    def list_runs(self) -> list[str]:
        if not self.temporal_dir.exists():
            return []
        return sorted(p.stem for p in self.temporal_dir.glob("*.json"))
