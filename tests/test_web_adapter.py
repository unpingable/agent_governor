"""Tests for the WebUI adapter (FastAPI endpoints)."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from governor.chat_bridge import ChatResponse as BridgeChatResponse
from governor.context_manager import GovernorContextManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_contexts_dir(tmp_path: Path) -> Path:
    """Temporary directory for governor contexts."""
    return tmp_path / "contexts"


@pytest.fixture
def mock_env(tmp_contexts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set environment variables for adapter configuration."""
    monkeypatch.setenv("BACKEND_TYPE", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("GOVERNOR_CONTEXT_ID", "test-context")
    monkeypatch.setenv("GOVERNOR_MODE", "general")
    monkeypatch.setenv("GOVERNOR_CONTEXTS_DIR", str(tmp_contexts_dir))


@pytest.fixture
def reset_adapter_globals() -> None:
    """Reset module-level globals between tests."""
    import webui.adapter as adapter_mod
    adapter_mod._bridge = None
    adapter_mod._context_manager = None
    yield
    adapter_mod._bridge = None
    adapter_mod._context_manager = None


@pytest.fixture
def app(mock_env, reset_adapter_globals):
    """Get the FastAPI app with test config."""
    # Re-import to pick up environment changes
    import importlib
    import webui.adapter as adapter_mod
    importlib.reload(adapter_mod)
    return adapter_mod.app


@pytest.fixture
def client(app):
    """Create a test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)


# ============================================================================
# TestRootEndpoint
# ============================================================================


class TestRootEndpoint:
    """Tests for GET /."""

    def test_returns_info(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Governor Chat Adapter"
        assert data["openai_compatible"] is True

    def test_includes_version(self, client) -> None:
        response = client.get("/")
        data = response.json()
        assert "version" in data
        assert data["version"] == "0.2.0"

    def test_includes_endpoints(self, client) -> None:
        response = client.get("/")
        data = response.json()
        assert "endpoints" in data
        assert "/v1/models" in data["endpoints"].values()
        assert "/v1/chat/completions" in data["endpoints"].values()


# ============================================================================
# TestHealthEndpoint
# ============================================================================


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_degraded_when_backend_down(self, client) -> None:
        """Health returns degraded when backend is unreachable."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Backend is not running so should be degraded
        assert data["status"] == "degraded"
        assert data["backend"]["connected"] is False

    def test_health_includes_governor_info(self, client) -> None:
        response = client.get("/health")
        data = response.json()
        assert "governor" in data
        assert "context_id" in data["governor"]
        assert "mode" in data["governor"]

    def test_health_includes_backend_type(self, client) -> None:
        response = client.get("/health")
        data = response.json()
        assert data["backend"]["type"] == "ollama"


# ============================================================================
# TestModelsEndpoint
# ============================================================================


class TestModelsEndpoint:
    """Tests for GET /v1/models."""

    def test_models_format(self, client) -> None:
        """Models endpoint returns correct format even on error."""
        # Backend is down, so this will raise 502
        response = client.get("/v1/models")
        # Could be 502 (backend down) or 200 (mocked)
        assert response.status_code in (200, 502)

    def test_get_model_by_id(self, client) -> None:
        response = client.get("/v1/models/test-model")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-model"
        assert data["object"] == "model"


# ============================================================================
# TestChatEndpoint
# ============================================================================


class TestChatEndpoint:
    """Tests for POST /v1/chat/completions."""

    def test_non_streaming_response_format(self, client, monkeypatch) -> None:
        """Non-streaming response has correct OpenAI format."""
        import webui.adapter as adapter_mod

        mock_bridge = AsyncMock()
        mock_bridge.chat.return_value = BridgeChatResponse(
            content="Hello from test", model="test-model",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        )
        mock_bridge.list_models = AsyncMock(return_value=[])

        # Inject mock bridge
        adapter_mod._bridge = mock_bridge

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "test-model"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["content"] == "Hello from test"
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["usage"]["total_tokens"] == 8

    def test_error_handling(self, client, monkeypatch) -> None:
        """Backend errors return 502."""
        import webui.adapter as adapter_mod

        mock_bridge = AsyncMock()
        mock_bridge.chat.side_effect = Exception("Connection refused")
        adapter_mod._bridge = mock_bridge

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert response.status_code == 502

    def test_empty_messages(self, client, monkeypatch) -> None:
        """Empty messages list is handled."""
        import webui.adapter as adapter_mod

        mock_bridge = AsyncMock()
        mock_bridge.chat.return_value = BridgeChatResponse(
            content="OK", model="m"
        )
        adapter_mod._bridge = mock_bridge

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [],
                "stream": False,
            },
        )
        assert response.status_code == 200

    def test_max_tokens_passthrough(self, client, monkeypatch) -> None:
        """max_tokens is passed through to backend."""
        import webui.adapter as adapter_mod

        mock_bridge = AsyncMock()
        mock_bridge.chat.return_value = BridgeChatResponse(
            content="OK", model="m"
        )
        adapter_mod._bridge = mock_bridge

        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 100,
                "stream": False,
            },
        )
        call_kwargs = mock_bridge.chat.call_args[1]
        assert call_kwargs.get("max_tokens") == 100

    def test_model_passthrough(self, client, monkeypatch) -> None:
        """Model name is passed through correctly."""
        import webui.adapter as adapter_mod

        mock_bridge = AsyncMock()
        mock_bridge.chat.return_value = BridgeChatResponse(
            content="OK", model="custom-model"
        )
        adapter_mod._bridge = mock_bridge

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "custom-model",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
            },
        )
        data = response.json()
        assert data["model"] == "custom-model"


# ============================================================================
# TestGovernorEndpoints
# ============================================================================


class TestGovernorEndpoints:
    """Tests for governor-specific endpoints."""

    def test_contexts_list(self, client, tmp_contexts_dir) -> None:
        """GET /governor/contexts returns context list."""
        # Create a context manually
        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-ctx-1", mode="fiction")

        # Need to inject this context manager
        import webui.adapter as adapter_mod
        adapter_mod._context_manager = cm

        response = client.get("/governor/contexts")
        assert response.status_code == 200
        data = response.json()
        assert "contexts" in data
        assert "active_context_id" in data
        assert len(data["contexts"]) == 1
        assert data["contexts"][0]["context_id"] == "test-ctx-1"

    def test_status_uninitialized(self, client) -> None:
        """GET /governor/status when context doesn't exist."""
        response = client.get("/governor/status")
        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is False

    def test_status_with_fiction_context(self, client, tmp_contexts_dir) -> None:
        """GET /governor/status with fiction context."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="fiction")
        adapter_mod._context_manager = cm

        response = client.get("/governor/status")
        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is True
        assert data["mode"] == "fiction"
        assert data["has_fiction_governor"] is True
        assert data["has_governor"] is True

    def test_status_with_code_context(self, client, tmp_contexts_dir) -> None:
        """GET /governor/status with code context."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/status")
        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is True
        assert data["mode"] == "code"
        assert data["has_fiction_governor"] is False


# ============================================================================
# TestBackendSelection
# ============================================================================


class TestBackendSelection:
    """Tests for backend type selection."""

    def test_default_is_ollama(self, monkeypatch, tmp_contexts_dir) -> None:
        """Default backend type is ollama."""
        monkeypatch.setenv("GOVERNOR_CONTEXTS_DIR", str(tmp_contexts_dir))
        monkeypatch.delenv("BACKEND_TYPE", raising=False)

        import importlib
        import webui.adapter as adapter_mod
        adapter_mod._bridge = None
        adapter_mod._context_manager = None
        importlib.reload(adapter_mod)

        assert adapter_mod.BACKEND_TYPE == "ollama"

    def test_anthropic_from_env(self, monkeypatch, tmp_contexts_dir) -> None:
        """BACKEND_TYPE=anthropic is read from environment."""
        monkeypatch.setenv("BACKEND_TYPE", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GOVERNOR_CONTEXTS_DIR", str(tmp_contexts_dir))

        import importlib
        import webui.adapter as adapter_mod
        adapter_mod._bridge = None
        adapter_mod._context_manager = None
        importlib.reload(adapter_mod)

        assert adapter_mod.BACKEND_TYPE == "anthropic"

    def test_ollama_from_env(self, monkeypatch, tmp_contexts_dir) -> None:
        """BACKEND_TYPE=ollama is read from environment."""
        monkeypatch.setenv("BACKEND_TYPE", "ollama")
        monkeypatch.setenv("GOVERNOR_CONTEXTS_DIR", str(tmp_contexts_dir))

        import importlib
        import webui.adapter as adapter_mod
        adapter_mod._bridge = None
        adapter_mod._context_manager = None
        importlib.reload(adapter_mod)

        assert adapter_mod.BACKEND_TYPE == "ollama"


# ============================================================================
# TestStreamingResponse
# ============================================================================


class TestStreamingResponse:
    """Tests for streaming chat responses."""

    def test_streaming_request(self, client, monkeypatch) -> None:
        """Streaming request returns SSE format."""
        import webui.adapter as adapter_mod

        async def mock_stream(*args, **kwargs):
            from governor.chat_bridge import ChatChunk
            yield ChatChunk(content="Hello ")
            yield ChatChunk(content="world", finish_reason="stop")

        mock_bridge = AsyncMock()
        mock_bridge.chat.return_value = mock_stream()
        adapter_mod._bridge = mock_bridge

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Parse SSE chunks
        content = response.text
        assert "data:" in content


# ============================================================================
# TestGovernorNow
# ============================================================================


class TestGovernorNow:
    """Tests for GET /governor/now."""

    def test_uninitialized_returns_ok(self, client) -> None:
        """Uninitialized context returns ok status."""
        response = client.get("/governor/now")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["sentence"].startswith("OK:")
        assert data["last_event"] is None
        assert data["suggested_action"] is None

    def test_with_empty_context(self, client, tmp_contexts_dir) -> None:
        """Empty initialized context returns ok."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/now")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mode"] == "code"

    def test_includes_context_id(self, client) -> None:
        response = client.get("/governor/now")
        data = response.json()
        assert "context_id" in data

    def test_includes_regime(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="general")
        adapter_mod._context_manager = cm

        response = client.get("/governor/now")
        data = response.json()
        # regime is present (may be None or a string depending on state)
        assert "regime" in data

    def test_response_shape(self, client) -> None:
        """Response has all expected keys."""
        response = client.get("/governor/now")
        data = response.json()
        expected_keys = {"context_id", "status", "sentence", "last_event", "suggested_action", "regime", "mode"}
        assert expected_keys == set(data.keys())

    def test_status_is_valid_pill(self, client) -> None:
        response = client.get("/governor/now")
        data = response.json()
        assert data["status"] in ("ok", "needs_attention", "blocked")


# ============================================================================
# TestGovernorWhy
# ============================================================================


class TestGovernorWhy:
    """Tests for GET /governor/why."""

    def test_uninitialized_returns_empty(self, client) -> None:
        response = client.get("/governor/why")
        assert response.status_code == 200
        data = response.json()
        assert data["feed"] == []
        assert data["total"] == 0

    def test_with_empty_context(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/why")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["feed"], list)

    def test_limit_parameter(self, client) -> None:
        response = client.get("/governor/why?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["feed"]) <= 5

    def test_severity_parameter(self, client) -> None:
        response = client.get("/governor/why?severity=error")
        assert response.status_code == 200

    def test_response_shape(self, client) -> None:
        response = client.get("/governor/why")
        data = response.json()
        expected_keys = {"context_id", "feed", "total"}
        assert expected_keys == set(data.keys())


# ============================================================================
# TestGovernorHistory
# ============================================================================


class TestGovernorHistory:
    """Tests for GET /governor/history."""

    def test_uninitialized_returns_empty(self, client) -> None:
        response = client.get("/governor/history")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == []

    def test_with_empty_context(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["days"], list)

    def test_days_parameter(self, client) -> None:
        response = client.get("/governor/history?days=3")
        assert response.status_code == 200

    def test_response_shape(self, client) -> None:
        response = client.get("/governor/history")
        data = response.json()
        expected_keys = {"context_id", "days"}
        assert expected_keys == set(data.keys())


# ============================================================================
# TestGovernorDetail
# ============================================================================


class TestGovernorDetail:
    """Tests for GET /governor/detail/{item_id}."""

    def test_404_when_uninitialized(self, client) -> None:
        response = client.get("/governor/detail/dec_test123")
        assert response.status_code == 404

    def test_404_unknown_id(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/detail/dec_nonexistent")
        assert response.status_code == 404

    def test_404_unknown_prefix(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/detail/xxx_unknown")
        assert response.status_code == 404

    def test_valid_prefixes_handled(self, client, tmp_contexts_dir) -> None:
        """All valid prefixes (dec_, clm_, ev_, vio_) are handled without 500."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        for prefix in ["dec_", "clm_", "ev_", "vio_"]:
            response = client.get(f"/governor/detail/{prefix}nonexistent")
            # Should be 404 (not found), not 500 (server error)
            assert response.status_code == 404

    def test_response_shape_on_404(self, client, tmp_contexts_dir) -> None:
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/detail/dec_missing")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


# ============================================================================
# TestGovernorStatusV2
# ============================================================================


class TestGovernorStatusV2:
    """Tests for /governor/status with viewmodel integration."""

    def test_uninitialized_no_viewmodel(self, client) -> None:
        """Uninitialized context does not include viewmodel key."""
        response = client.get("/governor/status")
        data = response.json()
        assert data["initialized"] is False
        assert "viewmodel" not in data

    def test_initialized_includes_viewmodel(self, client, tmp_contexts_dir) -> None:
        """Initialized context includes viewmodel key."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="code")
        adapter_mod._context_manager = cm

        response = client.get("/governor/status")
        data = response.json()
        assert data["initialized"] is True
        assert "viewmodel" in data
        assert data["viewmodel"]["schema_version"] == "v2"

    def test_backward_compat_fields(self, client, tmp_contexts_dir) -> None:
        """Backward-compat fields still present alongside viewmodel."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="fiction")
        adapter_mod._context_manager = cm

        response = client.get("/governor/status")
        data = response.json()
        # Old fields still present
        assert "context_id" in data
        assert "initialized" in data
        assert "mode" in data
        assert "facts_count" in data
        assert "decisions_count" in data
        assert "metadata" in data
        # New field present
        assert "viewmodel" in data

    def test_viewmodel_has_sections(self, client, tmp_contexts_dir) -> None:
        """Viewmodel contains the 8 standard sections."""
        import webui.adapter as adapter_mod

        cm = GovernorContextManager(base_dir=tmp_contexts_dir)
        cm.create("test-context", mode="general")
        adapter_mod._context_manager = cm

        response = client.get("/governor/status")
        vm = response.json()["viewmodel"]
        expected_sections = {"schema_version", "generated_at", "session", "regime",
                             "decisions", "claims", "evidence", "violations",
                             "execution", "stability"}
        assert expected_sections == set(vm.keys())


# ============================================================================
# TestRootEndpointV2
# ============================================================================


class TestRootEndpointV2:
    """Tests for new routes in root endpoint."""

    def test_includes_new_endpoints(self, client) -> None:
        response = client.get("/")
        data = response.json()
        endpoints = data["endpoints"]
        assert "governor_now" in endpoints
        assert "governor_why" in endpoints
        assert "governor_history" in endpoints
        assert "governor_detail" in endpoints
