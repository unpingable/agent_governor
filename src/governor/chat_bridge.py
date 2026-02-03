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

import hashlib
import json
import time
import uuid
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


@dataclass
class GovernorCheckResult:
    """Result of a governor response check."""

    violations: list[dict[str, Any]]
    checked_anchors: int
    passed: bool


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

    def _load_mode_anchors(self) -> list:
        """Load continuity anchors for the current mode.

        Dispatches by mode:
        - fiction: reads .fiction-gov/bible/ JSON files
        - nonfiction: reads .nonfiction/corpus.json
        - code/general: no mode-specific anchors

        All modes also check for active puppet and user-registered anchors.
        """
        from .continuity import Anchor, AnchorRegistry
        from .continuity_bridges import (
            anchors_from_fiction_bible,
            anchors_from_nonfiction_corpus,
            anchors_from_puppet_profile,
        )

        anchors: list[Anchor] = []

        # Mode-specific anchors
        if self.context.mode == "fiction":
            bible_data = self._load_fiction_bible_data()
            if bible_data:
                anchors.extend(anchors_from_fiction_bible(bible_data))
        elif self.context.mode == "nonfiction":
            corpus_data = self._load_nonfiction_corpus_data()
            if corpus_data:
                anchors.extend(anchors_from_nonfiction_corpus(corpus_data))

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

    def _load_fiction_bible_data(self) -> dict:
        """Read fiction bible JSON files directly (no Bible() instantiation)."""
        bible_dir = self.context.root / ".fiction-gov" / "bible"
        if not bible_dir.exists():
            return {}
        data: dict[str, Any] = {}
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

    def _load_active_puppet(self) -> dict | None:
        """Read active puppet profile if one exists."""
        active_path = self.context.root / ".governor" / "puppet_active.json"
        if not active_path.exists():
            return None
        try:
            return json.loads(active_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _build_system_prompt(self) -> str | None:
        """Build mode-specific system prompt with anchor context appended."""
        base = self._build_mode_prompt()
        if not base:
            return None

        anchors = self._load_mode_anchors()
        if anchors:
            from .continuity import AnchorRegistry

            reg = AnchorRegistry()
            for a in anchors:
                reg.register(a)
            ctx = reg.to_prompt_context()
            if ctx:
                base += "\n\n" + ctx

        return base

    def _build_mode_prompt(self) -> str | None:
        """Build base mode-specific system prompt (without anchor context)."""
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
        backend_type: "anthropic" or "ollama"
        **kwargs: Backend-specific config (api_key, host, etc.)
    """
    if backend_type == "anthropic":
        return AnthropicBackend(api_key=kwargs["api_key"])
    elif backend_type == "ollama":
        return OllamaBackend(host=kwargs.get("host", "http://localhost:11434"))
    raise ValueError(f"Unknown backend type: {backend_type}")
