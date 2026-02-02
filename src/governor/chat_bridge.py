"""
Chat Bridge: backend abstraction over Anthropic API and Ollama.

Provides a uniform interface for routing chat through different LLM backends
with governor integration hooks. Supports both streaming and non-streaming.

Backend selection via factory:
    backend = create_backend("anthropic", api_key="sk-...")
    backend = create_backend("ollama", host="http://localhost:11434")

Governor hooks inject system prompts and check responses based on context mode.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from .context_manager import GovernorContext, GovernorContextManager


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


class GovernorHooks:
    """Pre/post hooks for governor integration based on context mode."""

    def __init__(self, context: GovernorContext) -> None:
        self.context = context

    def augment_messages(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Inject system prompt based on context mode."""
        system_prompt = self._build_system_prompt()
        if not system_prompt:
            return messages

        # Don't duplicate if system prompt already present
        if messages and messages[0].role == "system":
            return messages

        return [ChatMessage(role="system", content=system_prompt)] + messages

    def check_response(self, content: str) -> list[dict[str, Any]]:
        """Check response content and return any warnings."""
        warnings: list[dict[str, Any]] = []

        if self.context.mode == "fiction":
            # Check for potential canon issues
            fiction_dir = self.context.root / ".fiction-gov"
            if fiction_dir.exists():
                try:
                    from fiction_governor import CanonRegistry
                    # Future: integrate canon checking
                except ImportError:
                    pass

        return warnings

    def _build_system_prompt(self) -> str | None:
        """Build mode-specific system prompt."""
        if self.context.mode == "fiction":
            return self._build_fiction_prompt()
        elif self.context.mode == "code":
            return self._build_code_prompt()
        elif self.context.mode == "nonfiction":
            return self._build_nonfiction_prompt()
        return None

    def _build_fiction_prompt(self) -> str:
        """System prompt for fiction writing mode."""
        return (
            "You are a fiction writing assistant with governor integration. "
            "Help maintain consistency:\n"
            "- Track character motivations and beliefs\n"
            "- Note when actions might contradict established facts\n"
            "- Flag potential continuity issues\n"
            "- Respect the narrative tone and style"
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
        """System prompt for non-fiction writing mode."""
        return (
            "You are a non-fiction writing assistant with governor integration. "
            "Help maintain scholarly rigor:\n"
            "- Verify citations and references\n"
            "- Maintain consistent terminology\n"
            "- Flag unsupported claims\n"
            "- Track the argument structure"
        )


class ChatBridge:
    """Routes chat through backend with governor hooks."""

    def __init__(
        self,
        backend: ChatBackend,
        context_manager: GovernorContextManager,
    ) -> None:
        self.backend = backend
        self.context_manager = context_manager

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
            return self.backend.stream(augmented, model, **kwargs)
        else:
            response = await self.backend.chat(augmented, model, **kwargs)
            # Post-response: check for governor warnings
            warnings = hooks.check_response(response.content)
            if warnings:
                warning_text = "\n\n---\n" + "\n".join(
                    f"[Governor] {w.get('message', str(w))}" for w in warnings
                )
                response = ChatResponse(
                    content=response.content + warning_text,
                    model=response.model,
                    usage=response.usage,
                    finish_reason=response.finish_reason,
                )
            return response

    async def list_models(self) -> list[dict[str, str]]:
        """List models from the backend."""
        return await self.backend.list_models()

    def get_context(self, context_id: str) -> GovernorContext | None:
        """Get a governor context by ID."""
        return self.context_manager.get(context_id)


def create_backend(backend_type: str, **kwargs: Any) -> ChatBackend:
    """Factory: create a ChatBackend by type.

    Args:
        backend_type: "anthropic" or "ollama"
        **kwargs: Backend-specific config (api_key, host, etc.)
    """
    if backend_type == "anthropic":
        return AnthropicBackend(api_key=kwargs["api_key"])
    elif backend_type == "ollama":
        return OllamaBackend(host=kwargs.get("host", "http://localhost:11434"))
    raise ValueError(f"Unknown backend type: {backend_type}")
