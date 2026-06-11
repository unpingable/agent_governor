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
| CLI | `src/governor/cli.py` | Main command-line interface (100+ commands) |
| Daemon | `src/governor/daemon.py` | JSON-RPC 2.0 over stdio/Unix socket (75 methods). Primary surface for Maude/Clerk/Phosphor. |
| MCP Server | `src/governor/mcp_server.py` | Model Context Protocol for Claude Desktop |
| MCP Gateway | `libs/mcp_governor/` | Policy-enforcing proxy between any MCP client and any tool server |
| Runtime Supervisor | `src/governor/runtime/` | Supervised sessions over external agent CLIs (Claude Code, Gemini CLI) |

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
| Signal Plane | `src/governor/signal_store.py` | SQLite projection cache over instrumentation JSONL |
| Instrumentation Spine | `src/governor/signals/` | v2.4 signals (Phase A/B/C/D): exposure, suppression, sigma rate, capture diagnostic, decision lag, posterior shift, replay harness, calibration, regime preflight |
| Correlator Telemetry | `src/governor/correlator_telemetry.py` | Capture detection, K-vector, regime classification |
| Semantic Stability | `src/governor/semantic_stability.py` | Perturbation-based conditioning audit |

### Runtime Supervision

Governor is no longer just a kernel — it is a supervision layer for external agent CLIs. The runtime subsystem wraps Claude Code and Gemini CLI sessions, intercepts tool calls via hook integration, mediates approvals, and tracks workspace promotion.

| Component | Path | Description |
|-----------|------|-------------|
| Event Bus | `src/governor/runtime/events.py` | Canonical event stream, JSONL persistence, monotonic seq |
| Supervisor | `src/governor/runtime/supervisor.py` | Session lifecycle FSM, intervention queue, auto-approve policy |
| Promotion | `src/governor/runtime/promotion.py` | Workspace diff detection, approve/reject/revert |
| Claude Code Adapter | `src/governor/runtime/adapters/claude_code.py` | Supervised mode via Unix socket hooks |
| Gemini CLI Adapter | `src/governor/runtime/adapters/gemini_cli.py` | BeforeTool/AfterTool hooks, isolated settings |

### Receipts & Authority Plane

| Component | Path | Description |
|-----------|------|-------------|
| Gate Receipts | `src/governor/gate_receipt.py` | Content-addressed decision receipts (receipt_v1) |
| Receipt Kernel | `libs/receipt_kernel/` | Standalone library: append-only hash-chained ledger, 6 constitutional invariants. Also published as `receipt-kernel` on PyPI. |
| Lane Routing | `src/governor/lanes.py` | Capability-based cascade (Lane 0/1/2/3), artifact reuse |
| Verifier Gate | `src/governor/verifier_gate.py` | Composition boundary for mechanical verification |
| Scope Governor | `src/governor/scope.py` | Locality-first policy, escalation receipts |
| Egress Gate | `src/governor/egress_gate.py` | Outbound data-flow policy (R1-R6 rule precedence) |
| Provenance Labels | `src/governor/provenance_labels.py` | Lightweight taint tracking for tool outputs |
| Intent Compiler | `src/governor/intent_compiler.py` | Structured hypothesis-collapse via templates |
| Context Manifest | `src/governor/context_manifest.py` | Prompt assembly as governed artifact |
| Context Compact | `src/governor/context_compact.py` | Loss-aware compaction with recovery store |
| Session Continuity | `src/governor/session_continuity.py` | Capsule-based session management, fork/promote |
| CI Lane | `src/governor/ci.py` | Receipt-producing CI wrapper and policy verifier |
| Git Governance | `src/governor/git_governance.py` | Integrity invariants at commit boundaries |
| Perforce | `src/governor/perforce.py` | Integrity invariants on explicit authority substrate |
| Interferometry | `src/governor/interferometry.py` | Multi-model claim comparison, parallel + serial deliberation |
| External Constraints | (planned) | Bind claims to Wikidata/Wikipedia/Scholar snapshots |

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

## The Constellation

Governor is one star, not a monolith. It sits in a constellation of independent tools that can each be used standalone. The constitutional rule:

> **Governor may coordinate independent tools, but it must not be the reason they are usable.**

The pieces are **loosely coupled, semantically aligned** — peers under a shared constitutional vocabulary, not stages in a pipeline. They are coupled by *meaning* more than by *mechanism*. Governor does not call NQ to govern. NQ does not call Governor to witness. They share a grammar (Δt, regimes, claims, receipts, admissibility) and selective interfaces, and that is all the coupling that should exist.

Each repo below works on its own. Governor enters when an action needs mediation, when authority crosses a boundary, or when receipts are required.

### In-tree libraries (`libs/`)

| Repo | Role | Standalone? |
|------|------|-------------|
| `libs/receipt_kernel/` | Append-only hash-chained event ledger, 6 constitutional invariants, blob store with redaction + retention. | Yes (PyPI: `receipt-kernel`) |
| `libs/mcp_governor/` | Policy-enforcing MCP gateway: client ↔ gateway ↔ tool server, with receipts. | Yes (depends only on `receipt_v1`) |

### Sibling repos (`~/git/`)

| Repo | Role | Relationship to Governor |
|------|------|--------------------------|
| `nlai` | Standalone epistemic kernel (PyPI: `nlai`). Zero deps, stdlib only. | Independent. Not "Governor Lite," not a required submodule. |
| `continuity` | Per-project governed memory: observe → commit → rely_on. SQLite-backed, MCP-served. | Memory substrate. Governor mediates cross-project rely-on, not memory itself. |
| `custody` | Secret metadata + governed operations (catalog, classes, allowed ops, leases). | Authority plane for secret use. Governor decides whether an operation may execute. |
| `standing` | Workload identity + authorization (Rust). HMAC-SHA256 WorkloadId tokens. | Identity substrate. Answers "who is asking from where" before Governor decides. |
| `dossier` | PR review provenance, Δt-aware review grants, stale approval detection. | Review-time governance. Independent of runtime governance. |
| `audit` | Code audit tool ("IAM for pull requests"). | Independent. |
| `wlp` | Witness Ledger Protocol — wire format for federable receipts. | Cross-project receipt fabric. Governor emits, WLP federates. |
| `maude` | Textual TUI operator console. Talks to daemon via JSON-RPC. | Client of Governor daemon. |
| `clerk` | Electron desktop app. | Client of Governor daemon. |
| `gov-webui` (Phosphor) | FastAPI + SPA web UI. | Client of Governor daemon. |
| `vscode-governor` | VS Code extension. CLI-based, not daemon-dependent. | Client of `governor` CLI. |

### How they compose

```
   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │  continuity  │    │   custody    │    │   standing   │
   │ (memory)     │    │ (secrets)    │    │ (identity)   │
   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
          │                   │                    │
          │  query / observe  │  catalog lookup    │  attest
          ▼                   ▼                    ▼
        ╔══════════════════════════════════════════════╗
        ║              Governor (gate)                 ║
        ║  Mediates ACTION across these substrates     ║
        ║  Emits receipts; never owns their state      ║
        ╚══════════════════════════════════════════════╝
                            │
                            ▼
                   ┌─────────────────┐
                   │  WLP receipts   │  (federation layer)
                   └─────────────────┘
```

The boundary is sharp: **read/query/observe** does not need Governor. **Action that crosses authority** does.

### The four-piece map

Beyond the operator-facing tools above, the constellation has a deeper four-piece structure for *how the work gets thought about*:

| Piece | Role |
|---|---|
| **Lean / papers** | Semantic hardening, theorem pressure, model discipline. Sharpens the categories. Not a runtime. |
| **Z3 / verifier sidecar** (`src/governor/verifier_gate.py`) | Bounded admissibility — local constraint discharge at decision time. An *instrument* Governor may consult, not its logical core. |
| **Governor** | Authority, enforcement, receipts. Decides what may happen and records what did. |
| **NQ** (sibling repo, monitoring) | Witness, regime detection, finding. Observes substrate and classifies failure modes. Does not authorize. |

These are peers, not stages. None of them is the upstream compiler for the others. Sometimes Governor calls the verifier. Sometimes the verifier runs offline. Sometimes the formal work clarifies a term both projects use. Sometimes none of them touch and they still stand on their own. That is what loose coupling actually looks like.

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
