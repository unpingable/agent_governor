# SPDX-License-Identifier: Apache-2.0
"""Tests for Phase Control System — Run Phases with Budget Locks.

Layer 2.1-A. Invariant G: B_verify inaccessible until phase ≥ VERIFY.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.phase_control import (
    Phase,
    TransitionResult,
    PhaseBudget,
    PhaseUsage,
    NoveltyDebt,
    RunState,
    PhaseTransitionEvent,
    PhaseController,
    PhaseStore,
    can_advance,
    check_budget,
    check_invariant_g,
    make_phase_event,
    A_MIN,
    COVERAGE_THRESHOLD,
    DEFAULT_EXPLORE_BUDGET,
    DEFAULT_DRAFT_BUDGET,
    DEFAULT_VERIFY_BUDGET,
    ALPHA_NOVELTY,
    LAMBDA_NOVELTY,
    Q_MAX,
    REVERIFY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestPhase:
    def test_ordering(self):
        assert Phase.SPECIFY < Phase.EXPLORE < Phase.DRAFT < Phase.VERIFY < Phase.COMMIT

    def test_values(self):
        assert Phase.SPECIFY == 0
        assert Phase.COMMIT == 4

    def test_count(self):
        assert len(Phase) == 5

    def test_name(self):
        assert Phase.VERIFY.name == "VERIFY"
        assert Phase["VERIFY"] == Phase.VERIFY


class TestTransitionResult:
    def test_values(self):
        assert TransitionResult.ADVANCED.value == "advanced"
        assert TransitionResult.BLOCKED.value == "blocked"
        assert TransitionResult.ALREADY_THERE.value == "already_there"
        assert TransitionResult.INVALID.value == "invalid"


# ---------------------------------------------------------------------------
# PhaseBudget Tests
# ---------------------------------------------------------------------------

class TestPhaseBudget:
    def test_defaults(self):
        b = PhaseBudget()
        assert b.explore == DEFAULT_EXPLORE_BUDGET
        assert b.draft == DEFAULT_DRAFT_BUDGET
        assert b.verify == DEFAULT_VERIFY_BUDGET

    def test_total(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        assert b.total == 18

    def test_available_explore(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        assert b.available(Phase.EXPLORE) == 10

    def test_available_draft(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        assert b.available(Phase.DRAFT) == 5

    def test_available_verify(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        assert b.available(Phase.VERIFY) == 3

    def test_available_specify(self):
        b = PhaseBudget()
        assert b.available(Phase.SPECIFY) == 0

    def test_available_commit(self):
        b = PhaseBudget()
        assert b.available(Phase.COMMIT) == 0

    def test_to_dict(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        d = b.to_dict()
        assert d == {"explore": 10, "draft": 5, "verify": 3}

    def test_roundtrip(self):
        b = PhaseBudget(explore=12, draft=8, verify=6)
        restored = PhaseBudget.from_dict(b.to_dict())
        assert restored.explore == 12
        assert restored.draft == 8
        assert restored.verify == 6


# ---------------------------------------------------------------------------
# PhaseUsage Tests
# ---------------------------------------------------------------------------

class TestPhaseUsage:
    def test_initial(self):
        u = PhaseUsage()
        assert u.used(Phase.EXPLORE) == 0
        assert u.used(Phase.DRAFT) == 0
        assert u.used(Phase.VERIFY) == 0

    def test_consume(self):
        u = PhaseUsage()
        u.consume(Phase.EXPLORE, 3)
        assert u.explore_used == 3
        u.consume(Phase.DRAFT, 2)
        assert u.draft_used == 2

    def test_remaining(self):
        b = PhaseBudget(explore=10, draft=5, verify=3)
        u = PhaseUsage(explore_used=4)
        assert u.remaining(b, Phase.EXPLORE) == 6
        assert u.remaining(b, Phase.DRAFT) == 5

    def test_remaining_exhausted(self):
        b = PhaseBudget(explore=5, draft=3, verify=2)
        u = PhaseUsage(explore_used=7)  # Over budget
        assert u.remaining(b, Phase.EXPLORE) == 0

    def test_roundtrip(self):
        u = PhaseUsage(explore_used=5, draft_used=3, verify_used=1)
        restored = PhaseUsage.from_dict(u.to_dict())
        assert restored.explore_used == 5
        assert restored.draft_used == 3
        assert restored.verify_used == 1


# ---------------------------------------------------------------------------
# NoveltyDebt Tests
# ---------------------------------------------------------------------------

class TestNoveltyDebt:
    def test_initial(self):
        nd = NoveltyDebt()
        assert nd.total == 0.0
        assert nd.confidence_cap == Q_MAX
        assert not nd.needs_reverification

    def test_record_change(self):
        nd = NoveltyDebt()
        nd.record_change(2.0, "added new endpoint")
        assert nd.total == pytest.approx(LAMBDA_NOVELTY * 2.0)
        assert len(nd.changes) == 1

    def test_confidence_cap_decreases(self):
        nd = NoveltyDebt()
        nd.record_change(5.0)
        expected_cap = Q_MAX - ALPHA_NOVELTY * (LAMBDA_NOVELTY * 5.0)
        assert nd.confidence_cap == pytest.approx(expected_cap)

    def test_confidence_cap_floors_at_zero(self):
        nd = NoveltyDebt()
        nd.record_change(100.0)  # Massive change
        assert nd.confidence_cap >= 0.0

    def test_needs_reverification(self):
        nd = NoveltyDebt()
        nd.record_change(float(REVERIFY_THRESHOLD) + 1.0)
        assert nd.needs_reverification

    def test_multiple_changes_accumulate(self):
        nd = NoveltyDebt()
        nd.record_change(1.0)
        nd.record_change(2.0)
        assert nd.total == pytest.approx(LAMBDA_NOVELTY * 3.0)
        assert len(nd.changes) == 2

    def test_roundtrip(self):
        nd = NoveltyDebt()
        nd.record_change(2.5, "test change")
        restored = NoveltyDebt.from_dict(nd.to_dict())
        assert restored.total == pytest.approx(nd.total)
        assert len(restored.changes) == 1


# ---------------------------------------------------------------------------
# RunState Tests
# ---------------------------------------------------------------------------

class TestRunState:
    def test_defaults(self):
        s = RunState()
        assert s.admissibility == 0.0
        assert s.candidates_generated == 0
        assert not s.artifact_exists
        assert s.coverage == 0.0

    def test_roundtrip(self):
        s = RunState(admissibility=0.7, candidates_generated=3,
                     artifact_exists=True, coverage=0.85)
        restored = RunState.from_dict(s.to_dict())
        assert restored.admissibility == 0.7
        assert restored.artifact_exists is True


# ---------------------------------------------------------------------------
# can_advance Tests
# ---------------------------------------------------------------------------

class TestCanAdvance:
    def test_specify_to_explore_allowed(self):
        s = RunState(admissibility=0.5)
        allowed, reason = can_advance(Phase.SPECIFY, s)
        assert allowed

    def test_specify_to_explore_blocked(self):
        s = RunState(admissibility=0.2)
        allowed, reason = can_advance(Phase.SPECIFY, s)
        assert not allowed
        assert str(A_MIN) in reason

    def test_explore_to_draft_allowed(self):
        s = RunState(candidates_generated=2)
        allowed, _ = can_advance(Phase.EXPLORE, s)
        assert allowed

    def test_explore_to_draft_blocked(self):
        s = RunState(candidates_generated=0)
        allowed, reason = can_advance(Phase.EXPLORE, s)
        assert not allowed
        assert "candidates" in reason

    def test_draft_to_verify_allowed(self):
        s = RunState(artifact_exists=True)
        allowed, _ = can_advance(Phase.DRAFT, s)
        assert allowed

    def test_draft_to_verify_blocked(self):
        s = RunState(artifact_exists=False)
        allowed, _ = can_advance(Phase.DRAFT, s)
        assert not allowed

    def test_verify_to_commit_allowed(self):
        s = RunState(coverage=0.9)
        allowed, _ = can_advance(Phase.VERIFY, s)
        assert allowed

    def test_verify_to_commit_blocked(self):
        s = RunState(coverage=0.5)
        allowed, _ = can_advance(Phase.VERIFY, s)
        assert not allowed

    def test_commit_always_true(self):
        allowed, _ = can_advance(Phase.COMMIT, RunState())
        assert allowed


# ---------------------------------------------------------------------------
# check_budget Tests
# ---------------------------------------------------------------------------

class TestCheckBudget:
    def test_has_budget(self):
        b = PhaseBudget(explore=10)
        u = PhaseUsage(explore_used=5)
        assert check_budget(Phase.EXPLORE, b, u)

    def test_no_budget(self):
        b = PhaseBudget(explore=5)
        u = PhaseUsage(explore_used=5)
        assert not check_budget(Phase.EXPLORE, b, u)


# ---------------------------------------------------------------------------
# Invariant G Tests
# ---------------------------------------------------------------------------

class TestInvariantG:
    def test_verify_locked_in_specify(self):
        b = PhaseBudget(verify=10)
        # In SPECIFY phase, verify budget should not be accessible via available()
        assert b.available(Phase.SPECIFY) == 0

    def test_verify_locked_in_explore(self):
        b = PhaseBudget(verify=10)
        assert b.available(Phase.EXPLORE) != b.verify or b.verify == 0

    def test_verify_accessible_in_verify(self):
        b = PhaseBudget(verify=10)
        assert b.available(Phase.VERIFY) == 10

    def test_check_invariant_g_specify(self):
        b = PhaseBudget(verify=10)
        assert check_invariant_g(Phase.SPECIFY, b)

    def test_check_invariant_g_verify(self):
        b = PhaseBudget(verify=10)
        assert check_invariant_g(Phase.VERIFY, b)


# ---------------------------------------------------------------------------
# PhaseTransitionEvent Tests
# ---------------------------------------------------------------------------

class TestPhaseTransitionEvent:
    def test_create(self):
        e = PhaseTransitionEvent(
            from_phase=Phase.SPECIFY, to_phase=Phase.EXPLORE,
            result=TransitionResult.ADVANCED, reason="ok",
        )
        assert e.ts != ""

    def test_to_dict(self):
        e = PhaseTransitionEvent(
            from_phase=Phase.EXPLORE, to_phase=Phase.DRAFT,
            result=TransitionResult.BLOCKED, reason="no candidates",
        )
        d = e.to_dict()
        assert d["from_phase"] == "EXPLORE"
        assert d["to_phase"] == "DRAFT"
        assert d["result"] == "blocked"

    def test_roundtrip(self):
        e = PhaseTransitionEvent(
            from_phase=Phase.DRAFT, to_phase=Phase.VERIFY,
            result=TransitionResult.ADVANCED, reason="artifact ready",
            budget_remaining={"explore": 5, "draft": 0, "verify": 10},
        )
        restored = PhaseTransitionEvent.from_dict(e.to_dict())
        assert restored.from_phase == Phase.DRAFT
        assert restored.result == TransitionResult.ADVANCED


# ---------------------------------------------------------------------------
# PhaseController Tests
# ---------------------------------------------------------------------------

class TestPhaseController:
    def test_create(self):
        c = PhaseController(run_id="run1")
        assert c.phase == Phase.SPECIFY
        assert c.budget.total > 0

    def test_advance_from_specify(self):
        c = PhaseController(run_id="run1")
        c.state.admissibility = 0.6
        evt = c.advance()
        assert evt.result == TransitionResult.ADVANCED
        assert c.phase == Phase.EXPLORE

    def test_advance_blocked(self):
        c = PhaseController(run_id="run1")
        c.state.admissibility = 0.1
        evt = c.advance()
        assert evt.result == TransitionResult.BLOCKED
        assert c.phase == Phase.SPECIFY  # Unchanged

    def test_advance_already_at_commit(self):
        c = PhaseController(run_id="run1", phase=Phase.COMMIT)
        evt = c.advance()
        assert evt.result == TransitionResult.ALREADY_THERE

    def test_full_lifecycle(self):
        c = PhaseController(run_id="run1")
        # SPECIFY → EXPLORE
        c.state.admissibility = 0.5
        assert c.advance().result == TransitionResult.ADVANCED
        assert c.phase == Phase.EXPLORE

        # EXPLORE → DRAFT
        c.state.candidates_generated = 1
        assert c.advance().result == TransitionResult.ADVANCED
        assert c.phase == Phase.DRAFT

        # DRAFT → VERIFY
        c.state.artifact_exists = True
        assert c.advance().result == TransitionResult.ADVANCED
        assert c.phase == Phase.VERIFY

        # VERIFY → COMMIT
        c.state.coverage = 0.9
        assert c.advance().result == TransitionResult.ADVANCED
        assert c.phase == Phase.COMMIT

    def test_consume_action(self):
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE)
        assert c.consume_action()
        assert c.usage.explore_used == 1

    def test_consume_action_exhausted(self):
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE,
                            budget=PhaseBudget(explore=1))
        assert c.consume_action()
        assert not c.consume_action()  # Budget exhausted

    def test_force_advance(self):
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE)
        evt = c.force_advance("budget exhausted")
        assert evt.result == TransitionResult.ADVANCED
        assert c.phase == Phase.DRAFT
        assert "forced" in evt.reason

    def test_force_advance_from_commit(self):
        c = PhaseController(run_id="run1", phase=Phase.COMMIT)
        evt = c.force_advance()
        assert evt.result == TransitionResult.ALREADY_THERE

    def test_record_novelty_before_verify(self):
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE)
        c.record_novelty(5.0)
        assert c.novelty.total == 0.0  # Not in VERIFY+ yet

    def test_record_novelty_in_verify(self):
        c = PhaseController(run_id="run1", phase=Phase.VERIFY)
        c.record_novelty(2.0, "added endpoint")
        assert c.novelty.total > 0

    def test_confidence_cap(self):
        c = PhaseController(run_id="run1", phase=Phase.VERIFY)
        assert c.confidence_cap == Q_MAX
        c.record_novelty(5.0)
        assert c.confidence_cap < Q_MAX

    def test_budget_remaining(self):
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE)
        c.consume_action(3)
        remaining = c.budget_remaining
        assert remaining["explore"] == DEFAULT_EXPLORE_BUDGET - 3
        assert remaining["draft"] == DEFAULT_DRAFT_BUDGET
        assert remaining["verify"] == DEFAULT_VERIFY_BUDGET

    def test_history_tracking(self):
        c = PhaseController(run_id="run1")
        c.state.admissibility = 0.5
        c.advance()
        c.state.candidates_generated = 1
        c.advance()
        assert len(c.history) == 2

    def test_to_dict(self):
        c = PhaseController(run_id="run1")
        d = c.to_dict()
        assert d["run_id"] == "run1"
        assert d["phase"] == "SPECIFY"
        assert "budget" in d
        assert "usage" in d
        assert "confidence_cap" in d

    def test_roundtrip(self):
        c = PhaseController(run_id="run1", phase=Phase.DRAFT)
        c.usage.consume(Phase.EXPLORE, 5)
        c.state.artifact_exists = True
        restored = PhaseController.from_dict(c.to_dict())
        assert restored.run_id == "run1"
        assert restored.phase == Phase.DRAFT
        assert restored.usage.explore_used == 5
        assert restored.state.artifact_exists is True


# ---------------------------------------------------------------------------
# PhaseStore Tests
# ---------------------------------------------------------------------------

class TestPhaseStore:
    def test_create(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        assert store.phase_dir == tmp_path / ".governor" / "phases"

    def test_save_load(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        c = PhaseController(run_id="run1", phase=Phase.EXPLORE)
        store.save(c)
        loaded = store.load("run1")
        assert loaded is not None
        assert loaded.phase == Phase.EXPLORE

    def test_load_missing(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        assert store.load("nonexistent") is None

    def test_list_runs(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        store.save(PhaseController(run_id="a"))
        store.save(PhaseController(run_id="b"))
        runs = store.list_runs()
        assert "a" in runs
        assert "b" in runs

    def test_list_runs_empty(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        assert store.list_runs() == []

    def test_corrupt_file(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")
        store._ensure_dirs()
        (store.phase_dir / "bad.json").write_text("not valid json")
        assert store.load("bad") is None


# ---------------------------------------------------------------------------
# Telemetry Event Tests
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        evt = make_phase_event("phase_transition", "run1",
                               {"from": "SPECIFY", "to": "EXPLORE"})
        assert evt["type"] == "phase_control"
        assert evt["action"] == "phase_transition"

    def test_minimal(self):
        evt = make_phase_event("check")
        assert evt["run_id"] == ""
        assert evt["details"] == {}


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_budget_schema(self):
        b = PhaseBudget()
        d = b.to_dict()
        assert set(d.keys()) == {"explore", "draft", "verify"}

    def test_usage_schema(self):
        u = PhaseUsage()
        d = u.to_dict()
        assert set(d.keys()) == {"explore_used", "draft_used", "verify_used"}

    def test_novelty_schema(self):
        nd = NoveltyDebt()
        d = nd.to_dict()
        assert set(d.keys()) == {"total", "confidence_cap", "needs_reverification", "changes"}

    def test_run_state_schema(self):
        s = RunState()
        d = s.to_dict()
        assert set(d.keys()) == {"admissibility", "candidates_generated",
                                  "artifact_exists", "coverage"}

    def test_transition_event_schema(self):
        e = PhaseTransitionEvent(
            from_phase=Phase.SPECIFY, to_phase=Phase.EXPLORE,
            result=TransitionResult.ADVANCED, reason="ok",
        )
        d = e.to_dict()
        assert set(d.keys()) == {"from_phase", "to_phase", "result", "reason",
                                  "budget_remaining", "ts"}

    def test_controller_schema(self):
        c = PhaseController(run_id="test")
        d = c.to_dict()
        required = {"run_id", "phase", "budget", "usage", "state", "novelty",
                    "history", "confidence_cap", "budget_remaining"}
        assert required.issubset(set(d.keys()))

    def test_event_schema(self):
        evt = make_phase_event("test")
        assert set(evt.keys()) == {"type", "action", "run_id", "details", "ts"}


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle_with_persistence(self, tmp_path):
        store = PhaseStore(governor_dir=tmp_path / ".governor")

        c = PhaseController(run_id="lifecycle")

        # SPECIFY: set admissibility and advance
        c.state.admissibility = 0.6
        evt = c.advance()
        assert evt.result == TransitionResult.ADVANCED
        assert c.phase == Phase.EXPLORE

        # EXPLORE: consume actions
        for _ in range(3):
            c.consume_action()
        c.state.candidates_generated = 2
        c.advance()
        assert c.phase == Phase.DRAFT

        # DRAFT: produce artifact
        c.consume_action(2)
        c.state.artifact_exists = True
        c.advance()
        assert c.phase == Phase.VERIFY

        # VERIFY: record novelty, then reach coverage
        c.record_novelty(2.0, "added validation")
        assert c.confidence_cap < Q_MAX

        c.state.coverage = 0.85
        c.advance()
        assert c.phase == Phase.COMMIT

        # Persist
        store.save(c)
        loaded = store.load("lifecycle")
        assert loaded is not None
        assert loaded.phase == Phase.COMMIT
        assert loaded.novelty.total > 0
        assert len(loaded.history) == 4

    def test_budget_exhaustion_forces_transition(self):
        c = PhaseController(
            run_id="budget_test",
            phase=Phase.EXPLORE,
            budget=PhaseBudget(explore=3, draft=5, verify=5),
        )
        for _ in range(3):
            c.consume_action()
        assert not c.consume_action()  # Exhausted
        evt = c.force_advance("budget exhausted")
        assert c.phase == Phase.DRAFT


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_budget(self):
        b = PhaseBudget(explore=0, draft=0, verify=0)
        assert b.total == 0
        assert b.available(Phase.EXPLORE) == 0

    def test_phase_int_comparison(self):
        assert Phase.SPECIFY < Phase.COMMIT
        assert Phase.VERIFY >= Phase.DRAFT
        assert Phase.COMMIT - Phase.SPECIFY == 4

    def test_store_default_dir(self):
        store = PhaseStore()
        assert store.governor_dir == Path(".governor")

    def test_novelty_debt_no_changes(self):
        nd = NoveltyDebt()
        assert nd.to_dict()["changes"] == []
        assert nd.confidence_cap == Q_MAX
