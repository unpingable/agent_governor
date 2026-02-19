# SPDX-License-Identifier: Apache-2.0
"""Golden demo trace tests.

Runs each demo scenario as a subprocess transcript through the gateway,
verifies receipt files are correct.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from receipt_v1 import verify, verify_chain

# Path to the demos/echo_server.py
DEMOS_DIR = Path(__file__).parent.parent / "demos"
CONFIG_DIR = Path(__file__).parent.parent / "config"


def _run_gateway(
    config_path: Path,
    transcript: str,
    receipt_path: Path,
) -> tuple[list[dict], list[dict]]:
    """Run the gateway as a subprocess with a scripted transcript.

    Returns (responses, receipts).
    """
    proc = subprocess.run(
        [sys.executable, "-m", "mcp_governor", str(config_path)],
        input=transcript,
        capture_output=True,
        text=True,
        timeout=15,
    )

    responses = []
    for line in proc.stdout.strip().split("\n"):
        if line.strip():
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    receipts = []
    if receipt_path.exists():
        for line in receipt_path.read_text().strip().split("\n"):
            if line.strip():
                receipts.append(json.loads(line))

    return responses, receipts


class TestDemoAllow:
    def test_allow_demo(self, tmp_path):
        """Demo: allow all tools → receipt with action=allow."""
        receipt_file = tmp_path / "receipts.jsonl"
        config = tmp_path / "config.toml"
        config.write_text(f"""
[gateway]
agent_id = "demo-agent"
receipt_path = "{receipt_file}"

[upstream]
command = ["{sys.executable}", "{DEMOS_DIR / 'echo_server.py'}"]

[policy]
default_policy = "allow"
""")

        transcript = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
            '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"text":"Hello!"}}}\n'
        )

        responses, receipts = _run_gateway(config, transcript, receipt_file)

        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["tool"]["tool_id"] == "echo"
        vr = verify(r)
        assert vr.valid, f"Invalid: {vr.errors}"


class TestDemoDeny:
    def test_deny_demo(self, tmp_path):
        """Demo: deny shell_exec → receipt with action=deny."""
        receipt_file = tmp_path / "receipts.jsonl"
        config = tmp_path / "config.toml"
        config.write_text(f"""
[gateway]
agent_id = "demo-agent"
receipt_path = "{receipt_file}"

[upstream]
command = ["{sys.executable}", "{DEMOS_DIR / 'echo_server.py'}"]

[policy]
default_policy = "allow"
deny_tools = ["shell_exec"]
""")

        transcript = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"shell_exec","arguments":{"command":"rm -rf /"}}}\n'
        )

        responses, receipts = _run_gateway(config, transcript, receipt_file)

        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "deny"
        assert r["decision"]["reason_code"] == "gov.policy_deny"
        vr = verify(r)
        assert vr.valid, f"Invalid: {vr.errors}"

        # Client should have received an error
        call_resp = [r for r in responses if r.get("id") == 2]
        assert len(call_resp) == 1
        assert "error" in call_resp[0]


class TestDemoPassthrough:
    def test_passthrough_demo(self, tmp_path):
        """Demo: allow-warn → denied tool allowed with passthrough reason."""
        receipt_file = tmp_path / "receipts.jsonl"
        config = tmp_path / "config.toml"
        config.write_text(f"""
[gateway]
agent_id = "demo-agent"
receipt_path = "{receipt_file}"

[upstream]
command = ["{sys.executable}", "{DEMOS_DIR / 'echo_server.py'}"]

[policy]
default_policy = "allow-warn"
deny_tools = ["shell_exec"]
""")

        transcript = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"shell_exec","arguments":{"command":"ls -la"}}}\n'
        )

        responses, receipts = _run_gateway(config, transcript, receipt_file)

        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["decision"]["reason_code"] == "gov.passthrough"
        vr = verify(r)
        assert vr.valid, f"Invalid: {vr.errors}"

        # Tool should have succeeded
        call_resp = [r for r in responses if r.get("id") == 2]
        assert len(call_resp) == 1
        assert "result" in call_resp[0]


class TestDemoChain:
    def test_multi_call_chain(self, tmp_path):
        """Multiple tool calls produce a valid receipt chain."""
        receipt_file = tmp_path / "receipts.jsonl"
        config = tmp_path / "config.toml"
        config.write_text(f"""
[gateway]
agent_id = "demo-agent"
receipt_path = "{receipt_file}"

[upstream]
command = ["{sys.executable}", "{DEMOS_DIR / 'echo_server.py'}"]

[policy]
default_policy = "allow"
""")

        transcript = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"echo","arguments":{"text":"first"}}}\n'
            '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"read_file","arguments":{"path":"/etc/hosts"}}}\n'
            '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"echo","arguments":{"text":"third"}}}\n'
        )

        responses, receipts = _run_gateway(config, transcript, receipt_file)

        assert len(receipts) == 3
        cr = verify_chain(receipts)
        assert cr.valid, f"Chain invalid: {cr.errors}"


class TestDemoHostile:
    def test_hostile_upstream(self, tmp_path):
        """Upstream error with big message → sanitized in receipt."""
        receipt_file = tmp_path / "receipts.jsonl"
        config = tmp_path / "config.toml"

        # Write a hostile echo server that returns a huge error
        hostile_server = tmp_path / "hostile_server.py"
        hostile_server.write_text('''
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":req_id,"result":{
            "protocolVersion":"2024-11-05","capabilities":{"tools":{}},
            "serverInfo":{"name":"hostile","version":"0.1"}}},separators=(",",":"))+"\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        big_err = "Error: api_key=sk-" + "A"*100 + " " + "x"*500
        sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":req_id,
            "error":{"code":-1,"message":big_err}},separators=(",",":"))+"\\n")
        sys.stdout.flush()
''')

        config.write_text(f"""
[gateway]
agent_id = "demo-agent"
receipt_path = "{receipt_file}"

[upstream]
command = ["{sys.executable}", "{hostile_server}"]

[policy]
default_policy = "allow"
""")

        transcript = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"bad_tool","arguments":{"big":"' + 'x' * 1000 + '"}}}\n'
        )

        responses, receipts = _run_gateway(config, transcript, receipt_file)

        assert len(receipts) == 1
        r = receipts[0]
        # Error should be sanitized
        err = r.get("execution", {}).get("error", "")
        assert len(err) <= 256
        assert "sk-" not in err
        # Receipt should still be valid
        vr = verify(r)
        assert vr.valid, f"Invalid: {vr.errors}"
