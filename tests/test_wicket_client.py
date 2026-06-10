# SPDX-License-Identifier: Apache-2.0
"""S1 seam tests: WicketClient refuses BEFORE invoking the wicket-check
downstream when standing receipt is missing or dangling.

Call-count teeth: refusal without call-count zero on the next-stage mock
is not refusal; it is logging. Per the campaign card and the operator
preflight.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.standing_client import (
    REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
    REFUSAL_KIND_STANDING_REQUIRED,
    StandingClient,
    StandingReceiptRef,
)
from governor.wicket_client import (
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
    WicketRefusal,
    WicketVerdict,
)


# ---------------------------------------------------------------------------
# Fake downstreams (operator-allowed: "fake downstreams/mocks").
# ---------------------------------------------------------------------------


class _FakeStandingService:
    def __init__(self, receipts: dict[str, StandingReceiptRef] | None = None):
        self.receipts = dict(receipts or {})
        self.call_count = 0

    def __call__(self, sid: str):
        self.call_count += 1
        return self.receipts.get(sid)


class _MockWicketCheck:
    """Mock wicket-check callable with call-count and last-arg capture.

    Returns an opaque sentinel verdict — this stub does not implement
    wicket's verdict shape (§7 / §8). That is the downstream's job; this
    seam only routes.
    """

    SENTINEL_VERDICT = {"surface_verdict": "authorized", "_sentinel": True}

    def __init__(self):
        self.call_count = 0
        self.last_arg: CookedContext | None = None

    def __call__(self, cooked_context: CookedContext):
        self.call_count += 1
        self.last_arg = cooked_context
        return self.SENTINEL_VERDICT


_VALID_DIGEST = "a" * 64


def _make_cooked(standing_receipt_id: str | None) -> CookedContext:
    """Build a structurally-complete CookedContext mirroring wicket SPEC §4.

    The S1 seam only inspects ``standing_receipt_id``; the other fields
    are populated to honor the SPEC shape without inventing semantics.
    """
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
        intended_action="git.commit",
        operation_class="execute",
        target="docs/gaps/COVERAGE.md",
        claimed_basis={
            "rule": "user requested edit in current session",
            "evidence_refs": [],
        },
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
        expected_effect="modify repository file at target path",
        call_timestamp="2026-06-09T00:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        prev_receipt_hash=None,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestWicketClientConstruction:
    def test_requires_standing_client(self):
        with pytest.raises(ValueError):
            WicketClient(standing_client=None, wicket_check_fn=lambda c: None)  # type: ignore[arg-type]

    def test_requires_wicket_check_fn(self):
        sc = StandingClient(verify_fn=lambda sid: None)
        with pytest.raises(ValueError):
            WicketClient(standing_client=sc, wicket_check_fn=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The S1 invariant: missing/dangling standing → ZERO calls to wicket-check.
# ---------------------------------------------------------------------------


class TestMissingStandingReceiptId:
    def test_none_id_refuses_zero_wicket_calls(self):
        fake_standing = _FakeStandingService()
        mock_wicket = _MockWicketCheck()
        client = WicketClient(
            standing_client=StandingClient(verify_fn=fake_standing),
            wicket_check_fn=mock_wicket,
        )
        cooked = _make_cooked(standing_receipt_id=None)

        result = client.check(cooked)

        # Teeth: wicket-check NEVER invoked.
        assert mock_wicket.call_count == 0
        assert mock_wicket.last_arg is None
        # Refusal is the S1-shaped one.
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        assert result.standing_receipt_id is None
        # Standing was consulted? It was not — the None check short-circuits.
        # (StandingClient does not call the downstream on a None id.)
        assert fake_standing.call_count == 0

    def test_empty_id_refuses_zero_wicket_calls(self):
        fake_standing = _FakeStandingService()
        mock_wicket = _MockWicketCheck()
        client = WicketClient(
            standing_client=StandingClient(verify_fn=fake_standing),
            wicket_check_fn=mock_wicket,
        )
        cooked = _make_cooked(standing_receipt_id="")

        result = client.check(cooked)

        assert mock_wicket.call_count == 0
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED


class TestDanglingStandingReceiptId:
    def test_unknown_id_refuses_zero_wicket_calls(self):
        # Downstream standing service knows no receipts.
        fake_standing = _FakeStandingService(receipts={})
        mock_wicket = _MockWicketCheck()
        client = WicketClient(
            standing_client=StandingClient(verify_fn=fake_standing),
            wicket_check_fn=mock_wicket,
        )
        dangling_id = "deadbeef" * 8
        cooked = _make_cooked(standing_receipt_id=dangling_id)

        result = client.check(cooked)

        # Teeth: wicket-check NEVER invoked when receipt dangles.
        assert mock_wicket.call_count == 0
        assert mock_wicket.last_arg is None
        # Refusal is the S1-shaped dangling-reference one.
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE
        assert result.standing_receipt_id == dangling_id
        # Standing downstream was consulted exactly once (the lookup-miss).
        assert fake_standing.call_count == 1


# ---------------------------------------------------------------------------
# The happy path: valid cooked context → wicket-check invoked exactly once
# with the cooked context passed through.
# ---------------------------------------------------------------------------


class TestValidStandingReceiptIdPassesThrough:
    def test_wicket_invoked_exactly_once_with_cooked_context(self):
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake_standing = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        mock_wicket = _MockWicketCheck()
        client = WicketClient(
            standing_client=StandingClient(verify_fn=fake_standing),
            wicket_check_fn=mock_wicket,
        )
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check(cooked)

        # Teeth: wicket-check invoked EXACTLY ONCE.
        assert mock_wicket.call_count == 1
        # And it received the cooked context, byte-identical (same object).
        assert mock_wicket.last_arg is cooked
        # Standing downstream was consulted exactly once.
        assert fake_standing.call_count == 1
        # Result is the verdict pass-through.
        assert isinstance(result, WicketVerdict)
        assert result.value is _MockWicketCheck.SENTINEL_VERDICT


# ---------------------------------------------------------------------------
# D0a: refusal-time GateReceipt emission with parent linkage.
# ---------------------------------------------------------------------------


class TestWicketRefusalReceiptEmission:
    """Every wicket-seam refusal emits a GateReceipt; when the refusal was
    caused by a standing-side refusal, the wicket receipt cites the
    standing receipt id as its parent so `governor why` walks the chain.
    """

    def test_standing_required_emits_wicket_receipt_with_parent_linkage(
        self, tmp_path: Path
    ):
        sink = GateReceiptSystem(tmp_path)
        fake_standing = _FakeStandingService()
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
            receipt_sink=sink,
        )
        cooked = _make_cooked(standing_receipt_id=None)

        result = client.check(cooked)

        # Teeth: wicket-check never invoked.
        assert mock_wicket.call_count == 0
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # Both standing and wicket receipts minted.
        assert result.receipt_id is not None
        assert result.parent_receipt_id is not None
        # Parent linkage: wicket receipt cites the standing receipt id.
        wicket_receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert wicket_receipt is not None
        assert wicket_receipt.gate == "wicket_seam"
        wicket_bundle = sink.evidence_for(wicket_receipt)
        assert wicket_bundle is not None
        assert (
            wicket_bundle["refusal_kind"] == REFUSAL_KIND_STANDING_REQUIRED
        )
        assert wicket_bundle["parent_receipt_ids"] == [result.parent_receipt_id]
        # The parent is a real standing-seam receipt.
        standing_receipt = sink.receipt_store.get_by_id(
            result.parent_receipt_id
        )
        assert standing_receipt is not None
        assert standing_receipt.gate == "standing_seam"

    def test_dangling_standing_receipt_emits_wicket_receipt_with_parent_linkage(
        self, tmp_path: Path
    ):
        sink = GateReceiptSystem(tmp_path)
        fake_standing = _FakeStandingService(receipts={})
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
            receipt_sink=sink,
        )
        dangling_id = "deadbeef" * 8
        cooked = _make_cooked(standing_receipt_id=dangling_id)

        result = client.check(cooked)

        assert mock_wicket.call_count == 0
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE
        assert result.receipt_id is not None
        assert result.parent_receipt_id is not None
        # Wicket receipt cites the standing receipt as parent.
        wicket_receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert wicket_receipt is not None
        wicket_bundle = sink.evidence_for(wicket_receipt)
        assert wicket_bundle is not None
        assert wicket_bundle["parent_receipt_ids"] == [
            result.parent_receipt_id
        ]
        # Parent is the standing-seam dangling-reference receipt.
        standing_receipt = sink.receipt_store.get_by_id(
            result.parent_receipt_id
        )
        assert standing_receipt is not None
        assert standing_receipt.gate == "standing_seam"
        standing_bundle = sink.evidence_for(standing_receipt)
        assert standing_bundle is not None
        assert (
            standing_bundle["refusal_kind"]
            == REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE
        )

    def test_happy_path_emits_no_refusal_receipt(self, tmp_path: Path):
        """Valid standing receipt: wicket-check runs, no *refusal* receipt.

        D0c-a flipped wicket's happy-path emission semantics: the wicket
        happy path now emits an authorized-admission receipt
        (verdict="pass"). D0d-b extended emission to the standing-success
        and LA-grant/consume happy paths for chain completeness; so the
        happy path through wicket (with a sink-wired standing client)
        now mints TWO positive receipts: the standing verified-standing
        receipt and the wicket admission. No *refusal* receipt is
        emitted on the happy path — that is what this test still
        guards. The full per-seam happy-path emission contract is
        asserted in the per-client emission test classes.
        """
        sink = GateReceiptSystem(tmp_path)
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake_standing = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
            receipt_sink=sink,
        )
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check(cooked)
        assert isinstance(result, WicketVerdict)
        # D0d-b: two positive receipts minted (standing verified +
        # wicket admit); no refusal receipts.
        all_receipts = sink.receipt_store.all()
        assert len(all_receipts) == 2
        # All receipts have verdict="pass". (D0d-b: standing also
        # emits pass on success.)
        for receipt in all_receipts:
            assert receipt.verdict == "pass"
        # The two gates are standing_seam (verified) and wicket_seam
        # (admit), in emit order.
        gates_in_order = [r.gate for r in all_receipts]
        assert gates_in_order == ["standing_seam", "wicket_seam"]

    def test_no_sink_preserves_back_compat(self):
        """Absent sink: refusal still returned, receipt_id is None."""
        fake_standing = _FakeStandingService()
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
        )
        cooked = _make_cooked(standing_receipt_id=None)

        result = client.check(cooked)
        assert isinstance(result, WicketRefusal)
        assert result.receipt_id is None
        assert result.parent_receipt_id is None


# ---------------------------------------------------------------------------
# D0c-a: authorized-admission GateReceipt emission.
# ---------------------------------------------------------------------------


class TestWicketAdmissionReceiptEmission:
    """Successful admission emits a GateReceipt with verdict="pass" under
    gate="wicket_seam". The emitted receipt id is propagated onto
    ``WicketVerdict.receipt_id`` so downstream LA can use it as
    ``admission_receipt_id`` — closing the "one synthesized link" debt
    surfaced at D0a.
    """

    def test_admission_success_emits_gate_receipt(self, tmp_path: Path):
        """Required test #1: wicket admission emits a GateReceipt."""
        sink = GateReceiptSystem(tmp_path)
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake_standing = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
            receipt_sink=sink,
        )
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check(cooked)

        assert isinstance(result, WicketVerdict)
        # The verdict pass-through still works (D0a invariant preserved).
        assert result.value is _MockWicketCheck.SENTINEL_VERDICT
        # A real receipt was minted and its id is on the verdict.
        assert result.receipt_id is not None
        admission_receipt = sink.receipt_store.get_by_id(result.receipt_id)
        assert admission_receipt is not None
        # Verdict and gate match the closed positive vocabulary.
        assert admission_receipt.verdict == "pass"
        assert admission_receipt.gate == "wicket_seam"
        # Evidence bundle carries the admission-side annotations.
        bundle = sink.evidence_for(admission_receipt)
        assert bundle is not None
        assert bundle["admission_verdict"] == "authorized"
        assert bundle["cited_standing_receipt_id"] == _VALID_DIGEST
        # D0d-b: standing-success now mints its own verified-standing
        # GateReceipt; the wicket admission cites it as parent so
        # ``governor why`` walks admission → standing.
        assert result.parent_receipt_id is not None
        assert bundle["parent_receipt_ids"] == [result.parent_receipt_id]
        # The parent is a real standing_seam receipt with verdict="pass".
        standing_receipt = sink.receipt_store.get_by_id(
            result.parent_receipt_id
        )
        assert standing_receipt is not None
        assert standing_receipt.gate == "standing_seam"
        assert standing_receipt.verdict == "pass"
        # The downstream wicket-check verdict is recorded so the bundle
        # is content-addressed against what the kernel returned.
        assert "downstream_verdict_repr" in bundle

    def test_emitted_admission_id_is_consumable_as_admission_receipt_id(
        self, tmp_path: Path
    ):
        """Required test #2: emitted admission receipt id is available to
        the downstream LA path via the documented seam — the LA client
        consumes the same string under ``admission_receipt_id`` and resolves
        it through its admission_verifier callback against the same sink.
        """
        from governor.linear_accountant_client import (
            CookedCapacityRequest,
            GrantedResult,
            LA_DECISION_GRANTED,
            LinearAccountantClient,
        )

        sink = GateReceiptSystem(tmp_path)
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake_standing = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        mock_wicket = _MockWicketCheck()
        standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
        wicket_client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
            receipt_sink=sink,
        )
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)
        admission = wicket_client.check(cooked)
        assert isinstance(admission, WicketVerdict)
        assert admission.receipt_id is not None

        # The LA client consumes the emitted admission_receipt_id verbatim;
        # the admission_verifier resolves it through the same sink — proving
        # the id flows across the seam without synthesis.
        def granted_response(la_request, now):
            return {
                "decision": LA_DECISION_GRANTED,
                "token_id": "tok-d0c-a",
                "granted_capacity": la_request["requested_capacity"],
                "scope": la_request["scope"],
                "expires_at": now + la_request["expires_after"],
                "receipt": "la_rcpt_grant_d0c_a",
            }

        la_client = LinearAccountantClient(
            request_capacity_callable=granted_response,
            consume_callable=lambda r, n: pytest.fail("consume not under test"),
            admission_verifier=(
                lambda rid: sink.receipt_store.get_by_id(rid) is not None
            ),
            receipt_sink=sink,
        )
        la_result = la_client.request_capacity(
            CookedCapacityRequest(
                request_id="req-d0c-a",
                actor="agent-d0c-a",
                action="write_file",
                target="/tmp/d0c-a",
                scope="fs_write",
                requested_capacity=1,
                # The wicket-emitted admission id carries forward verbatim.
                admission_receipt_id=admission.receipt_id,
                eligibility_valid_until=1000,
                expires_after=1000,
            ),
            now=0,
        )
        # LA granted — proving the verifier resolved the wicket-emitted id
        # through the same store rather than the LA client refusing on
        # dangling_receipt_reference.
        assert isinstance(la_result, GrantedResult)
        assert la_result.token_id == "tok-d0c-a"

    def test_admission_no_sink_preserves_back_compat(self):
        """Absent sink: WicketVerdict still returned, receipt_id is None."""
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake_standing = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        mock_wicket = _MockWicketCheck()
        # No receipt_sink wired on either client.
        standing = StandingClient(verify_fn=fake_standing)
        client = WicketClient(
            standing_client=standing,
            wicket_check_fn=mock_wicket,
        )
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check(cooked)
        assert isinstance(result, WicketVerdict)
        # Verdict pass-through still works.
        assert result.value is _MockWicketCheck.SENTINEL_VERDICT
        # No sink → no receipt id (back-compat with D0a callers).
        assert result.receipt_id is None
        assert result.parent_receipt_id is None
