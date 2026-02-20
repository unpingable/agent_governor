# SPDX-License-Identifier: Apache-2.0
"""Tests for reset auditability — _emit_reset_receipt() and CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from governor.cli import _emit_reset_receipt, cli
from governor.gate_receipt import (
    GateReceiptSystem,
    ROLE_RESET,
)


# =============================================================================
# _emit_reset_receipt() unit tests
# =============================================================================


class TestEmitResetReceipt:
    """Unit tests for the _emit_reset_receipt() helper."""

    def test_receipt_created(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "regime", {"current_regime": "elastic"})
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1

    def test_role_is_reset(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "boil", {"mode": "oolong"})
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert receipts[0].receipt_role == ROLE_RESET

    def test_evidence_has_target(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "drift", {"alert_level": 0})
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        evidence = system.evidence_for(receipts[0])
        assert evidence is not None
        assert evidence["target"] == "drift"

    def test_request_id_auto_generated(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "strict", {"total_evaluations": 42})
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        evidence = system.evidence_for(receipts[0])
        assert "request_id" in evidence
        assert len(evidence["request_id"]) == 32  # uuid hex

    def test_explicit_request_id(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "taint", {"claim_count": 5},
                            request_id="my-custom-id")
        system = GateReceiptSystem(gov_dir)
        evidence = system.evidence_for(system.query()[0])
        assert evidence["request_id"] == "my-custom-id"

    def test_noop_when_gov_dir_missing(self, tmp_path):
        """No error when gov_dir doesn't exist."""
        missing = tmp_path / "nonexistent"
        _emit_reset_receipt(missing, "regime", {})
        # No exception raised, no files created
        assert not missing.exists()

    def test_loud_fail_open(self, tmp_path):
        """On error, prints warning to stderr and continues."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        with patch("governor.gate_receipt.GateReceiptSystem.emit",
                    side_effect=RuntimeError("boom")):
            _emit_reset_receipt(gov_dir, "regime", {})
        # Verify the error was logged to the fallback log
        log_path = gov_dir / "reset_audit_errors.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "boom" in content

    def test_reset_reason_in_evidence(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "correlator", {"regime": "elastic"},
                            reset_reason="operator_request")
        system = GateReceiptSystem(gov_dir)
        evidence = system.evidence_for(system.query()[0])
        assert evidence["reset_reason"] == "operator_request"

    def test_wall_ts_and_monotonic_ts(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        _emit_reset_receipt(gov_dir, "scope", {"grant_count": 0})
        system = GateReceiptSystem(gov_dir)
        evidence = system.evidence_for(system.query()[0])
        assert "wall_ts" in evidence
        assert "monotonic_ts" in evidence
        assert isinstance(evidence["wall_ts"], float)
        assert isinstance(evidence["monotonic_ts"], float)


# =============================================================================
# CLI integration tests — representative reset commands emit receipts
# =============================================================================


def _init_governor(tmp_path: Path) -> Path:
    """Initialize a .governor directory for CLI testing."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "init"])
    assert result.exit_code == 0, result.output
    return tmp_path / ".governor"


class TestResetCLIIntegration:
    """Verify that CLI reset commands emit receipts before mutation."""

    def test_regime_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "regime", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "regime"

    def test_boil_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "boil", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "boil"

    def test_strict_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "strict", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "strict"

    def test_drift_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "drift", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "drift"

    def test_taint_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "taint", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "taint"

    def test_correlator_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "correlator", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "correlator"

    def test_scope_reset_emits_receipt(self, tmp_path):
        gov_dir = _init_governor(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--root", str(tmp_path), "scope", "reset", "--confirm"])
        assert result.exit_code == 0, result.output
        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="system_reset_request")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence["target"] == "scope"
