# SPDX-License-Identifier: Apache-2.0
"""TOML configuration loader for the MCP Governor Gateway."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration for a single gateway instance.

    Loaded from a TOML file with three sections:
    [gateway], [upstream], [policy].
    """
    # [gateway]
    agent_id: str = "local-dev"
    auth_context: str = "stdio"
    receipt_path: str = "./receipts/gateway.jsonl"
    deployment_id: str = "local"

    # [upstream]
    upstream_command: list[str] = field(default_factory=list)

    # [policy]
    default_policy: str = "allow"  # "allow" | "deny" | "allow-warn"
    deny_tools: list[str] = field(default_factory=list)  # regex patterns

    def __post_init__(self) -> None:
        if self.default_policy not in ("allow", "deny", "allow-warn"):
            raise ValueError(
                f"default_policy must be 'allow', 'deny', or 'allow-warn', "
                f"got {self.default_policy!r}"
            )

    @classmethod
    def from_toml(cls, path: str | Path) -> GatewayConfig:
        """Load configuration from a TOML file."""
        path = Path(path)
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return cls._from_dict(raw)

    @classmethod
    def from_toml_string(cls, text: str) -> GatewayConfig:
        """Load configuration from a TOML string (for testing)."""
        raw = tomllib.loads(text)
        return cls._from_dict(raw)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> GatewayConfig:
        gw = raw.get("gateway", {})
        up = raw.get("upstream", {})
        pol = raw.get("policy", {})

        kwargs: dict[str, Any] = {}

        # [gateway] section
        if "agent_id" in gw:
            kwargs["agent_id"] = str(gw["agent_id"])
        if "auth_context" in gw:
            kwargs["auth_context"] = str(gw["auth_context"])
        if "receipt_path" in gw:
            kwargs["receipt_path"] = str(gw["receipt_path"])
        if "deployment_id" in gw:
            kwargs["deployment_id"] = str(gw["deployment_id"])

        # [upstream] section
        if "command" in up:
            cmd = up["command"]
            if isinstance(cmd, str):
                kwargs["upstream_command"] = [cmd]
            elif isinstance(cmd, list):
                kwargs["upstream_command"] = [str(c) for c in cmd]
            else:
                raise ValueError(f"upstream.command must be a string or list, got {type(cmd)}")

        # [policy] section
        if "default_policy" in pol:
            kwargs["default_policy"] = str(pol["default_policy"])
        if "deny_tools" in pol:
            dt = pol["deny_tools"]
            if not isinstance(dt, list):
                raise ValueError("policy.deny_tools must be a list")
            kwargs["deny_tools"] = [str(p) for p in dt]

        return cls(**kwargs)
