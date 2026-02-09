# AGENTS.md — Working in this repo

This file is a **travel guide**, not a law.
Enforcement lives in the governor (admissibility, receipts, waivers).

If anything here conflicts with the governor's current constraints or the user's
explicit instructions, the governor and user win.

> Instruction files shape behavior; the governor determines admissibility.

---

## Quick start

```bash
pip install -e .           # Install in dev mode
governor init              # Initialize .governor/ directory
python3 -m pytest tests/ -q   # Run tests (use python3 on this system)
```

## Tests

```bash
python3 -m pytest tests/ -q                    # All tests (~8000+)
python3 -m pytest tests/test_<module>.py -v    # Single module
python3 -m pytest tests/ -k "pattern"          # Pattern match
```

Always run tests before proposing commits. Never claim tests pass without running them.

---

## Safety and irreversibility

### Do not do these without explicit user confirmation + governor receipt trail
- Push to remote, create/close PRs or issues
- Write to non-local endpoints (prod/staging), change credentials
- Push tags or releases
- Modify CI/CD pipelines
- Delete or rewrite git history
- Bulk refactors across modules without a plan

### Preferred workflow
- Make changes in small, reviewable steps
- Run tests locally before proposing commits
- For any operation that affects external state, require explicit user confirmation

---

## Repository layout

```
src/governor/          Core governor logic (authority plane, ~60 modules)
src/fiction_governor/   Fiction mode (characters, canon, drift, guardrails)
src/nonfiction_governor/  Nonfiction mode (corpus, DOI, citations, CFI)
src/ops_governor/      Ops mode (runbooks, blast radius, preconditions)
tests/                 All tests (python3 -m pytest)
docs/                  User-facing documentation
specs/                 Architectural specs (canonical truth for design)
integration/           Contract tests (Docker-based, run via bash run.sh)
vscode-governor/       VS Code extension (TypeScript)
```

The WebUI is a separate repo: `~/git/gov-webui` (github.com/unpingable/governor_webui).

---

## Coding conventions

- Python 3.10+ (use `|` for union types, not `Union`)
- Dataclasses for all data objects
- Type hints everywhere
- Tests in `tests/test_<module>.py`
- No free-form string assertions — use typed claims (`ClaimType` enum)

---

## Governor boundary

The governor is the only authority. Everything else is convenience.

- **UI/clients are untrusted.** They may be compromised. They render state but cannot override it.
- **Core** is the only place that evaluates admissibility, applies constraints, executes commits, and produces receipts.
- **Instruction files** (this file, CLAUDE.md, .codex rules) are guidance for agents, not enforcement. An agent that ignores this file is rude; an agent that bypasses the governor is broken.
- **Waivers leave scars.** Overrides must be explicit, attributable, and durable.

### The litmus test

> Can a compromised UI or plugin cause an irreversible action without passing
> a deterministic core check and leaving a durable receipt?

If yes, that's a bug.

---

## When you're unsure

Ask for clarification rather than guessing, especially around:
- Mode switching (fiction/code/nonfiction/research/general)
- Evidence or verification levels
- Waiver or override boundaries
- Anything that changes irreversible state

---

## Agent-specific instruction files

| Agent | File | Role |
|-------|------|------|
| Claude Code | `CLAUDE.md` + `.claude/rules/` | Operational context, scoped rules |
| Codex | `AGENTS.md` (this file) | Operating context + defaults |
| Any future agent | `AGENTS.md` (this file) | Start here |

All of these are travel guides. The governor is the constitution.
