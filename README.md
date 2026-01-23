# Agent Governor

**Production-safe constraints for AI coding agents**

Stop hallucinations. Enforce architectural coherence. Require evidence before writes.

When your AI agent says "I verified the tests pass" or "this API exists" - make it prove it.

---

## The Problem in 30 Seconds

You're using Claude Code, Cursor, or Copilot. The agent:
- Hallucinates APIs that don't exist
- Contradicts itself between sessions
- Drifts from architectural decisions you made yesterday
- Forces you to manually review every single change
- Gives you no audit trail for why decisions were made

**You need a human babysitter for every AI action.** That's not agentic development. That's expensive remote control.

---

## The Solution

Agent Governor enforces the **Non-Linguistic Authority Invariant (NLAI)**:

> Language is a proposal, not an authority.
> No update to authoritative state may be performed solely on the basis of language output.

**Translation:** The agent can *claim* anything. But it can't *write* anything until it provides verifiable evidence.

- Agent says "tests pass"? Governor runs the tests and produces a receipt.
- Agent says "file exists"? Governor checks and hashes the file.
- Agent says "we decided on React"? Governor checks the ledger for contradictions.

**Agent provides pointers. Governor produces receipts.**

---

## Key Features

- **Write gate**: No file mutations without verified evidence
- **Cryptographic receipts**: Governor-produced proof, agent can't fake it
- **Contradiction detection**: Catch when today's agent contradicts yesterday's decisions
- **Commitment ledger**: Full provenance for every architectural decision
- **Facts vs Decisions**: Empirical claims decay, normative decisions persist
- **Rejection logging**: Debug why proposals failed
- **Local-first**: SQLite storage, no external dependencies
- **Framework-agnostic**: Works with Claude Code, Cursor, Codex, or any agent

---

## Quick Start (60 seconds)

```bash
pip install agent-governor
```

```python
from governor import AgentGovernor

# Initialize with your repo root
governor = AgentGovernor("/path/to/your/repo")

# Agent proposes a claim with evidence
result = governor.propose(
    claim="Using React for frontend framework",
    topic="framework",
    paths=["package.json", "src/App.jsx"],  # Evidence files
)

if result.accepted:
    print(f"✓ Committed: {result.commit_id}")
else:
    print(f"✗ Rejected: {result.rejection_reason}")
```

**That's it.** The agent now can't contradict this decision without the governor catching it.

---

## Why This Matters

### Before Agent Governor

```
Agent: "I've updated the API to use GraphQL"
You: "Wait, didn't we decide on REST yesterday?"
Agent: "Oh, you're right. Let me fix that."
You: "How many other things did you change without remembering our decisions?"
Agent: "..."
```

### After Agent Governor

```
Agent: "I propose updating the API to use GraphQL"
Governor: "✗ REJECTED - Contradicts decision from 2024-01-15: 'API uses REST endpoints'"
Agent: "Understood. Maintaining REST architecture."
```

### The Real Difference

Most "AI memory" tools are **memory prosthetics** - they help the agent remember.

Agent Governor is **epistemic security** - it doesn't trust the agent's memory at all.

---

## How It Works

```
┌─────────────────┐
│  Coding Agent   │  Produces patches + pointers to evidence
└────────┬────────┘
         │ governor propose <patch>
         ▼
┌─────────────────┐
│    GOVERNOR     │  ← THE CHOKE POINT
│  ┌───────────┐  │
│  │ Verifiers │──┼──→ Runs actual checks, produces receipts
│  └───────────┘  │
│  ┌───────────┐  │
│  │  Ledgers  │──┼──→ facts/ + decisions/
│  └───────────┘  │
└────────┬────────┘
         │ Only if verified
         ▼
┌─────────────────┐
│   Working Tree  │  Actual file writes happen here
└─────────────────┘
```

**Key insight:** The agent can't provide evidence - it can only provide *pointers* to where evidence might exist. The governor does the actual verification and produces cryptographically-hashed receipts.

No hallucination can fake a receipt.

---

## Current Status

**737 tests passing** - Core system complete, multi-agent support, fiction/non-fiction governors, task management, audit graph.

### What Works Now

- Commitment ledger with full provenance
- File existence validation
- Command execution verification (tests pass, builds succeed)
- Contradiction detection
- Rejection logging for debugging
- Multi-agent coordination (SQLite with WAL mode)
- Agent permissions and blast radius limits
- MCP server for Claude Desktop integration
- Git pre-commit hook enforcement
- **Issue/task tracking with subtasks, dependencies, and milestones**
- **Session management with handoff notes**
- **Time tracking with start/stop timers**
- **Smart recommendations for what to work on next**
- **Audit graph with Maltego-style transforms** (claims→evidence, drift detection, rejection patterns)

### CLI Commands

```bash
# Initialize
governor init

# Propose/verify/apply workflow
governor propose --claim "type=file_exists,path=src/main.py"
governor verify <proposal-id>
governor apply <proposal-id>

# Query state
governor facts
governor decisions
governor status

# Multi-agent coordination
governor agent register --id worker-1 --class implementer
governor task claim --agent-id worker-1 --task "implement feature" --scope "src/api.py"

# Issue/task management
governor issue add "Implement feature" -p high -l feature
governor issue list --tree
governor issue start <task-id>
governor issue done <task-id>
governor issue block <task-id> <blocked-by-id>
governor issue next  # Get recommendations

# Milestones and labels
governor issue milestone add "v1.0" --due 2024-03-01
governor issue label add "bug" --color "#ff0000"

# Time tracking
governor issue timer start <task-id>
governor issue timer stop <task-id>

# Session handoffs
governor issue session start
governor issue session end --summary "Did X" --next "Do Y" --blocker "Waiting on Z"
governor issue session handoff  # Show last session's notes

# Export/import
governor issue export -o backup.json
governor issue import backup.json

# Audit graph (Maltego-style)
governor graph export -f json -o audit.json
governor graph export -f graphviz | dot -Tpng -o graph.png
governor graph stats           # Node/edge counts by type
governor graph unverified      # Claims lacking evidence
governor graph weak            # Proposals with weak grounding
governor graph rejections      # Rejection patterns
governor graph drift           # Session drift analysis
governor graph view            # Interactive browser viewer

# Integration
governor hook install
governor mcp serve
```

---

## Real-World Use Cases

### Architecture Enforcement
```python
# Commit your architectural decisions
governor.propose(
    claim="Microservices communicate via message queue, not direct HTTP",
    topic="architecture",
    decision=True
)

# Agent can't violate this without explicit override
```

### API Validation
```python
# Agent claims an endpoint exists
result = governor.propose(
    claim="User authentication endpoint at /api/v1/auth",
    paths=["api/routes.py", "tests/test_auth.py"]
)
# Governor verifies files exist and contain relevant code
```

### Test Requirements
```python
# Require tests to pass before accepting changes
result = governor.propose(
    claim="All tests pass after authentication refactor",
    verification_cmd="pytest tests/",
)
# Governor runs pytest and produces receipt
```

### Session Continuity
```python
# Get context for your agent's next session
context = governor.get_context(topics=["architecture", "api"])
# Inject into system prompt - agent now knows what was decided
```

### Task Management
```bash
# Break work into trackable pieces
governor issue add "Implement auth" -p high -m "v1.0"
governor issue add "Add login endpoint" --parent <auth-task-id>
governor issue add "Add logout endpoint" --parent <auth-task-id>

# Track dependencies
governor issue block <logout-id> <login-id>  # logout depends on login

# Get smart recommendations
governor issue next
# > 1. Add login endpoint [HIGH] (unblocks 1)
# > 2. Implement auth [HIGH] (milestone due in 5d)

# Preserve context across sessions
governor issue session start
# ... do work ...
governor issue session end \
  --summary "Implemented login, tests passing" \
  --next "Add logout endpoint" \
  --blocker "Need API docs for OAuth"

# Next session picks up where you left off
governor issue session handoff
```

---

## Demo

```bash
python demo.py
```

**Output:**
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

---

## Philosophy: Why External Constraint Beats Internal Alignment

**The problem with current approaches:**
- "Prompt engineering" - trying to make the agent more careful
- "Retrieval-augmented generation" - giving the agent better memory
- "Fine-tuning" - training the agent to be more accurate

**All of these assume:** If we make the agent smarter/better/more careful, it will make fewer mistakes.

**Agent Governor assumes:** The agent will *always* make mistakes. Build a system that catches them.

This is the same philosophy as:
- Type systems (don't trust the programmer, enforce constraints)
- TDD (don't trust your code, write tests first)
- Code review (don't trust yourself, require second verification)

**You wouldn't let untrusted code deploy without CI/CD. Why let untrusted agents write without verification?**

### The Audit Graph: Knowledge Governance

The audit graph isn't intelligence gathering - it's **knowledge governance**.

Where OSINT tools extract and correlate facts, Governor maps:
- **Epistemic provenance** - why a claim exists
- **Hypothesis stress-testing** - what supports it, what it displaced
- **Contradiction surfacing** - what it contradicts
- **Lineage and drift analysis** - what downstream actions depended on it
- **"What must be true for this to be allowed"** - made visible

This is research in the old sense. The kind that produces:
- Invariants
- Refutations
- Stable objects
- Reusable insight

**The spicy part:** Once you have that graph, LLMs stop being oracles and become junior analysts. They don't get to invent structure - they navigate one.

You're not building OSINT tooling. You're building a **lab bench for reasoning under constraint**.

---

## Installation

```bash
pip install agent-governor
```

Or from source:
```bash
git clone https://github.com/yourusername/agent-governor
cd agent-governor
pip install -e .
```

---

## Full Documentation

- **BUILD_SPEC.md** - Complete architecture specification
  - Receipt types (FileSnapshot, CmdRun, DiffReceipt)
  - Typed claims vocabulary
  - Facts vs Decisions ledger design
  - FSM state machine
  - Step-by-step build guide

- **MULTI_AGENT.md** - Multi-agent coordination
  - SQLite WAL mode for concurrency
  - Leases and epochs
  - Agent permissions
  - Dispatcher protocol

- **CLAUDE.md** - Development guide for contributors

---

## Comparison: Memory vs Governance

| Feature | Memory Tools | Agent Governor |
|---------|-------------|----------------|
| **Purpose** | Help agent remember | Prevent agent from lying |
| **Trust model** | Agent is helpful but forgetful | Agent is unreliable, require proof |
| **Verification** | None - agent's word is trusted | Cryptographic receipts required |
| **Write control** | No blocking | Write gate enforced |
| **Architecture** | Memory prosthetic | Epistemic security system |
| **Use case** | Task continuity | Production safety |

**Both are useful. They solve different problems.**

Use memory tools when you want continuity across sessions.
Use Agent Governor when you need production-safe AI development.

---

## License

Apache-2.0

---

## Why "Governor"?

In mechanical systems, a governor limits speed to prevent damage - like the spinning-ball mechanism on old steam engines.

In AI systems, the Agent Governor limits autonomy to prevent hallucination.

**Speed without control is just chaos.**

---

*When your AI agent speaks, make it show its work.*
