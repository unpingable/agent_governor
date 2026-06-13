# GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001

## Title

Discharge is a hot path — binding the discharge→activation edge so a claim becoming
non-blocking is an authorized, receipted decision, not a flag flip.

## Status

**Candidate — names a future-rung obligation, authorizes no build.** Filed
2026-06-13 (alignment sweep + operator). Surfaced by
`docs/cross-tool/hotpath-and-granularity-note.md` §Discharge (the under-weighted
hot path) and `GOV_GAP_RUNG_DEBT_COLLECTION_001` Rule 6 (collector binding). The
*authority basis* for discharge is unwired; this gap reserves the handle so it is
not lost going into P3.4 / P4.

## Why now

> **A claim becoming non-blocking is consequence-bearing.**

Activation gates are obvious; discharge feels like cleanup, and cleanup is where
systems hide state changes wearing sweatpants. The moment a `NonDischargeClaim`
goes open → discharged/deferred/waived, the system changes what future gates may
do. The audit (`working/audit-conversion-paths-2026-06-13.md`) found NO live
conversion crime here — `DebtLedger.discharge()` (`debt_ledger.py:99`) only flips a
stored flag and is not called by activation, and it explicitly "does not adjudicate
WHO may discharge". That absence of a live bug is exactly why the *authority basis*
must be installed before discharge becomes load-bearing (P3.4's
`indecomposable_gate` claim, P4 promotion).

## What exists

- `DebtLedger.record()` / `discharge()` / `open_claims()` (P3.0b) — flag flip, no
  authority adjudication.
- `RungDebt` enforces `authorized_collector != target_rung` at construction
  (the no-self-collection invariant is named in the *type*, not yet at the
  discharge call).

## What needs building (future)

The discharge→activation edge as an authorized, receipted transition:

```
evidence produced
  -> a check/adjudication MAY support discharge
  -> AUTHORIZED discharge decision (standing/operator basis; collector ≠ target rung)
  -> discharge receipt (provenance retained)
  -> future gates recompute eligibility from LIVE debt state
```

## Acceptance / negative-test family (NOT implemented here)

- a test pass alone cannot discharge a claim;
- doc presence alone cannot discharge a claim;
- builder/validator agreement cannot discharge without assert-standing / operator basis;
- a waiver does not DELETE the claim (custodial deposit, not erasure);
- a deferral does not DISCHARGE the claim;
- a discharged claim retains provenance and is auditable as a prior blocker;
- discharge by `authorized_collector == target_rung` is refused (no self-collection).

## Non-goals

- NOT a general discharge-subsystem redesign.
- NOT verifier/standing wiring for the adjudication step (cite, don't run).
- NOT building this inside P3.4 (P3.4 only needs operator/authorized discharge for
  the single `indecomposable_gate` claim, if a discharge seam already exists).

## Doctrine line

> Named is not collected; carried is not collected either. Don't only guard the
> door — guard whoever removes things from the "do not open" list.
