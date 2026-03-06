#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PreToolUse hook: evaluate tool calls against governor policy.

Reads Claude Code hook JSON from stdin, checks against governor gate,
returns allow/deny decision. This is a dumb adapter — all policy logic
lives in governor.

Pass 2 (enforcement): blocks policy violations before tool execution.

NOT wired in hooks.json by default (Pass 1 is observe-only).
To enable, add PreToolUse entries to hooks.json.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)  # Malformed input — fail open (allow)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    # Build check request for governor
    check_input = json.dumps({
        "hook": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    })

    try:
        result = subprocess.run(
            ["governor", "gate", "check", "--format", "json", "-f", "/dev/stdin"],
            input=check_input,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        sys.exit(0)  # Governor not available — fail open

    # Parse governor's verdict
    try:
        verdict = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Unparseable response — fail open

    if verdict.get("verdict") == "block":
        # Deny the tool call
        reason = verdict.get("reason", "Blocked by governor policy")
        violations = verdict.get("violations", [])
        if violations:
            reason += ": " + "; ".join(
                v.get("description", v.get("anchor_id", ""))
                for v in violations[:3]
            )

        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        json.dump(output, sys.stdout)
        sys.exit(0)

    # Allow by default
    sys.exit(0)


if __name__ == "__main__":
    main()
