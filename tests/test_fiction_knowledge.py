# SPDX-License-Identifier: Apache-2.0
"""Knowledge-path verification — the canon-loss failure, mechanically caught.

The specimen (a working author's complaint about LLM drafting tools): the
model wrote a character knowing something they never witnessed. Fluent prose,
violated epistemic boundary. This suite pins that it is now a finding rather
than a vibe.

The ladder under test — only the third rung is taste, and it is absent here
by design:

    hard      A was not present for event X.
    derived   A cannot know X unless a transmission path exists.
    soft      Would that path feel dramatically satisfying?  (author's call)
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from fiction_governor.canon import Canon
from fiction_governor.knowledge import (
    KnowledgeFindingKind,
    KnowledgeVerifier,
)
from fiction_governor.types import (
    Belief,
    TransmissionKind,
    TransmissionPath,
    migrate_legacy_source,
)


@pytest.fixture
def canon(tmp_path):
    return Canon(tmp_path)


@pytest.fixture
def verifier(canon):
    return KnowledgeVerifier(canon)


def _belief(character: str, text: str, chapter: int, transmission=None) -> Belief:
    return Belief(
        character=character,
        belief=text,
        learned_at_chapter=chapter,
        transmission=transmission,
    )


class TestTheSpecimen:
    """THE failure: a character knows something they never witnessed."""

    def test_character_who_was_not_there_cannot_have_witnessed_it(
        self, canon, verifier
    ):
        # Marcus dies in chapter 3. Elena is not in the room.
        event = canon.add_event(
            chapter=3,
            summary="Marcus dies in the cellar",
            characters=["Marcus", "Ines"],
            location="cellar",
        )
        # The draft has Elena reacting to his death as though she saw it.
        belief = _belief(
            "Elena",
            "Marcus is dead",
            chapter=4,
            transmission=TransmissionPath(
                kind=TransmissionKind.WITNESSED, event_id=event.id
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.CONTRADICTION
        assert finding.is_violation
        assert "not present" in finding.message
        assert "Marcus, Ines" in finding.message  # names who WAS there
        # The tool proposes author moves; it does not pick one.
        assert any("told them" in s for s in finding.suggestions)

    def test_the_same_belief_is_legal_once_she_is_actually_there(
        self, canon, verifier
    ):
        event = canon.add_event(
            chapter=3,
            summary="Marcus dies in the cellar",
            characters=["Marcus", "Ines", "Elena"],
            location="cellar",
        )
        belief = _belief(
            "Elena",
            "Marcus is dead",
            chapter=4,
            transmission=TransmissionPath(
                kind=TransmissionKind.WITNESSED, event_id=event.id
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.LEGAL_EXTENSION
        assert not finding.is_violation

    def test_and_legal_again_once_someone_tells_her(self, canon, verifier):
        """The derived constraint: a transmission path rescues the belief."""
        canon.add_event(
            chapter=3,
            summary="Marcus dies in the cellar",
            characters=["Marcus", "Ines"],
        )
        belief = _belief(
            "Elena",
            "Marcus is dead",
            chapter=4,
            transmission=TransmissionPath(
                kind=TransmissionKind.TOLD_BY, teller="Ines", at_chapter=4
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.LEGAL_EXTENSION


class TestPrematureKnowledge:
    def test_knowing_before_it_happens(self, canon, verifier):
        event = canon.add_event(
            chapter=7, summary="The letter arrives", characters=["Elena"]
        )
        belief = _belief(
            "Elena",
            "the letter arrived",
            chapter=2,  # she holds it five chapters early
            transmission=TransmissionPath(
                kind=TransmissionKind.WITNESSED, event_id=event.id
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.PREMATURE_KNOWLEDGE
        assert finding.is_violation
        assert "before it happens" in finding.message

    def test_told_after_the_fact(self, canon, verifier):
        canon.add_event(chapter=1, summary="A meeting", characters=["Ines"])
        belief = _belief(
            "Elena",
            "the plan changed",
            chapter=2,
            transmission=TransmissionPath(
                kind=TransmissionKind.TOLD_BY, teller="Ines", at_chapter=5
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.PREMATURE_KNOWLEDGE

    def test_witnessed_event_that_does_not_exist(self, canon, verifier):
        belief = _belief(
            "Elena",
            "something happened",
            chapter=4,
            transmission=TransmissionPath(
                kind=TransmissionKind.WITNESSED, event_id=uuid4()
            ),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.CONTRADICTION
        assert "no such event" in finding.message


class TestGapIsNotViolation:
    """A gap means the author hasn't written it yet. Conflating that with a
    contradiction is how a useful tool becomes a nag."""

    def test_unspecified_path_is_unsupported_not_contradiction(self, verifier):
        belief = _belief("Elena", "Marcus is dead", 4, TransmissionPath.unspecified())

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.UNSUPPORTED_PATH
        assert not finding.is_violation
        assert "not necessarily wrong" in finding.message

    def test_no_transmission_at_all_is_unsupported(self, verifier):
        finding = verifier.verify_belief(_belief("Elena", "Marcus is dead", 4))
        assert finding.kind is KnowledgeFindingKind.UNSUPPORTED_PATH

    @pytest.mark.parametrize(
        "kind", [TransmissionKind.INFERRED, TransmissionKind.ASSUMED]
    )
    def test_self_declared_paths_claim_no_backing_so_canon_stays_quiet(
        self, verifier, kind
    ):
        belief = _belief("Elena", "Marcus is dead", 4, TransmissionPath(kind=kind))

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.SELF_DECLARED
        assert not finding.is_violation

    def test_teller_who_appears_nowhere_is_unsupported_not_refuted(self, verifier):
        belief = _belief(
            "Elena",
            "Marcus is dead",
            4,
            TransmissionPath(kind=TransmissionKind.TOLD_BY, teller="Nobody"),
        )

        finding = verifier.verify_belief(belief)

        assert finding.kind is KnowledgeFindingKind.UNSUPPORTED_PATH
        assert not finding.is_violation


class TestUncheckableClaimsRefuseAtConstruction:
    """A WITNESSED claim with nothing to check is uncheckable, not weak —
    same law as operator_mode: the class is earned by evidence, never
    asserted by name."""

    def test_witnessed_without_event_refuses(self):
        with pytest.raises(ValueError, match="requires event_id"):
            TransmissionPath(kind=TransmissionKind.WITNESSED)

    def test_told_by_without_teller_refuses(self):
        with pytest.raises(ValueError, match="requires teller"):
            TransmissionPath(kind=TransmissionKind.TOLD_BY)

    def test_novel_kind_refuses(self):
        with pytest.raises(ValueError):
            TransmissionKind("overheard-ish")

    def test_checkable_is_exactly_the_two_that_name_referents(self):
        event_id = uuid4()
        assert TransmissionPath(TransmissionKind.WITNESSED, event_id=event_id).is_checkable
        assert TransmissionPath(TransmissionKind.TOLD_BY, teller="X").is_checkable
        assert not TransmissionPath(TransmissionKind.INFERRED).is_checkable
        assert not TransmissionPath(TransmissionKind.ASSUMED).is_checkable
        assert not TransmissionPath.unspecified().is_checkable


class TestLegacyMigration:
    """An old free-form string was never evidence. Promoting it now would
    manufacture custody the data never had."""

    def test_legacy_witnessed_string_does_not_become_a_checkable_claim(self):
        path = migrate_legacy_source("witnessed")
        assert path.kind is TransmissionKind.UNSPECIFIED
        assert path.note == "witnessed"  # retained as display

    def test_legacy_told_by_string_does_not_become_a_checkable_claim(self):
        path = migrate_legacy_source("told by Ines")
        assert path.kind is TransmissionKind.UNSPECIFIED
        assert path.note == "told by Ines"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("inferred", TransmissionKind.INFERRED),
            ("assumed", TransmissionKind.ASSUMED),
            ("Assumption", TransmissionKind.ASSUMED),
        ],
    )
    def test_self_declaring_strings_migrate_because_they_launder_nothing(
        self, text, expected
    ):
        assert migrate_legacy_source(text).kind is expected

    def test_absent_source_is_unspecified(self):
        assert migrate_legacy_source(None).kind is TransmissionKind.UNSPECIFIED
        assert migrate_legacy_source("   ").kind is TransmissionKind.UNSPECIFIED

    def test_legacy_belief_roundtrips_and_migrates(self):
        legacy = {
            "id": str(uuid4()),
            "character": "Elena",
            "belief": "Marcus is dead",
            "learned_at_chapter": 4,
            "source": "witnessed",
            "created_at": "2026-07-15T00:00:00+00:00",
        }

        belief = Belief.from_dict(legacy)

        assert belief.source == "witnessed"  # free text untouched, display only
        assert belief.transmission.kind is TransmissionKind.UNSPECIFIED
        # And it round-trips through the typed field.
        again = Belief.from_dict(belief.to_dict())
        assert again.transmission.kind is TransmissionKind.UNSPECIFIED
        assert again.source == "witnessed"

    def test_typed_transmission_survives_roundtrip(self, canon):
        event = canon.add_event(chapter=1, summary="X", characters=["Elena"])
        belief = _belief(
            "Elena",
            "x happened",
            1,
            TransmissionPath(kind=TransmissionKind.WITNESSED, event_id=event.id),
        )

        again = Belief.from_dict(belief.to_dict())

        assert again.transmission.kind is TransmissionKind.WITNESSED
        assert again.transmission.event_id == event.id


class TestBatch:
    def test_violations_filters_gaps_out(self, canon, verifier):
        event = canon.add_event(chapter=3, summary="M dies", characters=["Ines"])
        beliefs = [
            _belief(
                "Elena", "Marcus is dead", 4,
                TransmissionPath(TransmissionKind.WITNESSED, event_id=event.id),
            ),  # contradiction
            _belief("Ines", "it is cold", 4, TransmissionPath.unspecified()),  # gap
            _belief(
                "Ines", "Marcus is dead", 4,
                TransmissionPath(TransmissionKind.WITNESSED, event_id=event.id),
            ),  # legal
        ]

        assert len(verifier.verify_all(beliefs)) == 3
        violations = verifier.violations(beliefs)
        assert len(violations) == 1
        assert violations[0].character == "Elena"

    def test_invalidated_beliefs_are_not_current_claims(self, canon, verifier):
        event = canon.add_event(chapter=3, summary="M dies", characters=["Ines"])
        stale = _belief(
            "Elena", "Marcus is dead", 4,
            TransmissionPath(TransmissionKind.WITNESSED, event_id=event.id),
        )
        stale.invalidated_at_chapter = 5  # she learned she was wrong

        assert verifier.verify_all([stale]) == []
