"""
Autonomous executor: governor-constrained autonomous operation.

The executor runs a step function in a loop, checking spine compliance
and invariants at each step. Humans define the constraints (spine, invariants,
budget); the executor enforces them mechanically.

Phase A2: Core executor loop.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import time

from .spine import SpineManager, SpineCheckResult
from .invariants import InvariantSet, InvariantResult
from .execution import (
    ExecutionBudget,
    ExecutionUsage,
    ExecutionState,
    ExecutionStatus,
    StopReason,
    SessionManager,
)


@dataclass
class StepResult:
    """Result of one executor step."""

    success: bool
    message: str = ""
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    progress: dict[str, Any] = field(default_factory=dict)
    done: bool = False  # True = task complete, stop execution


@dataclass
class ExecutorConfig:
    """Configuration for the autonomous executor."""

    stop_on_violation: bool = True
    checkpoint_interval: int = 5  # Checkpoint every N iterations
    rate_limit_seconds: float = 0.0  # Delay between iterations
    max_consecutive_failures: int = 3


@dataclass
class ExecutionEvent:
    """An event during execution (for audit trail)."""

    iteration: int
    event_type: str  # "step", "spine_check", "invariant_check", "violation", "checkpoint", "stop"
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    details: dict[str, Any] = field(default_factory=dict)


# Step function type: takes state + iteration, returns StepResult
StepFn = Callable[[ExecutionState, int], StepResult]


class AutonomousExecutor:
    """
    Governor-constrained autonomous executor.

    Runs a step function in a loop with spine compliance checking,
    invariant verification, budget enforcement, and checkpointing.

    Usage:
        executor = AutonomousExecutor(
            spine_manager=SpineManager(root),
            invariants=invariant_set,
            session_manager=SessionManager(root),
        )
        state = executor.execute(
            step_fn=my_agent_step,
            task="Build feature X",
            budget=ExecutionBudget(max_iterations=50),
        )
    """

    def __init__(
        self,
        spine_manager: SpineManager | None = None,
        invariants: InvariantSet | None = None,
        session_manager: SessionManager | None = None,
        config: ExecutorConfig | None = None,
    ):
        self.spine_manager = spine_manager or SpineManager()
        self.invariants = invariants or InvariantSet()
        self.session_manager = session_manager
        self.config = config or ExecutorConfig()
        self.events: list[ExecutionEvent] = []

    def execute(
        self,
        step_fn: StepFn,
        task: str,
        budget: ExecutionBudget | None = None,
        spine_id: str | None = None,
        resume_state: ExecutionState | None = None,
    ) -> ExecutionState:
        """
        Run the autonomous execution loop.

        Args:
            step_fn: Callable that performs one step of work.
            task: Description of what to accomplish.
            budget: Resource limits.
            spine_id: Which spine to enforce (or use active).
            resume_state: Resume from a previous state.

        Returns:
            Final ExecutionState with status and all recorded events.
        """
        # Initialize or resume state
        if resume_state:
            state = resume_state
            state.resume()
        else:
            state = ExecutionState(
                task=task,
                spine_id=spine_id,
                invariant_ids=[i.id for i in self.invariants.invariants],
                budget=budget or ExecutionBudget(),
            )

        if spine_id:
            self.spine_manager.set_active(spine_id)

        self.events = []
        consecutive_failures = 0
        start_time = time.monotonic()

        while state.status == ExecutionStatus.RUNNING:
            iteration = state.used.iterations + 1
            iter_start = time.monotonic()

            # Check budget before step
            state.used.elapsed_seconds = time.monotonic() - start_time + (
                resume_state.used.elapsed_seconds if resume_state else 0
            )
            exhausted, reason = state.budget.is_exhausted(state.used)
            if exhausted:
                state.stop(StopReason.BUDGET_EXHAUSTED)
                self._record_event(iteration, "stop", f"Budget exhausted: {reason}")
                break

            # Run step
            try:
                step_result = step_fn(state, iteration)
            except Exception as e:
                consecutive_failures += 1
                self._record_event(iteration, "step", f"Step error: {e}")
                if consecutive_failures >= self.config.max_consecutive_failures:
                    state.stop(StopReason.ERROR)
                    self._record_event(
                        iteration, "stop",
                        f"Too many consecutive failures ({consecutive_failures})",
                    )
                    break
                continue

            consecutive_failures = 0

            # Record usage
            iter_elapsed = time.monotonic() - iter_start
            state.used.add_iteration(
                tokens=step_result.tokens_used,
                elapsed_seconds=iter_elapsed,
                cost_usd=step_result.cost_usd,
            )

            if step_result.progress:
                state.progress.update(step_result.progress)

            self._record_event(
                iteration, "step",
                step_result.message or f"Step {iteration} complete",
            )

            # Check if step succeeded
            if not step_result.success:
                self._record_event(iteration, "step", f"Step failed: {step_result.message}")
                continue

            # Check if task is done
            if step_result.done:
                state.complete()
                self._record_event(iteration, "stop", "Task completed by agent")
                break

            # Spine check
            if self.spine_manager.active_spine() is not None:
                proposal = {
                    "files_modified": step_result.files_modified,
                    "files_created": step_result.files_created,
                    "files_deleted": step_result.files_deleted,
                }
                spine_result = self.spine_manager.verify_proposal(proposal)
                if not spine_result.valid:
                    violation_msgs = [v.message for v in spine_result.violations]
                    state.record_violation(
                        "spine", "; ".join(violation_msgs),
                    )
                    self._record_event(
                        iteration, "spine_check",
                        f"Spine violations: {violation_msgs}",
                    )
                    if self.config.stop_on_violation:
                        state.stop(StopReason.CONSTRAINT_VIOLATION)
                        break

            # Invariant check
            all_files = (
                step_result.files_modified
                + step_result.files_created
            )
            blocking = self.invariants.blocking_violations(
                files_touched=all_files,
                root=self.spine_manager.root,
            )
            if blocking:
                for b in blocking:
                    state.record_violation(b.invariant_id, b.message)
                    self._record_event(
                        iteration, "invariant_check",
                        f"Invariant violation: {b.invariant_id}: {b.message}",
                    )
                if self.config.stop_on_violation:
                    state.stop(StopReason.CONSTRAINT_VIOLATION)
                    break

            # Checkpoint
            if (
                self.session_manager
                and iteration % self.config.checkpoint_interval == 0
            ):
                self.session_manager.save(state)
                self._record_event(iteration, "checkpoint", "State saved")

            # Rate limiting
            if self.config.rate_limit_seconds > 0:
                time.sleep(self.config.rate_limit_seconds)

        # Final checkpoint
        if self.session_manager:
            self.session_manager.save(state)

        return state

    def _record_event(
        self, iteration: int, event_type: str, message: str, **details: Any,
    ) -> None:
        self.events.append(ExecutionEvent(
            iteration=iteration,
            event_type=event_type,
            message=message,
            details=details,
        ))
