# SPDX-License-Identifier: Apache-2.0
"""Self-correction within already-admitted scope.

The worker proposes; the harness validates identity/scope/intent and re-admits through the
SAME gates. Repairs may fix implementation; they may not widen jurisdiction.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from governor.ag_admit import CandidateStep, DiffPathScopeGate, StepVerdict
from governor.gate_receipt import GateReceiptSystem
from governor.self_correction import (
    INTENT_SAME,
    SCOPE_NARROWER,
    SCOPE_SAME,
    FailureClass,
    RepairOrder,
    RepairProposal,
    RepairProvenance,
    RepairStatus,
    attempt_repair,
)

_WORKING = pathlib.Path(__file__).resolve().parents[1] / "working"
sys.path.insert(0, str(_WORKING))
import ag_admit_conductor  # noqa: E402

GRANT = ("toy_repo/allowed/**",)
GRANT_SRC = ("src/governor/**",)


def _diff(path: str, added: str = "new", removed: str = "old") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{removed}\n+{added}\n"
    )


def _step(step_id, path, *, intent="touch a file", scope="toy_repo/allowed/**", diff=None):
    return CandidateStep(
        step_id=step_id, repo="r", base_commit="0" * 40,
        diff=diff if diff is not None else _diff(path),
        declared_intent=intent, scope=scope, tests_to_run=("true",),
    )


class FixedProvider:
    def __init__(self, proposal):
        self.proposal = proposal
        self.called = 0

    def propose_repair(self, order):
        self.called += 1
        return self.proposal


class RaisingProvider:
    def __init__(self):
        self.called = 0

    def propose_repair(self, order):
        self.called += 1
        raise AssertionError("worker must not be called for this failure class")


# ---------------------------------------------------------------------------
# 1. path refusal -> repaired inside scope -> admitted
# ---------------------------------------------------------------------------


def test_path_refusal_repaired_inside_scope_admitted():
    original = _step("s1", "toy_repo/forbidden/secret.txt")
    order = RepairOrder(original, "rcpt-1", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("s1-r", "toy_repo/allowed/example.txt")
    prov = RepairProvenance("s1", "rcpt-1", "retarget into grant", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIRED_AND_ADMITTED
    assert out.mutated is True
    assert out.admit_result.verdict is StepVerdict.ADMIT


# ---------------------------------------------------------------------------
# 2/3. semantic-forbidden refusal: remove change -> admitted; reattempt -> rejected
# ---------------------------------------------------------------------------


def test_semantic_forbidden_repair_removes_change_admitted():
    original = _step("s2", "src/governor/gate_receipt.py", scope="src/governor/**")
    order = RepairOrder(original, "rcpt-2", FailureClass.SEMANTIC_FORBIDDEN, GRANT_SRC)
    repaired = _step("s2-r", "src/governor/widget.py", scope="src/governor/**")
    prov = RepairProvenance("s2", "rcpt-2", "remove forbidden change", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIRED_AND_ADMITTED


def test_semantic_forbidden_repair_reattempts_forbidden_rejected():
    original = _step("s3", "src/governor/gate_receipt.py", scope="src/governor/**")
    order = RepairOrder(original, "rcpt-3", FailureClass.SEMANTIC_FORBIDDEN, GRANT_SRC)
    bad = _diff("src/governor/gate_receipt.py", added="VALID_NON_DISCHARGE_KINDS = frozenset()")
    repaired = _step("s3-r", "src/governor/gate_receipt.py", scope="src/governor/**", diff=bad)
    prov = RepairProvenance("s3", "rcpt-3", "still tampering", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIR_REJECTED_BY_GATE
    assert out.mutated is False


# ---------------------------------------------------------------------------
# 4/5. CANNOT_TESTIFY and NEEDS_HUMAN: zero mutation, worker never called
# ---------------------------------------------------------------------------


def test_cannot_testify_zero_mutation_no_worker():
    order = RepairOrder(_step("s4", "toy_repo/allowed/x.txt"), "rcpt-4", FailureClass.CANNOT_TESTIFY, GRANT)
    provider = RaisingProvider()
    out = attempt_repair(order, provider)
    assert out.status is RepairStatus.REQUEST_EVIDENCE  # NOT rewritten to NEEDS_HUMAN
    assert out.mutated is False
    assert provider.called == 0


def test_needs_human_always_stops_no_worker():
    order = RepairOrder(_step("s5", "x"), "rcpt-5", FailureClass.NEEDS_HUMAN, GRANT)
    provider = RaisingProvider()
    out = attempt_repair(order, provider)
    assert out.status is RepairStatus.HALT_NEEDS_HUMAN
    assert out.mutated is False
    assert provider.called == 0


# ---------------------------------------------------------------------------
# 6. test failure -> repaired implementation inside scope -> admitted
# ---------------------------------------------------------------------------


def test_test_failure_repaired_implementation_admitted():
    original = _step("s6", "toy_repo/allowed/mod.py")
    order = RepairOrder(original, "rcpt-6", FailureClass.TEST_FAILURE, GRANT)
    repaired = _step("s6-r", "toy_repo/allowed/mod.py")
    prov = RepairProvenance("s6", "rcpt-6", "fix failing test", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIRED_AND_ADMITTED


# ---------------------------------------------------------------------------
# 7/8. widened scope and intent drift are rejected (the jurisdiction guards)
# ---------------------------------------------------------------------------


def test_repaired_widened_scope_rejected():
    original = _step("s7", "toy_repo/allowed/x.txt", scope="toy_repo/allowed/**")
    order = RepairOrder(original, "rcpt-7", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("s7-r", "toy_repo/allowed/x.txt", scope="toy_repo/**")  # WIDER
    prov = RepairProvenance("s7", "rcpt-7", "sneaky widen", SCOPE_NARROWER, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIR_REJECTED_SCOPE_WIDENED
    assert out.mutated is False


def test_repaired_intent_drift_rejected():
    original = _step("s8", "toy_repo/allowed/x.txt", intent="add feature A")
    order = RepairOrder(original, "rcpt-8", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("s8-r", "toy_repo/allowed/x.txt", intent="add feature B")  # drift
    prov = RepairProvenance("s8", "rcpt-8", "drift", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIR_REJECTED_INTENT_DRIFT
    assert out.mutated is False


def test_narrower_scope_is_allowed():
    original = _step("s8n", "toy_repo/allowed/x.txt", scope="toy_repo/allowed/**")
    order = RepairOrder(original, "rcpt-8n", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("s8n-r", "toy_repo/allowed/sub/y.txt", scope="toy_repo/allowed/sub/**")
    prov = RepairProvenance("s8n", "rcpt-8n", "narrow", SCOPE_NARROWER, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIRED_AND_ADMITTED


# ---------------------------------------------------------------------------
# 9. full trace with receipts: refusal -> repair (cites refusal) -> admission
# ---------------------------------------------------------------------------


def test_full_trace_refusal_repair_admission_with_receipts(tmp_path):
    system = GateReceiptSystem(tmp_path)
    original = _step("trace", "toy_repo/forbidden/secret.txt")
    refusal = ag_admit_conductor.conduct(original, DiffPathScopeGate(GRANT), system)
    assert refusal.verdict is StepVerdict.REJECT

    order = RepairOrder(original, refusal.receipt_id, FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("trace-r", "toy_repo/allowed/example.txt")
    prov = RepairProvenance("trace", refusal.receipt_id, "retarget into grant", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(
        order, FixedProvider(RepairProposal(repaired, prov)), receipt_system=system
    )
    assert out.status is RepairStatus.REPAIRED_AND_ADMITTED

    admit = ag_admit_conductor.conduct(repaired, DiffPathScopeGate(GRANT), system)
    assert admit.verdict is StepVerdict.ADMIT

    receipts = system.receipt_store.all()
    assert [r.gate for r in receipts] == ["step_admission", "self_correction", "step_admission"]
    sc_ev = system.evidence_for(receipts[1])
    assert sc_ev["repairs_receipt_id"] == refusal.receipt_id  # ancestry: cites the failure
    assert sc_ev["mutated"] is True
    assert sc_ev["conductor_decided"] is False
    assert receipts[2].verdict == "proceed"
    assert receipts[0].verdict == "block"


# ---------------------------------------------------------------------------
# Repair identity / ancestry pins + source guards
# ---------------------------------------------------------------------------


def test_provenance_requires_all_fields_and_closed_relations():
    with pytest.raises(ValueError):
        RepairProvenance("", "r", "reason", SCOPE_SAME, INTENT_SAME)  # empty step id
    with pytest.raises(ValueError):
        RepairProvenance("s", "r", "", SCOPE_SAME, INTENT_SAME)  # empty reason
    with pytest.raises(ValueError):
        RepairProvenance("s", "r", "reason", "wider", INTENT_SAME)  # bad scope_relation
    with pytest.raises(ValueError):
        RepairProvenance("s", "r", "reason", SCOPE_SAME, "different")  # bad intent_relation


def test_provenance_not_citing_source_rejected():
    original = _step("s10", "toy_repo/allowed/x.txt")
    order = RepairOrder(original, "rcpt-10", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    repaired = _step("s10-r", "toy_repo/allowed/y.txt")
    prov = RepairProvenance("WRONG", "rcpt-10", "r", SCOPE_SAME, INTENT_SAME)
    out = attempt_repair(order, FixedProvider(RepairProposal(repaired, prov)))
    assert out.status is RepairStatus.REPAIR_REJECTED_PROVENANCE
    assert out.mutated is False


def test_unreconstructable_source_no_repair():
    order = RepairOrder(_step("s11", "x"), "", FailureClass.PATH_OUT_OF_SCOPE, GRANT)
    provider = RaisingProvider()
    out = attempt_repair(order, provider)
    assert out.status is RepairStatus.NO_REPAIR_SOURCE_UNRECONSTRUCTABLE
    assert out.mutated is False
    assert provider.called == 0


def test_no_proposal_no_mutation():
    order = RepairOrder(_step("s12", "toy_repo/allowed/x.txt"), "rcpt-12", FailureClass.PATH_OUT_OF_SCOPE, GRANT)

    class NoneProvider:
        def propose_repair(self, order):
            return None

    out = attempt_repair(order, NoneProvider())
    assert out.status is RepairStatus.NO_PROPOSAL
    assert out.mutated is False
