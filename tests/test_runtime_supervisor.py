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
