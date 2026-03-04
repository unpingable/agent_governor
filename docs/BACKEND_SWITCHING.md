# Backend Switching

The WebUI supports switching between AI backends at runtime — no restart
needed.

## Available Backends

| Backend | Type | Auth Required |
|---------|------|---------------|
| Ollama | `ollama` | None (local) |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Claude Code CLI | `claude-code` | Claude subscription (CLI auth) |
| Codex CLI | `codex` | ChatGPT subscription (CLI auth) |

## Switching in the UI

The governor sidebar has a **Backend** card with a dropdown. Select a
different backend and the model list updates automatically. The connection
dot shows green (connected) or red (unreachable).

## Switching via API

### List backends

```
GET /v1/backends
```

Response:
```json
{
  "backends": [
    {"type": "ollama", "available": true, "active": true, "config_hint": "OLLAMA_HOST=http://localhost:11434"},
    {"type": "anthropic", "available": false, "active": false, "config_hint": "Set ANTHROPIC_API_KEY"},
    {"type": "claude-code", "available": true, "active": false, "config_hint": "CLAUDE_PATH=claude"},
    {"type": "codex", "available": false, "active": false, "config_hint": "codex CLI not found"}
  ],
  "active": "ollama",
  "connected": true
}
```

### Switch backend

```
POST /v1/backends/switch
Content-Type: application/json

{"backend_type": "anthropic"}
```

Response:
```json
{
  "success": true,
  "backend_type": "anthropic",
  "connected": true,
  "models": ["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"]
}
```

## Docker: start-codex.sh

For Codex backend in Docker, use `start-codex.sh` instead of `start.sh`:

```bash
bash start-codex.sh
```

It auto-detects:
- Node.js version (from `node --version` or nvm)
- Architecture (`x86_64` → `x86_64-unknown-linux-musl`, `aarch64` → `aarch64-unknown-linux-musl`)
- Codex binary path in nvm global modules
- Codex auth at `~/.codex/`

Writes a `.env` file with `REAL_HOME`, `NODE_VERSION`, and `ARCH`, then
starts `docker-compose` with the Codex override file.
