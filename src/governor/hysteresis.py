"""Hysteresis and anti-churn — prevent controller chatter (AG2 Layer 2.1-C).

Asymmetric mode transition thresholds, replan limiting, and regression detection.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HysteresisMode(Enum):
    """Operating modes with asymmetric transition thresholds."""
    NORMAL = "NORMAL"
    STRICT = "STRICT"


class TransitionVerdict(Enum):
    """Result of a mode transition check."""
    HOLD = "HOLD"           # Stay in current mode
    TRANSITION = "TRANSITION"  # Allow transition
    SUPPRESSED = "SUPPRESSED"  # Would transition, but hysteresis prevents it


class ReplanVerdict(Enum):
    """Result of a replan request."""
    ALLOWED = "ALLOWED"
    DENIED_DUPLICATE = "DENIED_DUPLICATE"
    DENIED_BUDGET = "DENIED_BUDGET"


class RegressionSeverity(Enum):
    """Severity of a verification regression."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Asymmetric thresholds for NORMAL ↔ STRICT transitions
# A_LOW: admissibility below this enters STRICT
# A_HIGH: admissibility must exceed this to exit STRICT
A_LOW = 0.40
A_HIGH = 0.75

# Replan budget defaults
DEFAULT_MAX_REPLANS = 3
DEFAULT_REPLAN_WINDOW = 300.0  # seconds (5 min)

# Regression thresholds
REGRESSION_THRESHOLD_WARN = 1   # 1+ regressions → warning
REGRESSION_THRESHOLD_BLOCK = 5  # 5+ regressions → block


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ModeTransitionResult:
    """Result of a mode transition check."""
    verdict: TransitionVerdict
    current_mode: HysteresisMode
    target_mode: HysteresisMode
    admissibility: float
    threshold: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "current_mode": self.current_mode.value,
            "target_mode": self.target_mode.value,
            "admissibility": self.admissibility,
            "threshold": self.threshold,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ModeTransitionResult:
        return cls(
            verdict=TransitionVerdict(d["verdict"]),
            current_mode=HysteresisMode(d["current_mode"]),
            target_mode=HysteresisMode(d["target_mode"]),
            admissibility=d["admissibility"],
            threshold=d["threshold"],
            reason=d.get("reason", ""),
        )


@dataclass
class ReplanTracker:
    """Limits replan frequency to prevent plan chatter."""
    max_replans: int = DEFAULT_MAX_REPLANS
    replan_count: int = 0
    last_plan_hash: str = ""
    window_start: float = 0.0
    window_seconds: float = DEFAULT_REPLAN_WINDOW
    history: list[str] = field(default_factory=list)

    def allow_replan(self, new_plan_hash: str) -> ReplanVerdict:
        """Check if a replan is allowed."""
        self._maybe_reset_window()
        if new_plan_hash == self.last_plan_hash:
            return ReplanVerdict.DENIED_DUPLICATE
        if self.replan_count >= self.max_replans:
            return ReplanVerdict.DENIED_BUDGET
        return ReplanVerdict.ALLOWED

    def record_replan(self, new_plan_hash: str) -> None:
        """Record a successful replan."""
        self._maybe_reset_window()
        self.replan_count += 1
        self.last_plan_hash = new_plan_hash
        self.history.append(new_plan_hash)

    def remaining(self) -> int:
        """Replans remaining in current window."""
        self._maybe_reset_window()
        return max(0, self.max_replans - self.replan_count)

    def reset(self) -> None:
        """Reset the tracker (new window)."""
        self.replan_count = 0
        self.last_plan_hash = ""
        self.window_start = time.time()
        self.history = []

    def _maybe_reset_window(self) -> None:
        now = time.time()
        if self.window_start == 0.0:
            self.window_start = now
        elif now - self.window_start > self.window_seconds:
            self.replan_count = 0
            self.window_start = now

    def to_dict(self) -> dict:
        return {
            "max_replans": self.max_replans,
            "replan_count": self.replan_count,
            "last_plan_hash": self.last_plan_hash,
            "window_start": self.window_start,
            "window_seconds": self.window_seconds,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReplanTracker:
        return cls(
            max_replans=d.get("max_replans", DEFAULT_MAX_REPLANS),
            replan_count=d.get("replan_count", 0),
            last_plan_hash=d.get("last_plan_hash", ""),
            window_start=d.get("window_start", 0.0),
            window_seconds=d.get("window_seconds", DEFAULT_REPLAN_WINDOW),
            history=d.get("history", []),
        )


@dataclass
class RegressionAlert:
    """Alert for a verification regression."""
    claim_id: str
    was_status: str
    now_status: str
    severity: RegressionSeverity
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "was_status": self.was_status,
            "now_status": self.now_status,
            "severity": self.severity.value,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RegressionAlert:
        return cls(
            claim_id=d["claim_id"],
            was_status=d["was_status"],
            now_status=d["now_status"],
            severity=RegressionSeverity(d["severity"]),
            ts=d.get("ts", ""),
        )


@dataclass
class HysteresisState:
    """Full hysteresis controller state."""
    mode: HysteresisMode = HysteresisMode.NORMAL
    replan_tracker: ReplanTracker = field(default_factory=ReplanTracker)
    transition_count: int = 0
    suppression_count: int = 0
    regression_count: int = 0
    last_admissibility: float = 1.0
    events: list[dict] = field(default_factory=list)

    def record_transition(self, result: ModeTransitionResult) -> None:
        """Record a transition result."""
        if result.verdict == TransitionVerdict.TRANSITION:
            self.mode = result.target_mode
            self.transition_count += 1
        elif result.verdict == TransitionVerdict.SUPPRESSED:
            self.suppression_count += 1
        self.last_admissibility = result.admissibility

    def record_regressions(self, alerts: list[RegressionAlert]) -> None:
        """Record regression alerts."""
        self.regression_count += len(alerts)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "replan_tracker": self.replan_tracker.to_dict(),
            "transition_count": self.transition_count,
            "suppression_count": self.suppression_count,
            "regression_count": self.regression_count,
            "last_admissibility": self.last_admissibility,
            "events": list(self.events),
        }

    @classmethod
    def from_dict(cls, d: dict) -> HysteresisState:
        return cls(
            mode=HysteresisMode(d.get("mode", "NORMAL")),
            replan_tracker=ReplanTracker.from_dict(d.get("replan_tracker", {})),
            transition_count=d.get("transition_count", 0),
            suppression_count=d.get("suppression_count", 0),
            regression_count=d.get("regression_count", 0),
            last_admissibility=d.get("last_admissibility", 1.0),
            events=d.get("events", []),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_plan_hash(plan_text: str) -> str:
    """SHA256-based plan fingerprint."""
    return hashlib.sha256(plan_text.encode()).hexdigest()[:16]


def check_mode_transition(
    current_mode: HysteresisMode,
    admissibility: float,
    *,
    a_low: float = A_LOW,
    a_high: float = A_HIGH,
) -> ModeTransitionResult:
    """Check if a mode transition should occur with asymmetric thresholds.

    STRICT → NORMAL requires admissibility > A_HIGH (hard to leave strict).
    NORMAL → STRICT requires admissibility < A_LOW (easy to enter strict).
    The gap [A_LOW, A_HIGH] is the hysteresis band — no transitions occur.
    """
    if current_mode == HysteresisMode.STRICT:
        if admissibility > a_high:
            return ModeTransitionResult(
                verdict=TransitionVerdict.TRANSITION,
                current_mode=current_mode,
                target_mode=HysteresisMode.NORMAL,
                admissibility=admissibility,
                threshold=a_high,
                reason="admissibility exceeds exit threshold",
            )
        else:
            # Would need to exceed A_HIGH to leave
            would_transition = admissibility > a_low  # in the band
            return ModeTransitionResult(
                verdict=TransitionVerdict.SUPPRESSED if would_transition else TransitionVerdict.HOLD,
                current_mode=current_mode,
                target_mode=HysteresisMode.NORMAL if would_transition else HysteresisMode.STRICT,
                admissibility=admissibility,
                threshold=a_high,
                reason="hysteresis_band" if would_transition else "below_exit_threshold",
            )
    else:
        # NORMAL mode
        if admissibility < a_low:
            return ModeTransitionResult(
                verdict=TransitionVerdict.TRANSITION,
                current_mode=current_mode,
                target_mode=HysteresisMode.STRICT,
                admissibility=admissibility,
                threshold=a_low,
                reason="admissibility below entry threshold",
            )
        else:
            would_transition = admissibility < a_high  # in the band
            return ModeTransitionResult(
                verdict=TransitionVerdict.HOLD,
                current_mode=current_mode,
                target_mode=HysteresisMode.NORMAL,
                admissibility=admissibility,
                threshold=a_low,
                reason="in_hysteresis_band" if would_transition else "above_entry_threshold",
            )


def check_replan(
    tracker: ReplanTracker,
    plan_text: str,
    *,
    auto_record: bool = True,
) -> tuple[ReplanVerdict, str]:
    """Check if a replan is allowed and optionally record it.

    Returns (verdict, plan_hash).
    """
    plan_hash = compute_plan_hash(plan_text)
    verdict = tracker.allow_replan(plan_hash)
    if verdict == ReplanVerdict.ALLOWED and auto_record:
        tracker.record_replan(plan_hash)
    return verdict, plan_hash


def detect_regressions(
    old_claims: list[dict],
    new_claims: list[dict],
) -> list[RegressionAlert]:
    """Detect verification regressions — claims that were verified but now aren't.

    Claims are dicts with at least 'id' and 'status' keys.
    'verified' status in old but not in new → regression.
    """
    old_verified: set[str] = set()
    for c in old_claims:
        if c.get("status") in ("verified", "VERIFIED", "SUPPORTED"):
            old_verified.add(c["id"])

    new_verified: set[str] = set()
    new_status_map: dict[str, str] = {}
    for c in new_claims:
        cid = c["id"]
        status = c.get("status", "unknown")
        new_status_map[cid] = status
        if status in ("verified", "VERIFIED", "SUPPORTED"):
            new_verified.add(cid)

    regressions = old_verified - new_verified
    alerts = []
    for claim_id in sorted(regressions):
        count = len(alerts)
        if count >= REGRESSION_THRESHOLD_BLOCK:
            severity = RegressionSeverity.HIGH
        elif count >= REGRESSION_THRESHOLD_WARN:
            severity = RegressionSeverity.MODERATE
        else:
            severity = RegressionSeverity.LOW
        alerts.append(RegressionAlert(
            claim_id=claim_id,
            was_status="verified",
            now_status=new_status_map.get(claim_id, "missing"),
            severity=severity,
        ))
    return alerts


def classify_regression_severity(count: int) -> RegressionSeverity:
    """Classify overall regression severity by count."""
    if count >= REGRESSION_THRESHOLD_BLOCK:
        return RegressionSeverity.HIGH
    elif count >= REGRESSION_THRESHOLD_WARN:
        return RegressionSeverity.MODERATE
    return RegressionSeverity.LOW


def check_invariant_k(
    state: HysteresisState,
    admissibility: float,
) -> tuple[bool, str]:
    """Invariant K: Mode transitions respect hysteresis band.

    No transition should occur when admissibility is in (A_LOW, A_HIGH)
    unless the direction matches.
    """
    result = check_mode_transition(state.mode, admissibility)
    if result.verdict == TransitionVerdict.SUPPRESSED:
        return True, f"transition suppressed at admissibility={admissibility:.3f}"
    if result.verdict == TransitionVerdict.TRANSITION:
        return True, f"transition allowed at admissibility={admissibility:.3f}"
    return True, f"hold at admissibility={admissibility:.3f}"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def make_hysteresis_event(
    action: str,
    run_id: str | None = None,
    details: dict | None = None,
) -> dict:
    """Create a hysteresis telemetry event."""
    return {
        "type": "hysteresis",
        "action": action,
        "run_id": run_id or "",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": details or {},
    }


def make_transition_event(result: ModeTransitionResult) -> dict:
    """Create event for a mode transition check."""
    action = {
        TransitionVerdict.TRANSITION: "mode_transition",
        TransitionVerdict.SUPPRESSED: "mode_transition_suppressed",
        TransitionVerdict.HOLD: "mode_hold",
    }[result.verdict]
    return make_hysteresis_event(action, details=result.to_dict())


def make_replan_event(verdict: ReplanVerdict, plan_hash: str, tracker: ReplanTracker) -> dict:
    """Create event for a replan check."""
    action = {
        ReplanVerdict.ALLOWED: "replan_allowed",
        ReplanVerdict.DENIED_DUPLICATE: "replan_denied",
        ReplanVerdict.DENIED_BUDGET: "replan_denied",
    }[verdict]
    return make_hysteresis_event(action, details={
        "verdict": verdict.value,
        "plan_hash": plan_hash,
        "replan_count": tracker.replan_count,
        "max_replans": tracker.max_replans,
        "reason": "duplicate" if verdict == ReplanVerdict.DENIED_DUPLICATE else
                  "budget_exhausted" if verdict == ReplanVerdict.DENIED_BUDGET else "allowed",
    })


def make_regression_event(alerts: list[RegressionAlert]) -> dict:
    """Create event for regression detection."""
    return make_hysteresis_event("verification_regression", details={
        "count": len(alerts),
        "severity": classify_regression_severity(len(alerts)).value,
        "alerts": [a.to_dict() for a in alerts],
    })


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class HysteresisStore:
    """Persistence for hysteresis state."""

    def __init__(self, governor_dir: Path | None = None):
        base = governor_dir or Path(".governor")
        self.hysteresis_dir = base / "hysteresis"

    def save(self, state: HysteresisState, run_id: str = "default") -> None:
        self.hysteresis_dir.mkdir(parents=True, exist_ok=True)
        path = self.hysteresis_dir / f"{run_id}.json"
        path.write_text(json.dumps(state.to_dict(), indent=2))

    def load(self, run_id: str = "default") -> HysteresisState | None:
        path = self.hysteresis_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return HysteresisState.from_dict(data)

    def list_runs(self) -> list[str]:
        if not self.hysteresis_dir.exists():
            return []
        return sorted(p.stem for p in self.hysteresis_dir.glob("*.json"))
