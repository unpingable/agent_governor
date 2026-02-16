# Scar Fingerprint — Action-Level Novelty Gate

**Status:** implemented
**Priority:** high (integrity bypass vector)
**Effort:** 1 session
**Depends on:** none

## Problem

Scars currently match on `region` only. When a failure occurs at
`src/auth.py` with failure_kind `timeout`, the resulting scar blocks
ALL retries in that region — but it also means:

1. An agent that fails with error type X, gets scarred, then retries
   with action type Y circumvents the scar's evidence accumulation.
   The scar retightens on ANY re-failure, but the evidence/annealing
   doesn't distinguish *what kind of failure* is recurring.

2. A scar created by `timeout` failures can anneal via stability
   evidence that's actually about `validation` success — the wrong
   evidence class relaxing the wrong threat.

3. There's no way to have a hard scar on `auth_bypass` in a region
   while allowing soft-scarred `timeout` retries in the same region.

This is an integrity bypass vector: the scar system is a circuit
breaker, but circuit breakers that don't distinguish fault types
provide weaker guarantees than they appear to.

## Fix

Add `failure_kind` and `action_type` to the scar fingerprint.
Different failure modes in the same region create **separate scars**,
each with their own stiffness and evidence lifecycle.

### New Fields

```python
@dataclass
class Scar:
    # Existing
    region: str              # Where it failed (file path, module, scope)
    stiffness: float         # Constraint severity [0.05, 1.0]

    # New
    failure_kind: str = ""   # What went wrong (timeout, validation, auth, etc.)
    action_type: str = ""    # What was attempted (write, read, execute, etc.)
```

### Fingerprint Semantics

- `region` alone is the **coarse** fingerprint (backward compat)
- `region + failure_kind + action_type` is the **fine** fingerprint
- When `failure_kind`/`action_type` are empty, match on region only
- `check_admissible()` returns the MOST RESTRICTIVE scar across all
  matching scars for a region

### Matching Rules

| Caller provides | Matches |
|----------------|---------|
| region only | All scars in that region (most restrictive wins) |
| region + failure_kind | Exact match on region+kind, OR region-only scars |
| region + failure_kind + action_type | Exact triple match, OR broader matches |

The rule: **broader scars apply to narrower queries, not vice versa.**
A region-level hard scar blocks everything in that region. A
failure_kind-specific scar only blocks that specific failure mode.

### API Changes

```python
# record_failure() gains two optional params
def record_failure(
    self, region, ...,
    failure_kind: str = "",     # NEW
    action_type: str = "",      # NEW
) -> FailureEvent:

# check_admissible() gains two optional params
def check_admissible(
    self, region,
    failure_kind: str = "",     # NEW
    action_type: str = "",      # NEW
) -> tuple[bool, float, Scar | None]:

# record_stability_evidence() gains two optional params
def record_stability_evidence(
    self, region,
    failure_kind: str = "",     # NEW
    action_type: str = "",      # NEW
) -> None:
```

### Backward Compatibility

All new parameters default to `""`. Existing callers that only pass
`region` get identical behavior: region-only matching, region-only
scars. No API breakage.

## Verification

1. Same region, different failure_kind → separate scars
2. Region-only check_admissible returns most restrictive scar
3. Retighten only fires for matching fingerprint
4. Evidence only anneals matching fingerprint
5. Hard scar on one failure_kind doesn't block unrelated failure_kind
6. Region-level scar (empty failure_kind) blocks ALL in that region
7. Serialization roundtrip preserves new fields
8. Existing tests pass unchanged (backward compat)

## Files

| File | Change |
|------|--------|
| `src/governor/scars.py` | Add failure_kind, action_type to Scar + FailureEvent; update matching |
| `tests/test_scars.py` | Add fingerprint-specific tests |
