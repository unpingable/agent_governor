# rrp — receipt-indexed admissibility gate prototype

**Status:** DRAFT (registered 2026-07-13 by AG naturalization ruling; census
defect D12 — the repo had an identity artifact with zero commits until
`rrp 9a0abf6` banked the tree). Ratifiable after first drift check against a
pushed remote.

## Contract snapshot (as of 9a0abf6, 2026-07-13)

- **Is:** strict-canonical-JSON admissibility gate — loads artifacts, derives
  claims from admissible evidence, emits canonical gate decisions. Python
  reference checker + Rust parity checker (`rust/admissibility-rs`),
  corpus-backed, prototype ABI v1 (`ABI_STATUS.md` authoritative).
- **Is not:** policy engine, sandbox, runtime, theorem prover, effect executor
  (README); bridge custody sits behind an explicit placeholder verifier seam
  **unsafe for production custody**.
- **Private**, no stability claim.
- **Lean seam:** `lean/docs/RRP-LEAN-CROSSWALK.md` (2026-07-09) pins intended
  checker semantics from the Lean side; proves nothing about this code.

## Drift

n/a — first registration; no prior AG snapshot to drift from.

## Gaps / slices

### R-RRP-1 — remote + push
tier: mechanical · executor: any · prereq: []
- purpose: durable provenance + shareable identity (zero-commit repos have neither)
- state: tree banked locally (`9a0abf6`); **private** remote creation + push
  held for operator push window
- stop condition: remote exists, initial import pushed, this file updated

### R-RRP-2 — obligation-ledger legibility
tier: conceptual · executor: fable/operator · prereq: [R-RRP-1]
- purpose: what does the corpus still owe the ABI, and where is that recorded?
  (release-checklist.md and dependency-audit.md exist in-repo; decide which
  surface is the canonical backlog and register it in the portfolio stub)
- stop condition: `roadmap-rrp` stub's canonical_source names one surface
