# SPDX-License-Identifier: Apache-2.0
"""Stage 3b2: live supervisor `enforce` — the full consequence chain through the real hot path.

A WRITE proposal drives the enforce chain (consume + one bounded marker effect). The legacy lab_gate
route is structurally unreachable from the enforce branch (it returns). Fail-closed: anything but a
verified effect success denies.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from governor.runtime.adapter import AdapterCapabilities, BackendHandle, NativeEvent
from governor.runtime.events import EventKind
from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.supervisor import SessionSupervisor
from governor.runtime.transition_subprocess import (
    DEFAULT_TRANSITION_CLI,
    TransitionProbe,
    TransitionSubprocess,
)

LA_CLI = os.environ.get("GOVERNOR_LA_CLI", DEFAULT_LA_CLI)
TK_CLI = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)
pytestmark = pytest.mark.skipif(
    not (Path(LA_CLI).exists() and Path(TK_CLI).exists()),
    reason="la_cli and/or transition-cli not built",
)

SCOPE = "lab"
ELIG = "sha256:standing-xyz"


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
                "tool_name": name, "tool_call_id": tcid, "tool_input": {"x": 1}})
            yield NativeEvent(kind="post_tool_use", payload={"tool_name": name, "tool_call_id": tcid})
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, h, a):
        self.controls.append((getattr(a, "kind", None), a.target_id))

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


def _granted(la):
    la.deposit(SCOPE, 5)
    dec = la.request_capacity({
        "request_id": "r1", "actor": "ag:main", "action": "write", "target": "demo", "scope": SCOPE,
        "requested_capacity": 5, "eligibility_reference": ELIG, "eligibility_valid_until": 1000,
        "expires_after": 1000, "idempotency_key": None}, 10)
    assert dec["decision"] == "Granted"
    return dec["token_id"]


def _run(tmp_path, *, eligibility=ELIG):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    token = _granted(la)
    probe = TransitionProbe(
        transport=transition, mode="enforce", receipt_system=None,
        enforce_config={
            "la": la, "token_handle": token, "scope": SCOPE, "eligibility_reference": eligibility,
            "sandbox_root": tmp_path / "sandbox", "durable_path": tmp_path / "enforce.jsonl",
            "valid_until": 1000, "now": 10,
        },
    )
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _Worker(tmp_path / "wt", [("a", "write")])
    record = sup.create_session(worker, "t", str(tmp_path), operator_mode="autonomous",
                                policy_context={"transition_probe": probe})
    sup.launch_session(record.session_id)
    time.sleep(0.7)
    return sup, record, la, worker


def _events(sup, record, kind):
    return [e for e in sup.get_events(record.session_id) if e.kind == kind]


def test_enforce_effect_succeeds_through_supervisor(tmp_path):
    sup, record, la, worker = _run(tmp_path)
    try:
        # The real bounded effect happened: the marker exists.
        assert (tmp_path / "sandbox" / "a.marker").exists()
        allowed = _events(sup, record, EventKind.TOOL_CALL_ALLOWED)
        assert len(allowed) == 1
        assert allowed[0].payload.get("enforce") is True
        assert allowed[0].payload.get("terminal") == "consumed_effect_succeeded"
        # The legacy lab_gate route was structurally unreachable: this is an enforce decision, not an
        # la_kind/consumed lab_gate decision.
        assert "la_kind" not in allowed[0].payload
        assert ("approve", "a") in worker.controls
    finally:
        la.close()


def test_enforce_denies_on_chain_refusal_no_effect(tmp_path):
    # Eligibility the probe presents != the eligibility the LA capability binds -> binding refuses ->
    # the chain never reaches consume or effect -> deny, no marker.
    sup, record, la, worker = _run(tmp_path, eligibility="sha256:WRONG")
    try:
        assert not (tmp_path / "sandbox" / "a.marker").exists()
        assert _events(sup, record, EventKind.TOOL_CALL_ALLOWED) == []
        denied = _events(sup, record, EventKind.TOOL_CALL_DENIED)
        assert len(denied) == 1
        assert denied[0].payload.get("enforce") is True
        assert ("deny", "a") in worker.controls
    finally:
        la.close()
