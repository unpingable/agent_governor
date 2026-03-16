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


# Hook script template for supervised mode.
# Connects to supervisor socket, sends tool info, waits for decision.
_SUPERVISED_PRE_TOOL_SCRIPT = '''\
#!/usr/bin/env python3
"""Governor supervised pre-tool hook. Talks to supervisor socket."""
import json
import os
import socket
import sys

def main():
    sock_path = os.environ.get("GOVERNOR_SUPERVISOR_SOCKET")
    if not sock_path:
        return  # No supervisor, allow by default

    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # Can't parse, allow

    tool_name = data.get("tool_name", "unknown")
    tool_input = data.get("tool_input", {})

    msg = json.dumps({
        "type": "pre_tool_use",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_call_id": data.get("tool_use_id", ""),
        "session_id": os.environ.get("GOVERNOR_SESSION_ID", ""),
    }) + "\\n"

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(30)
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
        decision = result.get("decision", "allow")
        if decision == "deny":
            reason = result.get("reason", "Blocked by governor")
            print(json.dumps({"decision": "block", "reason": reason}))
            sys.exit(0)
        # allow — print nothing, exit 0
    except Exception:
        pass  # Socket error = allow (fail-open for hooks, fail-closed for policy)

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


@dataclass
class ClaudeCodeHandle(BackendHandle):
    """Handle to a running Claude Code process."""

    process: subprocess.Popen | None = None
    socket_path: str | None = None
    hooks_dir: str | None = None


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
        """Launch Claude Code as a managed child process."""
        # Create temp dir for hook scripts and socket
        hooks_dir = Path(tempfile.mkdtemp(prefix="gov_hooks_"))
        socket_path = str(hooks_dir / "supervisor.sock")

        # Write hook scripts
        pre_hook = hooks_dir / "pre_tool_use.py"
        pre_hook.write_text(_SUPERVISED_PRE_TOOL_SCRIPT)
        pre_hook.chmod(pre_hook.stat().st_mode | stat.S_IXUSR)

        post_hook = hooks_dir / "post_tool_use.py"
        post_hook.write_text(_SUPERVISED_POST_TOOL_SCRIPT)
        post_hook.chmod(post_hook.stat().st_mode | stat.S_IXUSR)

        # Generate Claude settings with hooks pointing to our scripts
        settings = {
            "hooks": {
                "preToolUse": [
                    {
                        "type": "command",
                        "command": f"python3 {pre_hook}",
                        "timeout": 30000,
                    }
                ],
                "postToolUse": [
                    {
                        "type": "command",
                        "command": f"python3 {post_hook}",
                        "timeout": 5000,
                    }
                ],
            }
        }

        # Write settings to a temp location
        settings_file = hooks_dir / "settings.json"
        settings_file.write_text(json.dumps(settings, indent=2))

        # Build env for child process
        env = {**os.environ, **config.env}
        env["GOVERNOR_SUPERVISOR_SOCKET"] = socket_path
        env["GOVERNOR_SESSION_ID"] = config.session_id

        # Build claude command
        cmd = ["claude"]
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

        return ClaudeCodeHandle(
            pid=process.pid,
            native_session_ref=config.session_id,
            process=process,
            socket_path=socket_path,
            hooks_dir=str(hooks_dir),
        )

    def iter_events(self, handle: ClaudeCodeHandle) -> Iterable[NativeEvent]:
        """Yield native events from the Claude Code process.

        Listens on the supervisor socket for hook messages and
        monitors stdout/stderr for agent output.
        """
        if not handle.socket_path:
            return

        # Create and bind the Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)  # Non-blocking-ish for polling
        try:
            sock.bind(handle.socket_path)
        except OSError:
            # Socket already exists (shouldn't happen with tempdir)
            os.unlink(handle.socket_path)
            sock.bind(handle.socket_path)
        sock.listen(5)

        # Also monitor process stdout in a thread
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
            while self.is_alive(handle):
                # Check for hook messages
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
                            # Store connection for response
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

        finally:
            # Clean up pending hooks
            for conn in self._pending_hooks.values():
                try:
                    conn.close()
                except OSError:
                    pass
            self._pending_hooks.clear()
            sock.close()

            # Yield exit event
            if handle.process:
                returncode = handle.process.poll()
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

    def shutdown(self, handle: ClaudeCodeHandle, graceful: bool = True) -> None:
        """Terminate Claude Code."""
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

        # Clean up socket and hooks dir
        if handle.socket_path and os.path.exists(handle.socket_path):
            os.unlink(handle.socket_path)
        if handle.hooks_dir:
            import shutil

            shutil.rmtree(handle.hooks_dir, ignore_errors=True)

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
