# SPDX-License-Identifier: Apache-2.0
"""MCP Governor Gateway: policy-enforcing proxy for MCP tool servers.

Sits between any MCP client (agent runtime) and any MCP tool server,
enforcing allow/deny policy and emitting Receipt v1 records for every
tool invocation.

Phase 0: stdio transport, single upstream, allow/deny only, FileSink JSONL.
"""

__version__ = "0.1.0"

from mcp_governor.config import GatewayConfig
from mcp_governor.gateway import StdioGateway
from mcp_governor.policy import PolicyEngine
from mcp_governor.receipt_emitter import ReceiptEmitter
from mcp_governor.types import ActorInfo, PolicyDecision, ToolCallEnvelope

__all__ = [
    "GatewayConfig",
    "StdioGateway",
    "PolicyEngine",
    "ReceiptEmitter",
    "ActorInfo",
    "PolicyDecision",
    "ToolCallEnvelope",
]
