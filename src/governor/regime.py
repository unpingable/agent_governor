# SPDX-License-Identifier: Apache-2.0
"""
Regime Detection: Health monitoring for the governor system.

Classifies system state into operational regimes based on observable signals.
This is NOT "is the agent scheming?" - it's "is the system still in an
identifiable regime where our invariants hold?"

Regimes:
- ELASTIC: Stable, identifiable, normal operation
- WARM: Drifting but recoverable, tighten constraints
- DUCTILE: Path dependent, probing is intervention, reset required
- UNSTABLE: Positive feedback, cascade detected, emergency stop

Key insight: We don't probe intent, we observe dynamics.

Toggle via config.toml:
    [epistemic]
    regime_detection = true
    regime_auto_response = false  # Just detect, don't auto-respond
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any
import json


# =============================================================================
# Operational Regimes
# =============================================================================


class OperationalRegime(str, Enum):
    """System operational regimes."""

    ELASTIC = "elastic"
    """Stable, identifiable. Normal operation."""

    WARM = "warm"
    """Drifting but recoverable. Tighten constraints."""

    DUCTILE = "ductile"
    """Path dependent, probing is intervention. Reset needed."""

    UNSTABLE = "unstable"
    """Positive feedback cascade. Emergency stop."""

    @property
    def allowed_action_classes(self) -> frozenset["ActionClass"]:
        """Action classes permitted in this regime."""
        return _REGIME_ACTION_CLASSES[self]

    @property
    def severity(self) -> int:
        """Severity level (higher = worse)."""
        return {
            OperationalRegime.ELASTIC: 0,
            OperationalRegime.WARM: 1,
            OperationalRegime.DUCTILE: 2,
            OperationalRegime.UNSTABLE: 3,
        }[self]

    @property
    def recommended_action(self) -> str:
        """Recommended action for this regime."""
        return {
            OperationalRegime.ELASTIC: "CONTINUE",
            OperationalRegime.WARM: "TIGHTEN",
            OperationalRegime.DUCTILE: "RESET",
            OperationalRegime.UNSTABLE: "EMERGENCY_STOP",
        }[self]


# =============================================================================
# Action Classification (3.x seam — what kind of action is this?)
# =============================================================================


class ActionClass(str, Enum):
    """Classification of governor actions for regime-gated admission."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    CONFIGURE = "configure"
    RESET = "reset"
    STATUS = "status"
    RECOVERY_SUBMIT = "recovery_submit"


class DenyReason(str, Enum):
    """Why an action was denied. Append-only — never rename existing codes."""

    REGIME_RESTRICTED = "regime_restricted"
    LOCKED_ROUTE = "locked_route"
    STALE_SNAPSHOT = "stale_snapshot"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SCOPE_VIOLATION = "scope_violation"
    CAPTURE_DETECTED = "capture_detected"


class ResetReason(str, Enum):
    """Why a reset was initiated. Append-only — never rename existing codes."""

    OPERATOR_REQUEST = "operator_request"
    RECOVERY_FAILURE = "recovery_failure"
    REGIME_TRANSITION = "regime_transition"
    MANUAL_CLI = "manual_cli"
    SCHEDULED = "scheduled"


# Regime → allowed action classes (frozenset for immutability)
_ALL_ACTIONS = frozenset(ActionClass)
_REGIME_ACTION_CLASSES: dict[OperationalRegime, frozenset[ActionClass]] = {
    OperationalRegime.ELASTIC: _ALL_ACTIONS,
    OperationalRegime.WARM: _ALL_ACTIONS,
    OperationalRegime.DUCTILE: frozenset({
        ActionClass.READ, ActionClass.STATUS,
        ActionClass.RESET, ActionClass.RECOVERY_SUBMIT,
    }),
    OperationalRegime.UNSTABLE: frozenset({
        ActionClass.STATUS, ActionClass.RECOVERY_SUBMIT,
    }),
}


def check_regime_allows(
    regime: OperationalRegime,
    action_class: ActionClass,
) -> tuple[bool, DenyReason | None]:
    """Canonical check: is this action class permitted in this regime?

    Returns (allowed, deny_reason). All callers should use this rather
    than ad-hoc string matching against regime values.
    """
    allowed = regime.allowed_action_classes
    if action_class in allowed:
        return True, None
    return False, DenyReason.REGIME_RESTRICTED


def classify_action(operation: str) -> ActionClass:
    """Classify an operation description into an ActionClass.

    Central classifier. All callers must use this, not ad-hoc matching.
    2.x implementation is keyword-based; 3.x may use richer heuristics.
    """
    op = operation.lower()
    # Check reset before configure ("reset" contains "set")
    if any(kw in op for kw in ("reset", "clear", "wipe")):
        return ActionClass.RESET
    if any(kw in op for kw in ("write", "edit", "modify", "create", "delete", "patch")):
        return ActionClass.WRITE
    if any(kw in op for kw in ("run", "exec", "invoke", "call", "command")):
        return ActionClass.EXECUTE
    if any(kw in op for kw in ("config", "set", "tune", "adjust")):
        return ActionClass.CONFIGURE
    if any(kw in op for kw in ("status", "show", "list", "info", "query")):
        return ActionClass.STATUS
    if any(kw in op for kw in ("recover", "remediat", "fix", "repair")):
        return ActionClass.RECOVERY_SUBMIT
    if any(kw in op for kw in ("read", "get", "fetch", "view", "inspect")):
        return ActionClass.READ
    # Default: READ is the safest classification
    return ActionClass.READ


# =============================================================================
# Regime Signals (Observable Metrics)
# =============================================================================


@dataclass
class RegimeSignals:
    """
    Observable signals for regime classification.

    These are metrics we can actually measure, not inferred intent.
    """

    # Hysteresis: does the system return to baseline after perturbation?
    # High = sticky behavior, path dependence
    hysteresis: float = 0.0

    # Relaxation time: how long to return to baseline (seconds)?
    # Long = ductile, short = elastic
    relaxation_time: float = 0.0

    # Tool gain: are perturbations amplifying?
    # k > 1 = unstable, k < 1 = stable
    tool_gain: float = 0.5

    # Anisotropy: variance under paraphrase/reframe
    # High = sensitive to framing, aliasing risk
    anisotropy: float = 0.0

    # Provenance deficit: claims without evidence anchors
    # High = drifting from grounded state
    provenance_deficit: float = 0.0

    # Budget pressure: how often caps trigger (0-1)
    # High = system is straining against limits
    budget_pressure: float = 0.0

    # Contradiction rates (events per second in 60s window)
    contradiction_open_rate: float = 0.0  # New contradictions per second
    contradiction_close_rate: float = 0.0  # Resolved contradictions per second

    # Rejection rate: proposals rejected / total proposals
    rejection_rate: float = 0.0

    # Dangerous claim rate: dangerous claims / total claims
    dangerous_claim_rate: float = 0.0

    @property
    def contradictions_accumulating(self) -> bool:
        """Are contradictions accumulating faster than resolving?"""
        return self.contradiction_open_rate > self.contradiction_close_rate * 1.2

    def to_dict(self) -> dict[str, float]:
        return {
            "hysteresis": self.hysteresis,
            "relaxation_time": self.relaxation_time,
            "tool_gain": self.tool_gain,
            "anisotropy": self.anisotropy,
            "provenance_deficit": self.provenance_deficit,
            "budget_pressure": self.budget_pressure,
            "contradiction_open_rate": self.contradiction_open_rate,
            "contradiction_close_rate": self.contradiction_close_rate,
            "rejection_rate": self.rejection_rate,
            "dangerous_claim_rate": self.dangerous_claim_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeSignals":
        return cls(
            hysteresis=data.get("hysteresis", 0.0),
            relaxation_time=data.get("relaxation_time", 0.0),
            tool_gain=data.get("tool_gain", 0.5),
            anisotropy=data.get("anisotropy", 0.0),
            provenance_deficit=data.get("provenance_deficit", 0.0),
            budget_pressure=data.get("budget_pressure", 0.0),
            contradiction_open_rate=data.get("contradiction_open_rate", 0.0),
            contradiction_close_rate=data.get("contradiction_close_rate", 0.0),
            rejection_rate=data.get("rejection_rate", 0.0),
            dangerous_claim_rate=data.get("dangerous_claim_rate", 0.0),
        )


# =============================================================================
# Regime Thresholds
# =============================================================================


@dataclass
class RegimeThresholds:
    """
    Thresholds for regime transitions.

    These define the boundaries between regimes.
    Can be tuned based on empirical observation.
    """

    # ELASTIC -> WARM thresholds
    warm_hysteresis: float = 0.2
    warm_relaxation: float = 3.0
    warm_anisotropy: float = 0.3
    warm_provenance_deficit: float = 0.2
    warm_rejection_rate: float = 0.3
    warm_dangerous_rate: float = 0.1

    # WARM -> DUCTILE thresholds
    ductile_hysteresis: float = 0.5
    ductile_relaxation: float = 10.0
    ductile_anisotropy: float = 0.5
    ductile_budget_pressure: float = 0.7
    ductile_rejection_rate: float = 0.5

    # Any -> UNSTABLE thresholds
    unstable_tool_gain: float = 1.0  # k >= 1 is unstable
    unstable_budget_pressure: float = 0.9
    unstable_dangerous_rate: float = 0.3

    def to_dict(self) -> dict[str, float]:
        return {
            "warm_hysteresis": self.warm_hysteresis,
            "warm_relaxation": self.warm_relaxation,
            "warm_anisotropy": self.warm_anisotropy,
            "warm_provenance_deficit": self.warm_provenance_deficit,
            "warm_rejection_rate": self.warm_rejection_rate,
            "warm_dangerous_rate": self.warm_dangerous_rate,
            "ductile_hysteresis": self.ductile_hysteresis,
            "ductile_relaxation": self.ductile_relaxation,
            "ductile_anisotropy": self.ductile_anisotropy,
            "ductile_budget_pressure": self.ductile_budget_pressure,
            "ductile_rejection_rate": self.ductile_rejection_rate,
            "unstable_tool_gain": self.unstable_tool_gain,
            "unstable_budget_pressure": self.unstable_budget_pressure,
            "unstable_dangerous_rate": self.unstable_dangerous_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeThresholds":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


# =============================================================================
# Regime Transitions
# =============================================================================


@dataclass
class RegimeTransition:
    """Record of a regime transition."""

    timestamp: datetime
    from_regime: OperationalRegime
    to_regime: OperationalRegime
    signals: RegimeSignals
    trigger_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "from_regime": self.from_regime.value,
            "to_regime": self.to_regime.value,
            "signals": self.signals.to_dict(),
            "trigger_reasons": self.trigger_reasons,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeTransition":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            from_regime=OperationalRegime(data["from_regime"]),
            to_regime=OperationalRegime(data["to_regime"]),
            signals=RegimeSignals.from_dict(data["signals"]),
            trigger_reasons=data["trigger_reasons"],
        )


# =============================================================================
# Regime Metrics (for threshold tuning)
# =============================================================================


@dataclass
class RegimeMetrics:
    """
    Metrics collection for empirical validation.

    Tracks signal history, transitions, and dwell times
    to enable threshold tuning.
    """

    # Signal history (timestamp, signals, regime)
    signal_history: list[tuple[datetime, RegimeSignals, OperationalRegime]] = field(
        default_factory=list
    )
    max_signal_history: int = 1000

    # Transition counts
    transition_counts: dict[str, int] = field(default_factory=dict)

    # Regime dwell times (seconds in each regime)
    regime_entry_time: dict[OperationalRegime, datetime | None] = field(
        default_factory=dict
    )
    regime_dwell_times: dict[OperationalRegime, list[float]] = field(
        default_factory=lambda: {r: [] for r in OperationalRegime}
    )

    # Turn counter
    turn_counter: int = 0

    def record_signal(self, signals: RegimeSignals, regime: OperationalRegime) -> None:
        """Record a signal observation."""
        self.signal_history.append((datetime.now(timezone.utc), signals, regime))
        if len(self.signal_history) > self.max_signal_history:
            self.signal_history.pop(0)

    def record_transition(
        self, from_regime: OperationalRegime, to_regime: OperationalRegime
    ) -> None:
        """Record a regime transition."""
        key = f"{from_regime.value}->{to_regime.value}"
        self.transition_counts[key] = self.transition_counts.get(key, 0) + 1

        # Update dwell time for exited regime
        now = datetime.now(timezone.utc)
        if from_regime in self.regime_entry_time and self.regime_entry_time[from_regime]:
            entry = self.regime_entry_time[from_regime]
            dwell = (now - entry).total_seconds()
            self.regime_dwell_times[from_regime].append(dwell)

        # Mark entry to new regime
        self.regime_entry_time[to_regime] = now

    def advance_turn(self) -> None:
        """Advance turn counter."""
        self.turn_counter += 1

    def get_threshold_analysis(self) -> dict[str, Any]:
        """Analyze signal distributions by regime for threshold tuning."""
        if not self.signal_history:
            return {}

        # Group signals by regime
        by_regime: dict[OperationalRegime, list[RegimeSignals]] = {
            r: [] for r in OperationalRegime
        }
        for _, signals, regime in self.signal_history:
            by_regime[regime].append(signals)

        analysis = {}
        for regime, signals_list in by_regime.items():
            if not signals_list:
                continue

            analysis[regime.value] = {
                "count": len(signals_list),
                "hysteresis": {
                    "min": min(s.hysteresis for s in signals_list),
                    "max": max(s.hysteresis for s in signals_list),
                    "mean": sum(s.hysteresis for s in signals_list) / len(signals_list),
                },
                "tool_gain": {
                    "min": min(s.tool_gain for s in signals_list),
                    "max": max(s.tool_gain for s in signals_list),
                    "mean": sum(s.tool_gain for s in signals_list) / len(signals_list),
                },
                "provenance_deficit": {
                    "min": min(s.provenance_deficit for s in signals_list),
                    "max": max(s.provenance_deficit for s in signals_list),
                    "mean": sum(s.provenance_deficit for s in signals_list)
                    / len(signals_list),
                },
            }

        return analysis

    def get_summary(self) -> dict[str, Any]:
        """Get full metrics summary."""
        # Calculate average dwell times
        avg_dwell = {}
        for regime, times in self.regime_dwell_times.items():
            if times:
                avg_dwell[regime.value] = sum(times) / len(times)

        return {
            "total_observations": len(self.signal_history),
            "total_turns": self.turn_counter,
            "transitions": self.transition_counts,
            "avg_dwell_times": avg_dwell,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_counter": self.turn_counter,
            "transition_counts": self.transition_counts,
            "regime_dwell_times": {
                r.value: times for r, times in self.regime_dwell_times.items()
            },
            "summary": self.get_summary(),
        }


# =============================================================================
# Regime Detector
# =============================================================================


class RegimeDetector:
    """
    Detects operational regime from observable signals.

    This is a classifier over dynamics, not semantics.
    We observe behavior, not intent.
    """

    def __init__(
        self,
        thresholds: RegimeThresholds | None = None,
        collect_metrics: bool = True,
    ):
        self.thresholds = thresholds or RegimeThresholds()
        self.collect_metrics = collect_metrics

        self.current_regime = OperationalRegime.ELASTIC
        self.transition_history: list[RegimeTransition] = []
        self.last_signals: RegimeSignals | None = None

        # Metrics collection
        self.metrics = RegimeMetrics() if collect_metrics else None

    def classify(self, signals: RegimeSignals) -> tuple[OperationalRegime, list[str]]:
        """
        Classify current regime based on signals.

        Returns (regime, list_of_trigger_reasons).
        """
        self.last_signals = signals
        t = self.thresholds

        # Check UNSTABLE first (highest priority)
        unstable_reasons = []
        if signals.tool_gain >= t.unstable_tool_gain:
            unstable_reasons.append(f"tool_gain={signals.tool_gain:.2f} >= {t.unstable_tool_gain}")
        if signals.budget_pressure >= t.unstable_budget_pressure:
            unstable_reasons.append(
                f"budget_pressure={signals.budget_pressure:.2f} >= {t.unstable_budget_pressure}"
            )
        if signals.dangerous_claim_rate >= t.unstable_dangerous_rate:
            unstable_reasons.append(
                f"dangerous_rate={signals.dangerous_claim_rate:.2f} >= {t.unstable_dangerous_rate}"
            )

        if unstable_reasons:
            if self.metrics:
                self.metrics.record_signal(signals, OperationalRegime.UNSTABLE)
            return OperationalRegime.UNSTABLE, unstable_reasons

        # Check DUCTILE
        ductile_reasons = []
        if signals.hysteresis >= t.ductile_hysteresis:
            ductile_reasons.append(f"hysteresis={signals.hysteresis:.2f}")
        if signals.relaxation_time >= t.ductile_relaxation:
            ductile_reasons.append(f"relaxation={signals.relaxation_time:.1f}s")
        if signals.anisotropy >= t.ductile_anisotropy:
            ductile_reasons.append(f"anisotropy={signals.anisotropy:.2f}")
        if signals.budget_pressure >= t.ductile_budget_pressure:
            ductile_reasons.append(f"budget_pressure={signals.budget_pressure:.2f}")
        if signals.rejection_rate >= t.ductile_rejection_rate:
            ductile_reasons.append(f"rejection_rate={signals.rejection_rate:.2f}")

        # Need multiple indicators for DUCTILE
        if len(ductile_reasons) >= 2:
            if self.metrics:
                self.metrics.record_signal(signals, OperationalRegime.DUCTILE)
            return OperationalRegime.DUCTILE, ductile_reasons

        # Check WARM
        warm_reasons = []
        if signals.hysteresis >= t.warm_hysteresis:
            warm_reasons.append(f"hysteresis={signals.hysteresis:.2f}")
        if signals.relaxation_time >= t.warm_relaxation:
            warm_reasons.append(f"relaxation={signals.relaxation_time:.1f}s")
        if signals.anisotropy >= t.warm_anisotropy:
            warm_reasons.append(f"anisotropy={signals.anisotropy:.2f}")
        if signals.provenance_deficit >= t.warm_provenance_deficit:
            warm_reasons.append(f"provenance_deficit={signals.provenance_deficit:.2f}")
        if signals.rejection_rate >= t.warm_rejection_rate:
            warm_reasons.append(f"rejection_rate={signals.rejection_rate:.2f}")
        if signals.dangerous_claim_rate >= t.warm_dangerous_rate:
            warm_reasons.append(f"dangerous_rate={signals.dangerous_claim_rate:.2f}")
        if signals.contradictions_accumulating:
            warm_reasons.append("contradictions accumulating")

        if warm_reasons:
            if self.metrics:
                self.metrics.record_signal(signals, OperationalRegime.WARM)
            return OperationalRegime.WARM, warm_reasons

        # Default: ELASTIC
        if self.metrics:
            self.metrics.record_signal(signals, OperationalRegime.ELASTIC)
        return OperationalRegime.ELASTIC, ["all signals nominal"]

    def update(self, signals: RegimeSignals) -> RegimeTransition | None:
        """
        Update regime based on new signals.

        Returns transition if regime changed, None otherwise.
        """
        new_regime, reasons = self.classify(signals)

        if new_regime != self.current_regime:
            transition = RegimeTransition(
                timestamp=datetime.now(timezone.utc),
                from_regime=self.current_regime,
                to_regime=new_regime,
                signals=signals,
                trigger_reasons=reasons,
            )

            # Record metrics
            if self.metrics:
                self.metrics.record_transition(self.current_regime, new_regime)

            self.transition_history.append(transition)
            self.current_regime = new_regime
            return transition

        return None

    def get_recommended_action(self) -> str:
        """Get recommended action for current regime."""
        return self.current_regime.recommended_action

    def get_state(self) -> dict[str, Any]:
        """Get current detector state."""
        return {
            "current_regime": self.current_regime.value,
            "recommended_action": self.get_recommended_action(),
            "transitions": len(self.transition_history),
            "last_signals": self.last_signals.to_dict() if self.last_signals else None,
            "metrics": self.metrics.get_summary() if self.metrics else None,
        }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent transition history."""
        return [t.to_dict() for t in self.transition_history[-limit:]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize detector state."""
        return {
            "current_regime": self.current_regime.value,
            "thresholds": self.thresholds.to_dict(),
            "transition_history": [t.to_dict() for t in self.transition_history],
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeDetector":
        """Deserialize detector from dictionary."""
        thresholds = RegimeThresholds.from_dict(data["thresholds"])
        detector = cls(thresholds=thresholds, collect_metrics=data.get("metrics") is not None)
        detector.current_regime = OperationalRegime(data["current_regime"])
        detector.transition_history = [
            RegimeTransition.from_dict(t) for t in data.get("transition_history", [])
        ]
        # Restore partial metrics if present
        if data.get("metrics") and detector.metrics:
            detector.metrics.turn_counter = data["metrics"].get("turn_counter", 0)
            detector.metrics.transition_counts = data["metrics"].get("transition_counts", {})
            # Restore dwell times
            dwell_data = data["metrics"].get("regime_dwell_times", {})
            for regime_str, times in dwell_data.items():
                regime = OperationalRegime(regime_str)
                detector.metrics.regime_dwell_times[regime] = times
        return detector

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2, default=str)


# =============================================================================
# Signal Collector (helper for building signals from governor state)
# =============================================================================


class SignalCollector:
    """
    Helper class for collecting signals from governor state.

    Tracks metrics over time and computes regime signals.
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size

        # Rolling windows for rate calculations
        self.proposals: list[tuple[datetime, bool]] = []  # (time, accepted)
        self.contradictions_opened: list[datetime] = []
        self.contradictions_closed: list[datetime] = []
        self.dangerous_claims: list[datetime] = []
        self.total_claims: list[datetime] = []

        # Baseline tracking for hysteresis/relaxation
        self.baseline_rejection_rate: float = 0.0
        self.perturbation_time: datetime | None = None
        self.returned_to_baseline: bool = True

    def record_proposal(self, accepted: bool) -> None:
        """Record a proposal outcome."""
        now = datetime.now(timezone.utc)
        self.proposals.append((now, accepted))
        self._trim_window(self.proposals)

    def record_contradiction_opened(self) -> None:
        """Record a new contradiction."""
        self.contradictions_opened.append(datetime.now(timezone.utc))
        self._trim_window(self.contradictions_opened)

    def record_contradiction_closed(self) -> None:
        """Record a resolved contradiction."""
        self.contradictions_closed.append(datetime.now(timezone.utc))
        self._trim_window(self.contradictions_closed)

    def record_dangerous_claim(self) -> None:
        """Record a dangerous claim detected."""
        self.dangerous_claims.append(datetime.now(timezone.utc))
        self._trim_window(self.dangerous_claims)

    def record_claim(self) -> None:
        """Record any claim."""
        self.total_claims.append(datetime.now(timezone.utc))
        self._trim_window(self.total_claims)

    def _trim_window(self, lst: list) -> None:
        """Trim list to window size."""
        while len(lst) > self.window_size * 10:  # Keep some extra for rate calc
            lst.pop(0)

    def compute_signals(
        self,
        provenance_deficit: float = 0.0,
        budget_pressure: float = 0.0,
        tool_gain: float = 0.5,
    ) -> RegimeSignals:
        """
        Compute regime signals from collected data.

        Some signals (provenance_deficit, budget_pressure, tool_gain)
        must be provided externally as they depend on ledger state.
        """
        # Compute rejection rate
        recent_proposals = self.proposals[-self.window_size:]
        if recent_proposals:
            rejected = sum(1 for _, accepted in recent_proposals if not accepted)
            rejection_rate = rejected / len(recent_proposals)
        else:
            rejection_rate = 0.0

        # Compute contradiction rates (events-per-second in time window).
        # Both rates share the same denominator (window_time_s) so their
        # ratio is meaningful for comparisons like contradictions_accumulating.
        window_time_s = 60.0  # 1 minute window
        now = datetime.now(timezone.utc)

        recent_opens = [
            t for t in self.contradictions_opened
            if (now - t).total_seconds() < window_time_s
        ]
        recent_closes = [
            t for t in self.contradictions_closed
            if (now - t).total_seconds() < window_time_s
        ]

        open_rate = len(recent_opens) / window_time_s
        close_rate = len(recent_closes) / window_time_s

        # Compute dangerous claim rate
        recent_dangerous = [
            t for t in self.dangerous_claims
            if (now - t).total_seconds() < window_time_s
        ]
        recent_total = [
            t for t in self.total_claims
            if (now - t).total_seconds() < window_time_s
        ]

        if recent_total:
            dangerous_rate = len(recent_dangerous) / len(recent_total)
        else:
            dangerous_rate = 0.0

        # Compute hysteresis (deviation from baseline that persists)
        if recent_proposals and self.baseline_rejection_rate > 0:
            hysteresis = abs(rejection_rate - self.baseline_rejection_rate)
        else:
            hysteresis = 0.0

        # Compute relaxation time (simplified - time since last perturbation)
        if self.perturbation_time and not self.returned_to_baseline:
            relaxation_time = (now - self.perturbation_time).total_seconds()
        else:
            relaxation_time = 0.0

        return RegimeSignals(
            hysteresis=hysteresis,
            relaxation_time=relaxation_time,
            tool_gain=tool_gain,
            anisotropy=0.0,  # Would need paraphrase testing to compute
            provenance_deficit=provenance_deficit,
            budget_pressure=budget_pressure,
            contradiction_open_rate=open_rate,
            contradiction_close_rate=close_rate,
            rejection_rate=rejection_rate,
            dangerous_claim_rate=dangerous_rate,
        )

    def update_baseline(self) -> None:
        """Update baseline from current state."""
        recent = self.proposals[-self.window_size:]
        if recent:
            rejected = sum(1 for _, accepted in recent if not accepted)
            self.baseline_rejection_rate = rejected / len(recent)
        self.returned_to_baseline = True
        self.perturbation_time = None

    def record_perturbation(self) -> None:
        """Record that a significant perturbation occurred."""
        self.perturbation_time = datetime.now(timezone.utc)
        self.returned_to_baseline = False
