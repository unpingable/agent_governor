# Next — the D008 build ladder is complete; what follows is operational

Per [D008](DECISIONS.md) the build order was **reproducibility capsule →
ForbiddenSurfaceGate → self-correction-within-scope**. **All three have landed.** There is
no queued *new mechanism* — the next moves are operational (run the loop at reduced
throttle) and integration, not fresh admission machinery. Do not invent a new gate without
a forcing case.

## Built (the ladder)

- **Reproducibility capsule** — this directory (`d60850d`) + cold-start discovery rule in
  `docs/loop-protocol.md` §9 (`c708df0`).
- **ForbiddenSurfaceGate** — `src/governor/forbidden_surface_gate.py` (`92a91e1`). Path
  authority ≠ semantic authority, mechanized.
- **Self-correction within scope** — `src/governor/self_correction.py` +
  `tests/test_self_correction.py`. The worker proposes a repaired `CandidateStep` from a
  failure receipt; the harness validates ancestry/scope/intent ([D009](DECISIONS.md)) and
  re-admits through the same gates. The first real throttle reducer (T2).

## What follows (named, not a new build surface)

1. **Operate at reduced throttle (T2→T3).** Run real refused/failing steps through
   `attempt_repair`; the operator reviews **boundary moves** (scope relation, intent
   preservation, receipt causality, forbidden-surface refusals, promotion requests), not
   every mechanical repair. See `working/doctrine-ag-admit-throttle-ladder.md`.
2. **Wire a real `RepairProvider` (Codex).** Today's providers are deterministic stubs.
   The `RepairProvider` Protocol exists so Codex can be the dumb repair worker: hand it
   `REPLAY.md` + `DECISIONS.md` + a refusal receipt; it returns a `RepairProposal`. It may
   self-correct *implementation*; it may **not** self-authorize *jurisdiction* — the
   harness enforces that. **Named, not built** — needs an operator go + an integration
   forcing case.
3. **Promotion criteria as a checklist** (from the throttle-ladder doctrine) before any
   throttle reduction: N traces in class, zero mutation after refusal, commits causally
   linked, repairs preserve intent, no conductor diffs, no unknown verdict as admit/reject,
   full reconstruction from receipts.

A genuinely new admission mechanism would need its own forcing case, promotion note, and a
new `NEXT.md` entry — it is not implied by reaching the end of this ladder.
