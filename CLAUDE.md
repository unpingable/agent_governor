# CLAUDE.md - Instructions for Claude Code

## Project Overview

This is the **Agent Governor** - a constraint system for agentic coding tools. The core principle: **Language is a proposal, not an authority (NLAI)**.

**Status: Phase 1-3 COMPLETE** - All 14 steps from BUILD_SPEC.md implemented.
**Multi-Agent v2**: SQLite backend, leases, epochs, permissions, dispatcher protocol.
**Fiction Governor**: Prototype complete.
**Non-Fiction Governor**: Corpus management, DOI fetching, citation verification.
**Total: 642 tests**

## Key Documents

- `BUILD_SPEC.md` - Step-by-step build guide, receipt types, claim types, FSM
- `MULTI_AGENT.md` - Concurrency model, conflict detection, permissions, dispatcher protocol
- `TODO.md` - Future enhancements

## Quick Start

```bash
# Install in dev mode
pip install -e .

# Initialize governor in a project
governor init

# Run tests
pytest tests/ -v
```

## CLI Commands

```bash
# Core workflow
governor init                    # Initialize .governor/ directory
governor propose --claim "..."   # Create proposal with claims
governor verify <id>             # Verify proposal, produce receipts
governor apply <id>              # Apply verified proposal

# Query state
governor facts                   # List recorded facts
governor decisions               # List recorded decisions
governor status                  # Show proposal statuses
governor rejections              # Show rejection history

# Configuration
governor envelope                # Get/set operating mode (strict/exploratory)
governor decay                   # Check for stale facts

# Integration
governor hook install            # Install git pre-commit hook
governor hook status             # Check hook status
governor wrap -- <cmd>           # Wrap agent command with enforcement
governor changes                 # Show file approval status

# MCP Server
governor mcp serve               # Run MCP server for Claude integration
governor mcp tools               # List available MCP tools
governor mcp call <tool>         # Test MCP tools directly

# Multi-Agent Dispatcher Protocol (v2)
governor init --v2               # Initialize with SQLite backend
governor agent register --id X   # Register agent with governor
governor agent list              # List registered agents
governor agent permissions X     # Show permissions for agent
governor agent heartbeat --id X  # Keep agent registration active
governor task claim --agent-id X --task "..." --scope "..."  # Claim task
governor task heartbeat --agent-id X --task-id Y             # Extend task
governor task complete --agent-id X --task-id Y              # Complete task
governor task list               # List tasks/reservations
governor task cancel --agent-id X --task-id Y                # Cancel task
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

## File Structure

```
src/governor/
├── __init__.py       # Public API exports
├── receipts.py       # FileSnapshot, CmdRun, DiffReceipt dataclasses
├── producers.py      # Receipt-producing functions
├── claims.py         # ClaimType enum, Claim dataclass with validation
├── ledgers.py        # FactLedger, DecisionLedger with decay/conflict detection
├── fsm.py            # State machine: DRAFT→PROPOSED→VERIFIED→APPLIED
├── verifiers.py      # FileVerifier, CommandVerifier, DiffVerifier, etc.
├── envelopes.py      # Operating modes: exploratory vs strict
├── hooks.py          # Git pre-commit hook integration
├── wrapper.py        # Agent wrapper for file write interception
├── mcp_server.py     # MCP protocol server for Claude integration
├── cli.py            # Click CLI with all commands
│
# Multi-Agent v2 (SQLite-backed):
├── storage.py        # SQLite backend with WAL mode, leases, epochs
├── ledgers_v2.py     # SQLiteFactLedger, SQLiteDecisionLedger
├── permissions.py    # AgentPermissions, PermissionManager, profiles
│
# Legacy (v0.1, kept for reference):
├── core.py           # Original AgentGovernor class
├── ledger.py         # Original CodebaseLedger
├── validators.py     # Original validators
└── types.py          # Original type definitions

src/fiction_governor/
├── __init__.py       # Public API exports
├── types.py          # Character, WorldRule, BannedTrope, CanonEvent, etc.
├── bible.py          # Bible ledger (characters, world rules, tone, tropes)
├── canon.py          # Canon ledger (events, relationships)
├── verifiers.py      # InCharacterVerifier, TropeVerifier, ToneVerifier
└── cli.py            # fiction-gov CLI

src/nonfiction_governor/
├── __init__.py       # Public API exports
├── types.py          # Source, Concept, Position, WritingClaim
├── doi.py            # DOI metadata fetching (CrossRef/DataCite)
├── corpus.py         # Corpus ledger (your papers, concepts, positions)
├── verifiers.py      # CitationVerifier, TerminologyVerifier, ConsistencyVerifier
└── cli.py            # nonfiction-gov CLI
```

## Implementation Summary

### Phase 1 - The Gate (Weekend MVP)
| Step | Module | Description | Tests |
|------|--------|-------------|-------|
| 1 | receipts.py | FileSnapshot, CmdRun, DiffReceipt | 22 |
| 2 | producers.py | Receipt production from real inputs | 32 |
| 3 | claims.py | ClaimType enum, Claim validation | 42 |
| 4 | ledgers.py | FactLedger, DecisionLedger | 35 |
| 5 | fsm.py | State machine with guards | 33 |
| 6 | verifiers.py | Receipt-producing verifiers | 37 |
| 7 | cli.py | Core CLI commands | 25 |

### Phase 2 - Production Hardening
| Step | Feature | Description | Tests |
|------|---------|-------------|-------|
| 8 | Fact decay | Auto-invalidate when files change | 11 |
| 9 | Conflicts | Key-value conflict detection | 12 |
| 10 | Envelopes | exploratory vs strict modes | 15 |
| 11 | Feedback | Machine-readable rejection errors | 18 |

### Phase 3 - Integration
| Step | Feature | Description | Tests |
|------|---------|-------------|-------|
| 12 | Git hooks | Pre-commit enforcement | 33 |
| 13 | Wrapper | Agent file write interception | 29 |
| 14 | MCP server | Claude Desktop integration | 22 |

**Phase 1-3 tests: 381**

### Multi-Agent v2 (SQLite Backend)
| Module | Description | Tests |
|--------|-------------|-------|
| storage.py | SQLite with WAL, leases, epochs | 26 |
| ledgers_v2.py | SQLiteFactLedger, SQLiteDecisionLedger | 29 |
| claims.py | WORK_RESERVATION, INTENT claim types | 13 |
| permissions.py | AgentPermissions, PermissionManager | 27 |
| cli.py | Dispatcher protocol (agent/task commands) | 24 |

**Multi-Agent v2 tests: 119**

### Fiction Governor (Prototype)
| Module | Description | Tests |
|--------|-------------|-------|
| types.py | Character, WorldRule, BannedTrope, CanonEvent | 12 |
| bible.py | Bible ledger (decisions about story) | 12 |
| canon.py | Canon ledger (facts about story) | 9 |
| verifiers.py | In-character, trope, tone verification | 18 |

**Fiction Governor tests: 51**

### Non-Fiction Governor (Academic Writing)
| Module | Description | Tests |
|--------|-------------|-------|
| types.py | Source, Concept, Position, WritingClaim | 40 |
| corpus.py | Corpus ledger, conflict detection | 26 |
| verifiers.py | Citation, terminology, consistency verification | 25 |
| doi.py | DOI metadata fetching (CrossRef/DataCite) | -- |

**Non-Fiction Governor tests: 91**

**Total: 642 tests**

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
   # WRONG - agent-to-agent messaging, Gas Town style
   agent_a.tell(agent_b, "I'm working on /users")

   # RIGHT - coordination as state in ledger
   propose(Claim(type=ClaimType.WORK_RESERVATION, scope=["src/api/users.py"]))
   ```

6. **Don't skip the transaction.**
   ```python
   # WRONG - race condition village
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
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_claims.py -v

# Run with coverage
pytest tests/ --cov=governor
```

## Code Conventions

- Python 3.10+ (use `|` for union types)
- Dataclasses for all data objects
- Type hints everywhere
- Tests in `tests/test_<module>.py`

## The Meta-Constraint

You are using a tool designed to constrain AI coding agents. Apply its principles:
- Don't claim a file exists without checking
- Don't claim tests pass without running them
- Don't contradict architectural decisions
- Cite your receipts.
