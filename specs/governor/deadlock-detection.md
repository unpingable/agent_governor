# Deadlock detection — a governor primitive (landed 2026-06-14)

Module: `src/governor/deadlock.py`. Tests: `tests/test_deadlock.py` (13, green).

## The doctrine line
> **Deadlock is when valid local custody decisions compose into no global transition.**

Everyone is green; the run is stuck. It is the runtime rhyme of the temporal theorem
*locally valid ⇏ trajectory valid* (`hopwise admissible ⇏ trajectory admissible`).
Same family, different goblin.

## The trichotomy (kept distinct — this is the point)
```
REFUSAL    — an action is invalid / unsafe / out of bounds
EXHAUSTION — retry / budget / capacity spent
DEADLOCK   — locally valid positions compose into no owned next transition
```
The governor already types refusal everywhere and has exhaustion-shaped notions (scars,
budgets). Deadlock was the missing third. `regime.UNSTABLE` is a *different* axis
(cascade / positive feedback), not a stall.

## The classifier (`assess_stall`)
Six verdicts over a recent loop window of `TurnObservation`s:
`progressing · refusal · exhaustion · held_with_plan · operator_gate_open · deadlock`.

Deadlock requires ALL of (necessary structural condition first):
- ≥ `window` turns, every `local_outcome == defer`, **no artifact delta, no terminal**;
- **repeated** `semantic_fingerprint` (the same unresolved issue, no new evidence);
- **no owned next transition** — no `next_action_scheduled` and no minimal
  `DecisionPacket`.

Then it classifies *why*: `circular_custody_deferral` (A→B and B→A), 
`mutual_operator_deferral` (all → operator, no packet), or `repeated_unresolved_state`.

Not-deadlock outcomes are explicit and tested: progress beats stall; a refusing/
exhausting turn is REFUSAL/EXHAUSTION; a valid hold *with an explicit next action* is
`held_with_plan`; an emitted minimal decision packet is `operator_gate_open` (the agents
already converted to a typed gate — healthy, not silent).

## Two disciplines the detector itself obeys
1. **Evidence (NLAI).** Structural signals (no artifact delta + repeated state) are
   *necessary*. Deferral phrases ("your call", "not mine to decide") are *corroborating
   only* — language never authorizes the verdict alone. (Test:
   `deferral_language_without_structural_stall_is_not_deadlock`.)
2. **Don't resolve — convert.** The detector does NOT choose the blocked doctrine. It
   emits a `DeadlockReceipt` (`status="operator_required"`) that converts vague stuckness
   into a typed operator gate: options (incl. HOLD), forbidden ratifying actions, and a
   **process default** (`PROCESS_DEFAULT` = keep fenced progress, don't freeze, surface
   the ratification as one narrow operator decision) — the meta-move, never the content.
   This dogfoods `feedback_ratification_vs_progress_deadlock`: an undecided ratification
   must not freeze fenced progress.

## Lean / Python division (operator, 2026-06-14)
- **Lean** proves the classification boundary (`valid_deferrals_can_deadlock`,
  `deadlock_is_not_refusal_or_exhaustion`, `circular_deferral_requires_operator`) —
  owned by the Lean-Claude, `Scratch/DeadlockTrajectory.lean` (in progress, [scratch]).
  No string-matching / retry-counters / JSON-shape in Lean.
- **Python (this module)** detects the runtime symptom. No metaphysics in Python.

## Not done (next, consequence-bearing — NOT on momentum)
Wiring the detector into the live governor loop so it actually **halts retry /
autopromotion** on detection is a separate slice: a detector that emits testimony is
pure, but a detector that *stops the loop* is consequence-bearing and should be gated
(and wiring a halt mechanism on momentum would be exactly the failure this primitive
names). This slice ships the pure detector + receipt + boundary tests only.
```
