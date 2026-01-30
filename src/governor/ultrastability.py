"""
Ultrastability Layer: Ashby-style second-order adaptation for S₁ parameters.

The governor's budgets, thresholds, and rates can adapt based on observed
S₂ dynamics — but only within constitutional bounds and only when
adaptation criteria are met.

Key principle from Ashby:
> "Change the parameters of regulation, not the laws being regulated by."

Hierarchy:
  S₀ (Constitution): Immutable — NLAI, FSM topology, forbidden transitions
  S₁ (Regulatory): Budgets, thresholds, timeouts (adaptable within bounds)
  S₂ (Epistemic): Claims, contradictions, ledger (fully mutable)

Rule: S₂ may influence S₁.  S₁ may NOT influence S₀.

This module implements:
  1. Regulatory parameters with bounded adaptation (S₁)
  2. Epoch observations for health monitoring
  3. Adaptation triggers (when to consider changing S₁)
  4. Pathology detection (when adaptation is making things worse)
  5. UltrastabilityController: the main adaptation loop
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import json
import statistics
import uuid


# =============================================================================
# Enums
# =============================================================================


class AdaptationVerdict(str, Enum):
    """Result of adaptation consideration."""

    HOLD = "hold"
    """No change needed — system is stable."""

    ADAPT = "adapt"
    """Change within bounds — specific parameter adjustment proposed."""

    FREEZE = "freeze"
    """Stop adapting — pathology detected, wait for human."""

    ALERT = "alert"
    """Human intervention needed — serious pathology found."""


class Pathology(str, Enum):
    """Types of adaptation pathology."""

    OSCILLATION = "oscillation"
    """Parameters bouncing between values (3+ reversals in window)."""

    RUNAWAY = "runaway"
    """Continuous adaptation in one direction, hitting bounds."""

    INEFFECTIVE = "ineffective"
    """Adapting but metrics not improving."""

    WRONG_ATTRACTOR = "wrong_attractor"
    """System stabilized in a bad regime."""


class ParameterDirection(str, Enum):
    """Direction of a parameter change."""

    INCREASE = "increase"
    DECREASE = "decrease"


# =============================================================================
# S₁ Regulatory Parameters
# =============================================================================


@dataclass
class ParameterSpec:
    """
    Specification for a single regulatory parameter.

    Each S₁ parameter has a current value, constitutional bounds,
    and a maximum step size per adaptation epoch.
    """

    name: str
    current: float
    floor: float      # Constitutional minimum
    ceiling: float    # Constitutional maximum
    step: float       # Max change per adaptation epoch
    description: str = ""

    def __post_init__(self):
        if self.floor > self.ceiling:
            raise ValueError(f"{self.name}: floor ({self.floor}) > ceiling ({self.ceiling})")
        if self.step <= 0:
            raise ValueError(f"{self.name}: step must be positive, got {self.step}")
        self.current = max(self.floor, min(self.ceiling, self.current))

    @property
    def at_floor(self) -> bool:
        return self.current <= self.floor

    @property
    def at_ceiling(self) -> bool:
        return self.current >= self.ceiling

    @property
    def headroom_up(self) -> float:
        """Room to increase."""
        return self.ceiling - self.current

    @property
    def headroom_down(self) -> float:
        """Room to decrease."""
        return self.current - self.floor

    @property
    def range(self) -> float:
        return self.ceiling - self.floor

    @property
    def normalized(self) -> float:
        """Current value as fraction of range [0, 1]."""
        if self.range == 0:
            return 0.5
        return (self.current - self.floor) / self.range

    def propose_change(self, delta: float) -> tuple[float, bool]:
        """
        Propose a change to this parameter.

        Returns (new_value, was_clamped).
        Enforces floor/ceiling/step bounds.
        """
        # Clamp delta to step size
        clamped_delta = max(-self.step, min(self.step, delta))

        # Compute new value
        new_value = self.current + clamped_delta

        # Clamp to floor/ceiling
        was_clamped = False
        if new_value < self.floor:
            new_value = self.floor
            was_clamped = True
        elif new_value > self.ceiling:
            new_value = self.ceiling
            was_clamped = True

        return new_value, was_clamped

    def apply(self, new_value: float):
        """Apply a validated change."""
        self.current = max(self.floor, min(self.ceiling, new_value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current": self.current,
            "floor": self.floor,
            "ceiling": self.ceiling,
            "step": self.step,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterSpec":
        return cls(
            name=data["name"],
            current=data["current"],
            floor=data["floor"],
            ceiling=data["ceiling"],
            step=data["step"],
            description=data.get("description", ""),
        )


# Default S₁ parameters
DEFAULT_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "repair_budget",
        "current": 100.0,
        "floor": 10.0,
        "ceiling": 500.0,
        "step": 10.0,
        "description": "Budget for repair/resolution operations",
    },
    {
        "name": "refill_rate",
        "current": 5.0,
        "floor": 1.0,
        "ceiling": 20.0,
        "step": 1.0,
        "description": "Budget refill per turn",
    },
    {
        "name": "glass_threshold",
        "current": 20.0,
        "floor": 5.0,
        "ceiling": 50.0,
        "step": 2.0,
        "description": "Open contradictions before regime degrades",
    },
    {
        "name": "resolution_cost",
        "current": 10.0,
        "floor": 1.0,
        "ceiling": 50.0,
        "step": 2.0,
        "description": "Cost per contradiction resolution",
    },
    {
        "name": "claim_timeout_ms",
        "current": 5000.0,
        "floor": 1000.0,
        "ceiling": 30000.0,
        "step": 500.0,
        "description": "Timeout for claim verification",
    },
    {
        "name": "evidence_threshold",
        "current": 0.7,
        "floor": 0.3,
        "ceiling": 1.0,
        "step": 0.05,
        "description": "Minimum evidence strength for HARD commitment",
    },
    {
        "name": "independence_threshold",
        "current": 0.6,
        "floor": 0.3,
        "ceiling": 0.95,
        "step": 0.05,
        "description": "Minimum source independence for corroboration",
    },
]


class RegulatoryParameters:
    """
    S₁ — The regulatory layer that can adapt within bounds.

    Contains all tunable parameters with constitutional floor/ceiling/step
    constraints. S₂ observations drive adaptation; S₀ prevents overreach.
    """

    def __init__(self, specs: list[ParameterSpec] | None = None):
        if specs is None:
            specs = [ParameterSpec(**d) for d in DEFAULT_PARAMETERS]
        self._params: dict[str, ParameterSpec] = {s.name: s for s in specs}

    def get(self, name: str) -> ParameterSpec:
        """Get a parameter spec by name."""
        if name not in self._params:
            raise KeyError(f"Unknown parameter: {name}")
        return self._params[name]

    def value(self, name: str) -> float:
        """Get current value of a parameter."""
        return self.get(name).current

    def set_value(self, name: str, value: float):
        """Set value (clamped to bounds)."""
        self.get(name).apply(value)

    @property
    def names(self) -> list[str]:
        return list(self._params.keys())

    @property
    def all_specs(self) -> list[ParameterSpec]:
        return list(self._params.values())

    def propose_change(self, name: str, delta: float) -> tuple[float, bool]:
        """Propose a change. Returns (new_value, was_clamped)."""
        return self.get(name).propose_change(delta)

    def apply_change(self, name: str, new_value: float):
        """Apply a validated change."""
        self.get(name).apply(new_value)

    def summary(self) -> dict[str, dict[str, float]]:
        """Get a summary of all parameters."""
        return {
            name: {
                "current": spec.current,
                "floor": spec.floor,
                "ceiling": spec.ceiling,
                "normalized": spec.normalized,
            }
            for name, spec in self._params.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {"parameters": [s.to_dict() for s in self._params.values()]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegulatoryParameters":
        specs = [ParameterSpec.from_dict(d) for d in data.get("parameters", [])]
        return cls(specs if specs else None)


# =============================================================================
# Epoch Observation
# =============================================================================


@dataclass
class EpochObservation:
    """
    Observations from one adaptation epoch.

    An epoch is a fixed window of turns during which we collect
    metrics about system behavior.
    """

    epoch_id: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Counts
    turns: int = 0
    proposals_submitted: int = 0
    proposals_accepted: int = 0
    proposals_rejected: int = 0
    contradictions_opened: int = 0
    contradictions_closed: int = 0
    budget_blocks: int = 0
    violations: int = 0
    dangerous_claims: int = 0

    # Computed rates (call compute_rates() to populate)
    acceptance_rate: float = 0.0
    rejection_rate: float = 0.0
    open_rate: float = 0.0
    close_rate: float = 0.0
    block_rate: float = 0.0
    violation_rate: float = 0.0
    dangerous_rate: float = 0.0

    # State snapshot at end of epoch
    c_open: int = 0  # Open contradictions
    regime: str = "ELASTIC"
    active_scars: int = 0
    active_shields: int = 0

    def compute_rates(self):
        """Compute derived rates from counts."""
        if self.turns > 0:
            self.open_rate = self.contradictions_opened / self.turns
            self.close_rate = self.contradictions_closed / self.turns
            self.block_rate = self.budget_blocks / self.turns
            self.violation_rate = self.violations / self.turns
            self.dangerous_rate = self.dangerous_claims / self.turns
        if self.proposals_submitted > 0:
            self.acceptance_rate = self.proposals_accepted / self.proposals_submitted
            self.rejection_rate = self.proposals_rejected / self.proposals_submitted

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "timestamp": self.timestamp.isoformat(),
            "turns": self.turns,
            "proposals_submitted": self.proposals_submitted,
            "proposals_accepted": self.proposals_accepted,
            "proposals_rejected": self.proposals_rejected,
            "contradictions_opened": self.contradictions_opened,
            "contradictions_closed": self.contradictions_closed,
            "budget_blocks": self.budget_blocks,
            "violations": self.violations,
            "dangerous_claims": self.dangerous_claims,
            "acceptance_rate": self.acceptance_rate,
            "rejection_rate": self.rejection_rate,
            "open_rate": self.open_rate,
            "close_rate": self.close_rate,
            "block_rate": self.block_rate,
            "violation_rate": self.violation_rate,
            "dangerous_rate": self.dangerous_rate,
            "c_open": self.c_open,
            "regime": self.regime,
            "active_scars": self.active_scars,
            "active_shields": self.active_shields,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpochObservation":
        obs = cls(
            epoch_id=data.get("epoch_id", 0),
            turns=data.get("turns", 0),
            proposals_submitted=data.get("proposals_submitted", 0),
            proposals_accepted=data.get("proposals_accepted", 0),
            proposals_rejected=data.get("proposals_rejected", 0),
            contradictions_opened=data.get("contradictions_opened", 0),
            contradictions_closed=data.get("contradictions_closed", 0),
            budget_blocks=data.get("budget_blocks", 0),
            violations=data.get("violations", 0),
            dangerous_claims=data.get("dangerous_claims", 0),
            c_open=data.get("c_open", 0),
            regime=data.get("regime", "ELASTIC"),
            active_scars=data.get("active_scars", 0),
            active_shields=data.get("active_shields", 0),
        )
        if "timestamp" in data:
            obs.timestamp = datetime.fromisoformat(data["timestamp"])
        # Restore computed rates if present, otherwise compute
        if "acceptance_rate" in data:
            obs.acceptance_rate = data["acceptance_rate"]
            obs.rejection_rate = data.get("rejection_rate", 0.0)
            obs.open_rate = data.get("open_rate", 0.0)
            obs.close_rate = data.get("close_rate", 0.0)
            obs.block_rate = data.get("block_rate", 0.0)
            obs.violation_rate = data.get("violation_rate", 0.0)
            obs.dangerous_rate = data.get("dangerous_rate", 0.0)
        else:
            obs.compute_rates()
        return obs


# =============================================================================
# Adaptation History
# =============================================================================


@dataclass
class AdaptationRecord:
    """Record of a single parameter adaptation."""

    epoch_id: int
    timestamp: datetime
    parameter: str
    old_value: float
    new_value: float
    delta: float
    was_clamped: bool
    reason: str
    direction: ParameterDirection

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "timestamp": self.timestamp.isoformat(),
            "parameter": self.parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "delta": self.delta,
            "was_clamped": self.was_clamped,
            "reason": self.reason,
            "direction": self.direction.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptationRecord":
        return cls(
            epoch_id=data["epoch_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            parameter=data["parameter"],
            old_value=data["old_value"],
            new_value=data["new_value"],
            delta=data["delta"],
            was_clamped=data["was_clamped"],
            reason=data["reason"],
            direction=ParameterDirection(data["direction"]),
        )


class AdaptationHistory:
    """
    History of epochs and adaptations for trend analysis and pathology detection.
    """

    def __init__(self, max_epochs: int = 20, max_records: int = 100):
        self.max_epochs = max_epochs
        self.max_records = max_records
        self.epochs: list[EpochObservation] = []
        self.records: list[AdaptationRecord] = []

    def add_epoch(self, epoch: EpochObservation):
        """Add an epoch observation."""
        self.epochs.append(epoch)
        if len(self.epochs) > self.max_epochs:
            self.epochs.pop(0)

    def add_record(self, record: AdaptationRecord):
        """Log an adaptation record."""
        self.records.append(record)
        if len(self.records) > self.max_records:
            self.records.pop(0)

    def get_trend(self, metric: str, window: int = 3) -> float | None:
        """
        Get trend for a metric over recent epochs.

        Returns slope: positive = increasing, negative = decreasing.
        Returns None if insufficient data.
        """
        if len(self.epochs) < window:
            return None

        recent = self.epochs[-window:]
        values = [getattr(e, metric, 0.0) for e in recent]

        n = len(values)
        if n < 2:
            return None

        x_mean = (n - 1) / 2
        y_mean = statistics.mean(values)

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def recent_records_for(self, parameter: str, count: int = 10) -> list[AdaptationRecord]:
        """Get recent adaptation records for a specific parameter."""
        recs = [r for r in self.records if r.parameter == parameter]
        return recs[-count:]

    @property
    def total_adaptations(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_epochs": self.max_epochs,
            "max_records": self.max_records,
            "epochs": [e.to_dict() for e in self.epochs],
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptationHistory":
        h = cls(
            max_epochs=data.get("max_epochs", 20),
            max_records=data.get("max_records", 100),
        )
        h.epochs = [EpochObservation.from_dict(e) for e in data.get("epochs", [])]
        h.records = [AdaptationRecord.from_dict(r) for r in data.get("records", [])]
        return h


# =============================================================================
# Adaptation Triggers
# =============================================================================


@dataclass
class AdaptationTrigger:
    """Conditions that trigger adaptation consideration."""

    # Starvation indicators
    block_rate_threshold: float = 0.3  # >30% turns blocked = too tight

    # Accumulation indicators
    c_open_threshold: int = 15  # >15 open contradictions = accumulating
    open_close_ratio: float = 1.2  # open_rate > close_rate * ratio = accumulating

    # Stability indicators
    min_epochs_for_trend: int = 3  # Need 3 epochs to see trend
    trend_significance: float = 0.1  # Slope must exceed this

    # Rate thresholds
    violation_rate_threshold: float = 0.2  # >20% turns with violations
    dangerous_rate_threshold: float = 0.1  # >10% turns with dangerous claims

    def evaluate(
        self,
        current: EpochObservation,
        history: AdaptationHistory,
    ) -> tuple[bool, list[str]]:
        """
        Determine if adaptation should be considered.

        Returns (should_adapt, reasons).
        """
        reasons = []

        # Check for starvation (blocking too much)
        if current.block_rate > self.block_rate_threshold:
            reasons.append(f"block_rate={current.block_rate:.2f} > {self.block_rate_threshold}")

        # Check for contradiction accumulation
        if current.c_open > self.c_open_threshold:
            reasons.append(f"c_open={current.c_open} > {self.c_open_threshold}")

        if current.close_rate > 0 and current.open_rate > current.close_rate * self.open_close_ratio:
            reasons.append(
                f"open_rate={current.open_rate:.2f} > close_rate*{self.open_close_ratio}"
            )
        elif current.open_rate > 0 and current.close_rate == 0:
            reasons.append("contradictions opening but none closing")

        # Check violation rate
        if current.violation_rate > self.violation_rate_threshold:
            reasons.append(f"violation_rate={current.violation_rate:.2f} > {self.violation_rate_threshold}")

        # Check dangerous claim rate
        if current.dangerous_rate > self.dangerous_rate_threshold:
            reasons.append(f"dangerous_rate={current.dangerous_rate:.2f} > {self.dangerous_rate_threshold}")

        # Check trends
        c_open_trend = history.get_trend("c_open", self.min_epochs_for_trend)
        if c_open_trend is not None and c_open_trend > self.trend_significance:
            reasons.append(f"c_open trending up (slope={c_open_trend:.3f})")

        block_trend = history.get_trend("block_rate", self.min_epochs_for_trend)
        if block_trend is not None and block_trend > self.trend_significance:
            reasons.append(f"block_rate trending up (slope={block_trend:.3f})")

        return len(reasons) > 0, reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_rate_threshold": self.block_rate_threshold,
            "c_open_threshold": self.c_open_threshold,
            "open_close_ratio": self.open_close_ratio,
            "min_epochs_for_trend": self.min_epochs_for_trend,
            "trend_significance": self.trend_significance,
            "violation_rate_threshold": self.violation_rate_threshold,
            "dangerous_rate_threshold": self.dangerous_rate_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptationTrigger":
        return cls(
            block_rate_threshold=data.get("block_rate_threshold", 0.3),
            c_open_threshold=data.get("c_open_threshold", 15),
            open_close_ratio=data.get("open_close_ratio", 1.2),
            min_epochs_for_trend=data.get("min_epochs_for_trend", 3),
            trend_significance=data.get("trend_significance", 0.1),
            violation_rate_threshold=data.get("violation_rate_threshold", 0.2),
            dangerous_rate_threshold=data.get("dangerous_rate_threshold", 0.1),
        )


# =============================================================================
# Pathology Detection
# =============================================================================


@dataclass
class PathologyDetector:
    """
    Detect when adaptation is making things worse.

    Pathologies:
      OSCILLATION: Parameters bouncing between values
      RUNAWAY: Continuous same-direction adaptation hitting bounds
      INEFFECTIVE: Adapting but metrics not improving
      WRONG_ATTRACTOR: System stabilized in a bad regime
    """

    oscillation_window: int = 6
    oscillation_threshold: int = 3  # reversals to trigger

    runaway_threshold: int = 5  # consecutive clamped in same direction

    ineffective_epochs: int = 5  # epochs without improvement despite adaptation

    wrong_attractor_regimes: list[str] = field(
        default_factory=lambda: ["UNSTABLE", "DUCTILE"]
    )
    wrong_attractor_epochs: int = 3  # stuck in bad regime for N epochs

    def check_oscillation(self, history: AdaptationHistory) -> tuple[bool, str]:
        """Check for parameter oscillation."""
        if len(history.records) < self.oscillation_window:
            return False, ""

        recent = history.records[-self.oscillation_window:]

        # Group deltas by parameter
        by_param: dict[str, list[float]] = {}
        for r in recent:
            by_param.setdefault(r.parameter, []).append(r.delta)

        for param, deltas in by_param.items():
            if len(deltas) < 3:
                continue

            reversals = sum(
                1
                for i in range(1, len(deltas))
                if deltas[i] * deltas[i - 1] < 0  # Sign change
            )

            if reversals >= self.oscillation_threshold:
                return True, f"{param} oscillating ({reversals} reversals in {len(deltas)} changes)"

        return False, ""

    def check_runaway(self, history: AdaptationHistory) -> tuple[bool, str]:
        """Check for runaway adaptation (hitting bounds repeatedly)."""
        if len(history.records) < self.runaway_threshold:
            return False, ""

        recent = history.records[-self.runaway_threshold:]

        # Check if all recent adaptations hit bounds
        clamped = [r for r in recent if r.was_clamped]
        if len(clamped) >= self.runaway_threshold:
            param = clamped[0].parameter
            return True, f"{param} hitting bounds repeatedly ({len(clamped)} clamped)"

        # Check if all recent adaptations are in the same direction for same param
        by_param: dict[str, list[ParameterDirection]] = {}
        for r in recent:
            by_param.setdefault(r.parameter, []).append(r.direction)

        for param, dirs in by_param.items():
            if len(dirs) >= self.runaway_threshold and len(set(dirs)) == 1:
                return True, f"{param} always {dirs[0].value} ({len(dirs)} consecutive)"

        return False, ""

    def check_ineffective(self, history: AdaptationHistory) -> tuple[bool, str]:
        """Check if adaptation isn't helping."""
        if len(history.epochs) < self.ineffective_epochs:
            return False, ""

        recent_epochs = history.epochs[-self.ineffective_epochs:]

        # Were there adaptations during this window?
        min_epoch_id = recent_epochs[0].epoch_id
        recent_adaptations = [
            r for r in history.records if r.epoch_id >= min_epoch_id
        ]

        if not recent_adaptations:
            return False, ""  # No adaptations to judge

        # Check if key metrics improved
        c_open_start = recent_epochs[0].c_open
        c_open_end = recent_epochs[-1].c_open
        block_start = recent_epochs[0].block_rate
        block_end = recent_epochs[-1].block_rate

        # Neither improved despite adaptation
        if c_open_end >= c_open_start and block_end >= block_start:
            return True, (
                f"no improvement despite {len(recent_adaptations)} adaptations "
                f"(c_open: {c_open_start}->{c_open_end}, "
                f"block_rate: {block_start:.2f}->{block_end:.2f})"
            )

        return False, ""

    def check_wrong_attractor(self, history: AdaptationHistory) -> tuple[bool, str]:
        """Check if system stabilized in a bad regime."""
        if len(history.epochs) < self.wrong_attractor_epochs:
            return False, ""

        recent = history.epochs[-self.wrong_attractor_epochs:]
        regimes = [e.regime for e in recent]

        if len(set(regimes)) == 1 and regimes[0] in self.wrong_attractor_regimes:
            return True, f"stuck in {regimes[0]} for {self.wrong_attractor_epochs} epochs"

        return False, ""

    def detect(self, history: AdaptationHistory) -> tuple[list[Pathology], list[str]]:
        """
        Run all pathology checks.

        Returns (pathologies, messages).
        """
        pathologies = []
        messages = []

        is_osc, msg = self.check_oscillation(history)
        if is_osc:
            pathologies.append(Pathology.OSCILLATION)
            messages.append(msg)

        is_run, msg = self.check_runaway(history)
        if is_run:
            pathologies.append(Pathology.RUNAWAY)
            messages.append(msg)

        is_ineff, msg = self.check_ineffective(history)
        if is_ineff:
            pathologies.append(Pathology.INEFFECTIVE)
            messages.append(msg)

        is_wrong, msg = self.check_wrong_attractor(history)
        if is_wrong:
            pathologies.append(Pathology.WRONG_ATTRACTOR)
            messages.append(msg)

        return pathologies, messages

    def to_dict(self) -> dict[str, Any]:
        return {
            "oscillation_window": self.oscillation_window,
            "oscillation_threshold": self.oscillation_threshold,
            "runaway_threshold": self.runaway_threshold,
            "ineffective_epochs": self.ineffective_epochs,
            "wrong_attractor_regimes": self.wrong_attractor_regimes,
            "wrong_attractor_epochs": self.wrong_attractor_epochs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PathologyDetector":
        return cls(
            oscillation_window=data.get("oscillation_window", 6),
            oscillation_threshold=data.get("oscillation_threshold", 3),
            runaway_threshold=data.get("runaway_threshold", 5),
            ineffective_epochs=data.get("ineffective_epochs", 5),
            wrong_attractor_regimes=data.get("wrong_attractor_regimes", ["UNSTABLE", "DUCTILE"]),
            wrong_attractor_epochs=data.get("wrong_attractor_epochs", 3),
        )


# =============================================================================
# Adaptation Decision
# =============================================================================


@dataclass
class AdaptationDecision:
    """Result of adaptation deliberation."""

    verdict: AdaptationVerdict
    parameter: str | None = None
    current_value: float | None = None
    proposed_value: float | None = None
    delta: float | None = None
    was_clamped: bool = False
    reason: str = ""
    trigger_reasons: list[str] = field(default_factory=list)
    pathologies: list[Pathology] = field(default_factory=list)
    pathology_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "delta": self.delta,
            "was_clamped": self.was_clamped,
            "reason": self.reason,
            "trigger_reasons": self.trigger_reasons,
            "pathologies": [p.value for p in self.pathologies],
            "pathology_messages": self.pathology_messages,
        }


# =============================================================================
# Ultrastability Controller
# =============================================================================


class UltrastabilityController:
    """
    Second-order controller for S₁ adaptation.

    Implements Ashby's ultrastability: the system can change its own
    parameters to find stability, but cannot change the rules about
    how it changes parameters (S₀).

    Constitutional constraints:
    - Cannot modify S₀ (NLAI, FSM, forbidden transitions)
    - Cannot exceed bounds on any S₁ parameter
    - Cannot adapt if pathology detected
    - Must log all adaptations for audit
    """

    def __init__(
        self,
        parameters: RegulatoryParameters | None = None,
        trigger: AdaptationTrigger | None = None,
        pathology_detector: PathologyDetector | None = None,
        history: AdaptationHistory | None = None,
    ):
        self.parameters = parameters or RegulatoryParameters()
        self.trigger = trigger or AdaptationTrigger()
        self.pathology_detector = pathology_detector or PathologyDetector()
        self.history = history or AdaptationHistory()

        # Freeze state
        self.frozen = False
        self.freeze_reason: str | None = None
        self.freeze_pathologies: list[Pathology] = []

        # Epoch counter
        self.current_epoch: int = 0

    # =========================================================================
    # Core Loop
    # =========================================================================

    def observe_epoch(self, observation: EpochObservation):
        """Record observations from an epoch."""
        observation.epoch_id = self.current_epoch
        observation.compute_rates()
        self.history.add_epoch(observation)

    def consider_adaptation(self) -> AdaptationDecision:
        """
        Consider whether to adapt S₁ parameters.

        This is the main entry point for the ultrastability loop:
        1. Check if frozen → FREEZE
        2. Check for pathology → ALERT + auto-freeze
        3. Check trigger conditions → HOLD if stable
        4. Select parameter and direction → ADAPT
        """
        # 1. Frozen?
        if self.frozen:
            return AdaptationDecision(
                verdict=AdaptationVerdict.FREEZE,
                reason=f"frozen: {self.freeze_reason}",
                pathologies=list(self.freeze_pathologies),
            )

        # 2. Need observations
        if not self.history.epochs:
            return AdaptationDecision(
                verdict=AdaptationVerdict.HOLD,
                reason="no observations yet",
            )

        current = self.history.epochs[-1]

        # 3. Check for pathologies
        pathologies, messages = self.pathology_detector.detect(self.history)

        if pathologies:
            self.frozen = True
            self.freeze_reason = "; ".join(messages)
            self.freeze_pathologies = pathologies

            return AdaptationDecision(
                verdict=AdaptationVerdict.ALERT,
                reason="pathology detected — adaptation frozen",
                pathologies=pathologies,
                pathology_messages=messages,
            )

        # 4. Check trigger conditions
        should_adapt, trigger_reasons = self.trigger.evaluate(current, self.history)

        if not should_adapt:
            return AdaptationDecision(
                verdict=AdaptationVerdict.HOLD,
                reason="stable",
            )

        # 5. Select adaptation
        return self._select_adaptation(current, trigger_reasons)

    def apply_adaptation(self, decision: AdaptationDecision) -> bool:
        """
        Apply an adaptation decision.

        Returns True if applied, False if rejected.
        """
        if decision.verdict != AdaptationVerdict.ADAPT:
            return False

        if decision.parameter is None or decision.proposed_value is None:
            return False

        # Apply the change
        self.parameters.apply_change(decision.parameter, decision.proposed_value)

        # Log it
        direction = (
            ParameterDirection.INCREASE
            if (decision.delta or 0) >= 0
            else ParameterDirection.DECREASE
        )

        record = AdaptationRecord(
            epoch_id=self.current_epoch,
            timestamp=datetime.now(timezone.utc),
            parameter=decision.parameter,
            old_value=decision.current_value or 0,
            new_value=decision.proposed_value,
            delta=decision.delta or 0,
            was_clamped=decision.was_clamped,
            reason=decision.reason,
            direction=direction,
        )
        self.history.add_record(record)

        return True

    def advance_epoch(self):
        """Move to next epoch."""
        self.current_epoch += 1

    # =========================================================================
    # Freeze / Unfreeze
    # =========================================================================

    def freeze(self, reason: str, pathologies: list[Pathology] | None = None):
        """Manually freeze adaptation."""
        self.frozen = True
        self.freeze_reason = reason
        self.freeze_pathologies = pathologies or []

    def unfreeze(self, reason: str):
        """
        Manually unfreeze after human review.

        This is the only way to resume adaptation after pathology detection.
        """
        self.frozen = False
        self.freeze_reason = None
        self.freeze_pathologies = []

        # Log the unfreeze
        record = AdaptationRecord(
            epoch_id=self.current_epoch,
            timestamp=datetime.now(timezone.utc),
            parameter="_system",
            old_value=0,
            new_value=0,
            delta=0,
            was_clamped=False,
            reason=f"unfreeze: {reason}",
            direction=ParameterDirection.INCREASE,
        )
        self.history.add_record(record)

    # =========================================================================
    # Adaptation Selection
    # =========================================================================

    def _select_adaptation(
        self,
        current: EpochObservation,
        trigger_reasons: list[str],
    ) -> AdaptationDecision:
        """Select which parameter to adapt and by how much."""

        # Strategy: address the most pressing issue

        # If blocking too much → increase budget or reduce cost
        if current.block_rate > self.trigger.block_rate_threshold:
            return self._try_budget_relief(current, trigger_reasons)

        # If accumulating contradictions → increase refill rate
        if current.c_open > self.trigger.c_open_threshold:
            return self._try_accumulation_relief(current, trigger_reasons)

        # If violation rate too high → tighten evidence threshold
        if current.violation_rate > self.trigger.violation_rate_threshold:
            return self._try_tighten_evidence(current, trigger_reasons)

        # If dangerous claims rising → tighten independence
        if current.dangerous_rate > self.trigger.dangerous_rate_threshold:
            return self._try_tighten_independence(current, trigger_reasons)

        # Default: triggered but no clear single action
        return AdaptationDecision(
            verdict=AdaptationVerdict.HOLD,
            reason="triggered but no clear adaptation target",
            trigger_reasons=trigger_reasons,
        )

    def _try_budget_relief(
        self, current: EpochObservation, trigger_reasons: list[str]
    ) -> AdaptationDecision:
        """Try to relieve budget starvation."""
        # Try increasing repair budget first
        spec = self.parameters.get("repair_budget")
        new_val, clamped = spec.propose_change(spec.step)

        if not clamped or new_val != spec.current:
            delta = new_val - spec.current
            return AdaptationDecision(
                verdict=AdaptationVerdict.ADAPT,
                parameter="repair_budget",
                current_value=spec.current,
                proposed_value=new_val,
                delta=delta,
                was_clamped=clamped,
                reason=f"block_rate={current.block_rate:.2f}, increasing repair_budget",
                trigger_reasons=trigger_reasons,
            )

        # Budget at ceiling → try reducing resolution cost
        spec = self.parameters.get("resolution_cost")
        new_val, clamped = spec.propose_change(-spec.step)
        delta = new_val - spec.current

        return AdaptationDecision(
            verdict=AdaptationVerdict.ADAPT,
            parameter="resolution_cost",
            current_value=spec.current,
            proposed_value=new_val,
            delta=delta,
            was_clamped=clamped,
            reason=f"block_rate={current.block_rate:.2f}, reducing resolution_cost",
            trigger_reasons=trigger_reasons,
        )

    def _try_accumulation_relief(
        self, current: EpochObservation, trigger_reasons: list[str]
    ) -> AdaptationDecision:
        """Try to relieve contradiction accumulation."""
        spec = self.parameters.get("refill_rate")
        new_val, clamped = spec.propose_change(spec.step)
        delta = new_val - spec.current

        return AdaptationDecision(
            verdict=AdaptationVerdict.ADAPT,
            parameter="refill_rate",
            current_value=spec.current,
            proposed_value=new_val,
            delta=delta,
            was_clamped=clamped,
            reason=f"c_open={current.c_open}, increasing refill_rate",
            trigger_reasons=trigger_reasons,
        )

    def _try_tighten_evidence(
        self, current: EpochObservation, trigger_reasons: list[str]
    ) -> AdaptationDecision:
        """Tighten evidence threshold to reduce violations."""
        spec = self.parameters.get("evidence_threshold")
        new_val, clamped = spec.propose_change(spec.step)
        delta = new_val - spec.current

        return AdaptationDecision(
            verdict=AdaptationVerdict.ADAPT,
            parameter="evidence_threshold",
            current_value=spec.current,
            proposed_value=new_val,
            delta=delta,
            was_clamped=clamped,
            reason=f"violation_rate={current.violation_rate:.2f}, tightening evidence_threshold",
            trigger_reasons=trigger_reasons,
        )

    def _try_tighten_independence(
        self, current: EpochObservation, trigger_reasons: list[str]
    ) -> AdaptationDecision:
        """Tighten independence threshold to combat dangerous claims."""
        spec = self.parameters.get("independence_threshold")
        new_val, clamped = spec.propose_change(spec.step)
        delta = new_val - spec.current

        return AdaptationDecision(
            verdict=AdaptationVerdict.ADAPT,
            parameter="independence_threshold",
            current_value=spec.current,
            proposed_value=new_val,
            delta=delta,
            was_clamped=clamped,
            reason=f"dangerous_rate={current.dangerous_rate:.2f}, tightening independence_threshold",
            trigger_reasons=trigger_reasons,
        )

    # =========================================================================
    # Queries
    # =========================================================================

    def get_state(self) -> dict[str, Any]:
        """Get current ultrastability state for inspection."""
        return {
            "epoch": self.current_epoch,
            "frozen": self.frozen,
            "freeze_reason": self.freeze_reason,
            "freeze_pathologies": [p.value for p in self.freeze_pathologies],
            "parameters": self.parameters.summary(),
            "recent_epochs": len(self.history.epochs),
            "total_adaptations": self.history.total_adaptations,
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get adaptation metrics."""
        by_param: dict[str, int] = {}
        by_direction: dict[str, int] = {"increase": 0, "decrease": 0}
        clamped_count = 0

        for r in self.history.records:
            if r.parameter == "_system":
                continue
            by_param[r.parameter] = by_param.get(r.parameter, 0) + 1
            by_direction[r.direction.value] += 1
            if r.was_clamped:
                clamped_count += 1

        return {
            "total_epochs": self.current_epoch,
            "total_adaptations": self.history.total_adaptations,
            "adaptations_by_parameter": by_param,
            "adaptations_by_direction": by_direction,
            "clamped_count": clamped_count,
            "frozen": self.frozen,
        }

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters.to_dict(),
            "trigger": self.trigger.to_dict(),
            "pathology_detector": self.pathology_detector.to_dict(),
            "history": self.history.to_dict(),
            "frozen": self.frozen,
            "freeze_reason": self.freeze_reason,
            "freeze_pathologies": [p.value for p in self.freeze_pathologies],
            "current_epoch": self.current_epoch,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UltrastabilityController":
        params = RegulatoryParameters.from_dict(data.get("parameters", {}))
        trigger = AdaptationTrigger.from_dict(data.get("trigger", {}))
        detector = PathologyDetector.from_dict(data.get("pathology_detector", {}))
        history = AdaptationHistory.from_dict(data.get("history", {}))

        ctrl = cls(params, trigger, detector, history)
        ctrl.frozen = data.get("frozen", False)
        ctrl.freeze_reason = data.get("freeze_reason")
        ctrl.freeze_pathologies = [
            Pathology(p) for p in data.get("freeze_pathologies", [])
        ]
        ctrl.current_epoch = data.get("current_epoch", 0)
        return ctrl

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_controller(
    parameters: RegulatoryParameters | None = None,
    trigger: AdaptationTrigger | None = None,
) -> UltrastabilityController:
    """Create an ultrastability controller with optional custom config."""
    return UltrastabilityController(parameters=parameters, trigger=trigger)


def create_default_parameters() -> RegulatoryParameters:
    """Create default regulatory parameters."""
    return RegulatoryParameters()


def observe_and_consider(
    controller: UltrastabilityController,
    turns: int = 0,
    contradictions_opened: int = 0,
    contradictions_closed: int = 0,
    budget_blocks: int = 0,
    c_open: int = 0,
    regime: str = "ELASTIC",
) -> AdaptationDecision:
    """
    Quick helper: observe an epoch and consider adaptation in one step.

    Returns the adaptation decision.
    """
    obs = EpochObservation(
        turns=turns,
        contradictions_opened=contradictions_opened,
        contradictions_closed=contradictions_closed,
        budget_blocks=budget_blocks,
        c_open=c_open,
        regime=regime,
    )
    controller.observe_epoch(obs)
    decision = controller.consider_adaptation()
    controller.advance_epoch()
    return decision
