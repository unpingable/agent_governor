"""Tests for git hooks integration."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from governor.hooks import (
    get_git_root,
    get_staged_files,
    get_approved_files,
    check_staged_files,
    run_pre_commit_check,
    install_hook,
    uninstall_hook,
    get_hook_status,
    PRE_COMMIT_HOOK,
)
from governor.cli import cli
from governor.fsm import Proposal, ProposalState
from governor.claims import file_exists


def init_git_repo(path: Path) -> None:
    """Initialize a git repository at the given path."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        capture_output=True,
    )


class TestGetGitRoot:
    """Test git root detection."""

    def test_finds_git_root(self, tmp_path):
        """Finds git root in a repo."""
        init_git_repo(tmp_path)

        root = get_git_root(tmp_path)

        assert root == tmp_path

    def test_returns_none_outside_repo(self, tmp_path):
        """Returns None when not in a git repo."""
        root = get_git_root(tmp_path)

        assert root is None

    def test_finds_root_from_subdir(self, tmp_path):
        """Finds git root from subdirectory."""
        init_git_repo(tmp_path)
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)

        root = get_git_root(subdir)

        assert root == tmp_path


class TestGetStagedFiles:
    """Test getting staged files."""

    def test_no_staged_files(self, tmp_path):
        """Returns empty list when nothing staged."""
        init_git_repo(tmp_path)

        files = get_staged_files(tmp_path)

        assert files == []

    def test_returns_staged_files(self, tmp_path):
        """Returns list of staged files."""
        init_git_repo(tmp_path)

        # Create and stage a file
        (tmp_path / "test.py").write_text("# test")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)

        files = get_staged_files(tmp_path)

        assert "test.py" in files

    def test_multiple_staged_files(self, tmp_path):
        """Returns multiple staged files."""
        init_git_repo(tmp_path)

        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        subprocess.run(["git", "add", "a.py", "b.py"], cwd=tmp_path, capture_output=True)

        files = get_staged_files(tmp_path)

        assert "a.py" in files
        assert "b.py" in files


class TestGetApprovedFiles:
    """Test getting approved files from proposals."""

    def test_no_proposals(self, tmp_path):
        """Returns empty set when no proposals."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        approved = get_approved_files(gov_dir)

        assert approved == set()

    def test_gets_files_from_applied_proposal(self, tmp_path):
        """Gets files from applied proposals."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create an applied proposal
        proposal = Proposal(
            id=uuid4(),
            claims=[file_exists("src/main.py")],
            state=ProposalState.APPLIED,
            created_at=datetime.now(timezone.utc),
            applied_at=datetime.now(timezone.utc),
        )

        proposals = {str(proposal.id): proposal.to_dict()}
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))

        approved = get_approved_files(gov_dir)

        assert "src/main.py" in approved

    def test_ignores_non_applied_proposals(self, tmp_path):
        """Ignores proposals that aren't applied."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create a verified but not applied proposal
        proposal = Proposal(
            id=uuid4(),
            claims=[file_exists("pending.py")],
            state=ProposalState.VERIFIED,
            created_at=datetime.now(timezone.utc),
        )

        proposals = {str(proposal.id): proposal.to_dict()}
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))

        approved = get_approved_files(gov_dir)

        assert "pending.py" not in approved


class TestCheckStagedFiles:
    """Test checking staged files against approved files."""

    def test_all_approved(self, tmp_path):
        """All staged files are approved."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create applied proposal for test.py
        proposal = Proposal(
            id=uuid4(),
            claims=[file_exists("test.py")],
            state=ProposalState.APPLIED,
            created_at=datetime.now(timezone.utc),
            applied_at=datetime.now(timezone.utc),
        )
        (gov_dir / "proposals.json").write_text(
            json.dumps({str(proposal.id): proposal.to_dict()})
        )

        # Stage test.py
        (tmp_path / "test.py").write_text("# test")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)

        approved, unapproved = check_staged_files(tmp_path, gov_dir)

        assert "test.py" in approved
        assert unapproved == []

    def test_some_unapproved(self, tmp_path):
        """Some staged files are not approved."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        # Stage a file without approval
        (tmp_path / "unapproved.py").write_text("# nope")
        subprocess.run(["git", "add", "unapproved.py"], cwd=tmp_path, capture_output=True)

        approved, unapproved = check_staged_files(tmp_path, gov_dir)

        assert "unapproved.py" in unapproved

    def test_governor_files_always_approved(self, tmp_path):
        """Files in .governor/ are always approved."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        # Stage a governor file
        (gov_dir / "config.toml").write_text("# config")
        subprocess.run(
            ["git", "add", ".governor/config.toml"],
            cwd=tmp_path,
            capture_output=True,
        )

        approved, unapproved = check_staged_files(tmp_path, gov_dir)

        assert ".governor/config.toml" in approved


class TestRunPreCommitCheck:
    """Test the pre-commit check."""

    def test_allows_when_no_governor(self, tmp_path):
        """Allows commit when governor not initialized."""
        init_git_repo(tmp_path)

        success, message = run_pre_commit_check(tmp_path)

        assert success is True
        assert "not initialized" in message.lower()

    def test_allows_when_no_staged_files(self, tmp_path):
        """Allows commit when no files staged."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        success, message = run_pre_commit_check(tmp_path)

        assert success is True

    def test_blocks_unapproved_files(self, tmp_path):
        """Blocks commit with unapproved files."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        # Stage unapproved file
        (tmp_path / "bad.py").write_text("# bad")
        subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, capture_output=True)

        success, message = run_pre_commit_check(tmp_path)

        assert success is False
        assert "COMMIT BLOCKED" in message
        assert "bad.py" in message

    def test_allows_bypass(self, tmp_path):
        """Allows commit when bypass flag is set."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")

        # Stage unapproved file
        (tmp_path / "bad.py").write_text("# bad")
        subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, capture_output=True)

        success, message = run_pre_commit_check(tmp_path, bypass=True)

        assert success is True
        assert "bypass" in message.lower()

    def test_one_time_bypass_file(self, tmp_path):
        """One-time bypass file works and is consumed."""
        init_git_repo(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")
        (gov_dir / ".bypass").write_text("")

        # Stage unapproved file
        (tmp_path / "bad.py").write_text("# bad")
        subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, capture_output=True)

        # First check uses bypass
        success, message = run_pre_commit_check(tmp_path)
        assert success is True
        assert "bypass" in message.lower()

        # Bypass file should be consumed
        assert not (gov_dir / ".bypass").exists()

        # Second check should fail
        success2, message2 = run_pre_commit_check(tmp_path)
        assert success2 is False


class TestInstallHook:
    """Test hook installation."""

    def test_installs_hook(self, tmp_path):
        """Installs the pre-commit hook."""
        init_git_repo(tmp_path)

        success, message = install_hook(tmp_path)

        assert success is True
        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists()
        assert "governor" in hook_path.read_text()

    def test_hook_is_executable(self, tmp_path):
        """Installed hook is executable."""
        init_git_repo(tmp_path)

        install_hook(tmp_path)

        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
        assert hook_path.stat().st_mode & 0o111 != 0

    def test_backs_up_existing_hook(self, tmp_path):
        """Backs up existing hook."""
        init_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\necho old")

        success, message = install_hook(tmp_path)

        assert success is True
        assert (hooks_dir / "pre-commit.backup").exists()
        assert "backup" in message.lower()

    def test_idempotent_if_already_installed(self, tmp_path):
        """Does nothing if governor hook already installed."""
        init_git_repo(tmp_path)

        install_hook(tmp_path)
        success, message = install_hook(tmp_path)

        assert success is True
        assert "already installed" in message.lower()


class TestUninstallHook:
    """Test hook uninstallation."""

    def test_uninstalls_hook(self, tmp_path):
        """Uninstalls the hook."""
        init_git_repo(tmp_path)
        install_hook(tmp_path)

        success, message = uninstall_hook(tmp_path)

        assert success is True
        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
        assert not hook_path.exists()

    def test_restores_backup(self, tmp_path):
        """Restores backup hook."""
        init_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\necho old")

        install_hook(tmp_path)
        success, message = uninstall_hook(tmp_path)

        assert success is True
        hook_path = hooks_dir / "pre-commit"
        assert hook_path.exists()
        assert "old" in hook_path.read_text()
        assert "restored" in message.lower()

    def test_refuses_to_uninstall_non_governor_hook(self, tmp_path):
        """Won't uninstall a hook that isn't ours."""
        init_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\necho other")

        success, message = uninstall_hook(tmp_path)

        assert success is False
        assert "not a governor hook" in message.lower()


class TestGetHookStatus:
    """Test hook status reporting."""

    def test_not_installed(self, tmp_path):
        """Reports when hook not installed."""
        init_git_repo(tmp_path)

        status = get_hook_status(tmp_path)

        assert status["installed"] is False

    def test_installed_governor_hook(self, tmp_path):
        """Reports governor hook details."""
        init_git_repo(tmp_path)
        install_hook(tmp_path)

        status = get_hook_status(tmp_path)

        assert status["installed"] is True
        assert status["is_governor_hook"] is True
        assert status["executable"] is True


class TestHookCLI:
    """Test hook CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_hook_install_command(self, runner, tmp_path):
        """CLI can install hook."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())

            result = runner.invoke(cli, ["hook", "install"])

            assert result.exit_code == 0
            assert "installed" in result.output.lower()

    def test_hook_uninstall_command(self, runner, tmp_path):
        """CLI can uninstall hook."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())
            runner.invoke(cli, ["hook", "install"])

            result = runner.invoke(cli, ["hook", "uninstall"])

            assert result.exit_code == 0
            assert "removed" in result.output.lower()

    def test_hook_status_command(self, runner, tmp_path):
        """CLI can show hook status."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())

            result = runner.invoke(cli, ["hook", "status"])

            assert result.exit_code == 0
            assert "installed" in result.output.lower()

    def test_hook_bypass_command(self, runner, tmp_path):
        """CLI can create bypass."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["hook", "bypass"])

            assert result.exit_code == 0
            assert "bypass" in result.output.lower()
            assert (Path.cwd() / ".governor" / ".bypass").exists()

    def test_hook_pre_commit_blocks_unapproved(self, runner, tmp_path):
        """Pre-commit command blocks unapproved files."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())
            runner.invoke(cli, ["init"])

            # Stage unapproved file
            Path("test.py").write_text("# test")
            subprocess.run(["git", "add", "test.py"], capture_output=True)

            result = runner.invoke(cli, ["hook", "pre-commit"])

            assert result.exit_code == 1
            assert "BLOCKED" in result.output


class TestHookIntegration:
    """Integration tests for the hook workflow."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_approved_file_commits(self, runner, tmp_path):
        """File approved via governor can be committed."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())
            runner.invoke(cli, ["init"])

            # Create and approve a file
            Path("approved.py").write_text("# approved")

            # Propose, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=approved.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Stage the file
            subprocess.run(["git", "add", "approved.py"], capture_output=True)

            # Pre-commit should pass
            result = runner.invoke(cli, ["hook", "pre-commit"])

            assert result.exit_code == 0
            assert "approved" in result.output.lower()

    def test_mixed_files_blocks(self, runner, tmp_path):
        """Mixed approved/unapproved files blocks."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            init_git_repo(Path.cwd())
            runner.invoke(cli, ["init"])

            # Create and approve one file
            Path("approved.py").write_text("# approved")
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=approved.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Create unapproved file
            Path("unapproved.py").write_text("# nope")

            # Stage both
            subprocess.run(["git", "add", "approved.py", "unapproved.py"], capture_output=True)

            # Pre-commit should fail
            result = runner.invoke(cli, ["hook", "pre-commit"])

            assert result.exit_code == 1
            assert "unapproved.py" in result.output
