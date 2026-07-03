# SPDX-License-Identifier: Apache-2.0
"""Governor daemon wire protocol — the pieces every shell client duplicates.

This module de-triplicates what currently lives copied in three places (the
daemon, maude's client, phosphor's daemon_client): the Unix socket path
derivation, Content-Length framing, JSON-RPC 2.0 request/response shape, and the
-32001 auth error. Pure and stdlib-only; no IO of its own beyond the framing
codec's injected read function, so it is fully unit-testable without a daemon.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

# JSON-RPC error code the daemon returns when the backend is not authenticated
# (e.g. Claude Code not logged in). Shells map it to a login prompt, not a 502.
AUTH_ERROR_CODE = -32001


def default_socket_path(governor_dir: str | os.PathLike[str]) -> Path:
    """The daemon's Unix socket path for a governor directory.

    Byte-for-byte the same derivation as ``governor.daemon.default_socket_path``
    (that identity is what makes this the shared client): a 12-hex sha256 prefix
    over the resolved governor dir, under ``$XDG_RUNTIME_DIR`` (``/tmp`` fallback).
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    dir_hash = hashlib.sha256(str(Path(governor_dir).resolve()).encode()).hexdigest()[:12]
    return Path(xdg) / f"governor-{dir_hash}.sock"


class RPCError(Exception):
    """A JSON-RPC error result from the daemon. Carries the code + data."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class DaemonAuthError(RPCError):
    """The daemon's backend is not authenticated (code -32001). A shell should
    surface this as a login instruction, never as a transport failure."""


def make_request(method: str, params: dict | None = None, *, request_id: int) -> dict:
    """Build a JSON-RPC 2.0 request. ``request_id`` is the caller's to track."""
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": request_id,
    }


def parse_response(response: dict) -> Any:
    """Return a response's ``result``, or raise the typed error.

    ``-32001`` becomes :class:`DaemonAuthError`; any other error becomes
    :class:`RPCError`. A notification (no ``id``/``result``/``error``) returns
    ``None``.
    """
    if "error" in response and response["error"] is not None:
        err = response["error"]
        if not isinstance(err, dict):
            # A daemon that violates JSON-RPC (error is not an object) is still
            # an error, not a result — surface it, don't crash reading it.
            raise RPCError(0, str(err))
        code = err.get("code", 0)
        message = err.get("message", "")
        data = err.get("data")
        if code == AUTH_ERROR_CODE:
            raise DaemonAuthError(code, message, data)
        raise RPCError(code, message, data)
    return response.get("result")


def encode_message(msg: dict) -> bytes:
    """Content-Length framed JSON (the daemon's framing, verbatim)."""
    body = json.dumps(msg).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def read_message(readline: Callable[[], bytes], readexactly: Callable[[int], bytes]) -> dict | None:
    """Read one Content-Length framed JSON-RPC message.

    ``readline`` returns the next header line (bytes, incl. terminator; empty at
    EOF); ``readexactly(n)`` returns exactly ``n`` body bytes. Returns the parsed
    dict, or ``None`` on EOF / a frame with no Content-Length. Injecting the two
    read functions keeps this testable over a BytesIO and reusable over a socket.
    """
    headers: dict[str, str] = {}
    while True:
        line = readline()
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
    body = readexactly(int(length))
    return json.loads(body.decode("utf-8"))
