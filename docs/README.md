# Agent Governor Documentation

## Getting Started

1. **Install**: `pip install -e .`
2. **Initialize**: `governor init`
3. **Choose your mode**: See the mode guides below

## Mode Guides

Pick the guide that matches your use case:

| Mode | Guide | Use Case |
|------|-------|----------|
| **Fiction** | [modes/fiction.md](modes/fiction.md) | Novel writing, worldbuilding, character consistency |
| **Code** | [modes/code.md](modes/code.md) | Software development, tech stack decisions, patterns |
| **Nonfiction** | [modes/nonfiction.md](modes/nonfiction.md) | Academic writing, research, citation management |

## Architecture

For understanding the system internals:

- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) - High-level map of components

## Quick Reference

### The Three Moves

When the governor blocks a violation, you have three choices:

| Command | Action |
|---------|--------|
| `maude fix` (or `1`) | Regenerate to comply with constraint |
| `maude revise` (or `2`) | Update the constraint to match new reality |
| `maude proceed` (or `3`) | Log as intentional exception, continue |

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

---

## The Philosophy

**Language is a proposal, not an authority (NLAI).**

The AI proposes. You approve. The governor gates.

Your project. Your rules. AI follows, or it doesn't write.
