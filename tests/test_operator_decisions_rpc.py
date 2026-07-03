# SPDX-License-Identifier: Apache-2.0
"""GS-2b: the `operator.decisions.list` daemon method — the unified decision feed
over the wired runtime sources. Exposure-only (registered read_only); mints
nothing; every item mirrors a real pending object.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from governor.daemon import DaemonState, Dispatcher, register_handlers


@pytest.fixture
def gov_dir(tmp_path):
    d = tmp_path / ".governor"
    d.mkdir()
    (d / "sessions").mkdir()
    (d / "sessions" / "index.json").write_text(json.dumps({"sessions": {}, "mainline": None}))
    return d


@pytest.fixture
def dispatcher(gov_dir):
    state = DaemonState(gov_dir, mode="general")
    d = Dispatcher()
    register_handlers(d, state)
    return d, state


async def _call(dispatcher, method, params=None):
    req = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    return await dispatcher.dispatch(req)


@pytest.mark.asyncio
async def test_operator_decisions_list_registered_read_only(dispatcher):
    d, _ = dispatcher
    flags = d.get_method_info()
    # Registered, and NOT mutating (it is exposure-only).
    assert flags.get("operator.decisions.list") == "read_only"
    assert d.is_mutating("operator.decisions.list") is False


@pytest.mark.asyncio
async def test_operator_decisions_list_empty_when_no_sessions(dispatcher):
    d, _ = dispatcher
    resp = await _call(d, "operator.decisions.list")
    assert "error" not in resp
    assert resp["result"] == {"items": [], "count": 0}


# --- gather logic through a fake supervisor -------------------------------- #


@dataclass
class _FakeIntervention:
    intervention_id: str
    tool_call_id: str
    tool_name: str
    tool_input: dict
    event_id: str
    elapsed: float
    timeout_seconds: float = 300.0


@dataclass
class _FakeRecord:
    session_id: str


@dataclass
class _FakeSupervisor:
    interventions: dict = field(default_factory=dict)  # sid -> [Intervention]

    def list_sessions(self):
        return [_FakeRecord(sid) for sid in self.interventions]

    def get_pending_interventions(self, sid):
        return self.interventions.get(sid, [])

    def get_pending_promotion(self, sid):
        return None


@pytest.mark.asyncio
async def test_operator_decisions_list_gathers_interventions(dispatcher, monkeypatch):
    d, state = dispatcher
    fake = _FakeSupervisor(interventions={
        "sess_A": [_FakeIntervention("i1", "c1", "Bash", {"cmd": "rm"}, "e1", elapsed=10.0)],
    })
    # Point DaemonState at the fake supervisor + a no-pending violation resolver.
    monkeypatch.setattr(type(state), "runtime_supervisor", property(lambda self: fake))
    monkeypatch.setattr(type(state), "violation_resolver",
                        property(lambda self: type("V", (), {"get_pending": lambda s: None})()))
    resp = await _call(d, "operator.decisions.list")
    items = resp["result"]["items"]
    assert resp["result"]["count"] == 1
    it = items[0]
    assert it["kind"] == "intervention"
    assert it["session_ref"] == "sess_A"
    assert it["source"] == {"subsystem": "runtime.intervention", "native_id": "i1"}
    assert [o["key"] for o in it["options"]] == ["y", "n"]
    # kinds filter
    resp2 = await _call(d, "operator.decisions.list", {"kinds": ["violation"]})
    assert resp2["result"]["count"] == 0
