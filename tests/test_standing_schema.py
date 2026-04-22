# SPDX-License-Identifier: Apache-2.0
"""Standing-class envelope schema acceptance + supersession tests (C3).

Tests are grouped by the rule they enforce:

- :class:`TestSchemaAcceptance` — receipts that should pass schema
- :class:`TestSchemaRejection` — runtime schema violations (post-construction)
- :class:`TestEnvelopeRoundtrip` — to_dict → from_dict byte-identical
- :class:`TestHostileInput` — ``StandingReceipt.from_dict`` rejects
  malformed input with typed violations bundled in
  :class:`EnvelopeParseError`
- :class:`TestSupersessionCeremony` — Q4 supersession enforced; the
  bootstrap exemption is non-transitive
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from governor.standing import (
    AUTHORIZE_REQUIRED_CHECKS,
    AuthorizationVerdict,
    BasisRecord,
    BootstrapError,
    CONTINUITY_CLAIMABLE_ROLES,
    Check,
    CheckBasis,
    CheckResultStatus,
    ContinuityBasis,
    EnvelopeParseError,
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
    ViolationCode,
    canonical_json,
    load_decisions_directory,
    validate_schema,
)
from governor.standing.types import (
    REQUIRED_COMMON_FIELDS,
    STANDING_RECEIPT_ENVELOPE_KEYS,
)
from governor.standing.validator import (
    VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID,
    compute_ruleset_hash,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = REPO_ROOT / "docs" / "doctrine" / "decisions"


# =============================================================================
# Fixtures
# =============================================================================


def _basis(name: str) -> CheckBasis:
    return CheckBasis(
        summary=f"basis for {name}",
        rule_id=f"validator_contract.9.{name}",
        inspectable_refs=(f"ref:{name}",),
    )


def _structured_checks() -> dict[str, Check]:
    return {
        name: Check(result=CheckResultStatus.PASS, basis=_basis(name))
        for name in AUTHORIZE_REQUIRED_CHECKS
    }


def _observation(receipt_id: str = "rcpt_obs_001") -> StandingReceipt:
    return StandingReceipt(
        receipt_id=receipt_id,
        receipt_role=ReceiptRole.OBSERVATION,
        standing_class=StandingClass.OBSERVE,
        subject="host:abc",
        ontology_version="gov-doctrine-v1",
        producer="nq",
        created_at="2026-04-22T00:00:00Z",
    )


def _authorization(parent: StandingReceipt, **overrides) -> StandingReceipt:
    defaults = dict(
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
        policy_artifact_id="decision.validator_integration.q1",
        policy_artifact_hash="sha256:" + "0" * 64,
        verdict=AuthorizationVerdict.PERMIT,
        checks=_structured_checks(),
    )
    defaults.update(overrides)
    return StandingReceipt(**defaults)


# =============================================================================
# Schema acceptance
# =============================================================================


class TestSchemaAcceptance:
    def test_observation_passes_schema(self) -> None:
        assert validate_schema(_observation()) == []

    def test_authorize_with_full_checks_passes(self) -> None:
        obs = _observation()
        auth = _authorization(obs)
        assert validate_schema(auth) == []

    def test_authorize_with_partial_checks_fails(self) -> None:
        obs = _observation()
        partial = {
            name: Check(result=CheckResultStatus.PASS, basis=_basis(name))
            for name in ("standing_check", "scope_check")
        }
        auth = _authorization(obs, checks=partial)
        violations = validate_schema(auth)
        codes = [v.code for v in violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MISSING in codes
        # One missing-check violation per missing check, in alphabetical order.
        missing_names = sorted(v.pointers[0] for v in violations)
        assert missing_names == ["admissibility_check", "budget_check"]


# =============================================================================
# Schema rejection (runtime, post-construction)
# =============================================================================


class TestSchemaRejection:
    def test_bad_hash_format_on_self_content_hash(self) -> None:
        obs = _observation()
        # Construct a receipt with a non-canonical content_hash. dataclass
        # accepts any string here; the schema validator catches it at
        # runtime.
        obs2 = StandingReceipt(
            receipt_id=obs.receipt_id,
            receipt_role=obs.receipt_role,
            standing_class=obs.standing_class,
            subject=obs.subject,
            ontology_version=obs.ontology_version,
            producer=obs.producer,
            created_at=obs.created_at,
            content_hash="not-a-hash",
        )
        violations = validate_schema(obs2)
        assert any(v.code == ViolationCode.HASH_FORMAT_INVALID for v in violations)

    def test_bad_hash_format_on_parent_ref(self) -> None:
        # ParentRef itself doesn't validate hash format — the schema
        # validator is the runtime gate.
        obs = _observation()
        bad_parent = ParentRef(id="rcpt_obs_001", content_hash="garbage")
        receipt = StandingReceipt(
            receipt_id="rcpt_int_bad",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="x",
            created_at="2026-04-22T00:00:00Z",
            parent_receipts=(bad_parent,),
        )
        violations = validate_schema(receipt)
        assert any(v.code == ViolationCode.HASH_FORMAT_INVALID for v in violations)

    def test_malformed_check_value_in_dict(self) -> None:
        # In-code construction can stash a non-Check value into the dict.
        # The schema validator catches that.
        obs = _observation()
        bad_checks = dict(_structured_checks())
        bad_checks["scope_check"] = "this is not a Check"  # type: ignore[assignment]
        auth = _authorization(obs, checks=bad_checks)
        violations = validate_schema(auth)
        assert any(
            v.code == ViolationCode.AUTHORIZATION_CHECK_MALFORMED for v in violations
        )

    def test_validator_outcome_invalid_structural_when_check_missing(
        self,
    ) -> None:
        # End-to-end via StandingChainValidator: schema violations make
        # AUTHORIZE outcome INVALID_STRUCTURAL.
        registry = load_decisions_directory(DECISIONS_DIR)
        validator = StandingChainValidator(policy_registry=registry)
        obs = _observation()
        auth = _authorization(
            obs,
            checks={
                "standing_check": Check(
                    result=CheckResultStatus.PASS, basis=_basis("standing_check")
                )
            },
        )
        result = validator.validate(auth, {obs.receipt_id: obs})
        assert result.outcome == ValidationOutcome.INVALID_STRUCTURAL


# =============================================================================
# Envelope roundtrip
# =============================================================================


class TestEnvelopeRoundtrip:
    @pytest.mark.parametrize(
        "factory",
        [
            lambda: _observation(),
            lambda: StandingReceipt(
                receipt_id="rcpt_int",
                receipt_role=ReceiptRole.INTERPRETATION,
                standing_class=StandingClass.INTERPRET,
                subject="host:x",
                ontology_version="gov-doctrine-v1",
                producer="ns",
                created_at="2026-04-22T00:00:00Z",
                parent_receipts=(
                    ParentRef(id="rcpt_obs", content_hash="sha256:" + "a" * 64),
                ),
                subject_derivation=SubjectDerivation(
                    kind=SubjectDerivationKind.SAME_SUBJECT,
                    parent_id="rcpt_obs",
                ),
                payload={"selected_hypothesis": "checkpoint starvation"},
            ),
            lambda: _authorization(_observation()),
        ],
        ids=["observation", "interpretation_with_derivation", "authorization"],
    )
    def test_canonical_body_byte_identical_after_roundtrip(self, factory) -> None:
        original = factory()
        body_before = canonical_json(original.canonical_body())
        roundtripped = StandingReceipt.from_dict(original.to_dict())
        body_after = canonical_json(roundtripped.canonical_body())
        assert body_before == body_after

    def test_content_hash_preserved_through_roundtrip(self) -> None:
        original = _observation()
        h = original.compute_content_hash()
        # Caller stamps content_hash; roundtrip preserves it.
        with_hash = StandingReceipt(
            receipt_id=original.receipt_id,
            receipt_role=original.receipt_role,
            standing_class=original.standing_class,
            subject=original.subject,
            ontology_version=original.ontology_version,
            producer=original.producer,
            created_at=original.created_at,
            content_hash=h,
        )
        roundtripped = StandingReceipt.from_dict(with_hash.to_dict())
        assert roundtripped.content_hash == h
        assert roundtripped.compute_content_hash() == h


# =============================================================================
# Hostile-input discipline (from_dict)
# =============================================================================


class TestHostileInput:
    def test_non_mapping_input_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict("just a string")  # type: ignore[arg-type]
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.INVALID_FIELD_TYPE in codes

    def test_unknown_field_rejected(self) -> None:
        good = _observation().to_dict()
        good["evil_extra_field"] = "smuggled"
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        violations = exc_info.value.violations
        assert any(
            v.code == ViolationCode.UNKNOWN_FIELD_IN_ENVELOPE for v in violations
        )
        assert any("evil_extra_field" in v.message for v in violations)

    @pytest.mark.parametrize("missing_key", sorted(REQUIRED_COMMON_FIELDS))
    def test_missing_required_common_field_rejected(self, missing_key: str) -> None:
        good = _observation().to_dict()
        del good[missing_key]
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.MISSING_REQUIRED_COMMON_FIELD in codes

    def test_wrong_type_for_common_field_rejected(self) -> None:
        good = _observation().to_dict()
        good["receipt_id"] = 12345  # type: ignore[assignment]
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.INVALID_FIELD_TYPE in codes

    def test_unknown_receipt_role_rejected(self) -> None:
        good = _observation().to_dict()
        good["receipt_role"] = "wishful_thinking"
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.UNKNOWN_RECEIPT_ROLE in codes

    def test_bad_parent_ref_hash_rejected(self) -> None:
        good = StandingReceipt(
            receipt_id="rcpt_int",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject="x",
            ontology_version="gov-doctrine-v1",
            producer="x",
            created_at="2026-04-22T00:00:00Z",
        ).to_dict()
        good["parent_receipts"] = [{"id": "rcpt_obs", "content_hash": "garbage"}]
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.HASH_FORMAT_INVALID in codes

    def test_parent_ref_id_only_rejected(self) -> None:
        good = StandingReceipt(
            receipt_id="rcpt_int",
            receipt_role=ReceiptRole.INTERPRETATION,
            standing_class=StandingClass.INTERPRET,
            subject="x",
            ontology_version="gov-doctrine-v1",
            producer="x",
            created_at="2026-04-22T00:00:00Z",
        ).to_dict()
        good["parent_receipts"] = [{"id": "rcpt_obs"}]
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        # Either INVALID_FIELD_TYPE (no content_hash key) or
        # HASH_FORMAT_INVALID — both are typed rejections, not silent
        # acceptance.
        codes = [v.code for v in exc_info.value.violations]
        assert any(
            c
            in (
                ViolationCode.HASH_FORMAT_INVALID,
                ViolationCode.PARENT_REFERENCE_ID_ONLY,
                ViolationCode.INVALID_FIELD_TYPE,
            )
            for c in codes
        )

    def test_unknown_subject_derivation_kind_rejected(self) -> None:
        good = _observation().to_dict()
        good["subject_derivation"] = {
            "kind": "fancy_new_kind",
            "parent_id": "rcpt_obs",
        }
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.SUBJECT_DERIVATION_KIND_UNKNOWN in codes

    def test_envelope_key_set_is_closed(self) -> None:
        # The closed envelope is the schema-discipline anchor; this test
        # makes sure adding a field requires updating the constant.
        receipt = _observation()
        body = receipt.to_dict()
        for key in body:
            assert key in STANDING_RECEIPT_ENVELOPE_KEYS, (
                f"to_dict produced unknown key {key!r}; either add it to "
                "STANDING_RECEIPT_ENVELOPE_KEYS or stop emitting it"
            )


# =============================================================================
# Supersession ceremony — Q4 in practice
# =============================================================================


@pytest.fixture
def loaded_registry() -> PolicyRegistry:
    return load_decisions_directory(DECISIONS_DIR)


@pytest.fixture
def isolated_decisions(tmp_path: Path) -> Path:
    """Copy the real decisions directory into tmp so tests can mutate it."""

    dest = tmp_path / "decisions"
    shutil.copytree(DECISIONS_DIR, dest)
    return dest


def _active_bootstrap_filename() -> str:
    """Filename of the .md for the validator's *current* bootstrap.

    Computed from VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID so the test
    suite tracks the active version automatically when the validator
    bumps. (e.g. ``decision.validator.v0_3_0`` → ``validator-v0_3_0.md``)
    """

    suffix = VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID.split(".")[-1]
    return f"validator-{suffix}.md"


def _active_receipt_filename() -> str:
    return f"{VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID}.json"


class TestSupersessionCeremony:
    """Tests assert the *active bootstrap* (whatever VALIDATOR_VERSION
    currently is) succeeds against a real on-disk supersession chain
    and fails closed against forged/missing receipts. Tests are
    version-agnostic so v0.4.0+ pick them up automatically."""

    def test_validator_constructs_against_real_chain(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        StandingChainValidator(policy_registry=loaded_registry)

    def test_ruleset_hash_matches_active_bootstrap_declaration(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        bootstrap = loaded_registry.get(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)
        assert bootstrap is not None
        assert bootstrap.frontmatter["expected_ruleset_hash"] == compute_ruleset_hash()

    def test_active_bootstrap_supersedes_immediate_predecessor(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # Active bootstrap must declare a non-null `supersedes` (v0.1.0
        # is the only declaration permitted to lack one).
        active = loaded_registry.get(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)
        assert active is not None
        assert active.supersedes is not None, (
            "active bootstrap must supersede its predecessor; only v0.1.0 "
            "may lack a supersedes pointer"
        )
        # The named predecessor must itself be in the registry.
        assert loaded_registry.get(active.supersedes) is not None

    def test_full_supersession_chain_is_walkable_to_v0_1_0(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # Walk supersedes pointers from the active bootstrap. Must
        # terminate at v0.1.0 (the only one with supersedes=None) and
        # contain no cycles.
        seen: set[str] = set()
        current = loaded_registry.get(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)
        assert current is not None
        while current.supersedes is not None:
            assert current.policy_artifact_id not in seen, "supersession cycle"
            seen.add(current.policy_artifact_id)
            current = loaded_registry.get(current.supersedes)
            assert current is not None
        assert current.policy_artifact_id == "decision.validator.v0_1_0"

    def test_missing_prior_validation_receipt_raises_bootstrap_error(
        self, isolated_decisions: Path
    ) -> None:
        (isolated_decisions / "_validations" / _active_receipt_filename()).unlink()
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="prior validation receipt not found"):
            StandingChainValidator(policy_registry=registry)

    def test_missing_prior_validation_receipt_path_field_raises(
        self, isolated_decisions: Path
    ) -> None:
        bootstrap_path = isolated_decisions / _active_bootstrap_filename()
        text = bootstrap_path.read_text(encoding="utf-8")
        text = text.replace(
            f"prior_validation_receipt_path: _validations/{_active_receipt_filename()}\n",
            "",
        )
        bootstrap_path.write_text(text, encoding="utf-8")
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="prior_validation_receipt_path"):
            StandingChainValidator(policy_registry=registry)

    def test_forged_prior_receipt_with_wrong_target_hash_raises(
        self, isolated_decisions: Path
    ) -> None:
        receipt_path = (
            isolated_decisions / "_validations" / _active_receipt_filename()
        )
        receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
        receipt["target_receipts"] = [
            {
                "id": VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID,
                "content_hash": "sha256:" + "0" * 64,
            }
        ]
        receipt_path.write_bytes(canonical_json(receipt))
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="does not target this bootstrap"):
            StandingChainValidator(policy_registry=registry)

    def test_forged_prior_receipt_with_wrong_validator_id_raises(
        self, isolated_decisions: Path
    ) -> None:
        receipt_path = (
            isolated_decisions / "_validations" / _active_receipt_filename()
        )
        receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
        receipt["validator_id"] = "rogue.validator.v9.9.9"
        receipt_path.write_bytes(canonical_json(receipt))
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="validator_id mismatch"):
            StandingChainValidator(policy_registry=registry)

    def test_forged_prior_receipt_with_wrong_outcome_raises(
        self, isolated_decisions: Path
    ) -> None:
        receipt_path = (
            isolated_decisions / "_validations" / _active_receipt_filename()
        )
        receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
        receipt["outcome"] = "INVALID_STRUCTURAL"
        receipt_path.write_bytes(canonical_json(receipt))
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="outcome must be VALID"):
            StandingChainValidator(policy_registry=registry)

    def test_malformed_prior_receipt_json_raises(
        self, isolated_decisions: Path
    ) -> None:
        receipt_path = (
            isolated_decisions / "_validations" / _active_receipt_filename()
        )
        receipt_path.write_bytes(b"this is not valid JSON {{{")
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="not valid JSON"):
            StandingChainValidator(policy_registry=registry)

    def test_validator_can_validate_real_receipt_chain(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        validator = StandingChainValidator(policy_registry=loaded_registry)
        obs = _observation()
        result = validator.validate(obs, {})
        assert result.validator_version == VALIDATOR_VERSION
        assert result.ruleset_hash == compute_ruleset_hash()
        assert result.outcome == ValidationOutcome.VALID


# =============================================================================
# Check.basis discipline (C4)
# =============================================================================


class TestCheckBasisDiscipline:
    """Falsification target for C4: ``{"result":"pass","basis":"seemed fine"}``
    no longer slides through. Basis must be structured + inspectable."""

    def test_string_basis_seemed_fine_is_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            Check.from_dict({"result": "pass", "basis": "seemed fine"})
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes
        # Message must point at the C4 rule, not just say "wrong type".
        messages = " ".join(v.message for v in exc_info.value.violations)
        assert "structured" in messages or "C4" in messages

    def test_basis_missing_summary_is_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            CheckBasis.from_dict(
                {"rule_id": "x.y.z", "inspectable_refs": ["ref"]}
            )
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes

    def test_basis_missing_rule_id_is_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            CheckBasis.from_dict(
                {"summary": "ok", "inspectable_refs": ["ref"]}
            )
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes

    def test_basis_empty_inspectable_refs_is_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            CheckBasis.from_dict(
                {"summary": "ok", "rule_id": "x.y.z", "inspectable_refs": []}
            )
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes

    def test_basis_inspectable_ref_must_be_non_empty_string(self) -> None:
        with pytest.raises(EnvelopeParseError):
            CheckBasis.from_dict(
                {"summary": "ok", "rule_id": "x.y.z", "inspectable_refs": [""]}
            )
        with pytest.raises(EnvelopeParseError):
            CheckBasis.from_dict(
                {"summary": "ok", "rule_id": "x.y.z", "inspectable_refs": [123]}
            )

    def test_basis_unknown_field_rejected(self) -> None:
        with pytest.raises(EnvelopeParseError) as exc_info:
            CheckBasis.from_dict(
                {
                    "summary": "ok",
                    "rule_id": "x.y.z",
                    "inspectable_refs": ["r"],
                    "smuggled_authority": "no",
                }
            )
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes

    def test_basis_round_trips(self) -> None:
        original = CheckBasis(
            summary="parent has recommendatory standing",
            rule_id="validator_contract.5.1.authorization",
            inspectable_refs=("rcpt_rec_001", "rcpt_rec_002"),
        )
        assert CheckBasis.from_dict(original.to_dict()) == original

# =============================================================================
# Continuity basis discipline (C5, validator_contract §10)
# =============================================================================


def _continuity_basis() -> ContinuityBasis:
    """A well-formed continuity_basis block — all four sub-bases populated."""

    return ContinuityBasis(
        identity_basis=BasisRecord(
            summary="device id stable across reboots",
            rule_id="continuity.identity.host_uuid",
            inspectable_refs=("host:abc:uuid",),
        ),
        provenance_basis=BasisRecord(
            summary="lineage traced to bootstrap snapshot",
            rule_id="continuity.provenance.snapshot_chain",
            inspectable_refs=("snapshot:t0", "snapshot:t1"),
        ),
        evidence_basis=BasisRecord(
            summary="metric continuity confirmed across window",
            rule_id="continuity.evidence.metric_window",
            inspectable_refs=("rcpt_obs_metric_window",),
        ),
        operator_confidence_basis=BasisRecord(
            summary="operator approval recorded",
            rule_id="continuity.operator.approval",
            inspectable_refs=("rcpt_obs_approval",),
        ),
    )


class TestContinuityBasisDiscipline:
    """C5 falsification targets — chatty's "brutal and boring" set:

    - summary-only basis rejected
    - empty inspectable_refs rejected
    - continuity-preserving claim missing one required basis field rejected
    - continuity-preserving claim with basis prose but no provenance
      structure rejected
    - role gate enforced (presence-as-claim is not unrestricted)
    - presence-as-claim cannot be loophole'd via null/empty
    """

    def test_well_formed_block_round_trips(self) -> None:
        cb = _continuity_basis()
        assert ContinuityBasis.from_dict(cb.to_dict()) == cb

    def test_action_receipt_with_continuity_basis_passes_schema(
        self,
    ) -> None:
        obs = _observation()
        action = StandingReceipt(
            receipt_id="rcpt_act_001",
            receipt_role=ReceiptRole.ACTION,
            standing_class=StandingClass.EXECUTE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="runtime",
            created_at="2026-04-22T00:00:00Z",
            continuity_basis=_continuity_basis(),
        )
        assert validate_schema(action) == []

    @pytest.mark.parametrize(
        "ineligible_role,ineligible_standing",
        [
            (ReceiptRole.OBSERVATION, StandingClass.OBSERVE),
            (ReceiptRole.INTERPRETATION, StandingClass.INTERPRET),
            (ReceiptRole.POLICY_DECLARATION, StandingClass.POLICY_DECLARE),
            (ReceiptRole.VALIDATION, StandingClass.OBSERVE),
        ],
    )
    def test_role_gate_rejects_ineligible_roles(
        self, ineligible_role: ReceiptRole, ineligible_standing: StandingClass
    ) -> None:
        receipt = StandingReceipt(
            receipt_id="rcpt_role_gate",
            receipt_role=ineligible_role,
            standing_class=ineligible_standing,
            subject="host:x",
            ontology_version="gov-doctrine-v1",
            producer="x",
            created_at="2026-04-22T00:00:00Z",
            continuity_basis=_continuity_basis(),
        )
        violations = validate_schema(receipt)
        codes = [v.code for v in violations]
        assert ViolationCode.CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE in codes

    def test_eligible_roles_match_doctrine(self) -> None:
        # Sanity-pin the role set so a future "while we're here" tweak
        # gets caught by a test, not by an incident.
        assert CONTINUITY_CLAIMABLE_ROLES == frozenset(
            {
                ReceiptRole.RECOMMENDATION,
                ReceiptRole.AUTHORIZATION,
                ReceiptRole.ACTION,
            }
        )

    def test_explicit_null_block_rejected(self) -> None:
        good = _observation().to_dict()
        good["continuity_basis"] = None
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes
        msg = " ".join(v.message for v in exc_info.value.violations)
        assert "presence-as-claim" in msg or "explicit null" in msg

    def test_empty_block_rejected(self) -> None:
        good = _observation().to_dict()
        good["continuity_basis"] = {}
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    @pytest.mark.parametrize(
        "missing_field",
        [
            "identity_basis",
            "provenance_basis",
            "evidence_basis",
            "operator_confidence_basis",
        ],
    )
    def test_partial_block_rejected(self, missing_field: str) -> None:
        block = _continuity_basis().to_dict()
        del block[missing_field]
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        violations = exc_info.value.violations
        codes = [v.code for v in violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes
        # Message names the missing field — operators can fix without grep.
        msg = " ".join(v.message for v in violations)
        assert missing_field in msg

    def test_string_sub_basis_rejected(self) -> None:
        # The "basis prose but no provenance structure" target.
        block = _continuity_basis().to_dict()
        block["evidence_basis"] = "evidence chain looks fine"
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    def test_sub_basis_empty_inspectable_refs_rejected(self) -> None:
        block = _continuity_basis().to_dict()
        block["evidence_basis"]["inspectable_refs"] = []
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    def test_sub_basis_missing_summary_rejected(self) -> None:
        block = _continuity_basis().to_dict()
        del block["evidence_basis"]["summary"]
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    def test_sub_basis_unknown_field_rejected(self) -> None:
        block = _continuity_basis().to_dict()
        block["identity_basis"]["smuggled_authority"] = "no"
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    def test_unknown_top_level_field_in_block_rejected(self) -> None:
        block = _continuity_basis().to_dict()
        block["chronicle_basis"] = block["identity_basis"]  # cousin field
        good = _observation().to_dict()
        good["continuity_basis"] = block
        with pytest.raises(EnvelopeParseError) as exc_info:
            StandingReceipt.from_dict(good)
        codes = [v.code for v in exc_info.value.violations]
        assert ViolationCode.CONTINUITY_BASIS_MALFORMED in codes

    def test_no_continuity_claim_round_trips(self) -> None:
        # Absence is no-claim. Roundtrip must preserve the absence —
        # ``continuity_basis`` does not appear in canonical body.
        receipt = _observation()
        body = receipt.canonical_body()
        assert "continuity_basis" not in body
        # And from_dict accepts the absence.
        roundtripped = StandingReceipt.from_dict(receipt.to_dict())
        assert roundtripped.continuity_basis is None


    def test_in_code_check_with_string_basis_caught_by_schema_pre_pass(
        self) -> None:
        # Belt-and-suspenders: even if somebody constructs Check with a
        # non-CheckBasis basis in code (Python doesn't enforce dataclass
        # type annotations at runtime), the schema pre-pass catches it.
        # Test the schema function directly — going through full
        # validate() also hashes the target which can't canonicalize a
        # malformed receipt.
        bad_check = Check(result=CheckResultStatus.PASS, basis="seemed fine")  # type: ignore[arg-type]
        obs = _observation()
        bad_auth = StandingReceipt(
            receipt_id="rcpt_auth_bad",
            receipt_role=ReceiptRole.AUTHORIZATION,
            standing_class=StandingClass.AUTHORIZE,
            subject=obs.subject,
            ontology_version="gov-doctrine-v1",
            producer="governor",
            created_at="2026-04-22T00:00:00Z",
            checks={"standing_check": bad_check},
        )
        violations = validate_schema(bad_auth)
        codes = [v.code for v in violations]
        assert ViolationCode.AUTHORIZATION_CHECK_MALFORMED in codes
        # Message should point at C4, not just say "wrong type".
        messages = " ".join(v.message for v in violations)
        assert "CheckBasis" in messages or "C4" in messages
