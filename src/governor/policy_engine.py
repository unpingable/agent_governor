# SPDX-License-Identifier: Apache-2.0
"""
Policy Engine: abstract policy evaluation substrate for governor gates.

Every gate currently has inline decision logic. This module provides a shared
vocabulary (capabilities, obligations, verdicts) and a pure evaluator that
new gates (chain gate, egress gate, etc.) build on top of.

Design:
- Pure evaluator: evaluate(request, rules) → result, no side effects
- Deny-first with deterministic precedence: BLOCK > ESCALATE > WARN > PASS
- Structured request/result models (nullable v2 fields baked in now)
- "Allow with obligations" = PASS + obligations != [] (no separate verdict)
- ALL-of + ANY-of capability matching for composition detection
- Default policy = deny all, no magic exceptions

Companion specs: GOV_SPEC_POLICY_001, GOV_SPEC_CAP_001, GOV_SPEC_OBL_001.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Version Constants
# =============================================================================

POLICY_EVAL_REQUEST_SCHEMA = "governor/policy_eval_request/v1"
POLICY_EVAL_RESULT_SCHEMA = "governor/policy_eval_result/v1"
CAPABILITY_VOCAB_VERSION = "cap-v1"
OBLIGATION_VOCAB_VERSION = "obl-v1"
POLICY_ENGINE_VERSION = "1.0.0"


# =============================================================================
# Canonical JSON (local copy — same algorithm as gate_receipt.py)
# =============================================================================

def _canonical_json(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON for hashing. Same spec as gate_receipt.canonical_json."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# Enums — PolicyVerdict
# =============================================================================

class PolicyVerdict(str, Enum):
    """Evaluation outcome. Precedence: BLOCK > ESCALATE > WARN > PASS."""
    PASS = "pass"
    BLOCK = "block"
    ESCALATE = "escalate"
    WARN = "warn"


# Deterministic precedence order (highest first)
_VERDICT_PRECEDENCE: dict[PolicyVerdict, int] = {
    PolicyVerdict.BLOCK: 3,
    PolicyVerdict.ESCALATE: 2,
    PolicyVerdict.WARN: 1,
    PolicyVerdict.PASS: 0,
}


# =============================================================================
# Enums — Capability Taxonomy (GOV_SPEC_CAP_001)
# =============================================================================

class Capability(str, Enum):
    # Filesystem
    READ_FS = "read_fs"
    WRITE_FS = "write_fs"
    DELETE_FS = "delete_fs"
    # Process
    EXEC = "exec"
    EXEC_PRIVILEGED = "exec_privileged"
    TOOL_INSTALL = "tool_install"
    # Network
    NETWORK_EGRESS = "network_egress"
    NETWORK_INGRESS = "network_ingress"
    # Repo / SCM
    REPO_READ = "repo_read"
    REPO_WRITE = "repo_write"
    # Messaging
    MESSAGE_READ = "message_read"
    MESSAGE_SEND = "message_send"
    # Secrets
    SECRET_READ = "secret_read"
    SECRET_WRITE = "secret_write"
    # Config
    CONFIG_READ = "config_read"
    CONFIG_WRITE = "config_write"
    # Transform / orchestration
    TRANSFORM = "transform"
    POLICY_OVERRIDE = "policy_override"
    APPROVAL_CONSUME = "approval_consume"
    HANDOFF_REMOTE = "handoff_remote"
    # Night Shift adapter (GOV_GAP_NIGHTSHIFT_ADAPTER_001) — declared here
    # so strict_taxonomy accepts them; scoped semantics live adapter-side.
    MCP_CALL = "mcp_call"
    NIGHTSHIFT_PROMOTE = "nightshift_promote"
    PAGE_HUMAN = "page_human"
    # Fallback
    UNKNOWN = "unknown"


_VALID_CAPABILITIES = frozenset(c.value for c in Capability)


# =============================================================================
# Enums — Obligation Vocabulary (GOV_SPEC_OBL_001)
# =============================================================================

class ObligationKind(str, Enum):
    # Approval / escalation
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    FORCE_REMOTE = "force_remote"
    REQUIRE_ESCALATION_BUNDLE = "require_escalation_bundle"
    # Verification / evidence
    REQUIRE_EVIDENCE = "require_evidence"
    REQUIRE_ORACLE = "require_oracle"
    REQUIRE_REVALIDATION = "require_revalidation"
    # Data handling / egress
    REDACT_PAYLOAD = "redact_payload"
    RESTRICT_DESTINATION = "restrict_destination"
    REQUIRE_PAYLOAD_CLASSIFICATION = "require_payload_classification"
    # Observability
    LOG_HIGH_PRIORITY = "log_high_priority"
    EMIT_RECEIPT_ONLY = "emit_receipt_only"
    # Time / rate
    REQUIRE_FRESH_APPROVAL = "require_fresh_approval"
    COOLDOWN = "cooldown"
    # Safety
    DENY_IF_UNKNOWN = "deny_if_unknown"


# =============================================================================
# Enums — Supporting
# =============================================================================

class SubjectKind(str, Enum):
    TOOL_CALL = "tool_call"
    ACTION_CHAIN = "action_chain"
    EGRESS_ATTEMPT = "egress_attempt"
    DETECTOR_DECISION = "detector_decision"
    GATE_EVENT = "gate_event"


class PayloadClass(str, Enum):
    UNCLASSIFIED = "unclassified"
    REPO_SOURCE = "repo_source"
    SECRET_CANDIDATE = "secret_candidate"
    PII_CANDIDATE = "pii_candidate"
    CREDENTIAL_LIKE = "credential_like"
    UNKNOWN = "unknown"


class DestinationClass(str, Enum):
    EMAIL = "email"
    HTTP = "http"
    WEBHOOK = "webhook"
    SLACK = "slack"
    FILE = "file"
    UNKNOWN = "unknown"


class EnforcementStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    SKIPPED = "skipped"


class TrustMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


# =============================================================================
# Request Model
# =============================================================================

@dataclass(frozen=True)
class SubjectInfo:
    kind: str   # SubjectKind value
    subject_id: str
    action: str
    capabilities: tuple[str, ...] = ()
    tool_id: str | None = None
    tool_manifest_hash: str | None = None
    capability_vocab_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject_id": self.subject_id,
            "action": self.action,
            "capabilities": list(self.capabilities),
            "tool_id": self.tool_id,
            "tool_manifest_hash": self.tool_manifest_hash,
            "capability_vocab_version": self.capability_vocab_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubjectInfo:
        return cls(
            kind=data["kind"],
            subject_id=data["subject_id"],
            action=data["action"],
            capabilities=tuple(data.get("capabilities", ())),
            tool_id=data.get("tool_id"),
            tool_manifest_hash=data.get("tool_manifest_hash"),
            capability_vocab_version=data.get("capability_vocab_version"),
        )


@dataclass(frozen=True)
class PrincipalsInfo:
    actor_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrincipalsInfo:
        return cls(
            actor_id=data.get("actor_id"),
            agent_id=data.get("agent_id"),
            session_id=data.get("session_id"),
        )


@dataclass(frozen=True)
class ContextInfo:
    gate_name: str
    trust_mode: str = "local"
    task_id: str | None = None
    task_class: str | None = None
    lane: str | None = None
    request_nonce: str | None = None
    capability_vocab_version: str = CAPABILITY_VOCAB_VERSION
    obligation_vocab_version: str = OBLIGATION_VOCAB_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "trust_mode": self.trust_mode,
            "task_id": self.task_id,
            "task_class": self.task_class,
            "lane": self.lane,
            "request_nonce": self.request_nonce,
            "capability_vocab_version": self.capability_vocab_version,
            "obligation_vocab_version": self.obligation_vocab_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextInfo:
        return cls(
            gate_name=data["gate_name"],
            trust_mode=data.get("trust_mode", "local"),
            task_id=data.get("task_id"),
            task_class=data.get("task_class"),
            lane=data.get("lane"),
            request_nonce=data.get("request_nonce"),
            capability_vocab_version=data.get(
                "capability_vocab_version", CAPABILITY_VOCAB_VERSION,
            ),
            obligation_vocab_version=data.get(
                "obligation_vocab_version", OBLIGATION_VOCAB_VERSION,
            ),
        )


@dataclass(frozen=True)
class ProvenanceInfo:
    labels: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "refs": list(self.refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceInfo:
        return cls(
            labels=tuple(data.get("labels", ())),
            refs=tuple(data.get("refs", ())),
        )


@dataclass(frozen=True)
class DestinationInfo:
    destination_class: str = "unknown"
    identity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_class": self.destination_class,
            "identity": self.identity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DestinationInfo:
        return cls(
            destination_class=data.get("destination_class", "unknown"),
            identity=data.get("identity"),
        )


@dataclass(frozen=True)
class PayloadInfo:
    payload_hash: str | None = None
    payload_class: str | None = None
    destination: DestinationInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload_hash": self.payload_hash,
            "payload_class": self.payload_class,
            "destination": self.destination.to_dict() if self.destination else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PayloadInfo:
        dest = data.get("destination")
        return cls(
            payload_hash=data.get("payload_hash"),
            payload_class=data.get("payload_class"),
            destination=DestinationInfo.from_dict(dest) if dest else None,
        )


@dataclass(frozen=True)
class AttributesInfo:
    sensitivity: str | None = None
    is_composed: bool | None = None
    chain_length: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensitivity": self.sensitivity,
            "is_composed": self.is_composed,
            "chain_length": self.chain_length,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttributesInfo:
        return cls(
            sensitivity=data.get("sensitivity"),
            is_composed=data.get("is_composed"),
            chain_length=data.get("chain_length"),
            extra=dict(data.get("extra", {})),
        )


@dataclass(frozen=True)
class PolicyEvalRequest:
    """Structured request for policy evaluation."""
    subject: SubjectInfo
    context: ContextInfo
    schema: str = POLICY_EVAL_REQUEST_SCHEMA
    request_id: str = ""
    created_at: str = ""
    principals: PrincipalsInfo = field(default_factory=PrincipalsInfo)
    provenance: ProvenanceInfo = field(default_factory=ProvenanceInfo)
    payload: PayloadInfo | None = None
    attributes: AttributesInfo = field(default_factory=AttributesInfo)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "subject": self.subject.to_dict(),
            "principals": self.principals.to_dict(),
            "context": self.context.to_dict(),
            "provenance": self.provenance.to_dict(),
            "payload": self.payload.to_dict() if self.payload else None,
            "attributes": self.attributes.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyEvalRequest:
        payload = data.get("payload")
        return cls(
            schema=data.get("schema", POLICY_EVAL_REQUEST_SCHEMA),
            request_id=data.get("request_id", ""),
            created_at=data.get("created_at", ""),
            subject=SubjectInfo.from_dict(data["subject"]),
            principals=PrincipalsInfo.from_dict(data.get("principals", {})),
            context=ContextInfo.from_dict(data["context"]),
            provenance=ProvenanceInfo.from_dict(data.get("provenance", {})),
            payload=PayloadInfo.from_dict(payload) if payload else None,
            attributes=AttributesInfo.from_dict(data.get("attributes", {})),
        )


def request_content_hash(request: PolicyEvalRequest) -> str:
    """Content-addressed hash of a policy eval request for receipt binding."""
    return _content_hash(_canonical_json(request.to_dict()))


# =============================================================================
# Result Model
# =============================================================================

@dataclass(frozen=True)
class Obligation:
    kind: str   # ObligationKind value
    params: dict[str, Any] = field(default_factory=dict)
    obligation_id: str = ""
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "params": dict(self.params),
            "obligation_id": self.obligation_id,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Obligation:
        return cls(
            kind=data["kind"],
            params=dict(data.get("params", {})),
            obligation_id=data.get("obligation_id", ""),
            priority=data.get("priority", 0),
        )


@dataclass(frozen=True)
class MatchedRule:
    rule_id: str
    effect: str   # PolicyVerdict value
    priority: int = 0
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "effect": self.effect,
            "priority": self.priority,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchedRule:
        return cls(
            rule_id=data["rule_id"],
            effect=data["effect"],
            priority=data.get("priority", 0),
            reason_code=data.get("reason_code", ""),
        )


@dataclass(frozen=True)
class RationaleInfo:
    summary: str = ""
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RationaleInfo:
        return cls(
            summary=data.get("summary", ""),
            reason_codes=tuple(data.get("reason_codes", ())),
        )


@dataclass(frozen=True)
class PolicyIdentity:
    policy_engine_version: str = ""
    policy_bundle_id: str = ""
    policy_bundle_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_engine_version": self.policy_engine_version,
            "policy_bundle_id": self.policy_bundle_id,
            "policy_bundle_version": self.policy_bundle_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyIdentity:
        return cls(
            policy_engine_version=data.get("policy_engine_version", ""),
            policy_bundle_id=data.get("policy_bundle_id", ""),
            policy_bundle_version=data.get("policy_bundle_version", ""),
        )


@dataclass(frozen=True)
class PolicyEvalResult:
    """Outcome of policy evaluation."""
    schema: str = POLICY_EVAL_RESULT_SCHEMA
    request_id: str = ""
    evaluated_at: str = ""
    verdict: PolicyVerdict = PolicyVerdict.BLOCK
    matched_rules: tuple[MatchedRule, ...] = ()
    obligations: tuple[Obligation, ...] = ()
    rationale: RationaleInfo = field(default_factory=RationaleInfo)
    policy_identity: PolicyIdentity = field(default_factory=PolicyIdentity)

    @property
    def allowed(self) -> bool:
        return self.verdict in (PolicyVerdict.PASS, PolicyVerdict.WARN)

    @property
    def has_obligations(self) -> bool:
        return len(self.obligations) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "evaluated_at": self.evaluated_at,
            "verdict": self.verdict.value,
            "matched_rules": [r.to_dict() for r in self.matched_rules],
            "obligations": [o.to_dict() for o in self.obligations],
            "rationale": self.rationale.to_dict(),
            "policy_identity": self.policy_identity.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyEvalResult:
        return cls(
            schema=data.get("schema", POLICY_EVAL_RESULT_SCHEMA),
            request_id=data.get("request_id", ""),
            evaluated_at=data.get("evaluated_at", ""),
            verdict=PolicyVerdict(data.get("verdict", "block")),
            matched_rules=tuple(
                MatchedRule.from_dict(r) for r in data.get("matched_rules", ())
            ),
            obligations=tuple(
                Obligation.from_dict(o) for o in data.get("obligations", ())
            ),
            rationale=RationaleInfo.from_dict(data.get("rationale", {})),
            policy_identity=PolicyIdentity.from_dict(
                data.get("policy_identity", {}),
            ),
        )


# =============================================================================
# Gate Receipt Helpers (structured embedding for gates that adopt policy engine)
# =============================================================================

@dataclass(frozen=True)
class ObligationEnforcementRecord:
    """Post-eval record of whether an obligation was satisfied."""
    kind: str   # ObligationKind value
    enforcement_status: str   # EnforcementStatus value
    params: dict[str, Any] = field(default_factory=dict)
    evidence_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "enforcement_status": self.enforcement_status,
            "params": dict(self.params),
            "evidence_ref": self.evidence_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObligationEnforcementRecord:
        return cls(
            kind=data["kind"],
            enforcement_status=data["enforcement_status"],
            params=dict(data.get("params", {})),
            evidence_ref=data.get("evidence_ref"),
        )


@dataclass(frozen=True)
class PolicyReceiptFragment:
    """Canonical policy fragment embedded in gate receipts.

    Contract (frozen shape — composition gate and all future gates consume this):

        policy_verdict    : PolicyVerdict value string ("block"/"pass"/"warn"/…)
        matched_rule_ids  : Rule IDs that matched (IDs only, not full objects)
        obligation_kinds  : ObligationKind value strings (kinds only, not objects)
        policy_identity   : {policy_engine_version, policy_bundle_id, policy_bundle_version}
        applied           : Whether the verdict was applied to the gate result
        reason            : Explanation for noop/fail-open (None when applied)
        duration_ms       : Policy evaluation latency in milliseconds

    Gates may annotate the receipt with gate-specific fields (e.g. inline_status)
    alongside this fragment, but the fragment itself uses this shape only.
    """
    policy_verdict: str   # PolicyVerdict value
    matched_rule_ids: tuple[str, ...] = ()
    obligation_kinds: tuple[str, ...] = ()
    policy_identity: PolicyIdentity = field(default_factory=PolicyIdentity)
    applied: bool = True
    reason: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "policy_verdict": self.policy_verdict,
            "matched_rule_ids": list(self.matched_rule_ids),
            "obligation_kinds": list(self.obligation_kinds),
            "policy_identity": self.policy_identity.to_dict(),
            "applied": self.applied,
            "duration_ms": self.duration_ms,
        }
        if self.reason is not None:
            d["reason"] = self.reason
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyReceiptFragment:
        return cls(
            policy_verdict=data["policy_verdict"],
            matched_rule_ids=tuple(data.get("matched_rule_ids", ())),
            obligation_kinds=tuple(data.get("obligation_kinds", ())),
            policy_identity=PolicyIdentity.from_dict(
                data.get("policy_identity", {}),
            ),
            applied=data.get("applied", True),
            reason=data.get("reason"),
            duration_ms=data.get("duration_ms", 0.0),
        )


# =============================================================================
# Rule Model
# =============================================================================

@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule with match conditions and an effect."""
    rule_id: str
    description: str = ""
    priority: int = 0

    # Match conditions — ALL non-empty fields must match (AND semantics)
    match_capabilities_any: frozenset[str] = frozenset()
    match_capabilities_all: frozenset[str] = frozenset()
    match_action_types: frozenset[str] = frozenset()
    match_subject_kinds: frozenset[str] = frozenset()
    match_modes: frozenset[str] = frozenset()
    match_regimes: frozenset[str] = frozenset()
    match_principal_ids: frozenset[str] = frozenset()
    match_provenance: frozenset[str] = frozenset()
    match_payload_classes: frozenset[str] = frozenset()
    match_destination_classes: frozenset[str] = frozenset()
    match_target_pattern: str | None = None

    # Effect
    effect: str = "block"   # PolicyVerdict value
    obligations: tuple[Obligation, ...] = ()
    reason_code: str = ""
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "priority": self.priority,
            "match_capabilities_any": sorted(self.match_capabilities_any),
            "match_capabilities_all": sorted(self.match_capabilities_all),
            "match_action_types": sorted(self.match_action_types),
            "match_subject_kinds": sorted(self.match_subject_kinds),
            "match_modes": sorted(self.match_modes),
            "match_regimes": sorted(self.match_regimes),
            "match_principal_ids": sorted(self.match_principal_ids),
            "match_provenance": sorted(self.match_provenance),
            "match_payload_classes": sorted(self.match_payload_classes),
            "match_destination_classes": sorted(self.match_destination_classes),
            "match_target_pattern": self.match_target_pattern,
            "effect": self.effect,
            "obligations": [o.to_dict() for o in self.obligations],
            "reason_code": self.reason_code,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyRule:
        return cls(
            rule_id=data["rule_id"],
            description=data.get("description", ""),
            priority=data.get("priority", 0),
            match_capabilities_any=frozenset(
                data.get("match_capabilities_any", ()),
            ),
            match_capabilities_all=frozenset(
                data.get("match_capabilities_all", ()),
            ),
            match_action_types=frozenset(data.get("match_action_types", ())),
            match_subject_kinds=frozenset(data.get("match_subject_kinds", ())),
            match_modes=frozenset(data.get("match_modes", ())),
            match_regimes=frozenset(data.get("match_regimes", ())),
            match_principal_ids=frozenset(
                data.get("match_principal_ids", ()),
            ),
            match_provenance=frozenset(data.get("match_provenance", ())),
            match_payload_classes=frozenset(
                data.get("match_payload_classes", ()),
            ),
            match_destination_classes=frozenset(
                data.get("match_destination_classes", ()),
            ),
            match_target_pattern=data.get("match_target_pattern"),
            effect=data.get("effect", "block"),
            obligations=tuple(
                Obligation.from_dict(o)
                for o in data.get("obligations", ())
            ),
            reason_code=data.get("reason_code", ""),
            explanation=data.get("explanation", ""),
        )


@dataclass(frozen=True)
class PolicyRuleSet:
    """A collection of policy rules with metadata."""
    policy_bundle_id: str
    policy_bundle_version: str
    rules: tuple[PolicyRule, ...] = ()
    default_verdict: str = "block"   # PolicyVerdict value
    description: str = ""
    capability_vocab_version: str = CAPABILITY_VOCAB_VERSION
    obligation_vocab_version: str = OBLIGATION_VOCAB_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_bundle_id": self.policy_bundle_id,
            "policy_bundle_version": self.policy_bundle_version,
            "rules": [r.to_dict() for r in self.rules],
            "default_verdict": self.default_verdict,
            "description": self.description,
            "capability_vocab_version": self.capability_vocab_version,
            "obligation_vocab_version": self.obligation_vocab_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyRuleSet:
        return cls(
            policy_bundle_id=data["policy_bundle_id"],
            policy_bundle_version=data["policy_bundle_version"],
            rules=tuple(
                PolicyRule.from_dict(r) for r in data.get("rules", ())
            ),
            default_verdict=data.get("default_verdict", "block"),
            description=data.get("description", ""),
            capability_vocab_version=data.get(
                "capability_vocab_version", CAPABILITY_VOCAB_VERSION,
            ),
            obligation_vocab_version=data.get(
                "obligation_vocab_version", OBLIGATION_VOCAB_VERSION,
            ),
        )


# =============================================================================
# Evaluator (pure function)
# =============================================================================

def _rule_matches(rule: PolicyRule, request: PolicyEvalRequest) -> bool:
    """Check if all non-empty match conditions are satisfied (AND across fields)."""
    caps = set(request.subject.capabilities)

    # ANY-of capability match
    if rule.match_capabilities_any and not (caps & rule.match_capabilities_any):
        return False

    # ALL-of capability match (composition detection)
    if rule.match_capabilities_all and not (
        rule.match_capabilities_all <= caps
    ):
        return False

    # Action types
    if rule.match_action_types and request.subject.action not in rule.match_action_types:
        return False

    # Subject kinds
    if rule.match_subject_kinds and request.subject.kind not in rule.match_subject_kinds:
        return False

    # Trust mode
    if rule.match_modes and request.context.trust_mode not in rule.match_modes:
        return False

    # Regimes — sourced from attributes.extra["regime"], NOT a first-class
    # ContextInfo field.  Regime is a governor-internal concept; keeping it in
    # the flex bucket avoids premature schema canonization.
    if rule.match_regimes:
        regime = request.attributes.extra.get("regime", "")
        if regime not in rule.match_regimes:
            return False

    # Principal IDs
    if rule.match_principal_ids:
        principals = {
            request.principals.actor_id,
            request.principals.agent_id,
        }
        principals.discard(None)
        if not (principals & rule.match_principal_ids):
            return False

    # Provenance labels
    if rule.match_provenance:
        if not (set(request.provenance.labels) & rule.match_provenance):
            return False

    # Payload classes
    if rule.match_payload_classes:
        pc = request.payload.payload_class if request.payload else None
        if pc not in rule.match_payload_classes:
            return False

    # Destination classes
    if rule.match_destination_classes:
        dest = (
            request.payload.destination.destination_class
            if request.payload and request.payload.destination
            else None
        )
        if dest not in rule.match_destination_classes:
            return False

    # Target pattern (regex on subject_id)
    if rule.match_target_pattern is not None:
        try:
            if not re.search(rule.match_target_pattern, request.subject.subject_id):
                return False
        except re.error:
            # Invalid regex — treated as non-match, caller gets error via
            # the taxonomy check path (separate from match).
            return False

    return True


def evaluate(
    request: PolicyEvalRequest,
    policy: PolicyRuleSet,
    *,
    strict_taxonomy: bool = True,
) -> PolicyEvalResult:
    """Pure policy evaluation. No side effects. Deterministic.

    Args:
        request: Structured evaluation request.
        policy: Rule set to evaluate against.
        strict_taxonomy: If True, unknown capabilities cause immediate BLOCK.

    Returns:
        PolicyEvalResult with verdict, matched rules, obligations, rationale.
    """
    matched: list[MatchedRule] = []
    reason_codes: list[str] = []

    # --- Strict taxonomy check ---
    # Enum-ish strings (effect, kind, etc.) are tolerated at parse/from_dict
    # time for forward-compat: a newer policy bundle may introduce values that
    # an older evaluator doesn't know.  Validation happens HERE at eval time,
    # where the evaluator can produce a proper BLOCK + reason.  Don't "fix"
    # this by adding ValueError in from_dict — that breaks rolling upgrades.
    if strict_taxonomy:
        unknown = set(request.subject.capabilities) - _VALID_CAPABILITIES
        if unknown:
            rc = "unknown_capability"
            reason_codes.append(rc)
            matched.append(MatchedRule(
                rule_id="__taxonomy_check",
                effect=PolicyVerdict.BLOCK.value,
                priority=999,
                reason_code=rc,
            ))
            return PolicyEvalResult(
                request_id=request.request_id,
                verdict=PolicyVerdict.BLOCK,
                matched_rules=tuple(matched),
                rationale=RationaleInfo(
                    summary=f"Unknown capabilities: {sorted(unknown)}",
                    reason_codes=tuple(reason_codes),
                ),
                policy_identity=PolicyIdentity(
                    policy_engine_version=POLICY_ENGINE_VERSION,
                    policy_bundle_id=policy.policy_bundle_id,
                    policy_bundle_version=policy.policy_bundle_version,
                ),
            )

    # --- Partition rules by verdict class ---
    partitions: dict[int, list[PolicyRule]] = {3: [], 2: [], 1: [], 0: []}
    for rule in policy.rules:
        try:
            v = PolicyVerdict(rule.effect)
        except ValueError:
            continue  # skip invalid effect values
        prec = _VERDICT_PRECEDENCE[v]
        partitions[prec].append(rule)

    # Sort each partition by priority (highest first)
    for prec in partitions:
        partitions[prec].sort(key=lambda r: r.priority, reverse=True)

    # --- Evaluate in precedence order ---
    winning_rule: PolicyRule | None = None
    for prec in (3, 2, 1, 0):
        for rule in partitions[prec]:
            if _rule_matches(rule, request):
                winning_rule = rule
                break
        if winning_rule is not None:
            break

    # --- Build result ---
    if winning_rule is not None:
        verdict = PolicyVerdict(winning_rule.effect)
        matched.append(MatchedRule(
            rule_id=winning_rule.rule_id,
            effect=winning_rule.effect,
            priority=winning_rule.priority,
            reason_code=winning_rule.reason_code,
        ))
        if winning_rule.reason_code:
            reason_codes.append(winning_rule.reason_code)
        obligations = winning_rule.obligations
        summary = winning_rule.explanation or winning_rule.description
    else:
        verdict = PolicyVerdict(policy.default_verdict)
        obligations = ()
        summary = "No matching rule; applied default verdict."
        reason_codes.append("default_verdict")

    return PolicyEvalResult(
        request_id=request.request_id,
        verdict=verdict,
        matched_rules=tuple(matched),
        obligations=obligations,
        rationale=RationaleInfo(
            summary=summary,
            reason_codes=tuple(reason_codes),
        ),
        policy_identity=PolicyIdentity(
            policy_engine_version=POLICY_ENGINE_VERSION,
            policy_bundle_id=policy.policy_bundle_id,
            policy_bundle_version=policy.policy_bundle_version,
        ),
    )


# =============================================================================
# Built-in default policy
# =============================================================================

def default_policy() -> PolicyRuleSet:
    """Deny-all default policy. No exceptions."""
    return PolicyRuleSet(
        policy_bundle_id="governor.default",
        policy_bundle_version="1.0.0",
        default_verdict="block",
        description="Default deny-all policy. No rules, no exceptions.",
    )


# =============================================================================
# Persistence
# =============================================================================

def save_policy(policy: PolicyRuleSet, path: Path) -> None:
    """Save policy rule set to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json(policy.to_dict())
    path.write_bytes(data)


def load_policy(path: Path) -> PolicyRuleSet:
    """Load policy rule set from JSON file."""
    data = json.loads(path.read_bytes())
    return PolicyRuleSet.from_dict(data)
