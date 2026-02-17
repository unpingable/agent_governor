# Gap Spec Build Order

Sequencing based on dependency analysis. Each phase has exit criteria.

## v2.x — Observe, Measure, Warn

### v2.1 — Instrumentation Spine

| Order | Spec | Why First |
|-------|------|-----------|
| 1 | SILENT_SUPPRESSION_GAP | Can't diagnose capture if the governor is unplugged |
| 2 | EXPOSURE_PROXY_GAP (v0) | Non-gameable denominator for all capture metrics |
| 3 | SIGMA_RATE_GAP (observe-only) | Cheap, portable, immediately useful time series |

**Exit criteria:** You can tell (a) governor ran, (b) what it touched, (c) how often it endorsed then invalidated.

### v2.2 — Reflexive Health (Warn-Only)

| Order | Spec | Depends On |
|-------|------|------------|
| 4 | CAPTURE_SELF_DIAGNOSTIC_GAP | EXPOSURE_PROXY (hard), SIGMA_RATE (soft) |

**Invariant:** "no contradictions" must be distinguishable from "no contradiction recording" (SILENT_SUPPRESSION provides this).

**Exit criteria:** Advisory warning fires on synthetic declining-rate scenarios. No gating.

### v2.3 — Make It Measurable

| Order | Spec | Depends On |
|-------|------|------------|
| 5 | REPLAY_HARNESS_GAP (Tier B-lite) | Receipt kernel (shipped), σ-rate data |
| 6 | CALIBRATION_LAYER_GAP (v0) | Replay harness (for validation) |

Calibration v0 = each signal → bounded [0,1], explicit saturation, versioned params in receipts. Not perfect — iterate via replay.

**Exit criteria:** You can sweep thresholds and see the effect on "would have warned" over stored runs.

### v2.4 — Preflight as Lint

| Order | Spec | Depends On |
|-------|------|------------|
| 7 | PREDICT_REGIME_PREFLIGHT_GAP | Calibration layer (for calibrated risk scores), replay (for validation) |

**Exit criteria:** Predicted regime matches empirical CollapseDetector >80% of the time on replay data.

---

## v3.x — Integrate, Scale, Operate

### v3.0 — Contract First

| Order | Spec | Why First |
|-------|------|-----------|
| 8 | CROSS_DOMAIN_SCHEMA_GAP | Public API — schema versioning, clock semantics, partition keys |
| 9 | PAAS_SHARDING_GAP | Ordering guarantees, epoch roots, multi-daemon roles |

### v3.1 — Grounded Policy Knobs

| Order | Spec | Depends On |
|-------|------|------------|
| 10 | KAPPA_DIAL_GAP | Calibration layer + replay (κ must map to measurable frontier) |

### v3.2 — Operator Surface

| Order | Spec | Depends On |
|-------|------|------------|
| 11 | REGIME_CAPTURE_2D_GAP | Regime + capture on same calibrated scale |

---

## Dependency Graph

```
SILENT_SUPPRESSION ──┐
                     ├──→ CAPTURE_SELF_DIAGNOSTIC
EXPOSURE_PROXY ──────┘           │
     │                           │
SIGMA_RATE ──────────────────────┘
     │
     └──→ REPLAY_HARNESS ──→ CALIBRATION_LAYER ──→ PREDICT_REGIME_PREFLIGHT
               │                    │
               │                    └──→ KAPPA_DIAL
               │                    └──→ REGIME_CAPTURE_2D
               │
               └──→ CROSS_DOMAIN_SCHEMA ──→ PAAS_SHARDING
```

## v2→v3 Migration Trick

In v2, define a minimal "signal envelope" in receipts that is intentionally isomorphic to the eventual v3 TemplateInst fields (but don't call it the v3 schema yet). v3 promotes + freezes; no rewrite.

### v2 Minimal Signal Envelope

Every v2 signal emission (σ-rate observations, capture diagnostics, heartbeat events, calibrated signals, replay results, epoch checkpoints) uses this envelope. One job: carry any signal in a shape that can be appended, replayed, partitioned by `run_id`, and upgraded by `schema_version`.

```python
@dataclass
class SignalEnvelope:
    # ── Identity + ordering (sharding depends on this) ──────────────
    schema_version: int               # envelope schema version (1 for v2; promotes to v3)
    run_id: str                       # partition key; total-order boundary
    seq: int                          # monotonic per run; total order within the run stream
    event_type: str                   # enum: see EventType below

    # ── Clock vector (trend tests depend on this) ───────────────────
    step: int                         # monotonic per run (AUTHORITATIVE for ordering)
    t_wall: str | None                # ISO 8601 UTC (cross-run ordering / UX; never authoritative)

    # ── Source + signal identity ────────────────────────────────────
    producer: str                     # subsystem: "detector.scalar", "governor.correlator", "governor.preflight"
    signal_id: str                    # stable name: "sigma_rate", "exposure_proxy", "contradiction_trend"

    # ── Provenance / determinism (replay depends on this) ──────────
    detector_version: str             # semver or commit-ish for producing logic
    code_hash: str                    # git commit or package build ID
    params_hash: str                  # H(frozen config used at emission time)
    seed: int | None                  # stochastic seed if any; None = deterministic

    # ── Value (calibration depends on this) ─────────────────────────
    value_raw: float | None           # raw signal value (None for non-numeric events like heartbeats)
    unit: str | None                  # "per_step", "ratio", "count", "seconds", etc.
    direction: str | None             # "higher_worse" | "lower_worse" | None (for non-directional)
    value_norm: float | None          # calibrated [0,1] risk score (None until calibration layer exists)
    confidence: float                 # [0,1] — how much data backs this measurement

    # ── Severity taxonomy (warn-first structure) ────────────────────
    severity: str                     # "info" | "warn" | "fail"
    actionability: str                # "observe" | "investigate" | "act"

    # ── Windowing (trend tests + replay sweeps depend on this) ──────
    window: WindowDescriptor | None   # None for point-in-time events

    # ── Payload (source-specific, schema registered) ────────────────
    payload: dict                     # the actual signal data (source-specific)
    payload_hash: str                 # H(canonical_json(payload))

    # ── Integrity ───────────────────────────────────────────────────
    checkpoint: CheckpointRef | None  # epoch root reference (None for non-checkpoint events)

    # ── Traceability ────────────────────────────────────────────────
    parent_event_id: str | None       # for derived signals (e.g. calibrated from raw)
    tenant_id: str                    # "local" in v2; real tenant ID in PaaS v3

@dataclass
class WindowDescriptor:
    kind: str                         # "rolling" | "tumbling" | "cumulative"
    size_steps: int                   # window size in step-clock units
    start_step: int | None            # explicit boundary (optional)
    end_step: int | None              # explicit boundary (optional)
    agg: str                          # "mean" | "slope" | "ratio" | "count" | "max"
    sample_count: int                 # how many points contributed

@dataclass
class CheckpointRef:
    epoch_id: str
    root_hash: str                    # Merkle root of events in range
    range_start_seq: int
    range_end_seq: int
    prev_root_hash: str | None        # chain across epochs

class EventType:
    """Enum values for event_type field."""
    SENSOR_SAMPLE = "sensor_sample"           # single observation
    SENSOR_SUMMARY = "sensor_summary"         # windowed aggregation
    HEARTBEAT = "heartbeat"                   # liveness proof
    POLICY_DECISION = "policy_decision"       # warn-only in v2; gating in v3
    CHECKPOINT = "checkpoint"                 # epoch root
    PREFLIGHT_PREDICTION = "preflight_prediction"  # advisory regime prediction
```

### Canonical JSON example

```json
{
  "schema_version": 1,
  "run_id": "run_abc123",
  "seq": 847,
  "event_type": "sensor_summary",
  "step": 980,
  "t_wall": "2026-02-16T18:32:10.123Z",
  "producer": "governor.sigma_rate",
  "signal_id": "sigma_rate",
  "detector_version": "2.1.0",
  "code_hash": "git:deadbeef",
  "params_hash": "sha256:a1b2c3...",
  "seed": null,
  "value_raw": 0.031,
  "unit": "per_step",
  "direction": "higher_worse",
  "value_norm": null,
  "confidence": 0.8,
  "severity": "warn",
  "actionability": "observe",
  "window": {
    "kind": "rolling",
    "size_steps": 200,
    "agg": "slope",
    "sample_count": 180
  },
  "payload": {"endorsed_count": 180, "contradiction_count": 6, "contributing_ids": ["..."]},
  "payload_hash": "sha256:f4e5d6...",
  "checkpoint": null,
  "parent_event_id": null,
  "tenant_id": "local"
}
```

### "Does it pass?" rubric

1. **Replay**: Can I reproduce this signal on a different machine? Yes — `detector_version` + `code_hash` + `params_hash` + `seed` pin the logic.
2. **Sweep**: Can I sweep thresholds without guessing the window? Yes — `window.kind` + `size_steps` + `agg` + `sample_count` are explicit.
3. **Shard**: Can I partition by `run_id` and compute trends without cross-shard joins? Yes — `seq` is total order within run; `step` is authoritative clock.
4. **Compact**: Can I compact with epoch roots and keep tamper-evidence? Yes — `checkpoint.*` anchored to `seq` (same ordering key as shard).
5. **κ later**: Can I add κ as quota/policy without rewriting? Yes — `actionability` + `severity` + `tenant_id` are already present.

### Field Mapping to v3 TemplateInst

| v2 SignalEnvelope | v3 TemplateInst | Promotion |
|-------------------|-----------------|-----------|
| `schema_version: 1` | `schema_version: 2` | Bump |
| `run_id` | `run_id` | Identical |
| `seq` | `seq` | Identical |
| `event_type` | `event_type` | Identical |
| `step` + `t_wall` | `clock: ClockVector` | Nest into struct, add `tokens` + `tool_calls` |
| `producer` | `producer` | Identical |
| `signal_id` | `signal_id` | Identical |
| `detector_version` + `code_hash` + ... | `provenance: Provenance` | Nest into struct |
| `value_raw` + `unit` + `direction` + `value_norm` | `value: SignalValue` | Nest into struct |
| `severity` + `actionability` | `assessment: Assessment` | Nest into struct |
| `window` | `window` | Identical |
| `payload` + `payload_hash` | `payload` + `content_hash` | Rename hash field |
| `checkpoint` | `checkpoint` | Identical |
| `parent_event_id` | `parent_event_id` | Identical |
| `tenant_id` | `tenant_id` | Identical |
| — | `turn_id` | Added in v3 (nullable) |
| — | `integrity.sig` | Added in v3 (cryptographic signature) |

v3 promotion = nest flat fields into typed structs + add `turn_id` + add `integrity.sig` + bump `schema_version`. No payload changes. No field deletions. No adapters.

### Rules

1. **All v2 gap spec implementations MUST emit via SignalEnvelope.** No raw dicts, no bespoke event shapes.
2. **Payload schemas registered in a central dict** (not a runtime registry yet — just a Python dict mapping `signal_id` → expected keys). v3 promotes this to the SchemaRegistry.
3. **`local_only: true` signals** (if any) are exempt from envelope requirement but MUST be documented and WILL be deleted in v3. (See GAP_INVARIANTS.md §5.)
4. **PREDICT_REGIME_PREFLIGHT** emits into the same envelope as runtime detectors (event_type=`preflight_prediction`). This avoids wrapping it later.
5. **Ordering is by `seq`, never by `t_wall`.** Timestamp jitter must not affect event ordering.
6. **`tenant_id` defaults to `"local"` in v2.** Never omit it — PaaS promotion must not require backfilling.

## Cross-Cutting Contracts

All specs honor the invariants in `GAP_INVARIANTS.md`:
1. **Clock law** — step clock is total-order within run; wall clock for cross-run
2. **Determinism contract** — receipts carry governor_version, param snapshot, window defs
3. **Emission contracts** — per-sensor expected counts; zero ≠ healthy unless declared
4. **Severity taxonomy** — info/warn/fail × confidence × actionability
5. **No temporary adapters** — v2 signals emit via SignalEnvelope or are marked `local_only` (deleted in v3)
6. **Receipt integrity** — content-addressed IDs, per-run hash chains, epoch roots at compaction boundaries

## Files

```
specs/gaps/SILENT_SUPPRESSION_GAP.md        # v2.1
specs/gaps/EXPOSURE_PROXY_GAP.md            # v2.1
specs/gaps/SIGMA_RATE_GAP.md                # v2.1
specs/gaps/CAPTURE_SELF_DIAGNOSTIC_GAP.md   # v2.2
specs/gaps/REPLAY_HARNESS_GAP.md            # v2.3
specs/gaps/CALIBRATION_LAYER_GAP.md         # v2.3
specs/gaps/PREDICT_REGIME_PREFLIGHT_GAP.md  # v2.4
specs/gaps/CROSS_DOMAIN_SCHEMA_GAP.md       # v3.0
specs/gaps/PAAS_SHARDING_GAP.md             # v3.0
specs/gaps/KAPPA_DIAL_GAP.md                # v3.1
specs/gaps/REGIME_CAPTURE_2D_GAP.md         # v3.2
specs/gaps/GAP_BUILD_ORDER.md               # this file
specs/gaps/GAP_INVARIANTS.md                # cross-cutting contracts (clock, determinism, severity, emissions)
```
