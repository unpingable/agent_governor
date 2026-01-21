# CLAUDE.md - Instructions for Claude Code

## Project Overview

This is the **Epistemic Governor** - a constraint system for agentic coding tools. The core principle: **Language is a proposal, not an authority (NLAI)**.

**Status: COMPLETE** - All 14 steps from BUILD_SPEC.md are implemented with 381 tests.

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
# Legacy (v0.1, kept for reference):
├── core.py           # Original AgentGovernor class
├── ledger.py         # Original CodebaseLedger
├── validators.py     # Original validators
└── types.py          # Original type definitions
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

**Total: 381 tests**

## Claim Types

```python
ClaimType.FILE_EXISTS      # path exists
ClaimType.SYMBOL_DEFINED   # symbol at path:span
ClaimType.API_SURFACE      # endpoint/signature at location
ClaimType.TESTS_PASS       # command exits 0
ClaimType.DECISION         # normative choice (framework, style)
ClaimType.CHANGESET        # proposed file mutations
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
