# Agent Governor Documentation

## Getting Started

1. **Install**: `pip install -e .`
2. **Initialize**: `governor init`
3. **Choose your mode**: See the mode guides below

---

## Mode Guides

Pick the guide that matches your use case:

| Mode | Guide | Use Case |
|------|-------|----------|
| **Fiction** | [modes/fiction.md](modes/fiction.md) | Novel writing, worldbuilding, character consistency |
| **Code** | [modes/code.md](modes/code.md) | Software development, tech stack decisions, patterns |
| **Nonfiction** | [modes/nonfiction.md](modes/nonfiction.md) | Academic writing, research, citation management |
| **Ops** | [modes/ops.md](modes/ops.md) | SRE, runbooks, change management, blast radius |

### Ancillary Modes & Layers

These work alongside the main modes to provide additional control:

| Layer | Description |
|-------|-------------|
| **Puppet Mode** | Pin AI to a specific persona/voice |
| **Strict Mode** | Fail-closed governance preset |
| **Research Mode** | Non-convergent epistemic exploration |
| **Docket & Adjudicator** | Time-bounded verification, rulings, precedent |

See [modes/ancillary.md](modes/ancillary.md) for details.

---

## Interfaces

How you interact with the governor:

| Interface | Guide | Best For |
|-----------|-------|----------|
| **WebUI** | [interfaces/webui.md](interfaces/webui.md) | Chat-based interaction, visual feedback |
| **VS Code** | [interfaces/vscode.md](interfaces/vscode.md) | Real-time checking while coding |
| **CLI** | [interfaces/cli.md](interfaces/cli.md) | Scripting, automation, full control |

---

## Foundations

Core design principles and how they map to real-world accountability:

- [ADMISSIBILITY.md](ADMISSIBILITY.md) - Admissibility vs correctness: why receipts prove process, not outcomes
- [COMPLIANCE.md](COMPLIANCE.md) - Fiduciary law mapping (ERISA, SEC, process-based prudence)

## Architecture

For understanding the system internals:

- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) - High-level map of components

---

## Quick Reference

### Code Autopilot (Intent-Based Governance)

Declare what you're doing, the system configures enforcement:

```bash
# Quick profile switch
governor code --profile hotfix --scope "src/auth/**" --timebox 90 --because "fixing login"

# Check current state
governor code --status

# Full commands
governor intent show       # See resolved intent with provenance
governor intent set ...    # Set session intent
governor intent clear      # Clear session intent
```

**Profiles:** `greenfield` (warn only), `established` (default), `production` (strict), `hotfix` (narrow scope), `refactor` (soft anchors)

### The Three Moves

When the governor blocks a violation, you have three choices:

| In Chat | CLI Equivalent | Action |
|---------|----------------|--------|
| `1` or `fix` | `governor lite fix` | Regenerate to comply with constraint |
| `2` or `revise` | `governor lite revise` | Update the constraint to match new reality |
| `3` or `proceed` | `governor lite proceed` | Log as intentional exception, continue |

> **Note**: In chat/interactive mode, you can also prefix with "governor" (e.g., `governor fix`).

### Core CLI Commands

```bash
# Initialize
governor init

# Autopilot (quick profile switch)
governor code --profile hotfix --scope "src/**" --timebox 60 --because "reason"
governor code --status
governor intent show
governor intent set --profile <name> ...
governor intent clear

# Anchors (constraints)
governor continuity anchor add --id <id> --type <type> --description <desc> --forbidden-patterns <patterns> --severity reject [--class invariant]
governor continuity anchor list
governor continuity anchor remove <id>

# Overrides (for invariant anchors)
governor override create --anchor <id> --scope "..." --expires 2h --because "reason"
governor override list
governor override revoke <id> --because "done"

# Check content
governor continuity check <text>
governor check <file> --interactive --mode <mode>

# Resolve violations
governor lite pending
governor lite fix
governor lite revise
governor lite proceed
governor lite exceptions

# Status
governor status
governor continuity status
```

### WebUI

```bash
# Standard (API credits)
docker-compose up -d

# With Claude Max subscription
docker-compose -f docker-compose.yml -f docker-compose.claude-code.yml up -d

# With Ollama (local)
docker-compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```

Open **http://localhost:8001** (fiction) or **http://localhost:8002** (code)

### VS Code

1. Install the extension from `vscode-governor/`
2. Open a project with `.governor/` initialized
3. Use `Ctrl+Shift+G` to check the current file
4. Use `Ctrl+Shift+Alt+G` to toggle real-time checking

---

## Document Index

### Modes
- [modes/fiction.md](modes/fiction.md) - Fiction Mode for writers
- [modes/code.md](modes/code.md) - Code Mode for developers
- [modes/nonfiction.md](modes/nonfiction.md) - Nonfiction Mode for researchers
- [modes/ops.md](modes/ops.md) - Ops Mode for SREs
- [modes/ancillary.md](modes/ancillary.md) - Puppet, Strict, Research, Docket

### Interfaces
- [interfaces/webui.md](interfaces/webui.md) - WebUI setup and usage
- [interfaces/vscode.md](interfaces/vscode.md) - VS Code extension
- [interfaces/cli.md](interfaces/cli.md) - Complete CLI reference

### Foundations
- [ADMISSIBILITY.md](ADMISSIBILITY.md) - Admissibility vs correctness
- [COMPLIANCE.md](COMPLIANCE.md) - Fiduciary and regulatory mapping

### Architecture
- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) - System architecture

### Architecture Decision Records
- [adr/0001-proposal-commit-split.md](adr/0001-proposal-commit-split.md) - Why proposals and commits are separate stages
- [adr/0002-gate-not-memory.md](adr/0002-gate-not-memory.md) - Why the governor blocks, not logs
- [adr/0003-domain-specific-modes.md](adr/0003-domain-specific-modes.md) - Why fiction/code/nonfiction are separate modes
- [adr/0004-sqlite-over-postgres.md](adr/0004-sqlite-over-postgres.md) - Why SQLite with WAL, not Postgres
- [adr/0005-self-contained-webui.md](adr/0005-self-contained-webui.md) - Why no build step, no npm, no framework

---

## The Philosophy

**Language is a proposal, not an authority (NLAI).**

The AI proposes. You approve. The governor gates.

Your project. Your rules. AI follows, or it doesn't write.
