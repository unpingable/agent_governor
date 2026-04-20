# Governor Client Surface Map

> **Status:** Work in progress, 2026-04-20. Scaffolding first, detail accretes.
>
> **Companion docs:**
> - `CLIENT_ECOSYSTEM.md` — narrative per-client roadmap (VS Code, WebUI, Maude, Guvnah)
> - `specs/gaps/OPERATIONAL_SLA.md` — two-path contract (decision vs. evidence)

## Purpose

Crosswalk between governor's shipped coordination primitives and their
exposure to external clients. Prevents phantom-greenfield proposals by
making the existing surface legible.

Each primitive has a row. Each row answers:

- Is it reachable via daemon RPC?
- Is it reachable via MCP?
- Which clients plausibly need it?
- Does it land on the decision path or the evidence path?

## Non-Goals

- Not a new specification. No new primitives are proposed here.
- Not a roadmap. This maps what exists; it does not commit to what ships next.
- Not a complete inventory. Rows get filled in as they become load-bearing.
- Not a replacement for `CLIENT_ECOSYSTEM.md` — that doc is per-client narrative; this one is per-primitive crosswalk.

## Section 1 — Already Shipped Coordination Primitives

Pulled from `.claude/rules/implementation-summary.md`. This is the set
that any "we need multi-agent coordination" proposal must be checked
against before scoping new work.

| Primitive | Module | CLI | Notes |
|---|---|---|---|
| Multi-agent tasks, leases, dispatch | Multi-Agent v2 | `governor task {claim,heartbeat,complete,list,cancel}` | SQLite + WAL, epochs, permissions |
| Agent registration | Multi-Agent v2 | `governor agent {register,list,permissions,heartbeat}` | |
| Quorum state machine | `quorum.py` | `governor quorum {status,vote,policy,policies,history}` | 8 gates, Δt stability, risk levels |
| Independence scoring | `independence.py` | `governor independence {score,check}` | Jaccard, anti-cheat, quorum-integrated |
| Sybil resistance | `sybil.py` | — (integrated into quorum Gate 5) | Bloc detection, Neff, origin budget |
| Dissent ledger | `dissent.py` | — | First-class objections, commit gating |
| Agent roles | — | — | PROPOSER/RETRIEVER/FALSIFIER/SYNTHESIZER; quorum Gate 8 |
| Runtime supervisor | `runtime/` | `governor runtime {launch,fork,list,events,interventions,approve,deny,promotion,diff,promote,reject,kill,cleanup}` | Claude Code + Gemini CLI adapters |
| Append-only event log | `receipt_kernel` | — (library) | Hash-chained, 7 event types, retention |
| Receipt store + evidence | `gate_receipt.py` | `governor receipts {...}` | Content-addressed, JSONL + sharded blob store |
| Session continuity | `session_continuity.py` | `governor session {create,list,resume,fork,checkpoint,promote,delete}` | Capsule-based, three-layer model |
| Signal plane | `signal_store.py` | `governor signals {list,tail,explain,stats,rebuild,preflight}` | SQLite projection over JSONL |
| MCP server | `mcp_server.py` | `governor mcp {serve,tools,call}` | 21 tools, claim/receipt surface |
| Governor daemon | `daemon.py` | `governor serve [--stdio|--socket]` | JSON-RPC 2.0, ~80 methods |

If a coordination proposal names a primitive that already has a row
here, the task is "expose / connect / extend" — not "design / build."

## Section 2 — Daemon Surface vs. MCP Surface

As of 2026-04-20: daemon exposes ~80 RPC methods across the families
below. MCP server exposes 21 `governor_*` tools. The gap is real and
substantial.

| Family | Daemon RPC | MCP exposed? | Notes |
|---|---|---|---|
| `governor.*` | `hello`, `now`, `status`, `methods`, `selfcheck` | partial | `status` exposed |
| `sessions.*` | `list`, `create`, `delete`, `get` | no | |
| `intent.*` | `templates`, `schema`, `validate`, `compile`, `policy` | yes (via `governor_get_intent`, `governor_set_intent`) | |
| `receipts.*` / `receipts_v1.*` | `list`, `detail`, `verify` | no | |
| `chat.*` | `send`, `stream`, `models`, `backend` | no | |
| `chain.*` | `evaluate`, `preflight`, `record`, `status`, `rules`, `reset` | no | |
| `claims.*` | `list`, `detail`, `for_receipt`, `window`, `stats` | partial (`governor_claim_status`) | |
| `policy.*` | `evaluate`, `info`, `capabilities` | no | |
| `scope.*` | `status`, `check`, `escalate`, `grants` | no | |
| `stability.*` | `status`, `audit`, `history`, `probe` | no | |
| `lanes.*` | `route`, `explain`, `status` | no | |
| `signals.*` | `query`, `get`, `tail`, `stats`, `preflight` | no | |
| `constraint.*` | `status`, `check` | partial (`governor_check_text`, `governor_check_file`) | |
| `trace.*` | `tail` | no | |
| `runtime.session.*` | `create`, `launch`, `get`, `list`, `events`, `pause`, `resume`, `kill`, `fork` | no | |
| `runtime.intervention.*` | `list`, `resolve` | no | |
| `runtime.promotion.*` | `get`, `diff`, `resolve` | no | |
| `runtime.budget.*` | `get` | no | |
| `task.*` | `claim`, `heartbeat`, `complete`, `list`, `cancel` | no | **Lifted to daemon RPC 2026-04-20.** Backed by `reservations.py` (shared by CLI + RPC). Mutating: claim/heartbeat/complete/cancel. Read-only: list. |
| `quorum.*` / `independence.*` / `dissent.*` | CLI-only (no daemon RPC registered yet) | no | **TBD: lift to daemon RPC before cross-project quorum work.** |

`task.*` is now reachable over daemon RPC — Nightshift and NQ can use
work-reservation primitives without subprocessing the CLI. The shared
`reservations` module ensures CLI and RPC paths cannot drift.

`quorum.*`, `independence.*`, `dissent.*` remain CLI-only. These are
not blockers for the immediate Nightshift/NQ pain (collision avoidance
via leases) but will be needed if cross-project consensus or formal
review becomes a transition class.

## Section 3 — Client Profiles

### Maude / VS Code / WebUI / Guvnah

Covered in `CLIENT_ECOSYSTEM.md`. Not re-enumerated here. All current
v2 clients consume the daemon directly (UDS or stdio), not MCP.

### Nightshift

**Repo:** `~/git/scheduler` (Night Shift — ops work with Claude)

**Role candidate:** Client of governor's admission/quorum/runtime
surface. Consumes runtime session supervision for ops tasks;
consumes intent compilation and receipts for post-hoc accountability.

**Likely verb needs:**

- `runtime.session.*` — supervised ops sessions
- `runtime.intervention.*` — approve/deny tool calls
- `runtime.promotion.*` — workspace change gating
- `intent.{compile,policy}` — structured ops intent
- `receipts.*` — post-hoc accountability
- `chain.evaluate` / `chain.preflight` — pre-execution checks
- `scope.{check,escalate}` — bounded authority per ops task
- TBD: does Nightshift need its own task queue, or does it use `task.*` once that's RPC-exposed?

**Path mix:** Mostly **decision path** for interventions and
promotions (user/ops is waiting). **Evidence path** for receipt
listings and trace tail. TBD: concrete transitions to be filled in as
Nightshift ops work is specified.

### NQ

**Repo:** `~/git/notquery` (diagnostic monitor, SECRET)

**Role candidate:** Read-mostly client. Consumes signal/correlator/stability/regime
surface for monitoring; does not write transitions.

**Likely verb needs:**

- `signals.{query,tail,stats,preflight}` — signal plane reads
- `stability.{status,history}` — conditioning audit state
- `receipts.list` — recent decisions
- `trace.tail` — live event stream
- TBD: correlator methods if exposed (`correlator.{status,history,kvector}`)

**Path mix:** Almost entirely **evidence path**. No live gating
required; NQ observes, it does not admit.

### Operator UI (future)

**Role candidate:** Human-facing dashboard for adjudicating
promotions, disputes, pending violations, and exceptions across
supervised sessions.

**Likely verb needs:**

- `runtime.intervention.resolve` — human approve/deny
- `runtime.promotion.resolve` — human promote/reject
- `commit.{pending,fix,revise,proceed,exceptions}` — pending-violation workflow
- `sessions.*`, `receipts.*` — read surfaces

**Path mix:** **Decision path** for resolutions; **evidence path** for
dashboards.

## Section 4 — Transition Classes

From chatty's sketch, kept as a vocabulary for path classification.
Not all primitives fall cleanly into one class; many transitions mix.

| Class | Examples | Typical path |
|---|---|---|
| Publication | artifact publish, claim propose, receipt emit | Decision path (caller waits on confirmation) |
| Verification | quorum vote, independent verifier review | Evidence path (can be async) |
| Promotion | artifact `published`→`verified`→`promoted`, runtime workspace promote | **Decision path** (blocks downstream work) |
| Execution | runtime tool call approve, patch apply | **Decision path** (strict fail-closed) |
| Invalidation | artifact invalidate, claim retract, dissent raise | Mixed — immediate effect on consumers but often async from producer |

## Section 5 — Path Classification Notes

`specs/gaps/OPERATIONAL_SLA.md` already defines the two-path contract:

- **Decision path:** fast, p99 budget in ms, fail-closed or fail-open+debt-receipt. Policy freshness and index lag are first-class concerns.
- **Evidence path:** slower, accountable, debt tracking. Used for post-hoc admissibility, forensics, dashboards.

Per-primitive classification remains **TBD** until Nightshift's
concrete ops transitions are specified. The SLA spec is the right
place to annotate those classifications when they land — this doc
points at the rows that need updating; it does not duplicate the SLA
machinery.

## Open Items

- [ ] Lift `task.*`, `quorum.*`, `independence.*`, `dissent.*` to daemon RPC. Prerequisite for any cross-project client use.
- [ ] Decide MCP exposure scope. Is MCP the canonical cross-project surface, or is the daemon (UDS/stdio) enough and MCP stays claim-and-receipt focused?
- [ ] Concrete Nightshift ops transitions to classify (decision vs. evidence).
- [ ] Confirm correlator RPC surface (`correlator.*`) and whether NQ needs access.
- [ ] Decide whether Nightshift/NQ/other projects share a single governor daemon instance or each talk to their own, and what the cross-instance contract is if they don't share.
- [ ] Tenant/principal model for cross-project callers (touches `CLIENT_ECOSYSTEM.md` v3 transport posture).
