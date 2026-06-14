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
12. **Cross-cutting precondition (2026-06-13, GOV_GAP_OFFICE_COLLAPSE_AND_RECEIPT_SOVEREIGNTY_001):**
    further decompose/recompose work may continue ONLY if it preserves the conversion
    refusals — receipt sovereignty over Governor semantics; no Governor-as-kernel path; no
    `DebtClearVerdict → active_rung` write; no `rely_ok`/`verifier.allowed`/builder-agreement
    → authority; no local Standing stub as real grant; no controller transition without
    above-Governor (kernel-invariant) ratification. Verifier = hook not pipeline; Continuity
    = rely-time freshness (computed not remembered). Every cross-level transition names the
    office that owns the conversion, or it is forbidden.
13. **Decomposition-completeness precondition (2026-06-13, GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001):**
    recomposition soundness is conditional on decomposition completeness, and that condition
    is NOT discharged while boundaries are *declared*. Further decompose/recompose work
    (incl. **P4**) may continue ONLY if it preserves the enumeration/coverage split:
    AG-alone may claim `enumeration: complete` but only `coverage: best_effort`
    (`verifier: absent`); **no AG-alone receipt may emit `coverage: complete` or
    `decomposition: complete`** without solver/theorem/operator evidence. `account_boundaries`
    proves admitted-boundary disposition, NEVER boundary-set closure (the omitted-boundary
    blind spot is pinned: `tests/test_decomposition_closure_limit.py`). Closure requires
    kernel-granted capabilities, not plan-declared surfaces. Doc:
    `docs/cross-tool/decomposition-capability-closure-note.md`. SEQUENCE: document → audit →
    receipt-shape fields + guards + negative tests → shadow stubs → real wiring. **The knife:
    you cannot audit the absence of an omitted boundary; you can only make omission unexecutable.**
14. **Hot-path declaration (2026-06-13, `docs/cross-tool/hotpath-and-granularity-note.md`):**
    every future wiring slice MUST state whether it touches the **spine** (sovereign serial
    chain), an **island** (sharded high-volume), **IPC** (kernel message path), a
    **Standing-gate** (uncacheable re-check), or a **semantic-conversion** hot path — and name
    the office that owns any conversion. Governance fires at *action* granularity, not
    implementation granularity (gate the spend, not the syscall). No telemetry on the spine.
    **Discharge / waiver / deferral is consequence-bearing** (a claim becoming non-blocking
    changes what future gates may do) — it goes through an authorized decision + receipt, never
    "a test passed." Hot-path awareness is admission, not footer.

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
Mode (federation without hostage): `ActivationMode ∈ {constellation,
standalone_degraded}`. Constellation requires external Standing/LA/NQ receipts
when configured present; standalone_degraded uses local substitutes (bootstrap
standing, local exactly-once spend ledger, local custody), MUST mark the receipt
`standalone_degraded`, and MUST NOT claim LA/Standing/NQ-backed grade. Same
"run poor, don't fake rich" invariant as doctrine §5.
DoD: lifecycle drill (propose→approve→activate→trip→rollback→hashes==baseline);
expiry auto-revert; path/deletion/lineage fences; **the note's 8 negative tests**
(stale disposition, carried-digest staleness, assert-standing floor, no
DebtClearVerdict→active_rung write, override-not-reversal, override-still-spends,
repeated-override-pressure, LA-doesn't-parse); + degraded activation marks the
receipt and emits no constellation-grade claim.
**HIGH checkpoints at entry: crosswalk divergence #1 (validator quorum on
activation?) AND the four-office factoring (Standing/LA co-resident but not fused).**

**LANDED 2026-06-13** (`src/governor/activation.py`, `tests/test_activation.py`):
the four-office transaction for the one tunable `decomposition_size/max_slices`
(rung `self_governance`). Office 1 reads the live claim set from the authoritative
`DebtLedger.open_claims(P31_RUNG)` at the gate (recomputes the digest, refuses on
mismatch — caller-supplied claims can't activate); offices 2–4 = act-standing /
exactly-once `flock`-guarded local spend / durable custody. Writes honor only
custodied receipts AND are fenced to the one admitted P3.1 surface (forge+put+apply
cannot write off-surface — *bootstrap custody may be forgeable; admitted effect
surface must still be fenced*). Rollback derives the write authoritatively from the
custodied activation, restores absence topology (delete, not null), never erases
the activation record, inherits its mode. Two Codex validation passes (pass-1 fixed,
pass-2 off-surface leak fixed under operator ruling A); fuse-classified residue
(in-process forge-custody, constellation standing) is future custody/microkernel
work, recorded in `working/parked-p31-activation.md`. **Hard stop here — P3.2 not
started.**

**P3.1 LIFECYCLE DRILL LANDED 2026-06-13** (`tests/test_activation_drill.py`): the
single end-to-end walk that gates P3.2. Proves the effect-bearing rung can
*activate, account, and retreat without widening authority* — propose → eligibility
from the live DebtLedger (open debt blocks, discharge unblocks) → activate the one
tunable → observe the effect (8→4) AND the four-office receipts ON DISK (activation
receipt file, exactly-once spend ledger entry) → replay refuses (tunable unchanged)
→ rollback referencing the persisted activation receipt → observe restoration (→8,
activation record not erased) → forged/off-surface activation + rollback + ghost
(uncustodied) rollback all still refused, real tunable untouched. Test-only (no src
change, no new authority surface) → targeted verify-run pass (exit-witnessed), no
full suite warranted, no Codex pass. *Before enforcing recomposition, prove the
effect-bearing rung can activate, account, and retreat without widening authority.*
**P3.2 (enforcing RecompositionReceipt) remains gated; hard stop after the drill.**

### P3.2 — enforcing RecompositionReceipt, hard-gated on P3.1 drill passing

Flip the orchestrator-seam shadow to enforcing (`refused_laundering` blocks
recomposition/publication); laundering drill via drill_runner pattern.
DoD: blocked recomposition with walkable receipt chain; one enforcement surface this band.

**LANDED 2026-06-13** (`src/governor/cooked_context_orchestrator.py`): opt-in
`run(..., recomposition_plan=...)` enforcement; `enforce_recomposition` (effective
receipt accounting the declared plan against the chain's own traversal);
`RecompositionRefusal` outcome (carries receipt + accounting, NOT the laundered
success — train stops, cargo not forwarded); `SEAM_RECOMPOSITION`; shadow
refactored into shared `_chain_traversal`/`_chain_recomposition_meta` (P1.2
byte-identical). 9 enforcement tests incl. the laundering drill (all visible
slices pass + one dropped admitted boundary → blocks, zero added client calls),
honest-plan-admits, no-plan-byte-identical, can't-be-spent (type wall),
honest-refusal-not-relabelled, gate-is-pure, mutating-sink-cannot-suppress-or-corrupt.
Full suite green (verify-run, exit-witnessed) twice.

Two-stroke ledger: Codex pass-1 → block decided PRE-emission from the immutable
verdict (sink can't suppress). Codex pass-2 → operator ruling A: **the refusal must
be decided before emission AND reported from the same pre-emission snapshot** — the
`RecompositionRefusal` + its `accounting` are now built before the sink runs, so a
hostile `object.__setattr__` sink can corrupt neither the block nor the RETURNED
diagnosis. §11.3 classification (operator-ratified):
- *current-rung invariant*: `refused_laundering` blocks downstream execution. ✓
- *current-rung hygiene*: returned refusal diagnosis snapshots pre-sink accounting. ✓
- *substrate limit (NOT chased)*: hostile in-process `object.__setattr__` can
  vandalise the shared receipt object's own fields — same bootstrap-custody limit
  as P3.1: *in-process object forgery is not fenced; the admitted effect/control
  surface is*. The diagnosis we RETURN no longer reads from that object post-sink.

**Rust-extraction seam flagged for later (operator, not acted):** the invariant
cluster now stable enough to know what NOT to port — `account_boundaries` /
RecompositionVerdict + refusal snapshot / AnnealingDelta admission / activation
eligibility + exactly-once + receipt-backed apply-rollback. Doctrine: *Rust is
justified for the invariant-bearing recomposition/activation kernel, not for the
control plane* ("Bash for crimes, Python for bureaucracy, Rust for the part where
lying should be structurally expensive"). Composes with [[rust_kernel_port_ruling]]
(decision-kernel-only, post-launch; golden receipt corpus is the contract). NOT a
P-phase; revisit at/after the first self-build recompose. **Hard stop after P3.2.**

### Pre-P4 closure — plan-intake / decomposition gap (still pre-P4)

The work after P3.2 is *front-door hardening before promotion*, not more annealing.
"Recomposition depends on decomposition" — so we close the decomposition gap before
P4 can ask whether a trial activation should become baseline.

**P3.3 decomposition-completeness receipt shape — LANDED 77044f2.** Schema truth
before behavior truth: AG can no longer lie about decomposition completeness. Every
path to `complete` requires a structured evidence object; AG-alone emits
`enumeration=declared` / `coverage=best_effort`. Doc/gap:
`decomposition-capability-closure-note.md` + the closure gap (AC1/AC2 landed). Also
landed pre-P4: symbolic-instrument-witness + hotpath-and-granularity doctrine notes,
and the conversion-path audit (0 blocker / 0 live-risk).

**P3.4 prep-before-ingest indecomposable-gate blocker — LANDED** (`prep_ingest.py`).
The smallest runtime behavior that USES the receipt shape without pretending the
sibling tools exist. Hot-path class: **semantic-conversion / gate-admission** (ground
rule 14). One claim kind `indecomposable_gate` (namespaced by `plan_id`+`gate_id` —
identity is custody, not decoration); `prep_detect` emits it; `assert_ingest_admissible`
refuses while open; the planner cannot self-discharge (re-running prep with
`decomposable=True` does not clear); the ONLY clearance is `operator_discharge` requiring
a structured `OperatorDischargeEvidence` (non-empty ref, anti-forgery like P3.3) — no
generic flag-flip, `DebtLedger.discharge()` untouched; the reader is **fail-closed** (a
tampered `discharged`-without-ref record stays blocking, repairable only by genuine
operator evidence); discharged claims remain auditable (`is_cleared` is the semantic
predicate, not the raw flag). Three-cycle two-stroke (Codex: plan_id collision →
gate_id collision → pass). A *clearance socket, not a discharge subsystem* — the deeper
collector-binding/provenance hardening stays `GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001`.
P3.4 does NOT decide decomposability (operator/verifier judgment, future). *Before P4
can promote anything, AG has a front door that refuses plans whose gates are not yet
decomposable.*

### P4 — promotion & expiry maturation (3.0.x) — NOT STARTED

**Plan landed (docs-only) 2026-06-13: `working/P4-promotion-plan-2026-06-13.md`** —
the exact target (the one P3.1 tunable), the seven questions (evidence /
supersession receipt / expiry / rollback / bootstrap limits), the refusal cases, and
the hot-path class (semantic-conversion trial→baseline + spine supersession). P4
implementation is NOT started; entry gated on the three HIGH checkpoints.

This is **constitutional memory** (a trial shape surviving → becoming baseline), not
activation. Minimal P4: observe the one activated tunable over `evidence_count ≥ N` →
if in-bounds, promote trial → new ControlBaseline via the validator supersession
ceremony; prove old/new baseline diffable by content hashes; prove expiry/rollback
still works; refuse promotion if evidence insufficient.

**P4 preconditions (all now met except the last two):** P3 lifecycle drill exists ✓;
P3.2 enforcement green ✓; DebtLedger present ✓; P3.1 activation receipts exist ✓;
promotion target is exactly the one P3.1 tunable; supersession ceremony chosen; baseline
diff/revert path proven. **Plus the pre-P4 gate: P3.4 (plan-intake admission) fenced.**

Still forbidden in P4: multi-delta interaction; ops/NQ profile (until self-governance
survives one promotion cycle — constructor-refused otherwise); generic activation;
self-modifying kernel invariants; receipt-kernel ratification-invariant change; Rust port.
**HIGH checkpoints: ~~replay/holdout as promotion criterion (divergence #2)~~ RESOLVED
2026-06-13 (dual gate: live survival + replay/holdout falsification, never folded; replay
scoped as falsification gate; applies to the FIRST promotion, no poisoned bootstrap);
convergence_tuning disposition RESOLVED 2026-06-13 (operator fiat → COEXIST with one-way
external bridge; `annealing.py` never imports `convergence_tuning`; PromotionReceipt/
ControlBaseline mint from annealing/promotion custody NOT `TuningProposal`/`TuningApply`;
bridge = `tuning_proposal_bridge.py`, admissible-only, custody-complete; guardrail:
TuningApply≠PromotionReceipt, TuningProposal≠ControlBaseline —
`working/checkpoint-2-convergence-tuning-disposition-2026-06-13.md`); SELF_GOVERNANCE_SPEC
amendment per ratified crosswalk (OPEN, LAST — open tomorrow only if P4.0b needs spec
text now).**

**P4.0 split by substrate dependency:** P4.0a = substrate-agnostic `PromotionEligible`
predicate + refusal-first tests (`promotion_gate.py`; gate's only verb is refuse → safe
before checkpoint 2; in progress 2026-06-13). P4.0b = `ControlBaseline` mint + supersession
ceremony (gated on checkpoint 2). See `working/P4-promotion-plan-2026-06-13.md` Status.

## 4. Cadence map

HIGH (operator present): P0 review (crosswalk disposition + divergences); P2 exit
(allowlist review); P3.1 entry (quorum question); P4 (promotion criteria, spec amendment,
convergence_tuning disposition). Everything else AUTOPILOT under the loop protocol with
campaign exit-tickets per micro-step. codex-exec adversarial pass at the two vocabulary
checkpoints (P0 doctrine doc, P2 allowlist) — refute-not-confirm, file:line grounded.

## 5. Cut list (explicitly out of MVP — refuse smuggling)

- Auto-apply / any unattended delta activation.
- Validator-quorum machinery (unless P3.1 HIGH checkpoint rules it in).
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
Compelling: through P3.1+P3.2 on the self-governance profile (DONE).
Canonical order: P0 → P1.1 → P1.2 → P1.3 → P1.4 → P2.1 → P2.2 → P2.3 → P3.0 → P3.0b
→ P3.1 → P3.1-drill → P3.2 → [pre-P4 closure] → P3.3 → **P3.4** → P4.
Every boundary above is a safe halt; nothing in P1–P2 changes behavior, so launch-runway
work (W1) interleaves freely.

## 7. Slice tracker

> Reconciled 2026-06-13: old `P3a`→**P3.1**, old `P3b`→**P3.2**; the
> decomposition-completeness work is **P3.3**, prep-before-ingest is **P3.4**.
> P4 (promotion/expiry) is unchanged and NOT started — *still pre-P4*.

| Slice | Status | Notes |
|---|---|---|
| P0 docs/spec | **RATIFIED 2026-06-12** | crosswalk = parent-track + 5 carve-outs; spec byte-unmodified through P0–P1 |
| P1.1–P1.4 observation rung | **LANDED** | RecompositionReceipt + account_boundaries, shadow emission, annealing_observer, fidelity declaration |
| P2.1–P2.3 candidate-delta rung | **LANDED** | AnnealingDelta custody, ControlBaseline registry, read-only CLI (no apply verb) |
| P3.0 activation preflight | **LANDED** | `activation_preflight.py`; discharged P2_GENESIS_TARGET_ALLOWLIST_001 |
| P3.0b DebtLedger | **LANDED** | `debt_ledger.py` — authoritative live claim source; flock-guarded |
| P3.1 scoped four-office activation + rollback | **LANDED 5c88dfc** | one tunable; effect-surface fenced; reads live claims at the gate |
| P3.1 lifecycle drill | **LANDED aa5e00b** | activate → account → replay-refuse → rollback → restore; receipts on disk |
| P3.2 enforcing RecompositionReceipt | **LANDED 52e797f** | `refused_laundering` blocks; recomposition's only verb is refuse |
| *Pre-P4 closure (doctrine + audit)* | **LANDED** | decomposition-closure + symbolic-witness + hotpath notes (2428072/dd7a9a0/ec99cbf); conversion-path audit 0/0 (a4bc70f) |
| P3.3 decomposition-completeness receipt shape | **LANDED 77044f2** | every path to `complete` needs a structured evidence object; AG-alone = declared/best_effort |
| P3.4 prep-before-ingest indecomposable-gate blocker | **LANDED** | `prep_ingest.py`; semantic-conversion/gate-admission hot path; one claim kind + one operator-gated discharge socket; plan_id+gate_id namespaced; fail-closed reader |
| P4 promotion / expiry maturation | **NOT STARTED** | preconditions in §3 P4 block; constitutional memory, not more annealing |

## 8. Model-suitability note

P0 (this filing): Fable — conceptual seams, vocabulary control. P1.1–P1.4, P2.x: mid-tier
executable slices once specs are ratified (packet discipline per
[[feedback_model_tier_routing]]); escalate only at the HIGH checkpoints.
