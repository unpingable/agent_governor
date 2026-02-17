# SPDX-License-Identifier: Apache-2.0
"""
Execution state and budgets for autonomous operation.

Tracks resource consumption, progress, and state across multi-session
autonomous execution. The executor (Phase A2) uses these types;
this module defines the data structures only.

Phase A1: Core types (budget, usage, state).
Phase A2: Executor loop (future).
Phase A3: Session management (future).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import json
import uuid


class StopReason(str, Enum):
    """Why an autonomous execution session stopped."""

    AGENT_COMPLETION = "agent_completion"
    CONSTRAINT_VIOLATION = "constraint_violation"
    BUDGET_EXHAUSTED = "budget_exhausted"
    HUMAN_STOP = "human_stop"
    ERROR = "error"


class ExecutionStatus(str, Enum):
    """Current status of an execution session."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


# =============================================================================
# ExecutionBudget
# =============================================================================


@dataclass
class ExecutionBudget:
    """
    Resource limits for autonomous execution.

    Whichever limit is hit first stops execution. None means unlimited.
    """

    max_tokens: int | None = None
    max_iterations: int | None = None
    max_time_seconds: int | None = None
    max_cost_usd: float | None = None

    def is_exhausted(self, used: "ExecutionUsage") -> tuple[bool, str]:
        """Check if any budget limit has been reached."""
        if self.max_tokens is not None and used.tokens >= self.max_tokens:
            return True, f"Token budget exhausted: {used.tokens}/{self.max_tokens}"
        if self.max_iterations is not None and used.iterations >= self.max_iterations:
            return True, f"Iteration budget exhausted: {used.iterations}/{self.max_iterations}"
        if self.max_time_seconds is not None and used.elapsed_seconds >= self.max_time_seconds:
            return True, f"Time budget exhausted: {used.elapsed_seconds:.0f}s/{self.max_time_seconds}s"
        if self.max_cost_usd is not None and used.cost_usd >= self.max_cost_usd:
            return True, f"Cost budget exhausted: ${used.cost_usd:.2f}/${self.max_cost_usd:.2f}"
        return False, ""

    def remaining(self, used: "ExecutionUsage") -> dict[str, Any]:
        """Show remaining budget for each dimension."""
        result: dict[str, Any] = {}
        if self.max_tokens is not None:
            result["tokens"] = max(0, self.max_tokens - used.tokens)
        if self.max_iterations is not None:
            result["iterations"] = max(0, self.max_iterations - used.iterations)
        if self.max_time_seconds is not None:
            result["time_seconds"] = max(0.0, self.max_time_seconds - used.elapsed_seconds)
        if self.max_cost_usd is not None:
            result["cost_usd"] = max(0.0, self.max_cost_usd - used.cost_usd)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_iterations": self.max_iterations,
            "max_time_seconds": self.max_time_seconds,
            "max_cost_usd": self.max_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionBudget":
        return cls(
            max_tokens=data.get("max_tokens"),
            max_iterations=data.get("max_iterations"),
            max_time_seconds=data.get("max_time_seconds"),
            max_cost_usd=data.get("max_cost_usd"),
        )

    @classmethod
    def from_spec(cls, spec: str) -> "ExecutionBudget":
        """
        Parse a budget specification string.

        Format: "tokens=100000,iterations=50,time=1800,cost=5.00"
        """
        budget = cls()
        for part in spec.split(","):
            part = part.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "tokens":
                budget.max_tokens = int(value)
            elif key == "iterations":
                budget.max_iterations = int(value)
            elif key in ("time", "time_seconds"):
                budget.max_time_seconds = int(value)
            elif key in ("cost", "cost_usd"):
                budget.max_cost_usd = float(value)
        return budget


# =============================================================================
# ExecutionUsage
# =============================================================================


@dataclass
class ExecutionUsage:
    """Tracks resource consumption during execution."""

    tokens: int = 0
    iterations: int = 0
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0

    def add_iteration(
        self,
        tokens: int = 0,
        elapsed_seconds: float = 0.0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record one iteration of work."""
        self.iterations += 1
        self.tokens += tokens
        self.elapsed_seconds += elapsed_seconds
        self.cost_usd += cost_usd

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens,
            "iterations": self.iterations,
            "elapsed_seconds": self.elapsed_seconds,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionUsage":
        return cls(
            tokens=data.get("tokens", 0),
            iterations=data.get("iterations", 0),
            elapsed_seconds=data.get("elapsed_seconds", 0.0),
            cost_usd=data.get("cost_usd", 0.0),
        )


# =============================================================================
# ExecutionState
# =============================================================================


@dataclass
class ExecutionState:
    """
    Persistent state for multi-session autonomous execution.

    Checkpointed to disk so execution can resume across sessions.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task: str = ""
    spine_id: str | None = None
    invariant_ids: list[str] = field(default_factory=list)
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    used: ExecutionUsage = field(default_factory=ExecutionUsage)
    progress: dict[str, Any] = field(default_factory=dict)
    violations: list[dict[str, Any]] = field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.RUNNING
    stop_reason: StopReason | None = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_checkpoint: str | None = None

    def record_violation(self, invariant_id: str, message: str, **details: Any) -> None:
        """Record an invariant violation."""
        self.violations.append({
            "invariant_id": invariant_id,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **details,
        })

    def stop(self, reason: StopReason) -> None:
        """Mark execution as stopped."""
        self.status = ExecutionStatus.STOPPED
        self.stop_reason = reason

    def complete(self) -> None:
        """Mark execution as successfully completed."""
        self.status = ExecutionStatus.COMPLETED
        self.stop_reason = StopReason.AGENT_COMPLETION

    def pause(self) -> None:
        """Pause execution (can be resumed)."""
        self.status = ExecutionStatus.PAUSED

    def resume(self) -> None:
        """Resume paused execution."""
        if self.status == ExecutionStatus.PAUSED:
            self.status = ExecutionStatus.RUNNING

    @property
    def is_active(self) -> bool:
        return self.status in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED)

    def checkpoint(self, path: Path) -> None:
        """Save state to disk."""
        self.last_checkpoint = datetime.now().isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "spine_id": self.spine_id,
            "invariant_ids": list(self.invariant_ids),
            "budget": self.budget.to_dict(),
            "used": self.used.to_dict(),
            "progress": dict(self.progress),
            "violations": list(self.violations),
            "status": self.status.value,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "started_at": self.started_at,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionState":
        return cls(
            session_id=data.get("session_id", uuid.uuid4().hex[:12]),
            task=data.get("task", ""),
            spine_id=data.get("spine_id"),
            invariant_ids=data.get("invariant_ids", []),
            budget=ExecutionBudget.from_dict(data.get("budget", {})),
            used=ExecutionUsage.from_dict(data.get("used", {})),
            progress=data.get("progress", {}),
            violations=data.get("violations", []),
            status=ExecutionStatus(data.get("status", "running")),
            stop_reason=StopReason(data["stop_reason"]) if data.get("stop_reason") else None,
            started_at=data.get("started_at", datetime.now().isoformat()),
            last_checkpoint=data.get("last_checkpoint"),
        )

    @classmethod
    def load(cls, path: Path) -> "ExecutionState":
        """Load state from disk."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


# =============================================================================
# SessionManager
# =============================================================================


class SessionManager:
    """
    Manages execution sessions on disk.

    Sessions are stored in .governor/autonomous/<session_id>.json.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path(".")
        self.session_dir = self.root / ".governor" / "autonomous"

    def _ensure_dir(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.session_dir / f"{session_id}.json"

    def create(
        self,
        task: str,
        spine_id: str | None = None,
        invariant_ids: list[str] | None = None,
        budget: ExecutionBudget | None = None,
    ) -> ExecutionState:
        """Create a new execution session."""
        state = ExecutionState(
            task=task,
            spine_id=spine_id,
            invariant_ids=invariant_ids or [],
            budget=budget or ExecutionBudget(),
        )
        self._ensure_dir()
        state.checkpoint(self._session_path(state.session_id))
        return state

    def get(self, session_id: str) -> ExecutionState | None:
        """Get a session by ID."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        return ExecutionState.load(path)

    def save(self, state: ExecutionState) -> None:
        """Save session state."""
        self._ensure_dir()
        state.checkpoint(self._session_path(state.session_id))

    def list_sessions(self, active_only: bool = False) -> list[ExecutionState]:
        """List all sessions."""
        if not self.session_dir.exists():
            return []
        sessions = []
        for path in sorted(self.session_dir.glob("*.json")):
            try:
                state = ExecutionState.load(path)
                if active_only and not state.is_active:
                    continue
                sessions.append(state)
            except (json.JSONDecodeError, KeyError):
                continue
        return sessions

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        path = self._session_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
