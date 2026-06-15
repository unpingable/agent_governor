# RESUME — P4 HIGH gate (HIGH-prep DONE 2026-06-15; next = P4.0b mint)

HIGH-prep is complete. The three authorities were ratified operator-present 2026-06-15.
The constitution did NOT move yet — no `ControlBaseline`, no `PromotionReceipt`, nothing
minted. What changed is **docs/spec only**: the ceremony is now specified, so P4.0b starts
from a precise target instead of an open question.

> Eligibility opens the courtroom door. Promotion moves the constitution.
> HIGH-prep specified the move. P4.0b makes it. P4.0b is still HIGH / operator-present.

## What landed this session (docs/spec only, NOT pushed, no code)
1. **Doctrine — Checkpoint 3 RATIFIED.** Appended § "Checkpoint 3 / P4 Promotion" to
   `specs/core/SELF_GOVERNANCE_SPEC.md` (additive mapping of the built kernel onto v0.1;
   NO v0.2 bump, NO separate spec). Promotion = a **four-office classed act**
   (admissibility=`PromotionEligible` · act-standing=operator basis · exactly-once=single
   supersession mint · durable custody=`ControlBaseline`+lineage). Fence pinned: operator
   basis is **attributable/authorizing, never legitimizing, and cannot cure an evidentiary
   gap.**
2. **Custody — basis-bundle hash specified.** `specs/governor/promotion-evidence.md`
   § "P4.0b-prep". `basis_bundle_hash = sha256(canonical_json({...}))`. Excludes operator
   basis (circular) + clocks (different object); observation hashes sorted; prior-baseline
   bound by hash/receipt not bare value; open-claims a **frozen snapshot**, not a live
   pointer. *The bundle binds the reviewed world-state, not the operator's later act and
   not the evaluation clock.*
3. **Time — two-clock freshness ratified.** Review freshness (short sized window,
   ceremony-bound) vs survival-horizon freshness (must outlive replay+review+slack). Replay
   is upstream (frozen into the bundle), so the P4.0g scar's framing was inverted. No
   paused clock (deferred deposition mechanism). Keeper test pinned. *Don't use one clock
   to smuggle the other.*
4. **P4.0b acceptance criteria (6) + negative tests (9)** written in promotion-evidence.md
   § "P4.0b-prep" — the contract P4.0b must satisfy before any mint.

## Stack state (unchanged from session start — still all green, exit-witnessed, NOT pushed)
```
dca358c  P4 cold-start refusal artifact
433cad6  evidence walkability model (P4.0a gate consumed)
792a22d  activation store (P4.0c)
d2a28c5  observation admissibility — in_bounds derived (P4.0d)
32e6539  observation store — re-derive on load (P4.0e)
34845ac  replay/holdout producer (P4.0f)
2e38296  operator-basis producer — operator_basis_present derived (P4.0g)
```
This session added NO commits (docs edits to SELF_GOVERNANCE_SPEC.md + promotion-evidence.md
are uncommitted working-tree changes). Last verifier: `0381129f` [pass], 111 passed, exit 0.

## Next: P4.0b — mint ControlBaseline via the supersession ceremony (HIGH / operator-present)
The first slice where the constitutional furniture actually moves. Now fully specified:
- implement `basis_bundle_hash` per the canonical spec; wire it into the operator-basis
  consume path (replace P4.0g's opaque hash with the computed one)
- mint `PromotionReceipt` + `ControlBaseline` with content-addressed lineage, via the
  validator supersession ceremony
- satisfy the 6 acceptance criteria; pass the 9 negative tests (incl. the slow-replay keeper)
- Checkpoint 2 already RESOLVED → COEXIST (a `tuning_proposal_bridge.py` is optional, gated)

### Hard NOT in P4.0b either
- no real `max_slices=4` promotion until a real live-survival + replay corpus exists on disk
  (the real trial still has zero evidence — synthetic fixtures only for the mint tests)
- no second profile (ops/NQ) until self-governance survives one full promotion cycle
- no receipt-kernel / fuse / ratification invariant changes (supersession ceremony only)
- no push unless separately instructed
