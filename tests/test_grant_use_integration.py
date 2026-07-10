# SPDX-License-Identifier: Apache-2.0
"""S5a — minimal LIVE smoke for the approval-compression seam. Wires the REAL
components (DaemonState, runtime.grant.activate RPC, SessionSupervisor, receipt
system) and drives tool events through a scripted mock AGENT (the legit stand-in
— we test the governance seam, not the model). Observes the whole seam cross the
daemon boundary once, with receipt continuity, before any harness is built.
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from governor.daemon import DaemonState, Dispatcher, register_handlers
from governor.runtime.adapter import NativeEvent
from governor.runtime.events import EventKind
from tests.test_runtime_supervisor import MockAdapter


def _rpc(method, params):
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}


@pytest.mark.asyncio
async def test_s5a_live_smoke_activation_uses_and_receipt_continuity(tmp_path):
    gov = tmp_path / ".governor"
    (gov / "sessions").mkdir(parents=True)
    (gov / "sessions" / "index.json").write_text(
        json.dumps({"sessions": {}, "mainline": None})
    )
    state = DaemonState(gov, mode="general")
    d = Dispatcher()
    register_handlers(d, state)
    sup = state.runtime_supervisor

    # Scripted agent: two identical in-scope reads, one in-scope edit, one
    # in-scope cargo test, one out-of-scope edit (the widening).
    events = [
        NativeEvent(kind="pre_tool_use", payload={"tool_name": "Read", "tool_call_id": "r1", "tool_input": {"file_path": "/work/a.rs"}}),
        NativeEvent(kind="pre_tool_use", payload={"tool_name": "Read", "tool_call_id": "r2", "tool_input": {"file_path": "/work/a.rs"}}),
        NativeEvent(kind="pre_tool_use", payload={"tool_name": "Edit", "tool_call_id": "e_in", "tool_input": {"file_path": "/work/src/x.rs"}}),
        NativeEvent(kind="pre_tool_use", payload={"tool_name": "Bash", "tool_call_id": "cargo", "tool_input": {"command": "cargo test --lib"}}),
        NativeEvent(kind="pre_tool_use", payload={"tool_name": "Edit", "tool_call_id": "e_out", "tool_input": {"file_path": "/etc/passwd"}}),
    ]
    record = sup.create_session(adapter=MockAdapter(events=events), backend_kind="mock", cwd="/work")
    sid = record.session_id

    # Activate + attach a grant through the REAL RPC.
    witness = "operator approved 2026-07-10"
    wdig = "sha256:" + hashlib.sha256(witness.encode()).hexdigest()
    resp = await d.dispatch(_rpc("runtime.grant.activate", {
        "session_id": sid,
        "execution_request": {
            "write_paths": ["/work/src/**"],
            "commands": [{"program": "cargo", "argv_prefix": ["test"]}],
            "source_plan_digest": "sha256:plan",
            "approval_witness_digest": wdig,
            "horizon": "run",
        },
        "witness_bytes": witness,
    }))
    grant_id = resp["result"]["grant_id"]
    assert grant_id.startswith("sgr_")

    # Run the scripted agent through the real supervisor.
    sup.launch_session(sid)
    time.sleep(0.6)

    evs = sup.get_events(sid)

    # Only the out-of-scope edit prompts; everything in-envelope proceeds.
    interventions = sup.get_pending_interventions(sid)
    assert [i.tool_call_id for i in interventions] == ["e_out"]

    # In-scope edit + cargo carry grant_use=accepted, both citing THIS grant.
    accepted = [e for e in evs
                if e.kind == EventKind.TOOL_CALL_ALLOWED and e.payload.get("grant_use") == "accepted"]
    accepted_ids = {e.payload.get("tool_call_id") for e in accepted}
    assert {"e_in", "cargo"} <= accepted_ids
    assert all(e.payload.get("grant_id") == grant_id for e in accepted)

    # The widening prompt is annotated with why (axis), citing the same grant.
    prompted = [e for e in evs if e.kind == EventKind.OPERATOR_PROMPTED]
    gu = prompted[-1].payload.get("grant_use")
    assert gu and gu["disposition"] == "widens" and gu["axis"] == "write_path"
    assert gu["grant_id"] == grant_id

    # Receipt continuity: activation receipt exists, and grant.get returns the
    # same grant the uses cited.
    receipts = list(state.receipt_system.receipt_store.all())
    assert any(getattr(r, "gate", None) == "grant_activation" for r in receipts)
    g = (await d.dispatch(_rpc("runtime.grant.get", {"session_id": sid})))["result"]
    assert g["grant_id"] == grant_id
    # the same run's dispositions are visible through grant.get too
    dispositions = {u.get("disposition") for u in g["recent_uses"]}
    assert "accepted" in dispositions and "widens" in dispositions
