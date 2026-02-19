# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures for mcp_governor tests."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_receipt_path(tmp_path: Path) -> Path:
    return tmp_path / "receipts.jsonl"


@pytest.fixture
def tmp_config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.toml"


def make_jsonrpc_request(
    method: str, params: dict[str, Any] | None = None, req_id: Any = 1
) -> str:
    """Create a newline-terminated JSON-RPC request string."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, separators=(",", ":")) + "\n"


def make_jsonrpc_notification(method: str, params: dict[str, Any] | None = None) -> str:
    """Create a newline-terminated JSON-RPC notification (no id)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, separators=(",", ":")) + "\n"


def make_jsonrpc_result(req_id: Any, result: Any) -> str:
    """Create a newline-terminated JSON-RPC result string."""
    msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
    return json.dumps(msg, separators=(",", ":")) + "\n"


def parse_responses(output: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON-RPC responses."""
    results = []
    for line in output.strip().split("\n"):
        if line.strip():
            results.append(json.loads(line))
    return results
