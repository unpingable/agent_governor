#!/usr/bin/env python3
"""Bounded reproduction for the runtime ``operator_mode`` fail-open finding.

This is an inert audit artifact.  It writes only below a temporary directory,
does not start a real backend, and does not modify Governor state in the repo.
Exit 0 means the paired control and reproduction matched the finding.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    NativeEvent,
)
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.supervisor import SessionSupervisor


class WriteOnApproveAdapter:
    """A fake hook adapter that materializes a write only after ``approve``."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.controls: list[ControlAction] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_native_tool_hooks=True,
            supports_structured_events=True,
        )

    def launch(self, config: object) -> BackendHandle:
        return BackendHandle(pid=4242)

    def iter_events(self, handle: BackendHandle):
        yield NativeEvent(
            kind="pre_tool_use",
            payload={
                "tool_name": "Write",
                "tool_call_id": "tc_write_1",
                "tool_input": {
                    "path": str(self.destination),
                    "content": "effect crossed\n",
                },
            },
        )

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        self.controls.append(action)
        if action.kind == "approve" and action.target_id == "tc_write_1":
            self.destination.write_text("effect crossed\n", encoding="utf-8")

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        return None

    def map_event(self, event: NativeEvent) -> list[dict[str, object]]:
        return [
            {
                "kind": EventKind.TOOL_CALL_PROPOSED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload["tool_call_id"],
                "payload": event.payload,
            }
        ]

    def is_alive(self, handle: BackendHandle) -> bool:
        return True


def run_case(root: Path, mode: str) -> dict[str, object]:
    destination = root / f"{mode}.txt"
    adapter = WriteOnApproveAdapter(destination)
    supervisor = SessionSupervisor(root / f"state-{mode}")
    record = supervisor.create_session(
        adapter,
        "operator-mode-reproduction",
        str(root),
        operator_mode=mode,
    )
    supervisor.launch_session(record.session_id)

    for _ in range(100):
        events = supervisor.get_events(record.session_id)
        if any(
            event.kind in (EventKind.TOOL_CALL_ALLOWED, EventKind.OPERATOR_PROMPTED)
            for event in events
        ):
            break
        time.sleep(0.01)

    events = supervisor.get_events(record.session_id)
    allowed = [event for event in events if event.kind == EventKind.TOOL_CALL_ALLOWED]
    return {
        "mode": mode,
        "write_exists": destination.exists(),
        "controls": [action.kind for action in adapter.controls],
        "allowed": len(allowed),
        "prompted": sum(event.kind == EventKind.OPERATOR_PROMPTED for event in events),
        "pending": len(supervisor.get_pending_interventions(record.session_id)),
        "auto": [event.payload.get("auto") for event in allowed],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ag-operator-mode-repro-") as temp_dir:
        root = Path(temp_dir)
        result = {
            "control": run_case(root, "interactive"),
            "reproduction": run_case(root, "not-a-real-mode"),
        }

    print(json.dumps(result, indent=2, sort_keys=True))
    expected = {
        "control": {
            "mode": "interactive",
            "write_exists": False,
            "controls": [],
            "allowed": 0,
            "prompted": 1,
            "pending": 1,
            "auto": [],
        },
        "reproduction": {
            "mode": "not-a-real-mode",
            "write_exists": True,
            "controls": ["approve"],
            "allowed": 1,
            "prompted": 0,
            "pending": 0,
            "auto": [True],
        },
    }
    return 0 if result == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
