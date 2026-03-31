# Gap Spec: Decision-Time Context Closure

**Status:** proposed (v3)
**Affects:** gate receipts, fact ledger, regime detection
**Date:** 2026-03-31

## Problem

When a gate receipt says ALLOW or DENY, it captures the *decision* — verdict, evidence hash, policy hash. But it doesn't capture the *world image* that informed it: which facts were live, which decisions were active, what the regime was, what anchors existed.

This means a receipt proves *what happened* but not *what the governor believed at the time*. If a fact decayed between the decision and the audit, the receipt can't reconstruct why the decision was admissible when it was made.

## Proposed

A **context closure** — a content-addressed snapshot of the governor state that was live at the moment of a gate evaluation. Not a full copy of everything, but a hash-referenced summary:

- Active facts (hash of fact index)
- Active decisions (hash of decision index)
- Active anchors (hash of anchor registry)
- Current regime (regime name + signal values)
- Active overrides (hash of override set)
- Scope state (active run scope)

The closure hash gets included in the gate receipt as `context_hash`. The full closure is stored once (content-addressed, deduplicated across receipts that share the same state). Receipts reference it by hash.

This makes receipts fully reconstructable: given the receipt + the context closure + the policy, you can replay the decision and verify it was admissible under the state that existed at the time.

## Why This Matters

- **Audit:** "Was this ALLOW correct?" becomes answerable from artifacts alone
- **Drift detection:** context closure hashes that change between turns without explicit mutations are silent drift
- **Replay:** counterfactual analysis ("would this have been denied under yesterday's anchors?") becomes mechanical

## Why Not Now

This touches the receipt model, the fact ledger, the anchor registry, and the gate evaluation path. It's a cross-cutting change that needs careful design to avoid performance regression (hashing everything on every gate call). The right approach is probably lazy hashing with invalidation — recompute only when state actually changes.

## Sketch

```python
@dataclass(frozen=True)
class ContextClosure:
    facts_hash: str
    decisions_hash: str
    anchors_hash: str
    regime: str
    regime_signals_hash: str
    overrides_hash: str
    scope_hash: str
    closure_hash: str  # H(all of the above)
```

Gate evaluation becomes:
1. Compute or retrieve current context closure (cached, invalidated on mutation)
2. Evaluate gate as normal
3. Include `closure_hash` in receipt
4. Store closure if not already stored

## Dependencies

- `gate_receipt.py` (receipt fields)
- `ledgers.py` / `ledgers_v2.py` (fact/decision hashing)
- `continuity.py` (anchor registry hashing)
- `regime.py` (regime state)
- `overrides.py` (override set)
- `scope.py` (run scope)
