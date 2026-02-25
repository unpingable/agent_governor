# SPDX-License-Identifier: Apache-2.0
"""
CALIBRATION_FITTING — offline param-set fitting from replay corpus.

Produces frozen CalibrationParamSet artifacts + fit summary envelopes
from a corpus of signal envelopes. Deterministic, auditable, observe-only.

Design authority: specs/gaps/V2_4C_CALIBRATION_FITTING.md
"""

from __future__ import annotations

import hashlib
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from .calibration_layer import (
    CALIBRATION_CONFIG_VERSION,
    CalibrationParamSet,
    _is_numeric,
)
from .calibration_methods import (
    CALIBRATION_METHODS,
    REQUIRED_PARAMS,
    CalibrationMismatchError,
)
from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    canonical_json,
    content_hash,
)


# ── Config ───────────────────────────────────────────────────────────────────

CALIBRATION_FIT_CONFIG_VERSION = "calibration-fitting-v1"

# Default quality statuses to include
DEFAULT_INCLUDE_QUALITIES = frozenset({"ok", "partial"})

# Default classifications to exclude (suppression-aware by default)
DEFAULT_EXCLUDE_CLASSIFICATIONS = frozenset({
    "instrumentation_compromised",
    "suppressed",
})


# ── Exclusion reason taxonomy ────────────────────────────────────────────────

REASON_SIGNAL_VERSION_MISMATCH = "signal_version_mismatch"
REASON_TARGET_FIELD_MISSING = "target_field_missing"
REASON_NON_NUMERIC_VALUE = "non_numeric_value"
REASON_BOOL_VALUE = "bool_value"
REASON_MISSING_VALUE = "missing_value"
REASON_QUALITY_EXCLUDED = "quality_excluded"
REASON_CLASSIFICATION_EXCLUDED = "classification_excluded"
REASON_DOMAIN_INVALID = "domain_invalid"


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationFitSpec:
    """Frozen configuration for fitting a calibration param set.

    The fitting analogue to ReplaySpec — describes what to fit, from what
    corpus, using what rules, with what method.
    """

    fit_id: str
    signal_id: str
    signal_version: int
    target_field: str                   # "value" or named field in values
    method: str                         # "identity_clip" | "linear_minmax" | "log_minmax"
    source_mode: str                    # "replay" | "signal_envelopes"
    source_manifest_hash: str
    source_replay_run_id: str | None = None
    include_quality_statuses: frozenset[str] = field(
        default_factory=lambda: DEFAULT_INCLUDE_QUALITIES,
    )
    exclude_classifications: frozenset[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDE_CLASSIFICATIONS,
    )
    exclude_null_values: bool = True
    min_sample_count: int = 1
    clip_min: float = 0.0
    clip_max: float = 1.0
    log_base: float | None = None
    epsilon_shift: float | None = None
    notes: str | None = None
    created_by: str | None = None
    created_at: str = ""
    derivation_version: str = CALIBRATION_FIT_CONFIG_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict. Frozensets → sorted lists."""
        return {
            "fit_id": self.fit_id,
            "signal_id": self.signal_id,
            "signal_version": self.signal_version,
            "target_field": self.target_field,
            "method": self.method,
            "source_mode": self.source_mode,
            "source_manifest_hash": self.source_manifest_hash,
            "source_replay_run_id": self.source_replay_run_id,
            "include_quality_statuses": sorted(self.include_quality_statuses),
            "exclude_classifications": sorted(self.exclude_classifications),
            "exclude_null_values": self.exclude_null_values,
            "min_sample_count": self.min_sample_count,
            "clip_min": self.clip_min,
            "clip_max": self.clip_max,
            "log_base": self.log_base,
            "epsilon_shift": self.epsilon_shift,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "derivation_version": self.derivation_version,
        }

    def fit_spec_hash(self) -> str:
        """Content-addressed hash of the fit spec."""
        digest = hashlib.sha256(canonical_json(self.to_dict())).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationFitSpec:
        """Deserialize from dict. Lists → frozensets."""
        return cls(
            fit_id=d["fit_id"],
            signal_id=d["signal_id"],
            signal_version=d["signal_version"],
            target_field=d["target_field"],
            method=d["method"],
            source_mode=d["source_mode"],
            source_manifest_hash=d["source_manifest_hash"],
            source_replay_run_id=d.get("source_replay_run_id"),
            include_quality_statuses=frozenset(
                d.get("include_quality_statuses", DEFAULT_INCLUDE_QUALITIES),
            ),
            exclude_classifications=frozenset(
                d.get("exclude_classifications", DEFAULT_EXCLUDE_CLASSIFICATIONS),
            ),
            exclude_null_values=d.get("exclude_null_values", True),
            min_sample_count=d.get("min_sample_count", 1),
            clip_min=d.get("clip_min", 0.0),
            clip_max=d.get("clip_max", 1.0),
            log_base=d.get("log_base"),
            epsilon_shift=d.get("epsilon_shift"),
            notes=d.get("notes"),
            created_by=d.get("created_by"),
            created_at=d.get("created_at", ""),
            derivation_version=d.get(
                "derivation_version", CALIBRATION_FIT_CONFIG_VERSION,
            ),
        )


@dataclass(frozen=True)
class FitSample:
    """A single valid sample extracted from the corpus for fitting."""

    window_start: str | None
    subject_id: str | None
    raw_value: float
    quality_status: str
    source_hash: str


@dataclass(frozen=True)
class FitSampleSelection:
    """Result of sample extraction: selected samples + exclusion accounting."""

    samples: tuple[FitSample, ...]
    sample_count_total: int
    sample_count_used: int
    sample_count_excluded: int
    exclusion_reason_counts: dict[str, int]
    used_values: tuple[float, ...]
    window_range: str | None = None


@dataclass(frozen=True)
class FitStats:
    """Corpus statistics from fitting."""

    degenerate_fit: bool
    observed_min: float | None
    observed_max: float | None
    mean: float | None = None
    p50: float | None = None
    p95: float | None = None


@dataclass(frozen=True)
class FitResult:
    """Structured return from fit_param_set_from_corpus.

    param_set is None on failure. summary_envelope is always present.
    """

    param_set: CalibrationParamSet | None
    summary_envelope: SignalEnvelope
    errors: tuple[str, ...]


# ── Validation ───────────────────────────────────────────────────────────────


def validate_fit_spec(fit_spec: CalibrationFitSpec) -> None:
    """Validate a fit spec. Raises CalibrationMismatchError on invalid config."""

    if fit_spec.method not in CALIBRATION_METHODS:
        raise CalibrationMismatchError(
            f"unknown method {fit_spec.method!r} "
            f"(known: {sorted(CALIBRATION_METHODS)})",
        )

    if not fit_spec.include_quality_statuses:
        raise CalibrationMismatchError("include_quality_statuses must not be empty")

    if fit_spec.min_sample_count < 1:
        raise CalibrationMismatchError(
            f"min_sample_count must be >= 1, got {fit_spec.min_sample_count}",
        )

    # Clip bounds: must be in [0,1] and ordered
    if fit_spec.clip_max < fit_spec.clip_min:
        raise CalibrationMismatchError(
            f"inverted clip bounds: clip_max={fit_spec.clip_max} "
            f"< clip_min={fit_spec.clip_min}",
        )
    if fit_spec.clip_min < 0.0 or fit_spec.clip_max > 1.0:
        raise CalibrationMismatchError(
            f"clip bounds outside [0,1]: "
            f"clip_min={fit_spec.clip_min}, clip_max={fit_spec.clip_max}",
        )

    # log_minmax-specific validation
    if fit_spec.method == "log_minmax":
        if fit_spec.log_base is None:
            raise CalibrationMismatchError(
                "log_minmax requires log_base in fit spec",
            )
        if fit_spec.log_base <= 0 or fit_spec.log_base == 1:
            raise CalibrationMismatchError(
                f"invalid log_base={fit_spec.log_base} (must be positive and != 1)",
            )
        if fit_spec.epsilon_shift is None:
            raise CalibrationMismatchError(
                "log_minmax requires explicit epsilon_shift in fit spec",
            )
        if fit_spec.epsilon_shift <= 0:
            raise CalibrationMismatchError(
                f"epsilon_shift={fit_spec.epsilon_shift} must be > 0",
            )


# ── Sample extraction ────────────────────────────────────────────────────────


def extract_fit_samples(
    envelopes: Sequence[SignalEnvelope],
    fit_spec: CalibrationFitSpec,
) -> FitSampleSelection:
    """Extract valid samples from corpus with explicit exclusion accounting.

    Every excluded envelope increments exactly one exclusion reason count.
    Deterministic ordering: sort by (window_start, subject_id, content_hash).
    """
    exclusions: Counter[str] = Counter()
    samples: list[FitSample] = []
    total = 0

    # Deterministic candidate ordering
    candidates = sorted(
        envelopes,
        key=lambda e: (
            e.window_start or "",
            e.subject_id or "",
            content_hash(e.to_canonical_bytes()),
        ),
    )

    for env in candidates:
        total += 1

        # 1. Signal ID must match (not counted as exclusion — wrong signal)
        if env.signal_id != fit_spec.signal_id:
            continue  # not a candidate at all, don't count

        # 2. Signal version
        if env.signal_version != fit_spec.signal_version:
            exclusions[REASON_SIGNAL_VERSION_MISMATCH] += 1
            continue

        # 3. Extract raw value
        if fit_spec.target_field == "value":
            raw = env.value
        elif fit_spec.target_field in env.values:
            raw = env.values[fit_spec.target_field]
        else:
            exclusions[REASON_TARGET_FIELD_MISSING] += 1
            continue

        # 4. Null check
        if raw is None:
            if fit_spec.exclude_null_values:
                exclusions[REASON_MISSING_VALUE] += 1
                continue

        # 5. Bool check (before numeric, since bool is subclass of int)
        if isinstance(raw, bool):
            exclusions[REASON_BOOL_VALUE] += 1
            continue

        # 6. Numeric check
        if raw is not None and not _is_numeric(raw):
            exclusions[REASON_NON_NUMERIC_VALUE] += 1
            continue

        # 7. Quality filtering
        if env.quality_status not in fit_spec.include_quality_statuses:
            exclusions[REASON_QUALITY_EXCLUDED] += 1
            continue

        # 8. Classification filtering (if classification data present)
        classification = env.annotations.get("classification", "")
        if (
            classification
            and classification in fit_spec.exclude_classifications
        ):
            exclusions[REASON_CLASSIFICATION_EXCLUDED] += 1
            continue

        # 9. Domain filtering for log_minmax
        if (
            fit_spec.method == "log_minmax"
            and fit_spec.epsilon_shift is not None
            and raw is not None
        ):
            if raw + fit_spec.epsilon_shift <= 0:
                exclusions[REASON_DOMAIN_INVALID] += 1
                continue

        # Passed all filters
        if raw is not None:
            source_hash = content_hash(env.to_canonical_bytes())
            samples.append(FitSample(
                window_start=env.window_start,
                subject_id=env.subject_id,
                raw_value=float(raw),
                quality_status=env.quality_status,
                source_hash=source_hash,
            ))

    used_values = tuple(s.raw_value for s in samples)
    excluded = sum(exclusions.values())

    # Window range
    window_range = None
    if samples:
        starts = [s.window_start for s in samples if s.window_start]
        if starts:
            window_range = f"{min(starts)}/{max(starts)}"

    return FitSampleSelection(
        samples=tuple(samples),
        sample_count_total=total,
        sample_count_used=len(samples),
        sample_count_excluded=excluded,
        exclusion_reason_counts=dict(exclusions),
        used_values=used_values,
        window_range=window_range,
    )


# ── Method-specific fitting ──────────────────────────────────────────────────


def _fit_identity_clip(
    selection: FitSampleSelection,
    fit_spec: CalibrationFitSpec,
) -> tuple[dict[str, Any], FitStats]:
    """Fit identity_clip: fixed clip bounds from spec."""
    vals = selection.used_values
    return (
        {"min": fit_spec.clip_min, "max": fit_spec.clip_max},
        FitStats(
            degenerate_fit=len(set(vals)) <= 1,
            observed_min=min(vals) if vals else None,
            observed_max=max(vals) if vals else None,
            mean=statistics.mean(vals) if vals else None,
            p50=statistics.median(vals) if vals else None,
            p95=_percentile(vals, 0.95) if vals else None,
        ),
    )


def _fit_linear_minmax(
    selection: FitSampleSelection,
    fit_spec: CalibrationFitSpec,
) -> tuple[dict[str, Any], FitStats]:
    """Fit linear_minmax: observed min/max from corpus."""
    vals = selection.used_values
    obs_min = min(vals)
    obs_max = max(vals)
    degenerate = obs_min == obs_max
    return (
        {
            "observed_min": obs_min,
            "observed_max": obs_max,
            "clip_min": fit_spec.clip_min,
            "clip_max": fit_spec.clip_max,
        },
        FitStats(
            degenerate_fit=degenerate,
            observed_min=obs_min,
            observed_max=obs_max,
            mean=statistics.mean(vals),
            p50=statistics.median(vals),
            p95=_percentile(vals, 0.95),
        ),
    )


def _fit_log_minmax(
    selection: FitSampleSelection,
    fit_spec: CalibrationFitSpec,
) -> tuple[dict[str, Any], FitStats]:
    """Fit log_minmax: observed min/max from domain-valid corpus."""
    vals = selection.used_values
    obs_min = min(vals)
    obs_max = max(vals)
    degenerate = obs_min == obs_max
    return (
        {
            "observed_min": obs_min,
            "observed_max": obs_max,
            "log_base": fit_spec.log_base,
            "epsilon_shift": fit_spec.epsilon_shift,
            "clip_min": fit_spec.clip_min,
            "clip_max": fit_spec.clip_max,
        },
        FitStats(
            degenerate_fit=degenerate,
            observed_min=obs_min,
            observed_max=obs_max,
            mean=statistics.mean(vals),
            p50=statistics.median(vals),
            p95=_percentile(vals, 0.95),
        ),
    )


_FIT_METHODS = {
    "identity_clip": _fit_identity_clip,
    "linear_minmax": _fit_linear_minmax,
    "log_minmax": _fit_log_minmax,
}


def _percentile(values: tuple[float, ...] | list[float], q: float) -> float:
    """Simple percentile calculation (nearest-rank)."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(q * (len(s) - 1))
    return s[idx]


# ── Fit summary envelope ─────────────────────────────────────────────────────


def fit_summary_envelope(
    fit_spec: CalibrationFitSpec,
    selection: FitSampleSelection,
    fit_stats: FitStats | None,
    param_set: CalibrationParamSet | None,
    *,
    quality_status: str = QualityStatus.OK.value,
    quality_reasons: list[str] | None = None,
    error_messages: list[str] | None = None,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Build a fit summary artifact (always emitted, even on failure)."""
    ts = emitted_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    values: dict[str, Any] = {
        "fit_id": fit_spec.fit_id,
        "fit_spec_hash": fit_spec.fit_spec_hash(),
        "source_manifest_hash": fit_spec.source_manifest_hash,
        "source_replay_run_id": fit_spec.source_replay_run_id,
        "param_set_id": param_set.param_set_id if param_set else None,
        "param_set_hash": param_set.param_set_hash() if param_set else None,
        "signal_id": fit_spec.signal_id,
        "signal_version": fit_spec.signal_version,
        "target_field": fit_spec.target_field,
        "method": fit_spec.method,
        "sample_count_total": selection.sample_count_total,
        "sample_count_used": selection.sample_count_used,
        "sample_count_excluded": selection.sample_count_excluded,
        "exclusion_reason_counts": selection.exclusion_reason_counts,
        "clip_min": fit_spec.clip_min,
        "clip_max": fit_spec.clip_max,
    }

    if fit_stats:
        values["degenerate_fit"] = fit_stats.degenerate_fit
        values["observed_min"] = fit_stats.observed_min
        values["observed_max"] = fit_stats.observed_max
        values["mean"] = fit_stats.mean
        values["p50"] = fit_stats.p50
        values["p95"] = fit_stats.p95

    if fit_spec.method == "log_minmax":
        values["log_base"] = fit_spec.log_base
        values["epsilon_shift"] = fit_spec.epsilon_shift

    annotations: dict[str, Any] = {
        "calibration_fit_applied": True,
        "fit_config_version": CALIBRATION_FIT_CONFIG_VERSION,
    }
    if error_messages:
        annotations["error_messages"] = error_messages[:10]

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=ts,
        emitter="governor.signals.calibration_fitting",
        emitter_version="2.4.0-dev",
        signal_id="CALIBRATION_FIT_SUMMARY",
        signal_version=1,
        phase="2.4C",
        subject_type="corpus",
        subject_id=fit_spec.fit_id,
        value=float(selection.sample_count_used) if selection.sample_count_used else None,
        unit="count",
        values=values,
        quality_status=quality_status,
        quality_reasons=quality_reasons or [],
        sample_size=selection.sample_count_total,
        derivation=DerivationType.DERIVED.value,
        derivation_version=CALIBRATION_FIT_CONFIG_VERSION,
        annotations=annotations,
    )


# ── Orchestration ────────────────────────────────────────────────────────────


def fit_param_set_from_corpus(
    envelopes: Sequence[SignalEnvelope],
    fit_spec: CalibrationFitSpec,
    *,
    emitted_at: str | None = None,
) -> FitResult:
    """Fit a CalibrationParamSet from a corpus of signal envelopes.

    Returns FitResult with param_set (None on failure) and summary_envelope
    (always present). Deterministic for same inputs + spec + emitted_at.
    """
    # 1. Validate fit spec
    try:
        validate_fit_spec(fit_spec)
    except CalibrationMismatchError as e:
        summary = fit_summary_envelope(
            fit_spec,
            FitSampleSelection(
                samples=(),
                sample_count_total=0,
                sample_count_used=0,
                sample_count_excluded=0,
                exclusion_reason_counts={},
                used_values=(),
            ),
            fit_stats=None,
            param_set=None,
            quality_status=QualityStatus.INVALID.value,
            quality_reasons=[f"invalid_fit_spec: {e.reason}"],
            error_messages=[e.reason],
            emitted_at=emitted_at,
        )
        return FitResult(
            param_set=None,
            summary_envelope=summary,
            errors=(e.reason,),
        )

    # 2. Extract samples
    selection = extract_fit_samples(envelopes, fit_spec)

    # 3. Check minimum sample count
    if selection.sample_count_used < fit_spec.min_sample_count:
        reason = (
            f"insufficient samples: {selection.sample_count_used} valid "
            f"< min_sample_count={fit_spec.min_sample_count}"
        )
        summary = fit_summary_envelope(
            fit_spec,
            selection,
            fit_stats=None,
            param_set=None,
            quality_status=QualityStatus.UNAVAILABLE.value,
            quality_reasons=[reason],
            error_messages=[reason],
            emitted_at=emitted_at,
        )
        return FitResult(
            param_set=None,
            summary_envelope=summary,
            errors=(reason,),
        )

    # 4. Dispatch method fit
    fit_fn = _FIT_METHODS[fit_spec.method]
    params, fit_stats = fit_fn(selection, fit_spec)

    # 5. Build CalibrationParamSet
    ts = emitted_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    param_set = CalibrationParamSet(
        param_set_id=f"{fit_spec.fit_id}_ps",
        signal_id=fit_spec.signal_id,
        signal_version=fit_spec.signal_version,
        target_field=fit_spec.target_field,
        method=fit_spec.method,
        params=params,
        fit_source=fit_spec.source_replay_run_id or fit_spec.source_mode,
        fit_window_range=selection.window_range,
        include_quality_statuses=fit_spec.include_quality_statuses,
        exclude_classifications=fit_spec.exclude_classifications,
        fit_window_count=selection.sample_count_used,
        fit_skipped_count=selection.sample_count_excluded,
        created_at=ts,
        derivation_version=CALIBRATION_FIT_CONFIG_VERSION,
    )

    # 6. Build summary
    summary = fit_summary_envelope(
        fit_spec,
        selection,
        fit_stats=fit_stats,
        param_set=param_set,
        quality_status=QualityStatus.OK.value,
        emitted_at=emitted_at,
    )

    return FitResult(
        param_set=param_set,
        summary_envelope=summary,
        errors=(),
    )
