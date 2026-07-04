# ConvergenceFence — the load-bearing bridge

> **Status:** unproven. This is the footing the whole Governed Playbooks construction
> stands on. **Until the three hostile contracts below close on paper, every other doc
> in this directory is provisional.** Do not build registry / parser / scheduler /
> executor before this closes (see [build-phases.md](./build-phases.md) Phase 1).

---

## Why this exists

Reactor and pipeline are two composition laws that **do not unify**:

- **Reactor** — *conditional convergence*. Fires when state matches; drives toward a
  declared state. Idempotent, replayable. Asks "is the world the right shape yet?"
- **Pipeline** — *constructive-directional / typed dataflow*. Threads an artifact forward;
  each stage's output is the next stage's input. Safety is a property of the *flow*
  (acyclic, forward-only), provable without running. Asks "is the artifact being carried
  forward without reaching backward?"

No amount of reactor-cleverness turns one into the other. **The temptation to declare
"a reactor step is also a pipeline step" is false and dangerous** — the happy-path
example (reactor fires once, emits a digest) typechecks precisely because it isn't
behaving like a reactor at all. The real reactor cases (no-op, repeated firing,
non-convergence) do not obviously produce a "completion receipt the pipeline may consume
as typed input."

So the crossing object is **not** an identity. It is an adaptor: the **ConvergenceFence**.

```
Pipeline DAG
  → ConvergenceFence ───────────────────────────────┐
       contains: reactor algebra                     │  one terminal
       internal: no-op | fire-once | fire-many | fail │  ConvergenceOutcome
  → downstream pipeline step ←──────────────────────┘  (validated evidence)
```

The pipeline sees **one node**. The reactor's internal multiplicity stays inside the
fence trace. Otherwise repeated reactor firing leaks a loop into the pipeline DAG, and
the "acyclic, forward-only" proof just grew a possum in the walls.

---

## The shared leaf: BoundaryContract (not StepContract)

The shared primitive is probably **not** `StepContract`. A reactor is not secretly a
step; it is a sub-algebra behind a boundary. Restate the leaf as:

```
BoundaryContract {
  preconditions:        [...]                 // what must hold to enter
  authority_required:   [...]                 // standing / effect classes
  allowed_effects:      [...]                 // effect surface, typed
  required_witnesses:   [claim_type @ freshness]
  emitted_outcome:      TerminalOutcome       // the ONE thing downstream sees
  custody_behavior:     [...]                 // what unknown/partial means here
  freshness_reuse:      [...]                 // witness reuse semantics
}
```

Then:

```
PipelineStep       implements BoundaryContract
ReactorFence       implements BoundaryContract
HumanApprovalGate  implements BoundaryContract
ExternalEmitStep   implements BoundaryContract
```

**The footing question is whether BoundaryContract genuinely closes the three hostile
reactor cases at the pipeline seam.** If it does, the partition holds. If it doesn't, the
work is at the leaf, not the bridge, and everything above waits.

---

## Terminal ConvergenceOutcome

The fence emits exactly one of these. **Crucially, it emits a *validated convergence
outcome citing evidence*, not a raw NQ witness** — `service_active` alone is too cheap;
it may be one ingredient in convergence, not convergence itself.

```
AlreadyConverged {            // predicate already true; NO effect fired
  predicate, pre_witness, effects: [], spend: maybe_observe_only
}
Converged {                   // converged, possibly after N internal attempts
  predicate, attempts: N, effect_receipts: [r1..rN],   // INTERNAL trace, not exposed as edges
  final_witness, spend_receipts: [...], validation: { freshness_checked,
  claim_scope_unified, observer_method_admitted }, internal_trace_digest
}
RefusedPreEffect              // refused before any effect
NonConvergedNoEffect          // tried, did not converge, no effect occurred
NonConvergedPartialKnown      // partial, known effects
InterruptedUnknownEffect      // dispatched, custody unknown  >>> poison <<<
```

**Downstream progress is permitted ONLY by `AlreadyConverged` and `Converged`.**
Everything else blocks. `InterruptedUnknownEffect` *poisons* the downstream pipeline —
not failed, not false: **poisoned** — unless reconciled into a new receipt.

> Unknown custody is a terminal pipeline poison unless explicitly reconciled.

---

## The three hostile cases (the actual footing — write these first, on paper)

The happy-path single-fire-with-digest case typechecks and lulls everyone. These three
are the load-bearing joint. Build each by hand — *contracts only, no code* — before
anything generalizes.

### 1. No-op convergence

Predicate already satisfied; **no effect fires**. What terminal outcome? It can
typecheck **only if** the downstream pipeline edge requires *evidence that P holds*, not
*artifact produced by previous stage*. This forces the correction: **pipeline edges are
not always artifact-only — some are evidence/control edges.**

```
AlreadyConverged {
  predicate: target_has_artifact_digest(X) && service_active,
  pre_witness: ..., effects: [], spend: maybe_observe_only
}
```

Open question: does `AlreadyConverged` typecheck as valid input to a pipeline step whose
contract says `requires: evidence that P holds` — or does it expose that the step's
input contract was wrongly written as `requires: artifact emitted by previous stage`?

### 2. Repeated firing

State drifts during the run; reactor fires three times. This MUST NOT produce three
pipeline inputs. It produces **one** terminal `Converged` with the attempts as
*internal* trace. If the downstream step can see or depend on `r1`, `r2`, `r3`
individually, the fence leaked and the pipeline absorbed a loop. Small architecture war
crime.

Open question: does the pipeline step's *single* typed input slot accept the multiplicity
*only* as a sealed `internal_trace_digest`, never as enumerable edges?

### 3. Non-convergence / timeout / interruption

The reactor never reaches its state. This is `interrupted_unknown_effect` **inside a
pipeline** — unknown custody at the exact seam everyone assumed was clean.

Open question: what does the pipeline do with a predecessor in unknown custody? It must
refuse-before-effect / quarantine, not "failed step, continue if allowed." Does the
contract force that, or does the pipeline partially commit?

---

## The footing test, stated once

> **Can a reactor subrun be sealed behind a boundary whose terminal outcome is valid
> pipeline evidence, without leaking reactor multiplicity into the pipeline graph?**

If **yes** for all three hostile cases against a *single* `BoundaryContract`: the
partition holds, the city is real, build out.

If **no** (the bet is at least #1 and #2 fail, because the happy-path example quietly
assumed single-fire-with-digest): `BoundaryContract` is not yet the shared leaf, the
reactor/pipeline partition needs a third thing at the seam, and every elaboration in
these docs is provisional until resolved.

**Warning (common-mode synthesis failure):** multiple models agreeing the bridge holds
is *not* validation — it is correlated estimators assuming the same unproven lemma and
elaborating confidently past it. The footing is poured on paper, by hand, or it is not
poured.
