# SPDX-License-Identifier: Apache-2.0
"""Tock 1: the supervised pre-tool gate fails closed.

Forcing gap: GAP-A (working/tick-01-nq-masthead.md) — the pre-tool hook
abandoned its supervisor wait after a hardcoded 30s and ALLOWED, making
the write gate advisory whenever the operator was slower than 30 seconds
or absent entirely.

These tests execute the real hook script as a subprocess against real
Unix sockets. Acceptance criteria:

1. Decision timeout → deny, with explicit reason.
2. Supervisor socket error / unavailable → deny, with explicit reason.
3. Wait duration derives from the supervisor's intervention timeout
   (threaded via GOVERNOR_DECISION_TIMEOUT), not a hardcoded 30s.
4. Timeout denial is recorded in the event ledger (supervisor side).
5. The agent receives a denial result, not silence.
6. Existing allow/deny flow still works.
"""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import pytest

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    LaunchConfig,
    NativeEvent,
)
from governor.runtime.adapters.claude_code import (
    _SUPERVISED_PRE_TOOL_SCRIPT,
    DEFAULT_DECISION_TIMEOUT,
    HOOK_WAIT_GRACE,
    build_isolated_settings,
)
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.supervisor import SessionStatus, SessionSupervisor

HOOK_STDIN = json.dumps({
    "tool_name": "Write",
    "tool_input": {"file_path": "/tmp/x", "content": "y"},
    "tool_use_id": "tc_failclosed_001",
})


@pytest.fixture()
def sock_dir():
    """Temp dir with a short path for AF_UNIX binds.

    pytest's ``tmp_path`` on macOS lives under ``/private/var/folders/.../
    pytest-of-<user>/pytest-N/<test-name>0/``, which overruns the 104-byte
    ``sun_path`` limit and raises ``OSError: AF_UNIX path too long`` at bind
    time. Same fixture shape as ``short_tmp`` in tests/test_cli_backend.py.
    """
    d = tempfile.mkdtemp(prefix="gov_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def run_hook(tmp_path: Path, env: dict[str, str], stdin: str = HOOK_STDIN,
             timeout: float = 15.0) -> subprocess.CompletedProcess:
    script = tmp_path / "pre_tool_use.py"
    script.write_text(_SUPERVISED_PRE_TOOL_SCRIPT)
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin.encode(),
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", **env},
        timeout=timeout,
    )


def parse_decision(proc: subprocess.CompletedProcess) -> dict | None:
    """Return the hookSpecificOutput dict, or None for silent allow."""
    out = proc.stdout.decode().strip()
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]


class ReplyServer:
    """One-shot Unix socket server with a scripted reply behavior."""

    def __init__(self, sock_path: Path, reply: bytes | None):
        self.sock_path = str(sock_path)
        self.reply = reply  # None = accept, read, never respond
        self.received: bytes = b""
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(self.sock_path)
        self._listener.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self._listener.accept()
            conn.settimeout(10)
            while b"\n" not in self.received:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                self.received += chunk
            if self.reply is not None:
                conn.sendall(self.reply)
                conn.close()
            else:
                # Hold the connection open silently until the hook gives up.
                time.sleep(10)
                conn.close()
        except OSError:
            pass
        finally:
            self._listener.close()


class TestFailClosedPaths:
    """Acceptance 1, 2, 5: every failure path denies with a reason."""

    def test_deny_on_missing_socket_env(self, tmp_path):
        proc = run_hook(tmp_path, env={})
        decision = parse_decision(proc)
        assert decision is not None, "missing supervisor config must not be a silent allow"
        assert decision["permissionDecision"] == "deny"
        assert "failing closed" in decision["permissionDecisionReason"]

    def test_deny_on_unreachable_socket(self, tmp_path):
        proc = run_hook(tmp_path, env={
            "GOVERNOR_SUPERVISOR_SOCKET": str(tmp_path / "nonexistent.sock"),
        })
        decision = parse_decision(proc)
        assert decision is not None, "unreachable supervisor must not be a silent allow"
        assert decision["permissionDecision"] == "deny"
        assert "unreachable" in decision["permissionDecisionReason"]

    def test_deny_on_decision_timeout(self, tmp_path, sock_dir):
        sock = sock_dir / "supervisor.sock"
        ReplyServer(sock, reply=None)  # accepts, never answers
        start = time.monotonic()
        proc = run_hook(tmp_path, env={
            "GOVERNOR_SUPERVISOR_SOCKET": str(sock),
            "GOVERNOR_DECISION_TIMEOUT": "0.5",
            "GOVERNOR_HOOK_WAIT_GRACE": "0.5",
        })
        elapsed = time.monotonic() - start
        decision = parse_decision(proc)
        assert decision is not None, "decision timeout must not be a silent allow"
        assert decision["permissionDecision"] == "deny"
        assert "no supervisor decision" in decision["permissionDecisionReason"]
        assert elapsed < 8, "hook must honor the configured wait, not a hardcoded 30s"

    def test_deny_on_garbage_response(self, tmp_path, sock_dir):
        sock = sock_dir / "supervisor.sock"
        ReplyServer(sock, reply=b"not json at all\n")
        proc = run_hook(tmp_path, env={"GOVERNOR_SUPERVISOR_SOCKET": str(sock)})
        decision = parse_decision(proc)
        assert decision is not None and decision["permissionDecision"] == "deny"

    def test_deny_on_unrecognized_decision(self, tmp_path, sock_dir):
        sock = sock_dir / "supervisor.sock"
        ReplyServer(sock, reply=json.dumps({"decision": "maybe"}).encode() + b"\n")
        proc = run_hook(tmp_path, env={"GOVERNOR_SUPERVISOR_SOCKET": str(sock)})
        decision = parse_decision(proc)
        assert decision is not None and decision["permissionDecision"] == "deny"
        assert "unrecognized" in decision["permissionDecisionReason"]

    def test_deny_on_malformed_stdin(self, tmp_path):
        sock = tmp_path / "supervisor.sock"
        proc = run_hook(tmp_path, stdin="not json",
                        env={"GOVERNOR_SUPERVISOR_SOCKET": str(sock)})
        decision = parse_decision(proc)
        assert decision is not None and decision["permissionDecision"] == "deny"


class TestExistingFlowStillWorks:
    """Acceptance 6: allow and explicit deny are unchanged."""

    def test_allow_response_is_silent_allow(self, tmp_path, sock_dir):
        sock = sock_dir / "supervisor.sock"
        server = ReplyServer(sock, reply=json.dumps({"decision": "allow"}).encode() + b"\n")
        proc = run_hook(tmp_path, env={"GOVERNOR_SUPERVISOR_SOCKET": str(sock)})
        assert proc.returncode == 0
        assert parse_decision(proc) is None, "allow must remain silent (no hook output)"
        sent = json.loads(server.received.decode().strip())
        assert sent["tool_name"] == "Write"
        assert sent["tool_call_id"] == "tc_failclosed_001"

    def test_deny_response_carries_operator_reason(self, tmp_path, sock_dir):
        sock = sock_dir / "supervisor.sock"
        ReplyServer(sock, reply=json.dumps(
            {"decision": "deny", "reason": "out of scope fence"}).encode() + b"\n")
        proc = run_hook(tmp_path, env={"GOVERNOR_SUPERVISOR_SOCKET": str(sock)})
        decision = parse_decision(proc)
        assert decision is not None and decision["permissionDecision"] == "deny"
        assert decision["permissionDecisionReason"] == "out of scope fence"


class TestTimeoutAlignment:
    """Acceptance 3: the wait derives from the intervention timeout."""

    def test_settings_hook_timeout_covers_decision_window(self, tmp_path):
        settings = build_isolated_settings(
            tmp_path / "pre.py", tmp_path / "post.py", decision_timeout=300.0)
        hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
        # Claude Code kills the hook at this timeout and PROCEEDS (its hook
        # timeout is a non-blocking error) — so it must sit strictly behind
        # the script's own deny deadline (decision window + grace).
        assert hook["timeout"] > 300.0 + HOOK_WAIT_GRACE
        post = settings["hooks"]["PostToolUse"][0]["hooks"][0]
        assert post["timeout"] == 5, "observe-only post hook unchanged"

    def test_script_defaults_match_module_constants(self):
        assert f'"GOVERNOR_DECISION_TIMEOUT", {DEFAULT_DECISION_TIMEOUT}' in (
            _SUPERVISED_PRE_TOOL_SCRIPT
        )
        assert f'"GOVERNOR_HOOK_WAIT_GRACE", {HOOK_WAIT_GRACE}' in (
            _SUPERVISED_PRE_TOOL_SCRIPT
        )

    def test_supervisor_threads_decision_timeout_into_launch_env(self, tmp_path):
        captured: dict[str, Any] = {}

        class RecordingAdapter:
            def capabilities(self):
                return AdapterCapabilities()

            def launch(self, config: LaunchConfig) -> BackendHandle:
                captured["env"] = config.env
                return BackendHandle(pid=4242)

            def iter_events(self, handle) -> Iterable[NativeEvent]:
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})

            def send_control(self, handle, action: ControlAction) -> None:
                pass

            def shutdown(self, handle, graceful: bool = True) -> None:
                pass

            def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
                return [{"kind": EventKind.SESSION_EXITED,
                         "source_layer": SourceLayer.ADAPTER,
                         "payload": event.payload}]

            def is_alive(self, handle) -> bool:
                return False

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime",
                                       default_timeout=123.0)
        record = supervisor.create_session(
            RecordingAdapter(), "claude_code", str(tmp_path), task="t",
            operator_mode="interactive")
        supervisor.launch_session(record.session_id)
        assert float(captured["env"]["GOVERNOR_DECISION_TIMEOUT"]) == 123.0


class DenialWitnessAdapter:
    """Proposes one Write, waits for the supervisor's decision, exits."""

    def __init__(self):
        self.decisions: list[ControlAction] = []
        self._resolved = threading.Event()

    def capabilities(self):
        return AdapterCapabilities(supports_native_tool_hooks=True)

    def launch(self, config: LaunchConfig) -> BackendHandle:
        return BackendHandle(pid=4243)

    def iter_events(self, handle) -> Iterable[NativeEvent]:
        yield NativeEvent(kind="pre_tool_use", payload={
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/x"},
            "tool_call_id": "tc_timeout_001",
        })
        self._resolved.wait(timeout=10)
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, handle, action: ControlAction) -> None:
        self.decisions.append(action)
        if action.kind in ("approve", "deny"):
            self._resolved.set()

    def shutdown(self, handle, graceful: bool = True) -> None:
        self._resolved.set()

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        if event.kind == "pre_tool_use":
            return [{"kind": EventKind.TOOL_CALL_PROPOSED,
                     "source_layer": SourceLayer.ADAPTER,
                     "tool_call_id": event.payload["tool_call_id"],
                     "payload": event.payload}]
        return [{"kind": EventKind.SESSION_EXITED,
                 "source_layer": SourceLayer.ADAPTER,
                 "payload": event.payload}]

    def is_alive(self, handle) -> bool:
        return not self._resolved.is_set()


class TestTimeoutDenialLedger:
    """Acceptance 4 + 5, supervisor side: an unanswered intervention is
    auto-denied at the decision window, the denial reaches the backend
    via send_control, and the event ledger records it."""

    def test_intervention_timeout_denies_and_is_ledgered(self, tmp_path):
        adapter = DenialWitnessAdapter()
        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime",
                                       default_timeout=0.7)
        record = supervisor.create_session(
            adapter, "claude_code", str(tmp_path), task="t",
            operator_mode="interactive")
        supervisor.launch_session(record.session_id)

        # Operator never answers. Wait for the timeout watcher.
        for _ in range(80):
            time.sleep(0.1)
            rec = supervisor.get_session(record.session_id)
            if rec.status in (SessionStatus.EXITED, SessionStatus.FAILED):
                break

        denies = [a for a in adapter.decisions if a.kind == "deny"]
        assert denies, "backend must receive an explicit deny, not silence"
        assert denies[0].payload.get("reason") == "Intervention timeout"

        events = supervisor.get_events(record.session_id)
        denied = [e for e in events if e.kind == EventKind.TOOL_CALL_DENIED]
        assert denied, "timeout denial must be recorded in the event ledger"
        assert denied[0].payload.get("tool_call_id") == "tc_timeout_001"
