# SPDX-License-Identifier: Apache-2.0
"""Tests for fiction_governor.canon_capture — Canon Capture Phase 1.

Tests the CanonCaptureClassifier: pattern detection, false positive
filtering, proper noun extraction, deduplication, receipts, and edge cases.
"""

import hashlib

import pytest

from fiction_governor.canon_capture import (
    CanonCaptureClassifier,
    CapturedItem,
    CaptureKind,
    CaptureReceipt,
    CaptureStatus,
    _is_skippable,
)
from governor.capture import (
    classify_skippable,
    extract_proper_noun,
    strip_question_tag,
)


@pytest.fixture
def classifier():
    return CanonCaptureClassifier()


# =============================================================================
# Explicit markers (high confidence)
# =============================================================================


class TestExplicitMarkers:
    """Test high-confidence explicit definition markers."""

    def test_character_prefix(self, classifier):
        items, _ = classifier.scan("Character: Zara is a stubborn girl from Ashenmere")
        assert len(items) >= 1
        char_items = [i for i in items if i.kind == CaptureKind.CHARACTER]
        assert len(char_items) >= 1
        assert char_items[0].confidence >= 0.85

    def test_rule_prefix(self, classifier):
        items, _ = classifier.scan("Rule: Magic costs blood to use")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1
        assert rule_items[0].confidence >= 0.85
        assert "blood" in rule_items[0].statement.lower()

    def test_world_rule_prefix(self, classifier):
        items, _ = classifier.scan("World rule: No one can fly in this setting")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_backstory_prefix(self, classifier):
        items, _ = classifier.scan("Backstory: She grew up in the mountains")
        assert len(items) >= 1
        assert items[0].kind == CaptureKind.CHARACTER

    def test_possessive_backstory(self, classifier):
        items, _ = classifier.scan("Zara's backstory is that she fled the capital at age twelve.")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess == "Zara"]
        assert len(char_items) >= 1
        assert char_items[0].confidence >= 0.85

    def test_explicit_marker_case_insensitive(self, classifier):
        items, _ = classifier.scan("character: Thorne is brave")
        assert len(items) >= 1


# =============================================================================
# Copula definitions (medium confidence)
# =============================================================================


class TestCopulaDefinitions:
    """Test copula-based character definitions."""

    def test_is_from(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess == "Zara"]
        assert len(char_items) >= 1
        assert char_items[0].kind == CaptureKind.CHARACTER

    def test_is_a_role(self, classifier):
        items, _ = classifier.scan("Dorin is a blacksmith who lives near the gate")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess == "Dorin"]
        assert len(char_items) >= 1

    def test_has_trait(self, classifier):
        items, _ = classifier.scan("Thorne has green eyes and a scar on her left hand")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess == "Thorne"]
        assert len(char_items) >= 1

    def test_was_origin(self, classifier):
        items, _ = classifier.scan("Sable was raised in the capital by merchants")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess == "Sable"]
        assert len(char_items) >= 1

    def test_was_born(self, classifier):
        items, _ = classifier.scan("Nyx was born in the northern wastes")
        assert len(items) >= 1

    def test_copula_confidence_lower_than_explicit(self, classifier):
        explicit_items, _ = classifier.scan("Character: Zara is stubborn")
        copula_items, _ = classifier.scan("Zara is stubborn and loyal")

        explicit_conf = max(i.confidence for i in explicit_items) if explicit_items else 0
        copula_conf = max(i.confidence for i in copula_items) if copula_items else 0
        assert explicit_conf > copula_conf

    def test_multi_word_name(self, classifier):
        items, _ = classifier.scan("Thorne Voss is a scholar from the eastern provinces")
        assert len(items) >= 1
        char_items = [i for i in items if i.subject_guess and "Thorne" in i.subject_guess]
        assert len(char_items) >= 1


# =============================================================================
# Relationship markers
# =============================================================================


class TestRelationshipMarkers:
    """Test relationship detection patterns."""

    def test_are_relationship(self, classifier):
        items, _ = classifier.scan("Zara and Sable are rivals")
        assert len(items) >= 1
        rel_items = [i for i in items if i.kind == CaptureKind.RELATIONSHIP]
        assert len(rel_items) >= 1

    def test_possessive_relationship(self, classifier):
        items, _ = classifier.scan("Dorin is Thorne's father")
        assert len(items) >= 1
        rel_items = [i for i in items if i.kind == CaptureKind.RELATIONSHIP]
        assert len(rel_items) >= 1

    def test_relationship_subject_contains_both_names(self, classifier):
        items, _ = classifier.scan("Zara and Sable are childhood friends")
        rel_items = [i for i in items if i.kind == CaptureKind.RELATIONSHIP]
        if rel_items:
            subj = rel_items[0].subject_guess or ""
            assert "Zara" in subj or "Sable" in subj

    def test_are_siblings(self, classifier):
        items, _ = classifier.scan("Nyx and Riven are siblings who don't get along")
        rel_items = [i for i in items if i.kind == CaptureKind.RELATIONSHIP]
        assert len(rel_items) >= 1


# =============================================================================
# World-building markers
# =============================================================================


class TestWorldBuilding:
    """Test world-building detection patterns."""

    def test_in_this_world(self, classifier):
        items, _ = classifier.scan("In this world, magic is forbidden by the state")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_magic_works_by(self, classifier):
        items, _ = classifier.scan("Magic works by drawing energy from crystals")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_law_says(self, classifier):
        items, _ = classifier.scan("The law forbids anyone from entering the forest after dark")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_there_is_no(self, classifier):
        items, _ = classifier.scan("There is no electricity in this setting")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_there_are_no(self, classifier):
        items, _ = classifier.scan("There are no dragons in this world")
        assert len(items) >= 1


# =============================================================================
# Constraint markers
# =============================================================================


class TestConstraintMarkers:
    """Test character constraint detection patterns."""

    def test_would_never(self, classifier):
        items, _ = classifier.scan("Zara would never betray her family")
        assert len(items) >= 1
        constraint_items = [i for i in items if i.kind == CaptureKind.CONSTRAINT]
        assert len(constraint_items) >= 1
        assert constraint_items[0].field_guess == "wont"

    def test_cannot(self, classifier):
        items, _ = classifier.scan("Dorin cannot use magic due to his bloodline")
        assert len(items) >= 1
        constraint_items = [i for i in items if i.kind == CaptureKind.CONSTRAINT]
        assert len(constraint_items) >= 1

    def test_cant_contraction(self, classifier):
        items, _ = classifier.scan("Thorne can't swim because of an old injury")
        assert len(items) >= 1

    def test_always(self, classifier):
        items, _ = classifier.scan("Sable always carries a knife")
        assert len(items) >= 1
        items_with_sable = [i for i in items if i.subject_guess == "Sable"]
        assert len(items_with_sable) >= 1

    def test_forbidden_to(self, classifier):
        items, _ = classifier.scan("It's forbidden to speak the old language")
        assert len(items) >= 1
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1


# =============================================================================
# Negative cases — things we should NOT capture
# =============================================================================


class TestNegativeCases:
    """Test that non-definition text is correctly ignored."""

    def test_question_skipped(self, classifier):
        items, _ = classifier.scan("Is Thorne tall?")
        assert len(items) == 0

    def test_hypothetical_skipped(self, classifier):
        items, _ = classifier.scan("What if Thorne had blue eyes?")
        assert len(items) == 0

    def test_meta_discussion_skipped(self, classifier):
        items, _ = classifier.scan("I'm thinking about making her a doctor")
        assert len(items) == 0

    def test_do_you_think_skipped(self, classifier):
        items, _ = classifier.scan("Do you think Zara should be older?")
        assert len(items) == 0

    def test_lets_say_skipped(self, classifier):
        items, _ = classifier.scan("Let's say the magic system is different")
        assert len(items) == 0

    def test_maybe_skipped(self, classifier):
        items, _ = classifier.scan("Maybe Thorne has a secret past")
        assert len(items) == 0

    def test_im_considering_skipped(self, classifier):
        items, _ = classifier.scan("I'm considering making Zara from a different city")
        assert len(items) == 0

    def test_should_we_skipped(self, classifier):
        items, _ = classifier.scan("Should we make Dorin a warrior instead?")
        assert len(items) == 0

    def test_suppose_skipped(self, classifier):
        items, _ = classifier.scan("Suppose the world has two moons")
        assert len(items) == 0

    def test_empty_text(self, classifier):
        items, _ = classifier.scan("")
        assert len(items) == 0

    def test_whitespace_only(self, classifier):
        items, _ = classifier.scan("   \n\n  ")
        assert len(items) == 0

    def test_short_text(self, classifier):
        items, _ = classifier.scan("ok")
        assert len(items) == 0

    def test_lowercase_only(self, classifier):
        """No proper nouns -> no character captures."""
        items, _ = classifier.scan("the blacksmith lives near the gate")
        char_items = [i for i in items if i.kind == CaptureKind.CHARACTER]
        assert len(char_items) == 0

    def test_common_word_not_character(self, classifier):
        """Stopwords should never be a subject_guess."""
        items, _ = classifier.scan("The cat is old and grumpy")
        for item in items:
            if item.subject_guess:
                assert item.subject_guess.lower() not in {
                    "the", "a", "an", "this", "that",
                }


# =============================================================================
# Question-tagged assertions
# =============================================================================


class TestQuestionTaggedAssertions:
    """Test that 'X is Y, right?' gets low-confidence capture, not hard skip."""

    def test_right_tag_captured(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere, right?")
        assert len(items) >= 1
        assert all(i.confidence < 0.70 for i in items)  # Reduced confidence

    def test_yeah_tag_captured(self, classifier):
        items, _ = classifier.scan("Thorne has green eyes, yeah?")
        assert len(items) >= 1
        assert all(i.confidence < 0.70 for i in items)

    def test_correct_tag_captured(self, classifier):
        items, _ = classifier.scan("In this world magic costs blood, correct?")
        assert len(items) >= 1

    def test_pure_question_still_skipped(self, classifier):
        items, _ = classifier.scan("Is Thorne tall?")
        assert len(items) == 0

    def test_strip_question_tag_helper(self):
        assert strip_question_tag("Zara is stubborn, right?") == "Zara is stubborn"
        assert strip_question_tag("Thorne has red hair, yeah?") == "Thorne has red hair"
        assert strip_question_tag("Is she tall?") is None


# =============================================================================
# Proper noun extraction
# =============================================================================


class TestProperNounExtraction:
    """Test the extract_proper_noun helper."""

    def test_single_name(self):
        assert extract_proper_noun("Zara is stubborn") == "Zara"

    def test_two_word_name(self):
        assert extract_proper_noun("Thorne Voss is a scholar") == "Thorne Voss"

    def test_stopword_filtered(self):
        assert extract_proper_noun("Chapter five begins") is None

    def test_pronoun_filtered(self):
        assert extract_proper_noun("She is brave") is None

    def test_no_proper_noun(self):
        assert extract_proper_noun("the old man walked away") is None

    def test_multiple_returns_first_valid(self):
        result = extract_proper_noun("Dorin and Thorne went home")
        assert result in ("Dorin", "Thorne")


# =============================================================================
# Skippable detection
# =============================================================================


class TestSkippableDetection:
    """Test the classify_skippable filter."""

    def test_question_skippable(self):
        assert classify_skippable("Is Thorne brave?") == "question"

    def test_what_if_hypothetical(self):
        assert classify_skippable("What if she's older?") == "hypothetical"

    def test_im_thinking_meta(self):
        assert classify_skippable("I'm thinking about making him a wizard") == "meta"

    def test_statement_not_skippable(self):
        assert classify_skippable("Zara is from Ashenmere") is None

    def test_explicit_marker_not_skippable(self):
        assert classify_skippable("Character: Thorne is brave") is None


# =============================================================================
# Deduplication
# =============================================================================


class TestDeduplication:
    """Test that multiple pattern hits for the same subject merge."""

    def test_same_character_merged(self, classifier):
        text = "Zara is from Ashenmere and Zara has blue eyes"
        items, _ = classifier.scan(text)
        zara_items = [i for i in items if i.subject_guess == "Zara"]
        char_items = [i for i in zara_items if i.kind == CaptureKind.CHARACTER]
        assert len(char_items) <= 1

    def test_different_subjects_not_merged(self, classifier):
        text = "Zara is from Ashenmere. Thorne is from Veldmark."
        items, _ = classifier.scan(text)
        subjects = {i.subject_guess for i in items if i.subject_guess}
        assert "Zara" in subjects
        assert "Thorne" in subjects

    def test_different_kinds_not_merged(self, classifier):
        text = "Zara is stubborn. Zara would never lie."
        items, _ = classifier.scan(text)
        kinds = {i.kind for i in items if i.subject_guess == "Zara"}
        assert len(kinds) >= 1


# =============================================================================
# Receipt determinism
# =============================================================================


class TestReceiptDeterminism:
    """Test that same input produces deterministic receipts."""

    def test_same_input_same_hash(self, classifier):
        text = "Zara is from Ashenmere"
        _, receipt1 = classifier.scan(text)
        _, receipt2 = classifier.scan(text)
        assert receipt1.content_hash == receipt2.content_hash

    def test_same_input_same_pattern_hits(self, classifier):
        text = "Thorne has green eyes"
        _, receipt1 = classifier.scan(text)
        _, receipt2 = classifier.scan(text)
        assert len(receipt1.pattern_hits) == len(receipt2.pattern_hits)
        for h1, h2 in zip(receipt1.pattern_hits, receipt2.pattern_hits):
            assert h1["pattern_name"] == h2["pattern_name"]
            assert h1["span"] == h2["span"]

    def test_different_input_different_hash(self, classifier):
        _, receipt1 = classifier.scan("Zara is from Ashenmere")
        _, receipt2 = classifier.scan("Thorne is from Veldmark")
        assert receipt1.content_hash != receipt2.content_hash

    def test_receipt_has_forensic_version(self, classifier):
        _, receipt = classifier.scan("Zara is stubborn")
        assert receipt.classifier_version == "fiction.canon@1.0.0"
        assert "@" in receipt.classifier_version  # Forensic format

    def test_receipt_has_timestamp(self, classifier):
        _, receipt = classifier.scan("test")
        assert receipt.timestamp != ""

    def test_receipt_content_hash_matches(self, classifier):
        text = "Thorne is brave"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        _, receipt = classifier.scan(text)
        assert receipt.content_hash == expected


# =============================================================================
# CapturedItem status
# =============================================================================


class TestCapturedItemStatus:
    """Test that captures always start as PENDING."""

    def test_default_status_pending(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        for item in items:
            assert item.status == CaptureStatus.PENDING

    def test_status_enum_values(self):
        assert CaptureStatus.PENDING.value == "pending"
        assert CaptureStatus.ACCEPTED.value == "accepted"
        assert CaptureStatus.REJECTED.value == "rejected"
        assert CaptureStatus.EXPIRED.value == "expired"


# =============================================================================
# Subject source tracking (Chatty's dedup diagnostic)
# =============================================================================


class TestSubjectSource:
    """Test that subject_source records which pattern produced the guess."""

    def test_subject_source_populated(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        for item in items:
            if item.subject_guess:
                assert item.subject_source != ""
                assert isinstance(item.subject_source, str)

    def test_subject_source_in_serialization(self, classifier):
        items, _ = classifier.scan("Dorin is a blacksmith")
        if items:
            data = items[0].to_dict()
            assert "subject_source" in data


# =============================================================================
# Draft payload
# =============================================================================


class TestDraftPayload:
    """Test pre-filled modal payloads."""

    def test_character_has_name(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        char_items = [i for i in items if i.kind == CaptureKind.CHARACTER and i.subject_guess == "Zara"]
        if char_items:
            assert "name" in char_items[0].draft_payload
            assert char_items[0].draft_payload["name"] == "Zara"

    def test_character_has_description(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        char_items = [i for i in items if i.kind == CaptureKind.CHARACTER]
        if char_items:
            assert "description" in char_items[0].draft_payload

    def test_world_rule_has_rule(self, classifier):
        items, _ = classifier.scan("Rule: No magic after sunset")
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        if rule_items:
            assert "rule" in rule_items[0].draft_payload

    def test_constraint_has_wont(self, classifier):
        items, _ = classifier.scan("Zara would never betray her family")
        constraint_items = [i for i in items if i.kind == CaptureKind.CONSTRAINT]
        if constraint_items:
            assert "wont" in constraint_items[0].draft_payload


# =============================================================================
# Serialization
# =============================================================================


class TestSerialization:
    """Test to_dict / from_dict roundtrip."""

    def test_captured_item_roundtrip(self):
        item = CapturedItem(
            kind=CaptureKind.CHARACTER,
            confidence=0.85,
            subject_guess="Zara",
            statement="is from Ashenmere",
            field_guess="description",
            evidence_spans=[(0, 20)],
            source_message_id="msg_123",
            status=CaptureStatus.PENDING,
            draft_payload={"name": "Zara", "description": "is from Ashenmere"},
            subject_source="copula_is_descriptor",
        )
        data = item.to_dict()
        restored = CapturedItem.from_dict(data)
        assert restored.kind == item.kind
        assert restored.confidence == item.confidence
        assert restored.subject_guess == item.subject_guess
        assert restored.statement == item.statement
        assert restored.field_guess == item.field_guess
        assert restored.evidence_spans == item.evidence_spans
        assert restored.source_message_id == item.source_message_id
        assert restored.status == item.status
        assert restored.draft_payload == item.draft_payload
        assert restored.subject_source == item.subject_source

    def test_capture_receipt_to_dict(self, classifier):
        _, receipt = classifier.scan("Zara is from Ashenmere")
        data = receipt.to_dict()
        assert "fiction.canon@" in data["classifier_version"]
        assert "content_hash" in data
        assert isinstance(data["pattern_hits"], list)
        assert isinstance(data["items_detected"], int)


# =============================================================================
# Evidence spans
# =============================================================================


class TestEvidenceSpans:
    """Test that evidence spans point to actual matched text."""

    def test_span_within_text(self, classifier):
        text = "Zara is from Ashenmere"
        items, _ = classifier.scan(text)
        for item in items:
            for start, end in item.evidence_spans:
                assert 0 <= start < len(text)
                assert start < end <= len(text)

    def test_span_contains_match(self, classifier):
        text = "Thorne has green eyes"
        items, _ = classifier.scan(text)
        for item in items:
            for start, end in item.evidence_spans:
                span_text = text[start:end]
                assert len(span_text) > 0


# =============================================================================
# Max captures cap
# =============================================================================


class TestMaxCaptures:
    """Test that captures are capped at max_captures."""

    def test_default_max(self):
        classifier = CanonCaptureClassifier(max_captures=2)
        text = (
            "Zara is from Ashenmere. "
            "Thorne is a warrior. "
            "Dorin is a blacksmith. "
            "Sable has red hair. "
            "Nyx was born in the south."
        )
        items, _ = classifier.scan(text)
        assert len(items) <= 2

    def test_highest_confidence_kept(self):
        classifier = CanonCaptureClassifier(max_captures=1)
        text = "Character: Zara is stubborn. Sable has blue eyes."
        items, _ = classifier.scan(text)
        assert len(items) == 1
        assert items[0].confidence >= 0.70


# =============================================================================
# Multi-line / multi-statement messages
# =============================================================================


class TestMultiLine:
    """Test messages with multiple lines and statements."""

    def test_multiline_captures(self, classifier):
        text = "Zara is from Ashenmere.\nThorne is a warrior.\nIn this world, magic costs blood."
        items, _ = classifier.scan(text)
        assert len(items) >= 2

    def test_mixed_definitions_and_questions(self, classifier):
        text = "Zara is from Ashenmere. Is she tall? Thorne has green eyes."
        items, _ = classifier.scan(text)
        assert len(items) >= 1
        subjects = {i.subject_guess for i in items if i.subject_guess}
        assert "Zara" in subjects or "Thorne" in subjects

    def test_definition_then_hypothetical(self, classifier):
        text = "Dorin is a blacksmith.\nWhat if he were a wizard instead?"
        items, _ = classifier.scan(text)
        assert len(items) >= 1


# =============================================================================
# Kind enum
# =============================================================================


class TestCaptureKind:
    """Test CaptureKind enum values."""

    def test_values(self):
        assert CaptureKind.CHARACTER.value == "character"
        assert CaptureKind.WORLD_RULE.value == "world_rule"
        assert CaptureKind.RELATIONSHIP.value == "relationship"
        assert CaptureKind.CONSTRAINT.value == "constraint"

    def test_string_enum(self):
        assert isinstance(CaptureKind.CHARACTER, str)
        assert CaptureKind.CHARACTER == "character"


# =============================================================================
# Integration: realistic user messages
# =============================================================================


class TestRealisticMessages:
    """Test with realistic chat messages from fiction writing sessions."""

    def test_character_intro(self, classifier):
        text = "Zara is from Ashenmere and she's stubborn but secretly kind"
        items, _ = classifier.scan(text)
        assert len(items) >= 1
        assert any(i.subject_guess == "Zara" for i in items)

    def test_world_rule_declaration(self, classifier):
        items, _ = classifier.scan("In this world, only women can wield magic")
        rule_items = [i for i in items if i.kind == CaptureKind.WORLD_RULE]
        assert len(rule_items) >= 1

    def test_character_constraint(self, classifier):
        items, _ = classifier.scan("Zara would never kill anyone, not even in self-defense")
        assert any(i.kind == CaptureKind.CONSTRAINT for i in items)

    def test_relationship_definition(self, classifier):
        items, _ = classifier.scan("Zara and Sable are rivals who secretly respect each other")
        rel_items = [i for i in items if i.kind == CaptureKind.RELATIONSHIP]
        assert len(rel_items) >= 1

    def test_complex_message_mixed_types(self, classifier):
        text = (
            "Zara is from Ashenmere. "
            "She and Sable are childhood rivals. "
            "In this world, magic is powered by music. "
            "Zara would never use dark magic."
        )
        items, _ = classifier.scan(text)
        kinds = {i.kind for i in items}
        assert len(kinds) >= 2

    def test_narration_not_captured(self, classifier):
        text = (
            "She walked down the corridor, her footsteps echoing. "
            "The torches flickered as she passed, casting long shadows."
        )
        items, _ = classifier.scan(text)
        char_items = [i for i in items if i.kind == CaptureKind.CHARACTER]
        assert len(char_items) == 0

    def test_dialogue_not_over_captured(self, classifier):
        text = '"I am from Ashenmere," she said. "My father was a blacksmith."'
        items, _ = classifier.scan(text)
        for item in items:
            if item.subject_guess:
                assert item.subject_guess.lower() not in {"i", "my", "she"}

    def test_session_start_message(self, classifier):
        text = (
            "Let's start a new story. "
            "Character: Zara is a stubborn girl from the northern city of Ashenmere. "
            "She has dark hair and her mother was a healer."
        )
        items, _ = classifier.scan(text)
        assert len(items) >= 1
        zara_items = [i for i in items if i.subject_guess == "Zara"]
        assert len(zara_items) >= 1


# =============================================================================
# Message ID provenance
# =============================================================================


class TestProvenance:
    """Test that message_id is preserved in captures."""

    def test_message_id_stored(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere", message_id="msg_42")
        for item in items:
            assert item.source_message_id == "msg_42"

    def test_empty_message_id_default(self, classifier):
        items, _ = classifier.scan("Zara is from Ashenmere")
        for item in items:
            assert item.source_message_id == ""
