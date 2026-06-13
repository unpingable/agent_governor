# Campaign Card — Workflow Kernels + Self-Annealing

Filed 2026-06-12. Plan-mode survey + operator Q&A locked four decisions and three
amendments (recorded in §1). Template: `working/campaign-standing-before-spendability.md`.
Doctrine: `docs/doctrine/annealing_and_recomposition.md`. Crosswalk:
`working/crosswalk-self-governance-spec.md` (this campaign is presumptively the
implementation track for `specs/core/SELF_GOVERNANCE_SPEC.md`). Gap specs:
`GOV_GAP_RECOMPOSITION_RECEIPT_001` / `GOV_GAP_WORKFLOW_KERNEL_PROTOCOL_001` /
`GOV_GAP_ANNEALING_DELTA_001` / `GOV_GAP_CONTROL_BASELINE_001`.

## 0. Question / invariant / definition of done

**Question:** can the governor stop being procedural-config and become a kernel + adaptive
userland — typed transformation pipelines whose recomposition refuses laundering, with
receipt-driven self-annealing of future pipeline shape — without ever letting userland
mutate the kernel?

**Invariant (the campaign's single sentence):** *output is not admissible unless its
recomposition can account for every admitted decomposition boundary; policy may anneal only
outside the kernel boundary, only via admitted, scoped, expiring, baseline-tied deltas.*

**Compelling-MVP definition:** one full annealing lifecycle on the self-governance profile
(observe → candidate delta → human-admitted activation → tripped rollback → receipted
restore) PLUS one enforced `refused_laundering` at the orchestrator seam, both walkable via
`why`-style chains. Minimal = Phase 1 shadow only (receipt shape proven against real runs).

## 1. Ground rules (binding on every slice)

1. **Grep-first.** The survey says the primitive probably exists; check before building.
2. **Teeth standard.** Every refusal test asserts call-count zero on the next stage.
3. **Dogfood before cargo.** Process verdict validated before artifact verdict; ops/NQ
   profile constructor-refused absent a self-governance promotion receipt.
4. **Verifier exit discipline.** Greens are exit-code-witnessed (`governor verify-run`);
   no log-string parsing in any verdict path.
5. **One new enforcement surface per release band** (operator amendment 2): 3a teeth land
   and drill before 3b flips shadow→enforcing.
6. **Dependency direction** (operator amendment 1): `annealing.py` never imports
   `convergence_tuning.py`. Promote the custody pattern, not the domain module.
7. **Standalone invariant** (operator amendment 3): AG must remain operational without LA.
   LA-dependent authority refuses/downgrades with `requires_la_custody`; core
   recomposition/refusal/checkpoint/baseline semantics never depend on LA presence.
8. **The red line.** Checkpoints/forks/promotions are continuity machinery unless
   explicitly admitted as control-plane baselines. No baseline laundering.
9. **Layer badges.** Every new primitive declares its layer (kernel / app profile /
   workflow topology / policy-userland / runtime-session state) at introduction.
10. **No silent caps on the spec.** SELF_GOVERNANCE_SPEC stays unmodified until the
    crosswalk disposition is ratified; divergences are HIGH checkpoints, not quiet edits.
11. **Forbidden work** (smuggling = stop and re-scope): auto-apply in any form; annealing
    of refusal/custody/kernel semantics; loop-FSM codification before Phase 4; LA/wicket/
    standing contract changes; receipt_kernel invariant additions; governor-as-a-service
    surfaces; touching W1 launch-runway artifacts.

## 2. Decisions locked (operator, 2026-06-12)

| # | Decision | Ruling |
|---|---|---|
| D1 | SELF_GOVERNANCE_SPEC relationship | Crosswalk first, presumption parent-implementation-track; disposition ratified at Phase 0 review. No silent vocabulary replacement. |
| D2 | First shadow seam | Cooked-context orchestrator, immediately after `ChainResult`. Loop FSM stays doc-side. *"First observe recomposition against a typed result; do not codify the daily loop as kernel law until the receipt shape survives contact with reality."* |
| D3 | convergence_tuning custody | New thin `annealing.py` generalizes the custody shape; convergence_tuning untouched through 2.9.x; adapter/coexist decided Phase 4. |
| D4 | Intent fidelity home | AG-side (declared at intent_compiler, judged at recomposition); LA echoes opaquely, zero LA change; **active** constellation seam note with promotion criteria (`working/seam-la-fidelity-pools.md`). |
| A1 | Dependency direction | Generic annealing must not depend on a domain tuning module (ground rule 6). |
| A2 | Enforcement pacing | Phase 3 hard-split 3a → 3b (ground rule 5). |
| A3 | LA standalone rule | *"AG may run poor without LA. It must not run blind, and it must not fake being rich."* (ground rule 7; doctrine §5). |

## 3. Spine — phases as slices

Version mapping: Phase 0 → 2.8.x (docs) · Phases 1–2 → 2.9.x (additive, shadow-only, safe
alongside the W1 launch runway) · Phase 3 → **3.0.0** · Phase 4 → 3.0.x. Current: 2.8.1.

### P0 — docs/spec only *(this filing)*

Deliverables: this card; crosswalk; 4 gap specs; doctrine doc; LA seam note.
DoD: operator review — crosswalk disposition stated; every new primitive justified by a
named refusal; zero unresolved vocabulary collisions; zero changes under `src/`, `libs/`,
`tests/`. **HIGH checkpoint: crosswalk disposition + the four divergences (validator
quorum, replay/holdout rigor, significance gating, RecoveryPlanReceipt).**

### P1 — read-only observation (2.9.x)

1. **P1.1 (first safe code slice):** `RecompositionReceipt` + pure `account_boundaries()`
   + golden fixtures from existing receipt trails + synthetic dropped-slice fixture
   yielding `refused_laundering`. No wiring.
2. **P1.2:** shadow emission at the orchestrator seam (`shadow: true / effective: false`;
   names accepting kernel/profile as provisional; cites ChainResult basis). Teeth test:
   downstream call counts unchanged when shadow verdict is refused.
3. **P1.3:** `annealing_observer.py` — observation receipts from loop-protocol §11 metric
   definitions; purity pinned (zero mutation receipts per run).
4. **P1.4:** intent_compiler fidelity_class + losses_declared + loss posture (defaulted,
   unenforced; bit-for-bit behavior preservation); LA opaque echo where generic metadata
   already exists.

DoD: full suite green, zero existing-test modifications; AC1–AC6 of
GOV_GAP_RECOMPOSITION_RECEIPT_001; AC1–AC2/AC5 of GOV_GAP_WORKFLOW_KERNEL_PROTOCOL_001;
AC1 of GOV_GAP_ANNEALING_DELTA_001.
Out of scope: enforcement, delta generation, receipt_kernel changes, loop-FSM codification.
Cadence: AUTOPILOT after P0 ratification; P1.1 is dispatchable as a single slice.

### P2 — candidate deltas, no activation (2.9.x)

1. **P2.1:** `annealing.py` `AnnealingDelta` (allowlist Scope; 4 new forced-True
   HardGuards; mandatory expiry + named baseline + RollbackTrigger at construction;
   shared custody via neutral helper module or noted-debt copy — never importing
   convergence_tuning).
2. **P2.2:** `control_baseline.py` `ControlBaseline` registry (admission-only creation,
   creation receipts, red-line fence: no path from session promotion to baseline minting).
3. **P2.3:** CLI `governor annealing propose|list|show` — **no apply verb ships**.

DoD: deltas produced from real P1 observations; every refusal typed+receipted with
call-count-zero teeth; grep-fence + runtime assertion of no delta→config-write path;
genesis-class fence; `requires_la_custody` refusal on LA-dependent construction with LA
absent. Out of scope: activation, promotion, expiry execution, ops/NQ profile,
convergence_tuning migration.
Cadence: AUTOPILOT; **HIGH checkpoint at exit: review the tunable-surface allowlist enum
before any activation work begins.**

Phase 3 reshaped (2026-06-13 design pass): the opening slice moved from "start
activation machinery" to "prove activation cannot begin unless the debt/authority
gates are real." Split into P3.0 → P3.1 → P3.2. The decomposition doctrine
(GOV_GAP_RUNG_DEBT_COLLECTION_001) is P3.0 acceptance criteria, not a reason to
stall.

### P3.0 — activation preflight, NO activation (the next authorized slice)

Goal: build the gates that keep activation impossible until debts are collected.
Required:
- per-surface target ALLOWLISTS replace/constrain the free-form `target` —
  **discharges `P2_GENESIS_TARGET_ALLOWLIST_001` by mechanism, not prose**
  (free-form target → `refused_activation_eligibility`; allowlisted → eligible).
- activation-eligibility checker that **proves** activation is impossible while
  any target is free-form OR any `NonDischargeClaim` targeting activation is open.
- route future-rung debt into `NonDischargeClaim` (not commit prose); enforce
  `authorized_collector != target_rung`; parked recomposition boundaries share
  content-addressed identity with the claim they mint/reference.
- `account_boundaries` reused as the shared total-accounting combinator; the
  rung-transition layer owns the activation gate (operator lean — confirm against
  rung-transition code).
Forbidden: activate, apply, config writes (beyond allowlist/spec/test surfaces),
rollback mutation, promotion, enforcement flip, LA changes, ops/NQ profile,
loop-FSM codification, broad plan-decomposition implementation.
Validator rule: §11.3 + the independence refinement — future-rung-debt and
false-positive classifications require independence-admissible witnesses (floor
rises with continuation authorized); scope-expanding remedy halts by identity.
DoD: free-form target refused; eligibility checker proves activation impossible
with open/free-form debt; `P2_GENESIS_TARGET_ALLOWLIST_001` discharged by
witnessed mechanism; no activation/apply/config-mutation path exists.
> Before the system may activate deltas, it must prove activation is gated by
> debts it cannot self-clear.

### P3.1 — admitted scoped activation + rollback (3.0.0); RecompositionReceipt stays shadow

**Reshaped 2026-06-13: rung activation is a FOUR-OFFICE transaction, not a gate**
(`docs/cross-tool/rung-activation-four-office-note.md`): Governor/Wicket
admissibility · Standing entitlement (act-standing) · LA spend (exactly-once) ·
NQ custody. AG co-hosts them in bootstrap but must factor along eligibility /
spend / custody seams. `activate(delta, baseline_id, checkpoint_id)` — required
args, hash-validated, no defaults; human approval receipt; seam checkpoint
`pre_delta_activation`; gate-time expiry; typed receipt-additive rollback. Wire
exactly one pipeline: self-governance profile, lowest-stakes tunable. Only after
P3.0's gates are proven real.
Hard rules (from the four-office note): **`DebtClearVerdict` must never write
`active_rung`** (debt-clear is eligibility; activation is a separate LA spend);
**recompute the live claim set + debt disposition AT the activation gate**
(deferral is cargo, re-verification is standing — carried digests don't authorize);
**override = custodial deposit + Δh pressure, never reversal**; LA must not parse
the eligibility ref.
DoD: lifecycle drill (propose→approve→activate→trip→rollback→hashes==baseline);
expiry auto-revert; path/deletion/lineage fences; **the note's 8 negative tests**
(stale disposition, carried-digest staleness, assert-standing floor, no
DebtClearVerdict→active_rung write, override-not-reversal, override-still-spends,
repeated-override-pressure, LA-doesn't-parse).
**HIGH checkpoints at entry: crosswalk divergence #1 (validator quorum on
activation?) AND the four-office factoring (Standing/LA co-resident but not fused).**

### P3.2 — enforcing RecompositionReceipt, hard-gated on P3.1 drill passing

Flip the orchestrator-seam shadow to enforcing (`refused_laundering` blocks
recomposition/publication); laundering drill via drill_runner pattern.
DoD: blocked recomposition with walkable receipt chain; one enforcement surface this band.

### P4 — promotion & expiry maturation (3.0.x)

Evidence-count promotion → new ControlBaseline via supersession ceremony; bisectable
lineage; ops/NQ profile admitted only after a self-governance promotion receipt exists
(constructor-refused otherwise); convergence_tuning disposition (adapter vs coexist) with
migration receipts; loop-AUDIT shadow projection candidate.
**HIGH checkpoints: replay/holdout as promotion criterion (divergence #2);
convergence_tuning disposition; SELF_GOVERNANCE_SPEC amendment per ratified crosswalk.**

## 4. Cadence map

HIGH (operator present): P0 review (crosswalk disposition + divergences); P2 exit
(allowlist review); P3a entry (quorum question); P4 (promotion criteria, spec amendment,
convergence_tuning disposition). Everything else AUTOPILOT under the loop protocol with
campaign exit-tickets per micro-step. codex-exec adversarial pass at the two vocabulary
checkpoints (P0 doctrine doc, P2 allowlist) — refute-not-confirm, file:line grounded.

## 5. Cut list (explicitly out of MVP — refuse smuggling)

- Auto-apply / any unattended delta activation.
- Validator-quorum machinery (unless P3a HIGH checkpoint rules it in).
- Loop-protocol FSM codification (P4 candidate at most).
- ops/NQ profile before a self-governance promotion receipt exists.
- receipt_kernel invariant #14; any constitutional kernel surface change.
- LA typed fidelity pools; Wall 2; any LA/wicket/standing contract change.
- Governor-as-a-service, auth boundary, multi-tenant (spec carve-outs stay spec-side).
- LOCKED-as-routing-regime, RecoveryPlanReceipt, dual U/C ledger (brain-dump items remain
  brain-dump items).
- Intent-fidelity *enforcement* before recomposition shadow-assessment has real-run data.

## 6. Sizing / sequence

Minimal: P0 → P1.1 → P1.2 (receipt shape proven in shadow; stop-safe point).
Compelling: through P3a+P3b on the self-governance profile.
Canonical order: P0 → P1.1 → P1.2 → P1.3 → P1.4 → P2.1 → P2.2 → P2.3 → P3a → P3b → P4.
Every boundary above is a safe halt; nothing in P1–P2 changes behavior, so launch-runway
work (W1) interleaves freely.

## 7. Slice tracker

| Slice | Status | Notes |
|---|---|---|
| P0 docs/spec | **RATIFIED 2026-06-12** | crosswalk disposition = parent-track + 5 carve-outs (validator quorum, replay/holdout, significance gating, RecoveryPlanReceipt, auth/dual-ledger); spec stays byte-unmodified through P0–P1 |
| P1.1 RecompositionReceipt + account_boundaries | **IN PROGRESS 2026-06-12** | first safe code slice; authored on Opus 4.8 (Fable 5 export-controlled mid-campaign — substrate swap witnessed in `working/forcing-case-degraded-model-availability.md`) |
| P1.2 shadow emission at orchestrator | OPEN | blocked by P1.1 |
| P1.3 annealing_observer | OPEN | |
| P1.4 fidelity declaration | OPEN | |
| P2.1 AnnealingDelta | OPEN | blocked by P1.3; dependency-direction rule binds |
| P2.2 ControlBaseline registry | OPEN | red-line fence test mandatory |
| P2.3 CLI read paths | OPEN | no apply verb |
| P3a activation + rollback | OPEN | 3.0.0 line; HIGH checkpoint at entry |
| P3b enforcing recomposition | OPEN | hard-gated on P3a drill |
| P4 promotion / ops profile / disposition | OPEN | HIGH checkpoints |

## 8. Model-suitability note

P0 (this filing): Fable — conceptual seams, vocabulary control. P1.1–P1.4, P2.x: mid-tier
executable slices once specs are ratified (packet discipline per
[[feedback_model_tier_routing]]); escalate only at the HIGH checkpoints.
