# SPDX-License-Identifier: Apache-2.0
"""Unit tests for governor.reservations — extracted work-reservation primitives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from governor.permissions import PermissionManager
from governor.reservations import (
    AgentNotRegistered,
    PermissionDenied,
    ScopeConflict,
    TaskAlreadyCompleted,
    TaskNotFound,
    TaskNotOwned,
    cancel_reservation,
    claim_reservation,
    complete_reservation,
    heartbeat_reservation,
    list_reservations,
)
from governor.storage import get_storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gov_dir(tmp_path):
    """Fresh governor dir with empty storage (schema auto-created)."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


@pytest.fixture
def storage(gov_dir):
    """SQLite storage with multi-agent v2 schema initialized."""
    return get_storage(gov_dir)


@pytest.fixture
def perm_manager(gov_dir):
    """Default permission manager — allows all paths."""
    return PermissionManager(gov_dir)


@pytest.fixture
def fixed_now():
    """Stable timestamp for deterministic tests."""
    return datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


def _register_agent(storage, agent_id: str, *, when: datetime) -> None:
    storage.insert(
        "agents",
        {
            "id": agent_id,
            "agent_class": "default",
            "capabilities_json": "[]",
            "registered_at": when.isoformat(),
            "last_heartbeat": when.isoformat(),
            "permissions_json": "{}",
        },
    )


# ---------------------------------------------------------------------------
# claim_reservation
# ---------------------------------------------------------------------------


class TestClaimReservation:
    def test_claims_for_registered_agent(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)

        result = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="implement endpoint",
            scope_paths=["src/api.py"],
            now=fixed_now,
        )

        assert result["agent_id"] == "worker-1"
        assert result["task"] == "implement endpoint"
        assert result["scope"] == ["src/api.py"]
        assert result["eta_minutes"] == 30
        assert result["started_at"] == fixed_now.isoformat()
        expected_expires = fixed_now + timedelta(minutes=30)
        assert result["expires_at"] == expected_expires.isoformat()
        assert result["task_id"]

    def test_unknown_agent_raises(self, storage, perm_manager, fixed_now):
        with pytest.raises(AgentNotRegistered):
            claim_reservation(
                storage,
                perm_manager,
                agent_id="ghost",
                task="x",
                scope_paths=["src/a.py"],
                now=fixed_now,
            )

    def test_overlapping_scope_raises(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)

        first = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="first",
            scope_paths=["src/a.py", "src/b.py"],
            now=fixed_now,
        )

        with pytest.raises(ScopeConflict) as exc_info:
            claim_reservation(
                storage,
                perm_manager,
                agent_id="worker-2",
                task="second",
                scope_paths=["src/b.py", "src/c.py"],
                now=fixed_now,
            )

        err = exc_info.value
        assert err.conflicting_task_id == first["task_id"]
        assert err.conflicting_agent_id == "worker-1"
        assert err.overlap == ["src/b.py"]

    def test_expired_reservation_does_not_block(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)

        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="first",
            scope_paths=["src/a.py"],
            eta_minutes=10,
            now=fixed_now,
        )

        # Time passes — first reservation is now expired
        later = fixed_now + timedelta(minutes=20)
        result = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-2",
            task="second",
            scope_paths=["src/a.py"],
            now=later,
        )
        assert result["agent_id"] == "worker-2"

    def test_completed_reservation_does_not_block(
        self, storage, perm_manager, fixed_now
    ):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)

        first = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="first",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        complete_reservation(
            storage,
            agent_id="worker-1",
            task_id=first["task_id"],
            now=fixed_now + timedelta(minutes=1),
        )

        result = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-2",
            task="second",
            scope_paths=["src/a.py"],
            now=fixed_now + timedelta(minutes=2),
        )
        assert result["agent_id"] == "worker-2"


# ---------------------------------------------------------------------------
# heartbeat_reservation
# ---------------------------------------------------------------------------


class TestHeartbeatReservation:
    def test_extends_expiry(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            eta_minutes=10,
            now=fixed_now,
        )

        later = fixed_now + timedelta(minutes=5)
        result = heartbeat_reservation(
            storage,
            agent_id="worker-1",
            task_id=claim["task_id"],
            extend_minutes=20,
            now=later,
        )

        expected = later + timedelta(minutes=20)
        assert result["expires_at"] == expected.isoformat()

    def test_unknown_task_raises(self, storage, fixed_now):
        with pytest.raises(TaskNotFound):
            heartbeat_reservation(
                storage,
                agent_id="worker-1",
                task_id="missing",
                now=fixed_now,
            )

    def test_wrong_owner_raises(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )

        with pytest.raises(TaskNotOwned) as exc_info:
            heartbeat_reservation(
                storage,
                agent_id="worker-2",
                task_id=claim["task_id"],
                now=fixed_now,
            )
        assert exc_info.value.owner_agent_id == "worker-1"

    def test_completed_task_raises(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        complete_reservation(
            storage,
            agent_id="worker-1",
            task_id=claim["task_id"],
            now=fixed_now + timedelta(minutes=1),
        )

        with pytest.raises(TaskAlreadyCompleted):
            heartbeat_reservation(
                storage,
                agent_id="worker-1",
                task_id=claim["task_id"],
                now=fixed_now + timedelta(minutes=2),
            )


# ---------------------------------------------------------------------------
# complete_reservation
# ---------------------------------------------------------------------------


class TestCompleteReservation:
    def test_marks_complete_with_duration(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )

        completed_at = fixed_now + timedelta(minutes=15)
        result = complete_reservation(
            storage,
            agent_id="worker-1",
            task_id=claim["task_id"],
            proposal_id="prop-42",
            now=completed_at,
        )

        assert result["task_id"] == claim["task_id"]
        assert result["completed_at"] == completed_at.isoformat()
        assert result["duration_seconds"] == 15 * 60
        assert result["proposal_id"] == "prop-42"

    def test_proposal_id_optional(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        result = complete_reservation(
            storage,
            agent_id="worker-1",
            task_id=claim["task_id"],
            now=fixed_now,
        )
        assert result["proposal_id"] is None


# ---------------------------------------------------------------------------
# list_reservations
# ---------------------------------------------------------------------------


class TestListReservations:
    def test_empty_returns_empty_list(self, storage, fixed_now):
        assert list_reservations(storage, now=fixed_now) == []

    def test_returns_status_active(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        items = list_reservations(storage, now=fixed_now)
        assert len(items) == 1
        assert items[0]["status"] == "active"

    def test_returns_status_expired(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            eta_minutes=5,
            now=fixed_now,
        )
        items = list_reservations(
            storage,
            now=fixed_now + timedelta(minutes=10),
        )
        assert items[0]["status"] == "expired"

    def test_returns_status_completed(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        complete_reservation(
            storage,
            agent_id="worker-1",
            task_id=claim["task_id"],
            now=fixed_now + timedelta(minutes=1),
        )
        items = list_reservations(storage, now=fixed_now + timedelta(minutes=2))
        assert items[0]["status"] == "completed"

    def test_active_only_filters(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        # Active
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="active-task",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        # Expired
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="expired-task",
            scope_paths=["src/b.py"],
            eta_minutes=5,
            now=fixed_now,
        )

        items = list_reservations(
            storage,
            active_only=True,
            now=fixed_now + timedelta(minutes=10),
        )
        assert len(items) == 1
        assert items[0]["task"] == "active-task"

    def test_filter_by_agent(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="one",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-2",
            task="two",
            scope_paths=["src/b.py"],
            now=fixed_now,
        )

        items = list_reservations(storage, agent_id="worker-1", now=fixed_now)
        assert len(items) == 1
        assert items[0]["task"] == "one"


# ---------------------------------------------------------------------------
# cancel_reservation
# ---------------------------------------------------------------------------


class TestCancelReservation:
    def test_removes_reservation_and_returns_scope(
        self, storage, perm_manager, fixed_now
    ):
        _register_agent(storage, "worker-1", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py", "src/b.py"],
            now=fixed_now,
        )

        result = cancel_reservation(
            storage, agent_id="worker-1", task_id=claim["task_id"]
        )
        assert sorted(result["scope_released"]) == ["src/a.py", "src/b.py"]
        # Scope is now free for another agent
        _register_agent(storage, "worker-2", when=fixed_now)
        new_claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-2",
            task="reuse",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        assert new_claim["agent_id"] == "worker-2"

    def test_unknown_task_raises(self, storage):
        with pytest.raises(TaskNotFound):
            cancel_reservation(storage, agent_id="worker-1", task_id="missing")

    def test_wrong_owner_raises(self, storage, perm_manager, fixed_now):
        _register_agent(storage, "worker-1", when=fixed_now)
        _register_agent(storage, "worker-2", when=fixed_now)
        claim = claim_reservation(
            storage,
            perm_manager,
            agent_id="worker-1",
            task="x",
            scope_paths=["src/a.py"],
            now=fixed_now,
        )
        with pytest.raises(TaskNotOwned):
            cancel_reservation(
                storage, agent_id="worker-2", task_id=claim["task_id"]
            )
