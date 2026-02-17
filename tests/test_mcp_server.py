# SPDX-License-Identifier: Apache-2.0
"""Tests for MCP server."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.mcp_server import (
    MCPTool,
    GovernorMCPServer,
    create_mcp_server,
)
from governor.cli import cli


class TestMCPTool:
    """Test MCPTool class."""

    def test_to_dict(self):
        """Converts to MCP tool definition format."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            parameters={
                "arg1": {"type": "string", "required": True},
                "arg2": {"type": "number", "required": False},
            },
            handler=lambda **kwargs: {"success": True},
        )

        result = tool.to_dict()

        assert result["name"] == "test_tool"
        assert result["description"] == "A test tool"
        assert result["inputSchema"]["type"] == "object"
        assert "arg1" in result["inputSchema"]["properties"]
        assert "arg1" in result["inputSchema"]["required"]
        assert "arg2" not in result["inputSchema"]["required"]


class TestGovernorMCPServer:
    """Test GovernorMCPServer class."""

    @pytest.fixture
    def initialized_server(self, tmp_path):
        """Create a server with initialized governor."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "proposals.json").write_text("{}")
        (gov_dir / "facts").mkdir()
        (gov_dir / "facts" / "index.json").write_text("[]")
        (gov_dir / "facts" / "receipts").mkdir()
        (gov_dir / "decisions").mkdir()
        (gov_dir / "decisions" / "index.json").write_text("[]")
        (gov_dir / "config.toml").write_text("""
[envelopes]
default = "strict"
""")

        return GovernorMCPServer(tmp_path)

    def test_list_tools(self, initialized_server):
        """Lists available tools."""
        tools = initialized_server.list_tools()

        assert len(tools) > 0
        tool_names = [t["name"] for t in tools]
        assert "governor_propose" in tool_names
        assert "governor_verify" in tool_names
        assert "governor_apply" in tool_names
        assert "governor_status" in tool_names
        assert "governor_facts" in tool_names
        assert "governor_decisions" in tool_names
        assert "governor_envelope" in tool_names

    def test_call_unknown_tool(self, initialized_server):
        """Returns error for unknown tool."""
        result = initialized_server.call_tool("unknown_tool", {})

        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    def test_propose_tool(self, initialized_server, tmp_path):
        """Propose tool creates a proposal."""
        # Create a test file
        (tmp_path / "test.py").write_text("# test")

        result = initialized_server.call_tool("governor_propose", {
            "claims": [{"type": "file_exists", "path": "test.py"}]
        })

        assert result["success"] is True
        assert "proposal_id" in result
        assert result["state"] == "proposed"

    def test_propose_requires_claims(self, initialized_server):
        """Propose tool requires claims."""
        result = initialized_server.call_tool("governor_propose", {
            "claims": []
        })

        assert result["success"] is False
        assert "no claims" in result["error"].lower()

    def test_verify_tool(self, initialized_server, tmp_path):
        """Verify tool verifies a proposal."""
        # Create file and proposal
        (tmp_path / "test.py").write_text("# test")

        propose_result = initialized_server.call_tool("governor_propose", {
            "claims": [{"type": "file_exists", "path": "test.py"}]
        })
        proposal_id = propose_result["proposal_id"]

        result = initialized_server.call_tool("governor_verify", {
            "proposal_id": proposal_id
        })

        assert result["success"] is True
        assert result["state"] == "verified"

    def test_verify_not_found(self, initialized_server):
        """Verify returns error for unknown proposal."""
        result = initialized_server.call_tool("governor_verify", {
            "proposal_id": "not-a-real-id"
        })

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_apply_tool(self, initialized_server, tmp_path):
        """Apply tool applies a verified proposal."""
        # Create file, propose, and verify
        (tmp_path / "test.py").write_text("# test")

        propose_result = initialized_server.call_tool("governor_propose", {
            "claims": [{"type": "file_exists", "path": "test.py"}]
        })
        proposal_id = propose_result["proposal_id"]

        initialized_server.call_tool("governor_verify", {"proposal_id": proposal_id})

        result = initialized_server.call_tool("governor_apply", {
            "proposal_id": proposal_id
        })

        assert result["success"] is True
        assert result["state"] == "applied"

    def test_apply_requires_verified(self, initialized_server, tmp_path):
        """Apply requires proposal to be verified."""
        (tmp_path / "test.py").write_text("# test")

        propose_result = initialized_server.call_tool("governor_propose", {
            "claims": [{"type": "file_exists", "path": "test.py"}]
        })
        proposal_id = propose_result["proposal_id"]

        result = initialized_server.call_tool("governor_apply", {
            "proposal_id": proposal_id
        })

        assert result["success"] is False
        assert "verified" in result["error"].lower()

    def test_status_tool(self, initialized_server, tmp_path):
        """Status tool returns proposal status."""
        (tmp_path / "test.py").write_text("# test")

        propose_result = initialized_server.call_tool("governor_propose", {
            "claims": [{"type": "file_exists", "path": "test.py"}]
        })
        proposal_id = propose_result["proposal_id"]

        result = initialized_server.call_tool("governor_status", {
            "proposal_id": proposal_id
        })

        assert result["success"] is True
        assert result["proposal"]["state"] == "proposed"

    def test_status_summary(self, initialized_server):
        """Status without ID returns summary."""
        result = initialized_server.call_tool("governor_status", {})

        assert result["success"] is True
        assert "total" in result

    def test_facts_tool(self, initialized_server):
        """Facts tool returns facts."""
        result = initialized_server.call_tool("governor_facts", {})

        assert result["success"] is True
        assert "facts" in result

    def test_decisions_tool(self, initialized_server):
        """Decisions tool returns decisions."""
        result = initialized_server.call_tool("governor_decisions", {})

        assert result["success"] is True
        assert "decisions" in result

    def test_envelope_get(self, initialized_server):
        """Envelope tool returns current envelope."""
        result = initialized_server.call_tool("governor_envelope", {})

        assert result["success"] is True
        assert "mode" in result

    def test_envelope_set(self, initialized_server):
        """Envelope tool can set mode."""
        result = initialized_server.call_tool("governor_envelope", {
            "mode": "exploratory"
        })

        assert result["success"] is True
        assert result["mode"] == "exploratory"

        # Verify it changed
        result2 = initialized_server.call_tool("governor_envelope", {})
        assert result2["mode"] == "exploratory"


class TestCreateMCPServer:
    """Test create_mcp_server function."""

    def test_creates_server(self, tmp_path):
        """Creates a server instance."""
        server = create_mcp_server(tmp_path)

        assert isinstance(server, GovernorMCPServer)
        assert server.root == tmp_path


class TestMCPCLI:
    """Test MCP CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_mcp_tools_command(self, runner, tmp_path):
        """mcp tools lists available tools."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["mcp", "tools"])

            assert result.exit_code == 0
            assert "governor_propose" in result.output
            assert "governor_verify" in result.output

    def test_mcp_call_command(self, runner, tmp_path):
        """mcp call invokes a tool."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["mcp", "call", "governor_status"])

            assert result.exit_code == 0
            # Should have JSON output
            data = json.loads(result.output)
            assert data["success"] is True

    def test_mcp_call_with_args(self, runner, tmp_path):
        """mcp call passes arguments."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("test.py").write_text("# test")

            result = runner.invoke(cli, [
                "mcp", "call", "governor_propose",
                "-a", 'claims=[{"type":"file_exists","path":"test.py"}]'
            ])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["success"] is True
            assert "proposal_id" in data

    def test_mcp_call_unknown_tool(self, runner, tmp_path):
        """mcp call with unknown tool fails."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["mcp", "call", "unknown_tool"])

            assert result.exit_code == 1


class TestMCPFullWorkflow:
    """Test full MCP workflow."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_propose_verify_apply_via_mcp(self, runner, tmp_path):
        """Full workflow via MCP calls."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("app.py").write_text("# application code")

            # Propose
            result = runner.invoke(cli, [
                "mcp", "call", "governor_propose",
                "-a", 'claims=[{"type":"file_exists","path":"app.py"}]'
            ])
            data = json.loads(result.output)
            assert data["success"] is True
            proposal_id = data["proposal_id"]

            # Verify
            result = runner.invoke(cli, [
                "mcp", "call", "governor_verify",
                "-a", f'proposal_id={proposal_id}'
            ])
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["state"] == "verified"

            # Apply
            result = runner.invoke(cli, [
                "mcp", "call", "governor_apply",
                "-a", f'proposal_id={proposal_id}'
            ])
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["state"] == "applied"

            # Check status
            result = runner.invoke(cli, [
                "mcp", "call", "governor_status",
                "-a", f'proposal_id={proposal_id}'
            ])
            data = json.loads(result.output)
            assert data["proposal"]["state"] == "applied"

    def test_decision_workflow_via_mcp(self, runner, tmp_path):
        """Decision workflow via MCP."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose decision
            result = runner.invoke(cli, [
                "mcp", "call", "governor_propose",
                "-a", 'claims=[{"type":"decision","topic":"framework","choice":"fastapi"}]'
            ])
            data = json.loads(result.output)
            proposal_id = data["proposal_id"]

            # Verify and apply
            runner.invoke(cli, [
                "mcp", "call", "governor_verify",
                "-a", f'proposal_id={proposal_id}'
            ])
            runner.invoke(cli, [
                "mcp", "call", "governor_apply",
                "-a", f'proposal_id={proposal_id}'
            ])

            # Check decisions
            result = runner.invoke(cli, ["mcp", "call", "governor_decisions"])
            data = json.loads(result.output)
            assert data["count"] == 1
            assert data["decisions"][0]["topic"] == "framework"
            assert data["decisions"][0]["choice"] == "fastapi"
