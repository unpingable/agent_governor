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
    # Plot threads
    ThreadType,
    ThreadStatus,
    PlotThread,
    SceneProposal,
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


# ============================================================================
# Narrative Constraint Tests (Motivation, Belief, BehavioralConstraint)
# ============================================================================

from fiction_governor import (
    MotivationType,
    Motivation,
    Belief,
    BehavioralConstraint,
    NarrativeWarning,
    CharacterState,
    NarrativeVerifier,
)


class TestMotivation:
    """Tests for Motivation type."""

    def test_create_motivation(self):
        """Test creating a motivation."""
        mot = Motivation(
            character="Elena",
            type=MotivationType.GOAL,
            description="find her missing brother",
            intensity=8,
            as_of_chapter=1,
        )

        assert mot.character == "Elena"
        assert mot.type == MotivationType.GOAL
        assert mot.description == "find her missing brother"
        assert mot.intensity == 8
        assert mot.is_active

    def test_motivation_decay(self):
        """Test motivation intensity decay over time."""
        mot = Motivation(
            character="Elena",
            description="initial enthusiasm",
            intensity=10,
            as_of_chapter=1,
            decay_rate=0.2,  # 20% decay per chapter
        )

        # At chapter 1, full intensity
        assert mot.effective_intensity(1) == 10.0

        # At chapter 2, 80% of 10 = 8
        assert mot.effective_intensity(2) == pytest.approx(8.0)

        # At chapter 3, 80% of 8 = 6.4
        assert mot.effective_intensity(3) == pytest.approx(6.4)

    def test_motivation_resolved(self):
        """Test resolved motivation."""
        mot = Motivation(
            character="Elena",
            description="find the key",
            as_of_chapter=1,
        )

        assert mot.is_active

        mot.resolved_at_chapter = 5
        mot.resolution = "achieved"

        assert not mot.is_active
        assert mot.effective_intensity(6) == 0.0

    def test_motivation_serialization(self):
        """Test motivation roundtrip serialization."""
        mot = Motivation(
            character="Elena",
            type=MotivationType.FEAR,
            description="being abandoned",
            intensity=7,
            decay_rate=0.1,
            conflicts_with=["some-id"],
        )

        data = mot.to_dict()
        restored = Motivation.from_dict(data)

        assert restored.character == mot.character
        assert restored.type == mot.type
        assert restored.description == mot.description
        assert restored.intensity == mot.intensity
        assert restored.decay_rate == mot.decay_rate
        assert restored.conflicts_with == mot.conflicts_with


class TestBelief:
    """Tests for Belief type."""

    def test_create_belief(self):
        """Test creating a belief."""
        belief = Belief(
            character="Marcus",
            belief="Elena is dead",
            is_true=False,
            learned_at_chapter=3,
            source="saw her fall",
        )

        assert belief.character == "Marcus"
        assert belief.belief == "Elena is dead"
        assert belief.is_true is False
        assert belief.is_held

    def test_belief_invalidated(self):
        """Test invalidating a belief."""
        belief = Belief(
            character="Marcus",
            belief="Elena is dead",
            is_true=False,
            learned_at_chapter=3,
        )

        assert belief.is_held

        belief.invalidated_at_chapter = 7

        assert not belief.is_held

    def test_belief_serialization(self):
        """Test belief roundtrip serialization."""
        belief = Belief(
            character="Marcus",
            belief="the king is trustworthy",
            is_true=False,
            confidence=8,
            source="official propaganda",
        )

        data = belief.to_dict()
        restored = Belief.from_dict(data)

        assert restored.belief == belief.belief
        assert restored.is_true == belief.is_true
        assert restored.confidence == belief.confidence
        assert restored.source == belief.source


class TestBehavioralConstraint:
    """Tests for BehavioralConstraint type."""

    def test_create_constraint(self):
        """Test creating a behavioral constraint."""
        constraint = BehavioralConstraint(
            character="Elena",
            action_type="violence",
            constraint="requires extreme provocation",
            cost="psychological damage",
            prerequisites=["must be backed into corner"],
            exceptions=["if family is threatened"],
        )

        assert constraint.character == "Elena"
        assert constraint.action_type == "violence"
        assert "provocation" in constraint.constraint
        assert "psychological" in constraint.cost
        assert len(constraint.prerequisites) == 1
        assert len(constraint.exceptions) == 1

    def test_constraint_serialization(self):
        """Test constraint roundtrip serialization."""
        constraint = BehavioralConstraint(
            character="Elena",
            action_type="deception",
            constraint="struggles with lying",
            cost="guilt and self-loathing",
            source="raised by honest parents",
        )

        data = constraint.to_dict()
        restored = BehavioralConstraint.from_dict(data)

        assert restored.action_type == constraint.action_type
        assert restored.constraint == constraint.constraint
        assert restored.cost == constraint.cost
        assert restored.source == constraint.source


class TestCharacterState:
    """Tests for CharacterState manager."""

    @pytest.fixture
    def state(self, tmp_path):
        """Create a fresh CharacterState."""
        return CharacterState(tmp_path)

    def test_add_and_get_motivation(self, state):
        """Test adding and retrieving motivations."""
        mot = state.add_motivation(
            character="Elena",
            description="find her brother",
            type=MotivationType.GOAL,
            intensity=8,
        )

        retrieved = state.get_motivation(mot.id)

        assert retrieved is not None
        assert retrieved.description == "find her brother"

    def test_motivations_for_character(self, state):
        """Test getting motivations for a character."""
        state.add_motivation("Elena", "find brother", type=MotivationType.GOAL)
        state.add_motivation("Elena", "avoid capture", type=MotivationType.FEAR)
        state.add_motivation("Marcus", "protect Elena", type=MotivationType.DRIVE)

        elena_mots = state.motivations_for_character("Elena")

        assert len(elena_mots) == 2

    def test_motivations_time_filtered(self, state):
        """Test filtering motivations by chapter."""
        state.add_motivation("Elena", "early goal", as_of_chapter=1)
        state.add_motivation("Elena", "later goal", as_of_chapter=5)

        # At chapter 3, only early goal should be visible
        mots = state.motivations_for_character("Elena", at_chapter=3)
        assert len(mots) == 1
        assert "early" in mots[0].description

    def test_resolve_motivation(self, state):
        """Test resolving a motivation."""
        mot = state.add_motivation("Elena", "find the key")

        resolved = state.resolve_motivation(mot.id, chapter=5, resolution="achieved")

        assert resolved is not None
        assert not resolved.is_active
        assert resolved.resolution == "achieved"

    def test_conflicting_motivations(self, state):
        """Test detecting conflicting motivations."""
        mot_a = state.add_motivation("Elena", "protect Marcus")
        mot_b = state.add_motivation("Elena", "complete the mission")

        state.add_motivation_conflict(mot_a.id, mot_b.id)

        conflicts = state.conflicting_motivations("Elena", at_chapter=1)

        assert len(conflicts) == 1
        assert mot_a in conflicts[0]
        assert mot_b in conflicts[0]

    def test_add_and_get_belief(self, state):
        """Test adding and retrieving beliefs."""
        belief = state.add_belief(
            character="Marcus",
            belief="Elena is dead",
            is_true=False,
            learned_at_chapter=3,
        )

        retrieved = state.get_belief(belief.id)

        assert retrieved is not None
        assert retrieved.belief == "Elena is dead"
        assert retrieved.is_true is False

    def test_beliefs_time_filtered(self, state):
        """Test filtering beliefs by chapter."""
        state.add_belief("Marcus", "world is flat", learned_at_chapter=1)
        state.add_belief("Marcus", "world is round", learned_at_chapter=5)

        # At chapter 3
        beliefs = state.beliefs_for_character("Marcus", at_chapter=3)
        assert len(beliefs) == 1
        assert "flat" in beliefs[0].belief

    def test_character_believes(self, state):
        """Test checking what character believes."""
        state.add_belief("Marcus", "Elena is dead", learned_at_chapter=3)

        # At chapter 4, should find the belief
        belief = state.character_believes("Marcus", "Elena", at_chapter=4)
        assert belief is not None
        assert "dead" in belief.belief

        # At chapter 2, shouldn't find it yet
        belief = state.character_believes("Marcus", "Elena", at_chapter=2)
        assert belief is None

    def test_false_beliefs(self, state):
        """Test getting false beliefs."""
        state.add_belief("Marcus", "Elena is dead", learned_at_chapter=1, is_true=False)
        state.add_belief("Marcus", "the sun rises", learned_at_chapter=1, is_true=True)
        state.add_belief("Marcus", "fate is real", learned_at_chapter=1, is_true=None)

        false_beliefs = state.false_beliefs("Marcus")

        assert len(false_beliefs) == 1
        assert "dead" in false_beliefs[0].belief

    def test_add_and_get_constraint(self, state):
        """Test adding and retrieving constraints."""
        constraint = state.add_constraint(
            character="Elena",
            action_type="violence",
            constraint="extreme provocation required",
            cost="psychological damage",
        )

        retrieved = state.get_constraint(constraint.id)

        assert retrieved is not None
        assert retrieved.action_type == "violence"

    def test_constraints_for_action_type(self, state):
        """Test filtering constraints by action type."""
        state.add_constraint("Elena", "violence", "needs provocation")
        state.add_constraint("Elena", "deception", "struggles with lies")
        state.add_constraint("Elena", "vulnerability", "walls up")

        violence_constraints = state.constraints_for_character("Elena", action_type="violence")

        assert len(violence_constraints) == 1
        assert "provocation" in violence_constraints[0].constraint

    def test_check_action_returns_warnings(self, state):
        """Test that check_action returns appropriate warnings."""
        mot_a = state.add_motivation("Elena", "protect family")
        mot_b = state.add_motivation("Elena", "complete dangerous mission")
        state.add_motivation_conflict(mot_a.id, mot_b.id)

        state.add_constraint("Elena", "violence", "requires extreme cause", cost="guilt")

        warnings = state.check_action(
            character="Elena",
            action="attack the guard",
            chapter=1,
            action_type="violence",
        )

        assert len(warnings) >= 2  # conflict + constraint
        types = [w.warning_type for w in warnings]
        assert "motivation_conflict" in types
        assert "constraint_breach" in types

    def test_format_character_state(self, state):
        """Test formatting character state for prompt."""
        state.add_motivation("Elena", "find brother", intensity=8)
        state.add_belief("Elena", "Marcus is trustworthy", learned_at_chapter=1, is_true=True)
        state.add_constraint("Elena", "violence", "extreme provocation needed")

        formatted = state.format_character_state("Elena")

        assert "Elena" in formatted
        assert "find brother" in formatted
        assert "trustworthy" in formatted
        assert "violence" in formatted

    def test_state_persistence(self, tmp_path):
        """Test that state persists across instances."""
        state1 = CharacterState(tmp_path)
        state1.add_motivation("Elena", "test goal")
        state1.add_belief("Elena", "test belief", learned_at_chapter=1)
        state1.add_constraint("Elena", "test", "test constraint")

        # Create new instance pointing to same directory
        state2 = CharacterState(tmp_path)

        assert len(state2.motivations_for_character("Elena")) == 1
        assert len(state2.beliefs_for_character("Elena")) == 1
        assert len(state2.constraints_for_character("Elena")) == 1


class TestNarrativeVerifier:
    """Tests for NarrativeVerifier."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Set up bible and state for testing."""
        bible = Bible(tmp_path)
        bible.add_character("Elena", role="protagonist")

        state = CharacterState(tmp_path)
        state.add_motivation("Elena", "find her brother", intensity=8, as_of_chapter=1)
        state.add_belief("Elena", "Marcus is dead", is_true=False, learned_at_chapter=3)
        state.add_constraint("Elena", "violence", "extreme cause needed", cost="guilt")

        return tmp_path, bible, state

    def test_verify_action_with_constraint(self, setup):
        """Test verifying action against constraints."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        warnings = verifier.verify_action(
            character="Elena",
            action="attacks the guard",
            chapter=5,
            action_type="violence",
        )

        constraint_warnings = [w for w in warnings if w.warning_type == "constraint_breach"]
        assert len(constraint_warnings) >= 1

    def test_verify_knowledge_gap(self, setup):
        """Test detecting knowledge gaps."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        warning = verifier.verify_knowledge(
            character="Elena",
            uses_knowledge_of="the secret passage",
            chapter=1,
        )

        assert warning is not None
        assert warning.warning_type == "knowledge_gap"

    def test_verify_knowledge_exists(self, setup):
        """Test that known beliefs don't trigger warnings."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        # Elena knows about Marcus at chapter 5 (learned at chapter 3)
        warning = verifier.verify_knowledge(
            character="Elena",
            uses_knowledge_of="Marcus",
            chapter=5,
        )

        assert warning is None

    def test_verify_reaction_without_knowledge(self, setup):
        """Test detecting reaction to unknown information."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        warnings = verifier.verify_reaction(
            character="Elena",
            reacts_to="the king's betrayal",
            reaction="is furious",
            chapter=5,
        )

        belief_warnings = [w for w in warnings if w.warning_type == "belief_violation"]
        assert len(belief_warnings) >= 1

    def test_verify_reaction_to_false_belief(self, setup):
        """Test flagging reactions based on false beliefs."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        # Elena believes Marcus is dead (but it's false)
        warnings = verifier.verify_reaction(
            character="Elena",
            reacts_to="Marcus",
            reaction="mourns deeply",
            chapter=5,
        )

        false_belief_warnings = [w for w in warnings if w.warning_type == "false_belief_reaction"]
        assert len(false_belief_warnings) >= 1

    def test_verify_scene(self, setup):
        """Test verifying a complete scene."""
        project_dir, _, state = setup

        # Add conflicting motivations
        mot_a = state.add_motivation("Elena", "save herself")
        mot_b = state.add_motivation("Elena", "save others")
        state.add_motivation_conflict(mot_a.id, mot_b.id)

        verifier = NarrativeVerifier(project_dir)

        warnings = verifier.verify_scene(
            characters=["Elena"],
            chapter=5,
            actions=[("Elena", "runs away")],
        )

        # Should detect the motivation conflict
        conflict_warnings = [w for w in warnings if w.warning_type == "motivation_conflict"]
        assert len(conflict_warnings) >= 1

    def test_get_character_context(self, setup):
        """Test getting character context for prompts."""
        project_dir, _, _ = setup
        verifier = NarrativeVerifier(project_dir)

        context = verifier.get_character_context("Elena", chapter=5)

        assert "Elena" in context
        assert "find her brother" in context
        assert "Marcus" in context  # belief about Marcus
        assert "violence" in context  # constraint


class TestNarrativeWarning:
    """Tests for NarrativeWarning type."""

    def test_create_warning(self):
        """Test creating a narrative warning."""
        warning = NarrativeWarning(
            character="Elena",
            chapter=5,
            warning_type="motivation_conflict",
            message="Character has conflicting goals",
            severity="warning",
            suggestion="Consider showing internal struggle",
        )

        assert warning.character == "Elena"
        assert warning.warning_type == "motivation_conflict"
        assert warning.severity == "warning"


# ============================================================================
# Plot Thread Tests
# ============================================================================

class TestPlotThread:
    """Tests for PlotThread type."""

    def test_create_thread(self):
        """Test creating a plot thread."""
        thread = PlotThread(
            name="mysterious letter",
            thread_type=ThreadType.CHEKHOV_GUN,
            description="Elena finds a sealed letter in her father's study",
            planted_chapter=3,
        )

        assert thread.name == "mysterious letter"
        assert thread.thread_type == ThreadType.CHEKHOV_GUN
        assert thread.status == ThreadStatus.PLANTED
        assert thread.planted_chapter == 3
        assert thread.is_active

    def test_thread_development(self):
        """Test adding developments to a thread."""
        thread = PlotThread(
            name="mystery",
            thread_type=ThreadType.MYSTERY,
            description="Who killed the duke?",
            planted_chapter=1,
        )

        thread.add_development(3, "Elena finds a clue")
        thread.add_development(5, "The clue points to Marcus")

        assert thread.status == ThreadStatus.DEVELOPING
        assert len(thread.developments) == 2
        assert thread.developments[0]["chapter"] == 3

    def test_thread_resolution(self):
        """Test resolving a thread."""
        thread = PlotThread(
            name="Elena's arc",
            thread_type=ThreadType.CHARACTER_ARC,
            description="Elena learns to trust again",
            planted_chapter=1,
        )

        thread.resolve(10, "Elena finally trusts Marcus")

        assert thread.status == ThreadStatus.RESOLVED
        assert thread.resolved_chapter == 10
        assert thread.resolution == "Elena finally trusts Marcus"
        assert not thread.is_active

    def test_thread_overdue(self):
        """Test thread overdue detection."""
        thread = PlotThread(
            name="the gun",
            thread_type=ThreadType.CHEKHOV_GUN,
            description="Gun on the wall",
            planted_chapter=1,
            expected_payoff_by=5,
        )

        # Not overdue at chapter 4
        assert not thread.check_overdue(4)
        assert thread.status == ThreadStatus.PLANTED

        # Overdue at chapter 6
        assert thread.check_overdue(6)
        assert thread.status == ThreadStatus.OVERDUE

    def test_thread_serialization(self):
        """Test thread serialization."""
        thread = PlotThread(
            name="test",
            thread_type=ThreadType.FORESHADOWING,
            description="A hint of things to come",
            planted_chapter=2,
            characters=["Elena", "Marcus"],
            expected_payoff_by=10,
            importance=8,
        )
        thread.add_development(5, "The hint becomes clearer")

        data = thread.to_dict()
        restored = PlotThread.from_dict(data)

        assert restored.name == thread.name
        assert restored.thread_type == thread.thread_type
        assert restored.status == ThreadStatus.DEVELOPING
        assert restored.characters == ["Elena", "Marcus"]
        assert len(restored.developments) == 1

    def test_format_for_prompt(self):
        """Test thread formatting for prompts."""
        thread = PlotThread(
            name="sealed letter",
            thread_type=ThreadType.CHEKHOV_GUN,
            description="Unopened letter from father",
            planted_chapter=1,
            expected_payoff_by=10,
        )

        formatted = thread.format_for_prompt()
        assert "sealed letter" in formatted
        assert "chekhov_gun" in formatted
        assert "chapter 10" in formatted


class TestSceneProposal:
    """Tests for SceneProposal type."""

    def test_create_proposal(self):
        """Test creating a scene proposal."""
        proposal = SceneProposal(
            chapter=5,
            title="The Confrontation",
            summary="Elena confronts Marcus about the letter",
            characters=["Elena", "Marcus"],
            location="The garden",
        )

        assert proposal.chapter == 5
        assert proposal.title == "The Confrontation"
        assert proposal.status == "pending"
        assert "Elena" in proposal.characters

    def test_proposal_serialization(self):
        """Test proposal serialization."""
        proposal = SceneProposal(
            chapter=5,
            scene_number=2,
            title="Test Scene",
            summary="Something happens",
            characters=["Elena"],
            threads_advanced=["abc-123"],
            canon_events=["Elena discovers the truth"],
        )

        data = proposal.to_dict()
        restored = SceneProposal.from_dict(data)

        assert restored.chapter == 5
        assert restored.scene_number == 2
        assert restored.threads_advanced == ["abc-123"]
        assert "Elena discovers" in restored.canon_events[0]


class TestCanonThreads:
    """Tests for plot thread management in Canon."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Setup a canon with some threads."""
        canon = Canon(tmp_path)

        # Add some threads
        canon.add_thread(
            name="mysterious letter",
            thread_type=ThreadType.CHEKHOV_GUN,
            description="Sealed letter from father",
            planted_chapter=1,
            characters=["Elena"],
            expected_payoff_by=10,
            importance=8,
        )

        canon.add_thread(
            name="Marcus's secret",
            thread_type=ThreadType.MYSTERY,
            description="What is Marcus hiding?",
            planted_chapter=2,
            characters=["Marcus"],
        )

        canon.add_thread(
            name="Elena's arc",
            thread_type=ThreadType.CHARACTER_ARC,
            description="Elena learns to trust",
            planted_chapter=1,
            characters=["Elena"],
        )

        return canon

    def test_add_thread(self, tmp_path):
        """Test adding a thread."""
        canon = Canon(tmp_path)

        thread = canon.add_thread(
            name="the prophecy",
            thread_type=ThreadType.FORESHADOWING,
            description="The oracle's words",
            planted_chapter=1,
        )

        assert thread.name == "the prophecy"
        assert str(thread.id) in canon._threads

    def test_get_thread_by_id(self, setup):
        """Test getting thread by ID."""
        canon = setup
        threads = canon.all_threads()
        thread_id = str(threads[0].id)

        found = canon.get_thread(thread_id)
        assert found is not None
        assert found.name == threads[0].name

    def test_get_thread_by_name(self, setup):
        """Test getting thread by name."""
        canon = setup

        found = canon.get_thread_by_name("mysterious letter")
        assert found is not None
        assert found.thread_type == ThreadType.CHEKHOV_GUN

        # Case insensitive
        found2 = canon.get_thread_by_name("MYSTERIOUS LETTER")
        assert found2 is not None

    def test_develop_thread(self, setup):
        """Test developing a thread."""
        canon = setup
        thread = canon.get_thread_by_name("mysterious letter")

        updated = canon.develop_thread(str(thread.id), 5, "Elena almost opens it")

        assert updated.status == ThreadStatus.DEVELOPING
        assert len(updated.developments) == 1

    def test_resolve_thread(self, setup):
        """Test resolving a thread."""
        canon = setup
        thread = canon.get_thread_by_name("Marcus's secret")

        resolved = canon.resolve_thread(str(thread.id), 8, "Marcus reveals his past")

        assert resolved.status == ThreadStatus.RESOLVED
        assert resolved.resolved_chapter == 8

    def test_abandon_thread(self, setup):
        """Test abandoning a thread."""
        canon = setup
        thread = canon.get_thread_by_name("Elena's arc")

        abandoned = canon.abandon_thread(str(thread.id), reason="Changed direction")

        assert abandoned.status == ThreadStatus.ABANDONED
        assert "Changed direction" in abandoned.notes

    def test_active_threads(self, setup):
        """Test getting active threads."""
        canon = setup
        active = canon.active_threads()

        assert len(active) == 3  # All three are active

        # Resolve one
        thread = canon.get_thread_by_name("Marcus's secret")
        canon.resolve_thread(str(thread.id), 5, "Revealed")

        active = canon.active_threads()
        assert len(active) == 2

    def test_threads_by_type(self, setup):
        """Test filtering threads by type."""
        canon = setup

        chekhov = canon.threads_by_type(ThreadType.CHEKHOV_GUN)
        assert len(chekhov) == 1
        assert chekhov[0].name == "mysterious letter"

        arcs = canon.threads_by_type(ThreadType.CHARACTER_ARC)
        assert len(arcs) == 1

    def test_threads_for_character(self, setup):
        """Test getting threads for a character."""
        canon = setup

        elena_threads = canon.threads_for_character("Elena")
        assert len(elena_threads) == 2  # letter and arc

        marcus_threads = canon.threads_for_character("Marcus")
        assert len(marcus_threads) == 1

    def test_overdue_threads(self, setup):
        """Test detecting overdue threads."""
        canon = setup

        # At chapter 5, nothing overdue
        overdue = canon.overdue_threads(5)
        assert len(overdue) == 0

        # At chapter 12, the letter should be overdue
        overdue = canon.overdue_threads(12)
        assert len(overdue) == 1
        assert overdue[0].name == "mysterious letter"

    def test_chekhov_audit(self, setup):
        """Test the Chekhov audit."""
        canon = setup

        # Add development to one thread
        letter = canon.get_thread_by_name("mysterious letter")
        canon.develop_thread(str(letter.id), 5, "Elena glances at it")

        audit = canon.chekhov_audit(8)

        assert len(audit["planted"]) == 2  # mystery and arc
        assert len(audit["developing"]) == 1  # letter

        # At chapter 9, mystery approaches deadline (expected_payoff_by=10, none set)
        # Only the letter has a deadline, but it's already developing
        # Let's check for planted threads nearing deadline by adding one
        canon.add_thread(
            name="ticking clock",
            thread_type=ThreadType.SETUP,
            description="Time is running out",
            planted_chapter=1,
            expected_payoff_by=10,
        )

        audit = canon.chekhov_audit(9)
        assert len(audit["approaching"]) == 1  # ticking clock (planted, near deadline)

    def test_format_threads_for_prompt(self, setup):
        """Test formatting threads for prompts."""
        canon = setup

        formatted = canon.format_threads_for_prompt(current_chapter=5)

        assert "mysterious letter" in formatted
        assert "Marcus's secret" in formatted
        assert "Elena's arc" in formatted

    def test_thread_persistence(self, tmp_path):
        """Test that threads persist across Canon instances."""
        canon1 = Canon(tmp_path)
        canon1.add_thread(
            name="test thread",
            thread_type=ThreadType.SETUP,
            description="Testing persistence",
            planted_chapter=1,
        )

        # Create new instance
        canon2 = Canon(tmp_path)
        thread = canon2.get_thread_by_name("test thread")

        assert thread is not None
        assert thread.description == "Testing persistence"


class TestCanonProposals:
    """Tests for scene proposal management in Canon."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Setup canon with threads for proposals."""
        canon = Canon(tmp_path)

        # Add a thread to advance
        canon.add_thread(
            name="mystery",
            thread_type=ThreadType.MYSTERY,
            description="The central mystery",
            planted_chapter=1,
        )

        return canon

    def test_create_proposal(self, setup):
        """Test creating a proposal."""
        canon = setup

        proposal = canon.create_proposal(
            chapter=5,
            title="The Discovery",
            summary="Elena finds a clue",
            characters=["Elena"],
            location="Library",
        )

        assert proposal.title == "The Discovery"
        assert proposal.status == "pending"
        assert str(proposal.id) in canon._proposals

    def test_get_proposal(self, setup):
        """Test getting a proposal by ID."""
        canon = setup

        proposal = canon.create_proposal(
            chapter=5,
            title="Test",
            summary="Test scene",
        )

        found = canon.get_proposal(str(proposal.id))
        assert found is not None
        assert found.title == "Test"

    def test_approve_proposal(self, setup):
        """Test approving a proposal."""
        canon = setup
        thread = canon.get_thread_by_name("mystery")

        proposal = canon.create_proposal(
            chapter=5,
            title="Clue Found",
            summary="Elena finds evidence",
            characters=["Elena"],
            threads_advanced=[str(thread.id)],
            canon_events=["Elena discovers a hidden message"],
        )

        approved = canon.approve_proposal(str(proposal.id))

        assert approved.status == "approved"
        assert approved.reviewed_at is not None

        # Check thread was developed
        updated_thread = canon.get_thread(str(thread.id))
        assert len(updated_thread.developments) == 1

        # Check canon event was added
        events = canon.events_by_chapter(5)
        assert len(events) == 1
        assert "hidden message" in events[0].summary

    def test_approve_proposal_resolves_thread(self, setup):
        """Test that approving can resolve threads."""
        canon = setup
        thread = canon.get_thread_by_name("mystery")

        proposal = canon.create_proposal(
            chapter=10,
            title="Mystery Solved",
            summary="The truth is revealed",
            threads_resolved=[str(thread.id)],
        )

        canon.approve_proposal(str(proposal.id))

        resolved_thread = canon.get_thread(str(thread.id))
        assert resolved_thread.status == ThreadStatus.RESOLVED

    def test_reject_proposal(self, setup):
        """Test rejecting a proposal."""
        canon = setup

        proposal = canon.create_proposal(
            chapter=5,
            title="Bad Scene",
            summary="This doesn't work",
        )

        rejected = canon.reject_proposal(str(proposal.id), "Out of character")

        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "Out of character"

    def test_revise_proposal(self, setup):
        """Test revising a rejected proposal."""
        canon = setup

        proposal = canon.create_proposal(
            chapter=5,
            title="Scene",
            summary="Original summary",
        )

        canon.reject_proposal(str(proposal.id), "Needs work")

        revised = canon.revise_proposal(
            str(proposal.id),
            summary="Improved summary",
        )

        assert revised.status == "revised"
        assert revised.summary == "Improved summary"
        assert revised.rejection_reason is None

    def test_pending_proposals(self, setup):
        """Test getting pending proposals."""
        canon = setup

        canon.create_proposal(chapter=1, title="A", summary="A")
        canon.create_proposal(chapter=2, title="B", summary="B")
        p3 = canon.create_proposal(chapter=3, title="C", summary="C")

        canon.approve_proposal(str(p3.id))

        pending = canon.pending_proposals()
        assert len(pending) == 2

    def test_proposals_by_chapter(self, setup):
        """Test getting proposals by chapter."""
        canon = setup

        canon.create_proposal(chapter=5, title="A", summary="A")
        canon.create_proposal(chapter=5, title="B", summary="B")
        canon.create_proposal(chapter=6, title="C", summary="C")

        ch5 = canon.proposals_by_chapter(5)
        assert len(ch5) == 2

    def test_proposal_persistence(self, tmp_path):
        """Test that proposals persist across Canon instances."""
        canon1 = Canon(tmp_path)
        canon1.create_proposal(
            chapter=1,
            title="Test Proposal",
            summary="Testing persistence",
        )

        canon2 = Canon(tmp_path)
        proposals = canon2.all_proposals()

        assert len(proposals) == 1
        assert proposals[0].title == "Test Proposal"
