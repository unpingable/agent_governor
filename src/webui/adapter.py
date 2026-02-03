"""
OpenAI-compatible API adapter with Governor integration.

Supports switchable backends (Anthropic Claude, Ollama, Claude Code CLI) with
isolated governor contexts per user/project. Designed for use with Open WebUI
or any OpenAI-compatible client.

Run with: uvicorn webui.adapter:app --host 0.0.0.0 --port 8000

Configuration via environment variables:
    BACKEND_TYPE        - "anthropic", "ollama", or "claude-code" (default: "ollama")
    ANTHROPIC_API_KEY   - Required when BACKEND_TYPE=anthropic
    OLLAMA_HOST         - Ollama URL (default: http://localhost:11434)
    CLAUDE_PATH         - Path to claude CLI (default: "claude") for claude-code backend
    GOVERNOR_CONTEXT_ID - Active context ID (default: "default")
    GOVERNOR_MODE       - Context mode: fiction/code/nonfiction/general (default: "general")
    GOVERNOR_CONTEXTS_DIR - Base dir for contexts (default: ~/.governor-contexts)

The claude-code backend uses your Claude Max subscription instead of API credits.
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
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from governor.chat_bridge import (
    ChatBridge,
    ChatChunk,
    ChatMessage as BridgeChatMessage,
    ChatResponse as BridgeChatResponse,
    GovernorHooks,
    OllamaBackend,
    ViolationPendingResponse,
    create_backend,
)
from governor.violation_resolver import (
    ResolutionAction,
    ViolationResolver,
    format_violation_prompt,
)
from governor.context_manager import GovernorContextManager
from governor.viewmodel import build_viewmodel, GovernorViewModel
from webui.summaries import (
    derive_status_pill,
    derive_one_sentence,
    derive_suggested_action,
    derive_last_event,
    derive_why_feed,
    derive_history_days,
)

# ============================================================================
# Configuration from environment
# ============================================================================

BACKEND_TYPE = os.environ.get("BACKEND_TYPE", "ollama")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
CLAUDE_PATH = os.environ.get("CLAUDE_PATH", "claude")  # Path to claude CLI for claude-code backend
GOVERNOR_CONTEXT_ID = os.environ.get("GOVERNOR_CONTEXT_ID", "default")
GOVERNOR_MODE = os.environ.get("GOVERNOR_MODE", "general")
GOVERNOR_CONTEXTS_DIR = os.environ.get("GOVERNOR_CONTEXTS_DIR", "")
GOVERNOR_SHOW_OK_FOOTER = os.environ.get("GOVERNOR_SHOW_OK_FOOTER", "true").lower() in ("true", "1", "yes")

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
        elif BACKEND_TYPE == "claude-code":
            kwargs["claude_path"] = CLAUDE_PATH
        backend = create_backend(BACKEND_TYPE, **kwargs)
        _bridge = ChatBridge(
            backend=backend,
            context_manager=_get_context_manager(),
            show_ok_footer=GOVERNOR_SHOW_OK_FOOTER,
        )
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
    """OpenAI-compatible chat completions endpoint with violation resolution."""
    bridge = _get_bridge()
    cm = _get_context_manager()
    ctx = cm.get_or_create(GOVERNOR_CONTEXT_ID, mode=GOVERNOR_MODE)

    # Check for pending violation FIRST
    resolver = ViolationResolver(
        governor_dir=ctx.governor_dir,
        mode=ctx.mode,
        context_id=ctx.context_id,
    )
    pending = resolver.get_pending()

    if pending:
        # User has a pending violation — check if this message resolves it
        last_message = request.messages[-1].content if request.messages else ""
        action = resolver.is_resolution_command(last_message)

        if action:
            # Handle resolution
            result = await _handle_resolution(resolver, pending, action, bridge, request.model)
            return _format_resolution_response(result, request.model)
        else:
            # Re-present the choices — don't proceed with normal chat
            return _format_violation_pending_response(pending, request.model)

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
        return await _non_streaming_response_with_blocking(
            bridge, bridge_messages, request.model, context_id, kwargs, ctx, resolver
        )


async def _non_streaming_response(
    bridge: ChatBridge,
    messages: list[BridgeChatMessage],
    model: str,
    context_id: str,
    kwargs: dict[str, Any],
) -> ChatCompletionResponse:
    """Handle non-streaming chat response (legacy, no blocking check)."""
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


async def _non_streaming_response_with_blocking(
    bridge: ChatBridge,
    messages: list[BridgeChatMessage],
    model: str,
    context_id: str,
    kwargs: dict[str, Any],
    ctx: Any,
    resolver: ViolationResolver,
) -> ChatCompletionResponse:
    """Handle non-streaming chat response with blocking violation check."""
    try:
        result = await bridge.chat(
            messages=messages,
            model=model,
            context_id=context_id,
            stream=False,
            **kwargs,
        )
        assert isinstance(result, BridgeChatResponse)

        # Check for blocking violations
        run_id = uuid.uuid4().hex[:12]
        hooks = GovernorHooks(ctx)
        check_result = hooks.check_response_blocking(result.content, run_id)

        if isinstance(check_result, ViolationPendingResponse):
            # Return violation prompt instead of normal response
            return _format_violation_pending_response(check_result, model)

        # Normal response (may have non-blocking violations in footer)
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


async def _handle_resolution(
    resolver: ViolationResolver,
    pending: Any,
    action: ResolutionAction,
    bridge: ChatBridge,
    model: str,
) -> Any:
    """Handle a resolution action for a pending violation."""
    if action == ResolutionAction.FIX:
        return await resolver.resolve_fix(pending, bridge.backend, model)
    elif action == ResolutionAction.REVISE:
        return resolver.resolve_revise(pending)
    else:  # PROCEED
        return resolver.resolve_proceed(pending)


def _format_violation_pending_response(
    pending: Any,
    model: str,
) -> ChatCompletionResponse:
    """Format a ViolationPendingResponse as a ChatCompletionResponse.

    The response content is the violation prompt asking user to choose an action.
    """
    # Handle both ViolationPendingResponse and PendingViolation
    if hasattr(pending, "prompt"):
        # ViolationPendingResponse from check_response_blocking
        prompt_text = pending.prompt
    else:
        # PendingViolation from get_pending
        prompt_text = format_violation_prompt(pending.violations, pending.mode)

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=prompt_text),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


def _format_resolution_response(
    result: Any,
    model: str,
) -> ChatCompletionResponse:
    """Format a ResolutionResult as a ChatCompletionResponse."""
    # Build response content based on resolution action
    if result.success:
        if result.action == ResolutionAction.FIX:
            # Return the corrected content
            content = result.new_content or result.message
        elif result.action == ResolutionAction.REVISE:
            # Return original (now permitted) + note about revision
            content = f"[Governor] {result.message}\n\n{result.new_content or ''}"
        else:  # PROCEED
            # Return original (now permitted) + exception note
            content = f"[Governor] {result.message}\n\n{result.new_content or ''}"
    else:
        content = f"[Governor] Resolution failed: {result.message}"

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


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


def _resolve_context() -> tuple[Any | None, str]:
    """Resolve the active governor context.

    Returns (context_or_None, context_id).
    """
    cm = _get_context_manager()
    ctx = cm.get(GOVERNOR_CONTEXT_ID)
    return ctx, GOVERNOR_CONTEXT_ID


def _build_vm_for_context(ctx: Any) -> GovernorViewModel:
    """Build a GovernorViewModel from a resolved context."""
    return build_viewmodel(ctx.governor_dir, ctx.root)


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
    """Show governor state for the active context.

    Backward-compat fields preserved; adds 'viewmodel' key with v2 schema.
    """
    ctx, context_id = _resolve_context()

    if ctx is None:
        return {
            "context_id": context_id,
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

    # Build ViewModel v2
    vm = _build_vm_for_context(ctx)

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
        "viewmodel": vm.to_dict(),
    }


@app.get("/governor/now")
async def governor_now() -> dict[str, Any]:
    """Now screen: glanceable status for the active context."""
    ctx, context_id = _resolve_context()

    if ctx is None:
        return {
            "context_id": context_id,
            "status": "ok",
            "sentence": "OK: no governor context initialized.",
            "last_event": None,
            "suggested_action": None,
            "regime": None,
            "mode": GOVERNOR_MODE,
        }

    vm = _build_vm_for_context(ctx)

    return {
        "context_id": context_id,
        "status": derive_status_pill(vm),
        "sentence": derive_one_sentence(vm),
        "last_event": derive_last_event(vm),
        "suggested_action": derive_suggested_action(vm),
        "regime": vm.regime.name if vm.regime else None,
        "mode": ctx.mode,
    }


@app.get("/governor/why")
async def governor_why(limit: int = 20, severity: str | None = None) -> dict[str, Any]:
    """Why screen: decision/violation/claim feed."""
    ctx, context_id = _resolve_context()

    if ctx is None:
        return {"context_id": context_id, "feed": [], "total": 0}

    vm = _build_vm_for_context(ctx)
    feed = derive_why_feed(vm, limit=limit, severity_filter=severity)

    return {
        "context_id": context_id,
        "feed": feed,
        "total": len(feed),
    }


@app.get("/governor/history")
async def governor_history(days: int = 7) -> dict[str, Any]:
    """History screen: events grouped by calendar day."""
    ctx, context_id = _resolve_context()

    if ctx is None:
        return {"context_id": context_id, "days": []}

    vm = _build_vm_for_context(ctx)
    grouped = derive_history_days(vm, days=days)

    return {
        "context_id": context_id,
        "days": grouped,
    }


@app.get("/governor/detail/{item_id}")
async def governor_detail(item_id: str) -> dict[str, Any]:
    """Drill-down by ID prefix (dec_, clm_, ev_, vio_)."""
    ctx, context_id = _resolve_context()

    if ctx is None:
        raise HTTPException(status_code=404, detail="No governor context initialized.")

    vm = _build_vm_for_context(ctx)

    # Search by prefix
    if item_id.startswith("dec_"):
        for d in vm.decisions:
            if d.id == item_id:
                return {"id": item_id, "type": "decision", "data": d.to_dict()}
    elif item_id.startswith("clm_"):
        for c in vm.claims:
            if c.id == item_id:
                return {"id": item_id, "type": "claim", "data": c.to_dict()}
    elif item_id.startswith("ev_"):
        for e in vm.evidence:
            if e.id == item_id:
                return {"id": item_id, "type": "evidence", "data": e.to_dict()}
    elif item_id.startswith("vio_"):
        for v in vm.violations:
            if v.id == item_id:
                return {"id": item_id, "type": "violation", "data": v.to_dict()}

    raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")


# ============================================================================
# Sidecar UI
# ============================================================================

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/governor/ui", response_class=HTMLResponse)
async def governor_ui() -> HTMLResponse:
    """Serve the single-page Governor UI."""
    html_path = _STATIC_DIR / "governor.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


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
            "governor_now": "/governor/now",
            "governor_why": "/governor/why",
            "governor_history": "/governor/history",
            "governor_detail": "/governor/detail/{item_id}",
            "governor_ui": "/governor/ui",
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
