"""Tests for governor preflight checks."""

import json
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from governor.preflight import (
    PreflightCheck,
    PreflightResult,
    check_governor_dir,
    check_envelope,
    check_approved_files,
    check_claude_hooks,
    smoke_test_claude_hook,
    check_git_hook,
    check_restart_advisory,
    check_codex_config,
    detect_agent,
    run_preflight,
    _compute_overall,
)


# ── PreflightCheck / PreflightResult dataclass tests ───────────────────────


class TestPreflightDataclasses:
    def test_check_to_dict(self):
        c = PreflightCheck(name="test", status="pass", detail="ok")
        d = c.to_dict()
        assert d == {"name": "test", "status": "pass", "detail": "ok"}

    def test_check_to_dict_with_fix(self):
        c = PreflightCheck(name="test", status="fail", detail="bad", fix="do X")
        d = c.to_dict()
        assert d["fix"] == "do X"

    def test_result_to_dict(self):
        r = PreflightResult(
            checks=[PreflightCheck(name="a", status="pass", detail="ok")],
            overall="pass",
        )
        d = r.to_dict()
        assert d["overall"] == "pass"
        assert len(d["checks"]) == 1

    def test_compute_overall_all_pass(self):
        checks = [
            PreflightCheck(name="a", status="pass", detail=""),
            PreflightCheck(name="b", status="pass", detail=""),
        ]
        assert _compute_overall(checks) == "pass"

    def test_compute_overall_warn(self):
        checks = [
            PreflightCheck(name="a", status="pass", detail=""),
            PreflightCheck(name="b", status="warn", detail=""),
        ]
        assert _compute_overall(checks) == "warn"

    def test_compute_overall_fail_trumps_warn(self):
        checks = [
            PreflightCheck(name="a", status="warn", detail=""),
            PreflightCheck(name="b", status="fail", detail=""),
        ]
        assert _compute_overall(checks) == "fail"


# ── check_governor_dir ─────────────────────────────────────────────────────


class TestCheckGovernorDir:
    def test_missing(self, tmp_path):
        result = check_governor_dir(tmp_path)
        assert result.status == "fail"
        assert "does not exist" in result.detail
        assert result.fix == "governor init"

    def test_exists_writable(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        result = check_governor_dir(tmp_path)
        assert result.status == "pass"

    def test_not_a_directory(self, tmp_path):
        (tmp_path / ".governor").write_text("oops")
        result = check_governor_dir(tmp_path)
        assert result.status == "fail"
        assert "not a directory" in result.detail

    def test_read_only(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        gov_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = check_governor_dir(tmp_path)
            assert result.status == "fail"
            assert "not writable" in result.detail
        finally:
            gov_dir.chmod(stat.S_IRWXU)


# ── check_envelope ─────────────────────────────────────────────────────────


class TestCheckEnvelope:
    def test_strict(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / ".envelope").write_text("strict")
        result = check_envelope(tmp_path)
        assert result.status == "pass"
        assert "strict" in result.detail

    def test_exploratory_warn(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / ".envelope").write_text("exploratory")
        result = check_envelope(tmp_path)
        assert result.status == "warn"

    def test_exploratory_fail_when_strict_required(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / ".envelope").write_text("exploratory")
        result = check_envelope(tmp_path, require_strict=True)
        assert result.status == "fail"

    def test_missing(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        result = check_envelope(tmp_path)
        assert result.status == "fail"
        assert "No envelope" in result.detail

    def test_legacy_envelope_json(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "envelope.json").write_text('{"mode": "strict"}')
        result = check_envelope(tmp_path)
        assert result.status == "pass"

    def test_empty_envelope(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / ".envelope").write_text("")
        result = check_envelope(tmp_path)
        assert result.status == "fail"
        assert "empty" in result.detail


# ── check_approved_files ───────────────────────────────────────────────────


class TestCheckApprovedFiles:
    def test_present_with_files(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "approved_files.json").write_text('["a.py", "b.py"]')
        result = check_approved_files(tmp_path)
        assert result.status == "pass"
        assert "2 files" in result.detail

    def test_missing(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        result = check_approved_files(tmp_path)
        assert result.status == "warn"

    def test_empty_list(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "approved_files.json").write_text("[]")
        result = check_approved_files(tmp_path)
        assert result.status == "warn"
        assert "empty" in result.detail

    def test_invalid_json(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "approved_files.json").write_text("{bad")
        result = check_approved_files(tmp_path)
        assert result.status == "warn"
        assert "unreadable" in result.detail


# ── check_claude_hooks ─────────────────────────────────────────────────────


class TestCheckClaudeHooks:
    def _setup_hooks(self, tmp_path, scripts=True, settings=True, pre_hook=True):
        """Helper to set up hook infrastructure."""
        hooks_dir = tmp_path / ".governor" / "hooks"
        hooks_dir.mkdir(parents=True)

        if scripts:
            for name in ["pre_tool_use.py", "post_tool_use.py", "notification.py"]:
                script = hooks_dir / name
                script.write_text("#!/usr/bin/env python3\npass")
                script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        if settings:
            settings_dir = tmp_path / ".claude"
            settings_dir.mkdir(parents=True, exist_ok=True)
            hooks_list = []
            if pre_hook:
                hooks_list.append({
                    "type": "preToolUse",
                    "command": f"python3 {hooks_dir / 'pre_tool_use.py'}",
                    "timeout": 5000,
                })
            hooks_list.append({
                "type": "postToolUse",
                "command": f"python3 {hooks_dir / 'post_tool_use.py'}",
                "timeout": 5000,
            })
            (settings_dir / "settings.local.json").write_text(
                json.dumps({"hooks": hooks_list})
            )

    def test_fully_installed(self, tmp_path):
        self._setup_hooks(tmp_path)
        result = check_claude_hooks(tmp_path)
        assert result.status == "pass"

    def test_missing_scripts(self, tmp_path):
        self._setup_hooks(tmp_path, scripts=False)
        result = check_claude_hooks(tmp_path)
        assert result.status == "fail"
        assert "Missing hook scripts" in result.detail

    def test_missing_settings(self, tmp_path):
        self._setup_hooks(tmp_path, settings=False)
        result = check_claude_hooks(tmp_path)
        assert result.status == "fail"
        assert "settings.local.json missing" in result.detail

    def test_no_pre_hook_in_settings(self, tmp_path):
        self._setup_hooks(tmp_path, pre_hook=False)
        result = check_claude_hooks(tmp_path)
        assert result.status == "warn"
        assert "No preToolUse" in result.detail

    def test_scripts_not_executable(self, tmp_path):
        hooks_dir = tmp_path / ".governor" / "hooks"
        hooks_dir.mkdir(parents=True)
        for name in ["pre_tool_use.py", "post_tool_use.py", "notification.py"]:
            script = hooks_dir / name
            script.write_text("pass")
            script.chmod(stat.S_IRUSR | stat.S_IWUSR)  # no exec
        result = check_claude_hooks(tmp_path)
        assert result.status == "fail"
        assert "not executable" in result.detail


# ── smoke_test_claude_hook ─────────────────────────────────────────────────


class TestSmokeTestClaudeHook:
    def test_script_missing(self, tmp_path):
        (tmp_path / ".governor" / "hooks").mkdir(parents=True)
        result = smoke_test_claude_hook(tmp_path)
        assert result.status == "fail"
        assert "not found" in result.detail

    def test_blocks_unapproved_write(self, tmp_path):
        """Full integration: install real hooks, set strict, verify block."""
        from governor.claude_hooks import install_hook_scripts, create_approved_files_file

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Set strict envelope
        (gov_dir / ".envelope").write_text("strict")
        # Create empty approved files (nothing approved)
        create_approved_files_file(tmp_path, [])
        # Install real hook scripts
        install_hook_scripts(tmp_path)

        result = smoke_test_claude_hook(tmp_path)
        assert result.status == "pass"
        assert "exit=2" in result.detail

    def test_allows_in_exploratory(self, tmp_path):
        """In exploratory mode, hook allows unapproved writes → smoke test fails."""
        from governor.claude_hooks import install_hook_scripts, create_approved_files_file

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("exploratory")
        create_approved_files_file(tmp_path, [])
        install_hook_scripts(tmp_path)

        result = smoke_test_claude_hook(tmp_path)
        # In exploratory mode, hook exits 0 (allow), so smoke test reports fail
        assert result.status == "fail"
        assert "expected 2" in result.detail

    def test_timeout(self, tmp_path):
        """Hook script that hangs should be caught."""
        hooks_dir = tmp_path / ".governor" / "hooks"
        hooks_dir.mkdir(parents=True)
        script = hooks_dir / "pre_tool_use.py"
        script.write_text("#!/usr/bin/env python3\nimport time; time.sleep(999)")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        with patch("governor.preflight.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)
            result = smoke_test_claude_hook(tmp_path)
            assert result.status == "fail"
            assert "timed out" in result.detail


# ── check_git_hook ─────────────────────────────────────────────────────────


class TestCheckGitHook:
    def test_installed(self, tmp_path):
        hook_dir = tmp_path / ".git" / "hooks"
        hook_dir.mkdir(parents=True)
        hook = hook_dir / "pre-commit"
        hook.write_text("#!/bin/sh\ngovernor hook pre-commit")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        result = check_git_hook(tmp_path)
        assert result.status == "pass"

    def test_missing(self, tmp_path):
        result = check_git_hook(tmp_path)
        assert result.status == "warn"
        assert "not installed" in result.detail

    def test_not_executable(self, tmp_path):
        hook_dir = tmp_path / ".git" / "hooks"
        hook_dir.mkdir(parents=True)
        hook = hook_dir / "pre-commit"
        hook.write_text("#!/bin/sh\ngovernor hook pre-commit")
        hook.chmod(stat.S_IRUSR)
        result = check_git_hook(tmp_path)
        assert result.status == "warn"
        assert "not executable" in result.detail

    def test_no_governor_reference(self, tmp_path):
        hook_dir = tmp_path / ".git" / "hooks"
        hook_dir.mkdir(parents=True)
        hook = hook_dir / "pre-commit"
        hook.write_text("#!/bin/sh\necho hello")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        result = check_git_hook(tmp_path)
        assert result.status == "warn"
        assert "doesn't reference governor" in result.detail


# ── check_restart_advisory ─────────────────────────────────────────────────


class TestCheckRestartAdvisory:
    def test_no_settings(self, tmp_path):
        result = check_restart_advisory(tmp_path)
        assert result.status == "pass"

    def test_no_activity(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        (tmp_path / ".governor").mkdir()
        result = check_restart_advisory(tmp_path)
        assert result.status == "warn"
        assert "not be loaded" in result.detail

    def test_settings_newer(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".claude").mkdir()
        # Create notifications first (older)
        notif = tmp_path / ".governor" / "notifications.jsonl"
        notif.write_text('{"event":"start"}\n')
        # Then update settings (newer)
        import time
        time.sleep(0.05)
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        result = check_restart_advisory(tmp_path)
        assert result.status == "warn"
        assert "stale" in result.detail or "changed after" in result.detail

    def test_settings_older(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".claude").mkdir()
        # Create settings first (older)
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        import time
        time.sleep(0.05)
        # Then notifications (newer)
        notif = tmp_path / ".governor" / "notifications.jsonl"
        notif.write_text('{"event":"start"}\n')
        result = check_restart_advisory(tmp_path)
        assert result.status == "pass"

    def test_prefers_invocations_over_notifications(self, tmp_path):
        """hook_invocations.jsonl is preferred over notifications.jsonl."""
        import time
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".claude").mkdir()
        # Old notifications (would trigger warn)
        (tmp_path / ".governor" / "notifications.jsonl").write_text("{}\n")
        time.sleep(0.05)
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        time.sleep(0.05)
        # Fresh invocations (should override to pass)
        (tmp_path / ".governor" / "hook_invocations.jsonl").write_text("{}\n")
        result = check_restart_advisory(tmp_path)
        assert result.status == "pass"

    def test_invocations_stale(self, tmp_path):
        """Settings newer than invocations → warn."""
        import time
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".governor" / "hook_invocations.jsonl").write_text("{}\n")
        time.sleep(0.05)
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        result = check_restart_advisory(tmp_path)
        assert result.status == "warn"
        assert "stale" in result.detail


# ── detect_agent ───────────────────────────────────────────────────────────


class TestDetectAgent:
    def test_claude(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        assert detect_agent(tmp_path) == "claude"

    def test_codex_dir(self, tmp_path):
        (tmp_path / ".codex").mkdir()
        assert detect_agent(tmp_path) == "codex"

    def test_codex_config(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "codex_hooks.json").write_text("{}")
        assert detect_agent(tmp_path) == "codex"

    def test_none(self, tmp_path):
        assert detect_agent(tmp_path) is None

    def test_claude_takes_precedence(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")
        (tmp_path / ".codex").mkdir()
        assert detect_agent(tmp_path) == "claude"


# ── run_preflight ──────────────────────────────────────────────────────────


class TestRunPreflight:
    def test_all_pass(self, tmp_path):
        """Minimal setup for all-pass preflight (no agent)."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        (gov_dir / "approved_files.json").write_text('["a.py"]')
        # Git hook
        hook_dir = tmp_path / ".git" / "hooks"
        hook_dir.mkdir(parents=True)
        hook = hook_dir / "pre-commit"
        hook.write_text("#!/bin/sh\ngovernor hook pre-commit")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

        result = run_preflight(tmp_path)
        assert result.overall == "pass"

    def test_all_fail(self, tmp_path):
        """Empty directory: governor dir missing → fail."""
        result = run_preflight(tmp_path)
        assert result.overall == "fail"

    def test_strict_flag(self, tmp_path):
        """--strict flag causes exploratory envelope to fail."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("exploratory")
        (gov_dir / "approved_files.json").write_text("[]")

        result = run_preflight(tmp_path, strict=True)
        assert result.overall == "fail"
        envelope_check = [c for c in result.checks if c.name == "envelope"][0]
        assert envelope_check.status == "fail"

    def test_agent_claude(self, tmp_path):
        """With --agent claude, runs claude-specific checks."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        (gov_dir / "approved_files.json").write_text("[]")

        result = run_preflight(tmp_path, agent="claude")
        check_names = [c.name for c in result.checks]
        assert "claude_hooks" in check_names

    def test_agent_codex(self, tmp_path):
        """With --agent codex, runs codex-specific checks."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        (gov_dir / "approved_files.json").write_text("[]")

        result = run_preflight(tmp_path, agent="codex")
        check_names = [c.name for c in result.checks]
        assert "codex_hooks" in check_names

    def test_auto_detect_claude(self, tmp_path):
        """Auto-detects Claude when settings.local.json exists."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text("{}")

        result = run_preflight(tmp_path)
        check_names = [c.name for c in result.checks]
        assert "claude_hooks" in check_names

    def test_mixed_results(self, tmp_path):
        """Some pass, some warn → overall warn."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        # No approved_files → warn
        # No git hook → warn

        result = run_preflight(tmp_path)
        assert result.overall == "warn"

    def test_json_roundtrip(self, tmp_path):
        """Result serializes to valid JSON."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        result = run_preflight(tmp_path)
        d = result.to_dict()
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["overall"] == result.overall
        assert len(parsed["checks"]) == len(result.checks)


# ── Hook policy tests (template correctness) ──────────────────────────────
# These verify the actual hook script logic reads from the right source of
# truth and produces the right exit codes.


class TestHookPolicyEnforcement:
    """Tests that prove the pre_tool_use.py template correctly enforces policy."""

    def _run_hook(self, project_dir, payload):
        """Run the installed hook script with a payload."""
        hook = project_dir / ".governor" / "hooks" / "pre_tool_use.py"
        return subprocess.run(
            ["python3", str(hook)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_dir),
        )

    def _setup(self, tmp_path, mode="strict", approved=None):
        """Set up a governed project with hooks."""
        from governor.claude_hooks import install_hook_scripts, create_approved_files_file
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir(exist_ok=True)
        (gov_dir / ".envelope").write_text(mode)
        create_approved_files_file(tmp_path, approved or [])
        install_hook_scripts(tmp_path)

    def test_strict_blocks_unapproved_write(self, tmp_path):
        """Strict mode + unapproved file → exit 2 + block decision."""
        self._setup(tmp_path, mode="strict", approved=[])
        result = self._run_hook(tmp_path, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_strict_allows_approved_write(self, tmp_path):
        """Strict mode + approved file → exit 0."""
        self._setup(tmp_path, mode="strict", approved=["safe.py"])
        result = self._run_hook(tmp_path, {
            "tool_name": "Write",
            "tool_input": {"file_path": "safe.py"},
        })
        assert result.returncode == 0

    def test_exploratory_allows_unapproved(self, tmp_path):
        """Exploratory mode → exit 0 even for unapproved files."""
        self._setup(tmp_path, mode="exploratory", approved=[])
        result = self._run_hook(tmp_path, {
            "tool_name": "Write",
            "tool_input": {"file_path": "anything.py"},
        })
        assert result.returncode == 0

    def test_reads_envelope_not_envelope_json(self, tmp_path):
        """Hook reads .envelope (plain text), not envelope.json."""
        self._setup(tmp_path, mode="strict", approved=[])
        # Create a contradictory envelope.json
        (tmp_path / ".governor" / "envelope.json").write_text('{"mode": "exploratory"}')
        result = self._run_hook(tmp_path, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py"},
        })
        # .envelope says strict → should block
        assert result.returncode == 2

    def test_no_envelope_defaults_strict(self, tmp_path):
        """No envelope file at all → defaults to strict."""
        from governor.claude_hooks import install_hook_scripts, create_approved_files_file
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        create_approved_files_file(tmp_path, [])
        install_hook_scripts(tmp_path)
        # No .envelope file

        result = self._run_hook(tmp_path, {
            "tool_name": "Write",
            "tool_input": {"file_path": "evil.py"},
        })
        assert result.returncode == 2

    def test_edit_tool_also_gated(self, tmp_path):
        """Edit tool is also subject to approved file checks."""
        self._setup(tmp_path, mode="strict", approved=[])
        result = self._run_hook(tmp_path, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "evil.py"},
        })
        assert result.returncode == 2

    def test_blocked_command(self, tmp_path):
        """Blocked command patterns are enforced."""
        from governor.claude_hooks import install_hook_scripts, create_blocked_commands_file
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        create_blocked_commands_file(tmp_path, ["rm -rf"])
        install_hook_scripts(tmp_path)

        result = self._run_hook(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /important"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_allowed_command(self, tmp_path):
        """Non-blocked commands are allowed."""
        from governor.claude_hooks import install_hook_scripts, create_blocked_commands_file
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")
        create_blocked_commands_file(tmp_path, ["rm -rf"])
        install_hook_scripts(tmp_path)

        result = self._run_hook(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
        })
        assert result.returncode == 0


# ── Install output correctness ─────────────────────────────────────────────


class TestInstallOutputCorrectness:
    """Tests that `install` produces a working config artifact."""

    def test_install_creates_scripts(self, tmp_path):
        from governor.claude_hooks import install_hook_scripts
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)

        assert "pre_tool_use" in scripts
        assert scripts["pre_tool_use"].exists()
        assert os.access(scripts["pre_tool_use"], os.X_OK)

    def test_install_creates_all_scripts(self, tmp_path):
        from governor.claude_hooks import install_hook_scripts
        (tmp_path / ".governor").mkdir()
        scripts = install_hook_scripts(tmp_path)

        assert set(scripts.keys()) == {"pre_tool_use", "post_tool_use", "notification"}
        for path in scripts.values():
            assert path.exists()
            assert os.access(path, os.X_OK)

    def test_settings_json_shape(self, tmp_path):
        from governor.claude_hooks import install_claude_hooks
        (tmp_path / ".governor").mkdir()
        success, _ = install_claude_hooks(tmp_path)
        assert success

        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        assert "hooks" in settings
        hooks = settings["hooks"]
        types = [h["type"] for h in hooks]
        assert "preToolUse" in types
        assert "postToolUse" in types

    def test_settings_paths_are_absolute(self, tmp_path):
        from governor.claude_hooks import install_claude_hooks
        (tmp_path / ".governor").mkdir()
        install_claude_hooks(tmp_path)

        settings = json.loads(
            (tmp_path / ".claude" / "settings.local.json").read_text()
        )
        for hook in settings["hooks"]:
            cmd = hook["command"]
            # Command contains a path starting with / (absolute)
            parts = cmd.split()
            assert len(parts) >= 2
            assert parts[1].startswith("/")


# ── check_codex_config ─────────────────────────────────────────────────────


class TestCheckCodexConfig:
    def test_missing_config(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        result = check_codex_config(tmp_path)
        assert result.status == "fail"

    def test_present(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "codex_hooks.json").write_text(
            json.dumps({"codex_path": "codex", "audit": True})
        )
        with patch("shutil.which", return_value="/usr/bin/codex"):
            result = check_codex_config(tmp_path)
            assert result.status == "pass"

    def test_binary_not_found(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        (tmp_path / ".governor" / "codex_hooks.json").write_text(
            json.dumps({"codex_path": "codex"})
        )
        with patch("shutil.which", return_value=None):
            result = check_codex_config(tmp_path)
            assert result.status == "warn"
            assert "not found" in result.detail
