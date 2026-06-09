# SPDX-License-Identifier: Apache-2.0
"""Night Shift Governor Adapter.

Thin translation layer bridging Night Shift's expected RPC shape (per
`~/git/scheduler/docs/GAP-governor-contract.md`) to governor's existing
primitives:

- ``check_policy`` → ``policy_engine.evaluate`` + gate receipt
- ``record_receipt`` → ``GateReceiptSystem.emit``
- ``authorize_transition`` → ``policy_engine.evaluate`` + authority receipt

The adapter is translation only. No new policy logic. Verdict mapping is
deterministic and closed:

    PolicyVerdict.PASS     → NightShiftVerdict.ALLOW
    PolicyVerdict.BLOCK    → NightShiftVerdict.DENY
    PolicyVerdict.ESCALATE → NightShiftVerdict.REQUIRE_APPROVAL
    PolicyVerdict.WARN     → NightShiftVerdict.DOWNGRADE

See `specs/gaps/GOV_GAP_NIGHTSHIFT_ADAPTER_001.md` for design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .gate_receipt import (
    HorizonBlock,
    NonDischargeClaim,
    ROLE_AUTHORITY,
    ROLE_MEASUREMENT,
    GateReceipt,
    GateReceiptSystem,
)
from .policy_engine import (
    CAPABILITY_VOCAB_VERSION,
    Capability,
    ContextInfo,
    OBLIGATION_VOCAB_VERSION,
    PolicyEvalRequest,
    PolicyRuleSet,
    PolicyVerdict,
    PrincipalsInfo,
    SubjectInfo,
    SubjectKind,
    evaluate,
)


# =============================================================================
# Version
# =============================================================================

ADAPTER_VERSION = "1.0.0"
NIGHTSHIFT_ADAPTER_SCHEMA = "governor/nightshift_adapter/v1"


# =============================================================================
# Closed enums (frozen v1)
# =============================================================================


class AuthorityLevel(str, Enum):
    """Night Shift authority ladder, lowest to highest."""
    OBSERVE = "observe"
    ADVISE = "advise"
    STAGE = "stage"
    REQUEST = "request"
    APPLY = "apply"
    PUBLISH = "publish"


AUTHORITY_LEVEL_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.OBSERVE: 0,
    AuthorityLevel.ADVISE: 1,
    AuthorityLevel.STAGE: 2,
    AuthorityLevel.REQUEST: 3,
    AuthorityLevel.APPLY: 4,
    AuthorityLevel.PUBLISH: 5,
}


class BlastRadius(str, Enum):
    SINGLE_HOST = "single_host"
    MULTI_HOST = "multi_host"
    PUBLIC = "public"


class ToolClass(str, Enum):
    READ = "read"
    PROPOSE = "propose"
    STAGE = "stage"
    MUTATE = "mutate"
    PUBLISH = "publish"
    PAGE = "page"


class ActionKind(str, Enum):
    MCP_CALL = "mcp_call"
    TOOL_EXEC = "tool_exec"
    STATE_MUTATION = "state_mutation"
    PUBLISH = "publish"


class EventKind(str, Enum):
    """NS lifecycle events Governor produces authority receipts for."""
    AGENDA_PROMOTED = "agenda.promoted"
    ACTION_AUTHORIZED = "action.authorized"
    ACTION_APPLIED = "action.applied"
    ACTION_DENIED = "action.denied"
    ACTION_VERIFIED = "action.verified"
    ESCALATION_PAGED = "escalation.paged"


# Event kinds that carry promotion semantics emit a role=authority receipt.
# Measurement-class events emit a role=measurement receipt. Closed mapping —
# no inference from tone.
_AUTHORITY_EVENT_KINDS = frozenset({
    EventKind.AGENDA_PROMOTED,
    EventKind.ACTION_AUTHORIZED,
    EventKind.ACTION_APPLIED,
    EventKind.ACTION_DENIED,
})

_MEASUREMENT_EVENT_KINDS = frozenset({
    EventKind.ACTION_VERIFIED,
    EventKind.ESCALATION_PAGED,
})


def _receipt_role_for_event(event_kind: EventKind) -> str:
    if event_kind in _AUTHORITY_EVENT_KINDS:
        return ROLE_AUTHORITY
    if event_kind in _MEASUREMENT_EVENT_KINDS:
        return ROLE_MEASUREMENT
    # Unreachable under closed enum — defensive fail-closed.
    raise ValueError(f"Unmapped event_kind {event_kind!r}")


class NightShiftVerdict(str, Enum):
    """NS verdict vocabulary (per NS contract §check_policy response)."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    DOWNGRADE = "downgrade"


# Frozen verdict mapping. Changing this is a gap-spec supersession.
_VERDICT_MAP: dict[PolicyVerdict, NightShiftVerdict] = {
    PolicyVerdict.PASS: NightShiftVerdict.ALLOW,
    PolicyVerdict.BLOCK: NightShiftVerdict.DENY,
    PolicyVerdict.ESCALATE: NightShiftVerdict.REQUIRE_APPROVAL,
    PolicyVerdict.WARN: NightShiftVerdict.DOWNGRADE,
}


def translate_verdict(verdict: PolicyVerdict) -> NightShiftVerdict:
    """Map a policy_engine verdict to a Night Shift verdict.

    Deterministic. Every PolicyVerdict has exactly one NightShiftVerdict.
    """
    try:
        return _VERDICT_MAP[verdict]
    except KeyError as exc:
        raise ValueError(f"Unmapped PolicyVerdict {verdict!r}") from exc


# =============================================================================
# Request / response dataclasses
# =============================================================================


@dataclass(frozen=True)
class RequestedAction:
    """What NS wants to do.  Nested inside CheckPolicyRequest."""
    kind: str                 # ActionKind value
    tool_class: str           # ToolClass value
    tool_id: str
    arguments_hash: str       # sha256:<hex>
    blast_radius: str         # BlastRadius value
    reversible: bool

    def __post_init__(self) -> None:
        if self.kind not in {e.value for e in ActionKind}:
            raise ValueError(
                f"Invalid action kind {self.kind!r}; "
                f"must be one of {sorted(e.value for e in ActionKind)}"
            )
        if self.tool_class not in {e.value for e in ToolClass}:
            raise ValueError(
                f"Invalid tool_class {self.tool_class!r}; "
                f"must be one of {sorted(e.value for e in ToolClass)}"
            )
        if self.blast_radius not in {e.value for e in BlastRadius}:
            raise ValueError(
                f"Invalid blast_radius {self.blast_radius!r}; "
                f"must be one of {sorted(e.value for e in BlastRadius)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tool_class": self.tool_class,
            "tool_id": self.tool_id,
            "arguments_hash": self.arguments_hash,
            "blast_radius": self.blast_radius,
            "reversible": self.reversible,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequestedAction:
        return cls(
            kind=data["kind"],
            tool_class=data["tool_class"],
            tool_id=data["tool_id"],
            arguments_hash=data["arguments_hash"],
            blast_radius=data["blast_radius"],
            reversible=bool(data["reversible"]),
        )


@dataclass(frozen=True)
class CheckPolicyRequest:
    agenda_id: str
    run_id: str
    actor: str
    requested_action: RequestedAction
    authority_level: str          # AuthorityLevel value
    bundle_ref: str | None = None

    def __post_init__(self) -> None:
        if self.authority_level not in {e.value for e in AuthorityLevel}:
            raise ValueError(
                f"Invalid authority_level {self.authority_level!r}; "
                f"must be one of {sorted(e.value for e in AuthorityLevel)}"
            )
        for field_name in ("agenda_id", "run_id", "actor"):
            if not getattr(self, field_name):
                raise ValueError(f"CheckPolicyRequest.{field_name} is required")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agenda_id": self.agenda_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "requested_action": self.requested_action.to_dict(),
            "authority_level": self.authority_level,
        }
        if self.bundle_ref is not None:
            d["bundle_ref"] = self.bundle_ref
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckPolicyRequest:
        return cls(
            agenda_id=data["agenda_id"],
            run_id=data["run_id"],
            actor=data["actor"],
            requested_action=RequestedAction.from_dict(data["requested_action"]),
            authority_level=data["authority_level"],
            bundle_ref=data.get("bundle_ref"),
        )


@dataclass(frozen=True)
class CheckPolicyResponse:
    verdict: str                       # NightShiftVerdict value
    reason: str
    obligations: tuple[str, ...]       # ObligationKind values
    receipt_id: str
    downgrade_to: str | None = None    # AuthorityLevel value when verdict=downgrade

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "verdict": self.verdict,
            "reason": self.reason,
            "obligations": list(self.obligations),
            "receipt_id": self.receipt_id,
        }
        if self.downgrade_to is not None:
            d["downgrade_to"] = self.downgrade_to
        return d


@dataclass(frozen=True)
class RecordReceiptRequest:
    event_kind: str                 # EventKind value
    run_id: str
    agenda_id: str
    subject_hash: str               # sha256:<hex> — NS-computed
    evidence_hash: str              # sha256:<hex>
    policy_hash: str                # sha256:<hex>
    from_level: str | None = None   # AuthorityLevel value (for promotion events)
    to_level: str | None = None     # AuthorityLevel value (for promotion events)
    horizon: HorizonBlock | None = None   # optional tolerability declaration
    # Non-discharge claims this verdict explicitly does NOT settle.
    # Empty by default; NS populates a single `freshness` claim on
    # horizon-Defer outcomes (per
    # `~/git/scheduler/crates/nightshiftd/src/reconcile_horizon.rs`).
    # Other event kinds intentionally do not populate yet; initial
    # population is scoped to the already-witnessed horizon path.
    unsettled: tuple[NonDischargeClaim, ...] = ()

    def __post_init__(self) -> None:
        if self.event_kind not in {e.value for e in EventKind}:
            raise ValueError(
                f"Invalid event_kind {self.event_kind!r}; "
                f"must be one of {sorted(e.value for e in EventKind)}"
            )
        for field_name in (
            "run_id", "agenda_id", "subject_hash", "evidence_hash",
            "policy_hash",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"RecordReceiptRequest.{field_name} is required")
        valid_levels = {e.value for e in AuthorityLevel}
        if self.from_level is not None and self.from_level not in valid_levels:
            raise ValueError(
                f"Invalid from_level {self.from_level!r}; "
                f"must be one of {sorted(valid_levels)}"
            )
        if self.to_level is not None and self.to_level not in valid_levels:
            raise ValueError(
                f"Invalid to_level {self.to_level!r}; "
                f"must be one of {sorted(valid_levels)}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_kind": self.event_kind,
            "run_id": self.run_id,
            "agenda_id": self.agenda_id,
            "subject_hash": self.subject_hash,
            "evidence_hash": self.evidence_hash,
            "policy_hash": self.policy_hash,
        }
        if self.from_level is not None:
            d["from_level"] = self.from_level
        if self.to_level is not None:
            d["to_level"] = self.to_level
        if self.horizon is not None:
            d["horizon"] = self.horizon.to_dict()
        if self.unsettled:
            d["unsettled"] = [c.to_dict() for c in self.unsettled]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordReceiptRequest:
        horizon_data = data.get("horizon")
        horizon = (
            HorizonBlock.from_dict(horizon_data) if horizon_data else None
        )
        unsettled_raw = data.get("unsettled", ())
        unsettled = tuple(
            NonDischargeClaim.from_dict(c) for c in unsettled_raw
        )
        return cls(
            event_kind=data["event_kind"],
            run_id=data["run_id"],
            agenda_id=data["agenda_id"],
            subject_hash=data["subject_hash"],
            evidence_hash=data["evidence_hash"],
            policy_hash=data["policy_hash"],
            from_level=data.get("from_level"),
            to_level=data.get("to_level"),
            horizon=horizon,
            unsettled=unsettled,
        )


@dataclass(frozen=True)
class RecordReceiptResponse:
    receipt_id: str
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "receipt_hash": self.receipt_hash,
        }


@dataclass(frozen=True)
class EvidenceSummary:
    bundle_ref: str | None = None
    admissible_inputs: tuple[str, ...] = ()
    blocked_assumptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_ref": self.bundle_ref,
            "admissible_inputs": list(self.admissible_inputs),
            "blocked_assumptions": list(self.blocked_assumptions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceSummary:
        return cls(
            bundle_ref=data.get("bundle_ref"),
            admissible_inputs=tuple(data.get("admissible_inputs", ())),
            blocked_assumptions=tuple(data.get("blocked_assumptions", ())),
        )


@dataclass(frozen=True)
class AuthorizeTransitionRequest:
    run_id: str
    agenda_id: str
    from_level: str                           # AuthorityLevel value
    to_level: str                             # AuthorityLevel value
    evidence_summary: EvidenceSummary = field(default_factory=EvidenceSummary)

    def __post_init__(self) -> None:
        valid_levels = {e.value for e in AuthorityLevel}
        if self.from_level not in valid_levels:
            raise ValueError(
                f"Invalid from_level {self.from_level!r}; "
                f"must be one of {sorted(valid_levels)}"
            )
        if self.to_level not in valid_levels:
            raise ValueError(
                f"Invalid to_level {self.to_level!r}; "
                f"must be one of {sorted(valid_levels)}"
            )
        for field_name in ("run_id", "agenda_id"):
            if not getattr(self, field_name):
                raise ValueError(
                    f"AuthorizeTransitionRequest.{field_name} is required"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agenda_id": self.agenda_id,
            "from_level": self.from_level,
            "to_level": self.to_level,
            "evidence_summary": self.evidence_summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorizeTransitionRequest:
        return cls(
            run_id=data["run_id"],
            agenda_id=data["agenda_id"],
            from_level=data["from_level"],
            to_level=data["to_level"],
            evidence_summary=EvidenceSummary.from_dict(
                data.get("evidence_summary", {})
            ),
        )


@dataclass(frozen=True)
class AuthorizeTransitionResponse:
    verdict: str                         # NightShiftVerdict value
    reason: str
    required_approvals: tuple[str, ...]  # names of required approvals
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "required_approvals": list(self.required_approvals),
            "receipt_id": self.receipt_id,
        }


# =============================================================================
# Internal helpers
# =============================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _obligation_kinds(result_obligations: tuple[Any, ...]) -> tuple[str, ...]:
    """Pull the canonical obligation kind strings off a PolicyEvalResult."""
    return tuple(obligation.kind for obligation in result_obligations)


def _build_subject_capabilities(
    action_kind: str, tool_class: str
) -> tuple[str, ...]:
    """Derive the capability set a NS action implies.

    The action's tool_class determines which governor Capability values
    are in play. This mapping is conservative — a broader action implies
    the capabilities of the narrower ones below it in the ladder.
    """
    caps: list[str] = [Capability.MCP_CALL.value]
    if action_kind == ActionKind.MCP_CALL.value:
        caps.append(Capability.MCP_CALL.value)
    if tool_class in (
        ToolClass.MUTATE.value, ToolClass.STAGE.value,
        ToolClass.PUBLISH.value,
    ):
        caps.append(Capability.WRITE_FS.value)
    if tool_class == ToolClass.PUBLISH.value:
        caps.append(Capability.NETWORK_EGRESS.value)
    if tool_class == ToolClass.PAGE.value:
        caps.append(Capability.PAGE_HUMAN.value)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for cap in caps:
        if cap not in seen:
            seen.add(cap)
            deduped.append(cap)
    return tuple(deduped)


def _build_eval_request(
    request: CheckPolicyRequest, gate_name: str
) -> PolicyEvalRequest:
    """Translate a NS CheckPolicyRequest into a policy_engine request."""
    caps = _build_subject_capabilities(
        request.requested_action.kind,
        request.requested_action.tool_class,
    )
    subject = SubjectInfo(
        kind=SubjectKind.TOOL_CALL.value,
        subject_id=f"ns:{request.agenda_id}:{request.run_id}",
        action=request.requested_action.kind,
        capabilities=caps,
        tool_id=request.requested_action.tool_id,
        capability_vocab_version=CAPABILITY_VOCAB_VERSION,
    )
    context = ContextInfo(
        gate_name=gate_name,
        capability_vocab_version=CAPABILITY_VOCAB_VERSION,
        obligation_vocab_version=OBLIGATION_VOCAB_VERSION,
    )
    principals = PrincipalsInfo(actor_id=request.actor)
    return PolicyEvalRequest(
        subject=subject,
        context=context,
        principals=principals,
        request_id=f"ns-{request.agenda_id}-{request.run_id}-{_now_iso()}",
        created_at=_now_iso(),
    )


def _build_transition_eval_request(
    request: AuthorizeTransitionRequest,
) -> PolicyEvalRequest:
    """Translate a NS transition request into a policy_engine request.

    Transition requests carry authority-ladder movement as the primary
    capability; tool_class is implicit at this level.
    """
    caps = (Capability.NIGHTSHIFT_PROMOTE.value,)
    subject = SubjectInfo(
        kind=SubjectKind.GATE_EVENT.value,
        subject_id=f"ns:{request.agenda_id}:{request.run_id}",
        action=f"transition:{request.from_level}->{request.to_level}",
        capabilities=caps,
        capability_vocab_version=CAPABILITY_VOCAB_VERSION,
    )
    context = ContextInfo(
        gate_name="nightshift_transition",
        capability_vocab_version=CAPABILITY_VOCAB_VERSION,
        obligation_vocab_version=OBLIGATION_VOCAB_VERSION,
    )
    return PolicyEvalRequest(
        subject=subject,
        context=context,
        request_id=(
            f"ns-trans-{request.agenda_id}-{request.run_id}-"
            f"{request.from_level}->{request.to_level}"
        ),
        created_at=_now_iso(),
    )


def _default_downgrade_for(verdict: NightShiftVerdict) -> str | None:
    """When verdict=downgrade, what's the default level NS should drop to?

    NS contract implies `advise` as the safe baseline (§degraded-mode also
    uses advise as the ceiling). Policy may override by listing an
    obligation with a `downgrade_to` param — that's a v2 concern.
    """
    if verdict is NightShiftVerdict.DOWNGRADE:
        return AuthorityLevel.ADVISE.value
    return None


# =============================================================================
# Adapter surface
# =============================================================================


def check_policy(
    request: CheckPolicyRequest,
    policy_rule_set: PolicyRuleSet,
    receipt_system: GateReceiptSystem,
) -> CheckPolicyResponse:
    """NS asks Governor whether an action is allowed.

    Pure translation over ``policy_engine.evaluate`` with a companion
    gate receipt (role=measurement; the receipt records that NS asked
    and governor answered).
    """
    eval_request = _build_eval_request(request, gate_name="nightshift_policy")
    result = evaluate(eval_request, policy_rule_set)
    ns_verdict = translate_verdict(result.verdict)

    evidence_bundle = {
        "matched_rule_ids": [r.rule_id for r in result.matched_rules],
        "obligation_kinds": list(_obligation_kinds(result.obligations)),
        "policy_identity": result.policy_identity.to_dict(),
        "ns_request": request.to_dict(),
        "reason_codes": list(result.rationale.reason_codes),
    }
    receipt = receipt_system.emit(
        gate="nightshift_adapter",
        verdict=result.verdict.value,
        subject_kind="nightshift_check_policy",
        subject_bytes=(
            f"{request.agenda_id}:{request.run_id}:"
            f"{request.requested_action.arguments_hash}"
        ).encode("utf-8"),
        evidence_bundle=evidence_bundle,
        gate_config={
            "adapter_version": ADAPTER_VERSION,
            "authority_level": request.authority_level,
        },
        receipt_role=ROLE_MEASUREMENT,
    )

    return CheckPolicyResponse(
        verdict=ns_verdict.value,
        reason=result.rationale.summary or f"verdict={result.verdict.value}",
        obligations=_obligation_kinds(result.obligations),
        receipt_id=receipt.receipt_id,
        downgrade_to=_default_downgrade_for(ns_verdict),
    )


def record_receipt(
    event: RecordReceiptRequest,
    receipt_system: GateReceiptSystem,
) -> RecordReceiptResponse:
    """NS asks Governor to emit an authority receipt for a lifecycle event.

    The receipt_role is derived from event_kind by a closed mapping
    (authority vs measurement). Horizon is forwarded into the receipt
    when supplied — NS carries the tolerability declaration through.
    """
    role = _receipt_role_for_event(EventKind(event.event_kind))
    evidence_bundle = {
        "event_kind": event.event_kind,
        "run_id": event.run_id,
        "agenda_id": event.agenda_id,
        "ns_subject_hash": event.subject_hash,
        "ns_evidence_hash": event.evidence_hash,
        "ns_policy_hash": event.policy_hash,
    }
    if event.from_level is not None:
        evidence_bundle["from_level"] = event.from_level
    if event.to_level is not None:
        evidence_bundle["to_level"] = event.to_level

    receipt = receipt_system.emit(
        gate="nightshift_adapter",
        verdict="observe",  # lifecycle events are records, not verdicts
        subject_kind=f"nightshift_event:{event.event_kind}",
        subject_bytes=(
            f"{event.run_id}:{event.agenda_id}:{event.subject_hash}"
        ).encode("utf-8"),
        evidence_bundle=evidence_bundle,
        gate_config={
            "adapter_version": ADAPTER_VERSION,
            "event_kind": event.event_kind,
        },
        receipt_role=role,
        horizon=event.horizon,
        unsettled=event.unsettled,
    )
    return RecordReceiptResponse(
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_id,
    )


def authorize_transition(
    request: AuthorizeTransitionRequest,
    policy_rule_set: PolicyRuleSet,
    receipt_system: GateReceiptSystem,
) -> AuthorizeTransitionResponse:
    """NS asks Governor whether a run may move up the authority ladder.

    Delegates to policy_engine.evaluate with a transition-specific
    request shape, emits a role=authority receipt capturing the
    promotion attempt and its verdict.
    """
    eval_request = _build_transition_eval_request(request)
    result = evaluate(eval_request, policy_rule_set)
    ns_verdict = translate_verdict(result.verdict)

    required_approvals: list[str] = []
    for obligation in result.obligations:
        if obligation.kind == "require_human_approval":
            required_approvals.append("operator_approval")
        elif obligation.kind == "require_fresh_approval":
            required_approvals.append("fresh_reconciliation")

    evidence_bundle = {
        "matched_rule_ids": [r.rule_id for r in result.matched_rules],
        "obligation_kinds": list(_obligation_kinds(result.obligations)),
        "policy_identity": result.policy_identity.to_dict(),
        "ns_transition": request.to_dict(),
        "reason_codes": list(result.rationale.reason_codes),
    }
    receipt = receipt_system.emit(
        gate="nightshift_adapter",
        verdict=result.verdict.value,
        subject_kind="nightshift_authorize_transition",
        subject_bytes=(
            f"{request.agenda_id}:{request.run_id}:"
            f"{request.from_level}->{request.to_level}"
        ).encode("utf-8"),
        evidence_bundle=evidence_bundle,
        gate_config={
            "adapter_version": ADAPTER_VERSION,
            "from_level": request.from_level,
            "to_level": request.to_level,
        },
        receipt_role=ROLE_AUTHORITY,
    )

    return AuthorizeTransitionResponse(
        verdict=ns_verdict.value,
        reason=result.rationale.summary or f"verdict={result.verdict.value}",
        required_approvals=tuple(required_approvals),
        receipt_id=receipt.receipt_id,
    )
