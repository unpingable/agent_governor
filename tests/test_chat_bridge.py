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
# TestGovernorHooksContinuity
# ============================================================================


class TestGovernorHooksContinuity:
    """Tests for GovernorHooks with continuity bridge integration."""

    def _make_context(self, tmp_path: Path, mode: str = "general") -> GovernorContext:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir(parents=True, exist_ok=True)
        return GovernorContext(
            context_id="test",
            mode=mode,
            root=tmp_path,
            governor_dir=gov_dir,
            created_at="2025-01-01",
        )

    def _setup_fiction_bible(self, tmp_path: Path) -> None:
        bible_dir = tmp_path / ".fiction-gov" / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        (bible_dir / "banned_tropes.json").write_text(json.dumps([
            {"name": "chosen_one", "patterns": ["the chosen one"], "severity": "error", "reason": "cliche"},
        ]))
        (bible_dir / "characters.json").write_text(json.dumps([
            {"name": "Alice", "anti_patterns": ["betray her friends"], "voice": {"avoid": ["um"]}},
        ]))

    def _setup_nonfiction_corpus(self, tmp_path: Path) -> None:
        nf_dir = tmp_path / ".nonfiction"
        nf_dir.mkdir(parents=True, exist_ok=True)
        (nf_dir / "corpus.json").write_text(json.dumps({
            "concepts": [{"term": "entropy", "anti_patterns": ["randomness"]}],
            "positions": [{"id": "p1", "claim": "X causes Y", "superseded_by": None}],
        }))

    def _setup_puppet(self, tmp_path: Path) -> None:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir(parents=True, exist_ok=True)
        (gov_dir / "puppet_active.json").write_text(json.dumps({
            "puppet_id": "auditor",
            "voice": {"forbidden_phrases": ["I think"], "required_ticks": ["Source:"]},
        }))

    def test_check_response_fiction_banned_trope(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("She was the chosen one, destined for greatness.")
        assert len(warnings) > 0
        assert any(w["anchor_id"] == "fiction_trope_chosen_one" for w in warnings)

    def test_check_response_fiction_character_anti(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Alice decided to betray her friends.")
        assert any(w["anchor_id"] == "fiction_char_alice_anti" for w in warnings)

    def test_check_response_fiction_no_bible(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Some fiction text.")
        assert warnings == []

    def test_check_response_nonfiction_concept_anti(self, tmp_path: Path) -> None:
        self._setup_nonfiction_corpus(tmp_path)
        ctx = self._make_context(tmp_path, mode="nonfiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("The randomness of the system increased.")
        assert any(w["anchor_id"] == "nf_concept_entropy" for w in warnings)

    def test_check_response_nonfiction_no_corpus(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="nonfiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Academic text.")
        assert warnings == []

    def test_check_response_puppet_forbidden(self, tmp_path: Path) -> None:
        self._setup_puppet(tmp_path)
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("I think this is correct.")
        assert any(w["anchor_id"] == "puppet_auditor_forbidden" for w in warnings)

    def test_check_response_puppet_not_active(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("I think this is correct.")
        assert warnings == []

    def test_check_response_code_mode_empty(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Some code output")
        assert warnings == []

    def test_check_response_general_mode_empty(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="general")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Hello world")
        assert warnings == []

    def test_check_response_clean_passes(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("Alice walked through the garden peacefully.")
        assert warnings == []

    def test_check_response_multiple_violations(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("She was the chosen one and would betray her friends.")
        assert len(warnings) >= 2

    def test_check_response_warning_format(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("the chosen one spoke.")
        assert len(warnings) > 0
        w = warnings[0]
        assert "type" in w
        assert "anchor_id" in w
        assert "anchor_type" in w
        assert "severity" in w
        assert "message" in w
        assert "evidence" in w
        assert w["type"] == "continuity_violation"

    def test_augment_includes_anchor_context(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        system = result[0].content
        assert "ESTABLISHED DEFINITIONS AND CONSTRAINTS" in system

    def test_augment_fiction_with_tropes(self, tmp_path: Path) -> None:
        self._setup_fiction_bible(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        system = result[0].content
        assert "chosen_one" in system.lower() or "FORBIDDEN" in system

    def test_augment_no_data_unchanged(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        system = result[0].content
        # Base fiction prompt present, no ESTABLISHED CONSTRAINTS
        assert "fiction" in system.lower()
        assert "ESTABLISHED DEFINITIONS" not in system

    def test_user_registered_anchors_loaded(self, tmp_path: Path) -> None:
        """User-registered anchors from CLI are loaded in all modes."""
        from governor.continuity import Anchor, AnchorType, Severity, AnchorRegistry

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir(parents=True, exist_ok=True)
        cont_dir = gov_dir / "continuity"
        cont_dir.mkdir(parents=True, exist_ok=True)

        reg = AnchorRegistry()
        reg.register(Anchor(
            id="user_test",
            anchor_type=AnchorType.PROHIBITION,
            description="Do not say hello",
            forbidden_patterns=["hello"],
            severity=Severity.CORRECT,
        ))
        reg.save(cont_dir / "anchors.json")

        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        warnings = hooks.check_response("I said hello to the user.")
        assert any(w["anchor_id"] == "user_test" for w in warnings)


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
