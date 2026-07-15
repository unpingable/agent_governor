# SPDX-License-Identifier: Apache-2.0
"""Knowledge-path verification — can this character know this, and how?

The failure this exists to catch (operator, 2026-07-15, from a working
author's complaint about LLM drafting tools): *the model produced fluent
prose while violating who could know what.* That is not a taste failure. It
is a state-tracking failure, and structurally it is this constellation's core
crime — an unauthorized projection across an epistemic boundary. Same crime
as a claim becoming relied-upon authority with no standing; nicer prose.

The ladder (only the third rung is taste):

    hard constraint     A was not present for event X.
    derived constraint  A cannot know X unless a transmission path exists.
    soft judgment       Would that path feel dramatically satisfying?

This module adjudicates rungs one and two, mechanically, against canon. It
does not touch rung three: whether a legal path is *good writing* is the
author's call and always will be. ``fiction-gov`` remains advisory — this
verifier reports findings; only an explicit author act changes canon (see
``docs/doctrine/fiction-governor-consumer-boundary.md``).

What is checkable is checkable per CLAIM, not per domain: ``WITNESSED`` and
``TOLD_BY`` name referents canon can adjudicate; ``INFERRED`` and ``ASSUMED``
declare their own lack of external backing and are left alone; ``UNSPECIFIED``
is reported, never passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from fiction_governor.canon import Canon
from fiction_governor.types import Belief, TransmissionKind


class KnowledgeFindingKind(str, Enum):
    """Closed classification for a belief's knowledge path.

    Mirrors the authoring-domain finding classes: a contradiction violates
    canon; an unsupported path has no basis *yet*; a legal extension is new
    material consistent with canon. Aesthetic judgments are deliberately
    absent — this verifier has no opinion about them.
    """

    LEGAL_EXTENSION = "legal_extension"  # path verified against canon
    CONTRADICTION = "contradiction"  # claimed a path canon refutes
    PREMATURE_KNOWLEDGE = "premature_knowledge"  # knew it before it happened
    UNSUPPORTED_PATH = "unsupported_path"  # no verifiable path claimed
    SELF_DECLARED = "self_declared"  # inferred/assumed — claims no backing


#: Finding kinds that represent a canon violation rather than a gap.
BLOCKING_KINDS = frozenset(
    {KnowledgeFindingKind.CONTRADICTION, KnowledgeFindingKind.PREMATURE_KNOWLEDGE}
)


@dataclass(frozen=True)
class KnowledgeFinding:
    """One adjudication of one belief's transmission path."""

    kind: KnowledgeFindingKind
    belief_id: str
    character: str
    belief: str
    message: str
    suggestions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_violation(self) -> bool:
        """Whether canon refutes this belief's claimed path.

        A gap (unsupported/self-declared) is NOT a violation — the author may
        simply not have written the path yet. Conflating "unbacked" with
        "contradicted" is how a useful tool becomes a nag.
        """
        return self.kind in BLOCKING_KINDS


class KnowledgeVerifier:
    """Adjudicate belief transmission paths against canon.

    Advisory by construction: returns findings, mutates nothing. The author
    decides what to do about a contradiction — including deciding canon was
    wrong.
    """

    def __init__(self, canon: Canon):
        self.canon = canon

    def verify_belief(self, belief: Belief) -> KnowledgeFinding:
        path = belief.transmission
        if path is None or path.kind is TransmissionKind.UNSPECIFIED:
            note = (path.note if path else belief.source) or None
            extra = f" (unmigrated note: {note!r})" if note else ""
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.UNSUPPORTED_PATH,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} holds {belief.belief!r} with no stated "
                    f"transmission path{extra} — unverifiable, not necessarily wrong"
                ),
                suggestions=(
                    "Name the canon event they witnessed",
                    "Name who told them, and in which chapter",
                    "Mark it inferred or assumed if it has no external basis",
                ),
            )

        if path.kind in (TransmissionKind.INFERRED, TransmissionKind.ASSUMED):
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.SELF_DECLARED,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} {path.kind.value} {belief.belief!r} — "
                    f"claims no external backing; canon has nothing to refute"
                ),
            )

        if path.kind is TransmissionKind.WITNESSED:
            return self._verify_witnessed(belief)
        return self._verify_told_by(belief)

    def _verify_witnessed(self, belief: Belief) -> KnowledgeFinding:
        path = belief.transmission
        assert path is not None and path.event_id is not None  # construction-enforced
        event = self.canon.get_event(path.event_id)

        if event is None:
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.CONTRADICTION,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} claims to have witnessed event "
                    f"{path.event_id} — no such event exists in canon"
                ),
                suggestions=("Record the event in canon", "Correct the event reference"),
            )

        present = {c.lower() for c in event.characters}
        if belief.character.lower() not in present:
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.CONTRADICTION,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} claims to have witnessed "
                    f"{event.summary!r} (ch. {event.chapter}) but is not present "
                    f"in that event — canon lists: "
                    f"{', '.join(event.characters) or '(nobody)'}"
                ),
                suggestions=(
                    f"Add {belief.character} to the event's characters",
                    "Give them a transmission path instead (who told them?)",
                    "Mark the belief inferred or assumed",
                ),
            )

        if event.chapter > belief.learned_at_chapter:
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.PREMATURE_KNOWLEDGE,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} holds {belief.belief!r} from chapter "
                    f"{belief.learned_at_chapter}, but the event they cite happens "
                    f"in chapter {event.chapter} — they know it before it happens"
                ),
                suggestions=(
                    "Move the belief later",
                    "Move the event earlier",
                    "Give them an earlier path to the same knowledge",
                ),
            )

        return KnowledgeFinding(
            kind=KnowledgeFindingKind.LEGAL_EXTENSION,
            belief_id=str(belief.id),
            character=belief.character,
            belief=belief.belief,
            message=(
                f"{belief.character} witnessed {event.summary!r} "
                f"(ch. {event.chapter}) — path holds"
            ),
        )

    def _verify_told_by(self, belief: Belief) -> KnowledgeFinding:
        path = belief.transmission
        assert path is not None and path.teller  # construction-enforced
        teller = path.teller

        if not self.canon.events_with_character(teller):
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.UNSUPPORTED_PATH,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} was told {belief.belief!r} by {teller}, "
                    f"who appears in no canon event — the teller is unbacked"
                ),
                suggestions=(f"Record an event involving {teller}",),
            )

        if path.at_chapter is not None and path.at_chapter > belief.learned_at_chapter:
            return KnowledgeFinding(
                kind=KnowledgeFindingKind.PREMATURE_KNOWLEDGE,
                belief_id=str(belief.id),
                character=belief.character,
                belief=belief.belief,
                message=(
                    f"{belief.character} holds {belief.belief!r} from chapter "
                    f"{belief.learned_at_chapter}, but {teller} tells them in "
                    f"chapter {path.at_chapter} — told after the fact"
                ),
                suggestions=("Move the telling earlier", "Move the belief later"),
            )

        # NOT verified here: whether the TELLER had a path to the knowledge.
        # That is the recursive case (a chain of custody through characters) and
        # it is deliberately out of this slice — claiming to check it while only
        # checking the teller exists would be exactly the laundering this module
        # was built to refuse. Named, not built.
        return KnowledgeFinding(
            kind=KnowledgeFindingKind.LEGAL_EXTENSION,
            belief_id=str(belief.id),
            character=belief.character,
            belief=belief.belief,
            message=(
                f"{belief.character} was told {belief.belief!r} by {teller} — "
                f"teller exists and timing holds (teller's own path not checked)"
            ),
        )

    def verify_all(self, beliefs: list[Belief]) -> list[KnowledgeFinding]:
        """Adjudicate a set of beliefs, held beliefs only.

        Invalidated beliefs are excluded: a character who learned they were
        wrong is not currently making the claim.
        """
        return [self.verify_belief(b) for b in beliefs if b.is_held]

    def violations(self, beliefs: list[Belief]) -> list[KnowledgeFinding]:
        """Only the findings canon actively refutes."""
        return [f for f in self.verify_all(beliefs) if f.is_violation]
