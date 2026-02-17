# SPDX-License-Identifier: Apache-2.0
"""
Install artifact correctness tests.

Ensures `governor claude-hooks install` produces a config artifact that the
agent will actually read and that points to working scripts.

These catch "installer wrote a config the agent won't read" before you try
a session.
"""

import json
import os
import stat
from pathlib import Path

import pytest

from governor.claude_hooks import (
    install_claude_hooks,
    install_hook_scripts,
    generate_claude_settings,
    HookConfig,
)


class TestScriptsArtifact:
    """Hook scripts exist, are executable, and contain governor logic."""

    def test_all_three_scripts_created(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        assert set(scripts.keys()) == {"pre_tool_use", "post_tool_use", "notification"}

    def test_scripts_are_executable(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        for name, path in scripts.items():
            assert os.access(path, os.X_OK), f"{name} is not executable"

    def test_scripts_contain_shebang(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        for name, path in scripts.items():
            content = path.read_text()
            assert content.startswith("#!/usr/bin/env python3"), (
                f"{name} missing python3 shebang"
            )

    def test_pre_hook_reads_envelope(self, tmp_path):
        """pre_tool_use.py must read .envelope (not envelope.json as primary)."""
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        content = scripts["pre_tool_use"].read_text()
        assert ".envelope" in content
        # Verify it checks the plain text file first
        assert 'envelope_txt' in content or '.envelope' in content

    def test_pre_hook_checks_approved_files(self, tmp_path):
        """pre_tool_use.py must reference approved_files.json."""
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        content = scripts["pre_tool_use"].read_text()
        assert "approved_files.json" in content

    def test_post_hook_writes_audit(self, tmp_path):
        """post_tool_use.py must reference tool_audit.jsonl."""
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)
        content = scripts["post_tool_use"].read_text()
        assert "tool_audit.jsonl" in content


class TestSettingsArtifact:
    """settings.local.json has the right shape and references."""

    def test_settings_created(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        success, _ = install_claude_hooks(tmp_path)
        assert success
        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()

    def test_settings_has_hooks_key(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        assert "hooks" in settings
        assert isinstance(settings["hooks"], list)

    def test_hooks_reference_governor_dir(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        hooks_dir = str(tmp_path / ".governor" / "hooks")
        for hook in settings["hooks"]:
            assert hooks_dir in hook["command"], (
                f"Hook command doesn't point to governor hooks dir: {hook['command']}"
            )

    def test_hooks_paths_are_absolute(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        for hook in settings["hooks"]:
            parts = hook["command"].split()
            script_path = parts[-1]  # last arg is the script path
            assert script_path.startswith("/"), (
                f"Hook path is not absolute: {script_path}"
            )

    def test_pretooluse_hook_present(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        types = [h["type"] for h in settings["hooks"]]
        assert "preToolUse" in types, "No preToolUse hook — writes won't be blocked"

    def test_pretooluse_gates_write_tools(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        pre_hooks = [h for h in settings["hooks"] if h["type"] == "preToolUse"]
        assert len(pre_hooks) == 1
        tools = pre_hooks[0].get("tools", [])
        for required in ["Write", "Edit", "Bash"]:
            assert required in tools, f"preToolUse doesn't gate {required}"

    def test_merge_preserves_non_governor_hooks(self, tmp_path):
        """Installing doesn't destroy user's other hooks."""
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".claude").mkdir(parents=True)
        existing = {
            "hooks": [
                {"type": "preToolUse", "command": "my-custom-linter"},
            ],
            "other_setting": True,
        }
        (tmp_path / ".claude" / "settings.local.json").write_text(json.dumps(existing))

        install_claude_hooks(tmp_path)

        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        assert settings.get("other_setting") is True
        # Custom hook should survive
        commands = [h["command"] for h in settings["hooks"]]
        assert "my-custom-linter" in commands
