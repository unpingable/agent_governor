# SPDX-License-Identifier: Apache-2.0
"""Tests for telemetry dashboard."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from collections import deque

from governor.dashboard import (
    PhaseSpacePlot,
    RegimeGauge,
    EnergySparkline,
    EventLog,
    BudgetPanel,
    DashboardState,
    parse_log_line,
    load_recent_logs,
    compute_state_from_events,
    generate_demo_trace,
    print_trace_stats,
    RICH_AVAILABLE,
)


# =============================================================================
# PhaseSpacePlot Tests
# =============================================================================

class TestPhaseSpacePlot:
    """Tests for PhaseSpacePlot widget."""

    def test_initialization(self):
        """Plot initializes with empty history."""
        plot = PhaseSpacePlot()
        assert len(plot.history) == 0
        assert plot.width == 40
        assert plot.height == 15

    def test_update_adds_points(self):
        """update() adds data points to history."""
        plot = PhaseSpacePlot()
        plot.update(1.0, 2.0)
        plot.update(2.0, 3.0)
        assert len(plot.history) == 2
        assert plot.history[-1] == (2.0, 3.0)

    def test_history_limit(self):
        """History is limited to max length."""
        plot = PhaseSpacePlot(history_len=5)
        for i in range(10):
            plot.update(float(i), float(i))
        assert len(plot.history) == 5

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_returns_panel(self):
        """render() returns a Rich Panel."""
        from rich.panel import Panel
        plot = PhaseSpacePlot()
        plot.update(1.0, 1.0)
        result = plot.render()
        assert isinstance(result, Panel)

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_empty_history(self):
        """render() works with empty history."""
        from rich.panel import Panel
        plot = PhaseSpacePlot()
        result = plot.render()
        assert isinstance(result, Panel)


# =============================================================================
# RegimeGauge Tests
# =============================================================================

class TestRegimeGauge:
    """Tests for RegimeGauge widget."""

    def test_regime_colors(self):
        """All regime colors are defined."""
        gauge = RegimeGauge()
        for regime in ["ELASTIC", "WARM", "DUCTILE", "UNSTABLE"]:
            assert regime in gauge.COLORS

    def test_regime_icons(self):
        """All regime icons are defined."""
        gauge = RegimeGauge()
        for regime in ["ELASTIC", "WARM", "DUCTILE", "UNSTABLE"]:
            assert regime in gauge.ICONS

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_returns_panel(self):
        """render() returns a Rich Panel."""
        from rich.panel import Panel
        gauge = RegimeGauge()
        result = gauge.render("ELASTIC", 0.5, violations=0, proposals=10, rejections=1)
        assert isinstance(result, Panel)

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_unknown_regime(self):
        """render() handles unknown regime."""
        from rich.panel import Panel
        gauge = RegimeGauge()
        result = gauge.render("UNKNOWN", 0.0)
        assert isinstance(result, Panel)


# =============================================================================
# EnergySparkline Tests
# =============================================================================

class TestEnergySparkline:
    """Tests for EnergySparkline widget."""

    def test_initialization(self):
        """Sparkline initializes with empty history."""
        spark = EnergySparkline()
        assert len(spark.history) == 0

    def test_update_adds_values(self):
        """update() adds values to history."""
        spark = EnergySparkline()
        spark.update(1.0)
        spark.update(2.0)
        assert len(spark.history) == 2

    def test_history_limit(self):
        """History is limited to width."""
        spark = EnergySparkline(width=5)
        for i in range(10):
            spark.update(float(i))
        assert len(spark.history) == 5

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_returns_panel(self):
        """render() returns a Rich Panel."""
        from rich.panel import Panel
        spark = EnergySparkline()
        spark.update(5.0)
        result = spark.render()
        assert isinstance(result, Panel)

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_empty_history(self):
        """render() works with empty history."""
        from rich.panel import Panel
        spark = EnergySparkline()
        result = spark.render()
        assert isinstance(result, Panel)


# =============================================================================
# EventLog Tests
# =============================================================================

class TestEventLog:
    """Tests for EventLog widget."""

    def test_initialization(self):
        """Log initializes empty."""
        log = EventLog()
        assert len(log.entries) == 0

    def test_add_entry(self):
        """add() adds entries."""
        log = EventLog()
        log.add("proposal", "test details", "info")
        assert len(log.entries) == 1

    def test_max_entries(self):
        """Log respects max entries."""
        log = EventLog(max_entries=5)
        for i in range(10):
            log.add("proposal", f"entry {i}")
        assert len(log.entries) == 5

    def test_event_types(self):
        """Different event types are handled."""
        log = EventLog()
        for event_type in ["proposal", "verification", "llm_call", "error", "security_scan"]:
            log.add(event_type, "test")
        assert len(log.entries) == 5

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_returns_panel(self):
        """render() returns a Rich Panel."""
        from rich.panel import Panel
        log = EventLog()
        log.add("proposal", "test")
        result = log.render()
        assert isinstance(result, Panel)

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_empty(self):
        """render() works with no entries."""
        from rich.panel import Panel
        log = EventLog()
        result = log.render()
        assert isinstance(result, Panel)


# =============================================================================
# BudgetPanel Tests
# =============================================================================

class TestBudgetPanel:
    """Tests for BudgetPanel widget."""

    def test_initialization(self):
        """Panel initializes with zero values."""
        panel = BudgetPanel()
        assert panel.spent == 0.0
        assert panel.budget == 0.0
        assert panel.tokens == 0

    def test_update(self):
        """update() sets values."""
        panel = BudgetPanel()
        panel.update(5.0, 100.0, 10000)
        assert panel.spent == 5.0
        assert panel.budget == 100.0
        assert panel.tokens == 10000

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_returns_panel(self):
        """render() returns a Rich Panel."""
        from rich.panel import Panel
        panel = BudgetPanel()
        panel.update(5.0, 100.0, 10000)
        result = panel.render()
        assert isinstance(result, Panel)

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_render_no_budget(self):
        """render() works with no budget set."""
        from rich.panel import Panel
        panel = BudgetPanel()
        panel.update(5.0, 0.0, 10000)
        result = panel.render()
        assert isinstance(result, Panel)


# =============================================================================
# DashboardState Tests
# =============================================================================

class TestDashboardState:
    """Tests for DashboardState dataclass."""

    def test_default_values(self):
        """State has sensible defaults."""
        state = DashboardState()
        assert state.regime == "UNKNOWN"
        assert state.stress == 0.0
        assert state.violations == 0
        assert state.proposals == 0

    def test_all_fields(self):
        """All fields can be set."""
        state = DashboardState(
            regime="ELASTIC",
            stress=0.5,
            violations=2,
            proposals=10,
            rejections=1,
            spent_usd=5.0,
            budget_usd=100.0,
            tokens=5000,
            lambda_rate=2.0,
            mu_rate=3.0,
            energy=5.0,
        )
        assert state.regime == "ELASTIC"
        assert state.stress == 0.5


# =============================================================================
# Log Parsing Tests
# =============================================================================

class TestLogParsing:
    """Tests for log parsing functions."""

    def test_parse_valid_line(self):
        """parse_log_line parses valid JSON."""
        line = '{"event_type": "proposal", "level": "info"}'
        result = parse_log_line(line)
        assert result == {"event_type": "proposal", "level": "info"}

    def test_parse_invalid_line(self):
        """parse_log_line returns None for invalid JSON."""
        result = parse_log_line("not json")
        assert result is None

    def test_parse_empty_line(self):
        """parse_log_line handles empty lines."""
        result = parse_log_line("")
        assert result is None

    def test_parse_whitespace_line(self):
        """parse_log_line handles whitespace."""
        result = parse_log_line("   \n")
        assert result is None


class TestLoadRecentLogs:
    """Tests for load_recent_logs function."""

    def test_nonexistent_dir(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        result = load_recent_logs(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir(self, tmp_path):
        """Returns empty list for empty directory."""
        result = load_recent_logs(tmp_path)
        assert result == []

    def test_loads_jsonl_files(self, tmp_path):
        """Loads events from JSONL files."""
        log_file = tmp_path / "governor-20260203.jsonl"
        events = [
            {"event_type": "proposal", "level": "info"},
            {"event_type": "verification", "level": "info"},
        ]
        with open(log_file, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        result = load_recent_logs(tmp_path)
        assert len(result) == 2

    def test_respects_max_lines(self, tmp_path):
        """Respects max_lines limit."""
        log_file = tmp_path / "governor-20260203.jsonl"
        with open(log_file, 'w') as f:
            for i in range(100):
                f.write(json.dumps({"event_type": "proposal", "n": i}) + "\n")

        result = load_recent_logs(tmp_path, max_lines=10)
        assert len(result) == 10


class TestComputeStateFromEvents:
    """Tests for compute_state_from_events function."""

    def test_empty_events(self):
        """Handles empty event list."""
        state = compute_state_from_events([])
        assert state.proposals == 0
        assert state.regime == "ELASTIC"

    def test_counts_proposals(self):
        """Counts proposal events."""
        events = [
            {"event_type": "proposal"},
            {"event_type": "proposal"},
            {"event_type": "verification", "fields": {"success": True}},
        ]
        state = compute_state_from_events(events)
        assert state.proposals == 2

    def test_counts_rejections(self):
        """Counts failed verifications as rejections."""
        events = [
            {"event_type": "verification", "fields": {"success": False}},
            {"event_type": "verification", "fields": {"success": True}},
        ]
        state = compute_state_from_events(events)
        assert state.rejections == 1

    def test_counts_violations(self):
        """Counts error events as violations."""
        events = [
            {"event_type": "error"},
            {"event_type": "error"},
        ]
        state = compute_state_from_events(events)
        assert state.violations == 2

    def test_sums_tokens(self):
        """Sums tokens from LLM calls."""
        events = [
            {"event_type": "llm_call", "fields": {"tokens_used": 1000}},
            {"event_type": "llm_call", "fields": {"tokens_used": 2000}},
        ]
        state = compute_state_from_events(events)
        assert state.tokens == 3000

    def test_sums_costs(self):
        """Sums costs from LLM calls."""
        events = [
            {"event_type": "llm_call", "fields": {"cost_usd": 0.01}},
            {"event_type": "llm_call", "fields": {"cost_usd": 0.02}},
        ]
        state = compute_state_from_events(events)
        assert abs(state.spent_usd - 0.03) < 0.001

    def test_regime_from_stress(self):
        """Regime determined by stress level."""
        # Low stress -> ELASTIC
        events = [{"event_type": "proposal"}] * 10
        events.extend([{"event_type": "verification", "fields": {"success": True}}] * 10)
        state = compute_state_from_events(events)
        assert state.regime == "ELASTIC"

    def test_high_stress_regime(self):
        """High rejection rate leads to higher stress regime."""
        events = [{"event_type": "proposal"}] * 10
        # Many rejections
        events.extend([{"event_type": "verification", "fields": {"success": False}}] * 5)
        events.extend([{"event_type": "error"}] * 10)
        state = compute_state_from_events(events)
        assert state.regime in ["WARM", "DUCTILE", "UNSTABLE"]


# =============================================================================
# Demo Trace Generation Tests
# =============================================================================

class TestDemoTrace:
    """Tests for demo trace generation."""

    def test_generate_demo_trace(self, tmp_path):
        """generate_demo_trace creates valid JSONL file."""
        output = tmp_path / "demo.jsonl"
        result = generate_demo_trace(output)

        assert result == output
        assert output.exists()

        # Verify contents
        with open(output) as f:
            lines = f.readlines()
        assert len(lines) == 100

        # Each line should be valid JSON
        for line in lines:
            event = json.loads(line)
            assert "event_type" in event
            assert "timestamp" in event

    def test_demo_trace_event_types(self, tmp_path):
        """Demo trace contains varied event types."""
        output = tmp_path / "demo.jsonl"
        generate_demo_trace(output)

        event_types = set()
        with open(output) as f:
            for line in f:
                event = json.loads(line)
                event_types.add(event["event_type"])

        # Should have multiple event types
        assert len(event_types) >= 3


class TestTraceStats:
    """Tests for trace statistics."""

    def test_stats_nonexistent_file(self, tmp_path, capsys):
        """print_trace_stats handles missing file."""
        print_trace_stats(tmp_path / "missing.jsonl")
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "error" in captured.out.lower()

    def test_stats_valid_trace(self, tmp_path, capsys):
        """print_trace_stats prints statistics."""
        trace = tmp_path / "test.jsonl"
        events = [
            {"event_type": "proposal"},
            {"event_type": "proposal"},
            {"event_type": "verification"},
        ]
        with open(trace, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        print_trace_stats(trace)
        captured = capsys.readouterr()

        assert "Records: 3" in captured.out
        assert "proposal" in captured.out


# =============================================================================
# Integration Tests
# =============================================================================

class TestDashboardIntegration:
    """Integration tests for dashboard components."""

    def test_state_to_widgets(self):
        """DashboardState can drive all widgets."""
        state = DashboardState(
            regime="WARM",
            stress=0.4,
            violations=2,
            proposals=20,
            rejections=3,
            spent_usd=1.5,
            budget_usd=10.0,
            tokens=5000,
            lambda_rate=2.0,
            mu_rate=2.5,
            energy=4.0,
        )

        # All widgets should handle the state
        phase = PhaseSpacePlot()
        phase.update(state.lambda_rate, state.mu_rate)
        assert len(phase.history) == 1

        spark = EnergySparkline()
        spark.update(state.energy)
        assert len(spark.history) == 1

        budget = BudgetPanel()
        budget.update(state.spent_usd, state.budget_usd, state.tokens)
        assert budget.spent == 1.5

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_all_widgets_render(self):
        """All widgets can render without error."""
        from rich.panel import Panel

        phase = PhaseSpacePlot()
        phase.update(1.0, 1.0)
        assert isinstance(phase.render(), Panel)

        gauge = RegimeGauge()
        assert isinstance(gauge.render("ELASTIC", 0.2), Panel)

        spark = EnergySparkline()
        spark.update(5.0)
        assert isinstance(spark.render(), Panel)

        log = EventLog()
        log.add("proposal", "test")
        assert isinstance(log.render(), Panel)

        budget = BudgetPanel()
        budget.update(1.0, 10.0, 1000)
        assert isinstance(budget.render(), Panel)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_zero_energy(self):
        """Sparkline handles zero energy values."""
        spark = EnergySparkline()
        spark.update(0.0)
        spark.update(0.0)
        assert len(spark.history) == 2

    def test_high_values(self):
        """Widgets handle high values."""
        phase = PhaseSpacePlot()
        phase.update(1000.0, 1000.0)
        assert len(phase.history) == 1

        spark = EnergySparkline()
        spark.update(10000.0)
        assert len(spark.history) == 1

    def test_negative_rates(self):
        """Phase plot handles edge case values."""
        phase = PhaseSpacePlot()
        phase.update(0.0, 0.0)
        phase.update(-1.0, -1.0)  # Edge case
        assert len(phase.history) == 2

    def test_missing_event_fields(self):
        """State computation handles missing fields."""
        events = [
            {"event_type": "llm_call"},  # No fields
            {"event_type": "verification"},  # No fields.success
        ]
        state = compute_state_from_events(events)
        assert state.tokens == 0  # Default when missing
