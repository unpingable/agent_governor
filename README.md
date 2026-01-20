# Agent Governor

**A constraint system that makes AI coding agents production-safe.**

Prevents hallucination, maintains architectural coherence, and enforces evidence requirements for agentic development tools like Claude Code, Cursor, and Codex.

> ⚠️ **Status: Proof of Concept** - The core primitives work. The gate (write-blocking) is not yet implemented. See `BUILD_SPEC.md` for the full architecture.

## The Problem

Current agentic dev tools have critical gaps:
- Agents hallucinate APIs that don't exist
- They contradict themselves across sessions (no memory)
- They drift from architectural decisions
- Quality control requires manual PR review of everything
- No provenance for why decisions were made

## The Solution

The Agent Governor enforces the **Non-Linguistic Authority Invariant (NLAI)**:

> **Language is a proposal, not an authority.**
> No update to authoritative state may be performed solely on the basis of language output.

### The Key Insight

**Agent provides pointers. Governor produces receipts.**

The agent can't "provide evidence" - it can only point to where evidence might be found. The governor runs the actual checks and produces cryptographically-hashed receipts.

## Current Implementation (v0.1)

What works now:
- ✅ Commitment ledger with provenance
- ✅ File existence validation
- ✅ Contradiction detection (keyword-based)
- ✅ Rejection logging for debugging

What's coming (see `BUILD_SPEC.md`):
- ⏳ **Write gate** - no file mutations without verified proposals
- ⏳ **Governor-produced receipts** - agent can't fake evidence
- ⏳ **Typed claims** - structured vocabulary, not prose
- ⏳ **Facts vs Decisions split** - empirical (decays) vs normative (persists)
- ⏳ **FSM states** - DRAFT → PROPOSE → VERIFY → APPLY
- ⏳ **CLI interface** - `governor propose`, `governor verify`, `governor apply`

## Installation

```bash
pip install epistemic-governor
```

## Quick Start

```python
from governor import AgentGovernor

# Initialize with your repo root
governor = AgentGovernor("/path/to/your/repo")

# Agent proposes a claim with evidence
result = governor.propose(
    claim="Using React for frontend framework",
    topic="framework",
    paths=["package.json", "src/App.jsx"],  # Evidence: files that prove the claim
)

if result.accepted:
    print(f"Committed: {result.commit_id}")
else:
    print(f"Rejected: {result.rejection_reason}")

# Get architectural context for agent prompts
context = governor.get_context(topics=["framework", "api"])
# Inject this into your agent's system prompt

# Check for contradictions before a batch of changes
contradictions = governor.check_consistency([
    ("Using Vue components", "framework"),
    ("API uses REST", "api"),
])
```

## Demo

```bash
python demo.py
```

Output:
```
SCENARIO 2: Agent claims API file exists (HALLUCINATION)
  Claim: API endpoint defined in api/users.py
  Status: rejected
  Rejection: No evidence provided and validators could not verify claim

SCENARIO 3: Agent tries to use Vue (CONTRADICTION)
  Claim: Using Vue for frontend framework
  Status: rejected
  Contradiction: Contradicts existing commitment: Using React for frontend framework
```

## Architecture

```
┌─────────────────┐
│  Coding Agent   │  produces patches + pointers
└────────┬────────┘
         │ governor propose <patch>
         ▼
┌─────────────────┐
│    GOVERNOR     │  ← THE CHOKE POINT
│  ┌───────────┐  │
│  │ Verifiers │──┼──→ runs checks, produces receipts
│  └───────────┘  │
│  ┌───────────┐  │
│  │  Ledgers  │──┼──→ facts/ + decisions/
│  └───────────┘  │
└────────┬────────┘
         │ only if verified
         ▼
┌─────────────────┐
│   Working Tree  │  actual file writes
└─────────────────┘
```

## Full Specification

See `BUILD_SPEC.md` for:
- Receipt types (FileSnapshot, CmdRun, DiffReceipt)
- Typed claims (FILE_EXISTS, TESTS_PASS, DECISION, etc.)
- Facts vs Decisions ledger split
- FSM state machine
- CLI interface design
- Step-by-step build guide for Claude Code / Codex

## License

Apache-2.0

---

*Built using the epistemic governor architecture designed to prevent LLM hallucination through external constraint rather than internal alignment.*
