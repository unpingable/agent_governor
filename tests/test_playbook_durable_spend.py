# SPDX-License-Identifier: Apache-2.0
"""Slice 5 — durable, exactly-once playbook spend (the first Track A pickup).

> Durability is not permission.

The boss fight: the SAME playbook activation, retried after a crash/replay,
**does not double-spend**. The durable write-ahead ledger refuses the replayed
spend before any LA call — replay is boring. Plus: the spend is bound to the
authority admission (never the observe evidence record), an unbound spend is
rejected, and non-durable callers are byte-identical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governor.cooked_context_orchestrator import (
    ORIGIN_MODE_STUB,
    SEAM_DURABLE_SPEND,
    SEAM_WICKET,
    CookedContextOrchestrator,
    DemonstratedConsumed,
    build_authority_admission_verifier,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
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
from governor.playbooks.durable_spend import (
    REFUSED_DURABLE_REPLAY,
    REFUSED_INCOMPLETE_BASIS,
    DurablePlaybookSpendGate,
    DurableSpendLedger,
    DurableSpendRefusal,
    PlaybookSpendBasis,
    PlaybookSpendIntent,
    durable_spend_key,
)
from governor.standing_client import (
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
)

_VALID_DIGEST = "a" * 64


# --------------------------------------------------------------------------- #
# Fixtures (mirror the Slice 4 spend-chain fixtures, plus a durable gate).
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
        request_id="req-pb-5",
        actor="claude-code",
        action="write_file",
        target="sandbox://x.txt",
        scope="fs_write",
        requested_capacity=1,
        admission_receipt_id="PLACEHOLDER",
        eligibility_valid_until=10_000,
        expires_after=10_000,
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-pb-5",
        token_id="PLACEHOLDER",
        actor="claude-code",
        action="write_file",
        target="sandbox://x.txt",
        amount=1,
        scope="fs_write",
    )


def _granted(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": "tok-pb-5",
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        "receipt": {"la_receipt_id": "la-grant-pb-5"},
    }


def _consumed(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": la_request["token_id"],
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la-consume-pb-5"},
    }


def _admit_any(cooked_context: CookedContext) -> dict:
    return {"surface_verdict": "authorized", "_fake": True}


def _evidence(name: str = "alpha") -> PlaybookAdmissionEvidence:
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


def _intent(
    *, step_id: str = "s1", spec_digest: str | None = None
) -> PlaybookSpendIntent:
    return PlaybookSpendIntent(
        step_id=step_id,
        principal="claude-code",
        effect="write_file",
        resource="fs_write:sandbox://x.txt",
        amount=1,
        playbook_spec_digest=spec_digest or ("d" * 64),
    )


class _CountingConsume:
    """Counts how many times LA consume is actually invoked across runs."""

    def __init__(self):
        self.n = 0

    def __call__(self, la_request: dict, now: int) -> dict:
        self.n += 1
        return _consumed(la_request, now)


def _build(
    sink: GateReceiptSystem,
    ledger_root: Path,
    *,
    standing_valid: bool = True,
    consume_callable=_consumed,
    request_capacity_callable=_granted,
    with_durable_gate: bool = True,
):
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
    gate = (
        DurablePlaybookSpendGate(DurableSpendLedger(ledger_root), receipt_sink=wrapped)
        if with_durable_gate
        else None
    )
    return CookedContextOrchestrator(
        wicket_client=wicket,
        la_client=la,
        origin_mode=ORIGIN_MODE_STUB,
        durable_spend_gate=gate,
    )


def _receipts_by_gate(sink: GateReceiptSystem, gate: str) -> list[Any]:
    return [r for r in sink.receipt_store.all() if r.gate == gate]


# --------------------------------------------------------------------------- #
# THE BOSS FIGHT: replay does not double-spend.
# --------------------------------------------------------------------------- #


class TestReplayIsBoring:
    def test_replay_does_not_double_spend(self, tmp_path: Path):
        """Run the same playbook spend twice against the SAME durable ledger
        (simulating a crash/replay). The second run refuses at the durable gate
        before any LA consume — exactly one consume total."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        consume = _CountingConsume()
        ev, intent = _evidence(), _intent(spec_digest=_evidence().spec_digest)

        orch1 = _build(sink, ledger_root, consume_callable=consume)
        first = orch1.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=intent,
        )
        assert first.consumed is True
        assert consume.n == 1

        # Fresh orchestrator (new process), SAME durable ledger root → replay.
        orch2 = _build(sink, ledger_root, consume_callable=consume)
        replay = orch2.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=intent,
        )
        assert replay.refused is True
        assert replay.seam == SEAM_DURABLE_SPEND
        assert isinstance(replay.outcome, DurableSpendRefusal)
        assert replay.outcome.refusal_kind == REFUSED_DURABLE_REPLAY
        # The teeth: LA consume was invoked exactly ONCE across both runs.
        assert consume.n == 1

    def test_distinct_spends_are_not_replays(self, tmp_path: Path):
        """A different step (different durable key) is NOT a replay — it spends
        on its own. Only the SAME spend identity refuses."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        consume = _CountingConsume()
        ev = _evidence()
        orch = _build(sink, ledger_root, consume_callable=consume)

        for step in ("s1", "s2"):
            res = orch.run(
                _cooked(_VALID_DIGEST),
                _capacity_template(),
                _consume_template(),
                now=0,
                playbook_evidence=ev,
                playbook_spend_intent=_intent(
                    step_id=step, spec_digest=ev.spec_digest
                ),
            )
            assert res.consumed is True, step
        # Two distinct spends → two consumes.
        assert consume.n == 2


# --------------------------------------------------------------------------- #
# Spend basis is authority-bound and complete.
# --------------------------------------------------------------------------- #


class TestSpendBinding:
    def test_unbound_spend_is_rejected(self, tmp_path: Path):
        """A spend whose intent is missing a binding field (empty step_id) is
        rejected at the durable gate — no LA consume."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        consume = _CountingConsume()
        ev = _evidence()
        orch = _build(sink, ledger_root, consume_callable=consume)

        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=_intent(step_id="", spec_digest=ev.spec_digest),
        )
        assert result.refused is True
        assert result.seam == SEAM_DURABLE_SPEND
        assert isinstance(result.outcome, DurableSpendRefusal)
        assert result.outcome.refusal_kind == REFUSED_INCOMPLETE_BASIS
        assert consume.n == 0

    def test_durable_key_binds_authority_receipt(self, tmp_path: Path):
        """Two bases identical except for the authority admission receipt id
        produce different durable keys — the spend is authority-bound."""
        intent = _intent(spec_digest=_VALID_DIGEST)
        a = PlaybookSpendBasis.from_intent(intent, authority_admission_receipt_id="rcpt-A")
        b = PlaybookSpendBasis.from_intent(intent, authority_admission_receipt_id="rcpt-B")
        assert durable_spend_key(a) != durable_spend_key(b)

    def test_spend_claim_cites_admission_as_parent(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        ev = _evidence()
        orch = _build(sink, ledger_root)
        orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=_intent(spec_digest=ev.spec_digest),
        )
        claim = _receipts_by_gate(sink, "playbook_durable_spend")[0]
        assert claim.verdict == "observe"
        bundle = sink.evidence_for(claim)
        # The durable spend cites the wicket pass admission as parent.
        pass_admission = next(
            r
            for r in _receipts_by_gate(sink, "wicket_seam")
            if r.verdict == "pass"
        )
        assert bundle["parent_receipt_ids"] == [pass_admission.receipt_id]


# --------------------------------------------------------------------------- #
# Upstream gates still own their failures (durable gate is downstream).
# --------------------------------------------------------------------------- #


class TestUpstreamGatesUnchanged:
    def test_missing_standing_refuses_before_durable_gate(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        ev = _evidence()
        orch = _build(sink, ledger_root)
        result = orch.run(
            _cooked(None),  # no Standing
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            playbook_spend_intent=_intent(spec_digest=ev.spec_digest),
        )
        assert result.refused is True
        assert result.seam == SEAM_WICKET
        assert isinstance(result.outcome, WicketRefusal)
        assert result.outcome.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # The durable gate never ran (no claim receipt, ledger untouched).
        assert _receipts_by_gate(sink, "playbook_durable_spend") == []
        assert not DurableSpendLedger(ledger_root).is_claimed(
            durable_spend_key(
                PlaybookSpendBasis.from_intent(
                    _intent(spec_digest=ev.spec_digest),
                    authority_admission_receipt_id="x",
                )
            )
        )


# --------------------------------------------------------------------------- #
# Non-durable callers are byte-identical (no gate / no intent → unchanged).
# --------------------------------------------------------------------------- #


class TestNonDurableCallersPreserved:
    def test_no_gate_no_intent_runs_plain_spend(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        consume = _CountingConsume()
        ev = _evidence()
        orch = _build(
            sink, ledger_root, consume_callable=consume, with_durable_gate=False
        )
        # Playbook evidence but NO durable gate / intent → Slice 4 behavior.
        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
        )
        assert result.consumed is True
        assert consume.n == 1
        assert _receipts_by_gate(sink, "playbook_durable_spend") == []

    def test_gate_present_but_no_intent_skips_durable(self, tmp_path: Path):
        """Gate composed but no intent supplied → durable gate is skipped
        (a non-playbook chain through the same orchestrator is unchanged)."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        ledger_root = tmp_path / "spend"
        consume = _CountingConsume()
        ev = _evidence()
        orch = _build(sink, ledger_root, consume_callable=consume)
        result = orch.run(
            _cooked(_VALID_DIGEST),
            _capacity_template(),
            _consume_template(),
            now=0,
            playbook_evidence=ev,
            # no playbook_spend_intent
        )
        assert result.consumed is True
        assert consume.n == 1
        assert _receipts_by_gate(sink, "playbook_durable_spend") == []
