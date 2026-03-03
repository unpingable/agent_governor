# SPDX-License-Identifier: Apache-2.0
"""
SIGMA_RATE — endorsement-then-invalidation rate.

Tracks how often the system affirms something and later contradicts it.
Phase A is detection and counting only.

Event pairing (sigma-match-v1):
  - Endorsement: GateReceipt with verdict="pass"
  - Invalidation: GateReceipt with verdict="block" for same subject_hash
  - Link key: subject_hash (content-addressed, same subject bytes + kind tag)
  - Policy: first subsequent invalidation wins, one sigma event per endorsement
  - Duplicate endorsements for same subject_hash collapse (first endorse counts)

Denominator:
  - Preferred: EXPOSURE_PROXY value for the same window
  - Fallback: eligible_events (annotated)

Key invariants:
  - Weights/matching versioned from day one (match_rule_version)
  - Raw counts always emitted alongside rate (never rate-only)
  - missing != zero (no denominator → unavailable, not zero)
  - observe-only (no gating/policy changes)

subject_hash provenance (from gate_receipt.py):
  - Algorithm: SHA-256
  - Input: kind_tag (UTF-8) + b"\\x00" + content_bytes
  - Output: hex digest (64 chars, no prefix)
  - Kind tags include "text", "diff", "file_snapshot", "action_sequence", etc.
  - Canonical JSON: json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True)
  - Version: RECEIPT_SCHEMA_VERSION in gate_receipt.py (currently 3)
  - WARNING: changing canonicalization or hash algorithm breaks time-series
    continuity.  Bump MATCH_RULE_VERSION if subject_hash semantics change.

Window boundary semantics (shared across all Phase A signals):
  - window_start is INCLUSIVE (event.timestamp >= window_start)
  - window_end is EXCLUSIVE (event.timestamp < window_end)
  - Comparison is lexicographic on ISO 8601 UTC strings
  - Duplicate receipt_ids counted once (deduped by receipt_id)
  - Late-arriving events included if within window bounds
  - No "late arrival" concept at derivation layer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    default_source_versions,
)


# ── Match rule version ──────────────────────────────────────────────────────

MATCH_RULE_VERSION = "sigma-match-v1"

# Endorsement verdicts (receipt says "ok")
ENDORSEMENT_VERDICTS = frozenset({"pass"})

# Invalidation verdicts (receipt says "not ok")
INVALIDATION_VERDICTS = frozenset({"block"})

# Completeness value when using eligible_events as fallback denominator.
# Signals known degradation: we have a denominator, but it's not the
# preferred EXPOSURE_PROXY value.  0.8 = "computable but not ideal."
SIGMA_FALLBACK_COMPLETENESS = 0.8


# ── Event model ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SigmaEvent:
    """A single endorsement-then-invalidation event (sigma pair).

    Attributes:
        subject_hash: Content-addressed link key.
        endorsement_id: Receipt ID of the endorsing receipt.
        invalidation_id: Receipt ID of the invalidating receipt.
        endorsement_ts: ISO 8601 timestamp of endorsement.
        invalidation_ts: ISO 8601 timestamp of invalidation.
        lag_ms: Time between endorsement and invalidation in milliseconds.
    """

    subject_hash: str
    endorsement_id: str
    invalidation_id: str
    endorsement_ts: str
    invalidation_ts: str
    lag_ms: float


@dataclass(frozen=True)
class SigmaMatchResult:
    """Result of sigma pair matching over a set of events.

    Attributes:
        pairs: Matched sigma events.
        eligible_events: Total events considered for matching.
        dropped_endorsements: Endorsements with no subsequent invalidation.
        dropped_invalidations: Invalidations with no prior endorsement.
        invalid_pairs: Pairs dropped due to invariant violations (e.g. negative lag).
    """

    pairs: list[SigmaEvent] = field(default_factory=list)
    eligible_events: int = 0
    dropped_endorsements: int = 0
    dropped_invalidations: int = 0
    invalid_pairs: int = 0


# ── Pair matching ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReceiptEvent:
    """Minimal receipt representation for sigma matching.

    Callers extract these from GateReceipt or equivalent sources.
    """

    receipt_id: str
    timestamp: str           # ISO 8601 UTC
    verdict: str             # "pass" | "warn" | "block"
    subject_hash: str        # Content-addressed link key
    gate: str = ""           # Source gate (for filtering)


def _parse_ts_ms(ts: str) -> float | None:
    """Parse ISO 8601 UTC timestamp to epoch milliseconds.

    Returns None if parsing fails (caller decides how to handle).
    """
    try:
        # Handle both "Z" suffix and "+00:00"
        ts_clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_clean)
        return dt.timestamp() * 1000.0
    except (ValueError, TypeError, AttributeError):
        return None


def match_sigma_pairs(
    events: list[ReceiptEvent],
    *,
    match_rule_version: str = MATCH_RULE_VERSION,
) -> SigmaMatchResult:
    """Match endorsement→invalidation pairs from a stream of receipt events.

    Algorithm (sigma-match-v1):
      1. Sort events by timestamp (stable sort preserves receipt_id order for ties)
      2. For each subject_hash, track the first unmatched endorsement
      3. When an invalidation arrives for a subject_hash with a pending endorsement,
         form a sigma pair (first subsequent invalidation wins)
      4. Each endorsement can match at most one invalidation
      5. Negative lag (invalidation before endorsement) → invalid pair, dropped

    Args:
        events: Receipt events to match.
        match_rule_version: Version tag for the matching rules.

    Returns:
        SigmaMatchResult with matched pairs and audit counts.
    """
    # Sort by timestamp (stable)
    sorted_events = sorted(events, key=lambda e: e.timestamp)

    # Per-subject_hash: first unmatched endorsement
    pending_endorsements: dict[str, ReceiptEvent] = {}
    # Track which endorsements were consumed
    consumed_endorsement_ids: set[str] = set()

    pairs: list[SigmaEvent] = []
    invalid_count = 0
    endorsement_count = 0
    invalidation_count = 0

    for event in sorted_events:
        if event.verdict in ENDORSEMENT_VERDICTS:
            endorsement_count += 1
            # Only track the first unmatched endorsement per subject_hash
            if event.subject_hash not in pending_endorsements:
                pending_endorsements[event.subject_hash] = event

        elif event.verdict in INVALIDATION_VERDICTS:
            invalidation_count += 1
            endorsement = pending_endorsements.pop(event.subject_hash, None)
            if endorsement is not None:
                # Compute lag
                e_ms = _parse_ts_ms(endorsement.timestamp)
                i_ms = _parse_ts_ms(event.timestamp)

                if e_ms is not None and i_ms is not None:
                    lag = i_ms - e_ms
                    if lag < 0:
                        # Negative lag → invariant violation, drop pair
                        invalid_count += 1
                        continue

                    pairs.append(SigmaEvent(
                        subject_hash=event.subject_hash,
                        endorsement_id=endorsement.receipt_id,
                        invalidation_id=event.receipt_id,
                        endorsement_ts=endorsement.timestamp,
                        invalidation_ts=event.timestamp,
                        lag_ms=lag,
                    ))
                    consumed_endorsement_ids.add(endorsement.receipt_id)
                else:
                    # Unparseable timestamp → invalid
                    invalid_count += 1

    # Audit counts
    dropped_endorsements = endorsement_count - len(consumed_endorsement_ids)
    # Invalidations that didn't match any pending endorsement
    dropped_invalidations = invalidation_count - len(pairs) - invalid_count

    eligible = len(sorted_events)

    return SigmaMatchResult(
        pairs=pairs,
        eligible_events=eligible,
        dropped_endorsements=dropped_endorsements,
        dropped_invalidations=max(0, dropped_invalidations),
        invalid_pairs=invalid_count,
    )


# ── Lag statistics ──────────────────────────────────────────────────────────

def _compute_lag_stats(pairs: list[SigmaEvent]) -> dict[str, float | None]:
    """Compute mean and p95 lag from matched pairs."""
    if not pairs:
        return {"mean_lag_ms": None, "p95_lag_ms": None}

    lags = sorted(p.lag_ms for p in pairs)
    mean_lag = sum(lags) / len(lags)

    # p95: index = ceil(0.95 * n) - 1, clamped
    p95_idx = min(int(0.95 * len(lags) + 0.5), len(lags) - 1)
    p95_lag = lags[p95_idx]

    return {"mean_lag_ms": mean_lag, "p95_lag_ms": p95_lag}


# ── Derivation function ────────────────────────────────────────────────────

def derive_sigma_rate(
    match_result: SigmaMatchResult,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    exposure_proxy_value: float | None = None,
    emitter: str = "governor.signals.sigma_rate",
    emitter_version: str = "",
    session_id: str | None = None,
    source_receipt_ids: list[str] | None = None,
    source_streams: list[str] | None = None,
    source_versions: dict[str, str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive SIGMA_RATE from matched sigma pairs.

    Pure derivation — no IO. Caller provides pre-matched pairs and
    optionally the EXPOSURE_PROXY value for the same window.

    Denominator logic:
      - If exposure_proxy_value is provided and > 0 → use it
      - Else if eligible_events > 0 → use eligible_events (fallback)
      - Else → unavailable (no denominator)

    Quality logic:
      - No denominator → unavailable, value=None
      - Valid denominator + no sigma events → ok, value=0.0
      - Valid denominator + sigma events → ok, value=rate
      - Invalid pairs detected → invalid, value=None

    Args:
        match_result: Pre-computed sigma pair matching result.
        window_start: ISO 8601 UTC window start.
        window_end: ISO 8601 UTC window end.
        window_kind: Window type identifier.
        exposure_proxy_value: EXPOSURE_PROXY value for same window (preferred denominator).
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context.
        source_receipt_ids: Receipt IDs that contributed.
        source_streams: Named source streams.
        source_versions: Version info for source subsystems.
        emitted_at: Override emission timestamp.

    Returns:
        SignalEnvelope with signal_id="SIGMA_RATE".
    """
    sigma_count = len(match_result.pairs)
    lag_stats = _compute_lag_stats(match_result.pairs)

    # ── Invalid pairs detected → invalid quality ──────────────────────
    if match_result.invalid_pairs > 0:
        value: float | None = None
        quality_status = QualityStatus.INVALID.value
        quality_reasons = [
            f"invalid_pairs_detected ({match_result.invalid_pairs} pairs "
            f"with negative lag or corrupt timestamps)",
        ]
        denominator_value: float | int = 0
        denominator_type = "none"
        completeness: float | None = None
        sample_size: int | None = match_result.eligible_events or None

        return _build_envelope(
            value=value,
            quality_status=quality_status,
            quality_reasons=quality_reasons,
            sigma_count=sigma_count,
            match_result=match_result,
            denominator_value=denominator_value,
            denominator_type=denominator_type,
            lag_stats=lag_stats,
            completeness=completeness,
            sample_size=sample_size,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            source_receipt_ids=source_receipt_ids,
            source_streams=source_streams,
            source_versions=source_versions,
            emitted_at=emitted_at,
        )

    # ── Denominator selection ─────────────────────────────────────────
    if exposure_proxy_value is not None and exposure_proxy_value > 0:
        denominator_value = exposure_proxy_value
        denominator_type = "exposure_proxy"
    elif match_result.eligible_events > 0:
        denominator_value = match_result.eligible_events
        denominator_type = "eligible_events"
    else:
        # No denominator → unavailable
        return _build_envelope(
            value=None,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=["no_denominator"],
            sigma_count=0,
            match_result=match_result,
            denominator_value=0,
            denominator_type="none",
            lag_stats=lag_stats,
            completeness=None,
            sample_size=None,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            source_receipt_ids=source_receipt_ids,
            source_streams=source_streams,
            source_versions=source_versions,
            emitted_at=emitted_at,
        )

    # ── Compute rate ──────────────────────────────────────────────────
    rate = sigma_count / denominator_value if denominator_value > 0 else 0.0

    # ── Quality ───────────────────────────────────────────────────────
    quality_reasons_list: list[str] = []
    if denominator_type == "eligible_events":
        quality_reasons_list.append("fallback_denominator_used")

    if quality_reasons_list:
        quality_status = QualityStatus.PARTIAL.value
        completeness_val = SIGMA_FALLBACK_COMPLETENESS
    else:
        quality_status = QualityStatus.OK.value
        completeness_val = 1.0

    return _build_envelope(
        value=rate,
        quality_status=quality_status,
        quality_reasons=quality_reasons_list,
        sigma_count=sigma_count,
        match_result=match_result,
        denominator_value=denominator_value,
        denominator_type=denominator_type,
        lag_stats=lag_stats,
        completeness=completeness_val,
        sample_size=match_result.eligible_events,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        emitter=emitter,
        emitter_version=emitter_version,
        session_id=session_id,
        source_receipt_ids=source_receipt_ids,
        source_streams=source_streams,
        source_versions=source_versions,
        emitted_at=emitted_at,
    )


def _build_envelope(
    *,
    value: float | None,
    quality_status: str,
    quality_reasons: list[str],
    sigma_count: int,
    match_result: SigmaMatchResult,
    denominator_value: float | int,
    denominator_type: str,
    lag_stats: dict[str, float | None],
    completeness: float | None,
    sample_size: int | None,
    window_start: str,
    window_end: str,
    window_kind: str,
    emitter: str,
    emitter_version: str,
    session_id: str | None,
    source_receipt_ids: list[str] | None,
    source_streams: list[str] | None,
    source_versions: dict[str, str] | None,
    emitted_at: str | None,
) -> SignalEnvelope:
    """Internal helper to build the SignalEnvelope."""
    values: dict[str, Any] = {
        "sigma_events": sigma_count,
        "eligible_events": match_result.eligible_events,
        "denominator_value": denominator_value,
        "denominator_type": denominator_type,
        "match_rule_version": MATCH_RULE_VERSION,
        "mean_lag_ms": lag_stats["mean_lag_ms"],
        "p95_lag_ms": lag_stats["p95_lag_ms"],
        "matched_pairs_count": sigma_count,
        "dropped_endorsements": match_result.dropped_endorsements,
        "dropped_invalidations": match_result.dropped_invalidations,
        "invalid_pairs_count": match_result.invalid_pairs,
    }

    annotations: dict[str, Any] = {
        "match_rule_version": MATCH_RULE_VERSION,
    }
    if denominator_type == "eligible_events":
        annotations["denominator_fallback"] = True

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="SIGMA_RATE",
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        subject_id=f"win_{window_start}_{window_kind}",
        session_id=session_id,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="rate",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=sample_size,
        completeness=completeness,
        source_receipt_ids=source_receipt_ids or [],
        source_streams=source_streams or [],
        source_versions=source_versions if source_versions is not None else default_source_versions(),
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="sigma-rate-v1",
        annotations=annotations,
    )
