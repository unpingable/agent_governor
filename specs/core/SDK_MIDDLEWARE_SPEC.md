# SDK Middleware Specification

## Version 0.1 — Governor Integration for Anthropic SDK

```yaml
status: canonical
implemented: true
module: src/governor/sdk.py
tests: tests/test_sdk.py (36 tests)
depends_on:
  - KERNEL_CONSTRAINTS_SPEC.md
  - EPISTEMIC_STACK_SPEC.md
enables:
  - SDK-based agent builders getting governor enforcement
  - Third-party agent framework integration
```

---

## Executive Summary

SDK middleware provides **drop-in governor enforcement** for applications using the Anthropic Python SDK. Any SDK-based agent builder gets governor gates without rewriting their code.

**One-liner**: `client = GovernorMiddleware(anthropic.Anthropic())`

---

## 1. The Problem

Currently, governor integration requires:
- MCP server setup (Claude Desktop / Claude Code)
- CLI wrapper (`governor wrap -- command`)
- Direct API calls to governor

SDK users building custom agents have no easy path. They must either:
- Manually call governor before/after each API call
- Ignore governor entirely

---

## 2. The Solution

A middleware wrapper that intercepts Anthropic SDK calls and applies governor enforcement.

```python
from anthropic import Anthropic
from governor.sdk import GovernorMiddleware

# Without governor
client = Anthropic()

# With governor (drop-in replacement)
client = GovernorMiddleware(Anthropic())

# Usage unchanged
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "..."}]
)
# Governor automatically:
# - Checks claims in response
# - Validates against anchors
# - Records to epistemic ledger
# - Blocks on violations (configurable)
```

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Application                      │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  GovernorMiddleware                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Pre-Request │  │ Post-Response│  │  Ledger     │     │
│  │   Hooks     │  │    Hooks     │  │  Integration│     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Anthropic SDK                          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Anthropic API                          │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Core Interface

```python
# src/governor/sdk.py

from anthropic import Anthropic, AsyncAnthropic
from typing import Any, Callable
from dataclasses import dataclass

@dataclass
class MiddlewareConfig:
    """Configuration for governor middleware."""

    # Enforcement mode
    mode: str = "advisory"  # advisory | blocking | strict

    # What to check
    check_claims: bool = True
    check_anchors: bool = True
    check_security: bool = True

    # Ledger integration
    record_to_ledger: bool = True
    ledger_path: str | None = None

    # Hooks
    on_violation: Callable[[Violation], None] | None = None
    on_claim_extracted: Callable[[list[Claim]], None] | None = None


class GovernorMiddleware:
    """Middleware wrapper for Anthropic SDK."""

    def __init__(
        self,
        client: Anthropic | AsyncAnthropic,
        config: MiddlewareConfig | None = None,
    ):
        self.client = client
        self.config = config or MiddlewareConfig()
        self._setup_governor()

    def _setup_governor(self) -> None:
        """Initialize governor components."""
        self.signal_extractor = SignalExtractor()
        self.continuity_checker = ContinuityChecker()
        self.security_verifier = SecurityVerifier()
        if self.config.record_to_ledger:
            self.ledger = EpistemicLedger(self.config.ledger_path)

    @property
    def messages(self) -> "GovernedMessages":
        """Return governed messages interface."""
        return GovernedMessages(self.client.messages, self)


class GovernedMessages:
    """Governed wrapper for messages API."""

    def __init__(self, messages: Any, middleware: GovernorMiddleware):
        self.messages = messages
        self.middleware = middleware

    def create(self, **kwargs) -> Message:
        """Create message with governor enforcement."""
        # Pre-request hook
        self.middleware._pre_request(kwargs)

        # Make actual API call
        response = self.messages.create(**kwargs)

        # Post-response hook
        return self.middleware._post_response(response, kwargs)
```

---

## 5. Enforcement Modes

| Mode | Behavior |
|------|----------|
| `advisory` | Log violations, never block |
| `blocking` | Block on HARD violations, warn on SOFT |
| `strict` | Block on any violation |

```python
class GovernorMiddleware:
    def _post_response(self, response: Message, request: dict) -> Message:
        """Apply post-response checks."""
        violations = []

        # Extract claims from response
        if self.config.check_claims:
            text = self._extract_text(response)
            signals = self.signal_extractor.extract(text)
            if self.config.on_claim_extracted:
                self.config.on_claim_extracted(signals)

        # Check against anchors
        if self.config.check_anchors:
            anchor_violations = self.continuity_checker.check(text)
            violations.extend(anchor_violations)

        # Security check
        if self.config.check_security:
            security_violations = self.security_verifier.scan_content(text)
            violations.extend(security_violations)

        # Handle violations
        if violations:
            self._handle_violations(violations, response)

        # Record to ledger
        if self.config.record_to_ledger:
            self._record_to_ledger(response, signals, violations)

        return response

    def _handle_violations(
        self,
        violations: list[Violation],
        response: Message,
    ) -> None:
        """Handle violations according to mode."""
        if self.config.on_violation:
            for v in violations:
                self.config.on_violation(v)

        if self.config.mode == "advisory":
            return  # Log only

        hard_violations = [v for v in violations if v.severity == "hard"]
        if self.config.mode == "blocking" and hard_violations:
            raise GovernorViolationError(hard_violations)

        if self.config.mode == "strict" and violations:
            raise GovernorViolationError(violations)
```

---

## 6. Async Support

```python
class AsyncGovernorMiddleware:
    """Async middleware wrapper for AsyncAnthropic."""

    def __init__(
        self,
        client: AsyncAnthropic,
        config: MiddlewareConfig | None = None,
    ):
        self.client = client
        self.config = config or MiddlewareConfig()
        self._setup_governor()

    @property
    def messages(self) -> "AsyncGovernedMessages":
        return AsyncGovernedMessages(self.client.messages, self)


class AsyncGovernedMessages:
    async def create(self, **kwargs) -> Message:
        """Async create with governor enforcement."""
        self.middleware._pre_request(kwargs)
        response = await self.messages.create(**kwargs)
        return self.middleware._post_response(response, kwargs)
```

---

## 7. Streaming Support

```python
class GovernedMessages:
    def stream(self, **kwargs) -> "GovernedStream":
        """Stream with governor enforcement on completion."""
        self.middleware._pre_request(kwargs)
        stream = self.messages.stream(**kwargs)
        return GovernedStream(stream, self.middleware)


class GovernedStream:
    """Wrapper that applies governor checks on stream completion."""

    def __init__(self, stream: Any, middleware: GovernorMiddleware):
        self.stream = stream
        self.middleware = middleware
        self.accumulated_text = ""

    def __iter__(self):
        for event in self.stream:
            if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
                self.accumulated_text += event.delta.text
            yield event

        # On stream end, apply checks
        self.middleware._post_response_text(self.accumulated_text)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
```

---

## 8. Usage Examples

### Basic Usage

```python
from anthropic import Anthropic
from governor.sdk import GovernorMiddleware

client = GovernorMiddleware(Anthropic())

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a function to parse JSON"}]
)
```

### With Violation Handler

```python
def on_violation(v: Violation):
    print(f"VIOLATION: {v.type} - {v.message}")
    # Log to monitoring system
    metrics.increment("governor_violations", tags={"type": v.type})

client = GovernorMiddleware(
    Anthropic(),
    config=MiddlewareConfig(
        mode="advisory",
        on_violation=on_violation,
    )
)
```

### Strict Mode for Production

```python
client = GovernorMiddleware(
    Anthropic(),
    config=MiddlewareConfig(
        mode="strict",
        check_claims=True,
        check_anchors=True,
        check_security=True,
        record_to_ledger=True,
        ledger_path="/var/log/governor/ledger.db",
    )
)

try:
    response = client.messages.create(...)
except GovernorViolationError as e:
    # Handle blocked response
    for v in e.violations:
        handle_violation(v)
```

---

## 9. Integration with Existing Governor

```python
class GovernorMiddleware:
    def _setup_governor(self) -> None:
        """Use existing governor components."""
        from governor.claim_signals import SignalExtractor
        from governor.continuity import ContinuityChecker, AnchorRegistry
        from governor.security import SecurityVerifier
        from governor.epistemic import EpistemicLedger

        self.signal_extractor = SignalExtractor()
        self.anchor_registry = AnchorRegistry()
        self.continuity_checker = ContinuityChecker(self.anchor_registry)
        self.security_verifier = SecurityVerifier()

        if self.config.record_to_ledger:
            path = self.config.ledger_path or ".governor/epistemic.db"
            self.ledger = EpistemicLedger(path)
```

---

## 10. Success Criteria

| Criterion | Test |
|-----------|------|
| Drop-in replacement | Existing SDK code works unchanged |
| Claim extraction | Claims extracted from responses |
| Anchor checking | Violations detected |
| Security scanning | Unsafe patterns caught |
| Ledger recording | Claims recorded to epistemic ledger |
| Mode enforcement | Advisory logs, blocking blocks |
| Async support | Works with AsyncAnthropic |
| Streaming support | Checks applied on stream end |

---

## 11. Implementation Notes

### What Exists

- `claim_signals.py` — Signal extraction
- `continuity.py` — Anchor checking
- `security.py` — Security verification
- `epistemic.py` — Ledger persistence

### What Needs Building

| Component | Effort |
|-----------|--------|
| `sdk.py` module | Small |
| Middleware wrapper | Small |
| Async wrapper | Small |
| Streaming wrapper | Small |
| Tests | Small |

Total: ~300 lines of new code.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
