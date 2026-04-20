# SPDX-License-Identifier: Apache-2.0
"""Daemon RPC integration tests for task.* methods.

End-to-end coverage: dispatcher receives a JSON-RPC request, the handler
runs against a real temp Storage, and the response (success or typed
error) is returned. Verifies the daemon RPC surface mirrors CLI semantics.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from governor.daemon import (
    GOVERNOR_ERROR,
    INVALID_PARAMS,
    DaemonState,
    Dispatcher,
    register_handlers,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def rpc_request(method: str, params: dict | None = None, id: int = 1) -> dict:
    req = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        req["params"] = params
    return req


async def call(dispatcher: Dispatcher, method: str, params: dict | None = None):
    return await dispatcher.dispatch(rpc_request(method, params))


@pytest.fixture
def gov_dir(tmp_path):
    d = tmp_path / ".governor"
    d.mkdir()
    return d


@pytest.fixture
def state(gov_dir):
    return DaemonState(gov_dir, mode="general")


@pytest.fixture
def dispatcher(state):
    d = Dispatcher()
    register_handlers(d, state)
    return d


def _register_agent(state: DaemonState, agent_id: str) -> None:
    """Insert an agent directly via storage (bypasses CLI)."""
    now = datetime.now(timezone.utc).isoformat()
    state.storage.insert(
        "agents",
        {
            "id": agent_id,
            "agent_class": "default",
            "capabilities_json": "[]",
            "registered_at": now,
            "last_heartbeat": now,
            "permissions_json": "{}",
        },
    )


# ---------------------------------------------------------------------------
# task.claim
# ---------------------------------------------------------------------------


class TestTaskClaimRpc:
    @pytest.mark.asyncio
    async def test_claims_with_string_scope(self, dispatcher, state):
        _register_agent(state, "worker-1")

        resp = await call(
            dispatcher,
            "task.claim",
            {
                "agent_id": "worker-1",
                "task": "implement endpoint",
                "scope": "src/api.py,tests/test_api.py",
            },
        )

        assert "result" in resp
        result = resp["result"]
        assert result["agent_id"] == "worker-1"
        assert result["scope"] == ["src/api.py", "tests/test_api.py"]
        assert result["task_id"]

    @pytest.mark.asyncio
    async def test_claims_with_list_scope(self, dispatcher, state):
        _register_agent(state, "worker-1")
        resp = await call(
            dispatcher,
            "task.claim",
            {
                "agent_id": "worker-1",
                "task": "x",
                "scope": ["src/a.py", "src/b.py"],
            },
        )
        assert resp["result"]["scope"] == ["src/a.py", "src/b.py"]

    @pytest.mark.asyncio
    async def test_missing_agent_id_returns_error(self, dispatcher):
        # Convention (matches sessions.delete): ValueError → GOVERNOR_ERROR.
        # Only TypeError (signature mismatch) becomes INVALID_PARAMS.
        resp = await call(
            dispatcher,
            "task.claim",
            {"task": "x", "scope": "src/a.py"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "agent_id" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_missing_task_returns_error(self, dispatcher):
        resp = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "x", "scope": "src/a.py"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "task" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_missing_scope_returns_error(self, dispatcher):
        resp = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "x", "task": "y"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "scope" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_invalid_scope_type_returns_invalid_params(self, dispatcher):
        # TypeError (genuine signature/type error) becomes INVALID_PARAMS.
        resp = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "x", "task": "y", "scope": 42},
        )
        assert resp["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_governor_error(self, dispatcher):
        resp = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "ghost", "task": "x", "scope": "src/a.py"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "not registered" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_scope_conflict_returns_governor_error(self, dispatcher, state):
        _register_agent(state, "worker-1")
        _register_agent(state, "worker-2")
        await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "first", "scope": "src/a.py"},
        )
        resp = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-2", "task": "second", "scope": "src/a.py"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "conflict" in resp["error"]["message"].lower()


# ---------------------------------------------------------------------------
# task.heartbeat / task.complete / task.cancel
# ---------------------------------------------------------------------------


class TestTaskLifecycleRpc:
    @pytest.mark.asyncio
    async def test_heartbeat_extends_expiry(self, dispatcher, state):
        _register_agent(state, "worker-1")
        claim = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        task_id = claim["result"]["task_id"]
        original_expiry = claim["result"]["expires_at"]

        resp = await call(
            dispatcher,
            "task.heartbeat",
            {"agent_id": "worker-1", "task_id": task_id, "extend_minutes": 60},
        )
        assert "result" in resp
        # New expiry is later than original (clock-walltime, not deterministic
        # but must increase)
        assert resp["result"]["expires_at"] >= original_expiry

    @pytest.mark.asyncio
    async def test_complete_marks_done(self, dispatcher, state):
        _register_agent(state, "worker-1")
        claim = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        task_id = claim["result"]["task_id"]

        resp = await call(
            dispatcher,
            "task.complete",
            {"agent_id": "worker-1", "task_id": task_id, "proposal_id": "p-1"},
        )
        assert resp["result"]["completed_at"]
        assert resp["result"]["proposal_id"] == "p-1"
        assert resp["result"]["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_cancel_removes_reservation(self, dispatcher, state):
        _register_agent(state, "worker-1")
        claim = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        task_id = claim["result"]["task_id"]

        resp = await call(
            dispatcher,
            "task.cancel",
            {"agent_id": "worker-1", "task_id": task_id},
        )
        assert resp["result"]["scope_released"] == ["src/a.py"]

        # Listing now shows zero
        listing = await call(dispatcher, "task.list", {})
        assert listing["result"] == []

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_task_returns_error(self, dispatcher):
        resp = await call(
            dispatcher,
            "task.heartbeat",
            {"agent_id": "worker-1", "task_id": "missing"},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "not found" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_complete_wrong_owner_returns_error(self, dispatcher, state):
        _register_agent(state, "worker-1")
        _register_agent(state, "worker-2")
        claim = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        resp = await call(
            dispatcher,
            "task.complete",
            {"agent_id": "worker-2", "task_id": claim["result"]["task_id"]},
        )
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "owned by" in resp["error"]["message"]


# ---------------------------------------------------------------------------
# task.list
# ---------------------------------------------------------------------------


class TestTaskListRpc:
    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self, dispatcher):
        resp = await call(dispatcher, "task.list", {})
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_returns_active_after_claim(self, dispatcher, state):
        _register_agent(state, "worker-1")
        await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        resp = await call(dispatcher, "task.list", {})
        assert len(resp["result"]) == 1
        assert resp["result"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_filter_by_agent(self, dispatcher, state):
        _register_agent(state, "worker-1")
        _register_agent(state, "worker-2")
        await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "one", "scope": "src/a.py"},
        )
        await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-2", "task": "two", "scope": "src/b.py"},
        )
        resp = await call(dispatcher, "task.list", {"agent_id": "worker-1"})
        tasks = [item["task"] for item in resp["result"]]
        assert tasks == ["one"]

    @pytest.mark.asyncio
    async def test_active_only_filters_completed(self, dispatcher, state):
        _register_agent(state, "worker-1")
        first = await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "first", "scope": "src/a.py"},
        )
        await call(
            dispatcher,
            "task.claim",
            {"agent_id": "worker-1", "task": "second", "scope": "src/b.py"},
        )
        await call(
            dispatcher,
            "task.complete",
            {"agent_id": "worker-1", "task_id": first["result"]["task_id"]},
        )

        resp = await call(dispatcher, "task.list", {"active_only": True})
        tasks = [item["task"] for item in resp["result"]]
        assert tasks == ["second"]


# ---------------------------------------------------------------------------
# Mutating-flag enforcement
# ---------------------------------------------------------------------------


class TestMutatingFlags:
    """task.* mutating verbs should be blocked when dispatcher disallows mutation."""

    @pytest.mark.asyncio
    async def test_claim_blocked_by_readonly_dispatcher(self, state):
        readonly = Dispatcher(allow_mutating=False)
        register_handlers(readonly, state)
        _register_agent(state, "worker-1")

        resp = await call(
            readonly,
            "task.claim",
            {"agent_id": "worker-1", "task": "x", "scope": "src/a.py"},
        )
        # Must be an auth error — dispatcher refuses mutating call
        assert resp["error"]["code"] != 0
        assert "mutating" in resp["error"]["message"].lower() or \
               "blocked" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_list_allowed_on_readonly_dispatcher(self, state):
        readonly = Dispatcher(allow_mutating=False)
        register_handlers(readonly, state)

        resp = await call(readonly, "task.list", {})
        assert "result" in resp
