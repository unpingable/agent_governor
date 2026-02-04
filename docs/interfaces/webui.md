# WebUI Guide

The WebUI provides a chat interface for working with AI under governor constraints. It's built on Open WebUI with governor integration.

---

## Quick Start

### Standard Setup (API Credits)

```bash
cd agent_gov
docker-compose up -d
```

Open **http://localhost:3001**

This uses the Anthropic API directly (charges apply).

### With Claude Max Subscription

```bash
docker-compose -f docker-compose.yml -f docker-compose.claude-code.yml up -d
```

Routes chat through Claude Code CLI, using your Max subscription instead of API credits.

**Requirements:**
- Claude Code CLI installed (`claude` command available)
- Authenticated with `claude login`

### With Ollama (Local LLM)

```bash
docker-compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```

Uses local Ollama instance. No API charges, but requires local GPU/compute.

**Requirements:**
- Ollama running (`ollama serve`)
- Model pulled (`ollama pull llama3` or similar)

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Browser      │────▶│   Open WebUI    │────▶│  Governor       │
│  localhost:3001 │     │   (frontend)    │     │  Adapter        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────┐
                        │                                ▼        │
                        │  ┌──────────┐  ┌──────────┐  ┌────────┐│
                        │  │ Anthropic│  │  Ollama  │  │ Claude ││
                        │  │   API    │  │  Local   │  │  Code  ││
                        │  └──────────┘  └──────────┘  └────────┘│
                        │              BACKENDS                   │
                        └─────────────────────────────────────────┘
```

The adapter sits between Open WebUI and the LLM backends, adding:
- Mode-specific system prompts
- Continuity checking on responses
- Violation resolution flow
- Telemetry and audit logging

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_MODE` | `code` | Active mode: fiction, code, nonfiction, ops |
| `GOVERNOR_BACKEND` | `anthropic` | Backend: anthropic, ollama, claude-code |
| `ANTHROPIC_API_KEY` | — | API key (for anthropic backend) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama URL (for ollama backend) |
| `CLAUDE_PATH` | `claude` | Path to claude CLI (for claude-code backend) |
| `GOVERNOR_DIR` | `.governor` | Path to governor state directory |

### Docker Compose Override

Create `docker-compose.override.yml` for custom settings:

```yaml
version: '3.8'
services:
  governor-adapter:
    environment:
      - GOVERNOR_MODE=fiction
      - GOVERNOR_BACKEND=claude-code
```

---

## Modes

### Selecting a Mode

The mode determines what constraints are active. Set via environment variable or in-chat command.

**Environment:**
```bash
GOVERNOR_MODE=fiction docker-compose up -d
```

**In-chat:**
```
/mode fiction
```

### Mode Differences

| Mode | System Prompt Focus | Anchor Types |
|------|---------------------|--------------|
| Fiction | Story consistency, character voice | canon, prohibition, persona |
| Code | Tech decisions, patterns | canon, prohibition, style |
| Nonfiction | Sources, positions, hedging | canon, definition, style |
| Ops | Runbooks, time windows | All (via ops-gov) |

### Mode-Specific UI Panels

The WebUI shows different panels based on the active mode:

**Fiction Mode:**
- Characters — Add/view characters with descriptions
- World Rules — "In this world..." constraints
- Forbidden — Things that shouldn't happen

**Code Mode:**
- Decisions — "We use X for Y" architectural choices
- Constraints — "Never do X" prohibitions

---

## Violation Resolution

When the AI generates content that violates a constraint, you'll see a friendly prompt:

```
⚠️ This conflicts with something you said earlier

You said: "Elena has green eyes, not blue"
But I wrote: "Elena's blue eyes glistened..."

How would you like to handle this?

1. 🔄 Fix — I'll rewrite to match your rules
2. ✎ Change — Update what I should remember
3. ✓ Allow — Let this one through (I'll log it)
```

### Resolution Commands

| Input | Action |
|-------|--------|
| `1` or `fix` | AI regenerates compliant response |
| `2` or `change` | Updates the constraint to permit the output |
| `3` or `allow` | Logs exception, shows original output |

You can also type the words: `fix`, `change`, `allow`

### Corrections Log

The UI shows a "Corrections" panel tracking all resolutions:
- 🔄 Fixed — rewrote to comply
- ✎ Changed — updated the rule
- ✓ Allowed — logged exception

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
      - GOVERNOR_USER=erin
    ports:
      - "3001:3000"

  james-studio:
    extends:
      file: docker-compose.yml
      service: governor-adapter
    environment:
      - GOVERNOR_MODE=code
      - GOVERNOR_USER=james
    ports:
      - "3002:3000"
```

---

## Backend Details

### Anthropic API

Direct API access to Claude models.

**Pros:**
- Full model access
- Streaming support
- All features available

**Cons:**
- API charges apply
- Requires API key management

**Config:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GOVERNOR_BACKEND=anthropic
```

### Claude Code

Routes through Claude Code CLI, using your Max subscription.

**Pros:**
- Uses Max subscription (no per-message charges)
- Same Claude models
- No API key in environment

**Cons:**
- Requires Claude Code installed and authenticated
- Slightly higher latency (subprocess spawn)

**Config:**
```bash
export GOVERNOR_BACKEND=claude-code
export CLAUDE_PATH=/path/to/claude  # if not in PATH
```

### Ollama

Local LLM inference via Ollama.

**Pros:**
- No API charges
- Data stays local
- Works offline

**Cons:**
- Requires GPU/compute resources
- Model quality varies
- Larger models need significant RAM/VRAM

**Config:**
```bash
export GOVERNOR_BACKEND=ollama
export OLLAMA_HOST=http://localhost:11434
```

**Model selection** in chat:
```
/model llama3
/model codellama
/model mixtral
```

---

## Troubleshooting

### "Connection refused"

WebUI can't reach the adapter.

```bash
# Check adapter is running
docker-compose ps

# Check logs
docker-compose logs governor-adapter
```

### "API key not found"

Anthropic backend needs API key.

```bash
# Set in environment
export ANTHROPIC_API_KEY=sk-ant-...

# Or in docker-compose.override.yml
```

### "Claude not found"

Claude-code backend can't find CLI.

```bash
# Check claude is installed
which claude

# Set explicit path
export CLAUDE_PATH=/home/user/.local/bin/claude
```

### "Violation loop"

Getting the same violation repeatedly after "fix".

This means the AI can't satisfy the constraint. Options:
1. `revise` — relax the constraint
2. `proceed` — accept the exception
3. Check if the anchor is too strict

### "No anchors loaded"

Mode-specific anchors aren't loading.

```bash
# Check anchor status
governor continuity status

# List anchors
governor continuity anchor list

# Check mode
echo $GOVERNOR_MODE
```

---

## Advanced Usage

### Custom System Prompts

The adapter injects mode-specific system prompts. Customize in:

```
src/governor/chat_bridge.py → GovernorHooks._system_prompt_for_mode()
```

### Telemetry

Enable structured logging:

```bash
governor telemetry enable --logging
```

Logs go to `.governor/telemetry/`.

### API Endpoints

The adapter exposes OpenAI-compatible endpoints:

| Endpoint | Description |
|----------|-------------|
| `POST /v1/chat/completions` | Chat completion (streaming supported) |
| `GET /v1/models` | List available models |
| `GET /governor/status` | Governor state |
| `GET /governor/anchors` | List anchors |
| `POST /governor/resolve` | Resolve pending violation |

---

## Security Notes

- API keys should be in environment, not in code
- The adapter runs with governor enforcement — it can block output
- Exception logs contain partial responses (review before sharing)
- Multi-user setup isolates state but shares the same backend

---

*"Chat with guardrails. Your constraints, enforced."*
