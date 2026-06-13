# GOV_GAP_ANNEALING_DELTA_001

## Title

AnnealingObservation → CandidateDelta lifecycle: receipt-driven candidate policy deltas —
admitted, scoped, expiring, reversible, baseline-tied — generalizing the
`convergence_tuning.TuningProposal` custody pattern without depending on the domain module.

## Status

Gap spec — **proposed, awaiting one-nod ratification.** Phase 0 deliverable of
`working/campaign-workflow-kernel-annealing.md`. No build authorized by this filing.
Observation receipts are Phase 1; the delta object is Phase 2; **activation is Phase 3a and
is a separate authorization event** — nothing in Phases 1–2 can apply anything.

## Origin

2026-06-12 design session: *"Self-annealing is receipt-driven adjustment of future pipeline
shape, never silent reinterpretation of present obligations."* Crosswalk finding
(`working/crosswalk-self-governance-spec.md`): `AnnealingDelta` IS
SELF_GOVERNANCE_SPEC's `ProofCarryingDelta`, and `convergence_tuning.TuningProposal` is its
already-shipped ~90% implementation (admissibility checks, forced-True HardGuards,
forced-human Approval, RollbackTrigger, ProposalStore, full propose→apply→rollback receipts).

**The refusal that cannot be expressed today:** "this delta targets a non-tunable surface."
There is no typed answer to *what may annealing touch* — convergence_tuning's scope
vocabulary is fiction/anchor-domain; nothing covers routing/budgets/decomposition/witness
placement, and nothing refuses a genesis-class target at construction.

## What exists

1. `convergence_tuning.py` — the custody pattern (see Origin). Prior art / first
   specialization; **untouched through 2.9.x**.
2. `scars.py` — evidence-gated relaxation (`evidence_count >= required`, never wall-clock):
   the promotion criterion. Lineage: scar (remembered friction) → AnnealingObservation
   (classified friction with future-policy implication) → CandidateDelta (proposed
   adjustment).
3. `ultrastability.py` — bounded `ParameterSpec` (floor/ceiling/step) + pathology
   auto-freeze + human unfreeze: the pathology guard for delta trials.
4. `homeostat.py`/`coupling.py` — the per-turn recommend/decide loop; stays distinct
   (tunes *within* the current shape; annealing changes the *future* shape).
5. `overrides.py` — scoped+expiring+revocable receipt shape for activation windows.
   Known debt NOT to inherit: GOV_GAP_AUTHORIZATION_SHELF_LIFE_001 (expiry as metadata with
   zero gate-time callers) — delta expiry is gate-time-enforced from day one.
6. Loop-protocol §11 / `working/pipeline-doctrine-2026-06-12.md` — burn-per-progress,
   failure-class entropy, PROBE-wall ("probe sessions emit zero mutation receipts"): the
   observation metric definitions and the observer-purity pattern. Consume, don't re-derive.

## What needs building

1. **`AnnealingObservation`** (Phase 1, `src/governor/annealing_observer.py`): read-only
   receipt-stream consumer emitting observation receipts — source_receipts, pattern
   (retry_exhaustion | repeated_refusal | witness_gap | recomposition_loss |
   verifier_fragility), affected pipeline/profile, suggested delta kind. OBSERVE rung only;
   purity pinned (zero mutation receipts per observer run).
2. **`AnnealingDelta`** (Phase 2, `src/governor/annealing.py`): generalized proposal —
   tunable-surface **allowlist enum** as Scope (routing, budgets, decomposition size, retry
   posture, witness placement, default gates — closed); HardGuards extended with four new
   forced-True fields (`kernel_invariant_mutation_forbidden`,
   `refusal_semantics_mutation_forbidden`, `custody_mutation_forbidden`,
   `publication_rules_mutation_forbidden`); mandatory expiry + named `ControlBaseline` +
   `RollbackTrigger` at construction; shadow/effective status; source observation receipts;
   content-addressed identity.
   **Dependency direction (operator-pinned): `annealing.py` must NOT import
   `convergence_tuning.py`.** Extract pure shared custody helpers into a neutral module
   both import, or copy with a noted debt; convergence_tuning's adapter/coexist disposition
   is a Phase 4 decision. *Promote the custody pattern, not the domain module.*
3. **Admissibility checks** (Phase 2): refuse if target off-allowlist; no named
   ControlBaseline; no RollbackTrigger; no expiry; auto_apply requested; genesis-class
   scope (standing/, LA, wicket, receipts, classification policy, doctrine files) — typed
   refusal at construction.
4. **Activation/rollback** (Phase 3a, separate gap-level authorization):
   `activate(delta, baseline_id, checkpoint_id)` — required args, hash-validated, no
   defaults; human approval receipt; gate-time expiry; rollback restores config surfaces to
   baseline hashes + typed rollback receipt (regressed | exhausted | refused — dual-failure,
   never collapsed). Promotion (Phase 4): scars-style evidence count within
   `PredictedImpact` bounds → new ControlBaseline via supersession ceremony.
5. **LA-degraded authority** (operator amendment 2026-06-12, see
   `working/seam-la-fidelity-pools.md`): annealing must run without LA — local/static
   budgets, receipt-only spend summaries, **reduced annealing authority** (no cross-run
   metabolic budgets). Any delta whose trial or budget semantics require LA-backed spend
   custody must refuse or downgrade with typed reason `requires_la_custody` when LA is
   absent — never pretend local accounting is equivalent.

## Acceptance criteria

- AC1 (Phase 1): observer purity pinning test — an observer run emits zero mutation
  receipts, checkable from the receipt trail (the PROBE-wall pattern).
- AC2 (Phase 2): every constructional refusal is typed + receipted with call-count-zero
  teeth on the next stage.
- AC3 (Phase 2): no apply path exists — grep-fence + runtime assertion that no code path
  leads from `AnnealingDelta` to any config write.
- AC4 (Phase 2): genesis-class fence test — delta scoped at any genesis surface refused at
  construction.
- AC5 (Phase 3a): full lifecycle drill receipted end-to-end (propose → approve → activate →
  trip trigger → rollback → post-rollback config hashes == baseline hashes); expiry
  auto-revert drill.
- AC6 (Phase 3a): path fence — activation writer confined to `.governor/annealing/` +
  designated config keys.
- AC7: import fence — `annealing.py` imports no mutation-capable internals of
  standing/wicket/LA/receipt_kernel and does not import `convergence_tuning`.
- AC8: `requires_la_custody` refusal fires when an LA-dependent delta is constructed or
  activated with LA absent; AG-local annealing (static budgets) proceeds unaffected.

## Non-goals

- NO auto-apply, any phase (Approval.requires_human forced True; relaxation would be a
  kernel-grade amendment with validator-quorum implications per crosswalk §3.1).
- NO annealing of refusal semantics, custody semantics, kernel invariants, or
  authorization/publication rules — ever, via this surface.
- NO mutation of `convergence_tuning.py` or migration of its consumers (Phase 4 decision).
- NO multi-delta interaction reasoning (one Δ at a time; credit-assignment discipline).
- NO new audit substrate — lifecycle receipts ride the existing gate-receipt plane.
- NO LA/wicket contract changes (wicket wrap is AG-side composition).

## Open questions

1. Crosswalk divergence #1: does Phase 3 activation ever need validator quorum on top of
   forced-human approval? (HIGH checkpoint at Phase 3 entry.)
2. Crosswalk divergence #2: is replay/holdout non-regression a promotion criterion in
   Phase 4? (Bias: yes, via the existing C1 REPLAY_HARNESS, once a delta has trial data.)
3. Neutral shared-custody module name if extraction is chosen (`proposal_custody.py`?) —
   decide at Phase 2 implementation against actual shared surface size.

## Bound debt: P2_GENESIS_TARGET_ALLOWLIST_001 (bound 2026-06-13)

Per the debt-binding rule (GOV_GAP_PLAN_DECOMPOSITION_PROTOCOL_001 §kernel #3:
future-rung debt is admissible only if it binds a named collecting rung and
blocks that rung until discharged), the P2.1 genesis-detector debt is recorded
as a **standing obstacle**, not a log note:

```
debt_id:            P2_GENESIS_TARGET_ALLOWLIST_001
class:              future_rung_debt
collecting_rung:    Phase 3a activation preflight (P3.0)
blocks_before:      any AnnealingDelta activation / effect conferral
discharge_condition: per-surface target ALLOWLISTS replace/constrain the
                     free-form `target`; activation-eligibility refuses while
                     any target label is free-form (proven, not asserted)
owner:              operator (ratifies discharge)
```

This door does not open until the debt is paid: no activation rung may proceed
while `target` is free-form and only the best-effort normalized genesis detector
guards it.

## Required before Phase 3 activation (recorded 2026-06-13, P2.1 fuse outcome)

- **Per-surface target allowlists.** P2.1 ships a normalized-substring genesis *detector*
  on the free-form `target` (`annealing.py:_targets_genesis`). The surface allowlist is the
  real authority gate (closed 6-element set); the genesis detector is best-effort
  defense-in-depth — acceptable for candidate/no-apply custody, but a denylist over a
  free-form string is the wrong shape for *granting* activation authority (it can over-refuse
  oddly-named knobs and chases spelling evasions). **Before any Phase 3 activation, the
  free-form `target` must be replaced/constrained by per-surface known-knob ALLOWLISTS.**
  Doctrine: *candidate deltas may use normalized genesis detection as defense-in-depth;
  activation requires actual target allowlists.* (Fuse fired during P2.1 on tokenizer
  evasions — root cause was "string denylist is not the real boundary"; operator ratified
  the normalized-substring patch for P2.1 and recorded the allowlist redesign as the
  Phase-2.x/pre-activation direction.)
