# SPDX-License-Identifier: Apache-2.0
"""
Tests for Phase A1: Execution state and budgets.
"""

import json
import pytest
from pathlib import Path

from governor.execution import (
    StopReason,
    ExecutionStatus,
    ExecutionBudget,
    ExecutionUsage,
    ExecutionState,
    SessionManager,
)


# =============================================================================
# ExecutionBudget
# =============================================================================


class TestExecutionBudget:
    def test_default_unlimited(self):
        b = ExecutionBudget()
        assert b.max_tokens is None
        assert b.max_iterations is None
        assert b.max_time_seconds is None
        assert b.max_cost_usd is None

    def test_not_exhausted_when_unlimited(self):
        b = ExecutionBudget()
        used = ExecutionUsage(tokens=999999, iterations=999999)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is False

    def test_token_exhaustion(self):
        b = ExecutionBudget(max_tokens=1000)
        used = ExecutionUsage(tokens=1000)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is True
        assert "token" in msg.lower()

    def test_token_not_exhausted(self):
        b = ExecutionBudget(max_tokens=1000)
        used = ExecutionUsage(tokens=500)
        exhausted, _ = b.is_exhausted(used)
        assert exhausted is False

    def test_iteration_exhaustion(self):
        b = ExecutionBudget(max_iterations=50)
        used = ExecutionUsage(iterations=50)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is True
        assert "iteration" in msg.lower()

    def test_time_exhaustion(self):
        b = ExecutionBudget(max_time_seconds=3600)
        used = ExecutionUsage(elapsed_seconds=3600)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is True
        assert "time" in msg.lower()

    def test_cost_exhaustion(self):
        b = ExecutionBudget(max_cost_usd=5.0)
        used = ExecutionUsage(cost_usd=5.01)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is True
        assert "cost" in msg.lower()

    def test_first_limit_wins(self):
        b = ExecutionBudget(max_tokens=100, max_iterations=10)
        used = ExecutionUsage(tokens=100, iterations=5)
        exhausted, msg = b.is_exhausted(used)
        assert exhausted is True
        assert "token" in msg.lower()

    def test_remaining(self):
        b = ExecutionBudget(max_tokens=1000, max_iterations=50)
        used = ExecutionUsage(tokens=300, iterations=20)
        remaining = b.remaining(used)
        assert remaining["tokens"] == 700
        assert remaining["iterations"] == 30

    def test_remaining_floors_at_zero(self):
        b = ExecutionBudget(max_tokens=100)
        used = ExecutionUsage(tokens=200)
        remaining = b.remaining(used)
        assert remaining["tokens"] == 0

    def test_to_dict(self):
        b = ExecutionBudget(max_tokens=1000, max_cost_usd=5.0)
        d = b.to_dict()
        assert d["max_tokens"] == 1000
        assert d["max_cost_usd"] == 5.0
        assert d["max_iterations"] is None

    def test_from_dict(self):
        d = {"max_tokens": 2000, "max_iterations": 100}
        b = ExecutionBudget.from_dict(d)
        assert b.max_tokens == 2000
        assert b.max_iterations == 100
        assert b.max_cost_usd is None

    def test_from_spec_string(self):
        b = ExecutionBudget.from_spec("tokens=100000,iterations=50,time=1800,cost=5.00")
        assert b.max_tokens == 100000
        assert b.max_iterations == 50
        assert b.max_time_seconds == 1800
        assert b.max_cost_usd == 5.0

    def test_from_spec_partial(self):
        b = ExecutionBudget.from_spec("tokens=5000")
        assert b.max_tokens == 5000
        assert b.max_iterations is None

    def test_from_spec_empty(self):
        b = ExecutionBudget.from_spec("")
        assert b.max_tokens is None


# =============================================================================
# ExecutionUsage
# =============================================================================


class TestExecutionUsage:
    def test_default_zeros(self):
        u = ExecutionUsage()
        assert u.tokens == 0
        assert u.iterations == 0
        assert u.elapsed_seconds == 0.0
        assert u.cost_usd == 0.0

    def test_add_iteration(self):
        u = ExecutionUsage()
        u.add_iteration(tokens=100, elapsed_seconds=1.5, cost_usd=0.01)
        assert u.tokens == 100
        assert u.iterations == 1
        assert u.elapsed_seconds == 1.5
        assert u.cost_usd == 0.01

    def test_cumulative(self):
        u = ExecutionUsage()
        u.add_iteration(tokens=100)
        u.add_iteration(tokens=200)
        u.add_iteration(tokens=150)
        assert u.tokens == 450
        assert u.iterations == 3

    def test_to_dict(self):
        u = ExecutionUsage(tokens=500, iterations=10)
        d = u.to_dict()
        assert d["tokens"] == 500
        assert d["iterations"] == 10

    def test_from_dict(self):
        d = {"tokens": 1000, "iterations": 5, "cost_usd": 0.50}
        u = ExecutionUsage.from_dict(d)
        assert u.tokens == 1000
        assert u.iterations == 5
        assert u.cost_usd == 0.50


# =============================================================================
# ExecutionState
# =============================================================================


class TestExecutionState:
    def test_default_state(self):
        s = ExecutionState(task="build the thing")
        assert s.task == "build the thing"
        assert s.status == ExecutionStatus.RUNNING
        assert s.stop_reason is None
        assert s.is_active is True

    def test_stop(self):
        s = ExecutionState(task="test")
        s.stop(StopReason.BUDGET_EXHAUSTED)
        assert s.status == ExecutionStatus.STOPPED
        assert s.stop_reason == StopReason.BUDGET_EXHAUSTED
        assert s.is_active is False

    def test_complete(self):
        s = ExecutionState(task="test")
        s.complete()
        assert s.status == ExecutionStatus.COMPLETED
        assert s.stop_reason == StopReason.AGENT_COMPLETION
        assert s.is_active is False

    def test_pause_resume(self):
        s = ExecutionState(task="test")
        s.pause()
        assert s.status == ExecutionStatus.PAUSED
        assert s.is_active is True

        s.resume()
        assert s.status == ExecutionStatus.RUNNING

    def test_resume_only_from_paused(self):
        s = ExecutionState(task="test")
        s.stop(StopReason.HUMAN_STOP)
        s.resume()  # Should not change from stopped
        assert s.status == ExecutionStatus.STOPPED

    def test_record_violation(self):
        s = ExecutionState(task="test")
        s.record_violation("test_inv", "Tests failed", returncode=1)
        assert len(s.violations) == 1
        assert s.violations[0]["invariant_id"] == "test_inv"
        assert s.violations[0]["returncode"] == 1
        assert "timestamp" in s.violations[0]

    def test_to_dict(self):
        s = ExecutionState(task="build", spine_id="s1")
        d = s.to_dict()
        assert d["task"] == "build"
        assert d["spine_id"] == "s1"
        assert d["status"] == "running"
        assert "budget" in d
        assert "used" in d

    def test_from_dict(self):
        d = {
            "session_id": "abc123",
            "task": "loaded",
            "spine_id": "s1",
            "status": "stopped",
            "stop_reason": "budget_exhausted",
            "budget": {"max_tokens": 1000},
            "used": {"tokens": 1000, "iterations": 5},
        }
        s = ExecutionState.from_dict(d)
        assert s.session_id == "abc123"
        assert s.task == "loaded"
        assert s.status == ExecutionStatus.STOPPED
        assert s.stop_reason == StopReason.BUDGET_EXHAUSTED
        assert s.budget.max_tokens == 1000
        assert s.used.tokens == 1000

    def test_roundtrip(self):
        s = ExecutionState(
            task="roundtrip",
            spine_id="s1",
            invariant_ids=["tests_must_pass", "no_secrets"],
            budget=ExecutionBudget(max_tokens=5000, max_iterations=100),
        )
        s.used.add_iteration(tokens=500, cost_usd=0.05)
        s.record_violation("test", "failed")

        s2 = ExecutionState.from_dict(s.to_dict())
        assert s2.task == "roundtrip"
        assert s2.spine_id == "s1"
        assert len(s2.invariant_ids) == 2
        assert s2.budget.max_tokens == 5000
        assert s2.used.tokens == 500
        assert len(s2.violations) == 1

    def test_checkpoint_and_load(self, tmp_path):
        s = ExecutionState(task="checkpoint_test")
        s.used.add_iteration(tokens=100)
        path = tmp_path / "session.json"
        s.checkpoint(path)
        assert path.exists()
        assert s.last_checkpoint is not None

        loaded = ExecutionState.load(path)
        assert loaded.task == "checkpoint_test"
        assert loaded.used.tokens == 100

    def test_session_id_auto_generated(self):
        s1 = ExecutionState(task="a")
        s2 = ExecutionState(task="b")
        assert s1.session_id != s2.session_id
        assert len(s1.session_id) == 12


# =============================================================================
# StopReason / ExecutionStatus
# =============================================================================


class TestEnums:
    def test_stop_reasons(self):
        assert StopReason.AGENT_COMPLETION == "agent_completion"
        assert StopReason.BUDGET_EXHAUSTED == "budget_exhausted"
        assert StopReason.CONSTRAINT_VIOLATION == "constraint_violation"
        assert StopReason.HUMAN_STOP == "human_stop"
        assert StopReason.ERROR == "error"

    def test_execution_statuses(self):
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.PAUSED == "paused"
        assert ExecutionStatus.STOPPED == "stopped"
        assert ExecutionStatus.COMPLETED == "completed"


# =============================================================================
# SessionManager
# =============================================================================


class TestSessionManager:
    def test_no_sessions_initially(self, tmp_path):
        manager = SessionManager(tmp_path)
        assert manager.list_sessions() == []

    def test_create_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        state = manager.create(
            task="build feature",
            spine_id="s1",
            budget=ExecutionBudget(max_iterations=50),
        )
        assert state.task == "build feature"
        assert state.spine_id == "s1"
        assert state.budget.max_iterations == 50
        assert state.status == ExecutionStatus.RUNNING

    def test_get_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        created = manager.create(task="test")
        loaded = manager.get(created.session_id)
        assert loaded is not None
        assert loaded.session_id == created.session_id
        assert loaded.task == "test"

    def test_get_nonexistent(self, tmp_path):
        manager = SessionManager(tmp_path)
        assert manager.get("nope") is None

    def test_save_and_reload(self, tmp_path):
        manager = SessionManager(tmp_path)
        state = manager.create(task="save_test")
        state.used.add_iteration(tokens=100)
        state.record_violation("test", "failed")
        manager.save(state)

        reloaded = manager.get(state.session_id)
        assert reloaded.used.tokens == 100
        assert len(reloaded.violations) == 1

    def test_list_sessions(self, tmp_path):
        manager = SessionManager(tmp_path)
        manager.create(task="a")
        manager.create(task="b")
        manager.create(task="c")
        assert len(manager.list_sessions()) == 3

    def test_list_active_only(self, tmp_path):
        manager = SessionManager(tmp_path)
        s1 = manager.create(task="active")
        s2 = manager.create(task="stopped")
        s2.stop(StopReason.HUMAN_STOP)
        manager.save(s2)

        active = manager.list_sessions(active_only=True)
        assert len(active) == 1
        assert active[0].task == "active"

    def test_delete_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        state = manager.create(task="to_delete")
        assert manager.delete(state.session_id) is True
        assert manager.get(state.session_id) is None

    def test_delete_nonexistent(self, tmp_path):
        manager = SessionManager(tmp_path)
        assert manager.delete("nope") is False

    def test_persistence_across_instances(self, tmp_path):
        m1 = SessionManager(tmp_path)
        state = m1.create(task="persisted")

        m2 = SessionManager(tmp_path)
        loaded = m2.get(state.session_id)
        assert loaded is not None
        assert loaded.task == "persisted"
