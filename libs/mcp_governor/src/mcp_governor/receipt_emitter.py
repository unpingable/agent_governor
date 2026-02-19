# SPDX-License-Identifier: Apache-2.0
"""Receipt emitter: wraps ReceiptBuilder + FileSink + ReceiptChain.

Translates gateway-internal types (ToolCallEnvelope, PolicyDecision) into
Receipt v1 records and writes them to a JSONL file.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from receipt_v1 import (
    Action,
    Actor,
    AuthContext,
    EffectsConfidence,
    ExecutionStatus,
    Provenance,
    ReceiptBuilder,
    ReceiptChain,
    Receipt,
)
from receipt_v1.canonical import uuid7

from mcp_governor.sinks import RotatingFileSink
from mcp_governor.types import ActorInfo, GatewaySession, PolicyDecision, ReasonCode

# Max keys shown in args_summary
_MAX_SUMMARY_KEYS = 10
# Max length for error strings
_MAX_ERROR_LEN = 256

# Heuristic patterns for secrets in strings (shared with receipt_v1)
_SECRET_PATTERNS = [
    re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:secret|password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(?:sk|pk|ak|rk)-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"(?:token|auth)\s*[:=]\s*[A-Za-z0-9\-._~+/]{20,}", re.IGNORECASE),
    re.compile(r"AWS[A-Z0-9]{10,}"),
]


def _sanitize_string(s: str, max_len: int = _MAX_ERROR_LEN) -> str:
    """Single-line, length-capped, secret-scrubbed."""
    # Single line
    s = s.replace("\n", " ").replace("\r", " ")
    # Truncate
    if len(s) > max_len:
        s = s[:max_len - 3] + "..."
    # Scrub secrets
    for pat in _SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s


def _args_summary(arguments: dict[str, Any]) -> str:
    """Keys-only summary of tool arguments. Never includes values."""
    keys = list(arguments.keys())
    if not keys:
        return "args: (empty)"
    if len(keys) <= _MAX_SUMMARY_KEYS:
        return f"args: {', '.join(keys)}"
    shown = keys[:_MAX_SUMMARY_KEYS]
    return f"args: {', '.join(shown)} (+{len(keys) - _MAX_SUMMARY_KEYS} more)"


def _command_hash(command: list[str]) -> str:
    """SHA-256 of the upstream command (never raw)."""
    h = hashlib.sha256()
    for part in command:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class ReceiptEmitter:
    """Emits Receipt v1 records for tool calls through the gateway.

    Manages a ReceiptChain for sequencing and a FileSink for persistence.
    Fail-closed: if receipt write fails, raises (caller must handle).
    """

    def __init__(
        self,
        receipt_path: str | Path,
        deployment_id: str = "local",
        governor_version: str = "0.1.0",
        upstream_command: list[str] | None = None,
        *,
        fsync: bool = True,
        max_bytes: int = 10 * 1024 * 1024,
        keep_files: int = 5,
    ) -> None:
        self._receipt_path = Path(receipt_path)
        self._deployment_id = deployment_id
        self._governor_version = governor_version
        self._upstream_command = upstream_command or []
        self._instance_id = f"mcp-gw-{os.getpid()}"
        self._chain = ReceiptChain()
        self._sink = RotatingFileSink(
            str(self._receipt_path),
            fsync=fsync,
            max_bytes=max_bytes,
            keep_files=keep_files,
        )

    @property
    def chain(self) -> ReceiptChain:
        return self._chain

    @property
    def receipt_path(self) -> Path:
        return self._receipt_path

    def emit(
        self,
        session: GatewaySession,
        envelope: "ToolCallEnvelope",
        decision: PolicyDecision,
        *,
        execution_status: ExecutionStatus | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> Receipt:
        """Build and write a receipt for a tool call decision.

        Args:
            session: Current gateway session (identity info).
            envelope: The tool call envelope.
            decision: The policy decision made.
            execution_status: Upstream execution status (None for deny).
            duration_ms: Upstream call wall-clock time in ms.
            error: Upstream error message (will be sanitized).

        Returns:
            The written Receipt.

        Raises:
            OSError: If receipt file write fails.
        """
        from mcp_governor.types import ToolCallEnvelope  # avoid circular at module level

        # Map gateway types → receipt_v1 types
        actor = Actor(
            agent_id=session.actor_info.client_name or "unknown",
            session_id=session.session_id,
            auth_context=AuthContext.STDIO,
        )

        action = Action.ALLOW if decision.allow else Action.DENY

        provenance = Provenance(
            deployment_id=self._deployment_id,
            instance_id=self._instance_id,
            governor_version=self._governor_version,
        )

        # Build ext fields
        ext: dict[str, Any] = {}
        ai = session.actor_info
        if ai.protocol_version:
            ext["gov.mcp.protocol_version"] = ai.protocol_version
        if ai.client_name:
            ext["gov.mcp.client.name"] = ai.client_name
        if ai.client_version:
            ext["gov.mcp.client.version"] = ai.client_version
        if ai.server_name:
            ext["gov.mcp.server.name"] = ai.server_name
        if ai.server_version:
            ext["gov.mcp.server.version"] = ai.server_version
        if self._upstream_command:
            ext["gov.mcp.upstream.command_hash"] = _command_hash(self._upstream_command)
        ext["gov.mcp.upstream.server_id"] = envelope.server_id

        # Build receipt
        builder = ReceiptBuilder()
        builder.actor(actor)
        builder.tool(
            envelope.tool_id,
            envelope.arguments,
            call_id=envelope.call_id,
            args_summary=_args_summary(envelope.arguments),
        )
        builder.decision(
            action,
            decision.reason_code.value,
            reason_human=_sanitize_string(decision.reason_human) if decision.reason_human else None,
        )

        if execution_status is not None:
            sanitized_error = _sanitize_string(error) if error else None
            builder.execution(
                execution_status,
                duration_ms=duration_ms,
                error=sanitized_error,
                effects_confidence=EffectsConfidence.NONE,
            )

        builder.provenance(provenance)
        if ext:
            builder.ext(ext)

        receipt = builder.build(self._chain.next())
        self._chain.append(receipt)
        self._sink.write(receipt)
        return receipt
