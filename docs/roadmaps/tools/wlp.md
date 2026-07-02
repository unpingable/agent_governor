# Roadmap — wlp × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/wlp` (HEAD `081b1bb`, 2026-06-03; v0.2, Rust) · Docket:
governor-atlas constellation case · (name collision RESOLVED 2026-07-02: the
parked spec renamed `~/git/backburner/witness-ledger-protocol`, LINEAGE.md
in-repo — CONSOLIDATION.md #6)

## 1. Contract snapshot — what AG assumes today

- AG does **not** consume wlp directly today; AG composes standing/wicket/LA
  natively. wlp is the wire/envelope layer other constellation members use
  (nightshift refuses WLP warranty on freshness-unsettled packets).
- Constitution AG relies on doctrinally: "every WLP artifact must carry the terms
  under which it stops binding"; domain-semantically neutral,
  admissibility-semantically opinionated; temporal envelope mandatory fail-closed;
  revocation mutates PRESENT standing, never historical validity.
- Lean v7 lane split (candidate): WLP survives as envelope/causal-parent layer,
  **never semantics** — reserved theorems (`wlp_valid_does_not_imply_profile_authority`
  etc.). wlp's own SPEC already aligns.

## 2. Observed drift (dated)

None material. Healthiest protocol surface in the sweep: active cadence, gap
candidates filed with evidence, v7-doctrine-aligned (verified against
`~/git/lean` v7 gap spec §6, 2026-07-02).

## 3. Named gaps (non-binding — wlp's own, recorded for the docket)

- `WLP_RECEIVER_GATE_CANDIDATE` · `WLP_STORAGE_TRANSPORT_BOUNDARY` ·
  `WLP_STANDING_BOUNDARY_CROSSREF` · `WLP_RECEIVER_ACCEPTANCE_NOT_REPLAYABLE_GAP`
  — all candidates in wlp; AG watches, does not adopt.

## 4. Slices

### R-WLP-1 — HandlingReceipt revocation seam (candidate, blocked)
tier: conceptual · executor: fable · prereq: [forcing case: a wicket admission consumed by AG is later revoked and the revocation must surface retroactively across workflow stages]
- purpose: decide whether AG's admission chain consumes wlp HandlingReceipt revocation outcomes, or keeps native revocation checks per-seam.
- files: design note first; no code.
- tests: n/a (design).
- refusal mode: would surface revocation as an existing typed refusal at the consuming seam — vocabulary decided in the design slice.
- receipt shape: design-note commit citing wlp SPEC v0.2 §revocation.
- stop condition: gated entirely on the forcing case; do not open speculatively.

## 5. Do-not-build

- No AG adoption of wlp envelopes without the revocation forcing case — AG's
  native composition is not broken.
- WLP never carries semantics into AG (v7 lane split, verbatim): envelope and
  causal parentage only.
## 6. Operator questions

None open. (The two-wlp name collision was resolved 2026-07-02 by
operator-authorized rename of the parked fossil; see CONSOLIDATION.md #6.)
