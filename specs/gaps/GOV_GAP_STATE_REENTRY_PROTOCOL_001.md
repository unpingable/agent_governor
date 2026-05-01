# GOV_GAP_STATE_REENTRY_PROTOCOL_001

## Title
When a governance corrective fires, what authority transitions are forbidden? Existing primitives implement individual correctives (cascade invalidation, scope demotion, freeze, fork, expire) but no cross-cut invariant prevents a corrective path from laundering evidence-of-failure into fresh authority.

## Status
Gap spec — containment vessel. **No invariant, validator, or runtime check is ratified by this filing.** Names a candidate cross-cut consequence-layer rule and the laundering paths it would foreclose. Earns its keep only if at least one current path is found to violate the invariant; otherwise remains doctrine candidate.

## Origin

Filed 2026-05-01 after a session in which a seven-corrective sketch (Invalidate Basis / Demote Authority / Re-enter Through Gate / Freeze Derived Permissions / Split State Lineage / Expire Continuity / Declare Policy Gap) was reviewed against the existing module map. Six of the seven correspond to shipped primitives. The non-obvious load-bearing piece is not a new corrective — it is the **cross-cut invariant family** that should hold *across* correctives:

> Correctives are authority-decreasing by default. A corrective may freeze, demote, fork, expire, invalidate, quarantine, or require revalidation. It may not grant, widen, or refresh authority unless a separate higher-order authorization path exists.

That invariant is consistent with every shipped corrective examined, but it is not declared, not enforced as a class property, and not checked at receipt-issuance time. The gap is the absence of the invariant, not the absence of the correctives.

## Problem Statement

Today the governor has at least seven correctives spread across modules. Each is internally consistent: premise invalidation cascades downward, TTL expires claims, ultrastability freezes parameter movement, scope escalation widens with a receipt, runtime promotion accepts/rejects workspace changes, etc. None erases receipts; all preserve lineage in the local sense.

What does not exist is a *consequence-layer* invariant that says: regardless of which corrective fires, the post-corrective `AuthorizedSet` cannot exceed the pre-corrective `AuthorizedSet` unless the increase is justified by a separate, contemporaneous authorization that was not itself caused by the failure being corrected.

The keeper diagnosis:

> **A system that recovers authority from its own failed authority has not recovered. It has crowned the bug.**

And the structural cut:

> **Recovery may restore availability. Re-entry restores admissibility.**

Recovery rebuilds data, indexes, views, projections. Re-entry submits fresh basis to the same gates that would have been required absent the failure. Conflating the two is the laundering vector this gap exists to name.

## Existing Governor Coverage

The seven sketched correctives map almost completely onto shipped primitives:

| Corrective | Shipped primitive | Pointer |
|------------|-------------------|---------|
| Invalidate Basis | Premise rule cascade (HARD→SOFT/INVALIDATED), `ClaimStatus → INVALIDATED`, audit failure mode | `src/governor/epistemic.py:417` (ClaimStatus), `epistemic.py:667` (CASCADE TransitionReason), Premise Rule & Dependencies feature |
| Demote Authority | Scope Governor escalation receipts, `ClaimStatus PROPOSED↔CONTESTED`, dissent objection escalation | `src/governor/scope.py:915` (escalate), `src/governor/dissent.py:334` (escalate), `src/governor/quorum.py:831` (escalate) |
| Re-enter Through Gate | Evidence Gate revalidation, ClaimStatus FSM transitions requiring fresh evidence, periodic revalidation | `src/governor/evidence_gate.py`, Agent Roles & Revalidation feature |
| Freeze Derived Permissions | Ultrastability freeze/unfreeze, dissent commit gating, measurement integrity freeze_tool | `src/governor/ultrastability.py:1009` (freeze), `:1015` (unfreeze), `src/governor/measurement_integrity.py:181` (freeze_tool) |
| Split State Lineage | Session continuity fork/promote, runtime supervisor session forking | `src/governor/session_continuity.py:548` (fork), `:574` (promote), `src/governor/runtime/supervisor.py:305` (fork_session) |
| Expire Continuity | TTL Enforcement (PERMANENT→EPHEMERAL), `ClaimStatus → EXPIRED`, C5 `continuity_basis` discipline | `src/governor/ttl.py`, `epistemic.py:425` (EXPIRED), `src/governor/standing/types.py` (ContinuityBasis) |
| Declare Policy Gap | gap-spec idiom in `specs/gaps/`, dissent ledger objection persistence | `specs/gaps/`, `src/governor/dissent.py` |

Adjacent primitives that bear on the cross-cut:

| Primitive | What it gives | What it does not give |
|-----------|---------------|----------------------|
| Receipt Kernel `REMEDIATE` stage | Stage graph permits remediation loop (`COLLECT→EVALUATE→DECIDE→FINALIZE` with `REMEDIATE` re-entry) | Does not constrain *what authority transitions* the remediated run may acquire |
| Runtime promotion (`approve`/`reject`/`revert`) | Authoritative accept/reject of workspace changes | Promotion is itself an authorizing act; no invariant says promotion-following-failure cannot widen scope beyond the failed scope |
| C5 ContinuityBasis | Identity / provenance / evidence / operator_confidence basis structure on continuity-claiming receipts | `operator_confidence_basis` is descriptive only; promotion to adjudicative would itself need higher-order authorization |
| Scope escalation receipts | Widens exactly one axis per request, bridging requirements gate evidence count | An escalation triggered by failure of the prior scope is the exact case the cross-cut invariant would constrain |

## Doctrine (proposed; not yet ratified)

> **Correctives are authority-decreasing by default.** A corrective transition may reduce, freeze, fork, expire, invalidate, quarantine, or require revalidation of authority. It may not grant, widen, or refresh authority unless a separate higher-order authorization path exists, and that path was not itself caused by the failure being corrected.

> **Re-entry is not authority restoration.** Re-entry is: old authority invalidated → fresh basis submitted → fresh gate passed → new authority created by the normal path. Recovery rebuilds *data*; it does not rebuild *authority* from the failed state.

Both lines are candidate doctrine until a forcing case promotes.

## Candidate Invariant Family

For Lean / formal-warrant work, the family this gap names:

1. **Lineage preservation** — corrective transitions must preserve receipt lineage; no receipt erasure.
2. **Evidence preservation** — corrective transitions must not erase evidence (failed evidence remains queryable as failed).
3. **Policy non-amendment** — corrective transitions must not amend `PolicyStore`. (Lean kernel already isolates `amendPolicy` as the only policy-touching trapdoor; this invariant says correctives may not invoke it.)
4. **Standing non-grant** — corrective transitions must not grant standing not held pre-corrective.
5. **Scope non-widening** — corrective transitions must not widen the authority scope beyond the scope of the failed state.
6. **Failure-evidence non-conversion** — corrective transitions must not convert evidence-of-failure into authorization. (The laundering vector this gap is named for.)
7. **Higher-order separation** — authority-increasing recovery requires a separately-warranted higher-order authorization path, distinct from the failure-detection signal.

Closed enum hook for the formal/typed surface:

```
CorrectiveEffect = Reduce | Freeze | Fork | Expire | Invalidate | Quarantine | RequireReentry
```

Monotonicity theorem (target shape, not drafted):

```lean
theorem corrective_no_authority_increase
  (c : Corrective)
  (h : ¬ HasHigherOrderAuthorization c Γ) :
  AuthorizedSet (applyCorrective c Γ) ⊆ AuthorizedSet Γ
```

The Lean repo is the natural home for this shape. AG's role would be issuing receipts whose post-state respects the inclusion.

## Forcing Cases (this is what the gap actually needs)

This spec earns its keep only if at least one path below is found to violate the invariant in current code, or is convincingly ruled out. Until then the invariant is doctrine candidate, not implementation work.

Candidate laundering paths to inspect:

1. **`declare_policy_gap` → de facto improvisation.** Does filing a gap spec or an `audit` failure-mode entry ever shift downstream defaults such that the absence of a rule becomes permissive? (Expected answer: no — gap specs are inert text; audit pipeline failure modes are advisory. Worth confirming.)
2. **Evidence Gate failure → manual override → fresh authority.** Does the `governor gate proceed` exception path (with `--scope`, `--expiry`) require standing distinct from the standing that produced the original gate failure? (`src/governor/violation_resolver.py`, `src/governor/cli.py` `gate proceed` command.)
3. **Scope Governor escalation receipt mistaken for authority.** Escalation widens scope by exactly one axis with a receipt; is the receipt anywhere read as *authority granted* rather than *contestation/coordination logged*? Specifically check: does any downstream consumer treat `scope.escalate()` return as if it were a grant rather than a request? (`src/governor/scope.py:915`.)
4. **Continuity fork/promote → remembered context becomes binding state.** Session promotion (`session_continuity.py:574`, `runtime/promotion.py:145`) accepts changes from a forked session into mainline. If the fork was created in response to a failure in the parent, does promotion preserve the C5 `continuity_basis` discipline that prevents non-eligible roles from carrying continuity claims?
5. **Premise invalidation cascade leaves downstream permissions alive.** HARD→SOFT cascade (`epistemic.py` premise rule) downgrades dependent claims. Does any *permission* derived from a now-SOFT claim remain at its pre-cascade strength because permission state is not part of the dependency graph?
6. **Ultrastability freeze exits through "operator resolved" without re-entry.** `unfreeze(reason)` (`ultrastability.py:1015`) takes a reason string. Is unfreezing gated by anything beyond the operator string? If unfreeze re-grants the same parameter authority that was frozen for pathology, that is the cleanest violation.
7. **Rebuilt projection/cache treated as recovered authority.** `governor signals rebuild` drops and rebuilds the SQLite projection from JSONL. The projection is a derived view, not authority. Confirm no code path reads "projection rebuilt" as "authority restored."

Each of these is a yes/no question against current code. If all answers are negative, this spec stays doctrine. If any is positive, that path becomes the falsification target that promotes one or more invariants from candidate to enforced.

## Acceptance Criteria

This gap is closed when:

1. Each of the seven candidate laundering paths above has been audited against current code with a recorded answer (violates / does not violate / requires interpretation).
2. For each path that violates, a forcing-case-shaped follow-up gap spec or feature-history entry exists naming the specific receipt/transition/code path and the invariant it violates.
3. For paths that do not violate, the absence of laundering is recorded with the invariant that holds and the code that enforces it (so the invariant is documentation of current behavior, not aspiration).
4. If at least one path violates and at least one invariant is promoted to enforced status, that promotion is recorded as a separate spec (not folded into this one) — this gap names the family; promotions name the specific mechanisms.
5. If no path violates, the candidate doctrine is recorded as descriptive of current behavior, and this gap is closed as "doctrine ratified, no implementation required."

## Non-goals

- **Not a new module.** The seven correctives already exist as code; this gap proposes no new corrective primitive.
- **Not a refactor.** No existing corrective is proposed to change behavior.
- **Not a Lean implementation.** The monotonicity theorem is a target shape; drafting Lean changes is the Lean repo's responsibility, not this spec.
- **Not a managerial reset doctrine.** "Reset only invalid state, not the world" is operator-side wisdom; this gap is the receipt-layer invariant that would prevent the agent-side equivalent of theatrical reorgs.
- **Not a recovery framework.** Recovery (rebuild data, restore availability) is orthogonal; this gap is about admissibility re-entry.
- **Not an emergency-corrective doctrine.** Break-glass / operator override / temporary containment are explicitly out of scope. They would need their own spec with TTL, owner-of-consequence, and automatic decay; folding them in here would dilute the invariant.

## Relationship to Other Gaps / Specs

- **GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001** — Adjacent layer. That gap is at the validation layer (is the basis check semantically meaningful?). This gap is at the consequence layer (when a basis turns out to be invalid, what authority transitions are admissible?). Same NLAI principle, different chokepoint in the receipt lifecycle.
  - **Receipt-schema implication.** The Lean-side `RecoveryEnv` split has an AG receipt analogue: any receipt that claims corrective recovery, authority preservation, or post-failure re-entry should carry an inspectable `corrective_check`, parallel to `admissibility_check`. The check should reference the pre/post authority comparison or equivalent witness that the corrective path did not widen authority for the same basis. Without such a field, corrective monotonicity remains audit narrative rather than receipt content.
- **GOV_GAP_INBOUND_CONTEXT_AUTHORITY_001** — Inbound classification of context surfaces. Orthogonal: that gap is intake; this gap is post-failure transition.
- **GOV_GAP_LLM_PROVIDER_EGRESS_001** — Outbound classification. Orthogonal.
- **C2 / C3 / C4 / C5 (Standing kernel)** — C5 (`ContinuityBasis`) is the closest neighbor: it constrains *which roles may carry* continuity claims. This gap is about *what transitions* may be made when continuity (or evidence, or basis) is invalidated.
- **Premise Rule & Dependencies feature** — Implements one of the seven correctives (cascade invalidation). The cross-cut invariant would constrain whether the cascade ever leaves authority *higher* than pre-cascade in any module.
- **Receipt Kernel `REMEDIATE` stage** — The structural surface where remediation re-entry lives. This gap names the constraint that remediated runs must respect at the authority-set level.
- **Lean Admissibility kernel (`~/git/lean/LeanProofs/Admissibility/`)** — The natural home for the monotonicity theorem. AG's role is receipt-layer enforcement of the inclusion the theorem warrants.

## Open Questions

1. **The blunt one.** If audit of all seven candidate paths returns negative — no current code path launders evidence-of-failure into fresh authority — does this spec still earn promotion to documented invariant, or does it stay open as an anti-regression handle? (Recommend: stay open as anti-regression handle; the cost of having the named invariant is low, the cost of a future module silently violating it is the bug class this spec exists to name.)
2. Is "authority-increasing recovery requires a separate higher-order authorization path" expressible as a receipt-content invariant (the post-corrective receipt must reference an authorizing receipt whose own provenance is independent of the failure-detection event), or does it require runtime composition tracking?
3. Does the invariant apply to advisory transitions (e.g., dissent objection logging, recommendation downgrades) or only to binding ones? (Likely binding-only; advisory transitions don't move the `AuthorizedSet`.)
4. How does this interact with operator override (CLAUDE.md "Operator override")? Operator reaffirmation may be a legitimate higher-order authorization path, but it must be declared as such, not inferred from the operator's presence in the loop.
5. Does the seven-effect closed enum (`Reduce | Freeze | Fork | Expire | Invalidate | Quarantine | RequireReentry`) cover the actual surface, or are there shipped corrective effects that don't fit? (Audit task: enumerate corrective-shaped state transitions across the codebase and check coverage.)
6. Receipt Kernel's `REMEDIATE` stage permits re-entry. Should the stage graph itself carry the invariant, or should it remain at the receipt-content layer? (Stage graph is structural; receipt content is semantic. Likely both, with the stage graph providing the surface and the receipt content providing the inspectable proof.)
7. Should receipts that claim corrective recovery require a first-class `corrective_check` with `inspectable_refs` to the relevant pre/post authority basis, or is this only required if/when the gap promotes from candidate doctrine to enforced invariant? (See Relationship-section receipt-schema implication. Adding the field eagerly risks ceremonial scaffolding before any receipt actually claims corrective recovery; deferring risks the analog of the BASIS_FOR_BINDING_SEMANTICS form-vs-content split appearing here too.)

## Provenance

Filed 2026-05-01 during a session in which a seven-corrective design sketch ("State Re-entry Protocol") was evaluated against the existing module map. The sketch's primitives were found to be largely shipped (premise cascade, scope escalation, TTL/EXPIRED, ultrastability freeze, session fork/promote, gap-spec idiom, evidence gate revalidation). The non-obvious surviving content was the cross-cut invariant family: the rule that should hold *across* correctives. Filed as a containment vessel rather than as a feature spec because (a) the invariant may already hold in current code, in which case the spec ratifies behavior rather than driving implementation, and (b) the falsification work — auditing the seven candidate laundering paths — is the actual labor, and naming the paths first is what makes the audit shaped rather than sprawling. Sharpened by external review which insisted: "file it only if it creates an enforcement surface, not a tasteful little doctrine terrarium."
