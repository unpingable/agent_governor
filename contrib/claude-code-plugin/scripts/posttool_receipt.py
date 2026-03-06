#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PostToolUse hook: emit a governor receipt for tool actions.

Reads Claude Code hook JSON from stdin, emits a gate receipt via the
governor CLI. This is a dumb adapter — all policy logic lives in governor.

Pass 1 (observe only): receipts for writes and shell commands.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return  # Malformed input — fail open

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    tool_response = payload.get("tool_response", {})
    session_id = payload.get("session_id", "unknown")

    # Build evidence for the receipt
    evidence = {
        "hook": "PostToolUse",
        "tool_name": tool_name,
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        evidence["command"] = command
        evidence["command_hash"] = hashlib.sha256(command.encode()).hexdigest()[:16]
        subject = f"bash:{command[:80]}"

    elif tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        evidence["file_path"] = file_path
        if tool_name == "Write":
            content = tool_input.get("content", "")
            evidence["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
        elif tool_name == "Edit":
            old = tool_input.get("old_string", "")
            new = tool_input.get("new_string", "")
            evidence["edit_hash"] = hashlib.sha256(
                f"{old}→{new}".encode()
            ).hexdigest()[:16]
        subject = f"{tool_name.lower()}:{file_path}"

    else:
        # Unknown tool — still receipt it but with minimal evidence
        subject = f"{tool_name.lower()}:unknown"

    # Emit receipt via governor CLI (fail-open: if governor isn't installed
    # or .governor/ doesn't exist, just silently continue)
    try:
        subprocess.run(
            [
                "governor", "gate", "check",
                "--format", "json",
                "-f", "/dev/stdin",
            ],
            input=json.dumps({
                "tool_action": subject,
                "evidence": evidence,
            }),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass  # Fail open — governor not available


if __name__ == "__main__":
    main()
