# RESUME — P4 HIGH gate prep (pick up 2026-06-15)

Stopped 2026-06-14 at the right line: **all three producers exist, the eligible
evidence path works, but promotion is not authorized.**

> Eligibility opens the courtroom door. Promotion moves the constitution.

The producers can testify; they cannot crown a baseline. Next is deciding the exact
ceremony by which testimony becomes law — and that ceremony is **HIGH / operator-present**.
Do not resume on momentum.

## Where the stack is (all green, exit-witnessed, NOT pushed)
```
dca358c  P4 cold-start refusal artifact
433cad6  evidence walkability model (P4.0a gate consumed)
792a22d  activation store (P4.0c)
d2a28c5  observation admissibility — in_bounds derived (P4.0d)
32e6539  observation store — re-derive on load (P4.0e)
34845ac  replay/holdout producer (P4.0f)
2e38296  operator-basis producer — operator_basis_present derived (P4.0g)
```
Last verifier: `0381129f` [pass], 111 passed, exit 0. Spec: `specs/governor/promotion-evidence.md`.
Design backing: `working/P4.0g-operator-basis-lean-spike-2026-06-14.md` (Lean [scratch],
incl. observer foundation, freshness-window scar).

## Do NOT open P4.0b directly. Open HIGH-prep first (docs/spec only).

The three unsettled items are the actual HIGH gate — three *authorities*, not chores:

1. **Checkpoint 3 / SELF_GOVERNANCE_SPEC amendment — the DOCTRINE authority.**
   What does "promotion" mean under the now-built kernel/userland/four-office/rung-debt
   structure? Deferred all campaign as "OPEN, LAST." Operator-present decision.
   **Scope guard (from `working/anti-laundering-not-legitimacy-ag-consumption-2026-06-15.md`):**
   promotion via operator basis is **attributable, not legitimate** — the ceremony forces
   the mint to bear the operator's name; it does NOT certify the trial was good. Operator
   basis licenses the *authority* gap only, never the evidentiary (live/replay) ones
   (best-effort-completeness round-3: operator ≠ universal solvent). Keep the P4.0b
   narrative out of legitimacy-engine creep: the kernel is anti-laundering, not legitimacy.
   Now all-green specimen-backed (`authority_ratification_does_not_discharge_evidentiary_gap`
   / `_custodial_gap`; `nonsatisfied_closed_but_not_discharged` + 4 named residues) — but
   cite as a CONFIRMING specimen on a stipulated diagonal, [scratch], NOT independent proof
   the architecture is correct.
2. **Canonical basis-bundle hash — the CUSTODY authority.**
   What EXACT bundle does the operator basis review/consume? P4.0g binds with opaque
   hashes deliberately; left opaque too long it becomes "trust me bro, but hashed."
   Specify the fields + order over activation + observations + replay + operator basis.
3. **Freshness-window / pause-clock — the TIME authority.**
   Operator review competes with replay duration (the P4.0g scar). Either a sized review
   window (`> max replay runtime + slack`) OR explicit paused-clock receipt semantics.
   Otherwise fresh evidence rots during ceremony. Operator prefers the sized window
   unless operationally stupid; a pause must be explicit in the replay/operator receipt
   pair ("paused clocks are a future deposition").

## P4.0a-HIGH-prep slice scope (when the operator is present)
- draft/finalize the Checkpoint 3 SELF_GOVERNANCE_SPEC amendment text
- define the canonical basis-bundle hash (fields + canonical order)
- decide freshness policy: fixed review window vs explicit paused-clock receipt
- produce P4.0b acceptance criteria + negative tests (before any mint)

### Hard NOT in HIGH-prep
- no `ControlBaseline` mint
- no `PromotionReceipt`
- no `convergence_tuning` migration
- no push unless separately instructed
- no real `max_slices=4` promotion (the real trial still has zero evidence on disk)

## Then, and only then: P4.0b (mint ControlBaseline via the supersession ceremony)
The first slice where the constitutional furniture actually moves. Gated on the three
above being settled. HIGH / operator-present, Checkpoint-3-gated.
