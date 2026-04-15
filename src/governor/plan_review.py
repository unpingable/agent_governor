# SPDX-License-Identifier: Apache-2.0
"""
Plan Review — the authority boundary between speech and action.

    Proposal is speech.  Agenda is authority.  Compile is the governed
    narrowing step.

A Proposal is an inert language object: goals, scope, assumptions.  It is
never executable.  A human review assigns per-section decisions, and the
compile step produces an Agenda: an immutable, content-addressed authority
object that the executor may act on.

This module is the *kernel only*:
  - dataclasses (Proposal, ProposalSection, SectionDecision, Agenda,
    AgendaStep, DroppedSection, NarrowedSection, Event, CompileResult)
  - canonical JSON + content-addressed hashing
  - compile_agenda(): deterministic, returns events as data

No CLI, no state machine, no receipt I/O.  Those live in later slices.
The compile function is a pure, total function on (Proposal, decisions):
same inputs → same agenda_hash, always.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .gate_receipt import canonical_json, content_hash

# =============================================================================
# Schema
# =============================================================================

PLAN_REVIEW_SCHEMA_VERSION = 1


# =============================================================================
# Decision kinds (closed set)
# =============================================================================

DECISION_APPROVE = "approve"          # section goes to agenda as-is
DECISION_REJECT = "reject"            # section dropped outright
DECISION_NARROW = "narrow"            # section goes to agenda with narrowed scope
DECISION_MARK_INERT = "mark_inert"    # section dropped — informational only
DECISION_NEEDS_EVIDENCE = "needs_evidence"  # section dropped — revisit later

VALID_DECISION_KINDS = frozenset({
    DECISION_APPROVE, DECISION_REJECT, DECISION_NARROW,
    DECISION_MARK_INERT, DECISION_NEEDS_EVIDENCE,
})

# Decisions that drop the section (no step in agenda).
DROPPING_DECISIONS = frozenset({
    DECISION_REJECT, DECISION_MARK_INERT, DECISION_NEEDS_EVIDENCE,
})


# =============================================================================
# Execution modes (closed set)
# =============================================================================

MODE_INTERACTIVE = "interactive"
MODE_AUTONOMOUS = "autonomous"
MODE_DRY_RUN = "dry_run"

VALID_EXECUTION_MODES = frozenset({
    MODE_INTERACTIVE, MODE_AUTONOMOUS, MODE_DRY_RUN,
})


# =============================================================================
# Event taxonomy (frozen namespaces — append only, never rename)
# =============================================================================

EVENT_AGENDA_COMPILED = "agenda.compiled"
EVENT_AGENDA_SECTION_DROPPED = "agenda.section_dropped"
EVENT_AGENDA_SECTION_NARROWED = "agenda.section_narrowed"

KERNEL_EVENT_TYPES = frozenset({
    EVENT_AGENDA_COMPILED,
    EVENT_AGENDA_SECTION_DROPPED,
    EVENT_AGENDA_SECTION_NARROWED,
})


# =============================================================================
# Proposal (inert speech)
# =============================================================================


@dataclass(frozen=True)
class ProposalSection:
    """An addressable block of a proposal.

    goal and scope are prose.  assumptions, unknowns, and likely_tools are
    structured lists.  budget_estimate is free-form metadata — the authority
    budget lives on AgendaStep, not here.
    """

    section_id: str
    goal: str
    scope: str
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    likely_tools: tuple[str, ...] = ()
    budget_estimate: dict[str, Any] | None = None

    def to_canonical_dict(self) -> dict[str, Any]:
        """Canonical form for hashing.  Order-sensitive, timestamp-free."""
        d: dict[str, Any] = {
            "section_id": self.section_id,
            "goal": self.goal,
            "scope": self.scope,
            "assumptions": list(self.assumptions),
            "unknowns": list(self.unknowns),
            "likely_tools": list(self.likely_tools),
        }
        if self.budget_estimate is not None:
            d["budget_estimate"] = self.budget_estimate
        return d


@dataclass(frozen=True)
class Proposal:
    """An inert, content-addressed language object.

    A Proposal never executes.  It is speech.  It is the input to human
    review and, after review, to compile_agenda().

    proposal_hash() is content-addressed: same sections in same order,
    same revision → same hash.  Author / timestamp are metadata and do
    not participate in the hash.
    """

    proposal_id: str
    revision: int
    sections: tuple[ProposalSection, ...]
    author: str | None = None
    created_at: str | None = None  # metadata, not hashed

    def __post_init__(self) -> None:
        ids = [s.section_id for s in self.sections]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Proposal {self.proposal_id!r}: duplicate section_ids in {ids!r}")
        if self.revision < 0:
            raise ValueError(f"Proposal revision must be >= 0, got {self.revision}")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PLAN_REVIEW_SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "revision": self.revision,
            "sections": [s.to_canonical_dict() for s in self.sections],
        }

    def proposal_hash(self) -> str:
        return "sha256:" + content_hash(canonical_json(self.to_canonical_dict()))


# =============================================================================
# Review decisions
# =============================================================================


@dataclass(frozen=True)
class SectionDecision:
    """One review decision for one section of a proposal.

    NARROW requires explicit narrowed_goal AND narrowed_scope.  The kernel
    refuses to silently inherit the original prose when narrowing — that
    would let broad language carry through authority.

    allowed_tools / blocked_tools / execution_mode / budget_ceiling apply
    only to APPROVE and NARROW decisions (they become part of the
    AgendaStep).  They are ignored on dropping decisions.
    """

    section_id: str
    kind: str
    reason: str = ""
    narrowed_goal: str | None = None
    narrowed_scope: str | None = None
    allowed_tools: tuple[str, ...] | None = None
    blocked_tools: tuple[str, ...] | None = None
    execution_mode: str = MODE_INTERACTIVE
    budget_ceiling: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_DECISION_KINDS:
            raise ValueError(
                f"Invalid decision kind {self.kind!r}; "
                f"must be one of {sorted(VALID_DECISION_KINDS)}"
            )
        if self.execution_mode not in VALID_EXECUTION_MODES:
            raise ValueError(
                f"Invalid execution_mode {self.execution_mode!r}; "
                f"must be one of {sorted(VALID_EXECUTION_MODES)}"
            )
        if self.kind == DECISION_NARROW:
            if not self.narrowed_goal or not self.narrowed_scope:
                raise ValueError(
                    f"NARROW decision for section {self.section_id!r} requires "
                    f"both narrowed_goal and narrowed_scope (no silent inheritance "
                    f"of broad prose)"
                )
        else:
            if self.narrowed_goal is not None or self.narrowed_scope is not None:
                raise ValueError(
                    f"narrowed_goal/narrowed_scope only valid for NARROW decisions; "
                    f"section {self.section_id!r} has kind={self.kind}"
                )


# =============================================================================
# Agenda (authority)
# =============================================================================


@dataclass(frozen=True)
class AgendaStep:
    """An ordered, executable step authorized by an Agenda.

    allowed_tools/blocked_tools define the tool envelope.  execution_mode
    and budget_ceiling define the authority limits.  source_section_id
    carries lineage back to the proposal.
    """

    step_id: str
    source_section_id: str
    goal: str
    scope: str
    allowed_tools: tuple[str, ...] | None
    blocked_tools: tuple[str, ...] | None
    execution_mode: str
    budget_ceiling: dict[str, Any] | None = None

    def to_canonical_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "step_id": self.step_id,
            "source_section_id": self.source_section_id,
            "goal": self.goal,
            "scope": self.scope,
            "execution_mode": self.execution_mode,
        }
        if self.allowed_tools is not None:
            d["allowed_tools"] = list(self.allowed_tools)
        if self.blocked_tools is not None:
            d["blocked_tools"] = list(self.blocked_tools)
        if self.budget_ceiling is not None:
            d["budget_ceiling"] = self.budget_ceiling
        return d


@dataclass(frozen=True)
class Agenda:
    """The authority object produced by compile_agenda.

    An Agenda is immutable.  Its identity is its agenda_hash.  It derives
    from exactly one proposal revision (source_proposal_hash).

    An Agenda with zero steps is valid — it represents a proposal that
    was reviewed and fully rejected.  It still produces a receiptable
    compile result; it just authorizes nothing.
    """

    agenda_id: str
    source_proposal_hash: str
    steps: tuple[AgendaStep, ...]

    def __post_init__(self) -> None:
        ids = [s.step_id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Agenda {self.agenda_id!r}: duplicate step_ids in {ids!r}")

    def to_canonical_dict(self) -> dict[str, Any]:
        """Canonical form for hashing.

        agenda_id is excluded — it is a human-facing label, not content.
        Identity is determined by source_proposal_hash + steps.
        """
        return {
            "schema_version": PLAN_REVIEW_SCHEMA_VERSION,
            "source_proposal_hash": self.source_proposal_hash,
            "steps": [s.to_canonical_dict() for s in self.steps],
        }

    def agenda_hash(self) -> str:
        return "sha256:" + content_hash(canonical_json(self.to_canonical_dict()))


# =============================================================================
# Lossy-compile reporting
# =============================================================================


@dataclass(frozen=True)
class DroppedSection:
    """A section that did not become an AgendaStep.

    Dropped sections are either REJECT, MARK_INERT, or NEEDS_EVIDENCE.
    The decision kind is preserved so downstream readers can distinguish.
    """

    section_id: str
    decision_kind: str
    reason: str


@dataclass(frozen=True)
class NarrowedSection:
    """A section whose scope was narrowed during compile.

    Preserves the original and narrowed forms so the lossy transformation
    is inspectable.  This is the audit record of the narrowing step.
    """

    section_id: str
    original_goal: str
    original_scope: str
    narrowed_goal: str
    narrowed_scope: str
    reason: str


# =============================================================================
# Events (as data — emitted by compile, consumed by slice 2)
# =============================================================================


@dataclass(frozen=True)
class Event:
    """A compile-step event.

    events are content-addressed: event_id = H(event_type + canonical_json(payload)).
    timestamp and parent_event_id are metadata and do NOT affect event_id.

    Events are returned from compile_agenda() as data.  Slice 2 will wire
    them through gate_receipt.py; slice 1 just produces them.
    """

    event_id: str
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    parent_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.event_type not in KERNEL_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type {self.event_type!r}; "
                f"must be one of {sorted(KERNEL_EVENT_TYPES)}"
            )


def _make_event(
    event_type: str,
    payload: dict[str, Any],
    timestamp: str,
    parent_event_id: str | None = None,
) -> Event:
    """Construct an Event with content-addressed event_id."""
    identity = canonical_json({"event_type": event_type, "payload": payload})
    event_id = "sha256:" + content_hash(identity)
    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        payload=payload,
        parent_event_id=parent_event_id,
    )


# =============================================================================
# Compile result
# =============================================================================


@dataclass(frozen=True)
class CompileResult:
    """The complete, data-only output of compile_agenda().

    agenda is always present (may have zero steps).  agenda_hash and
    proposal_hash are redundant with agenda.agenda_hash() /
    source_proposal_hash but hoisted here for convenient logging.

    events are ordered: the agenda.compiled event comes last, after any
    section-level drop/narrow events (so its payload can reference
    completed lists).
    """

    agenda: Agenda
    agenda_hash: str
    proposal_hash: str
    dropped: tuple[DroppedSection, ...]
    narrowed: tuple[NarrowedSection, ...]
    events: tuple[Event, ...]
    compile_notes: tuple[str, ...] = ()


# =============================================================================
# Compile function — the constitutional object
# =============================================================================


def compile_agenda(
    proposal: Proposal,
    decisions: list[SectionDecision] | tuple[SectionDecision, ...],
    *,
    agenda_id: str | None = None,
    timestamp: str | None = None,
) -> CompileResult:
    """Compile a reviewed proposal into an executable agenda.

    This is the constitutional object of plan review.  Identity invariants:

      - Pure function of (proposal, decisions).  Same inputs → same
        agenda_hash.  (timestamp and agenda_id affect metadata only, not
        the hash.)
      - Every proposal section is explained: either it becomes an
        AgendaStep (approve/narrow), or it appears in dropped with its
        decision kind.  Nothing disappears silently.
      - NARROW decisions use the explicit narrowed_goal/narrowed_scope.
        The original proposal prose is never inherited silently into
        an agenda step.

    Refuses (raises ValueError) if:
      - decisions do not cover every section in the proposal
      - decisions reference unknown section_ids
      - two decisions reference the same section_id

    Returns a CompileResult with events as data — this kernel does not
    emit events to a receipt store.  The caller (slice 2) wires events
    through gate_receipt.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    agenda_id = agenda_id or f"agenda_{proposal.proposal_id}_r{proposal.revision}"

    # --- Validate decision coverage ---
    section_ids = [s.section_id for s in proposal.sections]
    section_id_set = set(section_ids)
    decision_ids = [d.section_id for d in decisions]

    seen: set[str] = set()
    for did in decision_ids:
        if did in seen:
            raise ValueError(f"Duplicate decision for section {did!r}")
        seen.add(did)

    unknown = seen - section_id_set
    if unknown:
        raise ValueError(
            f"Decisions reference unknown section_ids: {sorted(unknown)}"
        )
    missing = section_id_set - seen
    if missing:
        raise ValueError(
            f"Decisions do not cover every section; missing: {sorted(missing)}"
        )

    decision_by_id = {d.section_id: d for d in decisions}
    proposal_hash_val = proposal.proposal_hash()

    # --- Walk sections in proposal order, building outputs ---
    steps: list[AgendaStep] = []
    dropped: list[DroppedSection] = []
    narrowed: list[NarrowedSection] = []
    section_events: list[Event] = []

    for section in proposal.sections:
        decision = decision_by_id[section.section_id]

        if decision.kind in DROPPING_DECISIONS:
            record = DroppedSection(
                section_id=section.section_id,
                decision_kind=decision.kind,
                reason=decision.reason,
            )
            dropped.append(record)
            section_events.append(_make_event(
                EVENT_AGENDA_SECTION_DROPPED,
                {
                    "section_id": section.section_id,
                    "decision_kind": decision.kind,
                    "reason": decision.reason,
                    "proposal_hash": proposal_hash_val,
                },
                timestamp=ts,
            ))
            continue

        # APPROVE or NARROW → produce a step
        if decision.kind == DECISION_NARROW:
            goal = decision.narrowed_goal  # guaranteed non-None by SectionDecision check
            scope = decision.narrowed_scope
            narrowed.append(NarrowedSection(
                section_id=section.section_id,
                original_goal=section.goal,
                original_scope=section.scope,
                narrowed_goal=goal,
                narrowed_scope=scope,
                reason=decision.reason,
            ))
            section_events.append(_make_event(
                EVENT_AGENDA_SECTION_NARROWED,
                {
                    "section_id": section.section_id,
                    "original_goal": section.goal,
                    "original_scope": section.scope,
                    "narrowed_goal": goal,
                    "narrowed_scope": scope,
                    "reason": decision.reason,
                    "proposal_hash": proposal_hash_val,
                },
                timestamp=ts,
            ))
        else:
            goal = section.goal
            scope = section.scope

        step = AgendaStep(
            step_id=f"step_{section.section_id}",
            source_section_id=section.section_id,
            goal=goal,
            scope=scope,
            allowed_tools=decision.allowed_tools,
            blocked_tools=decision.blocked_tools,
            execution_mode=decision.execution_mode,
            budget_ceiling=decision.budget_ceiling,
        )
        steps.append(step)

    # --- Build the agenda ---
    agenda = Agenda(
        agenda_id=agenda_id,
        source_proposal_hash=proposal_hash_val,
        steps=tuple(steps),
    )
    agenda_hash_val = agenda.agenda_hash()

    # --- Top-level compile event (comes last so it can reference totals) ---
    compiled_event = _make_event(
        EVENT_AGENDA_COMPILED,
        {
            "agenda_id": agenda.agenda_id,
            "agenda_hash": agenda_hash_val,
            "proposal_id": proposal.proposal_id,
            "proposal_revision": proposal.revision,
            "proposal_hash": proposal_hash_val,
            "step_count": len(steps),
            "dropped_count": len(dropped),
            "narrowed_count": len(narrowed),
        },
        timestamp=ts,
    )

    # Parent section events to the compile event for lineage.
    parented_section_events = tuple(
        Event(
            event_id=e.event_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            payload=e.payload,
            parent_event_id=compiled_event.event_id,
        )
        for e in section_events
    )

    notes = [
        f"{len(steps)} step(s) authorized; "
        f"{len(dropped)} dropped; {len(narrowed)} narrowed."
    ]

    return CompileResult(
        agenda=agenda,
        agenda_hash=agenda_hash_val,
        proposal_hash=proposal_hash_val,
        dropped=tuple(dropped),
        narrowed=tuple(narrowed),
        events=parented_section_events + (compiled_event,),
        compile_notes=tuple(notes),
    )
