# CLAUDE.md - Instructions for Claude Code

## Project Overview

This is the **Agent Governor** — a constraint system for agentic coding tools. The core principle: **Language is a proposal, not an authority (NLAI)**.

The system provides write-blocking governance for AI coding agents via typed claims, receipt-producing verification, and transactional ledgers. It spans code governance, fiction writing, academic writing, SRE operations, and multi-agent coordination.

~7300 tests across 60+ modules. See `.claude/rules/implementation-summary.md` for full feature status and test counts.

## Key Documents

- `BUILD_SPEC.md` — Step-by-step build guide, receipt types, claim types, FSM
- `MULTI_AGENT.md` — Concurrency model, conflict detection, permissions, dispatcher protocol
- `.claude/rules/` — Modular rules (CLI reference, file structure, domain-specific guides)

## Quick Start

```bash
pip install -e .           # Install in dev mode
governor init              # Initialize .governor/ directory
pytest tests/ -v           # Run tests
bash start.sh              # WebUI with Claude Code backend
bash start-codex.sh        # WebUI with Codex backend (auto-detects Node, arch, binary)
```

## Architecture Rules (Non-Negotiable)

1. **NLAI: Language is a proposal, not an authority.**
   - Agents provide *pointers* (file paths, commands to run)
   - Governor produces *receipts* (hashed proof of verification)
   - Never trust agent-provided "evidence"

2. **Gate, not memory.**
   - The goal is write-blocking, not advisory logging
   - No file mutations without verified proposals
   - Pre-commit hook enforces this

3. **Two ledgers: facts vs decisions.**
   - `facts/` = empirical, auto-decays when files change
   - `decisions/` = normative, persists until explicitly revised
   - "Tests pass" is a fact. "We use React" is a decision.

4. **Typed claims, not prose.**
   - Claims are structured: `ClaimType.FILE_EXISTS`, `ClaimType.TESTS_PASS`, etc.
   - No free-form string assertions
   - If the claim type doesn't exist, add it to the enum first

5. **Agents don't talk to each other. They talk to the ledger.**
   - No agent-to-agent messaging
   - No "Mayor" or coordinator agent
   - Ledger is the only shared state
   - Conflicts are structural, not political

6. **Concurrency is transactional.** (see MULTI_AGENT.md)
   - SQLite with WAL mode for concurrent access
   - Leases prevent collision during verification
   - Epochs enable optimistic concurrency
   - No partial commits - atomic or nothing

## Common Mistakes to Avoid

1. **Don't let agents provide evidence directly.**
   ```python
   # WRONG - agent can lie
   def propose(claim: str, evidence: Evidence): ...

   # RIGHT - agent provides pointers, governor verifies
   def propose(claim: Claim, pointers: list[str]): ...
   ```

2. **Don't use free-form strings for claims.**
   ```python
   # WRONG - unstructured, hard to validate
   propose(claim="I think the tests pass")

   # RIGHT - typed, machine-checkable
   propose(claim=Claim(type=ClaimType.TESTS_PASS, command=["pytest"]))
   ```

3. **Don't mix facts and decisions.**
   ```python
   # WRONG - treating preference as theorem
   facts.add("we use React")

   # RIGHT - normative choice in decisions ledger
   decisions.add(Decision(topic="framework", choice="react"))
   ```

4. **Don't make it advisory.**
   ```python
   # WRONG - can be ignored
   if not governor.approve(patch):
       logger.warning("Governor rejected patch")
       apply_patch_anyway(patch)  # oops

   # RIGHT - gate is mandatory
   if not governor.approve(patch):
       raise GovernorRejection(patch, reason)
   ```

5. **Don't let agents coordinate directly.**
   ```python
   # WRONG - direct agent-to-agent messaging bypasses the ledger
   agent_a.tell(agent_b, "I'm working on /users")

   # RIGHT - coordination as state in ledger
   propose(Claim(type=ClaimType.WORK_RESERVATION, scope=["src/api/users.py"]))
   ```

6. **Don't skip the transaction.**
   ```python
   # WRONG - TOCTOU: check-then-act without atomicity
   if not has_conflict(claim):
       commit(claim)  # another agent could have committed between check and write

   # RIGHT - atomic transaction
   with db.transaction():
       if not has_conflict(claim):
           commit(claim)
   ```

## Claim Types

```python
ClaimType.FILE_EXISTS      # path exists
ClaimType.SYMBOL_DEFINED   # symbol at path:span
ClaimType.API_SURFACE      # endpoint/signature at location
ClaimType.TESTS_PASS       # command exits 0
ClaimType.DECISION         # normative choice (framework, style)
ClaimType.CHANGESET        # proposed file mutations

# Multi-agent coordination (v2):
ClaimType.WORK_RESERVATION # reserve scope for task (locks resources)
ClaimType.INTENT           # declare intent (advisory, no lock)
```

## Receipt Types

```python
FileSnapshot   # Proves file state at verification time
CmdRun         # Proves command execution result
DiffReceipt    # Proves changeset content
```

## Operating Envelopes

- **strict** (default): All claims require receipts, decisions committed, conflicts blocked
- **exploratory**: Receipts optional, decisions not committed, conflicts allowed

## Testing

```bash
pytest tests/ -v                   # Run all tests
pytest tests/test_claims.py -v     # Run specific module
pytest tests/ --cov=governor       # Run with coverage
pytest -m smoke tests/ -v          # Fresh-clone smoke tests (subprocess + real git)
pytest -m scale tests/ -v          # Performance/scale tests (generous bounds)
```

## Code Conventions

- Python 3.10+ (use `|` for union types)
- Dataclasses for all data objects
- Type hints everywhere
- Tests in `tests/test_<module>.py`

## Modular Rules

Detailed reference material is in `.claude/rules/`:

| File | Contents | Scoped? |
|------|----------|---------|
| `cli-reference.md` | All CLI commands | No (always loaded) |
| `file-structure.md` | Full file tree | No (always loaded) |
| `implementation-summary.md` | Feature status, test counts | No (always loaded) |
| `fiction-governor.md` | Fiction governor details | `src/fiction_governor/**` |
| `nonfiction-governor.md` | Non-fiction governor details | `src/nonfiction_governor/**` |
| `ops-governor.md` | Ops governor details | `src/ops_governor/**` |
| `vscode-extension.md` | VS Code extension details (extracted to separate repo) | N/A |
| `webui.md` | WebUI (extracted to gov-webui), chat bridge, interferometry | `chat_bridge`, etc. |
| `writing-modules.md` | W5 writing modules (11 modules) | `src/governor/writing_*.py` |

Path-scoped rules only load when Claude is working on matching files, reducing context overhead.

## Authority Boundary

This file is **guidance for Claude Code**, not enforcement. The governor is enforcement.

- This file and `.claude/rules/` shape Claude's behavior (travel guide)
- The governor determines admissibility (constitution)
- See `AGENTS.md` for the agent-neutral version of these conventions

> Instruction files shape behavior; the governor determines admissibility.

## The Meta-Constraint

You are using a tool designed to constrain AI coding agents. Apply its principles:
- Don't claim a file exists without checking
- Don't claim tests pass without running them
- Don't contradict architectural decisions
- Cite your receipts.
