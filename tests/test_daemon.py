"""Tests for the governor daemon — protocol, dispatcher, all 21 handlers."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from governor.daemon import (
    GOVERNOR_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    DaemonState,
    Dispatcher,
    default_socket_path,
    read_message,
    register_handlers,
    write_message,
)


# =============================================================================
# Helpers
# =============================================================================


def frame(msg: dict) -> bytes:
    """Create a Content-Length framed message."""
    body = json.dumps(msg).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def rpc_request(method: str, params: dict | None = None, id: int = 1) -> dict:
    """Build a JSON-RPC 2.0 request."""
    req = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        req["params"] = params
    return req


def rpc_notification(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 notification (no id)."""
    req = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        req["params"] = params
    return req


async def roundtrip(dispatcher: Dispatcher, method: str,
                    params: dict | None = None, id: int = 1) -> dict:
    """Send a request through the dispatcher and return the response."""
    request = rpc_request(method, params, id)
    return await dispatcher.dispatch(request)


@pytest.fixture
def tmp_gov_dir(tmp_path):
    """Create a temporary governor directory with minimal structure."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    (gov_dir / "sessions").mkdir()
    (gov_dir / "sessions" / "index.json").write_text(
        json.dumps({"sessions": {}, "mainline": None})
    )
    return gov_dir


@pytest.fixture
def state(tmp_gov_dir):
    """Create a DaemonState with temporary governor directory."""
    return DaemonState(tmp_gov_dir, mode="general")


@pytest.fixture
def dispatcher_and_state(state):
    """Create a Dispatcher with all handlers registered."""
    d = Dispatcher()
    register_handlers(d, state)
    return d, state


# =============================================================================
# Protocol: Content-Length framing
# =============================================================================


class TestContentLengthFraming:
    """Test Content-Length framed message reading/writing."""

    @pytest.mark.asyncio
    async def test_read_message_basic(self):
        """Read a simple JSON-RPC message."""
        msg = {"jsonrpc": "2.0", "method": "test", "id": 1}
        data = frame(msg)
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        result = await read_message(reader)
        assert result == msg

    @pytest.mark.asyncio
    async def test_read_message_eof(self):
        """Return None on EOF."""
        reader = asyncio.StreamReader()
        reader.feed_eof()
        result = await read_message(reader)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_message_no_content_length(self):
        """Return None when no Content-Length header."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"X-Custom: foo\r\n\r\n{}")
        reader.feed_eof()
        result = await read_message(reader)
        assert result is None

    @pytest.mark.asyncio
    async def test_write_message(self):
        """Write a framed message and verify format."""
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        writer = MagicMock()

        async def mock_drain():
            pass

        writer.drain = mock_drain
        written_data = bytearray()
        writer.write = lambda data: written_data.extend(data)

        await write_message(writer, msg)

        output = written_data.decode("utf-8")
        assert output.startswith("Content-Length: ")
        assert "\r\n\r\n" in output

        # Parse back
        _, _, body = output.partition("\r\n\r\n")
        parsed = json.loads(body)
        assert parsed == msg

    @pytest.mark.asyncio
    async def test_read_multiple_messages(self):
        """Read two consecutive framed messages."""
        msg1 = {"jsonrpc": "2.0", "method": "a", "id": 1}
        msg2 = {"jsonrpc": "2.0", "method": "b", "id": 2}
        reader = asyncio.StreamReader()
        reader.feed_data(frame(msg1) + frame(msg2))
        reader.feed_eof()

        r1 = await read_message(reader)
        r2 = await read_message(reader)
        assert r1 == msg1
        assert r2 == msg2

    @pytest.mark.asyncio
    async def test_read_message_with_unicode(self):
        """Handle unicode content correctly."""
        msg = {"jsonrpc": "2.0", "method": "test", "id": 1, "params": {"text": "caf\u00e9"}}
        data = frame(msg)
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        result = await read_message(reader)
        assert result["params"]["text"] == "caf\u00e9"


# =============================================================================
# Dispatcher: JSON-RPC 2.0 protocol
# =============================================================================


class TestDispatcher:
    """Test JSON-RPC 2.0 dispatcher logic."""

    @pytest.mark.asyncio
    async def test_dispatch_valid_request(self):
        async def echo(p):
            return p

        d = Dispatcher()
        d.register("echo", echo)
        resp = await d.dispatch(rpc_request("echo", {"hello": "world"}))
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_dispatch_method_not_found(self):
        d = Dispatcher()
        resp = await d.dispatch(rpc_request("nonexistent"))
        assert resp["error"]["code"] == METHOD_NOT_FOUND
        assert "nonexistent" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_dispatch_invalid_jsonrpc_version(self):
        d = Dispatcher()
        resp = await d.dispatch({"jsonrpc": "1.0", "method": "x", "id": 1})
        assert resp["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_dispatch_missing_method(self):
        d = Dispatcher()
        resp = await d.dispatch({"jsonrpc": "2.0", "id": 1})
        assert resp["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_dispatch_not_dict(self):
        d = Dispatcher()
        resp = await d.dispatch("not a dict")
        assert resp["error"]["code"] == PARSE_ERROR

    @pytest.mark.asyncio
    async def test_dispatch_handler_raises(self):
        async def bad_handler(params):
            raise RuntimeError("boom")

        d = Dispatcher()
        d.register("fail", bad_handler)
        resp = await d.dispatch(rpc_request("fail"))
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "boom" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_dispatch_handler_type_error(self):
        async def typed_handler(params):
            raise TypeError("bad param type")

        d = Dispatcher()
        d.register("typed", typed_handler)
        resp = await d.dispatch(rpc_request("typed"))
        assert resp["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_dispatch_notification_no_response(self):
        called = []
        async def handler(params):
            called.append(True)
            return {"ok": True}

        d = Dispatcher()
        d.register("notify_me", handler)
        resp = await d.dispatch(rpc_notification("notify_me"))
        assert resp is None
        assert called == [True]

    @pytest.mark.asyncio
    async def test_dispatch_notification_method_not_found(self):
        d = Dispatcher()
        resp = await d.dispatch(rpc_notification("nope"))
        assert resp is None  # Notifications don't get error responses

    @pytest.mark.asyncio
    async def test_dispatch_notification_handler_error(self):
        async def fail(params):
            raise RuntimeError("oops")
        d = Dispatcher()
        d.register("fail", fail)
        resp = await d.dispatch(rpc_notification("fail"))
        assert resp is None

    @pytest.mark.asyncio
    async def test_dispatch_preserves_id(self):
        async def echo(p):
            return {}

        d = Dispatcher()
        d.register("echo", echo)
        resp = await d.dispatch(rpc_request("echo", id=42))
        assert resp["id"] == 42

    @pytest.mark.asyncio
    async def test_dispatch_string_id(self):
        async def echo(p):
            return {}

        d = Dispatcher()
        d.register("echo", echo)
        req = {"jsonrpc": "2.0", "method": "echo", "id": "abc-123", "params": {}}
        resp = await d.dispatch(req)
        assert resp["id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_dispatch_null_id(self):
        async def echo(p):
            return {}

        d = Dispatcher()
        d.register("echo", echo)
        req = {"jsonrpc": "2.0", "method": "echo", "id": None, "params": {}}
        resp = await d.dispatch(req)
        assert resp["id"] is None
        assert "result" in resp

    @pytest.mark.asyncio
    async def test_dispatch_non_dict_params(self):
        """Non-dict params should be coerced to empty dict."""
        async def echo(p):
            return p

        d = Dispatcher()
        d.register("echo", echo)
        req = {"jsonrpc": "2.0", "method": "echo", "id": 1, "params": [1, 2, 3]}
        resp = await d.dispatch(req)
        assert resp["result"] == {}


# =============================================================================
# DaemonState
# =============================================================================


class TestDaemonState:
    """Test lazy initialization of governor subsystems."""

    def test_init(self, tmp_gov_dir):
        state = DaemonState(tmp_gov_dir, mode="fiction")
        assert state.governor_dir == tmp_gov_dir
        assert state.mode == "fiction"
        assert state.root == tmp_gov_dir.parent

    def test_session_store_lazy(self, state):
        assert state._session_store is None
        store = state.session_store
        assert store is not None
        assert state.session_store is store  # Same instance

    def test_receipt_system_lazy(self, state):
        assert state._receipt_system is None
        sys = state.receipt_system
        assert sys is not None
        assert state.receipt_system is sys

    def test_scar_ledger_lazy_no_file(self, state):
        """When no scars.json, create empty ledger."""
        assert state._scar_ledger is None
        ledger = state.scar_ledger
        assert ledger is not None
        assert len(ledger.get_active_scars()) == 0

    def test_scar_ledger_lazy_with_file(self, tmp_gov_dir):
        """When scars.json exists, load from it."""
        from governor.scars import ScarLedger, Scar
        ledger = ScarLedger()
        ledger.record_failure("test_region", observation_shift=0.1,
                              prediction_error=0.3, description="test")
        scar_path = tmp_gov_dir / "scars.json"
        scar_path.write_text(json.dumps(ledger.to_dict()))

        state = DaemonState(tmp_gov_dir)
        loaded = state.scar_ledger
        assert loaded.total_failures == 1

    def test_violation_resolver_lazy(self, state):
        assert state._violation_resolver is None
        resolver = state.violation_resolver
        assert resolver is not None
        assert state.violation_resolver is resolver


# =============================================================================
# Handler: governor.hello
# =============================================================================


class TestGovernorHello:

    @pytest.mark.asyncio
    async def test_hello_returns_protocol_version(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        result = resp["result"]
        assert result["protocol_version"] == PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_hello_capabilities(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        caps = resp["result"]["capabilities"]
        assert caps["fix_mode"] == "candidate_only"
        assert caps["sessions"] is True
        assert caps["intent"] is True

    @pytest.mark.asyncio
    async def test_hello_governor_info(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        gov = resp["result"]["governor"]
        assert gov["mode"] == "general"
        assert gov["initialized"] is True  # tmp_gov_dir exists


# =============================================================================
# Handler: governor.now
# =============================================================================


class TestGovernorNow:

    @pytest.mark.asyncio
    async def test_now_returns_pill_and_sentence(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.now")
        result = resp["result"]
        assert "pill" in result
        assert "sentence" in result

    @pytest.mark.asyncio
    async def test_now_graceful_on_missing_state(self, tmp_path):
        """When governor dir is empty, still returns something."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        state = DaemonState(gov_dir)
        d = Dispatcher()
        register_handlers(d, state)
        resp = await roundtrip(d, "governor.now")
        assert "pill" in resp["result"]


# =============================================================================
# Handler: governor.status
# =============================================================================


class TestGovernorStatus:

    @pytest.mark.asyncio
    async def test_status_fields(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.status")
        result = resp["result"]
        assert "mode" in result
        assert result["mode"] == "general"


# =============================================================================
# Handler: sessions.*
# =============================================================================


class TestSessions:

    @pytest.mark.asyncio
    async def test_list_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "sessions.list")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_create_and_list(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Create
        resp = await roundtrip(d, "sessions.create", {"title": "Test Session"})
        assert "metadata" in resp["result"]
        session_id = resp["result"]["metadata"]["session_id"]

        # List
        resp = await roundtrip(d, "sessions.list", id=2)
        assert len(resp["result"]) == 1

    @pytest.mark.asyncio
    async def test_get_session(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Create first
        resp = await roundtrip(d, "sessions.create", {"title": "Fetch Me"})
        session_id = resp["result"]["metadata"]["session_id"]

        # Get
        resp = await roundtrip(d, "sessions.get", {"id": session_id}, id=2)
        assert resp["result"]["metadata"]["name"] == "Fetch Me"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "sessions.get", {"id": "nonexistent"})
        assert resp["result"] is None

    @pytest.mark.asyncio
    async def test_delete_session(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Create
        resp = await roundtrip(d, "sessions.create", {"title": "Delete Me"})
        session_id = resp["result"]["metadata"]["session_id"]

        # Delete
        resp = await roundtrip(d, "sessions.delete", {"id": session_id}, id=2)
        assert resp["result"]["success"] is True

        # Verify gone
        resp = await roundtrip(d, "sessions.list", id=3)
        assert len(resp["result"]) == 0

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "sessions.delete", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_get_missing_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "sessions.get", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR


# =============================================================================
# Handler: intent.*
# =============================================================================


class TestIntent:

    @pytest.mark.asyncio
    async def test_templates(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "intent.templates")
        result = resp["result"]
        assert "templates" in result
        names = [t["name"] for t in result["templates"]]
        assert "session_start" in names

    @pytest.mark.asyncio
    async def test_schema(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "intent.schema", {"template_name": "session_start"})
        result = resp["result"]
        assert "schema_id" in result
        assert result["template_name"] == "session_start"
        assert "fields" in result

    @pytest.mark.asyncio
    async def test_schema_missing_template(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "intent.schema", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_policy(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "intent.policy")
        result = resp["result"]
        assert result["mode"] == "general"
        assert "policy" in result

    @pytest.mark.asyncio
    async def test_validate_with_values(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Get schema first
        schema_resp = await roundtrip(d, "intent.schema",
                                       {"template_name": "session_start"})
        schema_id = schema_resp["result"]["schema_id"]

        # Validate (empty values should produce errors for required fields)
        resp = await roundtrip(d, "intent.validate",
                               {"schema_id": schema_id, "values": {},
                                "template_name": "session_start"}, id=2)
        result = resp["result"]
        assert "valid" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_compile(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Get schema
        schema_resp = await roundtrip(d, "intent.schema",
                                       {"template_name": "session_start"})
        schema = schema_resp["result"]

        # Build values from defaults
        values = {}
        for field in schema.get("fields", []):
            if field.get("default") is not None:
                values[field["field_id"]] = field["default"]
            elif field.get("options"):
                values[field["field_id"]] = field["options"][0]["value"]

        resp = await roundtrip(d, "intent.compile",
                               {"schema_id": schema["schema_id"],
                                "values": values,
                                "template_name": "session_start"}, id=2)
        result = resp["result"]
        assert "intent_profile" in result
        assert "receipt_hash" in result


# =============================================================================
# Handler: receipts.*
# =============================================================================


class TestReceipts:

    @pytest.mark.asyncio
    async def test_list_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts.list")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_list_with_receipt(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        # Emit a receipt directly
        state.receipt_system.emit(
            gate="test_gate",
            verdict="pass",
            subject_kind="test",
            subject_bytes=b"test content",
            evidence_bundle={"data": "test"},
            gate_config={"threshold": 0.5},
        )
        resp = await roundtrip(d, "receipts.list")
        assert len(resp["result"]) == 1
        assert resp["result"][0]["gate"] == "test_gate"

    @pytest.mark.asyncio
    async def test_list_with_filter(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        state.receipt_system.emit(
            gate="a", verdict="pass", subject_kind="t",
            subject_bytes=b"1", evidence_bundle={}, gate_config={},
        )
        state.receipt_system.emit(
            gate="b", verdict="block", subject_kind="t",
            subject_bytes=b"2", evidence_bundle={}, gate_config={},
        )

        resp = await roundtrip(d, "receipts.list", {"verdict": "block"})
        assert len(resp["result"]) == 1
        assert resp["result"][0]["gate"] == "b"

    @pytest.mark.asyncio
    async def test_detail(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        receipt = state.receipt_system.emit(
            gate="test", verdict="pass", subject_kind="t",
            subject_bytes=b"x", evidence_bundle={"key": "val"}, gate_config={},
        )
        resp = await roundtrip(d, "receipts.detail",
                               {"receipt_id": receipt.receipt_id})
        assert resp["result"]["receipt"]["receipt_id"] == receipt.receipt_id
        assert resp["result"]["evidence"] is not None

    @pytest.mark.asyncio
    async def test_detail_not_found(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts.detail", {"receipt_id": "nonexistent"})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_detail_missing_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts.detail", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR


# =============================================================================
# Handler: scars.*
# =============================================================================


class TestScars:

    @pytest.mark.asyncio
    async def test_list_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "scars.list")
        result = resp["result"]
        assert "scars" in result
        assert "shields" in result
        assert "stats" in result
        assert result["scars"] == []

    @pytest.mark.asyncio
    async def test_list_with_scars(self, tmp_gov_dir):
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        # Low surprise ratio (obs/pred < rho_lo) → INTERNAL → scar
        ledger.record_failure("src/bad.py", observation_shift=0.1,
                              prediction_error=1.0, description="test failure")
        (tmp_gov_dir / "scars.json").write_text(json.dumps(ledger.to_dict()))

        state = DaemonState(tmp_gov_dir)
        d = Dispatcher()
        register_handlers(d, state)

        resp = await roundtrip(d, "scars.list")
        assert len(resp["result"]["scars"]) >= 1

    @pytest.mark.asyncio
    async def test_history_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "scars.history")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_history_with_events(self, tmp_gov_dir):
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        ledger.record_failure("r1", description="first")
        ledger.record_failure("r2", description="second")
        (tmp_gov_dir / "scars.json").write_text(json.dumps(ledger.to_dict()))

        state = DaemonState(tmp_gov_dir)
        d = Dispatcher()
        register_handlers(d, state)

        resp = await roundtrip(d, "scars.history", {"limit": 1})
        assert len(resp["result"]) == 1

    @pytest.mark.asyncio
    async def test_history_with_limit(self, tmp_gov_dir):
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        for i in range(10):
            ledger.record_failure(f"r{i}", description=f"fail {i}")
        (tmp_gov_dir / "scars.json").write_text(json.dumps(ledger.to_dict()))

        state = DaemonState(tmp_gov_dir)
        d = Dispatcher()
        register_handlers(d, state)

        resp = await roundtrip(d, "scars.history", {"limit": 3})
        assert len(resp["result"]) == 3


# =============================================================================
# Handler: commit.*
# =============================================================================


class TestCommit:

    @pytest.mark.asyncio
    async def test_pending_none(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.pending")
        assert resp["result"] is None

    @pytest.mark.asyncio
    async def test_fix_no_pending(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.fix", {"corrected_text": "hello"})
        assert resp["result"]["success"] is False
        assert "No pending" in resp["result"]["message"]

    @pytest.mark.asyncio
    async def test_fix_missing_text(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.fix", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_revise_no_pending(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.revise")
        assert resp["result"]["success"] is False

    @pytest.mark.asyncio
    async def test_proceed_no_pending(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.proceed", {"reason": "testing"})
        assert resp["result"]["success"] is False

    @pytest.mark.asyncio
    async def test_exceptions_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "commit.exceptions")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_pending_with_violation(self, dispatcher_and_state):
        """Create a pending violation and verify it's returned."""
        d, state = dispatcher_and_state
        resolver = state.violation_resolver

        # Create a pending violation manually
        resolver.create_pending(
            violations=[{"anchor_id": "a1", "description": "test violation"}],
            blocked_response="bad response",
            run_id="run_1",
        )

        resp = await roundtrip(d, "commit.pending")
        result = resp["result"]
        assert result is not None
        assert result["blocked_response"] == "bad response"

    @pytest.mark.asyncio
    async def test_proceed_with_violation(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        resolver = state.violation_resolver

        resolver.create_pending(
            violations=[{"anchor_id": "a1", "description": "test"}],
            blocked_response="bad",
            run_id="run_1",
        )

        resp = await roundtrip(d, "commit.proceed", {"reason": "needed"})
        result = resp["result"]
        assert result["success"] is True
        assert result["action"] == "proceed"

        # Should now have an exception
        resp = await roundtrip(d, "commit.exceptions", id=2)
        assert len(resp["result"]) == 1

    @pytest.mark.asyncio
    async def test_revise_with_violation(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        resolver = state.violation_resolver

        resolver.create_pending(
            violations=[{"anchor_id": "a1", "description": "test"}],
            blocked_response="original",
            run_id="run_1",
        )

        resp = await roundtrip(d, "commit.revise", {"new_anchor_text": "updated"})
        result = resp["result"]
        assert result["success"] is True
        assert result["action"] == "revise"


# =============================================================================
# default_socket_path
# =============================================================================


class TestDefaultSocketPath:

    def test_uses_xdg_runtime_dir(self, tmp_path):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(tmp_path)}):
            gov_dir = Path("/home/user/project/.governor")
            path = default_socket_path(gov_dir)
            assert str(path).startswith(str(tmp_path))
            assert path.name.startswith("governor-")
            assert path.suffix == ".sock"

    def test_deterministic(self, tmp_path):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(tmp_path)}):
            gov_dir = Path("/home/user/project/.governor")
            p1 = default_socket_path(gov_dir)
            p2 = default_socket_path(gov_dir)
            assert p1 == p2

    def test_different_dirs_different_paths(self, tmp_path):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(tmp_path)}):
            p1 = default_socket_path(Path("/a/.governor"))
            p2 = default_socket_path(Path("/b/.governor"))
            assert p1 != p2

    def test_fallback_to_tmp(self):
        env = os.environ.copy()
        env.pop("XDG_RUNTIME_DIR", None)
        with patch.dict(os.environ, env, clear=True):
            path = default_socket_path(Path("/project/.governor"))
            assert str(path).startswith("/tmp")


# =============================================================================
# All 21 methods registered
# =============================================================================


class TestAllMethodsRegistered:

    EXPECTED_METHODS = [
        "governor.hello",
        "governor.now",
        "governor.status",
        "sessions.list",
        "sessions.create",
        "sessions.delete",
        "sessions.get",
        "intent.templates",
        "intent.schema",
        "intent.validate",
        "intent.compile",
        "intent.policy",
        "receipts.list",
        "receipts.detail",
        "scars.list",
        "scars.history",
        "commit.pending",
        "commit.fix",
        "commit.revise",
        "commit.proceed",
        "commit.exceptions",
    ]

    def test_all_registered(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        for method in self.EXPECTED_METHODS:
            assert method in d._handlers, f"Missing handler: {method}"

    def test_exactly_21_methods(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        assert len(d._handlers) == 21

    @pytest.mark.asyncio
    async def test_all_methods_callable(self, dispatcher_and_state):
        """Every registered method should return a response (not crash)."""
        d, _ = dispatcher_and_state
        for i, method in enumerate(self.EXPECTED_METHODS):
            resp = await d.dispatch(rpc_request(method, {}, id=i))
            # Should get either a result or a governor error (missing params etc)
            # but NOT a method-not-found or parse error
            if "error" in resp:
                assert resp["error"]["code"] != METHOD_NOT_FOUND, (
                    f"{method} returned method-not-found"
                )


# =============================================================================
# Integration: framing + dispatcher
# =============================================================================


class TestEndToEnd:

    @pytest.mark.asyncio
    async def test_frame_dispatch_roundtrip(self, dispatcher_and_state):
        """Frame a request, read it, dispatch, write response, read response."""
        d, _ = dispatcher_and_state

        # Create framed request
        req = rpc_request("governor.hello")
        data = frame(req)

        # Read
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        msg = await read_message(reader)

        # Dispatch
        resp = await d.dispatch(msg)
        assert resp["result"]["protocol_version"] == PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_multiple_requests(self, dispatcher_and_state):
        """Multiple sequential requests work correctly."""
        d, _ = dispatcher_and_state

        r1 = await roundtrip(d, "governor.hello", id=1)
        r2 = await roundtrip(d, "governor.now", id=2)
        r3 = await roundtrip(d, "sessions.list", id=3)

        assert r1["id"] == 1
        assert r2["id"] == 2
        assert r3["id"] == 3
        assert "protocol_version" in r1["result"]
        assert "pill" in r2["result"]
        assert isinstance(r3["result"], list)
