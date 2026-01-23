# Agent Governor Roadmap

## Planned Integrations

### VS Code Extension

**Status:** Not started

A VS Code extension that brings governor into the editor:

- **Sidebar panel** showing:
  - Active tasks with tree view
  - Current session status and timer
  - Recent decisions/facts
  - Blocking relationships

- **Status bar** with:
  - Active timer (click to stop)
  - Current task
  - Session duration

- **Commands** (Ctrl+Shift+P):
  - `Governor: Start Task`
  - `Governor: Complete Task`
  - `Governor: Start Timer`
  - `Governor: End Session with Handoff`
  - `Governor: Show Recommendations`

- **SCM integration**:
  - Pre-commit hook status
  - Proposal approval workflow

- **Decorations**:
  - Gutter icons for files with associated facts
  - Highlight files in scope of active task

**Implementation notes:**
- Use VS Code Extension API
- Communicate with governor CLI or expose a simple HTTP/JSON-RPC API
- Could share MCP server infrastructure

---

### Obsidian Plugin

**Status:** Not started

Sync governor state to an Obsidian vault for knowledge management:

- **Daily notes integration**:
  - Auto-append session handoffs to daily note
  - Task completions logged with timestamps

- **Decisions as notes**:
  - Each decision becomes a linked note
  - Superseded decisions show revision history
  - Tags from topics become Obsidian tags

- **Tasks as notes** (optional):
  - Kanban-compatible frontmatter
  - Links between parent/subtasks
  - Dataview-compatible metadata

- **Facts with backlinks**:
  - Facts link to the files they reference
  - Staleness visible in note

- **Graph view**:
  - Decisions → files they govern
  - Tasks → proposals that resolved them
  - Sessions → work accomplished

**Implementation notes:**
- Could be one-way sync (governor → Obsidian) via CLI export
- Or bidirectional with Obsidian plugin that watches vault
- Export format: YAML frontmatter + markdown body

---

## Other Future Features

### Claude Code Hooks
- Behavioral guardrails injected into AI sessions
- Auto-load context from last session
- Enforce governor approval before file writes

### Web Dashboard
- Browser-based UI for governor state
- Task board (kanban view)
- Timeline of decisions
- Audit log visualization

### GitHub Integration
- Sync issues bidirectionally
- Link proposals to PRs
- Auto-close tasks when PR merges

### Slack/Discord Bot
- Session handoff notifications
- Task assignment alerts
- Daily digest of decisions made

---

## Completed

- [x] Core governor (receipts, claims, FSM)
- [x] Multi-agent coordination
- [x] Fiction governor
- [x] Non-fiction governor (academic writing)
- [x] Task management system
- [x] Session handoffs
- [x] Time tracking
- [x] MCP server
- [x] Git hooks
