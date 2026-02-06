# Agent Governor Architecture

## The Map

This document provides a high-level view of the Agent Governor system. For detailed subsystem specs, see `specs/core/`.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        AGENT GOVERNOR                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │   WebUI     │────▶│  Adapters   │────▶│   Governor  │        │
│  │ (built-in)  │     │ (per-user)  │     │   (kernel)  │        │
│  └─────────────┘     └─────────────┘     └──────┬──────┘        │
│                                                  │              │
│                      ┌───────────────────────────┼───────────┐  │
│                      │                           ▼           │  │
│                      │  ┌─────────┐  ┌─────────┐  ┌────────┐ │  │
│                      │  │ Anchors │  │ Ledger  │  │ Verify │ │  │
│                      │  └─────────┘  └─────────┘  └────────┘ │  │
│                      │           STORAGE (.governor/)        │  │
│                      └───────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │     CLI     │────▶│   Modes     │────▶│  Profiles   │        │
│  │ (governor)  │     │(fiction/code)│    │  (presets)  │        │
│  └─────────────┘     └─────────────┘     └─────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Inventory

### Entry Points

| Component | Path | Description |
|-----------|------|-------------|
| CLI | `src/governor/cli.py` | Main command-line interface (50+ commands) |
| WebUI Adapter | `src/webui/adapter.py` | FastAPI server, OpenAI-compatible API |
| MCP Server | `src/governor/mcp_server.py` | Model Context Protocol for Claude Desktop |

### Core Kernel

| Component | Path | Description |
|-----------|------|-------------|
| FSM | `src/governor/fsm.py` | State machine: DRAFT→PROPOSED→VERIFIED→APPLIED |
| Claims | `src/governor/claims.py` | Typed claim system with validation |
| Verifiers | `src/governor/verifiers.py` | Receipt-producing verification |
| Receipts | `src/governor/receipts.py` | FileSnapshot, CmdRun, DiffReceipt |

### Storage Layer

| Component | Path | Description |
|-----------|------|-------------|
| SQLite Backend | `src/governor/storage.py` | WAL mode, leases, epochs, migrations |
| Fact Ledger | `src/governor/ledgers_v2.py` | Empirical claims with auto-decay |
| Decision Ledger | `src/governor/ledgers_v2.py` | Normative choices, conflict detection |
| Epistemic Ledger | `src/governor/epistemic.py` | Provenance, confidence, evidence |

### Mode Subsystems

| Component | Path | Description |
|-----------|------|-------------|
| Fiction Governor | `src/fiction_governor/` | Canon, characters, plot threads, guardrails |
| Nonfiction Governor | `src/nonfiction_governor/` | Sources, concepts, positions, CFI |
| Ops Governor | `src/ops_governor/` | Runbooks, blast radius, preconditions |

### Continuity Enforcement

| Component | Path | Description |
|-----------|------|-------------|
| Anchors | `src/governor/continuity.py` | Semantic constraint setpoints |
| Checker | `src/governor/continuity.py` | Lexical deviation measurement |
| Correction Ladder | `src/governor/continuity.py` | Escalating interventions |
| Convergence Executor | `src/governor/continuity.py` | Closed-loop generation control |
| Violation Resolver | `src/governor/violation_resolver.py` | Fix/Revise/Proceed resolution flow |
| Staleness Detector | `src/governor/staleness.py` | Time-bounded verification, decay |
| Docket Manager | `src/governor/docket.py` | Cases, rulings, precedent record |
| Claim Status Dashboard | `src/governor/claim_status.py` | Weather report, health scoring |

### Governance Control

| Component | Path | Description |
|-----------|------|-------------|
| Regime Detection | `src/governor/regime.py` | ELASTIC/WARM/DUCTILE/UNSTABLE |
| Boil Control | `src/governor/boil.py` | Named presets with dwell time |
| Strict Mode | `src/governor/strict.py` | Fail-closed governance |
| Profiles | `src/governor/profiles.py` | Named governance presets |

### Multi-Agent Coordination

| Component | Path | Description |
|-----------|------|-------------|
| Permissions | `src/governor/permissions.py` | Agent capabilities and scopes |
| Quorum | `src/governor/quorum.py` | Multi-agent consensus protocol |
| Independence | `src/governor/independence.py` | Cooperative redundancy scoring |
| Sybil Resistance | `src/governor/sybil.py` | Bloc detection, effective voters |

### Security & Audit

| Component | Path | Description |
|-----------|------|-------------|
| Security Verifier | `src/governor/security.py` | Secret detection, injection, XSS |
| Audit Pipeline | `src/governor/audit.py` | Hallucination detection, failure modes |
| Claim Diff | `src/governor/claim_diff.py` | Epistemic state change detection |
| Taint Index | `src/governor/taint.py` | Recurrence detection |

### Adaptive Control

| Component | Path | Description |
|-----------|------|-------------|
| Ultrastability | `src/governor/ultrastability.py` | S₁ adaptive parameters |
| Homeostat | `src/governor/homeostat.py` | Exploration budgets, gain scheduling |
| Coupling | `src/governor/coupling.py` | Homeostat→Ultrastability protocol |
| Auto-Tuning | `src/governor/auto_tuning.py` | Threshold learning, calibration |

### Autonomous Execution

| Component | Path | Description |
|-----------|------|-------------|
| Spine | `src/governor/spine.py` | Locked project structure |
| Invariants | `src/governor/invariants.py` | Mechanically verifiable rules |
| Executor | `src/governor/executor.py` | Step-function loop with checkpointing |
| Sessions | `src/governor/execution.py` | Multi-session persistence |

### Telemetry & Observability

| Component | Path | Description |
|-----------|------|-------------|
| Telemetry | `src/governor/telemetry.py` | Structured logging, JSONL export |
| Prometheus | `src/governor/cli.py` | Optional metrics at /metrics |
| Dashboard | `src/governor/cli.py` | Rich TUI for regime visualization |

---

## Data Flow

### Request → Response (Chat)

```
User Input
    │
    ▼
┌──────────────┐
│   WebUI /    │
│   Adapter    │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  ChatBridge  │────▶│   Backend    │ (Anthropic/Ollama/ClaudeCode)
└──────┬───────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│ GovernorHooks│ ─── System prompt enrichment
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  LLM Call    │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  Continuity  │────▶│   Anchors    │ Check against constraints
│   Checker    │     └──────────────┘
└──────┬───────┘
       │
       ├── No violations → Return response
       │
       └── Violations → ViolationResolver
                              │
                              ▼
                        ┌──────────────┐
                        │ Fix/Revise/  │
                        │   Proceed    │
                        └──────────────┘
```

### Proposal → Receipt (Verification)

```
Agent Proposal
    │
    ▼
┌──────────────┐
│     FSM      │ DRAFT → PROPOSED
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│   Verifier   │────▶│   Receipt    │ (FileSnapshot/CmdRun/Diff)
└──────┬───────┘     │   Producer   │
       │             └──────────────┘
       ▼
┌──────────────┐
│    Ledger    │ Store with provenance
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     FSM      │ PROPOSED → VERIFIED → APPLIED
└──────────────┘
```

---

## Core Invariants

These rules cannot be broken:

1. **NLAI: Language is a proposal, not an authority.**
   - Agents provide pointers (paths, commands)
   - Governor produces receipts (hashed proof)
   - Never trust agent-provided "evidence"

2. **Gate, not memory.**
   - Write-blocking, not advisory logging
   - No file mutations without verified proposals

3. **Two ledgers: facts vs decisions.**
   - Facts = empirical, auto-decays
   - Decisions = normative, persists until revised

4. **Typed claims, not prose.**
   - Claims are structured with ClaimType enums
   - No free-form string assertions

5. **Agents talk to the ledger, not each other.**
   - No agent-to-agent messaging
   - Ledger is the only shared state

6. **Concurrency is transactional.**
   - SQLite with WAL mode
   - Leases prevent collision
   - Atomic or nothing

---

## Directory Structure

```
.governor/                    # Project-local state (gitignored)
├── governor.db               # SQLite database (facts, decisions, claims)
├── anchors.json              # Continuity anchors
├── pending_violations.json   # Awaiting resolution
├── docket_cases.json         # Pending docket cases
├── precedents.json           # Logged rulings (precedent record)
├── exceptions/               # Logged proceed decisions
├── receipts/                 # Verification receipts
├── sessions/                 # Execution sessions
├── spines/                   # Locked project structures
└── invariants/               # Persistent invariant specs
```

---

## Extension Points

### Adding a New Mode

1. Create mode package under `src/` (e.g., `src/mymode_governor/`)
2. Define types, verifiers, ledger extensions
3. Add anchor factories in `continuity_bridges.py`
4. Register mode in `GovernorHooks`
5. Add CLI commands

### Adding a New Claim Type

1. Add to `ClaimType` enum in `claims.py`
2. Add verifier in `verifiers.py`
3. Update relevant ledger for storage
4. Add CLI support

### Adding a New Invariant Kind

1. Add to `VALID_KINDS` in `invariant_store.py`
2. Create factory function returning `Invariant`
3. Implement check logic
4. Add CLI support

---

## Subsystem Documentation

For subsystem details, see the core specs (`specs/core/`) and the implementation summary (`.claude/rules/implementation-summary.md`). For mode-specific guides, see `docs/modes/`.

Key entry points:

- `MULTI_AGENT.md` — Coordination, leases, permissions
- `BUILD_SPEC.md` — Core kernel design, receipt types, claim lifecycle
- `specs/core/EPISTEMIC_STACK_SPEC.md` — Provenance, confidence, evidence (11 modules)
- `specs/core/KERNEL_CONSTRAINTS_SPEC.md` — The five non-negotiable invariants
- `.claude/rules/cli-reference.md` — All 100+ CLI commands

---

*"The goal is not to make the AI smarter. It's to make it respect boundaries."*
