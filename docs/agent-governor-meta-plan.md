# Agent Governor — Meta-Plan

**Status: orientation, not implementation spec.**

This document is a navigational artifact. It is *not* a roadmap, not a kernel
ratification, and not authorization to build. It organizes the planes the
constellation already separates and names one constitutional invariant that
several filed gap specs already obligate without a single anchor.

Where this document names a vocabulary (planes, binding verbs, observing
verbs, artifact-kind × use-kind), the vocabulary is a *handle for
recognition*, not a typed primitive in code. Promotion to typed primitives
requires a forcing case and lives in `specs/gaps/`.

---

## Premise

The stack is becoming a control surface for agent action. That changes the
governing question from:

> Can this tool detect, authorize, or record something?

to:

> Which artifacts are allowed to bind consequence, and under what witnessed
> conditions?

The answer is not more automation. The answer is **artifact discipline.**

## Core invariant

> **Nonbinding signal does not become binding consequence without a promoted
> artifact.**

Operational corollaries (each already obligated by a filed gap):

- Observation does not mint authority. (`working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`)
- Authority does not mint capacity. (`specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md`)
- Form does not mint content. (`specs/gaps/GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001.md`)
- Construction guarantees do not survive serialization unrevalidated. (`specs/gaps/GOV_GAP_SEALED_OUTCOME_BOUNDARY_001.md`)
- Post-validated ≠ pre-authorized. (`working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md`, recent commits)

The invariant is the through-line. The gaps are the load-bearing instances.

## Wards subtract; warrants attest

Two coherent positions exist for constraining what an agent can do, and the
difference is not cosmetic.

**Containment by subtraction.** Define the action space as
`actions = capabilities − wards`. Agents may act unless explicitly warded.
This is real engineering (deny-by-default network, writable-path
allowlists, sandboxed eval, port-isolated runtime) and dominant in
agent-runtime substrates today. Its failure mode is *fail-open under
novelty*: anything not warded is permitted. A new capability nobody
thought to ward is permitted by default.

**Consequence by warrant.** Define admissible action as a positive chain:
standing → admission → spendable capacity → execution → receipt. Each step
is a *witnessed attestation*. Absence of an attestation fails *closed* —
no standing means no admission regardless of warding. This is the
constellation's shape.

Slogan:

> **Wards subtract. Warrants attest.**

Neither is wrong; they protect against different failure modes. The seam
where containment runs out is the moment trust is *asserted* rather than
*witnessed* — e.g., any `sandbox: unrestricted` clause for "trusted
operator-local work." Trust asserted is not trust witnessed. The
admissibility layer begins where containment ends.

## The directional kernel

The core invariant above is the cross-class form (no nonbinding-class →
binding-class). The chain has a parallel within-class form:

> **No later-stage artifact may supply an earlier-stage authority
> condition.**

The chain is one-way:

```
observation / testimony
  → standing question
  → standing grant / refusal
  → wicket admission / refusal
  → linear accountant spendability
  → governor / nightshift execution
  → outcome / refusal receipt
  → continuity reliance
```

The forbidden conversions:

```
observation        ≠ standing
standing           ≠ admission
admission          ≠ spendability
spendability       ≠ execution proof
execution receipt  ≠ prior authorization
history            ≠ reliance
```

The full set of directional invariants and their composition with filed
gaps lives in `working/directional-invariants.md`. The kernel restated as
product sentence:

> **Agents may observe loosely, but may only act through standing,
> admission, spendable capacity, and receipted consequence.**

Companion to the ignition sentence at the bottom of this document.

## Planes

The constellation sorts into planes. Each plane disclaims its neighbors' jobs.
That separation is the architecture, not the documentation.

| Plane      | System                           | Job                                                                  |
| ---------- | -------------------------------- | -------------------------------------------------------------------- |
| testimony  | NQ (`~/git/nq-root/nq`)            | what kind of wrong is happening (findings as proofs)                 |
| memory     | continuity (`~/git/continuity`)  | what may persist and be relied on (observe → commit → rely)          |
| authority  | standing → wicket                | entitlement, then admissibility of a specific operation              |
| capacity   | linear_accountant                | budget left, exactly once; eligibility ≠ spendability                |
| execution  | nightshift, governor (this repo) | resume intent under policy; every action through the ledger          |
| transport  | WLP                              | the only thing that crosses a boundary; loss = degradation / refusal |
| constraint | z3-verifier                      | can this graph/config/plan permit forbidden conversion?              |

The constraint plane is not another authority plane. See **Z3 role**, below.

## Decision path for one agent action

```
standing
  → wicket
  → linear_accountant
  → governor / nightshift
  → WLP boundary if crossing
  → NQ observation
  → continuity promotion or refusal
```

1. **Standing** answers: may this actor act here at all?
2. **Wicket** answers: is this specific operation admissible on the cited
   basis?
3. **Linear Accountant** answers: is there remaining spendable capacity, and
   has this exact consumption already happened?
4. **Governor / Nightshift** executes or resumes only through receipted
   policy.
5. **WLP** carries only boundary-crossing artifacts whose loss degrades or
   refuses, never silently authorizes.
6. **NQ** observes what actually happened.
7. **Continuity** decides what survives into later reliance.

Each step refuses the upstream classification's laundering. Standing is not
admissibility. Admission is not spendability. Observation is not authority.

## Binding verbs vs observing verbs

The grammatical cut is between verbs that **bind consequence** and verbs that
**emit signal**.

### Binding verbs (handshake-only, fail-closed)

```
grant      admit       authorize
request_capacity        consume
commit     rely        mutate
cross_boundary
```

Loss here reads as refusal or degradation. A dropped denial must never become
silence; silence must never become consent.

### Observing verbs (may be lossy if loss is classified)

```
observe    notify      warn
diagnose   suggest     report_finding
```

Loss of observation creates an *observability-gap finding*. It does not
fabricate health. NQ already names the doctrine ("signal missing, not zero");
this is the constellation-level inheritance.

## Artifact-kind × use-kind transport table

A closed table is the discipline. Mode confusion becomes a type error, not a
configuration accident.

| Artifact kind                | Lossy-tolerant?                           | Strongest admissible use     |
| ---------------------------- | ----------------------------------------- | ---------------------------- |
| NQ finding                   | Yes, with gaps classified                 | orient / diagnose            |
| Observation / notification   | Yes, with sequence or heartbeat gaps      | suggest / inform             |
| Outcome receipt              | Replicable lossy only after durable write | audit / reconcile            |
| Standing grant               | No                                        | entitle                      |
| Wicket admission             | No                                        | admit operation              |
| Capacity request             | No                                        | reserve / check spendability |
| Capacity consume             | No                                        | spend exactly once           |
| WLP authorization            | No                                        | cross boundary               |
| Continuity commit            | No                                        | persist premise              |
| Continuity rely              | No                                        | bind future premise          |

The table is **closed** by intent. New artifact kinds enter via gap spec,
not by accretion.

The table is not yet typed in code anywhere. It is *the candidate vocabulary*
that promotion-of-typed-primitives would have to honor. Forcing case for
typing: a concrete laundering specimen in this repo that the current gates do
not refuse. None known today. The sentinel at
`working/sentinel-observation-not-authority.md` tracks the search.

## Z3 verifier role — checker, not judge

The constraint plane checks the **artifact graph**, not the claim, the agent,
or the authority itself.

> Given this proposed action / config / policy / table / plan, is there any
> possible path where a forbidden conversion happens?

The verifier emits a verification receipt:

```
verification_receipt:
  checked_artifact
  constraint_set
  result: sat | unsat | unknown
  counterexample if sat
```

Safety queries encode the **bad thing** and want `unsat`:

- `sat`     = found a possible violation (counterexample is the demon map)
- `unsat`   = no violation in this bounded model
- `unknown` = solver shrugged; do not promote

### Z3 vs Lean

- **Lean** proves doctrine in a small durable kernel: *this kind of conversion
  is impossible under these definitions.* See `~/git/lean/LeanProofs/`.
- **Z3** checks concrete instances: *does this AG policy file, routing
  table, artifact schema, or proposed plan violate the doctrine?*

Lean is the constitutional kernel. Z3 is the boundary scanner that finds the
secret hallway before it reaches a gate that would have to pretend it wasn't there.

The wicket repo (`~/git/wicket`) is the legibility surface for AG gate
doctrine; Z3 integration belongs at that seam, not in AG kernel.

## Pitch implication

Current public framing (`README.md`) names: **scope, evidence, budget,
scars** in the verdict example, but the surrounding prose only narrates
scope / evidence / approval. Budget is the retry-storm / blast-radius
control plane and deserves first-class prose status.

The minimal pitch revision:

> Agents may act only when their authority, evidence, freshness, and budget
> are witnessed — with action, refusal, and capacity spend recorded as
> first-class receipts.

Sharper one-line backbone:

> AG may observe loosely, but may only act through promoted authority, fresh
> evidence, spendable budget, and receipted refusal.

## Near-term implications (orientation, not commitments)

1. Promote artifact-kind discipline over transport-mode configuration. The
   right noun is artifact-kind, not TCP/UDP.
2. Make the binding/nonbinding split explicit wherever schemas land.
3. Treat Linear Accountant as a core plane in pitch, not auxiliary.
4. Ensure WLP cannot carry binding artifacts over lossy semantics.
5. Ensure lossy testimony produces observability-gap artifacts, not silent
   absence.
6. Keep each repo's "what this is not" section sharp.
7. **Do not let AG/Governor consume observations as authority without
   promotion.** This is the trapdoor everything else serves.
8. Prefer closed tables over clever prose wherever mode confusion is
   possible.
9. Keep non-jurisdictional work (garden / woods / drafts / chat) outside
   courthouse jurisdiction unless it explicitly tries to bind.

Items 1–9 are *handles*, not tasks. Promotion to ratified work requires a
forcing case per `~/.claude/CLAUDE.md` § YAGNI scope.

## What this document is not

- Not authorization to build new typed primitives.
- Not a ratification of `ArtifactKind` / `UseKind` as code-level enums.
- Not a roadmap, schedule, or implementation order.
- Not a replacement for the gap specs it cross-references. Those carry the
  load; this organizes them.
- Not a public claim about AG capability beyond what the implementation
  already does.

## Cross-references

Companion orientation docs:

- `docs/constellation-wire-plan.md` — the **physical wiring** companion: which
  transport each cross-repo seam uses today (all SPEC-harness injection as of
  2026-06-12), the W0–W4 promotion phases, and cold-start re-entry probes.
- `docs/constellation-zoning.md` — the **deferred-organ / one-way-door**
  companion to this file. Where this doc names the planes that *exist*, that one
  names the organs that *do not yet* (temporal authority, retraction transport,
  verdict seam, evidence death rites, restore epochs, schema evolution, fleet
  control) and the grain-of-refusal rule governing when each earns construction.
  PROVISIONAL; carries an LLM-relay provenance caveat.

Filed gap specs that obligate corollaries of the core invariant:

- `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md` — observation
  → authority laundering at the kernel classification surface.
- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — validity ≠
  spendability; budget/spendability audit obligations.
- `specs/gaps/GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001.md` — form vs.
  content at the receipt-schema layer.
- `specs/gaps/GOV_GAP_SEALED_OUTCOME_BOUNDARY_001.md` — construction
  discipline; authority observable, not constructible.
- `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` — post-validated ≠
  pre-authorized; serialization-boundary doctrine.
- `specs/gaps/GOV_GAP_PROMOTION_SURFACE_001.md` — promotion-surface
  obligations.
- `specs/gaps/GOV_GAP_EGRESS_001.md` — egress as runtime gate.

Memory pointers for constellation context:

- `linearaccountant_repo.md` — Linear Accountant boundary and packet shape.
- `wicket_repo.md` — admissibility preflight kernel; Z3 seam belongs here.
- `lean_admissibility_kernel.md` — formal warrants AG cites.

## One-line doctrine

> **AG may observe loosely, but may only act through promoted authority,
> fresh evidence, spendable budget, and receipted refusal.**
