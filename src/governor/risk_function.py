# SPDX-License-Identifier: Apache-2.0
"""
Risk Potential Function — Scalar Risk V.

V(x̂_t) = α₁·untrusted + α₂·scope + α₃·irrev + α₄·evidence_gap + α₅·anomaly.
Lyapunov-ish monotone control signal that drives mode tightening and tool gating.
Risk-driven policy: profile demotion, tool freezing, evidence threshold increase.

Spec: RISK_FUNCTION_SPEC (Layer 2.1-B)
Relationship to R_t: V is accumulated run-level risk; R_t is per-step risk index.
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

class RiskLevel(str, Enum):
    """Risk level classification."""
    LOW = "low"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyAction(str, Enum):
    """Actions taken by risk-driven policy."""
    NONE = "none"
    INCREASE_EVIDENCE = "increase_evidence"
    FREEZE_IRREVERSIBLE = "freeze_irreversible"
    DEMOTE_PROFILE = "demote_profile"
    FREEZE_ALL_SIDE_EFFECTS = "freeze_all_side_effects"


class RiskSignal(str, Enum):
    """Individual risk signal types."""
    UNTRUSTED_BLOB = "untrusted_blob"
    SCOPE_SIZE = "scope_size"
    IRREVERSIBILITY = "irreversibility"
    EVIDENCE_GAP = "evidence_gap"
    ANOMALY = "anomaly"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default risk weights (α₁ through α₅)
DEFAULT_WEIGHTS = {
    RiskSignal.UNTRUSTED_BLOB: 0.25,
    RiskSignal.SCOPE_SIZE: 0.15,
    RiskSignal.IRREVERSIBILITY: 0.25,
    RiskSignal.EVIDENCE_GAP: 0.20,
    RiskSignal.ANOMALY: 0.15,
}

# Risk thresholds
RISK_THRESHOLD_ELEVATED = 0.35
RISK_THRESHOLD_HIGH = 0.60
RISK_THRESHOLD_CRITICAL = 0.85

# Evidence multiplier on elevated risk
EVIDENCE_MULTIPLIER = 1.5

# Irreversible tool set (frozen at HIGH)
IRREVERSIBLE_TOOLS = frozenset({
    "execute", "write_file", "delete", "deploy", "send_email",
})

# Side-effect tools (frozen at CRITICAL)
SIDE_EFFECT_TOOLS = frozenset({
    "execute", "write_file", "delete", "deploy", "send_email",
    "modify", "create",
})

# Profile demotion order (strictest to loosest)
DEMOTION_ORDER = ["public", "autonomous", "delegated", "operator"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RiskWeights:
    """Weights for risk components."""
    untrusted: float = 0.25
    scope: float = 0.15
    irreversibility: float = 0.25
    evidence: float = 0.20
    anomaly: float = 0.15

    def to_dict(self) -> dict[str, float]:
        return {
            "untrusted": self.untrusted,
            "scope": self.scope,
            "irreversibility": self.irreversibility,
            "evidence": self.evidence,
            "anomaly": self.anomaly,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskWeights:
        return cls(
            untrusted=d.get("untrusted", 0.25),
            scope=d.get("scope", 0.15),
            irreversibility=d.get("irreversibility", 0.25),
            evidence=d.get("evidence", 0.20),
            anomaly=d.get("anomaly", 0.15),
        )


@dataclass
class RiskComponents:
    """Individual risk signal values (each in [0, 1])."""
    untrusted_blob_use: float = 0.0
    scope_size: float = 0.0
    irreversibility_intent: float = 0.0
    evidence_gap: float = 0.0
    anomaly_score: float = 0.0

    def __post_init__(self) -> None:
        for name in ("untrusted_blob_use", "scope_size", "irreversibility_intent",
                      "evidence_gap", "anomaly_score"):
            val = getattr(self, name)
            setattr(self, name, max(0.0, min(1.0, val)))

    def to_dict(self) -> dict[str, float]:
        return {
            "untrusted_blob_use": self.untrusted_blob_use,
            "scope_size": self.scope_size,
            "irreversibility_intent": self.irreversibility_intent,
            "evidence_gap": self.evidence_gap,
            "anomaly_score": self.anomaly_score,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskComponents:
        return cls(
            untrusted_blob_use=d.get("untrusted_blob_use", 0.0),
            scope_size=d.get("scope_size", 0.0),
            irreversibility_intent=d.get("irreversibility_intent", 0.0),
            evidence_gap=d.get("evidence_gap", 0.0),
            anomaly_score=d.get("anomaly_score", 0.0),
        )


@dataclass
class RiskAssessment:
    """A risk assessment with components, level, and applied policy."""
    run_id: str
    components: RiskComponents
    weights: RiskWeights
    risk_value: float = 0.0
    level: RiskLevel = RiskLevel.LOW
    actions_taken: list[PolicyAction] = field(default_factory=list)
    frozen_tools: set[str] = field(default_factory=set)
    demoted_to: str = ""
    evidence_multiplier: float = 1.0
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()
        if self.risk_value == 0.0:
            self.risk_value = compute_risk(self.components, self.weights)
        if self.level == RiskLevel.LOW:
            self.level = classify_risk(self.risk_value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "components": self.components.to_dict(),
            "weights": self.weights.to_dict(),
            "risk_value": round(self.risk_value, 6),
            "level": self.level.value,
            "actions_taken": [a.value for a in self.actions_taken],
            "frozen_tools": sorted(self.frozen_tools),
            "demoted_to": self.demoted_to,
            "evidence_multiplier": self.evidence_multiplier,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskAssessment:
        return cls(
            run_id=d["run_id"],
            components=RiskComponents.from_dict(d.get("components", {})),
            weights=RiskWeights.from_dict(d.get("weights", {})),
            risk_value=d.get("risk_value", 0.0),
            level=RiskLevel(d.get("level", "low")),
            actions_taken=[PolicyAction(a) for a in d.get("actions_taken", [])],
            frozen_tools=set(d.get("frozen_tools", [])),
            demoted_to=d.get("demoted_to", ""),
            evidence_multiplier=d.get("evidence_multiplier", 1.0),
            ts=d.get("ts", ""),
        )


@dataclass
class ThresholdCrossing:
    """Record of a risk threshold being crossed."""
    run_id: str
    previous_level: RiskLevel
    new_level: RiskLevel
    risk_value: float
    actions: list[PolicyAction]
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "previous_level": self.previous_level.value,
            "new_level": self.new_level.value,
            "risk_value": round(self.risk_value, 6),
            "actions": [a.value for a in self.actions],
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ThresholdCrossing:
        return cls(
            run_id=d["run_id"],
            previous_level=RiskLevel(d["previous_level"]),
            new_level=RiskLevel(d["new_level"]),
            risk_value=d.get("risk_value", 0.0),
            actions=[PolicyAction(a) for a in d.get("actions", [])],
            ts=d.get("ts", ""),
        )


@dataclass
class RiskState:
    """Accumulated risk state for a run."""
    run_id: str
    current_level: RiskLevel = RiskLevel.LOW
    current_risk: float = 0.0
    assessments: list[RiskAssessment] = field(default_factory=list)
    crossings: list[ThresholdCrossing] = field(default_factory=list)
    frozen_tools: set[str] = field(default_factory=set)
    active_profile: str = "operator"
    evidence_multiplier: float = 1.0
    peak_risk: float = 0.0

    def update(self, assessment: RiskAssessment) -> ThresholdCrossing | None:
        """Apply an assessment to the state. Returns crossing if threshold changed."""
        prev_level = self.current_level
        self.current_risk = assessment.risk_value
        self.current_level = assessment.level
        self.peak_risk = max(self.peak_risk, assessment.risk_value)
        self.assessments.append(assessment)

        # Apply policy effects
        self.frozen_tools |= assessment.frozen_tools
        if assessment.demoted_to:
            idx_current = _demotion_index(self.active_profile)
            idx_new = _demotion_index(assessment.demoted_to)
            if idx_new < idx_current:
                self.active_profile = assessment.demoted_to
        self.evidence_multiplier = max(self.evidence_multiplier, assessment.evidence_multiplier)

        if assessment.level != prev_level:
            crossing = ThresholdCrossing(
                run_id=self.run_id,
                previous_level=prev_level,
                new_level=assessment.level,
                risk_value=assessment.risk_value,
                actions=assessment.actions_taken,
            )
            self.crossings.append(crossing)
            return crossing
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_level": self.current_level.value,
            "current_risk": round(self.current_risk, 6),
            "frozen_tools": sorted(self.frozen_tools),
            "active_profile": self.active_profile,
            "evidence_multiplier": self.evidence_multiplier,
            "peak_risk": round(self.peak_risk, 6),
            "assessment_count": len(self.assessments),
            "crossing_count": len(self.crossings),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskState:
        return cls(
            run_id=d["run_id"],
            current_level=RiskLevel(d.get("current_level", "low")),
            current_risk=d.get("current_risk", 0.0),
            frozen_tools=set(d.get("frozen_tools", [])),
            active_profile=d.get("active_profile", "operator"),
            evidence_multiplier=d.get("evidence_multiplier", 1.0),
            peak_risk=d.get("peak_risk", 0.0),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_risk(components: RiskComponents, weights: RiskWeights | None = None) -> float:
    """Compute scalar risk V from weighted components."""
    w = weights or RiskWeights()
    v = (
        w.untrusted * components.untrusted_blob_use
        + w.scope * components.scope_size
        + w.irreversibility * components.irreversibility_intent
        + w.evidence * components.evidence_gap
        + w.anomaly * components.anomaly_score
    )
    return max(0.0, min(1.0, v))


def classify_risk(risk_value: float) -> RiskLevel:
    """Classify risk value into a level."""
    if risk_value >= RISK_THRESHOLD_CRITICAL:
        return RiskLevel.CRITICAL
    if risk_value >= RISK_THRESHOLD_HIGH:
        return RiskLevel.HIGH
    if risk_value >= RISK_THRESHOLD_ELEVATED:
        return RiskLevel.ELEVATED
    return RiskLevel.LOW


def apply_risk_policy(
    risk_value: float,
    level: RiskLevel | None = None,
) -> tuple[list[PolicyAction], set[str], str, float]:
    """Determine policy actions from risk level.

    Returns: (actions, frozen_tools, demoted_to, evidence_multiplier)
    """
    lvl = level or classify_risk(risk_value)
    actions: list[PolicyAction] = []
    frozen: set[str] = set()
    demoted = ""
    ev_mult = 1.0

    if lvl == RiskLevel.CRITICAL:
        actions.append(PolicyAction.DEMOTE_PROFILE)
        actions.append(PolicyAction.FREEZE_ALL_SIDE_EFFECTS)
        frozen = set(SIDE_EFFECT_TOOLS)
        demoted = "public"
        ev_mult = EVIDENCE_MULTIPLIER
    elif lvl == RiskLevel.HIGH:
        actions.append(PolicyAction.FREEZE_IRREVERSIBLE)
        frozen = set(IRREVERSIBLE_TOOLS)
        ev_mult = EVIDENCE_MULTIPLIER
    elif lvl == RiskLevel.ELEVATED:
        actions.append(PolicyAction.INCREASE_EVIDENCE)
        ev_mult = EVIDENCE_MULTIPLIER

    if not actions:
        actions.append(PolicyAction.NONE)

    return actions, frozen, demoted, ev_mult


def assess_risk(
    run_id: str,
    components: RiskComponents,
    weights: RiskWeights | None = None,
) -> RiskAssessment:
    """Full risk assessment: compute V, classify, determine policy."""
    w = weights or RiskWeights()
    v = compute_risk(components, w)
    lvl = classify_risk(v)
    actions, frozen, demoted, ev_mult = apply_risk_policy(v, lvl)

    return RiskAssessment(
        run_id=run_id,
        components=components,
        weights=w,
        risk_value=v,
        level=lvl,
        actions_taken=actions,
        frozen_tools=frozen,
        demoted_to=demoted,
        evidence_multiplier=ev_mult,
    )


def _demotion_index(profile_name: str) -> int:
    """Lower index = stricter profile."""
    try:
        return DEMOTION_ORDER.index(profile_name)
    except ValueError:
        return len(DEMOTION_ORDER)


# ---------------------------------------------------------------------------
# Signal extraction helpers
# ---------------------------------------------------------------------------

def extract_untrusted_signal(
    untrusted_count: int, quarantined_count: int, total_outputs: int
) -> float:
    """Extract untrusted blob signal from measurement integrity state."""
    if total_outputs == 0:
        return 0.0
    return min(1.0, (untrusted_count + 2 * quarantined_count) / max(total_outputs, 1))


def extract_evidence_gap(coverage: float) -> float:
    """Extract evidence gap from metrics coverage (1 - coverage)."""
    return max(0.0, min(1.0, 1.0 - coverage))


def extract_scope_signal(
    active_tools: int, total_tools: int, has_wildcard: bool
) -> float:
    """Extract scope size signal from deployment profile."""
    if has_wildcard:
        return 0.8
    if total_tools == 0:
        return 0.0
    return min(1.0, active_tools / max(total_tools, 1))


def extract_irreversibility_signal(
    pending_proposals: int, s3_actions: int, s2_actions: int
) -> float:
    """Extract irreversibility intent from action history."""
    score = 0.0
    score += min(0.5, s3_actions * 0.25)
    score += min(0.3, s2_actions * 0.1)
    score += min(0.2, pending_proposals * 0.1)
    return min(1.0, score)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class RiskStore:
    """Persistent store for risk state."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.risk_dir = self.governor_dir / "risk"

    def _ensure_dirs(self) -> None:
        self.risk_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: RiskState) -> Path:
        self._ensure_dirs()
        path = self.risk_dir / f"{state.run_id}.json"
        data = state.to_dict()
        # Include full assessments and crossings in stored form
        data["assessments"] = [a.to_dict() for a in state.assessments]
        data["crossings"] = [c.to_dict() for c in state.crossings]
        path.write_text(json.dumps(data, indent=2) + "\n")
        return path

    def load(self, run_id: str) -> RiskState | None:
        path = self.risk_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text())
            state = RiskState.from_dict(d)
            state.assessments = [
                RiskAssessment.from_dict(a) for a in d.get("assessments", [])
            ]
            state.crossings = [
                ThresholdCrossing.from_dict(c) for c in d.get("crossings", [])
            ]
            return state
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.risk_dir.exists():
            return []
        return sorted(f.stem for f in self.risk_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_risk_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "risk_function",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
