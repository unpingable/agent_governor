# Roadmap — claimc × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/claimc` (HEAD `db776cc`, 2026-06-28; Slices 1–3 complete) · Docket:
governor-atlas constellation case · ⚠ sibling session may be active in claimc —
coordinate before any cross-repo slice

## 1. Contract snapshot — what AG assumes today

- Consumer-pull posture: claimc is complete for its dumb pipeline
  (compile → settle → score); AG pulls when it has a claim needing settlement
  shape, claimc does not push.
- Compiler contract: `REJECTED` (no settlement apparatus declared, e.g.
  E004_MISSING_SETTLEMENT) vs `PASSED` (settleable — **not** true).
- Position: Verifier proves against declared checks; claimc checks structural
  settleability; Wicket authorizes movement. Three tools, three questions.

## 2. Observed drift (dated)

None. Slices 1–3 shipped as scoped; surfaces frozen for the slice set.

## 3. Named gaps (non-binding)

- `CLAIMC_PLAYBOOK_CLAIM_COMPILE` — playbook ActorOutput carries
  `claimed_status` / `claimed_test_results` / `raw_authority_claims` (S7
  normalizer). Whether those claims should be claimc-compiled (settlement
  apparatus declared or REJECTED) before review-packet assembly is a live
  question with no forcing case yet.

## 4. Slices

### R-CLAIMC-1 — playbook claim compilation (candidate, blocked)
tier: conceptual · executor: fable · prereq: [forcing case: first synthetic-conveyor review packet where an unsettleable claim caused wasted review or a laundering attempt]
- purpose: decide whether/where claimc compilation gates the S7→review seam.
- files: design note; no code until designed.
- tests: n/a (design).
- refusal mode: would surface claimc REJECTED as an existing playbook refusal — vocabulary chosen in design, from closed sets.
- receipt shape: design-note commit citing claimc docs/boundary.md.
- stop condition: gated on the forcing case; watch conveyor runs, don't pre-build.

## 5. Do-not-build

- No wiring claimc into any gate until an actual unsettleable-claim incident
  (consumer-pull holds).
- No treating claimc PASSED as truth anywhere (its own invariant).

## 6. Operator questions

None open.
