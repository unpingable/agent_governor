# Next packet — self-correction within scope (named, NOT built)

Per [D008](DECISIONS.md): build order is **reproducibility capsule → ForbiddenSurfaceGate
→ self-correction-within-scope**. The first two have landed; this file is now the seed for
the third. **Do not build it in the gate packet.**

## Done (prior step)

`ForbiddenSurfaceGate` is **built** — `src/governor/forbidden_surface_gate.py` +
`tests/test_forbidden_surface_gate.py`. It is the semantic companion to
`DiffPathScopeGate`: a classifier over the declared forbidden-surface list
([GRANTS.yaml](GRANTS.yaml)), conservative (forbidden file without a marker, or an
unparseable diff → `CANNOT_TESTIFY`), routed through the existing `ag_admit` projection,
with the dumb conductor unchanged. The composition specimen holds: a diff that is
path-allowed but mutates a closed enum gets ADMIT from `DiffPathScopeGate` and REJECT from
`ForbiddenSurfaceGate`. Path authority ≠ semantic authority is now mechanized.

## Goal (self-correction)

Reduce operator throttle by letting the loop repair its own refused/failing steps **inside
already-admitted scope** — not "trust the model more," but "stop making the human re-type
case law." This is the first real throttle reducer (T2 on the ladder, see
`working/doctrine-ag-admit-throttle-ladder.md`).

## Shape

```
refusal/test receipt + original CandidateStep + same declared intent
  → repaired CandidateStep (constrained by the refusal receipt)
  → SAME ag_admit path (DiffPathScopeGate + ForbiddenSurfaceGate)
  → admit / refuse / cannot_testify
```

Not a planner, not autopilot. A bounded repair that bounces off the fence without making
the fence.

## Invariant

A repair may run **only** within the original declared scope, intent, **and semantic-surface
class**. Every repair **cites the refusal/test receipt it answers**. Resubmission goes
through the same `ag_admit` path. The conductor stays dumb (D003/D005).

## Forbidden

No repair may widen scope, edit admission semantics, alter the `StepVerdict` projection,
modify the conductor, mutate loop state, or touch any forbidden surface ([GRANTS.yaml](GRANTS.yaml)).
Human review stays required for promotion, widening, authority-surface changes, and any
`NEEDS_HUMAN` source verdict (D005). Codex/repair-worker may self-correct *implementation*;
it may **not** self-authorize *jurisdiction*.

## Exit

A refused step is repaired within the same grant and re-admitted, with the repaired
admission receipt citing the refusal receipt it answers; a repair that strays outside scope
/ intent / semantic class is itself refused. Pins prove each.
