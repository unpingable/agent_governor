# SPDX-License-Identifier: Apache-2.0
"""
Automated Tuning — Phase E8.

Four sub-features that close the loop on regime detection, setpoints,
resets, and budget allocation:

1. **Threshold Auto-Tuning** — Learn optimal regime thresholds from
   signal distribution data. Suggests new boundaries via percentile
   analysis and false-positive/false-negative rates.

2. **Reset Effectiveness Tracking** — After a reset, observe whether
   the system actually returned to ELASTIC. Tracks at 1/3/5 turns
   post-reset. Aggregates by reset type.

3. **Setpoint Calibration** — Baseline observation phase collects
   natural operating rates, then produces calibrated setpoints with
   a configurable safety margin.

4. **Budget Sweep** — Systematically vary a parameter, measure outcome
   quality vs constraint tightness, and compute the Pareto frontier.

Orchestrated by `AutoTuner`, which delegates to each sub-feature.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from .regime import (
    OperationalRegime,
    RegimeMetrics,
    RegimeSignals,
    RegimeThresholds,
)
from .homeostat import EpistemicSetpoints, EpistemicVitals


# =============================================================================
# Enums
# =============================================================================


class ResetType(str, Enum):
    """Type of reset that was performed."""
    CONTEXT = "context"
    MODE = "mode"
    CHAIN = "chain"
    MANUAL = "manual"
    EMERGENCY = "emergency"


class TuningSuggestionKind(str, Enum):
    """Kind of tuning suggestion."""
    THRESHOLD = "threshold"
    SETPOINT = "setpoint"
    BUDGET = "budget"


class SweepMetric(str, Enum):
    """Metrics measured during a budget sweep."""
    BUDGET_BLOCK_FRACTION = "budget_block_fraction"
    CONTRADICTION_ACCUMULATION = "contradiction_accumulation"
    VIOLATION_RATE = "violation_rate"
    DANGEROUS_RATE = "dangerous_rate"
    REGIME_SEVERITY = "regime_severity"


class CalibrationPhase(str, Enum):
    """Phase of setpoint calibration."""
    BASELINE = "baseline"
    OBSERVATION = "observation"
    ANALYSIS = "analysis"
    COMPLETE = "complete"


# =============================================================================
# Helper: percentile (no numpy)
# =============================================================================


def percentile(values: list[float], p: float) -> float:
    """
    Compute the p-th percentile of a sorted list.

    Uses linear interpolation between closest ranks.
    Raises ValueError on empty list.
    """
    if not values:
        raise ValueError("Cannot compute percentile of empty list")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    # Map p (0-100) to index
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d = k - f
    return sorted_vals[f] * (1 - d) + sorted_vals[c] * d


# =============================================================================
# Sub-feature 1: Threshold Auto-Tuning
# =============================================================================


@dataclass
class SignalDistribution:
    """Distribution statistics for a single signal within a regime."""
    signal_name: str
    count: int
    min_val: float
    max_val: float
    mean: float
    median: float
    p25: float
    p75: float
    p90: float
    p95: float
    stddev: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "count": self.count,
            "min": self.min_val,
            "max": self.max_val,
            "mean": self.mean,
            "median": self.median,
            "p25": self.p25,
            "p75": self.p75,
            "p90": self.p90,
            "p95": self.p95,
            "stddev": self.stddev,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalDistribution:
        return cls(
            signal_name=data["signal_name"],
            count=data["count"],
            min_val=data["min"],
            max_val=data["max"],
            mean=data["mean"],
            median=data["median"],
            p25=data["p25"],
            p75=data["p75"],
            p90=data["p90"],
            p95=data["p95"],
            stddev=data["stddev"],
        )

    @classmethod
    def from_values(cls, signal_name: str, values: list[float]) -> SignalDistribution:
        """Compute distribution from raw values."""
        n = len(values)
        if n == 0:
            return cls(
                signal_name=signal_name,
                count=0, min_val=0.0, max_val=0.0,
                mean=0.0, median=0.0,
                p25=0.0, p75=0.0, p90=0.0, p95=0.0,
                stddev=0.0,
            )
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
        return cls(
            signal_name=signal_name,
            count=n,
            min_val=min(values),
            max_val=max(values),
            mean=mean,
            median=percentile(values, 50),
            p25=percentile(values, 25),
            p75=percentile(values, 75),
            p90=percentile(values, 90),
            p95=percentile(values, 95),
            stddev=math.sqrt(variance),
        )


@dataclass
class RegimeDistributions:
    """Signal distributions for a single regime."""
    regime: OperationalRegime
    sample_count: int
    distributions: dict[str, SignalDistribution] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "sample_count": self.sample_count,
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegimeDistributions:
        return cls(
            regime=OperationalRegime(data["regime"]),
            sample_count=data["sample_count"],
            distributions={
                k: SignalDistribution.from_dict(v)
                for k, v in data.get("distributions", {}).items()
            },
        )


@dataclass
class ClassificationError:
    """A single misclassification instance."""
    signal_name: str
    threshold_name: str
    actual_regime: OperationalRegime
    classified_regime: OperationalRegime
    is_false_positive: bool
    is_false_negative: bool


@dataclass
class ThresholdSuggestion:
    """Suggested change to a threshold."""
    threshold_name: str
    current_value: float
    suggested_value: float
    confidence: float
    reason: str
    fp_rate: float = 0.0
    fn_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_name": self.threshold_name,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
            "reason": self.reason,
            "fp_rate": self.fp_rate,
            "fn_rate": self.fn_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThresholdSuggestion:
        return cls(
            threshold_name=data["threshold_name"],
            current_value=data["current_value"],
            suggested_value=data["suggested_value"],
            confidence=data["confidence"],
            reason=data["reason"],
            fp_rate=data.get("fp_rate", 0.0),
            fn_rate=data.get("fn_rate", 0.0),
        )


@dataclass
class ThresholdAnalysis:
    """Result of threshold analysis."""
    distributions: dict[str, RegimeDistributions]
    suggestions: list[ThresholdSuggestion]
    total_samples: int
    fp_count: int
    fn_count: int
    accuracy: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
            "suggestions": [s.to_dict() for s in self.suggestions],
            "total_samples": self.total_samples,
            "fp_count": self.fp_count,
            "fn_count": self.fn_count,
            "accuracy": self.accuracy,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThresholdAnalysis:
        return cls(
            distributions={
                k: RegimeDistributions.from_dict(v)
                for k, v in data.get("distributions", {}).items()
            },
            suggestions=[ThresholdSuggestion.from_dict(s) for s in data.get("suggestions", [])],
            total_samples=data["total_samples"],
            fp_count=data["fp_count"],
            fn_count=data["fn_count"],
            accuracy=data["accuracy"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


# Mapping: threshold_name -> (signal_name, lower_regime, upper_regime)
# The threshold separates observations from lower_regime (below) and upper_regime (above).
THRESHOLD_MAP: dict[str, tuple[str, OperationalRegime, OperationalRegime]] = {
    "warm_hysteresis": ("hysteresis", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "warm_relaxation": ("relaxation_time", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "warm_anisotropy": ("anisotropy", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "warm_provenance_deficit": ("provenance_deficit", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "warm_rejection_rate": ("rejection_rate", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "warm_dangerous_rate": ("dangerous_claim_rate", OperationalRegime.ELASTIC, OperationalRegime.WARM),
    "ductile_hysteresis": ("hysteresis", OperationalRegime.WARM, OperationalRegime.DUCTILE),
    "ductile_relaxation": ("relaxation_time", OperationalRegime.WARM, OperationalRegime.DUCTILE),
    "ductile_anisotropy": ("anisotropy", OperationalRegime.WARM, OperationalRegime.DUCTILE),
    "ductile_budget_pressure": ("budget_pressure", OperationalRegime.WARM, OperationalRegime.DUCTILE),
    "ductile_rejection_rate": ("rejection_rate", OperationalRegime.WARM, OperationalRegime.DUCTILE),
    "unstable_tool_gain": ("tool_gain", OperationalRegime.DUCTILE, OperationalRegime.UNSTABLE),
    "unstable_budget_pressure": ("budget_pressure", OperationalRegime.DUCTILE, OperationalRegime.UNSTABLE),
    "unstable_dangerous_rate": ("dangerous_claim_rate", OperationalRegime.DUCTILE, OperationalRegime.UNSTABLE),
}

# Signal names that are extractable from RegimeSignals
SIGNAL_NAMES = [
    "hysteresis", "relaxation_time", "tool_gain", "anisotropy",
    "provenance_deficit", "budget_pressure", "contradiction_open_rate",
    "contradiction_close_rate", "rejection_rate", "dangerous_claim_rate",
]


def _extract_signal(signals: RegimeSignals, name: str) -> float:
    """Extract a named signal value from RegimeSignals."""
    return getattr(signals, name)


class ThresholdTuner:
    """
    Learns optimal regime thresholds from signal distribution data.

    Collects observations of (signals, regime) pairs and uses percentile
    analysis to suggest threshold boundary adjustments.
    """

    def __init__(self, min_samples_per_regime: int = 10, max_history: int = 2000):
        self.min_samples_per_regime = min_samples_per_regime
        self.max_history = max_history
        # Stored as (signals_dict, regime)
        self._observations: list[tuple[dict[str, float], OperationalRegime]] = []

    def record(self, signals: RegimeSignals, regime: OperationalRegime) -> None:
        """Add an observation."""
        self._observations.append((signals.to_dict(), regime))
        if len(self._observations) > self.max_history:
            self._observations.pop(0)

    def load_from_metrics(self, metrics: RegimeMetrics) -> int:
        """Bulk load from RegimeMetrics signal history. Returns count loaded."""
        loaded = 0
        for _ts, signals, regime in metrics.signal_history:
            self.record(signals, regime)
            loaded += 1
        return loaded

    def _group_by_regime(self) -> dict[OperationalRegime, list[dict[str, float]]]:
        """Group observations by regime."""
        groups: dict[OperationalRegime, list[dict[str, float]]] = {
            r: [] for r in OperationalRegime
        }
        for sig_dict, regime in self._observations:
            groups[regime].append(sig_dict)
        return groups

    def _compute_distributions(self) -> dict[str, RegimeDistributions]:
        """Compute distributions for each regime."""
        groups = self._group_by_regime()
        result: dict[str, RegimeDistributions] = {}
        for regime, sig_list in groups.items():
            if not sig_list:
                continue
            dists: dict[str, SignalDistribution] = {}
            for sig_name in SIGNAL_NAMES:
                values = [s[sig_name] for s in sig_list if sig_name in s]
                if values:
                    dists[sig_name] = SignalDistribution.from_values(sig_name, values)
            result[regime.value] = RegimeDistributions(
                regime=regime,
                sample_count=len(sig_list),
                distributions=dists,
            )
        return result

    def suggest_thresholds(self, thresholds: RegimeThresholds) -> list[ThresholdSuggestion]:
        """
        Suggest threshold adjustments based on observed distributions.

        For each threshold, finds the boundary at the midpoint between
        p90 of the lower regime and p25 of the upper regime.
        """
        groups = self._group_by_regime()
        suggestions: list[ThresholdSuggestion] = []

        for thresh_name, (sig_name, lower_regime, upper_regime) in THRESHOLD_MAP.items():
            lower_vals = [s[sig_name] for s in groups.get(lower_regime, []) if sig_name in s]
            upper_vals = [s[sig_name] for s in groups.get(upper_regime, []) if sig_name in s]

            if (len(lower_vals) < self.min_samples_per_regime or
                    len(upper_vals) < self.min_samples_per_regime):
                continue

            lower_p90 = percentile(lower_vals, 90)
            upper_p25 = percentile(upper_vals, 25)
            current = getattr(thresholds, thresh_name)

            if upper_p25 <= lower_p90:
                # Overlapping distributions — low confidence suggestion
                midpoint = (lower_p90 + upper_p25) / 2.0
                confidence = 0.3
                reason = (
                    f"Overlapping distributions: lower p90={lower_p90:.3f}, "
                    f"upper p25={upper_p25:.3f}"
                )
            else:
                midpoint = (lower_p90 + upper_p25) / 2.0
                gap = upper_p25 - lower_p90
                # Wider gap = higher confidence
                confidence = min(0.95, 0.5 + gap * 2.0)
                reason = (
                    f"Clear boundary: lower p90={lower_p90:.3f}, "
                    f"upper p25={upper_p25:.3f}, gap={gap:.3f}"
                )

            # Compute fp/fn rates for the suggestion
            fp_count = sum(1 for v in lower_vals if v >= midpoint)
            fn_count = sum(1 for v in upper_vals if v < midpoint)
            fp_rate = fp_count / len(lower_vals) if lower_vals else 0.0
            fn_rate = fn_count / len(upper_vals) if upper_vals else 0.0

            if abs(midpoint - current) > 0.001:
                suggestions.append(ThresholdSuggestion(
                    threshold_name=thresh_name,
                    current_value=current,
                    suggested_value=round(midpoint, 4),
                    confidence=round(confidence, 3),
                    reason=reason,
                    fp_rate=round(fp_rate, 3),
                    fn_rate=round(fn_rate, 3),
                ))

        return suggestions

    def analyze(self, thresholds: RegimeThresholds) -> ThresholdAnalysis:
        """Full analysis: distributions, suggestions, error rates."""
        distributions = self._compute_distributions()
        suggestions = self.suggest_thresholds(thresholds)

        # Count total errors using current thresholds
        total_fp = 0
        total_fn = 0
        total_correct = 0
        groups = self._group_by_regime()

        for thresh_name, (sig_name, lower_regime, upper_regime) in THRESHOLD_MAP.items():
            current = getattr(thresholds, thresh_name)
            lower_vals = [s[sig_name] for s in groups.get(lower_regime, []) if sig_name in s]
            upper_vals = [s[sig_name] for s in groups.get(upper_regime, []) if sig_name in s]

            for v in lower_vals:
                if v >= current:
                    total_fp += 1
                else:
                    total_correct += 1
            for v in upper_vals:
                if v < current:
                    total_fn += 1
                else:
                    total_correct += 1

        total = total_correct + total_fp + total_fn
        accuracy = total_correct / total if total > 0 else 1.0

        return ThresholdAnalysis(
            distributions=distributions,
            suggestions=suggestions,
            total_samples=len(self._observations),
            fp_count=total_fp,
            fn_count=total_fn,
            accuracy=round(accuracy, 4),
        )

    def apply_suggestions(
        self,
        thresholds: RegimeThresholds,
        suggestions: list[ThresholdSuggestion],
        min_confidence: float = 0.5,
    ) -> RegimeThresholds:
        """Apply suggestions that meet the confidence threshold."""
        data = thresholds.to_dict()
        for s in suggestions:
            if s.confidence >= min_confidence and s.threshold_name in data:
                data[s.threshold_name] = s.suggested_value
        return RegimeThresholds.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_samples_per_regime": self.min_samples_per_regime,
            "max_history": self.max_history,
            "observations": [
                {"signals": sig, "regime": regime.value}
                for sig, regime in self._observations
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThresholdTuner:
        tuner = cls(
            min_samples_per_regime=data.get("min_samples_per_regime", 10),
            max_history=data.get("max_history", 2000),
        )
        for obs in data.get("observations", []):
            tuner._observations.append((
                obs["signals"],
                OperationalRegime(obs["regime"]),
            ))
        return tuner


# =============================================================================
# Sub-feature 2: Reset Effectiveness Tracking
# =============================================================================


@dataclass
class ResetCheckpoint:
    """Observation at a specific number of turns after a reset."""
    turns_after: int
    regime: OperationalRegime
    signals: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns_after": self.turns_after,
            "regime": self.regime.value,
            "signals": self.signals,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResetCheckpoint:
        return cls(
            turns_after=data["turns_after"],
            regime=OperationalRegime(data["regime"]),
            signals=data.get("signals"),
        )


@dataclass
class ResetRecord:
    """Record of a single reset and its aftermath."""
    reset_id: str
    reset_type: ResetType
    reset_turn: int
    regime_at_reset: OperationalRegime
    checkpoints: list[ResetCheckpoint] = field(default_factory=list)
    restored_elastic: bool = False
    turns_to_restore: int | None = None
    complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "reset_id": self.reset_id,
            "reset_type": self.reset_type.value,
            "reset_turn": self.reset_turn,
            "regime_at_reset": self.regime_at_reset.value,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "restored_elastic": self.restored_elastic,
            "turns_to_restore": self.turns_to_restore,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResetRecord:
        return cls(
            reset_id=data["reset_id"],
            reset_type=ResetType(data["reset_type"]),
            reset_turn=data["reset_turn"],
            regime_at_reset=OperationalRegime(data["regime_at_reset"]),
            checkpoints=[ResetCheckpoint.from_dict(c) for c in data.get("checkpoints", [])],
            restored_elastic=data.get("restored_elastic", False),
            turns_to_restore=data.get("turns_to_restore"),
            complete=data.get("complete", False),
        )


@dataclass
class ResetTypeSummary:
    """Summary statistics for one reset type."""
    reset_type: ResetType
    total: int
    restored_count: int
    success_rate: float
    avg_turns_to_restore: float | None
    regime_distribution_after_5: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reset_type": self.reset_type.value,
            "total": self.total,
            "restored_count": self.restored_count,
            "success_rate": self.success_rate,
            "avg_turns_to_restore": self.avg_turns_to_restore,
            "regime_distribution_after_5": self.regime_distribution_after_5,
        }


@dataclass
class ResetReport:
    """Aggregate report across all reset types."""
    total_resets: int
    total_completed: int
    overall_success_rate: float
    by_type: dict[str, ResetTypeSummary] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_resets": self.total_resets,
            "total_completed": self.total_completed,
            "overall_success_rate": self.overall_success_rate,
            "by_type": {k: v.to_dict() for k, v in self.by_type.items()},
        }


class ResetTracker:
    """
    Tracks reset effectiveness by observing regime at checkpoints
    after each reset.
    """

    CHECKPOINT_TURNS = [1, 3, 5]

    def __init__(self, max_records: int = 200):
        self.max_records = max_records
        self._records: list[ResetRecord] = []
        self._current_turn: int = 0

    def record_reset(
        self,
        reset_id: str,
        reset_type: ResetType,
        regime_at_reset: OperationalRegime,
    ) -> ResetRecord:
        """Record that a reset occurred."""
        record = ResetRecord(
            reset_id=reset_id,
            reset_type=reset_type,
            reset_turn=self._current_turn,
            regime_at_reset=regime_at_reset,
        )
        self._records.append(record)
        if len(self._records) > self.max_records:
            self._records.pop(0)
        return record

    def advance_turn(
        self,
        current_regime: OperationalRegime,
        signals: RegimeSignals | None = None,
    ) -> list[ResetRecord]:
        """Advance turn and fill checkpoints for pending resets."""
        self._current_turn += 1
        sig_dict = signals.to_dict() if signals else None
        completed: list[ResetRecord] = []

        for record in self._records:
            if record.complete:
                continue
            turns_since = self._current_turn - record.reset_turn
            if turns_since in self.CHECKPOINT_TURNS:
                checkpoint = ResetCheckpoint(
                    turns_after=turns_since,
                    regime=current_regime,
                    signals=sig_dict,
                )
                record.checkpoints.append(checkpoint)

                # Check if restored to elastic
                if current_regime == OperationalRegime.ELASTIC and not record.restored_elastic:
                    record.restored_elastic = True
                    record.turns_to_restore = turns_since

                # Complete after last checkpoint
                if turns_since == self.CHECKPOINT_TURNS[-1]:
                    record.complete = True
                    completed.append(record)

        return completed

    def report(self) -> ResetReport:
        """Generate aggregate report."""
        completed = [r for r in self._records if r.complete]
        total_restored = sum(1 for r in completed if r.restored_elastic)
        overall_rate = total_restored / len(completed) if completed else 0.0

        # Group by type
        by_type: dict[str, list[ResetRecord]] = {}
        for r in completed:
            key = r.reset_type.value
            by_type.setdefault(key, []).append(r)

        summaries: dict[str, ResetTypeSummary] = {}
        for type_val, records in by_type.items():
            restored = [r for r in records if r.restored_elastic]
            restore_turns = [r.turns_to_restore for r in restored if r.turns_to_restore is not None]
            avg_restore = sum(restore_turns) / len(restore_turns) if restore_turns else None

            # Regime distribution at turn 5
            regime_dist: dict[str, int] = {}
            for r in records:
                for cp in r.checkpoints:
                    if cp.turns_after == 5:
                        rv = cp.regime.value
                        regime_dist[rv] = regime_dist.get(rv, 0) + 1

            summaries[type_val] = ResetTypeSummary(
                reset_type=ResetType(type_val),
                total=len(records),
                restored_count=len(restored),
                success_rate=len(restored) / len(records) if records else 0.0,
                avg_turns_to_restore=avg_restore,
                regime_distribution_after_5=regime_dist,
            )

        return ResetReport(
            total_resets=len(self._records),
            total_completed=len(completed),
            overall_success_rate=overall_rate,
            by_type=summaries,
        )

    def success_rate_by_type(self, reset_type: ResetType) -> float | None:
        """Get success rate for a specific reset type. None if no data."""
        completed = [
            r for r in self._records
            if r.complete and r.reset_type == reset_type
        ]
        if not completed:
            return None
        restored = sum(1 for r in completed if r.restored_elastic)
        return restored / len(completed)

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self._records if not r.complete)

    @property
    def completed_count(self) -> int:
        return sum(1 for r in self._records if r.complete)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_records": self.max_records,
            "current_turn": self._current_turn,
            "records": [r.to_dict() for r in self._records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResetTracker:
        tracker = cls(max_records=data.get("max_records", 200))
        tracker._current_turn = data.get("current_turn", 0)
        tracker._records = [ResetRecord.from_dict(r) for r in data.get("records", [])]
        return tracker


# =============================================================================
# Sub-feature 3: Setpoint Calibration
# =============================================================================


@dataclass
class BaselineObservation:
    """Single observation during baseline collection."""
    turn: int
    vitals: dict[str, float]
    regime: OperationalRegime

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "vitals": self.vitals,
            "regime": self.regime.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineObservation:
        return cls(
            turn=data["turn"],
            vitals=data["vitals"],
            regime=OperationalRegime(data["regime"]),
        )


@dataclass
class BaselineProfile:
    """Baseline operating profile computed from observations."""
    domain: str
    observation_count: int
    # Natural operating rates
    natural_revision_rate: float = 0.0
    natural_contradiction_rate: float = 0.0
    natural_hedge_rate: float = 0.0
    natural_refusal_rate: float = 0.0
    natural_support_deficit_rate: float = 0.0
    natural_retrieval_coverage: float = 1.0
    # Standard deviations
    revision_stddev: float = 0.0
    contradiction_stddev: float = 0.0
    hedge_stddev: float = 0.0
    refusal_stddev: float = 0.0
    support_deficit_stddev: float = 0.0
    retrieval_coverage_stddev: float = 0.0
    # Correlation
    revision_retraction_correlation: float = 0.0

    def to_setpoints(self, safety_margin: float = 1.5) -> EpistemicSetpoints:
        """
        Convert baseline to setpoints with safety margin.

        Setpoint = natural_rate + safety_margin * stddev
        """
        return EpistemicSetpoints(
            revision_target=min(1.0, self.natural_revision_rate + safety_margin * self.revision_stddev),
            contradiction_target=min(1.0, self.natural_contradiction_rate + safety_margin * self.contradiction_stddev),
            hedge_target=min(1.0, self.natural_hedge_rate + safety_margin * self.hedge_stddev),
            refusal_target=min(1.0, self.natural_refusal_rate + safety_margin * self.refusal_stddev),
            support_deficit_target=min(1.0, self.natural_support_deficit_rate + safety_margin * self.support_deficit_stddev),
            retrieval_coverage_target=max(0.0, self.natural_retrieval_coverage - safety_margin * self.retrieval_coverage_stddev),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "observation_count": self.observation_count,
            "natural_revision_rate": self.natural_revision_rate,
            "natural_contradiction_rate": self.natural_contradiction_rate,
            "natural_hedge_rate": self.natural_hedge_rate,
            "natural_refusal_rate": self.natural_refusal_rate,
            "natural_support_deficit_rate": self.natural_support_deficit_rate,
            "natural_retrieval_coverage": self.natural_retrieval_coverage,
            "revision_stddev": self.revision_stddev,
            "contradiction_stddev": self.contradiction_stddev,
            "hedge_stddev": self.hedge_stddev,
            "refusal_stddev": self.refusal_stddev,
            "support_deficit_stddev": self.support_deficit_stddev,
            "retrieval_coverage_stddev": self.retrieval_coverage_stddev,
            "revision_retraction_correlation": self.revision_retraction_correlation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineProfile:
        return cls(
            domain=data["domain"],
            observation_count=data["observation_count"],
            natural_revision_rate=data.get("natural_revision_rate", 0.0),
            natural_contradiction_rate=data.get("natural_contradiction_rate", 0.0),
            natural_hedge_rate=data.get("natural_hedge_rate", 0.0),
            natural_refusal_rate=data.get("natural_refusal_rate", 0.0),
            natural_support_deficit_rate=data.get("natural_support_deficit_rate", 0.0),
            natural_retrieval_coverage=data.get("natural_retrieval_coverage", 1.0),
            revision_stddev=data.get("revision_stddev", 0.0),
            contradiction_stddev=data.get("contradiction_stddev", 0.0),
            hedge_stddev=data.get("hedge_stddev", 0.0),
            refusal_stddev=data.get("refusal_stddev", 0.0),
            support_deficit_stddev=data.get("support_deficit_stddev", 0.0),
            retrieval_coverage_stddev=data.get("retrieval_coverage_stddev", 0.0),
            revision_retraction_correlation=data.get("revision_retraction_correlation", 0.0),
        )


@dataclass
class CalibrationResult:
    """Result of a calibration run."""
    domain: str
    phase: CalibrationPhase
    baseline: BaselineProfile | None
    calibrated_setpoints: EpistemicSetpoints | None
    observation_count: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "phase": self.phase.value,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "calibrated_setpoints": self.calibrated_setpoints.to_dict() if self.calibrated_setpoints else None,
            "observation_count": self.observation_count,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationResult:
        baseline = BaselineProfile.from_dict(data["baseline"]) if data.get("baseline") else None
        setpoints = EpistemicSetpoints.from_dict(data["calibrated_setpoints"]) if data.get("calibrated_setpoints") else None
        return cls(
            domain=data["domain"],
            phase=CalibrationPhase(data["phase"]),
            baseline=baseline,
            calibrated_setpoints=setpoints,
            observation_count=data["observation_count"],
            confidence=data["confidence"],
        )


class SetpointCalibrator:
    """
    Calibrates epistemic setpoints from observed natural operating rates.

    Workflow:
    1. begin_baseline() -> collect observations -> end_baseline()
    2. begin_observation() -> collect more -> calibrate()
    """

    MIN_BASELINE_SAMPLES = 20

    def __init__(self, domain: str = "general", safety_margin: float = 1.5):
        self.domain = domain
        self.safety_margin = safety_margin
        self.phase = CalibrationPhase.BASELINE
        self._baseline_observations: list[BaselineObservation] = []
        self._observation_observations: list[BaselineObservation] = []
        self._baseline_profile: BaselineProfile | None = None
        self._turn: int = 0
        self._baseline_started: bool = False
        self._observation_started: bool = False

    def begin_baseline(self) -> None:
        """Start baseline collection phase."""
        self.phase = CalibrationPhase.BASELINE
        self._baseline_observations.clear()
        self._baseline_started = True

    def record_baseline(self, vitals: EpistemicVitals, regime: OperationalRegime) -> None:
        """Record a baseline observation."""
        self._turn += 1
        self._baseline_observations.append(BaselineObservation(
            turn=self._turn,
            vitals=vitals.to_dict(),
            regime=regime,
        ))

    def end_baseline(self) -> BaselineProfile | None:
        """End baseline collection and compute profile. Returns None if insufficient data."""
        if len(self._baseline_observations) < self.MIN_BASELINE_SAMPLES:
            return None

        # Compute natural rates from observations
        revisions = [o.vitals["revision_rate"] for o in self._baseline_observations]
        contradictions = [o.vitals["contradiction_rate"] for o in self._baseline_observations]
        hedges = [o.vitals["hedge_rate"] for o in self._baseline_observations]
        refusals = [o.vitals["refusal_rate"] for o in self._baseline_observations]
        support_deficits = [o.vitals["support_deficit_rate"] for o in self._baseline_observations]
        retrieval_coverages = [o.vitals["retrieval_coverage"] for o in self._baseline_observations]

        n = len(self._baseline_observations)

        def _mean(vs: list[float]) -> float:
            return sum(vs) / len(vs) if vs else 0.0

        def _stddev(vs: list[float]) -> float:
            if len(vs) < 2:
                return 0.0
            m = _mean(vs)
            return math.sqrt(sum((v - m) ** 2 for v in vs) / (len(vs) - 1))

        # Revision-retraction correlation (using contradiction as proxy for retraction)
        corr = self._compute_correlation(revisions, contradictions)

        self._baseline_profile = BaselineProfile(
            domain=self.domain,
            observation_count=n,
            natural_revision_rate=_mean(revisions),
            natural_contradiction_rate=_mean(contradictions),
            natural_hedge_rate=_mean(hedges),
            natural_refusal_rate=_mean(refusals),
            natural_support_deficit_rate=_mean(support_deficits),
            natural_retrieval_coverage=_mean(retrieval_coverages),
            revision_stddev=_stddev(revisions),
            contradiction_stddev=_stddev(contradictions),
            hedge_stddev=_stddev(hedges),
            refusal_stddev=_stddev(refusals),
            support_deficit_stddev=_stddev(support_deficits),
            retrieval_coverage_stddev=_stddev(retrieval_coverages),
            revision_retraction_correlation=corr,
        )
        self.phase = CalibrationPhase.ANALYSIS
        return self._baseline_profile

    def begin_observation(self) -> None:
        """Start observation phase (after baseline)."""
        self.phase = CalibrationPhase.OBSERVATION
        self._observation_observations.clear()
        self._observation_started = True

    def record_observation(self, vitals: EpistemicVitals, regime: OperationalRegime) -> None:
        """Record an observation during observation phase."""
        self._turn += 1
        self._observation_observations.append(BaselineObservation(
            turn=self._turn,
            vitals=vitals.to_dict(),
            regime=regime,
        ))

    def calibrate(self, safety_margin: float | None = None) -> CalibrationResult:
        """
        Compute calibrated setpoints from baseline profile.

        Uses observation data if available, otherwise baseline only.
        """
        margin = safety_margin if safety_margin is not None else self.safety_margin

        if self._baseline_profile is None:
            return CalibrationResult(
                domain=self.domain,
                phase=self.phase,
                baseline=None,
                calibrated_setpoints=None,
                observation_count=len(self._baseline_observations),
                confidence=0.0,
            )

        setpoints = self._baseline_profile.to_setpoints(margin)
        obs_count = len(self._baseline_observations) + len(self._observation_observations)

        # Confidence scales with sample count (saturates around 100)
        confidence = min(0.95, obs_count / 100.0)

        self.phase = CalibrationPhase.COMPLETE
        return CalibrationResult(
            domain=self.domain,
            phase=self.phase,
            baseline=self._baseline_profile,
            calibrated_setpoints=setpoints,
            observation_count=obs_count,
            confidence=round(confidence, 3),
        )

    @staticmethod
    def _compute_correlation(xs: list[float], ys: list[float]) -> float:
        """Compute Pearson correlation coefficient."""
        n = len(xs)
        if n < 2 or n != len(ys):
            return 0.0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n
        std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / n)
        std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / n)
        if std_x < 1e-10 or std_y < 1e-10:
            return 0.0
        return cov / (std_x * std_y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "safety_margin": self.safety_margin,
            "phase": self.phase.value,
            "turn": self._turn,
            "baseline_observations": [o.to_dict() for o in self._baseline_observations],
            "observation_observations": [o.to_dict() for o in self._observation_observations],
            "baseline_profile": self._baseline_profile.to_dict() if self._baseline_profile else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SetpointCalibrator:
        cal = cls(
            domain=data.get("domain", "general"),
            safety_margin=data.get("safety_margin", 1.5),
        )
        cal.phase = CalibrationPhase(data.get("phase", "baseline"))
        cal._turn = data.get("turn", 0)
        cal._baseline_observations = [
            BaselineObservation.from_dict(o)
            for o in data.get("baseline_observations", [])
        ]
        cal._observation_observations = [
            BaselineObservation.from_dict(o)
            for o in data.get("observation_observations", [])
        ]
        if data.get("baseline_profile"):
            cal._baseline_profile = BaselineProfile.from_dict(data["baseline_profile"])
        return cal


# =============================================================================
# Sub-feature 4: Budget Sweep
# =============================================================================


@dataclass
class SweepPoint:
    """A single measurement point during a budget sweep."""
    parameter_name: str
    parameter_value: float
    turns: int
    budget_block_fraction: float
    contradiction_accumulation: float
    violation_rate: float
    dangerous_rate: float
    regime_at_end: OperationalRegime
    regime_severity_avg: float
    c_open_final: int
    c_open_max: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "turns": self.turns,
            "budget_block_fraction": self.budget_block_fraction,
            "contradiction_accumulation": self.contradiction_accumulation,
            "violation_rate": self.violation_rate,
            "dangerous_rate": self.dangerous_rate,
            "regime_at_end": self.regime_at_end.value,
            "regime_severity_avg": self.regime_severity_avg,
            "c_open_final": self.c_open_final,
            "c_open_max": self.c_open_max,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SweepPoint:
        return cls(
            parameter_name=data["parameter_name"],
            parameter_value=data["parameter_value"],
            turns=data["turns"],
            budget_block_fraction=data["budget_block_fraction"],
            contradiction_accumulation=data["contradiction_accumulation"],
            violation_rate=data["violation_rate"],
            dangerous_rate=data["dangerous_rate"],
            regime_at_end=OperationalRegime(data["regime_at_end"]),
            regime_severity_avg=data["regime_severity_avg"],
            c_open_final=data["c_open_final"],
            c_open_max=data["c_open_max"],
        )


@dataclass
class ParetoPoint:
    """A point on the Pareto frontier."""
    parameter_value: float
    quality_score: float
    constraint_tightness: float
    dominates: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_value": self.parameter_value,
            "quality_score": self.quality_score,
            "constraint_tightness": self.constraint_tightness,
            "dominates": self.dominates,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParetoPoint:
        return cls(
            parameter_value=data["parameter_value"],
            quality_score=data["quality_score"],
            constraint_tightness=data["constraint_tightness"],
            dominates=data.get("dominates", []),
        )


@dataclass
class SweepResult:
    """Result of a budget sweep experiment."""
    parameter_name: str
    sweep_values: list[float]
    points: list[SweepPoint]
    pareto_frontier: list[ParetoPoint]
    recommended_value: float | None
    safety_invariant_held: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "sweep_values": self.sweep_values,
            "points": [p.to_dict() for p in self.points],
            "pareto_frontier": [p.to_dict() for p in self.pareto_frontier],
            "recommended_value": self.recommended_value,
            "safety_invariant_held": self.safety_invariant_held,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SweepResult:
        return cls(
            parameter_name=data["parameter_name"],
            sweep_values=data["sweep_values"],
            points=[SweepPoint.from_dict(p) for p in data.get("points", [])],
            pareto_frontier=[ParetoPoint.from_dict(p) for p in data.get("pareto_frontier", [])],
            recommended_value=data.get("recommended_value"),
            safety_invariant_held=data.get("safety_invariant_held", True),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
        )


# Default quality weights: negative = penalty
DEFAULT_QUALITY_WEIGHTS: dict[str, float] = {
    "budget_block_fraction": -2.0,
    "contradiction_accumulation": -3.0,
    "violation_rate": -2.0,
    "dangerous_rate": -4.0,
    "regime_severity": -1.5,
}


class BudgetSweeper:
    """
    Systematically varies a parameter and measures outcome quality
    vs constraint tightness to find the Pareto frontier.
    """

    def __init__(
        self,
        parameter_name: str,
        quality_weights: dict[str, float] | None = None,
    ):
        self.parameter_name = parameter_name
        self.quality_weights = quality_weights or dict(DEFAULT_QUALITY_WEIGHTS)
        self._points: list[SweepPoint] = []

    def record_point(
        self,
        parameter_value: float,
        turns: int,
        budget_block_fraction: float,
        contradiction_accumulation: float,
        violation_rate: float,
        dangerous_rate: float,
        regime_at_end: OperationalRegime,
        regime_severity_avg: float,
        c_open_final: int = 0,
        c_open_max: int = 0,
    ) -> SweepPoint:
        """Record a single sweep measurement."""
        point = SweepPoint(
            parameter_name=self.parameter_name,
            parameter_value=parameter_value,
            turns=turns,
            budget_block_fraction=budget_block_fraction,
            contradiction_accumulation=contradiction_accumulation,
            violation_rate=violation_rate,
            dangerous_rate=dangerous_rate,
            regime_at_end=regime_at_end,
            regime_severity_avg=regime_severity_avg,
            c_open_final=c_open_final,
            c_open_max=c_open_max,
        )
        self._points.append(point)
        return point

    def _compute_quality(self, point: SweepPoint) -> float:
        """Compute quality score for a single point."""
        w = self.quality_weights
        score = 0.0
        score += w.get("budget_block_fraction", 0.0) * point.budget_block_fraction
        score += w.get("contradiction_accumulation", 0.0) * point.contradiction_accumulation
        score += w.get("violation_rate", 0.0) * point.violation_rate
        score += w.get("dangerous_rate", 0.0) * point.dangerous_rate
        score += w.get("regime_severity", 0.0) * point.regime_severity_avg
        return score

    def _compute_tightness(self, point: SweepPoint) -> float:
        """
        Compute constraint tightness for a point.

        Higher value = tighter constraints (less freedom).
        We use budget_block_fraction + regime_severity as proxy.
        """
        return point.budget_block_fraction + point.regime_severity_avg / 3.0

    def _compute_pareto_frontier(self) -> list[ParetoPoint]:
        """
        Compute Pareto frontier via non-dominated sort.

        A point is Pareto-optimal if no other point is better on BOTH
        quality and tightness (lower tightness is better).
        """
        if not self._points:
            return []

        scored: list[tuple[SweepPoint, float, float]] = []
        for p in self._points:
            q = self._compute_quality(p)
            t = self._compute_tightness(p)
            scored.append((p, q, t))

        frontier: list[ParetoPoint] = []
        for i, (pi, qi, ti) in enumerate(scored):
            dominated = False
            dominates_list: list[float] = []
            for j, (pj, qj, tj) in enumerate(scored):
                if i == j:
                    continue
                # j dominates i if j is >= on both objectives and strictly > on at least one
                if qj >= qi and tj <= ti and (qj > qi or tj < ti):
                    dominated = True
                    break
                # i dominates j
                if qi >= qj and ti <= tj and (qi > qj or ti < tj):
                    dominates_list.append(pj.parameter_value)
            if not dominated:
                frontier.append(ParetoPoint(
                    parameter_value=pi.parameter_value,
                    quality_score=round(qi, 4),
                    constraint_tightness=round(ti, 4),
                    dominates=dominates_list,
                ))

        # Sort frontier by parameter value
        frontier.sort(key=lambda p: p.parameter_value)
        return frontier

    def analyze(self) -> SweepResult:
        """Analyze all recorded points and produce a sweep result."""
        pareto = self._compute_pareto_frontier()

        # Recommend: best quality on Pareto frontier
        recommended = None
        if pareto:
            best = max(pareto, key=lambda p: p.quality_score)
            recommended = best.parameter_value

        # Safety invariant: no point ended in UNSTABLE
        safety_held = all(
            p.regime_at_end != OperationalRegime.UNSTABLE
            for p in self._points
        )

        return SweepResult(
            parameter_name=self.parameter_name,
            sweep_values=[p.parameter_value for p in self._points],
            points=list(self._points),
            pareto_frontier=pareto,
            recommended_value=recommended,
            safety_invariant_held=safety_held,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "quality_weights": self.quality_weights,
            "points": [p.to_dict() for p in self._points],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetSweeper:
        sweeper = cls(
            parameter_name=data["parameter_name"],
            quality_weights=data.get("quality_weights", dict(DEFAULT_QUALITY_WEIGHTS)),
        )
        sweeper._points = [SweepPoint.from_dict(p) for p in data.get("points", [])]
        return sweeper


# =============================================================================
# Orchestrator: AutoTuner
# =============================================================================


class AutoTuner:
    """
    Orchestrator that delegates to each sub-feature.

    Provides a unified interface for recording data and getting status.
    """

    def __init__(
        self,
        threshold_tuner: ThresholdTuner | None = None,
        reset_tracker: ResetTracker | None = None,
        setpoint_calibrator: SetpointCalibrator | None = None,
    ):
        self.threshold_tuner = threshold_tuner or ThresholdTuner()
        self.reset_tracker = reset_tracker or ResetTracker()
        self.setpoint_calibrator = setpoint_calibrator or SetpointCalibrator()

    def record_signal(self, signals: RegimeSignals, regime: OperationalRegime) -> None:
        """Record a signal observation for threshold tuning."""
        self.threshold_tuner.record(signals, regime)

    def record_reset(
        self,
        reset_type: ResetType,
        regime_at_reset: OperationalRegime,
        reset_id: str | None = None,
    ) -> ResetRecord:
        """Record a reset event."""
        rid = reset_id or str(uuid.uuid4())[:8]
        return self.reset_tracker.record_reset(rid, reset_type, regime_at_reset)

    def advance_turn(
        self,
        current_regime: OperationalRegime,
        signals: RegimeSignals | None = None,
    ) -> list[ResetRecord]:
        """Advance turn for reset tracking."""
        return self.reset_tracker.advance_turn(current_regime, signals)

    def analyze_thresholds(self, thresholds: RegimeThresholds) -> ThresholdAnalysis:
        """Run threshold analysis."""
        return self.threshold_tuner.analyze(thresholds)

    def reset_report(self) -> ResetReport:
        """Get reset effectiveness report."""
        return self.reset_tracker.report()

    def get_status(self) -> dict[str, Any]:
        """Get status of all tuning sub-features."""
        return {
            "threshold_tuner": {
                "observations": len(self.threshold_tuner._observations),
                "min_samples_per_regime": self.threshold_tuner.min_samples_per_regime,
            },
            "reset_tracker": {
                "total_records": len(self.reset_tracker._records),
                "pending": self.reset_tracker.pending_count,
                "completed": self.reset_tracker.completed_count,
            },
            "setpoint_calibrator": {
                "domain": self.setpoint_calibrator.domain,
                "phase": self.setpoint_calibrator.phase.value,
                "baseline_observations": len(self.setpoint_calibrator._baseline_observations),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_tuner": self.threshold_tuner.to_dict(),
            "reset_tracker": self.reset_tracker.to_dict(),
            "setpoint_calibrator": self.setpoint_calibrator.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoTuner:
        return cls(
            threshold_tuner=ThresholdTuner.from_dict(data.get("threshold_tuner", {}))
            if data.get("threshold_tuner") else None,
            reset_tracker=ResetTracker.from_dict(data.get("reset_tracker", {}))
            if data.get("reset_tracker") else None,
            setpoint_calibrator=SetpointCalibrator.from_dict(data.get("setpoint_calibrator", {}))
            if data.get("setpoint_calibrator") else None,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def create_auto_tuner(domain: str = "general") -> AutoTuner:
    """Create an AutoTuner with default sub-features."""
    return AutoTuner(
        threshold_tuner=ThresholdTuner(),
        reset_tracker=ResetTracker(),
        setpoint_calibrator=SetpointCalibrator(domain=domain),
    )


def create_threshold_tuner(min_samples: int = 10) -> ThresholdTuner:
    """Create a ThresholdTuner with specified minimum samples."""
    return ThresholdTuner(min_samples_per_regime=min_samples)


def create_reset_tracker() -> ResetTracker:
    """Create a ResetTracker with default settings."""
    return ResetTracker()


def create_setpoint_calibrator(
    domain: str = "general",
    safety_margin: float = 1.5,
) -> SetpointCalibrator:
    """Create a SetpointCalibrator for a domain."""
    return SetpointCalibrator(domain=domain, safety_margin=safety_margin)


def create_budget_sweeper(parameter_name: str) -> BudgetSweeper:
    """Create a BudgetSweeper for a named parameter."""
    return BudgetSweeper(parameter_name=parameter_name)


def analyze_thresholds_from_metrics(
    metrics: RegimeMetrics,
    thresholds: RegimeThresholds,
) -> ThresholdAnalysis:
    """One-shot: load metrics into a tuner and analyze."""
    tuner = ThresholdTuner()
    tuner.load_from_metrics(metrics)
    return tuner.analyze(thresholds)
