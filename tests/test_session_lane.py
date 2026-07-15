# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — A-1 ruling, Option 4b: derived lane labeling.

Ruled 2026-07-15: "name the distinction without pretending you can enforce
the stronger boundary for free." The lane ("governed"/"ungoverned") is
DERIVED from seam-B grant presence, stamped on every canonical event at
emission, exposed on session.get — and gates NOTHING. 4a (the restriction)
is a named, unimplemented follow-up (`a1-lane-restriction-4a`).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

import pytest

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    NativeEvent,
)
from governor.runtime.events import CanonicalEvent, EventBus, EventKind, SourceLayer
from governor.runtime.supervisor import SessionSupervisor


class OneWriteAdapter:
    """Minimal adapter proposing a single Write tool call."""

    def __init__(self) -> None:
        self.controls: list[ControlAction] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_native_tool_hooks=True, supports_structured_events=True
        )

    def launch(self, config: object) -> BackendHandle:
        return BackendHandle(pid=4242)

    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]:
        yield NativeEvent(
            kind="pre_tool_use",
            payload={
                "tool_name": "Write",
                "tool_call_id": "tc_1",
                "tool_input": {"path": "/tmp/x", "content": "y"},
            },
        )

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        self.controls.append(action)

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        return None

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        return [{
            "kind": EventKind.TOOL_CALL_PROPOSED,
            "source_layer": SourceLayer.ADAPTER,
            "tool_call_id": event.payload["tool_call_id"],
            "payload": event.payload,
        }]

    def is_alive(self, handle: BackendHandle) -> bool:
        return True


def _settle(supervisor: SessionSupervisor, session_id: str, adapter: OneWriteAdapter):
    supervisor.launch_session(session_id)
    for _ in range(200):
        events = supervisor.get_events(session_id)
        prompted = any(e.kind == EventKind.OPERATOR_PROMPTED for e in events)
        allowed = any(e.kind == EventKind.TOOL_CALL_ALLOWED for e in events)
        if prompted or (allowed and adapter.controls):
            break
        time.sleep(0.01)
    return supervisor.get_events(session_id)


class TestDerivedLane:
    def test_plain_session_is_ungoverned_on_record_and_every_event(self, tmp_path):
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = OneWriteAdapter()
        record = sup.create_session(adapter, "mock", str(tmp_path))

        assert sup.session_lane(record.session_id) == "ungoverned"
        events = _settle(sup, record.session_id, adapter)
        assert events, "session must have emitted events"
        assert all(e.lane == "ungoverned" for e in events), (
            f"every event must carry the lane; got "
            f"{[(e.kind, e.lane) for e in events if e.lane != 'ungoverned']}"
        )

    def test_ungoverned_autonomous_square_is_distinguishable_in_the_trail(
        self, tmp_path
    ):
        """THE 4b acceptance: the exposed square keeps working but stops
        being invisible — its auto-approved writes are lane-labeled."""
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = OneWriteAdapter()
        record = sup.create_session(
            adapter, "mock", str(tmp_path), operator_mode="autonomous"
        )

        events = _settle(sup, record.session_id, adapter)
        allowed = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED]

        # 4b changes NO behavior: the square still auto-approves...
        assert len(allowed) == 1
        assert allowed[0].payload.get("auto") is True
        assert adapter.controls and adapter.controls[0].kind == "approve"
        # ...but the trail now testifies which lane the effect came from.
        assert allowed[0].lane == "ungoverned"

    def test_grant_attachment_flips_the_lane_and_the_trail_shows_when(
        self, tmp_path
    ):
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = OneWriteAdapter()
        record = sup.create_session(adapter, "mock", str(tmp_path))
        sid = record.session_id

        bus = sup._get_bus(sid)
        bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "mock")
        assert sup.session_lane(sid) == "ungoverned"

        sup.attach_execution_grant(sid, object())  # lane derives from presence
        assert sup.session_lane(sid) == "governed"
        bus.emit("post_attach_marker", SourceLayer.SUPERVISOR, "mock")

        events = sup.get_events(sid)
        assert events[-2].lane == "ungoverned"  # before the attach
        assert events[-1].lane == "governed"  # after — the transition is in the trail

    def test_revoked_lease_stays_governed(self, tmp_path):
        """A governed session whose grant died is not an ungoverned one."""
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        record = sup.create_session(OneWriteAdapter(), "mock", str(tmp_path))
        sid = record.session_id
        sup.attach_execution_grant(sid, object())

        sup.revoke_execution_grant(sid, reason="test")

        assert sup.session_lane(sid) == "governed"


class TestEnvelopeCompat:
    def test_old_events_read_back_unlabeled(self):
        d = {
            "event_id": "evt_x", "session_id": "s", "seq": 0,
            "at": "2026-07-15T00:00:00Z", "kind": "session_created",
            "source_layer": "supervisor", "backend_kind": "mock",
        }
        evt = CanonicalEvent.from_dict(d)
        assert evt.lane is None  # absence of testimony, not a third lane

    def test_lane_round_trips(self):
        d = {
            "event_id": "evt_x", "session_id": "s", "seq": 0,
            "at": "2026-07-15T00:00:00Z", "kind": "session_created",
            "source_layer": "supervisor", "backend_kind": "mock",
            "lane": "governed",
        }
        assert CanonicalEvent.from_dict(d).lane == "governed"
        assert CanonicalEvent.from_dict(d).to_dict()["lane"] == "governed"

    def test_raising_provider_degrades_to_unlabeled_never_lost(self, tmp_path):
        """The label is testimony; the event is the record."""
        bus = EventBus("s", tmp_path / "s_events.jsonl")

        def boom() -> str:
            raise RuntimeError("provider broke")

        bus.lane_provider = boom
        evt = bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "mock")
        assert evt.lane is None
        assert bus.latest(1) == [evt]  # emitted and persisted regardless
        assert (tmp_path / "s_events.jsonl").exists()


class TestDaemonSurface:
    @pytest.mark.asyncio
    async def test_session_get_exposes_derived_lane(self, tmp_path):
        from governor.daemon import DaemonState, Dispatcher, register_handlers

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        state = DaemonState(gov_dir, mode="general")
        dispatcher = Dispatcher()
        register_handlers(dispatcher, state)

        record = state.runtime_supervisor.create_session(
            OneWriteAdapter(), "mock", str(tmp_path)
        )
        response = await dispatcher.dispatch({
            "jsonrpc": "2.0", "id": 1, "method": "runtime.session.get",
            "params": {"session_id": record.session_id},
        })

        assert response["result"]["lane"] == "ungoverned"

        state.runtime_supervisor.attach_execution_grant(record.session_id, object())
        response = await dispatcher.dispatch({
            "jsonrpc": "2.0", "id": 2, "method": "runtime.session.get",
            "params": {"session_id": record.session_id},
        })
        assert response["result"]["lane"] == "governed"
