# BestEffortCompleteness (Lean scratch) — AG relevance map (2026-06-15)

`~/git/lean/LeanProofs/Scratch/BestEffortCompleteness.lean` — sorry-free, [scratch], not
in the default build target, header says "informs the loop/governor doctrine; blesses
nothing." So it **informs** AG design; it cannot **ratify** it (tier discipline). Recorded
because the operator flagged it forward-relevant.

## What it proves (the wall, not "best effort" itself)
- `GapKind` ∈ {operational, semantic, evidentiary, custodial, authority}; `Closure` ∈
  {satisfied, refused, quarantined, exhausted, escalated} — **only `satisfied` discharges;
  the other four are best-effort residue.** `Basis` = typed justification (issuer's
  *warrant*, not *rank*); `licenses` is a **diagonal** (each basis licenses exactly one
  kind), with **No-Silent-Conversion** (no interconversion, no universal/top basis).
- `discharged` = satisfied closure **under a kind-matched basis**. `complete` = every
  required obligation discharged.
- Hinge: `unlicensed_for_kind_is_not_discharge`. Headline:
  `system_execution_cannot_complete_authority_requirement` (through `complete`, not a
  grammar restriction).
- **Best-effort residue, exhaustive (completeness pass, 2026-06-15):** general lemma
  `nonsatisfied_closed_but_not_discharged` + four named instances `exhausted` / `refused`
  / `quarantined` / `escalated` — all close, none discharge. (Was a single `exhaustion`
  wall; now conjunctive coverage, each citeable by name.)
- **Operator-fiat fence, all-green pair:** `authority_ratification_does_not_discharge_evidentiary_gap`
  **and** `authority_ratification_does_not_discharge_custodial_gap` — an authority
  (operator-fiat) basis discharges *neither* evidentiary nor custodial gaps.
  Specimen-backed, no longer definitional.
- The provenance is the lesson: the laundering bug climbed the rank ladder three times
  (any-closure → any-satisfied → operator-issuer); each fix moved the 777 up a rung. The
  real fix is **TYPE the justification, don't rank it** — "signed is not witnessed."

## Where this is forward-relevant to AG

1. **P3.3 decomposition-completeness (`decomposition_completeness.py`) — this is its formal
   wall.** AG-alone emits `enumeration=declared` / `coverage=best_effort`, and "no AG-alone
   receipt may emit `coverage=complete` without solver/theorem/operator evidence." That
   runtime valve = the Lean's `exhausted closes ≠ discharges` + "completeness needs a
   kind-matched basis." Campaign ground rule 13 (decomposition completeness gates
   recomposition/promotion) is the P4 hook. **This is the citation when that valve is
   questioned** — at [scratch], informing.

2. **The P4 producer family (P4.0d–g) — the licensing diagonal is why the three witnesses
   can't be folded.** live-survival (evidentiary) / replay-holdout (evidentiary) /
   operator-basis (authority) each license their own gap; no interconversion. The gate
   requires all three independently and `operator_basis_present ≠ eligible` — which is
   exactly `system_execution_cannot_complete_authority_requirement` + the diagonal, now
   Lean-backed (informally). P4.0g's architecture is confirmed, not just asserted.

3. **THE FORWARD WARNING (round-3 lesson) — operator-fiat is NOT a universal solvent.**
   The bug's third home: `operator` became chmod 777, discharging an evidentiary gap with
   no evidence. AG runs operator-fiat standing in P3.1 (bootstrap) and operator-basis in
   P4.0g. The wall: **operator basis licenses the AUTHORITY kind only — it must NOT be read
   as discharging the evidentiary (live/replay) or custodial gaps.** Now specimen-backed
   all-green, citeable by name: `authority_ratification_does_not_discharge_evidentiary_gap`
   + `authority_ratification_does_not_discharge_custodial_gap`. At **P4.0b** (the HIGH
   gate, tomorrow): the operator's promotion basis discharges the *authority* requirement;
   it does not substitute for the live-survival/replay evidence the gate independently
   checks. Do not let the operator stamp become the universal discharge. (AG already fences
   this — P3.1 marks `standalone_degraded` and claims no LA/Standing/NQ grade; the Lean is
   why that fence is load-bearing, not ceremony.)

## Family placement (no overclaim)
This is the **best-effort / discharge ⇏ completeness** instance of the no-lift family
(`working/lift-failure-family-2026-06-14.md`) — across the *basis↔kind* boundary. Per the
meta-bridge guard it is **schema-aligned, not reduced** (it is not a global-section
theorem; it is a denote-and-refute discharge wall). A candidate row, not a member.

**Completeness-pass fence (keep visible at the mint).** The 2026-06-15 pass made the
coverage all-green (general lemma + four named residue instances + the operator-fiat
pair), so AG cites *specimens by name*, not "one specimen + a definitional argument." But
the basis→kind diagonal is still a **stipulation of this specimen**, and it's still
[scratch]. So all-green **confirms AG's chosen architecture, it does not independently
discover/prove it is the right diagonal.** At P4.0b: cite it as a confirming specimen on a
stipulated diagonal, never as independent proof the promotion architecture is correct —
that would be the legitimacy-engine read the scope correction forbids.

## Bonus: the deadlock-side Lean landed too ([scratch])
`DeadlockTrajectory` (`deadlock_is_not_refusal_or_exhaustion`,
`ownerless_deferral_requires_operator`) is the Lean end of the governor detector
(`src/governor/deadlock.py`). `DeadlockEscalation` carries a specimen for **every**
multigov-gap correction (`chain_tip_in_key_splits_same_issue`,
`coarse_key_merges_distinct_issues`, `resolved_does_not_suppress_recurrence`,
`decision_survives_lease_rotation`, `fake_cas_admits_two_winners`). The AG records
(`specs/governor/deadlock-detection.md`, `specs/gaps/GOV_GAP_MULTIGOV_DEADLOCK_CUSTODY_001.md`)
no longer cite unbuilt Lean — companions exist at [scratch], informing not ratifying.
