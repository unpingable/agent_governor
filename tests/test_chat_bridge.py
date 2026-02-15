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
    ClaudeCodeBackend,
    CodexBackend,
    GovernorHooks,
    GovernorCheckResult,
    ViolationPendingResponse,
    ChatBridge,
    create_backend,
    _format_governor_footer,
    FORMAT_LEAK_CANARY,
    _has_format_leak,
    _build_multiturn_prompt,
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
# TestGovernorHooksFictionType
# ============================================================================


class TestGovernorHooksFictionType:
    """Tests for fiction type and code regime setters."""

    def _make_context(self, tmp_path: Path, mode: str = "fiction") -> GovernorContext:
        return GovernorContext(
            context_id="test",
            mode=mode,
            root=tmp_path,
            governor_dir=tmp_path / ".governor",
            created_at="2025-01-01",
        )

    def test_set_fiction_type_comedy(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        hooks.set_fiction_type("comedy")
        assert hooks.get_fiction_type() == "comedy"

    def test_set_fiction_type_tragedy(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        hooks.set_fiction_type("tragedy")
        assert hooks.get_fiction_type() == "tragedy"

    def test_set_fiction_type_dramedy(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        hooks.set_fiction_type("dramedy")
        assert hooks.get_fiction_type() == "dramedy"

    def test_set_fiction_type_all_valid_types(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        valid_types = [
            "comedy", "tragedy", "drama", "sincerity",
            "dramedy", "tragicomedy", "sincere_drama", "neutral",
        ]
        for ft in valid_types:
            hooks.set_fiction_type(ft)
            assert hooks.get_fiction_type() == ft

    def test_set_fiction_type_invalid_raises(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        with pytest.raises(ValueError) as excinfo:
            hooks.set_fiction_type("invalid_type")
        assert "Invalid fiction type" in str(excinfo.value)
        assert "invalid_type" in str(excinfo.value)

    def test_get_fiction_type_none_when_unset(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        hooks = GovernorHooks(ctx)
        assert hooks.get_fiction_type() is None

    def test_set_code_regime_dev(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        hooks.set_code_regime("dev")
        assert ctx.metadata["code_regime"] == "dev"

    def test_set_code_regime_sre(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        hooks.set_code_regime("sre")
        assert ctx.metadata["code_regime"] == "sre"

    def test_set_code_regime_invalid_raises(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        with pytest.raises(ValueError) as excinfo:
            hooks.set_code_regime("invalid")
        assert "Invalid code regime" in str(excinfo.value)


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

    def test_check_response_code_mode_no_decisions_empty(self, tmp_path: Path) -> None:
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

    # ---- Fiction canon integration ----

    def _setup_fiction_canon(self, tmp_path: Path) -> None:
        canon_dir = tmp_path / ".fiction-gov" / "canon"
        canon_dir.mkdir(parents=True, exist_ok=True)
        (canon_dir / "events.json").write_text(json.dumps([
            {"chapter": 3, "summary": "Alice discovers the letter", "characters": ["Alice"], "location": "library"},
        ]))
        (canon_dir / "relationships.json").write_text(json.dumps([
            {"character_a": "Alice", "character_b": "Bob", "type": "siblings", "as_of_chapter": 1},
        ]))
        (canon_dir / "threads.json").write_text(json.dumps([
            {"name": "Missing Key", "status": "active", "planted_chapter": 2, "characters": ["Alice"]},
            {"name": "Old Quest", "status": "resolved"},
        ]))

    def test_fiction_canon_events_loaded(self, tmp_path: Path) -> None:
        self._setup_fiction_canon(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some text")
        # Canon events produce anchors (no violations since CANON has no patterns)
        assert result.checked_anchors >= 1

    def test_fiction_relationships_loaded(self, tmp_path: Path) -> None:
        self._setup_fiction_canon(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some text")
        assert result.checked_anchors >= 2  # at least event + relationship

    def test_fiction_threads_loaded(self, tmp_path: Path) -> None:
        self._setup_fiction_canon(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some text")
        # 1 event + 1 relationship + 1 active thread (resolved skipped) = 3
        assert result.checked_anchors >= 3

    def test_fiction_canon_missing_dir_graceful(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        # No .fiction-gov/canon/ dir at all - should not error
        result = hooks.check_response_full("Some text")
        assert result.passed is True

    def test_fiction_canon_in_system_prompt(self, tmp_path: Path) -> None:
        self._setup_fiction_canon(tmp_path)
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        system = result[0].content
        assert "Alice discovers the letter" in system
        assert "siblings" in system

    # ---- Code decisions integration ----

    def _setup_code_decisions(self, tmp_path: Path) -> None:
        dec_dir = tmp_path / ".governor" / "decisions"
        dec_dir.mkdir(parents=True, exist_ok=True)
        (dec_dir / "index.json").write_text(json.dumps([
            {"topic": "framework", "choice": "React", "rationale": "Community support"},
            {"topic": "testing", "choice": "pytest", "rationale": "Rich plugins"},
        ]))

    def test_code_decisions_loaded(self, tmp_path: Path) -> None:
        self._setup_code_decisions(tmp_path)
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some code output")
        assert result.checked_anchors == 2

    def test_code_decisions_in_system_prompt(self, tmp_path: Path) -> None:
        self._setup_code_decisions(tmp_path)
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Fix the bug")]
        result = hooks.augment_messages(messages)
        system = result[0].content
        assert "framework" in system.lower()
        assert "React" in system

    def test_code_decisions_missing_dir_graceful(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some code output")
        assert result.passed is True
        assert result.checked_anchors == 0

    def test_code_mode_checked_anchors_count(self, tmp_path: Path) -> None:
        self._setup_code_decisions(tmp_path)
        ctx = self._make_context(tmp_path, mode="code")
        hooks = GovernorHooks(ctx)
        result = hooks.check_response_full("Some code output")
        assert result.checked_anchors == 2
        assert result.passed is True

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

    def test_augment_no_bible_data(self, tmp_path: Path) -> None:
        """Even without bible data, fiction mode has writing module anchors."""
        ctx = self._make_context(tmp_path, mode="fiction")
        hooks = GovernorHooks(ctx)
        messages = [ChatMessage(role="user", content="Write a scene")]
        result = hooks.augment_messages(messages)
        assert len(result) == 2
        system = result[0].content
        # Base fiction prompt present with writing module anchors
        assert "fiction" in system.lower()
        # Writing module anchors are now always present for fiction mode
        # Should have governance/tone/constraint anchors
        assert "Governance" in system or "PROHIBITED" in system or "STYLE" in system

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

    def test_claude_code_backend(self) -> None:
        backend = create_backend("claude-code")
        assert isinstance(backend, ClaudeCodeBackend)

    def test_claude_code_custom_path(self) -> None:
        backend = create_backend("claude-code", claude_path="/custom/path/claude")
        assert isinstance(backend, ClaudeCodeBackend)
        assert backend.claude_path == "/custom/path/claude"

    def test_codex_backend(self) -> None:
        backend = create_backend("codex")
        assert isinstance(backend, CodexBackend)

    def test_codex_custom_path(self) -> None:
        backend = create_backend("codex", codex_path="/custom/path/codex")
        assert isinstance(backend, CodexBackend)
        assert backend.codex_path == "/custom/path/codex"

    def test_unknown_backend(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend("unknown")


# ============================================================================
# TestClaudeCodeBackend
# ============================================================================


class TestClaudeCodeBackend:
    """Tests for ClaudeCodeBackend."""

    def test_init_default_path(self) -> None:
        backend = ClaudeCodeBackend()
        assert backend.claude_path == "claude"

    def test_init_custom_path(self) -> None:
        backend = ClaudeCodeBackend(claude_path="/usr/local/bin/claude")
        assert backend.claude_path == "/usr/local/bin/claude"

    def test_extract_system_and_prompt_user_only(self) -> None:
        backend = ClaudeCodeBackend()
        messages = [ChatMessage(role="user", content="Hello")]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == ""
        assert prompt == "Hello"

    def test_extract_system_and_prompt_with_system(self) -> None:
        backend = ClaudeCodeBackend()
        messages = [
            ChatMessage(role="system", content="Be helpful"),
            ChatMessage(role="user", content="Hi"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == "Be helpful"
        assert prompt == "Hi"
        # System messages should NOT be in the user prompt
        assert "Be helpful" not in prompt

    def test_extract_system_and_prompt_conversation(self) -> None:
        backend = ClaudeCodeBackend()
        messages = [
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="4"),
            ChatMessage(role="user", content="Thanks!"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == ""
        # Multi-turn uses XML tags to avoid role markers leaking into output
        assert "<user>\nWhat is 2+2?\n</user>" in prompt
        assert "<assistant>\n4\n</assistant>" in prompt
        assert "<user>\nThanks!\n</user>" in prompt
        assert "<conversation_history" in prompt
        assert "Do not echo" in prompt
        # Canary token for format leak detection
        assert FORMAT_LEAK_CANARY in prompt
        # Regression: old markers caused model to echo [User]/[Assistant] in fiction
        assert "[User]" not in prompt
        assert "[Assistant]" not in prompt

    def test_extract_system_and_prompt_multiple_system(self) -> None:
        """Multiple system messages are concatenated."""
        backend = ClaudeCodeBackend()
        messages = [
            ChatMessage(role="system", content="Rule 1"),
            ChatMessage(role="system", content="Rule 2"),
            ChatMessage(role="user", content="Hi"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert "Rule 1" in system
        assert "Rule 2" in system
        assert prompt == "Hi"

    def test_extract_system_and_prompt_empty(self) -> None:
        backend = ClaudeCodeBackend()
        system, prompt = backend._extract_system_and_prompt([])
        assert system == ""
        assert prompt == ""

    def test_list_models(self) -> None:
        backend = ClaudeCodeBackend()
        models = run_async(backend.list_models())
        assert len(models) > 0
        assert any(m["id"] == "sonnet" for m in models)
        assert all(m["owned_by"] == "claude-code" for m in models)

    def test_chat_command_has_model_flag(self) -> None:
        """Chat command should include --model flag."""
        import asyncio

        backend = ClaudeCodeBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                json.dumps({"result": "ok"}).encode(),
                b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "sonnet"))

        assert "--model" in captured_cmd
        model_idx = captured_cmd.index("--model")
        assert captured_cmd[model_idx + 1] == "sonnet"

    def test_chat_command_has_system_prompt_flag(self) -> None:
        """Chat command should include --system-prompt when system messages present."""
        import asyncio

        backend = ClaudeCodeBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                json.dumps({"result": "ok"}).encode(),
                b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [
                ChatMessage(role="system", content="Be helpful"),
                ChatMessage(role="user", content="Hello"),
            ]
            run_async(backend.chat(messages, "sonnet"))

        assert "--system-prompt" in captured_cmd
        sp_idx = captured_cmd.index("--system-prompt")
        assert captured_cmd[sp_idx + 1] == "Be helpful"

    def test_chat_command_pipes_via_stdin(self) -> None:
        """Prompt should be piped via stdin, not as CLI arg."""
        import asyncio

        backend = ClaudeCodeBackend()

        captured_input = []

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            async def mock_communicate(input=None):
                if input:
                    captured_input.append(input)
                return (json.dumps({"result": "ok"}).encode(), b"")
            proc.communicate = mock_communicate
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "sonnet"))

        assert len(captured_input) == 1
        assert captured_input[0] == b"Hello"

    def test_chat_command_no_system_prompt_flag_when_absent(self) -> None:
        """No --system-prompt flag when no system messages."""
        import asyncio

        backend = ClaudeCodeBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                json.dumps({"result": "ok"}).encode(),
                b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "sonnet"))

        assert "--system-prompt" not in captured_cmd

    def test_stream_command_has_verbose_flag(self) -> None:
        """Stream command should include --verbose (required for stream-json)."""
        import asyncio

        backend = ClaudeCodeBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            # Mock stdin
            proc.stdin = MagicMock()
            proc.stdin.write = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdin.close = MagicMock()
            # Mock stdout that returns empty (no data)
            async def read_empty(n):
                return b""
            proc.stdout = MagicMock()
            proc.stdout.read = read_empty
            # Mock stderr for error handling path
            async def read_stderr():
                return b""
            proc.stderr = MagicMock()
            proc.stderr.read = read_stderr
            proc.returncode = 0
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]

            async def collect():
                chunks = []
                async for chunk in backend.stream(messages, "sonnet"):
                    chunks.append(chunk)
                return chunks

            run_async(collect())

        assert "--verbose" in captured_cmd
        assert "--model" in captured_cmd
        assert "stream-json" in captured_cmd

    def test_chat_json_parsing_result_field(self) -> None:
        """Chat should extract content from data['result'] string."""
        import asyncio

        backend = ClaudeCodeBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                json.dumps({
                    "result": "Hello from Claude!",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }).encode(),
                b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "sonnet"))

        assert response.content == "Hello from Claude!"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 5

    def test_chat_json_array_verbose_output(self) -> None:
        """--verbose + --output-format json returns a JSON array, not a dict."""
        backend = ClaudeCodeBackend()

        # This is the actual format from `claude --print --output-format json --verbose`
        verbose_output = json.dumps([
            {"type": "system", "subtype": "init", "session_id": "abc"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi!"}]}},
            {"type": "result", "subtype": "success", "result": "Hi!",
             "usage": {"input_tokens": 100, "output_tokens": 10}},
        ])

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                verbose_output.encode(), b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "sonnet"))

        assert response.content == "Hi!"
        assert response.usage["prompt_tokens"] == 100
        assert response.usage["completion_tokens"] == 10

    def test_chat_json_array_no_result_item(self) -> None:
        """JSON array without a result item should return empty content."""
        backend = ClaudeCodeBackend()

        verbose_output = json.dumps([
            {"type": "system", "subtype": "init"},
        ])

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(
                verbose_output.encode(), b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "sonnet"))

        assert response.content == ""

    @pytest.mark.asyncio
    async def test_chat_subprocess_error(self) -> None:
        """Test that chat handles subprocess errors gracefully."""
        backend = ClaudeCodeBackend(claude_path="/nonexistent/path")
        messages = [ChatMessage(role="user", content="test")]

        with pytest.raises((FileNotFoundError, RuntimeError)):
            await backend.chat(messages, "sonnet")


# ============================================================================
# TestCodexBackend
# ============================================================================


class TestCodexBackend:
    """Tests for CodexBackend."""

    def test_init_default_path(self) -> None:
        backend = CodexBackend()
        assert backend.codex_path == "codex"

    def test_init_custom_path(self) -> None:
        backend = CodexBackend(codex_path="/usr/local/bin/codex")
        assert backend.codex_path == "/usr/local/bin/codex"

    def test_extract_system_and_prompt_user_only(self) -> None:
        backend = CodexBackend()
        messages = [ChatMessage(role="user", content="Hello")]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == ""
        assert prompt == "Hello"

    def test_extract_system_and_prompt_with_system(self) -> None:
        """System text is extracted separately (prepended to prompt in chat/stream)."""
        backend = CodexBackend()
        messages = [
            ChatMessage(role="system", content="Be helpful"),
            ChatMessage(role="user", content="Hi"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == "Be helpful"
        assert prompt == "Hi"

    def test_extract_system_and_prompt_conversation(self) -> None:
        backend = CodexBackend()
        messages = [
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="4"),
            ChatMessage(role="user", content="Thanks!"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert system == ""
        # Multi-turn uses XML tags to avoid role markers leaking into output
        assert "<user>\nWhat is 2+2?\n</user>" in prompt
        assert "<assistant>\n4\n</assistant>" in prompt
        assert "<user>\nThanks!\n</user>" in prompt
        assert "<conversation_history" in prompt
        assert "Do not echo" in prompt
        # Canary token for format leak detection
        assert FORMAT_LEAK_CANARY in prompt
        # Regression: old markers caused model to echo [User]/[Assistant] in fiction
        assert "[User]" not in prompt
        assert "[Assistant]" not in prompt

    def test_extract_system_and_prompt_multiple_system(self) -> None:
        """Multiple system messages are concatenated."""
        backend = CodexBackend()
        messages = [
            ChatMessage(role="system", content="Rule 1"),
            ChatMessage(role="system", content="Rule 2"),
            ChatMessage(role="user", content="Hi"),
        ]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert "Rule 1" in system
        assert "Rule 2" in system
        assert prompt == "Hi"

    def test_extract_system_and_prompt_empty(self) -> None:
        backend = CodexBackend()
        system, prompt = backend._extract_system_and_prompt([])
        assert system == ""
        assert prompt == ""

    def test_list_models(self) -> None:
        backend = CodexBackend()
        models = run_async(backend.list_models())
        assert len(models) == 3
        assert any(m["id"] == "o3" for m in models)
        assert any(m["id"] == "o4-mini" for m in models)
        assert all(m["owned_by"] == "codex" for m in models)

    def test_chat_command_has_model_flag(self) -> None:
        """Chat command should include -m flag."""
        backend = CodexBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            # Return JSONL with agent_message + turn.completed
            output = (
                '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n'
            )
            proc.communicate = AsyncMock(return_value=(
                output.encode(), b"",
            ))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "o4-mini"))

        assert "-m" in captured_cmd
        model_idx = captured_cmd.index("-m")
        assert captured_cmd[model_idx + 1] == "o4-mini"

    def test_chat_prompt_via_stdin(self) -> None:
        """Prompt should be piped via stdin."""
        backend = CodexBackend()

        captured_input = []

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            async def mock_communicate(input=None):
                if input:
                    captured_input.append(input)
                output = (
                    '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
                    '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n'
                )
                return (output.encode(), b"")
            proc.communicate = mock_communicate
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "o3"))

        assert len(captured_input) == 1
        assert captured_input[0] == b"Hello"

    def test_chat_no_system_flag(self) -> None:
        """Codex has no --system-prompt flag; system is baked into prompt."""
        backend = CodexBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            output = '{"type":"turn.completed","usage":{}}\n'
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [
                ChatMessage(role="system", content="Be helpful"),
                ChatMessage(role="user", content="Hello"),
            ]
            run_async(backend.chat(messages, "o3"))

        assert "--system-prompt" not in captured_cmd

    def test_chat_system_prepended_to_stdin(self) -> None:
        """System text should be prepended to stdin prompt."""
        backend = CodexBackend()

        captured_input = []

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            async def mock_communicate(input=None):
                if input:
                    captured_input.append(input)
                output = '{"type":"turn.completed","usage":{}}\n'
                return (output.encode(), b"")
            proc.communicate = mock_communicate
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [
                ChatMessage(role="system", content="Be helpful"),
                ChatMessage(role="user", content="Hello"),
            ]
            run_async(backend.chat(messages, "o3"))

        assert len(captured_input) == 1
        prompt = captured_input[0].decode("utf-8")
        assert prompt.startswith("[System]: Be helpful")
        assert "Hello" in prompt

    def test_chat_parses_jsonl_content(self) -> None:
        """Extracts content from item.completed with agent_message type."""
        backend = CodexBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            output = (
                '{"type":"thread.started","thread_id":"t1"}\n'
                '{"type":"turn.started"}\n'
                '{"type":"item.completed","item":{"id":"i0","type":"reasoning","text":"thinking..."}}\n'
                '{"type":"item.completed","item":{"id":"i1","type":"agent_message","text":"Hello from Codex!"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":20}}\n'
            )
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "o3"))

        assert response.content == "Hello from Codex!"

    def test_chat_parses_usage(self) -> None:
        """Extracts usage from turn.completed event."""
        backend = CodexBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            output = (
                '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
                '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":20}}\n'
            )
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "o3"))

        assert response.usage["prompt_tokens"] == 100
        assert response.usage["completion_tokens"] == 20
        assert response.usage["total_tokens"] == 120

    def test_chat_ignores_reasoning_items(self) -> None:
        """item.type == 'reasoning' should be skipped, not included in content."""
        backend = CodexBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            output = (
                '{"type":"item.completed","item":{"type":"reasoning","text":"thinking..."}}\n'
                '{"type":"item.completed","item":{"type":"agent_message","text":"answer"}}\n'
                '{"type":"turn.completed","usage":{}}\n'
            )
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            response = run_async(backend.chat(messages, "o3"))

        assert response.content == "answer"
        assert "thinking" not in response.content

    def test_chat_handles_error_event(self) -> None:
        """Error event in JSONL should raise RuntimeError."""
        backend = CodexBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            output = '{"type":"error","message":"rate limit exceeded"}\n'
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            with pytest.raises(RuntimeError, match="rate limit exceeded"):
                run_async(backend.chat(messages, "o3"))

    def test_chat_handles_turn_failed(self) -> None:
        """turn.failed event should raise RuntimeError."""
        backend = CodexBackend()

        async def mock_subprocess_exec(*args, **kwargs):
            proc = MagicMock()
            output = '{"type":"turn.failed","error":{"message":"context too long"}}\n'
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            with pytest.raises(RuntimeError, match="context too long"):
                run_async(backend.chat(messages, "o3"))

    def test_stream_yields_content_chunks(self) -> None:
        """Streaming yields agent_message text as chunks."""
        backend = CodexBackend()

        jsonl_lines = (
            '{"type":"item.completed","item":{"type":"agent_message","text":"Hello "}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"world!"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n'
        )

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            nonlocal call_count
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdin.write = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdin.close = MagicMock()

            data = jsonl_lines.encode()

            async def read_stdout(n):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    return data
                return b""

            proc.stdout = MagicMock()
            proc.stdout.read = read_stdout

            async def read_stderr():
                return b""
            proc.stderr = MagicMock()
            proc.stderr.read = read_stderr
            proc.returncode = 0
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]

            async def collect():
                chunks = []
                async for chunk in backend.stream(messages, "o3"):
                    chunks.append(chunk)
                return chunks

            collected = run_async(collect())

        contents = [c.content for c in collected if c.content]
        assert "Hello " in contents
        assert "world!" in contents

    def test_stream_sends_stop_on_turn_completed(self) -> None:
        """turn.completed event yields a stop chunk."""
        backend = CodexBackend()

        jsonl_lines = (
            '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
            '{"type":"turn.completed","usage":{}}\n'
        )

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            nonlocal call_count
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdin.write = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdin.close = MagicMock()

            async def read_stdout(n):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    return jsonl_lines.encode()
                return b""

            proc.stdout = MagicMock()
            proc.stdout.read = read_stdout

            async def read_stderr():
                return b""
            proc.stderr = MagicMock()
            proc.stderr.read = read_stderr
            proc.returncode = 0
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]

            async def collect():
                chunks = []
                async for chunk in backend.stream(messages, "o3"):
                    chunks.append(chunk)
                return chunks

            collected = run_async(collect())

        # Last chunk should have finish_reason="stop"
        assert collected[-1].finish_reason == "stop"

    def test_stream_handles_error_gracefully(self) -> None:
        """Error mid-stream yields error chunk instead of crashing."""
        backend = CodexBackend()

        jsonl_lines = (
            '{"type":"item.completed","item":{"type":"agent_message","text":"partial"}}\n'
            '{"type":"error","message":"something broke"}\n'
        )

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            nonlocal call_count
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdin.write = MagicMock()
            proc.stdin.drain = AsyncMock()
            proc.stdin.close = MagicMock()

            async def read_stdout(n):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    return jsonl_lines.encode()
                return b""

            proc.stdout = MagicMock()
            proc.stdout.read = read_stdout

            async def read_stderr():
                return b""
            proc.stderr = MagicMock()
            proc.stderr.read = read_stderr
            proc.returncode = 0
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]

            async def collect():
                chunks = []
                async for chunk in backend.stream(messages, "o3"):
                    chunks.append(chunk)
                return chunks

            collected = run_async(collect())

        all_content = "".join(c.content for c in collected)
        assert "partial" in all_content
        assert "something broke" in all_content

    @pytest.mark.asyncio
    async def test_chat_subprocess_error(self) -> None:
        """Test that chat handles nonexistent binary gracefully."""
        backend = CodexBackend(codex_path="/nonexistent/path")
        messages = [ChatMessage(role="user", content="test")]

        with pytest.raises((FileNotFoundError, RuntimeError)):
            await backend.chat(messages, "o3")

    def test_chat_command_has_exec_and_json_flags(self) -> None:
        """Command should include exec, --json, and --skip-git-repo-check."""
        backend = CodexBackend()

        captured_cmd = []

        async def mock_subprocess_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            output = '{"type":"turn.completed","usage":{}}\n'
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            messages = [ChatMessage(role="user", content="Hello")]
            run_async(backend.chat(messages, "o3"))

        assert "exec" in captured_cmd
        assert "--json" in captured_cmd
        assert "--skip-git-repo-check" in captured_cmd
        assert "-" in captured_cmd  # stdin marker


# ============================================================================
# TestFormatLeakDetection
# ============================================================================


class TestFormatLeakDetection:
    """Tests for format leak canary and detection."""

    def test_canary_is_non_natural(self) -> None:
        """Canary token should never appear in normal text."""
        assert "__CANARY_" in FORMAT_LEAK_CANARY
        assert FORMAT_LEAK_CANARY == "__CANARY_9f3c1a__"

    def test_has_format_leak_detects_canary(self) -> None:
        assert _has_format_leak(f"Here is some text {FORMAT_LEAK_CANARY} oops")

    def test_has_format_leak_detects_xml_tags(self) -> None:
        assert _has_format_leak("blah <user> blah")
        assert _has_format_leak("blah </assistant> blah")
        assert _has_format_leak("<conversation_history> stuff")

    def test_has_format_leak_clean_output(self) -> None:
        assert not _has_format_leak("The answer is 42.")
        assert not _has_format_leak("Once upon a time, in a land far away...")
        assert not _has_format_leak("")

    def test_has_format_leak_partial_markers(self) -> None:
        """Substrings of markers that aren't exact shouldn't trigger."""
        assert not _has_format_leak("the conversation history was long")
        assert not _has_format_leak("a user walked into a bar")

    def test_build_multiturn_prompt_contains_canary(self) -> None:
        parts = [("user", "hi"), ("assistant", "hello"), ("user", "bye")]
        prompt = _build_multiturn_prompt(parts)
        assert FORMAT_LEAK_CANARY in prompt
        assert "<user>" in prompt
        assert "</user>" in prompt

    def test_build_multiturn_prompt_strict_mode(self) -> None:
        parts = [("user", "hi"), ("assistant", "hello")]
        normal = _build_multiturn_prompt(parts)
        strict = _build_multiturn_prompt(parts, strict=True)
        assert "Do not reproduce any XML" in strict
        assert "Do not echo" in normal
        # Both have canary
        assert FORMAT_LEAK_CANARY in normal
        assert FORMAT_LEAK_CANARY in strict

    def test_claude_code_retry_on_leak(self) -> None:
        """ClaudeCodeBackend.chat() retries once if format leak detected."""
        backend = ClaudeCodeBackend()
        call_count = 0

        async def mock_run_cli(system_text, user_prompt, model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: response contains leaked markers
                return ChatResponse(
                    content="<user>\nleaked\n</user>\nActual response",
                    model=model,
                )
            else:
                # Retry: clean response
                return ChatResponse(content="Clean response", model=model)

        backend._run_cli = mock_run_cli
        messages = [
            ChatMessage(role="user", content="Tell me a story"),
            ChatMessage(role="assistant", content="Once upon a time"),
            ChatMessage(role="user", content="Continue"),
        ]
        result = run_async(backend.chat(messages, "sonnet"))
        assert call_count == 2
        assert result.content == "Clean response"

    def test_claude_code_no_retry_when_clean(self) -> None:
        """ClaudeCodeBackend.chat() does not retry clean responses."""
        backend = ClaudeCodeBackend()
        call_count = 0

        async def mock_run_cli(system_text, user_prompt, model):
            nonlocal call_count
            call_count += 1
            return ChatResponse(content="A clean story", model=model)

        backend._run_cli = mock_run_cli
        messages = [
            ChatMessage(role="user", content="Tell me a story"),
            ChatMessage(role="assistant", content="Once upon a time"),
            ChatMessage(role="user", content="Continue"),
        ]
        result = run_async(backend.chat(messages, "sonnet"))
        assert call_count == 1
        assert result.content == "A clean story"

    def test_claude_code_max_one_retry(self) -> None:
        """Only one retry — if retry also leaks, return it anyway."""
        backend = ClaudeCodeBackend()
        call_count = 0

        async def mock_run_cli(system_text, user_prompt, model):
            nonlocal call_count
            call_count += 1
            # Both calls leak — should still return after 2
            return ChatResponse(
                content="<assistant>still leaking</assistant>",
                model=model,
            )

        backend._run_cli = mock_run_cli
        messages = [
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content="Hey"),
            ChatMessage(role="user", content="More"),
        ]
        result = run_async(backend.chat(messages, "sonnet"))
        assert call_count == 2  # One original + one retry, no infinite loop
        assert "<assistant>" in result.content  # Leak returned, not stripped

    def test_codex_retry_on_leak(self) -> None:
        """CodexBackend.chat() retries once if format leak detected."""
        backend = CodexBackend()
        call_count = 0

        async def mock_run_cli(combined_prompt, model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ChatResponse(
                    content="<user>\nleaked\n</user>\nResult",
                    model=model,
                )
            else:
                return ChatResponse(content="Clean result", model=model)

        backend._run_cli = mock_run_cli
        messages = [
            ChatMessage(role="user", content="Question"),
            ChatMessage(role="assistant", content="Answer"),
            ChatMessage(role="user", content="Follow-up"),
        ]
        result = run_async(backend.chat(messages, "o3"))
        assert call_count == 2
        assert result.content == "Clean result"

    def test_single_turn_no_canary(self) -> None:
        """Single-turn messages skip the multi-turn wrapper entirely."""
        backend = ClaudeCodeBackend()
        messages = [ChatMessage(role="user", content="Just one message")]
        system, prompt = backend._extract_system_and_prompt(messages)
        assert FORMAT_LEAK_CANARY not in prompt
        assert prompt == "Just one message"


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


# ============================================================================
# TestViolationPendingResponse
# ============================================================================


class TestViolationPendingResponse:
    """Tests for ViolationPendingResponse dataclass."""

    def test_creation(self) -> None:
        """ViolationPendingResponse can be created."""
        vpr = ViolationPendingResponse(
            blocked_response="Hello world",
            violations=[{"anchor_id": "a1", "severity": "reject"}],
            choices=["1. Fix", "2. Revise", "3. Proceed"],
            prompt="Choose an action",
            run_id="run_001",
        )
        assert vpr.blocked_response == "Hello world"
        assert len(vpr.violations) == 1

    def test_to_dict(self) -> None:
        """ViolationPendingResponse serializes to dict."""
        vpr = ViolationPendingResponse(
            blocked_response="content",
            violations=[{"a": "b"}],
            choices=["1", "2"],
            prompt="prompt",
            run_id="run",
            pending_id="pend_xyz",
        )
        d = vpr.to_dict()
        assert d["blocked_response"] == "content"
        assert d["pending_id"] == "pend_xyz"


# ============================================================================
# TestCheckResponseBlocking
# ============================================================================


class TestCheckResponseBlocking:
    """Tests for check_response_blocking method."""

    def _setup_context_with_reject_anchor(self, tmp_path: Path) -> GovernorContext:
        """Create a context with a REJECT-severity anchor."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="fiction")

        # Create a continuity anchor with REJECT severity
        anchors_dir = ctx.governor_dir / "continuity"
        anchors_dir.mkdir(parents=True)
        anchors_file = anchors_dir / "anchors.json"
        anchors_file.write_text(json.dumps({
            "anchors": [{
                "id": "test_reject_anchor",
                "anchor_type": "prohibition",
                "description": "Cannot mention secret password",
                "forbidden_patterns": ["secret password"],
                "severity": "reject",
            }]
        }))
        return ctx

    def test_non_blocking_returns_check_result(self, tmp_path: Path) -> None:
        """Non-blocking violations return GovernorCheckResult."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="fiction")
        hooks = GovernorHooks(ctx)

        result = hooks.check_response_blocking("Hello world", "run_001")
        assert isinstance(result, GovernorCheckResult)
        assert result.passed is True

    def test_reject_severity_returns_pending(self, tmp_path: Path) -> None:
        """REJECT-severity violations return ViolationPendingResponse."""
        ctx = self._setup_context_with_reject_anchor(tmp_path)
        hooks = GovernorHooks(ctx)

        result = hooks.check_response_blocking(
            "The secret password is 12345", "run_002"
        )
        assert isinstance(result, ViolationPendingResponse)
        assert result.blocked_response == "The secret password is 12345"
        assert len(result.violations) >= 1
        assert result.run_id == "run_002"

    def test_pending_has_choices(self, tmp_path: Path) -> None:
        """ViolationPendingResponse includes mode-appropriate choices."""
        ctx = self._setup_context_with_reject_anchor(tmp_path)
        hooks = GovernorHooks(ctx)

        result = hooks.check_response_blocking(
            "The secret password is 12345", "run_003"
        )
        assert isinstance(result, ViolationPendingResponse)
        assert len(result.choices) == 3
        # Fiction mode should mention canon
        assert any("canon" in c.lower() for c in result.choices)

    def test_pending_prompt_is_formatted(self, tmp_path: Path) -> None:
        """ViolationPendingResponse has formatted user prompt."""
        ctx = self._setup_context_with_reject_anchor(tmp_path)
        hooks = GovernorHooks(ctx)

        result = hooks.check_response_blocking(
            "The secret password is 12345", "run_004"
        )
        assert isinstance(result, ViolationPendingResponse)
        assert "[Governor] Blocked" in result.prompt
        # Prompt includes resolution commands (fix/revise/proceed)
        assert "fix" in result.prompt.lower()

    def test_pending_creates_file(self, tmp_path: Path) -> None:
        """Blocking check creates pending violation file."""
        ctx = self._setup_context_with_reject_anchor(tmp_path)
        hooks = GovernorHooks(ctx)

        result = hooks.check_response_blocking(
            "The secret password is 12345", "run_005"
        )
        assert isinstance(result, ViolationPendingResponse)

        # Check pending file was created
        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(ctx.governor_dir)
        pending = resolver.get_pending()
        assert pending is not None
        assert pending.run_id == "run_005"

    def test_warn_severity_not_blocking(self, tmp_path: Path) -> None:
        """WARN-severity violations do not block."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="fiction")

        # Create anchor with WARN severity
        anchors_dir = ctx.governor_dir / "continuity"
        anchors_dir.mkdir(parents=True)
        anchors_file = anchors_dir / "anchors.json"
        anchors_file.write_text(json.dumps({
            "anchors": [{
                "id": "warn_anchor",
                "anchor_type": "prohibition",
                "description": "Warn about clichés",
                "forbidden_patterns": ["once upon a time"],
                "severity": "warn",
            }]
        }))

        hooks = GovernorHooks(ctx)
        result = hooks.check_response_blocking(
            "Once upon a time in a land far away", "run_006"
        )
        # Should return GovernorCheckResult, not ViolationPendingResponse
        assert isinstance(result, GovernorCheckResult)
        assert len(result.violations) >= 1  # Has violations but not blocking


# ============================================================================
# TestResearchMode
# ============================================================================


class TestResearchMode:
    """Tests for research mode integration in GovernorHooks."""

    def test_build_research_prompt(self, tmp_path: Path) -> None:
        """Research mode produces a system prompt."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        hooks = GovernorHooks(ctx)
        prompt = hooks._build_mode_prompt()
        assert prompt is not None
        assert "epistemic debt" in prompt.lower()
        assert "claim" in prompt.lower()

    def test_research_prompt_includes_ed(self, tmp_path: Path) -> None:
        """Research prompt includes ED when store has data."""
        from governor.research_store import ResearchStore

        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        store = ResearchStore(ctx.governor_dir)
        store.add_claim("Test claim")

        hooks = GovernorHooks(ctx)
        prompt = hooks._build_research_prompt()
        assert "ED Score:" in prompt

    def test_load_research_store(self, tmp_path: Path) -> None:
        """_load_research_store returns a ResearchStore."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        hooks = GovernorHooks(ctx)
        store = hooks._load_research_store()
        assert store is not None

    def test_research_store_to_anchors(self, tmp_path: Path) -> None:
        """Claims and assumptions become anchors."""
        from governor.research_store import ResearchStore

        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        store = ResearchStore(ctx.governor_dir)
        store.add_claim("Active claim")
        store.add_assumption("Active assumption")

        hooks = GovernorHooks(ctx)
        anchors = hooks._load_research_anchors()
        assert len(anchors) == 2
        assert any("Claim:" in a.description for a in anchors)
        assert any("Assumption:" in a.description for a in anchors)

    def test_research_mode_dispatch(self, tmp_path: Path) -> None:
        """mode='research' uses research prompt path."""
        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        hooks = GovernorHooks(ctx)
        prompt = hooks._build_mode_prompt()
        assert prompt is not None
        assert "research" in prompt.lower()

    def test_research_mode_anchors(self, tmp_path: Path) -> None:
        """mode='research' loads research anchors via _load_mode_anchors."""
        from governor.research_store import ResearchStore

        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        store = ResearchStore(ctx.governor_dir)
        store.add_claim("Anchor claim")

        hooks = GovernorHooks(ctx)
        all_anchors = hooks._load_mode_anchors()
        assert any("research-" in a.id for a in all_anchors)

    def test_retracted_claims_excluded_from_anchors(self, tmp_path: Path) -> None:
        """Retracted and superseded claims don't become anchors."""
        from governor.research_store import ClaimStatus, ResearchStore

        cm = GovernorContextManager(base_dir=tmp_path / "contexts")
        ctx = cm.create("test-ctx", mode="research")
        store = ResearchStore(ctx.governor_dir)
        c = store.add_claim("Retracted claim")
        store.update_claim_status(c.id, ClaimStatus.RETRACTED)

        hooks = GovernorHooks(ctx)
        anchors = hooks._load_research_anchors()
        assert len(anchors) == 0


# =============================================================================
# Auth error detection — ClaudeCodeAuthError + _is_auth_error
# =============================================================================


class TestClaudeCodeAuthError:
    """Tests for authentication error detection in ClaudeCodeBackend."""

    def test_is_auth_error_detects_not_logged_in(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("Error: not logged in")

    def test_is_auth_error_detects_401(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("HTTP 401: Unauthorized")

    def test_is_auth_error_detects_expired(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("Your session has expired, please re-authenticate")

    def test_is_auth_error_detects_login_required(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("Login required")

    def test_is_auth_error_detects_credential(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("Invalid credential provided")

    def test_is_auth_error_detects_please_login(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("Please log in at claude.ai")

    def test_is_auth_error_negative_case(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert not _is_auth_error("Model not found: claude-4-opus")

    def test_is_auth_error_negative_network(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert not _is_auth_error("Connection refused")

    def test_is_auth_error_case_insensitive(self) -> None:
        from governor.chat_bridge import _is_auth_error
        assert _is_auth_error("NOT LOGGED IN")

    def test_exception_message_includes_login_hint(self) -> None:
        from governor.chat_bridge import ClaudeCodeAuthError
        err = ClaudeCodeAuthError("token expired")
        assert "claude /login" in str(err)

    def test_exception_stores_stderr(self) -> None:
        from governor.chat_bridge import ClaudeCodeAuthError
        err = ClaudeCodeAuthError("some stderr output")
        assert err.stderr_text == "some stderr output"

    def test_exception_default_message(self) -> None:
        from governor.chat_bridge import ClaudeCodeAuthError
        err = ClaudeCodeAuthError("")
        assert "authentication required" in str(err)

    def test_codex_auth_error_message(self) -> None:
        from governor.chat_bridge import CodexAuthError
        err = CodexAuthError("unauthorized")
        assert "codex auth login" in str(err)

    def test_codex_auth_error_stores_stderr(self) -> None:
        from governor.chat_bridge import CodexAuthError
        err = CodexAuthError("some output")
        assert err.stderr_text == "some output"

    def test_codex_auth_error_default_message(self) -> None:
        from governor.chat_bridge import CodexAuthError
        err = CodexAuthError("")
        assert "authentication required" in str(err)

    def test_backend_auth_error_is_base(self) -> None:
        from governor.chat_bridge import BackendAuthError, ClaudeCodeAuthError, CodexAuthError
        assert issubclass(ClaudeCodeAuthError, BackendAuthError)
        assert issubclass(CodexAuthError, BackendAuthError)
        assert issubclass(BackendAuthError, RuntimeError)

    def test_both_caught_by_base(self) -> None:
        from governor.chat_bridge import BackendAuthError, ClaudeCodeAuthError, CodexAuthError
        for exc_class in (ClaudeCodeAuthError, CodexAuthError):
            try:
                raise exc_class("test")
            except BackendAuthError:
                pass  # expected
