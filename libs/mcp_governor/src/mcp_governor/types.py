# SPDX-License-Identifier: Apache-2.0
"""MCP-independent internal types for the gateway.

These types represent the gateway's internal model of a tool call and
its policy decision.  They never import MCP types — the gateway converts
JSON-RPC messages to/from these envelopes at the protocol boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReasonCode(str, Enum):
    """Unambiguous reason codes for policy decisions."""
    POLICY_ALLOW = "gov.policy_allow"
    PASSTHROUGH = "gov.passthrough"
    POLICY_DENY = "gov.policy_deny"
    DEFAULT_DENY = "gov.default_deny"


@dataclass(frozen=True)
class ActorInfo:
    """Captured identity from MCP initialize handshake.

    Populated after the client sends ``initialize`` and the upstream
    tool server responds.
    """
    client_name: str | None = None
    client_version: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None


@dataclass(frozen=True)
class ToolCallEnvelope:
    """Internal representation of an inbound tools/call request.

    Created from the JSON-RPC message before policy evaluation.
    """
    tool_name: str
    arguments: dict[str, Any]
    call_id: str  # JSON-RPC id, always stringified
    server_id: str = "upstream"  # Phase 0: always "upstream"

    @property
    def tool_id(self) -> str:
        """Qualified tool identifier for receipts."""
        return self.tool_name


@dataclass(frozen=True)
class PolicyDecision:
    """Result of policy evaluation for a tool call."""
    allow: bool
    reason_code: ReasonCode
    reason_human: str | None = None
    matched_pattern: str | None = None  # The deny regex that matched, if any


@dataclass
class GatewaySession:
    """Mutable state for one gateway session (one initialize lifecycle)."""
    session_id: str  # uuid7, generated at initialize
    actor_info: ActorInfo = field(default_factory=ActorInfo)
    initialized: bool = False
