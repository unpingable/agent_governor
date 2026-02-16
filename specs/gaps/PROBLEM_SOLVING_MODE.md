# Problem-Solving Mode: Controlled Divergence with Strict Validation

## Purpose

Treat "be creative to break a block" as a **stage**, not a vibe.
Creativity is a generator of plausible alternatives — mechanically
identical to hallucination. The membrane between "proposal" and
"validated output" is the entire point.

status: spec (not building yet)

---

## The Problem

Creativity and hallucination have the same shape: produce plausible
text that isn't grounded in evidence. The failure mode isn't "it got
creative" — it's **creative output crossing the membrane into
authoritative output**.

In code: tests fail, security holes ship.
In nonfiction: citations are fake, claims are ungrounded.
In fiction: less dangerous, but context drift and canon violations still apply.

---

## The Pattern: DIVERGE → VALIDATE

Two-phase loop, explicit and receipted:

### Phase 1: DIVERGE (creative)

- Generate hypotheses / approaches / outlines / refactor plans
- Output is **explicitly non-authoritative** (tagged as proposal set)
- Mode: `creative` or `mixed` (weak evidence allowed)
- Evidence kind: `proposal:*` (WEAK by policy)
- Tool access: **read-only / sandboxed introspection only**
  - No filesystem writes, no network mutations, no creds
- Budget-capped: max N hypotheses, max tokens, max retries

### Phase 2: VALIDATE / CONVERGE (boring)

- Code: compile / tests / lint / typecheck / sandbox execution
- Nonfiction: retrieval / citations + claims_map binding
- Fiction: canon check / bible consistency / continuity check
- Mode must be `factual` before FINALIZE
- Anything not validated: downgraded to UNKNOWN or dropped
- Full invariant set runs (all 12 + mode transition invariant)

**Key principle**: triggering creativity is cheap; promoting it is expensive.

---

## Stage Graph Variant

```
START → COLLECT → DIVERGE → VALIDATE → DECIDE → FINALIZE
                    ↑           |
                    └───────────┘  (retry: re-diverge on validation failure)
```

With the existing `REMEDIATE` concept for the retry loop:

```
START → COLLECT → DIVERGE → VALIDATE → DECIDE → FINALIZE
                    ↑                      |
                    └──── REMEDIATE ────────┘
```

DIVERGE is a new stage. VALIDATE reuses the existing EVALUATE semantics
but with the additional constraint that mode must be factual/mixed.

---

## What Already Exists

Most guards are already built. This feature is primarily a **wiring exercise**:

| Guard | Status | Where |
|-------|--------|-------|
| Mode-gated invariants (factual/mixed/creative) | Built | 6 hallucination invariants |
| Evidence kind → strength mapping | Built | `KIND_TO_STRENGTH`, `strength_for_kind()` |
| Claims must bind to evidence | Built | `claims.evidence_binding` |
| Output must bind to claims | Built | `output.bound_to_claims` |
| Closed-world refs | Built | `refs.closed_world` |
| Confidence sanity (provenance-based) | Built | `confidence.sanity` |
| Stage graph with hard-fail illegal transitions | Built | `StageGraph` |
| Hash-chained event ledger | Built | `SqliteReceiptStore` |
| Evidence_gate → kernel bridge | Built | `_emit_kernel_run()` |
| Mode field on RUN_START | Built | `meta.mode` |

## What's New

### 1. DIVERGE stage in stage graph

Add a new built-in graph with DIVERGE:

```python
PROBLEM_SOLVING_GRAPH = StageGraph(
    graph_id="v1_problem_solving",
    transitions={
        "START": ["COLLECT"],
        "COLLECT": ["DIVERGE"],
        "DIVERGE": ["VALIDATE"],
        "VALIDATE": ["DECIDE", "REMEDIATE"],
        "DECIDE": ["FINALIZE"],
        "REMEDIATE": ["DIVERGE"],  # re-diverge on validation failure
        "FINALIZE": [],
    },
    initial_stage="START",
    terminal_stages=frozenset({"FINALIZE"}),
)
```

### 2. Flow-level policy: `RUN_START.meta.flow_kind`

Flow kind is set by the caller/task type, NOT by the user:

- `fact_only` — code changes, compliance summaries, nonfiction publishing
- `mixed` — research, exploration with fact gate on deliverables
- `creative_ok` — fiction, brainstorming (no fact gate required)

This is routing, not permission. The user can't toggle it.

### 3. `flow.kind_singleton` invariant (immutability)

flow_kind is set once at RUN_START and CANNOT change for the run:

- Scan all events for any payload that attempts to change flow_kind → FAIL
- flow_kind is in the envelope's `meta` (chained, not just a blob)
- This closes the toggle-bypass vector: "oops, mixed now" mid-run
- No exceptions: if you need a different flow_kind, start a new run

### 4. `flow.fact_gate_required` invariant (FAIL hard, not WARN)

If `flow_kind=fact_only`:

- Final mode must be `factual`
- Required stage path must include `VALIDATE`
- Final `claims_map` / `output.bound_to_claims` must NOT cite `proposal:*` evidence kinds
- (Simple variant: DIVERGE stage disallowed entirely in fact_only flows)

This makes "solution mode" a routing feature that can exist inside a flow
without being able to *decide what kind of flow it is*.

### 5. `mode.no_unreceipted_change` invariant

New invariant: mode transitions must be explicit and receipted.

- Scan events for mode changes (in RUN_START.meta.mode and any STAGE_ADVANCE
  that changes the operating mode)
- If the mode at FINALIZE differs from the mode at the most recent DIVERGE→VALIDATE
  boundary without an explicit MODE_SET or STAGE_ADVANCE recording the change → FAIL
- Prevents creative mode leaking into factual finalization by accident

### 6. `deliverable.no_proposal_refs` invariant

Final output and claims_map must not cite `proposal:*` evidence kinds.

- Scan final `claims_map.claims[].evidence_refs` for blob refs
- Look up evidence_kind from EVIDENCE_PUT events (existing `build_blob_kind_map()`)
- Any ref with `proposal:*` kind in the final deliverable → FAIL
- Ensures proposals stay proposals; deliverables cite only validated evidence

### 7. `proposal:*` evidence kind

New evidence_kind prefix. Policy mapping:

```python
"proposal:hypothesis": EvidenceStrength.WEAK,
"proposal:approach": EvidenceStrength.WEAK,
"proposal:outline": EvidenceStrength.WEAK,
"proposal:refactor_plan": EvidenceStrength.WEAK,
```

Proposals produce UNKNOWN until validated. Not even WARN.

### 8. `deliverable:*` evidence kind

Validated output gets tagged:

```python
"deliverable:tested": EvidenceStrength.STRONG,
"deliverable:cited": EvidenceStrength.MEDIUM,
"deliverable:reviewed": EvidenceStrength.MEDIUM,
```

### 9. DIVERGE budget

Configurable caps per diverge phase:

- `max_hypotheses`: int (default 5)
- `max_tokens`: int (default 10_000)
- `max_retries`: int (default 3, then abstain/escalate)

Budget exceeded → REMEDIATE with abstain recommendation, not infinite brainstorm.

### 10. Tool sandboxing in DIVERGE

DIVERGE stage restricts tool access:

- Read-only filesystem introspection: yes
- Code execution in sandbox: yes (if available)
- Filesystem writes: no
- Network mutations: no
- Credential access: no

This maps to existing scope governor contracts (tool contracts with
required/allowed axes).

---

## Creativity Triggers (Heuristics)

When to inject DIVERGE (cheap detection, no mind-reading):

1. **Repeated oracle failures**: same test fails N times in a row
2. **Search space stuck**: same patch shape repeated (taint similarity)
3. **Empty output loops**: model can't start, repeated reframes
4. **Explicit request**: user says "try something different"

Trigger is cheap. Promotion is expensive.

---

## Diversity Without Randomness

"Be creative" is a bad knob. Better knobs:

- Force N distinct strategies: "refactor vs minimal fix vs revert"
- Force different failure hypotheses: "type error vs state mismatch vs bad assumption"
- Swap oracle order: fast static checks first, then expensive tests
- Vary context framing: different system prompts, different prior evidence subsets

---

## Abstain as Correct Outcome

Many "blocks" are "missing information." The framework must prefer
"need X" (escalate) over "invent X" (hallucinate).

Abstain produces a `DECISION` event with `action: "abstain"` and
`basis: {reason: "insufficient_information", needed: [...]}`.

---

## UI/UX Labels

- CLI: print `[PROPOSAL]` vs `[VERIFIED]` banners
- WebUI: distinct visual treatment (dashed border, yellow background, etc.)
- API: `phase: "diverge"` vs `phase: "validated"` in response metadata
- Prevents social hallucination (human reads draft as final)

---

## Mode-Specific Application

### Code (ship first — cheapest oracles)

- DIVERGE: generate approach candidates
- VALIDATE: compile + test + lint + typecheck
- Oracles are fast and cheap → iterate quickly

### Nonfiction

- DIVERGE: generate argument structure, source candidates
- VALIDATE: retrieval + closed-world citations + claims_map binding
- Requires citation bundle workflow to be comfortable first

### Fiction

- DIVERGE: generate plot alternatives, character responses
- VALIDATE: canon check + bible consistency + continuity check
- Lower stakes but context drift still matters

---

## Implementation Order

### Late v2 (minimal, local)

- Add `flow_kind` field to `RUN_START.meta` (fact_only / mixed / creative_ok)
- Add `v1_problem_solving` stage graph
- Add `proposal:*` / `deliverable:*` evidence_kind entries to KIND_TO_STRENGTH
- Add 4 invariants:
  - `flow.kind_singleton` — flow_kind immutable per run (toggle-bypass prevention)
  - `flow.fact_gate_required` — fact_only flows must VALIDATE + finalize factual (FAIL hard)
  - `mode.no_unreceipted_change` — mode transitions explicit + receipted
  - `deliverable.no_proposal_refs` — final output cannot cite proposal artifacts
- Wire into evidence_gate: when stuck-detection triggers → switch to problem_solving graph
- Budget caps as config (simple counters, not a framework)
- Required path invariant: DIVERGE must appear before VALIDATE in problem_solving runs

This is a stage graph variant + invariant requirements + flow policy. No services, no infra.

### v3 (operational, scaled)

- Hot-loaded policy bundles (tune diverge/validate thresholds per tenant)
- Executor routing: different executors for DIVERGE vs VALIDATE
- Multi-tenancy cost attribution (diverge is cheap but adds up)
- External anchoring for audit
- Remediation runner with budgets (automated retry loop)
- Live policy updates without restart

---

## Design Constraints

1. **Proposals are UNKNOWN until validated.** No WARN, no PASS.
2. **Mode transitions are explicit and receipted.** No silent drift.
3. **DIVERGE cannot touch privileged tools.** Read-only or sandboxed.
4. **Budget is hard.** Exceeded budget → abstain, not infinite loop.
5. **FINALIZE in factual mode requires VALIDATE stage.** Literal stage requirement.
6. **Proposal artifacts are separate from deliverable artifacts.** evidence_kind enforces this.

> "Problem solving mode is allowed to be wrong. Final mode is not allowed to be unproven."

---

## Dependencies

- Receipt kernel bridge (done)
- 12 invariants (done)
- Evidence provenance model (done)
- Stage graphs (done)
- Scope governor tool contracts (done)
- evidence_gate → kernel wiring (done)

All dependencies are met. This can ship whenever priorities allow.

---

## Risk Assessment

**Without this**: blocks cause frustration, users bypass governance, creative
workarounds happen outside the system (unreceipted).

**With this done wrong**: creative output leaks into authoritative output,
producing receipted hallucinations that look legitimate.

**With this done right**: controlled hypothesis generation feeding a strict
validity pipeline. The system gets smarter without getting less honest.
