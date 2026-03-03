# SPDX-License-Identifier: Apache-2.0
"""GATE_CHECK_SUMMARY — one signal per evidence gate invocation.

First live signal from a production code path. Proves signal plane blood flow.

Not an aggregate metric — an event record. One envelope per `gate.check()` call.
Emitted from `governor gate check` CLI. Fail-open: emission failure never blocks
the gate.

Quality semantics:
  - Gate ran and returned → ok, value=1.0
  - Gate threw an exception → unavailable, value=None (attempt recorded)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    default_source_versions,
)

logger = logging.getLogger(__name__)

SIGNAL_ID = "GATE_CHECK_SUMMARY"
SIGNAL_VERSION = 1
DERIVATION_VERSION = "gate-check-summary-v1"


def build_gate_check_summary(
    *,
    verdict: str,
    claims_count: int,
    violations_count: int,
    warnings_count: int,
    has_oracle_evidence: bool = False,
    duration_ns: int | None = None,
    session_id: str | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Build a GATE_CHECK_SUMMARY envelope from gate check results.

    Pure function — no IO.

    Args:
        verdict: Gate result status ("OK", "WARN", "BLOCKED").
        claims_count: Number of claims extracted.
        violations_count: Number of blocking violations.
        warnings_count: Number of warnings.
        has_oracle_evidence: Whether oracle evidence was provided to the invocation.
        duration_ns: Wall-clock duration in nanoseconds (monotonic).
        session_id: Process-scoped session ID for correlation.
        emitted_at: ISO 8601 UTC timestamp override (default: now).
    """
    values: dict[str, Any] = {
        "verdict": verdict,
        "claims_count": claims_count,
        "violations_count": violations_count,
        "warnings_count": warnings_count,
        "has_oracle_evidence": has_oracle_evidence,
    }
    if duration_ns is not None:
        values["duration_ns"] = duration_ns

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter="governor.signals.gate_check_summary",
        emitter_version="1",
        signal_id=SIGNAL_ID,
        signal_version=SIGNAL_VERSION,
        phase="2.5",
        subject_type="gate_invocation",
        session_id=session_id,
        value=1.0,
        unit="event",
        values=values,
        quality_status=QualityStatus.OK.value,
        source_versions=default_source_versions(),
        derivation=DerivationType.DIRECT.value,
        derivation_version=DERIVATION_VERSION,
    )


def build_gate_check_error_summary(
    *,
    error_type: str,
    error_message: str,
    has_oracle_evidence: bool = False,
    duration_ns: int | None = None,
    session_id: str | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Build an unavailable GATE_CHECK_SUMMARY when the gate throws.

    Records the attempt even when the gate fails. value=None (missing != zero).
    """
    values: dict[str, Any] = {
        "verdict": "ERROR",
        "claims_count": 0,
        "violations_count": 0,
        "warnings_count": 0,
        "has_oracle_evidence": has_oracle_evidence,
        "error_type": error_type[:200],  # cap to avoid bloat
        "error_message": error_message[:500],
    }
    if duration_ns is not None:
        values["duration_ns"] = duration_ns

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter="governor.signals.gate_check_summary",
        emitter_version="1",
        signal_id=SIGNAL_ID,
        signal_version=SIGNAL_VERSION,
        phase="2.5",
        subject_type="gate_invocation",
        session_id=session_id,
        value=None,
        unit="event",
        values=values,
        quality_status=QualityStatus.UNAVAILABLE.value,
        quality_reasons=["gate_exception"],
        source_versions=default_source_versions(),
        derivation=DerivationType.DIRECT.value,
        derivation_version=DERIVATION_VERSION,
    )


def try_emit_gate_check_summary(
    signal_sink: "SignalEmitter | None",
    envelope: SignalEnvelope,
) -> None:
    """Best-effort signal emission. Fail-open, never raises.

    Let JsonlSink's built-in SIGNAL_EMIT_FAILED handle emission errors.
    """
    if signal_sink is None:
        return
    try:
        signal_sink.emit(envelope)
    except Exception:
        # JsonlSink already writes SIGNAL_EMIT_FAILED on failure.
        # Log here only as defense-in-depth.
        logger.debug("GATE_CHECK_SUMMARY emission failed", exc_info=True)
