# SPDX-License-Identifier: Apache-2.0
"""
Chat Bridge: backend abstraction over Anthropic API, Ollama, Claude Code, and Codex.

Provides a uniform interface for routing chat through different LLM backends
with governor integration hooks. Supports both streaming and non-streaming.

Backend selection via factory:
    backend = create_backend("anthropic", api_key="sk-...")
    backend = create_backend("ollama", host="http://localhost:11434")
    backend = create_backend("codex", codex_path="codex")

Governor hooks inject system prompts and check responses based on context mode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from .context_manager import GovernorContext, GovernorContextManager


class BackendAuthError(RuntimeError):
    """Base class for backend authentication failures.

    Subclasses provide backend-specific login instructions.
    """

    def __init__(self, message: str, stderr_text: str = "") -> None:
        super().__init__(message)
        self.stderr_text = stderr_text


class ClaudeCodeAuthError(BackendAuthError):
    """Raised when the Claude Code CLI reports an authentication failure."""

    def __init__(self, stderr_text: str = "") -> None:
        detail = stderr_text.strip() if stderr_text.strip() else "authentication required"
        super().__init__(
            f"Claude Code is not logged in: {detail}. "
            "Run `claude /login` in a terminal to re-authenticate.",
            stderr_text=stderr_text,
        )


class CodexAuthError(BackendAuthError):
    """Raised when the Codex CLI reports an authentication failure."""

    def __init__(self, stderr_text: str = "") -> None:
        detail = stderr_text.strip() if stderr_text.strip() else "authentication required"
        super().__init__(
            f"Codex is not logged in: {detail}. "
            "Run `codex auth login` in a terminal to re-authenticate.",
            stderr_text=stderr_text,
        )


# Patterns in CLI stderr that indicate auth failure (shared across backends)
_AUTH_FAILURE_PATTERNS = [
    "not logged in",
    "login required",
    "authentication",
    "unauthorized",
    "auth token",
    "expired",
    "credential",
    "please log in",
    "api key",
    "/login",
    "403",
    "401",
]


def _is_auth_error(stderr_text: str) -> bool:
    """Detect whether CLI stderr indicates an authentication failure."""
    lower = stderr_text.lower()
    return any(pattern in lower for pattern in _AUTH_FAILURE_PATTERNS)


@dataclass
class ChatMessage:
    """A chat message in the conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from an LLM backend."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    finish_reason: str = "stop"


@dataclass
class ChatChunk:
    """A streaming chunk from an LLM backend."""

    content: str
    finish_reason: str | None = None


@dataclass
class GovernorCheckResult:
    """Result of a governor response check."""

    violations: list[dict[str, Any]]
    checked_anchors: int
    passed: bool


@dataclass
class ViolationPendingResponse:
    """Response when violations require resolution (blocking).

    Instead of returning the assistant's response, this object is returned
    to indicate that the user must resolve the violation first.
    """

    blocked_response: str           # The response that was blocked
    violations: list[dict[str, Any]]  # Blocking violations (REJECT severity)
    choices: list[str]              # Available resolution choices
    prompt: str                     # User-facing prompt
    run_id: str                     # Generation run identifier
    pending_id: str = ""            # ID of the pending violation record

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked_response": self.blocked_response,
            "violations": self.violations,
            "choices": self.choices,
            "prompt": self.prompt,
            "run_id": self.run_id,
            "pending_id": self.pending_id,
        }


def _format_governor_footer(result: GovernorCheckResult, show_ok: bool) -> str | None:
    """Format a governor footer string for chat responses.

    Returns a footer string to append, or None if no footer needed.
    """
    if result.violations:
        lines = [f"[Governor] {w.get('message', str(w))}" for w in result.violations]
        return "\n\n---\n" + "\n".join(lines)
    if show_ok and result.checked_anchors > 0:
        return "\n\n---\n[Governor] OK"
    return None


@runtime_checkable
class ChatBackend(Protocol):
    """Protocol for LLM backends."""

    async def chat(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> ChatResponse: ...

    async def stream(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[ChatChunk]: ...

    async def list_models(self) -> list[dict[str, str]]: ...


class OllamaBackend:
    """Ollama LLM backend via HTTP API."""

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host.rstrip("/")

    async def chat(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> ChatResponse:
        """Send a non-streaming chat request to Ollama."""
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]
        payload: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
        }

        options: dict[str, Any] = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs["temperature"]
        if "top_p" in kwargs:
            options["top_p"] = kwargs["top_p"]
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")
        return ChatResponse(
            content=content,
            model=model,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": (
                    data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                ),
            },
            finish_reason="stop",
        )

    async def stream(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[ChatChunk]:
        """Stream a chat response from Ollama."""
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]
        payload: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
        }

        options: dict[str, Any] = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs["temperature"]
        if "top_p" in kwargs:
            options["top_p"] = kwargs["top_p"]
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    content = data.get("message", {}).get("content", "")
                    done = data.get("done", False)
                    yield ChatChunk(
                        content=content,
                        finish_reason="stop" if done else None,
                    )

    async def list_models(self) -> list[dict[str, str]]:
        """List available models from Ollama."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            data = response.json()

        return [
            {"id": m["name"], "owned_by": "ollama"}
            for m in data.get("models", [])
        ]


class AnthropicBackend:
    """Anthropic Claude API backend."""

    # Hardcoded model list (Anthropic doesn't have a list models endpoint)
    MODELS = [
        {"id": "claude-sonnet-4-20250514", "owned_by": "anthropic"},
        {"id": "claude-haiku-4-20250414", "owned_by": "anthropic"},
        {"id": "claude-opus-4-20250514", "owned_by": "anthropic"},
    ]

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Anthropic API key is required")
        self.api_key = api_key

    async def chat(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> ChatResponse:
        """Send a non-streaming chat request to Anthropic."""
        # Separate system message from conversation
        system_text = ""
        conversation: list[dict[str, str]] = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                conversation.append({"role": m.role, "content": m.content})

        # Anthropic requires at least one non-system message
        if not conversation:
            conversation = [{"role": "user", "content": "Hello"}]

        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        # Extract content from Anthropic response format
        content_blocks = data.get("content", [])
        content = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )

        usage_data = data.get("usage", {})
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            usage={
                "prompt_tokens": usage_data.get("input_tokens", 0),
                "completion_tokens": usage_data.get("output_tokens", 0),
                "total_tokens": (
                    usage_data.get("input_tokens", 0)
                    + usage_data.get("output_tokens", 0)
                ),
            },
            finish_reason=data.get("stop_reason", "stop"),
        )

    async def stream(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[ChatChunk]:
        """Stream a chat response from Anthropic."""
        # Separate system message from conversation
        system_text = ""
        conversation: list[dict[str, str]] = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                conversation.append({"role": m.role, "content": m.content})

        if not conversation:
            conversation = [{"role": "user", "content": "Hello"}]

        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            ) as response:
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: " prefix
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield ChatChunk(content=delta.get("text", ""))
                    elif event_type == "message_stop":
                        yield ChatChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[dict[str, str]]:
        """Return hardcoded list of Claude models."""
        return list(self.MODELS)


# ---------------------------------------------------------------------------
# Format-leak detection for CLI backends (ClaudeCode + Codex)
#
# When multi-turn conversations are flattened into a single prompt, the model
# may echo structural markers back into its response. A canary token embedded
# in the conversation wrapper lets us detect this cheaply.
# ---------------------------------------------------------------------------

FORMAT_LEAK_CANARY = "__CANARY_9f3c1a__"

_FORMAT_LEAK_MARKERS = (
    FORMAT_LEAK_CANARY,
    "<conversation_history>",
    "</conversation_history>",
    "<user>",
    "</user>",
    "<assistant>",
    "</assistant>",
)


def _has_format_leak(content: str) -> bool:
    """Return True if model output contains transcript structure markers."""
    return any(marker in content for marker in _FORMAT_LEAK_MARKERS)


def _build_multiturn_prompt(
    conversation_parts: list[tuple[str, str]], *, strict: bool = False,
) -> str:
    """Flatten multi-turn conversation into a single prompt with XML structure.

    Args:
        conversation_parts: list of (role, content) tuples.
        strict: if True, use stronger no-echo instruction (retry attempt).
    """
    parts = []
    for role, content in conversation_parts:
        parts.append(f"<{role}>\n{content}\n</{role}>")

    instruction = (
        "Respond to the last user message above. "
        "Do not reproduce any XML tags, role markers, or transcript "
        "formatting in your response — output only the assistant reply."
        if strict
        else "Respond to the last user message above. Do not echo the "
        "conversation structure or role tags in your response."
    )

    return (
        f"<conversation_history {FORMAT_LEAK_CANARY}>\n"
        + "\n".join(parts)
        + "\n</conversation_history>\n\n"
        + instruction
    )


class ClaudeCodeBackend:
    """Claude Code CLI backend — uses Max subscription instead of API credits.

    Routes chat through the `claude` CLI with --print mode, parsing stream-json output.
    This lets you use your Claude Max subscription for WebUI chat.

    Key implementation details:
    - Prompt is piped via stdin (not CLI arg) to avoid ARG_MAX limits
    - System messages are passed via --system-prompt flag
    - --verbose is required for stream-json output format
    - --model flag passes the model selection to the CLI
    """

    # Model mapping (WebUI model names -> claude CLI understands these)
    MODELS = [
        {"id": "claude-sonnet-4-20250514", "owned_by": "claude-code"},
        {"id": "claude-opus-4-20250514", "owned_by": "claude-code"},
        {"id": "sonnet", "owned_by": "claude-code"},
        {"id": "opus", "owned_by": "claude-code"},
    ]

    def __init__(self, claude_path: str = "claude") -> None:
        """Initialize with path to claude CLI."""
        self.claude_path = claude_path

    async def _run_cli(
        self, system_text: str, user_prompt: str, model: str,
    ) -> ChatResponse:
        """Run claude CLI once and parse the response."""
        import asyncio

        cmd = [
            self.claude_path,
            "--print",
            "--output-format", "json",
            "--verbose",
            "--model", model,
        ]
        if system_text:
            cmd.extend(["--system-prompt", system_text])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=user_prompt.encode("utf-8"))

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            if _is_auth_error(error_msg):
                raise ClaudeCodeAuthError(error_msg)
            raise RuntimeError(f"Claude Code CLI failed: {error_msg}")

        try:
            data = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError:
            content = stdout.decode("utf-8").strip()
            return ChatResponse(content=content, model=model)

        if isinstance(data, list):
            result_item = next(
                (item for item in data if isinstance(item, dict) and item.get("type") == "result"),
                None,
            )
            data = result_item if result_item is not None else {}

        content = data.get("result", "")
        if not isinstance(content, str):
            content = str(content)

        return ChatResponse(
            content=content,
            model=model,
            usage={
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    data.get("usage", {}).get("input_tokens", 0) +
                    data.get("usage", {}).get("output_tokens", 0)
                ),
            },
            finish_reason="stop",
        )

    async def chat(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> ChatResponse:
        """Send a non-streaming chat request via Claude Code CLI."""
        system_text, user_prompt = self._extract_system_and_prompt(messages)
        response = await self._run_cli(system_text, user_prompt, model)

        # Format leak post-check: if the model echoed transcript markers,
        # retry once with a stronger no-echo instruction.
        if _has_format_leak(response.content):
            logger.warning("FormatLeak detected in ClaudeCode response, retrying with strict prompt")
            strict_prompt = _build_multiturn_prompt(
                self._conversation_parts(messages), strict=True,
            )
            response = await self._run_cli(system_text, strict_prompt, model)

        return response

    async def stream(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[ChatChunk]:
        """Stream a chat response via Claude Code CLI."""
        import asyncio

        system_text, user_prompt = self._extract_system_and_prompt(messages)

        # Build command — --verbose is required for stream-json
        # Note: --print mode doesn't execute tools, so no permissions flag needed
        cmd = [
            self.claude_path,
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            "--model", model,
        ]
        if system_text:
            cmd.extend(["--system-prompt", system_text])

        # Run claude CLI with streaming — pipe prompt via stdin
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Write prompt to stdin and close it so the CLI can proceed
        proc.stdin.write(user_prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        # Read stdout line by line
        buffer = ""
        sent_stop = False
        while True:
            chunk = await proc.stdout.read(1024)
            if not chunk:
                break

            buffer += chunk.decode("utf-8", errors="replace")

            # Process complete lines
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Handle different message types from stream-json
                msg_type = data.get("type", "")

                if msg_type == "assistant":
                    # Content chunk
                    content = data.get("message", {}).get("content", "")
                    if isinstance(content, list):
                        # Content blocks
                        for block in content:
                            if block.get("type") == "text":
                                yield ChatChunk(content=block.get("text", ""))
                    elif isinstance(content, str):
                        yield ChatChunk(content=content)

                elif msg_type == "result":
                    # Final result
                    yield ChatChunk(content="", finish_reason="stop")
                    sent_stop = True

        # Process any remaining data in buffer after EOF
        remaining = buffer.strip()
        if remaining:
            try:
                data = json.loads(remaining)
                msg_type = data.get("type", "")
                if msg_type == "assistant":
                    content = data.get("message", {}).get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if block.get("type") == "text":
                                yield ChatChunk(content=block.get("text", ""))
                    elif isinstance(content, str):
                        yield ChatChunk(content=content)
                elif msg_type == "result":
                    yield ChatChunk(content="", finish_reason="stop")
                    sent_stop = True
            except json.JSONDecodeError:
                pass

        # Wait for process to complete and check for errors
        await proc.wait()

        if proc.returncode != 0 and not sent_stop:
            stderr_data = await proc.stderr.read()
            error_msg = stderr_data.decode("utf-8", errors="replace").strip()
            if _is_auth_error(error_msg):
                yield ChatChunk(
                    content="\n\n[Error] Claude Code is not logged in. "
                    "Run `claude /login` in a terminal to re-authenticate."
                )
            else:
                error_text = f"Claude Code CLI failed (exit {proc.returncode})"
                if error_msg:
                    error_text += f": {error_msg}"
                yield ChatChunk(content=f"\n\n[Error] {error_text}")

        # Ensure we send a final stop chunk
        if not sent_stop:
            yield ChatChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[dict[str, str]]:
        """Return available models for Claude Code."""
        return list(self.MODELS)

    @staticmethod
    def _conversation_parts(messages: list[ChatMessage]) -> list[tuple[str, str]]:
        """Extract (role, content) pairs for non-system messages."""
        return [
            (m.role, m.content) for m in messages if m.role != "system"
        ]

    def _extract_system_and_prompt(
        self, messages: list[ChatMessage]
    ) -> tuple[str, str]:
        """Extract system prompt and user conversation from messages.

        Returns:
            (system_text, user_prompt) — system messages concatenated for
            --system-prompt flag, user/assistant turns flattened for stdin.
        """
        system_parts: list[str] = []
        conversation_parts: list[str] = []

        has_assistant = False
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "user":
                conversation_parts.append(("user", msg.content))
            elif msg.role == "assistant":
                conversation_parts.append(("assistant", msg.content))
                has_assistant = True

        system_text = "\n\n".join(system_parts)

        # For single-turn (common case), just send the user message as-is.
        # For multi-turn, flatten with XML tags so the model sees context
        # without echoing role markers in fiction/creative output.
        if len(conversation_parts) == 1 and not has_assistant:
            user_prompt = conversation_parts[0][1]
        elif conversation_parts:
            user_prompt = _build_multiturn_prompt(conversation_parts)
        else:
            user_prompt = ""

        return system_text, user_prompt


class CodexBackend:
    """Codex CLI backend — uses ChatGPT subscription instead of API credits.

    Routes chat through the `codex` CLI with exec --json mode, parsing JSONL output.
    This lets you use your ChatGPT subscription for WebUI chat.

    Key implementation details:
    - Prompt is piped via stdin (using `-` flag) to avoid ARG_MAX limits
    - System messages are prepended to the user prompt (no --system-prompt flag)
    - --json flag produces JSONL output (one JSON object per line)
    - --skip-git-repo-check avoids git repo validation
    - -m flag passes the model selection to the CLI
    """

    MODELS = [
        {"id": "o3", "owned_by": "codex"},
        {"id": "o4-mini", "owned_by": "codex"},
        {"id": "codex-mini", "owned_by": "codex"},
    ]

    def __init__(self, codex_path: str = "codex") -> None:
        """Initialize with path to codex CLI."""
        self.codex_path = codex_path

    async def _run_cli(
        self, combined_prompt: str, model: str,
    ) -> ChatResponse:
        """Run codex CLI once and parse the response."""
        import asyncio

        cmd = [
            self.codex_path,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-m", model,
            "-",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=combined_prompt.encode("utf-8"))

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            if _is_auth_error(error_msg):
                raise CodexAuthError(error_msg)
            raise RuntimeError(f"Codex CLI failed: {error_msg}")

        content_parts: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for line in stdout.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")

            if event_type == "item.completed":
                item = data.get("item", {})
                if item.get("type") == "agent_message":
                    content_parts.append(item.get("text", ""))

            elif event_type == "turn.completed":
                u = data.get("usage", {})
                usage["prompt_tokens"] = u.get("input_tokens", 0)
                usage["completion_tokens"] = u.get("output_tokens", 0)
                usage["total_tokens"] = (
                    u.get("input_tokens", 0) + u.get("output_tokens", 0)
                )

            elif event_type in ("error", "turn.failed"):
                error_msg = data.get("message", "")
                if not error_msg:
                    error_msg = data.get("error", {}).get("message", "Unknown error")
                raise RuntimeError(f"Codex CLI error: {error_msg}")

        return ChatResponse(
            content="".join(content_parts),
            model=model,
            usage=usage,
            finish_reason="stop",
        )

    async def chat(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> ChatResponse:
        """Send a non-streaming chat request via Codex CLI."""
        system_text, user_prompt = self._extract_system_and_prompt(messages)

        if system_text:
            combined_prompt = f"[System]: {system_text}\n\n{user_prompt}"
        else:
            combined_prompt = user_prompt

        response = await self._run_cli(combined_prompt, model)

        # Format leak post-check: if the model echoed transcript markers,
        # retry once with a stronger no-echo instruction.
        if _has_format_leak(response.content):
            logger.warning("FormatLeak detected in Codex response, retrying with strict prompt")
            strict_prompt = _build_multiturn_prompt(
                self._conversation_parts(messages), strict=True,
            )
            if system_text:
                strict_prompt = f"[System]: {system_text}\n\n{strict_prompt}"
            response = await self._run_cli(strict_prompt, model)

        return response

    async def stream(
        self, messages: list[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[ChatChunk]:
        """Stream a chat response via Codex CLI."""
        import asyncio

        system_text, user_prompt = self._extract_system_and_prompt(messages)

        # Prepend system text to prompt
        if system_text:
            combined_prompt = f"[System]: {system_text}\n\n{user_prompt}"
        else:
            combined_prompt = user_prompt

        # Build command
        cmd = [
            self.codex_path,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-m", model,
            "-",
        ]

        # Run codex CLI with streaming — pipe prompt via stdin
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Write prompt to stdin and close it so the CLI can proceed
        proc.stdin.write(combined_prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        # Read stdout line by line
        buffer = ""
        sent_stop = False
        while True:
            chunk = await proc.stdout.read(1024)
            if not chunk:
                break

            buffer += chunk.decode("utf-8", errors="replace")

            # Process complete lines
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "")

                if event_type == "item.completed":
                    item = data.get("item", {})
                    if item.get("type") == "agent_message":
                        yield ChatChunk(content=item.get("text", ""))

                elif event_type == "turn.completed":
                    yield ChatChunk(content="", finish_reason="stop")
                    sent_stop = True

                elif event_type in ("error", "turn.failed"):
                    error_msg = data.get("message", "")
                    if not error_msg:
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                    yield ChatChunk(content=f"\n\n[Error] Codex CLI: {error_msg}")

        # Process any remaining data in buffer after EOF
        remaining = buffer.strip()
        if remaining:
            try:
                data = json.loads(remaining)
                event_type = data.get("type", "")
                if event_type == "item.completed":
                    item = data.get("item", {})
                    if item.get("type") == "agent_message":
                        yield ChatChunk(content=item.get("text", ""))
                elif event_type == "turn.completed":
                    yield ChatChunk(content="", finish_reason="stop")
                    sent_stop = True
            except json.JSONDecodeError:
                pass

        # Wait for process to complete and check for errors
        await proc.wait()

        if proc.returncode != 0 and not sent_stop:
            stderr_data = await proc.stderr.read()
            error_msg = stderr_data.decode("utf-8", errors="replace").strip()
            if _is_auth_error(error_msg):
                yield ChatChunk(
                    content="\n\n[Error] Codex is not logged in. "
                    "Run `codex auth login` in a terminal to re-authenticate."
                )
            else:
                error_text = f"Codex CLI failed (exit {proc.returncode})"
                if error_msg:
                    error_text += f": {error_msg}"
                yield ChatChunk(content=f"\n\n[Error] {error_text}")

        # Ensure we send a final stop chunk
        if not sent_stop:
            yield ChatChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[dict[str, str]]:
        """Return available models for Codex."""
        return list(self.MODELS)

    @staticmethod
    def _conversation_parts(messages: list[ChatMessage]) -> list[tuple[str, str]]:
        """Extract (role, content) pairs for non-system messages."""
        return [
            (m.role, m.content) for m in messages if m.role != "system"
        ]

    def _extract_system_and_prompt(
        self, messages: list[ChatMessage]
    ) -> tuple[str, str]:
        """Extract system prompt and user conversation from messages.

        Returns:
            (system_text, user_prompt) — system messages concatenated,
            user/assistant turns flattened for stdin. System text is prepended
            to the prompt in chat()/stream() since Codex has no system prompt flag.
        """
        system_parts: list[str] = []
        conversation_parts: list[str] = []

        has_assistant = False
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "user":
                conversation_parts.append(("user", msg.content))
            elif msg.role == "assistant":
                conversation_parts.append(("assistant", msg.content))
                has_assistant = True

        system_text = "\n\n".join(system_parts)

        # For single-turn (common case), just send the user message as-is.
        # For multi-turn, flatten with XML tags so the model sees context
        # without echoing role markers in fiction/creative output.
        if len(conversation_parts) == 1 and not has_assistant:
            user_prompt = conversation_parts[0][1]
        elif conversation_parts:
            user_prompt = _build_multiturn_prompt(conversation_parts)
        else:
            user_prompt = ""

        return system_text, user_prompt


class GovernorHooks:
    """Pre/post hooks for governor integration based on context mode."""

    # Valid fiction types (from writing_router.py)
    VALID_FICTION_TYPES = {
        "comedy", "tragedy", "drama", "sincerity",
        "dramedy", "tragicomedy", "sincere_drama", "neutral",
    }

    def __init__(self, context: GovernorContext) -> None:
        self.context = context
        # Context manifest chain state
        self._prev_manifest_hash: str | None = None
        self._prev_build_id: str | None = None
        self._last_manifest: Any | None = None

    def set_fiction_type(self, fiction_type: str) -> None:
        """Set the explicit fiction type for fiction mode.

        Fiction type is NEVER auto-detected. User must explicitly set:
        - Pure types: comedy, tragedy, drama, sincerity
        - Hybrids: dramedy, tragicomedy, sincere_drama
        - neutral: balanced (no strong regime)

        No one wants comedy in their drama. Unless it's a dramedy.

        Args:
            fiction_type: One of the valid fiction types

        Raises:
            ValueError: If fiction_type is not valid
        """
        if fiction_type not in self.VALID_FICTION_TYPES:
            raise ValueError(
                f"Invalid fiction type: {fiction_type}. "
                f"Must be one of: {sorted(self.VALID_FICTION_TYPES)}"
            )
        self.context.metadata["fiction_type"] = fiction_type

    def get_fiction_type(self) -> str | None:
        """Get the currently set fiction type, if any."""
        return self.context.metadata.get("fiction_type")

    def set_code_regime(self, regime: str) -> None:
        """Set the code regime for code mode.

        Args:
            regime: dev, sre, or analysis
        """
        valid = {"dev", "sre", "analysis"}
        if regime not in valid:
            raise ValueError(f"Invalid code regime: {regime}. Must be one of: {valid}")
        self.context.metadata["code_regime"] = regime

    def augment_messages(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Inject system prompt based on context mode."""
        system_prompt = self._build_system_prompt()
        if not system_prompt:
            return messages

        # Don't duplicate if system prompt already present
        if messages and messages[0].role == "system":
            return messages

        return [ChatMessage(role="system", content=system_prompt)] + messages

    def check_response_full(
        self, content: str, collector: Any | None = None
    ) -> GovernorCheckResult:
        """Check response content against mode-specific continuity anchors.

        Returns a GovernorCheckResult with violations, anchor count, and pass/fail.
        """
        anchors = self._load_mode_anchors()
        if not anchors:
            return GovernorCheckResult(violations=[], checked_anchors=0, passed=True)

        from .continuity import ContinuityChecker

        start_ms = time.monotonic()
        checker = ContinuityChecker()
        report = checker.check(content, anchors)
        latency_ms = (time.monotonic() - start_ms) * 1000.0

        # Emit telemetry for one-shot gate
        if collector is not None:
            try:
                run_id = uuid.uuid4().hex[:12]
                ids_str = ",".join(sorted(a.id for a in anchors))
                anchors_hash = hashlib.sha256(ids_str.encode("utf-8")).hexdigest()[:16]
                error_total = round(1.0 - report.score, 6)
                error_by_anchor: dict[str, float] = {}
                for v in report.violations:
                    error_by_anchor[v.anchor_id] = error_by_anchor.get(v.anchor_id, 0.0) + 1.0
                violations_dicts = [
                    {"anchor_id": v.anchor_id, "severity": v.severity.value, "description": v.description}
                    for v in report.violations
                ]
                prompt_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
                tokens_est = len(content.split())

                collector.record_continuity_trace(
                    run_id=run_id,
                    mode=self.context.mode,
                    attempt=0,
                    error_total=error_total,
                    error_by_anchor=error_by_anchor,
                    violations=violations_dicts,
                    action="none",
                    action_params={},
                    delta_total=None,
                    delta_by_anchor={},
                    tokens=tokens_est,
                    latency_ms=latency_ms,
                    prompt_hash=prompt_hash,
                    anchors_hash=anchors_hash,
                )
                final_status = "ACCEPTED" if report.passed else "REFUSED"
                collector.record_continuity_result(
                    run_id=run_id,
                    mode=self.context.mode,
                    attempts=1,
                    final_status=final_status,
                    residual_error_total=error_total,
                    residual_error_by_anchor=error_by_anchor,
                    action_path=["none"],
                    total_tokens=tokens_est,
                    total_latency_ms=latency_ms,
                    monotone=True,
                    oscillation_detected=False,
                    deadzone_actions=[],
                    interference_edges=[],
                    anchors_hash=anchors_hash,
                )
            except Exception:
                pass

        violations = [
            {
                "type": "continuity_violation",
                "anchor_id": v.anchor_id,
                "anchor_type": v.anchor_type.value,
                "severity": v.severity.value,
                "message": v.description,
                "evidence": v.evidence,
            }
            for v in report.violations
        ]
        return GovernorCheckResult(
            violations=violations,
            checked_anchors=len(anchors),
            passed=report.passed,
        )

    def check_response(
        self, content: str, collector: Any | None = None
    ) -> list[dict[str, Any]]:
        """Check response content against mode-specific continuity anchors.

        Returns a list of violation dicts. Delegates to check_response_full().
        """
        return self.check_response_full(content, collector=collector).violations

    def check_response_blocking(
        self, content: str, run_id: str, collector: Any | None = None
    ) -> GovernorCheckResult | ViolationPendingResponse:
        """Check response and return blocking response if REJECT-severity violations.

        For non-blocking violations (WARN, CORRECT), returns normal GovernorCheckResult.
        For blocking violations (REJECT), creates a pending violation and returns
        ViolationPendingResponse that must be resolved before continuing.

        Args:
            content: Response content to check
            run_id: Identifier for this generation run
            collector: Optional telemetry collector

        Returns:
            GovernorCheckResult for non-blocking, ViolationPendingResponse for blocking
        """
        result = self.check_response_full(content, collector=collector)

        # Check for REJECT-severity violations (blocking)
        blocking = [v for v in result.violations if v.get("severity") == "reject"]

        if not blocking:
            return result

        # Create pending violation
        from .violation_resolver import (
            ViolationResolver,
            format_violation_prompt,
            get_mode_choices,
        )

        resolver = ViolationResolver(
            governor_dir=self.context.governor_dir,
            mode=self.context.mode,
            context_id=self.context.context_id,
        )
        pending = resolver.create_pending(blocking, content, run_id)

        return ViolationPendingResponse(
            blocked_response=content,
            violations=blocking,
            choices=get_mode_choices(self.context.mode),
            prompt=format_violation_prompt(blocking, self.context.mode),
            run_id=run_id,
            pending_id=pending.id,
        )

    def _load_mode_anchors(self) -> list:
        """Load continuity anchors for the current mode.

        Dispatches by mode:
        - fiction: reads .fiction-gov/bible/ JSON files + writing module anchors
        - nonfiction: reads .nonfiction/corpus.json + writing module anchors
        - code/general: no mode-specific anchors

        All modes also check for active puppet and user-registered anchors.
        """
        from .continuity import Anchor, AnchorRegistry
        from .continuity_bridges import (
            anchors_from_code_decisions,
            anchors_from_fiction_bible,
            anchors_from_nonfiction_corpus,
            anchors_from_puppet_profile,
            anchors_from_writing_modules,
        )

        anchors: list[Anchor] = []

        # Mode-specific anchors
        if self.context.mode == "fiction":
            bible_data = self._load_fiction_bible_data()
            if bible_data:
                anchors.extend(anchors_from_fiction_bible(bible_data))
            # Add writing module anchors for fiction
            regime = self._detect_active_regime()
            anchors.extend(anchors_from_writing_modules(regime))
        elif self.context.mode == "nonfiction":
            corpus_data = self._load_nonfiction_corpus_data()
            if corpus_data:
                anchors.extend(anchors_from_nonfiction_corpus(corpus_data))
            # Add writing module anchors for nonfiction
            regime = self._detect_active_regime()
            anchors.extend(anchors_from_writing_modules(regime))
        elif self.context.mode == "code":
            decisions_data = self._load_code_decisions_data()
            if decisions_data:
                anchors.extend(anchors_from_code_decisions(decisions_data))
        elif self.context.mode == "research":
            research_anchors = self._load_research_anchors()
            anchors.extend(research_anchors)

        # Puppet anchors (all modes)
        puppet_data = self._load_active_puppet()
        if puppet_data:
            anchors.extend(anchors_from_puppet_profile(puppet_data))

        # User-registered anchors from CLI (all modes)
        anchors_path = self.context.root / ".governor" / "continuity" / "anchors.json"
        if anchors_path.exists():
            try:
                registry = AnchorRegistry.load(anchors_path)
                anchors.extend(registry.all())
            except Exception:
                pass

        return anchors

    def _detect_active_regime(self) -> str:
        """Detect the active writing regime for the current mode.

        Fiction type is EXPLICIT - user must set it, not auto-detected.
        Defaults: fiction→neutral (idle loop), nonfiction→nonfiction, code→code_dev.

        Neutral is the default for fiction. Most language isn't doing heavy
        authorial work - it's connective tissue. Users must explicitly select
        comedy/tragedy/drama/sincerity when they want regime-specific control.

        Priority:
        1. fiction_type metadata (explicit type like comedy/tragedy/dramedy)
        2. regime metadata (legacy, regime name string)
        3. Mode-based defaults

        Returns:
            The regime name string
        """
        # Check for explicit fiction_type (preferred - user-selected)
        fiction_type = self.context.metadata.get("fiction_type")
        if fiction_type:
            # Map fiction type to regime name
            fiction_type_to_regime = {
                "comedy": "comedy",
                "tragedy": "tragedy",
                "drama": "drama",
                "sincerity": "sincerity",
                "dramedy": "drama",  # Primary component
                "tragicomedy": "tragedy",  # Primary component
                "sincere_drama": "drama",  # Primary component
                "neutral": "neutral",  # Idle loop
            }
            return fiction_type_to_regime.get(fiction_type, "neutral")

        # Check for explicit regime in context metadata (legacy)
        regime = self.context.metadata.get("regime")
        if regime:
            return regime

        # Mode-based defaults
        if self.context.mode == "fiction":
            return "neutral"  # Neutral is the idle loop, not comedy
        elif self.context.mode == "nonfiction":
            return "nonfiction"
        elif self.context.mode == "code":
            return "code_dev"  # Code domain uses custody controller
        return "nonfiction"  # Safe default

    def _load_fiction_bible_data(self) -> dict:
        """Read fiction bible + canon JSON files directly (no Bible()/Canon() instantiation)."""
        data: dict[str, Any] = {}

        # Bible data
        bible_dir = self.context.root / ".fiction-gov" / "bible"
        if bible_dir.exists():
            for name in ("characters", "world_rules", "banned_tropes"):
                f = bible_dir / f"{name}.json"
                if f.exists():
                    try:
                        data[name] = json.loads(f.read_text())
                    except (json.JSONDecodeError, OSError):
                        pass
            tone_f = bible_dir / "tone.json"
            if tone_f.exists():
                try:
                    data["tone"] = json.loads(tone_f.read_text())
                except (json.JSONDecodeError, OSError):
                    pass

        # Canon data (events, relationships, threads)
        canon_dir = self.context.root / ".fiction-gov" / "canon"
        if canon_dir.exists():
            canon_map = {
                "events": "canon_events",
                "relationships": "relationships",
                "threads": "threads",
            }
            for filename, key in canon_map.items():
                f = canon_dir / f"{filename}.json"
                if f.exists():
                    try:
                        data[key] = json.loads(f.read_text())
                    except (json.JSONDecodeError, OSError):
                        pass

        return data

    def _load_nonfiction_corpus_data(self) -> dict:
        """Read nonfiction corpus JSON directly (no Corpus() instantiation)."""
        corpus_path = self.context.root / ".nonfiction" / "corpus.json"
        if not corpus_path.exists():
            return {}
        try:
            return json.loads(corpus_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_code_decisions_data(self) -> list[dict]:
        """Read governor decisions index directly (no DecisionLedger instantiation)."""
        decisions_path = self.context.root / ".governor" / "decisions" / "index.json"
        if not decisions_path.exists():
            return []
        try:
            return json.loads(decisions_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _load_active_puppet(self) -> dict | None:
        """Read active puppet profile if one exists."""
        active_path = self.context.root / ".governor" / "puppet_active.json"
        if not active_path.exists():
            return None
        try:
            return json.loads(active_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _load_research_anchors(self) -> list:
        """Build continuity anchors from the research store.

        Claims become definition anchors, assumptions become definition anchors.
        """
        from .continuity import Anchor, AnchorType, Severity

        anchors = []
        store = self._load_research_store()
        if store is None:
            return anchors

        from .research_store import ClaimStatus as RClaimStatus

        for claim in store.claims.values():
            if claim.status in (RClaimStatus.RETRACTED, RClaimStatus.SUPERSEDED):
                continue
            anchors.append(Anchor(
                id=f"research-{claim.id}",
                anchor_type=AnchorType.DEFINITION,
                description=f"Claim: {claim.content}",
                severity=Severity.WARN,
            ))

        for assumption in store.assumptions.values():
            if assumption.status.value == "deprecated":
                continue
            anchors.append(Anchor(
                id=f"research-{assumption.id}",
                anchor_type=AnchorType.DEFINITION,
                description=f"Assumption: {assumption.content}",
                severity=Severity.WARN,
            ))

        return anchors

    def _build_system_prompt(self) -> str | None:
        """Build mode-specific system prompt with anchor context appended."""
        base = self._build_mode_prompt()
        if not base:
            return None

        regions: list[tuple[str, str, str]] = [("mode_base", "mode_base", base)]

        anchors = self._load_mode_anchors()
        if anchors:
            from .continuity import AnchorRegistry

            reg = AnchorRegistry()
            for a in anchors:
                reg.register(a)
            ctx = reg.to_prompt_context()
            if ctx:
                base += "\n\n" + ctx
                regions.append(("mode_anchors", "mode_anchors", ctx))

        # Manifest — fail-open but NOT silent
        try:
            from .context_manifest import build_manifest, ManifestStore, emit_build_receipt
            from .session import get_session_id

            manifest = build_manifest(
                mode=self.context.mode,
                regions=regions,
                session_id=get_session_id(),
                prev_manifest_hash=self._prev_manifest_hash,
                prev_build_id=self._prev_build_id,
            )
            self._prev_manifest_hash = manifest.manifest_hash
            self._prev_build_id = manifest.build_id
            self._last_manifest = manifest
            self._store_manifest(manifest)
        except Exception as exc:
            import sys
            print(f"WARNING: context manifest build failed: {exc}", file=sys.stderr)
            try:
                from .context_manifest import emit_build_failure_receipt
                from .gate_receipt import ReceiptStore
                from pathlib import Path
                gov_dir = Path(".governor")
                if gov_dir.exists():
                    failure_receipt = emit_build_failure_receipt(
                        build_id=uuid.uuid4().hex[:16],
                        mode=self.context.mode,
                        exc_type=type(exc).__name__,
                        exc_message=str(exc)[:200],
                    )
                    ReceiptStore(gov_dir).append(failure_receipt)
            except Exception:
                pass  # Last resort — don't fail the prompt build

        return base

    def _store_manifest(self, manifest: Any) -> None:
        """Persist manifest and emit gate receipt. Warn on error."""
        try:
            from pathlib import Path
            from .context_manifest import ManifestStore, emit_build_receipt
            from .gate_receipt import ReceiptStore, EvidenceStore

            gov_dir = Path(".governor")
            if not gov_dir.exists():
                return

            store = ManifestStore(gov_dir)
            store.append(manifest)

            receipt = emit_build_receipt(manifest)
            receipt_store = ReceiptStore(gov_dir)
            receipt_store.append(receipt)
        except Exception as exc:
            import sys
            print(f"WARNING: context manifest store failed: {exc}", file=sys.stderr)

    def _build_mode_prompt(self) -> str | None:
        """Build base mode-specific system prompt (without anchor context)."""
        if self.context.mode == "fiction":
            return self._build_fiction_prompt()
        elif self.context.mode == "code":
            return self._build_code_prompt()
        elif self.context.mode == "nonfiction":
            return self._build_nonfiction_prompt()
        elif self.context.mode == "research":
            return self._build_research_prompt()
        return None

    def _build_fiction_prompt(self) -> str:
        """System prompt for fiction writing mode.

        Incorporates affect regime awareness, governance invisibility rules,
        and tone envelope guidance from fic.md and tone.md specs.
        """
        regime = self._detect_active_regime()
        return (
            "You are a fiction writing assistant with governor integration.\n\n"
            "## Core Invariant\n"
            "Governance must never surface in-band. The reader should never detect "
            "that an author is managing outcomes. No apologies, no meta-commentary, "
            "no committee voice, no hedging that reveals authorial anxiety.\n\n"
            "## Canon Authority\n"
            "Canonical truth lives only in the Characters and World Rules stores.\n"
            "Facts mentioned in chat are provisional draft notes until saved to canon.\n"
            "Do not imply a chat-stated fact is \"remembered\" or established canon "
            "unless it exists in canon.\n"
            "When the user states a new character or world fact that is not in canon, "
            "acknowledge it as a draft detail and include a single short nudge: "
            "\"If you want that to stick, add it under Characters/World Rules.\"\n"
            "If the user asks for consistency or recall and the fact is not in canon, "
            "say so plainly and point to the canon UI.\n\n"
            "## Affect Regime\n"
            f"Current regime: {regime}. Maintain regime-appropriate tone and pacing.\n"
            "- Comedy: preserve perceived risk (Rp). Hedges kill comedy.\n"
            "- Tragedy: meaning must lag suffering. Don't explain too soon.\n"
            "- Horror: maintain unresolved threat. Premature closure kills tension.\n"
            "- Romance: authentic vulnerability. Fake confidence kills credibility.\n\n"
            "## Consistency\n"
            "- Track character motivations and beliefs\n"
            "- Note when actions might contradict established facts\n"
            "- Respect the narrative tone and style\n"
            "- Exit cleanly without moral bows or unearned CTAs"
        )

    def _build_code_prompt(self) -> str:
        """System prompt for code development mode."""
        return (
            "You are a code development assistant with governor integration. "
            "Help maintain architectural coherence:\n"
            "- Reference existing decisions before proposing changes\n"
            "- Cite evidence for claims about the codebase\n"
            "- Flag potential conflicts with established patterns\n"
            "- Don't claim files exist without checking"
        )

    def _build_nonfiction_prompt(self) -> str:
        """System prompt for non-fiction writing mode.

        Incorporates epistemic control guidance from nonfic.md spec:
        claim levels, velocity discipline, Ep/Re expectations, governance
        visibility suppression.
        """
        return (
            "You are a non-fiction writing assistant with governor integration.\n\n"
            "## Core Invariant\n"
            "Governance must never surface in-band. No preemptive defense, no virtue "
            "signaling, no balance theater, no empty rigor markers.\n\n"
            "## Epistemic Control\n"
            "- Claims have levels: SOFT (maybe), HARD (supported), NORM (value-laden)\n"
            "- Don't promote claims without explicit evidence support\n"
            "- Maintain velocity discipline: claim rate should not outpace evidence\n"
            "- Normative claims require sufficient evidence foundation first\n\n"
            "## Epistemic Honesty (Ep)\n"
            "- Calibrate hedges: epistemic hedges (uncertainty) are appropriate, "
            "social hedges (anxiety) reveal governance\n"
            "- Expose falsifiers and boundary conditions\n"
            "- Engage alternatives honestly, not as strawmen\n\n"
            "## Structural Integrity\n"
            "- Verify citations and references\n"
            "- Maintain consistent terminology\n"
            "- Track the argument structure\n"
            "- Exit cleanly without moral inflation or unearned conclusions"
        )

    def _build_research_prompt(self) -> str:
        """System prompt for research writing mode.

        Integrates epistemic debt tracking: claims, assumptions, uncertainties,
        typed links, and the ED score. Injects accepted sources and claims
        so the capture loop pays rent on the next turn.
        """
        # Load ED summary and accepted context if store exists
        ed_context = ""
        accepted_context = ""
        store = self._load_research_store()
        if store is not None:
            ed = store.compute_ed()
            floating = ed["floating"]
            uncertain = ed["open_uncertain"]
            total = ed["total"]
            ed_context = (
                f"\n\n## Current Epistemic Debt\n"
                f"ED Score: {total} | {floating} floating claims | "
                f"{uncertain} open uncertainties\n"
                f"Every unsupported claim and unresolved uncertainty adds to ED. "
                f"Support claims with evidence links to reduce it."
            )
            accepted_context = self._build_accepted_context(store)

        return (
            "You are a research writing assistant with epistemic debt tracking.\n\n"
            "## Core Principle\n"
            "Epistemic debt is like technical debt: visible, survivable, impossible "
            "to gaslight away. Every claim starts FLOATING until supported by evidence. "
            "Unsupported claims are liabilities, not lies — but they accumulate.\n\n"
            "## Claim Registration\n"
            "- Register claims explicitly. A claim without a scope is a liability.\n"
            "- Support claims with typed links (SUPPORTS, CONTESTS, ASSUMES, "
            "SUPERSEDES, NARROWS).\n"
            "- FLOATING claims need evidence. CONTESTED claims need resolution.\n\n"
            "## Assumptions & Uncertainties\n"
            "- Surface assumptions early. Hidden assumptions are the worst debt.\n"
            "- Log uncertainties when you find them. An acknowledged uncertainty is "
            "better than a hidden one.\n"
            "- Resolving uncertainty without new support is a collapse — it inflates ED.\n\n"
            "## ED Score\n"
            "- ED rises with floating claims, missing scopes, open uncertainties, "
            "collapse events, and unresolved contests.\n"
            "- Reduce ED by adding support links, filling in scopes, and resolving "
            "uncertainties with evidence."
            + ed_context
            + accepted_context
        )

    def _build_accepted_context(self, store: Any) -> str:
        """Build ACCEPTED SOURCES and ACCEPTED CLAIMS blocks for prompt injection.

        Rules (from design review):
        - Bounded: cap at K=20 claims, S=25 sources
        - Machine-checkable: structured format with IDs and ref types
        - Don't brick empty ledger: graceful minimal injection when nothing accepted
        - Separate sources from claims: distinct sections
        - CANDIDATE_SOURCES format: model proposes new refs for user to accept/reject
        """
        # Collect active claims (not retracted/superseded), newest first
        active_claims = [
            c for c in store.claims.values()
            if c.status.value not in ("retracted", "superseded")
        ]
        active_claims.sort(key=lambda c: c.created_at, reverse=True)
        active_claims = active_claims[:20]

        # Extract unique source_refs preserving insertion order
        source_refs: list[str] = []
        seen_refs: set[str] = set()
        for claim in active_claims:
            if claim.source_ref and claim.source_ref not in seen_refs:
                source_refs.append(claim.source_ref)
                seen_refs.add(claim.source_ref)
        source_refs = source_refs[:25]

        # Empty ledger — minimal instruction, don't brick the prompt
        if not active_claims and not source_refs:
            return (
                "\n\n## Source Discipline\n"
                "No sources accepted yet. Do not fabricate citations. "
                "If you reference a source, present it as:\n"
                "CANDIDATE_SOURCE: <ref_type>:<identifier>\n"
                "The user will accept or reject it."
            )

        parts: list[str] = []

        if source_refs:
            parts.append("## Accepted Sources")
            for ref in source_refs:
                parts.append(f"- {ref}")

        if active_claims:
            if parts:
                parts.append("")
            parts.append("## Accepted Claims")
            for claim in active_claims:
                line = f"[{claim.id}] \"{claim.content}\""
                if claim.source_ref:
                    line += f" source_ref={claim.source_ref}"
                if claim.status.value != "floating":
                    line += f" ({claim.status.value})"
                parts.append(line)

        # Enforcement instruction
        parts.append("")
        if source_refs:
            parts.append(
                "## Source Discipline\n"
                "Cite only accepted source_refs when making supported claims. "
                "To introduce a new source, present it as:\n"
                "CANDIDATE_SOURCE: <ref_type>:<identifier>\n"
                "The user will accept or reject it."
            )
        else:
            parts.append(
                "## Source Discipline\n"
                "No source_refs accepted yet. Do not fabricate citations. "
                "If you reference a source, present it as:\n"
                "CANDIDATE_SOURCE: <ref_type>:<identifier>\n"
                "The user will accept or reject it."
            )

        return "\n\n" + "\n".join(parts)

    def _load_research_store(self) -> Any | None:
        """Load the research store if it exists."""
        try:
            from .research_store import ResearchStore
            return ResearchStore(self.context.governor_dir)
        except Exception:
            return None


class ChatBridge:
    """Routes chat through backend with governor hooks."""

    def __init__(
        self,
        backend: ChatBackend,
        context_manager: GovernorContextManager,
        collector: Any | None = None,
        show_ok_footer: bool = True,
    ) -> None:
        self.backend = backend
        self.context_manager = context_manager
        self._collector = collector
        self.show_ok_footer = show_ok_footer

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        context_id: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse | AsyncIterator[ChatChunk]:
        """Route chat through backend with governor hooks applied."""
        ctx = self.context_manager.get_or_create(context_id)
        hooks = GovernorHooks(ctx)

        # Pre-request: inject system prompt
        augmented = hooks.augment_messages(messages)

        if stream:
            raw_stream = self.backend.stream(augmented, model, **kwargs)
            return self._checked_stream(raw_stream, hooks, self.show_ok_footer)
        else:
            response = await self.backend.chat(augmented, model, **kwargs)
            # Post-response: check for governor warnings
            result = hooks.check_response_full(
                response.content, collector=self._collector
            )
            footer = _format_governor_footer(result, self.show_ok_footer)
            if footer:
                response = ChatResponse(
                    content=response.content + footer,
                    model=response.model,
                    usage=response.usage,
                    finish_reason=response.finish_reason,
                )
            return response

    async def _checked_stream(
        self,
        raw_stream: AsyncIterator[ChatChunk],
        hooks: GovernorHooks,
        show_ok: bool,
    ) -> AsyncIterator[ChatChunk]:
        """Wrap a raw backend stream with governor checks.

        Yields chunks in real-time. On stream completion, runs governor check
        on accumulated content and injects a footer chunk before the final
        finish_reason chunk if needed.
        """
        accumulated: list[str] = []
        async for chunk in raw_stream:
            if chunk.content:
                accumulated.append(chunk.content)
            if chunk.finish_reason is not None:
                # Stream is done — run governor check on accumulated text
                full_text = "".join(accumulated)
                try:
                    result = hooks.check_response_full(
                        full_text, collector=self._collector
                    )
                    footer = _format_governor_footer(result, show_ok)
                except Exception as e:
                    footer = f"\n\n---\n[Governor] Check failed: {e}"
                if footer:
                    # Yield footer content before the finish chunk
                    yield ChatChunk(content=footer, finish_reason=None)
                yield chunk
                return
            else:
                yield chunk

    async def list_models(self) -> list[dict[str, str]]:
        """List models from the backend."""
        return await self.backend.list_models()

    def get_context(self, context_id: str) -> GovernorContext | None:
        """Get a governor context by ID."""
        return self.context_manager.get(context_id)


def create_backend(backend_type: str, **kwargs: Any) -> ChatBackend:
    """Factory: create a ChatBackend by type.

    Args:
        backend_type: "anthropic", "ollama", "claude-code", or "codex"
        **kwargs: Backend-specific config (api_key, host, claude_path, codex_path, etc.)
    """
    if backend_type == "anthropic":
        return AnthropicBackend(api_key=kwargs["api_key"])
    elif backend_type == "ollama":
        return OllamaBackend(host=kwargs.get("host", "http://localhost:11434"))
    elif backend_type == "claude-code":
        return ClaudeCodeBackend(claude_path=kwargs.get("claude_path", "claude"))
    elif backend_type == "codex":
        return CodexBackend(codex_path=kwargs.get("codex_path", "codex"))
    raise ValueError(f"Unknown backend type: {backend_type}")
