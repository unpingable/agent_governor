---
paths:
  - "src/webui/**"
  - "src/governor/chat_bridge.py"
  - "src/governor/context_manager.py"
  - "src/governor/interferometry.py"
  - "tests/test_web_adapter*"
  - "tests/test_chat_bridge*"
  - "tests/test_interferometry*"
  - "tests/test_context_manager*"
  - "docker-compose*"
  - "start*.sh"
  - "Dockerfile*"
---
# WebUI & Chat Infrastructure

## Key Patterns

- ClaudeCodeBackend uses `claude --print` CLI mode; `--verbose` required for `stream-json` output
- Claude Code CLI takes prompt via stdin (not args) to avoid ARG_MAX
- System prompts go via `--system-prompt` flag, not inline `[System]:` markup
- `--output-format json --verbose` returns a **JSON array** `[{system}, {assistant}, {result}]`, NOT a dict
- `--output-format stream-json --verbose` returns one JSON object per line (newline-delimited)
- `data["result"]` from the result item is a plain string
- WebUI root (`/`) serves combined chat+governor HTML; JSON info at `/api/info`
- Governor sidebar polls `/governor/status`, `/governor/now`, and mode-specific endpoints on 3s interval
- Docker `start.sh` auto-detects REAL_HOME and CLAUDE_VERSION for snap Docker compatibility

## Modules

- **adapter.py** — FastAPI adapter with OpenAI-compatible API, governor endpoints, backend switching (`GET /v1/backends`, `POST /v1/backends/switch`)
- **static/index.html** — Combined chat + governor sidebar UI with backend dropdown
- **chat_bridge.py** — ChatBridge, OllamaBackend, AnthropicBackend, ClaudeCodeBackend, CodexBackend, GovernorHooks, create_backend factory
- **context_manager.py** — GovernorContext, GovernorContextManager, isolated per-user/project contexts
- **interferometry.py** — Multi-model claim comparison: parallel + serial ("yes, and") modes, claim alignment (shared/unique/conflicting), Jaccard fingerprinting, ledger promotion, JSON persistence

## Backend Toggle

- `_current_backend_type` is a mutable module-level var in adapter.py
- `_get_available_backends()` checks env vars + `shutil.which()` for CLI backends
- Switching replaces the global `_bridge` instance via `create_backend()`

## Docker

- `start.sh` — Claude Code backend Docker setup
- `start-codex.sh` — Codex backend Docker setup (auto-detects Node.js, arch, binary path)
- `docker-compose.codex.yml` uses `${ARCH:-x86_64-unknown-linux-musl}` from `.env`

**Total: 91 (WebUI) + 47 (Interferometry) + 6 (Backend Toggle) tests**
