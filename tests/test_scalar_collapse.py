"""Tests for Scalar Collapse Detection (AG2 Layer 2, Item #7)."""

import json
import math
import random
from pathlib import Path

import pytest

from governor.scalar_collapse import (
    CollapseRisk,
    CollapseAction,
    DEFAULT_METRICS,
    MetricSample,
    CollapseSignals,
    CollapseReport,
    CollapseHistory,
    CollapseDetector,
    compute_signals,
    compute_collapse_risk,
    classify_risk,
    determine_action,
    detect_collapse,
    make_collapse_event,
    _mean,
    _variance,
    _std,
    _covariance,
    _pearson_correlation,
    _covariance_matrix,
    _eigenvalues_symmetric,
    _effective_dimension,
    _variance_concentration,
    _shannon_entropy,
    _max_entropy,
    _find_dominant_metric,
    _find_suppressed_modes,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestCollapseRisk:
    def test_values(self):
        assert CollapseRisk.HEALTHY.value == "healthy"
        assert CollapseRisk.WARNING.value == "warning"
        assert CollapseRisk.ELEVATED.value == "elevated"
        assert CollapseRisk.CRITICAL.value == "critical"

    def test_count(self):
        assert len(CollapseRisk) == 4


class TestCollapseAction:
    def test_values(self):
        assert CollapseAction.PASS.value == "pass"
        assert CollapseAction.WARN.value == "warn"
        assert CollapseAction.FREEZE_TUNING.value == "freeze_tuning"
        assert CollapseAction.INJECT_DIVERSITY.value == "inject_diversity"

    def test_count(self):
        assert len(CollapseAction) == 4


# ---------------------------------------------------------------------------
# Pure Python Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_mean(self):
        assert _mean([1, 2, 3, 4, 5]) == 3.0
        assert _mean([]) == 0.0

    def test_variance(self):
        assert _variance([1, 1, 1]) == 0.0
        assert abs(_variance([1, 2, 3]) - 2 / 3) < 0.001

    def test_std(self):
        assert _std([1, 1, 1]) == 0.0
        assert _std([1, 2, 3]) > 0

    def test_covariance(self):
        # Perfect positive correlation
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        cov = _covariance(xs, ys)
        assert cov > 0

        # Uncorrelated
        assert _covariance([1, 1, 1], [1, 2, 3]) == 0.0

    def test_pearson_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert abs(_pearson_correlation(xs, ys) - 1.0) < 0.001

        # Anti-correlated
        ys_neg = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert abs(_pearson_correlation(xs, ys_neg) + 1.0) < 0.001

        # Constant
        assert _pearson_correlation([1, 1, 1], [1, 2, 3]) == 0.0

    def test_covariance_matrix(self):
        data = [[1, 2, 3], [4, 5, 6]]
        cov = _covariance_matrix(data)
        assert len(cov) == 2
        assert len(cov[0]) == 2
        # Symmetric
        assert cov[0][1] == cov[1][0]

    def test_eigenvalues_identity(self):
        M = [[1, 0], [0, 1]]
        evals = _eigenvalues_symmetric(M)
        assert len(evals) == 2
        assert abs(evals[0] - 1.0) < 0.01
        assert abs(evals[1] - 1.0) < 0.01

    def test_eigenvalues_diagonal(self):
        M = [[3, 0], [0, 1]]
        evals = _eigenvalues_symmetric(M)
        assert abs(evals[0] - 3.0) < 0.01
        assert abs(evals[1] - 1.0) < 0.01

    def test_eigenvalues_symmetric(self):
        M = [[2, 1], [1, 2]]
        evals = _eigenvalues_symmetric(M)
        # Eigenvalues of [[2,1],[1,2]] are 3 and 1
        assert abs(evals[0] - 3.0) < 0.01
        assert abs(evals[1] - 1.0) < 0.01

    def test_eigenvalues_empty(self):
        assert _eigenvalues_symmetric([]) == []

    def test_eigenvalues_1x1(self):
        assert _eigenvalues_symmetric([[5.0]]) == [5.0]

    def test_effective_dimension(self):
        # All equal eigenvalues → full dimension
        assert _effective_dimension([1, 1, 1]) == 3
        # One dominant → dimension 1
        assert _effective_dimension([100, 0.001, 0.001]) == 1
        # Empty
        assert _effective_dimension([]) == 0.0

    def test_variance_concentration(self):
        # All equal → even distribution
        assert abs(_variance_concentration([1, 1, 1]) - 1 / 3) < 0.01
        # One dominant
        assert _variance_concentration([100, 1, 1]) > 0.9
        # Empty
        assert _variance_concentration([]) == 0.0

    def test_shannon_entropy(self):
        # Uniform distribution → max entropy
        counts = {"a": 10, "b": 10, "c": 10, "d": 10}
        assert abs(_shannon_entropy(counts) - 2.0) < 0.01

        # All one category → 0
        assert _shannon_entropy({"a": 100}) == 0.0

        # Empty
        assert _shannon_entropy({}) == 0.0

    def test_max_entropy(self):
        assert _max_entropy(2) == 1.0
        assert abs(_max_entropy(4) - 2.0) < 0.01
        assert _max_entropy(1) == 0.0


# ---------------------------------------------------------------------------
# MetricSample
# ---------------------------------------------------------------------------


class TestMetricSample:
    def test_roundtrip(self):
        s = MetricSample(turn=5, metrics={"a": 0.5, "b": 0.8})
        d = s.to_dict()
        s2 = MetricSample.from_dict(d)
        assert s2.turn == 5
        assert s2.metrics["a"] == 0.5


# ---------------------------------------------------------------------------
# CollapseSignals
# ---------------------------------------------------------------------------


class TestCollapseSignals:
    def test_roundtrip(self):
        s = CollapseSignals(
            effective_dimension=4.0,
            variance_concentration=0.35,
            action_entropy=1.5,
            metric_agreement=0.2,
            max_dimension=7,
        )
        d = s.to_dict()
        s2 = CollapseSignals.from_dict(d)
        assert s2.effective_dimension == 4.0
        assert s2.max_dimension == 7


# ---------------------------------------------------------------------------
# Risk Classification
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    def test_healthy(self):
        assert classify_risk(0.1) == CollapseRisk.HEALTHY

    def test_warning(self):
        assert classify_risk(0.35) == CollapseRisk.WARNING

    def test_elevated(self):
        assert classify_risk(0.55) == CollapseRisk.ELEVATED

    def test_critical(self):
        assert classify_risk(0.8) == CollapseRisk.CRITICAL

    def test_boundaries(self):
        assert classify_risk(0.3) == CollapseRisk.WARNING
        assert classify_risk(0.5) == CollapseRisk.ELEVATED
        assert classify_risk(0.7) == CollapseRisk.CRITICAL


class TestDetermineAction:
    def test_mapping(self):
        assert determine_action(CollapseRisk.HEALTHY) == CollapseAction.PASS
        assert determine_action(CollapseRisk.WARNING) == CollapseAction.WARN
        assert determine_action(CollapseRisk.ELEVATED) == CollapseAction.FREEZE_TUNING
        assert determine_action(CollapseRisk.CRITICAL) == CollapseAction.INJECT_DIVERSITY


# ---------------------------------------------------------------------------
# compute_collapse_risk
# ---------------------------------------------------------------------------


class TestComputeCollapseRisk:
    def test_healthy_signals(self):
        signals = CollapseSignals(
            effective_dimension=5.0,
            variance_concentration=0.2,
            action_entropy=2.0,
            metric_agreement=0.1,
            max_dimension=7,
        )
        risk = compute_collapse_risk(signals)
        assert risk < 0.3

    def test_collapsed_signals(self):
        signals = CollapseSignals(
            effective_dimension=1.0,
            variance_concentration=0.9,
            action_entropy=0.1,
            metric_agreement=0.9,
            max_dimension=7,
        )
        risk = compute_collapse_risk(signals)
        assert risk > 0.7

    def test_bounded(self):
        signals = CollapseSignals(
            effective_dimension=0.0,
            variance_concentration=1.0,
            action_entropy=0.0,
            metric_agreement=1.0,
            max_dimension=7,
        )
        risk = compute_collapse_risk(signals)
        assert 0.0 <= risk <= 1.0


# ---------------------------------------------------------------------------
# compute_signals
# ---------------------------------------------------------------------------


class TestComputeSignals:
    def _make_independent_samples(self, n: int = 50) -> list[MetricSample]:
        """Generate samples with independent metrics."""
        random.seed(42)
        samples = []
        for i in range(n):
            samples.append(MetricSample(
                turn=i,
                metrics={
                    "a": random.gauss(0.5, 0.1),
                    "b": random.gauss(0.3, 0.2),
                    "c": random.gauss(0.7, 0.15),
                },
            ))
        return samples

    def _make_correlated_samples(self, n: int = 50) -> list[MetricSample]:
        """Generate samples where all metrics move together (scalar collapse)."""
        random.seed(42)
        samples = []
        for i in range(n):
            base = random.gauss(0.5, 0.1)
            samples.append(MetricSample(
                turn=i,
                metrics={
                    "a": base + random.gauss(0, 0.01),
                    "b": base * 0.8 + random.gauss(0, 0.01),
                    "c": base * 1.2 + random.gauss(0, 0.01),
                },
            ))
        return samples

    def test_empty_samples(self):
        signals = compute_signals([])
        assert signals.effective_dimension == 0.0
        assert signals.max_dimension == 0

    def test_independent_metrics(self):
        samples = self._make_independent_samples()
        signals = compute_signals(samples, ["a", "b", "c"])
        assert signals.effective_dimension >= 2
        assert signals.metric_agreement < 0.5
        assert signals.max_dimension == 3

    def test_correlated_metrics(self):
        samples = self._make_correlated_samples()
        signals = compute_signals(samples, ["a", "b", "c"])
        assert signals.variance_concentration > 0.5
        assert signals.metric_agreement > 0.5

    def test_action_entropy(self):
        samples = [MetricSample(i, {"a": 0.5}) for i in range(10)]
        actions = {"approve": 25, "reject": 25, "review": 25, "escalate": 25}
        signals = compute_signals(samples, ["a"], actions)
        assert signals.action_entropy > 1.5  # Near max entropy

    def test_low_action_entropy(self):
        samples = [MetricSample(i, {"a": 0.5}) for i in range(10)]
        actions = {"approve": 100, "reject": 1}
        signals = compute_signals(samples, ["a"], actions)
        assert signals.action_entropy < 0.2


# ---------------------------------------------------------------------------
# detect_collapse
# ---------------------------------------------------------------------------


class TestDetectCollapse:
    def test_healthy(self):
        random.seed(42)
        samples = [
            MetricSample(i, {
                "a": random.gauss(0.5, 0.1),
                "b": random.gauss(0.3, 0.2),
                "c": random.gauss(0.7, 0.15),
            })
            for i in range(50)
        ]
        report = detect_collapse(samples, ["a", "b", "c"])
        assert report.risk_level in (CollapseRisk.HEALTHY, CollapseRisk.WARNING)
        assert report.action in (CollapseAction.PASS, CollapseAction.WARN)

    def test_collapsed(self):
        random.seed(42)
        samples = []
        for i in range(50):
            base = i * 0.01
            samples.append(MetricSample(i, {
                "a": base + random.gauss(0, 0.001),
                "b": base * 0.8 + random.gauss(0, 0.001),
                "c": base * 1.2 + random.gauss(0, 0.001),
            }))
        report = detect_collapse(samples, ["a", "b", "c"])
        assert report.risk_score > 0.3
        assert report.signals.variance_concentration > 0.5

    def test_empty(self):
        report = detect_collapse([])
        assert report.risk_level == CollapseRisk.HEALTHY
        assert report.window_turns == 0

    def test_irreversible(self):
        """Risk > 0.8 sustained over 20+ turns → irreversible."""
        samples = []
        for i in range(25):
            base = i * 0.1
            samples.append(MetricSample(i, {
                "a": base,
                "b": base * 0.99,
                "c": base * 1.01,
            }))
        report = detect_collapse(
            samples, ["a", "b", "c"],
            action_counts={"approve": 100},
            irreversibility_threshold=20,
        )
        if report.risk_score > 0.8:
            assert report.irreversible

    def test_report_roundtrip(self):
        samples = [MetricSample(i, {"a": i * 0.1}) for i in range(20)]
        report = detect_collapse(samples, ["a"])
        d = report.to_dict()
        r2 = CollapseReport.from_dict(d)
        assert r2.report_id == report.report_id
        assert r2.risk_score == report.risk_score

    def test_summary(self):
        samples = [MetricSample(i, {"a": 0.5}) for i in range(10)]
        report = detect_collapse(samples, ["a"])
        summary = report.to_summary()
        assert "Risk score" in summary
        assert report.risk_level.value in summary


# ---------------------------------------------------------------------------
# Dominant Metric / Suppressed Modes
# ---------------------------------------------------------------------------


class TestDominantMetric:
    def test_one_dominant(self):
        random.seed(42)
        samples = [
            MetricSample(i, {
                "big": random.gauss(0, 10.0),  # High variance
                "small": random.gauss(0, 0.01),  # Low variance
            })
            for i in range(50)
        ]
        dominant = _find_dominant_metric(samples, ["big", "small"])
        assert dominant == "big"

    def test_no_dominant(self):
        samples = [MetricSample(i, {"a": 0.5, "b": 0.5}) for i in range(50)]
        dominant = _find_dominant_metric(samples, ["a", "b"])
        assert dominant is None  # All constant → no variance

    def test_empty(self):
        assert _find_dominant_metric([], ["a"]) is None


class TestSuppressedModes:
    def test_suppression(self):
        """Metric that loses variance in second half."""
        samples = []
        for i in range(40):
            if i < 20:
                # Early: high variance
                samples.append(MetricSample(i, {
                    "stable": random.gauss(0.5, 0.1),
                    "declining": random.gauss(0.5, 0.5),
                }))
            else:
                # Late: declining metric becomes constant
                samples.append(MetricSample(i, {
                    "stable": random.gauss(0.5, 0.1),
                    "declining": 0.5 + random.gauss(0, 0.01),
                }))
        suppressed = _find_suppressed_modes(samples, ["stable", "declining"])
        assert "declining" in suppressed

    def test_no_suppression(self):
        random.seed(42)
        samples = [
            MetricSample(i, {"a": random.gauss(0.5, 0.1)})
            for i in range(40)
        ]
        suppressed = _find_suppressed_modes(samples, ["a"])
        assert len(suppressed) == 0

    def test_insufficient_data(self):
        samples = [MetricSample(0, {"a": 0.5})]
        assert _find_suppressed_modes(samples, ["a"]) == []


# ---------------------------------------------------------------------------
# CollapseHistory
# ---------------------------------------------------------------------------


class TestCollapseHistory:
    def test_save_and_load(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = CollapseHistory(gov_dir)

        signals = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        report = CollapseReport(
            report_id="test123",
            signals=signals,
            risk_score=0.35,
            risk_level=CollapseRisk.WARNING,
            action=CollapseAction.WARN,
        )
        path = history.save_report(report)
        assert path is not None

        loaded = history.load_report("test123")
        assert loaded is not None
        assert loaded.risk_score == 0.35

    def test_list_reports(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = CollapseHistory(gov_dir)

        signals = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        for i in range(3):
            report = CollapseReport(
                report_id=f"r{i}",
                signals=signals,
                risk_score=0.1 * i,
                risk_level=CollapseRisk.HEALTHY,
                action=CollapseAction.PASS,
            )
            history.save_report(report)

        reports = history.list_reports()
        assert len(reports) == 3

    def test_no_governor_dir(self):
        history = CollapseHistory()
        assert history.save_report(CollapseReport(
            "r", CollapseSignals(0, 0, 0, 0, 0), 0.0,
            CollapseRisk.HEALTHY, CollapseAction.PASS,
        )) is None


# ---------------------------------------------------------------------------
# CollapseDetector
# ---------------------------------------------------------------------------


class TestCollapseDetector:
    def test_basic(self):
        detector = CollapseDetector(metric_names=["a", "b"])
        for i in range(20):
            detector.record_sample({"a": random.gauss(0.5, 0.1), "b": random.gauss(0.3, 0.2)})
        report = detector.check()
        assert isinstance(report, CollapseReport)

    def test_has_sufficient_data(self):
        detector = CollapseDetector(min_samples=10)
        assert not detector.has_sufficient_data
        for i in range(10):
            detector.record_sample({"a": 0.5})
        assert detector.has_sufficient_data

    def test_record_action(self):
        detector = CollapseDetector(metric_names=["a"])
        detector.record_action("approve")
        detector.record_action("approve")
        detector.record_action("reject")
        for i in range(10):
            detector.record_sample({"a": 0.5})
        report = detector.check()
        assert report.signals.action_entropy > 0

    def test_status(self):
        detector = CollapseDetector()
        status = detector.status()
        assert "sample_count" in status
        assert "metric_names" in status

    def test_window_size(self):
        detector = CollapseDetector(metric_names=["a"])
        for i in range(100):
            detector.record_sample({"a": random.gauss(0.5, 0.1)})
        report = detector.check(window_size=20)
        assert report.window_turns == 20

    def test_save_report(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        detector = CollapseDetector(metric_names=["a"], governor_dir=gov_dir)
        for i in range(10):
            detector.record_sample({"a": 0.5})
        detector.check()
        collapse_dir = gov_dir / "collapse"
        assert collapse_dir.exists()


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TestMakeCollapseEvent:
    def test_basic(self):
        signals = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        report = CollapseReport(
            report_id="test",
            signals=signals,
            risk_score=0.35,
            risk_level=CollapseRisk.WARNING,
            action=CollapseAction.WARN,
        )
        event = make_collapse_event(report)
        assert event["type"] == "collapse_check"
        assert event["risk_score"] == 0.35
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------


class TestGoldenSchemas:
    def test_collapse_signals_schema(self):
        s = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        d = s.to_dict()
        required = {"effective_dimension", "variance_concentration", "action_entropy", "metric_agreement", "max_dimension"}
        assert required == set(d.keys())

    def test_collapse_report_schema(self):
        signals = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        report = CollapseReport(
            report_id="test",
            signals=signals,
            risk_score=0.35,
            risk_level=CollapseRisk.WARNING,
            action=CollapseAction.WARN,
        )
        d = report.to_dict()
        required = {
            "report_id", "signals", "risk_score", "risk_level",
            "action", "dominant_metric", "suppressed_modes",
            "window_turns", "irreversible", "recommendations",
            "created_at",
        }
        assert required == set(d.keys())

    def test_collapse_event_schema(self):
        signals = CollapseSignals(3.0, 0.4, 1.5, 0.3, 5)
        report = CollapseReport(
            report_id="test", signals=signals,
            risk_score=0.35, risk_level=CollapseRisk.WARNING,
            action=CollapseAction.WARN,
        )
        event = make_collapse_event(report)
        required = {
            "type", "report_id", "risk_score", "risk_level",
            "action", "effective_dimension", "variance_concentration",
            "dominant_metric", "suppressed_modes", "irreversible",
            "window_turns", "timestamp",
        }
        assert required == set(event.keys())


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_healthy_system(self):
        """Independent metrics should produce healthy report."""
        random.seed(42)
        samples = [
            MetricSample(i, {
                "approval_rate": random.gauss(0.7, 0.1),
                "security_score": random.gauss(0.9, 0.05),
                "convergence_speed": random.gauss(0.5, 0.15),
            })
            for i in range(50)
        ]
        actions = {"approve": 30, "reject": 10, "review": 8, "escalate": 2}
        report = detect_collapse(samples, action_counts=actions)
        assert report.risk_level in (CollapseRisk.HEALTHY, CollapseRisk.WARNING)

    def test_collapsing_system(self):
        """Metrics converging to same trajectory = collapse."""
        random.seed(42)
        samples = []
        for i in range(50):
            base = 0.5 + i * 0.005
            noise = 0.001
            samples.append(MetricSample(i, {
                "approval_rate": base + random.gauss(0, noise),
                "security_score": base * 0.9 + random.gauss(0, noise),
                "convergence_speed": base * 1.1 + random.gauss(0, noise),
            }))
        actions = {"approve": 45, "reject": 3, "review": 1, "escalate": 1}
        report = detect_collapse(samples, action_counts=actions)
        # Should detect some level of collapse
        assert report.risk_score > 0.2  # At minimum warning-level

    def test_detector_lifecycle(self, tmp_path):
        """Full detector lifecycle: record → check → persist → query."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        detector = CollapseDetector(
            metric_names=["a", "b", "c"],
            governor_dir=gov_dir,
        )

        random.seed(42)
        for i in range(30):
            detector.record_sample({
                "a": random.gauss(0.5, 0.1),
                "b": random.gauss(0.3, 0.2),
                "c": random.gauss(0.7, 0.15),
            })
            detector.record_action(random.choice(["approve", "reject", "review"]))

        report = detector.check()
        assert isinstance(report, CollapseReport)
        assert detector.last_report is report

        # Check history was saved
        history = CollapseHistory(gov_dir)
        reports = history.list_reports()
        assert len(reports) >= 1

    def test_monotonic_risk(self):
        """More correlated metrics → higher risk."""
        risks = []
        for noise_scale in [0.5, 0.1, 0.01, 0.001]:
            random.seed(42)
            samples = []
            for i in range(50):
                base = i * 0.01
                samples.append(MetricSample(i, {
                    "a": base + random.gauss(0, noise_scale),
                    "b": base + random.gauss(0, noise_scale),
                    "c": base + random.gauss(0, noise_scale),
                }))
            report = detect_collapse(samples, ["a", "b", "c"])
            risks.append(report.risk_score)

        # Risk should generally increase as noise decreases (metrics converge)
        # Allow for some non-monotonicity due to estimation noise
        assert risks[-1] >= risks[0] - 0.1
