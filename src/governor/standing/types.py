# SPDX-License-Identifier: Apache-2.0
"""Closed enums, dataclasses, and the violation vocabulary.

The vocabulary lands here before any check uses it so ``INVALID_STRUCTURAL``
never becomes a stringly-typed bucket with prose excuses hanging off it.
Every violation a check can raise has a code in :class:`ViolationCode`.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


# =============================================================================
# Constitutional anchors
# =============================================================================

# The four ratified Q1–Q4 decisions from
# ``docs/doctrine/decisions/``. The validator's bootstrap policy_declaration
# cites these by id; if any is missing from the loaded registry the
# validator refuses to run.
BOOTSTRAP_POLICY_ARTIFACT_IDS: tuple[str, ...] = (
    "decision.validator_integration.q1",
    "decision.validator_integration.q2",
    "decision.validator_integration.q3",
    "decision.validator_integration.q4",
)


# =============================================================================
# Closed enums (validator_contract §3, §4, §11)
# =============================================================================


class StandingClass(enum.Enum):
    """Closed standing-class lattice. No UNKNOWN/OTHER admitted."""

    OBSERVE = "OBSERVE"
    INTERPRET = "INTERPRET"
    RECOMMEND = "RECOMMEND"
    AUTHORIZE = "AUTHORIZE"
    EXECUTE = "EXECUTE"
    POLICY_DECLARE = "POLICY_DECLARE"


class ReceiptRole(enum.Enum):
    """Closed receipt role enum. ``validation`` is meta-governance."""

    OBSERVATION = "observation"
    INTERPRETATION = "interpretation"
    RECOMMENDATION = "recommendation"
    AUTHORIZATION = "authorization"
    ACTION = "action"
    POLICY_DECLARATION = "policy_declaration"
    VALIDATION = "validation"


# Default role → standing mapping (validator_contract §4).
ROLE_TO_STANDING: dict[ReceiptRole, StandingClass] = {
    ReceiptRole.OBSERVATION: StandingClass.OBSERVE,
    ReceiptRole.INTERPRETATION: StandingClass.INTERPRET,
    ReceiptRole.RECOMMENDATION: StandingClass.RECOMMEND,
    ReceiptRole.AUTHORIZATION: StandingClass.AUTHORIZE,
    ReceiptRole.ACTION: StandingClass.EXECUTE,
    ReceiptRole.POLICY_DECLARATION: StandingClass.POLICY_DECLARE,
    # validation has no canonical standing — it is meta-governance and
    # may not serve as a sole authority parent (§4, §5.1).
}


# Required immediate parent standing, by child role
# (validator_contract §5.1). ``None`` means parents are not required at
# this layer (observation, policy_declaration, validation are handled by
# their own rules).
ALLOWED_PARENT_STANDING: dict[ReceiptRole, frozenset[StandingClass] | None] = {
    ReceiptRole.OBSERVATION: None,
    ReceiptRole.INTERPRETATION: frozenset({StandingClass.OBSERVE}),
    ReceiptRole.RECOMMENDATION: frozenset({StandingClass.INTERPRET}),
    ReceiptRole.AUTHORIZATION: frozenset({StandingClass.RECOMMEND}),
    ReceiptRole.ACTION: frozenset({StandingClass.AUTHORIZE}),
    ReceiptRole.POLICY_DECLARATION: None,
    ReceiptRole.VALIDATION: None,
}


class SubjectDerivationKind(enum.Enum):
    """Closed enum per ratified Q2 (decision.validator_integration.q2).

    Additions require a ratified ``policy_declaration`` referencing the
    prior enum version as ``supersedes``. ``basis`` prose is not a
    substitute and does not unlock unrecognized kinds.
    """

    SAME_SUBJECT = "same_subject"
    INSTANCE_OF = "instance_of"
    AGGREGATION_OF = "aggregation_of"
    SCOPE_NARROWING = "scope_narrowing"


class ValidationOutcome(enum.Enum):
    """Validator outcomes per validator_contract §12 + ratified Q4."""

    VALID = "VALID"
    INVALID_STRUCTURAL = "INVALID_STRUCTURAL"
    INVALID_SEMANTIC = "INVALID_SEMANTIC"
    INVALID_CHAIN = "INVALID_CHAIN"
    VALID_WITH_EXCEPTION = "VALID_WITH_EXCEPTION"


class AuthorizationVerdict(enum.Enum):
    """Closed verdict enum (standing_and_receipts §11.3)."""

    PERMIT = "permit"
    DENY = "deny"
    ESCALATE = "escalate"
    REQUIRE_HUMAN = "require_human"


# =============================================================================
# Violation vocabulary
# =============================================================================


class ViolationClass(enum.Enum):
    """Three violation classes per validator_contract §11."""

    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    CHAIN = "chain"


class ViolationCode(enum.Enum):
    """Machine-facing violation vocabulary.

    Every check raises one of these. New codes are added; existing codes
    are never renamed or removed (same append-only discipline as
    instrumentation reason codes).
    """

    # Structural — validator_contract §5, §11.1
    UNKNOWN_RECEIPT_ROLE = "unknown_receipt_role"
    UNKNOWN_STANDING_CLASS = "unknown_standing_class"
    INVALID_ROLE_STANDING_MAPPING = "invalid_role_standing_mapping"
    MISSING_REQUIRED_PARENT = "missing_required_parent"
    PARENT_STANDING_NOT_ADMISSIBLE = "parent_standing_not_admissible"
    SUBJECT_DERIVATION_INVALID = "subject_derivation_invalid"
    SUBJECT_DERIVATION_KIND_UNKNOWN = "subject_derivation_kind_unknown"
    SUBJECT_LINEAGE_INCOHERENT = "subject_lineage_incoherent"
    EXCEPTION_CLASS_NOT_REGISTERED = "exception_class_not_registered"
    COMPRESSED_PATH_DIRECTION_NOT_ALLOWED = "compressed_path_direction_not_allowed"

    # Semantic — validator_contract §8, §11.2
    BINDING_RECEIPT_MISSING_POLICY_FIELDS = "binding_receipt_missing_policy_fields"
    POLICY_ARTIFACT_NOT_REGISTERED = "policy_artifact_not_registered"
    POLICY_ARTIFACT_HASH_MISMATCH = "policy_artifact_hash_mismatch"
    ONTOLOGY_VERSION_MISSING = "ontology_version_missing"
    ONTOLOGY_VERSION_NOT_REGISTERED = "ontology_version_not_registered"
    EXCEPTION_REQUIRED_EVIDENCE_MISSING = "exception_required_evidence_missing"

    # Chain — validator_contract §6, §11.3
    PARENT_REFERENCE_ID_ONLY = "parent_reference_id_only"
    PARENT_NOT_FOUND = "parent_not_found"
    PARENT_CONTENT_HASH_MISMATCH = "parent_content_hash_mismatch"
    PARENT_GRAPH_CYCLE = "parent_graph_cycle"


VIOLATION_CLASS_FOR_CODE: dict[ViolationCode, ViolationClass] = {
    # Structural
    ViolationCode.UNKNOWN_RECEIPT_ROLE: ViolationClass.STRUCTURAL,
    ViolationCode.UNKNOWN_STANDING_CLASS: ViolationClass.STRUCTURAL,
    ViolationCode.INVALID_ROLE_STANDING_MAPPING: ViolationClass.STRUCTURAL,
    ViolationCode.MISSING_REQUIRED_PARENT: ViolationClass.STRUCTURAL,
    ViolationCode.PARENT_STANDING_NOT_ADMISSIBLE: ViolationClass.STRUCTURAL,
    ViolationCode.SUBJECT_DERIVATION_INVALID: ViolationClass.STRUCTURAL,
    ViolationCode.SUBJECT_DERIVATION_KIND_UNKNOWN: ViolationClass.STRUCTURAL,
    ViolationCode.SUBJECT_LINEAGE_INCOHERENT: ViolationClass.STRUCTURAL,
    ViolationCode.EXCEPTION_CLASS_NOT_REGISTERED: ViolationClass.STRUCTURAL,
    ViolationCode.COMPRESSED_PATH_DIRECTION_NOT_ALLOWED: ViolationClass.STRUCTURAL,
    # Semantic
    ViolationCode.BINDING_RECEIPT_MISSING_POLICY_FIELDS: ViolationClass.SEMANTIC,
    ViolationCode.POLICY_ARTIFACT_NOT_REGISTERED: ViolationClass.SEMANTIC,
    ViolationCode.POLICY_ARTIFACT_HASH_MISMATCH: ViolationClass.SEMANTIC,
    ViolationCode.ONTOLOGY_VERSION_MISSING: ViolationClass.SEMANTIC,
    ViolationCode.ONTOLOGY_VERSION_NOT_REGISTERED: ViolationClass.SEMANTIC,
    ViolationCode.EXCEPTION_REQUIRED_EVIDENCE_MISSING: ViolationClass.SEMANTIC,
    # Chain
    ViolationCode.PARENT_REFERENCE_ID_ONLY: ViolationClass.CHAIN,
    ViolationCode.PARENT_NOT_FOUND: ViolationClass.CHAIN,
    ViolationCode.PARENT_CONTENT_HASH_MISMATCH: ViolationClass.CHAIN,
    ViolationCode.PARENT_GRAPH_CYCLE: ViolationClass.CHAIN,
}


@dataclass(frozen=True)
class Violation:
    """A single violation produced by a validator check."""

    code: ViolationCode
    message: str
    receipt_id: str | None = None
    pointers: tuple[str, ...] = ()

    @property
    def violation_class(self) -> ViolationClass:
        return VIOLATION_CLASS_FOR_CODE[self.code]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "class": self.violation_class.value,
            "message": self.message,
            "receipt_id": self.receipt_id,
            "pointers": list(self.pointers),
        }


# =============================================================================
# Receipt envelope (standing_and_receipts §6)
# =============================================================================


@dataclass(frozen=True)
class ParentRef:
    """Content-bound parent reference (validator_contract §6).

    ID-only references are rejected; both fields are required.
    """

    id: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "content_hash": self.content_hash}


@dataclass(frozen=True)
class SubjectDerivation:
    """Subject transformation under the closed Q2 enum.

    ``basis`` is descriptive only and is **not** a validator input
    (Q2 ratification: removing or changing ``basis`` post-hoc must not
    change the validator verdict).
    """

    kind: SubjectDerivationKind
    parent_id: str
    # For aggregation_of: the full set of parent ids being aggregated.
    aggregate_parent_ids: tuple[str, ...] = ()
    # For scope_narrowing: how containment is mechanically established.
    # Q2.A is deferred; "prefix" is supported as the first concrete check.
    containment_basis: str | None = None
    basis: str | None = None  # descriptive only — not a validator input

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "parent_id": self.parent_id,
            "aggregate_parent_ids": list(self.aggregate_parent_ids),
            "containment_basis": self.containment_basis,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class StandingReceipt:
    """A standing-class receipt envelope.

    The canonical body for hashing is everything except ``content_hash``
    and the optional ``display_metadata`` field. ``display_metadata`` is
    operator-facing UI only and per Q1 acceptance #4 must not change the
    receipt hash when edited.
    """

    receipt_id: str
    receipt_role: ReceiptRole
    standing_class: StandingClass
    subject: str
    ontology_version: str
    producer: str
    created_at: str
    parent_receipts: tuple[ParentRef, ...] = ()
    subject_derivation: SubjectDerivation | None = None
    # For compressed-path authorizations only:
    exception_class: str | None = None
    exception_reason: str | None = None
    operator_approval_ref: ParentRef | None = None
    compression_acknowledged: bool = False
    # Authorization binding fields:
    policy_artifact_id: str | None = None
    policy_artifact_hash: str | None = None
    verdict: AuthorizationVerdict | None = None
    # Free-form payload (role-specific extras kept here so envelope shape
    # stays stable; schema hardening is downstream of this commit).
    payload: dict[str, Any] = field(default_factory=dict)
    # Operator-facing only; not part of canonical body.
    display_metadata: dict[str, Any] = field(default_factory=dict)
    # Carried forward, not validated yet (gap survival is follow-on work):
    gaps: tuple[dict[str, Any], ...] = ()
    gaps_resolved: tuple[dict[str, Any], ...] = ()
    # Optional caller-provided content hash; the validator recomputes and
    # checks parent hashes against the canonical body of the parent.
    content_hash: str | None = None

    def canonical_body(self) -> dict[str, Any]:
        """Return the dict that hashes to ``content_hash``.

        Excludes ``content_hash`` itself and ``display_metadata``
        (Q1 acceptance #4: display metadata cannot change the hash).
        """

        body = asdict(self)
        body.pop("content_hash", None)
        body.pop("display_metadata", None)
        # Normalize enum values so canonical_json sees strings.
        body["receipt_role"] = self.receipt_role.value
        body["standing_class"] = self.standing_class.value
        if self.subject_derivation is not None:
            body["subject_derivation"]["kind"] = self.subject_derivation.kind.value
        if self.verdict is not None:
            body["verdict"] = self.verdict.value
        return body

    def compute_content_hash(self) -> str:
        return content_hash(self.canonical_body())


# =============================================================================
# Validation receipt (Q4 mandatory fields)
# =============================================================================


@dataclass(frozen=True)
class ValidationReceipt:
    """Per-target validation result.

    Carries every Q4 mandatory field. Missing any field makes the
    receipt itself invalid and downstream consumers must reject it.
    """

    validator_id: str
    validator_version: str
    ruleset_hash: str
    policy_registry_hash: str
    validated_at: str
    target_receipts: tuple[ParentRef, ...]
    outcome: ValidationOutcome
    violations: tuple[Violation, ...] = ()
    exceptions: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_id": self.validator_id,
            "validator_version": self.validator_version,
            "ruleset_hash": self.ruleset_hash,
            "policy_registry_hash": self.policy_registry_hash,
            "validated_at": self.validated_at,
            "target_receipts": [p.to_dict() for p in self.target_receipts],
            "outcome": self.outcome.value,
            "violations": [v.to_dict() for v in self.violations],
            "exceptions": list(self.exceptions),
        }


# =============================================================================
# Canonical JSON + content hash
# =============================================================================
#
# Same canonicalization parameters as receipt_kernel.envelope.canonical_json
# so a future Q1.A ratification picking "new event types" can carry these
# bodies forward without rehashing.


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(obj: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(obj)).hexdigest()}"
