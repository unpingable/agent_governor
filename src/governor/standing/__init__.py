# SPDX-License-Identifier: Apache-2.0
"""Standing-class chain validator.

Constitutional substrate for the standing lattice
(OBSERVE → INTERPRET → RECOMMEND → AUTHORIZE → EXECUTE → POLICY_DECLARE).

Implements the validator contract from
``docs/doctrine/validator_contract.md`` and the four ratified integration
decisions:

- ``decision.validator_integration.q1`` — kernel composition (Option A,
  ride libs/receipt_kernel)
- ``decision.validator_integration.q2`` — subject_derivation closed enum
  (Option B, four kinds, policy-declared extension)
- ``decision.validator_integration.q3`` — exception-class registry
  (Option A, closed/governed, initial registry empty,
  OBSERVE → AUTHORIZE only)
- ``decision.validator_integration.q4`` — validator provenance
  (Option A, every validator version is a policy_declaration)

See ``specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md`` for the gap spec
that pins these resolutions.

Coexistence note: this package currently houses two unrelated substrates
by design-for-now, not by accident:

- Constitutional validator (this ``__init__.py`` re-exports): standing
  lattice, receipts, validator contract.
- Workload-identity verification (``workload_identity`` submodule):
  HMAC-signed auth tokens.

Both were once named ``governor.standing``. The top-level ``__init__``
exports only validator symbols to avoid name collision at the package
root. Callers that need workload-identity primitives must import via
``governor.standing.workload_identity`` explicitly. If the split ever
feels stupid enough to fix, rename the submodule to
``governor.workload_identity`` rather than merging the root surfaces.
"""

from governor.standing.policy_registry import (
    PolicyArtifact,
    PolicyRegistry,
    load_decisions_directory,
)
from governor.standing.schema import SCHEMA_SNAPSHOT, validate_schema
from governor.standing.types import (
    ALLOWED_PARENT_STANDING,
    AUTHORIZE_REQUIRED_CHECKS,
    AuthorizationVerdict,
    BOOTSTRAP_POLICY_ARTIFACT_IDS,
    BasisRecord,
    CONTINUITY_BASIS_FIELDS,
    CONTINUITY_CLAIMABLE_ROLES,
    Check,
    CheckBasis,
    CheckResultStatus,
    ContinuityBasis,
    EnvelopeParseError,
    HASH_PATTERN,
    ParentRef,
    REQUIRED_COMMON_FIELDS,
    ReceiptRole,
    ROLE_TO_STANDING,
    STANDING_RECEIPT_ENVELOPE_KEYS,
    StandingClass,
    StandingReceipt,
    SubjectDerivation,
    SubjectDerivationKind,
    ValidationOutcome,
    ValidationReceipt,
    Violation,
    ViolationClass,
    ViolationCode,
    canonical_json,
    content_hash,
    is_valid_content_hash,
)
from governor.standing.validator import (
    BootstrapError,
    StandingChainValidator,
    VALIDATOR_ID,
    VALIDATOR_VERSION,
)

__all__ = [
    "ALLOWED_PARENT_STANDING",
    "AUTHORIZE_REQUIRED_CHECKS",
    "AuthorizationVerdict",
    "BOOTSTRAP_POLICY_ARTIFACT_IDS",
    "BasisRecord",
    "BootstrapError",
    "CONTINUITY_BASIS_FIELDS",
    "CONTINUITY_CLAIMABLE_ROLES",
    "Check",
    "CheckBasis",
    "CheckResultStatus",
    "ContinuityBasis",
    "EnvelopeParseError",
    "HASH_PATTERN",
    "ParentRef",
    "PolicyArtifact",
    "PolicyRegistry",
    "REQUIRED_COMMON_FIELDS",
    "ReceiptRole",
    "ROLE_TO_STANDING",
    "SCHEMA_SNAPSHOT",
    "STANDING_RECEIPT_ENVELOPE_KEYS",
    "StandingChainValidator",
    "StandingClass",
    "StandingReceipt",
    "SubjectDerivation",
    "SubjectDerivationKind",
    "VALIDATOR_ID",
    "VALIDATOR_VERSION",
    "ValidationOutcome",
    "ValidationReceipt",
    "Violation",
    "ViolationClass",
    "ViolationCode",
    "canonical_json",
    "content_hash",
    "is_valid_content_hash",
    "load_decisions_directory",
    "validate_schema",
]
