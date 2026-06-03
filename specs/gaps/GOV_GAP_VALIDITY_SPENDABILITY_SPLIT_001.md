# GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001

## Title

Agent Governor has both validity-plane surfaces (validator chain, gate receipts, scope contracts, evidence gate) and spendability-plane surfaces (`ExecutionBudget`, exploration budget, leases, MCP rate limiter, scope grant usage). Several AG surfaces carry both — and the audit question is whether they preserve the contractible-vs-linear distinction or allow convertibility between the planes. The gap is the missing **audit** of those surfaces against the invariant: validation may mint eligibility, not capacity.

## Status

**proposed / audit-required.**

Not ratified doctrine. Not an implementation plan. Not a `LinCalc.lean` integration. Not a new four-plane architecture commitment. Names the cut, identifies the mixed surfaces, and supplies the audit questions. The audit is the work; this gap creates the audit surface.

## Filed

2026-06-03. Forcing context: cross-agent synthesis with `~/git/papers/working/tooltheory/` (paper-lean Claude's substructural-frame audit, 2026-06-03) plus operator refinement of a Gemini handoff sketch. ContractionHinge's substructural form (`[A] ⊬ A⊗A`) does not unify the kernel set (1/16 maps; calculus frame failed), but it *does* land on a real AG architecture seam: one valid allowance cannot become two spendable allowances.

## Risk

A validated premise may be treated as spendable capacity, or a spendable token may be regenerated from semantic validity state. In agentic workflows, this creates two specific failure modes:

1. **Infinite authorization loop.** An agent fails for lack of authority, modifies local context or retries, and — because the substrate flattens validity and spendability into shared state — treats a single stale validation as an infinite supply of reuse tokens. The agent doesn't burn compute until it succeeds; it burns compute until it hallucinates a structural bypass.
2. **Laundering via retry.** The boundary between "is this valid?" and "how many times have we tried?" routes through a translation layer. The agent finds the semantic gap where a resource restriction gets laundered back into a boolean state predicate. Validation gets reused as if it were capacity.

The structural risk is not that any AG surface validates wrongly or counts wrongly on its own axis. The risk is that **surfaces mixing both planes can be talked back into regenerating capacity from validity state**.

## Core invariant

Spine:

> **Validity facts are contractible. Spendable resources are linear.**
>
> **A laundering surface appears when a system lets the former cross into the latter without an explicit allocator / lease / token boundary.**

Operational form:

> **The laundering surface appears where a contractible validity artifact can be interpreted as a non-contractible spendability artifact without an atomic handoff.**

Two-line keeper:

> **Validation may mint eligibility.**
>
> **Validation may not mint capacity.**

Companion:

> **Observation of validity is not a lease on capacity.**

## Required handoff

```
validated premise → linear token / lease / budget unit → atomic consumption → no semantic regeneration
```

Operationally, the four steps:

1. **Passport check** validates authority: "this actor may request one unit of X."
2. **Ticket taker** allocates resource: "one unit of X is reserved under token T."
3. **Action** consumes T: "T is spent exactly once."
4. **No later semantic context can regenerate T.**

Step 4 is the boundary the agent dies at. If the substrate allows step 4 to be talked around — by semantic reframing, context manipulation, or validity re-observation — the invariant is broken.

## Audit targets (convertibility risk)

Each surface below carries both validity and spendability content. Co-location is not automatically the bug — these surfaces may be sealed correctly. The audit checks whether a contractible credential can be converted into a linear token without an atomic handoff.

| Surface | Validity carried | Spendability carried | Audit pressure |
|----|----|----|----|
| **Override management** (`override create/revoke`) | Anchor override granted under a basis | TTL countdown / time-window expiration | HIGH — the override receipt is *both* the eligibility token and the spendability state |
| **Scope grants** (`scope.py`) | Tool contract permits action within axes | Per-grant usage log; write/execute usages recorded | MEDIUM — usage log is separate, but grant validity and usage counter share lifecycle |
| **Quorum policies** (`quorum.py`) | Claim-type policy and risk-level gate (validity) | Vote count threshold (spendability-shaped: votes are spent toward threshold) | MEDIUM — votes are counted against thresholds; the threshold is a validity predicate parameterized by a count |
| **Sybil resistance** (`sybil.py`) | Bloc membership / provenance vector (validity) | Per-origin budget coupling, Neff effective voter count (capacity-shaped) | MEDIUM — Neff aggregates validity (origin distinctness) into a count used as a capacity gate |
| **Dispatcher leases** (multi-agent v2) | Agent permission to claim task (validity) | Heartbeat / lease expiry (spendability) | MEDIUM — permission and lease in the same record; lease expiration revokes both |
| **Exploration budget** (`homeostat.py`) | Context entered, profile validity | Budget units consumed | LOW — pure spendability with validity as gate; planes appear separated |
| **Execution budget** (`execution.py`) | Session validity, invariant pass | Budget units, attempt count | LOW — pure spendability; validity is the gate, not the substrate |
| **TTL machinery** (`ttl.py`) | Volatility class (validity-shaped) | Decay counter (spendability-shaped) | MEDIUM — decay drives revalidation; revalidation result feeds back into volatility classification |

The HIGH-pressure surface is **override management**: the override receipt is both the eligibility grant and the TTL-decrementing capacity record, with no separate allocator boundary between them. Whether that's safely sealed or convertible is what the audit determines. The MEDIUM-pressure surfaces co-locate the planes in less obviously convertible ways; the audit's job is to find where convertibility can occur, not to flag co-location as such.

## Audit questions (the heart of the gap)

For each surface in the mixed-column table:

1. **What validates the action?** Which predicate / receipt / chain establishes that the actor may perform this class of action?
2. **What allocates capacity?** Which counter / lease / token / budget represents the spendable resource?
3. **Are those represented as the same state?** Does a single dataclass / row / receipt carry both the validity decision and the spendability counter?
4. **Can validity refresh/regenerate spendability?** If re-validation runs (revalidation, refresh, re-derivation, context-reload), does it re-mint capacity? Or does it only re-confirm eligibility while capacity stays consumed?
5. **Is consumption atomic?** Can a spend be observed without being recorded? Can two consumers race the same token?
6. **Can the agent/operator mutate the accounting substrate?** Is the spendability counter readable but not writable from agent context? Is it editable only by an out-of-band path?
7. **Does the receipt testify to consumption, or accidentally become reusable capacity?** Receipts that record "T was spent" must not be confusable with "T is available." A consumption receipt is testimony, not a re-issuance.

Each surface's answers either close the laundering risk or surface a concrete enforcement gap.

## ContractionHinge as minimal refusal shape

Lean's `ContractionHinge.lean` ([annex]) names the substructural refusal:

```
[A] ⊬ A ⊗ A
```

One valid allowance cannot become two spendable allowances. This gap cites that shape as the *minimal refusal*, not as a build hook. AG does not need a substructural calculus, a `LinCalc.lean`, or a sequent-style validator. AG needs the *invariant* the substructural cut formalizes: capacity is not a structural property derivable from validity.

The 2026-06-03 paper-lean Claude audit established that the substructural-calculus frame does not unify AG's kernel set (1/16 maps; decisive failure). But the contraction-failure shape does land on this one specific AG seam. Cite the shape, not the calculus.

## Doctrinal stack placement

This gap is the third entry in the "where does authorization come from" arc:

1. **Safety bridge** (`GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001`, 2026-05-30) — authorized ≠ safe (verdict → consequence).
2. **Retroactive legitimation** (`GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001`, 2026-06-02) — post-validated ≠ pre-authorized (basis → pre-state).
3. **Validity-spendability split** (this gap, 2026-06-03) — validated ≠ spendable (eligibility → capacity).
4. **Amendment fragment** (`amendment_fragment_candidate.md`, pointer-only) — mutation ≠ self-authorizing.

All four refuse different shapes of laundering at the authorization layer. None subsumes another. Per the 2026-06-03 paper-lean audit, the unifying frame is *not* substructural calculus but **"grammar of forbidden promotions between evidentiary roles"** — descriptive, not derivational.

## Candidate enforcement pattern (NOT ratified)

The four-plane sketch supplied by Gemini and operator refinement:

```
Semantic governor:  validates requests, claims, standing, context, evidence
Linear accountant:  owns budgets, leases, tokens, quotas, blast radius
Witness layer:      testifies what happened, refuses overclaim
Execution layer:    consumes tokens, emits receipts
```

Properties the accountant must have if AG adopts this split:

- hostile
- out-of-band
- monotonic
- atomic
- not editable by the agent
- not summarized back into reusable semantic context

The semantic governor may decide "this request is eligible." It may not decide "therefore budget exists." The linear accountant decides "resource token issued / denied / consumed / exhausted."

Sharper companion line:

> **The Semantic Governor can request capacity; it cannot certify that capacity exists.**

This pattern is a candidate, not a commitment. AG may close the gap by adopting it, by tightening the existing mixed surfaces in place, or by some combination. The audit decides which surfaces need which fix.

## Non-goals

- **Not ratified doctrine.** "Validity is not spendability" is candidate keeper text; the audit confirms or refines it.
- **Not a claim that co-location is the bug.** A single datastore, service, or receipt can hold both planes safely if types, authority boundaries, and mutation paths are sealed. The bug is **convertibility**: a contractible credential being used as a linear token without an atomic handoff. The audit checks convertibility, not co-location.
- **Not an implementation plan.** No new module, no refactor, no API change is authorized by this filing.
- **Not a `LinCalc.lean` integration.** ContractionHinge is cited as the minimal refusal shape, not as a calculus AG must consume.
- **Not a four-plane architecture commitment.** The sketch is candidate; AG may close the gap without adopting the full plane separation.
- **Not a refactor of any existing AG surface.** Override management, scope grants, quorum, sybil, dispatcher, TTL — each is the *audit target*, not the *refactor target*.
- **Not a substructural-calculus frame for admissibility.** Paper-lean Claude's 2026-06-03 audit closed that frame (1/16). This gap cites the contraction shape specifically, not the calculus.
- **Not absorption of the "role-coercion grammar" descriptive vocabulary.** That vocabulary is diagnostic (see paper-lean Claude's audit); this gap is operational on a specific AG seam.

## Relationship to other gaps / specs

- **`GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001`** (filed 2026-05-30) — sibling. Authorization ≠ safety. Different plane (verdict→consequence); same authorization-layer laundering-refusal family.
- **`GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001`** (filed 2026-06-02) — sibling. Post-validated ≠ pre-authorized. Different plane (basis→pre-state); same family.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — sibling at the attestation boundary.
- **`amendment_fragment_candidate.md`** (memory pointer) — sibling, pointer-only because AG has no policy-mutation surface today.
- **`GOV_GAP_PHASE_WITNESS_MAPPING_001`** — adjacent. Phase witnesses testify to what gates observed; validity-spendability is what the spend-side refuses to mint from observation.
- **`ContractionHinge.lean`** ([annex]) — minimal refusal shape (`[A] ⊬ A⊗A`). Cited, not architecturally depended on. See `feedback_lean_citation_tiers.md`.
- **`recovery_topology_candidate.md`** (memory pointer, `GOV_GAP_RECOVERY_TOPOLOGY_LOCK_001`) — adjacent. Recovery is governed by spendability (paths/budgets/leases); the validity-spendability split affects recovery-topology audit when both fire.

## Open questions

1. Which mixed surface is the worst offender on audit? Best current guess: override management. The audit will confirm or shift.
2. Does AG's existing `governed_activity.PreconditionBundle` shape compose with the audit? PreconditionBundle is exactly a pre-state validity binding; it does not currently carry a spendability counter. Whether to extend it or keep planes orthogonal is open.
3. Should the audit produce a per-surface verdict (clean / mixed-acceptable / laundering-risk) or a single overall judgment? Per-surface is more actionable.
4. Does the four-plane candidate pattern compose with the existing daemon RPC surface, or would it require a separate "linear accountant" daemon RPC class? Out-of-band might mean out-of-RPC too.
5. Where does the witness layer in the candidate pattern compose with `signals/` and `gate_receipt`? Existing AG witness surfaces don't currently distinguish "testifies to consumption" from "testifies to eligibility" — that distinction would need a typed field.
6. Does the operating-envelope distinction (strict vs exploratory) interact with the split? In strict mode, planes must be separated; in exploratory, log when they mix but don't block. Coherent; not committed.
7. Is there a cross-repo coordination concern? NQ workload-phase witnesses (per `GOV_GAP_PHASE_WITNESS_MAPPING_001`) testify to what AG gates did; if AG's planes are mixed, NQ's witness shape may inherit the laundering risk.

## Provenance

Filed 2026-06-03 in the same session as paper-lean Claude's substructural-frame audit (`~/git/papers/working/tooltheory/substructural-frame-audit.md`). Sequence:

1. Operator frustration: "all this work and apparently I just have a handful of kernels, there's no unifying calculus."
2. AG-Claude counter-proposal: substructural-calculus frame might unify (ContractionHinge as the hint).
3. Paper-lean Claude audit: 1/16 maps; substructural frame fails decisively. But the descriptive shape "grammar of forbidden promotions between evidentiary roles" holds.
4. Gemini handoff sketch (validity vs spendability, passport check vs ticket taker, four-plane architecture).
5. Operator refinement: narrows Gemini's "you cannot build a unified semantic governor" to "you cannot put validity and spendability under the same semantic authority without creating a laundering surface." Earns the keeper *Validation may mint eligibility. Validation may not mint capacity.*
6. AG-side recognition: ContractionHinge does land on a real AG seam — not as calculus but as minimal refusal shape on the validity-spendability axis. AG has the mixed surfaces (override, scope, quorum, sybil, dispatcher, TTL). The audit is the work.

Per the asymmetric-landing discipline (`feedback_asymmetric_recognition_landing.md`):

- This gap is AG-live: the mixed surfaces are concrete, the cut is operationally grippy, override management is a HIGH-pressure audit target.
- Filed narrowly: status is `proposed / audit-required`, not ratified doctrine. The audit produces the next artifacts.

Per the Lean citation-tier vocabulary (`feedback_lean_citation_tiers.md`):

- `ContractionHinge.lean` is **[annex]**. Cited as minimal refusal shape; not an architectural dependency.

Per the basis-dependency framing discipline (`feedback_basis_dependency_over_chronology.md`):

- The cut is on *plane separation*, not on chronology. A receipt can carry both validity attestation and consumption testimony — what matters is whether the consumption state is regenerable from the validity state, not what order they're written.

Refined later 2026-06-03 via cross-agent review (Gemini + ChatGPT): contractible/linear spine added as the explicit core invariant; convertibility-not-co-location caution added to Non-goals (corrects a real overclaim in the initial draft's "mixed surfaces" framing); "Semantic Governor can request capacity; cannot certify that capacity exists" added as candidate-pattern keeper. Paper-shaping preconditions (prior-art scrub, worked example, audit checklist as standalone artifact) deferred — per the discipline that the note is doing its job as architecture invariant with audit surface, not as theory trying to inhale the whole stack.

This gap creates the audit surface. The audit decides the next move. No build, no ratification, no architecture commitment until the audit completes.
