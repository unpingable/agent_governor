# SPDX-License-Identifier: Apache-2.0
"""
ag-admit conductor — DISPOSABLE. Keep it stupid.

Per docs/doctrine/specs_do_not_bootstrap.md: the intelligence lives at the two ends
(the generator proposes; ag_admit/the gate refuse). The middle stays mechanical. This
file is the middle. It carries a CandidateStep, asks ag_admit for a StepVerdict, writes
one admission receipt, and returns an action label. That is all.

It does NOT: decide admissibility, parse diffs, synthesize authority, reinterpret a
verdict by substring, rewrite CANNOT_TESTIFY into NEEDS_HUMAN, or mutate anything on a
non-ADMIT verdict. The moment this file feels clever, specs_do_not_bootstrap has
reincarnated in a new host — delete the cleverness.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from governor.ag_admit import AdmitResult, StepVerdict, ag_admit
from governor.gate_receipt import GateReceiptSystem

# StepVerdict → (receipt verdict [closed set], mechanical action label). Static. Dumb.
# "refuse" / "request_evidence" / "halt_for_human" all mean: NO MUTATION.
_VERDICT_TABLE: dict[StepVerdict, tuple[str, str]] = {
    StepVerdict.ADMIT: ("proceed", "execute"),
    StepVerdict.REJECT: ("block", "refuse"),
    StepVerdict.CANNOT_TESTIFY: ("warn", "request_evidence"),
    StepVerdict.NEEDS_HUMAN: ("block", "halt_for_human"),
}


@dataclass(frozen=True)
class Outcome:
    verdict: StepVerdict
    action: str  # "execute" only on ADMIT; everything else is non-mutating
    receipt_id: str
    admit: AdmitResult


def conduct(step, gate, receipts: GateReceiptSystem) -> Outcome:
    """Carry a CandidateStep through admission and emit exactly one receipt."""
    result: AdmitResult = asyncio.run(ag_admit(step, gate))  # the delegated judgment
    receipt_verdict, action = _VERDICT_TABLE[result.verdict]
    raw = result.preflight_decision.raw if isinstance(result.preflight_decision.raw, dict) else {}
    receipt = receipts.emit(
        gate="step_admission",
        verdict=receipt_verdict,
        subject_kind="candidate_step",
        subject_bytes=step.diff.encode("utf-8"),
        evidence_bundle={
            "step_id": step.step_id,
            "step_verdict": result.verdict.value,
            "source_gate": raw.get("source_gate"),
            "source_verdict": result.source_verdict,
            "reasons": list(result.reasons),
            "observed_paths": list(result.observed_paths),
            "observation_method": raw.get("observation_method"),
            "declared_allowed_scope": raw.get("allowed_scope"),
            "declared_touched_paths": raw.get("declared_touched_paths"),
            "declared_observed_mismatch": raw.get("declared_observed_mismatch"),
            "conductor_decided": False,
        },
        gate_config={
            "conductor": "ag_admit_conductor",
            "allowed_scope": raw.get("allowed_scope"),
        },
    )
    return Outcome(
        verdict=result.verdict,
        action=action,
        receipt_id=receipt.receipt_id,
        admit=result,
    )
