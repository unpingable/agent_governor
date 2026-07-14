# SPDX-License-Identifier: Apache-2.0
"""Approval-witness producer — round-trip with the seam-B verifier."""

from __future__ import annotations

import json

import pytest

from governor.runtime.approval_binding import (
    REFUSAL_PLAN_REF_MISMATCH,
    REFUSAL_WITNESS_INVALID,
    ApprovalBindingError,
    verify_approval_binds_plan,
)
from governor.runtime.approval_witness import (
    WITNESS_VERSION,
    build_approval_witness,
    sanitize_ref,
    write_approval_witness,
)


# --- the load-bearing invariant: producer output verifies for its plan --------

def test_minted_witness_verifies_for_its_plan():
    pb = b"# Plan A\nplan_version: 1\nbody"
    w = build_approval_witness(pb, "approve")
    got = verify_approval_binds_plan(
        plan_bytes=pb,
        witness_bytes=w.witness_bytes,
        source_plan_digest=w.plan_ref,       # honest caller
        approval_witness_digest=w.approval_witness_digest,
    )
    assert got == w.plan_ref


def test_minted_witness_refuses_a_different_plan():
    """A witness minted for A cannot admit B — even shipping A's whole (witness,
    plan_ref) verbatim (the replay an attacker would attempt)."""
    w = build_approval_witness(b"# Plan A", "approve")
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=b"# Plan B - attacker",
            witness_bytes=w.witness_bytes,
            source_plan_digest=w.plan_ref,   # the lie
            approval_witness_digest=w.approval_witness_digest,
        )
    assert ei.value.refusal_kind == REFUSAL_PLAN_REF_MISMATCH


def test_deny_witness_does_not_authorize():
    pb = b"# Plan"
    w = build_approval_witness(pb, "deny")
    with pytest.raises(ApprovalBindingError) as ei:
        verify_approval_binds_plan(
            plan_bytes=pb, witness_bytes=w.witness_bytes,
            source_plan_digest=w.plan_ref, approval_witness_digest=w.approval_witness_digest,
        )
    assert ei.value.refusal_kind == REFUSAL_WITNESS_INVALID


def test_str_and_bytes_plan_mint_identically():
    text = "# Plan\nunicode: café\n"
    assert build_approval_witness(text, "approve") == build_approval_witness(
        text.encode("utf-8"), "approve"
    )


# --- format + determinism -----------------------------------------------------

def test_witness_format():
    w = build_approval_witness(b"# Plan", "approve")
    obj = json.loads(w.witness_bytes.decode("utf-8"))
    assert obj == {
        "witness_version": WITNESS_VERSION,
        "decision": "approve",
        "plan_ref": w.plan_ref,
    }
    assert w.plan_ref.startswith("sha256:") and len(w.plan_ref) == 7 + 64


def test_mint_is_deterministic():
    a = build_approval_witness(b"# Plan", "approve")
    b = build_approval_witness(b"# Plan", "approve")
    assert a.witness_bytes == b.witness_bytes
    assert a.approval_witness_digest == b.approval_witness_digest


def test_empty_plan_and_empty_decision_refuse():
    with pytest.raises(ValueError):
        build_approval_witness(b"", "approve")
    with pytest.raises(ValueError):
        build_approval_witness(b"# Plan", "")


# --- write path (what maude's resolver reads) ---------------------------------

def test_written_witness_is_found_by_ref_and_verifies(tmp_path):
    pb = b"# nightshift plan\nplan_version: 1\n"
    approval_ref = "operator:act-1"
    dest = write_approval_witness(tmp_path, approval_ref, pb, "approve")

    # maude's file_witness_resolver keys a non-digest ref to sanitize_ref(ref)
    assert dest == tmp_path / sanitize_ref(approval_ref)
    resolved = (tmp_path / sanitize_ref(approval_ref)).read_bytes()
    assert resolved == dest.read_bytes()

    # and the resolved bytes verify against the plan (full loop)
    w = build_approval_witness(pb, "approve")
    got = verify_approval_binds_plan(
        plan_bytes=pb, witness_bytes=resolved,
        source_plan_digest=w.plan_ref, approval_witness_digest=w.approval_witness_digest,
    )
    assert got == w.plan_ref


def test_write_refuses_to_overwrite_an_existing_witness(tmp_path):
    write_approval_witness(tmp_path, "operator:act-1", b"# Plan A", "approve")
    with pytest.raises(FileExistsError):
        write_approval_witness(tmp_path, "operator:act-1", b"# Plan B", "approve")


def test_sanitize_ref_matches_maude_convention():
    # pinned to maude/plan/witness.py sanitize_ref (non-[A-Za-z0-9._-] -> _)
    assert sanitize_ref("operator:act-1") == "operator_act-1"
    assert sanitize_ref("a/b c") == "a_b_c"
    assert sanitize_ref("keep.dash-_ok") == "keep.dash-_ok"


# --- operator CLI surface -----------------------------------------------------

def test_cli_approve_plan_mints_bound_witness(tmp_path):
    from click.testing import CliRunner

    from governor.cli import cli

    plan = tmp_path / "plan.md"
    plan.write_text("# nightshift plan\nplan_version: 1\n")
    wdir = tmp_path / "witnesses"

    r = CliRunner().invoke(cli, [
        "runtime", "approve-plan", str(plan),
        "--ref", "operator:act-1", "--witness-dir", str(wdir), "--json",
    ])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    witness_bytes = (wdir / sanitize_ref("operator:act-1")).read_bytes()
    got = verify_approval_binds_plan(
        plan_bytes=plan.read_bytes(), witness_bytes=witness_bytes,
        source_plan_digest=out["plan_ref"],
        approval_witness_digest=out["approval_witness_digest"],
    )
    assert got == out["plan_ref"]

    # second run refuses to overwrite the approval act
    r2 = CliRunner().invoke(cli, [
        "runtime", "approve-plan", str(plan),
        "--ref", "operator:act-1", "--witness-dir", str(wdir),
    ])
    assert r2.exit_code != 0
