"""
Coverage and Efficiency Metrics — Severity-Weighted Verification.

Drives phase transitions, risk assessment, and CBI computation.
Coverage = Σ(w_i · v_i) / Σ(w_i) where w_i is severity weight.

Spec: METRICS_SPEC (Layer 2.1-A)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MetricSeverity(str, Enum):
    """Severity levels for claims (mirrors admissibility Severity)."""
    S1 = "S1"  # Low
    S2 = "S2"  # Medium
    S3 = "S3"  # High


class VerificationStatus(str, Enum):
    """Status of a claim's verification."""
    UNKNOWN = "unknown"
    VERIFIED = "verified"
    WAIVED = "waived"
    REFUTED = "refuted"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[MetricSeverity, float] = {
    MetricSeverity.S1: 1.0,
    MetricSeverity.S2: 3.0,
    MetricSeverity.S3: 10.0,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MetricClaim:
    """A claim tracked for coverage metrics."""
    claim_id: str
    description: str
    severity: MetricSeverity
    status: VerificationStatus = VerificationStatus.UNKNOWN
    evidence_id: str = ""  # Link to evidence that verified/refuted

    @property
    def weight(self) -> float:
        return SEVERITY_WEIGHTS.get(self.severity, 1.0)

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    @property
    def is_resolved(self) -> bool:
        """Claim is resolved (verified, waived, or refuted)."""
        return self.status in (
            VerificationStatus.VERIFIED,
            VerificationStatus.WAIVED,
            VerificationStatus.REFUTED,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "claim_id": self.claim_id,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
        }
        if self.evidence_id:
            d["evidence_id"] = self.evidence_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MetricClaim:
        return cls(
            claim_id=d["claim_id"],
            description=d.get("description", ""),
            severity=MetricSeverity(d["severity"]),
            status=VerificationStatus(d.get("status", "unknown")),
            evidence_id=d.get("evidence_id", ""),
        )


@dataclass
class ClaimCoverage:
    """Aggregated coverage statistics."""
    total_claims: int
    by_status: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, dict[str, int]] = field(default_factory=dict)
    weighted_coverage: float = 0.0

    def s3_coverage(self) -> float:
        """Coverage for S3 claims only."""
        s3 = self.by_severity.get("S3", {})
        total = sum(s3.values())
        if total == 0:
            return 1.0
        verified = s3.get("verified", 0) + s3.get("waived", 0)
        return verified / total

    def s2_coverage(self) -> float:
        """Coverage for S2 claims only."""
        s2 = self.by_severity.get("S2", {})
        total = sum(s2.values())
        if total == 0:
            return 1.0
        verified = s2.get("verified", 0) + s2.get("waived", 0)
        return verified / total

    def summary(self) -> str:
        return (
            f"Coverage: {self.weighted_coverage:.1%} | "
            f"S3: {self.s3_coverage():.1%} | "
            f"S2: {self.s2_coverage():.1%}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "by_status": self.by_status,
            "by_severity": self.by_severity,
            "weighted_coverage": self.weighted_coverage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimCoverage:
        return cls(
            total_claims=d["total_claims"],
            by_status=d.get("by_status", {}),
            by_severity=d.get("by_severity", {}),
            weighted_coverage=d.get("weighted_coverage", 0.0),
        )


@dataclass
class EfficiencyMetric:
    """Verification efficiency: how much certainty per check."""
    coverage_before: float
    coverage_after: float
    actions: int
    efficiency: float = 0.0

    def __post_init__(self) -> None:
        if self.efficiency == 0.0 and self.actions > 0:
            self.efficiency = (self.coverage_after - self.coverage_before) / self.actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_before": self.coverage_before,
            "coverage_after": self.coverage_after,
            "actions": self.actions,
            "efficiency": self.efficiency,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EfficiencyMetric:
        return cls(
            coverage_before=d["coverage_before"],
            coverage_after=d["coverage_after"],
            actions=d["actions"],
            efficiency=d.get("efficiency", 0.0),
        )


@dataclass
class CoverageSnapshot:
    """Point-in-time coverage snapshot for tracking deltas."""
    ts: str
    coverage: float
    total_claims: int
    verified_claims: int
    actions_taken: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "coverage": self.coverage,
            "total_claims": self.total_claims,
            "verified_claims": self.verified_claims,
            "actions_taken": self.actions_taken,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CoverageSnapshot:
        return cls(
            ts=d["ts"],
            coverage=d["coverage"],
            total_claims=d["total_claims"],
            verified_claims=d["verified_claims"],
            actions_taken=d.get("actions_taken", 0),
        )


# ---------------------------------------------------------------------------
# Core computation functions
# ---------------------------------------------------------------------------

def compute_coverage(claims: list[MetricClaim]) -> float:
    """Compute severity-weighted coverage.

    Coverage = Σ(w_i · v_i) / Σ(w_i) where v_i = 1 if verified/waived.
    Empty claim list returns 1.0 (vacuously covered).
    """
    if not claims:
        return 1.0
    total_weight = sum(c.weight for c in claims)
    if total_weight == 0:
        return 1.0
    verified_weight = sum(c.weight for c in claims if c.is_verified or c.status == VerificationStatus.WAIVED)
    return verified_weight / total_weight


def compute_coverage_by_severity(claims: list[MetricClaim], severity: MetricSeverity) -> float:
    """Compute coverage for claims of a specific severity."""
    filtered = [c for c in claims if c.severity == severity]
    return compute_coverage(filtered)


def compute_efficiency(coverage_before: float, coverage_after: float, actions: int) -> float:
    """Compute verification efficiency η = ΔCoverage / actions."""
    if actions == 0:
        return 0.0
    return (coverage_after - coverage_before) / actions


def compute_claim_coverage(claims: list[MetricClaim]) -> ClaimCoverage:
    """Compute full claim coverage statistics."""
    by_status: dict[str, int] = {}
    by_severity: dict[str, dict[str, int]] = {}

    for c in claims:
        st = c.status.value
        sv = c.severity.value

        by_status[st] = by_status.get(st, 0) + 1

        if sv not in by_severity:
            by_severity[sv] = {}
        by_severity[sv][st] = by_severity[sv].get(st, 0) + 1

    return ClaimCoverage(
        total_claims=len(claims),
        by_status=by_status,
        by_severity=by_severity,
        weighted_coverage=compute_coverage(claims),
    )


def update_claim_status(
    claim: MetricClaim,
    new_status: VerificationStatus,
    evidence_id: str = "",
) -> MetricClaim:
    """Update a claim's verification status. Returns new claim (immutable style)."""
    return MetricClaim(
        claim_id=claim.claim_id,
        description=claim.description,
        severity=claim.severity,
        status=new_status,
        evidence_id=evidence_id or claim.evidence_id,
    )


# ---------------------------------------------------------------------------
# MetricsTracker — per-run tracking
# ---------------------------------------------------------------------------

@dataclass
class MetricsTracker:
    """Tracks claims and coverage for a single run."""
    run_id: str
    claims: list[MetricClaim] = field(default_factory=list)
    snapshots: list[CoverageSnapshot] = field(default_factory=list)
    total_actions: int = 0

    def add_claim(self, claim: MetricClaim) -> None:
        self.claims.append(claim)

    def verify_claim(self, claim_id: str, evidence_id: str = "") -> bool:
        """Mark a claim as verified. Returns True if found."""
        for i, c in enumerate(self.claims):
            if c.claim_id == claim_id:
                self.claims[i] = update_claim_status(c, VerificationStatus.VERIFIED, evidence_id)
                return True
        return False

    def waive_claim(self, claim_id: str) -> bool:
        """Mark a claim as waived. Returns True if found."""
        for i, c in enumerate(self.claims):
            if c.claim_id == claim_id:
                self.claims[i] = update_claim_status(c, VerificationStatus.WAIVED)
                return True
        return False

    def refute_claim(self, claim_id: str, evidence_id: str = "") -> bool:
        """Mark a claim as refuted. Returns True if found."""
        for i, c in enumerate(self.claims):
            if c.claim_id == claim_id:
                self.claims[i] = update_claim_status(c, VerificationStatus.REFUTED, evidence_id)
                return True
        return False

    @property
    def coverage(self) -> float:
        return compute_coverage(self.claims)

    @property
    def claim_coverage(self) -> ClaimCoverage:
        return compute_claim_coverage(self.claims)

    def take_snapshot(self, actions_taken: int = 0) -> CoverageSnapshot:
        """Take a coverage snapshot."""
        self.total_actions += actions_taken
        verified = sum(1 for c in self.claims if c.is_verified)
        snap = CoverageSnapshot(
            ts=datetime.now(timezone.utc).isoformat(),
            coverage=self.coverage,
            total_claims=len(self.claims),
            verified_claims=verified,
            actions_taken=self.total_actions,
        )
        self.snapshots.append(snap)
        return snap

    def latest_efficiency(self) -> float:
        """Compute efficiency from the last two snapshots."""
        if len(self.snapshots) < 2:
            return 0.0
        prev = self.snapshots[-2]
        curr = self.snapshots[-1]
        action_delta = curr.actions_taken - prev.actions_taken
        return compute_efficiency(prev.coverage, curr.coverage, action_delta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "claims": [c.to_dict() for c in self.claims],
            "snapshots": [s.to_dict() for s in self.snapshots],
            "total_actions": self.total_actions,
            "coverage": self.coverage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MetricsTracker:
        tracker = cls(
            run_id=d["run_id"],
            claims=[MetricClaim.from_dict(c) for c in d.get("claims", [])],
            snapshots=[CoverageSnapshot.from_dict(s) for s in d.get("snapshots", [])],
            total_actions=d.get("total_actions", 0),
        )
        return tracker


# ---------------------------------------------------------------------------
# MetricsStore — persistence
# ---------------------------------------------------------------------------

class MetricsStore:
    """Persistent store for metrics."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.metrics_dir = self.governor_dir / "metrics"

    def _ensure_dirs(self) -> None:
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

    def save_tracker(self, tracker: MetricsTracker) -> Path:
        self._ensure_dirs()
        path = self.metrics_dir / f"{tracker.run_id}.json"
        path.write_text(json.dumps(tracker.to_dict(), indent=2) + "\n")
        return path

    def load_tracker(self, run_id: str) -> MetricsTracker | None:
        path = self.metrics_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return MetricsTracker.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.metrics_dir.exists():
            return []
        return sorted(
            f.stem for f in self.metrics_dir.glob("*.json")
        )


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_metrics_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "metrics",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
