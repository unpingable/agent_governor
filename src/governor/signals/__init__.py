# SPDX-License-Identifier: Apache-2.0
"""
v2.4 Instrumentation Spine — signal envelope, emitter, and derivations.

Phase A substrate: envelope model, quality semantics, JSONL emission.
Signal derivation modules: exposure_proxy, silent_suppression, sigma_rate.
Phase B: advisory diagnostics over Phase A signals.
Phase C: replay harness and calibration layer.
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
from .capture_self_diagnostic import (
    ALL_CLASSIFICATIONS,
    DIAG_CONFIG_VERSION,
    DiagnosticInputs,
    derive_capture_self_diagnostic,
)
from .decision_evidence_lag import (
    CLASSIFICATION_BACKFILLED,
    CLASSIFICATION_POLICY_EXEMPT,
    CLASSIFICATION_SUPPORTED,
    CLASSIFICATION_UNSUPPORTED,
    DECISION_GATES,
    LAG_CONFIG_VERSION,
    POLICY_EXEMPT_GATES,
    DecisionClassification,
    LagAggregateResult,
    ReceiptRecord,
    classify_decisions,
    derive_decision_evidence_lag,
)
from .replay_harness import (
    DERIVATION_REGISTRY,
    REPLAY_CONFIG_VERSION,
    DerivationEntry,
    ReplayManifest,
    ReplaySpec,
    ReplayWindowInput,
    ReplayWindowResult,
    replay_summary_envelope,
    replay_windows,
)
from .replay_sources import (
    prepare_envelope_windows,
    prepare_receipt_windows,
)
from .calibration_methods import (
    CALIBRATION_METHODS,
    REQUIRED_PARAMS,
    CalibrationMismatchError,
    identity_clip,
    linear_minmax,
    log_minmax,
)
from .calibration_layer import (
    CALIBRATION_CONFIG_VERSION,
    CalibrationParamSet,
    apply_calibration,
)

__all__ = [
    # Envelope
    "CURRENT_SCHEMA_VERSION",
    "DerivationType",
    "QualityStatus",
    "SignalEmitter",
    "SignalEnvelope",
    "JsonlSink",
    "validate_envelope",
    # A1: Exposure Proxy
    "DEFAULT_WEIGHT_SET_ID",
    "DEFAULT_WEIGHTS",
    "ExposureComponents",
    "compute_exposure_points",
    "count_from_receipts",
    "derive_exposure_proxy",
    # A2: Silent Suppression
    "SuppressionIndicators",
    "classify_suppression",
    "derive_silent_suppression",
    # A3: Sigma Rate
    "MATCH_RULE_VERSION",
    "SIGMA_FALLBACK_COMPLETENESS",
    "ReceiptEvent",
    "SigmaEvent",
    "SigmaMatchResult",
    "derive_sigma_rate",
    "match_sigma_pairs",
    # B1: Capture Self Diagnostic
    "ALL_CLASSIFICATIONS",
    "DIAG_CONFIG_VERSION",
    "DiagnosticInputs",
    "derive_capture_self_diagnostic",
    # B2: Decision Evidence Lag
    "CLASSIFICATION_BACKFILLED",
    "CLASSIFICATION_POLICY_EXEMPT",
    "CLASSIFICATION_SUPPORTED",
    "CLASSIFICATION_UNSUPPORTED",
    "DECISION_GATES",
    "LAG_CONFIG_VERSION",
    "POLICY_EXEMPT_GATES",
    "DecisionClassification",
    "LagAggregateResult",
    "ReceiptRecord",
    "classify_decisions",
    "derive_decision_evidence_lag",
    # C1: Replay Harness
    "DERIVATION_REGISTRY",
    "REPLAY_CONFIG_VERSION",
    "DerivationEntry",
    "ReplayManifest",
    "ReplaySpec",
    "ReplayWindowInput",
    "ReplayWindowResult",
    "replay_summary_envelope",
    "replay_windows",
    "prepare_envelope_windows",
    "prepare_receipt_windows",
    # C2: Calibration Layer
    "CALIBRATION_CONFIG_VERSION",
    "CALIBRATION_METHODS",
    "REQUIRED_PARAMS",
    "CalibrationMismatchError",
    "CalibrationParamSet",
    "apply_calibration",
    "identity_clip",
    "linear_minmax",
    "log_minmax",
]
