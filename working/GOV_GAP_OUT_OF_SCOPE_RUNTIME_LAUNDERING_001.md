# GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001

## Title
A kernel classification of `outOfScope` is epistemic non-authority. If a runtime treats it as permission-shaped ambiguity, the classification has been laundered into spendable authority that no kernel ever minted.

## Status
**Working candidate / failed grounding audit 2026-05-21.** Originally filed by a cross-fence drop from a papers-side Claude into `specs/gaps/`. AG-side two-grep audit (run 2026-05-21) failed to ground the primary thesis: no AG kernel or verdict surface currently emits `outOfScope` as an authority-relevant classification. The three matches in tree (`autopilot.py` OutOfScopeAction enum, `writing_ticketing.py` reason string, `constraint_compiler.py` comment) are not classification-to-authority surfaces.

The spec was moved from `specs/gaps/` to `working/` 2026-05-21 to honor AG's grep-first discipline (`memory/feedback_grep_before_sketch.md`, `memory/feedback_grep_receipts_before_paper_specs.md`) and to keep `specs/gaps/` from becoming a quarantine zone for imported plausible doctrine.

Promotion to `specs/gaps/` requires either:
- AG introducing an `outOfScope` (or equivalent epistemic-non-authority) verdict slot in a kernel return type, or
- a real AG laundering instance: a code path that consumes a non-`denied` classification result as proceed-permission.

The grounded portions of this filing — the receipt-vs-authority distinction and the TOCTOU-across-serialization warning — have been lifted to `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` as a Cross-Boundary Doctrine section, where they have AG-side forcing cases (override-receipt serialization across the daemon→CLI boundary). They are NOT lost; they are grounded where they apply.

Original status block (preserved for historical accuracy): "Gap spec — containment vessel. No schema, validator, runtime gate, or enforcement behavior is ratified by this filing. Names the laundering path and the runtime contract shape; future forcing cases promote."

## Keeper

> `outOfScope` is not permission. It is audible non-authority.

Or operationally:

> No minted authority means no mutation.

## Origin

Filed 2026-05-21 after a session in which:

1. The Lean Slice 1 aperture (`~/git/lean/LeanProofs/Admissibility/LocalBoundary.lean`) closed `composition_preserves_global_safety_aperture` by separating component-local authorization (`LocalAllows lb_i`) from merged-partition safety (`MergeAdmissible.{left,right}_sound`). The proof never invokes the merged boundary to authorize a component step — *if the merged boundary authorizes the component step, locality has already been lost.*
2. A Gemini reading of that aperture observed correctly that the structural refusal in Lean does not bind a Python runtime that consumes a classification result. The runtime can still launder `outOfScope` into "permission-shaped ambiguity" if no contract forbids it.
3. The shape rhymes with `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001` (form vs. content gap) and `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` (authority observable not constructible). This gap is the third member of that family: **the classification-result-to-runtime-authorization bridge has no enforced contract.**

## Problem Statement

A kernel that returns a classification value into the set

```text
{ allowed, denied, unresolved, outOfScope, malformed }
```

does not, by virtue of returning a non-`denied` value, authorize anything. `outOfScope` is the load-bearing case: it is the result that *most* invites laundering, because it is structurally indistinguishable from "ambiguous" or "unclassified" if the runtime does not insist on the distinction.

The laundering move:

> `denied` was not returned, therefore the action may proceed.

This is the same move as the ambient-authority-leak specimen at the calculus layer (`~/git/papers/working/models/boundary-calculus/specimens/ambient-authority-leak.md`), recast across the runtime boundary. The aperture forbids it structurally inside the typed kernel. The runtime is the other side of the seam.

## Invariant

A runtime may not execute a mutation-bearing action from an `outOfScope` classification. For mutation-bearing actions, `outOfScope` is deny-equivalent at the runtime gate because no authority was minted.

For observation-only or diagnostic actions, `outOfScope` may be emitted as visible non-authority only if the action carries no mutation, no commitment, and no downstream standing.

## Clarification: outOfScope ≠ DENY semantically

The collapse `outOfScope = DENY` is operationally adequate for mutation but semantically wrong:

```text
outOfScope ≠ forbidden
outOfScope ≠ allowed
outOfScope = this kernel did not mint authority
```

The runtime policy says: *no minted authority → no mutation.* This routes through the same gate as DENY without collapsing the epistemic content. A diagnostic surface may still report "kernel returned outOfScope" as visible testimony — it just cannot become spendable authority for any downstream action that mutates state, creates commitment, or establishes standing.

## Decision Table

| Kernel result            | Critical mutation                  | Diagnostic observation                |
| ------------------------ | ---------------------------------- | ------------------------------------- |
| Authorized / allowed     | may proceed if runtime checks pass | may proceed                           |
| Denied                   | must not proceed                   | usually may report denial only        |
| Gap / unresolved         | must not proceed                   | may report gap                        |
| outOfScope               | must not proceed                   | may report non-authority only         |
| malformed / unclassified | must not proceed                   | may report parser/evaluator failure   |

The subtlety: `outOfScope` can still be **observable**. It just cannot become **spendable authority**.

## Boundary Warning: Construction-Boundary TOCTOU

Constructive bundling (the typed kernel's "make the cursed thing unrepresentable" move) eliminates TOCTOU only **inside the construction boundary**.

Once the bundle is serialized to JSON, handed to Python, persisted to disk, emitted as a receipt, or interpreted by a separate AG process, the type-level guarantee becomes a *claim about authority* rather than authority itself.

Therefore:

> Constructive bundling eliminates TOCTOU only within the construction boundary. Across a runtime or serialization boundary, the bundle must be revalidated, sealed, or treated as a receipt claim rather than live authority.

This connects to the existing standing/receipt doctrine:

> Receipt is what you can copy; authority is what you spend.

A serialized classification result is a **receipt of a past evaluation**, not live authority. The runtime contract must distinguish the two.

## Existing Governor Coverage (audit pending)

Coverage to be verified before promotion:

| Component | Expected check | Status |
|-----------|---------------|--------|
| AUTHORIZE receipt validator | Should reject mutation downstream of `outOfScope` classification | Not yet audited against this contract |
| Runtime gate (egress / mutation) | Should treat unminted authority as deny-equivalent | Specified by `GOV_GAP_EGRESS_001`?; cross-link pending |
| Standing chain validator | Should not permit `outOfScope`-derived links to count as authority continuity | Likely intersects `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` |

The two-grep falsification this spec demands (before any promotion):

1. Are there any production code paths that consume a classification result whose set includes `outOfScope` (or equivalent epistemic-non-authority value) and proceed on non-`denied`?
2. Are there any serialization boundaries across which a kernel classification crosses without revalidation or sealing?

Both are paper-shaped audits. Neither is enforced today.

## Related

- `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001` — form-vs-content sibling at the receipt-schema layer.
- `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` — construction-discipline sibling (authority observable not constructible).
- `GOV_GAP_EGRESS_001` — likely intersect at the runtime gate.
- `~/git/papers/working/models/boundary-calculus/specimens/ambient-authority-leak.md` — the calculus-layer specimen that this runtime-layer gap mirrors.
- `~/git/lean/LeanProofs/Admissibility/LocalBoundary.lean` — the typed-kernel side of the same shape: `ComponentStep.left/right` authorizes via `LocalAllows lb_i`, never via the merged boundary.

## Non-goals

- This spec does not define a runtime gate implementation.
- This spec does not promote `outOfScope` to a canonical kernel return value across all governor modules.
- This spec does not retroactively audit existing receipts.
- This spec does not require Lean changes; the typed kernel already refuses the laundering pattern by construction.

## Forcing Case for Promotion

- A live mutation traced to an `outOfScope`-derived classification result (live incident).
- A receipt validator instance that accepts non-`denied` ≡ proceed in any AUTHORIZE flow.
- Any cross-process serialization of a kernel classification that downstream consumers spend without revalidation.

Until then: gap spec, no enforcement.
