# SPDX-License-Identifier: Apache-2.0
"""Gemini CLI runtime adapter for supervised sessions.

Supervised mode: Governor launches Gemini CLI as a managed child process.
Hook scripts communicate with the supervisor via Unix domain socket.

Gemini CLI uses BeforeTool/AfterTool hooks (vs Claude's PreToolUse/PostToolUse).
Blocking is via exit code 2 + stderr reason (vs Claude's JSON output).
"""

from __future__ import annotations

import json
import os
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


# Gemini BeforeTool hook: connect to supervisor, get decision.
# Exit code 0 = allow, exit code 2 = block (stderr = reason).
_SUPERVISED_BEFORE_TOOL_SCRIPT = '''\
#!/usr/bin/env python3
"""Governor supervised BeforeTool hook for Gemini CLI."""
import json
import os
import socket
import sys

def main():
    sock_path = os.environ.get("GOVERNOR_SUPERVISOR_SOCKET")
    if not sock_path:
        sys.exit(0)  # No supervisor, allow

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "unknown")
    tool_input = data.get("tool_input", data.get("input", {}))

    msg = json.dumps({
        "type": "before_tool",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_call_id": data.get("tool_use_id", data.get("id", "")),
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
            # Gemini CLI: exit code 2 = system block, stderr = reason
            print(reason, file=sys.stderr)
            sys.exit(2)
    except Exception:
        pass  # Socket error = allow (fail-open)

if __name__ == "__main__":
    main()
'''

_SUPERVISED_AFTER_TOOL_SCRIPT = '''\
#!/usr/bin/env python3
"""Governor supervised AfterTool hook for Gemini CLI."""
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
        "type": "after_tool",
        "tool_name": data.get("tool_name", "unknown"),
        "tool_call_id": data.get("tool_use_id", data.get("id", "")),
        "session_id": os.environ.get("GOVERNOR_SESSION_ID", ""),
    }) + "\\n"

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(sock_path)
        s.sendall(msg.encode())
        s.close()
    except Exception:
        pass

if __name__ == "__main__":
    main()
'''


@dataclass
class GeminiCliHandle(BackendHandle):
    """Handle to a running Gemini CLI process."""

    process: subprocess.Popen | None = None
    socket_path: str | None = None
    hooks_dir: str | None = None
    listener_socket: socket.socket | None = None


class GeminiCliAdapter:
    """Runtime adapter for Gemini CLI in supervised mode."""

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_pause=False,
            supports_resume=False,
            supports_native_tool_hooks=True,
            supports_structured_events=True,
            supports_input_injection=False,  # Gemini headless doesn't take stdin after launch
            supports_graceful_shutdown=True,
        )

    def launch(self, config: LaunchConfig) -> GeminiCliHandle:
        """Launch Gemini CLI as a managed child process."""
        cwd = Path(config.cwd)

        # Create temp dir for hook scripts and socket
        hooks_dir = Path(tempfile.mkdtemp(prefix="gov_hooks_"))
        socket_path = str(hooks_dir / "supervisor.sock")

        # Write hook scripts
        before_hook = hooks_dir / "before_tool.py"
        before_hook.write_text(_SUPERVISED_BEFORE_TOOL_SCRIPT)
        before_hook.chmod(before_hook.stat().st_mode | stat.S_IXUSR)

        after_hook = hooks_dir / "after_tool.py"
        after_hook.write_text(_SUPERVISED_AFTER_TOOL_SCRIPT)
        after_hook.chmod(after_hook.stat().st_mode | stat.S_IXUSR)

        # Build isolated settings for Gemini CLI via --policy or settings
        # Gemini hooks go in .gemini/settings.json or passed via env
        # For isolation, write a settings file in the hooks dir
        gemini_settings = {
            "hooks": {
                "BeforeTool": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"python3 {before_hook}",
                                "timeout": 30,
                            }
                        ],
                    }
                ],
                "AfterTool": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"python3 {after_hook}",
                                "timeout": 5,
                            }
                        ],
                    }
                ],
            },
        }

        settings_file = hooks_dir / "gemini_settings.json"
        settings_file.write_text(json.dumps(gemini_settings, indent=2))

        # Create and bind listener socket BEFORE starting Gemini
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.settimeout(1.0)
        listener.bind(socket_path)
        listener.listen(5)

        # Build env
        env = {**os.environ, **config.env}
        env["GOVERNOR_SUPERVISOR_SOCKET"] = socket_path
        env["GOVERNOR_SESSION_ID"] = config.session_id

        # Build gemini command
        # --approval-mode yolo: auto-approve (governor hooks handle gating)
        # --output-format text: plain text output
        cmd = ["gemini", "--approval-mode", "yolo"]
        if config.args:
            cmd.extend(config.args)

        # Gemini uses --prompt for headless mode
        if config.task:
            cmd.extend(["--prompt", config.task])

        # Point to our isolated settings
        # Gemini reads settings from .gemini/settings.json in the project dir
        # We can also use GEMINI_CLI_SYSTEM_SETTINGS_PATH env var
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(settings_file)

        process = subprocess.Popen(
            cmd,
            cwd=config.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Close stdin for headless mode
        if config.task and process.stdin:
            process.stdin.close()

        return GeminiCliHandle(
            pid=process.pid,
            native_session_ref=config.session_id,
            process=process,
            socket_path=socket_path,
            hooks_dir=str(hooks_dir),
            listener_socket=listener,
        )

    def iter_events(self, handle: GeminiCliHandle) -> Iterable[NativeEvent]:
        """Yield native events from the Gemini CLI process."""
        if not handle.socket_path:
            return

        sock = handle.listener_socket
        if not sock:
            return

        stdout_events: list[NativeEvent] = []
        stderr_lines: list[str] = []
        stdout_lock = threading.Lock()

        def _read_stdout():
            if handle.process and handle.process.stdout:
                for line in handle.process.stdout:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text and not text.startswith("[WARN]") and not text.startswith("Loaded cached"):
                        with stdout_lock:
                            stdout_events.append(
                                NativeEvent(kind="agent_output", payload={"text": text})
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

        self._pending_hooks: dict[str, socket.socket] = {}

        try:
            process_alive = True
            while process_alive or stdout_events:
                process_alive = self.is_alive(handle)

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

                        if msg_type == "before_tool":
                            self._pending_hooks[tool_call_id] = conn
                            yield NativeEvent(
                                kind="before_tool",
                                payload={
                                    "tool_name": msg.get("tool_name", "unknown"),
                                    "tool_input": msg.get("tool_input", {}),
                                    "tool_call_id": tool_call_id,
                                },
                            )
                        elif msg_type == "after_tool":
                            conn.close()
                            yield NativeEvent(
                                kind="after_tool",
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

                with stdout_lock:
                    for evt in stdout_events:
                        yield evt
                    stdout_events.clear()

            t_out.join(timeout=3)
            t_err.join(timeout=3)

            with stdout_lock:
                for evt in stdout_events:
                    yield evt
                stdout_events.clear()

        finally:
            for conn in self._pending_hooks.values():
                try:
                    conn.close()
                except OSError:
                    pass
            self._pending_hooks.clear()
            sock.close()

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

    def send_control(self, handle: GeminiCliHandle, action: ControlAction) -> None:
        """Send a control action to Gemini CLI."""
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

    def shutdown(self, handle: GeminiCliHandle, graceful: bool = True) -> None:
        """Terminate Gemini CLI."""
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

    def _cleanup_hooks_dir(self, handle: GeminiCliHandle) -> None:
        if handle.socket_path and os.path.exists(handle.socket_path):
            try:
                os.unlink(handle.socket_path)
            except OSError:
                pass
        if handle.hooks_dir:
            import shutil
            shutil.rmtree(handle.hooks_dir, ignore_errors=True)

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        """Map Gemini CLI native events to canonical event dicts."""
        results: list[dict[str, Any]] = []

        if event.kind == "before_tool":
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
        elif event.kind == "after_tool":
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

    def is_alive(self, handle: GeminiCliHandle) -> bool:
        if not handle.process:
            return False
        return handle.process.poll() is None
