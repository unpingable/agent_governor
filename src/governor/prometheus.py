# SPDX-License-Identifier: Apache-2.0
"""
Prometheus metrics export for governor telemetry.

Exposes metrics at /metrics endpoint for Prometheus scraping.

Usage:
    governor prometheus enable              # Start metrics server
    governor prometheus disable             # Stop server
    governor prometheus status              # Show config and metrics

Metrics exported:
    Counters:
    - governor_proposals_total              # Total proposals created
    - governor_verifications_total          # Total verifications (success/failure labels)
    - governor_llm_calls_total              # LLM API calls (model label)
    - governor_tokens_total                 # Tokens consumed (input/output labels)
    - governor_errors_total                 # Errors by type
    - governor_claims_total                 # Claims registered
    - governor_security_scans_total         # Security scans run
    - governor_continuity_checks_total      # Continuity checks (pass/fail)

    Histograms:
    - governor_verification_duration_seconds    # Verification latency
    - governor_llm_call_duration_seconds        # LLM call latency
    - governor_continuity_iterations            # Iterations to convergence

    Gauges:
    - governor_regime                       # Current regime (1=ELASTIC, 2=WARM, 3=DUCTILE, 4=UNSTABLE)
    - governor_stress                       # Current stress level (0.0-1.0)
    - governor_budget_spent_usd             # Budget spent
    - governor_budget_remaining_usd         # Budget remaining
    - governor_active_sessions              # Active autonomous sessions
    - governor_open_proposals               # Proposals in non-terminal state

Design:
    - Optional dependency: prometheus_client
    - Graceful degradation if not installed
    - Thread-safe metric updates
    - Configurable port (default 9090)
    - Integration with TelemetryCollector
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Any
import json
import logging

logger = logging.getLogger(__name__)

# Check for prometheus_client availability
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        Info,
        start_http_server,
        REGISTRY,
        CollectorRegistry,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Stub classes for when prometheus_client isn't installed
    Counter = None
    Histogram = None
    Gauge = None
    Info = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PrometheusConfig:
    """Prometheus metrics configuration."""
    enabled: bool = False
    port: int = 9090
    host: str = "0.0.0.0"

    # Histogram buckets
    duration_buckets: tuple[float, ...] = (
        0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
    )
    iteration_buckets: tuple[float, ...] = (
        1, 2, 3, 4, 5, 7, 10, 15, 20, 30
    )

    def save(self, gov_dir: Path) -> None:
        """Save config to .governor/prometheus.json."""
        config_file = gov_dir / "prometheus.json"
        with open(config_file, 'w') as f:
            json.dump({
                "enabled": self.enabled,
                "port": self.port,
                "host": self.host,
            }, f, indent=2)

    @classmethod
    def load(cls, gov_dir: Path) -> "PrometheusConfig":
        """Load config from .governor/prometheus.json."""
        config_file = gov_dir / "prometheus.json"
        if not config_file.exists():
            return cls()
        try:
            with open(config_file) as f:
                data = json.load(f)
            return cls(
                enabled=data.get("enabled", False),
                port=data.get("port", 9090),
                host=data.get("host", "0.0.0.0"),
            )
        except (json.JSONDecodeError, IOError):
            return cls()


# =============================================================================
# Metrics Registry
# =============================================================================

class GovernorMetrics:
    """
    Prometheus metrics for governor operations.

    Thread-safe metric updates. All metrics are prefixed with 'governor_'.
    """

    def __init__(self, registry: "CollectorRegistry | None" = None):
        """
        Initialize metrics.

        Args:
            registry: Optional custom registry (uses default if None)
        """
        if not PROMETHEUS_AVAILABLE:
            self._enabled = False
            return

        self._enabled = True
        self._registry = registry or REGISTRY

        # =====================================================================
        # Counters
        # =====================================================================

        self.proposals_total = Counter(
            'governor_proposals_total',
            'Total proposals created',
            registry=self._registry,
        )

        self.verifications_total = Counter(
            'governor_verifications_total',
            'Total verifications performed',
            ['status'],  # success, failure
            registry=self._registry,
        )

        self.llm_calls_total = Counter(
            'governor_llm_calls_total',
            'Total LLM API calls',
            ['model', 'provider'],
            registry=self._registry,
        )

        self.tokens_total = Counter(
            'governor_tokens_total',
            'Total tokens consumed',
            ['direction'],  # input, output
            registry=self._registry,
        )

        self.cost_total = Counter(
            'governor_cost_usd_total',
            'Total cost in USD',
            ['model'],
            registry=self._registry,
        )

        self.errors_total = Counter(
            'governor_errors_total',
            'Total errors by type',
            ['error_type'],
            registry=self._registry,
        )

        self.claims_total = Counter(
            'governor_claims_total',
            'Total claims registered',
            ['claim_type', 'provenance'],
            registry=self._registry,
        )

        self.security_scans_total = Counter(
            'governor_security_scans_total',
            'Total security scans',
            ['result'],  # clean, findings
            registry=self._registry,
        )

        self.continuity_checks_total = Counter(
            'governor_continuity_checks_total',
            'Total continuity checks',
            ['result'],  # pass, fail, converged
            registry=self._registry,
        )

        self.regime_transitions_total = Counter(
            'governor_regime_transitions_total',
            'Total regime transitions',
            ['from_regime', 'to_regime'],
            registry=self._registry,
        )

        # =====================================================================
        # Histograms
        # =====================================================================

        self.verification_duration = Histogram(
            'governor_verification_duration_seconds',
            'Verification duration in seconds',
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self._registry,
        )

        self.llm_call_duration = Histogram(
            'governor_llm_call_duration_seconds',
            'LLM call duration in seconds',
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=self._registry,
        )

        self.continuity_iterations = Histogram(
            'governor_continuity_iterations',
            'Iterations to convergence',
            buckets=(1, 2, 3, 4, 5, 7, 10, 15, 20, 30),
            registry=self._registry,
        )

        self.complexity_score = Histogram(
            'governor_task_complexity',
            'Task complexity scores',
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=self._registry,
        )

        # =====================================================================
        # Gauges
        # =====================================================================

        self.regime = Gauge(
            'governor_regime',
            'Current regime (1=ELASTIC, 2=WARM, 3=DUCTILE, 4=UNSTABLE)',
            registry=self._registry,
        )

        self.stress = Gauge(
            'governor_stress',
            'Current stress level (0.0-1.0)',
            registry=self._registry,
        )

        self.budget_spent = Gauge(
            'governor_budget_spent_usd',
            'Budget spent in USD',
            registry=self._registry,
        )

        self.budget_remaining = Gauge(
            'governor_budget_remaining_usd',
            'Budget remaining in USD',
            registry=self._registry,
        )

        self.active_sessions = Gauge(
            'governor_active_sessions',
            'Active autonomous execution sessions',
            registry=self._registry,
        )

        self.open_proposals = Gauge(
            'governor_open_proposals',
            'Proposals in non-terminal state',
            registry=self._registry,
        )

        self.anchors_registered = Gauge(
            'governor_anchors_registered',
            'Continuity anchors registered',
            ['anchor_type'],
            registry=self._registry,
        )

        # =====================================================================
        # Info
        # =====================================================================

        self.info = Info(
            'governor',
            'Governor instance information',
            registry=self._registry,
        )

    @property
    def enabled(self) -> bool:
        """Check if metrics are enabled."""
        return self._enabled

    # =========================================================================
    # Recording Methods
    # =========================================================================

    def record_proposal(self) -> None:
        """Record a proposal creation."""
        if not self._enabled:
            return
        self.proposals_total.inc()

    def record_verification(self, success: bool, duration_seconds: float = 0.0) -> None:
        """Record a verification result."""
        if not self._enabled:
            return
        status = "success" if success else "failure"
        self.verifications_total.labels(status=status).inc()
        if duration_seconds > 0:
            self.verification_duration.observe(duration_seconds)

    def record_llm_call(
        self,
        model: str,
        provider: str = "unknown",
        duration_seconds: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record an LLM API call."""
        if not self._enabled:
            return
        self.llm_calls_total.labels(model=model, provider=provider).inc()
        if duration_seconds > 0:
            self.llm_call_duration.observe(duration_seconds)
        if input_tokens > 0:
            self.tokens_total.labels(direction="input").inc(input_tokens)
        if output_tokens > 0:
            self.tokens_total.labels(direction="output").inc(output_tokens)
        if cost_usd > 0:
            self.cost_total.labels(model=model).inc(cost_usd)

    def record_error(self, error_type: str) -> None:
        """Record an error."""
        if not self._enabled:
            return
        self.errors_total.labels(error_type=error_type).inc()

    def record_claim(self, claim_type: str, provenance: str = "unknown") -> None:
        """Record a claim registration."""
        if not self._enabled:
            return
        self.claims_total.labels(claim_type=claim_type, provenance=provenance).inc()

    def record_security_scan(self, has_findings: bool) -> None:
        """Record a security scan."""
        if not self._enabled:
            return
        result = "findings" if has_findings else "clean"
        self.security_scans_total.labels(result=result).inc()

    def record_continuity_check(
        self,
        passed: bool,
        converged: bool = False,
        iterations: int = 0,
    ) -> None:
        """Record a continuity check."""
        if not self._enabled:
            return
        if converged:
            result = "converged"
        elif passed:
            result = "pass"
        else:
            result = "fail"
        self.continuity_checks_total.labels(result=result).inc()
        if iterations > 0:
            self.continuity_iterations.observe(iterations)

    def record_regime_transition(self, from_regime: str, to_regime: str) -> None:
        """Record a regime transition."""
        if not self._enabled:
            return
        self.regime_transitions_total.labels(
            from_regime=from_regime,
            to_regime=to_regime,
        ).inc()

    def record_complexity(self, score: float) -> None:
        """Record a task complexity score."""
        if not self._enabled:
            return
        self.complexity_score.observe(score)

    # =========================================================================
    # Gauge Setters
    # =========================================================================

    def set_regime(self, regime: str) -> None:
        """Set current regime gauge."""
        if not self._enabled:
            return
        regime_values = {
            "ELASTIC": 1,
            "WARM": 2,
            "DUCTILE": 3,
            "UNSTABLE": 4,
        }
        self.regime.set(regime_values.get(regime, 0))

    def set_stress(self, stress: float) -> None:
        """Set current stress gauge."""
        if not self._enabled:
            return
        self.stress.set(stress)

    def set_budget(self, spent: float, remaining: float) -> None:
        """Set budget gauges."""
        if not self._enabled:
            return
        self.budget_spent.set(spent)
        self.budget_remaining.set(remaining)

    def set_active_sessions(self, count: int) -> None:
        """Set active sessions gauge."""
        if not self._enabled:
            return
        self.active_sessions.set(count)

    def set_open_proposals(self, count: int) -> None:
        """Set open proposals gauge."""
        if not self._enabled:
            return
        self.open_proposals.set(count)

    def set_anchors(self, anchor_type: str, count: int) -> None:
        """Set anchors gauge for a type."""
        if not self._enabled:
            return
        self.anchors_registered.labels(anchor_type=anchor_type).set(count)

    def set_info(self, version: str = "", mode: str = "") -> None:
        """Set instance info."""
        if not self._enabled:
            return
        self.info.info({
            "version": version,
            "mode": mode,
        })


# =============================================================================
# Metrics Server
# =============================================================================

class MetricsServer:
    """
    HTTP server for Prometheus metrics endpoint.

    Runs in a background thread, exposes /metrics.
    """

    def __init__(
        self,
        metrics: GovernorMetrics,
        config: PrometheusConfig,
    ):
        self.metrics = metrics
        self.config = config
        self._server_thread: Thread | None = None
        self._running = False

    def start(self) -> bool:
        """
        Start the metrics server.

        Returns:
            True if started successfully, False otherwise
        """
        if not PROMETHEUS_AVAILABLE:
            logger.warning("prometheus_client not installed, cannot start server")
            return False

        if self._running:
            logger.warning("Metrics server already running")
            return True

        try:
            # Start HTTP server in background thread
            start_http_server(
                port=self.config.port,
                addr=self.config.host,
            )
            self._running = True
            logger.info(f"Prometheus metrics server started on {self.config.host}:{self.config.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            return False

    def stop(self) -> None:
        """Stop the metrics server."""
        # Note: prometheus_client doesn't provide a clean shutdown mechanism
        # The server thread is daemonized and will stop with the process
        self._running = False
        logger.info("Metrics server stop requested (will stop with process)")

    @property
    def running(self) -> bool:
        """Check if server is running."""
        return self._running

    def get_metrics_text(self) -> str:
        """Get current metrics in Prometheus text format."""
        if not PROMETHEUS_AVAILABLE:
            return "# prometheus_client not installed\n"
        return generate_latest().decode('utf-8')


# =============================================================================
# Telemetry Integration
# =============================================================================

class PrometheusTelemetryBackend:
    """
    Telemetry backend that updates Prometheus metrics.

    Integrates with TelemetryCollector to automatically update
    metrics from telemetry events.
    """

    def __init__(self, metrics: GovernorMetrics):
        self.metrics = metrics

    def record(self, event: dict[str, Any]) -> None:
        """
        Record a telemetry event to Prometheus metrics.

        Args:
            event: Telemetry event dict with event_type and fields
        """
        if not self.metrics.enabled:
            return

        event_type = event.get("event_type", "")
        fields = event.get("fields", {})
        duration_ms = event.get("duration_ms", 0)

        if event_type == "proposal":
            self.metrics.record_proposal()

        elif event_type == "verification":
            success = fields.get("success", True)
            duration_s = duration_ms / 1000.0 if duration_ms else 0
            self.metrics.record_verification(success, duration_s)

        elif event_type == "llm_call":
            model = fields.get("model", "unknown")
            provider = fields.get("provider", "unknown")
            duration_s = duration_ms / 1000.0 if duration_ms else 0
            input_tokens = fields.get("input_tokens", 0) or fields.get("tokens_used", 0)
            output_tokens = fields.get("output_tokens", 0)
            cost = fields.get("cost_usd", 0.0)
            self.metrics.record_llm_call(
                model=model,
                provider=provider,
                duration_seconds=duration_s,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )

        elif event_type == "error":
            error_type = fields.get("error_type", "unknown")
            self.metrics.record_error(error_type)

        elif event_type == "claim_registered":
            claim_type = fields.get("claim_type", "unknown")
            provenance = fields.get("provenance", "unknown")
            self.metrics.record_claim(claim_type, provenance)

        elif event_type == "security_scan":
            findings = fields.get("findings_count", 0) > 0
            self.metrics.record_security_scan(findings)

        elif event_type == "continuity_result":
            converged = fields.get("converged", False)
            passed = fields.get("passed", False)
            iterations = fields.get("iterations", 0)
            self.metrics.record_continuity_check(passed, converged, iterations)


# =============================================================================
# Convenience Functions
# =============================================================================

# Global metrics instance (lazily initialized)
_global_metrics: GovernorMetrics | None = None
_global_server: MetricsServer | None = None


def get_metrics() -> GovernorMetrics:
    """Get or create global metrics instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = GovernorMetrics()
    return _global_metrics


def get_server(config: PrometheusConfig | None = None) -> MetricsServer:
    """Get or create global metrics server."""
    global _global_server
    if _global_server is None:
        metrics = get_metrics()
        _global_server = MetricsServer(metrics, config or PrometheusConfig())
    return _global_server


def enable_prometheus(gov_dir: Path, port: int = 9090) -> bool:
    """
    Enable Prometheus metrics and start server.

    Args:
        gov_dir: Governor directory
        port: Port for metrics endpoint

    Returns:
        True if enabled successfully
    """
    config = PrometheusConfig(enabled=True, port=port)
    config.save(gov_dir)

    server = get_server(config)
    return server.start()


def disable_prometheus(gov_dir: Path) -> None:
    """Disable Prometheus metrics."""
    config = PrometheusConfig.load(gov_dir)
    config.enabled = False
    config.save(gov_dir)

    server = get_server()
    server.stop()


def create_telemetry_backend() -> PrometheusTelemetryBackend:
    """Create a Prometheus backend for TelemetryCollector."""
    return PrometheusTelemetryBackend(get_metrics())
