# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.types."""

from mcp_governor.types import (
    ActorInfo,
    GatewaySession,
    PolicyDecision,
    ReasonCode,
    ToolCallEnvelope,
)


class TestReasonCode:
    def test_values(self):
        assert ReasonCode.POLICY_ALLOW == "gov.policy_allow"
        assert ReasonCode.PASSTHROUGH == "gov.passthrough"
        assert ReasonCode.POLICY_DENY == "gov.policy_deny"
        assert ReasonCode.DEFAULT_DENY == "gov.default_deny"

    def test_all_namespaced(self):
        for code in ReasonCode:
            assert code.value.startswith("gov."), f"{code} not namespaced"


class TestActorInfo:
    def test_defaults(self):
        info = ActorInfo()
        assert info.client_name is None
        assert info.server_name is None

    def test_from_initialize(self):
        info = ActorInfo(
            client_name="test-agent",
            client_version="1.0",
            server_name="echo-server",
            server_version="0.1",
            protocol_version="2024-11-05",
        )
        assert info.client_name == "test-agent"
        assert info.protocol_version == "2024-11-05"

    def test_frozen(self):
        info = ActorInfo(client_name="x")
        try:
            info.client_name = "y"  # type: ignore[misc]
            assert False, "should be frozen"
        except AttributeError:
            pass


class TestToolCallEnvelope:
    def test_basic(self):
        env = ToolCallEnvelope(
            tool_name="echo",
            arguments={"text": "hello"},
            call_id="42",
        )
        assert env.tool_name == "echo"
        assert env.tool_id == "echo"
        assert env.call_id == "42"
        assert env.server_id == "upstream"

    def test_frozen(self):
        env = ToolCallEnvelope(tool_name="x", arguments={}, call_id="1")
        try:
            env.tool_name = "y"  # type: ignore[misc]
            assert False, "should be frozen"
        except AttributeError:
            pass

    def test_tool_id_equals_tool_name(self):
        env = ToolCallEnvelope(tool_name="shell.exec", arguments={}, call_id="1")
        assert env.tool_id == "shell.exec"


class TestPolicyDecision:
    def test_allow(self):
        d = PolicyDecision(
            allow=True,
            reason_code=ReasonCode.POLICY_ALLOW,
            reason_human="Tool not in deny list",
        )
        assert d.allow is True
        assert d.reason_code == ReasonCode.POLICY_ALLOW

    def test_deny(self):
        d = PolicyDecision(
            allow=False,
            reason_code=ReasonCode.POLICY_DENY,
            matched_pattern=r"shell\..*",
        )
        assert d.allow is False
        assert d.matched_pattern == r"shell\..*"


class TestGatewaySession:
    def test_mutable(self):
        s = GatewaySession(session_id="test-id")
        assert not s.initialized
        s.initialized = True
        assert s.initialized

    def test_actor_info_default(self):
        s = GatewaySession(session_id="test-id")
        assert s.actor_info.client_name is None
