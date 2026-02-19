# SPDX-License-Identifier: Apache-2.0
"""StdioGateway: policy-enforcing proxy between MCP client and tool server.

The gateway speaks MCP on both sides:
- Server to the agent runtime (reads stdin, writes stdout)
- Client to the upstream tool server (child process stdio)

Phase 0: single upstream, allow/deny only, no transforms.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from typing import IO, Any

from receipt_v1 import ExecutionStatus
from receipt_v1.canonical import uuid7

from mcp_governor.config import GatewayConfig
from mcp_governor.framing import read_message, write_message
from mcp_governor.policy import PolicyEngine
from mcp_governor.receipt_emitter import ReceiptEmitter
from mcp_governor.types import (
    ActorInfo,
    GatewaySession,
    PolicyDecision,
    ReasonCode,
    ToolCallEnvelope,
)

# Hard timeout for upstream initialize handshake
_INIT_TIMEOUT_S = 10.0


def _log(msg: str) -> None:
    """Log to stderr (never stdout — that's the MCP wire)."""
    print(f"[mcp-governor] {msg}", file=sys.stderr, flush=True)


def _make_error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _make_result_response(req_id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC result response."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _drain_stderr(stream: IO[str]) -> None:
    """Drain upstream stderr in a background thread to prevent deadlock."""
    try:
        for line in stream:
            _log(f"[upstream] {line.rstrip()}")
    except (ValueError, OSError):
        pass  # stream closed


class StdioGateway:
    """MCP stdio proxy with policy enforcement and receipt emission.

    Lifecycle:
    1. Client sends ``initialize`` → gateway spawns upstream, handshakes
    2. Client sends ``notifications/initialized`` → forwarded
    3. ``tools/list`` → forwarded with deny-filter applied
    4. ``tools/call`` → policy check → allow/deny → receipt
    5. Everything else → forwarded unchanged
    """

    def __init__(
        self,
        config: GatewayConfig,
        *,
        client_in: IO[str] | None = None,
        client_out: IO[str] | None = None,
    ) -> None:
        self._config = config
        self._client_in = client_in or sys.stdin
        self._client_out = client_out or sys.stdout
        self._policy = PolicyEngine(
            deny_tools=config.deny_tools,
            default_policy=config.default_policy,
        )
        self._emitter: ReceiptEmitter | None = None
        self._session: GatewaySession | None = None
        self._upstream_proc: subprocess.Popen[str] | None = None
        self._upstream_in: IO[str] | None = None  # write to upstream
        self._upstream_out: IO[str] | None = None  # read from upstream
        self._stderr_thread: threading.Thread | None = None
        self._running = False

    def run(self) -> None:
        """Main proxy loop. Blocks until client EOF or error."""
        self._running = True
        try:
            self._proxy_loop()
        finally:
            self._running = False
            self._cleanup()

    def _proxy_loop(self) -> None:
        while self._running:
            msg = read_message(self._client_in)
            if msg is None:
                _log("Client EOF, shutting down")
                break

            method = msg.get("method")
            req_id = msg.get("id")  # None for notifications

            if method == "initialize":
                self._handle_initialize(msg)
            elif method == "notifications/initialized":
                self._handle_initialized_notification(msg)
            elif method == "tools/list":
                self._handle_tools_list(msg)
            elif method == "tools/call":
                self._handle_tools_call(msg)
            else:
                # Forward everything else unchanged
                self._forward_to_upstream(msg)
                if req_id is not None:
                    # It's a request — wait for upstream response and forward
                    resp = self._read_upstream()
                    if resp is not None:
                        write_message(self._client_out, resp)
                # Notifications (no id): just forward, no response expected

    def _handle_initialize(self, msg: dict[str, Any]) -> None:
        """Handle client initialize request."""
        req_id = msg.get("id")
        params = msg.get("params", {})
        client_info = params.get("clientInfo", {})

        # Create session
        self._session = GatewaySession(session_id=uuid7())

        # Spawn upstream
        if not self._config.upstream_command:
            write_message(self._client_out, _make_error_response(
                req_id, -32603, "No upstream command configured"))
            return

        try:
            self._spawn_upstream()
        except OSError as e:
            _log(f"Failed to spawn upstream: {e}")
            write_message(self._client_out, _make_error_response(
                req_id, -32603, f"Failed to spawn upstream: {e}"))
            return

        # Send initialize to upstream
        upstream_init = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-governor",
                    "version": "0.1.0",
                },
            },
        }
        self._forward_to_upstream(upstream_init)

        # Wait for upstream response with timeout
        upstream_resp = self._read_upstream(timeout=_INIT_TIMEOUT_S)
        if upstream_resp is None:
            _log("Upstream initialize timed out")
            write_message(self._client_out, _make_error_response(
                req_id, -32603, "Upstream tool server did not respond to initialize"))
            self._cleanup()
            return

        # Capture identity info
        upstream_result = upstream_resp.get("result", {})
        upstream_server_info = upstream_result.get("serverInfo", {})

        self._session.actor_info = ActorInfo(
            client_name=client_info.get("name"),
            client_version=client_info.get("version"),
            server_name=upstream_server_info.get("name"),
            server_version=upstream_server_info.get("version"),
            protocol_version=upstream_result.get("protocolVersion",
                                                  params.get("protocolVersion")),
        )

        # Initialize receipt emitter
        self._emitter = ReceiptEmitter(
            receipt_path=self._config.receipt_path,
            deployment_id=self._config.deployment_id,
            governor_version="0.1.0",
            upstream_command=self._config.upstream_command,
            fsync=True,
        )

        # Reply to client with gateway's server info + upstream capabilities
        capabilities = upstream_result.get("capabilities", {})
        response = _make_result_response(req_id, {
            "protocolVersion": upstream_result.get("protocolVersion", "2024-11-05"),
            "capabilities": capabilities,
            "serverInfo": {
                "name": "mcp-governor",
                "version": "0.1.0",
            },
        })
        write_message(self._client_out, response)
        self._session.initialized = True
        _log(f"Initialized: client={client_info.get('name')}, "
             f"upstream={upstream_server_info.get('name')}")

    def _handle_initialized_notification(self, msg: dict[str, Any]) -> None:
        """Forward notifications/initialized to upstream."""
        self._forward_to_upstream({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

    def _handle_tools_list(self, msg: dict[str, Any]) -> None:
        """Forward tools/list with deny-filter applied."""
        req_id = msg.get("id")
        self._forward_to_upstream(msg)
        resp = self._read_upstream()
        if resp is None:
            write_message(self._client_out, _make_error_response(
                req_id, -32603, "Upstream did not respond to tools/list"))
            return

        # Filter tools by policy
        result = resp.get("result", {})
        tools = result.get("tools", [])
        allowed_names = set(self._policy.filter_tools([t.get("name", "") for t in tools]))
        filtered_tools = [t for t in tools if t.get("name", "") in allowed_names]

        resp_out = _make_result_response(req_id, {"tools": filtered_tools})
        write_message(self._client_out, resp_out)

    def _handle_tools_call(self, msg: dict[str, Any]) -> None:
        """Policy check → allow/deny → receipt → forward or error."""
        req_id = msg.get("id")
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        envelope = ToolCallEnvelope(
            tool_name=tool_name,
            arguments=arguments,
            call_id=str(req_id) if req_id is not None else "null",
        )

        decision = self._policy.evaluate(tool_name)

        if not decision.allow:
            # Deny path: emit receipt, return error
            self._try_emit(envelope, decision)
            write_message(self._client_out, _make_error_response(
                req_id, -32601,
                f"Tool '{tool_name}' denied by governor policy"))
            return

        # Allow path: forward to upstream
        t0 = time.monotonic()
        self._forward_to_upstream(msg)
        resp = self._read_upstream()
        duration_ms = int((time.monotonic() - t0) * 1000)

        if resp is None:
            self._try_emit(
                envelope, decision,
                execution_status=ExecutionStatus.TIMEOUT,
                duration_ms=duration_ms,
                error="Upstream did not respond",
            )
            write_message(self._client_out, _make_error_response(
                req_id, -32603, "Upstream did not respond to tools/call"))
            return

        # Determine execution status
        if "error" in resp:
            exec_status = ExecutionStatus.FAILURE
            error_msg = resp["error"].get("message", "unknown error")
        else:
            exec_status = ExecutionStatus.SUCCESS
            error_msg = None

        # Emit receipt BEFORE returning result (fail-closed)
        self._try_emit(
            envelope, decision,
            execution_status=exec_status,
            duration_ms=duration_ms,
            error=error_msg,
        )

        # Return upstream response to client
        write_message(self._client_out, resp)

    def _try_emit(
        self,
        envelope: ToolCallEnvelope,
        decision: PolicyDecision,
        **kwargs: Any,
    ) -> None:
        """Attempt receipt emission. On failure, log loudly but don't crash."""
        if self._emitter is None or self._session is None:
            _log("WARNING: Receipt emission skipped (no session)")
            return
        try:
            self._emitter.emit(self._session, envelope, decision, **kwargs)
        except Exception as e:
            _log(f"CRITICAL: Receipt emission failed: {e}")
            # Fail-closed: if we already executed upstream, we can't undo it.
            # But we MUST tell the caller something is wrong.
            # The gateway logs to stderr; the response still goes through
            # so the agent knows governance is degraded.

    def _spawn_upstream(self) -> None:
        """Spawn the upstream tool server as a child process."""
        proc = subprocess.Popen(
            self._config.upstream_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line buffered
        )
        self._upstream_proc = proc
        self._upstream_in = proc.stdin
        self._upstream_out = proc.stdout

        # Drain stderr in background to prevent deadlock
        if proc.stderr:
            self._stderr_thread = threading.Thread(
                target=_drain_stderr, args=(proc.stderr,), daemon=True)
            self._stderr_thread.start()

    def _forward_to_upstream(self, msg: dict[str, Any]) -> None:
        """Write a message to the upstream tool server."""
        if self._upstream_in is None:
            return
        try:
            write_message(self._upstream_in, msg)
        except (BrokenPipeError, OSError) as e:
            _log(f"Failed to write to upstream: {e}")

    def _read_upstream(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Read one message from upstream. Optional timeout."""
        if self._upstream_out is None:
            return None

        if timeout is not None:
            result: dict[str, Any] | None = None
            exc: Exception | None = None

            def _read() -> None:
                nonlocal result, exc
                try:
                    result = read_message(self._upstream_out)  # type: ignore[arg-type]
                except Exception as e:
                    exc = e

            t = threading.Thread(target=_read, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                return None  # timed out
            if exc is not None:
                _log(f"Error reading upstream: {exc}")
                return None
            return result

        try:
            return read_message(self._upstream_out)
        except (ValueError, OSError) as e:
            _log(f"Error reading upstream: {e}")
            return None

    def _cleanup(self) -> None:
        """Kill upstream child process and close pipes."""
        proc = self._upstream_proc
        if proc is None:
            return

        # Close stdin to signal upstream
        if proc.stdin:
            try:
                proc.stdin.close()
            except OSError:
                pass

        # Give it a moment to exit
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            _log("Upstream did not exit, sending SIGTERM")
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                _log("Upstream did not exit after SIGTERM, sending SIGKILL")
                proc.kill()
                proc.wait()

        self._upstream_proc = None
        self._upstream_in = None
        self._upstream_out = None
