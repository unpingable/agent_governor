"""
Tests for regime detection: health monitoring for the governor system.
"""

import pytest
from datetime import datetime, timezone, timedelta

from governor.regime import (
    # Regimes
    OperationalRegime,
    # Signals and thresholds
    RegimeSignals,
    RegimeThresholds,
    RegimeTransition,
    # Metrics
    RegimeMetrics,
    # Detector
    RegimeDetector,
    # Signal collector
    SignalCollector,
)


# =============================================================================
# OperationalRegime Tests
# =============================================================================


class TestOperationalRegime:
    """Tests for the OperationalRegime enum."""

    def test_regime_values(self):
        """All regimes should have string values."""
        assert OperationalRegime.ELASTIC.value == "elastic"
        assert OperationalRegime.WARM.value == "warm"
        assert OperationalRegime.DUCTILE.value == "ductile"
        assert OperationalRegime.UNSTABLE.value == "unstable"

    def test_severity_ordering(self):
        """Severity should increase: ELASTIC < WARM < DUCTILE < UNSTABLE."""
        assert OperationalRegime.ELASTIC.severity < OperationalRegime.WARM.severity
        assert OperationalRegime.WARM.severity < OperationalRegime.DUCTILE.severity
        assert OperationalRegime.DUCTILE.severity < OperationalRegime.UNSTABLE.severity

    def test_recommended_actions(self):
        """Each regime should have a recommended action."""
        assert OperationalRegime.ELASTIC.recommended_action == "CONTINUE"
        assert OperationalRegime.WARM.recommended_action == "TIGHTEN"
        assert OperationalRegime.DUCTILE.recommended_action == "RESET"
        assert OperationalRegime.UNSTABLE.recommended_action == "EMERGENCY_STOP"


# =============================================================================
# RegimeSignals Tests
# =============================================================================


class TestRegimeSignals:
    """Tests for regime signals."""

    def test_default_values(self):
        """Default signals should indicate healthy state."""
        signals = RegimeSignals()

        assert signals.hysteresis == 0.0
        assert signals.tool_gain == 0.5
        assert signals.budget_pressure == 0.0

    def test_contradictions_accumulating(self):
        """Detect when contradictions are accumulating."""
        # Not accumulating: close rate >= open rate
        signals1 = RegimeSignals(
            contradiction_open_rate=0.1,
            contradiction_close_rate=0.1,
        )
        assert signals1.contradictions_accumulating is False

        # Accumulating: open rate > close rate * 1.2
        signals2 = RegimeSignals(
            contradiction_open_rate=0.5,
            contradiction_close_rate=0.2,
        )
        assert signals2.contradictions_accumulating is True

    def test_serialization(self):
        """Signals should serialize/deserialize."""
        signals = RegimeSignals(
            hysteresis=0.3,
            tool_gain=0.8,
            budget_pressure=0.5,
        )

        data = signals.to_dict()
        restored = RegimeSignals.from_dict(data)

        assert restored.hysteresis == signals.hysteresis
        assert restored.tool_gain == signals.tool_gain
        assert restored.budget_pressure == signals.budget_pressure


# =============================================================================
# RegimeThresholds Tests
# =============================================================================


class TestRegimeThresholds:
    """Tests for regime thresholds."""

    def test_default_thresholds(self):
        """Default thresholds should be sensible."""
        t = RegimeThresholds()

        # WARM thresholds should be lower than DUCTILE
        assert t.warm_hysteresis < t.ductile_hysteresis
        assert t.warm_relaxation < t.ductile_relaxation

        # UNSTABLE tool gain threshold is 1.0 (amplification)
        assert t.unstable_tool_gain == 1.0

    def test_serialization(self):
        """Thresholds should serialize/deserialize."""
        t = RegimeThresholds(warm_hysteresis=0.25)

        data = t.to_dict()
        restored = RegimeThresholds.from_dict(data)

        assert restored.warm_hysteresis == 0.25


# =============================================================================
# RegimeDetector Tests
# =============================================================================


class TestRegimeDetector:
    """Tests for the regime detector."""

    def test_default_regime_is_elastic(self):
        """Detector should start in ELASTIC regime."""
        detector = RegimeDetector()
        assert detector.current_regime == OperationalRegime.ELASTIC

    def test_classify_elastic(self):
        """Normal signals should classify as ELASTIC."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            hysteresis=0.1,
            relaxation_time=1.0,
            tool_gain=0.3,
            budget_pressure=0.1,
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.ELASTIC
        assert "nominal" in reasons[0]

    def test_classify_warm_single_indicator(self):
        """Single warm indicator should trigger WARM."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            hysteresis=0.3,  # Above warm threshold
            relaxation_time=1.0,
            tool_gain=0.3,
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.WARM
        assert any("hysteresis" in r for r in reasons)

    def test_classify_warm_contradictions(self):
        """Accumulating contradictions should trigger WARM."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            contradiction_open_rate=0.5,
            contradiction_close_rate=0.2,
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.WARM
        assert any("contradictions" in r for r in reasons)

    def test_classify_warm_dangerous_claims(self):
        """High dangerous claim rate should trigger WARM."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            dangerous_claim_rate=0.15,  # Above warm threshold
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.WARM
        assert any("dangerous" in r for r in reasons)

    def test_classify_ductile_multiple_indicators(self):
        """Multiple ductile indicators should trigger DUCTILE."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            hysteresis=0.6,  # Above ductile threshold
            relaxation_time=12.0,  # Above ductile threshold
            budget_pressure=0.75,  # Above ductile threshold
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.DUCTILE
        assert len(reasons) >= 2

    def test_classify_unstable_tool_gain(self):
        """Tool gain >= 1 should trigger UNSTABLE."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            tool_gain=1.2,  # Amplification
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.UNSTABLE
        assert any("tool_gain" in r for r in reasons)

    def test_classify_unstable_budget_pressure(self):
        """Extreme budget pressure should trigger UNSTABLE."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            budget_pressure=0.95,  # Near total saturation
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.UNSTABLE
        assert any("budget" in r for r in reasons)

    def test_classify_unstable_dangerous_claims(self):
        """Very high dangerous claim rate should trigger UNSTABLE."""
        detector = RegimeDetector()

        signals = RegimeSignals(
            dangerous_claim_rate=0.35,  # Above unstable threshold
        )

        regime, reasons = detector.classify(signals)

        assert regime == OperationalRegime.UNSTABLE
        assert any("dangerous" in r for r in reasons)

    def test_unstable_takes_priority(self):
        """UNSTABLE should take priority over other regimes."""
        detector = RegimeDetector()

        # Mix of WARM and UNSTABLE indicators
        signals = RegimeSignals(
            hysteresis=0.3,  # WARM
            tool_gain=1.5,  # UNSTABLE
        )

        regime, _ = detector.classify(signals)

        assert regime == OperationalRegime.UNSTABLE

    def test_update_triggers_transition(self):
        """Update should return transition when regime changes."""
        detector = RegimeDetector()

        # Start elastic
        signals1 = RegimeSignals(tool_gain=0.3)
        transition1 = detector.update(signals1)
        assert transition1 is None

        # Transition to unstable
        signals2 = RegimeSignals(tool_gain=1.5)
        transition2 = detector.update(signals2)

        assert transition2 is not None
        assert transition2.from_regime == OperationalRegime.ELASTIC
        assert transition2.to_regime == OperationalRegime.UNSTABLE
        assert detector.current_regime == OperationalRegime.UNSTABLE

    def test_no_transition_same_regime(self):
        """No transition when staying in same regime."""
        detector = RegimeDetector()

        signals = RegimeSignals(tool_gain=0.3)
        transition1 = detector.update(signals)
        transition2 = detector.update(signals)

        assert transition1 is None
        assert transition2 is None

    def test_transition_history(self):
        """Detector should track transition history."""
        detector = RegimeDetector()

        # Elastic -> Warm -> Ductile
        detector.update(RegimeSignals(hysteresis=0.3))
        detector.update(RegimeSignals(hysteresis=0.6, budget_pressure=0.75))

        assert len(detector.transition_history) == 2
        assert detector.transition_history[0].to_regime == OperationalRegime.WARM
        assert detector.transition_history[1].to_regime == OperationalRegime.DUCTILE

    def test_get_state(self):
        """Get current detector state."""
        detector = RegimeDetector()
        detector.update(RegimeSignals(tool_gain=0.3))

        state = detector.get_state()

        assert state["current_regime"] == "elastic"
        assert state["recommended_action"] == "CONTINUE"
        assert state["last_signals"] is not None

    def test_get_history(self):
        """Get transition history as dicts."""
        detector = RegimeDetector()
        detector.update(RegimeSignals(hysteresis=0.3))

        history = detector.get_history()

        assert len(history) == 1
        assert history[0]["to_regime"] == "warm"

    def test_serialization(self):
        """Detector should serialize to JSON."""
        detector = RegimeDetector()
        detector.update(RegimeSignals(hysteresis=0.3))

        json_str = detector.to_json()

        assert "warm" in json_str
        assert "thresholds" in json_str


# =============================================================================
# RegimeMetrics Tests
# =============================================================================


class TestRegimeMetrics:
    """Tests for regime metrics collection."""

    def test_record_signal(self):
        """Record signals for analysis."""
        metrics = RegimeMetrics()

        signals = RegimeSignals(hysteresis=0.3)
        metrics.record_signal(signals, OperationalRegime.WARM)

        assert len(metrics.signal_history) == 1
        assert metrics.signal_history[0][2] == OperationalRegime.WARM

    def test_signal_history_limit(self):
        """Signal history should be limited."""
        metrics = RegimeMetrics()
        metrics.max_signal_history = 5

        for i in range(10):
            metrics.record_signal(RegimeSignals(), OperationalRegime.ELASTIC)

        assert len(metrics.signal_history) == 5

    def test_record_transition(self):
        """Record transitions and dwell times."""
        metrics = RegimeMetrics()

        # Enter WARM
        metrics.regime_entry_time[OperationalRegime.ELASTIC] = datetime.now(
            timezone.utc
        ) - timedelta(seconds=10)

        metrics.record_transition(OperationalRegime.ELASTIC, OperationalRegime.WARM)

        assert metrics.transition_counts["elastic->warm"] == 1
        assert len(metrics.regime_dwell_times[OperationalRegime.ELASTIC]) == 1
        assert metrics.regime_dwell_times[OperationalRegime.ELASTIC][0] >= 10

    def test_turn_counter(self):
        """Turn counter should advance."""
        metrics = RegimeMetrics()

        metrics.advance_turn()
        metrics.advance_turn()

        assert metrics.turn_counter == 2

    def test_threshold_analysis(self):
        """Analyze signal distributions by regime."""
        metrics = RegimeMetrics()

        # Record some signals in different regimes
        metrics.record_signal(RegimeSignals(hysteresis=0.1), OperationalRegime.ELASTIC)
        metrics.record_signal(RegimeSignals(hysteresis=0.15), OperationalRegime.ELASTIC)
        metrics.record_signal(RegimeSignals(hysteresis=0.4), OperationalRegime.WARM)

        analysis = metrics.get_threshold_analysis()

        assert "elastic" in analysis
        assert analysis["elastic"]["count"] == 2
        assert analysis["elastic"]["hysteresis"]["mean"] == 0.125

    def test_summary(self):
        """Get metrics summary."""
        metrics = RegimeMetrics()
        metrics.advance_turn()
        metrics.record_signal(RegimeSignals(), OperationalRegime.ELASTIC)

        summary = metrics.get_summary()

        assert summary["total_turns"] == 1
        assert summary["total_observations"] == 1


# =============================================================================
# SignalCollector Tests
# =============================================================================


class TestSignalCollector:
    """Tests for the signal collector helper."""

    def test_record_proposal(self):
        """Record proposal outcomes."""
        collector = SignalCollector()

        collector.record_proposal(accepted=True)
        collector.record_proposal(accepted=False)

        assert len(collector.proposals) == 2

    def test_compute_rejection_rate(self):
        """Compute rejection rate from proposals."""
        collector = SignalCollector(window_size=10)

        # 3 accepted, 2 rejected = 40% rejection rate
        for _ in range(3):
            collector.record_proposal(accepted=True)
        for _ in range(2):
            collector.record_proposal(accepted=False)

        signals = collector.compute_signals()

        assert signals.rejection_rate == 0.4

    def test_compute_contradiction_rates(self):
        """Compute contradiction rates."""
        collector = SignalCollector(window_size=10)

        collector.record_contradiction_opened()
        collector.record_contradiction_opened()
        collector.record_contradiction_closed()

        signals = collector.compute_signals()

        # Should have some open rate
        assert signals.contradiction_open_rate > 0

    def test_compute_dangerous_rate(self):
        """Compute dangerous claim rate."""
        collector = SignalCollector()

        collector.record_claim()
        collector.record_claim()
        collector.record_dangerous_claim()

        signals = collector.compute_signals()

        # 1 dangerous out of ~2-3 claims
        assert signals.dangerous_claim_rate > 0

    def test_external_signals_passed_through(self):
        """External signals should be passed through."""
        collector = SignalCollector()

        signals = collector.compute_signals(
            provenance_deficit=0.5,
            budget_pressure=0.3,
            tool_gain=0.8,
        )

        assert signals.provenance_deficit == 0.5
        assert signals.budget_pressure == 0.3
        assert signals.tool_gain == 0.8

    def test_update_baseline(self):
        """Update baseline for hysteresis tracking."""
        collector = SignalCollector()

        for _ in range(5):
            collector.record_proposal(accepted=True)
        for _ in range(5):
            collector.record_proposal(accepted=False)

        collector.update_baseline()

        assert collector.baseline_rejection_rate == 0.5
        assert collector.returned_to_baseline is True

    def test_record_perturbation(self):
        """Record perturbation for relaxation tracking."""
        collector = SignalCollector()
        collector.update_baseline()

        collector.record_perturbation()

        assert collector.perturbation_time is not None
        assert collector.returned_to_baseline is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestRegimeIntegration:
    """Integration tests for regime detection."""

    def test_healthy_system_stays_elastic(self):
        """A healthy system should stay ELASTIC."""
        detector = RegimeDetector()
        collector = SignalCollector()

        # Simulate healthy operation
        for _ in range(10):
            collector.record_proposal(accepted=True)
            collector.record_claim()

        signals = collector.compute_signals()
        transition = detector.update(signals)

        assert transition is None
        assert detector.current_regime == OperationalRegime.ELASTIC

    def test_degrading_system_transitions(self):
        """A degrading system should transition through regimes."""
        detector = RegimeDetector()

        # Start healthy
        assert detector.current_regime == OperationalRegime.ELASTIC

        # Some stress -> WARM
        detector.update(RegimeSignals(rejection_rate=0.35))
        assert detector.current_regime == OperationalRegime.WARM

        # More stress -> DUCTILE
        detector.update(
            RegimeSignals(
                hysteresis=0.6,
                rejection_rate=0.55,
                budget_pressure=0.75,
            )
        )
        assert detector.current_regime == OperationalRegime.DUCTILE

        # Critical -> UNSTABLE
        detector.update(RegimeSignals(tool_gain=1.2))
        assert detector.current_regime == OperationalRegime.UNSTABLE

    def test_recovery_from_warm(self):
        """System should recover from WARM when signals improve."""
        detector = RegimeDetector()

        # Enter WARM
        detector.update(RegimeSignals(rejection_rate=0.35))
        assert detector.current_regime == OperationalRegime.WARM

        # Recover to ELASTIC
        detector.update(RegimeSignals(rejection_rate=0.1))
        assert detector.current_regime == OperationalRegime.ELASTIC

    def test_metrics_track_transitions(self):
        """Metrics should track regime transitions."""
        detector = RegimeDetector(collect_metrics=True)

        # Multiple transitions
        detector.update(RegimeSignals(rejection_rate=0.35))  # -> WARM
        detector.update(RegimeSignals(rejection_rate=0.1))  # -> ELASTIC
        detector.update(RegimeSignals(tool_gain=1.2))  # -> UNSTABLE

        metrics = detector.metrics.get_summary()

        assert metrics["total_observations"] == 3
        assert "elastic->warm" in detector.metrics.transition_counts
        assert "warm->elastic" in detector.metrics.transition_counts
        assert "elastic->unstable" in detector.metrics.transition_counts

    def test_dangerous_claims_affect_regime(self):
        """Dangerous claim accumulation should affect regime."""
        detector = RegimeDetector()
        collector = SignalCollector()

        # Record some dangerous claims
        for _ in range(10):
            collector.record_claim()
        for _ in range(2):
            collector.record_dangerous_claim()

        signals = collector.compute_signals()
        detector.update(signals)

        # Should be at least WARM due to dangerous claims
        assert detector.current_regime.severity >= OperationalRegime.WARM.severity
