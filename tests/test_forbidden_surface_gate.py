# SPDX-License-Identifier: Apache-2.0
"""ForbiddenSurfaceGate — semantic-surface classification beside DiffPathScopeGate.

Proves: path-allowed-but-semantically-forbidden changes are rejected; semantic-allowed
pass; ambiguous → CANNOT_TESTIFY; the projection runs through existing ag_admit; and the
dumb conductor (unchanged) records detected surfaces.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

from governor.ag_admit import CandidateStep, DiffPathScopeGate, StepVerdict, ag_admit
from governor.forbidden_surface_gate import (
    REASON_CANNOT_OBSERVE_DIFF,
    REASON_NO_FORBIDDEN_SURFACE,
    REASON_SEMANTIC_AMBIGUOUS,
    REASON_SEMANTIC_FORBIDDEN,
    ForbiddenSurfaceGate,
    _scan_diff,
)
from governor.gate_receipt import GateReceiptSystem

_WORKING = pathlib.Path(__file__).resolve().parents[1] / "working"
sys.path.insert(0, str(_WORKING))
import ag_admit_conductor  # noqa: E402


def _diff_modify(path: str, added: str = "new", removed: str = "old") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{removed}\n+{added}\n"
    )


def _step(diff: str, scope: str = "*") -> CandidateStep:
    return CandidateStep(
        step_id="s",
        repo="agent_gov",
        base_commit="HEAD",
        diff=diff,
        declared_intent="x",
        scope=scope,
    )


def _admit(diff: str, gate=None):
    return asyncio.run(ag_admit(_step(diff), gate or ForbiddenSurfaceGate()))


# ---------------------------------------------------------------------------
# Core classifier outcomes
# ---------------------------------------------------------------------------


def test_semantic_forbidden_closed_enum_rejects():
    # A changed line touching a closed-enum marker in gate_receipt.py → BLOCK.
    diff = _diff_modify(
        "src/governor/gate_receipt.py",
        added='    "clean_antecedents",  # added to VALID_NON_DISCHARGE_KINDS',
    )
    r = _admit(diff)
    assert r.verdict is StepVerdict.REJECT
    raw = r.preflight_decision.raw
    assert raw["reason"] == REASON_SEMANTIC_FORBIDDEN
    ids = {d["surface_id"] for d in raw["detected_surfaces"]}
    assert "closed_receipt_enums" in ids


def test_semantic_allowed_passes():
    # An ordinary file with no forbidden surface → ADMIT.
    r = _admit(_diff_modify("src/governor/widget.py"))
    assert r.verdict is StepVerdict.ADMIT
    assert r.preflight_decision.raw["reason"] == REASON_NO_FORBIDDEN_SURFACE


def test_forbidden_file_no_marker_is_ambiguous_cannot_testify():
    # gate_receipt.py touched, but the changed line carries no declared marker → ambiguous.
    diff = _diff_modify(
        "src/governor/gate_receipt.py",
        added="# just a clarifying comment",
        removed="# old comment",
    )
    r = _admit(diff)
    assert r.verdict is StepVerdict.CANNOT_TESTIFY
    raw = r.preflight_decision.raw
    assert raw["reason"] == REASON_SEMANTIC_AMBIGUOUS
    assert "closed_receipt_enums" in raw["ambiguous_surfaces"]


def test_stepverdict_projection_marker_rejects():
    diff = _diff_modify(
        "src/governor/ag_admit.py",
        added="def project_source_verdict(x):  # tampering",
    )
    r = _admit(diff)
    assert r.verdict is StepVerdict.REJECT
    ids = {d["surface_id"] for d in r.preflight_decision.raw["detected_surfaces"]}
    assert "stepverdict_projection" in ids


def test_preflight_contract_marker_rejects():
    diff = _diff_modify(
        "src/governor/governed_dispatch.py",
        added="class PreflightDecision:  # changing the contract",
    )
    r = _admit(diff)
    assert r.verdict is StepVerdict.REJECT


def test_ci_accept_semantics_marker_rejects():
    diff = _diff_modify(
        "src/governor/ci.py", added="    accepts_waiver_admitted = True  # loosen"
    )
    r = _admit(diff)
    assert r.verdict is StepVerdict.REJECT
    ids = {d["surface_id"] for d in r.preflight_decision.raw["detected_surfaces"]}
    assert "ci_accept_semantics" in ids


def test_loop_state_whole_file_rejects_on_any_touch():
    # loop_state has empty markers: any touch to loop.json is a modification.
    diff = _diff_modify(".governor/loop.json", added='  "phase": "BUILD",')
    r = _admit(diff)
    assert r.verdict is StepVerdict.REJECT
    ids = {d["surface_id"] for d in r.preflight_decision.raw["detected_surfaces"]}
    assert "loop_state" in ids


def test_unparseable_diff_cannot_testify():
    r = _admit("this is not a diff\njust prose\n")
    assert r.verdict is StepVerdict.CANNOT_TESTIFY
    assert r.preflight_decision.raw["reason"] == REASON_CANNOT_OBSERVE_DIFF


# ---------------------------------------------------------------------------
# Two-gate composition: path-allowed but semantic-forbidden
# ---------------------------------------------------------------------------


def test_path_allowed_but_semantic_forbidden_specimen():
    # The whole point: DiffPathScopeGate ADMITs (path in scope), ForbiddenSurfaceGate REJECTs.
    diff = _diff_modify(
        "src/governor/gate_receipt.py",
        added="VALID_NON_DISCHARGE_KINDS = frozenset()  # gutted",
    )
    step = _step(diff, scope="src/governor/**")
    path_gate = DiffPathScopeGate(("src/governor/**",))
    path_result = asyncio.run(ag_admit(step, path_gate))
    sem_result = asyncio.run(ag_admit(step, ForbiddenSurfaceGate()))
    assert path_result.verdict is StepVerdict.ADMIT  # path authority alone is fooled
    assert sem_result.verdict is StepVerdict.REJECT  # semantic authority catches it


def test_path_allowed_and_semantic_allowed_specimen():
    diff = _diff_modify("src/governor/widget.py", added="x = 1")
    step = _step(diff, scope="src/governor/**")
    path_gate = DiffPathScopeGate(("src/governor/**",))
    assert asyncio.run(ag_admit(step, path_gate)).verdict is StepVerdict.ADMIT
    assert asyncio.run(ag_admit(step, ForbiddenSurfaceGate())).verdict is StepVerdict.ADMIT


# ---------------------------------------------------------------------------
# The dumb conductor (UNCHANGED) records detected surfaces + conductor_decided
# ---------------------------------------------------------------------------


def test_conductor_records_detected_surfaces_without_modification(tmp_path):
    system = GateReceiptSystem(tmp_path)
    diff = _diff_modify(
        "src/governor/gate_receipt.py", added="VALID_VERDICTS = frozenset()  # tamper"
    )
    out = ag_admit_conductor.conduct(_step(diff), ForbiddenSurfaceGate(), system)
    assert out.verdict is StepVerdict.REJECT
    receipt = system.receipt_store.all()[-1]
    ev = system.evidence_for(receipt)
    assert ev["conductor_decided"] is False
    assert ev["source_gate"] == "ForbiddenSurfaceGate"
    # detected surfaces ride in block_reasons, which the unchanged conductor records:
    flat = str(ev["reasons"])
    assert "closed_receipt_enums" in flat


# ---------------------------------------------------------------------------
# Helper unit checks
# ---------------------------------------------------------------------------


def test_scan_diff_extracts_files_and_changed_lines():
    files, changed = _scan_diff(_diff_modify("a/b/c.py", added="hello", removed="bye"))
    assert files is not None
    assert any(f.endswith("b/c.py") for f in files)
    assert "hello" in changed and "bye" in changed


def test_scan_diff_returns_none_without_header():
    files, _changed = _scan_diff("no header here")
    assert files is None


@pytest.mark.parametrize("marker_change", [True, False])
def test_marker_presence_distinguishes_block_from_ambiguous(marker_change):
    added = "VALID_VERDICTS = ()" if marker_change else "# benign comment"
    r = _admit(_diff_modify("src/governor/gate_receipt.py", added=added))
    if marker_change:
        assert r.verdict is StepVerdict.REJECT
    else:
        assert r.verdict is StepVerdict.CANNOT_TESTIFY
