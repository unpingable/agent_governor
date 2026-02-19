# SPDX-License-Identifier: Apache-2.0
"""Newline-delimited JSON-RPC framing for MCP stdio transport.

Per MCP spec: stdio transport uses newline-delimited JSON-RPC.
Messages MUST NOT contain embedded newlines.
One line = one message.
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any


def read_message(stream: IO[str]) -> dict[str, Any] | None:
    """Read one newline-delimited JSON-RPC message from a text stream.

    Returns None on EOF (empty line or stream closed).
    Raises ValueError on malformed JSON.
    """
    line = stream.readline()
    if not line:
        return None
    line = line.rstrip("\n\r")
    if not line:
        return None
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON-RPC message: {e}") from e
    if not isinstance(msg, dict):
        raise ValueError(f"JSON-RPC message must be an object, got {type(msg).__name__}")
    return msg


def write_message(stream: IO[str], msg: dict[str, Any]) -> None:
    """Write one newline-delimited JSON-RPC message to a text stream.

    Uses compact separators to ensure no embedded newlines.
    Flushes after write.
    """
    line = json.dumps(msg, separators=(",", ":"), ensure_ascii=True)
    stream.write(line + "\n")
    stream.flush()
