"""Tests for the receipt kernel bridge adapter.

Key invariant: kernel disabled must NEVER produce silent green.
"""

from __future__ import annotations

import pytest

from governor.receipt_bridge import KernelStatus, ReceiptKernelBridge


class TestKernelStatus:
    """KernelStatus must prevent silent green when kernel is disabled."""

    def test_enabled_allows_pass(self):
        status = KernelStatus(enabled=True, reason="available")
        assert status.verdict_ceiling == "pass"

    def test_disabled_caps_at_unknown(self):
        """CRITICAL: disabled kernel cannot claim PASS."""
        status = KernelStatus(enabled=False, reason="not_installed")
        assert status.verdict_ceiling == "unknown"

    def test_no_store_caps_at_unknown(self):
        status = KernelStatus(enabled=False, reason="no_store")
        assert status.verdict_ceiling == "unknown"

    def test_to_dict(self):
        status = KernelStatus(enabled=True, reason="available")
        d = status.to_dict()
        assert d == {"enabled": True, "reason": "available"}


class TestBridgeStatus:
    """Bridge must expose its disabled state clearly."""

    def test_bridge_with_no_store(self):
        bridge = ReceiptKernelBridge(
            store=None, policy_id="test", policy_version="0",
            stage_graph_id="v1_default",
        )
        assert not bridge.available
        assert bridge.status.enabled is False
        assert bridge.status.reason == "no_store"
        assert bridge.status.verdict_ceiling == "unknown"

    def test_bridge_no_ops_when_disabled(self):
        """All methods must return None (not raise) when disabled."""
        bridge = ReceiptKernelBridge(
            store=None, policy_id="test", policy_version="0",
            stage_graph_id="v1_default",
        )
        bridge.ensure_run("run1")  # no error
        assert bridge.run_start("run1", "START") is None
        assert bridge.stage_advance("run1", "START", "COLLECT") is None
        ev_ref, blob = bridge.evidence_put("run1", "COLLECT", "key", b"data")
        assert ev_ref is None
        assert blob is None
        assert bridge.record_evaluation("run1", "EVAL", [], "pass", True) is None
        assert bridge.record_decision("run1", "DECIDE", "d1", {}) is None
        assert bridge.run_finalize("run1", "FINALIZE", "pass", {}) is None


class TestBridgeWithRealKernel:
    """Bridge with receipt_kernel installed and store provided."""

    def test_bridge_available_with_store(self, tmp_path):
        from receipt_kernel.store_sqlite import SqliteReceiptStore

        store = SqliteReceiptStore(str(tmp_path / "test.db"), redaction_enabled=False)
        store.initialize_schema()

        bridge = ReceiptKernelBridge(
            store=store, policy_id="test", policy_version="0.0.0",
            stage_graph_id="v1_default", actor_kind="pytest", actor_id="test",
        )
        assert bridge.available
        assert bridge.status.enabled
        assert bridge.status.verdict_ceiling == "pass"
        store.close()

    def test_bridge_emits_events(self, tmp_path):
        from receipt_kernel.store_sqlite import SqliteReceiptStore

        store = SqliteReceiptStore(str(tmp_path / "test.db"), redaction_enabled=False)
        store.initialize_schema()

        bridge = ReceiptKernelBridge(
            store=store, policy_id="test", policy_version="0.0.0",
            stage_graph_id="v1_default", actor_kind="pytest", actor_id="test",
        )
        bridge.ensure_run("run1", {"test": True})
        start_ref = bridge.run_start("run1", "START")
        assert start_ref is not None
        assert start_ref.startswith("event://")

        advance_ref = bridge.stage_advance("run1", "START", "COLLECT")
        assert advance_ref is not None

        ev_ref, blob = bridge.evidence_put(
            "run1", "COLLECT", "output", b'{"result": 1}',
            content_type="application/json",
        )
        assert ev_ref is not None
        assert blob is not None
        assert blob.ref.startswith("blob://")

        eval_ref = bridge.record_evaluation(
            "run1", "EVALUATE",
            [{"invariant_id": "test", "verdict": "pass"}],
            "pass", True,
        )
        assert eval_ref is not None

        dec_ref = bridge.record_decision(
            "run1", "DECIDE", "dec_1",
            {"overall_verdict": "pass"},
            event_refs=[eval_ref],
        )
        assert dec_ref is not None

        fin_ref = bridge.run_finalize(
            "run1", "FINALIZE", "pass", {},
            event_refs=[eval_ref, dec_ref],
        )
        assert fin_ref is not None

        # Verify chain integrity
        from receipt_kernel.invariants.ledger_chain_valid import LedgerChainValidInvariant
        from receipt_kernel.types import Verdict

        result = LedgerChainValidInvariant().evaluate(
            {"store": store, "run_id": "run1"}
        )
        assert result.verdict == Verdict.PASS
        store.close()


class TestKernelDisabledRegressionGuard:
    """CRITICAL: kernel missing + run completes must NOT produce PASS.

    This test exists because "kernel not installed → no-ops" is an escape
    hatch that's indistinguishable from "restart fixed it" unless we
    stamp UNKNOWN everywhere.
    """

    def test_disabled_bridge_verdict_ceiling_blocks_pass(self):
        """The verdict_ceiling mechanism prevents PASS when kernel is disabled."""
        bridge = ReceiptKernelBridge(
            store=None, policy_id="test", policy_version="0",
            stage_graph_id="v1_default",
        )

        # Simulate a "run completed successfully" scenario
        bridge.ensure_run("run1")
        bridge.run_start("run1", "START")
        bridge.run_finalize("run1", "FINALIZE", "pass", {})

        # The bridge says the run is "done" (no errors), BUT:
        overall_verdict = bridge.status.verdict_ceiling
        assert overall_verdict != "pass", (
            "CRITICAL BUG: kernel disabled but verdict is 'pass'. "
            "This means restarts silently suppress governance failures."
        )
        assert overall_verdict == "unknown"

    def test_disabled_status_is_machine_readable(self):
        """The disabled reason must be machine-readable, not just a bool."""
        bridge = ReceiptKernelBridge(
            store=None, policy_id="test", policy_version="0",
            stage_graph_id="v1_default",
        )
        d = bridge.status.to_dict()
        assert "enabled" in d
        assert "reason" in d
        assert d["enabled"] is False
        assert isinstance(d["reason"], str)
        assert len(d["reason"]) > 0
