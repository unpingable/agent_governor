# MCP Safety Controls Specification

> **RETIRED-UNUSED 2026-06-16.** The implementation this spec described
> (`src/governor/mcp_safety.py` + `tests/test_mcp_safety.py`) was deleted: it
> had **zero production consumers** — never imported by `mcp_server.py`, the
> daemon, or any gate. The earlier `implemented: true` / `status: canonical`
> frontmatter overstated reality (shipped code ≠ wired code). The **capability
> class** (rate limit / backpressure / circuit breaking / idempotency / latency
> deadline) is sound but is retired pending a forcing case. See
> `specs/gaps/GOV_GAP_MCP_SAFETY_DISPOSITION_001.md` for the disposition ruling
> and the resurrection condition. The spec body below is preserved as historical
> design reference only — it does NOT describe live behavior.

## Version 0.1 — Self-Protective Control Infrastructure

```yaml
status: retired-unused          # was: canonical (overstated — never wired)
implemented: false              # code deleted 2026-06-16, see disposition gap
module: (deleted) src/governor/mcp_safety.py
tests: (deleted) tests/test_mcp_safety.py
disposition: specs/gaps/GOV_GAP_MCP_SAFETY_DISPOSITION_001.md
depends_on:
  - KERNEL_CONSTRAINTS_SPEC.md
enables:
  - (none — was never on a production path)
```

---

## Executive Summary

The MCP server currently exposes 21 tools for governor integration with Claude and other LLM agents. These tools are **advisory** — they provide information and accept proposals but have no self-protective infrastructure.

This spec defines the safety controls needed for production deployment: backpressure, rate limits, circuit breakers, idempotency, latency budgets, and fault modeling.

**Core Principle**: The MCP server must protect itself from misbehaving clients without becoming a bottleneck for well-behaved ones.

---

## 1. Current State

### 1.1 Existing Tools (21)

| Category | Tools |
|----------|-------|
| Core workflow | propose, verify, apply, status |
| Query | facts, decisions, envelope |
| Anchors | get_anchors, get_docket, claim_status |
| Checking | check_text, check_file, check_staleness |
| Resolution | record_ruling, get_constraints_for_fix, reverify |
| Intent | get_intent, set_intent, suggest_profile |
| Override | override, override_list |

### 1.2 What's Missing

| Control | Current State | Risk |
|---------|---------------|------|
| Rate limiting | None | Runaway agent floods server |
| Backpressure | None | Memory exhaustion |
| Circuit breakers | None | Cascading failures |
| Idempotency | None | Duplicate operations |
| Latency budgets | None | Hung requests block others |
| Fault modeling | None | No graceful degradation |

---

## 2. Safety Controls

### 2.1 Rate Limiting

**Rule**: Per-client request limits with exponential backoff.

```python
@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_allowance: int = 10
    backoff_base: float = 1.5
    max_backoff: float = 60.0

class RateLimiter:
    def check(self, client_id: str) -> RateLimitResult:
        """
        Returns:
        - ALLOWED: Request proceeds
        - THROTTLED: Request delayed (backoff seconds in result)
        - REJECTED: Request denied (quota exhausted)
        """
        ...

    def record(self, client_id: str, tool: str) -> None:
        """Record request for rate tracking."""
        ...
```

**Response on limit**:
```json
{
  "error": "rate_limited",
  "retry_after_seconds": 15,
  "requests_remaining": 0,
  "reset_at": "2026-02-05T16:00:00Z"
}
```

---

### 2.2 Backpressure

**Rule**: Reject new requests when queue depth exceeds threshold.

```python
@dataclass
class BackpressureConfig:
    max_queue_depth: int = 100
    max_memory_mb: int = 512
    shed_policy: str = "oldest"  # oldest | newest | random

class BackpressureController:
    def admit(self, request: MCPRequest) -> bool:
        """Return False to shed load."""
        if self.queue_depth > self.config.max_queue_depth:
            return False
        if self.memory_usage_mb > self.config.max_memory_mb:
            return False
        return True

    def shed(self) -> list[str]:
        """Shed requests according to policy, return shed request IDs."""
        ...
```

**Response on backpressure**:
```json
{
  "error": "server_overloaded",
  "retry_after_seconds": 5,
  "queue_depth": 100
}
```

---

### 2.3 Circuit Breakers

**Rule**: Stop calling failing subsystems, fail fast instead.

```python
class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_requests: int = 3

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.state = CircuitState.CLOSED
        self.failures = 0

    def call(self, fn: Callable) -> Any:
        """Execute fn with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(self.name, self.recovery_remaining)

        try:
            result = fn()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
```

**Breakers needed**:
- `ledger_read` — Fact/decision ledger queries
- `ledger_write` — Proposals, rulings
- `file_io` — File checking operations
- `verification` — Verification pipeline

---

### 2.4 Idempotency

**Rule**: Duplicate requests return cached result, don't re-execute.

```python
@dataclass
class IdempotencyConfig:
    key_ttl: timedelta = timedelta(hours=1)
    max_cached: int = 10000

class IdempotencyLayer:
    def __init__(self, config: IdempotencyConfig):
        self.cache: dict[str, CachedResult] = {}

    def get_or_execute(
        self,
        idempotency_key: str,
        fn: Callable[[], Any],
    ) -> Any:
        """Return cached result or execute and cache."""
        if idempotency_key in self.cache:
            cached = self.cache[idempotency_key]
            if not cached.expired:
                return cached.result

        result = fn()
        self.cache[idempotency_key] = CachedResult(result, datetime.now())
        return result
```

**Client usage**:
```json
{
  "tool": "governor_propose",
  "idempotency_key": "client-123-proposal-abc",
  "params": { ... }
}
```

---

### 2.5 Latency Budgets

**Rule**: Requests have deadlines; exceeded = fail fast.

```python
@dataclass
class LatencyBudget:
    tool: str
    budget_ms: int
    warn_threshold_ms: int

DEFAULT_BUDGETS: dict[str, LatencyBudget] = {
    "governor_check_text": LatencyBudget("governor_check_text", 500, 300),
    "governor_check_file": LatencyBudget("governor_check_file", 1000, 600),
    "governor_verify": LatencyBudget("governor_verify", 5000, 3000),
    "governor_propose": LatencyBudget("governor_propose", 2000, 1000),
    # ... etc
}

class LatencyEnforcer:
    def execute_with_budget(
        self,
        tool: str,
        fn: Callable,
        budget_ms: int | None = None,
    ) -> Any:
        """Execute with timeout, raise on budget exceeded."""
        budget = budget_ms or DEFAULT_BUDGETS.get(tool, 5000)
        # Use threading/asyncio timeout
        ...
```

**Response on timeout**:
```json
{
  "error": "latency_budget_exceeded",
  "tool": "governor_verify",
  "budget_ms": 5000,
  "elapsed_ms": 5023
}
```

---

### 2.6 Fault Modeling

**Rule**: Classify tools as sensors vs actuators; different failure modes.

```python
class ToolClass(str, Enum):
    SENSOR = "sensor"      # Read-only, safe to retry
    ACTUATOR = "actuator"  # Mutates state, retry carefully

TOOL_CLASSIFICATION: dict[str, ToolClass] = {
    # Sensors (safe to retry)
    "governor_facts": ToolClass.SENSOR,
    "governor_decisions": ToolClass.SENSOR,
    "governor_status": ToolClass.SENSOR,
    "governor_get_anchors": ToolClass.SENSOR,
    "governor_check_text": ToolClass.SENSOR,
    "governor_check_file": ToolClass.SENSOR,
    "governor_claim_status": ToolClass.SENSOR,

    # Actuators (retry with idempotency key only)
    "governor_propose": ToolClass.ACTUATOR,
    "governor_verify": ToolClass.ACTUATOR,
    "governor_apply": ToolClass.ACTUATOR,
    "governor_record_ruling": ToolClass.ACTUATOR,
    "governor_set_intent": ToolClass.ACTUATOR,
    "governor_override": ToolClass.ACTUATOR,
}

class FaultHandler:
    def handle_failure(self, tool: str, error: Exception) -> ErrorResponse:
        """Return appropriate error response based on tool class."""
        tool_class = TOOL_CLASSIFICATION.get(tool, ToolClass.ACTUATOR)

        if tool_class == ToolClass.SENSOR:
            return ErrorResponse(
                retryable=True,
                retry_after=1,
                message=str(error),
            )
        else:
            return ErrorResponse(
                retryable=False,  # or True only with idempotency key
                message=str(error),
                requires_idempotency_key=True,
            )
```

---

## 3. Integration Architecture

```
Client Request
      │
      ▼
┌─────────────────┐
│  Rate Limiter   │──→ 429 Too Many Requests
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Backpressure   │──→ 503 Service Unavailable
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Idempotency    │──→ Cached Result (if duplicate)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Circuit Breaker │──→ 503 Circuit Open
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Latency Budget  │──→ 504 Gateway Timeout
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Tool Handler  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fault Handler  │──→ Appropriate error response
└─────────────────┘
```

---

## 4. Configuration

```yaml
# .governor/mcp_safety.yaml
rate_limiting:
  enabled: true
  requests_per_minute: 60
  requests_per_hour: 1000
  burst_allowance: 10

backpressure:
  enabled: true
  max_queue_depth: 100
  max_memory_mb: 512
  shed_policy: oldest

circuit_breakers:
  enabled: true
  failure_threshold: 5
  recovery_timeout: 30

idempotency:
  enabled: true
  key_ttl_hours: 1
  max_cached: 10000

latency_budgets:
  enabled: true
  default_ms: 5000
  overrides:
    governor_check_text: 500
    governor_verify: 5000
```

---

## 5. Metrics

```python
class MCPMetrics:
    requests_total: Counter
    requests_rejected: Counter  # by reason
    latency_histogram: Histogram
    circuit_state: Gauge
    queue_depth: Gauge
    cache_hits: Counter
    cache_misses: Counter
```

---

## 6. Success Criteria

| Criterion | Test |
|-----------|------|
| Rate limiting | 100 requests/s rejected after quota |
| Backpressure | Queue > 100 sheds oldest |
| Circuit breaker | 5 failures opens circuit |
| Idempotency | Duplicate request returns cached |
| Latency budget | Slow operation times out |
| Graceful degradation | Sensors retry, actuators require key |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
