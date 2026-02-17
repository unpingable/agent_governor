# SPDX-License-Identifier: Apache-2.0
"""Tests for agent wrapper."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.wrapper import (
    FileChange,
    DirectorySnapshot,
    generate_unified_diff,
    rollback_changes,
    create_claims_from_changes,
    AgentWrapper,
    wrap_agent,
)
from governor.claims import ClaimType
from governor.cli import cli


class TestFileChange:
    """Test FileChange dataclass."""

    def test_created_change(self):
        """Represents a created file."""
        change = FileChange(
            path="new.py",
            change_type="created",
            new_hash="abc123",
            new_content=b"# new file",
        )

        assert change.path == "new.py"
        assert change.change_type == "created"
        assert change.old_hash is None

    def test_modified_change(self):
        """Represents a modified file."""
        change = FileChange(
            path="existing.py",
            change_type="modified",
            old_hash="old123",
            new_hash="new456",
            old_content=b"# old",
            new_content=b"# new",
        )

        assert change.change_type == "modified"
        assert change.old_hash == "old123"
        assert change.new_hash == "new456"

    def test_deleted_change(self):
        """Represents a deleted file."""
        change = FileChange(
            path="removed.py",
            change_type="deleted",
            old_hash="old123",
            old_content=b"# deleted",
        )

        assert change.change_type == "deleted"
        assert change.new_hash is None


class TestDirectorySnapshot:
    """Test DirectorySnapshot class."""

    def test_captures_files(self, tmp_path):
        """Captures files in directory."""
        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")

        snapshot = DirectorySnapshot(tmp_path)

        assert "a.py" in snapshot.files
        assert "b.py" in snapshot.files

    def test_captures_nested_files(self, tmp_path):
        """Captures nested files."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")

        snapshot = DirectorySnapshot(tmp_path)

        assert "src/main.py" in snapshot.files

    def test_excludes_git_directory(self, tmp_path):
        """Excludes .git directory."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("# git config")
        (tmp_path / "real.py").write_text("# real")

        snapshot = DirectorySnapshot(tmp_path)

        assert "real.py" in snapshot.files
        assert ".git/config" not in snapshot.files

    def test_excludes_governor_directory(self, tmp_path):
        """Excludes .governor directory."""
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "config.toml").write_text("# config")
        (tmp_path / "real.py").write_text("# real")

        snapshot = DirectorySnapshot(tmp_path)

        assert "real.py" in snapshot.files
        assert ".governor/config.toml" not in snapshot.files

    def test_diff_detects_created_file(self, tmp_path):
        """Diff detects created files."""
        before = DirectorySnapshot(tmp_path)

        (tmp_path / "new.py").write_text("# new")

        after = DirectorySnapshot(tmp_path)
        changes = before.diff(after)

        assert len(changes) == 1
        assert changes[0].path == "new.py"
        assert changes[0].change_type == "created"

    def test_diff_detects_modified_file(self, tmp_path):
        """Diff detects modified files."""
        (tmp_path / "existing.py").write_text("# original")

        before = DirectorySnapshot(tmp_path)

        (tmp_path / "existing.py").write_text("# modified")

        after = DirectorySnapshot(tmp_path)
        changes = before.diff(after)

        assert len(changes) == 1
        assert changes[0].path == "existing.py"
        assert changes[0].change_type == "modified"

    def test_diff_detects_deleted_file(self, tmp_path):
        """Diff detects deleted files."""
        (tmp_path / "doomed.py").write_text("# doomed")

        before = DirectorySnapshot(tmp_path)

        (tmp_path / "doomed.py").unlink()

        after = DirectorySnapshot(tmp_path)
        changes = before.diff(after)

        assert len(changes) == 1
        assert changes[0].path == "doomed.py"
        assert changes[0].change_type == "deleted"

    def test_diff_detects_multiple_changes(self, tmp_path):
        """Diff detects multiple changes."""
        (tmp_path / "modified.py").write_text("# original")
        (tmp_path / "deleted.py").write_text("# deleted")

        before = DirectorySnapshot(tmp_path)

        (tmp_path / "created.py").write_text("# new")
        (tmp_path / "modified.py").write_text("# changed")
        (tmp_path / "deleted.py").unlink()

        after = DirectorySnapshot(tmp_path)
        changes = before.diff(after)

        change_types = {c.path: c.change_type for c in changes}
        assert change_types["created.py"] == "created"
        assert change_types["modified.py"] == "modified"
        assert change_types["deleted.py"] == "deleted"


class TestGenerateUnifiedDiff:
    """Test unified diff generation."""

    def test_created_file_diff(self):
        """Generates diff for created file."""
        changes = [FileChange(
            path="new.py",
            change_type="created",
            new_content=b"# line 1\n# line 2",
        )]

        diff = generate_unified_diff(changes)

        assert "--- /dev/null" in diff
        assert "+++ b/new.py" in diff
        assert "+# line 1" in diff

    def test_deleted_file_diff(self):
        """Generates diff for deleted file."""
        changes = [FileChange(
            path="old.py",
            change_type="deleted",
            old_content=b"# goodbye",
        )]

        diff = generate_unified_diff(changes)

        assert "--- a/old.py" in diff
        assert "+++ /dev/null" in diff
        assert "-# goodbye" in diff

    def test_modified_file_diff(self):
        """Generates diff for modified file."""
        changes = [FileChange(
            path="modified.py",
            change_type="modified",
            old_content=b"# old",
            new_content=b"# new",
        )]

        diff = generate_unified_diff(changes)

        assert "--- a/modified.py" in diff
        assert "+++ b/modified.py" in diff
        assert "-# old" in diff
        assert "+# new" in diff


class TestRollbackChanges:
    """Test rollback functionality."""

    def test_rollback_created_file(self, tmp_path):
        """Rollback removes created file."""
        (tmp_path / "new.py").write_text("# new")

        changes = [FileChange(
            path="new.py",
            change_type="created",
        )]

        rollback_changes(tmp_path, changes)

        assert not (tmp_path / "new.py").exists()

    def test_rollback_deleted_file(self, tmp_path):
        """Rollback restores deleted file."""
        changes = [FileChange(
            path="restored.py",
            change_type="deleted",
            old_content=b"# original content",
        )]

        rollback_changes(tmp_path, changes)

        assert (tmp_path / "restored.py").exists()
        assert (tmp_path / "restored.py").read_text() == "# original content"

    def test_rollback_modified_file(self, tmp_path):
        """Rollback restores original content."""
        (tmp_path / "modified.py").write_text("# modified")

        changes = [FileChange(
            path="modified.py",
            change_type="modified",
            old_content=b"# original",
        )]

        rollback_changes(tmp_path, changes)

        assert (tmp_path / "modified.py").read_text() == "# original"

    def test_rollback_creates_parent_directories(self, tmp_path):
        """Rollback creates parent directories for restored files."""
        changes = [FileChange(
            path="src/deep/file.py",
            change_type="deleted",
            old_content=b"# nested",
        )]

        rollback_changes(tmp_path, changes)

        assert (tmp_path / "src" / "deep" / "file.py").exists()


class TestCreateClaimsFromChanges:
    """Test claim creation from changes."""

    def test_creates_file_exists_claims(self):
        """Creates file_exists claims for created/modified files."""
        changes = [
            FileChange(path="new.py", change_type="created"),
            FileChange(path="modified.py", change_type="modified"),
        ]

        claims = create_claims_from_changes(changes)

        file_exists_claims = [c for c in claims if c.type == ClaimType.FILE_EXISTS]
        assert len(file_exists_claims) == 2

    def test_creates_changeset_claim(self):
        """Creates changeset claim for all changes."""
        changes = [
            FileChange(path="a.py", change_type="created", new_content=b"# a"),
            FileChange(path="b.py", change_type="modified", old_content=b"# old", new_content=b"# new"),
        ]

        claims = create_claims_from_changes(changes)

        changeset_claims = [c for c in claims if c.type == ClaimType.CHANGESET]
        assert len(changeset_claims) == 1
        assert "a.py" in changeset_claims[0].paths
        assert "b.py" in changeset_claims[0].paths


class TestAgentWrapper:
    """Test AgentWrapper class."""

    def test_detects_file_changes(self, tmp_path):
        """Detects changes made by command."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        wrapper = AgentWrapper(tmp_path, gov_dir)

        # Run a command that creates a file
        exit_code, changes = wrapper.run([
            sys.executable, "-c",
            f"open('{tmp_path}/created.py', 'w').write('# new')"
        ])

        assert exit_code == 0
        assert len(changes) == 1
        assert changes[0].path == "created.py"
        assert changes[0].change_type == "created"

    def test_enforcement_blocks_unapproved(self, tmp_path):
        """Enforcement blocks unapproved changes."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")
        (gov_dir / "facts").mkdir()
        (gov_dir / "facts" / "index.json").write_text("[]")
        (gov_dir / "decisions").mkdir()
        (gov_dir / "decisions" / "index.json").write_text("[]")

        # Create config with strict mode
        (gov_dir / "config.toml").write_text("""
[envelopes]
default = "strict"
""")

        wrapper = AgentWrapper(tmp_path, gov_dir)

        # Run command that creates a file
        exit_code, message = wrapper.run_with_enforcement([
            sys.executable, "-c",
            f"open('{tmp_path}/blocked.py', 'w').write('# blocked')"
        ])

        # Should be blocked and rolled back
        assert exit_code == 1
        assert "blocked" in message.lower()
        assert not (tmp_path / "blocked.py").exists()

    def test_enforcement_allows_with_auto_approve(self, tmp_path):
        """Enforcement allows with auto-approve in exploratory mode."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")
        (gov_dir / "facts").mkdir()
        (gov_dir / "facts" / "index.json").write_text("[]")
        (gov_dir / "facts" / "receipts").mkdir()
        (gov_dir / "decisions").mkdir()
        (gov_dir / "decisions" / "index.json").write_text("[]")

        # Create config with exploratory mode
        (gov_dir / "config.toml").write_text("""
[envelopes]
default = "exploratory"
""")
        (gov_dir / ".envelope").write_text("exploratory")

        wrapper = AgentWrapper(tmp_path, gov_dir, auto_approve=True)

        # Run command that creates a file
        exit_code, message = wrapper.run_with_enforcement([
            sys.executable, "-c",
            f"open('{tmp_path}/allowed.py', 'w').write('# allowed')"
        ])

        # Should be allowed
        assert exit_code == 0
        assert "approved" in message.lower()
        assert (tmp_path / "allowed.py").exists()


class TestWrapAgent:
    """Test wrap_agent function."""

    def test_runs_without_governor(self, tmp_path):
        """Runs without enforcement when governor not initialized."""
        exit_code, message = wrap_agent(
            [sys.executable, "-c", "print('hello')"],
            root=tmp_path,
        )

        assert exit_code == 0
        assert "not initialized" in message.lower()


class TestWrapCLI:
    """Test wrap CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_wrap_command_exists(self, runner):
        """Wrap command exists."""
        result = runner.invoke(cli, ["wrap", "--help"])

        assert result.exit_code == 0
        assert "wrap" in result.output.lower()

    def test_wrap_runs_command(self, runner, tmp_path):
        """Wrap command runs the specified command."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # No governor initialized, should run without enforcement
            result = runner.invoke(cli, ["wrap", "--", sys.executable, "-c", "print('hello')"])

            assert "not initialized" in result.output.lower()


class TestChangesCLI:
    """Test changes CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_changes_requires_init(self, runner, tmp_path):
        """Changes command requires governor init."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["changes"])

            assert result.exit_code == 1
            assert "not initialized" in result.output.lower()

    def test_changes_requires_git(self, runner, tmp_path):
        """Changes command requires git repo."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["changes"])

            assert result.exit_code == 1
            assert "git" in result.output.lower()

    def test_changes_shows_status(self, runner, tmp_path):
        """Changes command shows file status."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git
            subprocess.run(["git", "init"], capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], capture_output=True)

            runner.invoke(cli, ["init"])

            # Create a file
            Path("test.py").write_text("# test")

            result = runner.invoke(cli, ["changes"])

            assert result.exit_code == 0
            # Should show the file needs approval
            assert "test.py" in result.output or "No uncommitted" in result.output


# =============================================================================
# Receipt Emission
# =============================================================================


class TestWrapperReceipts:
    """Test gate receipt emission from AgentWrapper."""

    def test_pass_receipt_on_approved_changes(self, tmp_path):
        """Approved changes emit a 'pass' receipt."""
        from governor.gate_receipt import GateReceiptSystem

        root = tmp_path / "project"
        root.mkdir()
        gov_dir = root / ".governor"
        gov_dir.mkdir()

        # Set exploratory envelope (require_receipts=False, enables auto_approve)
        envelope_path = gov_dir / ".envelope"
        envelope_path.write_text("exploratory")

        proposals_path = gov_dir / "proposals.json"
        proposals_path.write_text("{}")

        wrapper = AgentWrapper(
            root=root,
            gov_dir=gov_dir,
            auto_approve=True,
        )

        # Simulate: create a file, then run enforcement
        # We'll use a command that creates a file
        script = root / "create_file.sh"
        script.write_text('#!/bin/sh\necho "hello" > "$1/new_file.txt"')
        script.chmod(0o755)

        exit_code, message = wrapper.run_with_enforcement(
            [str(script), str(root)]
        )

        assert "Approved" in message

        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="wrapper")
        assert len(receipts) == 1
        assert receipts[0].verdict == "pass"

    def test_block_receipt_on_rejected_changes(self, tmp_path):
        """Rejected changes emit a 'block' receipt."""
        from governor.gate_receipt import GateReceiptSystem

        root = tmp_path / "project"
        root.mkdir()
        gov_dir = root / ".governor"
        gov_dir.mkdir()

        # Set strict envelope (require receipts)
        envelope_path = gov_dir / ".envelope"
        envelope_path.write_text("strict")

        proposals_path = gov_dir / "proposals.json"
        proposals_path.write_text("{}")

        wrapper = AgentWrapper(
            root=root,
            gov_dir=gov_dir,
            auto_approve=False,
            on_changes=lambda _: False,  # Always reject
        )

        # Create a file via command
        script = root / "create_file.sh"
        script.write_text('#!/bin/sh\necho "hello" > "$1/new_file.txt"')
        script.chmod(0o755)

        exit_code, message = wrapper.run_with_enforcement(
            [str(script), str(root)]
        )

        assert "Blocked" in message

        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="wrapper")
        assert len(receipts) == 1
        assert receipts[0].verdict == "block"

    def test_receipt_evidence_has_changes(self, tmp_path):
        """Receipt evidence contains file change details."""
        from governor.gate_receipt import GateReceiptSystem

        root = tmp_path / "project"
        root.mkdir()
        gov_dir = root / ".governor"
        gov_dir.mkdir()

        envelope_path = gov_dir / ".envelope"
        envelope_path.write_text("exploratory")
        proposals_path = gov_dir / "proposals.json"
        proposals_path.write_text("{}")

        wrapper = AgentWrapper(
            root=root, gov_dir=gov_dir, auto_approve=True,
        )

        script = root / "create_file.sh"
        script.write_text('#!/bin/sh\necho "hello" > "$1/new_file.txt"')
        script.chmod(0o755)

        wrapper.run_with_enforcement([str(script), str(root)])

        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="wrapper")
        evidence = system.evidence_for(receipts[0])
        assert "changes" in evidence
        assert len(evidence["changes"]) > 0
        assert evidence["changes"][0]["type"] == "created"

    def test_no_receipt_without_changes(self, tmp_path):
        """No receipt emitted when there are no file changes."""
        from governor.gate_receipt import GateReceiptSystem

        root = tmp_path / "project"
        root.mkdir()
        gov_dir = root / ".governor"
        gov_dir.mkdir()

        wrapper = AgentWrapper(root=root, gov_dir=gov_dir)

        # Command that does nothing
        exit_code, message = wrapper.run_with_enforcement(["true"])
        assert "No file changes" in message

        system = GateReceiptSystem(gov_dir)
        receipts = system.query(gate="wrapper")
        assert len(receipts) == 0
