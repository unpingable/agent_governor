# Crosswalk: SELF_GOVERNANCE_SPEC v0.1 ↔ Workflow-Kernel / Self-Annealing Campaign

Filed 2026-06-12 as a Phase 0 deliverable of `working/campaign-workflow-kernel-annealing.md`.

**Posture:** `specs/core/SELF_GOVERNANCE_SPEC.md` v0.1 ("3.x Preview", captured pre-2026-02,
hardened by external review) is the **authoritative prior**, not stale text. The 2026-06-12
operator/ChatGPT design session independently re-derived most of its spine under new names.
This document maps the two vocabularies before anything is amended or superseded. No silent
vocabulary replacement. No second live 3.x story unless this crosswalk proves a real split.

`specs/gaps/3X_BRAIN_DUMP.md` (2026-02-20) is treated as a rider on the spec: its
five-artifact ontology and LOCKED-as-routing-regime items are included in the mapping.

## 1. Term-by-term mapping

| SELF_GOVERNANCE_SPEC v0.1 | Campaign vocabulary | Mapping quality | Notes |
|---|---|---|---|
| Executor/Proposer separation (§Three Non-Negotiables #1): Governor applies θ and cannot modify it; Meta-Governor proposes Δθ and cannot apply it; narrow audited Acceptance Gate between them | Kernel-invariants vs annealable-userland split; annealing observer/proposer emits `CandidateDelta`s; admission gate activates them | **Same object** | The campaign's "annealing may propose, never apply" IS executor/proposer separation. The campaign adds the layer badges (kernel / app profile / workflow topology / policy-userland / runtime-session state) the spec implies but does not name. |
| Protected θ / `SIGNIFICANCE_CONFIG` marked PROTECTED / "constitution doesn't amend itself" / Capability Discipline ("self-tuning cannot expand its own tool surface") | Non-annealable kernel core; tunable-surface **allowlist enum**; four forced-True HardGuards (`kernel_invariant_mutation_forbidden`, `refusal_semantics_mutation_forbidden`, `custody_mutation_forbidden`, `publication_rules_mutation_forbidden`); genesis-class scope refused at construction | **Same object, sharper enforcement point** | Spec protects by convention + gate check; campaign enforces at delta *construction* (cannot even build an off-allowlist delta) and inherits constellation directional custody (genesis-class surfaces never self-amend). |
| Acceptance Gate (meta-invariants + measurement gating + capability check + hysteresis/dwell + cross-model quorum) | Delta admission: allowlist check, named `ControlBaseline`, mandatory expiry + `RollbackTrigger`, human approval forced True, optional wicket wrap (`operation_class=authorize`, `intended_action=policy_delta_apply`) | **Same object** | Spec's cross-model validator quorum is NOT in the campaign's Phases 0–4 — deferred, see §3 divergences. |
| Admissible Measurement Gating (Δθ justified only by admissible measurements, never model narrative; `INADMISSIBLE_SIGNALS`) | `AnnealingObservation` receipts derived only from receipt streams (loop-protocol §11 metrics: burn-per-progress, failure-class entropy, decomposition stats); observer purity pinning test (zero mutation receipts) | **Same object** | Campaign grounds "admissible" in the existing receipt plane rather than a bespoke `AdmissibleMeasurements` dataclass. NLAI already supplies the narrative ban. |
| `ThetaDelta` + `ProofCarryingDelta` (machine-checkable why-bundle: measurements snapshot, thresholds used, invariants checked, predicted effect, proof hash) | `AnnealingDelta` (generalized `convergence_tuning.TuningProposal`: Scope, ChangeSet, source observation receipts, PredictedImpact, admissibility check results, content-addressed identity) | **Same object** | `TuningProposal` is the already-shipped ~90% implementation of `ProofCarryingDelta`. The campaign names that fact and promotes the custody pattern (not the domain module) into `annealing.py`. |
| `ThetaSnapshot` + `RollbackController` (θ history, evaluation windows, baseline-vs-current triggers, `_validate_rollback_target` policy-hash check) | `ControlBaseline` registry (named, admitted rollback target: content-addressed config hashes + session-continuity checkpoint ref + creation receipt + lineage) + typed rollback receipts (regressed\|exhausted\|refused) | **Same object, one upgrade** | Spec's "can't rollback to pre-amendment config after amendment" (policy-hash match) maps directly to baseline lineage. Campaign upgrade: rollback restores topology, never history — receipt-additive, no erasure. Spec's stratified `BaselineMetrics` (Simpson's-paradox defense) belongs to *observation*, not to the rollback target — the campaign's `BaselineProfile` vs `ControlBaseline` split makes this explicit. |
| Hysteresis + dwell + bounded step (`max_delta_per_epoch`) | Delta expiry/trial windows; ultrastability `ParameterSpec` floor/ceiling/step reused; pathology auto-freeze + human unfreeze | **Same object** | Already shipped in `ultrastability.py`/`homeostat.py`/`coupling.py`; campaign assigns them their layer badge (policy-userland, per-turn, *within* current shape) and keeps them distinct from annealing (*future* shape). |
| No Epistemic Laundering (U_t decreases only via legitimate *path*; `AcceptanceProvenance`; BLOCKER_REDEFINED / SCOPE_SHRUNK_SILENTLY) | `RecompositionReceipt` + `account_boundaries()` — every admitted decomposition boundary must carry a disposition; unaccounted boundary ⇒ `refused_laundering`. "Lossy intent is allowed; unreceipted loss is laundering." | **Same principle, NEW surface** | The spec polices laundering at the *θ/uncertainty* plane. The campaign extends the identical path-not-value principle to the *work* plane (decompose→recompose). This is the campaign's largest genuinely-new contribution; it implements the spec's principle where the spec had no coverage. |
| Signed Policy Snapshots / Constitutional Hash | `ControlBaseline` content-addressed config hashes (policy_ir hashing pattern); validator `ruleset_hash` pinning (already shipped, `standing/validator.py`) | **Same object** | Partially shipped already. |
| Meta-Audit Log (hash-chained, structural signals) | Gate receipts + receipt_kernel hash-chained ledger (shipped); annealing lifecycle receipts ride the existing plane | **Already shipped** | No new audit substrate needed. |
| Freeze/Unfreeze sovereignty; E-Stop | Ultrastability pathology freeze (shipped); delta activation halt + rollback; baseline deletion refused while referenced | **Same object** | |
| Gap 9: Constitutional Revision Events ("amendments must themselves be receipted events") | Validator supersession ceremony (`standing/validator.py` v0.1→v0.4: new version requires a validation receipt produced by the prior version) reused for baseline promotion | **Spec gap, ALREADY SOLVED in-tree** | The spec listed this as unsolved; the standing validator shipped the mechanism in 2026-06. Crosswalk closes Gap 9 by reference. |
| Brain-dump #2: five-artifact ontology (`MeasurementSnapshot` / `TransitionProposal` / `AuthorityReceipt` / `RecoveryPlanReceipt` / `ResetReceipt`) | `AnnealingObservation` / `AnnealingDelta` / admission+approval receipts / *(no analog — see divergences)* / typed rollback receipt | **4 of 5 map** | `RecoveryPlanReceipt` (planned recovery vs stumbled-into-working-state) has no campaign analog. Not absorbed; remains a brain-dump item. |
| Brain-dump #1: LOCKED as routing regime | Not addressed by this campaign | **Out of scope** | Routing-regime control law is orthogonal to annealing; stays with regime/lanes work. |
| Replay + holdout non-regression (MUST list); canary rotation; runtime harness | Trial activation window + post-activation receipts within `PredictedImpact` bounds; scars-style evidence-count promotion; Phase C1 REPLAY_HARNESS (shipped, offline) as future evaluation substrate | **Same intent, thinner v1** | See divergences §3 — the campaign's Phase 3/4 evaluation is deliberately weaker than the spec's full harness. |
| Workload-shift blindness / credit assignment ("one Δθ at a time") | Phase 3 "wire exactly one pipeline, lowest-stakes tunable"; Phase 4 "multi-delta interaction out of scope" | **Same discipline** | |
| Auth service boundary / capability tokens / multi-tenant (§3.x Service Boundary) | Not addressed | **Out of scope** | Governor-as-a-service track; the campaign explicitly targets the *singular governor instance*. |
| checkpoint/fork/promote (session_continuity, cited by spec ecosystem) | **Red line:** checkpoints/forks/promotions are resumability/continuity machinery unless explicitly admitted as control-plane baselines. Promoted session state ≠ known-good policy baseline. | **Semantic mismatch, now fenced** | The spec never conflated these, but nothing previously *prevented* the conflation. The campaign's doctrine doc pins it. |

## 2. What the campaign adds that the spec does not have

1. **The recomposition surface.** `RecompositionReceipt` + boundary accounting — laundering
   defense applied to decompose→recompose, not just θ/U_t. The spec's no-laundering principle,
   new jurisdiction.
2. **`TransformationPipeline` as the unit of governance** (pipeline types: text→action,
   event→action, claim→verdict, …) with profiles (self-governance, ops/NQ). The spec governs
   *the governor's parameters*; the campaign also governs *the shape of the work*.
3. **Intent fidelity classes** (exact/bounded/heuristic/exploratory) + declared loss budgets,
   judged at recomposition. No spec analog; composes with admissible-measurement discipline
   (fidelity is declared and receipted, never narrated after the fact).
4. **Layer badges** — the explicit kernel / app profile / workflow topology / policy-userland /
   runtime-session-state classification the spec's HARD BOUNDARY diagram implies for exactly
   two layers.
5. **Constellation composition** — directional custody, wicket wrap for delta admission,
   LA opaque fidelity echo. The spec predates the constellation seam work.

## 3. Real divergences (not just renames) — flagged, not resolved here

1. **Cross-model validator quorum.** The spec's one-liner: *"Any theta update requires
   admissible measurement coverage + independent validator quorum + no valid veto witness."*
   The campaign's Phases 0–4 require human approval (forced True) but NO validator quorum.
   Disposition options: (a) human-approval-forced-True is the v1 *stronger* substitute and
   quorum arrives when auto-apply is ever contemplated (campaign's implicit position), or
   (b) quorum is constitutional and Phase 3 activation must carry it. **Operator call at
   Phase 0 review.** Recommendation: (a) — quorum machinery (`quorum.py`, codex-exec
   adversarial review) exists if wanted, but forced-human is strictly more conservative than
   quorum-gated automation.
2. **Evaluation rigor.** Spec MUSTs include replay+holdout non-regression before apply.
   Campaign Phase 3 activates after admissibility checks + human approval, with rollback
   triggers as the safety net; replay-based pre-evaluation (Phase C1 harness) is named but
   not required. Recommendation: acceptable for the lowest-stakes tunable in Phase 3a;
   promotion (Phase 4) should revisit replay/holdout as a promotion criterion.
3. **Statistical significance machinery.** Spec's `SignificanceConfig` (sample size, effect
   size, CI width) has no campaign analog; observations feed deltas without significance
   gating in v1. Recommendation: fold as admissibility check when observation volume makes
   it meaningful; premature now (review note #1 in the spec itself says δ/ε are vibes
   without an estimator — don't fake it).
4. **`RecoveryPlanReceipt`** (brain-dump #2/#3/#6): no campaign analog. Stays open in the
   brain dump; not this campaign's jurisdiction.

## 4. Disposition (recommendation)

**Option 1 — parent implementation track — with scoped carve-outs.**

- This campaign is formally **the implementation track for SELF_GOVERNANCE_SPEC's core**
  (§Three Non-Negotiables, Safety Monotonicity, No Epistemic Laundering, Proof-Carrying Δθ,
  Constitutional Hash, Capability Discipline), under the campaign vocabulary. The mapping in
  §1 shows these are the same objects; maintaining two names for each would be the
  "two live 3.x stories" hazard realized.
- **Amendment, not rewrite:** when Phase 2 lands, SELF_GOVERNANCE_SPEC gains a short
  vocabulary-bridge preamble (spec term → campaign term → implementing module) and its v0.1
  pseudocode sections are marked *illustrative; superseded by implementation* section by
  section as each lands. Review Notes #1–8 and the MUST/SHOULD/MAY list remain binding
  acceptance inputs for Phases 3–4.
- **Carve-outs that remain the spec's own (not absorbed):** validator quorum policy,
  runtime harness/canary rotation, dual ledger (U_t, C_t economics), LOCKED-as-routing-regime,
  auth service boundary / capability tokens / multi-tenant. These stay spec-side, unclaimed
  by this campaign.
- **Gap 9 closed by reference** to the validator supersession ceremony.
- The four divergences in §3 are recorded in the campaign card as HIGH-cadence checkpoints
  (operator decisions at the phase that touches each), not silently resolved here.

Per operator instruction 2026-06-12: presumption toward option 1; this crosswalk is the
evidence for it. **One nod ratifies; until then SELF_GOVERNANCE_SPEC stands unmodified.**

---

## RATIFIED 2026-06-12

Operator ratified Option 1: **SELF_GOVERNANCE_SPEC is the parent implementation track for
this campaign**, with these items held as carve-outs / checkpoints (NOT absorbed, NOT
blocking P1):

- validator quorum — stays spec-side; HIGH checkpoint at Phase 3a entry (divergence #1)
- replay/holdout runtime rigor — promotion-criterion question, Phase 4 (divergence #2)
- significance gating — fold when observation volume is meaningful (divergence #3)
- RecoveryPlanReceipt — remains a brain-dump item, not this campaign's jurisdiction
- auth boundary / dual ledger — stay spec-side until explicitly sliced

The amendment-not-rewrite mechanic stands: SELF_GOVERNANCE_SPEC gains the vocabulary-bridge
preamble + section-by-section "superseded by implementation" marks **when Phase 2 lands**,
not before. The spec remains byte-unmodified through Phases 0–1.

## Divergence #2 RESOLVED 2026-06-13 (P4 entry, Checkpoint 1)

**Decision: replay/holdout IS a promotion criterion.** Promotion of the surviving
`max_slices=4` trial into a `ControlBaseline` requires a **dual gate**, both witnesses
mandatory and **never folded into one**:

1. **live survival witness** — `evidence_count >= N` fresh, in-bounds, walkable-from-
   activation receipts (*did the trial survive reality?*);
2. **replay/holdout falsification witness** — a Phase C1 `REPLAY_HARNESS` non-regression
   pass against a frozen corpus, emitting a separate `ReplayHoldoutReceipt` (frozen corpus
   hash, harness version, comparator baseline id, verdict) (*does promotion avoid known
   regression?*).

**Scope:** replay/holdout is a **promotion falsification gate** — not a tuning optimizer,
not a new selection surface. No post-hoc case selection, no mutation on failure, no claim
that replay proves optimality. Failure of either witness blocks promotion and leaves the
prior baseline authoritative.

**Rationale (operator):** P4 is precedent-setting authority conversion; the first
promotion ceremony becomes the template. An evidence-count-only first baseline would teach
the governor that spec-MUSTs are aspirational. The criterion **applies to this first P4
promotion**, not merely to future tunables — the root of the promoted lineage must carry
the criterion its descendants inherit (no poisoned-bootstrap exception).

Recorded in `working/P4-promotion-plan-2026-06-13.md` (the seven-questions doc, evidence
section + refusal cases + `PromotionEligible` predicate) and reflected in
`specs/gaps/GOV_GAP_CONTROL_BASELINE_001.md` (Phase-4 promotion). Divergences #1 (validator
quorum), #3 (significance gating), #4 (RecoveryPlanReceipt) remain as recorded.
