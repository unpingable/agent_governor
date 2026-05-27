# GOV_GAP_CORRECTIVE_TRANSITION_BOUNDARY_001

## Title
AG has recovery-shaped primitives (scar, anneal, shield) but does not type the distinction between **corrective** and **forward authority-increasing** transitions. Lean's `Corrective.lean` now formalizes that boundary; the AG-side enforcement surface has not caught up.

## Status
Gap spec — containment vessel. **No new transition types, no rename of scar/anneal/shield, and no enforcement behavior is ratified by this filing.** Names the laundering shape and the keeper phrasing; future forcing cases promote.

## Origin

Filed 2026-05-08 after the Lean Admissibility kernel grew a fifth module (`Corrective.lean`, added 2026-05-01) and a sibling boundary module (`CorrectiveBoundary.lean`, added 2026-05-07) that together formalize a boundary AG already had vocabulary for but no typed enforcement against:

> **A corrective recovery transition must not, on the same basis, increase the authorized action set.**

The Lean kernel proves a same-basis-K corrective Step cannot turn a non-authorized claim into an authorized one; authority-increasing recovery requires a separately classified *forward* transition with fresh basis K'. The AG-side surfaces that perform recovery shapes (`scars.py` annealing, `shield` relaxation, dissent retraction, scar-revoke paths) do not currently sort transitions into corrective vs forward, and do not gate "may this recovery grant new authority?" on a fresh-basis predicate.

This is the recovery-axis complement to `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`. That gap names the missing content-semantic enforcement of admissibility checks at AUTHORIZE issuance. This gap names the missing typed boundary at the moment a *prior* denied or restricted state passes through a healing path.

## Problem Statement

Today AG's recovery-shaped primitives include:

| Surface | What it does | Authority-flow shape |
|---------|-------------|---------------------|
| `Scar.anneal` (`scars.py:142`) | Reduces stiffness toward `anneal_floor` under evidence; never to zero | Restores admissibility *context* — relaxes a prior denial under accumulated evidence |
| `Shield.relax` (`scars.py:358`) | Lowers gate strictness on inputs to a region | Same shape as anneal: prior restriction relaxes under signal |
| Scar-revoke paths (`ScarLedger`) | Removes a scar entirely | Same as above, structural variant |
| Dissent retraction (`dissent.py`) | Removes an objection from a proposal's record | Recovery-shaped at the consensus layer |
| Quarantine release (`drift.py`) | Premise leaves quarantine after revalidation | Recovery at the premise layer |

Each is recovery-flavored. None is currently typed against the question:

> **Does this transition merely restore prior admissibility context, or does it grant new authority that did not exist before?**

The Lean kernel cuts that question at the basis K. Same-K recovery can restore but cannot grant. Fresh-K forward authorization is the legitimate path to authority-increase. AG has no typed reflection of this cut: a scar that anneals to its floor and a fresh authorization for a previously-denied action class are observationally adjacent shapes in the AG ledger, but they are constitutionally different transitions.

The keeper diagnosis:

> **AG can heal. AG cannot currently prove its healing did not mint authority.**

## Failure Mode

The laundering path:

1. An action class is denied under basis K (scar recorded, shield raised, dissent logged).
2. Evidence accumulates against the original failure.
3. A recovery surface — anneal, relax, retraction — runs.
4. The denied action class is now permitted.
5. The recovery surface ran *under K* (same-basis), but the consumer treats the result as if a fresh authority verdict had been issued.

In Lean terms: the system emitted what should have been classified as a forward transition with fresh K', but the recovery surface did not re-derive a new basis. The bridge from "stiffness fell below threshold" to "action may proceed" is entirely in the consumer's head — exactly the same shape as the laundering path named in `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`, but at the recovery valve rather than the authorization valve.

The structural risk is not that anneal is wrong. The structural risk is that anneal's output is treated as authority-equivalent to a forward authorization issued under fresh basis.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `Scar.can_anneal` (`scars.py:135`) | Evidence-gated: requires `required_evidence` count, `anneal_floor` boundary | No basis K associated with the original failure or with the anneal event |
| `Scar.anneal` (`scars.py:142`) | Decay toward floor under evidence | No fresh-basis predicate before granting authority-increase |
| `ScarLedger` | Persists scars, evidence ledger | No typed distinction between "scar restored" and "fresh authority granted" |
| `dissent.py` retraction | Removes objection | No basis re-derivation on retraction |
| Lean `Corrective.lean` | `WeaklyLessPermissive`, `CorrectiveMonotone`, `RecoveryEnv`, `corrective_no_authority_laundering` | Formal target only; AG implementation has not connected scar/shield/dissent recovery to this standard |

## Formal Witness (Target, Not Seam)

The Lean kernel — *Admissibility Calculus 1.0* (concept DOI [10.5281/zenodo.20369489](https://doi.org/10.5281/zenodo.20369489); eight-module public surface aggregated via `CalculusOne.lean`) in `~/git/lean/LeanProofs/Admissibility/` — provides the relevant handles. `Corrective` is **inside** the 1.0 promise; `CorrectiveBoundary` is **annex** (compiled, sorry-free, but explicitly *not* part of the 1.0 compatibility claim — future versions may rename/refactor/absorb without notice):

- `Corrective.lean` — `classify : Step → CorrectiveClass` (total function: `corrective | forward | neutral`); `WeaklyLessPermissive env Γ' Γ` preorder ("every claim authorized at Γ' was already authorized at Γ"); `CorrectiveMonotone env` proof obligation.
- `Corrective.lean` — `RecoveryEnv` bundles a `DerivationEnv` with the `CorrectiveMonotone` witness; `applyCorrectiveRecovery` requires a `RecoveryEnv` rather than a raw `DerivationEnv` (the available-vs-operationally-required distinction).
- `Corrective.lean` — load-bearing corollary `corrective_no_authority_laundering`: same-basis K, a corrective Step cannot turn a non-authorized claim into an authorized one. Same-K is load-bearing; re-entry through a fresh K' via a forward Step is the legitimate path.
- `CorrectiveBoundary.lean` — model-dependence boundary result: confirms the abstract kernel's existential is genuinely model-dependent, demonstrating that the monotonicity guarantee is *constructive* under nondegenerate store ops (not vacuously true).

This kernel is not the gap. It is the standard the AG recovery surfaces have not yet caught up to. The gap is that AG's anneal/relax/retraction paths emit outputs that look authority-equivalent to forward authorizations, without any typed predicate that distinguishes the two.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Defines that a corrective transition (anneal, relax, retraction, quarantine release) restores prior admissibility context but does not, by itself, mint authority.
2. States that authority-increasing recovery — granting an action class that was denied — requires a separately classified forward authorization under fresh basis K', not a same-K stiffness reduction.
3. Identifies which AG recovery surfaces today emit outputs that consumers may bridge to "action permitted," and names the consumer-side bridge as the laundering path (not the recovery surface itself).
4. Records that no rename of scar / anneal / shield / dissent is ratified, and no new transition type is required by this filing.
5. Identifies forcing cases that would justify promotion to typed enforcement: a postmortem in which an annealed scar's threshold drop was treated as a fresh authorization; a recurring class of dissent-retraction events where the retracted objection was the only basis for refusal; an integration where shield relaxation was wired directly to action permission without an intervening authorization step.

## Doctrine (proposed; not yet ratified)

> **Corrective recovery may restore admissibility context, but it must not mint authority under the same basis.**

> **Healing a prior denial is not the same transition as granting a new permission. Same-K recovery restores; fresh-K forward authorization grants.**

The first line is the rule. The second is the structural shape. Both are candidate doctrine until a forcing case promotes.

## Non-goals

- **Not a new transition type.** No `CorrectiveStep` / `ForwardStep` enum addition is proposed.
- **Not a rename of scar / anneal / shield / dissent.** Existing vocabulary stays.
- **Not a claim that Lean mandates AG architecture.** The kernel is a formal target; AG instantiation is not bound by it.
- **Not a collapse of recovery, retry, revalidation, and new authorization into one bucket.** The point is precisely that they are *different* transitions; this gap names the lack of typed distinction, not a unification.
- **Not a refactor of `ScarLedger`, `dissent.py`, or `drift.py`.** This gap names the constitutional question those surfaces don't currently answer; it does not specify the answer.
- **Not a bridge to RPP, receipt_kernel, or standing chain validator.** Each may eventually carry a piece of the typed cut; none is committed by this filing.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Sibling at the AUTHORIZE-issuance valve. That gap names the missing content semantics on `admissibility_check`. This gap names the missing typed boundary at recovery. Both are content-discipline complements to C3/C4's form discipline.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Names the missing `AuthorizationVerdict` mint. The bridge "well-formed AUTHORIZE chain → action proceeds" is exactly the consumer-side bridge this gap names at the recovery valve. Same NLAI shape, different chokepoint.
- **`GOV_GAP_HYSTERESIS_REPAIR_001`** — Adjacent. That gap concerns hysteretic state and repair semantics; this one concerns the typed boundary between any recovery transition (hysteretic or not) and authority-granting.
- **Lean `Admissibility/Corrective.lean` + `CorrectiveBoundary.lean`** — Formal target. The AG-side instantiation, if ever built, would mirror the kernel's `classify` total function and the `RecoveryEnv` operational gate.
- **`scars.py` (`Scar.anneal`, `Shield.relax`, `ScarLedger`)** — The AG surfaces under audit. Implementation is correct as recovery primitives; the gap is in how their outputs are consumed.

## Open Questions

1. Which AG recovery surfaces today have consumers that bridge directly from "recovery condition met" to "action permitted"? An audit pass before any typed-boundary work would name those bridges concretely.
2. Is the cut at *basis K* the right cut for AG, or is the analogous AG-side cut at the proposal/intent layer (where `intent_compiler` already structures hypothesis collapse)?
3. Should fresh-basis forward authorization after recovery be a separate FSM transition in `ClaimStatus`, or does the existing `PROPOSED → SUPPORTED` path already cover it under the right preconditions? If covered, what makes the path post-recovery materially different from a first-time authorization?
4. Does scar annealing's `anneal_floor` (never reduces stiffness to zero) already structurally prevent the laundering path for the scar surface? If so, the laundering risk is concentrated in dissent retraction and quarantine release; if not, the floor is a hysteresis discipline, not an authority-laundering defense, and the two should not be conflated.
5. Where does `CorrectiveBoundary.lean`'s model-dependence result land for AG? AG's "store ops" are SQLite mutations and ledger appends — closer to the nondegenerate witness model than the identity model. Does that make the laundering risk concrete (not vacuous), and if so, does the boundary module's `NondegenerateStoreSemantics` shape suggest where to look first?

## Provenance

Filed 2026-05-08 during a sweep of `~/git/lean` after the May-2026 additions to `LeanProofs/Admissibility/`. Three lean modules postdate AG's last gap-spec pass on the kernel: `Corrective.lean` (May 1), `CorrectiveBoundary.lean` (May 7), and `WitnessInvariance.lean` (May 8). The corrective layer added a typed monotonicity boundary AG had vocabulary for (scar / anneal / shield / dissent / quarantine) but no typed surface against. Filed as a containment vessel before any transition-type work — preserves correct attribution (the laundering path is the same NLAI shape as the SEALED_OUTCOME_BOUNDARY gap, at a different chokepoint) and prevents the gap from being conflated with whatever specific mechanism eventually closes it.
