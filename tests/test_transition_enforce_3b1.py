# SPDX-License-Identifier: Apache-2.0
"""Stage 3b1 review proofs: live LA consumption, LA as the sole authoritative burn.

Real `la_cli` + real `transition-cli`. Capacity is actually spent (`operational: true`); the actuator is
still fake.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.transition_enforce import (
    CRASH_AFTER_CONSUME,
    T_NOT_ATTEMPTED,
    T_REFUSED,
    T_UNKNOWN,
    enforce_chain,
    reconstruct,
)
from governor.runtime.transition_subprocess import DEFAULT_TRANSITION_CLI, TransitionSubprocess

LA_CLI = os.environ.get("GOVERNOR_LA_CLI", DEFAULT_LA_CLI)
TK_CLI = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)

pytestmark = pytest.mark.skipif(
    not (Path(LA_CLI).exists() and Path(TK_CLI).exists()),
    reason="la_cli and/or transition-cli not built",
)

SCOPE = "lab"
ELIG = "sha256:standing-xyz"


def _granted_token(la: LASubprocess, *, capacity: int = 5, now: int = 10) -> str:
    la.deposit(SCOPE, capacity)
    dec = la.request_capacity(
        {
            "request_id": "r1", "actor": "ag:main", "action": "write", "target": "demo",
            "scope": SCOPE, "requested_capacity": capacity, "eligibility_reference": ELIG,
            "eligibility_valid_until": 1000, "expires_after": 1000, "idempotency_key": None,
        },
        now,
    )
    assert dec["decision"] == "Granted", dec
    return dec["token_id"]  # opaque handle "t0"


def _enforce(transition, la, durable, *, capability_id="nonce-1", op="op-1", now=10, **kw):
    return enforce_chain(
        transition, la, token_handle="t0", scope=SCOPE, target="demo", effect_class="fs_write",
        operation_hash=op, consumer="ag:main", eligibility_reference=ELIG,
        capability_id=capability_id, valid_until=1000, now=now, durable_path=durable, **kw,
    )


def test_live_consume_spends_capacity_and_is_operational(tmp_path):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    try:
        _granted_token(la, capacity=3)
        durable = tmp_path / "ledger.jsonl"
        res = _enforce(transition, la, durable)

        # Real consequence: capacity spent, operational true, but the effect was fake (not attempted).
        assert res["result"] == T_NOT_ATTEMPTED
        assert res["operational"] is True

        # The composed snapshot is pinned before the burn; the consume receipt is durable and written
        # BEFORE the effect outcome (Stage 3c order: snapshot -> consume -> outcome).
        records = [json.loads(l) for l in durable.read_text().splitlines() if l.strip()]
        assert [r["kind"] for r in records] == ["composed_snapshot", "consume_receipt", "effect_outcome"]
        consume = next(r for r in records if r["kind"] == "consume_receipt")
        assert consume["operational"] is True

        # Reconstruction: spent, effect not attempted.
        assert reconstruct(durable) == {res["consumption_event_id"]: T_NOT_ATTEMPTED}
    finally:
        la.close()


def test_replay_refuses_via_la_authoritative_burn(tmp_path):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    try:
        _granted_token(la, capacity=3)
        durable = tmp_path / "ledger.jsonl"
        first = _enforce(transition, la, durable, capability_id="n", op="op-X")
        assert first["result"] == T_NOT_ATTEMPTED

        # Same operation + capability => same consumption_event_id => LA AlreadyConsumed.
        again = _enforce(transition, la, durable, capability_id="n", op="op-X")
        assert again["result"] == T_REFUSED
        assert "AlreadyConsumed" in again["reason"]
    finally:
        la.close()


def test_eligibility_reference_survives_end_to_end(tmp_path):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    try:
        _granted_token(la)
        # The capability LA mints binds the grant's eligibility verbatim; correspondence echoes it; a
        # drift would have refused. Reaching "consumed" proves it survived.
        res = _enforce(transition, la, tmp_path / "l.jsonl")
        assert res["result"] == T_NOT_ATTEMPTED
        assert res["consumption_event_id"].startswith("op-1:")
    finally:
        la.close()


def test_process_death_after_consume_is_spent_outcome_unknown(tmp_path):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    try:
        _granted_token(la)
        durable = tmp_path / "l.jsonl"
        res = _enforce(transition, la, durable, capability_id="c", op="op-crash",
                       crash_at=CRASH_AFTER_CONSUME)
        assert res["result"] == "crashed"
        assert res["operational"] is True

        # Reconstruction sees spent + outcome unknown — NOT permission to replay.
        assert reconstruct(durable) == {"op-crash:c": T_UNKNOWN}

        # And a replay of the same event still refuses (LA spent it).
        again = _enforce(transition, la, durable, capability_id="c", op="op-crash")
        assert again["result"] == T_REFUSED and "AlreadyConsumed" in again["reason"]
    finally:
        la.close()


def test_fail_closed_never_observe(tmp_path):
    # No real binaries needed: stubs prove the enforce path refuses (never observes) when a boundary is
    # unavailable, and that nothing is consumed.
    durable = tmp_path / "l.jsonl"

    class _DeadTransition:
        def correspondence_check(self, _inner):
            return None  # transport failure

    class _La:
        def __init__(self):
            self.consumed = False

        def issue_capability(self, *a, **k):
            return {
                "capability_id": "c", "scope": SCOPE, "target": "demo", "effect_class": "fs_write",
                "eligibility_reference": ELIG, "expires_at": 1000, "single_use": True,
            }

        def consume(self, *a, **k):
            self.consumed = True
            return {"decision": "Consumed"}

    la = _La()
    res = enforce_chain(
        _DeadTransition(), la, token_handle="t0", scope=SCOPE, target="demo",
        effect_class="fs_write", operation_hash="op", consumer="ag:main", eligibility_reference=ELIG,
        capability_id="c", valid_until=1000, now=10, durable_path=durable,
    )
    assert res["result"] == T_REFUSED
    assert res["reason"] == "transition_unavailable"
    assert la.consumed is False, "fail-closed: no consume when the kernel is unavailable"
    # Fail-closed is not fail-silent: the infra refusal is recorded durably, and no consume happened.
    import json as _json
    recs = [_json.loads(l) for l in durable.read_text().splitlines() if l.strip()]
    assert recs == [{"kind": "infra_refusal", "reason": "transition_unavailable"}]
