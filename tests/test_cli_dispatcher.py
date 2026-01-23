"""Tests for dispatcher protocol CLI commands."""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path

from governor.cli import cli
from governor.storage import get_storage


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def initialized_dir(tmp_path, runner):
    """Create an initialized governor directory."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["--root", td, "init", "--v2"])
        assert result.exit_code == 0
        yield Path(td)


class TestAgentRegister:
    """Tests for governor agent register."""

    def test_register_new_agent(self, runner, initialized_dir):
        """Can register a new agent."""
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        assert result.exit_code == 0
        assert "registered" in result.output.lower()
        assert "worker-1" in result.output

    def test_register_with_class(self, runner, initialized_dir):
        """Can register agent with specific class."""
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "agent", "register",
                "--id", "arch-1",
                "--class", "architect",
            ],
        )
        assert result.exit_code == 0
        assert "architect" in result.output.lower()

    def test_register_with_capabilities(self, runner, initialized_dir):
        """Can register agent with capabilities."""
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "agent", "register",
                "--id", "worker-1",
                "--capabilities", "changeset,fact",
            ],
        )
        assert result.exit_code == 0
        assert "changeset" in result.output

    def test_update_existing_agent(self, runner, initialized_dir):
        """Re-registering updates existing agent."""
        # First registration
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        # Second registration with different class
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "agent", "register",
                "--id", "worker-1",
                "--class", "architect",
            ],
        )
        assert result.exit_code == 0
        assert "updated" in result.output.lower()


class TestAgentList:
    """Tests for governor agent list."""

    def test_list_empty(self, runner, initialized_dir):
        """List with no agents."""
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "list"],
        )
        assert result.exit_code == 0
        assert "no agents" in result.output.lower()

    def test_list_agents(self, runner, initialized_dir):
        """List registered agents."""
        # Register some agents
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-2", "--class", "implementer"],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "list"],
        )
        assert result.exit_code == 0
        assert "worker-1" in result.output
        assert "worker-2" in result.output

    def test_list_filter_by_class(self, runner, initialized_dir):
        """Can filter agents by class."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1", "--class", "implementer"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "arch-1", "--class", "architect"],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "list", "--class", "architect"],
        )
        assert result.exit_code == 0
        assert "arch-1" in result.output
        assert "worker-1" not in result.output


class TestAgentPermissions:
    """Tests for governor agent permissions."""

    def test_show_permissions(self, runner, initialized_dir):
        """Show permissions for an agent."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1", "--class", "implementer"],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "permissions", "worker-1"],
        )
        assert result.exit_code == 0
        assert "can_propose" in result.output.lower()

    def test_show_permissions_with_class_override(self, runner, initialized_dir):
        """Can override class for permission check."""
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "permissions", "unknown", "--class", "architect"],
        )
        assert result.exit_code == 0
        assert "architect" in result.output.lower()


class TestAgentHeartbeat:
    """Tests for governor agent heartbeat."""

    def test_heartbeat_registered_agent(self, runner, initialized_dir):
        """Heartbeat works for registered agent."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "heartbeat", "--id", "worker-1"],
        )
        assert result.exit_code == 0
        assert "heartbeat" in result.output.lower()

    def test_heartbeat_unregistered_agent(self, runner, initialized_dir):
        """Heartbeat fails for unregistered agent."""
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "heartbeat", "--id", "unknown"],
        )
        assert result.exit_code == 1
        assert "not registered" in result.output.lower()


class TestTaskClaim:
    """Tests for governor task claim."""

    def test_claim_task(self, runner, initialized_dir):
        """Can claim a task."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        assert result.exit_code == 0
        assert "claimed" in result.output.lower()

    def test_claim_task_unregistered_agent(self, runner, initialized_dir):
        """Cannot claim task without registering."""
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "unknown",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        assert result.exit_code == 1
        assert "not registered" in result.output.lower()

    def test_claim_task_with_eta(self, runner, initialized_dir):
        """Can claim task with ETA."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
                "--eta", "60",
            ],
        )
        assert result.exit_code == 0
        assert "60 minutes" in result.output

    def test_claim_conflicting_scope(self, runner, initialized_dir):
        """Cannot claim overlapping scope."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-2"],
        )

        # First claim
        runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )

        # Conflicting claim
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-2",
                "--task", "another feature",
                "--scope", "src/api.py",
            ],
        )
        assert result.exit_code == 1
        assert "conflict" in result.output.lower()


class TestTaskHeartbeat:
    """Tests for governor task heartbeat."""

    def test_heartbeat_task(self, runner, initialized_dir):
        """Can send heartbeat to extend task."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        # Claim task
        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        # Extract task ID from output
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        assert task_id is not None

        # Send heartbeat
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "heartbeat",
                "--agent-id", "worker-1",
                "--task-id", task_id,
            ],
        )
        assert result.exit_code == 0
        assert "heartbeat" in result.output.lower()

    def test_heartbeat_wrong_agent(self, runner, initialized_dir):
        """Cannot heartbeat another agent's task."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-2"],
        )

        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "heartbeat",
                "--agent-id", "worker-2",
                "--task-id", task_id,
            ],
        )
        assert result.exit_code == 1
        assert "worker-1" in result.output  # Shows actual owner


class TestTaskComplete:
    """Tests for governor task complete."""

    def test_complete_task(self, runner, initialized_dir):
        """Can complete a task."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "complete",
                "--agent-id", "worker-1",
                "--task-id", task_id,
            ],
        )
        assert result.exit_code == 0
        assert "completed" in result.output.lower()

    def test_complete_with_proposal(self, runner, initialized_dir):
        """Can complete task with proposal reference."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "complete",
                "--agent-id", "worker-1",
                "--task-id", task_id,
                "--proposal-id", "abc123",
            ],
        )
        assert result.exit_code == 0
        assert "abc123" in result.output


class TestTaskList:
    """Tests for governor task list."""

    def test_list_empty(self, runner, initialized_dir):
        """List with no tasks."""
        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "task", "list"],
        )
        assert result.exit_code == 0
        assert "no tasks" in result.output.lower()

    def test_list_tasks(self, runner, initialized_dir):
        """List active tasks."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "task", "list"],
        )
        assert result.exit_code == 0
        assert "implement feature" in result.output

    def test_list_filter_by_agent(self, runner, initialized_dir):
        """Can filter tasks by agent."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-2"],
        )

        runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "task one",
                "--scope", "src/one.py",
            ],
        )
        runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-2",
                "--task", "task two",
                "--scope", "src/two.py",
            ],
        )

        result = runner.invoke(
            cli,
            ["--root", str(initialized_dir), "task", "list", "--agent-id", "worker-1"],
        )
        assert result.exit_code == 0
        assert "task one" in result.output
        assert "task two" not in result.output


class TestTaskCancel:
    """Tests for governor task cancel."""

    def test_cancel_task(self, runner, initialized_dir):
        """Can cancel a task."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )

        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "cancel",
                "--agent-id", "worker-1",
                "--task-id", task_id,
            ],
        )
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()

    def test_cancel_releases_scope(self, runner, initialized_dir):
        """Cancelling task releases scope for others."""
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-1"],
        )
        runner.invoke(
            cli,
            ["--root", str(initialized_dir), "agent", "register", "--id", "worker-2"],
        )

        # First claim
        claim_result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-1",
                "--task", "implement feature",
                "--scope", "src/api.py",
            ],
        )
        task_id = None
        for line in claim_result.output.split("\n"):
            if "claimed:" in line.lower():
                task_id = line.split(":")[-1].strip()
                break

        # Cancel
        runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "cancel",
                "--agent-id", "worker-1",
                "--task-id", task_id,
            ],
        )

        # Second agent can now claim
        result = runner.invoke(
            cli,
            [
                "--root", str(initialized_dir),
                "task", "claim",
                "--agent-id", "worker-2",
                "--task", "different feature",
                "--scope", "src/api.py",
            ],
        )
        assert result.exit_code == 0
        assert "claimed" in result.output.lower()
