# SPDX-License-Identifier: Apache-2.0
"""
Detector Handoff Gate — Controller Decision → Gate Receipt.

Reads a controller_decision.json (v1) from the Δt hallucination detector's
runtime controller. Validates the schema, checks replay protection bindings
(nonce, output hash, TTL), maps final_status to a governor verdict, and emits
a standard GateReceipt via the existing GateReceiptSystem.

This is *not* the 19-D signal collapse (see detector_integration.py).
This is the 3-way controller decision: accept, retry, or stop.

Spec: DETECTOR_HANDOFF_SPEC.md
Boundary: No imports from detector. The file is the API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from governor.gate_receipt import GateReceiptSystem, canonical_json, GateReceipt

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

SCHEMA_VERSION = "controller_decision/v1"

DEFAULT_TTL_MS = 30_000
"""Default maximum age (ms) for a decision file before the governor rejects it."""

CLOCK_SKEW_TOLERANCE_S = 5
"""Maximum seconds a created_at timestamp may be in the future."""


# =============================================================================
# Enums
# =============================================================================


class ControllerAction(str, Enum):
    """What the controller did (a verb)."""

    FAST_PATH = "FAST_PATH"
    LOW_MARGIN_RETRY = "LOW_MARGIN_RETRY"
    GROUND = "GROUND"
    STOP = "STOP"


class FinalStatus(str, Enum):
    """Outcome after all attempts (a noun)."""

    CLEAN = "CLEAN"
    LOW_MARGIN_RECOVERED = "LOW_MARGIN_RECOVERED"
    CONFIDENT_WRONG = "CONFIDENT_WRONG"
    KNOWLEDGE_BOUNDARY = "KNOWLEDGE_BOUNDARY"
    ORACLE_ERROR = "ORACLE_ERROR"


class OracleResult(str, Enum):
    """Oracle check result."""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class FailureKind(str, Enum):
    """Closed enum for oracle FAIL entries."""

    NOT_FOUND = "NOT_FOUND"
    MALFORMED = "MALFORMED"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    TYPECHECK = "TYPECHECK"
    LINT = "LINT"
    TEST_FAIL = "TEST_FAIL"


class ErrorKind(str, Enum):
    """Closed enum for oracle ERROR entries."""

    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    BINARY_MISSING = "BINARY_MISSING"
    PARSE = "PARSE"


class HandoffRecommendation(str, Enum):
    """What the controller recommends the governor do next."""

    NONE = "NONE"
    GROUND = "GROUND"
    ESCALATE_MODEL = "ESCALATE_MODEL"
    ESCALATE_REMOTE = "ESCALATE_REMOTE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


# Valid final_status values when controller_action == STOP
_STOP_VALID_STATUSES = frozenset({
    FinalStatus.CONFIDENT_WRONG,
    FinalStatus.KNOWLEDGE_BOUNDARY,
    FinalStatus.ORACLE_ERROR,
})


# =============================================================================
# Verdict mapping
# =============================================================================

_VERDICT_MAP: dict[FinalStatus, str] = {
    FinalStatus.CLEAN: "pass",
    FinalStatus.LOW_MARGIN_RECOVERED: "pass",
    FinalStatus.CONFIDENT_WRONG: "block",
    FinalStatus.KNOWLEDGE_BOUNDARY: "block",
    FinalStatus.ORACLE_ERROR: "block",
}


# =============================================================================
# Errors
# =============================================================================


class HandoffValidationError(ValueError):
    """Raised when a controller_decision.json fails validation."""


# =============================================================================
# Data types
# =============================================================================


@dataclass
class HandoffConfig:
    """Configuration for the handoff gate."""

    default_ttl_ms: int = DEFAULT_TTL_MS
    oracle_error_override_classes: list[str] = field(default_factory=list)
    """Task classes where ORACLE_ERROR may be downgraded to 'warn'."""

    shadow_mode: bool = False
    """If True, emit receipts but always return 'pass' verdict (log-only)."""

    oracle_profile_requirements: dict[str, str] = field(default_factory=dict)
    """Map of task_class → required oracle_profile. Empty = no enforcement."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_ttl_ms": self.default_ttl_ms,
            "oracle_error_override_classes": self.oracle_error_override_classes,
            "shadow_mode": self.shadow_mode,
            "oracle_profile_requirements": self.oracle_profile_requirements,
        }


@dataclass
class HandoffResult:
    """Result of processing a controller decision."""

    verdict: str
    """Governor verdict: 'pass', 'block', or 'warn'."""

    final_status: str
    """The controller's final_status value."""

    controller_action: str
    """The controller's action."""

    receipt: GateReceipt | None = None
    """Gate receipt (None if receipt system unavailable)."""

    shadow: bool = False
    """True if shadow_mode overrode a block/warn to pass."""

    effective_verdict: str = ""
    """What the verdict would have been without shadow mode."""

    escalation_bundle: dict[str, Any] | None = None
    """Populated when verdict is 'block'. Contains evidence for remote model."""

    validation_errors: list[str] = field(default_factory=list)
    """Non-empty if the decision failed validation (verdict forced to 'block')."""

    def __post_init__(self) -> None:
        if not self.effective_verdict:
            self.effective_verdict = self.verdict


# =============================================================================
# Nonce generation
# =============================================================================


def generate_nonce() -> str:
    """Generate a request nonce for freshness binding."""
    return secrets.token_hex(16)


# =============================================================================
# Core validation + processing
# =============================================================================


def validate_schema(decision: dict[str, Any]) -> list[str]:
    """Validate the controller_decision schema. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    # Schema version
    schema = decision.get("schema")
    if schema != SCHEMA_VERSION:
        errors.append(f"Unknown schema: {schema!r} (expected {SCHEMA_VERSION!r})")
        return errors  # Can't validate further if schema is wrong

    # Required top-level sections
    for section in ("task", "local_model", "decision", "evidence", "economics", "created_at"):
        if section not in decision:
            errors.append(f"Missing required section: {section!r}")

    if errors:
        return errors

    # Task section
    task = decision["task"]
    for field_name in ("task_id", "task_class", "namespace", "prompt_hash"):
        if field_name not in task:
            errors.append(f"task.{field_name} is required")

    # Decision section
    dec = decision["decision"]
    for field_name in ("fork_risk", "tau_milliunits", "controller_action", "final_status"):
        if field_name not in dec:
            errors.append(f"decision.{field_name} is required")

    if "fork_risk" in dec:
        fr = dec["fork_risk"]
        if not isinstance(fr, dict) or "value_milliunits" not in fr:
            errors.append("decision.fork_risk.value_milliunits is required")

    # Validate enum values
    if "controller_action" in dec:
        try:
            ControllerAction(dec["controller_action"])
        except ValueError:
            errors.append(f"Invalid controller_action: {dec['controller_action']!r}")

    if "final_status" in dec:
        try:
            FinalStatus(dec["final_status"])
        except ValueError:
            errors.append(f"Invalid final_status: {dec['final_status']!r}")

    # STOP invariant: STOP + CLEAN is a paradox
    if "controller_action" in dec and "final_status" in dec:
        try:
            action = ControllerAction(dec["controller_action"])
            status = FinalStatus(dec["final_status"])
            if action == ControllerAction.STOP and status not in _STOP_VALID_STATUSES:
                errors.append(
                    f"STOP invariant violated: controller_action=STOP "
                    f"cannot have final_status={status.value}"
                )
        except ValueError:
            pass  # Already caught above

    # Oracle result enum validation
    evidence = decision.get("evidence", {})
    for i, check in enumerate(evidence.get("oracle_checks", [])):
        result = check.get("result")
        try:
            OracleResult(result)
        except (ValueError, TypeError):
            errors.append(f"evidence.oracle_checks[{i}].result: invalid value {result!r}")

    return errors


def validate_bindings(
    decision: dict[str, Any],
    expected_nonce: str | None = None,
    actual_output: bytes | None = None,
    config: HandoffConfig | None = None,
) -> list[str]:
    """Validate replay/substitution protection bindings. Returns list of errors."""
    errors: list[str] = []
    config = config or HandoffConfig()

    task = decision.get("task", {})
    dec = decision.get("decision", {})

    # Nonce validation
    if expected_nonce is not None:
        file_nonce = task.get("request_nonce")
        if file_nonce != expected_nonce:
            errors.append(
                f"Nonce mismatch: expected {expected_nonce!r}, got {file_nonce!r}"
            )

    # Output hash validation (only for CLEAN/LOW_MARGIN_RECOVERED verdicts)
    if actual_output is not None:
        file_hash = task.get("output_hash")
        if file_hash:
            actual_hash = hashlib.sha256(actual_output).hexdigest()
            if file_hash != actual_hash:
                errors.append(
                    f"Output hash mismatch: decision says {file_hash[:16]}..., "
                    f"actual output hashes to {actual_hash[:16]}..."
                )

    # TTL validation (governor time, not detector time)
    ttl_ms = dec.get("decision_ttl_ms", config.default_ttl_ms)
    created_at_str = decision.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)

            # Check not too far in future
            future_delta = (created_at - now).total_seconds()
            if future_delta > CLOCK_SKEW_TOLERANCE_S:
                errors.append(
                    f"created_at is {future_delta:.1f}s in the future "
                    f"(tolerance: {CLOCK_SKEW_TOLERANCE_S}s)"
                )

            # Check TTL (against governor time)
            age_ms = (now - created_at).total_seconds() * 1000
            if age_ms > ttl_ms:
                errors.append(
                    f"Decision expired: age={age_ms:.0f}ms, ttl={ttl_ms}ms"
                )
        except (ValueError, TypeError):
            errors.append(f"Invalid created_at timestamp: {created_at_str!r}")

    # Oracle profile enforcement
    if config.oracle_profile_requirements:
        task_class = task.get("task_class", "")
        required_profile = config.oracle_profile_requirements.get(task_class)
        if required_profile:
            actual_profile = task.get("oracle_profile")
            if actual_profile != required_profile:
                errors.append(
                    f"Oracle profile mismatch for task_class={task_class!r}: "
                    f"expected {required_profile!r}, got {actual_profile!r}"
                )

    return errors


def map_verdict(
    decision: dict[str, Any],
    config: HandoffConfig | None = None,
) -> str:
    """Map final_status to governor verdict, respecting ORACLE_ERROR overrides."""
    config = config or HandoffConfig()
    dec = decision.get("decision", {})
    status = FinalStatus(dec["final_status"])

    verdict = _VERDICT_MAP[status]

    # ORACLE_ERROR override: block → warn for allowed task classes
    if status == FinalStatus.ORACLE_ERROR and config.oracle_error_override_classes:
        task_class = decision.get("task", {}).get("task_class", "")
        if task_class in config.oracle_error_override_classes:
            verdict = "warn"

    return verdict


def build_evidence_bundle(decision: dict[str, Any]) -> dict[str, Any]:
    """Extract the evidence bundle from a controller decision for the gate receipt."""
    dec = decision.get("decision", {})
    evidence = decision.get("evidence", {})
    economics = decision.get("economics", {})

    bundle: dict[str, Any] = {}

    # From evidence section
    for key in ("candidates", "oracle_checks", "failures", "controller_trace_ref"):
        if key in evidence:
            bundle[key] = evidence[key]

    # From decision section
    for key in ("fork_risk", "tau_milliunits", "controller_action", "final_status",
                "handoff_recommendation", "decision_ttl_ms"):
        if key in dec:
            bundle[key] = dec[key]

    # From economics section
    for key in ("local_tokens_spent", "retry_tokens_spent", "retry_count",
                "latency_ms", "oracle_latency_ms"):
        if key in economics:
            bundle[key] = economics[key]

    return bundle


def build_gate_config(decision: dict[str, Any], config: HandoffConfig | None = None) -> dict[str, Any]:
    """Build gate_config for the GateReceipt."""
    config = config or HandoffConfig()
    task = decision.get("task", {})
    model = decision.get("local_model", {})

    gc: dict[str, Any] = {
        "gate": "detector_handoff",
        "schema": decision.get("schema", SCHEMA_VERSION),
        "model_id": model.get("model_id", "unknown"),
        "task_class": task.get("task_class", "unknown"),
        "namespace": task.get("namespace", "unknown"),
        "enforcement": "shadow" if config.shadow_mode else "gated",
    }

    # Include override info if ORACLE_ERROR was downgraded
    dec = decision.get("decision", {})
    if dec.get("final_status") == FinalStatus.ORACLE_ERROR.value:
        task_class = task.get("task_class", "")
        if task_class in config.oracle_error_override_classes:
            gc["oracle_error_override"] = "warn"
            gc["oracle_error_override_class"] = task_class

    return gc


def build_escalation_bundle(
    decision: dict[str, Any],
    receipt: GateReceipt | None = None,
) -> dict[str, Any]:
    """Build an escalation bundle for a blocked decision.

    Contains everything a remote model needs to understand what was tried
    and why it failed.
    """
    task = decision.get("task", {})
    evidence = decision.get("evidence", {})
    dec = decision.get("decision", {})

    bundle: dict[str, Any] = {
        "reason": dec.get("final_status", ""),
        "handoff_recommendation": dec.get("handoff_recommendation", ""),
    }

    if receipt:
        bundle["receipt_id"] = receipt.receipt_id

    # Task context
    for key in ("task_id", "task_class", "namespace", "prompt_hash", "oracle_profile"):
        if key in task:
            bundle[key] = task[key]

    # What was tried
    bundle["local_model"] = decision.get("local_model", {})
    if "candidates" in evidence:
        bundle["candidates"] = evidence["candidates"]

    # Why it failed
    for key in ("oracle_checks", "failures"):
        if key in evidence:
            bundle[key] = evidence[key]

    return bundle


# =============================================================================
# Handoff Gate (facade)
# =============================================================================


class DetectorHandoffGate:
    """Reads controller_decision.json, validates, and emits GateReceipts.

    Usage:
        gate = DetectorHandoffGate(receipt_system=receipt_sys)
        nonce = gate.generate_nonce()
        # ... give nonce to detector, detector generates, writes decision file ...
        result = gate.process(decision_path, expected_nonce=nonce, actual_output=output_bytes)
        if result.verdict == "block":
            escalation = result.escalation_bundle  # send to remote model
    """

    def __init__(
        self,
        receipt_system: GateReceiptSystem | None = None,
        config: HandoffConfig | None = None,
    ):
        self.receipt_system = receipt_system
        self.config = config or HandoffConfig()

    def generate_nonce(self) -> str:
        """Generate a fresh request nonce."""
        return generate_nonce()

    def process_file(
        self,
        decision_path: Path,
        expected_nonce: str | None = None,
        actual_output: bytes | None = None,
    ) -> HandoffResult:
        """Read a controller_decision.json file and process it.

        Args:
            decision_path: Path to the controller_decision.json file.
            expected_nonce: The nonce we issued. If provided, validates match.
            actual_output: The actual model output bytes. If provided, validates hash.

        Returns:
            HandoffResult with verdict, receipt, and optional escalation bundle.
        """
        try:
            content = decision_path.read_text()
            decision = json.loads(content)
        except FileNotFoundError:
            return HandoffResult(
                verdict="block",
                final_status="",
                controller_action="",
                validation_errors=[f"Decision file not found: {decision_path}"],
            )
        except json.JSONDecodeError as e:
            return HandoffResult(
                verdict="block",
                final_status="",
                controller_action="",
                validation_errors=[f"Invalid JSON: {e}"],
            )

        return self.process(decision, expected_nonce=expected_nonce, actual_output=actual_output)

    def process(
        self,
        decision: dict[str, Any],
        expected_nonce: str | None = None,
        actual_output: bytes | None = None,
    ) -> HandoffResult:
        """Process a parsed controller decision dict.

        This is the core method. process_file() is a convenience wrapper.
        """
        # Phase 1: Schema validation
        schema_errors = validate_schema(decision)
        if schema_errors:
            return HandoffResult(
                verdict="block",
                final_status=decision.get("decision", {}).get("final_status", ""),
                controller_action=decision.get("decision", {}).get("controller_action", ""),
                validation_errors=schema_errors,
            )

        # Phase 2: Binding validation (nonce, hash, TTL, oracle profile)
        binding_errors = validate_bindings(
            decision,
            expected_nonce=expected_nonce,
            actual_output=actual_output,
            config=self.config,
        )

        dec = decision.get("decision", {})
        final_status = dec["final_status"]
        controller_action = dec["controller_action"]

        # If binding validation fails, force block
        if binding_errors:
            result = HandoffResult(
                verdict="block",
                final_status=final_status,
                controller_action=controller_action,
                validation_errors=binding_errors,
            )
            # Still emit receipt (with block verdict) if receipt system available
            if self.receipt_system:
                try:
                    receipt = self._emit_receipt(decision, "block")
                    result.receipt = receipt
                except Exception as e:
                    logger.warning("Failed to emit receipt for binding failure: %s", e)
            return result

        # Phase 3: Verdict mapping
        verdict = map_verdict(decision, self.config)

        # Phase 4: Shadow mode override
        shadow = False
        effective_verdict = verdict
        if self.config.shadow_mode and verdict != "pass":
            shadow = True
            effective_verdict = verdict
            verdict = "pass"

        # Phase 5: Emit receipt
        receipt = None
        if self.receipt_system:
            try:
                emit_verdict = effective_verdict if shadow else verdict
                receipt = self._emit_receipt(decision, emit_verdict)
            except Exception as e:
                logger.warning("Failed to emit gate receipt: %s", e)

        # Phase 6: Build escalation bundle if blocked
        escalation = None
        actual_verdict = effective_verdict if shadow else verdict
        if actual_verdict == "block":
            escalation = build_escalation_bundle(decision, receipt)

        return HandoffResult(
            verdict=verdict,
            final_status=final_status,
            controller_action=controller_action,
            receipt=receipt,
            shadow=shadow,
            effective_verdict=effective_verdict,
            escalation_bundle=escalation,
        )

    def _emit_receipt(self, decision: dict[str, Any], verdict: str) -> GateReceipt:
        """Emit a GateReceipt for this decision."""
        assert self.receipt_system is not None

        subject_bytes = canonical_json(decision)
        evidence_bundle = build_evidence_bundle(decision)
        gate_config = build_gate_config(decision, self.config)

        return self.receipt_system.emit(
            gate="detector_handoff",
            verdict=verdict,
            subject_kind="controller_decision",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config=gate_config,
        )
