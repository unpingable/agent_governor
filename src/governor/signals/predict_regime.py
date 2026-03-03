# SPDX-License-Identifier: Apache-2.0
"""
PREDICT_REGIME_PREFLIGHT — observe-only pre-session regime prediction.

Pure derivation over calibrated A/B signal envelopes. Produces a single
prediction envelope: predicted regime + confidence + provenance.

No gating, no policy, no IO, no hidden state.

Design authority: specs/gaps/V2_4D_PREDICT_REGIME_PREFLIGHT.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    content_hash,
    default_source_versions,
)


# ── Config ───────────────────────────────────────────────────────────────────

PREFLIGHT_CONFIG_VERSION = "predict-regime-preflight-v1"

# ── Regime taxonomy ──────────────────────────────────────────────────────────


class PreflightRegime(str, Enum):
    """Predicted regime from preflight analysis."""

    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    INSTRUMENTATION_COMPROMISED = "instrumentation_compromised"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INDETERMINATE = "indeterminate"


ALL_REGIMES = frozenset(r.value for r in PreflightRegime)

# ── Signal IDs ───────────────────────────────────────────────────────────────

# Required calibrated signals
REQUIRED_SIGNALS = frozenset({
    "EXPOSURE_PROXY",
    "SIGMA_RATE",
    "CAPTURE_SELF_DIAGNOSTIC",
})

# Optional calibrated signals
OPTIONAL_SIGNALS = frozenset({
    "DECISION_EVIDENCE_LAG",
    "SILENT_SUPPRESSION",
})

ALL_EXPECTED_SIGNALS = REQUIRED_SIGNALS | OPTIONAL_SIGNALS

# ── Default weights and thresholds ───────────────────────────────────────────


@dataclass(frozen=True)
class PreflightConfig:
    """Frozen configuration for regime prediction.

    Weights and thresholds for v1 heuristic scoring.
    """

    # Feature weights (must sum to ~1.0 for interpretability)
    weight_capture_diagnostic: float = 0.40
    weight_sigma_rate: float = 0.30
    weight_decision_lag: float = 0.20
    weight_exposure_proxy: float = 0.10

    # Risk score thresholds
    threshold_normal: float = 0.3      # below → normal
    threshold_watch: float = 0.6       # below → watch, above → warning

    # Confidence caps
    confidence_cap_missing_required: float = 0.5
    confidence_cap_suppressed: float = 0.3

    # Suppression detection threshold
    suppression_threshold: float = 0.5  # calibrated suppression value above this → compromised

    config_version: str = PREFLIGHT_CONFIG_VERSION


DEFAULT_CONFIG = PreflightConfig()


# ── Input types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreflightInput:
    """Extracted and aligned input for regime prediction."""

    signal_id: str
    calibrated_value: float | None
    quality_status: str
    source_hash: str
    is_required: bool
    is_usable: bool              # has numeric value + acceptable quality
    reason: str | None = None    # why not usable, if applicable


@dataclass(frozen=True)
class PreflightInputSet:
    """Complete set of extracted inputs with alignment metadata."""

    inputs: dict[str, PreflightInput]   # signal_id → input
    input_count_expected: int
    input_count_present: int
    input_count_usable: int
    missing_required: frozenset[str]
    missing_optional: frozenset[str]
    alignment_ok: bool
    alignment_reasons: tuple[str, ...]


# ── Input extraction ─────────────────────────────────────────────────────────

# Acceptable quality statuses for usable inputs
USABLE_QUALITIES = frozenset({"ok", "partial"})


def extract_preflight_inputs(
    envelopes: Sequence[SignalEnvelope],
) -> PreflightInputSet:
    """Extract and align calibrated inputs for regime prediction.

    Expects one envelope per signal_id. If multiple envelopes share a
    signal_id, the most recent (by emitted_at) wins.
    """
    # Index by signal_id, most recent wins
    by_signal: dict[str, SignalEnvelope] = {}
    for env in envelopes:
        existing = by_signal.get(env.signal_id)
        if existing is None or env.emitted_at > existing.emitted_at:
            by_signal[env.signal_id] = env

    inputs: dict[str, PreflightInput] = {}
    missing_required: set[str] = set()
    missing_optional: set[str] = set()
    alignment_reasons: list[str] = []

    for sig_id in sorted(ALL_EXPECTED_SIGNALS):
        is_required = sig_id in REQUIRED_SIGNALS
        env = by_signal.get(sig_id)

        if env is None:
            reason = f"{sig_id} not present"
            if is_required:
                missing_required.add(sig_id)
            else:
                missing_optional.add(sig_id)
            inputs[sig_id] = PreflightInput(
                signal_id=sig_id,
                calibrated_value=None,
                quality_status="unavailable",
                source_hash="",
                is_required=is_required,
                is_usable=False,
                reason=reason,
            )
            continue

        # Extract value — calibrated envelopes use top-level value
        # or values["normalized_value"] if calibrated via C2 apply
        raw_value = env.value
        if raw_value is None and "normalized_value" in env.values:
            raw_value = env.values["normalized_value"]

        # Check usability
        is_numeric = (
            isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
        )
        quality_ok = env.quality_status in USABLE_QUALITIES
        is_usable = is_numeric and quality_ok and raw_value is not None

        reason = None
        if raw_value is None:
            reason = f"{sig_id} value is None"
        elif not is_numeric:
            reason = f"{sig_id} value not numeric"
        elif not quality_ok:
            reason = f"{sig_id} quality={env.quality_status}"

        source_hash = content_hash(env.to_canonical_bytes())

        inputs[sig_id] = PreflightInput(
            signal_id=sig_id,
            calibrated_value=float(raw_value) if is_usable else None,
            quality_status=env.quality_status,
            source_hash=source_hash,
            is_required=is_required,
            is_usable=is_usable,
            reason=reason,
        )

    # Alignment check
    alignment_ok = len(missing_required) == 0
    if missing_required:
        alignment_reasons.append(
            f"missing required: {sorted(missing_required)}",
        )
    if missing_optional:
        alignment_reasons.append(
            f"missing optional: {sorted(missing_optional)}",
        )

    present = sum(1 for inp in inputs.values() if inp.source_hash)
    usable = sum(1 for inp in inputs.values() if inp.is_usable)

    return PreflightInputSet(
        inputs=inputs,
        input_count_expected=len(ALL_EXPECTED_SIGNALS),
        input_count_present=present,
        input_count_usable=usable,
        missing_required=frozenset(missing_required),
        missing_optional=frozenset(missing_optional),
        alignment_ok=alignment_ok,
        alignment_reasons=tuple(alignment_reasons),
    )


# ── Prediction logic ─────────────────────────────────────────────────────────


def _get_feature_value(
    input_set: PreflightInputSet,
    signal_id: str,
) -> float | None:
    """Get usable calibrated value for a signal, or None."""
    inp = input_set.inputs.get(signal_id)
    if inp is None or not inp.is_usable:
        return None
    return inp.calibrated_value


def _check_suppression(
    input_set: PreflightInputSet,
    config: PreflightConfig,
) -> bool:
    """Check if suppression/instrumentation-dark is active.

    Uses SILENT_SUPPRESSION if available, or CAPTURE_SELF_DIAGNOSTIC
    classification if annotated as instrumentation_compromised.
    """
    # Check SILENT_SUPPRESSION signal
    suppression = input_set.inputs.get("SILENT_SUPPRESSION")
    if suppression and suppression.is_usable:
        # Low suppression value = healthy, high = suppressed
        # But SILENT_SUPPRESSION is inverted: 1.0 = healthy, 0.0 = suppressed
        # After calibration it stays in same semantics
        if suppression.calibrated_value is not None:
            if suppression.calibrated_value <= (1.0 - config.suppression_threshold):
                return True

    # Check CAPTURE_SELF_DIAGNOSTIC for compromised classification
    diag = input_set.inputs.get("CAPTURE_SELF_DIAGNOSTIC")
    if diag and diag.source_hash:
        # Can't directly check classification from calibrated value alone,
        # but if the calibrated value is very high, it indicates concern
        if diag.is_usable and diag.calibrated_value is not None:
            if diag.calibrated_value >= config.suppression_threshold:
                return True

    return False


def _compute_risk_score(
    input_set: PreflightInputSet,
    config: PreflightConfig,
) -> tuple[float, dict[str, float | None]]:
    """Compute weighted risk score from calibrated features.

    Returns (risk_score, feature_values).
    Missing features get weight redistributed to present ones.
    """
    features: dict[str, tuple[float, float | None]] = {
        "CAPTURE_SELF_DIAGNOSTIC": (
            config.weight_capture_diagnostic,
            _get_feature_value(input_set, "CAPTURE_SELF_DIAGNOSTIC"),
        ),
        "SIGMA_RATE": (
            config.weight_sigma_rate,
            _get_feature_value(input_set, "SIGMA_RATE"),
        ),
        "DECISION_EVIDENCE_LAG": (
            config.weight_decision_lag,
            _get_feature_value(input_set, "DECISION_EVIDENCE_LAG"),
        ),
        "EXPOSURE_PROXY": (
            config.weight_exposure_proxy,
            _get_feature_value(input_set, "EXPOSURE_PROXY"),
        ),
    }

    feature_values: dict[str, float | None] = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for sig_id, (weight, value) in features.items():
        feature_values[sig_id] = value
        if value is not None:
            total_weight += weight
            weighted_sum += weight * value

    if total_weight == 0.0:
        return 0.0, feature_values

    # Normalize by actual weight used (redistribute missing weight)
    risk_score = weighted_sum / total_weight
    return risk_score, feature_values


def _classify_regime(
    risk_score: float,
    config: PreflightConfig,
) -> PreflightRegime:
    """Map risk score to regime via thresholds."""
    if risk_score < config.threshold_normal:
        return PreflightRegime.NORMAL
    elif risk_score < config.threshold_watch:
        return PreflightRegime.WATCH
    else:
        return PreflightRegime.WARNING


def _compute_confidence(
    input_set: PreflightInputSet,
    config: PreflightConfig,
    *,
    suppressed: bool = False,
) -> float:
    """Compute prediction confidence from input quality/completeness.

    Confidence is bounded [0, 1]. Degrades when:
    - required signals missing → hard cap
    - suppression active → hard cap
    - partial quality → discount
    - optional signals missing → small discount
    """
    if input_set.input_count_expected == 0:
        return 0.0

    # Base: completeness ratio
    completeness = input_set.input_count_usable / input_set.input_count_expected
    confidence = completeness

    # Quality ratio: ok > partial
    ok_count = sum(
        1 for inp in input_set.inputs.values()
        if inp.is_usable and inp.quality_status == "ok"
    )
    usable = input_set.input_count_usable
    if usable > 0:
        quality_ratio = ok_count / usable
        # Blend: 70% completeness, 30% quality
        confidence = 0.7 * completeness + 0.3 * quality_ratio

    # Hard caps
    if input_set.missing_required:
        confidence = min(confidence, config.confidence_cap_missing_required)
    if suppressed:
        confidence = min(confidence, config.confidence_cap_suppressed)

    return max(0.0, min(1.0, confidence))


# ── Main entry point ─────────────────────────────────────────────────────────


def predict_regime_preflight(
    envelopes: Sequence[SignalEnvelope],
    *,
    config: PreflightConfig | None = None,
    session_id: str | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Predict operational regime from calibrated signal envelopes.

    Pure function. No IO, no hidden state, no policy effects.
    Returns a single SignalEnvelope with predicted regime + confidence.

    Args:
        envelopes: Calibrated A/B signal envelopes.
        config: Override prediction config (default: DEFAULT_CONFIG).
        session_id: Session context. If None, inferred from most recent input.
        emitted_at: Override emission timestamp (default: now).
    """
    cfg = config or DEFAULT_CONFIG

    # 1. Extract and align inputs
    input_set = extract_preflight_inputs(envelopes)

    # 2. Suppression precedence check
    suppressed = _check_suppression(input_set, cfg)

    # 3. Determine regime
    reason_codes: list[str] = []

    if suppressed:
        # Hard branch: suppression overrides everything
        regime = PreflightRegime.INSTRUMENTATION_COMPROMISED
        risk_score = 1.0
        feature_values: dict[str, float | None] = {
            sig: _get_feature_value(input_set, sig)
            for sig in ("CAPTURE_SELF_DIAGNOSTIC", "SIGMA_RATE",
                        "DECISION_EVIDENCE_LAG", "EXPOSURE_PROXY")
        }
        reason_codes.append("suppression_precedence")
    elif input_set.missing_required:
        # Not enough inputs for prediction
        regime = PreflightRegime.INSUFFICIENT_HISTORY
        risk_score = 0.0
        feature_values = {
            sig: _get_feature_value(input_set, sig)
            for sig in ("CAPTURE_SELF_DIAGNOSTIC", "SIGMA_RATE",
                        "DECISION_EVIDENCE_LAG", "EXPOSURE_PROXY")
        }
        reason_codes.append("missing_required_signals")
        for sig in sorted(input_set.missing_required):
            reason_codes.append(f"missing:{sig}")
    elif input_set.input_count_usable == 0:
        # Present but not usable
        regime = PreflightRegime.INDETERMINATE
        risk_score = 0.0
        feature_values = {
            sig: None
            for sig in ("CAPTURE_SELF_DIAGNOSTIC", "SIGMA_RATE",
                        "DECISION_EVIDENCE_LAG", "EXPOSURE_PROXY")
        }
        reason_codes.append("no_usable_inputs")
    else:
        # Normal scoring path
        risk_score, feature_values = _compute_risk_score(input_set, cfg)
        regime = _classify_regime(risk_score, cfg)
        if input_set.missing_optional:
            reason_codes.append("degraded_optional")

    # 4. Confidence
    confidence = _compute_confidence(input_set, cfg, suppressed=suppressed)

    # 5. Quality status
    if input_set.missing_required:
        quality_status = QualityStatus.UNAVAILABLE.value
    elif any(
        inp.quality_status == "partial"
        for inp in input_set.inputs.values()
        if inp.is_usable
    ):
        quality_status = QualityStatus.PARTIAL.value
    else:
        quality_status = QualityStatus.OK.value

    quality_reasons: list[str] = []
    if input_set.missing_required:
        quality_reasons.append(
            f"missing_required:{sorted(input_set.missing_required)}",
        )
    if input_set.missing_optional:
        quality_reasons.append(
            f"missing_optional:{sorted(input_set.missing_optional)}",
        )

    # 6. Build output envelope — missing≠zero: unavailable → value=None
    output_value: float | None = confidence
    if quality_status == QualityStatus.UNAVAILABLE.value:
        output_value = None

    ts = emitted_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Input provenance
    input_hashes: dict[str, str] = {}
    input_quality_statuses: dict[str, str] = {}
    for sig_id, inp in sorted(input_set.inputs.items()):
        if inp.source_hash:
            input_hashes[sig_id] = inp.source_hash
        input_quality_statuses[sig_id] = inp.quality_status

    # Monotonic propagation: union source_receipt_ids from input envelopes
    propagated_receipt_ids: list[str] = []
    for env in envelopes:
        propagated_receipt_ids.extend(env.source_receipt_ids)

    # Infer session_id from most recent input if not provided
    resolved_session_id = session_id
    if resolved_session_id is None:
        for env in sorted(envelopes, key=lambda e: e.emitted_at, reverse=True):
            if env.session_id:
                resolved_session_id = env.session_id
                break

    values: dict[str, Any] = {
        "predicted_regime": regime.value,
        "confidence": confidence,
        "risk_score": risk_score,
        "input_count_expected": input_set.input_count_expected,
        "input_count_present": input_set.input_count_present,
        "input_count_usable": input_set.input_count_usable,
        "feature_values": feature_values,
        "input_quality_statuses": input_quality_statuses,
        "reason_codes": reason_codes,
        "model_version": PREFLIGHT_CONFIG_VERSION,
    }

    annotations: dict[str, Any] = {
        "input_envelope_hashes": input_hashes,
        "suppression_precedence_applied": suppressed,
        "config_version": PREFLIGHT_CONFIG_VERSION,
    }

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=ts,
        emitter="governor.signals.predict_regime",
        emitter_version="2.4.0-dev",
        signal_id="PREDICT_REGIME_PREFLIGHT",
        signal_version=1,
        phase="2.4D",
        subject_type="session",
        session_id=resolved_session_id,
        value=output_value,
        unit="score",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        sample_size=input_set.input_count_present,
        completeness=(
            input_set.input_count_usable / input_set.input_count_expected
            if input_set.input_count_expected > 0
            else None
        ),
        source_receipt_ids=propagated_receipt_ids,
        source_versions=default_source_versions(),
        derivation=DerivationType.DERIVED.value,
        derivation_version=PREFLIGHT_CONFIG_VERSION,
        annotations=annotations,
    )
