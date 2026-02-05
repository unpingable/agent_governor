"""MCP Safety Controls — self-protective infrastructure for the MCP server.

The MCP server must protect itself from misbehaving clients without
becoming a bottleneck for well-behaved ones.

Controls:
- Rate limiting: Per-client request limits with exponential backoff
- Backpressure: Reject requests when queue depth exceeds threshold
- Circuit breakers: Stop calling failing subsystems, fail fast
- Idempotency: Duplicate requests return cached result
- Latency budgets: Requests have deadlines, exceeded = fail fast
- Fault modeling: Classify tools as sensors vs actuators
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, TypeVar
import threading
import time
import hashlib
import json


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -----------------------------------------------------------------------------
# Rate Limiting
# -----------------------------------------------------------------------------


class RateLimitStatus(str, Enum):
    """Result of rate limit check."""

    ALLOWED = "allowed"
    THROTTLED = "throttled"  # Request delayed
    REJECTED = "rejected"  # Quota exhausted


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_allowance: int = 10
    backoff_base: float = 1.5
    max_backoff: float = 60.0


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    status: RateLimitStatus
    retry_after_seconds: float = 0.0
    requests_remaining: int = 0
    reset_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "retry_after_seconds": self.retry_after_seconds,
            "requests_remaining": self.requests_remaining,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
        }


class RateLimiter:
    """Per-client rate limiting with exponential backoff."""

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._minute_windows: dict[str, list[datetime]] = {}
        self._hour_windows: dict[str, list[datetime]] = {}
        self._backoff_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def check(self, client_id: str) -> RateLimitResult:
        """Check if request is allowed for client."""
        with self._lock:
            now = _utcnow()
            self._cleanup_windows(client_id, now)

            minute_count = len(self._minute_windows.get(client_id, []))
            hour_count = len(self._hour_windows.get(client_id, []))

            # Check burst allowance
            if minute_count < self.config.burst_allowance:
                return RateLimitResult(
                    status=RateLimitStatus.ALLOWED,
                    requests_remaining=self.config.requests_per_minute - minute_count,
                )

            # Check minute limit
            if minute_count >= self.config.requests_per_minute:
                backoff = self._calculate_backoff(client_id)
                reset_at = now + timedelta(seconds=60)
                return RateLimitResult(
                    status=RateLimitStatus.THROTTLED,
                    retry_after_seconds=backoff,
                    requests_remaining=0,
                    reset_at=reset_at,
                )

            # Check hour limit
            if hour_count >= self.config.requests_per_hour:
                reset_at = now + timedelta(hours=1)
                return RateLimitResult(
                    status=RateLimitStatus.REJECTED,
                    retry_after_seconds=min(
                        (reset_at - now).total_seconds(), self.config.max_backoff
                    ),
                    requests_remaining=0,
                    reset_at=reset_at,
                )

            return RateLimitResult(
                status=RateLimitStatus.ALLOWED,
                requests_remaining=self.config.requests_per_minute - minute_count,
            )

    def record(self, client_id: str, tool: str | None = None) -> None:
        """Record a request for rate tracking."""
        with self._lock:
            now = _utcnow()

            if client_id not in self._minute_windows:
                self._minute_windows[client_id] = []
            if client_id not in self._hour_windows:
                self._hour_windows[client_id] = []

            self._minute_windows[client_id].append(now)
            self._hour_windows[client_id].append(now)

            # Reset backoff on successful request
            self._backoff_counts[client_id] = 0

    def _cleanup_windows(self, client_id: str, now: datetime) -> None:
        """Remove expired entries from windows."""
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        if client_id in self._minute_windows:
            self._minute_windows[client_id] = [
                t for t in self._minute_windows[client_id] if t > minute_ago
            ]
        if client_id in self._hour_windows:
            self._hour_windows[client_id] = [
                t for t in self._hour_windows[client_id] if t > hour_ago
            ]

    def _calculate_backoff(self, client_id: str) -> float:
        """Calculate exponential backoff for client."""
        count = self._backoff_counts.get(client_id, 0)
        self._backoff_counts[client_id] = count + 1

        backoff = self.config.backoff_base ** count
        return min(backoff, self.config.max_backoff)

    def get_stats(self, client_id: str) -> dict:
        """Get rate limit stats for client."""
        with self._lock:
            now = _utcnow()
            self._cleanup_windows(client_id, now)

            return {
                "client_id": client_id,
                "minute_count": len(self._minute_windows.get(client_id, [])),
                "hour_count": len(self._hour_windows.get(client_id, [])),
                "minute_limit": self.config.requests_per_minute,
                "hour_limit": self.config.requests_per_hour,
            }


# -----------------------------------------------------------------------------
# Backpressure
# -----------------------------------------------------------------------------


class ShedPolicy(str, Enum):
    """Policy for shedding requests under backpressure."""

    OLDEST = "oldest"
    NEWEST = "newest"
    RANDOM = "random"


@dataclass
class BackpressureConfig:
    """Configuration for backpressure control."""

    max_queue_depth: int = 100
    max_memory_mb: int = 512
    shed_policy: ShedPolicy = ShedPolicy.OLDEST


@dataclass
class BackpressureResult:
    """Result of backpressure check."""

    admitted: bool
    queue_depth: int
    shed_count: int = 0

    def to_dict(self) -> dict:
        return {
            "admitted": self.admitted,
            "queue_depth": self.queue_depth,
            "shed_count": self.shed_count,
        }


class BackpressureController:
    """Controls request admission under load."""

    def __init__(self, config: BackpressureConfig | None = None):
        self.config = config or BackpressureConfig()
        self._queue: list[str] = []  # Request IDs
        self._lock = threading.Lock()

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def admit(self, request_id: str) -> BackpressureResult:
        """Check if request should be admitted."""
        with self._lock:
            if len(self._queue) >= self.config.max_queue_depth:
                return BackpressureResult(
                    admitted=False,
                    queue_depth=len(self._queue),
                )

            self._queue.append(request_id)
            return BackpressureResult(
                admitted=True,
                queue_depth=len(self._queue),
            )

    def release(self, request_id: str) -> None:
        """Release a request from the queue."""
        with self._lock:
            if request_id in self._queue:
                self._queue.remove(request_id)

    def shed(self, count: int = 1) -> list[str]:
        """Shed requests according to policy."""
        with self._lock:
            shed_ids = []

            for _ in range(min(count, len(self._queue))):
                if self.config.shed_policy == ShedPolicy.OLDEST:
                    shed_ids.append(self._queue.pop(0))
                elif self.config.shed_policy == ShedPolicy.NEWEST:
                    shed_ids.append(self._queue.pop())
                else:  # RANDOM
                    import random

                    idx = random.randrange(len(self._queue))
                    shed_ids.append(self._queue.pop(idx))

            return shed_ids

    def get_stats(self) -> dict:
        """Get backpressure stats."""
        with self._lock:
            return {
                "queue_depth": len(self._queue),
                "max_queue_depth": self.config.max_queue_depth,
                "utilization": len(self._queue) / self.config.max_queue_depth,
            }


# -----------------------------------------------------------------------------
# Circuit Breakers
# -----------------------------------------------------------------------------


class CircuitState(str, Enum):
    """State of a circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_requests: int = 3


class CircuitOpenError(Exception):
    """Raised when circuit is open."""

    def __init__(self, name: str, recovery_remaining: float):
        self.name = name
        self.recovery_remaining = recovery_remaining
        super().__init__(f"Circuit '{name}' is open, recovery in {recovery_remaining:.1f}s")


class CircuitBreaker:
    """Circuit breaker for a subsystem."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes_in_half_open = 0
        self._last_failure_time: datetime | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_recovery()
            return self._state

    @property
    def recovery_remaining(self) -> float:
        with self._lock:
            if self._state != CircuitState.OPEN or self._last_failure_time is None:
                return 0.0
            elapsed = (_utcnow() - self._last_failure_time).total_seconds()
            return max(0.0, self.config.recovery_timeout - elapsed)

    def call(self, fn: Callable[[], Any]) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            self._check_recovery()

            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(self.name, self.recovery_remaining)

        try:
            result = fn()
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def _check_recovery(self) -> None:
        """Check if circuit should transition from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = (_utcnow() - self._last_failure_time).total_seconds()
            if elapsed >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._successes_in_half_open = 0

    def _record_success(self) -> None:
        """Record successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._successes_in_half_open += 1
                if self._successes_in_half_open >= self.config.half_open_requests:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
            else:
                self._failures = 0

    def _record_failure(self) -> None:
        """Record failed call."""
        with self._lock:
            self._failures += 1
            self._last_failure_time = _utcnow()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
            elif self._failures >= self.config.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._successes_in_half_open = 0
            self._last_failure_time = None

    def get_stats(self) -> dict:
        """Get circuit breaker stats."""
        with self._lock:
            self._check_recovery()
            return {
                "name": self.name,
                "state": self._state.value,
                "failures": self._failures,
                "failure_threshold": self.config.failure_threshold,
                "recovery_remaining": self.recovery_remaining,
            }


# Default circuit breakers for MCP subsystems
CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in CIRCUIT_BREAKERS:
        CIRCUIT_BREAKERS[name] = CircuitBreaker(name)
    return CIRCUIT_BREAKERS[name]


# -----------------------------------------------------------------------------
# Idempotency
# -----------------------------------------------------------------------------


@dataclass
class IdempotencyConfig:
    """Configuration for idempotency layer."""

    key_ttl: timedelta = field(default_factory=lambda: timedelta(hours=1))
    max_cached: int = 10000


@dataclass
class CachedResult:
    """A cached result for idempotency."""

    result: Any
    created_at: datetime
    ttl: timedelta

    @property
    def expired(self) -> bool:
        return _utcnow() > self.created_at + self.ttl


class IdempotencyLayer:
    """Ensures duplicate requests return cached results."""

    def __init__(self, config: IdempotencyConfig | None = None):
        self.config = config or IdempotencyConfig()
        self._cache: dict[str, CachedResult] = {}
        self._lock = threading.Lock()

    def get_or_execute(
        self,
        idempotency_key: str,
        fn: Callable[[], Any],
    ) -> tuple[Any, bool]:
        """Return cached result or execute and cache.

        Returns:
            (result, was_cached) tuple
        """
        with self._lock:
            # Check cache
            if idempotency_key in self._cache:
                cached = self._cache[idempotency_key]
                if not cached.expired:
                    return cached.result, True
                else:
                    del self._cache[idempotency_key]

            # Cleanup if too many cached
            if len(self._cache) >= self.config.max_cached:
                self._cleanup()

        # Execute outside lock
        result = fn()

        with self._lock:
            self._cache[idempotency_key] = CachedResult(
                result=result,
                created_at=_utcnow(),
                ttl=self.config.key_ttl,
            )

        return result, False

    def _cleanup(self) -> None:
        """Remove expired entries."""
        expired = [k for k, v in self._cache.items() if v.expired]
        for k in expired:
            del self._cache[k]

        # If still too many, remove oldest
        if len(self._cache) >= self.config.max_cached:
            sorted_keys = sorted(
                self._cache.keys(), key=lambda k: self._cache[k].created_at
            )
            for k in sorted_keys[: len(self._cache) // 2]:
                del self._cache[k]

    def invalidate(self, idempotency_key: str) -> bool:
        """Invalidate a cached result."""
        with self._lock:
            if idempotency_key in self._cache:
                del self._cache[idempotency_key]
                return True
            return False

    def get_stats(self) -> dict:
        """Get idempotency stats."""
        with self._lock:
            active = sum(1 for v in self._cache.values() if not v.expired)
            return {
                "cached_count": len(self._cache),
                "active_count": active,
                "max_cached": self.config.max_cached,
            }


def generate_idempotency_key(tool: str, params: dict) -> str:
    """Generate an idempotency key from tool and params."""
    content = json.dumps({"tool": tool, "params": params}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# -----------------------------------------------------------------------------
# Latency Budgets
# -----------------------------------------------------------------------------


@dataclass
class LatencyBudget:
    """Latency budget for a tool."""

    tool: str
    budget_ms: int
    warn_threshold_ms: int


class LatencyBudgetExceeded(Exception):
    """Raised when latency budget is exceeded."""

    def __init__(self, tool: str, budget_ms: int, elapsed_ms: int):
        self.tool = tool
        self.budget_ms = budget_ms
        self.elapsed_ms = elapsed_ms
        super().__init__(
            f"Latency budget exceeded for '{tool}': {elapsed_ms}ms > {budget_ms}ms"
        )


# Default budgets for MCP tools
DEFAULT_BUDGETS: dict[str, LatencyBudget] = {
    "governor_check_text": LatencyBudget("governor_check_text", 500, 300),
    "governor_check_file": LatencyBudget("governor_check_file", 1000, 600),
    "governor_verify": LatencyBudget("governor_verify", 5000, 3000),
    "governor_propose": LatencyBudget("governor_propose", 2000, 1000),
    "governor_apply": LatencyBudget("governor_apply", 2000, 1000),
    "governor_facts": LatencyBudget("governor_facts", 500, 300),
    "governor_decisions": LatencyBudget("governor_decisions", 500, 300),
    "governor_status": LatencyBudget("governor_status", 500, 300),
    "governor_get_anchors": LatencyBudget("governor_get_anchors", 500, 300),
}

DEFAULT_BUDGET_MS = 5000


class LatencyEnforcer:
    """Enforces latency budgets for tool calls."""

    def __init__(self, budgets: dict[str, LatencyBudget] | None = None):
        self.budgets = budgets or DEFAULT_BUDGETS
        self._metrics: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def execute_with_budget(
        self,
        tool: str,
        fn: Callable[[], Any],
        budget_ms: int | None = None,
    ) -> Any:
        """Execute with timeout, raise on budget exceeded."""
        budget = budget_ms
        if budget is None:
            budget_config = self.budgets.get(tool)
            budget = budget_config.budget_ms if budget_config else DEFAULT_BUDGET_MS

        start = time.monotonic()
        try:
            result = fn()
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            self._record_latency(tool, elapsed_ms)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if elapsed_ms > budget:
            raise LatencyBudgetExceeded(tool, budget, elapsed_ms)

        return result

    def _record_latency(self, tool: str, elapsed_ms: float) -> None:
        """Record latency for metrics."""
        with self._lock:
            if tool not in self._metrics:
                self._metrics[tool] = []
            self._metrics[tool].append(elapsed_ms)
            # Keep last 100 measurements
            if len(self._metrics[tool]) > 100:
                self._metrics[tool] = self._metrics[tool][-100:]

    def get_stats(self, tool: str | None = None) -> dict:
        """Get latency stats."""
        with self._lock:
            if tool:
                latencies = self._metrics.get(tool, [])
                if not latencies:
                    return {"tool": tool, "samples": 0}
                return {
                    "tool": tool,
                    "samples": len(latencies),
                    "avg_ms": sum(latencies) / len(latencies),
                    "min_ms": min(latencies),
                    "max_ms": max(latencies),
                    "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)]
                    if len(latencies) >= 20
                    else None,
                }
            else:
                return {
                    tool: self.get_stats(tool) for tool in self._metrics.keys()
                }


# -----------------------------------------------------------------------------
# Fault Modeling
# -----------------------------------------------------------------------------


class ToolClass(str, Enum):
    """Classification of tools for fault handling."""

    SENSOR = "sensor"  # Read-only, safe to retry
    ACTUATOR = "actuator"  # Mutates state, retry carefully


# Tool classification for MCP tools
TOOL_CLASSIFICATION: dict[str, ToolClass] = {
    # Sensors (safe to retry)
    "governor_facts": ToolClass.SENSOR,
    "governor_decisions": ToolClass.SENSOR,
    "governor_status": ToolClass.SENSOR,
    "governor_envelope": ToolClass.SENSOR,
    "governor_get_anchors": ToolClass.SENSOR,
    "governor_get_docket": ToolClass.SENSOR,
    "governor_claim_status": ToolClass.SENSOR,
    "governor_check_text": ToolClass.SENSOR,
    "governor_check_file": ToolClass.SENSOR,
    "governor_check_staleness": ToolClass.SENSOR,
    "governor_get_intent": ToolClass.SENSOR,
    "governor_suggest_profile": ToolClass.SENSOR,
    "governor_override_list": ToolClass.SENSOR,
    "governor_get_constraints_for_fix": ToolClass.SENSOR,
    # Actuators (retry with idempotency key only)
    "governor_propose": ToolClass.ACTUATOR,
    "governor_verify": ToolClass.ACTUATOR,
    "governor_apply": ToolClass.ACTUATOR,
    "governor_record_ruling": ToolClass.ACTUATOR,
    "governor_set_intent": ToolClass.ACTUATOR,
    "governor_override": ToolClass.ACTUATOR,
    "governor_reverify": ToolClass.ACTUATOR,
}


@dataclass
class ErrorResponse:
    """Structured error response."""

    error: str
    message: str
    retryable: bool
    retry_after_seconds: float = 0.0
    requires_idempotency_key: bool = False

    def to_dict(self) -> dict:
        return {
            "error": self.error,
            "message": self.message,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "requires_idempotency_key": self.requires_idempotency_key,
        }


class FaultHandler:
    """Handles faults according to tool classification."""

    def handle_failure(self, tool: str, error: Exception) -> ErrorResponse:
        """Return appropriate error response based on tool class."""
        tool_class = TOOL_CLASSIFICATION.get(tool, ToolClass.ACTUATOR)

        if tool_class == ToolClass.SENSOR:
            return ErrorResponse(
                error="transient_error",
                message=str(error),
                retryable=True,
                retry_after_seconds=1.0,
            )
        else:
            return ErrorResponse(
                error="operation_failed",
                message=str(error),
                retryable=True,
                requires_idempotency_key=True,
            )

    def is_sensor(self, tool: str) -> bool:
        """Check if tool is a sensor (read-only)."""
        return TOOL_CLASSIFICATION.get(tool, ToolClass.ACTUATOR) == ToolClass.SENSOR

    def is_actuator(self, tool: str) -> bool:
        """Check if tool is an actuator (mutates state)."""
        return TOOL_CLASSIFICATION.get(tool, ToolClass.ACTUATOR) == ToolClass.ACTUATOR


# -----------------------------------------------------------------------------
# Unified Safety Controller
# -----------------------------------------------------------------------------


@dataclass
class SafetyConfig:
    """Unified configuration for all safety controls."""

    rate_limiting: RateLimitConfig = field(default_factory=RateLimitConfig)
    backpressure: BackpressureConfig = field(default_factory=BackpressureConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    idempotency: IdempotencyConfig = field(default_factory=IdempotencyConfig)

    # Feature flags
    rate_limiting_enabled: bool = True
    backpressure_enabled: bool = True
    circuit_breakers_enabled: bool = True
    idempotency_enabled: bool = True
    latency_budgets_enabled: bool = True


T = TypeVar("T")


class SafetyController:
    """Unified controller for all MCP safety controls.

    This is the main interface for applying safety controls to MCP requests.
    """

    def __init__(self, config: SafetyConfig | None = None):
        self.config = config or SafetyConfig()
        self.rate_limiter = RateLimiter(self.config.rate_limiting)
        self.backpressure = BackpressureController(self.config.backpressure)
        self.idempotency = IdempotencyLayer(self.config.idempotency)
        self.latency_enforcer = LatencyEnforcer()
        self.fault_handler = FaultHandler()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create circuit breaker for subsystem."""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                name, self.config.circuit_breaker
            )
        return self._circuit_breakers[name]

    def execute(
        self,
        tool: str,
        fn: Callable[[], T],
        client_id: str = "default",
        idempotency_key: str | None = None,
        circuit: str | None = None,
    ) -> T:
        """Execute a tool call with all safety controls.

        Args:
            tool: Tool name
            fn: Function to execute
            client_id: Client identifier for rate limiting
            idempotency_key: Optional key for idempotency
            circuit: Optional circuit breaker name

        Returns:
            Result of fn()

        Raises:
            Various errors if safety controls reject the request
        """
        request_id = f"{client_id}:{tool}:{_utcnow().timestamp()}"

        # 1. Rate limiting
        if self.config.rate_limiting_enabled:
            result = self.rate_limiter.check(client_id)
            if result.status == RateLimitStatus.REJECTED:
                raise RateLimitError(result)
            elif result.status == RateLimitStatus.THROTTLED:
                # Could sleep here, but for now just record and proceed
                pass

        # 2. Backpressure
        if self.config.backpressure_enabled:
            bp_result = self.backpressure.admit(request_id)
            if not bp_result.admitted:
                raise BackpressureError(bp_result)

        try:
            # 3. Idempotency
            if self.config.idempotency_enabled and idempotency_key:
                cached_result, was_cached = self.idempotency.get_or_execute(
                    idempotency_key, lambda: self._execute_inner(tool, fn, circuit)
                )
                return cached_result

            # Execute without idempotency
            return self._execute_inner(tool, fn, circuit)

        finally:
            # Release backpressure
            if self.config.backpressure_enabled:
                self.backpressure.release(request_id)

            # Record rate limit
            if self.config.rate_limiting_enabled:
                self.rate_limiter.record(client_id, tool)

    def _execute_inner(
        self,
        tool: str,
        fn: Callable[[], T],
        circuit: str | None,
    ) -> T:
        """Execute with circuit breaker and latency budget."""
        # 4. Circuit breaker
        if self.config.circuit_breakers_enabled and circuit:
            cb = self.get_circuit_breaker(circuit)
            if self.config.latency_budgets_enabled:
                return cb.call(lambda: self.latency_enforcer.execute_with_budget(tool, fn))
            else:
                return cb.call(fn)

        # 5. Latency budget only
        if self.config.latency_budgets_enabled:
            return self.latency_enforcer.execute_with_budget(tool, fn)

        # No controls
        return fn()

    def get_stats(self) -> dict:
        """Get stats from all safety controllers."""
        return {
            "rate_limiting": {
                "enabled": self.config.rate_limiting_enabled,
            },
            "backpressure": self.backpressure.get_stats(),
            "idempotency": self.idempotency.get_stats(),
            "latency": self.latency_enforcer.get_stats(),
            "circuit_breakers": {
                name: cb.get_stats() for name, cb in self._circuit_breakers.items()
            },
        }


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(f"Rate limit exceeded: {result.status.value}")


class BackpressureError(Exception):
    """Raised when request is rejected due to backpressure."""

    def __init__(self, result: BackpressureResult):
        self.result = result
        super().__init__(f"Server overloaded: queue depth {result.queue_depth}")


# -----------------------------------------------------------------------------
# Module-level convenience
# -----------------------------------------------------------------------------


_default_controller: SafetyController | None = None


def get_safety_controller() -> SafetyController:
    """Get or create the default safety controller."""
    global _default_controller
    if _default_controller is None:
        _default_controller = SafetyController()
    return _default_controller


def execute_with_safety(
    tool: str,
    fn: Callable[[], T],
    client_id: str = "default",
    idempotency_key: str | None = None,
    circuit: str | None = None,
) -> T:
    """Execute a tool call with safety controls using default controller."""
    return get_safety_controller().execute(
        tool=tool,
        fn=fn,
        client_id=client_id,
        idempotency_key=idempotency_key,
        circuit=circuit,
    )
