# SPDX-License-Identifier: Apache-2.0
"""Receipt v1 bridge: dual-emit receipt_v1 alongside gate_receipt.

Hooks into the evidence gate (and optionally wrapper) to emit structured
Receipt v1 records in parallel with the existing GateReceipt system.

Design principles:
- **Dual-emit**: gate_receipt continues as-is; receipt_v1 is additive
- **One toggle**: GOV_RECEIPT_V1=1 env var or config flag
- **One sink**: JSONL file via receipt_v1.sinks.FileSink
- **Fail-open**: receipt_v1 emission errors are logged, never block the gate
- **Chain state**: per session_id with LRU cap (default 128 sessions)

Mapping (gate_receipt → receipt_v1):
  gate_receipt.gate           → tool_id = "gov.{gate}"
  gate_receipt.verdict        → decision.action (pass→ALLOW, block→DENY, warn→ALLOW)
  gate_receipt.subject_hash   → tool.args_hash (reused, same SHA-256 hex)
  gate_receipt.evidence_hash  → ext.gov.evidence_hash
  gate_receipt.policy_hash    → ext.gov.policy_hash
  gate_receipt.receipt_id     → ext.gov.legacy_receipt_id
  gate_receipt.principal_id   → actor.agent_id
  gate_receipt.tenant_id      → actor.session_id fallback
  EvidenceGateStatus          → decision.reason_code (gov.pass/gov.blocked/gov.warn)
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Verdict → Receipt v1 mapping
# =============================================================================

# Gate verdict → receipt_v1 Action + reason_code
_VERDICT_MAP: dict[str, tuple[str, str]] = {
    "pass":  ("allow", "gov.passthrough"),
    "warn":  ("allow", "gov.warn"),
    "block": ("deny",  "gov.blocked"),
}


# =============================================================================
# Chain state (per session_id, LRU-bounded)
# =============================================================================

@dataclass
class _ChainHead:
    """Tracks the head of a receipt chain for one session."""
    seq: int
    last_receipt_id: str
    last_receipt_hash: str


class _ChainTracker:
    """LRU-bounded chain state per session_id.

    When the cap is exceeded, the oldest session's chain is evicted.
    A new receipt in an evicted session starts a new chain (seq=1)
    and gets stamped with ext.gov.chain_reset="lru_evict" so the
    discontinuity is distinguishable from tampering.
    """

    def __init__(self, max_sessions: int = 128):
        self._heads: OrderedDict[str, _ChainHead] = OrderedDict()
        self._evicted: set[str] = set()  # session_ids that were evicted
        self._max = max_sessions

    def get(self, session_id: str) -> _ChainHead | None:
        """Get chain head for session, promoting to most-recent."""
        if session_id in self._heads:
            self._heads.move_to_end(session_id)
            return self._heads[session_id]
        return None

    def was_evicted(self, session_id: str) -> bool:
        """True if this session was previously evicted (chain reset)."""
        return session_id in self._evicted

    def advance(self, session_id: str, receipt_id: str, receipt_hash: str) -> None:
        """Record a new receipt as the chain head."""
        head = self.get(session_id)
        if head is None:
            self._heads[session_id] = _ChainHead(
                seq=1,
                last_receipt_id=receipt_id,
                last_receipt_hash=receipt_hash,
            )
            # Clear eviction flag once the new chain starts
            self._evicted.discard(session_id)
        else:
            head.seq += 1
            head.last_receipt_id = receipt_id
            head.last_receipt_hash = receipt_hash

        # Evict oldest if over cap
        while len(self._heads) > self._max:
            evicted_sid, _ = self._heads.popitem(last=False)
            self._evicted.add(evicted_sid)

    def next_seq(self, session_id: str) -> int:
        """What the next seq will be for this session."""
        head = self.get(session_id)
        return 1 if head is None else head.seq + 1


# =============================================================================
# Bridge context (what the caller provides)
# =============================================================================

@dataclass
class BridgeContext:
    """Context for a receipt_v1 emission.

    Callers populate what they know; the bridge fills defaults for the rest.
    """
    # Who
    agent_id: str = "local"
    session_id: str = "default"
    auth_context: str | None = None  # "stdio", "oauth", etc.

    # What tool call is being governed
    gate: str = "evidence_gate"
    tool_args: Any = None  # Original tool args (for args_hash)
    tool_version: str | None = None
    call_id: str | None = None
    args_summary: str | None = None

    # Decision details
    verdict: str = "pass"  # gate_receipt verdict: "pass" | "warn" | "block"
    reason_human: str | None = None
    blocking_reasons: list[str] | None = None

    # Legacy correlation
    legacy_receipt_id: str | None = None
    evidence_hash: str | None = None
    policy_hash: str | None = None
    subject_hash: str | None = None

    # Execution (only for allow/transform outcomes)
    execution_status: str | None = None  # "success", "failure", "timeout"
    attempt: int = 1
    duration_ms: int | None = None
    side_effects: list[str] | None = None
    error: str | None = None
    sanitized_result: Any = None


# =============================================================================
# Bridge
# =============================================================================

class ReceiptV1Bridge:
    """Emits Receipt v1 records alongside existing gate receipts.

    Usage:
        bridge = ReceiptV1Bridge(gov_dir=Path(".governor"))
        if bridge.enabled:
            bridge.emit(BridgeContext(
                agent_id="claude",
                session_id="sess-123",
                gate="evidence_gate",
                verdict="block",
                reason_human="HARD claim lacks evidence",
                legacy_receipt_id="abc123...",
            ))

    Toggle:
        - Set GOV_RECEIPT_V1=1 environment variable, OR
        - Pass enabled=True to constructor
    """

    def __init__(
        self,
        gov_dir: Path,
        *,
        enabled: bool | None = None,
        deployment_id: str = "local",
        instance_id: str | None = None,
        max_sessions: int = 128,
        fsync: bool = True,
        fail_closed: bool = False,
    ):
        # Toggle: explicit arg > env var > off
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = os.environ.get("GOV_RECEIPT_V1", "").strip() == "1"

        self._gov_dir = gov_dir
        self._deployment_id = deployment_id
        self._instance_id = instance_id or f"gov-{os.getpid()}"
        self._chains = _ChainTracker(max_sessions)
        self._fsync = fsync
        self._fail_closed = fail_closed
        self._sink = None  # Lazy init

        # Import governor version at init (not per-call)
        self._governor_version = "2.3.0"
        try:
            import importlib.metadata
            self._governor_version = importlib.metadata.version("governor")
        except Exception:
            pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_sink(self) -> Any:
        """Lazy-init the FileSink (avoids import if disabled)."""
        if self._sink is None:
            from receipt_v1.sinks import FileSink
            path = self._gov_dir / "receipts" / "receipt_v1.jsonl"
            self._sink = FileSink(path, fsync=self._fsync)
        return self._sink

    def emit(self, ctx: BridgeContext) -> str | None:
        """Emit a Receipt v1 record from bridge context.

        Returns the receipt_id on success, None on failure.
        Failures are logged but never raise (unless fail_closed=True).
        """
        if not self._enabled:
            return None

        try:
            return self._do_emit(ctx)
        except Exception as exc:
            logger.warning(
                "receipt_v1 bridge emission failed: %s "
                "[session_id=%s call_id=%s gate=%s]",
                exc, ctx.session_id, ctx.call_id, ctx.gate,
            )
            if self._fail_closed:
                raise
            return None

    def _do_emit(self, ctx: BridgeContext) -> str:
        """Build and write the receipt. Raises on any error."""
        from receipt_v1.canonical import args_hash as compute_args_hash
        from receipt_v1.receipt import ReceiptBuilder
        from receipt_v1.types import (
            Action,
            Actor,
            AuthContext,
            Chain,
            ExecutionStatus,
            Provenance,
        )

        # ── Actor ────────────────────────────────────────────────────
        auth = None
        if ctx.auth_context:
            try:
                auth = AuthContext(ctx.auth_context)
            except ValueError:
                pass

        actor = Actor(
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
            auth_context=auth,
        )

        # ── Tool ─────────────────────────────────────────────────────
        tool_id = f"gov.{ctx.gate}"
        # If caller provided raw tool_args, we hash them properly.
        # Otherwise fall back to the subject_hash from gate_receipt.
        tool_args = ctx.tool_args if ctx.tool_args is not None else {"subject_hash": ctx.subject_hash or "unknown"}

        # ── Decision ─────────────────────────────────────────────────
        action_str, reason_code = _VERDICT_MAP.get(ctx.verdict, ("deny", "gov.unknown"))
        action = Action(action_str)

        # Build a human-readable reason
        reason_human = ctx.reason_human
        if reason_human is None and ctx.blocking_reasons:
            reason_human = "; ".join(ctx.blocking_reasons[:3])

        # ── Chain ────────────────────────────────────────────────────
        chain_reset = self._chains.was_evicted(ctx.session_id)
        head = self._chains.get(ctx.session_id)
        if head is None:
            chain = Chain(seq=1)
        else:
            chain = Chain(
                seq=head.seq + 1,
                parent_receipt_id=head.last_receipt_id,
                parent_receipt_hash=head.last_receipt_hash,
            )

        # ── Provenance ───────────────────────────────────────────────
        provenance = Provenance(
            deployment_id=self._deployment_id,
            instance_id=self._instance_id,
            governor_version=self._governor_version,
        )

        # ── Build receipt ────────────────────────────────────────────
        builder = (
            ReceiptBuilder()
            .actor(actor)
            .tool(
                tool_id, tool_args,
                tool_version=ctx.tool_version,
                call_id=ctx.call_id,
                args_summary=ctx.args_summary,
            )
            .decision(
                action, reason_code,
                reason_human=reason_human,
            )
            .provenance(provenance)
        )

        # ── Execution (only for allow/transform) ────────────────────
        if ctx.execution_status is not None and action in (Action.ALLOW, Action.TRANSFORM):
            try:
                ex_status = ExecutionStatus(ctx.execution_status)
            except ValueError:
                ex_status = ExecutionStatus.FAILURE
            builder.execution(
                ex_status,
                attempt=ctx.attempt,
                duration_ms=ctx.duration_ms,
                side_effects=ctx.side_effects,
                error=ctx.error,
                sanitized_result=ctx.sanitized_result,
            )

        # ── ext: correlate with legacy receipt + chain reset marker ──
        ext: dict[str, Any] = {}
        if ctx.legacy_receipt_id:
            ext["gov.legacy_receipt_id"] = ctx.legacy_receipt_id
        if ctx.evidence_hash:
            ext["gov.evidence_hash"] = ctx.evidence_hash
        if ctx.policy_hash:
            ext["gov.policy_hash"] = ctx.policy_hash
        if chain_reset:
            ext["gov.chain_reset"] = "lru_evict"
        if ext:
            builder.ext(ext)

        # ── Emit ─────────────────────────────────────────────────────
        receipt = builder.build(chain)
        self._get_sink().write(receipt)

        # ── Update chain state ───────────────────────────────────────
        self._chains.advance(ctx.session_id, receipt.receipt_id, receipt.receipt_hash)

        logger.debug(
            "receipt_v1 emitted: id=%s seq=%d gate=%s verdict=%s",
            receipt.receipt_id[:12], chain.seq, ctx.gate, ctx.verdict,
        )

        return receipt.receipt_id
