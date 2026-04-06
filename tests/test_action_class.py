# SPDX-License-Identifier: Apache-2.0
"""Tests for action classification: READ < WRITE < COMMUNICATE."""

from __future__ import annotations

import pytest

from governor.runtime.supervisor import ActionClass, classify_action


class TestClassifyAction:
    """Static tool-name classification."""

    def test_read_tools(self):
        for tool in ("Read", "read", "Glob", "glob", "Grep", "grep",
                      "read_file", "grep_search"):
            assert classify_action(tool) == ActionClass.READ, f"{tool} should be READ"

    def test_write_tools(self):
        for tool in ("Write", "write", "Edit", "edit", "Bash", "bash",
                      "NotebookEdit", "notebookedit",
                      "replace", "write_file", "run_shell_command"):
            assert classify_action(tool) == ActionClass.WRITE, f"{tool} should be WRITE"

    def test_unknown_tool_defaults_to_write(self):
        assert classify_action("SomeNewTool") == ActionClass.WRITE

    def test_case_insensitive(self):
        assert classify_action("READ") == ActionClass.READ
        assert classify_action("BASH") == ActionClass.WRITE


class TestCommunicateUpgrade:
    """Dynamic upgrade from WRITE to COMMUNICATE based on command content."""

    def test_curl_is_communicate(self):
        assert classify_action("Bash", {"command": "curl -X POST https://slack.com/api/chat"}) == ActionClass.COMMUNICATE

    def test_git_push_is_communicate(self):
        assert classify_action("Bash", {"command": "git push origin main"}) == ActionClass.COMMUNICATE

    def test_gh_pr_is_communicate(self):
        assert classify_action("Bash", {"command": "gh pr create --title 'fix'"}) == ActionClass.COMMUNICATE

    def test_gh_issue_is_communicate(self):
        assert classify_action("Bash", {"command": "gh issue comment 42 --body 'done'"}) == ActionClass.COMMUNICATE

    def test_sendmail_is_communicate(self):
        assert classify_action("Bash", {"command": "echo body | sendmail user@example.com"}) == ActionClass.COMMUNICATE

    def test_wget_is_communicate(self):
        assert classify_action("Bash", {"command": "wget --post-data=x https://api.example.com"}) == ActionClass.COMMUNICATE

    def test_regular_bash_stays_write(self):
        assert classify_action("Bash", {"command": "pytest tests/ -v"}) == ActionClass.WRITE

    def test_ls_stays_write(self):
        assert classify_action("Bash", {"command": "ls -la"}) == ActionClass.WRITE

    def test_empty_command_stays_write(self):
        assert classify_action("Bash", {"command": ""}) == ActionClass.WRITE

    def test_no_tool_input_stays_write(self):
        assert classify_action("Bash", None) == ActionClass.WRITE

    def test_read_tool_not_upgraded(self):
        # Read tools should never upgrade to COMMUNICATE
        assert classify_action("Read", {"command": "curl something"}) == ActionClass.READ

    def test_case_insensitive_pattern(self):
        assert classify_action("Bash", {"command": "CURL -X POST https://example.com"}) == ActionClass.COMMUNICATE

    def test_gemini_shell_upgrade(self):
        assert classify_action("run_shell_command", {"command": "git push"}) == ActionClass.COMMUNICATE


class TestActionClassOrdering:
    """Action classes have meaningful ordering for policy decisions."""

    def test_read_less_than_write(self):
        # Enum comparison by definition order
        classes = list(ActionClass)
        assert classes.index(ActionClass.READ) < classes.index(ActionClass.WRITE)

    def test_write_less_than_communicate(self):
        classes = list(ActionClass)
        assert classes.index(ActionClass.WRITE) < classes.index(ActionClass.COMMUNICATE)
