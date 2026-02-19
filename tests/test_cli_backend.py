# SPDX-License-Identifier: Apache-2.0
"""Tests for cli_backend: sync RPC client and backend chooser."""

import json
import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture()
def short_tmp():
    """Temp dir with a short path — avoids AF_UNIX 104-byte limit on macOS."""
    d = tempfile.mkdtemp(prefix="gov_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)

from governor.cli_backend import (
    _read_frame,
    _write_frame,
    check_method_allowed,
    get_operator_backend,
    reset_cache,
    reset_methods_cache,
    reset_rpc_counter,
    sync_rpc_call,
    sync_rpc_call_raw,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_echo_server(sock_path: Path, response: dict | None = None) -> socket.socket:
    """Start a Unix socket server that echoes back a canned JSON-RPC response.

    Returns the server socket (caller must close it).
    """
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)
    srv.settimeout(2.0)

    def _serve():
        try:
            conn, _ = srv.accept()
            conn.settimeout(2.0)
            # Read request frame
            frame = _read_frame(conn)
            if frame is None:
                conn.close()
                return
            # Build response
            if response is not None:
                resp = response
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": frame.get("id"),
                    "result": {"protocol_version": "1.0"},
                }
            _write_frame(conn, resp)
            conn.close()
        except Exception:
            pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return srv


# ---------------------------------------------------------------------------
# Content-Length framing
# ---------------------------------------------------------------------------

class TestFraming:
    def test_roundtrip(self, short_tmp):
        """Write + read a frame through a real socket pair."""
        sock_path = short_tmp / "test.sock"
        msg = {"jsonrpc": "2.0", "method": "test", "id": 1}

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        received = []

        def _reader():
            conn, _ = srv.accept()
            conn.settimeout(2.0)
            received.append(_read_frame(conn))
            conn.close()

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))
        _write_frame(client, msg)
        client.close()

        t.join(timeout=2)
        srv.close()

        assert len(received) == 1
        assert received[0] == msg

    def test_read_frame_returns_none_on_empty(self):
        """_read_frame returns None when socket has no data."""
        s1, s2 = socket.socketpair()
        s2.close()  # EOF immediately
        s1.settimeout(0.1)
        result = _read_frame(s1)
        s1.close()
        assert result is None


# ---------------------------------------------------------------------------
# sync_rpc_call
# ---------------------------------------------------------------------------

class TestSyncRpcCall:
    def test_successful_call(self, short_tmp):
        """sync_rpc_call returns result on success."""
        sock_path = short_tmp / "rpc.sock"
        srv = _start_echo_server(sock_path)
        try:
            result = sync_rpc_call(sock_path, "governor.hello", {})
            assert result is not None
            assert result["protocol_version"] == "1.0"
        finally:
            srv.close()

    def test_returns_none_on_no_socket(self, tmp_path):
        """Returns None when socket file doesn't exist."""
        result = sync_rpc_call(tmp_path / "nonexistent.sock", "test", {})
        assert result is None

    def test_returns_none_on_rpc_error(self, short_tmp):
        """Returns None when server returns an RPC error."""
        sock_path = short_tmp / "err.sock"
        error_response = {
            "jsonrpc": "2.0",
            "id": None,  # Will be overwritten by server
            "error": {"code": -32000, "message": "test error"},
        }

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        def _serve():
            try:
                conn, _ = srv.accept()
                conn.settimeout(2.0)
                frame = _read_frame(conn)
                if frame:
                    resp = dict(error_response)
                    resp["id"] = frame.get("id")
                    _write_frame(conn, resp)
                conn.close()
            except Exception:
                pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        result = sync_rpc_call(sock_path, "test", {})
        srv.close()
        assert result is None

    def test_skips_notifications(self, short_tmp):
        """sync_rpc_call skips notification frames and returns the response."""
        sock_path = short_tmp / "notify.sock"

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        def _serve():
            try:
                conn, _ = srv.accept()
                conn.settimeout(2.0)
                frame = _read_frame(conn)
                if frame:
                    # Send a notification first (no id)
                    notif = {"jsonrpc": "2.0", "method": "chat.delta",
                             "params": {"content": "hi"}}
                    _write_frame(conn, notif)
                    # Then send the real response
                    resp = {"jsonrpc": "2.0", "id": frame["id"],
                            "result": {"ok": True}}
                    _write_frame(conn, resp)
                conn.close()
            except Exception:
                pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        result = sync_rpc_call(sock_path, "test", {})
        srv.close()
        assert result is not None
        assert result["ok"] is True

    def test_increments_request_id(self, short_tmp):
        """Each call gets a unique request ID."""
        reset_rpc_counter()
        sock_path = short_tmp / "id.sock"

        ids_seen = []

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(5)

        def _serve():
            for _ in range(2):
                try:
                    conn, _ = srv.accept()
                    conn.settimeout(2.0)
                    frame = _read_frame(conn)
                    if frame:
                        ids_seen.append(frame["id"])
                        resp = {"jsonrpc": "2.0", "id": frame["id"],
                                "result": {"ok": True}}
                        _write_frame(conn, resp)
                    conn.close()
                except Exception:
                    pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        sync_rpc_call(sock_path, "test1", {})
        sync_rpc_call(sock_path, "test2", {})
        t.join(timeout=2)
        srv.close()

        assert len(ids_seen) == 2
        assert ids_seen[0] != ids_seen[1]

    def test_timeout_returns_none(self, short_tmp):
        """Returns None on timeout (server doesn't respond)."""
        sock_path = short_tmp / "slow.sock"

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        def _serve():
            try:
                conn, _ = srv.accept()
                time.sleep(3)  # Longer than timeout
                conn.close()
            except Exception:
                pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        result = sync_rpc_call(sock_path, "test", {}, timeout=0.1)
        srv.close()
        assert result is None


# ---------------------------------------------------------------------------
# Backend chooser
# ---------------------------------------------------------------------------

class TestGetOperatorBackend:
    def setup_method(self):
        reset_cache()

    def teardown_method(self):
        reset_cache()
        # Clean up env var
        os.environ.pop("GOV_BACKEND", None)

    def test_returns_local_when_no_socket(self, tmp_path):
        """Without a daemon socket, returns 'local'."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        result = get_operator_backend(gov_dir)
        assert result == "local"

    def test_forced_rpc(self, tmp_path):
        """GOV_BACKEND=rpc forces rpc mode."""
        os.environ["GOV_BACKEND"] = "rpc"
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        result = get_operator_backend(gov_dir)
        assert result == "rpc"

    def test_forced_local(self, tmp_path):
        """GOV_BACKEND=local forces local mode."""
        os.environ["GOV_BACKEND"] = "local"
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        result = get_operator_backend(gov_dir)
        assert result == "local"

    def test_auto_finds_running_daemon(self, tmp_path):
        """auto mode detects a running daemon and returns 'rpc'."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Compute the expected socket path and start a server there
        from governor.daemon import default_socket_path
        sock_path = default_socket_path(gov_dir)
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        srv = _start_echo_server(sock_path)
        try:
            result = get_operator_backend(gov_dir)
            assert result == "rpc"
        finally:
            srv.close()
            if sock_path.exists():
                sock_path.unlink()

    def test_cache_ttl(self, tmp_path):
        """Cached result expires after TTL."""
        os.environ["GOV_BACKEND"] = "local"
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        result1 = get_operator_backend(gov_dir)
        assert result1 == "local"

        # Change env — but cache still holds
        os.environ["GOV_BACKEND"] = "rpc"
        result2 = get_operator_backend(gov_dir)
        assert result2 == "local"  # Still cached

        # Expire cache
        reset_cache()
        result3 = get_operator_backend(gov_dir)
        assert result3 == "rpc"

    def test_reset_cache(self, tmp_path):
        """reset_cache() clears the cached result."""
        os.environ["GOV_BACKEND"] = "local"
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        get_operator_backend(gov_dir)
        reset_cache()

        os.environ["GOV_BACKEND"] = "rpc"
        result = get_operator_backend(gov_dir)
        assert result == "rpc"


# ---------------------------------------------------------------------------
# sync_rpc_call_raw
# ---------------------------------------------------------------------------

class TestSyncRpcCallRaw:
    def test_returns_full_frame_on_success(self, short_tmp):
        """sync_rpc_call_raw returns the full frame dict including 'result'."""
        sock_path = short_tmp / "raw.sock"
        srv = _start_echo_server(sock_path)
        try:
            frame = sync_rpc_call_raw(sock_path, "governor.hello", {})
            assert frame is not None
            assert "result" in frame
            assert frame["result"]["protocol_version"] == "1.0"
            assert "jsonrpc" in frame
        finally:
            srv.close()

    def test_returns_full_frame_on_rpc_error(self, short_tmp):
        """Returns frame with 'error' key on RPC errors (not None)."""
        sock_path = short_tmp / "raw_err.sock"

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        def _serve():
            try:
                conn, _ = srv.accept()
                conn.settimeout(2.0)
                req = _read_frame(conn)
                if req:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req["id"],
                        "error": {"code": -32000, "message": "test error"},
                    }
                    _write_frame(conn, resp)
                conn.close()
            except Exception:
                pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        frame = sync_rpc_call_raw(sock_path, "test", {})
        srv.close()
        assert frame is not None
        assert "error" in frame
        assert frame["error"]["code"] == -32000

    def test_returns_none_on_transport_failure(self, tmp_path):
        """Returns None when socket doesn't exist."""
        frame = sync_rpc_call_raw(tmp_path / "nonexistent.sock", "test", {})
        assert frame is None


# ---------------------------------------------------------------------------
# check_method_allowed
# ---------------------------------------------------------------------------

def _start_methods_server(sock_path: Path, methods_info: list[dict]) -> socket.socket:
    """Start a server that responds to governor.methods with given info."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)

    def _serve():
        try:
            conn, _ = srv.accept()
            conn.settimeout(2.0)
            req = _read_frame(conn)
            if req:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "result": {"methods": methods_info, "count": len(methods_info)},
                }
                _write_frame(conn, resp)
            conn.close()
        except Exception:
            pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return srv


class TestCheckMethodAllowed:
    def setup_method(self):
        reset_methods_cache()

    def teardown_method(self):
        reset_methods_cache()

    def test_blocks_mutating_when_not_armed(self, short_tmp):
        sock_path = short_tmp / "methods.sock"
        methods = [
            {"method": "governor.hello", "classification": "read_only"},
            {"method": "sessions.create", "classification": "mutating"},
        ]
        srv = _start_methods_server(sock_path, methods)
        try:
            err = check_method_allowed(sock_path, "sessions.create", allow_mutating=False)
            assert err is not None
            assert "Refused" in err
            assert "sessions.create" in err
            # Default: both locks missing
            assert "--mutating flag" in err
            assert "GOV_RPC_ALLOW_MUTATING" in err
        finally:
            srv.close()

    def test_message_shows_only_missing_lock(self, short_tmp):
        """When CLI flag is set but env var is not, only env var is listed."""
        sock_path = short_tmp / "methods_msg.sock"
        methods = [
            {"method": "sessions.create", "classification": "mutating"},
        ]
        srv = _start_methods_server(sock_path, methods)
        try:
            err = check_method_allowed(
                sock_path, "sessions.create", allow_mutating=False,
                cli_flag=True, env_var=False,
            )
            assert err is not None
            assert "--mutating flag" not in err
            assert "GOV_RPC_ALLOW_MUTATING" in err
        finally:
            srv.close()

    def test_allows_mutating_when_armed(self, short_tmp):
        sock_path = short_tmp / "methods2.sock"
        methods = [
            {"method": "sessions.create", "classification": "mutating"},
        ]
        srv = _start_methods_server(sock_path, methods)
        try:
            err = check_method_allowed(sock_path, "sessions.create", allow_mutating=True)
            assert err is None
        finally:
            srv.close()

    def test_allows_read_only_unconditionally(self, short_tmp):
        sock_path = short_tmp / "methods3.sock"
        methods = [
            {"method": "governor.hello", "classification": "read_only"},
        ]
        srv = _start_methods_server(sock_path, methods)
        try:
            err = check_method_allowed(sock_path, "governor.hello", allow_mutating=False)
            assert err is None
        finally:
            srv.close()

    def test_returns_none_when_daemon_unreachable(self, tmp_path):
        """Fail-open: if we can't reach the daemon, don't block the call."""
        err = check_method_allowed(tmp_path / "no.sock", "anything", allow_mutating=False)
        assert err is None

    def test_returns_none_for_unknown_method(self, short_tmp):
        """Unknown methods pass through — let the daemon reject them."""
        sock_path = short_tmp / "methods4.sock"
        methods = [
            {"method": "governor.hello", "classification": "read_only"},
        ]
        srv = _start_methods_server(sock_path, methods)
        try:
            err = check_method_allowed(sock_path, "nonexistent.method", allow_mutating=False)
            assert err is None
        finally:
            srv.close()
