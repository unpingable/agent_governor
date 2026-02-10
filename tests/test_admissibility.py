"""Tests for Admissibility Gate — Push-Back System.

Layer 2.1-A. Invariant F: No hidden assumptions for S2/S3 actions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.admissibility import (
    Severity,
    UnknownCategory,
    ResolvableBy,
    PushbackMode,
    AssumptionStatus,
    Unknown,
    Assumption,
    AdmissibilityAssessment,
    Waiver,
    AdmissibilityStore,
    select_pushback_mode,
    select_clarifying_questions,
    assess_task,
    check_invariant_f,
    make_admissibility_event,
    W_SETPOINT,
    W_CONSTRAINTS,
    W_OBSERVABILITY,
    A_HIGH,
    A_LOW,
    UNKNOWN_SEVERITY_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_values(self):
        assert Severity.S1.value == "S1"
        assert Severity.S2.value == "S2"
        assert Severity.S3.value == "S3"

    def test_count(self):
        assert len(Severity) == 3


class TestUnknownCategory:
    def test_values(self):
        assert UnknownCategory.OBJECTIVE.value == "objective"
        assert UnknownCategory.CONSTRAINT.value == "constraint"
        assert UnknownCategory.CONTEXT.value == "context"
        assert UnknownCategory.RESOURCE.value == "resource"

    def test_count(self):
        assert len(UnknownCategory) == 4


class TestResolvableBy:
    def test_values(self):
        assert ResolvableBy.USER_CLARIFICATION.value == "user_clarification"
        assert ResolvableBy.TOOL_QUERY.value == "tool_query"
        assert ResolvableBy.ASSUMPTION.value == "assumption"

    def test_count(self):
        assert len(ResolvableBy) == 3


class TestPushbackMode:
    def test_values(self):
        assert PushbackMode.PROCEED.value == "proceed"
        assert PushbackMode.SOFT.value == "soft"
        assert PushbackMode.HARD.value == "hard"
        assert PushbackMode.SAFE.value == "safe"

    def test_count(self):
        assert len(PushbackMode) == 4


class TestAssumptionStatus:
    def test_values(self):
        assert AssumptionStatus.ACTIVE.value == "active"
        assert AssumptionStatus.WAIVED.value == "waived"
        assert AssumptionStatus.INVALIDATED.value == "invalidated"


# ---------------------------------------------------------------------------
# Unknown Tests
# ---------------------------------------------------------------------------

class TestUnknown:
    def test_create(self):
        u = Unknown(
            id="u_001",
            description="target platform",
            severity=Severity.S2,
            category=UnknownCategory.CONSTRAINT,
            resolvable_by=ResolvableBy.USER_CLARIFICATION,
        )
        assert u.id == "u_001"
        assert u.severity == Severity.S2
        assert u.weight == UNKNOWN_SEVERITY_WEIGHTS[Severity.S2]

    def test_auto_weight(self):
        u1 = Unknown(id="a", description="x", severity=Severity.S1,
                      category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION)
        u3 = Unknown(id="b", description="y", severity=Severity.S3,
                      category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION)
        assert u1.weight < u3.weight

    def test_explicit_weight(self):
        u = Unknown(id="a", description="x", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION,
                    weight=0.99)
        assert u.weight == 0.99

    def test_generate_question(self):
        u = Unknown(id="u1", description="the database schema",
                    severity=Severity.S2, category=UnknownCategory.CONTEXT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION)
        q = u.generate_question()
        assert "the database schema" in q
        assert q.endswith("?")

    def test_generate_question_categories(self):
        for cat in UnknownCategory:
            u = Unknown(id="u", description="thing", severity=Severity.S1,
                        category=cat, resolvable_by=ResolvableBy.ASSUMPTION)
            q = u.generate_question()
            assert q.endswith("?")

    def test_estimate_voi(self):
        u_user = Unknown(id="a", description="x", severity=Severity.S3,
                         category=UnknownCategory.OBJECTIVE,
                         resolvable_by=ResolvableBy.USER_CLARIFICATION)
        u_assume = Unknown(id="b", description="x", severity=Severity.S3,
                           category=UnknownCategory.OBJECTIVE,
                           resolvable_by=ResolvableBy.ASSUMPTION)
        # User clarification should have higher VoI
        assert u_user.estimate_voi() > u_assume.estimate_voi()

    def test_voi_severity_ordering(self):
        def make(sev: Severity) -> Unknown:
            return Unknown(id="u", description="x", severity=sev,
                           category=UnknownCategory.OBJECTIVE,
                           resolvable_by=ResolvableBy.USER_CLARIFICATION)
        assert make(Severity.S3).estimate_voi() > make(Severity.S2).estimate_voi()
        assert make(Severity.S2).estimate_voi() > make(Severity.S1).estimate_voi()

    def test_to_dict(self):
        u = Unknown(id="u_001", description="target", severity=Severity.S2,
                    category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION)
        d = u.to_dict()
        assert d["id"] == "u_001"
        assert d["severity"] == "S2"
        assert d["category"] == "constraint"
        assert d["resolvable_by"] == "user_clarification"
        assert "weight" in d

    def test_roundtrip(self):
        u = Unknown(id="u_001", description="target", severity=Severity.S2,
                    category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION, weight=0.3)
        restored = Unknown.from_dict(u.to_dict())
        assert restored.id == u.id
        assert restored.severity == u.severity
        assert restored.weight == u.weight


# ---------------------------------------------------------------------------
# Assumption Tests
# ---------------------------------------------------------------------------

class TestAssumption:
    def test_create(self):
        a = Assumption(id="a_001", unknown_id="u_001",
                       assumption="Python 3.11+", severity=Severity.S1)
        assert a.status == AssumptionStatus.ACTIVE
        assert a.created_at != ""

    def test_to_dict(self):
        a = Assumption(id="a_001", unknown_id="u_001",
                       assumption="Python 3.11+", severity=Severity.S1)
        d = a.to_dict()
        assert d["id"] == "a_001"
        assert d["assumption"] == "Python 3.11+"
        assert d["status"] == "active"

    def test_roundtrip(self):
        a = Assumption(id="a_001", unknown_id="u_001",
                       assumption="Python 3.11+", severity=Severity.S2,
                       waiver_by="user", waiver_reason="confirmed")
        restored = Assumption.from_dict(a.to_dict())
        assert restored.id == a.id
        assert restored.waiver_by == "user"


# ---------------------------------------------------------------------------
# AdmissibilityAssessment Tests
# ---------------------------------------------------------------------------

class TestAdmissibilityAssessment:
    def test_perfect_score(self):
        a = AdmissibilityAssessment(
            setpoint_score=1.0,
            constraint_score=1.0,
            observability_score=1.0,
        )
        assert a.score == pytest.approx(1.0)
        assert a.mode == PushbackMode.PROCEED

    def test_zero_score(self):
        a = AdmissibilityAssessment(
            setpoint_score=0.0,
            constraint_score=0.0,
            observability_score=0.0,
        )
        assert a.score == pytest.approx(0.0)
        assert a.mode == PushbackMode.HARD

    def test_score_with_unknowns(self):
        u = Unknown(id="u1", description="x", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        a = AdmissibilityAssessment(
            setpoint_score=0.8,
            constraint_score=0.8,
            observability_score=0.8,
            unknowns=[u],
        )
        assert a.score < 0.8  # Penalty from unknown

    def test_s3_unknown_forces_safe(self):
        u = Unknown(id="u1", description="data loss risk", severity=Severity.S3,
                    category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION)
        a = AdmissibilityAssessment(
            setpoint_score=1.0,
            constraint_score=1.0,
            observability_score=1.0,
            unknowns=[u],
        )
        assert a.mode == PushbackMode.SAFE

    def test_soft_mode(self):
        a = AdmissibilityAssessment(
            setpoint_score=0.6,
            constraint_score=0.6,
            observability_score=0.6,
        )
        # Score = 0.4*0.6 + 0.35*0.6 + 0.25*0.6 = 0.6
        assert a.score == pytest.approx(0.6)
        assert a.mode == PushbackMode.SOFT

    def test_s3_unknowns_property(self):
        unknowns = [
            Unknown(id="u1", description="a", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION),
            Unknown(id="u2", description="b", severity=Severity.S3,
                    category=UnknownCategory.CONSTRAINT, resolvable_by=ResolvableBy.USER_CLARIFICATION),
        ]
        a = AdmissibilityAssessment(
            setpoint_score=0.8, constraint_score=0.8, observability_score=0.8,
            unknowns=unknowns,
        )
        assert len(a.s3_unknowns) == 1
        assert a.s3_unknowns[0].id == "u2"

    def test_s2_unknowns_property(self):
        unknowns = [
            Unknown(id="u1", description="a", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION),
            Unknown(id="u2", description="b", severity=Severity.S2,
                    category=UnknownCategory.CONSTRAINT, resolvable_by=ResolvableBy.USER_CLARIFICATION),
        ]
        a = AdmissibilityAssessment(
            setpoint_score=0.8, constraint_score=0.8, observability_score=0.8,
            unknowns=unknowns,
        )
        assert len(a.s2_unknowns) == 2

    def test_to_dict(self):
        a = AdmissibilityAssessment(
            setpoint_score=0.8, constraint_score=0.7, observability_score=0.6,
        )
        d = a.to_dict()
        assert d["setpoint_score"] == 0.8
        assert "score" in d
        assert "mode" in d

    def test_roundtrip(self):
        u = Unknown(id="u1", description="x", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION)
        a = AdmissibilityAssessment(
            setpoint_score=0.8, constraint_score=0.7, observability_score=0.6,
            unknowns=[u],
        )
        restored = AdmissibilityAssessment.from_dict(a.to_dict())
        assert restored.setpoint_score == a.setpoint_score
        assert len(restored.unknowns) == 1

    def test_score_clamped(self):
        """Score should never exceed 1.0 or go below 0.0."""
        a = AdmissibilityAssessment(
            setpoint_score=1.0, constraint_score=1.0, observability_score=1.0,
        )
        assert a.score <= 1.0
        # With many unknowns, score floors at 0
        unknowns = [
            Unknown(id=f"u{i}", description="x", severity=Severity.S3,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION)
            for i in range(10)
        ]
        a2 = AdmissibilityAssessment(
            setpoint_score=0.5, constraint_score=0.5, observability_score=0.5,
            unknowns=unknowns,
        )
        assert a2.score >= 0.0


# ---------------------------------------------------------------------------
# Waiver Tests
# ---------------------------------------------------------------------------

class TestWaiver:
    def test_create(self):
        w = Waiver(id="w_001", unknown_id="u_001", assumption_id="a_001",
                   by="user", acknowledged_risk="May not work on Windows")
        assert w.created_at != ""

    def test_to_dict(self):
        w = Waiver(id="w_001", unknown_id="u_001", assumption_id="a_001",
                   by="user", acknowledged_risk="Risk noted")
        d = w.to_dict()
        assert d["by"] == "user"
        assert d["acknowledged_risk"] == "Risk noted"

    def test_roundtrip(self):
        w = Waiver(id="w_001", unknown_id="u_001", assumption_id="a_001",
                   by="user", acknowledged_risk="Risk noted")
        restored = Waiver.from_dict(w.to_dict())
        assert restored.id == w.id
        assert restored.by == w.by


# ---------------------------------------------------------------------------
# Core Function Tests
# ---------------------------------------------------------------------------

class TestSelectPushbackMode:
    def test_proceed(self):
        a = AdmissibilityAssessment(
            setpoint_score=1.0, constraint_score=1.0, observability_score=1.0,
        )
        assert select_pushback_mode(a) == PushbackMode.PROCEED

    def test_soft(self):
        a = AdmissibilityAssessment(
            setpoint_score=0.6, constraint_score=0.6, observability_score=0.6,
        )
        assert select_pushback_mode(a) == PushbackMode.SOFT

    def test_hard(self):
        a = AdmissibilityAssessment(
            setpoint_score=0.2, constraint_score=0.2, observability_score=0.2,
        )
        assert select_pushback_mode(a) == PushbackMode.HARD

    def test_safe_overrides_high_score(self):
        u = Unknown(id="u1", description="x", severity=Severity.S3,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION)
        a = AdmissibilityAssessment(
            setpoint_score=1.0, constraint_score=1.0, observability_score=1.0,
            unknowns=[u],
        )
        assert select_pushback_mode(a) == PushbackMode.SAFE

    def test_boundary_a_high(self):
        a = AdmissibilityAssessment(
            setpoint_score=A_HIGH, constraint_score=A_HIGH, observability_score=A_HIGH,
        )
        # Score = A_HIGH * (w1 + w2 + w3) = A_HIGH * 1.0 = A_HIGH
        assert a.score == pytest.approx(A_HIGH)
        assert select_pushback_mode(a) == PushbackMode.PROCEED

    def test_boundary_a_low(self):
        a = AdmissibilityAssessment(
            setpoint_score=A_LOW, constraint_score=A_LOW, observability_score=A_LOW,
        )
        assert a.score == pytest.approx(A_LOW)
        assert select_pushback_mode(a) == PushbackMode.SOFT


class TestSelectClarifyingQuestions:
    def test_empty(self):
        assert select_clarifying_questions([]) == []

    def test_single_unknown(self):
        u = Unknown(id="u1", description="target platform", severity=Severity.S2,
                    category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION)
        qs = select_clarifying_questions([u])
        assert len(qs) == 1
        assert "target platform" in qs[0]

    def test_max_questions(self):
        unknowns = [
            Unknown(id=f"u{i}", description=f"thing {i}", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION)
            for i in range(10)
        ]
        qs = select_clarifying_questions(unknowns, max_questions=3)
        assert len(qs) == 3

    def test_sorted_by_voi(self):
        u_low = Unknown(id="low", description="minor thing", severity=Severity.S1,
                        category=UnknownCategory.CONTEXT,
                        resolvable_by=ResolvableBy.ASSUMPTION)
        u_high = Unknown(id="high", description="critical thing", severity=Severity.S3,
                         category=UnknownCategory.CONSTRAINT,
                         resolvable_by=ResolvableBy.USER_CLARIFICATION)
        qs = select_clarifying_questions([u_low, u_high], max_questions=2)
        # Higher severity should come first
        assert "critical thing" in qs[0]


class TestAssessTask:
    def test_basic(self):
        a = assess_task(0.8, 0.7, 0.6)
        assert a.setpoint_score == 0.8
        assert a.constraint_score == 0.7
        assert a.observability_score == 0.6
        assert a.unknowns == []

    def test_with_unknowns(self):
        u = Unknown(id="u1", description="x", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        a = assess_task(0.8, 0.7, 0.6, unknowns=[u])
        assert len(a.unknowns) == 1

    def test_clamping(self):
        a = assess_task(1.5, -0.2, 0.5)
        assert a.setpoint_score == 1.0
        assert a.constraint_score == 0.0

    def test_custom_thresholds(self):
        a = assess_task(0.5, 0.5, 0.5, a_high=0.3, a_low=0.1)
        assert a.a_high == 0.3
        assert a.mode == PushbackMode.PROCEED


# ---------------------------------------------------------------------------
# Invariant F Tests
# ---------------------------------------------------------------------------

class TestInvariantF:
    def test_no_violations_when_no_unknowns(self):
        assert check_invariant_f([], []) == []

    def test_s1_unknown_without_assumption_ok(self):
        u = Unknown(id="u1", description="x", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        violations = check_invariant_f([], [u])
        assert violations == []  # S1 doesn't require assumption

    def test_s2_unknown_without_assumption_violates(self):
        u = Unknown(id="u1", description="x", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        violations = check_invariant_f([], [u])
        assert len(violations) == 1
        assert "u1" in violations[0]

    def test_s3_unknown_without_assumption_violates(self):
        u = Unknown(id="u1", description="x", severity=Severity.S3,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        violations = check_invariant_f([], [u])
        assert len(violations) == 1

    def test_s2_with_assumption_passes(self):
        u = Unknown(id="u1", description="x", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        a = Assumption(id="a1", unknown_id="u1", assumption="Assuming X",
                       severity=Severity.S2)
        violations = check_invariant_f([a], [u])
        assert violations == []

    def test_s3_with_assumption_but_no_waiver_violates(self):
        u = Unknown(id="u1", description="x", severity=Severity.S3,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        a = Assumption(id="a1", unknown_id="u1", assumption="Assuming X",
                       severity=Severity.S3)
        violations = check_invariant_f([a], [u])
        assert len(violations) == 1
        assert "waiver" in violations[0].lower()

    def test_s3_with_assumption_and_waiver_passes(self):
        u = Unknown(id="u1", description="x", severity=Severity.S3,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        a = Assumption(id="a1", unknown_id="u1", assumption="Assuming X",
                       severity=Severity.S3, waiver_by="user")
        violations = check_invariant_f([a], [u])
        assert violations == []

    def test_mixed_severities(self):
        unknowns = [
            Unknown(id="u1", description="a", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION),
            Unknown(id="u2", description="b", severity=Severity.S2,
                    category=UnknownCategory.CONSTRAINT, resolvable_by=ResolvableBy.USER_CLARIFICATION),
            Unknown(id="u3", description="c", severity=Severity.S3,
                    category=UnknownCategory.RESOURCE, resolvable_by=ResolvableBy.USER_CLARIFICATION),
        ]
        # Only S2 assumption, no S3
        assumptions = [
            Assumption(id="a2", unknown_id="u2", assumption="X", severity=Severity.S2),
        ]
        violations = check_invariant_f(assumptions, unknowns)
        # S1 is fine, S2 has assumption, S3 has no assumption
        assert len(violations) == 1
        assert "u3" in violations[0]


# ---------------------------------------------------------------------------
# Store Tests
# ---------------------------------------------------------------------------

class TestAdmissibilityStore:
    def test_create(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        assert store.admissibility_dir == tmp_path / ".governor" / "admissibility"

    def test_save_load_assessment(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        a = AdmissibilityAssessment(setpoint_score=0.8, constraint_score=0.7,
                                     observability_score=0.6)
        store.save_assessment("run1", a)
        loaded = store.load_assessment("run1")
        assert loaded is not None
        assert loaded.setpoint_score == 0.8

    def test_load_missing_assessment(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        assert store.load_assessment("nonexistent") is None

    def test_save_load_unknowns(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        unknowns = [
            Unknown(id="u1", description="x", severity=Severity.S2,
                    category=UnknownCategory.OBJECTIVE, resolvable_by=ResolvableBy.ASSUMPTION),
        ]
        store.save_unknowns("run1", unknowns)
        loaded = store.load_unknowns("run1")
        assert len(loaded) == 1
        assert loaded[0].id == "u1"

    def test_load_missing_unknowns(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        assert store.load_unknowns("nonexistent") == []

    def test_save_load_assumptions(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        assumptions = [
            Assumption(id="a1", unknown_id="u1", assumption="Python 3.11+",
                       severity=Severity.S1),
        ]
        store.save_assumptions("run1", assumptions)
        loaded = store.load_assumptions("run1")
        assert len(loaded) == 1
        assert loaded[0].assumption == "Python 3.11+"

    def test_save_load_waivers(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        waivers = [
            Waiver(id="w1", unknown_id="u1", assumption_id="a1",
                   by="user", acknowledged_risk="Risk accepted"),
        ]
        store.save_waivers("run1", waivers)
        loaded = store.load_waivers("run1")
        assert len(loaded) == 1
        assert loaded[0].by == "user"

    def test_list_runs(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        a = AdmissibilityAssessment(setpoint_score=0.5, constraint_score=0.5,
                                     observability_score=0.5)
        store.save_assessment("run1", a)
        store.save_assessment("run2", a)
        runs = store.list_runs()
        assert "run1" in runs
        assert "run2" in runs

    def test_list_runs_empty(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        assert store.list_runs() == []

    def test_corrupt_file_returns_none(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        store._ensure_dirs()
        (store.admissibility_dir / "bad_assessment.json").write_text("not json{{{")
        assert store.load_assessment("bad") is None

    def test_corrupt_unknowns_returns_empty(self, tmp_path):
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")
        store._ensure_dirs()
        (store.admissibility_dir / "bad_unknowns.json").write_text("not json")
        assert store.load_unknowns("bad") == []


# ---------------------------------------------------------------------------
# Telemetry Event Tests
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create_event(self):
        evt = make_admissibility_event("assessed", "run1", {"score": 0.7})
        assert evt["type"] == "admissibility"
        assert evt["action"] == "assessed"
        assert evt["run_id"] == "run1"
        assert evt["details"]["score"] == 0.7
        assert "ts" in evt

    def test_create_event_minimal(self):
        evt = make_admissibility_event("check")
        assert evt["run_id"] == ""
        assert evt["details"] == {}


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_unknown_schema(self):
        u = Unknown(id="u1", description="x", severity=Severity.S1,
                    category=UnknownCategory.OBJECTIVE,
                    resolvable_by=ResolvableBy.ASSUMPTION)
        d = u.to_dict()
        assert set(d.keys()) == {"id", "description", "severity", "category",
                                  "resolvable_by", "weight"}

    def test_assumption_schema(self):
        a = Assumption(id="a1", unknown_id="u1", assumption="X", severity=Severity.S1)
        d = a.to_dict()
        assert set(d.keys()) == {"id", "unknown_id", "assumption", "severity",
                                  "status", "waiver_by", "waiver_reason", "created_at"}

    def test_assessment_schema(self):
        a = AdmissibilityAssessment(setpoint_score=0.5, constraint_score=0.5,
                                     observability_score=0.5)
        d = a.to_dict()
        assert set(d.keys()) == {"setpoint_score", "constraint_score",
                                  "observability_score", "unknowns", "score", "mode"}

    def test_waiver_schema(self):
        w = Waiver(id="w1", unknown_id="u1", assumption_id="a1",
                   by="user", acknowledged_risk="risk")
        d = w.to_dict()
        assert set(d.keys()) == {"id", "unknown_id", "assumption_id", "by",
                                  "acknowledged_risk", "created_at"}

    def test_event_schema(self):
        evt = make_admissibility_event("test", "r1", {"k": "v"})
        assert set(evt.keys()) == {"type", "action", "run_id", "details", "ts"}


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Assess → questions → assume → check invariant F → persist."""
        store = AdmissibilityStore(governor_dir=tmp_path / ".governor")

        unknowns = [
            Unknown(id="u1", description="target platform",
                    severity=Severity.S2, category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION),
            Unknown(id="u2", description="data loss risk",
                    severity=Severity.S3, category=UnknownCategory.CONSTRAINT,
                    resolvable_by=ResolvableBy.USER_CLARIFICATION),
        ]

        # Assess
        assessment = assess_task(0.8, 0.7, 0.6, unknowns=unknowns)
        assert assessment.mode == PushbackMode.SAFE  # S3 unknown

        # Generate questions
        qs = select_clarifying_questions(unknowns)
        assert len(qs) >= 1

        # Make assumptions
        assumptions = [
            Assumption(id="a1", unknown_id="u1",
                       assumption="Linux only", severity=Severity.S2),
            Assumption(id="a2", unknown_id="u2",
                       assumption="Backup exists", severity=Severity.S3,
                       waiver_by="user"),
        ]

        # Check invariant F
        violations = check_invariant_f(assumptions, unknowns)
        assert violations == []  # All covered

        # Persist
        store.save_assessment("run1", assessment)
        store.save_unknowns("run1", unknowns)
        store.save_assumptions("run1", assumptions)

        # Reload
        loaded = store.load_assessment("run1")
        assert loaded is not None
        assert loaded.mode == PushbackMode.SAFE

    def test_proceed_without_unknowns(self):
        assessment = assess_task(0.9, 0.9, 0.9)
        assert assessment.mode == PushbackMode.PROCEED
        assert assessment.score > A_HIGH
        assert check_invariant_f([], []) == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_zero_scores(self):
        a = assess_task(0.0, 0.0, 0.0)
        assert a.score == 0.0
        assert a.mode == PushbackMode.HARD

    def test_many_s1_unknowns(self):
        unknowns = [
            Unknown(id=f"u{i}", description=f"minor {i}", severity=Severity.S1,
                    category=UnknownCategory.CONTEXT, resolvable_by=ResolvableBy.ASSUMPTION)
            for i in range(20)
        ]
        a = assess_task(1.0, 1.0, 1.0, unknowns=unknowns)
        assert a.mode != PushbackMode.SAFE  # No S3 unknowns
        assert a.score >= 0.0  # Clamped

    def test_custom_weights(self):
        a = AdmissibilityAssessment(
            setpoint_score=1.0, constraint_score=0.0, observability_score=0.0,
            w_setpoint=1.0, w_constraints=0.0, w_observability=0.0,
        )
        assert a.score == pytest.approx(1.0)

    def test_store_default_dir(self):
        store = AdmissibilityStore()
        assert store.governor_dir == Path(".governor")
