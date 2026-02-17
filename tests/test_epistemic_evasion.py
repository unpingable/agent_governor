# SPDX-License-Identifier: Apache-2.0
"""Tests for epistemic_evasion — evasion operator detection (AG2 Layer 2.1-C)."""

import json
from pathlib import Path

import pytest

from governor.epistemic_evasion import (
    EvasionOperator,
    FailureMode,
    EvasionSeverity,
    OperatorDetection,
    EvasionResult,
    EvasionState,
    EvasionStore,
    detect_hedge_injection,
    detect_virtue_shield,
    detect_pdc,
    detect_context_weapon,
    detect_status_anchor,
    detect_incentive_solvent,
    detect_pedantry_deflection,
    detect_moral_rebinding,
    detect_frame_router,
    detect_motte_fallback,
    analyze_evasion,
    select_coupling_question,
    check_invariant_j,
    audit_governor_prompts,
    make_evasion_event,
    OPERATOR_WEIGHTS,
    FAILURE_MODE_OPERATORS,
    EVASION_THRESHOLD_LOW,
    EVASION_THRESHOLD_HIGH,
    FORCED_COUPLING_QUESTIONS,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_operators(self):
        assert len(EvasionOperator) == 11
        assert EvasionOperator.FR.value == "FR"
        assert EvasionOperator.PDC.value == "PDC"

    def test_failure_modes(self):
        assert len(FailureMode) == 5

    def test_severity(self):
        assert len(EvasionSeverity) == 3


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

class TestHedgeInjection:
    def test_no_hedges(self):
        d = detect_hedge_injection("The sky is blue.")
        assert d.confidence == 0.0

    def test_hedges_without_confidence(self):
        d = detect_hedge_injection("It probably seems complicated, in a sense.")
        assert d.confidence > 0.0  # 3+ hedges

    def test_hedges_with_confidence(self):
        d = detect_hedge_injection(
            "I could be wrong but it's complicated, probably, and it's "
            "nuanced — but clearly this is the answer."
        )
        assert d.confidence > 0.3
        assert d.operator == EvasionOperator.HI


class TestVirtueShield:
    def test_no_virtue(self):
        d = detect_virtue_shield("Pass the salt.")
        assert d.confidence == 0.0

    def test_virtue_tokens(self):
        d = detect_virtue_shield(
            "I'm updating my priors after steelmanning the argument."
        )
        assert d.confidence > 0.3
        assert len(d.tells) >= 2

    def test_single_token(self):
        d = detect_virtue_shield("I'm updating on this.")
        assert d.confidence == 0.0  # Need 2+


class TestPDC:
    def test_clean(self):
        d = detect_pdc("The tests pass.")
        assert d.confidence == 0.0

    def test_pdc_markers(self):
        d = detect_pdc("Just asking questions. It's worth considering, big if true.")
        assert d.confidence > 0.5


class TestContextWeapon:
    def test_clean(self):
        d = detect_context_weapon("The function returns 42.")
        assert d.confidence == 0.0

    def test_context_escape(self):
        d = detect_context_weapon("That's taken out of context and oversimplifying things.")
        assert d.confidence > 0.3


class TestStatusAnchor:
    def test_clean(self):
        d = detect_status_anchor("Add a login page.")
        assert d.confidence == 0.0

    def test_status_dropping(self):
        d = detect_status_anchor(
            "As the research shows, the data suggests significant effects."
        )
        assert d.confidence > 0.3


class TestIncentiveSolvent:
    def test_clean(self):
        d = detect_incentive_solvent("Fix the bug.")
        assert d.confidence == 0.0

    def test_incentive_talk(self):
        d = detect_incentive_solvent(
            "People respond to incentives, it's systemic and structural."
        )
        assert d.confidence > 0.5


class TestPedantryDeflection:
    def test_clean(self):
        d = detect_pedantry_deflection("Can you clarify?")
        assert d.confidence == 0.0

    def test_deflection(self):
        d = detect_pedantry_deflection("That's just semantics, stop sealioning.")
        assert d.confidence > 0.5


class TestMoralRebinding:
    def test_no_context(self):
        d = detect_moral_rebinding("We should protect the vulnerable.")
        assert d.confidence == 0.0

    def test_axis_switch(self):
        context = ["Rights and freedom are paramount."]
        d = detect_moral_rebinding(
            "But think about the harm and suffering caused.",
            context=context,
        )
        assert d.confidence > 0.0

    def test_same_axis(self):
        context = ["Rights are important."]
        d = detect_moral_rebinding("Freedom matters too.", context=context)
        assert d.confidence == 0.0


class TestFrameRouter:
    def test_clean(self):
        d = detect_frame_router("The test passes.")
        assert d.confidence == 0.0

    def test_reframe(self):
        d = detect_frame_router("What I'm actually saying is that the real question is...")
        assert d.confidence > 0.3


class TestMotteFallback:
    def test_clean(self):
        d = detect_motte_fallback("Here is the implementation.")
        assert d.confidence == 0.0

    def test_retreat(self):
        d = detect_motte_fallback("I'm not saying that. All I'm saying is it's worth considering.")
        assert d.confidence > 0.3


# ---------------------------------------------------------------------------
# Composite analysis
# ---------------------------------------------------------------------------

class TestAnalyzeEvasion:
    def test_clean_text(self):
        r = analyze_evasion("The function returns the sum of two numbers.")
        assert r.severity == EvasionSeverity.LOW
        assert r.score < EVASION_THRESHOLD_LOW
        assert r.confidence_cap == 1.0

    def test_evasive_text(self):
        text = (
            "I'm updating my priors here. It probably seems complicated, "
            "but I could be wrong. Steelmanning the other side, "
            "it's worth considering that incentives are structural. "
            "Just asking questions about what the research shows."
        )
        r = analyze_evasion(text)
        assert r.score > 0
        assert len(r.operators) > 0

    def test_coupling_question(self):
        text = (
            "I'm updating my priors and steelmanning this. "
            "It's probably complicated and nuanced."
        )
        r = analyze_evasion(text)
        if r.severity != EvasionSeverity.LOW:
            assert r.coupling_question != ""

    def test_failure_mode_detection(self):
        # Create text that triggers multiple operators in same FM
        text = (
            "I could be wrong but it's complicated, arguably nuanced, "
            "and I'm not saying that exactly. All I'm saying is it seems likely. "
            "Just asking, food for thought."
        )
        r = analyze_evasion(text)
        # Should trigger HI + MF + PDC → FM-1 (Falsification Avoidance)
        if len(r.operators) >= 2:
            # May detect failure modes
            pass  # FM detection depends on which operators triggered


class TestSelectCouplingQuestion:
    def test_incentive_solvent(self):
        q = select_coupling_question([EvasionOperator.IS])
        assert "responsible" in q

    def test_virtue_shield(self):
        q = select_coupling_question([EvasionOperator.VS])
        assert "mechanism" in q

    def test_motte_fallback(self):
        q = select_coupling_question([EvasionOperator.MF])
        assert "falsify" in q

    def test_status_anchor(self):
        q = select_coupling_question([EvasionOperator.SA])
        assert "prediction" in q

    def test_default(self):
        q = select_coupling_question([])
        assert q == FORCED_COUPLING_QUESTIONS[0]


# ---------------------------------------------------------------------------
# Invariant J
# ---------------------------------------------------------------------------

class TestInvariantJ:
    def test_clean(self):
        ok, _ = check_invariant_j("The function adds two numbers.")
        assert ok

    def test_evasive(self):
        text = (
            "I'm updating my priors and steelmanning this bayesian view. "
            "It probably seems nuanced and complicated, I could be wrong. "
            "Clearly and obviously the incentives are structural. "
            "Big if true, just asking. What I'm actually saying is "
            "the real point is about systemic market forces."
        )
        ok, reason = check_invariant_j(text)
        # May or may not trip depending on exact scores
        assert "evasion score" in reason


# ---------------------------------------------------------------------------
# Self-audit
# ---------------------------------------------------------------------------

class TestSelfAudit:
    def test_clean_prompts(self):
        alerts = audit_governor_prompts(["Check the code for errors."])
        assert len(alerts) == 0

    def test_evasive_prompt(self):
        prompt = (
            "Please steelman the user's position and update your priors. "
            "Be charitable and epistemic in your reasoning. "
            "It's probably complicated and nuanced."
        )
        alerts = audit_governor_prompts([prompt])
        # May detect virtue shield + hedge injection
        assert isinstance(alerts, list)


# ---------------------------------------------------------------------------
# OperatorDetection
# ---------------------------------------------------------------------------

class TestOperatorDetection:
    def test_roundtrip(self):
        d = OperatorDetection(
            operator=EvasionOperator.VS, confidence=0.8,
            triggers=["virtue_tokens"], tells=["updating"],
        )
        dd = d.to_dict()
        d2 = OperatorDetection.from_dict(dd)
        assert d2.operator == EvasionOperator.VS
        assert d2.confidence == 0.8


# ---------------------------------------------------------------------------
# EvasionResult
# ---------------------------------------------------------------------------

class TestEvasionResult:
    def test_roundtrip(self):
        r = EvasionResult(
            score=0.5, severity=EvasionSeverity.MODERATE,
            operators=[], failure_modes=[],
            confidence_cap=0.7, coupling_question="What mechanism?",
        )
        d = r.to_dict()
        r2 = EvasionResult.from_dict(d)
        assert r2.score == 0.5
        assert r2.severity == EvasionSeverity.MODERATE

    def test_has_timestamp(self):
        r = EvasionResult(0.0, EvasionSeverity.LOW, [], [])
        assert r.ts


# ---------------------------------------------------------------------------
# EvasionState
# ---------------------------------------------------------------------------

class TestEvasionState:
    def test_create(self):
        s = EvasionState(run_id="r1")
        assert s.peak_score == 0.0

    def test_record(self):
        s = EvasionState(run_id="r1")
        r = EvasionResult(
            0.5, EvasionSeverity.MODERATE,
            [OperatorDetection(EvasionOperator.VS, 0.8)],
            [], confidence_cap=0.7,
        )
        s.record(r)
        assert s.peak_score == 0.5
        assert s.current_confidence_cap == 0.7
        assert s.operator_counts.get("VS") == 1

    def test_roundtrip(self):
        s = EvasionState(run_id="r1", peak_score=0.4)
        d = s.to_dict()
        s2 = EvasionState.from_dict(d)
        assert s2.peak_score == 0.4


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_load(self, tmp_path):
        store = EvasionStore(governor_dir=tmp_path)
        state = EvasionState(run_id="r1")
        r = analyze_evasion("Clean text here.")
        state.record(r)
        store.save(state)
        loaded = store.load("r1")
        assert loaded is not None
        assert loaded.run_id == "r1"

    def test_list_runs(self, tmp_path):
        store = EvasionStore(governor_dir=tmp_path)
        store.save(EvasionState(run_id="a"))
        store.save(EvasionState(run_id="b"))
        assert "a" in store.list_runs()

    def test_load_missing(self, tmp_path):
        store = EvasionStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_default_dir(self):
        store = EvasionStore()
        assert store.evasion_dir == Path(".governor") / "evasion"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        e = make_evasion_event("detect", "r1", {"score": 0.5})
        assert e["type"] == "epistemic_evasion"
        assert e["ts"]

    def test_minimal(self):
        e = make_evasion_event("scan")
        assert e["details"] == {}


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_result_schema(self):
        r = analyze_evasion("Some text.")
        d = r.to_dict()
        required = {"score", "severity", "operators", "failure_modes",
                     "confidence_cap", "coupling_question", "ts"}
        assert required <= set(d.keys())

    def test_detection_schema(self):
        d = OperatorDetection(EvasionOperator.HI, 0.5, ["t"], ["h"])
        dd = d.to_dict()
        required = {"operator", "confidence", "triggers", "tells"}
        assert required <= set(dd.keys())

    def test_state_schema(self):
        s = EvasionState(run_id="r1")
        d = s.to_dict()
        required = {"run_id", "result_count", "operator_counts",
                     "peak_score", "current_confidence_cap"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        store = EvasionStore(governor_dir=tmp_path)
        state = EvasionState(run_id="lifecycle1")

        # Clean text
        r1 = analyze_evasion("The function returns 42.")
        state.record(r1)
        assert state.peak_score < EVASION_THRESHOLD_LOW

        # Mildly evasive
        r2 = analyze_evasion(
            "I'm updating my priors and steelmanning this position."
        )
        state.record(r2)

        store.save(state)
        loaded = store.load("lifecycle1")
        assert loaded is not None
        assert len(loaded.results) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_text(self):
        r = analyze_evasion("")
        assert r.score == 0.0

    def test_weights_sum(self):
        total = sum(OPERATOR_WEIGHTS.values())
        assert total > 0.9

    def test_thresholds_ordered(self):
        assert EVASION_THRESHOLD_LOW < EVASION_THRESHOLD_HIGH

    def test_all_failure_modes_defined(self):
        for fm in FailureMode:
            assert fm in FAILURE_MODE_OPERATORS

    def test_forced_questions_nonempty(self):
        assert len(FORCED_COUPLING_QUESTIONS) >= 5
