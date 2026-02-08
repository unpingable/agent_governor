"""Tests for risk_function — scalar risk V from signals (AG2 Layer 2.1-B)."""

import json
import time
from pathlib import Path

import pytest

from governor.risk_function import (
    RiskLevel,
    PolicyAction,
    RiskSignal,
    RiskWeights,
    RiskComponents,
    RiskAssessment,
    ThresholdCrossing,
    RiskState,
    RiskStore,
    compute_risk,
    classify_risk,
    apply_risk_policy,
    assess_risk,
    extract_untrusted_signal,
    extract_evidence_gap,
    extract_scope_signal,
    extract_irreversibility_signal,
    make_risk_event,
    RISK_THRESHOLD_ELEVATED,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_CRITICAL,
    EVIDENCE_MULTIPLIER,
    IRREVERSIBLE_TOOLS,
    SIDE_EFFECT_TOOLS,
    DEMOTION_ORDER,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.ELEVATED.value == "elevated"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_count(self):
        assert len(RiskLevel) == 4


class TestPolicyAction:
    def test_values(self):
        assert PolicyAction.NONE.value == "none"
        assert PolicyAction.INCREASE_EVIDENCE.value == "increase_evidence"
        assert PolicyAction.FREEZE_IRREVERSIBLE.value == "freeze_irreversible"
        assert PolicyAction.DEMOTE_PROFILE.value == "demote_profile"
        assert PolicyAction.FREEZE_ALL_SIDE_EFFECTS.value == "freeze_all_side_effects"

    def test_count(self):
        assert len(PolicyAction) == 5


class TestRiskSignal:
    def test_values(self):
        assert len(RiskSignal) == 5
        assert RiskSignal.UNTRUSTED_BLOB.value == "untrusted_blob"


# ---------------------------------------------------------------------------
# RiskWeights
# ---------------------------------------------------------------------------

class TestRiskWeights:
    def test_defaults(self):
        w = RiskWeights()
        assert w.untrusted == 0.25
        assert w.scope == 0.15
        assert w.irreversibility == 0.25
        assert w.evidence == 0.20
        assert w.anomaly == 0.15

    def test_sum_to_one(self):
        w = RiskWeights()
        total = w.untrusted + w.scope + w.irreversibility + w.evidence + w.anomaly
        assert abs(total - 1.0) < 1e-9

    def test_to_dict(self):
        w = RiskWeights()
        d = w.to_dict()
        assert "untrusted" in d
        assert "anomaly" in d

    def test_roundtrip(self):
        w = RiskWeights(untrusted=0.3, scope=0.2)
        w2 = RiskWeights.from_dict(w.to_dict())
        assert w2.untrusted == 0.3
        assert w2.scope == 0.2


# ---------------------------------------------------------------------------
# RiskComponents
# ---------------------------------------------------------------------------

class TestRiskComponents:
    def test_defaults(self):
        c = RiskComponents()
        assert c.untrusted_blob_use == 0.0
        assert c.evidence_gap == 0.0

    def test_clamp_upper(self):
        c = RiskComponents(untrusted_blob_use=1.5)
        assert c.untrusted_blob_use == 1.0

    def test_clamp_lower(self):
        c = RiskComponents(anomaly_score=-0.5)
        assert c.anomaly_score == 0.0

    def test_to_dict(self):
        c = RiskComponents(evidence_gap=0.5)
        d = c.to_dict()
        assert d["evidence_gap"] == 0.5

    def test_roundtrip(self):
        c = RiskComponents(scope_size=0.7, anomaly_score=0.3)
        c2 = RiskComponents.from_dict(c.to_dict())
        assert c2.scope_size == 0.7
        assert c2.anomaly_score == 0.3


# ---------------------------------------------------------------------------
# compute_risk
# ---------------------------------------------------------------------------

class TestComputeRisk:
    def test_zero_components(self):
        c = RiskComponents()
        assert compute_risk(c) == 0.0

    def test_all_max(self):
        c = RiskComponents(
            untrusted_blob_use=1.0, scope_size=1.0,
            irreversibility_intent=1.0, evidence_gap=1.0, anomaly_score=1.0
        )
        v = compute_risk(c)
        assert abs(v - 1.0) < 1e-9

    def test_weighted(self):
        c = RiskComponents(untrusted_blob_use=1.0)
        w = RiskWeights(untrusted=0.5, scope=0.0, irreversibility=0.0, evidence=0.0, anomaly=0.0)
        assert abs(compute_risk(c, w) - 0.5) < 1e-9

    def test_clamped(self):
        # Even with extreme weights, result clamped to [0, 1]
        c = RiskComponents(untrusted_blob_use=1.0, evidence_gap=1.0)
        w = RiskWeights(untrusted=0.8, scope=0.0, irreversibility=0.0, evidence=0.8, anomaly=0.0)
        v = compute_risk(c, w)
        assert v <= 1.0

    def test_default_weights(self):
        c = RiskComponents(evidence_gap=1.0)
        v = compute_risk(c)
        assert abs(v - 0.20) < 1e-9


# ---------------------------------------------------------------------------
# classify_risk
# ---------------------------------------------------------------------------

class TestClassifyRisk:
    def test_low(self):
        assert classify_risk(0.0) == RiskLevel.LOW
        assert classify_risk(0.34) == RiskLevel.LOW

    def test_elevated(self):
        assert classify_risk(RISK_THRESHOLD_ELEVATED) == RiskLevel.ELEVATED
        assert classify_risk(0.5) == RiskLevel.ELEVATED

    def test_high(self):
        assert classify_risk(RISK_THRESHOLD_HIGH) == RiskLevel.HIGH
        assert classify_risk(0.7) == RiskLevel.HIGH

    def test_critical(self):
        assert classify_risk(RISK_THRESHOLD_CRITICAL) == RiskLevel.CRITICAL
        assert classify_risk(1.0) == RiskLevel.CRITICAL

    def test_threshold_ordering(self):
        assert RISK_THRESHOLD_ELEVATED < RISK_THRESHOLD_HIGH < RISK_THRESHOLD_CRITICAL


# ---------------------------------------------------------------------------
# apply_risk_policy
# ---------------------------------------------------------------------------

class TestApplyRiskPolicy:
    def test_low_no_action(self):
        actions, frozen, demoted, ev = apply_risk_policy(0.1)
        assert PolicyAction.NONE in actions
        assert len(frozen) == 0
        assert demoted == ""
        assert ev == 1.0

    def test_elevated_increases_evidence(self):
        actions, frozen, demoted, ev = apply_risk_policy(0.4)
        assert PolicyAction.INCREASE_EVIDENCE in actions
        assert ev == EVIDENCE_MULTIPLIER
        assert len(frozen) == 0

    def test_high_freezes_irreversible(self):
        actions, frozen, demoted, ev = apply_risk_policy(0.7)
        assert PolicyAction.FREEZE_IRREVERSIBLE in actions
        assert frozen == set(IRREVERSIBLE_TOOLS)
        assert ev == EVIDENCE_MULTIPLIER

    def test_critical_demotes_and_freezes_all(self):
        actions, frozen, demoted, ev = apply_risk_policy(0.9)
        assert PolicyAction.DEMOTE_PROFILE in actions
        assert PolicyAction.FREEZE_ALL_SIDE_EFFECTS in actions
        assert frozen == set(SIDE_EFFECT_TOOLS)
        assert demoted == "public"

    def test_explicit_level(self):
        actions, _, _, _ = apply_risk_policy(0.1, level=RiskLevel.HIGH)
        assert PolicyAction.FREEZE_IRREVERSIBLE in actions


# ---------------------------------------------------------------------------
# assess_risk
# ---------------------------------------------------------------------------

class TestAssessRisk:
    def test_low_risk(self):
        c = RiskComponents()
        a = assess_risk("run1", c)
        assert a.level == RiskLevel.LOW
        assert a.risk_value == 0.0

    def test_high_risk(self):
        c = RiskComponents(
            untrusted_blob_use=0.8, evidence_gap=0.9,
            irreversibility_intent=0.7, anomaly_score=0.5, scope_size=0.6,
        )
        a = assess_risk("run2", c)
        assert a.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert len(a.frozen_tools) > 0

    def test_custom_weights(self):
        c = RiskComponents(untrusted_blob_use=1.0)
        w = RiskWeights(untrusted=0.5, scope=0.0, irreversibility=0.0, evidence=0.0, anomaly=0.0)
        a = assess_risk("run3", c, w)
        assert abs(a.risk_value - 0.5) < 1e-9
        assert a.level == RiskLevel.ELEVATED

    def test_has_timestamp(self):
        a = assess_risk("r", RiskComponents())
        assert a.ts


# ---------------------------------------------------------------------------
# RiskAssessment serialization
# ---------------------------------------------------------------------------

class TestRiskAssessmentSerialization:
    def test_to_dict(self):
        a = assess_risk("run1", RiskComponents(evidence_gap=0.5))
        d = a.to_dict()
        assert d["run_id"] == "run1"
        assert "components" in d
        assert "weights" in d
        assert "risk_value" in d
        assert "level" in d

    def test_roundtrip(self):
        a = assess_risk("run1", RiskComponents(evidence_gap=0.5, anomaly_score=0.3))
        d = a.to_dict()
        a2 = RiskAssessment.from_dict(d)
        assert a2.run_id == a.run_id
        assert abs(a2.risk_value - a.risk_value) < 1e-6
        assert a2.level == a.level


# ---------------------------------------------------------------------------
# ThresholdCrossing
# ---------------------------------------------------------------------------

class TestThresholdCrossing:
    def test_create(self):
        c = ThresholdCrossing(
            run_id="r1", previous_level=RiskLevel.LOW,
            new_level=RiskLevel.ELEVATED, risk_value=0.4,
            actions=[PolicyAction.INCREASE_EVIDENCE],
        )
        assert c.previous_level == RiskLevel.LOW
        assert c.new_level == RiskLevel.ELEVATED
        assert c.ts

    def test_roundtrip(self):
        c = ThresholdCrossing(
            run_id="r1", previous_level=RiskLevel.LOW,
            new_level=RiskLevel.HIGH, risk_value=0.65,
            actions=[PolicyAction.FREEZE_IRREVERSIBLE],
        )
        d = c.to_dict()
        c2 = ThresholdCrossing.from_dict(d)
        assert c2.previous_level == RiskLevel.LOW
        assert c2.new_level == RiskLevel.HIGH
        assert c2.actions == [PolicyAction.FREEZE_IRREVERSIBLE]


# ---------------------------------------------------------------------------
# RiskState
# ---------------------------------------------------------------------------

class TestRiskState:
    def test_create(self):
        s = RiskState(run_id="r1")
        assert s.current_level == RiskLevel.LOW
        assert s.peak_risk == 0.0

    def test_update_no_crossing(self):
        s = RiskState(run_id="r1")
        a = assess_risk("r1", RiskComponents(evidence_gap=0.1))
        crossing = s.update(a)
        assert crossing is None
        assert s.current_risk == a.risk_value
        assert len(s.assessments) == 1

    def test_update_with_crossing(self):
        s = RiskState(run_id="r1")
        a = assess_risk("r1", RiskComponents(
            untrusted_blob_use=0.9, evidence_gap=0.9,
            irreversibility_intent=0.8, anomaly_score=0.7, scope_size=0.8
        ))
        crossing = s.update(a)
        assert crossing is not None
        assert crossing.previous_level == RiskLevel.LOW
        assert s.current_level != RiskLevel.LOW

    def test_peak_tracking(self):
        s = RiskState(run_id="r1")
        a1 = assess_risk("r1", RiskComponents(evidence_gap=0.8))
        s.update(a1)
        a2 = assess_risk("r1", RiskComponents(evidence_gap=0.1))
        s.update(a2)
        assert s.peak_risk >= a1.risk_value

    def test_frozen_tools_accumulate(self):
        s = RiskState(run_id="r1")
        a = assess_risk("r1", RiskComponents(
            untrusted_blob_use=0.9, evidence_gap=0.9,
            irreversibility_intent=0.9, anomaly_score=0.9, scope_size=0.9
        ))
        s.update(a)
        # Once frozen, stays frozen
        a2 = assess_risk("r1", RiskComponents())
        s.update(a2)
        assert len(s.frozen_tools) > 0

    def test_demotion_only_stricter(self):
        s = RiskState(run_id="r1", active_profile="operator")
        a = assess_risk("r1", RiskComponents(
            untrusted_blob_use=1.0, evidence_gap=1.0,
            irreversibility_intent=1.0, anomaly_score=1.0, scope_size=1.0
        ))
        s.update(a)
        assert s.active_profile == "public"
        # Can't go back to operator from low risk
        a2 = assess_risk("r1", RiskComponents())
        s.update(a2)
        assert s.active_profile == "public"

    def test_to_dict(self):
        s = RiskState(run_id="r1")
        d = s.to_dict()
        assert d["run_id"] == "r1"
        assert d["current_level"] == "low"

    def test_roundtrip(self):
        s = RiskState(run_id="r1", current_risk=0.5, peak_risk=0.5,
                      current_level=RiskLevel.ELEVATED)
        d = s.to_dict()
        s2 = RiskState.from_dict(d)
        assert s2.current_level == RiskLevel.ELEVATED


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

class TestSignalExtraction:
    def test_untrusted_zero(self):
        assert extract_untrusted_signal(0, 0, 10) == 0.0

    def test_untrusted_some(self):
        v = extract_untrusted_signal(3, 0, 10)
        assert abs(v - 0.3) < 1e-9

    def test_untrusted_quarantined_weighted(self):
        v = extract_untrusted_signal(0, 2, 10)
        assert abs(v - 0.4) < 1e-9

    def test_untrusted_no_outputs(self):
        assert extract_untrusted_signal(0, 0, 0) == 0.0

    def test_untrusted_clamped(self):
        v = extract_untrusted_signal(10, 10, 5)
        assert v <= 1.0

    def test_evidence_gap(self):
        assert abs(extract_evidence_gap(0.8) - 0.2) < 1e-9

    def test_evidence_gap_full(self):
        assert extract_evidence_gap(1.0) == 0.0

    def test_evidence_gap_none(self):
        assert extract_evidence_gap(0.0) == 1.0

    def test_scope_wildcard(self):
        assert extract_scope_signal(0, 0, True) == 0.8

    def test_scope_ratio(self):
        v = extract_scope_signal(5, 10, False)
        assert abs(v - 0.5) < 1e-9

    def test_scope_zero(self):
        assert extract_scope_signal(0, 0, False) == 0.0

    def test_irreversibility_zero(self):
        assert extract_irreversibility_signal(0, 0, 0) == 0.0

    def test_irreversibility_s3(self):
        v = extract_irreversibility_signal(0, 2, 0)
        assert v > 0.0

    def test_irreversibility_clamped(self):
        v = extract_irreversibility_signal(100, 100, 100)
        assert v <= 1.0


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestRiskStore:
    def test_create(self, tmp_path):
        store = RiskStore(governor_dir=tmp_path)
        assert store.risk_dir == tmp_path / "risk"

    def test_save_load(self, tmp_path):
        store = RiskStore(governor_dir=tmp_path)
        s = RiskState(run_id="r1")
        a = assess_risk("r1", RiskComponents(evidence_gap=0.5))
        s.update(a)
        store.save(s)
        s2 = store.load("r1")
        assert s2 is not None
        assert s2.run_id == "r1"
        assert abs(s2.current_risk - s.current_risk) < 1e-6
        assert len(s2.assessments) == 1

    def test_list_runs(self, tmp_path):
        store = RiskStore(governor_dir=tmp_path)
        s1 = RiskState(run_id="a1")
        s2 = RiskState(run_id="b2")
        store.save(s1)
        store.save(s2)
        runs = store.list_runs()
        assert "a1" in runs
        assert "b2" in runs

    def test_load_missing(self, tmp_path):
        store = RiskStore(governor_dir=tmp_path)
        assert store.load("nonexistent") is None

    def test_list_empty(self, tmp_path):
        store = RiskStore(governor_dir=tmp_path)
        assert store.list_runs() == []

    def test_default_dir(self):
        store = RiskStore()
        assert store.risk_dir == Path(".governor") / "risk"


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        e = make_risk_event("risk_update", "r1", {"risk": 0.5})
        assert e["type"] == "risk_function"
        assert e["action"] == "risk_update"
        assert e["run_id"] == "r1"
        assert e["ts"]

    def test_minimal(self):
        e = make_risk_event("assess")
        assert e["details"] == {}


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_assessment_schema(self):
        a = assess_risk("r1", RiskComponents(evidence_gap=0.5))
        d = a.to_dict()
        required = {"run_id", "components", "weights", "risk_value", "level",
                     "actions_taken", "frozen_tools", "demoted_to",
                     "evidence_multiplier", "ts"}
        assert required <= set(d.keys())

    def test_crossing_schema(self):
        c = ThresholdCrossing(
            run_id="r1", previous_level=RiskLevel.LOW,
            new_level=RiskLevel.HIGH, risk_value=0.65,
            actions=[PolicyAction.FREEZE_IRREVERSIBLE],
        )
        d = c.to_dict()
        required = {"run_id", "previous_level", "new_level", "risk_value", "actions", "ts"}
        assert required <= set(d.keys())

    def test_state_schema(self):
        s = RiskState(run_id="r1")
        d = s.to_dict()
        required = {"run_id", "current_level", "current_risk", "frozen_tools",
                     "active_profile", "evidence_multiplier", "peak_risk",
                     "assessment_count", "crossing_count"}
        assert required <= set(d.keys())

    def test_event_schema(self):
        e = make_risk_event("update", "r1")
        required = {"type", "action", "run_id", "details", "ts"}
        assert required <= set(e.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Full risk lifecycle: assess → update state → cross threshold → store."""
        store = RiskStore(governor_dir=tmp_path)
        state = RiskState(run_id="lifecycle1")

        # Low risk
        a1 = assess_risk("lifecycle1", RiskComponents(evidence_gap=0.1))
        c1 = state.update(a1)
        assert c1 is None
        assert state.current_level == RiskLevel.LOW

        # Elevated risk
        a2 = assess_risk("lifecycle1", RiskComponents(
            evidence_gap=0.9, anomaly_score=0.8, scope_size=0.7, untrusted_blob_use=0.5
        ))
        c2 = state.update(a2)
        assert c2 is not None
        assert state.current_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)

        # Critical risk
        a3 = assess_risk("lifecycle1", RiskComponents(
            untrusted_blob_use=1.0, evidence_gap=1.0,
            irreversibility_intent=1.0, anomaly_score=1.0, scope_size=1.0
        ))
        c3 = state.update(a3)
        assert state.current_level == RiskLevel.CRITICAL
        assert state.active_profile == "public"
        assert len(state.frozen_tools) > 0

        # Persist and reload
        store.save(state)
        loaded = store.load("lifecycle1")
        assert loaded is not None
        assert loaded.current_level == RiskLevel.CRITICAL
        assert loaded.peak_risk == state.peak_risk

    def test_signal_to_assessment(self):
        """Extract signals → build components → assess."""
        untrusted = extract_untrusted_signal(3, 1, 10)
        gap = extract_evidence_gap(0.6)
        scope = extract_scope_signal(5, 10, False)
        irrev = extract_irreversibility_signal(1, 1, 2)

        c = RiskComponents(
            untrusted_blob_use=untrusted,
            scope_size=scope,
            irreversibility_intent=irrev,
            evidence_gap=gap,
            anomaly_score=0.0,
        )
        a = assess_risk("sig_test", c)
        assert a.risk_value > 0.0
        assert a.level in (RiskLevel.LOW, RiskLevel.ELEVATED)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_threshold_boundaries(self):
        # Exactly at threshold
        assert classify_risk(RISK_THRESHOLD_ELEVATED) == RiskLevel.ELEVATED
        assert classify_risk(RISK_THRESHOLD_HIGH) == RiskLevel.HIGH
        assert classify_risk(RISK_THRESHOLD_CRITICAL) == RiskLevel.CRITICAL

    def test_just_below_threshold(self):
        assert classify_risk(RISK_THRESHOLD_ELEVATED - 0.001) == RiskLevel.LOW
        assert classify_risk(RISK_THRESHOLD_HIGH - 0.001) == RiskLevel.ELEVATED
        assert classify_risk(RISK_THRESHOLD_CRITICAL - 0.001) == RiskLevel.HIGH

    def test_demotion_order(self):
        assert DEMOTION_ORDER[0] == "public"
        assert DEMOTION_ORDER[-1] == "operator"

    def test_constants(self):
        assert len(IRREVERSIBLE_TOOLS) > 0
        assert len(SIDE_EFFECT_TOOLS) >= len(IRREVERSIBLE_TOOLS)
        assert EVIDENCE_MULTIPLIER > 1.0
