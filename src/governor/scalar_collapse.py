# SPDX-License-Identifier: Apache-2.0
"""
Scalar Collapse Detection — Eigenstructure Evaporation in Governance Chains.

Monitors the effective dimensionality of the governor's decision space.
Detects when metrics that should be independent converge to scalar behavior,
when action distributions narrow, and when "everything improves at once."

Spec: SCALAR_COLLAPSE_SPEC.md (Layer 2, Item #7 of AG2 build order)

Core insight: Scalar collapse looks like improvement. Every dashboard metric
goes up. The failure is invisible until the suppressed modes matter — and by
then, recovery requires exogenous forcing, not tuning.

Key properties:
  - Pure detection (reads telemetry, produces report, no mutations)
  - Pure Python covariance/PCA (no numpy dependency)
  - Monotonic response (higher risk only tightens, never loosens)
  - Irreversibility-aware (warns when tuning can no longer recover)
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CollapseRisk(str, Enum):
    """Collapse risk level."""

    HEALTHY = "healthy"
    """risk < 0.3 — normal metric diversity."""

    WARNING = "warning"
    """0.3 ≤ risk < 0.5 — effective dimension declining."""

    ELEVATED = "elevated"
    """0.5 ≤ risk < 0.7 — freeze auto-tuning recommended."""

    CRITICAL = "critical"
    """risk ≥ 0.7 — inject diversity constraints. Approaching irreversibility."""


class CollapseAction(str, Enum):
    """Response action for collapse risk."""

    PASS = "pass"
    """No action needed."""

    WARN = "warn"
    """Alert: effective dimension declining."""

    FREEZE_TUNING = "freeze_tuning"
    """Freeze auto-tuning. Require multi-objective justification."""

    INJECT_DIVERSITY = "inject_diversity"
    """Freeze tuning + inject diversity constraints."""


# ---------------------------------------------------------------------------
# Default metric names
# ---------------------------------------------------------------------------

DEFAULT_METRICS = [
    "approval_rate",
    "evidence_quality",
    "convergence_speed",
    "security_score",
    "action_diversity",
    "constraint_count",
    "override_rate",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MetricSample:
    """A single governance metric observation."""

    turn: int
    """Governance turn/decision number."""

    metrics: dict[str, float]
    """Metric name → value."""

    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"turn": self.turn, "metrics": self.metrics}
        if self.timestamp:
            d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MetricSample:
        return cls(
            turn=d["turn"],
            metrics=d["metrics"],
            timestamp=datetime.fromisoformat(d["timestamp"]) if d.get("timestamp") else None,
        )


@dataclass
class CollapseSignals:
    """Proxy signals for scalar collapse."""

    effective_dimension: float
    """Rank of metric covariance matrix (eigenvalues above noise floor)."""

    variance_concentration: float
    """PC1 explained variance ratio (0.0–1.0). >0.7 = effectively scalar."""

    action_entropy: float
    """Shannon entropy of action distribution. 0 = always same action."""

    metric_agreement: float
    """Mean pairwise |correlation| between metrics (0.0–1.0)."""

    max_dimension: int = 0
    """Maximum possible dimension (number of metrics tracked)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_dimension": round(self.effective_dimension, 4),
            "variance_concentration": round(self.variance_concentration, 4),
            "action_entropy": round(self.action_entropy, 4),
            "metric_agreement": round(self.metric_agreement, 4),
            "max_dimension": self.max_dimension,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CollapseSignals:
        return cls(
            effective_dimension=d["effective_dimension"],
            variance_concentration=d["variance_concentration"],
            action_entropy=d["action_entropy"],
            metric_agreement=d["metric_agreement"],
            max_dimension=d.get("max_dimension", 0),
        )


@dataclass
class CollapseReport:
    """Aggregate collapse detection result."""

    report_id: str
    """Content hash of the report."""

    signals: CollapseSignals
    """Detection signals."""

    risk_score: float
    """0.0 (healthy) to 1.0 (collapsed)."""

    risk_level: CollapseRisk
    """Risk classification."""

    action: CollapseAction
    """Recommended response action."""

    dominant_metric: str | None = None
    """Which metric is eating the others (if detectable)."""

    suppressed_modes: list[str] = field(default_factory=list)
    """Metrics losing independent variance."""

    window_turns: int = 0
    """Analysis window size."""

    irreversible: bool = False
    """True if collapse is beyond tuning-recoverable."""

    recommendations: list[str] = field(default_factory=list)
    """Suggested mitigations."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def dedup_fingerprint(self) -> str:
        """NOT canonical content-addressing — use only for dedup/integrity."""
        data = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "signals": self.signals.to_dict(),
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level.value,
            "action": self.action.value,
            "dominant_metric": self.dominant_metric,
            "suppressed_modes": self.suppressed_modes,
            "window_turns": self.window_turns,
            "irreversible": self.irreversible,
            "recommendations": self.recommendations,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CollapseReport:
        return cls(
            report_id=d["report_id"],
            signals=CollapseSignals.from_dict(d["signals"]),
            risk_score=d["risk_score"],
            risk_level=CollapseRisk(d["risk_level"]),
            action=CollapseAction(d["action"]),
            dominant_metric=d.get("dominant_metric"),
            suppressed_modes=d.get("suppressed_modes", []),
            window_turns=d.get("window_turns", 0),
            irreversible=d.get("irreversible", False),
            recommendations=d.get("recommendations", []),
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.now(timezone.utc),
        )

    def to_summary(self) -> str:
        lines = [
            f"Collapse Report: {self.report_id}",
            f"  Risk score: {self.risk_score:.4f} ({self.risk_level.value})",
            f"  Action: {self.action.value}",
            f"  Effective dimension: {self.signals.effective_dimension:.1f}/{self.signals.max_dimension}",
            f"  Variance concentration (PC1): {self.signals.variance_concentration:.4f}",
            f"  Action entropy: {self.signals.action_entropy:.4f}",
            f"  Metric agreement: {self.signals.metric_agreement:.4f}",
            f"  Window: {self.window_turns} turns",
        ]
        if self.dominant_metric:
            lines.append(f"  Dominant metric: {self.dominant_metric}")
        if self.suppressed_modes:
            lines.append(f"  Suppressed modes: {', '.join(self.suppressed_modes)}")
        if self.irreversible:
            lines.append("  WARNING: Collapse is beyond tuning-recoverable.")
            lines.append("  Recovery requires exogenous forcing (manual constraint injection).")
        if self.recommendations:
            lines.append("  Recommendations:")
            for r in self.recommendations:
                lines.append(f"    - {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pure Python Statistics
# ---------------------------------------------------------------------------


def _mean(xs: list[float]) -> float:
    """Arithmetic mean."""
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _variance(xs: list[float]) -> float:
    """Population variance."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def _std(xs: list[float]) -> float:
    """Population standard deviation."""
    return math.sqrt(_variance(xs))


def _covariance(xs: list[float], ys: list[float]) -> float:
    """Population covariance between two lists."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = _mean(xs)
    my = _mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)


def _pearson_correlation(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    if len(xs) < 2:
        return 0.0
    sx = _std(xs)
    sy = _std(ys)
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    return _covariance(xs, ys) / (sx * sy)


def _covariance_matrix(data: list[list[float]]) -> list[list[float]]:
    """Compute covariance matrix from metric vectors.

    data[i] = list of values for metric i across all samples.
    Returns n×n covariance matrix.
    """
    n = len(data)
    cov: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            c = _covariance(data[i], data[j])
            cov[i][j] = c
            cov[j][i] = c
    return cov


def _eigenvalues_symmetric(M: list[list[float]], max_iter: int = 200, tol: float = 1e-8) -> list[float]:
    """Estimate eigenvalues of a symmetric matrix via QR-like iteration.

    For small matrices (n ≤ 10), uses Jacobi eigenvalue algorithm.
    Returns eigenvalues sorted descending.
    """
    n = len(M)
    if n == 0:
        return []
    if n == 1:
        return [M[0][0]]

    # Work on a copy
    A = [row[:] for row in M]

    # Jacobi iteration for symmetric matrices
    for _ in range(max_iter * n):
        # Find largest off-diagonal element
        max_val = 0.0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                if abs(A[i][j]) > max_val:
                    max_val = abs(A[i][j])
                    p, q = i, j

        if max_val < tol:
            break

        # Compute rotation angle
        if abs(A[p][p] - A[q][q]) < 1e-15:
            theta = math.pi / 4
        else:
            theta = 0.5 * math.atan2(2 * A[p][q], A[p][p] - A[q][q])

        c = math.cos(theta)
        s = math.sin(theta)

        # Apply Givens rotation
        A_new = [row[:] for row in A]
        for i in range(n):
            if i != p and i != q:
                A_new[i][p] = c * A[i][p] + s * A[i][q]
                A_new[p][i] = A_new[i][p]
                A_new[i][q] = -s * A[i][p] + c * A[i][q]
                A_new[q][i] = A_new[i][q]

        A_new[p][p] = c * c * A[p][p] + 2 * s * c * A[p][q] + s * s * A[q][q]
        A_new[q][q] = s * s * A[p][p] - 2 * s * c * A[p][q] + c * c * A[q][q]
        A_new[p][q] = 0.0
        A_new[q][p] = 0.0

        A = A_new

    eigenvalues = sorted([A[i][i] for i in range(n)], reverse=True)
    return eigenvalues


def _effective_dimension(eigenvalues: list[float], noise_floor: float = 0.01) -> float:
    """Count eigenvalues above noise floor."""
    if not eigenvalues:
        return 0.0
    total = sum(abs(e) for e in eigenvalues)
    if total < 1e-10:
        return 0.0
    threshold = noise_floor * total
    return sum(1 for e in eigenvalues if abs(e) > threshold)


def _variance_concentration(eigenvalues: list[float]) -> float:
    """PC1 explained variance ratio."""
    if not eigenvalues:
        return 0.0
    total = sum(abs(e) for e in eigenvalues)
    if total < 1e-10:
        return 0.0
    return abs(eigenvalues[0]) / total


def _shannon_entropy(counts: dict[str, int]) -> float:
    """Shannon entropy of a count distribution."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def _max_entropy(n: int) -> float:
    """Maximum possible entropy for n categories."""
    if n <= 1:
        return 0.0
    return math.log2(n)


# ---------------------------------------------------------------------------
# Core Detection
# ---------------------------------------------------------------------------


def compute_signals(
    samples: list[MetricSample],
    metric_names: list[str] | None = None,
    action_counts: dict[str, int] | None = None,
) -> CollapseSignals:
    """Compute collapse detection signals from metric samples.

    Args:
        samples: List of metric observations (one per governance turn).
        metric_names: Metrics to analyze. Defaults to all present in samples.
        action_counts: Distribution of governance actions (for entropy).

    Returns:
        CollapseSignals with effective dimension, variance concentration,
        action entropy, and metric agreement.
    """
    if not samples:
        return CollapseSignals(
            effective_dimension=0.0,
            variance_concentration=0.0,
            action_entropy=0.0,
            metric_agreement=0.0,
            max_dimension=0,
        )

    # Determine metric names
    if metric_names is None:
        all_names: set[str] = set()
        for s in samples:
            all_names.update(s.metrics.keys())
        metric_names = sorted(all_names)

    if not metric_names:
        return CollapseSignals(
            effective_dimension=0.0,
            variance_concentration=0.0,
            action_entropy=0.0,
            metric_agreement=0.0,
            max_dimension=0,
        )

    n_metrics = len(metric_names)

    # Extract metric vectors (per-metric time series)
    data: list[list[float]] = []
    for name in metric_names:
        series = [s.metrics.get(name, 0.0) for s in samples]
        data.append(series)

    # 1. Covariance matrix and eigenvalues
    cov = _covariance_matrix(data)
    eigenvalues = _eigenvalues_symmetric(cov)

    eff_dim = _effective_dimension(eigenvalues)
    var_conc = _variance_concentration(eigenvalues)

    # 2. Action entropy
    if action_counts:
        act_ent = _shannon_entropy(action_counts)
    else:
        act_ent = _max_entropy(4)  # Assume healthy if no data

    # 3. Metric agreement (mean pairwise |correlation|)
    if n_metrics >= 2:
        correlations: list[float] = []
        for i in range(n_metrics):
            for j in range(i + 1, n_metrics):
                r = abs(_pearson_correlation(data[i], data[j]))
                correlations.append(r)
        agreement = _mean(correlations)
    else:
        agreement = 0.0

    return CollapseSignals(
        effective_dimension=round(eff_dim, 4),
        variance_concentration=round(var_conc, 4),
        action_entropy=round(act_ent, 4),
        metric_agreement=round(agreement, 4),
        max_dimension=n_metrics,
    )


def compute_collapse_risk(
    signals: CollapseSignals,
    w_dim: float = 0.3,
    w_var: float = 0.3,
    w_ent: float = 0.2,
    w_agr: float = 0.2,
) -> float:
    """Weighted combination of collapse signals into risk score.

    risk = w1 * (1 - dim/max_dim) + w2 * var_conc + w3 * (1 - ent/max_ent) + w4 * agreement
    """
    # Dimension loss: 1 when dim=0, 0 when dim=max
    if signals.max_dimension > 0:
        dim_loss = 1.0 - signals.effective_dimension / signals.max_dimension
    else:
        dim_loss = 0.0

    # Variance concentration: directly indicates scalar dominance
    var_conc = signals.variance_concentration

    # Entropy loss: 1 when entropy=0, 0 when at max
    max_ent = _max_entropy(4)  # Assume 4 action types
    if max_ent > 0:
        ent_loss = 1.0 - min(signals.action_entropy / max_ent, 1.0)
    else:
        ent_loss = 0.0

    # Metric agreement: high agreement = scalar behavior
    agreement = signals.metric_agreement

    risk = w_dim * dim_loss + w_var * var_conc + w_ent * ent_loss + w_agr * agreement
    return round(max(0.0, min(1.0, risk)), 4)


def classify_risk(risk_score: float) -> CollapseRisk:
    """Classify risk score into risk level."""
    if risk_score >= 0.7:
        return CollapseRisk.CRITICAL
    if risk_score >= 0.5:
        return CollapseRisk.ELEVATED
    if risk_score >= 0.3:
        return CollapseRisk.WARNING
    return CollapseRisk.HEALTHY


def determine_action(risk_level: CollapseRisk) -> CollapseAction:
    """Determine response action from risk level."""
    return {
        CollapseRisk.HEALTHY: CollapseAction.PASS,
        CollapseRisk.WARNING: CollapseAction.WARN,
        CollapseRisk.ELEVATED: CollapseAction.FREEZE_TUNING,
        CollapseRisk.CRITICAL: CollapseAction.INJECT_DIVERSITY,
    }[risk_level]


def _find_dominant_metric(
    samples: list[MetricSample],
    metric_names: list[str],
) -> str | None:
    """Find the metric with highest variance contribution."""
    if not samples or not metric_names:
        return None

    # Compute variance per metric
    variances: dict[str, float] = {}
    for name in metric_names:
        series = [s.metrics.get(name, 0.0) for s in samples]
        variances[name] = _variance(series)

    total_var = sum(variances.values())
    if total_var < 1e-10:
        return None

    # Find the one explaining most variance
    dominant = max(variances, key=lambda k: variances[k])
    if variances[dominant] / total_var > 0.3:
        return dominant
    return None


def _find_suppressed_modes(
    samples: list[MetricSample],
    metric_names: list[str],
    threshold: float = 0.05,
) -> list[str]:
    """Find metrics with declining variance (being suppressed)."""
    if not samples or len(samples) < 4:
        return []

    suppressed: list[str] = []
    midpoint = len(samples) // 2

    for name in metric_names:
        early = [s.metrics.get(name, 0.0) for s in samples[:midpoint]]
        late = [s.metrics.get(name, 0.0) for s in samples[midpoint:]]

        early_var = _variance(early)
        late_var = _variance(late)

        if early_var > threshold and late_var < early_var * 0.3:
            suppressed.append(name)

    return suppressed


def _generate_recommendations(
    risk_level: CollapseRisk,
    dominant: str | None,
    suppressed: list[str],
    irreversible: bool,
) -> list[str]:
    """Generate mitigation recommendations."""
    recs: list[str] = []

    if risk_level == CollapseRisk.CRITICAL:
        if irreversible:
            recs.append("Collapse is beyond tuning-recoverable. Manual intervention required.")
            recs.append("Inject new constraints or anchors that address suppressed modes.")
        else:
            recs.append("Freeze all auto-tuning immediately.")
            recs.append("Inject diversity constraints for suppressed modes.")

        if dominant:
            recs.append(f"Reduce weight of dominant metric '{dominant}' in optimization.")

    elif risk_level == CollapseRisk.ELEVATED:
        recs.append("Freeze auto-tuning. Require multi-objective justification for changes.")
        if suppressed:
            recs.append(f"Protect suppressed modes: {', '.join(suppressed)}")

    elif risk_level == CollapseRisk.WARNING:
        recs.append("Monitor effective dimension. Consider widening exploration budget.")

    return recs


# ---------------------------------------------------------------------------
# Main Detection Function
# ---------------------------------------------------------------------------


def detect_collapse(
    samples: list[MetricSample],
    metric_names: list[str] | None = None,
    action_counts: dict[str, int] | None = None,
    irreversibility_threshold: int = 20,
) -> CollapseReport:
    """Analyze metric samples for scalar collapse.

    Pure function. Reads data, computes signals, produces report.
    No side effects.

    Args:
        samples: Metric observations from governance turns.
        metric_names: Metrics to analyze (defaults to all present).
        action_counts: Governance action distribution for entropy.
        irreversibility_threshold: Sustained high-risk turns before irreversibility warning.

    Returns:
        CollapseReport with risk score, signals, and recommendations.
    """
    if metric_names is None:
        all_names: set[str] = set()
        for s in samples:
            all_names.update(s.metrics.keys())
        metric_names = sorted(all_names)

    signals = compute_signals(samples, metric_names, action_counts)
    risk_score = compute_collapse_risk(signals)
    risk_level = classify_risk(risk_score)
    action = determine_action(risk_level)

    dominant = _find_dominant_metric(samples, metric_names) if samples else None
    suppressed = _find_suppressed_modes(samples, metric_names) if samples else []

    # Irreversibility check: risk > 0.8 sustained over threshold
    irreversible = False
    if risk_score > 0.8 and len(samples) >= irreversibility_threshold:
        irreversible = True

    recommendations = _generate_recommendations(risk_level, dominant, suppressed, irreversible)

    report_data = json.dumps({
        "risk_score": risk_score,
        "signals": signals.to_dict(),
        "window": len(samples),
    }, sort_keys=True)
    report_id = hashlib.sha256(report_data.encode()).hexdigest()[:12]

    return CollapseReport(
        report_id=report_id,
        signals=signals,
        risk_score=risk_score,
        risk_level=risk_level,
        action=action,
        dominant_metric=dominant,
        suppressed_modes=suppressed,
        window_turns=len(samples),
        irreversible=irreversible,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Collapse History (file-based persistence)
# ---------------------------------------------------------------------------


@dataclass
class CollapseHistory:
    """Persistent collapse detection history."""

    governor_dir: Path | None = None

    @property
    def _history_dir(self) -> Path | None:
        if self.governor_dir is None:
            return None
        return self.governor_dir / "collapse"

    def save_report(self, report: CollapseReport) -> Path | None:
        d = self._history_dir
        if d is None:
            return None
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{report.report_id}.json"
        path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
        return path

    def load_report(self, report_id: str) -> CollapseReport | None:
        d = self._history_dir
        if d is None:
            return None
        path = d / f"{report_id}.json"
        if not path.exists():
            return None
        return CollapseReport.from_dict(json.loads(path.read_text()))

    def list_reports(self) -> list[dict[str, Any]]:
        d = self._history_dir
        if d is None or not d.exists():
            return []
        reports: list[dict[str, Any]] = []
        for path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text())
                reports.append({
                    "report_id": data["report_id"],
                    "risk_score": data["risk_score"],
                    "risk_level": data["risk_level"],
                    "action": data["action"],
                    "window_turns": data.get("window_turns", 0),
                    "irreversible": data.get("irreversible", False),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return reports


# ---------------------------------------------------------------------------
# Collapse Detector (facade)
# ---------------------------------------------------------------------------


class CollapseDetector:
    """Facade for scalar collapse detection.

    Tracks metric samples, computes signals, and produces reports.
    """

    def __init__(
        self,
        metric_names: list[str] | None = None,
        governor_dir: Path | None = None,
        min_samples: int = 10,
    ):
        self._metric_names = metric_names or DEFAULT_METRICS
        self._governor_dir = governor_dir
        self._min_samples = min_samples
        self._samples: list[MetricSample] = []
        self._action_counts: dict[str, int] = {}
        self._last_report: CollapseReport | None = None

    def record_sample(self, metrics: dict[str, float], turn: int | None = None) -> None:
        """Record a metric observation."""
        t = turn if turn is not None else len(self._samples)
        self._samples.append(MetricSample(
            turn=t,
            metrics=metrics,
            timestamp=datetime.now(timezone.utc),
        ))

    def record_action(self, action: str) -> None:
        """Record a governance action for entropy tracking."""
        self._action_counts[action] = self._action_counts.get(action, 0) + 1

    def check(self, window_size: int | None = None) -> CollapseReport:
        """Run collapse detection on recorded samples.

        Args:
            window_size: Use only the last N samples. None = use all.

        Returns:
            CollapseReport.
        """
        samples = self._samples
        if window_size is not None:
            samples = samples[-window_size:]

        report = detect_collapse(
            samples,
            self._metric_names,
            self._action_counts if self._action_counts else None,
        )
        self._last_report = report

        if self._governor_dir is not None:
            history = CollapseHistory(self._governor_dir)
            history.save_report(report)

        return report

    @property
    def has_sufficient_data(self) -> bool:
        """Whether enough samples exist for meaningful analysis."""
        return len(self._samples) >= self._min_samples

    @property
    def last_report(self) -> CollapseReport | None:
        return self._last_report

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def status(self) -> dict[str, Any]:
        """Current detector status."""
        result: dict[str, Any] = {
            "sample_count": len(self._samples),
            "min_samples": self._min_samples,
            "has_sufficient_data": self.has_sufficient_data,
            "metric_names": self._metric_names,
            "action_counts": self._action_counts,
        }
        if self._last_report:
            result["last_risk_score"] = self._last_report.risk_score
            result["last_risk_level"] = self._last_report.risk_level.value
        return result


# ---------------------------------------------------------------------------
# Telemetry event helper
# ---------------------------------------------------------------------------


def make_collapse_event(report: CollapseReport) -> dict[str, Any]:
    """Create a telemetry event dict for a collapse check."""
    return {
        "type": "collapse_check",
        "report_id": report.report_id,
        "risk_score": report.risk_score,
        "risk_level": report.risk_level.value,
        "action": report.action.value,
        "effective_dimension": report.signals.effective_dimension,
        "variance_concentration": report.signals.variance_concentration,
        "dominant_metric": report.dominant_metric,
        "suppressed_modes": report.suppressed_modes,
        "irreversible": report.irreversible,
        "window_turns": report.window_turns,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
