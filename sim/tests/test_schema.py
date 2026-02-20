# SPDX-License-Identifier: Apache-2.0
"""Tests for governor_sim.schema."""

import json

import pytest

from governor_sim.schema import TraceEvent, TraceHeader, VALID_EVENT_TYPES


class TestTraceHeader:
    def test_defaults(self):
        h = TraceHeader()
        assert h.dsl_version == 1
        assert h.seed == 0

    def test_roundtrip(self):
        h = TraceHeader(dsl_version=2, seed=42)
        d = h.to_dict()
        h2 = TraceHeader.from_dict(d)
        assert h == h2

    def test_params_roundtrip(self):
        params = {"heartbeat_interval": 120, "heartbeat_grace": 30}
        h = TraceHeader(params=params)
        d = h.to_dict()
        assert d["params"] == params
        h2 = TraceHeader.from_dict(d)
        assert h2.params == params

    def test_empty_params_omitted_from_dict(self):
        h = TraceHeader()
        d = h.to_dict()
        assert "params" not in d


class TestTraceEvent:
    def test_construction_and_frozen(self):
        e = TraceEvent(t_ms=100, seq=0, scenario="test", event_type="call", payload={"x": 1})
        assert e.t_ms == 100
        assert e.actor is None
        with pytest.raises(AttributeError):
            e.t_ms = 200  # type: ignore[misc]

    def test_negative_t_ms_raises(self):
        with pytest.raises(ValueError, match="t_ms must be >= 0"):
            TraceEvent(t_ms=-1, seq=0, scenario="test", event_type="call")

    def test_negative_seq_raises(self):
        with pytest.raises(ValueError, match="seq must be >= 0"):
            TraceEvent(t_ms=0, seq=-1, scenario="test", event_type="call")

    def test_bad_event_type_raises(self):
        with pytest.raises(ValueError, match="event_type must be one of"):
            TraceEvent(t_ms=0, seq=0, scenario="test", event_type="sleep")

    def test_empty_scenario_raises(self):
        with pytest.raises(ValueError, match="scenario must be non-empty"):
            TraceEvent(t_ms=0, seq=0, scenario="", event_type="call")

    def test_actor_none_allowed(self):
        e = TraceEvent(t_ms=0, seq=0, scenario="test", event_type="fault", actor=None)
        assert e.actor is None
        d = e.to_dict()
        assert "actor" not in d

    def test_roundtrip(self):
        e = TraceEvent(
            t_ms=500, seq=3, scenario="s1", event_type="emit",
            payload={"kind": "receipt"}, actor="alice",
            session_id="sess-1", run_id="run-1",
        )
        d = e.to_dict()
        e2 = TraceEvent.from_dict(d)
        assert e == e2

    def test_to_json_line_deterministic(self):
        e = TraceEvent(t_ms=0, seq=0, scenario="test", event_type="call", payload={"b": 2, "a": 1})
        line1 = e.to_json_line()
        line2 = e.to_json_line()
        assert line1 == line2
        # Verify sorted keys
        parsed = json.loads(line1)
        assert list(parsed.keys()) == sorted(parsed.keys())
        # Verify compact separators (no spaces)
        assert " " not in line1
