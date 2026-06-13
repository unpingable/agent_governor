# Annealing and Recomposition

Status: **PROVISIONAL** (filed 2026-06-12, Phase 0 of
`working/campaign-workflow-kernel-annealing.md`). Doctrine candidate; binds the campaign's
build slices on operator nod, not the wider repo until ratified. Composes with
`specs/core/SELF_GOVERNANCE_SPEC.md` per `working/crosswalk-self-governance-spec.md`
(this campaign is presumptively that spec's implementation track).

## 1. The reframe

The governor is not "CI for agents." It is **semantic CI**: a governed event-control plane
whose unit of work is a transformation pipeline —

```
input → projected intent → decompose → admit bounded slices → execute under scope
      → collect witnesses → recompose → verdict / action / refusal → receipt
```

CI asks *did the build pass*. The governor asks *did the action still mean what the admitted
decomposition said it meant*. **Recomposition is where laundering happens**: completed
subtasks do not automatically imply an admissible whole. Decomposition is capacity
management; recomposition is legitimacy management.

The masked-exit-code scar (migration 058, 2026-06-12; `~/.claude/CLAUDE.md` § Verification
discipline; `src/governor/verify.py`) is the type specimen: `cargo test | tail` was a
*pipeline witness-corruption bug* — failed verifier → lossy projection → recomposed as
success.

## 2. The six preserved properties

Every pipeline stage must preserve, or receipt the loss of:

1. **Scope** — what was this allowed to touch?
2. **Basis** — what evidence was relied upon?
3. **Witness** — who/what testified?
4. **Exit status** — did the verifier actually pass? (Exit codes are the verdict; never
   inferred through lossy shell projections.)
5. **Recomposition rule** — how did partial verdicts become a final verdict?
6. **Publication boundary** — can this leave the local trust domain?

A stage transition that discards any of these without a receipt is inadmissible. That
refusal is what `RecompositionReceipt` + `account_boundaries()` exist to express
(`specs/gaps/GOV_GAP_RECOMPOSITION_RECEIPT_001.md`).

## 3. Kernel vs annealable userland (the one organizing distinction)

```
Kernel:    what must never be false        — changes only via admitted upgrade ceremony
Profile:   what this app/workflow cares about
Policy:    what may anneal
Receipts:  why anyone should believe it happened
```

The verdict stack climbs the kernel hierarchy: slice kernel renders the **cargo verdict**
(did the artifact work — verifier exit codes), workflow/app kernels render the **dogfood
verdict** (did the process remain governed), the system kernel renders the
**packet/publication verdict** (may this leave the trust domain). A slice can pass while
the workflow refuses the recomposition; a workflow can pass while the system refuses
publication. Every recomposition states **which kernel accepted it**.

### Layer badges

Every governance primitive carries a layer badge. The test for any primitive is not
"do we have words that rhyme with this?" but **"does this primitive know which layer it
belongs to?"**

| Badge | Means | Occupied today by (examples) |
|---|---|---|
| **kernel** | invariant-bearing; mutates only via admitted upgrade ceremony | `libs/receipt_kernel` (StageGraph, 13 invariants), `standing/validator.py` (+ its supersession ceremony), refusal/custody semantics, genesis-class seams (standing, wicket, LA, AG enforcement, receipts, classification policy, doctrine files) |
| **app profile** | app-specific invariants and meaning | `spine.py`/`invariants.py`, `policy_engine.py`, domain governors |
| **workflow topology** | pipeline decomposition/recomposition rules, routing, gates | `cooked_context_orchestrator.py`, `intent_compiler.py`, `lanes.py`, `docs/loop-protocol.md` FSM (doc-side) |
| **policy-userland** | annealable defaults, budgets, postures | `convergence_tuning.py`, `ultrastability.py` params, `homeostat.py`/`coupling.py`, `overrides.py`, `scars.py` stiffness |
| **runtime-session state** | resumability and working context; never authority | `session_continuity.py` capsules/checkpoints/fork/promote, `execution.py` ExecutionState, loop.json |

## 4. The hard red line (baseline laundering)

> **Checkpoints/forks/promotions are resumability/continuity machinery unless explicitly
> admitted as control-plane baselines.** A promoted session state is not automatically a
> known-good policy baseline. Same family, different badge.

Mechanically: a `ControlBaseline` is created only by an explicit admission step with a
creation receipt; nothing in session_continuity's promote path mints one. Checkpoint says
*"I can resume/explain from here."* Baseline says *"I am allowed to roll back to here."*
Promotion says *"this checkpoint has earned baseline status"* — and earning means the
supersession ceremony (a receipt produced under the prior baseline), never elapsed time,
never session promotion. *Checkpoint everything that changes shape; baseline only what
survives judgment.*

## 5. Self-annealing

Self-healing restores state; self-annealing improves future admissibility — it edits the
shape of the *next* run, never the obligations of the *present* one.

> **Self-annealing is receipt-driven adjustment of future pipeline shape, never silent
> reinterpretation of present obligations.**

Lifecycle (every arrow receipted):

```
receipt stream → AnnealingObservation → CandidateDelta (AnnealingDelta)
              → admission (human approval forced True; named ControlBaseline;
                           mandatory expiry; RollbackTrigger)
              → scoped activation → promote (evidence-count) | rollback | expire
```

### May tune (the allowlist — exhaustive, closed; per constellation-zoning §3 authority is allowlisted)

- routing policy / lane defaults
- budgets (capacity, retry, time, attention defaults)
- decomposition size / slice caps
- retry posture
- witness placement (where in the pipeline evidence is collected)
- default gates (which optional gates are on by default)

### May NOT mutate (ever, via annealing)

- kernel invariants
- refusal semantics
- custody semantics
- authorization / publication rules
- the allowlist above, or these HardGuards themselves

These four prohibitions are forced-True `HardGuards` fields checked at delta
*construction* — an off-allowlist or genesis-class-scoped delta cannot be built, not merely
not applied. Kernel changes take the admitted upgrade path (validator-supersession
ceremony), which is surgery, not learning. Directional custody binds throughout: **a system
may not rewrite gates while acting through them** — `annealing.py` acts *through* standing/
wicket/LA/receipt gates and never imports their mutation-capable internals.

> **Lossy intent is allowed; unreceipted loss is laundering.** Intent carries a declared
> fidelity class (exact / bounded / heuristic / exploratory) and loss budget; losses are
> declared at recomposition and judged against the declaration. AG judges fidelity; LA
> meters spend (`working/seam-la-fidelity-pools.md`).

### Standalone / degraded capability rule (operator-pinned, 2026-06-12)

> **LA enriches AG's metabolic accounting; it is not the root of AG's jurisdiction.**
> AG may run poor without LA. It must not run blind, and it must not fake being rich.

AG must remain operational without Linear Accountant. The architecture is *AG
kernel/recomposition: mandatory; LA adapter: optional capability provider* — never
*AG → LA → permission to breathe*.

| | With LA | Without LA |
|---|---|---|
| spend | typed metabolic spend, cross-run budgets | local/static budgets, receipt-only spend summaries |
| refusal reach | cross-repo metabolic refusal | AG-local only |
| fidelity | opaque echo now; typed pools if ever forced | declared, accounted, and judged at recomposition exactly the same |
| annealing | full authority | **reduced authority** (no LA-backed trial budgets) |

Degradation rule: loss of LA reduces available authority/capability; it must not disable
core recomposition, refusal, checkpoint, or baseline semantics. Refusal rule: any action
requiring LA-backed spend custody must refuse or downgrade with typed reason
**`requires_la_custody`** when LA is absent — never pretend local accounting is equivalent.

### Division of labor (these three stay distinct)

| Mechanism | Cadence | Acts on | Mutates |
|---|---|---|---|
| **Homeostat → Coupling → Ultrastability** (`TuningDelta`/`TuningIntent`) | per-turn / per-epoch | parameters *within* the current shape, inside floor/ceiling/step bounds | nothing structural; deadband + freeze guard oscillation |
| **Scars** (evidence-gated stiffness) | per-failure / per-evidence | memory of damage; admissibility friction | stiffness only; topology of the scar is permanent |
| **Annealing** (`AnnealingDelta`) | per-admitted-delta | the *future* shape: routing, budgets, decomposition, witness placement, default gates | only allowlisted surfaces, only via admission, always with baseline + expiry |

Lineage, not identity: a scar is remembered friction; an `AnnealingObservation` is
classified friction with a future-policy implication; a `CandidateDelta` is the proposed
adjustment. Scar "anneal" (stiffness relaxation) keeps its existing meaning; the new
objects are "annealing deltas."

### Dependency direction (operator-pinned, 2026-06-12)

> **Generic annealing must not depend on a domain tuning module.**

`annealing.py` must not import `convergence_tuning.py`. Shared pure custody helpers live in
a neutral module both import, or are copied with a noted debt until convergence_tuning
becomes an adapter (Phase 4 decision). Promote the custody pattern, not the domain module.

### Enforcement pacing (operator-pinned, 2026-06-12)

**One new enforcement surface per release band.** Phase 3a lands activation/rollback teeth
while RecompositionReceipt stays shadow; Phase 3b flips recomposition to enforcing only
after the 3a lifecycle drill passes.

## 6. Vocabulary collision tables (binding on campaign code and receipts)

**"baseline"** — never bare in code or receipts:

| Term | Object | Layer |
|---|---|---|
| `BaselineProfile` (`auto_tuning.py`) | metric-distribution snapshot ("what normal looked like") | runtime observation |
| `ControlBaseline` (new) | named, admitted rollback target with creation receipt + lineage | control plane (admitted) |

**"checkpoint"** — seam checkpoints are tagged `session_continuity.Checkpoint`s
(`seam=pre_delta_activation` etc.), NOT a fourth type:

| Term | Object |
|---|---|
| `session_continuity.Checkpoint` | named capsule cut within a session |
| `execution.ExecutionState` | autonomous-executor envelope save |
| auto_tuning reset tracking | telemetry bookkeeping |
| seam checkpoint (new usage) | a `session_continuity.Checkpoint` carrying a `seam` tag at a dangerous transition |

**"kernel"** — four senses, all live:

| Term | Object |
|---|---|
| `libs/receipt_kernel` | attestation substrate (hash-chained ledger + invariants) |
| `specs/core/KERNEL_CONSTRAINTS_SPEC.md` / evidence-gate kernel | evidence-gated coding-harness constraint core |
| authority-kernel substrate (`GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`, Rust mint) | post-launch decision-kernel port |
| kernel hierarchy (this doc) | the layer-badge system: system/app/workflow/slice invariant levels |

**"anneal"**: `scars.py` stiffness relaxation (unchanged) vs annealing deltas (new).
**"delta"**: `TuningDelta` (homeostat, per-turn multiplier recommendation) vs
`AnnealingDelta` (prospective, admitted, expiring policy delta) — never interchangeable.

## 7. Composition with the validator lattice

Annealing observation and proposal sit at OBSERVE→INTERPRET→RECOMMEND on the standing-class
lattice. Activation requires AUTHORIZE from outside the annealing module (human approval
receipt; optionally wrapped for wicket as `operation_class=authorize`,
`intended_action=policy_delta_apply`). Rollback reasons stay dual-failure-typed
(regressed | exhausted | refused) and never collapse — juridical and metabolic failure are
different facts.

## 8. Provenance

Derived from the 2026-06-12 operator/ChatGPT design session ("semantic CI", "microkernels
all the way down, but not turtles — turtles have no receipt discipline"), reconciled against
SELF_GOVERNANCE_SPEC v0.1 (crosswalk: `working/crosswalk-self-governance-spec.md`),
pipeline doctrine (`working/pipeline-doctrine-2026-06-12.md`, loop-protocol §11), and the
constellation zoning record (`docs/constellation-zoning.md`). Campaign card:
`working/campaign-workflow-kernel-annealing.md`. Gap specs:
`GOV_GAP_RECOMPOSITION_RECEIPT_001`, `GOV_GAP_WORKFLOW_KERNEL_PROTOCOL_001`,
`GOV_GAP_ANNEALING_DELTA_001`, `GOV_GAP_CONTROL_BASELINE_001`.
