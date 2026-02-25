# SPDX-License-Identifier: Apache-2.0
"""Tests for Phase D: PREDICT_REGIME_PREFLIGHT."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.signals.predict_regime import (
    ALL_EXPECTED_SIGNALS,
    ALL_REGIMES,
    DEFAULT_CONFIG,
    OPTIONAL_SIGNALS,
    PREFLIGHT_CONFIG_VERSION,
    REQUIRED_SIGNALS,
    USABLE_QUALITIES,
    PreflightConfig,
    PreflightInputSet,
    PreflightRegime,
    extract_preflight_inputs,
    predict_regime_preflight,
)
from governor.signals.envelope import SignalEnvelope, validate_envelope

# ── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "signals"
GOLDEN_DIR = FIXTURES

# ── Helpers ──────────────────────────────────────────────────────────────────

TS = "2026-02-25T13:00:00Z"


def _make_calibrated(
    *,
    signal_id: str,
    value: float | None = 0.2,
    quality_status: str = "ok",
    emitted_at: str = "2026-02-25T12:05:00Z",
    annotations: dict | None = None,
) -> SignalEnvelope:
    """Build a minimal calibrated envelope for testing."""
    return SignalEnvelope(
        schema_version="0.4.0",
        emitted_at=emitted_at,
        emitter="governor.signals.calibration_layer",
        emitter_version="2.4.0-dev",
        signal_id=signal_id,
        signal_version=1,
        phase="2.4C",
        subject_type="window",
        subject_id="test_window",
        window_start="2026-02-25T11:55:00Z",
        window_end="2026-02-25T12:00:00Z",
        window_kind="rolling_5m",
        value=value,
        unit="normalized",
        values={
            "normalized_value": value,
            "raw_value": value,
            "calibration_method": "identity_clip",
        },
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=10,
        completeness=1.0,
        derivation="derived",
        derivation_version="calibration-layer-v1",
        annotations=annotations or {},
    )


def _make_full_input_set(
    *,
    exposure: float = 0.2,
    sigma: float = 0.1,
    capture: float = 0.15,
    lag: float = 0.05,
    suppression: float = 0.9,  # 0.9 = healthy
    **overrides: float | None,
) -> list[SignalEnvelope]:
    """Build a complete set of calibrated inputs."""
    envs = [
        _make_calibrated(signal_id="EXPOSURE_PROXY", value=exposure),
        _make_calibrated(signal_id="SIGMA_RATE", value=sigma),
        _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC", value=capture),
        _make_calibrated(signal_id="DECISION_EVIDENCE_LAG", value=lag),
        _make_calibrated(signal_id="SILENT_SUPPRESSION", value=suppression),
    ]
    return envs


# ════════════════════════════════════════════════════════════════════════════
# TestPreflightRegimeEnum
# ════════════════════════════════════════════════════════════════════════════


class TestPreflightRegimeEnum:
    def test_all_values(self):
        assert len(PreflightRegime) == 6

    def test_string_enum(self):
        assert PreflightRegime.NORMAL.value == "normal"
        assert PreflightRegime.WARNING.value == "warning"

    def test_all_regimes_frozenset(self):
        assert ALL_REGIMES == frozenset({
            "normal", "watch", "warning",
            "instrumentation_compromised",
            "insufficient_history", "indeterminate",
        })


# ════════════════════════════════════════════════════════════════════════════
# TestSignalSets
# ════════════════════════════════════════════════════════════════════════════


class TestSignalSets:
    def test_required_signals(self):
        assert REQUIRED_SIGNALS == frozenset({
            "EXPOSURE_PROXY", "SIGMA_RATE", "CAPTURE_SELF_DIAGNOSTIC",
        })

    def test_optional_signals(self):
        assert OPTIONAL_SIGNALS == frozenset({
            "DECISION_EVIDENCE_LAG", "SILENT_SUPPRESSION",
        })

    def test_all_expected(self):
        assert ALL_EXPECTED_SIGNALS == REQUIRED_SIGNALS | OPTIONAL_SIGNALS


# ════════════════════════════════════════════════════════════════════════════
# TestPreflightConfig
# ════════════════════════════════════════════════════════════════════════════


class TestPreflightConfig:
    def test_frozen(self):
        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.threshold_normal = 0.5  # type: ignore[misc]

    def test_default_weights_sum(self):
        cfg = DEFAULT_CONFIG
        total = (
            cfg.weight_capture_diagnostic
            + cfg.weight_sigma_rate
            + cfg.weight_decision_lag
            + cfg.weight_exposure_proxy
        )
        assert total == pytest.approx(1.0)

    def test_thresholds_ordered(self):
        assert DEFAULT_CONFIG.threshold_normal < DEFAULT_CONFIG.threshold_watch


# ════════════════════════════════════════════════════════════════════════════
# TestExtractPreflightInputs
# ════════════════════════════════════════════════════════════════════════════


class TestExtractPreflightInputs:
    def test_full_set_all_present(self):
        envs = _make_full_input_set()
        result = extract_preflight_inputs(envs)
        assert result.input_count_expected == 5
        assert result.input_count_present == 5
        assert result.input_count_usable == 5
        assert result.alignment_ok is True

    def test_missing_required(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = extract_preflight_inputs(envs)
        assert result.alignment_ok is False
        assert "SIGMA_RATE" in result.missing_required
        assert "CAPTURE_SELF_DIAGNOSTIC" in result.missing_required

    def test_missing_optional_still_aligned(self):
        envs = [
            _make_calibrated(signal_id="EXPOSURE_PROXY"),
            _make_calibrated(signal_id="SIGMA_RATE"),
            _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC"),
        ]
        result = extract_preflight_inputs(envs)
        assert result.alignment_ok is True
        assert result.missing_optional == frozenset({
            "DECISION_EVIDENCE_LAG", "SILENT_SUPPRESSION",
        })

    def test_none_value_not_usable(self):
        envs = [_make_calibrated(signal_id="SIGMA_RATE", value=None)]
        result = extract_preflight_inputs(envs)
        inp = result.inputs["SIGMA_RATE"]
        assert inp.is_usable is False
        assert inp.calibrated_value is None

    def test_unavailable_quality_not_usable(self):
        envs = [_make_calibrated(
            signal_id="SIGMA_RATE", value=0.1, quality_status="unavailable",
        )]
        result = extract_preflight_inputs(envs)
        inp = result.inputs["SIGMA_RATE"]
        assert inp.is_usable is False

    def test_partial_quality_is_usable(self):
        envs = [_make_calibrated(
            signal_id="SIGMA_RATE", value=0.1, quality_status="partial",
        )]
        result = extract_preflight_inputs(envs)
        assert result.inputs["SIGMA_RATE"].is_usable is True

    def test_most_recent_wins(self):
        envs = [
            _make_calibrated(
                signal_id="SIGMA_RATE", value=0.1,
                emitted_at="2026-02-25T12:00:00Z",
            ),
            _make_calibrated(
                signal_id="SIGMA_RATE", value=0.9,
                emitted_at="2026-02-25T12:05:00Z",
            ),
        ]
        result = extract_preflight_inputs(envs)
        assert result.inputs["SIGMA_RATE"].calibrated_value == pytest.approx(0.9)
        assert result.input_count_present == 1  # deduplicated

    def test_source_hash_populated(self):
        envs = [_make_calibrated(signal_id="SIGMA_RATE")]
        result = extract_preflight_inputs(envs)
        assert result.inputs["SIGMA_RATE"].source_hash.startswith("sha256:")

    def test_unknown_signal_ignored(self):
        envs = [
            _make_calibrated(signal_id="UNKNOWN_SIGNAL"),
            _make_calibrated(signal_id="SIGMA_RATE"),
        ]
        result = extract_preflight_inputs(envs)
        assert "UNKNOWN_SIGNAL" not in result.inputs

    def test_empty_input(self):
        result = extract_preflight_inputs([])
        assert result.input_count_present == 0
        assert result.input_count_usable == 0
        assert result.alignment_ok is False
        assert result.missing_required == REQUIRED_SIGNALS


# ════════════════════════════════════════════════════════════════════════════
# TestSuppressionPrecedence
# ════════════════════════════════════════════════════════════════════════════


class TestSuppressionPrecedence:
    def test_low_suppression_triggers_compromised(self):
        """Low SILENT_SUPPRESSION value = unhealthy → compromised."""
        envs = _make_full_input_set(suppression=0.1)  # 0.1 = very suppressed
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "instrumentation_compromised"
        assert result.annotations["suppression_precedence_applied"] is True

    def test_healthy_suppression_no_override(self):
        envs = _make_full_input_set(suppression=0.9)  # healthy
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] != "instrumentation_compromised"
        assert result.annotations["suppression_precedence_applied"] is False

    def test_high_capture_diagnostic_triggers_compromised(self):
        """High CAPTURE_SELF_DIAGNOSTIC → compromised via suppression check."""
        envs = _make_full_input_set(capture=0.8, suppression=0.9)
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "instrumentation_compromised"

    def test_suppression_overrides_low_risk(self):
        """Even if all other signals are normal, suppression wins."""
        envs = _make_full_input_set(
            exposure=0.01, sigma=0.01, capture=0.01, lag=0.01,
            suppression=0.1,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "instrumentation_compromised"

    def test_suppression_confidence_capped(self):
        envs = _make_full_input_set(suppression=0.1)
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["confidence"] <= DEFAULT_CONFIG.confidence_cap_suppressed


# ════════════════════════════════════════════════════════════════════════════
# TestInsufficientHistory
# ════════════════════════════════════════════════════════════════════════════


class TestInsufficientHistory:
    def test_missing_required_signals(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "insufficient_history"

    def test_empty_input(self):
        result = predict_regime_preflight([], emitted_at=TS)
        assert result.values["predicted_regime"] == "insufficient_history"

    def test_quality_status_unavailable(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.quality_status == "unavailable"

    def test_confidence_capped(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["confidence"] <= DEFAULT_CONFIG.confidence_cap_missing_required

    def test_reason_codes_include_missing(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        reasons = result.values["reason_codes"]
        assert "missing_required_signals" in reasons


# ════════════════════════════════════════════════════════════════════════════
# TestIndeterminate
# ════════════════════════════════════════════════════════════════════════════


class TestIndeterminate:
    def test_all_present_but_none_usable(self):
        """All required present but with bad quality → indeterminate."""
        envs = [
            _make_calibrated(
                signal_id="EXPOSURE_PROXY", value=0.1,
                quality_status="invalid",
            ),
            _make_calibrated(
                signal_id="SIGMA_RATE", value=0.1,
                quality_status="invalid",
            ),
            _make_calibrated(
                signal_id="CAPTURE_SELF_DIAGNOSTIC", value=0.1,
                quality_status="invalid",
            ),
        ]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "indeterminate"
        assert "no_usable_inputs" in result.values["reason_codes"]


# ════════════════════════════════════════════════════════════════════════════
# TestRiskScoreBands
# ════════════════════════════════════════════════════════════════════════════


class TestRiskScoreBands:
    def test_low_risk_normal(self):
        envs = _make_full_input_set(
            exposure=0.05, sigma=0.05, capture=0.05, lag=0.05,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "normal"

    def test_medium_risk_watch(self):
        envs = _make_full_input_set(
            exposure=0.4, sigma=0.4, capture=0.4, lag=0.4,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "watch"

    def test_high_risk_warning(self):
        # Keep capture below suppression_threshold (0.5) to avoid
        # suppression precedence; drive warning via sigma/lag/exposure.
        envs = _make_full_input_set(
            exposure=0.9, sigma=0.9, capture=0.49, lag=0.9,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] == "warning"

    def test_risk_score_in_values(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert "risk_score" in result.values
        assert 0.0 <= result.values["risk_score"] <= 1.0

    def test_boundary_normal_watch(self):
        """Risk score exactly at threshold → watch (not normal)."""
        # With all features at 0.3, weighted sum = 0.3 → exactly at boundary
        envs = _make_full_input_set(
            exposure=0.3, sigma=0.3, capture=0.3, lag=0.3,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        # 0.3 is not < 0.3, so it goes to watch
        assert result.values["predicted_regime"] == "watch"

    def test_boundary_watch_warning(self):
        # Use custom config so we can test the boundary behavior
        # without pushing capture above suppression_threshold.
        cfg = PreflightConfig(threshold_watch=0.45)
        envs = _make_full_input_set(
            exposure=0.45, sigma=0.45, capture=0.45, lag=0.45,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, config=cfg, emitted_at=TS)
        # risk_score = 0.45, not < threshold_watch (0.45) → warning
        assert result.values["predicted_regime"] == "warning"

    def test_feature_values_in_output(self):
        envs = _make_full_input_set(sigma=0.42)
        result = predict_regime_preflight(envs, emitted_at=TS)
        fv = result.values["feature_values"]
        assert fv["SIGMA_RATE"] == pytest.approx(0.42)


# ════════════════════════════════════════════════════════════════════════════
# TestConfidence
# ════════════════════════════════════════════════════════════════════════════


class TestConfidence:
    def test_full_ok_inputs_high_confidence(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["confidence"] > 0.8

    def test_partial_inputs_lower_confidence(self):
        envs = [
            _make_calibrated(signal_id="EXPOSURE_PROXY", quality_status="partial"),
            _make_calibrated(signal_id="SIGMA_RATE", quality_status="partial"),
            _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC", quality_status="partial"),
        ]
        full_envs = _make_full_input_set()
        r_full = predict_regime_preflight(full_envs, emitted_at=TS)
        r_partial = predict_regime_preflight(envs, emitted_at=TS)
        assert r_partial.values["confidence"] < r_full.values["confidence"]

    def test_confidence_bounded(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert 0.0 <= result.values["confidence"] <= 1.0

    def test_empty_input_zero_confidence(self):
        result = predict_regime_preflight([], emitted_at=TS)
        assert result.values["confidence"] == 0.0

    def test_confidence_equals_top_level_value(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.value == result.values["confidence"]


# ════════════════════════════════════════════════════════════════════════════
# TestQualityPropagation
# ════════════════════════════════════════════════════════════════════════════


class TestQualityPropagation:
    def test_all_ok_inputs_ok_quality(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.quality_status == "ok"

    def test_partial_input_partial_quality(self):
        envs = [
            _make_calibrated(signal_id="EXPOSURE_PROXY", quality_status="partial"),
            _make_calibrated(signal_id="SIGMA_RATE"),
            _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC"),
        ]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.quality_status == "partial"

    def test_missing_required_unavailable_quality(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.quality_status == "unavailable"

    def test_quality_reasons_populated(self):
        envs = [_make_calibrated(signal_id="EXPOSURE_PROXY")]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert len(result.quality_reasons) > 0


# ════════════════════════════════════════════════════════════════════════════
# TestProvenanceClosure
# ════════════════════════════════════════════════════════════════════════════


class TestProvenanceClosure:
    def test_input_hashes_in_annotations(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        hashes = result.annotations["input_envelope_hashes"]
        for sig in ALL_EXPECTED_SIGNALS:
            assert sig in hashes
            assert hashes[sig].startswith("sha256:")

    def test_config_version_in_annotations(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.annotations["config_version"] == PREFLIGHT_CONFIG_VERSION

    def test_model_version_in_values(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["model_version"] == PREFLIGHT_CONFIG_VERSION

    def test_input_quality_statuses_in_values(self):
        envs = _make_full_input_set()
        result = predict_regime_preflight(envs, emitted_at=TS)
        iqs = result.values["input_quality_statuses"]
        assert "SIGMA_RATE" in iqs


# ════════════════════════════════════════════════════════════════════════════
# TestDeterminism
# ════════════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_same_inputs_same_output(self):
        envs = _make_full_input_set()
        r1 = predict_regime_preflight(envs, emitted_at=TS)
        r2 = predict_regime_preflight(envs, emitted_at=TS)
        assert r1.to_canonical_bytes() == r2.to_canonical_bytes()

    def test_different_emitted_at_only(self):
        envs = _make_full_input_set()
        r1 = predict_regime_preflight(envs, emitted_at="2026-02-25T12:00:00Z")
        r2 = predict_regime_preflight(envs, emitted_at="2026-02-25T12:01:00Z")
        assert r1.values == r2.values
        assert r1.emitted_at != r2.emitted_at

    def test_canonical_json_stable(self):
        envs = _make_full_input_set()
        r = predict_regime_preflight(envs, emitted_at=TS)
        assert r.to_canonical_bytes() == r.to_canonical_bytes()


# ════════════════════════════════════════════════════════════════════════════
# TestEnvelopeShape
# ════════════════════════════════════════════════════════════════════════════


class TestEnvelopeShape:
    @pytest.fixture()
    def prediction(self):
        return predict_regime_preflight(_make_full_input_set(), emitted_at=TS)

    def test_signal_id(self, prediction):
        assert prediction.signal_id == "PREDICT_REGIME_PREFLIGHT"

    def test_signal_version(self, prediction):
        assert prediction.signal_version == 1

    def test_phase(self, prediction):
        assert prediction.phase == "2.4D"

    def test_unit(self, prediction):
        assert prediction.unit == "score"

    def test_derivation(self, prediction):
        assert prediction.derivation == "derived"

    def test_derivation_version(self, prediction):
        assert prediction.derivation_version == PREFLIGHT_CONFIG_VERSION

    def test_subject_type(self, prediction):
        assert prediction.subject_type == "session"

    def test_passes_validation(self, prediction):
        errors = validate_envelope(prediction)
        assert errors == [], f"Validation errors: {errors}"

    def test_serializes_to_json(self, prediction):
        j = prediction.to_json()
        parsed = json.loads(j)
        assert parsed["phase"] == "2.4D"
        assert parsed["signal_id"] == "PREDICT_REGIME_PREFLIGHT"

    def test_values_has_required_keys(self, prediction):
        v = prediction.values
        for key in (
            "predicted_regime", "confidence", "risk_score",
            "input_count_expected", "input_count_present",
            "input_count_usable", "feature_values",
            "reason_codes", "model_version",
        ):
            assert key in v, f"Missing key: {key}"


# ════════════════════════════════════════════════════════════════════════════
# TestCustomConfig
# ════════════════════════════════════════════════════════════════════════════


class TestCustomConfig:
    def test_custom_thresholds(self):
        cfg = PreflightConfig(threshold_normal=0.1, threshold_watch=0.2)
        envs = _make_full_input_set(
            exposure=0.15, sigma=0.15, capture=0.15, lag=0.15,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, config=cfg, emitted_at=TS)
        # 0.15 >= 0.1 threshold_normal but < 0.2 → watch
        assert result.values["predicted_regime"] == "watch"

    def test_custom_weights(self):
        # All weight on sigma_rate
        cfg = PreflightConfig(
            weight_capture_diagnostic=0.0,
            weight_sigma_rate=1.0,
            weight_decision_lag=0.0,
            weight_exposure_proxy=0.0,
        )
        envs = _make_full_input_set(
            sigma=0.8, capture=0.01, lag=0.01, exposure=0.01,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, config=cfg, emitted_at=TS)
        assert result.values["risk_score"] == pytest.approx(0.8)


# ════════════════════════════════════════════════════════════════════════════
# TestMissingOptionalDegrades
# ════════════════════════════════════════════════════════════════════════════


class TestMissingOptionalDegrades:
    def test_missing_optional_still_predicts(self):
        envs = [
            _make_calibrated(signal_id="EXPOSURE_PROXY", value=0.1),
            _make_calibrated(signal_id="SIGMA_RATE", value=0.1),
            _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC", value=0.1),
        ]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert result.values["predicted_regime"] in ALL_REGIMES
        # Confidence should be lower than full set
        full_result = predict_regime_preflight(_make_full_input_set(), emitted_at=TS)
        assert result.values["confidence"] < full_result.values["confidence"]

    def test_reason_codes_include_degraded_optional(self):
        envs = [
            _make_calibrated(signal_id="EXPOSURE_PROXY"),
            _make_calibrated(signal_id="SIGMA_RATE"),
            _make_calibrated(signal_id="CAPTURE_SELF_DIAGNOSTIC"),
        ]
        result = predict_regime_preflight(envs, emitted_at=TS)
        assert "degraded_optional" in result.values["reason_codes"]


# ════════════════════════════════════════════════════════════════════════════
# TestGoldenFixtures
# ════════════════════════════════════════════════════════════════════════════


class TestGoldenFixtures:
    GOLDEN_NORMAL = GOLDEN_DIR / "predict_regime_normal.json"
    GOLDEN_WARNING = GOLDEN_DIR / "predict_regime_warning.json"
    GOLDEN_COMPROMISED = GOLDEN_DIR / "predict_regime_compromised.json"
    GOLDEN_INSUFFICIENT = GOLDEN_DIR / "predict_regime_insufficient.json"

    def _write_golden(self, path: Path, env: SignalEnvelope) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(env.to_json() + "\n")

    def test_golden_normal(self):
        envs = _make_full_input_set(
            exposure=0.05, sigma=0.05, capture=0.05, lag=0.05,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        self._write_golden(self.GOLDEN_NORMAL, result)
        golden = SignalEnvelope.from_json(self.GOLDEN_NORMAL.read_text())
        assert golden.values["predicted_regime"] == "normal"

    def test_golden_warning(self):
        # Keep capture below suppression_threshold to exercise normal scoring.
        envs = _make_full_input_set(
            exposure=0.9, sigma=0.9, capture=0.49, lag=0.9,
            suppression=0.95,
        )
        result = predict_regime_preflight(envs, emitted_at=TS)
        self._write_golden(self.GOLDEN_WARNING, result)
        golden = SignalEnvelope.from_json(self.GOLDEN_WARNING.read_text())
        assert golden.values["predicted_regime"] == "warning"

    def test_golden_compromised(self):
        envs = _make_full_input_set(suppression=0.1)
        result = predict_regime_preflight(envs, emitted_at=TS)
        self._write_golden(self.GOLDEN_COMPROMISED, result)
        golden = SignalEnvelope.from_json(self.GOLDEN_COMPROMISED.read_text())
        assert golden.values["predicted_regime"] == "instrumentation_compromised"

    def test_golden_insufficient(self):
        result = predict_regime_preflight([], emitted_at=TS)
        self._write_golden(self.GOLDEN_INSUFFICIENT, result)
        golden = SignalEnvelope.from_json(self.GOLDEN_INSUFFICIENT.read_text())
        assert golden.values["predicted_regime"] == "insufficient_history"

    def test_all_goldens_validate(self):
        for golden_path in [
            self.GOLDEN_NORMAL, self.GOLDEN_WARNING,
            self.GOLDEN_COMPROMISED, self.GOLDEN_INSUFFICIENT,
        ]:
            if golden_path.exists():
                env = SignalEnvelope.from_json(golden_path.read_text())
                errors = validate_envelope(env)
                assert errors == [], f"{golden_path.name}: {errors}"
