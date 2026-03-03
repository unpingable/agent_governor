# SPDX-License-Identifier: Apache-2.0
"""
v2.4 Instrumentation Spine — signal envelope, emitter, and derivations.

Phase A substrate: envelope model, quality semantics, JSONL emission.
Signal derivation modules: exposure_proxy, silent_suppression, sigma_rate.
Phase B: advisory diagnostics over Phase A signals.
Phase C: replay harness and calibration layer.
Phase D: regime prediction from calibrated signals.
"""

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    default_source_versions,
    validate_envelope,
)
from .emit import (
    SIGNAL_EMIT_FAILED,
    SIGNAL_EMIT_FAILED_VERSION,
    JsonlSink,
    SignalEmitter,
    build_emit_failed_envelope,
)
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
from .calibration_fitting import (
    CALIBRATION_FIT_CONFIG_VERSION,
    CalibrationFitSpec,
    FitResult,
    FitSample,
    FitSampleSelection,
    extract_fit_samples,
    fit_param_set_from_corpus,
    fit_summary_envelope,
    validate_fit_spec,
)
from .gate_check_summary import (
    SIGNAL_ID as GATE_CHECK_SUMMARY_SIGNAL_ID,
    build_gate_check_summary,
    build_gate_check_error_summary,
    try_emit_gate_check_summary,
)
from .predict_regime import (
    ALL_EXPECTED_SIGNALS,
    ALL_REGIMES,
    DEFAULT_CONFIG,
    OPTIONAL_SIGNALS,
    PREFLIGHT_CONFIG_VERSION,
    REQUIRED_SIGNALS,
    PreflightConfig,
    PreflightInput,
    PreflightInputSet,
    PreflightRegime,
    extract_preflight_inputs,
    predict_regime_preflight,
)

__all__ = [
    # Envelope
    "CURRENT_SCHEMA_VERSION",
    "DerivationType",
    "QualityStatus",
    "default_source_versions",
    "SIGNAL_EMIT_FAILED",
    "SIGNAL_EMIT_FAILED_VERSION",
    "SignalEmitter",
    "SignalEnvelope",
    "JsonlSink",
    "build_emit_failed_envelope",
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
    # C2: Calibration Fitting
    "CALIBRATION_FIT_CONFIG_VERSION",
    "CalibrationFitSpec",
    "FitResult",
    "FitSample",
    "FitSampleSelection",
    "extract_fit_samples",
    "fit_param_set_from_corpus",
    "fit_summary_envelope",
    "validate_fit_spec",
    # Gate Check Summary
    "GATE_CHECK_SUMMARY_SIGNAL_ID",
    "build_gate_check_summary",
    "build_gate_check_error_summary",
    "try_emit_gate_check_summary",
    # D: Predict Regime Preflight
    "ALL_EXPECTED_SIGNALS",
    "ALL_REGIMES",
    "DEFAULT_CONFIG",
    "OPTIONAL_SIGNALS",
    "PREFLIGHT_CONFIG_VERSION",
    "REQUIRED_SIGNALS",
    "PreflightConfig",
    "PreflightInput",
    "PreflightInputSet",
    "PreflightRegime",
    "extract_preflight_inputs",
    "predict_regime_preflight",
]
