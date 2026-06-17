# SPDX-License-Identifier: Apache-2.0
"""Stage 3b2: the first real bounded effect — exclusive create_new of a fixed-content marker.

Real `la_cli` + `transition-cli`. Proves the terminal vocabulary, the required ordering, idempotency, and
replay-legible reconciliation at every crash point.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.transition_enforce import (
    CRASH_AFTER_ATTEMPT,
    CRASH_AFTER_CONSUME,
    CRASH_AFTER_EFFECT,
    CRASH_BEFORE_CONSUME,
    T_CONFLICT,
    T_REFUSED,
    T_SUCCEEDED,
    T_UNKNOWN,
    MarkerActuator,
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
CONTENT = b"create_marker_v1:fixed-bytes"


def _setup(tmp_path):
    la = LASubprocess(LA_CLI)
    la.start()
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    la.deposit(SCOPE, 5)
    dec = la.request_capacity(
        {
            "request_id": "r1", "actor": "ag:main", "action": "write", "target": "demo",
            "scope": SCOPE, "requested_capacity": 5, "eligibility_reference": ELIG,
            "eligibility_valid_until": 1000, "expires_after": 1000, "idempotency_key": None,
        },
        10,
    )
    assert dec["decision"] == "Granted"
    return la, transition


def _marker(tmp_path, name="m"):
    return MarkerActuator(tmp_path / "sandbox", name, CONTENT)


def _enforce(transition, la, durable, actuator, *, op="op-1", cap="c", **kw):
    return enforce_chain(
        transition, la, token_handle="t0", scope=SCOPE, target="demo",
        effect_class="create_marker_v1", operation_hash=op, consumer="ag:main",
        eligibility_reference=ELIG, capability_id=cap, valid_until=1000, now=10,
        durable_path=durable, actuator=actuator, **kw,
    )


def test_marker_created_once_and_verified(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        act = _marker(tmp_path)
        res = _enforce(transition, la, durable, act)

        assert res["result"] == T_SUCCEEDED
        assert res["operational"] is True
        # The real marker exists with the exact fixed content.
        assert act.marker_path.read_bytes() == CONTENT
        assert hashlib.sha256(act.marker_path.read_bytes()).hexdigest() == act.content_sha256

        # Required ordering on disk: consume -> attempt -> outcome.
        kinds = [json.loads(l)["kind"] for l in durable.read_text().splitlines() if l.strip()]
        assert kinds == ["consume_receipt", "effect_attempt", "effect_outcome"]
        assert reconstruct(durable) == {res["consumption_event_id"]: T_SUCCEEDED}

        # Replay of the same operation refuses at LA (the effect does not run twice).
        again = _enforce(transition, la, durable, _marker(tmp_path))
        assert again["result"] == T_REFUSED and "AlreadyConsumed" in again["reason"]
    finally:
        la.close()


def test_crash_before_consume_is_not_spent(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        res = _enforce(transition, la, durable, _marker(tmp_path), op="op-A",
                       crash_at=CRASH_BEFORE_CONSUME)
        assert res["result"] == "crashed_before_consume"
        assert res["operational"] is False
        # Nothing spent, nothing durable: a newly admitted operation may retry.
        assert reconstruct(durable) == {}
        assert not (tmp_path / "sandbox" / "m.marker").exists()
    finally:
        la.close()


def test_crash_after_consume_before_attempt_is_outcome_unknown(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        res = _enforce(transition, la, durable, _marker(tmp_path), op="op-B",
                       crash_at=CRASH_AFTER_CONSUME)
        assert res["result"] == "crashed"
        assert reconstruct(durable) == {"op-B:c": T_UNKNOWN}
    finally:
        la.close()


def test_crash_after_attempt_before_effect_is_outcome_unknown(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        res = _enforce(transition, la, durable, _marker(tmp_path), op="op-C",
                       crash_at=CRASH_AFTER_ATTEMPT)
        assert res["result"] == "crashed"
        # Marker absent -> a classed non-effect terminal, never success.
        assert reconstruct(durable) == {"op-C:c": T_UNKNOWN}
        assert not (tmp_path / "sandbox" / "m.marker").exists()
    finally:
        la.close()


def test_crash_after_effect_reconciles_success_from_marker(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        # The effect runs (marker created) but the success receipt is never written.
        res = _enforce(transition, la, durable, _marker(tmp_path), op="op-D",
                       crash_at=CRASH_AFTER_EFFECT)
        assert res["result"] == "crashed"
        # Reconciliation recovers EffectSucceeded from the exact expected marker — without repeating it.
        assert (tmp_path / "sandbox" / "m.marker").read_bytes() == CONTENT
        assert reconstruct(durable) == {"op-D:c": T_SUCCEEDED}
    finally:
        la.close()


def test_crash_after_effect_with_wrong_marker_is_conflict_never_success(tmp_path):
    la, transition = _setup(tmp_path)
    try:
        durable = tmp_path / "l.jsonl"
        # A pre-existing marker with WRONG content: create_new fails, and reconcile must classify the
        # wrong-content marker as a conflict — never success.
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir(parents=True)
        (sandbox / "m.marker").write_bytes(b"someone-elses-bytes")
        res = _enforce(transition, la, durable, _marker(tmp_path), op="op-E",
                       crash_at=CRASH_AFTER_EFFECT)
        assert res["result"] == "crashed"
        assert reconstruct(durable) == {"op-E:c": T_CONFLICT}
    finally:
        la.close()
