# Candidate: the work container (intermodal freight lens)

**Status:** CANDIDATE — non-binding. A handle for review, not authorization to
build. Provenance: operator framing, 2026-07-04 (conveyor-dogfood campaign,
during the maude V1/V2 vocab pass). Promote only with a forcing case +
explicit ratification.

## The idea in one line

A unit of governed work is an **intermodal container**: a sealed, bounded unit
of intent that moves across planning systems, agent harnesses, repos, shells,
reviewers, and humans **without losing custody or pretending the transit system
is the cargo**.

> Jira tracks intention *socially* ("we plan to do X").
> The container transports intention *operationally* ("this bounded unit of X
> was packaged, handed to executor Y under constraints Z, produced artifacts Q,
> and is now admissible / obstructed / contaminated / needs splitting").

The primitive is **not** `epic → sprint → task → subtask` (Jira already did that
crime scene). The primitive is **bounded transferable work**:

```
work intent → sealed container → execution attempts → receipts → next admissible container
```

The hierarchy becomes *cargo*, not ontology: an epic compiles into one or more
containers; a sprint is a convoy/shipping lane; a task is cargo inside a
container.

## This is NOT greenfield — it already shipped once, in AG

The container is already instantiated as AG's playbook/conveyor system
(`src/governor/playbooks/`). The freight lens is a *name and synthesis* over
primitives already carrying freight:

| Freight term          | Already-shipped AG primitive                                  |
| --------------------- | ------------------------------------------------------------- |
| Standard box + seal   | `PlaybookSpec → CertifiedPlaybook` (canonical digest, closure)|
| Manifest              | plan-envelope-v0 (objective, scope, steps) / playbook spec    |
| Routing / permissions | `RationCard` (absence-restrictive allowlists, locked axes)    |
| Latched consignment   | `QueuedPlaybook` (per-item `operator_approved` latch, fences) |
| Bill of lading        | custody / provenance record (digests, parent refs)            |
| Customs               | Wicket admission-as-evidence + SyntheticCage (safe ≠ live)    |
| Crane / yard          | maude scheduler/supervisor + the conveyor harness             |
| Damaged-cargo report  | obstruction / partial-result receipt (ReviewPacket, halt_if)  |
| Intermodal transfer   | sha256-sealed `HandoffRenderer`; the exported projection      |
| Reviewer verdict      | `ReviewPacket` + `ReviewPacketValidator` (`used ≤ granted`)   |

## The killer invariant — already enforced as code

> **Decomposition must preserve custody. Recomposition must not create authority.**

This is not aspirational. AG's workflow-kernel spine already enforces it:
`RecompositionReceipt` + `account_boundaries()` (the laundering refusal —
`refused_laundering` when an admitted decomposition boundary is unaccounted),
`RecompositionRefusal` at the `recomposition_seam`, where **recomposition's only
verb is refuse** (see `pipeline_types.py`, `cooked_context_orchestrator.py`,
feature-history "Workflow-Kernel / Self-Annealing Spine"). You can unload,
reload, route, split, batch, defer, or inspect cargo — but you cannot change
what was authorized just because it passed through a terminal.

## The architectural call this forces: ONE object, many terminals

The intermodal trick collapses if cargo is re-minted at every port. Therefore:

- **AG is the bonded origin.** The container is sealed here (digest applied,
  RationCard bound, recomposition can only refuse). AG holds custody.
- **maude / Night Shift / NQ are terminals** (crane, customs shed). They
  *transport, inspect, and render* the container — they do **not** define their
  own law-bearing `WorkContainer` type and do **not** re-mint authority.
- The transport surface is the already-named AG item **"make the law portable"**
  (STATUS, conveyor-dogfood): a stable EXPORTED projection
  (`QueuedPlaybookRef / RationCardRef / ReviewPacket / ApprovalWitness /
  ConstraintProjection / GovernedPlanBinding` + refusal classes + digest/
  citation rules + authority axes). Consumers read the serialized surface,
  never AG internals. This is the CD-1a "no import coupling" rule graduating
  from prose to artifact.

  **Status (2026-07-04): the CONTRACT ARTIFACT has STARTED** — `docs/api/`
  (work-container / agent-integration / provider-integration) +
  `schemas/*.v1.json` (DRAFT/CANDIDATE), a projection over shipped shapes that
  mints nothing. The split that reconciles this with the gate: naming the
  surface (contract artifact) is "name early" and can happen now; the **live
  WIRING** — `governed_dispatch` emitting/consuming a serialized WorkContainer —
  stays **gated on CD-4** proving the runtime shape (build vector Slice 4).

  **Slice 4 landed the PROJECTION (2026-07-04), not the wiring.**
  `src/governor/work_container.py` + `project_cd4b_work_container()` project the
  proven CD-4B live shape (`sess_aabb2a056f9f`) into a schema-valid, sealed
  container (persisted candidate at the CD-4 specimen dir). It is a pure projection
  over shipped objects — no registry, no dispatch. The live `governed_dispatch`
  emission/consumption (and a first-class admission `GateReceipt` behind
  `admission_ref`) remain the next gated step. **Projection, not delegation.**

> **AG owns legitimacy. Maude owns logistics. The WorkContainer is the bill of
> lading between them.**

**Sharpening (operator, 2026-07-04): "cover object" ≠ documentation-only
metaphor.** The container must become a **real exported record** — a serialized,
consumable object — just NOT a new law-bearing kernel object. It is the
**portable ABI** between AG and maude. The danger it earns (in a good way):
it is the one shape both sides agree on, rather than another ontology barnacle.
Doc-only would be under-building; a new kernel primitive would be over-building.
The target is the narrow middle: an export record.

The exported, maude-facing object gets a name **distinct from the AG internals**
so the two never blur: `WorkContainerRef` / `WorkConsignment` / `GovernedWorkUnit`
(name still open). AG internals stay `CertifiedPlaybook` / `RationCard` /
`GovernedPlanBinding` / `ReviewPacket` / `RecompositionRefusal`.

Anti-pattern to avoid (constellation doctrine): a second, divergent, law-bearing
container in maude = duplicate authority + custody drift ("Maude-in-drag" / "AG
wearing a little sailor hat"). maude's job is to be a *good terminal*, not a
second mint.

## Vocabulary: three-layer disclosure (feeds the maude V1/V2 pass)

The freight metaphor is the **middle** (teaching) layer — not the surface, not
the deep theory:

| Layer   | Audience                    | Words                                        |
| ------- | --------------------------- | -------------------------------------------- |
| Surface | operator driving (buttons)  | run, queue, approve, blocked, retry, discard, split, review |
| Middle  | "why is it shaped this way" | container, manifest, seal, yard, waybill, customs, damage report |
| Deep    | theory / debugging          | custody, admissibility, ration, witness, recomposition refusal, authority boundary |

Note the trap the operator flagged: freight words (*consignment, waybill*) are
their own opacity — as foreign to a plain sysadmin as *custody*. So the freight
lens stays in help/docs/`why` (middle), NOT on the button vocabulary — "unless
you want Maude to sound like SAP wearing a little sailor hat."

## Anti-goals (what the container is NOT)

- **Not a task manager.** No epic/sprint/subtask ontology; hierarchy is cargo.
- **Not a Jira replacement.** Jira tracks intention socially; this transports it
  operationally. They are different jobs.
- **Not a new authority primitive.** Legitimacy stays in AG. The export carries
  *references and receipts*, never fresh standing.
- **Not a recomposition engine.** Recomposition lives in AG's spine and its only
  verb is refuse. The container does not recombine cargo into new authority.
- **Not an executor.** maude schedules/dispatches/supervises; the harness
  executes; AG gates. The container is the thing moved, not the mover.

## Export sketch (the serialized object a terminal consumes)

The maude-facing record — read without importing AG internals. Illustrative,
NOT a schema to build:

```
GovernedWorkUnit (a.k.a. WorkContainerRef / WorkConsignment)   # name still open
  manifest:   objective, non_goals, authority_boundary, expected_outputs, acceptable_partial_outputs
  cargo:      context_refs, files/repos/issues, plan_ref, assumptions, known_hazards
  routing:    eligible_executors, forbidden_executors, required_substrate, tool/network/write perms
              (projected from RationCard — read-only, never re-derived)
  custody:    source, creator, digest (seal), parent_container, decomposition_lineage
  execution:  max_steps, stop_conditions, verification_required, allowed_mutations
  receipts:   transcript_refs, artifact_refs, diffs, test_results, obstructions, reviewer_verdicts
```

Every field is a **projection of an existing AG artifact** (CertifiedPlaybook /
RationCard / GovernedPlanBinding / ReviewPacket), serialized at the bonded
origin and sealed by digest. maude behavior over it: `schedule → dispatch →
supervise → inspect → return receipts`. Names still open — do not axiomatize one
here (names are half the trap).

## Open questions (for a future forcing case, not now)

1. The export is a **projection wrapper** over `CertifiedPlaybook + RationCard +
   GovernedPlanBinding + ReviewPacket`, not a new law-bearing type — confirmed
   direction (operator, 2026-07-04). Open: exact field set + versioning of the
   wire record.
2. Does a Jira/GitHub epic *compile into* containers, and where does that
   compiler live? (Ingress, not the container itself.)
3. Convoy/lane semantics (batch of containers) — deferred until multi-container
   routing has a real driver.

## Do-not

- Do not build a second law-bearing container type in maude (AG-in-drag).
- Do not let "cover object" collapse into documentation-only; it is a real
  exported record.
- Do not start the portable projection before CD-4's live run proves the shape
  ("don't build the port before naming the cargo standard").
- Do not promote this note to doctrine without a forcing case + ratification.
