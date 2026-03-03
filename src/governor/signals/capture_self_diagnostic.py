# SPDX-License-Identifier: Apache-2.0
"""
CAPTURE_SELF_DIAGNOSTIC — advisory windowed diagnostic over Phase A signals.

Answers: "Is the instrumentation spine itself operating correctly, and
does it see signs of capture?"

Phase B1: consumes Phase A signal envelopes only (EXPOSURE_PROXY,
SILENT_SUPPRESSION, SIGMA_RATE).  Does NOT read raw receipts, daemon
state, or receipt stores.

Classifications:
  normal                     — healthy, no capture signal
  watch                      — mild anomaly, not actionable yet
  warning                    — elevated capture signal
  instrumentation_compromised — A2 says instrumentation is dark
  insufficient_history       — not enough data to classify
  indeterminate              — conflicting signals

Key invariants:
  - B consumes A signal envelopes only (layering invariant)
  - Suppression beats capture (A2 precedence)
  - Observe-only (no blocking, no policy changes)
  - Missing != zero
  - Threshold config versioned (DIAG_CONFIG_VERSION)

Design authority: specs/gaps/V2_4B_CAPTURE_SELF_DIAGNOSTIC.md
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


# ── Classifications ────────────────────────────────────────────────────────

CLASSIFICATION_NORMAL = "normal"
CLASSIFICATION_WATCH = "watch"
CLASSIFICATION_WARNING = "warning"
CLASSIFICATION_INSTRUMENTATION_COMPROMISED = "instrumentation_compromised"
CLASSIFICATION_INSUFFICIENT_HISTORY = "insufficient_history"
CLASSIFICATION_INDETERMINATE = "indeterminate"

ALL_CLASSIFICATIONS = frozenset({
    CLASSIFICATION_NORMAL,
    CLASSIFICATION_WATCH,
    CLASSIFICATION_WARNING,
    CLASSIFICATION_INSTRUMENTATION_COMPROMISED,
    CLASSIFICATION_INSUFFICIENT_HISTORY,
    CLASSIFICATION_INDETERMINATE,
})


# ── Threshold config (capture-selfdiag-v1) ─────────────────────────────────
#
# All thresholds are named constants.  Changing any value below MUST bump
# DIAG_CONFIG_VERSION.  Downstream consumers (dashboards, alerting) depend
# on consistent semantics.

DIAG_CONFIG_VERSION = "capture-selfdiag-v1"

# Sigma rate contribution
SIGMA_WEIGHT = 0.7
SIGMA_RATE_CEILING = 0.5       # sigma rate at which sigma_score maxes out at 1.0

# Invalid pairs penalty (from A3)
INVALID_PAIRS_PENALTY = 0.2
INVALID_PAIRS_PENALTY_WEIGHT = 0.1

# Exposure coverage contribution
COVERAGE_WEIGHT = 0.3
LOW_COVERAGE_THRESHOLD = 0.5   # below this, low coverage contributes to score

# Classification thresholds
WATCH_THRESHOLD = 0.1
WARNING_THRESHOLD = 0.4


# ── Input model ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DiagnosticInputs:
    """Phase A signal envelopes for a single window.

    All inputs should share the same window_start/window_end/window_kind.
    A2 (suppression) is required; A1 and A3 are optional but degrade quality.
    """

    a1_exposure_proxy: SignalEnvelope | None = None
    a2_silent_suppression: SignalEnvelope | None = None
    a3_sigma_rate: SignalEnvelope | None = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _validate_window_alignment(inputs: DiagnosticInputs) -> list[str]:
    """Check that all present inputs share the same window.

    Returns list of error strings (empty = valid).
    """
    envelopes = []
    labels = []
    if inputs.a1_exposure_proxy is not None:
        envelopes.append(inputs.a1_exposure_proxy)
        labels.append("A1")
    if inputs.a2_silent_suppression is not None:
        envelopes.append(inputs.a2_silent_suppression)
        labels.append("A2")
    if inputs.a3_sigma_rate is not None:
        envelopes.append(inputs.a3_sigma_rate)
        labels.append("A3")

    if len(envelopes) < 2:
        return []  # nothing to compare

    ref = envelopes[0]
    errors = []
    for i, env in enumerate(envelopes[1:], 1):
        if env.window_start != ref.window_start:
            errors.append(
                f"window_start mismatch: {labels[0]}={ref.window_start} vs "
                f"{labels[i]}={env.window_start}"
            )
        if env.window_end != ref.window_end:
            errors.append(
                f"window_end mismatch: {labels[0]}={ref.window_end} vs "
                f"{labels[i]}={env.window_end}"
            )
        if env.window_kind != ref.window_kind:
            errors.append(
                f"window_kind mismatch: {labels[0]}={ref.window_kind} vs "
                f"{labels[i]}={env.window_kind}"
            )
    return errors


def _extract_a1(env: SignalEnvelope | None) -> dict[str, Any]:
    """Extract A1 fields needed for scoring."""
    if env is None:
        return {
            "value": None,
            "quality_status": "unavailable",
            "coverage_ratio": 0.0,
            "completeness": None,
            "content_hash": None,
        }
    return {
        "value": env.value,
        "quality_status": env.quality_status,
        "coverage_ratio": env.values.get("coverage_ratio", 0.0),
        "completeness": env.completeness,
        "content_hash": env.content_hash(),
    }


def _extract_a2(env: SignalEnvelope | None) -> dict[str, Any]:
    """Extract A2 fields needed for scoring."""
    if env is None:
        return {
            "value": None,
            "quality_status": "unavailable",
            "classification": "unknown",
            "completeness": None,
            "content_hash": None,
        }
    return {
        "value": env.value,
        "quality_status": env.quality_status,
        "classification": env.annotations.get("classification", "unknown"),
        "completeness": env.completeness,
        "content_hash": env.content_hash(),
    }


def _extract_a3(env: SignalEnvelope | None) -> dict[str, Any]:
    """Extract A3 fields needed for scoring."""
    if env is None:
        return {
            "value": None,
            "quality_status": "unavailable",
            "sigma_events": 0,
            "invalid_pairs_count": 0,
            "denominator_type": "none",
            "completeness": None,
            "content_hash": None,
        }
    return {
        "value": env.value,
        "quality_status": env.quality_status,
        "sigma_events": env.values.get("sigma_events", 0),
        "invalid_pairs_count": env.values.get("invalid_pairs_count", 0),
        "denominator_type": env.values.get("denominator_type", "none"),
        "completeness": env.completeness,
        "content_hash": env.content_hash(),
    }


_SCORABLE_QUALITY = frozenset({QualityStatus.OK.value, QualityStatus.PARTIAL.value})


def _compute_capture_score(
    a1: dict[str, Any],
    a3: dict[str, Any],
) -> tuple[float | None, float, float, float]:
    """Compute capture_decline_score from A1 and A3 extracts.

    Returns (score_or_none, sigma_component, coverage_component, weight_sum).
    """
    score = 0.0
    weight_sum = 0.0
    sigma_component = 0.0
    coverage_component = 0.0

    # Sigma rate contribution (A3)
    if a3["quality_status"] in _SCORABLE_QUALITY:
        sigma_rate = a3["value"] if a3["value"] is not None else 0.0
        sigma_score = min(sigma_rate / SIGMA_RATE_CEILING, 1.0) if SIGMA_RATE_CEILING > 0 else 0.0
        sigma_component = sigma_score * SIGMA_WEIGHT
        score += sigma_component
        weight_sum += SIGMA_WEIGHT

        # Invalid pairs penalty
        if a3["invalid_pairs_count"] > 0:
            score += INVALID_PAIRS_PENALTY
            weight_sum += INVALID_PAIRS_PENALTY_WEIGHT

    # Exposure coverage contribution (A1)
    if a1["quality_status"] in _SCORABLE_QUALITY:
        coverage = a1["coverage_ratio"]
        if coverage < LOW_COVERAGE_THRESHOLD:
            cov_score = (LOW_COVERAGE_THRESHOLD - coverage) / LOW_COVERAGE_THRESHOLD if LOW_COVERAGE_THRESHOLD > 0 else 0.0
            coverage_component = cov_score * COVERAGE_WEIGHT
            score += coverage_component
            weight_sum += COVERAGE_WEIGHT

    if weight_sum <= 0:
        return None, 0.0, 0.0, 0.0

    final_score = min(score / weight_sum, 1.0)
    return final_score, sigma_component, coverage_component, weight_sum


def _classify_from_score(score: float | None) -> str:
    """Map capture_decline_score to classification."""
    if score is None:
        return CLASSIFICATION_INSUFFICIENT_HISTORY
    if score < WATCH_THRESHOLD:
        return CLASSIFICATION_NORMAL
    if score < WARNING_THRESHOLD:
        return CLASSIFICATION_WATCH
    return CLASSIFICATION_WARNING


# ── Derivation function ───────────────────────────────────────────────────

def derive_capture_self_diagnostic(
    inputs: DiagnosticInputs,
    window_start: str,
    window_end: str,
    window_kind: str = "rolling_5m",
    *,
    emitter: str = "governor.signals.capture_self_diagnostic",
    emitter_version: str = "",
    session_id: str | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Derive CAPTURE_SELF_DIAGNOSTIC from Phase A signal envelopes.

    Pure derivation — no IO.  Caller provides pre-gathered A signal
    envelopes for the target window.

    Value semantics:
      0.0 = healthy (no capture signal)
      0.0–1.0 = capture_decline_score
      None = not computable (compromised, insufficient, indeterminate)

    Args:
        inputs: Phase A signal envelopes.
        window_start: ISO 8601 UTC window start.
        window_end: ISO 8601 UTC window end.
        window_kind: Window type identifier.
        emitter: Source module identifier.
        emitter_version: Source module version.
        session_id: Session context.
        emitted_at: Override emission timestamp.

    Returns:
        SignalEnvelope with signal_id="CAPTURE_SELF_DIAGNOSTIC".
    """
    # ── Extract input fields ────────────────────────────────────────────
    a1 = _extract_a1(inputs.a1_exposure_proxy)
    a2 = _extract_a2(inputs.a2_silent_suppression)
    a3 = _extract_a3(inputs.a3_sigma_rate)
    _inp_envs = (
        inputs.a1_exposure_proxy,
        inputs.a2_silent_suppression,
        inputs.a3_sigma_rate,
    )

    # ── Window alignment check ──────────────────────────────────────────
    alignment_errors = _validate_window_alignment(inputs)
    if alignment_errors:
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INDETERMINATE,
            quality_status=QualityStatus.INVALID.value,
            quality_reasons=["window_mismatch: " + "; ".join(alignment_errors)],
            completeness=None,
            sample_size=0,
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=0,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    # ── Missing A2 → unavailable ────────────────────────────────────────
    if inputs.a2_silent_suppression is None:
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INDETERMINATE,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=["missing_suppression_signal"],
            completeness=None,
            sample_size=0,
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=0,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    # ── Suppression precedence (Step 1) ─────────────────────────────────
    # A2 value: 1.0=healthy, 0.0=suppressed, None=idle/indeterminate
    if a2["value"] is not None and a2["value"] == 0.0:
        # Instrumentation is dark
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INSTRUMENTATION_COMPROMISED,
            quality_status=QualityStatus.OK.value,
            quality_reasons=[],
            completeness=1.0,
            sample_size=1,
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=1,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    if a2["value"] is None:
        # Idle or indeterminate — not enough data
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INSUFFICIENT_HISTORY,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=["suppression_idle_or_indeterminate"],
            completeness=None,
            sample_size=1,
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=1,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    # ── A2 is healthy (value=1.0) — proceed to capture scoring ──────────

    # Check if we have enough inputs to score
    a1_present = inputs.a1_exposure_proxy is not None
    a3_present = inputs.a3_sigma_rate is not None

    if not a1_present and not a3_present:
        # A2 healthy but no A1 or A3 → insufficient inputs to score
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INSUFFICIENT_HISTORY,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=["insufficient_input_signals"],
            completeness=None,
            sample_size=1,
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=1,
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    # ── Capture scoring (Step 2) ────────────────────────────────────────
    score, sigma_comp, coverage_comp, _ = _compute_capture_score(a1, a3)

    if score is None:
        # Inputs present but none were scorable (all invalid/unavailable)
        return _build_envelope(
            value=None,
            classification=CLASSIFICATION_INDETERMINATE,
            quality_status=QualityStatus.PARTIAL.value,
            quality_reasons=["no_scorable_inputs"],
            completeness=None,
            sample_size=_count_inputs(a1_present, a3_present),
            a1=a1, a2=a2, a3=a3,
            sigma_component=0.0,
            coverage_component=0.0,
            input_signal_count=_count_inputs(a1_present, a3_present),
            window_start=window_start,
            window_end=window_end,
            window_kind=window_kind,
            emitter=emitter,
            emitter_version=emitter_version,
            session_id=session_id,
            emitted_at=emitted_at,
            input_envelopes=_inp_envs,
        )

    # ── Classification from score (Step 3) ──────────────────────────────
    classification = _classify_from_score(score)

    # ── Quality ─────────────────────────────────────────────────────────
    input_count = 1  # A2 always counted
    completeness_values: list[float] = []

    if a1_present:
        input_count += 1
        if a1["completeness"] is not None:
            completeness_values.append(a1["completeness"])
    if a3_present:
        input_count += 1
        if a3["completeness"] is not None:
            completeness_values.append(a3["completeness"])
    if a2["completeness"] is not None:
        completeness_values.append(a2["completeness"])

    # Determine quality
    if a1_present and a3_present:
        # All three inputs present
        any_partial = (
            a1["quality_status"] == QualityStatus.PARTIAL.value
            or a3["quality_status"] == QualityStatus.PARTIAL.value
        )
        if any_partial:
            q_status = QualityStatus.PARTIAL.value
            q_reasons = ["input_signal_partial"]
        else:
            q_status = QualityStatus.OK.value
            q_reasons = []
    else:
        # Missing A1 or A3 → partial
        missing = []
        if not a1_present:
            missing.append("EXPOSURE_PROXY")
        if not a3_present:
            missing.append("SIGMA_RATE")
        q_status = QualityStatus.PARTIAL.value
        q_reasons = [f"missing_input_signals ({', '.join(missing)})"]

    comp = min(completeness_values) if completeness_values else None

    return _build_envelope(
        value=score,
        classification=classification,
        quality_status=q_status,
        quality_reasons=q_reasons,
        completeness=comp,
        sample_size=input_count,
        a1=a1, a2=a2, a3=a3,
        sigma_component=sigma_comp,
        coverage_component=coverage_comp,
        input_signal_count=input_count,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        emitter=emitter,
        emitter_version=emitter_version,
        session_id=session_id,
        emitted_at=emitted_at,
        input_envelopes=_inp_envs,
    )


def _count_inputs(a1_present: bool, a3_present: bool) -> int:
    """Count how many input signals are present (A2 always counted)."""
    return 1 + int(a1_present) + int(a3_present)


def _build_envelope(
    *,
    value: float | None,
    classification: str,
    quality_status: str,
    quality_reasons: list[str],
    completeness: float | None,
    sample_size: int,
    a1: dict[str, Any],
    a2: dict[str, Any],
    a3: dict[str, Any],
    sigma_component: float,
    coverage_component: float,
    input_signal_count: int,
    window_start: str,
    window_end: str,
    window_kind: str,
    emitter: str,
    emitter_version: str,
    session_id: str | None,
    emitted_at: str | None,
    input_envelopes: tuple[SignalEnvelope | None, ...] = (),
) -> SignalEnvelope:
    """Internal helper to build the output SignalEnvelope."""
    values: dict[str, Any] = {
        "capture_decline_score": value,
        "classification": classification,
        "sigma_rate_input": a3["value"],
        "sigma_rate_quality": a3["quality_status"],
        "sigma_score_component": sigma_component,
        "invalid_pairs_count": a3["invalid_pairs_count"],
        "exposure_proxy_input": a1["value"],
        "exposure_proxy_quality": a1["quality_status"],
        "coverage_ratio": a1["coverage_ratio"],
        "coverage_score_component": coverage_component,
        "suppression_input": a2["value"],
        "suppression_classification": a2["classification"],
        "input_signal_count": input_signal_count,
        "config_version": DIAG_CONFIG_VERSION,
    }

    annotations: dict[str, Any] = {
        "config_version": DIAG_CONFIG_VERSION,
        "a1_content_hash": a1["content_hash"],
        "a2_content_hash": a2["content_hash"],
        "a3_content_hash": a3["content_hash"],
    }

    # source_streams: only streams that contributed
    source_streams: list[str] = []
    if a1["content_hash"] is not None:
        source_streams.append("EXPOSURE_PROXY")
    if a2["content_hash"] is not None:
        source_streams.append("SILENT_SUPPRESSION")
    if a3["content_hash"] is not None:
        source_streams.append("SIGMA_RATE")

    # Monotonic propagation: union source_receipt_ids from input signals
    propagated_receipt_ids: list[str] = []
    for inp_env in input_envelopes:
        if inp_env is not None:
            propagated_receipt_ids.extend(inp_env.source_receipt_ids)

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="CAPTURE_SELF_DIAGNOSTIC",
        signal_version=1,
        phase="2.4B",
        subject_type="window",
        subject_id=f"diag_{window_start}_{window_kind}",
        session_id=session_id,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="score",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=sample_size,
        completeness=completeness,
        source_receipt_ids=propagated_receipt_ids,
        source_streams=source_streams,
        source_versions=default_source_versions(),
        derivation=DerivationType.DERIVED.value,
        derivation_version=DIAG_CONFIG_VERSION,
        annotations=annotations,
    )
