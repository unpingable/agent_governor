"""Tests for Claude Code hooks integration."""

import json
import pytest
from pathlib import Path

from governor.claude_hooks import (
    HookConfig,
    install_hook_scripts,
    generate_claude_settings,
    install_claude_hooks,
    uninstall_claude_hooks,
    get_hook_status,
    get_hooks_dir,
    get_claude_settings_path,
    create_blocked_commands_file,
    create_approved_files_file,
)


class TestHookConfig:
    """Tests for HookConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = HookConfig()

        assert config.pre_tool_use is True
        assert config.post_tool_use is True
        assert config.notification is True
        assert config.timeout_ms == 5000

    def test_custom_config(self):
        """Test custom configuration."""
        config = HookConfig(
            pre_tool_use=False,
            timeout_ms=10000,
        )

        assert config.pre_tool_use is False
        assert config.timeout_ms == 10000

    def test_serialization(self):
        """Test config serialization."""
        config = HookConfig(
            pre_tool_use=False,
            pre_tool_filter=["Write"],
        )

        data = config.to_dict()
        restored = HookConfig.from_dict(data)

        assert restored.pre_tool_use is False
        assert restored.pre_tool_filter == ["Write"]


class TestInstallHookScripts:
    """Tests for hook script installation."""

    def test_install_scripts(self, tmp_path):
        """Test installing hook scripts."""
        scripts = install_hook_scripts(tmp_path)

        assert "pre_tool_use" in scripts
        assert "post_tool_use" in scripts
        assert "notification" in scripts

        # Check files exist
        hooks_dir = get_hooks_dir(tmp_path)
        assert (hooks_dir / "pre_tool_use.py").exists()
        assert (hooks_dir / "post_tool_use.py").exists()
        assert (hooks_dir / "notification.py").exists()

    def test_scripts_are_executable(self, tmp_path):
        """Test that scripts are executable."""
        install_hook_scripts(tmp_path)
        hooks_dir = get_hooks_dir(tmp_path)

        for script in hooks_dir.glob("*.py"):
            # Check executable bit
            assert script.stat().st_mode & 0o111 != 0


class TestGenerateClaudeSettings:
    """Tests for Claude settings generation."""

    def test_generate_all_hooks(self, tmp_path):
        """Test generating settings with all hooks."""
        install_hook_scripts(tmp_path)
        settings = generate_claude_settings(tmp_path)

        assert "hooks" in settings
        assert len(settings["hooks"]) == 3

        hook_types = {h["type"] for h in settings["hooks"]}
        assert "preToolUse" in hook_types
        assert "postToolUse" in hook_types
        assert "notification" in hook_types

    def test_generate_partial_hooks(self, tmp_path):
        """Test generating settings with partial hooks."""
        install_hook_scripts(tmp_path)
        config = HookConfig(pre_tool_use=True, post_tool_use=False, notification=False)
        settings = generate_claude_settings(tmp_path, config)

        assert len(settings["hooks"]) == 1
        assert settings["hooks"][0]["type"] == "preToolUse"

    def test_hook_includes_tool_filter(self, tmp_path):
        """Test that hook includes tool filter."""
        install_hook_scripts(tmp_path)
        config = HookConfig(pre_tool_filter=["Write", "Edit"])
        settings = generate_claude_settings(tmp_path, config)

        pre_hook = next(h for h in settings["hooks"] if h["type"] == "preToolUse")
        assert pre_hook["tools"] == ["Write", "Edit"]

    def test_hook_includes_timeout(self, tmp_path):
        """Test that hook includes timeout."""
        install_hook_scripts(tmp_path)
        config = HookConfig(timeout_ms=10000)
        settings = generate_claude_settings(tmp_path, config)

        for hook in settings["hooks"]:
            assert hook["timeout"] == 10000


class TestInstallClaudeHooks:
    """Tests for full hook installation."""

    def test_install_hooks(self, tmp_path):
        """Test full hook installation."""
        success, message = install_claude_hooks(tmp_path)

        assert success is True
        assert "installed" in message.lower()

        # Check scripts exist
        hooks_dir = get_hooks_dir(tmp_path)
        assert hooks_dir.exists()
        assert len(list(hooks_dir.glob("*.py"))) == 3

        # Check Claude settings exist
        settings_path = get_claude_settings_path(tmp_path)
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings
        assert len(settings["hooks"]) == 3

    def test_install_with_custom_config(self, tmp_path):
        """Test installation with custom config."""
        config = HookConfig(post_tool_use=False)
        success, _ = install_claude_hooks(tmp_path, config)

        assert success is True

        settings_path = get_claude_settings_path(tmp_path)
        settings = json.loads(settings_path.read_text())

        hook_types = {h["type"] for h in settings["hooks"]}
        assert "postToolUse" not in hook_types

    def test_install_merges_existing_settings(self, tmp_path):
        """Test that installation merges with existing settings."""
        # Create existing settings
        settings_path = get_claude_settings_path(tmp_path)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({
            "someOtherSetting": "value",
            "hooks": [
                {"type": "custom", "command": "custom-hook"}
            ]
        }))

        success, _ = install_claude_hooks(tmp_path, merge=True)

        assert success is True

        settings = json.loads(settings_path.read_text())
        assert settings["someOtherSetting"] == "value"
        # Should have custom hook + governor hooks
        assert len(settings["hooks"]) == 4


class TestUninstallClaudeHooks:
    """Tests for hook uninstallation."""

    def test_uninstall_hooks(self, tmp_path):
        """Test hook uninstallation."""
        # First install
        install_claude_hooks(tmp_path)

        # Then uninstall
        success, message = uninstall_claude_hooks(tmp_path)

        assert success is True

        # Check scripts removed
        hooks_dir = get_hooks_dir(tmp_path)
        assert len(list(hooks_dir.glob("*.py"))) == 0

    def test_uninstall_preserves_other_hooks(self, tmp_path):
        """Test that uninstall preserves other hooks in settings."""
        # Create settings with other hooks
        settings_path = get_claude_settings_path(tmp_path)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({
            "hooks": [
                {"type": "custom", "command": "custom-hook"}
            ]
        }))

        # Install governor hooks
        install_claude_hooks(tmp_path)

        # Uninstall
        uninstall_claude_hooks(tmp_path)

        # Check custom hook preserved
        settings = json.loads(settings_path.read_text())
        assert len(settings["hooks"]) == 1
        assert settings["hooks"][0]["type"] == "custom"


class TestGetHookStatus:
    """Tests for hook status checking."""

    def test_status_not_installed(self, tmp_path):
        """Test status when hooks not installed."""
        status = get_hook_status(tmp_path)

        assert status["hooks_dir_exists"] is False
        assert status["scripts_installed"] == []
        assert status["claude_settings_exists"] is False
        assert status["hooks_configured"] == []

    def test_status_installed(self, tmp_path):
        """Test status when hooks installed."""
        install_claude_hooks(tmp_path)

        status = get_hook_status(tmp_path)

        assert status["hooks_dir_exists"] is True
        assert len(status["scripts_installed"]) == 3
        assert status["claude_settings_exists"] is True
        assert len(status["hooks_configured"]) == 3


class TestBlockedCommands:
    """Tests for blocked commands file."""

    def test_create_blocked_commands(self, tmp_path):
        """Test creating blocked commands file."""
        blocked_file = create_blocked_commands_file(tmp_path)

        assert blocked_file.exists()

        blocked = json.loads(blocked_file.read_text())
        assert isinstance(blocked, list)
        assert "rm -rf /" in blocked

    def test_create_custom_blocked_commands(self, tmp_path):
        """Test creating custom blocked commands."""
        patterns = ["dangerous_cmd", "bad_script"]
        blocked_file = create_blocked_commands_file(tmp_path, patterns)

        blocked = json.loads(blocked_file.read_text())
        assert blocked == patterns


class TestApprovedFiles:
    """Tests for approved files file."""

    def test_create_approved_files(self, tmp_path):
        """Test creating approved files file."""
        approved_file = create_approved_files_file(tmp_path)

        assert approved_file.exists()

        approved = json.loads(approved_file.read_text())
        assert isinstance(approved, list)
        assert len(approved) == 0

    def test_create_with_files(self, tmp_path):
        """Test creating approved files with list."""
        files = ["src/main.py", "README.md"]
        approved_file = create_approved_files_file(tmp_path, files)

        approved = json.loads(approved_file.read_text())
        assert approved == files


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_hooks_dir(self, tmp_path):
        """Test get_hooks_dir."""
        hooks_dir = get_hooks_dir(tmp_path)
        assert hooks_dir == tmp_path / ".governor" / "hooks"

    def test_get_claude_settings_path(self, tmp_path):
        """Test get_claude_settings_path."""
        settings_path = get_claude_settings_path(tmp_path)
        assert settings_path == tmp_path / ".claude" / "settings.local.json"
