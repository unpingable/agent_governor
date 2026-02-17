# SPDX-License-Identifier: Apache-2.0
"""Tests for Prometheus metrics export."""

import json
import pytest
from pathlib import Path

from governor.prometheus import (
    PROMETHEUS_AVAILABLE,
    PrometheusConfig,
    GovernorMetrics,
    MetricsServer,
    PrometheusTelemetryBackend,
    get_metrics,
    create_telemetry_backend,
)


# =============================================================================
# PrometheusConfig Tests
# =============================================================================

class TestPrometheusConfig:
    """Tests for PrometheusConfig dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = PrometheusConfig()
        assert config.enabled is False
        assert config.port == 9090
        assert config.host == "0.0.0.0"

    def test_custom_values(self):
        """Config accepts custom values."""
        config = PrometheusConfig(enabled=True, port=8080, host="127.0.0.1")
        assert config.enabled is True
        assert config.port == 8080
        assert config.host == "127.0.0.1"

    def test_save_and_load(self, tmp_path):
        """Config saves and loads correctly."""
        config = PrometheusConfig(enabled=True, port=9999)
        config.save(tmp_path)

        loaded = PrometheusConfig.load(tmp_path)
        assert loaded.enabled is True
        assert loaded.port == 9999

    def test_load_nonexistent(self, tmp_path):
        """Loading nonexistent config returns defaults."""
        config = PrometheusConfig.load(tmp_path / "nonexistent")
        assert config.enabled is False
        assert config.port == 9090

    def test_load_corrupted(self, tmp_path):
        """Loading corrupted config returns defaults."""
        config_file = tmp_path / "prometheus.json"
        config_file.write_text("not valid json")

        config = PrometheusConfig.load(tmp_path)
        assert config.enabled is False

    def test_save_creates_file(self, tmp_path):
        """Save creates the config file."""
        config = PrometheusConfig()
        config.save(tmp_path)

        assert (tmp_path / "prometheus.json").exists()


# =============================================================================
# GovernorMetrics Tests (with prometheus_client)
# =============================================================================

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestGovernorMetricsWithClient:
    """Tests for GovernorMetrics when prometheus_client is available."""

    def test_initialization(self):
        """Metrics initialize correctly."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        assert metrics.enabled is True

    def test_record_proposal(self):
        """record_proposal increments counter."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_proposal()
        metrics.record_proposal()

        # Check counter value
        assert metrics.proposals_total._value.get() == 2

    def test_record_verification_success(self):
        """record_verification with success."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_verification(success=True, duration_seconds=0.5)

        assert metrics.verifications_total.labels(status="success")._value.get() == 1

    def test_record_verification_failure(self):
        """record_verification with failure."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_verification(success=False)

        assert metrics.verifications_total.labels(status="failure")._value.get() == 1

    def test_record_llm_call(self):
        """record_llm_call tracks all fields."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_llm_call(
            model="claude-sonnet-4",
            provider="anthropic",
            duration_seconds=1.5,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
        )

        assert metrics.llm_calls_total.labels(
            model="claude-sonnet-4", provider="anthropic"
        )._value.get() == 1
        assert metrics.tokens_total.labels(direction="input")._value.get() == 1000
        assert metrics.tokens_total.labels(direction="output")._value.get() == 500

    def test_record_error(self):
        """record_error tracks error types."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_error("validation")
        metrics.record_error("validation")
        metrics.record_error("timeout")

        assert metrics.errors_total.labels(error_type="validation")._value.get() == 2
        assert metrics.errors_total.labels(error_type="timeout")._value.get() == 1

    def test_record_claim(self):
        """record_claim tracks claim types and provenance."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_claim("FILE_EXISTS", "assumed")
        metrics.record_claim("TESTS_PASS", "verified")

        assert metrics.claims_total.labels(
            claim_type="FILE_EXISTS", provenance="assumed"
        )._value.get() == 1

    def test_record_security_scan(self):
        """record_security_scan tracks results."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_security_scan(has_findings=False)
        metrics.record_security_scan(has_findings=True)

        assert metrics.security_scans_total.labels(result="clean")._value.get() == 1
        assert metrics.security_scans_total.labels(result="findings")._value.get() == 1

    def test_record_continuity_check(self):
        """record_continuity_check tracks results."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_continuity_check(passed=True, converged=True, iterations=3)
        metrics.record_continuity_check(passed=False, converged=False)

        assert metrics.continuity_checks_total.labels(result="converged")._value.get() == 1
        assert metrics.continuity_checks_total.labels(result="fail")._value.get() == 1

    def test_record_regime_transition(self):
        """record_regime_transition tracks transitions."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.record_regime_transition("ELASTIC", "WARM")

        assert metrics.regime_transitions_total.labels(
            from_regime="ELASTIC", to_regime="WARM"
        )._value.get() == 1

    def test_set_regime(self):
        """set_regime updates gauge."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.set_regime("ELASTIC")
        assert metrics.regime._value.get() == 1

        metrics.set_regime("WARM")
        assert metrics.regime._value.get() == 2

        metrics.set_regime("DUCTILE")
        assert metrics.regime._value.get() == 3

        metrics.set_regime("UNSTABLE")
        assert metrics.regime._value.get() == 4

    def test_set_stress(self):
        """set_stress updates gauge."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.set_stress(0.5)
        assert metrics.stress._value.get() == 0.5

    def test_set_budget(self):
        """set_budget updates both gauges."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.set_budget(spent=10.0, remaining=90.0)
        assert metrics.budget_spent._value.get() == 10.0
        assert metrics.budget_remaining._value.get() == 90.0

    def test_set_active_sessions(self):
        """set_active_sessions updates gauge."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.set_active_sessions(3)
        assert metrics.active_sessions._value.get() == 3

    def test_set_info(self):
        """set_info updates info metric."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        metrics.set_info(version="1.0.0", mode="strict")
        # Info metric stores dict, verify no exception


# =============================================================================
# GovernorMetrics Tests (without prometheus_client)
# =============================================================================

class TestGovernorMetricsStub:
    """Tests for GovernorMetrics graceful degradation."""

    def test_methods_dont_crash_when_disabled(self):
        """All methods work without prometheus_client."""
        # Create metrics without registry (simulates missing library)
        metrics = GovernorMetrics()

        # These should not raise even if prometheus isn't available
        if not PROMETHEUS_AVAILABLE:
            assert not metrics.enabled
        else:
            # With prometheus, create disabled metrics manually
            metrics._enabled = False

        # All methods should be no-ops
        metrics.record_proposal()
        metrics.record_verification(True, 1.0)
        metrics.record_llm_call("model", "provider", 1.0, 100, 50, 0.01)
        metrics.record_error("test")
        metrics.record_claim("TEST", "assumed")
        metrics.record_security_scan(True)
        metrics.record_continuity_check(True, True, 5)
        metrics.record_regime_transition("ELASTIC", "WARM")
        metrics.record_complexity(0.5)
        metrics.set_regime("ELASTIC")
        metrics.set_stress(0.5)
        metrics.set_budget(10.0, 90.0)
        metrics.set_active_sessions(1)
        metrics.set_open_proposals(2)
        metrics.set_anchors("test", 3)
        metrics.set_info("1.0", "strict")


# =============================================================================
# MetricsServer Tests
# =============================================================================

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestMetricsServer:
    """Tests for MetricsServer."""

    def test_initialization(self):
        """Server initializes correctly."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        config = PrometheusConfig(port=9999)

        server = MetricsServer(metrics, config)
        assert not server.running

    def test_get_metrics_text(self):
        """get_metrics_text returns Prometheus format."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        config = PrometheusConfig()
        server = MetricsServer(metrics, config)

        # Record some metrics
        metrics.record_proposal()

        text = server.get_metrics_text()
        assert "governor_proposals_total" in text

    def test_running_property(self):
        """running property reflects state."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        config = PrometheusConfig()
        server = MetricsServer(metrics, config)

        assert server.running is False


# =============================================================================
# PrometheusTelemetryBackend Tests
# =============================================================================

class TestPrometheusTelemetryBackend:
    """Tests for PrometheusTelemetryBackend."""

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_proposal_event(self):
        """Backend records proposal events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({"event_type": "proposal", "fields": {}})

        assert metrics.proposals_total._value.get() == 1

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_verification_event(self):
        """Backend records verification events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({
            "event_type": "verification",
            "fields": {"success": True},
            "duration_ms": 500,
        })

        assert metrics.verifications_total.labels(status="success")._value.get() == 1

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_llm_call_event(self):
        """Backend records LLM call events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({
            "event_type": "llm_call",
            "fields": {
                "model": "claude-sonnet-4",
                "provider": "anthropic",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.05,
            },
            "duration_ms": 1500,
        })

        assert metrics.llm_calls_total.labels(
            model="claude-sonnet-4", provider="anthropic"
        )._value.get() == 1

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_error_event(self):
        """Backend records error events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({
            "event_type": "error",
            "fields": {"error_type": "validation"},
        })

        assert metrics.errors_total.labels(error_type="validation")._value.get() == 1

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_security_scan_event(self):
        """Backend records security scan events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({
            "event_type": "security_scan",
            "fields": {"findings_count": 2},
        })

        assert metrics.security_scans_total.labels(result="findings")._value.get() == 1

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_record_continuity_result_event(self):
        """Backend records continuity result events."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        backend.record({
            "event_type": "continuity_result",
            "fields": {"converged": True, "iterations": 3},
        })

        assert metrics.continuity_checks_total.labels(result="converged")._value.get() == 1

    def test_record_unknown_event(self):
        """Backend handles unknown event types gracefully."""
        metrics = GovernorMetrics()
        backend = PrometheusTelemetryBackend(metrics)

        # Should not raise
        backend.record({"event_type": "unknown_type", "fields": {}})


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_metrics_returns_instance(self):
        """get_metrics returns a GovernorMetrics instance."""
        metrics = get_metrics()
        assert isinstance(metrics, GovernorMetrics)

    def test_create_telemetry_backend(self):
        """create_telemetry_backend returns backend instance."""
        backend = create_telemetry_backend()
        assert isinstance(backend, PrometheusTelemetryBackend)


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestIntegration:
    """Integration tests for Prometheus metrics."""

    def test_full_workflow(self):
        """Test a realistic workflow of metric recording."""
        from prometheus_client import CollectorRegistry
        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)
        backend = PrometheusTelemetryBackend(metrics)

        # Simulate a session
        metrics.set_regime("ELASTIC")
        metrics.set_active_sessions(1)

        # Proposal
        backend.record({"event_type": "proposal", "fields": {"claim_count": 2}})

        # LLM call
        backend.record({
            "event_type": "llm_call",
            "fields": {
                "model": "claude-sonnet-4",
                "provider": "anthropic",
                "input_tokens": 5000,
                "cost_usd": 0.02,
            },
            "duration_ms": 2000,
        })

        # Verification
        backend.record({
            "event_type": "verification",
            "fields": {"success": True},
            "duration_ms": 100,
        })

        # Update regime
        metrics.record_regime_transition("ELASTIC", "WARM")
        metrics.set_regime("WARM")

        # Verify metrics
        assert metrics.proposals_total._value.get() == 1
        assert metrics.llm_calls_total.labels(
            model="claude-sonnet-4", provider="anthropic"
        )._value.get() == 1
        assert metrics.verifications_total.labels(status="success")._value.get() == 1
        assert metrics.regime._value.get() == 2  # WARM

    def test_config_persistence(self, tmp_path):
        """Config persists across save/load cycles."""
        original = PrometheusConfig(enabled=True, port=8888)
        original.save(tmp_path)

        # Simulate restart
        loaded = PrometheusConfig.load(tmp_path)
        assert loaded.enabled == original.enabled
        assert loaded.port == original.port


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_zero_values(self):
        """Handles zero values correctly."""
        metrics = GovernorMetrics()
        if not PROMETHEUS_AVAILABLE:
            return

        # Should not raise with zeros
        metrics.record_verification(True, 0.0)
        metrics.record_llm_call("m", "p", 0.0, 0, 0, 0.0)

    def test_large_values(self):
        """Handles large values correctly."""
        metrics = GovernorMetrics()
        if not PROMETHEUS_AVAILABLE:
            return

        # Should handle large token counts
        metrics.record_llm_call(
            "m", "p", 100.0,
            input_tokens=1_000_000,
            output_tokens=500_000,
            cost_usd=100.0,
        )

    def test_special_characters_in_labels(self):
        """Handles special characters in labels."""
        metrics = GovernorMetrics()
        if not PROMETHEUS_AVAILABLE:
            return

        # Should handle various strings
        metrics.record_error("error/with/slashes")
        metrics.record_claim("CLAIM:TYPE", "test provenance")

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
    def test_concurrent_updates(self):
        """Handles concurrent metric updates."""
        from prometheus_client import CollectorRegistry
        from concurrent.futures import ThreadPoolExecutor
        import threading

        registry = CollectorRegistry()
        metrics = GovernorMetrics(registry=registry)

        def record_many():
            for _ in range(100):
                metrics.record_proposal()

        # Run concurrent updates
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(record_many) for _ in range(4)]
            for f in futures:
                f.result()

        # Should have 400 total
        assert metrics.proposals_total._value.get() == 400
