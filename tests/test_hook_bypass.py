"""
Adversarial hook bypass tests.

Tests that the governor's Claude Code hook enforcement can't be easily
circumvented through symlinks, tampering, malformed payloads, unicode
tricks, or other attack vectors.

Reuses HookHarness from tests/agent_integration/test_hook_policy.py.

Run:
    python3 -m pytest tests/test_hook_bypass.py -v
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from governor.claude_hooks import (
    install_hook_scripts,
    create_approved_files_file,
    create_blocked_commands_file,
)
from governor.preflight import (
    check_claude_hooks,
    smoke_test_claude_hook,
)

# Reuse HookHarness from agent_integration tests
sys.path.insert(0, str(Path(__file__).parent / "agent_integration"))
from test_hook_policy import HookHarness


# ── Symlink attacks ──────────────────────────────────────────────────────


class TestSymlinkAttacks:
    """Attempt to bypass enforcement via symbolic links."""

    def test_symlink_approved_files_to_dev_null(self, tmp_path):
        """Replace approved_files.json with symlink to /dev/null → not exit 0.

        /dev/null reads as empty → json.loads("") throws JSONDecodeError.
        The hook crashes (exit 1) rather than cleanly blocking (exit 2).
        Either way, the write is NOT allowed — the important thing is exit != 0.
        """
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=["src/main.py"])

        # Replace the real approved_files.json with symlink to /dev/null
        approved_path = tmp_path / ".governor" / "approved_files.json"
        approved_path.unlink()
        approved_path.symlink_to("/dev/null")

        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/main.py", "content": "x"},
        })
        # Hook crashes or blocks — either way, not exit 0 (allowed)
        assert result.returncode != 0, "Symlink to /dev/null should not allow writes"

    def test_symlink_in_file_path(self, tmp_path):
        """File path containing symlink component → literal match fails → blocked."""
        project = HookHarness.setup_project(
            tmp_path, mode="strict", approved=["src/main.py"],
        )
        # Even if a symlink exists, the hook does literal string matching
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "link/main.py", "content": "x"},
        })
        HookHarness.assert_blocked(result, "not pre-approved")

    def test_symlink_approved_files_to_permissive_list(self, tmp_path):
        """Replace approved_files.json with symlink to a file containing '*'."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])

        # Create a permissive list elsewhere
        permissive = tmp_path / "permissive.json"
        permissive.write_text(json.dumps(["evil.py"]))

        # Replace with symlink
        approved_path = tmp_path / ".governor" / "approved_files.json"
        approved_path.unlink()
        approved_path.symlink_to(str(permissive))

        # The hook follows symlinks when reading the file, so evil.py is now "approved"
        # This test documents this known behavior — the fix is preflight detecting
        # that approved_files.json is a symlink
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py", "content": "x"},
        })
        # This WILL be allowed because the hook reads through the symlink.
        # Document this as a known limitation.
        HookHarness.assert_allowed(result)


# ── Hook script tampering ────────────────────────────────────────────────


class TestHookScriptTampering:
    """Attempt to bypass by modifying the hook scripts themselves."""

    def test_replaced_hook_script_detected_by_preflight(self, tmp_path):
        """If hook script content is changed, preflight smoke test catches it."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])

        # Replace hook with a permissive script
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        hook.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")

        # Now the hook allows everything
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py", "content": "x"},
        })
        # The tampered hook allows it
        assert result.returncode == 0

        # But preflight smoke test detects the problem
        check = smoke_test_claude_hook(project)
        assert check.status == "fail", (
            f"Preflight should detect tampered hook, got: {check.status} — {check.detail}"
        )

    def test_hook_script_permissions_are_executable(self, tmp_path):
        """Installed hook scripts have executable permission."""
        scripts = install_hook_scripts(tmp_path)
        for name, path in scripts.items():
            assert path.exists(), f"Script {name} not created"
            mode = path.stat().st_mode
            assert mode & stat.S_IXUSR, f"{name} not user-executable"

    def test_hook_script_removed_detected_by_preflight(self, tmp_path):
        """Deleting hook scripts → preflight fails."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])

        # Delete the pre_tool_use hook
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        hook.unlink()

        check = check_claude_hooks(project)
        assert check.status == "fail", f"Expected fail, got: {check.status} — {check.detail}"
        assert "pre_tool_use.py" in check.detail

    def test_hook_permissions_removed_detected_by_preflight(self, tmp_path):
        """Hook exists but isn't executable → preflight catches it."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])

        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        hook.chmod(0o644)  # Remove execute bit

        check = check_claude_hooks(project)
        assert check.status in ("fail", "warn"), (
            f"Expected fail/warn for non-executable hook, got: {check.status}"
        )


# ── Unknown tool type ────────────────────────────────────────────────────


class TestUnknownToolType:
    """Unknown tool names should fail-open (exit 0) per current design."""

    def test_unknown_tool_allowed(self, tmp_path):
        """Unknown tool type → exit 0 (allowed, fail-open)."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        result = HookHarness.run_hook(project, {
            "tool_name": "SomeNewTool",
            "tool_input": {"arg": "value"},
        })
        HookHarness.assert_allowed(result)

    def test_read_tool_not_blocked(self, tmp_path):
        """Read tool is never blocked (read-only operation)."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        result = HookHarness.run_hook(project, {
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/passwd"},
        })
        HookHarness.assert_allowed(result)

    def test_empty_tool_name_allowed(self, tmp_path):
        """Empty tool name → fail-open."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        result = HookHarness.run_hook(project, {
            "tool_name": "",
            "tool_input": {},
        })
        HookHarness.assert_allowed(result)


# ── Large and malformed payloads ─────────────────────────────────────────


class TestMalformedPayloads:
    """Hook doesn't crash or hang on unusual inputs."""

    def test_huge_file_path(self, tmp_path):
        """Very long file path doesn't crash the hook."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        huge_path = "a/" * 5000 + "evil.py"
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": huge_path, "content": "x"},
        })
        # Should complete without crash — blocked because not approved
        assert result.returncode in (0, 2), f"Hook crashed: {result.stderr}"

    def test_huge_command(self, tmp_path):
        """Very long command doesn't crash the hook."""
        project = HookHarness.setup_project(
            tmp_path, mode="strict", blocked=["rm -rf"],
        )
        huge_cmd = "echo " + "x" * 100_000
        result = HookHarness.run_hook(project, {
            "tool_name": "Bash",
            "tool_input": {"command": huge_cmd},
        })
        assert result.returncode in (0, 2), f"Hook crashed: {result.stderr}"

    def test_deeply_nested_json(self, tmp_path):
        """Deeply nested tool_input doesn't crash."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        nested = {"a": "b"}
        for _ in range(100):
            nested = {"nested": nested}
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "test.py", "content": json.dumps(nested)},
        })
        assert result.returncode in (0, 2), f"Hook crashed: {result.stderr}"

    def test_empty_stdin(self, tmp_path):
        """Empty stdin → fail-open (exit 0), not crash."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        result = subprocess.run(
            ["python3", str(hook)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project),
        )
        assert result.returncode == 0, f"Empty stdin should fail-open: {result.stderr}"

    def test_invalid_json_stdin(self, tmp_path):
        """Invalid JSON stdin → fail-open (exit 0), not crash."""
        project = HookHarness.setup_project(tmp_path, mode="strict", approved=[])
        hook = project / ".governor" / "hooks" / "pre_tool_use.py"
        result = subprocess.run(
            ["python3", str(hook)],
            input="not json at all {{{",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project),
        )
        assert result.returncode == 0, f"Invalid JSON should fail-open: {result.stderr}"


# ── Unicode tricks ───────────────────────────────────────────────────────


class TestUnicodeTricks:
    """Unicode normalization, null bytes, RTL overrides can't bypass checks."""

    def test_null_byte_in_path(self, tmp_path):
        """Null byte in file path → literal mismatch → blocked."""
        project = HookHarness.setup_project(
            tmp_path, mode="strict", approved=["src/main.py"],
        )
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/main\x00.py", "content": "x"},
        })
        HookHarness.assert_blocked(result, "not pre-approved")

    def test_rtl_override_in_path(self, tmp_path):
        """RTL override character in path → literal mismatch → blocked."""
        project = HookHarness.setup_project(
            tmp_path, mode="strict", approved=["src/main.py"],
        )
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/\u202emain.py", "content": "x"},
        })
        HookHarness.assert_blocked(result, "not pre-approved")

    def test_nfc_vs_nfd_normalization(self, tmp_path):
        """NFC vs NFD normalized filename → literal mismatch → blocked.

        e with acute: NFC = U+00E9, NFD = U+0065 + U+0301
        These look identical visually but are different bytes.
        """
        import unicodedata
        nfc = unicodedata.normalize("NFC", "r\u00e9sum\u00e9.py")
        nfd = unicodedata.normalize("NFD", "r\u00e9sum\u00e9.py")

        project = HookHarness.setup_project(
            tmp_path, mode="strict", approved=[nfc],
        )
        # Write with NFD version — should NOT match NFC in approved list
        result = HookHarness.run_hook(project, {
            "tool_name": "Write",
            "tool_input": {"file_path": nfd, "content": "x"},
        })
        # Literal match: NFD != NFC
        if nfc != nfd:
            HookHarness.assert_blocked(result, "not pre-approved")
        else:
            # On some systems these might be equal
            pass


# ── --no-verify bypass ───────────────────────────────────────────────────


class TestNoVerifyBypass:
    """Document that --no-verify bypasses the git pre-commit hook.

    This is a known limitation of git hooks. The governor's preflight
    command is the mitigation — it doesn't rely on git hooks.
    """

    def test_no_verify_documented_as_bypass(self, tmp_path):
        """git commit --no-verify skips pre-commit hook — known limitation."""
        # This test just documents the fact, doesn't test git behavior
        # The actual mitigation is `governor preflight` which doesn't use git hooks
        assert True, (
            "Known: --no-verify bypasses pre-commit hook. "
            "Mitigation: governor preflight runs checks independently of git."
        )
