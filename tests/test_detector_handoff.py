# SPDX-License-Identifier: Apache-2.0
"""Tests for detector_handoff.py — controller decision → gate receipt."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from governor.detector_handoff import (
    CLOCK_SKEW_TOLERANCE_S,
    DEFAULT_TTL_MS,
    SCHEMA_VERSION,
    ControllerAction,
    DetectorHandoffGate,
    ErrorKind,
    FailureKind,
    FinalStatus,
    HandoffConfig,
    HandoffResult,
    HandoffValidationError,
    HandoffRecommendation,
    OracleResult,
    build_escalation_bundle,
    build_evidence_bundle,
    build_gate_config,
    generate_nonce,
    map_verdict,
    validate_bindings,
    validate_schema,
)
from governor.gate_receipt import GateReceiptSystem


# =============================================================================
# Fixtures
# =============================================================================


def _make_decision(
    *,
    schema: str = SCHEMA_VERSION,
    task_id: str = "test-task-1",
    task_class: str = "citation",
    namespace: str = "pypi",
    prompt_hash: str = "a" * 64,
    output_hash: str = "",
    request_nonce: str = "",
    oracle_profile: str = "pypi_locked",
    model_id: str = "Qwen/Qwen2.5-3B-Instruct",
    controller_action: str = "FAST_PATH",
    final_status: str = "CLEAN",
    tau_milliunits: int = 50,
    fork_risk_milliunits: int = 80,
    decision_ttl_ms: int = DEFAULT_TTL_MS,
    oracle_checks: list[dict[str, Any]] | None = None,
    failures: list[dict[str, Any]] | None = None,
    local_tokens: int = 312,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a valid controller_decision dict."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    decision: dict[str, Any] = {
        "schema": schema,
        "task": {
            "task_id": task_id,
            "task_class": task_class,
            "namespace": namespace,
            "prompt_hash": prompt_hash,
        },
        "local_model": {
            "model_id": model_id,
            "quant": "none",
            "decoding": {"temperature": 0.7, "retry_temperature": 0.0, "seed": 42},
            "controller_version": "1.0",
        },
        "decision": {
            "fork_risk": {
                "metric": "prompt_min_margin",
                "value_milliunits": fork_risk_milliunits,
                "window_k": 16,
            },
            "tau_milliunits": tau_milliunits,
            "controller_action": controller_action,
            "final_status": final_status,
            "decision_ttl_ms": decision_ttl_ms,
            "handoff_recommendation": "NONE",
        },
        "evidence": {
            "candidates": ["pypi:requests==2.31.0"],
            "oracle_checks": oracle_checks or [
                {"oracle": "pypi_json_api", "query": "requests==2.31.0", "result": "PASS", "latency_ms": 142}
            ],
            "failures": failures or [],
            "controller_trace_ref": "data/runs/test/controller_details.jsonl",
        },
        "economics": {
            "local_tokens_spent": local_tokens,
            "retry_tokens_spent": 0,
            "retry_count": 0,
            "latency_ms": 1840,
            "oracle_latency_ms": 142,
        },
        "created_at": created_at,
    }

    if output_hash:
        decision["task"]["output_hash"] = output_hash
    if request_nonce:
        decision["task"]["request_nonce"] = request_nonce
    if oracle_profile:
        decision["task"]["oracle_profile"] = oracle_profile

    return decision


@pytest.fixture
def receipt_system(tmp_path: Path) -> GateReceiptSystem:
    """Create a real GateReceiptSystem in a temp directory."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    return GateReceiptSystem(gov_dir)


@pytest.fixture
def gate(receipt_system: GateReceiptSystem) -> DetectorHandoffGate:
    """Create a DetectorHandoffGate with a real receipt system."""
    return DetectorHandoffGate(receipt_system=receipt_system)


# =============================================================================
# Schema validation
# =============================================================================


class TestValidateSchema:

    def test_valid_decision(self):
        decision = _make_decision()
        errors = validate_schema(decision)
        assert errors == []

    def test_unknown_schema_version(self):
        decision = _make_decision(schema="controller_decision/v99")
        errors = validate_schema(decision)
        assert len(errors) == 1
        assert "Unknown schema" in errors[0]

    def test_missing_schema(self):
        decision = _make_decision()
        del decision["schema"]
        errors = validate_schema(decision)
        assert len(errors) == 1
        assert "Unknown schema" in errors[0]

    def test_missing_required_sections(self):
        decision = {"schema": SCHEMA_VERSION}
        errors = validate_schema(decision)
        assert any("task" in e for e in errors)
        assert any("decision" in e for e in errors)
        assert any("evidence" in e for e in errors)

    def test_missing_task_fields(self):
        decision = _make_decision()
        decision["task"] = {"task_id": "x"}
        errors = validate_schema(decision)
        assert any("task_class" in e for e in errors)
        assert any("namespace" in e for e in errors)

    def test_missing_decision_fields(self):
        decision = _make_decision()
        decision["decision"] = {}
        errors = validate_schema(decision)
        assert any("fork_risk" in e for e in errors)
        assert any("tau_milliunits" in e for e in errors)
        assert any("controller_action" in e for e in errors)
        assert any("final_status" in e for e in errors)

    def test_missing_fork_risk_value(self):
        decision = _make_decision()
        decision["decision"]["fork_risk"] = {"metric": "prompt_min_margin"}
        errors = validate_schema(decision)
        assert any("value_milliunits" in e for e in errors)

    def test_invalid_controller_action(self):
        decision = _make_decision(controller_action="YOLO")
        errors = validate_schema(decision)
        assert any("Invalid controller_action" in e for e in errors)

    def test_invalid_final_status(self):
        decision = _make_decision(final_status="VIBES")
        errors = validate_schema(decision)
        assert any("Invalid final_status" in e for e in errors)

    def test_invalid_oracle_result(self):
        decision = _make_decision(oracle_checks=[
            {"oracle": "pypi", "query": "x", "result": "maybe", "latency_ms": 100}
        ])
        errors = validate_schema(decision)
        assert any("oracle_checks[0].result" in e for e in errors)


class TestStopInvariant:

    def test_stop_with_clean_is_paradox(self):
        decision = _make_decision(controller_action="STOP", final_status="CLEAN")
        errors = validate_schema(decision)
        assert any("STOP invariant" in e for e in errors)

    def test_stop_with_low_margin_recovered_is_paradox(self):
        decision = _make_decision(controller_action="STOP", final_status="LOW_MARGIN_RECOVERED")
        errors = validate_schema(decision)
        assert any("STOP invariant" in e for e in errors)

    def test_stop_with_confident_wrong_ok(self):
        decision = _make_decision(controller_action="STOP", final_status="CONFIDENT_WRONG")
        errors = validate_schema(decision)
        assert errors == []

    def test_stop_with_knowledge_boundary_ok(self):
        decision = _make_decision(controller_action="STOP", final_status="KNOWLEDGE_BOUNDARY")
        errors = validate_schema(decision)
        assert errors == []

    def test_stop_with_oracle_error_ok(self):
        decision = _make_decision(controller_action="STOP", final_status="ORACLE_ERROR")
        errors = validate_schema(decision)
        assert errors == []


# =============================================================================
# Binding validation
# =============================================================================


class TestValidateBindings:

    def test_no_bindings_required(self):
        decision = _make_decision()
        errors = validate_bindings(decision)
        assert errors == []

    def test_nonce_match(self):
        nonce = "abc123"
        decision = _make_decision(request_nonce=nonce)
        errors = validate_bindings(decision, expected_nonce=nonce)
        assert errors == []

    def test_nonce_mismatch(self):
        decision = _make_decision(request_nonce="old_nonce")
        errors = validate_bindings(decision, expected_nonce="new_nonce")
        assert len(errors) == 1
        assert "Nonce mismatch" in errors[0]

    def test_nonce_missing_in_file(self):
        decision = _make_decision()
        errors = validate_bindings(decision, expected_nonce="expected")
        assert len(errors) == 1
        assert "Nonce mismatch" in errors[0]

    def test_output_hash_match(self):
        output = b"hello world"
        h = hashlib.sha256(output).hexdigest()
        decision = _make_decision(output_hash=h)
        errors = validate_bindings(decision, actual_output=output)
        assert errors == []

    def test_output_hash_mismatch(self):
        """Negative test: mutated output_hash should hard-block."""
        output = b"hello world"
        decision = _make_decision(output_hash="0" * 64)
        errors = validate_bindings(decision, actual_output=output)
        assert len(errors) == 1
        assert "Output hash mismatch" in errors[0]

    def test_output_hash_not_in_file_skips(self):
        """If decision doesn't include output_hash, no validation."""
        output = b"hello world"
        decision = _make_decision()
        errors = validate_bindings(decision, actual_output=output)
        assert errors == []

    def test_ttl_valid(self):
        decision = _make_decision(decision_ttl_ms=60000)
        errors = validate_bindings(decision)
        assert errors == []

    def test_ttl_expired(self):
        """Negative test: expired TTL should hard-block."""
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        decision = _make_decision(created_at=old_time, decision_ttl_ms=30000)
        errors = validate_bindings(decision)
        assert len(errors) == 1
        assert "expired" in errors[0]

    def test_future_created_at(self):
        future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        decision = _make_decision(created_at=future)
        errors = validate_bindings(decision)
        assert any("future" in e for e in errors)

    def test_future_within_tolerance(self):
        near_future = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        decision = _make_decision(created_at=near_future)
        errors = validate_bindings(decision)
        assert errors == []

    def test_oracle_profile_enforcement_match(self):
        config = HandoffConfig(oracle_profile_requirements={"citation": "pypi_locked"})
        decision = _make_decision(task_class="citation", oracle_profile="pypi_locked")
        errors = validate_bindings(decision, config=config)
        assert errors == []

    def test_oracle_profile_enforcement_mismatch(self):
        config = HandoffConfig(oracle_profile_requirements={"citation": "pypi_locked"})
        decision = _make_decision(task_class="citation", oracle_profile="code_standard")
        errors = validate_bindings(decision, config=config)
        assert len(errors) == 1
        assert "Oracle profile mismatch" in errors[0]

    def test_oracle_profile_no_requirement(self):
        config = HandoffConfig(oracle_profile_requirements={"codegen": "code_standard"})
        decision = _make_decision(task_class="citation", oracle_profile="anything")
        errors = validate_bindings(decision, config=config)
        assert errors == []


# =============================================================================
# Verdict mapping
# =============================================================================


class TestVerdictMapping:

    @pytest.mark.parametrize("status,expected", [
        ("CLEAN", "pass"),
        ("LOW_MARGIN_RECOVERED", "pass"),
        ("CONFIDENT_WRONG", "block"),
        ("KNOWLEDGE_BOUNDARY", "block"),
        ("ORACLE_ERROR", "block"),
    ])
    def test_verdict_mapping(self, status: str, expected: str):
        decision = _make_decision(final_status=status)
        # Fix STOP invariant for block statuses
        if expected == "block" and status != "ORACLE_ERROR":
            decision["decision"]["controller_action"] = "STOP"
        verdict = map_verdict(decision)
        assert verdict == expected

    def test_oracle_error_override_for_allowed_class(self):
        config = HandoffConfig(oracle_error_override_classes=["qa"])
        decision = _make_decision(final_status="ORACLE_ERROR", task_class="qa")
        verdict = map_verdict(decision, config)
        assert verdict == "warn"

    def test_oracle_error_no_override_for_unlisted_class(self):
        config = HandoffConfig(oracle_error_override_classes=["qa"])
        decision = _make_decision(final_status="ORACLE_ERROR", task_class="citation")
        verdict = map_verdict(decision, config)
        assert verdict == "block"

    def test_oracle_error_no_override_empty_list(self):
        config = HandoffConfig(oracle_error_override_classes=[])
        decision = _make_decision(final_status="ORACLE_ERROR")
        verdict = map_verdict(decision, config)
        assert verdict == "block"


# =============================================================================
# Evidence bundle + gate config
# =============================================================================


class TestBuildEvidenceBundle:

    def test_contains_decision_fields(self):
        decision = _make_decision()
        bundle = build_evidence_bundle(decision)
        assert "controller_action" in bundle
        assert "final_status" in bundle
        assert "tau_milliunits" in bundle
        assert "fork_risk" in bundle

    def test_contains_evidence_fields(self):
        decision = _make_decision()
        bundle = build_evidence_bundle(decision)
        assert "candidates" in bundle
        assert "oracle_checks" in bundle
        assert "controller_trace_ref" in bundle

    def test_contains_economics_fields(self):
        decision = _make_decision()
        bundle = build_evidence_bundle(decision)
        assert "local_tokens_spent" in bundle
        assert "retry_tokens_spent" in bundle
        assert "latency_ms" in bundle

    def test_no_escalation_tokens_spent(self):
        decision = _make_decision()
        bundle = build_evidence_bundle(decision)
        assert "escalation_tokens_spent" not in bundle


class TestBuildGateConfig:

    def test_basic_shape(self):
        decision = _make_decision()
        gc = build_gate_config(decision)
        assert gc["gate"] == "detector_handoff"
        assert gc["schema"] == SCHEMA_VERSION
        assert gc["enforcement"] == "gated"

    def test_shadow_mode(self):
        config = HandoffConfig(shadow_mode=True)
        decision = _make_decision()
        gc = build_gate_config(decision, config)
        assert gc["enforcement"] == "shadow"

    def test_oracle_error_override_logged(self):
        config = HandoffConfig(oracle_error_override_classes=["qa"])
        decision = _make_decision(final_status="ORACLE_ERROR", task_class="qa")
        gc = build_gate_config(decision, config)
        assert gc.get("oracle_error_override") == "warn"
        assert gc.get("oracle_error_override_class") == "qa"


# =============================================================================
# Escalation bundle
# =============================================================================


class TestBuildEscalationBundle:

    def test_contains_failure_evidence(self):
        decision = _make_decision(
            final_status="CONFIDENT_WRONG",
            controller_action="STOP",
            failures=[{"kind": "oracle_fail", "message": "not found", "attempt": 1}],
        )
        decision["decision"]["handoff_recommendation"] = "ESCALATE_REMOTE"
        bundle = build_escalation_bundle(decision)
        assert bundle["reason"] == "CONFIDENT_WRONG"
        assert bundle["handoff_recommendation"] == "ESCALATE_REMOTE"
        assert "failures" in bundle
        assert "oracle_checks" in bundle
        assert "local_model" in bundle

    def test_includes_receipt_id_when_available(self):
        decision = _make_decision(final_status="CONFIDENT_WRONG", controller_action="STOP")
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "abc123"
        bundle = build_escalation_bundle(decision, mock_receipt)
        assert bundle["receipt_id"] == "abc123"

    def test_no_receipt_id_without_receipt(self):
        decision = _make_decision(final_status="CONFIDENT_WRONG", controller_action="STOP")
        bundle = build_escalation_bundle(decision)
        assert "receipt_id" not in bundle

    def test_includes_task_context(self):
        decision = _make_decision(
            final_status="KNOWLEDGE_BOUNDARY",
            controller_action="STOP",
            task_class="citation",
            namespace="doi",
            oracle_profile="doi_locked",
        )
        bundle = build_escalation_bundle(decision)
        assert bundle["task_class"] == "citation"
        assert bundle["namespace"] == "doi"
        assert bundle["oracle_profile"] == "doi_locked"


# =============================================================================
# DetectorHandoffGate (facade)
# =============================================================================


class TestDetectorHandoffGate:

    def test_process_clean_decision(self, gate: DetectorHandoffGate):
        decision = _make_decision(final_status="CLEAN")
        result = gate.process(decision)
        assert result.verdict == "pass"
        assert result.final_status == "CLEAN"
        assert result.receipt is not None
        assert result.escalation_bundle is None
        assert result.validation_errors == []

    def test_process_block_decision(self, gate: DetectorHandoffGate):
        decision = _make_decision(
            final_status="CONFIDENT_WRONG",
            controller_action="STOP",
        )
        decision["decision"]["handoff_recommendation"] = "ESCALATE_REMOTE"
        result = gate.process(decision)
        assert result.verdict == "block"
        assert result.receipt is not None
        assert result.escalation_bundle is not None
        assert result.escalation_bundle["reason"] == "CONFIDENT_WRONG"

    def test_process_knowledge_boundary(self, gate: DetectorHandoffGate):
        decision = _make_decision(
            final_status="KNOWLEDGE_BOUNDARY",
            controller_action="STOP",
        )
        result = gate.process(decision)
        assert result.verdict == "block"
        assert result.escalation_bundle is not None

    def test_process_low_margin_recovered(self, gate: DetectorHandoffGate):
        decision = _make_decision(
            final_status="LOW_MARGIN_RECOVERED",
            controller_action="LOW_MARGIN_RETRY",
        )
        result = gate.process(decision)
        assert result.verdict == "pass"
        assert result.escalation_bundle is None

    def test_process_oracle_error_default_block(self, gate: DetectorHandoffGate):
        decision = _make_decision(
            final_status="ORACLE_ERROR",
            controller_action="STOP",
        )
        result = gate.process(decision)
        assert result.verdict == "block"

    def test_schema_validation_failure_blocks(self, gate: DetectorHandoffGate):
        decision = _make_decision(schema="controller_decision/v99")
        result = gate.process(decision)
        assert result.verdict == "block"
        assert len(result.validation_errors) > 0
        assert result.receipt is None

    def test_stop_clean_invariant_blocks(self, gate: DetectorHandoffGate):
        decision = _make_decision(controller_action="STOP", final_status="CLEAN")
        result = gate.process(decision)
        assert result.verdict == "block"
        assert any("STOP invariant" in e for e in result.validation_errors)

    def test_nonce_mismatch_blocks(self, gate: DetectorHandoffGate):
        """Negative test: stale nonce should hard-block."""
        decision = _make_decision(request_nonce="old_nonce")
        result = gate.process(decision, expected_nonce="new_nonce")
        assert result.verdict == "block"
        assert any("Nonce mismatch" in e for e in result.validation_errors)
        # Receipt should still be emitted (recording the block)
        assert result.receipt is not None

    def test_output_hash_mismatch_blocks(self, gate: DetectorHandoffGate):
        """Negative test: mutated output_hash should hard-block."""
        output = b"actual model output"
        decision = _make_decision(output_hash="0" * 64)
        result = gate.process(decision, actual_output=output)
        assert result.verdict == "block"
        assert any("Output hash mismatch" in e for e in result.validation_errors)

    def test_expired_ttl_blocks(self, gate: DetectorHandoffGate):
        """Negative test: expired TTL should hard-block."""
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        decision = _make_decision(created_at=old_time, decision_ttl_ms=30000)
        result = gate.process(decision)
        assert result.verdict == "block"
        assert any("expired" in e for e in result.validation_errors)


class TestShadowMode:

    def test_shadow_mode_overrides_block_to_pass(self, receipt_system: GateReceiptSystem):
        config = HandoffConfig(shadow_mode=True)
        gate = DetectorHandoffGate(receipt_system=receipt_system, config=config)
        decision = _make_decision(
            final_status="CONFIDENT_WRONG",
            controller_action="STOP",
        )
        result = gate.process(decision)
        assert result.verdict == "pass"
        assert result.shadow is True
        assert result.effective_verdict == "block"
        assert result.escalation_bundle is not None  # still built

    def test_shadow_mode_pass_stays_pass(self, receipt_system: GateReceiptSystem):
        config = HandoffConfig(shadow_mode=True)
        gate = DetectorHandoffGate(receipt_system=receipt_system, config=config)
        decision = _make_decision(final_status="CLEAN")
        result = gate.process(decision)
        assert result.verdict == "pass"
        assert result.shadow is False

    def test_shadow_mode_receipt_records_effective_verdict(self, receipt_system: GateReceiptSystem):
        config = HandoffConfig(shadow_mode=True)
        gate = DetectorHandoffGate(receipt_system=receipt_system, config=config)
        decision = _make_decision(
            final_status="CONFIDENT_WRONG",
            controller_action="STOP",
        )
        result = gate.process(decision)
        # Receipt should record the effective verdict (block), not the shadow override
        assert result.receipt is not None
        assert result.receipt.verdict == "block"


class TestProcessFile:

    def test_read_from_disk(self, gate: DetectorHandoffGate, tmp_path: Path):
        decision = _make_decision()
        path = tmp_path / "controller_decision.json"
        path.write_text(json.dumps(decision))
        result = gate.process_file(path)
        assert result.verdict == "pass"

    def test_file_not_found(self, gate: DetectorHandoffGate, tmp_path: Path):
        result = gate.process_file(tmp_path / "nonexistent.json")
        assert result.verdict == "block"
        assert any("not found" in e for e in result.validation_errors)

    def test_invalid_json(self, gate: DetectorHandoffGate, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")
        result = gate.process_file(path)
        assert result.verdict == "block"
        assert any("Invalid JSON" in e for e in result.validation_errors)


class TestNoReceiptSystem:

    def test_works_without_receipt_system(self):
        gate = DetectorHandoffGate(receipt_system=None)
        decision = _make_decision()
        result = gate.process(decision)
        assert result.verdict == "pass"
        assert result.receipt is None


# =============================================================================
# Nonce generation
# =============================================================================


class TestGenerateNonce:

    def test_nonce_is_hex_string(self):
        nonce = generate_nonce()
        assert len(nonce) == 32  # 16 bytes = 32 hex chars
        int(nonce, 16)  # Should not raise

    def test_nonces_are_unique(self):
        nonces = {generate_nonce() for _ in range(100)}
        assert len(nonces) == 100


# =============================================================================
# Enum coverage
# =============================================================================


class TestEnums:

    def test_controller_action_values(self):
        assert set(ControllerAction) == {
            ControllerAction.FAST_PATH,
            ControllerAction.LOW_MARGIN_RETRY,
            ControllerAction.GROUND,
            ControllerAction.STOP,
        }

    def test_final_status_values(self):
        assert set(FinalStatus) == {
            FinalStatus.CLEAN,
            FinalStatus.LOW_MARGIN_RECOVERED,
            FinalStatus.CONFIDENT_WRONG,
            FinalStatus.KNOWLEDGE_BOUNDARY,
            FinalStatus.ORACLE_ERROR,
        }

    def test_oracle_result_values(self):
        assert set(OracleResult) == {
            OracleResult.PASS,
            OracleResult.FAIL,
            OracleResult.ERROR,
        }

    def test_failure_kind_values(self):
        assert FailureKind.NOT_FOUND.value == "NOT_FOUND"
        assert FailureKind.TYPECHECK.value == "TYPECHECK"
        assert len(FailureKind) == 6

    def test_error_kind_values(self):
        assert ErrorKind.TIMEOUT.value == "TIMEOUT"
        assert ErrorKind.BINARY_MISSING.value == "BINARY_MISSING"
        assert len(ErrorKind) == 5

    def test_handoff_recommendation_values(self):
        assert len(HandoffRecommendation) == 5


# =============================================================================
# HandoffConfig
# =============================================================================


class TestHandoffConfig:

    def test_defaults(self):
        config = HandoffConfig()
        assert config.default_ttl_ms == DEFAULT_TTL_MS
        assert config.oracle_error_override_classes == []
        assert config.shadow_mode is False
        assert config.oracle_profile_requirements == {}

    def test_to_dict(self):
        config = HandoffConfig(shadow_mode=True, oracle_error_override_classes=["qa"])
        d = config.to_dict()
        assert d["shadow_mode"] is True
        assert d["oracle_error_override_classes"] == ["qa"]


# =============================================================================
# HandoffResult
# =============================================================================


class TestHandoffResult:

    def test_effective_verdict_defaults_to_verdict(self):
        result = HandoffResult(verdict="pass", final_status="CLEAN", controller_action="FAST_PATH")
        assert result.effective_verdict == "pass"

    def test_effective_verdict_preserved_when_set(self):
        result = HandoffResult(
            verdict="pass",
            final_status="CONFIDENT_WRONG",
            controller_action="STOP",
            effective_verdict="block",
            shadow=True,
        )
        assert result.effective_verdict == "block"


# =============================================================================
# Integration: nonce + hash + full flow
# =============================================================================


class TestFullFlowWithBindings:

    def test_nonce_and_hash_happy_path(self, gate: DetectorHandoffGate):
        nonce = gate.generate_nonce()
        output = b"def hello(): return 'world'"
        output_hash = hashlib.sha256(output).hexdigest()
        decision = _make_decision(
            request_nonce=nonce,
            output_hash=output_hash,
        )
        result = gate.process(decision, expected_nonce=nonce, actual_output=output)
        assert result.verdict == "pass"
        assert result.validation_errors == []

    def test_stale_nonce_full_flow(self, gate: DetectorHandoffGate):
        """Full flow: generate nonce, but decision uses a different one."""
        nonce = gate.generate_nonce()
        decision = _make_decision(request_nonce="stale_nonce")
        result = gate.process(decision, expected_nonce=nonce)
        assert result.verdict == "block"

    def test_tampered_output_full_flow(self, gate: DetectorHandoffGate):
        """Full flow: decision says output_hash X but actual output hashes to Y."""
        output = b"real output"
        tampered_hash = hashlib.sha256(b"tampered output").hexdigest()
        decision = _make_decision(output_hash=tampered_hash)
        result = gate.process(decision, actual_output=output)
        assert result.verdict == "block"

    def test_binding_failure_still_emits_receipt(self, gate: DetectorHandoffGate):
        """Even when bindings fail, receipt is emitted (documenting the block)."""
        decision = _make_decision(request_nonce="wrong")
        result = gate.process(decision, expected_nonce="right")
        assert result.verdict == "block"
        assert result.receipt is not None
        assert result.receipt.verdict == "block"
