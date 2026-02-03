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
    GovernorCheckResult,
    ChatBridge,
    create_backend,
    _format_governor_footer,
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


# ============================================================================
# TestGovernorCheckResult
# ============================================================================


class TestGovernorCheckResult:
    """Tests for GovernorCheckResult dataclass."""

    def test_check_result_dataclass(self) -> None:
        result = GovernorCheckResult(
            violations=[{"message": "bad"}],
            checked_anchors=3,
            passed=False,
        )
        assert result.violations == [{"message": "bad"}]
        assert result.checked_anchors == 3
        assert result.passed is False

    def test_check_result_empty(self) -> None:
        result = GovernorCheckResult(violations=[], checked_anchors=0, passed=True)
        assert result.violations == []
        assert result.passed is True


# ============================================================================
# TestFormatGovernorFooter
# ============================================================================


class TestFormatGovernorFooter:
    """Tests for _format_governor_footer helper."""

    def test_violations_footer(self) -> None:
        result = GovernorCheckResult(
            violations=[{"message": "banned trope detected"}],
            checked_anchors=2,
            passed=False,
        )
        footer = _format_governor_footer(result, show_ok=True)
        assert footer is not None
        assert "[Governor] banned trope detected" in footer
        assert footer.startswith("\n\n---\n")

    def test_ok_footer_when_anchors_checked(self) -> None:
        result = GovernorCheckResult(violations=[], checked_anchors=3, passed=True)
        footer = _format_governor_footer(result, show_ok=True)
        assert footer == "\n\n---\n[Governor] OK"

    def test_no_footer_when_show_ok_disabled(self) -> None:
        result = GovernorCheckResult(violations=[], checked_anchors=3, passed=True)
        footer = _format_governor_footer(result, show_ok=False)
        assert footer is None

    def test_no_footer_when_no_anchors(self) -> None:
        result = GovernorCheckResult(violations=[], checked_anchors=0, passed=True)
        footer = _format_governor_footer(result, show_ok=True)
        assert footer is None

    def test_multiple_violations(self) -> None:
        result = GovernorCheckResult(
            violations=[{"message": "issue A"}, {"message": "issue B"}],
            checked_anchors=5,
            passed=False,
        )
        footer = _format_governor_footer(result, show_ok=True)
        assert "[Governor] issue A" in footer
        assert "[Governor] issue B" in footer


# ============================================================================
# TestChatBridgeGovernorFooter
# ============================================================================


class TestChatBridgeGovernorFooter:
    """Tests for non-streaming governor footer behavior."""

    def _setup_fiction_context(self, tmp_path: Path) -> GovernorContextManager:
        """Create a fiction context and populate its bible dir."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("fiction-ctx", mode="fiction")
        bible_dir = ctx.root / ".fiction-gov" / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        (bible_dir / "banned_tropes.json").write_text(json.dumps([
            {"name": "chosen_one", "patterns": ["the chosen one"], "severity": "error", "reason": "cliche"},
        ]))
        return cm

    def test_non_streaming_ok_footer(self, tmp_path: Path) -> None:
        """Clean pass in fiction mode appends [Governor] OK."""
        cm = self._setup_fiction_context(tmp_path)
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="Alice walked peacefully.", model="test-model"
        ))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        result = run_async(bridge.chat(
            [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx"
        ))
        assert isinstance(result, ChatResponse)
        assert result.content.endswith("[Governor] OK")

    def test_non_streaming_ok_footer_disabled(self, tmp_path: Path) -> None:
        """show_ok_footer=False suppresses OK footer."""
        cm = self._setup_fiction_context(tmp_path)
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="Alice walked peacefully.", model="test-model"
        ))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=False)

        result = run_async(bridge.chat(
            [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx"
        ))
        assert isinstance(result, ChatResponse)
        assert "[Governor]" not in result.content

    def test_non_streaming_violations_appended(self, tmp_path: Path) -> None:
        """Violations are appended as before."""
        cm = self._setup_fiction_context(tmp_path)
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="She was the chosen one.", model="test-model"
        ))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)

        result = run_async(bridge.chat(
            [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx"
        ))
        assert isinstance(result, ChatResponse)
        assert "[Governor]" in result.content
        # Should be a violation, not OK
        assert "chosen" in result.content.lower()

    def test_non_streaming_no_anchors_no_footer(self, tmp_path: Path) -> None:
        """General mode with no anchors: no footer at all."""
        mock_backend = AsyncMock()
        mock_backend.chat = AsyncMock(return_value=ChatResponse(
            content="Hello world", model="test-model"
        ))
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        cm.create("gen-ctx", mode="general")
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        result = run_async(bridge.chat(
            [ChatMessage(role="user", content="Hi")], "test-model", "gen-ctx"
        ))
        assert isinstance(result, ChatResponse)
        assert result.content == "Hello world"

    def test_non_streaming_default_show_ok(self, tmp_path: Path) -> None:
        """Default show_ok_footer is True."""
        mock_backend = AsyncMock()
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        bridge = ChatBridge(backend=mock_backend, context_manager=cm)
        assert bridge.show_ok_footer is True


# ============================================================================
# TestChatBridgeStreaming
# ============================================================================


class TestChatBridgeStreaming:
    """Tests for streaming governor check behavior."""

    def _setup_fiction_context(self, tmp_path: Path) -> GovernorContextManager:
        """Create a fiction context and populate its bible dir."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("fiction-ctx", mode="fiction")
        bible_dir = ctx.root / ".fiction-gov" / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        (bible_dir / "banned_tropes.json").write_text(json.dumps([
            {"name": "chosen_one", "patterns": ["the chosen one"], "severity": "error", "reason": "cliche"},
        ]))
        return cm

    def _make_stream(self, chunks: list[ChatChunk]):
        """Create an async iterator from a list of chunks."""
        async def stream():
            for c in chunks:
                yield c
        return stream()

    def test_streaming_accumulates_and_checks(self, tmp_path: Path) -> None:
        """Banned trope in streamed content triggers governor violation chunk."""
        cm = self._setup_fiction_context(tmp_path)

        chunks = [
            ChatChunk(content="She was "),
            ChatChunk(content="the chosen one."),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx",
                stream=True,
            )
            return [c async for c in result]

        collected = run_async(collect())
        # Should have content chunks + governor footer chunk + finish chunk
        contents = "".join(c.content for c in collected)
        assert "[Governor]" in contents
        # The last chunk should have finish_reason
        assert collected[-1].finish_reason == "stop"

    def test_streaming_ok_footer_when_clean(self, tmp_path: Path) -> None:
        """Clean pass in fiction mode gets OK chunk in stream."""
        cm = self._setup_fiction_context(tmp_path)

        chunks = [
            ChatChunk(content="Alice walked peacefully."),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx",
                stream=True,
            )
            return [c async for c in result]

        collected = run_async(collect())
        contents = "".join(c.content for c in collected)
        assert "[Governor] OK" in contents
        assert collected[-1].finish_reason == "stop"

    def test_streaming_ok_footer_disabled(self, tmp_path: Path) -> None:
        """show_ok_footer=False suppresses OK in stream."""
        cm = self._setup_fiction_context(tmp_path)

        chunks = [
            ChatChunk(content="Alice walked peacefully."),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=False)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx",
                stream=True,
            )
            return [c async for c in result]

        collected = run_async(collect())
        contents = "".join(c.content for c in collected)
        assert "[Governor]" not in contents

    def test_streaming_no_anchors_no_footer(self, tmp_path: Path) -> None:
        """General mode, no anchors: stream passes through unchanged."""
        chunks = [
            ChatChunk(content="Hello "),
            ChatChunk(content="world"),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        cm.create("gen-ctx", mode="general")
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Hi")], "test-model", "gen-ctx",
                stream=True,
            )
            return [c async for c in result]

        collected = run_async(collect())
        contents = "".join(c.content for c in collected)
        assert contents == "Hello world"
        assert collected[-1].finish_reason == "stop"

    def test_streaming_error_handling(self, tmp_path: Path) -> None:
        """Check failure in stream produces a warning chunk instead of crash."""
        cm = self._setup_fiction_context(tmp_path)

        chunks = [
            ChatChunk(content="Some text."),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx",
                stream=True,
            )
            # Patch after stream is created but before iteration
            with patch.object(GovernorHooks, "check_response_full", side_effect=RuntimeError("boom")):
                return [c async for c in result]

        collected = run_async(collect())
        contents = "".join(c.content for c in collected)
        assert "[Governor] Check failed:" in contents
        assert "boom" in contents
        assert collected[-1].finish_reason == "stop"

    def test_streaming_finish_reason_ordering(self, tmp_path: Path) -> None:
        """Governor footer chunk comes before the finish_reason chunk."""
        cm = self._setup_fiction_context(tmp_path)

        chunks = [
            ChatChunk(content="the chosen one appears"),
            ChatChunk(content="", finish_reason="stop"),
        ]
        mock_backend = AsyncMock()
        mock_backend.stream = MagicMock(return_value=self._make_stream(chunks))
        bridge = ChatBridge(backend=mock_backend, context_manager=cm, show_ok_footer=True)

        async def collect():
            result = await bridge.chat(
                [ChatMessage(role="user", content="Write")], "test-model", "fiction-ctx",
                stream=True,
            )
            return [c async for c in result]

        collected = run_async(collect())
        # Find the governor chunk
        gov_chunks = [c for c in collected if "[Governor]" in c.content]
        assert len(gov_chunks) >= 1
        # Governor chunk should have no finish_reason
        for gc in gov_chunks:
            assert gc.finish_reason is None
        # Last chunk has finish_reason
        assert collected[-1].finish_reason == "stop"
