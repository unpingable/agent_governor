"""Tests for the Linear Accountant client seam (S2 + S3).

Teeth-standard: every refusal test asserts ZERO calls (or exact-once calls)
on a mock of the next downstream stage. Refusal that merely logs is not
refusal. Effect-count assertions cover the S3 replay-kill invariant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    CLOSED_REFUSAL_KINDS,
    LA_DECISION_ALREADY_CONSUMED,
    LA_DECISION_CONSUMED,
    LA_DECISION_DENIED,
    LA_DECISION_EXPIRED,
    LA_DECISION_GRANTED,
    LA_DECISION_INSUFFICIENT_CAPACITY,
    LA_DECISION_REVOKED,
    LA_DECISION_SCOPE_MISMATCH,
    LA_DECISION_UNKNOWN_TOKEN,
    REFUSAL_ADMISSION_DENIED,
    REFUSAL_ALREADY_CONSUMED,
    REFUSAL_CAPACITY_REFUSED,
    REFUSAL_DANGLING_RECEIPT_REFERENCE,
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    GrantedResult,
    LinearAccountantClient,
    RefusalResult,
)


# ---------------------------------------------------------------------------
# Test doubles.
#
# Plain callables with a call counter. No mock framework. The point is to make
# call-count assertions explicit and visible.
# ---------------------------------------------------------------------------


class _CountingCallable:
    """Wraps a deterministic response into a callable with a call counter."""

    def __init__(self, response_fn):
        self._response_fn = response_fn
        self.calls: list[tuple[dict, int]] = []

    def __call__(self, la_request: dict, now: int) -> dict:
        self.calls.append((la_request, now))
        return self._response_fn(la_request, now)

    @property
    def call_count(self) -> int:
        return len(self.calls)


class _EffectCounter:
    """Stands in for the downstream effect that a Consumed verdict authorizes.

    The S3 invariant under test: across two replayed consume calls, the
    second LA verdict is AlreadyConsumed, the client emits an
    ``already_consumed`` refusal, and the effect counter advances exactly
    once.
    """

    def __init__(self) -> None:
        self.count = 0

    def perform(self) -> None:
        self.count += 1


def _admission_present(known_ids: set[str]):
    """Build an admission verifier that knows ``known_ids``."""

    def verify(receipt_id: str) -> bool:
        return receipt_id in known_ids

    return verify


def _valid_capacity_request(
    *, admission_receipt_id: str | None = "ag_admit_001"
) -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-1",
        actor="agent-a",
        action="write_file",
        target="/tmp/x",
        scope="fs_write",
        requested_capacity=1,
        admission_receipt_id=admission_receipt_id,
        eligibility_valid_until=1000,
        expires_after=1000,
        idempotency_key="req-1",
    )


def _consume_request(
    *, event_id: str = "evt-1", token_id: Any = "token-7"
) -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id=event_id,
        token_id=token_id,
        actor="agent-a",
        action="write_file",
        target="/tmp/x",
        amount=1,
        scope="fs_write",
    )


# Canned LA responses --------------------------------------------------------


def _granted_response(token_id: Any = "token-7"):
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_GRANTED,
            "token_id": token_id,
            "granted_capacity": la_request["requested_capacity"],
            "scope": la_request["scope"],
            "expires_at": now + la_request["expires_after"],
            "receipt": "la_rcpt_grant_1",
        }

    return response


def _denied_response(reason: str = "insufficient stock"):
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_DENIED,
            "denial_reason": reason,
            "receipt": "la_rcpt_deny_1",
        }

    return response


def _never_called(la_request: dict, now: int) -> dict:
    raise AssertionError(
        "LA callable invoked when the client should have refused pre-call"
    )


# ===========================================================================
# S2 — request_capacity invariants.
# ===========================================================================


def test_s2_missing_admission_receipt_id_refuses_pre_call_zero_la_calls():
    """Missing admission_receipt_id → admission_denied; LA never invoked."""
    request_capacity_mock = _CountingCallable(_never_called)
    consume_mock = _CountingCallable(_never_called)
    client = LinearAccountantClient(
        request_capacity_callable=request_capacity_mock,
        consume_callable=consume_mock,
        admission_verifier=_admission_present(set()),
    )

    result = client.request_capacity(
        _valid_capacity_request(admission_receipt_id=None),
        now=0,
    )

    assert isinstance(result, RefusalResult)
    assert result.kind == REFUSAL_ADMISSION_DENIED
    # TEETH: zero calls past the refusal.
    assert request_capacity_mock.call_count == 0
    assert consume_mock.call_count == 0


def test_s2_empty_admission_receipt_id_refuses_pre_call_zero_la_calls():
    """Whitespace-only admission_receipt_id also fails the gate."""
    request_capacity_mock = _CountingCallable(_never_called)
    client = LinearAccountantClient(
        request_capacity_callable=request_capacity_mock,
        consume_callable=_CountingCallable(_never_called),
        admission_verifier=_admission_present(set()),
    )

    result = client.request_capacity(
        _valid_capacity_request(admission_receipt_id="   "),
        now=0,
    )

    assert isinstance(result, RefusalResult)
    assert result.kind == REFUSAL_ADMISSION_DENIED
    assert request_capacity_mock.call_count == 0


def test_s2_dangling_admission_receipt_id_refuses_pre_call_zero_la_calls():
    """Cited but unresolvable admission_receipt_id → dangling refusal."""
    request_capacity_mock = _CountingCallable(_never_called)
    client = LinearAccountantClient(
        request_capacity_callable=request_capacity_mock,
        consume_callable=_CountingCallable(_never_called),
        # Verifier knows NO ids.
        admission_verifier=_admission_present(set()),
    )

    result = client.request_capacity(
        _valid_capacity_request(admission_receipt_id="ag_admit_ghost"),
        now=0,
    )

    assert isinstance(result, RefusalResult)
    assert result.kind == REFUSAL_DANGLING_RECEIPT_REFERENCE
    # TEETH: zero calls past the refusal.
    assert request_capacity_mock.call_count == 0


def test_s2_valid_request_invokes_la_request_capacity_exactly_once():
    """Valid cooked request → LA callable invoked exactly once."""
    request_capacity_mock = _CountingCallable(_granted_response())
    client = LinearAccountantClient(
        request_capacity_callable=request_capacity_mock,
        consume_callable=_CountingCallable(_never_called),
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.request_capacity(_valid_capacity_request(), now=0)

    assert isinstance(result, GrantedResult)
    # TEETH: exactly one downstream call.
    assert request_capacity_mock.call_count == 1
    # Verify the LA-shaped request carries the AG admission id as
    # eligibility_reference per handoff §2.
    la_request, _now = request_capacity_mock.calls[0]
    assert la_request["eligibility_reference"] == "ag_admit_001"
    # Field names match lib.rs verbatim.
    expected_keys = {
        "request_id",
        "actor",
        "action",
        "target",
        "scope",
        "requested_capacity",
        "eligibility_reference",
        "eligibility_valid_until",
        "expires_after",
        "idempotency_key",
    }
    assert set(la_request.keys()) == expected_keys


def test_s2_la_denied_maps_to_capacity_refused_refusal():
    """LA Denied (e.g. insufficient stock at request) → capacity_refused."""
    request_capacity_mock = _CountingCallable(_denied_response("insufficient stock"))
    client = LinearAccountantClient(
        request_capacity_callable=request_capacity_mock,
        consume_callable=_CountingCallable(_never_called),
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.request_capacity(_valid_capacity_request(), now=0)

    assert isinstance(result, RefusalResult)
    assert result.kind == REFUSAL_CAPACITY_REFUSED
    assert request_capacity_mock.call_count == 1


# ===========================================================================
# S3 — consume invariants.
# ===========================================================================


def _replay_consume_callable():
    """First call returns Consumed; subsequent calls with same event_id return
    AlreadyConsumed. Mirrors LA's mechanical behavior."""
    seen_events: set[str] = set()

    def response(la_request: dict, now: int) -> dict:
        event_id = la_request["consumption_event_id"]
        token_id = la_request["token_id"]
        if event_id in seen_events:
            return {
                "decision": LA_DECISION_ALREADY_CONSUMED,
                "token_id": token_id,
                "receipt": f"la_rcpt_replay_{event_id}",
            }
        seen_events.add(event_id)
        return {
            "decision": LA_DECISION_CONSUMED,
            "token_id": token_id,
            "consumed_amount": la_request["amount"],
            "remaining_capacity": 0,
            "receipt": f"la_rcpt_consumed_{event_id}",
        }

    return response


def test_s3_replay_with_same_event_id_increments_effect_exactly_once():
    """The load-bearing S3 invariant.

    Two consume calls with the same consumption_event_id:
      * LA consume callable is invoked TWICE (the client always asks LA).
      * The downstream effect counter advances EXACTLY ONCE.
      * The first call returns ConsumedResult, the second a closed-set
        ``already_consumed`` refusal.
    """
    consume_mock = _CountingCallable(_replay_consume_callable())
    client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=consume_mock,
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    effect = _EffectCounter()
    consume_req = _consume_request(event_id="evt-1", token_id="token-7")

    # First call → Consumed → effect.
    first = client.consume(consume_req, now=0)
    assert isinstance(first, ConsumedResult)
    effect.perform()

    # Second call (replay) → AlreadyConsumed → already_consumed refusal.
    second = client.consume(consume_req, now=1)
    assert isinstance(second, RefusalResult)
    assert second.kind == REFUSAL_ALREADY_CONSUMED
    # Effect is gated on isinstance(result, ConsumedResult). The replay
    # must NOT increment.
    if isinstance(second, ConsumedResult):
        effect.perform()

    # TEETH: LA was asked twice, but the effect counter is exactly 1.
    assert consume_mock.call_count == 2
    assert effect.count == 1


def test_s3_insufficient_capacity_maps_to_capacity_refused():
    """LA InsufficientCapacity at consume → capacity_refused refusal."""

    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_INSUFFICIENT_CAPACITY,
            "token_id": la_request["token_id"],
            "remaining_capacity": 0,
            "requested_amount": la_request["amount"],
            "receipt": "la_rcpt_insufficient",
        }

    consume_mock = _CountingCallable(response)
    client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=consume_mock,
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.consume(_consume_request(), now=0)

    assert isinstance(result, RefusalResult)
    assert result.kind == REFUSAL_CAPACITY_REFUSED
    assert consume_mock.call_count == 1


def test_s3_consumed_returns_consumed_result_with_la_decision_attached():
    """Happy-path: LA Consumed → ConsumedResult; not a refusal."""
    consume_mock = _CountingCallable(_replay_consume_callable())
    client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=consume_mock,
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.consume(_consume_request(event_id="evt-fresh"), now=0)

    assert isinstance(result, ConsumedResult)
    assert not isinstance(result, RefusalResult)
    assert result.la_decision["decision"] == LA_DECISION_CONSUMED


@pytest.mark.parametrize(
    "la_variant,expected_refusal_kind",
    [
        (LA_DECISION_EXPIRED, "token_expired"),
        (LA_DECISION_REVOKED, "token_revoked"),
        (LA_DECISION_UNKNOWN_TOKEN, "unknown_token"),
        (LA_DECISION_SCOPE_MISMATCH, "scope_mismatch"),
    ],
)
def test_s3_non_consumed_variants_map_to_distinct_closed_set_kinds(
    la_variant,
    expected_refusal_kind,
):
    """Each LA ConsumptionDecision failure variant maps to its own refusal kind.

    Ratified at S4-lite 2026-06-09 per codex adversarial nomenclature review:
    each LA variant is a SPEC-visible failure shape with its own receipt
    fields, so collapsing them under ``capacity_refused`` would lose the
    distinction S5 ``why <receipt-id>`` needs.
    """

    def response(la_request: dict, now: int) -> dict:
        body: dict = {
            "decision": la_variant,
            "token_id": la_request["token_id"],
            "receipt": "la_rcpt_other",
        }
        if la_variant == LA_DECISION_EXPIRED:
            body["expired_at"] = 999
        if la_variant == LA_DECISION_REVOKED:
            body["revoked_at"] = 999
        if la_variant == LA_DECISION_SCOPE_MISMATCH:
            body["expected_scope"] = "fs_write"
            body["requested_scope"] = "net"
        return body

    consume_mock = _CountingCallable(response)
    client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=consume_mock,
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.consume(_consume_request(), now=0)

    assert isinstance(result, RefusalResult)
    # Closed-set invariant.
    assert result.kind in CLOSED_REFUSAL_KINDS
    # Distinct per-variant mapping (S4-lite ratified).
    assert result.kind == expected_refusal_kind
    assert consume_mock.call_count == 1


def test_s3_unknown_decision_variant_does_not_crash():
    """A genuinely unrecognized decision tag still surfaces as closed-set."""

    def response(la_request: dict, now: int) -> dict:
        return {"decision": "FabricatedNewVariant", "token_id": "token-7"}

    consume_mock = _CountingCallable(response)
    client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=consume_mock,
        admission_verifier=_admission_present({"ag_admit_001"}),
    )

    result = client.consume(_consume_request(), now=0)

    assert isinstance(result, RefusalResult)
    assert result.kind in CLOSED_REFUSAL_KINDS


# ===========================================================================
# Cross-cutting closed-vocabulary invariant.
# ===========================================================================


def test_refusal_result_rejects_invented_kinds():
    """The client cannot invent refusal kinds outside the closed set."""
    with pytest.raises(ValueError):
        RefusalResult(kind="not_a_real_kind", detail="should fail")


# ===========================================================================
# D0a — refusal-time GateReceipt emission, per-variant refusal_kind.
# ===========================================================================


def _make_la_client(sink: GateReceiptSystem, *, known_admissions=("ag_admit_001",)):
    """Build an LA client wired to emit refusal receipts into ``sink``."""
    return LinearAccountantClient(
        request_capacity_callable=_CountingCallable(_never_called),
        consume_callable=_CountingCallable(_never_called),
        admission_verifier=_admission_present(set(known_admissions)),
        receipt_sink=sink,
    )


class TestLaRefusalReceiptEmission:
    """Each LA refusal variant mints its own kind, retrievable from the store."""

    def test_admission_denied_emits_gate_receipt(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        client = _make_la_client(sink)
        result = client.request_capacity(
            _valid_capacity_request(admission_receipt_id=None), now=0
        )
        assert isinstance(result, RefusalResult)
        assert result.kind == REFUSAL_ADMISSION_DENIED
        assert result.receipt_id is not None
        receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert receipt is not None
        assert receipt.gate == "la_seam"
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle["refusal_kind"] == REFUSAL_ADMISSION_DENIED
        # No admission cited → no parent.
        assert bundle["parent_receipt_ids"] == []

    def test_dangling_admission_emits_gate_receipt(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        client = _make_la_client(sink)
        result = client.request_capacity(
            _valid_capacity_request(admission_receipt_id="ag_admit_ghost"),
            now=0,
        )
        assert isinstance(result, RefusalResult)
        assert result.kind == REFUSAL_DANGLING_RECEIPT_REFERENCE
        assert result.receipt_id is not None
        receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert receipt is not None
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle["cited_admission_receipt_id"] == "ag_admit_ghost"

    def test_la_denied_emits_capacity_refused_with_parent_linkage(
        self, tmp_path: Path
    ):
        sink = GateReceiptSystem(tmp_path)
        client = LinearAccountantClient(
            request_capacity_callable=_CountingCallable(
                _denied_response("insufficient stock")
            ),
            consume_callable=_CountingCallable(_never_called),
            admission_verifier=_admission_present({"ag_admit_001"}),
            receipt_sink=sink,
        )
        result = client.request_capacity(_valid_capacity_request(), now=0)
        assert isinstance(result, RefusalResult)
        assert result.kind == REFUSAL_CAPACITY_REFUSED
        # Parent linkage cites the admission receipt id when admission was
        # the resolved basis the request carried.
        assert result.parent_receipt_id == "ag_admit_001"
        receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert receipt is not None
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle["parent_receipt_ids"] == ["ag_admit_001"]

    @pytest.mark.parametrize(
        "la_variant,expected_kind",
        [
            (LA_DECISION_EXPIRED, "token_expired"),
            (LA_DECISION_REVOKED, "token_revoked"),
            (LA_DECISION_UNKNOWN_TOKEN, "unknown_token"),
            (LA_DECISION_SCOPE_MISMATCH, "scope_mismatch"),
            (LA_DECISION_INSUFFICIENT_CAPACITY, "capacity_refused"),
            (LA_DECISION_ALREADY_CONSUMED, "already_consumed"),
        ],
    )
    def test_consume_variants_emit_per_variant_kind(
        self, tmp_path: Path, la_variant, expected_kind
    ):
        """LA refusal emits per-variant refusal_kind — the operator-required
        ratification at S4-lite materializes as one receipt per kind."""
        sink = GateReceiptSystem(tmp_path)

        def response(la_request: dict, now: int) -> dict:
            body: dict = {
                "decision": la_variant,
                "token_id": la_request["token_id"],
                "receipt": "la_rcpt_other",
            }
            if la_variant == LA_DECISION_INSUFFICIENT_CAPACITY:
                body["remaining_capacity"] = 0
                body["requested_amount"] = la_request["amount"]
            return body

        client = LinearAccountantClient(
            request_capacity_callable=_CountingCallable(_never_called),
            consume_callable=_CountingCallable(response),
            admission_verifier=_admission_present({"ag_admit_001"}),
            receipt_sink=sink,
        )
        result = client.consume(_consume_request(), now=0)
        assert isinstance(result, RefusalResult)
        assert result.kind == expected_kind
        assert result.receipt_id is not None
        receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert receipt is not None
        assert receipt.gate == "la_seam"
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle["refusal_kind"] == expected_kind

    def test_no_sink_preserves_back_compat(self):
        """Absent sink: RefusalResult.receipt_id is None; behavior unchanged."""
        client = LinearAccountantClient(
            request_capacity_callable=_CountingCallable(_never_called),
            consume_callable=_CountingCallable(_never_called),
            admission_verifier=_admission_present(set()),
        )
        result = client.request_capacity(
            _valid_capacity_request(admission_receipt_id=None), now=0
        )
        assert isinstance(result, RefusalResult)
        assert result.receipt_id is None
        assert result.parent_receipt_id is None
        assert result.kind == REFUSAL_ADMISSION_DENIED

    def test_granted_emits_positive_la_receipt_citing_admission_as_parent(
        self, tmp_path: Path
    ):
        """D0d-b: Granted now mints a positive ``la_seam`` GateReceipt
        (verdict="pass") AND no refusal receipt.

        Amended from D0a's ``test_happy_path_emits_no_refusal_receipt``
        — D0d-b extends emission to the happy path for chain
        completeness. Descriptive marker
        ``evidence_bundle["la_outcome"] = "granted"`` is internal-only;
        NOT a closed refusal kind.
        """
        sink = GateReceiptSystem(tmp_path)
        client = LinearAccountantClient(
            request_capacity_callable=_CountingCallable(_granted_response()),
            consume_callable=_CountingCallable(_never_called),
            admission_verifier=_admission_present({"ag_admit_001"}),
            receipt_sink=sink,
        )
        result = client.request_capacity(_valid_capacity_request(), now=0)
        assert isinstance(result, GrantedResult)
        # D0d-b: exactly one positive receipt minted.
        all_receipts = sink.receipt_store.all()
        assert len(all_receipts) == 1
        receipt = all_receipts[0]
        assert receipt.gate == "la_seam"
        assert receipt.verdict == "pass"
        # GrantedResult carries the emitted receipt id forward so the
        # orchestrator / runner can thread it as parent on consume.
        assert result.receipt_id == receipt.receipt_id
        # Admission receipt id is cited as parent on the grant receipt.
        assert result.parent_receipt_id == "ag_admit_001"
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle.get("la_outcome") == "granted"
        assert bundle["parent_receipt_ids"] == ["ag_admit_001"]
        # No refusal_kind on a positive receipt.
        assert "refusal_kind" not in bundle

    def test_consumed_emits_positive_la_receipt_citing_grant_as_parent(
        self, tmp_path: Path
    ):
        """D0d-b: Consumed mints a positive ``la_seam`` GateReceipt
        (verdict="pass") and cites the prior grant receipt as parent
        when the caller threads ``parent_grant_receipt_id``."""
        sink = GateReceiptSystem(tmp_path)
        client = LinearAccountantClient(
            request_capacity_callable=_CountingCallable(_never_called),
            consume_callable=_CountingCallable(
                _replay_consume_callable()
            ),
            admission_verifier=_admission_present({"ag_admit_001"}),
            receipt_sink=sink,
        )
        parent_grant_id = "fake_grant_receipt_id_for_test"
        result = client.consume(
            _consume_request(event_id="evt-d0d-b-consumed"),
            now=0,
            parent_grant_receipt_id=parent_grant_id,
        )
        assert isinstance(result, ConsumedResult)
        all_receipts = sink.receipt_store.all()
        assert len(all_receipts) == 1
        receipt = all_receipts[0]
        assert receipt.gate == "la_seam"
        assert receipt.verdict == "pass"
        assert result.receipt_id == receipt.receipt_id
        assert result.parent_receipt_id == parent_grant_id
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle.get("la_outcome") == "consumed"
        assert bundle["parent_receipt_ids"] == [parent_grant_id]
        assert "refusal_kind" not in bundle


# ===========================================================================
# D0c-a — LA refusal cites a REAL wicket-emitted admission receipt id as
# parent. This closes the "one synthesized link" debt surfaced by D0a:
# the admission_receipt_id in the parent linkage is now produced by a
# real ``WicketClient.check()`` success, not by a fixture string.
# ===========================================================================


def test_d0c_a_la_refusal_cites_real_wicket_emitted_admission_id_as_parent(
    tmp_path: Path,
):
    """Required test #3: LA refusal cites a real wicket-emitted admission
    receipt id as parent_receipt_id, not a synthesized id.

    Wiring: one ``GateReceiptSystem`` is shared by the wicket happy-path
    emitter and the LA refusal emitter. The admission_receipt_id that
    LA's RefusalResult cites as parent is the same string that wicket's
    ``_emit_admission_receipt`` minted, and resolves through the same
    sink — proving the LA→admission parent linkage is real, not stitched
    in by the test fixture.
    """
    from governor.standing_client import StandingClient, StandingReceiptRef
    from governor.wicket_client import (
        ActorStanding,
        CookedContext,
        Precedence,
        Revocation,
        ScopeAssertion,
        WicketClient,
        WicketVerdict,
    )

    sink = GateReceiptSystem(tmp_path)

    valid_digest = "c" * 64
    standing_ref = StandingReceiptRef(
        digest=valid_digest, kind="grant_issued"
    )
    standing_client = StandingClient(
        verify_fn=lambda sid: standing_ref if sid == valid_digest else None,
        receipt_sink=sink,
    )
    wicket_client = WicketClient(
        standing_client=standing_client,
        wicket_check_fn=lambda _c: {"surface_verdict": "authorized"},
        receipt_sink=sink,
    )
    cooked = CookedContext(
        actor="agent-d0c-a",
        actor_standing=ActorStanding(
            cls="interpret", provenance="caller_asserted"
        ),
        intended_action="write_file",
        operation_class="execute",
        target="/tmp/d0c-a-la",
        claimed_basis={"rule": "test", "evidence_refs": []},
        precedence=Precedence(
            resolution="active",
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        expected_effect="write",
        call_timestamp="2026-06-09T12:00:00Z",
        standing_receipt_id=valid_digest,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
    )

    # Step 1: real wicket admission via WicketClient.check() → real id.
    admission = wicket_client.check(cooked)
    assert isinstance(admission, WicketVerdict)
    real_admission_id = admission.receipt_id
    assert real_admission_id is not None
    # The id resolves in the same sink the LA verifier will read.
    assert sink.receipt_store.get_by_id(real_admission_id) is not None

    # Step 2: drive LA refusal carrying the real admission id.
    la_client = LinearAccountantClient(
        request_capacity_callable=_CountingCallable(
            _denied_response("insufficient stock")
        ),
        consume_callable=_CountingCallable(_never_called),
        admission_verifier=(
            lambda rid: sink.receipt_store.get_by_id(rid) is not None
        ),
        receipt_sink=sink,
    )
    la_result = la_client.request_capacity(
        CookedCapacityRequest(
            request_id="req-d0c-a-la",
            actor="agent-d0c-a",
            action="write_file",
            target="/tmp/d0c-a-la",
            scope="fs_write",
            requested_capacity=1,
            admission_receipt_id=real_admission_id,
            eligibility_valid_until=1000,
            expires_after=1000,
        ),
        now=0,
    )
    assert isinstance(la_result, RefusalResult)
    assert la_result.kind == REFUSAL_CAPACITY_REFUSED
    # The parent_receipt_id is the real wicket-emitted admission id —
    # NOT a synthesized fixture string.
    assert la_result.parent_receipt_id == real_admission_id
    # The LA refusal receipt's evidence bundle records the same id in
    # parent_receipt_ids, so ``governor why`` can walk LA → admission via
    # the real chain (no synthetic links).
    la_receipt = sink.receipt_store.get_by_id(la_result.receipt_id)
    assert la_receipt is not None
    la_bundle = sink.evidence_for(la_receipt)
    assert la_bundle is not None
    assert la_bundle["parent_receipt_ids"] == [real_admission_id]
