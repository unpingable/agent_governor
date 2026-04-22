# SPDX-License-Identifier: Apache-2.0
"""Closed enums, dataclasses, and the violation vocabulary.

The vocabulary lands here before any check uses it so ``INVALID_STRUCTURAL``
never becomes a stringly-typed bucket with prose excuses hanging off it.
Every violation a check can raise has a code in :class:`ViolationCode`.
"""

from __future__ import annotations

import enum
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from receipt_kernel.envelope import canonical_json, compute_hash


# Canonical content-hash format. Same prefix + length as receipt_kernel.
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_valid_content_hash(value: object) -> bool:
    """Strict content-hash format check. No best-effort normalization."""

    return isinstance(value, str) and bool(HASH_PATTERN.fullmatch(value))


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


class CheckResultStatus(enum.Enum):
    """Closed status enum for structured check results (validator_contract §9)."""

    PASS = "pass"
    FAIL = "fail"
    ESCALATE = "escalate"


# AUTHORIZE receipts must carry these four structured checks
# (standing_and_receipts §7.4 + validator_contract §9). ID-only or
# boolean-only check fields are insufficient.
AUTHORIZE_REQUIRED_CHECKS: frozenset[str] = frozenset(
    {
        "standing_check",
        "admissibility_check",
        "scope_check",
        "budget_check",
    }
)


# Roles permitted to carry a ``continuity_basis`` block (C5).
# Per validator_contract §10 + standing_and_receipts §7.3:
# continuity preservation is claimed by recommendation (proposing
# continuity-affecting work), authorization (binding it), and action
# (executing it). Other roles (observation, interpretation,
# policy_declaration, validation) cannot claim continuity preservation
# at this layer.
CONTINUITY_CLAIMABLE_ROLES: frozenset[ReceiptRole] = frozenset(
    {
        ReceiptRole.RECOMMENDATION,
        ReceiptRole.AUTHORIZATION,
        ReceiptRole.ACTION,
    }
)


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
    HASH_FORMAT_INVALID = "hash_format_invalid"

    # Schema — closed envelope, structured checks (C3)
    UNKNOWN_FIELD_IN_ENVELOPE = "unknown_field_in_envelope"
    MISSING_REQUIRED_COMMON_FIELD = "missing_required_common_field"
    INVALID_FIELD_TYPE = "invalid_field_type"
    AUTHORIZATION_CHECK_MISSING = "authorization_check_missing"
    AUTHORIZATION_CHECK_MALFORMED = "authorization_check_malformed"

    # Continuity basis (C5) — validator_contract §10
    CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE = "continuity_basis_role_not_eligible"
    CONTINUITY_BASIS_MALFORMED = "continuity_basis_malformed"


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
    ViolationCode.HASH_FORMAT_INVALID: ViolationClass.CHAIN,
    # Schema (C3) — structural; a malformed envelope can't be parentage-checked.
    ViolationCode.UNKNOWN_FIELD_IN_ENVELOPE: ViolationClass.STRUCTURAL,
    ViolationCode.MISSING_REQUIRED_COMMON_FIELD: ViolationClass.STRUCTURAL,
    ViolationCode.INVALID_FIELD_TYPE: ViolationClass.STRUCTURAL,
    ViolationCode.AUTHORIZATION_CHECK_MISSING: ViolationClass.STRUCTURAL,
    ViolationCode.AUTHORIZATION_CHECK_MALFORMED: ViolationClass.STRUCTURAL,
    # Continuity basis (C5)
    ViolationCode.CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE: ViolationClass.STRUCTURAL,
    ViolationCode.CONTINUITY_BASIS_MALFORMED: ViolationClass.STRUCTURAL,
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


class EnvelopeParseError(ValueError):
    """Raised by ``StandingReceipt.from_dict`` on hostile/malformed input.

    Carries the typed ``violations`` so callers can surface them in the
    same vocabulary as the runtime validator.
    """

    def __init__(self, violations: list["Violation"]) -> None:
        codes = ",".join(v.code.value for v in violations)
        super().__init__(f"envelope parse failed: {codes}")
        self.violations: list[Violation] = list(violations)


# =============================================================================
# Structured check results (validator_contract §9, standing_and_receipts §7.4)
# =============================================================================


def _validate_basis_block(
    data: object,
    *,
    field_label: str,
    violation_code: "ViolationCode",
) -> tuple[str, str, tuple[str, ...]]:
    """Shared parser for the ``{summary, rule_id, inspectable_refs}`` shape.

    Used by :class:`CheckBasis` (Check.basis, C4) and
    :class:`BasisRecord` (continuity sub-bases, C5). Returns the
    validated triple. Raises :class:`EnvelopeParseError` carrying the
    caller-supplied violation code so different basis surfaces can
    surface their own typed rejection (CheckBasis →
    ``AUTHORIZATION_CHECK_MALFORMED``; BasisRecord →
    ``CONTINUITY_BASIS_MALFORMED``).

    Same shape, different species — no shared dataclass (per chatty
    rule: reuse helpers, not object identity).
    """

    if not isinstance(data, Mapping):
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=(
                        f"{field_label} must be a structured mapping "
                        "({summary, rule_id, inspectable_refs}); freeform "
                        "string is not admissible"
                    ),
                )
            ]
        )
    allowed = {"summary", "rule_id", "inspectable_refs"}
    unknown = set(data.keys()) - allowed
    if unknown:
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=f"unknown {field_label} field(s): {sorted(unknown)}",
                )
            ]
        )
    missing = allowed - set(data.keys())
    if missing:
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=f"{field_label} missing required field(s): {sorted(missing)}",
                )
            ]
        )
    summary = data["summary"]
    rule_id = data["rule_id"]
    refs = data["inspectable_refs"]
    if not isinstance(summary, str) or not summary:
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=f"{field_label}.summary must be a non-empty string",
                )
            ]
        )
    if not isinstance(rule_id, str) or not rule_id:
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=f"{field_label}.rule_id must be a non-empty string",
                )
            ]
        )
    if not isinstance(refs, (list, tuple)) or not refs:
        raise EnvelopeParseError(
            [
                Violation(
                    code=violation_code,
                    message=(
                        f"{field_label}.inspectable_refs must be a non-empty list "
                        "of references to inspectable state"
                    ),
                )
            ]
        )
    for r in refs:
        if not isinstance(r, str) or not r:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=violation_code,
                        message=(
                            f"{field_label}.inspectable_refs entries must be "
                            "non-empty strings"
                        ),
                    )
                ]
            )
    return summary, rule_id, tuple(refs)


@dataclass(frozen=True)
class CheckBasis:
    """Structured provenance for a check's verdict (C4).

    Replaces the freeform ``basis: str`` field on :class:`Check`. The
    validator does not adjudicate whether the basis is *wise* — that
    would be policy depth. It does enforce that the basis is
    inspectable: there is a rule, a brief, and at least one
    reference to something an auditor can interrogate.

    The hidden failure mode this prevents:
    ``{"result":"pass","basis":"seemed fine"}`` — a verdict that
    points at nothing.
    """

    summary: str  # non-empty brief reason
    rule_id: str  # which rule produced the verdict (e.g. "validator_contract.5.1")
    inspectable_refs: tuple[str, ...]  # non-empty; ids/keys/handles to inspectable state

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "rule_id": self.rule_id,
            "inspectable_refs": list(self.inspectable_refs),
        }

    @classmethod
    def from_dict(cls, data: object) -> "CheckBasis":
        summary, rule_id, refs = _validate_basis_block(
            data,
            field_label="check.basis",
            violation_code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
        )
        return cls(summary=summary, rule_id=rule_id, inspectable_refs=refs)


# =============================================================================
# Continuity basis (C5, validator_contract §10)
# =============================================================================


@dataclass(frozen=True)
class BasisRecord:
    """Generic structured basis record: summary + rule_id + non-empty refs.

    Same *shape* as :class:`CheckBasis` (chatty rule: reuse the helper,
    not the object identity). Distinct *type* because the semantic
    surface is different — a basis record inside
    :class:`ContinuityBasis` is one of four sub-bases for a continuity
    preservation claim, not a check verdict.

    If a future ratification ever discovers the semantics are actually
    identical, this and :class:`CheckBasis` can be merged via a
    Q4-style supersession; until then they stay distinct so each
    surface can drift independently.
    """

    summary: str
    rule_id: str
    inspectable_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "rule_id": self.rule_id,
            "inspectable_refs": list(self.inspectable_refs),
        }

    @classmethod
    def from_dict(cls, data: object, *, field_label: str) -> "BasisRecord":
        summary, rule_id, refs = _validate_basis_block(
            data,
            field_label=field_label,
            violation_code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
        )
        return cls(summary=summary, rule_id=rule_id, inspectable_refs=refs)


# The four required sub-basis fields per validator_contract §10.
# Order matters only for canonical serialization (sort_keys handles it).
CONTINUITY_BASIS_FIELDS: tuple[str, ...] = (
    "identity_basis",
    "provenance_basis",
    "evidence_basis",
    "operator_confidence_basis",
)


@dataclass(frozen=True)
class ContinuityBasis:
    """A continuity preservation claim block (C5, validator_contract §10).

    Presence on a receipt = an explicit claim that this receipt
    preserves continuity. The block is governed all-or-nothing:
    partial bases are rejected. ``operator_confidence_basis`` is
    descriptive only at this layer — the validator enforces presence
    and shape, but does not read its value as a weighting signal.
    Promoting it to adjudicative would be a separate Q4-style
    supersession.
    """

    identity_basis: BasisRecord
    provenance_basis: BasisRecord
    evidence_basis: BasisRecord
    operator_confidence_basis: BasisRecord

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name).to_dict() for name in CONTINUITY_BASIS_FIELDS}

    @classmethod
    def from_dict(cls, data: object) -> "ContinuityBasis":
        if data is None:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
                        message=(
                            "continuity_basis is presence-as-claim; "
                            "explicit null is not admissible (omit the field "
                            "to make no continuity claim)"
                        ),
                    )
                ]
            )
        if not isinstance(data, Mapping):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
                        message=(
                            "continuity_basis must be a structured mapping "
                            "with all four required sub-bases"
                        ),
                    )
                ]
            )
        if not data:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
                        message=(
                            "continuity_basis is presence-as-claim; empty "
                            "block is not admissible (omit the field to make "
                            "no continuity claim)"
                        ),
                    )
                ]
            )
        required = set(CONTINUITY_BASIS_FIELDS)
        unknown = set(data.keys()) - required
        if unknown:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
                        message=f"unknown continuity_basis field(s): {sorted(unknown)}",
                    )
                ]
            )
        missing = required - set(data.keys())
        if missing:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.CONTINUITY_BASIS_MALFORMED,
                        message=(
                            f"continuity_basis missing required sub-basis: {sorted(missing)} "
                            "(all-or-nothing — partial blocks are not admissible)"
                        ),
                    )
                ]
            )
        return cls(
            identity_basis=BasisRecord.from_dict(
                data["identity_basis"], field_label="continuity_basis.identity_basis"
            ),
            provenance_basis=BasisRecord.from_dict(
                data["provenance_basis"], field_label="continuity_basis.provenance_basis"
            ),
            evidence_basis=BasisRecord.from_dict(
                data["evidence_basis"], field_label="continuity_basis.evidence_basis"
            ),
            operator_confidence_basis=BasisRecord.from_dict(
                data["operator_confidence_basis"],
                field_label="continuity_basis.operator_confidence_basis",
            ),
        )


@dataclass(frozen=True)
class Check:
    """A single structured check result on an authorization receipt.

    Both fields are required. Boolean-only or ID-only check values are
    insufficient (validator_contract §9). The ``basis`` is itself a
    structured :class:`CheckBasis` — schema enforces presence, shape,
    and inspectability, but does not adjudicate semantic content depth.
    """

    result: CheckResultStatus
    basis: CheckBasis

    def to_dict(self) -> dict[str, Any]:
        return {"result": self.result.value, "basis": self.basis.to_dict()}

    @classmethod
    def from_dict(cls, data: object) -> "Check":
        if not isinstance(data, Mapping):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                        message=f"check entry must be a mapping, got {type(data).__name__}",
                    )
                ]
            )
        unknown = set(data.keys()) - {"result", "basis"}
        if unknown:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                        message=f"unknown check field(s): {sorted(unknown)}",
                    )
                ]
            )
        result_raw = data.get("result")
        basis_raw = data.get("basis")
        if not isinstance(result_raw, str):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                        message="check.result must be a string",
                    )
                ]
            )
        try:
            result = CheckResultStatus(result_raw)
        except ValueError:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                        message=(
                            f"check.result {result_raw!r} not in "
                            f"{[s.value for s in CheckResultStatus]}"
                        ),
                    )
                ]
            ) from None
        # Delegates to CheckBasis — raises EnvelopeParseError on the
        # "seemed fine" string-basis case.
        basis = CheckBasis.from_dict(basis_raw)
        return cls(result=result, basis=basis)


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


# Closed envelope key set — anything else in a deserialized dict is
# UNKNOWN_FIELD_IN_ENVELOPE. This is the C3 schema-discipline anchor:
# adding a field is a ruleset change requiring a validator version bump
# (Q4 supersession discipline).
STANDING_RECEIPT_ENVELOPE_KEYS: frozenset[str] = frozenset(
    {
        "receipt_id",
        "receipt_role",
        "standing_class",
        "subject",
        "ontology_version",
        "producer",
        "created_at",
        "parent_receipts",
        "subject_derivation",
        "exception_class",
        "exception_reason",
        "operator_approval_ref",
        "compression_acknowledged",
        "policy_artifact_id",
        "policy_artifact_hash",
        "verdict",
        "checks",
        "continuity_basis",
        "payload",
        "display_metadata",
        "gaps",
        "gaps_resolved",
        "content_hash",
    }
)


# Always-required common fields per standing_and_receipts §6. Missing
# any of these on a deserialized envelope is MISSING_REQUIRED_COMMON_FIELD.
REQUIRED_COMMON_FIELDS: frozenset[str] = frozenset(
    {
        "receipt_id",
        "receipt_role",
        "standing_class",
        "subject",
        "ontology_version",
        "producer",
        "created_at",
    }
)


@dataclass(frozen=True)
class StandingReceipt:
    """A standing-class receipt envelope.

    The canonical body for hashing is everything except ``content_hash``
    and the optional ``display_metadata`` field. ``display_metadata`` is
    operator-facing UI only and per Q1 acceptance #4 must not change the
    receipt hash when edited.

    Deserialization (``from_dict``) treats hostile input as a real
    threat surface: unknown fields are rejected, missing required
    fields are rejected, type mismatches are rejected. There is no
    best-effort normalization.
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
    # Structured check results (validator_contract §9). AUTHORIZE
    # receipts must carry the four AUTHORIZE_REQUIRED_CHECKS; the
    # schema validator enforces presence + shape.
    checks: dict[str, Check] = field(default_factory=dict)
    # Continuity preservation claim (C5, validator_contract §10).
    # Presence = explicit claim. Only roles in
    # CONTINUITY_CLAIMABLE_ROLES may carry this field; the schema
    # validator enforces the role gate.
    continuity_basis: ContinuityBasis | None = None
    # Free-form payload (role-specific extras kept here so envelope shape
    # stays stable; per-role payload schema is follow-on work).
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
        Enum values are normalized to their string forms so
        canonical_json output is stable across runs and processes.
        """

        body = asdict(self)
        body.pop("content_hash", None)
        body.pop("display_metadata", None)
        body["receipt_role"] = self.receipt_role.value
        body["standing_class"] = self.standing_class.value
        if self.subject_derivation is not None:
            body["subject_derivation"]["kind"] = self.subject_derivation.kind.value
        if self.verdict is not None:
            body["verdict"] = self.verdict.value
        # checks: normalize CheckResultStatus enums.
        body["checks"] = {name: chk.to_dict() for name, chk in self.checks.items()}
        # continuity_basis is presence-as-claim — absence = no claim.
        # asdict gives us ``None`` when the field is unset; drop it so
        # the canonical body distinguishes absence from explicit null
        # (explicit null is rejected by from_dict as a loophole).
        if self.continuity_basis is None:
            body.pop("continuity_basis", None)
        else:
            body["continuity_basis"] = self.continuity_basis.to_dict()
        return body

    def to_dict(self) -> dict[str, Any]:
        """Full, roundtrippable dict including content_hash + display_metadata.

        Round-trip property: ``from_dict(to_dict(r)).canonical_body()``
        equals ``r.canonical_body()`` byte-identically.
        """

        body = self.canonical_body()
        if self.content_hash is not None:
            body["content_hash"] = self.content_hash
        if self.display_metadata:
            body["display_metadata"] = dict(self.display_metadata)
        return body

    def compute_content_hash(self) -> str:
        return content_hash(self.canonical_body())

    @classmethod
    def from_dict(cls, data: object) -> "StandingReceipt":
        """Parse a receipt from a dict with hostile-input discipline.

        Raises :class:`EnvelopeParseError` carrying typed
        :class:`Violation` instances for any of:

        - non-mapping input
        - unknown keys (closed envelope)
        - missing required common fields
        - wrong types on structured fields (parent_receipts,
          subject_derivation, checks)
        - bad ``sha256:[64-hex]`` content hashes
        - unknown enum values (receipt_role, standing_class, verdict,
          subject_derivation.kind)

        There is no best-effort normalization. Quietly accepting
        nonsense is exactly the failure mode this method exists to
        prevent.
        """

        if not isinstance(data, Mapping):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.INVALID_FIELD_TYPE,
                        message=f"envelope must be a mapping, got {type(data).__name__}",
                    )
                ]
            )
        violations: list[Violation] = []
        unknown = set(data.keys()) - STANDING_RECEIPT_ENVELOPE_KEYS
        for key in sorted(unknown):
            violations.append(
                Violation(
                    code=ViolationCode.UNKNOWN_FIELD_IN_ENVELOPE,
                    message=f"unknown envelope key {key!r}",
                )
            )
        missing = REQUIRED_COMMON_FIELDS - set(data.keys())
        for key in sorted(missing):
            violations.append(
                Violation(
                    code=ViolationCode.MISSING_REQUIRED_COMMON_FIELD,
                    message=f"required common field {key!r} missing",
                )
            )
        if violations:
            raise EnvelopeParseError(violations)

        # Required fields are all string-valued at this layer.
        for key in REQUIRED_COMMON_FIELDS:
            if not isinstance(data[key], str):
                violations.append(
                    Violation(
                        code=ViolationCode.INVALID_FIELD_TYPE,
                        message=f"common field {key!r} must be a string",
                    )
                )
        if violations:
            raise EnvelopeParseError(violations)

        # Closed enums.
        try:
            receipt_role = ReceiptRole(data["receipt_role"])
        except ValueError:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.UNKNOWN_RECEIPT_ROLE,
                        message=f"receipt_role {data['receipt_role']!r} not in closed set",
                    )
                ]
            ) from None
        try:
            standing_class = StandingClass(data["standing_class"])
        except ValueError:
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.UNKNOWN_STANDING_CLASS,
                        message=f"standing_class {data['standing_class']!r} not in closed set",
                    )
                ]
            ) from None

        # parent_receipts: list of {id, content_hash}.
        parent_receipts = _parse_parent_refs(data.get("parent_receipts", []))

        # subject_derivation: optional structured.
        sd_raw = data.get("subject_derivation")
        subject_derivation = (
            _parse_subject_derivation(sd_raw) if sd_raw is not None else None
        )

        # operator_approval_ref: optional ParentRef.
        oar_raw = data.get("operator_approval_ref")
        operator_approval_ref = (
            _parse_one_parent_ref(oar_raw) if oar_raw is not None else None
        )

        # verdict: optional enum.
        verdict_raw = data.get("verdict")
        verdict: AuthorizationVerdict | None = None
        if verdict_raw is not None:
            try:
                verdict = AuthorizationVerdict(verdict_raw)
            except ValueError:
                raise EnvelopeParseError(
                    [
                        Violation(
                            code=ViolationCode.INVALID_FIELD_TYPE,
                            message=f"verdict {verdict_raw!r} not in closed set",
                        )
                    ]
                ) from None

        # checks: dict[str, Check].
        checks_raw = data.get("checks", {})
        if not isinstance(checks_raw, Mapping):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.INVALID_FIELD_TYPE,
                        message="checks must be a mapping",
                    )
                ]
            )
        checks: dict[str, Check] = {}
        for name, chk_raw in checks_raw.items():
            if not isinstance(name, str):
                raise EnvelopeParseError(
                    [
                        Violation(
                            code=ViolationCode.INVALID_FIELD_TYPE,
                            message="check names must be strings",
                        )
                    ]
                )
            checks[name] = Check.from_dict(chk_raw)

        # continuity_basis (C5): role gate enforced by schema pre-pass;
        # here we only parse the structure if the key is present.
        # Note: from_dict treats explicit ``continuity_basis: null`` and
        # ``continuity_basis: {}`` as malformed (presence-as-claim
        # cannot be loophole'd). Omit the field to make no claim.
        continuity_basis: ContinuityBasis | None = None
        if "continuity_basis" in data:
            continuity_basis = ContinuityBasis.from_dict(
                data["continuity_basis"]
            )

        # Hash format checks (chain class).
        cont_hash = data.get("content_hash")
        if cont_hash is not None and not is_valid_content_hash(cont_hash):
            violations.append(
                Violation(
                    code=ViolationCode.HASH_FORMAT_INVALID,
                    message=f"content_hash {cont_hash!r} is not sha256:<64-hex>",
                )
            )
        pa_hash = data.get("policy_artifact_hash")
        if pa_hash is not None and not is_valid_content_hash(pa_hash):
            violations.append(
                Violation(
                    code=ViolationCode.HASH_FORMAT_INVALID,
                    message=f"policy_artifact_hash {pa_hash!r} is not sha256:<64-hex>",
                )
            )
        if violations:
            raise EnvelopeParseError(violations)

        return cls(
            receipt_id=data["receipt_id"],
            receipt_role=receipt_role,
            standing_class=standing_class,
            subject=data["subject"],
            ontology_version=data["ontology_version"],
            producer=data["producer"],
            created_at=data["created_at"],
            parent_receipts=parent_receipts,
            subject_derivation=subject_derivation,
            exception_class=data.get("exception_class"),
            exception_reason=data.get("exception_reason"),
            operator_approval_ref=operator_approval_ref,
            compression_acknowledged=bool(data.get("compression_acknowledged", False)),
            policy_artifact_id=data.get("policy_artifact_id"),
            policy_artifact_hash=pa_hash,
            verdict=verdict,
            checks=checks,
            continuity_basis=continuity_basis,
            payload=dict(data.get("payload", {})),
            display_metadata=dict(data.get("display_metadata", {})),
            gaps=tuple(data.get("gaps", ())),
            gaps_resolved=tuple(data.get("gaps_resolved", ())),
            content_hash=cont_hash,
        )


def _parse_parent_refs(value: object) -> tuple[ParentRef, ...]:
    if not isinstance(value, (list, tuple)):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="parent_receipts must be a list",
                )
            ]
        )
    refs: list[ParentRef] = []
    violations: list[Violation] = []
    for entry in value:
        try:
            refs.append(_parse_one_parent_ref(entry))
        except EnvelopeParseError as exc:
            violations.extend(exc.violations)
    if violations:
        raise EnvelopeParseError(violations)
    return tuple(refs)


def _parse_one_parent_ref(value: object) -> ParentRef:
    if not isinstance(value, Mapping):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="parent reference must be a mapping with id + content_hash",
                )
            ]
        )
    unknown = set(value.keys()) - {"id", "content_hash"}
    if unknown:
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.UNKNOWN_FIELD_IN_ENVELOPE,
                    message=f"unknown parent_ref keys: {sorted(unknown)}",
                )
            ]
        )
    pid = value.get("id")
    phash = value.get("content_hash")
    if not isinstance(pid, str) or not pid:
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.PARENT_REFERENCE_ID_ONLY,
                    message="parent_ref.id must be a non-empty string",
                )
            ]
        )
    if not is_valid_content_hash(phash):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.HASH_FORMAT_INVALID,
                    message=f"parent_ref.content_hash {phash!r} is not sha256:<64-hex>",
                )
            ]
        )
    return ParentRef(id=pid, content_hash=phash)


def _parse_subject_derivation(value: object) -> SubjectDerivation:
    if not isinstance(value, Mapping):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="subject_derivation must be a mapping",
                )
            ]
        )
    allowed_keys = {"kind", "parent_id", "aggregate_parent_ids", "containment_basis", "basis"}
    unknown = set(value.keys()) - allowed_keys
    if unknown:
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.UNKNOWN_FIELD_IN_ENVELOPE,
                    message=f"unknown subject_derivation keys: {sorted(unknown)}",
                )
            ]
        )
    kind_raw = value.get("kind")
    if not isinstance(kind_raw, str):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="subject_derivation.kind must be a string",
                )
            ]
        )
    try:
        kind = SubjectDerivationKind(kind_raw)
    except ValueError:
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.SUBJECT_DERIVATION_KIND_UNKNOWN,
                    message=f"subject_derivation.kind {kind_raw!r} not in closed set",
                )
            ]
        ) from None
    parent_id = value.get("parent_id")
    if not isinstance(parent_id, str) or not parent_id:
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="subject_derivation.parent_id must be a non-empty string",
                )
            ]
        )
    agg = value.get("aggregate_parent_ids", ())
    if not isinstance(agg, (list, tuple)):
        raise EnvelopeParseError(
            [
                Violation(
                    code=ViolationCode.INVALID_FIELD_TYPE,
                    message="subject_derivation.aggregate_parent_ids must be a list",
                )
            ]
        )
    for item in agg:
        if not isinstance(item, str):
            raise EnvelopeParseError(
                [
                    Violation(
                        code=ViolationCode.INVALID_FIELD_TYPE,
                        message="aggregate_parent_ids entries must be strings",
                    )
                ]
            )
    return SubjectDerivation(
        kind=kind,
        parent_id=parent_id,
        aggregate_parent_ids=tuple(agg),
        containment_basis=value.get("containment_basis"),
        basis=value.get("basis"),
    )


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
# Single canonical owner: ``receipt_kernel.envelope``. Standing receipts and
# kernel events use byte-identical canonicalization so a future Q1.A
# ratification picking "new event types" can carry these bodies forward
# without rehashing. ``canonical_json`` is re-exported (not duplicated)
# so any future change to canonical-form parameters lands in one place.


def content_hash(obj: Any) -> str:
    """Return ``sha256:<hex>`` content hash for an object's canonical JSON."""

    return compute_hash(canonical_json(obj))
