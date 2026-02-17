# SPDX-License-Identifier: Apache-2.0
"""Tests for fact decay functionality."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from governor.claims import file_exists
from governor.receipts import FileSnapshot
from governor.ledgers import Fact, FactLedger
from governor.cli import cli


class TestFactLedgerDecay:
    """Test FactLedger decay methods."""

    @pytest.fixture
    def ledger(self, tmp_path):
        """Create a FactLedger in a temp directory."""
        governor_dir = tmp_path / ".governor"
        return FactLedger(governor_dir)

    @pytest.fixture
    def sample_receipt(self):
        """Create a sample receipt."""
        return FileSnapshot(
            path="test.py",
            blob_hash="abc123",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

    def test_check_staleness_fresh_file(self, ledger, tmp_path, sample_receipt):
        """Fact is fresh when file hasn't changed."""
        # Create file
        test_file = tmp_path / "code.py"
        test_file.write_text("original content")
        file_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Add fact with hash
        fact = ledger.add(
            file_exists("code.py"),
            sample_receipt,
            file_hashes={"code.py": file_hash},
        )

        # Should be fresh
        assert ledger.check_staleness(fact, base_path=tmp_path) is False

    def test_check_staleness_changed_file(self, ledger, tmp_path, sample_receipt):
        """Fact is stale when file has changed."""
        # Create file
        test_file = tmp_path / "code.py"
        test_file.write_text("original content")
        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Add fact with hash
        fact = ledger.add(
            file_exists("code.py"),
            sample_receipt,
            file_hashes={"code.py": original_hash},
        )

        # Modify file
        test_file.write_text("modified content")

        # Should be stale
        assert ledger.check_staleness(fact, base_path=tmp_path) is True

    def test_check_staleness_deleted_file(self, ledger, tmp_path, sample_receipt):
        """Fact is stale when file is deleted."""
        # Create file
        test_file = tmp_path / "code.py"
        test_file.write_text("content")
        file_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Add fact
        fact = ledger.add(
            file_exists("code.py"),
            sample_receipt,
            file_hashes={"code.py": file_hash},
        )

        # Delete file
        test_file.unlink()

        # Should be stale
        assert ledger.check_staleness(fact, base_path=tmp_path) is True

    def test_invalidate_stale(self, ledger, tmp_path, sample_receipt):
        """invalidate_stale removes stale facts."""
        # Create two files
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        file1.write_text("a")
        file2.write_text("b")

        hash1 = hashlib.sha256(b"a").hexdigest()
        hash2 = hashlib.sha256(b"b").hexdigest()

        # Add facts
        fact1 = ledger.add(
            file_exists("a.py"),
            sample_receipt,
            file_hashes={"a.py": hash1},
        )
        fact2 = ledger.add(
            file_exists("b.py"),
            sample_receipt,
            file_hashes={"b.py": hash2},
        )

        # Modify one file
        file1.write_text("a modified")

        # Invalidate stale
        stale = ledger.invalidate_stale(base_path=tmp_path)

        assert fact1.id in stale
        assert fact2.id not in stale
        assert ledger.count == 1

    def test_invalidate_by_changed_files(self, ledger, tmp_path, sample_receipt):
        """invalidate_by_changed_files works with file list."""
        # Add facts
        fact1 = ledger.add(
            file_exists("src/a.py"),
            sample_receipt,
            file_hashes={"src/a.py": "hash1"},
        )
        fact2 = ledger.add(
            file_exists("src/b.py"),
            sample_receipt,
            file_hashes={"src/b.py": "hash2"},
        )
        fact3 = ledger.add(
            file_exists("src/c.py"),
            sample_receipt,
            file_hashes={"src/c.py": "hash3"},
        )

        # Simulate some files changed
        changed = {"src/a.py", "src/c.py"}
        invalidated = ledger.invalidate_by_changed_files(changed, tmp_path)

        assert fact1.id in invalidated
        assert fact2.id not in invalidated
        assert fact3.id in invalidated
        assert ledger.count == 1

    def test_decay_check_comprehensive(self, ledger, tmp_path, sample_receipt):
        """decay_check uses both git and hash detection."""
        # Create file
        test_file = tmp_path / "main.py"
        test_file.write_text("content")
        file_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Add fact
        ledger.add(
            file_exists("main.py"),
            sample_receipt,
            file_hashes={"main.py": file_hash},
        )

        # Modify file
        test_file.write_text("changed")

        # Run decay check
        result = ledger.decay_check(base_path=tmp_path)

        # Should have been invalidated by hash check
        assert len(result["hash_invalidated"]) == 1 or len(result["git_invalidated"]) == 1
        assert ledger.count == 0


class TestDecayCLI:
    """Test the governor decay CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_decay_empty(self, runner, tmp_path):
        """decay with no facts shows empty message."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["decay"])

            assert result.exit_code == 0
            assert "No facts to check" in result.output

    def test_decay_shows_fresh_facts(self, runner, tmp_path):
        """decay shows fresh facts as ok."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("content")

            # Create, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Check decay
            result = runner.invoke(cli, ["decay"])

            assert result.exit_code == 0
            assert "ok" in result.output
            assert "All facts are fresh" in result.output

    def test_decay_detects_stale(self, runner, tmp_path):
        """decay detects stale facts."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            main_file = Path("main.py")
            main_file.write_text("original")

            # Create, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Modify file
            main_file.write_text("modified")

            # Check decay
            result = runner.invoke(cli, ["decay"])

            assert result.exit_code == 0
            assert "STALE" in result.output
            assert "stale fact(s)" in result.output

    def test_decay_auto_prune(self, runner, tmp_path):
        """decay --auto-prune removes stale facts."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            main_file = Path("main.py")
            main_file.write_text("original")

            # Create, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Modify file
            main_file.write_text("modified")

            # Prune
            result = runner.invoke(cli, ["decay", "--auto-prune"])

            assert result.exit_code == 0
            assert "Pruned" in result.output

            # Verify facts are gone
            result = runner.invoke(cli, ["facts"])
            assert "No facts" in result.output


class TestApplyExtractsHashes:
    """Test that apply extracts file hashes for decay tracking."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_apply_stores_file_hash(self, runner, tmp_path):
        """apply stores file hash for staleness detection."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("app.py").write_text("# app")

            # Create, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=app.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Now modify and check decay
            Path("app.py").write_text("# modified app")

            result = runner.invoke(cli, ["decay"])
            assert "STALE" in result.output
