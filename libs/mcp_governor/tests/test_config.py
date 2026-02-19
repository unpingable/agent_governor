# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.config."""

import pytest

from mcp_governor.config import GatewayConfig


class TestDefaults:
    def test_all_defaults(self):
        cfg = GatewayConfig()
        assert cfg.agent_id == "local-dev"
        assert cfg.auth_context == "stdio"
        assert cfg.receipt_path == "./receipts/gateway.jsonl"
        assert cfg.deployment_id == "local"
        assert cfg.upstream_command == []
        assert cfg.default_policy == "allow"
        assert cfg.deny_tools == []

    def test_invalid_default_policy(self):
        with pytest.raises(ValueError, match="default_policy"):
            GatewayConfig(default_policy="invalid")


class TestFromTomlString:
    def test_minimal(self):
        cfg = GatewayConfig.from_toml_string("""
[upstream]
command = ["python", "-m", "echo_server"]
""")
        assert cfg.upstream_command == ["python", "-m", "echo_server"]
        assert cfg.agent_id == "local-dev"  # default

    def test_full(self):
        cfg = GatewayConfig.from_toml_string("""
[gateway]
agent_id = "test-agent"
auth_context = "stdio"
receipt_path = "/tmp/receipts.jsonl"
deployment_id = "ci"

[upstream]
command = ["node", "server.js"]

[policy]
default_policy = "deny"
deny_tools = ["shell\\\\..*", "dangerous\\\\..*"]
""")
        assert cfg.agent_id == "test-agent"
        assert cfg.deployment_id == "ci"
        assert cfg.upstream_command == ["node", "server.js"]
        assert cfg.default_policy == "deny"
        assert len(cfg.deny_tools) == 2

    def test_allow_warn_policy(self):
        cfg = GatewayConfig.from_toml_string("""
[policy]
default_policy = "allow-warn"
""")
        assert cfg.default_policy == "allow-warn"

    def test_invalid_policy_in_toml(self):
        with pytest.raises(ValueError, match="default_policy"):
            GatewayConfig.from_toml_string("""
[policy]
default_policy = "yolo"
""")

    def test_string_command_becomes_list(self):
        cfg = GatewayConfig.from_toml_string("""
[upstream]
command = "echo_server"
""")
        assert cfg.upstream_command == ["echo_server"]

    def test_empty_sections(self):
        cfg = GatewayConfig.from_toml_string("")
        assert cfg.agent_id == "local-dev"

    def test_deny_tools_must_be_list(self):
        with pytest.raises(ValueError, match="deny_tools must be a list"):
            GatewayConfig.from_toml_string("""
[policy]
deny_tools = "not_a_list"
""")


class TestFromTomlFile:
    def test_load_file(self, tmp_path):
        toml_file = tmp_path / "test.toml"
        toml_file.write_text("""
[gateway]
agent_id = "file-test"

[upstream]
command = ["python", "server.py"]
""")
        cfg = GatewayConfig.from_toml(toml_file)
        assert cfg.agent_id == "file-test"
        assert cfg.upstream_command == ["python", "server.py"]
