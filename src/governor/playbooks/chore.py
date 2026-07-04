# SPDX-License-Identifier: Apache-2.0
"""First self-hosted governed-playbook chore (Slice 6 — dogfood execution).

> Dogfood execution is not autopilot.

This is the first time AG performs a bounded effect *of its own* under the full
governed chain (Slices 3–5): evidence coherence → Wicket authority admission →
LA spend → durable replay-safe spend → **the chore runs**. The chore is
aggressively unsexy on purpose: an *aggressively boring, read-only* maintenance
task whose only output is a **non-authoritative report receipt**.

The boss fight:

    AG runs a governed chore, leaves receipts, and a future AG cannot mistake
    the report for authority.

So the report is structurally inert:
- ``verdict="observe"`` under its own gate (``governed_chore_report``) — it
  decides nothing,
- carries ``non_authoritative: True`` and ``record_kind: chore_report``,
- fails ``is_authority_admission_receipt`` (gate≠wicket_seam / verdict≠pass), so
  it can never be cited as a spend basis. The Slice-4 wall already refuses it.

The non-collapses Slices 3–5 made mechanical all still hold, and one is added:
**report ≠ authority.** A generated report records what was observed; it never
authorizes anything.

What this is NOT (stop line):
- It is not autopilot. The agent performs EXACTLY ONE caller-supplied chore. No
  loop, no discretionary task selection, no remembered "may".
- It is not external-agent dispatch. A self-hosted chore is AG's own code; it
  does NOT route through ``runtime/supervisor.py`` (which gates *external* agent
  CLI tool calls). The supervisor's forcing case is the autopilot slice, not
  this one — see the Slice 6 exit ticket.
- It is not an effect-bearing chore. The chore is **read-only by contract**. A
  chore with real (operational) effect must route its outcome through
  ``confer_operational_effect`` (Wall 1) and so requires ``OperationalConsumed``
  (observed origin); a read-only report confers no operational effect, so the
  mechanical ``consumed`` gate is the correct and sufficient trigger here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Optional

from governor.gate_receipt import canonical_json, content_hash

from .admission_evidence import PlaybookAdmissionEvidence
from .durable_spend import PlaybookSpendIntent

# Gate + verdict for the chore report. Distinct gate so the report can never be
# confused with an authority admission (wicket_seam/pass) or a spend (la_seam/pass).
GOVERNED_CHORE_REPORT_GATE = "governed_chore_report"
GOVERNED_CHORE_REPORT_VERDICT = "observe"  # a report decides nothing

# Why the chore did not run (the governed chain refused before the spend).
CHORE_NOT_RUN_CHAIN_DID_NOT_SPEND = "chain_did_not_spend"


# A chore is a read-only, no-argument callable returning structured findings.
ChoreFn = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class ChoreReport:
    """The result of a governed chore. ``non_authoritative`` is always True — a
    report records what was observed; it never authorizes anything. ``ok`` is
    False when the chore raised (the failure is recorded, not swallowed)."""

    chore_name: str
    ok: bool
    findings: dict[str, Any]
    non_authoritative: bool = True

    def findings_digest(self) -> str:
        return content_hash(canonical_json(self.findings))


@dataclass(frozen=True)
class ChoreResult:
    """The governed chore ran (the chain spent). Carries the report and the id
    of the non-authoritative report receipt (when a sink is wired). ``spend_seam``
    is the chain seam that produced the spend (``la_seam_consume``)."""

    report: ChoreReport
    spend_seam: str
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


@dataclass(frozen=True)
class ChoreNotRun:
    """The governed chore did NOT run because the chain refused before spending.

    The chore is gated on an actual spend — a refusal anywhere upstream (evidence
    / authority / durable / LA) means no chore, no report. ``chain_seam`` names
    where the chain refused so the caller can see which gate stopped it."""

    reason: str
    chain_seam: str


# --------------------------------------------------------------------------- #
# A concrete, aggressively-boring read-only chore: audit the receipt store.
# --------------------------------------------------------------------------- #


def read_only_receipt_audit(sink: Any) -> dict[str, Any]:
    """Read-only audit: tally the gate receipts by (gate, verdict).

    The toaster. Reads ``sink.receipt_store.all()`` and counts — it mutates
    nothing, decides nothing, authorizes nothing. The snapshot is taken BEFORE
    the report receipt is emitted, so the report describes the state it observed
    (its own non-authoritative summary is appended afterward by the executor).
    """
    receipts = sink.receipt_store.all()
    by_gate_verdict: Counter[str] = Counter()
    for r in receipts:
        by_gate_verdict[f"{r.gate}/{r.verdict}"] += 1
    return {
        "audit": "receipt_store_by_gate_verdict",
        "total_receipts": len(receipts),
        "counts": dict(sorted(by_gate_verdict.items())),
    }


# --------------------------------------------------------------------------- #
# The governed chore executor.
# --------------------------------------------------------------------------- #


def _emit_chore_report(
    receipt_sink: Any | None,
    report: ChoreReport,
    *,
    chore_inputs: dict[str, Any],
    parent_receipt_id: Optional[str],
) -> Optional[str]:
    """Emit the non-authoritative chore report receipt; return its id (or None)."""
    if receipt_sink is None:
        return None
    evidence_bundle: dict[str, Any] = {
        "record_kind": "chore_report",
        "non_authoritative": True,
        "chore_name": report.chore_name,
        "chore_ok": report.ok,
        "findings_digest": report.findings_digest(),
        "findings": report.findings,
        "parent_receipt_ids": [parent_receipt_id] if parent_receipt_id else [],
    }
    evidence_bundle.update(chore_inputs)
    subject_bytes = (
        f"{report.chore_name}|{report.findings_digest()}"
    ).encode("utf-8")
    receipt = receipt_sink.emit(
        gate=GOVERNED_CHORE_REPORT_GATE,
        verdict=GOVERNED_CHORE_REPORT_VERDICT,
        subject_kind="governed_chore_report",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence_bundle,
        gate_config={"seam": "S6_governed_chore", "report": "non_authoritative"},
    )
    return receipt.receipt_id


def run_governed_chore(
    orchestrator: Any,
    *,
    chore_name: str,
    chore_fn: ChoreFn,
    cooked_context: Any,
    capacity_request_template: Any,
    consume_request_template: Any,
    now: int,
    playbook_evidence: PlaybookAdmissionEvidence,
    playbook_spend_intent: PlaybookSpendIntent,
    receipt_sink: Any | None = None,
    finding_id: Optional[str] = None,
) -> ChoreResult | ChoreNotRun:
    """Run ONE governed chore through the full Slice 3–5 chain, then (and only
    then) execute the read-only chore and emit a non-authoritative report.

    Gate discipline (every invariant the chain already enforces, plus the chore
    trigger):

    - The chore runs IFF the chain actually **spent** (``ChainResult.consumed``).
      A refusal anywhere upstream — evidence-unbound, no Standing, durable
      replay, LA denied — returns ``ChoreNotRun`` and the chore never executes.
    - So: an observe evidence receipt cannot dispatch (it is not a spend); a
      Wicket pass without an LA spend cannot dispatch (no consume); a durable
      spend without exact binding cannot dispatch (the durable gate refuses).
    - A chore that raises is recorded (``ok=False``) — auditable state, not
      folklore.
    - The report is non-authoritative (``verdict=observe``) and cites the LA
      consume receipt as parent, so ``governor why`` walks report → consume →
      grant → admission → standing.

    Replay safety is inherited, not re-implemented: the durable spend gate
    (Slice 5) refuses a replayed spend, so a re-run returns ``ChoreNotRun`` and
    the chore does not re-execute. The durable spend IS the chore's idempotency.
    """
    chain = orchestrator.run(
        cooked_context,
        capacity_request_template,
        consume_request_template,
        now,
        finding_id=finding_id,
        playbook_evidence=playbook_evidence,
        playbook_spend_intent=playbook_spend_intent,
    )

    # The chore runs ONLY on an actual spend. Anything else: no chore, no report.
    if not chain.consumed:
        return ChoreNotRun(
            reason=CHORE_NOT_RUN_CHAIN_DID_NOT_SPEND,
            chain_seam=chain.seam,
        )

    # Spend happened. Cite the LA consume receipt as the report's parent.
    consumed_result = getattr(chain.outcome, "consumed_result", None)
    parent_receipt_id = getattr(consumed_result, "receipt_id", None)

    # Execute the read-only chore. A raise is recorded, not swallowed.
    try:
        findings = chore_fn()
        ok = True
    except Exception as exc:  # noqa: BLE001 — failure is recorded as state
        findings = {"error": type(exc).__name__, "detail": str(exc)}
        ok = False

    report = ChoreReport(chore_name=chore_name, ok=ok, findings=findings)
    rid = _emit_chore_report(
        receipt_sink,
        report,
        chore_inputs={
            "playbook_spec_digest": playbook_spend_intent.playbook_spec_digest,
            "step_id": playbook_spend_intent.step_id,
            "principal": playbook_spend_intent.principal,
        },
        parent_receipt_id=parent_receipt_id,
    )
    return ChoreResult(
        report=report,
        spend_seam=chain.seam,
        receipt_id=rid,
        parent_receipt_id=parent_receipt_id,
    )


__all__ = [
    "GOVERNED_CHORE_REPORT_GATE",
    "GOVERNED_CHORE_REPORT_VERDICT",
    "CHORE_NOT_RUN_CHAIN_DID_NOT_SPEND",
    "ChoreFn",
    "ChoreReport",
    "ChoreResult",
    "ChoreNotRun",
    "read_only_receipt_audit",
    "run_governed_chore",
]
