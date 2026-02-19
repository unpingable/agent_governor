# SPDX-License-Identifier: Apache-2.0
"""Tests for gate heartbeat: missed-heartbeat model + CLI + preflight."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.gate_heartbeat import (
    HeartbeatConfig,
    HeartbeatStatus,
    gate_heartbeat,
    _compute_missed,
    _most_recent_receipt,
)
from governor.preflight import check_gate_heartbeat, PreflightCheck
from governor.cli import cli


# =============================================================================
# HeartbeatStatus
# =============================================================================


class TestHeartbeatStatus:
    def test_no_receipts(self, tmp_path):
        """No receipts → None/0/False, not an error."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        status = gate_heartbeat(gov_dir, now=now)

        assert status.last_check_timestamp is None
        assert status.seconds_since_last is None
        assert status.missed_count == 0
        assert status.is_stale is False
        assert status.gate is None

    def test_recent_receipt_active(self, tmp_path):
        """Receipt within interval → missed=0, not stale."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T11:58:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        status = gate_heartbeat(gov_dir, now=now)

        assert status.last_check_timestamp == "2026-01-15T11:58:00+00:00"
        assert status.seconds_since_last == 120.0
        assert status.missed_count == 0
        assert status.is_stale is False
        assert status.gate == "evidence_gate"

    def test_old_receipt_stale(self, tmp_path):
        """Receipt much older than 3 intervals → stale."""
        gov_dir = tmp_path / ".governor"
        # 20 minutes ago, with default 5min interval and 1min grace
        # elapsed=1200, missed = floor((1200-60)/300) = floor(3.8) = 3
        _write_receipt(gov_dir, "2026-01-15T11:40:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        status = gate_heartbeat(gov_dir, now=now)

        assert status.missed_count == 3
        assert status.is_stale is True

    def test_missed_count_math(self, tmp_path):
        """Verify floor((elapsed - grace) / interval) exactly."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T11:00:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # elapsed = 3600s, grace = 60, interval = 300
        # missed = floor((3600 - 60) / 300) = floor(11.8) = 11

        status = gate_heartbeat(gov_dir, now=now)

        assert status.seconds_since_last == 3600.0
        assert status.missed_count == 11
        assert status.is_stale is True

    def test_not_stale_when_session_inactive(self, tmp_path):
        """High missed count but session_active=False → not stale."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T11:00:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        status = gate_heartbeat(gov_dir, now=now, session_active=False)

        assert status.missed_count == 11
        assert status.is_stale is False
        assert status.is_session_active is False

    def test_custom_config(self, tmp_path):
        """Override interval/grace/threshold."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T11:50:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # elapsed = 600s, custom interval=60, grace=10, threshold=5
        # missed = floor((600 - 10) / 60) = floor(9.83) = 9
        config = HeartbeatConfig(
            expected_interval_seconds=60.0,
            grace_period_seconds=10.0,
            stale_after_missed=5,
        )

        status = gate_heartbeat(gov_dir, config=config, now=now)

        assert status.missed_count == 9
        assert status.is_stale is True
        assert status.expected_interval == 60.0

    def test_deterministic_now(self, tmp_path):
        """Injected clock gives deterministic results."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T12:00:00+00:00", "evidence_gate")

        t1 = datetime(2026, 1, 15, 12, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 15, 12, 30, 0, tzinfo=timezone.utc)

        s1 = gate_heartbeat(gov_dir, now=t1)
        s2 = gate_heartbeat(gov_dir, now=t2)

        assert s1.seconds_since_last == 60.0
        assert s2.seconds_since_last == 1800.0
        assert s1.missed_count == 0
        assert s2.missed_count > 0

    def test_to_dict_roundtrip(self, tmp_path):
        """to_dict contains all fields and is JSON-serializable."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T12:00:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 3, 0, tzinfo=timezone.utc)

        status = gate_heartbeat(gov_dir, now=now)
        d = status.to_dict()

        # Verify all fields present
        assert set(d.keys()) == {
            "last_check_timestamp", "seconds_since_last",
            "expected_interval", "missed_count", "is_stale",
            "is_session_active", "gate",
        }
        # JSON-serializable
        text = json.dumps(d)
        assert json.loads(text) == d

    def test_within_grace_period(self, tmp_path):
        """Elapsed just beyond interval but within grace → 0 missed."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T11:55:00+00:00", "evidence_gate")
        now = datetime(2026, 1, 15, 12, 0, 30, tzinfo=timezone.utc)
        # elapsed = 330s, grace = 60, interval = 300
        # missed = floor((330 - 60) / 300) = floor(0.9) = 0

        status = gate_heartbeat(gov_dir, now=now)

        assert status.missed_count == 0
        assert status.is_stale is False


# =============================================================================
# _compute_missed unit tests
# =============================================================================


class TestComputeMissed:
    def test_zero_elapsed(self):
        assert _compute_missed(0, 60, 300) == 0

    def test_within_grace(self):
        assert _compute_missed(50, 60, 300) == 0

    def test_one_missed(self):
        # elapsed=400, grace=60, interval=300 → floor((400-60)/300) = 1
        assert _compute_missed(400, 60, 300) == 1

    def test_zero_interval(self):
        assert _compute_missed(1000, 60, 0) == 0


# =============================================================================
# CLI
# =============================================================================


class TestCLI:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def initialized_dir(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            yield Path(td)

    def test_heartbeat_no_receipts(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "gate", "heartbeat"]
        )
        assert result.exit_code == 0
        assert "no receipts" in result.output.lower()

    def test_heartbeat_json_output(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "gate", "heartbeat", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "missed_count" in data
        assert "is_stale" in data
        assert data["last_check_timestamp"] is None

    def test_heartbeat_text_with_receipts(self, runner, initialized_dir):
        gov_dir = initialized_dir / ".governor"
        _write_receipt(gov_dir, datetime.now(timezone.utc).isoformat(), "evidence_gate")

        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "gate", "heartbeat"]
        )
        assert result.exit_code == 0
        assert "active" in result.output.lower()
        assert "evidence_gate" in result.output


# =============================================================================
# Preflight
# =============================================================================


class TestPreflight:
    def test_check_no_receipts_clean_install(self, tmp_path):
        """No .governor/ → pass (check #1 handles missing dir)."""
        result = check_gate_heartbeat(tmp_path)
        assert result.status == "pass"
        assert result.name == "gate_heartbeat"

    def test_check_receipts_present(self, tmp_path):
        """Receipts exist → pass."""
        gov_dir = tmp_path / ".governor"
        _write_receipt(gov_dir, "2026-01-15T12:00:00+00:00", "evidence_gate")

        result = check_gate_heartbeat(tmp_path)
        assert result.status == "pass"
        assert "present" in result.detail.lower()

    def test_check_no_receipts_with_session(self, tmp_path):
        """Session artifacts but no receipts → warn."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Create a session indicator
        (gov_dir / "hook_invocations.jsonl").write_text('{"ts":"2026-01-15"}\n')

        result = check_gate_heartbeat(tmp_path)
        assert result.status == "warn"
        assert result.fix is not None

    def test_check_gov_dir_no_sessions_no_receipts(self, tmp_path):
        """Gov dir exists but empty (no sessions, no receipts) → pass."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        result = check_gate_heartbeat(tmp_path)
        assert result.status == "pass"
        assert "clean install" in result.detail.lower()


# =============================================================================
# Helpers
# =============================================================================


def _write_receipt(gov_dir: Path, timestamp: str, gate: str = "evidence_gate"):
    """Write a minimal gate receipt JSONL line for testing."""
    receipts_dir = gov_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "receipt_id": "test_receipt_001",
        "schema_version": 2,
        "timestamp": timestamp,
        "gate": gate,
        "verdict": "pass",
        "subject_hash": "abc123",
        "evidence_hash": "def456",
        "policy_hash": "ghi789",
    }
    with open(receipts_dir / "gate_receipts.jsonl", "a") as f:
        f.write(json.dumps(receipt) + "\n")
