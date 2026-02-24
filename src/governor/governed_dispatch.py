# SPDX-License-Identifier: Apache-2.0
"""
Governed dispatch — the enforcement membrane for composition governance.

One helper. One enforcement shape. Adapters (Guvnah, Maude, hooks) call
governed_dispatch() instead of touching transport directly.

Invariant: If preflight decision is "blocked", transport_call is NEVER invoked.

Flow:
    1. Caller builds PreflightRequest
    2. governed_dispatch() calls client.preflight() → PreflightDecision
    3. If blocked → return DispatchResult with blocked=True, no transport call
    4. If allowed → call transport_call() → capture result
    5. Call client.record() with result_status
    6. Return DispatchResult

The daemon is the judge; governed_dispatch is the bailiff.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Data types
# =============================================================================


@dataclass(frozen=True)
class PreflightRequest:
    """What the caller wants to do."""
    tool_id: str
    correlation_id: str
    args: dict[str, Any] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreflightDecision:
    """What the daemon decided."""
    decision: str               # "allow" | "would_block" | "blocked"
    preflight_token: str | None = None
    mode: str = "detect_only"
    block_reasons: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DispatchContext:
    """Passed to transport_call so it knows what was preflighted."""
    tool_id: str
    args: dict[str, Any]
    correlation_id: str
    preflight_decision: PreflightDecision


@dataclass(frozen=True)
class DispatchResult:
    """What came back from the whole governed dispatch cycle."""
    blocked: bool
    decision: str               # "allow" | "would_block" | "blocked"
    preflight_decision: PreflightDecision
    transport_result: Any = None
    result_status: str = "ok"   # "ok" | "failed" | "timeout"
    record_id: str | None = None
    error: str | None = None


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class PreflightClient(Protocol):
    """Transport-agnostic interface to the daemon's chain RPCs."""

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        """Call chain.preflight and return the decision."""
        ...

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Call chain.record after dispatch completes."""
        ...


# =============================================================================
# Error
# =============================================================================


class GovernanceError(Exception):
    """Raised when the governance membrane itself fails.

    NOT raised for blocked actions (that's a normal DispatchResult).
    Raised for: transport failures to the daemon, malformed responses,
    unexpected states.
    """

    def __init__(self, message: str, phase: str = "unknown", cause: Exception | None = None):
        super().__init__(message)
        self.phase = phase
        self.cause = cause


# =============================================================================
# The enforcement membrane
# =============================================================================


async def governed_dispatch(
    client: PreflightClient,
    request: PreflightRequest,
    transport_call,  # async (DispatchContext) -> Any
    *,
    record_id: str | None = None,
    fail_open: bool = False,
) -> DispatchResult:
    """One function. One enforcement shape. Every adapter calls this.

    Args:
        client: PreflightClient that talks to the daemon
        request: What the caller wants to do
        transport_call: async callable that does the actual tool dispatch
        record_id: Optional idempotency key for chain.record
        fail_open: If True, dispatch proceeds on preflight errors.
                   If False (default), preflight errors raise GovernanceError.

    Returns:
        DispatchResult — always. Blocked actions have blocked=True.

    Raises:
        GovernanceError: If the governance membrane itself fails
            (NOT for blocked actions — those are normal results).
    """
    # Generate record_id if not provided (for retry safety)
    if record_id is None:
        record_id = uuid.uuid4().hex

    # ---- Phase 1: Preflight ----
    try:
        decision = await client.preflight(request)
    except Exception as exc:
        if fail_open:
            logger.warning(
                "governed_dispatch: preflight failed (fail_open=True), "
                "proceeding without governance: %s",
                exc,
            )
            decision = PreflightDecision(
                decision="allow",
                mode="fail_open",
            )
        else:
            raise GovernanceError(
                f"Preflight failed: {exc}",
                phase="preflight",
                cause=exc,
            ) from exc

    # ---- Phase 2: Enforcement gate ----
    if decision.decision == "blocked":
        return DispatchResult(
            blocked=True,
            decision="blocked",
            preflight_decision=decision,
            result_status="blocked",
            record_id=record_id,
        )

    # ---- Phase 3: Dispatch ----
    context = DispatchContext(
        tool_id=request.tool_id,
        args=request.args,
        correlation_id=request.correlation_id,
        preflight_decision=decision,
    )

    result_status = "ok"
    transport_result = None
    error_msg = None

    try:
        transport_result = await transport_call(context)
    except Exception as exc:
        result_status = "failed"
        error_msg = str(exc)
        logger.warning(
            "governed_dispatch: transport_call failed for %s: %s",
            request.tool_id, exc,
        )

    # ---- Phase 4: Record ----
    try:
        await client.record(
            request,
            result_status=result_status,
            preflight_token=decision.preflight_token,
            record_id=record_id,
        )
    except Exception as exc:
        # Record failure is logged but does NOT block the result.
        # The tool already ran — failing the record would discard work
        # without preventing the side effect.
        logger.warning(
            "governed_dispatch: record failed for %s (tool already ran): %s",
            request.tool_id, exc,
        )

    return DispatchResult(
        blocked=False,
        decision=decision.decision,
        preflight_decision=decision,
        transport_result=transport_result,
        result_status=result_status,
        record_id=record_id,
        error=error_msg,
    )


# =============================================================================
# Daemon adapter
# =============================================================================


class DaemonPreflightClient:
    """PreflightClient that delegates to a daemon via an RPC caller.

    The rpc_call is a generic async function:
        async def rpc_call(method: str, params: dict) -> dict

    This works with any transport — Guvnah's child-process stdio,
    Maude's Unix socket, or the Dispatcher.dispatch() in tests.
    """

    def __init__(self, rpc_call) -> None:
        self._rpc = rpc_call

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        """Call chain.preflight and adapt the response."""
        params: dict[str, Any] = {
            "tool_id": request.tool_id,
            "correlation_id": request.correlation_id,
        }
        if request.args:
            params["args"] = request.args
        if request.exceptions:
            params["exceptions"] = request.exceptions

        resp = await self._rpc("chain.preflight", params)

        # The daemon returns the full preflight result dict.
        # Extract the fields we need for the decision.
        if "error" in resp:
            raise GovernanceError(
                f"chain.preflight returned error: {resp.get('message', resp['error'])}",
                phase="preflight",
            )

        return PreflightDecision(
            decision=resp.get("decision", "allow"),
            preflight_token=resp.get("preflight_token"),
            mode=resp.get("mode", "detect_only"),
            block_reasons=resp.get("block_reasons", []),
            raw=resp,
        )

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Call chain.record after dispatch completes."""
        params: dict[str, Any] = {
            "tool_id": request.tool_id,
            "correlation_id": request.correlation_id,
            "result_status": result_status,
        }
        if request.args:
            params["args"] = request.args
        if preflight_token:
            params["preflight_token"] = preflight_token
        if record_id:
            params["record_id"] = record_id

        resp = await self._rpc("chain.record", params)

        if "error" in resp:
            raise GovernanceError(
                f"chain.record returned error: {resp.get('message', resp['error'])}",
                phase="record",
            )

        return resp
