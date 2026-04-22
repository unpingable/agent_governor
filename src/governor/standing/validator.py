# SPDX-License-Identifier: Apache-2.0
"""Standing-class chain validator.

Implements the must-land cut from
``specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md`` §"first-pass
implementation priority" rolled together with the four ratified Q1–Q4
decisions:

1. parentage / transition (validator_contract §5)
2. policy registry verification (§8)
3. chain integrity (§6)
4. subject_derivation closed enum (Q2)
5. exception-class admissibility (Q3 — empty registry, fail-closed)
6. validation receipt provenance (Q4)
7. envelope schema discipline (C3) — closed key set, structured
   AUTHORIZE checks (validator_contract §9), strict content-hash
   format

Gap survival/resolution (§7) and per-role payload field schemas are
follow-on commits.

There are no Q5 pre-ratification fallbacks anywhere in this file. Every
rule below is the ratified rule.

Version history (each bump = ``policy_declaration`` with
``supersedes`` populated, per Q4):

- ``0.1.0`` — initial validator (C2)
- ``0.2.0`` — schema discipline (C3): structured AUTHORIZE checks,
  strict hash format, closed envelope, ``from_dict`` deserialization
  hostile-input rejection
- ``0.3.0`` — Check.basis structure (C4): ``basis`` becomes a
  :class:`CheckBasis` (summary + rule_id + inspectable_refs);
  freeform string basis is no longer admissible. First repeat
  exercise of the supersession ceremony.
- ``0.4.0`` — Continuity basis (C5, validator_contract §10):
  ``continuity_basis`` is a structured all-or-nothing block on
  receipts that claim continuity preservation. Role-gated to
  recommendation/authorization/action only. Third iteration of the
  supersession ceremony — the pattern is now routine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from governor.standing.policy_registry import PolicyArtifact, PolicyRegistry
from governor.standing.schema import SCHEMA_SNAPSHOT, validate_schema
from governor.standing.types import (
    ALLOWED_PARENT_STANDING,
    BOOTSTRAP_POLICY_ARTIFACT_IDS,
    ParentRef,
    ROLE_TO_STANDING,
    ReceiptRole,
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
)


VALIDATOR_ID = "agent_gov.standing_chain_validator"
VALIDATOR_VERSION = "0.4.0"

# The validator's own constitutional anchor. The artifact carries
# ``expected_ruleset_hash`` in its frontmatter; startup compares that
# value against :func:`compute_ruleset_hash` and refuses to run on
# mismatch (Q4 acceptance #2 + #4). Each version bump moves this
# pointer to a new ratified declaration with ``supersedes`` populated.
VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID = "decision.validator.v0_4_0"


class BootstrapError(RuntimeError):
    """Raised when the validator cannot resolve its constitutional anchor.

    The ratified Q4 rule is fail-closed at startup: missing ratified
    artifacts, missing bootstrap policy_declaration, or
    ``expected_ruleset_hash`` mismatch all refuse the validator. There
    is no override.
    """


# =============================================================================
# Ruleset identity
# =============================================================================


def _ruleset_snapshot() -> dict[str, object]:
    """Canonical, order-stable view of the rules the validator enforces.

    Anything that can change a verdict belongs here. Loaded policy
    registry contents do **not** belong here — those are hashed
    separately as ``policy_registry_hash``.

    A change to this snapshot bumps ``ruleset_hash``, which forces a
    Q4 supersession (new ``policy_declaration`` with ``supersedes``
    populated). That is the entire point of the snapshot existing.
    """

    return {
        "validator_id": VALIDATOR_ID,
        "validator_version": VALIDATOR_VERSION,
        "bootstrap_policy_artifact_ids": list(BOOTSTRAP_POLICY_ARTIFACT_IDS),
        "validator_bootstrap_policy_artifact_id": VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID,
        "role_to_standing": {
            r.value: ROLE_TO_STANDING[r].value
            for r in sorted(ROLE_TO_STANDING.keys(), key=lambda x: x.value)
        },
        "allowed_parent_standing": {
            r.value: (
                sorted(s.value for s in standings)
                if standings is not None
                else None
            )
            for r, standings in sorted(
                ALLOWED_PARENT_STANDING.items(), key=lambda kv: kv[0].value
            )
        },
        "subject_derivation_kinds": sorted(
            k.value for k in SubjectDerivationKind
        ),
        "validation_outcomes": sorted(o.value for o in ValidationOutcome),
        # C3: closed violation vocabulary + schema discipline.
        # Adding/removing codes here is a ruleset change.
        "violation_codes": sorted(c.value for c in ViolationCode),
        "schema": SCHEMA_SNAPSHOT,
        # Q3: initial exception-class registry is empty by ratification.
        # Adding a class is a registry mutation; that registry is hashed
        # separately as policy_registry_hash, not folded into ruleset.
    }


def compute_ruleset_hash() -> str:
    return f"sha256:{hashlib.sha256(canonical_json(_ruleset_snapshot())).hexdigest()}"


# =============================================================================
# Validator
# =============================================================================


@dataclass
class StandingChainValidator:
    """The constitutional wall.

    Construct with a :class:`PolicyRegistry` already loaded with the
    four ratified Q1–Q4 decisions and the validator's bootstrap
    policy_declaration. The constructor performs the startup integrity
    check and raises :class:`BootstrapError` on failure.
    """

    policy_registry: PolicyRegistry

    def __post_init__(self) -> None:
        self._verify_bootstrap()

    # ------------------------------------------------------------------
    # Bootstrap (Q4 §"ruleset_hash mismatch fail-closed at startup")
    # ------------------------------------------------------------------

    def _verify_bootstrap(self) -> None:
        missing_anchors = [
            pid
            for pid in BOOTSTRAP_POLICY_ARTIFACT_IDS
            if not self.policy_registry.has(pid)
        ]
        if missing_anchors:
            raise BootstrapError(
                "missing ratified Q1–Q4 anchors: "
                + ", ".join(missing_anchors)
            )
        bootstrap = self.policy_registry.get(
            VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID
        )
        if bootstrap is None:
            raise BootstrapError(
                "missing validator bootstrap policy_declaration "
                f"({VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID})"
            )
        expected = bootstrap.frontmatter.get("expected_ruleset_hash")
        actual = compute_ruleset_hash()
        if expected != actual:
            raise BootstrapError(
                "ruleset_hash mismatch: bootstrap declaration expects "
                f"{expected!r} but validator computes {actual!r}. "
                "Update the bootstrap policy_declaration with the new "
                "ruleset_hash and re-ratify, or revert the rule change."
            )
        declared_version = bootstrap.frontmatter.get("validator_version")
        if declared_version != VALIDATOR_VERSION:
            raise BootstrapError(
                "validator_version mismatch: bootstrap declaration "
                f"names {declared_version!r}, code is {VALIDATOR_VERSION!r}"
            )
        # If this declaration supersedes a prior version, verify the
        # supersession ceremony succeeded (Q4 + bootstrap doc:
        # "the new declaration must itself be admitted via a validation
        # receipt produced by the prior validator. The bootstrap
        # exemption is not transitive.").
        supersedes = bootstrap.frontmatter.get("supersedes")
        if supersedes:
            self._verify_supersession(bootstrap, supersedes)

    def _verify_supersession(
        self, bootstrap: PolicyArtifact, supersedes_id: str
    ) -> None:
        """Verify the prior-version validation receipt for a superseding
        bootstrap declaration. Fails loud — no interpretive dance."""

        prior = self.policy_registry.get(supersedes_id)
        if prior is None:
            raise BootstrapError(
                f"superseding bootstrap declares supersedes={supersedes_id!r}, "
                "but the prior declaration is missing from the registry"
            )
        receipt_path_raw = bootstrap.frontmatter.get("prior_validation_receipt_path")
        if not receipt_path_raw:
            raise BootstrapError(
                "superseding bootstrap missing prior_validation_receipt_path; "
                "the bootstrap exemption is not transitive — successors must "
                "carry an attested validation receipt produced by the prior "
                "validator"
            )
        # Path is relative to the bootstrap declaration's own directory
        # so the artifact pair (declaration + receipt) moves as a unit.
        # Tamper-evidence comes from the receipt's own target_receipts
        # entry binding to the declaration's content_hash; no separate
        # receipt_hash field is needed (and would create a hash-cycle).
        bootstrap_dir = Path(bootstrap.source_path).parent
        receipt_path = bootstrap_dir / receipt_path_raw
        if not receipt_path.is_file():
            raise BootstrapError(
                f"prior validation receipt not found at {receipt_path}"
            )
        receipt_bytes = receipt_path.read_bytes()
        try:
            receipt = json.loads(receipt_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError(
                f"prior validation receipt is not valid JSON: {exc}"
            ) from None
        # Receipt must claim the right validator + version + outcome.
        if receipt.get("validator_id") != VALIDATOR_ID:
            raise BootstrapError(
                "prior validation receipt validator_id mismatch: expected "
                f"{VALIDATOR_ID!r}, got {receipt.get('validator_id')!r}"
            )
        prior_declared_version = prior.frontmatter.get("validator_version")
        if receipt.get("validator_version") != prior_declared_version:
            raise BootstrapError(
                "prior validation receipt validator_version mismatch: prior "
                f"declaration names {prior_declared_version!r}, receipt has "
                f"{receipt.get('validator_version')!r}"
            )
        prior_expected_ruleset = prior.frontmatter.get("expected_ruleset_hash")
        if receipt.get("ruleset_hash") != prior_expected_ruleset:
            raise BootstrapError(
                "prior validation receipt ruleset_hash mismatch: prior "
                f"declaration declares {prior_expected_ruleset!r}, receipt "
                f"has {receipt.get('ruleset_hash')!r}"
            )
        if receipt.get("outcome") != ValidationOutcome.VALID.value:
            raise BootstrapError(
                "prior validation receipt outcome must be VALID, got "
                f"{receipt.get('outcome')!r}"
            )
        # The receipt must target this exact bootstrap declaration.
        targets = receipt.get("target_receipts") or []
        if not any(
            isinstance(t, dict)
            and t.get("id") == bootstrap.policy_artifact_id
            and t.get("content_hash") == bootstrap.content_hash
            for t in targets
        ):
            raise BootstrapError(
                "prior validation receipt does not target this bootstrap "
                f"declaration (id={bootstrap.policy_artifact_id}, "
                f"content_hash={bootstrap.content_hash})"
            )

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def validate(
        self,
        target: StandingReceipt,
        chain: dict[str, StandingReceipt],
    ) -> ValidationReceipt:
        """Validate a single receipt against its parent chain.

        ``chain`` is a lookup of receipt_id → StandingReceipt for every
        ancestor referenced (transitively or directly) by ``target``.
        """

        violations: list[Violation] = []

        # Schema pre-pass (C3) runs first. A malformed envelope can't be
        # parentage-checked sensibly, but we don't early-return — every
        # check still runs so operators see the full picture, not just
        # the first failure (validator_contract §15 framing).
        violations.extend(validate_schema(target))
        violations.extend(self._check_role_standing_mapping(target))
        violations.extend(self._check_chain_integrity(target, chain))
        violations.extend(self._check_parentage(target, chain))
        violations.extend(self._check_subject_derivation(target, chain))
        violations.extend(self._check_compression_path(target, chain))
        violations.extend(self._check_policy_binding(target))

        outcome = self._classify_outcome(target, violations)
        exceptions = self._collect_exceptions(target, outcome)

        return ValidationReceipt(
            validator_id=VALIDATOR_ID,
            validator_version=VALIDATOR_VERSION,
            ruleset_hash=compute_ruleset_hash(),
            policy_registry_hash=self.policy_registry.registry_hash(),
            validated_at=datetime.now(timezone.utc).isoformat(),
            target_receipts=(
                ParentRef(
                    id=target.receipt_id,
                    content_hash=target.compute_content_hash(),
                ),
            ),
            outcome=outcome,
            violations=tuple(violations),
            exceptions=tuple(exceptions),
        )

    # ------------------------------------------------------------------
    # Outcome classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_outcome(
        target: StandingReceipt,
        violations: Iterable[Violation],
    ) -> ValidationOutcome:
        violations = list(violations)
        if not violations:
            if target.exception_class:
                return ValidationOutcome.VALID_WITH_EXCEPTION
            return ValidationOutcome.VALID
        # Order: chain > structural > semantic.
        # Validator_contract §12: any of these → invalid.
        classes = {v.violation_class for v in violations}
        if ViolationClass.CHAIN in classes:
            return ValidationOutcome.INVALID_CHAIN
        if ViolationClass.STRUCTURAL in classes:
            return ValidationOutcome.INVALID_STRUCTURAL
        return ValidationOutcome.INVALID_SEMANTIC

    @staticmethod
    def _collect_exceptions(
        target: StandingReceipt,
        outcome: ValidationOutcome,
    ) -> list[dict[str, object]]:
        if outcome != ValidationOutcome.VALID_WITH_EXCEPTION:
            return []
        return [
            {
                "exception_class": target.exception_class,
                "exception_reason": target.exception_reason,
                "compression_acknowledged": target.compression_acknowledged,
            }
        ]

    # ------------------------------------------------------------------
    # Check: role ↔ standing mapping (validator_contract §4, §11.1)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_role_standing_mapping(
        target: StandingReceipt,
    ) -> list[Violation]:
        # Roles and standing classes are already enums, so unknown
        # values cannot reach here without a TypeError at construction.
        # The remaining check is the role↔standing mapping.
        expected_standing = ROLE_TO_STANDING.get(target.receipt_role)
        if expected_standing is None:
            # validation has no canonical standing — accept any.
            return []
        if target.standing_class != expected_standing:
            return [
                Violation(
                    code=ViolationCode.INVALID_ROLE_STANDING_MAPPING,
                    message=(
                        f"role {target.receipt_role.value} expects standing "
                        f"{expected_standing.value}, got {target.standing_class.value}"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Check: chain integrity (validator_contract §6, §11.3)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_chain_integrity(
        target: StandingReceipt,
        chain: dict[str, StandingReceipt],
    ) -> list[Violation]:
        violations: list[Violation] = []
        for parent_ref in target.parent_receipts:
            if not parent_ref.id or not parent_ref.content_hash:
                violations.append(
                    Violation(
                        code=ViolationCode.PARENT_REFERENCE_ID_ONLY,
                        message="parent reference must include id and content_hash",
                        receipt_id=target.receipt_id,
                        pointers=(parent_ref.id or "<unknown>",),
                    )
                )
                continue
            parent = chain.get(parent_ref.id)
            if parent is None:
                violations.append(
                    Violation(
                        code=ViolationCode.PARENT_NOT_FOUND,
                        message=f"parent receipt {parent_ref.id!r} not found in chain",
                        receipt_id=target.receipt_id,
                        pointers=(parent_ref.id,),
                    )
                )
                continue
            actual_hash = parent.compute_content_hash()
            if actual_hash != parent_ref.content_hash:
                violations.append(
                    Violation(
                        code=ViolationCode.PARENT_CONTENT_HASH_MISMATCH,
                        message=(
                            f"parent {parent_ref.id} content_hash mismatch: "
                            f"declared {parent_ref.content_hash}, actual {actual_hash}"
                        ),
                        receipt_id=target.receipt_id,
                        pointers=(parent_ref.id,),
                    )
                )

        # Cycle detection: walk transitively from target.
        if _has_cycle(target, chain):
            violations.append(
                Violation(
                    code=ViolationCode.PARENT_GRAPH_CYCLE,
                    message=f"parent graph cycle reachable from {target.receipt_id}",
                    receipt_id=target.receipt_id,
                )
            )
        return violations

    # ------------------------------------------------------------------
    # Check: parentage (validator_contract §5.1, §5.4)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_parentage(
        target: StandingReceipt,
        chain: dict[str, StandingReceipt],
    ) -> list[Violation]:
        # Compressed paths are evaluated by _check_compression_path; if a
        # receipt declares an exception_class it is exempt here so the
        # compression path is the *only* place that decision is made.
        if target.exception_class:
            return []

        required = ALLOWED_PARENT_STANDING.get(target.receipt_role)
        if required is None:
            return []
        # Resolve parent standings (skipping ones we couldn't load — those
        # already produced chain violations and we don't want to
        # double-report).
        parent_standings: set[StandingClass] = set()
        for parent_ref in target.parent_receipts:
            parent = chain.get(parent_ref.id)
            if parent is not None:
                parent_standings.add(parent.standing_class)
        # Required parent must appear at least once. Other higher- or
        # same-standing parents may appear as supporting references but
        # cannot substitute (§5.4).
        if not (parent_standings & required):
            return [
                Violation(
                    code=(
                        ViolationCode.MISSING_REQUIRED_PARENT
                        if not target.parent_receipts
                        else ViolationCode.PARENT_STANDING_NOT_ADMISSIBLE
                    ),
                    message=(
                        f"role {target.receipt_role.value} requires a parent with "
                        f"standing in {sorted(s.value for s in required)}; "
                        f"got {sorted(s.value for s in parent_standings) or 'none'}"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Check: subject_derivation (Q2 ratification)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_subject_derivation(
        target: StandingReceipt,
        chain: dict[str, StandingReceipt],
    ) -> list[Violation]:
        # If subject byte-equals at least one parent's subject, no
        # derivation is required (Q2 ratification: same_subject equality
        # *is* the derivation).
        parent_subjects = {
            chain[p.id].subject
            for p in target.parent_receipts
            if p.id in chain
        }
        if target.subject in parent_subjects:
            # Optional derivation block must still validate if present.
            if target.subject_derivation is None:
                return []
            if target.subject_derivation.kind != SubjectDerivationKind.SAME_SUBJECT:
                # Declared a different kind while the subject equals a
                # parent — accept the declared kind on its own merits
                # below.
                pass
            else:
                # same_subject declared; nothing more to check.
                return []

        if target.subject_derivation is None:
            # Subject differs from all parents and no derivation given.
            # Observation/policy_declaration receipts can legitimately
            # introduce new subjects with no parents — only complain if
            # the role requires lineage.
            if ALLOWED_PARENT_STANDING.get(target.receipt_role) is None:
                return []
            return [
                Violation(
                    code=ViolationCode.SUBJECT_LINEAGE_INCOHERENT,
                    message=(
                        "child subject does not match any parent subject and no "
                        "subject_derivation provided"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]

        return _check_derivation_kind(target, target.subject_derivation, chain)

    # ------------------------------------------------------------------
    # Check: compression path (validator_contract §5.3 + Q3 ratification)
    # ------------------------------------------------------------------

    def _check_compression_path(
        self,
        target: StandingReceipt,
        chain: dict[str, StandingReceipt],
    ) -> list[Violation]:
        if not target.exception_class:
            return []
        # Q3 ratification: registry is initially empty; any compressed
        # authorization is INVALID_STRUCTURAL until at least one
        # exception class is added via its own policy_declaration.
        decl = self.policy_registry.get_exception_class(target.exception_class)
        if decl is None:
            return [
                Violation(
                    code=ViolationCode.EXCEPTION_CLASS_NOT_REGISTERED,
                    message=(
                        f"exception_class {target.exception_class!r} is not in "
                        "the ratified registry"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]
        # Direction check: only declared {source → target} pairs are
        # admissible. At ratification time only OBSERVE → AUTHORIZE may
        # be declared.
        violations: list[Violation] = []
        parent_standings = {
            chain[p.id].standing_class
            for p in target.parent_receipts
            if p.id in chain
        }
        source_ok = StandingClass(decl.allowed_source_standing) in parent_standings
        target_ok = target.standing_class == StandingClass(decl.allowed_target_standing)
        if not (source_ok and target_ok):
            violations.append(
                Violation(
                    code=ViolationCode.COMPRESSED_PATH_DIRECTION_NOT_ALLOWED,
                    message=(
                        f"exception_class {target.exception_class!r} declares "
                        f"{decl.allowed_source_standing} → {decl.allowed_target_standing}; "
                        "actual chain does not match"
                    ),
                    receipt_id=target.receipt_id,
                )
            )
        # Required evidence must be present as a named parent-receipt
        # role (we look at parent payload roles for the named evidence
        # types, e.g. 'operator_approval').
        parent_evidence_kinds = {
            chain[p.id].payload.get("evidence_kind")
            for p in target.parent_receipts
            if p.id in chain
        }
        for needed in decl.required_parent_evidence:
            if needed not in parent_evidence_kinds and not _parent_with_role(
                target, chain, needed
            ):
                violations.append(
                    Violation(
                        code=ViolationCode.EXCEPTION_REQUIRED_EVIDENCE_MISSING,
                        message=(
                            f"exception_class {target.exception_class!r} requires "
                            f"parent evidence {needed!r}, not present"
                        ),
                        receipt_id=target.receipt_id,
                    )
                )
        return violations

    # ------------------------------------------------------------------
    # Check: policy binding (validator_contract §8)
    # ------------------------------------------------------------------

    def _check_policy_binding(
        self,
        target: StandingReceipt,
    ) -> list[Violation]:
        binding = target.standing_class in (
            StandingClass.AUTHORIZE,
            StandingClass.EXECUTE,
        )
        if not binding:
            # Non-binding receipts: ontology_version is still mandatory
            # at this layer (§6, §8.3) but nothing else.
            if not target.ontology_version:
                return [
                    Violation(
                        code=ViolationCode.ONTOLOGY_VERSION_MISSING,
                        message="ontology_version is required on every receipt",
                        receipt_id=target.receipt_id,
                    )
                ]
            return []

        violations: list[Violation] = []
        if not target.policy_artifact_id or not target.policy_artifact_hash:
            violations.append(
                Violation(
                    code=ViolationCode.BINDING_RECEIPT_MISSING_POLICY_FIELDS,
                    message=(
                        f"role {target.receipt_role.value} requires "
                        "policy_artifact_id and policy_artifact_hash"
                    ),
                    receipt_id=target.receipt_id,
                )
            )
            return violations
        if not target.ontology_version:
            violations.append(
                Violation(
                    code=ViolationCode.ONTOLOGY_VERSION_MISSING,
                    message="ontology_version is required on binding receipts",
                    receipt_id=target.receipt_id,
                )
            )
        artifact = self.policy_registry.get(target.policy_artifact_id)
        if artifact is None:
            violations.append(
                Violation(
                    code=ViolationCode.POLICY_ARTIFACT_NOT_REGISTERED,
                    message=(
                        f"policy_artifact_id {target.policy_artifact_id!r} not "
                        "in registry"
                    ),
                    receipt_id=target.receipt_id,
                )
            )
            return violations
        if artifact.content_hash != target.policy_artifact_hash:
            violations.append(
                Violation(
                    code=ViolationCode.POLICY_ARTIFACT_HASH_MISMATCH,
                    message=(
                        "policy_artifact_hash mismatch: receipt declares "
                        f"{target.policy_artifact_hash}, registry has "
                        f"{artifact.content_hash}"
                    ),
                    receipt_id=target.receipt_id,
                )
            )
        if (
            target.ontology_version
            and not self.policy_registry.has_ontology_version(target.ontology_version)
        ):
            violations.append(
                Violation(
                    code=ViolationCode.ONTOLOGY_VERSION_NOT_REGISTERED,
                    message=(
                        f"ontology_version {target.ontology_version!r} not registered"
                    ),
                    receipt_id=target.receipt_id,
                )
            )
        return violations


# =============================================================================
# Helpers
# =============================================================================


def _has_cycle(
    start: StandingReceipt,
    chain: dict[str, StandingReceipt],
) -> bool:
    """Detect a cycle in the parent graph reachable from ``start``."""

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        node = chain.get(node_id)
        if node is not None:
            for parent in node.parent_receipts:
                if dfs(parent.id):
                    return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    # The start receipt may not be in chain; walk from its parents.
    for parent in start.parent_receipts:
        if parent.id == start.receipt_id:
            return True
        if dfs(parent.id):
            return True
    return False


def _parent_with_role(
    target: StandingReceipt,
    chain: dict[str, StandingReceipt],
    role_name: str,
) -> bool:
    """Whether any parent of ``target`` has receipt_role equal to ``role_name``."""

    for parent_ref in target.parent_receipts:
        parent = chain.get(parent_ref.id)
        if parent is not None and parent.receipt_role.value == role_name:
            return True
    return False


def _check_derivation_kind(
    target: StandingReceipt,
    derivation: SubjectDerivation,
    chain: dict[str, StandingReceipt],
) -> list[Violation]:
    """Mechanical check per Q2 ratification for a declared derivation kind."""

    parent = chain.get(derivation.parent_id)
    if parent is None:
        return [
            Violation(
                code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                message=(
                    f"subject_derivation references unknown parent {derivation.parent_id!r}"
                ),
                receipt_id=target.receipt_id,
            )
        ]
    # The parent must also appear in parent_receipts, otherwise the
    # derivation is unhitched from chain integrity.
    if not any(p.id == derivation.parent_id for p in target.parent_receipts):
        return [
            Violation(
                code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                message=(
                    "subject_derivation parent must appear in parent_receipts"
                ),
                receipt_id=target.receipt_id,
            )
        ]

    kind = derivation.kind
    if kind == SubjectDerivationKind.SAME_SUBJECT:
        if target.subject != parent.subject:
            return [
                Violation(
                    code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                    message="same_subject requires byte-equal child and parent subjects",
                    receipt_id=target.receipt_id,
                )
            ]
        return []
    if kind == SubjectDerivationKind.INSTANCE_OF:
        # Q2 ratification: at this layer the mechanical check is the
        # hash-linked parentage; class-shaped typing depends on Q2.B
        # which is deferred.
        return []
    if kind == SubjectDerivationKind.AGGREGATION_OF:
        if not derivation.aggregate_parent_ids:
            return [
                Violation(
                    code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                    message="aggregation_of requires aggregate_parent_ids",
                    receipt_id=target.receipt_id,
                )
            ]
        parent_ids = {p.id for p in target.parent_receipts}
        missing = [
            pid for pid in derivation.aggregate_parent_ids if pid not in parent_ids
        ]
        if missing:
            return [
                Violation(
                    code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                    message=(
                        "aggregation_of requires every aggregated parent in "
                        f"parent_receipts; missing: {missing}"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]
        return []
    if kind == SubjectDerivationKind.SCOPE_NARROWING:
        # Strict containment: child ≠ parent (Q2 ratification).
        if target.subject == parent.subject:
            return [
                Violation(
                    code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                    message=(
                        "scope_narrowing requires strict containment; child equals parent"
                    ),
                    receipt_id=target.receipt_id,
                )
            ]
        # Q2.A is deferred. We accept the prefix check as the first
        # concrete mechanical containment test; future kinds (set-membership,
        # declared scope-axis) require Q2.A ratification.
        if derivation.containment_basis in (None, "prefix"):
            if not target.subject.startswith(parent.subject):
                return [
                    Violation(
                        code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                        message=(
                            "scope_narrowing prefix containment failed: child "
                            f"{target.subject!r} is not a prefix-extension of parent "
                            f"{parent.subject!r}"
                        ),
                        receipt_id=target.receipt_id,
                    )
                ]
            return []
        return [
            Violation(
                code=ViolationCode.SUBJECT_DERIVATION_INVALID,
                message=(
                    f"scope_narrowing containment_basis {derivation.containment_basis!r} "
                    "is not yet ratified (Q2.A deferred)"
                ),
                receipt_id=target.receipt_id,
            )
        ]
    # Unreachable — kind is an enum.
    return [
        Violation(
            code=ViolationCode.SUBJECT_DERIVATION_KIND_UNKNOWN,
            message=f"unknown subject_derivation kind {kind!r}",
            receipt_id=target.receipt_id,
        )
    ]
