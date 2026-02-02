"""
Tests for Phase A2: Autonomous executor loop.
"""

import pytest
from pathlib import Path

from governor.executor import (
    StepResult,
    ExecutorConfig,
    ExecutionEvent,
    AutonomousExecutor,
    StepFn,
)
from governor.execution import (
    ExecutionBudget,
    ExecutionState,
    ExecutionStatus,
    ExecutionUsage,
    StopReason,
    SessionManager,
)
from governor.spine import Spine, SpineManager
from governor.invariants import (
    Invariant,
    InvariantSet,
    InvariantType,
    InvariantResult,
    InvariantLibrary,
)


# =============================================================================
# StepResult
# =============================================================================


class TestStepResult:
    def test_default(self):
        r = StepResult(success=True)
        assert r.success is True
        assert r.message == ""
        assert r.files_modified == []
        assert r.files_created == []
        assert r.files_deleted == []
        assert r.tokens_used == 0
        assert r.cost_usd == 0.0
        assert r.progress == {}
        assert r.done is False

    def test_with_values(self):
        r = StepResult(
            success=True,
            message="Built module",
            files_modified=["src/main.py"],
            files_created=["src/utils.py"],
            tokens_used=500,
            cost_usd=0.05,
            progress={"step": 1},
            done=True,
        )
        assert r.files_modified == ["src/main.py"]
        assert r.files_created == ["src/utils.py"]
        assert r.tokens_used == 500
        assert r.done is True

    def test_failed_step(self):
        r = StepResult(success=False, message="Compilation error")
        assert r.success is False
        assert r.message == "Compilation error"


# =============================================================================
# ExecutorConfig
# =============================================================================


class TestExecutorConfig:
    def test_defaults(self):
        c = ExecutorConfig()
        assert c.stop_on_violation is True
        assert c.checkpoint_interval == 5
        assert c.rate_limit_seconds == 0.0
        assert c.max_consecutive_failures == 3

    def test_custom(self):
        c = ExecutorConfig(
            stop_on_violation=False,
            checkpoint_interval=10,
            rate_limit_seconds=1.0,
            max_consecutive_failures=5,
        )
        assert c.stop_on_violation is False
        assert c.checkpoint_interval == 10
        assert c.rate_limit_seconds == 1.0
        assert c.max_consecutive_failures == 5


# =============================================================================
# ExecutionEvent
# =============================================================================


class TestExecutionEvent:
    def test_basic(self):
        e = ExecutionEvent(iteration=1, event_type="step", message="Done")
        assert e.iteration == 1
        assert e.event_type == "step"
        assert e.message == "Done"
        assert e.timestamp  # Auto-populated
        assert e.details == {}

    def test_with_details(self):
        e = ExecutionEvent(
            iteration=5,
            event_type="violation",
            message="Spine violation",
            details={"file": "secret.key"},
        )
        assert e.details["file"] == "secret.key"


# =============================================================================
# AutonomousExecutor - Basic execution
# =============================================================================


def _make_step_fn(results: list[StepResult]) -> StepFn:
    """Helper: make a step function from a list of results."""
    idx = [0]

    def step_fn(state: ExecutionState, iteration: int) -> StepResult:
        if idx[0] < len(results):
            r = results[idx[0]]
            idx[0] += 1
            return r
        return StepResult(success=True, done=True)

    return step_fn


def _counting_step_fn(count: int = 3) -> StepFn:
    """Helper: step function that runs N times then completes."""
    calls = [0]

    def step_fn(state: ExecutionState, iteration: int) -> StepResult:
        calls[0] += 1
        if calls[0] >= count:
            return StepResult(success=True, message=f"Step {calls[0]}", done=True)
        return StepResult(success=True, message=f"Step {calls[0]}")

    return step_fn


class TestExecutorBasic:
    def test_simple_completion(self):
        executor = AutonomousExecutor()
        step_fn = _counting_step_fn(3)
        state = executor.execute(
            step_fn=step_fn,
            task="simple task",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.COMPLETED
        assert state.stop_reason == StopReason.AGENT_COMPLETION
        assert state.used.iterations == 3
        assert state.task == "simple task"

    def test_immediate_completion(self):
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([StepResult(success=True, done=True)])
        state = executor.execute(step_fn=step_fn, task="instant")
        assert state.status == ExecutionStatus.COMPLETED
        assert state.used.iterations == 1

    def test_budget_exhaustion(self):
        executor = AutonomousExecutor()
        # Step function never sets done=True
        step_fn = lambda state, it: StepResult(success=True, message=f"Step {it}")
        state = executor.execute(
            step_fn=step_fn,
            task="budget test",
            budget=ExecutionBudget(max_iterations=5),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED
        assert state.used.iterations == 5

    def test_token_budget(self):
        executor = AutonomousExecutor()

        def step_fn(state, it):
            return StepResult(success=True, tokens_used=600)

        state = executor.execute(
            step_fn=step_fn,
            task="token budget",
            budget=ExecutionBudget(max_tokens=1000),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED
        # First step uses 600 tokens, second check sees 600 < 1000, runs again,
        # now 1200 >= 1000, budget exhausted
        assert state.used.tokens >= 1000

    def test_cost_budget(self):
        executor = AutonomousExecutor()

        def step_fn(state, it):
            return StepResult(success=True, cost_usd=3.0)

        state = executor.execute(
            step_fn=step_fn,
            task="cost budget",
            budget=ExecutionBudget(max_cost_usd=5.0),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED

    def test_events_recorded(self):
        executor = AutonomousExecutor()
        step_fn = _counting_step_fn(2)
        state = executor.execute(
            step_fn=step_fn,
            task="event test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert len(executor.events) > 0
        # Should have step events + stop event
        event_types = [e.event_type for e in executor.events]
        assert "step" in event_types
        assert "stop" in event_types

    def test_unlimited_budget(self):
        executor = AutonomousExecutor()
        step_fn = _counting_step_fn(5)
        state = executor.execute(step_fn=step_fn, task="unlimited")
        assert state.status == ExecutionStatus.COMPLETED
        assert state.used.iterations == 5

    def test_progress_tracked(self):
        executor = AutonomousExecutor()

        def step_fn(state, it):
            return StepResult(
                success=True,
                progress={"files_processed": it},
                done=(it >= 3),
            )

        state = executor.execute(
            step_fn=step_fn,
            task="progress",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.progress["files_processed"] == 3

    def test_state_has_invariant_ids(self):
        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="test_inv",
            type=InvariantType.TEST,
            rule="Test",
            verify=lambda **kw: InvariantResult(passed=True, message="OK", invariant_id="test_inv"),
        ))
        executor = AutonomousExecutor(invariants=inv_set)
        step_fn = _make_step_fn([StepResult(success=True, done=True)])
        state = executor.execute(step_fn=step_fn, task="inv ids")
        assert "test_inv" in state.invariant_ids


# =============================================================================
# Error handling
# =============================================================================


class TestExecutorErrors:
    def test_step_exception_retried(self):
        calls = [0]

        def failing_step(state, it):
            calls[0] += 1
            if calls[0] <= 2:
                raise ValueError("Temporary error")
            return StepResult(success=True, done=True)

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=failing_step,
            task="retry test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.COMPLETED
        assert calls[0] == 3  # 2 failures + 1 success

    def test_max_consecutive_failures(self):
        def always_fail(state, it):
            raise RuntimeError("Permanent error")

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=always_fail,
            task="fail test",
            budget=ExecutionBudget(max_iterations=20),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.ERROR

    def test_failures_reset_on_success(self):
        calls = [0]

        def intermittent_step(state, it):
            calls[0] += 1
            if calls[0] in (1, 3):
                raise ValueError("Intermittent")
            if calls[0] >= 5:
                return StepResult(success=True, done=True)
            return StepResult(success=True)

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=2),
        )
        state = executor.execute(
            step_fn=intermittent_step,
            task="intermittent",
            budget=ExecutionBudget(max_iterations=20),
        )
        assert state.status == ExecutionStatus.COMPLETED

    def test_failed_step_not_counted_as_exception(self):
        """A step returning success=False is not an exception."""
        calls = [0]

        def step_fn(state, it):
            calls[0] += 1
            if calls[0] <= 3:
                return StepResult(success=False, message="Not ready")
            return StepResult(success=True, done=True)

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=2),
        )
        state = executor.execute(
            step_fn=step_fn,
            task="soft fail",
            budget=ExecutionBudget(max_iterations=20),
        )
        assert state.status == ExecutionStatus.COMPLETED


# =============================================================================
# Spine enforcement
# =============================================================================


class TestExecutorSpine:
    def test_no_spine_allows_all(self):
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([
            StepResult(
                success=True,
                files_created=["any_file.py"],
                done=True,
            ),
        ])
        state = executor.execute(step_fn=step_fn, task="no spine")
        assert state.status == ExecutionStatus.COMPLETED
        assert len(state.violations) == 0

    def test_spine_violation_stops_execution(self, tmp_path):
        # Create a spine that forbids *.secret files
        spine = Spine(
            id="strict",
            structure={"forbidden_paths": ["*.secret"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("strict")

        executor = AutonomousExecutor(
            spine_manager=manager,
            config=ExecutorConfig(stop_on_violation=True),
        )
        step_fn = _make_step_fn([
            StepResult(
                success=True,
                files_created=["db.secret"],
            ),
        ])
        state = executor.execute(
            step_fn=step_fn,
            task="spine test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION
        assert len(state.violations) > 0

    def test_spine_violation_continue_if_not_stop_on_violation(self, tmp_path):
        spine = Spine(
            id="lenient",
            structure={"forbidden_paths": ["*.secret"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("lenient")

        executor = AutonomousExecutor(
            spine_manager=manager,
            config=ExecutorConfig(stop_on_violation=False),
        )

        calls = [0]

        def step_fn(state, it):
            calls[0] += 1
            if calls[0] == 1:
                return StepResult(success=True, files_created=["bad.secret"])
            return StepResult(success=True, done=True)

        state = executor.execute(
            step_fn=step_fn,
            task="continue after violation",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.COMPLETED
        assert len(state.violations) > 0

    def test_spine_valid_proposal_passes(self, tmp_path):
        spine = Spine(
            id="basic",
            structure={
                "files": {"README.md": "required"},
                "forbidden_paths": ["*.secret"],
            },
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("basic")

        executor = AutonomousExecutor(spine_manager=manager)
        step_fn = _make_step_fn([
            StepResult(
                success=True,
                files_modified=["src/app.py"],
                done=True,
            ),
        ])
        state = executor.execute(step_fn=step_fn, task="valid proposal")
        assert state.status == ExecutionStatus.COMPLETED
        assert len(state.violations) == 0

    def test_spine_set_active_via_execute(self, tmp_path):
        spine = Spine(
            id="from_exec",
            structure={"forbidden_paths": ["*.key"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)

        executor = AutonomousExecutor(spine_manager=manager)
        step_fn = _make_step_fn([StepResult(success=True, done=True)])
        state = executor.execute(
            step_fn=step_fn,
            task="activate spine",
            spine_id="from_exec",
        )
        assert state.status == ExecutionStatus.COMPLETED
        assert manager.active_spine().id == "from_exec"

    def test_spine_required_file_deletion_blocked(self, tmp_path):
        spine = Spine(
            id="protect",
            structure={"files": {"README.md": "required"}},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("protect")

        executor = AutonomousExecutor(spine_manager=manager)
        step_fn = _make_step_fn([
            StepResult(
                success=True,
                files_deleted=["README.md"],
            ),
        ])
        state = executor.execute(
            step_fn=step_fn,
            task="delete required",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION


# =============================================================================
# Invariant enforcement
# =============================================================================


class TestExecutorInvariants:
    def _make_failing_invariant(self, inv_id: str) -> Invariant:
        return Invariant(
            id=inv_id,
            type=InvariantType.TEST,
            rule=f"Invariant {inv_id}",
            verify=lambda inv_id=inv_id, **kw: InvariantResult(
                passed=False, message=f"{inv_id} failed", invariant_id=inv_id,
            ),
            on_violation="block",
        )

    def _make_passing_invariant(self, inv_id: str) -> Invariant:
        return Invariant(
            id=inv_id,
            type=InvariantType.TEST,
            rule=f"Invariant {inv_id}",
            verify=lambda inv_id=inv_id, **kw: InvariantResult(
                passed=True, message="OK", invariant_id=inv_id,
            ),
        )

    def test_passing_invariants(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_passing_invariant("pass_1"))
        inv_set.add(self._make_passing_invariant("pass_2"))

        executor = AutonomousExecutor(invariants=inv_set)
        step_fn = _make_step_fn([
            StepResult(success=True, files_modified=["src/app.py"], done=True),
        ])
        state = executor.execute(step_fn=step_fn, task="inv pass")
        assert state.status == ExecutionStatus.COMPLETED
        assert len(state.violations) == 0

    def test_blocking_invariant_stops(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_failing_invariant("blocker"))

        executor = AutonomousExecutor(invariants=inv_set)
        step_fn = _make_step_fn([
            StepResult(success=True, files_modified=["src/app.py"]),
        ])
        state = executor.execute(
            step_fn=step_fn,
            task="inv block",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION
        assert len(state.violations) > 0

    def test_warning_invariant_continues(self):
        inv_set = InvariantSet()
        warner = Invariant(
            id="warner",
            type=InvariantType.TEST,
            rule="Warner",
            verify=lambda **kw: InvariantResult(
                passed=False, message="Warning", invariant_id="warner",
            ),
            on_violation="warn",
        )
        inv_set.add(warner)

        executor = AutonomousExecutor(invariants=inv_set)
        step_fn = _counting_step_fn(2)
        state = executor.execute(
            step_fn=step_fn,
            task="inv warn",
            budget=ExecutionBudget(max_iterations=10),
        )
        # Warnings don't generate blocking_violations, so no violations
        assert state.status == ExecutionStatus.COMPLETED

    def test_invariant_not_checked_on_failed_step(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_failing_invariant("blocker"))

        calls = [0]

        def step_fn(state, it):
            calls[0] += 1
            if calls[0] == 1:
                return StepResult(success=False, message="Failed")
            return StepResult(success=True, done=True)

        executor = AutonomousExecutor(invariants=inv_set)
        state = executor.execute(
            step_fn=step_fn,
            task="skip inv on fail",
            budget=ExecutionBudget(max_iterations=10),
        )
        # Second step succeeds and is done, so invariant checked on that step
        # but done=True triggers completion before invariant check
        # Actually looking at the code: done check is BEFORE invariant check
        assert state.status == ExecutionStatus.COMPLETED

    def test_empty_invariant_set(self):
        executor = AutonomousExecutor(invariants=InvariantSet())
        step_fn = _make_step_fn([
            StepResult(success=True, files_created=["anything.py"], done=True),
        ])
        state = executor.execute(step_fn=step_fn, task="no invariants")
        assert state.status == ExecutionStatus.COMPLETED


# =============================================================================
# Checkpointing
# =============================================================================


class TestExecutorCheckpointing:
    def test_checkpoint_at_interval(self, tmp_path):
        session_mgr = SessionManager(tmp_path)
        executor = AutonomousExecutor(
            session_manager=session_mgr,
            config=ExecutorConfig(checkpoint_interval=2),
        )
        step_fn = _counting_step_fn(5)
        state = executor.execute(
            step_fn=step_fn,
            task="checkpoint test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.COMPLETED
        # Should have checkpointed at iterations 2, 4 + final
        checkpoint_events = [
            e for e in executor.events if e.event_type == "checkpoint"
        ]
        assert len(checkpoint_events) >= 2

    def test_final_checkpoint_always(self, tmp_path):
        session_mgr = SessionManager(tmp_path)
        executor = AutonomousExecutor(
            session_manager=session_mgr,
            config=ExecutorConfig(checkpoint_interval=100),  # Won't hit interval
        )
        step_fn = _make_step_fn([StepResult(success=True, done=True)])
        state = executor.execute(step_fn=step_fn, task="final cp")
        # Final checkpoint happens even if interval not reached
        loaded = session_mgr.get(state.session_id)
        assert loaded is not None
        assert loaded.task == "final cp"

    def test_no_checkpoint_without_session_manager(self):
        executor = AutonomousExecutor(session_manager=None)
        step_fn = _counting_step_fn(3)
        state = executor.execute(
            step_fn=step_fn,
            task="no checkpoint",
        )
        assert state.status == ExecutionStatus.COMPLETED
        # No error from missing session manager

    def test_session_persisted_across_steps(self, tmp_path):
        session_mgr = SessionManager(tmp_path)
        executor = AutonomousExecutor(
            session_manager=session_mgr,
            config=ExecutorConfig(checkpoint_interval=1),  # Every step
        )
        step_fn = _counting_step_fn(3)
        state = executor.execute(
            step_fn=step_fn,
            task="persist test",
            budget=ExecutionBudget(max_iterations=10),
        )
        loaded = session_mgr.get(state.session_id)
        assert loaded.used.iterations == 3
        assert loaded.status == ExecutionStatus.COMPLETED


# =============================================================================
# Resume
# =============================================================================


class TestExecutorResume:
    def test_resume_from_paused(self, tmp_path):
        session_mgr = SessionManager(tmp_path)
        executor = AutonomousExecutor(session_manager=session_mgr)

        # First execution: 3 steps then pause
        calls = [0]

        def step_fn(state, it):
            calls[0] += 1
            if calls[0] >= 3:
                state.pause()
                return StepResult(success=True, done=False)
            return StepResult(success=True)

        state1 = executor.execute(
            step_fn=step_fn,
            task="resume test",
            budget=ExecutionBudget(max_iterations=20),
        )
        assert state1.status == ExecutionStatus.PAUSED

        # Resume with a new step function that completes
        step_fn2 = _make_step_fn([StepResult(success=True, done=True)])
        state2 = executor.execute(
            step_fn=step_fn2,
            task="resume test",
            resume_state=state1,
        )
        assert state2.status == ExecutionStatus.COMPLETED
        assert state2.session_id == state1.session_id

    def test_resume_preserves_usage(self):
        executor = AutonomousExecutor()

        # First run: 3 steps
        step_fn1 = _counting_step_fn(3)
        state1 = executor.execute(
            step_fn=step_fn1,
            task="preserve usage",
            budget=ExecutionBudget(max_iterations=20),
        )
        state1.pause()
        iterations_after_first = state1.used.iterations

        # Resume
        step_fn2 = _make_step_fn([StepResult(success=True, done=True)])
        state2 = executor.execute(
            step_fn=step_fn2,
            task="preserve usage",
            resume_state=state1,
        )
        assert state2.used.iterations == iterations_after_first + 1


# =============================================================================
# Combined spine + invariants
# =============================================================================


class TestExecutorCombined:
    def test_spine_and_invariants_both_pass(self, tmp_path):
        spine = Spine(
            id="combined",
            structure={"forbidden_paths": ["*.secret"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("combined")

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="always_pass",
            type=InvariantType.TEST,
            rule="Always pass",
            verify=lambda **kw: InvariantResult(
                passed=True, message="OK", invariant_id="always_pass",
            ),
        ))

        executor = AutonomousExecutor(
            spine_manager=manager,
            invariants=inv_set,
        )
        step_fn = _make_step_fn([
            StepResult(success=True, files_modified=["src/app.py"], done=True),
        ])
        state = executor.execute(step_fn=step_fn, task="combined")
        assert state.status == ExecutionStatus.COMPLETED
        assert len(state.violations) == 0

    def test_spine_passes_invariant_fails(self, tmp_path):
        spine = Spine(
            id="combo2",
            structure={"forbidden_paths": ["*.secret"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("combo2")

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="always_fail",
            type=InvariantType.TEST,
            rule="Always fail",
            verify=lambda **kw: InvariantResult(
                passed=False, message="FAIL", invariant_id="always_fail",
            ),
            on_violation="block",
        ))

        executor = AutonomousExecutor(
            spine_manager=manager,
            invariants=inv_set,
        )
        step_fn = _make_step_fn([
            StepResult(success=True, files_modified=["src/ok.py"]),
        ])
        state = executor.execute(
            step_fn=step_fn,
            task="spine ok inv fail",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION

    def test_spine_fails_before_invariant_check(self, tmp_path):
        """Spine check runs before invariant check. If spine fails, invariants not checked."""
        spine = Spine(
            id="first_check",
            structure={"forbidden_paths": ["*.key"]},
        )
        manager = SpineManager(tmp_path)
        manager.lock(spine)
        manager.set_active("first_check")

        invariant_checked = [False]

        def inv_verify(**kw):
            invariant_checked[0] = True
            return InvariantResult(passed=False, message="FAIL", invariant_id="inv_check")

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="inv_check",
            type=InvariantType.TEST,
            rule="Check order",
            verify=inv_verify,
            on_violation="block",
        ))

        executor = AutonomousExecutor(
            spine_manager=manager,
            invariants=inv_set,
        )
        step_fn = _make_step_fn([
            StepResult(success=True, files_created=["api.key"]),
        ])
        state = executor.execute(
            step_fn=step_fn,
            task="order test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        # Spine violation detected, so invariants were NOT checked
        assert not invariant_checked[0]


# =============================================================================
# Edge cases
# =============================================================================


class TestExecutorEdgeCases:
    def test_zero_iteration_budget(self):
        executor = AutonomousExecutor()
        step_fn = lambda state, it: StepResult(success=True, done=True)
        state = executor.execute(
            step_fn=step_fn,
            task="zero budget",
            budget=ExecutionBudget(max_iterations=0),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED
        assert state.used.iterations == 0

    def test_events_reset_each_execute(self):
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([StepResult(success=True, done=True)])

        executor.execute(step_fn=step_fn, task="run 1")
        events_1 = len(executor.events)

        executor.execute(step_fn=step_fn, task="run 2")
        # Events should be from run 2 only, not cumulative
        assert len(executor.events) == events_1  # Same pattern

    def test_usage_tracks_tokens(self):
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([
            StepResult(success=True, tokens_used=100, cost_usd=0.01),
            StepResult(success=True, tokens_used=200, cost_usd=0.02),
            StepResult(success=True, tokens_used=150, cost_usd=0.015, done=True),
        ])
        state = executor.execute(step_fn=step_fn, task="tokens")
        assert state.used.tokens == 450
        assert abs(state.used.cost_usd - 0.045) < 0.001
        assert state.used.iterations == 3

    def test_elapsed_seconds_tracked(self):
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([
            StepResult(success=True),
            StepResult(success=True, done=True),
        ])
        state = executor.execute(step_fn=step_fn, task="time")
        assert state.used.elapsed_seconds >= 0

    def test_default_executor(self):
        """Executor with all defaults works."""
        executor = AutonomousExecutor()
        step_fn = _make_step_fn([StepResult(success=True, done=True)])
        state = executor.execute(step_fn=step_fn, task="defaults")
        assert state.status == ExecutionStatus.COMPLETED
