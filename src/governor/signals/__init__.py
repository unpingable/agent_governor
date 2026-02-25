# SPDX-License-Identifier: Apache-2.0
"""
v2.4 Instrumentation Spine — signal envelope, emitter, and derivations.

Phase A substrate: envelope model, quality semantics, JSONL emission.
Signal derivation modules: exposure_proxy, silent_suppression, sigma_rate.
"""

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    validate_envelope,
)
from .emit import JsonlSink, SignalEmitter
from .exposure_proxy import (
    DEFAULT_WEIGHT_SET_ID,
    DEFAULT_WEIGHTS,
    ExposureComponents,
    compute_exposure_points,
    count_from_receipts,
    derive_exposure_proxy,
)
from .sigma_rate import (
    MATCH_RULE_VERSION,
    SIGMA_FALLBACK_COMPLETENESS,
    ReceiptEvent,
    SigmaEvent,
    SigmaMatchResult,
    derive_sigma_rate,
    match_sigma_pairs,
)
from .silent_suppression import (
    SuppressionIndicators,
    classify_suppression,
    derive_silent_suppression,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_WEIGHT_SET_ID",
    "DEFAULT_WEIGHTS",
    "DerivationType",
    "ExposureComponents",
    "JsonlSink",
    "QualityStatus",
    "SignalEmitter",
    "SignalEnvelope",
    "SuppressionIndicators",
    "MATCH_RULE_VERSION",
    "SIGMA_FALLBACK_COMPLETENESS",
    "ReceiptEvent",
    "SigmaEvent",
    "SigmaMatchResult",
    "classify_suppression",
    "compute_exposure_points",
    "count_from_receipts",
    "derive_exposure_proxy",
    "derive_sigma_rate",
    "derive_silent_suppression",
    "match_sigma_pairs",
    "validate_envelope",
]
