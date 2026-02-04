# Agent Governor

**Production-oriented constraints for AI coding agents.**
Agents can *propose*. Only the governor can *commit*.
**Agent provides pointers. Governor produces receipts.**
No write hits disk unless verification succeeds.

Block unverified writes. Catch contradictions. Persist decisions.

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
- **Cryptographic receipts**: SHA-256 hashes of file state, command output, and diffs at verification time — stored in the ledger, not producible by agents
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

# Initialize governor in your project
cd your-project
governor init

# Record an architectural decision
governor propose --claim "Using React for frontend" --topic framework
governor verify 1
governor apply 1

# Now the governor will catch contradictions
governor propose --claim "Using Vue for frontend" --topic framework
# ✗ REJECTED - Contradicts existing decision on 'framework'
```

**That's it.** The agent now can't contradict this decision without the governor catching it.

### For Writers (Fiction Mode)

```bash
# Set up a character constraint
governor continuity anchor add \
  --id "elena-eyes" \
  --type canon \
  --description "Elena has green eyes" \
  --forbidden-patterns "Elena's blue eyes" "her blue eyes" \
  --severity reject

# Check text for violations
governor check chapter3.txt --mode fiction
```

### For Developers (Code Mode)

```bash
# Set your working profile
governor intent set --profile hotfix --scope "src/auth/**" --because "fixing login bug"

# Check files as you work
governor check src/auth/login.py

# VS Code: Ctrl+Shift+G to check current file
```

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

**Key insight:** The agent can't provide evidence — it can only provide *pointers* to where evidence might exist. The governor does the actual verification and produces cryptographically-hashed receipts.

No hallucination can fake a receipt.

### Threat Model

- **Agents are untrusted.** They may hallucinate, contradict prior decisions, or drift from architectural constraints.
- **The host is trusted.** Governor runs locally with direct filesystem access.
- **Governor defends against:** fabricated claims, unverified writes, temporal drift, epistemic amplification across agents.
- **Governor does NOT defend against:** malicious dependencies, compromised host, adversarial model weights.

---

## Current Status

**2,000+ tests passing** — Core system, multi-agent coordination, epistemic governance, fiction/non-fiction governors, ops governor, drift detection, ultrastability.

### What Works Now

- Commitment ledger with full provenance (facts vs decisions)
- File existence validation, command execution verification
- Contradiction detection with rejection logging
- Multi-agent coordination (SQLite WAL, leases, permissions)
- Epistemic governance (provenance tracking, confidence modeling, evidence requirements)
- Regime detection (ELASTIC/WARM/DUCTILE/UNSTABLE health monitoring)
- Drift detection (temporal asymmetry defense, premise quarantine)
- Ultrastability (Ashby-style S₁ adaptation with pathology detection)
- MCP server for Claude Desktop, git pre-commit hook enforcement
- Audit graph with Maltego-style transforms
- Task management with dependencies, milestones, session handoffs

### CLI Commands (Highlights)

```bash
# Core workflow
governor init                   # Initialize .governor/ directory
governor propose --claim "..."  # Create proposal with claims
governor verify <id>            # Verify proposal, produce receipts
governor apply <id>             # Apply verified proposal

# Query state
governor facts                  # List recorded facts
governor decisions              # List recorded decisions
governor status                 # Show proposal statuses

# Multi-agent coordination
governor agent register --id X  # Register agent with governor
governor task claim --agent-id X --task "..." --scope "..."

# Epistemic & regime
governor epistemic status       # Provenance, confidence, evidence
governor regime status          # Operational health (ELASTIC → UNSTABLE)
governor drift status           # Temporal asymmetry defense

# Integration
governor hook install           # Git pre-commit enforcement
governor mcp serve              # MCP server for Claude integration
```

See **CLAUDE.md** for the full CLI reference (~50 commands across 15 subsystems).

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
# Track work with dependencies, milestones, and session handoffs
governor issue add "Implement auth" -p high -m "v1.0"
governor issue block <logout-id> <login-id>
governor issue next                          # Prioritized recommendations
governor issue session handoff               # Resume context across sessions
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
git clone https://github.com/unpingable/agent_governor
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
| **Purpose** | Help agent remember | Prevent ungrounded commits |
| **Trust model** | Agent is helpful but forgetful | Agent is unreliable, require proof |
| **Verification** | Optional / out of band | Cryptographic receipts required |
| **Write control** | No blocking | Write gate enforced |
| **Architecture** | Memory prosthetic | Epistemic security system |
| **Use case** | Task continuity | Production safety |

**Both are useful. They solve different problems.**

Use memory tools when you want continuity across sessions.
Use Agent Governor when you need production-oriented AI development with verification guarantees.

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
