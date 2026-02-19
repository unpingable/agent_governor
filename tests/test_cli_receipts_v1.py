# SPDX-License-Identifier: Apache-2.0
"""Tests for receipts CLI: list/show/verify with --format v1 and legacy."""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def gov_dir(tmp_path):
    """Initialize a minimal .governor/ tree."""
    gd = tmp_path / ".governor"
    gd.mkdir()
    (gd / "facts").mkdir()
    (gd / "facts" / "receipts").mkdir()
    (gd / "facts" / "index.json").write_text("[]")
    (gd / "decisions").mkdir()
    (gd / "decisions" / "index.json").write_text("[]")
    (gd / "proposals.json").write_text("{}")
    (gd / "receipts").mkdir()
    return gd


def _make_v1_receipt(seq: int, receipt_id: str, parent_id: str | None = None,
                     parent_hash: str | None = None, tool_id: str = "test_tool",
                     action: str = "allow") -> dict:
    """Build a minimal v1 receipt dict."""
    from receipt_v1.canonical import receipt_hash

    chain: dict = {"seq": seq}
    if parent_id:
        chain["parent_receipt_id"] = parent_id
        chain["parent_receipt_hash"] = parent_hash

    d = {
        "receipt_id": receipt_id,
        "receipt_version": "1.0",
        "receipt_hash": "",  # Filled below
        "chain": chain,
        "timestamp_wall": f"2026-02-19T12:{seq:02d}:00Z",
        "actor": {"agent_id": "test-agent", "session_id": "test-session"},
        "tool": {"tool_id": tool_id, "args_hash": "a" * 64},
        "decision": {"action": action, "reason_code": "gov.test"},
        "provenance": {
            "deployment_id": "test-deploy",
            "instance_id": "test-instance",
            "governor_version": "0.1.0",
        },
    }
    d["receipt_hash"] = receipt_hash(d)
    return d


def _write_v1_receipts(gov_dir: Path, receipts: list[dict]) -> None:
    """Write receipt dicts to receipt_v1.jsonl."""
    path = gov_dir / "receipts" / "receipt_v1.jsonl"
    with open(path, "w") as f:
        for r in receipts:
            f.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# Backward compatibility: governor receipts (no subcommand)
# ---------------------------------------------------------------------------

class TestReceiptsBackwardCompat:
    def test_bare_receipts_shows_no_results(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts"])
        assert result.exit_code == 0
        assert "No receipts found" in result.output

    def test_receipts_with_gate_flag(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "--gate", "evidence_gate"])
        assert result.exit_code == 0
        assert "No receipts found" in result.output

    def test_receipts_with_json_flag(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "--json"])
        assert result.exit_code == 0
        assert "No receipts found" in result.output


# ---------------------------------------------------------------------------
# receipts list
# ---------------------------------------------------------------------------

class TestReceiptsList:
    def test_list_legacy_empty(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list"])
        assert result.exit_code == 0
        assert "No receipts found" in result.output

    def test_list_v1_empty(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list", "--format", "v1"])
        assert result.exit_code == 0
        assert "No v1 receipts found" in result.output

    def test_list_v1_with_data(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list", "--format", "v1"])
        assert result.exit_code == 0
        assert "Receipt v1" in result.output
        assert "01234567" in result.output

    def test_list_v1_json(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list", "--format", "v1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["receipt_id"] == "01234567-1234-7000-8000-000000000001"

    def test_list_since_rejects_legacy(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list",
                                     "--format", "legacy", "--since", "some-id"])
        assert result.exit_code != 0
        assert "--since is only supported" in result.output

    def test_list_since_not_found(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list",
                                     "--format", "v1", "--since", "nonexistent-id"])
        assert result.exit_code != 0
        assert "Receipt not found" in result.output

    def test_list_since_cursor(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        r2 = _make_v1_receipt(2, "01234567-1234-7000-8000-000000000002",
                              parent_id=r1["receipt_id"], parent_hash=r1["receipt_hash"])
        _write_v1_receipts(gov_dir, [r1, r2])
        # --since r1 should only show r2
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list",
                                     "--format", "v1", "--since",
                                     "01234567-1234-7000-8000-000000000001", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [d["receipt_id"] for d in data]
        assert "01234567-1234-7000-8000-000000000001" not in ids
        assert "01234567-1234-7000-8000-000000000002" in ids

    def test_list_env_default_format(self, runner, gov_dir, tmp_path, monkeypatch):
        monkeypatch.setenv("GOV_RECEIPTS_DEFAULT", "v1")
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "list"])
        assert result.exit_code == 0
        assert "Receipt v1" in result.output


# ---------------------------------------------------------------------------
# receipts show
# ---------------------------------------------------------------------------

class TestReceiptsShow:
    def test_show_v1_by_uuid_shape(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "show",
                                     "01234567-1234-7000-8000-000000000001"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["receipt_id"] == "01234567-1234-7000-8000-000000000001"

    def test_show_not_found(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "show",
                                     "01234567-1234-7000-8000-000000000099"])
        assert result.exit_code != 0
        assert "Receipt not found" in result.output

    def test_show_forced_format(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "show",
                                     "01234567-1234-7000-8000-000000000001",
                                     "--format", "v1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["receipt_version"] == "1.0"

    def test_show_ambiguous_auto_routes(self, runner, gov_dir, tmp_path):
        """Non-UUID, non-hex64 IDs try auto (both stores)."""
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "show", "short-id"])
        assert result.exit_code != 0
        assert "Receipt not found" in result.output


# ---------------------------------------------------------------------------
# receipts verify
# ---------------------------------------------------------------------------

class TestReceiptsVerify:
    def test_verify_empty_chain(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "verify"])
        assert result.exit_code == 0
        assert "Chain valid: 0 receipts" in result.output

    def test_verify_valid_chain(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        r2 = _make_v1_receipt(2, "01234567-1234-7000-8000-000000000002",
                              parent_id=r1["receipt_id"], parent_hash=r1["receipt_hash"])
        _write_v1_receipts(gov_dir, [r1, r2])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "verify"])
        assert result.exit_code == 0
        assert "Chain valid" in result.output
        assert "2 receipts" in result.output

    def test_verify_json_output(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        _write_v1_receipts(gov_dir, [r1])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "verify", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["count"] == 1
        assert data["first_receipt_id"] == "01234567-1234-7000-8000-000000000001"
        assert data["last_receipt_id"] == "01234567-1234-7000-8000-000000000001"

    def test_verify_broken_chain(self, runner, gov_dir, tmp_path):
        r1 = _make_v1_receipt(1, "01234567-1234-7000-8000-000000000001")
        # r2 points to wrong parent
        r2 = _make_v1_receipt(2, "01234567-1234-7000-8000-000000000002",
                              parent_id=r1["receipt_id"], parent_hash="b" * 64)
        _write_v1_receipts(gov_dir, [r1, r2])
        result = runner.invoke(cli, ["-r", str(tmp_path), "receipts", "verify"])
        assert result.exit_code != 0
        assert "INVALID" in result.output


# ---------------------------------------------------------------------------
# Operator group receipts delegation
# ---------------------------------------------------------------------------

class TestOperatorReceipts:
    def test_operator_receipts_delegates(self, runner, gov_dir, tmp_path):
        result = runner.invoke(cli, ["-r", str(tmp_path), "operator", "receipts"])
        assert result.exit_code == 0
        assert "No receipts found" in result.output
