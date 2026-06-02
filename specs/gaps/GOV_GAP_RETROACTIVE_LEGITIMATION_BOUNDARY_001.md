# GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001

## Title

Agent Governor's standing validator chain (C2-C5) enforces parent-ref content-binding and parentage transitions, but does not refuse receipts whose authorization basis depends on the post-state the operation produces. The cut is: `AuthorizedIn(S, O)` cannot be inferred from `PostValidated(S, O)` where validation depends on `S' = apply(S, O)`. Lean's `RetroactiveLegitimation.lean` (2026-06-02) formalizes the boundary; AG has the live authorization layer but no named refusal at this cut.

## Status

Gap spec — containment vessel. **No refusal predicate authorized, no validator-chain change proposed, no implementation drafted.** Names the cut, the AG-side surfaces under audit, and the forcing-case posture. Candidate, non-binding.

## Filed

2026-06-02. Forcing context: drop of `RetroactiveLegitimation.lean` in lean repo (commit `5b5d79d`, 2026-06-02). Sibling of `GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001` (filed 2026-05-30) and part of the "where does authorization come from" doctrinal arc that also includes `AmendmentFragment.lean` (forward mutation; pointer-only, see `~/.claude/projects/-home-jbeck-git-agent-gov/memory/amendment_fragment_candidate.md`).

## Origin

The Lean module formalizes the cut:

> `PostValidated(S, O)` (the post-state carries a witness for `O`) does NOT imply `AuthorizedIn(S, O)` (the pre-state carries one).

Specimen: `install W` adds `(install W, W)` to the state. T4 — the headline refusal — proves the transition is inadmissible even though T2 shows the post-state validates. Authorization is anchored at `S`, never at `apply S O`.

The operational keepers:

> **Post-state witness is not pre-state authority.**
>
> **An operation cannot be authorized by evidence whose standing exists only because the operation succeeded.**

### Framing: dependency, not chronology

The forbidden move is **post-state dependency laundering**, not timestamp ordering. A receipt can be generated later (after the operation, after `S'` exists) while still testifying to a basis valid at `S`. What cannot happen is the basis itself depending on `S'` — on the post-state the operation produces. The cut is on dependency direction, not wall-clock order.

This matters because timestamp-shaped framings invite workarounds ("but we can mint the receipt before the operation runs") that miss the actual structural risk. The structural risk is dependency: did the basis stand at `S`, or does it require `S'` to stand?

This pairs with the 2026-05-30 cut (`GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001`):

| Earlier cut (safety-bridge) | This cut (retroactive-legitimation) |
|----|----|
| Authorization ≠ safety | Authorization ≠ self-supporting witness |
| Bridge between authorized verdict and value-preserving consequence | Basis dependency between authorization and the post-state operation produces |
| Refuses laundering authorized → safe | Refuses laundering post-validated → pre-authorized |

Both refuse different shapes of laundering at the authorization layer. Neither subsumes the other.

## Problem Statement

AG's standing validator chain enforces structural authorization discipline:

- **C2 (StandingChainValidator):** parent_refs are content-bound (§6 content-bound parents + cycle detection); parentage transitions per §5.1/§5.4; subject_derivation per Q2 (same_subject byte-equality, scope_narrowing prefix containment, aggregation_of completeness); policy binding per §8.
- **C3 (Standing Schema Discipline):** strict `sha256:[64-hex]` hash format, structured `Check` types, AUTHORIZE_REQUIRED_CHECKS (standing/admissibility/scope/budget).
- **C4 (Check Basis Discipline):** `Check.basis` is structured `CheckBasis` (summary + rule_id + non-empty `inspectable_refs`).
- **C5 (Continuity Basis):** `continuity_basis` is presence-as-claim block; four sub-bases (identity, provenance, evidence, operator_confidence); role-gated to CLAIMABLE_ROLES.

None of these refuses the retroactive-legitimation laundering directly. Where the chain interacts with the cut:

| Validator layer | What it checks | Why it doesn't close this cut |
|----|----|----|
| C2 parent_refs content-bound | Parent receipts must be content-addressable and not cycle | Parent-binding is *receipt-to-receipt* lineage. The retroactive cut is *receipt-to-pre-state-basis* binding: does this receipt's authorization basis stand at `S`, or does it require `S'`? |
| C2 subject_derivation | `same_subject` byte-equality, `scope_narrowing` prefix containment | Subject-derivation is about the *target* of authorization, not the dependency direction of the basis |
| C3 AUTHORIZE_REQUIRED_CHECKS | standing/admissibility/scope/budget checks present | The four required checks are presence-of-check checks; none explicitly verifies that the basis stood at the pre-state |
| C4 CheckBasis.inspectable_refs | Refs are non-empty list of non-empty strings | Refs format-validated; whether their *standing* depends on the post-state is not asserted |
| C5 continuity_basis.evidence_basis | Evidence sub-basis present, role-gated | Presence-as-claim; the *adjudicative* question of "does this basis stand at the pre-state" is descriptive, not enforced (per the C5 design note: operator_confidence_basis is descriptive only) |
| C5 continuity_basis.provenance_basis | Provenance sub-basis present | Same as above: presence-as-claim, not pre-state basis-dependency enforcement |

Each surface is correct on its axis. The gap is the missing **basis-dependency** predicate: does the authorization basis stand at `S`, or does it require `S' = apply(S, O)` to stand?

## Failure Mode

The laundering path:

1. Operation `O` is proposed against pre-state `S`.
2. The proposing actor lacks a basis for `O` that stands at `S`.
3. `O` runs and produces post-state `S'`. `S'` contains evidence `E` whose standing depends on `S'` — `E` exists / is valid / has the role it claims *because `O` succeeded*.
4. A standing receipt `R` is minted authorizing `O`. `R`'s `CheckBasis.inspectable_refs` cite `E`.
5. The validator chain accepts `R`:
   - Parent-refs are content-bound (C2 passes — `E` has a valid sha256 hash, no cycles).
   - Schema is valid (C3 passes — `E`'s hash is well-formed).
   - CheckBasis is structured (C4 passes — `E` is a non-empty ref).
   - Continuity_basis presence-as-claim is intact (C5 passes if the role requires it).
6. `R` is treated downstream as authorization for `O`. But the basis citing `E` cannot stand at `S` — `E`'s standing exists only because `O` succeeded. `R` is retroactive legitimation, not authorization.

The structural risk is not that any check is wrong on its own axis. The risk is that **the validator chain accepts authorization whose basis depends on the post-state**. The Lean witness (`install W` specimen) is the lived form: the operation produces the very basis on which authorization stands.

Note the dependency framing: it is not required that `E` be minted *after* `O` in wall-clock time. `E` could exist as bytes before `O` runs. What matters is whether `E`'s *standing as a basis for authorizing `O`* depends on the post-state `O` produces. The forbidden shape is structural, not temporal.

This is a different shape from `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` (which names the attestation-vs-authority kernel split at the receipt-emission boundary) and from `GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001` (which names authorization ≠ safety at the verdict→consequence boundary). All three are siblings:

| Sibling | What it refuses |
|----|----|
| Sealed-outcome boundary | "the seal certifies the outcome" |
| Authorization-safety bridge | "the verdict certifies the safety" |
| Retroactive-legitimation (this gap) | "the post-state supplies the basis for its own production" |

Each is a distinct authorization-layer laundering refusal. None subsumes another.

## Existing Governor Coverage (Sibling Surfaces)

| Surface | Carries part of the predicate? |
|---|---|
| Standing validator C2 (parentage transitions) | Adjacent — receipt-to-receipt lineage, not receipt-to-pre-state-basis dependency |
| Standing validator C2 (subject_derivation) | Adjacent — subject of authorization, not basis dependency direction |
| C5 continuity_basis (evidence_basis, provenance_basis) | Closest — presence-as-claim of basis structure, but adjudicatively *descriptive only* per current C5 design |
| `gate_receipt.py` (subject_hash, evidence_hash, policy_hash, timestamp metadata) | Carries timestamp but timestamp is wall-clock, not dependency — does not refuse post-state-dependent bases |
| `governed_activity.py` (FactObservation, PreconditionBundle, AttemptRecord) | Closest behavioral analog — explicit pre-state `precondition_bundle` and attempt-time `fact_observation`. PreconditionBundle is exactly a pre-state basis binding, fingerprinted and content-addressed. Drift verdict at attempt time refuses some retroactivity classes but does not formalize the cut |
| `signals/` (source_receipt_ids, monotonic propagation) | Tracks lineage; not a basis-dependency predicate |
| `evidence_gate.py` (claim extraction, custody scoring) | Custody is about evidence collection, not basis-dependency direction |
| Intent compiler (IntentFormSchema, deterministic compilation) | Pre-operation; selection from templates, not adjudication of basis dependency |

Note: `governed_activity.py` is the closest existing AG surface to a retroactive-legitimation refusal. Its `PreconditionBundle` is exactly a pre-state basis binding, fingerprinted and content-addressed. The shape composes naturally with this cut, but the validator chain does not currently consume `governed_activity` predicates as basis-dependency input.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Names the cut — post-state witness is not pre-state authority — and refuses the laundering path explicitly. Framing is dependency-direction, not chronology.
2. Identifies the four validator-chain layers (C2-C5) and what each does/doesn't enforce relative to the cut.
3. Records that `governed_activity.py`'s `PreconditionBundle` shape is the closest existing AG analog; whether to lift the predicate into the validator chain is implementation territory.
4. Identifies forcing cases that would justify selecting a refusal: a postmortem where a receipt was accepted whose authorization basis depended on the post-state the operation produced; an audit where evidence_basis presence (C5) was satisfied but the basis's standing required the operation to have succeeded; a session-resume where a capsule's authorization witness cited a basis whose standing depended on the resumed state.
5. **Operational test:** any validator path that accepts an operation must identify the authority basis valid *before* the operation's consequences are applied — i.e., must show the basis stands at `S`, not just at `S'`.
6. Does not specify implementation. Adding a basis-dependency predicate to C2 (a new `pre_state_basis_check`), promoting C5 evidence_basis from descriptive to adjudicative, or integrating `governed_activity.PreconditionBundle` into validator-chain enforcement are each coherent paths; none is committed.

## Doctrine (proposed; not yet ratified)

> **Post-state witness is not pre-state authority.**
>
> **An operation cannot be authorized by evidence whose standing exists only because the operation succeeded.**
>
> **The authorization basis must be valid in the pre-state and must not depend on the post-state produced by the operation. The validator chain must identify the basis at the pre-state, not infer it from the post-state.**

Candidate doctrine until a forcing case selects an enforcement path.

## Non-goals

- **Not a refactor of the validator chain (C2/C3/C4/C5).** Each version is correct on its axis. The gap is the missing basis-dependency predicate, not a wrong predicate on any existing layer.
- **Not a chronological/wall-clock ordering enforcement.** Receipts can be generated after the operation they authorize; the cut is on basis dependency, not timestamp. Implementations that key on wall-clock timestamps miss the actual structural risk.
- **Not a general policy-amendment calculus.** Forward mutation (policy change) is a *sibling* concern; see `~/.claude/projects/-home-jbeck-git-agent-gov/memory/amendment_fragment_candidate.md` for the pointer reserving `GOV_GAP_AMENDMENT_FRAGMENT_001`. Pointer-only because AG has no policy-mutation surface today.
- **Not a promotion of `operator_confidence_basis` from descriptive to adjudicative.** Per the C5 design note, that promotion is "a hotter seam requiring its own Q4 supersession." This gap does not propose it.
- **Not a port of `RetroactiveLegitimation.lean` definitions.** AG's instantiation, if forced, will be a typed predicate over `(GovState, Operation, Witness)`, not a port of `PostValidated` / `AuthorizedIn`.
- **Not a global basis-dependency enforcement.** The cut is per-receipt at the validator chain. AG does not certify "no retroactive legitimation has ever occurred system-wide."
- **Not a ratification of the Lean cut as AG doctrine.** The Lean module is annex-tier (compiled, conceptually useful, not an architectural dependency). The cut is the *forcing observation*. AG's doctrine waits on the enforcement-path selection.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001`** — Sibling, filed 2026-05-30. That gap names authorization ≠ safety at the verdict→consequence boundary. This gap names authorization ≠ self-supporting witness at the basis→pre-state boundary. Both are authorization-layer laundering refusals; neither subsumes the other.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Sibling. Names receipt_kernel ≠ authority_kernel at the *attestation* boundary. Different surface, same authorization-discipline family.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Adjacent. Names missing content-semantic enforcement on `admissibility_check`. Composes with this gap if the basis-dependency predicate would inspect basis content.
- **`GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001`** — Adjacent. Names qualification-vs-drift at the per-witness level. Composes at the validator-chain layer if witness qualification regimes need to bind to pre-state basis.
- **`GOV_GAP_PHASE_WITNESS_MAPPING_001`** — Adjacent. Phase witnesses testify to what gates observed in which window; retroactive-legitimation is what the basis-dependency refuses at the authorization layer.
- **`AmendmentFragment.lean`** — Sibling Lean module (pointer-only on AG side as `GOV_GAP_AMENDMENT_FRAGMENT_001` candidate). Forward mutation cut; this gap is the backward legitimation cut. The arc as a whole is "where does authorization come from."
- **`RetroactiveLegitimation.lean`** — Formal target (annex-tier per the Lean dependency vocabulary; see `~/.claude/projects/-home-jbeck-git-agent-gov/memory/feedback_lean_citation_tiers.md`). AG's instantiation, if forced, would not port the Lean definitions; it would consume the cut they formalize.
- **Standing validator chain (C2-C5)** and **`governed_activity.py`** — The AG surfaces under audit. None is wrong; the gap is the missing basis-dependency predicate composed across them.
- **Doctrinal stack (2026-05-30 / 2026-06-02):**
  1. Safety bridge: authorized ≠ safe
  2. Retroactive legitimation: post-validated ≠ pre-authorized
  3. Amendment fragment: policy mutation ≠ self-authorizing (pointer-only)
  4. Contraction hinge: warrant reuse is a structural resource issue (cite-only)

## Open Questions

1. Which validator layer is the right home for the predicate? C2 (parentage discipline could extend to basis-dependency), C5 (evidence_basis could be promoted from descriptive to adjudicative), or a new C6 layer? Each is coherent.
2. Does `governed_activity.PreconditionBundle` already implicitly enforce the cut for the surfaces that consume it? If yes, the gap may close by integrating preconditions into validator-chain consumption rather than adding a new predicate.
3. Does the receipt's `policy_hash` axis (content-addressed at receipt mint time) already implicitly bind basis dependency? `policy_hash` pins the policy version under which the verdict was earned; it does not pin whether the basis itself stands at the pre-state. Adjacent axes, different cuts.
4. Where in the receipt lifecycle does the predicate live? Three coherent positions: (a) at validator chain admission (refuse the receipt before storage); (b) at receipt consumption (refuse to act on retroactive receipts); (c) at gate emission (refuse to mint receipts whose basis depends on the post-state). Each has different blast radius.
5. Does this gap interact with the operating-envelope distinction (strict vs exploratory)? In strict mode, retroactive legitimation → block; in exploratory, log + warn. Coherent; not committed.
6. How does this compose with session-continuity capsule resume? A capsule resumes with an authorization witness from a prior session; if the resumed state itself is part of the basis, the basis-dependency cut may need a different formulation across the session boundary (does the basis stand at the *pre-resume* state, or the *post-resume* state?).
7. What is the right operational form of the basis-dependency check? Three coherent shapes: (a) the basis is content-addressed in a store whose content predates the operation; (b) the basis is a `PreconditionBundle` that was sampled and fingerprinted at pre-state observation; (c) the basis is recomputable from pre-state inputs alone (a determinism check). Each rejects different laundering classes.

## Provenance

Filed 2026-06-02 after a sweep of `~/git/lean/LeanProofs/Admissibility/` covering the 2026-06-02 drops (AmendmentFragment, ContractionHinge, RetroactiveLegitimation) and 2026-06-01 drops (BoundaryWitness, ParameterizedMerge). The three June-02 modules form a coherent arc — "where does authorization come from" — with AmendmentFragment naming forward mutation refusal, RetroactiveLegitimation naming backward legitimation refusal, and ContractionHinge naming the structural underlay.

Initial draft (2026-06-02 morning) framed the cut as temporal/chronological ordering ("witness must precede the act it authorizes"). Operator correction same day: the framing is too wall-clock-shaped. A receipt can be generated later while still testifying to a pre-state basis; what cannot happen is the basis itself depending on the post-state. The forbidden move is **post-state dependency laundering**, not timestamp ordering. This revision (2026-06-02 PM) shifts framing throughout. See `~/.claude/projects/-home-jbeck-git-agent-gov/memory/feedback_basis_dependency_over_chronology.md` for the rule.

Per the asymmetric-landing discipline (see `~/.claude/projects/-home-jbeck-git-agent-gov/memory/feedback_asymmetric_recognition_landing.md`):

- RetroactiveLegitimation lands as a filed gap spec — sibling of safety-bridge, the validator chain is AG's live authorization layer, the cut is operationally grippy.
- AmendmentFragment lands as a memory pointer reserving `GOV_GAP_AMENDMENT_FRAGMENT_001` — AG has no policy-mutation surface today; filing creates architecture gravity.
- ContractionHinge / BoundaryWitness / ParameterizedMerge / BudgetMerge / MergeConflict / GuardCollapse: cite-don't-extract.

Per the Lean citation-tier vocabulary (see `~/.claude/projects/-home-jbeck-git-agent-gov/memory/feedback_lean_citation_tiers.md`):

- `CalculusOne.lean` is **[1.0]** — stable enough to pin against.
- `RetroactiveLegitimation.lean` and the rest of the 2026-06-02 drop are **[annex]** — evidence-bearing, conceptually useful, not architectural dependencies.
- This gap cites the annex; it does not architecturally depend on it.

This gap is a containment vessel. It does not authorize a build, ratify a refusal predicate, or commit AG to an enforcement path. It names the cut, the existing partial surfaces, and the forcing-case posture. Enforcement-path selection waits.
