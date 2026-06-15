# SPDX-License-Identifier: Apache-2.0
"""Deadlock detector tests — the trichotomy boundary + the operator's five.

Deadlock is locally-valid deferrals composing into no owned next transition. It is NOT
refusal, NOT exhaustion, NOT a valid held plan, NOT an already-open operator gate. The
structural stall (no artifact delta + repeated state) is necessary; deferral language
alone never authorizes the verdict (NLAI).
"""

from __future__ import annotations

import pytest

from governor.deadlock import (
    DEADLOCK_CIRCULAR_CUSTODY,
    DEADLOCK_MUTUAL_OPERATOR_DEFERRAL,
    LOCAL_DEFER,
    LOCAL_EXHAUST,
    LOCAL_PROGRESS,
    LOCAL_REFUSE,
    PROCESS_DEFAULT,
    VERDICT_DEADLOCK,
    VERDICT_EXHAUSTION,
    VERDICT_HELD_WITH_PLAN,
    VERDICT_OPERATOR_GATE_OPEN,
    VERDICT_PROGRESSING,
    VERDICT_REFUSAL,
    DecisionPacket,
    MalformedTurnError,
    TurnObservation,
    assess_stall,
    detect_deadlock,
)

FP = "observer-noun-and-promotion"  # one unresolved issue, repeated


def _defer(turn, actor, *, to=None, fp=FP, packet=None, next_action=None):
    return TurnObservation(
        turn=turn,
        actor=actor,
        local_outcome=LOCAL_DEFER,
        artifact_delta=False,
        terminal=False,
        semantic_fingerprint=fp,
        assigns_decision_to=to,
        decision_packet=packet,
        next_action_scheduled=next_action,
        deferral_signals=("your call", "not mine to decide"),
    )


def _assess(turns):
    return assess_stall(
        turns,
        loop_id="loop-1",
        blocked_surface="shared observer module noun",
        issue="neutral noun / promotion scope",
    )


# --- #1: two agents mutually defer -> deadlock receipt -----------------------


def test_circular_custody_deferral_is_deadlock():
    turns = [
        _defer(1, "ag_claude", to="lean_claude"),
        _defer(2, "lean_claude", to="ag_claude"),
    ]
    a = _assess(turns)
    assert a.verdict == VERDICT_DEADLOCK
    assert a.receipt is not None
    assert a.receipt.deadlock_class == DEADLOCK_CIRCULAR_CUSTODY
    assert a.receipt.status == "operator_required"
    assert set(a.receipt.participants) == {"ag_claude", "lean_claude"}


def test_mutual_operator_deferral_is_deadlock():
    turns = [_defer(1, "ag_claude", to="operator"), _defer(2, "lean_claude", to="operator")]
    a = _assess(turns)
    assert a.verdict == VERDICT_DEADLOCK
    assert a.receipt.deadlock_class == DEADLOCK_MUTUAL_OPERATOR_DEFERRAL


# --- #2: valid HOLD with explicit next action -> NOT deadlock ----------------


def test_hold_with_explicit_next_action_is_not_deadlock():
    turns = [
        _defer(1, "ag_claude", to="operator"),
        _defer(2, "ag_claude", to="operator", next_action="re-check after P4.0b ratified"),
    ]
    a = _assess(turns)
    assert a.verdict == VERDICT_HELD_WITH_PLAN
    assert a.receipt is None


# --- #3: refusal from one agent -> refusal, not deadlock ---------------------


def test_refusal_is_not_deadlock():
    turns = [
        _defer(1, "ag_claude", to="operator"),
        TurnObservation(
            turn=2,
            actor="lean_claude",
            local_outcome=LOCAL_REFUSE,
            artifact_delta=False,
            terminal=False,
            semantic_fingerprint=FP,
        ),
    ]
    a = _assess(turns)
    assert a.verdict == VERDICT_REFUSAL
    assert a.receipt is None


# --- #4: retry exhaustion -> exhaustion, not deadlock ------------------------


def test_exhaustion_is_not_deadlock():
    turns = [
        _defer(1, "ag_claude", to="operator"),
        TurnObservation(
            turn=2,
            actor="ag_claude",
            local_outcome=LOCAL_EXHAUST,
            artifact_delta=False,
            terminal=False,
            semantic_fingerprint=FP,
        ),
    ]
    a = _assess(turns)
    assert a.verdict == VERDICT_EXHAUSTION
    assert a.receipt is None


# --- #5: decision packet emitted -> operator_gate_open, not silent stall -----


def test_emitted_decision_packet_is_operator_gate_open_not_deadlock():
    packet = DecisionPacket(
        decision_name="observer noun",
        options=("VerdictFor", "AssignsVerdict"),
        next_action_after_choice="mint module under chosen noun",
        recommended_default="VerdictFor",
    )
    turns = [
        _defer(1, "ag_claude", to="operator"),
        _defer(2, "lean_claude", to="operator", packet=packet),
    ]
    a = _assess(turns)
    assert a.verdict == VERDICT_OPERATOR_GATE_OPEN
    assert a.receipt is None


# --- Progress / NLAI guards --------------------------------------------------


def test_artifact_delta_beats_stall():
    turns = [
        _defer(1, "ag_claude", to="lean_claude"),
        TurnObservation(
            turn=2,
            actor="lean_claude",
            local_outcome=LOCAL_PROGRESS,
            artifact_delta=True,
            terminal=False,
            semantic_fingerprint=FP,
        ),
    ]
    assert _assess(turns).verdict == VERDICT_PROGRESSING


def test_deferral_language_without_structural_stall_is_not_deadlock():
    """NLAI: deferral phrases alone do not make a deadlock. With an artifact delta the
    turn is progress regardless of how much it says 'your call'."""
    turns = [
        _defer(1, "ag_claude", to="lean_claude"),
        TurnObservation(
            turn=2,
            actor="lean_claude",
            local_outcome=LOCAL_DEFER,
            artifact_delta=True,  # something landed despite the deferral talk
            terminal=False,
            semantic_fingerprint=FP,
            deferral_signals=("your call", "not mine to decide", "good place to leave"),
        ),
    ]
    assert _assess(turns).verdict == VERDICT_PROGRESSING


def test_changing_fingerprint_is_progress_not_deadlock():
    """New evidence each turn (different fingerprint) is work, not a stuck loop."""
    turns = [
        _defer(1, "ag_claude", to="operator", fp="issue-A"),
        _defer(2, "lean_claude", to="operator", fp="issue-B"),
    ]
    assert _assess(turns).verdict == VERDICT_PROGRESSING


def test_single_defer_turn_is_not_yet_deadlock():
    assert _assess([_defer(1, "ag_claude", to="operator")]).verdict == VERDICT_PROGRESSING


# --- The detector does not resolve the blocked issue -------------------------


def test_receipt_recommends_process_default_not_content():
    receipt = detect_deadlock(
        [_defer(1, "ag_claude", to="lean_claude"), _defer(2, "lean_claude", to="ag_claude")],
        loop_id="loop-1",
        blocked_surface="observer noun",
        issue="neutral noun choice",
    )
    assert receipt is not None
    # The default is the PROCESS move (don't freeze), never a pick of the blocked content.
    assert receipt.recommended_default == PROCESS_DEFAULT
    assert "VerdictFor" not in receipt.recommended_default
    assert any("fenced progress" in o.lower() for o in receipt.options)
    assert receipt.forbidden_next_actions  # ratifying acts are fenced off


def test_custom_forbidden_actions_passthrough():
    receipt = detect_deadlock(
        [_defer(1, "a", to="b"), _defer(2, "b", to="a")],
        loop_id="loop-1",
        blocked_surface="x",
        issue="y",
        forbidden_next_actions=("mint module", "CLAIM-REGISTER promotion"),
    )
    assert receipt.forbidden_next_actions == ("mint module", "CLAIM-REGISTER promotion")


# --- Construction discipline -------------------------------------------------


def test_malformed_local_outcome_refused():
    with pytest.raises(MalformedTurnError):
        TurnObservation(
            turn=1,
            actor="a",
            local_outcome="vibes",
            artifact_delta=False,
            terminal=False,
            semantic_fingerprint=FP,
        )
