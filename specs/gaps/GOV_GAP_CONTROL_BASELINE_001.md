# GOV_GAP_CONTROL_BASELINE_001

## Title

ControlBaseline registry + seam checkpoints: named, admitted rollback targets for
control-plane mutation — fenced hard against continuity machinery (a promoted session is
not a baseline) and against metric snapshots (a BaselineProfile is not a rollback target).

## Status

Gap spec — **proposed, awaiting one-nod ratification.** Phase 0 deliverable of
`working/campaign-workflow-kernel-annealing.md`. No build authorized by this filing.
Registry is Phase 2; rollback exercise is Phase 3a.

## Origin

2026-06-12 design session: *"No self-annealing without a named known-good baseline and a
receipted rollback path"*; *"checkpoint everything that changes shape; baseline only what
survives judgment."* Operator red line (doctrine
`docs/doctrine/annealing_and_recomposition.md` §4): **checkpoints/forks/promotions are
resumability/continuity machinery unless explicitly admitted as control-plane baselines.**
Crosswalk: this is SELF_GOVERNANCE_SPEC's `ThetaSnapshot`/`RollbackController` (including
its "can't roll back to pre-amendment config" policy-hash rule), upgraded with
receipt-additive rollback and the continuity fence.

**The refusal that cannot be expressed today:** "no activation without a named, admitted
rollback target." Nothing currently types a known-good control-plane state; the nearest
rhymes are the wrong objects (session promotion = custody transfer of working state;
auto_tuning BaselineProfile = metric distribution; ExecutionState = resumability envelope).

## What exists

1. `session_continuity.py` — Capsule/Checkpoint/fork/promote. **Reused, not duplicated**:
   seam checkpoints are session-continuity Checkpoints carrying a `seam=` tag
   (`pre_delta_activation`, `post_activation`, `post_dogfood_verdict`, …). Promotion there
   remains continuity-local; it never mints a ControlBaseline.
2. `policy_ir.py` — content-addressed vocabulary/slot-set hashing: the identity pattern for
   baseline config hashes.
3. `auto_tuning.py` `BaselineProfile` — metric snapshot ("what normal looked like");
   feeds observations, never a rollback target. Naming fence is binding (doctrine §6).
4. `standing/validator.py` supersession ceremony — the promotion mechanism: a new baseline
   must carry a receipt produced under the prior baseline (closes SELF_GOVERNANCE_SPEC
   Gap 9 "constitutional revision events" by reference).
5. `convergence_tuning.py` ProposalStore — the file-per-item store pattern.
6. `config_effective.py` — layered effective-config resolution; the surface a baseline
   snapshot hashes over (designated keys only).

## What needs building

1. **`ControlBaseline`** (Phase 2, `src/governor/control_baseline.py`): frozen dataclass —
   name; content-addressed hashes of the designated config surfaces (policy_ir hashing
   pattern); `session_continuity` Checkpoint reference; creation receipt id; lineage
   pointer (supersedes); admitted_by. File-per-item registry under
   `.governor/control_baselines/`.
2. **Admission step**: a ControlBaseline exists only via an explicit admission with a
   creation receipt. No auto-minting from session promotion, schedule, or delta activation.
3. **Rollback semantics** (Phase 3a): restore designated config surfaces to baseline
   hashes; emit rollback receipt typed regressed | exhausted | refused; **rollback restores
   policy/topology, not history** — the failed trial's receipts remain (aircraft incident
   report, not git revert).
4. **Reference counting / deletion fence**: baseline deletion refused while any active or
   unexpired delta references it.
5. **Promotion** (Phase 4): trial checkpoint earns baseline status via the supersession
   ceremony; lineage is content-addressed so any two baselines are diffable from hashes
   alone (bisectability: "the badness entered at C3" is a query, not an archaeology dig).
   **Promotion eligibility is a DUAL gate (Checkpoint 1, RATIFIED 2026-06-13, crosswalk
   divergence #2):** a live survival witness (`evidence_count >= N` fresh, in-bounds,
   walkable-from-activation receipts) AND a replay/holdout falsification witness (Phase C1
   `REPLAY_HARNESS` non-regression pass against a frozen corpus, emitting a separate
   `ReplayHoldoutReceipt`: frozen corpus hash, harness version, comparator baseline id,
   verdict). The two witnesses are **never folded** (different epistemology, different
   receipt). Replay is a *promotion falsification gate*, not a tuning optimizer or
   selection surface. The eligibility predicate is implemented substrate-agnostically in
   `src/governor/promotion_gate.py` (P4.0a); minting the ControlBaseline on an eligible
   verdict is P4.0b (gated on the convergence_tuning disposition). See
   `working/P4-promotion-plan-2026-06-13.md`.
6. **Lineage validity rule**: rollback target must be lineage-compatible with the current
   constitution (the spec's policy-hash rule) — you cannot roll back across an admitted
   kernel upgrade.

## Acceptance criteria

- AC1 (Phase 2): constructing/admitting a baseline emits a creation receipt; registry
  round-trips; hashes are stable and content-addressed.
- AC2 (Phase 2): the red-line fence — no code path from `session_continuity.promote()` to
  baseline creation (grep-fence + test); a session promotion does not change the baseline
  registry.
- AC3 (Phase 3a): rollback drill — post-rollback designated config hashes equal baseline
  hashes; rollback receipt present and typed; trial receipts still present (no erasure).
- AC4 (Phase 3a): deletion fence — deleting a referenced baseline is a typed refusal.
- AC5 (Phase 4): bisectability — given any two baselines in a lineage, the config diff is
  reconstructable from stored hashes alone.
- AC5b (Phase 4, Checkpoint 1): the dual promotion gate refuses on a missing/failed
  replay/holdout witness even when the live survival witness passes, and vice versa; the
  two witnesses are carried as separate receipt references, never folded. (Predicate-level
  refusals: `tests/test_promotion_gate.py`; ceremony-level: P4.0b.)
- AC6: rollback across a kernel-upgrade boundary refused (lineage validity).

## Non-goals

- NOT a session/state restore mechanism (that is session_continuity's job).
- NOT a metric baseline (that is BaselineProfile's job).
- NOT a git-layer construct — baselines cover designated governance config surfaces, not
  the working tree.
- NOT automatic baseline capture on a timer; admission is always explicit.
- NOT dependent on LA: baseline/checkpoint/rollback semantics are core and must operate
  with LA absent (standalone invariant, `working/seam-la-fidelity-pools.md`).

## Open questions

1. The designated config-surface list (what a baseline hashes over): exact key set is a
   Phase 2 decision; bias minimal (the surfaces the tunable allowlist can touch, nothing
   more).
2. Seam-tag vocabulary: closed set now (`pre_delta_activation`, `post_activation`,
   `post_dogfood_verdict`, `pre_publication`) or open string? Bias closed, extended by
   doctrine edit.
3. Does ControlBaseline carry the BaselineProfile (metric snapshot) *by reference* for
   trial comparison? Bias: yes, by receipt/hash reference, never by embedding — keeps the
   two "baseline" senses physically separate.
