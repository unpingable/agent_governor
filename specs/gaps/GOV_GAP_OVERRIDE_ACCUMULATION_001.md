# Gap Spec: Override Accumulation Signal (Δr→Δw Detection)

**Status:** proposed (build candidate — smallest bounded slice)
**Affects:** scars, overrides, regime detection
**Date:** 2026-03-31
**Origin:** cybernetic failure taxonomy — Δr→Δw pipeline (recursion captures authority)

## Problem

Governor has scars (Δh — constraint stiffening after failure) and overrides with expiry (Δw prevention — sunset clauses on temporary authority). But it doesn't track the *frequency* of overrides per scope. If an operator grants 5 overrides for the same region across 3 sessions, that's either:

- A bad anchor that needs revision (the rule is wrong)
- Authority drift (the exception is becoming policy)

Either way, the pattern should be visible and receipted.

## Proposed

Record override events by scope. Track rolling counts. Expose a simple pressure signal.

### Data

Per override event, record:
- `scope` (region/file pattern)
- `anchor_id` (which anchor was overridden)
- `reason_class` (scar fingerprint or override reason)
- `session_id`
- `operator_id` (principal)
- `created_at`
- `expires_at`
- `expired_without_renewal` (bool, backfilled)

### Aggregation

Rolling window (configurable, default 7 days):
- `override_count` per (scope, anchor_id)
- `unique_sessions` per (scope, anchor_id)
- `unique_operators` per (scope, anchor_id)
- `renewal_rate` — fraction of overrides that were renewed before expiry

### Signal

`exception_pressure: low | medium | high`

Thresholds (configurable):
- `low`: ≤2 overrides in window
- `medium`: 3-5 overrides, or same scope overridden in ≥3 sessions
- `high`: >5 overrides, or renewal_rate > 0.5 (more than half renewed)

High pressure → surface in `governor status`, `governor doctor`, and regime signals. Not auto-action — just visibility.

### Receipt

Each pressure evaluation emits a gate receipt:
- `gate: "exception_pressure"`
- `verdict: "observe"`
- `scope`, `anchor_id`, `pressure_level`, `override_count`, `window_days`

### CLI

```bash
governor override pressure              # Show current pressure by scope
governor override pressure --json       # Machine-readable
governor override history --scope "src/**"  # Override events for a scope
```

## Non-Goals

- Not auto-revoking overrides (that's operator authority)
- Not auto-revising anchors (that's a decision, not a fact)
- Not a grand theory of authority drift — just counting and surfacing

## Dependencies

- Existing `governor override` system
- Existing `scars.py` (scar fingerprints)
- `gate_receipt.py` for receipt emission
