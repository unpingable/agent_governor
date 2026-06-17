# SPDX-License-Identifier: Apache-2.0
"""GAP-3b: memory custody wired into the REAL supervisor path (non-operational).

The live supervisor's Standing input is derived THROUGH `memory_custody` via the probe's
`memory_context_builder`. Centerpiece: inherited session memory presented WITHOUT a `may_rely`
promotion cannot contribute Standing — `StandingOutput::Required` → the transition refuses → no
candidate. In `observe` the governed (legacy) path still continues and that divergence is recorded
loudly; in `hold` the path stops before any effect.

This is the bridge that makes "inputs can't be laundered through memory" true in the artery, not just on
the workbench. Still no `enforce`: full prevention of the legacy route is Stage 3.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.runtime.adapter import AdapterCapabilities, BackendHandle, NativeEvent
from governor.runtime.events import EventKind
from governor.runtime.supervisor import SessionSupervisor
from governor.runtime.transition_subprocess import (
    DEFAULT_TRANSITION_CLI,
    TransitionProbe,
    TransitionSubprocess,
)

BINARY = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)
pytestmark = pytest.mark.skipif(not Path(BINARY).exists(), reason=f"transition-cli not built at {BINARY}")


class _Worker:
    def __init__(self, worktree, proposals):
        self.worktree = Path(worktree)
        self.proposals = proposals
        self.controls = []

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config):
        return BackendHandle(pid=1)

    def iter_events(self, h):
        for tcid, name in self.proposals:
            yield NativeEvent(kind="pre_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid,
                "tool_input": {"file_path": str(self.worktree / f"{tcid}.txt"), "content": "effect"},
            })
            yield NativeEvent(kind="post_tool_use", payload={"tool_name": name, "tool_call_id": tcid})
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, h, a):
        self.controls.append(a)
        if getattr(a, "kind", None) == "approve":
            (self.worktree / f"{a.target_id}.txt").write_text("effect")

    def shutdown(self, h, g=True):
        pass

    def map_event(self, e):
        if e.kind == "pre_tool_use":
            return [{"kind": EventKind.TOOL_CALL_PROPOSED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "post_tool_use":
            return [{"kind": EventKind.TOOL_CALL_COMPLETED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "process_exit":
            return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter", "payload": e.payload}]
        return []

    def is_alive(self, h):
        return False


def _inherited_unpromoted(tool_name, tool_input, scope, target):
    """A claim inherited from a previous session, restated, with NO may_rely promotion."""
    return {
        "artifact": {
            "origin": "session-prev", "recorder": "ag:outer", "subject": "disk_pressure",
            "scope": scope or "lab", "intended_consumer": "ag:main", "recorded_at": 1,
            "epistemic_class": "inherited", "valid_until": 10_000,
            "content_digest": "sha256:inherited-summary",
        },
        "presentation": {"consumer": "ag:main", "now": 2, "scope": scope or "lab"},
    }


def _make_probe(mode, tmp_path):
    transport = TransitionSubprocess(binary_path=BINARY)
    transport.start()
    system = GateReceiptSystem(tmp_path / f"trx_{mode}")
    return TransitionProbe(
        transport=transport, mode=mode, receipt_system=system,
        memory_context_builder=_inherited_unpromoted,
    ), system


def _run(tmp_path, *, probe):
    wt = tmp_path / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    ctx = {"transition_probe": probe} if probe is not None else None
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _Worker(wt, [("a", "write")])
    record = sup.create_session(worker, "test", str(wt), operator_mode="autonomous", policy_context=ctx)
    sup.launch_session(record.session_id)
    time.sleep(0.6)
    return sup, record, wt


def _events(sup, record, kind):
    return [e for e in sup.get_events(record.session_id) if e.kind == kind]


def _gates(root: Path):
    jsonl = root / "receipts" / "gate_receipts.jsonl"
    return [json.loads(l)["gate"] for l in jsonl.read_text().splitlines() if l.strip()] if jsonl.exists() else []


def test_observe_inherited_memory_refused_but_legacy_continues(tmp_path):
    # The centerpiece: legacy autonomous path WOULD allow this write from inherited memory; the kernel,
    # routing Standing through custody, REFUSES (no may_rely promotion) -> no candidate.
    probe, _ = _make_probe("observe", tmp_path)
    sup, record, wt = _run(tmp_path, probe=probe)

    # Legacy governed path continued (the open hallway): file written.
    assert (wt / "a.txt").exists()
    # The kernel's refusal of laundered memory was recorded LOUDLY.
    div = _events(sup, record, "transition_divergence_observed")
    assert len(div) == 1
    assert div[0].payload["transition_decision"] == "refuse"
    gates = _gates(tmp_path / "trx_observe")
    assert "transition_kernel_seam" in gates and "transition_kernel_divergence" in gates


def test_hold_inherited_memory_stops_before_effect(tmp_path):
    probe, _ = _make_probe("hold", tmp_path)
    sup, record, wt = _run(tmp_path, probe=probe)

    # The door holds: no effect, no approval.
    assert not (wt / "a.txt").exists()
    assert _events(sup, record, EventKind.TOOL_CALL_ALLOWED) == []
    assert len(_events(sup, record, "transition_probe_held")) == 1
    assert "transition_kernel_seam" in _gates(tmp_path / "trx_hold")
