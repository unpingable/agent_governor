# SPDX-License-Identifier: Apache-2.0
"""
EXPOSURE_PROXY — non-gameable denominator for capture/contradiction metrics.

Pure derivation: takes authoritative event counts, produces SignalEnvelope.
No IO in the derivation path. Receipt counting is a separate thin helper.

Key invariants:
  - Weights explicit and versioned (DEFAULT_WEIGHT_SET_ID)
  - Authoritative surfaces only (receipts, dispatch, daemon events)
  - missing != zero (no events → unavailable, not zero)
  - Counts attempts, not just successes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
)

if TYPE_CHECKING:
    from ..gate_receipt import ReceiptStore


# ── Weight configuration (explicit + versioned from day one) ────────────────
#
# Overlap policy:  COMPOSITE OPPORTUNITY ACCOUNTING
#
#   Components may intentionally overlap in the pipeline.  For example,
#   a single user turn may trigger a chat_generation call that also fires
#   an evidence_check.  This is deliberate: we're measuring *total
#   governance opportunity*, not independent event classes.
#
#   Weights represent how much each surface contributes to exposure
#   opportunity, not Bayesian priors on independent events.
#
#   If you change this to independent-event normalization, bump the
#   weight_set_id.  Downstream calibration (Phase C) will break silently
#   if the accounting model changes without a version bump.
#
# Changing any weight below MUST bump DEFAULT_WEIGHT_SET_ID.
#
# ┌───────────────────────┬────────┬──────────────────────────────────────────┐
# │ Component             │ Weight │ Rationale                                │
# ├───────────────────────┼────────┼──────────────────────────────────────────┤
# │ tool_dispatch         │  1.0   │ Chain gate preflight/record — direct     │
# │                       │        │ governance surface, highest fidelity     │
# ├───────────────────────┼────────┼──────────────────────────────────────────┤
# │ chat_generation       │  0.5   │ Daemon inline gating — governed but      │
# │                       │        │ lower enforcement depth than dispatch    │
# ├───────────────────────┼────────┼──────────────────────────────────────────┤
# │ evidence_checks       │  0.8   │ Evidence gate — core enforcement path,   │
# │                       │        │ may correlate with chat_generation       │
# ├───────────────────────┼────────┼──────────────────────────────────────────┤
# │ violation_evaluations │  1.0   │ Violation resolver — active governance   │
# │                       │        │ events, may follow tool_dispatch         │
# └───────────────────────┴────────┴──────────────────────────────────────────┘

DEFAULT_WEIGHT_SET_ID = "default-v1"

DEFAULT_WEIGHTS: dict[str, float] = {
    "tool_dispatch": 1.0,
    "chat_generation": 0.5,
    "evidence_checks": 0.8,
    "violation_evaluations": 1.0,
}

# Total number of component streams (for coverage ratio)
_TOTAL_STREAMS = len(DEFAULT_WEIGHTS)

# Component → ReceiptStore gate mapping (for count_from_receipts)
_GATE_COMPONENT_MAP: dict[str, str] = {
    "chain_composition": "tool_dispatch",
    "evidence_gate": "evidence_checks",
}


# ── Input model ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExposureComponents:
    """Raw event counts from authoritative governance surfaces.

    Each field counts attempts (not just successes) from an authoritative
    event surface.  The derivation function weights and sums them.
    """

    tool_dispatch_attempts: int = 0
    chat_generation_calls: int = 0
    evidence_checks: int = 0
    violation_evaluations: int = 0

    @property
    def total(self) -> int:
        """Total eligible events across all components."""
        return (
            self.tool_dispatch_attempts
            + self.chat_generation_calls
            + self.evidence_checks
            + self.violation_evaluations
        )

    def has_any(self) -> bool:
        """True if any component has at least one event."""
        return self.total > 0

    def active_stream_count(self) -> int:
        """How many component streams have at least one event."""
        return sum(
            1
            for c in (
                self.tool_dispatch_attempts,
                self.chat_generation_calls,
                self.evidence_checks,
                self.violation_evaluations,
            )
            if c > 0
        )

    def to_values_dict(self) -> dict[str, int]:
        """Flat component counts for SignalEnvelope.values."""
        return {
            "component_tool_dispatch_attempts": self.tool_dispatch_attempts,
            "component_chat_generation_calls": self.chat_generation_calls,
            "component_evidence_checks": self.evidence_checks,
            "component_violation_evaluations": self.violation_evaluations,
        }


# ── Pure computation ────────────────────────────────────────────────────────

def compute_exposure_points(
    components: ExposureComponents,
    weights: dict[str, float] | None = None,
) -> float:
    """Weighted sum of component counts.  Pure function, no IO."""
    w = weights if weights is not None else DEFAULT_WEIGHTS
    return (
        components.tool_dispatch_attempts * w.get("tool_dispatch", 0.0)
        + components.chat_generation_calls * w.get("chat_generation", 0.0)
        + components.evidence_checks * w.get("evidence_checks", 0.0)
        + components.violation_evaluations * w.get("violation_evaluations", 0.0)
    )


# ── Derivation function ────────────────────────────────────────────────────

def derive_exposure_proxy(
    components: ExposureComponents,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    excluded_events: int = 0,
    excluded_reasons: dict[str, int] | None = None,
    weights: dict[str, float] | None = None,
    weight_set_id: str | None = None,
    emitter: str = "governor.signals.exposure_proxy",
    emitter_version: str = "",
    session_id: str | None = None,
    source_receipt_ids: list[str] | None = None,
    source_streams: list[str] | None = None,
    source_versions: dict[str, str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive EXPOSURE_PROXY from authoritative event counts.

    Pure derivation — no IO. Caller provides pre-counted components.

    Quality logic:
      - No events at all (eligible + excluded = 0) → unavailable, value=None
      - Events present → ok, value = weighted sum
      - value=0.0 is valid when events exist but sum to zero

    Args:
        components: Raw event counts from authoritative surfaces.
        window_start: ISO 8601 UTC window start.
        window_end: ISO 8601 UTC window end.
        window_kind: Window type identifier (e.g. "rolling_5m").
        excluded_events: Count of events excluded from weighting.
        excluded_reasons: Reason codes for excluded events.
        weights: Override weight set (default: DEFAULT_WEIGHTS).
        weight_set_id: Version tag for weight provenance.
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context (if scoped to a session).
        source_receipt_ids: Receipt IDs that contributed to this derivation.
        source_streams: Named source streams (e.g. ["preflight", "dispatch"]).
        source_versions: Version info for source subsystems.
        emitted_at: Override emission timestamp (default: now).

    Returns:
        SignalEnvelope with signal_id="EXPOSURE_PROXY".
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS
    wid = weight_set_id or DEFAULT_WEIGHT_SET_ID

    eligible = components.total
    source_count = eligible + excluded_events
    points = compute_exposure_points(components, w)

    # ── Quality determination ──────────────────────────────────────────
    if source_count == 0:
        # No events of any kind — cannot compute.  Missing, not zero.
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["no_events_in_window"]
        value: float | None = None
        completeness: float | None = None
        sample_size: int | None = None
    else:
        # Events present — computable.  Zero is a valid result.
        value = points
        sample_size = source_count

        # Coverage: how many of the expected component streams contributed?
        active = components.active_stream_count()
        coverage = active / _TOTAL_STREAMS if _TOTAL_STREAMS else 1.0

        if coverage < 1.0 and eligible > 0:
            quality_status = QualityStatus.PARTIAL.value
            quality_reasons = [
                f"incomplete_stream_coverage ({active}/{_TOTAL_STREAMS} streams)",
            ]
            completeness = coverage
        else:
            quality_status = QualityStatus.OK.value
            quality_reasons = []
            completeness = 1.0

    # ── Build values dict (always populated for auditability) ──────────
    values: dict[str, Any] = {
        "exposure_points_total": points,
        "eligible_events": eligible,
        "excluded_events": excluded_events,
        "weighted_event_count": points,
        "coverage_ratio": completeness if completeness is not None else 0.0,
        "source_event_count": source_count,
    }
    values.update(components.to_values_dict())

    # ── Annotations (non-semantic extras) ──────────────────────────────
    annotations: dict[str, Any] = {"weight_set_id": wid}
    if excluded_reasons:
        annotations["excluded_reason_counts"] = dict(excluded_reasons)

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="EXPOSURE_PROXY",
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        subject_id=f"win_{window_start}_{window_kind}",
        session_id=session_id,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="exposure_points",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=sample_size,
        completeness=completeness,
        source_receipt_ids=source_receipt_ids or [],
        source_streams=source_streams or [],
        source_versions=source_versions or {},
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="exposure-proxy-v1",
        annotations=annotations,
    )


# ── Receipt store helper (thin mapping, not derivation) ─────────────────────

def count_from_receipts(
    receipt_store: ReceiptStore,
    *,
    window_start: str | None = None,
    window_end: str | None = None,
    gate_component_map: dict[str, str] | None = None,
) -> ExposureComponents:
    """Count authoritative events from a ReceiptStore.

    Maps receipt gate names to ExposureComponents fields.
    This is a convenience helper — callers can build ExposureComponents
    directly if they have counts from other sources.

    Default mapping:
      - "chain_composition" → tool_dispatch_attempts
      - "evidence_gate"     → evidence_checks

    chat_generation_calls and violation_evaluations require different
    sources (daemon telemetry, violation resolver) and are NOT counted
    here.  Caller must add them separately.

    Window boundary semantics:
      - window_start is INCLUSIVE (receipt.timestamp >= window_start)
      - window_end is EXCLUSIVE (receipt.timestamp < window_end)
      - If neither is specified, counts ALL receipts (no windowing)
      - Comparison is lexicographic on ISO 8601 strings (works for UTC)
      - Duplicate receipt_ids are counted once (deduped by receipt_id)
      - Late-arriving events are included if they fall within the window;
        there is no "late arrival" concept at the counting layer

    Returns:
        ExposureComponents with counts from the receipt store.
    """
    mapping = gate_component_map if gate_component_map is not None else _GATE_COMPONENT_MAP
    receipts = receipt_store.all()

    tool_dispatch = 0
    evidence_checks = 0
    seen_ids: set[str] = set()

    for receipt in receipts:
        # Dedupe by receipt_id
        if receipt.receipt_id in seen_ids:
            continue
        seen_ids.add(receipt.receipt_id)

        # Window filtering (inclusive start, exclusive end)
        if window_start is not None and receipt.timestamp < window_start:
            continue
        if window_end is not None and receipt.timestamp >= window_end:
            continue

        component = mapping.get(receipt.gate)
        if component == "tool_dispatch":
            tool_dispatch += 1
        elif component == "evidence_checks":
            evidence_checks += 1

    return ExposureComponents(
        tool_dispatch_attempts=tool_dispatch,
        evidence_checks=evidence_checks,
    )
