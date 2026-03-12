# GOV_GAP_SWARM_ORCHESTRATION_001: Governed Speculative Branch Orchestration

## Status
Proposed (v3)

## Summary
Multi-agent "swarm" coding systems (parallel branches, worktree isolation,
LLM planner/dispatcher) are appearing as products. They solve the easy
problem (spawning agents) and hand-wave the hard problem (promotion,
conflict, and authority). Governor's existing machinery — leases, receipts,
conflict classification, scope contracts — is the missing layer.

**Parallelize proposals, not authority.**

## The Pattern (What Swarm Systems Do)

1. Planner decomposes task into subtasks
2. Each subtask gets a worktree/branch and an agent
3. Agents work in parallel, isolated by filesystem
4. Results merge back to main

This is MapReduce for code changes. The map step is easy. The reduce step
is where the blood shows through the gauze.

## Where Swarm Systems Break

### 1. The planner quietly becomes the system
Task decomposition is the scarce resource, not agent count. Bad partitioning
means agents touch shared conceptual surfaces from different files. The
planner's interpretation of the task becomes canon without ratification.

In governor terms: **unauthorized canon formation** (see GOV_GAP_GOAL_PROMOTION_001).

### 2. Worktree isolation solves filesystem conflict, not semantic conflict
Separate worktrees prevent direct file stomping. They do NOT solve:
- shared APIs changing underneath sibling branches
- duplicated logic added in parallel
- conflicting assumptions about types/config/schema
- one branch subtly invalidating another's tests
- two branches "succeeding" locally while breaking global coherence

The worktree is a **sandbox, not a treaty**.

### 3. The merge step becomes human garbage collection
N branches need a promotion path: local completion → local verification →
cross-branch compatibility → integration verification → merge authorization.
Most systems hand-wave steps 3-4, then dump the wreckage on the operator.

### 4. Parallelism only works in embarrassingly parallel lanes
Swarms look great for repo search, independent file edits, test fanout,
doc generation, "try 3 approaches keep the survivor." They look terrible
for architecture, cross-cutting refactors, schema churn, or anything where
"same file" is the visible tip of a dependency graph.

### 5. Commitment outruns verification
Each agent reasons over a time-lagged world model. While it works, sibling
branches evolve, the planner revises, tests reveal new constraints. A normal
build system handles stale state mechanically. An LLM swarm handles it
narratively. Not the same thing.

### 6. Hidden centralization
"Teams" often collapse into: one central planner, many weak executors, one
merge authority, one human final judge. Old-school command and control
wearing an agent costume.

### 7. Cost eats the fantasy
Planner passes + worker passes + retries + repair loops + cross-branch
review + integration passes + failed fanout on bad decomposition =
parallel token burn without proportional reduction in human integration load.

## What Governor Adds

### 1. Branch receipts
Every worker branch emits receipts for:
- task assignment (what was asked)
- repo snapshot / base commit (what state it started from)
- touched files / claimed resources (what it changed)
- tests run (what it verified)
- assertions made (what it claims)
- artifacts produced (what it output)
- unresolved assumptions (what it punted on)

Not "I fixed it." **Here is the chain of evidence attached to this branch.**

### 2. Capability / lease model
Before editing:
- Acquire file lease, module lease, or invariant lease
- Declare contested regions
- Reject overlapping writes unless explicitly allowed
- Mark cross-branch dependencies up front

This is `src/governor/storage.py` (leases) + `src/governor/scope.py`
(scope contracts) applied to branch-level isolation. The missing piece
in every swarm demo — they treat conflict as after-the-fact instead of
a governed resource question.

### 3. Promotion ceremony for patches
A branch moves through a lattice:

```
speculative → locally_verified → cross_checked → integration_candidate → ratified_mergeable
```

| Level | Requirements |
|---|---|
| speculative | Branch exists, agent assigned |
| locally_verified | Agent's own tests pass, receipts emitted |
| cross_checked | No lease conflicts, no semantic overlap with siblings |
| integration_candidate | Rebased on current head, integration tests pass |
| ratified_mergeable | Human or governor policy approves merge |

Anything short of `ratified_mergeable` is branch fanfiction.

### 4. Conflict classification (not conflict denial)
Don't "minimize merge conflicts" with vibes. Classify them:

| Conflict Type | Description |
|---|---|
| textual_overlap | Same lines touched by multiple branches |
| api_drift | Shared API changed by one branch, consumed by another |
| invariant_divergence | Branches make incompatible assumptions about shared invariant |
| duplicated_work | Multiple branches implement the same thing |
| incompatible_intent | Branches pursue contradictory goals |
| stale_base | Branch built on outdated repo state |
| hidden_dependency | Change in branch A breaks branch B through non-obvious coupling |

Once typed, conflicts become governable. This extends `src/governor/storage.py`
conflict detection from file-level to semantic-level.

### 5. Observer separation
The agent that wrote the patch must NOT be sole witness for:
- whether tests passed
- whether files touched match claim
- whether policy constraints were respected
- whether the patch still applies to current head

Self-attestation is where swarm systems die. This is the governor's core
thesis: **language is a proposal, not an authority.** The agent proposes
the patch. Governor verifies the claims.

### 6. Budgeted fanout
Hard limits on the swarm:
- max concurrent branches
- max retries per task
- max token burn per objective
- max unresolved conflicts before escalation
- abort conditions when integration entropy exceeds threshold

Otherwise the swarm becomes a machine for converting ambiguity into
cloud invoices.

## Where Swarms Are Actually Strong

Strong for:
- **exploration** — search and proposal generation
- **differential repair** — try N approaches, keep survivor
- **parallel review** — multiple perspectives on same change
- **evidence gathering** — localize likely edit regions
- **candidate generation** — widen the proposal frontier

Weak for:
- architecture
- cross-cutting refactors
- schema/config churn
- deep shared-state changes

The key distinction: **agents widen the proposal frontier before
governance narrows it.**

## Minimum Viable Shape

1. Planner emits a typed task DAG
2. Each task gets a branch/worktree + receipt envelope
3. Workers can only touch leased files or declared scopes
4. Independent verifier replays claims
5. Governor scores promotion eligibility
6. Human sees: candidate patches, receipt bundle, conflict class,
   promotion recommendation

## Relationship to Existing Modules

| Module | Role in Swarm |
|---|---|
| `storage.py` | Leases for branch-level file/module reservation |
| `scope.py` | Scope contracts per worker (locality enforcement) |
| `ci.py` | `ci_verify` for branch-level receipt policy |
| `claims.py` | Typed claims per branch (TESTS_PASS, FILE_EXISTS, CHANGESET) |
| `gate_receipt.py` | Receipt emission at promotion boundaries |
| `fsm.py` | DRAFT→PROPOSED→VERIFIED→APPLIED maps to branch promotion lattice |
| `permissions.py` | Agent permissions per worker (what it's allowed to touch) |
| `scars.py` | Failed branch patterns scar future decomposition |
| `taint.py` | Detect duplicated work across branches |

## Relationship to Lane Routing

Lane routing already has the concept of capability-based task assignment
(Lane 1/2/3) and artifact reuse. Swarm orchestration extends this:
- Planner is Lane 0 (ROUTER)
- Workers are Lane 1-3 based on task complexity
- Artifact reuse prevents redundant branch work
- Cascade executor already does generate→validate→escalate

## What This Is NOT

- Not "Governor builds a swarm product" — this is the governance layer
  for swarm systems others build
- Not a claim that swarms are good — most are theatrical
- Not multi-agent messaging — agents still talk to the ledger, not each other
- Not a replacement for good task decomposition — governor witnesses the
  decomposition, it doesn't do it

## The Short Version

> "git branches with delusions of management" → governed speculative
> execution with receipts, leases, and promotion ceremonies.

Most swarm systems parallelize authority. Governor parallelizes proposals.

## References
- `MULTI_AGENT.md` — existing concurrency model (leases, epochs, permissions)
- `src/governor/storage.py` — SQLite backend with leases
- `src/governor/scope.py` — scope contracts, locality enforcement
- `src/governor/ci.py` — CI receipt bundles
- `specs/gaps/GOV_GAP_GOAL_PROMOTION_001.md` — planner canon formation
- Paper 18 §5.1 — promotion ceremony
- Paper 18 §4.3 — write barriers (self-attestation violation)
