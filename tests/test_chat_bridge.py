"""Tests for ChatBridge, backends, and GovernorHooks."""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from governor.chat_bridge import (
    ChatMessage,
    ChatResponse,
    ChatChunk,
    ChatBackend,
    OllamaBackend,
    AnthropicBackend,
    GovernorHooks,
    ChatBridge,
    create_backend,
)
from governor.context_manager import GovernorContext, GovernorContextManager


def run_async(coro):
    """Helper to run async code in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================================
# TestChatMessage
# ============================================================================


class TestChatMessage:
    """Tests for ChatMessage dataclass."""

    def test_creation(self) -> None:
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_role(self) -> None:
        msg = ChatMessage(role="system", content="You are helpful")
        assert msg.role == "system"

    def test_assistant_role(self) -> None:
        msg = ChatMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"


# ============================================================================
# TestChatResponse
# ============================================================================


class TestChatResponse:
    """Tests for ChatResponse dataclass."""

    def test_creation(self) -> None:
        resp = ChatResponse(content="Hello", model="test-model")
        assert resp.content == "Hello"
        assert resp.model == "test-model"

    def test_defaults(self) -> None:
        resp = ChatResponse(content="", model="m")
        assert resp.finish_reason == "stop"
        assert resp.usage["prompt_tokens"] == 0
        assert resp.usage["completion_tokens"] == 0
        assert resp.usage["total_tokens"] == 0

    def test_custom_usage(self) -> None:
        resp = ChatResponse(
            content="Hi",
            model="m",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        assert resp.usage["total_tokens"] == 15


# ============================================================================
# TestChatChunk
# ============================================================================


class TestChatChunk:
    """Tests for ChatChunk dataclass."""

    def test_creation(self) -> None:
        chunk = ChatChunk(content="Hello")
        assert chunk.content == "Hello"
        assert chunk.finish_reason is None

    def test_with_finish(self) -> None:
        chunk = ChatChunk(content="", finish_reason="stop")
        assert chunk.finish_reason == "stop"


# ============================================================================
# TestOllamaBackend
# ============================================================================


class TestOllamaBackend:
    """Tests for OllamaBackend."""

    def test_host_config(self) -> None:
        backend = OllamaBackend(host="http://custom:9999")
        assert backend.host == "http://custom:9999"

    def test_default_host(self) -> None:
        backend = OllamaBackend()
        assert backend.host == "http://localhost:11434"

    def test_trailing_slash_stripped(self) -> None:
        backend = OllamaBackend(host="http://localhost:11434/")
        assert backend.host == "http://localhost:11434"

    def test_chat_mocked(self) -> None:
        """Mocked chat request to Ollama."""
        import httpx

        backend = OllamaBackend()
        mock_response = httpx.Response(
            200,
            json={
                "message": {"content": "Hello from Ollama"},
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
            request=httpx.Request("POST", "http://localhost"),
        )

        async def mock_post(*args, **kwargs):
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            messages = [ChatMessage(role="user", content="Hi")]
            response = run_async(backend.chat(messages, "llama3"))
            assert response.content == "Hello from Ollama"
            assert response.model == "llama3"
            assert response.usage["prompt_tokens"] == 10
            assert response.usage["completion_tokens"] == 5

    def test_list_models_mocked(self) -> None:
        """Mocked list models from Ollama."""
        import httpx

        backend = OllamaBackend()
        mock_response = httpx.Response(
            200,
            json={"models": [{"name": "llama3"}, {"name": "codellama"}]},
            request=httpx.Request("GET", "http://localhost"),
        )

        async def mock_get(*args, **kwargs):
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            models = run_async(backend.list_models())
            assert len(models) == 2
            assert models[0]["id"] == "llama3"
            assert models[1]["id"] == "codellama"

    def test_chat_with_options(self) -> None:
        """Options (temperature, max_tokens) are passed through."""
        import httpx

        backend = OllamaBackend()
        captured_payload = {}
        mock_response = httpx.Response(
            200,
            json={"message": {"content": "OK"}, "prompt_eval_count": 0, "eval_count": 0},
            request=httpx.Request("POST", "http://localhost"),
        )

        async def mock_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            messages = [ChatMessage(role="user", content="Hi")]
            run_async(backend.chat(messages, "llama3", temperature=0.5, max_tokens=100))
            assert captured_payload["options"]["temperature"] == 0.5
            assert captured_payload["options"]["num_predict"] == 100


# ============================================================================
# TestAnthropicBackend
# ============================================================================


class TestAnthropicBackend:
    """Tests for AnthropicBackend."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ValueError, match="API key is required"):
            AnthropicBackend(api_key="")

    def test_creation(self) -> None:
        backend = AnthropicBackend(api_key="sk-test-key")
        assert backend.api_key == "sk-test-key"

    def test_chat_mocked(self) -> None:
        """Mocked chat request to Anthropic."""
        import httpx

        backend = AnthropicBackend(api_key="sk-test")
        mock_response = httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello from Claude"}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "stop_reason": "end_turn",
            },
            request=httpx.Request("POST", "https://api.anthropic.com"),
        )

        async def mock_post(*args, **kwargs):
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            messages = [ChatMessage(role="user", content="Hi")]
            response = run_async(backend.chat(messages, "claude-sonnet-4-20250514"))
            assert response.content == "Hello from Claude"
            assert response.usage["prompt_tokens"] == 10
            assert response.usage["completion_tokens"] == 5

    def test_list_models(self) -> None:
        backend = AnthropicBackend(api_key="sk-test")
        models = run_async(backend.list_models())
        assert len(models) > 0
        ids = [m["id"] for m in models]
        assert any("claude" in mid for mid in ids)

    def test_system_message_separation(self) -> None:
        """System messages should be separated from conversation."""
        import httpx

        backend = AnthropicBackend(api_key="sk-test")
        mock_response = httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "OK"}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
            request=httpx.Request("POST", "https://api.anthropic.com"),
        )

        captured_payload = {}

        async def mock_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            messages = [
                ChatMessage(role="system", content="Be helpful"),
                ChatMessage(role="user", content="Hi"),
            ]
            run_async(backend.chat(messages, "claude-sonnet-4-20250514"))

            # System should be separate field, not in messages
            assert "system" in captured_payload
            assert all(m["role"] != "system" for m in captured_payload["messages"])


# ============================================================================
# TestGovernorHooks
# ============================================================================


class TestGovernorHooks:
    """Tests for GovernorHooks."""

    def _make_context(self, tmp_path: Path, mode: str = "general") -> GovernorContext:
        return GovernorContext(
            context_id="test",
            mode=mode,
            root=tmp_path,
            governor_dir=tmp_path / ".governor",
            created_at="2025-01-01",
        )

    def test_augment_fiction_mode(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        assert result[0].role == "system"
        assert "fiction" in result[0].content.lower()

    def test_augment_code_mode(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Fix bug")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        assert result[0].role == "system"
        assert "code" in result[0].content.lower()

    def test_augment_nonfiction_mode(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="nonfiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Check my paper")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        assert result[0].role == "system"
        assert "non-fiction" in result[0].content.lower()

    def test_augment_general_mode_no_system(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="general")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Hello")]
        result = hooks.augment_messages(messages)
        assert len(result) == 1  # no system prompt added

    def test_augment_skips_if_system_present(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [
            ChatMessage(role="system", content="Custom prompt"),
            ChatMessage(role="user", content="Hi"),
        ]
        result = hooks.augment_messages(messages)
        assert len(result) == 2  # didn't add another system message
        assert result[0].content == "Custom prompt"

    def test_check_response_returns_list(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="general")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Some response text")
        assert isinstance(warnings, list)


# ============================================================================
# TestChatBridge
# ============================================================================


class TestChatBridge:
    """Tests for ChatBridge."""

    def test_routes_to_backend(self, tmp_path: Path) -> None:
        """Bridge routes chat to the underlying backend."""
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="Response", model="test-model"
        ))
        cm = GovernorContextManager(base_dir=tmp_path)
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        messages = [ChatMessage(role="user", content="Hello")]
        result = run_async(bridge.chat(messages, "test-model", "test-ctx"))
        assert isinstance(result, ChatResponse)
        assert result.content == "Response"

    def test_applies_hooks(self, tmp_path: Path) -> None:
        """Bridge applies governor hooks (system prompt injection)."""
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="OK", model="test-model"
        ))
        cm = GovernorContextManager(base_dir=tmp_path)
        cm.create("fiction-ctx", mode="fiction")
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        messages = [ChatMessage(role="user", content="Write a scene")]
        run_async(bridge.chat(messages, "test-model", "fiction-ctx"))

        # Check that the backend received augmented messages (with system prompt)
        call_args = mock_backend.chat.call_args
        sent_messages = call_args[0][0]
        assert len(sent_messages) == 2
        assert sent_messages[0].role == "system"

    def test_list_models(self, tmp_path: Path) -> None:
        mock_backend = AsyncMock()
        mock_backend.list_models = AsyncMock(return_value=[
            {"id": "model-a", "owned_by": "test"}
        ])
        cm = GovernorContextManager(base_dir=tmp_path)
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        models = run_async(bridge.list_models())
        assert len(models) == 1
        assert models[0]["id"] == "model-a"

    def test_get_context(self, tmp_path: Path) -> None:
        mock_backend = MagicMock()
        cm = GovernorContextManager(base_dir=tmp_path)
        cm.create("ctx-1")
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        ctx = bridge.get_context("ctx-1")
        assert ctx is not None
        assert ctx.context_id == "ctx-1"

    def test_get_context_nonexistent(self, tmp_path: Path) -> None:
        mock_backend = MagicMock()
        cm = GovernorContextManager(base_dir=tmp_path)
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        assert bridge.get_context("nope") is None


# ============================================================================
# TestCreateBackend
# ============================================================================


class TestCreateBackend:
    """Tests for create_backend factory."""

    def test_ollama_backend(self) -> None:
        backend = create_backend("ollama")
        assert isinstance(backend, OllamaBackend)

    def test_ollama_custom_host(self) -> None:
        backend = create_backend("ollama", host="http://custom:9999")
        assert isinstance(backend, OllamaBackend)
        assert backend.host == "http://custom:9999"

    def test_anthropic_backend(self) -> None:
        backend = create_backend("anthropic", api_key="sk-test")
        assert isinstance(backend, AnthropicBackend)

    def test_unknown_backend(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend("unknown")
