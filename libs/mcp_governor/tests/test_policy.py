# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.policy."""

import pytest

from mcp_governor.policy import PolicyEngine
from mcp_governor.types import ReasonCode


class TestAllowDefault:
    def test_allow_no_deny_list(self):
        engine = PolicyEngine(deny_tools=[], default_policy="allow")
        d = engine.evaluate("echo")
        assert d.allow is True
        assert d.reason_code == ReasonCode.POLICY_ALLOW

    def test_deny_matching_tool(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow")
        d = engine.evaluate("shell.exec")
        assert d.allow is False
        assert d.reason_code == ReasonCode.POLICY_DENY
        assert d.matched_pattern == r"shell\..*"

    def test_allow_non_matching_tool(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow")
        d = engine.evaluate("echo")
        assert d.allow is True
        assert d.reason_code == ReasonCode.POLICY_ALLOW

    def test_multiple_deny_patterns(self):
        engine = PolicyEngine(
            deny_tools=[r"shell\..*", r"dangerous\..*"],
            default_policy="allow",
        )
        assert engine.evaluate("shell.exec").allow is False
        assert engine.evaluate("dangerous.rm").allow is False
        assert engine.evaluate("echo").allow is True

    def test_fullmatch_not_search(self):
        """Deny patterns must match the full tool name, not a substring."""
        engine = PolicyEngine(deny_tools=[r"shell"], default_policy="allow")
        assert engine.evaluate("shell").allow is False
        assert engine.evaluate("shell.exec").allow is True  # no fullmatch
        assert engine.evaluate("myshell").allow is True


class TestDenyDefault:
    def test_deny_all_when_empty_deny_list(self):
        engine = PolicyEngine(deny_tools=[], default_policy="deny")
        d = engine.evaluate("echo")
        assert d.allow is False
        assert d.reason_code == ReasonCode.DEFAULT_DENY

    def test_deny_matching_takes_priority(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="deny")
        d = engine.evaluate("shell.exec")
        assert d.allow is False
        assert d.reason_code == ReasonCode.POLICY_DENY  # explicit deny, not default


class TestPassthroughWarn:
    def test_passthrough_allows_denied_tool(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow-warn")
        d = engine.evaluate("shell.exec")
        assert d.allow is True
        assert d.reason_code == ReasonCode.PASSTHROUGH
        assert d.matched_pattern == r"shell\..*"

    def test_passthrough_clean_allow(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow-warn")
        d = engine.evaluate("echo")
        assert d.allow is True
        assert d.reason_code == ReasonCode.POLICY_ALLOW


class TestFilterTools:
    def test_filter_removes_denied(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow")
        result = engine.filter_tools(["echo", "shell.exec", "read_file"])
        assert result == ["echo", "read_file"]

    def test_filter_passthrough_keeps_all(self):
        engine = PolicyEngine(deny_tools=[r"shell\..*"], default_policy="allow-warn")
        result = engine.filter_tools(["echo", "shell.exec", "read_file"])
        assert result == ["echo", "shell.exec", "read_file"]

    def test_filter_deny_default_removes_all(self):
        engine = PolicyEngine(deny_tools=[], default_policy="deny")
        result = engine.filter_tools(["echo", "read_file"])
        assert result == []


class TestValidation:
    def test_invalid_default_policy(self):
        with pytest.raises(ValueError, match="Invalid default_policy"):
            PolicyEngine(default_policy="yolo")

    def test_invalid_regex(self):
        with pytest.raises(ValueError, match="Invalid deny regex"):
            PolicyEngine(deny_tools=["[invalid"])
