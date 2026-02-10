"""
Phase Control System — Run Phases with Budget Locks and Novelty Debt.

Agent runs as controlled processes: SPECIFY → EXPLORE → DRAFT → VERIFY → COMMIT.
Bell lap insight: lock B_verify until VERIFY phase.
Novelty debt caps confidence for late scope changes.

Spec: PHASE_CONTROL_SPEC (Layer 2.1-A)
Invariant G: B_verify is inaccessible until phase ≥ VERIFY.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Phase(IntEnum):
    """Run phases in sequence. IntEnum enables ordering (SPECIFY < EXPLORE < ...)."""
    SPECIFY = 0
    EXPLORE = 1
    DRAFT = 2
    VERIFY = 3
    COMMIT = 4


class TransitionResult(str, Enum):
    """Result of a phase transition attempt."""
    ADVANCED = "advanced"
    BLOCKED = "blocked"
    ALREADY_THERE = "already_there"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_EXPLORE_BUDGET = 20
DEFAULT_DRAFT_BUDGET = 15
DEFAULT_VERIFY_BUDGET = 10

# Admissibility threshold for SPECIFY → EXPLORE
A_MIN = 0.4

# Coverage threshold for VERIFY → COMMIT
COVERAGE_THRESHOLD = 0.8

# Novelty debt coefficient
LAMBDA_NOVELTY = 1.0

# Confidence cap reduction per unit novelty
ALPHA_NOVELTY = 0.1

# Maximum confidence
Q_MAX = 1.0

# Re-verification trigger threshold
REVERIFY_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PhaseBudget:
    """Budget allocation across phases."""
    explore: int = DEFAULT_EXPLORE_BUDGET
    draft: int = DEFAULT_DRAFT_BUDGET
    verify: int = DEFAULT_VERIFY_BUDGET

    @property
    def total(self) -> int:
        return self.explore + self.draft + self.verify

    def available(self, phase: Phase) -> int:
        """Get budget available for the given phase.

        Invariant G: verify budget only accessible in VERIFY phase.
        """
        if phase == Phase.VERIFY:
            return self.verify
        elif phase == Phase.DRAFT:
            return self.draft
        elif phase == Phase.EXPLORE:
            return self.explore
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "explore": self.explore,
            "draft": self.draft,
            "verify": self.verify,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PhaseBudget:
        return cls(
            explore=d.get("explore", DEFAULT_EXPLORE_BUDGET),
            draft=d.get("draft", DEFAULT_DRAFT_BUDGET),
            verify=d.get("verify", DEFAULT_VERIFY_BUDGET),
        )


@dataclass
class PhaseUsage:
    """Tracks actions consumed per phase."""
    explore_used: int = 0
    draft_used: int = 0
    verify_used: int = 0

    def used(self, phase: Phase) -> int:
        if phase == Phase.EXPLORE:
            return self.explore_used
        elif phase == Phase.DRAFT:
            return self.draft_used
        elif phase == Phase.VERIFY:
            return self.verify_used
        return 0

    def consume(self, phase: Phase, count: int = 1) -> None:
        if phase == Phase.EXPLORE:
            self.explore_used += count
        elif phase == Phase.DRAFT:
            self.draft_used += count
        elif phase == Phase.VERIFY:
            self.verify_used += count

    def remaining(self, budget: PhaseBudget, phase: Phase) -> int:
        return max(0, budget.available(phase) - self.used(phase))

    def to_dict(self) -> dict[str, Any]:
        return {
            "explore_used": self.explore_used,
            "draft_used": self.draft_used,
            "verify_used": self.verify_used,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PhaseUsage:
        return cls(
            explore_used=d.get("explore_used", 0),
            draft_used=d.get("draft_used", 0),
            verify_used=d.get("verify_used", 0),
        )


@dataclass
class NoveltyDebt:
    """Tracks novelty debt accumulated after entering VERIFY phase."""
    total: float = 0.0
    changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def confidence_cap(self) -> float:
        """Maximum confidence under current novelty debt."""
        return max(0.0, Q_MAX - ALPHA_NOVELTY * self.total)

    @property
    def needs_reverification(self) -> bool:
        """Check if accumulated novelty exceeds reverification threshold."""
        return self.total > REVERIFY_THRESHOLD

    def record_change(self, distance: float, description: str = "") -> None:
        """Record a scope change and accumulate debt."""
        debt_increment = LAMBDA_NOVELTY * distance
        self.total += debt_increment
        self.changes.append({
            "distance": distance,
            "debt_increment": debt_increment,
            "total_after": self.total,
            "description": description,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "confidence_cap": self.confidence_cap,
            "needs_reverification": self.needs_reverification,
            "changes": self.changes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NoveltyDebt:
        nd = cls(
            total=d.get("total", 0.0),
            changes=d.get("changes", []),
        )
        return nd


@dataclass
class RunState:
    """State required for phase transition decisions."""
    admissibility: float = 0.0
    candidates_generated: int = 0
    artifact_exists: bool = False
    coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "admissibility": self.admissibility,
            "candidates_generated": self.candidates_generated,
            "artifact_exists": self.artifact_exists,
            "coverage": self.coverage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunState:
        return cls(
            admissibility=d.get("admissibility", 0.0),
            candidates_generated=d.get("candidates_generated", 0),
            artifact_exists=d.get("artifact_exists", False),
            coverage=d.get("coverage", 0.0),
        )


@dataclass
class PhaseTransitionEvent:
    """Record of a phase transition."""
    from_phase: Phase
    to_phase: Phase
    result: TransitionResult
    reason: str
    budget_remaining: dict[str, int] = field(default_factory=dict)
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_phase": self.from_phase.name,
            "to_phase": self.to_phase.name,
            "result": self.result.value,
            "reason": self.reason,
            "budget_remaining": self.budget_remaining,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PhaseTransitionEvent:
        return cls(
            from_phase=Phase[d["from_phase"]],
            to_phase=Phase[d["to_phase"]],
            result=TransitionResult(d["result"]),
            reason=d.get("reason", ""),
            budget_remaining=d.get("budget_remaining", {}),
            ts=d.get("ts", ""),
        )


# ---------------------------------------------------------------------------
# Phase transition logic
# ---------------------------------------------------------------------------

def can_advance(current: Phase, state: RunState) -> tuple[bool, str]:
    """Check if transition to next phase is allowed.

    Returns (allowed, reason).
    """
    if current == Phase.SPECIFY:
        if state.admissibility >= A_MIN:
            return True, "admissibility sufficient"
        return False, f"admissibility {state.admissibility:.2f} < {A_MIN}"

    elif current == Phase.EXPLORE:
        if state.candidates_generated > 0:
            return True, "candidates generated"
        return False, "no candidates generated"

    elif current == Phase.DRAFT:
        if state.artifact_exists:
            return True, "artifact exists"
        return False, "no artifact produced"

    elif current == Phase.VERIFY:
        if state.coverage >= COVERAGE_THRESHOLD:
            return True, "coverage threshold met"
        return False, f"coverage {state.coverage:.2f} < {COVERAGE_THRESHOLD}"

    elif current == Phase.COMMIT:
        return True, "terminal phase"

    return False, "unknown phase"


def check_budget(phase: Phase, budget: PhaseBudget, usage: PhaseUsage) -> bool:
    """Check if there's budget remaining for an action in this phase."""
    return usage.remaining(budget, phase) > 0


def check_invariant_g(phase: Phase, budget: PhaseBudget) -> bool:
    """Check Invariant G: B_verify inaccessible before VERIFY.

    Returns True if the invariant holds (verify budget is properly locked).
    """
    if phase < Phase.VERIFY:
        # Verify budget should not be accessible
        return budget.available(phase) != budget.verify or budget.verify == 0
    return True


# ---------------------------------------------------------------------------
# PhaseController — run-level controller
# ---------------------------------------------------------------------------

@dataclass
class PhaseController:
    """Controls phase transitions and budget consumption for a run."""
    run_id: str
    phase: Phase = Phase.SPECIFY
    budget: PhaseBudget = field(default_factory=PhaseBudget)
    usage: PhaseUsage = field(default_factory=PhaseUsage)
    state: RunState = field(default_factory=RunState)
    novelty: NoveltyDebt = field(default_factory=NoveltyDebt)
    history: list[PhaseTransitionEvent] = field(default_factory=list)

    def advance(self) -> PhaseTransitionEvent:
        """Attempt to advance to the next phase."""
        if self.phase == Phase.COMMIT:
            evt = PhaseTransitionEvent(
                from_phase=self.phase, to_phase=self.phase,
                result=TransitionResult.ALREADY_THERE,
                reason="already at terminal phase",
            )
            self.history.append(evt)
            return evt

        next_phase = Phase(self.phase + 1)
        allowed, reason = can_advance(self.phase, self.state)

        if allowed:
            evt = PhaseTransitionEvent(
                from_phase=self.phase, to_phase=next_phase,
                result=TransitionResult.ADVANCED,
                reason=reason,
                budget_remaining={
                    "explore": self.usage.remaining(self.budget, Phase.EXPLORE),
                    "draft": self.usage.remaining(self.budget, Phase.DRAFT),
                    "verify": self.usage.remaining(self.budget, Phase.VERIFY),
                },
            )
            self.phase = next_phase
            self.history.append(evt)
            return evt
        else:
            evt = PhaseTransitionEvent(
                from_phase=self.phase, to_phase=next_phase,
                result=TransitionResult.BLOCKED,
                reason=reason,
            )
            self.history.append(evt)
            return evt

    def consume_action(self, count: int = 1) -> bool:
        """Consume an action from the current phase budget.

        Returns True if action was allowed, False if budget exhausted.
        """
        if not check_budget(self.phase, self.budget, self.usage):
            return False
        self.usage.consume(self.phase, count)
        return True

    def force_advance(self, reason: str = "budget exhausted") -> PhaseTransitionEvent:
        """Force transition to next phase (e.g., when budget exhausted)."""
        if self.phase == Phase.COMMIT:
            evt = PhaseTransitionEvent(
                from_phase=self.phase, to_phase=self.phase,
                result=TransitionResult.ALREADY_THERE,
                reason="already at terminal phase",
            )
            self.history.append(evt)
            return evt

        next_phase = Phase(self.phase + 1)
        evt = PhaseTransitionEvent(
            from_phase=self.phase, to_phase=next_phase,
            result=TransitionResult.ADVANCED,
            reason=f"forced: {reason}",
        )
        self.phase = next_phase
        self.history.append(evt)
        return evt

    def record_novelty(self, distance: float, description: str = "") -> None:
        """Record a scope change (only meaningful in VERIFY+ phases)."""
        if self.phase >= Phase.VERIFY:
            self.novelty.record_change(distance, description)

    @property
    def confidence_cap(self) -> float:
        """Current confidence cap (affected by novelty debt)."""
        return self.novelty.confidence_cap

    @property
    def budget_remaining(self) -> dict[str, int]:
        return {
            "explore": self.usage.remaining(self.budget, Phase.EXPLORE),
            "draft": self.usage.remaining(self.budget, Phase.DRAFT),
            "verify": self.usage.remaining(self.budget, Phase.VERIFY),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self.phase.name,
            "budget": self.budget.to_dict(),
            "usage": self.usage.to_dict(),
            "state": self.state.to_dict(),
            "novelty": self.novelty.to_dict(),
            "history": [e.to_dict() for e in self.history],
            "confidence_cap": self.confidence_cap,
            "budget_remaining": self.budget_remaining,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PhaseController:
        return cls(
            run_id=d["run_id"],
            phase=Phase[d["phase"]],
            budget=PhaseBudget.from_dict(d.get("budget", {})),
            usage=PhaseUsage.from_dict(d.get("usage", {})),
            state=RunState.from_dict(d.get("state", {})),
            novelty=NoveltyDebt.from_dict(d.get("novelty", {})),
            history=[PhaseTransitionEvent.from_dict(e) for e in d.get("history", [])],
        )


# ---------------------------------------------------------------------------
# PhaseStore — persistence
# ---------------------------------------------------------------------------

class PhaseStore:
    """Persistent store for phase controllers."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.phase_dir = self.governor_dir / "phases"

    def _ensure_dirs(self) -> None:
        self.phase_dir.mkdir(parents=True, exist_ok=True)

    def save(self, controller: PhaseController) -> Path:
        self._ensure_dirs()
        path = self.phase_dir / f"{controller.run_id}.json"
        path.write_text(json.dumps(controller.to_dict(), indent=2) + "\n")
        return path

    def load(self, run_id: str) -> PhaseController | None:
        path = self.phase_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return PhaseController.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.phase_dir.exists():
            return []
        return sorted(f.stem for f in self.phase_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_phase_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "phase_control",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
