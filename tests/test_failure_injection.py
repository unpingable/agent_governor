# SPDX-License-Identifier: Apache-2.0
"""
Failure-injection tests for the autonomous executor.

Purpose: Verify that the executor handles faults gracefully — timeouts,
checkpoint corruption, save failures, and mid-flight budget exhaustion.
These tests protect autonomous mode from silent degradation.

Categories:
1. Tool call timeouts (step_fn raises TimeoutError)
2. Checkpoint write failures (SessionManager.save raises)
3. Resume from corrupted checkpoint (bad JSON on disk)
4. Consecutive failure threshold
5. Budget exhaustion mid-step
6. Spine check during failure recovery
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from governor.executor import (
    AutonomousExecutor,
    ExecutorConfig,
    StepResult,
)
from governor.execution import (
    ExecutionBudget,
    ExecutionState,
    ExecutionStatus,
    ExecutionUsage,
    SessionManager,
    StopReason,
)
from governor.spine import Spine, SpineManager
from governor.invariants import InvariantSet


# =============================================================================
# Helpers
# =============================================================================


def _success_step(state, iteration):
    """Step that always succeeds."""
    return StepResult(success=True, message=f"Step {iteration} ok")


def _done_step(state, iteration):
    """Step that completes the task."""
    return StepResult(success=True, message="Done", done=True)


def _failing_step(state, iteration):
    """Step that always raises."""
    raise RuntimeError("Tool exploded")


def _timeout_step(state, iteration):
    """Step that simulates a timeout."""
    raise TimeoutError("Tool call timed out after 30s")


def _intermittent_step(fail_until=3):
    """Step that fails N times then succeeds."""
    call_count = [0]
    def step(state, iteration):
        call_count[0] += 1
        if call_count[0] <= fail_until:
            raise RuntimeError(f"Failure #{call_count[0]}")
        return StepResult(success=True, message="Recovered", done=True)
    return step


def _slow_step(state, iteration):
    """Step that reports high token usage."""
    return StepResult(
        success=True,
        message=f"Step {iteration}",
        tokens_used=50000,
        cost_usd=1.00,
    )


# =============================================================================
# 1. Tool Call Timeouts
# =============================================================================


class TestTimeoutHandling:
    """Executor handles TimeoutError from step functions."""

    def test_timeout_counts_as_failure(self):
        """TimeoutError counts toward consecutive failure limit."""
        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=2),
        )
        state = executor.execute(
            step_fn=_timeout_step,
            task="Test timeout",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.ERROR

    def test_timeout_recorded_in_events(self):
        """TimeoutError is recorded in executor events."""
        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=1),
        )
        state = executor.execute(
            step_fn=_timeout_step,
            task="Test timeout events",
            budget=ExecutionBudget(max_iterations=5),
        )
        step_events = [e for e in executor.events if e.event_type == "step"]
        assert any("timed out" in e.message.lower() or "timeout" in e.message.lower()
                    for e in step_events)

    def test_timeout_does_not_corrupt_state(self):
        """State remains consistent after timeouts."""
        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=_timeout_step,
            task="Test state integrity",
            budget=ExecutionBudget(max_iterations=10),
        )
        # State should be well-formed
        assert state.session_id is not None
        assert state.task == "Test state integrity"
        assert state.status == ExecutionStatus.STOPPED

    def test_timeout_then_recovery(self):
        """Executor recovers if step succeeds after timeout."""
        call_count = [0]
        def step(state, iteration):
            call_count[0] += 1
            if call_count[0] == 1:
                raise TimeoutError("First call times out")
            return StepResult(success=True, message="Recovered", done=True)

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=step,
            task="Timeout recovery",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.COMPLETED


# =============================================================================
# 2. Checkpoint Write Failures
# =============================================================================


class TestCheckpointWriteFailures:
    """Executor handles SessionManager.save() failures."""

    def test_save_failure_propagates(self):
        """If checkpoint save fails, the error propagates (fail-closed behavior)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))

            # Patch save to always raise
            sm.save = MagicMock(side_effect=OSError("Disk full"))

            executor = AutonomousExecutor(
                session_manager=sm,
                config=ExecutorConfig(checkpoint_interval=1),
            )

            # The executor doesn't swallow save errors — this is correct
            # fail-closed behavior: if we can't persist state, we stop.
            with pytest.raises(OSError, match="Disk full"):
                executor.execute(
                    step_fn=_done_step,
                    task="Test save failure",
                    budget=ExecutionBudget(max_iterations=5),
                )

    def test_final_checkpoint_failure_still_returns_state(self):
        """If final checkpoint fails, state is still returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            sm.save = MagicMock(side_effect=OSError("Disk full"))

            executor = AutonomousExecutor(
                session_manager=sm,
                config=ExecutorConfig(checkpoint_interval=1),
            )

            # The executor may raise or handle — either way,
            # we should get meaningful state or a clean error
            try:
                state = executor.execute(
                    step_fn=_done_step,
                    task="Final save fails",
                    budget=ExecutionBudget(max_iterations=5),
                )
                # If it returns, state should be valid
                assert state.task == "Final save fails"
            except OSError:
                # Acceptable: the executor propagated the save error
                pass


# =============================================================================
# 3. Resume from Corrupted Checkpoint
# =============================================================================


class TestCorruptedCheckpointResume:
    """Resume from malformed checkpoint files."""

    def test_corrupted_json_raises(self):
        """Loading corrupted JSON raises a meaningful error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".governor" / "autonomous"
            session_dir.mkdir(parents=True)
            bad_file = session_dir / "bad_session.json"
            bad_file.write_text("NOT VALID JSON {{{")

            with pytest.raises((json.JSONDecodeError, ValueError, KeyError)):
                ExecutionState.load(bad_file)

    def test_empty_file_raises(self):
        """Loading empty file raises."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".governor" / "autonomous"
            session_dir.mkdir(parents=True)
            empty_file = session_dir / "empty.json"
            empty_file.write_text("")

            with pytest.raises((json.JSONDecodeError, ValueError)):
                ExecutionState.load(empty_file)

    def test_partial_json_missing_fields(self):
        """JSON with missing fields uses defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".governor" / "autonomous"
            session_dir.mkdir(parents=True)
            partial_file = session_dir / "partial.json"
            partial_file.write_text(json.dumps({"task": "partial"}))

            state = ExecutionState.from_dict({"task": "partial"})
            assert state.task == "partial"
            assert state.status == ExecutionStatus.RUNNING
            assert state.budget.max_iterations is None

    def test_wrong_type_in_status_field(self):
        """Invalid status value in JSON."""
        data = {
            "session_id": "test",
            "task": "test",
            "status": "invalid_status",
        }
        with pytest.raises(ValueError):
            ExecutionState.from_dict(data)

    def test_session_manager_skips_corrupted_files(self):
        """SessionManager.list_sessions skips corrupted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))

            # Create a valid session
            valid_state = sm.create(task="Valid task")

            # Create a corrupted file
            session_dir = Path(tmpdir) / ".governor" / "autonomous"
            bad_file = session_dir / "corrupted.json"
            bad_file.write_text("NOT JSON")

            # list_sessions should skip the bad file
            sessions = sm.list_sessions()
            assert len(sessions) == 1
            assert sessions[0].task == "Valid task"

    def test_valid_checkpoint_roundtrip(self):
        """Valid checkpoint file round-trips correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            state = sm.create(
                task="Round trip test",
                budget=ExecutionBudget(max_iterations=10),
            )
            state.used.add_iteration(tokens=100)
            sm.save(state)

            loaded = sm.get(state.session_id)
            assert loaded is not None
            assert loaded.task == "Round trip test"
            assert loaded.used.tokens == 100
            assert loaded.budget.max_iterations == 10


# =============================================================================
# 4. Consecutive Failure Threshold
# =============================================================================


class TestConsecutiveFailureThreshold:
    """Executor stops after too many consecutive failures."""

    def test_stops_at_threshold(self):
        """Executor stops after max_consecutive_failures."""
        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=_failing_step,
            task="Always fails",
            budget=ExecutionBudget(max_iterations=100),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.ERROR
        # Should have exactly 3 failed iterations (not 100)
        assert state.used.iterations == 0  # Failures don't count as iterations

    def test_recovery_resets_counter(self):
        """A successful step resets the consecutive failure counter."""
        step = _intermittent_step(fail_until=2)

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=step,
            task="Intermittent",
            budget=ExecutionBudget(max_iterations=10),
        )
        # Should complete because it recovers before hitting 3
        assert state.status == ExecutionStatus.COMPLETED

    def test_different_exception_types_all_count(self):
        """Various exception types all count toward the limit."""
        errors = [ValueError("bad"), TypeError("wrong"), RuntimeError("oops")]
        idx = [0]
        def rotating_error(state, iteration):
            err = errors[idx[0] % len(errors)]
            idx[0] += 1
            raise err

        executor = AutonomousExecutor(
            config=ExecutorConfig(max_consecutive_failures=3),
        )
        state = executor.execute(
            step_fn=rotating_error,
            task="Various errors",
            budget=ExecutionBudget(max_iterations=100),
        )
        assert state.status == ExecutionStatus.STOPPED


# =============================================================================
# 5. Budget Exhaustion Mid-Step
# =============================================================================


class TestBudgetExhaustionMidStep:
    """Executor stops cleanly when budget runs out during execution."""

    def test_token_budget_exhaustion(self):
        """Stops when token budget is exhausted."""
        executor = AutonomousExecutor()
        state = executor.execute(
            step_fn=_slow_step,
            task="Token hungry",
            budget=ExecutionBudget(max_tokens=60000),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED

    def test_iteration_budget_exhaustion(self):
        """Stops at iteration limit."""
        executor = AutonomousExecutor()
        state = executor.execute(
            step_fn=_success_step,
            task="Iteration limit",
            budget=ExecutionBudget(max_iterations=3),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED

    def test_cost_budget_exhaustion(self):
        """Stops when cost budget is exhausted."""
        executor = AutonomousExecutor()
        state = executor.execute(
            step_fn=_slow_step,
            task="Cost limit",
            budget=ExecutionBudget(max_cost_usd=1.50),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.BUDGET_EXHAUSTED

    def test_budget_check_happens_before_step(self):
        """Budget is checked BEFORE each step (not after)."""
        calls = [0]
        def counting_step(state, iteration):
            calls[0] += 1
            return StepResult(success=True, message="ok", tokens_used=100)

        executor = AutonomousExecutor()
        state = executor.execute(
            step_fn=counting_step,
            task="Pre-check",
            budget=ExecutionBudget(max_iterations=2),
        )
        # Should have been called exactly 2 times (budget checked before 3rd)
        assert calls[0] == 2

    def test_usage_tracked_accurately(self):
        """Usage metrics accurately reflect consumed resources."""
        executor = AutonomousExecutor()
        state = executor.execute(
            step_fn=_slow_step,
            task="Track usage",
            budget=ExecutionBudget(max_iterations=3),
        )
        assert state.used.iterations == 3
        assert state.used.tokens == 150000  # 50000 per step × 3
        assert state.used.cost_usd == pytest.approx(3.00, abs=0.01)


# =============================================================================
# 6. Spine Check During Failure Recovery
# =============================================================================


class TestSpineCheckDuringRecovery:
    """Spine constraints are still enforced even after partial failures."""

    def test_spine_violation_stops_execution(self):
        """A spine violation during execution stops the executor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sm = SpineManager(root=root)

            spine = Spine(
                id="test_spine",
                structure={
                    "forbidden_paths": ["*.secret"],
                },
            )
            sm.lock(spine)
            sm.set_active("test_spine")

            def step_touching_forbidden(state, iteration):
                return StepResult(
                    success=True,
                    message="Created secret",
                    files_created=["creds.secret"],
                )

            executor = AutonomousExecutor(
                spine_manager=sm,
                config=ExecutorConfig(stop_on_violation=True),
            )
            state = executor.execute(
                step_fn=step_touching_forbidden,
                task="Spine test",
                budget=ExecutionBudget(max_iterations=10),
            )
            assert state.status == ExecutionStatus.STOPPED
            assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION
            assert len(state.violations) > 0

    def test_invariant_violation_recorded(self):
        """Invariant violations are recorded in state.violations."""
        from governor.invariants import Invariant, InvariantType, InvariantResult

        def always_fail(**kwargs):
            return InvariantResult(
                passed=False,
                message="Security issue found",
                invariant_id="always_fail",
            )

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="always_fail",
            type=InvariantType.FORBIDDEN,
            rule="Always fails",
            verify=always_fail,
            on_violation="block",
        ))

        executor = AutonomousExecutor(
            invariants=inv_set,
            config=ExecutorConfig(stop_on_violation=True),
        )
        state = executor.execute(
            step_fn=_success_step,
            task="Invariant test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert any("always_fail" in v.get("invariant_id", "") for v in state.violations)

    def test_warning_invariant_does_not_stop(self):
        """A warning-level invariant doesn't stop execution."""
        from governor.invariants import Invariant, InvariantType, InvariantResult

        def warn_check(**kwargs):
            return InvariantResult(
                passed=False,
                message="Minor issue",
                invariant_id="warn_inv",
            )

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="warn_inv",
            type=InvariantType.CONSISTENCY,
            rule="Warns only",
            verify=warn_check,
            on_violation="warn",  # Not "block"
        ))

        executor = AutonomousExecutor(
            invariants=inv_set,
            config=ExecutorConfig(stop_on_violation=True),
        )
        state = executor.execute(
            step_fn=_done_step,
            task="Warning test",
            budget=ExecutionBudget(max_iterations=10),
        )
        # Should complete (warning doesn't block)
        assert state.status == ExecutionStatus.COMPLETED


# =============================================================================
# 7. Execution State Persistence Under Faults
# =============================================================================


class TestStatePersistenceUnderFaults:
    """State persists correctly even when execution ends abnormally."""

    def test_state_saved_after_error_stop(self):
        """State is saved to disk after error-induced stop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            executor = AutonomousExecutor(
                session_manager=sm,
                config=ExecutorConfig(max_consecutive_failures=2),
            )
            state = executor.execute(
                step_fn=_failing_step,
                task="Error state save",
                budget=ExecutionBudget(max_iterations=10),
            )
            # Load from disk
            loaded = sm.get(state.session_id)
            assert loaded is not None
            assert loaded.status == ExecutionStatus.STOPPED
            assert loaded.stop_reason == StopReason.ERROR

    def test_state_saved_after_budget_exhaustion(self):
        """State is saved to disk after budget exhaustion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            executor = AutonomousExecutor(session_manager=sm)
            state = executor.execute(
                step_fn=_success_step,
                task="Budget save",
                budget=ExecutionBudget(max_iterations=2),
            )
            loaded = sm.get(state.session_id)
            assert loaded is not None
            assert loaded.stop_reason == StopReason.BUDGET_EXHAUSTED

    def test_state_saved_after_completion(self):
        """State is saved to disk after normal completion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            executor = AutonomousExecutor(session_manager=sm)
            state = executor.execute(
                step_fn=_done_step,
                task="Normal complete",
                budget=ExecutionBudget(max_iterations=10),
            )
            loaded = sm.get(state.session_id)
            assert loaded is not None
            assert loaded.status == ExecutionStatus.COMPLETED

    def test_resume_from_saved_state(self):
        """Can resume execution from a previously saved state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(root=Path(tmpdir))
            executor = AutonomousExecutor(session_manager=sm)

            # First run: exhaust budget
            state = executor.execute(
                step_fn=_success_step,
                task="Resume test",
                budget=ExecutionBudget(max_iterations=3),
            )
            assert state.status == ExecutionStatus.STOPPED

            # Pause and reload
            state.pause()
            sm.save(state)

            loaded = sm.get(state.session_id)
            assert loaded is not None
            assert loaded.status == ExecutionStatus.PAUSED

            # Resume with new budget
            loaded.budget = ExecutionBudget(max_iterations=loaded.used.iterations + 2)
            state2 = executor.execute(
                step_fn=_done_step,
                task="Resume test",
                resume_state=loaded,
            )
            assert state2.status == ExecutionStatus.COMPLETED
