# Roadmap — porter × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/porter` (design-only: schema + README ratified, **no commits on
main**) · Docket: no governor-atlas case yet (correct — no edge exists)

## 1. Contract snapshot — what AG assumes today

Nothing wired. Porter's *designed* contract (its DESIGN.md):

- Neutral courier for ephemeral substrates: runs declared commands on temp
  VMs/containers/hosts, returns honest receipts — transcript, true exit code
  (`steps[].exit_code_observed: bool` — refuses rather than fabricates), artifact
  hashes.
- `porter.record.v0` schema with `fact_mismatches` (declared vs observed
  substrate facts); recipe hook returns `{kind, transport, declared, observed,
  fact_mismatches}`.
- Carries **no domain verdict** (no success/passed/admissible) — caller judges.

The exit-code honesty aligns with AG's verifier-wrapper doctrine
(`governor verify-run`, masked-exit refusal) — same scar, same rule.

## 2. Observed drift (dated)

None possible — nothing to drift. (Operator note 2026-07-02: porter's prominence
in outside planning was a recency artifact; this roadmap exists for completeness,
weighted accordingly.)

## 3. Named gaps (non-binding)

- `PORTER_CLIENT_CANDIDATE` — if AG ever needs substrate-run evidence (e.g.
  capable-VM playbook records beyond the current H-series harness), a thin
  injected-callable client in the standing_client.py idiom is the shape. Named,
  not built.

## 4. Slices

### R-PORTER-1 — thin client (candidate, doubly blocked)
tier: conceptual · executor: fable · prereq: [porter main has working code AND a named AG evidence-collection forcing case]
- purpose: decide whether AG consumes porter.record.v0 for substrate-run evidence, and at which seam.
- files: design note first.
- tests: n/a (design).
- refusal mode: porter records with `exit_code_observed: false` must map to AG's no-verified-result posture (never a claimed pass).
- receipt shape: design-note commit citing porter DESIGN.md §3.
- stop condition: both gates named above; do not open on one.

## 5. Do-not-build

- No AG client while porter has no commits (a ratified schema is not a runnable
  contract).
- No H-series harness replacement by porter speculation — the cage/bwrap work is
  shipped and scoped; porter would be additive evidence, not a substitute.

## 6. Operator questions

None open.
