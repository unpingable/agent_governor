# SPDX-License-Identifier: Apache-2.0
"""S5b — reusable harness for driving ops-shaped workflows through the REAL
grant-use seam (DaemonState + runtime.grant.activate RPC + SessionSupervisor +
receipts). Built AFTER S5a observed the seam once. Scenarios capture expected
dispositions as a corpus, so the operating model — not the unit-test model — is
what regresses. Not a test module itself (no test_ prefix); imported by the
corpus tests.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from governor.daemon import DaemonState, Dispatcher, register_handlers
from governor.runtime.adapter import NativeEvent
from governor.runtime.events import EventKind


@dataclass
class OpsScenario:
    """One ops-shaped workflow + the disposition each call should receive.

    ``calls`` is a list of (tool_call_id, tool_name, tool_input). ``expect``
    maps tool_call_id -> a disposition token:
        "auto"                       read / no-grant-check silent approve
        "accepted"                   grant-use WithinGrant, silent approve
        "widens:<axis>"              grant-use WidensGrant -> prompt
        "unverifiable:<reason>"      grant-use Unverifiable -> prompt (fail closed)
    """

    name: str
    write_paths: list[str]
    commands: list[dict]
    calls: list[tuple[str, str, dict]]
    expect: dict[str, str]


def _grant_request(scenario: OpsScenario) -> tuple[dict, str]:
    witness = f"operator approved {scenario.name}"
    wdig = "sha256:" + hashlib.sha256(witness.encode()).hexdigest()
    return {
        "write_paths": list(scenario.write_paths),
        "commands": list(scenario.commands),
        "source_plan_digest": "sha256:plan",
        "approval_witness_digest": wdig,
        "horizon": "run",
    }, witness


def _disposition_for(tid: str, evs) -> str:
    """Reduce the event stream to one disposition token for a tool_call_id."""
    for e in evs:
        p = e.payload if isinstance(e.payload, dict) else {}
        if p.get("tool_call_id") != tid:
            continue
        if e.kind == EventKind.TOOL_CALL_ALLOWED:
            if p.get("grant_use") == "accepted":
                return "accepted"
            return "auto"
        if e.kind == EventKind.OPERATOR_PROMPTED:
            gu = p.get("grant_use")
            if isinstance(gu, dict):
                if gu.get("disposition") == "widens":
                    return f"widens:{gu.get('axis')}"
                if gu.get("disposition") == "unverifiable":
                    return f"unverifiable:{gu.get('reason')}"
            return "prompt"
    return "none"


async def run_ops_scenario(tmp_path, scenario: OpsScenario) -> dict:
    """Run a scenario through the real seam; return {tool_call_id: disposition}."""
    from tests.test_runtime_supervisor import MockAdapter

    gov = tmp_path / scenario.name / ".governor"
    (gov / "sessions").mkdir(parents=True)
    (gov / "sessions" / "index.json").write_text(
        json.dumps({"sessions": {}, "mainline": None})
    )
    state = DaemonState(gov, mode="general")
    d = Dispatcher()
    register_handlers(d, state)
    sup = state.runtime_supervisor

    events = [
        NativeEvent(kind="pre_tool_use", payload={"tool_name": tn, "tool_call_id": tid, "tool_input": ti})
        for (tid, tn, ti) in scenario.calls
    ]
    record = sup.create_session(adapter=MockAdapter(events=events), backend_kind="mock", cwd="/work")
    sid = record.session_id

    req, witness = _grant_request(scenario)
    resp = await d.dispatch({
        "jsonrpc": "2.0", "id": 1, "method": "runtime.grant.activate",
        "params": {"session_id": sid, "execution_request": req, "witness_bytes": witness},
    })
    assert resp["result"]["grant_id"].startswith("sgr_"), resp

    sup.launch_session(sid)
    time.sleep(0.6)
    evs = sup.get_events(sid)
    return {tid: _disposition_for(tid, evs) for (tid, _, _) in scenario.calls}
