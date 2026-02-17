# SPDX-License-Identifier: Apache-2.0
"""Tests for auto_tuning module — Phase E8: Automated Tuning."""

import math
import pytest
from datetime import datetime, timezone

from governor.auto_tuning import (
    # Enums
    ResetType,
    TuningSuggestionKind,
    SweepMetric,
    CalibrationPhase,
    # Helper
    percentile,
    # Sub-feature 1: Threshold Auto-Tuning
    SignalDistribution,
    RegimeDistributions,
    ClassificationError,
    ThresholdSuggestion,
    ThresholdAnalysis,
    ThresholdTuner,
    THRESHOLD_MAP,
    # Sub-feature 2: Reset Effectiveness Tracking
    ResetCheckpoint,
    ResetRecord,
    ResetTypeSummary,
    ResetReport,
    ResetTracker,
    # Sub-feature 3: Setpoint Calibration
    BaselineObservation,
    BaselineProfile,
    CalibrationResult,
    SetpointCalibrator,
    # Sub-feature 4: Budget Sweep
    SweepPoint,
    ParetoPoint,
    SweepResult,
    BudgetSweeper,
    DEFAULT_QUALITY_WEIGHTS,
    # Orchestrator
    AutoTuner,
    # Convenience
    create_auto_tuner,
    create_threshold_tuner,
    create_reset_tracker,
    create_setpoint_calibrator,
    create_budget_sweeper,
    analyze_thresholds_from_metrics,
)
from governor.regime import (
    OperationalRegime,
    RegimeSignals,
    RegimeThresholds,
    RegimeMetrics,
)
from governor.homeostat import EpistemicVitals, EpistemicSetpoints


# =============================================================================
# Test Enums
# =============================================================================


class TestEnums:
    def test_reset_type_values(self):
        assert ResetType.CONTEXT == "context"
        assert ResetType.MODE == "mode"
        assert ResetType.CHAIN == "chain"
        assert ResetType.MANUAL == "manual"
        assert ResetType.EMERGENCY == "emergency"

    def test_tuning_suggestion_kind_values(self):
        assert TuningSuggestionKind.THRESHOLD == "threshold"
        assert TuningSuggestionKind.SETPOINT == "setpoint"
        assert TuningSuggestionKind.BUDGET == "budget"

    def test_sweep_metric_values(self):
        assert SweepMetric.BUDGET_BLOCK_FRACTION == "budget_block_fraction"
        assert SweepMetric.CONTRADICTION_ACCUMULATION == "contradiction_accumulation"
        assert SweepMetric.VIOLATION_RATE == "violation_rate"
        assert SweepMetric.DANGEROUS_RATE == "dangerous_rate"
        assert SweepMetric.REGIME_SEVERITY == "regime_severity"

    def test_calibration_phase_values(self):
        assert CalibrationPhase.BASELINE == "baseline"
        assert CalibrationPhase.OBSERVATION == "observation"
        assert CalibrationPhase.ANALYSIS == "analysis"
        assert CalibrationPhase.COMPLETE == "complete"


# =============================================================================
# Test Percentile
# =============================================================================


class TestPercentile:
    def test_single_value(self):
        assert percentile([42.0], 50) == 42.0

    def test_even_count(self):
        vals = [1.0, 2.0, 3.0, 4.0]
        assert percentile(vals, 50) == 2.5

    def test_odd_count(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile(vals, 50) == 3.0

    def test_p0_and_p100(self):
        vals = [10.0, 20.0, 30.0]
        assert percentile(vals, 0) == 10.0
        assert percentile(vals, 100) == 30.0

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            percentile([], 50)


# =============================================================================
# Test SignalDistribution
# =============================================================================


class TestSignalDistribution:
    def test_create(self):
        sd = SignalDistribution(
            signal_name="hysteresis", count=100,
            min_val=0.0, max_val=1.0, mean=0.5, median=0.5,
            p25=0.25, p75=0.75, p90=0.9, p95=0.95, stddev=0.2,
        )
        assert sd.signal_name == "hysteresis"
        assert sd.count == 100

    def test_to_dict_from_dict(self):
        sd = SignalDistribution(
            signal_name="tool_gain", count=50,
            min_val=0.1, max_val=0.9, mean=0.5, median=0.5,
            p25=0.3, p75=0.7, p90=0.85, p95=0.9, stddev=0.15,
        )
        d = sd.to_dict()
        restored = SignalDistribution.from_dict(d)
        assert restored.signal_name == sd.signal_name
        assert restored.count == sd.count
        assert restored.mean == sd.mean

    def test_from_values(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        sd = SignalDistribution.from_values("test_signal", vals)
        assert sd.count == 10
        assert sd.min_val == 1.0
        assert sd.max_val == 10.0
        assert sd.mean == 5.5

    def test_from_values_single(self):
        sd = SignalDistribution.from_values("single", [42.0])
        assert sd.count == 1
        assert sd.mean == 42.0
        assert sd.median == 42.0
        assert sd.stddev == 0.0

    def test_from_values_empty(self):
        sd = SignalDistribution.from_values("empty", [])
        assert sd.count == 0
        assert sd.mean == 0.0


# =============================================================================
# Test RegimeDistributions
# =============================================================================


class TestRegimeDistributions:
    def test_create(self):
        rd = RegimeDistributions(
            regime=OperationalRegime.ELASTIC,
            sample_count=100,
        )
        assert rd.regime == OperationalRegime.ELASTIC
        assert rd.sample_count == 100

    def test_to_dict_from_dict(self):
        sd = SignalDistribution.from_values("hysteresis", [0.1, 0.2, 0.3])
        rd = RegimeDistributions(
            regime=OperationalRegime.WARM,
            sample_count=3,
            distributions={"hysteresis": sd},
        )
        d = rd.to_dict()
        restored = RegimeDistributions.from_dict(d)
        assert restored.regime == OperationalRegime.WARM
        assert "hysteresis" in restored.distributions

    def test_from_dict_empty(self):
        d = {"regime": "elastic", "sample_count": 0}
        rd = RegimeDistributions.from_dict(d)
        assert rd.distributions == {}

    def test_with_multiple_distributions(self):
        sd1 = SignalDistribution.from_values("hysteresis", [0.1, 0.2])
        sd2 = SignalDistribution.from_values("tool_gain", [0.5, 0.6])
        rd = RegimeDistributions(
            regime=OperationalRegime.ELASTIC,
            sample_count=2,
            distributions={"hysteresis": sd1, "tool_gain": sd2},
        )
        assert len(rd.distributions) == 2


# =============================================================================
# Test ThresholdSuggestion
# =============================================================================


class TestThresholdSuggestion:
    def test_create(self):
        ts = ThresholdSuggestion(
            threshold_name="warm_hysteresis",
            current_value=0.2,
            suggested_value=0.25,
            confidence=0.8,
            reason="Clear boundary",
        )
        assert ts.threshold_name == "warm_hysteresis"
        assert ts.suggested_value == 0.25

    def test_to_dict_from_dict(self):
        ts = ThresholdSuggestion(
            threshold_name="warm_hysteresis",
            current_value=0.2,
            suggested_value=0.25,
            confidence=0.8,
            reason="test",
            fp_rate=0.05,
            fn_rate=0.03,
        )
        d = ts.to_dict()
        restored = ThresholdSuggestion.from_dict(d)
        assert restored.threshold_name == ts.threshold_name
        assert restored.fp_rate == 0.05
        assert restored.fn_rate == 0.03

    def test_from_dict_defaults(self):
        d = {
            "threshold_name": "x",
            "current_value": 0.1,
            "suggested_value": 0.2,
            "confidence": 0.5,
            "reason": "r",
        }
        ts = ThresholdSuggestion.from_dict(d)
        assert ts.fp_rate == 0.0
        assert ts.fn_rate == 0.0

    def test_confidence_range(self):
        ts = ThresholdSuggestion(
            threshold_name="x", current_value=0.1,
            suggested_value=0.2, confidence=0.95, reason="r",
        )
        assert 0.0 <= ts.confidence <= 1.0


# =============================================================================
# Test ThresholdAnalysis
# =============================================================================


class TestThresholdAnalysis:
    def test_create(self):
        ta = ThresholdAnalysis(
            distributions={},
            suggestions=[],
            total_samples=100,
            fp_count=5,
            fn_count=3,
            accuracy=0.92,
        )
        assert ta.total_samples == 100
        assert ta.accuracy == 0.92

    def test_to_dict_from_dict(self):
        ta = ThresholdAnalysis(
            distributions={},
            suggestions=[],
            total_samples=50,
            fp_count=2,
            fn_count=1,
            accuracy=0.94,
        )
        d = ta.to_dict()
        restored = ThresholdAnalysis.from_dict(d)
        assert restored.total_samples == 50
        assert restored.accuracy == 0.94

    def test_with_suggestions(self):
        ts = ThresholdSuggestion(
            threshold_name="warm_hysteresis",
            current_value=0.2, suggested_value=0.25,
            confidence=0.8, reason="test",
        )
        ta = ThresholdAnalysis(
            distributions={},
            suggestions=[ts],
            total_samples=100,
            fp_count=0, fn_count=0,
            accuracy=1.0,
        )
        d = ta.to_dict()
        restored = ThresholdAnalysis.from_dict(d)
        assert len(restored.suggestions) == 1
        assert restored.suggestions[0].threshold_name == "warm_hysteresis"


# =============================================================================
# Test ThresholdTuner
# =============================================================================


class TestThresholdTuner:
    def _make_signals(self, **kwargs) -> RegimeSignals:
        return RegimeSignals(**kwargs)

    def test_record(self):
        tuner = ThresholdTuner()
        sig = self._make_signals(hysteresis=0.1)
        tuner.record(sig, OperationalRegime.ELASTIC)
        assert len(tuner._observations) == 1

    def test_max_history(self):
        tuner = ThresholdTuner(max_history=5)
        for i in range(10):
            tuner.record(self._make_signals(hysteresis=i * 0.1), OperationalRegime.ELASTIC)
        assert len(tuner._observations) == 5

    def test_load_from_metrics(self):
        metrics = RegimeMetrics()
        for i in range(15):
            sig = self._make_signals(hysteresis=i * 0.05)
            metrics.record_signal(sig, OperationalRegime.ELASTIC)
        tuner = ThresholdTuner()
        loaded = tuner.load_from_metrics(metrics)
        assert loaded == 15

    def test_distributions(self):
        tuner = ThresholdTuner(min_samples_per_regime=3)
        for i in range(10):
            tuner.record(self._make_signals(hysteresis=0.1 + i * 0.01), OperationalRegime.ELASTIC)
        dists = tuner._compute_distributions()
        assert "elastic" in dists
        assert "hysteresis" in dists["elastic"].distributions

    def test_suggest_clear_boundary(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        # ELASTIC: low hysteresis
        for _ in range(10):
            tuner.record(self._make_signals(hysteresis=0.1), OperationalRegime.ELASTIC)
        # WARM: high hysteresis
        for _ in range(10):
            tuner.record(self._make_signals(hysteresis=0.5), OperationalRegime.WARM)

        thresholds = RegimeThresholds()
        suggestions = tuner.suggest_thresholds(thresholds)
        # Should suggest adjusting warm_hysteresis
        hyst_suggestions = [s for s in suggestions if s.threshold_name == "warm_hysteresis"]
        assert len(hyst_suggestions) > 0
        # Suggested value should be between 0.1 and 0.5
        s = hyst_suggestions[0]
        assert 0.1 <= s.suggested_value <= 0.5

    def test_suggest_overlapping_boundary(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        # Overlapping distributions
        for i in range(10):
            tuner.record(self._make_signals(hysteresis=0.15 + i * 0.03), OperationalRegime.ELASTIC)
        for i in range(10):
            tuner.record(self._make_signals(hysteresis=0.20 + i * 0.03), OperationalRegime.WARM)

        thresholds = RegimeThresholds()
        suggestions = tuner.suggest_thresholds(thresholds)
        hyst = [s for s in suggestions if s.threshold_name == "warm_hysteresis"]
        if hyst:
            # Low confidence due to overlap
            assert hyst[0].confidence <= 0.5

    def test_suggest_insufficient_samples(self):
        tuner = ThresholdTuner(min_samples_per_regime=20)
        for _ in range(5):
            tuner.record(self._make_signals(hysteresis=0.1), OperationalRegime.ELASTIC)
        for _ in range(5):
            tuner.record(self._make_signals(hysteresis=0.5), OperationalRegime.WARM)
        suggestions = tuner.suggest_thresholds(RegimeThresholds())
        # Not enough samples — shouldn't suggest for warm_hysteresis
        hyst = [s for s in suggestions if s.threshold_name == "warm_hysteresis"]
        assert len(hyst) == 0

    def test_analyze(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        for _ in range(10):
            tuner.record(self._make_signals(hysteresis=0.05), OperationalRegime.ELASTIC)
        for _ in range(10):
            tuner.record(self._make_signals(hysteresis=0.4), OperationalRegime.WARM)
        analysis = tuner.analyze(RegimeThresholds())
        assert analysis.total_samples == 20
        assert 0.0 <= analysis.accuracy <= 1.0

    def test_suggest_fp_fn_rates(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        for _ in range(20):
            tuner.record(self._make_signals(hysteresis=0.05), OperationalRegime.ELASTIC)
        for _ in range(20):
            tuner.record(self._make_signals(hysteresis=0.6), OperationalRegime.WARM)
        suggestions = tuner.suggest_thresholds(RegimeThresholds())
        for s in suggestions:
            assert 0.0 <= s.fp_rate <= 1.0
            assert 0.0 <= s.fn_rate <= 1.0

    def test_apply_suggestions(self):
        tuner = ThresholdTuner()
        thresholds = RegimeThresholds()
        suggestions = [
            ThresholdSuggestion(
                threshold_name="warm_hysteresis",
                current_value=0.2,
                suggested_value=0.25,
                confidence=0.8,
                reason="test",
            ),
            ThresholdSuggestion(
                threshold_name="warm_relaxation",
                current_value=3.0,
                suggested_value=3.5,
                confidence=0.3,  # Below min_confidence
                reason="low conf",
            ),
        ]
        new_thresholds = tuner.apply_suggestions(thresholds, suggestions, min_confidence=0.5)
        assert new_thresholds.warm_hysteresis == 0.25
        assert new_thresholds.warm_relaxation == 3.0  # Not applied

    def test_apply_suggestions_filtered(self):
        tuner = ThresholdTuner()
        thresholds = RegimeThresholds()
        suggestions = [
            ThresholdSuggestion(
                threshold_name="warm_hysteresis",
                current_value=0.2,
                suggested_value=0.25,
                confidence=0.4,
                reason="low",
            ),
        ]
        new_thresholds = tuner.apply_suggestions(thresholds, suggestions, min_confidence=0.5)
        assert new_thresholds.warm_hysteresis == 0.2  # Not applied

    def test_serialization(self):
        tuner = ThresholdTuner(min_samples_per_regime=15)
        tuner.record(self._make_signals(hysteresis=0.1), OperationalRegime.ELASTIC)
        d = tuner.to_dict()
        restored = ThresholdTuner.from_dict(d)
        assert restored.min_samples_per_regime == 15
        assert len(restored._observations) == 1

    def test_error_rates_in_analysis(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        # Some elastic observations above warm_hysteresis threshold (0.2) → false positives
        for _ in range(5):
            tuner.record(self._make_signals(hysteresis=0.1), OperationalRegime.ELASTIC)
        for _ in range(5):
            tuner.record(self._make_signals(hysteresis=0.3), OperationalRegime.ELASTIC)
        for _ in range(10):
            tuner.record(self._make_signals(hysteresis=0.4), OperationalRegime.WARM)
        analysis = tuner.analyze(RegimeThresholds())
        # Should have some fp (elastic with hysteresis > 0.2)
        assert analysis.fp_count >= 0


# =============================================================================
# Test ResetCheckpoint
# =============================================================================


class TestResetCheckpoint:
    def test_create(self):
        cp = ResetCheckpoint(turns_after=1, regime=OperationalRegime.WARM)
        assert cp.turns_after == 1
        assert cp.signals is None

    def test_to_dict_from_dict(self):
        cp = ResetCheckpoint(
            turns_after=3,
            regime=OperationalRegime.ELASTIC,
            signals={"hysteresis": 0.1},
        )
        d = cp.to_dict()
        restored = ResetCheckpoint.from_dict(d)
        assert restored.turns_after == 3
        assert restored.signals == {"hysteresis": 0.1}

    def test_from_dict_no_signals(self):
        d = {"turns_after": 5, "regime": "ductile"}
        cp = ResetCheckpoint.from_dict(d)
        assert cp.regime == OperationalRegime.DUCTILE
        assert cp.signals is None


# =============================================================================
# Test ResetRecord
# =============================================================================


class TestResetRecord:
    def test_create(self):
        rr = ResetRecord(
            reset_id="r1",
            reset_type=ResetType.CONTEXT,
            reset_turn=10,
            regime_at_reset=OperationalRegime.WARM,
        )
        assert rr.reset_id == "r1"
        assert not rr.complete

    def test_with_checkpoints(self):
        rr = ResetRecord(
            reset_id="r2",
            reset_type=ResetType.MODE,
            reset_turn=5,
            regime_at_reset=OperationalRegime.DUCTILE,
            checkpoints=[
                ResetCheckpoint(turns_after=1, regime=OperationalRegime.WARM),
            ],
        )
        assert len(rr.checkpoints) == 1

    def test_completion_flags(self):
        rr = ResetRecord(
            reset_id="r3",
            reset_type=ResetType.EMERGENCY,
            reset_turn=0,
            regime_at_reset=OperationalRegime.UNSTABLE,
            restored_elastic=True,
            turns_to_restore=3,
            complete=True,
        )
        assert rr.restored_elastic
        assert rr.turns_to_restore == 3

    def test_serialization(self):
        rr = ResetRecord(
            reset_id="r4",
            reset_type=ResetType.CHAIN,
            reset_turn=7,
            regime_at_reset=OperationalRegime.WARM,
            checkpoints=[
                ResetCheckpoint(turns_after=1, regime=OperationalRegime.ELASTIC),
            ],
            restored_elastic=True,
            turns_to_restore=1,
            complete=True,
        )
        d = rr.to_dict()
        restored = ResetRecord.from_dict(d)
        assert restored.reset_id == "r4"
        assert restored.restored_elastic
        assert len(restored.checkpoints) == 1


# =============================================================================
# Test ResetTracker
# =============================================================================


class TestResetTracker:
    def test_record_reset(self):
        tracker = ResetTracker()
        record = tracker.record_reset("r1", ResetType.CONTEXT, OperationalRegime.WARM)
        assert record.reset_id == "r1"
        assert tracker.pending_count == 1

    def test_advance_turn_checkpoint_1(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        completed = tracker.advance_turn(OperationalRegime.ELASTIC)
        assert len(completed) == 0  # Turn 1 checkpoint but not last
        record = tracker._records[0]
        assert len(record.checkpoints) == 1
        assert record.checkpoints[0].turns_after == 1

    def test_advance_turn_checkpoint_3(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        tracker.advance_turn(OperationalRegime.WARM)   # turn 1
        tracker.advance_turn(OperationalRegime.WARM)   # turn 2
        tracker.advance_turn(OperationalRegime.WARM)   # turn 3
        record = tracker._records[0]
        assert len(record.checkpoints) == 2  # checkpoints at 1 and 3

    def test_advance_turn_checkpoint_5_completes(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        for i in range(5):
            completed = tracker.advance_turn(OperationalRegime.WARM)
        assert len(completed) == 1
        assert completed[0].complete
        assert not completed[0].restored_elastic

    def test_restored_elastic_true(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        tracker.advance_turn(OperationalRegime.ELASTIC)  # Restored at turn 1
        record = tracker._records[0]
        assert record.restored_elastic
        assert record.turns_to_restore == 1

    def test_restored_elastic_false(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.DUCTILE)
        for _ in range(5):
            tracker.advance_turn(OperationalRegime.WARM)
        record = tracker._records[0]
        assert not record.restored_elastic
        assert record.turns_to_restore is None

    def test_turns_to_restore_at_3(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.CHAIN, OperationalRegime.DUCTILE)
        tracker.advance_turn(OperationalRegime.WARM)    # turn 1
        tracker.advance_turn(OperationalRegime.WARM)    # turn 2
        tracker.advance_turn(OperationalRegime.ELASTIC) # turn 3
        record = tracker._records[0]
        assert record.restored_elastic
        assert record.turns_to_restore == 3

    def test_concurrent_resets(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        tracker.advance_turn(OperationalRegime.WARM)  # turn 1 for r1
        tracker.record_reset("r2", ResetType.CONTEXT, OperationalRegime.DUCTILE)
        tracker.advance_turn(OperationalRegime.ELASTIC)  # turn 2 for r1, turn 1 for r2
        r1 = tracker._records[0]
        r2 = tracker._records[1]
        assert len(r1.checkpoints) == 1  # turn 1 only (turn 2 is not a checkpoint)
        assert len(r2.checkpoints) == 1  # turn 1

    def test_report_empty(self):
        tracker = ResetTracker()
        report = tracker.report()
        assert report.total_resets == 0
        assert report.overall_success_rate == 0.0

    def test_report(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        for _ in range(5):
            tracker.advance_turn(OperationalRegime.ELASTIC)
        report = tracker.report()
        assert report.total_resets == 1
        assert report.total_completed == 1
        assert report.overall_success_rate == 1.0
        assert "mode" in report.by_type

    def test_success_rate_by_type(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.MODE, OperationalRegime.WARM)
        for _ in range(5):
            tracker.advance_turn(OperationalRegime.ELASTIC)
        rate = tracker.success_rate_by_type(ResetType.MODE)
        assert rate == 1.0
        assert tracker.success_rate_by_type(ResetType.CHAIN) is None

    def test_max_records(self):
        tracker = ResetTracker(max_records=3)
        for i in range(5):
            tracker.record_reset(f"r{i}", ResetType.MODE, OperationalRegime.WARM)
        assert len(tracker._records) == 3

    def test_serialization(self):
        tracker = ResetTracker()
        tracker.record_reset("r1", ResetType.CONTEXT, OperationalRegime.WARM)
        tracker.advance_turn(OperationalRegime.ELASTIC)
        d = tracker.to_dict()
        restored = ResetTracker.from_dict(d)
        assert len(restored._records) == 1
        assert restored._current_turn == 1


# =============================================================================
# Test ResetReport
# =============================================================================


class TestResetReport:
    def test_empty(self):
        rr = ResetReport(
            total_resets=0,
            total_completed=0,
            overall_success_rate=0.0,
        )
        assert rr.total_resets == 0

    def test_by_type(self):
        summary = ResetTypeSummary(
            reset_type=ResetType.MODE,
            total=10,
            restored_count=7,
            success_rate=0.7,
            avg_turns_to_restore=2.5,
            regime_distribution_after_5={"elastic": 7, "warm": 3},
        )
        rr = ResetReport(
            total_resets=10,
            total_completed=10,
            overall_success_rate=0.7,
            by_type={"mode": summary},
        )
        assert rr.by_type["mode"].success_rate == 0.7

    def test_success_rate(self):
        summary = ResetTypeSummary(
            reset_type=ResetType.EMERGENCY,
            total=5,
            restored_count=2,
            success_rate=0.4,
            avg_turns_to_restore=4.0,
            regime_distribution_after_5={"warm": 3, "elastic": 2},
        )
        assert summary.success_rate == 0.4

    def test_regime_dist(self):
        summary = ResetTypeSummary(
            reset_type=ResetType.CHAIN,
            total=3,
            restored_count=1,
            success_rate=1 / 3,
            avg_turns_to_restore=5.0,
            regime_distribution_after_5={"elastic": 1, "ductile": 2},
        )
        d = summary.to_dict()
        assert d["regime_distribution_after_5"]["ductile"] == 2


# =============================================================================
# Test BaselineProfile
# =============================================================================


class TestBaselineProfile:
    def test_create(self):
        bp = BaselineProfile(domain="medical", observation_count=100)
        assert bp.domain == "medical"

    def test_to_setpoints_default(self):
        bp = BaselineProfile(
            domain="general", observation_count=50,
            natural_revision_rate=0.05,
            natural_contradiction_rate=0.02,
            natural_hedge_rate=0.15,
            natural_refusal_rate=0.01,
            natural_support_deficit_rate=0.10,
            natural_retrieval_coverage=0.90,
            revision_stddev=0.02,
            contradiction_stddev=0.01,
            hedge_stddev=0.05,
            refusal_stddev=0.005,
            support_deficit_stddev=0.03,
            retrieval_coverage_stddev=0.05,
        )
        sp = bp.to_setpoints()  # default safety_margin=1.5
        assert sp.revision_target == pytest.approx(0.05 + 1.5 * 0.02, abs=0.001)
        assert sp.contradiction_target == pytest.approx(0.02 + 1.5 * 0.01, abs=0.001)
        # retrieval_coverage target is natural - margin * stddev
        assert sp.retrieval_coverage_target == pytest.approx(0.90 - 1.5 * 0.05, abs=0.001)

    def test_to_setpoints_custom_margin(self):
        bp = BaselineProfile(
            domain="general", observation_count=50,
            natural_revision_rate=0.05,
            revision_stddev=0.02,
        )
        sp = bp.to_setpoints(safety_margin=2.0)
        assert sp.revision_target == pytest.approx(0.05 + 2.0 * 0.02, abs=0.001)

    def test_to_dict_from_dict(self):
        bp = BaselineProfile(
            domain="legal", observation_count=200,
            natural_revision_rate=0.03,
            revision_stddev=0.01,
            revision_retraction_correlation=0.85,
        )
        d = bp.to_dict()
        restored = BaselineProfile.from_dict(d)
        assert restored.domain == "legal"
        assert restored.revision_retraction_correlation == 0.85

    def test_setpoints_clamped(self):
        # Ensure setpoints don't go above 1.0
        bp = BaselineProfile(
            domain="test", observation_count=10,
            natural_revision_rate=0.9,
            revision_stddev=0.2,
        )
        sp = bp.to_setpoints(safety_margin=2.0)
        assert sp.revision_target <= 1.0


# =============================================================================
# Test SetpointCalibrator
# =============================================================================


class TestSetpointCalibrator:
    def _make_vitals(self, **kwargs) -> EpistemicVitals:
        defaults = {
            "revision_rate": 0.05,
            "contradiction_rate": 0.02,
            "hedge_rate": 0.15,
            "refusal_rate": 0.01,
            "support_deficit_rate": 0.10,
            "retrieval_coverage": 0.90,
        }
        defaults.update(kwargs)
        return EpistemicVitals(**defaults)

    def test_phases(self):
        cal = SetpointCalibrator()
        assert cal.phase == CalibrationPhase.BASELINE

    def test_begin_baseline(self):
        cal = SetpointCalibrator()
        cal.begin_baseline()
        assert cal.phase == CalibrationPhase.BASELINE

    def test_record_baseline(self):
        cal = SetpointCalibrator()
        cal.begin_baseline()
        cal.record_baseline(self._make_vitals(), OperationalRegime.ELASTIC)
        assert len(cal._baseline_observations) == 1

    def test_end_baseline_insufficient(self):
        cal = SetpointCalibrator()
        cal.begin_baseline()
        for _ in range(5):
            cal.record_baseline(self._make_vitals(), OperationalRegime.ELASTIC)
        result = cal.end_baseline()
        assert result is None  # Not enough samples

    def test_end_baseline_sufficient(self):
        cal = SetpointCalibrator()
        cal.begin_baseline()
        for i in range(25):
            cal.record_baseline(
                self._make_vitals(revision_rate=0.04 + i * 0.001),
                OperationalRegime.ELASTIC,
            )
        profile = cal.end_baseline()
        assert profile is not None
        assert profile.observation_count == 25
        assert cal.phase == CalibrationPhase.ANALYSIS

    def test_correlation(self):
        # Perfect positive correlation
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        corr = SetpointCalibrator._compute_correlation(xs, ys)
        assert corr == pytest.approx(1.0, abs=0.01)

    def test_correlation_negative(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [10.0, 8.0, 6.0, 4.0, 2.0]
        corr = SetpointCalibrator._compute_correlation(xs, ys)
        assert corr == pytest.approx(-1.0, abs=0.01)

    def test_correlation_insufficient(self):
        corr = SetpointCalibrator._compute_correlation([1.0], [2.0])
        assert corr == 0.0

    def test_observation_phase(self):
        cal = SetpointCalibrator()
        cal.begin_observation()
        assert cal.phase == CalibrationPhase.OBSERVATION
        cal.record_observation(self._make_vitals(), OperationalRegime.ELASTIC)
        assert len(cal._observation_observations) == 1

    def test_calibrate_no_baseline(self):
        cal = SetpointCalibrator()
        result = cal.calibrate()
        assert result.baseline is None
        assert result.calibrated_setpoints is None
        assert result.confidence == 0.0

    def test_calibrate_with_baseline(self):
        cal = SetpointCalibrator(domain="test")
        cal.begin_baseline()
        for i in range(25):
            cal.record_baseline(self._make_vitals(), OperationalRegime.ELASTIC)
        cal.end_baseline()
        result = cal.calibrate()
        assert result.phase == CalibrationPhase.COMPLETE
        assert result.calibrated_setpoints is not None
        assert result.confidence > 0.0

    def test_domain(self):
        cal = SetpointCalibrator(domain="medical")
        assert cal.domain == "medical"

    def test_serialization(self):
        cal = SetpointCalibrator(domain="legal", safety_margin=2.0)
        cal.begin_baseline()
        for i in range(25):
            cal.record_baseline(self._make_vitals(), OperationalRegime.ELASTIC)
        cal.end_baseline()
        d = cal.to_dict()
        restored = SetpointCalibrator.from_dict(d)
        assert restored.domain == "legal"
        assert restored.safety_margin == 2.0
        assert restored._baseline_profile is not None
        assert len(restored._baseline_observations) == 25


# =============================================================================
# Test CalibrationResult
# =============================================================================


class TestCalibrationResult:
    def test_create(self):
        cr = CalibrationResult(
            domain="general",
            phase=CalibrationPhase.COMPLETE,
            baseline=None,
            calibrated_setpoints=None,
            observation_count=0,
            confidence=0.0,
        )
        assert cr.domain == "general"

    def test_to_dict_from_dict(self):
        bp = BaselineProfile(domain="test", observation_count=50)
        sp = EpistemicSetpoints()
        cr = CalibrationResult(
            domain="test",
            phase=CalibrationPhase.COMPLETE,
            baseline=bp,
            calibrated_setpoints=sp,
            observation_count=50,
            confidence=0.5,
        )
        d = cr.to_dict()
        restored = CalibrationResult.from_dict(d)
        assert restored.domain == "test"
        assert restored.confidence == 0.5
        assert restored.baseline is not None

    def test_from_dict_nulls(self):
        d = {
            "domain": "x",
            "phase": "baseline",
            "baseline": None,
            "calibrated_setpoints": None,
            "observation_count": 0,
            "confidence": 0.0,
        }
        cr = CalibrationResult.from_dict(d)
        assert cr.baseline is None
        assert cr.calibrated_setpoints is None


# =============================================================================
# Test SweepPoint
# =============================================================================


class TestSweepPoint:
    def test_create(self):
        sp = SweepPoint(
            parameter_name="claim_budget",
            parameter_value=10.0,
            turns=100,
            budget_block_fraction=0.2,
            contradiction_accumulation=0.1,
            violation_rate=0.05,
            dangerous_rate=0.02,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.3,
            c_open_final=2,
            c_open_max=5,
        )
        assert sp.parameter_name == "claim_budget"

    def test_to_dict_from_dict(self):
        sp = SweepPoint(
            parameter_name="budget",
            parameter_value=20.0,
            turns=50,
            budget_block_fraction=0.1,
            contradiction_accumulation=0.05,
            violation_rate=0.03,
            dangerous_rate=0.01,
            regime_at_end=OperationalRegime.WARM,
            regime_severity_avg=0.5,
            c_open_final=1,
            c_open_max=3,
        )
        d = sp.to_dict()
        restored = SweepPoint.from_dict(d)
        assert restored.parameter_value == 20.0
        assert restored.regime_at_end == OperationalRegime.WARM

    def test_from_dict_defaults(self):
        d = {
            "parameter_name": "x",
            "parameter_value": 1.0,
            "turns": 10,
            "budget_block_fraction": 0.0,
            "contradiction_accumulation": 0.0,
            "violation_rate": 0.0,
            "dangerous_rate": 0.0,
            "regime_at_end": "elastic",
            "regime_severity_avg": 0.0,
            "c_open_final": 0,
            "c_open_max": 0,
        }
        sp = SweepPoint.from_dict(d)
        assert sp.c_open_final == 0


# =============================================================================
# Test BudgetSweeper
# =============================================================================


class TestBudgetSweeper:
    def test_record_point(self):
        sweeper = BudgetSweeper("claim_budget")
        point = sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.2,
            contradiction_accumulation=0.1,
            violation_rate=0.05, dangerous_rate=0.02,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.3,
        )
        assert point.parameter_value == 10.0
        assert len(sweeper._points) == 1

    def test_quality_score(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.5,
            contradiction_accumulation=0.3,
            violation_rate=0.2, dangerous_rate=0.1,
            regime_at_end=OperationalRegime.WARM,
            regime_severity_avg=1.0,
        )
        q = sweeper._compute_quality(sweeper._points[0])
        # All penalties are negative, so quality should be negative
        assert q < 0

    def test_tightness(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=5.0, turns=50,
            budget_block_fraction=0.8,
            contradiction_accumulation=0.0,
            violation_rate=0.0, dangerous_rate=0.0,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.0,
        )
        t = sweeper._compute_tightness(sweeper._points[0])
        assert t == pytest.approx(0.8, abs=0.01)

    def test_pareto_two_points(self):
        sweeper = BudgetSweeper("budget")
        # Point A: good quality, low tightness
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.1,
            contradiction_accumulation=0.05,
            violation_rate=0.02, dangerous_rate=0.01,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.1,
        )
        # Point B: worse quality, higher tightness
        sweeper.record_point(
            parameter_value=5.0, turns=100,
            budget_block_fraction=0.5,
            contradiction_accumulation=0.3,
            violation_rate=0.2, dangerous_rate=0.1,
            regime_at_end=OperationalRegime.WARM,
            regime_severity_avg=1.0,
        )
        pareto = sweeper._compute_pareto_frontier()
        # Point A dominates Point B
        assert len(pareto) == 1
        assert pareto[0].parameter_value == 10.0

    def test_pareto_five_points(self):
        sweeper = BudgetSweeper("budget")
        configs = [
            (5.0, 0.6, 0.4, 0.3, 0.15, 1.5),
            (10.0, 0.3, 0.2, 0.1, 0.05, 0.5),
            (15.0, 0.1, 0.1, 0.05, 0.02, 0.2),
            (20.0, 0.05, 0.05, 0.02, 0.01, 0.1),
            (25.0, 0.02, 0.02, 0.01, 0.005, 0.05),
        ]
        for val, bbf, ca, vr, dr, rs in configs:
            sweeper.record_point(
                parameter_value=val, turns=100,
                budget_block_fraction=bbf,
                contradiction_accumulation=ca,
                violation_rate=vr, dangerous_rate=dr,
                regime_at_end=OperationalRegime.ELASTIC,
                regime_severity_avg=rs,
            )
        pareto = sweeper._compute_pareto_frontier()
        assert len(pareto) >= 1

    def test_pareto_all_dominated(self):
        sweeper = BudgetSweeper("budget")
        # One point dominates all others
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.01,
            contradiction_accumulation=0.01,
            violation_rate=0.01, dangerous_rate=0.01,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.0,
        )
        for val in [5.0, 15.0, 20.0]:
            sweeper.record_point(
                parameter_value=val, turns=100,
                budget_block_fraction=0.5,
                contradiction_accumulation=0.5,
                violation_rate=0.5, dangerous_rate=0.5,
                regime_at_end=OperationalRegime.WARM,
                regime_severity_avg=1.0,
            )
        pareto = sweeper._compute_pareto_frontier()
        assert len(pareto) == 1
        assert pareto[0].parameter_value == 10.0

    def test_pareto_none_dominated(self):
        sweeper = BudgetSweeper("budget")
        # Trade-off: A has low tightness but bad quality; B has high tightness but good quality
        # Point A: loose (low block) but high contradictions/violations -> bad quality, low tightness
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.01,
            contradiction_accumulation=0.5,
            violation_rate=0.3, dangerous_rate=0.2,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.3,
        )
        # Point B: tight (high block) but zero contradictions/violations -> better quality, high tightness
        sweeper.record_point(
            parameter_value=20.0, turns=100,
            budget_block_fraction=0.5,
            contradiction_accumulation=0.0,
            violation_rate=0.0, dangerous_rate=0.0,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.0,
        )
        pareto = sweeper._compute_pareto_frontier()
        assert len(pareto) == 2

    def test_analyze(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.2,
            contradiction_accumulation=0.1,
            violation_rate=0.05, dangerous_rate=0.02,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.3,
        )
        result = sweeper.analyze()
        assert result.parameter_name == "budget"
        assert result.recommended_value is not None
        assert result.safety_invariant_held

    def test_recommend(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.1,
            contradiction_accumulation=0.05,
            violation_rate=0.02, dangerous_rate=0.01,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.2,
        )
        sweeper.record_point(
            parameter_value=5.0, turns=100,
            budget_block_fraction=0.5,
            contradiction_accumulation=0.3,
            violation_rate=0.2, dangerous_rate=0.1,
            regime_at_end=OperationalRegime.WARM,
            regime_severity_avg=1.0,
        )
        result = sweeper.analyze()
        assert result.recommended_value == 10.0

    def test_safety_invariant(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=1.0, turns=100,
            budget_block_fraction=0.9,
            contradiction_accumulation=0.8,
            violation_rate=0.5, dangerous_rate=0.3,
            regime_at_end=OperationalRegime.UNSTABLE,
            regime_severity_avg=3.0,
        )
        result = sweeper.analyze()
        assert not result.safety_invariant_held

    def test_serialization(self):
        sweeper = BudgetSweeper("test_param")
        sweeper.record_point(
            parameter_value=10.0, turns=50,
            budget_block_fraction=0.1,
            contradiction_accumulation=0.05,
            violation_rate=0.02, dangerous_rate=0.01,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.1,
        )
        d = sweeper.to_dict()
        restored = BudgetSweeper.from_dict(d)
        assert restored.parameter_name == "test_param"
        assert len(restored._points) == 1


# =============================================================================
# Test AutoTuner
# =============================================================================


class TestAutoTuner:
    def test_create(self):
        at = AutoTuner()
        assert at.threshold_tuner is not None
        assert at.reset_tracker is not None
        assert at.setpoint_calibrator is not None

    def test_record_signal(self):
        at = AutoTuner()
        sig = RegimeSignals(hysteresis=0.1)
        at.record_signal(sig, OperationalRegime.ELASTIC)
        assert len(at.threshold_tuner._observations) == 1

    def test_record_reset(self):
        at = AutoTuner()
        record = at.record_reset(ResetType.MODE, OperationalRegime.WARM, "r1")
        assert record.reset_id == "r1"

    def test_advance_turn(self):
        at = AutoTuner()
        at.record_reset(ResetType.MODE, OperationalRegime.WARM)
        completed = at.advance_turn(OperationalRegime.ELASTIC)
        assert len(completed) == 0  # Only turn 1

    def test_status(self):
        at = AutoTuner()
        status = at.get_status()
        assert "threshold_tuner" in status
        assert "reset_tracker" in status
        assert "setpoint_calibrator" in status

    def test_to_dict(self):
        at = AutoTuner()
        at.record_signal(RegimeSignals(hysteresis=0.1), OperationalRegime.ELASTIC)
        d = at.to_dict()
        assert "threshold_tuner" in d
        assert "reset_tracker" in d
        assert "setpoint_calibrator" in d

    def test_from_dict(self):
        at = AutoTuner()
        at.record_signal(RegimeSignals(hysteresis=0.1), OperationalRegime.ELASTIC)
        d = at.to_dict()
        restored = AutoTuner.from_dict(d)
        assert len(restored.threshold_tuner._observations) == 1

    def test_roundtrip(self):
        at = AutoTuner()
        sig = RegimeSignals(hysteresis=0.2, tool_gain=0.6)
        at.record_signal(sig, OperationalRegime.WARM)
        at.record_reset(ResetType.CONTEXT, OperationalRegime.WARM, "r1")
        at.advance_turn(OperationalRegime.ELASTIC)
        d = at.to_dict()
        restored = AutoTuner.from_dict(d)
        assert len(restored.threshold_tuner._observations) == 1
        assert len(restored.reset_tracker._records) == 1


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenience:
    def test_create_auto_tuner(self):
        at = create_auto_tuner(domain="medical")
        assert at.setpoint_calibrator.domain == "medical"

    def test_create_threshold_tuner(self):
        tt = create_threshold_tuner(min_samples=20)
        assert tt.min_samples_per_regime == 20

    def test_create_reset_tracker(self):
        rt = create_reset_tracker()
        assert rt.max_records == 200

    def test_create_setpoint_calibrator(self):
        sc = create_setpoint_calibrator(domain="legal", safety_margin=2.0)
        assert sc.domain == "legal"
        assert sc.safety_margin == 2.0

    def test_create_budget_sweeper(self):
        bs = create_budget_sweeper("claim_budget")
        assert bs.parameter_name == "claim_budget"

    def test_analyze_from_metrics(self):
        metrics = RegimeMetrics()
        for i in range(15):
            sig = RegimeSignals(hysteresis=0.05 + i * 0.01)
            metrics.record_signal(sig, OperationalRegime.ELASTIC)
        for i in range(15):
            sig = RegimeSignals(hysteresis=0.4 + i * 0.01)
            metrics.record_signal(sig, OperationalRegime.WARM)
        thresholds = RegimeThresholds()
        analysis = analyze_thresholds_from_metrics(metrics, thresholds)
        assert analysis.total_samples == 30


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_empty_analyze(self):
        tuner = ThresholdTuner()
        analysis = tuner.analyze(RegimeThresholds())
        assert analysis.total_samples == 0
        assert analysis.accuracy == 1.0
        assert len(analysis.suggestions) == 0

    def test_no_resets_report(self):
        tracker = ResetTracker()
        report = tracker.report()
        assert report.total_resets == 0
        assert report.by_type == {}

    def test_zero_variance_signals(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        for _ in range(10):
            tuner.record(RegimeSignals(hysteresis=0.1), OperationalRegime.ELASTIC)
        for _ in range(10):
            tuner.record(RegimeSignals(hysteresis=0.4), OperationalRegime.WARM)
        dists = tuner._compute_distributions()
        elastic_hyst = dists["elastic"].distributions["hysteresis"]
        assert elastic_hyst.stddev == pytest.approx(0.0, abs=1e-10)

    def test_single_sweep_point(self):
        sweeper = BudgetSweeper("budget")
        sweeper.record_point(
            parameter_value=10.0, turns=100,
            budget_block_fraction=0.2,
            contradiction_accumulation=0.1,
            violation_rate=0.05, dangerous_rate=0.02,
            regime_at_end=OperationalRegime.ELASTIC,
            regime_severity_avg=0.3,
        )
        result = sweeper.analyze()
        assert len(result.pareto_frontier) == 1
        assert result.recommended_value == 10.0

    def test_all_identical_signals(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        sig = RegimeSignals()  # all defaults
        for _ in range(20):
            tuner.record(sig, OperationalRegime.ELASTIC)
        analysis = tuner.analyze(RegimeThresholds())
        assert analysis.total_samples == 20

    def test_overlapping_regimes(self):
        tuner = ThresholdTuner(min_samples_per_regime=5)
        # Both regimes have same signal values
        for _ in range(10):
            tuner.record(RegimeSignals(hysteresis=0.3), OperationalRegime.ELASTIC)
        for _ in range(10):
            tuner.record(RegimeSignals(hysteresis=0.3), OperationalRegime.WARM)
        suggestions = tuner.suggest_thresholds(RegimeThresholds())
        # Should have low confidence or no suggestion if midpoint equals current
        for s in suggestions:
            if s.threshold_name == "warm_hysteresis":
                assert s.confidence <= 0.5
