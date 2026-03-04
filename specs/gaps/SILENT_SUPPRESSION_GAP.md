# Gap: Silent Suppression — Ledger Heartbeat & Starvation Detection

**Branch:** v2.x
**Status:** shipped (v2.5.0 — `signals/silent_suppression.py`; retained as design rationale per V2_4A_SPINE.md §8)
**Depends on:** evidence_gate.py, receipt_bridge.py, telemetry.py
**Build phase:** v2.1 (instrumentation spine — build FIRST)
**Blocks:** CAPTURE_SELF_DIAGNOSTIC_GAP (hard — can't diagnose capture if governor is unplugged)

## The Problem

The governor can be silenced without being captured. If the evidence gate stops being called — because the integration hook is disabled, the wrapper is bypassed, or the agent switches to a code path that doesn't invoke governance — no contradiction can be detected, no σ-rate computed, no capture indicator fires. Everything looks healthy because nothing is being measured.

This is the "dead thermometer" failure: the instrument reads normal because it's unplugged.

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| Receipt emission | evidence_gate.py, gate_receipt.py | Every check emits a receipt or logs `receipt_suppressed` |
| Telemetry events | telemetry.py | Events logged per check |
| Correlator K-vector Throughput | correlator_telemetry.py | Turn volume tracked |
| Preflight checks | preflight.py | 8 checks at session start |

**The gap**: all these assume the evidence gate is being called. None detect the absence of calls.

## What Needs Building

### 1. Ledger Heartbeat

A periodic check that the evidence gate has been called within the expected interval:

```python
@dataclass
class HeartbeatConfig:
    expected_interval_seconds: float = 300.0  # expect a check every 5 minutes during active session
    grace_period_seconds: float = 60.0        # tolerance for timing jitter
    stale_after_missed: int = 3               # 3 missed heartbeats = stale

@dataclass
class HeartbeatStatus:
    last_check_timestamp: datetime | None
    seconds_since_last: float
    expected_interval: float
    missed_count: int
    is_stale: bool
    is_session_active: bool  # don't alarm during idle
```

### 2. Starvation Detection

Starvation = the governor is active (session running, model generating) but the evidence gate hasn't been called. This is distinct from idle (no session, no generation).

Detection requires correlating two signals:
- **Model activity**: tokens being generated (from chat_bridge or daemon)
- **Gate activity**: evidence_gate.check() calls (from receipt store timestamps)

If model activity > 0 and gate activity = 0 for `stale_after_missed` intervals → starvation alert.

### 3. Alerting

```bash
governor gate heartbeat              # show heartbeat status
governor gate heartbeat --json       # machine-readable
```

Starvation appears as:
- Telemetry event: `GATE_STARVATION` with severity ERROR
- Dashboard: red banner "Governor gate not receiving checks"
- Correlator: Throughput dimension drops to 0 → DEGRADED_CAPACITY flag

### 4. Integration with Preflight

Add a 9th preflight check: "was the evidence gate called in the last session?" This catches the case where hooks were disabled between sessions.

### 5. Per-Sensor Emission Contracts

Starvation isn't only "no calls." It's also "calls happened, but one channel didn't emit." Each registered signal source declares expected emission counts:

```python
@dataclass
class EmissionContract:
    source: str                           # e.g. "evidence_gate", "drift_detector"
    expected_emissions_per_window: int    # minimum expected per observation window
    zero_is_valid: bool                   # True only for legitimately-silent sensors
```

If `not zero_is_valid` and actual emissions = 0 → `SENSOR_SILENT` telemetry event. This is distinct from `GATE_STARVATION` (no calls at all). Here the gate was called but one sensor didn't fire — partial suppression looks like "everything is calm" when it's "one instrument is dead."

See also: GAP_INVARIANTS.md §3 (Emission Contracts).

## Why This Matters

Capture detection (correlator, self-diagnostic) assumes a continuous stream of observations. If the stream stops, all indicators read "normal" because there's no data to contradict anything. The heartbeat is the meta-check: "am I still measuring?"

## Build Estimate

~80 lines (heartbeat + starvation logic) + ~20 lines CLI + ~50 tests.

## Acceptance Criteria

1. Heartbeat tracks last evidence_gate.check() timestamp
2. Starvation detected when model is active but gate is silent
3. `governor gate heartbeat` shows status
4. Telemetry event emitted on starvation
5. Preflight check #9: "gate active in last session"
6. No false positives during idle (no active session)
