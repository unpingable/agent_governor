# Roadmap — continuity × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/continuity` (HEAD `64599e1`, 2026-06-28) · Docket: governor-atlas
constellation case · Reliance doctrine: Continuity governs what can be RELIED on;
Maude governs what must be DECIDED; Spine governs what can be FOUND.

## 1. Contract snapshot — what AG assumes today

- AG (as a Claude session) uses continuity via MCP (`memory_get_case`,
  `memory_query_latest`, observe/commit/revoke lifecycle) — session-tooling use,
  not a governor runtime dependency.
- Lifecycle contract: observed → committed → revoked, each transition receipted
  and hash-chained; `rely_ok` queryable per memory.
- Declaration export v0 shipped ("the envelope, never the verdict");
  ProjectionReceipt candidate ("read is witnessed claim, not stored truth" —
  same shape as AG's GOV_GAP_QUERIED_RECEIPT_SUBSTRATE_001).

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| AG GateReceipts carry no linkage to continuity memories; operator decisions recorded in continuity are invisible to `governor why` chains | gate_receipt.py has no continuity parent field; continuity cross-reliance doctrine (commit `96429a3`) expects consumers to link | MED |
| Reliance queries (`rely_ok`) unwired from any AG runtime seam | no AG call sites | MED (candidate, needs forcing case) |

## 3. Named gaps (non-binding)

- `CONTINUITY_GATE_RECEIPT_LINKAGE` — decisions that flow through continuity's
  lifecycle should be citable as parents from AG receipts (one-way: AG cites
  continuity; continuity never becomes an authority source for gates).
- `CONTINUITY_RELIANCE_AT_STANDING_SEAM` — "is this grant still safe to rely on"
  as a query BEFORE spend; distinct from Standing's own refusals (advisory
  pre-check, never a substitute for the Standing verdict).

## 4. Slices

### R-CONT-1 — GateReceipt↔continuity linkage design
tier: conceptual · executor: fable · prereq: [reconciliation A8 (report may reshape this)]
- purpose: decide the citation shape — how an AG receipt names a continuity memory/receipt as parent without importing continuity state into gate verdicts.
- files: design note working/continuity-receipt-linkage.md.
- tests: n/a (design); emits the mechanical work order.
- refusal mode: none added — linkage is testimony, not gating. **Memory continuity is not doctrine admission** (campaign constraint, verbatim): a linked memory NEVER upgrades a verdict.
- receipt shape: design-note commit.
- stop condition: any design where a memory's presence changes a gate outcome — STOP, that is the forbidden collapse.

### R-CONT-2 — linkage execution
tier: mechanical · executor: codex · prereq: [R-CONT-1]
- purpose: execute R-CONT-1's work order (expected: optional `continuity_refs` testimony field on receipt metadata, populated at named call sites).
- files: enumerated by R-CONT-1.
- tests: `python3 -m pytest tests/test_gate_receipt.py -v` exit 0; receipt-id determinism unchanged (content-address unaffected by metadata — verified by existing hash pins).
- refusal mode: n/a (testimony field).
- receipt shape: commit citing R-CONT-1.
- stop condition: if linkage would enter `evidence_hash`/receipt identity — obstruction note (that changes receipt semantics; re-tier).

## 5. Do-not-build

- No continuity-as-authority: `rely_ok` may advise, never authorize; no gate
  reads memory state to decide a verdict.
- No AG writes into continuity's lifecycle on the governor runtime path (session
  tooling and governor runtime stay distinct custody surfaces).
- No ProjectionReceipt adoption until continuity ratifies its candidate (watch,
  cite, don't fork).

## 6. Operator questions

None open. R-CONT-1 gated on the reconciliation report only.
