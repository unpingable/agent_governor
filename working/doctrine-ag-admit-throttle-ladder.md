# Doctrine (PROVISIONAL, candidate) — ag-admit throttle ladder & self-correction

Captured 2026-06-23 from operator direction. **Named, not built.** Records the trajectory
the ag-admit loop builds toward, so the next slice is grounded, not improvised. Composes
with `docs/doctrine/specs_do_not_bootstrap.md` and `working/campaign-ag-admit-self-build.md`.

## The thesis

Reducing operator throttle must mean **"more of the loop's own refusals and repairs become
admissible without babysitting,"** NOT "a larger blind-trust blob." Widening scope stays
slow even while repair *inside* scope gets fast.

> Codex/AG may self-correct implementation; it may not self-authorize jurisdiction.

The machine earns a longer leash only after it proves it understands the fence by running
into it correctly (Slice 3's NEEDS_HUMAN at the closed-enum boundary is exactly that).

## Operator review → operator audit

Target mode: AG proposes → gate admits/refuses → repair worker fixes failures → receipts
prove bounded success → operator **samples/audits exceptions**. Reviews shrink to: scope too
broad / receipt missing causal link / should-have-been-CANNOT_TESTIFY / promotion overclaims
/ naming nits — not "why is the conductor doing policy."

## Throttle ladder (not a binary switch)

| Level | AG may | Human role |
|---|---|---|
| T0 manual | propose only | approve everything |
| T1 execute admitted slices | build inside declared path scope | review receipts |
| T2 self-repair | repair failures/refusals inside same scope | review final trace |
| T3 exception-only | continue through routine rejects/cannot-testify repairs | review escalations/promotions |
| T4 sampled audit | run admitted backlog slices | inspect random sample + ALL widenings |

Current state: **T1** (toy + one promoted packet, receipts reviewed). T2 is the next build.

## Codex = repair worker, not governor

**May:** apply mechanical repairs, shrink diffs back into allowed paths, fix tests,
normalize receipt output, turn refusal reasons into candidate patches.
**May NOT:** reinterpret `StepVerdict`, edit projection semantics, edit conductor authority,
widen path scope, bless incomplete waiver packets, silently change loop state.

## Next build after Slice 3 — self-correction within the same grant

Not a planner, not autopilot. Just:

```
refusal/test receipt + original CandidateStep + same declared intent
  → repaired CandidateStep (constrained by the refusal receipt)
  → SAME ag_admit gate
  → admit / refuse / cannot_testify
```

Invariants (each must become a pinning test when built):

- a repair may run **only within the original declared scope and intent**;
- every repair **cites the refusal/test receipt it answers**;
- resubmission goes through the **same `ag_admit` path**;
- no repair may widen scope, edit admission semantics, alter `StepVerdict` projection,
  modify the conductor, or mutate loop state;
- human review stays required for promotion, widening, authority-surface changes, and any
  `NEEDS_HUMAN` source verdict.

This is the first real throttle reducer: the machine learns to **bounce off the fence
without making the fence**.

## Mechanical promotion criteria (gate for reducing throttle)

Before any throttle reduction, require (checkable, not vibes):

1. **N successful traces** in the same class;
2. **zero mutation after refusal**;
3. **all commits causally linked** to admission receipts;
4. **all repairs preserve the original declared intent**;
5. **no conductor diffs** except explicitly authorized;
6. **no unknown verdict projected as admit/reject** (unknown → CANNOT_TESTIFY);
7. **full reconstruction from receipts**.

## Also queued (discovered in Slice 3)

A **forbidden-surface classifier** beside `DiffPathScopeGate` — path authority ≠ semantic
authority. Detects closed-enum / verdict-semantics / conductor-authority / governed_dispatch
touches that a path gate cannot. Candidate; downstream of self-correction.
