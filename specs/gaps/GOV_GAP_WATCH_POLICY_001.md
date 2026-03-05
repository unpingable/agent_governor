# GOV_GAP_WATCH_POLICY_001: Watch Policy Abstraction

**Status**: v3 candidate (not scheduled)
**Category**: Naming / refactor
**Priority**: Low — substrate exists, abstraction does not

## Problem

Governor has monitoring semantics scattered across multiple modules:

- `watch.py` — file system watching with automatic security scanning
- `claude_hooks.py` — pre/post tool hooks for Claude CLI
- `scope.py` — grant usage logging, escalation tracking
- `daemon.py` — heartbeat semantics, session lifecycle
- `continuity.py` — anchor checking on file changes
- `regime.py` / `boil.py` — operational health thresholds

Each module implements "watch this, escalate if weird" independently. The
primitives work. But there is no unified `WatchPolicy` type that declares:

- **What** is being watched (scope, cadence, subject)
- **Why** (policy reference, invariant linkage)
- **Escalation** (what happens when the watch fires)
- **Lifecycle** (when watching starts/stops, expiry, renewal)

This is not a missing capability. It is a missing center of gravity.

## Risk of Inaction

Scattered monitoring semantics tend to rot. When "watching" lives in six
places with six conventions, the system works but the idea does not cohere.
Incoherent monitoring is how you get false confidence with better vocabulary.

## What a v3 Fix Looks Like

A `WatchPolicy` frozen dataclass that unifies the declaration:

```python
@dataclass(frozen=True)
class WatchPolicy:
    policy_id: str
    subject: str          # What to watch (file path, scope, signal name, etc.)
    cadence: str          # "on_change", "periodic:60s", "on_gate_fire", etc.
    escalation: str       # "receipt", "block", "alert", etc.
    expires: str | None   # ISO 8601 or None for permanent
    rationale: str        # Why this watch exists
    linked_invariant: str | None  # Invariant spec ID, if any
```

Existing modules would declare their watches via this type rather than
implementing ad-hoc monitoring loops. The type is declarative — it does
not replace the monitoring implementations, it names them.

## Relationship to Labelwatch/Driftwatch

Governor's job is to **produce** watch declarations and receipts.
Labelwatch/Driftwatch's job is to **consume** them as receipt-native
observers for long-running coherence monitoring.

The watch policy abstraction lives in governor (producer-side declaration).
The operational supervisor that acts on degraded watches lives in the
consumer tools (Labelwatch/Driftwatch).

## Origin

Identified during v2.7.0 review of agentic monitoring requirements.
Core insight: "the gap is in the consumers, not the producer" — but
the producer should still declare its watches coherently.
