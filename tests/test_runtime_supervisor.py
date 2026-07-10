# SPDX-License-Identifier: Apache-2.0
"""Tests for the session supervisor."""

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import pytest

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    LaunchConfig,
    NativeEvent,
)
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.supervisor import (
    InputInjectionError,
    Intervention,
    SessionStatus,
    SessionSupervisor,
)


class MockHandle(BackendHandle):
    """Mock backend handle."""
    alive: bool = True


class MockAdapter:
    """Mock adapter that yields controlled events and records control actions."""

    def __init__(self, events: list[NativeEvent] | None = None):
        self._events = events or []
        self._control_actions: list[ControlAction] = []
        self._launched = False
        self._shutdown = False
        self._handle: MockHandle | None = None

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_native_tool_hooks=True,
            supports_structured_events=True,
            supports_graceful_shutdown=True,
        )

    def launch(self, config: LaunchConfig) -> MockHandle:
        self._launched = True
        self._launch_config = config
        self._handle = MockHandle(pid=12345)
        return self._handle

    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]:
        for evt in self._events:
            yield evt
        # After events exhausted, signal process exit
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        self._control_actions.append(action)

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        self._shutdown = True
        if self._handle:
            self._handle.alive = False

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        if event.kind == "pre_tool_use":
            return [{
                "kind": EventKind.TOOL_CALL_PROPOSED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload.get("tool_call_id"),
                "payload": {
                    "tool_name": event.payload.get("tool_name", "unknown"),
                    "tool_input": event.payload.get("tool_input", {}),
                    "tool_call_id": event.payload.get("tool_call_id"),
                },
            }]
        elif event.kind == "post_tool_use":
            return [{
                "kind": EventKind.TOOL_CALL_COMPLETED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload.get("tool_call_id"),
                "payload": {
                    "tool_name": event.payload.get("tool_name", "unknown"),
                    "tool_call_id": event.payload.get("tool_call_id"),
                },
            }]
        elif event.kind == "process_exit":
            rc = event.payload.get("returncode")
            kind = EventKind.SESSION_EXITED if rc == 0 else EventKind.SESSION_FAILED
            return [{"kind": kind, "source_layer": SourceLayer.ADAPTER, "payload": event.payload}]
        elif event.kind == "agent_output":
            return [{"kind": "agent_output", "source_layer": SourceLayer.ADAPTER,
                      "payload": event.payload}]
        return []

    def is_alive(self, handle: BackendHandle) -> bool:
        if isinstance(handle, MockHandle):
            return handle.alive
        return False


@pytest.fixture
def supervisor(tmp_path):
    return SessionSupervisor(state_dir=tmp_path / "runtime")


class TestSessionLifecycle:
    def test_create_session(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp/project")
        assert record.status == SessionStatus.CREATED
        assert record.backend_kind == "mock"
        assert record.cwd == "/tmp/project"
        assert record.session_id.startswith("sess_")

    def test_create_emits_event(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        events = supervisor.get_events(record.session_id)
        assert len(events) == 1
        assert events[0].kind == EventKind.SESSION_CREATED

    def test_launch_session(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        record = supervisor.launch_session(record.session_id)
        # Should have launched and the event loop will run
        assert adapter._launched
        assert record.pid == 12345
        # Wait for event loop to finish
        time.sleep(0.5)
        # Should be exited since mock adapter yields process_exit(0)
        record = supervisor.get_session(record.session_id)
        assert record.status == SessionStatus.EXITED

    def test_launch_emits_lifecycle_events(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        events = supervisor.get_events(record.session_id)
        kinds = [e.kind for e in events]
        assert EventKind.SESSION_CREATED in kinds
        assert EventKind.SESSION_LAUNCHING in kinds
        assert EventKind.SESSION_ATTACHED in kinds
        assert EventKind.SESSION_RUNNING in kinds
        assert EventKind.SESSION_EXITED in kinds

    def test_list_sessions(self, supervisor):
        adapter1 = MockAdapter()
        adapter2 = MockAdapter()
        supervisor.create_session(adapter1, "mock", "/tmp/a")
        supervisor.create_session(adapter2, "mock", "/tmp/b")
        sessions = supervisor.list_sessions()
        assert len(sessions) == 2

    def test_session_with_task(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp", task="Fix the bug")
        assert record.task == "Fix the bug"
        events = supervisor.get_events(record.session_id)
        assert events[0].payload.get("task") == "Fix the bug"


class TestHarnessArgs:
    """NS-0 (nightshift-functional-mvp): the model pin must survive
    create_session -> LaunchConfig -> adapter argv."""

    def test_harness_args_reach_launch_config(self, tmp_path):
        adapter = MockAdapter()
        sup = SessionSupervisor(state_dir=tmp_path)
        record = sup.create_session(
            adapter=adapter,
            backend_kind="mock",
            cwd=str(tmp_path),
            harness_args=["--model", "claude-haiku-4-5"],
        )
        assert record.harness_args == ["--model", "claude-haiku-4-5"]
        sup.launch_session(record.session_id)
        assert adapter._launch_config.args == ["--model", "claude-haiku-4-5"]

    def test_harness_args_default_empty(self, tmp_path):
        adapter = MockAdapter()
        sup = SessionSupervisor(state_dir=tmp_path)
        record = sup.create_session(
            adapter=adapter, backend_kind="mock", cwd=str(tmp_path)
        )
        assert record.harness_args == []
        sup.launch_session(record.session_id)
        assert adapter._launch_config.args == []


class TestStateTransitions:
    def test_valid_transitions(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        assert record.status == SessionStatus.CREATED

        # Launch transitions through LAUNCHING → ATTACHING → RUNNING
        supervisor.launch_session(record.session_id)
        time.sleep(0.1)
        # May be running or already exited

    def test_pause_resume(self, supervisor):
        adapter = MockAdapter(events=[])  # No events, will just sit
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.1)

        # Session may be running or already exited (mock exits quickly)
        # Test pause/resume on a running session
        record = supervisor.get_session(record.session_id)
        if record.status == SessionStatus.RUNNING:
            supervisor.pause_session(record.session_id)
            record = supervisor.get_session(record.session_id)
            assert record.status == SessionStatus.PAUSED

            supervisor.resume_session(record.session_id)
            record = supervisor.get_session(record.session_id)
            assert record.status == SessionStatus.RUNNING

    def test_kill_session(self, supervisor):
        adapter = MockAdapter(events=[])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.1)

        supervisor.kill_session(record.session_id)
        record = supervisor.get_session(record.session_id)
        # May be FAILED (killed) or EXITED (mock exits before kill arrives)
        assert record.status in (SessionStatus.FAILED, SessionStatus.EXITED)
        assert adapter._shutdown


class TestToolInterception:
    def test_read_tool_auto_approved(self, supervisor):
        """Read-only tools should be auto-approved in interactive mode."""
        adapter = MockAdapter(events=[
            NativeEvent(kind="pre_tool_use", payload={
                "tool_name": "Read",
                "tool_call_id": "tc_001",
                "tool_input": {"path": "/tmp/foo"},
            }),
            NativeEvent(kind="post_tool_use", payload={
                "tool_name": "Read",
                "tool_call_id": "tc_001",
            }),
        ])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        events = supervisor.get_events(record.session_id)
        kinds = [e.kind for e in events]
        assert EventKind.TOOL_CALL_PROPOSED in kinds
        assert EventKind.TOOL_CALL_ALLOWED in kinds
        # Should have been auto-approved (no intervention)
        allowed_events = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED]
        assert allowed_events[0].payload.get("auto") is True

    def test_write_tool_creates_intervention(self, supervisor):
        """Write tools should create an intervention in interactive mode."""
        adapter = MockAdapter(events=[
            NativeEvent(kind="pre_tool_use", payload={
                "tool_name": "Bash",
                "tool_call_id": "tc_001",
                "tool_input": {"command": "rm -rf /"},
            }),
        ])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.3)

        # Should have a pending intervention
        interventions = supervisor.get_pending_interventions(record.session_id)
        assert len(interventions) == 1
        assert interventions[0].tool_name == "Bash"
        assert interventions[0].tool_call_id == "tc_001"

    def test_resolve_intervention_approve(self, supervisor):
        """Approving an intervention should send approve to adapter."""
        adapter = MockAdapter(events=[
            NativeEvent(kind="pre_tool_use", payload={
                "tool_name": "Write",
                "tool_call_id": "tc_001",
                "tool_input": {"path": "/tmp/foo"},
            }),
        ])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.3)

        result = supervisor.resolve_intervention(record.session_id, "tc_001", "approve")
        assert result is not None
        assert result.decision == "approve"

        # Adapter should have received approve
        approves = [a for a in adapter._control_actions if a.kind == "approve"]
        assert len(approves) >= 1
        assert approves[0].target_id == "tc_001"

    def test_resolve_intervention_deny(self, supervisor):
        """Denying an intervention should send deny to adapter."""
        adapter = MockAdapter(events=[
            NativeEvent(kind="pre_tool_use", payload={
                "tool_name": "Edit",
                "tool_call_id": "tc_001",
                "tool_input": {},
            }),
        ])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.3)

        result = supervisor.resolve_intervention(record.session_id, "tc_001", "deny", reason="Too dangerous")
        assert result is not None
        assert result.decision == "deny"
        assert result.reason == "Too dangerous"

        denies = [a for a in adapter._control_actions if a.kind == "deny"]
        assert len(denies) >= 1

    def test_resolve_nonexistent_intervention(self, supervisor):
        """Resolving a nonexistent intervention returns None."""
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        result = supervisor.resolve_intervention(record.session_id, "tc_nonexistent", "approve")
        assert result is None


class TestIntervention:
    def test_intervention_timing(self):
        i = Intervention(
            intervention_id="int_1",
            tool_call_id="tc_1",
            tool_name="Bash",
            tool_input={},
            event_id="evt_1",
            created_at=time.monotonic(),
            timeout_seconds=10.0,
        )
        assert i.elapsed < 1.0
        assert i.remaining > 9.0
        assert not i.timed_out

    def test_intervention_timeout(self):
        i = Intervention(
            intervention_id="int_1",
            tool_call_id="tc_1",
            tool_name="Bash",
            tool_input={},
            event_id="evt_1",
            created_at=time.monotonic() - 100,  # Created 100s ago
            timeout_seconds=10.0,
        )
        assert i.timed_out
        assert i.remaining == 0.0


class TestEventRetrieval:
    def test_get_events_empty(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        events = supervisor.get_events(record.session_id, since_seq=999)
        assert events == []

    def test_get_events_with_cursor(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        all_events = supervisor.get_events(record.session_id, since_seq=0)
        assert len(all_events) > 0

        # Get only later events
        mid_seq = len(all_events) // 2
        later = supervisor.get_events(record.session_id, since_seq=mid_seq)
        assert len(later) < len(all_events)
        assert all(e.seq >= mid_seq for e in later)

    def test_get_pending_interventions_empty(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        assert supervisor.get_pending_interventions(record.session_id) == []

    def test_get_nonexistent_session(self, supervisor):
        assert supervisor.get_session("nonexistent") is None


class TestOnEventCallback:
    def test_callback_receives_events(self, tmp_path):
        received = []
        supervisor = SessionSupervisor(
            state_dir=tmp_path / "runtime",
            on_event=lambda e: received.append(e),
        )
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        # Should have received events via callback
        assert len(received) > 0
        kinds = [e.kind for e in received]
        assert EventKind.SESSION_EXITED in kinds or EventKind.SESSION_FAILED in kinds

    def test_callback_error_does_not_crash(self, tmp_path):
        def bad_callback(e):
            raise RuntimeError("callback exploded")

        supervisor = SessionSupervisor(
            state_dir=tmp_path / "runtime",
            on_event=bad_callback,
        )
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        # Session should still complete despite callback errors
        record = supervisor.get_session(record.session_id)
        assert record.status in (SessionStatus.EXITED, SessionStatus.FAILED)


class TestSendInput:
    """Operator input injection (GS-5) — fail-closed at every gate."""

    def _running_input_session(self, supervisor, *, input_capable: bool):
        """Create a session and force it into a RUNNING, handle-attached state
        without spinning the real event loop (which exits immediately)."""
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp/proj")
        facet = supervisor._get_facet(record.session_id)
        facet.handle = MockHandle(pid=999)
        facet.capabilities = AdapterCapabilities(
            supports_input_injection=input_capable,
        )
        record.status = SessionStatus.RUNNING  # bypass FSM for the gate under test
        return adapter, record

    def test_empty_text_refused_before_lookup(self, supervisor):
        # The text gate fires first — no session needs to exist.
        with pytest.raises(InputInjectionError):
            supervisor.send_input("sess_nonexistent", "   ")

    def test_no_such_session_is_input_error_not_keyerror(self, supervisor):
        # Contract: a missing session surfaces as InputInjectionError (which the
        # daemon catches), never a raw KeyError.
        with pytest.raises(InputInjectionError, match="no such session"):
            supervisor.send_input("sess_does_not_exist", "hello")

    def test_no_handle_refused(self, supervisor):
        adapter = MockAdapter()
        record = supervisor.create_session(adapter, "mock", "/tmp")
        # Created, never launched -> no live handle.
        with pytest.raises(InputInjectionError, match="no live backend handle"):
            supervisor.send_input(record.session_id, "hello")

    def test_not_running_refused(self, supervisor):
        adapter, record = self._running_input_session(supervisor, input_capable=True)
        record.status = SessionStatus.PAUSED
        with pytest.raises(InputInjectionError, match="not running"):
            supervisor.send_input(record.session_id, "hello")

    def test_unsupported_backend_refused(self, supervisor):
        adapter, record = self._running_input_session(supervisor, input_capable=False)
        with pytest.raises(InputInjectionError, match="does not support input injection"):
            supervisor.send_input(record.session_id, "hello")
        # Fail-closed: nothing was sent to the backend.
        assert not any(a.kind == "send_input" for a in adapter._control_actions)

    def test_success_sends_control_and_emits_event(self, supervisor):
        adapter, record = self._running_input_session(supervisor, input_capable=True)
        supervisor.send_input(record.session_id, "run the tests")

        sends = [a for a in adapter._control_actions if a.kind == "send_input"]
        assert len(sends) == 1
        assert sends[0].payload["text"] == "run the tests"

        events = supervisor.get_events(record.session_id)
        inputs = [e for e in events if e.kind == EventKind.OPERATOR_INPUT]
        assert len(inputs) == 1
        assert inputs[0].source_layer == SourceLayer.OPERATOR
        assert inputs[0].payload["text"] == "run the tests"
        assert inputs[0].payload["chars"] == len("run the tests")


class TestGrantUseCompression:
    """S2b — approval compression at the supervisor gate. Within-grant
    WRITE/COMMUNICATE calls auto-approve silently + receipt the use; widening
    and unverifiable calls still prompt (annotated with why); no grant =
    unchanged interactive behavior. Compression only ever REMOVES a prompt for
    an in-envelope call — never approves a would-be-denied one."""

    def _grant(self):
        from governor.runtime.execution_grant import (
            ExecutionRequest,
            activate_execution_grant,
        )
        from governor.runtime.grant_use_gate import CommandGrant
        return activate_execution_grant(ExecutionRequest(
            write_paths=frozenset({"/tmp/**"}),
            commands=(CommandGrant("cargo", ("test",)),),
            source_plan_digest="sha256:p", approval_witness_digest="sha256:w",
        ))

    def _fire(self, supervisor, tool_name, tool_input, grant):
        adapter = MockAdapter(events=[
            NativeEvent(kind="pre_tool_use", payload={
                "tool_name": tool_name, "tool_call_id": "tc_001", "tool_input": tool_input,
            }),
        ])
        record = supervisor.create_session(adapter, "mock", "/tmp")
        if grant is not None:
            supervisor.attach_execution_grant(record.session_id, grant)
        supervisor.launch_session(record.session_id)
        time.sleep(0.3)
        return adapter, record

    def _prompt_payload(self, supervisor, session_id):
        prompted = [e for e in supervisor.get_events(session_id)
                    if e.kind == EventKind.OPERATOR_PROMPTED]
        assert prompted, "expected an operator prompt"
        return prompted[-1].payload

    def test_within_grant_command_auto_approves_no_prompt(self, supervisor):
        adapter, record = self._fire(supervisor, "Bash", {"command": "cargo test --lib"}, self._grant())
        assert supervisor.get_pending_interventions(record.session_id) == []
        approves = [a for a in adapter._control_actions
                    if a.kind == "approve" and a.target_id == "tc_001"]
        assert len(approves) == 1
        allowed = [e for e in supervisor.get_events(record.session_id)
                   if e.kind == EventKind.TOOL_CALL_ALLOWED]
        assert allowed and allowed[-1].payload.get("grant_use") == "accepted"
        assert allowed[-1].payload.get("grant_id", "").startswith("sgr_")

    def test_within_grant_write_path_auto_approves(self, supervisor):
        adapter, record = self._fire(supervisor, "Edit", {"file_path": "/tmp/foo.txt"}, self._grant())
        assert supervisor.get_pending_interventions(record.session_id) == []
        assert any(a.kind == "approve" for a in adapter._control_actions)

    def test_widening_command_still_prompts_annotated(self, supervisor):
        adapter, record = self._fire(supervisor, "Bash", {"command": "cargo publish"}, self._grant())
        assert len(supervisor.get_pending_interventions(record.session_id)) == 1
        gu = self._prompt_payload(supervisor, record.session_id).get("grant_use")
        assert gu and gu["disposition"] == "widens" and gu["axis"] == "shell"

    def test_opaque_shell_fails_closed_to_prompt(self, supervisor):
        adapter, record = self._fire(supervisor, "Bash", {"command": "cargo test; rm -rf /"}, self._grant())
        assert len(supervisor.get_pending_interventions(record.session_id)) == 1
        gu = self._prompt_payload(supervisor, record.session_id).get("grant_use")
        assert gu and gu["disposition"] == "unverifiable"

    def test_write_outside_grant_still_prompts(self, supervisor):
        adapter, record = self._fire(supervisor, "Edit", {"file_path": "/etc/passwd"}, self._grant())
        assert len(supervisor.get_pending_interventions(record.session_id)) == 1
        gu = self._prompt_payload(supervisor, record.session_id).get("grant_use")
        assert gu and gu["disposition"] == "widens" and gu["axis"] == "write_path"

    def test_no_grant_is_unchanged_interactive_prompt(self, supervisor):
        adapter, record = self._fire(supervisor, "Bash", {"command": "cargo test"}, None)
        assert len(supervisor.get_pending_interventions(record.session_id)) == 1
        assert "grant_use" not in self._prompt_payload(supervisor, record.session_id)
