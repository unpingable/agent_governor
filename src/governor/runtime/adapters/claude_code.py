# SPDX-License-Identifier: Apache-2.0
"""Claude Code runtime adapter for supervised sessions.

Supervised mode: Governor launches Claude Code as a managed child process.
Hook scripts communicate with the supervisor via a Unix domain socket
(one per session) for real-time tool interception.

Builds on existing claude_hooks.py for hook script generation.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    LaunchConfig,
    NativeEvent,
)
from governor.runtime.events import EventKind, SourceLayer


# Default supervisor decision window (seconds). Must match
# SessionSupervisor's default_timeout; the live value is threaded through
# the GOVERNOR_DECISION_TIMEOUT env var at launch.
DEFAULT_DECISION_TIMEOUT = 300.0

# Grace added on top of the decision window. The supervisor's own
# timeout watcher auto-denies at the decision window and answers over
# the socket, so under normal operation the hook never hits its own
# deadline — the hook-side timeout is purely a backstop for a hung or
# dead supervisor, and it too fails closed.
HOOK_WAIT_GRACE = 30.0


# Hook script template for supervised mode.
# Connects to supervisor socket, sends tool info, waits for decision.
# FAIL-CLOSED: a supervised session whose supervisor is absent, hung, or
# unintelligible has no authority to mutate anything. Every error path
# denies with an explicit reason; silence is never an allow.
_SUPERVISED_PRE_TOOL_SCRIPT = '''\
#!/usr/bin/env python3
"""Governor supervised pre-tool hook. Talks to supervisor socket.

Fail-closed: timeout, socket error, missing configuration, or a
garbled response all DENY the tool call with an explicit reason.
"""
import json
import os
import socket
import sys

def _deny(reason):
    # Claude Code PreToolUse hook output format
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))

def _env_float(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default

def main():
    sock_path = os.environ.get("GOVERNOR_SUPERVISOR_SOCKET")
    if not sock_path:
        _deny("Governor supervised session: supervisor socket not configured — failing closed.")
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        _deny("Governor supervised session: could not parse hook input — failing closed.")
        return

    decision_timeout = _env_float("GOVERNOR_DECISION_TIMEOUT", 300.0)
    grace = _env_float("GOVERNOR_HOOK_WAIT_GRACE", 30.0)
    wait_seconds = decision_timeout + grace

    msg = json.dumps({
        "type": "pre_tool_use",
        "tool_name": data.get("tool_name", "unknown"),
        "tool_input": data.get("tool_input", {}),
        "tool_call_id": data.get("tool_use_id", ""),
        "session_id": os.environ.get("GOVERNOR_SESSION_ID", ""),
    }) + "\\n"

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(wait_seconds)
        s.connect(sock_path)
        s.sendall(msg.encode())
        resp = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
            if b"\\n" in resp:
                break
        s.close()

        result = json.loads(resp.decode().strip())
        decision = result.get("decision")
        if decision == "allow":
            return  # allow — output nothing, exit 0
        if decision == "deny":
            _deny(result.get("reason", "Blocked by governor"))
            return
        _deny("Governor supervised session: unrecognized supervisor decision %r — failing closed." % (decision,))
    except socket.timeout:
        _deny("Governor supervised session: no supervisor decision within %ds — failing closed." % int(wait_seconds))
    except Exception as exc:
        _deny("Governor supervised session: supervisor unreachable (%s) — failing closed." % exc.__class__.__name__)

if __name__ == "__main__":
    main()
'''

_SUPERVISED_POST_TOOL_SCRIPT = '''\
#!/usr/bin/env python3
"""Governor supervised post-tool hook. Notifies supervisor of completion."""
import json
import os
import socket
import sys

def main():
    sock_path = os.environ.get("GOVERNOR_SUPERVISOR_SOCKET")
    if not sock_path:
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    msg = json.dumps({
        "type": "post_tool_use",
        "tool_name": data.get("tool_name", "unknown"),
        "tool_call_id": data.get("tool_use_id", ""),
        "session_id": os.environ.get("GOVERNOR_SESSION_ID", ""),
    }) + "\\n"

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(sock_path)
        s.sendall(msg.encode())
        s.close()
    except Exception:
        pass  # Post-tool is observe-only, never block

if __name__ == "__main__":
    main()
'''


def build_isolated_settings(
    pre_hook: Path, post_hook: Path, decision_timeout: float
) -> dict[str, Any]:
    """Build the isolated --settings payload for a supervised child session.

    The PreToolUse hook timeout must strictly exceed the hook script's own
    wait (decision window + HOOK_WAIT_GRACE): Claude Code treats a
    hook it kills at timeout as a non-blocking error and PROCEEDS with the
    tool call, which would reopen the fail-open hole from outside the
    script. The extra grace here keeps the kill deadline behind the
    script's deny deadline.
    """
    pre_tool_hook_timeout = int(decision_timeout + HOOK_WAIT_GRACE + 30)
    return {
        # Permissions: allow all governed tools
        "permissions": {
            "allow": [
                "Read(*)",
                "Write(*)",
                "Edit(*)",
                "Bash(*)",
                "Glob(*)",
                "Grep(*)",
                "NotebookEdit(*)",
            ],
        },
        # Hooks: governor pre/post tool interception
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {pre_hook}",
                            "timeout": pre_tool_hook_timeout,
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {post_hook}",
                            "timeout": 5,
                        }
                    ],
                }
            ],
        },
    }


@dataclass
class ClaudeCodeHandle(BackendHandle):
    """Handle to a running Claude Code process."""

    process: subprocess.Popen | None = None
    socket_path: str | None = None
    hooks_dir: str | None = None
    listener_socket: socket.socket | None = None


class ClaudeCodeAdapter:
    """Runtime adapter for Claude Code in supervised mode.

    Launches claude CLI as a child process with governor hooks that
    communicate via Unix domain socket for real-time tool interception.
    """

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_pause=False,  # Soft pause only (block approvals)
            supports_resume=False,
            supports_native_tool_hooks=True,
            supports_structured_events=True,
            supports_input_injection=True,
            supports_graceful_shutdown=True,
        )

    def launch(self, config: LaunchConfig) -> ClaudeCodeHandle:
        """Launch Claude Code as a managed child process.

        Uses --settings to pass an ISOLATED settings file with governor hooks
        and permissions. Does NOT modify the project's .claude/settings.local.json.
        This prevents stale hooks from poisoning the parent Claude session.
        """
        cwd = Path(config.cwd)

        # Create temp dir for hook scripts, socket, and isolated settings
        hooks_dir = Path(tempfile.mkdtemp(prefix="gov_hooks_"))
        socket_path = str(hooks_dir / "supervisor.sock")

        # Write hook scripts
        pre_hook = hooks_dir / "pre_tool_use.py"
        pre_hook.write_text(_SUPERVISED_PRE_TOOL_SCRIPT)
        pre_hook.chmod(pre_hook.stat().st_mode | stat.S_IXUSR)

        post_hook = hooks_dir / "post_tool_use.py"
        post_hook.write_text(_SUPERVISED_POST_TOOL_SCRIPT)
        post_hook.chmod(post_hook.stat().st_mode | stat.S_IXUSR)

        # Supervisor decision window, threaded in via LaunchConfig.env.
        # The hook script waits this long (+ grace) for a decision; the
        # settings-level hook timeout must exceed that wait so Claude Code
        # never kills the hook before it can fail closed.
        try:
            decision_timeout = float(config.env.get("GOVERNOR_DECISION_TIMEOUT", ""))
        except (TypeError, ValueError):
            decision_timeout = DEFAULT_DECISION_TIMEOUT

        # Build isolated settings file for the child Claude session.
        # This is passed via --settings and does NOT touch the project's settings.
        isolated_settings = build_isolated_settings(pre_hook, post_hook, decision_timeout)

        settings_file = hooks_dir / "governor_settings.json"
        settings_file.write_text(json.dumps(isolated_settings, indent=2))

        # Create and bind listener socket BEFORE starting Claude
        # This prevents a race where Claude's hooks try to connect before we listen
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.settimeout(1.0)
        listener.bind(socket_path)
        listener.listen(5)

        # Build env for child process
        env = {**os.environ, **config.env}
        env["GOVERNOR_SUPERVISOR_SOCKET"] = socket_path
        env["GOVERNOR_SESSION_ID"] = config.session_id
        # Always set explicitly so the hook script and the settings-level
        # hook timeout agree on the decision window even when the
        # supervisor didn't pass one.
        env["GOVERNOR_DECISION_TIMEOUT"] = str(decision_timeout)

        # Build claude command
        # --settings: isolated settings file with hooks + permissions (no shared state pollution)
        # --permission-mode auto: Claude auto-approves within the settings permissions
        # --tools: hard capability boundary
        cmd = [
            "claude",
            "--settings", str(settings_file),
            "--permission-mode", "auto",
            "--tools", "Read,Write,Edit,Bash,Glob,Grep,NotebookEdit",
        ]
        if config.args:
            cmd.extend(config.args)

        # If a task is provided, pass it as the prompt
        if config.task:
            cmd.extend(["--print", config.task])

        process = subprocess.Popen(
            cmd,
            cwd=config.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Close stdin so Claude knows there's no interactive input
        # (--print mode reads prompt from args, not stdin)
        if config.task and process.stdin:
            process.stdin.close()

        handle = ClaudeCodeHandle(
            pid=process.pid,
            native_session_ref=config.session_id,
            process=process,
            socket_path=socket_path,
            hooks_dir=str(hooks_dir),
            listener_socket=listener,
            extra={"isolated_settings": str(settings_file)},
        )

        # NOTE: No atexit cleanup. Previous approach caused race conditions:
        # atexit handlers from earlier sessions delete temp dirs while the
        # current session's hooks still reference them, causing PostToolUse
        # hook failures that make Claude roll back edits.
        # Cleanup happens in explicit shutdown() only.
        # Use `governor runtime cleanup` for manual stale hook removal.

        return handle

    def iter_events(self, handle: ClaudeCodeHandle) -> Iterable[NativeEvent]:
        """Yield native events from the Claude Code process.

        Listens on the supervisor socket for hook messages and
        monitors stdout/stderr for agent output.
        """
        if not handle.socket_path:
            return

        # Use the pre-bound listener socket from launch()
        sock = handle.listener_socket
        if not sock:
            return

        # Monitor process stdout/stderr in threads
        stdout_events: list[NativeEvent] = []
        stderr_lines: list[str] = []
        stdout_lock = threading.Lock()

        def _read_stdout():
            if handle.process and handle.process.stdout:
                for line in handle.process.stdout:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        with stdout_lock:
                            stdout_events.append(
                                NativeEvent(
                                    kind="agent_output",
                                    payload={"text": text},
                                )
                            )

        def _read_stderr():
            if handle.process and handle.process.stderr:
                for line in handle.process.stderr:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        stderr_lines.append(text)

        t_out = threading.Thread(target=_read_stdout, daemon=True)
        t_err = threading.Thread(target=_read_stderr, daemon=True)
        t_out.start()
        t_err.start()

        # Store pending hook connections that need responses
        self._pending_hooks: dict[str, socket.socket] = {}

        try:
            # Main event loop — check socket, stdout, and process status
            process_alive = True
            while process_alive or stdout_events:
                process_alive = self.is_alive(handle)

                # Check for hook messages via socket
                try:
                    conn, _ = sock.accept()
                    data = b""
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if b"\n" in data:
                            break

                    if data:
                        msg = json.loads(data.decode().strip())
                        msg_type = msg.get("type", "")
                        tool_call_id = msg.get("tool_call_id", str(uuid.uuid4().hex[:8]))

                        if msg_type == "pre_tool_use":
                            self._pending_hooks[tool_call_id] = conn
                            yield NativeEvent(
                                kind="pre_tool_use",
                                payload={
                                    "tool_name": msg.get("tool_name", "unknown"),
                                    "tool_input": msg.get("tool_input", {}),
                                    "tool_call_id": tool_call_id,
                                },
                            )
                        elif msg_type == "post_tool_use":
                            conn.close()
                            yield NativeEvent(
                                kind="post_tool_use",
                                payload={
                                    "tool_name": msg.get("tool_name", "unknown"),
                                    "tool_call_id": tool_call_id,
                                },
                            )
                        else:
                            conn.close()
                    else:
                        conn.close()
                except socket.timeout:
                    pass
                except OSError:
                    pass

                # Drain stdout events
                with stdout_lock:
                    for evt in stdout_events:
                        yield evt
                    stdout_events.clear()

            # Process exited — wait for IO threads to finish draining
            t_out.join(timeout=3)
            t_err.join(timeout=3)

            # Final stdout drain
            with stdout_lock:
                for evt in stdout_events:
                    yield evt
                stdout_events.clear()

        finally:
            # Clean up pending hooks
            for conn in self._pending_hooks.values():
                try:
                    conn.close()
                except OSError:
                    pass
            self._pending_hooks.clear()
            sock.close()

        # Yield exit event AFTER finally (so it's always the last event)
        if handle.process:
            handle.process.wait(timeout=5)
            returncode = handle.process.returncode
            yield NativeEvent(
                kind="process_exit",
                payload={
                    "returncode": returncode,
                    "stderr_tail": stderr_lines[-10:] if stderr_lines else [],
                },
            )

    def send_control(self, handle: ClaudeCodeHandle, action: ControlAction) -> None:
        """Send a control action to Claude Code."""
        if action.kind == "approve":
            tool_call_id = action.target_id or ""
            conn = self._pending_hooks.pop(tool_call_id, None)
            if conn:
                try:
                    resp = json.dumps({"decision": "allow"}) + "\n"
                    conn.sendall(resp.encode())
                    conn.close()
                except OSError:
                    pass

        elif action.kind == "deny":
            tool_call_id = action.target_id or ""
            reason = action.payload.get("reason", "Blocked by operator")
            conn = self._pending_hooks.pop(tool_call_id, None)
            if conn:
                try:
                    resp = json.dumps({"decision": "deny", "reason": reason}) + "\n"
                    conn.sendall(resp.encode())
                    conn.close()
                except OSError:
                    pass

        elif action.kind == "kill":
            self.shutdown(handle, graceful=False)

        elif action.kind == "send_input":
            if handle.process and handle.process.stdin:
                text = action.payload.get("text", "")
                try:
                    handle.process.stdin.write((text + "\n").encode())
                    handle.process.stdin.flush()
                except OSError:
                    pass

    # No _restore_settings needed — hooks live in an isolated settings file
    # passed via --settings, not in the project's .claude/settings.local.json.

    def _cleanup_hooks_dir(self, handle: ClaudeCodeHandle) -> None:
        """Remove socket and temp hooks directory."""
        if handle.socket_path and os.path.exists(handle.socket_path):
            try:
                os.unlink(handle.socket_path)
            except OSError:
                pass
        if handle.hooks_dir:
            import shutil
            shutil.rmtree(handle.hooks_dir, ignore_errors=True)

    def shutdown(self, handle: ClaudeCodeHandle, graceful: bool = True) -> None:
        """Terminate Claude Code and clean up."""
        if not handle.process:
            return

        if graceful:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                handle.process.kill()
                handle.process.wait(timeout=5)
        else:
            handle.process.kill()
            try:
                handle.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        self._cleanup_hooks_dir(handle)

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        """Map Claude Code native events to canonical event dicts."""
        results: list[dict[str, Any]] = []

        if event.kind == "pre_tool_use":
            results.append({
                "kind": EventKind.TOOL_CALL_PROPOSED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload.get("tool_call_id"),
                "payload": {
                    "tool_name": event.payload.get("tool_name", "unknown"),
                    "tool_input": event.payload.get("tool_input", {}),
                    "tool_call_id": event.payload.get("tool_call_id"),
                },
            })

        elif event.kind == "post_tool_use":
            results.append({
                "kind": EventKind.TOOL_CALL_COMPLETED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload.get("tool_call_id"),
                "payload": {
                    "tool_name": event.payload.get("tool_name", "unknown"),
                    "tool_call_id": event.payload.get("tool_call_id"),
                },
            })

        elif event.kind == "agent_output":
            results.append({
                "kind": "agent_output",
                "source_layer": SourceLayer.ADAPTER,
                "payload": {"text": event.payload.get("text", "")},
            })

        elif event.kind == "process_exit":
            returncode = event.payload.get("returncode")
            if returncode == 0:
                results.append({
                    "kind": EventKind.SESSION_EXITED,
                    "source_layer": SourceLayer.ADAPTER,
                    "payload": event.payload,
                })
            else:
                results.append({
                    "kind": EventKind.SESSION_FAILED,
                    "source_layer": SourceLayer.ADAPTER,
                    "payload": event.payload,
                })

        return results

    def is_alive(self, handle: ClaudeCodeHandle) -> bool:
        """Check if Claude Code is still running."""
        if not handle.process:
            return False
        return handle.process.poll() is None
