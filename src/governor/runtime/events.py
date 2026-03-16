# SPDX-License-Identifier: Apache-2.0
"""Canonical event bus for supervised agent sessions.

The event bus normalizes backend-native events into a uniform stream.
Events are sequenced per session, persisted to append-only JSONL,
and queryable by sequence cursor.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


class EventKind(str, Enum):
    """Canonical event kinds for supervised sessions."""

    # Lifecycle
    SESSION_CREATED = "session_created"
    SESSION_LAUNCHING = "session_launching"
    SESSION_ATTACHED = "session_attached"
    SESSION_RUNNING = "session_running"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_DRAINING = "session_draining"
    SESSION_EXITED = "session_exited"
    SESSION_FAILED = "session_failed"
    SUPERVISOR_RESTART = "supervisor_restart"

    # Tool boundary
    TOOL_CALL_PROPOSED = "tool_call_proposed"
    TOOL_CALL_ALLOWED = "tool_call_allowed"
    TOOL_CALL_DENIED = "tool_call_denied"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"

    # Workspace
    WORKSPACE_CHANGE_DETECTED = "workspace_change_detected"
    PROMOTION_REQUIRED = "promotion_required"
    PROMOTION_RESOLVED = "promotion_resolved"

    # Operator
    OPERATOR_PROMPTED = "operator_prompted"
    OPERATOR_DECISION = "operator_decision"

    # Intervention
    INTERVENTION_TIMEOUT = "intervention_timeout"

    # Faults
    ADAPTER_ERROR = "adapter_error"
    RUNTIME_PROTOCOL_ERROR = "runtime_protocol_error"


class SourceLayer(str, Enum):
    """Where the event originated."""

    ADAPTER = "adapter"
    SUPERVISOR = "supervisor"
    POLICY = "policy"
    OPERATOR = "operator"


@dataclass(slots=True)
class CanonicalEvent:
    """A normalized event from any backend.

    Sequenced per session, correlated to receipts.
    Identified by (session_id, seq) — unique within a session.
    """

    event_id: str
    session_id: str
    seq: int
    at: str  # ISO 8601
    kind: str  # EventKind value
    source_layer: str  # SourceLayer value
    backend_kind: str
    correlation_id: str | None = None
    parent_event_id: str | None = None
    receipt_ids: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CanonicalEvent:
        return cls(**{k: v for k, v in d.items() if k in cls.__slots__})


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


class EventBus:
    """Per-session canonical event bus with append-only JSONL persistence.

    Thread-safe via fcntl file locking. Provides monotonic seq allocation
    and since_seq cursor reads.
    """

    def __init__(self, session_id: str, store_path: Path | str) -> None:
        self._session_id = session_id
        self._store_path = Path(store_path)
        self._next_seq = 0
        self._events: list[CanonicalEvent] = []
        self._seen_tool_call_ids: set[str] = set()

        # Load existing events if store exists
        if self._store_path.exists():
            self._load_existing()

    def _load_existing(self) -> None:
        """Load events from JSONL store, set next_seq."""
        max_seq = -1
        with open(self._store_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    evt = CanonicalEvent.from_dict(d)
                    self._events.append(evt)
                    if evt.seq > max_seq:
                        max_seq = evt.seq
                    # Track tool_call_ids for dedup
                    tcid = evt.payload.get("tool_call_id")
                    if tcid and evt.kind == EventKind.TOOL_CALL_PROPOSED:
                        self._seen_tool_call_ids.add(tcid)
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue  # skip corrupt lines
        self._next_seq = max_seq + 1

    def emit(
        self,
        kind: EventKind | str,
        source_layer: SourceLayer | str,
        backend_kind: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        parent_event_id: str | None = None,
        receipt_ids: list[str] | None = None,
        tool_call_id: str | None = None,
    ) -> CanonicalEvent:
        """Emit a canonical event. Returns the event.

        If tool_call_id is provided for a TOOL_CALL_PROPOSED event and
        it has already been seen, returns the existing event (dedup).
        """
        kind_str = kind.value if isinstance(kind, EventKind) else kind
        layer_str = source_layer.value if isinstance(source_layer, SourceLayer) else source_layer

        # Dedup tool_call_proposed by tool_call_id
        if tool_call_id and kind_str == EventKind.TOOL_CALL_PROPOSED:
            if tool_call_id in self._seen_tool_call_ids:
                for evt in reversed(self._events):
                    if (
                        evt.kind == EventKind.TOOL_CALL_PROPOSED
                        and evt.payload.get("tool_call_id") == tool_call_id
                    ):
                        return evt
            self._seen_tool_call_ids.add(tool_call_id)

        payload = payload or {}
        if tool_call_id:
            payload["tool_call_id"] = tool_call_id

        evt = CanonicalEvent(
            event_id=_new_event_id(),
            session_id=self._session_id,
            seq=self._next_seq,
            at=_now_iso(),
            kind=kind_str,
            source_layer=layer_str,
            backend_kind=backend_kind,
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
            receipt_ids=receipt_ids or [],
            payload=payload,
        )
        self._next_seq += 1
        self._events.append(evt)
        self._persist(evt)
        return evt

    def _persist(self, evt: CanonicalEvent) -> None:
        """Append event to JSONL store with file locking."""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(evt.to_dict(), separators=(",", ":")) + "\n"
        fd = os.open(
            str(self._store_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def since_seq(self, seq: int, limit: int = 100) -> list[CanonicalEvent]:
        """Return events with seq >= the given value, up to limit."""
        result = []
        for evt in self._events:
            if evt.seq >= seq:
                result.append(evt)
                if len(result) >= limit:
                    break
        return result

    def latest(self, n: int = 20) -> list[CanonicalEvent]:
        """Return the most recent N events."""
        return self._events[-n:]

    def get_by_id(self, event_id: str) -> CanonicalEvent | None:
        """Lookup event by event_id."""
        for evt in reversed(self._events):
            if evt.event_id == event_id:
                return evt
        return None

    def get_by_tool_call_id(self, tool_call_id: str) -> list[CanonicalEvent]:
        """Return all events for a given tool_call_id."""
        return [
            evt
            for evt in self._events
            if evt.payload.get("tool_call_id") == tool_call_id
        ]

    @property
    def next_seq(self) -> int:
        return self._next_seq

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def event_count(self) -> int:
        return len(self._events)
