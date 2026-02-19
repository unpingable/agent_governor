# SPDX-License-Identifier: Apache-2.0
"""
Governor preflight checks.

Answers one question: "If an agent tries something unauthorized right now,
will the governor stop it?"

This is not configuration-checking — it's enforcement verification.
The smoke test actually runs the hook and confirms it blocks.
"""

import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreflightCheck:
    """Result of a single preflight check."""
    name: str           # e.g. "governor_dir_writable"
    status: str         # "pass" | "warn" | "fail"
    detail: str         # human-readable explanation
    fix: str | None = None  # command to fix, if applicable

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.fix is not None:
            d["fix"] = self.fix
        return d


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks."""
    checks: list[PreflightCheck] = field(default_factory=list)
    overall: str = "pass"  # "pass" | "warn" | "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "overall": self.overall,
        }


def _compute_overall(checks: list[PreflightCheck]) -> str:
    """Derive overall status from individual checks."""
    statuses = {c.status for c in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


# ── Individual checks ──────────────────────────────────────────────────────


def check_governor_dir(project_dir: Path) -> PreflightCheck:
    """Check that .governor/ exists and is writable."""
    gov_dir = project_dir / ".governor"
    if not gov_dir.exists():
        return PreflightCheck(
            name="governor_dir",
            status="fail",
            detail=".governor/ directory does not exist",
            fix="governor init",
        )
    if not gov_dir.is_dir():
        return PreflightCheck(
            name="governor_dir",
            status="fail",
            detail=".governor exists but is not a directory",
            fix="rm .governor && governor init",
        )
    if not os.access(gov_dir, os.W_OK):
        return PreflightCheck(
            name="governor_dir",
            status="fail",
            detail=".governor/ directory is not writable",
            fix=f"chmod u+w {gov_dir}",
        )
    return PreflightCheck(
        name="governor_dir",
        status="pass",
        detail="Governor directory writable",
    )


def check_envelope(project_dir: Path, require_strict: bool = False) -> PreflightCheck:
    """Check that envelope is readable and optionally strict."""
    gov_dir = project_dir / ".governor"
    envelope_path = gov_dir / ".envelope"

    if not envelope_path.exists():
        # Check legacy path
        legacy = gov_dir / "envelope.json"
        if legacy.exists():
            try:
                data = json.loads(legacy.read_text())
                mode = data.get("mode", "unknown")
            except (json.JSONDecodeError, OSError):
                return PreflightCheck(
                    name="envelope",
                    status="fail",
                    detail="envelope.json exists but is unreadable",
                    fix="governor envelope strict",
                )
        else:
            return PreflightCheck(
                name="envelope",
                status="fail",
                detail="No envelope file found (.envelope or envelope.json)",
                fix="governor envelope strict",
            )
    else:
        try:
            mode = envelope_path.read_text().strip()
        except OSError:
            return PreflightCheck(
                name="envelope",
                status="fail",
                detail=".envelope file exists but is unreadable",
                fix="governor envelope strict",
            )

    if not mode:
        return PreflightCheck(
            name="envelope",
            status="fail",
            detail=".envelope file is empty",
            fix="governor envelope strict",
        )

    if require_strict and mode != "strict":
        return PreflightCheck(
            name="envelope",
            status="fail",
            detail=f"Envelope is '{mode}' but strict is required",
            fix="governor envelope strict",
        )

    if mode != "strict":
        return PreflightCheck(
            name="envelope",
            status="warn",
            detail=f"Envelope is '{mode}' (not strict)",
            fix="governor envelope strict",
        )

    return PreflightCheck(
        name="envelope",
        status="pass",
        detail="Envelope: strict",
    )


def check_approved_files(project_dir: Path) -> PreflightCheck:
    """Check that approved_files.json exists."""
    gov_dir = project_dir / ".governor"
    approved_path = gov_dir / "approved_files.json"

    if not approved_path.exists():
        return PreflightCheck(
            name="approved_files",
            status="warn",
            detail="No approved_files.json — strict mode blocks everything",
            fix="governor claude-hooks approve <files>",
        )

    try:
        data = json.loads(approved_path.read_text())
    except (json.JSONDecodeError, OSError):
        return PreflightCheck(
            name="approved_files",
            status="warn",
            detail="approved_files.json exists but is unreadable",
            fix="governor claude-hooks approve <files>",
        )

    count = len(data) if isinstance(data, list) else 0
    if count == 0:
        return PreflightCheck(
            name="approved_files",
            status="warn",
            detail="approved_files.json is empty — strict mode blocks all writes",
            fix="governor claude-hooks approve <files>",
        )

    return PreflightCheck(
        name="approved_files",
        status="pass",
        detail=f"Approved files list present ({count} files)",
    )


def check_claude_hooks(project_dir: Path) -> PreflightCheck:
    """Check that Claude Code hook scripts exist and settings reference them."""
    hooks_dir = project_dir / ".governor" / "hooks"
    settings_path = project_dir / ".claude" / "settings.local.json"

    # Check scripts exist + executable
    expected_scripts = ["pre_tool_use.py", "post_tool_use.py", "notification.py"]
    missing_scripts = []
    non_exec = []
    for name in expected_scripts:
        script = hooks_dir / name
        if not script.exists():
            missing_scripts.append(name)
        elif not os.access(script, os.X_OK):
            non_exec.append(name)

    if missing_scripts:
        return PreflightCheck(
            name="claude_hooks",
            status="fail",
            detail=f"Missing hook scripts: {', '.join(missing_scripts)}",
            fix="governor claude-hooks install",
        )

    if non_exec:
        return PreflightCheck(
            name="claude_hooks",
            status="fail",
            detail=f"Hook scripts not executable: {', '.join(non_exec)}",
            fix="governor claude-hooks install",
        )

    # Check settings.local.json references hooks
    if not settings_path.exists():
        return PreflightCheck(
            name="claude_hooks",
            status="fail",
            detail="settings.local.json missing — hooks not wired to Claude Code",
            fix="governor claude-hooks install",
        )

    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return PreflightCheck(
            name="claude_hooks",
            status="fail",
            detail="settings.local.json unreadable",
            fix="governor claude-hooks install",
        )

    hooks = settings.get("hooks", [])
    hooks_dir_str = str(hooks_dir)
    governor_hooks = [h for h in hooks if hooks_dir_str in h.get("command", "")]

    if not governor_hooks:
        return PreflightCheck(
            name="claude_hooks",
            status="fail",
            detail="settings.local.json has no governor hook entries",
            fix="governor claude-hooks install",
        )

    has_pre = any(h.get("type") == "preToolUse" for h in governor_hooks)
    if not has_pre:
        return PreflightCheck(
            name="claude_hooks",
            status="warn",
            detail="No preToolUse hook configured — writes won't be blocked",
            fix="governor claude-hooks install",
        )

    return PreflightCheck(
        name="claude_hooks",
        status="pass",
        detail=f"Claude hooks: configured + installed ({len(governor_hooks)} hooks)",
    )


def smoke_test_claude_hook(project_dir: Path) -> PreflightCheck:
    """Run the pre-tool hook with a synthetic unapproved write and verify it blocks."""
    hook_script = project_dir / ".governor" / "hooks" / "pre_tool_use.py"

    if not hook_script.exists():
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail="pre_tool_use.py not found — cannot smoke test",
            fix="governor claude-hooks install",
        )

    # Synthetic payload: Write to a file that definitely isn't approved
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/__governor_preflight_smoke_test_unapproved__.txt",
            "content": "smoke test",
        },
    })

    try:
        result = subprocess.run(
            ["python3", str(hook_script)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_dir),
        )
    except subprocess.TimeoutExpired:
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail="Hook script timed out (>10s)",
            fix="governor claude-hooks install",
        )
    except FileNotFoundError:
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail="python3 not found",
        )
    except Exception as e:
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail=f"Failed to run hook: {e}",
            fix="governor claude-hooks install",
        )

    if result.returncode != 2:
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail=f"Hook exited {result.returncode} (expected 2 = block)",
            fix="governor claude-hooks install",
        )

    # Verify output contains a block decision
    stdout = result.stdout.strip()
    try:
        output = json.loads(stdout)
        if output.get("decision") != "block":
            return PreflightCheck(
                name="claude_hook_smoke",
                status="fail",
                detail=f"Hook output decision is '{output.get('decision')}', expected 'block'",
                fix="governor claude-hooks install",
            )
    except (json.JSONDecodeError, AttributeError):
        return PreflightCheck(
            name="claude_hook_smoke",
            status="fail",
            detail="Hook stdout is not valid JSON with 'decision' field",
            fix="governor claude-hooks install",
        )

    return PreflightCheck(
        name="claude_hook_smoke",
        status="pass",
        detail="Pre-tool smoke test: blocks unapproved write (exit=2)",
    )


def check_git_hook(project_dir: Path) -> PreflightCheck:
    """Check that git pre-commit hook exists and references governor."""
    git_hook = project_dir / ".git" / "hooks" / "pre-commit"

    if not git_hook.exists():
        return PreflightCheck(
            name="git_hook",
            status="warn",
            detail="Git pre-commit hook not installed",
            fix="governor hook install",
        )

    if not os.access(git_hook, os.X_OK):
        return PreflightCheck(
            name="git_hook",
            status="warn",
            detail="Git pre-commit hook exists but not executable",
            fix=f"chmod +x {git_hook}",
        )

    try:
        content = git_hook.read_text()
    except OSError:
        return PreflightCheck(
            name="git_hook",
            status="warn",
            detail="Git pre-commit hook exists but unreadable",
            fix="governor hook install",
        )

    if "governor" not in content:
        return PreflightCheck(
            name="git_hook",
            status="warn",
            detail="Git pre-commit hook exists but doesn't reference governor",
            fix="governor hook install",
        )

    return PreflightCheck(
        name="git_hook",
        status="pass",
        detail="Git pre-commit hook installed",
    )


def check_restart_advisory(project_dir: Path) -> PreflightCheck:
    """Check if settings changed after last observed hook invocation.

    Uses hook_invocations.jsonl (written by the pre-tool hook every time it
    fires) as the ground truth for "hooks are actually live." Falls back to
    notifications.jsonl if invocations file doesn't exist yet.
    """
    settings_path = project_dir / ".claude" / "settings.local.json"
    invocations_path = project_dir / ".governor" / "hook_invocations.jsonl"
    notifications_path = project_dir / ".governor" / "notifications.jsonl"

    if not settings_path.exists():
        return PreflightCheck(
            name="restart_advisory",
            status="pass",
            detail="No settings file — no restart needed",
        )

    try:
        settings_mtime = settings_path.stat().st_mtime
    except OSError:
        return PreflightCheck(
            name="restart_advisory",
            status="pass",
            detail="Cannot read settings mtime",
        )

    # Prefer hook_invocations (direct proof hooks fired) over notifications
    activity_path = invocations_path if invocations_path.exists() else notifications_path

    if not activity_path.exists():
        # No activity recorded — hooks have never fired
        return PreflightCheck(
            name="restart_advisory",
            status="warn",
            detail="No hook invocations recorded — hooks may not be loaded yet",
            fix="Restart Claude Code to load hooks",
        )

    try:
        activity_mtime = activity_path.stat().st_mtime
    except OSError:
        return PreflightCheck(
            name="restart_advisory",
            status="pass",
            detail="Cannot read activity file mtime",
        )

    if settings_mtime > activity_mtime:
        return PreflightCheck(
            name="restart_advisory",
            status="warn",
            detail="Settings changed after last hook invocation — agent has stale hooks",
            fix="Restart Claude Code to load updated hooks",
        )

    return PreflightCheck(
        name="restart_advisory",
        status="pass",
        detail="Hooks invoked after last settings change — hooks are current",
    )


def check_codex_config(project_dir: Path) -> PreflightCheck:
    """Check Codex hooks configuration."""
    config_path = project_dir / ".governor" / "codex_hooks.json"

    if not config_path.exists():
        return PreflightCheck(
            name="codex_hooks",
            status="fail",
            detail="Codex hooks config not found",
            fix="governor codex-hooks install",
        )

    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return PreflightCheck(
            name="codex_hooks",
            status="fail",
            detail="Codex hooks config unreadable",
            fix="governor codex-hooks install",
        )

    # Check if codex binary is available
    import shutil
    codex_path = data.get("codex_path", "codex")
    if not shutil.which(codex_path):
        return PreflightCheck(
            name="codex_hooks",
            status="warn",
            detail=f"Codex binary '{codex_path}' not found in PATH",
        )

    return PreflightCheck(
        name="codex_hooks",
        status="pass",
        detail="Codex hooks configured",
    )


def check_gate_heartbeat(project_dir: Path) -> PreflightCheck:
    """Check that the evidence gate fired in the last session.

    Logic:
    - No .governor/ → skip (check #1 handles this)
    - No receipts AND no session artifacts → pass (clean install)
    - No receipts BUT session artifacts exist → warn
    - Receipts exist → pass
    """
    gov_dir = project_dir / ".governor"
    if not gov_dir.exists():
        return PreflightCheck(
            name="gate_heartbeat",
            status="pass",
            detail="No .governor/ directory — skipping gate heartbeat",
        )

    receipt_path = gov_dir / "receipts" / "gate_receipts.jsonl"
    has_receipts = receipt_path.exists() and receipt_path.stat().st_size > 0

    if has_receipts:
        return PreflightCheck(
            name="gate_heartbeat",
            status="pass",
            detail="Gate receipts present — evidence gate has fired",
        )

    # No receipts — check if there are session artifacts indicating
    # a session has run (sessions index, telemetry logs, etc.)
    session_indicators = [
        gov_dir / "sessions" / "index.json",
        gov_dir / "telemetry",
        gov_dir / "hook_invocations.jsonl",
    ]
    has_session = any(p.exists() for p in session_indicators)

    if has_session:
        return PreflightCheck(
            name="gate_heartbeat",
            status="warn",
            detail="Session artifacts exist but gate never fired — evidence gate may be bypassed",
            fix="governor gate check <file>",
        )

    # Clean install: no receipts, no session artifacts
    return PreflightCheck(
        name="gate_heartbeat",
        status="pass",
        detail="No receipts or session artifacts — clean install",
    )


# ── Agent detection ────────────────────────────────────────────────────────


def detect_agent(project_dir: Path) -> str | None:
    """Auto-detect which agent is configured for this project."""
    if (project_dir / ".claude" / "settings.local.json").exists():
        return "claude"
    if (project_dir / ".codex").exists():
        return "codex"
    if (project_dir / ".governor" / "codex_hooks.json").exists():
        return "codex"
    return None


# ── Orchestrator ───────────────────────────────────────────────────────────


def run_preflight(
    project_dir: Path,
    agent: str | None = None,
    strict: bool = False,
) -> PreflightResult:
    """Run all applicable preflight checks.

    Args:
        project_dir: Project root directory.
        agent: "claude" | "codex" | None (auto-detect).
        strict: If True, fail if envelope isn't strict.

    Returns:
        PreflightResult with all checks and overall status.
    """
    if agent is None:
        agent = detect_agent(project_dir)

    checks: list[PreflightCheck] = []

    # 1. Governor dir
    checks.append(check_governor_dir(project_dir))

    # 2+3. Envelope
    checks.append(check_envelope(project_dir, require_strict=strict))

    # 4. Approved files
    checks.append(check_approved_files(project_dir))

    # Agent-specific checks
    if agent == "claude":
        # 5. Claude hooks installed
        checks.append(check_claude_hooks(project_dir))
        # 6. Smoke test (only if hooks are installed)
        hook_check = checks[-1]
        if hook_check.status == "pass":
            checks.append(smoke_test_claude_hook(project_dir))
    elif agent == "codex":
        checks.append(check_codex_config(project_dir))

    # 7. Git pre-commit hook
    checks.append(check_git_hook(project_dir))

    # 8. Restart advisory (claude only)
    if agent == "claude":
        checks.append(check_restart_advisory(project_dir))

    # 9. Gate heartbeat (all agents)
    checks.append(check_gate_heartbeat(project_dir))

    overall = _compute_overall(checks)

    return PreflightResult(checks=checks, overall=overall)
