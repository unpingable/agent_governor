# SPDX-License-Identifier: Apache-2.0
"""Deadlock detection — a governor primitive distinct from refusal and exhaustion.

> **Deadlock is when valid local custody decisions compose into no global transition.**

Everyone is green; the run is stuck. It is the runtime rhyme of the temporal theorem
*locally valid ⇏ trajectory valid* (`hopwise admissible ⇏ trajectory admissible`).
Three outcomes the governor must keep distinct:

    REFUSAL    — an action is invalid / unsafe / out of bounds
    EXHAUSTION — retry / budget / capacity spent
    DEADLOCK   — locally valid positions compose into no owned next transition

Division of labor (operator, 2026-06-14): **Lean** proves the classification boundary
(`valid_deferrals_can_deadlock`, `deadlock_is_not_refusal_or_exhaustion`); **this module**
detects the runtime symptom. No string-matching/retry-counters/JSON-shape in Lean; no
metaphysics in Python.

**The rule the detector itself must obey (and dogfoods):** it does NOT resolve the
deadlock by choosing the blocked doctrine. It converts *vague stuckness* into a *typed
operator gate* — a `DeadlockReceipt` with options, a PROCESS default (keep fenced
progress; don't freeze), and forbidden ratifying actions. It recommends the meta-move,
never the content. (This is exactly `feedback_ratification_vs_progress_deadlock`: an
undecided ratification must not freeze fenced progress.)

**Evidence discipline (NLAI):** structural signals — no artifact delta + repeated
semantic state across turns — are *necessary* for a deadlock verdict. Deferral phrases
("your call", "not mine to decide") are *corroborating only*; language never authorizes
the verdict on its own. The receipt is testimony (status `operator_required`), not a
consequence: halting automation is the consumer's act on the receipt, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# --- Local (per-turn) outcomes, observed --------------------------------------
LOCAL_PROGRESS = "progress"
LOCAL_REFUSE = "refuse"
LOCAL_EXHAUST = "exhaust"
LOCAL_DEFER = "defer"
LOCAL_OUTCOMES = frozenset({LOCAL_PROGRESS, LOCAL_REFUSE, LOCAL_EXHAUST, LOCAL_DEFER})

# --- Global stall verdicts ----------------------------------------------------
VERDICT_PROGRESSING = "progressing"
VERDICT_REFUSAL = "refusal"
VERDICT_EXHAUSTION = "exhaustion"
VERDICT_HELD_WITH_PLAN = "held_with_plan"
VERDICT_OPERATOR_GATE_OPEN = "operator_gate_open"
VERDICT_DEADLOCK = "deadlock"

# --- Deadlock classes ---------------------------------------------------------
DEADLOCK_CIRCULAR_CUSTODY = "circular_custody_deferral"
DEADLOCK_MUTUAL_OPERATOR_DEFERRAL = "mutual_operator_deferral"
DEADLOCK_REPEATED_UNRESOLVED = "repeated_unresolved_state"

OPERATOR = "operator"

# Process default the detector may recommend — never the blocked content.
PROCESS_DEFAULT = (
    "continue fenced progress (scratch / audit / sketch / record a provisional); "
    "do not freeze; surface the ratification as one narrow operator-present decision"
)


class MalformedTurnError(ValueError):
    """A turn observation was structurally malformed (unknown local_outcome)."""


@dataclass(frozen=True)
class DecisionPacket:
    """A minimal operator-decision packet. ``is_minimal`` is what distinguishes a healthy
    converted gate from a silent stall: a named decision, ≥2 options, and a concrete next
    action after the choice."""

    decision_name: str
    options: tuple[str, ...]
    next_action_after_choice: str
    recommended_default: Optional[str] = None
    consequences: str = ""

    def is_minimal(self) -> bool:
        return bool(
            self.decision_name
            and len(self.options) >= 2
            and self.next_action_after_choice
        )


@dataclass(frozen=True)
class TurnObservation:
    """One loop turn, as the governor observes it — not as an agent narrates it.

    ``artifact_delta`` / ``terminal`` are the structural signals (a file/commit/receipt
    landed, or a terminal state was reached). ``local_outcome`` is the observed local
    move. ``assigns_decision_to`` is who this actor says owns the next decision (custody
    handoff). ``decision_packet`` / ``next_action_scheduled`` are the two ways an owned
    next transition can legitimately exist. ``deferral_signals`` are corroborating phrases
    only. ``semantic_fingerprint`` identifies the unresolved issue, to detect repetition.
    """

    turn: int
    actor: str
    local_outcome: str
    artifact_delta: bool
    terminal: bool
    semantic_fingerprint: str
    assigns_decision_to: Optional[str] = None
    decision_packet: Optional[DecisionPacket] = None
    next_action_scheduled: Optional[str] = None
    deferral_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.local_outcome not in LOCAL_OUTCOMES:
            raise MalformedTurnError(
                f"local_outcome must be one of {sorted(LOCAL_OUTCOMES)}, "
                f"got {self.local_outcome!r}"
            )
        if not isinstance(self.deferral_signals, tuple):
            raise MalformedTurnError("deferral_signals must be a tuple")


@dataclass(frozen=True)
class DeadlockReceipt:
    """Testimony that a deadlock exists, converted into a typed operator gate. Carries
    the options + a PROCESS default + forbidden ratifying actions — never a decision on
    the blocked issue. ``status`` is always ``operator_required``."""

    loop_id: str
    detected_at_turn: int
    participants: tuple[str, ...]
    blocked_surface: str
    issue: str
    deadlock_class: str
    evidence: tuple[str, ...]
    required_operator_decision: str
    options: tuple[str, ...]
    recommended_default: Optional[str]
    allowed_next_actions: tuple[str, ...]
    forbidden_next_actions: tuple[str, ...]
    status: Literal["operator_required"] = "operator_required"


@dataclass(frozen=True)
class StallAssessment:
    """The classification result. ``receipt`` is non-None iff ``verdict`` is
    ``deadlock``."""

    verdict: str
    receipt: Optional[DeadlockReceipt] = None
    evidence: tuple[str, ...] = field(default_factory=tuple)


def _classify_deadlock(recent: tuple[TurnObservation, ...]) -> str:
    # Circular custody: actor A hands the decision to B and B hands it back to A
    # (neither owns it). Operator handoffs are excluded — those are not circular.
    edges = {
        (t.actor, t.assigns_decision_to)
        for t in recent
        if t.assigns_decision_to and t.assigns_decision_to != OPERATOR
    }
    if any((b, a) in edges for (a, b) in edges):
        return DEADLOCK_CIRCULAR_CUSTODY
    assigned = [t.assigns_decision_to for t in recent if t.assigns_decision_to]
    if assigned and all(a == OPERATOR for a in assigned):
        return DEADLOCK_MUTUAL_OPERATOR_DEFERRAL
    return DEADLOCK_REPEATED_UNRESOLVED


def assess_stall(
    turns: tuple[TurnObservation, ...] | list[TurnObservation],
    *,
    loop_id: str,
    blocked_surface: str,
    issue: str,
    window: int = 2,
    forbidden_next_actions: tuple[str, ...] = (),
) -> StallAssessment:
    """Classify the recent loop window into one of the six verdicts. Pure; no IO.

    Progress (any artifact delta / terminal in the window) beats every stall verdict.
    A single refusing or exhausting turn classifies as REFUSAL / EXHAUSTION — those are
    not deadlock. A deadlock requires the STRUCTURAL stall (≥``window`` turns, all
    ``defer``, no delta, no terminal) PLUS a repeated semantic fingerprint, AND the
    absence of any owned next transition (no scheduled next action, no minimal decision
    packet). When those hold, a ``DeadlockReceipt`` is synthesized — a typed operator
    gate, not a resolution.
    """
    turns = tuple(turns)
    recent = turns[-window:] if len(turns) >= window else turns

    # Progress beats stall.
    if any(t.artifact_delta or t.terminal for t in recent):
        return StallAssessment(VERDICT_PROGRESSING)

    # Refusal / exhaustion are not deadlock.
    if any(t.local_outcome == LOCAL_REFUSE for t in recent):
        return StallAssessment(VERDICT_REFUSAL)
    if any(t.local_outcome == LOCAL_EXHAUST for t in recent):
        return StallAssessment(VERDICT_EXHAUSTION)

    # Structural-stall necessary condition: enough turns, all deferring, no delta.
    if len(recent) < window or not all(
        t.local_outcome == LOCAL_DEFER for t in recent
    ):
        return StallAssessment(VERDICT_PROGRESSING)

    # An owned next transition exists → not stuck.
    if any(t.next_action_scheduled for t in recent):
        return StallAssessment(VERDICT_HELD_WITH_PLAN)
    if any(t.decision_packet and t.decision_packet.is_minimal() for t in recent):
        # The agents already converted to a typed gate themselves: operator_required,
        # but NOT a silent stall — nothing for the detector to synthesize.
        return StallAssessment(VERDICT_OPERATOR_GATE_OPEN)

    # New evidence each turn (changing fingerprint) → working, not stuck (yet).
    if len({t.semantic_fingerprint for t in recent}) != 1:
        return StallAssessment(VERDICT_PROGRESSING)

    # --- DEADLOCK: locally valid deferrals, repeated state, no owned transition ---
    deadlock_class = _classify_deadlock(recent)
    participants = tuple(sorted({t.actor for t in recent}))
    evidence = (
        f"window turns {recent[0].turn}-{recent[-1].turn}: all local_outcome=defer, "
        f"no artifact_delta, no terminal",
        f"semantic_fingerprint repeated: {recent[-1].semantic_fingerprint!r}",
        "custody handoffs: "
        + "; ".join(
            f"{t.actor}->{t.assigns_decision_to}"
            for t in recent
            if t.assigns_decision_to
        ),
        "no minimal decision packet emitted",
    )
    receipt = DeadlockReceipt(
        loop_id=loop_id,
        detected_at_turn=recent[-1].turn,
        participants=participants,
        blocked_surface=blocked_surface,
        issue=issue,
        deadlock_class=deadlock_class,
        evidence=evidence,
        required_operator_decision=(
            f"own the next transition on '{blocked_surface}': "
            f"decide or delegate the blocked issue ({issue})"
        ),
        # Options the detector may safely name without deciding the content:
        options=(
            "HOLD all work on the blocked surface",
            "CONTINUE fenced progress only (no ratifying act)",
            "OPERATOR directs the specific resolution",
        ),
        recommended_default=PROCESS_DEFAULT,  # process move, NOT the blocked content
        allowed_next_actions=(
            "scratch / aggregation",
            "audit / compile",
            "claim sketch",
            "record a provisional preference",
        ),
        forbidden_next_actions=forbidden_next_actions
        or ("any ratifying / minting / promoting / register act on the blocked surface",),
    )
    return StallAssessment(VERDICT_DEADLOCK, receipt=receipt, evidence=evidence)


def detect_deadlock(
    turns: tuple[TurnObservation, ...] | list[TurnObservation],
    *,
    loop_id: str,
    blocked_surface: str,
    issue: str,
    window: int = 2,
    forbidden_next_actions: tuple[str, ...] = (),
) -> Optional[DeadlockReceipt]:
    """Convenience: the ``DeadlockReceipt`` iff the window is a deadlock, else ``None``."""
    return assess_stall(
        turns,
        loop_id=loop_id,
        blocked_surface=blocked_surface,
        issue=issue,
        window=window,
        forbidden_next_actions=forbidden_next_actions,
    ).receipt


__all__ = [
    "LOCAL_PROGRESS",
    "LOCAL_REFUSE",
    "LOCAL_EXHAUST",
    "LOCAL_DEFER",
    "LOCAL_OUTCOMES",
    "VERDICT_PROGRESSING",
    "VERDICT_REFUSAL",
    "VERDICT_EXHAUSTION",
    "VERDICT_HELD_WITH_PLAN",
    "VERDICT_OPERATOR_GATE_OPEN",
    "VERDICT_DEADLOCK",
    "DEADLOCK_CIRCULAR_CUSTODY",
    "DEADLOCK_MUTUAL_OPERATOR_DEFERRAL",
    "DEADLOCK_REPEATED_UNRESOLVED",
    "OPERATOR",
    "PROCESS_DEFAULT",
    "MalformedTurnError",
    "DecisionPacket",
    "TurnObservation",
    "DeadlockReceipt",
    "StallAssessment",
    "assess_stall",
    "detect_deadlock",
]
