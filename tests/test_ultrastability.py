# SPDX-License-Identifier: Apache-2.0
"""Tests for governor.ultrastability — Ashby-style S₁ adaptation."""

import json
import pytest

from governor.ultrastability import (
    AdaptationVerdict,
    Pathology,
    ParameterDirection,
    ParameterSpec,
    RegulatoryParameters,
    EpochObservation,
    AdaptationRecord,
    AdaptationHistory,
    AdaptationTrigger,
    PathologyDetector,
    AdaptationDecision,
    UltrastabilityController,
    create_controller,
    create_default_parameters,
    observe_and_consider,
    DEFAULT_PARAMETERS,
)
from datetime import datetime, timezone


# =============================================================================
# Enum Tests
# =============================================================================


class TestAdaptationVerdict:
    def test_values(self):
        assert AdaptationVerdict.HOLD.value == "hold"
        assert AdaptationVerdict.ADAPT.value == "adapt"
        assert AdaptationVerdict.FREEZE.value == "freeze"
        assert AdaptationVerdict.ALERT.value == "alert"

    def test_string_enum(self):
        assert AdaptationVerdict.HOLD == "hold"


class TestPathology:
    def test_values(self):
        assert Pathology.OSCILLATION.value == "oscillation"
        assert Pathology.RUNAWAY.value == "runaway"
        assert Pathology.INEFFECTIVE.value == "ineffective"
        assert Pathology.WRONG_ATTRACTOR.value == "wrong_attractor"


class TestParameterDirection:
    def test_values(self):
        assert ParameterDirection.INCREASE.value == "increase"
        assert ParameterDirection.DECREASE.value == "decrease"


# =============================================================================
# ParameterSpec Tests
# =============================================================================


class TestParameterSpec:
    def test_basic_creation(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.name == "test"
        assert s.current == 5.0
        assert s.floor == 0.0
        assert s.ceiling == 10.0
        assert s.step == 1.0

    def test_floor_ceiling_validation(self):
        with pytest.raises(ValueError, match="floor.*ceiling"):
            ParameterSpec(name="bad", current=5.0, floor=10.0, ceiling=0.0, step=1.0)

    def test_step_validation(self):
        with pytest.raises(ValueError, match="step must be positive"):
            ParameterSpec(name="bad", current=5.0, floor=0.0, ceiling=10.0, step=0)

    def test_current_clamped_to_bounds(self):
        s = ParameterSpec(name="test", current=15.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.current == 10.0
        s2 = ParameterSpec(name="test", current=-5.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s2.current == 0.0

    def test_at_floor(self):
        s = ParameterSpec(name="test", current=0.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.at_floor
        s2 = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        assert not s2.at_floor

    def test_at_ceiling(self):
        s = ParameterSpec(name="test", current=10.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.at_ceiling

    def test_headroom(self):
        s = ParameterSpec(name="test", current=3.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.headroom_up == 7.0
        assert s.headroom_down == 3.0

    def test_range(self):
        s = ParameterSpec(name="test", current=5.0, floor=2.0, ceiling=8.0, step=1.0)
        assert s.range == 6.0

    def test_normalized(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s.normalized == 0.5
        s2 = ParameterSpec(name="test", current=0.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s2.normalized == 0.0
        s3 = ParameterSpec(name="test", current=10.0, floor=0.0, ceiling=10.0, step=1.0)
        assert s3.normalized == 1.0

    def test_normalized_zero_range(self):
        s = ParameterSpec(name="test", current=5.0, floor=5.0, ceiling=5.0, step=1.0)
        assert s.normalized == 0.5

    def test_propose_change_normal(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=2.0)
        new_val, clamped = s.propose_change(1.5)
        assert new_val == 6.5
        assert not clamped

    def test_propose_change_clamped_ceiling(self):
        s = ParameterSpec(name="test", current=9.0, floor=0.0, ceiling=10.0, step=2.0)
        new_val, clamped = s.propose_change(2.0)
        assert new_val == 10.0
        assert clamped

    def test_propose_change_clamped_floor(self):
        s = ParameterSpec(name="test", current=1.0, floor=0.0, ceiling=10.0, step=2.0)
        new_val, clamped = s.propose_change(-2.0)
        assert new_val == 0.0
        assert clamped

    def test_propose_change_step_limit(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        new_val, clamped = s.propose_change(5.0)
        assert new_val == 6.0  # Clamped to step size
        assert not clamped  # Not clamped to floor/ceiling

    def test_apply(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        s.apply(7.0)
        assert s.current == 7.0

    def test_apply_clamped(self):
        s = ParameterSpec(name="test", current=5.0, floor=0.0, ceiling=10.0, step=1.0)
        s.apply(15.0)
        assert s.current == 10.0

    def test_to_dict(self):
        s = ParameterSpec(name="budget", current=100.0, floor=10.0, ceiling=500.0, step=10.0, description="test")
        d = s.to_dict()
        assert d["name"] == "budget"
        assert d["current"] == 100.0
        assert d["description"] == "test"

    def test_roundtrip(self):
        s = ParameterSpec(name="budget", current=100.0, floor=10.0, ceiling=500.0, step=10.0)
        d = s.to_dict()
        s2 = ParameterSpec.from_dict(d)
        assert s2.name == s.name
        assert s2.current == s.current
        assert s2.floor == s.floor
        assert s2.ceiling == s.ceiling


# =============================================================================
# RegulatoryParameters Tests
# =============================================================================


class TestRegulatoryParameters:
    def test_default_parameters(self):
        params = RegulatoryParameters()
        assert len(params.names) == len(DEFAULT_PARAMETERS)
        assert "repair_budget" in params.names
        assert "refill_rate" in params.names
        assert "evidence_threshold" in params.names

    def test_get(self):
        params = RegulatoryParameters()
        spec = params.get("repair_budget")
        assert spec.name == "repair_budget"
        assert spec.current == 100.0

    def test_get_unknown(self):
        params = RegulatoryParameters()
        with pytest.raises(KeyError):
            params.get("nonexistent")

    def test_value(self):
        params = RegulatoryParameters()
        assert params.value("repair_budget") == 100.0

    def test_set_value(self):
        params = RegulatoryParameters()
        params.set_value("repair_budget", 200.0)
        assert params.value("repair_budget") == 200.0

    def test_propose_change(self):
        params = RegulatoryParameters()
        new_val, clamped = params.propose_change("repair_budget", 10.0)
        assert new_val == 110.0
        assert not clamped

    def test_apply_change(self):
        params = RegulatoryParameters()
        params.apply_change("repair_budget", 200.0)
        assert params.value("repair_budget") == 200.0

    def test_summary(self):
        params = RegulatoryParameters()
        s = params.summary()
        assert "repair_budget" in s
        assert "current" in s["repair_budget"]
        assert "normalized" in s["repair_budget"]

    def test_custom_specs(self):
        specs = [
            ParameterSpec(name="custom", current=50.0, floor=0.0, ceiling=100.0, step=5.0),
        ]
        params = RegulatoryParameters(specs)
        assert params.names == ["custom"]
        assert params.value("custom") == 50.0

    def test_to_dict(self):
        params = RegulatoryParameters()
        d = params.to_dict()
        assert "parameters" in d
        assert len(d["parameters"]) == len(DEFAULT_PARAMETERS)

    def test_roundtrip(self):
        params = RegulatoryParameters()
        params.set_value("repair_budget", 250.0)
        d = params.to_dict()
        params2 = RegulatoryParameters.from_dict(d)
        assert params2.value("repair_budget") == 250.0


# =============================================================================
# EpochObservation Tests
# =============================================================================


class TestEpochObservation:
    def test_defaults(self):
        obs = EpochObservation()
        assert obs.epoch_id == 0
        assert obs.turns == 0
        assert obs.c_open == 0
        assert obs.regime == "ELASTIC"

    def test_compute_rates(self):
        obs = EpochObservation(
            turns=100,
            contradictions_opened=10,
            contradictions_closed=5,
            budget_blocks=30,
            violations=20,
            dangerous_claims=15,
            proposals_submitted=50,
            proposals_accepted=40,
            proposals_rejected=10,
        )
        obs.compute_rates()
        assert obs.open_rate == 0.1
        assert obs.close_rate == 0.05
        assert obs.block_rate == 0.3
        assert obs.violation_rate == 0.2
        assert obs.dangerous_rate == 0.15
        assert obs.acceptance_rate == 0.8
        assert obs.rejection_rate == 0.2

    def test_compute_rates_zero_turns(self):
        obs = EpochObservation(turns=0)
        obs.compute_rates()
        assert obs.block_rate == 0.0

    def test_to_dict(self):
        obs = EpochObservation(turns=50, c_open=10, regime="WARM")
        d = obs.to_dict()
        assert d["turns"] == 50
        assert d["c_open"] == 10
        assert d["regime"] == "WARM"

    def test_roundtrip(self):
        obs = EpochObservation(
            turns=100,
            contradictions_opened=10,
            budget_blocks=30,
            c_open=15,
            regime="DUCTILE",
        )
        obs.compute_rates()
        d = obs.to_dict()
        obs2 = EpochObservation.from_dict(d)
        assert obs2.turns == 100
        assert obs2.c_open == 15
        assert obs2.regime == "DUCTILE"
        assert obs2.block_rate == obs.block_rate


# =============================================================================
# AdaptationRecord Tests
# =============================================================================


class TestAdaptationRecord:
    def _make_record(self, **kwargs) -> AdaptationRecord:
        defaults = dict(
            epoch_id=0,
            timestamp=datetime.now(timezone.utc),
            parameter="repair_budget",
            old_value=100.0,
            new_value=110.0,
            delta=10.0,
            was_clamped=False,
            reason="test",
            direction=ParameterDirection.INCREASE,
        )
        defaults.update(kwargs)
        return AdaptationRecord(**defaults)

    def test_creation(self):
        r = self._make_record()
        assert r.parameter == "repair_budget"
        assert r.delta == 10.0
        assert r.direction == ParameterDirection.INCREASE

    def test_to_dict(self):
        r = self._make_record()
        d = r.to_dict()
        assert d["parameter"] == "repair_budget"
        assert d["direction"] == "increase"

    def test_roundtrip(self):
        r = self._make_record(was_clamped=True, direction=ParameterDirection.DECREASE)
        d = r.to_dict()
        r2 = AdaptationRecord.from_dict(d)
        assert r2.parameter == r.parameter
        assert r2.was_clamped is True
        assert r2.direction == ParameterDirection.DECREASE


# =============================================================================
# AdaptationHistory Tests
# =============================================================================


class TestAdaptationHistory:
    def test_empty(self):
        h = AdaptationHistory()
        assert len(h.epochs) == 0
        assert len(h.records) == 0
        assert h.total_adaptations == 0

    def test_add_epoch(self):
        h = AdaptationHistory()
        h.add_epoch(EpochObservation(turns=50))
        assert len(h.epochs) == 1

    def test_epoch_eviction(self):
        h = AdaptationHistory(max_epochs=3)
        for i in range(5):
            h.add_epoch(EpochObservation(epoch_id=i, turns=10))
        assert len(h.epochs) == 3
        assert h.epochs[0].epoch_id == 2  # Oldest evicted

    def test_add_record(self):
        h = AdaptationHistory()
        r = AdaptationRecord(
            epoch_id=0, timestamp=datetime.now(timezone.utc),
            parameter="x", old_value=1, new_value=2, delta=1,
            was_clamped=False, reason="test", direction=ParameterDirection.INCREASE,
        )
        h.add_record(r)
        assert h.total_adaptations == 1

    def test_record_eviction(self):
        h = AdaptationHistory(max_records=3)
        for i in range(5):
            r = AdaptationRecord(
                epoch_id=i, timestamp=datetime.now(timezone.utc),
                parameter="x", old_value=i, new_value=i + 1, delta=1,
                was_clamped=False, reason="test", direction=ParameterDirection.INCREASE,
            )
            h.add_record(r)
        assert len(h.records) == 3

    def test_get_trend_insufficient_data(self):
        h = AdaptationHistory()
        h.add_epoch(EpochObservation(c_open=5))
        assert h.get_trend("c_open", window=3) is None

    def test_get_trend_increasing(self):
        h = AdaptationHistory()
        for i in range(5):
            h.add_epoch(EpochObservation(epoch_id=i, c_open=10 + i * 5))
        trend = h.get_trend("c_open", window=5)
        assert trend is not None
        assert trend > 0  # Increasing

    def test_get_trend_decreasing(self):
        h = AdaptationHistory()
        for i in range(5):
            h.add_epoch(EpochObservation(epoch_id=i, c_open=30 - i * 5))
        trend = h.get_trend("c_open", window=5)
        assert trend is not None
        assert trend < 0  # Decreasing

    def test_get_trend_flat(self):
        h = AdaptationHistory()
        for i in range(5):
            h.add_epoch(EpochObservation(epoch_id=i, c_open=10))
        trend = h.get_trend("c_open", window=5)
        assert trend == 0.0

    def test_recent_records_for(self):
        h = AdaptationHistory()
        for i in range(3):
            h.add_record(AdaptationRecord(
                epoch_id=i, timestamp=datetime.now(timezone.utc),
                parameter="repair_budget", old_value=100 + i, new_value=110 + i,
                delta=10, was_clamped=False, reason="test",
                direction=ParameterDirection.INCREASE,
            ))
        h.add_record(AdaptationRecord(
            epoch_id=3, timestamp=datetime.now(timezone.utc),
            parameter="refill_rate", old_value=5, new_value=6,
            delta=1, was_clamped=False, reason="test",
            direction=ParameterDirection.INCREASE,
        ))
        recs = h.recent_records_for("repair_budget")
        assert len(recs) == 3

    def test_roundtrip(self):
        h = AdaptationHistory()
        h.add_epoch(EpochObservation(epoch_id=0, turns=100, c_open=10))
        h.add_record(AdaptationRecord(
            epoch_id=0, timestamp=datetime.now(timezone.utc),
            parameter="x", old_value=1, new_value=2, delta=1,
            was_clamped=False, reason="test", direction=ParameterDirection.INCREASE,
        ))
        d = h.to_dict()
        h2 = AdaptationHistory.from_dict(d)
        assert len(h2.epochs) == 1
        assert len(h2.records) == 1


# =============================================================================
# AdaptationTrigger Tests
# =============================================================================


class TestAdaptationTrigger:
    def test_defaults(self):
        t = AdaptationTrigger()
        assert t.block_rate_threshold == 0.3
        assert t.c_open_threshold == 15

    def test_stable_no_trigger(self):
        t = AdaptationTrigger()
        obs = EpochObservation(turns=100, budget_blocks=10, c_open=5)
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert not should
        assert len(reasons) == 0

    def test_high_block_rate_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(turns=100, budget_blocks=50)
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("block_rate" in r for r in reasons)

    def test_high_c_open_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(turns=100, c_open=20)
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("c_open" in r for r in reasons)

    def test_accumulation_ratio_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(
            turns=100, contradictions_opened=20, contradictions_closed=5,
        )
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("open_rate" in r for r in reasons)

    def test_zero_close_rate_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(
            turns=100, contradictions_opened=5, contradictions_closed=0,
        )
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("none closing" in r for r in reasons)

    def test_violation_rate_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(turns=100, violations=30)
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("violation_rate" in r for r in reasons)

    def test_dangerous_rate_triggers(self):
        t = AdaptationTrigger()
        obs = EpochObservation(turns=100, dangerous_claims=15)
        obs.compute_rates()
        h = AdaptationHistory()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("dangerous_rate" in r for r in reasons)

    def test_trend_triggers(self):
        t = AdaptationTrigger(min_epochs_for_trend=3, trend_significance=0.05)
        h = AdaptationHistory()
        for i in range(4):
            h.add_epoch(EpochObservation(epoch_id=i, turns=100, c_open=10 + i * 10))
        obs = EpochObservation(turns=100, c_open=50)
        obs.compute_rates()
        should, reasons = t.evaluate(obs, h)
        assert should
        assert any("trending up" in r for r in reasons)

    def test_roundtrip(self):
        t = AdaptationTrigger(block_rate_threshold=0.5, c_open_threshold=25)
        d = t.to_dict()
        t2 = AdaptationTrigger.from_dict(d)
        assert t2.block_rate_threshold == 0.5
        assert t2.c_open_threshold == 25


# =============================================================================
# PathologyDetector Tests
# =============================================================================


class TestPathologyDetector:
    def _make_record(self, param: str, delta: float, clamped: bool = False, epoch: int = 0) -> AdaptationRecord:
        direction = ParameterDirection.INCREASE if delta >= 0 else ParameterDirection.DECREASE
        return AdaptationRecord(
            epoch_id=epoch, timestamp=datetime.now(timezone.utc),
            parameter=param, old_value=100, new_value=100 + delta,
            delta=delta, was_clamped=clamped, reason="test",
            direction=direction,
        )

    def test_no_pathology(self):
        d = PathologyDetector()
        h = AdaptationHistory()
        pathologies, messages = d.detect(h)
        assert len(pathologies) == 0

    def test_oscillation_detected(self):
        d = PathologyDetector(oscillation_window=6, oscillation_threshold=3)
        h = AdaptationHistory()
        # Alternating increases and decreases
        for i in range(6):
            delta = 10 if i % 2 == 0 else -10
            h.add_record(self._make_record("repair_budget", delta))
        pathologies, messages = d.detect(h)
        assert Pathology.OSCILLATION in pathologies

    def test_oscillation_not_triggered_below_threshold(self):
        d = PathologyDetector(oscillation_window=6, oscillation_threshold=3)
        h = AdaptationHistory()
        # Only 2 reversals (below threshold of 3)
        deltas = [10, -10, 10, 10, 10, 10]
        for delta in deltas:
            h.add_record(self._make_record("repair_budget", delta))
        pathologies, _ = d.detect(h)
        assert Pathology.OSCILLATION not in pathologies

    def test_runaway_clamped(self):
        d = PathologyDetector(runaway_threshold=5)
        h = AdaptationHistory()
        for i in range(5):
            h.add_record(self._make_record("repair_budget", 10, clamped=True))
        pathologies, messages = d.detect(h)
        assert Pathology.RUNAWAY in pathologies

    def test_runaway_same_direction(self):
        d = PathologyDetector(runaway_threshold=5)
        h = AdaptationHistory()
        for i in range(5):
            h.add_record(self._make_record("repair_budget", 10))
        pathologies, messages = d.detect(h)
        assert Pathology.RUNAWAY in pathologies

    def test_ineffective_detected(self):
        d = PathologyDetector(ineffective_epochs=3)
        h = AdaptationHistory()
        # 3 epochs, metrics not improving despite adaptations
        for i in range(3):
            h.add_epoch(EpochObservation(
                epoch_id=i, turns=100, budget_blocks=30, c_open=20,
            ))
            h.epochs[-1].compute_rates()
            h.add_record(self._make_record("repair_budget", 10, epoch=i))
        pathologies, messages = d.detect(h)
        assert Pathology.INEFFECTIVE in pathologies

    def test_ineffective_not_triggered_if_improving(self):
        d = PathologyDetector(ineffective_epochs=3)
        h = AdaptationHistory()
        for i in range(3):
            h.add_epoch(EpochObservation(
                epoch_id=i, turns=100, budget_blocks=30 - i * 10, c_open=20 - i * 5,
            ))
            h.epochs[-1].compute_rates()
            h.add_record(self._make_record("repair_budget", 10, epoch=i))
        pathologies, _ = d.detect(h)
        assert Pathology.INEFFECTIVE not in pathologies

    def test_ineffective_not_triggered_without_adaptations(self):
        d = PathologyDetector(ineffective_epochs=3)
        h = AdaptationHistory()
        for i in range(3):
            h.add_epoch(EpochObservation(
                epoch_id=i, turns=100, budget_blocks=30, c_open=20,
            ))
        # No adaptations → not ineffective (nothing was tried)
        pathologies, _ = d.detect(h)
        assert Pathology.INEFFECTIVE not in pathologies

    def test_wrong_attractor(self):
        d = PathologyDetector(wrong_attractor_epochs=3, wrong_attractor_regimes=["UNSTABLE"])
        h = AdaptationHistory()
        for i in range(3):
            h.add_epoch(EpochObservation(epoch_id=i, regime="UNSTABLE"))
        pathologies, messages = d.detect(h)
        assert Pathology.WRONG_ATTRACTOR in pathologies

    def test_wrong_attractor_not_triggered_mixed_regimes(self):
        d = PathologyDetector(wrong_attractor_epochs=3)
        h = AdaptationHistory()
        regimes = ["ELASTIC", "UNSTABLE", "ELASTIC"]
        for i, r in enumerate(regimes):
            h.add_epoch(EpochObservation(epoch_id=i, regime=r))
        pathologies, _ = d.detect(h)
        assert Pathology.WRONG_ATTRACTOR not in pathologies

    def test_wrong_attractor_good_regime_ok(self):
        d = PathologyDetector(wrong_attractor_epochs=3)
        h = AdaptationHistory()
        for i in range(3):
            h.add_epoch(EpochObservation(epoch_id=i, regime="ELASTIC"))
        pathologies, _ = d.detect(h)
        assert Pathology.WRONG_ATTRACTOR not in pathologies

    def test_multiple_pathologies(self):
        """Multiple pathologies can be detected simultaneously."""
        d = PathologyDetector(
            oscillation_window=6, oscillation_threshold=3,
            wrong_attractor_epochs=3,
        )
        h = AdaptationHistory()
        # Oscillation
        for i in range(6):
            delta = 10 if i % 2 == 0 else -10
            h.add_record(self._make_record("repair_budget", delta))
        # Wrong attractor
        for i in range(3):
            h.add_epoch(EpochObservation(epoch_id=i, regime="UNSTABLE"))
        pathologies, _ = d.detect(h)
        assert Pathology.OSCILLATION in pathologies
        assert Pathology.WRONG_ATTRACTOR in pathologies

    def test_roundtrip(self):
        d = PathologyDetector(oscillation_window=10, runaway_threshold=8)
        data = d.to_dict()
        d2 = PathologyDetector.from_dict(data)
        assert d2.oscillation_window == 10
        assert d2.runaway_threshold == 8


# =============================================================================
# UltrastabilityController Tests
# =============================================================================


class TestUltrastabilityControllerBasics:
    def test_creation(self):
        ctrl = UltrastabilityController()
        assert ctrl.current_epoch == 0
        assert not ctrl.frozen
        assert ctrl.freeze_reason is None
        assert len(ctrl.history.epochs) == 0

    def test_creation_with_params(self):
        params = RegulatoryParameters()
        params.set_value("repair_budget", 200.0)
        ctrl = UltrastabilityController(parameters=params)
        assert ctrl.parameters.value("repair_budget") == 200.0

    def test_observe_epoch(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, c_open=5)
        ctrl.observe_epoch(obs)
        assert len(ctrl.history.epochs) == 1
        assert ctrl.history.epochs[0].epoch_id == 0

    def test_advance_epoch(self):
        ctrl = UltrastabilityController()
        ctrl.advance_epoch()
        assert ctrl.current_epoch == 1
        ctrl.advance_epoch()
        assert ctrl.current_epoch == 2


class TestUltrastabilityControllerHold:
    def test_hold_no_observations(self):
        ctrl = UltrastabilityController()
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.HOLD
        assert "no observations" in decision.reason

    def test_hold_stable(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, budget_blocks=5, c_open=3)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.HOLD


class TestUltrastabilityControllerAdapt:
    def test_adapt_high_block_rate(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, budget_blocks=50, c_open=3)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert decision.parameter == "repair_budget"
        assert decision.proposed_value > ctrl.parameters.value("repair_budget") or decision.parameter == "resolution_cost"

    def test_adapt_applied(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, budget_blocks=50, c_open=3)
        ctrl.observe_epoch(obs)
        old_budget = ctrl.parameters.value("repair_budget")
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        applied = ctrl.apply_adaptation(decision)
        assert applied
        assert ctrl.parameters.value(decision.parameter) == decision.proposed_value
        assert ctrl.history.total_adaptations == 1

    def test_adapt_not_applied_if_hold(self):
        ctrl = UltrastabilityController()
        decision = AdaptationDecision(verdict=AdaptationVerdict.HOLD, reason="stable")
        applied = ctrl.apply_adaptation(decision)
        assert not applied

    def test_adapt_accumulation(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, c_open=20)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert decision.parameter == "refill_rate"

    def test_adapt_violations(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, violations=30)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert decision.parameter == "evidence_threshold"

    def test_adapt_dangerous_claims(self):
        ctrl = UltrastabilityController()
        obs = EpochObservation(turns=100, dangerous_claims=15)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert decision.parameter == "independence_threshold"

    def test_adapt_budget_at_ceiling_falls_to_cost(self):
        """When repair_budget is at ceiling, reduce resolution_cost instead."""
        ctrl = UltrastabilityController()
        ctrl.parameters.set_value("repair_budget", 500.0)  # At ceiling
        obs = EpochObservation(turns=100, budget_blocks=50, c_open=3)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert decision.parameter == "resolution_cost"


class TestUltrastabilityControllerFreeze:
    def test_manual_freeze(self):
        ctrl = UltrastabilityController()
        ctrl.freeze("manual test")
        assert ctrl.frozen
        assert ctrl.freeze_reason == "manual test"

    def test_frozen_returns_freeze_verdict(self):
        ctrl = UltrastabilityController()
        ctrl.freeze("manual test")
        obs = EpochObservation(turns=100, budget_blocks=50)
        ctrl.observe_epoch(obs)
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.FREEZE

    def test_unfreeze(self):
        ctrl = UltrastabilityController()
        ctrl.freeze("test")
        assert ctrl.frozen
        ctrl.unfreeze("human reviewed")
        assert not ctrl.frozen
        assert ctrl.freeze_reason is None
        # Unfreeze is logged
        assert ctrl.history.total_adaptations == 1

    def test_pathology_triggers_alert_and_freeze(self):
        """Pathology detection auto-freezes and returns ALERT."""
        ctrl = UltrastabilityController(
            pathology_detector=PathologyDetector(
                wrong_attractor_epochs=3,
                wrong_attractor_regimes=["UNSTABLE"],
            ),
        )
        for i in range(3):
            obs = EpochObservation(epoch_id=i, turns=100, regime="UNSTABLE")
            ctrl.observe_epoch(obs)
            ctrl.advance_epoch()

        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ALERT
        assert Pathology.WRONG_ATTRACTOR in decision.pathologies
        assert ctrl.frozen


class TestUltrastabilityControllerQueries:
    def test_get_state(self):
        ctrl = UltrastabilityController()
        state = ctrl.get_state()
        assert "epoch" in state
        assert "frozen" in state
        assert "parameters" in state
        assert "total_adaptations" in state

    def test_get_metrics(self):
        ctrl = UltrastabilityController()
        # Run a few adaptations
        for i in range(3):
            obs = EpochObservation(turns=100, budget_blocks=50)
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            if decision.verdict == AdaptationVerdict.ADAPT:
                ctrl.apply_adaptation(decision)
            ctrl.advance_epoch()

        m = ctrl.get_metrics()
        assert m["total_epochs"] == 3
        assert m["total_adaptations"] >= 1
        assert "adaptations_by_parameter" in m
        assert "adaptations_by_direction" in m


# =============================================================================
# Serialization Tests
# =============================================================================


class TestUltrastabilityControllerSerialization:
    def test_to_dict(self):
        ctrl = UltrastabilityController()
        d = ctrl.to_dict()
        assert "parameters" in d
        assert "trigger" in d
        assert "pathology_detector" in d
        assert "history" in d
        assert "frozen" in d
        assert "current_epoch" in d

    def test_from_dict(self):
        ctrl = UltrastabilityController()
        ctrl.parameters.set_value("repair_budget", 300.0)
        ctrl.current_epoch = 5
        ctrl.freeze("test")
        d = ctrl.to_dict()
        ctrl2 = UltrastabilityController.from_dict(d)
        assert ctrl2.parameters.value("repair_budget") == 300.0
        assert ctrl2.current_epoch == 5
        assert ctrl2.frozen

    def test_to_json(self):
        ctrl = UltrastabilityController()
        j = ctrl.to_json()
        data = json.loads(j)
        assert data["current_epoch"] == 0

    def test_roundtrip_with_history(self):
        ctrl = UltrastabilityController()
        for i in range(5):
            obs = EpochObservation(turns=100, budget_blocks=50 if i < 3 else 10, c_open=5)
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            if decision.verdict == AdaptationVerdict.ADAPT:
                ctrl.apply_adaptation(decision)
            ctrl.advance_epoch()

        d = ctrl.to_dict()
        ctrl2 = UltrastabilityController.from_dict(d)
        assert ctrl2.current_epoch == ctrl.current_epoch
        assert ctrl2.parameters.value("repair_budget") == ctrl.parameters.value("repair_budget")
        assert len(ctrl2.history.epochs) == len(ctrl.history.epochs)
        assert len(ctrl2.history.records) == len(ctrl.history.records)


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    def test_create_controller(self):
        ctrl = create_controller()
        assert isinstance(ctrl, UltrastabilityController)
        assert not ctrl.frozen

    def test_create_controller_custom(self):
        params = create_default_parameters()
        params.set_value("repair_budget", 300.0)
        trigger = AdaptationTrigger(block_rate_threshold=0.5)
        ctrl = create_controller(params, trigger)
        assert ctrl.parameters.value("repair_budget") == 300.0
        assert ctrl.trigger.block_rate_threshold == 0.5

    def test_create_default_parameters(self):
        params = create_default_parameters()
        assert "repair_budget" in params.names

    def test_observe_and_consider_stable(self):
        ctrl = create_controller()
        decision = observe_and_consider(ctrl, turns=100, c_open=3)
        assert decision.verdict == AdaptationVerdict.HOLD
        assert ctrl.current_epoch == 1  # Advanced

    def test_observe_and_consider_stressed(self):
        ctrl = create_controller()
        decision = observe_and_consider(
            ctrl, turns=100, budget_blocks=50, c_open=3,
        )
        assert decision.verdict == AdaptationVerdict.ADAPT
        assert ctrl.current_epoch == 1


# =============================================================================
# Integration / E2E Tests
# =============================================================================


class TestE2E:
    def test_full_adaptation_cycle(self):
        """Simulate a full cycle: stress → adapt → stabilize."""
        ctrl = create_controller()

        # Phase 1: Stressed system
        for i in range(3):
            obs = EpochObservation(turns=100, budget_blocks=50, c_open=5)
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            if decision.verdict == AdaptationVerdict.ADAPT:
                ctrl.apply_adaptation(decision)
            ctrl.advance_epoch()

        # Repair budget should have increased
        assert ctrl.parameters.value("repair_budget") > 100.0

        # Phase 2: Stabilized
        for i in range(3):
            obs = EpochObservation(turns=100, budget_blocks=5, c_open=3)
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            assert decision.verdict == AdaptationVerdict.HOLD
            ctrl.advance_epoch()

    def test_pathology_detection_and_recovery(self):
        """Simulate pathology → freeze → human unfreeze → resume."""
        ctrl = UltrastabilityController(
            pathology_detector=PathologyDetector(
                wrong_attractor_epochs=3,
                wrong_attractor_regimes=["UNSTABLE"],
            ),
        )

        # Push into UNSTABLE for 3 epochs
        for i in range(3):
            obs = EpochObservation(turns=100, regime="UNSTABLE", budget_blocks=50)
            ctrl.observe_epoch(obs)
            ctrl.advance_epoch()

        # Now adaptation should detect pathology
        decision = ctrl.consider_adaptation()
        assert decision.verdict == AdaptationVerdict.ALERT
        assert ctrl.frozen

        # System is frozen
        decision2 = ctrl.consider_adaptation()
        assert decision2.verdict == AdaptationVerdict.FREEZE

        # Human unfreezes
        ctrl.unfreeze("investigated and fixed root cause")
        assert not ctrl.frozen

        # Can adapt again
        obs = EpochObservation(turns=100, budget_blocks=50, regime="WARM")
        ctrl.observe_epoch(obs)
        decision3 = ctrl.consider_adaptation()
        assert decision3.verdict in (AdaptationVerdict.ADAPT, AdaptationVerdict.HOLD)

    def test_multiple_parameter_adaptations(self):
        """Different stresses adapt different parameters."""
        ctrl = create_controller()

        # Block rate stress → repair_budget
        obs = EpochObservation(turns=100, budget_blocks=50)
        ctrl.observe_epoch(obs)
        d1 = ctrl.consider_adaptation()
        assert d1.parameter == "repair_budget"
        ctrl.apply_adaptation(d1)
        ctrl.advance_epoch()

        # Contradiction accumulation → refill_rate
        obs = EpochObservation(turns=100, c_open=20)
        ctrl.observe_epoch(obs)
        d2 = ctrl.consider_adaptation()
        assert d2.parameter == "refill_rate"
        ctrl.apply_adaptation(d2)
        ctrl.advance_epoch()

        # Violation rate → evidence_threshold
        obs = EpochObservation(turns=100, violations=30)
        ctrl.observe_epoch(obs)
        d3 = ctrl.consider_adaptation()
        assert d3.parameter == "evidence_threshold"

    def test_serialization_preserves_full_state(self):
        """Full round-trip preserves all controller state."""
        ctrl = create_controller()

        for i in range(5):
            obs = EpochObservation(
                turns=100,
                budget_blocks=40 if i < 3 else 5,
                c_open=10 + i,
            )
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            if decision.verdict == AdaptationVerdict.ADAPT:
                ctrl.apply_adaptation(decision)
            ctrl.advance_epoch()

        d = ctrl.to_dict()
        ctrl2 = UltrastabilityController.from_dict(d)

        assert ctrl2.current_epoch == ctrl.current_epoch
        assert ctrl2.frozen == ctrl.frozen
        assert ctrl2.history.total_adaptations == ctrl.history.total_adaptations
        assert len(ctrl2.history.epochs) == len(ctrl.history.epochs)

        # Parameter values match
        for name in ctrl.parameters.names:
            assert ctrl2.parameters.value(name) == ctrl.parameters.value(name)

    def test_bounded_adaptation(self):
        """Parameters never exceed constitutional bounds."""
        ctrl = create_controller()

        # Hammer the system with many epochs of stress
        for i in range(50):
            obs = EpochObservation(turns=100, budget_blocks=80, c_open=5)
            ctrl.observe_epoch(obs)
            decision = ctrl.consider_adaptation()
            if decision.verdict == AdaptationVerdict.ADAPT:
                ctrl.apply_adaptation(decision)
            elif decision.verdict in (AdaptationVerdict.ALERT, AdaptationVerdict.FREEZE):
                ctrl.unfreeze("test override")
            ctrl.advance_epoch()

        # Verify all parameters are within bounds
        for spec in ctrl.parameters.all_specs:
            assert spec.current >= spec.floor, f"{spec.name} below floor"
            assert spec.current <= spec.ceiling, f"{spec.name} above ceiling"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_empty_trigger_reasons(self):
        d = AdaptationDecision(verdict=AdaptationVerdict.HOLD, reason="stable")
        assert d.trigger_reasons == []

    def test_decision_to_dict(self):
        d = AdaptationDecision(
            verdict=AdaptationVerdict.ADAPT,
            parameter="x",
            current_value=1.0,
            proposed_value=2.0,
            delta=1.0,
            pathologies=[Pathology.OSCILLATION],
        )
        data = d.to_dict()
        assert data["verdict"] == "adapt"
        assert data["pathologies"] == ["oscillation"]

    def test_adaptation_record_negative_delta(self):
        r = AdaptationRecord(
            epoch_id=0, timestamp=datetime.now(timezone.utc),
            parameter="x", old_value=10, new_value=8,
            delta=-2, was_clamped=False, reason="test",
            direction=ParameterDirection.DECREASE,
        )
        assert r.direction == ParameterDirection.DECREASE

    def test_parameter_spec_zero_range(self):
        s = ParameterSpec(name="fixed", current=5.0, floor=5.0, ceiling=5.0, step=1.0)
        assert s.range == 0.0
        assert s.headroom_up == 0.0
        assert s.headroom_down == 0.0
        new_val, clamped = s.propose_change(1.0)
        assert new_val == 5.0
        assert clamped

    def test_epoch_observation_all_zero(self):
        obs = EpochObservation()
        obs.compute_rates()
        assert obs.block_rate == 0.0
        assert obs.acceptance_rate == 0.0
