# SPDX-License-Identifier: Apache-2.0
"""Tests for hysteresis — anti-churn mode transitions (AG2 Layer 2.1-C)."""

import json
import time
from pathlib import Path

import pytest

from governor.hysteresis import (
    HysteresisMode,
    TransitionVerdict,
    ReplanVerdict,
    RegressionSeverity,
    ModeTransitionResult,
    ReplanTracker,
    RegressionAlert,
    HysteresisState,
    compute_plan_hash,
    check_mode_transition,
    check_replan,
    detect_regressions,
    classify_regression_severity,
    check_invariant_k,
    make_hysteresis_event,
    make_transition_event,
    make_replan_event,
    make_regression_event,
    HysteresisStore,
    A_LOW,
    A_HIGH,
    DEFAULT_MAX_REPLANS,
    DEFAULT_REPLAN_WINDOW,
    REGRESSION_THRESHOLD_WARN,
    REGRESSION_THRESHOLD_BLOCK,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_modes(self):
        assert len(HysteresisMode) == 2
        assert HysteresisMode.NORMAL.value == "NORMAL"
        assert HysteresisMode.STRICT.value == "STRICT"

    def test_transition_verdicts(self):
        assert len(TransitionVerdict) == 3

    def test_replan_verdicts(self):
        assert len(ReplanVerdict) == 3

    def test_regression_severity(self):
        assert len(RegressionSeverity) == 3


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_thresholds_ordered(self):
        assert A_LOW < A_HIGH

    def test_hysteresis_band_exists(self):
        assert A_HIGH - A_LOW > 0.1  # Meaningful band

    def test_max_replans(self):
        assert DEFAULT_MAX_REPLANS == 3

    def test_replan_window(self):
        assert DEFAULT_REPLAN_WINDOW > 0

    def test_regression_thresholds_ordered(self):
        assert REGRESSION_THRESHOLD_WARN < REGRESSION_THRESHOLD_BLOCK


# ---------------------------------------------------------------------------
# ModeTransitionResult
# ---------------------------------------------------------------------------

class TestModeTransitionResult:
    def test_create(self):
        r = ModeTransitionResult(
            verdict=TransitionVerdict.TRANSITION,
            current_mode=HysteresisMode.NORMAL,
            target_mode=HysteresisMode.STRICT,
            admissibility=0.3,
            threshold=A_LOW,
        )
        assert r.verdict == TransitionVerdict.TRANSITION

    def test_roundtrip(self):
        r = ModeTransitionResult(
            verdict=TransitionVerdict.SUPPRESSED,
            current_mode=HysteresisMode.STRICT,
            target_mode=HysteresisMode.NORMAL,
            admissibility=0.6,
            threshold=A_HIGH,
            reason="hysteresis_band",
        )
        d = r.to_dict()
        r2 = ModeTransitionResult.from_dict(d)
        assert r2.verdict == TransitionVerdict.SUPPRESSED
        assert r2.admissibility == 0.6
        assert r2.reason == "hysteresis_band"

    def test_schema(self):
        r = ModeTransitionResult(
            TransitionVerdict.HOLD, HysteresisMode.NORMAL,
            HysteresisMode.NORMAL, 0.5, A_LOW,
        )
        d = r.to_dict()
        required = {"verdict", "current_mode", "target_mode", "admissibility", "threshold", "reason"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# ReplanTracker
# ---------------------------------------------------------------------------

class TestReplanTracker:
    def test_default(self):
        t = ReplanTracker()
        assert t.max_replans == DEFAULT_MAX_REPLANS
        assert t.replan_count == 0
        assert t.remaining() == DEFAULT_MAX_REPLANS

    def test_allow_replan(self):
        t = ReplanTracker()
        assert t.allow_replan("hash1") == ReplanVerdict.ALLOWED

    def test_deny_duplicate(self):
        t = ReplanTracker()
        t.record_replan("hash1")
        assert t.allow_replan("hash1") == ReplanVerdict.DENIED_DUPLICATE

    def test_deny_budget(self):
        t = ReplanTracker(max_replans=2)
        t.record_replan("a")
        t.record_replan("b")
        assert t.allow_replan("c") == ReplanVerdict.DENIED_BUDGET

    def test_remaining_decrements(self):
        t = ReplanTracker(max_replans=3)
        t.record_replan("a")
        assert t.remaining() == 2
        t.record_replan("b")
        assert t.remaining() == 1

    def test_reset(self):
        t = ReplanTracker(max_replans=2)
        t.record_replan("a")
        t.record_replan("b")
        assert t.remaining() == 0
        t.reset()
        assert t.remaining() == 2
        assert t.last_plan_hash == ""

    def test_history(self):
        t = ReplanTracker()
        t.record_replan("x")
        t.record_replan("y")
        assert t.history == ["x", "y"]

    def test_roundtrip(self):
        t = ReplanTracker(max_replans=5)
        t.record_replan("abc")
        d = t.to_dict()
        t2 = ReplanTracker.from_dict(d)
        assert t2.max_replans == 5
        assert t2.replan_count == 1
        assert t2.last_plan_hash == "abc"

    def test_window_reset(self):
        t = ReplanTracker(max_replans=2, window_seconds=0.01)
        t.record_replan("a")
        t.record_replan("b")
        assert t.remaining() == 0
        time.sleep(0.02)
        assert t.remaining() == 2  # Window expired


# ---------------------------------------------------------------------------
# RegressionAlert
# ---------------------------------------------------------------------------

class TestRegressionAlert:
    def test_create(self):
        a = RegressionAlert(
            claim_id="c1", was_status="verified",
            now_status="unknown", severity=RegressionSeverity.LOW,
        )
        assert a.claim_id == "c1"
        assert a.ts  # Has timestamp

    def test_roundtrip(self):
        a = RegressionAlert("c1", "verified", "missing", RegressionSeverity.HIGH)
        d = a.to_dict()
        a2 = RegressionAlert.from_dict(d)
        assert a2.claim_id == "c1"
        assert a2.severity == RegressionSeverity.HIGH

    def test_schema(self):
        a = RegressionAlert("c1", "verified", "unknown", RegressionSeverity.LOW)
        d = a.to_dict()
        required = {"claim_id", "was_status", "now_status", "severity", "ts"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# HysteresisState
# ---------------------------------------------------------------------------

class TestHysteresisState:
    def test_default(self):
        s = HysteresisState()
        assert s.mode == HysteresisMode.NORMAL
        assert s.transition_count == 0
        assert s.suppression_count == 0

    def test_record_transition(self):
        s = HysteresisState()
        result = ModeTransitionResult(
            TransitionVerdict.TRANSITION, HysteresisMode.NORMAL,
            HysteresisMode.STRICT, 0.3, A_LOW,
        )
        s.record_transition(result)
        assert s.mode == HysteresisMode.STRICT
        assert s.transition_count == 1

    def test_record_suppression(self):
        s = HysteresisState(mode=HysteresisMode.STRICT)
        result = ModeTransitionResult(
            TransitionVerdict.SUPPRESSED, HysteresisMode.STRICT,
            HysteresisMode.NORMAL, 0.6, A_HIGH, "hysteresis_band",
        )
        s.record_transition(result)
        assert s.mode == HysteresisMode.STRICT  # Didn't change
        assert s.suppression_count == 1

    def test_record_regressions(self):
        s = HysteresisState()
        alerts = [
            RegressionAlert("c1", "verified", "unknown", RegressionSeverity.LOW),
            RegressionAlert("c2", "verified", "missing", RegressionSeverity.LOW),
        ]
        s.record_regressions(alerts)
        assert s.regression_count == 2

    def test_roundtrip(self):
        s = HysteresisState(
            mode=HysteresisMode.STRICT,
            transition_count=3,
            suppression_count=2,
        )
        d = s.to_dict()
        s2 = HysteresisState.from_dict(d)
        assert s2.mode == HysteresisMode.STRICT
        assert s2.transition_count == 3

    def test_schema(self):
        s = HysteresisState()
        d = s.to_dict()
        required = {"mode", "replan_tracker", "transition_count",
                     "suppression_count", "regression_count", "last_admissibility"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# compute_plan_hash
# ---------------------------------------------------------------------------

class TestPlanHash:
    def test_deterministic(self):
        h1 = compute_plan_hash("plan A")
        h2 = compute_plan_hash("plan A")
        assert h1 == h2

    def test_different_plans(self):
        h1 = compute_plan_hash("plan A")
        h2 = compute_plan_hash("plan B")
        assert h1 != h2

    def test_length(self):
        h = compute_plan_hash("test")
        assert len(h) == 16


# ---------------------------------------------------------------------------
# check_mode_transition
# ---------------------------------------------------------------------------

class TestCheckModeTransition:
    def test_normal_stays_normal_above_band(self):
        r = check_mode_transition(HysteresisMode.NORMAL, 0.9)
        assert r.verdict == TransitionVerdict.HOLD
        assert r.current_mode == HysteresisMode.NORMAL

    def test_normal_to_strict_below_a_low(self):
        r = check_mode_transition(HysteresisMode.NORMAL, 0.2)
        assert r.verdict == TransitionVerdict.TRANSITION
        assert r.target_mode == HysteresisMode.STRICT

    def test_normal_holds_in_band(self):
        r = check_mode_transition(HysteresisMode.NORMAL, 0.6)
        assert r.verdict == TransitionVerdict.HOLD

    def test_strict_to_normal_above_a_high(self):
        r = check_mode_transition(HysteresisMode.STRICT, 0.9)
        assert r.verdict == TransitionVerdict.TRANSITION
        assert r.target_mode == HysteresisMode.NORMAL

    def test_strict_suppressed_in_band(self):
        r = check_mode_transition(HysteresisMode.STRICT, 0.6)
        assert r.verdict == TransitionVerdict.SUPPRESSED
        assert r.reason == "hysteresis_band"

    def test_strict_holds_below_a_low(self):
        r = check_mode_transition(HysteresisMode.STRICT, 0.2)
        assert r.verdict == TransitionVerdict.HOLD

    def test_custom_thresholds(self):
        r = check_mode_transition(
            HysteresisMode.NORMAL, 0.45, a_low=0.5, a_high=0.9,
        )
        assert r.verdict == TransitionVerdict.TRANSITION

    def test_at_a_low_boundary(self):
        # Exactly at A_LOW — not below, so no transition
        r = check_mode_transition(HysteresisMode.NORMAL, A_LOW)
        assert r.verdict == TransitionVerdict.HOLD

    def test_at_a_high_boundary(self):
        # Exactly at A_HIGH — not above, so suppressed in strict
        r = check_mode_transition(HysteresisMode.STRICT, A_HIGH)
        assert r.verdict == TransitionVerdict.SUPPRESSED


# ---------------------------------------------------------------------------
# check_replan
# ---------------------------------------------------------------------------

class TestCheckReplan:
    def test_first_replan_allowed(self):
        t = ReplanTracker()
        verdict, h = check_replan(t, "plan A")
        assert verdict == ReplanVerdict.ALLOWED
        assert t.replan_count == 1

    def test_duplicate_denied(self):
        t = ReplanTracker()
        check_replan(t, "plan A")
        verdict, _ = check_replan(t, "plan A")
        assert verdict == ReplanVerdict.DENIED_DUPLICATE

    def test_budget_exhausted(self):
        t = ReplanTracker(max_replans=1)
        check_replan(t, "plan A")
        verdict, _ = check_replan(t, "plan B")
        assert verdict == ReplanVerdict.DENIED_BUDGET

    def test_no_auto_record(self):
        t = ReplanTracker()
        verdict, h = check_replan(t, "plan A", auto_record=False)
        assert verdict == ReplanVerdict.ALLOWED
        assert t.replan_count == 0  # Not recorded


# ---------------------------------------------------------------------------
# detect_regressions
# ---------------------------------------------------------------------------

class TestDetectRegressions:
    def test_no_regressions(self):
        old = [{"id": "c1", "status": "verified"}]
        new = [{"id": "c1", "status": "verified"}]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 0

    def test_single_regression(self):
        old = [{"id": "c1", "status": "verified"}]
        new = [{"id": "c1", "status": "unknown"}]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 1
        assert alerts[0].claim_id == "c1"
        assert alerts[0].was_status == "verified"
        assert alerts[0].now_status == "unknown"

    def test_missing_claim(self):
        old = [{"id": "c1", "status": "verified"}]
        new = []
        alerts = detect_regressions(old, new)
        assert len(alerts) == 1
        assert alerts[0].now_status == "missing"

    def test_multiple_regressions(self):
        old = [
            {"id": "c1", "status": "verified"},
            {"id": "c2", "status": "verified"},
            {"id": "c3", "status": "verified"},
        ]
        new = [
            {"id": "c1", "status": "unknown"},
            {"id": "c2", "status": "unknown"},
            {"id": "c3", "status": "verified"},
        ]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 2

    def test_no_regression_if_never_verified(self):
        old = [{"id": "c1", "status": "pending"}]
        new = [{"id": "c1", "status": "unknown"}]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 0

    def test_supported_status(self):
        old = [{"id": "c1", "status": "SUPPORTED"}]
        new = [{"id": "c1", "status": "CONTESTED"}]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 1

    def test_empty_inputs(self):
        assert detect_regressions([], []) == []


# ---------------------------------------------------------------------------
# classify_regression_severity
# ---------------------------------------------------------------------------

class TestClassifyRegressionSeverity:
    def test_zero(self):
        assert classify_regression_severity(0) == RegressionSeverity.LOW

    def test_warn(self):
        assert classify_regression_severity(REGRESSION_THRESHOLD_WARN) == RegressionSeverity.MODERATE

    def test_block(self):
        assert classify_regression_severity(REGRESSION_THRESHOLD_BLOCK) == RegressionSeverity.HIGH


# ---------------------------------------------------------------------------
# Invariant K
# ---------------------------------------------------------------------------

class TestInvariantK:
    def test_normal_above_band(self):
        s = HysteresisState()
        ok, reason = check_invariant_k(s, 0.9)
        assert ok
        assert "hold" in reason

    def test_strict_in_band(self):
        s = HysteresisState(mode=HysteresisMode.STRICT)
        ok, reason = check_invariant_k(s, 0.6)
        assert ok
        assert "suppressed" in reason

    def test_transition(self):
        s = HysteresisState()
        ok, reason = check_invariant_k(s, 0.2)
        assert ok
        assert "allowed" in reason


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_hysteresis_event(self):
        e = make_hysteresis_event("test", "r1", {"x": 1})
        assert e["type"] == "hysteresis"
        assert e["action"] == "test"
        assert e["ts"]

    def test_minimal_event(self):
        e = make_hysteresis_event("scan")
        assert e["details"] == {}

    def test_transition_event(self):
        r = ModeTransitionResult(
            TransitionVerdict.SUPPRESSED, HysteresisMode.STRICT,
            HysteresisMode.NORMAL, 0.6, A_HIGH, "hysteresis_band",
        )
        e = make_transition_event(r)
        assert e["action"] == "mode_transition_suppressed"

    def test_transition_event_allowed(self):
        r = ModeTransitionResult(
            TransitionVerdict.TRANSITION, HysteresisMode.NORMAL,
            HysteresisMode.STRICT, 0.2, A_LOW,
        )
        e = make_transition_event(r)
        assert e["action"] == "mode_transition"

    def test_replan_event_allowed(self):
        t = ReplanTracker()
        e = make_replan_event(ReplanVerdict.ALLOWED, "abc", t)
        assert e["action"] == "replan_allowed"

    def test_replan_event_denied(self):
        t = ReplanTracker(max_replans=0, replan_count=0)
        e = make_replan_event(ReplanVerdict.DENIED_BUDGET, "abc", t)
        assert e["action"] == "replan_denied"
        assert e["details"]["reason"] == "budget_exhausted"

    def test_replan_event_duplicate(self):
        t = ReplanTracker()
        e = make_replan_event(ReplanVerdict.DENIED_DUPLICATE, "abc", t)
        assert e["details"]["reason"] == "duplicate"

    def test_regression_event(self):
        alerts = [
            RegressionAlert("c1", "verified", "unknown", RegressionSeverity.LOW),
        ]
        e = make_regression_event(alerts)
        assert e["action"] == "verification_regression"
        assert e["details"]["count"] == 1


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_load(self, tmp_path):
        store = HysteresisStore(governor_dir=tmp_path)
        state = HysteresisState(mode=HysteresisMode.STRICT, transition_count=5)
        store.save(state, "run1")
        loaded = store.load("run1")
        assert loaded is not None
        assert loaded.mode == HysteresisMode.STRICT
        assert loaded.transition_count == 5

    def test_load_missing(self, tmp_path):
        store = HysteresisStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_list_runs(self, tmp_path):
        store = HysteresisStore(governor_dir=tmp_path)
        store.save(HysteresisState(), "a")
        store.save(HysteresisState(), "b")
        runs = store.list_runs()
        assert "a" in runs
        assert "b" in runs

    def test_default_dir(self):
        store = HysteresisStore()
        assert store.hysteresis_dir == Path(".governor") / "hysteresis"

    def test_default_run_id(self, tmp_path):
        store = HysteresisStore(governor_dir=tmp_path)
        store.save(HysteresisState())
        loaded = store.load()
        assert loaded is not None


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_transition_result_schema(self):
        r = check_mode_transition(HysteresisMode.NORMAL, 0.5)
        d = r.to_dict()
        required = {"verdict", "current_mode", "target_mode", "admissibility", "threshold", "reason"}
        assert required <= set(d.keys())

    def test_state_schema(self):
        s = HysteresisState()
        d = s.to_dict()
        required = {"mode", "replan_tracker", "transition_count",
                     "suppression_count", "regression_count", "last_admissibility"}
        assert required <= set(d.keys())

    def test_alert_schema(self):
        a = RegressionAlert("c1", "verified", "unknown", RegressionSeverity.LOW)
        d = a.to_dict()
        required = {"claim_id", "was_status", "now_status", "severity", "ts"}
        assert required <= set(d.keys())

    def test_tracker_schema(self):
        t = ReplanTracker()
        d = t.to_dict()
        required = {"max_replans", "replan_count", "last_plan_hash",
                     "window_start", "window_seconds", "history"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        store = HysteresisStore(governor_dir=tmp_path)
        state = HysteresisState()

        # Start in normal mode with good admissibility
        r1 = check_mode_transition(state.mode, 0.8)
        assert r1.verdict == TransitionVerdict.HOLD
        state.record_transition(r1)

        # Admissibility drops below A_LOW → enter STRICT
        r2 = check_mode_transition(state.mode, 0.2)
        assert r2.verdict == TransitionVerdict.TRANSITION
        state.record_transition(r2)
        assert state.mode == HysteresisMode.STRICT

        # Admissibility recovers to band but can't leave STRICT
        r3 = check_mode_transition(state.mode, 0.6)
        assert r3.verdict == TransitionVerdict.SUPPRESSED
        state.record_transition(r3)
        assert state.mode == HysteresisMode.STRICT

        # Admissibility exceeds A_HIGH → leave STRICT
        r4 = check_mode_transition(state.mode, 0.9)
        assert r4.verdict == TransitionVerdict.TRANSITION
        state.record_transition(r4)
        assert state.mode == HysteresisMode.NORMAL

        assert state.transition_count == 2
        assert state.suppression_count == 1

        # Replan tracking
        verdict, _ = check_replan(state.replan_tracker, "plan 1")
        assert verdict == ReplanVerdict.ALLOWED
        verdict, _ = check_replan(state.replan_tracker, "plan 2")
        assert verdict == ReplanVerdict.ALLOWED
        verdict, _ = check_replan(state.replan_tracker, "plan 3")
        assert verdict == ReplanVerdict.ALLOWED
        verdict, _ = check_replan(state.replan_tracker, "plan 4")
        assert verdict == ReplanVerdict.DENIED_BUDGET

        # Regression detection
        old = [{"id": "c1", "status": "verified"}, {"id": "c2", "status": "verified"}]
        new = [{"id": "c1", "status": "unknown"}, {"id": "c2", "status": "verified"}]
        alerts = detect_regressions(old, new)
        state.record_regressions(alerts)
        assert state.regression_count == 1

        # Persist
        store.save(state, "lifecycle1")
        loaded = store.load("lifecycle1")
        assert loaded is not None
        assert loaded.transition_count == 2
        assert loaded.regression_count == 1

    def test_replan_with_hash(self):
        tracker = ReplanTracker(max_replans=3)
        h1 = compute_plan_hash("implement login feature")
        h2 = compute_plan_hash("implement auth feature")
        assert h1 != h2

        verdict = tracker.allow_replan(h1)
        assert verdict == ReplanVerdict.ALLOWED
        tracker.record_replan(h1)

        verdict = tracker.allow_replan(h1)
        assert verdict == ReplanVerdict.DENIED_DUPLICATE

        verdict = tracker.allow_replan(h2)
        assert verdict == ReplanVerdict.ALLOWED


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_admissibility(self):
        r = check_mode_transition(HysteresisMode.NORMAL, 0.0)
        assert r.verdict == TransitionVerdict.TRANSITION

    def test_one_admissibility(self):
        r = check_mode_transition(HysteresisMode.STRICT, 1.0)
        assert r.verdict == TransitionVerdict.TRANSITION

    def test_empty_plan_hash(self):
        h = compute_plan_hash("")
        assert len(h) == 16

    def test_replan_tracker_zero_max(self):
        t = ReplanTracker(max_replans=0)
        assert t.allow_replan("anything") == ReplanVerdict.DENIED_BUDGET

    def test_regression_large_set(self):
        old = [{"id": f"c{i}", "status": "verified"} for i in range(20)]
        new = [{"id": f"c{i}", "status": "unknown"} for i in range(20)]
        alerts = detect_regressions(old, new)
        assert len(alerts) == 20
        # Last alerts should be HIGH severity
        assert alerts[-1].severity == RegressionSeverity.HIGH
