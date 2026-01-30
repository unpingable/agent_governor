"""
OpenAI-compatible API adapter for Ollama with Governor integration.

Run with: uvicorn webui.adapter:app --host 0.0.0.0 --port 8000

Then point Open WebUI at http://localhost:8000/v1
"""

import json
import os
import time
import uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Ollama endpoint - read from environment variable
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

app = FastAPI(
    title="Governor-Ollama Adapter",
    description="OpenAI-compatible API with Governor integration",
    version="0.1.0",
)

# CORS for Open WebUI
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
    owned_by: str = "ollama"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


# ============================================================================
# Governor Integration Hooks
# ============================================================================


class GovernorHooks:
    """
    Hooks for integrating Governor constraints into the chat flow.

    Override these methods to add fiction-governor or other constraints.
    """

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self.fiction_governor = None
        self._try_load_fiction_governor()

    def _try_load_fiction_governor(self) -> None:
        """Try to load fiction governor if available."""
        try:
            from fiction_governor import CanonRegistry, ContinuityTracker
            canon_dir = self.project_dir / ".fiction-gov"
            if canon_dir.exists():
                self.fiction_governor = {
                    "canon": CanonRegistry(canon_dir),
                    "continuity": ContinuityTracker(canon_dir),
                }
        except ImportError:
            pass

    async def pre_request(
        self,
        messages: list[ChatMessage],
        model: str,
        metadata: dict[str, Any],
    ) -> list[ChatMessage]:
        """
        Hook called before sending request to Ollama.

        Can modify messages, inject system prompts, etc.
        """
        # Example: Inject fiction writing system prompt if in creative mode
        if metadata.get("mode") == "fiction":
            system_prompt = self._build_fiction_system_prompt()
            if system_prompt and (not messages or messages[0].role != "system"):
                messages = [ChatMessage(role="system", content=system_prompt)] + messages

        return messages

    async def post_response(
        self,
        response_content: str,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Hook called after receiving response from Ollama.

        Can validate against canon, check continuity, add warnings.
        Returns (possibly modified content, list of warnings/annotations).
        """
        warnings = []

        # Example: Check for potential canon violations
        if self.fiction_governor and metadata.get("mode") == "fiction":
            # This is where you'd integrate continuity checking
            # For now, just a placeholder
            pass

        return response_content, warnings

    def _build_fiction_system_prompt(self) -> str | None:
        """Build system prompt with fiction writing guidance."""
        if not self.fiction_governor:
            return None

        # Could pull active character states, canon facts, etc.
        return """You are a fiction writing assistant. Help maintain consistency:
- Track character motivations and beliefs
- Note when actions might contradict established facts
- Flag potential continuity issues
"""


# Global hooks instance
hooks = GovernorHooks()


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/v1/models")
async def list_models() -> ModelList:
    """List available models from Ollama."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            response.raise_for_status()
            data = response.json()

            models = [
                ModelInfo(id=model["name"], created=0, owned_by="ollama")
                for model in data.get("models", [])
            ]

            return ModelList(data=models)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama connection error: {e}")


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str) -> ModelInfo:
    """Get info about a specific model."""
    return ModelInfo(id=model_id, owned_by="ollama")


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse | StreamingResponse:
    """
    OpenAI-compatible chat completions endpoint.

    Routes to Ollama with optional Governor integration.
    """
    # Build metadata for hooks
    metadata = {
        "mode": detect_mode(request.messages),
        "user": request.user,
        "model": request.model,
    }

    # Pre-request hook
    messages = await hooks.pre_request(request.messages, request.model, metadata)

    # Convert to Ollama format
    ollama_messages = [
        {"role": m.role, "content": m.content}
        for m in messages
    ]

    ollama_request = {
        "model": request.model,
        "messages": ollama_messages,
        "stream": request.stream,
        "options": {
            "temperature": request.temperature,
            "top_p": request.top_p,
        },
    }

    if request.max_tokens:
        ollama_request["options"]["num_predict"] = request.max_tokens

    if request.stream:
        return StreamingResponse(
            stream_ollama_response(ollama_request, metadata),
            media_type="text/event-stream",
        )
    else:
        return await non_streaming_response(ollama_request, metadata)


async def non_streaming_response(
    ollama_request: dict,
    metadata: dict[str, Any],
) -> ChatCompletionResponse:
    """Handle non-streaming response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json=ollama_request,
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("message", {}).get("content", "")

            # Post-response hook
            content, warnings = await hooks.post_response(content, [], metadata)

            # Add warnings as suffix if any
            if warnings:
                warning_text = "\n\n---\n" + "\n".join(f"⚠️ {w}" for w in warnings)
                content += warning_text

            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                created=int(time.time()),
                model=ollama_request["model"],
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=content),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                ),
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama error: {e}")


async def stream_ollama_response(
    ollama_request: dict,
    metadata: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream response from Ollama in OpenAI SSE format."""
    request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{OLLAMA_HOST}/api/chat",
                json=ollama_request,
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

                    # OpenAI SSE format
                    chunk = {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": ollama_request["model"],
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content} if content else {},
                                "finish_reason": "stop" if done else None,
                            }
                        ],
                    }

                    yield f"data: {json.dumps(chunk)}\n\n"

                    if done:
                        yield "data: [DONE]\n\n"
                        break

        except httpx.RequestError as e:
            error_chunk = {
                "error": {"message": str(e), "type": "server_error"}
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"


def detect_mode(messages: list[ChatMessage]) -> str:
    """
    Detect the conversation mode based on content.

    Used to determine which governor hooks to apply.
    """
    # Simple heuristic - could be made smarter
    text = " ".join(m.content.lower() for m in messages)

    fiction_keywords = ["story", "character", "novel", "chapter", "scene", "dialogue", "plot"]
    if any(kw in text for kw in fiction_keywords):
        return "fiction"

    return "general"


# ============================================================================
# Health/Status Endpoints
# ============================================================================


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Check Ollama connection
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            ollama_ok = response.status_code == 200
    except:
        pass

    return {
        "status": "healthy" if ollama_ok else "degraded",
        "ollama": "connected" if ollama_ok else "disconnected",
        "governor_hooks": hooks.fiction_governor is not None,
    }


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Governor-Ollama Adapter",
        "version": "0.1.0",
        "openai_compatible": True,
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions",
            "health": "/health",
        },
    }


# ============================================================================
# CLI Entry Point
# ============================================================================


def main():
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
