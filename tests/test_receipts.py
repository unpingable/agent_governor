"""Tests for receipt types."""

import json
from datetime import datetime

import pytest

from governor.receipts import (
    FileSnapshot,
    CmdRun,
    DiffReceipt,
    Receipt,
    receipt_from_dict,
)


class TestFileSnapshot:
    """Test FileSnapshot receipt type."""

    def test_create_basic(self):
        """Can create a FileSnapshot with required fields."""
        snapshot = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123def456",
            size_bytes=1024,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        assert snapshot.path == "src/main.py"
        assert snapshot.blob_hash == "abc123def456"
        assert snapshot.size_bytes == 1024
        assert snapshot.excerpt_spans is None

    def test_create_with_excerpt_spans(self):
        """Can create a FileSnapshot with excerpt spans."""
        snapshot = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=2048,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
            excerpt_spans=[(10, 20), (50, 60)],
        )

        assert snapshot.excerpt_spans == [(10, 20), (50, 60)]

    def test_to_dict(self):
        """FileSnapshot serializes to dict correctly."""
        snapshot = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=1024,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
            excerpt_spans=[(10, 20)],
        )

        data = snapshot.to_dict()

        assert data["type"] == "file_snapshot"
        assert data["path"] == "src/main.py"
        assert data["blob_hash"] == "abc123"
        assert data["size_bytes"] == 1024
        assert data["timestamp"] == "2025-01-15T12:00:00"
        assert data["excerpt_spans"] == [(10, 20)]

    def test_from_dict(self):
        """FileSnapshot deserializes from dict correctly."""
        data = {
            "type": "file_snapshot",
            "path": "src/main.py",
            "blob_hash": "abc123",
            "size_bytes": 1024,
            "timestamp": "2025-01-15T12:00:00",
            "excerpt_spans": [[10, 20]],
        }

        snapshot = FileSnapshot.from_dict(data)

        assert snapshot.path == "src/main.py"
        assert snapshot.blob_hash == "abc123"
        assert snapshot.size_bytes == 1024
        assert snapshot.timestamp == datetime(2025, 1, 15, 12, 0, 0)
        assert snapshot.excerpt_spans == [(10, 20)]

    def test_round_trip(self):
        """FileSnapshot survives JSON round-trip."""
        original = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123def456789",
            size_bytes=4096,
            timestamp=datetime(2025, 1, 15, 12, 30, 45),
            excerpt_spans=[(1, 10), (100, 150)],
        )

        json_str = json.dumps(original.to_dict())
        restored = FileSnapshot.from_dict(json.loads(json_str))

        assert restored == original

    def test_round_trip_no_spans(self):
        """FileSnapshot without spans survives round-trip."""
        original = FileSnapshot(
            path="config.toml",
            blob_hash="deadbeef",
            size_bytes=256,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        json_str = json.dumps(original.to_dict())
        restored = FileSnapshot.from_dict(json.loads(json_str))

        assert restored == original
        assert restored.excerpt_spans is None

    def test_is_immutable(self):
        """FileSnapshot is frozen (immutable)."""
        snapshot = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=1024,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        with pytest.raises(AttributeError):
            snapshot.path = "other.py"


class TestCmdRun:
    """Test CmdRun receipt type."""

    def test_create_basic(self):
        """Can create a CmdRun with required fields."""
        cmd = CmdRun(
            command=("pytest", "-v"),
            exit_code=0,
            stdout_hash="stdout123",
            stderr_hash="stderr456",
            cwd="/home/user/project",
            duration_ms=1500,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        assert cmd.command == ("pytest", "-v")
        assert cmd.exit_code == 0
        assert cmd.duration_ms == 1500

    def test_to_dict(self):
        """CmdRun serializes to dict correctly."""
        cmd = CmdRun(
            command=("pytest", "-v", "--tb=short"),
            exit_code=1,
            stdout_hash="abc",
            stderr_hash="def",
            cwd="/project",
            duration_ms=2500,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        data = cmd.to_dict()

        assert data["type"] == "cmd_run"
        assert data["command"] == ["pytest", "-v", "--tb=short"]
        assert data["exit_code"] == 1
        assert data["stdout_hash"] == "abc"
        assert data["stderr_hash"] == "def"
        assert data["cwd"] == "/project"
        assert data["duration_ms"] == 2500

    def test_from_dict(self):
        """CmdRun deserializes from dict correctly."""
        data = {
            "type": "cmd_run",
            "command": ["make", "build"],
            "exit_code": 0,
            "stdout_hash": "hash1",
            "stderr_hash": "hash2",
            "cwd": "/build",
            "duration_ms": 5000,
            "timestamp": "2025-01-15T12:00:00",
        }

        cmd = CmdRun.from_dict(data)

        assert cmd.command == ("make", "build")
        assert cmd.exit_code == 0
        assert cmd.cwd == "/build"

    def test_round_trip(self):
        """CmdRun survives JSON round-trip."""
        original = CmdRun(
            command=("npm", "test", "--", "--coverage"),
            exit_code=0,
            stdout_hash="a1b2c3",
            stderr_hash="d4e5f6",
            cwd="/home/user/app",
            duration_ms=12345,
            timestamp=datetime(2025, 1, 15, 14, 30, 0),
        )

        json_str = json.dumps(original.to_dict())
        restored = CmdRun.from_dict(json.loads(json_str))

        assert restored == original

    def test_is_immutable(self):
        """CmdRun is frozen (immutable)."""
        cmd = CmdRun(
            command=("echo", "hi"),
            exit_code=0,
            stdout_hash="x",
            stderr_hash="y",
            cwd="/",
            duration_ms=10,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        with pytest.raises(AttributeError):
            cmd.exit_code = 1


class TestDiffReceipt:
    """Test DiffReceipt receipt type."""

    def test_create_basic(self):
        """Can create a DiffReceipt with required fields."""
        diff = DiffReceipt(
            paths_touched=("src/main.py", "src/utils.py"),
            unified_diff_hash="diff123",
            base_tree_hash="tree456",
            additions=50,
            deletions=10,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        assert diff.paths_touched == ("src/main.py", "src/utils.py")
        assert diff.additions == 50
        assert diff.deletions == 10

    def test_to_dict(self):
        """DiffReceipt serializes to dict correctly."""
        diff = DiffReceipt(
            paths_touched=("README.md",),
            unified_diff_hash="abc",
            base_tree_hash="def",
            additions=100,
            deletions=0,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        data = diff.to_dict()

        assert data["type"] == "diff_receipt"
        assert data["paths_touched"] == ["README.md"]
        assert data["unified_diff_hash"] == "abc"
        assert data["base_tree_hash"] == "def"
        assert data["additions"] == 100
        assert data["deletions"] == 0

    def test_from_dict(self):
        """DiffReceipt deserializes from dict correctly."""
        data = {
            "type": "diff_receipt",
            "paths_touched": ["a.py", "b.py", "c.py"],
            "unified_diff_hash": "hash1",
            "base_tree_hash": "hash2",
            "additions": 200,
            "deletions": 150,
            "timestamp": "2025-01-15T12:00:00",
        }

        diff = DiffReceipt.from_dict(data)

        assert diff.paths_touched == ("a.py", "b.py", "c.py")
        assert diff.additions == 200
        assert diff.deletions == 150

    def test_round_trip(self):
        """DiffReceipt survives JSON round-trip."""
        original = DiffReceipt(
            paths_touched=("file1.py", "file2.py"),
            unified_diff_hash="aabbccdd",
            base_tree_hash="11223344",
            additions=75,
            deletions=25,
            timestamp=datetime(2025, 1, 15, 16, 45, 30),
        )

        json_str = json.dumps(original.to_dict())
        restored = DiffReceipt.from_dict(json.loads(json_str))

        assert restored == original

    def test_is_immutable(self):
        """DiffReceipt is frozen (immutable)."""
        diff = DiffReceipt(
            paths_touched=("x.py",),
            unified_diff_hash="a",
            base_tree_hash="b",
            additions=1,
            deletions=1,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
        )

        with pytest.raises(AttributeError):
            diff.additions = 999


class TestReceiptFromDict:
    """Test the generic receipt_from_dict deserializer."""

    def test_deserialize_file_snapshot(self):
        """receipt_from_dict handles FileSnapshot."""
        data = {
            "type": "file_snapshot",
            "path": "test.py",
            "blob_hash": "abc",
            "size_bytes": 100,
            "timestamp": "2025-01-15T12:00:00",
            "excerpt_spans": None,
        }

        receipt = receipt_from_dict(data)

        assert isinstance(receipt, FileSnapshot)
        assert receipt.path == "test.py"

    def test_deserialize_cmd_run(self):
        """receipt_from_dict handles CmdRun."""
        data = {
            "type": "cmd_run",
            "command": ["echo"],
            "exit_code": 0,
            "stdout_hash": "a",
            "stderr_hash": "b",
            "cwd": "/",
            "duration_ms": 1,
            "timestamp": "2025-01-15T12:00:00",
        }

        receipt = receipt_from_dict(data)

        assert isinstance(receipt, CmdRun)
        assert receipt.command == ("echo",)

    def test_deserialize_diff_receipt(self):
        """receipt_from_dict handles DiffReceipt."""
        data = {
            "type": "diff_receipt",
            "paths_touched": ["x.py"],
            "unified_diff_hash": "a",
            "base_tree_hash": "b",
            "additions": 1,
            "deletions": 0,
            "timestamp": "2025-01-15T12:00:00",
        }

        receipt = receipt_from_dict(data)

        assert isinstance(receipt, DiffReceipt)
        assert receipt.paths_touched == ("x.py",)

    def test_unknown_type_raises(self):
        """receipt_from_dict raises on unknown type."""
        data = {"type": "unknown_receipt"}

        with pytest.raises(ValueError, match="Unknown receipt type"):
            receipt_from_dict(data)

    def test_missing_type_raises(self):
        """receipt_from_dict raises when type is missing."""
        data = {"path": "test.py"}

        with pytest.raises(ValueError, match="Unknown receipt type"):
            receipt_from_dict(data)
