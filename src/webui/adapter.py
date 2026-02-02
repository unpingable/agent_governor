"""
OpenAI-compatible API adapter with Governor integration.

Supports switchable backends (Anthropic Claude, Ollama) with isolated governor
contexts per user/project. Designed for use with Open WebUI or any OpenAI-
compatible client.

Run with: uvicorn webui.adapter:app --host 0.0.0.0 --port 8000

Configuration via environment variables:
    BACKEND_TYPE        - "anthropic" or "ollama" (default: "ollama")
    ANTHROPIC_API_KEY   - Required when BACKEND_TYPE=anthropic
    OLLAMA_HOST         - Ollama URL (default: http://localhost:11434)
    GOVERNOR_CONTEXT_ID - Active context ID (default: "default")
    GOVERNOR_MODE       - Context mode: fiction/code/nonfiction/general (default: "general")
    GOVERNOR_CONTEXTS_DIR - Base dir for contexts (default: ~/.governor-contexts)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from governor.chat_bridge import (
    ChatBridge,
    ChatChunk,
    ChatMessage as BridgeChatMessage,
    ChatResponse as BridgeChatResponse,
    GovernorHooks,
    OllamaBackend,
    create_backend,
)
from governor.context_manager import GovernorContextManager

# ============================================================================
# Configuration from environment
# ============================================================================

BACKEND_TYPE = os.environ.get("BACKEND_TYPE", "ollama")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GOVERNOR_CONTEXT_ID = os.environ.get("GOVERNOR_CONTEXT_ID", "default")
GOVERNOR_MODE = os.environ.get("GOVERNOR_MODE", "general")
GOVERNOR_CONTEXTS_DIR = os.environ.get("GOVERNOR_CONTEXTS_DIR", "")

# ============================================================================
# Application setup
# ============================================================================

app = FastAPI(
    title="Governor Chat Adapter",
    description="OpenAI-compatible API with switchable backends and Governor integration",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic Models (OpenAI API format)
# ============================================================================


class ChatMessage(BaseModel):
    role: str
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    stop: list[str] | str | None = None
    max_tokens: int | None = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    user: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage | None = None


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "system"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


# ============================================================================
# Bridge setup (lazy init on first request)
# ============================================================================

_bridge: ChatBridge | None = None
_context_manager: GovernorContextManager | None = None


def _get_context_manager() -> GovernorContextManager:
    global _context_manager
    if _context_manager is None:
        base_dir = Path(GOVERNOR_CONTEXTS_DIR) if GOVERNOR_CONTEXTS_DIR else None
        _context_manager = GovernorContextManager(base_dir=base_dir)
    return _context_manager


def _get_bridge() -> ChatBridge:
    global _bridge
    if _bridge is None:
        kwargs: dict[str, Any] = {}
        if BACKEND_TYPE == "anthropic":
            kwargs["api_key"] = ANTHROPIC_API_KEY
        elif BACKEND_TYPE == "ollama":
            kwargs["host"] = OLLAMA_HOST
        backend = create_backend(BACKEND_TYPE, **kwargs)
        _bridge = ChatBridge(backend=backend, context_manager=_get_context_manager())
    return _bridge


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/v1/models")
async def list_models() -> ModelList:
    """List available models from the backend."""
    try:
        bridge = _get_bridge()
        models = await bridge.list_models()
        return ModelList(
            data=[
                ModelInfo(id=m["id"], owned_by=m.get("owned_by", "system"))
                for m in models
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str) -> ModelInfo:
    """Get info about a specific model."""
    return ModelInfo(id=model_id, owned_by=BACKEND_TYPE)


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse | StreamingResponse:
    """OpenAI-compatible chat completions endpoint."""
    bridge = _get_bridge()

    # Convert Pydantic models to bridge messages
    bridge_messages = [
        BridgeChatMessage(role=m.role, content=m.content) for m in request.messages
    ]

    kwargs: dict[str, Any] = {
        "temperature": request.temperature,
        "top_p": request.top_p,
    }
    if request.max_tokens is not None:
        kwargs["max_tokens"] = request.max_tokens

    context_id = GOVERNOR_CONTEXT_ID

    if request.stream:
        return StreamingResponse(
            _stream_response(bridge, bridge_messages, request.model, context_id, kwargs),
            media_type="text/event-stream",
        )
    else:
        return await _non_streaming_response(
            bridge, bridge_messages, request.model, context_id, kwargs
        )


async def _non_streaming_response(
    bridge: ChatBridge,
    messages: list[BridgeChatMessage],
    model: str,
    context_id: str,
    kwargs: dict[str, Any],
) -> ChatCompletionResponse:
    """Handle non-streaming chat response."""
    try:
        result = await bridge.chat(
            messages=messages,
            model=model,
            context_id=context_id,
            stream=False,
            **kwargs,
        )
        # result is ChatResponse (not streaming)
        assert isinstance(result, BridgeChatResponse)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=result.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=result.content),
                    finish_reason=result.finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=result.usage.get("prompt_tokens", 0),
                completion_tokens=result.usage.get("completion_tokens", 0),
                total_tokens=result.usage.get("total_tokens", 0),
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")


async def _stream_response(
    bridge: ChatBridge,
    messages: list[BridgeChatMessage],
    model: str,
    context_id: str,
    kwargs: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream response in OpenAI SSE format."""
    request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

    try:
        stream = await bridge.chat(
            messages=messages,
            model=model,
            context_id=context_id,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            assert isinstance(chunk, ChatChunk)
            sse_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk.content} if chunk.content else {},
                        "finish_reason": chunk.finish_reason,
                    }
                ],
            }
            yield f"data: {json.dumps(sse_chunk)}\n\n"

            if chunk.finish_reason:
                yield "data: [DONE]\n\n"
                break

    except Exception as e:
        error_chunk = {"error": {"message": str(e), "type": "server_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


# ============================================================================
# Governor Endpoints
# ============================================================================


@app.get("/governor/contexts")
async def list_contexts() -> dict[str, Any]:
    """List all governor contexts."""
    cm = _get_context_manager()
    contexts = cm.list_contexts()
    return {
        "active_context_id": GOVERNOR_CONTEXT_ID,
        "contexts": [ctx.to_dict() for ctx in contexts],
    }


@app.get("/governor/status")
async def governor_status() -> dict[str, Any]:
    """Show governor state for the active context."""
    cm = _get_context_manager()
    ctx = cm.get(GOVERNOR_CONTEXT_ID)

    if ctx is None:
        return {
            "context_id": GOVERNOR_CONTEXT_ID,
            "initialized": False,
            "mode": GOVERNOR_MODE,
        }

    gov_dir = ctx.governor_dir
    has_governor = gov_dir.exists()
    has_fiction = (ctx.root / ".fiction-gov").exists()

    # Count facts and decisions
    facts_count = 0
    decisions_count = 0
    if has_governor:
        facts_index = gov_dir / "facts" / "index.json"
        if facts_index.exists():
            try:
                facts_data = json.loads(facts_index.read_text())
                facts_count = len(facts_data) if isinstance(facts_data, list) else 0
            except (json.JSONDecodeError, OSError):
                pass
        decisions_index = gov_dir / "decisions" / "index.json"
        if decisions_index.exists():
            try:
                dec_data = json.loads(decisions_index.read_text())
                decisions_count = len(dec_data) if isinstance(dec_data, list) else 0
            except (json.JSONDecodeError, OSError):
                pass

    return {
        "context_id": ctx.context_id,
        "initialized": True,
        "mode": ctx.mode,
        "created_at": ctx.created_at,
        "has_governor": has_governor,
        "has_fiction_governor": has_fiction,
        "facts_count": facts_count,
        "decisions_count": decisions_count,
        "metadata": ctx.metadata,
    }


# ============================================================================
# Health / Root
# ============================================================================


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    backend_ok = False
    bridge = _get_bridge()

    try:
        await bridge.list_models()
        backend_ok = True
    except Exception:
        pass

    cm = _get_context_manager()
    ctx = cm.get(GOVERNOR_CONTEXT_ID)

    return {
        "status": "healthy" if backend_ok else "degraded",
        "backend": {
            "type": BACKEND_TYPE,
            "connected": backend_ok,
        },
        "governor": {
            "context_id": GOVERNOR_CONTEXT_ID,
            "mode": GOVERNOR_MODE,
            "initialized": ctx is not None,
        },
    }


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint with basic info."""
    return {
        "name": "Governor Chat Adapter",
        "version": "0.2.0",
        "backend": BACKEND_TYPE,
        "openai_compatible": True,
        "governor_context": GOVERNOR_CONTEXT_ID,
        "governor_mode": GOVERNOR_MODE,
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions",
            "health": "/health",
            "governor_contexts": "/governor/contexts",
            "governor_status": "/governor/status",
        },
    }


# ============================================================================
# CLI Entry Point
# ============================================================================


def main() -> None:
    """Run the adapter server."""
    import uvicorn

    uvicorn.run(
        "webui.adapter:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
