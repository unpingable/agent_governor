# WebUI Guide

The WebUI provides a chat interface for working with AI under governor constraints. It serves a self-contained chat + governor panel at a single URL — no external frontend needed.

---

## Quick Start

### Standard Setup (API Credits)

```bash
cd agent_gov
docker-compose up -d
```

Open **http://localhost:8001**

This uses the Anthropic API directly (charges apply).

### With Claude Max Subscription

```bash
docker-compose -f docker-compose.yml -f docker-compose.claude-code.yml up -d
```

Open **http://localhost:8001**

Routes chat through Claude Code CLI, using your Max subscription instead of API credits.

**Requirements:**
- Claude Code CLI installed (`claude` command available)
- Authenticated with `claude login`

### With Ollama (Local LLM)

```bash
docker-compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```

Open **http://localhost:8001**

Uses local Ollama instance. No API charges, but requires local GPU/compute.

**Requirements:**
- Ollama running (`ollama serve`)
- Model pulled (`ollama pull llama3` or similar)

### Without Docker

```bash
pip install -e .
BACKEND_TYPE=ollama GOVERNOR_MODE=fiction uvicorn webui.adapter:app --port 8001
```

Open **http://localhost:8001**

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Browser — localhost:8001            │
│  ┌──────────────────────┬──────────────────────┐│
│  │     Chat Panel       │  Governor Sidebar    ││
│  │  Messages + Input    │  Status, Rules,      ││
│  │  Streaming SSE       │  Characters, etc.    ││
│  └──────────┬───────────┴──────────┬───────────┘│
└─────────────┼──────────────────────┼─────────────┘
              │                      │
              ▼                      ▼
┌─────────────────────────────────────────────────┐
│            Governor Adapter (:8001)             │
│  /v1/chat/completions  │  /governor/*           │
│  /v1/models            │  /governor/ui          │
│  /health               │  /api/info             │
└────────────┬────────────────────────────────────┘
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
┌────────┐┌────────┐┌────────┐
│Anthropic││ Ollama ││ Claude │
│  API   ││ Local  ││  Code  │
└────────┘└────────┘└────────┘
```

The adapter serves both the UI and the API:
- **GET /** — Combined chat + governor UI (single-page app)
- **POST /v1/chat/completions** — OpenAI-compatible chat (streaming supported)
- **GET /governor/*** — Governor state, fiction/code data, corrections
- **GET /governor/ui** — Standalone governor panel (backward compat)
- **GET /api/info** — JSON endpoint with API info

Governor integration adds:
- Mode-specific system prompts
- Continuity checking on responses
- Violation resolution flow
- Telemetry and audit logging

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_TYPE` | `ollama` | Backend: anthropic, ollama, claude-code |
| `GOVERNOR_MODE` | `general` | Active mode: fiction, code, nonfiction, general |
| `ANTHROPIC_API_KEY` | — | API key (for anthropic backend) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama URL (for ollama backend) |
| `CLAUDE_PATH` | `claude` | Path to claude CLI (for claude-code backend) |
| `GOVERNOR_CONTEXT_ID` | `default` | Active context ID |
| `GOVERNOR_CONTEXTS_DIR` | `~/.governor-contexts` | Base dir for contexts |
| `GOVERNOR_SHOW_OK_FOOTER` | `true` | Show "[Governor] OK" in chat when clean |

### Docker Compose Override

Create `docker-compose.override.yml` for custom settings:

```yaml
version: '3.8'
services:
  governor-adapter:
    environment:
      - GOVERNOR_MODE=fiction
      - BACKEND_TYPE=claude-code
```

---

## Modes

### Selecting a Mode

The mode determines what constraints are active. Set via environment variable.

```bash
GOVERNOR_MODE=fiction uvicorn webui.adapter:app --port 8001
```

### Mode Differences

| Mode | System Prompt Focus | Sidebar Panels |
|------|---------------------|----------------|
| Fiction | Story consistency, character voice, affect regime | Characters, World Rules, Forbidden |
| Code | Tech decisions, patterns | Decisions, Constraints |
| Nonfiction | Sources, positions, hedging | (status + corrections) |
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

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Combined chat + governor UI |
| `/v1/chat/completions` | POST | Chat completion (streaming supported) |
| `/v1/models` | GET | List available models |
| `/api/info` | GET | JSON API info |
| `/health` | GET | Health check |
| `/governor/status` | GET | Governor state |
| `/governor/now` | GET | Glanceable status |
| `/governor/why` | GET | Decision/violation feed |
| `/governor/history` | GET | Events by day |
| `/governor/corrections` | GET | Resolution history |
| `/governor/ui` | GET | Standalone governor panel |
| `/governor/fiction/characters` | GET/POST | Fiction characters |
| `/governor/fiction/world-rules` | GET/POST | Fiction world rules |
| `/governor/fiction/forbidden` | GET/POST | Fiction prohibitions |
| `/governor/code/decisions` | GET/POST | Code decisions |
| `/governor/code/constraints` | GET/POST | Code constraints |

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

- API keys should be in environment, not in code
- The adapter runs with governor enforcement — it can block output
- Exception logs contain partial responses (review before sharing)
- Multi-user setup isolates state but shares the same backend
