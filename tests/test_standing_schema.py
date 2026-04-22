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
    BootstrapError,
    Check,
    CheckResultStatus,
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


def _structured_checks() -> dict[str, Check]:
    return {
        name: Check(result=CheckResultStatus.PASS, basis=f"basis for {name}")
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
            name: Check(result=CheckResultStatus.PASS, basis="ok")
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
            obs, checks={"standing_check": Check(CheckResultStatus.PASS, "ok")}
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


class TestSupersessionCeremony:
    def test_v0_2_0_validator_constructs_against_real_chain(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # The on-disk receipt chain is real; if the ceremony works at
        # all it works here.
        StandingChainValidator(policy_registry=loaded_registry)

    def test_ruleset_hash_matches_v0_2_0_declaration(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        bootstrap = loaded_registry.get(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)
        assert bootstrap is not None
        assert bootstrap.frontmatter["expected_ruleset_hash"] == compute_ruleset_hash()

    def test_v0_2_0_supersedes_v0_1_0(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        v020 = loaded_registry.get(VALIDATOR_BOOTSTRAP_POLICY_ARTIFACT_ID)
        assert v020 is not None
        assert v020.supersedes == "decision.validator.v0_1_0"

    def test_missing_prior_validation_receipt_raises_bootstrap_error(
        self, isolated_decisions: Path
    ) -> None:
        # Delete the prior validation receipt; v0.2.0 bootstrap fails closed.
        (isolated_decisions / "_validations" / "decision.validator.v0_2_0.json").unlink()
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="prior validation receipt not found"):
            StandingChainValidator(policy_registry=registry)

    def test_missing_prior_validation_receipt_path_field_raises(
        self, isolated_decisions: Path
    ) -> None:
        # Strip prior_validation_receipt_path from the v0.2.0 frontmatter.
        v020_path = isolated_decisions / "validator-v0_2_0.md"
        text = v020_path.read_text(encoding="utf-8")
        text = text.replace(
            "prior_validation_receipt_path: _validations/decision.validator.v0_2_0.json\n",
            "",
        )
        v020_path.write_text(text, encoding="utf-8")
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(
            BootstrapError, match="prior_validation_receipt_path"
        ):
            StandingChainValidator(policy_registry=registry)

    def test_forged_prior_receipt_with_wrong_target_hash_raises(
        self, isolated_decisions: Path
    ) -> None:
        # Forge: receipt that targets a *different* content_hash.
        receipt_path = (
            isolated_decisions / "_validations" / "decision.validator.v0_2_0.json"
        )
        receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
        receipt["target_receipts"] = [
            {
                "id": "decision.validator.v0_2_0",
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
            isolated_decisions / "_validations" / "decision.validator.v0_2_0.json"
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
            isolated_decisions / "_validations" / "decision.validator.v0_2_0.json"
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
            isolated_decisions / "_validations" / "decision.validator.v0_2_0.json"
        )
        receipt_path.write_bytes(b"this is not valid JSON {{{")
        registry = load_decisions_directory(isolated_decisions)
        with pytest.raises(BootstrapError, match="not valid JSON"):
            StandingChainValidator(policy_registry=registry)

    def test_v0_2_0_validator_can_validate_real_receipt_chain(
        self, loaded_registry: PolicyRegistry
    ) -> None:
        # End-to-end: the ceremony succeeded → validator runs → produces
        # the expected new ruleset_hash on emitted ValidationReceipts.
        validator = StandingChainValidator(policy_registry=loaded_registry)
        obs = _observation()
        result = validator.validate(obs, {})
        assert result.validator_version == VALIDATOR_VERSION
        assert result.validator_version == "0.2.0"
        assert result.ruleset_hash == compute_ruleset_hash()
        assert result.outcome == ValidationOutcome.VALID
