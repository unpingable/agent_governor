# SPDX-License-Identifier: Apache-2.0
"""Golden trace test for supervised session event streams.

Validates that a supervised session with one tool intervention produces
the expected canonical event sequence. This is the dogfood-verified
proof path from 2026-03-16.
"""

import json
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
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.supervisor import SessionStatus, SessionSupervisor

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "runtime" / "golden_supervised_session.json"


class ToolUseAdapter:
    """Mock adapter that simulates one Bash tool call then exits."""

    def __init__(self):
        self._control_actions: list[ControlAction] = []
        self._approved = False

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_native_tool_hooks=True,
            supports_structured_events=True,
            supports_graceful_shutdown=True,
        )

    def launch(self, config: LaunchConfig) -> BackendHandle:
        return BackendHandle(pid=99999)

    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]:
        # 1. Propose a Bash tool call
        yield NativeEvent(
            kind="pre_tool_use",
            payload={
                "tool_name": "Bash",
                "tool_input": {"command": "echo hello"},
                "tool_call_id": "tc_golden_001",
            },
        )

        # 2. Wait for approval (supervisor will call send_control)
        for _ in range(100):
            if self._approved:
                break
            time.sleep(0.05)

        # 3. Post-tool completion
        yield NativeEvent(
            kind="post_tool_use",
            payload={
                "tool_name": "Bash",
                "tool_call_id": "tc_golden_001",
            },
        )

        # 4. Agent output
        yield NativeEvent(
            kind="agent_output",
            payload={"text": "Done."},
        )

        # 5. Clean exit
        yield NativeEvent(
            kind="process_exit",
            payload={"returncode": 0},
        )

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        self._control_actions.append(action)
        if action.kind == "approve":
            self._approved = True

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        pass

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        if event.kind == "pre_tool_use":
            return [{
                "kind": EventKind.TOOL_CALL_PROPOSED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload.get("tool_call_id"),
                "payload": {
                    "tool_name": event.payload.get("tool_name"),
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
                    "tool_name": event.payload.get("tool_name"),
                    "tool_call_id": event.payload.get("tool_call_id"),
                },
            }]
        elif event.kind == "agent_output":
            return [{"kind": "agent_output", "source_layer": SourceLayer.ADAPTER,
                      "payload": event.payload}]
        elif event.kind == "process_exit":
            return [{"kind": EventKind.SESSION_EXITED, "source_layer": SourceLayer.ADAPTER,
                      "payload": event.payload}]
        return []

    def is_alive(self, handle: BackendHandle) -> bool:
        return not self._approved or True  # stays alive until exit event


class TestGoldenTrace:
    """Validate the canonical event sequence against the golden fixture."""

    def test_golden_event_sequence(self, tmp_path):
        golden = json.loads(GOLDEN_PATH.read_text())

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ToolUseAdapter()

        record = supervisor.create_session(
            adapter=adapter,
            backend_kind="claude_code",
            cwd="/tmp",
            task="echo hello",
            operator_mode="interactive",
        )
        supervisor.launch_session(record.session_id)

        # Wait for intervention
        for _ in range(50):
            time.sleep(0.1)
            pending = supervisor.get_pending_interventions(record.session_id)
            if pending:
                break

        # Approve the intervention
        pending = supervisor.get_pending_interventions(record.session_id)
        assert len(pending) == 1, f"Expected 1 intervention, got {len(pending)}"
        assert pending[0].tool_name == "Bash"
        supervisor.resolve_intervention(record.session_id, "tc_golden_001", "approve")

        # Wait for completion
        for _ in range(50):
            time.sleep(0.1)
            record = supervisor.get_session(record.session_id)
            if record.status in (SessionStatus.EXITED, SessionStatus.FAILED):
                break

        assert record.status == SessionStatus.EXITED

        # Compare event sequence against golden
        events = supervisor.get_events(record.session_id)
        assert len(events) == len(golden), (
            f"Event count mismatch: got {len(events)}, expected {len(golden)}\n"
            f"Got: {[e.kind for e in events]}\n"
            f"Expected: {[g['kind'] for g in golden]}"
        )

        for i, (actual, expected) in enumerate(zip(events, golden)):
            assert actual.seq == expected["seq"], f"seq mismatch at {i}"
            assert actual.kind == expected["kind"], (
                f"kind mismatch at seq {i}: got {actual.kind}, expected {expected['kind']}"
            )
            assert actual.source_layer == expected["source_layer"], (
                f"source_layer mismatch at seq {i}: got {actual.source_layer}, expected {expected['source_layer']}"
            )
            # Check tool_name in payload where golden specifies it
            if "payload" in expected and "tool_name" in expected["payload"]:
                assert actual.payload.get("tool_name") == expected["payload"]["tool_name"], (
                    f"tool_name mismatch at seq {i}"
                )

    def test_monotonic_seq(self, tmp_path):
        """Event sequences must be strictly monotonic."""
        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ToolUseAdapter()
        record = supervisor.create_session(adapter, "test", "/tmp", operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(1)

        events = supervisor.get_events(record.session_id)
        for i in range(1, len(events)):
            assert events[i].seq == events[i - 1].seq + 1, (
                f"Non-monotonic seq at {i}: {events[i-1].seq} -> {events[i].seq}"
            )

    def test_session_id_consistent(self, tmp_path):
        """All events must carry the same session_id."""
        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ToolUseAdapter()
        record = supervisor.create_session(adapter, "test", "/tmp", operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(1)

        events = supervisor.get_events(record.session_id)
        for e in events:
            assert e.session_id == record.session_id

    def test_lifecycle_bookends(self, tmp_path):
        """First event is session_created, last is session_exited or session_failed."""
        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ToolUseAdapter()
        record = supervisor.create_session(adapter, "test", "/tmp", operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(1)

        events = supervisor.get_events(record.session_id)
        assert events[0].kind == EventKind.SESSION_CREATED
        assert events[-1].kind in (EventKind.SESSION_EXITED, EventKind.SESSION_FAILED)

    def test_tool_call_paired(self, tmp_path):
        """Every tool_call_proposed has a matching allowed/denied and completed/failed."""
        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ToolUseAdapter()
        record = supervisor.create_session(adapter, "test", "/tmp", task="test",
                                           operator_mode="interactive")
        supervisor.launch_session(record.session_id)

        # Wait for and approve intervention
        for _ in range(50):
            time.sleep(0.1)
            pending = supervisor.get_pending_interventions(record.session_id)
            if pending:
                supervisor.resolve_intervention(record.session_id, "tc_golden_001", "approve")
                break

        time.sleep(1)
        events = supervisor.get_events(record.session_id)

        proposed = [e for e in events if e.kind == EventKind.TOOL_CALL_PROPOSED]
        resolved = [e for e in events if e.kind in (
            EventKind.TOOL_CALL_ALLOWED, EventKind.TOOL_CALL_DENIED
        )]
        completed = [e for e in events if e.kind in (
            EventKind.TOOL_CALL_COMPLETED, EventKind.TOOL_CALL_FAILED
        )]

        assert len(proposed) == len(resolved), "Every proposal needs a resolution"
        assert len(proposed) == len(completed), "Every proposal needs a completion"


class TestHookFormat:
    """Regression tests for Claude Code hook format."""

    def test_hook_keys_are_pascal_case(self):
        """Claude Code requires PascalCase: PreToolUse, PostToolUse."""
        from governor.runtime.adapters.claude_code import ClaudeCodeAdapter
        # The adapter writes settings with these keys
        # This test just validates the constant exists in the right form
        import governor.runtime.adapters.claude_code as cc
        # Check the hook injection code uses PascalCase
        import inspect
        source = inspect.getsource(cc.ClaudeCodeAdapter.launch)
        assert '"PreToolUse"' in source, "Hook injection must use PascalCase PreToolUse"
        assert '"PostToolUse"' in source, "Hook injection must use PascalCase PostToolUse"
        assert '"preToolUse"' not in source, "camelCase preToolUse must not appear"
        assert '"postToolUse"' not in source, "camelCase postToolUse must not appear"

    def test_hook_matcher_nesting(self):
        """Hooks must use {matcher, hooks: [{type, command, timeout}]} format."""
        import inspect
        import governor.runtime.adapters.claude_code as cc
        source = inspect.getsource(cc.ClaudeCodeAdapter.launch)
        assert '"matcher"' in source, "Hook entries must have a matcher field"
        assert '"hooks"' in source, "Hook entries must have nested hooks array"

    def test_pre_tool_deny_format(self):
        """PreToolUse deny must output hookSpecificOutput.permissionDecision."""
        from governor.runtime.adapters.claude_code import _SUPERVISED_PRE_TOOL_SCRIPT
        assert "hookSpecificOutput" in _SUPERVISED_PRE_TOOL_SCRIPT
        assert "permissionDecision" in _SUPERVISED_PRE_TOOL_SCRIPT
        assert '"deny"' in _SUPERVISED_PRE_TOOL_SCRIPT

    def test_stdin_closed_for_print_mode(self):
        """Adapter must close stdin when task is provided (--print mode)."""
        import inspect
        import governor.runtime.adapters.claude_code as cc
        source = inspect.getsource(cc.ClaudeCodeAdapter.launch)
        assert "stdin.close()" in source, "stdin must be closed for --print mode"
