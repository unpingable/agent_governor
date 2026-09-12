# AGENTS.md — Working in this repo

## Deprecated: Agent Governor classic (2026-09-08)

This repository (`unpingable/agent_governor`, commonly checked out as
`agent_gov`) is **deprecated**. NQ classic (`unpingable/nq`) is also deprecated.
Neither is a target for new integrations, features, provider execution paths,
or qualification intended to establish a new supported consumer.

- Use **Constellation AG** (`unpingable/constellation-ag`) for supported exact-work authorization
  and one-use authority, and **Constellation Docket** (`unpingable/constellation-docket`) for attempt,
  dispatch, and reconciliation custody. Discover their current supported
  interfaces and qualified revisions before implementing an integration.
- Keep evidence qualification and application validation with their supported
  owners. Do not assume classic receipts or APIs transfer unchanged, or that
  ag-ng/Docket replace every diagnostic capability supplied by classic.
- Retain classic only for explicitly identified transitional dependencies and
  rollback. Record the consumer, supplied capability, owner, and removal gate;
  distinguish source, build-image, and production removal.
- Do not add classic imports, pins, container installs, fixture-generation
  requirements, or automatic fallback. A renamed wrapper does not retire a
  classic dependency. Historical evidence may remain identified as historical.
- Inspection, migration, and retirement work may proceed within the user's
  scope. Repairs to a remaining classic runtime require explicit bounded
  transitional or rollback authorization; do not revive its architecture.
- Remove deployed classic dependencies only after replacement qualification.
  Deprecation alone does not authorize service shutdown, deletion, or migration.

This section governs how to use the legacy guide below. Its quick-start,
architecture, and deployment instructions describe classic only; they do not
authorize installing or selecting it for current work. References below to
"the governor" as the authority do not designate classic as today's owner.

## Legacy maintenance guide

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
python3 -m pytest tests/ -q                    # All tests (~14,500)
python3 -m pytest tests/test_<module>.py -v    # Single module
python3 -m pytest tests/ -k "pattern"          # Pattern match
python3 -m pytest sim/ -v                      # Sim harness tests (~80)
python3 -m pytest -m smoke tests/ -v           # Fresh-clone smoke tests
python3 -m pytest -m scale tests/ -v           # Performance/scale tests
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
src/governor/              Core governor logic (~60 modules)
src/governor/signals/      v2.4 instrumentation spine (Phase A-D)
src/fiction_governor/       Fiction mode (characters, canon, drift, guardrails)
src/nonfiction_governor/   Nonfiction mode (corpus, DOI, citations, CFI)
src/ops_governor/          Ops mode (runbooks, blast radius, preconditions)
libs/receipt_kernel/       Receipt kernel (stdlib-only, zero external deps)
sim/governor_sim/          Sim harness (scenario DSL, signal adapter)
tests/                     All tests (python3 -m pytest)
docs/                      Documentation
specs/                     Architectural specs (canonical truth for design)
integration/               Contract tests (Docker-based, run via bash run.sh)
```

Extracted repos (separate GitHub repositories):
- VS Code extension: [github.com/unpingable/vscode-governor](https://github.com/unpingable/vscode-governor)
- WebUI (Phosphor): [github.com/unpingable/governor_webui](https://github.com/unpingable/governor_webui)

---

## Key entry points

| What | Where |
|------|-------|
| Evidence gate (enforcement surface) | `src/governor/evidence_gate.py` |
| Daemon (JSON-RPC control plane, 65 RPCs) | `src/governor/daemon.py` |
| Gate receipts (decision receipts) | `src/governor/gate_receipt.py` |
| Receipt kernel (audit trail) | `libs/receipt_kernel/` |
| Instrumentation spine (signals) | `src/governor/signals/` |
| Chain gate (composition enforcement) | `src/governor/chain_gate.py` |
| CLI | `src/governor/cli.py` |

---

## Coding conventions

- Python 3.10+ (use `|` for union types, not `Union`)
- Dataclasses for all data objects
- Type hints everywhere
- Tests in `tests/test_<module>.py`
- No free-form string assertions — use typed claims (`ClaimType` enum)
- License: Apache-2.0

---

## Core design premises

- **NLAI: Natural language is a proposal, not an authority.** Agents provide pointers, the governor verifies and produces receipts.
- **Gate, not memory.** Write-blocking, not advisory logging.
- **Two ledgers: facts vs decisions.** Facts are empirical and decay. Decisions are normative and persist.
- **Typed claims, not prose.** Claims are structured (`ClaimType` enum), not free-form strings.
- **Agents don't talk to each other.** They talk to the ledger. No agent-to-agent messaging.
- **Concurrency is transactional.** Atomic or nothing.

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
