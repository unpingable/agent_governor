# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.4 Phase A1: EXPOSURE_PROXY derivation."""

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
from governor.signals.exposure_proxy import (
    DEFAULT_WEIGHT_SET_ID,
    DEFAULT_WEIGHTS,
    ExposureComponents,
    compute_exposure_points,
    count_from_receipts,
    derive_exposure_proxy,
)

FIXTURES = Path(__file__).parent / "fixtures" / "signals"

# ── Common test helpers ──────────────────────────────────────────────────────

WINDOW_START = "2026-02-24T17:40:00Z"
WINDOW_END = "2026-02-24T17:45:00Z"
WINDOW_KIND = "rolling_5m"


def make_components(**overrides) -> ExposureComponents:
    """All 4 streams active → quality_status="ok" by default."""
    defaults = dict(
        tool_dispatch_attempts=8,
        chat_generation_calls=4,
        evidence_checks=5,
        violation_evaluations=3,
    )
    defaults.update(overrides)
    return ExposureComponents(**defaults)


def make_envelope(**overrides) -> SignalEnvelope:
    """Derive an exposure proxy envelope with sane defaults."""
    defaults = dict(
        components=make_components(),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        window_kind=WINDOW_KIND,
        emitter_version="test-v1",
        emitted_at="2026-02-24T17:42:11Z",
    )
    defaults.update(overrides)
    return derive_exposure_proxy(**defaults)


def _make_receipt(receipt_id, gate, verdict="pass", timestamp="2026-02-24T17:42:11Z"):
    """Helper to create a GateReceipt for testing."""
    from governor.gate_receipt import GateReceipt
    return GateReceipt(
        receipt_id=receipt_id,
        schema_version=3,
        timestamp=timestamp,
        gate=gate,
        verdict=verdict,
        subject_hash="abc",
        evidence_hash="def",
        policy_hash="ghi",
    )


# ── ExposureComponents ──────────────────────────────────────────────────────

class TestExposureComponents:
    def test_total_sums_all_fields(self):
        c = ExposureComponents(
            tool_dispatch_attempts=3,
            chat_generation_calls=2,
            evidence_checks=1,
            violation_evaluations=4,
        )
        assert c.total == 10

    def test_total_default_is_zero(self):
        c = ExposureComponents()
        assert c.total == 0

    def test_has_any_true_when_nonzero(self):
        c = ExposureComponents(tool_dispatch_attempts=1)
        assert c.has_any()

    def test_has_any_false_when_all_zero(self):
        c = ExposureComponents()
        assert not c.has_any()

    def test_active_stream_count(self):
        c = ExposureComponents(
            tool_dispatch_attempts=5,
            evidence_checks=3,
        )
        assert c.active_stream_count() == 2

    def test_active_stream_count_all(self):
        c = make_components()
        assert c.active_stream_count() == 4

    def test_to_values_dict(self):
        c = ExposureComponents(
            tool_dispatch_attempts=8,
            chat_generation_calls=4,
            evidence_checks=5,
            violation_evaluations=3,
        )
        d = c.to_values_dict()
        assert d["component_tool_dispatch_attempts"] == 8
        assert d["component_chat_generation_calls"] == 4
        assert d["component_evidence_checks"] == 5
        assert d["component_violation_evaluations"] == 3

    def test_frozen(self):
        c = ExposureComponents(tool_dispatch_attempts=1)
        with pytest.raises(AttributeError):
            c.tool_dispatch_attempts = 2  # type: ignore[misc]


# ── compute_exposure_points ─────────────────────────────────────────────────

class TestComputeExposurePoints:
    def test_default_weights(self):
        c = ExposureComponents(
            tool_dispatch_attempts=10,
            chat_generation_calls=10,
            evidence_checks=10,
            violation_evaluations=10,
        )
        expected = (
            10 * 1.0   # tool_dispatch
            + 10 * 0.5 # chat_generation
            + 10 * 0.8 # evidence_checks
            + 10 * 1.0 # violation_evaluations
        )
        assert compute_exposure_points(c) == expected
        assert expected == 33.0

    def test_custom_weights(self):
        c = ExposureComponents(tool_dispatch_attempts=5)
        custom = {"tool_dispatch": 2.0}
        assert compute_exposure_points(c, weights=custom) == 10.0

    def test_zero_components_returns_zero(self):
        c = ExposureComponents()
        assert compute_exposure_points(c) == 0.0

    def test_single_component(self):
        c = ExposureComponents(evidence_checks=10)
        assert compute_exposure_points(c) == 10 * 0.8

    def test_missing_weight_key_defaults_to_zero(self):
        c = ExposureComponents(tool_dispatch_attempts=5)
        # Empty weight dict — no keys match
        assert compute_exposure_points(c, weights={}) == 0.0

    def test_known_computation(self):
        """Regression test with known values."""
        c = ExposureComponents(
            tool_dispatch_attempts=8,
            chat_generation_calls=4,
            evidence_checks=5,
            violation_evaluations=3,
        )
        expected = 8 * 1.0 + 4 * 0.5 + 5 * 0.8 + 3 * 1.0
        assert compute_exposure_points(c) == expected
        assert expected == 17.0


# ── derive_exposure_proxy ───────────────────────────────────────────────────

class TestDeriveExposureProxy:
    """Core derivation tests."""

    def test_produces_signal_envelope(self):
        env = make_envelope()
        assert isinstance(env, SignalEnvelope)

    def test_signal_identity(self):
        env = make_envelope()
        assert env.signal_id == "EXPOSURE_PROXY"
        assert env.signal_version == 1
        assert env.phase == "2.4A"

    def test_derivation_metadata(self):
        env = make_envelope()
        assert env.derivation == DerivationType.WINDOWED_AGGREGATE.value
        assert env.derivation_version == "exposure-proxy-v1"

    def test_window_fields(self):
        env = make_envelope()
        assert env.window_start == WINDOW_START
        assert env.window_end == WINDOW_END
        assert env.window_kind == WINDOW_KIND
        assert env.subject_type == "window"

    def test_subject_id_encodes_window(self):
        env = make_envelope()
        assert env.subject_id == f"win_{WINDOW_START}_{WINDOW_KIND}"

    def test_unit_is_exposure_points(self):
        env = make_envelope()
        assert env.unit == "exposure_points"

    def test_value_is_weighted_sum(self):
        c = ExposureComponents(
            tool_dispatch_attempts=8,
            chat_generation_calls=4,
            evidence_checks=5,
            violation_evaluations=3,
        )
        env = make_envelope(components=c)
        expected = 8 * 1.0 + 4 * 0.5 + 5 * 0.8 + 3 * 1.0
        assert env.value == expected

    def test_values_dict_has_all_submetrics(self):
        env = make_envelope()
        v = env.values
        assert "exposure_points_total" in v
        assert "eligible_events" in v
        assert "excluded_events" in v
        assert "weighted_event_count" in v
        assert "coverage_ratio" in v
        assert "source_event_count" in v
        assert "component_tool_dispatch_attempts" in v
        assert "component_chat_generation_calls" in v
        assert "component_evidence_checks" in v
        assert "component_violation_evaluations" in v

    def test_eligible_events_equals_component_total(self):
        c = make_components()
        env = make_envelope(components=c)
        assert env.values["eligible_events"] == c.total

    def test_source_event_count_includes_excluded(self):
        env = make_envelope(excluded_events=3)
        c = make_components()
        assert env.values["source_event_count"] == c.total + 3

    def test_annotations_include_weight_set_id(self):
        env = make_envelope()
        assert env.annotations["weight_set_id"] == DEFAULT_WEIGHT_SET_ID

    def test_custom_weight_set_id(self):
        env = make_envelope(weight_set_id="custom-v2")
        assert env.annotations["weight_set_id"] == "custom-v2"

    def test_excluded_reasons_in_annotations(self):
        reasons = {"non_governed_ui_event": 2, "test_excluded": 1}
        env = make_envelope(excluded_events=3, excluded_reasons=reasons)
        assert env.annotations["excluded_reason_counts"] == reasons

    def test_no_excluded_reasons_omits_key(self):
        env = make_envelope()
        assert "excluded_reason_counts" not in env.annotations

    def test_session_id_passthrough(self):
        env = make_envelope(session_id="sess_123")
        assert env.session_id == "sess_123"

    def test_source_receipt_ids_passthrough(self):
        ids = ["rcpt_1", "rcpt_2"]
        env = make_envelope(source_receipt_ids=ids)
        assert env.source_receipt_ids == ids

    def test_source_streams_passthrough(self):
        streams = ["preflight", "dispatch"]
        env = make_envelope(source_streams=streams)
        assert env.source_streams == streams

    def test_source_versions_passthrough(self):
        versions = {"governor.daemon": "2.4.0-dev"}
        env = make_envelope(source_versions=versions)
        assert env.source_versions == versions

    def test_validates_cleanly(self):
        env = make_envelope()
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"


# ── Custom weights ──────────────────────────────────────────────────────────

class TestCustomWeights:
    def test_custom_weights_change_value(self):
        c = ExposureComponents(tool_dispatch_attempts=10)
        env1 = make_envelope(components=c)
        env2 = make_envelope(
            components=c,
            weights={"tool_dispatch": 2.0},
            weight_set_id="double-v1",
        )
        assert env1.value == 10.0
        assert env2.value == 20.0

    def test_zero_weights_yield_zero_value(self):
        """value=0 with events is a valid measurement (not unavailable)."""
        c = make_components()  # all 4 streams active → ok quality
        env = make_envelope(
            components=c,
            weights={
                "tool_dispatch": 0.0,
                "chat_generation": 0.0,
                "evidence_checks": 0.0,
                "violation_evaluations": 0.0,
            },
        )
        assert env.value == 0.0
        assert env.quality_status == QualityStatus.OK.value


# ── Quality semantics ───────────────────────────────────────────────────────

class TestQualitySemantics:
    """Missing != zero invariant for EXPOSURE_PROXY."""

    def test_no_events_yields_unavailable(self):
        """No events at all → value=None, quality=unavailable."""
        c = ExposureComponents()  # all zeros
        env = make_envelope(components=c, excluded_events=0)
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        assert "no_events_in_window" in env.quality_reasons

    def test_no_events_has_null_completeness(self):
        c = ExposureComponents()
        env = make_envelope(components=c, excluded_events=0)
        assert env.completeness is None
        assert env.sample_size is None

    def test_unavailable_validates(self):
        """Unavailable envelope passes validation."""
        c = ExposureComponents()
        env = make_envelope(components=c, excluded_events=0)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_all_streams_active_yields_ok(self):
        """All 4 component streams active → ok."""
        env = make_envelope()  # make_components() has all 4
        assert env.quality_status == QualityStatus.OK.value
        assert env.quality_reasons == []

    def test_ok_has_completeness_one(self):
        env = make_envelope()  # all 4 streams
        assert env.completeness == 1.0

    def test_ok_has_sample_size(self):
        c = make_components()
        env = make_envelope(components=c, excluded_events=2)
        assert env.sample_size == c.total + 2

    def test_zero_exposure_with_events_is_not_unavailable(self):
        """Events exist but all yield zero weight → NOT unavailable.

        This is the critical missing != zero invariant:
        zero means "observed absence of exposure", not "couldn't compute".
        """
        c = ExposureComponents(tool_dispatch_attempts=5)
        env = make_envelope(
            components=c,
            weights={"tool_dispatch": 0.0},
        )
        assert env.value == 0.0
        assert env.quality_status != QualityStatus.UNAVAILABLE.value

    def test_only_excluded_events_is_ok(self):
        """All events excluded but some existed → value=0, quality=ok.

        We had opportunity, nothing qualified. That's a valid zero.
        """
        c = ExposureComponents()  # no eligible events
        env = make_envelope(components=c, excluded_events=5)
        assert env.value == 0.0
        assert env.quality_status == QualityStatus.OK.value

    def test_unavailable_zero_not_confused(self):
        """Explicit test: unavailable and zero are distinct states."""
        c_none = ExposureComponents()
        env_unavailable = make_envelope(components=c_none, excluded_events=0)

        # Use all 4 streams at zero weight for a clean ok-quality zero
        c_zero = make_components()
        env_zero = make_envelope(
            components=c_zero,
            weights={
                "tool_dispatch": 0.0,
                "chat_generation": 0.0,
                "evidence_checks": 0.0,
                "violation_evaluations": 0.0,
            },
        )

        assert env_unavailable.value is None
        assert env_zero.value == 0.0
        assert env_unavailable.quality_status == QualityStatus.UNAVAILABLE.value
        assert env_zero.quality_status == QualityStatus.OK.value


# ── Coverage / partial quality signaling ────────────────────────────────────

class TestCoverageSignaling:
    """Partial quality when not all expected streams contribute data."""

    def test_single_stream_yields_partial(self):
        """Only 1 of 4 streams active → partial."""
        c = ExposureComponents(tool_dispatch_attempts=5)
        env = make_envelope(components=c)
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert env.completeness == 1 / 4

    def test_two_streams_yield_partial(self):
        c = ExposureComponents(tool_dispatch_attempts=3, evidence_checks=2)
        env = make_envelope(components=c)
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert env.completeness == 2 / 4

    def test_three_streams_yield_partial(self):
        c = ExposureComponents(
            tool_dispatch_attempts=3,
            evidence_checks=2,
            violation_evaluations=1,
        )
        env = make_envelope(components=c)
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert env.completeness == 3 / 4

    def test_all_streams_yield_ok(self):
        env = make_envelope()  # all 4 active
        assert env.quality_status == QualityStatus.OK.value
        assert env.completeness == 1.0

    def test_partial_quality_reasons_mention_stream_count(self):
        c = ExposureComponents(tool_dispatch_attempts=5)
        env = make_envelope(components=c)
        assert any("1/4 streams" in r for r in env.quality_reasons)

    def test_partial_validates(self):
        c = ExposureComponents(tool_dispatch_attempts=5)
        env = make_envelope(components=c)
        errors = validate_envelope(env)
        assert errors == []

    def test_only_excluded_events_yields_ok_not_partial(self):
        """Zero eligible but excluded events present → ok, not partial.

        Coverage is about eligible stream presence, and with no eligible
        events the stream count is zero (but source_count > 0 makes it
        computable). This is a valid zero, not a coverage problem.
        """
        c = ExposureComponents()
        env = make_envelope(components=c, excluded_events=5)
        assert env.quality_status == QualityStatus.OK.value

    def test_coverage_ratio_in_values(self):
        c = ExposureComponents(tool_dispatch_attempts=5, evidence_checks=3)
        env = make_envelope(components=c)
        assert env.values["coverage_ratio"] == 2 / 4


# ── Weight versioning ───────────────────────────────────────────────────────

class TestWeightVersioning:
    """Weights must be explicit and versioned — no hidden magic."""

    def test_default_weight_set_id_in_annotations(self):
        env = make_envelope()
        assert env.annotations["weight_set_id"] == "default-v1"

    def test_weight_set_id_follows_custom_weights(self):
        env = make_envelope(
            weights={"tool_dispatch": 99.0},
            weight_set_id="experiment-v3",
        )
        assert env.annotations["weight_set_id"] == "experiment-v3"

    def test_default_weights_are_documented(self):
        """All component keys are present in DEFAULT_WEIGHTS."""
        assert "tool_dispatch" in DEFAULT_WEIGHTS
        assert "chat_generation" in DEFAULT_WEIGHTS
        assert "evidence_checks" in DEFAULT_WEIGHTS
        assert "violation_evaluations" in DEFAULT_WEIGHTS

    def test_default_weights_are_positive(self):
        for key, val in DEFAULT_WEIGHTS.items():
            assert val >= 0, f"Weight for {key} is negative: {val}"


# ── Anti-gaming: authoritative sources only ─────────────────────────────────

class TestAntiGaming:
    """EXPOSURE_PROXY must count from system of record, not self-judgment."""

    def test_components_match_authoritative_surfaces(self):
        """Component fields map to known authoritative event surfaces."""
        c = ExposureComponents()
        assert hasattr(c, "tool_dispatch_attempts")     # chain gate receipts
        assert hasattr(c, "chat_generation_calls")       # daemon generation
        assert hasattr(c, "evidence_checks")             # evidence gate
        assert hasattr(c, "violation_evaluations")       # violation resolver

    def test_excluded_events_are_auditable(self):
        """Exclusions must be explicit and countable."""
        reasons = {"non_governed_ui_event": 2, "healthcheck": 1}
        env = make_envelope(excluded_events=3, excluded_reasons=reasons)
        assert env.values["excluded_events"] == 3
        assert env.annotations["excluded_reason_counts"] == reasons

    def test_blocked_attempts_still_count(self):
        """Blocked/failed attempts are exposure-bearing events.

        Otherwise people bias the denominator by selective drops.
        """
        c = ExposureComponents(
            tool_dispatch_attempts=5,   # includes blocked attempts
            violation_evaluations=3,     # includes unresolved violations
        )
        env = make_envelope(components=c)
        assert env.values["eligible_events"] == 8
        assert env.value > 0


# ── Envelope shape compliance ───────────────────────────────────────────────

class TestEnvelopeShape:
    def test_schema_version_current(self):
        env = make_envelope()
        assert env.schema_version == CURRENT_SCHEMA_VERSION

    def test_emitter_field(self):
        env = make_envelope(emitter="test.module")
        assert env.emitter == "test.module"

    def test_emitted_at_override(self):
        env = make_envelope(emitted_at="2026-01-01T00:00:00Z")
        assert env.emitted_at == "2026-01-01T00:00:00Z"

    def test_emitted_at_defaults_to_now(self):
        env = derive_exposure_proxy(
            make_components(),
            WINDOW_START,
            WINDOW_END,
            emitter_version="test",
        )
        assert env.emitted_at  # not empty

    def test_round_trip_json(self):
        env = make_envelope()
        d = env.to_dict()
        recovered = SignalEnvelope.from_dict(d)
        assert recovered == env

    def test_content_hash_deterministic(self):
        env = make_envelope()
        assert env.content_hash() == env.content_hash()

    def test_different_components_different_hash(self):
        env1 = make_envelope(
            components=ExposureComponents(tool_dispatch_attempts=1),
        )
        env2 = make_envelope(
            components=ExposureComponents(tool_dispatch_attempts=2),
        )
        assert env1.content_hash() != env2.content_hash()


# ── Golden fixture shape tests ──────────────────────────────────────────────

class TestGoldenFixture:
    """Verify golden fixtures are compatible with derived envelopes."""

    def test_golden_fixture_parses(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "EXPOSURE_PROXY"

    def test_golden_fixture_has_expected_values_keys(self):
        """Golden fixture values dict has the same keys as derivation output."""
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        derived = make_envelope()
        for key in env.values:
            assert key in derived.values, f"Golden key {key!r} not in derived values"

    def test_golden_fixture_has_weight_set_id(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert "weight_set_id" in env.annotations

    def test_golden_fixture_validates(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == []


class TestCorrelatedStagesFixture:
    """Golden fixture: all 4 streams active in one window (pipeline overlap)."""

    def test_correlated_fixture_parses(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "EXPOSURE_PROXY"

    def test_all_component_keys_present(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.values["component_tool_dispatch_attempts"] > 0
        assert env.values["component_chat_generation_calls"] > 0
        assert env.values["component_evidence_checks"] > 0
        assert env.values["component_violation_evaluations"] > 0

    def test_correlated_fixture_quality_ok(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == QualityStatus.OK.value

    def test_correlated_fixture_has_overlap_annotation(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.annotations.get("overlap_policy") == "composite_opportunity_accounting"

    def test_correlated_fixture_validates(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == []

    def test_correlated_fixture_math_consistent(self):
        """Verify the fixture value equals the default-weight computation."""
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_correlated.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        c = ExposureComponents(
            tool_dispatch_attempts=env.values["component_tool_dispatch_attempts"],
            chat_generation_calls=env.values["component_chat_generation_calls"],
            evidence_checks=env.values["component_evidence_checks"],
            violation_evaluations=env.values["component_violation_evaluations"],
        )
        expected = compute_exposure_points(c)
        assert env.value == expected


class TestZeroButValidFixture:
    """Golden fixture: authoritative sources present, zero exposure, ok quality."""

    def test_zero_fixture_parses(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_zero.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "EXPOSURE_PROXY"

    def test_zero_fixture_value_is_zero(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_zero.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.value == 0.0

    def test_zero_fixture_quality_is_ok(self):
        """Value is zero but quality is ok — events existed."""
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_zero.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == QualityStatus.OK.value

    def test_zero_fixture_has_excluded_events(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_zero.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        assert env.values["excluded_events"] > 0
        assert env.values["source_event_count"] > 0

    def test_zero_fixture_validates(self):
        data = json.loads(
            (FIXTURES / "envelope_ok_exposure_proxy_zero.json").read_text()
        )
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == []


# ── count_from_receipts ─────────────────────────────────────────────────────

class TestCountFromReceipts:
    """Test the thin receipt-counting helper."""

    def test_empty_store(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        components = count_from_receipts(store)
        assert components.total == 0

    def test_counts_chain_composition_as_tool_dispatch(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        for i in range(3):
            store.append(_make_receipt(f"r{i}", "chain_composition"))
        components = count_from_receipts(store)
        assert components.tool_dispatch_attempts == 3

    def test_counts_evidence_gate_as_evidence_checks(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        for i in range(5):
            store.append(_make_receipt(f"ev{i}", "evidence_gate"))
        components = count_from_receipts(store)
        assert components.evidence_checks == 5

    def test_ignores_unrecognized_gates(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("unknown1", "some_other_gate"))
        components = count_from_receipts(store)
        assert components.total == 0

    def test_counts_all_verdicts_including_blocked(self, tmp_path):
        """Blocked/failed attempts still count — exposure is about attempts.

        This is the anti-gaming hinge: if blocked attempts were excluded,
        an adversary could shrink the denominator by failing more.
        """
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        for verdict in ("pass", "warn", "block"):
            store.append(_make_receipt(f"v_{verdict}", "chain_composition", verdict=verdict))
        components = count_from_receipts(store)
        assert components.tool_dispatch_attempts == 3

    def test_mixed_gates(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        receipts = [
            ("mixed0", "chain_composition", "pass"),
            ("mixed1", "chain_composition", "block"),
            ("mixed2", "evidence_gate", "pass"),
            ("mixed3", "evidence_gate", "warn"),
            ("mixed4", "evidence_gate", "pass"),
            ("mixed5", "some_other", "pass"),
        ]
        for rid, gate, verdict in receipts:
            store.append(_make_receipt(rid, gate, verdict=verdict))
        components = count_from_receipts(store)
        assert components.tool_dispatch_attempts == 2
        assert components.evidence_checks == 3
        assert components.chat_generation_calls == 0
        assert components.violation_evaluations == 0

    def test_custom_gate_map(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("custom1", "my_custom_gate"))
        custom_map = {"my_custom_gate": "tool_dispatch"}
        components = count_from_receipts(store, gate_component_map=custom_map)
        assert components.tool_dispatch_attempts == 1


# ── Window boundary semantics ───────────────────────────────────────────────

class TestWindowBoundaries:
    """Window filtering: start inclusive, end exclusive, dedupe by receipt_id."""

    def test_window_start_inclusive(self, tmp_path):
        """Receipt at exactly window_start is included."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("at_start", "chain_composition",
                                   timestamp="2026-02-24T17:40:00Z"))
        components = count_from_receipts(
            store,
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        assert components.tool_dispatch_attempts == 1

    def test_window_end_exclusive(self, tmp_path):
        """Receipt at exactly window_end is excluded."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("at_end", "chain_composition",
                                   timestamp="2026-02-24T17:45:00Z"))
        components = count_from_receipts(
            store,
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        assert components.tool_dispatch_attempts == 0

    def test_before_window_excluded(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("early", "chain_composition",
                                   timestamp="2026-02-24T17:39:59Z"))
        components = count_from_receipts(
            store,
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        assert components.tool_dispatch_attempts == 0

    def test_after_window_excluded(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("late", "chain_composition",
                                   timestamp="2026-02-24T17:46:00Z"))
        components = count_from_receipts(
            store,
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        assert components.tool_dispatch_attempts == 0

    def test_no_window_counts_all(self, tmp_path):
        """Without window params, counts all receipts."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("a", "chain_composition",
                                   timestamp="2020-01-01T00:00:00Z"))
        store.append(_make_receipt("b", "chain_composition",
                                   timestamp="2030-01-01T00:00:00Z"))
        components = count_from_receipts(store)
        assert components.tool_dispatch_attempts == 2

    def test_duplicate_receipt_ids_deduped(self, tmp_path):
        """Same receipt_id appended twice → counted once."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("dup1", "chain_composition"))
        store.append(_make_receipt("dup1", "chain_composition"))
        components = count_from_receipts(store)
        assert components.tool_dispatch_attempts == 1

    def test_window_with_mixed_in_out(self, tmp_path):
        """Mix of in-window and out-of-window receipts."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        store.append(_make_receipt("before", "chain_composition",
                                   timestamp="2026-02-24T17:39:00Z"))
        store.append(_make_receipt("in1", "chain_composition",
                                   timestamp="2026-02-24T17:40:00Z"))
        store.append(_make_receipt("in2", "evidence_gate",
                                   timestamp="2026-02-24T17:42:00Z"))
        store.append(_make_receipt("at_end", "chain_composition",
                                   timestamp="2026-02-24T17:45:00Z"))
        store.append(_make_receipt("after", "evidence_gate",
                                   timestamp="2026-02-24T17:46:00Z"))
        components = count_from_receipts(
            store,
            window_start="2026-02-24T17:40:00Z",
            window_end="2026-02-24T17:45:00Z",
        )
        assert components.tool_dispatch_attempts == 1
        assert components.evidence_checks == 1


# ── Integration: derive from receipt counts ─────────────────────────────────

class TestDeriveFromReceipts:
    """End-to-end: count from receipts → derive → validate."""

    def test_receipt_to_envelope(self, tmp_path):
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        for i in range(4):
            store.append(_make_receipt(f"cc{i}", "chain_composition"))
        for i in range(2):
            store.append(_make_receipt(f"eg{i}", "evidence_gate"))

        components = count_from_receipts(store)
        env = derive_exposure_proxy(
            components,
            WINDOW_START,
            WINDOW_END,
            emitter_version="test",
        )

        assert env.signal_id == "EXPOSURE_PROXY"
        assert env.value == 4 * 1.0 + 2 * 0.8  # tool=4, evidence=2
        # 2 of 4 streams → partial
        assert env.quality_status == QualityStatus.PARTIAL.value
        errors = validate_envelope(env)
        assert errors == []

    def test_receipt_windowed_to_envelope(self, tmp_path):
        """End-to-end with windowed receipt counting."""
        from governor.gate_receipt import ReceiptStore
        store = ReceiptStore(tmp_path)
        # 2 in window, 1 outside
        store.append(_make_receipt("in1", "chain_composition",
                                   timestamp="2026-02-24T17:41:00Z"))
        store.append(_make_receipt("in2", "chain_composition",
                                   timestamp="2026-02-24T17:43:00Z"))
        store.append(_make_receipt("out", "chain_composition",
                                   timestamp="2026-02-24T17:50:00Z"))

        components = count_from_receipts(
            store,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
        )
        env = derive_exposure_proxy(
            components,
            WINDOW_START,
            WINDOW_END,
            emitter_version="test",
        )

        assert env.value == 2 * 1.0  # only 2 in-window chain_composition
        assert env.values["component_tool_dispatch_attempts"] == 2
        errors = validate_envelope(env)
        assert errors == []
