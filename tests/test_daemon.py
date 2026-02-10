"""Tests for the governor daemon — protocol, dispatcher, all 25 handlers."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    _emit_chat_receipt,
    default_socket_path,
    detect_backend,
    load_daemon_config,
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
        "chat.send",
        "chat.models",
        "chat.backend",
    ]

    EXPECTED_STREAMING_METHODS = [
        "chat.stream",
    ]

    def test_all_registered(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        for method in self.EXPECTED_METHODS:
            assert method in d._handlers, f"Missing handler: {method}"
        for method in self.EXPECTED_STREAMING_METHODS:
            assert method in d._streaming_handlers, f"Missing streaming handler: {method}"

    def test_exactly_25_methods(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        total = len(d._handlers) + len(d._streaming_handlers)
        assert total == 25

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


# =============================================================================
# Config file loading
# =============================================================================


class TestLoadDaemonConfig:

    def test_no_config_file(self, tmp_path):
        result = load_daemon_config(tmp_path)
        assert result == {}

    def test_basic_config(self, tmp_path):
        conf = tmp_path / "daemon.conf"
        conf.write_text("[backend]\ntype = anthropic\nmodel = sonnet\n")
        result = load_daemon_config(tmp_path)
        assert result["backend.type"] == "anthropic"
        assert result["backend.model"] == "sonnet"

    def test_nested_sections(self, tmp_path):
        conf = tmp_path / "daemon.conf"
        conf.write_text(
            "[backend.anthropic]\n"
            "api_key = sk-test\n"
            "[backend.ollama]\n"
            "url = http://myhost:11434\n"
            "[daemon]\n"
            "mode = fiction\n"
        )
        result = load_daemon_config(tmp_path)
        assert result["backend.anthropic.api_key"] == "sk-test"
        assert result["backend.ollama.url"] == "http://myhost:11434"
        assert result["daemon.mode"] == "fiction"

    def test_malformed_config(self, tmp_path):
        conf = tmp_path / "daemon.conf"
        conf.write_text("this is not valid ini\n\x00\x01")
        result = load_daemon_config(tmp_path)
        # Should not crash, just return partial or empty
        assert isinstance(result, dict)


# =============================================================================
# Backend auto-detection
# =============================================================================


class TestDetectBackend:

    def test_explicit_backend_type_env(self):
        with patch.dict(os.environ, {"BACKEND_TYPE": "anthropic",
                                     "ANTHROPIC_API_KEY": "sk-x"}):
            bt, kwargs = detect_backend()
            assert bt == "anthropic"
            assert kwargs["api_key"] == "sk-x"

    def test_explicit_ollama_type(self):
        with patch.dict(os.environ, {"BACKEND_TYPE": "ollama"}, clear=False):
            bt, kwargs = detect_backend()
            assert bt == "ollama"
            assert "host" in kwargs

    def test_config_file_fallback(self):
        config = {"backend.type": "codex"}
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            bt, kwargs = detect_backend(config)
            assert bt == "codex"

    def test_auto_detect_anthropic_key(self):
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env["ANTHROPIC_API_KEY"] = "sk-ant-test"
        with patch.dict(os.environ, env, clear=True):
            bt, kwargs = detect_backend()
            assert bt == "anthropic"
            assert kwargs["api_key"] == "sk-ant-test"

    def test_auto_detect_claude_cli(self):
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("shutil.which", side_effect=lambda x: "/usr/bin/claude" if x == "claude" else None):
            bt, kwargs = detect_backend()
            assert bt == "claude-code"
            assert kwargs["claude_path"] == "claude"

    def test_auto_detect_codex_cli(self):
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("shutil.which", side_effect=lambda x: "/usr/bin/codex" if x == "codex" else None):
            bt, kwargs = detect_backend()
            assert bt == "codex"

    def test_fallback_to_ollama(self):
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("shutil.which", return_value=None):
            bt, kwargs = detect_backend()
            assert bt == "ollama"

    def test_env_overrides_config(self):
        config = {"backend.type": "ollama"}
        with patch.dict(os.environ, {"BACKEND_TYPE": "anthropic",
                                     "ANTHROPIC_API_KEY": "key"}):
            bt, kwargs = detect_backend(config)
            assert bt == "anthropic"

    def test_default_model_from_env(self):
        with patch.dict(os.environ, {"BACKEND_TYPE": "ollama",
                                     "GOVERNOR_MODEL": "llama3"}):
            bt, kwargs = detect_backend()
            assert kwargs["default_model"] == "llama3"

    def test_default_model_from_config(self):
        config = {"backend.type": "ollama", "backend.model": "mistral"}
        env = os.environ.copy()
        env.pop("BACKEND_TYPE", None)
        env.pop("GOVERNOR_MODEL", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), \
             patch("shutil.which", return_value=None):
            bt, kwargs = detect_backend(config)
            assert kwargs.get("default_model") == "mistral"

    def test_ollama_custom_host(self):
        with patch.dict(os.environ, {"BACKEND_TYPE": "ollama",
                                     "OLLAMA_HOST": "http://gpu:11434"}):
            bt, kwargs = detect_backend()
            assert kwargs["host"] == "http://gpu:11434"


# =============================================================================
# DaemonState: ChatBridge + context manager
# =============================================================================


class TestDaemonStateChatBridge:

    def test_chat_bridge_none_on_failure(self, state):
        """When backend creation fails, chat_bridge returns None."""
        with patch("governor.daemon.detect_backend",
                   return_value=("anthropic", {"api_key": ""})):
            # Anthropic backend with empty key raises ValueError
            bridge = state.chat_bridge
            assert bridge is None

    def test_backend_type_lazy(self, state):
        """backend_type triggers detection on first access."""
        with patch("governor.daemon.detect_backend",
                   return_value=("ollama", {"host": "http://localhost:11434"})):
            assert state.backend_type == "ollama"

    def test_default_model_empty(self, state):
        assert state.default_model == ""

    def test_context_manager_lazy(self, state):
        assert state._context_manager is None
        cm = state.context_manager
        assert cm is not None
        assert state.context_manager is cm

    def test_daemon_config_lazy(self, state):
        assert state._config is None
        cfg = state.daemon_config
        assert isinstance(cfg, dict)
        assert state.daemon_config is cfg


# =============================================================================
# Handler: governor.hello — updated capabilities
# =============================================================================


class TestGovernorHelloChat:

    @pytest.mark.asyncio
    async def test_hello_includes_chat_capability(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        caps = resp["result"]["capabilities"]
        assert "chat" in caps
        assert "streaming" in caps
        assert "backend" in caps
        assert isinstance(caps["backend"], dict)
        assert "type" in caps["backend"]
        assert "connected" in caps["backend"]

    @pytest.mark.asyncio
    async def test_hello_chat_false_when_no_backend(self, dispatcher_and_state):
        """Chat capability is False when no backend can be created."""
        d, state = dispatcher_and_state
        # Force no backend
        state._chat_bridge = None
        state._backend_type = "none"
        with patch.object(DaemonState, "chat_bridge", new_callable=lambda: property(lambda self: None)):
            d2 = Dispatcher()
            register_handlers(d2, state)
            resp = await roundtrip(d2, "governor.hello")
            caps = resp["result"]["capabilities"]
            assert caps["chat"] is False


# =============================================================================
# Handler: chat.backend
# =============================================================================


class TestChatBackend:

    @pytest.mark.asyncio
    async def test_backend_returns_type(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        resp = await roundtrip(d, "chat.backend")
        result = resp["result"]
        assert "type" in result
        assert "connected" in result

    @pytest.mark.asyncio
    async def test_backend_no_model_by_default(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chat.backend")
        # No default_model set in test fixture
        assert "model" not in resp["result"]


# =============================================================================
# Handler: chat.models
# =============================================================================


class TestChatModels:

    @pytest.mark.asyncio
    async def test_models_empty_when_no_backend(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        # No backend configured in test environment
        resp = await roundtrip(d, "chat.models")
        result = resp["result"]
        assert "models" in result
        assert isinstance(result["models"], list)


# =============================================================================
# Handler: chat.send — with mock backend
# =============================================================================


class MockChatBackend:
    """Minimal mock backend for testing chat handlers."""

    def __init__(self, response_content: str = "Hello from mock"):
        self.response_content = response_content
        self.last_messages = None
        self.last_model = None

    async def chat(self, messages, model, **kwargs):
        from governor.chat_bridge import ChatResponse
        self.last_messages = messages
        self.last_model = model
        return ChatResponse(
            content=self.response_content,
            model=model or "mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    async def stream(self, messages, model, **kwargs):
        from governor.chat_bridge import ChatChunk
        self.last_messages = messages
        self.last_model = model
        # Yield content in chunks
        words = self.response_content.split()
        for word in words:
            yield ChatChunk(content=word + " ")
        yield ChatChunk(content="", finish_reason="stop")

    async def list_models(self):
        return [{"id": "mock-model", "owned_by": "test"}]


@pytest.fixture
def state_with_mock_backend(tmp_gov_dir):
    """DaemonState with a mock chat backend pre-wired."""
    state = DaemonState(tmp_gov_dir, mode="general")
    mock_backend = MockChatBackend("Hello from the governed LLM")
    from governor.chat_bridge import ChatBridge
    from governor.context_manager import GovernorContextManager
    ctx_mgr = GovernorContextManager(tmp_gov_dir)
    state._chat_bridge = ChatBridge(
        backend=mock_backend,
        context_manager=ctx_mgr,
        show_ok_footer=True,
    )
    state._backend_type = "mock"
    state._backend_kwargs = {}
    state._context_manager = ctx_mgr
    return state


@pytest.fixture
def dispatcher_with_chat(state_with_mock_backend):
    d = Dispatcher()
    register_handlers(d, state_with_mock_backend)
    return d, state_with_mock_backend


class TestChatSend:

    @pytest.mark.asyncio
    async def test_send_basic(self, dispatcher_with_chat):
        d, state = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
        })
        result = resp["result"]
        assert "content" in result
        assert result["content"] == "Hello from the governed LLM"
        assert result["model"] == "mock-model"
        assert "usage" in result
        assert "violations" in result
        assert result["pending"] is None

    @pytest.mark.asyncio
    async def test_send_with_model(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
            "model": "custom-model",
        })
        assert resp["result"]["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_send_missing_messages(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_send_empty_messages(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {"messages": []})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_send_no_backend(self, tmp_gov_dir):
        """chat.send fails gracefully when no backend is configured."""
        state = DaemonState(tmp_gov_dir, mode="general")
        # Force chat_bridge to None by setting a failed state
        state._chat_bridge = None
        state._backend_type = "none"

        # Prevent lazy init from auto-detecting a real backend
        with patch.object(DaemonState, "chat_bridge",
                          new_callable=lambda: property(lambda self: None)):
            d = Dispatcher()
            register_handlers(d, state)
            resp = await roundtrip(d, "chat.send", {
                "messages": [{"role": "user", "content": "Hi"}],
            })
            assert resp["error"]["code"] == GOVERNOR_ERROR
            assert "No chat backend" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_send_footer_included(self, dispatcher_with_chat):
        """Non-blocking response includes governor footer."""
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "test"}],
        })
        result = resp["result"]
        # With no anchors, footer may be None or OK depending on checked_anchors
        assert "footer" in result

    @pytest.mark.asyncio
    async def test_send_multi_message(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "How are you?"},
            ],
        })
        result = resp["result"]
        assert "content" in result

    @pytest.mark.asyncio
    async def test_send_with_context_id(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
            "context_id": "test-ctx",
        })
        result = resp["result"]
        assert result["pending"] is None

    @pytest.mark.asyncio
    async def test_send_emits_receipt(self, dispatcher_with_chat):
        d, state = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "test"}],
        })
        assert resp["result"]["content"]  # Got a response
        # Check receipt was emitted
        receipts = state.receipt_system.query(gate="chat_bridge")
        assert len(receipts) >= 1
        assert receipts[0].verdict == "pass"


# =============================================================================
# Handler: chat.stream — streaming with notifications
# =============================================================================


class TestChatStream:

    @pytest.mark.asyncio
    async def test_stream_dispatches(self, dispatcher_with_chat):
        """chat.stream handler is found and executes."""
        d, state = dispatcher_with_chat
        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        # Call the streaming handler directly through the dispatcher
        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hello"}],
        }, mock_notify)

        assert "content" in result
        assert result["content"] == "Hello from the governed LLM "
        # Should have received delta notifications
        assert len(notifications) > 0
        for n in notifications:
            assert n["method"] == "chat.delta"
            assert "content" in n["params"]

    @pytest.mark.asyncio
    async def test_stream_final_response(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hi"}],
        }, mock_notify)

        # Final result has all required fields
        assert "content" in result
        assert "model" in result
        assert "violations" in result
        assert "footer" in result
        assert "pending" in result

    @pytest.mark.asyncio
    async def test_stream_no_backend(self, tmp_gov_dir):
        state = DaemonState(tmp_gov_dir, mode="general")
        with patch.object(DaemonState, "chat_bridge",
                          new_callable=lambda: property(lambda self: None)):
            d = Dispatcher()
            register_handlers(d, state)
            req = rpc_request("chat.stream", {
                "messages": [{"role": "user", "content": "Hi"}],
            })
            resp = await d.dispatch(req)
            assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_stream_emits_receipt(self, dispatcher_with_chat):
        d, state = dispatcher_with_chat
        handler = d._streaming_handlers["chat.stream"]

        async def noop_notify(method: str, params: dict) -> None:
            pass

        await handler({
            "messages": [{"role": "user", "content": "test"}],
        }, noop_notify)

        receipts = state.receipt_system.query(gate="chat_bridge")
        assert len(receipts) >= 1

    @pytest.mark.asyncio
    async def test_stream_missing_messages(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat

        async def noop_notify(method: str, params: dict) -> None:
            pass

        handler = d._streaming_handlers["chat.stream"]
        with pytest.raises(ValueError, match="Missing required param"):
            await handler({}, noop_notify)

    @pytest.mark.asyncio
    async def test_stream_delta_content_matches(self, dispatcher_with_chat):
        """All delta content concatenated equals the final content."""
        d, _ = dispatcher_with_chat
        chunks: list[str] = []

        async def collect_notify(method: str, params: dict) -> None:
            if method == "chat.delta":
                chunks.append(params["content"])

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hi"}],
        }, collect_notify)

        streamed = "".join(chunks)
        assert streamed == result["content"]


# =============================================================================
# Streaming dispatch integration (writer passthrough)
# =============================================================================


class TestStreamingDispatch:

    @pytest.mark.asyncio
    async def test_dispatch_passes_writer_to_streaming_handler(self):
        """Verify dispatch plumbs the writer into streaming handlers."""
        d = Dispatcher()
        received_notify = []

        async def streaming_echo(params: dict, notify) -> dict:
            await notify("test.delta", {"chunk": "A"})
            await notify("test.delta", {"chunk": "B"})
            return {"result": "done"}

        d.register_streaming("test.echo", streaming_echo)

        # Create a mock writer
        written: list[bytes] = []
        writer = MagicMock()
        writer.write = lambda data: written.append(data)

        async def mock_drain():
            pass
        writer.drain = mock_drain

        req = {"jsonrpc": "2.0", "method": "test.echo", "id": 1, "params": {}}
        resp = await d.dispatch(req, writer=writer)

        assert resp["result"] == {"result": "done"}
        # Two notifications should have been written
        assert len(written) == 2

        # Parse the written notifications
        for data in written:
            text = data.decode("utf-8")
            assert "Content-Length:" in text
            _, _, body = text.partition("\r\n\r\n")
            msg = json.loads(body)
            assert msg["method"] == "test.delta"

    @pytest.mark.asyncio
    async def test_streaming_handler_without_writer(self):
        """When no writer, notify is a no-op (doesn't crash)."""
        d = Dispatcher()

        async def streaming_handler(params, notify):
            await notify("delta", {"x": 1})
            return {"ok": True}

        d.register_streaming("test.stream", streaming_handler)
        req = {"jsonrpc": "2.0", "method": "test.stream", "id": 1, "params": {}}
        resp = await d.dispatch(req, writer=None)
        assert resp["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_streaming_handler_error(self):
        d = Dispatcher()

        async def bad_stream(params, notify):
            raise RuntimeError("stream failed")

        d.register_streaming("test.fail", bad_stream)
        req = {"jsonrpc": "2.0", "method": "test.fail", "id": 1, "params": {}}
        resp = await d.dispatch(req)
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "stream failed" in resp["error"]["message"]


# =============================================================================
# _emit_chat_receipt helper
# =============================================================================


class TestEmitChatReceipt:

    def test_emit_pass(self, state_with_mock_backend):
        state = state_with_mock_backend
        _emit_chat_receipt(state, "pass", "Hello world", "run_1")
        receipts = state.receipt_system.query(gate="chat_bridge", verdict="pass")
        assert len(receipts) == 1

    def test_emit_block(self, state_with_mock_backend):
        state = state_with_mock_backend
        _emit_chat_receipt(state, "block", "Bad content", "run_2")
        receipts = state.receipt_system.query(gate="chat_bridge", verdict="block")
        assert len(receipts) == 1

    def test_emit_receipt_failure_silent(self, state):
        """Receipt emission failure should not propagate."""
        # state has no chat bridge, but _emit_chat_receipt should not crash
        _emit_chat_receipt(state, "pass", "content", "run_3")
        # No exception raised — that's the test


# =============================================================================
# Chat with blocking violations
# =============================================================================


class TestChatBlockingViolation:

    @pytest.mark.asyncio
    async def test_send_with_violation_returns_pending(self, tmp_gov_dir):
        """When governor check finds REJECT violations, pending is returned."""
        state = DaemonState(tmp_gov_dir, mode="general")
        mock_backend = MockChatBackend("This violates everything")

        from governor.chat_bridge import ChatBridge, GovernorCheckResult, ViolationPendingResponse
        from governor.context_manager import GovernorContextManager

        ctx_mgr = GovernorContextManager(tmp_gov_dir)
        state._chat_bridge = ChatBridge(
            backend=mock_backend,
            context_manager=ctx_mgr,
            show_ok_footer=True,
        )
        state._backend_type = "mock"
        state._backend_kwargs = {}
        state._context_manager = ctx_mgr

        d = Dispatcher()
        register_handlers(d, state)

        # Mock check_response_blocking to return a ViolationPendingResponse
        violation_resp = ViolationPendingResponse(
            blocked_response="This violates everything",
            violations=[{"anchor_id": "a1", "severity": "reject", "message": "Bad"}],
            choices=["fix", "revise", "proceed"],
            prompt="Violation detected",
            run_id="test_run",
            pending_id="pending_1",
        )

        with patch("governor.chat_bridge.GovernorHooks.check_response_blocking",
                    return_value=violation_resp):
            resp = await roundtrip(d, "chat.send", {
                "messages": [{"role": "user", "content": "Do bad thing"}],
            })
            result = resp["result"]
            assert result["pending"] is not None
            assert result["pending"]["blocked_response"] == "This violates everything"
            assert len(result["violations"]) == 1

    @pytest.mark.asyncio
    async def test_stream_with_violation_returns_pending(self, tmp_gov_dir):
        state = DaemonState(tmp_gov_dir, mode="general")
        mock_backend = MockChatBackend("Violating content")

        from governor.chat_bridge import ChatBridge, ViolationPendingResponse
        from governor.context_manager import GovernorContextManager

        ctx_mgr = GovernorContextManager(tmp_gov_dir)
        state._chat_bridge = ChatBridge(
            backend=mock_backend,
            context_manager=ctx_mgr,
        )
        state._backend_type = "mock"
        state._backend_kwargs = {}
        state._context_manager = ctx_mgr

        d = Dispatcher()
        register_handlers(d, state)

        violation_resp = ViolationPendingResponse(
            blocked_response="Violating content",
            violations=[{"anchor_id": "a1", "severity": "reject"}],
            choices=["fix"],
            prompt="Fix it",
            run_id="run_x",
        )

        async def noop_notify(method, params):
            pass

        with patch("governor.chat_bridge.GovernorHooks.check_response_blocking",
                    return_value=violation_resp):
            handler = d._streaming_handlers["chat.stream"]
            result = await handler({
                "messages": [{"role": "user", "content": "test"}],
            }, noop_notify)
            assert result["pending"] is not None


# =============================================================================
# Chat with mock backend: models listing
# =============================================================================


class TestChatModelsWithBackend:

    @pytest.mark.asyncio
    async def test_models_from_mock_backend(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.models")
        models = resp["result"]["models"]
        assert len(models) == 1
        assert models[0]["id"] == "mock-model"

    @pytest.mark.asyncio
    async def test_backend_info_with_mock(self, dispatcher_with_chat):
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.backend")
        result = resp["result"]
        assert result["type"] == "mock"
        assert result["connected"] is True


# =============================================================================
# Pending violation pre-check in chat.send / chat.stream
# =============================================================================


class TestChatPendingPreCheck:
    """When a pending violation exists, chat.send/chat.stream must not generate."""

    @pytest.fixture
    def state_with_pending(self, tmp_gov_dir):
        """DaemonState with a mock backend AND a pre-existing pending violation."""
        import json as _json
        from governor.violation_resolver import PendingViolation, ResolutionStatus

        state = DaemonState(tmp_gov_dir, mode="general")

        # Wire up mock backend
        mock_backend = MockChatBackend("Should NOT appear")
        from governor.chat_bridge import ChatBridge
        from governor.context_manager import GovernorContextManager

        ctx_mgr = GovernorContextManager(tmp_gov_dir)
        state._chat_bridge = ChatBridge(
            backend=mock_backend,
            context_manager=ctx_mgr,
            show_ok_footer=True,
        )
        state._backend_type = "mock"
        state._backend_kwargs = {}
        state._context_manager = ctx_mgr

        # Write a pending violation to disk
        pending = PendingViolation(
            id="pending_test_1",
            context_id="default",
            run_id="run_abc",
            violations=[
                {"anchor_id": "anchor-1", "severity": "reject",
                 "description": "Tone violation"}
            ],
            blocked_response="The blocked text",
            timestamp="2025-01-01T00:00:00Z",
            mode="general",
            status=ResolutionStatus.PENDING,
        )
        (tmp_gov_dir / "pending_violations.json").write_text(
            _json.dumps(pending.to_dict())
        )

        return state

    @pytest.fixture
    def dispatcher_with_pending(self, state_with_pending):
        d = Dispatcher()
        register_handlers(d, state_with_pending)
        return d, state_with_pending

    @pytest.mark.asyncio
    async def test_send_returns_pending_without_generating(
        self, dispatcher_with_pending
    ):
        """chat.send must return pending violation instead of calling backend."""
        d, state = dispatcher_with_pending
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hello"}],
        })
        result = resp["result"]
        # Should return pending, NOT the mock backend response
        assert result["pending"] is not None
        assert result["pending"]["id"] == "pending_test_1"
        assert result["content"] == ""
        assert len(result["violations"]) == 1

    @pytest.mark.asyncio
    async def test_stream_returns_pending_without_generating(
        self, dispatcher_with_pending
    ):
        """chat.stream must return pending violation without streaming."""
        d, _ = dispatcher_with_pending
        notifications: list[dict] = []

        async def collect(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler(
            {"messages": [{"role": "user", "content": "Hello"}]},
            collect,
        )
        # Should return pending, not stream content
        assert result["pending"] is not None
        assert result["content"] == ""
        # No delta notifications sent
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_send_resolution_command_resolves(
        self, dispatcher_with_pending
    ):
        """When pending exists and user sends 'proceed', resolve the violation."""
        d, state = dispatcher_with_pending
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "proceed"}],
        })
        result = resp["result"]
        # Should be resolved — no more pending
        assert result["pending"] is None
        assert "Governor" in result["content"] or "Proceed" in result["content"].lower() or result["content"]

    @pytest.mark.asyncio
    async def test_stream_resolution_command_resolves(
        self, dispatcher_with_pending
    ):
        """When pending exists and user sends 'revise', resolve via stream path."""
        d, _ = dispatcher_with_pending

        async def noop(method: str, params: dict) -> None:
            pass

        handler = d._streaming_handlers["chat.stream"]
        result = await handler(
            {"messages": [{"role": "user", "content": "revise"}]},
            noop,
        )
        assert result["pending"] is None

    @pytest.mark.asyncio
    async def test_send_non_resolution_message_re_presents_pending(
        self, dispatcher_with_pending
    ):
        """Non-resolution messages should re-present the pending violation."""
        d, _ = dispatcher_with_pending
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "tell me a joke"}],
        })
        result = resp["result"]
        assert result["pending"] is not None
        assert result["pending"]["id"] == "pending_test_1"

    @pytest.mark.asyncio
    async def test_send_without_pending_generates_normally(
        self, dispatcher_with_chat
    ):
        """When no pending violation, chat.send generates as usual."""
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
        })
        result = resp["result"]
        assert result["pending"] is None
        assert result["content"] == "Hello from the governed LLM"
