# SPDX-License-Identifier: Apache-2.0
"""
Self-correction within already-admitted scope.

Reduce operator throttle by letting a repair worker (Codex / another generator) produce a
*repaired* CandidateStep from a refusal/test receipt — while preserving every authority
boundary. The worker is a mechanic with a work order, not a magistrate with vibes: it
proposes (dumb, can be wrong); this harness VALIDATES the proposal's identity, scope, and
intent, then re-admits it through the SAME gates. The worker may self-correct
*implementation*; it may not self-authorize *jurisdiction*.

Invariants (capsule seed docs/campaigns/ag-admit-self-build/NEXT.md):
- a repair runs only within the original declared scope (same or narrower) and intent;
- every repair CITES the refusal/test receipt it answers (repair identity / ancestry);
- resubmission goes through the same ag_admit path (DiffPathScopeGate + ForbiddenSurfaceGate);
- no scope widening, no StepVerdict-projection / conductor / governed_dispatch / closed-enum
  / loop-state / semantic-surface change; NEEDS_HUMAN always stops; CANNOT_TESTIFY never
  mutates; CANNOT_TESTIFY is never rewritten to NEEDS_HUMAN;
- a repaired step is NOT admitted until it passes the same gates;
- no repair if the source receipt is missing/ambiguous/unreconstructable.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .ag_admit import AdmitResult, CandidateStep, DiffPathScopeGate, StepVerdict, ag_admit
from .forbidden_surface_gate import ForbiddenSurfaceGate
from .governed_dispatch import PreflightDecision, PreflightRequest

# Repair-identity vocabulary (closed).
SCOPE_SAME = "same"
SCOPE_NARROWER = "narrower"
INTENT_SAME = "same"


class FailureClass(Enum):
    PATH_OUT_OF_SCOPE = "path_out_of_scope"
    SEMANTIC_FORBIDDEN = "semantic_surface_forbidden"
    CANNOT_TESTIFY = "cannot_testify"
    NEEDS_HUMAN = "needs_human"
    TEST_FAILURE = "test_failure"


@dataclass(frozen=True)
class RepairProvenance:
    """Repair identity / ancestry. Without it a 'new' step is a laundering repair."""

    repairs_step_id: str
    repairs_receipt_id: str
    repair_reason: str
    scope_relation: str  # SCOPE_SAME | SCOPE_NARROWER
    intent_relation: str  # INTENT_SAME

    def __post_init__(self) -> None:
        if self.scope_relation not in (SCOPE_SAME, SCOPE_NARROWER):
            raise ValueError(f"scope_relation must be same|narrower, got {self.scope_relation!r}")
        if self.intent_relation != INTENT_SAME:
            raise ValueError(f"intent_relation must be 'same', got {self.intent_relation!r}")
        if not (self.repairs_step_id and self.repairs_receipt_id and self.repair_reason):
            raise ValueError("repair provenance requires non-empty step_id, receipt_id, reason")


@dataclass(frozen=True)
class RepairProposal:
    step: CandidateStep
    provenance: RepairProvenance


@dataclass(frozen=True)
class RepairOrder:
    """The work order handed to a repair worker."""

    original_step: CandidateStep
    source_receipt_id: str
    failure_class: FailureClass
    grant: tuple[str, ...]  # the ORIGINAL DiffPathScopeGate allowed globs (re-admit reuses it)


class RepairProvider(Protocol):
    """A dumb repair worker (e.g. Codex). Proposes; never decides admissibility."""

    def propose_repair(self, order: RepairOrder) -> RepairProposal | None:
        ...


class RepairStatus(Enum):
    REPAIRED_AND_ADMITTED = "repaired_and_admitted"
    HALT_NEEDS_HUMAN = "halt_needs_human"
    REQUEST_EVIDENCE = "request_evidence"
    NO_REPAIR_SOURCE_UNRECONSTRUCTABLE = "no_repair_source_unreconstructable"
    NO_PROPOSAL = "no_proposal"
    REPAIR_REJECTED_PROVENANCE = "repair_rejected_provenance"
    REPAIR_REJECTED_INTENT_DRIFT = "repair_rejected_intent_drift"
    REPAIR_REJECTED_SCOPE_WIDENED = "repair_rejected_scope_widened"
    REPAIR_REJECTED_BY_GATE = "repair_rejected_by_gate"
    REPAIR_CANNOT_TESTIFY = "repair_cannot_testify"


@dataclass(frozen=True)
class RepairOutcome:
    status: RepairStatus
    admit_result: AdmitResult | None = None
    proposal: RepairProposal | None = None
    detail: str = ""
    mutated: bool = False  # produced an admitted change? (zero-mutation pins read this)


# ---------------------------------------------------------------------------
# CompositeAdmissionGate — all sub-gates must admit
# ---------------------------------------------------------------------------


class CompositeAdmissionGate:
    """Run a candidate through several PreflightClients; ALL must admit.

    Combined verdict precedence (a definite no beats a don't-know): BLOCK > REQUIRE_HUMAN
    > CANNOT_TESTIFY > PROCEED. The winning sub-decision is returned, with every sub-verdict
    recorded in raw.composite (data, not vibes).
    """

    GATE_NAME = "CompositeAdmissionGate"
    _PRECEDENCE = {"BLOCK": 3, "REQUIRE_HUMAN": 2, "CANNOT_TESTIFY": 1, "PROCEED": 0}

    def __init__(self, gates: list[Any] | tuple[Any, ...]):
        self.gates = tuple(gates)

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        subs: list[PreflightDecision] = [await g.preflight(request) for g in self.gates]
        composite = [
            {
                "source_gate": (d.raw or {}).get("source_gate"),
                "source_verdict": (d.raw or {}).get("source_verdict"),
                "reason": (d.raw or {}).get("reason"),
            }
            for d in subs
        ]

        def rank(d: PreflightDecision) -> int:
            sv = (d.raw or {}).get("source_verdict")
            return self._PRECEDENCE.get(sv, 1)  # unknown source verdict ranks as CANNOT_TESTIFY

        winner = max(subs, key=rank)
        merged_raw = dict(winner.raw or {})
        merged_raw["source_gate"] = self.GATE_NAME
        merged_raw["composite"] = composite
        merged_raw["observed_paths"] = sorted(
            {p for d in subs for p in (d.raw or {}).get("observed_paths", [])}
        )
        return PreflightDecision(
            decision=winner.decision,
            mode="enforce",
            block_reasons=list(winner.block_reasons),
            raw=merged_raw,
        )

    async def record(self, request, result_status, preflight_token=None, record_id=None):
        return {"recorded": True, "gate": self.GATE_NAME, "result_status": result_status}


def default_gates(grant: tuple[str, ...]) -> CompositeAdmissionGate:
    """The standard re-admission path: path authority + semantic-surface classification."""
    return CompositeAdmissionGate([DiffPathScopeGate(grant), ForbiddenSurfaceGate()])


# ---------------------------------------------------------------------------
# Scope containment (declared same-or-narrower)
# ---------------------------------------------------------------------------


def _globs(scope: str) -> list[str]:
    return [s.strip() for s in scope.split(";") if s.strip()]


def _glob_covered_by(a: str, b: str) -> bool:
    if a == b:
        return True
    if b.endswith("/**"):
        prefix = b[:-3]
        return a == prefix or a.startswith(prefix + "/")
    if b.endswith("/*"):
        prefix = b[:-2]
        return a.startswith(prefix + "/") and "/" not in a[len(prefix) + 1 :]
    return False


def _scope_same_or_narrower(repaired_scope: str, original_scope: str) -> bool:
    """True iff every repaired glob is covered by some original glob (no widening)."""
    rep = _globs(repaired_scope)
    orig = _globs(original_scope)
    if not rep:
        return True  # empty = nothing claimed
    return all(any(_glob_covered_by(r, o) for o in orig) for r in rep)


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------


def attempt_repair(
    order: RepairOrder,
    provider: RepairProvider,
    *,
    gates: Any | None = None,
    receipt_system: Any | None = None,
) -> RepairOutcome:
    """Produce, validate, and re-admit a repaired CandidateStep. Never widens jurisdiction."""
    outcome = _attempt_repair_inner(order, provider, gates)
    if receipt_system is not None:
        _emit_repair_receipt(receipt_system, order, outcome)
    return outcome


def _attempt_repair_inner(order: RepairOrder, provider: RepairProvider, gates: Any | None) -> RepairOutcome:
    # Guard 0: source must be reconstructable.
    if not order.source_receipt_id or order.failure_class is None:
        return RepairOutcome(RepairStatus.NO_REPAIR_SOURCE_UNRECONSTRUCTABLE, mutated=False)

    fc = order.failure_class
    # NEEDS_HUMAN always stops; CANNOT_TESTIFY requests evidence — neither mutates, neither
    # calls the worker (no laundering a halt into a repair).
    if fc == FailureClass.NEEDS_HUMAN:
        return RepairOutcome(RepairStatus.HALT_NEEDS_HUMAN, mutated=False)
    if fc == FailureClass.CANNOT_TESTIFY:
        return RepairOutcome(RepairStatus.REQUEST_EVIDENCE, mutated=False)

    # PATH_OUT_OF_SCOPE / SEMANTIC_FORBIDDEN / TEST_FAILURE → ask the worker.
    proposal = provider.propose_repair(order)
    if proposal is None:
        return RepairOutcome(RepairStatus.NO_PROPOSAL, mutated=False)

    prov = proposal.provenance
    original = order.original_step

    # Validate ancestry: the repair must cite exactly this step + source receipt.
    if prov.repairs_step_id != original.step_id or prov.repairs_receipt_id != order.source_receipt_id:
        return RepairOutcome(
            RepairStatus.REPAIR_REJECTED_PROVENANCE, proposal=proposal, mutated=False,
            detail="provenance does not cite the original step/receipt",
        )

    # Intent must be preserved.
    if prov.intent_relation != INTENT_SAME or proposal.step.declared_intent != original.declared_intent:
        return RepairOutcome(
            RepairStatus.REPAIR_REJECTED_INTENT_DRIFT, proposal=proposal, mutated=False,
            detail="declared_intent drifted",
        )

    # Declared scope must be same-or-narrower (no widening claim).
    if not _scope_same_or_narrower(proposal.step.scope, original.scope):
        return RepairOutcome(
            RepairStatus.REPAIR_REJECTED_SCOPE_WIDENED, proposal=proposal, mutated=False,
            detail="repaired scope widens beyond original",
        )

    # Re-admit through the SAME gates (original grant). The gates — not this harness —
    # decide admissibility: out-of-grant paths and re-introduced forbidden surfaces are
    # caught here, not trusted from the worker's declarations.
    gate = gates or default_gates(order.grant)
    result = asyncio.run(ag_admit(proposal.step, gate))
    if result.verdict is StepVerdict.ADMIT:
        return RepairOutcome(
            RepairStatus.REPAIRED_AND_ADMITTED, admit_result=result, proposal=proposal, mutated=True,
        )
    if result.verdict is StepVerdict.CANNOT_TESTIFY:
        return RepairOutcome(
            RepairStatus.REPAIR_CANNOT_TESTIFY, admit_result=result, proposal=proposal, mutated=False,
        )
    # REJECT (e.g. forbidden surface re-introduced, or retargeted outside the grant).
    return RepairOutcome(
        RepairStatus.REPAIR_REJECTED_BY_GATE, admit_result=result, proposal=proposal, mutated=False,
    )


_STATUS_VERDICT = {
    RepairStatus.REPAIRED_AND_ADMITTED: "proceed",
    RepairStatus.HALT_NEEDS_HUMAN: "block",
    RepairStatus.REQUEST_EVIDENCE: "warn",
    RepairStatus.NO_REPAIR_SOURCE_UNRECONSTRUCTABLE: "warn",
    RepairStatus.NO_PROPOSAL: "warn",
    RepairStatus.REPAIR_REJECTED_PROVENANCE: "block",
    RepairStatus.REPAIR_REJECTED_INTENT_DRIFT: "block",
    RepairStatus.REPAIR_REJECTED_SCOPE_WIDENED: "block",
    RepairStatus.REPAIR_REJECTED_BY_GATE: "block",
    RepairStatus.REPAIR_CANNOT_TESTIFY: "warn",
}


def _emit_repair_receipt(receipt_system: Any, order: RepairOrder, outcome: RepairOutcome) -> Any:
    """Emit a self_correction receipt that CITES the source receipt (the causal link)."""
    prov = outcome.proposal.provenance if outcome.proposal else None
    evidence: dict[str, Any] = {
        "repairs_receipt_id": order.source_receipt_id,  # ancestry: the failure answered
        "repairs_step_id": order.original_step.step_id,
        "failure_class": order.failure_class.value if order.failure_class else None,
        "status": outcome.status.value,
        "mutated": outcome.mutated,
        "repaired_step_id": outcome.proposal.step.step_id if outcome.proposal else None,
        "scope_relation": prov.scope_relation if prov else None,
        "intent_relation": prov.intent_relation if prov else None,
        "repair_reason": prov.repair_reason if prov else None,
        "detail": outcome.detail,
        "conductor_decided": False,
    }
    return receipt_system.emit(
        gate="self_correction",
        verdict=_STATUS_VERDICT[outcome.status],
        subject_kind="repair",
        subject_bytes=f"{order.source_receipt_id}:{order.original_step.step_id}".encode(),
        evidence_bundle=evidence,
        gate_config={"grant": list(order.grant)},
    )
