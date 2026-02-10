# WebUI Guide

The WebUI provides a chat interface for working with AI under governor constraints. It serves a self-contained chat + governor panel at a single URL — no external frontend needed.

The WebUI lives in a separate repo: [gov-webui](https://github.com/unpingable/governor_webui). All governance logic stays in `agent-governor`; the WebUI is presentation only.

**Key invariant**: The WebUI is an untrusted cockpit. It cannot sign receipts, mint keys, broaden scope, or execute commits without core challenge.

---

## Quick Start

### Install

```bash
cd ~/git/gov-webui
pip install -e .
```

### Run

```bash
governor-webui                    # http://127.0.0.1:8000

# With environment overrides
BACKEND_TYPE=ollama GOVERNOR_MODE=fiction governor-webui
BACKEND_TYPE=anthropic ANTHROPIC_API_KEY=sk-ant-... governor-webui
BACKEND_TYPE=claude-code governor-webui
BACKEND_TYPE=codex governor-webui
```

### Docker

See `gov-webui/start.sh` (Claude Code backend) or `gov-webui/start-codex.sh` (Codex backend). These auto-detect CLIs and architecture.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Browser — localhost:8000            │
│  ┌──────────────────────┬──────────────────────┐│
│  │     Chat Panel       │  Governor Sidebar    ││
│  │  Messages + Input    │  Status, Rules,      ││
│  │  Intent Form (⚙)    │  Characters, etc.    ││
│  │  Streaming SSE       │  Compare, Dashboard  ││
│  └──────────┬───────────┴──────────┬───────────┘│
└─────────────┼──────────────────────┼─────────────┘
              │                      │
              ▼                      ▼
┌─────────────────────────────────────────────────┐
│       gov-webui Adapter (:8000)                 │
│  /v1/chat/completions  │  /governor/*           │
│  /v1/models            │  /v2/intent/*          │
│  /v2/runs/*            │  /v2/dashboard/*       │
│  /health               │  /api/info             │
└────────────┬────────────────────────────────────┘
             │
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
┌────────┐┌────────┐┌────────┐┌────────┐
│Anthropic││ Ollama ││ Claude ││ Codex  │
│  API   ││ Local  ││  Code  ││  CLI   │
└────────┘└────────┘└────────┘└────────┘
```

The adapter serves both the UI and the API:
- **GET /** — Combined chat + governor UI (single-page app)
- **GET /dashboard** — V2 governance dashboard
- **POST /v1/chat/completions** — OpenAI-compatible chat (streaming supported)
- **GET /governor/*** — Governor state, fiction/code/research data, corrections
- **GET /v2/intent/*** — Intent compiler (templates, schema, compile, policy)
- **GET /v2/runs/*** — Run-centric dashboard API
- **GET /api/info** — JSON endpoint with API info and all endpoint paths

Governor integration adds:
- Mode-specific system prompts (fiction bible, code constraints, etc.)
- Continuity checking on responses
- Violation resolution flow (fix/revise/proceed)
- Intent compilation with gate receipts
- Telemetry and audit logging

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_TYPE` | `ollama` | Backend: `anthropic`, `ollama`, `claude-code`, `codex` |
| `GOVERNOR_MODE` | `general` | Active mode: `fiction`, `code`, `nonfiction`, `research`, `general` |
| `ANTHROPIC_API_KEY` | — | API key (for anthropic backend) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama URL (for ollama backend) |
| `CLAUDE_PATH` | `claude` | Path to claude CLI (for claude-code backend) |
| `CODEX_PATH` | `codex` | Path to codex CLI (for codex backend) |
| `GOVERNOR_CONTEXT_ID` | `default` | Active context ID |
| `GOVERNOR_CONTEXTS_DIR` | `~/.governor-contexts` | Base dir for contexts |
| `GOVERNOR_AUTH_TOKEN` | — | Bearer token for mutating endpoints (empty = no auth) |
| `GOVERNOR_BIND_HOST` | `127.0.0.1` | Bind host (set to `0.0.0.0` for network access) |
| `GOVERNOR_SHOW_OK_FOOTER` | `true` | Show "[Governor] OK" in chat when clean |

---

## Modes

### Selecting a Mode

The mode determines what constraints are active. Set via environment variable.

```bash
GOVERNOR_MODE=fiction governor-webui
```

### Mode Differences

| Mode | System Prompt Focus | Sidebar Panels |
|------|---------------------|----------------|
| Fiction | Story consistency, character voice, affect regime | Characters, World Rules, Forbidden |
| Code | Tech decisions, patterns, interferometry | Decisions, Constraints, Compare |
| Nonfiction | Sources, positions, hedging | (status + corrections) |
| Research | Non-convergent exploration, hypothesis tracking | Claims, Assumptions, Uncertainties, Links |
| General | No mode-specific prompts | (status + corrections) |

### Mode-Specific UI Panels

The sidebar shows different panels based on the active mode:

**Fiction Mode:**
- Characters — Add/view characters with descriptions and prohibitions
- World Rules — "In this world..." constraints
- Forbidden — Things that shouldn't happen

**Code Mode:**
- Decisions — "We use X for Y" architectural choices
- Constraints — "Never do X" prohibitions

---

## Violation Resolution

When the AI generates content that violates a constraint, you'll see a prompt in the chat:

```
[Governor] Blocked — 1 violation(s) detected.

  - test_reject_anchor: Cannot mention secret password

How would you like to handle this?

1. fix — Rewrite to comply with the constraint
2. revise — Update the constraint to permit this
3. proceed — Allow this once and log an exception
```

### Resolution Commands

| Input | Action |
|-------|--------|
| `1` or `fix` | AI regenerates compliant response |
| `2` or `revise` | Updates the constraint to permit the output |
| `3` or `proceed` | Logs exception, shows original output |

### Corrections Log

The sidebar shows a "Corrections" panel tracking all resolutions.

### Blocking Behavior

While a violation is pending:
- Normal messages are blocked
- Only resolution commands are accepted
- This ensures you explicitly handle every violation

---

## Intent Compiler

The intent form (gear icon next to send) provides structured session configuration. Instead of free-form prompts, the model's decision space is externalized as a form with finite options, then deterministically compiled into constraints.

### How It Works

1. Click the gear icon (or call `GET /v2/intent/schema/{template}`)
2. Select a template: `session_start`, `task_scope`, or `verification_config`
3. Fill in the form — options show model confidence as bars
4. Click Compile — the response is deterministically converted to profile + scope + constraints
5. A gate receipt is emitted with the compilation result

### Mode-Gated Form Policy

Form structure freedom is proportional to blast radius:

| Mode | Policy | Meaning |
|------|--------|---------|
| Code, General | `TEMPLATE_ONLY` | Only built-in templates allowed |
| Nonfiction, Research | `VALIDATED_CUSTOM` | Model can propose forms, schema-validated |
| Fiction | `CUSTOM_OK` | Any valid form accepted |

### API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v2/intent/templates` | GET | List available templates |
| `/v2/intent/schema/{name}` | GET | Build form schema for current mode |
| `/v2/intent/validate` | POST | Validate response against schema |
| `/v2/intent/compile` | POST | Compile response into intent + constraints |
| `/v2/intent/policy` | GET | Current form policy for active mode |

### Types

Core types live in `governor.intent_compiler`:
- `IntentFormSchema` — content-addressed form definition
- `IntentFormResponse` — user's filled-out values
- `IntentCompilationResult` — profile, scope, deny, timebox, constraint block, receipt hash
- `WidgetType` — 7 widget types (select_one, select_many, slider, text_short, text_long, conditional, confirmation)

---

## Multi-User Setup

The WebUI supports isolated contexts per user/project.

### Per-User Contexts

Each user gets their own:
- Governor state directory
- Anchors and violations
- Session history
- Exception log

### Docker Setup for Teams

```yaml
# docker-compose.team.yml
version: '3.8'
services:
  erin-studio:
    extends:
      file: docker-compose.yml
      service: governor-adapter
    environment:
      - GOVERNOR_MODE=fiction
      - GOVERNOR_CONTEXT_ID=erin
    ports:
      - "8001:8000"

  james-studio:
    extends:
      file: docker-compose.yml
      service: governor-adapter
    environment:
      - GOVERNOR_MODE=code
      - GOVERNOR_CONTEXT_ID=james
    ports:
      - "8002:8000"
```

---

## Backend Details

### Anthropic API

Direct API access to Claude models.

**Pros:** Full model access, streaming support, all features
**Cons:** API charges apply, requires API key

```bash
export BACKEND_TYPE=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

### Claude Code

Routes through Claude Code CLI, using your Max subscription.

**Pros:** Uses Max subscription (no per-message charges), no API key in environment
**Cons:** Requires Claude Code installed and authenticated, slightly higher latency

```bash
export BACKEND_TYPE=claude-code
export CLAUDE_PATH=/path/to/claude  # if not in PATH
```

### Ollama

Local LLM inference via Ollama.

**Pros:** No API charges, data stays local, works offline
**Cons:** Requires GPU/compute resources, model quality varies

```bash
export BACKEND_TYPE=ollama
export OLLAMA_HOST=http://localhost:11434
```

### Codex

Routes through OpenAI Codex CLI, using your ChatGPT subscription.

**Pros:** Uses ChatGPT subscription, no per-message charges
**Cons:** Requires Codex CLI installed, Node.js required

```bash
export BACKEND_TYPE=codex
export CODEX_PATH=/path/to/codex  # if not in PATH
```

---

## API Endpoints

Mutating endpoints (POST) require `Authorization: Bearer <token>` when `GOVERNOR_AUTH_TOKEN` is set.

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/` | GET | Combined chat + governor UI | No |
| `/dashboard` | GET | V2 governance dashboard | No |
| `/health` | GET | Health check | No |
| `/api/info` | GET | JSON API info with all endpoint paths | No |
| `/v1/models` | GET | List available models | No |
| `/v1/chat/completions` | POST | Chat completion (streaming supported) | Yes |
| `/v1/backends` | GET | List available backends | No |
| `/v1/backends/switch` | POST | Switch backend at runtime | Yes |
| `/sessions/` | GET/POST | Session CRUD | POST: Yes |
| `/sessions/{id}` | GET/PUT/DELETE | Session by ID | PUT/DELETE: Yes |
| `/sessions/{id}/messages` | POST | Append message to session | Yes |
| `/governor/status` | GET | Governor state | No |
| `/governor/now` | GET | Glanceable status | No |
| `/governor/why` | GET | Decision/violation feed | No |
| `/governor/history` | GET | Events by day | No |
| `/governor/corrections` | GET | Resolution history | No |
| `/governor/fiction/characters` | GET/POST | Fiction characters | POST: Yes |
| `/governor/fiction/world-rules` | GET/POST | Fiction world rules | POST: Yes |
| `/governor/fiction/forbidden` | GET/POST | Fiction prohibitions | POST: Yes |
| `/governor/code/decisions` | GET/POST | Code decisions | POST: Yes |
| `/governor/code/constraints` | GET/POST | Code constraints | POST: Yes |
| `/governor/research/*` | GET/POST | Research claims, assumptions, etc. | POST: Yes |
| `/v2/intent/templates` | GET | Intent form templates | No |
| `/v2/intent/schema/{name}` | GET | Build intent form schema | No |
| `/v2/intent/validate` | POST | Validate intent form response | No |
| `/v2/intent/compile` | POST | Compile response (emits receipt) | No |
| `/v2/intent/policy` | GET | Current form policy | No |
| `/v2/runs/*` | GET/POST | Run-centric dashboard | POST: Yes |
| `/v2/dashboard/*` | GET | Dashboard summary and regime | No |
| `/v2/demos/*` | GET | Playwright demo scenarios | No |

---

## Troubleshooting

### "Connection refused"

Adapter isn't running.

```bash
docker-compose ps
docker-compose logs governor-adapter
```

### "API key not found"

Anthropic backend needs API key.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### "Claude not found"

Claude-code backend can't find CLI.

```bash
which claude
export CLAUDE_PATH=/home/user/.local/bin/claude
```

### "Violation loop"

Getting the same violation repeatedly after "fix".

Options:
1. `revise` — relax the constraint
2. `proceed` — accept the exception
3. Check if the anchor is too strict

### "No anchors loaded"

Mode-specific anchors aren't loading.

```bash
governor continuity status
governor continuity anchor list
echo $GOVERNOR_MODE
```

---

## Security Notes

- **The WebUI is an untrusted cockpit.** It renders governor state but cannot override it. All governance decisions happen in the core.
- API keys should be in environment variables, not in code
- Set `GOVERNOR_AUTH_TOKEN` for mutating endpoints in shared/network deployments
- Set `GOVERNOR_BIND_HOST=127.0.0.1` (the default) to prevent network exposure
- Exception logs contain partial responses (review before sharing)
- Multi-user setup isolates governor state but shares the same backend
- See [DEPLOYMENT_MODES.md](../DEPLOYMENT_MODES.md) for transport security and threat models
