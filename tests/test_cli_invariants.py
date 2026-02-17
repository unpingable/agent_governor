# SPDX-License-Identifier: Apache-2.0
"""
Tests for CLI invariant management commands and autonomous run.
Deferred 1: Invariant management CLI + execution shell.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_dir(runner, tmp_path):
    """Create an initialized governor project."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        yield Path(td)


# =============================================================================
# TestInvariantAdd
# =============================================================================


class TestInvariantAdd:
    def test_add_no_secrets(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets"]
        )
        assert result.exit_code == 0
        assert "no_secrets" in result.output
        assert "added" in result.output.lower()

    def test_add_file_exists(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists", "--path", "README.md"],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_add_dir_exists(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "dir-exists", "--path", "src"],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_add_forbidden(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "forbidden", "--pattern", "*.secret"],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_add_max_file_size(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "max-file-size", "--max-kb", "100"],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_add_test_kind(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "test", "--command", "echo"],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_add_custom_id(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "my_custom_id"],
        )
        assert result.exit_code == 0
        assert "my_custom_id" in result.output

    def test_add_warn_violation(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--on-violation", "warn"],
        )
        assert result.exit_code == 0
        assert "warn" in result.output

    def test_add_file_exists_missing_path(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists"],
        )
        assert result.exit_code != 0
        assert "path" in result.output.lower()

    def test_add_forbidden_missing_pattern(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "forbidden"],
        )
        assert result.exit_code != 0
        assert "pattern" in result.output.lower()


# =============================================================================
# TestInvariantList
# =============================================================================


class TestInvariantList:
    def test_list_empty(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "list"]
        )
        assert result.exit_code == 0
        assert "no invariants" in result.output.lower()

    def test_list_after_add(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets"]
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "list"]
        )
        assert result.exit_code == 0
        assert "no_secrets" in result.output
        assert "no-secrets" in result.output  # kind

    def test_list_multiple(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets"]
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists", "--path", "README.md", "--id", "readme"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "list"]
        )
        assert result.exit_code == 0
        assert "Total: 2" in result.output

    def test_list_warn_marker(self, runner, initialized_dir):
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--on-violation", "warn"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "list"]
        )
        assert result.exit_code == 0
        assert "warn" in result.output


# =============================================================================
# TestInvariantShow
# =============================================================================


class TestInvariantShow:
    def test_show_existing(self, runner, initialized_dir):
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists", "--path", "README.md", "--id", "readme_check"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "show", "readme_check"]
        )
        assert result.exit_code == 0
        assert "readme_check" in result.output
        assert "file-exists" in result.output
        assert "README.md" in result.output

    def test_show_nonexistent(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "show", "nope"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_show_params_displayed(self, runner, initialized_dir):
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "max-file-size", "--max-kb", "250", "--id", "size_check"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "show", "size_check"]
        )
        assert result.exit_code == 0
        assert "250" in result.output


# =============================================================================
# TestInvariantRemove
# =============================================================================


class TestInvariantRemove:
    def test_remove_existing(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "to_remove"]
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "remove", "to_remove"]
        )
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_remove_nonexistent(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "remove", "nope"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_remove_then_list(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "rm_test"]
        )
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "remove", "rm_test"]
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "list"]
        )
        assert result.exit_code == 0
        assert "no invariants" in result.output.lower()


# =============================================================================
# TestInvariantCheck
# =============================================================================


class TestInvariantCheck:
    def test_check_pass(self, runner, initialized_dir):
        # no-secrets with no files = pass
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets"]
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check"]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_dir_exists_fail(self, runner, initialized_dir):
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "dir-exists", "--path", "nonexistent_dir", "--id", "dir_check"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check"]
        )
        assert result.exit_code != 0
        assert "FAIL" in result.output

    def test_check_file_exists_pass(self, runner, initialized_dir):
        # Create the file
        (initialized_dir / "test_file.txt").write_text("hello")
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists", "--path", "test_file.txt", "--id", "file_check"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check"]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_specific_id(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "specific"]
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check", "--id", "specific"]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_no_invariants(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check"]
        )
        assert result.exit_code == 0
        assert "no invariants" in result.output.lower()

    def test_check_summary(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "ns"]
        )
        (initialized_dir / "test_exists.txt").write_text("hi")
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "invariant", "add", "file-exists", "--path", "test_exists.txt", "--id", "fe"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check"]
        )
        assert result.exit_code == 0
        assert "Summary:" in result.output
        assert "2 passed" in result.output

    def test_check_nonexistent_id(self, runner, initialized_dir):
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "check", "--id", "missing"]
        )
        assert result.exit_code != 0


# =============================================================================
# TestAutonomousRun
# =============================================================================


class TestAutonomousRun:
    def test_dry_run(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Test task", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        assert "PAUSED" in result.output or "paused" in result.output.lower()
        assert "Test task" in result.output

    def test_normal_run(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Noop task"],
        )
        assert result.exit_code == 0
        assert "completed" in result.output.lower()

    def test_run_with_budget(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Budget task", "--budget", "iterations=5"],
        )
        assert result.exit_code == 0
        assert "completed" in result.output.lower()

    def test_run_with_invalid_spine(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Bad spine", "--spine-id", "nonexistent"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_run_creates_session(self, runner, initialized_dir):
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Session test"],
        )
        result = runner.invoke(
            cli, ["--root", str(initialized_dir), "autonomous", "list"]
        )
        assert result.exit_code == 0
        assert "Session test" in result.output

    def test_dry_run_with_invariants(self, runner, initialized_dir):
        runner.invoke(
            cli, ["--root", str(initialized_dir), "invariant", "add", "no-secrets", "--id", "ns"]
        )
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "With inv", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "ns" in result.output
        assert "1" in result.output  # Invariants: 1

    def test_run_with_spine(self, runner, initialized_dir):
        # Create a spine first
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "spine", "lock", "test_spine", "-rd", "src"],
        )
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run", "--task", "Spine task", "--spine-id", "test_spine"],
        )
        assert result.exit_code == 0

    def test_run_task_required(self, runner, initialized_dir):
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "autonomous", "run"],
        )
        assert result.exit_code != 0
