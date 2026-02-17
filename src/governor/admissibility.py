# SPDX-License-Identifier: Apache-2.0
"""
Admissibility Gate — Push-Back System.

Computes whether a task is well-specified enough to proceed. Push-back is
information-theoretically cheap compared to downstream loss from
underspecification.

Spec: ADMISSIBILITY_SPEC (Layer 2.1-A)
Invariant F: No hidden assumptions for S2/S3 actions.
"""

from __future__ import annotations

import hashlib
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

class Severity(str, Enum):
    """Severity levels for unknowns and claims."""
    S1 = "S1"  # Low — cosmetic, style, minor
    S2 = "S2"  # Medium — functional, correctness
    S3 = "S3"  # High — security, data loss, irreversible


class UnknownCategory(str, Enum):
    """Category of an unknown."""
    OBJECTIVE = "objective"      # What are we trying to achieve?
    CONSTRAINT = "constraint"    # What limits apply?
    CONTEXT = "context"          # What environment/state?
    RESOURCE = "resource"        # What resources available?


class ResolvableBy(str, Enum):
    """How an unknown can be resolved."""
    USER_CLARIFICATION = "user_clarification"
    TOOL_QUERY = "tool_query"
    ASSUMPTION = "assumption"


class PushbackMode(str, Enum):
    """Push-back mode based on admissibility score."""
    PROCEED = "proceed"  # A >= A_high: normal operation
    SOFT = "soft"        # A_low <= A < A_high: proceed but cap confidence
    HARD = "hard"        # A < A_low: deny COMMIT, ask questions
    SAFE = "safe"        # Any S3 unknown: block S3 actuation entirely


class AssumptionStatus(str, Enum):
    """Status of an assumption made to resolve an unknown."""
    ACTIVE = "active"
    WAIVED = "waived"
    INVALIDATED = "invalidated"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default weights for admissibility score components
W_SETPOINT = 0.4
W_CONSTRAINTS = 0.35
W_OBSERVABILITY = 0.25

# Default thresholds
A_HIGH = 0.7   # Above this: PROCEED
A_LOW = 0.4    # Below this: HARD push-back

# Default unknown severity weights (for penalty computation)
UNKNOWN_SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.S1: 0.05,
    Severity.S2: 0.15,
    Severity.S3: 0.40,
}

# Maximum questions to ask in HARD mode
MAX_QUESTIONS = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Unknown:
    """A first-class unknown with severity tracking."""
    id: str
    description: str
    severity: Severity
    category: UnknownCategory
    resolvable_by: ResolvableBy
    weight: float = 0.0  # Impact on admissibility (auto-computed if 0)

    def __post_init__(self) -> None:
        if self.weight == 0.0:
            self.weight = UNKNOWN_SEVERITY_WEIGHTS.get(self.severity, 0.1)

    def generate_question(self) -> str:
        """Generate a clarifying question for this unknown."""
        prefix = {
            UnknownCategory.OBJECTIVE: "What is the expected outcome for",
            UnknownCategory.CONSTRAINT: "What constraints apply to",
            UnknownCategory.CONTEXT: "What is the current state of",
            UnknownCategory.RESOURCE: "What resources are available for",
        }
        return f"{prefix.get(self.category, 'Can you clarify')} {self.description}?"

    def estimate_voi(self) -> float:
        """Estimate value of information for resolving this unknown.

        Higher severity + higher weight = more valuable to resolve.
        User-resolvable unknowns have higher VoI (definitive answers).
        """
        base = self.weight * {Severity.S1: 1.0, Severity.S2: 2.0, Severity.S3: 5.0}[self.severity]
        multiplier = {
            ResolvableBy.USER_CLARIFICATION: 1.5,
            ResolvableBy.TOOL_QUERY: 1.2,
            ResolvableBy.ASSUMPTION: 0.8,
        }
        return base * multiplier.get(self.resolvable_by, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category.value,
            "resolvable_by": self.resolvable_by.value,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Unknown:
        return cls(
            id=d["id"],
            description=d["description"],
            severity=Severity(d["severity"]),
            category=UnknownCategory(d["category"]),
            resolvable_by=ResolvableBy(d["resolvable_by"]),
            weight=d.get("weight", 0.0),
        )


@dataclass
class Assumption:
    """An assumption made to resolve an unknown."""
    id: str
    unknown_id: str
    assumption: str
    severity: Severity
    status: AssumptionStatus = AssumptionStatus.ACTIVE
    waiver_by: str = ""      # Who waived (if waived)
    waiver_reason: str = ""  # Why waived
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "unknown_id": self.unknown_id,
            "assumption": self.assumption,
            "severity": self.severity.value,
            "status": self.status.value,
            "waiver_by": self.waiver_by,
            "waiver_reason": self.waiver_reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Assumption:
        return cls(
            id=d["id"],
            unknown_id=d["unknown_id"],
            assumption=d["assumption"],
            severity=Severity(d["severity"]),
            status=AssumptionStatus(d.get("status", "active")),
            waiver_by=d.get("waiver_by", ""),
            waiver_reason=d.get("waiver_reason", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class AdmissibilityAssessment:
    """Assessment of task admissibility."""
    setpoint_score: float       # 0-1: how well-defined is success?
    constraint_score: float     # 0-1: are constraints explicit?
    observability_score: float  # 0-1: can we measure/verify success?
    unknowns: list[Unknown] = field(default_factory=list)

    # Configurable weights and thresholds
    w_setpoint: float = W_SETPOINT
    w_constraints: float = W_CONSTRAINTS
    w_observability: float = W_OBSERVABILITY
    a_high: float = A_HIGH
    a_low: float = A_LOW

    @property
    def score(self) -> float:
        """Compute admissibility score A."""
        base = (
            self.w_setpoint * self.setpoint_score
            + self.w_constraints * self.constraint_score
            + self.w_observability * self.observability_score
        )
        penalty = sum(u.weight for u in self.unknowns)
        return max(0.0, min(1.0, base - penalty))

    @property
    def mode(self) -> PushbackMode:
        """Determine push-back mode from score."""
        return select_pushback_mode(self)

    @property
    def s3_unknowns(self) -> list[Unknown]:
        """S3 unknowns that force SAFE mode."""
        return [u for u in self.unknowns if u.severity == Severity.S3]

    @property
    def s2_unknowns(self) -> list[Unknown]:
        return [u for u in self.unknowns if u.severity == Severity.S2]

    def to_dict(self) -> dict[str, Any]:
        return {
            "setpoint_score": self.setpoint_score,
            "constraint_score": self.constraint_score,
            "observability_score": self.observability_score,
            "unknowns": [u.to_dict() for u in self.unknowns],
            "score": self.score,
            "mode": self.mode.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AdmissibilityAssessment:
        return cls(
            setpoint_score=d["setpoint_score"],
            constraint_score=d["constraint_score"],
            observability_score=d["observability_score"],
            unknowns=[Unknown.from_dict(u) for u in d.get("unknowns", [])],
        )


@dataclass
class Waiver:
    """Explicit waiver for an unknown's assumption."""
    id: str
    unknown_id: str
    assumption_id: str
    by: str                  # Who granted the waiver
    acknowledged_risk: str   # What risk was acknowledged
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "unknown_id": self.unknown_id,
            "assumption_id": self.assumption_id,
            "by": self.by,
            "acknowledged_risk": self.acknowledged_risk,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Waiver:
        return cls(
            id=d["id"],
            unknown_id=d["unknown_id"],
            assumption_id=d["assumption_id"],
            by=d["by"],
            acknowledged_risk=d["acknowledged_risk"],
            created_at=d.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def select_pushback_mode(assessment: AdmissibilityAssessment) -> PushbackMode:
    """Select push-back mode based on admissibility assessment.

    S3 unknowns → SAFE (immediate, regardless of score).
    A >= A_high → PROCEED
    A_low <= A < A_high → SOFT
    A < A_low → HARD
    """
    if any(u.severity == Severity.S3 for u in assessment.unknowns):
        return PushbackMode.SAFE

    s = assessment.score
    if s >= assessment.a_high:
        return PushbackMode.PROCEED
    elif s >= assessment.a_low:
        return PushbackMode.SOFT
    else:
        return PushbackMode.HARD


def select_clarifying_questions(
    unknowns: list[Unknown], max_questions: int = MAX_QUESTIONS
) -> list[str]:
    """Select highest VoI questions that resolve unknowns."""
    if not unknowns:
        return []
    scored = [(u, u.estimate_voi()) for u in unknowns]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [u.generate_question() for u, _ in scored[:max_questions]]


def assess_task(
    setpoint: float,
    constraints: float,
    observability: float,
    unknowns: list[Unknown] | None = None,
    *,
    a_high: float = A_HIGH,
    a_low: float = A_LOW,
) -> AdmissibilityAssessment:
    """Convenience: assess a task and return full assessment."""
    return AdmissibilityAssessment(
        setpoint_score=max(0.0, min(1.0, setpoint)),
        constraint_score=max(0.0, min(1.0, constraints)),
        observability_score=max(0.0, min(1.0, observability)),
        unknowns=unknowns or [],
        a_high=a_high,
        a_low=a_low,
    )


def check_invariant_f(assumptions: list[Assumption], unknowns: list[Unknown]) -> list[str]:
    """Check Invariant F: No hidden assumptions for S2/S3 actions.

    Returns list of violation descriptions (empty = compliant).
    """
    violations: list[str] = []
    # All S2/S3 unknowns must have explicit assumptions or waivers
    s2s3 = [u for u in unknowns if u.severity in (Severity.S2, Severity.S3)]
    assumption_map = {a.unknown_id: a for a in assumptions}

    for u in s2s3:
        a = assumption_map.get(u.id)
        if not a:
            violations.append(
                f"Unknown {u.id} ({u.severity.value}) has no explicit assumption"
            )
        elif a.status == AssumptionStatus.ACTIVE and u.severity == Severity.S3:
            # S3 assumptions must be waived, not just active
            if not a.waiver_by:
                violations.append(
                    f"S3 assumption {a.id} for unknown {u.id} requires explicit waiver"
                )

    return violations


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class AdmissibilityStore:
    """Persistent store for admissibility state."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.admissibility_dir = self.governor_dir / "admissibility"

    def _ensure_dirs(self) -> None:
        self.admissibility_dir.mkdir(parents=True, exist_ok=True)

    def save_assessment(self, run_id: str, assessment: AdmissibilityAssessment) -> Path:
        """Save an assessment for a run."""
        self._ensure_dirs()
        path = self.admissibility_dir / f"{run_id}_assessment.json"
        path.write_text(json.dumps(assessment.to_dict(), indent=2) + "\n")
        return path

    def load_assessment(self, run_id: str) -> AdmissibilityAssessment | None:
        """Load an assessment for a run."""
        path = self.admissibility_dir / f"{run_id}_assessment.json"
        if not path.exists():
            return None
        try:
            return AdmissibilityAssessment.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def save_unknowns(self, run_id: str, unknowns: list[Unknown]) -> Path:
        """Save unknowns for a run."""
        self._ensure_dirs()
        path = self.admissibility_dir / f"{run_id}_unknowns.json"
        path.write_text(json.dumps([u.to_dict() for u in unknowns], indent=2) + "\n")
        return path

    def load_unknowns(self, run_id: str) -> list[Unknown]:
        """Load unknowns for a run."""
        path = self.admissibility_dir / f"{run_id}_unknowns.json"
        if not path.exists():
            return []
        try:
            return [Unknown.from_dict(d) for d in json.loads(path.read_text())]
        except (json.JSONDecodeError, KeyError):
            return []

    def save_assumptions(self, run_id: str, assumptions: list[Assumption]) -> Path:
        """Save assumptions for a run."""
        self._ensure_dirs()
        path = self.admissibility_dir / f"{run_id}_assumptions.json"
        path.write_text(json.dumps([a.to_dict() for a in assumptions], indent=2) + "\n")
        return path

    def load_assumptions(self, run_id: str) -> list[Assumption]:
        """Load assumptions for a run."""
        path = self.admissibility_dir / f"{run_id}_assumptions.json"
        if not path.exists():
            return []
        try:
            return [Assumption.from_dict(d) for d in json.loads(path.read_text())]
        except (json.JSONDecodeError, KeyError):
            return []

    def save_waivers(self, run_id: str, waivers: list[Waiver]) -> Path:
        """Save waivers for a run."""
        self._ensure_dirs()
        path = self.admissibility_dir / f"{run_id}_waivers.json"
        path.write_text(json.dumps([w.to_dict() for w in waivers], indent=2) + "\n")
        return path

    def load_waivers(self, run_id: str) -> list[Waiver]:
        """Load waivers for a run."""
        path = self.admissibility_dir / f"{run_id}_waivers.json"
        if not path.exists():
            return []
        try:
            return [Waiver.from_dict(d) for d in json.loads(path.read_text())]
        except (json.JSONDecodeError, KeyError):
            return []

    def list_runs(self) -> list[str]:
        """List run IDs that have assessments."""
        if not self.admissibility_dir.exists():
            return []
        runs = set()
        for f in self.admissibility_dir.glob("*_assessment.json"):
            runs.add(f.name.replace("_assessment.json", ""))
        return sorted(runs)


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_admissibility_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a telemetry event for admissibility actions."""
    return {
        "type": "admissibility",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
