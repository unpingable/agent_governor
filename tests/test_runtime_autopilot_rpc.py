# SPDX-License-Identifier: Apache-2.0
"""GS-7: `runtime.autopilot.get` / `runtime.autopilot.set` daemon methods.

The envelope-strip truth (read) + the workspace-default profile switch (write,
receipt-citing). Workspace-scoped ONLY — GS-7 stop condition: no per-RUNNING-
session envelope mutation. `get` is read-only; `set` is mutating, emits a
profile-change gate receipt, and refuses an unknown profile with the closed
`unknown_profile` vocab.
"""

from __future__ import annotations

import json

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


def _autopilot_receipts(gov_dir):
    path = gov_dir / "receipts" / "gate_receipts.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("gate") == "autopilot":
            out.append(rec)
    return out


# --- registration ---------------------------------------------------------- #


@pytest.mark.asyncio
async def test_autopilot_get_is_read_only_set_is_mutating(dispatcher):
    d, _ = dispatcher
    flags = d.get_method_info()
    assert flags.get("runtime.autopilot.get") == "read_only"
    assert d.is_mutating("runtime.autopilot.get") is False
    # The set door MUST be classified mutating.
    assert d.is_mutating("runtime.autopilot.set") is True


# --- get: the envelope strip ----------------------------------------------- #


@pytest.mark.asyncio
async def test_get_returns_workspace_default_envelope_strip(dispatcher):
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.get")
    assert "error" not in resp
    view = resp["result"]
    # System default with no intent set is `established`.
    assert view["profile"] == "established"
    assert view["known_profile"] is True
    assert view["scope"] == "workspace_default"
    assert set(view["available"]) == {
        "greenfield", "established", "production", "hotfix", "refactor"
    }
    s = view["settings"]
    assert s["approval_path"] == "prompt"
    assert s["anchor_strictness"] == "soft"
    assert s["envelope"] == "exploratory"
    assert s["change_ceiling"] is None


# --- set: the workspace switch --------------------------------------------- #


@pytest.mark.asyncio
async def test_set_switches_profile_emits_receipt_and_get_reflects(dispatcher, gov_dir):
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.set",
                       {"profile": "production", "reason": "ship day"})
    assert "error" not in resp
    res = resp["result"]
    assert res["changed"] is True
    assert res["previous_profile"] == "established"
    assert res["profile"] == "production"
    # With no higher-priority layer, effective profile == what we set == subject.
    assert res["requested_profile"] == "production"
    assert res["receipt_id"]
    # Envelope strip now reflects the production envelope.
    assert res["settings"]["approval_path"] == "require_human"
    assert res["settings"]["envelope"] == "strict"
    ceiling = res["settings"]["change_ceiling"]
    assert ceiling["max_files"] == 20 and ceiling["max_loc"] == 500

    # A fresh get reflects the persisted workspace default.
    resp2 = await _call(d, "runtime.autopilot.get")
    assert resp2["result"]["profile"] == "production"

    # The profile-change receipt persisted, gate=autopilot, verdict=pass.
    recs = _autopilot_receipts(gov_dir)
    assert len(recs) == 1
    assert recs[0]["verdict"] == "pass"
    assert recs[0]["receipt_id"] == res["receipt_id"]


# --- set: refusal (closed vocab) ------------------------------------------- #


@pytest.mark.asyncio
async def test_set_unknown_profile_refuses_and_writes_nothing(dispatcher, gov_dir):
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.set", {"profile": "banana"})
    assert "error" not in resp  # typed refusal rides in the result, not a JSON-RPC error
    res = resp["result"]
    assert res["changed"] is False
    assert res["error"] == "unknown_profile"
    assert res["profile"] == "banana"
    assert "established" in res["available"]
    # Nothing written: no receipt, and get still shows the default.
    assert _autopilot_receipts(gov_dir) == []
    resp2 = await _call(d, "runtime.autopilot.get")
    assert resp2["result"]["profile"] == "established"


@pytest.mark.asyncio
async def test_set_missing_profile_refuses_unknown_profile(dispatcher):
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.set", {})
    res = resp["result"]
    assert res["changed"] is False
    assert res["error"] == "unknown_profile"


# --- STOP condition: workspace-scoped only, no per-running-session mutation -- #


@pytest.mark.asyncio
async def test_set_rejects_session_id_scoped_mutation(dispatcher, gov_dir):
    """A per-session target is a malformed call for this method (mid-session
    envelope change is forbidden). Fail closed; nothing written."""
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.set",
                       {"profile": "production", "session_id": "sess_A"})
    assert "error" in resp
    assert "workspace-scoped" in resp["error"]["message"]
    # Refused before any write.
    assert _autopilot_receipts(gov_dir) == []
    resp2 = await _call(d, "runtime.autopilot.get")
    assert resp2["result"]["profile"] == "established"


@pytest.mark.asyncio
async def test_set_rejects_empty_session_id_key_presence_not_truthiness(dispatcher, gov_dir):
    """The guard is key-presence, not truthiness: a falsy session_id still
    signals per-session intent and must be rejected (codex hardening)."""
    d, _ = dispatcher
    for bad in ("", 0, False, None):
        resp = await _call(d, "runtime.autopilot.set",
                           {"profile": "production", "session_id": bad})
        assert "error" in resp, f"session_id={bad!r} should be rejected"
        assert "workspace-scoped" in resp["error"]["message"]
    assert _autopilot_receipts(gov_dir) == []


@pytest.mark.asyncio
async def test_reset_same_profile_reports_changed_false_but_still_receipts(dispatcher, gov_dir):
    """Re-affirming the active profile is honestly reported changed=False, yet
    the operator action is still recorded (receipt emitted) — idempotence in
    the reported delta, not a dropped audit record."""
    d, _ = dispatcher
    # Default profile is `established`; set it again.
    resp = await _call(d, "runtime.autopilot.set", {"profile": "established"})
    res = resp["result"]
    assert res["changed"] is False
    assert res["previous_profile"] == "established"
    assert res["profile"] == "established"
    assert res["receipt_id"]
    assert len(_autopilot_receipts(gov_dir)) == 1


@pytest.mark.asyncio
async def test_set_fails_closed_when_standing_required_and_no_token(dispatcher, gov_dir, monkeypatch):
    """The change cites the operator via the canonical resolve_principal path:
    when standing is required and no verifiable token is supplied, `set` fails
    closed (AUTH_ERROR) and writes nothing — the operator cannot be forged into
    the receipt by an unauthenticated caller."""
    d, state = dispatcher
    monkeypatch.setattr(type(state), "require_standing", property(lambda self: True))
    resp = await _call(d, "runtime.autopilot.set", {"profile": "production"})
    assert "error" in resp
    assert resp["error"]["code"] == -32001  # AUTH_ERROR
    # Nothing recorded; the change was refused before the receipt.
    assert _autopilot_receipts(gov_dir) == []


@pytest.mark.asyncio
async def test_set_surfaces_higher_priority_override_vs_receipt_subject(dispatcher, gov_dir, monkeypatch):
    """NEW-ISSUE pin (codex): a higher-priority intent layer (GOV_PROFILE env)
    outranks the workspace default we write. The effective `profile` then
    differs from what we set — but the receipted subject is surfaced explicitly
    as `requested_profile`, never a silent mismatch."""
    d, _ = dispatcher
    monkeypatch.setenv("GOV_PROFILE", "hotfix")  # Layer 2 outranks the session layer
    resp = await _call(d, "runtime.autopilot.set", {"profile": "production"})
    res = resp["result"]
    # Effective resolution is still the env override...
    assert res["profile"] == "hotfix"
    assert res["resolved_from"] == "env"
    # ...but what we set / receipted is explicit and honest.
    assert res["requested_profile"] == "production"
    # Env dominated before and after, so the effective profile did not move.
    assert res["changed"] is False
    assert res["receipt_id"]
    assert len(_autopilot_receipts(gov_dir)) == 1


@pytest.mark.asyncio
async def test_forged_principal_id_is_not_trusted_into_receipt(dispatcher, gov_dir):
    """WARN pin (codex): with standing not required and client-trust not enabled
    (the default), a caller-supplied principal_id is IGNORED — the receipt cites
    `local`, not the forged identity. Operator attribution is not forgeable."""
    d, _ = dispatcher
    resp = await _call(d, "runtime.autopilot.set",
                       {"profile": "production", "principal_id": "admin_forged"})
    assert resp["result"]["changed"] is True
    recs = _autopilot_receipts(gov_dir)
    assert len(recs) == 1
    assert recs[0]["principal_id"] == "local"
    assert recs[0]["principal_id"] != "admin_forged"


@pytest.mark.asyncio
async def test_autopilot_never_consults_the_runtime_supervisor(dispatcher, monkeypatch):
    """Adversarial pin for the stop condition: get/set derive purely from the
    workspace intent/config layers and must never reach into the supervised
    runtime. Point runtime_supervisor at a booby-trap that raises on ANY access
    — get and set must still succeed."""
    d, state = dispatcher

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"autopilot must not touch the supervisor (accessed {name!r})")

    monkeypatch.setattr(type(state), "runtime_supervisor", property(lambda self: _Boom()))
    get_resp = await _call(d, "runtime.autopilot.get")
    assert get_resp["result"]["profile"] == "established"
    set_resp = await _call(d, "runtime.autopilot.set", {"profile": "refactor"})
    assert set_resp["result"]["changed"] is True
    assert set_resp["result"]["profile"] == "refactor"
