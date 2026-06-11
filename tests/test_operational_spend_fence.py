# SPDX-License-Identifier: Apache-2.0
"""Wall 1 of the simulated-evidence fence — the operational-consequence
type split and its spend wall (``confer_operational_effect``).

Ratified 2026-06-12 (option B amended). The fence is NOT a flag a downstream
consumer must remember to check ("downstream MUST check ``.operational``" is the
blocklist pattern wearing a flag costume — one forgetful consumer confers real
effect from a drill). The fence is a TYPE SPLIT with a runtime ``isinstance``
wall: a chain run under a non-operational origin produces a
``DemonstratedConsumed``, which the single spend/effect seam refuses by type.

Python types vanish at runtime, so these tests are the wall's teeth: handing a
``DemonstratedConsumed`` (or a bare ``ConsumedResult``, or anything else) to the
spend seam MUST raise. Without them the wall is theatre.

Two layers:

  * Spend-seam unit tests — ``confer_operational_effect`` admits exactly
    ``OperationalConsumed`` and refuses everything else.
  * Orchestrator wiring tests — ``run()`` maps origin_mode to the right
    outcome type for the WHOLE closed set: only ``observed`` is operational;
    drill / synthetic / replay / cli_origin / stub_origin demonstrate
    structure (the chain runs, receipts mint) but fence the spend.
"""

from __future__ import annotations

from typing import Any

import pytest

from governor.cooked_context_orchestrator import (
    AG_INTERNAL_ORIGIN_MODES,
    NQ_ORIGIN_MODES,
    OPERATIONAL_ORIGIN_MODES,
    ORIGIN_MODE_CLI,
    ORIGIN_MODE_DRILL,
    ORIGIN_MODE_OBSERVED,
    ORIGIN_MODE_REPLAY,
    ORIGIN_MODE_STUB,
    ORIGIN_MODE_SYNTHETIC,
    ORIGIN_REFUSED_NOT_OPERATIONAL,
    CookedContextOrchestrator,
    DemonstratedConsumed,
    NonOperationalSpendError,
    OperationalConsumed,
    OriginAdmission,
    confer_operational_effect,
    operational_admission,
    wrap_receipt_sink_with_origin_mode,
)
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_GRANTED,
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
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

# Every closed-set origin that is NOT operational. The fence must refuse the
# spend for all of these; ``observed`` is the sole operational mode.
NON_OPERATIONAL_MODES = sorted(
    (AG_INTERNAL_ORIGIN_MODES | NQ_ORIGIN_MODES) - OPERATIONAL_ORIGIN_MODES
)


# ---------------------------------------------------------------------------
# Fixtures for the spend-seam unit tests — a plausible ConsumedResult and the
# two wrapper types, built directly (no chain needed).
# ---------------------------------------------------------------------------


def _consumed_result(token_id: str = "tok-1") -> ConsumedResult:
    return ConsumedResult(
        token_id=token_id,
        consumed_amount=1,
        remaining_capacity=0,
        receipt={"la_receipt_id": "la-consume-xyz"},
        la_decision={"decision": LA_DECISION_CONSUMED},
        receipt_id="rcpt-consume-1",
        parent_receipt_id="rcpt-grant-1",
    )


def _operational(origin_mode: str = ORIGIN_MODE_OBSERVED) -> OperationalConsumed:
    return OperationalConsumed(
        consumed_result=_consumed_result(),
        origin_admission=operational_admission(origin_mode),
    )


def _demonstrated(origin_mode: str = ORIGIN_MODE_DRILL) -> DemonstratedConsumed:
    return DemonstratedConsumed(
        consumed_result=_consumed_result(),
        origin_admission=operational_admission(origin_mode),
    )


# ---------------------------------------------------------------------------
# Spend-seam unit tests — confer_operational_effect.
# ---------------------------------------------------------------------------


class TestSpendSeamWall:
    def test_operational_passes_and_returns_underlying_result(self):
        op = _operational()
        out = confer_operational_effect(op)
        # The seam returns the exact underlying LA result for the caller to act on.
        assert out is op.consumed_result
        assert isinstance(out, ConsumedResult)

    def test_demonstrated_is_refused_by_type(self):
        demo = _demonstrated(ORIGIN_MODE_DRILL)
        with pytest.raises(NonOperationalSpendError) as exc:
            confer_operational_effect(demo)
        # The refusal NAMES the offending origin and reason — a refused drill
        # spend audits differently from a refused synthetic spend.
        assert exc.value.origin_mode == ORIGIN_MODE_DRILL
        assert exc.value.reason == ORIGIN_REFUSED_NOT_OPERATIONAL

    @pytest.mark.parametrize("mode", NON_OPERATIONAL_MODES)
    def test_every_non_operational_mode_refused_at_the_seam(self, mode: str):
        demo = _demonstrated(mode)
        with pytest.raises(NonOperationalSpendError) as exc:
            confer_operational_effect(demo)
        assert exc.value.origin_mode == mode

    def test_bare_consumed_result_is_not_spendable(self):
        # A raw LA ConsumedResult carries no origin verdict. It must NOT be
        # spendable — only an outcome that went through the orchestrator's
        # fence (and came out OperationalConsumed) may confer effect.
        with pytest.raises(NonOperationalSpendError):
            confer_operational_effect(_consumed_result())

    def test_none_and_arbitrary_objects_refused(self):
        with pytest.raises(NonOperationalSpendError):
            confer_operational_effect(None)
        with pytest.raises(NonOperationalSpendError):
            confer_operational_effect("authorized")
        with pytest.raises(NonOperationalSpendError):
            confer_operational_effect(42)


class TestTypeDistinctness:
    """The structural unrepresentability claim: the two outcomes are distinct
    types, and neither is a ConsumedResult — so no ``isinstance(x,
    ConsumedResult)`` check anywhere can be fooled into spending a drill."""

    def test_operational_and_demonstrated_are_distinct_types(self):
        op = _operational()
        demo = _demonstrated()
        assert not isinstance(op, DemonstratedConsumed)
        assert not isinstance(demo, OperationalConsumed)

    def test_wrappers_are_not_consumed_results(self):
        # Composition, NOT subclassing: a DemonstratedConsumed must not pass
        # an ``isinstance(_, ConsumedResult)`` gate, or the wall has a hole.
        assert not isinstance(_operational(), ConsumedResult)
        assert not isinstance(_demonstrated(), ConsumedResult)

    def test_admission_verdict_matches_the_type(self):
        assert _operational().origin_admission.admitted is True
        assert _demonstrated().origin_admission.admitted is False


# ---------------------------------------------------------------------------
# Orchestrator wiring tests — origin_mode → outcome type, on a real chain.
# ---------------------------------------------------------------------------


def _cooked_context(standing_receipt_id: str) -> CookedContext:
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
        intended_action="write_file",
        operation_class="execute",
        target="/tmp/fence_target",
        claimed_basis={"rule": "test", "evidence_refs": []},
        precedence=Precedence(
            resolution="active", provenance="caller_asserted", evidence_refs=()
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
        request_id="req-fence-1",
        actor="claude-code",
        action="write_file",
        target="/tmp/fence_target",
        scope="fs_write",
        requested_capacity=1,
        admission_receipt_id="will-be-replaced",
        eligibility_valid_until=1000,
        expires_after=1000,
        idempotency_key="req-fence-1",
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-fence-1",
        token_id="will-be-replaced",
        actor="claude-code",
        action="write_file",
        target="/tmp/fence_target",
        amount=1,
        scope="fs_write",
    )


def _granted(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": "tok-fence",
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        "receipt": {"la_receipt_id": "la-grant-fence"},
    }


def _consumed(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": "tok-fence",
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la-consume-fence"},
    }


class _RecordingSink:
    """Minimal ReceiptSink: records every emit so we can prove the chain
    actually ran (structure demonstrated) even when fenced non-operational."""

    def __init__(self) -> None:
        self.emits: list[dict[str, Any]] = []

    def emit(
        self,
        gate: str,
        verdict: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_bundle: dict[str, Any],
        gate_config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        receipt = {
            "gate": gate,
            "verdict": verdict,
            "evidence_bundle": evidence_bundle,
            "receipt_id": f"rcpt-{len(self.emits)}",
        }
        self.emits.append(receipt)
        # Clients read ``.receipt_id`` off the returned object for chain
        # linkage; mirror the duck type with a tiny shim.
        return type("R", (), receipt)()


def _run_chain(origin_mode: str):
    standing_id = "a" * 64
    sink = _RecordingSink()
    wrapped = wrap_receipt_sink_with_origin_mode(sink, origin_mode)

    standing_client = StandingClient(
        verify_fn=lambda sid: StandingReceiptRef(
            digest=standing_id, kind="grant_activated"
        )
        if sid == standing_id
        else None,
        receipt_sink=wrapped,
    )
    wicket_client = WicketClient(
        standing_client=standing_client,
        wicket_check_fn=lambda cc: {"surface_verdict": "authorized"},
        receipt_sink=wrapped,
    )
    la_client = LinearAccountantClient(
        request_capacity_callable=_granted,
        consume_callable=_consumed,
        admission_verifier=lambda rid: True,
        receipt_sink=wrapped,
    )
    orchestrator = CookedContextOrchestrator(
        wicket_client=wicket_client,
        la_client=la_client,
        origin_mode=origin_mode,
    )
    result = orchestrator.run(
        cooked_context=_cooked_context(standing_id),
        capacity_request_template=_capacity_template(),
        consume_request_template=_consume_template(),
        now=0,
    )
    return result, sink


class TestOrchestratorOriginToType:
    def test_observed_is_operational_and_spendable(self):
        result, _ = _run_chain(ORIGIN_MODE_OBSERVED)
        assert result.consumed is True
        assert result.operational is True
        assert isinstance(result.outcome, OperationalConsumed)
        # The only operational origin: the spend seam admits it.
        spendable = confer_operational_effect(result.outcome)
        assert isinstance(spendable, ConsumedResult)
        assert spendable.token_id == "tok-fence"

    @pytest.mark.parametrize("mode", NON_OPERATIONAL_MODES)
    def test_non_operational_demonstrates_but_fences_the_spend(self, mode: str):
        result, sink = _run_chain(mode)
        # The chain MECHANICALLY ran — structure demonstrated, receipts minted
        # (zoning §Evidence classes: simulated may demonstrate structure).
        assert result.consumed is True
        assert len(sink.emits) >= 1
        # ...but it is NOT operational, and the spend seam refuses it by type.
        assert result.operational is False
        assert isinstance(result.outcome, DemonstratedConsumed)
        with pytest.raises(NonOperationalSpendError) as exc:
            confer_operational_effect(result.outcome)
        assert exc.value.origin_mode == mode

    def test_drill_receipts_still_carry_origin_mode_stamp(self):
        # The demonstration is honestly labeled: every minted receipt carries
        # origin_mode=drill, so nothing downstream can mistake it for observed.
        _, sink = _run_chain(ORIGIN_MODE_DRILL)
        assert sink.emits
        for receipt in sink.emits:
            assert receipt["evidence_bundle"]["origin_mode"] == ORIGIN_MODE_DRILL


def test_non_operational_modes_cover_the_whole_closed_set_minus_observed():
    # Pinning guard: if a new origin mode is added to the closed set, this
    # forces a decision about whether it is operational — it cannot silently
    # default. Every non-observed closed mode must be exercised above.
    assert set(NON_OPERATIONAL_MODES) == {
        ORIGIN_MODE_CLI,
        ORIGIN_MODE_STUB,
        ORIGIN_MODE_DRILL,
        ORIGIN_MODE_REPLAY,
        ORIGIN_MODE_SYNTHETIC,
    }
    assert OPERATIONAL_ORIGIN_MODES == frozenset({ORIGIN_MODE_OBSERVED})
