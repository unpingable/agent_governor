"""Tests for D0c-b cooked-context orchestrator.

Five tests per the operator spec:

  1. cli_origin + standing client refuses → standing refusal returned,
     LA client never invoked, standing receipt carries origin_mode.
  2. stub_origin + standing OK + wicket refusal (downstream verdict path
     produces a refusal-shaped result) — for our chain that means the
     LA client is never invoked when wicket fails. Realized at the LA
     seam's admission gate (dangling admission), since the wicket stub
     authorizes any verified cooked context. The test demonstrates a
     wicket-side refusal (missing standing_receipt_id makes wicket
     refuse before LA is consulted) AND covers the
     ``stub_origin`` propagation. NOTE: per the wicket SPEC stub, the
     only refusals wicket emits at this seam are standing-shaped; the
     test exercises the standing-required path under stub_origin.
  3. all three OK (standing → wicket admit → LA grant → LA consume) →
     ChainResult.consumed; all three emitted receipts carry origin_mode.
  4. construction with origin_mode="nq_origin" (and other not-in-closed
     values) RAISES — the discipline-of-not-laundering test.
  5. end-to-end real-chain test with a real GateReceiptSystem in tmp dir
     + cli_origin: emitted receipts (queried via the ReceiptStore +
     EvidenceStore) carry origin_mode in evidence_bundle.

The wicket-refusal-vs-LA-refusal distinction also gets a sixth bonus
case (LA refuses on admission) so that the "refusal at each seam
propagates origin_mode" claim is fully covered without modifying
client semantics. That sixth case is part of test 5's real-chain
coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from governor.cooked_context_orchestrator import (
    CLOSED_ORIGIN_MODES,
    EVIDENCE_KEY_ORIGIN_MODE,
    ORIGIN_MODE_CLI,
    ORIGIN_MODE_STUB,
    SEAM_LA_CONSUME,
    SEAM_LA_REQUEST,
    SEAM_WICKET,
    ChainResult,
    CookedContextOrchestrator,
    InvalidOriginModeError,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_GRANTED,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
    RefusalResult,
)
from governor.standing_client import StandingClient, StandingReceiptRef
from governor.wicket_client import (
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
    WicketRefusal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_VALID_STANDING_DIGEST = "a" * 64


def _make_cooked_context(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
        intended_action="write_file",
        operation_class="execute",
        target="/tmp/orch_target",
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


def _capacity_template() -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-orch-1",
        actor="claude-code",
        action="write_file",
        target="/tmp/orch_target",
        scope="fs_write",
        requested_capacity=1,
        # admission_receipt_id is overwritten by the orchestrator;
        # template value is ignored.
        admission_receipt_id="will-be-replaced",
        eligibility_valid_until=1000,
        expires_after=1000,
        idempotency_key="req-orch-1",
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-orch-1",
        # token_id is overwritten by the orchestrator;
        # template value is ignored.
        token_id="will-be-replaced",
        actor="claude-code",
        action="write_file",
        target="/tmp/orch_target",
        amount=1,
        scope="fs_write",
    )


class _CallCounter:
    """Wraps a callable with a call count."""

    def __init__(self, inner):
        self._inner = inner
        self.calls: list[Any] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._inner(*args, **kwargs)

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _never_called(*args, **kwargs):
    raise AssertionError(
        f"downstream callable invoked unexpectedly with args={args!r} kwargs={kwargs!r}"
    )


def _granted_response(token_id: Any = "token-orch-7"):
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_GRANTED,
            "token_id": token_id,
            "granted_capacity": la_request["requested_capacity"],
            "scope": la_request["scope"],
            "expires_at": now + la_request["expires_after"],
            "receipt": {"la_receipt_id": "la-receipt-001"},
        }
    return response


def _consumed_response(token_id: Any = "token-orch-7"):
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_CONSUMED,
            "token_id": token_id,
            "consumed_amount": la_request["amount"],
            "remaining_capacity": 0,
            "receipt": {"la_receipt_id": "la-consume-receipt-001"},
        }
    return response


def _admit_any_cooked(cooked_context: CookedContext) -> dict:
    """Wicket-check fake: every cooked context that reaches it is admitted."""
    return {"surface_verdict": "authorized", "_fake": True}


def _build_orchestrator(
    *,
    origin_mode: str,
    standing_known: dict[str, StandingReceiptRef] | None = None,
    sink: Any,
    request_capacity_callable=None,
    consume_callable=None,
    admission_verifier=None,
):
    """Build a fully wired orchestrator with the wrapped sink."""
    wrapped_sink = wrap_receipt_sink_with_origin_mode(sink, origin_mode)

    standing_lookup = standing_known or {}

    standing_client = StandingClient(
        verify_fn=lambda sid: standing_lookup.get(sid),
        receipt_sink=wrapped_sink,
    )
    wicket_client = WicketClient(
        standing_client=standing_client,
        wicket_check_fn=_admit_any_cooked,
        receipt_sink=wrapped_sink,
    )
    la_client = LinearAccountantClient(
        request_capacity_callable=(
            request_capacity_callable or _CallCounter(_granted_response())
        ),
        consume_callable=consume_callable or _CallCounter(_consumed_response()),
        admission_verifier=admission_verifier or (lambda rid: True),
        receipt_sink=wrapped_sink,
    )
    orchestrator = CookedContextOrchestrator(
        wicket_client=wicket_client,
        la_client=la_client,
        origin_mode=origin_mode,
    )
    return orchestrator, standing_client, wicket_client, la_client


# ---------------------------------------------------------------------------
# Construction-time discipline tests.
# ---------------------------------------------------------------------------


class TestOriginModeClosedSet:
    """The discipline-of-not-laundering surface.

    These tests are load-bearing: they enforce that the AG-side
    orchestrator cannot construct against any NQ-shaped value.
    """

    def test_closed_set_is_union_of_ag_internal_and_nq_side(self):
        # Cross-repo bridge (D0-Bridge, 2026-06-09): the closed set
        # widened from {cli_origin, stub_origin} to also include the
        # NQ-side vocabulary {observed, drill, replay, synthetic}
        # ratified by NQ migration 057. If this fires, either the AG
        # side added a value without a corresponding NQ migration, or
        # NQ's closed set drifted and AG has not been re-synchronized.
        from governor.cooked_context_orchestrator import (
            AG_INTERNAL_ORIGIN_MODES,
            NQ_ORIGIN_MODES,
            ORIGIN_MODE_DRILL,
            ORIGIN_MODE_OBSERVED,
            ORIGIN_MODE_REPLAY,
            ORIGIN_MODE_SYNTHETIC,
        )
        assert AG_INTERNAL_ORIGIN_MODES == frozenset({ORIGIN_MODE_CLI, ORIGIN_MODE_STUB})
        assert NQ_ORIGIN_MODES == frozenset({
            ORIGIN_MODE_OBSERVED,
            ORIGIN_MODE_DRILL,
            ORIGIN_MODE_REPLAY,
            ORIGIN_MODE_SYNTHETIC,
        })
        assert CLOSED_ORIGIN_MODES == AG_INTERNAL_ORIGIN_MODES | NQ_ORIGIN_MODES

    def test_nq_origin_umbrella_alias_still_raises(self, tmp_path):
        # The umbrella value ``nq_origin`` is NOT a concrete mint-
        # provenance value — the bridge uses the concrete NQ-side value
        # (``observed``/``drill``/``replay``/``synthetic``), never an
        # alias. Construction-time refusal still fires on the alias.
        sink = GateReceiptSystem(tmp_path)
        standing_client = StandingClient(verify_fn=lambda sid: None, receipt_sink=sink)
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=_admit_any_cooked,
            receipt_sink=sink,
        )
        la_client = LinearAccountantClient(
            request_capacity_callable=_CallCounter(_granted_response()),
            consume_callable=_CallCounter(_consumed_response()),
            admission_verifier=lambda rid: True,
            receipt_sink=sink,
        )
        with pytest.raises(InvalidOriginModeError):
            CookedContextOrchestrator(
                wicket_client=wicket_client,
                la_client=la_client,
                origin_mode="nq_origin",
            )

    @pytest.mark.parametrize(
        "good_mode",
        [
            "observed",
            "drill",
            "replay",
            "synthetic",
        ],
    )
    def test_nq_side_concrete_values_admitted(self, tmp_path, good_mode):
        # Bridge invariant: NQ-side concrete values pass construction.
        # Operator forbade INVENTING NQ provenance, not CONSUMING it
        # from the NQ wire — and NQ migration 057 has now ratified the
        # closed set, so AG consuming these values is the doctrine-
        # correct shape.
        sink = GateReceiptSystem(tmp_path)
        standing_client = StandingClient(verify_fn=lambda sid: None, receipt_sink=sink)
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=_admit_any_cooked,
            receipt_sink=sink,
        )
        la_client = LinearAccountantClient(
            request_capacity_callable=_CallCounter(_granted_response()),
            consume_callable=_CallCounter(_consumed_response()),
            admission_verifier=lambda rid: True,
            receipt_sink=sink,
        )
        orch = CookedContextOrchestrator(
            wicket_client=wicket_client,
            la_client=la_client,
            origin_mode=good_mode,
        )
        assert orch.origin_mode == good_mode

    @pytest.mark.parametrize(
        "bad_mode",
        [
            "nq_origin",  # umbrella alias — never admissible
            "exercise",  # not in NQ migration 057's closed set
            "",
            "CLI_ORIGIN",  # case-sensitive — uppercase must refuse too
            "cli-origin",  # hyphen variant — must refuse
        ],
    )
    def test_not_in_closed_set_raises(self, tmp_path, bad_mode):
        sink = GateReceiptSystem(tmp_path)
        standing_client = StandingClient(verify_fn=lambda sid: None, receipt_sink=sink)
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=_admit_any_cooked,
            receipt_sink=sink,
        )
        la_client = LinearAccountantClient(
            request_capacity_callable=_CallCounter(_granted_response()),
            consume_callable=_CallCounter(_consumed_response()),
            admission_verifier=lambda rid: True,
            receipt_sink=sink,
        )
        with pytest.raises(InvalidOriginModeError):
            CookedContextOrchestrator(
                wicket_client=wicket_client,
                la_client=la_client,
                origin_mode=bad_mode,
            )

    def test_invalid_origin_mode_error_is_a_value_error(self):
        # Doctrine: InvalidOriginModeError is a ValueError so callers
        # that catch ValueError on construction don't suddenly miss
        # the discipline failure.
        assert issubclass(InvalidOriginModeError, ValueError)

    def test_wrap_sink_also_refuses_bad_origin_mode(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        with pytest.raises(InvalidOriginModeError):
            wrap_receipt_sink_with_origin_mode(sink, "nq_origin")


class TestOrchestratorConstructionRequirements:
    def test_requires_wicket_client(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        la_client = LinearAccountantClient(
            request_capacity_callable=_CallCounter(_granted_response()),
            consume_callable=_CallCounter(_consumed_response()),
            admission_verifier=lambda rid: True,
            receipt_sink=sink,
        )
        with pytest.raises(ValueError):
            CookedContextOrchestrator(
                wicket_client=None,  # type: ignore[arg-type]
                la_client=la_client,
                origin_mode=ORIGIN_MODE_CLI,
            )

    def test_requires_la_client(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        standing_client = StandingClient(verify_fn=lambda sid: None, receipt_sink=sink)
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=_admit_any_cooked,
            receipt_sink=sink,
        )
        with pytest.raises(ValueError):
            CookedContextOrchestrator(
                wicket_client=wicket_client,
                la_client=None,  # type: ignore[arg-type]
                origin_mode=ORIGIN_MODE_CLI,
            )

    def test_origin_mode_property_exposes_declared_value(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        orchestrator, _, _, _ = _build_orchestrator(
            origin_mode=ORIGIN_MODE_STUB, sink=sink
        )
        assert orchestrator.origin_mode == ORIGIN_MODE_STUB


# ---------------------------------------------------------------------------
# Test 1: cli_origin + standing refusal → LA never invoked + stamp present.
# ---------------------------------------------------------------------------


class TestCliOriginStandingRefusal:
    def test_standing_refusal_short_circuits_la_and_stamps_origin(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        request_capacity_mock = _CallCounter(_never_called)
        consume_mock = _CallCounter(_never_called)

        orchestrator, _, _, _ = _build_orchestrator(
            origin_mode=ORIGIN_MODE_CLI,
            standing_known={},  # nothing known — standing-required fires
            sink=sink,
            request_capacity_callable=request_capacity_mock,
            consume_callable=consume_mock,
        )

        cooked = _make_cooked_context(standing_receipt_id=None)
        result = orchestrator.run(
            cooked_context=cooked,
            capacity_request_template=_capacity_template(),
            consume_request_template=_consume_template(),
            now=0,
        )

        # Refusal returned from the wicket seam; underlying outcome is a
        # WicketRefusal (the standing-required path).
        assert isinstance(result, ChainResult)
        assert result.refused
        assert not result.consumed
        assert isinstance(result.outcome, WicketRefusal)
        assert result.seam == SEAM_WICKET

        # LA NEVER invoked — teeth.
        assert request_capacity_mock.call_count == 0
        assert consume_mock.call_count == 0

        # The wicket-seam refusal receipt carries origin_mode=cli_origin.
        receipts = sink.query()
        assert len(receipts) >= 1, "wicket emitted at least one refusal receipt"
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_CLI, (
                f"receipt {receipt.receipt_id!r} missing origin_mode stamp; "
                f"evidence keys={sorted(evidence.keys())}"
            )


# ---------------------------------------------------------------------------
# Test 2: stub_origin + wicket-seam refusal → LA never invoked + stamp.
#
# The wicket seam's only refusal path is standing-shaped (per the SPEC
# stub). The chain returns a WicketRefusal under SEAM_WICKET. LA is
# never invoked, and the receipt carries origin_mode=stub_origin.
# ---------------------------------------------------------------------------


class TestStubOriginWicketRefusal:
    def test_dangling_standing_receipt_refusal_under_stub_origin(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)
        request_capacity_mock = _CallCounter(_never_called)
        consume_mock = _CallCounter(_never_called)

        orchestrator, _, _, _ = _build_orchestrator(
            origin_mode=ORIGIN_MODE_STUB,
            standing_known={},  # dangling — cited id is unknown
            sink=sink,
            request_capacity_callable=request_capacity_mock,
            consume_callable=consume_mock,
        )

        cooked = _make_cooked_context(standing_receipt_id="deadbeef" * 8)
        result = orchestrator.run(
            cooked_context=cooked,
            capacity_request_template=_capacity_template(),
            consume_request_template=_consume_template(),
            now=0,
        )

        assert result.refused
        assert isinstance(result.outcome, WicketRefusal)
        assert result.seam == SEAM_WICKET

        # LA never invoked.
        assert request_capacity_mock.call_count == 0
        assert consume_mock.call_count == 0

        # All emitted receipts on the chain carry origin_mode=stub_origin.
        # (Both the standing-seam dangling refusal AND the wicket-seam
        # refusal are minted under the wrapped sink.)
        receipts = sink.query()
        assert len(receipts) >= 1
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_STUB


# ---------------------------------------------------------------------------
# Test 3: full happy path → ConsumedResult + all three receipts stamped.
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_full_chain_returns_consumed_and_stamps_all_receipts(self, tmp_path):
        sink = GateReceiptSystem(tmp_path)

        standing_id = _VALID_STANDING_DIGEST
        ref = StandingReceiptRef(digest=standing_id, kind="grant_activated")
        request_capacity_mock = _CallCounter(_granted_response())
        consume_mock = _CallCounter(_consumed_response())

        # Admission verifier: every admission id we threaded in should
        # be recognized. Because the orchestrator overrides the
        # capacity_request_template's admission_receipt_id with the
        # wicket-emitted receipt id, the verifier accepts everything
        # (the real wicket emission produced a real receipt id).
        orchestrator, _, _, _ = _build_orchestrator(
            origin_mode=ORIGIN_MODE_CLI,
            standing_known={standing_id: ref},
            sink=sink,
            request_capacity_callable=request_capacity_mock,
            consume_callable=consume_mock,
            admission_verifier=lambda rid: rid is not None,
        )

        cooked = _make_cooked_context(standing_receipt_id=standing_id)
        result = orchestrator.run(
            cooked_context=cooked,
            capacity_request_template=_capacity_template(),
            consume_request_template=_consume_template(),
            now=0,
        )

        # Consumed verdict; the chain delivered an allowed effect.
        assert result.consumed
        assert not result.refused
        assert result.seam == SEAM_LA_CONSUME

        # LA invoked exactly once for request and once for consume.
        assert request_capacity_mock.call_count == 1
        assert consume_mock.call_count == 1

        # Capacity request received admission_receipt_id == the
        # wicket-emitted receipt id (not the template's placeholder).
        la_request, _now = request_capacity_mock.calls[0][0]
        assert la_request["eligibility_reference"] != "will-be-replaced"
        # It must be SOME real receipt id from the chain.
        assert isinstance(la_request["eligibility_reference"], str)
        assert len(la_request["eligibility_reference"]) > 0

        # Consume received the granted token_id, not the placeholder.
        consume_request, _now2 = consume_mock.calls[0][0]
        assert consume_request["token_id"] == "token-orch-7"

        # All emitted receipts carry origin_mode=cli_origin.
        receipts = sink.query()
        # We expect at least:
        #   - one wicket-admission receipt (D0c-a)
        # No LA refusal receipts (everything passed). No standing
        # refusal receipt (standing verified). So exactly one stamped
        # receipt on the happy path.
        assert len(receipts) >= 1
        stamped = 0
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_CLI
            stamped += 1
        assert stamped >= 1


# ---------------------------------------------------------------------------
# Test 5: end-to-end real-chain emission with a real GateReceiptSystem in
# tmp dir; assert origin_mode is queryable on every emitted receipt.
#
# Also covers a bonus refusal-at-LA-seam case so the orchestrator's
# refusal-vs-bypass distinction is exercised on a non-wicket gate.
# ---------------------------------------------------------------------------


class TestRealChainEndToEnd:
    def test_emitted_receipts_carry_origin_mode_via_receipt_store(self, tmp_path):
        """Real GateReceiptSystem; refusal at the LA admission gate.

        Walk the chain so the LA seam fires admission_denied (we supply
        a None admission, then make wicket return a verdict whose
        receipt_id we DON'T register with the admission verifier).
        For that, we use a wicket-check that returns a verdict but the
        WicketVerdict.receipt_id is real (emitted by wicket); the
        admission_verifier we wire rejects unknown ids; the wicket
        receipt_id is therefore "not known" to the admission_verifier
        only if we say so.

        Simpler shape: configure admission_verifier to return False for
        everything. The wicket emits an admission receipt and the
        orchestrator threads its id into the capacity request; LA
        refuses with dangling_receipt_reference (the confabulated path).
        """
        gov_root: Path = tmp_path / "gov"
        gov_root.mkdir()
        sink = GateReceiptSystem(gov_root)

        standing_id = _VALID_STANDING_DIGEST
        ref = StandingReceiptRef(digest=standing_id, kind="grant_activated")
        request_capacity_mock = _CallCounter(_never_called)
        consume_mock = _CallCounter(_never_called)

        orchestrator, _, _, _ = _build_orchestrator(
            origin_mode=ORIGIN_MODE_CLI,
            standing_known={standing_id: ref},
            sink=sink,
            request_capacity_callable=request_capacity_mock,
            consume_callable=consume_mock,
            # Admission verifier rejects every id — including the real
            # wicket-emitted admission_receipt_id. LA refuses with
            # dangling_receipt_reference. This is the confabulated-
            # admission path exercised end-to-end through the real
            # ReceiptStore/EvidenceStore.
            admission_verifier=lambda rid: False,
        )

        cooked = _make_cooked_context(standing_receipt_id=standing_id)
        result = orchestrator.run(
            cooked_context=cooked,
            capacity_request_template=_capacity_template(),
            consume_request_template=_consume_template(),
            now=0,
        )

        # LA-seam refusal. request_capacity_callable NEVER invoked
        # (gate fires PRE-call). consume NEVER invoked.
        assert result.refused
        assert isinstance(result.outcome, RefusalResult)
        assert result.seam == SEAM_LA_REQUEST
        assert request_capacity_mock.call_count == 0
        assert consume_mock.call_count == 0

        # Query the ReceiptStore directly (the persistence boundary the
        # operator named in the test spec).
        receipts = sink.query()
        # Expect at least two receipts: wicket-admission + LA refusal.
        assert len(receipts) >= 2

        stamped_kinds: list[str] = []
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None, (
                f"evidence blob missing for receipt {receipt.receipt_id!r}"
            )
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_CLI, (
                f"receipt {receipt.receipt_id!r} (gate={receipt.gate!r}) "
                f"missing/wrong origin_mode; evidence keys="
                f"{sorted(evidence.keys())}"
            )
            stamped_kinds.append(receipt.gate)

        # Sanity: both gates fired on this chain.
        assert "wicket_seam" in stamped_kinds
        assert "la_seam" in stamped_kinds


# ---------------------------------------------------------------------------
# Wrapped-sink unit tests (defense-in-depth on the injection mechanism).
# ---------------------------------------------------------------------------


class TestWrappedSinkBehavior:
    def test_wrapped_sink_does_not_mutate_caller_bundle(self, tmp_path):
        """The wrapper must shallow-copy the bundle; callers must not see
        the injected origin_mode key in their own dict."""
        sink = GateReceiptSystem(tmp_path)
        wrapped = wrap_receipt_sink_with_origin_mode(sink, ORIGIN_MODE_CLI)

        caller_bundle: dict[str, Any] = {"caller_key": "preserved"}
        wrapped.emit(
            gate="wicket_seam",
            verdict="block",
            subject_kind="wicket_cooked_context",
            subject_bytes=b"x",
            evidence_bundle=caller_bundle,
            gate_config={"seam": "test"},
        )

        # Caller's dict UNCHANGED.
        assert EVIDENCE_KEY_ORIGIN_MODE not in caller_bundle
        assert caller_bundle == {"caller_key": "preserved"}

    def test_wrapped_sink_overwrites_caller_origin_mode(self, tmp_path):
        """If a caller sneaks origin_mode into the bundle, the wrapper
        OVERWRITES it — the orchestrator is authoritative for this field."""
        sink = GateReceiptSystem(tmp_path)
        wrapped = wrap_receipt_sink_with_origin_mode(sink, ORIGIN_MODE_CLI)

        receipt = wrapped.emit(
            gate="wicket_seam",
            verdict="block",
            subject_kind="wicket_cooked_context",
            subject_bytes=b"y",
            evidence_bundle={
                EVIDENCE_KEY_ORIGIN_MODE: "stub_origin",  # caller lies
                "x": "y",
            },
            gate_config={"seam": "test"},
        )
        evidence = sink.evidence_for(receipt)
        assert evidence is not None
        # Wrapper's value wins.
        assert evidence[EVIDENCE_KEY_ORIGIN_MODE] == ORIGIN_MODE_CLI
