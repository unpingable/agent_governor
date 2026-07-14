# SPDX-License-Identifier: Apache-2.0
"""Approval-binds-plan_ref (seam B) — the verifier's acceptance criteria."""

from __future__ import annotations

import hashlib
import json

import pytest

from governor.runtime.approval_binding import (
    MAX_PLAN_BYTES,
    REFUSAL_PLAN_REF_MISMATCH,
    REFUSAL_WITNESS_INVALID,
    ApprovalBindingError,
    verify_approval_binds_plan,
)


def _plan_ref(pb: bytes) -> str:
    return "sha256:" + hashlib.sha256(pb).hexdigest()


def _witness(plan_ref: str, *, version="approval-witness/v1", decision="approve", extra=None):
    """Mint a self-consistent witness (bytes + its integrity digest)."""
    obj = {"witness_version": version, "decision": decision, "plan_ref": plan_ref}
    if extra:
        obj.update(extra)
    wb = json.dumps(obj).encode("utf-8")
    wd = "sha256:" + hashlib.sha256(wb).hexdigest()
    return wb, wd


# --- AC2: positive twin -------------------------------------------------------

def test_binds_the_correct_plan():
    pb = b"# Plan A\nplan_version: 1\nbody"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr)
    got = verify_approval_binds_plan(
        plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
    )
    assert got == pr


def test_bare_hex_source_digest_normalizes_and_binds():
    pb = b"# Plan A"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr)
    # caller supplies source_plan_digest as bare 64-hex (no prefix)
    got = verify_approval_binds_plan(
        plan_bytes=pb, witness_bytes=wb,
        source_plan_digest=pr[len("sha256:"):], approval_witness_digest=wd,
    )
    assert got == pr


# --- AC1 / AC3: the replay defense (load-bearing) -----------------------------

def test_replay_refuses_even_when_caller_lies_about_source_digest():
    """Witness authentic for Plan A, run against Plan B, caller sets
    source_plan_digest == witness.plan_ref to look consistent. Must refuse —
    AG re-hashes the ACTUAL plan bytes."""
    plan_a = b"# Plan A - the approved one"
    plan_b = b"# Plan B - the attacker's plan"
    ref_a = _plan_ref(plan_a)
    wb, wd = _witness(ref_a)  # witness attests plan A
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=plan_b,          # actually running B
            witness_bytes=wb,           # A's witness
            source_plan_digest=ref_a,   # the lie: claims B is A
            approval_witness_digest=wd,
        )
    assert ei.value.refusal_kind == REFUSAL_PLAN_REF_MISMATCH


def test_honest_source_digest_for_wrong_plan_also_refuses():
    """Caller is honest (source_plan_digest = sha256(plan_b)) but the witness
    names plan A — witness.plan_ref != sha256(plan_b) → refuse."""
    plan_a = b"# Plan A"
    plan_b = b"# Plan B"
    wb, wd = _witness(_plan_ref(plan_a))
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=plan_b, witness_bytes=wb,
            source_plan_digest=_plan_ref(plan_b), approval_witness_digest=wd,
        )
    assert ei.value.refusal_kind == REFUSAL_PLAN_REF_MISMATCH


# --- AC4 / #5: mandatory bytes, fail-closed -----------------------------------

@pytest.mark.parametrize("missing", ["plan", "witness"])
def test_missing_bytes_refuse_fail_closed(missing):
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr)
    kwargs = dict(plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd)
    kwargs["plan_bytes" if missing == "plan" else "witness_bytes"] = None
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(**kwargs)
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


@pytest.mark.parametrize("empty", [b"", "   ".encode()])
def test_empty_plan_bytes_refuses(empty):
    wb, wd = _witness(_plan_ref(empty or b"x"))
    with pytest.raises(ApprovalBindingError):
        verify_approval_binds_plan(
            plan_bytes=b"", witness_bytes=wb,
            source_plan_digest="sha256:" + "0" * 64, approval_witness_digest=wd,
        )


# --- witness integrity + structural validity ----------------------------------

def test_witness_integrity_mismatch_refuses():
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb, _ = _witness(pr)
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr,
            approval_witness_digest="sha256:" + "a" * 64,  # wrong digest
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_non_json_witness_refuses():
    pb = b"# Plan"
    wb = b"not json at all"
    wd = "sha256:" + hashlib.sha256(wb).hexdigest()
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=_plan_ref(pb),
            approval_witness_digest=wd,
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_missing_witness_key_refuses():
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb = json.dumps({"witness_version": "approval-witness/v1", "decision": "approve"}).encode()
    wd = "sha256:" + hashlib.sha256(wb).hexdigest()
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_unknown_witness_version_refuses():
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr, version="approval-witness/v99")
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_non_approving_decision_refuses():
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr, decision="deny")
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


@pytest.mark.parametrize("bad", [{"a": 1}, ["x"], 42])
def test_non_bytes_evidence_refuses_within_vocabulary(bad):
    """Hostile-input hardening (sandwich finding): a dict/list/int passed as
    plan_bytes must refuse with the closed refusal, not a raw TypeError."""
    pb = b"# Plan"
    pr = _plan_ref(pb)
    wb, wd = _witness(pr)
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=bad, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_oversize_plan_refuses():
    pb = b"x" * (MAX_PLAN_BYTES + 1)
    pr = _plan_ref(pb)
    wb, wd = _witness(pr)
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


# --- snapshot / input-shape handling ------------------------------------------

def test_bytearray_and_str_inputs_snapshot_and_bind():
    text = "# Plan A\nunicode: café"
    pb_bytes = text.encode("utf-8")
    pr = _plan_ref(pb_bytes)
    wb, wd = _witness(pr)
    # str plan_bytes (the JSON-RPC carriage) encodes to the exact bytes
    assert verify_approval_binds_plan(
        plan_bytes=text, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
    ) == pr
    # bytearray is copied to immutable bytes; mutating the caller's buffer after
    # the call cannot have changed the verified identity
    ba = bytearray(pb_bytes)
    assert verify_approval_binds_plan(
        plan_bytes=ba, witness_bytes=wb, source_plan_digest=pr, approval_witness_digest=wd
    ) == pr
    ba.extend(b"tamper")
    assert _plan_ref(bytes(ba)) != pr  # the mutated buffer would NOT have bound
