# SPDX-License-Identifier: Apache-2.0
"""Trivial MCP tool server for demos and testing.

Implements 3 tools:
  - echo: returns the input text
  - read_file: returns a fake file content
  - shell_exec: returns a fake shell output

Speaks newline-delimited JSON-RPC on stdio.
"""

from __future__ import annotations

import json
import sys
from typing import Any

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the input text back",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file (fake implementation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "shell_exec",
        "description": "Execute a shell command (fake implementation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
            },
            "required": ["command"],
        },
    },
]


def _write(msg: dict[str, Any]) -> None:
    line = json.dumps(msg, separators=(",", ":"), ensure_ascii=True)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _result(req_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id: Any, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _handle_tools_call(req_id: Any, params: dict[str, Any]) -> None:
    name = params.get("name", "")
    args = params.get("arguments", {})

    if name == "echo":
        text = args.get("text", "")
        _result(req_id, {
            "content": [{"type": "text", "text": text}],
        })
    elif name == "read_file":
        path = args.get("path", "/unknown")
        _result(req_id, {
            "content": [{"type": "text", "text": f"Contents of {path}: [fake data]"}],
        })
    elif name == "shell_exec":
        cmd = args.get("command", "")
        _result(req_id, {
            "content": [{"type": "text", "text": f"$ {cmd}\n[fake output]"}],
        })
    else:
        _error(req_id, -32601, f"Unknown tool: {name}")


def main() -> None:
    print("[echo-server] Starting", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            _result(req_id, {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "0.1.0"},
            })
        elif method == "notifications/initialized":
            pass  # notification, no response
        elif method == "tools/list":
            _result(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            _handle_tools_call(req_id, params)
        elif method == "ping":
            _result(req_id, {})
        else:
            if req_id is not None:
                _error(req_id, -32601, f"Unknown method: {method}")

    print("[echo-server] EOF, exiting", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
