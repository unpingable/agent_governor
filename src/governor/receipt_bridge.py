# SPDX-License-Identifier: Apache-2.0
"""Bridge adapter: emit receipt_kernel events from agent_gov workflows.

This adapter lets agent_gov emit hash-chained events in parallel with
its existing JSONL receipt system. It does NOT replace existing receipts —
it adds a second, richer audit trail.

Usage:
    from governor.receipt_bridge import ReceiptKernelBridge
    from receipt_kernel.store_sqlite import SqliteReceiptStore

    store = SqliteReceiptStore(str(gov_dir / "receipt_kernel.db"))
    store.initialize_schema()
    bridge = ReceiptKernelBridge(store=store, policy_id="evidence_gate", ...)
    bridge.run_start(run_id, "START", {"mode": "code"})
    ...
    bridge.run_finalize(run_id, "FINALIZE", "pass", {})
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from receipt_kernel.envelope import make_envelope
    from receipt_kernel.store_sqlite import SqliteReceiptStore
    from receipt_kernel.types import BlobRef

    RECEIPT_KERNEL_AVAILABLE = True
except ImportError:
    RECEIPT_KERNEL_AVAILABLE = False
    SqliteReceiptStore = None  # type: ignore[assignment,misc]
    BlobRef = None  # type: ignore[assignment,misc]


@dataclass
class KernelStatus:
    """Status of the receipt kernel for run summaries.

    When kernel is disabled, this provides a machine-checkable marker
    that prevents silent green. Any overall verdict path MUST check this.
    """

    enabled: bool
    reason: str  # "available", "not_installed", "no_store", etc.

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "reason": self.reason}

    @property
    def verdict_ceiling(self) -> str:
        """Maximum verdict allowed when kernel is disabled.

        If kernel is not enabled, the best you can claim is UNKNOWN.
        PASS requires kernel verification.
        """
        return "pass" if self.enabled else "unknown"


@dataclass
class ReceiptKernelBridge:
    """Thin bridge from agent_gov workflows to receipt_kernel event ledger.

    If receipt_kernel is not installed, all methods are no-ops.
    IMPORTANT: Callers MUST check .status to determine if PASS is allowed.
    A disabled kernel means the run cannot claim PASS — only UNKNOWN.
    """

    store: Any  # SqliteReceiptStore when available
    policy_id: str
    policy_version: str
    stage_graph_id: str
    actor_kind: str = "cli"
    actor_id: str = "unknown"

    @property
    def available(self) -> bool:
        return RECEIPT_KERNEL_AVAILABLE and self.store is not None

    @property
    def status(self) -> KernelStatus:
        """Machine-checkable kernel status. Never silent."""
        if not RECEIPT_KERNEL_AVAILABLE:
            return KernelStatus(enabled=False, reason="not_installed")
        if self.store is None:
            return KernelStatus(enabled=False, reason="no_store")
        return KernelStatus(enabled=True, reason="available")

    def ensure_run(self, run_id: str, meta: dict[str, Any] | None = None) -> None:
        if not self.available:
            return
        self.store.ensure_run(
            run_id=run_id,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            meta=meta,
        )

    def run_start(self, run_id: str, stage: str, meta: dict[str, Any] | None = None) -> str | None:
        if not self.available:
            return None
        env = make_envelope(
            event_type="RUN_START",
            stage=stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={"meta": dict(meta or {})},
        )
        return self.store.append_event(run_id, env)

    def stage_advance(
        self, run_id: str, from_stage: str, to_stage: str, reason: str = "normal",
    ) -> str | None:
        if not self.available:
            return None
        env = make_envelope(
            event_type="STAGE_ADVANCE",
            stage=to_stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={"from_stage": from_stage, "to_stage": to_stage, "reason": reason},
        )
        return self.store.append_event(run_id, env)

    def evidence_put(
        self,
        run_id: str,
        stage: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/json",
        evidence_class: str = "public",
        meta: dict[str, Any] | None = None,
    ) -> tuple[str | None, Any]:
        if not self.available:
            return None, None
        blob = self.store.put_blob(
            data, content_type=content_type, evidence_class=evidence_class,
        )
        env = make_envelope(
            event_type="EVIDENCE_PUT",
            stage=stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={
                "key": key,
                "evidence": blob.to_dict(),
                "meta": dict(meta or {}),
            },
            blob_refs=[blob.ref],
        )
        event_ref = self.store.append_event(run_id, env)
        return event_ref, blob

    def record_evaluation(
        self,
        run_id: str,
        stage: str,
        results: list[dict[str, Any]],
        overall_verdict: str,
        evidence_complete: bool,
    ) -> str | None:
        if not self.available:
            return None
        env = make_envelope(
            event_type="EVALUATION",
            stage=stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={
                "results": results,
                "overall_verdict": overall_verdict,
                "evidence_complete": bool(evidence_complete),
            },
        )
        return self.store.append_event(run_id, env)

    def record_decision(
        self,
        run_id: str,
        stage: str,
        decision_id: str,
        basis: dict[str, Any],
        action_plan: list[dict[str, Any]] | None = None,
        event_refs: list[str] | None = None,
    ) -> str | None:
        if not self.available:
            return None
        env = make_envelope(
            event_type="DECISION",
            stage=stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={
                "decision_id": decision_id,
                "basis": basis,
                "action_plan": action_plan or [],
            },
            event_refs=event_refs,
        )
        return self.store.append_event(run_id, env)

    def run_finalize(
        self,
        run_id: str,
        stage: str,
        overall_verdict: str,
        summary: dict[str, Any],
        event_refs: list[str] | None = None,
    ) -> str | None:
        if not self.available:
            return None
        env = make_envelope(
            event_type="RUN_FINALIZE",
            stage=stage,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            stage_graph_id=self.stage_graph_id,
            actor_kind=self.actor_kind,
            actor_id=self.actor_id,
            payload={
                "overall_verdict": overall_verdict,
                "summary": dict(summary),
            },
            event_refs=event_refs,
        )
        return self.store.append_event(run_id, env)
