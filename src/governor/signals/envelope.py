# SPDX-License-Identifier: Apache-2.0
"""
SignalEnvelope — canonical emission shape for v2.4 instrumentation spine.

Design authority: specs/gaps/V2_4A_SPINE.md + golden fixtures.
v3 promotion: nest flat fields into typed structs, bump schema_version.

Key invariants:
  - missing != zero (value=None + quality_status="unavailable" is distinct from value=0.0)
  - observe-only (no policy/gating changes)
  - versioned semantics (signal_version, derivation_version, source_versions)
  - receipt-linkable provenance (source_receipt_ids, source_streams)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


CURRENT_SCHEMA_VERSION = "0.4.0"


class QualityStatus(str, Enum):
    """Quality of a signal computation.

    ok:          metric computed and trustworthy
    partial:     computed with degraded coverage
    unavailable: cannot compute (missing source, no denominator, daemon down)
    invalid:     computation attempted but inputs violated invariants
    """

    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class DerivationType(str, Enum):
    """How this signal value was produced."""

    DIRECT = "direct"
    WINDOWED_AGGREGATE = "windowed_aggregate"
    DERIVED = "derived"


# ── Canonical JSON (same convention as gate_receipt.py) ──────────────────────

def canonical_json(obj: dict) -> bytes:
    """Deterministic JSON bytes for hashing. Matches gate_receipt.py convention."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest with prefix."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ── SignalEnvelope ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalEnvelope:
    """Canonical emission shape for instrumentation signals.

    Every field matches the golden fixture schema exactly. Signal-specific
    data goes in ``values`` (named submetrics) and ``annotations`` (non-
    semantic extras). Nothing required for metric reconstruction belongs
    in annotations.
    """

    # ── Envelope identity ────────────────────────────────────────────────
    schema_version: str
    emitted_at: str                              # ISO 8601 UTC
    emitter: str                                 # e.g. "governor.daemon"
    emitter_version: str                         # app/build version

    # ── Signal identity ──────────────────────────────────────────────────
    signal_id: str                               # "EXPOSURE_PROXY" etc.
    signal_version: int                          # semantic version of signal logic
    phase: str                                   # "2.4A"

    # ── Subject / scope ──────────────────────────────────────────────────
    subject_type: str                            # "session" | "window" | "runtime"
    subject_id: str | None = None
    correlation_id: str | None = None
    session_id: str | None = None

    # ── Windowing ────────────────────────────────────────────────────────
    window_start: str | None = None              # ISO 8601 UTC
    window_end: str | None = None                # ISO 8601 UTC
    window_kind: str | None = None               # "rolling_5m" etc.

    # ── Values ───────────────────────────────────────────────────────────
    value: float | None = None                   # primary scalar (None = not computable)
    unit: str | None = None                      # "ratio" | "rate" | "exposure_points" etc.
    values: dict[str, Any] = field(default_factory=dict)  # named submetrics

    # ── Quality ──────────────────────────────────────────────────────────
    quality_status: str = QualityStatus.OK.value
    quality_reasons: list[str] = field(default_factory=list)
    sample_size: int | None = None
    completeness: float | None = None            # [0,1]

    # ── Provenance ───────────────────────────────────────────────────────
    source_receipt_ids: list[str] = field(default_factory=list)
    source_streams: list[str] = field(default_factory=list)
    source_versions: dict[str, str] = field(default_factory=dict)

    # ── Derivation ───────────────────────────────────────────────────────
    derivation: str = DerivationType.DIRECT.value
    derivation_version: str = ""

    # ── Annotations (non-semantic extras) ────────────────────────────────
    annotations: dict[str, Any] = field(default_factory=dict)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict (JSON-serializable)."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string (human-readable, not canonical)."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=True)

    def to_canonical_bytes(self) -> bytes:
        """Canonical JSON bytes for hashing / content-addressing."""
        return canonical_json(self.to_dict())

    def content_hash(self) -> str:
        """SHA-256 of canonical JSON. Content-addressed identity."""
        return content_hash(self.to_canonical_bytes())

    def values_hash(self) -> str:
        """SHA-256 of canonical JSON of the values dict only."""
        return content_hash(canonical_json(self.values))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalEnvelope:
        """Construct from dict (e.g. parsed JSON). Unknown keys are ignored."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, text: str) -> SignalEnvelope:
        """Construct from JSON string."""
        return cls.from_dict(json.loads(text))


# ── Validation ───────────────────────────────────────────────────────────────

class EnvelopeValidationError(ValueError):
    """Raised when an envelope violates structural invariants."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Envelope validation failed: {'; '.join(errors)}")


def validate_envelope(env: SignalEnvelope) -> list[str]:
    """Validate structural invariants. Returns list of error strings (empty = valid).

    Rules:
      - Required fields must be present and non-empty
      - quality_status must be a valid QualityStatus value
      - derivation must be a valid DerivationType value
      - quality_status="ok" requires value or non-empty values
      - quality_status="unavailable" with value != None is suspect (warning, not error)
      - Windowed signals must have window fields
      - quality_reasons must be a list (never None/omitted)
      - source_versions, source_streams, source_receipt_ids must be lists/dicts
    """
    errors: list[str] = []

    # ── Required non-empty strings ───────────────────────────────────────
    for name in (
        "schema_version", "emitted_at", "emitter", "emitter_version",
        "signal_id", "phase", "subject_type", "derivation",
        "derivation_version",
    ):
        val = getattr(env, name, None)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"required field '{name}' is missing or empty")

    # ── signal_version must be positive int ──────────────────────────────
    if not isinstance(env.signal_version, int) or env.signal_version < 1:
        errors.append("signal_version must be a positive integer")

    # ── Enum validity ────────────────────────────────────────────────────
    valid_quality = {s.value for s in QualityStatus}
    if env.quality_status not in valid_quality:
        errors.append(
            f"quality_status '{env.quality_status}' not in {sorted(valid_quality)}"
        )

    valid_derivation = {d.value for d in DerivationType}
    if env.derivation not in valid_derivation:
        errors.append(
            f"derivation '{env.derivation}' not in {sorted(valid_derivation)}"
        )

    # ── quality_status="ok" requires a value ─────────────────────────────
    if env.quality_status == QualityStatus.OK.value:
        if env.value is None and not env.values:
            errors.append(
                "quality_status='ok' requires 'value' or non-empty 'values'"
            )

    # ── missing != zero: unavailable should have value=None ──────────────
    if env.quality_status == QualityStatus.UNAVAILABLE.value:
        if env.value is not None and env.value == 0.0:
            # This is a warning-level issue. We surface it as an error because
            # conflating zero with missing is exactly the anti-pattern we're
            # guarding against.
            errors.append(
                "quality_status='unavailable' should not have value=0.0 "
                "(zero means observed absence, None means unknown)"
            )

    # ── Windowed signals need window fields ──────────────────────────────
    if env.window_kind is not None:
        if not env.window_start or not env.window_end:
            errors.append(
                "window_kind is set but window_start/window_end are missing"
            )

    # ── quality_reasons must be a list ───────────────────────────────────
    if not isinstance(env.quality_reasons, list):
        errors.append("quality_reasons must be a list")

    # ── Collection types ─────────────────────────────────────────────────
    if not isinstance(env.source_receipt_ids, list):
        errors.append("source_receipt_ids must be a list")
    if not isinstance(env.source_streams, list):
        errors.append("source_streams must be a list")
    if not isinstance(env.source_versions, dict):
        errors.append("source_versions must be a dict")
    if not isinstance(env.values, dict):
        errors.append("values must be a dict")
    if not isinstance(env.annotations, dict):
        errors.append("annotations must be a dict")

    return errors
