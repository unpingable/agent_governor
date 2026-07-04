# Roadmap — lean × AG (the catch-up lane)

**Status:** RATIFIED (2026-07-02, A8 — snapshot + drift confirmed by executed evidence slices)
Repo: `~/git/lean` (HEAD `762967c`, 2026-07-02 — the repo moved TWICE today:
**v7.0.0 TAGGED same day** (`b9860aa`, artifact authority profiles +
next-surfaces register; was CANDIDATE at the morning sweep), post-v7 threads
already open (pathverdict tier-1 extraction in scratch)) · Crosswalk:
`~/git/lean/docs/AG-AUDIT-CHECKLIST.md`

## 1. Contract snapshot — what AG assumes today

- AG cites Lean per the citation-tier rule (memory: feedback_lean_citation_tiers):
  **[1.0] stable / [annex] compiled / [scratch] recon; annex cannot ratify.**
- Known live citation: `src/governor/proof_seam.py` → refusal class →
  `Freshness.expired_not_fresh` ([1.0], class-not-instance framing;
  NO_KERNEL_THEOREM gaps marked, not borrowed).
- Kernel-axis sweep obligation (memory: lean_admissibility_kernel): sweep the
  lean repo when doing kernel-axis work.

## 2. Observed drift (dated) — AG's scoping is ~5 releases behind

| what's new | tier | AG impact |
|---|---|---|
| Admissibility Kernels 1.0 (8 public modules: Authority, StateTransition, Derivation, Execution, Corrective, Freshness, SurfaceAuthorization, WitnessInvariance; + the aggregator — count corrected per R-LEAN-2) | [1.0] | citable NOW; A3b adjudicates against AG schemas |
| Witnessed Derivation Calculus v1.4.0 (Mathlib-free; Lift, non-manufacture, ResourceCheckerExec) | [1.0-separate] | citable for bridge composition |
| BoundedCalculi v3.0.0 (9 bounded judgments; `checkpoint_mints_nothing`, ticket-accepted≠executed…) | ANNEX | cite exact theorem only; cannot ratify |
| v4/v5/v6 custody campaign — priced contraction, "normalization cannot forge payment", **v6 finite-support checker (typed CheckResult naming the offender; `firstDeficient_decides_check`; decidable screens)** | SCRATCH (v6.0.0 tagged) | pilot-only (slice B6); uncitable as authority until promoted |
| **v7.0.0 SHIPPED (tagged 2026-07-02 evening)**: artifact authority profiles; lane split — Lean owns profile laws, **AG owns JSON schemas / wire formats / runtime gates**; WLP = envelope only | **RELEASED** (verify per-theorem tier before citing) | **B7 lane assignment is LIVE** — AG's schema work proceeds against the released profile laws, no longer marked non-binding-until-ratification |
| `docs/AG-AUDIT-CHECKLIST.md` — 8 items mapping theorem families to AG schema audits; `CLAIM-REGISTER.md` — what Lean DISPROVED | docs | A3a/A3b anchor |

## 3. Named gaps (non-binding)

- `freshness-granularity` (filed 2026-07-03) — AG keeps a single refusal kind
  `standing_before_spendability_not_bounded` with a typed `freshness_subcase`
  receipt field mirroring Lean Freshness {expired, not_yet_valid,
  divergence_excessive, incoherent_interval}; the two-clock gate produces only
  `expired`. AG's public refusal vocab stays coarser than Lean Freshness [1.0]
  by design until a routing consumer forces a split. Alignment gap, not a
  blocker. (`.governor/backlog/freshness-granularity.json`; pickup INVENTORY.)
- `LEAN_CITATION_TIER_AUDIT` — **DISCHARGED 2026-07-04 by R-LEAN-2** (table in
  reconciliation INVENTORY §3): zero down-tier cites used as authority;
  proof_seam.py line-accurate at HEAD `84d6d24`; residual debt is cosmetic
  (retired "Calculus" name + missing tier markers in dated gap specs,
  fix-on-touch).

## 4. Slices

### R-LEAN-1 — checklist adjudication
= reconciliation slices **A3a/A3b** (campaign NEXT.md) — not duplicated here.

### R-LEAN-2 — citation-tier audit of AG  **(EXECUTED 2026-07-04 — agent sweep + Fable adjudication at lean HEAD `84d6d24` (the `ff4aadf` pin below was stale); table → reconciliation INVENTORY §3; zero authority-laundering cites; 1 live-doc fix + fix-on-touch flags)**
tier: mechanical · executor: codex · prereq: [A3a]
- purpose: every AG reference to a Lean module/theorem carries the correct current tier marker; moved/renamed targets flagged.
- files: grep `Lean\|lean/LeanProofs\|expired_not_fresh\|CorrectiveBoundary` across docs/ src/ specs/; table → reconciliation INVENTORY §3.
- tests: every row = AG file:line · cited name · found-in-lean-at (path) · tier; zero unresolved cites without a flag.
- refusal mode: SCRATCH/CANDIDATE cites used as authority → finding (the "annex can't ratify" rule extended down-tier).
- receipt shape: one commit citing lean HEAD `ff4aadf`.
- stop condition: a cite whose target genuinely vanished — flag `target_gone`, don't guess successors.

### R-LEAN-3 — v7 schema lane
= pickup slice **B7** (campaign NEXT.md) — not duplicated here.

## 5. Do-not-build

- No SCRATCH or CANDIDATE citation as authority anywhere in AG (pilot and design
  lanes only); ANNEX cites name the exact theorem.
- No Lean theorem name treated as an implementation requirement without stating
  the operational invariant (packet stop-line, verbatim).
- No AG-side re-proof or shadow formalization — cite, don't fork.

## 6. Operator questions

- Q-B7 (v7 CANDIDATE exposure) — in the pickup capsule.
