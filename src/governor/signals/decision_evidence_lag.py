# SPDX-License-Identifier: Apache-2.0
"""
DECISION_EVIDENCE_LAG — per-decision timing classification.

When a decision was made, was the evidence that justifies it available
*before* the decision, or was it backfilled afterwards?

Derivation source: gate receipt pairs (decision + evidence) from the
receipt store.  NOT from Phase A signals.  B2 is parallel to B1.

Per-decision classifications:
  SUPPORTED_AS_OF  — evidence existed before decision
  BACKFILLED       — evidence arrived after decision
  UNSUPPORTED      — no linked evidence found
  POLICY_EXEMPT    — decision gate is policy-exempt

Key invariants:
  - observed_at vs effective_at: ingestion lag ≠ backfill
  - Same-timestamp → SUPPORTED_AS_OF (tie-break toward support)
  - Multiple evidence → earliest wins
  - Policy-exempt excluded from denominator
  - Observe-only (no blocking)
  - Missing ≠ zero

Design authority: specs/gaps/V2_4B_DECISION_EVIDENCE_LAG.md
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


# ── Config (decision-evidence-lag-v1) ──────────────────────────────────────

LAG_CONFIG_VERSION = "decision-evidence-lag-v1"

# Gates that produce decisions (receipts from these are "decision receipts")
DECISION_GATES: frozenset[str] = frozenset({
    "evidence_gate",
    "chain_composition",
    "pre_commit",
    "scope_escalation",
})

# Gates that are policy-exempt (decisions don't need evidence backing)
POLICY_EXEMPT_GATES: frozenset[str] = frozenset({
    "intent_compiler",
})

# Decision verdicts (any verdict from a decision gate counts)
DECISION_VERDICTS: frozenset[str] = frozenset({"pass", "warn", "block"})


# ── Per-decision classifications ──────────────────────────────────────────

CLASSIFICATION_SUPPORTED = "SUPPORTED_AS_OF"
CLASSIFICATION_BACKFILLED = "BACKFILLED"
CLASSIFICATION_UNSUPPORTED = "UNSUPPORTED"
CLASSIFICATION_POLICY_EXEMPT = "POLICY_EXEMPT"

ALL_CLASSIFICATIONS = frozenset({
    CLASSIFICATION_SUPPORTED,
    CLASSIFICATION_BACKFILLED,
    CLASSIFICATION_UNSUPPORTED,
    CLASSIFICATION_POLICY_EXEMPT,
})


# ── Input model ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReceiptRecord:
    """Minimal receipt representation for lag analysis.

    Callers extract these from GateReceipt or equivalent sources.
    """

    receipt_id: str
    timestamp: str       # ISO 8601 UTC (effective_at)
    gate: str
    verdict: str         # "pass" | "warn" | "block"
    subject_hash: str


@dataclass(frozen=True)
class DecisionClassification:
    """Per-decision classification result."""

    decision_id: str           # receipt_id of the decision
    classification: str        # one of ALL_CLASSIFICATIONS
    subject_hash: str
    decision_ts: str           # decision timestamp
    evidence_id: str | None = None   # receipt_id of linked evidence (if any)
    evidence_ts: str | None = None   # evidence timestamp (if any)
    backfill_delay_ms: float | None = None    # for BACKFILLED
    support_staleness_ms: float | None = None # for SUPPORTED_AS_OF


@dataclass(frozen=True)
class LagAggregateResult:
    """Aggregated lag statistics across a window of decisions."""

    classifications: list[DecisionClassification] = field(default_factory=list)
    total_decisions: int = 0
    supported_count: int = 0
    backfilled_count: int = 0
    unsupported_count: int = 0
    policy_exempt_count: int = 0
    unparseable_count: int = 0  # decisions with unparseable timestamps


# ── Timestamp parsing ──────────────────────────────────────────────────────

def _parse_ts_ms(ts: str) -> float | None:
    """Parse ISO 8601 UTC timestamp to epoch milliseconds.

    Returns None if parsing fails.
    """
    try:
        ts_clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_clean)
        return dt.timestamp() * 1000.0
    except (ValueError, TypeError, AttributeError):
        return None


# ── Per-decision classification ────────────────────────────────────────────

def classify_decisions(
    receipts: list[ReceiptRecord],
    *,
    decision_gates: frozenset[str] | None = None,
    policy_exempt_gates: frozenset[str] | None = None,
) -> LagAggregateResult:
    """Classify each decision receipt's evidence timing.

    Algorithm:
      1. Separate receipts into decisions and evidence by gate
      2. Build evidence index: subject_hash → list of (timestamp_ms, receipt)
      3. For each decision:
         a. If gate is policy-exempt → POLICY_EXEMPT
         b. Find evidence with matching subject_hash
         c. If no evidence → UNSUPPORTED
         d. If earliest evidence.effective_at <= decision.effective_at → SUPPORTED_AS_OF
         e. If earliest evidence.effective_at > decision.effective_at → BACKFILLED

    Args:
        receipts: All receipts in the window (decisions + evidence).
        decision_gates: Override decision gate set.
        policy_exempt_gates: Override policy-exempt gate set.

    Returns:
        LagAggregateResult with per-decision classifications.
    """
    d_gates = decision_gates if decision_gates is not None else DECISION_GATES
    pe_gates = policy_exempt_gates if policy_exempt_gates is not None else POLICY_EXEMPT_GATES

    # ── Separate decisions from evidence ────────────────────────────────
    decisions: list[ReceiptRecord] = []
    # Evidence index: subject_hash → list of (ts_ms, receipt)
    evidence_by_subject: dict[str, list[tuple[float, ReceiptRecord]]] = {}

    seen_ids: set[str] = set()
    for r in receipts:
        if r.receipt_id in seen_ids:
            continue
        seen_ids.add(r.receipt_id)

        if r.gate in d_gates and r.verdict in DECISION_VERDICTS:
            decisions.append(r)

        # All receipts can serve as evidence (including from non-decision gates)
        ts_ms = _parse_ts_ms(r.timestamp)
        if ts_ms is not None:
            evidence_by_subject.setdefault(r.subject_hash, []).append(
                (ts_ms, r)
            )

    # ── Classify each decision ──────────────────────────────────────────
    classifications: list[DecisionClassification] = []
    unparseable = 0

    for dec in decisions:
        # Policy exempt?
        if dec.gate in pe_gates:
            classifications.append(DecisionClassification(
                decision_id=dec.receipt_id,
                classification=CLASSIFICATION_POLICY_EXEMPT,
                subject_hash=dec.subject_hash,
                decision_ts=dec.timestamp,
            ))
            continue

        # Parse decision timestamp
        dec_ms = _parse_ts_ms(dec.timestamp)
        if dec_ms is None:
            unparseable += 1
            classifications.append(DecisionClassification(
                decision_id=dec.receipt_id,
                classification=CLASSIFICATION_UNSUPPORTED,
                subject_hash=dec.subject_hash,
                decision_ts=dec.timestamp,
            ))
            continue

        # Find evidence with matching subject_hash
        evidence_list = evidence_by_subject.get(dec.subject_hash, [])

        # Exclude the decision receipt itself from evidence
        evidence_candidates = [
            (ts_ms, r) for ts_ms, r in evidence_list
            if r.receipt_id != dec.receipt_id
        ]

        if not evidence_candidates:
            classifications.append(DecisionClassification(
                decision_id=dec.receipt_id,
                classification=CLASSIFICATION_UNSUPPORTED,
                subject_hash=dec.subject_hash,
                decision_ts=dec.timestamp,
            ))
            continue

        # Sort by timestamp, take earliest
        evidence_candidates.sort(key=lambda x: x[0])
        earliest_ts_ms, earliest_evidence = evidence_candidates[0]

        # Classify: <= means supported (tie-break toward support)
        if earliest_ts_ms <= dec_ms:
            staleness = dec_ms - earliest_ts_ms
            classifications.append(DecisionClassification(
                decision_id=dec.receipt_id,
                classification=CLASSIFICATION_SUPPORTED,
                subject_hash=dec.subject_hash,
                decision_ts=dec.timestamp,
                evidence_id=earliest_evidence.receipt_id,
                evidence_ts=earliest_evidence.timestamp,
                support_staleness_ms=staleness,
            ))
        else:
            delay = earliest_ts_ms - dec_ms
            classifications.append(DecisionClassification(
                decision_id=dec.receipt_id,
                classification=CLASSIFICATION_BACKFILLED,
                subject_hash=dec.subject_hash,
                decision_ts=dec.timestamp,
                evidence_id=earliest_evidence.receipt_id,
                evidence_ts=earliest_evidence.timestamp,
                backfill_delay_ms=delay,
            ))

    # ── Aggregate ───────────────────────────────────────────────────────
    supported = sum(1 for c in classifications if c.classification == CLASSIFICATION_SUPPORTED)
    backfilled = sum(1 for c in classifications if c.classification == CLASSIFICATION_BACKFILLED)
    unsupported = sum(1 for c in classifications if c.classification == CLASSIFICATION_UNSUPPORTED)
    policy_exempt = sum(1 for c in classifications if c.classification == CLASSIFICATION_POLICY_EXEMPT)

    return LagAggregateResult(
        classifications=classifications,
        total_decisions=len(classifications),
        supported_count=supported,
        backfilled_count=backfilled,
        unsupported_count=unsupported,
        policy_exempt_count=policy_exempt,
        unparseable_count=unparseable,
    )


# ── Lag statistics ──────────────────────────────────────────────────────

def _compute_lag_stats(
    values: list[float],
) -> tuple[float | None, float | None]:
    """Compute mean and p95 from a list of values."""
    if not values:
        return None, None
    mean = sum(values) / len(values)
    sorted_vals = sorted(values)
    p95_idx = min(int(0.95 * len(sorted_vals) + 0.5), len(sorted_vals) - 1)
    return mean, sorted_vals[p95_idx]


# ── Derivation function ───────────────────────────────────────────────────

def derive_decision_evidence_lag(
    receipts: list[ReceiptRecord],
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    decision_gates: frozenset[str] | None = None,
    policy_exempt_gates: frozenset[str] | None = None,
    emitter: str = "governor.signals.decision_evidence_lag",
    emitter_version: str = "",
    session_id: str | None = None,
    source_receipt_ids: list[str] | None = None,
    source_streams: list[str] | None = None,
    source_versions: dict[str, str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive DECISION_EVIDENCE_LAG from gate receipts in a window.

    Pure derivation — reads receipt data in, produces SignalEnvelope out.

    Value semantics:
      value = backfill_rate (backfilled / classifiable_decisions)
      0.0 = all decisions supported or unsupported (no backfill)
      None = no decisions in window (unavailable)

    Args:
        receipts: All receipts in the window.
        window_start: ISO 8601 UTC window start.
        window_end: ISO 8601 UTC window end.
        window_kind: Window type identifier.
        decision_gates: Override decision gate set.
        policy_exempt_gates: Override policy-exempt gate set.
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context.
        source_receipt_ids: Receipt IDs that contributed.
        source_streams: Named source streams.
        source_versions: Version info for source subsystems.
        emitted_at: Override emission timestamp.

    Returns:
        SignalEnvelope with signal_id="DECISION_EVIDENCE_LAG".
    """
    d_gates = decision_gates if decision_gates is not None else DECISION_GATES
    pe_gates = policy_exempt_gates if policy_exempt_gates is not None else POLICY_EXEMPT_GATES

    # Window-filter receipts (inclusive start, exclusive end)
    windowed: list[ReceiptRecord] = []
    for r in receipts:
        if r.timestamp >= window_start and r.timestamp < window_end:
            windowed.append(r)
        # Also include evidence from before the window (needed for linking)
        elif r.timestamp < window_start:
            # Include pre-window evidence for linking to in-window decisions
            windowed.append(r)

    result = classify_decisions(
        windowed,
        decision_gates=d_gates,
        policy_exempt_gates=pe_gates,
    )

    # ── No decisions → unavailable ──────────────────────────────────────
    if result.total_decisions == 0:
        return _build_envelope(
            value=None,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=["no_decisions_in_window"],
            completeness=None,
            sample_size=None,
            result=result,
            d_gates=d_gates,
            pe_gates=pe_gates,
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

    # ── Compute rates ───────────────────────────────────────────────────
    classifiable = (
        result.supported_count
        + result.backfilled_count
        + result.unsupported_count
    )

    if classifiable > 0:
        backfill_rate: float | None = result.backfilled_count / classifiable
        unsupported_rate: float | None = result.unsupported_count / classifiable
    else:
        # All policy-exempt
        backfill_rate = None
        unsupported_rate = None

    # ── Lag statistics ──────────────────────────────────────────────────
    backfill_delays = [
        c.backfill_delay_ms for c in result.classifications
        if c.backfill_delay_ms is not None
    ]
    staleness_values = [
        c.support_staleness_ms for c in result.classifications
        if c.support_staleness_ms is not None
    ]

    mean_backfill, p95_backfill = _compute_lag_stats(backfill_delays)
    mean_staleness, p95_staleness = _compute_lag_stats(staleness_values)

    # ── Quality ─────────────────────────────────────────────────────────
    quality_reasons: list[str] = []
    if result.unparseable_count > 0:
        quality_reasons.append(
            f"unparseable_timestamps ({result.unparseable_count} decisions)"
        )

    if quality_reasons:
        quality_status = QualityStatus.PARTIAL.value
        comp = 1.0 - (result.unparseable_count / result.total_decisions)
    elif classifiable == 0:
        quality_status = QualityStatus.OK.value
        comp = 1.0
    else:
        quality_status = QualityStatus.OK.value
        comp = 1.0

    return _build_envelope(
        value=backfill_rate,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        completeness=comp,
        sample_size=result.total_decisions,
        result=result,
        d_gates=d_gates,
        pe_gates=pe_gates,
        backfill_rate=backfill_rate,
        unsupported_rate=unsupported_rate,
        mean_backfill_delay_ms=mean_backfill,
        p95_backfill_delay_ms=p95_backfill,
        mean_support_staleness_ms=mean_staleness,
        p95_support_staleness_ms=p95_staleness,
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
    completeness: float | None,
    sample_size: int | None,
    result: LagAggregateResult,
    d_gates: frozenset[str],
    pe_gates: frozenset[str],
    backfill_rate: float | None = None,
    unsupported_rate: float | None = None,
    mean_backfill_delay_ms: float | None = None,
    p95_backfill_delay_ms: float | None = None,
    mean_support_staleness_ms: float | None = None,
    p95_support_staleness_ms: float | None = None,
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
    """Internal helper to build the output SignalEnvelope."""
    classifiable = (
        result.supported_count + result.backfilled_count + result.unsupported_count
    )

    values: dict[str, Any] = {
        "total_decisions": result.total_decisions,
        "classifiable_decisions": classifiable,
        "supported_count": result.supported_count,
        "backfilled_count": result.backfilled_count,
        "unsupported_count": result.unsupported_count,
        "policy_exempt_count": result.policy_exempt_count,
        "backfill_rate": backfill_rate,
        "unsupported_rate": unsupported_rate,
        "mean_backfill_delay_ms": mean_backfill_delay_ms,
        "p95_backfill_delay_ms": p95_backfill_delay_ms,
        "mean_support_staleness_ms": mean_support_staleness_ms,
        "p95_support_staleness_ms": p95_support_staleness_ms,
        "config_version": LAG_CONFIG_VERSION,
    }

    annotations: dict[str, Any] = {
        "config_version": LAG_CONFIG_VERSION,
        "decision_gates": sorted(d_gates),
        "policy_exempt_gates": sorted(pe_gates),
    }

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="DECISION_EVIDENCE_LAG",
        signal_version=1,
        phase="2.4B",
        subject_type="window",
        subject_id=f"lag_{window_start}_{window_kind}",
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
        derivation_version=LAG_CONFIG_VERSION,
        annotations=annotations,
    )
