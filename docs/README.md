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

## Architecture

For understanding the system internals:

- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) - High-level map of components

---

## Quick Reference

### The Three Moves

When the governor blocks a violation, you have three choices:

| In Chat | CLI Equivalent | Action |
|---------|----------------|--------|
| `1` or `fix` | `governor lite fix` | Regenerate to comply with constraint |
| `2` or `revise` | `governor lite revise` | Update the constraint to match new reality |
| `3` or `proceed` | `governor lite proceed` | Log as intentional exception, continue |

> **Note**: In chat/interactive mode, you can also prefix with "maude" (e.g., `maude fix`).

### Core CLI Commands

```bash
# Initialize
governor init

# Anchors (constraints)
governor continuity anchor add --id <id> --type <type> --description <desc> --forbidden-patterns <patterns> --severity reject
governor continuity anchor list
governor continuity anchor remove <id>

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

Open **http://localhost:3001**

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

### Architecture
- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) - System architecture

---

## The Philosophy

**Language is a proposal, not an authority (NLAI).**

The AI proposes. You approve. The governor gates.

Your project. Your rules. AI follows, or it doesn't write.
