# SPDX-License-Identifier: Apache-2.0
"""Runtime schema validator (C3).

Runs as a pre-pass before the rest of :class:`StandingChainValidator`
checks. A malformed envelope can't be parentage-checked sensibly, so
schema violations are surfaced first.

Scope held tight on purpose: shape and presence, not policy depth.
This module does not try to model the full §7 per-role required-field
catalogue — that's follow-on work as we accumulate field experience.
What it enforces:

- ``sha256:[64-hex]`` format on every content hash that appears on a
  constructed receipt
- AUTHORIZE receipts carry all four
  :data:`~governor.standing.types.AUTHORIZE_REQUIRED_CHECKS` and
  every check is a well-formed :class:`~governor.standing.types.Check`

The deserialization path (``StandingReceipt.from_dict``) handles closed
envelope + missing common fields + type rejection. Together they form
the schema discipline: hostile input fails fast at the boundary,
in-code construction fails at this runtime pass.
"""

from __future__ import annotations

from governor.standing.types import (
    AUTHORIZE_REQUIRED_CHECKS,
    CONTINUITY_BASIS_FIELDS,
    CONTINUITY_CLAIMABLE_ROLES,
    Check,
    CheckBasis,
    StandingClass,
    StandingReceipt,
    Violation,
    ViolationCode,
    is_valid_content_hash,
)


# Hashed snapshot of what this module enforces. Folded into the
# validator's ruleset_hash so any change here forces a Q4 supersession.
SCHEMA_SNAPSHOT: dict[str, object] = {
    "schema_version": "0.4.0",
    "authorize_required_checks": sorted(AUTHORIZE_REQUIRED_CHECKS),
    "check_field_set": ["result", "basis"],
    "check_basis_field_set": ["summary", "rule_id", "inspectable_refs"],
    "continuity_basis_field_set": list(CONTINUITY_BASIS_FIELDS),
    "continuity_claimable_roles": sorted(r.value for r in CONTINUITY_CLAIMABLE_ROLES),
    "hash_pattern": "^sha256:[0-9a-f]{64}$",
}


def validate_schema(receipt: StandingReceipt) -> list[Violation]:
    """Return runtime schema violations for a constructed receipt.

    Empty list = receipt passes the schema pre-pass. Non-empty = the
    rest of the validator should not run; the envelope is too malformed
    to evaluate.
    """

    violations: list[Violation] = []

    # Hash format — every content_hash on the constructed receipt.
    if receipt.content_hash is not None and not is_valid_content_hash(
        receipt.content_hash
    ):
        violations.append(
            Violation(
                code=ViolationCode.HASH_FORMAT_INVALID,
                message=(
                    f"content_hash {receipt.content_hash!r} is not sha256:<64-hex>"
                ),
                receipt_id=receipt.receipt_id,
            )
        )
    if (
        receipt.policy_artifact_hash is not None
        and not is_valid_content_hash(receipt.policy_artifact_hash)
    ):
        violations.append(
            Violation(
                code=ViolationCode.HASH_FORMAT_INVALID,
                message=(
                    f"policy_artifact_hash {receipt.policy_artifact_hash!r} "
                    "is not sha256:<64-hex>"
                ),
                receipt_id=receipt.receipt_id,
            )
        )
    for parent in receipt.parent_receipts:
        if not is_valid_content_hash(parent.content_hash):
            violations.append(
                Violation(
                    code=ViolationCode.HASH_FORMAT_INVALID,
                    message=(
                        f"parent {parent.id} content_hash {parent.content_hash!r} "
                        "is not sha256:<64-hex>"
                    ),
                    receipt_id=receipt.receipt_id,
                    pointers=(parent.id,),
                )
            )

    # AUTHORIZE structured-check enforcement (validator_contract §9).
    if receipt.standing_class == StandingClass.AUTHORIZE:
        violations.extend(_check_authorize_checks(receipt))

    # Continuity basis role gate (C5, validator_contract §10).
    # Presence-as-claim: if the field is set, the role must be in
    # CONTINUITY_CLAIMABLE_ROLES. The structural validity of the block
    # itself is enforced at parse time by ContinuityBasis.from_dict.
    if receipt.continuity_basis is not None:
        if receipt.receipt_role not in CONTINUITY_CLAIMABLE_ROLES:
            violations.append(
                Violation(
                    code=ViolationCode.CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE,
                    message=(
                        f"role {receipt.receipt_role.value!r} cannot claim "
                        "continuity preservation; only "
                        f"{sorted(r.value for r in CONTINUITY_CLAIMABLE_ROLES)} "
                        "may carry continuity_basis"
                    ),
                    receipt_id=receipt.receipt_id,
                )
            )

    return violations


def _check_authorize_checks(receipt: StandingReceipt) -> list[Violation]:
    """Per validator_contract §9: presence + shape of the four required checks."""

    violations: list[Violation] = []
    present = set(receipt.checks.keys())
    missing = AUTHORIZE_REQUIRED_CHECKS - present
    for name in sorted(missing):
        violations.append(
            Violation(
                code=ViolationCode.AUTHORIZATION_CHECK_MISSING,
                message=f"AUTHORIZE receipt missing required check {name!r}",
                receipt_id=receipt.receipt_id,
                pointers=(name,),
            )
        )
    # In-code construction can stash a non-Check value into the dict,
    # or a Check whose basis is the wrong type (the dataclass doesn't
    # type-check). Belt-and-suspenders against both.
    for name, value in receipt.checks.items():
        if not isinstance(value, Check):
            violations.append(
                Violation(
                    code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                    message=(
                        f"check {name!r} must be a Check instance, "
                        f"got {type(value).__name__}"
                    ),
                    receipt_id=receipt.receipt_id,
                    pointers=(name,),
                )
            )
            continue
        if not isinstance(value.basis, CheckBasis):
            violations.append(
                Violation(
                    code=ViolationCode.AUTHORIZATION_CHECK_MALFORMED,
                    message=(
                        f"check {name!r} basis must be a CheckBasis instance, "
                        f"got {type(value.basis).__name__} — freeform string "
                        "basis is not admissible (C4)"
                    ),
                    receipt_id=receipt.receipt_id,
                    pointers=(name,),
                )
            )
    return violations
