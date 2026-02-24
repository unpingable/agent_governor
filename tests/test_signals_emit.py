# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.4 Phase A0: SignalEmitter protocol and JsonlSink."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    SignalEnvelope,
    validate_envelope,
)
from governor.signals.emit import JsonlSink, MultiSink, SignalEmitter

FIXTURES = Path(__file__).parent / "fixtures" / "signals"


def make_envelope(**overrides) -> SignalEnvelope:
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


# ── Protocol conformance ─────────────────────────────────────────────────────

class TestProtocol:
    def test_jsonl_sink_is_emitter(self, tmp_path):
        sink = JsonlSink(tmp_path / "signals.jsonl")
        assert isinstance(sink, SignalEmitter)

    def test_multi_sink_is_emitter(self, tmp_path):
        inner = JsonlSink(tmp_path / "signals.jsonl")
        multi = MultiSink([inner])
        assert isinstance(multi, SignalEmitter)


# ── JsonlSink ────────────────────────────────────────────────────────────────

class TestJsonlSink:
    def test_emit_creates_file(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope())
        assert path.exists()

    def test_emit_appends_one_line(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope(signal_id="SIG_1"))
        sink.emit(make_envelope(signal_id="SIG_2"))
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope())
        for line in path.read_text().strip().split("\n"):
            parsed = json.loads(line)
            assert parsed["signal_id"] == "TEST_SIGNAL"

    def test_emit_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope())
        assert path.exists()

    def test_read_all_returns_envelopes(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope(signal_id="A"))
        sink.emit(make_envelope(signal_id="B"))
        envelopes = sink.read_all()
        assert len(envelopes) == 2
        assert envelopes[0].signal_id == "A"
        assert envelopes[1].signal_id == "B"

    def test_read_all_empty_file(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        assert sink.read_all() == []

    def test_read_all_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        sink = JsonlSink(path)
        assert sink.read_all() == []

    def test_count(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        assert sink.count() == 0
        sink.emit(make_envelope())
        sink.emit(make_envelope())
        assert sink.count() == 2

    def test_count_missing_file(self, tmp_path):
        sink = JsonlSink(tmp_path / "nope.jsonl")
        assert sink.count() == 0

    def test_round_trip_preserves_envelope(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        original = make_envelope(
            value=3.14,
            values={"x": 1, "y": 2},
            quality_reasons=["test_reason"],
            annotations={"note": "hello"},
        )
        sink.emit(original)
        recovered = sink.read_all()[0]
        assert recovered == original

    def test_validation_rejects_invalid(self, tmp_path):
        """Invalid envelopes are skipped, not written."""
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path, validate=True)
        bad = make_envelope(quality_status="bogus")
        sink.emit(bad)
        assert sink.count() == 0

    def test_validation_disabled(self, tmp_path):
        """With validate=False, invalid envelopes still get written."""
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path, validate=False)
        bad = make_envelope(quality_status="bogus")
        sink.emit(bad)
        assert sink.count() == 1

    def test_emit_never_raises(self, tmp_path):
        """Even on IO errors, emit must not raise (observe-only)."""
        # Point at a directory (not a file) to cause write failure
        path = tmp_path / "dir_not_file"
        path.mkdir()
        sink = JsonlSink(path)
        # Should not raise
        sink.emit(make_envelope())

    def test_path_property(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        assert sink.path == path

    def test_read_all_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path)
        sink.emit(make_envelope(signal_id="GOOD"))
        # Append a malformed line
        with open(path, "a") as f:
            f.write("not valid json\n")
        sink.emit(make_envelope(signal_id="ALSO_GOOD"))
        envelopes = sink.read_all()
        assert len(envelopes) == 2
        assert envelopes[0].signal_id == "GOOD"
        assert envelopes[1].signal_id == "ALSO_GOOD"


# ── Golden fixture emit + read round-trip ────────────────────────────────────

class TestGoldenFixtureEmitRoundTrip:
    """Emit golden fixtures through JsonlSink and verify recovery."""

    FIXTURE_FILES = [
        "envelope_ok_exposure_proxy.json",
        "envelope_partial_sigma_rate.json",
        "envelope_unavailable_silent_suppression.json",
        "envelope_invalid_sigma_rate.json",
    ]

    @pytest.mark.parametrize("filename", FIXTURE_FILES)
    def test_golden_fixture_survives_emit_cycle(self, tmp_path, filename):
        data = json.loads((FIXTURES / filename).read_text())
        env = SignalEnvelope.from_dict(data)

        path = tmp_path / "signals.jsonl"
        sink = JsonlSink(path, validate=True)
        sink.emit(env)

        recovered = sink.read_all()
        assert len(recovered) == 1
        assert recovered[0] == env


# ── MultiSink ────────────────────────────────────────────────────────────────

class TestMultiSink:
    def test_fans_out_to_all_sinks(self, tmp_path):
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"
        multi = MultiSink([JsonlSink(path_a), JsonlSink(path_b)])
        multi.emit(make_envelope())
        assert JsonlSink(path_a).count() == 1
        assert JsonlSink(path_b).count() == 1

    def test_one_sink_failure_does_not_block_others(self, tmp_path):
        """If one sink fails, others still receive the envelope."""
        path_good = tmp_path / "good.jsonl"
        path_bad = tmp_path / "bad_dir"
        path_bad.mkdir()  # will cause write failure

        multi = MultiSink([JsonlSink(path_bad), JsonlSink(path_good)])
        multi.emit(make_envelope())
        assert JsonlSink(path_good).count() == 1


# ── Missing != Zero invariant (dedicated tests) ─────────────────────────────

class TestMissingNotZero:
    """Dedicated tests for the missing != zero invariant."""

    def test_zero_value_with_ok_is_valid(self):
        """Zero IS a valid measurement when quality is ok."""
        env = make_envelope(value=0.0, quality_status="ok")
        errors = validate_envelope(env)
        assert errors == []

    def test_none_value_with_unavailable_is_valid(self):
        """None means 'could not compute'. This is the correct pattern."""
        env = make_envelope(value=None, quality_status="unavailable")
        errors = validate_envelope(env)
        assert errors == []

    def test_zero_value_with_unavailable_is_rejected(self):
        """Conflating zero with missing is the bug this catches."""
        env = make_envelope(value=0.0, quality_status="unavailable")
        errors = validate_envelope(env)
        assert len(errors) > 0

    def test_none_value_with_ok_but_values_dict_is_valid(self):
        """No scalar value but meaningful submetrics — still ok."""
        env = make_envelope(value=None, quality_status="ok", values={"count": 42})
        errors = validate_envelope(env)
        assert errors == []

    def test_none_value_with_partial_is_valid(self):
        env = make_envelope(value=None, quality_status="partial")
        errors = validate_envelope(env)
        assert errors == []

    def test_none_value_with_invalid_is_valid(self):
        env = make_envelope(value=None, quality_status="invalid")
        errors = validate_envelope(env)
        assert errors == []
