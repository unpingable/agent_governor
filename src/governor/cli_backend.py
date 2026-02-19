# SPDX-License-Identifier: Apache-2.0
"""
Synchronous RPC client for CLI → daemon communication.

Pure stdlib (socket module). No asyncio. Used by operator commands
(doctor, dashboard, trace) to prefer daemon state when available.

Backend chooser triangle:
    GOV_BACKEND=rpc    → fail loud if daemon unreachable
    GOV_BACKEND=auto   → try daemon, fall back to local (default)
    GOV_BACKEND=local  → never try daemon
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Content-Length framing (same wire format as daemon.py)
# ---------------------------------------------------------------------------

def _write_frame(sock: socket.socket, msg: dict) -> None:
    """Write a Content-Length framed JSON-RPC message to a socket."""
    body = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sock.sendall(header + body)


def _read_frame(sock: socket.socket) -> dict | None:
    """Read a Content-Length framed JSON-RPC message from a socket.

    Returns the parsed dict, or None on EOF / parse error.
    """
    # Read headers line by line
    buf = b""
    content_length = -1
    while True:
        byte = sock.recv(1)
        if not byte:
            return None  # EOF
        buf += byte
        if buf.endswith(b"\r\n\r\n"):
            break
        # Safety: headers shouldn't exceed 1KB
        if len(buf) > 1024:
            return None

    # Parse Content-Length from headers
    for line in buf.decode("utf-8", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                return None

    if content_length < 0:
        return None

    # Read exact body
    body = b""
    while len(body) < content_length:
        chunk = sock.recv(content_length - len(body))
        if not chunk:
            return None  # EOF mid-body
        body += chunk

    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Synchronous JSON-RPC call
# ---------------------------------------------------------------------------

_request_counter = 0


def sync_rpc_call(
    sock_path: Path,
    method: str,
    params: dict,
    timeout: float = 2.0,
) -> dict | None:
    """Synchronous JSON-RPC 2.0 call over Unix socket.

    Returns the result dict on success, or None on any error
    (timeout, connection refused, RPC error, malformed response).
    Callers should fall back to local state on None.
    """
    global _request_counter
    _request_counter += 1
    request_id = _request_counter

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(sock_path))
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
            "params": params,
        }
        _write_frame(s, msg)

        # Read frames, skip notifications, stop at our response
        while True:
            frame = _read_frame(s)
            if frame is None:
                return None
            # Skip notifications (no "id" field)
            if "id" not in frame:
                continue
            # Skip responses for other request IDs
            if frame.get("id") != request_id:
                continue
            # RPC error → let caller fall back
            if "error" in frame:
                return None
            return frame.get("result")
    except (socket.timeout, ConnectionError, OSError, FileNotFoundError):
        return None
    finally:
        s.close()


def sync_rpc_call_raw(
    sock_path: Path,
    method: str,
    params: dict,
    timeout: float = 5.0,
) -> dict | None:
    """Synchronous JSON-RPC 2.0 call — returns the full response frame.

    Unlike ``sync_rpc_call`` which swallows errors and returns None,
    this returns the entire frame dict (including ``"error"`` key on
    RPC errors) so callers can display the error to the user.

    Returns None only on transport failure (timeout, connection refused,
    EOF, malformed frame).
    """
    global _request_counter
    _request_counter += 1
    request_id = _request_counter

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(sock_path))
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
            "params": params,
        }
        _write_frame(s, msg)

        while True:
            frame = _read_frame(s)
            if frame is None:
                return None
            if "id" not in frame:
                continue  # Skip notifications
            if frame.get("id") != request_id:
                continue
            return frame  # Full frame: result or error
    except (socket.timeout, ConnectionError, OSError, FileNotFoundError):
        return None
    finally:
        s.close()


def reset_rpc_counter() -> None:
    """Reset the request counter. For testing only."""
    global _request_counter
    _request_counter = 0


# ---------------------------------------------------------------------------
# Method classification cache (for rpc call safety interlock)
# ---------------------------------------------------------------------------

_methods_cache: dict[str, tuple[dict[str, str], float]] = {}
_METHODS_CACHE_TTL_S = 5.0


def _get_method_info(sock_path: Path) -> dict[str, str] | None:
    """Cached governor.methods lookup. Returns {method: classification} or None."""
    cache_key = str(sock_path)
    now = time.monotonic()
    entry = _methods_cache.get(cache_key)
    if entry and (now - entry[1]) < _METHODS_CACHE_TTL_S:
        return entry[0]
    result = sync_rpc_call(sock_path, "governor.methods", {}, timeout=2.0)
    if result is None:
        return None
    by_name = {m["method"]: m["classification"] for m in result.get("methods", [])}
    _methods_cache[cache_key] = (by_name, now)
    return by_name


def check_method_allowed(
    sock_path: Path,
    method: str,
    allow_mutating: bool,
    *,
    cli_flag: bool = False,
    env_var: bool = False,
) -> str | None:
    """Return error message if method is blocked, or None if allowed.

    When *allow_mutating* is False and the method is mutating, the message
    specifies which lock(s) are missing (CLI flag, env var, or both).
    """
    info = _get_method_info(sock_path)
    if info is None:
        return None  # Can't check — let the call fail naturally
    if method not in info:
        return None  # Unknown method — let the daemon reject it
    if info[method] == "mutating" and not allow_mutating:
        missing: list[str] = []
        if not cli_flag:
            missing.append("--mutating flag")
        if not env_var:
            missing.append("GOV_RPC_ALLOW_MUTATING=1 env var")
        detail = " and ".join(missing) if missing else "both locks"
        return (
            f"Refused: {method!r} is a mutating method.\n"
            f"Missing: {detail}.\n"
            f"The daemon may also enforce its own policy "
            f"(daemon.allow_mutating_rpc in daemon.conf)."
        )
    return None


def reset_methods_cache() -> None:
    """Clear the methods cache. For testing only."""
    _methods_cache.clear()


# ---------------------------------------------------------------------------
# Backend chooser — keyed by resolved gov_dir path
# ---------------------------------------------------------------------------

# Cache is keyed by resolved gov_dir so different dirs in one process
# (tests, --gov-dir flag) never cross-pollinate.
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_S = 1.0  # Short TTL — not process lifetime


def get_operator_backend(gov_dir: Path) -> str:
    """Determine whether operator commands should use RPC or local file reads.

    Returns "rpc" or "local". Result is cached per gov_dir for ~1s.

    Environment variable GOV_BACKEND controls behavior:
        "rpc"   → always use daemon (fail loud if unreachable)
        "local" → never try daemon
        "auto"  → probe daemon socket, fall back to local (default)
    """
    cache_key = str(gov_dir.resolve())
    now = time.monotonic()
    entry = _cache.get(cache_key)
    if entry and (now - entry[1]) < _CACHE_TTL_S:
        return entry[0]

    forced = os.environ.get("GOV_BACKEND", "auto").strip().lower()
    if forced == "rpc":
        _cache[cache_key] = ("rpc", now)
        return "rpc"
    if forced == "local":
        _cache[cache_key] = ("local", now)
        return "local"

    # auto: probe daemon socket
    from .daemon import default_socket_path
    sock_path = default_socket_path(gov_dir)
    if sock_path.exists():
        try:
            result = sync_rpc_call(sock_path, "governor.hello", {}, timeout=0.3)
            if result is not None:
                _cache[cache_key] = ("rpc", now)
                return "rpc"
        except Exception:
            pass

    _cache[cache_key] = ("local", now)
    return "local"


def reset_cache() -> None:
    """Clear the backend choice cache. For testing only."""
    _cache.clear()
