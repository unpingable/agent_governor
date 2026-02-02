"""Tests for continuity_bridges: mode-specific anchor factories."""

import pytest

from governor.continuity import Anchor, AnchorType, Severity
from governor.continuity_bridges import (
    anchors_from_characters,
    anchors_from_banned_tropes,
    anchors_from_world_rules,
    anchors_from_tone_settings,
    anchors_from_fiction_bible,
    anchors_from_concepts,
    anchors_from_positions,
    anchors_from_nonfiction_corpus,
    anchors_from_puppet_profile,
)


# =============================================================================
# TestAnchorsFromCharacters
# =============================================================================


class TestAnchorsFromCharacters:
    """Tests for anchors_from_characters."""

    def test_anti_patterns_creates_prohibition(self) -> None:
        chars = [{"name": "Alice", "anti_patterns": ["betray her friends"]}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.PROHIBITION
        assert "betray her friends" in anchors[0].forbidden_patterns

    def test_voice_avoid_creates_persona(self) -> None:
        chars = [{"name": "Bob", "voice": {"avoid": ["slang", "profanity"]}}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.PERSONA
        assert anchors[0].forbidden_patterns == ["slang", "profanity"]

    def test_both_anti_and_voice(self) -> None:
        chars = [{
            "name": "Carol",
            "anti_patterns": ["run away"],
            "voice": {"avoid": ["um", "like"]},
        }]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 2

    def test_empty_anti_patterns_skipped(self) -> None:
        chars = [{"name": "Dave", "anti_patterns": []}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 0

    def test_no_voice_key_skipped(self) -> None:
        chars = [{"name": "Eve"}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 0

    def test_id_format(self) -> None:
        chars = [{"name": "Mr Foo", "anti_patterns": ["x"]}]
        anchors = anchors_from_characters(chars)
        assert anchors[0].id == "fiction_char_mr_foo_anti"

    def test_severity_anti_is_correct(self) -> None:
        chars = [{"name": "A", "anti_patterns": ["x"]}]
        anchors = anchors_from_characters(chars)
        assert anchors[0].severity == Severity.CORRECT

    def test_source_field(self) -> None:
        chars = [{"name": "A", "anti_patterns": ["x"]}]
        anchors = anchors_from_characters(chars)
        assert anchors[0].source == "fiction_bridge"

    def test_multiple_characters(self) -> None:
        chars = [
            {"name": "A", "anti_patterns": ["x"]},
            {"name": "B", "voice": {"avoid": ["y"]}},
            {"name": "C", "anti_patterns": ["z"], "voice": {"avoid": ["w"]}},
        ]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 4

    def test_voice_with_no_avoid(self) -> None:
        chars = [{"name": "D", "voice": {"dialogue": "terse"}}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 0


# =============================================================================
# TestAnchorsFromBannedTropes
# =============================================================================


class TestAnchorsFromBannedTropes:
    """Tests for anchors_from_banned_tropes."""

    def test_patterns_create_prohibition(self) -> None:
        tropes = [{"name": "chosen_one", "patterns": ["the chosen one", "prophecy"], "severity": "error"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.PROHIBITION
        assert anchors[0].forbidden_patterns == ["the chosen one", "prophecy"]

    def test_error_severity_maps_to_reject(self) -> None:
        tropes = [{"name": "x", "patterns": ["p"], "severity": "error"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert anchors[0].severity == Severity.REJECT

    def test_warning_severity_maps_to_warn(self) -> None:
        tropes = [{"name": "x", "patterns": ["p"], "severity": "warning"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert anchors[0].severity == Severity.WARN

    def test_empty_patterns_skipped(self) -> None:
        tropes = [{"name": "x", "patterns": [], "severity": "error"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert len(anchors) == 0

    def test_missing_patterns_skipped(self) -> None:
        tropes = [{"name": "x", "severity": "error"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert len(anchors) == 0

    def test_id_format(self) -> None:
        tropes = [{"name": "love_triangle", "patterns": ["p"], "severity": "warning"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert anchors[0].id == "fiction_trope_love_triangle"

    def test_description_includes_reason(self) -> None:
        tropes = [{"name": "x", "patterns": ["p"], "reason": "overused", "severity": "warning"}]
        anchors = anchors_from_banned_tropes(tropes)
        assert "overused" in anchors[0].description

    def test_multiple_tropes(self) -> None:
        tropes = [
            {"name": "a", "patterns": ["p1"], "severity": "error"},
            {"name": "b", "patterns": ["p2"], "severity": "warning"},
        ]
        anchors = anchors_from_banned_tropes(tropes)
        assert len(anchors) == 2


# =============================================================================
# TestAnchorsFromWorldRules
# =============================================================================


class TestAnchorsFromWorldRules:
    """Tests for anchors_from_world_rules."""

    def test_rule_creates_canon_anchor(self) -> None:
        rules = [{"name": "gravity", "rule": "Objects fall down", "category": "physics"}]
        anchors = anchors_from_world_rules(rules)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.CANON

    def test_id_format(self) -> None:
        rules = [{"name": "no magic", "rule": "Magic does not exist"}]
        anchors = anchors_from_world_rules(rules)
        assert anchors[0].id == "fiction_rule_no_magic"

    def test_severity_is_warn(self) -> None:
        rules = [{"name": "x", "rule": "y"}]
        anchors = anchors_from_world_rules(rules)
        assert anchors[0].severity == Severity.WARN

    def test_description_includes_category(self) -> None:
        rules = [{"name": "x", "rule": "y", "category": "society"}]
        anchors = anchors_from_world_rules(rules)
        assert "society" in anchors[0].description

    def test_empty_rules_list(self) -> None:
        anchors = anchors_from_world_rules([])
        assert len(anchors) == 0

    def test_no_forbidden_or_required_patterns(self) -> None:
        """World rules are conceptual -- no pattern matching."""
        rules = [{"name": "x", "rule": "y"}]
        anchors = anchors_from_world_rules(rules)
        assert anchors[0].forbidden_patterns == []
        assert anchors[0].required_patterns == []


# =============================================================================
# TestAnchorsFromToneSettings
# =============================================================================


class TestAnchorsFromToneSettings:
    """Tests for anchors_from_tone_settings."""

    def test_avoid_creates_style_anchor(self) -> None:
        tone = {"avoid": ["purple prose", "adverbs"]}
        anchors = anchors_from_tone_settings(tone)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.STYLE
        assert anchors[0].forbidden_patterns == ["purple prose", "adverbs"]

    def test_not_genres_creates_style_anchor(self) -> None:
        tone = {"not_genres": ["romance", "horror"]}
        anchors = anchors_from_tone_settings(tone)
        assert len(anchors) == 1
        assert anchors[0].forbidden_concepts == ["romance", "horror"]

    def test_both_avoid_and_not_genres(self) -> None:
        tone = {"avoid": ["x"], "not_genres": ["y"]}
        anchors = anchors_from_tone_settings(tone)
        assert len(anchors) == 2

    def test_empty_both_skips(self) -> None:
        tone = {"avoid": [], "not_genres": []}
        anchors = anchors_from_tone_settings(tone)
        assert len(anchors) == 0

    def test_missing_keys_skips(self) -> None:
        tone = {"genre": "sci-fi"}
        anchors = anchors_from_tone_settings(tone)
        assert len(anchors) == 0

    def test_avoid_severity_is_correct(self) -> None:
        tone = {"avoid": ["x"]}
        anchors = anchors_from_tone_settings(tone)
        assert anchors[0].severity == Severity.CORRECT

    def test_not_genres_severity_is_warn(self) -> None:
        tone = {"not_genres": ["y"]}
        anchors = anchors_from_tone_settings(tone)
        assert anchors[0].severity == Severity.WARN

    def test_id_format(self) -> None:
        tone = {"avoid": ["x"], "not_genres": ["y"]}
        anchors = anchors_from_tone_settings(tone)
        ids = {a.id for a in anchors}
        assert "fiction_tone_avoid" in ids
        assert "fiction_tone_not_genres" in ids


# =============================================================================
# TestAnchorsFromFictionBible
# =============================================================================


class TestAnchorsFromFictionBible:
    """Tests for anchors_from_fiction_bible master factory."""

    def test_combines_all_sub_factories(self) -> None:
        bible = {
            "characters": [{"name": "A", "anti_patterns": ["x"]}],
            "banned_tropes": [{"name": "t", "patterns": ["p"], "severity": "error"}],
            "world_rules": [{"name": "r", "rule": "text"}],
            "tone": {"avoid": ["adverbs"]},
        }
        anchors = anchors_from_fiction_bible(bible)
        types = {a.anchor_type for a in anchors}
        assert AnchorType.PROHIBITION in types
        assert AnchorType.CANON in types
        assert AnchorType.STYLE in types

    def test_empty_bible(self) -> None:
        anchors = anchors_from_fiction_bible({})
        assert len(anchors) == 0

    def test_partial_bible(self) -> None:
        bible = {"characters": [{"name": "A", "anti_patterns": ["x"]}]}
        anchors = anchors_from_fiction_bible(bible)
        assert len(anchors) == 1

    def test_anchor_count(self) -> None:
        bible = {
            "characters": [
                {"name": "A", "anti_patterns": ["x"]},
                {"name": "B", "voice": {"avoid": ["y"]}},
            ],
            "banned_tropes": [{"name": "t", "patterns": ["p"], "severity": "warning"}],
        }
        # 1 anti + 1 voice + 1 trope = 3
        anchors = anchors_from_fiction_bible(bible)
        assert len(anchors) == 3

    def test_source_field_consistent(self) -> None:
        bible = {
            "characters": [{"name": "A", "anti_patterns": ["x"]}],
            "banned_tropes": [{"name": "t", "patterns": ["p"], "severity": "error"}],
        }
        anchors = anchors_from_fiction_bible(bible)
        assert all(a.source == "fiction_bridge" for a in anchors)


# =============================================================================
# TestAnchorsFromConcepts
# =============================================================================


class TestAnchorsFromConcepts:
    """Tests for anchors_from_concepts."""

    def test_anti_patterns_create_definition(self) -> None:
        concepts = [{"term": "entropy", "anti_patterns": ["disorder", "chaos"]}]
        anchors = anchors_from_concepts(concepts)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.DEFINITION
        assert anchors[0].forbidden_patterns == ["disorder", "chaos"]

    def test_empty_anti_patterns_skipped(self) -> None:
        concepts = [{"term": "x", "anti_patterns": []}]
        anchors = anchors_from_concepts(concepts)
        assert len(anchors) == 0

    def test_no_anti_patterns_skipped(self) -> None:
        concepts = [{"term": "x", "definition": "y"}]
        anchors = anchors_from_concepts(concepts)
        assert len(anchors) == 0

    def test_id_format(self) -> None:
        concepts = [{"term": "phase space", "anti_patterns": ["x"]}]
        anchors = anchors_from_concepts(concepts)
        assert anchors[0].id == "nf_concept_phase_space"

    def test_severity_is_correct(self) -> None:
        concepts = [{"term": "x", "anti_patterns": ["y"]}]
        anchors = anchors_from_concepts(concepts)
        assert anchors[0].severity == Severity.CORRECT

    def test_source_field(self) -> None:
        concepts = [{"term": "x", "anti_patterns": ["y"]}]
        anchors = anchors_from_concepts(concepts)
        assert anchors[0].source == "nonfiction_bridge"

    def test_multiple_concepts(self) -> None:
        concepts = [
            {"term": "a", "anti_patterns": ["x"]},
            {"term": "b", "anti_patterns": ["y"]},
        ]
        anchors = anchors_from_concepts(concepts)
        assert len(anchors) == 2


# =============================================================================
# TestAnchorsFromPositions
# =============================================================================


class TestAnchorsFromPositions:
    """Tests for anchors_from_positions."""

    def test_current_position_creates_canon(self) -> None:
        positions = [{"id": "abc-123", "claim": "X causes Y", "superseded_by": None}]
        anchors = anchors_from_positions(positions)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.CANON

    def test_superseded_positions_skipped(self) -> None:
        positions = [{"id": "abc", "claim": "old claim", "superseded_by": "def"}]
        anchors = anchors_from_positions(positions)
        assert len(anchors) == 0

    def test_description_is_claim(self) -> None:
        positions = [{"id": "abc", "claim": "Temperature affects viscosity", "superseded_by": None}]
        anchors = anchors_from_positions(positions)
        assert anchors[0].description == "Temperature affects viscosity"

    def test_id_uses_uuid_suffix(self) -> None:
        positions = [{"id": "12345678-abcd-efgh-ijkl-mnopqrstuvwx", "claim": "x", "superseded_by": None}]
        anchors = anchors_from_positions(positions)
        assert anchors[0].id.startswith("nf_position_")

    def test_severity_is_warn(self) -> None:
        positions = [{"id": "abc", "claim": "x", "superseded_by": None}]
        anchors = anchors_from_positions(positions)
        assert anchors[0].severity == Severity.WARN

    def test_mixed_current_and_superseded(self) -> None:
        positions = [
            {"id": "a", "claim": "old", "superseded_by": "b"},
            {"id": "b", "claim": "current", "superseded_by": None},
        ]
        anchors = anchors_from_positions(positions)
        assert len(anchors) == 1
        assert anchors[0].description == "current"


# =============================================================================
# TestAnchorsFromNonfictionCorpus
# =============================================================================


class TestAnchorsFromNonfictionCorpus:
    """Tests for anchors_from_nonfiction_corpus master factory."""

    def test_combines_concepts_and_positions(self) -> None:
        corpus = {
            "concepts": [{"term": "entropy", "anti_patterns": ["chaos"]}],
            "positions": [{"id": "p1", "claim": "X is true", "superseded_by": None}],
        }
        anchors = anchors_from_nonfiction_corpus(corpus)
        types = {a.anchor_type for a in anchors}
        assert AnchorType.DEFINITION in types
        assert AnchorType.CANON in types

    def test_empty_corpus(self) -> None:
        anchors = anchors_from_nonfiction_corpus({})
        assert len(anchors) == 0

    def test_partial_corpus(self) -> None:
        corpus = {"concepts": [{"term": "x", "anti_patterns": ["y"]}]}
        anchors = anchors_from_nonfiction_corpus(corpus)
        assert len(anchors) == 1


# =============================================================================
# TestAnchorsFromPuppetProfile
# =============================================================================


class TestAnchorsFromPuppetProfile:
    """Tests for anchors_from_puppet_profile."""

    def test_forbidden_phrases_creates_persona(self) -> None:
        profile = {
            "puppet_id": "auditor",
            "voice": {"forbidden_phrases": ["I think", "maybe"]},
        }
        anchors = anchors_from_puppet_profile(profile)
        assert len(anchors) == 1
        assert anchors[0].anchor_type == AnchorType.PERSONA
        assert anchors[0].forbidden_patterns == ["I think", "maybe"]

    def test_required_ticks_creates_persona(self) -> None:
        profile = {
            "puppet_id": "auditor",
            "voice": {"required_ticks": ["Timeline:", "Source:"]},
        }
        anchors = anchors_from_puppet_profile(profile)
        assert len(anchors) == 1
        assert anchors[0].required_patterns == ["Timeline:", "Source:"]

    def test_both_forbidden_and_required(self) -> None:
        profile = {
            "puppet_id": "auditor",
            "voice": {
                "forbidden_phrases": ["I think"],
                "required_ticks": ["Timeline:"],
            },
        }
        anchors = anchors_from_puppet_profile(profile)
        assert len(anchors) == 2

    def test_empty_voice_skips(self) -> None:
        profile = {"puppet_id": "x", "voice": {}}
        anchors = anchors_from_puppet_profile(profile)
        assert len(anchors) == 0

    def test_missing_voice_skips(self) -> None:
        profile = {"puppet_id": "x"}
        anchors = anchors_from_puppet_profile(profile)
        assert len(anchors) == 0

    def test_id_format(self) -> None:
        profile = {
            "puppet_id": "auditor",
            "voice": {"forbidden_phrases": ["x"], "required_ticks": ["y"]},
        }
        anchors = anchors_from_puppet_profile(profile)
        ids = {a.id for a in anchors}
        assert "puppet_auditor_forbidden" in ids
        assert "puppet_auditor_required" in ids

    def test_severity_forbidden_is_correct(self) -> None:
        profile = {"puppet_id": "x", "voice": {"forbidden_phrases": ["y"]}}
        anchors = anchors_from_puppet_profile(profile)
        assert anchors[0].severity == Severity.CORRECT

    def test_severity_required_is_warn(self) -> None:
        profile = {"puppet_id": "x", "voice": {"required_ticks": ["y"]}}
        anchors = anchors_from_puppet_profile(profile)
        assert anchors[0].severity == Severity.WARN

    def test_source_field(self) -> None:
        profile = {"puppet_id": "x", "voice": {"forbidden_phrases": ["y"]}}
        anchors = anchors_from_puppet_profile(profile)
        assert anchors[0].source == "puppet_bridge"


# =============================================================================
# TestEdgeCases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for all bridge factories."""

    def test_none_fields_in_character(self) -> None:
        chars = [{"name": "A", "anti_patterns": None, "voice": None}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 0

    def test_unicode_in_patterns(self) -> None:
        chars = [{"name": "Ren\u00e9", "anti_patterns": ["\u00e9l\u00e8ve"]}]
        anchors = anchors_from_characters(chars)
        assert len(anchors) == 1
        assert "\u00e9l\u00e8ve" in anchors[0].forbidden_patterns

    def test_special_chars_in_name(self) -> None:
        chars = [{"name": "O'Brien Jr.", "anti_patterns": ["x"]}]
        anchors = anchors_from_characters(chars)
        assert "o'brien" in anchors[0].id

    def test_empty_lists_everywhere(self) -> None:
        bible = {
            "characters": [],
            "banned_tropes": [],
            "world_rules": [],
            "tone": {"avoid": [], "not_genres": []},
        }
        anchors = anchors_from_fiction_bible(bible)
        assert len(anchors) == 0

    def test_anchors_are_valid_anchor_objects(self) -> None:
        """All bridge outputs should be valid Anchor instances."""
        chars = [{"name": "A", "anti_patterns": ["x"]}]
        anchors = anchors_from_characters(chars)
        a = anchors[0]
        assert isinstance(a, Anchor)
        d = a.to_dict()
        roundtrip = Anchor.from_dict(d)
        assert roundtrip.id == a.id
        assert roundtrip.forbidden_patterns == a.forbidden_patterns
