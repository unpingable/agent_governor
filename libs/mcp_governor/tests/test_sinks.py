# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.sinks — secure receipt file handling."""

import json
import os
import stat

import pytest

from receipt_v1 import (
    Action,
    Actor,
    AuthContext,
    Chain,
    Decision,
    Provenance,
    Receipt,
    ReceiptBuilder,
    ReceiptChain,
)

from mcp_governor.sinks import RotatingFileSink, _FILE_MODE


def _make_receipt(chain: ReceiptChain) -> Receipt:
    """Build a minimal valid receipt."""
    return (
        ReceiptBuilder()
        .actor(Actor(agent_id="test", session_id="s1", auth_context=AuthContext.STDIO))
        .tool("echo", {"text": "hi"}, call_id="1")
        .decision(Action.ALLOW, "gov.policy_allow")
        .provenance(Provenance(
            deployment_id="test", instance_id="test-1", governor_version="0.1.0"))
        .build(chain.next())
    )


class TestSecurePermissions:
    def test_new_file_created_with_0600(self, tmp_path):
        """Receipt file is created with 0o600 from the start."""
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        chain = ReceiptChain()
        r = _make_receipt(chain)
        chain.append(r)
        sink.write(r)

        mode = os.stat(path).st_mode & 0o777
        assert mode == _FILE_MODE, f"Expected {oct(_FILE_MODE)}, got {oct(mode)}"

    def test_warns_on_too_open_permissions(self, tmp_path, capsys):
        """Warns if existing file has permissions more open than 0600."""
        path = tmp_path / "receipts.jsonl"
        # Create file with world-readable permissions
        path.touch(mode=0o644)

        # RotatingFileSink checks on init — warning goes to stderr
        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "0o644" in captured.err

    def test_no_warning_on_correct_permissions(self, tmp_path, capsys):
        """No warning if existing file already has 0o600."""
        path = tmp_path / "receipts.jsonl"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT, _FILE_MODE)
        os.close(fd)

        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err


class TestRotation:
    def test_no_rotation_when_small(self, tmp_path):
        """File stays put when under size limit."""
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=1024 * 1024)
        chain = ReceiptChain()
        for _ in range(5):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        assert path.exists()
        assert not path.with_name("receipts.jsonl.1").exists()

    def test_rotation_on_size(self, tmp_path):
        """File rotates when exceeding max_bytes."""
        path = tmp_path / "receipts.jsonl"
        # Very small limit to force rotation
        sink = RotatingFileSink(path, fsync=False, max_bytes=100, keep_files=3)
        chain = ReceiptChain()

        # Write enough receipts to trigger rotation
        for _ in range(10):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        # Current file should exist
        assert path.exists()
        # At least one rotated file should exist
        assert path.with_name("receipts.jsonl.1").exists()

    def test_rotation_limits_files(self, tmp_path):
        """Only keeps keep_files rotated files."""
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=50, keep_files=2)
        chain = ReceiptChain()

        for _ in range(20):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        # Should have current + at most 2 rotated
        assert path.exists()
        # .3 should not exist (keep_files=2)
        assert not path.with_name("receipts.jsonl.3").exists()

    def test_rotation_disabled_when_zero(self, tmp_path):
        """max_bytes=0 means no rotation."""
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        chain = ReceiptChain()

        for _ in range(5):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        assert path.exists()
        assert not path.with_name("receipts.jsonl.1").exists()

    def test_rotated_files_have_secure_permissions(self, tmp_path):
        """Rotated files keep the permissions of the original."""
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=50, keep_files=2)
        chain = ReceiptChain()

        for _ in range(10):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        rotated = path.with_name("receipts.jsonl.1")
        if rotated.exists():
            mode = os.stat(rotated).st_mode & 0o777
            assert mode == _FILE_MODE, f"Rotated file has {oct(mode)}, expected {oct(_FILE_MODE)}"


class TestReadAll:
    def test_read_all(self, tmp_path):
        path = tmp_path / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        chain = ReceiptChain()

        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            sink.write(r)

        receipts = sink.read_all()
        assert len(receipts) == 3
        assert all(r["decision"]["action"] == "allow" for r in receipts)

    def test_read_all_empty(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        sink = RotatingFileSink(path, fsync=False)
        assert sink.read_all() == []


class TestParentDirs:
    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "receipts.jsonl"
        sink = RotatingFileSink(path, fsync=False, max_bytes=0)
        assert path.parent.exists()
