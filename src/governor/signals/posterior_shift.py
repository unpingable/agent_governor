# SPDX-License-Identifier: Apache-2.0
r"""
POSTERIOR_SHIFT_ATTRIBUTION — leave-one-out influence at the A-signal level.

Answers: "How much does each Phase A signal influence the B1 diagnostic?"
by *removing* each signal and recomputing the entire B1 derivation.

Phase B3: consumes Phase A signal envelopes + the B1 CAPTURE_SELF_DIAGNOSTIC.
Uses the B1 derivation function itself for recomputation — no shortcuts.

Attribution method: loo_influence_v1 (leave-one-out).

Algorithm:
  Let S = {A1, A2, A3} (Phase A signals used by B1)
  score_full = B1(S).capture_decline_score
  For each signal s in S:
    score_minus = B1(S \ {s}).capture_decline_score
    delta_raw[s] = score_full - score_minus

  If calibration is provided:
    cal_full = cal(score_full)
    For each s: cal_minus[s] = cal(score_minus[s])
    delta_cal[s] = cal_full - cal_minus[s]

Key invariants:
  - Removal semantics: "remove signal" means remove from DiagnosticInputs
    and RECOMPUTE everything. No shortcuts. No subtracting a term.
  - Non-conservation: LOO deltas DO NOT sum to total shift. That's correct.
    Deltas are influences, not partitions. Normalized via |delta| mass.
  - Determinism: same input set → identical rankings + deltas
  - Degenerates: empty set, singleton, None scores
  - Stability: removing a signal not used by scoring yields delta=0
  - Compute cost: n+1 B1 derivations (always explicit)

Output schema:
  signal_id: POSTERIOR_SHIFT_ATTRIBUTION
  value: total delta mass (sum of |delta_raw|), or None if not computable
  unit: "influence"
  values: {
    method, score_full, classification_full,
    influences: [{signal_id, score_full, score_minus,
                   delta_raw, direction, rank,
                   classification_minus,
                   delta_cal, cal_full, cal_minus (if applicable)}],
    n_signals, compute_cost, config_version,
    influence_mass, normalized (bool)
  }

Design authority: B3 was originally deferred from v2.4B to post-calibration;
shipped in 9546b33 after Phase C proved stable.
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


# ── Config ────────────────────────────────────────────────────────────────

ATTRIBUTION_CONFIG_VERSION = "posterior-shift-v1"
ATTRIBUTION_METHOD = "loo_influence_v1"

# Float comparison tolerance
EPSILON = 1e-9


# ── Influence model ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Influence:
    """One signal's leave-one-out influence on the B1 diagnostic."""

    signal_id: str            # "EXPOSURE_PROXY" | "SILENT_SUPPRESSION" | "SIGMA_RATE"
    score_full: float | None  # B1 score with all signals
    score_minus: float | None  # B1 score without this signal
    delta_raw: float | None   # score_full - score_minus (None if either is None)
    classification_full: str | None
    classification_minus: str | None
    direction: str            # "increase" | "decrease" | "unchanged" | "indeterminate"
    rank: int                 # 1 = largest |delta|, ties broken by signal_id

    # Optional calibration fields (None if no calibration provided)
    cal_full: float | None = None
    cal_minus: float | None = None
    delta_cal: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "signal_id": self.signal_id,
            "score_full": self.score_full,
            "score_minus": self.score_minus,
            "delta_raw": self.delta_raw,
            "classification_full": self.classification_full,
            "classification_minus": self.classification_minus,
            "direction": self.direction,
            "rank": self.rank,
        }
        if self.cal_full is not None or self.delta_cal is not None:
            d["cal_full"] = self.cal_full
            d["cal_minus"] = self.cal_minus
            d["delta_cal"] = self.delta_cal
        return d


# ── LOO computation ───────────────────────────────────────────────────────

def _direction(delta: float | None) -> str:
    if delta is None:
        return "indeterminate"
    if delta > EPSILON:
        return "increase"
    if delta < -EPSILON:
        return "decrease"
    return "unchanged"


def _recompute_b1_score(
    a1: SignalEnvelope | None,
    a2: SignalEnvelope | None,
    a3: SignalEnvelope | None,
    window_start: str,
    window_end: str,
    window_kind: str,
) -> tuple[float | None, str | None]:
    """Recompute B1 and return (score, classification).

    Uses the actual B1 derivation function — no shortcuts.
    """
    from .capture_self_diagnostic import (
        DiagnosticInputs,
        derive_capture_self_diagnostic,
    )

    env = derive_capture_self_diagnostic(
        DiagnosticInputs(
            a1_exposure_proxy=a1,
            a2_silent_suppression=a2,
            a3_sigma_rate=a3,
        ),
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        emitted_at=window_end,
    )
    vals = env.values or {}
    return vals.get("capture_decline_score"), vals.get("classification")


def compute_loo_influences(
    a1: SignalEnvelope | None,
    a2: SignalEnvelope | None,
    a3: SignalEnvelope | None,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    calibrate: Any | None = None,  # callable: float → float (optional)
) -> list[Influence]:
    """Compute leave-one-out influences for each Phase A signal.

    Pure function. Performs n+1 B1 derivations (1 full + n leave-one-out).

    Args:
        a1: Phase A1 EXPOSURE_PROXY envelope (or None).
        a2: Phase A2 SILENT_SUPPRESSION envelope (or None).
        a3: Phase A3 SIGMA_RATE envelope (or None).
        window_start: ISO 8601 UTC.
        window_end: ISO 8601 UTC.
        window_kind: Window type.
        calibrate: Optional calibration function (score → calibrated_score).

    Returns:
        List of Influence objects, ranked by |delta_raw| descending.
    """
    # Full computation
    score_full, class_full = _recompute_b1_score(
        a1, a2, a3, window_start, window_end, window_kind,
    )

    cal_full = calibrate(score_full) if calibrate and score_full is not None else None

    # Define signal set with their removal variants
    signals: list[tuple[str, SignalEnvelope | None]] = []
    if a1 is not None:
        signals.append(("EXPOSURE_PROXY", a1))
    if a2 is not None:
        signals.append(("SILENT_SUPPRESSION", a2))
    if a3 is not None:
        signals.append(("SIGMA_RATE", a3))

    # Leave-one-out: remove each signal and recompute
    raw_influences: list[tuple[str, float | None, str | None]] = []

    for sig_id, _env in signals:
        # Build input set with this signal removed
        loo_a1 = None if sig_id == "EXPOSURE_PROXY" else a1
        loo_a2 = None if sig_id == "SILENT_SUPPRESSION" else a2
        loo_a3 = None if sig_id == "SIGMA_RATE" else a3

        score_minus, class_minus = _recompute_b1_score(
            loo_a1, loo_a2, loo_a3, window_start, window_end, window_kind,
        )
        raw_influences.append((sig_id, score_minus, class_minus))

    # Compute deltas and rank
    deltas: list[tuple[str, float | None, float | None, str | None, float | None, float | None, float | None]] = []

    for sig_id, score_minus, class_minus in raw_influences:
        if score_full is not None and score_minus is not None:
            delta_raw = score_full - score_minus
        else:
            delta_raw = None

        # Calibrated deltas
        if calibrate and score_minus is not None:
            cal_minus = calibrate(score_minus)
            delta_cal = (cal_full - cal_minus) if cal_full is not None and cal_minus is not None else None
        else:
            cal_minus = None
            delta_cal = None

        deltas.append((sig_id, score_minus, delta_raw, class_minus, cal_minus, delta_cal, cal_full))

    # Rank by |delta_raw| descending, ties broken by signal_id alphabetical
    ranked = sorted(
        deltas,
        key=lambda x: (-abs(x[2]) if x[2] is not None else 0.0, x[0]),
    )

    influences: list[Influence] = []
    for rank_idx, (sig_id, score_minus, delta_raw, class_minus, cal_minus, delta_cal, cf) in enumerate(ranked):
        influences.append(Influence(
            signal_id=sig_id,
            score_full=score_full,
            score_minus=score_minus,
            delta_raw=delta_raw,
            classification_full=class_full,
            classification_minus=class_minus,
            direction=_direction(delta_raw),
            rank=rank_idx + 1,
            cal_full=cf,
            cal_minus=cal_minus,
            delta_cal=delta_cal,
        ))

    return influences


# ── Derivation function ──────────────────────────────────────────────────

def derive_posterior_shift(
    a1: SignalEnvelope | None,
    a2: SignalEnvelope | None,
    a3: SignalEnvelope | None,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    calibrate: Any | None = None,
    emitter: str = "governor.signals.posterior_shift",
    emitter_version: str = "",
    session_id: str | None = None,
    source_receipt_ids: list[str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive POSTERIOR_SHIFT_ATTRIBUTION via leave-one-out influence.

    Pure derivation — no IO (except n+1 B1 recomputations).

    Args:
        a1: Phase A1 EXPOSURE_PROXY envelope (or None).
        a2: Phase A2 SILENT_SUPPRESSION envelope (or None).
        a3: Phase A3 SIGMA_RATE envelope (or None).
        window_start: ISO 8601 UTC.
        window_end: ISO 8601 UTC.
        window_kind: Window type.
        calibrate: Optional calibration function (score → calibrated_score).
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context.
        source_receipt_ids: Receipt IDs from upstream signals.
        emitted_at: Override emission timestamp.

    Returns:
        SignalEnvelope with signal_id="POSTERIOR_SHIFT_ATTRIBUTION".
    """
    influences = compute_loo_influences(
        a1, a2, a3,
        window_start, window_end, window_kind,
        calibrate=calibrate,
    )

    # Count input signals present
    n_signals = sum(1 for s in (a1, a2, a3) if s is not None)
    compute_cost = n_signals + 1  # full + n LOO

    # Compute score_full from first influence (all have same value)
    score_full = influences[0].score_full if influences else None
    class_full = influences[0].classification_full if influences else None

    # Influence mass = sum(|delta_raw|)
    raw_deltas = [inf.delta_raw for inf in influences if inf.delta_raw is not None]
    influence_mass = sum(abs(d) for d in raw_deltas) if raw_deltas else None

    # Quality logic
    if score_full is None:
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["score_not_computable"]
        value = None
    elif not influences:
        quality_status = QualityStatus.UNAVAILABLE.value
        quality_reasons = ["no_input_signals"]
        value = None
    else:
        quality_status = QualityStatus.OK.value
        quality_reasons = []
        value = influence_mass

    # Provenance: union receipt IDs from all input signals
    propagated_receipt_ids: list[str] = list(source_receipt_ids or [])
    for env in (a1, a2, a3):
        if env is not None:
            propagated_receipt_ids.extend(env.source_receipt_ids)

    # Source streams
    source_streams: list[str] = []
    if a1 is not None:
        source_streams.append("EXPOSURE_PROXY")
    if a2 is not None:
        source_streams.append("SILENT_SUPPRESSION")
    if a3 is not None:
        source_streams.append("SIGMA_RATE")

    # Completeness from inputs
    completeness_values = [
        env.completeness
        for env in (a1, a2, a3)
        if env is not None and env.completeness is not None
    ]
    completeness = min(completeness_values) if completeness_values else None

    # Annotations
    annotations: dict[str, Any] = {
        "config_version": ATTRIBUTION_CONFIG_VERSION,
        "method": ATTRIBUTION_METHOD,
        "a1_content_hash": a1.content_hash() if a1 else None,
        "a2_content_hash": a2.content_hash() if a2 else None,
        "a3_content_hash": a3.content_hash() if a3 else None,
        "has_calibration": calibrate is not None,
    }

    # Values dict
    values: dict[str, Any] = {
        "method": ATTRIBUTION_METHOD,
        "score_full": score_full,
        "classification_full": class_full,
        "influences": [inf.to_dict() for inf in influences],
        "n_signals": n_signals,
        "compute_cost": compute_cost,
        "influence_mass": influence_mass,
        "config_version": ATTRIBUTION_CONFIG_VERSION,
    }

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="POSTERIOR_SHIFT_ATTRIBUTION",
        signal_version=1,
        phase="2.4B",
        subject_type="window",
        subject_id=f"attr_{window_start}_{window_kind}",
        session_id=session_id,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="influence",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=n_signals or None,
        completeness=completeness,
        source_receipt_ids=propagated_receipt_ids,
        source_streams=source_streams,
        source_versions=default_source_versions(),
        derivation=DerivationType.DERIVED.value,
        derivation_version=ATTRIBUTION_CONFIG_VERSION,
        annotations=annotations,
    )
