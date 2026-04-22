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
"""

from governor.standing.policy_registry import (
    PolicyArtifact,
    PolicyRegistry,
    load_decisions_directory,
)
from governor.standing.types import (
    ALLOWED_PARENT_STANDING,
    AuthorizationVerdict,
    BOOTSTRAP_POLICY_ARTIFACT_IDS,
    ParentRef,
    ReceiptRole,
    ROLE_TO_STANDING,
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
)
from governor.standing.validator import (
    BootstrapError,
    StandingChainValidator,
    VALIDATOR_ID,
    VALIDATOR_VERSION,
)

__all__ = [
    "ALLOWED_PARENT_STANDING",
    "AuthorizationVerdict",
    "BOOTSTRAP_POLICY_ARTIFACT_IDS",
    "BootstrapError",
    "ParentRef",
    "PolicyArtifact",
    "PolicyRegistry",
    "ReceiptRole",
    "ROLE_TO_STANDING",
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
    "load_decisions_directory",
]
