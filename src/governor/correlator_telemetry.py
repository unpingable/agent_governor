"""
Correlator telemetry: Capture detection for the governor.

The governor is a correlator, not just a brake. Temporal mismatch is signed:
constructive (leverage) or destructive (shear) depending on correlator quality
K = (T, F, A, C). The system handles shear well. What's missing is capture
detection — when everything gets "too smooth" because the system produces false
coherence by killing degrees of freedom.

Zero contradictions under nonzero exposure should be suspicious, not clean.

Key concepts (Paper 16, "The Gain Geometry of Temporal Mismatch"):
- K-vector: (Throughput, Fidelity, Authority, Cost) — do NOT scalarize
- Capture: high throughput + authority, low fidelity (false coherence)
- Proposition 4.2: four capture indicators
- Proposition 5.3: contradiction suppression inversion

Design decisions (from review):
1. Indicators always computed (pre-gate), labeled binding/non-binding for dashboard
2. Mode-count normalized by exposure (mode_per_exposure), not raw count
3. Entropy gated by exposure minimum — stagnant entropy in idle is not capture
4. Contradiction uses generated_objections (not just open) — resolved != suppressed
5. Commitment shear = loss_ratio (lost/total at boundary), not vibes
6. cost_budget > threshold → DEGRADED_CAPACITY flag, not automatic SHEAR
7. Hysteresis on all indicators + capture regime (consecutive windows)

Architecture:
- Pure functions for all detection logic (no subsystem imports at module level)
- Stateful coordinator (CorrelatorTelemetry) wraps pure functions + persistence
- Signals consumed from existing subsystems via dicts, not direct imports
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class CorrelatorRegime(str, Enum):
    """Regime classification for the governor-as-correlator."""

    LEVERAGE = "leverage"
    """Baseline within correlator limits, high fidelity."""

    SHEAR = "shear"
    """Baseline exceeds correlator capacity (T < t_min AND A blocking, or backlog)."""

    CAPTURE = "capture"
    """High throughput + authority, low fidelity (false coherence)."""

    UNKNOWN = "unknown"
    """Insufficient data for classification."""


class CaptureIndicator(str, Enum):
    """Indicators of capture onset (Proposition 4.2)."""

    MODE_COUNT_DECREASING = "mode_count_decreasing"
    """Prop 4.2(3a): mode_per_exposure trending down (normalized by exposure)."""

    ENTROPY_NONINCREASING = "entropy_nonincreasing"
    """Prop 4.2(3b): provenance entropy stagnant or decreasing under exposure."""

    CONTRADICTION_SUPPRESSION = "contradiction_suppression"
    """Prop 4.2(3c) + Prop 5.3: generated contradictions → 0 under exposure."""

    COMMITMENT_SHEAR = "commitment_shear"
    """Prop 4.2(3d): lost_commitments / total_commitments_crossing_boundary."""


class AuthorityLevel(str, Enum):
    """Governor authority level derived from envelope mode."""

    BLOCKING = "blocking"
    """Strict envelope — governor can block actions."""

    ADVISORY = "advisory"
    """Exploratory envelope — governor advises but does not block."""

    SLIM = "slim"
    """Slim envelope — minimal governance."""


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class FidelityProxy:
    """Proxy measurements for correlator fidelity.

    Explicitly labeled as proxy — never pretending to be exact.
    These are observable signals that track fidelity, not fidelity itself.
    """

    mode_preservation: float
    """Ratio of live hypothesis/claim branches preserved window-over-window."""

    contradiction_persistence: float
    """Fraction of contradictions surviving reconciliation (>0 = healthy)."""

    representation_shear: float
    """Loss ratio: lost_commitments / total_commitments_crossing_boundary."""

    provenance_entropy: float
    """Entropy of provenance distribution across claims."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_preservation": self.mode_preservation,
            "contradiction_persistence": self.contradiction_persistence,
            "representation_shear": self.representation_shear,
            "provenance_entropy": self.provenance_entropy,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FidelityProxy:
        return cls(
            mode_preservation=float(d.get("mode_preservation", 0.0)),
            contradiction_persistence=float(d.get("contradiction_persistence", 0.0)),
            representation_shear=float(d.get("representation_shear", 0.0)),
            provenance_entropy=float(d.get("provenance_entropy", 0.0)),
        )


@dataclass(frozen=True)
class KVector:
    """Correlator quality vector K = (T, F, A, C).

    WARNING: Do not scalarize. There is no .score() or .magnitude() method.
    The K-vector is a typed tuple, not a point in a metric space.
    Comparisons are per-component only.
    """

    throughput: float
    """Reconciliations per observation window."""

    fidelity: FidelityProxy
    """Proxy fidelity bundle (NOT a scalar)."""

    authority: AuthorityLevel
    """Governor authority level from envelope mode."""

    cost_budget: float
    """Cost burn vs budget ratio [0, 1]."""

    window_step: int
    """Window step number when this vector was computed."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "throughput": self.throughput,
            "fidelity": self.fidelity.to_dict(),
            "authority": self.authority.value,
            "cost_budget": self.cost_budget,
            "window_step": self.window_step,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KVector:
        return cls(
            throughput=float(d.get("throughput", 0.0)),
            fidelity=FidelityProxy.from_dict(d.get("fidelity", {})),
            authority=AuthorityLevel(d.get("authority", "advisory")),
            cost_budget=float(d.get("cost_budget", 0.0)),
            window_step=int(d.get("window_step", 0)),
        )


@dataclass(frozen=True)
class CaptureSignals:
    """Per-window signals consumed by capture diagnostics.

    Aggregated from dissent, epistemic, regime, and claim_diff subsystems.
    """

    # From dissent — track GENERATED not just open
    open_objection_count: int = 0
    generated_objection_count: int = 0
    distinct_agent_count: int = 0

    # From epistemic
    active_claim_count: int = 0
    provenance_entropy: float = 0.0
    distinct_provenance_count: int = 0
    dangerous_claim_count: int = 0

    # From regime / claim_diff
    contradiction_open_rate: float = 0.0
    contradiction_close_rate: float = 0.0
    mutation_velocity: float = 0.0
    silent_retraction_count: int = 0

    # Commitment boundary tracking
    total_commitments_at_boundary: int = 0
    lost_commitments_at_boundary: int = 0

    # Derived
    exposure: int = 0
    live_hypothesis_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_objection_count": self.open_objection_count,
            "generated_objection_count": self.generated_objection_count,
            "distinct_agent_count": self.distinct_agent_count,
            "active_claim_count": self.active_claim_count,
            "provenance_entropy": self.provenance_entropy,
            "distinct_provenance_count": self.distinct_provenance_count,
            "dangerous_claim_count": self.dangerous_claim_count,
            "contradiction_open_rate": self.contradiction_open_rate,
            "contradiction_close_rate": self.contradiction_close_rate,
            "mutation_velocity": self.mutation_velocity,
            "silent_retraction_count": self.silent_retraction_count,
            "total_commitments_at_boundary": self.total_commitments_at_boundary,
            "lost_commitments_at_boundary": self.lost_commitments_at_boundary,
            "exposure": self.exposure,
            "live_hypothesis_count": self.live_hypothesis_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaptureSignals:
        return cls(
            open_objection_count=int(d.get("open_objection_count", 0)),
            generated_objection_count=int(d.get("generated_objection_count", 0)),
            distinct_agent_count=int(d.get("distinct_agent_count", 0)),
            active_claim_count=int(d.get("active_claim_count", 0)),
            provenance_entropy=float(d.get("provenance_entropy", 0.0)),
            distinct_provenance_count=int(d.get("distinct_provenance_count", 0)),
            dangerous_claim_count=int(d.get("dangerous_claim_count", 0)),
            contradiction_open_rate=float(d.get("contradiction_open_rate", 0.0)),
            contradiction_close_rate=float(d.get("contradiction_close_rate", 0.0)),
            mutation_velocity=float(d.get("mutation_velocity", 0.0)),
            silent_retraction_count=int(d.get("silent_retraction_count", 0)),
            total_commitments_at_boundary=int(d.get("total_commitments_at_boundary", 0)),
            lost_commitments_at_boundary=int(d.get("lost_commitments_at_boundary", 0)),
            exposure=int(d.get("exposure", 0)),
            live_hypothesis_count=int(d.get("live_hypothesis_count", 0)),
        )


@dataclass(frozen=True)
class CaptureThresholds:
    """Configurable thresholds for capture detection.

    Defaults chosen conservatively — trigger on clear capture, not noise.
    All indicators use hysteresis (consecutive_windows) to prevent oscillation.
    """

    throughput_min: float = 5.0
    """Minimum reconciliations per window for CAPTURE declaration."""

    exposure_min: int = 3
    """Minimum exposure per window for entropy/contradiction checks."""

    mode_per_exposure_threshold: float = 0.5
    """Mode-per-exposure ratio below this = MODE_COUNT_DECREASING."""

    mode_consecutive_windows: int = 2
    """Consecutive windows of declining mode_per_exposure before triggering."""

    entropy_delta_threshold: float = 0.0
    """Entropy delta at or below this = non-increasing."""

    entropy_consecutive_windows: int = 2
    """Consecutive non-increasing entropy windows before triggering."""

    contradiction_suppression_ratio: float = 0.1
    """Generated-objection/exposure ratio below this = suppression."""

    contradiction_consecutive_windows: int = 2
    """Consecutive windows of suppressed contradictions before triggering."""

    commitment_loss_ratio_threshold: float = 0.3
    """Loss ratio (lost/total at boundary) above this = COMMITMENT_SHEAR."""

    silent_retraction_threshold: int = 3
    """Silent retractions above this count contribute to commitment shear."""

    commitment_consecutive_windows: int = 2
    """Consecutive windows of shear before triggering."""

    capture_indicator_min: int = 2
    """Minimum indicators triggered to classify as CAPTURE."""

    capture_consecutive_windows: int = 2
    """Consecutive windows with >= indicator_min before declaring CAPTURE."""

    cost_budget_degraded_threshold: float = 0.9
    """Cost budget ratio above this = degraded capacity flag (NOT automatic SHEAR)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "throughput_min": self.throughput_min,
            "exposure_min": self.exposure_min,
            "mode_per_exposure_threshold": self.mode_per_exposure_threshold,
            "mode_consecutive_windows": self.mode_consecutive_windows,
            "entropy_delta_threshold": self.entropy_delta_threshold,
            "entropy_consecutive_windows": self.entropy_consecutive_windows,
            "contradiction_suppression_ratio": self.contradiction_suppression_ratio,
            "contradiction_consecutive_windows": self.contradiction_consecutive_windows,
            "commitment_loss_ratio_threshold": self.commitment_loss_ratio_threshold,
            "silent_retraction_threshold": self.silent_retraction_threshold,
            "commitment_consecutive_windows": self.commitment_consecutive_windows,
            "capture_indicator_min": self.capture_indicator_min,
            "capture_consecutive_windows": self.capture_consecutive_windows,
            "cost_budget_degraded_threshold": self.cost_budget_degraded_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaptureThresholds:
        return cls(
            throughput_min=float(d.get("throughput_min", 5.0)),
            exposure_min=int(d.get("exposure_min", 3)),
            mode_per_exposure_threshold=float(d.get("mode_per_exposure_threshold", 0.5)),
            mode_consecutive_windows=int(d.get("mode_consecutive_windows", 2)),
            entropy_delta_threshold=float(d.get("entropy_delta_threshold", 0.0)),
            entropy_consecutive_windows=int(d.get("entropy_consecutive_windows", 2)),
            contradiction_suppression_ratio=float(d.get("contradiction_suppression_ratio", 0.1)),
            contradiction_consecutive_windows=int(d.get("contradiction_consecutive_windows", 2)),
            commitment_loss_ratio_threshold=float(d.get("commitment_loss_ratio_threshold", 0.3)),
            silent_retraction_threshold=int(d.get("silent_retraction_threshold", 3)),
            commitment_consecutive_windows=int(d.get("commitment_consecutive_windows", 2)),
            capture_indicator_min=int(d.get("capture_indicator_min", 2)),
            capture_consecutive_windows=int(d.get("capture_consecutive_windows", 2)),
            cost_budget_degraded_threshold=float(d.get("cost_budget_degraded_threshold", 0.9)),
        )


@dataclass
class IndicatorState:
    """Per-indicator hysteresis state (consecutive window tracking)."""

    mode_streak: int = 0
    entropy_streak: int = 0
    contradiction_streak: int = 0
    commitment_streak: int = 0
    capture_streak: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "mode_streak": self.mode_streak,
            "entropy_streak": self.entropy_streak,
            "contradiction_streak": self.contradiction_streak,
            "commitment_streak": self.commitment_streak,
            "capture_streak": self.capture_streak,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IndicatorState:
        return cls(
            mode_streak=int(d.get("mode_streak", 0)),
            entropy_streak=int(d.get("entropy_streak", 0)),
            contradiction_streak=int(d.get("contradiction_streak", 0)),
            commitment_streak=int(d.get("commitment_streak", 0)),
            capture_streak=int(d.get("capture_streak", 0)),
        )


@dataclass
class CaptureDiagnostic:
    """Result of one capture diagnostic run."""

    window_step: int
    regime: CorrelatorRegime
    indicators_triggered: list[CaptureIndicator]
    indicator_details: dict[str, Any]
    k_vector: KVector
    signals: CaptureSignals
    confidence: float
    gate_met: bool = True
    """Whether T/A gate was met. If False, indicators are non-binding context."""
    capacity_degraded: bool = False
    """Whether cost budget exceeded threshold (informational, not regime)."""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_step": self.window_step,
            "regime": self.regime.value,
            "indicators_triggered": [i.value for i in self.indicators_triggered],
            "indicator_details": self.indicator_details,
            "k_vector": self.k_vector.to_dict(),
            "signals": self.signals.to_dict(),
            "confidence": self.confidence,
            "gate_met": self.gate_met,
            "capacity_degraded": self.capacity_degraded,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaptureDiagnostic:
        return cls(
            window_step=int(d.get("window_step", 0)),
            regime=CorrelatorRegime(d.get("regime", "unknown")),
            indicators_triggered=[
                CaptureIndicator(i) for i in d.get("indicators_triggered", [])
            ],
            indicator_details=d.get("indicator_details", {}),
            k_vector=KVector.from_dict(d.get("k_vector", {})),
            signals=CaptureSignals.from_dict(d.get("signals", {})),
            confidence=float(d.get("confidence", 0.0)),
            gate_met=bool(d.get("gate_met", True)),
            capacity_degraded=bool(d.get("capacity_degraded", False)),
            timestamp=d.get("timestamp", ""),
        )


# =============================================================================
# Pure Functions
# =============================================================================


def compute_capture_signals(
    *,
    dissent_metrics: dict[str, Any] | None = None,
    epistemic_metrics: dict[str, Any] | None = None,
    regime_signals: dict[str, Any] | None = None,
    diff_trends: dict[str, Any] | None = None,
    exposure: int = 0,
    hypothesis_count: int = 0,
) -> CaptureSignals:
    """Aggregate subsystem metrics into CaptureSignals.

    All inputs are dicts — no direct subsystem imports.
    Missing or None dicts are treated as empty.
    """
    dm = dissent_metrics or {}
    em = epistemic_metrics or {}
    rs = regime_signals or {}
    dt = diff_trends or {}

    return CaptureSignals(
        open_objection_count=int(dm.get("open_objection_count", 0)),
        generated_objection_count=int(dm.get("generated_objection_count", 0)),
        distinct_agent_count=int(dm.get("distinct_agent_count", 0)),
        active_claim_count=int(em.get("active_claim_count", 0)),
        provenance_entropy=float(em.get("provenance_entropy", 0.0)),
        distinct_provenance_count=int(em.get("distinct_provenance_count", 0)),
        dangerous_claim_count=int(em.get("dangerous_claim_count", 0)),
        contradiction_open_rate=float(rs.get("contradiction_open_rate", 0.0)),
        contradiction_close_rate=float(rs.get("contradiction_close_rate", 0.0)),
        mutation_velocity=float(dt.get("mutation_velocity", 0.0)),
        silent_retraction_count=int(dt.get("silent_retraction_count", 0)),
        total_commitments_at_boundary=int(dt.get("total_commitments_at_boundary", 0)),
        lost_commitments_at_boundary=int(dt.get("lost_commitments_at_boundary", 0)),
        exposure=exposure,
        live_hypothesis_count=hypothesis_count,
    )


def compute_fidelity_proxy(
    *,
    provenance_entropy: float = 0.0,
    contradiction_persistence: float = 0.0,
    mode_ratio: float = 1.0,
    commitment_shear: float = 0.0,
) -> FidelityProxy:
    """Compute fidelity proxy from observable signals."""
    return FidelityProxy(
        mode_preservation=max(0.0, min(1.0, mode_ratio)),
        contradiction_persistence=max(0.0, contradiction_persistence),
        representation_shear=max(0.0, commitment_shear),
        provenance_entropy=max(0.0, provenance_entropy),
    )


def compute_k_vector(
    *,
    throughput: float,
    fidelity: FidelityProxy,
    authority: AuthorityLevel,
    cost_ratio: float,
    window_step: int,
) -> KVector:
    """Construct K-vector from components."""
    return KVector(
        throughput=max(0.0, throughput),
        fidelity=fidelity,
        authority=authority,
        cost_budget=max(0.0, min(1.0, cost_ratio)),
        window_step=window_step,
    )


def _check_mode_count_decreasing(
    signals_current: CaptureSignals,
    signals_previous: CaptureSignals | None,
    thresholds: CaptureThresholds,
) -> tuple[bool, dict[str, Any]]:
    """Prop 4.2(3a): mode_per_exposure trending down.

    Normalized by exposure to avoid false positives in boring periods.
    Raw hypothesis count is gameable (spam hypotheses) — normalizing
    by exposure captures survivorship ratio.
    """
    if signals_previous is None:
        return False, {"reason": "no_previous_data"}

    # Normalize by exposure
    current_exposure = max(signals_current.exposure, 1)
    previous_exposure = max(signals_previous.exposure, 1)

    current_mpe = signals_current.live_hypothesis_count / current_exposure
    previous_mpe = signals_previous.live_hypothesis_count / previous_exposure

    if previous_mpe <= 0:
        return False, {"reason": "previous_mpe_zero", "current_mpe": round(current_mpe, 4)}

    ratio = current_mpe / previous_mpe
    raw_triggered = ratio < thresholds.mode_per_exposure_threshold

    return raw_triggered, {
        "current_mpe": round(current_mpe, 4),
        "previous_mpe": round(previous_mpe, 4),
        "ratio": round(ratio, 4),
        "threshold": thresholds.mode_per_exposure_threshold,
        "current_hypotheses": signals_current.live_hypothesis_count,
        "current_exposure": signals_current.exposure,
    }


def _check_entropy_nonincreasing(
    signals_current: CaptureSignals,
    signals_previous: CaptureSignals | None,
    thresholds: CaptureThresholds,
) -> tuple[bool, dict[str, Any]]:
    """Prop 4.2(3b): provenance entropy stagnant or decreasing.

    Only evaluates when exposure >= e_min — stagnant entropy in idle
    environments is not capture, it's just quiet.
    """
    if signals_previous is None:
        return False, {"reason": "no_previous_data"}

    # Exposure gate: don't flag idle periods
    if signals_current.exposure < thresholds.exposure_min:
        return False, {
            "reason": "exposure_below_minimum",
            "exposure": signals_current.exposure,
            "exposure_min": thresholds.exposure_min,
        }

    delta = signals_current.provenance_entropy - signals_previous.provenance_entropy
    raw_triggered = delta <= thresholds.entropy_delta_threshold
    return raw_triggered, {
        "current_entropy": round(signals_current.provenance_entropy, 4),
        "previous_entropy": round(signals_previous.provenance_entropy, 4),
        "delta": round(delta, 4),
        "threshold": thresholds.entropy_delta_threshold,
    }


def _check_contradiction_suppression(
    signals_current: CaptureSignals,
    thresholds: CaptureThresholds,
) -> tuple[bool, dict[str, Any]]:
    """Prop 4.2(3c) + Prop 5.3: generated contradictions → 0 under exposure.

    Uses generated_objection_count, not open_objection_count.
    Open objections can drop because they were resolved legitimately.
    Capture is "generated → 0 under exposure" — nothing being surfaced.
    """
    if signals_current.exposure <= 0:
        return False, {"reason": "zero_exposure"}

    # Use generated count — capture kills generation, not just resolution
    ratio = signals_current.generated_objection_count / signals_current.exposure
    raw_triggered = ratio < thresholds.contradiction_suppression_ratio
    return raw_triggered, {
        "generated_objections": signals_current.generated_objection_count,
        "open_objections": signals_current.open_objection_count,
        "exposure": signals_current.exposure,
        "ratio": round(ratio, 4),
        "threshold": thresholds.contradiction_suppression_ratio,
    }


def _check_commitment_shear(
    signals_current: CaptureSignals,
    k_vector: KVector,
    thresholds: CaptureThresholds,
) -> tuple[bool, dict[str, Any]]:
    """Prop 4.2(3d): commitment loss ratio at representation boundaries.

    Computed as: lost_commitments / total_commitments_crossing_boundary.
    Also considers silent retractions (committed claims vanishing without trace).
    """
    # Loss ratio at representation boundary
    total = signals_current.total_commitments_at_boundary
    lost = signals_current.lost_commitments_at_boundary
    if total > 0:
        loss_ratio = lost / total
    else:
        # Fall back to representation_shear from fidelity proxy
        loss_ratio = k_vector.fidelity.representation_shear

    retraction_trigger = (
        signals_current.silent_retraction_count > thresholds.silent_retraction_threshold
    )
    loss_ratio_trigger = loss_ratio > thresholds.commitment_loss_ratio_threshold
    raw_triggered = retraction_trigger or loss_ratio_trigger

    return raw_triggered, {
        "loss_ratio": round(loss_ratio, 4),
        "lost_commitments": lost,
        "total_commitments": total,
        "loss_ratio_threshold": thresholds.commitment_loss_ratio_threshold,
        "silent_retractions": signals_current.silent_retraction_count,
        "retraction_threshold": thresholds.silent_retraction_threshold,
        "retraction_triggered": retraction_trigger,
        "loss_ratio_triggered": loss_ratio_trigger,
    }


def diagnose_capture(
    *,
    signals_current: CaptureSignals,
    signals_previous: CaptureSignals | None,
    k_vector: KVector,
    thresholds: CaptureThresholds,
    indicator_state: IndicatorState,
) -> tuple[CaptureDiagnostic, IndicatorState]:
    """Run capture diagnostics for one observation window.

    Returns (diagnostic, updated_indicator_state).

    Indicators are ALWAYS computed (pre-gate) so the dashboard can show
    "capture-shaped signals present." The T/A gate controls whether
    indicators are binding (can declare CAPTURE regime) or non-binding
    (informational context only).
    """
    indicators: list[CaptureIndicator] = []
    details: dict[str, Any] = {}
    new_state = IndicatorState(
        mode_streak=indicator_state.mode_streak,
        entropy_streak=indicator_state.entropy_streak,
        contradiction_streak=indicator_state.contradiction_streak,
        commitment_streak=indicator_state.commitment_streak,
        capture_streak=indicator_state.capture_streak,
    )

    # --- Always compute indicators (pre-gate) ---

    # (3a) Mode count decreasing (normalized by exposure)
    mode_triggered, mode_info = _check_mode_count_decreasing(
        signals_current, signals_previous, thresholds
    )
    new_state.mode_streak = (
        new_state.mode_streak + 1 if mode_triggered else 0
    )
    mode_info["streak"] = new_state.mode_streak
    mode_info["streak_threshold"] = thresholds.mode_consecutive_windows
    details["mode_count"] = mode_info
    if new_state.mode_streak >= thresholds.mode_consecutive_windows:
        indicators.append(CaptureIndicator.MODE_COUNT_DECREASING)

    # (3b) Entropy non-increasing (gated by exposure minimum)
    entropy_triggered, entropy_info = _check_entropy_nonincreasing(
        signals_current, signals_previous, thresholds
    )
    new_state.entropy_streak = (
        new_state.entropy_streak + 1 if entropy_triggered else 0
    )
    entropy_info["streak"] = new_state.entropy_streak
    entropy_info["streak_threshold"] = thresholds.entropy_consecutive_windows
    details["entropy"] = entropy_info
    if new_state.entropy_streak >= thresholds.entropy_consecutive_windows:
        indicators.append(CaptureIndicator.ENTROPY_NONINCREASING)

    # (3c) Contradiction suppression (uses generated, not open)
    contra_triggered, contra_info = _check_contradiction_suppression(
        signals_current, thresholds
    )
    new_state.contradiction_streak = (
        new_state.contradiction_streak + 1 if contra_triggered else 0
    )
    contra_info["streak"] = new_state.contradiction_streak
    contra_info["streak_threshold"] = thresholds.contradiction_consecutive_windows
    details["contradiction"] = contra_info
    if new_state.contradiction_streak >= thresholds.contradiction_consecutive_windows:
        indicators.append(CaptureIndicator.CONTRADICTION_SUPPRESSION)

    # (3d) Commitment shear (loss ratio at boundary)
    commit_triggered, commit_info = _check_commitment_shear(
        signals_current, k_vector, thresholds
    )
    new_state.commitment_streak = (
        new_state.commitment_streak + 1 if commit_triggered else 0
    )
    commit_info["streak"] = new_state.commitment_streak
    commit_info["streak_threshold"] = thresholds.commitment_consecutive_windows
    details["commitment"] = commit_info
    if new_state.commitment_streak >= thresholds.commitment_consecutive_windows:
        indicators.append(CaptureIndicator.COMMITMENT_SHEAR)

    # --- Gate check ---
    authority_gated = k_vector.authority == AuthorityLevel.BLOCKING
    throughput_gated = k_vector.throughput >= thresholds.throughput_min
    gate_met = authority_gated and throughput_gated

    details["authority_gated"] = authority_gated
    details["throughput_gated"] = throughput_gated
    details["gate_met"] = gate_met

    # Capacity degradation flag (informational, not SHEAR)
    capacity_degraded = k_vector.cost_budget > thresholds.cost_budget_degraded_threshold
    details["capacity_degraded"] = capacity_degraded

    # --- Capture hysteresis: require consecutive windows ---
    binding_indicators = indicators if gate_met else []
    enough_indicators = len(binding_indicators) >= thresholds.capture_indicator_min
    new_state.capture_streak = (
        new_state.capture_streak + 1 if enough_indicators else 0
    )

    # --- Classify regime ---
    regime = classify_regime(
        k_vector=k_vector,
        capture_indicators=binding_indicators,
        capture_streak=new_state.capture_streak,
        thresholds=thresholds,
    )

    # --- Confidence ---
    if regime == CorrelatorRegime.CAPTURE:
        confidence = min(1.0, len(binding_indicators) / 4.0)
    elif regime == CorrelatorRegime.LEVERAGE:
        confidence = 0.8 if throughput_gated else 0.5
    elif regime == CorrelatorRegime.SHEAR:
        confidence = 0.7
    else:
        confidence = 0.0

    diagnostic = CaptureDiagnostic(
        window_step=k_vector.window_step,
        regime=regime,
        indicators_triggered=indicators,  # ALL indicators (binding + non-binding)
        indicator_details=details,
        k_vector=k_vector,
        signals=signals_current,
        confidence=confidence,
        gate_met=gate_met,
        capacity_degraded=capacity_degraded,
    )

    return diagnostic, new_state


def classify_regime(
    *,
    k_vector: KVector,
    capture_indicators: list[CaptureIndicator],
    capture_streak: int = 0,
    thresholds: CaptureThresholds,
) -> CorrelatorRegime:
    """Classify correlator regime from K-vector and indicators.

    Decision tree:
    1. Insufficient data (first window) → UNKNOWN
    2. Low throughput under blocking authority → SHEAR
    3. Enough indicators + sustained streak under blocking → CAPTURE
    4. Otherwise → LEVERAGE
    """
    # UNKNOWN: first window
    if k_vector.window_step == 0:
        return CorrelatorRegime.UNKNOWN

    # SHEAR: throughput below minimum while blocking
    # (low T + blocking = governor capacity exceeded)
    if (
        k_vector.throughput < thresholds.throughput_min
        and k_vector.authority == AuthorityLevel.BLOCKING
    ):
        return CorrelatorRegime.SHEAR

    # CAPTURE: enough indicators + sustained streak under blocking
    if (
        k_vector.authority == AuthorityLevel.BLOCKING
        and len(capture_indicators) >= thresholds.capture_indicator_min
        and capture_streak >= thresholds.capture_consecutive_windows
    ):
        return CorrelatorRegime.CAPTURE

    # LEVERAGE: default healthy state
    return CorrelatorRegime.LEVERAGE


def judge_interferometry_run(
    *,
    run_signals: dict[str, Any],
    k_vector: KVector,
    capture_indicators: list[CaptureIndicator],
) -> dict[str, Any]:
    """Assess an interferometry run in context of correlator state.

    Under capture, interferometry results are suspect — the system
    may be producing false agreement by constraining the solution space.
    """
    regime = classify_regime(
        k_vector=k_vector,
        capture_indicators=capture_indicators,
        thresholds=CaptureThresholds(),
    )

    shared_ratio = float(run_signals.get("shared_ratio", 0.0))
    conflict_count = int(run_signals.get("conflict_count", 0))

    result: dict[str, Any] = {
        "regime": regime.value,
        "indicators_active": [i.value for i in capture_indicators],
    }

    if regime == CorrelatorRegime.CAPTURE:
        result["warning"] = "interferometry_under_capture"
        result["trust_shared"] = False
        result["recommendation"] = (
            "High model agreement during capture regime may reflect "
            "false coherence. Verify with independent signals."
        )
    elif regime == CorrelatorRegime.SHEAR:
        result["warning"] = "interferometry_under_shear"
        result["trust_shared"] = shared_ratio > 0.3
        result["recommendation"] = (
            "System under shear — interferometry results may be noisy."
        )
    else:
        result["trust_shared"] = True
        result["recommendation"] = None

    result["shared_ratio"] = shared_ratio
    result["conflict_count"] = conflict_count

    return result


# =============================================================================
# Stateful Coordinator
# =============================================================================


_MAX_HISTORY = 100


class CorrelatorTelemetry:
    """Stateful coordinator for correlator telemetry.

    Wraps pure functions, maintains rolling history, persists to disk.
    Uses atomic writes (tmp + rename) for persistence.
    """

    def __init__(
        self,
        thresholds: CaptureThresholds | None = None,
        max_history: int = _MAX_HISTORY,
        telemetry: Any | None = None,
    ) -> None:
        self.thresholds = thresholds or CaptureThresholds()
        self.max_history = max_history
        self._telemetry = telemetry  # Optional TelemetryCollector (avoids import cycle)
        self._history: list[CaptureDiagnostic] = []
        self._indicator_state = IndicatorState()
        self._window_step: int = 0

    @property
    def window_step(self) -> int:
        return self._window_step

    @property
    def indicator_state(self) -> IndicatorState:
        return self._indicator_state

    def observe(
        self,
        *,
        dissent_metrics: dict[str, Any] | None = None,
        epistemic_metrics: dict[str, Any] | None = None,
        regime_signals: dict[str, Any] | None = None,
        diff_trends: dict[str, Any] | None = None,
        exposure: int = 0,
        hypothesis_count: int = 0,
        throughput: float = 0.0,
        authority: AuthorityLevel = AuthorityLevel.ADVISORY,
        cost_ratio: float = 0.0,
        contradiction_persistence: float = 0.0,
        mode_ratio: float = 1.0,
        commitment_shear: float = 0.0,
    ) -> CaptureDiagnostic:
        """Observe one window and run diagnostics.

        Computes signals, fidelity, K-vector, and runs capture detection.
        Appends result to history.
        """
        signals = compute_capture_signals(
            dissent_metrics=dissent_metrics,
            epistemic_metrics=epistemic_metrics,
            regime_signals=regime_signals,
            diff_trends=diff_trends,
            exposure=exposure,
            hypothesis_count=hypothesis_count,
        )

        fidelity = compute_fidelity_proxy(
            provenance_entropy=signals.provenance_entropy,
            contradiction_persistence=contradiction_persistence,
            mode_ratio=mode_ratio,
            commitment_shear=commitment_shear,
        )

        k_vec = compute_k_vector(
            throughput=throughput,
            fidelity=fidelity,
            authority=authority,
            cost_ratio=cost_ratio,
            window_step=self._window_step,
        )

        previous = self._history[-1].signals if self._history else None

        diagnostic, self._indicator_state = diagnose_capture(
            signals_current=signals,
            signals_previous=previous,
            k_vector=k_vec,
            thresholds=self.thresholds,
            indicator_state=self._indicator_state,
        )

        self._history.append(diagnostic)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        self._window_step += 1
        self._emit_telemetry(diagnostic)
        return diagnostic

    def _emit_telemetry(self, diagnostic: CaptureDiagnostic) -> None:
        """Emit telemetry events for this observation.  No-op if no collector."""
        if self._telemetry is None:
            return
        try:
            from .telemetry import TelemetryEventType

            # Low-cardinality fields only — no raw text, no UUIDs per event
            fields = {
                "regime": diagnostic.regime.value,
                "window_step": diagnostic.window_step,
                "confidence": round(diagnostic.confidence, 3),
                "gate_met": diagnostic.gate_met,
                "capacity_degraded": diagnostic.capacity_degraded,
                "indicators": [i.value for i in diagnostic.indicators_triggered],
                "k_throughput": round(diagnostic.k_vector.throughput, 2),
                "k_authority": diagnostic.k_vector.authority.value,
                "k_cost": round(diagnostic.k_vector.cost_budget, 3),
            }
            self._telemetry.record_correlator_observation(**fields)

            if diagnostic.regime == CorrelatorRegime.CAPTURE and diagnostic.gate_met:
                self._telemetry.record_capture_detected(
                    regime=diagnostic.regime.value,
                    confidence=round(diagnostic.confidence, 3),
                    indicators=[i.value for i in diagnostic.indicators_triggered],
                    window_step=diagnostic.window_step,
                )
        except Exception:
            pass  # Telemetry never crashes the correlator

    def get_regime(self) -> CorrelatorRegime:
        """Get current correlator regime."""
        if not self._history:
            return CorrelatorRegime.UNKNOWN
        return self._history[-1].regime

    def get_latest_k_vector(self) -> KVector | None:
        """Get the most recent K-vector."""
        if not self._history:
            return None
        return self._history[-1].k_vector

    def get_latest_diagnostic(self) -> CaptureDiagnostic | None:
        """Get the most recent diagnostic."""
        if not self._history:
            return None
        return self._history[-1]

    def get_history(self, limit: int | None = None) -> list[CaptureDiagnostic]:
        """Get diagnostic history, newest first."""
        history = list(reversed(self._history))
        if limit is not None:
            history = history[:limit]
        return history

    def get_metrics(self) -> dict[str, Any]:
        """Get summary metrics for the correlator."""
        if not self._history:
            return {
                "regime": CorrelatorRegime.UNKNOWN.value,
                "total_observations": 0,
                "capture_count": 0,
                "shear_count": 0,
                "leverage_count": 0,
                "indicator_state": self._indicator_state.to_dict(),
            }

        capture_count = sum(
            1 for d in self._history if d.regime == CorrelatorRegime.CAPTURE
        )
        shear_count = sum(
            1 for d in self._history if d.regime == CorrelatorRegime.SHEAR
        )
        leverage_count = sum(
            1 for d in self._history if d.regime == CorrelatorRegime.LEVERAGE
        )

        return {
            "regime": self._history[-1].regime.value,
            "total_observations": len(self._history),
            "capture_count": capture_count,
            "shear_count": shear_count,
            "leverage_count": leverage_count,
            "indicator_state": self._indicator_state.to_dict(),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._history.clear()
        self._indicator_state = IndicatorState()
        self._window_step = 0

    # --- Persistence ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": self.thresholds.to_dict(),
            "max_history": self.max_history,
            "history": [d.to_dict() for d in self._history],
            "indicator_state": self._indicator_state.to_dict(),
            "window_step": self._window_step,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CorrelatorTelemetry:
        thresholds = CaptureThresholds.from_dict(d.get("thresholds", {}))
        ct = cls(
            thresholds=thresholds,
            max_history=int(d.get("max_history", _MAX_HISTORY)),
        )
        ct._history = [
            CaptureDiagnostic.from_dict(h) for h in d.get("history", [])
        ]
        ct._indicator_state = IndicatorState.from_dict(
            d.get("indicator_state", {})
        )
        ct._window_step = int(d.get("window_step", 0))
        return ct

    def save(self, gov_dir: Path) -> None:
        """Save state to {gov_dir}/correlator.json.

        Uses atomic write (tmp + rename) to avoid corruption on crash.
        """
        path = gov_dir / "correlator.json"
        content = json.dumps(self.to_dict(), indent=2)
        # Atomic write: write to tmp in same dir, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(gov_dir), prefix=".correlator_", suffix=".tmp"
        )
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(path))
        except BaseException:
            if not closed:
                os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(
        cls,
        gov_dir: Path,
        telemetry: Any | None = None,
    ) -> CorrelatorTelemetry:
        """Load state from {gov_dir}/correlator.json, or return fresh instance."""
        path = gov_dir / "correlator.json"
        if not path.exists():
            return cls(telemetry=telemetry)
        try:
            data = json.loads(path.read_text())
            ct = cls.from_dict(data)
            ct._telemetry = telemetry
            return ct
        except (json.JSONDecodeError, KeyError, ValueError):
            return cls(telemetry=telemetry)
