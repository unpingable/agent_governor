# SPDX-License-Identifier: Apache-2.0
"""Tests for plan_review kernel: Proposal → compile_agenda → Agenda.

The spine under test:
    Proposal is speech.  Agenda is authority.  Compile is the
    governed narrowing step.

These tests lock the invariants that make compile a constitutional
object: determinism, total coverage, explicit lossy reporting, and
refusal of silent prose inheritance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.plan_review import (
    DECISION_APPROVE,
    DECISION_MARK_INERT,
    DECISION_NARROW,
    DECISION_NEEDS_EVIDENCE,
    DECISION_REJECT,
    EVENT_AGENDA_COMPILED,
    EVENT_AGENDA_SECTION_DROPPED,
    EVENT_AGENDA_SECTION_NARROWED,
    MODE_AUTONOMOUS,
    MODE_DRY_RUN,
    MODE_INTERACTIVE,
    Agenda,
    AgendaStep,
    CompileResult,
    DroppedSection,
    Event,
    NarrowedSection,
    Proposal,
    ProposalSection,
    SectionDecision,
    compile_agenda,
)


FIXED_TS = "2026-04-15T00:00:00+00:00"
ALT_TS = "2099-01-01T00:00:00+00:00"


# =============================================================================
# Helpers
# =============================================================================


def _make_proposal(
    *,
    proposal_id: str = "plan-001",
    revision: int = 1,
    sections: list[ProposalSection] | None = None,
) -> Proposal:
    if sections is None:
        sections = [
            ProposalSection(
                section_id="s1",
                goal="Refactor auth middleware",
                scope="src/auth/*.py",
                assumptions=("tests exist",),
                likely_tools=("Edit", "Grep"),
            ),
            ProposalSection(
                section_id="s2",
                goal="Add rate limiting",
                scope="src/api/rate.py",
            ),
            ProposalSection(
                section_id="s3",
                goal="Write blog post",
                scope="docs/blog/",
            ),
        ]
    return Proposal(
        proposal_id=proposal_id,
        revision=revision,
        sections=tuple(sections),
    )


def _default_decisions() -> list[SectionDecision]:
    return [
        SectionDecision(section_id="s1", kind=DECISION_APPROVE, reason="looks good"),
        SectionDecision(
            section_id="s2",
            kind=DECISION_NARROW,
            reason="tighten scope",
            narrowed_goal="Add rate limiting to POST /login only",
            narrowed_scope="src/api/rate.py (login endpoint only)",
        ),
        SectionDecision(section_id="s3", kind=DECISION_REJECT, reason="out of scope"),
    ]


# =============================================================================
# ProposalSection / Proposal
# =============================================================================


class TestProposalBasics:
    def test_duplicate_section_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate section_ids"):
            Proposal(
                proposal_id="p",
                revision=0,
                sections=(
                    ProposalSection(section_id="s1", goal="g", scope="sc"),
                    ProposalSection(section_id="s1", goal="g2", scope="sc2"),
                ),
            )

    def test_negative_revision_rejected(self) -> None:
        with pytest.raises(ValueError, match="revision"):
            Proposal(proposal_id="p", revision=-1, sections=())

    def test_proposal_hash_is_sha256_prefixed(self) -> None:
        h = _make_proposal().proposal_hash()
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_author_and_created_at_are_metadata(self) -> None:
        p1 = _make_proposal()
        # Build a copy with author/created_at set; hash must match.
        p2 = Proposal(
            proposal_id=p1.proposal_id,
            revision=p1.revision,
            sections=p1.sections,
            author="alice",
            created_at="2026-04-15T00:00:00+00:00",
        )
        assert p1.proposal_hash() == p2.proposal_hash()


class TestProposalHashSensitivity:
    def test_section_order_matters(self) -> None:
        p1 = _make_proposal()
        p2 = _make_proposal(sections=list(reversed(p1.sections)))
        assert p1.proposal_hash() != p2.proposal_hash()

    def test_revision_matters(self) -> None:
        p1 = _make_proposal(revision=1)
        p2 = _make_proposal(revision=2)
        assert p1.proposal_hash() != p2.proposal_hash()

    def test_proposal_id_matters(self) -> None:
        p1 = _make_proposal(proposal_id="A")
        p2 = _make_proposal(proposal_id="B")
        assert p1.proposal_hash() != p2.proposal_hash()

    def test_section_content_matters(self) -> None:
        p1 = _make_proposal()
        altered = list(p1.sections)
        altered[0] = ProposalSection(
            section_id=altered[0].section_id,
            goal=altered[0].goal + " (changed)",
            scope=altered[0].scope,
        )
        p2 = _make_proposal(sections=altered)
        assert p1.proposal_hash() != p2.proposal_hash()


# =============================================================================
# SectionDecision invariants
# =============================================================================


class TestSectionDecision:
    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid decision kind"):
            SectionDecision(section_id="s", kind="maybe")

    def test_invalid_execution_mode_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid execution_mode"):
            SectionDecision(section_id="s", kind=DECISION_APPROVE, execution_mode="yolo")

    def test_narrow_requires_both_narrowed_fields(self) -> None:
        with pytest.raises(ValueError, match="narrowed_goal and narrowed_scope"):
            SectionDecision(section_id="s", kind=DECISION_NARROW, narrowed_goal="tighter")
        with pytest.raises(ValueError, match="narrowed_goal and narrowed_scope"):
            SectionDecision(section_id="s", kind=DECISION_NARROW, narrowed_scope="tighter")
        with pytest.raises(ValueError, match="narrowed_goal and narrowed_scope"):
            SectionDecision(section_id="s", kind=DECISION_NARROW)

    def test_narrowed_fields_rejected_on_non_narrow(self) -> None:
        with pytest.raises(ValueError, match="only valid for NARROW"):
            SectionDecision(
                section_id="s", kind=DECISION_APPROVE, narrowed_goal="x", narrowed_scope="y",
            )
        with pytest.raises(ValueError, match="only valid for NARROW"):
            SectionDecision(
                section_id="s", kind=DECISION_REJECT, narrowed_goal="x", narrowed_scope="y",
            )


# =============================================================================
# compile_agenda: coverage enforcement
# =============================================================================


class TestCompileCoverage:
    def test_missing_decision_raises(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(section_id="s1", kind=DECISION_APPROVE),
            SectionDecision(section_id="s2", kind=DECISION_APPROVE),
            # s3 missing
        ]
        with pytest.raises(ValueError, match="do not cover every section"):
            compile_agenda(p, decisions)

    def test_duplicate_decision_raises(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(section_id="s1", kind=DECISION_APPROVE),
            SectionDecision(section_id="s1", kind=DECISION_REJECT),
            SectionDecision(section_id="s2", kind=DECISION_APPROVE),
            SectionDecision(section_id="s3", kind=DECISION_REJECT),
        ]
        with pytest.raises(ValueError, match="Duplicate decision"):
            compile_agenda(p, decisions)

    def test_unknown_section_raises(self) -> None:
        p = _make_proposal()
        decisions = _default_decisions() + [
            SectionDecision(section_id="s_ghost", kind=DECISION_APPROVE),
        ]
        with pytest.raises(ValueError, match="unknown section_ids"):
            compile_agenda(p, decisions)


# =============================================================================
# compile_agenda: lossy reporting & narrowing
# =============================================================================


class TestCompileBehaviour:
    def test_every_section_accounted_for(self) -> None:
        """No silent loss: each section is either a step or appears in dropped."""
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        step_ids = {s.source_section_id for s in result.agenda.steps}
        dropped_ids = {d.section_id for d in result.dropped}
        all_ids = step_ids | dropped_ids
        assert all_ids == {s.section_id for s in p.sections}
        assert not (step_ids & dropped_ids)

    def test_narrow_produces_step_with_narrowed_prose(self) -> None:
        """Narrowed steps must carry the narrowed goal/scope, NEVER the original."""
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        s2_step = next(s for s in result.agenda.steps if s.source_section_id == "s2")
        assert s2_step.goal == "Add rate limiting to POST /login only"
        assert s2_step.scope == "src/api/rate.py (login endpoint only)"
        # The original broad prose MUST NOT appear in the step.
        assert s2_step.goal != "Add rate limiting"
        assert s2_step.scope != "src/api/rate.py"

    def test_narrow_reported_with_both_originals_and_narrowed(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        assert len(result.narrowed) == 1
        narr = result.narrowed[0]
        assert narr.section_id == "s2"
        assert narr.original_goal == "Add rate limiting"
        assert narr.narrowed_goal == "Add rate limiting to POST /login only"

    def test_approved_section_inherits_original_prose(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        s1_step = next(s for s in result.agenda.steps if s.source_section_id == "s1")
        assert s1_step.goal == "Refactor auth middleware"
        assert s1_step.scope == "src/auth/*.py"

    def test_dropped_kinds_preserved(self) -> None:
        p = _make_proposal(sections=[
            ProposalSection(section_id="a", goal="g", scope="s"),
            ProposalSection(section_id="b", goal="g", scope="s"),
            ProposalSection(section_id="c", goal="g", scope="s"),
        ])
        decisions = [
            SectionDecision(section_id="a", kind=DECISION_REJECT, reason="r"),
            SectionDecision(section_id="b", kind=DECISION_MARK_INERT, reason="info"),
            SectionDecision(section_id="c", kind=DECISION_NEEDS_EVIDENCE, reason="later"),
        ]
        result = compile_agenda(p, decisions, timestamp=FIXED_TS)
        kinds = {d.section_id: d.decision_kind for d in result.dropped}
        assert kinds == {
            "a": DECISION_REJECT,
            "b": DECISION_MARK_INERT,
            "c": DECISION_NEEDS_EVIDENCE,
        }
        assert len(result.agenda.steps) == 0

    def test_steps_preserve_proposal_order(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(section_id="s1", kind=DECISION_APPROVE),
            SectionDecision(section_id="s2", kind=DECISION_APPROVE),
            SectionDecision(section_id="s3", kind=DECISION_APPROVE),
        ]
        result = compile_agenda(p, decisions, timestamp=FIXED_TS)
        assert [s.source_section_id for s in result.agenda.steps] == ["s1", "s2", "s3"]

    def test_all_reject_yields_empty_agenda(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(section_id=s.section_id, kind=DECISION_REJECT)
            for s in p.sections
        ]
        result = compile_agenda(p, decisions, timestamp=FIXED_TS)
        assert result.agenda.steps == ()
        assert len(result.dropped) == 3
        # Still a valid, hashable, authority object.
        assert result.agenda_hash.startswith("sha256:")

    def test_agenda_lineage_to_proposal(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        assert result.agenda.source_proposal_hash == p.proposal_hash()
        assert result.proposal_hash == p.proposal_hash()
        assert result.agenda_hash == result.agenda.agenda_hash()

    def test_step_carries_tool_envelope_and_mode(self) -> None:
        p = _make_proposal(sections=[
            ProposalSection(section_id="s1", goal="g", scope="sc"),
        ])
        decisions = [
            SectionDecision(
                section_id="s1",
                kind=DECISION_APPROVE,
                allowed_tools=("Read", "Edit"),
                blocked_tools=("Bash",),
                execution_mode=MODE_AUTONOMOUS,
                budget_ceiling={"max_edits": 3},
            ),
        ]
        result = compile_agenda(p, decisions, timestamp=FIXED_TS)
        step = result.agenda.steps[0]
        assert step.allowed_tools == ("Read", "Edit")
        assert step.blocked_tools == ("Bash",)
        assert step.execution_mode == MODE_AUTONOMOUS
        assert step.budget_ceiling == {"max_edits": 3}


# =============================================================================
# Determinism — the constitutional property
# =============================================================================


class TestDeterminism:
    def test_same_inputs_same_hash(self) -> None:
        p = _make_proposal()
        r1 = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        r2 = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        assert r1.agenda_hash == r2.agenda_hash

    def test_timestamp_does_not_affect_hash(self) -> None:
        p = _make_proposal()
        r1 = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        r2 = compile_agenda(p, _default_decisions(), timestamp=ALT_TS)
        assert r1.agenda_hash == r2.agenda_hash

    def test_agenda_id_does_not_affect_hash(self) -> None:
        p = _make_proposal()
        r1 = compile_agenda(
            p, _default_decisions(), timestamp=FIXED_TS, agenda_id="agenda_alpha",
        )
        r2 = compile_agenda(
            p, _default_decisions(), timestamp=FIXED_TS, agenda_id="agenda_beta",
        )
        assert r1.agenda_hash == r2.agenda_hash
        assert r1.agenda.agenda_id != r2.agenda.agenda_id

    def test_decision_change_changes_hash(self) -> None:
        p = _make_proposal()
        base = _default_decisions()
        altered = list(base)
        altered[0] = SectionDecision(section_id="s1", kind=DECISION_REJECT)
        r1 = compile_agenda(p, base, timestamp=FIXED_TS)
        r2 = compile_agenda(p, altered, timestamp=FIXED_TS)
        assert r1.agenda_hash != r2.agenda_hash

    def test_narrow_prose_change_changes_hash(self) -> None:
        p = _make_proposal()
        base = _default_decisions()
        altered = list(base)
        altered[1] = SectionDecision(
            section_id="s2",
            kind=DECISION_NARROW,
            narrowed_goal="Different narrowed goal",
            narrowed_scope="Different narrowed scope",
        )
        r1 = compile_agenda(p, base, timestamp=FIXED_TS)
        r2 = compile_agenda(p, altered, timestamp=FIXED_TS)
        assert r1.agenda_hash != r2.agenda_hash

    def test_proposal_revision_change_changes_agenda_hash(self) -> None:
        p1 = _make_proposal(revision=1)
        p2 = _make_proposal(revision=2)
        r1 = compile_agenda(p1, _default_decisions(), timestamp=FIXED_TS)
        r2 = compile_agenda(p2, _default_decisions(), timestamp=FIXED_TS)
        assert r1.agenda_hash != r2.agenda_hash

    def test_tool_envelope_change_changes_hash(self) -> None:
        p = _make_proposal(sections=[
            ProposalSection(section_id="s1", goal="g", scope="sc"),
        ])
        d1 = [SectionDecision(section_id="s1", kind=DECISION_APPROVE)]
        d2 = [SectionDecision(
            section_id="s1", kind=DECISION_APPROVE, allowed_tools=("Read",),
        )]
        r1 = compile_agenda(p, d1, timestamp=FIXED_TS)
        r2 = compile_agenda(p, d2, timestamp=FIXED_TS)
        assert r1.agenda_hash != r2.agenda_hash


# =============================================================================
# Events as data
# =============================================================================


class TestEvents:
    def test_compile_event_is_last(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        assert result.events[-1].event_type == EVENT_AGENDA_COMPILED

    def test_section_events_parented_to_compile_event(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        compiled = result.events[-1]
        for ev in result.events[:-1]:
            assert ev.parent_event_id == compiled.event_id

    def test_event_counts_match_result(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        dropped_events = [e for e in result.events if e.event_type == EVENT_AGENDA_SECTION_DROPPED]
        narrowed_events = [e for e in result.events if e.event_type == EVENT_AGENDA_SECTION_NARROWED]
        assert len(dropped_events) == len(result.dropped)
        assert len(narrowed_events) == len(result.narrowed)

    def test_event_ids_are_content_addressed(self) -> None:
        """Same payload → same event_id (timestamp is NOT part of identity)."""
        p = _make_proposal()
        r1 = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        r2 = compile_agenda(p, _default_decisions(), timestamp=ALT_TS)
        # Map by event_type + section_id (if present) for comparison.
        def key(e: Event) -> tuple:
            return (e.event_type, e.payload.get("section_id"))
        ids1 = {key(e): e.event_id for e in r1.events}
        ids2 = {key(e): e.event_id for e in r2.events}
        assert ids1 == ids2

    def test_compile_event_payload_carries_hashes(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        payload = result.events[-1].payload
        assert payload["agenda_hash"] == result.agenda_hash
        assert payload["proposal_hash"] == result.proposal_hash
        assert payload["step_count"] == len(result.agenda.steps)
        assert payload["dropped_count"] == len(result.dropped)
        assert payload["narrowed_count"] == len(result.narrowed)

    def test_dropped_event_payload_preserves_decision_kind(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        drop = next(e for e in result.events if e.event_type == EVENT_AGENDA_SECTION_DROPPED)
        assert drop.payload["section_id"] == "s3"
        assert drop.payload["decision_kind"] == DECISION_REJECT


# =============================================================================
# The spine — proposal_hash ≠ agenda_hash
# =============================================================================


class TestSpineInvariants:
    def test_agenda_hash_differs_from_proposal_hash(self) -> None:
        """Proposal is speech; Agenda is authority; they are different things."""
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        assert result.agenda_hash != result.proposal_hash

    def test_hash_format(self) -> None:
        p = _make_proposal()
        result = compile_agenda(p, _default_decisions(), timestamp=FIXED_TS)
        for h in (result.agenda_hash, result.proposal_hash):
            assert h.startswith("sha256:")
            assert len(h) == len("sha256:") + 64


# =============================================================================
# Golden fixtures — catch "harmless refactor changed semantics" immediately
# =============================================================================


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "plan_review"


def _golden_snapshot(result: CompileResult) -> dict:
    """Canonical snapshot of a CompileResult for golden comparison.

    Timestamps and auto-derived ids are excluded; only content-addressed
    identity (hashes, ordering, decision outcomes) is captured.
    """
    return {
        "proposal_hash": result.proposal_hash,
        "agenda_hash": result.agenda_hash,
        "agenda": {
            "source_proposal_hash": result.agenda.source_proposal_hash,
            "steps": [s.to_canonical_dict() for s in result.agenda.steps],
        },
        "dropped": [
            {"section_id": d.section_id, "kind": d.decision_kind, "reason": d.reason}
            for d in result.dropped
        ],
        "narrowed": [
            {
                "section_id": n.section_id,
                "original_goal": n.original_goal,
                "original_scope": n.original_scope,
                "narrowed_goal": n.narrowed_goal,
                "narrowed_scope": n.narrowed_scope,
                "reason": n.reason,
            }
            for n in result.narrowed
        ],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "parent_event_id": e.parent_event_id,
                "payload": e.payload,
            }
            for e in result.events
        ],
    }


class TestGoldens:
    def test_mixed_compile_matches_golden(self) -> None:
        """Full exercise: approve + narrow + reject, locked against a fixture."""
        p = _make_proposal()
        result = compile_agenda(
            p,
            _default_decisions(),
            agenda_id="agenda_plan-001_r1",
            timestamp=FIXED_TS,
        )
        snapshot = _golden_snapshot(result)
        golden_path = FIXTURES_DIR / "mixed_compile.json"
        if not golden_path.exists():
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            pytest.skip(f"Golden created: {golden_path}. Re-run to verify.")
        expected = json.loads(golden_path.read_text())
        assert snapshot == expected, (
            f"Golden mismatch at {golden_path}. If the change is intentional, "
            f"delete the file and re-run to regenerate."
        )

    def test_all_reject_matches_golden(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(
                section_id=s.section_id, kind=DECISION_REJECT, reason=f"no to {s.section_id}",
            )
            for s in p.sections
        ]
        result = compile_agenda(
            p, decisions, agenda_id="agenda_plan-001_r1", timestamp=FIXED_TS,
        )
        snapshot = _golden_snapshot(result)
        golden_path = FIXTURES_DIR / "all_reject.json"
        if not golden_path.exists():
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            pytest.skip(f"Golden created: {golden_path}. Re-run to verify.")
        expected = json.loads(golden_path.read_text())
        assert snapshot == expected

    def test_all_approve_with_modes_matches_golden(self) -> None:
        p = _make_proposal()
        decisions = [
            SectionDecision(
                section_id="s1", kind=DECISION_APPROVE,
                allowed_tools=("Read", "Edit"), execution_mode=MODE_INTERACTIVE,
            ),
            SectionDecision(
                section_id="s2", kind=DECISION_APPROVE,
                allowed_tools=("Read",), blocked_tools=("Bash",),
                execution_mode=MODE_AUTONOMOUS,
                budget_ceiling={"max_files": 5, "max_duration_s": 120},
            ),
            SectionDecision(
                section_id="s3", kind=DECISION_APPROVE,
                execution_mode=MODE_DRY_RUN,
            ),
        ]
        result = compile_agenda(
            p, decisions, agenda_id="agenda_plan-001_r1", timestamp=FIXED_TS,
        )
        snapshot = _golden_snapshot(result)
        golden_path = FIXTURES_DIR / "all_approve_modes.json"
        if not golden_path.exists():
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            pytest.skip(f"Golden created: {golden_path}. Re-run to verify.")
        expected = json.loads(golden_path.read_text())
        assert snapshot == expected
