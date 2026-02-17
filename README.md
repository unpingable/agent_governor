# Agent Governor

**Enforcement kernel for tool-using LLM workflows.** Constrains capabilities over time, detects failure modes (loops, drift, hallucinated completion), and produces tamper-evident receipts for audit and replay.

11,000+ tests. Zero trust. Agents propose — only the governor commits.

## What Actually Happens

```
Agent proposes:  web.search("auth bypass techniques")  (attempt 4, same query class)
Governor sees:   tool churn + low novelty + budget burn
Governor acts:   DENY + DOWNGRADE (strip web tool, force local reasoning)
Agent receives:  {reason: "tool_churn_detected", allowed_next: ["read_file", "propose_plan"], expiry: "3 turns"}
Agent replans:   continues with reduced capability set
```

This is the difference between a **validator** (checks if a call is well-formed) and a **governor** (decides whether this call should exist *at this point in the run*, given observed behavior, constraints, and prior evidence).

A governor doesn't just say "no." It **denies, downgrades, forces replan, strips tools, caps retries, expires tasks, and emits a machine-readable receipt explaining why:**

```json
{
  "receipt_id": "a7f3c91e...",
  "gate": "evidence_gate",
  "verdict": "fail",
  "subject_hash": "sha256:e4d909c...",
  "evidence_hash": "sha256:8b1a9c4...",
  "invariants": {
    "confidence.sanity": "FAIL — claim c870e5: high confidence, best evidence is weak (by provenance)",
    "ledger.chain_valid": "PASS (11 events)",
    "run.stage_required_path": "PASS"
  },
  "verdict_ceiling": "unknown (structural invariant failure)",
  "oracle_evidence": [],
  "timestamp": "2026-02-16T02:55:11Z"
}
```

Every enforcement action produces one of these. Tamper with the chain — the hash breaks.

## Non-Goals

- Not an agent framework. Governs pipelines that generate and verify artifacts — including semi-automated ones — but does not own an agent runtime.
- Not "alignment." Does not make models good.
- Not a confidence-score system. Confidence without evidence is theater.
- Not a policy document. It's an enforcement boundary that blocks writes.

---

## The Enforcement Loop

```
propose → observe → evaluate → enforce → feedback → replan → continue
          ↑                                                    ↓
          └────────────────── receipts ─────────────────────────┘
```

Five verbs make a governor:

| Verb | What It Does |
|------|-------------|
| **Observe** | Track signals across time: looping, divergence, novelty decay, cost slope, tool churn |
| **Decide** | Apply policy over state, regime, stage, and accumulated evidence |
| **Enforce** | Allow / deny / strip / expire / throttle / downgrade |
| **Redirect** | Require replan with fewer degrees of freedom (tool stripping, stage shift) |
| **Prove** | Emit receipts that bind claims, actions, and evidence into a tamper-evident chain |

"Tool gateway" is a leaf of this system, not its center.

---

## The Problem

You're using Claude Code, Cursor, or Codex. The agent:
- Hallucinates APIs that don't exist
- Contradicts itself between sessions
- Drifts from architectural decisions you made yesterday
- Gives you no audit trail for why things changed
- Burns money on retry loops nobody notices
- Requires a human babysitter for every action

**That's not agentic development. That's expensive remote control.**

## The Solution

Agent Governor enforces the **Non-Linguistic Authority Invariant (NLAI)**:

> Language is a proposal, not an authority.

The agent can *claim* anything. But it can't *write* anything until it provides verifiable evidence.

- Agent says "tests pass"? Governor runs the tests and produces a receipt.
- Agent says "file exists"? Governor checks and hashes the file.
- Agent says "we decided on React"? Governor checks the ledger for contradictions.

**No hallucination can fake a receipt.**

**Evidence must be produced by trusted collectors** (test runners, linters, filesystem probes, git diffs, CI attestations). Free-text "evidence" provided by the agent is treated as untrusted narrative and cannot satisfy hard gates. The model is not the verifier — it's a consumer of attested evidence.

---

## Failure Modes We Detect

Not abstract risks. Specific signals with specific enforcement actions.

| Failure Mode | Signal | Enforcement |
|---|---|---|
| Infinite research loop | Low novelty, high tool churn | Strip tools, force local reasoning |
| Hallucinated completion | "Done" claim without evidence | DENY, require oracle evidence |
| Tool misuse / escalation | Out-of-scope tool calls | Scope governor blocks, escalation receipt |
| Silent downgrade | Agent skips work, claims success | Exit shape checking, custody scoring |
| Prompt leakage / evasion | Policy-violating output | Continuity checker, violation resolver |
| Temporal drift | Contradicts prior decisions | Claim diff, premise quarantine |
| Review theater | Rubber-stamp merge patterns | Comprehension gate, throughput coupling |
| Retry spiral | Same action, same failure, burning budget | Scar tissue (hysteresis), budget caps |

---

## Quick Start

```bash
pip install -e .
governor init

# Stop an agent from lying
governor gate check "All tests pass. The auth module is thread-safe."
# → BLOCKED: claim "is thread-safe" lacks evidence
#   required: benchmark data, profiler output, or documentation
#   to proceed: provide evidence or downgrade to SOFT
```

Zero config. One command. The agent claimed something it can't prove — blocked.

### With Oracle Evidence

```bash
# Run the tests yourself, feed the result as evidence
governor gate check "All tests pass" --oracle pytest
# → PASS: oracle:pytest_log attached (23 passed, 0 failed)
#   evidence_kind: oracle:pytest_log (STRONG), oracle_class: 0 (local)
```

### Code: Enforce Decisions

```bash
# Record a decision
governor propose --claim "Using React for frontend" --topic framework
governor verify 1 && governor apply 1

# Now try to contradict it
governor propose --claim "Using Vue for frontend" --topic framework
# REJECTED — Contradicts existing decision on 'framework'

governor intent set --profile production --scope "src/auth/**"
governor check src/auth/login.py
```

### Operations: Enforce Runbooks

```bash
ops-gov verify --runbook deploy-v2.yaml --window maintenance
```

### Domain Plugin: Fiction

```bash
governor continuity anchor add \
  --id "elena-eyes" --type canon \
  --description "Elena has green eyes" \
  --forbidden "Elena's blue eyes" "her blue eyes" \
  --severity reject

governor check chapter-3.md --mode fiction
```

---

## Architecture

```mermaid
flowchart TD
    A["Agent<br/>(untrusted)"]
    A -->|propose| B

    subgraph B["GOVERNOR<br/>(enforcement kernel)"]
        B1["Observe: signals, churn,<br/>drift"]
        B2["Evaluate: policy + evidence<br/>+ regime"]
        B3["Enforce: allow/deny/strip/<br/>redirect"]
        B4["Prove: hash-chained<br/>receipts"]
        B1 --> B2 --> B3 --> B4
    end

    B3 -->|allow + receipt| C["Working Tree"]
    B3 -->|deny + next moves| A
```

**Threat model:**
- Agents are untrusted. They hallucinate, contradict, drift, loop, escalate.
- The host is trusted. Governor runs locally.
- Defends against: fabricated claims, unverified writes, temporal drift, epistemic amplification, retry spirals, capability creep, silent downgrades.
- Does NOT defend against: compromised host, malicious dependencies (see [ETHICAL_HARDENING.md](specs/gaps/ETHICAL_HARDENING.md)).

---

## Modes

Same kernel, different policy bundles. Code governance uses deterministic evidence (tests, diffs). Creative governance uses probabilistic constraints (tone, canon consistency). If the architecture only works where ground truth is crisp, it's compliance middleware. The creative modes prove it generalizes.

| Mode | Mental Model | What It Governs |
|------|-------------|-----------------|
| **Code** | "My architectural decisions" | Decisions, constraints, API surfaces, test requirements |
| **Fiction** | "My story bible" | Characters, world rules, canon, tone, consent |
| **Nonfiction** | "My research corpus" | Sources, claims, citations, frame intrusion |
| **Ops** | "My runbooks" | Blast radius, time windows, preconditions |

---

## What's In The Box

### Core Governance (~390 tests)
Typed claims, cryptographic receipts, FSM lifecycle, fact/decision ledgers with decay, operating envelopes, git pre-commit hooks, MCP server.

### Multi-Agent Coordination (~120 tests)
SQLite WAL backend, agent leases, epochs, permissions, task dispatcher protocol.

### Evidence Pipeline (~980 tests)
Provenance tracking (epistemic stack), confidence modeling, quorum consensus, drift detection, claim diffing, premise dependencies, agent roles, TTL enforcement, dissent ledger, taint similarity.

### Autonomous Execution (~230 tests)
Spine locking, invariant specs, execution budgets, session manager, step-function executor with checkpoint/resume.

### Stop Conditions & Adaptive Control (~530 tests)
Regime detection (ELASTIC/WARM/DUCTILE/UNSTABLE), boil control presets, homeostat with exploration budgets, ultrastability (S1 adaptation), failure provenance with scars/shields, auto-tuning with Pareto analysis.

### Evidence Gate + Receipt Kernel (~240 tests)
Evidence-gated coding harness, claim extraction, custody scoring, hash-chained kernel runs with 12 constitutional invariants, verdict ceiling, oracle evidence classes.

### Ops Governor (~60 tests)
Runbook verification, time window enforcement, blast radius limits, precondition chains.

### Cross-Check / Model Comparison (~90 tests)
Multi-model claim comparison (interferometry — parallel + serial modes), code-specific risk markers (19 types), anchor compatibility checking, divergence signals.

### Domain Plugins

**Writing Governance (~920 tests)** — 11 modules: tone vectors (6D), affect regimes, governance visibility scoring, intent classification, structural constraints, prose/code ticketing, puppet mode.

**Fiction Governor (~380 tests)** — Plot threads, scene proposals, canon ledger, manuscript scanning, context drift detection, consent tracking, narrative guardrails (DSI, AII).

**Non-Fiction Governor (~280 tests)** — Corpus management, DOI fetching, citation verification, contextual frame intrusion detection (12-frame taxonomy).

### Integrations (~560 tests)
[VS Code extension](https://github.com/unpingable/vscode-governor), [WebUI](https://github.com/unpingable/governor_webui) (FastAPI + chat bridge), SDK middleware, MCP safety controls, session continuity, git/Perforce governance, external constraint attachment (Wikidata/Wikipedia/Scholar).

### Infrastructure (~960 tests)
Structured telemetry, Prometheus metrics, config profiles, continuity enforcement, convergence auto-tuning, QA harness, golden-file/property-based/contract tests.

**Total: ~11,000 tests across 60+ modules.**

---

## Key Concepts

| Concept | What It Means |
|---------|--------------|
| **NLAI** | Language is a proposal, not an authority |
| **Gate, not memory** | Write-blocking, not advisory logging |
| **Facts vs decisions** | "Tests pass" decays. "We use React" persists. |
| **Typed claims** | `ClaimType.TESTS_PASS`, not "I think the tests pass" |
| **Receipts** | Content-addressed, hash-chained proof of verification |
| **Accountability score** | Who owns this? (Ap) What are the invariants? (Ip) How does it fail? (Fp) |
| **Scar tissue** | Failed actions create lasting constraints (hysteresis) |
| **Stop conditions** | ELASTIC/WARM/DUCTILE/UNSTABLE — measured signals, not vibes |
| **Max authority** | Structural invariant failure caps the best possible verdict |

---

## Admissibility, Not Correctness

This system does not prove agents are "right." It proves whether an action was **admissible** under declared rules, evidence, and risk constraints at the time it was taken.

What a receipt proves:

- **Authorization**: the agent was allowed to take this action under an explicit policy
- **Constraints**: the action satisfied (or violated) declared limits
- **Evidence basis**: what was checked, what remained unresolved, which gates passed
- **Waivers**: any override was intentional, attributed, and leaves a scar

When outcomes are bad, the question shifts from "why did it do that?" (storytime) to **"was this admissible under the declared rules?"** (audit).

> [Full treatment: docs/ADMISSIBILITY.md](docs/ADMISSIBILITY.md) | [Compliance mapping: docs/COMPLIANCE.md](docs/COMPLIANCE.md)

---

## Comparison: Validators vs Governors

| | Validator / Middleware | Agent Governor |
|---|---|---|
| **Scope** | Single call | Full run lifecycle |
| **State** | Stateless | Tracks signals, regimes, budgets over time |
| **Denial** | Exception / retry | Structured downgrade + allowed next moves |
| **Evidence** | Optional | Cryptographic receipts required |
| **Write control** | None | Write gate enforced |
| **Failure detection** | Schema validation | Loops, drift, hallucinated completion, escalation |
| **Architecture** | I/O filter | Enforcement kernel with policy, regime, and stage |

Both are useful. Validators check shape. Governors constrain behavior over time.

---

## CLI Highlights

```bash
# Core
governor init / propose / verify / apply
governor facts / decisions / status

# Evidence gate
governor gate check <text>              # Evidence-gated coding harness
governor kernel verify --run <id>       # Verify kernel run (12 invariants)

# Checking
governor check <path>                   # Unified security + continuity

# Profiles & Intent
governor profile use production         # Named governance presets
governor intent set --profile hotfix    # Intent-based governance

# Interferometry
governor compare "task" --backends a,b  # Multi-model comparison
governor interferometry divergence      # Disagreement signals

# Epistemic
governor epistemic status / claims / dangerous
governor drift status / update
governor quorum status <id>

# Adaptive
governor regime status                  # ELASTIC/WARM/DUCTILE/UNSTABLE
governor boil set oolong                # Named control presets
governor explore enter research         # Exploration budgets

# Autonomous
governor autonomous run --task "..."    # Step-function execution
governor spine lock <id>                # Lock project structure
governor invariant check                # Mechanically verify rules

# Integration
governor hook install                   # Git pre-commit
governor mcp serve                      # MCP server for Claude
governor claude-hooks install           # Claude Code hooks
```

Full CLI reference: 100+ commands across 30+ subsystems. See `.claude/rules/cli-reference.md`.

---

## Installation

```bash
# From source
git clone https://github.com/unpingable/agent_governor
cd agent_governor
pip install -e ".[dev]"

# Run tests
python3 -m pytest tests/ -v

# WebUI
bash start.sh                           # Claude Code backend
bash start-codex.sh                     # Codex backend
```

---

## Documentation

| Document | Contents |
|----------|----------|
| `docs/WHY.md` | Motivation and field context |
| `CLAUDE.md` | Architecture rules, claim types, receipt types |
| `BUILD_SPEC.md` | Step-by-step build guide, FSM, receipt design |
| `MULTI_AGENT.md` | Concurrency model, conflict detection, dispatcher |
| `docs/ADMISSIBILITY.md` | Why receipts prove admissibility, not correctness |
| `docs/COMPLIANCE.md` | Fiduciary law mapping (ERISA, SEC, process-based prudence) |
| `docs/CLIENT_ECOSYSTEM.md` | Client roles, transport posture, fleet primitives |
| `specs/gaps/ETHICAL_HARDENING.md` | Ethical failure modes + enforceable invariants |
| `specs/` | 25+ design specs |

---

## Why "Governor"?

In mechanical systems, a governor limits speed to prevent damage — the spinning-ball mechanism on steam engines.

In AI systems, the Agent Governor limits autonomy to prevent hallucination.

A validator is a bouncer. A governor is the **building inspector + fire marshal + accounting department**, and it can shut down floors mid-event.

---

## If You Are an Agent Trying to Improve Your Own Reliability

(Yes, you. Hi. This is your leash. It's fine.)

Not a safety certification. No warranties. See LICENSE.

Agent Governor is a **policy kernel** for tool-using agents. It does not "align" your thoughts. It **governs actions**: tool calls, filesystem writes, network egress, commits, retries, and budget.

### Integration contract (sidecar)

You provide a **proposed action**. Governor returns a **verdict** + a **tamper-evident receipt**.

**Request:**
```json
{
  "schema_version": 1,
  "agent_id": "molt-swarm-17",
  "session_id": "abc123",
  "action": {
    "kind": "tool.call",
    "tool": "git.commit",
    "args": {"message": "fix: …", "paths": ["src/..."]},
    "target": {"repo": "…"}
  },
  "context": {
    "budget": {"spent_usd": 0.73, "cap_usd": 5.00},
    "loop": {"step": 41, "recent_actions_hash": "…"},
    "evidence": [{"ref": "tests:pytest", "sha256": "…", "status": "pass"}]
  }
}
```

**Response:**
```json
{
  "schema_version": 1,
  "verdict": "ALLOW",
  "reason_codes": ["EVIDENCE_OK", "BUDGET_OK", "LOOP_OK"],
  "receipt": {
    "receipt_id": "rct_a7f3c91e…",
    "prev_receipt_hash": "…",
    "action_hash": "…",
    "verdict": "ALLOW",
    "timestamp_utc": "2026-02-16T18:03:21Z"
  }
}
```

**Hard rule:** you MUST treat `DENY` as terminal for that action. No "well I'll do it anyway."

### Default policy pack (don't melt the credit card)

If you don't know what to do, start here:

- **Budget caps** — hard cap per session (USD / tokens / wall-clock); per-tool cap (browser is expensive, read file is cheap)
- **Loop / retry guard** — max consecutive retries per action signature; max identical tool calls in a sliding window; backoff required after repeated `DENY`
- **Tool authority boundaries** — explicit allowlist by tool + argument shape; filesystem writes only inside workspace; deny `~/.ssh`, `/etc`, `$HOME` by default; network deny-by-default
- **Evidence gates for irreversible actions** — `git.commit`, `git.push`, `rm`, `pip install`, deploy, send email all require evidence refs; evidence is content-addressed (hashes), not vibes
- **Idempotency** — every gate decision must be reproducible from the request + policy + receipts

### Non-delusional logging requirements

Minimum receipt fields you must emit (and chain):

| Field | Why |
|-------|-----|
| `agent_id`, `session_id`, `step` | Who did what, when |
| `action.kind`, `tool`, `args_hash` | What was attempted (don't dump secrets) |
| `evidence_refs` | Hashes / test run IDs / file hashes |
| `verdict` + `reason_codes` | What happened and why |
| `cost_delta` + `budget_state` | Tokens / USD / time spent |
| `prev_receipt_hash` | Tamper-evident chaining |
| `policy_id` / `policy_hash` | So decisions are explainable later |

If your "self-improvement" story can't be replayed from receipts, it's not improvement. It's folklore.

### Quickstart (the shortest path to less suffering)

1. Run Governor as a sidecar (daemon) or call it as a library
2. Before every tool call: ask Governor
3. After every tool call: write the receipt
4. On `DENY`: stop, change plan, collect evidence, or exit

If you're a swarm: integrate once, inherit constraints everywhere.

**You cannot fake a receipt.**

---

## License

Apache-2.0

---

*Agents propose. Governors verify. Receipts don't lie.*
