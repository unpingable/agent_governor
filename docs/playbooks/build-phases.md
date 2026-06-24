# Governed Playbooks — Build Phases

> **Status:** plan. No phase past 0 is started. **Phase the work by dangerous seam and
> effect boundary, NOT by object model.** Building the inert parts first (Spec, storage,
> serialization) feels like progress and defers every real bug — the seams and the
> custody — to the end, under the most schedule pressure, which is exactly when redshift
> waves them through.

The shape: **each phase makes exactly one dangerous thing real for the first time** —
first certification, first live seam, first irreversible effect, first interruption,
first embedded joint, first composition, first delegation. One new way to be wrong per
phase, each gated on the prior, each with its invariant written *before* it is built.
The inert object model materializes only when a seam demands it.

---

## Phase 0 — Invariant ledger (paper; ratified before code)

Deliverable: [invariant-ledger.md](./invariant-ledger.md), ratified and hash-pinned.
The only phase with no executable, and it gates all the rest. This is the **test oracle**
for Phases 3–6, whose characteristic failures are silent — you must predict them to
catch them.

Write order (each is the seam the organ map most wants you to take on faith):

1. **W-001** Wicket proposal intake
2. **SL-001** Standing → LA reservation
3. **LE-001** LA → Executor consumption
4. **WF-001** NQ fresh-witness consumption  *(third-most dangerous; left unwritten, a
   true-but-stale observation walks a pipeline off a cliff with every receipt valid)*
5. the rest: WS-001, OE-001, EC-001, CF-001, MC-001, SP-001/002, NS-001, RV-001

If something is genuinely missing, it surfaces here as a seam with **no invariant** —
concretely, by name. If nothing surfaces, the itch was the seam-finder idling, and the
ledger is what lets you *see* that rather than hope it.

---

## Phase 1 — Boundary outcome algebra (paper first, then Lean)

**The footing.** The three ConvergenceFence hostile contracts (no-op, repeated firing,
non-convergence) against a *single* `BoundaryContract`. Paper until they close; **then**
the Lean owner formalizes — not playbook-claude inline (fusing proof and implementation
destroys the independence that makes the proof worth anything).

> **HARD GATE: if the contracts don't close, STOP. The partition is wrong and nothing
> below is real. No Rust until this is green.**

The judgment call that is genuinely yours: **how thin the first `BoundaryContract` is.**
Too thin and it typechecks the hostile cases by being vacuous (proves nothing); too rich
and it never closes. The minimal contract that is *non-trivial and closes* is the actual
intellectual work of this whole build.

---

## Phase 2 — Spec → Certified (one kind, no effects)

Minimal object model starts. PlaybookSpec IR + parser + composition checker emitting a
`certified_kind` receipt — **reactor-kind first** (simpler algebra); pipeline-kind is
Phase 2b once reactor certification is solid. No execution, no effects.

Deliverable: an inert artifact can be certified or refused, and the `certified_kind` tag
is **earned from the checker, never written on the artifact**. This is where
`claimed_kind ≠ certified_kind` is proven in code.

(Reactor-first vs pipeline-first is a you-call: if your near-term use is build/CI-shaped,
pipeline-first may pay rent sooner at the cost of harder early proofs.)

---

## Phase 3 — RunRequest/RunPlan + Wicket → Standing → LA seam (observe-only)

First *live* phase, deliberately defanged: only `observe_pure` steps (which forces
typing the read surface, per OE-001). RunPlan binds inputs **with typed input
constraints** (a certified playbook is only certified over its input domain — this phase
builds constrained binding). RunRequest flows RunRequest → Wicket → Standing → LA.

**The point of this phase is the Standing→LA seam under the Phase-0 invariant** — does
`admitted` cross to `reserve` as a *verified receipt* or a *trusted claim*. The seam is
the experiment; effects are observe-only because the seam, not the effect, is under test.

---

## Phase 4 — One irreversible effect (full custody, chaos interruption)

Exactly one `emit-external` or `mutate-local` step, end to end. First time the system can
break the world → first time custody is real: spend consumed at LA, witness attached,
RunInstance recorded.

The actual test is the **chaos-injection custody test**: kill the executor *between
dispatch and witness*, assert it enters `interrupted_unknown_effect` and **not** silent
no-effect (EC-001). Chaos injection here is not a robustness test — it is a *custody*
test. One effect, fully governed, fully interruption-tested, before there are ever two.

---

## Phase 5 — Embedded ConvergenceFence (live)

The Phase-1 paper joint, now executed: a pipeline containing the reactor stage, the
terminal-outcome-as-typed-input crossing for real. Not built until the *contract* closed
(Phase 1) **and** single-kind execution works (Phases 2–4). Paper meets running code at
the load-bearing joint.

---

## Phase 6 — Composition / sub-playbooks / dependency closure

Sub-playbooks with lock semantics: no `latest`, digest-pinned, closure-resolved, Standing
evaluating the **whole closure**, no transitive standing, no hidden effect steps inside
imports, dependency diff triggers recertification. Checked against Phase-0's composition
invariants, **not eyeballed** — pre-state the seam invariants *before* combining, because
composition's failures (two individually-valid receipts, one corrupted shared state) do
not announce themselves. This is also where transitive-promotion and the waiver seam get
their real test.

---

## Phase 7 — Nightshift scheduling (delegated future agency)

Last, because it multiplies every prior risk by time and unattendedness. "A schedule is
not standing" (NS-001) is enforced here: every firing produces a *candidate*, re-resolves
standing live, never inherits. Scheduling a system whose custody you don't yet trust is
how you get the September incident from a March approval.

---

## Standing warnings

- **Do not** build registry / parser / scheduling / executor before Phase 0/1 closes.
- Passing a golden-path implementation does **not** prove the bridge (that's fidelity,
  not soundness — redshift with a green test suite).
- "Combine and see what happens" is insufficient: composition and custody failures are
  silent; seam invariants must be **written before** composition tests.
- Split failure-injection in two — **certification-time** injection (bad spec → must be
  refused pre-run; a *runtime* failure means the gate is porous) is a different test from
  **runtime** injection (chaos → must enter correct custody state).
- Multiple models agreeing the design is sound is a reason for *suspicion*, not comfort
  (common-mode synthesis failure).

---

## Ownership (anti-laundering, applied to the dev process)

| Role               | Owns                                                      |
| ------------------ | -------------------------------------------------------- |
| playbook-claude    | builds / proposes implementation                         |
| Lean owner         | proves bridge / boundary algebra (Phase 1)               |
| cartographer-claude| reviews constellation fit (admits-or-refuses)            |
| chat register      | adversarial taste; **no state-evaluation authority**     |

The thing that certifies coherence must not be the thing producing the artifact being
certified. playbook-claude proposes; cartographer-claude reviews work it didn't write.
Don't fuse Lean and implementation. Otherwise: Claude certified Claude's Claude — a
papier-mâché auditor.
