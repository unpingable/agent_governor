# SPDX-License-Identifier: Apache-2.0
"""Tests for Phase C2 CALIBRATION_LAYER — apply-only calibration."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from types import MappingProxyType

import pytest

from governor.signals.calibration_methods import (
    CALIBRATION_METHODS,
    REQUIRED_PARAMS,
    CalibrationMismatchError,
    identity_clip,
    linear_minmax,
    log_minmax,
)
from governor.signals.calibration_layer import (
    CALIBRATION_CONFIG_VERSION,
    CalibrationParamSet,
    apply_calibration,
    validate_param_set,
    _is_numeric,
)
from governor.signals.envelope import SignalEnvelope, validate_envelope

# ── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "signals"
GOLDEN_DIR = FIXTURES  # golden calibrated fixtures live alongside source fixtures


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_fixture(name: str) -> SignalEnvelope:
    """Load a signal envelope fixture by filename."""
    path = FIXTURES / name
    return SignalEnvelope.from_json(path.read_text())


def _make_source(
    *,
    signal_id: str = "SIGMA_RATE",
    signal_version: int = 1,
    value: float | None = 0.15,
    unit: str = "rate",
    quality_status: str = "ok",
    quality_reasons: list[str] | None = None,
    values: dict | None = None,
    phase: str = "2.4A",
) -> SignalEnvelope:
    """Build a minimal source envelope for testing."""
    return SignalEnvelope(
        schema_version="0.4.0",
        emitted_at="2026-02-25T12:00:00Z",
        emitter="governor.signals.test",
        emitter_version="2.4.0-dev",
        signal_id=signal_id,
        signal_version=signal_version,
        phase=phase,
        subject_type="window",
        subject_id="test_window",
        window_start="2026-02-25T11:55:00Z",
        window_end="2026-02-25T12:00:00Z",
        window_kind="rolling_5m",
        value=value,
        unit=unit,
        values=values or {},
        quality_status=quality_status,
        quality_reasons=quality_reasons or [],
        sample_size=10,
        completeness=1.0,
        derivation="windowed_aggregate",
        derivation_version="test-v1",
    )


def _make_param_set(
    *,
    signal_id: str = "SIGMA_RATE",
    signal_version: int = 1,
    target_field: str = "value",
    method: str = "identity_clip",
    params: dict | None = None,
    param_set_id: str = "ps_test_001",
) -> CalibrationParamSet:
    """Build a minimal CalibrationParamSet for testing."""
    if params is None:
        params = {"min": 0.0, "max": 1.0}
    return CalibrationParamSet(
        param_set_id=param_set_id,
        signal_id=signal_id,
        signal_version=signal_version,
        target_field=target_field,
        method=method,
        params=params,
        created_at="2026-02-25T00:00:00Z",
    )


# ════════════════════════════════════════════════════════════════════════════
# TestCalibrationMismatchError
# ════════════════════════════════════════════════════════════════════════════


class TestCalibrationMismatchError:
    def test_basic_construction(self):
        err = CalibrationMismatchError("bad value")
        assert str(err) == "bad value"
        assert err.reason == "bad value"

    def test_param_set_id_and_signal_id(self):
        err = CalibrationMismatchError(
            "mismatch", param_set_id="ps_01", signal_id="SIGMA_RATE"
        )
        assert err.param_set_id == "ps_01"
        assert err.signal_id == "SIGMA_RATE"

    def test_inherits_exception(self):
        assert issubclass(CalibrationMismatchError, Exception)


# ════════════════════════════════════════════════════════════════════════════
# TestIdentityClip
# ════════════════════════════════════════════════════════════════════════════


class TestIdentityClip:
    def test_in_range_value_unchanged(self):
        assert identity_clip(0.5, {"min": 0.0, "max": 1.0}) == 0.5

    def test_value_above_max_clipped(self):
        assert identity_clip(1.5, {"min": 0.0, "max": 1.0}) == 1.0

    def test_value_below_min_clipped(self):
        assert identity_clip(-0.3, {"min": 0.0, "max": 1.0}) == 0.0

    def test_boundary_exactly_zero(self):
        assert identity_clip(0.0, {"min": 0.0, "max": 1.0}) == 0.0

    def test_boundary_exactly_one(self):
        assert identity_clip(1.0, {"min": 0.0, "max": 1.0}) == 1.0

    def test_custom_narrow_range(self):
        assert identity_clip(0.3, {"min": 0.2, "max": 0.8}) == 0.3
        assert identity_clip(0.1, {"min": 0.2, "max": 0.8}) == 0.2
        assert identity_clip(0.9, {"min": 0.2, "max": 0.8}) == 0.8

    def test_refuse_inverted_bounds(self):
        with pytest.raises(CalibrationMismatchError, match="inverted bounds"):
            identity_clip(0.5, {"min": 0.8, "max": 0.2})

    def test_refuse_bounds_outside_unit(self):
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            identity_clip(0.5, {"min": -1.0, "max": 2.0})

    def test_refuse_min_negative(self):
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            identity_clip(0.5, {"min": -0.1, "max": 1.0})

    def test_refuse_max_above_one(self):
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            identity_clip(0.5, {"min": 0.0, "max": 1.1})


# ════════════════════════════════════════════════════════════════════════════
# TestLinearMinmax
# ════════════════════════════════════════════════════════════════════════════


class TestLinearMinmax:
    def test_normal_scaling(self):
        result = linear_minmax(5.0, {
            "observed_min": 0.0, "observed_max": 10.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == pytest.approx(0.5)

    def test_degenerate_same_bounds(self):
        result = linear_minmax(5.0, {
            "observed_min": 5.0, "observed_max": 5.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == 0.5

    def test_value_at_obs_min(self):
        result = linear_minmax(0.0, {
            "observed_min": 0.0, "observed_max": 10.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == pytest.approx(0.0)

    def test_value_at_obs_max(self):
        result = linear_minmax(10.0, {
            "observed_min": 0.0, "observed_max": 10.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == pytest.approx(1.0)

    def test_value_below_obs_min_clipped(self):
        result = linear_minmax(-5.0, {
            "observed_min": 0.0, "observed_max": 10.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == 0.0

    def test_value_above_obs_max_clipped(self):
        result = linear_minmax(15.0, {
            "observed_min": 0.0, "observed_max": 10.0,
            "clip_min": 0.0, "clip_max": 1.0,
        })
        assert result == 1.0

    def test_refuse_inverted_observed_bounds(self):
        with pytest.raises(CalibrationMismatchError, match="inverted bounds.*observed_max"):
            linear_minmax(5.0, {
                "observed_min": 10.0, "observed_max": 0.0,
                "clip_min": 0.0, "clip_max": 1.0,
            })

    def test_refuse_inverted_clip_bounds(self):
        with pytest.raises(CalibrationMismatchError, match="inverted.*clip"):
            linear_minmax(5.0, {
                "observed_min": 0.0, "observed_max": 10.0,
                "clip_min": 0.8, "clip_max": 0.2,
            })

    def test_refuse_clip_outside_unit(self):
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            linear_minmax(5.0, {
                "observed_min": 0.0, "observed_max": 10.0,
                "clip_min": -0.5, "clip_max": 1.5,
            })


# ════════════════════════════════════════════════════════════════════════════
# TestLogMinmax
# ════════════════════════════════════════════════════════════════════════════


class TestLogMinmax:
    """16 tests covering param-set guards, runtime guard, and normal operation."""

    _VALID_PARAMS = {
        "observed_min": 0.0, "observed_max": 100.0,
        "log_base": math.e, "epsilon_shift": 1.0,
        "clip_min": 0.0, "clip_max": 1.0,
    }

    def test_normal_positive_value(self):
        result = log_minmax(50.0, self._VALID_PARAMS)
        assert 0.0 < result < 1.0

    def test_degenerate_obs_min_eq_obs_max(self):
        params = {**self._VALID_PARAMS, "observed_min": 5.0, "observed_max": 5.0}
        result = log_minmax(5.0, params)
        assert result == 0.5

    def test_value_at_obs_min(self):
        result = log_minmax(0.0, self._VALID_PARAMS)
        assert result == pytest.approx(0.0)

    def test_value_at_obs_max(self):
        result = log_minmax(100.0, self._VALID_PARAMS)
        assert result == pytest.approx(1.0)

    def test_epsilon_shift_value_zero(self):
        params = {**self._VALID_PARAMS, "epsilon_shift": 1e-10}
        result = log_minmax(0.0, params)
        assert _is_numeric(result)

    def test_epsilon_shift_negative_value_valid(self):
        # value=-0.5, epsilon_shift=1.0, so shifted=0.5 > 0 → valid
        result = log_minmax(-0.5, self._VALID_PARAMS)
        assert _is_numeric(result)

    def test_refuse_value_plus_epsilon_le_zero(self):
        with pytest.raises(CalibrationMismatchError, match="domain error"):
            log_minmax(-2.0, self._VALID_PARAMS)  # -2 + 1 = -1 <= 0

    def test_refuse_log_base_zero(self):
        params = {**self._VALID_PARAMS, "log_base": 0}
        with pytest.raises(CalibrationMismatchError, match="log_base"):
            log_minmax(5.0, params)

    def test_refuse_log_base_one(self):
        params = {**self._VALID_PARAMS, "log_base": 1}
        with pytest.raises(CalibrationMismatchError, match="log_base"):
            log_minmax(5.0, params)

    def test_refuse_log_base_negative(self):
        params = {**self._VALID_PARAMS, "log_base": -2}
        with pytest.raises(CalibrationMismatchError, match="log_base"):
            log_minmax(5.0, params)

    def test_refuse_epsilon_shift_le_zero(self):
        params = {**self._VALID_PARAMS, "epsilon_shift": 0}
        with pytest.raises(CalibrationMismatchError, match="epsilon_shift"):
            log_minmax(5.0, params)

    def test_refuse_obs_min_plus_epsilon_le_zero(self):
        params = {**self._VALID_PARAMS, "observed_min": -2.0, "epsilon_shift": 1.0}
        with pytest.raises(CalibrationMismatchError, match="observed_min.*epsilon"):
            log_minmax(5.0, params)

    def test_refuse_obs_max_plus_epsilon_le_zero(self):
        # obs_min + eps = 1.0 > 0 (passes), obs_max + eps = -1.0 <= 0 (fires)
        params = {
            **self._VALID_PARAMS,
            "observed_min": 0.0, "observed_max": -2.0,
            "epsilon_shift": 1.0,
        }
        with pytest.raises(CalibrationMismatchError, match="observed_max.*epsilon"):
            log_minmax(5.0, params)

    def test_refuse_inverted_observed_bounds(self):
        params = {**self._VALID_PARAMS, "observed_min": 100.0, "observed_max": 0.0}
        with pytest.raises(CalibrationMismatchError, match="inverted bounds.*observed_max"):
            log_minmax(5.0, params)

    def test_refuse_inverted_clip_bounds(self):
        params = {**self._VALID_PARAMS, "clip_min": 0.8, "clip_max": 0.2}
        with pytest.raises(CalibrationMismatchError, match="inverted.*clip"):
            log_minmax(5.0, params)

    def test_degenerate_log_space_returns_half(self):
        """When obs_min == obs_max, log_min == log_max → returns 0.5, not error."""
        params = {**self._VALID_PARAMS, "observed_min": 10.0, "observed_max": 10.0}
        result = log_minmax(10.0, params)
        assert result == 0.5

    def test_refuse_clip_outside_unit(self):
        params = {**self._VALID_PARAMS, "clip_min": -0.1, "clip_max": 1.0}
        with pytest.raises(CalibrationMismatchError, match="outside \\[0,1\\]"):
            log_minmax(5.0, params)


# ════════════════════════════════════════════════════════════════════════════
# TestCalibrationParamSet
# ════════════════════════════════════════════════════════════════════════════


class TestCalibrationParamSet:
    def test_frozen_dataclass(self):
        ps = _make_param_set()
        with pytest.raises(AttributeError):
            ps.param_set_id = "changed"  # type: ignore[misc]

    def test_params_is_mapping_proxy(self):
        ps = _make_param_set()
        assert isinstance(ps.params, MappingProxyType)

    def test_mutating_source_dict_no_effect(self):
        """BUG FIX (Nit 8): MappingProxyType wraps a COPY, not a view."""
        source = {"min": 0.0, "max": 1.0}
        ps = CalibrationParamSet(
            param_set_id="ps_bug",
            signal_id="TEST",
            signal_version=1,
            target_field="value",
            method="identity_clip",
            params=source,
        )
        source["min"] = 999.0  # mutate after construction
        assert ps.params["min"] == 0.0  # unaffected

    def test_to_dict_from_dict_roundtrip(self):
        ps = _make_param_set(
            params={"min": 0.0, "max": 1.0},
        )
        d = ps.to_dict()
        ps2 = CalibrationParamSet.from_dict(d)
        assert ps2.param_set_id == ps.param_set_id
        assert ps2.signal_id == ps.signal_id
        assert dict(ps2.params) == dict(ps.params)
        assert ps2.method == ps.method

    def test_param_set_hash_deterministic(self):
        ps = _make_param_set()
        h1 = ps.param_set_hash()
        h2 = ps.param_set_hash()
        assert h1 == h2

    def test_param_set_hash_changes_with_params(self):
        ps1 = _make_param_set(params={"min": 0.0, "max": 1.0})
        ps2 = _make_param_set(params={"min": 0.1, "max": 0.9})
        assert ps1.param_set_hash() != ps2.param_set_hash()

    def test_param_set_hash_includes_param_set_id(self):
        ps1 = _make_param_set(param_set_id="ps_a")
        ps2 = _make_param_set(param_set_id="ps_b")
        assert ps1.param_set_hash() != ps2.param_set_hash()

    def test_required_fields(self):
        ps = _make_param_set()
        assert ps.param_set_id
        assert ps.signal_id
        assert ps.method
        assert ps.target_field

    def test_frozenset_serialization(self):
        ps = CalibrationParamSet(
            param_set_id="ps_fs",
            signal_id="TEST",
            signal_version=1,
            target_field="value",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
            include_quality_statuses=frozenset({"ok", "partial"}),
            exclude_classifications=frozenset({"indeterminate"}),
        )
        d = ps.to_dict()
        assert d["include_quality_statuses"] == ["ok", "partial"]  # sorted
        assert d["exclude_classifications"] == ["indeterminate"]

    def test_hash_format_prefix(self):
        ps = _make_param_set()
        h = ps.param_set_hash()
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars


# ════════════════════════════════════════════════════════════════════════════
# TestValidateParamSet
# ════════════════════════════════════════════════════════════════════════════


class TestValidateParamSet:
    def test_valid_param_set_passes(self):
        src = _make_source()
        ps = _make_param_set()
        validate_param_set(ps, src)  # no exception

    def test_signal_id_mismatch(self):
        src = _make_source(signal_id="EXPOSURE_PROXY")
        ps = _make_param_set(signal_id="SIGMA_RATE")
        with pytest.raises(CalibrationMismatchError, match="signal_id mismatch"):
            validate_param_set(ps, src)

    def test_signal_version_mismatch(self):
        src = _make_source(signal_version=2)
        ps = _make_param_set(signal_version=1)
        with pytest.raises(CalibrationMismatchError, match="signal_version mismatch"):
            validate_param_set(ps, src)

    def test_target_field_value_always_valid(self):
        src = _make_source()
        ps = _make_param_set(target_field="value")
        validate_param_set(ps, src)  # no exception

    def test_target_field_in_values_dict(self):
        src = _make_source(values={"backfill_rate": 0.3})
        ps = _make_param_set(target_field="backfill_rate")
        validate_param_set(ps, src)  # no exception

    def test_target_field_not_found(self):
        src = _make_source(values={})
        ps = _make_param_set(target_field="nonexistent_field")
        with pytest.raises(CalibrationMismatchError, match="not found"):
            validate_param_set(ps, src)

    def test_unknown_method(self):
        src = _make_source()
        ps = _make_param_set(method="quadratic_fit")
        with pytest.raises(CalibrationMismatchError, match="unknown method"):
            validate_param_set(ps, src)

    def test_missing_required_param(self):
        src = _make_source()
        ps = _make_param_set(method="linear_minmax", params={"observed_min": 0.0})
        with pytest.raises(CalibrationMismatchError, match="missing required"):
            validate_param_set(ps, src)

    def test_target_field_non_numeric(self):
        src = _make_source(values={"status": "ok"})
        ps = _make_param_set(target_field="status")
        with pytest.raises(CalibrationMismatchError, match="not numeric"):
            validate_param_set(ps, src)

    def test_target_field_bool_rejected(self):
        src = _make_source(values={"flag": True})
        ps = _make_param_set(target_field="flag")
        with pytest.raises(CalibrationMismatchError, match="not numeric"):
            validate_param_set(ps, src)


# ════════════════════════════════════════════════════════════════════════════
# TestIsNumeric
# ════════════════════════════════════════════════════════════════════════════


class TestIsNumeric:
    def test_int_is_numeric(self):
        assert _is_numeric(42) is True

    def test_float_is_numeric(self):
        assert _is_numeric(3.14) is True

    def test_bool_not_numeric(self):
        assert _is_numeric(True) is False
        assert _is_numeric(False) is False

    def test_string_not_numeric(self):
        assert _is_numeric("0.5") is False

    def test_none_not_numeric(self):
        assert _is_numeric(None) is False


# ════════════════════════════════════════════════════════════════════════════
# TestApplyCalibration
# ════════════════════════════════════════════════════════════════════════════


class TestApplyCalibration:
    def test_identity_clip_on_bounded_signal(self):
        src = _make_source(value=0.15)
        ps = _make_param_set(method="identity_clip", params={"min": 0.0, "max": 1.0})
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value == pytest.approx(0.15)

    def test_log_minmax_on_unbounded_signal(self):
        src = _make_source(
            signal_id="EXPOSURE_PROXY", value=18.5, unit="exposure_points",
        )
        ps = _make_param_set(
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            params={
                "observed_min": 0.0, "observed_max": 100.0,
                "log_base": math.e, "epsilon_shift": 1.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert 0.0 <= result.value <= 1.0

    def test_source_value_none(self):
        src = _make_source(value=None, quality_status="ok")
        ps = _make_param_set()
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value is None

    def test_source_quality_unavailable(self):
        src = _make_source(value=None, quality_status="unavailable")
        ps = _make_param_set()
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value is None
        assert result.quality_status == "unavailable"

    def test_source_quality_invalid(self):
        src = _make_source(value=None, quality_status="invalid")
        ps = _make_param_set()
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value is None
        assert result.quality_status == "invalid"

    def test_source_quality_partial(self):
        src = _make_source(value=0.3, quality_status="partial")
        ps = _make_param_set()
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value == pytest.approx(0.3)
        assert result.quality_status == "partial"

    def test_source_quality_ok(self):
        src = _make_source(value=0.7, quality_status="ok")
        ps = _make_param_set()
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.value == pytest.approx(0.7)
        assert result.quality_status == "ok"

    def test_normalized_value_in_unit_range(self):
        src = _make_source(
            signal_id="EXPOSURE_PROXY", value=50.0, unit="exposure_points",
        )
        ps = _make_param_set(
            signal_id="EXPOSURE_PROXY",
            method="linear_minmax",
            params={
                "observed_min": 0.0, "observed_max": 100.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert 0.0 <= result.value <= 1.0

    def test_source_envelope_not_mutated(self):
        src = _make_source(value=0.5)
        src_dict_before = src.to_dict()
        ps = _make_param_set()
        apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert src.to_dict() == src_dict_before

    def test_deterministic_same_inputs(self):
        src = _make_source(value=0.42)
        ps = _make_param_set()
        r1 = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        r2 = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r1.to_dict() == r2.to_dict()

    def test_target_field_value_top_level(self):
        src = _make_source(value=0.6)
        ps = _make_param_set(target_field="value")
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.values["raw_value"] == 0.6

    def test_target_field_in_values_dict(self):
        src = _make_source(values={"backfill_rate": 0.3})
        ps = _make_param_set(target_field="backfill_rate")
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert result.values["raw_value"] == 0.3
        assert result.values["target_field"] == "backfill_rate"


# ════════════════════════════════════════════════════════════════════════════
# TestCompanionEnvelopeShape
# ════════════════════════════════════════════════════════════════════════════


class TestCompanionEnvelopeShape:
    @pytest.fixture()
    def calibrated(self):
        src = _make_source(value=0.5, unit="rate")
        ps = _make_param_set()
        return apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")

    def test_signal_id_preserved(self, calibrated):
        assert calibrated.signal_id == "SIGMA_RATE"

    def test_signal_version_preserved(self, calibrated):
        assert calibrated.signal_version == 1

    def test_phase_is_2_4C(self, calibrated):
        assert calibrated.phase == "2.4C"

    def test_unit_is_normalized(self, calibrated):
        assert calibrated.unit == "normalized"

    def test_derivation_is_derived(self, calibrated):
        assert calibrated.derivation == "derived"

    def test_derivation_version(self, calibrated):
        assert calibrated.derivation_version == CALIBRATION_CONFIG_VERSION

    def test_values_has_required_keys(self, calibrated):
        v = calibrated.values
        assert "raw_value" in v
        assert "normalized_value" in v
        assert "calibration_method" in v
        assert "param_set_id" in v
        assert "input_quality_status" in v
        assert "config_version" in v

    def test_values_has_target_field(self, calibrated):
        assert calibrated.values["target_field"] == "value"

    def test_values_has_source_unit(self, calibrated):
        assert calibrated.values["source_unit"] == "rate"

    def test_annotations_has_required_keys(self, calibrated):
        a = calibrated.annotations
        assert "source_signal_hash" in a
        assert a["calibration_applied"] is True
        assert "param_set_id" in a
        assert "config_version" in a

    def test_annotations_has_param_set_hash(self, calibrated):
        assert "param_set_hash" in calibrated.annotations
        assert calibrated.annotations["param_set_hash"].startswith("sha256:")

    def test_window_preserved(self, calibrated):
        assert calibrated.window_start == "2026-02-25T11:55:00Z"
        assert calibrated.window_end == "2026-02-25T12:00:00Z"
        assert calibrated.window_kind == "rolling_5m"

    def test_subject_preserved(self, calibrated):
        assert calibrated.subject_type == "window"
        assert calibrated.subject_id == "test_window"


# ════════════════════════════════════════════════════════════════════════════
# TestQualityPropagation
# ════════════════════════════════════════════════════════════════════════════


class TestQualityPropagation:
    def test_ok_stays_ok(self):
        src = _make_source(value=0.5, quality_status="ok")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.quality_status == "ok"

    def test_partial_stays_partial(self):
        src = _make_source(value=0.5, quality_status="partial")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.quality_status == "partial"

    def test_unavailable_stays_unavailable(self):
        src = _make_source(value=None, quality_status="unavailable")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.quality_status == "unavailable"
        assert r.value is None

    def test_invalid_stays_invalid(self):
        src = _make_source(value=None, quality_status="invalid")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.quality_status == "invalid"
        assert r.value is None

    def test_quality_never_upgraded(self):
        """Partial input should never become ok output."""
        src = _make_source(value=0.5, quality_status="partial")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.quality_status != "ok"


# ════════════════════════════════════════════════════════════════════════════
# TestSourceNotMutated
# ════════════════════════════════════════════════════════════════════════════


class TestSourceNotMutated:
    def test_source_envelope_unchanged(self):
        src = _make_source(value=0.5, values={"extra": 42})
        before = src.to_dict()
        ps = _make_param_set()
        apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert src.to_dict() == before

    def test_param_set_unchanged(self):
        ps = _make_param_set()
        before = ps.to_dict()
        src = _make_source()
        apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert ps.to_dict() == before


# ════════════════════════════════════════════════════════════════════════════
# TestDeterminism
# ════════════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_same_source_same_params_identical(self):
        src = _make_source(value=0.42)
        ps = _make_param_set()
        ts = "2026-02-25T12:05:00Z"
        r1 = apply_calibration(src, ps, emitted_at=ts)
        r2 = apply_calibration(src, ps, emitted_at=ts)
        assert r1.to_canonical_bytes() == r2.to_canonical_bytes()

    def test_different_emitted_at_only_difference(self):
        src = _make_source(value=0.42)
        ps = _make_param_set()
        r1 = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        r2 = apply_calibration(src, ps, emitted_at="2026-02-25T12:06:00Z")
        assert r1.emitted_at != r2.emitted_at
        assert r1.value == r2.value
        assert r1.values == r2.values

    def test_canonical_json_stable(self):
        src = _make_source(value=0.42)
        ps = _make_param_set()
        ts = "2026-02-25T12:05:00Z"
        r = apply_calibration(src, ps, emitted_at=ts)
        b1 = r.to_canonical_bytes()
        b2 = r.to_canonical_bytes()
        assert b1 == b2


# ════════════════════════════════════════════════════════════════════════════
# TestMissingNotZero
# ════════════════════════════════════════════════════════════════════════════


class TestMissingNotZero:
    def test_none_stays_none(self):
        src = _make_source(value=None, quality_status="ok")
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.value is None
        assert r.values["normalized_value"] is None

    def test_zero_gets_calibrated(self):
        src = _make_source(value=0.0)
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.value == 0.0  # identity_clip(0.0, min=0, max=1) = 0.0
        assert r.values["raw_value"] == 0.0

    def test_zero_with_log_minmax_epsilon_shifted(self):
        src = _make_source(signal_id="EXPOSURE_PROXY", value=0.0, unit="exposure_points")
        ps = _make_param_set(
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            params={
                "observed_min": 0.0, "observed_max": 100.0,
                "log_base": math.e, "epsilon_shift": 1.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.value is not None
        assert r.value >= 0.0


# ════════════════════════════════════════════════════════════════════════════
# TestRealSignalFixtures
# ════════════════════════════════════════════════════════════════════════════


class TestRealSignalFixtures:
    """Apply calibration to real signal fixture files."""

    def test_exposure_proxy_log_minmax(self):
        src = _load_fixture("envelope_ok_exposure_proxy.json")
        ps = _make_param_set(
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            params={
                "observed_min": 0.0, "observed_max": 200.0,
                "log_base": math.e, "epsilon_shift": 1.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert 0.0 <= r.value <= 1.0
        assert r.unit == "normalized"

    def test_sigma_rate_identity_clip(self):
        src = _load_fixture("envelope_ok_sigma_rate.json")
        ps = _make_param_set(
            signal_id="SIGMA_RATE",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        # SIGMA_RATE value ~0.087 should pass through unchanged
        assert r.value == pytest.approx(src.value, abs=1e-9)

    def test_unavailable_sigma_rate(self):
        src = _load_fixture("envelope_unavailable_sigma_rate.json")
        ps = _make_param_set(
            signal_id="SIGMA_RATE",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.value is None
        assert r.quality_status == "unavailable"

    def test_decision_lag_backfill_rate(self):
        src = _load_fixture("envelope_supported_decision_lag.json")
        ps = _make_param_set(
            signal_id="DECISION_EVIDENCE_LAG",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
            target_field="backfill_rate",
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.values["target_field"] == "backfill_rate"
        assert r.values["raw_value"] == 0.0

    def test_empty_decision_lag_unavailable(self):
        src = _load_fixture("envelope_empty_decision_lag.json")
        ps = _make_param_set(
            signal_id="DECISION_EVIDENCE_LAG",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        assert r.value is None
        assert r.quality_status == "unavailable"

    def test_exposure_proxy_zero_log_minmax(self):
        src = _load_fixture("envelope_ok_exposure_proxy_zero.json")
        ps = _make_param_set(
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            params={
                "observed_min": 0.0, "observed_max": 200.0,
                "log_base": math.e, "epsilon_shift": 1.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        # value=0.0 with epsilon_shift=1.0 → log(1)/log(e) = 0, normalized to 0.0
        assert r.value is not None
        assert r.value == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════════════════
# TestGoldenFixtures
# ════════════════════════════════════════════════════════════════════════════


class TestGoldenFixtures:
    """Generate and verify golden calibrated fixtures."""

    GOLDEN_EXPOSURE = GOLDEN_DIR / "envelope_calibrated_exposure_proxy.json"
    GOLDEN_SIGMA = GOLDEN_DIR / "envelope_calibrated_sigma_rate.json"
    GOLDEN_UNAVAILABLE = GOLDEN_DIR / "envelope_calibrated_unavailable.json"

    def _write_golden(self, path: Path, env: SignalEnvelope) -> None:
        """Write golden fixture if it doesn't exist."""
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(env.to_json() + "\n")

    def test_golden_calibrated_exposure_proxy(self):
        src = _load_fixture("envelope_ok_exposure_proxy.json")
        ps = _make_param_set(
            param_set_id="golden_exposure_log",
            signal_id="EXPOSURE_PROXY",
            method="log_minmax",
            params={
                "observed_min": 0.0, "observed_max": 200.0,
                "log_base": math.e, "epsilon_shift": 1.0,
                "clip_min": 0.0, "clip_max": 1.0,
            },
        )
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        self._write_golden(self.GOLDEN_EXPOSURE, result)

        golden = SignalEnvelope.from_json(self.GOLDEN_EXPOSURE.read_text())
        assert result.value == pytest.approx(golden.value, abs=1e-12)
        assert result.signal_id == golden.signal_id
        assert result.phase == "2.4C"

    def test_golden_calibrated_sigma_rate(self):
        src = _load_fixture("envelope_ok_sigma_rate.json")
        ps = _make_param_set(
            param_set_id="golden_sigma_clip",
            signal_id="SIGMA_RATE",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        self._write_golden(self.GOLDEN_SIGMA, result)

        golden = SignalEnvelope.from_json(self.GOLDEN_SIGMA.read_text())
        assert result.value == pytest.approx(golden.value, abs=1e-12)
        assert result.signal_id == golden.signal_id
        assert result.phase == "2.4C"

    def test_golden_calibrated_unavailable(self):
        src = _load_fixture("envelope_unavailable_sigma_rate.json")
        ps = _make_param_set(
            param_set_id="golden_unavail",
            signal_id="SIGMA_RATE",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        result = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        self._write_golden(self.GOLDEN_UNAVAILABLE, result)

        golden = SignalEnvelope.from_json(self.GOLDEN_UNAVAILABLE.read_text())
        assert result.value is None
        assert golden.value is None
        assert result.quality_status == "unavailable"


# ════════════════════════════════════════════════════════════════════════════
# TestEnvelopeValidation
# ════════════════════════════════════════════════════════════════════════════


class TestEnvelopeValidation:
    def test_calibrated_envelope_passes_validation(self):
        src = _make_source(value=0.5)
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        errors = validate_envelope(r)
        assert errors == [], f"Validation errors: {errors}"

    def test_calibrated_with_target_in_values_passes(self):
        src = _make_source(values={"backfill_rate": 0.3})
        ps = _make_param_set(target_field="backfill_rate")
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        errors = validate_envelope(r)
        assert errors == [], f"Validation errors: {errors}"

    def test_calibrated_envelope_serializes_to_json(self):
        src = _make_source(value=0.5)
        ps = _make_param_set()
        r = apply_calibration(src, ps, emitted_at="2026-02-25T12:05:00Z")
        j = r.to_json()
        parsed = json.loads(j)
        assert parsed["phase"] == "2.4C"
        assert parsed["unit"] == "normalized"


# ════════════════════════════════════════════════════════════════════════════
# TestRegistryConsistency
# ════════════════════════════════════════════════════════════════════════════


class TestRegistryConsistency:
    def test_methods_and_params_same_keys(self):
        assert set(CALIBRATION_METHODS.keys()) == set(REQUIRED_PARAMS.keys())

    def test_all_params_are_frozensets(self):
        for method, params in REQUIRED_PARAMS.items():
            assert isinstance(params, frozenset), f"{method} params not frozenset"

    def test_methods_are_callable(self):
        for method, fn in CALIBRATION_METHODS.items():
            assert callable(fn), f"{method} is not callable"
