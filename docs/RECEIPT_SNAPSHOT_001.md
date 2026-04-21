# Receipt Snapshot 001: Action-Axis Primitives Dormant in Dogfood

**Date:** 2026-04-21
**Subject:** `.governor/receipts/gate_receipts.jsonl` distribution
**Triggering question:** Does the continuity-budget inequality from the ops-non-self-identical-controller paper bite in agent_gov?

## Method

A paper (`~/git/papers/working/ops-non-self-identical-controller.md`) proposed an action-side feasibility condition

$$\tau_{\text{auth}} + \delta_h(B, \theta) < T_{\text{exit}}$$

composed from authority-routing delay, handoff reorientation overhead, and exit horizon. A gap spec draft (CONTINUITY_BUDGET envelope) was proposed to surface this as a receiptable signal at decision points: escalation pending, compaction fires, regime enters WARM+, resume/handoff.

Before repo-shaping the spec, the cheapest available falsification was asked: **do these decision-point events fire at all in the current dogfood?**

Grep-before-sketch, not spec-then-find-case.

## Finding

926 gate receipts in `.governor/receipts/gate_receipts.jsonl`. Distribution:

| Count | Gate              | Verdict |
|------:|-------------------|---------|
|  914  | context_build     | observe |
|    4  | evidence_gate     | pass    |
|    2  | stability_probe   | observe |
|    2  | lane_routing      | pass    |
|    2  | plugin_post_tool  | observe |
|    2  | doctrine_consult  | observe |

Action-axis ingredients:

- `scope_escalation` receipts: **0**
- Scope grants (all): **0**
- Scope escalation history: **none**
- Regime transitions recorded: **none**
- Context compaction receipts: **none**

Every trigger class the CONTINUITY_BUDGET envelope would emit at — escalation pending, compaction, regime transition, resume — has fired zero times. Not "fires trivially FEASIBLE." Does not fire.

## Interpretation

Two possible causes, both useful:

1. **The live workload doesn't exercise these primitives.** Current dogfood is dominated by prompt assembly (context_build at 99%). Chat-bridge-driven generation doesn't trigger scope escalation, doesn't cross regime thresholds, doesn't hit compaction. The primitives exist in code; the workload doesn't reach them.
2. **The primitives fire but don't emit receipts.** Wiring gap between the subsystems (regime detector, scope governor, compactor) and the receipt store.

Distinguishing requires instrumentation review, not more paper reading.

Either way, the CONTINUITY_BUDGET envelope was premature by one further step than expected. The action-axis composition is not the live gap; the action axis is dormant.

## Heuristic (for future paper→tooling mappings)

> **Grep the gate_receipts distribution before drafting a gap spec derived from a paper.**

If the paper's trigger events aren't firing in the current dogfood, the spec is premature regardless of how well the math lifts. This is the cheapest available falsification and it runs in seconds:

```bash
python3 -c "
import json
from collections import Counter
gates = Counter()
with open('.governor/receipts/gate_receipts.jsonl') as f:
    for line in f:
        r = json.loads(line)
        gates[r.get('gate')] += 1
for g, n in gates.most_common():
    print(f'{n:5d}  {g}')
"
```

If the gate distribution does not contain the paper's trigger classes, stop. The paper may still apply; the spec does not.

## Side finding: `governor regime status` broken

Discovered incidentally. The CLI (`src/governor/cli.py:5143-5172`) used stale keys against `RegimeDetector.get_state()`:

- CLI expected `state["current_signals"]` → actual key is `last_signals` (and is `None` when no signals have been observed).
- CLI expected `state["warnings"]` → key does not exist in `get_state()`.
- Signal field access (`hysteresis`, `relaxation_time`, etc.) assumed `last_signals` is dict-shaped; failed on `None`.
- `regime_update` also unpacked `detector.update()` as a `(regime, warnings)` tuple when it actually returns `RegimeTransition | None`.

Root cause: CLI contract drifted from `regime.py`.

**RESOLVED (2026-04-21):** All three commands (`regime status`, `regime signals`, `regime update`) fixed. 5 CLI smoke regression tests added to `tests/test_regime.py::TestRegimeCliSmoke` covering empty-state paths for each command plus JSON variants.

**Persistence follow-on RESOLVED (2026-04-21):** `RegimeDetector.to_dict()` and `from_dict()` now serialize `last_signals` and `last_signals_at` (observation timestamp set in `classify()`). CLI displays relative age in human output ("observed 2m ago"); JSON exposes absolute ISO-8601 UTC. Backward-compat reads handle pre-existing state files (missing keys → `None`). 5 roundtrip tests added to `tests/test_regime.py::TestRegimeDetectorPersistenceRoundtrip`. Verified end-to-end: signals set by `regime update` survive a fresh CLI invocation. 81/81 regime tests pass; 394/394 across regime-touching modules (boil, viewmodel, daemon).

Rationale for fix-not-document: `save_regime_detector()` is called after every `regime update`, and the save was silently dropping `last_signals`. That's a roundtrip-integrity bug, not a semantics question — saved state was lying about what was saved.

## What this does *not* conclude

- Not that the paper is wrong.
- Not that the action-axis composition is permanently off the table.
- Not that the identity axis is automatically the right next move — that claim has its own gates.

Only that the continuity-budget envelope does not earn its draft in the current regime.

## Next

- Identity-axis work (starting with interferometry-as-identifiability-probe) becomes the candidate live gap. Its own gating is whether the reframe changes observable behavior, not whether its trigger events fire — interferometry is an explicit user-invoked subsystem.
- CONTINUITY_BUDGET envelope: shelved. Reactivation gate is evidence that action-axis primitives fire *and* compose non-trivially.
- Regime-status CLI bug: recorded above, not fixed.
