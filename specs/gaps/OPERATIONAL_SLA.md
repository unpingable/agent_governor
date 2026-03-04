# Operational SLA

Availability, latency, and temporal coherence constraints for the governor
as a control plane.

status: partially shipped (2.x: timing fragment on gate receipts shipped; 3.x SLA contracts: open)

---

## Problem

The governor started as a library with receipts. It is becoming a control
plane that sits on the decision path. This changes the failure mode:

- Library: if the governor is slow, the agent is slow. Annoying.
- Control plane: if the governor is slow, the agent is *blocked*. Outage.
- Control plane: if the governor is unavailable, the agent either stops
  (fail-closed) or proceeds without governance (fail-open). Both are bad,
  but they're bad in different ways.

Today there is no explicit contract for how long a gate decision may take,
how stale a policy may be, or what happens when the governor can't answer
in time. These are all implicit, which means every caller invents their own
timeout and every failure is ad hoc.

The missing concept is **operational SLA**: explicit, measurable, per-path
contracts on latency, availability, and freshness. Not because we want
on-call, but because we want the governor to detect its own degradation and
emit structured evidence of it.

---

## Two Paths, Two SLAs

The governor has two distinct performance domains:

### Decision path

The synchronous gate: can this action proceed?

- Must be fast (p99 budget measured in milliseconds)
- Sits on the critical path of every governed action
- Fail mode is existential: too slow = operationally intolerable
- Current implementation: in-process function call (sub-ms), but daemon
  RPC adds transport + serialization + contention

Contract shape:
```
decision_budget_ms: 50     # p99 target for gate verdict
decision_timeout_ms: 200   # hard cutoff, fail-open if exceeded
```

### Evidence path

The asynchronous trail: persist receipts, index signals, emit telemetry.

- Can be slower than the decision path
- Must be *accountable*: if evidence is late, that fact is itself recorded
- Current implementation: JSONL append (fast), SQLite ingest (batched),
  telemetry (fire-and-forget)

Contract shape:
```
receipt_budget_ms: 500     # p99 target for receipt persistence
index_lag_budget_s: 30     # max acceptable signal index lag
evidence_timeout_ms: 5000  # hard cutoff, emit debt receipt if exceeded
```

The key insight: the decision path and evidence path have different failure
semantics. A slow decision is an outage. Slow evidence is debt.

---

## Fail Modes

### Fail-closed

Gate returns BLOCK when it cannot compute a verdict in time. Safer for
high-risk actions, but the governor becomes a single point of outage.

### Fail-open with debt receipt

Gate returns PROCEED with a structured "governance unavailable" receipt.
The action proceeds, but:

1. A `GOVERNANCE_DEBT` receipt is emitted with the reason, budget exceeded,
   and what was skipped
2. The debt receipt is itself queryable and counts against SLO
3. Downstream systems can detect "this action was not fully governed" from
   the receipt chain

This is the governor-native move: fail-open is itself a governed event.

### Fail mode is per-lane

The lane routing system already encodes risk. That's secretly SLO routing:

| Lane | Fail mode | Decision budget | Evidence requirement |
|------|-----------|-----------------|---------------------|
| Lane 3 (DEEP/high-risk) | Fail-closed | Generous (500ms) | Synchronous, full |
| Lane 2 (GENERAL) | Fail-open + debt | Standard (100ms) | Synchronous, may skip |
| Lane 1 (FAST/low-risk) | Fail-open + debt | Tight (50ms) | Async allowed |

This is not a new subsystem. It's a column in the existing lane contract.

---

## Temporal Coherence

Clock-time constraints beyond latency:

### Policy freshness

"The policy version used for this decision must be no more than X old."

If the daemon is running a cached policy and the policy file changed 2
hours ago, the decision was made against stale rules. This is not a latency
problem; it's a *coherence* problem.

```
policy_max_age_s: 3600        # re-read policy if older than this
policy_fingerprint_check: true # verify file hash on decision path
```

### Toolchain fingerprint

"The environment fingerprint must match the current toolchain."

If `pyproject.toml` changed since the last receipt, all FILE_EXISTS and
TESTS_PASS facts are potentially stale. The governor already has decay
semantics for this. The SLA adds a *time bound* on how long you can
operate with stale facts before the governor considers itself degraded.

### Index lag

"The signal index must be within Y seconds of the JSONL source."

The signal store already tracks `lag_bytes`. The SLA adds a contract:
if lag exceeds the budget, emit a signal (`SLO_INDEX_LAG_EXCEEDED`).

---

## Timing Fragment (2.x hook)

The one concrete 2.x deliverable: add a `timing` dict to receipts and
signals so that SLA measurement is possible before SLA enforcement exists.

### On gate receipts

```python
timing: {
    "start_ns": 1709123456789000000,   # monotonic, not wall clock
    "end_ns":   1709123456791000000,
    "duration_ms": 2.0,
    "budget_ms": 50,                    # which budget applied
    "budget_source": "lane_contract",   # where the budget came from
}
```

### On signal envelopes

Already have `emitted_at`. Add to `values` dict:

```python
values: {
    ...,
    "derivation_duration_ms": 3.2,     # how long the derivation took
}
```

### On debt receipts (new receipt type, 3.x)

```python
GOVERNANCE_DEBT: {
    "reason": "decision_timeout",
    "budget_ms": 50,
    "actual_ms": 73,
    "skipped": ["evidence_linking", "continuity_check"],
    "lane": "FAST",
    "fail_mode": "open",
}
```

No enforcement. Just measurement. Once you can measure it, SLA stops
being abstract and becomes another signal domain you can route, aggregate,
and yell about.

---

## Signal Domain

Once timing fragments exist, the SLA surface becomes a signal source:

| Signal | Phase | What |
|--------|-------|------|
| `SLO_DECISION_BUDGET` | 3.x | Decision path latency vs budget |
| `SLO_EVIDENCE_BUDGET` | 3.x | Evidence path latency vs budget |
| `SLO_INDEX_LAG` | 2.x | Signal index lag vs budget |
| `SLO_POLICY_STALE` | 3.x | Policy age vs freshness bound |
| `GOVERNANCE_DEBT` | 3.x | Count/rate of fail-open decisions |

These are all observe-only signals (consistent with the instrumentation
spine invariant). No gating. The SLA is a measurement, not a gate — the
gates are the existing gates; the SLA tells you whether they're meeting
their performance contract.

---

## What This Is Not

- Not an uptime SLA for a service (the governor is not a service yet)
- Not a promise to external customers (this is internal coherence)
- Not a monitoring system (the signals *are* the monitoring; no separate
  dashboard infrastructure)
- Not a replacement for the existing gate semantics (gates still gate;
  SLA tells you if the gates are performing)

This is: explicit, measurable contracts on the governor's own operational
behavior, expressed in the governor's own substrate (receipts, signals,
lanes), so that the governor can detect and report its own degradation.

"Missing the time for the clock" is the most governor-coded failure mode.
The SLA makes that failure visible.

---

## Implementation Order

1. **2.x: Timing fragment on gate receipts** — `start_ns`, `end_ns`,
   `duration_ms`, `budget_ms`. No enforcement. Just measurement.
   Requires: small edit to `gate_receipt.py`.

2. **2.x: `SLO_INDEX_LAG` signal** — emit from signal store when
   `lag_bytes` exceeds budget. Already have the data; just add the
   signal emission. Ships with `VERIFY_SUMMARY`.

3. **3.x: Fail-open debt receipts** — new receipt type, emitted when
   decision path exceeds timeout. Lane contract gets `fail_mode` column.

4. **3.x: Policy freshness constraint** — `policy_max_age_s` in config,
   checked on decision path. Stale policy → `SLO_POLICY_STALE` signal.

5. **3.x: Per-lane SLO enforcement** — budget enforcement in lane
   contracts. `SLO_DECISION_BUDGET` signal.

---

## Open Questions

- **Wall clock vs monotonic**: Timing fragments should use `time.monotonic_ns()`
  for duration, not `datetime.now()`. But receipts use ISO 8601 for
  `emitted_at`. Two clocks in one receipt?
  Resolution: `emitted_at` stays wall clock (human-readable, cross-process).
  `timing.start_ns`/`end_ns` are monotonic (accurate duration, single-process
  only). Both are correct for their purpose.

- **Budget source hierarchy**: Where does the budget come from?
  `lane_contract > profile > config > default`. Need a resolution order.
  Same pattern as intent resolution (6-layer stack).

- **Debt receipt vs debt signal**: Are these separate? A debt receipt is a
  gate receipt with verdict "proceed" and a debt reason. A debt signal is
  a signal envelope summarizing debt rate. Both exist; one is per-event,
  one is windowed.

---

## References

- Lane routing: `src/governor/lanes.py` (LaneContract, RoutePlan)
- Gate receipts: `src/governor/gate_receipt.py` (GateReceipt, ReceiptStore)
- Signal store: `src/governor/signal_store.py` (SignalStore, IngestResult)
- Decay semantics: `src/governor/ttl.py` (TTLManager, VolatilityClass)
- Policy freshness: relates to `specs/gaps/GOV_GAP_SESSION_001.md`
