# SPDX-License-Identifier: Apache-2.0
"""S5c — grant LEASE lifecycle: revocation + expiry. Invariant: a grant may be
used repeatedly, but never past revocation or horizon. Unit lease tests +
supervisor/daemon integration (revoke path, use-time expiry on a monotonic
clock, terminal dispositions distinct from widening, idempotence, no
resurrection).
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from governor.daemon import DaemonState, Dispatcher, register_handlers
from governor.runtime.adapter import NativeEvent
from governor.runtime.events import EventKind
from governor.runtime.execution_grant import (
    GRANT_ACTIVE,
    GRANT_EXPIRED,
    GRANT_REVOKED,
    ExecutionRequest,
    GrantLease,
    activate_execution_grant,
)
from governor.runtime.grant_use_gate import CommandGrant
from tests.test_runtime_supervisor import MockAdapter


def _artifact():
    return activate_execution_grant(ExecutionRequest(
        write_paths=frozenset({"/work/src/**"}),
        commands=(CommandGrant("cargo", ("test",)),),
        source_plan_digest="sha256:p", approval_witness_digest="sha256:w",
    ))


# --------------------------------------------------------------------------
# Unit — lease lifecycle.
# --------------------------------------------------------------------------

def test_revoke_is_idempotent_and_does_not_overwrite_reason():
    lease = GrantLease(_artifact(), activated_monotonic=0.0)
    assert lease.state == GRANT_ACTIVE
    assert lease.revoke("first") == GRANT_REVOKED
    assert lease.revoke("second") == GRANT_REVOKED  # no-op
    assert lease.revoked_reason == "first"


def test_revoke_does_not_override_expiry():
    lease = GrantLease(_artifact(), activated_monotonic=0.0, expires_after_ns=1)
    lease.check_expiry(1.0)  # 1s >> 1ns
    assert lease.state == GRANT_EXPIRED
    assert lease.revoke("op") == GRANT_EXPIRED  # terminal wins; not rewritten


def test_expiry_boundary_checked_at_use_time():
    lease = GrantLease(_artifact(), activated_monotonic=10.0, expires_after_ns=1_000_000_000)
    lease.check_expiry(10.5)  # 0.5s elapsed < 1s
    assert lease.state == GRANT_ACTIVE
    lease.check_expiry(11.0)  # 1.0s elapsed >= 1s
    assert lease.state == GRANT_EXPIRED


def test_expired_never_unexpires_on_clock_regression():
    lease = GrantLease(_artifact(), activated_monotonic=0.0, expires_after_ns=1)
    lease.check_expiry(1.0)
    assert lease.state == GRANT_EXPIRED
    lease.check_expiry(0.0)  # clock goes backward — must not resurrect
    assert lease.state == GRANT_EXPIRED


def test_no_expiry_bound_stays_active():
    lease = GrantLease(_artifact(), activated_monotonic=0.0, expires_after_ns=None)
    lease.check_expiry(1e9)
    assert lease.state == GRANT_ACTIVE


# --------------------------------------------------------------------------
# Integration helpers.
# --------------------------------------------------------------------------

def _setup(tmp_path, clock=None):
    gov = tmp_path / ".governor"
    (gov / "sessions").mkdir(parents=True)
    (gov / "sessions" / "index.json").write_text(json.dumps({"sessions": {}, "mainline": None}))
    state = DaemonState(gov, mode="general")
    d = Dispatcher()
    register_handlers(d, state)
    if clock is not None:
        state.runtime_supervisor._monotonic = clock
    return d, state


def _rpc(method, params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


def _cargo_session(sup, tcid="c1"):
    events = [NativeEvent(kind="pre_tool_use", payload={
        "tool_name": "Bash", "tool_call_id": tcid, "tool_input": {"command": "cargo test --lib"}})]
    return sup.create_session(adapter=MockAdapter(events=events), backend_kind="mock", cwd="/work")


def _activate(d, sid, expires_after_ns=None):
    plan_text = "# grant-lease plan\nplan_version: 1\n"
    plan_ref = "sha256:" + hashlib.sha256(plan_text.encode("utf-8")).hexdigest()
    witness = json.dumps({
        "witness_version": "approval-witness/v1", "decision": "approve", "plan_ref": plan_ref,
    })
    wdig = "sha256:" + hashlib.sha256(witness.encode()).hexdigest()
    params = {
        "session_id": sid,
        "execution_request": {
            "write_paths": ["/work/src/**"],
            "commands": [{"program": "cargo", "argv_prefix": ["test"]}],
            "source_plan_digest": plan_ref,
            "approval_witness_digest": wdig,
            "horizon": "run",
        },
        "witness_bytes": witness,
        "plan_bytes": plan_text,
    }
    if expires_after_ns is not None:
        params["expires_after_ns"] = expires_after_ns
    return _rpc("runtime.grant.activate", params)


def _disposition(sup, sid, tcid):
    for e in sup.get_events(sid):
        p = e.payload if isinstance(e.payload, dict) else {}
        if p.get("tool_call_id") != tcid:
            continue
        if e.kind == EventKind.TOOL_CALL_ALLOWED and p.get("grant_use") == "accepted":
            return "accepted"
        if e.kind == EventKind.OPERATOR_PROMPTED and isinstance(p.get("grant_use"), dict):
            return p["grant_use"]["disposition"]
    return "none"


# --------------------------------------------------------------------------
# S5c1 — revocation through the real seam.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoked_grant_refuses_subsequent_use(tmp_path):
    d, state = _setup(tmp_path)
    sup = state.runtime_supervisor
    record = _cargo_session(sup)
    sid = record.session_id
    await d.dispatch(_activate(d, sid))
    # revoke BEFORE the call fires
    rv = await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid, "reason": "operator pulled it"}))
    assert rv["result"]["state"] == GRANT_REVOKED
    sup.launch_session(sid)
    time.sleep(0.5)
    # the in-scope cargo test now prompts as revoked, NOT accepted
    assert _disposition(sup, sid, "c1") == "revoked"
    g = (await d.dispatch(_rpc("runtime.grant.get", {"session_id": sid})))["result"]
    assert g["state"] == GRANT_REVOKED and g["revoked_reason"] == "operator pulled it"


@pytest.mark.asyncio
async def test_revoke_is_idempotent_and_receipted_once(tmp_path):
    d, state = _setup(tmp_path)
    sup = state.runtime_supervisor
    sid = _cargo_session(sup).session_id
    await d.dispatch(_activate(d, sid))
    r1 = (await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid})))["result"]
    r2 = (await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid})))["result"]
    assert r1["already_terminal"] is False and r2["already_terminal"] is True
    revocations = [r for r in state.receipt_system.receipt_store.all()
                   if getattr(r, "gate", None) == "grant_revocation"]
    assert len(revocations) == 1  # no duplicate receipt on the idempotent call


@pytest.mark.asyncio
async def test_revoke_without_grant_reports_no_grant(tmp_path):
    d, state = _setup(tmp_path)
    sid = _cargo_session(state.runtime_supervisor).session_id
    rv = (await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid})))["result"]
    assert rv["revoked"] is False and rv["error"] == "no_grant"


# --------------------------------------------------------------------------
# S5c2 — expiry, checked at use time on a monotonic clock.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_expired_by_use_time_refuses(tmp_path):
    clock = {"t": 0.0}
    d, state = _setup(tmp_path, clock=lambda: clock["t"])
    sup = state.runtime_supervisor
    sid = _cargo_session(sup).session_id
    # activate at t=0 with a 1s bound
    await d.dispatch(_activate(d, sid, expires_after_ns=1_000_000_000))
    # advance the clock PAST the horizon before the call is processed
    clock["t"] = 2.0
    sup.launch_session(sid)
    time.sleep(0.5)
    assert _disposition(sup, sid, "c1") == "expired"
    g = (await d.dispatch(_rpc("runtime.grant.get", {"session_id": sid})))["result"]
    assert g["state"] == GRANT_EXPIRED


@pytest.mark.asyncio
async def test_grant_within_horizon_still_accepts(tmp_path):
    clock = {"t": 0.0}
    d, state = _setup(tmp_path, clock=lambda: clock["t"])
    sup = state.runtime_supervisor
    sid = _cargo_session(sup).session_id
    await d.dispatch(_activate(d, sid, expires_after_ns=1_000_000_000))
    clock["t"] = 0.2  # 0.2s < 1s
    sup.launch_session(sid)
    time.sleep(0.5)
    assert _disposition(sup, sid, "c1") == "accepted"


# --------------------------------------------------------------------------
# S5c3 — adversarial / ordering.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_resurrection_by_stale_session_state(tmp_path):
    # A revoked lease stays terminal; the session's stored state cannot flip it
    # back to active. (Explicit re-activation is a NEW operator act — a
    # different path — not resurrection by stale state.)
    d, state = _setup(tmp_path)
    sup = state.runtime_supervisor
    sid = _cargo_session(sup).session_id
    await d.dispatch(_activate(d, sid))
    await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid}))
    lease = sup.get_grant_lease(sid)
    # any number of use-time checks never un-terminals it
    lease.check_expiry(sup._monotonic())
    assert lease.state == GRANT_REVOKED


@pytest.mark.asyncio
async def test_activation_then_revocation_receipts_both_present(tmp_path):
    d, state = _setup(tmp_path)
    sup = state.runtime_supervisor
    sid = _cargo_session(sup).session_id
    act = (await d.dispatch(_activate(d, sid)))["result"]
    await d.dispatch(_rpc("runtime.grant.revoke", {"session_id": sid}))
    gates = [getattr(r, "gate", None) for r in state.receipt_system.receipt_store.all()]
    assert "grant_activation" in gates and "grant_revocation" in gates
