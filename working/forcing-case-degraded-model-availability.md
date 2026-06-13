# Forcing Case — Degraded Model Availability

Filed 2026-06-12, mid-campaign, by the model that caught the live one.

## The event

During the workflow-kernel/self-annealing campaign (Phase 0 → P1.1 handoff), the US
government issued an export-control directive suspending access to **Fable 5 / Mythos 5**
for any foreign national, and Anthropic disabled Fable/Mythos for all customers to comply
(other models unaffected). The campaign had been running on Fable 5; it continued on
**Opus 4.8**. Refs: anthropic.com/news/fable-mythos-access; FT 2026-06-12.

The campaign filed a customs checkpoint for Skynet on the morning the actual customs
authority arrived. Comedy aside, it is a real forcing case for a surface the campaign
named in the abstract and immediately got tested on in the concrete.

## Why it is a forcing case (not just an anecdote)

The campaign's standalone/degraded-capability doctrine
(`docs/doctrine/annealing_and_recomposition.md` §5, LA standalone rule) already says, for
the *Linear Accountant*:

> A capability provider may be absent; the system degrades with **reduced authority** and a
> **typed refusal** (`requires_la_custody`); it must not fake equivalence.

Model substrate is the same shape, one layer down. The model is not ambient — it is a
**witnessed input** to every governed transformation. Losing the baseline model is exactly
the LA-absent case applied to the proposer/executor itself.

> **Model identity/availability is a witnessed input. A fallback model may continue at
> reduced authority/capability, but the downgrade must not silently preserve the prior
> run's budget and fidelity assumptions.**

Concretely, the doctrine walking in wearing a fake mustache:

```
baseline model capability disappeared
  → continuation must re-declare substrate (which model, witnessed)
  → reduced/substitute model may proceed only under re-declared authority
  → receipt the downgrade; do not inherit the prior model's budget/fidelity envelope silently
```

## Composition with existing doctrine (this is recognition, not new metaphysics)

- **[[provider_substitution_basis_mutation]]** (memory): *same API surface ≠ same
  admissibility basis*. A model swap is a basis mutation even when the interface is
  identical. This forcing case is that rule firing on the *model* axis, under duress.
- **LA standalone rule** (doctrine §5): identical degrade-don't-fake pattern; the model is
  another optional-capability axis, except it is *less* optional — there is no recomposition
  without a model. So the refusal is not `requires_la_custody` but a substrate-declaration
  obligation: a run may not claim the authority envelope of a model it is not running on.
- **Intent fidelity** (campaign): fidelity_class is declared per intent; a model downgrade
  may *lower* the affordable fidelity (a weaker substitute cannot honestly promise `exact`),
  which is a re-declaration, not a silent carry-forward.
- **AUTO_RUN budget** (loop-protocol §11): the metabolic caps (`max_slices_per_run`, retry
  budgets) were sized against a model; a substrate swap should re-confirm, not inherit, the
  budget.

## Reserved candidate (name early, ratify lazily — NOT a filed spec)

**`GOV_GAP_MODEL_SUBSTRATE_AVAILABILITY_001`** — candidate name reserved, **not filed.**
Forcing case is now real (this event), but no AG runtime surface witnesses model identity
today, and building one is out of scope for the workflow-kernel campaign. The retrofit cost
of *naming* it is zero; the architecture-gravity cost of *building* it now is not paid.

If/when sliced, the shape (recorded so the retrofit is named, not improvised):

- A run's receipts carry a `model_substrate` witness (model id + availability mode:
  `baseline` / `substitute` / `degraded`) — a witnessed input, never asserted prose.
- A substitute/degraded substrate re-declares its authority + fidelity envelope; it cannot
  spend the baseline's budget or promise the baseline's fidelity without re-declaration.
- This is a *separate surface* from `RecompositionReceipt`. Do NOT smuggle a model-substrate
  field into the recomposition receipt (P1.1) — different concern, different lifecycle. The
  recomposition receipt judges boundary accounting; substrate witnessing is a sibling.

Trigger to file the real spec: a forcing case where AG *itself* (not the harness/model
runner) must gate or refuse on model identity — e.g. an annealing delta whose trial
validity depends on which model produced the observations, or a governed session that must
refuse to inherit a prior model's authority envelope. Until then: reserved, composed,
unbuilt.

## This session's honest substrate note

Phase 0 was authored by Fable 5; P1.1 is authored by Opus 4.8. The swap is witnessed here
rather than silent. For careful spec-faithful implementation work this is lateral, not a
downgrade — but the point of the doctrine is that *lateral must still be witnessed, not
assumed*. No budget/fidelity claim from the Fable-authored plan is inherited silently; the
P1.1 slice is re-derived from the ratified gap spec, not from the prior model's context
alone.
