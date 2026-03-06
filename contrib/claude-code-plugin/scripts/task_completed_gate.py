#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TaskCompleted hook: gate task completion on governance conditions.

Reads Claude Code hook JSON from stdin, checks governance conditions,
exits 0 (allow) or 2 (reject with feedback).

Pass 2 (enforcement): refuses task completion if governance conditions
are not met.

NOT wired in hooks.json by default (Pass 1 is observe-only).
To enable, add TaskCompleted entries to hooks.json.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)  # Malformed input — allow completion

    # Check governor status
    try:
        result = subprocess.run(
            ["governor", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        sys.exit(0)  # Governor not available — allow completion

    try:
        status = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Unparseable — allow

    # Check for open violations
    violations = status.get("violations", {})
    pending = violations.get("pending", 0) if isinstance(violations, dict) else 0
    ok = violations.get("ok", True) if isinstance(violations, dict) else True

    if not ok or pending > 0:
        msg = (
            f"Governor: {pending} unresolved violation(s) must be addressed "
            f"before completing this task. Run /governor:check for details."
        )
        print(msg, file=sys.stderr)
        sys.exit(2)  # Reject — Claude gets feedback, continues working

    sys.exit(0)  # All clear


if __name__ == "__main__":
    main()
