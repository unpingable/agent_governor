# SPDX-License-Identifier: Apache-2.0
"""
SILENT_SUPPRESSION — plugged-in-but-dark detector.

Detects when the governor is expected to be in-path but is effectively
absent.  Uses multiple indicators, not daemon self-attestation alone.

Classification:
  idle         — no activity in window (no external expectation)
  healthy      — active window + sufficient in-path governor evidence
  likely_suppressed — active window + missing/insufficient evidence
  indeterminate — cannot classify (insufficient data from both sides)

External expectation source (Phase A):
  Chain preflight/record attempts (gate="chain_composition" receipts)
  and evidence gate invocations count as "expected activity markers."
  These originate from callers (Guvnah, Maude, hooks), not the daemon
  itself. If callers are invoking governance APIs but no in-path
  receipts appear, the governor is likely suppressed.

Key invariants:
  - idle != suppressed (no activity is not a sign of failure)
  - missing != zero
  - observe-only (no gating/policy changes)
  - at least one indicator external to daemon self-report

Window boundary semantics (shared across all Phase A signals):
  - window_start is INCLUSIVE (event.timestamp >= window_start)
  - window_end is EXCLUSIVE (event.timestamp < window_end)
  - Comparison is lexicographic on ISO 8601 UTC strings
  - Duplicate receipt_ids counted once (deduped by receipt_id)
  - Late-arriving events included if within window bounds
  - No "late arrival" concept at derivation layer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    default_source_versions,
)


# ── Classification ──────────────────────────────────────────────────────────

CLASSIFICATION_IDLE = "idle"
CLASSIFICATION_HEALTHY = "healthy"
CLASSIFICATION_LIKELY_SUPPRESSED = "likely_suppressed"
CLASSIFICATION_INDETERMINATE = "indeterminate"


# ── Input model ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SuppressionIndicators:
    """Indicators from independent sources for suppression detection.

    External expectation sources (caller-side):
      expected_heartbeat_count — expected periodic health probes in window
      observed_heartbeat_count — heartbeats actually observed
      expected_event_markers   — governance API calls from callers
                                 (chain preflight/record, evidence checks)

    In-path evidence (governor-side):
      observed_event_markers   — governor receipts/events confirming in-path activity
      daemon_reachable         — daemon responded to at least one probe
      in_path_evidence_present — at least one governance receipt in window

    Activity indicator:
      activity_observed        — any external caller activity (dispatch, chat, etc.)
    """

    expected_heartbeat_count: int = 0
    observed_heartbeat_count: int = 0
    expected_event_markers: int = 0
    observed_event_markers: int = 0
    daemon_reachable: bool = False
    in_path_evidence_present: bool = False
    activity_observed: bool = False

    def has_expectation(self) -> bool:
        """True if there's any basis to expect governor activity."""
        return (
            self.activity_observed
            or self.expected_event_markers > 0
            or self.expected_heartbeat_count > 0
        )

    def has_evidence(self) -> bool:
        """True if in-path governor evidence was observed."""
        return (
            self.in_path_evidence_present
            or self.observed_event_markers > 0
            or self.observed_heartbeat_count > 0
        )


# ── Classification function ────────────────────────────────────────────────

def classify_suppression(indicators: SuppressionIndicators) -> str:
    """Classify suppression state from indicators.

    Rules:
      1. No expectation + no evidence → idle
      2. Expectation + sufficient evidence → healthy
      3. Expectation + no/insufficient evidence → likely_suppressed
      4. No expectation + some evidence → healthy (governor active, no demand)
      5. Insufficient data to determine → indeterminate

    Returns: classification string.
    """
    has_expect = indicators.has_expectation()
    has_evid = indicators.has_evidence()

    if not has_expect and not has_evid:
        return CLASSIFICATION_IDLE

    if has_expect and has_evid:
        # Both sides reporting → healthy
        return CLASSIFICATION_HEALTHY

    if has_expect and not has_evid:
        # Callers are active but governor produced no evidence
        if indicators.daemon_reachable:
            # Daemon is up but not producing receipts → likely suppressed
            return CLASSIFICATION_LIKELY_SUPPRESSED
        else:
            # Daemon unreachable + active callers → likely suppressed
            return CLASSIFICATION_LIKELY_SUPPRESSED

    if not has_expect and has_evid:
        # Governor is producing evidence without external demand
        # This is normal (background checks, self-tests, etc.)
        return CLASSIFICATION_HEALTHY

    return CLASSIFICATION_INDETERMINATE


# ── Derivation function ────────────────────────────────────────────────────

def derive_silent_suppression(
    indicators: SuppressionIndicators,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    emitter: str = "governor.signals.silent_suppression",
    emitter_version: str = "",
    session_id: str | None = None,
    source_receipt_ids: list[str] | None = None,
    source_streams: list[str] | None = None,
    source_versions: dict[str, str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive SILENT_SUPPRESSION from multi-source indicators.

    Pure derivation — no IO. Caller provides pre-gathered indicators.

    Value semantics:
      1.0 = not suppressed (healthy)
      0.0 = likely suppressed (active-but-dark)
      None = cannot compute (idle or indeterminate)

    Args:
        indicators: Multi-source suppression indicators.
        window_start: ISO 8601 UTC window start.
        window_end: ISO 8601 UTC window end.
        window_kind: Window type identifier.
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context.
        source_receipt_ids: Receipt IDs that contributed.
        source_streams: Named source streams.
        source_versions: Version info for source subsystems.
        emitted_at: Override emission timestamp.

    Returns:
        SignalEnvelope with signal_id="SILENT_SUPPRESSION".
    """
    classification = classify_suppression(indicators)

    # ── Value and quality from classification ──────────────────────────
    if classification == CLASSIFICATION_IDLE:
        value: float | None = None
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["no_activity_in_window"]
        completeness: float | None = None
        sample_size: int | None = None

    elif classification == CLASSIFICATION_HEALTHY:
        value = 1.0
        quality_status = QualityStatus.OK.value
        quality_reasons = []
        completeness = 1.0
        sample_size = (
            indicators.observed_event_markers
            + indicators.observed_heartbeat_count
        ) or 1

    elif classification == CLASSIFICATION_LIKELY_SUPPRESSED:
        value = 0.0
        quality_status = QualityStatus.OK.value
        quality_reasons = []
        completeness = 1.0
        sample_size = indicators.expected_event_markers or 1

    elif classification == CLASSIFICATION_INDETERMINATE:
        value = None
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["insufficient_data"]
        completeness = None
        sample_size = None

    else:
        # Defensive: unknown classification
        value = None
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["unknown_classification"]
        completeness = None
        sample_size = None

    # ── Partial quality for degraded indicator coverage ────────────────
    # If we have a classification but some indicator sources are missing,
    # degrade to partial.
    if classification in (CLASSIFICATION_HEALTHY, CLASSIFICATION_LIKELY_SUPPRESSED):
        indicator_sources = [
            indicators.expected_heartbeat_count > 0 or indicators.observed_heartbeat_count > 0,
            indicators.expected_event_markers > 0 or indicators.observed_event_markers > 0,
            indicators.activity_observed,
        ]
        active_sources = sum(1 for s in indicator_sources if s)
        total_sources = len(indicator_sources)
        if active_sources < total_sources:
            quality_status = QualityStatus.PARTIAL.value
            quality_reasons = [
                f"incomplete_indicator_coverage ({active_sources}/{total_sources} sources)",
            ]
            completeness = active_sources / total_sources

    # ── Values dict (all indicators for auditability) ──────────────────
    values: dict[str, Any] = {
        "expected_heartbeat_count": indicators.expected_heartbeat_count,
        "observed_heartbeat_count": indicators.observed_heartbeat_count,
        "expected_event_markers": indicators.expected_event_markers,
        "observed_event_markers": indicators.observed_event_markers,
        "daemon_reachable": 1 if indicators.daemon_reachable else 0,
        "in_path_evidence_present": 1 if indicators.in_path_evidence_present else 0,
        "activity_observed": 1 if indicators.activity_observed else 0,
        "suppression_detected": 1 if classification == CLASSIFICATION_LIKELY_SUPPRESSED else 0,
    }

    # ── Annotations ────────────────────────────────────────────────────
    annotations: dict[str, Any] = {
        "classification": classification,
    }

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="SILENT_SUPPRESSION",
        signal_version=1,
        phase="2.4A",
        subject_type="runtime",
        subject_id=f"runtime_{window_start}_{window_kind}",
        session_id=session_id,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="ratio",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=sample_size,
        completeness=completeness,
        source_receipt_ids=source_receipt_ids or [],
        source_streams=source_streams or [],
        source_versions=source_versions if source_versions is not None else default_source_versions(),
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="silent-suppression-v1",
        annotations=annotations,
    )
