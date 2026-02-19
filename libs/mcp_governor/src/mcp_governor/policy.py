# SPDX-License-Identifier: Apache-2.0
"""Policy engine: allow/deny decisions from deny-list regex patterns.

Phase 0: no transforms, no escalation, no budgets.
"""

from __future__ import annotations

import re
from typing import Sequence

from mcp_governor.types import PolicyDecision, ReasonCode


class PolicyEngine:
    """Evaluates tool names against a deny-list of regex patterns.

    Three modes (set by ``default_policy``):

    - ``"allow"``      — allow unless explicitly denied
    - ``"deny"``       — deny unless *not* matching any deny pattern
                         (with empty deny list, everything is denied)
    - ``"allow-warn"`` — allow everything, but tag denied tools as passthrough
    """

    def __init__(
        self,
        deny_tools: Sequence[str] = (),
        default_policy: str = "allow",
    ) -> None:
        if default_policy not in ("allow", "deny", "allow-warn"):
            raise ValueError(f"Invalid default_policy: {default_policy!r}")
        self._default_policy = default_policy
        self._deny_patterns: list[tuple[str, re.Pattern[str]]] = []
        for pat_str in deny_tools:
            try:
                compiled = re.compile(pat_str)
            except re.error as e:
                raise ValueError(f"Invalid deny regex {pat_str!r}: {e}") from e
            self._deny_patterns.append((pat_str, compiled))

    def evaluate(self, tool_name: str) -> PolicyDecision:
        """Evaluate whether a tool call should be allowed or denied."""
        # Check deny patterns
        for pat_str, compiled in self._deny_patterns:
            if compiled.fullmatch(tool_name):
                if self._default_policy == "allow-warn":
                    # Passthrough mode: allow but tag
                    return PolicyDecision(
                        allow=True,
                        reason_code=ReasonCode.PASSTHROUGH,
                        reason_human=f"Would deny ({pat_str}) but passthrough mode active",
                        matched_pattern=pat_str,
                    )
                return PolicyDecision(
                    allow=False,
                    reason_code=ReasonCode.POLICY_DENY,
                    reason_human=f"Tool matches deny pattern: {pat_str}",
                    matched_pattern=pat_str,
                )

        # No deny pattern matched
        if self._default_policy == "deny":
            return PolicyDecision(
                allow=False,
                reason_code=ReasonCode.DEFAULT_DENY,
                reason_human="Default policy is deny and no allow rule matched",
            )

        return PolicyDecision(
            allow=True,
            reason_code=ReasonCode.POLICY_ALLOW,
            reason_human="Tool not in deny list",
        )

    def filter_tools(self, tool_names: Sequence[str]) -> list[str]:
        """Return tool names that would be allowed (for tools/list filtering).

        In allow-warn mode, all tools pass through (passthrough-warn doesn't hide).
        """
        return [name for name in tool_names if self.evaluate(name).allow]
