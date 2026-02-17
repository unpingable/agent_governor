# SPDX-License-Identifier: Apache-2.0
"""SDK Middleware — drop-in governor enforcement for Anthropic SDK.

Usage:
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

Governor automatically:
- Checks claims in response
- Validates against anchors
- Records to epistemic ledger
- Blocks on violations (configurable)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterator, Protocol
import logging

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------


class EnforcementMode(str, Enum):
    """Enforcement mode for the middleware."""

    ADVISORY = "advisory"  # Log violations, never block
    BLOCKING = "blocking"  # Block on HARD violations, warn on SOFT
    STRICT = "strict"  # Block on any violation


class ViolationSeverity(str, Enum):
    """Severity of a violation."""

    HARD = "hard"  # Kernel constraint violation
    SOFT = "soft"  # Preference violation


@dataclass
class Violation:
    """A detected violation."""

    violation_id: str
    severity: ViolationSeverity
    violation_type: str
    message: str
    location: str | None = None
    suggestion: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {
            "violation_id": self.violation_id,
            "severity": self.severity.value,
            "violation_type": self.violation_type,
            "message": self.message,
            "location": self.location,
            "suggestion": self.suggestion,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MiddlewareConfig:
    """Configuration for governor middleware."""

    # Enforcement mode
    mode: EnforcementMode = EnforcementMode.ADVISORY

    # What to check
    check_claims: bool = True
    check_anchors: bool = True
    check_security: bool = True

    # Ledger integration
    record_to_ledger: bool = True
    ledger_path: str | None = None

    # Hooks
    on_violation: Callable[[Violation], None] | None = None
    on_claim_extracted: Callable[[list], None] | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "check_claims": self.check_claims,
            "check_anchors": self.check_anchors,
            "check_security": self.check_security,
            "record_to_ledger": self.record_to_ledger,
            "ledger_path": self.ledger_path,
        }


class GovernorViolationError(Exception):
    """Raised when violations block a response."""

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        messages = [f"[{v.severity.value}] {v.message}" for v in violations]
        super().__init__(f"Governor blocked response: {'; '.join(messages)}")


# -----------------------------------------------------------------------------
# Message Protocol (for type hints without requiring anthropic)
# -----------------------------------------------------------------------------


class Message(Protocol):
    """Protocol for Anthropic Message response."""

    id: str
    content: list
    model: str
    role: str


class ContentBlock(Protocol):
    """Protocol for content block in message."""

    type: str


class TextBlock(Protocol):
    """Protocol for text content block."""

    type: str
    text: str


# -----------------------------------------------------------------------------
# Middleware Implementation
# -----------------------------------------------------------------------------


def _generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class GovernorMiddleware:
    """Middleware wrapper for Anthropic SDK.

    Drop-in replacement that adds governor enforcement to API calls.
    """

    def __init__(
        self,
        client: Any,
        config: MiddlewareConfig | None = None,
    ):
        """Initialize middleware.

        Args:
            client: Anthropic or AsyncAnthropic client
            config: Middleware configuration
        """
        self.client = client
        self.config = config or MiddlewareConfig()
        self._setup_governor()

        # Track violations for this session
        self._violations: list[Violation] = []

    def _setup_governor(self) -> None:
        """Initialize governor components."""
        # Lazy imports to avoid requiring all modules
        self._signal_extractor = None
        self._continuity_checker = None
        self._security_verifier = None
        self._ledger = None

    @property
    def signal_extractor(self):
        """Lazy-load signal extractor."""
        if self._signal_extractor is None:
            from .claim_signals import SignalExtractor

            self._signal_extractor = SignalExtractor()
        return self._signal_extractor

    @property
    def continuity_checker(self):
        """Lazy-load continuity checker."""
        if self._continuity_checker is None:
            from .continuity import ContinuityChecker, AnchorRegistry

            registry = AnchorRegistry()
            self._continuity_checker = ContinuityChecker(registry)
        return self._continuity_checker

    @property
    def security_verifier(self):
        """Lazy-load security verifier."""
        if self._security_verifier is None:
            from .security import SecurityVerifier

            self._security_verifier = SecurityVerifier()
        return self._security_verifier

    @property
    def ledger(self):
        """Lazy-load epistemic ledger."""
        if self._ledger is None and self.config.record_to_ledger:
            from .epistemic import EpistemicLedger

            path = self.config.ledger_path or ".governor/epistemic.db"
            self._ledger = EpistemicLedger(path)
        return self._ledger

    @property
    def messages(self) -> "GovernedMessages":
        """Return governed messages interface."""
        return GovernedMessages(self.client.messages, self)

    def _pre_request(self, kwargs: dict) -> None:
        """Pre-request hook. Called before API call."""
        # Could add request validation here
        pass

    def _post_response(self, response: Any, kwargs: dict) -> Any:
        """Post-response hook. Called after API call."""
        violations = []

        # Extract text from response
        text = self._extract_text(response)

        # Extract claims from response
        if self.config.check_claims:
            try:
                signals = self.signal_extractor.extract(text)
                if self.config.on_claim_extracted and signals.matches:
                    self.config.on_claim_extracted(signals.matches)

                # Record to ledger
                if self.config.record_to_ledger and self.ledger:
                    self._record_claims_to_ledger(signals, response)
            except Exception as e:
                logger.warning(f"Claim extraction failed: {e}")

        # Check against anchors
        if self.config.check_anchors:
            try:
                anchor_violations = self._check_anchors(text)
                violations.extend(anchor_violations)
            except Exception as e:
                logger.warning(f"Anchor checking failed: {e}")

        # Security check
        if self.config.check_security:
            try:
                security_violations = self._check_security(text)
                violations.extend(security_violations)
            except Exception as e:
                logger.warning(f"Security checking failed: {e}")

        # Handle violations
        if violations:
            self._handle_violations(violations, response)

        return response

    def _extract_text(self, response: Any) -> str:
        """Extract text content from response."""
        if hasattr(response, "content"):
            texts = []
            for block in response.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return "\n".join(texts)
        return ""

    def _check_anchors(self, text: str) -> list[Violation]:
        """Check text against anchors."""
        violations = []

        result = self.continuity_checker.check(text)
        for finding in result.findings:
            violations.append(
                Violation(
                    violation_id=_generate_id("viol"),
                    severity=(
                        ViolationSeverity.HARD
                        if finding.severity == "error"
                        else ViolationSeverity.SOFT
                    ),
                    violation_type="anchor_violation",
                    message=finding.message,
                    location=f"line {finding.line}" if finding.line else None,
                    suggestion=finding.suggestion,
                )
            )

        return violations

    def _check_security(self, text: str) -> list[Violation]:
        """Check text for security issues."""
        violations = []

        findings = self.security_verifier.scan_content(text)
        for finding in findings:
            violations.append(
                Violation(
                    violation_id=_generate_id("viol"),
                    severity=ViolationSeverity.HARD,
                    violation_type=f"security_{finding.get('type', 'unknown')}",
                    message=finding.get("message", "Security issue detected"),
                    location=finding.get("location"),
                    suggestion=finding.get("suggestion"),
                )
            )

        return violations

    def _record_claims_to_ledger(self, signals, response: Any) -> None:
        """Record extracted claims to epistemic ledger."""
        if not self.ledger:
            return

        for match in signals.matches:
            try:
                from .epistemic import Provenance

                self.ledger.create_claim(
                    text=match.text,
                    provenance=Provenance.DERIVED,
                    confidence=0.5,  # Default confidence for extracted claims
                    metadata={
                        "source": "sdk_middleware",
                        "response_id": getattr(response, "id", None),
                        "signal_type": match.signal_type.value,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record claim: {e}")

    def _handle_violations(
        self,
        violations: list[Violation],
        response: Any,
    ) -> None:
        """Handle violations according to mode."""
        # Track violations
        self._violations.extend(violations)

        # Call hook if configured
        if self.config.on_violation:
            for v in violations:
                try:
                    self.config.on_violation(v)
                except Exception as e:
                    logger.warning(f"Violation hook failed: {e}")

        # Log violations
        for v in violations:
            if v.severity == ViolationSeverity.HARD:
                logger.warning(f"HARD violation: {v.message}")
            else:
                logger.info(f"SOFT violation: {v.message}")

        # Check mode and potentially block
        if self.config.mode == EnforcementMode.ADVISORY:
            return  # Log only

        hard_violations = [v for v in violations if v.severity == ViolationSeverity.HARD]

        if self.config.mode == EnforcementMode.BLOCKING and hard_violations:
            raise GovernorViolationError(hard_violations)

        if self.config.mode == EnforcementMode.STRICT and violations:
            raise GovernorViolationError(violations)

    def get_violations(self) -> list[Violation]:
        """Get all violations from this session."""
        return self._violations.copy()

    def clear_violations(self) -> None:
        """Clear violation history."""
        self._violations.clear()

    # Proxy other client attributes
    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to underlying client."""
        return getattr(self.client, name)


class GovernedMessages:
    """Governed wrapper for messages API."""

    def __init__(self, messages: Any, middleware: GovernorMiddleware):
        self._messages = messages
        self._middleware = middleware

    def create(self, **kwargs) -> Any:
        """Create message with governor enforcement."""
        # Pre-request hook
        self._middleware._pre_request(kwargs)

        # Make actual API call
        response = self._messages.create(**kwargs)

        # Post-response hook
        return self._middleware._post_response(response, kwargs)

    def stream(self, **kwargs) -> "GovernedStream":
        """Stream with governor enforcement on completion."""
        self._middleware._pre_request(kwargs)
        stream = self._messages.stream(**kwargs)
        return GovernedStream(stream, self._middleware)

    # Proxy other methods
    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to underlying messages."""
        return getattr(self._messages, name)


class GovernedStream:
    """Wrapper that applies governor checks on stream completion."""

    def __init__(self, stream: Any, middleware: GovernorMiddleware):
        self._stream = stream
        self._middleware = middleware
        self._accumulated_text = ""
        self._response = None

    def __iter__(self) -> Iterator:
        for event in self._stream:
            # Accumulate text from content_block_delta events
            if hasattr(event, "delta") and hasattr(event.delta, "text"):
                self._accumulated_text += event.delta.text
            yield event

        # On stream end, apply checks
        self._middleware._post_response_text(self._accumulated_text)

    def __enter__(self):
        if hasattr(self._stream, "__enter__"):
            self._stream.__enter__()
        return self

    def __exit__(self, *args):
        if hasattr(self._stream, "__exit__"):
            self._stream.__exit__(*args)

    def get_final_text(self) -> str:
        """Get accumulated text from stream."""
        return self._accumulated_text


# Add _post_response_text method to middleware
def _post_response_text(self: GovernorMiddleware, text: str) -> None:
    """Post-response hook for streamed text."""
    violations = []

    # Extract claims from text
    if self.config.check_claims:
        try:
            signals = self.signal_extractor.extract(text)
            if self.config.on_claim_extracted and signals.matches:
                self.config.on_claim_extracted(signals.matches)
        except Exception as e:
            logger.warning(f"Claim extraction failed: {e}")

    # Check against anchors
    if self.config.check_anchors:
        try:
            anchor_violations = self._check_anchors(text)
            violations.extend(anchor_violations)
        except Exception as e:
            logger.warning(f"Anchor checking failed: {e}")

    # Security check
    if self.config.check_security:
        try:
            security_violations = self._check_security(text)
            violations.extend(security_violations)
        except Exception as e:
            logger.warning(f"Security checking failed: {e}")

    # Handle violations (but don't raise for streaming - already delivered)
    if violations:
        # Track and log but don't raise
        self._violations.extend(violations)
        if self.config.on_violation:
            for v in violations:
                try:
                    self.config.on_violation(v)
                except Exception as e:
                    logger.warning(f"Violation hook failed: {e}")


# Patch the method onto the class
GovernorMiddleware._post_response_text = _post_response_text


# -----------------------------------------------------------------------------
# Async Support
# -----------------------------------------------------------------------------


class AsyncGovernorMiddleware:
    """Async middleware wrapper for AsyncAnthropic."""

    def __init__(
        self,
        client: Any,
        config: MiddlewareConfig | None = None,
    ):
        self.client = client
        self.config = config or MiddlewareConfig()
        self._sync_middleware = GovernorMiddleware(client, config)

    @property
    def messages(self) -> "AsyncGovernedMessages":
        return AsyncGovernedMessages(self.client.messages, self._sync_middleware)

    def get_violations(self) -> list[Violation]:
        return self._sync_middleware.get_violations()

    def clear_violations(self) -> None:
        self._sync_middleware.clear_violations()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)


class AsyncGovernedMessages:
    """Async governed wrapper for messages API."""

    def __init__(self, messages: Any, middleware: GovernorMiddleware):
        self._messages = messages
        self._middleware = middleware

    async def create(self, **kwargs) -> Any:
        """Async create with governor enforcement."""
        self._middleware._pre_request(kwargs)
        response = await self._messages.create(**kwargs)
        return self._middleware._post_response(response, kwargs)

    async def stream(self, **kwargs):
        """Async stream with governor enforcement."""
        self._middleware._pre_request(kwargs)
        stream = self._messages.stream(**kwargs)
        return AsyncGovernedStream(stream, self._middleware)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._messages, name)


class AsyncGovernedStream:
    """Async wrapper that applies governor checks on stream completion."""

    def __init__(self, stream: Any, middleware: GovernorMiddleware):
        self._stream = stream
        self._middleware = middleware
        self._accumulated_text = ""

    async def __aiter__(self):
        async for event in self._stream:
            if hasattr(event, "delta") and hasattr(event.delta, "text"):
                self._accumulated_text += event.delta.text
            yield event

        self._middleware._post_response_text(self._accumulated_text)

    async def __aenter__(self):
        if hasattr(self._stream, "__aenter__"):
            await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        if hasattr(self._stream, "__aexit__"):
            await self._stream.__aexit__(*args)
