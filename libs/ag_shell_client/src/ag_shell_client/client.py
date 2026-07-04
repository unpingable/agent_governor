# SPDX-License-Identifier: Apache-2.0
"""Live Unix-socket client for the governor daemon (GS-8b).

Wraps the pure codec in :mod:`ag_shell_client.protocol` with an asyncio
connection so shells (maude, phosphor's governed-session lane) share ONE client
instead of each re-deriving connect/call/stream. Transport ONLY — framing +
dispatch; no UI, no retry policy, no rendering (those stay in the shells).

Connection model (mirrors the daemon): one client instance == one connection,
which the daemon serves **sequentially** — one in-flight request at a time. A
held :meth:`AsyncDaemonClient.stream` occupies the connection until it ends, so
per the shell contract you run ``operator.watch`` on a *dedicated second client*
while a first client handles unary calls. Attempting a concurrent request on a
busy client fails fast (never interleaves frames). Stdlib-only.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from .protocol import (
    RPCError,
    default_socket_path,
    encode_message,
    make_request,
    parse_response,
)


@dataclass(frozen=True)
class StreamItem:
    """One item from a streaming call.

    A stream is a sequence of ``notification`` items (mid-stream pushes, e.g.
    ``chat.delta`` / ``operator.watch.update``) terminated by exactly one
    ``result`` item carrying the call's final result value. An error frame
    raises (``RPCError`` / ``DaemonAuthError``) instead of yielding.
    """

    kind: str  # "notification" | "result"
    method: str | None  # notification method name; None for the result
    payload: Any  # notification params dict, or the final result value


class AsyncDaemonClient:
    """Async JSON-RPC client over the daemon's Unix socket.

    Construct with :meth:`connect`. Use :meth:`call` for unary RPCs and
    :meth:`stream` for held streaming RPCs. Supports ``async with``.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        default_timeout: float = 10.0,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._default_timeout = default_timeout
        self._next_id = 0
        self._busy = False
        self._gen = 0  # operation generation, for gen-guarded release
        # An interrupted exchange (timeout/cancel/EOF after a request was
        # written) leaves the sequential connection indeterminate: a response
        # may still be pending. Once poisoned, the client refuses reuse.
        self._poisoned = False

    @classmethod
    async def connect(
        cls,
        governor_dir: str | os.PathLike[str] | None = None,
        *,
        socket_path: str | os.PathLike[str] | None = None,
        default_timeout: float = 10.0,
        connect_timeout: float = 5.0,
    ) -> "AsyncDaemonClient":
        """Open a connection to the daemon.

        Provide either ``governor_dir`` (path derived via
        :func:`default_socket_path`, byte-identical to the daemon's) or an
        explicit ``socket_path``.
        """
        if socket_path is None:
            if governor_dir is None:
                raise ValueError("connect requires governor_dir or socket_path")
            socket_path = default_socket_path(governor_dir)
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(socket_path)),
            timeout=connect_timeout,
        )
        return cls(reader, writer, default_timeout=default_timeout)

    # -- lifecycle ---------------------------------------------------------- #

    async def aclose(self) -> None:
        """Close the connection. Idempotent."""
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            # Best-effort teardown: a socket already gone is not an error worth
            # raising from a close path.
            pass

    async def __aenter__(self) -> "AsyncDaemonClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- requests ----------------------------------------------------------- #

    async def call(
        self, method: str, params: dict | None = None, *, timeout: float | None = None
    ) -> Any:
        """Send a unary request; return its ``result`` or raise the typed error.

        ``-32001`` raises :class:`~ag_shell_client.protocol.DaemonAuthError`; any
        other error raises :class:`~ag_shell_client.protocol.RPCError`.
        """
        timeout = self._default_timeout if timeout is None else timeout
        gen = self._acquire()
        try:
            try:
                return await asyncio.wait_for(self._call(method, params), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # A request was already written; on a sequential connection the
                # daemon may still respond later. Poison so the connection is not
                # silently reused mid-exchange (its next read would be stale).
                self._poisoned = True
                raise
        finally:
            self._release(gen)

    async def _call(self, method: str, params: dict | None) -> Any:
        rid = self._send(method, params)
        await self._writer.drain()
        while True:
            frame = await self._read_frame()
            if frame is None:
                self._poisoned = True
                raise RPCError(0, "connection closed before response")
            fid = frame.get("id")
            if fid == rid:
                return parse_response(frame)  # our response (result or typed error)
            # Not our id. An error frame not tied to our request (e.g. a
            # null-id parse / invalid-request error) TERMINATES the exchange —
            # surface it, never skip: skipping waits forever for a response the
            # daemon will not send. Poison first: our own response may yet be
            # pending, so the connection is indeterminate and must not be reused.
            if frame.get("error") is not None:
                self._poisoned = True
                return parse_response(frame)  # raises the typed error
            if "method" in frame:
                continue  # a stray notification on a unary call
            # A foreign RESULT id on a one-in-flight connection is a desync;
            # fail closed rather than block on the next read.
            self._poisoned = True
            raise RPCError(0, f"unexpected response id {fid!r} (expected {rid})")

    async def stream(
        self,
        method: str,
        params: dict | None = None,
        *,
        read_timeout: float | None = None,
    ) -> AsyncIterator[StreamItem]:
        """Send a streaming request; yield notifications then the final result.

        Yields a :class:`StreamItem` per server notification, then exactly one
        ``result`` item, then stops. Raises on an error frame. Holds the
        connection for the stream's lifetime — use a second client for
        concurrent unary calls.

        ``read_timeout`` (default ``None`` = unbounded, since streams like
        ``operator.watch`` are legitimately long-lived) bounds each individual
        frame read; a stalled read then poisons the connection and raises rather
        than pinning it forever.
        """
        gen = self._acquire()
        drained = False  # did we consume the terminal (id-matched) frame?
        try:
            rid = self._send(method, params)
            await self._writer.drain()
            while True:
                frame = await self._read_one(read_timeout)
                if frame is None:
                    self._poisoned = True
                    raise RPCError(0, "connection closed during stream")
                fid = frame.get("id")
                if fid == rid:
                    # Terminal frame reached — the exchange is complete and the
                    # connection is clean even if parse_response raises a typed
                    # error below (the server has finished this request).
                    drained = True
                    result = parse_response(frame)
                    # Release deterministically at terminal-frame time (before
                    # the final yield), gen-guarded, so a consumer that stops
                    # right after the result does not leave the connection busy.
                    self._release(gen)
                    yield StreamItem("result", None, result)
                    return
                if "method" in frame:
                    # Params passed VERBATIM (no ``or {}`` — that would rewrite a
                    # valid falsy payload); missing params → None.
                    yield StreamItem("notification", frame.get("method"), frame.get("params"))
                    continue
                if frame.get("error") is not None:
                    parse_response(frame)  # foreign-id error — raises, ends stream
                # A foreign RESULT id mid-stream is a desync; fail closed.
                raise RPCError(0, f"unexpected frame id {fid!r} during stream (expected {rid})")
        finally:
            # Any exit BEFORE the terminal frame (consumer break → GeneratorExit,
            # cancellation, read EOF/timeout, mid-stream failure) leaves frames
            # the daemon is still sending for this stream undrained on the wire.
            # Poison so the connection is not reused mid-exchange.
            if not drained:
                self._poisoned = True
            self._release(gen)

    # -- internals ---------------------------------------------------------- #

    def _acquire(self) -> int:
        # Single-threaded asyncio: a set flag is sufficient mutual-exclusion for
        # "one in-flight request per connection". Fail fast rather than
        # interleave frames (which would corrupt the stream). Returns a
        # generation token so a stale operation's release can be distinguished
        # from a live one's.
        if self._poisoned:
            raise RuntimeError(
                "ag_shell_client: connection is in an indeterminate state after "
                "a prior timeout/cancel/EOF; reconnect a fresh client"
            )
        if self._busy:
            raise RuntimeError(
                "ag_shell_client: a request is already in flight on this "
                "connection; use a separate client for concurrent streams"
            )
        self._busy = True
        self._gen += 1
        return self._gen

    def _release(self, gen: int) -> None:
        # gen-guarded: a superseded operation's finally must not free a newer
        # operation's flag (e.g. a stream that released early then had its
        # generator GC'd while a fresh call is in flight).
        if self._busy and self._gen == gen:
            self._busy = False

    async def _read_one(self, read_timeout: float | None) -> dict | None:
        if read_timeout is None:
            return await self._read_frame()
        try:
            return await asyncio.wait_for(self._read_frame(), timeout=read_timeout)
        except asyncio.TimeoutError:
            self._poisoned = True
            raise

    def _send(self, method: str, params: dict | None) -> int:
        self._next_id += 1
        rid = self._next_id
        self._writer.write(encode_message(make_request(method, params, request_id=rid)))
        return rid

    async def _read_frame(self) -> dict | None:
        """Read one Content-Length framed message from the stream reader.

        Mirrors the daemon's async framing (``read_message``) exactly:
        ``Content-Length: N\\r\\n\\r\\n`` + N body bytes. Returns the parsed
        dict, or ``None`` on EOF / a frame without Content-Length.
        """
        headers: dict[str, str] = {}
        while True:
            line = await self._reader.readline()
            if not line:
                return None  # EOF
            decoded = line.decode("utf-8")
            if decoded in ("\r\n", "\n"):
                break
            if ":" in decoded:
                key, _, value = decoded.partition(":")
                headers[key.strip()] = value.strip()

        length = headers.get("Content-Length")
        if length is None:
            return None
        try:
            body = await self._reader.readexactly(int(length))
        except asyncio.IncompleteReadError:
            return None  # connection died mid-body → treat as EOF
        return json.loads(body.decode("utf-8"))
