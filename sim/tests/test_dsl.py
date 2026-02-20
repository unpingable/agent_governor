# SPDX-License-Identifier: Apache-2.0
"""Tests for governor_sim.dsl."""

import json
import tempfile
from pathlib import Path

import pytest

from governor_sim.dsl import compile_scenario, load_scenario, parse_duration_ms


class TestParseDuration:
    def test_seconds(self):
        assert parse_duration_ms("30s") == 30_000

    def test_minutes(self):
        assert parse_duration_ms("5m") == 300_000

    def test_milliseconds(self):
        assert parse_duration_ms("200ms") == 200

    def test_compound(self):
        assert parse_duration_ms("5m30s") == 330_000

    def test_full_compound(self):
        assert parse_duration_ms("1m2s3ms") == 62_003

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid duration"):
            parse_duration_ms("abc")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="invalid duration"):
            parse_duration_ms("")


class TestCompileScenario:
    def test_absolute_time(self):
        spec = {
            "name": "test",
            "steps": [
                {"type": "call", "t": 0, "payload": {"target": "gate_check", "output": "x"}},
                {"type": "call", "t": 1000, "payload": {"target": "gate_check", "output": "y"}},
            ],
        }
        header, events = compile_scenario(spec)
        assert header.dsl_version == 1
        assert len(events) == 2
        assert events[0].t_ms == 0
        assert events[1].t_ms == 1000

    def test_relative_time(self):
        spec = {
            "name": "test",
            "steps": [
                {"type": "call", "t": 0, "payload": {"target": "gate_check", "output": "x"}},
                {"type": "call", "after": "2m", "payload": {"target": "gate_check", "output": "y"}},
            ],
        }
        _, events = compile_scenario(spec)
        assert events[1].t_ms == 120_000

    def test_seq_monotonic(self):
        spec = {
            "name": "test",
            "steps": [
                {"type": "call", "t": 0, "payload": {"target": "gate_check", "output": "a"}},
                {"type": "call", "t": 100, "payload": {"target": "gate_check", "output": "b"}},
                {"type": "call", "t": 200, "payload": {"target": "gate_check", "output": "c"}},
            ],
        }
        _, events = compile_scenario(spec)
        seqs = [e.seq for e in events]
        assert seqs == [0, 1, 2]

    def test_asserts_appended_after_steps(self):
        spec = {
            "name": "test",
            "steps": [
                {"type": "call", "t": 500, "payload": {"target": "gate_check", "output": "x"}},
            ],
            "asserts": [
                {"check": "expect_receipt_count", "value": 1},
            ],
        }
        _, events = compile_scenario(spec)
        assert len(events) == 2
        assert events[-1].event_type == "assert"
        assert events[-1].t_ms == 500  # at final step time

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="non-empty 'name'"):
            compile_scenario({"steps": []})

    def test_missing_time_raises(self):
        with pytest.raises(ValueError, match="'t'.*or 'after'"):
            compile_scenario({"name": "test", "steps": [{"type": "call", "payload": {}}]})

    def test_params_carried_to_header(self):
        spec = {
            "name": "test",
            "params": {"heartbeat_interval": 120, "heartbeat_grace": 30},
            "steps": [{"type": "call", "t": 0, "payload": {"target": "gate_check", "output": "x"}}],
        }
        header, _ = compile_scenario(spec)
        assert header.params["heartbeat_interval"] == 120
        assert header.params["heartbeat_grace"] == 30


class TestLoadScenario:
    def test_json_file(self, tmp_path):
        spec = {"name": "test", "steps": []}
        p = tmp_path / "test.json"
        p.write_text(json.dumps(spec))
        loaded = load_scenario(p)
        assert loaded["name"] == "test"
