# Roadmap — nq × AG

**Status:** DRAFT (2026-07-02; ratifies after reconciliation slice A8)
Repo: `~/git/nq-root/nq` (HEAD `c1dd7d3`, 2026-07-02) · Docket: governor-atlas
constellation case (NQ edge) · Consumer seam: `src/governor/nightshift_adapter.py`
+ `src/governor/drill_runner.py` (FindingSnapshot consumers)

## 1. Contract snapshot — what AG assumes today

- Export contract `nq.finding_snapshot.v1` (NQ `crates/nq-db/src/export.rs`):
  `admissibility {state, reason, ancestor_key, declaration_id}` is load-bearing
  (AG must refuse suppressed findings); `basis {state, source_id, witness_id,
  last_basis_gen, state_at}`; `regime`/`diagnosis` optional and ignorable.
- Invariant inherited: a finding snapshot is **evidence, not authorization** —
  consumers re-check before acting.
- MIN_SCHEMA_FOR_EXPORT = 57 pinned in the adapter path.
- NQ is origin of the claim-custody spine's first leg
  (`docs/architecture/claim-custody-spine.md`).

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Evidence retirement is now an explicit operator act; AG has no retirement trigger wiring | NQ `source_retirement.rs`, `EVIDENCE_RETIREMENT_GAP.md` | HIGH |
| BASIS_STALE_CONTRACT v0 ratified 2026-07-02: `basis_state ∈ {unknown, stale, retired}`, never fabricated; AG adapters don't treat `stale` as a live condition | NQ `docs/working/decisions/BASIS_STALE_CONTRACT.md`, commits `3249fe1`/`22cbd3f` | HIGH |
| Clause-7: authority timestamp is `witness_collected_at` (≠ ingest `collected_at`); AG should use `basis.state_at` as the admissibility clock | clause-7 audit complete (ZFS + SMART eligible) | MED |
| Clause-4: stale transition writes regardless of silence finding; dedup gates notification, not state | NQ commit `c1dd7d3` | LOW (informational for AG) |
| Service/log provenance named schema debt (not AG's to fix) | NQ commit `c5f9559` | INFO |

## 3. Named gaps (non-binding)

- `NQ_RETIREMENT_TRIGGER_UNWIRED` — AG has no operator-facing path that calls
  NQ retirement; retirement decisions made in AG-space die in prose.
- `NQ_STALE_BASIS_LIVE_CONDITION` — AG consumption treats basis.state as
  pass/fail-ish; `stale` needs distinct handling (neither fresh nor retired).
- `NQ_WITNESS_CLOCK_ADMISSIBILITY` — AG freshness checks against NQ findings
  must bind to the witness clock, not ingest time (composes with AG's
  clock_witness discipline: a gap needs compatible bases).

## 4. Slices

### R-NQ-1 — stale-basis consumption design
tier: conceptual · executor: fable · prereq: [reconciliation A4]
- purpose: decide what AG does when `basis.state == "stale"` (distinct from fresh and retired) at each consuming seam.
- files: design note working/nq-stale-basis-consumption.md; nightshift_adapter.py + drill_runner.py identified read points.
- tests: n/a (design); enumerates R-NQ-2's work order.
- refusal mode: names the refusal (likely existing `admission_gap_accounted` or a documented pass-through with basis recorded — decided here, not in the mechanical slice).
- receipt shape: design-note commit citing BASIS_STALE_CONTRACT.md.
- stop condition: if handling requires NEW refusal vocabulary → operator question, not invention.

### R-NQ-2 — witness-clock discipline (work order emitted by R-NQ-1)
tier: mechanical · executor: codex · prereq: [R-NQ-1]
- purpose: every AG freshness comparison against NQ findings uses `basis.state_at` / `witness_collected_at`, never ingest time.
- files: enumerated by R-NQ-1 (expected: nightshift_adapter.py, drill_runner.py).
- tests: `python3 -m pytest tests/test_nightshift_adapter.py -v` exit 0 + new pin test asserting the clock field read.
- refusal mode: exercises existing clock_witness incompatible-basis refusals where applicable.
- receipt shape: commit citing clause-7 audit.
- stop condition: a comparison site mixes clock bases with no compatible witness — obstruction note (that is a clock_witness gap, not a swap).

### R-NQ-3 — retirement trigger wiring (authority sandwich)
tier: conceptual → mechanical → review · executor: fable/codex/codex-exec · prereq: [R-NQ-1; forcing case: first real retirement decision made in AG-space]
- purpose: operator-facing AG path that calls NQ `retire_source()` and records the receipt chain.
- files: TBD by design slice (candidate: ops CLI surface).
- tests: TBD by design slice; NQ side already pins retire/unretire semantics.
- refusal mode: unretire returns to `unknown` (NQ re-proves live) — AG must not testify liveness.
- receipt shape: AG receipt citing NQ retirement receipt as parent.
- stop condition: gated on forcing case; do not build speculatively.

## 5. Do-not-build

- No fabricated `basis_state` anywhere (NQ's own invariant; AG must not paper it).
- No cross-boundary `basis_source_id` inference (NQ clause-4 explicitly forbids).
- No AG-side liveness testimony (unretire → `unknown` is NQ's re-proof loop).
- No consuming `regime`/`diagnosis` until a slice needs them (optional stays optional).

## 6. Operator questions

None open. R-NQ-3 waits on its named forcing case, not on a ruling.
