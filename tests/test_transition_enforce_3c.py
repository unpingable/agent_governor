# SPDX-License-Identifier: Apache-2.0
"""Stage 3c: the composed durable receipt pins the admission snapshot that governed the effect.

3b proved "capacity was consumed and an effect happened." 3c proves the stronger composed-coherence
property: a verifier can reconstruct **the exact composed admission snapshot under which the effect was
allowed**, and any chain that describes a different admission state than the one that governed the effect
is rejected.

Integration tests run the real `la_cli` + `transition-cli`; the incoherence tests drive the durable store
and `reconstruct_composed` directly (the kernel never emits an incoherent chain — these prove the verifier
refuses a tampered or lossy one).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.transition_enforce import (
    CRASH_AFTER_CONSUME,
    T_SUCCEEDED,
    T_UNKNOWN,
    MarkerActuator,
    composed_snapshot_hash,
    enforce_chain,
    reconstruct_composed,
    verify_snapshot_coherence,
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


def _setup():
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


def _enforce(transition, la, durable, actuator, *, op="op-1", cap="c", **kw):
    return enforce_chain(
        transition, la, token_handle="t0", scope=SCOPE, target="demo",
        effect_class="create_marker_v1", operation_hash=op, consumer="ag:main",
        eligibility_reference=ELIG, capability_id=cap, valid_until=1000, now=10,
        durable_path=durable, actuator=actuator, **kw,
    )


def _records(durable: Path):
    return [json.loads(line) for line in durable.read_text().splitlines() if line.strip()]


def _rewrite(durable: Path, records):
    durable.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))


# --- the kernel pins the snapshot; Python reconstructs the identical hash ---- #


def test_kernel_and_python_canonical_hash_agree(tmp_path):
    """The cross-language integrity check: the kernel's snapshot_hash must recompute byte-for-byte in
    Python (RFC 8785 JCS + SHA-256). If this ever fails, the two canonicalizations have drifted and the
    durable coherence check is silently worthless."""
    la, transition = _setup()
    try:
        bundle = {
            "office_outputs": {
                "standing": "verified", "standing_receipt_ref": ELIG,
                "la_admission": "admitted", "la_consume": "consumed", "scope": SCOPE, "target": "demo",
            },
            "capability": {
                "capability_id": "c", "scope": SCOPE, "target": "demo",
                "effect_class": "create_marker_v1", "eligibility_reference": ELIG,
                "expires_at": 1000, "single_use": True,
            },
            "revalidation": {"standing_ref": ELIG, "live": True, "valid_until": 1000, "now": 10},
            "operation": {"operation_hash": "op-1", "consumer": "ag:main"},
            "requested": {
                "operation_hash": "op-1", "consumer": "ag:main", "scope": SCOPE, "target": "demo",
                "effect_class": "create_marker_v1", "capability_nonce": "c", "now": 10,
            },
        }
        corr = transition.correspondence_check(bundle)
        assert corr["result"] == "correspondence_ok"
        assert composed_snapshot_hash(corr["composed_snapshot"]) == corr["snapshot_hash"]
    finally:
        la.close()


def test_success_chain_reconstructs_coherent_with_snapshot(tmp_path):
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT))
        out = reconstruct_composed(durable)
        entry = out["op-1:c"]
        assert entry["outcome"] == T_SUCCEEDED
        assert entry["coherent"] is True and entry["incoherence"] is None
        # The governing admission snapshot is attached and pins the execution clock.
        assert entry["snapshot"]["eligibility_reference"] == ELIG
        assert entry["snapshot"]["revalidated_at"] == 10
        assert entry["snapshot"]["revalidation_valid_until"] == 1000
    finally:
        la.close()


def test_replay_reconstructs_identical_snapshot_hash(tmp_path):
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT))
        first = reconstruct_composed(durable)["op-1:c"]["snapshot_hash"]
        second = reconstruct_composed(durable)["op-1:c"]["snapshot_hash"]
        assert first == second, "replay must reconstruct the identical snapshot hash"
    finally:
        la.close()


def test_crash_after_consume_keeps_governing_snapshot_attached(tmp_path):
    """Consumed + OutcomeUnknown — but the governing snapshot is still reconstructable, because it was
    pinned durably BEFORE the burn."""
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT),
                 crash_at=CRASH_AFTER_CONSUME)
        entry = reconstruct_composed(durable)["op-1:c"]
        assert entry["outcome"] == T_UNKNOWN
        assert entry["coherent"] is True
        assert entry["snapshot"]["consumption_event_id"] == "op-1:c"
        assert entry["snapshot"]["revalidated_at"] == 10
    finally:
        la.close()


# --- a chain that describes a different admission state is rejected ----------- #


def test_tampered_snapshot_field_is_incoherent(tmp_path):
    """Edit a governing fact in the durable snapshot without re-deriving the hash: the recomputed hash no
    longer matches, so the chain no longer proves same-snapshot coherence."""
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT))
        recs = _records(durable)
        for r in recs:
            if r["kind"] == "composed_snapshot":
                r["snapshot"]["eligibility_reference"] = "sha256:FORGED"
        _rewrite(durable, recs)
        entry = reconstruct_composed(durable)["op-1:c"]
        assert entry["coherent"] is False
        assert entry["incoherence"] == "snapshot_hash_mismatch"
    finally:
        la.close()


def test_consume_referencing_a_different_snapshot_hash_is_incoherent(tmp_path):
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT))
        recs = _records(durable)
        for r in recs:
            if r["kind"] == "consume_receipt":
                r["snapshot_hash"] = "sha256:some-other-snapshot"
        _rewrite(durable, recs)
        entry = reconstruct_composed(durable)["op-1:c"]
        assert entry["coherent"] is False
        assert entry["incoherence"] == "consume_snapshot_hash_mismatch"
    finally:
        la.close()


def test_consume_without_any_snapshot_is_incoherent(tmp_path):
    """A consumed event whose composed snapshot record is absent — the very gap Stage 3c closes — must not
    read as coherent."""
    la, transition = _setup()
    try:
        durable = tmp_path / "l.jsonl"
        _enforce(transition, la, durable, MarkerActuator(tmp_path / "sb", "m", CONTENT))
        recs = [r for r in _records(durable) if r["kind"] != "composed_snapshot"]
        _rewrite(durable, recs)
        entry = reconstruct_composed(durable)["op-1:c"]
        assert entry["coherent"] is False
        assert entry["incoherence"] == "missing_snapshot"
    finally:
        la.close()


# --- the lossy-receipt case (no kernel/LA needed) ---------------------------- #


class _FakeLA:
    """Mints a capability and records whether consume was ever reached."""

    def __init__(self):
        self.consumed = False

    def issue_capability(self, token, target, effect_class, cap_id, *, now):
        return {
            "capability_id": cap_id, "scope": SCOPE, "target": target, "effect_class": effect_class,
            "eligibility_reference": ELIG, "expires_at": 1000, "single_use": True,
        }

    def consume(self, *_a, **_k):
        self.consumed = True
        return {"decision": "Consumed"}


class _NoSnapshotKernel:
    """A kernel that passes correspondence but emits no composed snapshot (e.g. a pre-3c build)."""

    def correspondence_check(self, _bundle):
        return {"result": "correspondence_ok", "consumption_event_id": "op:c",
                "eligibility_reference": ELIG}


def test_missing_composed_snapshot_fails_closed(tmp_path):
    """A kernel that cannot pin the composed snapshot must not be allowed to spend — fail-closed before
    the burn, nothing durable but the infra refusal."""
    la = _FakeLA()
    durable = tmp_path / "l.jsonl"
    res = enforce_chain(
        _NoSnapshotKernel(), la, token_handle="t0", scope=SCOPE, target="demo",
        effect_class="create_marker_v1", operation_hash="op", consumer="ag:main",
        eligibility_reference=ELIG, capability_id="c", valid_until=1000, now=10, durable_path=durable,
    )
    assert res["result"].startswith("not_consumed") or res["operational"] is False
    assert res["reason"] == "composed_snapshot_missing"
    assert la.consumed is False, "fail-closed: no burn when the snapshot cannot be pinned"
    recs = _records(durable)
    assert recs == [{"kind": "infra_refusal", "reason": "composed_snapshot_missing"}]


def test_lossy_snapshot_without_execution_clock_is_rejected():
    """A snapshot that claims liveness but pins no execution clock cannot distinguish two execution
    snapshots over one lineage — the case the Lean lossy_receipt_cannot_pin_snapshot model rules out."""
    snapshot = {
        "schema": "transition_kernel.composed_snapshot.v1", "kernel_version": "0.0.0",
        "operation_hash": "op", "admission_candidate_hash": "sha256:abc",
        "eligibility_reference": ELIG, "revalidation_live": True, "revalidation_valid_until": 1000,
        "revalidated_at": 0, "capability_nonce": "c", "consumption_event_id": "op:c",
        "consumer": "ag:main", "scope": SCOPE, "target": "demo", "effect_class": "create_marker_v1",
    }
    assert verify_snapshot_coherence("op:c", snapshot, composed_snapshot_hash(snapshot)) \
        == "missing_revalidation_clock"
