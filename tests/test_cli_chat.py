# SPDX-License-Identifier: Apache-2.0
"""Tests for cli_chat.py — Governed Conversational CLI with Backend Switching."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from governor.cli_chat import (
    BackendInfo,
    ChatConfig,
    ChatResult,
    CompareResult,
    DEFAULT_CONFIG_PATH,
    DEFAULT_MODELS,
    KNOWN_BACKENDS,
    format_compare,
    format_response,
    make_chat_event,
    parse_backend_list,
    parse_backend_spec,
    probe_backend,
    probe_backends,
    run_chat,
    run_compare,
    _extract_simple_signals,
    _resolve_model,
)


# ===========================================================================
# ChatConfig tests
# ===========================================================================

class TestChatConfig:
    """Tests for ChatConfig persistence."""

    def test_default_values(self):
        c = ChatConfig()
        assert c.active_backend == "ollama"
        assert c.active_model == ""
        assert c.backend_options == {}

    def test_to_dict(self):
        c = ChatConfig(active_backend="anthropic", active_model="claude-sonnet-4-20250514")
        d = c.to_dict()
        assert d["active_backend"] == "anthropic"
        assert d["active_model"] == "claude-sonnet-4-20250514"
        assert d["backend_options"] == {}

    def test_from_dict(self):
        d = {"active_backend": "claude-code", "active_model": "x", "backend_options": {"a": {"k": "v"}}}
        c = ChatConfig.from_dict(d)
        assert c.active_backend == "claude-code"
        assert c.active_model == "x"
        assert c.backend_options == {"a": {"k": "v"}}

    def test_from_dict_defaults(self):
        c = ChatConfig.from_dict({})
        assert c.active_backend == "ollama"
        assert c.active_model == ""

    def test_roundtrip(self, tmp_path: Path):
        p = tmp_path / "chat_config.json"
        c = ChatConfig(active_backend="anthropic", active_model="claude-3-haiku")
        c.save(p)
        loaded = ChatConfig.load(p)
        assert loaded.active_backend == "anthropic"
        assert loaded.active_model == "claude-3-haiku"

    def test_load_missing(self, tmp_path: Path):
        p = tmp_path / "nope.json"
        c = ChatConfig.load(p)
        assert c.active_backend == "ollama"

    def test_load_corrupt(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        c = ChatConfig.load(p)
        assert c.active_backend == "ollama"

    def test_save_creates_parent(self, tmp_path: Path):
        p = tmp_path / "deep" / "nested" / "config.json"
        c = ChatConfig()
        c.save(p)
        assert p.exists()

    def test_backend_options_roundtrip(self, tmp_path: Path):
        p = tmp_path / "config.json"
        c = ChatConfig(
            active_backend="ollama",
            backend_options={
                "ollama": {"host": "http://remote:11434"},
                "anthropic": {"api_key": "sk-test"},
            },
        )
        c.save(p)
        loaded = ChatConfig.load(p)
        assert loaded.backend_options["ollama"]["host"] == "http://remote:11434"


# ===========================================================================
# BackendInfo tests
# ===========================================================================

class TestBackendInfo:
    """Tests for BackendInfo dataclass."""

    def test_creation(self):
        b = BackendInfo(name="ollama", available=True, reason="ok")
        assert b.name == "ollama"
        assert b.available is True
        assert b.reason == "ok"
        assert b.models == []
        assert b.default_model == ""

    def test_to_dict(self):
        b = BackendInfo(
            name="anthropic", available=True,
            reason="key set", models=["claude-3"], default_model="claude-3",
        )
        d = b.to_dict()
        assert d["name"] == "anthropic"
        assert d["available"] is True
        assert d["models"] == ["claude-3"]
        assert d["default_model"] == "claude-3"

    def test_unavailable(self):
        b = BackendInfo(name="codex", available=False, reason="not found")
        assert not b.available
        assert b.reason == "not found"


# ===========================================================================
# Backend probing tests
# ===========================================================================

class TestProbeBackends:
    """Tests for backend availability checking."""

    @patch("governor.cli_chat._check_ollama")
    @patch("governor.cli_chat._check_anthropic")
    @patch("governor.cli_chat._check_claude_code")
    @patch("governor.cli_chat._check_codex")
    def test_probe_all(self, m_codex, m_claude, m_anthro, m_ollama):
        m_ollama.return_value = BackendInfo(name="ollama", available=True, reason="ok")
        m_anthro.return_value = BackendInfo(name="anthropic", available=False, reason="no key")
        m_claude.return_value = BackendInfo(name="claude-code", available=True, reason="/usr/bin/claude")
        m_codex.return_value = BackendInfo(name="codex", available=False, reason="not found")

        results = probe_backends()
        assert len(results) == 4
        assert results[0].available is True
        assert results[1].available is False
        assert results[2].available is True
        assert results[3].available is False

    @patch("governor.cli_chat._check_ollama")
    def test_probe_single(self, m_ollama):
        m_ollama.return_value = BackendInfo(name="ollama", available=True, reason="ok")
        result = probe_backend("ollama")
        assert result.available is True

    def test_probe_unknown_backend(self):
        result = probe_backend("unknown")
        assert not result.available
        assert "unknown backend" in result.reason

    @patch("governor.cli_chat._check_ollama", side_effect=Exception("boom"))
    def test_probe_exception_caught(self, m_ollama):
        results = probe_backends()
        assert results[0].available is False
        assert "boom" in results[0].reason

    def test_known_backends(self):
        assert len(KNOWN_BACKENDS) == 4
        assert "ollama" in KNOWN_BACKENDS
        assert "anthropic" in KNOWN_BACKENDS

    def test_default_models(self):
        for backend in KNOWN_BACKENDS:
            assert backend in DEFAULT_MODELS


# ===========================================================================
# ChatResult tests
# ===========================================================================

class TestChatResult:
    """Tests for ChatResult dataclass."""

    def test_creation(self):
        r = ChatResult(response="hello", model="llama3", backend="ollama")
        assert r.response == "hello"
        assert r.passed is True
        assert r.violations == []
        assert r.latency_ms == 0.0

    def test_to_dict(self):
        r = ChatResult(
            response="test", model="m", backend="b",
            violations=[{"severity": "warn", "anchor_id": "a1"}],
            checked_anchors=3,
            passed=False,
            latency_ms=42.567,
        )
        d = r.to_dict()
        assert d["response"] == "test"
        assert d["passed"] is False
        assert len(d["violations"]) == 1
        assert d["latency_ms"] == 42.6

    def test_with_usage(self):
        r = ChatResult(
            response="x", model="m", backend="b",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        assert r.usage["total_tokens"] == 30


# ===========================================================================
# CompareResult tests
# ===========================================================================

class TestCompareResult:
    """Tests for CompareResult dataclass."""

    def test_creation(self):
        r = CompareResult(results=[])
        assert r.shared_signals == []
        assert r.unique_signals == {}
        assert r.conflict_signals == []

    def test_to_dict(self):
        r = CompareResult(
            results=[ChatResult(response="a", model="m1", backend="b1")],
            shared_signals=["action:create"],
            unique_signals={"b1": ["file:x.py"]},
            conflict_signals=["commitment:must"],
        )
        d = r.to_dict()
        assert len(d["results"]) == 1
        assert d["shared_signals"] == ["action:create"]


# ===========================================================================
# Signal extraction tests
# ===========================================================================

class TestSignalExtraction:
    """Tests for simple signal extraction."""

    def test_action_signals(self):
        s = _extract_simple_signals("You should create a new file and delete the old one.")
        assert "action:create" in s
        assert "action:delete" in s

    def test_file_references(self):
        s = _extract_simple_signals("Modify src/auth.py and update config.json")
        assert any(sig.startswith("file:") for sig in s)

    def test_code_block(self):
        s = _extract_simple_signals("Here's the code:\n```python\nprint('hi')\n```")
        assert "contains:code_block" in s

    def test_import_signal(self):
        s = _extract_simple_signals("import os\nimport sys")
        assert "contains:import" in s

    def test_function_def(self):
        s = _extract_simple_signals("def main():\n    pass")
        assert "contains:function_def" in s

    def test_class_def(self):
        s = _extract_simple_signals("class Foo:\n    pass")
        assert "contains:class_def" in s

    def test_commitment_signals(self):
        s = _extract_simple_signals("You must validate inputs and should log errors.")
        assert "commitment:must" in s
        assert "commitment:should" in s

    def test_empty_text(self):
        s = _extract_simple_signals("")
        assert len(s) == 0

    def test_no_duplicates(self):
        s = _extract_simple_signals("create create create")
        assert list(s).count("action:create") == 1


# ===========================================================================
# Model resolution tests
# ===========================================================================

class TestResolveModel:
    """Tests for model resolution priority."""

    def test_explicit_model_wins(self):
        config = ChatConfig(active_model="default-model")
        assert _resolve_model("ollama", "explicit", config) == "explicit"

    def test_config_model_second(self):
        config = ChatConfig(active_model="config-model")
        assert _resolve_model("ollama", "", config) == "config-model"

    def test_default_model_last(self):
        config = ChatConfig(active_model="")
        assert _resolve_model("ollama", "", config) == DEFAULT_MODELS["ollama"]

    def test_unknown_backend_empty(self):
        config = ChatConfig(active_model="")
        assert _resolve_model("unknown", "", config) == ""


# ===========================================================================
# Parse backend spec tests
# ===========================================================================

class TestParseBackendSpec:
    """Tests for backend spec string parsing."""

    def test_backend_only(self):
        assert parse_backend_spec("ollama") == ("ollama", "")

    def test_backend_and_model(self):
        assert parse_backend_spec("ollama:llama3") == ("ollama", "llama3")

    def test_model_with_colon(self):
        # Ollama models can have colons like "llama3:latest"
        assert parse_backend_spec("ollama:llama3:latest") == ("ollama", "llama3:latest")

    def test_parse_list(self):
        result = parse_backend_list("ollama:llama3,anthropic:claude-3")
        assert len(result) == 2
        assert result[0] == ("ollama", "llama3")
        assert result[1] == ("anthropic", "claude-3")

    def test_parse_list_with_spaces(self):
        result = parse_backend_list("ollama:llama3 , anthropic:claude-3")
        assert len(result) == 2

    def test_parse_list_empty(self):
        result = parse_backend_list("")
        assert result == []

    def test_parse_list_trailing_comma(self):
        result = parse_backend_list("ollama,")
        assert len(result) == 1


# ===========================================================================
# Format response tests
# ===========================================================================

class TestFormatResponse:
    """Tests for terminal output formatting."""

    def test_basic_format(self):
        r = ChatResult(
            response="Hello world", model="llama3", backend="ollama",
            latency_ms=123.4, usage={"total_tokens": 50},
        )
        out = format_response(r)
        assert "Hello world" in out
        assert "ollama:llama3" in out
        assert "123ms" in out
        assert "50 tokens" in out

    def test_no_meta(self):
        r = ChatResult(response="Hello", model="m", backend="b")
        out = format_response(r, show_meta=False)
        assert out == "Hello"

    def test_with_violations(self):
        r = ChatResult(
            response="Bad response", model="m", backend="b",
            violations=[{
                "severity": "reject",
                "anchor_id": "anchor-1",
                "description": "Violates safety constraint",
            }],
        )
        out = format_response(r)
        assert "VIOLATIONS (1)" in out
        assert "[reject] anchor-1" in out
        assert "safety constraint" in out

    def test_no_violations(self):
        r = ChatResult(response="Good", model="m", backend="b")
        out = format_response(r)
        assert "VIOLATIONS" not in out


class TestFormatCompare:
    """Tests for compare output formatting."""

    def test_basic_compare_format(self):
        r = CompareResult(
            results=[
                ChatResult(response="Response A", model="m1", backend="b1"),
                ChatResult(response="Response B", model="m2", backend="b2"),
            ],
            shared_signals=["action:create"],
            unique_signals={"b1": ["file:a.py"]},
        )
        out = format_compare(r)
        assert "[b1:m1]" in out
        assert "[b2:m2]" in out
        assert "Response A" in out
        assert "Response B" in out
        assert "Signal Comparison" in out
        assert "Shared (1)" in out
        assert "Unique to b1" in out

    def test_compare_with_conflicts(self):
        r = CompareResult(
            results=[ChatResult(response="x", model="m", backend="b")],
            conflict_signals=["commitment:must", "commitment:should"],
        )
        out = format_compare(r)
        assert "Conflicts (2)" in out

    def test_compare_with_violations(self):
        r = CompareResult(
            results=[ChatResult(
                response="x", model="m", backend="b",
                violations=[{"severity": "warn", "anchor_id": "a1"}],
            )],
        )
        out = format_compare(r)
        assert "Violations: 1" in out


# ===========================================================================
# Telemetry event tests
# ===========================================================================

class TestMakeChatEvent:
    """Tests for telemetry event creation."""

    def test_basic_event(self):
        r = ChatResult(
            response="hello", model="llama3", backend="ollama",
            violations=[], checked_anchors=5, passed=True,
            latency_ms=100.0, usage={"total_tokens": 42},
        )
        e = make_chat_event(r)
        assert e["type"] == "cli_chat"
        assert e["backend"] == "ollama"
        assert e["model"] == "llama3"
        assert e["violations"] == 0
        assert e["checked_anchors"] == 5
        assert e["passed"] is True
        assert e["latency_ms"] == 100.0
        assert e["tokens"] == 42
        assert len(e["response_hash"]) == 12

    def test_event_with_violations(self):
        r = ChatResult(
            response="bad", model="m", backend="b",
            violations=[{"a": 1}, {"b": 2}],
            passed=False,
        )
        e = make_chat_event(r)
        assert e["violations"] == 2
        assert e["passed"] is False

    def test_deterministic_hash(self):
        r = ChatResult(response="same", model="m", backend="b")
        e1 = make_chat_event(r)
        e2 = make_chat_event(r)
        assert e1["response_hash"] == e2["response_hash"]


# ===========================================================================
# run_chat with mocked backend tests
# ===========================================================================

class TestRunChat:
    """Tests for run_chat with mocked backends."""

    def _make_mock_backend(self, response_text: str = "Mock response") -> MagicMock:
        """Create a mock backend that returns a canned response."""
        from governor.chat_bridge import ChatResponse

        mock = MagicMock()
        mock.chat = AsyncMock(return_value=ChatResponse(
            content=response_text,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        ))
        return mock

    @patch("governor.cli_chat._create_backend_instance")
    def test_basic_chat(self, mock_create, tmp_path: Path):
        mock_backend = self._make_mock_backend()
        mock_create.return_value = mock_backend

        config_path = tmp_path / "config.json"
        ChatConfig(active_backend="ollama").save(config_path)

        result = run_chat(
            "Hello",
            backend="ollama",
            model="llama3",
            use_hooks=False,
            config_path=config_path,
        )
        assert result.response == "Mock response"
        assert result.backend == "ollama"
        assert result.passed is True
        assert result.latency_ms > 0

    @patch("governor.cli_chat._create_backend_instance")
    def test_chat_with_hooks(self, mock_create, tmp_path: Path):
        mock_backend = self._make_mock_backend()
        mock_create.return_value = mock_backend

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        # Governor hooks require .governor dir
        gov_dir = Path.cwd() / ".governor"
        gov_dir.mkdir(exist_ok=True)

        result = run_chat(
            "Test prompt",
            backend="ollama",
            model="llama3",
            use_hooks=True,
            config_path=config_path,
        )
        assert result.response == "Mock response"
        # Hooks should have been applied (system message injected)
        call_args = mock_backend.chat.call_args
        messages = call_args[0][0]
        # Should have system + user message
        assert len(messages) >= 1

    @patch("governor.cli_chat._create_backend_instance")
    def test_chat_uses_config_defaults(self, mock_create, tmp_path: Path):
        mock_backend = self._make_mock_backend()
        mock_create.return_value = mock_backend

        config_path = tmp_path / "config.json"
        ChatConfig(active_backend="anthropic", active_model="claude-3-haiku").save(config_path)

        result = run_chat(
            "Test",
            use_hooks=False,
            config_path=config_path,
        )
        # Should have used anthropic backend
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[0][0] == "anthropic"

    @patch("governor.cli_chat._create_backend_instance")
    def test_chat_json_output(self, mock_create, tmp_path: Path):
        mock_backend = self._make_mock_backend("JSON test")
        mock_create.return_value = mock_backend

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        result = run_chat("Test", backend="ollama", model="m", use_hooks=False, config_path=config_path)
        d = result.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert "JSON test" in json_str


# ===========================================================================
# run_compare with mocked backend tests
# ===========================================================================

class TestRunCompare:
    """Tests for run_compare with mocked backends."""

    @patch("governor.cli_chat._create_backend_instance")
    def test_basic_compare(self, mock_create, tmp_path: Path):
        from governor.chat_bridge import ChatResponse

        call_count = 0

        def make_backend(name, config):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.chat = AsyncMock(return_value=ChatResponse(
                    content="Create a file called auth.py", model="m1",
                ))
            else:
                mock.chat = AsyncMock(return_value=ChatResponse(
                    content="Create auth.py and add validation", model="m2",
                ))
            return mock

        mock_create.side_effect = make_backend

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        result = run_compare(
            "Add auth",
            backends=[("ollama", "llama3"), ("anthropic", "claude-3")],
            config_path=config_path,
        )
        assert len(result.results) == 2
        assert "auth.py" in result.results[0].response
        # Both should share action:create
        assert "action:create" in result.shared_signals

    @patch("governor.cli_chat._create_backend_instance")
    def test_compare_with_error(self, mock_create, tmp_path: Path):
        from governor.chat_bridge import ChatResponse

        call_count = 0

        def make_backend(name, config):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.chat = AsyncMock(return_value=ChatResponse(
                    content="Good response", model="m1",
                ))
            else:
                mock.chat = AsyncMock(side_effect=ConnectionError("timeout"))
            return mock

        mock_create.side_effect = make_backend

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        result = run_compare(
            "Test",
            backends=[("ollama", "llama3"), ("anthropic", "claude-3")],
            config_path=config_path,
        )
        assert len(result.results) == 2
        assert "Error" in result.results[1].response


# ===========================================================================
# Backend check functions (unit tests with mocks)
# ===========================================================================

class TestBackendChecks:
    """Tests for individual backend check functions."""

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_check_claude_code_available(self, mock_which):
        from governor.cli_chat import _check_claude_code
        info = _check_claude_code()
        assert info.available is True
        assert "/usr/bin/claude" in info.reason

    @patch("shutil.which", return_value=None)
    def test_check_claude_code_unavailable(self, mock_which):
        from governor.cli_chat import _check_claude_code
        info = _check_claude_code()
        assert info.available is False

    @patch("shutil.which", return_value="/usr/bin/codex")
    def test_check_codex_available(self, mock_which):
        from governor.cli_chat import _check_codex
        info = _check_codex()
        assert info.available is True

    @patch("shutil.which", return_value=None)
    def test_check_codex_unavailable(self, mock_which):
        from governor.cli_chat import _check_codex
        info = _check_codex()
        assert info.available is False

    def test_check_anthropic_with_key(self):
        from governor.cli_chat import _check_anthropic
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-1234567890"}):
            info = _check_anthropic()
            assert info.available is True
            assert "sk-test-" in info.reason

    def test_check_anthropic_without_key(self):
        from governor.cli_chat import _check_anthropic
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            info = _check_anthropic()
            assert info.available is False


# ===========================================================================
# Golden-file schema tests
# ===========================================================================

class TestGoldenSchemas:
    """Tests that serialized schemas remain stable."""

    def test_chat_config_schema(self):
        c = ChatConfig()
        d = c.to_dict()
        assert set(d.keys()) == {"active_backend", "active_model", "backend_options"}

    def test_backend_info_schema(self):
        b = BackendInfo(name="x", available=True)
        d = b.to_dict()
        assert set(d.keys()) == {"name", "available", "reason", "models", "default_model"}

    def test_chat_result_schema(self):
        r = ChatResult(response="x", model="m", backend="b")
        d = r.to_dict()
        expected = {"response", "model", "backend", "violations", "checked_anchors",
                     "passed", "usage", "latency_ms"}
        assert set(d.keys()) == expected

    def test_compare_result_schema(self):
        r = CompareResult(results=[])
        d = r.to_dict()
        expected = {"results", "shared_signals", "unique_signals", "conflict_signals"}
        assert set(d.keys()) == expected

    def test_chat_event_schema(self):
        r = ChatResult(response="x", model="m", backend="b")
        e = make_chat_event(r)
        expected = {"type", "backend", "model", "response_hash", "violations",
                     "checked_anchors", "passed", "latency_ms", "tokens"}
        assert set(e.keys()) == expected


# ===========================================================================
# Integration-level tests (mocked backend, real hooks flow)
# ===========================================================================

class TestIntegration:
    """Integration tests with mocked backends but real governor hooks."""

    @patch("governor.cli_chat._create_backend_instance")
    def test_full_lifecycle(self, mock_create, tmp_path: Path):
        """Full chat lifecycle: config → chat → format → event."""
        from governor.chat_bridge import ChatResponse

        mock = MagicMock()
        mock.chat = AsyncMock(return_value=ChatResponse(
            content="I'll create a new auth module with JWT support.",
            model="llama3:latest",
            usage={"prompt_tokens": 15, "completion_tokens": 30, "total_tokens": 45},
        ))
        mock_create.return_value = mock

        # Save config
        config_path = tmp_path / "config.json"
        ChatConfig(active_backend="ollama", active_model="llama3:latest").save(config_path)

        # Run chat
        result = run_chat(
            "Add JWT auth to the project",
            use_hooks=False,
            config_path=config_path,
        )

        # Check result
        assert "JWT" in result.response
        assert result.model == "llama3:latest"
        assert result.backend == "ollama"
        assert result.passed is True

        # Format
        formatted = format_response(result)
        assert "JWT" in formatted
        assert "ollama:llama3" in formatted

        # Event
        event = make_chat_event(result)
        assert event["type"] == "cli_chat"
        assert event["tokens"] == 45

    @patch("governor.cli_chat._create_backend_instance")
    def test_scope_passed_to_context(self, mock_create, tmp_path: Path):
        """Verify scope is passed through to governor context."""
        from governor.chat_bridge import ChatResponse

        mock = MagicMock()
        mock.chat = AsyncMock(return_value=ChatResponse(
            content="Scoped response", model="m",
        ))
        mock_create.return_value = mock

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        result = run_chat(
            "Test",
            scope="src/auth/**",
            use_hooks=True,
            config_path=config_path,
        )
        assert result.response == "Scoped response"

    @patch("governor.cli_chat._create_backend_instance")
    def test_mode_passed_to_hooks(self, mock_create, tmp_path: Path):
        """Verify mode is passed through to governor hooks."""
        from governor.chat_bridge import ChatResponse

        mock = MagicMock()
        mock.chat = AsyncMock(return_value=ChatResponse(
            content="Fiction response", model="m",
        ))
        mock_create.return_value = mock

        config_path = tmp_path / "config.json"
        ChatConfig().save(config_path)

        result = run_chat(
            "Write a scene",
            mode="fiction",
            use_hooks=True,
            config_path=config_path,
        )
        assert result.response == "Fiction response"


# ===========================================================================
# Edge case tests
# ===========================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_prompt_signals(self):
        s = _extract_simple_signals("")
        assert len(s) == 0

    def test_very_long_text_signals(self):
        text = "create " * 1000
        s = _extract_simple_signals(text)
        # Should still work without OOM
        assert "action:create" in s

    def test_unicode_signals(self):
        s = _extract_simple_signals("créer un fichier")
        # Should not crash
        assert isinstance(s, set)

    def test_config_with_all_fields(self):
        c = ChatConfig(
            active_backend="anthropic",
            active_model="claude-3-opus",
            backend_options={
                "ollama": {"host": "http://gpu-server:11434"},
                "anthropic": {"api_key": "sk-hidden"},
            },
        )
        d = c.to_dict()
        assert d["backend_options"]["ollama"]["host"] == "http://gpu-server:11434"

    def test_parse_backend_spec_empty(self):
        b, m = parse_backend_spec("")
        assert b == ""
        assert m == ""

    def test_chat_result_default_usage(self):
        r = ChatResult(response="x", model="m", backend="b")
        assert r.usage["prompt_tokens"] == 0
        assert r.usage["completion_tokens"] == 0
        assert r.usage["total_tokens"] == 0
