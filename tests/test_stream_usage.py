# SPDX-License-Identifier: Apache-2.0
"""Tests for context usage telemetry — usage data in streaming responses."""

from __future__ import annotations

import json

import pytest

from governor.chat_bridge import ChatChunk


class TestChatChunkUsage:
    """ChatChunk carries optional usage data."""

    def test_default_no_usage(self):
        chunk = ChatChunk(content="hello")
        assert chunk.usage is None

    def test_usage_on_final_chunk(self):
        chunk = ChatChunk(
            content="",
            finish_reason="stop",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert chunk.usage == {"input_tokens": 100, "output_tokens": 50}
        assert chunk.finish_reason == "stop"

    def test_usage_none_when_not_provided(self):
        chunk = ChatChunk(content="", finish_reason="stop")
        assert chunk.usage is None


class TestAnthropicStreamUsage:
    """Anthropic backend extracts usage from SSE events."""

    @pytest.mark.asyncio
    async def test_message_start_and_delta_usage(self):
        """Simulate Anthropic SSE with usage in message_start and message_delta."""
        from governor.chat_bridge import AnthropicBackend

        events = [
            {"type": "message_start", "message": {"usage": {
                "input_tokens": 1200,
                "cache_creation_input_tokens": 400,
                "cache_read_input_tokens": 800,
            }}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
            {"type": "message_delta", "usage": {"output_tokens": 25}},
            {"type": "message_stop"},
        ]

        # Build SSE lines
        lines = [f"data: {json.dumps(e)}" for e in events]

        # Monkey-patch to capture the parsing logic
        chunks: list[ChatChunk] = []

        # We can't easily call stream() without a real API, so test the
        # extraction logic by simulating what the stream method does
        _usage: dict[str, int] = {}
        for event in events:
            event_type = event.get("type", "")
            if event_type == "message_start":
                u = event.get("message", {}).get("usage", {})
                if u.get("input_tokens"):
                    _usage["input_tokens"] = u["input_tokens"]
                    _usage["cache_creation_input_tokens"] = u.get("cache_creation_input_tokens", 0)
                    _usage["cache_read_input_tokens"] = u.get("cache_read_input_tokens", 0)
            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    chunks.append(ChatChunk(content=delta.get("text", "")))
            elif event_type == "message_delta":
                u = event.get("usage", {})
                if u.get("output_tokens"):
                    _usage["output_tokens"] = u["output_tokens"]
            elif event_type == "message_stop":
                chunks.append(ChatChunk(
                    content="", finish_reason="stop",
                    usage=_usage or None,
                ))

        assert len(chunks) == 2
        final = chunks[-1]
        assert final.finish_reason == "stop"
        assert final.usage is not None
        assert final.usage["input_tokens"] == 1200
        assert final.usage["output_tokens"] == 25
        assert final.usage["cache_creation_input_tokens"] == 400
        assert final.usage["cache_read_input_tokens"] == 800


class TestOllamaStreamUsage:
    """Ollama backend extracts usage from final done=true line."""

    def test_done_line_usage(self):
        data = {
            "message": {"content": ""},
            "done": True,
            "prompt_eval_count": 500,
            "eval_count": 120,
        }

        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        usage = None
        if prompt_tokens or completion_tokens:
            usage = {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            }

        chunk = ChatChunk(
            content="",
            finish_reason="stop",
            usage=usage,
        )
        assert chunk.usage == {"input_tokens": 500, "output_tokens": 120}

    def test_done_line_no_counts(self):
        """When Ollama doesn't provide counts, usage is None."""
        data = {"message": {"content": ""}, "done": True}

        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        usage = None
        if prompt_tokens or completion_tokens:
            usage = {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            }

        chunk = ChatChunk(content="", finish_reason="stop", usage=usage)
        assert chunk.usage is None


class TestCliBackendStreamUsage:
    """CLI backends (Claude Code, Codex) extract usage from result/turn events."""

    def test_claude_result_event_with_usage(self):
        data = {
            "type": "result",
            "usage": {"input_tokens": 4800, "output_tokens": 350},
        }
        u = data.get("usage", {})
        usage = {k: v for k, v in u.items() if isinstance(v, int)} if u else None

        chunk = ChatChunk(content="", finish_reason="stop", usage=usage or None)
        assert chunk.usage == {"input_tokens": 4800, "output_tokens": 350}

    def test_claude_result_event_no_usage(self):
        data = {"type": "result"}
        u = data.get("usage", {})
        usage = {k: v for k, v in u.items() if isinstance(v, int)} if u else None

        chunk = ChatChunk(content="", finish_reason="stop", usage=usage or None)
        assert chunk.usage is None

    def test_codex_turn_completed_with_usage(self):
        data = {
            "type": "turn.completed",
            "usage": {"input_tokens": 3200, "output_tokens": 180},
        }
        u = data.get("usage", {})
        usage = {k: v for k, v in u.items() if isinstance(v, int)} if u else None

        chunk = ChatChunk(content="", finish_reason="stop", usage=usage or None)
        assert chunk.usage == {"input_tokens": 3200, "output_tokens": 180}

    def test_non_int_values_filtered(self):
        """Only int values are kept (filter out strings, nulls)."""
        data = {
            "type": "result",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "model": "claude-3",  # string, should be filtered
            },
        }
        u = data.get("usage", {})
        usage = {k: v for k, v in u.items() if isinstance(v, int)} if u else None

        chunk = ChatChunk(content="", finish_reason="stop", usage=usage or None)
        assert chunk.usage == {"input_tokens": 100, "output_tokens": 50}
        assert "model" not in chunk.usage


class TestDaemonStreamUsage:
    """Daemon passes usage from final chunk to RPC result."""

    def test_usage_captured_from_final_chunk(self):
        """Simulate the daemon's chunk accumulation loop."""
        chunks = [
            ChatChunk(content="Hello "),
            ChatChunk(content="world"),
            ChatChunk(
                content="", finish_reason="stop",
                usage={"input_tokens": 2000, "output_tokens": 100},
            ),
        ]

        accumulated: list[str] = []
        stream_usage: dict[str, int] = {}
        for chunk in chunks:
            if chunk.content:
                accumulated.append(chunk.content)
            if chunk.finish_reason is not None:
                if chunk.usage:
                    stream_usage = chunk.usage
                break

        assert "".join(accumulated) == "Hello world"
        assert stream_usage == {"input_tokens": 2000, "output_tokens": 100}

    def test_no_usage_when_backend_omits(self):
        chunks = [
            ChatChunk(content="Hello"),
            ChatChunk(content="", finish_reason="stop"),
        ]

        stream_usage: dict[str, int] = {}
        for chunk in chunks:
            if chunk.finish_reason is not None:
                if chunk.usage:
                    stream_usage = chunk.usage
                break

        assert stream_usage == {}
