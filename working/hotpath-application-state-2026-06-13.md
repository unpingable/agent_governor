# Hot-path application state — 2026-06-13

Current-campaign application of the durable doctrine in
`docs/cross-tool/hotpath-and-granularity-note.md`. This file is the "what's true
today / what the next slice must preserve" surface; the doctrine note is the
campaign-independent rule set.

## State

- **Doctrine in place:** decomposition-capability-closure, symbolic-instrument-
  witness, and hotpath-and-granularity notes + gaps are committed
  (`docs/cross-tool/`, `specs/gaps/`).
- **Conversion-path audit clean:** `working/audit-conversion-paths-2026-06-13.md` —
  0 BLOCKER, 0 LIVE_RISK over the 11 semantic conversions. The nine non-doctrine
  crimes are fenced; the two open are the decomposition-closure gap.
- **Substrate hot paths are dormant, not wired:** the sovereign receipt chain runs
  serial under WIP-1 (no concurrency pressure yet); the microkernel/IPC and
  federated Standing are FUTURE — their hot-path cost is named, not incurred.
- **Receipt-shape slice (decomposition_completeness.py): LANDED at 77044f2.** The
  coverage-axis structured-evidence symmetry was applied (operator ruling A): every
  path to `complete` carries a structured evidence object with a non-empty
  provenance ref — bare z3/lean strings dead. Codex pass-3 clean.

## What the next wiring slice MUST preserve

1. **Spine vs island split.** No high-volume telemetry / worker-observation /
   bulk-witness receipts on the sovereign spine. Meaningful transitions on the
   spine; noise on islands.
2. **Action-granularity governance.** No per-token / per-helper / per-syscall /
   per-telemetry-row governance checks. Fire at the consequence boundary.
3. **Named owning office** for every semantic conversion (no free-standing
   conversion).
4. **Discharge is consequence-bearing.** A claim becoming non-blocking goes through
   an authorized discharge decision + receipt, not "a test passed."
5. **Standing checks at gate granularity**, never cached as authority (lease = a
   routing hint only).
6. **IPC minimizes round-trips** — one meaningful action = one bundled transaction
   envelope, not a synchronous office-to-office chain.

## Acceptance / TODO markers (NOT built here)

- no high-volume telemetry on the sovereign spine (island it);
- no per-token / per-helper-function governance checks;
- no semantic conversion without a named owning office;
- claim discharge / waiver / deferral treated as consequence-bearing (the
  negative-test family is in the doctrine note);
- Standing checks occur at gate granularity, not cached as authority;
- IPC design minimizes round-trips per meaningful action (transaction envelope).

## Pickup rule (binds future slices)

> Every future wiring slice states whether it touches the spine, an island, IPC,
> a Standing-gate, or a semantic-conversion hot path — and names the office that
> owns any conversion. Hot-path awareness is admission, not footer.

## Next intended seam

The decomposition-completeness **receipt-shape** slice is LANDED (77044f2;
hot-path class **none**). The **P3.4 prep-before-ingest** blocker is now also LANDED
(`prep_ingest.py`) — the first slice whose declared hot-path class is real:
**semantic-conversion / gate-admission**, and it pays the first installment on the
**discharge** hot path (an operator-gated, fail-closed clearance socket). Pre-P4 order:
`0 ✓ · 1 ✓ · 2 ✓ · 3 P4 plan · 4 start P4`. Next is the **P4 promotion/expiry plan
update** (constitutional memory), then P4. (The shadow-stub rung — emitting
`ag_alone()` on a real decomposition check so the evidence sockets await real producers —
remains a candidate wiring slice, sequenced after P4 planning unless a forcing case
pulls it earlier; it too must declare its hot-path class.)
