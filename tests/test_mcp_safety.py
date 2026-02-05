"""Tests for MCP safety controls module."""

import time
from datetime import timedelta
import threading
import pytest

from governor.mcp_safety import (
    # Rate limiting
    RateLimitStatus,
    RateLimitConfig,
    RateLimitResult,
    RateLimiter,
    RateLimitError,
    # Backpressure
    ShedPolicy,
    BackpressureConfig,
    BackpressureResult,
    BackpressureController,
    BackpressureError,
    # Circuit breakers
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreaker,
    CircuitOpenError,
    get_circuit_breaker,
    # Idempotency
    IdempotencyConfig,
    IdempotencyLayer,
    generate_idempotency_key,
    # Latency
    LatencyBudget,
    LatencyBudgetExceeded,
    LatencyEnforcer,
    DEFAULT_BUDGETS,
    # Fault modeling
    ToolClass,
    TOOL_CLASSIFICATION,
    ErrorResponse,
    FaultHandler,
    # Unified controller
    SafetyConfig,
    SafetyController,
    get_safety_controller,
    execute_with_safety,
)


# -----------------------------------------------------------------------------
# Rate Limiting Tests
# -----------------------------------------------------------------------------


class TestRateLimitStatus:
    def test_all_values(self):
        assert RateLimitStatus.ALLOWED == "allowed"
        assert RateLimitStatus.THROTTLED == "throttled"
        assert RateLimitStatus.REJECTED == "rejected"


class TestRateLimitConfig:
    def test_defaults(self):
        config = RateLimitConfig()
        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.burst_allowance == 10

    def test_custom(self):
        config = RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=500,
            burst_allowance=5,
        )
        assert config.requests_per_minute == 30


class TestRateLimitResult:
    def test_creation(self):
        result = RateLimitResult(
            status=RateLimitStatus.ALLOWED,
            requests_remaining=50,
        )
        assert result.status == RateLimitStatus.ALLOWED
        assert result.requests_remaining == 50

    def test_to_dict(self):
        result = RateLimitResult(
            status=RateLimitStatus.THROTTLED,
            retry_after_seconds=5.0,
        )
        d = result.to_dict()
        assert d["status"] == "throttled"
        assert d["retry_after_seconds"] == 5.0


class TestRateLimiter:
    def test_allows_initial_requests(self):
        limiter = RateLimiter()
        result = limiter.check("client1")
        assert result.status == RateLimitStatus.ALLOWED

    def test_allows_within_burst(self):
        limiter = RateLimiter(RateLimitConfig(burst_allowance=5))
        for i in range(5):
            result = limiter.check("client1")
            assert result.status == RateLimitStatus.ALLOWED
            limiter.record("client1")

    def test_throttles_after_minute_limit(self):
        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=5,
            burst_allowance=3,
        ))
        for i in range(5):
            limiter.record("client1")

        result = limiter.check("client1")
        assert result.status == RateLimitStatus.THROTTLED

    def test_exponential_backoff(self):
        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=2,
            burst_allowance=1,
            backoff_base=2.0,
        ))
        limiter.record("client1")
        limiter.record("client1")

        result1 = limiter.check("client1")
        assert result1.retry_after_seconds == 1.0  # 2^0

        result2 = limiter.check("client1")
        assert result2.retry_after_seconds == 2.0  # 2^1

    def test_get_stats(self):
        limiter = RateLimiter()
        limiter.record("client1")
        limiter.record("client1")

        stats = limiter.get_stats("client1")
        assert stats["minute_count"] == 2
        assert stats["hour_count"] == 2

    def test_thread_safety(self):
        limiter = RateLimiter()
        errors = []

        def worker():
            try:
                for _ in range(100):
                    limiter.check("client1")
                    limiter.record("client1")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# -----------------------------------------------------------------------------
# Backpressure Tests
# -----------------------------------------------------------------------------


class TestShedPolicy:
    def test_all_values(self):
        assert ShedPolicy.OLDEST == "oldest"
        assert ShedPolicy.NEWEST == "newest"
        assert ShedPolicy.RANDOM == "random"


class TestBackpressureConfig:
    def test_defaults(self):
        config = BackpressureConfig()
        assert config.max_queue_depth == 100
        assert config.shed_policy == ShedPolicy.OLDEST


class TestBackpressureController:
    def test_admits_under_limit(self):
        controller = BackpressureController(BackpressureConfig(max_queue_depth=10))
        result = controller.admit("req1")
        assert result.admitted
        assert result.queue_depth == 1

    def test_rejects_at_limit(self):
        controller = BackpressureController(BackpressureConfig(max_queue_depth=2))
        controller.admit("req1")
        controller.admit("req2")

        result = controller.admit("req3")
        assert not result.admitted
        assert result.queue_depth == 2

    def test_release(self):
        controller = BackpressureController(BackpressureConfig(max_queue_depth=2))
        controller.admit("req1")
        controller.admit("req2")

        controller.release("req1")
        result = controller.admit("req3")
        assert result.admitted

    def test_shed_oldest(self):
        controller = BackpressureController(BackpressureConfig(
            max_queue_depth=3,
            shed_policy=ShedPolicy.OLDEST,
        ))
        controller.admit("req1")
        controller.admit("req2")
        controller.admit("req3")

        shed = controller.shed(1)
        assert shed == ["req1"]
        assert controller.queue_depth == 2

    def test_shed_newest(self):
        controller = BackpressureController(BackpressureConfig(
            max_queue_depth=3,
            shed_policy=ShedPolicy.NEWEST,
        ))
        controller.admit("req1")
        controller.admit("req2")
        controller.admit("req3")

        shed = controller.shed(1)
        assert shed == ["req3"]

    def test_get_stats(self):
        controller = BackpressureController(BackpressureConfig(max_queue_depth=10))
        controller.admit("req1")
        controller.admit("req2")

        stats = controller.get_stats()
        assert stats["queue_depth"] == 2
        assert stats["utilization"] == 0.2


# -----------------------------------------------------------------------------
# Circuit Breaker Tests
# -----------------------------------------------------------------------------


class TestCircuitState:
    def test_all_values(self):
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        for _ in range(3):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass

        assert cb.state == CircuitState.OPEN

    def test_open_circuit_raises(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        with pytest.raises(CircuitOpenError) as exc_info:
            cb.call(lambda: "success")

        assert exc_info.value.name == "test"

    def test_success_resets_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        # 2 failures
        for _ in range(2):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass

        # 1 success resets
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED

        # Need 3 more failures now
        for _ in range(2):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass

        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
        ))

        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
            half_open_requests=2,
        ))

        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        time.sleep(0.15)
        cb.call(lambda: "ok")
        cb.call(lambda: "ok")

        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
        ))

        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        assert cb.state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_get_stats(self):
        cb = CircuitBreaker("test")
        stats = cb.get_stats()
        assert stats["name"] == "test"
        assert stats["state"] == "closed"


class TestGetCircuitBreaker:
    def test_creates_and_caches(self):
        # Clear module cache
        from governor import mcp_safety
        mcp_safety.CIRCUIT_BREAKERS.clear()

        cb1 = get_circuit_breaker("test")
        cb2 = get_circuit_breaker("test")
        assert cb1 is cb2


# -----------------------------------------------------------------------------
# Idempotency Tests
# -----------------------------------------------------------------------------


class TestIdempotencyConfig:
    def test_defaults(self):
        config = IdempotencyConfig()
        assert config.key_ttl == timedelta(hours=1)
        assert config.max_cached == 10000


class TestIdempotencyLayer:
    def test_caches_result(self):
        layer = IdempotencyLayer()
        call_count = [0]

        def expensive_fn():
            call_count[0] += 1
            return "result"

        result1, cached1 = layer.get_or_execute("key1", expensive_fn)
        result2, cached2 = layer.get_or_execute("key1", expensive_fn)

        assert result1 == result2 == "result"
        assert not cached1
        assert cached2
        assert call_count[0] == 1

    def test_different_keys_execute_separately(self):
        layer = IdempotencyLayer()
        call_count = [0]

        def fn():
            call_count[0] += 1
            return call_count[0]

        result1, _ = layer.get_or_execute("key1", fn)
        result2, _ = layer.get_or_execute("key2", fn)

        assert result1 == 1
        assert result2 == 2

    def test_expired_entries_reexecute(self):
        layer = IdempotencyLayer(IdempotencyConfig(key_ttl=timedelta(milliseconds=50)))
        call_count = [0]

        def fn():
            call_count[0] += 1
            return call_count[0]

        result1, _ = layer.get_or_execute("key1", fn)
        time.sleep(0.1)
        result2, _ = layer.get_or_execute("key1", fn)

        assert result1 == 1
        assert result2 == 2

    def test_invalidate(self):
        layer = IdempotencyLayer()
        layer.get_or_execute("key1", lambda: "v1")
        assert layer.invalidate("key1")
        assert not layer.invalidate("key1")

    def test_get_stats(self):
        layer = IdempotencyLayer()
        layer.get_or_execute("key1", lambda: "v1")
        layer.get_or_execute("key2", lambda: "v2")

        stats = layer.get_stats()
        assert stats["cached_count"] == 2


class TestGenerateIdempotencyKey:
    def test_deterministic(self):
        key1 = generate_idempotency_key("tool", {"a": 1, "b": 2})
        key2 = generate_idempotency_key("tool", {"a": 1, "b": 2})
        assert key1 == key2

    def test_different_params_different_keys(self):
        key1 = generate_idempotency_key("tool", {"a": 1})
        key2 = generate_idempotency_key("tool", {"a": 2})
        assert key1 != key2


# -----------------------------------------------------------------------------
# Latency Tests
# -----------------------------------------------------------------------------


class TestLatencyBudget:
    def test_creation(self):
        budget = LatencyBudget("test_tool", 500, 300)
        assert budget.tool == "test_tool"
        assert budget.budget_ms == 500
        assert budget.warn_threshold_ms == 300


class TestDefaultBudgets:
    def test_check_text_budget(self):
        assert "governor_check_text" in DEFAULT_BUDGETS
        assert DEFAULT_BUDGETS["governor_check_text"].budget_ms == 500


class TestLatencyEnforcer:
    def test_allows_fast_execution(self):
        enforcer = LatencyEnforcer()
        result = enforcer.execute_with_budget("test", lambda: "ok", budget_ms=1000)
        assert result == "ok"

    def test_raises_on_exceeded(self):
        enforcer = LatencyEnforcer()

        def slow_fn():
            time.sleep(0.1)
            return "ok"

        with pytest.raises(LatencyBudgetExceeded) as exc_info:
            enforcer.execute_with_budget("test", slow_fn, budget_ms=50)

        assert exc_info.value.budget_ms == 50
        assert exc_info.value.elapsed_ms >= 50

    def test_records_metrics(self):
        enforcer = LatencyEnforcer()
        enforcer.execute_with_budget("test", lambda: "ok", budget_ms=1000)
        enforcer.execute_with_budget("test", lambda: "ok", budget_ms=1000)

        stats = enforcer.get_stats("test")
        assert stats["samples"] == 2

    def test_uses_default_budget(self):
        enforcer = LatencyEnforcer({
            "my_tool": LatencyBudget("my_tool", 100, 50)
        })

        # Should use 100ms budget, not default
        result = enforcer.execute_with_budget("my_tool", lambda: "ok")
        assert result == "ok"


# -----------------------------------------------------------------------------
# Fault Modeling Tests
# -----------------------------------------------------------------------------


class TestToolClass:
    def test_all_values(self):
        assert ToolClass.SENSOR == "sensor"
        assert ToolClass.ACTUATOR == "actuator"


class TestToolClassification:
    def test_facts_is_sensor(self):
        assert TOOL_CLASSIFICATION["governor_facts"] == ToolClass.SENSOR

    def test_propose_is_actuator(self):
        assert TOOL_CLASSIFICATION["governor_propose"] == ToolClass.ACTUATOR


class TestErrorResponse:
    def test_creation(self):
        resp = ErrorResponse(
            error="test_error",
            message="Test message",
            retryable=True,
        )
        assert resp.error == "test_error"
        assert resp.retryable

    def test_to_dict(self):
        resp = ErrorResponse(
            error="rate_limited",
            message="Too many requests",
            retryable=True,
            retry_after_seconds=5.0,
        )
        d = resp.to_dict()
        assert d["error"] == "rate_limited"
        assert d["retry_after_seconds"] == 5.0


class TestFaultHandler:
    def test_sensor_is_retryable(self):
        handler = FaultHandler()
        resp = handler.handle_failure("governor_facts", Exception("test"))
        assert resp.retryable
        assert not resp.requires_idempotency_key

    def test_actuator_requires_idempotency(self):
        handler = FaultHandler()
        resp = handler.handle_failure("governor_propose", Exception("test"))
        assert resp.requires_idempotency_key

    def test_is_sensor(self):
        handler = FaultHandler()
        assert handler.is_sensor("governor_facts")
        assert not handler.is_sensor("governor_propose")


# -----------------------------------------------------------------------------
# Safety Controller Tests
# -----------------------------------------------------------------------------


class TestSafetyConfig:
    def test_defaults(self):
        config = SafetyConfig()
        assert config.rate_limiting_enabled
        assert config.backpressure_enabled
        assert config.circuit_breakers_enabled
        assert config.idempotency_enabled
        assert config.latency_budgets_enabled


class TestSafetyController:
    def test_execute_simple(self):
        controller = SafetyController()
        result = controller.execute("test_tool", lambda: "ok")
        assert result == "ok"

    def test_execute_with_idempotency(self):
        controller = SafetyController()
        call_count = [0]

        def fn():
            call_count[0] += 1
            return call_count[0]

        result1 = controller.execute("test", fn, idempotency_key="key1")
        result2 = controller.execute("test", fn, idempotency_key="key1")

        assert result1 == result2 == 1
        assert call_count[0] == 1

    def test_execute_with_circuit_breaker(self):
        controller = SafetyController(SafetyConfig(
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2),
        ))

        for _ in range(2):
            try:
                controller.execute("test", lambda: 1 / 0, circuit="test_circuit")
            except ZeroDivisionError:
                pass

        with pytest.raises(CircuitOpenError):
            controller.execute("test", lambda: "ok", circuit="test_circuit")

    def test_execute_with_rate_limit(self):
        controller = SafetyController(SafetyConfig(
            rate_limiting=RateLimitConfig(
                requests_per_minute=2,
                requests_per_hour=100,
                burst_allowance=1,
            ),
        ))

        # First request OK
        controller.execute("test", lambda: "ok", client_id="client1")
        controller.execute("test", lambda: "ok", client_id="client1")

        # Third should be throttled/rejected
        with pytest.raises(RateLimitError):
            controller.execute("test", lambda: "ok", client_id="client1")

    def test_execute_with_backpressure(self):
        controller = SafetyController(SafetyConfig(
            backpressure=BackpressureConfig(max_queue_depth=1),
        ))

        # This is tricky to test since requests complete quickly
        # Just verify no error on normal execution
        result = controller.execute("test", lambda: "ok")
        assert result == "ok"

    def test_get_stats(self):
        controller = SafetyController()
        controller.execute("test", lambda: "ok")

        stats = controller.get_stats()
        assert "rate_limiting" in stats
        assert "backpressure" in stats
        assert "idempotency" in stats
        assert "latency" in stats
        assert "circuit_breakers" in stats

    def test_disabled_controls(self):
        controller = SafetyController(SafetyConfig(
            rate_limiting_enabled=False,
            backpressure_enabled=False,
            circuit_breakers_enabled=False,
            idempotency_enabled=False,
            latency_budgets_enabled=False,
        ))

        # Should execute without any controls
        result = controller.execute("test", lambda: "ok")
        assert result == "ok"


class TestModuleFunctions:
    def test_get_safety_controller_singleton(self):
        # Reset singleton
        import governor.mcp_safety as mod
        mod._default_controller = None

        c1 = get_safety_controller()
        c2 = get_safety_controller()
        assert c1 is c2

    def test_execute_with_safety(self):
        # Reset singleton
        import governor.mcp_safety as mod
        mod._default_controller = None

        result = execute_with_safety("test", lambda: "ok")
        assert result == "ok"


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline(self):
        """Test all safety controls working together."""
        controller = SafetyController(SafetyConfig(
            rate_limiting=RateLimitConfig(
                requests_per_minute=100,
                burst_allowance=50,
            ),
            backpressure=BackpressureConfig(max_queue_depth=50),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        ))

        # Successful requests
        for i in range(10):
            result = controller.execute(
                "governor_check_text",
                lambda: {"ok": True},
                client_id="test_client",
                idempotency_key=f"key_{i}",
                circuit="verification",
            )
            assert result == {"ok": True}

    def test_graceful_degradation(self):
        """Test that failures are handled gracefully."""
        controller = SafetyController(SafetyConfig(
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=0.1,
            ),
        ))

        # Cause failures
        for _ in range(3):
            try:
                controller.execute(
                    "test",
                    lambda: 1 / 0,
                    circuit="flaky_service",
                )
            except ZeroDivisionError:
                pass

        # Circuit is now open
        with pytest.raises(CircuitOpenError):
            controller.execute(
                "test",
                lambda: "ok",
                circuit="flaky_service",
            )

        # Wait for recovery
        time.sleep(0.15)

        # Should be half-open and allow request
        result = controller.execute(
            "test",
            lambda: "recovered",
            circuit="flaky_service",
        )
        assert result == "recovered"
