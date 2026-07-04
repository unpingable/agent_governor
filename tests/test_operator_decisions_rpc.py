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


# --- GS-2b remainder: docket_case source via the real disk load path -------- #


def _seed_docket_case(gov_dir, *, case_number=7, case_type="stale"):
    """Write a pending DocketCase to docket_cases.json — the on-disk source
    DaemonState.docket_manager loads (mirrors the CLI docket wiring)."""
    case = {
        "case_number": case_number,
        "case_type": case_type,
        "claim_id": "clm_1",
        "anchor_id": None,
        "status": "pending",
        "description": "confidence decayed",
        "evidence": [],
        "created_at": "2026-07-03T10:00:00+00:00",
        "blocked_content": None,
        "freshness_info": {"age_days": 42},
    }
    (gov_dir / "docket_cases.json").write_text(
        json.dumps({"cases": {str(case_number): case}, "next_case_number": case_number + 1})
    )


@pytest.mark.asyncio
async def test_operator_decisions_list_gathers_docket_case(dispatcher, gov_dir):
    """The persisted docket case surfaces through the REAL load path — no stub;
    DaemonState.docket_manager reads docket_cases.json under governor_dir."""
    d, _ = dispatcher
    _seed_docket_case(gov_dir)
    resp = await _call(d, "operator.decisions.list")
    items = resp["result"]["items"]
    assert resp["result"]["count"] == 1
    it = items[0]
    assert it["kind"] == "docket_case"
    assert it["source"] == {"subsystem": "docket", "native_id": "7"}
    # STALE case → stale rulings only (reverify/dismiss).
    assert [o["key"] for o in it["options"]] == ["v", "d"]
    assert it["detail"]["freshness_info"] == {"age_days": 42}
    # kinds filter honors the new kind.
    resp2 = await _call(d, "operator.decisions.list", {"kinds": ["docket_case"]})
    assert resp2["result"]["count"] == 1
    resp3 = await _call(d, "operator.decisions.list", {"kinds": ["intervention"]})
    assert resp3["result"]["count"] == 0


@pytest.mark.asyncio
async def test_operator_decisions_list_empty_docket_unchanged(dispatcher):
    """No docket_cases.json -> docket source contributes nothing; the existing
    green empty-feed path is unchanged."""
    d, _ = dispatcher
    resp = await _call(d, "operator.decisions.list")
    assert resp["result"] == {"items": [], "count": 0}


@pytest.mark.asyncio
async def test_docket_and_intervention_coexist_as_distinct_items(dispatcher, gov_dir, monkeypatch):
    """A live intervention and a persisted docket case surface as two distinct
    items — the docket binds no resolver, so nothing is double-carded."""
    d, state = dispatcher
    _seed_docket_case(gov_dir, case_number=5)
    fake = _FakeSupervisor(interventions={
        "sess_A": [_FakeIntervention("i1", "c1", "Bash", {"cmd": "rm"}, "e1", elapsed=10.0)],
    })
    monkeypatch.setattr(type(state), "runtime_supervisor", property(lambda self: fake))
    monkeypatch.setattr(type(state), "violation_resolver",
                        property(lambda self: type("V", (), {"get_pending": lambda s: None})()))
    resp = await _call(d, "operator.decisions.list")
    items = resp["result"]["items"]
    assert resp["result"]["count"] == 2
    assert sorted(i["kind"] for i in items) == ["docket_case", "intervention"]
    assert len({i["decision_id"] for i in items}) == 2


@pytest.mark.asyncio
async def test_resolve_routes_docket_stale_dismiss(dispatcher, gov_dir):
    """GS-3 docket route: a STALE docket case resolves through the ONE door to
    DocketManager.rule_dismiss; the returned precedent IS the record, and the
    ruled case drops from the feed (idempotence → decision_not_found on retry)."""
    d, _ = dispatcher
    _seed_docket_case(gov_dir, case_number=9)  # case_type="stale"
    listed = await _call(d, "operator.decisions.list")
    item = listed["result"]["items"][0]
    assert item["kind"] == "docket_case"
    assert [o["key"] for o in item["options"]] == ["v", "d"]

    resp = await _call(d, "operator.decisions.resolve",
                       {"decision_id": item["decision_id"], "option_key": "d",
                        "args": {"reason": "accepted"}})
    res = resp["result"]
    assert res["resolved"] is True
    assert res["kind"] == "docket_case"
    assert res["ruling"] == "dismiss"
    assert res["precedent"]["ruling"] == "dismiss"
    assert res["precedent"]["case_number"] == 9

    # Ruled → no longer pending → gone from the feed; re-resolve is not-found.
    after = await _call(d, "operator.decisions.list")
    assert after["result"]["count"] == 0
    again = await _call(d, "operator.decisions.resolve",
                        {"decision_id": item["decision_id"], "option_key": "d"})
    assert again["result"] == {"resolved": False, "error": "decision_not_found"}


@pytest.mark.asyncio
async def test_resolve_routes_docket_contested_sustain(dispatcher, gov_dir):
    """A CONTESTED docket case routes to rule_sustain and offers only the
    contested rulings (no reverify/dismiss the case type would reject)."""
    d, _ = dispatcher
    _seed_docket_case(gov_dir, case_number=4, case_type="contested")
    listed = await _call(d, "operator.decisions.list")
    item = listed["result"]["items"][0]
    assert [o["key"] for o in item["options"]] == ["s", "a", "g"]
    resp = await _call(d, "operator.decisions.resolve",
                       {"decision_id": item["decision_id"], "option_key": "s"})
    res = resp["result"]
    assert res["resolved"] is True and res["ruling"] == "sustain"
    assert res["precedent"]["case_number"] == 4


@pytest.mark.asyncio
async def test_resolve_grant_exception_scope_not_forgeable(dispatcher, gov_dir):
    """No privilege escalation via forged args: the grant_exception option
    declares no scope, so a caller-supplied args.scope='project' cannot broaden
    the exception — the door grants only the narrowest single_instance."""
    d, _ = dispatcher
    _seed_docket_case(gov_dir, case_number=6, case_type="contested")
    listed = await _call(d, "operator.decisions.list")
    item = listed["result"]["items"][0]
    resp = await _call(d, "operator.decisions.resolve",
                       {"decision_id": item["decision_id"], "option_key": "g",
                        "args": {"scope": "project", "reason": "try to widen"}})
    res = resp["result"]
    assert res["resolved"] is True and res["ruling"] == "grant_exception"
    # Forged wider scope ignored — narrowest scope granted.
    assert res["precedent"]["scope"] == "single_instance"
