---
paths:
  - "src/governor/chat_bridge.py"
  - "src/governor/context_manager.py"
  - "src/governor/interferometry.py"
  - "src/governor/intent_compiler.py"
  - "tests/test_chat_bridge*"
  - "tests/test_interferometry*"
  - "tests/test_context_manager*"
  - "tests/test_intent_compiler*"
---
# WebUI & Chat Infrastructure

> **NOTE:** WebUI adapter (`adapter.py`, `summaries.py`, static HTML) has been
> extracted to `~/git/gov-webui` (github.com/unpingable/governor_webui).
> This file covers the governor-side modules that webui depends on.

## Trust Boundary

**The WebUI is an untrusted cockpit.** It renders governor state but cannot override it.

Litmus test: *Can a compromised UI or plugin cause an irreversible action without passing a deterministic core check and leaving a durable receipt?* If yes, that's a bug.

Invariants:
- UI cannot sign receipts, mint keys, broaden scope, or execute commits without core challenge
- All governance decisions happen in `agent-governor` core, never in `gov-webui`
- Intent forms in `TEMPLATE_ONLY` modes (code, general) cannot propose custom schemas — the core rejects them
- Every compilation emits a gate receipt (`gate="intent_compiler"`) or logs `receipt_suppressed`

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

- **adapter.py** — FastAPI adapter with OpenAI-compatible API, governor endpoints, backend switching, intent compiler API, v2 dashboard
- **static/index.html** — Combined chat + governor sidebar UI with backend dropdown, intent form modal, violation modal, compare input
- **chat_bridge.py** — ChatBridge, OllamaBackend, AnthropicBackend, ClaudeCodeBackend, CodexBackend, GovernorHooks, create_backend factory
- **context_manager.py** — GovernorContext, GovernorContextManager, isolated per-user/project contexts
- **interferometry.py** — Multi-model claim comparison: parallel + serial ("yes, and") modes, claim alignment (shared/unique/conflicting), Jaccard fingerprinting, ledger promotion, JSON persistence
- **intent_compiler.py** — Structured hypothesis-collapse: templates → forms → deterministic compilation → receipts

## Intent Compiler

Form structure freedom is proportional to blast radius:

| Mode | Policy | Custom forms? |
|------|--------|---------------|
| code, general | `TEMPLATE_ONLY` | No — only built-in templates |
| nonfiction, research | `VALIDATED_CUSTOM` | Yes, but schema-validated |
| fiction | `CUSTOM_OK` | Yes, any valid schema |

3 built-in templates: `session_start`, `task_scope`, `verification_config`

API surface (in gov-webui adapter):
- `GET /v2/intent/templates` — list templates
- `GET /v2/intent/schema/{name}` — build schema for current mode
- `POST /v2/intent/validate` — validate response against schema
- `POST /v2/intent/compile` — compile response → intent + constraints + receipt
- `GET /v2/intent/policy` — current policy for active mode

## Backend Toggle

- `_current_backend_type` is a mutable module-level var in adapter.py
- `_get_available_backends()` checks env vars + `shutil.which()` for CLI backends
- Switching replaces the global `_bridge` instance via `create_backend()`

## Agent Instruction Export (future)

Governor is source of truth; UI exports into agent-specific affordances.

- Core can expose a "recommended policy snippet" (static text / template variables)
- UI can apply it to `AGENTS.md`, `CLAUDE.md`, Codex rules as an export step
- This is convenience tooling, not truth — the governor remains the authority
- See `AGENTS.md` in repo root for the agent-neutral travel guide pattern

## Docker

- `start.sh` — Claude Code backend Docker setup
- `start-codex.sh` — Codex backend Docker setup (auto-detects Node.js, arch, binary path)

**Total: 91 (WebUI) + 47 (Interferometry) + 6 (Backend Toggle) + 131 (Intent Compiler) tests**
