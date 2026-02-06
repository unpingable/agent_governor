# CLI Chat Specification

## Version 0.1 — Governed Conversational CLI With Backend Switching

```yaml
status: gap
implemented: false
depends_on:
  - chat_bridge.py         # ChatBackend protocol, 4 backends, create_backend()
  - interferometry.py      # run_parallel(), run_serial(), multi-backend
  - continuity.py          # AnchorRegistry, ContinuityChecker
  - check.py               # Unified check aggregation
  - SLIM_MODE_SPEC.md
  - CONSTRAINT_COMPILER_SPEC.md
blocking: CLI-native multi-model workflows
estimated_scope: small
```

### Companion to: SLIM_MODE_SPEC.md, CONSTRAINT_COMPILER_SPEC.md

---

## Executive Summary

The WebUI (`src/webui/adapter.py`) provides governed chat with runtime backend switching across four backends (Ollama, Anthropic, Claude Code, Codex). The CLI has no equivalent — `governor interferometry run` sends prompts to multiple backends for comparison, but there's no governed conversational mode.

This spec adds `governor chat` as a thin CLI layer over the existing `ChatBridge` and `GovernorHooks`, plus `governor backend` for backend management. The plumbing exists; this is surface area, not architecture.

**Design principle**: If you can do it in the WebUI, you should be able to do it in the terminal.

---

## 1. The Problem

### 1.1 What Works Today

| Capability | WebUI | CLI |
|-----------|-------|-----|
| Chat with single backend | Yes | No |
| Switch backends at runtime | Yes (`POST /v1/backends/switch`) | No |
| Governor hooks on responses | Yes (`GovernorHooks`) | No |
| Multi-backend interferometry | Yes (`/governor/interferometry/run`) | Yes (`governor interferometry run`) |
| Constraint projection in system prompt | Yes (via `GovernorHooks.augment_messages`) | No |

### 1.2 The Gap

A developer in a terminal (the most common environment for Claude Code / Codex users) cannot:
- Send a governed prompt to Ollama and get a response checked against anchors
- Switch between local and API models without restarting a WebUI
- Get a quick interferometry comparison without the full `interferometry run` ceremony
- Use the governor as a governed `curl` for LLM APIs

---

## 2. The Solution

### 2.1 Backend Management

```bash
# List available backends and their status
governor backend list
#   ollama        available (http://localhost:11434, 3 models)
#   anthropic     available (API key set, claude-sonnet-4-20250514)
#   claude-code   available (/usr/bin/claude)
#   codex         not found

# Switch active backend
governor backend switch ollama
governor backend switch anthropic --model claude-sonnet-4-20250514

# Show active backend
governor backend status
#   Active: ollama (llama3:latest)

# List models for active backend
governor backend models
```

Active backend persisted in `.governor/config.toml` (or existing config mechanism).

### 2.2 Governed Chat

```bash
# Single prompt, governed response
governor chat "Refactor the auth module to use JWT"
# → Response from active backend
# → Checked against anchors, decisions, active constraints
# → Violations shown inline

# With explicit backend
governor chat "Explain this function" --backend ollama --model llama3

# With scope (for constraint projection)
governor chat "Add error handling" --scope "src/auth/**"

# Pipe-friendly (stdin prompt, stdout response)
echo "What does this do?" | governor chat --stdin

# JSON output (for scripting)
governor chat "List the API endpoints" --format json
```

### 2.3 Quick Interferometry

```bash
# Compare two backends on a prompt (shorthand for interferometry run)
governor chat "Add input validation" --compare ollama:llama3,anthropic:claude-sonnet-4-20250514
# → Shows both responses side-by-side
# → Highlights shared claims, unique claims, conflicts
# → Risk markers if code mode

# Even shorter
governor compare "Add input validation" --backends ollama:llama3,anthropic:claude-sonnet-4-20250514
# (alias for existing interferometry compare, already implemented)
```

### 2.4 Governor Hooks in CLI Chat

Every `governor chat` response passes through `GovernorHooks`:

1. **Pre-request**: System prompt enriched with mode-specific constraints (decisions, anchors, active profile). In slim mode, uses `slim status --json` as lightweight constraint projection.
2. **Post-response**: `ContinuityChecker` runs against active anchors. Violations reported inline.
3. **Blocking**: If `reject`-severity anchor is violated, response is flagged (not suppressed — the user asked for it, but the violation is loud).

---

## 3. Architecture

```
governor chat "prompt"
    │
    ├─ read active backend from .governor/config.toml
    ├─ create_backend() (existing factory in chat_bridge.py)
    ├─ GovernorHooks.augment_messages() (existing, adds constraints)
    │
    ├─ backend.chat(messages, model) (existing ChatBackend protocol)
    │
    ├─ GovernorHooks.check_response_blocking() (existing, anchor check)
    ├─ format + print response
    └─ print violations (if any)
```

No new subsystems. This is a CLI entry point that calls existing functions.

### 3.1 What's New vs Reused

| Component | Status |
|-----------|--------|
| `ChatBackend` protocol | Exists (`chat_bridge.py`) |
| 4 backend implementations | Exist (`chat_bridge.py`) |
| `create_backend()` factory | Exists (`chat_bridge.py`) |
| `GovernorHooks` | Exists (`chat_bridge.py`) |
| `ContinuityChecker` | Exists (`continuity.py`) |
| Backend state persistence | **New** (small: read/write `.governor/config.toml`) |
| `governor backend` CLI commands | **New** (small: 4 subcommands) |
| `governor chat` CLI command | **New** (small: prompt → backend → hooks → print) |

---

## 4. Design Constraints

1. **No daemon.** `governor chat` is a single invocation, not a long-running process. Stateless between calls (backend choice persisted in config, conversation history is not).
2. **Pipe-friendly.** Prompt via stdin, response via stdout, violations via stderr. Composable with Unix tools.
3. **No conversation memory.** Each `governor chat` is a single turn. Multi-turn conversation is the WebUI's job (or Claude Code's job). The CLI is for one-shot governed queries.
4. **Async under the hood.** Backends use async; CLI wraps in `asyncio.run()`. No new concurrency model.

---

## 5. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `SLIM_MODE_SPEC.md` | `governor chat` in slim mode uses lightweight constraint projection |
| `CONSTRAINT_COMPILER_SPEC.md` | Full constraint compilation optionally injected via `--scope` |
| `DETECTOR_INTEGRATION_SPEC.md` | Detector signals attach to chat responses as supplementary evidence |

---

## 6. Open Questions

1. **Conversation history.** Should `governor chat` support `--continue` for multi-turn? Could store history in `.governor/chat_history.jsonl`. Adds complexity; may not be worth it if Claude Code already provides conversation.

2. **Streaming.** Backends support `stream()`. Should `governor chat` stream tokens to stdout? Nice UX, but governor hooks can only check the complete response. Candidate: stream to terminal, run hooks after completion, print violations at the end.

3. **Cost tracking.** API backends (Anthropic) cost money. Should `governor chat` show token counts and estimated cost? Telemetry already tracks this; could surface it with `--verbose`.
