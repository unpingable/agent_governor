# SPDX-License-Identifier: Apache-2.0
"""Tests for Phase C2 CALIBRATION_FITTING — offline param-set fitting."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from governor.signals.calibration_fitting import (
    CALIBRATION_FIT_CONFIG_VERSION,
    DEFAULT_EXCLUDE_CLASSIFICATIONS,
    DEFAULT_INCLUDE_QUALITIES,
    REASON_BOOL_VALUE,
    REASON_CLASSIFICATION_EXCLUDED,
    REASON_DOMAIN_INVALID,
    REASON_MISSING_VALUE,
    REASON_NON_NUMERIC_VALUE,
    REASON_QUALITY_EXCLUDED,
    REASON_SIGNAL_VERSION_MISMATCH,
    REASON_TARGET_FIELD_MISSING,
    CalibrationFitSpec,
    FitResult,
    FitSample,
    FitSampleSelection,
    FitStats,
    extract_fit_samples,
    fit_param_set_from_corpus,
    fit_summary_envelope,
    validate_fit_spec,
)
from governor.signals.calibration_layer import (
    CalibrationParamSet,
    apply_calibration,
)
from governor.signals.calibration_methods import CalibrationMismatchError
from governor.signals.envelope import SignalEnvelope, validate_envelope

# ── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "signals"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_fixture(name: str) -> SignalEnvelope:
    return SignalEnvelope.from_json((FIXTURES / name).read_text())


def _make_corpus_envelope(
    *,
    signal_id: str = "SIGMA_RATE",
    signal_version: int = 1,
    value: float | None = 0.15,
    unit: str = "rate",
    quality_status: str = "ok",
    values: dict | None = None,
    window_start: str = "2026-02-25T12:00:00Z",
    window_end: str = "2026-02-25T12:05:00Z",
    subject_id: str = "win_01",
    annotations: dict | None = None,
) -> SignalEnvelope:
    return SignalEnvelope(
        schema_version="0.4.0",
        emitted_at="2026-02-25T12:05:00Z",
        emitter="governor.signals.test",
        emitter_version="2.4.0-dev",
        signal_id=signal_id,
        signal_version=signal_version,
        phase="2.4A",
        subject_type="window",
        subject_id=subject_id,
        window_start=window_start,
        window_end=window_end,
        window_kind="rolling_5m",
        value=value,
        unit=unit,
        values=values or {},
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=10,
        completeness=1.0,
        derivation="windowed_aggregate",
        derivation_version="test-v1",
        annotations=annotations or {},
    )


def _make_fit_spec(
    *,
    signal_id: str = "SIGMA_RATE",
    signal_version: int = 1,
    target_field: str = "value",
    method: str = "identity_clip",
    min_sample_count: int = 1,
    log_base: float | None = None,
    epsilon_shift: float | None = None,
    clip_min: float = 0.0,
    clip_max: float = 1.0,
    source_manifest_hash: str = "sha256:test_manifest",
    include_quality_statuses: frozenset[str] | None = None,
    exclude_classifications: frozenset[str] | None = None,
) -> CalibrationFitSpec:
    return CalibrationFitSpec(
        fit_id="fit_test_001",
        signal_id=signal_id,
        signal_version=signal_version,
        target_field=target_field,
        method=method,
        source_mode="signal_envelopes",
        source_manifest_hash=source_manifest_hash,
        min_sample_count=min_sample_count,
        clip_min=clip_min,
        clip_max=clip_max,
        log_base=log_base,
        epsilon_shift=epsilon_shift,
        created_at="2026-02-25T00:00:00Z",
        include_quality_statuses=(
            include_quality_statuses
            if include_quality_statuses is not None
            else DEFAULT_INCLUDE_QUALITIES
        ),
        exclude_classifications=(
            exclude_classifications
            if exclude_classifications is not None
            else DEFAULT_EXCLUDE_CLASSIFICATIONS
        ),
    )


def _make_corpus(values: list[float], **kwargs) -> list[SignalEnvelope]:
    """Build a corpus of envelopes with given top-level values."""
    return [
        _make_corpus_envelope(
            value=v,
            subject_id=f"win_{i:03d}",
            window_start=f"2026-02-25T{12 + i}:00:00Z",
            **kwargs,
        )
        for i, v in enumerate(values)
    ]


# ════════════════════════════════════════════════════════════════════════════
# TestCalibrationFitSpec
# ════════════════════════════════════════════════════════════════════════════


class TestCalibrationFitSpec:
    def test_frozen_dataclass(self):
        spec = _make_fit_spec()
        with pytest.raises(AttributeError):
            spec.fit_id = "changed"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        spec = _make_fit_spec()
        d = spec.to_dict()
        spec2 = CalibrationFitSpec.from_dict(d)
        assert spec2.fit_id == spec.fit_id
        assert spec2.signal_id == spec.signal_id
        assert spec2.method == spec.method

    def test_fit_spec_hash_deterministic(self):
        spec = _make_fit_spec()
        assert spec.fit_spec_hash() == spec.fit_spec_hash()

    def test_fit_spec_hash_changes_on_field_change(self):
        s1 = _make_fit_spec(method="identity_clip")
        s2 = _make_fit_spec(method="linear_minmax")
        assert s1.fit_spec_hash() != s2.fit_spec_hash()

    def test_hash_format(self):
        spec = _make_fit_spec()
        h = spec.fit_spec_hash()
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64

    def test_default_include_qualities(self):
        spec = _make_fit_spec()
        assert spec.include_quality_statuses == frozenset({"ok", "partial"})

    def test_default_exclude_classifications(self):
        spec = _make_fit_spec()
        assert "instrumentation_compromised" in spec.exclude_classifications
        assert "suppressed" in spec.exclude_classifications

    def test_frozenset_serialization(self):
        spec = _make_fit_spec()
        d = spec.to_dict()
        assert isinstance(d["include_quality_statuses"], list)
        assert d["include_quality_statuses"] == sorted(spec.include_quality_statuses)


# ════════════════════════════════════════════════════════════════════════════
# TestValidateFitSpec
# ════════════════════════════════════════════════════════════════════════════


class TestValidateFitSpec:
    def test_valid_identity_passes(self):
        validate_fit_spec(_make_fit_spec(method="identity_clip"))

    def test_valid_linear_passes(self):
        validate_fit_spec(_make_fit_spec(method="linear_minmax"))

    def test_valid_log_passes(self):
        validate_fit_spec(_make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        ))

    def test_unknown_method(self):
        with pytest.raises(CalibrationMismatchError, match="unknown method"):
            validate_fit_spec(_make_fit_spec(method="quadratic"))

    def test_empty_include_qualities(self):
        with pytest.raises(CalibrationMismatchError, match="include_quality"):
            validate_fit_spec(_make_fit_spec(include_quality_statuses=frozenset()))

    def test_min_sample_count_zero(self):
        with pytest.raises(CalibrationMismatchError, match="min_sample_count"):
            validate_fit_spec(_make_fit_spec(min_sample_count=0))

    def test_min_sample_count_negative(self):
        with pytest.raises(CalibrationMismatchError, match="min_sample_count"):
            validate_fit_spec(_make_fit_spec(min_sample_count=-1))

    def test_inverted_clip_bounds(self):
        with pytest.raises(CalibrationMismatchError, match="inverted clip"):
            validate_fit_spec(_make_fit_spec(clip_min=0.8, clip_max=0.2))

    def test_clip_outside_unit(self):
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            validate_fit_spec(_make_fit_spec(clip_min=-0.1, clip_max=1.0))

    def test_log_missing_log_base(self):
        with pytest.raises(CalibrationMismatchError, match="log_base"):
            validate_fit_spec(_make_fit_spec(
                method="log_minmax", epsilon_shift=1.0,
            ))

    def test_log_missing_epsilon_shift(self):
        with pytest.raises(CalibrationMismatchError, match="epsilon_shift"):
            validate_fit_spec(_make_fit_spec(
                method="log_minmax", log_base=math.e,
            ))

    def test_log_invalid_log_base(self):
        with pytest.raises(CalibrationMismatchError, match="log_base"):
            validate_fit_spec(_make_fit_spec(
                method="log_minmax", log_base=1, epsilon_shift=1.0,
            ))

    def test_log_epsilon_le_zero(self):
        with pytest.raises(CalibrationMismatchError, match="epsilon_shift"):
            validate_fit_spec(_make_fit_spec(
                method="log_minmax", log_base=math.e, epsilon_shift=0,
            ))


# ════════════════════════════════════════════════════════════════════════════
# TestExtractFitSamples
# ════════════════════════════════════════════════════════════════════════════


class TestExtractFitSamples:
    def test_basic_extraction(self):
        corpus = _make_corpus([0.1, 0.2, 0.3])
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        assert sel.sample_count_used == 3
        assert sel.used_values == pytest.approx((0.1, 0.2, 0.3))

    def test_target_field_value(self):
        corpus = _make_corpus([0.5])
        spec = _make_fit_spec(target_field="value")
        sel = extract_fit_samples(corpus, spec)
        assert sel.sample_count_used == 1

    def test_target_field_in_values_dict(self):
        env = _make_corpus_envelope(values={"backfill_rate": 0.3})
        spec = _make_fit_spec(
            signal_id="SIGMA_RATE", target_field="backfill_rate",
        )
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 1
        assert sel.used_values[0] == pytest.approx(0.3)

    def test_target_field_missing_excluded(self):
        env = _make_corpus_envelope(values={})
        spec = _make_fit_spec(target_field="nonexistent")
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_TARGET_FIELD_MISSING] == 1

    def test_non_numeric_excluded(self):
        env = _make_corpus_envelope(values={"status": "ok"})
        spec = _make_fit_spec(target_field="status")
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_NON_NUMERIC_VALUE] == 1

    def test_bool_excluded(self):
        env = _make_corpus_envelope(values={"flag": True})
        spec = _make_fit_spec(target_field="flag")
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_BOOL_VALUE] == 1

    def test_null_excluded(self):
        env = _make_corpus_envelope(value=None, quality_status="ok")
        spec = _make_fit_spec()
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_MISSING_VALUE] == 1

    def test_quality_filtering(self):
        corpus = [
            _make_corpus_envelope(value=0.1, quality_status="ok", subject_id="w1"),
            _make_corpus_envelope(value=0.2, quality_status="unavailable", subject_id="w2"),
            _make_corpus_envelope(value=0.3, quality_status="partial", subject_id="w3"),
        ]
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        assert sel.sample_count_used == 2  # ok + partial
        assert sel.exclusion_reason_counts[REASON_QUALITY_EXCLUDED] == 1

    def test_classification_filtering(self):
        env = _make_corpus_envelope(
            value=0.5,
            annotations={"classification": "instrumentation_compromised"},
        )
        spec = _make_fit_spec()
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_CLASSIFICATION_EXCLUDED] == 1

    def test_log_domain_invalid_excluded(self):
        env = _make_corpus_envelope(value=-5.0)
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_DOMAIN_INVALID] == 1

    def test_signal_version_mismatch(self):
        env = _make_corpus_envelope(signal_version=99)
        spec = _make_fit_spec(signal_version=1)
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.exclusion_reason_counts[REASON_SIGNAL_VERSION_MISMATCH] == 1

    def test_wrong_signal_id_not_counted(self):
        """Envelopes with different signal_id are not candidates at all."""
        env = _make_corpus_envelope(signal_id="EXPOSURE_PROXY")
        spec = _make_fit_spec(signal_id="SIGMA_RATE")
        sel = extract_fit_samples([env], spec)
        assert sel.sample_count_used == 0
        assert sel.sample_count_excluded == 0

    def test_deterministic_ordering(self):
        corpus = [
            _make_corpus_envelope(value=0.3, subject_id="w_c", window_start="2026-02-25T14:00:00Z"),
            _make_corpus_envelope(value=0.1, subject_id="w_a", window_start="2026-02-25T12:00:00Z"),
            _make_corpus_envelope(value=0.2, subject_id="w_b", window_start="2026-02-25T13:00:00Z"),
        ]
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        # Should be sorted by window_start
        assert sel.used_values == pytest.approx((0.1, 0.2, 0.3))

    def test_exact_exclusion_counts(self):
        corpus = [
            _make_corpus_envelope(value=0.1, subject_id="w1"),               # included
            _make_corpus_envelope(value=None, subject_id="w2"),              # missing
            _make_corpus_envelope(value=0.3, quality_status="invalid", subject_id="w3"),  # quality
        ]
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        assert sel.sample_count_used == 1
        assert sel.sample_count_excluded == 2
        assert sel.exclusion_reason_counts[REASON_MISSING_VALUE] == 1
        assert sel.exclusion_reason_counts[REASON_QUALITY_EXCLUDED] == 1

    def test_window_range_computed(self):
        corpus = _make_corpus([0.1, 0.2, 0.3])
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        assert sel.window_range is not None
        assert "/" in sel.window_range

    def test_zero_is_valid_sample(self):
        """Zero is a valid value, not None (missing≠zero)."""
        corpus = _make_corpus([0.0, 0.1, 0.2])
        spec = _make_fit_spec()
        sel = extract_fit_samples(corpus, spec)
        assert sel.sample_count_used == 3
        assert 0.0 in sel.used_values


# ════════════════════════════════════════════════════════════════════════════
# TestMethodFitting — identity_clip
# ════════════════════════════════════════════════════════════════════════════


class TestFitIdentityClip:
    def test_emits_spec_clip_bounds(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec(method="identity_clip", clip_min=0.0, clip_max=1.0)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.param_set.params["min"] == 0.0
        assert result.param_set.params["max"] == 1.0

    def test_custom_clip_bounds(self):
        corpus = _make_corpus([0.3, 0.5])
        spec = _make_fit_spec(method="identity_clip", clip_min=0.1, clip_max=0.9)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.params["min"] == 0.1
        assert result.param_set.params["max"] == 0.9


# ════════════════════════════════════════════════════════════════════════════
# TestMethodFitting — linear_minmax
# ════════════════════════════════════════════════════════════════════════════


class TestFitLinearMinmax:
    def test_normal_corpus(self):
        corpus = _make_corpus([2.0, 5.0, 8.0, 10.0])
        spec = _make_fit_spec(method="linear_minmax")
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.param_set.params["observed_min"] == 2.0
        assert result.param_set.params["observed_max"] == 10.0

    def test_degenerate_corpus_allowed(self):
        corpus = _make_corpus([5.0, 5.0, 5.0])
        spec = _make_fit_spec(method="linear_minmax")
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.param_set.params["observed_min"] == 5.0
        assert result.param_set.params["observed_max"] == 5.0
        assert result.summary_envelope.values["degenerate_fit"] is True

    def test_insufficient_samples_no_param_set(self):
        corpus = _make_corpus([5.0])
        spec = _make_fit_spec(method="linear_minmax", min_sample_count=5)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is None
        assert result.errors
        assert result.summary_envelope.quality_status == "unavailable"

    def test_clip_bounds_passed_through(self):
        corpus = _make_corpus([1.0, 10.0])
        spec = _make_fit_spec(method="linear_minmax", clip_min=0.1, clip_max=0.9)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.params["clip_min"] == 0.1
        assert result.param_set.params["clip_max"] == 0.9


# ════════════════════════════════════════════════════════════════════════════
# TestMethodFitting — log_minmax
# ════════════════════════════════════════════════════════════════════════════


class TestFitLogMinmax:
    def test_valid_positive_corpus(self):
        corpus = _make_corpus([1.0, 10.0, 50.0, 100.0])
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.param_set.params["observed_min"] == 1.0
        assert result.param_set.params["observed_max"] == 100.0
        assert result.param_set.params["epsilon_shift"] == 1.0
        assert result.param_set.params["log_base"] == math.e

    def test_domain_invalid_excluded(self):
        corpus = [
            _make_corpus_envelope(value=-5.0, subject_id="w1"),  # domain invalid
            _make_corpus_envelope(value=10.0, subject_id="w2"),  # valid
            _make_corpus_envelope(value=50.0, subject_id="w3"),  # valid
        ]
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.param_set.params["observed_min"] == 10.0
        assert result.summary_envelope.values["exclusion_reason_counts"].get(REASON_DOMAIN_INVALID) == 1

    def test_all_domain_invalid_no_param_set(self):
        corpus = _make_corpus([-10.0, -5.0, -3.0])
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is None
        assert result.summary_envelope.quality_status == "unavailable"

    def test_degenerate_corpus_flagged(self):
        corpus = _make_corpus([5.0, 5.0, 5.0])
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None
        assert result.summary_envelope.values["degenerate_fit"] is True

    def test_epsilon_shift_required(self):
        spec = _make_fit_spec(method="log_minmax", log_base=math.e)
        result = fit_param_set_from_corpus([], spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is None
        assert result.summary_envelope.quality_status == "invalid"


# ════════════════════════════════════════════════════════════════════════════
# TestFitSummaryEnvelope
# ════════════════════════════════════════════════════════════════════════════


class TestFitSummaryEnvelope:
    def test_success_summary_shape(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        s = result.summary_envelope
        assert s.signal_id == "CALIBRATION_FIT_SUMMARY"
        assert s.phase == "2.4C"
        assert s.derivation == "derived"
        assert s.quality_status == "ok"

    def test_failure_summary_shape(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec(min_sample_count=100)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        s = result.summary_envelope
        assert s.quality_status == "unavailable"
        assert result.param_set is None

    def test_provenance_hashes_included(self):
        corpus = _make_corpus([0.1, 0.5])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        v = result.summary_envelope.values
        assert v["fit_spec_hash"] == spec.fit_spec_hash()
        assert v["source_manifest_hash"] == spec.source_manifest_hash

    def test_exclusion_counts_included(self):
        corpus = [
            _make_corpus_envelope(value=0.1, subject_id="w1"),
            _make_corpus_envelope(value=None, subject_id="w2"),
        ]
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        v = result.summary_envelope.values
        assert v["sample_count_used"] == 1
        assert v["sample_count_excluded"] == 1

    def test_corpus_stats_included(self):
        corpus = _make_corpus([2.0, 5.0, 8.0])
        spec = _make_fit_spec(method="linear_minmax")
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        v = result.summary_envelope.values
        assert v["observed_min"] == 2.0
        assert v["observed_max"] == 8.0
        assert "mean" in v

    def test_deterministic_serialization(self):
        corpus = _make_corpus([0.1, 0.5])
        spec = _make_fit_spec()
        ts = "2026-02-25T12:05:00Z"
        r1 = fit_param_set_from_corpus(corpus, spec, emitted_at=ts)
        r2 = fit_param_set_from_corpus(corpus, spec, emitted_at=ts)
        assert r1.summary_envelope.to_canonical_bytes() == r2.summary_envelope.to_canonical_bytes()

    def test_invalid_spec_summary(self):
        spec = _make_fit_spec(method="nonexistent")
        result = fit_param_set_from_corpus([], spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is None
        assert result.summary_envelope.quality_status == "invalid"
        assert result.errors

    def test_summary_validates(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        errors = validate_envelope(result.summary_envelope)
        assert errors == [], f"Validation errors: {errors}"

    def test_failure_summary_validates(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec(min_sample_count=100)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        errors = validate_envelope(result.summary_envelope)
        assert errors == [], f"Validation errors: {errors}"

    def test_error_messages_capped(self):
        """Error messages in annotations should be capped at 10."""
        spec = _make_fit_spec(method="log_minmax")  # missing epsilon_shift
        result = fit_param_set_from_corpus([], spec, emitted_at="2026-02-25T12:05:00Z")
        msgs = result.summary_envelope.annotations.get("error_messages", [])
        assert len(msgs) <= 10

    def test_param_set_hash_in_success_summary(self):
        corpus = _make_corpus([0.1, 0.5])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        v = result.summary_envelope.values
        assert v["param_set_hash"] is not None
        assert v["param_set_hash"].startswith("sha256:")

    def test_param_set_hash_none_in_failure(self):
        spec = _make_fit_spec(min_sample_count=100)
        result = fit_param_set_from_corpus([], spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.summary_envelope.values["param_set_hash"] is None


# ════════════════════════════════════════════════════════════════════════════
# TestFitParamSetProvenance
# ════════════════════════════════════════════════════════════════════════════


class TestFitParamSetProvenance:
    def test_fit_source_populated(self):
        corpus = _make_corpus([0.1, 0.5])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.fit_source == "signal_envelopes"

    def test_fit_source_replay_run_id(self):
        corpus = _make_corpus([0.1, 0.5])
        spec = CalibrationFitSpec(
            fit_id="fit_replay",
            signal_id="SIGMA_RATE",
            signal_version=1,
            target_field="value",
            method="identity_clip",
            source_mode="replay",
            source_manifest_hash="sha256:replay_manifest",
            source_replay_run_id="replay_run_001",
            created_at="2026-02-25T00:00:00Z",
        )
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.fit_source == "replay_run_001"

    def test_fit_window_count(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.fit_window_count == 3

    def test_fit_skipped_count(self):
        corpus = [
            _make_corpus_envelope(value=0.1, subject_id="w1"),
            _make_corpus_envelope(value=None, subject_id="w2"),
        ]
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.fit_skipped_count == 1

    def test_include_exclude_sets_preserved(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.include_quality_statuses == spec.include_quality_statuses
        assert result.param_set.exclude_classifications == spec.exclude_classifications

    def test_param_set_id_from_fit_id(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert spec.fit_id in result.param_set.param_set_id

    def test_derivation_version(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec()
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set.derivation_version == CALIBRATION_FIT_CONFIG_VERSION


# ════════════════════════════════════════════════════════════════════════════
# TestIntegrationWithApply
# ════════════════════════════════════════════════════════════════════════════


class TestIntegrationWithApply:
    """Fit param sets must be accepted by apply_calibration()."""

    def test_fit_identity_then_apply(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec(method="identity_clip")
        fit_result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")

        source = _make_corpus_envelope(value=0.42)
        calibrated = apply_calibration(
            source, fit_result.param_set, emitted_at="2026-02-25T12:10:00Z",
        )
        assert calibrated.value == pytest.approx(0.42)
        assert calibrated.phase == "2.4C"

    def test_fit_linear_then_apply(self):
        corpus = _make_corpus([0.0, 5.0, 10.0])
        spec = _make_fit_spec(method="linear_minmax")
        fit_result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")

        source = _make_corpus_envelope(value=5.0)
        calibrated = apply_calibration(
            source, fit_result.param_set, emitted_at="2026-02-25T12:10:00Z",
        )
        assert 0.0 <= calibrated.value <= 1.0
        assert calibrated.value == pytest.approx(0.5)

    def test_fit_log_then_apply(self):
        corpus = _make_corpus([0.0, 10.0, 50.0, 100.0])
        spec = _make_fit_spec(
            method="log_minmax", log_base=math.e, epsilon_shift=1.0,
        )
        fit_result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")

        source = _make_corpus_envelope(value=50.0)
        calibrated = apply_calibration(
            source, fit_result.param_set, emitted_at="2026-02-25T12:10:00Z",
        )
        assert 0.0 <= calibrated.value <= 1.0

    def test_fit_decision_lag_backfill_rate_then_apply(self):
        """Fit on target_field in values dict, then apply."""
        envs = [
            _make_corpus_envelope(
                signal_id="DECISION_EVIDENCE_LAG",
                values={"backfill_rate": v},
                subject_id=f"w{i}",
                window_start=f"2026-02-25T{12+i}:00:00Z",
            )
            for i, v in enumerate([0.0, 0.1, 0.3, 0.5])
        ]
        spec = _make_fit_spec(
            signal_id="DECISION_EVIDENCE_LAG",
            target_field="backfill_rate",
            method="identity_clip",
        )
        fit_result = fit_param_set_from_corpus(envs, spec, emitted_at="2026-02-25T12:05:00Z")

        source = _make_corpus_envelope(
            signal_id="DECISION_EVIDENCE_LAG",
            values={"backfill_rate": 0.2},
        )
        calibrated = apply_calibration(
            source, fit_result.param_set, emitted_at="2026-02-25T12:10:00Z",
        )
        assert calibrated.values["target_field"] == "backfill_rate"
        assert calibrated.values["raw_value"] == 0.2

    def test_fitted_param_set_hash_stable(self):
        corpus = _make_corpus([0.1, 0.5, 0.9])
        spec = _make_fit_spec()
        ts = "2026-02-25T12:05:00Z"
        r1 = fit_param_set_from_corpus(corpus, spec, emitted_at=ts)
        r2 = fit_param_set_from_corpus(corpus, spec, emitted_at=ts)
        assert r1.param_set.param_set_hash() == r2.param_set.param_set_hash()

    def test_source_envelopes_not_mutated(self):
        corpus = _make_corpus([0.1, 0.5])
        before = [e.to_dict() for e in corpus]
        spec = _make_fit_spec()
        fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        after = [e.to_dict() for e in corpus]
        assert before == after


# ════════════════════════════════════════════════════════════════════════════
# TestIntegrationWithRealFixtures
# ════════════════════════════════════════════════════════════════════════════


class TestIntegrationWithRealFixtures:
    """Fit from real signal fixture files, then apply."""

    def test_fit_exposure_proxy_from_fixtures(self):
        envs = [
            _load_fixture("envelope_ok_exposure_proxy.json"),
            _load_fixture("envelope_ok_exposure_proxy_zero.json"),
        ]
        spec = _make_fit_spec(
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            log_base=math.e,
            epsilon_shift=1.0,
        )
        result = fit_param_set_from_corpus(envs, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None

        # Apply to a sample
        calibrated = apply_calibration(
            envs[0], result.param_set, emitted_at="2026-02-25T12:10:00Z",
        )
        assert 0.0 <= calibrated.value <= 1.0

    def test_fit_sigma_rate_from_fixtures(self):
        envs = [
            _load_fixture("envelope_ok_sigma_rate.json"),
        ]
        spec = _make_fit_spec(
            signal_id="SIGMA_RATE",
            method="identity_clip",
        )
        result = fit_param_set_from_corpus(envs, spec, emitted_at="2026-02-25T12:05:00Z")
        assert result.param_set is not None

    def test_unavailable_fixture_excluded(self):
        envs = [
            _load_fixture("envelope_ok_sigma_rate.json"),
            _load_fixture("envelope_unavailable_sigma_rate.json"),
        ]
        spec = _make_fit_spec(signal_id="SIGMA_RATE")
        result = fit_param_set_from_corpus(envs, spec, emitted_at="2026-02-25T12:05:00Z")
        # Only the ok one should be included
        assert result.summary_envelope.values["sample_count_used"] == 1


# ════════════════════════════════════════════════════════════════════════════
# TestGoldenFixtures
# ════════════════════════════════════════════════════════════════════════════


class TestGoldenFitFixtures:
    GOLDEN_SUCCESS = FIXTURES / "calibration_fit_summary_success.json"
    GOLDEN_FAILURE = FIXTURES / "calibration_fit_summary_failure.json"

    def _write_golden(self, path: Path, env: SignalEnvelope) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(env.to_json() + "\n")

    def test_golden_success_summary(self):
        corpus = _make_corpus([2.0, 5.0, 8.0, 10.0])
        spec = _make_fit_spec(method="linear_minmax")
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        self._write_golden(self.GOLDEN_SUCCESS, result.summary_envelope)

        golden = SignalEnvelope.from_json(self.GOLDEN_SUCCESS.read_text())
        assert golden.quality_status == "ok"
        assert golden.signal_id == "CALIBRATION_FIT_SUMMARY"

    def test_golden_failure_summary(self):
        corpus = _make_corpus([0.1])
        spec = _make_fit_spec(method="linear_minmax", min_sample_count=100)
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        self._write_golden(self.GOLDEN_FAILURE, result.summary_envelope)

        golden = SignalEnvelope.from_json(self.GOLDEN_FAILURE.read_text())
        assert golden.quality_status == "unavailable"

    def test_golden_summary_validates(self):
        corpus = _make_corpus([2.0, 5.0, 8.0])
        spec = _make_fit_spec(method="linear_minmax")
        result = fit_param_set_from_corpus(corpus, spec, emitted_at="2026-02-25T12:05:00Z")
        errors = validate_envelope(result.summary_envelope)
        assert errors == [], f"Validation errors: {errors}"
