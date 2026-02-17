# Cross-Cutting Invariants & Contracts

Stapled onto all v2/v3 gap specs. Violating any of these turns the gap specs into an adapter museum.

## 1. Clock Law

Multiple clocks exist. Define which is authoritative and what happens when they disagree.

### Clocks

| Clock | Source | Authoritative For | Gameable? |
|-------|--------|--------------------|-----------|
| **Wall clock** | `datetime.utcnow()` | Ordering events in real time, heartbeat intervals | No (but skew possible) |
| **Step clock** | Monotonic counter per run | Ordering within a run, receipt chain seq | No |
| **Token clock** | API response metadata | Exposure measurement, cost estimation | Partially (model can pad) |
| **Tool-call clock** | Evidence gate invocations | Exposure (external surface changes) | No |
| **Turn clock** | User/assistant alternation | Session progress | Partially (model can split) |

### Rules

1. **Step clock is the total-order key within a run.** All events within a run are ordered by step. Wall clock is metadata, not identity.
2. **Wall clock is authoritative for cross-run ordering** and heartbeat/starvation detection.
3. **Token clock is derived, never authoritative.** It's an input to ExposureVector, not a standalone signal.
4. **Missing clock = fail-safe.** If wall clock is absent, treat event as "now." If step clock is absent, event is unorderable (reject).
5. **Skew tolerance:** Wall clock skew up to 5 seconds is ignored. Beyond that, emit a `CLOCK_SKEW` telemetry event and use step clock for ordering.
6. **All trend tests (σ-rate, capture diagnostic, regime detector) use step clock for their window boundaries**, not wall clock. Wall clock drift must not create phantom trends.

### Conversion

```python
@dataclass
class ClockVector:
    step: int                     # monotonic per run (authoritative)
    wall_utc: datetime            # real time (cross-run ordering)
    tokens: int | None            # cumulative tokens (derived)
    tool_calls: int | None        # cumulative tool invocations (derived)
    turn: int | None              # conversation turn (derived)
```

Every `TemplateInst` / signal envelope carries a `ClockVector`. Consumers choose which clock dimension to use; the envelope doesn't decide for them.

## 2. Determinism Contract for Replay

Receipts must carry enough metadata to make replay meaningful, not "recompute with new code."

### Required Provenance Fields (on every replay-eligible receipt)

| Field | Purpose |
|-------|---------|
| `governor_version` | Git commit hash or package version |
| `detector_versions` | Dict of detector name → version (for external detectors) |
| `parameter_snapshot` | Frozen dict of all tunable params at emission time |
| `window_definition` | Window size, step boundaries, overlap config |
| `sampling_cadence` | How often this signal is sampled |
| `random_seed` | If any stochastic process involved (None if deterministic) |

### Rule

If a replay produces a different verdict than the original, and the provenance fields match exactly, that's a **bug**. If provenance fields differ, the divergence is **expected** and must be annotated in the `ReplayResult.differences` list.

## 3. Emission Contracts (Per-Sensor)

SILENT_SUPPRESSION_GAP covers "governor unplugged." This contract covers **partial suppression**: a sensor is enabled but emitted zero events.

### Rule

Every registered signal source declares:
```python
@dataclass
class EmissionContract:
    source: str                   # e.g. "evidence_gate", "drift_detector"
    expected_emissions_per_window: int  # minimum expected events per observation window
    zero_is_valid: bool           # True only for sensors that legitimately produce nothing (e.g. no drift = no events)
```

If `not zero_is_valid` and actual emissions = 0 for a window → `SENSOR_SILENT` telemetry event. This is distinct from `GATE_STARVATION` (no calls at all) — here the gate was called but one sensor channel didn't fire.

### Why This Matters

Capture detection relies on contradiction signals. If the contradiction detector runs but the evidence gate doesn't feed it claims, contradictions = 0 — which looks like "no problems" when it's actually "no measurement."

## 4. Severity Taxonomy (Warn-First Structure)

v2 accumulates warnings. Without consistent structure, the CLI/dashboard becomes a slot machine.

### Fields (on every warning/alert)

| Field | Type | Meaning |
|-------|------|---------|
| `severity` | enum: `info`, `warn`, `fail` | How bad |
| `confidence` | float [0, 1] | How sure we are |
| `actionability` | enum: `observe`, `investigate`, `act` | What the operator should do |
| `baseline_delta` | float | How far from baseline (in calibrated units, once calibration exists) |
| `source` | str | Which subsystem emitted this |
| `evidence_ref` | str \| None | Receipt/blob ID supporting this assessment |

### Severity Rules

- `info`: Emitted on every observation cycle. No operator attention needed.
- `warn`: Something is outside baseline. Operator should look. **No automated response.**
- `fail`: Hard invariant violated. Gating action may follow. **Always has evidence_ref.**

### Escalation

Sustained `warn` (configurable, default 5 consecutive windows) auto-escalates `actionability` from `observe` → `investigate`. Never auto-escalates to `act` — that requires a `fail` or human override.

## 5. No Temporary Adapters

**Rule:** If a v2 signal cannot be emitted in an envelope that is shape-compatible with the eventual v3 `TemplateInst`, then either:

1. Change the v2 envelope now to be compatible, or
2. Explicitly mark the signal `local_only: true` — meaning it will be **deleted** (not adapted) when v3 lands.

There is no third option. "Temporary adapter" is not a category that exists.

### Practical Implication

The v2 minimal signal envelope (defined in GAP_BUILD_ORDER.md) must be a strict subset of v3 `TemplateInst`. v3 promotion is "add fields + freeze schema version," not "rewrite + adapt."

## 6. Receipt Integrity at Shard Boundaries (v3 Pre-Requisite)

Even in single-tenant v2, design receipts so they survive sharding:

- **Content-addressed IDs** (already done in gate_receipt.py) are naturally dedup-safe across shards.
- **Hash chains are per-run, not global.** A run's chain integrity is verifiable without access to other runs.
- **Epoch roots** (in REPLAY_HARNESS_GAP) provide tamper-evidence at compaction boundaries.
- **Signatures are deferred to v3.** v2 relies on filesystem permissions; v3 needs cryptographic signing for multi-tenant.

The v2 design must not preclude adding signatures later. This means: never hash over mutable metadata (timestamps are metadata, not identity — already correct in gate_receipt.py).
