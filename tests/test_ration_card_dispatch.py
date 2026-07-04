# SPDX-License-Identifier: Apache-2.0
"""Slice 7 (allowlist slice) — ration-card dispatch of one live external agent.

> Tiny door, big lock, little sign saying "no, even for you."

The boss fight: a live external agent is dispatched ONCE, under fresh governed
admission + durable spend, produces an inert report, and CANNOT convert its
report / transcript / success into authority for a second action.

The laundering walls are the point — they get more tests than the happy path:
agent transcript ≠ authority · agent success ≠ authority · report ≠ authority ·
dispatch receipt ≠ permission to dispatch again · allowlist membership ≠ Standing
grant · LA spend ≠ arbitrary tool access · human refusal wins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
from governor.playbooks.durable_spend import (
    DurablePlaybookSpendGate,
    DurableSpendLedger,
    PlaybookSpendIntent,
)
from governor.playbooks.ration_card import (
    GOVERNED_DISPATCH_REPORT_GATE,
    REFUSED_AGENT_EXCEEDED_CARD,
    REFUSED_HUMAN_REFUSAL,
    REFUSED_OUTSIDE_RATION_CARD,
    AgentRunResult,
    DispatchNotRun,
    DispatchRefused,
    DispatchRequest,
    DispatchResult,
    RationCard,
    dispatch_under_ration_card,
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
_AGENT = "claude-code-runner-1"
_TASK = "read_only_audit"


# --------------------------------------------------------------------------- #
# A fake one-shot agent runner (the live Claude Code / Gemini adapter in prod).
# --------------------------------------------------------------------------- #


class _FakeRunner:
    def __init__(self, *, succeeded=True, transcript="ran audit", produced_writes=()):
        self.calls = 0
        self._result = AgentRunResult(
            succeeded=succeeded,
            transcript=transcript,
            produced_writes=frozenset(produced_writes),
        )

    def run_once(self, request: DispatchRequest) -> AgentRunResult:
        self.calls += 1
        return self._result


def _cooked(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="agent-governor",
        actor_standing=ActorStanding(cls="execute", provenance="caller_asserted"),
        intended_action="playbook.dispatch",
        operation_class="execute",
        target="sandbox://audit",
        claimed_basis={"rule": "ration-card dispatch", "evidence_refs": []},
        precedence=Precedence(resolution="active", provenance="caller_asserted"),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
        ),
        expected_effect="dispatch one external agent for one read-only audit",
        call_timestamp="2026-06-25T00:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True, provenance="caller_asserted"
        ),
    )


def _capacity_template() -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-disp-7",
        actor="agent-governor",
        action="dispatch_agent",
        target="sandbox://audit",
        scope="dispatch",
        requested_capacity=1,
        admission_receipt_id="PLACEHOLDER",
        eligibility_valid_until=10_000,
        expires_after=10_000,
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-disp-7",
        token_id="PLACEHOLDER",
        actor="agent-governor",
        action="dispatch_agent",
        target="sandbox://audit",
        amount=1,
        scope="dispatch",
    )


def _granted(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": "tok-disp-7",
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        "receipt": {"la_receipt_id": "la-grant-disp-7"},
    }


def _consumed(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": la_request["token_id"],
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la-consume-disp-7"},
    }


def _denied(la_request: dict, now: int) -> dict:
    return {"decision": LA_DECISION_DENIED, "denial_reason": "no capacity", "receipt": {}}


def _admit_any(cooked_context: CookedContext) -> dict:
    return {"surface_verdict": "authorized", "_fake": True}


def _evidence(name: str = "dispatch-playbook") -> PlaybookAdmissionEvidence:
    spec = parse_playbook(
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        "steps:\n"
        "  - id: d1\n"
        "    action: dispatch_agent\n"
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


def _intent(spec_digest: str, *, step_id: str = "d1") -> PlaybookSpendIntent:
    return PlaybookSpendIntent(
        step_id=step_id,
        principal="agent-governor",
        effect="dispatch_agent",
        resource="dispatch:sandbox://audit",
        amount=1,
        playbook_spec_digest=spec_digest,
    )


def _card(**overrides) -> RationCard:
    base = dict(agent_id=_AGENT, task_kind=_TASK)
    base.update(overrides)
    return RationCard(**base)


def _request(**overrides) -> DispatchRequest:
    base = dict(agent_id=_AGENT, task_kind=_TASK)
    base.update(overrides)
    return DispatchRequest(**base)


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


def _dispatch(orch, wrapped, *, card=None, request=None, runner=None, refusal_check=None,
              standing="valid", spec_digest=None):
    ev = _evidence()
    sid = _VALID_DIGEST if standing == "valid" else (None if standing == "none" else standing)
    return dispatch_under_ration_card(
        orch,
        card=card or _card(),
        request=request or _request(),
        runner=runner or _FakeRunner(),
        cooked_context=_cooked(sid),
        capacity_request_template=_capacity_template(),
        consume_request_template=_consume_template(),
        now=0,
        playbook_evidence=ev,
        playbook_spend_intent=_intent(spec_digest or ev.spec_digest),
        receipt_sink=wrapped,
        refusal_check=refusal_check,
    )


def _dispatch_reports(sink: GateReceiptSystem) -> list[Any]:
    return [r for r in sink.receipt_store.all() if r.gate == GOVERNED_DISPATCH_REPORT_GATE]


# --------------------------------------------------------------------------- #
# Happy path: one dispatch, inert report.
# --------------------------------------------------------------------------- #


class TestDispatchHappyPath:
    def test_dispatches_once_and_reports(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        runner = _FakeRunner()
        result = _dispatch(orch, wrapped, runner=runner)

        assert isinstance(result, DispatchResult)
        assert runner.calls == 1
        assert result.report.succeeded is True
        assert result.report.non_authoritative is True
        assert len(_dispatch_reports(sink)) == 1


# --------------------------------------------------------------------------- #
# THE LAUNDERING WALLS — these matter more than the happy path.
# --------------------------------------------------------------------------- #


class TestLaunderingWalls:
    def test_transcript_and_success_and_report_are_not_authority(self, tmp_path: Path):
        """agent transcript ≠ authority, agent success ≠ authority,
        report ≠ authority — the dispatch report (carrying the transcript digest
        and the success flag) is observe-verdict and fails the authority
        predicate, so the Slice-4 spend-basis wall refuses it."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        _dispatch(orch, wrapped, runner=_FakeRunner(succeeded=True))

        report = _dispatch_reports(sink)[0]
        assert report.verdict == "observe"
        assert is_authority_admission_receipt(report) is False
        bundle = sink.evidence_for(report)
        assert bundle["non_authoritative"] is True
        assert bundle["agent_succeeded"] is True
        # The transcript is reduced to a digest — the raw text is never a claim.
        assert "transcript_digest" in bundle
        assert "transcript" not in bundle

    def test_dispatch_receipt_is_not_permission_to_dispatch_again(self, tmp_path: Path):
        """A second dispatch needs a FRESH spend; the durable gate refuses the
        replay, so the dispatch report is not a re-dispatch permission."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        spend_root = tmp_path / "spend"
        ev = _evidence()

        orch1, w1 = _build(sink, spend_root)
        runner1 = _FakeRunner()
        first = _dispatch(orch1, w1, runner=runner1, spec_digest=ev.spec_digest)
        assert isinstance(first, DispatchResult)
        assert runner1.calls == 1

        orch2, w2 = _build(sink, spend_root)  # same durable ledger → replay
        runner2 = _FakeRunner()
        replay = _dispatch(orch2, w2, runner=runner2, spec_digest=ev.spec_digest)
        assert isinstance(replay, DispatchNotRun)
        # The agent was NOT dispatched a second time.
        assert runner2.calls == 0
        assert len(_dispatch_reports(sink)) == 1

    def test_allowlist_membership_is_not_standing_grant(self, tmp_path: Path):
        """Being on the card does NOT grant Standing. With a valid card+request
        but no Standing, the chain refuses and the agent never runs."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend", standing_valid=False)
        runner = _FakeRunner()
        result = _dispatch(orch, wrapped, runner=runner, standing="none")
        assert isinstance(result, DispatchNotRun)
        assert result.chain_seam == "wicket_seam"
        assert runner.calls == 0
        assert _dispatch_reports(sink) == []

    def test_standing_grant_is_not_la_spend(self, tmp_path: Path):
        """Standing authorizes but LA denies → no spend → no dispatch."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend", request_capacity_callable=_denied)
        runner = _FakeRunner()
        result = _dispatch(orch, wrapped, runner=runner)
        assert isinstance(result, DispatchNotRun)
        assert result.chain_seam == "la_seam_request"
        assert runner.calls == 0

    def test_la_spend_is_not_arbitrary_tool_access(self, tmp_path: Path):
        """A spend authorizes ONLY the carded task. A request for an out-of-card
        write refuses BEFORE any spend — the card is a separate necessary gate,
        never unlocked by a spend."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        runner = _FakeRunner()
        result = _dispatch(
            orch,
            wrapped,
            card=_card(allowed_write_paths=frozenset({"reports/audit.json"})),
            request=_request(requested_write_paths=frozenset({"/etc/passwd"})),
            runner=runner,
        )
        assert isinstance(result, DispatchRefused)
        assert result.refusal_kind == REFUSED_OUTSIDE_RATION_CARD
        assert runner.calls == 0
        # No spend was made for an out-of-card request.
        assert sink.receipt_store.all() == [] or all(
            r.gate != "la_seam" for r in sink.receipt_store.all()
        )

    def test_agent_writing_outside_card_is_fenced_after_the_fact(self, tmp_path: Path):
        """Even the agent's actual output is fenced: a runner that writes outside
        the card is refused (auditable), its output denied effect."""
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        runner = _FakeRunner(produced_writes={"reports/audit.json", "../escape.txt"})
        result = _dispatch(
            orch,
            wrapped,
            card=_card(allowed_write_paths=frozenset({"reports/audit.json"})),
            request=_request(requested_write_paths=frozenset({"reports/audit.json"})),
            runner=runner,
        )
        assert isinstance(result, DispatchRefused)
        assert result.refusal_kind == REFUSED_AGENT_EXCEEDED_CARD
        # The agent did run (we cannot un-run it), but its output is denied a
        # report receipt — no inert report is minted for an over-reaching run.
        assert runner.calls == 1
        assert _dispatch_reports(sink) == []

    def test_human_refusal_wins_before_any_spend(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        runner = _FakeRunner()
        result = _dispatch(
            orch, wrapped, runner=runner, refusal_check=lambda: "operator killed it"
        )
        assert isinstance(result, DispatchRefused)
        assert result.refusal_kind == REFUSED_HUMAN_REFUSAL
        assert runner.calls == 0
        # Refusal wins before the chain even runs — nothing spent.
        assert sink.receipt_store.all() == []


# --------------------------------------------------------------------------- #
# Card construction: dangerous axes are locked closed by type.
# --------------------------------------------------------------------------- #


class TestCardLocks:
    @pytest.mark.parametrize(
        "kw",
        [
            {"git_allowed": True},
            {"doctrine_writes_allowed": True},
            {"network_allowed": True},
            {"output_is_observe_only": False},
        ],
    )
    def test_card_refuses_dangerous_axes(self, kw):
        with pytest.raises(ValueError):
            _card(**kw)

    def test_wrong_agent_refuses(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        orch, wrapped = _build(sink, tmp_path / "spend")
        runner = _FakeRunner()
        result = _dispatch(
            orch, wrapped, request=_request(agent_id="some-other-agent"), runner=runner
        )
        assert isinstance(result, DispatchRefused)
        assert result.refusal_kind == REFUSED_OUTSIDE_RATION_CARD
        assert runner.calls == 0
