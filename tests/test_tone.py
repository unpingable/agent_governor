"""
Tests for Phase T1: ToneProfile & Manual Authoring.

Tests the ToneProfile dataclass, text analysis, tone checking,
guidance generation, and ToneManager persistence.
"""

import json
import pytest
from pathlib import Path

from nonfiction_governor.tone import (
    ToneProfile,
    ToneViolation,
    ToneCheckResult,
    ToneChecker,
    ToneManager,
    analyze_text,
    generate_tone_guidance,
    format_system_prompt,
)


# =============================================================================
# ToneProfile Dataclass
# =============================================================================


class TestToneProfile:
    def test_default_profile(self):
        p = ToneProfile()
        assert p.name == "default"
        assert p.avg_sentence_length == 18
        assert p.contractions_frequency == 0.5
        assert p.uses_fragments is False
        assert p.uses_em_dashes is False
        assert p.technical_density == 0.3

    def test_custom_profile(self):
        p = ToneProfile(
            name="conversational",
            avg_sentence_length=14,
            uses_fragments=True,
            uses_second_person=True,
            contractions_frequency=0.74,
            uses_em_dashes=True,
            sarcasm_frequency=0.4,
            opening_patterns=["Here's the thing:", "Let me be clear:"],
        )
        assert p.name == "conversational"
        assert p.avg_sentence_length == 14
        assert p.uses_fragments is True
        assert p.contractions_frequency == 0.74
        assert len(p.opening_patterns) == 2

    def test_clamping(self):
        p = ToneProfile(contractions_frequency=1.5, technical_density=-0.2, sarcasm_frequency=3.0)
        assert p.contractions_frequency == 1.0
        assert p.technical_density == 0.0
        assert p.sarcasm_frequency == 1.0

    def test_to_dict(self):
        p = ToneProfile(name="test", avg_sentence_length=20)
        d = p.to_dict()
        assert d["name"] == "test"
        assert d["avg_sentence_length"] == 20
        assert "created_at" in d
        assert "updated_at" in d

    def test_from_dict(self):
        d = {
            "name": "loaded",
            "avg_sentence_length": 22,
            "uses_fragments": True,
            "contractions_frequency": 0.8,
        }
        p = ToneProfile.from_dict(d)
        assert p.name == "loaded"
        assert p.avg_sentence_length == 22
        assert p.uses_fragments is True
        assert p.contractions_frequency == 0.8

    def test_from_dict_defaults(self):
        """from_dict should use defaults for missing fields."""
        p = ToneProfile.from_dict({})
        assert p.name == "default"
        assert p.avg_sentence_length == 18

    def test_roundtrip(self):
        p = ToneProfile(
            name="roundtrip",
            avg_sentence_length=16,
            uses_fragments=True,
            opening_patterns=["Note:", "The point:"],
            favorite_adjectives=["grim", "structural"],
        )
        p2 = ToneProfile.from_dict(p.to_dict())
        assert p2.name == p.name
        assert p2.avg_sentence_length == p.avg_sentence_length
        assert p2.uses_fragments == p.uses_fragments
        assert p2.opening_patterns == p.opening_patterns
        assert p2.favorite_adjectives == p.favorite_adjectives

    def test_save_and_load(self, tmp_path):
        p = ToneProfile(name="saved", avg_sentence_length=15, uses_em_dashes=True)
        path = tmp_path / "profile.json"
        p.save(path)
        assert path.exists()

        loaded = ToneProfile.load(path)
        assert loaded.name == "saved"
        assert loaded.avg_sentence_length == 15
        assert loaded.uses_em_dashes is True

    def test_save_creates_parent_dirs(self, tmp_path):
        p = ToneProfile(name="nested")
        path = tmp_path / "sub" / "dir" / "profile.json"
        p.save(path)
        assert path.exists()


# =============================================================================
# ToneViolation
# =============================================================================


class TestToneViolation:
    def test_basic(self):
        v = ToneViolation(
            dimension="sentence_length",
            message="Too long",
            expected=18,
            actual=25,
            suggestion="Break up sentences",
        )
        assert v.dimension == "sentence_length"
        assert v.expected == 18
        assert v.actual == 25

    def test_to_dict(self):
        v = ToneViolation(
            dimension="contractions",
            message="Too few",
            expected=0.74,
            actual=0.3,
        )
        d = v.to_dict()
        assert d["dimension"] == "contractions"
        assert d["expected"] == 0.74
        assert d["actual"] == 0.3


# =============================================================================
# ToneCheckResult
# =============================================================================


class TestToneCheckResult:
    def test_valid(self):
        r = ToneCheckResult(valid=True)
        assert r.valid is True
        assert len(r.violations) == 0

    def test_with_violations(self):
        r = ToneCheckResult(
            valid=False,
            violations=[
                ToneViolation("a", "msg", True, False),
                ToneViolation("b", "msg", 0.5, 0.1),
            ],
        )
        assert r.valid is False
        assert len(r.violations) == 2

    def test_to_dict(self):
        r = ToneCheckResult(
            valid=False,
            violations=[ToneViolation("a", "msg", True, False)],
            metrics={"word_count": 100},
        )
        d = r.to_dict()
        assert d["valid"] is False
        assert len(d["violations"]) == 1
        assert d["metrics"]["word_count"] == 100


# =============================================================================
# analyze_text()
# =============================================================================


class TestAnalyzeText:
    def test_empty_text(self):
        m = analyze_text("")
        assert m.get("empty") is True

    def test_basic_text(self):
        text = "This is a simple sentence. Here is another one. And a third."
        m = analyze_text(text)
        assert m["sentence_count"] == 3
        assert m["avg_sentence_length"] > 0
        assert m["word_count"] > 0

    def test_contractions_detected(self):
        text = "It's a great day. Don't you think? I won't argue."
        m = analyze_text(text)
        assert m["contractions_frequency"] > 0.5

    def test_no_contractions(self):
        text = "It is a great day. Do you not think so? I will not argue."
        m = analyze_text(text)
        assert m["contractions_frequency"] < 0.5

    def test_second_person(self):
        text = "You should consider this carefully. Your opinion matters."
        m = analyze_text(text)
        assert m["uses_second_person"] is True

    def test_no_second_person(self):
        text = "The system operates autonomously. It processes data efficiently."
        m = analyze_text(text)
        assert m["uses_second_person"] is False

    def test_first_person(self):
        text = "I believe this is correct. My analysis shows it."
        m = analyze_text(text)
        assert m["uses_first_person"] is True

    def test_em_dashes(self):
        text = "The system\u2014when properly configured\u2014works well."
        m = analyze_text(text)
        assert m["uses_em_dashes"] is True

    def test_double_dash_em_dashes(self):
        text = "The system--when properly configured--works well."
        m = analyze_text(text)
        assert m["uses_em_dashes"] is True

    def test_ellipses(self):
        text = "And then it happened... the system failed."
        m = analyze_text(text)
        assert m["uses_ellipses"] is True

    def test_parentheticals(self):
        text = "The approach (while unconventional) proved effective."
        m = analyze_text(text)
        assert m["uses_parentheticals"] is True

    def test_rhetorical_questions(self):
        text = "Why would anyone design it this way? The answer is simple."
        m = analyze_text(text)
        assert m["uses_rhetorical_questions"] is True

    def test_colon_emphasis(self):
        text = "The problem: nobody noticed. The solution: Automate it."
        m = analyze_text(text)
        assert m["uses_colons_for_emphasis"] is True

    def test_single_sentence_paragraphs(self):
        text = "First paragraph with content.\n\nAlone.\n\nThird paragraph here."
        m = analyze_text(text)
        assert m["uses_single_sentence_paragraphs"] is True

    def test_paragraph_count(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        m = analyze_text(text)
        assert m["paragraph_count"] == 3


# =============================================================================
# ToneChecker
# =============================================================================


class TestToneChecker:
    def test_matching_text_passes(self):
        profile = ToneProfile(avg_sentence_length=5, contractions_frequency=0.5)
        checker = ToneChecker(profile)
        text = "Short words here. Yes indeed. More words too."
        result = checker.check(text)
        # Should not have sentence length violation (within 5-word tolerance)
        length_violations = [v for v in result.violations if v.dimension == "sentence_length"]
        assert len(length_violations) == 0

    def test_sentence_length_violation(self):
        profile = ToneProfile(avg_sentence_length=5)
        checker = ToneChecker(profile)
        text = (
            "This is a very long sentence that goes on and on and on and on and on. "
            "Another very long sentence that continues for quite a while indeed."
        )
        result = checker.check(text)
        length_violations = [v for v in result.violations if v.dimension == "sentence_length"]
        assert len(length_violations) == 1

    def test_missing_fragments_violation(self):
        profile = ToneProfile(uses_fragments=True)
        checker = ToneChecker(profile)
        text = "This is a complete sentence. Here is another complete sentence."
        result = checker.check(text)
        fragment_violations = [v for v in result.violations if v.dimension == "fragments"]
        assert len(fragment_violations) == 1

    def test_missing_second_person_violation(self):
        profile = ToneProfile(uses_second_person=True)
        checker = ToneChecker(profile)
        text = "The system works well. It processes data efficiently."
        result = checker.check(text)
        voice_violations = [v for v in result.violations if v.dimension == "second_person"]
        assert len(voice_violations) == 1

    def test_contraction_frequency_violation(self):
        profile = ToneProfile(contractions_frequency=0.8)
        checker = ToneChecker(profile, tolerance=0.2)
        text = "It is a test. I will not do it. She does not care."
        result = checker.check(text)
        contraction_violations = [v for v in result.violations if v.dimension == "contractions"]
        assert len(contraction_violations) == 1

    def test_missing_em_dashes_violation(self):
        profile = ToneProfile(uses_em_dashes=True)
        checker = ToneChecker(profile)
        text = "A simple sentence. Another simple sentence."
        result = checker.check(text)
        dash_violations = [v for v in result.violations if v.dimension == "em_dashes"]
        assert len(dash_violations) == 1

    def test_empty_text_passes(self):
        profile = ToneProfile(uses_fragments=True, uses_em_dashes=True)
        checker = ToneChecker(profile)
        result = checker.check("")
        assert result.valid is True

    def test_violations_have_suggestions(self):
        profile = ToneProfile(uses_fragments=True, uses_second_person=True)
        checker = ToneChecker(profile)
        text = "The system operates. It works well."
        result = checker.check(text)
        for v in result.violations:
            assert v.suggestion  # All violations should have suggestions

    def test_all_dimensions_can_be_checked(self):
        """Profile with everything enabled, text with nothing."""
        profile = ToneProfile(
            uses_fragments=True,
            uses_second_person=True,
            uses_first_person=True,
            uses_em_dashes=True,
            uses_rhetorical_questions=True,
            uses_parentheticals=True,
            contractions_frequency=0.9,
        )
        checker = ToneChecker(profile)
        text = "The system operates. It works efficiently."
        result = checker.check(text)
        assert not result.valid
        dimensions = {v.dimension for v in result.violations}
        assert "second_person" in dimensions
        assert "first_person" in dimensions
        assert "em_dashes" in dimensions
        assert "rhetorical_questions" in dimensions
        assert "parentheticals" in dimensions

    def test_tolerance_affects_contractions(self):
        profile = ToneProfile(contractions_frequency=0.5)
        # With high tolerance, small deviations pass
        checker = ToneChecker(profile, tolerance=0.5)
        text = "It is fine. She does not mind. He will not care."
        result = checker.check(text)
        contraction_violations = [v for v in result.violations if v.dimension == "contractions"]
        assert len(contraction_violations) == 0  # Within tolerance


# =============================================================================
# generate_tone_guidance()
# =============================================================================


class TestGenerateToneGuidance:
    def test_basic_guidance(self):
        profile = ToneProfile(avg_sentence_length=18, technical_density=0.35)
        guidance = generate_tone_guidance(profile)
        assert "18 words" in guidance
        assert "35%" in guidance

    def test_fragments_guidance(self):
        profile = ToneProfile(uses_fragments=True)
        guidance = generate_tone_guidance(profile)
        assert "fragments" in guidance.lower()

    def test_second_person_guidance(self):
        profile = ToneProfile(uses_second_person=True)
        guidance = generate_tone_guidance(profile)
        assert "you" in guidance.lower()

    def test_contractions_high(self):
        profile = ToneProfile(contractions_frequency=0.8)
        guidance = generate_tone_guidance(profile)
        assert "contractions" in guidance.lower()
        assert "frequently" in guidance.lower()

    def test_contractions_low(self):
        profile = ToneProfile(contractions_frequency=0.2)
        guidance = generate_tone_guidance(profile)
        assert "sparingly" in guidance.lower()

    def test_em_dashes_guidance(self):
        profile = ToneProfile(uses_em_dashes=True)
        guidance = generate_tone_guidance(profile)
        assert "em dash" in guidance.lower()

    def test_opening_patterns_included(self):
        profile = ToneProfile(opening_patterns=["Here's the thing:", "Let me be clear:"])
        guidance = generate_tone_guidance(profile)
        assert "Here's the thing:" in guidance

    def test_sarcasm_guidance(self):
        profile = ToneProfile(sarcasm_frequency=0.5)
        guidance = generate_tone_guidance(profile)
        assert "sarcasm" in guidance.lower()

    def test_profanity_guidance(self):
        profile = ToneProfile(uses_profanity=True)
        guidance = generate_tone_guidance(profile)
        assert "profanity" in guidance.lower()

    def test_custom_guidance_appended(self):
        profile = ToneProfile(custom_guidance="Always end with a punch line.")
        guidance = generate_tone_guidance(profile)
        assert "punch line" in guidance

    def test_provocative_headers(self):
        profile = ToneProfile(header_style="provocative")
        guidance = generate_tone_guidance(profile)
        assert "provocative" in guidance.lower()

    def test_lists_sparingly(self):
        profile = ToneProfile(uses_lists="sparingly")
        guidance = generate_tone_guidance(profile)
        assert "sparingly" in guidance.lower()

    def test_favorite_words(self):
        profile = ToneProfile(
            favorite_adjectives=["grim", "structural"],
            favorite_verbs=["fails", "collapses"],
        )
        guidance = generate_tone_guidance(profile)
        assert "grim" in guidance
        assert "fails" in guidance


# =============================================================================
# format_system_prompt()
# =============================================================================


class TestFormatSystemPrompt:
    def test_includes_name(self):
        profile = ToneProfile(name="my_voice")
        prompt = format_system_prompt(profile)
        assert "my_voice" in prompt

    def test_includes_guidance(self):
        profile = ToneProfile(uses_fragments=True)
        prompt = format_system_prompt(profile)
        assert "fragments" in prompt.lower()

    def test_includes_warning(self):
        profile = ToneProfile()
        prompt = format_system_prompt(profile)
        assert "generic AI prose" in prompt


# =============================================================================
# ToneManager
# =============================================================================


class TestToneManager:
    def test_no_profile_initially(self, tmp_path):
        manager = ToneManager(tmp_path)
        assert manager.has_profile is False
        assert manager.profile is None

    def test_set_and_get_profile(self, tmp_path):
        manager = ToneManager(tmp_path)
        profile = ToneProfile(name="test", avg_sentence_length=20)
        manager.set_profile(profile)
        assert manager.has_profile is True
        assert manager.profile.name == "test"
        assert manager.profile.avg_sentence_length == 20

    def test_persistence(self, tmp_path):
        manager1 = ToneManager(tmp_path)
        manager1.set_profile(ToneProfile(name="persisted", uses_em_dashes=True))

        # New manager should load from disk
        manager2 = ToneManager(tmp_path)
        assert manager2.has_profile is True
        assert manager2.profile.name == "persisted"
        assert manager2.profile.uses_em_dashes is True

    def test_clear_profile(self, tmp_path):
        manager = ToneManager(tmp_path)
        manager.set_profile(ToneProfile(name="to_clear"))
        manager.clear_profile()
        assert manager.has_profile is False
        assert manager.profile is None

    def test_lock_unlock(self, tmp_path):
        manager = ToneManager(tmp_path)
        manager.set_profile(ToneProfile(name="lockable"))
        assert manager.is_locked is False

        manager.lock()
        assert manager.is_locked is True

        manager.unlock()
        assert manager.is_locked is False

    def test_check_text(self, tmp_path):
        manager = ToneManager(tmp_path)
        manager.set_profile(ToneProfile(uses_second_person=True))
        result = manager.check_text("The system works well.")
        assert result.valid is False

    def test_check_text_no_profile(self, tmp_path):
        manager = ToneManager(tmp_path)
        result = manager.check_text("Any text.")
        assert result.valid is True

    def test_get_guidance(self, tmp_path):
        manager = ToneManager(tmp_path)
        manager.set_profile(ToneProfile(uses_fragments=True))
        guidance = manager.get_guidance()
        assert "fragments" in guidance.lower()

    def test_get_guidance_no_profile(self, tmp_path):
        manager = ToneManager(tmp_path)
        assert manager.get_guidance() == ""

    def test_get_system_prompt(self, tmp_path):
        manager = ToneManager(tmp_path)
        manager.set_profile(ToneProfile(name="my_voice"))
        prompt = manager.get_system_prompt()
        assert "my_voice" in prompt

    def test_get_system_prompt_no_profile(self, tmp_path):
        manager = ToneManager(tmp_path)
        assert manager.get_system_prompt() == ""


# =============================================================================
# Integration: Full workflow
# =============================================================================


class TestFullWorkflow:
    def test_create_check_modify(self, tmp_path):
        """Create profile, check text, get violations, get guidance."""
        manager = ToneManager(tmp_path)

        # Create a conversational profile
        profile = ToneProfile(
            name="conversational",
            avg_sentence_length=14,
            uses_fragments=True,
            uses_second_person=True,
            contractions_frequency=0.74,
            uses_em_dashes=True,
            sarcasm_frequency=0.4,
            technical_density=0.35,
            opening_patterns=["Here's the thing:"],
        )
        manager.set_profile(profile)

        # Check formal text (should have violations)
        formal_text = (
            "In this analysis, we examine the structural dynamics of information "
            "operations in the context of temporal coherence frameworks. The primary "
            "consideration is the relationship between adversarial persistence and "
            "institutional memory deficits."
        )
        result = manager.check_text(formal_text)
        assert not result.valid
        dimensions = {v.dimension for v in result.violations}
        assert "second_person" in dimensions  # No "you"
        assert "em_dashes" in dimensions  # No em dashes
        assert "fragments" in dimensions  # No fragments

        # Get guidance for fixing
        guidance = manager.get_guidance()
        assert "you" in guidance.lower()
        assert "fragments" in guidance.lower()
        assert "em dash" in guidance.lower()

    def test_json_roundtrip_workflow(self, tmp_path):
        """Save profile to JSON, load it, check it works."""
        profile = ToneProfile(
            name="from_json",
            uses_profanity=True,
            contractions_frequency=0.8,
            custom_guidance="Always be direct.",
        )

        # Save to JSON
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps(profile.to_dict(), indent=2))

        # Load and use
        loaded = ToneProfile.load(json_path)
        assert loaded.name == "from_json"
        assert loaded.uses_profanity is True
        assert loaded.custom_guidance == "Always be direct."

        guidance = generate_tone_guidance(loaded)
        assert "profanity" in guidance.lower()
        assert "Always be direct." in guidance
