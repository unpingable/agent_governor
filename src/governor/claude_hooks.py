"""
Claude Code hooks integration.

Generates hook scripts that integrate the governor with Claude Code's
hook system for pre/post tool call verification.

Claude Code hooks are configured in:
- Project: .claude/settings.json or .claude/settings.local.json
- User: ~/.claude/settings.json

Hook types:
- PreToolUse: Runs before a tool is used
- PostToolUse: Runs after a tool completes
- Notification: Runs on status updates
"""

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Hook script templates

PRE_TOOL_USE_SCRIPT = '''\
#!/usr/bin/env python3
"""
Governor pre-tool hook for Claude Code.

Validates tool calls before execution:
- Checks if file operations are in approved scope
- Validates command safety
- Enforces governor rules
"""

import json
import sys
from pathlib import Path

def get_governor_dir() -> Path | None:
    """Find the .governor directory."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        gov_dir = parent / ".governor"
        if gov_dir.exists():
            return gov_dir
    return None

def load_permissions(gov_dir: Path) -> dict:
    """Load governor permissions."""
    perms_file = gov_dir / "permissions.json"
    if perms_file.exists():
        return json.loads(perms_file.read_text())
    return {}

def check_file_operation(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Check if a file operation is allowed."""
    gov_dir = get_governor_dir()
    if not gov_dir:
        return True, "No governor initialized"

    # Get file path from various tool input formats
    file_path = None
    if "file_path" in tool_input:
        file_path = tool_input["file_path"]
    elif "path" in tool_input:
        file_path = tool_input["path"]
    elif "target" in tool_input:
        file_path = tool_input["target"]

    if not file_path:
        return True, "No file path in operation"

    # Check against approved files
    approved_file = gov_dir / "approved_files.json"
    if approved_file.exists():
        approved = set(json.loads(approved_file.read_text()))
        if file_path not in approved:
            # Check if it's a new file (allowed in exploratory mode)
            mode_file = gov_dir / "envelope.json"
            if mode_file.exists():
                mode = json.loads(mode_file.read_text()).get("mode", "strict")
                if mode == "strict":
                    return False, f"File not pre-approved: {file_path}"

    return True, "Allowed"

def check_command(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Check if a command is safe to run."""
    gov_dir = get_governor_dir()
    if not gov_dir:
        return True, "No governor initialized"

    command = tool_input.get("command", "")

    # Load blocked commands
    blocked_file = gov_dir / "blocked_commands.json"
    if blocked_file.exists():
        blocked = json.loads(blocked_file.read_text())
        for pattern in blocked:
            if pattern in command:
                return False, f"Blocked command pattern: {pattern}"

    return True, "Allowed"

def main():
    """Main hook entry point."""
    # Read hook input from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # No input or invalid JSON - allow
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Check based on tool type
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        allowed, reason = check_file_operation(tool_name, tool_input)
    elif tool_name == "Bash":
        allowed, reason = check_command(tool_name, tool_input)
    else:
        allowed, reason = True, "No restrictions for this tool"

    if not allowed:
        # Output rejection message
        result = {
            "decision": "block",
            "reason": reason,
            "message": f"Governor blocked {tool_name}: {reason}",
        }
        print(json.dumps(result))
        sys.exit(2)  # Non-zero to block

    sys.exit(0)  # Allow

if __name__ == "__main__":
    main()
'''

POST_TOOL_USE_SCRIPT = '''\
#!/usr/bin/env python3
"""
Governor post-tool hook for Claude Code.

Records tool outcomes for audit and verification:
- Logs file changes
- Records command outputs
- Updates governor state
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def get_governor_dir() -> Path | None:
    """Find the .governor directory."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        gov_dir = parent / ".governor"
        if gov_dir.exists():
            return gov_dir
    return None

def log_tool_use(tool_name: str, tool_input: dict, tool_output: dict) -> None:
    """Log tool use for audit."""
    gov_dir = get_governor_dir()
    if not gov_dir:
        return

    audit_file = gov_dir / "tool_audit.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
    }

    with audit_file.open("a") as f:
        f.write(json.dumps(entry) + "\\n")

def update_file_state(tool_name: str, tool_input: dict) -> None:
    """Update tracked file state after a file operation."""
    gov_dir = get_governor_dir()
    if not gov_dir:
        return

    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not file_path:
        return

    # Record the file was modified
    modified_file = gov_dir / "modified_files.json"
    if modified_file.exists():
        modified = set(json.loads(modified_file.read_text()))
    else:
        modified = set()

    modified.add(file_path)
    modified_file.write_text(json.dumps(list(modified), indent=2))

def main():
    """Main hook entry point."""
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_output = input_data.get("tool_output", {})

    # Log for audit
    log_tool_use(tool_name, tool_input, tool_output)

    # Update state for file operations
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        update_file_state(tool_name, tool_input)

    sys.exit(0)

if __name__ == "__main__":
    main()
'''

NOTIFICATION_SCRIPT = '''\
#!/usr/bin/env python3
"""
Governor notification hook for Claude Code.

Handles status notifications:
- Session start/end
- Task completion
- Error events
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def get_governor_dir() -> Path | None:
    """Find the .governor directory."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        gov_dir = parent / ".governor"
        if gov_dir.exists():
            return gov_dir
    return None

def log_notification(event_type: str, data: dict) -> None:
    """Log notification for audit."""
    gov_dir = get_governor_dir()
    if not gov_dir:
        return

    log_file = gov_dir / "notifications.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "data": data,
    }

    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\\n")

def main():
    """Main hook entry point."""
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    event_type = input_data.get("type", "unknown")
    log_notification(event_type, input_data)

    sys.exit(0)

if __name__ == "__main__":
    main()
'''


@dataclass
class HookConfig:
    """Configuration for Claude Code hooks."""

    # Which hooks to install
    pre_tool_use: bool = True
    post_tool_use: bool = True
    notification: bool = True

    # Tools to filter (empty = all tools)
    pre_tool_filter: list[str] = field(default_factory=lambda: ["Write", "Edit", "Bash", "NotebookEdit"])
    post_tool_filter: list[str] = field(default_factory=lambda: ["Write", "Edit", "NotebookEdit"])

    # Timeout in milliseconds
    timeout_ms: int = 5000

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_tool_use": self.pre_tool_use,
            "post_tool_use": self.post_tool_use,
            "notification": self.notification,
            "pre_tool_filter": self.pre_tool_filter,
            "post_tool_filter": self.post_tool_filter,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HookConfig":
        return cls(
            pre_tool_use=data.get("pre_tool_use", True),
            post_tool_use=data.get("post_tool_use", True),
            notification=data.get("notification", True),
            pre_tool_filter=data.get("pre_tool_filter", ["Write", "Edit", "Bash", "NotebookEdit"]),
            post_tool_filter=data.get("post_tool_filter", ["Write", "Edit", "NotebookEdit"]),
            timeout_ms=data.get("timeout_ms", 5000),
        )


def get_hooks_dir(project_dir: Path) -> Path:
    """Get the hooks directory for a project."""
    return project_dir / ".governor" / "hooks"


def get_claude_settings_path(project_dir: Path) -> Path:
    """Get the Claude Code settings path for a project."""
    return project_dir / ".claude" / "settings.local.json"


def install_hook_scripts(project_dir: Path) -> dict[str, Path]:
    """
    Install hook scripts to the project's .governor/hooks directory.

    Returns dict of hook_name -> script_path.
    """
    hooks_dir = get_hooks_dir(project_dir)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts = {}

    # Pre-tool hook
    pre_hook = hooks_dir / "pre_tool_use.py"
    pre_hook.write_text(PRE_TOOL_USE_SCRIPT)
    pre_hook.chmod(pre_hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts["pre_tool_use"] = pre_hook

    # Post-tool hook
    post_hook = hooks_dir / "post_tool_use.py"
    post_hook.write_text(POST_TOOL_USE_SCRIPT)
    post_hook.chmod(post_hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts["post_tool_use"] = post_hook

    # Notification hook
    notif_hook = hooks_dir / "notification.py"
    notif_hook.write_text(NOTIFICATION_SCRIPT)
    notif_hook.chmod(notif_hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts["notification"] = notif_hook

    return scripts


def generate_claude_settings(
    project_dir: Path,
    config: HookConfig | None = None,
) -> dict[str, Any]:
    """
    Generate Claude Code settings with hook configuration.

    Returns the settings dict (doesn't write to file).
    """
    config = config or HookConfig()
    hooks_dir = get_hooks_dir(project_dir)

    hooks = []

    if config.pre_tool_use:
        hook_entry = {
            "type": "preToolUse",
            "command": f"python3 {hooks_dir / 'pre_tool_use.py'}",
            "timeout": config.timeout_ms,
        }
        if config.pre_tool_filter:
            hook_entry["tools"] = config.pre_tool_filter
        hooks.append(hook_entry)

    if config.post_tool_use:
        hook_entry = {
            "type": "postToolUse",
            "command": f"python3 {hooks_dir / 'post_tool_use.py'}",
            "timeout": config.timeout_ms,
        }
        if config.post_tool_filter:
            hook_entry["tools"] = config.post_tool_filter
        hooks.append(hook_entry)

    if config.notification:
        hooks.append({
            "type": "notification",
            "command": f"python3 {hooks_dir / 'notification.py'}",
            "timeout": config.timeout_ms,
        })

    return {"hooks": hooks}


def install_claude_hooks(
    project_dir: Path,
    config: HookConfig | None = None,
    merge: bool = True,
) -> tuple[bool, str]:
    """
    Install Claude Code hooks for the project.

    Args:
        project_dir: Project root directory
        config: Hook configuration
        merge: If True, merge with existing settings; if False, overwrite

    Returns:
        (success, message)
    """
    config = config or HookConfig()

    # Install hook scripts
    try:
        scripts = install_hook_scripts(project_dir)
    except Exception as e:
        return False, f"Failed to install hook scripts: {e}"

    # Generate settings
    new_settings = generate_claude_settings(project_dir, config)

    # Load existing settings if merging
    settings_path = get_claude_settings_path(project_dir)

    if merge and settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
            # Merge hooks (replace existing governor hooks)
            existing_hooks = existing.get("hooks", [])
            # Remove any existing governor hooks
            hooks_dir_str = str(get_hooks_dir(project_dir))
            existing_hooks = [h for h in existing_hooks if hooks_dir_str not in h.get("command", "")]
            # Add new hooks
            existing_hooks.extend(new_settings["hooks"])
            existing["hooks"] = existing_hooks
            new_settings = existing
        except Exception:
            pass  # Use new settings only

    # Write settings
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(new_settings, indent=2))
    except Exception as e:
        return False, f"Failed to write settings: {e}"

    return True, f"Installed {len(scripts)} hook scripts and updated {settings_path}"


def uninstall_claude_hooks(project_dir: Path) -> tuple[bool, str]:
    """
    Uninstall Claude Code hooks for the project.

    Returns:
        (success, message)
    """
    hooks_dir = get_hooks_dir(project_dir)

    # Remove hook scripts
    removed_scripts = []
    if hooks_dir.exists():
        for script in hooks_dir.glob("*.py"):
            try:
                script.unlink()
                removed_scripts.append(script.name)
            except Exception:
                pass

    # Update Claude settings
    settings_path = get_claude_settings_path(project_dir)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            if "hooks" in settings:
                hooks_dir_str = str(hooks_dir)
                settings["hooks"] = [
                    h for h in settings["hooks"]
                    if hooks_dir_str not in h.get("command", "")
                ]
                settings_path.write_text(json.dumps(settings, indent=2))
        except Exception:
            pass

    return True, f"Removed {len(removed_scripts)} hook scripts"


def get_hook_status(project_dir: Path) -> dict[str, Any]:
    """Get the current hook installation status."""
    hooks_dir = get_hooks_dir(project_dir)
    settings_path = get_claude_settings_path(project_dir)

    status = {
        "hooks_dir_exists": hooks_dir.exists(),
        "scripts_installed": [],
        "claude_settings_exists": settings_path.exists(),
        "hooks_configured": [],
    }

    if hooks_dir.exists():
        status["scripts_installed"] = [f.name for f in hooks_dir.glob("*.py")]

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            hooks = settings.get("hooks", [])
            hooks_dir_str = str(hooks_dir)
            status["hooks_configured"] = [
                h.get("type") for h in hooks
                if hooks_dir_str in h.get("command", "")
            ]
        except Exception:
            pass

    return status


def create_blocked_commands_file(project_dir: Path, patterns: list[str] | None = None) -> Path:
    """Create or update the blocked commands file."""
    gov_dir = project_dir / ".governor"
    gov_dir.mkdir(parents=True, exist_ok=True)

    blocked_file = gov_dir / "blocked_commands.json"

    default_patterns = [
        "rm -rf /",
        "rm -rf ~",
        ":(){ :|:& };:",  # Fork bomb
        "> /dev/sda",
        "mkfs.",
        "dd if=/dev/zero",
        "chmod -R 777 /",
        "curl | sh",
        "wget | sh",
    ]

    patterns = patterns or default_patterns
    blocked_file.write_text(json.dumps(patterns, indent=2))

    return blocked_file


def create_approved_files_file(project_dir: Path, files: list[str] | None = None) -> Path:
    """Create or update the approved files file."""
    gov_dir = project_dir / ".governor"
    gov_dir.mkdir(parents=True, exist_ok=True)

    approved_file = gov_dir / "approved_files.json"
    files = files or []
    approved_file.write_text(json.dumps(files, indent=2))

    return approved_file
