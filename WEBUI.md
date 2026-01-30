# Agent Governor WebUI

A ChatGPT-like interface for local LLMs with Governor integration.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Open WebUI    │────▶│ Governor Adapter │────▶│   Ollama    │
│  (Chat UI)      │     │ (OpenAI API)     │     │  (LLMs)     │
│  port 3000      │     │  port 8000       │     │ port 11434  │
└─────────────────┘     └──────────────────┘     └─────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  Governor    │
                        │  Hooks       │
                        │ (fiction,    │
                        │  ops, etc)   │
                        └──────────────┘
```

The adapter sits between Open WebUI and Ollama, providing:
- OpenAI-compatible API endpoints
- Fiction governor integration (canon checking, continuity)
- Conversation mode detection
- Extensible hook system

## Quick Start (Docker)

The easiest way to run everything:

```bash
# Start the full stack
docker-compose up -d

# Pull a model (first time only)
docker exec -it governor-ollama ollama pull deepseek-coder:6.7b

# Open the UI
open http://localhost:3000
```

That's it! Open WebUI will be available at `http://localhost:3000`.

## Quick Start (Manual)

If you prefer running without Docker:

### 1. Start Ollama

```bash
# Install Ollama if needed
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull a model (in another terminal)
ollama pull deepseek-coder:6.7b
```

### 2. Start the Governor Adapter

```bash
# Install dependencies
pip install -e ".[webui]"

# Start the adapter
governor-webui
# Or: uvicorn webui.adapter:app --host 0.0.0.0 --port 8000
```

### 3. Start Open WebUI

```bash
# Using Docker (easiest)
docker run -d -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=not-needed \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e WEBUI_AUTH=false \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main

# Or install from pip
pip install open-webui
open-webui serve --port 3000
```

### 4. Access the UI

Open http://localhost:3000 in your browser.

## Configuration

### Adapter Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `GOVERNOR_PROJECT_DIR` | Current directory | Project dir for governor configs |

### Open WebUI Settings

In Open WebUI settings, configure:
- **OpenAI API Base URL**: `http://localhost:8000/v1` (or `http://adapter:8000/v1` in Docker)
- **API Key**: `not-needed` (any value works)

## Using for Fiction Writing

The adapter detects "fiction mode" based on conversation content and can:

1. **Inject system prompts** with fiction writing guidance
2. **Check continuity** against established canon (if configured)
3. **Track character states** across conversations
4. **Warn about inconsistencies**

### Setting Up Fiction Governor

```bash
# Initialize fiction governor in your project
fiction-gov init --project "My Novel"

# Add canon facts
fiction-gov canon add "character" "Elena has blue eyes"
fiction-gov canon add "setting" "The story takes place in 2045"

# Start writing - the UI will now have access to this canon
```

### Fiction Mode Detection

The adapter automatically detects fiction writing based on keywords:
- story, character, novel, chapter, scene, dialogue, plot

You can also explicitly set the mode in your system prompt.

## Extending the Adapter

The adapter has a hook system for custom logic:

```python
# src/webui/adapter.py

class GovernorHooks:
    async def pre_request(self, messages, model, metadata):
        """Called before sending to Ollama."""
        # Add custom system prompts
        # Inject context
        # Modify messages
        return messages

    async def post_response(self, content, messages, metadata):
        """Called after receiving response."""
        # Validate against canon
        # Check continuity
        # Add warnings
        return content, warnings
```

## Recommended Models for Writing

| Model | Size | Best For |
|-------|------|----------|
| `deepseek-coder:6.7b` | 4GB | General, fast responses |
| `llama2:13b` | 8GB | Creative writing |
| `mixtral:8x7b` | 26GB | Best quality (needs GPU) |
| `neural-chat:7b` | 4GB | Conversational |

Pull with:
```bash
ollama pull <model-name>
# or via Docker:
docker exec -it governor-ollama ollama pull <model-name>
```

## Troubleshooting

### "Connection refused" errors
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check adapter is running
curl http://localhost:8000/health
```

### Models not showing in UI
```bash
# Verify models are pulled
ollama list

# Check adapter can see them
curl http://localhost:8000/v1/models
```

### Slow responses
- Use smaller models (7B instead of 13B+)
- Ensure GPU acceleration is working
- Check system resources

### Docker networking issues
```bash
# Restart the stack
docker-compose down && docker-compose up -d

# Check container logs
docker-compose logs -f adapter
```

## Ports Summary

| Service | Port | Description |
|---------|------|-------------|
| Open WebUI | 3000 | Chat interface |
| Governor Adapter | 8000 | OpenAI-compatible API |
| Ollama | 11434 | LLM backend |
