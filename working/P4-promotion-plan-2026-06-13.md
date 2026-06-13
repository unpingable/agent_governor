# P4 promotion / expiry — plan (docs-only, NOT implementation)

Item 3 of the pre-P4 order. Defines the minimal P4 around promotion/expiry of the
**single P3.1 activated tunable**, so P4 starts from a precise target instead of
"more annealing." **P4 is constitutional memory** — a trial shape surviving and
becoming baseline — NOT another wire-a-guard slice. This is plan only; no runtime,
no kernel enforcement, no new decomposition work.

## What is being promoted (exact target)

The one P3.1 tunable: **`decomposition_size / max_slices`** on rung
`self_governance`. The *trial state* is the active value an admitted P3.1 activation
set (e.g. `max_slices = 4`, prior baseline `8`). Promotion turns that surviving
trial value into a **new named `ControlBaseline`** — the known-good policy baseline
future activations measure drift against.

> **Red line (verbatim from the campaign):** checkpoints/forks/promotions are
> resumability machinery *unless explicitly admitted as control-plane baselines*. A
> promoted session state is NOT automatically a known-good baseline — promotion is a
> separate, classed act (observe trial survives → mint baseline via ceremony).

## P4 preconditions (all met except the entry checkpoints)

P3 lifecycle drill ✓ · P3.2 enforcement green ✓ · DebtLedger present ✓ · P3.1
activation receipts exist ✓ · **pre-P4 plan-intake gate P3.4 fenced ✓**. Remaining:
promotion target = the one tunable (this doc); supersession ceremony chosen (below);
baseline diff/revert path proven (P4 acceptance). Entry HIGH checkpoints (operator
present): replay/holdout as promotion criterion (crosswalk divergence #2);
convergence_tuning disposition; SELF_GOVERNANCE_SPEC amendment per ratified crosswalk.

## The seven questions

**What evidence proves the trial survived?**
`evidence_count >= N` of IN-BOUNDS post-activation observation receipts — *scars-style
evidence-count, never wall-clock*. "In-bounds" = the trial value held without its
`RollbackTrigger` firing (e.g. `refusal_rate <= 0.2`). Evidence must be FRESH (the
two-clock discipline from `standing_spendability` — trial evidence observed within its
horizon; stale evidence does not count) and walkable from the P3.1 activation receipt
forward.

**What receipt makes baseline supersession valid?**
The validator **supersession ceremony** (the one proven across validator
v0.1.0→v0.4.0): the NEW `ControlBaseline` carries a receipt produced UNDER the prior
baseline, with content-addressed lineage (bisectable). A `PromotionReceipt` binds:
`prior_baseline_id`, `trial_activation_id(s)`, `evidence_count` + the in-bounds
evidence refs, `new_baseline` content-hash, and the operator/standing basis. Any two
baselines must be diffable from content hashes alone.

**What expires if promotion does not happen?**
The trial activation carries gate-time expiry (P3.1 / shelf-life discipline). No
promotion before expiry → **auto-revert to the prior baseline**. The trial is a
time-boxed experiment: promoted (→ baseline) or expired (→ rollback). It never
silently persists as a third state.

**What rollback/revert path remains?**
The P3.1 rollback restores the config surface to the prior baseline hashes + a typed
rollback receipt (`regressed | exhausted | refused`). Post-rollback hashes ==
baseline (drilled). **Reverting a PROMOTED baseline is itself a supersession** (a new
ceremony back to the prior, with lineage) — NOT a silent undo. Dual-failure
preservation: rollback reason types never collapse.

**What is still bootstrap/degraded?**
In-process forgeability of evidence/receipts (substrate limit, P3.1/P3.3 fence shape
not provenance); operator-fiat standing for the promotion authorization; local
supersession ceremony (no external offices); single tunable only (ops/NQ profile
gated on this surviving one full promotion cycle — constructor-refused otherwise);
the fuse not yet kernel-enforced (`GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001`).

## Refusal cases (promotion REFUSES when)

- insufficient `evidence_count` (< N in-bounds receipts);
- stale / expired trial evidence (freshness horizon lapsed);
- an open `NonDischargeClaim` targets the promotion rung (DebtLedger — promotion is a
  rung transition; open claims block it, recomputed at the gate);
- missing activation receipt (no custodied P3.1 receipt to promote from);
- missing rollback/revert evidence (cannot promote what cannot be reverted);
- attempt to promote MORE than the one scoped tunable (off-surface — fenced like P3.1);
- attempt to alter receipt-kernel / fuse / ratification invariants (constitutional —
  supersession ceremony only, never a promotion side effect);
- operator / standing basis absent where required (promotion is a controller
  transition — above-Governor ratification; operator-fiat for now, never self-minted).

## Hot-path class (ground rule 14) for eventual P4 implementation

**Semantic-conversion (trial → baseline) + spine (baseline-supersession receipt).**
Policy/rule promotion is a SPINE event (consequence-bearing, serial under WIP-1), NOT
an island. It is also a **controller transition** — per the receipt-sovereignty note
it must go through above-Governor ratification (operator-fiat), and the rule requiring
that ratification must eventually be a receipt-kernel invariant, not Governor policy.
NOT island, NOT IPC (single-host bootstrap), NOT a Standing-gate beyond the operator
basis.

## Minimal P4 slice shape (when authorized — NOT now)

1. **P4.0 promotion gate** — observe the one tunable over `evidence_count >= N`
   in-bounds fresh receipts → if met, mint a new `ControlBaseline` via the
   supersession ceremony (PromotionReceipt + content-addressed lineage). Refuse on any
   refusal case above. Prove old/new baseline diffable by content hashes; prove
   expiry auto-revert and rollback-to-baseline still pass.
2. **P4.1 second profile (gated)** — ops/NQ profile admitted ONLY after self-governance
   survives one full promotion cycle (the ops-profile constructor refuses absent a
   self-governance PromotionReceipt). convergence_tuning final disposition decided here
   (adapter vs coexist) with migration receipts.

## Explicitly NOT in P4

Multi-delta interaction; generic activation framework; self-modifying kernel
invariants; receipt-kernel ratification/fuse invariant changes; Rust port; the
loop-AUDIT shadow projection (candidate at most). One promotion surface this band.

## Status

Plan only. Pre-P4 order: `0 ✓ · 1 ✓ · 2 ✓ · 3 ✓ (this doc) · 4 start P4`. P4 entry is
gated on the three HIGH checkpoints (operator present). Next action is the operator's
go for P4.0 implementation — not taken here.
