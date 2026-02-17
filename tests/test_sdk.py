# SPDX-License-Identifier: Apache-2.0
"""Tests for SDK middleware module."""

from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

from governor.sdk import (
    # Types
    EnforcementMode,
    ViolationSeverity,
    Violation,
    MiddlewareConfig,
    GovernorViolationError,
    # Middleware
    GovernorMiddleware,
    GovernedMessages,
    GovernedStream,
    # Async
    AsyncGovernorMiddleware,
    AsyncGovernedMessages,
    _generate_id,
)


# -----------------------------------------------------------------------------
# Test Types
# -----------------------------------------------------------------------------


class TestEnforcementMode:
    def test_all_values(self):
        assert EnforcementMode.ADVISORY == "advisory"
        assert EnforcementMode.BLOCKING == "blocking"
        assert EnforcementMode.STRICT == "strict"


class TestViolationSeverity:
    def test_all_values(self):
        assert ViolationSeverity.HARD == "hard"
        assert ViolationSeverity.SOFT == "soft"


class TestViolation:
    def test_creation(self):
        v = Violation(
            violation_id="viol_123",
            severity=ViolationSeverity.HARD,
            violation_type="security_injection",
            message="SQL injection detected",
        )
        assert v.severity == ViolationSeverity.HARD
        assert v.message == "SQL injection detected"

    def test_to_dict(self):
        v = Violation(
            violation_id="viol_456",
            severity=ViolationSeverity.SOFT,
            violation_type="anchor_violation",
            message="Violates style guide",
            location="line 42",
            suggestion="Consider using active voice",
        )
        d = v.to_dict()
        assert d["severity"] == "soft"
        assert d["location"] == "line 42"
        assert d["suggestion"] == "Consider using active voice"


class TestMiddlewareConfig:
    def test_defaults(self):
        config = MiddlewareConfig()
        assert config.mode == EnforcementMode.ADVISORY
        assert config.check_claims is True
        assert config.check_anchors is True
        assert config.check_security is True
        assert config.record_to_ledger is True

    def test_custom(self):
        config = MiddlewareConfig(
            mode=EnforcementMode.STRICT,
            check_claims=False,
            check_security=False,
        )
        assert config.mode == EnforcementMode.STRICT
        assert config.check_claims is False

    def test_to_dict(self):
        config = MiddlewareConfig(mode=EnforcementMode.BLOCKING)
        d = config.to_dict()
        assert d["mode"] == "blocking"


class TestGovernorViolationError:
    def test_creation(self):
        violations = [
            Violation(
                violation_id="v1",
                severity=ViolationSeverity.HARD,
                violation_type="test",
                message="Error 1",
            ),
            Violation(
                violation_id="v2",
                severity=ViolationSeverity.SOFT,
                violation_type="test",
                message="Error 2",
            ),
        ]
        error = GovernorViolationError(violations)
        assert len(error.violations) == 2
        assert "Error 1" in str(error)


# -----------------------------------------------------------------------------
# Mock Anthropic Classes
# -----------------------------------------------------------------------------


@dataclass
class MockTextBlock:
    type: str = "text"
    text: str = "Test response"


@dataclass
class MockMessage:
    id: str = "msg_123"
    content: list = None
    model: str = "claude-3-sonnet"
    role: str = "assistant"

    def __post_init__(self):
        if self.content is None:
            self.content = [MockTextBlock()]


class MockMessages:
    def create(self, **kwargs):
        return MockMessage()

    def stream(self, **kwargs):
        return MockStream()


class MockStream:
    def __iter__(self):
        yield MockStreamEvent("Hello ")
        yield MockStreamEvent("world!")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@dataclass
class MockDelta:
    text: str


@dataclass
class MockStreamEvent:
    text: str

    @property
    def delta(self):
        return MockDelta(self.text)


class MockClient:
    def __init__(self):
        self.messages = MockMessages()


# -----------------------------------------------------------------------------
# Test Middleware
# -----------------------------------------------------------------------------


class TestGovernorMiddleware:
    def test_creation(self):
        client = MockClient()
        middleware = GovernorMiddleware(client)
        assert middleware.client is client
        assert middleware.config.mode == EnforcementMode.ADVISORY

    def test_with_config(self):
        client = MockClient()
        config = MiddlewareConfig(mode=EnforcementMode.STRICT)
        middleware = GovernorMiddleware(client, config)
        assert middleware.config.mode == EnforcementMode.STRICT

    def test_messages_property(self):
        client = MockClient()
        middleware = GovernorMiddleware(client)
        messages = middleware.messages
        assert isinstance(messages, GovernedMessages)

    def test_extract_text(self):
        middleware = GovernorMiddleware(MockClient())
        response = MockMessage(content=[
            MockTextBlock(text="Hello"),
            MockTextBlock(text="World"),
        ])
        text = middleware._extract_text(response)
        assert "Hello" in text
        assert "World" in text

    def test_extract_text_dict_blocks(self):
        middleware = GovernorMiddleware(MockClient())
        response = MagicMock()
        response.content = [{"type": "text", "text": "Dict content"}]
        text = middleware._extract_text(response)
        assert text == "Dict content"

    def test_get_violations(self):
        middleware = GovernorMiddleware(MockClient())
        assert middleware.get_violations() == []

    def test_clear_violations(self):
        middleware = GovernorMiddleware(MockClient())
        middleware._violations = [
            Violation("v1", ViolationSeverity.HARD, "test", "msg")
        ]
        middleware.clear_violations()
        assert middleware._violations == []

    def test_proxy_attributes(self):
        client = MockClient()
        client.custom_attr = "test_value"
        middleware = GovernorMiddleware(client)
        assert middleware.custom_attr == "test_value"


class TestGovernedMessages:
    def test_create(self):
        client = MockClient()
        middleware = GovernorMiddleware(
            client,
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )
        messages = middleware.messages

        response = messages.create(
            model="claude-3-sonnet",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert response.id == "msg_123"
        assert response.role == "assistant"

    def test_stream(self):
        client = MockClient()
        middleware = GovernorMiddleware(
            client,
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )
        messages = middleware.messages

        stream = messages.stream(
            model="claude-3-sonnet",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert isinstance(stream, GovernedStream)

    def test_proxy_attributes(self):
        client = MockClient()
        client.messages.custom = "value"
        middleware = GovernorMiddleware(client)
        assert middleware.messages.custom == "value"


class TestGovernedStream:
    def test_iteration(self):
        client = MockClient()
        middleware = GovernorMiddleware(
            client,
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )

        stream = GovernedStream(MockStream(), middleware)
        texts = []
        for event in stream:
            texts.append(event.delta.text)

        assert "Hello " in texts
        assert "world!" in texts

    def test_accumulated_text(self):
        client = MockClient()
        middleware = GovernorMiddleware(
            client,
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )

        stream = GovernedStream(MockStream(), middleware)
        for _ in stream:
            pass

        assert stream.get_final_text() == "Hello world!"

    def test_context_manager(self):
        stream = GovernedStream(MockStream(), GovernorMiddleware(
            MockClient(),
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        ))
        with stream as s:
            for _ in s:
                pass


# -----------------------------------------------------------------------------
# Test Enforcement Modes
# -----------------------------------------------------------------------------


class TestEnforcement:
    def test_advisory_mode_logs_only(self):
        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.ADVISORY,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        # Manually add violations
        violations = [
            Violation("v1", ViolationSeverity.HARD, "test", "Hard violation")
        ]

        # Should not raise
        middleware._handle_violations(violations, MockMessage())
        assert len(middleware.get_violations()) == 1

    def test_blocking_mode_raises_on_hard(self):
        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.BLOCKING,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        violations = [
            Violation("v1", ViolationSeverity.HARD, "test", "Hard violation")
        ]

        with pytest.raises(GovernorViolationError) as exc_info:
            middleware._handle_violations(violations, MockMessage())

        assert len(exc_info.value.violations) == 1

    def test_blocking_mode_allows_soft(self):
        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.BLOCKING,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        violations = [
            Violation("v1", ViolationSeverity.SOFT, "test", "Soft violation")
        ]

        # Should not raise
        middleware._handle_violations(violations, MockMessage())

    def test_strict_mode_raises_on_any(self):
        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.STRICT,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        violations = [
            Violation("v1", ViolationSeverity.SOFT, "test", "Soft violation")
        ]

        with pytest.raises(GovernorViolationError):
            middleware._handle_violations(violations, MockMessage())


# -----------------------------------------------------------------------------
# Test Hooks
# -----------------------------------------------------------------------------


class TestHooks:
    def test_violation_hook_called(self):
        called_violations = []

        def on_violation(v):
            called_violations.append(v)

        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.ADVISORY,
            on_violation=on_violation,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        violations = [
            Violation("v1", ViolationSeverity.SOFT, "test", "Test violation")
        ]
        middleware._handle_violations(violations, MockMessage())

        assert len(called_violations) == 1
        assert called_violations[0].violation_id == "v1"

    def test_claim_extracted_hook(self):
        extracted = []

        def on_claim(claims):
            extracted.extend(claims)

        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.ADVISORY,
            on_claim_extracted=on_claim,
            check_claims=True,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        # The actual extraction would require mocking SignalExtractor
        # This just verifies the hook is wired up


# -----------------------------------------------------------------------------
# Test Async Support
# -----------------------------------------------------------------------------


class TestAsyncMiddleware:
    def test_creation(self):
        client = MockClient()
        middleware = AsyncGovernorMiddleware(client)
        assert middleware.client is client

    def test_messages_property(self):
        client = MockClient()
        middleware = AsyncGovernorMiddleware(client)
        messages = middleware.messages
        assert isinstance(messages, AsyncGovernedMessages)

    def test_violations(self):
        client = MockClient()
        middleware = AsyncGovernorMiddleware(client)
        assert middleware.get_violations() == []
        middleware.clear_violations()


# -----------------------------------------------------------------------------
# Test Integration with Governor Components
# -----------------------------------------------------------------------------


class TestIntegrationWithGovernor:
    @patch("governor.sdk.GovernorMiddleware.security_verifier")
    def test_security_check(self, mock_verifier):
        mock_verifier.scan_content.return_value = [
            {"type": "sql_injection", "message": "SQL injection risk"}
        ]

        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.ADVISORY,
            check_claims=False,
            check_anchors=False,
            check_security=True,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        # Force the property to return our mock
        middleware._security_verifier = mock_verifier

        response = MockMessage(content=[MockTextBlock(text="SELECT * FROM users")])
        middleware._post_response(response, {})

        violations = middleware.get_violations()
        assert len(violations) == 1
        assert violations[0].violation_type == "security_sql_injection"


# -----------------------------------------------------------------------------
# Test Helpers
# -----------------------------------------------------------------------------


class TestHelpers:
    def test_generate_id(self):
        id1 = _generate_id("test")
        id2 = _generate_id("test")
        assert id1.startswith("test_")
        assert id2.startswith("test_")
        assert id1 != id2


# -----------------------------------------------------------------------------
# Test Edge Cases
# -----------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_response(self):
        middleware = GovernorMiddleware(
            MockClient(),
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )
        response = MockMessage(content=[])
        text = middleware._extract_text(response)
        assert text == ""

    def test_response_without_content(self):
        middleware = GovernorMiddleware(
            MockClient(),
            MiddlewareConfig(
                check_claims=False,
                check_anchors=False,
                check_security=False,
                record_to_ledger=False,
            ),
        )
        response = MagicMock(spec=[])  # No content attribute
        text = middleware._extract_text(response)
        assert text == ""

    def test_hook_exception_handled(self):
        def bad_hook(v):
            raise RuntimeError("Hook failed")

        client = MockClient()
        config = MiddlewareConfig(
            mode=EnforcementMode.ADVISORY,
            on_violation=bad_hook,
            check_claims=False,
            check_anchors=False,
            check_security=False,
            record_to_ledger=False,
        )
        middleware = GovernorMiddleware(client, config)

        violations = [
            Violation("v1", ViolationSeverity.SOFT, "test", "Test")
        ]

        # Should not raise despite hook failure
        middleware._handle_violations(violations, MockMessage())
