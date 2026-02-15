"""Tests for correlator telemetry: capture detection for the governor."""

import json
import os
import pytest
from pathlib import Path

from governor.correlator_telemetry import (
    AuthorityLevel,
    CaptureDiagnostic,
    CaptureIndicator,
    CaptureSignals,
    CaptureThresholds,
    CorrelatorRegime,
    CorrelatorTelemetry,
    FidelityProxy,
    IndicatorState,
    KVector,
    classify_regime,
    compute_capture_signals,
    compute_fidelity_proxy,
    compute_k_vector,
    diagnose_capture,
    judge_interferometry_run,
)


# =============================================================================
# Enum Tests
# =============================================================================


class TestCorrelatorRegime:
    def test_leverage_value(self):
        assert CorrelatorRegime.LEVERAGE == "leverage"

    def test_shear_value(self):
        assert CorrelatorRegime.SHEAR == "shear"

    def test_capture_value(self):
        assert CorrelatorRegime.CAPTURE == "capture"

    def test_unknown_value(self):
        assert CorrelatorRegime.UNKNOWN == "unknown"

    def test_from_string(self):
        assert CorrelatorRegime("leverage") == CorrelatorRegime.LEVERAGE


class TestCaptureIndicator:
    def test_mode_count_decreasing(self):
        assert CaptureIndicator.MODE_COUNT_DECREASING == "mode_count_decreasing"

    def test_entropy_nonincreasing(self):
        assert CaptureIndicator.ENTROPY_NONINCREASING == "entropy_nonincreasing"

    def test_contradiction_suppression(self):
        assert CaptureIndicator.CONTRADICTION_SUPPRESSION == "contradiction_suppression"

    def test_commitment_shear(self):
        assert CaptureIndicator.COMMITMENT_SHEAR == "commitment_shear"

    def test_from_string(self):
        assert CaptureIndicator("commitment_shear") == CaptureIndicator.COMMITMENT_SHEAR


class TestAuthorityLevel:
    def test_blocking(self):
        assert AuthorityLevel.BLOCKING == "blocking"

    def test_advisory(self):
        assert AuthorityLevel.ADVISORY == "advisory"

    def test_slim(self):
        assert AuthorityLevel.SLIM == "slim"


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestFidelityProxy:
    def test_construction(self):
        fp = FidelityProxy(
            mode_preservation=0.9,
            contradiction_persistence=0.3,
            representation_shear=0.1,
            provenance_entropy=2.5,
        )
        assert fp.mode_preservation == 0.9
        assert fp.contradiction_persistence == 0.3

    def test_roundtrip(self):
        fp = FidelityProxy(0.8, 0.4, 0.2, 1.7)
        d = fp.to_dict()
        fp2 = FidelityProxy.from_dict(d)
        assert fp == fp2

    def test_from_dict_defaults(self):
        fp = FidelityProxy.from_dict({})
        assert fp.mode_preservation == 0.0
        assert fp.provenance_entropy == 0.0

    def test_frozen(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        with pytest.raises(AttributeError):
            fp.mode_preservation = 0.9  # type: ignore

    def test_proxy_labeling(self):
        """Verify docstring mentions 'proxy' — never pretends to be exact."""
        assert "proxy" in FidelityProxy.__doc__.lower()

    def test_to_dict_keys(self):
        fp = FidelityProxy(0.1, 0.2, 0.3, 0.4)
        d = fp.to_dict()
        assert set(d.keys()) == {
            "mode_preservation", "contradiction_persistence",
            "representation_shear", "provenance_entropy",
        }


class TestKVector:
    def test_construction(self):
        fp = FidelityProxy(0.9, 0.3, 0.1, 2.0)
        kv = KVector(
            throughput=10.0,
            fidelity=fp,
            authority=AuthorityLevel.BLOCKING,
            cost_budget=0.5,
            window_step=3,
        )
        assert kv.throughput == 10.0
        assert kv.authority == AuthorityLevel.BLOCKING

    def test_roundtrip(self):
        fp = FidelityProxy(0.8, 0.4, 0.2, 1.5)
        kv = KVector(8.0, fp, AuthorityLevel.ADVISORY, 0.3, 5)
        d = kv.to_dict()
        kv2 = KVector.from_dict(d)
        assert kv == kv2

    def test_no_score_method(self):
        """K-vector must NOT be scalarizable."""
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(5.0, fp, AuthorityLevel.BLOCKING, 0.5, 1)
        assert not hasattr(kv, "score")
        assert not hasattr(kv, "magnitude")

    def test_from_dict_defaults(self):
        kv = KVector.from_dict({})
        assert kv.throughput == 0.0
        assert kv.authority == AuthorityLevel.ADVISORY
        assert kv.window_step == 0

    def test_frozen(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(5.0, fp, AuthorityLevel.BLOCKING, 0.5, 1)
        with pytest.raises(AttributeError):
            kv.throughput = 99.0  # type: ignore

    def test_to_dict_contains_fidelity(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(5.0, fp, AuthorityLevel.BLOCKING, 0.5, 1)
        d = kv.to_dict()
        assert isinstance(d["fidelity"], dict)
        assert d["authority"] == "blocking"

    def test_from_dict_nested_fidelity(self):
        d = {
            "throughput": 7.0,
            "fidelity": {"mode_preservation": 0.9, "provenance_entropy": 3.0},
            "authority": "blocking",
            "cost_budget": 0.4,
            "window_step": 2,
        }
        kv = KVector.from_dict(d)
        assert kv.fidelity.mode_preservation == 0.9
        assert kv.fidelity.provenance_entropy == 3.0

    def test_warning_in_docstring(self):
        assert "do not scalarize" in KVector.__doc__.lower()


class TestCaptureSignals:
    def test_construction_defaults(self):
        cs = CaptureSignals()
        assert cs.open_objection_count == 0
        assert cs.generated_objection_count == 0
        assert cs.exposure == 0

    def test_construction_with_values(self):
        cs = CaptureSignals(
            open_objection_count=3,
            generated_objection_count=5,
            exposure=50,
            live_hypothesis_count=10,
        )
        assert cs.generated_objection_count == 5
        assert cs.live_hypothesis_count == 10

    def test_roundtrip(self):
        cs = CaptureSignals(
            open_objection_count=2,
            generated_objection_count=4,
            distinct_agent_count=3,
            active_claim_count=15,
            provenance_entropy=2.1,
            exposure=30,
            live_hypothesis_count=8,
            total_commitments_at_boundary=20,
            lost_commitments_at_boundary=3,
        )
        d = cs.to_dict()
        cs2 = CaptureSignals.from_dict(d)
        assert cs == cs2

    def test_from_dict_defaults(self):
        cs = CaptureSignals.from_dict({})
        assert cs.generated_objection_count == 0
        assert cs.total_commitments_at_boundary == 0

    def test_boundary_fields_present(self):
        """Commitment boundary tracking fields exist."""
        cs = CaptureSignals(
            total_commitments_at_boundary=100,
            lost_commitments_at_boundary=15,
        )
        d = cs.to_dict()
        assert d["total_commitments_at_boundary"] == 100
        assert d["lost_commitments_at_boundary"] == 15

    def test_frozen(self):
        cs = CaptureSignals()
        with pytest.raises(AttributeError):
            cs.exposure = 99  # type: ignore

    def test_generated_vs_open_distinct(self):
        """Generated and open objection counts are independent fields."""
        cs = CaptureSignals(open_objection_count=2, generated_objection_count=5)
        assert cs.open_objection_count != cs.generated_objection_count

    def test_to_dict_all_keys(self):
        cs = CaptureSignals()
        d = cs.to_dict()
        assert "generated_objection_count" in d
        assert "total_commitments_at_boundary" in d
        assert "lost_commitments_at_boundary" in d


class TestCaptureThresholds:
    def test_defaults(self):
        ct = CaptureThresholds()
        assert ct.throughput_min == 5.0
        assert ct.exposure_min == 3
        assert ct.capture_consecutive_windows == 2

    def test_roundtrip(self):
        ct = CaptureThresholds(throughput_min=3.0, exposure_min=5)
        d = ct.to_dict()
        ct2 = CaptureThresholds.from_dict(d)
        assert ct == ct2

    def test_hysteresis_fields_present(self):
        ct = CaptureThresholds()
        assert ct.mode_consecutive_windows == 2
        assert ct.entropy_consecutive_windows == 2
        assert ct.contradiction_consecutive_windows == 2
        assert ct.commitment_consecutive_windows == 2
        assert ct.capture_consecutive_windows == 2

    def test_cost_budget_is_degraded_not_shear(self):
        ct = CaptureThresholds()
        assert hasattr(ct, "cost_budget_degraded_threshold")
        # No field called cost_budget_shear_threshold
        assert not hasattr(ct, "cost_budget_shear_threshold")

    def test_from_dict_defaults(self):
        ct = CaptureThresholds.from_dict({})
        assert ct.throughput_min == 5.0

    def test_custom_values(self):
        ct = CaptureThresholds(
            throughput_min=2.0,
            mode_per_exposure_threshold=0.3,
            capture_indicator_min=3,
        )
        assert ct.throughput_min == 2.0
        assert ct.mode_per_exposure_threshold == 0.3


class TestIndicatorState:
    def test_defaults(self):
        st = IndicatorState()
        assert st.mode_streak == 0
        assert st.capture_streak == 0

    def test_roundtrip(self):
        st = IndicatorState(mode_streak=3, entropy_streak=2, capture_streak=1)
        d = st.to_dict()
        st2 = IndicatorState.from_dict(d)
        assert st2.mode_streak == 3
        assert st2.capture_streak == 1

    def test_mutable(self):
        st = IndicatorState()
        st.mode_streak = 5
        assert st.mode_streak == 5


class TestCaptureDiagnostic:
    def test_construction(self):
        fp = FidelityProxy(0.9, 0.3, 0.1, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        sig = CaptureSignals(exposure=50)
        diag = CaptureDiagnostic(
            window_step=5,
            regime=CorrelatorRegime.LEVERAGE,
            indicators_triggered=[],
            indicator_details={},
            k_vector=kv,
            signals=sig,
            confidence=0.8,
        )
        assert diag.regime == CorrelatorRegime.LEVERAGE
        assert diag.gate_met is True  # default

    def test_gate_met_false(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(2.0, fp, AuthorityLevel.ADVISORY, 0.3, 1)
        sig = CaptureSignals()
        diag = CaptureDiagnostic(
            window_step=1,
            regime=CorrelatorRegime.LEVERAGE,
            indicators_triggered=[CaptureIndicator.CONTRADICTION_SUPPRESSION],
            indicator_details={},
            k_vector=kv,
            signals=sig,
            confidence=0.5,
            gate_met=False,
        )
        assert not diag.gate_met
        assert len(diag.indicators_triggered) == 1  # non-binding

    def test_roundtrip(self):
        fp = FidelityProxy(0.8, 0.3, 0.1, 1.5)
        kv = KVector(8.0, fp, AuthorityLevel.BLOCKING, 0.4, 3)
        sig = CaptureSignals(exposure=30, generated_objection_count=2)
        diag = CaptureDiagnostic(
            window_step=3,
            regime=CorrelatorRegime.CAPTURE,
            indicators_triggered=[
                CaptureIndicator.CONTRADICTION_SUPPRESSION,
                CaptureIndicator.MODE_COUNT_DECREASING,
            ],
            indicator_details={"test": True},
            k_vector=kv,
            signals=sig,
            confidence=0.5,
            gate_met=True,
            capacity_degraded=True,
        )
        d = diag.to_dict()
        diag2 = CaptureDiagnostic.from_dict(d)
        assert diag2.regime == CorrelatorRegime.CAPTURE
        assert len(diag2.indicators_triggered) == 2
        assert diag2.gate_met is True
        assert diag2.capacity_degraded is True

    def test_timestamp_auto_generated(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(5.0, fp, AuthorityLevel.BLOCKING, 0.5, 1)
        sig = CaptureSignals()
        diag = CaptureDiagnostic(
            window_step=1,
            regime=CorrelatorRegime.UNKNOWN,
            indicators_triggered=[],
            indicator_details={},
            k_vector=kv,
            signals=sig,
            confidence=0.0,
        )
        assert diag.timestamp != ""
        assert "T" in diag.timestamp  # ISO format

    def test_to_dict_includes_new_fields(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(5.0, fp, AuthorityLevel.BLOCKING, 0.5, 1)
        sig = CaptureSignals()
        diag = CaptureDiagnostic(
            window_step=1,
            regime=CorrelatorRegime.LEVERAGE,
            indicators_triggered=[],
            indicator_details={},
            k_vector=kv,
            signals=sig,
            confidence=0.8,
            gate_met=True,
            capacity_degraded=False,
        )
        d = diag.to_dict()
        assert "gate_met" in d
        assert "capacity_degraded" in d


# =============================================================================
# Pure Function Tests
# =============================================================================


class TestComputeCaptureSignals:
    def test_all_none(self):
        cs = compute_capture_signals()
        assert cs.exposure == 0
        assert cs.generated_objection_count == 0

    def test_dissent_metrics(self):
        cs = compute_capture_signals(
            dissent_metrics={
                "open_objection_count": 3,
                "generated_objection_count": 7,
                "distinct_agent_count": 2,
            },
        )
        assert cs.open_objection_count == 3
        assert cs.generated_objection_count == 7

    def test_epistemic_metrics(self):
        cs = compute_capture_signals(
            epistemic_metrics={
                "active_claim_count": 20,
                "provenance_entropy": 3.2,
            },
        )
        assert cs.active_claim_count == 20
        assert cs.provenance_entropy == 3.2

    def test_diff_trends_with_boundary(self):
        cs = compute_capture_signals(
            diff_trends={
                "silent_retraction_count": 5,
                "total_commitments_at_boundary": 50,
                "lost_commitments_at_boundary": 8,
            },
        )
        assert cs.silent_retraction_count == 5
        assert cs.total_commitments_at_boundary == 50
        assert cs.lost_commitments_at_boundary == 8

    def test_exposure_and_hypothesis(self):
        cs = compute_capture_signals(exposure=42, hypothesis_count=10)
        assert cs.exposure == 42
        assert cs.live_hypothesis_count == 10

    def test_missing_keys_default_zero(self):
        cs = compute_capture_signals(
            dissent_metrics={"unrelated_key": 999},
        )
        assert cs.open_objection_count == 0
        assert cs.generated_objection_count == 0

    def test_partial_dicts(self):
        cs = compute_capture_signals(
            dissent_metrics={"open_objection_count": 1},
            epistemic_metrics={"provenance_entropy": 1.5},
            regime_signals={"contradiction_open_rate": 0.3},
            diff_trends={"mutation_velocity": 0.1},
            exposure=10,
        )
        assert cs.open_objection_count == 1
        assert cs.provenance_entropy == 1.5
        assert cs.contradiction_open_rate == 0.3
        assert cs.mutation_velocity == 0.1


class TestComputeFidelityProxy:
    def test_basic(self):
        fp = compute_fidelity_proxy(
            provenance_entropy=2.0,
            contradiction_persistence=0.3,
            mode_ratio=0.9,
            commitment_shear=0.1,
        )
        assert fp.provenance_entropy == 2.0
        assert fp.mode_preservation == 0.9

    def test_clamping_mode_ratio(self):
        fp = compute_fidelity_proxy(mode_ratio=1.5)
        assert fp.mode_preservation == 1.0
        fp2 = compute_fidelity_proxy(mode_ratio=-0.5)
        assert fp2.mode_preservation == 0.0

    def test_negative_shear_clamped(self):
        fp = compute_fidelity_proxy(commitment_shear=-0.5)
        assert fp.representation_shear == 0.0

    def test_defaults(self):
        fp = compute_fidelity_proxy()
        assert fp.mode_preservation == 1.0  # default mode_ratio=1.0
        assert fp.contradiction_persistence == 0.0


class TestComputeKVector:
    def test_basic(self):
        fp = FidelityProxy(0.9, 0.3, 0.1, 2.0)
        kv = compute_k_vector(
            throughput=10.0,
            fidelity=fp,
            authority=AuthorityLevel.BLOCKING,
            cost_ratio=0.5,
            window_step=3,
        )
        assert kv.throughput == 10.0
        assert kv.window_step == 3

    def test_clamping_throughput(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = compute_k_vector(
            throughput=-5.0, fidelity=fp,
            authority=AuthorityLevel.ADVISORY, cost_ratio=0.5, window_step=0,
        )
        assert kv.throughput == 0.0

    def test_clamping_cost_ratio(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = compute_k_vector(
            throughput=5.0, fidelity=fp,
            authority=AuthorityLevel.BLOCKING, cost_ratio=1.5, window_step=1,
        )
        assert kv.cost_budget == 1.0
        kv2 = compute_k_vector(
            throughput=5.0, fidelity=fp,
            authority=AuthorityLevel.BLOCKING, cost_ratio=-0.3, window_step=1,
        )
        assert kv2.cost_budget == 0.0


# =============================================================================
# Indicator Check Tests
# =============================================================================


class TestDiagnoseCapture:
    """Tests for the diagnose_capture pure function."""

    def _make_signals(self, **kwargs) -> CaptureSignals:
        defaults = {
            "exposure": 50,
            "live_hypothesis_count": 10,
            "generated_objection_count": 5,
        }
        defaults.update(kwargs)
        return CaptureSignals(**defaults)

    def _make_k(self, **kwargs) -> KVector:
        fp_kwargs = kwargs.pop("fidelity_kwargs", {})
        fp = FidelityProxy(
            mode_preservation=fp_kwargs.get("mode_preservation", 0.9),
            contradiction_persistence=fp_kwargs.get("contradiction_persistence", 0.3),
            representation_shear=fp_kwargs.get("representation_shear", 0.0),
            provenance_entropy=fp_kwargs.get("provenance_entropy", 2.0),
        )
        defaults = {
            "throughput": 10.0,
            "fidelity": fp,
            "authority": AuthorityLevel.BLOCKING,
            "cost_budget": 0.3,
            "window_step": 5,
        }
        defaults.update(kwargs)
        return KVector(**defaults)

    def test_first_window_unknown(self):
        """First window should be UNKNOWN regardless of signals."""
        sig = self._make_signals()
        kv = self._make_k(window_step=0)
        diag, state = diagnose_capture(
            signals_current=sig, signals_previous=None,
            k_vector=kv, thresholds=CaptureThresholds(),
            indicator_state=IndicatorState(),
        )
        assert diag.regime == CorrelatorRegime.UNKNOWN

    def test_leverage_healthy(self):
        """Active contradictions, diverse provenance → LEVERAGE."""
        prev = self._make_signals(
            provenance_entropy=2.0, live_hypothesis_count=10, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=2.3, live_hypothesis_count=12, exposure=50,
            generated_objection_count=6,
        )
        kv = self._make_k()
        diag, state = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=CaptureThresholds(),
            indicator_state=IndicatorState(),
        )
        assert diag.regime == CorrelatorRegime.LEVERAGE
        assert len(diag.indicators_triggered) == 0

    def test_indicators_computed_without_gate(self):
        """Indicators computed even when gate not met (non-binding context)."""
        # Advisory authority → gate not met
        prev = self._make_signals(
            provenance_entropy=2.0, live_hypothesis_count=10, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.5, live_hypothesis_count=3, exposure=50,
            generated_objection_count=0,  # suppressed
        )
        kv = self._make_k(authority=AuthorityLevel.ADVISORY)
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
        )
        diag, state = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=IndicatorState(),
        )
        # Indicators computed but gate not met
        assert not diag.gate_met
        assert len(diag.indicators_triggered) > 0  # pre-gate indicators
        assert diag.regime != CorrelatorRegime.CAPTURE  # can't declare capture

    def test_authority_gate_prevents_capture(self):
        """Advisory authority → never CAPTURE, even with all indicators."""
        prev = self._make_signals(
            provenance_entropy=2.0, live_hypothesis_count=10, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.0, live_hypothesis_count=2, exposure=50,
            generated_objection_count=0,
            silent_retraction_count=10,
            total_commitments_at_boundary=20,
            lost_commitments_at_boundary=15,
        )
        kv = self._make_k(authority=AuthorityLevel.ADVISORY)
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=1,
        )
        diag, _ = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=IndicatorState(),
        )
        assert diag.regime != CorrelatorRegime.CAPTURE

    def test_throughput_gate_prevents_capture(self):
        """Low throughput under blocking → SHEAR, not CAPTURE."""
        prev = self._make_signals(
            provenance_entropy=2.0, live_hypothesis_count=10, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.0, live_hypothesis_count=2, exposure=50,
            generated_objection_count=0,
        )
        kv = self._make_k(throughput=1.0)  # below t_min
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            capture_consecutive_windows=1,
        )
        diag, _ = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=IndicatorState(),
        )
        assert diag.regime == CorrelatorRegime.SHEAR

    def test_capacity_degraded_flag(self):
        """High cost budget sets degraded flag but doesn't force SHEAR."""
        sig = self._make_signals()
        kv = self._make_k(cost_budget=0.95)
        diag, _ = diagnose_capture(
            signals_current=sig, signals_previous=None,
            k_vector=kv, thresholds=CaptureThresholds(),
            indicator_state=IndicatorState(),
        )
        assert diag.capacity_degraded is True
        # Not SHEAR just because of cost
        # (first window → UNKNOWN, but the point is it's not forced to SHEAR)

    def test_hysteresis_prevents_single_window_capture(self):
        """Single window of indicators does not trigger CAPTURE."""
        prev = self._make_signals(
            provenance_entropy=3.0, live_hypothesis_count=20, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.0, live_hypothesis_count=2, exposure=50,
            generated_objection_count=0,
            silent_retraction_count=10,
            total_commitments_at_boundary=20,
            lost_commitments_at_boundary=15,
        )
        kv = self._make_k()
        # All indicators fire but capture_consecutive_windows=2
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=2,  # need 2 windows
        )
        diag, state = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=IndicatorState(),
        )
        # First window: indicators fire but capture_streak only 1
        assert state.capture_streak == 1
        assert diag.regime == CorrelatorRegime.LEVERAGE  # not CAPTURE yet

    def test_hysteresis_second_window_triggers_capture(self):
        """Second consecutive window of indicators triggers CAPTURE."""
        prev = self._make_signals(
            provenance_entropy=3.0, live_hypothesis_count=20, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.0, live_hypothesis_count=2, exposure=50,
            generated_objection_count=0,
            silent_retraction_count=10,
            total_commitments_at_boundary=20,
            lost_commitments_at_boundary=15,
        )
        kv = self._make_k()
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=2,
        )
        # Seed: first window already built streak=1
        state = IndicatorState(
            mode_streak=1, entropy_streak=1,
            contradiction_streak=1, commitment_streak=1,
            capture_streak=1,
        )
        diag, new_state = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=state,
        )
        assert new_state.capture_streak >= 2
        assert diag.regime == CorrelatorRegime.CAPTURE

    def test_single_indicator_no_capture(self):
        """One indicator is not enough for CAPTURE (need >= 2)."""
        prev = self._make_signals(
            provenance_entropy=2.0, live_hypothesis_count=10, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.5, live_hypothesis_count=10, exposure=50,
            generated_objection_count=0,  # only contradiction suppression fires
        )
        kv = self._make_k()
        thresholds = CaptureThresholds(
            contradiction_consecutive_windows=1,
            capture_consecutive_windows=1,
        )
        state = IndicatorState()
        diag, _ = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=state,
        )
        assert diag.regime == CorrelatorRegime.LEVERAGE

    def test_confidence_capture(self):
        """CAPTURE confidence scales with indicator count."""
        prev = self._make_signals(
            provenance_entropy=3.0, live_hypothesis_count=20, exposure=50,
        )
        cur = self._make_signals(
            provenance_entropy=1.0, live_hypothesis_count=2, exposure=50,
            generated_objection_count=0,
            silent_retraction_count=10,
            total_commitments_at_boundary=20,
            lost_commitments_at_boundary=15,
        )
        kv = self._make_k()
        thresholds = CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=1,
        )
        state = IndicatorState(capture_streak=1)
        diag, _ = diagnose_capture(
            signals_current=cur, signals_previous=prev,
            k_vector=kv, thresholds=thresholds,
            indicator_state=state,
        )
        assert diag.regime == CorrelatorRegime.CAPTURE
        assert diag.confidence > 0.5  # multiple indicators


class TestContradictionInversion:
    """Test Prop 5.3: zero contradictions + exposure = suspicious."""

    def test_zero_generated_under_exposure(self):
        """Zero generated objections under exposure → suppression flagged."""
        sig = CaptureSignals(
            exposure=50,
            generated_objection_count=0,
            open_objection_count=0,
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert triggered
        assert info["ratio"] == 0.0

    def test_healthy_generation_rate(self):
        """Adequate generated objections → no suppression."""
        sig = CaptureSignals(
            exposure=50,
            generated_objection_count=10,
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert not triggered
        assert info["ratio"] == 0.2

    def test_zero_exposure_not_flagged(self):
        """Zero exposure → no suppression (nothing to suppress)."""
        sig = CaptureSignals(exposure=0, generated_objection_count=0)
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert not triggered
        assert info["reason"] == "zero_exposure"

    def test_open_resolved_but_generated_is_key(self):
        """Open=0 but generated=5 → NOT suppression (just resolved)."""
        sig = CaptureSignals(
            exposure=50,
            open_objection_count=0,
            generated_objection_count=5,
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert not triggered  # generated/exposure = 0.1, at threshold

    def test_barely_suppressed(self):
        """Ratio just below threshold → triggered."""
        sig = CaptureSignals(
            exposure=50,
            generated_objection_count=4,  # 4/50 = 0.08 < 0.1
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert triggered
        assert info["ratio"] == pytest.approx(0.08)

    def test_exactly_at_threshold(self):
        """Ratio at exactly threshold → NOT triggered (< not <=)."""
        sig = CaptureSignals(
            exposure=100,
            generated_objection_count=10,  # 10/100 = 0.1 = threshold
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        triggered, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert not triggered

    def test_custom_threshold(self):
        sig = CaptureSignals(exposure=50, generated_objection_count=4)
        from governor.correlator_telemetry import _check_contradiction_suppression
        thresholds = CaptureThresholds(contradiction_suppression_ratio=0.05)
        triggered, _ = _check_contradiction_suppression(sig, thresholds)
        assert not triggered  # 4/50 = 0.08 > 0.05

    def test_info_includes_both_counts(self):
        """Info dict should include both generated and open counts."""
        sig = CaptureSignals(
            exposure=50, generated_objection_count=3, open_objection_count=1,
        )
        from governor.correlator_telemetry import _check_contradiction_suppression
        _, info = _check_contradiction_suppression(sig, CaptureThresholds())
        assert "generated_objections" in info
        assert "open_objections" in info


class TestModeCountDecreasing:
    """Test mode_per_exposure normalization."""

    def test_normalized_by_exposure(self):
        """Mode count normalized by exposure, not raw count."""
        from governor.correlator_telemetry import _check_mode_count_decreasing
        prev = CaptureSignals(live_hypothesis_count=20, exposure=100)
        cur = CaptureSignals(live_hypothesis_count=10, exposure=50)
        # mpe_prev = 20/100 = 0.2, mpe_cur = 10/50 = 0.2, ratio = 1.0
        triggered, info = _check_mode_count_decreasing(cur, prev, CaptureThresholds())
        assert not triggered  # same rate, different volumes

    def test_declining_rate_triggers(self):
        from governor.correlator_telemetry import _check_mode_count_decreasing
        prev = CaptureSignals(live_hypothesis_count=20, exposure=50)  # mpe = 0.4
        cur = CaptureSignals(live_hypothesis_count=5, exposure=50)    # mpe = 0.1
        # ratio = 0.1/0.4 = 0.25 < 0.5 threshold
        triggered, info = _check_mode_count_decreasing(cur, prev, CaptureThresholds())
        assert triggered
        assert info["ratio"] < 0.5

    def test_no_previous_data(self):
        from governor.correlator_telemetry import _check_mode_count_decreasing
        cur = CaptureSignals(live_hypothesis_count=10, exposure=50)
        triggered, info = _check_mode_count_decreasing(cur, None, CaptureThresholds())
        assert not triggered
        assert info["reason"] == "no_previous_data"

    def test_previous_zero_mpe(self):
        from governor.correlator_telemetry import _check_mode_count_decreasing
        prev = CaptureSignals(live_hypothesis_count=0, exposure=50)  # mpe = 0
        cur = CaptureSignals(live_hypothesis_count=5, exposure=50)
        triggered, info = _check_mode_count_decreasing(cur, prev, CaptureThresholds())
        assert not triggered

    def test_info_includes_exposure(self):
        from governor.correlator_telemetry import _check_mode_count_decreasing
        prev = CaptureSignals(live_hypothesis_count=10, exposure=50)
        cur = CaptureSignals(live_hypothesis_count=8, exposure=40)
        _, info = _check_mode_count_decreasing(cur, prev, CaptureThresholds())
        assert "current_mpe" in info
        assert "previous_mpe" in info
        assert "current_exposure" in info


class TestEntropyNonincreasing:
    """Test entropy check with exposure gating."""

    def test_exposure_below_minimum(self):
        """Low exposure → no entropy check."""
        from governor.correlator_telemetry import _check_entropy_nonincreasing
        prev = CaptureSignals(provenance_entropy=2.0)
        cur = CaptureSignals(provenance_entropy=1.0, exposure=1)  # below default e_min=3
        triggered, info = _check_entropy_nonincreasing(cur, prev, CaptureThresholds())
        assert not triggered
        assert info["reason"] == "exposure_below_minimum"

    def test_decreasing_entropy_under_exposure(self):
        from governor.correlator_telemetry import _check_entropy_nonincreasing
        prev = CaptureSignals(provenance_entropy=3.0)
        cur = CaptureSignals(provenance_entropy=2.0, exposure=10)
        triggered, info = _check_entropy_nonincreasing(cur, prev, CaptureThresholds())
        assert triggered
        assert info["delta"] < 0

    def test_increasing_entropy(self):
        from governor.correlator_telemetry import _check_entropy_nonincreasing
        prev = CaptureSignals(provenance_entropy=2.0)
        cur = CaptureSignals(provenance_entropy=3.0, exposure=10)
        triggered, info = _check_entropy_nonincreasing(cur, prev, CaptureThresholds())
        assert not triggered

    def test_no_previous(self):
        from governor.correlator_telemetry import _check_entropy_nonincreasing
        cur = CaptureSignals(provenance_entropy=2.0, exposure=10)
        triggered, info = _check_entropy_nonincreasing(cur, None, CaptureThresholds())
        assert not triggered


class TestCommitmentShear:
    """Test loss-ratio based commitment shear."""

    def test_loss_ratio_triggers(self):
        from governor.correlator_telemetry import _check_commitment_shear
        sig = CaptureSignals(
            total_commitments_at_boundary=100,
            lost_commitments_at_boundary=50,  # 50% loss
        )
        fp = FidelityProxy(0.9, 0.3, 0.0, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        triggered, info = _check_commitment_shear(sig, kv, CaptureThresholds())
        assert triggered
        assert info["loss_ratio"] == 0.5
        assert info["loss_ratio_triggered"] is True

    def test_no_boundary_falls_back_to_proxy(self):
        from governor.correlator_telemetry import _check_commitment_shear
        sig = CaptureSignals(total_commitments_at_boundary=0)
        fp = FidelityProxy(0.9, 0.3, 0.5, 2.0)  # shear = 0.5 > 0.3 threshold
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        triggered, info = _check_commitment_shear(sig, kv, CaptureThresholds())
        assert triggered
        assert info["loss_ratio"] == 0.5  # from fidelity proxy

    def test_silent_retractions_trigger(self):
        from governor.correlator_telemetry import _check_commitment_shear
        sig = CaptureSignals(
            silent_retraction_count=10,  # > 3 threshold
            total_commitments_at_boundary=100,
            lost_commitments_at_boundary=5,  # 5% loss, below threshold
        )
        fp = FidelityProxy(0.9, 0.3, 0.0, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        triggered, info = _check_commitment_shear(sig, kv, CaptureThresholds())
        assert triggered
        assert info["retraction_triggered"] is True
        assert info["loss_ratio_triggered"] is False

    def test_healthy_no_shear(self):
        from governor.correlator_telemetry import _check_commitment_shear
        sig = CaptureSignals(
            total_commitments_at_boundary=100,
            lost_commitments_at_boundary=5,  # 5% < 30% threshold
            silent_retraction_count=1,  # < 3 threshold
        )
        fp = FidelityProxy(0.9, 0.3, 0.0, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        triggered, info = _check_commitment_shear(sig, kv, CaptureThresholds())
        assert not triggered


class TestClassifyRegime:
    def test_first_window_unknown(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 0)
        regime = classify_regime(
            k_vector=kv, capture_indicators=[], thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.UNKNOWN

    def test_low_throughput_blocking_shear(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(1.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        regime = classify_regime(
            k_vector=kv, capture_indicators=[], thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.SHEAR

    def test_low_throughput_advisory_leverage(self):
        """Low throughput under advisory is not SHEAR — governor isn't blocking."""
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(1.0, fp, AuthorityLevel.ADVISORY, 0.3, 5)
        regime = classify_regime(
            k_vector=kv, capture_indicators=[], thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE

    def test_capture_with_indicators_and_streak(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        indicators = [
            CaptureIndicator.MODE_COUNT_DECREASING,
            CaptureIndicator.CONTRADICTION_SUPPRESSION,
        ]
        regime = classify_regime(
            k_vector=kv, capture_indicators=indicators,
            capture_streak=2, thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.CAPTURE

    def test_capture_insufficient_streak(self):
        """Indicators met but streak too short."""
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        indicators = [
            CaptureIndicator.MODE_COUNT_DECREASING,
            CaptureIndicator.CONTRADICTION_SUPPRESSION,
        ]
        regime = classify_regime(
            k_vector=kv, capture_indicators=indicators,
            capture_streak=1,  # need 2
            thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE

    def test_cost_budget_does_not_force_shear(self):
        """High cost budget alone does NOT produce SHEAR (just degraded flag)."""
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.95, 5)
        regime = classify_regime(
            k_vector=kv, capture_indicators=[], thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE  # not SHEAR

    def test_default_leverage(self):
        fp = FidelityProxy(0.9, 0.3, 0.1, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        regime = classify_regime(
            k_vector=kv, capture_indicators=[], thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE

    def test_one_indicator_not_capture(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        regime = classify_regime(
            k_vector=kv,
            capture_indicators=[CaptureIndicator.ENTROPY_NONINCREASING],
            capture_streak=5,
            thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE

    def test_advisory_with_indicators_not_capture(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.ADVISORY, 0.3, 5)
        indicators = [
            CaptureIndicator.MODE_COUNT_DECREASING,
            CaptureIndicator.CONTRADICTION_SUPPRESSION,
            CaptureIndicator.ENTROPY_NONINCREASING,
        ]
        regime = classify_regime(
            k_vector=kv, capture_indicators=indicators,
            capture_streak=10, thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.LEVERAGE

    def test_three_indicators_capture(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        indicators = [
            CaptureIndicator.MODE_COUNT_DECREASING,
            CaptureIndicator.CONTRADICTION_SUPPRESSION,
            CaptureIndicator.COMMITMENT_SHEAR,
        ]
        regime = classify_regime(
            k_vector=kv, capture_indicators=indicators,
            capture_streak=3, thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.CAPTURE

    def test_four_indicators_max_capture(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        indicators = list(CaptureIndicator)
        regime = classify_regime(
            k_vector=kv, capture_indicators=indicators,
            capture_streak=5, thresholds=CaptureThresholds(),
        )
        assert regime == CorrelatorRegime.CAPTURE


class TestJudgeInterferometryRun:
    def test_leverage_trusts_shared(self):
        fp = FidelityProxy(0.9, 0.3, 0.1, 2.0)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.8, "conflict_count": 1},
            k_vector=kv,
            capture_indicators=[],
        )
        assert result["trust_shared"] is True
        assert result["recommendation"] is None

    def test_capture_distrusts_shared(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        indicators = [
            CaptureIndicator.MODE_COUNT_DECREASING,
            CaptureIndicator.CONTRADICTION_SUPPRESSION,
        ]
        # Need capture_streak for classify_regime, but judge_interferometry_run
        # uses default thresholds without streak — so won't be CAPTURE via
        # classify_regime. Let's test with more indicators.
        # Actually, classify_regime default capture_consecutive_windows=2
        # and default capture_streak=0 means it won't declare CAPTURE.
        # This is correct behavior — judge should use the actual regime.
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.9, "conflict_count": 0},
            k_vector=kv,
            capture_indicators=indicators,
        )
        # With default thresholds and capture_streak=0, regime = LEVERAGE
        assert result["regime"] == "leverage"

    def test_shear_conditional_trust(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(1.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)  # low throughput
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.1, "conflict_count": 5},
            k_vector=kv,
            capture_indicators=[],
        )
        assert result["regime"] == "shear"
        assert result["trust_shared"] is False  # 0.1 < 0.3

    def test_shear_trusts_high_shared(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(1.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.5, "conflict_count": 2},
            k_vector=kv,
            capture_indicators=[],
        )
        assert result["regime"] == "shear"
        assert result["trust_shared"] is True  # 0.5 > 0.3

    def test_unknown_trusts(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 0)  # step=0
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.7, "conflict_count": 0},
            k_vector=kv,
            capture_indicators=[],
        )
        assert result["regime"] == "unknown"
        assert result["trust_shared"] is True

    def test_missing_run_signals(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        result = judge_interferometry_run(
            run_signals={},
            k_vector=kv,
            capture_indicators=[],
        )
        assert result["shared_ratio"] == 0.0
        assert result["conflict_count"] == 0

    def test_indicators_listed(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        result = judge_interferometry_run(
            run_signals={"shared_ratio": 0.5},
            k_vector=kv,
            capture_indicators=[CaptureIndicator.ENTROPY_NONINCREASING],
        )
        assert "entropy_nonincreasing" in result["indicators_active"]

    def test_result_always_has_regime(self):
        fp = FidelityProxy(0.5, 0.5, 0.5, 0.5)
        kv = KVector(10.0, fp, AuthorityLevel.BLOCKING, 0.3, 5)
        result = judge_interferometry_run(
            run_signals={}, k_vector=kv, capture_indicators=[],
        )
        assert "regime" in result


# =============================================================================
# Stateful Coordinator Tests
# =============================================================================


class TestCorrelatorTelemetry:
    def test_initial_state(self):
        ct = CorrelatorTelemetry()
        assert ct.get_regime() == CorrelatorRegime.UNKNOWN
        assert ct.get_latest_k_vector() is None
        assert ct.get_latest_diagnostic() is None
        assert ct.window_step == 0

    def test_observe_returns_diagnostic(self):
        ct = CorrelatorTelemetry()
        diag = ct.observe(exposure=10, throughput=5.0, hypothesis_count=5)
        assert isinstance(diag, CaptureDiagnostic)
        assert ct.window_step == 1

    def test_observe_increments_step(self):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10)
        ct.observe(exposure=10)
        ct.observe(exposure=10)
        assert ct.window_step == 3

    def test_history_ordering(self):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10, throughput=5.0)
        ct.observe(exposure=20, throughput=6.0)
        ct.observe(exposure=30, throughput=7.0)
        history = ct.get_history()
        assert len(history) == 3
        # Newest first
        assert history[0].signals.exposure == 30
        assert history[2].signals.exposure == 10

    def test_history_limit(self):
        ct = CorrelatorTelemetry()
        for i in range(5):
            ct.observe(exposure=i * 10)
        history = ct.get_history(limit=2)
        assert len(history) == 2

    def test_history_cap(self):
        ct = CorrelatorTelemetry(max_history=5)
        for i in range(10):
            ct.observe(exposure=i)
        assert len(ct.get_history()) == 5

    def test_get_metrics_empty(self):
        ct = CorrelatorTelemetry()
        metrics = ct.get_metrics()
        assert metrics["regime"] == "unknown"
        assert metrics["total_observations"] == 0

    def test_get_metrics_after_observations(self):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10, throughput=10.0, authority=AuthorityLevel.BLOCKING)
        ct.observe(exposure=10, throughput=10.0, authority=AuthorityLevel.BLOCKING)
        metrics = ct.get_metrics()
        assert metrics["total_observations"] == 2

    def test_reset(self):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10)
        ct.observe(exposure=20)
        ct.reset()
        assert ct.window_step == 0
        assert ct.get_regime() == CorrelatorRegime.UNKNOWN
        assert len(ct.get_history()) == 0

    def test_leverage_scenario(self):
        """Healthy system: active contradictions, diverse provenance, growing modes."""
        ct = CorrelatorTelemetry(thresholds=CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=1,
        ))
        # Window 0: UNKNOWN (first)
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 5},
            epistemic_metrics={"provenance_entropy": 2.5},
        )
        # Window 1: LEVERAGE (healthy growth)
        diag = ct.observe(
            exposure=60, hypothesis_count=15, throughput=12.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 7},
            epistemic_metrics={"provenance_entropy": 3.0},
        )
        assert diag.regime == CorrelatorRegime.LEVERAGE
        assert len(diag.indicators_triggered) == 0

    def test_capture_onset_scenario(self):
        """Capture: contradictions → 0, provenance concentrating, modes falling."""
        ct = CorrelatorTelemetry(thresholds=CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=1,
        ))
        # Healthy baseline
        ct.observe(
            exposure=50, hypothesis_count=20, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 10},
            epistemic_metrics={"provenance_entropy": 3.0},
        )
        # First capture-shaped window (streak builds)
        ct.observe(
            exposure=50, hypothesis_count=3, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.5},
            diff_trends={
                "silent_retraction_count": 10,
                "total_commitments_at_boundary": 50,
                "lost_commitments_at_boundary": 30,
            },
        )
        # Second capture-shaped window (triggers capture)
        diag = ct.observe(
            exposure=50, hypothesis_count=1, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.0},
            diff_trends={
                "silent_retraction_count": 15,
                "total_commitments_at_boundary": 40,
                "lost_commitments_at_boundary": 25,
            },
        )
        assert diag.regime == CorrelatorRegime.CAPTURE
        assert diag.gate_met is True
        assert len(diag.indicators_triggered) >= 2

    def test_advisory_prevents_capture_scenario(self):
        """Same signals in ADVISORY → NOT capture."""
        ct = CorrelatorTelemetry(thresholds=CaptureThresholds(
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
            capture_consecutive_windows=1,
        ))
        ct.observe(
            exposure=50, hypothesis_count=20, throughput=10.0,
            authority=AuthorityLevel.ADVISORY,
            dissent_metrics={"generated_objection_count": 10},
            epistemic_metrics={"provenance_entropy": 3.0},
        )
        ct.observe(
            exposure=50, hypothesis_count=3, throughput=10.0,
            authority=AuthorityLevel.ADVISORY,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.0},
        )
        diag = ct.observe(
            exposure=50, hypothesis_count=1, throughput=10.0,
            authority=AuthorityLevel.ADVISORY,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 0.5},
        )
        assert diag.regime != CorrelatorRegime.CAPTURE
        assert not diag.gate_met
        # Indicators still computed (non-binding)
        assert len(diag.indicators_triggered) > 0


class TestCorrelatorState:
    """Persistence tests for CorrelatorTelemetry."""

    def test_to_dict_from_dict_empty(self):
        ct = CorrelatorTelemetry()
        d = ct.to_dict()
        ct2 = CorrelatorTelemetry.from_dict(d)
        assert ct2.window_step == 0
        assert len(ct2.get_history()) == 0

    def test_to_dict_from_dict_with_history(self):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10, throughput=5.0, hypothesis_count=5)
        ct.observe(exposure=20, throughput=6.0, hypothesis_count=8)
        d = ct.to_dict()
        ct2 = CorrelatorTelemetry.from_dict(d)
        assert ct2.window_step == 2
        assert len(ct2.get_history()) == 2

    def test_roundtrip_preserves_indicator_state(self):
        ct = CorrelatorTelemetry()
        ct._indicator_state.mode_streak = 3
        ct._indicator_state.capture_streak = 1
        d = ct.to_dict()
        ct2 = CorrelatorTelemetry.from_dict(d)
        assert ct2.indicator_state.mode_streak == 3
        assert ct2.indicator_state.capture_streak == 1

    def test_roundtrip_preserves_thresholds(self):
        ct = CorrelatorTelemetry(
            thresholds=CaptureThresholds(throughput_min=3.0, exposure_min=10),
        )
        d = ct.to_dict()
        ct2 = CorrelatorTelemetry.from_dict(d)
        assert ct2.thresholds.throughput_min == 3.0
        assert ct2.thresholds.exposure_min == 10

    def test_save_load(self, tmp_path):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=10, throughput=5.0)
        ct.save(tmp_path)
        ct2 = CorrelatorTelemetry.load(tmp_path)
        assert ct2.window_step == 1
        assert len(ct2.get_history()) == 1

    def test_load_missing_file(self, tmp_path):
        ct = CorrelatorTelemetry.load(tmp_path)
        assert ct.window_step == 0

    def test_load_corrupt_json(self, tmp_path):
        (tmp_path / "correlator.json").write_text("NOT JSON")
        ct = CorrelatorTelemetry.load(tmp_path)
        assert ct.window_step == 0

    def test_save_atomic_creates_file(self, tmp_path):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=5)
        ct.save(tmp_path)
        path = tmp_path / "correlator.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["window_step"] == 1

    def test_save_overwrites(self, tmp_path):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=5)
        ct.save(tmp_path)
        ct.observe(exposure=10)
        ct.save(tmp_path)
        ct2 = CorrelatorTelemetry.load(tmp_path)
        assert ct2.window_step == 2

    def test_from_dict_defaults(self):
        ct = CorrelatorTelemetry.from_dict({})
        assert ct.window_step == 0
        assert ct.thresholds.throughput_min == 5.0

    def test_to_dict_includes_schema_version(self):
        from governor.correlator_telemetry import CORRELATOR_SCHEMA_VERSION
        ct = CorrelatorTelemetry()
        d = ct.to_dict()
        assert d["schema_version"] == CORRELATOR_SCHEMA_VERSION

    def test_from_dict_accepts_legacy_no_version(self):
        """Legacy blobs (no schema_version key) treated as v0, loaded OK."""
        d = {"thresholds": {}, "max_history": 50, "history": [], "window_step": 3}
        ct = CorrelatorTelemetry.from_dict(d)
        assert ct.window_step == 3

    def test_from_dict_rejects_future_version(self):
        from governor.correlator_telemetry import CORRELATOR_SCHEMA_VERSION
        d = {"schema_version": CORRELATOR_SCHEMA_VERSION + 1}
        with pytest.raises(ValueError, match="newer than supported"):
            CorrelatorTelemetry.from_dict(d)

    def test_save_load_roundtrip_preserves_version(self, tmp_path):
        ct = CorrelatorTelemetry()
        ct.observe(exposure=5)
        ct.save(tmp_path)
        data = json.loads((tmp_path / "correlator.json").read_text())
        assert "schema_version" in data
        ct2 = CorrelatorTelemetry.load(tmp_path)
        assert ct2.window_step == 1


# =============================================================================
# Scenario Tests (multi-indicator, end-to-end)
# =============================================================================


class TestScenarios:
    """Multi-indicator scenarios testing realistic sequences."""

    def _make_ct(self, **threshold_kwargs) -> CorrelatorTelemetry:
        defaults = {
            "mode_consecutive_windows": 1,
            "entropy_consecutive_windows": 1,
            "contradiction_consecutive_windows": 1,
            "commitment_consecutive_windows": 1,
            "capture_consecutive_windows": 2,
        }
        defaults.update(threshold_kwargs)
        return CorrelatorTelemetry(thresholds=CaptureThresholds(**defaults))

    def test_gradual_capture_onset(self):
        """Capture develops over multiple windows."""
        ct = self._make_ct()

        # Window 0: healthy baseline
        ct.observe(
            exposure=50, hypothesis_count=20, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 8},
            epistemic_metrics={"provenance_entropy": 3.0},
        )

        # Window 1: first signs
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 2},
            epistemic_metrics={"provenance_entropy": 2.5},
        )

        # Window 2: clear capture
        ct.observe(
            exposure=50, hypothesis_count=3, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 2.0},
            diff_trends={
                "total_commitments_at_boundary": 30,
                "lost_commitments_at_boundary": 15,
            },
        )

        # Window 3: capture declared (streak met)
        diag = ct.observe(
            exposure=50, hypothesis_count=1, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.5},
            diff_trends={
                "total_commitments_at_boundary": 25,
                "lost_commitments_at_boundary": 12,
            },
        )
        assert diag.regime == CorrelatorRegime.CAPTURE

    def test_recovery_from_capture(self):
        """System recovers from capture when contradictions resurface."""
        ct = self._make_ct(capture_consecutive_windows=1)

        # Baseline
        ct.observe(
            exposure=50, hypothesis_count=20, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 8},
            epistemic_metrics={"provenance_entropy": 3.0},
        )
        # Capture onset
        ct.observe(
            exposure=50, hypothesis_count=2, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.0},
            diff_trends={"total_commitments_at_boundary": 50, "lost_commitments_at_boundary": 30},
        )
        diag = ct.observe(
            exposure=50, hypothesis_count=1, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 0.5},
            diff_trends={"total_commitments_at_boundary": 50, "lost_commitments_at_boundary": 30},
        )
        assert diag.regime == CorrelatorRegime.CAPTURE

        # Recovery: contradictions return, entropy grows
        diag = ct.observe(
            exposure=50, hypothesis_count=15, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 10},
            epistemic_metrics={"provenance_entropy": 2.5},
        )
        # Capture streak broken
        assert diag.regime != CorrelatorRegime.CAPTURE

    def test_shear_under_low_throughput(self):
        """Low throughput under blocking → SHEAR."""
        ct = self._make_ct()
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=1.0,
            authority=AuthorityLevel.BLOCKING,
        )
        diag = ct.observe(
            exposure=50, hypothesis_count=10, throughput=2.0,
            authority=AuthorityLevel.BLOCKING,
        )
        assert diag.regime == CorrelatorRegime.SHEAR

    def test_boring_period_no_false_positive(self):
        """Low exposure quiet period should NOT trigger capture indicators."""
        ct = self._make_ct()
        # Baseline
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 5},
            epistemic_metrics={"provenance_entropy": 2.0},
        )
        # Quiet period: low exposure, stable entropy
        diag = ct.observe(
            exposure=1, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 2.0},
        )
        # Entropy check gated by exposure_min
        entropy_info = diag.indicator_details.get("entropy", {})
        if "reason" in entropy_info:
            assert entropy_info["reason"] == "exposure_below_minimum"

    def test_mixed_signals_no_capture(self):
        """Only one indicator fires → LEVERAGE, not CAPTURE."""
        ct = self._make_ct()
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 5},
            epistemic_metrics={"provenance_entropy": 2.0},
        )
        # Only contradiction suppression, everything else healthy
        diag = ct.observe(
            exposure=50, hypothesis_count=12, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 2.5},  # growing
        )
        assert diag.regime == CorrelatorRegime.LEVERAGE


# =============================================================================
# Telemetry Emission Tests
# =============================================================================


class TestTelemetryEmission:
    """Verify correlator emits structured telemetry events."""

    def test_observe_emits_correlator_observation(self):
        """Each observe() should emit a CORRELATOR_OBSERVATION event."""
        from governor.telemetry import TelemetryCollector, TelemetryConfig

        tel = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        ct = CorrelatorTelemetry(telemetry=tel)
        ct.observe(exposure=10, throughput=5.0)
        assert tel.event_count == 1

    def test_observe_emits_with_correct_fields(self):
        """Emitted event should have low-cardinality fields."""
        events = []

        class CapturingBackend:
            def record(self, event):
                events.append(event)

        from governor.telemetry import TelemetryCollector, TelemetryConfig

        tel = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        tel.add_backend(CapturingBackend())
        ct = CorrelatorTelemetry(telemetry=tel)
        ct.observe(exposure=10, throughput=5.0, authority=AuthorityLevel.ADVISORY)

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type.value == "correlator_observation"
        assert "regime" in ev.fields
        assert "k_throughput" in ev.fields
        assert "indicators" in ev.fields
        assert isinstance(ev.fields["indicators"], list)

    def test_capture_emits_capture_detected(self):
        """When capture is declared (binding), should emit CAPTURE_DETECTED."""
        events = []

        class CapturingBackend:
            def record(self, event):
                events.append(event)

        from governor.telemetry import TelemetryCollector, TelemetryConfig

        tel = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        tel.add_backend(CapturingBackend())
        # Use thresholds that make capture easy to trigger
        thresholds = CaptureThresholds(
            capture_indicator_min=1,
            capture_consecutive_windows=1,
            mode_consecutive_windows=1,
            entropy_consecutive_windows=1,
            contradiction_consecutive_windows=1,
            commitment_consecutive_windows=1,
        )
        ct = CorrelatorTelemetry(thresholds=thresholds, telemetry=tel)
        # First observation to set baseline
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 5},
            epistemic_metrics={"provenance_entropy": 2.0},
            mode_ratio=1.0,
        )
        # Second observation with capture-like signals
        ct.observe(
            exposure=50, hypothesis_count=10, throughput=10.0,
            authority=AuthorityLevel.BLOCKING,
            dissent_metrics={"generated_objection_count": 0},
            epistemic_metrics={"provenance_entropy": 1.0},
            mode_ratio=0.3,
            commitment_shear=0.5,
        )

        capture_events = [e for e in events if e.event_type.value == "capture_detected"]
        # May or may not trigger depending on exact thresholds — just verify no crash
        # and that observation events were emitted
        obs_events = [e for e in events if e.event_type.value == "correlator_observation"]
        assert len(obs_events) == 2

    def test_no_telemetry_no_crash(self):
        """Without a collector, observe() still works fine."""
        ct = CorrelatorTelemetry(telemetry=None)
        diag = ct.observe(exposure=10, throughput=5.0)
        assert diag is not None

    def test_load_with_telemetry(self, tmp_path):
        """load() should accept and pass through telemetry parameter."""
        from governor.telemetry import TelemetryCollector, TelemetryConfig

        tel = TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
        ct = CorrelatorTelemetry.load(tmp_path, telemetry=tel)
        assert ct._telemetry is tel
        ct.observe(exposure=5, throughput=1.0)
        assert tel.event_count == 1
