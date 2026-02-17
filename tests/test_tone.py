# SPDX-License-Identifier: Apache-2.0
"""
Tests for Tone Profiling (Phase T1 + T2).

Phase T1: ToneProfile dataclass, text analysis, tone checking,
guidance generation, and ToneManager persistence.

Phase T2: Corpus analysis, automatic extraction, profile comparison.
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
    ProfileDeviation,
    analyze_text,
    generate_tone_guidance,
    format_system_prompt,
    extract_tone_profile,
    compare_profiles,
    _count_syllables,
    _estimate_technical_density,
    _extract_ngram_patterns,
    _extract_opening_patterns,
    _extract_frequent_content_words,
    _classify_content_words,
    _STOP_WORDS,
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


# =============================================================================
# Phase T2: Corpus Analysis & Automatic Extraction
# =============================================================================


# Helper function tests
# =============================================================================


class TestCountSyllables:
    def test_one_syllable(self):
        assert _count_syllables("cat") == 1
        assert _count_syllables("the") == 1
        assert _count_syllables("dog") == 1

    def test_two_syllables(self):
        assert _count_syllables("happy") == 2
        assert _count_syllables("running") == 2

    def test_three_syllables(self):
        assert _count_syllables("beautiful") == 3
        assert _count_syllables("important") == 3

    def test_silent_e(self):
        assert _count_syllables("change") == 1
        assert _count_syllables("produce") == 2

    def test_empty(self):
        assert _count_syllables("") == 0

    def test_minimum_one(self):
        assert _count_syllables("x") >= 1


class TestEstimateTechnicalDensity:
    def test_simple_text(self):
        words = "the cat sat on the mat".split()
        density = _estimate_technical_density(words)
        assert density == 0.0  # No complex words

    def test_technical_text(self):
        words = "the implementation demonstrates architectural complexity in adversarial environments".split()
        density = _estimate_technical_density(words)
        assert density > 0.3  # Several complex words

    def test_empty(self):
        assert _estimate_technical_density([]) == 0.0

    def test_all_stop_words(self):
        words = "the and or but is are was were".split()
        assert _estimate_technical_density(words) == 0.0


class TestExtractNgramPatterns:
    def test_repeated_patterns(self):
        texts = [
            "The problem is simple.",
            "The problem is complex.",
            "Something else entirely.",
            "The problem is obvious.",
        ]
        patterns = _extract_ngram_patterns(texts, n=3, top_k=5)
        assert len(patterns) >= 1
        assert any("problem" in p.lower() for p in patterns)

    def test_no_repeats(self):
        texts = ["Alpha beta gamma.", "Delta epsilon zeta.", "Eta theta iota."]
        patterns = _extract_ngram_patterns(texts, n=3, top_k=5)
        assert len(patterns) == 0  # Nothing repeated more than once

    def test_empty(self):
        assert _extract_ngram_patterns([], n=3, top_k=5) == []


class TestExtractOpeningPatterns:
    def test_with_repeated_openings(self):
        paragraphs = [
            "The key insight here is important. More details follow.",
            "The key insight here is subtle. Even more to say.",
            "Something different entirely. No pattern.",
            "The key insight here is profound. Final thoughts.",
        ]
        patterns = _extract_opening_patterns(paragraphs)
        assert len(patterns) >= 1

    def test_no_patterns(self):
        paragraphs = ["Unique opening one.", "Different start two.", "Another thing three."]
        patterns = _extract_opening_patterns(paragraphs)
        assert len(patterns) == 0


class TestExtractFrequentContentWords:
    def test_basic(self):
        words = "system system system design design test test test test".split()
        frequent = _extract_frequent_content_words(words, _STOP_WORDS, top_n=5)
        assert "test" in frequent
        assert "system" in frequent
        assert "design" in frequent

    def test_filters_stop_words(self):
        words = "the the the and and and system".split()
        frequent = _extract_frequent_content_words(words, _STOP_WORDS, top_n=5)
        assert "the" not in frequent
        assert "and" not in frequent

    def test_filters_short_words(self):
        words = "is am on at it system design".split()
        frequent = _extract_frequent_content_words(words, _STOP_WORDS, top_n=5)
        for w in frequent:
            assert len(w) > 2


class TestClassifyContentWords:
    def test_adjective_detection(self):
        words = ["structural", "beautiful", "creative", "powerful", "system"]
        adjectives, verbs = _classify_content_words(words)
        assert "structural" in adjectives
        assert "beautiful" in adjectives
        assert "creative" in adjectives
        assert "powerful" in adjectives

    def test_verb_detection(self):
        words = ["organize", "stabilize", "integrate", "simplify", "system"]
        adjectives, verbs = _classify_content_words(words)
        assert "organize" in verbs or "stabilize" in verbs
        assert "simplify" in verbs

    def test_max_five_each(self):
        words = [
            "structural", "beautiful", "creative", "powerful", "functional",
            "logical", "additional", "organize", "stabilize", "integrate",
            "simplify", "purify", "normalize",
        ]
        adjectives, verbs = _classify_content_words(words)
        assert len(adjectives) <= 5
        assert len(verbs) <= 5


# extract_tone_profile tests
# =============================================================================


class TestExtractToneProfile:
    def _write_file(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content)
        return p

    def test_empty_file_list(self):
        profile = extract_tone_profile([])
        assert profile.name == "extracted"

    def test_single_file(self, tmp_path):
        f = self._write_file(tmp_path, "sample.md", (
            "This is a test sentence. Here is another one. "
            "And a third sentence with more words.\n\n"
            "Second paragraph here. It's got contractions. Don't you think?"
        ))
        profile = extract_tone_profile([f])
        assert profile.name == "extracted"
        assert profile.avg_sentence_length > 0
        assert profile.description == "Extracted from 1 reference file(s)"

    def test_multiple_files(self, tmp_path):
        f1 = self._write_file(tmp_path, "a.md", (
            "Short sentence. Another short one. Brief.\n\n"
            "Second paragraph. Also brief."
        ))
        f2 = self._write_file(tmp_path, "b.md", (
            "This is a much longer sentence with many more words in it. "
            "Another long sentence that goes on and on.\n\n"
            "Yet another paragraph. With somewhat longer sentences too."
        ))
        profile = extract_tone_profile([f1, f2])
        assert profile.description == "Extracted from 2 reference file(s)"
        # Average should be between the two files
        assert profile.avg_sentence_length > 0

    def test_empty_files_skipped(self, tmp_path):
        f1 = self._write_file(tmp_path, "empty.md", "")
        f2 = self._write_file(tmp_path, "good.md", "This has content. Real sentences here.")
        profile = extract_tone_profile([f1, f2])
        assert profile.description == "Extracted from 1 reference file(s)"

    def test_boolean_threshold(self, tmp_path):
        # 1 of 3 files uses fragments -- below 0.5 threshold, above 0.3 threshold
        f1 = self._write_file(tmp_path, "a.md", "Just so. Brief. No.")
        f2 = self._write_file(tmp_path, "b.md", "This is a complete sentence with many words. Here is another full sentence.")
        f3 = self._write_file(tmp_path, "c.md", "This has several complete sentences in it. They are all nicely formed sentences.")

        profile_low = extract_tone_profile([f1, f2, f3], bool_threshold=0.3)
        assert profile_low.uses_fragments is True  # 1/3 >= 0.3

        profile_high = extract_tone_profile([f1, f2, f3], bool_threshold=0.5)
        assert profile_high.uses_fragments is False  # 1/3 < 0.5

    def test_contractions_extracted(self, tmp_path):
        f = self._write_file(tmp_path, "contractions.md", (
            "It's a great system. Don't you think? We can't deny it."
        ))
        profile = extract_tone_profile([f])
        assert profile.contractions_frequency > 0.5

    def test_no_contractions_extracted(self, tmp_path):
        f = self._write_file(tmp_path, "formal.md", (
            "It is a great system. Do you not think so? We cannot deny it."
        ))
        profile = extract_tone_profile([f])
        assert profile.contractions_frequency < 0.5

    def test_em_dashes_detected(self, tmp_path):
        f = self._write_file(tmp_path, "dashes.md", (
            "The system\u2014when properly configured\u2014works well. "
            "Another sentence with an em dash\u2014like this."
        ))
        profile = extract_tone_profile([f])
        assert profile.uses_em_dashes is True

    def test_second_person_detected(self, tmp_path):
        f = self._write_file(tmp_path, "you.md", (
            "You should consider this approach. Your workflow will improve."
        ))
        profile = extract_tone_profile([f])
        assert profile.uses_second_person is True

    def test_technical_density(self, tmp_path):
        f = self._write_file(tmp_path, "technical.md", (
            "The implementation demonstrates architectural complexity. "
            "Adversarial environments require sophisticated countermeasures. "
            "Institutional resilience depends on organizational preparedness."
        ))
        profile = extract_tone_profile([f])
        assert profile.technical_density > 0.2

    def test_custom_name(self, tmp_path):
        f = self._write_file(tmp_path, "sample.md", "Some content here. More words.")
        profile = extract_tone_profile([f], name="my_voice")
        assert profile.name == "my_voice"

    def test_vocabulary_extraction(self, tmp_path):
        f = self._write_file(tmp_path, "vocab.md", (
            "The structural analysis reveals fundamental problems. "
            "Structural issues are often invisible. "
            "The structural integrity of the system is questionable. "
            "We must organize and stabilize the architecture."
        ))
        profile = extract_tone_profile([f])
        # Should extract some adjectives/verbs from frequent words
        assert isinstance(profile.favorite_adjectives, list)
        assert isinstance(profile.favorite_verbs, list)

    def test_all_empty_files(self, tmp_path):
        f1 = self._write_file(tmp_path, "a.md", "")
        f2 = self._write_file(tmp_path, "b.md", "   ")
        profile = extract_tone_profile([f1, f2])
        assert profile.name == "extracted"
        assert profile.avg_sentence_length == 18  # default

    def test_rhetorical_questions(self, tmp_path):
        f = self._write_file(tmp_path, "questions.md", (
            "Why do we build these systems? Because they matter. "
            "What happens when they fail? Everything breaks."
        ))
        profile = extract_tone_profile([f])
        assert profile.uses_rhetorical_questions is True

    def test_parentheticals(self, tmp_path):
        f = self._write_file(tmp_path, "parens.md", (
            "The approach (while unconventional) proved effective. "
            "Results (shown in Table 1) confirm this."
        ))
        profile = extract_tone_profile([f])
        assert profile.uses_parentheticals is True

    def test_colons_detected(self, tmp_path):
        f = self._write_file(tmp_path, "colons.md", (
            "The problem: Nobody pays attention. The solution: Automate everything."
        ))
        profile = extract_tone_profile([f])
        assert profile.uses_colons_for_emphasis is True


# ProfileDeviation tests
# =============================================================================


class TestProfileDeviation:
    def test_basic(self):
        d = ProfileDeviation(
            dimension="sentence_length",
            baseline_value=18,
            other_value=25,
            deviation=7.0,
            significant=True,
            message="sentence_length: 18 → 25 (Δ=7.00) [SIGNIFICANT]",
        )
        assert d.dimension == "sentence_length"
        assert d.significant is True

    def test_to_dict(self):
        d = ProfileDeviation(
            dimension="contractions",
            baseline_value=0.7,
            other_value=0.3,
            deviation=0.4,
            significant=True,
            message="contractions: 0.7 → 0.3",
        )
        data = d.to_dict()
        assert data["dimension"] == "contractions"
        assert data["deviation"] == 0.4
        assert data["significant"] is True


# compare_profiles tests
# =============================================================================


class TestCompareProfiles:
    def test_identical_profiles(self):
        p1 = ToneProfile(name="a")
        p2 = ToneProfile(name="b")
        deviations = compare_profiles(p1, p2)
        assert len(deviations) == 0

    def test_sentence_length_deviation(self):
        p1 = ToneProfile(avg_sentence_length=18)
        p2 = ToneProfile(avg_sentence_length=25)
        deviations = compare_profiles(p1, p2)
        length_devs = [d for d in deviations if d.dimension == "avg_sentence_length"]
        assert len(length_devs) == 1
        assert length_devs[0].significant is True  # 7 > 5 tolerance
        assert length_devs[0].deviation == 7.0

    def test_sentence_length_within_tolerance(self):
        p1 = ToneProfile(avg_sentence_length=18)
        p2 = ToneProfile(avg_sentence_length=21)
        deviations = compare_profiles(p1, p2)
        length_devs = [d for d in deviations if d.dimension == "avg_sentence_length"]
        assert len(length_devs) == 1
        assert length_devs[0].significant is False  # 3 <= 5 tolerance

    def test_contraction_deviation(self):
        p1 = ToneProfile(contractions_frequency=0.8)
        p2 = ToneProfile(contractions_frequency=0.3)
        deviations = compare_profiles(p1, p2, tolerance=0.2)
        contraction_devs = [d for d in deviations if d.dimension == "contractions_frequency"]
        assert len(contraction_devs) == 1
        assert contraction_devs[0].significant is True

    def test_boolean_deviation(self):
        p1 = ToneProfile(uses_fragments=True)
        p2 = ToneProfile(uses_fragments=False)
        deviations = compare_profiles(p1, p2)
        frag_devs = [d for d in deviations if d.dimension == "uses_fragments"]
        assert len(frag_devs) == 1
        assert frag_devs[0].significant is True
        assert frag_devs[0].deviation == 1.0

    def test_boolean_same_no_deviation(self):
        p1 = ToneProfile(uses_fragments=True)
        p2 = ToneProfile(uses_fragments=True)
        deviations = compare_profiles(p1, p2)
        frag_devs = [d for d in deviations if d.dimension == "uses_fragments"]
        assert len(frag_devs) == 0

    def test_string_deviation(self):
        p1 = ToneProfile(header_style="statement")
        p2 = ToneProfile(header_style="provocative")
        deviations = compare_profiles(p1, p2)
        style_devs = [d for d in deviations if d.dimension == "header_style"]
        assert len(style_devs) == 1
        assert style_devs[0].significant is True

    def test_multiple_deviations(self):
        p1 = ToneProfile(
            avg_sentence_length=18,
            uses_fragments=True,
            uses_em_dashes=True,
            contractions_frequency=0.8,
        )
        p2 = ToneProfile(
            avg_sentence_length=30,
            uses_fragments=False,
            uses_em_dashes=False,
            contractions_frequency=0.2,
        )
        deviations = compare_profiles(p1, p2)
        significant = [d for d in deviations if d.significant]
        assert len(significant) >= 4

    def test_tolerance_parameter(self):
        p1 = ToneProfile(contractions_frequency=0.5)
        p2 = ToneProfile(contractions_frequency=0.6)

        # With tight tolerance, this is significant
        devs_tight = compare_profiles(p1, p2, tolerance=0.05)
        sig_tight = [d for d in devs_tight if d.dimension == "contractions_frequency" and d.significant]
        assert len(sig_tight) == 1

        # With loose tolerance, this is not significant
        devs_loose = compare_profiles(p1, p2, tolerance=0.2)
        sig_loose = [d for d in devs_loose if d.dimension == "contractions_frequency" and d.significant]
        assert len(sig_loose) == 0

    def test_all_deviations_have_messages(self):
        p1 = ToneProfile(
            avg_sentence_length=10,
            uses_fragments=True,
            header_style="question",
        )
        p2 = ToneProfile(
            avg_sentence_length=20,
            uses_fragments=False,
            header_style="statement",
        )
        deviations = compare_profiles(p1, p2)
        for d in deviations:
            assert d.message
            assert d.dimension

    def test_technical_density_deviation(self):
        p1 = ToneProfile(technical_density=0.1)
        p2 = ToneProfile(technical_density=0.5)
        deviations = compare_profiles(p1, p2)
        td_devs = [d for d in deviations if d.dimension == "technical_density"]
        assert len(td_devs) == 1
        assert td_devs[0].significant is True  # 0.4 > 0.2

    def test_sarcasm_deviation(self):
        p1 = ToneProfile(sarcasm_frequency=0.0)
        p2 = ToneProfile(sarcasm_frequency=0.5)
        deviations = compare_profiles(p1, p2)
        sarc_devs = [d for d in deviations if d.dimension == "sarcasm_frequency"]
        assert len(sarc_devs) == 1
        assert sarc_devs[0].significant is True


# Integration: extract then compare
# =============================================================================


class TestExtractAndCompare:
    def test_extract_then_compare_identical(self, tmp_path):
        """Extracting a profile from text, then comparing the same text should yield few deviations."""
        text = (
            "You should always validate your assumptions. Don't skip this step. "
            "It's the most important part of the process.\n\n"
            "Why does this matter? Because unchecked assumptions lead to failures. "
            "Your system\u2014no matter how well designed\u2014will break without validation."
        )
        f = tmp_path / "reference.md"
        f.write_text(text)

        # Extract profile from reference
        baseline = extract_tone_profile([f], name="reference")

        # Compare the same text against the extracted profile
        checker = ToneChecker(baseline)
        result = checker.check(text)
        # Should mostly match since we extracted from the same text
        assert len(result.violations) <= 2  # Allow minor rounding differences

    def test_drift_detection(self, tmp_path):
        """Detect voice drift between conversational reference and formal new writing."""
        # Conversational reference
        ref = tmp_path / "reference.md"
        ref.write_text(
            "Here's the thing: you can't trust AI outputs blindly. Don't do it. "
            "It's a recipe for disaster\u2014and everyone knows it.\n\n"
            "Why? Because they hallucinate. They confabulate. They make things up."
        )

        # Formal new writing (drifted)
        new = tmp_path / "chapter5.md"
        new.write_text(
            "In this analysis, we examine the structural dynamics of information "
            "operations in the context of temporal coherence frameworks. The primary "
            "consideration is the relationship between adversarial persistence and "
            "institutional memory deficits."
        )

        baseline = extract_tone_profile([ref], name="my_voice")
        new_profile = extract_tone_profile([new], name="chapter5")
        deviations = compare_profiles(baseline, new_profile)
        significant = [d for d in deviations if d.significant]

        # Should detect multiple significant deviations
        assert len(significant) >= 2

    def test_consistent_voice(self, tmp_path):
        """Same-style writing should produce few significant deviations."""
        ref = tmp_path / "reference.md"
        ref.write_text(
            "The system processes data efficiently. It validates inputs carefully. "
            "Errors are logged and reported automatically.\n\n"
            "Performance matters. Reliability matters more. Both are achievable."
        )

        new = tmp_path / "new.md"
        new.write_text(
            "The module handles authentication securely. It checks credentials carefully. "
            "Failures are tracked and escalated automatically.\n\n"
            "Security matters. Correctness matters more. Both are necessary."
        )

        baseline = extract_tone_profile([ref])
        new_profile = extract_tone_profile([new])
        deviations = compare_profiles(baseline, new_profile)
        significant = [d for d in deviations if d.significant]

        # Similar style should produce few significant deviations
        assert len(significant) <= 3
