# SPDX-License-Identifier: Apache-2.0
"""A2b: the transition-kernel probe spliced into the REAL supervisor hot path.

Drives `_handle_tool_proposed` through a real `SessionSupervisor` + scripted worker (the established
pattern), with the additive, flag-gated `transition_probe`. No `la_cli` needed: in autonomous mode a
WRITE without a lab_gate auto-approves — that IS the governed path continuing.

Acceptance:
- `disabled` (and absent) → behavior byte-identical to baseline; no transition receipts/events.
- `observe` + a hostile (refusing) office posture → the kernel would REFUSE while the governed path
  CONTINUES (the file is written). That divergence is recorded LOUDLY (a `transition_kernel_divergence`
  receipt + a `transition_divergence_observed` event) — never silently treated as advisory success.
- `hold` → the kernel decision is recorded, then the path STOPS before any effect: the file is NOT
  written and no approval is sent.
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

pytestmark = pytest.mark.skipif(
    not Path(BINARY).exists(),
    reason=f"transition-cli not built at {BINARY}",
)


class _Worker:
    """Scripted worker: proposes WRITEs; performs the real file effect only when AG approves."""

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


def _refuse_builder(tool_name, tool_input, scope, target):
    """Hostile office posture: standing expired → the kernel refuses at standing_seam, while the
    governed (autonomous) path would happily continue."""
    return {"standing": "expired", "scope": scope or "lab", "target": target or tool_name}


def _make_probe(mode, tmp_path, *, builder=None):
    transport = TransitionSubprocess(binary_path=BINARY)
    transport.start()
    system = GateReceiptSystem(tmp_path / f"trx_{mode}")
    kwargs = {"transport": transport, "mode": mode, "receipt_system": system}
    if builder is not None:
        kwargs["build_office_context"] = builder
    return TransitionProbe(**kwargs), system


def _run(tmp_path, *, probe, proposals=(("a", "write"),)):
    wt = tmp_path / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    ctx = {"transition_probe": probe} if probe is not None else None
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _Worker(wt, list(proposals))
    record = sup.create_session(worker, "test", str(wt), operator_mode="autonomous", policy_context=ctx)
    sup.launch_session(record.session_id)
    time.sleep(0.6)
    return sup, record, wt


def _events(sup, record, kind):
    return [e for e in sup.get_events(record.session_id) if e.kind == kind]


def _receipt_gates(system_root: Path):
    jsonl = system_root / "receipts" / "gate_receipts.jsonl"
    if not jsonl.exists():
        return []
    return [json.loads(line)["gate"] for line in jsonl.read_text().splitlines() if line.strip()]


def test_disabled_is_baseline(tmp_path):
    # No probe at all: the WRITE auto-approves, file written, no transition events.
    sup, record, wt = _run(tmp_path, probe=None)
    assert (wt / "a.txt").exists(), "governed path should auto-approve the write"
    assert _events(sup, record, "transition_divergence_observed") == []
    assert _events(sup, record, "transition_probe_held") == []

    # mode='disabled' must be identical.
    probe, system = _make_probe("disabled", tmp_path)
    sup2, record2, wt2 = _run(tmp_path / "d", probe=probe)
    assert (wt2 / "a.txt").exists()
    assert _events(sup2, record2, "transition_divergence_observed") == []
    assert _receipt_gates(tmp_path / "trx_disabled") == [], "disabled must mint no transition receipts"


def test_observe_records_loud_divergence_but_path_continues(tmp_path):
    probe, system = _make_probe("observe", tmp_path, builder=_refuse_builder)
    sup, record, wt = _run(tmp_path, probe=probe)

    # Governed path CONTINUED: the file was written (auto-approved).
    assert (wt / "a.txt").exists(), "observe must not stop the governed path"
    allowed = _events(sup, record, EventKind.TOOL_CALL_ALLOWED)
    assert len(allowed) == 1

    # The divergence was recorded LOUDLY (not silently treated as advisory success).
    div_events = _events(sup, record, "transition_divergence_observed")
    assert len(div_events) == 1
    assert div_events[0].payload["transition_decision"] == "refuse"
    gates = _receipt_gates(tmp_path / "trx_observe")
    assert "transition_kernel_seam" in gates, "the kernel decision was recorded (measurement)"
    assert "transition_kernel_divergence" in gates, "the refuse-vs-continue divergence was recorded"


def test_hold_stops_before_effect(tmp_path):
    probe, system = _make_probe("hold", tmp_path)  # default (admit) posture
    sup, record, wt = _run(tmp_path, probe=probe)

    # STOP before effect: no file, no approval.
    assert not (wt / "a.txt").exists(), "hold must stop before the effect"
    assert _events(sup, record, EventKind.TOOL_CALL_ALLOWED) == []
    held = _events(sup, record, "transition_probe_held")
    assert len(held) == 1
    # The kernel decision was still recorded as a measurement.
    assert "transition_kernel_seam" in _receipt_gates(tmp_path / "trx_hold")
