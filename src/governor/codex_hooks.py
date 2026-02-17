# SPDX-License-Identifier: Apache-2.0
"""
Codex CLI hooks integration.

Codex has no native pre-tool hook system. Instead, we:
1. Parse the NDJSON event stream for audit + notifications
2. Snapshot-diff the filesystem for post-hoc accountability
3. Emit gate receipts for every governed execution

True pre-tool gating isn't possible without MCP proxy (v3).
This module provides full post-hoc audit and the wrapper for governed execution.
"""

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CodexHookConfig:
    """Configuration for Codex CLI hooks."""
    audit: bool = True                  # Write tool_audit.jsonl
    notifications: bool = True          # Write notifications.jsonl
    snapshot_changes: bool = True       # Pre/post filesystem diff
    codex_path: str = "codex"           # Path to codex binary
    model: str = "o4-mini"              # Default model

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit": self.audit,
            "notifications": self.notifications,
            "snapshot_changes": self.snapshot_changes,
            "codex_path": self.codex_path,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodexHookConfig":
        return cls(
            audit=data.get("audit", True),
            notifications=data.get("notifications", True),
            snapshot_changes=data.get("snapshot_changes", True),
            codex_path=data.get("codex_path", "codex"),
            model=data.get("model", "o4-mini"),
        )


def parse_codex_event(line: str) -> dict | None:
    """Parse a single NDJSON line from codex --json output.

    Returns parsed dict or None for empty/malformed lines.
    """
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def classify_event(event: dict) -> str:
    """Classify a codex event into a governor hook equivalent.

    Returns one of: "session_start", "response", "turn_end", "error", "unknown".
    """
    event_type = event.get("type", "")

    if event_type == "thread.started":
        return "session_start"
    elif event_type == "item.completed":
        item = event.get("item", {})
        if item.get("type") == "agent_message":
            return "response"
        return "unknown"
    elif event_type == "turn.completed":
        return "turn_end"
    elif event_type in ("error", "turn.failed"):
        return "error"
    return "unknown"


def extract_response_text(event: dict) -> str | None:
    """Extract response text from an item.completed event."""
    if event.get("type") != "item.completed":
        return None
    item = event.get("item", {})
    if item.get("type") == "agent_message":
        return item.get("text", "")
    return None


def extract_usage(event: dict) -> dict[str, int] | None:
    """Extract token usage from a turn.completed event."""
    if event.get("type") != "turn.completed":
        return None
    usage = event.get("usage", {})
    return {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }


def extract_error(event: dict) -> str | None:
    """Extract error message from an error/turn.failed event."""
    event_type = event.get("type", "")
    if event_type == "error":
        return event.get("message", "Unknown error")
    elif event_type == "turn.failed":
        return event.get("error", {}).get("message", "Unknown error")
    return None


def log_codex_event(gov_dir: Path, event: dict) -> None:
    """Append event to appropriate audit log in .governor/."""
    timestamp = datetime.now(timezone.utc).isoformat()
    classification = classify_event(event)

    # Always log to tool_audit.jsonl
    audit_entry = {
        "timestamp": timestamp,
        "source": "codex",
        "event_type": event.get("type", "unknown"),
        "classification": classification,
        "raw": event,
    }
    audit_file = gov_dir / "tool_audit.jsonl"
    with audit_file.open("a") as f:
        f.write(json.dumps(audit_entry) + "\n")

    # Log notifications for session-level events
    if classification in ("session_start", "turn_end", "error"):
        notif_entry = {
            "timestamp": timestamp,
            "event_type": f"codex.{classification}",
            "data": event,
        }
        notif_file = gov_dir / "notifications.jsonl"
        with notif_file.open("a") as f:
            f.write(json.dumps(notif_entry) + "\n")


def _log_file_changes(gov_dir: Path, changes: list) -> None:
    """Log file changes to audit trail."""
    if not changes:
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    for change in changes:
        entry = {
            "timestamp": timestamp,
            "source": "codex",
            "event_type": "file_change",
            "classification": "file_change",
            "raw": {
                "path": change.path,
                "change_type": change.change_type,
            },
        }
        audit_file = gov_dir / "tool_audit.jsonl"
        with audit_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def run_codex_governed(
    project_dir: Path,
    prompt: str,
    config: CodexHookConfig | None = None,
    env: dict[str, str] | None = None,
    _snapshot_cls: type | None = None,
) -> tuple[int, str, list]:
    """Run codex exec with governor instrumentation.

    Returns (exit_code, response_text, file_changes).

    Flow:
    1. Take filesystem snapshot (reuse DirectorySnapshot from wrapper.py)
    2. Run `codex exec --json -m <model> -` with prompt via stdin
    3. Parse NDJSON events, log each to .governor/ audit files
    4. Take post-snapshot, diff for file changes
    5. Log file changes to tool_audit.jsonl
    6. Emit gate receipt (verdict based on file changes vs approved list)
    7. Return results
    """
    from .wrapper import DirectorySnapshot

    SnapshotCls = _snapshot_cls or DirectorySnapshot
    config = config or CodexHookConfig()
    gov_dir = project_dir / ".governor"

    # 1. Pre-snapshot
    pre_snapshot = None
    if config.snapshot_changes:
        pre_snapshot = SnapshotCls(project_dir)

    # 2. Run codex
    cmd = [config.codex_path, "exec", "--json", "--skip-git-repo-check", "-m", config.model, "-"]
    run_env = dict(env or {})

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env={**dict(subprocess.os.environ), **run_env} if run_env else None,
            cwd=str(project_dir),
        )
    except FileNotFoundError:
        return (127, f"Codex binary not found: {config.codex_path}", [])
    except Exception as e:
        return (1, f"Failed to run codex: {e}", [])

    # 3. Parse NDJSON events
    content_parts: list[str] = []
    usage: dict[str, int] = {}

    for line in result.stdout.splitlines():
        event = parse_codex_event(line)
        if event is None:
            continue

        # Log to audit trail
        if config.audit and gov_dir.exists():
            log_codex_event(gov_dir, event)

        # Accumulate response
        text = extract_response_text(event)
        if text is not None:
            content_parts.append(text)

        # Capture usage
        u = extract_usage(event)
        if u is not None:
            usage = u

        # Handle errors
        error = extract_error(event)
        if error is not None:
            content_parts.append(f"\n[Error] {error}")

    response_text = "".join(content_parts)

    # 4. Post-snapshot + diff
    file_changes: list = []
    if config.snapshot_changes and pre_snapshot is not None:
        post_snapshot = SnapshotCls(project_dir)
        file_changes = pre_snapshot.diff(post_snapshot)

    # 5. Log file changes
    if config.audit and gov_dir.exists() and file_changes:
        _log_file_changes(gov_dir, file_changes)

    # 6. Emit gate receipt
    if gov_dir.exists():
        _emit_receipt(gov_dir, file_changes, config)

    return (result.returncode, response_text, file_changes)


def _emit_receipt(gov_dir: Path, file_changes: list, config: CodexHookConfig) -> None:
    """Emit a gate receipt for the codex execution."""
    try:
        from .gate_receipt import GateReceiptSystem

        # Determine verdict based on file changes
        if not file_changes:
            verdict = "pass"
        else:
            # Check approved files
            approved_path = gov_dir / "approved_files.json"
            if approved_path.exists():
                try:
                    approved = set(json.loads(approved_path.read_text()))
                except (json.JSONDecodeError, OSError):
                    approved = set()

                unapproved = [c for c in file_changes if c.path not in approved]
                verdict = "block" if unapproved else "pass"
            else:
                # No approved list → all changes flagged
                verdict = "warn"

        system = GateReceiptSystem(gov_dir)
        system.emit(
            gate="codex_hooks",
            verdict=verdict,
            subject_kind="codex_execution",
            subject_bytes="\n".join(
                sorted(c.path for c in file_changes)
            ).encode("utf-8") if file_changes else b"no_changes",
            evidence_bundle={
                "changes": [
                    {"path": c.path, "type": c.change_type}
                    for c in file_changes
                ],
                "model": config.model,
            },
            gate_config={
                "gate": "codex_hooks",
                "enforcement": "posthoc",
                "model": config.model,
                "snapshot_changes": config.snapshot_changes,
            },
        )
    except Exception:
        pass  # Fail-open: receipt emission should never block execution


def get_codex_status(project_dir: Path) -> dict[str, Any]:
    """Check codex hooks status."""
    gov_dir = project_dir / ".governor"
    config_path = gov_dir / "codex_hooks.json"

    status: dict[str, Any] = {
        "config_exists": config_path.exists(),
        "codex_available": False,
        "codex_path": "codex",
        "audit_files": [],
    }

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            status["codex_path"] = data.get("codex_path", "codex")
            status["config"] = data
        except (json.JSONDecodeError, OSError):
            status["config_error"] = "Failed to read config"

    # Check if codex binary is available
    codex_path = status["codex_path"]
    status["codex_available"] = shutil.which(codex_path) is not None

    # Check for audit files
    if gov_dir.exists():
        for name in ["tool_audit.jsonl", "notifications.jsonl"]:
            path = gov_dir / name
            if path.exists():
                status["audit_files"].append(name)

    return status


def install_codex_config(project_dir: Path, config: CodexHookConfig | None = None) -> tuple[bool, str]:
    """Write default config and verify codex binary is available.

    Returns (success, message).
    """
    config = config or CodexHookConfig()
    gov_dir = project_dir / ".governor"

    if not gov_dir.exists():
        return False, ".governor/ directory does not exist — run `governor init` first"

    config_path = gov_dir / "codex_hooks.json"
    config_path.write_text(json.dumps(config.to_dict(), indent=2))

    # Check if codex binary is available
    if not shutil.which(config.codex_path):
        return True, (
            f"Config written to {config_path}\n"
            f"Warning: codex binary '{config.codex_path}' not found in PATH"
        )

    return True, f"Config written to {config_path}"


def uninstall_codex_config(project_dir: Path) -> tuple[bool, str]:
    """Remove codex hooks config.

    Returns (success, message).
    """
    config_path = project_dir / ".governor" / "codex_hooks.json"

    if not config_path.exists():
        return True, "No codex hooks config to remove"

    try:
        config_path.unlink()
        return True, "Codex hooks config removed"
    except OSError as e:
        return False, f"Failed to remove config: {e}"
