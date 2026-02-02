"""Tests for continuity enforcement module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from governor.continuity import (
    Anchor,
    AnchorRegistry,
    AnchorType,
    AttemptLog,
    ContinuityChecker,
    ContinuityReport,
    CorrectionConfig,
    CorrectionLadder,
    CorrectionLevel,
    ConvergenceBudget,
    ConvergenceExecutor,
    ConvergenceResult,
    DEFAULT_LADDER,
    GenerationProvider,
    RecommendedAction,
    Severity,
    Violation,
    check_output,
    create_checker,
    create_convergence_executor,
    create_ladder,
    create_registry,
)


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:
    def test_anchor_type_values(self):
        assert AnchorType.DEFINITION == "definition"
        assert AnchorType.CANON == "canon"
        assert AnchorType.STYLE == "style"
        assert AnchorType.PROHIBITION == "prohibition"
        assert AnchorType.REQUIREMENT == "requirement"
        assert AnchorType.PERSONA == "persona"

    def test_severity_values(self):
        assert Severity.WARN == "warn"
        assert Severity.CORRECT == "correct"
        assert Severity.REJECT == "reject"

    def test_recommended_action_values(self):
        assert RecommendedAction.ACCEPT == "accept"
        assert RecommendedAction.SOFT_REPROMPT == "soft_reprompt"
        assert RecommendedAction.HARD_REPROMPT == "hard_reprompt"
        assert RecommendedAction.CONSTRAIN_DECODING == "constrain_decoding"
        assert RecommendedAction.ESCALATE == "escalate"
        assert RecommendedAction.FAIL_CLOSED == "fail_closed"

    def test_correction_level_values(self):
        assert CorrectionLevel.NONE == "none"
        assert CorrectionLevel.SOFT_REPROMPT == "soft_reprompt"
        assert CorrectionLevel.HARD_REPROMPT == "hard_reprompt"
        assert CorrectionLevel.CONSTRAIN_DECODING == "constrain_decoding"
        assert CorrectionLevel.REQUIRE_HITL == "require_hitl"
        assert CorrectionLevel.FAIL_CLOSED == "fail_closed"

    def test_str_inheritance(self):
        """All enums inherit from str, so they compare as strings."""
        assert isinstance(AnchorType.DEFINITION, str)
        assert isinstance(Severity.WARN, str)
        assert isinstance(RecommendedAction.ACCEPT, str)
        assert isinstance(CorrectionLevel.NONE, str)

    def test_enum_from_value(self):
        assert AnchorType("definition") == AnchorType.DEFINITION
        assert Severity("reject") == Severity.REJECT
        assert CorrectionLevel("fail_closed") == CorrectionLevel.FAIL_CLOSED

    def test_all_anchor_types_covered(self):
        assert len(AnchorType) == 6

    def test_all_severity_levels_covered(self):
        assert len(Severity) == 3


# =============================================================================
# TestContinuityAnchor
# =============================================================================


class TestContinuityAnchor:
    def test_creation_minimal(self):
        a = Anchor(id="a1", anchor_type=AnchorType.DEFINITION, description="Test")
        assert a.id == "a1"
        assert a.anchor_type == AnchorType.DEFINITION
        assert a.severity == Severity.CORRECT  # default

    def test_creation_full(self):
        a = Anchor(
            id="a2",
            anchor_type=AnchorType.PROHIBITION,
            description="No bad words",
            required_patterns=["good"],
            required_concepts=["positive"],
            forbidden_patterns=["bad"],
            forbidden_concepts=["negative"],
            severity=Severity.REJECT,
            source="admin",
            established_at=42,
        )
        assert a.forbidden_patterns == ["bad"]
        assert a.source == "admin"
        assert a.established_at == 42

    def test_to_dict(self):
        a = Anchor(id="a1", anchor_type=AnchorType.CANON, description="Test")
        d = a.to_dict()
        assert d["id"] == "a1"
        assert d["anchor_type"] == "canon"
        assert d["severity"] == "correct"
        assert "custom_check" not in d  # not serialized

    def test_from_dict(self):
        d = {
            "id": "a1",
            "anchor_type": "style",
            "description": "Be formal",
            "required_patterns": ["Dear"],
            "severity": "warn",
        }
        a = Anchor.from_dict(d)
        assert a.id == "a1"
        assert a.anchor_type == AnchorType.STYLE
        assert a.severity == Severity.WARN
        assert a.required_patterns == ["Dear"]

    def test_roundtrip(self):
        a = Anchor(
            id="rt",
            anchor_type=AnchorType.PERSONA,
            description="Act as pirate",
            required_patterns=["arr"],
            forbidden_patterns=["hello"],
            severity=Severity.REJECT,
        )
        d = a.to_dict()
        a2 = Anchor.from_dict(d)
        assert a2.id == a.id
        assert a2.anchor_type == a.anchor_type
        assert a2.severity == a.severity
        assert a2.required_patterns == a.required_patterns
        assert a2.forbidden_patterns == a.forbidden_patterns

    def test_to_prompt_reminder(self):
        a = Anchor(
            id="a1",
            anchor_type=AnchorType.REQUIREMENT,
            description="Must cite sources",
            required_patterns=["[1]", "[2]"],
            forbidden_patterns=["trust me"],
        )
        reminder = a.to_prompt_reminder()
        assert "REQUIREMENT" in reminder
        assert "Must cite sources" in reminder
        assert "REQUIRED" in reminder
        assert "FORBIDDEN" in reminder

    def test_to_prompt_reminder_minimal(self):
        a = Anchor(id="a1", anchor_type=AnchorType.CANON, description="Sky is blue")
        reminder = a.to_prompt_reminder()
        assert "CANON" in reminder
        assert "Sky is blue" in reminder

    def test_custom_check_not_serialized(self):
        def custom(output, anchor):
            return True, []

        a = Anchor(
            id="a1",
            anchor_type=AnchorType.DEFINITION,
            description="Test",
            custom_check=custom,
        )
        d = a.to_dict()
        assert "custom_check" not in d

    def test_defaults(self):
        a = Anchor(id="a1", anchor_type=AnchorType.DEFINITION, description="Test")
        assert a.required_patterns == []
        assert a.required_concepts == []
        assert a.forbidden_patterns == []
        assert a.forbidden_concepts == []
        assert a.custom_check is None
        assert a.source == "user"
        assert a.established_at is None

    def test_from_dict_defaults(self):
        d = {"id": "a1", "anchor_type": "canon", "description": "Test"}
        a = Anchor.from_dict(d)
        assert a.severity == Severity.CORRECT
        assert a.source == "user"


# =============================================================================
# TestContinuityViolation
# =============================================================================


class TestContinuityViolation:
    def test_creation(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.PROHIBITION,
            severity=Severity.REJECT,
            description="Found bad pattern",
            evidence=["matched 'bad'"],
        )
        assert v.anchor_id == "a1"
        assert v.severity == Severity.REJECT

    def test_str(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.CANON,
            severity=Severity.WARN,
            description="Missing fact",
        )
        s = str(v)
        assert "WARN" in s
        assert "a1" in s
        assert "Missing fact" in s

    def test_to_dict(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.STYLE,
            severity=Severity.CORRECT,
            description="Wrong tone",
            evidence=["too casual"],
        )
        d = v.to_dict()
        assert d["anchor_id"] == "a1"
        assert d["anchor_type"] == "style"
        assert d["severity"] == "correct"

    def test_from_dict(self):
        d = {
            "anchor_id": "a1",
            "anchor_type": "requirement",
            "severity": "reject",
            "description": "Missing pattern",
            "evidence": ["not found"],
        }
        v = Violation.from_dict(d)
        assert v.anchor_type == AnchorType.REQUIREMENT
        assert v.evidence == ["not found"]

    def test_roundtrip(self):
        v = Violation(
            anchor_id="a2",
            anchor_type=AnchorType.PERSONA,
            severity=Severity.CORRECT,
            description="Broke character",
            evidence=["said hello"],
        )
        d = v.to_dict()
        v2 = Violation.from_dict(d)
        assert v2.anchor_id == v.anchor_id
        assert v2.description == v.description


# =============================================================================
# TestContinuityReport
# =============================================================================


class TestContinuityReport:
    def test_passed_report(self):
        r = ContinuityReport(
            passed=True,
            score=1.0,
            violations=[],
            recommended_action=RecommendedAction.ACCEPT,
            checked_anchors=3,
        )
        assert r.passed
        assert r.violation_count == 0
        assert not r.has_critical
        assert "PASSED" in r.summary()

    def test_failed_report(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.CANON,
            severity=Severity.CORRECT,
            description="Bad",
        )
        r = ContinuityReport(
            passed=False,
            score=0.5,
            violations=[v],
            recommended_action=RecommendedAction.SOFT_REPROMPT,
            checked_anchors=2,
        )
        assert not r.passed
        assert r.violation_count == 1
        assert not r.has_critical
        assert "FAILED" in r.summary()

    def test_has_critical(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.PROHIBITION,
            severity=Severity.REJECT,
            description="Critical violation",
        )
        r = ContinuityReport(
            passed=False, score=0.0, violations=[v],
            recommended_action=RecommendedAction.HARD_REPROMPT,
        )
        assert r.has_critical

    def test_to_dict(self):
        r = ContinuityReport(
            passed=True,
            score=1.0,
            violations=[],
            recommended_action=RecommendedAction.ACCEPT,
            checked_anchors=1,
            check_time_ms=5.0,
        )
        d = r.to_dict()
        assert d["passed"] is True
        assert d["score"] == 1.0
        assert d["recommended_action"] == "accept"

    def test_from_dict(self):
        d = {
            "passed": False,
            "score": 0.5,
            "violations": [{
                "anchor_id": "a1",
                "anchor_type": "canon",
                "severity": "warn",
                "description": "test",
            }],
            "recommended_action": "soft_reprompt",
            "checked_anchors": 2,
        }
        r = ContinuityReport.from_dict(d)
        assert not r.passed
        assert r.violation_count == 1

    def test_roundtrip(self):
        v = Violation(
            anchor_id="a1",
            anchor_type=AnchorType.CANON,
            severity=Severity.CORRECT,
            description="Test",
            evidence=["e1"],
        )
        r = ContinuityReport(
            passed=False,
            score=0.5,
            violations=[v],
            recommended_action=RecommendedAction.HARD_REPROMPT,
            correction_context="Fix it",
            checked_anchors=2,
            check_time_ms=10.0,
        )
        d = r.to_dict()
        r2 = ContinuityReport.from_dict(d)
        assert r2.passed == r.passed
        assert r2.score == r.score
        assert r2.violation_count == r.violation_count
        assert r2.correction_context == r.correction_context

    def test_summary_format(self):
        r = ContinuityReport(
            passed=False,
            score=0.33,
            violations=[
                Violation(anchor_id="a1", anchor_type=AnchorType.CANON,
                          severity=Severity.CORRECT, description="Bad"),
            ],
            recommended_action=RecommendedAction.SOFT_REPROMPT,
        )
        s = r.summary()
        assert "1 violations" in s
        assert "0.33" in s
        assert "soft_reprompt" in s


# =============================================================================
# TestAttemptLog
# =============================================================================


class TestAttemptLog:
    def test_creation(self):
        r = ContinuityReport(
            passed=True, score=1.0, violations=[],
            recommended_action=RecommendedAction.ACCEPT,
        )
        log = AttemptLog(
            attempt_number=0,
            prompt_hash="abc123",
            output_hash="def456",
            report=r,
        )
        assert log.attempt_number == 0
        assert log.correction_applied is None

    def test_to_dict(self):
        r = ContinuityReport(
            passed=True, score=1.0, violations=[],
            recommended_action=RecommendedAction.ACCEPT,
        )
        log = AttemptLog(
            attempt_number=1,
            prompt_hash="abc",
            output_hash="def",
            report=r,
            correction_applied="soft_reprompt",
            tokens_generated=100,
            latency_ms=50.0,
        )
        d = log.to_dict()
        assert d["attempt_number"] == 1
        assert d["correction_applied"] == "soft_reprompt"
        assert d["tokens_generated"] == 100

    def test_without_correction(self):
        r = ContinuityReport(
            passed=True, score=1.0, violations=[],
            recommended_action=RecommendedAction.ACCEPT,
        )
        log = AttemptLog(attempt_number=0, prompt_hash="a", output_hash="b", report=r)
        d = log.to_dict()
        assert d["correction_applied"] is None

    def test_with_correction(self):
        r = ContinuityReport(
            passed=False, score=0.0, violations=[],
            recommended_action=RecommendedAction.HARD_REPROMPT,
        )
        log = AttemptLog(
            attempt_number=2,
            prompt_hash="x",
            output_hash="y",
            report=r,
            correction_applied="hard_reprompt",
        )
        d = log.to_dict()
        assert d["correction_applied"] == "hard_reprompt"


# =============================================================================
# TestAnchorRegistry
# =============================================================================


class TestAnchorRegistry:
    def test_empty(self):
        reg = AnchorRegistry()
        assert len(reg) == 0
        assert reg.all() == []

    def test_register(self):
        reg = AnchorRegistry()
        a = Anchor(id="a1", anchor_type=AnchorType.CANON, description="Test")
        reg.register(a)
        assert len(reg) == 1
        assert reg.get("a1") is a

    def test_unregister(self):
        reg = AnchorRegistry()
        a = Anchor(id="a1", anchor_type=AnchorType.CANON, description="Test")
        reg.register(a)
        removed = reg.unregister("a1")
        assert removed is a
        assert len(reg) == 0
        assert reg.get("a1") is None

    def test_unregister_missing(self):
        reg = AnchorRegistry()
        assert reg.unregister("nope") is None

    def test_get_missing(self):
        reg = AnchorRegistry()
        assert reg.get("nope") is None

    def test_get_by_type(self):
        reg = AnchorRegistry()
        reg.register(Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1"))
        reg.register(Anchor(id="a2", anchor_type=AnchorType.CANON, description="C2"))
        reg.register(Anchor(id="a3", anchor_type=AnchorType.STYLE, description="S1"))

        canons = reg.get_by_type(AnchorType.CANON)
        assert len(canons) == 2
        styles = reg.get_by_type(AnchorType.STYLE)
        assert len(styles) == 1

    def test_get_by_type_empty(self):
        reg = AnchorRegistry()
        assert reg.get_by_type(AnchorType.PERSONA) == []

    def test_all(self):
        reg = AnchorRegistry()
        reg.register(Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1"))
        reg.register(Anchor(id="a2", anchor_type=AnchorType.STYLE, description="S1"))
        assert len(reg.all()) == 2

    def test_overwrite(self):
        """Registering with same id replaces the anchor."""
        reg = AnchorRegistry()
        a1 = Anchor(id="a1", anchor_type=AnchorType.CANON, description="V1")
        a2 = Anchor(id="a1", anchor_type=AnchorType.STYLE, description="V2")
        reg.register(a1)
        reg.register(a2)
        assert len(reg) == 1
        assert reg.get("a1").description == "V2"
        assert reg.get("a1").anchor_type == AnchorType.STYLE

    def test_prompt_context(self):
        reg = AnchorRegistry()
        reg.register(Anchor(
            id="a1", anchor_type=AnchorType.DEFINITION,
            description="X means Y",
            required_patterns=["X"],
        ))
        ctx = reg.to_prompt_context()
        assert "ESTABLISHED DEFINITIONS AND CONSTRAINTS" in ctx
        assert "X means Y" in ctx
        assert "REQUIRED" in ctx

    def test_prompt_context_empty(self):
        reg = AnchorRegistry()
        assert reg.to_prompt_context() == ""

    def test_save_load_roundtrip(self, tmp_path):
        reg = AnchorRegistry()
        reg.register(Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1",
                            required_patterns=["fact"], severity=Severity.REJECT))
        reg.register(Anchor(id="a2", anchor_type=AnchorType.STYLE, description="S1",
                            forbidden_patterns=["slang"]))

        path = tmp_path / "anchors.json"
        reg.save(path)

        reg2 = AnchorRegistry.load(path)
        assert len(reg2) == 2
        assert reg2.get("a1").severity == Severity.REJECT
        assert reg2.get("a2").forbidden_patterns == ["slang"]

    def test_load_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        reg = AnchorRegistry.load(path)
        assert len(reg) == 0

    def test_to_dict_from_dict(self):
        reg = AnchorRegistry()
        reg.register(Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1"))
        d = reg.to_dict()
        reg2 = AnchorRegistry.from_dict(d)
        assert len(reg2) == 1
        assert reg2.get("a1").description == "C1"

    def test_len(self):
        reg = AnchorRegistry()
        assert len(reg) == 0
        reg.register(Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1"))
        assert len(reg) == 1
        reg.register(Anchor(id="a2", anchor_type=AnchorType.CANON, description="C2"))
        assert len(reg) == 2
        reg.unregister("a1")
        assert len(reg) == 1


# =============================================================================
# TestContinuityChecker
# =============================================================================


class TestContinuityChecker:
    def test_no_anchors(self):
        checker = ContinuityChecker()
        report = checker.check("Hello world", [])
        assert report.passed
        assert report.score == 1.0
        assert report.violation_count == 0

    def test_forbidden_pattern_found(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No profanity",
            forbidden_patterns=["damn"],
        )
        report = checker.check("Oh damn it", [anchor])
        assert not report.passed
        assert report.violation_count == 1
        assert report.violations[0].anchor_id == "a1"

    def test_forbidden_pattern_not_found(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No profanity",
            forbidden_patterns=["damn"],
        )
        report = checker.check("Hello world", [anchor])
        assert report.passed
        assert report.score == 1.0

    def test_required_pattern_found(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must cite sources",
            required_patterns=["[1]"],
        )
        report = checker.check("According to [1], this is true.", [anchor])
        assert report.passed

    def test_required_pattern_missing(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must cite sources",
            required_patterns=["[1]"],
        )
        report = checker.check("This is true.", [anchor])
        assert not report.passed
        assert report.violation_count == 1

    def test_case_insensitive_default(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No shouting",
            forbidden_patterns=["HELLO"],
        )
        report = checker.check("hello world", [anchor])
        assert not report.passed  # case insensitive matches

    def test_case_sensitive(self):
        checker = ContinuityChecker(case_sensitive=True)
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No shouting",
            forbidden_patterns=["HELLO"],
        )
        report = checker.check("hello world", [anchor])
        assert report.passed  # case sensitive: "HELLO" != "hello"

    def test_custom_check_pass(self):
        def custom(output, anchor):
            return True, []

        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.DEFINITION,
            description="Custom pass",
            custom_check=custom,
        )
        report = checker.check("anything", [anchor])
        assert report.passed

    def test_custom_check_fail(self):
        def custom(output, anchor):
            return False, ["missing concept X"]

        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.DEFINITION,
            description="Custom fail",
            custom_check=custom,
        )
        report = checker.check("anything", [anchor])
        assert not report.passed
        assert report.violations[0].evidence == ["missing concept X"]

    def test_custom_check_error(self):
        def custom(output, anchor):
            raise ValueError("boom")

        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.DEFINITION,
            description="Custom error",
            custom_check=custom,
        )
        report = checker.check("anything", [anchor])
        assert not report.passed
        assert "error" in report.violations[0].description.lower()

    def test_custom_check_overrides_patterns(self):
        """Custom check takes precedence over pattern matching."""
        def custom(output, anchor):
            return True, []

        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.DEFINITION,
            description="Custom overrides",
            forbidden_patterns=["anything"],  # would fail without custom
            custom_check=custom,
        )
        report = checker.check("anything", [anchor])
        assert report.passed  # custom says pass, patterns ignored

    def test_mixed_anchors(self):
        checker = ContinuityChecker()
        a1 = Anchor(
            id="good", anchor_type=AnchorType.REQUIREMENT,
            description="Must greet",
            required_patterns=["hello"],
        )
        a2 = Anchor(
            id="bad", anchor_type=AnchorType.PROHIBITION,
            description="No goodbye",
            forbidden_patterns=["goodbye"],
        )
        # Passes a1, fails a2
        report = checker.check("hello and goodbye", [a1, a2])
        assert not report.passed
        assert report.score == 0.5  # 1 of 2 anchors passed

    def test_score_calculation(self):
        checker = ContinuityChecker()
        a1 = Anchor(id="a1", anchor_type=AnchorType.CANON, description="C1",
                     required_patterns=["alpha"])
        a2 = Anchor(id="a2", anchor_type=AnchorType.CANON, description="C2",
                     required_patterns=["beta"])
        a3 = Anchor(id="a3", anchor_type=AnchorType.CANON, description="C3",
                     required_patterns=["gamma"])
        report = checker.check("alpha and gamma", [a1, a2, a3])
        assert report.score == pytest.approx(2.0 / 3.0)

    def test_action_accept_for_warn_only(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.STYLE,
            description="Style hint",
            forbidden_patterns=["like"],
            severity=Severity.WARN,
        )
        report = checker.check("I like it", [anchor])
        assert report.recommended_action == RecommendedAction.ACCEPT

    def test_action_soft_reprompt_for_1_correct(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Req",
            required_patterns=["xyz"],
            severity=Severity.CORRECT,
        )
        report = checker.check("no xyz here... oh wait", [anchor])
        # "xyz" is actually present as substring — let's use a pattern that won't match
        report = checker.check("no match here", [anchor])
        assert report.recommended_action == RecommendedAction.SOFT_REPROMPT

    def test_action_hard_reprompt_for_reject(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No secrets",
            forbidden_patterns=["password123"],
            severity=Severity.REJECT,
        )
        report = checker.check("the password123 is leaked", [anchor])
        assert report.recommended_action == RecommendedAction.HARD_REPROMPT

    def test_action_hard_reprompt_for_many_correct(self):
        checker = ContinuityChecker()
        anchors = [
            Anchor(id=f"a{i}", anchor_type=AnchorType.REQUIREMENT,
                   description=f"Req{i}", required_patterns=[f"pattern_{i}"],
                   severity=Severity.CORRECT)
            for i in range(4)
        ]
        report = checker.check("nothing matches", anchors)
        # 4 CORRECT violations → should be HARD_REPROMPT (>2)
        assert report.recommended_action == RecommendedAction.HARD_REPROMPT

    def test_correction_context_built(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
            severity=Severity.CORRECT,
        )
        report = checker.check("goodbye", [anchor])
        assert report.correction_context is not None
        assert "CORRECTION REQUIRED" in report.correction_context
        assert "Must say hello" in report.correction_context

    def test_forbidden_concept(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No machine learning",
            forbidden_concepts=["neural network"],
        )
        report = checker.check("We use a neural network for classification", [anchor])
        assert not report.passed

    def test_required_concept(self):
        checker = ContinuityChecker()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must mention safety",
            required_concepts=["safety protocol"],
        )
        report = checker.check("Follow the safety protocol at all times", [anchor])
        assert report.passed


# =============================================================================
# TestCorrectionLadder
# =============================================================================


class TestCorrectionLadder:
    def test_initial_level(self):
        ladder = CorrectionLadder()
        assert ladder.current_level == CorrectionLevel.SOFT_REPROMPT

    def test_escalation_sequence(self):
        ladder = CorrectionLadder()
        levels = [ladder.current_level]
        # Exhaust retries at each level and escalate
        while not ladder.is_exhausted():
            while not ladder.should_escalate():
                ladder.record_retry()
            ladder.escalate()
            levels.append(ladder.current_level)

        assert CorrectionLevel.SOFT_REPROMPT in levels
        assert CorrectionLevel.HARD_REPROMPT in levels
        assert CorrectionLevel.CONSTRAIN_DECODING in levels
        assert CorrectionLevel.REQUIRE_HITL in levels
        assert CorrectionLevel.FAIL_CLOSED in levels

    def test_retry_tracking(self):
        ladder = CorrectionLadder()
        assert not ladder.should_escalate()
        ladder.record_retry()
        assert not ladder.should_escalate()  # default max_retries=2
        ladder.record_retry()
        assert ladder.should_escalate()

    def test_exhaustion(self):
        ladder = CorrectionLadder()
        assert not ladder.is_exhausted()
        # Escalate through all levels
        for _ in range(10):
            if ladder.is_exhausted():
                break
            while not ladder.should_escalate():
                ladder.record_retry()
            ladder.escalate()
        assert ladder.is_exhausted()

    def test_reset(self):
        ladder = CorrectionLadder()
        ladder.record_retry()
        ladder.record_retry()
        ladder.escalate()
        assert ladder.current_level != CorrectionLevel.SOFT_REPROMPT
        ladder.reset()
        assert ladder.current_level == CorrectionLevel.SOFT_REPROMPT

    def test_apply_correction_soft(self):
        ladder = CorrectionLadder()
        corrected = ladder.apply_correction(
            "Write about cats",
            "CORRECTION: mention whiskers",
            [],
        )
        assert "CORRECTION" in corrected
        assert "Write about cats" in corrected

    def test_apply_correction_with_constraints(self):
        ladder = CorrectionLadder([
            CorrectionConfig(
                level=CorrectionLevel.HARD_REPROMPT,
                prepend_reminder=True,
                inject_constraints=True,
            ),
        ])
        anchors = [
            Anchor(id="a1", anchor_type=AnchorType.PROHIBITION,
                   description="No X", forbidden_patterns=["bad_word"]),
            Anchor(id="a2", anchor_type=AnchorType.REQUIREMENT,
                   description="Say Y", required_patterns=["good_word"]),
        ]
        corrected = ladder.apply_correction(
            "Original prompt",
            "Fix this",
            anchors,
        )
        assert "FORBIDDEN: bad_word" in corrected
        assert "REQUIRED: good_word" in corrected
        assert "Original prompt" in corrected

    def test_generation_params_temperature(self):
        ladder = CorrectionLadder()
        # Escalate to CONSTRAIN_DECODING
        while ladder.current_level != CorrectionLevel.CONSTRAIN_DECODING:
            while not ladder.should_escalate():
                ladder.record_retry()
            ladder.escalate()
        params = ladder.get_generation_params()
        assert "temperature" in params
        assert params["temperature"] == 0.3

    def test_generation_params_empty_at_soft(self):
        ladder = CorrectionLadder()
        params = ladder.get_generation_params()
        assert "temperature" not in params

    def test_custom_config(self):
        configs = [
            CorrectionConfig(level=CorrectionLevel.HARD_REPROMPT, max_retries_at_level=1),
            CorrectionConfig(level=CorrectionLevel.FAIL_CLOSED, max_retries_at_level=0),
        ]
        ladder = CorrectionLadder(configs)
        assert ladder.current_level == CorrectionLevel.HARD_REPROMPT
        ladder.record_retry()
        assert ladder.should_escalate()

    def test_default_ladder_constant(self):
        assert len(DEFAULT_LADDER) == 5
        assert DEFAULT_LADDER[0].level == CorrectionLevel.SOFT_REPROMPT
        assert DEFAULT_LADDER[-1].level == CorrectionLevel.FAIL_CLOSED


# =============================================================================
# TestConvergenceExecutor
# =============================================================================


class MockProvider:
    """Mock generation provider for testing."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._call_count = 0

    def generate(self, prompt: str, **kwargs) -> str:
        if self._call_count >= len(self._responses):
            return self._responses[-1]
        output = self._responses[self._call_count]
        self._call_count += 1
        return output

    @property
    def call_count(self) -> int:
        return self._call_count


class TestConvergenceExecutor:
    def test_first_try_converge(self):
        provider = MockProvider(["hello world"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        assert result.converged
        assert result.attempts == 1
        assert result.output == "hello world"

    def test_retry_converge(self):
        # First response fails, second succeeds
        provider = MockProvider(["bad output", "hello world"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        assert result.converged
        assert result.attempts == 2

    def test_fail_closed(self):
        """All attempts fail — returns best with converged=False."""
        provider = MockProvider(["bad"] * 10)
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        budget = ConvergenceBudget(max_attempts=3)
        executor = ConvergenceExecutor(provider=provider, budget=budget)
        result = executor.converge_generate("Say hello", [anchor])
        assert not result.converged
        assert result.output == "bad"  # best attempt (all same score)

    def test_budget_max_attempts(self):
        provider = MockProvider(["bad"] * 100)
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        budget = ConvergenceBudget(max_attempts=2)
        executor = ConvergenceExecutor(provider=provider, budget=budget)
        result = executor.converge_generate("Say hello", [anchor])
        assert not result.converged
        assert result.attempts <= 2

    def test_attempt_log(self):
        provider = MockProvider(["bad", "hello"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        assert len(result.attempt_log) == 2
        assert result.attempt_log[0].attempt_number == 0
        assert result.attempt_log[1].attempt_number == 1

    def test_prompt_changes_between_attempts(self):
        """Prompt hash should change between correction attempts."""
        provider = MockProvider(["bad", "bad", "hello"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        if len(result.attempt_log) >= 2:
            # First attempt uses original prompt, second uses corrected
            h0 = result.attempt_log[0].prompt_hash
            h1 = result.attempt_log[1].prompt_hash
            assert h0 != h1  # correction changes the prompt

    def test_escalation_occurs(self):
        """Correction level should escalate after retries."""
        provider = MockProvider(["bad"] * 20)
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
            severity=Severity.CORRECT,
        )
        budget = ConvergenceBudget(max_attempts=10)
        executor = ConvergenceExecutor(provider=provider, budget=budget)
        result = executor.converge_generate("Say hello", [anchor])
        # Should have tried at multiple correction levels
        assert not result.converged
        corrections = [a.correction_applied for a in result.attempt_log if a.correction_applied]
        assert len(corrections) > 0

    def test_result_fields(self):
        provider = MockProvider(["hello world"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        assert isinstance(result.total_tokens, int)
        assert isinstance(result.total_latency_ms, float)
        assert result.final_prompt is not None
        assert result.final_report.passed

    def test_best_output_tracked(self):
        """When failing, returns the best-scoring output."""
        provider = MockProvider(["has hello but also bad", "nothing good"])
        anchor_req = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        anchor_proh = Anchor(
            id="a2", anchor_type=AnchorType.PROHIBITION,
            description="No bad",
            forbidden_patterns=["bad"],
        )
        budget = ConvergenceBudget(max_attempts=2)
        executor = ConvergenceExecutor(provider=provider, budget=budget)
        result = executor.converge_generate("Test", [anchor_req, anchor_proh])
        assert not result.converged
        # First output has score 0.0 (fails both: has "bad", has "hello" → 1 pass, 1 fail = 0.5)
        # Actually: first output has "hello" (passes a1) and "bad" (fails a2) → score 0.5
        # Second output: no "hello" (fails a1), no "bad" (passes a2) → score 0.5
        # Both same score, best_output = first one (set first)
        assert result.output == "has hello but also bad"

    def test_generation_error_handling(self):
        """Provider errors are handled gracefully."""
        class ErrorProvider:
            def __init__(self):
                self.calls = 0

            def generate(self, prompt, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("API down")
                return "hello"

        provider = ErrorProvider()
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        assert result.converged
        assert result.attempts == 2

    def test_to_dict(self):
        provider = MockProvider(["hello"])
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Say hello", [anchor])
        d = result.to_dict()
        assert d["converged"] is True
        assert "attempt_log" in d
        assert d["output"] == "hello"

    def test_no_anchors(self):
        """With no anchors, first output passes immediately."""
        provider = MockProvider(["anything"])
        executor = ConvergenceExecutor(provider=provider)
        result = executor.converge_generate("Write something", [])
        assert result.converged
        assert result.attempts == 1

    def test_budget_max_tokens(self):
        """Token budget is enforced."""
        provider = MockProvider(["word " * 5000] * 10)
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        budget = ConvergenceBudget(max_attempts=10, max_tokens=100)
        executor = ConvergenceExecutor(provider=provider, budget=budget)
        result = executor.converge_generate("Say hello", [anchor])
        assert not result.converged
        assert result.total_tokens > 0


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:
    def test_create_registry(self, tmp_path):
        reg = create_registry(tmp_path)
        assert len(reg) == 0

    def test_create_checker(self):
        checker = create_checker()
        assert isinstance(checker, ContinuityChecker)

    def test_create_ladder(self):
        ladder = create_ladder()
        assert ladder.current_level == CorrectionLevel.SOFT_REPROMPT

    def test_check_output_oneshot(self):
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        )
        report = check_output("hello world", [anchor])
        assert report.passed


# =============================================================================
# TestAdapterIntegration
# =============================================================================


class TestAdapterIntegration:
    def test_continuity_invariant_passes(self, tmp_path):
        from governor.adapters import continuity_invariant
        from governor.continuity import AnchorRegistry, ContinuityChecker

        reg = AnchorRegistry()
        reg.register(Anchor(
            id="a1", anchor_type=AnchorType.REQUIREMENT,
            description="Must say hello",
            required_patterns=["hello"],
        ))

        inv = continuity_invariant(registry=reg)

        # Create a file that passes
        test_file = tmp_path / "test.py"
        test_file.write_text("# hello world\nprint('hi')")

        result = inv.verify(root=tmp_path, files_touched=["test.py"])
        assert result.passed

    def test_continuity_invariant_blocks(self, tmp_path):
        from governor.adapters import continuity_invariant
        from governor.continuity import AnchorRegistry

        reg = AnchorRegistry()
        reg.register(Anchor(
            id="a1", anchor_type=AnchorType.PROHIBITION,
            description="No passwords",
            forbidden_patterns=["password123"],
            severity=Severity.REJECT,
        ))

        inv = continuity_invariant(registry=reg)

        test_file = tmp_path / "test.py"
        test_file.write_text("secret = 'password123'")

        result = inv.verify(root=tmp_path, files_touched=["test.py"])
        assert not result.passed
        assert "violation" in result.message.lower()

    def test_continuity_invariant_warns(self, tmp_path):
        from governor.adapters import continuity_invariant
        from governor.continuity import AnchorRegistry

        reg = AnchorRegistry()
        reg.register(Anchor(
            id="a1", anchor_type=AnchorType.STYLE,
            description="Style hint",
            forbidden_patterns=["todo"],
            severity=Severity.WARN,
        ))

        # min_severity=correct by default, so WARN violations are below threshold
        inv = continuity_invariant(registry=reg)

        test_file = tmp_path / "test.py"
        test_file.write_text("# todo: fix this later")

        result = inv.verify(root=tmp_path, files_touched=["test.py"])
        assert result.passed  # warn is below "correct" threshold

    def test_adapter_config(self):
        from governor.adapters import AdapterConfig

        config = AdapterConfig()
        assert config.continuity_registry is None
        assert config.continuity_checker is None

    def test_build_adapter_set(self):
        from governor.adapters import AdapterConfig, build_adapter_set
        from governor.continuity import AnchorRegistry

        reg = AnchorRegistry()
        reg.register(Anchor(
            id="a1", anchor_type=AnchorType.CANON,
            description="Test",
        ))
        config = AdapterConfig(continuity_registry=reg)
        invariants = build_adapter_set(config)
        assert len(invariants) == 1
        assert invariants[0].id == "continuity_check"


# =============================================================================
# TestSerialization
# =============================================================================


class TestSerialization:
    def test_convergence_budget_roundtrip(self):
        b = ConvergenceBudget(max_attempts=3, max_tokens=5000, max_time_ms=15000.0)
        d = b.to_dict()
        b2 = ConvergenceBudget.from_dict(d)
        assert b2.max_attempts == 3
        assert b2.max_tokens == 5000
        assert b2.max_time_ms == 15000.0

    def test_correction_config_roundtrip(self):
        c = CorrectionConfig(
            level=CorrectionLevel.HARD_REPROMPT,
            max_retries_at_level=3,
            temperature_override=0.5,
            inject_constraints=True,
        )
        d = c.to_dict()
        c2 = CorrectionConfig.from_dict(d)
        assert c2.level == CorrectionLevel.HARD_REPROMPT
        assert c2.max_retries_at_level == 3
        assert c2.temperature_override == 0.5
        assert c2.inject_constraints is True

    def test_anchor_registry_json_roundtrip(self, tmp_path):
        reg = AnchorRegistry()
        for i in range(5):
            reg.register(Anchor(
                id=f"a{i}",
                anchor_type=AnchorType.CANON,
                description=f"Anchor {i}",
                required_patterns=[f"pat_{i}"],
                forbidden_patterns=[f"bad_{i}"],
                severity=Severity.CORRECT if i % 2 == 0 else Severity.REJECT,
            ))

        path = tmp_path / "test.json"
        reg.save(path)

        # Verify JSON is valid
        data = json.loads(path.read_text())
        assert len(data["anchors"]) == 5

        reg2 = AnchorRegistry.load(path)
        assert len(reg2) == 5
        for i in range(5):
            a = reg2.get(f"a{i}")
            assert a is not None
            assert a.required_patterns == [f"pat_{i}"]
            assert a.forbidden_patterns == [f"bad_{i}"]


# =============================================================================
# TestGenerationProviderProtocol
# =============================================================================


class TestGenerationProviderProtocol:
    def test_mock_provider_is_protocol(self):
        provider = MockProvider(["hello"])
        assert isinstance(provider, GenerationProvider)

    def test_lambda_provider(self):
        """Any object with generate method satisfies the protocol."""
        class SimpleProvider:
            def generate(self, prompt: str, **kwargs) -> str:
                return f"Echo: {prompt}"

        provider = SimpleProvider()
        assert isinstance(provider, GenerationProvider)
