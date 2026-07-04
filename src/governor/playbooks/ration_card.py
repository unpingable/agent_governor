# SPDX-License-Identifier: Apache-2.0
"""Ration-card dispatch (Slice 7 — allowlist slice, NOT a behavior loop).

> Autopilot begins when the agent can spend a permission without remembering it.

The first slice where AG dispatches a **live external agent** — and so the first
where the supervisor's external-agent surface is the right one. But this is an
*allowlist* slice, not bounded autopilot: a governed playbook may dispatch ONE
named external agent to perform ONE predeclared boring task, under a brutally
narrow ration card, with fresh admission + durable spend, producing only
**non-authoritative** receipts. No loop. No discretionary task selection.

The boss fight:

    A live external agent is dispatched once, under fresh governed admission and
    durable spend, produces an inert report, and CANNOT convert its report,
    transcript, or success into authority for a second action.

The laundering walls (these matter more than the happy path):
- agent transcript ≠ authority      (the dispatch report is observe, fails the
- agent success ≠ authority          authority predicate; never a spend basis)
- report ≠ authority
- dispatch receipt ≠ permission to dispatch again  (a 2nd dispatch needs a fresh
                                                    spend; the durable gate refuses replay)
- allowlist membership ≠ Standing grant  (the card is a SEPARATE necessary gate;
                                          the chain still requires Standing-verified admission)
- Standing grant ≠ LA spend          (inherited from S4)
- LA spend ≠ arbitrary tool access   (a spend authorizes ONLY the carded task /
                                       agent / writes; out-of-card refuses; even the
                                       agent's actual output is fenced ⊆ the card)

Design — "tiny door, big lock". This does NOT make ``runtime/supervisor.py``
understand playbooks. It builds the ONE ration card the supervisor would carry:
a one-shot dispatch gate over a ``RationedAgentRunner`` (the narrow contract a
real runtime adapter satisfies — injected here so the slice is deterministically
testable; the live Claude Code / Gemini binding is a thin production adapter,
named in the exit ticket, not built into this gate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from governor.gate_receipt import canonical_json, content_hash

from .admission_evidence import PlaybookAdmissionEvidence
from .durable_spend import PlaybookSpendIntent

# Gate + verdict for the dispatch report. Distinct gate; observe verdict — a
# dispatch report decides nothing and authorizes nothing.
GOVERNED_DISPATCH_REPORT_GATE = "governed_dispatch_report"
GOVERNED_DISPATCH_REPORT_VERDICT = "observe"

# Closed refusal vocabulary for this seam.
REFUSED_OUTSIDE_RATION_CARD = "dispatch_outside_ration_card"
REFUSED_HUMAN_REFUSAL = "dispatch_human_refused"
REFUSED_AGENT_EXCEEDED_CARD = "dispatch_agent_exceeded_card"
DISPATCH_REFUSALS = frozenset(
    {
        REFUSED_OUTSIDE_RATION_CARD,
        REFUSED_HUMAN_REFUSAL,
        REFUSED_AGENT_EXCEEDED_CARD,
    }
)

# Why a dispatch did not run (the governed chain refused before the spend).
DISPATCH_NOT_RUN_CHAIN_DID_NOT_SPEND = "chain_did_not_spend"


@dataclass(frozen=True)
class RationCard:
    """The tiny allowlist authorizing exactly ONE dispatch of ONE external agent
    for ONE predeclared chore. Brutally narrow by construction.

    Absence-restrictive (allowlist, not blocklist): a write path / shell command
    not explicitly listed is forbidden; a novel one is refused, never admitted.
    The dangerous axes are **locked closed and cannot be opened in this slice** —
    ``__post_init__`` refuses a card that allows git, doctrine writes, network,
    or non-observe output. Tiny door, big lock, enforced by type.
    """

    agent_id: str  # one named external runner
    task_kind: str  # e.g. "read_only_audit"
    allowed_write_paths: frozenset[str] = field(default_factory=frozenset)
    allowed_shell_commands: frozenset[str] = field(default_factory=frozenset)
    # Locked-closed axes. Present as explicit refusals, not silent absence.
    git_allowed: bool = False
    doctrine_writes_allowed: bool = False
    network_allowed: bool = False
    output_is_observe_only: bool = True

    def __post_init__(self) -> None:
        if not self.agent_id or not self.task_kind:
            raise ValueError("RationCard requires a named agent_id and task_kind")
        # S7-first: these axes may not be opened. A card that tries is refused.
        if self.git_allowed:
            raise ValueError("ration card may not allow git in the allowlist slice")
        if self.doctrine_writes_allowed:
            raise ValueError("ration card may not allow doctrine writes")
        if self.network_allowed:
            raise ValueError("ration card may not allow network")
        if not self.output_is_observe_only:
            raise ValueError("ration card output must be observe-only")


@dataclass(frozen=True)
class DispatchRequest:
    """What the dispatched agent is actually asked to do — checked against the
    ration card. A request outside the card refuses; the card is the allowlist,
    never a suggestion."""

    agent_id: str
    task_kind: str
    requested_write_paths: frozenset[str] = field(default_factory=frozenset)
    requested_shell_commands: frozenset[str] = field(default_factory=frozenset)
    requested_network: bool = False
    requested_git: bool = False


@dataclass(frozen=True)
class AgentRunResult:
    """What the dispatched external agent produced. ``transcript`` is opaque text;
    ``produced_writes`` is the set of paths it actually wrote (fenced ⊆ card)."""

    succeeded: bool
    transcript: str
    produced_writes: frozenset[str] = field(default_factory=frozenset)


class RationedAgentRunner(Protocol):
    """The narrow one-shot dispatch contract. Production: a thin wrapper over a
    ``runtime.RuntimeAdapter`` (launch → drive the one task to completion →
    collect transcript → shutdown). Injected here so the gate is testable."""

    def run_once(self, request: DispatchRequest) -> AgentRunResult: ...


def _subset_violation(
    requested: frozenset[str], allowed: frozenset[str]
) -> frozenset[str]:
    return requested - allowed


def match_ration_card(
    card: RationCard, request: DispatchRequest
) -> Optional[str]:
    """Return None if the request is within the card, else a human-readable
    reason. The card is the allowlist: agent + task must match exactly, every
    requested write/shell must be listed, and the locked axes (network/git) must
    be unrequested."""
    if request.agent_id != card.agent_id:
        return (
            f"agent {request.agent_id!r} is not the carded agent {card.agent_id!r}"
        )
    if request.task_kind != card.task_kind:
        return (
            f"task {request.task_kind!r} is not the carded task {card.task_kind!r}"
        )
    extra_writes = _subset_violation(
        request.requested_write_paths, card.allowed_write_paths
    )
    if extra_writes:
        return f"write paths outside the card: {sorted(extra_writes)}"
    extra_shell = _subset_violation(
        request.requested_shell_commands, card.allowed_shell_commands
    )
    if extra_shell:
        return f"shell commands outside the card: {sorted(extra_shell)}"
    if request.requested_network:
        return "network requested but the card locks network closed"
    if request.requested_git:
        return "git requested but the card locks git closed"
    return None


@dataclass(frozen=True)
class DispatchReport:
    """The (always non-authoritative) result of a dispatch. Records the agent's
    outcome and a digest of its transcript — never lets the transcript itself
    become a claim."""

    agent_id: str
    task_kind: str
    succeeded: bool
    transcript_digest: str
    non_authoritative: bool = True


@dataclass(frozen=True)
class DispatchResult:
    """The agent was dispatched once (the chain spent and the card matched).
    Carries the non-authoritative report + receipt id."""

    report: DispatchReport
    spend_seam: str
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


@dataclass(frozen=True)
class DispatchNotRun:
    """The dispatch did not happen because the governed chain refused before the
    spend (no admission / no spend / replay). ``chain_seam`` names where."""

    reason: str
    chain_seam: str


@dataclass(frozen=True)
class DispatchRefused:
    """The dispatch was refused at the ration-card / human / agent-fence layer.
    ``refusal_kind`` ∈ ``DISPATCH_REFUSALS``. A refusal here means the external
    agent was NOT run (or its output was fenced after the fact)."""

    refusal_kind: str
    detail: str
    receipt_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.refusal_kind not in DISPATCH_REFUSALS:
            raise ValueError(
                f"refusal_kind {self.refusal_kind!r} not in {sorted(DISPATCH_REFUSALS)}"
            )


def _emit_dispatch_report(
    receipt_sink: Any | None,
    report: DispatchReport,
    *,
    parent_receipt_id: Optional[str],
) -> Optional[str]:
    if receipt_sink is None:
        return None
    evidence_bundle: dict[str, Any] = {
        "record_kind": "dispatch_report",
        "non_authoritative": True,
        "agent_id": report.agent_id,
        "task_kind": report.task_kind,
        "agent_succeeded": report.succeeded,
        "transcript_digest": report.transcript_digest,
        "parent_receipt_ids": [parent_receipt_id] if parent_receipt_id else [],
    }
    subject_bytes = (
        f"{report.agent_id}|{report.task_kind}|{report.transcript_digest}"
    ).encode("utf-8")
    receipt = receipt_sink.emit(
        gate=GOVERNED_DISPATCH_REPORT_GATE,
        verdict=GOVERNED_DISPATCH_REPORT_VERDICT,
        subject_kind="governed_dispatch_report",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence_bundle,
        gate_config={"seam": "S7_ration_card", "report": "non_authoritative"},
    )
    return receipt.receipt_id


def dispatch_under_ration_card(
    orchestrator: Any,
    *,
    card: RationCard,
    request: DispatchRequest,
    runner: RationedAgentRunner,
    cooked_context: Any,
    capacity_request_template: Any,
    consume_request_template: Any,
    now: int,
    playbook_evidence: PlaybookAdmissionEvidence,
    playbook_spend_intent: PlaybookSpendIntent,
    receipt_sink: Any | None = None,
    refusal_check: Optional[Callable[[], Optional[str]]] = None,
    finding_id: Optional[str] = None,
) -> DispatchResult | DispatchNotRun | DispatchRefused:
    """Dispatch ONE external agent for ONE carded chore, under the full governed
    chain. The order encodes the walls:

    1. **Human refusal wins** — ``refusal_check`` (the kill switch) is consulted
       first; a refusal refuses the dispatch *before any spend*. Refusal wins.
    2. **Ration card** — the request must be within the card (agent/task match,
       writes/shell ⊆ allowlist, network/git unrequested). Out-of-card refuses
       *before any spend* — the card is a SEPARATE necessary gate, never
       substitutable by a spend ("LA spend ≠ arbitrary tool access").
    3. **Governed chain** — fresh evidence + Standing authority + LA + durable
       spend (Slices 3–5). No spend ⇒ ``DispatchNotRun`` ⇒ the agent never runs.
       ("allowlist membership ≠ Standing grant": being carded does not authorize;
       the chain still demands fresh admission.)
    4. **Dispatch once** — the agent runs exactly once via the injected runner.
    5. **Fence the output** — the agent's actual writes are checked ⊆ the card;
       an over-reaching agent refuses *after the fact* (auditable), its output
       denied effect.
    6. **Non-authoritative report** — observe verdict; the transcript is reduced
       to a digest; the report cites the LA consume as parent. The transcript,
       the success, and the report are all structurally inert: none is authority.

    Replay safety is inherited: the durable spend gate refuses a replayed spend,
    so a re-dispatch returns ``DispatchNotRun`` — the dispatch receipt is NOT
    permission to dispatch again.
    """
    # 1. Human refusal wins — before any spend.
    if refusal_check is not None:
        reason = refusal_check()
        if reason:
            return DispatchRefused(
                refusal_kind=REFUSED_HUMAN_REFUSAL,
                detail=f"human/kill-switch refusal: {reason}",
            )

    # 2. Ration card — a separate necessary gate, checked before any spend.
    card_violation = match_ration_card(card, request)
    if card_violation:
        return DispatchRefused(
            refusal_kind=REFUSED_OUTSIDE_RATION_CARD,
            detail=card_violation,
        )

    # 3. Governed chain — fresh admission + durable spend. No spend, no dispatch.
    chain = orchestrator.run(
        cooked_context,
        capacity_request_template,
        consume_request_template,
        now,
        finding_id=finding_id,
        playbook_evidence=playbook_evidence,
        playbook_spend_intent=playbook_spend_intent,
    )
    if not chain.consumed:
        return DispatchNotRun(
            reason=DISPATCH_NOT_RUN_CHAIN_DID_NOT_SPEND, chain_seam=chain.seam
        )

    consumed_result = getattr(chain.outcome, "consumed_result", None)
    parent_receipt_id = getattr(consumed_result, "receipt_id", None)

    # 4. Dispatch the external agent exactly once.
    run = runner.run_once(request)

    # 5. Fence the agent's actual output ⊆ the card. Even agent output is fenced.
    overreach = _subset_violation(run.produced_writes, card.allowed_write_paths)
    if overreach:
        return DispatchRefused(
            refusal_kind=REFUSED_AGENT_EXCEEDED_CARD,
            detail=f"agent wrote outside the card: {sorted(overreach)}",
        )

    # 6. Non-authoritative report — transcript reduced to a digest.
    report = DispatchReport(
        agent_id=request.agent_id,
        task_kind=request.task_kind,
        succeeded=run.succeeded,
        transcript_digest=content_hash(
            canonical_json({"transcript": run.transcript})
        ),
    )
    rid = _emit_dispatch_report(
        receipt_sink, report, parent_receipt_id=parent_receipt_id
    )
    return DispatchResult(
        report=report,
        spend_seam=chain.seam,
        receipt_id=rid,
        parent_receipt_id=parent_receipt_id,
    )


__all__ = [
    "GOVERNED_DISPATCH_REPORT_GATE",
    "GOVERNED_DISPATCH_REPORT_VERDICT",
    "REFUSED_OUTSIDE_RATION_CARD",
    "REFUSED_HUMAN_REFUSAL",
    "REFUSED_AGENT_EXCEEDED_CARD",
    "DISPATCH_REFUSALS",
    "DISPATCH_NOT_RUN_CHAIN_DID_NOT_SPEND",
    "RationCard",
    "DispatchRequest",
    "AgentRunResult",
    "RationedAgentRunner",
    "match_ration_card",
    "DispatchReport",
    "DispatchResult",
    "DispatchNotRun",
    "DispatchRefused",
    "dispatch_under_ration_card",
]
