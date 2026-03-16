# SPDX-License-Identifier: Apache-2.0
"""Tests for the canonical event bus."""

import json
import tempfile
from pathlib import Path

import pytest

from governor.runtime.events import CanonicalEvent, EventBus, EventKind, SourceLayer


@pytest.fixture
def tmp_store(tmp_path):
    return tmp_path / "events.jsonl"


class TestCanonicalEvent:
    def test_to_dict_roundtrip(self):
        evt = CanonicalEvent(
            event_id="evt_abc123",
            session_id="sess_xyz",
            seq=0,
            at="2026-03-16T00:00:00Z",
            kind=EventKind.SESSION_CREATED,
            source_layer=SourceLayer.SUPERVISOR,
            backend_kind="claude_code",
            payload={"cwd": "/tmp"},
        )
        d = evt.to_dict()
        assert d["event_id"] == "evt_abc123"
        assert d["kind"] == "session_created"
        assert d["payload"]["cwd"] == "/tmp"

        restored = CanonicalEvent.from_dict(d)
        assert restored.event_id == evt.event_id
        assert restored.kind == evt.kind
        assert restored.payload == evt.payload

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "event_id": "evt_1",
            "session_id": "sess_1",
            "seq": 0,
            "at": "2026-01-01T00:00:00Z",
            "kind": "session_created",
            "source_layer": "supervisor",
            "backend_kind": "test",
            "unknown_field": "should be ignored",
        }
        evt = CanonicalEvent.from_dict(d)
        assert evt.event_id == "evt_1"


class TestEventBus:
    def test_emit_assigns_monotonic_seq(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        e1 = bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test")
        e2 = bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test")
        assert e1.seq == 0
        assert e2.seq == 1

    def test_emit_persists_to_jsonl(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test", payload={"x": 1})

        lines = tmp_store.read_text().strip().split("\n")
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["kind"] == "session_created"
        assert d["payload"]["x"] == 1

    def test_since_seq(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        for i in range(10):
            bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test", payload={"i": i})

        events = bus.since_seq(5)
        assert len(events) == 5
        assert events[0].seq == 5
        assert events[-1].seq == 9

    def test_since_seq_with_limit(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        for i in range(10):
            bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test")

        events = bus.since_seq(0, limit=3)
        assert len(events) == 3

    def test_latest(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        for i in range(5):
            bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test", payload={"i": i})

        last3 = bus.latest(3)
        assert len(last3) == 3
        assert last3[0].payload["i"] == 2
        assert last3[2].payload["i"] == 4

    def test_get_by_id(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        e1 = bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test")
        e2 = bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test")

        assert bus.get_by_id(e1.event_id) is e1
        assert bus.get_by_id(e2.event_id) is e2
        assert bus.get_by_id("nonexistent") is None

    def test_tool_call_dedup(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        e1 = bus.emit(
            EventKind.TOOL_CALL_PROPOSED,
            SourceLayer.ADAPTER,
            "test",
            tool_call_id="tc_001",
            payload={"tool_name": "bash"},
        )
        # Same tool_call_id should return the existing event
        e2 = bus.emit(
            EventKind.TOOL_CALL_PROPOSED,
            SourceLayer.ADAPTER,
            "test",
            tool_call_id="tc_001",
            payload={"tool_name": "bash"},
        )
        assert e1.event_id == e2.event_id
        assert bus.event_count == 1

    def test_tool_call_different_ids_not_deduped(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        e1 = bus.emit(
            EventKind.TOOL_CALL_PROPOSED,
            SourceLayer.ADAPTER,
            "test",
            tool_call_id="tc_001",
        )
        e2 = bus.emit(
            EventKind.TOOL_CALL_PROPOSED,
            SourceLayer.ADAPTER,
            "test",
            tool_call_id="tc_002",
        )
        assert e1.event_id != e2.event_id
        assert bus.event_count == 2

    def test_get_by_tool_call_id(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        bus.emit(EventKind.TOOL_CALL_PROPOSED, SourceLayer.ADAPTER, "test",
                 tool_call_id="tc_001", payload={"tool_name": "bash"})
        bus.emit(EventKind.TOOL_CALL_ALLOWED, SourceLayer.POLICY, "test",
                 tool_call_id="tc_001")
        bus.emit(EventKind.TOOL_CALL_COMPLETED, SourceLayer.ADAPTER, "test",
                 tool_call_id="tc_001")
        bus.emit(EventKind.TOOL_CALL_PROPOSED, SourceLayer.ADAPTER, "test",
                 tool_call_id="tc_002")

        events = bus.get_by_tool_call_id("tc_001")
        assert len(events) == 3
        assert all(e.payload.get("tool_call_id") == "tc_001" for e in events)

    def test_reload_from_existing_store(self, tmp_store):
        bus1 = EventBus("sess_1", tmp_store)
        bus1.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test")
        bus1.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test")
        bus1.emit(EventKind.TOOL_CALL_PROPOSED, SourceLayer.ADAPTER, "test",
                  tool_call_id="tc_001")

        # Create new bus from same store
        bus2 = EventBus("sess_1", tmp_store)
        assert bus2.event_count == 3
        assert bus2.next_seq == 3
        # Dedup should work after reload
        e = bus2.emit(EventKind.TOOL_CALL_PROPOSED, SourceLayer.ADAPTER, "test",
                      tool_call_id="tc_001")
        assert e.seq == 2  # Original seq, not a new one
        assert bus2.event_count == 3

    def test_store_file_permissions(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test")
        mode = tmp_store.stat().st_mode & 0o777
        assert mode == 0o600

    def test_session_id_propagates(self, tmp_store):
        bus = EventBus("sess_abc", tmp_store)
        evt = bus.emit(EventKind.SESSION_CREATED, SourceLayer.SUPERVISOR, "test")
        assert evt.session_id == "sess_abc"
        assert bus.session_id == "sess_abc"

    def test_event_ids_are_unique(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        ids = set()
        for _ in range(100):
            evt = bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, "test")
            ids.add(evt.event_id)
        assert len(ids) == 100

    def test_receipt_ids_and_correlation(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        evt = bus.emit(
            EventKind.TOOL_CALL_ALLOWED,
            SourceLayer.POLICY,
            "test",
            receipt_ids=["rcpt_001", "rcpt_002"],
            correlation_id="corr_abc",
        )
        assert evt.receipt_ids == ["rcpt_001", "rcpt_002"]
        assert evt.correlation_id == "corr_abc"

    def test_parent_event_id(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        e1 = bus.emit(EventKind.TOOL_CALL_PROPOSED, SourceLayer.ADAPTER, "test")
        e2 = bus.emit(EventKind.TOOL_CALL_ALLOWED, SourceLayer.POLICY, "test",
                      parent_event_id=e1.event_id)
        assert e2.parent_event_id == e1.event_id

    def test_empty_bus(self, tmp_store):
        bus = EventBus("sess_1", tmp_store)
        assert bus.event_count == 0
        assert bus.next_seq == 0
        assert bus.since_seq(0) == []
        assert bus.latest() == []
