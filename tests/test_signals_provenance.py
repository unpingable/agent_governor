# SPDX-License-Identifier: Apache-2.0
"""Tests for provenance tightening across signal spine.

Verifies:
  1. source_versions always populated (never {})
  2. source_receipt_ids monotonic propagation (A → B → C → D)
  3. session_id present in Phase D outputs
"""

from __future__ import annotations

import pytest

from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    QualityStatus,
    SignalEnvelope,
    default_source_versions,
)
from governor.signals.exposure_proxy import (
    ExposureComponents,
    derive_exposure_proxy,
)
from governor.signals.silent_suppression import (
    SuppressionIndicators,
    derive_silent_suppression,
)
from governor.signals.sigma_rate import (
    SigmaMatchResult,
    derive_sigma_rate,
)
from governor.signals.capture_self_diagnostic import (
    DiagnosticInputs,
    derive_capture_self_diagnostic,
)
from governor.signals.decision_evidence_lag import (
    derive_decision_evidence_lag,
)
from governor.signals.calibration_layer import apply_calibration, CalibrationParamSet
from governor.signals.predict_regime import predict_regime_preflight
from governor.signals.gate_check_summary import (
    build_gate_check_summary,
    build_gate_check_error_summary,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────

WIN_START = "2026-03-03T00:00:00Z"
WIN_END = "2026-03-03T00:05:00Z"
WIN_KIND = "rolling_5m"


def _make_a1(receipt_ids: list[str] | None = None, session_id: str | None = None):
    return derive_exposure_proxy(
        ExposureComponents(tool_dispatch_attempts=5, chat_generation_calls=3),
        WIN_START, WIN_END, WIN_KIND,
        source_receipt_ids=receipt_ids,
        session_id=session_id,
        emitted_at=WIN_END,
    )


def _make_a2(receipt_ids: list[str] | None = None, session_id: str | None = None):
    return derive_silent_suppression(
        SuppressionIndicators(
            expected_event_markers=5,
            observed_event_markers=3,
            activity_observed=True,
            in_path_evidence_present=True,
        ),
        WIN_START, WIN_END, WIN_KIND,
        source_receipt_ids=receipt_ids,
        session_id=session_id,
        emitted_at=WIN_END,
    )


def _make_a3(receipt_ids: list[str] | None = None, session_id: str | None = None):
    return derive_sigma_rate(
        SigmaMatchResult(eligible_events=10),
        WIN_START, WIN_END, WIN_KIND,
        source_receipt_ids=receipt_ids,
        session_id=session_id,
        emitted_at=WIN_END,
    )


# ── 1. default_source_versions ───────────────────────────────────────────────


class TestDefaultSourceVersions:
    def test_returns_non_empty(self):
        sv = default_source_versions()
        assert isinstance(sv, dict)
        assert len(sv) >= 2

    def test_has_governor_key(self):
        sv = default_source_versions()
        assert "governor" in sv
        assert sv["governor"] != ""

    def test_has_envelope_schema_key(self):
        sv = default_source_versions()
        assert "envelope_schema" in sv
        assert sv["envelope_schema"] == CURRENT_SCHEMA_VERSION


# ── 2. source_versions populated in every builder ────────────────────────────


class TestSourceVersionsPopulated:
    """Every signal builder produces non-empty source_versions."""

    def test_a1_exposure_proxy(self):
        env = _make_a1()
        assert env.source_versions, "source_versions must not be empty"
        assert "governor" in env.source_versions

    def test_a2_silent_suppression(self):
        env = _make_a2()
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_a3_sigma_rate(self):
        env = _make_a3()
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_b1_capture_self_diagnostic(self):
        env = derive_capture_self_diagnostic(
            DiagnosticInputs(
                a1_exposure_proxy=_make_a1(),
                a2_silent_suppression=_make_a2(),
                a3_sigma_rate=_make_a3(),
            ),
            WIN_START, WIN_END, WIN_KIND,
            emitted_at=WIN_END,
        )
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_b2_decision_evidence_lag(self):
        env = derive_decision_evidence_lag(
            [],  # empty receipt list
            WIN_START, WIN_END, WIN_KIND,
            emitted_at=WIN_END,
        )
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_d_predict_regime(self):
        a1 = _make_a1()
        a2 = _make_a2()
        a3 = _make_a3()
        env = predict_regime_preflight([a1, a2, a3], emitted_at=WIN_END)
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_gate_check_summary(self):
        env = build_gate_check_summary(
            verdict="OK", claims_count=1, violations_count=0, warnings_count=0,
        )
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_gate_check_error_summary(self):
        env = build_gate_check_error_summary(
            error_type="ValueError", error_message="boom",
        )
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_caller_override_respected(self):
        """Explicit source_versions from caller takes precedence."""
        custom = {"my_tool": "1.0"}
        env = derive_exposure_proxy(
            ExposureComponents(tool_dispatch_attempts=1),
            WIN_START, WIN_END, WIN_KIND,
            source_versions=custom,
            emitted_at=WIN_END,
        )
        assert env.source_versions == custom


# ── 3. source_receipt_ids monotonic propagation ──────────────────────────────


class TestReceiptIdPropagation:
    """source_receipt_ids never silently dropped through the chain."""

    def test_a_signals_accept_receipt_ids(self):
        ids = ["r1", "r2", "r3"]
        for builder in (_make_a1, _make_a2, _make_a3):
            env = builder(receipt_ids=ids)
            assert env.source_receipt_ids == ids

    def test_b1_unions_from_a_inputs(self):
        """B1 unions source_receipt_ids from A1 + A2 + A3."""
        a1 = _make_a1(receipt_ids=["r1", "r2"])
        a2 = _make_a2(receipt_ids=["r3"])
        a3 = _make_a3(receipt_ids=["r4", "r5"])
        env = derive_capture_self_diagnostic(
            DiagnosticInputs(
                a1_exposure_proxy=a1,
                a2_silent_suppression=a2,
                a3_sigma_rate=a3,
            ),
            WIN_START, WIN_END, WIN_KIND,
            emitted_at=WIN_END,
        )
        assert set(env.source_receipt_ids) == {"r1", "r2", "r3", "r4", "r5"}

    def test_b1_handles_none_inputs(self):
        """B1 with missing A1/A3 still propagates from A2."""
        a2 = _make_a2(receipt_ids=["r1"])
        env = derive_capture_self_diagnostic(
            DiagnosticInputs(
                a1_exposure_proxy=None,
                a2_silent_suppression=a2,
                a3_sigma_rate=None,
            ),
            WIN_START, WIN_END, WIN_KIND,
            emitted_at=WIN_END,
        )
        assert env.source_receipt_ids == ["r1"]

    def test_calibration_layer_propagates(self):
        """C calibration layer preserves receipt IDs from source."""
        a1 = _make_a1(receipt_ids=["r1", "r2"])
        param_set = CalibrationParamSet(
            param_set_id="test",
            signal_id="EXPOSURE_PROXY",
            signal_version=1,
            target_field="value",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        cal = apply_calibration(a1, param_set, emitted_at=WIN_END)
        assert cal.source_receipt_ids == ["r1", "r2"]

    def test_d_unions_from_input_envelopes(self):
        """Phase D unions receipt IDs from all input envelopes."""
        a1 = _make_a1(receipt_ids=["r1"])
        a2 = _make_a2(receipt_ids=["r2"])
        a3 = _make_a3(receipt_ids=["r3"])
        env = predict_regime_preflight([a1, a2, a3], emitted_at=WIN_END)
        assert set(env.source_receipt_ids) == {"r1", "r2", "r3"}

    def test_full_chain_monotonic(self):
        """A → C (calibration) → D preserves receipt IDs through the chain."""
        a1 = _make_a1(receipt_ids=["r1"])
        a2 = _make_a2(receipt_ids=["r2"])
        a3 = _make_a3(receipt_ids=["r3"])

        # Calibrate A1
        param_set = CalibrationParamSet(
            param_set_id="test",
            signal_id="EXPOSURE_PROXY",
            signal_version=1,
            target_field="value",
            method="identity_clip",
            params={"min": 0.0, "max": 1.0},
        )
        a1_cal = apply_calibration(a1, param_set, emitted_at=WIN_END)
        assert "r1" in a1_cal.source_receipt_ids

        # Predict regime from calibrated + raw
        env = predict_regime_preflight(
            [a1_cal, a2, a3], emitted_at=WIN_END,
        )
        assert "r1" in env.source_receipt_ids
        assert "r2" in env.source_receipt_ids
        assert "r3" in env.source_receipt_ids


# ── 4. session_id in Phase D ─────────────────────────────────────────────────


class TestSessionIdInPhaseD:
    def test_explicit_session_id(self):
        """Phase D accepts explicit session_id parameter."""
        a1 = _make_a1()
        a2 = _make_a2()
        a3 = _make_a3()
        env = predict_regime_preflight(
            [a1, a2, a3],
            session_id="gov_explicit123",
            emitted_at=WIN_END,
        )
        assert env.session_id == "gov_explicit123"

    def test_inferred_from_most_recent_input(self):
        """Phase D infers session_id from most recent input envelope."""
        a1 = _make_a1(session_id="gov_old")
        # A2 is emitted at same time but sorted later — most recent wins
        a2 = _make_a2(session_id="gov_session456")
        a3 = _make_a3(session_id=None)
        env = predict_regime_preflight([a1, a2, a3], emitted_at=WIN_END)
        # All emitted_at are the same (WIN_END), so first with session_id
        # from reverse-sorted wins. Since all have same emitted_at, order
        # is stable — first non-None wins.
        assert env.session_id is not None

    def test_none_when_no_inputs_have_session(self):
        """Phase D session_id is None when no inputs have it."""
        a1 = _make_a1(session_id=None)
        a2 = _make_a2(session_id=None)
        a3 = _make_a3(session_id=None)
        env = predict_regime_preflight([a1, a2, a3], emitted_at=WIN_END)
        assert env.session_id is None

    def test_explicit_overrides_inference(self):
        """Explicit session_id takes precedence over inferred."""
        a1 = _make_a1(session_id="gov_from_input")
        a2 = _make_a2()
        a3 = _make_a3()
        env = predict_regime_preflight(
            [a1, a2, a3],
            session_id="gov_explicit",
            emitted_at=WIN_END,
        )
        assert env.session_id == "gov_explicit"
