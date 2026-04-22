# SPDX-License-Identifier: Apache-2.0
"""Standing-class chain validator acceptance tests.

Tests are grouped by the ratified decision artifact whose acceptance
criteria they enforce. Each group's docstring names the
``policy_artifact_id`` so future audits can grep by id rather than
prose.

Hidden-test framing (the falsification target for C2):
> Does the repo gain a way to say "this receipt chain is inadmissible"
> that it could not say before?

Yes. ``test_observation_to_action_chain_is_rejected`` is the smallest
demonstration; the rest of the file maps the rejection vocabulary
against the ratified acceptance criteria.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.standing import (
    BOOTSTRAP_POLICY_ARTIFACT_IDS,
    AuthorizationVerdict,
    BootstrapError,
    Check,
    CheckResultStatus,
    ParentRef,
    PolicyRegistry,
    ReceiptRole,
    StandingChainValidator,
    StandingClass,
    StandingReceipt,
    SubjectDerivation,
    SubjectDerivationKind,
    VALIDATOR_VERSION,
    ValidationOutcome,
    ViolationClass,
    ViolationCode,
    load_decisions_directory,
)
from governor.standing.kernel_bridge import (
    to_kernel_envelope,
    validation_to_kernel_envelope,
)
from governor.standing.policy_registry import (
    ExceptionClassDeclaration,
    PolicyArtifact,
)
from governor.standing.validator import (
    VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID,
    compute_ruleset_hash,
)
from receipt_kernel.envelope import seal_envelope, verify_envelope_hash


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = REPO_ROOT / "docs" / "doctrine" / "decisions"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def loaded_registry() -> PolicyRegistry:
    """Registry loaded from the real ratified decision artifacts on disk."""

    return load_decisions_directory(DECISIONS_DIR)


@pytest.fixture
def validator(loaded_registry: PolicyRegistry) -> StandingChainValidator:
    return StandingChainValidator(policy_registry=loaded_registry)


def _observation(receipt_id: str = "rcpt_obs_001", subject: str = "host123") -> StandingReceipt:
    return StandingReceipt(
        receipt_id=receipt_id,
        receipt_role=ReceiptRole.OBSERVATION,
        standing_class=StandingClass.OBSERVE,
        subject=subject,
        ontology_version="gov-doctrine-v1",
        producer="nq",
        created_at="2026-04-22T00:00:00Z",
    )


def _interpretation(parent: StandingReceipt) -> StandingReceipt:
    return StandingReceipt(
        receipt_id="rcpt_int_001",
        receipt_role=ReceiptRole.INTERPRETATION,
        standing_class=StandingClass.INTERPRET,
        subject=parent.subject,
        ontology_version="gov-doctrine-v1",
        producer="night_shift",
        created_at="2026-04-22T00:00:00Z",
        parent_receipts=(
            ParentRef(id=parent.receipt_id, content_hash=parent.compute_content_hash()),
        ),
    )


def _recommendation(parent: StandingReceipt) -> StandingReceipt:
    return StandingReceipt(
        receipt_id="rcpt_rec_001",
        receipt_role=ReceiptRole.RECOMMENDATION,
        standing_class=StandingClass.RECOMMEND,
        subject=parent.subject,
        ontology_version="gov-doctrine-v1",
        producer="night_shift",
        created_at="2026-04-22T00:00:00Z",
        parent_receipts=(
            ParentRef(id=parent.receipt_id, content_hash=parent.compute_content_hash()),
        ),
    )


def _structured_checks() -> dict[str, Check]:
    """The four required AUTHORIZE checks per validator_contract §9."""

    return {
        "standing_check": Check(
            result=CheckResultStatus.PASS, basis="parent has recommendatory standing"
        ),
        "admissibility_check": Check(
            result=CheckResultStatus.PASS, basis="evidence chain complete"
        ),
        "scope_check": Check(
            result=CheckResultStatus.PASS, basis="within declared scope"
        ),
        "budget_check": Check(
            result=CheckResultStatus.PASS, basis="under per-session budget"
        ),
    }


def _authorization(
    parent: StandingReceipt,
    *,
    policy_artifact_id: str,
    policy_artifact_hash: str,
    checks: dict[str, Check] | None = None,
) -> StandingReceipt:
    return StandingReceipt(
        receipt_id="rcpt_auth_001",
        receipt_role=ReceiptRole.AUTHORIZATION,
        standing_class=StandingClass.AUTHORIZE,
        subject=parent.subject,
        ontology_version="gov-doctrine-v1",
        producer="governor",
        created_at="2026-04-22T00:00:00Z",
        parent_receipts=(
            ParentRef(id=parent.receipt_id, content_hash=parent.compute_content_hash()),
        ),
        policy_artifact_id=policy_artifact_id,
        policy_artifact_hash=policy_artifact_hash,
        verdict=AuthorizationVerdict.PERMIT,
        checks=checks if checks is not None else _structured_checks(),
    )


def _action(parent: StandingReceipt) -> StandingReceipt:
    return StandingReceipt(
        receipt_id="rcpt_act_001",
        receipt_role=ReceiptRole.ACTION,
        standing_class=StandingClass.EXECUTE,
        subject=parent.subject,
        ontology_version="gov-doctrine-v1",
        producer="runtime",
        created_at="2026-04-22T00:00:00Z",
        parent_receipts=(
            ParentRef(id=parent.receipt_id, content_hash=parent.compute_content_hash()),
        ),
        policy_artifact_id=parent.policy_artifact_id,
        policy_artifact_hash=parent.policy_artifact_hash,
    )


# =============================================================================
# Bootstrap (decision.validator.v0_1_0 acceptance criteria)
# =============================================================================


class TestBootstrap:
    """Acceptance criteria for ``decision.validator.v0_1_0``.

    The bootstrap doc is the only declaration permitted to lack a prior
    validation receipt. Every other admissibility property of the
    validator depends on it.
    """

    def test_bootstrap_doc_is_loaded_from_disk(self, loaded_registry: PolicyRegistry) -> None:
        assert loaded_registry.has(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)

    def test_validator_constructs_when_bootstrap_present(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        StandingChainValidator(policy_registry=loaded_registry)

    def test_validator_refuses_when_bootstrap_missing(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        del loaded_registry.artifacts[VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID]
        with pytest.raises(BootstrapError, match="bootstrap"):
            StandingChainValidator(policy_registry=loaded_registry)

    @pytest.mark.parametrize("missing_anchor", BOOTSTRAP_POLICY_ARTIFACT_IDS)
    def test_validator_refuses_when_q_anchor_missing(
        self, loaded_registry: PolicyRegistry, missing_anchor: str
    ) -> None:
        del loaded_registry.artifacts[missing_anchor]
        with pytest.raises(BootstrapError, match="Q1.Q4 anchors"):
            StandingChainValidator(policy_registry=loaded_registry)

    def test_validator_refuses_on_ruleset_hash_mismatch(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        original = loaded_registry.artifacts[VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID]
        broken_fm = dict(original.frontmatter)
        broken_fm["expected_ruleset_hash"] = "sha256:" + "0" * 64
        loaded_registry.artifacts[VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID] = PolicyArtifact(
            policy_artifact_id=original.policy_artifact_id,
            ontology_version=original.ontology_version,
            ratified_at=original.ratified_at,
            ratifier=original.ratifier,
            supersedes=original.supersedes,
            content_hash=original.content_hash,
            source_path=original.source_path,
            frontmatter=broken_fm,
        )
        with pytest.raises(BootstrapError, match="ruleset_hash mismatch"):
            StandingChainValidator(policy_registry=loaded_registry)

    def test_validator_refuses_on_version_mismatch(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        original = loaded_registry.artifacts[VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID]
        broken_fm = dict(original.frontmatter)
        broken_fm["validator_version"] = "9.9.9"
        loaded_registry.artifacts[VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID] = PolicyArtifact(
            policy_artifact_id=original.policy_artifact_id,
            ontology_version=original.ontology_version,
            ratified_at=original.ratified_at,
            ratifier=original.ratifier,
            supersedes=original.supersedes,
            content_hash=original.content_hash,
            source_path=original.source_path,
            frontmatter=broken_fm,
        )
        with pytest.raises(BootstrapError, match="validator_version mismatch"):
            StandingChainValidator(policy_registry=loaded_registry)

    def test_ruleset_hash_is_deterministic(self) -> None:
        # Two calls produce identical output (hashes of canonical JSON).
        assert compute_ruleset_hash() == compute_ruleset_hash()


# =============================================================================
# Q1 acceptance (decision.validator_integration.q1)
# =============================================================================


class TestQ1KernelComposition:
    """Q1 acceptance criteria — receipts ride receipt_kernel ledger.

    Per ratified Q1 (Option A), standing-class receipts emit through
    libs/receipt_kernel. The acceptance criteria below come from the
    ratification's §"Acceptance criteria (frozen for validator
    implementation)".
    """

    def test_re_hash_matches_stored_hash(self) -> None:
        # Q1 acceptance #1: a receipt's canonical body hashes to its
        # stored content_hash.
        obs = _observation()
        h1 = obs.compute_content_hash()
        # Recomputing yields the same hash.
        assert obs.compute_content_hash() == h1

    def test_parent_content_hash_resolves_against_chain(
        self, validator: StandingChainValidator
    ) -> None:
        # Q1 acceptance #2: parent_receipts[].content_hash references
        # resolve against the same chain the child is committed to.
        obs = _observation()
        interp = _interpretation(obs)
        chain = {obs.receipt_id: obs}
        result = validator.validate(interp, chain)
        assert result.outcome == ValidationOutcome.VALID

    def test_kernel_envelope_round_trips(self) -> None:
        # Q1 acceptance #3 (proxy): receipts can be carried through a
        # kernel envelope; sealed envelope verifies. The full
        # kernel-invariants check belongs to the receipt_kernel test
        # suite; here we only assert the bridge produces a valid sealed
        # envelope with the standing receipt in payload.
        obs = _observation()
        env = to_kernel_envelope(
            obs,
            stage="COLLECT",
            policy_id="agent_gov.standing_chain_validator",
            policy_version=VALIDATOR_VERSION,
            stage_graph_id="default",
        )
        sealed = seal_envelope(env)
        assert verify_envelope_hash(sealed)
        assert sealed["payload"]["receipt_role"] == "observation"
        assert sealed["payload"]["standing_class"] == "OBSERVE"

    def test_display_metadata_does_not_change_content_hash(self) -> None:
        # Q1 acceptance #4: display metadata cannot change the receipt
        # hash when edited.
        obs_a = _observation()
        obs_b = StandingReceipt(
            receipt_id=obs_a.receipt_id,
            receipt_role=obs_a.receipt_role,
            standing_class=obs_a.standing_class,
            subject=obs_a.subject,
            ontology_version=obs_a.ontology_version,
            producer=obs_a.producer,
            created_at=obs_a.created_at,
            display_metadata={"operator_note": "looks suspicious"},
        )
        assert obs_a.compute_content_hash() == obs_b.compute_content_hash()


# =============================================================================
# Q2 acceptance (decision.validator_integration.q2)
# =============================================================================


class TestQ2SubjectDerivation:
    """Q2 acceptance criteria — closed subject_derivation enum.

    Acceptance criteria from the ratification's §"Acceptance criteria
    (frozen for validator implementation)".
    """

    def test_same_subject_implicit_when_byte_equal(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation(subject="host123")
        interp = _interpretation(obs)
        assert interp.subject == obs.subject
        result = validator.validate(interp, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.VALID

    def test_unknown_kind_rejected_at_dataclass_layer(self) -> None:
        # Q2 acceptance #1: unknown kinds → INVALID_STRUCTURAL.
        # Because SubjectDerivationKind is a closed enum, attempting to
        # construct one with an unknown value raises ValueError; this
        # is the structural rejection happening at the type boundary.
        with pytest.raises(ValueError):
            SubjectDerivationKind("not_a_real_kind")

    def test_scope_narrowing_strict_containment(
        self, validator: StandingChainValidator
    ) -> None:
        # Q2 acceptance #2 + #4: mechanical check; equal subject under
        # scope_narrowing → INVALID_STRUCTURAL.
        obs = _observation(subject="scope:host")
        bad = StandingReceipt(
            receipt_id="rcpt_int_bad",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject="scope:host",  # same as parent
            ontology_version="gov-doctrine-v1",
            producer="night_shift",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
            ),
            subject_derivation=SubjectDerivation(
                kind=SubjectDerivationKind.SCOPE_NARROWING,
                parent_id=obs.receipt_id,
            ),
        )
        result = validator.validate(bad, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.INVALID_STRUCTURAL
        codes = {v.code for v in result.violations}
        assert ViolationCode.SUBJECT_DERIVATION_INVALID in codes

    def test_scope_narrowing_prefix_extension_accepted(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation(subject="scope:host")
        good = StandingReceipt(
            receipt_id="rcpt_int_good",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject="scope:host:disk0",
            ontology_version="gov-doctrine-v1",
            producer="night_shift",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
            ),
            subject_derivation=SubjectDerivation(
                kind=SubjectDerivationKind.SCOPE_NARROWING,
                parent_id=obs.receipt_id,
                containment_basis="prefix",
            ),
        )
        result = validator.validate(good, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.VALID

    def test_aggregation_requires_all_parents_present(
        self, validator: StandingChainValidator
    ) -> None:
        obs1 = _observation(receipt_id="rcpt_obs_a", subject="host_a")
        obs2 = _observation(receipt_id="rcpt_obs_b", subject="host_b")
        bad = StandingReceipt(
            receipt_id="rcpt_int_agg",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject="cluster:ab",
            ontology_version="gov-doctrine-v1",
            producer="night_shift",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs1.receipt_id, content_hash=obs1.compute_content_hash()),
                # obs2 referenced in derivation but NOT in parent_receipts
            ),
            subject_derivation=SubjectDerivation(
                kind=SubjectDerivationKind.AGGREGATION_OF,
                parent_id=obs1.receipt_id,
                aggregate_parent_ids=(obs1.receipt_id, obs2.receipt_id),
            ),
        )
        result = validator.validate(
            bad, {obs1.receipt_id: obs1, obs2.receipt_id: obs2}
        )
        assert result.outcome == ValidationOutcome.INVALID_STRUCTURAL


# =============================================================================
# Q3 acceptance (decision.validator_integration.q3)
# =============================================================================


class TestQ3ExceptionClassRegistry:
    """Q3 acceptance criteria — closed governed registry, initially empty.

    The empty initial state is **the** ratified behavior. Tests pin it
    as a first-class state so a future "bug fix" cannot quietly widen
    the gate.
    """

    def test_empty_registry_is_initial_state(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        assert loaded_registry.exception_classes == {}

    def test_compressed_authorization_rejected_by_empty_registry(
        self, validator: StandingChainValidator
    ) -> None:
        # Q3 acceptance #1: unknown exception_class → INVALID_STRUCTURAL.
        # With empty registry, every exception_class is unknown.
        obs = _observation()
        compressed = StandingReceipt(
            receipt_id="rcpt_auth_compressed",
            receipt_role=ReceiptRole.AUTHORIZATION,
            standing_class=StandingClass.AUTHORIZE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="governor",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
            ),
            policy_artifact_id="decision.validator_integration.q1",
            policy_artifact_hash=loaded_registry_hash(),
            verdict=AuthorizationVerdict.PERMIT,
            exception_class="emergency_compression",
            exception_reason="operator override",
            compression_acknowledged=True,
        )
        result = validator.validate(compressed, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.INVALID_STRUCTURAL
        codes = {v.code for v in result.violations}
        assert ViolationCode.EXCEPTION_CLASS_NOT_REGISTERED in codes

    def test_compressed_admitted_when_class_declared_with_evidence(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # Q3 acceptance #4: registered class with all required parent
        # evidence present → VALID_WITH_EXCEPTION.
        loaded_registry.add_exception_class(
            ExceptionClassDeclaration(
                exception_class="operator_emergency",
                allowed_source_standing="OBSERVE",
                allowed_target_standing="AUTHORIZE",
                required_parent_evidence=("operator_approval",),
                scope_limits=("emergency",),
                expiry_or_review_date="2027-01-01T00:00:00Z",
                declared_by="decision.test.exception_operator_emergency",
            )
        )
        validator = StandingChainValidator(policy_registry=loaded_registry)
        obs = _observation()
        # The "operator_approval" evidence is supplied as another
        # observation-class receipt whose payload tags it as such.
        approval = StandingReceipt(
            receipt_id="rcpt_obs_approval",
            receipt_role=ReceiptRole.OBSERVATION,
            standing_class=StandingClass.OBSERVE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="operator",
            created_at="2026-04-22T00:00:00Z",
            payload={"evidence_kind": "operator_approval"},
        )
        compressed = StandingReceipt(
            receipt_id="rcpt_auth_compressed_ok",
            receipt_role=ReceiptRole.AUTHORIZATION,
            standing_class=StandingClass.AUTHORIZE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="governor",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
                ParentRef(id=approval.receipt_id, content_hash=approval.compute_content_hash()),
            ),
            policy_artifact_id="decision.validator_integration.q1",
            policy_artifact_hash=loaded_registry.get(
                "decision.validator_integration.q1"
            ).content_hash,
            verdict=AuthorizationVerdict.PERMIT,
            exception_class="operator_emergency",
            exception_reason="disk failing now",
            compression_acknowledged=True,
            checks=_structured_checks(),
        )
        result = validator.validate(
            compressed,
            {obs.receipt_id: obs, approval.receipt_id: approval},
        )
        assert result.outcome == ValidationOutcome.VALID_WITH_EXCEPTION

    def test_compressed_rejected_when_required_evidence_missing(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # Q3 acceptance #4: missing required evidence → INVALID_SEMANTIC,
        # not VALID_WITH_EXCEPTION.
        loaded_registry.add_exception_class(
            ExceptionClassDeclaration(
                exception_class="operator_emergency",
                allowed_source_standing="OBSERVE",
                allowed_target_standing="AUTHORIZE",
                required_parent_evidence=("operator_approval",),
                scope_limits=("emergency",),
                expiry_or_review_date="2027-01-01T00:00:00Z",
                declared_by="decision.test.exception_operator_emergency",
            )
        )
        validator = StandingChainValidator(policy_registry=loaded_registry)
        obs = _observation()
        compressed = StandingReceipt(
            receipt_id="rcpt_auth_compressed_noev",
            receipt_role=ReceiptRole.AUTHORIZATION,
            standing_class=StandingClass.AUTHORIZE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="governor",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
            ),
            policy_artifact_id="decision.validator_integration.q1",
            policy_artifact_hash=loaded_registry.get(
                "decision.validator_integration.q1"
            ).content_hash,
            verdict=AuthorizationVerdict.PERMIT,
            exception_class="operator_emergency",
            exception_reason="forgot to attach approval",
            compression_acknowledged=True,
            checks=_structured_checks(),
        )
        result = validator.validate(compressed, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.INVALID_SEMANTIC
        codes = {v.code for v in result.violations}
        assert ViolationCode.EXCEPTION_REQUIRED_EVIDENCE_MISSING in codes


# =============================================================================
# Q4 acceptance (decision.validator_integration.q4)
# =============================================================================


class TestQ4ValidatorProvenance:
    """Q4 acceptance criteria — every validator run emits a validation
    receipt with all mandatory fields populated."""

    def test_every_validator_run_produces_validation_receipt(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        result = validator.validate(obs, {})
        # Q4 acceptance #1: all mandatory fields populated.
        assert result.validator_id == "agent_gov.standing_chain_validator"
        assert result.validator_version == VALIDATOR_VERSION
        assert result.ruleset_hash.startswith("sha256:")
        assert result.policy_registry_hash.startswith("sha256:")
        assert result.validated_at  # ISO 8601 UTC timestamp
        assert len(result.target_receipts) == 1
        assert result.outcome in ValidationOutcome
        # violations and exceptions are tuples (possibly empty).
        assert isinstance(result.violations, tuple)
        assert isinstance(result.exceptions, tuple)

    def test_validation_receipt_round_trips_through_kernel_bridge(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        result = validator.validate(obs, {})
        env = validation_to_kernel_envelope(
            result,
            stage="EVALUATE",
            policy_id="agent_gov.standing_chain_validator",
            policy_version=VALIDATOR_VERSION,
            stage_graph_id="default",
        )
        sealed = seal_envelope(env)
        assert verify_envelope_hash(sealed)
        assert sealed["payload"]["receipt_role"] == "validation"
        assert (
            sealed["payload"]["validation_receipt"]["validator_version"]
            == VALIDATOR_VERSION
        )

    def test_ruleset_hash_in_receipt_matches_compute_ruleset_hash(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        result = validator.validate(obs, {})
        assert result.ruleset_hash == compute_ruleset_hash()


# =============================================================================
# The hidden test + chatty's six-test ring
# =============================================================================


class TestRejectionVocabulary:
    """The capability the repo gains by this commit.

    Each test names one thing the validator can now reject that it
    couldn't before, with the keyed violation code.
    """

    def test_minimal_valid_chain_accepted(
        self, validator: StandingChainValidator, loaded_registry: PolicyRegistry
    ) -> None:
        # observation → interpretation → recommendation → authorization → action
        obs = _observation()
        interp = _interpretation(obs)
        rec = _recommendation(interp)
        q1 = loaded_registry.get("decision.validator_integration.q1")
        auth = _authorization(
            rec,
            policy_artifact_id=q1.policy_artifact_id,
            policy_artifact_hash=q1.content_hash,
        )
        act = _action(auth)
        chain = {
            obs.receipt_id: obs,
            interp.receipt_id: interp,
            rec.receipt_id: rec,
            auth.receipt_id: auth,
        }
        for receipt in (obs, interp, rec, auth, act):
            result = validator.validate(receipt, chain)
            assert result.outcome == ValidationOutcome.VALID, (
                f"{receipt.receipt_id} rejected: {[v.to_dict() for v in result.violations]}"
            )

    def test_observation_to_action_chain_is_rejected(
        self, validator: StandingChainValidator
    ) -> None:
        # The hidden test: action whose only parent is an observation.
        # validator_contract §5.4 forbidden parentage.
        obs = _observation()
        bad_action = StandingReceipt(
            receipt_id="rcpt_act_bad",
            receipt_role=ReceiptRole.ACTION,
            standing_class=StandingClass.EXECUTE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="runtime",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash=obs.compute_content_hash()),
            ),
            policy_artifact_id="decision.validator_integration.q1",
            policy_artifact_hash="sha256:" + "0" * 64,
        )
        result = validator.validate(bad_action, {obs.receipt_id: obs})
        assert result.outcome in (
            ValidationOutcome.INVALID_STRUCTURAL,
            ValidationOutcome.INVALID_SEMANTIC,
        )
        codes = {v.code for v in result.violations}
        assert ViolationCode.PARENT_STANDING_NOT_ADMISSIBLE in codes
        # Every violation has a class assigned (no stringly-typed bucket).
        for v in result.violations:
            assert v.violation_class in ViolationClass

    def test_parent_content_hash_mismatch_is_rejected(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        interp = StandingReceipt(
            receipt_id="rcpt_int_tampered",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="night_shift",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(
                ParentRef(id=obs.receipt_id, content_hash="sha256:" + "f" * 64),
            ),
        )
        result = validator.validate(interp, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.INVALID_CHAIN
        codes = {v.code for v in result.violations}
        assert ViolationCode.PARENT_CONTENT_HASH_MISMATCH in codes

    def test_parent_not_in_chain_is_rejected(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        interp = _interpretation(obs)
        # chain missing obs
        result = validator.validate(interp, {})
        assert result.outcome == ValidationOutcome.INVALID_CHAIN
        codes = {v.code for v in result.violations}
        assert ViolationCode.PARENT_NOT_FOUND in codes

    def test_unknown_policy_artifact_is_rejected(
        self, validator: StandingChainValidator
    ) -> None:
        obs = _observation()
        interp = _interpretation(obs)
        rec = _recommendation(interp)
        auth = _authorization(
            rec,
            policy_artifact_id="decision.does_not_exist",
            policy_artifact_hash="sha256:" + "0" * 64,
        )
        chain = {
            obs.receipt_id: obs,
            interp.receipt_id: interp,
            rec.receipt_id: rec,
        }
        result = validator.validate(auth, chain)
        assert result.outcome == ValidationOutcome.INVALID_SEMANTIC
        codes = {v.code for v in result.violations}
        assert ViolationCode.POLICY_ARTIFACT_NOT_REGISTERED in codes

    def test_violation_codes_carry_classes(self) -> None:
        from governor.standing.types import VIOLATION_CLASS_FOR_CODE

        for code in ViolationCode:
            assert code in VIOLATION_CLASS_FOR_CODE


# =============================================================================
# Helper to read registry hash without re-constructing validator
# =============================================================================


def loaded_registry_hash() -> str:
    """Return the on-disk registry hash. Used in compressed-path test
    fixtures where we want a syntactically valid policy_artifact_hash
    even when the binding will be rejected for other reasons."""

    return load_decisions_directory(DECISIONS_DIR).registry_hash()
