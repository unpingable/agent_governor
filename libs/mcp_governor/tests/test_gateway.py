# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.gateway — full proxy transcript tests.

Strategy: create a GatewayConfig pointing at a mock echo server,
run the gateway with piped stdin/stdout, feed JSON-RPC transcript,
assert responses + receipt file contents.
"""

from __future__ import annotations

import io
import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mcp_governor.config import GatewayConfig
from mcp_governor.framing import read_message, write_message
from mcp_governor.gateway import StdioGateway, _make_error_response, _make_result_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(method: str, params: dict | None = None, req_id: Any = 1) -> dict:
    m: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        m["params"] = params
    return m


def _notif(method: str, params: dict | None = None) -> dict:
    m: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        m["params"] = params
    return m


def _result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


class FakeUpstream:
    """Simulates an upstream MCP tool server via in-memory streams.

    Writes responses to its stdout when it receives requests on stdin.
    Runs in a background thread.
    """

    def __init__(self, tools: list[dict] | None = None) -> None:
        self.tools = tools or [
            {"name": "echo", "description": "Echo text", "inputSchema": {"type": "object"}},
            {"name": "shell.exec", "description": "Execute shell", "inputSchema": {"type": "object"}},
        ]
        # Gateway writes to upstream_in → upstream reads from _in_r
        self._in_r, self._in_w = _pipe_pair()
        # Upstream writes to _out_w → gateway reads from upstream_out
        self._out_r, self._out_w = _pipe_pair()
        self._thread: threading.Thread | None = None

    @property
    def stdin_for_gateway(self) -> io.StringIO:
        """Gateway writes here (upstream's stdin)."""
        return self._in_w

    @property
    def stdout_for_gateway(self) -> io.StringIO:
        """Gateway reads here (upstream's stdout)."""
        return self._out_r

    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            msg = read_message(self._in_r)
            if msg is None:
                break
            method = msg.get("method")
            req_id = msg.get("id")

            if method == "initialize":
                write_message(self._out_w, _result(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-server", "version": "1.0"},
                }))
            elif method == "tools/list":
                write_message(self._out_w, _result(req_id, {"tools": self.tools}))
            elif method == "tools/call":
                params = msg.get("params", {})
                name = params.get("name", "")
                args = params.get("arguments", {})
                if name == "echo":
                    write_message(self._out_w, _result(req_id, {
                        "content": [{"type": "text", "text": args.get("text", "")}],
                    }))
                elif name == "fail_tool":
                    write_message(self._out_w, {
                        "jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -1, "message": "Tool execution failed"},
                    })
                else:
                    write_message(self._out_w, _result(req_id, {
                        "content": [{"type": "text", "text": f"called {name}"}],
                    }))
            elif method == "notifications/initialized":
                pass  # notification, no response
            else:
                # Forward unknown methods back with empty result
                if req_id is not None:
                    write_message(self._out_w, _result(req_id, {}))


def _pipe_pair() -> tuple[io.StringIO, io.StringIO]:
    """Create a connected pair of StringIO streams using a threading pipe."""
    # Use a simple threading-based pipe
    return _ThreadPipe(), _ThreadPipe.__new__(_ThreadPipe)


class _ThreadPipe(io.StringIO):
    """A StringIO that blocks on readline() until data is written."""
    pass


# Since real pipe pairs are complex with StringIO, let's use a simpler approach:
# We'll test the gateway by directly calling internal methods and using
# a subprocess-based integration for the full transcript test.

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_make_error_response(self):
        resp = _make_error_response(42, -32601, "Not found")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert resp["error"]["code"] == -32601
        assert resp["error"]["message"] == "Not found"

    def test_make_result_response(self):
        resp = _make_result_response("abc", {"tools": []})
        assert resp["id"] == "abc"
        assert resp["result"] == {"tools": []}


# ---------------------------------------------------------------------------
# Gateway tests using mock upstream via monkey-patching
# ---------------------------------------------------------------------------

class TestGatewayInitialize:
    def test_no_upstream_command(self, tmp_path):
        """Gateway returns error if no upstream command configured."""
        config = GatewayConfig(
            upstream_command=[],
            receipt_path=str(tmp_path / "r.jsonl"),
        )
        client_in = io.StringIO()
        client_out = io.StringIO()

        # Write initialize request
        init_req = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }, separators=(",", ":")) + "\n"
        client_in.write(init_req)
        client_in.seek(0)

        gw = StdioGateway(config, client_in=client_in, client_out=client_out)
        gw.run()

        client_out.seek(0)
        resp = json.loads(client_out.readline())
        assert "error" in resp
        assert resp["error"]["code"] == -32603


class TestGatewayToolsCall:
    """Test tools/call with a patched upstream."""

    def _run_gateway_with_transcript(
        self,
        tmp_path: Path,
        client_messages: list[dict],
        upstream_responses: list[dict],
        deny_tools: list[str] | None = None,
        default_policy: str = "allow",
    ) -> tuple[list[dict], list[dict]]:
        """Run gateway with scripted upstream responses.

        Returns (client_responses, receipt_dicts).
        """
        # Set up config
        config = GatewayConfig(
            upstream_command=["fake"],
            receipt_path=str(tmp_path / "receipts.jsonl"),
            deny_tools=deny_tools or [],
            default_policy=default_policy,
        )

        # Prepare client input
        client_in = io.StringIO()
        for msg in client_messages:
            write_message(client_in, msg)
        client_in.seek(0)

        client_out = io.StringIO()

        # Mock spawn + upstream I/O
        upstream_out = io.StringIO()
        for resp in upstream_responses:
            write_message(upstream_out, resp)
        upstream_out.seek(0)

        upstream_in = io.StringIO()

        gw = StdioGateway(config, client_in=client_in, client_out=client_out)

        # Patch spawn to use our mock streams
        def fake_spawn():
            gw._upstream_in = upstream_in
            gw._upstream_out = upstream_out
            gw._upstream_proc = MagicMock()
            gw._upstream_proc.stdin = upstream_in
            gw._upstream_proc.stdout = upstream_out
            gw._upstream_proc.stderr = None
            gw._upstream_proc.wait = MagicMock()

        with patch.object(gw, '_spawn_upstream', side_effect=fake_spawn):
            gw.run()

        # Parse client responses
        client_out.seek(0)
        responses = []
        while True:
            line = client_out.readline()
            if not line:
                break
            line = line.strip()
            if line:
                responses.append(json.loads(line))

        # Parse receipts
        receipt_path = tmp_path / "receipts.jsonl"
        receipts = []
        if receipt_path.exists():
            for line in receipt_path.read_text().strip().split("\n"):
                if line.strip():
                    receipts.append(json.loads(line))

        return responses, receipts

    def test_allow_echo(self, tmp_path):
        """Full transcript: init → list → call echo → receipt."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/list", {}, req_id=2),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "hello"}}, req_id=3),
        ]

        upstream_resps = [
            # init response
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            # tools/list response
            _result(2, {"tools": [
                {"name": "echo", "description": "Echo text", "inputSchema": {"type": "object"}},
            ]}),
            # tools/call echo response
            _result(3, {"content": [{"type": "text", "text": "hello"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        # Check client responses
        assert len(responses) >= 3  # init + list + call
        # init response
        assert responses[0].get("result", {}).get("serverInfo", {}).get("name") == "mcp-governor"
        # tools/list response
        assert len(responses[1].get("result", {}).get("tools", [])) == 1
        # tools/call response
        assert "result" in responses[2]

        # Check receipt
        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["decision"]["reason_code"] == "gov.policy_allow"
        assert r["tool"]["tool_id"] == "echo"
        assert r["tool"]["call_id"] == "3"
        assert r["chain"]["seq"] == 1

    def test_deny_shell(self, tmp_path):
        """tools/call shell.exec with deny policy → error + deny receipt."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "shell.exec", "arguments": {"cmd": "ls"}}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps,
            deny_tools=[r"shell\..*"])

        # Client should get init response + error for tools/call
        assert len(responses) >= 2
        call_resp = responses[-1]
        assert "error" in call_resp
        assert call_resp["error"]["code"] == -32601

        # Deny receipt
        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "deny"
        assert r["decision"]["reason_code"] == "gov.policy_deny"

    def test_tools_list_filters_denied(self, tmp_path):
        """tools/list should not show denied tools."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/list", {}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            _result(2, {"tools": [
                {"name": "echo", "description": "Echo"},
                {"name": "shell.exec", "description": "Shell"},
                {"name": "read_file", "description": "Read"},
            ]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps,
            deny_tools=[r"shell\..*"])

        list_resp = responses[1]
        tools = list_resp.get("result", {}).get("tools", [])
        names = [t["name"] for t in tools]
        assert "echo" in names
        assert "read_file" in names
        assert "shell.exec" not in names

    def test_chain_across_calls(self, tmp_path):
        """Two allowed tool calls should produce chained receipts."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "a"}}, req_id=2),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "b"}}, req_id=3),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            _result(2, {"content": [{"type": "text", "text": "a"}]}),
            _result(3, {"content": [{"type": "text", "text": "b"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        assert len(receipts) == 2
        assert receipts[0]["chain"]["seq"] == 1
        assert receipts[1]["chain"]["seq"] == 2
        assert receipts[1]["chain"]["parent_receipt_id"] == receipts[0]["receipt_id"]

    def test_int_call_id(self, tmp_path):
        """JSON-RPC id as int should be stringified in receipt."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "hi"}}, req_id=42),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            _result(42, {"content": [{"type": "text", "text": "hi"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        assert len(receipts) == 1
        assert receipts[0]["tool"]["call_id"] == "42"  # stringified

    def test_upstream_failure(self, tmp_path):
        """Upstream returning error → execution.status = failure."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "fail_tool", "arguments": {}}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            {"jsonrpc": "2.0", "id": 2,
             "error": {"code": -1, "message": "Tool execution failed"}},
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["execution"]["status"] == "failure"
        assert "failed" in r["execution"]["error"]

    def test_passthrough_warn(self, tmp_path):
        """allow-warn mode: denied tool still allowed, receipt shows passthrough."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "shell.exec", "arguments": {"cmd": "ls"}}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            _result(2, {"content": [{"type": "text", "text": "file1 file2"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps,
            deny_tools=[r"shell\..*"],
            default_policy="allow-warn")

        # Tool call should succeed (passthrough)
        assert "result" in responses[-1]

        # Receipt shows passthrough
        assert len(receipts) == 1
        assert receipts[0]["decision"]["action"] == "allow"
        assert receipts[0]["decision"]["reason_code"] == "gov.passthrough"

    def test_ext_fields_populated(self, tmp_path):
        """Receipt ext fields contain MCP identity info."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "my-agent", "version": "2.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "hi"}}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "my-server", "version": "3.0"},
            }),
            _result(2, {"content": [{"type": "text", "text": "hi"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        ext = receipts[0].get("ext", {})
        assert ext["gov.mcp.client.name"] == "my-agent"
        assert ext["gov.mcp.client.version"] == "2.0"
        assert ext["gov.mcp.server.name"] == "my-server"
        assert ext["gov.mcp.server.version"] == "3.0"
        assert ext["gov.mcp.protocol_version"] == "2024-11-05"
        assert ext["gov.mcp.upstream.server_id"] == "upstream"

    def test_receipt_valid(self, tmp_path):
        """Every receipt passes receipt_v1 verification."""
        from receipt_v1 import verify, verify_chain

        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "a"}}, req_id=2),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "b"}}, req_id=3),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
            _result(2, {"content": [{"type": "text", "text": "a"}]}),
            _result(3, {"content": [{"type": "text", "text": "b"}]}),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps)

        # Each receipt is individually valid
        for r in receipts:
            vr = verify(r)
            assert vr.valid, f"Receipt invalid: {vr.errors}"

        # Chain is valid
        if len(receipts) > 1:
            cr = verify_chain(receipts)
            assert cr.valid, f"Chain invalid: {cr.errors}"

    def test_deny_default_policy(self, tmp_path):
        """default_policy=deny blocks everything."""
        client_msgs = [
            _msg("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            }, req_id=1),
            _notif("notifications/initialized"),
            _msg("tools/call", {"name": "echo", "arguments": {"text": "hi"}}, req_id=2),
        ]

        upstream_resps = [
            _result(0, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1"},
            }),
        ]

        responses, receipts = self._run_gateway_with_transcript(
            tmp_path, client_msgs, upstream_resps,
            default_policy="deny")

        assert "error" in responses[-1]
        assert len(receipts) == 1
        assert receipts[0]["decision"]["action"] == "deny"
        assert receipts[0]["decision"]["reason_code"] == "gov.default_deny"
