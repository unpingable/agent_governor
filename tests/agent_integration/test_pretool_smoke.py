# SPDX-License-Identifier: Apache-2.0
"""
Pre-tool smoke tests (effective enforcement).

After install + strict + empty approved list:
  - execute pre_tool_use.py with a synthetic Write event
  - assert exit code == 2 and stdout contains "decision":"block"

This proves the enforcement code is correct. It does *not* prove the agent
is calling it, but it prevents the "hook template bug" class completely.

This is the same test that `governor preflight` runs under the hood.
"""

import json
import subprocess
from pathlib import Path

import pytest

from governor.claude_hooks import (
    install_hook_scripts,
    create_approved_files_file,
    create_blocked_commands_file,
)
from governor.preflight import smoke_test_claude_hook, run_preflight


class TestSmokeTestDirectExecution:
    """Run the actual hook script and verify it blocks."""

    def _setup(self, tmp_path, mode="strict", approved=None, blocked=None):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text(mode)
        create_approved_files_file(tmp_path, approved or [])
        if blocked is not None:
            create_blocked_commands_file(tmp_path, blocked)
        install_hook_scripts(tmp_path)
        return tmp_path

    def _run(self, project_dir, payload):
        hook = project_dir / ".governor" / "hooks" / "pre_tool_use.py"
        return subprocess.run(
            ["python3", str(hook)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_dir),
        )

    def test_strict_empty_list_blocks_any_write(self, tmp_path):
        """The canonical test: strict + nothing approved = everything blocked."""
        project = self._setup(tmp_path)
        result = self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "anything.py", "content": "x"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_output_is_valid_json(self, tmp_path):
        """Hook stdout must be parseable JSON for Claude Code to process."""
        project = self._setup(tmp_path)
        result = self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "x.py", "content": "x"},
        })
        # Must not throw
        output = json.loads(result.stdout)
        assert "decision" in output
        assert "reason" in output

    def test_block_output_includes_message(self, tmp_path):
        """Block output should include a human-readable message."""
        project = self._setup(tmp_path)
        result = self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "x.py", "content": "x"},
        })
        output = json.loads(result.stdout)
        assert "message" in output
        assert len(output["message"]) > 0

    def test_allowed_write_exits_zero_no_output(self, tmp_path):
        """Allowed writes exit 0. No JSON output needed."""
        project = self._setup(tmp_path, approved=["safe.py"])
        result = self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "safe.py", "content": "x"},
        })
        assert result.returncode == 0

    def test_invalid_json_input_exits_zero(self, tmp_path):
        """Hook receiving garbage on stdin should allow (fail-open for unknown tools)."""
        project = self._setup(tmp_path)
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        result = subprocess.run(
            ["python3", str(hook)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project),
        )
        assert result.returncode == 0

    def test_empty_stdin_exits_zero(self, tmp_path):
        """Hook with no stdin should allow (Claude Code may send nothing)."""
        project = self._setup(tmp_path)
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        result = subprocess.run(
            ["python3", str(hook)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project),
        )
        assert result.returncode == 0


class TestInvocationStamp:
    """Verify hooks write invocation stamps that prove they're live."""

    def _setup(self, tmp_path, mode="strict", approved=None):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text(mode)
        create_approved_files_file(tmp_path, approved or [])
        install_hook_scripts(tmp_path)
        return tmp_path

    def _run(self, project_dir, payload):
        hook = project_dir / ".governor" / "hooks" / "pre_tool_use.py"
        return subprocess.run(
            ["python3", str(hook)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_dir),
        )

    def test_block_writes_invocation(self, tmp_path):
        """Blocked action creates hook_invocations.jsonl entry."""
        project = self._setup(tmp_path)
        self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py", "content": "x"},
        })
        inv = project / ".governor" / "hook_invocations.jsonl"
        assert inv.exists()
        entries = [json.loads(l) for l in inv.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["decision"] == "block"
        assert entries[0]["tool"] == "Write"

    def test_allow_writes_invocation(self, tmp_path):
        """Allowed action also creates hook_invocations.jsonl entry."""
        project = self._setup(tmp_path, approved=["safe.py"])
        self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "safe.py", "content": "x"},
        })
        inv = project / ".governor" / "hook_invocations.jsonl"
        assert inv.exists()
        entries = [json.loads(l) for l in inv.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["decision"] == "allow"

    def test_failopen_logs_detail(self, tmp_path):
        """Fail-open on garbage stdin logs the event."""
        project = self._setup(tmp_path)
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        subprocess.run(
            ["python3", str(hook)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project),
        )
        inv = project / ".governor" / "hook_invocations.jsonl"
        assert inv.exists()
        entries = [json.loads(l) for l in inv.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["decision"] == "allow"
        assert "fail-open" in entries[0].get("detail", "")

    def test_multiple_invocations_append(self, tmp_path):
        """Multiple hook calls append, don't overwrite."""
        project = self._setup(tmp_path, approved=["a.py"])
        self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "a.py", "content": "x"},
        })
        self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "b.py", "content": "x"},
        })
        inv = project / ".governor" / "hook_invocations.jsonl"
        entries = [json.loads(l) for l in inv.read_text().strip().splitlines()]
        assert len(entries) == 2
        assert entries[0]["decision"] == "allow"
        assert entries[1]["decision"] == "block"

    def test_invocation_has_timestamp(self, tmp_path):
        """Each invocation includes an ISO timestamp."""
        project = self._setup(tmp_path)
        self._run(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "x.py", "content": "x"},
        })
        inv = project / ".governor" / "hook_invocations.jsonl"
        entries = [json.loads(l) for l in inv.read_text().strip().splitlines()]
        assert "timestamp" in entries[0]
        # Should be ISO format
        assert "T" in entries[0]["timestamp"]


class TestPreflightSmoke:
    """Verify `governor preflight` smoke test matches direct execution."""

    def test_preflight_smoke_passes_in_strict(self, tmp_path):
        """Preflight smoke test should pass when hooks are correctly installed."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        create_approved_files_file(tmp_path, [])
        install_hook_scripts(tmp_path)

        result = smoke_test_claude_hook(tmp_path)
        assert result.status == "pass"

    def test_preflight_full_green_in_strict(self, tmp_path):
        """Full preflight with all Claude infra should be passable."""
        from governor.claude_hooks import install_claude_hooks
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        create_approved_files_file(tmp_path, ["src/main.py"])
        install_claude_hooks(tmp_path)
        # Create git hook
        hook_dir = tmp_path / ".git" / "hooks"
        hook_dir.mkdir(parents=True)
        hook = hook_dir / "pre-commit"
        hook.write_text("#!/bin/sh\ngovernor hook pre-commit")
        hook.chmod(0o755)
        # Create notification so restart advisory passes
        (gov_dir / "notifications.jsonl").write_text('{"event":"test"}\n')

        result = run_preflight(tmp_path, agent="claude")
        # Should be pass or warn (restart advisory may warn)
        assert result.overall in ("pass", "warn")
        # No fails
        fails = [c for c in result.checks if c.status == "fail"]
        assert fails == [], f"Unexpected fails: {fails}"
