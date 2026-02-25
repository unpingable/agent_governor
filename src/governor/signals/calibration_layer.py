# SPDX-License-Identifier: Apache-2.0
"""
CALIBRATION_LAYER — apply-only calibration for raw A/B signals.

Normalizes raw signal values to [0,1] using frozen, versioned parameter sets.
This is the apply path only — no fitting from replay corpora yet.

Key invariants:
  - Refuse = CalibrationMismatchError (exception, not degraded output)
  - Quality never upgrades (unavailable/invalid → value=None, quality preserved)
  - Missing ≠ zero preserved (None stays None, 0.0 gets calibrated)
  - Companion envelope, not mutation (new envelope, source unchanged)
  - params is truly immutable (MappingProxyType wraps a *copy*)
  - bool is not numeric

Design authority: specs/gaps/V2_4C_SPINE.md §3
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from .calibration_methods import (
    CALIBRATION_METHODS,
    REQUIRED_PARAMS,
    CalibrationMismatchError,
)
from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    SignalEnvelope,
    canonical_json,
    content_hash,
)


# ── Config ───────────────────────────────────────────────────────────────────

CALIBRATION_CONFIG_VERSION = "calibration-layer-v1"

# Quality statuses that pass through without calibration (value=None)
PASSTHROUGH_QUALITIES = frozenset({"unavailable", "invalid"})


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_numeric(value: Any) -> bool:
    """True if value is int or float but NOT bool.

    Python bool is a subclass of int, so isinstance(True, int) is True.
    We exclude bools explicitly because they are not signal values.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _hash_envelope(env: SignalEnvelope) -> str:
    """Content hash of a source envelope."""
    return content_hash(env.to_canonical_bytes())


# ── CalibrationParamSet ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationParamSet:
    """Frozen, versioned parameter set for calibration.

    params field is wrapped in MappingProxyType for true immutability.
    __post_init__ copies the source dict before wrapping — MappingProxyType
    alone is a read-only *view*, not a copy.
    """

    param_set_id: str
    signal_id: str
    signal_version: int
    target_field: str               # "value" or named field in values
    method: str                     # "identity_clip" | "linear_minmax" | "log_minmax"
    params: MappingProxyType        # truly immutable — __post_init__ copies + wraps
    fit_source: str | None = None
    fit_window_range: str | None = None
    include_quality_statuses: frozenset[str] = field(default_factory=frozenset)
    exclude_classifications: frozenset[str] = field(default_factory=frozenset)
    fit_window_count: int | None = None
    fit_skipped_count: int | None = None
    created_at: str = ""
    derivation_version: str = CALIBRATION_CONFIG_VERSION

    def __post_init__(self) -> None:
        # Copy + wrap → true immutability (MappingProxyType is a view, not a copy)
        if isinstance(self.params, MappingProxyType):
            # Already wrapped — re-wrap a copy to ensure isolation
            object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        else:
            # Raw dict or other mapping — copy then wrap
            object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict. params → dict, frozensets → sorted lists."""
        return {
            "param_set_id": self.param_set_id,
            "signal_id": self.signal_id,
            "signal_version": self.signal_version,
            "target_field": self.target_field,
            "method": self.method,
            "params": dict(self.params),
            "fit_source": self.fit_source,
            "fit_window_range": self.fit_window_range,
            "include_quality_statuses": sorted(self.include_quality_statuses),
            "exclude_classifications": sorted(self.exclude_classifications),
            "fit_window_count": self.fit_window_count,
            "fit_skipped_count": self.fit_skipped_count,
            "created_at": self.created_at,
            "derivation_version": self.derivation_version,
        }

    def param_set_hash(self) -> str:
        """Content-addressed hash of apply-semantic fields.

        Covers: param_set_id, signal_id, signal_version, target_field,
        method, params, derivation_version. Fit metadata excluded (provenance
        about *where* params came from, not *what* they mean).
        """
        payload = {
            "param_set_id": self.param_set_id,
            "signal_id": self.signal_id,
            "signal_version": self.signal_version,
            "target_field": self.target_field,
            "method": self.method,
            "params": dict(self.params),
            "derivation_version": self.derivation_version,
        }
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationParamSet:
        """Deserialize from dict. Lists → frozensets, dict → MappingProxyType."""
        return cls(
            param_set_id=d["param_set_id"],
            signal_id=d["signal_id"],
            signal_version=d["signal_version"],
            target_field=d["target_field"],
            method=d["method"],
            params=d.get("params", {}),
            fit_source=d.get("fit_source"),
            fit_window_range=d.get("fit_window_range"),
            include_quality_statuses=frozenset(d.get("include_quality_statuses", [])),
            exclude_classifications=frozenset(d.get("exclude_classifications", [])),
            fit_window_count=d.get("fit_window_count"),
            fit_skipped_count=d.get("fit_skipped_count"),
            created_at=d.get("created_at", ""),
            derivation_version=d.get("derivation_version", CALIBRATION_CONFIG_VERSION),
        )


# ── Validation ───────────────────────────────────────────────────────────────


def validate_param_set(param_set: CalibrationParamSet, source_env: SignalEnvelope) -> None:
    """Validate that a param set is compatible with a source envelope.

    Raises CalibrationMismatchError on mismatch.
    """
    if param_set.signal_id != source_env.signal_id:
        raise CalibrationMismatchError(
            f"signal_id mismatch: param_set={param_set.signal_id!r}, "
            f"source={source_env.signal_id!r}",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )

    if param_set.signal_version != source_env.signal_version:
        raise CalibrationMismatchError(
            f"signal_version mismatch: param_set={param_set.signal_version}, "
            f"source={source_env.signal_version}",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )

    # Validate target field exists and is numeric
    if param_set.target_field == "value":
        raw = source_env.value
    elif param_set.target_field in source_env.values:
        raw = source_env.values[param_set.target_field]
    else:
        raise CalibrationMismatchError(
            f"target_field {param_set.target_field!r} not found in source envelope "
            f"(not 'value' and not in values dict)",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )

    # Target field must be numeric or None (None handled at apply time)
    if raw is not None and not _is_numeric(raw):
        raise CalibrationMismatchError(
            f"target_field {param_set.target_field!r} value {raw!r} "
            f"(type {type(raw).__name__}) is not numeric",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )

    # Method must be known
    if param_set.method not in CALIBRATION_METHODS:
        raise CalibrationMismatchError(
            f"unknown method {param_set.method!r} "
            f"(known: {sorted(CALIBRATION_METHODS)})",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )

    # Required params for method must be present
    required = REQUIRED_PARAMS.get(param_set.method, frozenset())
    missing = required - set(param_set.params.keys())
    if missing:
        raise CalibrationMismatchError(
            f"missing required params for {param_set.method}: {sorted(missing)}",
            param_set_id=param_set.param_set_id,
            signal_id=source_env.signal_id,
        )


# ── Apply ────────────────────────────────────────────────────────────────────


def apply_calibration(
    source_env: SignalEnvelope,
    param_set: CalibrationParamSet,
    *,
    emitted_at: str | None = None,
) -> SignalEnvelope:
    """Apply calibration to a source signal envelope.

    Returns a new companion envelope with normalized value in [0,1].
    Source envelope is never mutated.

    Quality propagation:
      - ok/partial: calibrate normally, quality preserved
      - unavailable/invalid: value=None, quality preserved
      - None raw value: value=None, quality preserved

    Raises CalibrationMismatchError on param/source mismatch.
    """
    # 1. Validate compatibility
    validate_param_set(param_set, source_env)

    # 2. Extract raw value
    if param_set.target_field == "value":
        raw_value = source_env.value
    else:
        raw_value = source_env.values[param_set.target_field]

    # 3. Determine if we should calibrate or pass through
    normalized: float | None = None
    if raw_value is None:
        normalized = None
    elif source_env.quality_status in PASSTHROUGH_QUALITIES:
        normalized = None
    else:
        # Apply calibration method
        method_fn = CALIBRATION_METHODS[param_set.method]
        normalized = method_fn(float(raw_value), param_set.params)

    # 4. Build companion values
    values = {
        "raw_value": raw_value,
        "normalized_value": normalized,
        "calibration_method": param_set.method,
        "param_set_id": param_set.param_set_id,
        "input_quality_status": source_env.quality_status,
        "config_version": CALIBRATION_CONFIG_VERSION,
        "target_field": param_set.target_field,
        "source_unit": source_env.unit,
    }

    # 5. Build companion annotations
    annotations = {
        "source_signal_hash": _hash_envelope(source_env),
        "calibration_applied": True,
        "param_set_id": param_set.param_set_id,
        "param_set_hash": param_set.param_set_hash(),
        "config_version": CALIBRATION_CONFIG_VERSION,
    }

    # 6. Build companion envelope
    ts = emitted_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return SignalEnvelope(
        schema_version=source_env.schema_version,
        emitted_at=ts,
        emitter="governor.signals.calibration_layer",
        emitter_version=source_env.emitter_version,
        signal_id=source_env.signal_id,
        signal_version=source_env.signal_version,
        phase="2.4C",
        subject_type=source_env.subject_type,
        subject_id=source_env.subject_id,
        correlation_id=source_env.correlation_id,
        session_id=source_env.session_id,
        window_start=source_env.window_start,
        window_end=source_env.window_end,
        window_kind=source_env.window_kind,
        value=normalized,
        unit="normalized",
        values=values,
        quality_status=source_env.quality_status,
        quality_reasons=list(source_env.quality_reasons),
        sample_size=source_env.sample_size,
        completeness=source_env.completeness,
        source_receipt_ids=list(source_env.source_receipt_ids),
        source_streams=list(source_env.source_streams),
        source_versions=dict(source_env.source_versions),
        derivation=DerivationType.DERIVED.value,
        derivation_version=CALIBRATION_CONFIG_VERSION,
        annotations=annotations,
    )
