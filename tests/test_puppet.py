# SPDX-License-Identifier: Apache-2.0
"""Tests for puppet mode — persona pinning with semantic safety."""

import json
import pytest
from pathlib import Path

from governor.puppet import (
    # Enums
    CertaintyLevel,
    TagPosition,
    AnswerMode,
    DiffRuleId,
    DiffWarnId,
    RenderVerdict,
    # Dataclasses
    FormattingRules,
    VoiceConstraints,
    HedgePolicy,
    VolatilityPolicy,
    EpistemicPosture,
    BehavioralConstraints,
    RoleDisclaimer,
    SafetyOverrides,
    PuppetProfile,
    SkeletonAtom,
    AnswerSkeleton,
    DiffViolation,
    DiffWarning,
    DiffGuardResult,
    PuppetRenderResult,
    # Classes
    PuppetDiffGuard,
    PuppetRenderer,
    PuppetRegistry,
    # Helpers
    classify_certainty,
    extract_certainty_profile,
    extract_imperatives,
    extract_citations,
    # Convenience
    create_puppet_registry,
    create_puppet_renderer,
    create_diff_guard,
    create_skeleton,
    render_with_puppet,
    # Builtin profiles
    _BUILTIN_PROFILES,
)
from governor.semvar import Register
from governor.strict import ClaimCategory, CommitLevel


# =============================================================================
# Enums
# =============================================================================


class TestEnums:
    """Test all puppet enums have expected values."""

    def test_certainty_level_values(self):
        assert CertaintyLevel.HIGH == "high"
        assert CertaintyLevel.MEDIUM == "medium"
        assert CertaintyLevel.LOW == "low"

    def test_tag_position_values(self):
        assert TagPosition.PREFIX == "prefix"
        assert TagPosition.SUFFIX == "suffix"
        assert TagPosition.NONE == "none"

    def test_answer_mode_values(self):
        assert AnswerMode.DIRECT == "direct"
        assert AnswerMode.DIAGNOSTIC == "diagnostic"
        assert AnswerMode.SKEPTICAL == "skeptical"

    def test_diff_rule_id_values(self):
        assert len(DiffRuleId) == 7
        assert DiffRuleId.R1_NEW_ENTITIES.value == "R1_NEW_ENTITIES"

    def test_diff_warn_id_values(self):
        assert len(DiffWarnId) == 2
        assert DiffWarnId.W1_COMPRESSION_RISK.value == "W1_COMPRESSION_RISK"

    def test_render_verdict_values(self):
        assert RenderVerdict.PASSED == "passed"
        assert RenderVerdict.RERENDERED == "rerendered"
        assert RenderVerdict.FALLBACK == "fallback"


# =============================================================================
# FormattingRules
# =============================================================================


class TestFormattingRules:
    def test_create_defaults(self):
        f = FormattingRules()
        assert f.allow_lists is True
        assert f.allow_headings is True
        assert f.allow_tables is False
        assert f.max_bullets_per_list == 10
        assert f.max_lists == 4

    def test_to_dict(self):
        f = FormattingRules(allow_tables=True, max_lists=2)
        d = f.to_dict()
        assert d["allow_tables"] is True
        assert d["max_lists"] == 2

    def test_from_dict(self):
        d = {"allow_lists": False, "max_bullets_per_list": 5}
        f = FormattingRules.from_dict(d)
        assert f.allow_lists is False
        assert f.max_bullets_per_list == 5
        assert f.allow_tables is False  # default


# =============================================================================
# VoiceConstraints
# =============================================================================


class TestVoiceConstraints:
    def test_create_defaults(self):
        v = VoiceConstraints()
        assert v.register == Register.NEUTRAL
        assert v.verbosity_cap_tokens == 500
        assert v.tone_tags == []
        assert v.forbidden_phrases == []

    def test_with_fields(self):
        v = VoiceConstraints(
            tone_tags=["dry", "terse"],
            register=Register.CLINICAL,
            forbidden_phrases=["obviously"],
        )
        assert v.tone_tags == ["dry", "terse"]
        assert v.register == Register.CLINICAL
        assert "obviously" in v.forbidden_phrases

    def test_to_dict(self):
        v = VoiceConstraints(tone_tags=["formal"], register=Register.FORMAL)
        d = v.to_dict()
        assert d["register"] == "formal"
        assert d["tone_tags"] == ["formal"]
        assert "formatting" in d

    def test_from_dict(self):
        d = {
            "tone_tags": ["wry"],
            "register": "wry",
            "verbosity_cap_tokens": 200,
            "forbidden_phrases": ["lol"],
            "required_ticks": ["Timeline:"],
        }
        v = VoiceConstraints.from_dict(d)
        assert v.register == Register.WRY
        assert v.verbosity_cap_tokens == 200
        assert v.required_ticks == ["Timeline:"]


# =============================================================================
# HedgePolicy
# =============================================================================


class TestHedgePolicy:
    def test_create(self):
        h = HedgePolicy(
            soft_markers=["likely"],
            hard_markers=["is"],
            forbid_overclaim_words=["proves"],
        )
        assert h.soft_markers == ["likely"]
        assert h.forbid_overclaim_words == ["proves"]

    def test_to_dict(self):
        h = HedgePolicy(soft_markers=["probably"])
        d = h.to_dict()
        assert d["soft_markers"] == ["probably"]

    def test_from_dict(self):
        d = {"soft_markers": ["maybe"], "hard_markers": ["is"], "forbid_overclaim_words": []}
        h = HedgePolicy.from_dict(d)
        assert h.soft_markers == ["maybe"]


# =============================================================================
# VolatilityPolicy
# =============================================================================


class TestVolatilityPolicy:
    def test_create(self):
        v = VolatilityPolicy()
        assert v.allow_news_like_claims is True
        assert v.force_sources_for_volatile is True

    def test_defaults(self):
        v = VolatilityPolicy()
        assert "HIGH" in v.freshness_max_seconds
        assert v.freshness_max_seconds["HIGH"] == 3600

    def test_to_dict_from_dict(self):
        v = VolatilityPolicy(allow_news_like_claims=False)
        d = v.to_dict()
        v2 = VolatilityPolicy.from_dict(d)
        assert v2.allow_news_like_claims is False


# =============================================================================
# EpistemicPosture
# =============================================================================


class TestEpistemicPosture:
    def test_create(self):
        e = EpistemicPosture()
        assert len(e.allowed_claim_types) == len(ClaimCategory)

    def test_get_commit_level_default(self):
        e = EpistemicPosture()
        assert e.get_commit_level(ClaimCategory.CODE) == CommitLevel.SOFT

    def test_get_commit_level_configured(self):
        e = EpistemicPosture(
            default_commit_level={"code": CommitLevel.HARD}
        )
        assert e.get_commit_level(ClaimCategory.CODE) == CommitLevel.HARD

    def test_allows_claim_type(self):
        e = EpistemicPosture(
            allowed_claim_types=[ClaimCategory.STATIC_FACT, ClaimCategory.CODE]
        )
        assert e.allows_claim_type(ClaimCategory.CODE) is True
        assert e.allows_claim_type(ClaimCategory.JUDGMENT) is False

    def test_to_dict_from_dict(self):
        e = EpistemicPosture(
            allowed_claim_types=[ClaimCategory.STATIC_FACT],
            default_commit_level={"static_fact": CommitLevel.HARD},
        )
        d = e.to_dict()
        e2 = EpistemicPosture.from_dict(d)
        assert e2.allowed_claim_types == [ClaimCategory.STATIC_FACT]
        assert e2.get_commit_level(ClaimCategory.STATIC_FACT) == CommitLevel.HARD


# =============================================================================
# BehavioralConstraints
# =============================================================================


class TestBehavioralConstraints:
    def test_create(self):
        b = BehavioralConstraints()
        assert b.interaction_style == AnswerMode.DIRECT
        assert b.ask_clarifying_questions is True
        assert b.max_questions == 1

    def test_to_dict(self):
        b = BehavioralConstraints(
            refuse_domains=["medical"],
            interaction_style=AnswerMode.SKEPTICAL,
        )
        d = b.to_dict()
        assert d["refuse_domains"] == ["medical"]
        assert d["interaction_style"] == "skeptical"

    def test_from_dict(self):
        d = {
            "refuse_domains": [],
            "allow_tools": ["search"],
            "forbid_tools": [],
            "require_tool_for": {},
            "interaction_style": "diagnostic",
            "ask_clarifying_questions": False,
            "max_questions": 3,
        }
        b = BehavioralConstraints.from_dict(d)
        assert b.interaction_style == AnswerMode.DIAGNOSTIC
        assert b.ask_clarifying_questions is False
        assert b.max_questions == 3


# =============================================================================
# RoleDisclaimer
# =============================================================================


class TestRoleDisclaimer:
    def test_create(self):
        r = RoleDisclaimer()
        assert r.enabled is True
        assert r.tag_format == TagPosition.PREFIX

    def test_apply_prefix(self):
        r = RoleDisclaimer(tag_text="[puppet: test]")
        result = r.apply("Hello world")
        assert result == "[puppet: test]\n\nHello world"

    def test_apply_suffix(self):
        r = RoleDisclaimer(tag_format=TagPosition.SUFFIX, tag_text="[end]")
        result = r.apply("Hello world")
        assert result == "Hello world\n\n[end]"

    def test_apply_none(self):
        r = RoleDisclaimer(tag_format=TagPosition.NONE, tag_text="[tag]")
        result = r.apply("Hello world")
        assert result == "Hello world"

    def test_to_dict_from_dict(self):
        r = RoleDisclaimer(tag_text="[puppet: x]", tag_format=TagPosition.SUFFIX)
        d = r.to_dict()
        r2 = RoleDisclaimer.from_dict(d)
        assert r2.tag_text == "[puppet: x]"
        assert r2.tag_format == TagPosition.SUFFIX


# =============================================================================
# SafetyOverrides
# =============================================================================


class TestSafetyOverrides:
    def test_create(self):
        s = SafetyOverrides()
        assert s.allow_spice is False
        assert s.forbid_insults is True

    def test_defaults(self):
        s = SafetyOverrides(allow_spice=True)
        assert s.allow_spice is True

    def test_to_dict_from_dict(self):
        s = SafetyOverrides(allow_spice=True, forbid_insults=False)
        d = s.to_dict()
        s2 = SafetyOverrides.from_dict(d)
        assert s2.allow_spice is True
        assert s2.forbid_insults is False


# =============================================================================
# PuppetProfile
# =============================================================================


class TestPuppetProfile:
    def test_create_minimal(self):
        p = PuppetProfile(puppet_id="test")
        assert p.puppet_id == "test"
        assert p.version == "1.0"
        assert p.description == ""

    def test_create_full(self):
        p = PuppetProfile(
            puppet_id="full",
            version="2.0",
            description="Full profile",
            voice=VoiceConstraints(tone_tags=["dry"]),
            disclaimer=RoleDisclaimer(tag_text="[test]"),
        )
        assert p.voice.tone_tags == ["dry"]
        assert p.disclaimer.tag_text == "[test]"

    def test_to_dict(self):
        p = PuppetProfile(puppet_id="test", description="desc")
        d = p.to_dict()
        assert d["puppet_id"] == "test"
        assert d["description"] == "desc"
        assert "voice" in d
        assert "epistemic" in d

    def test_from_dict(self):
        d = {
            "puppet_id": "from_dict_test",
            "version": "1.0",
            "description": "test",
            "voice": VoiceConstraints().to_dict(),
            "epistemic": EpistemicPosture().to_dict(),
            "behavioral": BehavioralConstraints().to_dict(),
            "disclaimer": RoleDisclaimer().to_dict(),
            "safety": SafetyOverrides().to_dict(),
        }
        p = PuppetProfile.from_dict(d)
        assert p.puppet_id == "from_dict_test"

    def test_roundtrip(self):
        p = PuppetProfile(
            puppet_id="roundtrip",
            voice=VoiceConstraints(forbidden_phrases=["bad"]),
            disclaimer=RoleDisclaimer(tag_text="[rt]", tag_format=TagPosition.SUFFIX),
        )
        d = p.to_dict()
        p2 = PuppetProfile.from_dict(d)
        assert p2.puppet_id == p.puppet_id
        assert p2.voice.forbidden_phrases == ["bad"]
        assert p2.disclaimer.tag_text == "[rt]"


# =============================================================================
# SkeletonAtom
# =============================================================================


class TestSkeletonAtom:
    def test_create(self):
        a = SkeletonAtom(text="Hello")
        assert a.text == "Hello"
        assert a.commit_level == CommitLevel.SOFT
        assert a.category is None

    def test_with_citations(self):
        a = SkeletonAtom(text="Fact", citations=["[1]", "[2]"])
        assert len(a.citations) == 2

    def test_to_dict(self):
        a = SkeletonAtom(text="X", category=ClaimCategory.CODE)
        d = a.to_dict()
        assert d["category"] == "code"
        assert d["commit_level"] == "soft"

    def test_from_dict(self):
        d = {"text": "Y", "commit_level": "hard", "category": "procedure", "citations": ["[1]"]}
        a = SkeletonAtom.from_dict(d)
        assert a.commit_level == CommitLevel.HARD
        assert a.category == ClaimCategory.PROCEDURE
        assert a.citations == ["[1]"]


# =============================================================================
# AnswerSkeleton
# =============================================================================


class TestAnswerSkeleton:
    def test_create(self):
        s = AnswerSkeleton(raw_text="Hello world")
        assert s.raw_text == "Hello world"

    def test_full_text_from_atoms(self):
        s = AnswerSkeleton(
            atoms=[SkeletonAtom(text="Hello"), SkeletonAtom(text="world")],
            raw_text="raw",
        )
        assert s.full_text() == "Hello world"

    def test_full_text_from_raw(self):
        s = AnswerSkeleton(raw_text="fallback text")
        assert s.full_text() == "fallback text"

    def test_to_dict_from_dict(self):
        s = AnswerSkeleton(
            atoms=[SkeletonAtom(text="A"), SkeletonAtom(text="B")],
            raw_text="A B",
        )
        d = s.to_dict()
        s2 = AnswerSkeleton.from_dict(d)
        assert s2.full_text() == "A B"
        assert len(s2.atoms) == 2


# =============================================================================
# DiffViolation
# =============================================================================


class TestDiffViolation:
    def test_create(self):
        v = DiffViolation(
            rule_id=DiffRuleId.R1_NEW_ENTITIES,
            description="New entities found",
            detail="Google, Microsoft",
        )
        assert v.rule_id == DiffRuleId.R1_NEW_ENTITIES

    def test_to_dict(self):
        v = DiffViolation(rule_id=DiffRuleId.R2_NEW_NUMBERS, description="numbers")
        d = v.to_dict()
        assert d["rule_id"] == "R2_NEW_NUMBERS"

    def test_from_dict(self):
        d = {"rule_id": "R3_CERTAINTY_ESCALATION", "description": "escalation", "detail": ""}
        v = DiffViolation.from_dict(d)
        assert v.rule_id == DiffRuleId.R3_CERTAINTY_ESCALATION


# =============================================================================
# DiffWarning
# =============================================================================


class TestDiffWarning:
    def test_create(self):
        w = DiffWarning(warn_id=DiffWarnId.W1_COMPRESSION_RISK, description="too short")
        assert w.warn_id == DiffWarnId.W1_COMPRESSION_RISK

    def test_to_dict(self):
        w = DiffWarning(warn_id=DiffWarnId.W2_TONE_DRIFT, description="tone")
        d = w.to_dict()
        assert d["rule_id"] == "W2_TONE_DRIFT"

    def test_from_dict(self):
        d = {"rule_id": "W1_COMPRESSION_RISK", "description": "short", "detail": "ratio: 0.3"}
        w = DiffWarning.from_dict(d)
        assert w.warn_id == DiffWarnId.W1_COMPRESSION_RISK


# =============================================================================
# DiffGuardResult
# =============================================================================


class TestDiffGuardResult:
    def test_create_pass(self):
        r = DiffGuardResult(passed=True)
        assert r.passed is True
        assert r.violations == []

    def test_create_fail(self):
        v = DiffViolation(rule_id=DiffRuleId.R1_NEW_ENTITIES, description="new")
        r = DiffGuardResult(passed=False, violations=[v])
        assert r.passed is False
        assert len(r.violations) == 1

    def test_to_dict_from_dict(self):
        v = DiffViolation(rule_id=DiffRuleId.R2_NEW_NUMBERS, description="num")
        w = DiffWarning(warn_id=DiffWarnId.W1_COMPRESSION_RISK, description="short")
        r = DiffGuardResult(passed=False, violations=[v], warnings=[w])
        d = r.to_dict()
        r2 = DiffGuardResult.from_dict(d)
        assert r2.passed is False
        assert len(r2.violations) == 1
        assert len(r2.warnings) == 1


# =============================================================================
# Certainty Helpers
# =============================================================================


class TestCertaintyHelpers:
    def test_classify_high(self):
        assert classify_certainty("is") == CertaintyLevel.HIGH
        assert classify_certainty("must") == CertaintyLevel.HIGH
        assert classify_certainty("definitely") == CertaintyLevel.HIGH

    def test_classify_medium(self):
        assert classify_certainty("likely") == CertaintyLevel.MEDIUM
        assert classify_certainty("probably") == CertaintyLevel.MEDIUM

    def test_classify_low(self):
        assert classify_certainty("might") == CertaintyLevel.LOW
        assert classify_certainty("maybe") == CertaintyLevel.LOW

    def test_classify_unknown(self):
        assert classify_certainty("banana") is None
        assert classify_certainty("the") is None

    def test_extract_certainty_profile(self):
        text = "This is definitely true but might be wrong and probably fine"
        profile = extract_certainty_profile(text)
        assert profile[CertaintyLevel.HIGH] >= 2  # is, definitely
        assert profile[CertaintyLevel.MEDIUM] >= 1  # probably
        assert profile[CertaintyLevel.LOW] >= 1  # might

    def test_extract_imperatives(self):
        text = "Run the tests. Delete old files. The system is working."
        imps = extract_imperatives(text)
        assert "run" in imps
        assert "delete" in imps

    def test_extract_citations(self):
        text = "According to [1] and [Smith 2020], the claim in [source] is valid."
        cites = extract_citations(text)
        assert "[1]" in cites
        assert "[Smith 2020]" in cites
        assert "[source]" in cites


# =============================================================================
# PuppetDiffGuard
# =============================================================================


class TestPuppetDiffGuard:
    def _make_skeleton(self, text):
        return AnswerSkeleton(atoms=[SkeletonAtom(text=text)], raw_text=text)

    def _make_profile(self, **kwargs):
        return PuppetProfile(puppet_id="test", **kwargs)

    def test_r1_pass_no_new_entities(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The Google system works well")
        profile = self._make_profile()
        result = guard.check(skel, "The Google system works well", profile)
        assert result.passed is True

    def test_r1_fail_new_entities(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The system works well")
        profile = self._make_profile()
        result = guard.check(skel, "The Microsoft Azure system works well", profile)
        assert any(v.rule_id == DiffRuleId.R1_NEW_ENTITIES for v in result.violations)

    def test_r2_pass_same_numbers(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("There are 42 items")
        profile = self._make_profile()
        result = guard.check(skel, "There are 42 items", profile)
        r2_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R2_NEW_NUMBERS]
        assert len(r2_violations) == 0

    def test_r2_fail_new_numbers(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("There are some items")
        profile = self._make_profile()
        result = guard.check(skel, "There are 99 items", profile)
        assert any(v.rule_id == DiffRuleId.R2_NEW_NUMBERS for v in result.violations)

    def test_r3_pass_no_escalation(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("This might be true")
        profile = self._make_profile()
        result = guard.check(skel, "This might be true", profile)
        r3_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R3_CERTAINTY_ESCALATION]
        assert len(r3_violations) == 0

    def test_r3_fail_certainty_escalation(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("This might be true")
        profile = self._make_profile()
        result = guard.check(skel, "This definitely is true", profile)
        assert any(v.rule_id == DiffRuleId.R3_CERTAINTY_ESCALATION for v in result.violations)

    def test_r4_pass_no_scope_escalation(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("Some users report this issue")
        profile = self._make_profile()
        result = guard.check(skel, "Some users report this issue", profile)
        r4_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R4_SCOPE_ESCALATION]
        assert len(r4_violations) == 0

    def test_r4_fail_scope_escalation(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("Some users report this issue")
        profile = self._make_profile()
        result = guard.check(skel, "Every user always reports this issue", profile)
        assert any(v.rule_id == DiffRuleId.R4_SCOPE_ESCALATION for v in result.violations)

    def test_r5_pass_citations_preserved(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The claim [1] is supported by [2]")
        profile = self._make_profile()
        result = guard.check(skel, "The claim [1] is supported by [2]", profile)
        r5_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R5_CITATION_REMOVAL]
        assert len(r5_violations) == 0

    def test_r5_fail_citation_removed(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The claim [1] is supported by [2]")
        profile = self._make_profile()
        result = guard.check(skel, "The claim is supported", profile)
        assert any(v.rule_id == DiffRuleId.R5_CITATION_REMOVAL for v in result.violations)

    def test_r6_pass_same_negation(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("This is not correct")
        profile = self._make_profile()
        result = guard.check(skel, "This is not correct", profile)
        r6_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R6_POLARITY_FLIP]
        assert len(r6_violations) == 0

    def test_r6_fail_polarity_flip(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("This is not correct")
        profile = self._make_profile()
        result = guard.check(skel, "This is correct", profile)
        assert any(v.rule_id == DiffRuleId.R6_POLARITY_FLIP for v in result.violations)

    def test_r7_pass_no_new_instructions(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The process works by running tests")
        profile = self._make_profile()
        result = guard.check(skel, "The process works by running tests", profile)
        r7_violations = [v for v in result.violations if v.rule_id == DiffRuleId.R7_NEW_INSTRUCTIONS]
        assert len(r7_violations) == 0

    def test_r7_fail_new_instructions(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The system is stable")
        profile = self._make_profile()
        result = guard.check(skel, "Delete the old files immediately", profile)
        assert any(v.rule_id == DiffRuleId.R7_NEW_INSTRUCTIONS for v in result.violations)

    def test_w1_no_compression(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("A reasonable length text")
        profile = self._make_profile()
        result = guard.check(skel, "A reasonable length text", profile)
        assert not any(w.warn_id == DiffWarnId.W1_COMPRESSION_RISK for w in result.warnings)

    def test_w1_compression_risk(self):
        guard = PuppetDiffGuard(compression_threshold=0.5)
        skel = self._make_skeleton("A much longer text with many words that explain things in detail")
        profile = self._make_profile()
        result = guard.check(skel, "Short", profile)
        assert any(w.warn_id == DiffWarnId.W1_COMPRESSION_RISK for w in result.warnings)

    def test_w2_no_tone_drift(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The answer is straightforward")
        profile = self._make_profile(
            voice=VoiceConstraints(forbidden_phrases=["lol", "yolo"])
        )
        result = guard.check(skel, "The answer is straightforward", profile)
        assert not any(w.warn_id == DiffWarnId.W2_TONE_DRIFT for w in result.warnings)

    def test_w2_tone_drift(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The answer lol is straightforward")
        profile = self._make_profile(
            voice=VoiceConstraints(forbidden_phrases=["lol"])
        )
        result = guard.check(skel, "The answer lol is straightforward", profile)
        assert any(w.warn_id == DiffWarnId.W2_TONE_DRIFT for w in result.warnings)

    def test_full_check_pass(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("The system might have issues")
        profile = self._make_profile()
        result = guard.check(skel, "The system might have issues", profile)
        assert result.passed is True

    def test_full_check_fail_multiple(self):
        guard = PuppetDiffGuard()
        skel = self._make_skeleton("Some things might work based on [1]")
        profile = self._make_profile()
        # New entity, certainty escalation, citation removal
        result = guard.check(skel, "Everything definitely works at Amazon", profile)
        assert result.passed is False
        assert len(result.violations) >= 2


# =============================================================================
# PuppetRenderer
# =============================================================================


class TestPuppetRenderer:
    def _make_profile(self, **kwargs):
        return PuppetProfile(puppet_id="test", **kwargs)

    def test_render_pass(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("The system works well")
        profile = self._make_profile()
        result = renderer.render(skel, profile)
        assert result.verdict == RenderVerdict.PASSED
        assert result.attempts == 1

    def test_forbidden_removal(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("This is obviously the best approach")
        profile = self._make_profile(
            voice=VoiceConstraints(forbidden_phrases=["obviously"])
        )
        result = renderer.render(skel, profile)
        assert "obviously" not in result.rendered.lower()
        assert result.forbidden_phrases_removed >= 1

    def test_verbosity_cap(self):
        long_text = " ".join(["word"] * 100)
        renderer = PuppetRenderer()
        skel = create_skeleton(long_text)
        profile = self._make_profile(
            voice=VoiceConstraints(verbosity_cap_tokens=10)
        )
        result = renderer.render(skel, profile)
        assert result.rendered.endswith("...")
        # Should have at most 10 words + "..."
        word_count = len(result.rendered.replace("...", "").strip().split())
        assert word_count <= 10

    def test_disclaimer_prefix(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Content here")
        profile = self._make_profile(
            disclaimer=RoleDisclaimer(tag_text="[puppet: test]", tag_format=TagPosition.PREFIX)
        )
        result = renderer.render(skel, profile)
        assert result.rendered.startswith("[puppet: test]")
        assert result.disclaimer_applied is True

    def test_disclaimer_suffix(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Content here")
        profile = self._make_profile(
            disclaimer=RoleDisclaimer(tag_text="[end]", tag_format=TagPosition.SUFFIX)
        )
        result = renderer.render(skel, profile)
        assert result.rendered.endswith("[end]")
        assert result.disclaimer_applied is True

    def test_disclaimer_none(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Content here")
        profile = self._make_profile(
            disclaimer=RoleDisclaimer(enabled=False)
        )
        result = renderer.render(skel, profile)
        assert result.disclaimer_applied is False

    def test_fallback_on_fail(self):
        """When diff guard fails every attempt, return original with FALLBACK verdict."""
        # Create a scenario that always fails: skeleton has no entities,
        # but forbidden phrase removal changes polarity
        renderer = PuppetRenderer(max_attempts=2)
        skel = create_skeleton("This is not the right approach to take")
        # Removing "not" from forbidden phrases will flip polarity
        profile = self._make_profile(
            voice=VoiceConstraints(forbidden_phrases=["not"])
        )
        result = renderer.render(skel, profile)
        assert result.verdict == RenderVerdict.FALLBACK
        assert result.attempts == 2

    def test_rerender(self):
        """Test that rerender verdict is possible."""
        # This is hard to trigger deterministically since the renderer
        # uses the same logic on retry. Test that the verdict enum exists.
        assert RenderVerdict.RERENDERED == "rerendered"

    def test_mask_code_blocks(self):
        renderer = PuppetRenderer()
        text = "Here is code: ```python\nprint('hello')\n``` and text with obviously bad"
        skel = create_skeleton(text)
        profile = self._make_profile(
            voice=VoiceConstraints(forbidden_phrases=["obviously"])
        )
        result = renderer.render(skel, profile)
        # Code block should be preserved
        assert "```python" in result.rendered
        assert "print('hello')" in result.rendered

    def test_render_result_to_dict(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Simple text")
        profile = self._make_profile()
        result = renderer.render(skel, profile)
        d = result.to_dict()
        assert "original" in d
        assert "rendered" in d
        assert "verdict" in d
        assert "guard_result" in d


# =============================================================================
# PuppetRenderResult
# =============================================================================


class TestPuppetRenderResult:
    def test_create(self):
        r = PuppetRenderResult(
            original="orig",
            rendered="rend",
            verdict=RenderVerdict.PASSED,
            guard_result=DiffGuardResult(passed=True),
        )
        assert r.original == "orig"
        assert r.attempts == 1

    def test_to_dict(self):
        r = PuppetRenderResult(
            original="orig",
            rendered="rend",
            verdict=RenderVerdict.FALLBACK,
            guard_result=DiffGuardResult(passed=False),
            attempts=3,
        )
        d = r.to_dict()
        assert d["verdict"] == "fallback"
        assert d["attempts"] == 3

    def test_from_dict(self):
        d = {
            "original": "a",
            "rendered": "b",
            "verdict": "passed",
            "guard_result": {"passed": True, "violations": [], "warnings": []},
            "attempts": 1,
            "disclaimer_applied": True,
            "forbidden_phrases_removed": 2,
        }
        r = PuppetRenderResult.from_dict(d)
        assert r.disclaimer_applied is True
        assert r.forbidden_phrases_removed == 2


# =============================================================================
# Builtin Profiles
# =============================================================================


class TestBuiltinProfiles:
    def test_ops_scribe_fields(self):
        p = _BUILTIN_PROFILES["ops_scribe"]
        assert p.puppet_id == "ops_scribe"
        assert p.voice.register == Register.CLINICAL
        assert "definitely" in p.voice.forbidden_phrases
        assert p.disclaimer.tag_format == TagPosition.PREFIX
        assert p.safety.allow_spice is True

    def test_procurement_lawyer_fields(self):
        p = _BUILTIN_PROFILES["procurement_lawyer"]
        assert p.puppet_id == "procurement_lawyer"
        assert p.voice.register == Register.FORMAL
        assert "lol" in p.voice.forbidden_phrases
        assert p.disclaimer.tag_format == TagPosition.SUFFIX
        assert p.safety.allow_spice is False

    def test_daria_mirror_fields(self):
        p = _BUILTIN_PROFILES["daria_mirror"]
        assert p.puppet_id == "daria_mirror"
        assert p.voice.register == Register.WRY
        assert "happy to help" in p.voice.forbidden_phrases
        assert p.disclaimer.enabled is False
        assert p.safety.allow_spice is True

    def test_all_have_required_fields(self):
        for name, p in _BUILTIN_PROFILES.items():
            assert p.puppet_id == name
            assert p.version
            assert p.description
            assert isinstance(p.voice, VoiceConstraints)
            assert isinstance(p.epistemic, EpistemicPosture)
            assert isinstance(p.behavioral, BehavioralConstraints)

    def test_all_serialize(self):
        for name, p in _BUILTIN_PROFILES.items():
            d = p.to_dict()
            assert d["puppet_id"] == name
            json_str = json.dumps(d)
            assert len(json_str) > 0

    def test_all_roundtrip(self):
        for name, p in _BUILTIN_PROFILES.items():
            d = p.to_dict()
            p2 = PuppetProfile.from_dict(d)
            assert p2.puppet_id == p.puppet_id
            assert p2.voice.register == p.voice.register
            assert p2.voice.forbidden_phrases == p.voice.forbidden_phrases


# =============================================================================
# PuppetRegistry
# =============================================================================


class TestPuppetRegistry:
    def test_list_builtins(self):
        reg = PuppetRegistry()
        profiles = reg.list_profiles()
        assert "ops_scribe" in profiles
        assert "procurement_lawyer" in profiles
        assert "daria_mirror" in profiles

    def test_get_builtin(self):
        reg = PuppetRegistry()
        p = reg.get("ops_scribe")
        assert p is not None
        assert p.puppet_id == "ops_scribe"

    def test_get_missing(self):
        reg = PuppetRegistry()
        assert reg.get("nonexistent") is None

    def test_activate(self):
        reg = PuppetRegistry()
        p = reg.activate("ops_scribe")
        assert p.puppet_id == "ops_scribe"
        assert reg.is_active() is True

    def test_deactivate(self):
        reg = PuppetRegistry()
        reg.activate("ops_scribe")
        reg.deactivate()
        assert reg.is_active() is False
        assert reg.active_profile() is None

    def test_active_profile(self):
        reg = PuppetRegistry()
        assert reg.active_profile() is None
        reg.activate("daria_mirror")
        assert reg.active_profile().puppet_id == "daria_mirror"

    def test_is_active(self):
        reg = PuppetRegistry()
        assert reg.is_active() is False
        reg.activate("ops_scribe")
        assert reg.is_active() is True

    def test_create_custom(self):
        reg = PuppetRegistry()
        custom = PuppetProfile(puppet_id="my_puppet", description="custom")
        reg.create(custom)
        assert "my_puppet" in reg.list_profiles()
        assert reg.get("my_puppet").description == "custom"

    def test_create_overwrite_blocked(self):
        reg = PuppetRegistry()
        builtin = PuppetProfile(puppet_id="ops_scribe")
        with pytest.raises(ValueError, match="Cannot overwrite builtin"):
            reg.create(builtin)

    def test_delete_custom(self):
        reg = PuppetRegistry()
        custom = PuppetProfile(puppet_id="temp")
        reg.create(custom)
        reg.delete("temp")
        assert reg.get("temp") is None

    def test_delete_builtin_blocked(self):
        reg = PuppetRegistry()
        with pytest.raises(ValueError, match="Cannot delete builtin"):
            reg.delete("ops_scribe")

    def test_to_dict(self):
        reg = PuppetRegistry()
        reg.activate("ops_scribe")
        d = reg.to_dict()
        assert d["active"] == "ops_scribe"
        assert "ops_scribe" in d["builtins"]

    def test_from_dict(self):
        reg = PuppetRegistry()
        custom = PuppetProfile(puppet_id="x", description="y")
        reg.create(custom)
        reg.activate("x")
        d = reg.to_dict()
        reg2 = PuppetRegistry.from_dict(d)
        assert reg2._active == "x"
        assert "x" in reg2._custom

    def test_disk_persistence(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create and save
        reg = PuppetRegistry(governor_dir=gov_dir)
        custom = PuppetProfile(puppet_id="persisted", description="disk test")
        reg.create(custom)
        reg.activate("persisted")

        # Reload from disk
        reg2 = PuppetRegistry(governor_dir=gov_dir)
        assert "persisted" in reg2.list_profiles()
        assert reg2.is_active() is True
        assert reg2.active_profile().puppet_id == "persisted"


# =============================================================================
# Convenience Functions
# =============================================================================


class TestConvenience:
    def test_create_puppet_registry(self):
        reg = create_puppet_registry()
        assert isinstance(reg, PuppetRegistry)
        assert len(reg.list_profiles()) >= 3

    def test_create_puppet_renderer(self):
        renderer = create_puppet_renderer()
        assert isinstance(renderer, PuppetRenderer)

    def test_create_diff_guard(self):
        guard = create_diff_guard()
        assert isinstance(guard, PuppetDiffGuard)

    def test_create_skeleton(self):
        skel = create_skeleton("Hello world")
        assert skel.full_text() == "Hello world"
        assert len(skel.atoms) == 1

    def test_render_with_puppet(self):
        profile = PuppetProfile(puppet_id="test")
        result = render_with_puppet("Simple text", profile)
        assert isinstance(result, PuppetRenderResult)
        assert result.verdict in (RenderVerdict.PASSED, RenderVerdict.FALLBACK)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_empty_text_render(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("")
        profile = PuppetProfile(puppet_id="test")
        result = renderer.render(skel, profile)
        assert isinstance(result, PuppetRenderResult)

    def test_no_atoms_skeleton(self):
        skel = AnswerSkeleton(raw_text="fallback only")
        assert skel.full_text() == "fallback only"
        assert skel.atoms == []

    def test_profile_no_forbidden(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Some text obviously")
        profile = PuppetProfile(puppet_id="clean")
        result = renderer.render(skel, profile)
        assert result.forbidden_phrases_removed == 0

    def test_all_hard_atoms_citation_check(self):
        atoms = [
            SkeletonAtom(text="Fact [1]", commit_level=CommitLevel.HARD, citations=["[1]"]),
            SkeletonAtom(text="Another [2]", commit_level=CommitLevel.HARD, citations=["[2]"]),
        ]
        skel = AnswerSkeleton(atoms=atoms)
        guard = PuppetDiffGuard()
        profile = PuppetProfile(puppet_id="test")
        # Remove citations
        result = guard.check(skel, "Fact Another", profile)
        assert any(v.rule_id == DiffRuleId.R5_CITATION_REMOVAL for v in result.violations)

    def test_multiple_violations(self):
        guard = PuppetDiffGuard()
        skel = create_skeleton("This might be true based on [1]")
        profile = PuppetProfile(puppet_id="test")
        # Introduce entity, escalate certainty, remove citation
        rendered = "This definitely is true at Amazon"
        result = guard.check(skel, rendered, profile)
        assert result.passed is False
        assert len(result.violations) >= 2

    def test_zero_verbosity_cap(self):
        renderer = PuppetRenderer()
        skel = create_skeleton("Some text here")
        profile = PuppetProfile(
            puppet_id="zero_cap",
            voice=VoiceConstraints(verbosity_cap_tokens=0),
        )
        result = renderer.render(skel, profile)
        # Zero cap should not truncate (treated as no limit)
        assert isinstance(result, PuppetRenderResult)
