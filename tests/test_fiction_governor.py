"""Tests for the fiction governor."""

import json
import pytest
from pathlib import Path

from fiction_governor import (
    Bible,
    Canon,
    Character,
    CharacterTrait,
    CharacterVoice,
    WorldRule,
    BannedTrope,
    ToneSettings,
    CanonEvent,
    Relationship,
    FictionClaimType,
    FictionClaim,
    InCharacterVerifier,
    TropeVerifier,
    CanonVerifier,
    ToneVerifier,
    FictionVerifier,
)
from fiction_governor.bible import COMMON_TROPES


# ============================================================================
# Types Tests
# ============================================================================

class TestCharacter:
    """Tests for Character type."""

    def test_create_character(self):
        """Test creating a character."""
        char = Character(name="Elena", role="protagonist")
        assert char.name == "Elena"
        assert char.role == "protagonist"
        assert char.traits == []
        assert char.anti_patterns == []

    def test_add_trait(self):
        """Test adding traits to a character."""
        char = Character(name="Elena")
        char.add_trait("cynical", nuance="privately romantic")

        assert len(char.traits) == 1
        assert char.traits[0].trait == "cynical"
        assert char.traits[0].nuance == "privately romantic"

    def test_add_anti_pattern(self):
        """Test adding anti-patterns."""
        char = Character(name="Elena")
        char.add_anti_pattern("would never abandon a friend")

        assert len(char.anti_patterns) == 1
        assert "abandon" in char.anti_patterns[0]

    def test_to_dict_from_dict(self):
        """Test serialization roundtrip."""
        char = Character(name="Elena", role="protagonist")
        char.add_trait("cynical", nuance="privately romantic")
        char.add_anti_pattern("would never cry in public")
        char.voice = CharacterVoice(
            internal_monologue="sardonic",
            dialogue="clipped",
            avoid=["exclamation points"],
        )

        data = char.to_dict()
        restored = Character.from_dict(data)

        assert restored.name == char.name
        assert restored.role == char.role
        assert len(restored.traits) == 1
        assert restored.traits[0].nuance == "privately romantic"
        assert restored.voice.internal_monologue == "sardonic"

    def test_format_for_prompt(self):
        """Test formatting character for LLM prompt."""
        char = Character(name="Elena", role="protagonist")
        char.add_trait("cynical")
        char.add_anti_pattern("would never cry in public")

        formatted = char.format_for_prompt()

        assert "### Elena" in formatted
        assert "protagonist" in formatted
        assert "cynical" in formatted
        assert "cry in public" in formatted


class TestWorldRule:
    """Tests for WorldRule type."""

    def test_create_rule(self):
        """Test creating a world rule."""
        rule = WorldRule(
            name="magic_cost",
            rule="Magic causes proportional physical pain",
            category="magic",
            implications=["No one uses magic casually"],
        )

        assert rule.name == "magic_cost"
        assert rule.category == "magic"
        assert len(rule.implications) == 1

    def test_to_dict_from_dict(self):
        """Test serialization roundtrip."""
        rule = WorldRule(
            name="magic_cost",
            rule="Magic causes proportional physical pain",
            category="magic",
        )

        data = rule.to_dict()
        restored = WorldRule.from_dict(data)

        assert restored.name == rule.name
        assert restored.rule == rule.rule


class TestBannedTrope:
    """Tests for BannedTrope type."""

    def test_create_trope(self):
        """Test creating a banned trope."""
        trope = BannedTrope(
            name="chosen_one",
            reason="Protagonist should earn their role",
            patterns=[r"you are the chosen"],
            severity="error",
        )

        assert trope.name == "chosen_one"
        assert len(trope.patterns) == 1
        assert trope.severity == "error"


class TestCanonEvent:
    """Tests for CanonEvent type."""

    def test_create_event(self):
        """Test creating a canon event."""
        event = CanonEvent(
            chapter=3,
            summary="Elena discovers the hidden door",
            characters=["Elena", "Marcus"],
            location="The Library",
        )

        assert event.chapter == 3
        assert "Elena" in event.characters
        assert event.location == "The Library"

    def test_to_dict_from_dict(self):
        """Test serialization roundtrip."""
        event = CanonEvent(
            chapter=3,
            summary="Elena discovers the hidden door",
            characters=["Elena"],
            quote="The door had always been there.",
        )

        data = event.to_dict()
        restored = CanonEvent.from_dict(data)

        assert restored.chapter == event.chapter
        assert restored.summary == event.summary
        assert restored.quote == event.quote


class TestFictionClaim:
    """Tests for FictionClaim type."""

    def test_in_character_claim(self):
        """Test creating an in-character claim."""
        claim = FictionClaim(
            type=FictionClaimType.IN_CHARACTER,
            character="Elena",
        )

        assert claim.type == FictionClaimType.IN_CHARACTER
        assert "Elena" in claim.describe()

    def test_no_banned_trope_claim(self):
        """Test creating a no-banned-trope claim."""
        claim = FictionClaim(type=FictionClaimType.NO_BANNED_TROPE)

        assert claim.type == FictionClaimType.NO_BANNED_TROPE
        assert "no_banned_trope" in claim.describe()


# ============================================================================
# Bible Tests
# ============================================================================

class TestBible:
    """Tests for Bible ledger."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path

    def test_init_creates_structure(self, temp_project):
        """Test that Bible creates directory structure."""
        bible = Bible(temp_project)

        assert (temp_project / ".fiction-gov" / "bible").exists()
        assert (temp_project / ".fiction-gov" / "bible" / "characters.json").exists()

    def test_add_character(self, temp_project):
        """Test adding a character."""
        bible = Bible(temp_project)
        char = bible.add_character("Elena", role="protagonist")

        assert char.name == "Elena"

        # Verify persistence
        bible2 = Bible(temp_project)
        loaded = bible2.get_character("elena")  # Case insensitive
        assert loaded is not None
        assert loaded.name == "Elena"

    def test_add_character_trait(self, temp_project):
        """Test adding traits to a character."""
        bible = Bible(temp_project)
        bible.add_character("Elena")

        char = bible.add_character_trait("Elena", "cynical", nuance="privately romantic")

        assert char is not None
        assert len(char.traits) == 1
        assert char.traits[0].trait == "cynical"

    def test_add_anti_pattern(self, temp_project):
        """Test adding anti-patterns."""
        bible = Bible(temp_project)
        bible.add_character("Elena")

        char = bible.add_character_anti_pattern("Elena", "would never cry in public")

        assert char is not None
        assert "cry in public" in char.anti_patterns[0]

    def test_set_character_voice(self, temp_project):
        """Test setting character voice."""
        bible = Bible(temp_project)
        bible.add_character("Elena")

        char = bible.set_character_voice(
            "Elena",
            internal_monologue="sardonic",
            dialogue="clipped",
            avoid=["exclamation points"],
        )

        assert char.voice is not None
        assert char.voice.internal_monologue == "sardonic"

    def test_ban_common_trope(self, temp_project):
        """Test banning a common trope."""
        bible = Bible(temp_project)

        trope = bible.ban_common_trope("chosen_one")

        assert trope is not None
        assert trope.name == "chosen_one"
        assert len(trope.patterns) > 0  # Should have predefined patterns

    def test_ban_custom_trope(self, temp_project):
        """Test banning a custom trope."""
        bible = Bible(temp_project)

        trope = bible.ban_trope(
            "my_custom_trope",
            reason="Because I said so",
            patterns=[r"pattern1", r"pattern2"],
        )

        assert trope.name == "my_custom_trope"
        assert len(trope.patterns) == 2

    def test_unban_trope(self, temp_project):
        """Test unbanning a trope."""
        bible = Bible(temp_project)
        bible.ban_common_trope("chosen_one")

        assert bible.get_banned_trope("chosen_one") is not None

        bible.unban_trope("chosen_one")

        assert bible.get_banned_trope("chosen_one") is None

    def test_add_world_rule(self, temp_project):
        """Test adding a world rule."""
        bible = Bible(temp_project)

        rule = bible.add_world_rule(
            "magic_cost",
            "Magic causes proportional physical pain",
            category="magic",
            implications=["No one uses magic casually"],
        )

        assert rule.name == "magic_cost"

        # Verify persistence
        bible2 = Bible(temp_project)
        loaded = bible2.get_world_rule("magic_cost")
        assert loaded is not None
        assert loaded.rule == "Magic causes proportional physical pain"

    def test_set_tone(self, temp_project):
        """Test setting tone."""
        bible = Bible(temp_project)

        tone = bible.set_tone(
            genre="literary fantasy",
            not_genres=["YA", "cozy"],
            prose_style="precise, sensory",
            avoid=["purple prose"],
        )

        assert tone.genre == "literary fantasy"
        assert "YA" in tone.not_genres

    def test_format_for_prompt(self, temp_project):
        """Test formatting entire bible for prompt."""
        bible = Bible(temp_project)
        bible.add_character("Elena", role="protagonist")
        bible.add_character_trait("Elena", "cynical")
        bible.ban_common_trope("chosen_one")
        bible.set_tone(genre="literary fantasy")

        formatted = bible.format_for_prompt()

        assert "# Story Bible" in formatted
        assert "Elena" in formatted
        assert "chosen_one" in formatted
        assert "literary fantasy" in formatted


# ============================================================================
# Canon Tests
# ============================================================================

class TestCanon:
    """Tests for Canon ledger."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path

    def test_init_creates_structure(self, temp_project):
        """Test that Canon creates directory structure."""
        canon = Canon(temp_project)

        assert (temp_project / ".fiction-gov" / "canon").exists()
        assert (temp_project / ".fiction-gov" / "canon" / "events.json").exists()

    def test_add_event(self, temp_project):
        """Test adding an event."""
        canon = Canon(temp_project)

        event = canon.add_event(
            chapter=3,
            summary="Elena discovers the hidden door",
            characters=["Elena", "Marcus"],
            location="The Library",
        )

        assert event.chapter == 3
        assert event.summary == "Elena discovers the hidden door"

    def test_events_by_chapter(self, temp_project):
        """Test getting events by chapter."""
        canon = Canon(temp_project)
        canon.add_event(chapter=1, summary="Event 1")
        canon.add_event(chapter=2, summary="Event 2")
        canon.add_event(chapter=1, summary="Event 1b")

        ch1_events = canon.events_by_chapter(1)

        assert len(ch1_events) == 2

    def test_events_with_character(self, temp_project):
        """Test getting events with a character."""
        canon = Canon(temp_project)
        canon.add_event(chapter=1, summary="Event 1", characters=["Elena"])
        canon.add_event(chapter=2, summary="Event 2", characters=["Marcus"])
        canon.add_event(chapter=3, summary="Event 3", characters=["Elena", "Marcus"])

        elena_events = canon.events_with_character("Elena")

        assert len(elena_events) == 2

    def test_last_location(self, temp_project):
        """Test getting last known location."""
        canon = Canon(temp_project)
        canon.add_event(chapter=1, summary="Event 1", characters=["Elena"], location="Castle")
        canon.add_event(chapter=2, summary="Event 2", characters=["Elena"], location="Forest")

        location, chapter = canon.last_location("Elena")

        assert location == "Forest"
        assert chapter == 2

    def test_set_relationship(self, temp_project):
        """Test setting a relationship."""
        canon = Canon(temp_project)

        rel = canon.set_relationship(
            "Elena",
            "Marcus",
            status="strangers",
            as_of_chapter=1,
            dynamics=["Elena doesn't trust Marcus"],
        )

        assert rel.status == "strangers"
        assert "Elena doesn't trust Marcus" in rel.dynamics

    def test_relationship_history(self, temp_project):
        """Test relationship history tracking."""
        canon = Canon(temp_project)

        canon.set_relationship("Elena", "Marcus", status="strangers", as_of_chapter=1)
        canon.set_relationship("Elena", "Marcus", status="uneasy allies", as_of_chapter=3)

        rel = canon.get_relationship("Elena", "Marcus")

        assert rel.status == "uneasy allies"
        assert "Ch1: strangers" in rel.history

    def test_character_can_be_at(self, temp_project):
        """Test checking if character can be at location."""
        canon = Canon(temp_project)
        canon.add_event(chapter=1, summary="Elena at castle", characters=["Elena"], location="Castle")

        # Same chapter, different location - should fail
        can_be, reason = canon.character_can_be_at("Elena", "Forest", chapter=1)
        assert not can_be

        # Later chapter - should pass (could have traveled)
        can_be, reason = canon.character_can_be_at("Elena", "Forest", chapter=2)
        assert can_be

    def test_format_for_prompt(self, temp_project):
        """Test formatting canon for prompt."""
        canon = Canon(temp_project)
        canon.add_event(chapter=1, summary="Elena arrives", characters=["Elena"], location="Castle")
        canon.set_relationship("Elena", "Marcus", status="strangers", as_of_chapter=1)

        formatted = canon.format_for_prompt()

        assert "# Story Canon" in formatted
        assert "Elena arrives" in formatted
        assert "strangers" in formatted


# ============================================================================
# Verifier Tests
# ============================================================================

class TestInCharacterVerifier:
    """Tests for InCharacterVerifier."""

    @pytest.fixture
    def bible(self, tmp_path):
        """Create a bible with a character."""
        bible = Bible(tmp_path)
        bible.add_character("Elena", role="protagonist")
        bible.add_character_trait("Elena", "cynical")
        bible.add_character_anti_pattern("Elena", "would never cry openly")
        bible.set_character_voice("Elena", avoid=["exclamation points", "!"])
        return bible

    def test_verify_in_character(self, bible):
        """Test verifying in-character content."""
        verifier = InCharacterVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.IN_CHARACTER, character="Elena")
        content = "Elena sighed and looked away. Whatever."

        result = verifier.verify(claim, content)

        assert result.success

    def test_verify_out_of_character_anti_pattern(self, bible):
        """Test detecting out-of-character via anti-pattern."""
        verifier = InCharacterVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.IN_CHARACTER, character="Elena")
        content = "Elena would never cry openly, but today she did exactly that."

        result = verifier.verify(claim, content)

        assert not result.success
        assert "anti-pattern" in result.message.lower()

    def test_verify_out_of_character_voice(self, bible):
        """Test detecting out-of-character via voice."""
        verifier = InCharacterVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.IN_CHARACTER, character="Elena")
        content = "Elena shouted excitedly! This is amazing!"

        result = verifier.verify(claim, content)

        assert not result.success
        assert result.severity == "warning"

    def test_missing_character(self, bible):
        """Test handling missing character."""
        verifier = InCharacterVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.IN_CHARACTER, character="Unknown")

        result = verifier.verify(claim, "Some content")

        assert not result.success
        assert "not found" in result.message


class TestTropeVerifier:
    """Tests for TropeVerifier."""

    @pytest.fixture
    def bible(self, tmp_path):
        """Create a bible with banned tropes."""
        bible = Bible(tmp_path)
        bible.ban_common_trope("chosen_one")
        bible.ban_trope(
            "instant_expert",
            reason="Skills should be earned",
            patterns=[r"suddenly knew how to", r"mastered .* in moments"],
            severity="warning",
        )
        return bible

    def test_no_trope_detected(self, bible):
        """Test content with no banned tropes."""
        verifier = TropeVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.NO_BANNED_TROPE)
        content = "Elena practiced for weeks before she could even lift the sword properly."

        result = verifier.verify(claim, content)

        assert result.success

    def test_trope_detected_error(self, bible):
        """Test detecting a banned trope (error severity)."""
        verifier = TropeVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.NO_BANNED_TROPE)
        content = "The elder looked at her. 'You are the chosen one, destined to save us all.'"

        result = verifier.verify(claim, content)

        assert not result.success
        assert result.severity == "error"
        assert "chosen_one" in result.message

    def test_trope_detected_warning(self, bible):
        """Test detecting a banned trope (warning severity)."""
        verifier = TropeVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.NO_BANNED_TROPE)
        content = "She suddenly knew how to wield the ancient magic."

        result = verifier.verify(claim, content)

        assert not result.success
        assert result.severity == "warning"


class TestToneVerifier:
    """Tests for ToneVerifier."""

    @pytest.fixture
    def bible(self, tmp_path):
        """Create a bible with tone settings."""
        bible = Bible(tmp_path)
        bible.set_tone(
            genre="literary fantasy",
            prose_style="precise",
            avoid=["purple prose", "suddenly"],
        )
        return bible

    def test_tone_appropriate(self, bible):
        """Test content with appropriate tone."""
        verifier = ToneVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.TONE_APPROPRIATE)
        content = "The door stood before her, weathered oak against grey stone."

        result = verifier.verify(claim, content)

        assert result.success

    def test_tone_avoid_word(self, bible):
        """Test detecting avoided words."""
        verifier = ToneVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.TONE_APPROPRIATE)
        content = "Suddenly, Elena realized the truth. It was purple prose incarnate."

        result = verifier.verify(claim, content)

        assert not result.success
        assert result.severity == "warning"

    def test_purple_prose_detection(self, bible):
        """Test detecting purple prose indicators."""
        verifier = ToneVerifier(bible)

        claim = FictionClaim(type=FictionClaimType.TONE_APPROPRIATE)
        content = "Her azure orbs gazed upon his chiseled visage."

        result = verifier.verify(claim, content)

        assert not result.success


class TestCanonVerifier:
    """Tests for CanonVerifier."""

    @pytest.fixture
    def canon(self, tmp_path):
        """Create a canon with events."""
        canon = Canon(tmp_path)
        canon.add_event(chapter=1, summary="Elena at castle", characters=["Elena"], location="Castle")
        canon.set_relationship("Elena", "Marcus", status="strangers", as_of_chapter=1)
        return canon

    def test_character_present_valid(self, canon):
        """Test valid character presence."""
        verifier = CanonVerifier(canon)

        claim = FictionClaim(
            type=FictionClaimType.CHARACTER_PRESENT,
            character="Elena",
            location="Castle",
            chapter=1,
        )

        result = verifier.verify_character_present(claim)

        assert result.success

    def test_character_present_invalid(self, canon):
        """Test invalid character presence (same chapter, different location)."""
        verifier = CanonVerifier(canon)

        claim = FictionClaim(
            type=FictionClaimType.CHARACTER_PRESENT,
            character="Elena",
            location="Forest",
            chapter=1,
        )

        result = verifier.verify_character_present(claim)

        assert not result.success
        assert "Castle" in result.message


class TestFictionVerifier:
    """Tests for FictionVerifier (composite verifier)."""

    @pytest.fixture
    def project(self, tmp_path):
        """Create a project with bible and canon."""
        bible = Bible(tmp_path)
        bible.add_character("Elena", role="protagonist")
        bible.add_character_trait("Elena", "cynical")
        bible.add_character_anti_pattern("Elena", "would never beg")
        bible.ban_common_trope("chosen_one")
        bible.set_tone(genre="literary fantasy", prose_style="precise")

        canon = Canon(tmp_path)
        canon.add_event(chapter=1, summary="Elena arrives", characters=["Elena"], location="Castle")

        return tmp_path

    def test_verify_scene(self, project):
        """Test verifying a complete scene."""
        verifier = FictionVerifier(project)

        content = "Elena crossed her arms and looked away. Typical."
        results = verifier.verify_scene(
            content,
            characters=["Elena"],
            chapter=1,
            location="Castle",
        )

        failures = [r for r in results if not r.success]
        assert len(failures) == 0

    def test_quick_check_pass(self, project):
        """Test quick check that passes."""
        verifier = FictionVerifier(project)

        content = "Elena shrugged. Whatever."
        passed, issues = verifier.quick_check(content, ["Elena"])

        assert passed
        assert len(issues) == 0

    def test_quick_check_fail_trope(self, project):
        """Test quick check that fails on trope."""
        verifier = FictionVerifier(project)

        content = "The prophecy spoke of her. She was the chosen one."
        passed, issues = verifier.quick_check(content, ["Elena"])

        assert not passed
        assert any("chosen_one" in issue.lower() for issue in issues)

    def test_quick_check_fail_character(self, project):
        """Test quick check that fails on character."""
        verifier = FictionVerifier(project)

        content = "Elena fell to her knees and started to beg desperately."
        passed, issues = verifier.quick_check(content, ["Elena"])

        assert not passed


# ============================================================================
# Common Tropes Tests
# ============================================================================

class TestCommonTropes:
    """Tests for the common tropes dictionary."""

    def test_common_tropes_exist(self):
        """Test that common tropes are defined."""
        assert "chosen_one" in COMMON_TROPES
        assert "love_triangle" in COMMON_TROPES
        assert "magical_pregnancy" in COMMON_TROPES

    def test_common_tropes_have_patterns(self):
        """Test that common tropes have detection patterns."""
        chosen_one = COMMON_TROPES["chosen_one"]

        assert len(chosen_one.patterns) > 0
        assert chosen_one.severity == "error"

    def test_chosen_one_patterns_match(self):
        """Test that chosen_one patterns actually match."""
        import re

        trope = COMMON_TROPES["chosen_one"]
        test_texts = [
            "You are the chosen one",
            "The prophecy spoke of a hero",
            "She was destined to save us all",
        ]

        for text in test_texts:
            matched = any(re.search(p, text, re.IGNORECASE) for p in trope.patterns)
            assert matched, f"Pattern should match: {text}"
