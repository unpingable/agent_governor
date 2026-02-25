# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.4 Phase A2: SILENT_SUPPRESSION derivation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    QualityStatus,
    DerivationType,
    SignalEnvelope,
    validate_envelope,
)
from governor.signals.silent_suppression import (
    CLASSIFICATION_HEALTHY,
    CLASSIFICATION_IDLE,
    CLASSIFICATION_INDETERMINATE,
    CLASSIFICATION_LIKELY_SUPPRESSED,
    SuppressionIndicators,
    classify_suppression,
    derive_silent_suppression,
)

FIXTURES = Path(__file__).parent / "fixtures" / "signals"

# ── Common helpers ───────────────────────────────────────────────────────────

WINDOW_START = "2026-02-24T17:40:00Z"
WINDOW_END = "2026-02-24T17:45:00Z"
WINDOW_KIND = "rolling_5m"


def make_envelope(**overrides) -> SignalEnvelope:
    defaults = dict(
        indicators=SuppressionIndicators(
            expected_heartbeat_count=5,
            observed_heartbeat_count=5,
            expected_event_markers=10,
            observed_event_markers=8,
            daemon_reachable=True,
            in_path_evidence_present=True,
            activity_observed=True,
        ),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        window_kind=WINDOW_KIND,
        emitter_version="test-v1",
        emitted_at="2026-02-24T17:42:11Z",
    )
    defaults.update(overrides)
    return derive_silent_suppression(**defaults)


# ── SuppressionIndicators ───────────────────────────────────────────────────

class TestSuppressionIndicators:
    def test_defaults_all_false_zero(self):
        ind = SuppressionIndicators()
        assert not ind.has_expectation()
        assert not ind.has_evidence()

    def test_has_expectation_from_activity(self):
        ind = SuppressionIndicators(activity_observed=True)
        assert ind.has_expectation()

    def test_has_expectation_from_expected_markers(self):
        ind = SuppressionIndicators(expected_event_markers=3)
        assert ind.has_expectation()

    def test_has_expectation_from_heartbeat(self):
        ind = SuppressionIndicators(expected_heartbeat_count=1)
        assert ind.has_expectation()

    def test_has_evidence_from_receipts(self):
        ind = SuppressionIndicators(in_path_evidence_present=True)
        assert ind.has_evidence()

    def test_has_evidence_from_observed_markers(self):
        ind = SuppressionIndicators(observed_event_markers=1)
        assert ind.has_evidence()

    def test_has_evidence_from_heartbeat(self):
        ind = SuppressionIndicators(observed_heartbeat_count=1)
        assert ind.has_evidence()

    def test_frozen(self):
        ind = SuppressionIndicators()
        with pytest.raises(AttributeError):
            ind.activity_observed = True  # type: ignore[misc]


# ── classify_suppression ────────────────────────────────────────────────────

class TestClassifySuppression:
    def test_idle_no_activity_no_evidence(self):
        """No activity, no evidence → idle."""
        ind = SuppressionIndicators()
        assert classify_suppression(ind) == CLASSIFICATION_IDLE

    def test_healthy_expectation_and_evidence(self):
        """Both sides reporting → healthy."""
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            observed_event_markers=5,
            daemon_reachable=True,
            in_path_evidence_present=True,
        )
        assert classify_suppression(ind) == CLASSIFICATION_HEALTHY

    def test_healthy_evidence_without_expectation(self):
        """Governor producing evidence without external demand → healthy."""
        ind = SuppressionIndicators(
            in_path_evidence_present=True,
            observed_event_markers=3,
        )
        assert classify_suppression(ind) == CLASSIFICATION_HEALTHY

    def test_likely_suppressed_activity_no_evidence(self):
        """Active callers but no governor evidence → likely suppressed."""
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=True,
        )
        assert classify_suppression(ind) == CLASSIFICATION_LIKELY_SUPPRESSED

    def test_likely_suppressed_daemon_unreachable(self):
        """Active callers, daemon unreachable → likely suppressed."""
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=False,
        )
        assert classify_suppression(ind) == CLASSIFICATION_LIKELY_SUPPRESSED

    def test_idle_is_not_suppression(self):
        """Critical invariant: no activity is NOT suppression."""
        ind = SuppressionIndicators()
        classification = classify_suppression(ind)
        assert classification != CLASSIFICATION_LIKELY_SUPPRESSED
        assert classification == CLASSIFICATION_IDLE


# ── derive_silent_suppression ───────────────────────────────────────────────

class TestDeriveSilentSuppression:
    """Core derivation tests."""

    def test_produces_signal_envelope(self):
        env = make_envelope()
        assert isinstance(env, SignalEnvelope)

    def test_signal_identity(self):
        env = make_envelope()
        assert env.signal_id == "SILENT_SUPPRESSION"
        assert env.signal_version == 1
        assert env.phase == "2.4A"

    def test_derivation_metadata(self):
        env = make_envelope()
        assert env.derivation == DerivationType.WINDOWED_AGGREGATE.value
        assert env.derivation_version == "silent-suppression-v1"

    def test_window_fields(self):
        env = make_envelope()
        assert env.window_start == WINDOW_START
        assert env.window_end == WINDOW_END
        assert env.window_kind == WINDOW_KIND

    def test_subject_type_is_runtime(self):
        env = make_envelope()
        assert env.subject_type == "runtime"

    def test_unit_is_ratio(self):
        env = make_envelope()
        assert env.unit == "ratio"

    def test_validates_cleanly(self):
        env = make_envelope()
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"


# ── Idle window ─────────────────────────────────────────────────────────────

class TestIdleWindow:
    """No activity → unavailable, not suppressed."""

    def test_idle_value_is_none(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert env.value is None

    def test_idle_quality_unavailable(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_idle_reason(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert "no_activity_in_window" in env.quality_reasons

    def test_idle_classification_annotation(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert env.annotations["classification"] == CLASSIFICATION_IDLE

    def test_idle_completeness_none(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert env.completeness is None

    def test_idle_validates(self):
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        errors = validate_envelope(env)
        assert errors == []


# ── Healthy window ──────────────────────────────────────────────────────────

class TestHealthyWindow:
    """Active + evidence → healthy."""

    def test_healthy_value_is_one(self):
        env = make_envelope()
        assert env.value == 1.0

    def test_healthy_classification(self):
        env = make_envelope()
        assert env.annotations["classification"] == CLASSIFICATION_HEALTHY

    def test_healthy_validates(self):
        env = make_envelope()
        errors = validate_envelope(env)
        assert errors == []


# ── Active-but-dark (likely suppressed) ─────────────────────────────────────

class TestLikelySuppressed:
    """Active callers but no governor evidence → likely suppressed."""

    def test_suppressed_value_is_zero(self):
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=True,
        )
        env = make_envelope(indicators=ind)
        assert env.value == 0.0

    def test_suppressed_classification(self):
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=True,
        )
        env = make_envelope(indicators=ind)
        assert env.annotations["classification"] == CLASSIFICATION_LIKELY_SUPPRESSED

    def test_suppressed_daemon_unreachable(self):
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=False,
        )
        env = make_envelope(indicators=ind)
        assert env.value == 0.0
        assert env.annotations["classification"] == CLASSIFICATION_LIKELY_SUPPRESSED

    def test_suppression_detected_flag(self):
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
        )
        env = make_envelope(indicators=ind)
        assert env.values["suppression_detected"] == 1

    def test_suppressed_validates(self):
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
        )
        env = make_envelope(indicators=ind)
        errors = validate_envelope(env)
        assert errors == []

    def test_suppressed_not_unavailable(self):
        """Suppressed is a valid measurement (value=0), not unavailable."""
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
        )
        env = make_envelope(indicators=ind)
        assert env.quality_status != QualityStatus.UNAVAILABLE.value


# ── Missing != zero ─────────────────────────────────────────────────────────

class TestMissingNotZero:
    """Suppressed (value=0) and idle (value=None) are distinct."""

    def test_idle_is_none_not_zero(self):
        ind_idle = SuppressionIndicators()
        env = make_envelope(indicators=ind_idle)
        assert env.value is None

    def test_suppressed_is_zero_not_none(self):
        ind_dark = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
        )
        env = make_envelope(indicators=ind_dark)
        assert env.value == 0.0

    def test_idle_and_suppressed_distinct(self):
        ind_idle = SuppressionIndicators()
        ind_dark = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
        )
        env_idle = make_envelope(indicators=ind_idle)
        env_dark = make_envelope(indicators=ind_dark)

        assert env_idle.value is None
        assert env_dark.value == 0.0
        assert env_idle.quality_status == QualityStatus.UNAVAILABLE.value
        assert env_dark.quality_status != QualityStatus.UNAVAILABLE.value

    def test_healthy_is_one(self):
        env = make_envelope()
        assert env.value == 1.0


# ── Anti-self-attestation ───────────────────────────────────────────────────

class TestAntiSelfAttestation:
    """Daemon self-report alone is insufficient."""

    def test_daemon_reachable_alone_is_not_healthy(self):
        """daemon_reachable=True without external expectation/evidence."""
        ind = SuppressionIndicators(daemon_reachable=True)
        classification = classify_suppression(ind)
        # daemon_reachable alone doesn't create expectation or evidence
        assert classification == CLASSIFICATION_IDLE

    def test_daemon_reachable_plus_activity_but_no_evidence(self):
        """Daemon says it's reachable, callers are active, but no receipts."""
        ind = SuppressionIndicators(
            daemon_reachable=True,
            activity_observed=True,
            expected_event_markers=5,
        )
        classification = classify_suppression(ind)
        assert classification == CLASSIFICATION_LIKELY_SUPPRESSED

    def test_evidence_requires_receipts_not_just_daemon(self):
        """in_path_evidence_present comes from receipts, not daemon liveness."""
        # With receipts → healthy
        ind_with = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            in_path_evidence_present=True,
        )
        assert classify_suppression(ind_with) == CLASSIFICATION_HEALTHY

        # Without receipts → suppressed
        ind_without = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=True,
        )
        assert classify_suppression(ind_without) == CLASSIFICATION_LIKELY_SUPPRESSED


# ── Partial quality (degraded indicator coverage) ───────────────────────────

class TestPartialQuality:
    """Partial quality when not all indicator sources contribute."""

    def test_all_sources_yield_ok(self):
        """All 3 indicator source groups active → ok."""
        env = make_envelope()  # has heartbeat, markers, and activity
        assert env.quality_status == QualityStatus.OK.value

    def test_missing_heartbeat_yields_partial(self):
        """No heartbeat data → partial."""
        ind = SuppressionIndicators(
            expected_event_markers=5,
            observed_event_markers=5,
            activity_observed=True,
            in_path_evidence_present=True,
            daemon_reachable=True,
        )
        env = make_envelope(indicators=ind)
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert any("2/3 sources" in r for r in env.quality_reasons)

    def test_only_activity_yields_partial(self):
        """Only activity_observed indicator → partial."""
        ind = SuppressionIndicators(
            activity_observed=True,
            expected_event_markers=5,
            daemon_reachable=True,
        )
        env = make_envelope(indicators=ind)
        # likely_suppressed + partial (only activity + markers, no heartbeat)
        assert env.quality_status == QualityStatus.PARTIAL.value

    def test_partial_validates(self):
        ind = SuppressionIndicators(
            expected_event_markers=5,
            observed_event_markers=5,
            activity_observed=True,
            in_path_evidence_present=True,
        )
        env = make_envelope(indicators=ind)
        errors = validate_envelope(env)
        assert errors == []

    def test_idle_is_unavailable_not_partial(self):
        """Idle windows don't get partial — they're unavailable."""
        ind = SuppressionIndicators()
        env = make_envelope(indicators=ind)
        assert env.quality_status == QualityStatus.UNAVAILABLE.value


# ── Values dict (all indicators for auditability) ──────────────────────────

class TestValuesDict:
    def test_all_indicator_fields_present(self):
        env = make_envelope()
        v = env.values
        assert "expected_heartbeat_count" in v
        assert "observed_heartbeat_count" in v
        assert "expected_event_markers" in v
        assert "observed_event_markers" in v
        assert "daemon_reachable" in v
        assert "in_path_evidence_present" in v
        assert "activity_observed" in v
        assert "suppression_detected" in v

    def test_boolean_fields_encoded_as_int(self):
        env = make_envelope()
        assert env.values["daemon_reachable"] in (0, 1)
        assert env.values["in_path_evidence_present"] in (0, 1)
        assert env.values["activity_observed"] in (0, 1)
        assert env.values["suppression_detected"] in (0, 1)

    def test_healthy_suppression_detected_zero(self):
        env = make_envelope()
        assert env.values["suppression_detected"] == 0


# ── Classification annotation ──────────────────────────────────────────────

class TestClassificationAnnotation:
    """classification lives in annotations, not quality_status."""

    def test_classification_always_present(self):
        for ind in [
            SuppressionIndicators(),  # idle
            SuppressionIndicators(activity_observed=True,  # healthy
                                   in_path_evidence_present=True),
            SuppressionIndicators(activity_observed=True,  # suppressed
                                   expected_event_markers=5),
        ]:
            env = make_envelope(indicators=ind)
            assert "classification" in env.annotations

    def test_classification_is_string(self):
        env = make_envelope()
        assert isinstance(env.annotations["classification"], str)


# ── Envelope shape compliance ───────────────────────────────────────────────

class TestEnvelopeShape:
    def test_schema_version(self):
        env = make_envelope()
        assert env.schema_version == CURRENT_SCHEMA_VERSION

    def test_round_trip_json(self):
        env = make_envelope()
        d = env.to_dict()
        recovered = SignalEnvelope.from_dict(d)
        assert recovered == env

    def test_content_hash_deterministic(self):
        env = make_envelope()
        assert env.content_hash() == env.content_hash()

    def test_session_id_passthrough(self):
        env = make_envelope(session_id="sess_test")
        assert env.session_id == "sess_test"

    def test_source_receipt_ids_passthrough(self):
        env = make_envelope(source_receipt_ids=["r1", "r2"])
        assert env.source_receipt_ids == ["r1", "r2"]


# ── Golden fixture round-trip ───────────────────────────────────────────────

class TestGoldenFixture:
    """Verify the existing golden fixture is compatible."""

    def test_golden_fixture_parses(self):
        data = json.loads(
            (FIXTURES / "envelope_unavailable_silent_suppression.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "SILENT_SUPPRESSION"

    def test_golden_fixture_validates(self):
        data = json.loads(
            (FIXTURES / "envelope_unavailable_silent_suppression.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_fixture_is_unavailable(self):
        """Golden fixture represents idle window → unavailable."""
        data = json.loads(
            (FIXTURES / "envelope_unavailable_silent_suppression.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
