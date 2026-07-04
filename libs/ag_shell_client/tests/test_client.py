# SPDX-License-Identifier: Apache-2.0
"""GS-8b: the live-socket client class.

Two flavors:
- Unit tests over an in-memory ``asyncio.StreamReader`` pre-fed with framed
  frames (deterministic, no daemon): id-matching, notification skipping, typed
  error mapping, stream notifications-then-result, busy fail-fast.
- Live-daemon smoke: a real ``serve_unix`` in a background task — proves the
  client speaks the daemon's wire byte-for-byte (unary round-trip + streaming).

The package pins no pytest-asyncio; each async body runs via ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ag_shell_client import (
    AsyncDaemonClient,
    DaemonAuthError,
    RPCError,
    StreamItem,
)
from ag_shell_client.protocol import encode_message


class _FakeWriter:
    """Minimal StreamWriter stand-in capturing written bytes."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def _client_over(*frames: dict) -> AsyncDaemonClient:
    """A client whose reader is pre-fed the given frames (then EOF)."""
    reader = asyncio.StreamReader()
    for frame in frames:
        reader.feed_data(encode_message(frame))
    reader.feed_eof()
    return AsyncDaemonClient(reader, _FakeWriter())


# --- unit: unary call ------------------------------------------------------ #


def test_call_returns_result():
    async def go():
        client = _client_over({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        return await client.call("governor.hello")

    assert asyncio.run(go()) == {"ok": True}


def test_call_skips_notifications_before_matching_id():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "method": "noise", "params": {"x": 1}},
            {"jsonrpc": "2.0", "id": 1, "result": 42},
        )
        return await client.call("m")

    assert asyncio.run(go()) == 42


def test_call_maps_rpc_error():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "nope"}}
        )
        await client.call("bogus")

    with pytest.raises(RPCError) as ei:
        asyncio.run(go())
    assert ei.value.code == -32601


def test_call_maps_auth_error():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "login"}}
        )
        await client.call("chat.send")

    with pytest.raises(DaemonAuthError) as ei:
        asyncio.run(go())
    assert ei.value.code == -32001


def test_call_surfaces_idless_error_frame_no_hang():
    """BLOCK fix (codex): an error frame not tied to our id (null-id parse /
    invalid-request error) must be raised, never skipped — skipping would hang
    waiting for a response the daemon won't send."""
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse"}}
        )
        await client.call("m")

    with pytest.raises(RPCError) as ei:
        asyncio.run(go())
    assert ei.value.code == -32700


def test_call_fails_closed_on_foreign_result_id():
    """WARN fix (codex): a result with a foreign id on a one-in-flight
    connection is a desync — fail closed, don't block on the next read."""
    async def go():
        client = _client_over({"jsonrpc": "2.0", "id": 999, "result": "stale"})
        await client.call("m")  # expects id 1

    with pytest.raises(RPCError) as ei:
        asyncio.run(go())
    assert "unexpected response id" in str(ei.value)


def test_poisoned_client_refuses_reuse():
    """WARN fix (codex): after an interrupted exchange the connection is
    indeterminate; reuse fails fast rather than reading a stale frame."""
    async def go():
        client = _client_over({"jsonrpc": "2.0", "id": 1, "result": 1})
        client._poisoned = True
        await client.call("m")

    with pytest.raises(RuntimeError) as ei:
        asyncio.run(go())
    assert "indeterminate" in str(ei.value)


def test_stream_notification_params_preserved_verbatim():
    """WARN fix (codex): notification params pass through verbatim — a valid
    falsy/empty payload is not rewritten to {}, and missing params → None."""
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "method": "e", "params": {}},   # empty but valid
            {"jsonrpc": "2.0", "method": "e"},                  # no params key
            {"jsonrpc": "2.0", "id": 1, "result": None},
        )
        return [it async for it in client.stream("s")]

    items = asyncio.run(go())
    assert items[0].payload == {}
    assert items[1].payload is None
    assert items[-1].kind == "result"


def test_call_foreign_error_poisons_connection():
    """NEW-ISSUE fix (codex): after surfacing a foreign-id error our real
    response may still be pending, so the connection is poisoned — reuse fails
    fast rather than reading a late stale response."""
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse"}}
        )
        try:
            await client.call("m")
        except RPCError:
            pass
        await client.call("m2")  # reuse must fail fast

    with pytest.raises(RuntimeError) as ei:
        asyncio.run(go())
    assert "indeterminate" in str(ei.value)


def test_stream_aclose_before_terminal_poisons_connection():
    """STILL-OPEN fix (codex): closing a stream before its terminal frame leaves
    frames the daemon is still sending undrained — the connection is poisoned so
    it is not reused mid-exchange."""
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "method": "e", "params": {"n": 1}},
            {"jsonrpc": "2.0", "id": 1, "result": {"done": True}},
        )
        agen = client.stream("s")
        first = await agen.__anext__()
        assert first.kind == "notification"
        await agen.aclose()  # early close, before the terminal (id=1) frame
        await client.call("x")  # reuse must fail fast

    with pytest.raises(RuntimeError) as ei:
        asyncio.run(go())
    assert "indeterminate" in str(ei.value)


def test_call_raises_on_eof_before_response():
    async def go():
        client = _client_over()  # no frames, immediate EOF
        await client.call("m")

    with pytest.raises(RPCError):
        asyncio.run(go())


def test_request_ids_increment_across_calls():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "id": 1, "result": "a"},
            {"jsonrpc": "2.0", "id": 2, "result": "b"},
        )
        first = await client.call("m")
        second = await client.call("m")
        return first, second, bytes(client._writer.buf)

    first, second, written = asyncio.run(go())
    assert (first, second) == ("a", "b")
    # Both request ids appear on the wire, distinct and incrementing.
    assert b'"id": 1' in written and b'"id": 2' in written


# --- unit: streaming ------------------------------------------------------- #


def test_stream_yields_notifications_then_result():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "method": "chat.delta", "params": {"content": "a"}},
            {"jsonrpc": "2.0", "method": "chat.delta", "params": {"content": "b"}},
            {"jsonrpc": "2.0", "id": 1, "result": {"done": True}},
        )
        return [item async for item in client.stream("chat.stream")]

    items = asyncio.run(go())
    assert [it.kind for it in items] == ["notification", "notification", "result"]
    assert items[0].method == "chat.delta"
    assert items[0].payload == {"content": "a"}
    assert items[-1].payload == {"done": True}


def test_stream_error_frame_raises_during_iteration():
    async def go():
        client = _client_over(
            {"jsonrpc": "2.0", "method": "chat.delta", "params": {"content": "a"}},
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "login"}},
        )
        collected = []
        async for item in client.stream("chat.stream"):
            collected.append(item)
        return collected

    with pytest.raises(DaemonAuthError):
        asyncio.run(go())


# --- unit: connection discipline ------------------------------------------ #


def test_busy_client_fails_fast():
    async def go():
        client = _client_over({"jsonrpc": "2.0", "id": 1, "result": 1})
        client._busy = True  # simulate an in-flight request
        await client.call("m")

    with pytest.raises(RuntimeError):
        asyncio.run(go())


def test_stream_item_is_immutable():
    it = StreamItem("notification", "chat.delta", {"x": 1})
    with pytest.raises(Exception):
        it.kind = "result"  # frozen dataclass


# --- live daemon smoke ----------------------------------------------------- #


def _make_state(tmp_path):
    from governor.daemon import DaemonState

    gov = tmp_path / ".governor"
    gov.mkdir()
    (gov / "sessions").mkdir()
    (gov / "sessions" / "index.json").write_text(
        json.dumps({"sessions": {}, "mainline": None})
    )
    return DaemonState(gov, mode="general"), gov


async def _with_live_daemon(state, gov, body):
    """Run ``body(gov)`` against a real daemon serving ``state`` on gov's socket."""
    from governor.daemon import default_socket_path, serve_unix

    sock = default_socket_path(gov)
    server = asyncio.create_task(serve_unix(sock, state))
    try:
        for _ in range(100):
            if sock.exists():
                break
            await asyncio.sleep(0.02)
        return await body(gov)
    finally:
        server.cancel()
        try:
            await server
        except asyncio.CancelledError:
            pass


def test_live_hello_roundtrip(tmp_path):
    async def go():
        state, gov = _make_state(tmp_path)

        async def body(gov):
            client = await AsyncDaemonClient.connect(gov)
            try:
                return await client.call("governor.hello")
            finally:
                await client.aclose()

        return await _with_live_daemon(state, gov, body)

    hello = asyncio.run(go())
    assert isinstance(hello, dict) and hello
    # governor.hello advertises the protocol + capabilities.
    assert "protocol_version" in hello or "capabilities" in hello


def test_live_stream_operator_watch(tmp_path):
    async def go():
        state, gov = _make_state(tmp_path)

        async def body(gov):
            client = await AsyncDaemonClient.connect(gov)
            try:
                items = []
                async for item in client.stream(
                    "operator.watch", {"max_ticks": 1, "interval_ms": 200}
                ):
                    items.append(item)
                return items
            finally:
                await client.aclose()

        return await _with_live_daemon(state, gov, body)

    items = asyncio.run(go())
    # At least the terminal result; the opening snapshot is a notification.
    assert items, "stream produced no items"
    assert items[-1].kind == "result"
    assert any(it.kind == "notification" for it in items)
