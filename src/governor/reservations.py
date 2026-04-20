# SPDX-License-Identifier: Apache-2.0
"""Work-reservation primitives shared by CLI and daemon RPC.

These functions encapsulate the multi-agent coordination logic that was
previously inlined in cli.py task_* handlers. They take Storage and
PermissionManager as parameters so callers (CLI, daemon RPC, library
users) compose them with their own resource lifecycle.

All functions raise typed exceptions (subclasses of ReservationError) for
failure modes; callers translate to their preferred error surface (Click
exit codes, JSON-RPC errors, etc.).

Return values are plain dicts so callers can render them as JSON, format
for terminal output, or pass them through unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import uuid4

from .permissions import PermissionManager
from .storage import Storage


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ReservationError(Exception):
    """Base for reservation errors."""


class AgentNotRegistered(ReservationError):
    """The named agent has not been registered."""


class PermissionDenied(ReservationError):
    """The agent's permissions do not allow the requested scope path."""

    def __init__(self, message: str, *, agent_id: str, path: str) -> None:
        super().__init__(message)
        self.agent_id = agent_id
        self.path = path


class ScopeConflict(ReservationError):
    """Requested scope overlaps with an active reservation held by another agent."""

    def __init__(
        self,
        message: str,
        *,
        conflicting_task_id: str,
        conflicting_task: str,
        conflicting_agent_id: str,
        overlap: Sequence[str],
    ) -> None:
        super().__init__(message)
        self.conflicting_task_id = conflicting_task_id
        self.conflicting_task = conflicting_task
        self.conflicting_agent_id = conflicting_agent_id
        self.overlap = list(overlap)


class TaskNotFound(ReservationError):
    """No reservation exists with the given task_id."""


class TaskNotOwned(ReservationError):
    """The reservation exists but is owned by a different agent."""

    def __init__(self, message: str, *, owner_agent_id: str) -> None:
        super().__init__(message)
        self.owner_agent_id = owner_agent_id


class TaskAlreadyCompleted(ReservationError):
    """The reservation has already been marked complete."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _serialize_reservation(row: Any, *, now: datetime) -> dict[str, Any]:
    """Render a reservations row as a JSON-friendly dict with derived status."""
    completed = row["completed_at"] is not None
    expires = datetime.fromisoformat(row["expires_at"])
    expired = expires < now

    if completed:
        status = "completed"
    elif expired:
        status = "expired"
    else:
        status = "active"

    return {
        "id": row["id"],
        "task": row["task"],
        "agent_id": row["agent_id"],
        "scope": json.loads(row["scope_json"]),
        "status": status,
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "completed_at": row["completed_at"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def claim_reservation(
    storage: Storage,
    perm_manager: PermissionManager,
    *,
    agent_id: str,
    task: str,
    scope_paths: Sequence[str],
    eta_minutes: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Claim a work reservation for the given scope.

    Raises:
        AgentNotRegistered: agent_id is unknown.
        PermissionDenied: agent's permissions disallow one of scope_paths.
        ScopeConflict: another active reservation overlaps scope_paths.
    """
    now = _now(now)

    agent = storage.get_by_id("agents", agent_id)
    if not agent:
        raise AgentNotRegistered(
            f"Agent '{agent_id}' not registered. "
            f"Run 'governor agent register' first."
        )

    perms = perm_manager.get_permissions(agent_id, agent["agent_class"])
    for path in scope_paths:
        if not perms.can_touch_path(path):
            raise PermissionDenied(
                f"Agent '{agent_id}' cannot touch path '{path}'",
                agent_id=agent_id,
                path=path,
            )

    active = storage.query("reservations", where=None, order_by="started_at DESC")
    requested = set(scope_paths)
    for res in active:
        if res["completed_at"]:
            continue
        expires = datetime.fromisoformat(res["expires_at"])
        if expires < now:
            continue

        existing_scope = json.loads(res["scope_json"])
        overlap = requested & set(existing_scope)
        if overlap:
            raise ScopeConflict(
                f"Scope conflict with existing reservation '{res['id']}'",
                conflicting_task_id=res["id"],
                conflicting_task=res["task"],
                conflicting_agent_id=res["agent_id"],
                overlap=sorted(overlap),
            )

    task_id = str(uuid4())
    expires_at = now + timedelta(minutes=eta_minutes)

    storage.insert(
        "reservations",
        {
            "id": task_id,
            "task": task,
            "scope_json": json.dumps(list(scope_paths)),
            "agent_id": agent_id,
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "completed_at": None,
        },
    )
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "task": task,
        "scope": list(scope_paths),
        "eta_minutes": eta_minutes,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def heartbeat_reservation(
    storage: Storage,
    *,
    agent_id: str,
    task_id: str,
    extend_minutes: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Extend an active reservation's expiry.

    Raises:
        TaskNotFound: no reservation with task_id.
        TaskNotOwned: reservation belongs to a different agent.
        TaskAlreadyCompleted: reservation is already complete.
    """
    now = _now(now)
    reservation = _load_owned_active(storage, task_id=task_id, agent_id=agent_id)

    new_expires = now + timedelta(minutes=extend_minutes)
    storage.update(
        "reservations",
        "id",
        task_id,
        {"expires_at": new_expires.isoformat()},
    )
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "expires_at": new_expires.isoformat(),
        "extend_minutes": extend_minutes,
    }


def complete_reservation(
    storage: Storage,
    *,
    agent_id: str,
    task_id: str,
    proposal_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mark a reservation complete.

    Raises:
        TaskNotFound, TaskNotOwned, TaskAlreadyCompleted.

    Note: proposal_id is echoed back in the result but not persisted on the
    reservations row (no column exists for it). Preserves CLI behavior.
    """
    now = _now(now)
    reservation = _load_owned_active(storage, task_id=task_id, agent_id=agent_id)

    storage.update(
        "reservations",
        "id",
        task_id,
        {"completed_at": now.isoformat()},
    )
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    started = datetime.fromisoformat(reservation["started_at"])
    duration = (now - started).total_seconds()

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "task": reservation["task"],
        "proposal_id": proposal_id,
        "started_at": reservation["started_at"],
        "completed_at": now.isoformat(),
        "duration_seconds": duration,
    }


def list_reservations(
    storage: Storage,
    *,
    agent_id: str | None = None,
    active_only: bool = False,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """List reservations, optionally filtered by agent or activity."""
    now = _now(now)
    where = {"agent_id": agent_id} if agent_id else None
    rows = storage.query("reservations", where=where, order_by="started_at DESC")

    result: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_reservation(row, now=now)
        if active_only and item["status"] != "active":
            continue
        result.append(item)
    return result


def cancel_reservation(
    storage: Storage,
    *,
    agent_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Cancel a reservation, releasing its scope.

    Raises:
        TaskNotFound, TaskNotOwned, TaskAlreadyCompleted.
    """
    reservation = _load_owned_active(storage, task_id=task_id, agent_id=agent_id)
    scope = json.loads(reservation["scope_json"])
    storage.delete("reservations", "id", task_id)

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "scope_released": scope,
    }


def _load_owned_active(
    storage: Storage, *, task_id: str, agent_id: str
) -> Any:
    """Load a reservation, validating ownership and not-completed.

    Shared validation for heartbeat/complete/cancel.
    """
    reservation = storage.get_by_id("reservations", task_id)
    if not reservation:
        raise TaskNotFound(f"Task '{task_id}' not found")
    if reservation["agent_id"] != agent_id:
        raise TaskNotOwned(
            f"Task '{task_id}' is owned by '{reservation['agent_id']}', "
            f"not '{agent_id}'",
            owner_agent_id=reservation["agent_id"],
        )
    if reservation["completed_at"]:
        raise TaskAlreadyCompleted(f"Task '{task_id}' is already completed")
    return reservation
