# SPDX-License-Identifier: Apache-2.0
"""Tests for the golden fixtures."""

from pathlib import Path

import pytest

from governor_sim.dsl import compile_scenario, load_scenario
from governor_sim.runner import InprocRunner

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestHeartbeatActive:
    @pytest.fixture
    def compiled(self):
        spec = load_scenario(FIXTURES_DIR / "heartbeat_active.json")
        return compile_scenario(spec)

    def test_compiles(self, compiled):
        header, events = compiled
        assert header.dsl_version == 1
        assert len(events) > 0

    def test_monotonic_t_ms(self, compiled):
        _, events = compiled
        non_assert = [e for e in events if e.event_type != "assert"]
        times = [e.t_ms for e in non_assert]
        assert times == sorted(times)

    def test_monotonic_seq(self, compiled):
        _, events = compiled
        seqs = [e.seq for e in events]
        assert seqs == list(range(len(seqs)))

    def test_deterministic_compile(self):
        spec = load_scenario(FIXTURES_DIR / "heartbeat_active.json")
        _, events1 = compile_scenario(spec)
        _, events2 = compile_scenario(spec)
        assert [e.to_dict() for e in events1] == [e.to_dict() for e in events2]

    def test_assertions_pass(self, compiled, tmp_path):
        _, events = compiled
        runner = InprocRunner(work_dir=tmp_path)
        result = runner.run(events)
        assert result.passed, f"Failures: {result.assertion_results} Errors: {result.errors}"


class TestHeartbeatStale:
    @pytest.fixture
    def compiled(self):
        spec = load_scenario(FIXTURES_DIR / "heartbeat_stale.json")
        return compile_scenario(spec)

    def test_compiles(self, compiled):
        header, events = compiled
        assert header.dsl_version == 1

    def test_staleness_detected(self, compiled, tmp_path):
        _, events = compiled
        runner = InprocRunner(work_dir=tmp_path)
        result = runner.run(events)
        assert result.passed, f"Failures: {result.assertion_results} Errors: {result.errors}"

    def test_monotonic_t_ms(self, compiled):
        _, events = compiled
        non_assert = [e for e in events if e.event_type != "assert"]
        times = [e.t_ms for e in non_assert]
        assert times == sorted(times)

    def test_monotonic_seq(self, compiled):
        _, events = compiled
        seqs = [e.seq for e in events]
        assert seqs == list(range(len(seqs)))


class TestGateDisabled:
    @pytest.fixture
    def compiled(self):
        spec = load_scenario(FIXTURES_DIR / "gate_disabled.json")
        return compile_scenario(spec)

    def test_compiles(self, compiled):
        header, events = compiled
        assert header.dsl_version == 1

    def test_assertions_pass(self, compiled, tmp_path):
        _, events = compiled
        runner = InprocRunner(work_dir=tmp_path)
        result = runner.run(events)
        assert result.passed, f"Failures: {result.assertion_results} Errors: {result.errors}"

    def test_only_two_receipts(self, compiled, tmp_path):
        """Gate disabled between checks 2-3, so only first + last produce receipts."""
        _, events = compiled
        runner = InprocRunner(work_dir=tmp_path)
        runner.run(events)
        api = runner._get_api()
        assert api.receipt_count() == 2

    def test_monotonic_seq(self, compiled):
        _, events = compiled
        seqs = [e.seq for e in events]
        assert seqs == list(range(len(seqs)))
