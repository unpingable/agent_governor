# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.4 Phase A0: SignalEnvelope model, validation, serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    canonical_json,
    content_hash,
    validate_envelope,
)

FIXTURES = Path(__file__).parent / "fixtures" / "signals"


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_envelope(**overrides) -> SignalEnvelope:
    """Minimal valid envelope with sensible defaults."""
    defaults = dict(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at="2026-02-24T17:42:11Z",
        emitter="governor.test",
        emitter_version="0.0.1",
        signal_id="TEST_SIGNAL",
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        value=1.0,
        unit="count",
        quality_status="ok",
        derivation="direct",
        derivation_version="test-v1",
    )
    defaults.update(overrides)
    return SignalEnvelope(**defaults)


# ── QualityStatus enum ───────────────────────────────────────────────────────

class TestQualityStatus:
    def test_values(self):
        assert QualityStatus.OK.value == "ok"
        assert QualityStatus.PARTIAL.value == "partial"
        assert QualityStatus.UNAVAILABLE.value == "unavailable"
        assert QualityStatus.INVALID.value == "invalid"

    def test_string_comparison(self):
        assert QualityStatus.OK == "ok"

    def test_all_four_statuses(self):
        assert len(QualityStatus) == 4


# ── DerivationType enum ─────────────────────────────────────────────────────

class TestDerivationType:
    def test_values(self):
        assert DerivationType.DIRECT.value == "direct"
        assert DerivationType.WINDOWED_AGGREGATE.value == "windowed_aggregate"
        assert DerivationType.DERIVED.value == "derived"

    def test_all_three(self):
        assert len(DerivationType) == 3


# ── SignalEnvelope construction ──────────────────────────────────────────────

class TestSignalEnvelopeConstruction:
    def test_minimal_valid(self):
        env = make_envelope()
        assert env.signal_id == "TEST_SIGNAL"
        assert env.schema_version == CURRENT_SCHEMA_VERSION

    def test_frozen(self):
        env = make_envelope()
        with pytest.raises(AttributeError):
            env.value = 99.0  # type: ignore[misc]

    def test_defaults(self):
        env = make_envelope()
        assert env.subject_id is None
        assert env.correlation_id is None
        assert env.session_id is None
        assert env.window_start is None
        assert env.window_end is None
        assert env.window_kind is None
        assert env.values == {}
        assert env.quality_reasons == []
        assert env.sample_size is None
        assert env.completeness is None
        assert env.source_receipt_ids == []
        assert env.source_streams == []
        assert env.source_versions == {}
        assert env.annotations == {}

    def test_all_fields_populated(self):
        env = SignalEnvelope(
            schema_version="0.4.0",
            emitted_at="2026-02-24T17:42:11Z",
            emitter="governor.daemon",
            emitter_version="2.4.0-dev",
            signal_id="EXPOSURE_PROXY",
            signal_version=1,
            phase="2.4A",
            subject_type="window",
            subject_id="win_001",
            correlation_id="corr_001",
            session_id="sess_001",
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
            window_kind="rolling_5m",
            value=18.5,
            unit="exposure_points",
            values={"eligible_events": 14},
            quality_status="ok",
            quality_reasons=[],
            sample_size=16,
            completeness=1.0,
            source_receipt_ids=["rcpt_001"],
            source_streams=["preflight"],
            source_versions={"governor.daemon": "2.4.0-dev"},
            derivation="windowed_aggregate",
            derivation_version="exposure-proxy-v1",
            annotations={"weight_set_id": "default-v1"},
        )
        assert env.value == 18.5
        assert env.values["eligible_events"] == 14
        assert env.source_receipt_ids == ["rcpt_001"]


# ── Serialization round-trip ─────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_round_trip(self):
        env = make_envelope(values={"x": 1}, annotations={"note": "test"})
        d = env.to_dict()
        env2 = SignalEnvelope.from_dict(d)
        assert env == env2

    def test_to_json_round_trip(self):
        env = make_envelope(value=3.14, unit="ratio")
        text = env.to_json()
        env2 = SignalEnvelope.from_json(text)
        assert env == env2

    def test_from_dict_ignores_unknown_keys(self):
        d = make_envelope().to_dict()
        d["future_field"] = "v3_data"
        env = SignalEnvelope.from_dict(d)
        assert env.signal_id == "TEST_SIGNAL"

    def test_none_values_in_json(self):
        env = make_envelope(value=None, quality_status="unavailable")
        text = env.to_json()
        parsed = json.loads(text)
        assert parsed["value"] is None
        env2 = SignalEnvelope.from_json(text)
        assert env2.value is None


# ── Canonical JSON + hashing ─────────────────────────────────────────────────

class TestCanonicalJson:
    def test_deterministic(self):
        env = make_envelope(values={"b": 2, "a": 1})
        b1 = env.to_canonical_bytes()
        b2 = env.to_canonical_bytes()
        assert b1 == b2

    def test_sorted_keys(self):
        env = make_envelope(values={"zebra": 1, "alpha": 2})
        text = env.to_canonical_bytes().decode()
        assert text.index('"alpha"') < text.index('"zebra"')

    def test_content_hash_stable(self):
        env = make_envelope()
        h1 = env.content_hash()
        h2 = env.content_hash()
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_content_hash_changes_with_value(self):
        env1 = make_envelope(value=1.0)
        env2 = make_envelope(value=2.0)
        assert env1.content_hash() != env2.content_hash()

    def test_values_hash(self):
        env = make_envelope(values={"x": 42})
        h = env.values_hash()
        assert h.startswith("sha256:")

    def test_values_hash_independent_of_envelope(self):
        """values_hash should only depend on the values dict."""
        env1 = make_envelope(value=1.0, values={"x": 42})
        env2 = make_envelope(value=2.0, values={"x": 42})
        assert env1.values_hash() == env2.values_hash()

    def test_canonical_json_no_spaces(self):
        data = {"a": 1, "b": [2, 3]}
        result = canonical_json(data).decode()
        assert " " not in result

    def test_content_hash_function(self):
        h = content_hash(b"hello")
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars


# ── Validation ───────────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_envelope_no_errors(self):
        env = make_envelope()
        assert validate_envelope(env) == []

    def test_missing_required_string_fields(self):
        for field_name in (
            "schema_version", "emitted_at", "emitter", "emitter_version",
            "signal_id", "phase", "subject_type", "derivation",
            "derivation_version",
        ):
            env = make_envelope(**{field_name: ""})
            errors = validate_envelope(env)
            assert any(field_name in e for e in errors), f"Expected error for {field_name}"

    def test_signal_version_must_be_positive(self):
        env = make_envelope(signal_version=0)
        errors = validate_envelope(env)
        assert any("signal_version" in e for e in errors)

    def test_signal_version_negative(self):
        env = make_envelope(signal_version=-1)
        errors = validate_envelope(env)
        assert any("signal_version" in e for e in errors)

    def test_invalid_quality_status(self):
        env = make_envelope(quality_status="bogus")
        errors = validate_envelope(env)
        assert any("quality_status" in e for e in errors)

    def test_invalid_derivation(self):
        env = make_envelope(derivation="magic")
        errors = validate_envelope(env)
        assert any("derivation" in e for e in errors)

    def test_ok_requires_value_or_values(self):
        """quality_status='ok' with no value and no values is invalid."""
        env = make_envelope(quality_status="ok", value=None, values={})
        errors = validate_envelope(env)
        assert any("requires" in e for e in errors)

    def test_ok_with_only_values_dict(self):
        """quality_status='ok' with values dict but no scalar value is fine."""
        env = make_envelope(quality_status="ok", value=None, values={"x": 1})
        errors = validate_envelope(env)
        assert errors == []

    def test_ok_with_only_scalar_value(self):
        """quality_status='ok' with scalar value but empty values is fine."""
        env = make_envelope(quality_status="ok", value=5.0, values={})
        errors = validate_envelope(env)
        assert errors == []

    # ── missing != zero ──────────────────────────────────────────────────

    def test_unavailable_with_value_zero_is_error(self):
        """Conflating zero with missing is the exact anti-pattern we guard against."""
        env = make_envelope(quality_status="unavailable", value=0.0)
        errors = validate_envelope(env)
        assert any("zero" in e.lower() or "0.0" in e for e in errors)

    def test_unavailable_with_value_none_is_valid(self):
        env = make_envelope(quality_status="unavailable", value=None)
        errors = validate_envelope(env)
        assert errors == []

    def test_unavailable_with_nonzero_value_is_valid(self):
        """Rare edge case: partial result with unavailable status."""
        env = make_envelope(quality_status="unavailable", value=5.0)
        errors = validate_envelope(env)
        # No error for non-zero value with unavailable
        assert not any("zero" in e.lower() or "0.0" in e for e in errors)

    # ── Window fields ────────────────────────────────────────────────────

    def test_window_kind_requires_start_end(self):
        env = make_envelope(window_kind="rolling_5m", window_start=None, window_end=None)
        errors = validate_envelope(env)
        assert any("window" in e for e in errors)

    def test_window_kind_with_start_end_is_valid(self):
        env = make_envelope(
            window_kind="rolling_5m",
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        errors = validate_envelope(env)
        assert errors == []

    def test_no_window_kind_is_valid(self):
        """Point-in-time signals don't need window fields."""
        env = make_envelope(window_kind=None)
        errors = validate_envelope(env)
        assert errors == []

    # ── All quality statuses valid ───────────────────────────────────────

    def test_all_quality_statuses_accepted(self):
        for qs in QualityStatus:
            kwargs = {"quality_status": qs.value}
            if qs == QualityStatus.UNAVAILABLE:
                kwargs["value"] = None
            elif qs == QualityStatus.INVALID:
                kwargs["value"] = None
            env = make_envelope(**kwargs)
            errors = validate_envelope(env)
            # ok requires value, others don't — only check for status-specific errors
            status_errors = [e for e in errors if "quality_status" in e]
            assert status_errors == [], f"Unexpected quality_status error for {qs.value}"

    # ── All derivation types valid ───────────────────────────────────────

    def test_all_derivation_types_accepted(self):
        for dt in DerivationType:
            env = make_envelope(derivation=dt.value)
            errors = validate_envelope(env)
            deriv_errors = [e for e in errors if "derivation" in e]
            assert deriv_errors == [], f"Unexpected derivation error for {dt.value}"


# ── Golden fixture round-trips ───────────────────────────────────────────────

class TestGoldenFixtures:
    """Every golden fixture must parse, validate, and round-trip."""

    FIXTURE_FILES = [
        "envelope_ok_exposure_proxy.json",
        "envelope_partial_sigma_rate.json",
        "envelope_unavailable_silent_suppression.json",
        "envelope_invalid_sigma_rate.json",
    ]

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_parses(self, filename):
        path = FIXTURES / filename
        assert path.exists(), f"Missing fixture: {path}"
        data = json.loads(path.read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id in ("EXPOSURE_PROXY", "SIGMA_RATE", "SILENT_SUPPRESSION")

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_validates(self, filename):
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors in {filename}: {errors}"

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_round_trips(self, filename):
        """Parse → to_dict → from_dict → compare."""
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        d = env.to_dict()
        env2 = SignalEnvelope.from_dict(d)
        assert env == env2

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_json_round_trip(self, filename):
        """Parse → to_json → from_json → compare."""
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        text = env.to_json()
        env2 = SignalEnvelope.from_json(text)
        assert env == env2

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_has_provenance(self, filename):
        """Every fixture must have versioning/provenance fields."""
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.emitter_version
        assert env.signal_version >= 1
        assert env.derivation_version
        assert isinstance(env.source_versions, dict)

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_has_quality_reasons_list(self, filename):
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        assert isinstance(env.quality_reasons, list)

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_fixture_schema_version(self, filename):
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.schema_version == CURRENT_SCHEMA_VERSION

    def test_ok_fixture_has_value(self):
        data = json.loads((FIXTURES / "envelope_ok_exposure_proxy.json").read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "ok"
        assert env.value is not None
        assert env.value == 18.5

    def test_unavailable_fixture_has_null_value(self):
        data = json.loads(
            (FIXTURES / "envelope_unavailable_silent_suppression.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "unavailable"
        assert env.value is None

    def test_partial_fixture_has_degraded_completeness(self):
        data = json.loads((FIXTURES / "envelope_partial_sigma_rate.json").read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "partial"
        assert env.completeness is not None
        assert env.completeness < 1.0

    def test_invalid_fixture_has_null_value(self):
        data = json.loads((FIXTURES / "envelope_invalid_sigma_rate.json").read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "invalid"
        assert env.value is None

    def test_ok_fixture_window_fields_present(self):
        data = json.loads((FIXTURES / "envelope_ok_exposure_proxy.json").read_text())
        env = SignalEnvelope.from_dict(data)
        assert env.window_kind is not None
        assert env.window_start is not None
        assert env.window_end is not None

    def test_unavailable_idle_is_not_suppression(self):
        """The critical invariant: idle window emits unavailable, not value=0."""
        data = json.loads(
            (FIXTURES / "envelope_unavailable_silent_suppression.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.value is None
        assert "no_activity_in_window" in env.quality_reasons
        assert env.annotations.get("classification") == "idle"


# ── Content hash stability ───────────────────────────────────────────────────

class TestContentHashStability:
    """Hashes must be deterministic across runs."""

    def test_fixture_hash_deterministic(self):
        data = json.loads((FIXTURES / "envelope_ok_exposure_proxy.json").read_text())
        env = SignalEnvelope.from_dict(data)
        h1 = env.content_hash()
        h2 = env.content_hash()
        assert h1 == h2

    def test_different_fixtures_different_hashes(self):
        hashes = set()
        for f in TestGoldenFixtures.FIXTURE_FILES:
            data = json.loads((FIXTURES / f).read_text())
            env = SignalEnvelope.from_dict(data)
            hashes.add(env.content_hash())
        assert len(hashes) == len(TestGoldenFixtures.FIXTURE_FILES)
