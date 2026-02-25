# SPDX-License-Identifier: Apache-2.0
"""Tests for CAPTURE_SELF_DIAGNOSTIC (Phase B1)."""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from governor.signals.capture_self_diagnostic import (
    ALL_CLASSIFICATIONS,
    CLASSIFICATION_INDETERMINATE,
    CLASSIFICATION_INSTRUMENTATION_COMPROMISED,
    CLASSIFICATION_INSUFFICIENT_HISTORY,
    CLASSIFICATION_NORMAL,
    CLASSIFICATION_WARNING,
    CLASSIFICATION_WATCH,
    COVERAGE_WEIGHT,
    DIAG_CONFIG_VERSION,
    INVALID_PAIRS_PENALTY,
    INVALID_PAIRS_PENALTY_WEIGHT,
    LOW_COVERAGE_THRESHOLD,
    SIGMA_RATE_CEILING,
    SIGMA_WEIGHT,
    WARNING_THRESHOLD,
    WATCH_THRESHOLD,
    DiagnosticInputs,
    _classify_from_score,
    _compute_capture_score,
    _validate_window_alignment,
    derive_capture_self_diagnostic,
)
from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    validate_envelope,
)


# ── Test fixtures / helpers ────────────────────────────────────────────────

WINDOW_START = "2026-02-25T10:00:00Z"
WINDOW_END = "2026-02-25T10:05:00Z"
WINDOW_KIND = "rolling_5m"
EMITTED_AT = "2026-02-25T10:05:00Z"


def _make_a1(
    value: float | None = 10.0,
    quality_status: str = "ok",
    coverage_ratio: float = 1.0,
    completeness: float | None = 1.0,
    window_start: str = WINDOW_START,
    window_end: str = WINDOW_END,
    window_kind: str = WINDOW_KIND,
) -> SignalEnvelope:
    """Build a minimal A1 (EXPOSURE_PROXY) envelope."""
    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=EMITTED_AT,
        emitter="governor.signals.exposure_proxy",
        emitter_version="test",
        signal_id="EXPOSURE_PROXY",
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        subject_id=f"win_{window_start}_{window_kind}",
        session_id=None,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="exposure_points",
        values={
            "exposure_points_total": value or 0.0,
            "eligible_events": 10,
            "excluded_events": 0,
            "weighted_event_count": value or 0.0,
            "coverage_ratio": coverage_ratio,
            "source_event_count": 10,
        },
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=10,
        completeness=completeness,
        source_receipt_ids=[],
        source_streams=[],
        source_versions={},
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="exposure-proxy-v1",
    )


def _make_a2(
    value: float | None = 1.0,
    quality_status: str = "ok",
    classification: str = "healthy",
    completeness: float | None = 1.0,
    window_start: str = WINDOW_START,
    window_end: str = WINDOW_END,
    window_kind: str = WINDOW_KIND,
) -> SignalEnvelope:
    """Build a minimal A2 (SILENT_SUPPRESSION) envelope."""
    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=EMITTED_AT,
        emitter="governor.signals.silent_suppression",
        emitter_version="test",
        signal_id="SILENT_SUPPRESSION",
        signal_version=1,
        phase="2.4A",
        subject_type="runtime",
        subject_id=f"runtime_{window_start}_{window_kind}",
        session_id=None,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="ratio",
        values={
            "expected_heartbeat_count": 5,
            "observed_heartbeat_count": 5,
            "expected_event_markers": 3,
            "observed_event_markers": 3,
            "daemon_reachable": 1,
            "in_path_evidence_present": 1,
            "activity_observed": 1,
            "suppression_detected": 0,
        },
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=5,
        completeness=completeness,
        source_receipt_ids=[],
        source_streams=[],
        source_versions={},
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="silent-suppression-v1",
        annotations={"classification": classification},
    )


def _make_a3(
    value: float | None = 0.0,
    quality_status: str = "ok",
    sigma_events: int = 0,
    invalid_pairs_count: int = 0,
    denominator_type: str = "exposure_proxy",
    completeness: float | None = 1.0,
    window_start: str = WINDOW_START,
    window_end: str = WINDOW_END,
    window_kind: str = WINDOW_KIND,
) -> SignalEnvelope:
    """Build a minimal A3 (SIGMA_RATE) envelope."""
    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=EMITTED_AT,
        emitter="governor.signals.sigma_rate",
        emitter_version="test",
        signal_id="SIGMA_RATE",
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        subject_id=f"win_{window_start}_{window_kind}",
        session_id=None,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="rate",
        values={
            "sigma_events": sigma_events,
            "eligible_events": 10,
            "denominator_value": 10,
            "denominator_type": denominator_type,
            "match_rule_version": "sigma-match-v1",
            "mean_lag_ms": None,
            "p95_lag_ms": None,
            "matched_pairs_count": sigma_events,
            "dropped_endorsements": 0,
            "dropped_invalidations": 0,
            "invalid_pairs_count": invalid_pairs_count,
        },
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=10,
        completeness=completeness,
        source_receipt_ids=[],
        source_streams=[],
        source_versions={},
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="sigma-rate-v1",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Config constants are sane."""

    def test_classifications_complete(self):
        assert len(ALL_CLASSIFICATIONS) == 6

    def test_config_version_string(self):
        assert DIAG_CONFIG_VERSION == "capture-selfdiag-v1"

    def test_thresholds_ordered(self):
        assert 0 < WATCH_THRESHOLD < WARNING_THRESHOLD < 1.0

    def test_weights_positive(self):
        assert SIGMA_WEIGHT > 0
        assert COVERAGE_WEIGHT > 0
        assert SIGMA_RATE_CEILING > 0
        assert LOW_COVERAGE_THRESHOLD > 0

    def test_sigma_plus_coverage_weight_sums_to_one(self):
        assert SIGMA_WEIGHT + COVERAGE_WEIGHT == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Window alignment validation
# ═══════════════════════════════════════════════════════════════════════════

class TestWindowAlignment:
    """Window alignment checks."""

    def test_all_matching_windows(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        assert _validate_window_alignment(inputs) == []

    def test_mismatched_window_start(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(window_start="2026-02-25T09:55:00Z"),
            a3_sigma_rate=_make_a3(),
        )
        errors = _validate_window_alignment(inputs)
        assert len(errors) >= 1
        assert "window_start" in errors[0]

    def test_mismatched_window_kind(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(window_kind="rolling_10m"),
        )
        errors = _validate_window_alignment(inputs)
        assert len(errors) >= 1
        assert "window_kind" in errors[0]

    def test_single_input_no_validation_needed(self):
        inputs = DiagnosticInputs(a2_silent_suppression=_make_a2())
        assert _validate_window_alignment(inputs) == []

    def test_window_mismatch_produces_invalid_envelope(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(window_start="2026-02-25T09:55:00Z"),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.INVALID.value
        assert env.values["classification"] == CLASSIFICATION_INDETERMINATE
        assert env.value is None
        assert any("window_mismatch" in r for r in env.quality_reasons)


# ═══════════════════════════════════════════════════════════════════════════
# Suppression precedence
# ═══════════════════════════════════════════════════════════════════════════

class TestSuppressionPrecedence:
    """A2 state gates everything else."""

    def test_a2_suppressed_yields_instrumentation_compromised(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(value=0.0, classification="likely_suppressed"),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_INSTRUMENTATION_COMPROMISED
        assert env.value is None
        assert env.quality_status == QualityStatus.OK.value

    def test_a2_idle_yields_insufficient_history(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(
                value=None, quality_status="unavailable", classification="idle",
            ),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_INSUFFICIENT_HISTORY
        assert env.value is None

    def test_a2_indeterminate_yields_insufficient_history(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(
                value=None, quality_status="unavailable",
                classification="indeterminate",
            ),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_INSUFFICIENT_HISTORY

    def test_a2_missing_entirely(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        assert any("missing_suppression_signal" in r for r in env.quality_reasons)
        assert env.value is None

    def test_suppression_overrides_even_with_high_sigma(self):
        """Even if A3 shows high sigma, suppression takes precedence."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(value=0.0, classification="likely_suppressed"),
            a3_sigma_rate=_make_a3(value=0.9, sigma_events=10),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_INSTRUMENTATION_COMPROMISED
        assert env.value is None


# ═══════════════════════════════════════════════════════════════════════════
# Capture scoring
# ═══════════════════════════════════════════════════════════════════════════

class TestCaptureScoring:
    """Score computation from A1 and A3 extracts."""

    def test_zero_sigma_zero_coverage_issue_yields_zero(self):
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 1.0,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": 0.0, "quality_status": "ok", "sigma_events": 0,
               "invalid_pairs_count": 0, "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        score, sigma_comp, cov_comp, _ = _compute_capture_score(a1, a3)
        assert score == pytest.approx(0.0)
        assert sigma_comp == pytest.approx(0.0)
        assert cov_comp == pytest.approx(0.0)

    def test_high_sigma_rate_yields_high_score(self):
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 1.0,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": SIGMA_RATE_CEILING, "quality_status": "ok",
               "sigma_events": 5, "invalid_pairs_count": 0,
               "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        score, sigma_comp, _, _ = _compute_capture_score(a1, a3)
        assert score is not None
        # At ceiling, sigma_score = 1.0 * SIGMA_WEIGHT / total_weight
        assert score > WARNING_THRESHOLD

    def test_low_coverage_contributes_to_score(self):
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 0.1,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": 0.0, "quality_status": "ok", "sigma_events": 0,
               "invalid_pairs_count": 0, "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        score, _, cov_comp, _ = _compute_capture_score(a1, a3)
        assert score is not None
        assert score > 0.0
        assert cov_comp > 0.0

    def test_full_coverage_no_contribution(self):
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 1.0,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": 0.0, "quality_status": "ok", "sigma_events": 0,
               "invalid_pairs_count": 0, "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        _, _, cov_comp, _ = _compute_capture_score(a1, a3)
        assert cov_comp == 0.0

    def test_invalid_pairs_add_penalty(self):
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 1.0,
               "completeness": 1.0, "content_hash": "h1"}
        a3_no_invalid = {"value": 0.1, "quality_status": "ok", "sigma_events": 1,
                          "invalid_pairs_count": 0, "denominator_type": "exposure_proxy",
                          "completeness": 1.0, "content_hash": "h3"}
        a3_with_invalid = {**a3_no_invalid, "invalid_pairs_count": 2}

        score_clean, _, _, _ = _compute_capture_score(a1, a3_no_invalid)
        score_dirty, _, _, _ = _compute_capture_score(a1, a3_with_invalid)
        assert score_dirty > score_clean

    def test_both_unavailable_yields_none(self):
        a1 = {"value": None, "quality_status": "unavailable", "coverage_ratio": 0.0,
               "completeness": None, "content_hash": "h1"}
        a3 = {"value": None, "quality_status": "unavailable", "sigma_events": 0,
               "invalid_pairs_count": 0, "denominator_type": "none",
               "completeness": None, "content_hash": "h3"}
        score, _, _, _ = _compute_capture_score(a1, a3)
        assert score is None

    def test_a3_only_scoring(self):
        """A1 absent, only A3 contributes."""
        a1 = {"value": None, "quality_status": "unavailable", "coverage_ratio": 0.0,
               "completeness": None, "content_hash": None}
        a3 = {"value": 0.25, "quality_status": "ok", "sigma_events": 2,
               "invalid_pairs_count": 0, "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        score, sigma_comp, cov_comp, _ = _compute_capture_score(a1, a3)
        assert score is not None
        assert score > 0.0
        assert cov_comp == 0.0  # A1 not scorable

    def test_a1_only_scoring(self):
        """A3 absent, only A1 contributes (via coverage)."""
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 0.1,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": None, "quality_status": "unavailable", "sigma_events": 0,
               "invalid_pairs_count": 0, "denominator_type": "none",
               "completeness": None, "content_hash": None}
        score, sigma_comp, cov_comp, _ = _compute_capture_score(a1, a3)
        assert score is not None
        assert score > 0.0
        assert sigma_comp == 0.0  # A3 not scorable

    def test_score_clamped_to_one(self):
        """Even extreme inputs don't exceed 1.0."""
        a1 = {"value": 10.0, "quality_status": "ok", "coverage_ratio": 0.0,
               "completeness": 1.0, "content_hash": "h1"}
        a3 = {"value": 10.0, "quality_status": "ok", "sigma_events": 100,
               "invalid_pairs_count": 50, "denominator_type": "exposure_proxy",
               "completeness": 1.0, "content_hash": "h3"}
        score, _, _, _ = _compute_capture_score(a1, a3)
        assert score is not None
        assert score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Classification from score
# ═══════════════════════════════════════════════════════════════════════════

class TestClassification:
    """Score → classification mapping."""

    def test_none_yields_insufficient(self):
        assert _classify_from_score(None) == CLASSIFICATION_INSUFFICIENT_HISTORY

    def test_zero_yields_normal(self):
        assert _classify_from_score(0.0) == CLASSIFICATION_NORMAL

    def test_below_watch_yields_normal(self):
        assert _classify_from_score(WATCH_THRESHOLD - 0.01) == CLASSIFICATION_NORMAL

    def test_at_watch_yields_watch(self):
        assert _classify_from_score(WATCH_THRESHOLD) == CLASSIFICATION_WATCH

    def test_between_watch_and_warning_yields_watch(self):
        mid = (WATCH_THRESHOLD + WARNING_THRESHOLD) / 2
        assert _classify_from_score(mid) == CLASSIFICATION_WATCH

    def test_at_warning_yields_warning(self):
        assert _classify_from_score(WARNING_THRESHOLD) == CLASSIFICATION_WARNING

    def test_above_warning_yields_warning(self):
        assert _classify_from_score(0.99) == CLASSIFICATION_WARNING


# ═══════════════════════════════════════════════════════════════════════════
# Full derivation — happy paths
# ═══════════════════════════════════════════════════════════════════════════

class TestDerivationNormal:
    """All inputs present and healthy — normal path."""

    def test_all_clean_yields_normal(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=0.0, sigma_events=0),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert env.signal_version == 1
        assert env.phase == "2.4B"
        assert env.values["classification"] == CLASSIFICATION_NORMAL
        assert env.value is not None
        assert env.value < WATCH_THRESHOLD
        assert env.quality_status == QualityStatus.OK.value
        assert env.derivation == DerivationType.DERIVED.value
        assert env.derivation_version == DIAG_CONFIG_VERSION
        assert env.unit == "score"

    def test_moderate_sigma_yields_watch(self):
        # sigma_rate between watch and warning thresholds
        # sigma_rate = WATCH_THRESHOLD * SIGMA_RATE_CEILING * (SIGMA_WEIGHT + COVERAGE_WEIGHT) / SIGMA_WEIGHT
        # but simpler to just pick a value empirically
        sigma_val = 0.1  # should produce score ~0.14 (watch territory)
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=sigma_val, sigma_events=1),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] in (CLASSIFICATION_WATCH, CLASSIFICATION_NORMAL)
        assert env.value is not None

    def test_high_sigma_yields_warning(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=SIGMA_RATE_CEILING, sigma_events=5),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_WARNING
        assert env.value is not None
        assert env.value >= WARNING_THRESHOLD


# ═══════════════════════════════════════════════════════════════════════════
# Full derivation — degraded paths
# ═══════════════════════════════════════════════════════════════════════════

class TestDerivationDegraded:
    """Missing or partial inputs."""

    def test_a1_missing_yields_partial_quality(self):
        inputs = DiagnosticInputs(
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=0.0),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert any("EXPOSURE_PROXY" in r for r in env.quality_reasons)
        assert env.value is not None  # still computable from A3

    def test_a3_missing_yields_partial_quality(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(coverage_ratio=0.2),
            a2_silent_suppression=_make_a2(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert any("SIGMA_RATE" in r for r in env.quality_reasons)
        # Still computable from A1 coverage (if coverage is low)
        assert env.value is not None

    def test_a1_and_a3_missing_yields_insufficient(self):
        inputs = DiagnosticInputs(
            a2_silent_suppression=_make_a2(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        assert env.values["classification"] == CLASSIFICATION_INSUFFICIENT_HISTORY
        assert env.value is None

    def test_a3_partial_quality_inherits(self):
        """When A3 is partial, B1 becomes partial too."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(quality_status="partial", completeness=0.8),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert env.completeness == pytest.approx(0.8)

    def test_a3_invalid_not_scorable(self):
        """A3 with quality=invalid should not contribute to scoring."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(coverage_ratio=0.2),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=None, quality_status="invalid"),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        # Should still be computable from A1 alone
        assert env.value is not None
        # A3 invalid means sigma didn't contribute
        assert env.values["sigma_score_component"] == pytest.approx(0.0)

    def test_all_inputs_invalid_yields_indeterminate(self):
        """When both A1 and A3 are invalid and A2 is ok but no scorable data."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(value=None, quality_status="invalid", coverage_ratio=0.0),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=None, quality_status="invalid"),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["classification"] == CLASSIFICATION_INDETERMINATE
        assert env.value is None


# ═══════════════════════════════════════════════════════════════════════════
# Envelope shape and validation
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvelopeShape:
    """Output envelope has all required fields."""

    @pytest.fixture()
    def normal_env(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        return derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT, emitter_version="test",
        )

    def test_signal_identity(self, normal_env):
        assert normal_env.signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert normal_env.signal_version == 1
        assert normal_env.phase == "2.4B"

    def test_subject_type(self, normal_env):
        assert normal_env.subject_type == "window"
        assert normal_env.subject_id.startswith("diag_")

    def test_unit(self, normal_env):
        assert normal_env.unit == "score"

    def test_derivation(self, normal_env):
        assert normal_env.derivation == DerivationType.DERIVED.value
        assert normal_env.derivation_version == DIAG_CONFIG_VERSION

    def test_window_fields(self, normal_env):
        assert normal_env.window_start == WINDOW_START
        assert normal_env.window_end == WINDOW_END
        assert normal_env.window_kind == WINDOW_KIND

    def test_values_dict_keys(self, normal_env):
        required_keys = {
            "capture_decline_score", "classification",
            "sigma_rate_input", "sigma_rate_quality", "sigma_score_component",
            "invalid_pairs_count",
            "exposure_proxy_input", "exposure_proxy_quality",
            "coverage_ratio", "coverage_score_component",
            "suppression_input", "suppression_classification",
            "input_signal_count", "config_version",
        }
        assert required_keys.issubset(set(normal_env.values.keys()))

    def test_annotations_dict_keys(self, normal_env):
        required_keys = {
            "config_version", "a1_content_hash", "a2_content_hash", "a3_content_hash",
        }
        assert required_keys.issubset(set(normal_env.annotations.keys()))

    def test_source_streams_populated(self, normal_env):
        assert "EXPOSURE_PROXY" in normal_env.source_streams
        assert "SILENT_SUPPRESSION" in normal_env.source_streams
        assert "SIGMA_RATE" in normal_env.source_streams

    def test_source_streams_only_present_inputs(self):
        """Source streams should only list inputs that were provided."""
        inputs = DiagnosticInputs(
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert "EXPOSURE_PROXY" not in env.source_streams
        assert "SILENT_SUPPRESSION" in env.source_streams
        assert "SIGMA_RATE" in env.source_streams

    def test_validates_cleanly(self, normal_env):
        errors = validate_envelope(normal_env)
        assert errors == []

    def test_content_hash_stable(self, normal_env):
        """Same inputs → same content hash."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env2 = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT, emitter_version="test",
        )
        assert normal_env.content_hash() == env2.content_hash()


# ═══════════════════════════════════════════════════════════════════════════
# Round-trip serialization
# ═══════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """to_dict / from_dict / to_json round-trip."""

    def test_round_trip(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        d = env.to_dict()
        env2 = SignalEnvelope.from_dict(d)
        assert env2.signal_id == env.signal_id
        assert env2.value == env.value
        assert env2.values == env.values
        assert env2.annotations == env.annotations

    def test_json_round_trip(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        j = env.to_json()
        env2 = SignalEnvelope.from_json(j)
        assert env2.signal_id == env.signal_id
        assert env2.values["classification"] == env.values["classification"]


# ═══════════════════════════════════════════════════════════════════════════
# Observe-only invariant
# ═══════════════════════════════════════════════════════════════════════════

class TestObserveOnly:
    """B1 must not block, alter policy, or mutate anything."""

    def test_module_has_no_blocking_imports(self):
        """Verify the module doesn't import gating/policy infrastructure."""
        import governor.signals.capture_self_diagnostic as mod
        source = pathlib.Path(mod.__file__).read_text()
        # These imports would indicate policy/gating integration
        for forbidden in [
            "from ..evidence_gate",
            "from ..wrapper",
            "from ..hooks",
            "from ..daemon",
            "from ..violation_resolver",
        ]:
            assert forbidden not in source, f"Found forbidden import: {forbidden}"

    def test_no_receipt_store_access(self):
        """B1 must not access receipt stores directly."""
        import governor.signals.capture_self_diagnostic as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "ReceiptStore" not in source
        assert "receipt_store" not in source

    def test_derive_is_pure(self):
        """Derivation function takes envelopes in, returns envelope out, no side effects."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env1 = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        env2 = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        # Same inputs → same outputs (deterministic, no hidden state)
        assert env1.to_dict() == env2.to_dict()


# ═══════════════════════════════════════════════════════════════════════════
# Missing ≠ zero invariant
# ═══════════════════════════════════════════════════════════════════════════

class TestMissingNotZero:
    """Value=None + unavailable is distinct from value=0.0 + ok."""

    def test_no_inputs_yields_none_not_zero(self):
        inputs = DiagnosticInputs(
            a2_silent_suppression=_make_a2(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.value is None
        assert env.quality_status != QualityStatus.OK.value

    def test_clean_zero_sigma_is_zero_not_none(self):
        """Zero sigma rate = healthy (value near 0.0), not missing."""
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(value=0.0, sigma_events=0),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.value is not None
        assert env.value == pytest.approx(0.0)
        assert env.quality_status == QualityStatus.OK.value


# ═══════════════════════════════════════════════════════════════════════════
# Completeness inheritance
# ═══════════════════════════════════════════════════════════════════════════

class TestCompletenessInheritance:
    """B1 completeness = min of input completeness values."""

    def test_all_complete(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(completeness=1.0),
            a2_silent_suppression=_make_a2(completeness=1.0),
            a3_sigma_rate=_make_a3(completeness=1.0),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.completeness == pytest.approx(1.0)

    def test_a3_partial_sets_minimum(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(completeness=1.0),
            a2_silent_suppression=_make_a2(completeness=1.0),
            a3_sigma_rate=_make_a3(completeness=0.6, quality_status="partial"),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.completeness == pytest.approx(0.6)

    def test_a1_partial_sets_minimum(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(completeness=0.5, quality_status="partial",
                                        coverage_ratio=0.5),
            a2_silent_suppression=_make_a2(completeness=1.0),
            a3_sigma_rate=_make_a3(completeness=0.8, quality_status="partial"),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.completeness == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════════════
# Config version provenance
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigVersion:
    """Config version is embedded in output for provenance."""

    def test_values_has_config_version(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.values["config_version"] == DIAG_CONFIG_VERSION

    def test_annotations_has_config_version(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.annotations["config_version"] == DIAG_CONFIG_VERSION

    def test_derivation_version_matches_config(self):
        inputs = DiagnosticInputs(
            a1_exposure_proxy=_make_a1(),
            a2_silent_suppression=_make_a2(),
            a3_sigma_rate=_make_a3(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.derivation_version == DIAG_CONFIG_VERSION


# ═══════════════════════════════════════════════════════════════════════════
# Content hash provenance in annotations
# ═══════════════════════════════════════════════════════════════════════════

class TestInputHashProvenance:
    """Annotations contain content hashes of input envelopes."""

    def test_all_three_hashes_present(self):
        a1 = _make_a1()
        a2 = _make_a2()
        a3 = _make_a3()
        inputs = DiagnosticInputs(
            a1_exposure_proxy=a1,
            a2_silent_suppression=a2,
            a3_sigma_rate=a3,
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.annotations["a1_content_hash"] == a1.content_hash()
        assert env.annotations["a2_content_hash"] == a2.content_hash()
        assert env.annotations["a3_content_hash"] == a3.content_hash()

    def test_missing_inputs_have_null_hash(self):
        inputs = DiagnosticInputs(
            a2_silent_suppression=_make_a2(),
        )
        env = derive_capture_self_diagnostic(
            inputs, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitted_at=EMITTED_AT,
        )
        assert env.annotations["a1_content_hash"] is None
        assert env.annotations["a2_content_hash"] is not None
        assert env.annotations["a3_content_hash"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Golden fixtures
# ═══════════════════════════════════════════════════════════════════════════

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "signals"


class TestGoldenFixtures:
    """Golden fixture regression tests."""

    def _load_fixture(self, name: str) -> dict:
        path = FIXTURE_DIR / name
        return json.loads(path.read_text())

    def test_golden_normal(self):
        data = self._load_fixture("envelope_normal_capture_diag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert env.values["classification"] == CLASSIFICATION_NORMAL
        assert env.value is not None
        assert env.value < WATCH_THRESHOLD
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_warning(self):
        data = self._load_fixture("envelope_warning_capture_diag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.values["classification"] == CLASSIFICATION_WARNING
        assert env.value is not None
        assert env.value >= WARNING_THRESHOLD
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_compromised(self):
        data = self._load_fixture("envelope_compromised_capture_diag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.values["classification"] == CLASSIFICATION_INSTRUMENTATION_COMPROMISED
        assert env.value is None
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_insufficient(self):
        data = self._load_fixture("envelope_insufficient_capture_diag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.values["classification"] == CLASSIFICATION_INSUFFICIENT_HISTORY
        assert env.value is None
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_partial(self):
        data = self._load_fixture("envelope_partial_capture_diag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.values["classification"] in (
            CLASSIFICATION_NORMAL, CLASSIFICATION_WATCH, CLASSIFICATION_WARNING,
        )
        assert env.quality_status == QualityStatus.PARTIAL.value
        errors = validate_envelope(env)
        assert errors == []

    def test_all_fixtures_have_required_values_keys(self):
        required_keys = {
            "capture_decline_score", "classification",
            "sigma_rate_input", "sigma_rate_quality", "sigma_score_component",
            "invalid_pairs_count",
            "exposure_proxy_input", "exposure_proxy_quality",
            "coverage_ratio", "coverage_score_component",
            "suppression_input", "suppression_classification",
            "input_signal_count", "config_version",
        }
        for name in (
            "envelope_normal_capture_diag.json",
            "envelope_warning_capture_diag.json",
            "envelope_compromised_capture_diag.json",
            "envelope_insufficient_capture_diag.json",
            "envelope_partial_capture_diag.json",
        ):
            data = self._load_fixture(name)
            assert required_keys.issubset(set(data["values"].keys())), f"Missing keys in {name}"
