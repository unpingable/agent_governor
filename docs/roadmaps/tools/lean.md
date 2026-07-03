# Roadmap — lean × AG (the catch-up lane)

**Status:** DRAFT (2026-07-02; ratifies after reconciliation slice A8)
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
| Admissibility Kernels 1.0 (9 modules: Authority, StateTransition, Derivation, Execution, Corrective, Freshness, SurfaceAuthorization, WitnessInvariance + aggregator) | [1.0] | citable NOW; A3b adjudicates against AG schemas |
| Witnessed Derivation Calculus v1.4.0 (Mathlib-free; Lift, non-manufacture, ResourceCheckerExec) | [1.0-separate] | citable for bridge composition |
| BoundedCalculi v3.0.0 (9 bounded judgments; `checkpoint_mints_nothing`, ticket-accepted≠executed…) | ANNEX | cite exact theorem only; cannot ratify |
| v4/v5/v6 custody campaign — priced contraction, "normalization cannot forge payment", **v6 finite-support checker (typed CheckResult naming the offender; `firstDeficient_decides_check`; decidable screens)** | SCRATCH (v6.0.0 tagged) | pilot-only (slice B6); uncitable as authority until promoted |
| **v7.0.0 SHIPPED (tagged 2026-07-02 evening)**: artifact authority profiles; lane split — Lean owns profile laws, **AG owns JSON schemas / wire formats / runtime gates**; WLP = envelope only | **RELEASED** (verify per-theorem tier before citing) | **B7 lane assignment is LIVE** — AG's schema work proceeds against the released profile laws, no longer marked non-binding-until-ratification |
| `docs/AG-AUDIT-CHECKLIST.md` — 8 items mapping theorem families to AG schema audits; `CLAIM-REGISTER.md` — what Lean DISPROVED | docs | A3a/A3b anchor |

## 3. Named gaps (non-binding)

- `LEAN_CITATION_TIER_AUDIT` — AG docs citing lean predate the tier explosion;
  each citation needs its tier marker verified (a [1.0] cite made when 1.0 was
  the whole repo may now accidentally reference moved/renamed annex content).

## 4. Slices

### R-LEAN-1 — checklist adjudication
= reconciliation slices **A3a/A3b** (campaign NEXT.md) — not duplicated here.

### R-LEAN-2 — citation-tier audit of AG
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
