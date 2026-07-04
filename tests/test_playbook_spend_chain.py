# SPDX-License-Identifier: Apache-2.0
"""Slice 4 — playbook-governed SPEND: evidence → authority → LA consume.

> Evidence admits consideration; Standing authorizes; LA spends.

This wires the existing CookedContextOrchestrator through the Slice 3 playbook
evidence gate and onto the unchanged LA spend seam. The slice proves the
composition SHAPE without laundering any layer into another:

- evidence coherence is necessary but not sufficient,
- Standing authority is necessary but is not the spend,
- the LA spend's basis is the authority (pass) admission receipt — NEVER the
  observe-verdict evidence record (the Slice 4 laundering wall).

Failure taxonomy stays crisp by owner:
  digest/closure          -> evidence gate (SEAM_WICKET, playbook_evidence_unbound)
  no Standing             -> authority gate (SEAM_WICKET, standing_required)
  LA denied / unavailable -> effect gate    (SEAM_LA_REQUEST, capacity_refused)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governor.cooked_context_orchestrator import (
    ORIGIN_MODE_STUB,
    SEAM_LA_REQUEST,
    SEAM_WICKET,
    CookedContextOrchestrator,
    DemonstratedConsumed,
    build_authority_admission_verifier,
    is_authority_admission_receipt,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_DENIED,
    LA_DECISION_GRANTED,
    REFUSAL_ADMISSION_DENIED,
    REFUSAL_CAPACITY_REFUSED,
    REFUSAL_DANGLING_RECEIPT_REFERENCE,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
    RefusalResult,
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
from governor.standing_client import (
    REFUSAL_KIND_STANDING_REQUIRED,
    StandingClient,
    StandingReceiptRef,
)
from governor.wicket_client import (
    REFUSAL_KIND_PLAYBOOK_EVIDENCE_UNBOUND,
    WICKET_PLAYBOOK_EVIDENCE_GATE,
    WICKET_SEAM_GATE,
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
    WicketRefusal,
)

_VALID_DIGEST = "a" * 64


# --------------------------------------------------------------------------- #
# Fixtures: cooked context, templates, LA fakes, real playbook evidence.
# --------------------------------------------------------------------------- #


def _cooked(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="execute", provenance="caller_asserted"),
        intended_action="playbook.run",
        operation_class="execute",
        target="sandbox://x.txt",
        claimed_basis={"rule": "playbook-governed spend", "evidence_refs": []},
        precedence=Precedence(resolution="active", provenance="caller_asserted"),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
        ),
        expected_effect="consume one unit of write capacity",
        call_timestamp="2026-06-25T00:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True, provenance="caller_asserted"
        ),
    )


def _capacity_template() -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-pb-4",
        actor="claude-code",
        action="write_file",
        target="sandbox://x.txt",
        scope="fs_write",
        requested_capacity=1,
        admission_receipt_id="PLACEHOLDER",  # orchestrator replaces this
        eligibility_valid_until=10_000,
        expires_after=10_000,
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-pb-4",
        token_id="PLACEHOLDER",  # orchestrator replaces with granted token
        actor="claude-code",
        action="write_file",
        target="sandbox://x.txt",
        amount=1,
        scope="fs_write",
    )


def _granted(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": "tok-pb-4",
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        "receipt": {"la_receipt_id": "la-grant-pb-4"},
    }


def _consumed(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": la_request["token_id"],
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la-consume-pb-4"},
    }


def _denied(la_request: dict, now: int) -> dict:
    return {"decision": LA_DECISION_DENIED, "denial_reason": "no stock", "receipt": {}}


def _admit_any(cooked_context: CookedContext) -> dict:
    return {"surface_verdict": "authorized", "_fake": True}


def _coherent_evidence(name: str = "alpha") -> PlaybookAdmissionEvidence:
    spec = parse_playbook(
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        "steps:\n"
        "  - id: s1\n"
        "    action: write_file\n"
        "    target: sandbox://x.txt\n"
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


def _tampered_evidence() -> PlaybookAdmissionEvidence:
    ev, other = _coherent_evidence("alpha"), _coherent_evidence("beta")
    return PlaybookAdmissionEvidence(
        spec_digest=ev.spec_digest,
        certified_kind=ev.certified_kind,
        claimed_certified_kind_digest=other.claimed_certified_kind_digest,
        closure=ev.closure,
        claimed_closure_digest=ev.claimed_closure_digest,
    )


def _build(
    sink: GateReceiptSystem,
    *,
    standing_valid: bool,
    request_capacity_callable=_granted,
    consume_callable=_consumed,
):
    """Wire a playbook-spend orchestrator over a real sink with the authority
    admission verifier (the Slice 4 wall: only a wicket pass admission is a
    valid LA spend basis)."""
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
        consume_callable=consume_callable,
        admission_verifier=build_authority_admission_verifier(sink),
        receipt_sink=wrapped,
    )
    return CookedContextOrchestrator(
        wicket_client=wicket, la_client=la, origin_mode=ORIGIN_MODE_STUB
    )


def _receipts_by_gate(sink: GateReceiptSystem, gate: str) -> list[Any]:
    return [r for r in sink.receipt_store.all() if r.gate == gate]


# --------------------------------------------------------------------------- #
# Success: evidence + Standing + LA → bounded consume.
# --------------------------------------------------------------------------- #


class TestPlaybookSpendSuccess:
    def test_evidence_authority_spend_consumes(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True)

        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )

        # The chain mechanically consumed (stub origin → DemonstratedConsumed:
        # structure shown, operational effect fenced by Wall 1 — orthogonal).
        assert result.consumed is True
        assert isinstance(result.outcome, DemonstratedConsumed)
        assert result.outcome.consumed_result.consumed_amount == 1

    def test_spend_basis_is_authority_not_evidence(self, tmp_path: Path):
        """The LA grant cites the wicket PASS admission as its basis — never the
        observe-verdict evidence record. Certification did not become the spend
        basis."""
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True)
        orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )

        pass_admissions = [
            r for r in _receipts_by_gate(sink, WICKET_SEAM_GATE) if r.verdict == "pass"
        ]
        assert len(pass_admissions) == 1
        admission_id = pass_admissions[0].receipt_id

        observe_records = _receipts_by_gate(sink, WICKET_PLAYBOOK_EVIDENCE_GATE)
        assert len(observe_records) == 1
        observe_id = observe_records[0].receipt_id
        assert observe_records[0].verdict == "observe"

        # The LA grant receipt's basis is the authority admission, not the
        # evidence record.
        grants = [
            r
            for r in sink.receipt_store.all()
            if r.gate == "la_seam" and r.verdict == "pass"
        ]
        grant_bundle = sink.evidence_for(grants[0])
        assert grant_bundle["cited_admission_receipt_id"] == admission_id
        assert grant_bundle["cited_admission_receipt_id"] != observe_id


# --------------------------------------------------------------------------- #
# Refusal taxonomy, by owner.
# --------------------------------------------------------------------------- #


class TestRefusalTaxonomy:
    def test_missing_standing_refuses_before_la(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        la_calls = {"n": 0}

        def counting_request(la_request, now):
            la_calls["n"] += 1
            return _granted(la_request, now)

        orch = _build(
            sink, standing_valid=True, request_capacity_callable=counting_request
        )
        result = orch.run(
            _cooked(None),  # no Standing authority
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )
        assert result.refused is True
        assert result.seam == SEAM_WICKET
        assert isinstance(result.outcome, WicketRefusal)
        assert result.outcome.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # LA never reached.
        assert la_calls["n"] == 0

    def test_tampered_evidence_refuses_before_standing(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True)
        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_tampered_evidence(),
        )
        assert result.refused is True
        assert result.seam == SEAM_WICKET
        assert isinstance(result.outcome, WicketRefusal)
        assert result.outcome.refusal_kind == REFUSAL_KIND_PLAYBOOK_EVIDENCE_UNBOUND
        # Standing never consulted: no standing_seam receipt minted.
        assert _receipts_by_gate(sink, "standing_seam") == []

    def test_la_denied_surfaces_at_la_seam_not_wicket(self, tmp_path: Path):
        """LA unavailable/denied with valid evidence + Standing: the refusal is
        the EFFECT gate's, not pretended as a wicket failure."""
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True, request_capacity_callable=_denied)
        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )
        assert result.refused is True
        assert result.seam == SEAM_LA_REQUEST
        assert isinstance(result.outcome, RefusalResult)
        assert result.outcome.kind == REFUSAL_CAPACITY_REFUSED


# --------------------------------------------------------------------------- #
# The Slice 4 laundering wall: certification alone cannot reserve capacity.
# --------------------------------------------------------------------------- #


class TestCertificationIsNotSpendBasis:
    def test_authority_predicate_rejects_observe_record(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True)
        orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )
        pass_admission = next(
            r for r in _receipts_by_gate(sink, WICKET_SEAM_GATE) if r.verdict == "pass"
        )
        observe_record = _receipts_by_gate(sink, WICKET_PLAYBOOK_EVIDENCE_GATE)[0]

        # Authority admission: yes. Evidence record: no.
        assert is_authority_admission_receipt(pass_admission) is True
        assert is_authority_admission_receipt(observe_record) is False

    def test_la_refuses_evidence_record_cited_as_spend_basis(self, tmp_path: Path):
        """Manually cite the observe evidence record id as the LA admission
        basis. The authority verifier refuses it — the evidence record resolves
        in the store but is not an admission, so LA returns
        dangling_receipt_reference. Certification could not reserve capacity."""
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=True)
        orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=_coherent_evidence(),
        )
        observe_id = _receipts_by_gate(sink, WICKET_PLAYBOOK_EVIDENCE_GATE)[0].receipt_id

        # A fresh LA client with the authority verifier; request capacity citing
        # the EVIDENCE record id as the admission basis.
        wrapped = wrap_receipt_sink_with_origin_mode(sink, ORIGIN_MODE_STUB)
        la_calls = {"n": 0}

        def counting_request(la_request, now):
            la_calls["n"] += 1
            return _granted(la_request, now)

        la = LinearAccountantClient(
            request_capacity_callable=counting_request,
            consume_callable=_consumed,
            admission_verifier=build_authority_admission_verifier(sink),
            receipt_sink=wrapped,
        )
        req = CookedCapacityRequest(
            request_id="req-launder",
            actor="claude-code",
            action="write_file",
            target="sandbox://x.txt",
            scope="fs_write",
            requested_capacity=1,
            admission_receipt_id=observe_id,  # ← certification, not authority
            eligibility_valid_until=10_000,
            expires_after=10_000,
        )
        result = la.request_capacity(req, now=0)
        assert isinstance(result, RefusalResult)
        assert result.kind == REFUSAL_DANGLING_RECEIPT_REFERENCE
        # Teeth: LA request callable never invoked — refused pre-call.
        assert la_calls["n"] == 0


# --------------------------------------------------------------------------- #
# Existing non-playbook callers preserved (no playbook_evidence → unchanged).
# --------------------------------------------------------------------------- #


class TestNonPlaybookCallersPreserved:
    def test_no_playbook_evidence_runs_plain_chain(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        # Plain (non-playbook) verifier: admits any resolvable receipt, the
        # pre-Slice-4 default behavior.
        wrapped = wrap_receipt_sink_with_origin_mode(sink, ORIGIN_MODE_STUB)
        known = {_VALID_DIGEST: StandingReceiptRef(digest=_VALID_DIGEST, kind="grant")}
        standing = StandingClient(
            verify_fn=lambda sid: known.get(sid), receipt_sink=wrapped
        )
        wicket = WicketClient(
            standing_client=standing, wicket_check_fn=_admit_any, receipt_sink=wrapped
        )
        la = LinearAccountantClient(
            request_capacity_callable=_granted,
            consume_callable=_consumed,
            admission_verifier=lambda rid: True,
            receipt_sink=wrapped,
        )
        orch = CookedContextOrchestrator(
            wicket_client=wicket, la_client=la, origin_mode=ORIGIN_MODE_STUB
        )

        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            # no playbook_evidence
        )
        assert result.consumed is True
        # No evidence record minted on the plain path.
        assert _receipts_by_gate(sink, WICKET_PLAYBOOK_EVIDENCE_GATE) == []

    def test_admission_denied_when_no_admission_id(self, tmp_path: Path):
        """Plain path, but wicket refuses standing → no admission id → LA would
        never be reached. Confirms the plain refusal path is unchanged."""
        sink = GateReceiptSystem(tmp_path)
        orch = _build(sink, standing_valid=False)
        result = orch.run(
            _cooked("dangling" * 8),  # cited but unknown → dangling at standing
            _capacity_template(),
            _consume_template(),
            now=0,
        )
        assert result.refused is True
        assert result.seam == SEAM_WICKET
        # Sanity: the admission-denied LA kind exists and is distinct from what
        # we got (we refused upstream at wicket, never reached LA's gate).
        assert REFUSAL_ADMISSION_DENIED == "admission_denied"
