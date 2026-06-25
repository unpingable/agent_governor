# SPDX-License-Identifier: Apache-2.0
"""Slice 6 — first self-hosted governed-playbook chore (dogfood execution).

> Dogfood execution is not autopilot.

AG runs ONE boring read-only chore through the full Slice 3–5 chain
(evidence → authority → LA spend → durable spend) and emits a NON-AUTHORITATIVE
report receipt. The boss fight:

    AG runs a governed chore, leaves receipts, and a future AG cannot mistake
    the report for authority.

Pinned: the chore runs only on an actual spend; observe receipts / Wicket pass
without spend / unbound durable spend cannot dispatch; replay does not
re-execute; a failed chore is recorded; the report is structurally inert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governor.cooked_context_orchestrator import (
    ORIGIN_MODE_STUB,
    CookedContextOrchestrator,
    build_authority_admission_verifier,
    is_authority_admission_receipt,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_DENIED,
    LA_DECISION_GRANTED,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
)
from governor.playbooks import (
    PlaybookAdmissionEvidence,
    certified_kind_measurement_digest,
    certify,
    dependency_closure_digest,
    parse_playbook,
    playbook_spec_digest,
    resolve_closure,
)
from governor.playbooks.chore import (
    CHORE_NOT_RUN_CHAIN_DID_NOT_SPEND,
    GOVERNED_CHORE_REPORT_GATE,
    ChoreNotRun,
    ChoreResult,
    read_only_receipt_audit,
    run_governed_chore,
)
from governor.playbooks.durable_spend import (
    DurablePlaybookSpendGate,
    DurableSpendLedger,
    PlaybookSpendIntent,
)
from governor.standing_client import StandingClient, StandingReceiptRef
from governor.wicket_client import (
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
)

_VALID_DIGEST = "a" * 64


def _cooked(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="agent-governor",
        actor_standing=ActorStanding(cls="execute", provenance="caller_asserted"),
        intended_action="playbook.chore",
        operation_class="execute",
        target="sandbox://audit",
        claimed_basis={"rule": "self-hosted governed chore", "evidence_refs": []},
        precedence=Precedence(resolution="active", provenance="caller_asserted"),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
        ),
        expected_effect="run a read-only audit and emit a non-authoritative report",
        call_timestamp="2026-06-25T00:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True, provenance="caller_asserted"
        ),
    )


def _capacity_template() -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-chore-6",
        actor="agent-governor",
        action="read_only_audit",
        target="sandbox://audit",
        scope="audit",
        requested_capacity=1,
        admission_receipt_id="PLACEHOLDER",
        eligibility_valid_until=10_000,
        expires_after=10_000,
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-chore-6",
        token_id="PLACEHOLDER",
        actor="agent-governor",
        action="read_only_audit",
        target="sandbox://audit",
        amount=1,
        scope="audit",
    )


def _granted(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": "tok-chore-6",
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        "receipt": {"la_receipt_id": "la-grant-chore-6"},
    }


def _consumed(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": la_request["token_id"],
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la-consume-chore-6"},
    }


def _denied(la_request: dict, now: int) -> dict:
    return {"decision": LA_DECISION_DENIED, "denial_reason": "no capacity", "receipt": {}}


def _admit_any(cooked_context: CookedContext) -> dict:
    return {"surface_verdict": "authorized", "_fake": True}


def _evidence(name: str = "audit-playbook") -> PlaybookAdmissionEvidence:
    spec = parse_playbook(
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        "steps:\n"
        "  - id: audit1\n"
        "    action: read_only_audit\n"
        "    target: sandbox://audit\n"
    )
    cert = certify(spec)
    closure = resolve_closure(spec, lambda ref: None)
    return PlaybookAdmissionEvidence(
        spec_digest=playbook_spec_digest(spec),
        certified_kind=cert,
        claimed_certified_kind_digest=certified_kind_measurement_digest(cert),
        closure=closure,
        claimed_closure_digest=dependency_closure_digest(closure),
    )


def _intent(spec_digest: str, *, step_id: str = "audit1") -> PlaybookSpendIntent:
    return PlaybookSpendIntent(
        step_id=step_id,
        principal="agent-governor",
        effect="read_only_audit",
        resource="audit:sandbox://audit",
        amount=1,
        playbook_spec_digest=spec_digest,
    )


def _build(sink, ledger_root, *, standing_valid=True, request_capacity_callable=_granted):
    wrapped = wrap_receipt_sink_with_origin_mode(sink, ORIGIN_MODE_STUB)
    known = (
        {_VALID_DIGEST: StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")}
        if standing_valid
        else {}
    )
    standing = StandingClient(verify_fn=lambda sid: known.get(sid), receipt_sink=wrapped)
    wicket = WicketClient(
        standing_client=standing, wicket_check_fn=_admit_any, receipt_sink=wrapped
    )
    la = LinearAccountantClient(
        request_capacity_callable=request_capacity_callable,
        consume_callable=_consumed,
        admission_verifier=build_authority_admission_verifier(sink),
        receipt_sink=wrapped,
    )
    gate = DurablePlaybookSpendGate(DurableSpendLedger(ledger_root), receipt_sink=wrapped)
    orch = CookedContextOrchestrator(
        wicket_client=wicket,
        la_client=la,
        origin_mode=ORIGIN_MODE_STUB,
        durable_spend_gate=gate,
    )
    return orch, wrapped


def _run_chore(orch, wrapped, ev, intent, *, chore_fn=None):
    return run_governed_chore(
        orch,
        chore_name="receipt_store_audit",
        chore_fn=chore_fn or (lambda: read_only_receipt_audit(wrapped._inner)),
        cooked_context=_cooked(_VALID_DIGEST),
        capacity_request_template=_capacity_template(),
        consume_request_template=_consume_template(),
        now=0,
        playbook_evidence=ev,
        playbook_spend_intent=intent,
        receipt_sink=wrapped,
    )


def _chore_reports(sink: GateReceiptSystem) -> list[Any]:
    return [r for r in sink.receipt_store.all() if r.gate == GOVERNED_CHORE_REPORT_GATE]


# --------------------------------------------------------------------------- #
# THE BOSS FIGHT: chore runs, leaves receipts, report is not authority.
# --------------------------------------------------------------------------- #


class TestDogfoodBossFight:
    def test_chore_runs_and_report_is_non_authoritative(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        ev = _evidence()

        result = _run_chore(orch, wrapped, ev, _intent(ev.spec_digest))

        assert isinstance(result, ChoreResult)
        assert result.report.ok is True
        assert result.report.non_authoritative is True
        assert result.report.findings["audit"] == "receipt_store_by_gate_verdict"

        # A report receipt was emitted, observe-verdict, under its own gate.
        reports = _chore_reports(sink)
        assert len(reports) == 1
        report_receipt = reports[0]
        assert report_receipt.verdict == "observe"
        bundle = sink.evidence_for(report_receipt)
        assert bundle["non_authoritative"] is True
        assert bundle["record_kind"] == "chore_report"

        # A future AG cannot mistake the report for authority: it fails the
        # authority-admission predicate, so the Slice-4 spend-basis wall refuses
        # it. report != authority.
        assert is_authority_admission_receipt(report_receipt) is False

        # The report cites the LA consume as parent (walkable chain).
        consume_receipts = [
            r for r in sink.receipt_store.all()
            if r.gate == "la_seam" and r.verdict == "pass"
            and sink.evidence_for(r).get("la_outcome") == "consumed"
        ]
        assert bundle["parent_receipt_ids"] == [consume_receipts[0].receipt_id]

    def test_replay_does_not_re_execute_the_chore(self, tmp_path: Path):
        """Re-run the same governed chore against the same durable ledger: the
        durable gate refuses the replay, so the chore does not re-execute and no
        second report is emitted. The durable spend IS the chore's idempotency."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        spend_root = tmp_path / "spend"
        ev = _evidence()
        intent = _intent(ev.spec_digest)

        orch1, w1 = _build(sink, spend_root)
        first = _run_chore(orch1, w1, ev, intent)
        assert isinstance(first, ChoreResult)

        orch2, w2 = _build(sink, spend_root)  # fresh process, same ledger
        replay = _run_chore(orch2, w2, ev, intent)
        assert isinstance(replay, ChoreNotRun)
        assert replay.reason == CHORE_NOT_RUN_CHAIN_DID_NOT_SPEND
        # Exactly one report across both runs.
        assert len(_chore_reports(sink)) == 1


# --------------------------------------------------------------------------- #
# Dispatch gating: only an actual spend dispatches the chore.
# --------------------------------------------------------------------------- #


class TestDispatchGating:
    def test_no_standing_does_not_dispatch(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend", standing_valid=False)
        ev = _evidence()
        result = run_governed_chore(
            orch,
            chore_name="receipt_store_audit",
            chore_fn=lambda: read_only_receipt_audit(wrapped._inner),
            cooked_context=_cooked(None),  # no Standing
            capacity_request_template=_capacity_template(),
            consume_request_template=_consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=_intent(ev.spec_digest),
            receipt_sink=wrapped,
        )
        assert isinstance(result, ChoreNotRun)
        assert result.chain_seam == "wicket_seam"
        assert _chore_reports(sink) == []

    def test_la_denied_does_not_dispatch(self, tmp_path: Path):
        """Wicket pass but LA denies → no spend → chore does not dispatch."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(
            sink, tmp_path / "spend", request_capacity_callable=_denied
        )
        ev = _evidence()
        result = _run_chore(orch, wrapped, ev, _intent(ev.spec_digest))
        assert isinstance(result, ChoreNotRun)
        assert result.chain_seam == "la_seam_request"
        assert _chore_reports(sink) == []

    def test_unbound_durable_spend_does_not_dispatch(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        ev = _evidence()
        # Incomplete intent (empty step_id) → durable gate refuses → no spend.
        result = _run_chore(
            orch, wrapped, ev, _intent(ev.spec_digest, step_id="")
        )
        assert isinstance(result, ChoreNotRun)
        assert result.chain_seam == "playbook_durable_spend_seam"
        assert _chore_reports(sink) == []


# --------------------------------------------------------------------------- #
# A failed chore is recorded as auditable state, not folklore.
# --------------------------------------------------------------------------- #


class TestFailedChoreIsRecorded:
    def test_raising_chore_records_failure(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        ev = _evidence()

        def boom() -> dict:
            raise RuntimeError("audit blew up")

        result = _run_chore(orch, wrapped, ev, _intent(ev.spec_digest), chore_fn=boom)
        # The spend happened, the chore failed — recorded, not swallowed.
        assert isinstance(result, ChoreResult)
        assert result.report.ok is False
        assert result.report.findings["error"] == "RuntimeError"
        reports = _chore_reports(sink)
        assert len(reports) == 1
        bundle = sink.evidence_for(reports[0])
        assert bundle["chore_ok"] is False
        assert bundle["non_authoritative"] is True
