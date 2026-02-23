# Gap Spec Build Order

Sequencing based on dependency analysis. Each phase has exit criteria.

## v2.4 — Instrumentation Spine (Observe, Measure, Warn)

None of this shipped in 2.0–2.3. The entire instrumentation spine is parked for v2.4.
See `docs/V2_STATUS.md` for the 2.x boundary.

### Phase A — Instrumentation Spine

| Order | Spec | Why First |
|-------|------|-----------|
| 1 | SILENT_SUPPRESSION_GAP | Can't diagnose capture if the governor is unplugged |
| 2 | EXPOSURE_PROXY_GAP (v0) | Non-gameable denominator for all capture metrics |
| 3 | SIGMA_RATE_GAP (observe-only) | Cheap, portable, immediately useful time series |

**Exit criteria:** You can tell (a) governor ran, (b) what it touched, (c) how often it endorsed then invalidated.

### Phase B — Reflexive Health (Warn-Only)

| Order | Spec | Depends On |
|-------|------|------------|
| 4 | CAPTURE_SELF_DIAGNOSTIC_GAP | EXPOSURE_PROXY (hard), SIGMA_RATE (soft) |

**Invariant:** "no contradictions" must be distinguishable from "no contradiction recording" (SILENT_SUPPRESSION provides this).

**Exit criteria:** Advisory warning fires on synthetic declining-rate scenarios. No gating.

### Phase C — Make It Measurable

| Order | Spec | Depends On |
|-------|------|------------|
| 5 | REPLAY_HARNESS_GAP (Tier B-lite) | Receipt kernel (shipped), σ-rate data |
| 6 | CALIBRATION_LAYER_GAP (v0) | Replay harness (for validation) |

Calibration v0 = each signal → bounded [0,1], explicit saturation, versioned params in receipts. Not perfect — iterate via replay.

**Exit criteria:** You can sweep thresholds and see the effect on "would have warned" over stored runs.

### Phase D — Preflight as Lint

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

GOV_PRIM_PROV_001 ──┬──→ GOV_GAP_CHAIN_001 ──→ GOV_GAP_EGRESS_001
                    │
                    └──→ GOV_GAP_EGRESS_001

GOV_GAP_MCP_SUPPLY_001 (v3, standalone)
GOV_GAP_SESSION_001 (v3, needs principal model)
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
    event_id: str                     # stable identity (UUID/ULID); producer-assigned, survives resequencing
    seq: int                          # monotonic per run; stream-assigned total order (may change on repack)
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
    calibration_id: str | None        # which calibration produced value_norm (None until calibration layer)
    confidence: float                 # [0,1] — how much data backs this measurement

    # ── Severity taxonomy (warn-first structure) ────────────────────
    severity: str                     # "info" | "warn" | "fail"
    actionability: str                # "observe" | "investigate" | "act"
    reason_codes: list[str]           # stable machine-readable codes (see ReasonCode enum)

    # ── Windowing (trend tests + replay sweeps depend on this) ──────
    window: WindowDescriptor | None   # None for point-in-time events

    # ── Policy (for POLICY_DECISION events) ─────────────────────────
    policy: PolicyRef | None          # None for non-decision events

    # ── Payload (source-specific, schema registered) ────────────────
    payload: dict                     # the actual signal data (source-specific)
    payload_hash: str                 # H(canonical_json(payload))

    # ── Integrity ───────────────────────────────────────────────────
    checkpoint: CheckpointRef | None  # epoch root reference (None for non-checkpoint events)

    # ── Traceability ────────────────────────────────────────────────
    parent_event_id: str | None       # references event_id (NEVER seq); for derived signals
    tenant_id: str                    # "local" in v2; real tenant ID in PaaS v3

@dataclass
class WindowDescriptor:
    clock_kind: str                   # "step" (v2 only); future: "token", "wall"
    kind: str                         # "rolling" | "tumbling" | "cumulative"
    size: int                         # window size in clock_kind units
    start: int | None                 # explicit boundary (optional)
    end: int | None                   # explicit boundary (optional)
    agg: str                          # "mean" | "slope" | "ratio" | "count" | "max"
    sample_count: int                 # how many points contributed

@dataclass
class CheckpointRef:
    epoch_id: str
    root_hash: str                    # Merkle root of event hashes in range
    seq_start: int                    # range boundary on seq axis
    seq_end: int                      # range boundary on seq axis
    step_start: int                   # range boundary on step axis (for cross-reference)
    step_end: int                     # range boundary on step axis (for cross-reference)
    prev_root_hash: str | None        # chain across epochs

@dataclass
class PolicyRef:
    policy_id: str                    # which policy was evaluated
    policy_version: str               # version of that policy
    verdict: str                      # "allow" | "warn" | "deny" | "escalate"
    reason_codes: list[str]           # stable machine-readable codes

class EventType:
    """Enum values for event_type field."""
    SENSOR_SAMPLE = "sensor_sample"           # single observation
    SENSOR_SUMMARY = "sensor_summary"         # windowed aggregation
    HEARTBEAT = "heartbeat"                   # liveness proof
    POLICY_DECISION = "policy_decision"       # warn-only in v2; gating in v3
    CHECKPOINT = "checkpoint"                 # epoch root
    PREFLIGHT_PREDICTION = "preflight_prediction"  # advisory regime prediction
```

### Identity semantics: `event_id` vs `seq`

- **`event_id`**: stable identity (UUID/ULID), producer-assigned. Survives resequencing, stream merge, log repack. This is what `parent_event_id` references.
- **`seq`**: total order within a run, stream/ingest-assigned. May change on repack/merge. This is what sharding and checkpoint ranges use.
- **`parent_event_id` always references `event_id`, never `seq`.** Lineage must survive resequencing.

### Canonicalization + hash rules

Content hash (`payload_hash`) is computed via:
- `json.dumps(payload, sort_keys=True, separators=(',',':'), ensure_ascii=True).encode('utf-8')` (same as gate_receipt.py)
- SHA-256, hex-encoded with `sha256:` prefix
- Numbers: Python `json.dumps` default (no trailing zeros, no scientific for small integers)
- Null: JSON `null` (not absent key)

**Hash inclusion rules:**
- `payload_hash` covers: `payload` dict only
- `seq` is **excluded** from hashed material (it's stream-assigned, may change on repack)
- `event_id` is **included** in the checkpoint Merkle tree (binds identity to epoch root)
- Checkpoint `root_hash` = Merkle root of `H(event_id || payload_hash)` for all events in the seq range
- This means: order is bound by `(seq → event_id)` mapping inside the checkpoint, not by signing individual events

**Consequence:** Valid checkpoint + valid event_id chain = tamper-evident ordering, even though `seq` itself is mutable.

### Reason codes (stable, machine-readable)

Every `severity: warn` or `severity: fail` event MUST include at least one `reason_code`. Human text lives in `payload`; dashboards and replay key on reason codes.

```python
class ReasonCode:
    """Stable reason codes. Add new codes; never rename or remove existing ones."""
    # ── Capture / suppression ───────────────────────────────────────
    CAPTURE_LOW_CONTRADICTION_UNDER_EXPOSURE = "capture_low_contradiction_under_exposure"
    CAPTURE_ENTROPY_NON_INCREASING = "capture_entropy_non_increasing"
    CAPTURE_COMMITMENT_LOSS = "capture_commitment_loss"

    # ── Silent suppression ──────────────────────────────────────────
    GATE_STARVATION = "gate_starvation"           # no gate calls at all
    SENSOR_SILENT = "sensor_silent"               # gate called, sensor emitted zero
    HEARTBEAT_MISSED = "heartbeat_missed"         # expected heartbeat not received

    # ── Sigma rate ──────────────────────────────────────────────────
    SIGMA_ABOVE_BASELINE = "sigma_above_baseline"
    SIGMA_TREND_RISING = "sigma_trend_rising"

    # ── Exposure ────────────────────────────────────────────────────
    EXPOSURE_CLOCK_SKEW = "exposure_clock_skew"

    # ── Calibration ─────────────────────────────────────────────────
    CALIBRATION_INSUFFICIENT_DATA = "calibration_insufficient_data"
    CALIBRATION_BASELINE_SHIFT = "calibration_baseline_shift"

    # ── Regime / preflight ──────────────────────────────────────────
    REGIME_PREDICTED_UNSTABLE = "regime_predicted_unstable"
    REGIME_PREDICTED_METASTABLE = "regime_predicted_metastable"

    # ── Policy ──────────────────────────────────────────────────────
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    BUDGET_EXCEEDED = "budget_exceeded"
    LOOP_DETECTED = "loop_detected"
    TOOL_CHURN = "tool_churn"
```

### Preflight prediction: vector output

PREFLIGHT_PREDICTION events use `value_raw` for the primary risk score (boundary proximity, [0,1]). The full prediction vector lives in `payload`:

```json
{
  "predicted_regime": "metastable",
  "boundary_proximity": 0.73,
  "confidence": 0.85,
  "failure_mode": "drift_cycle",
  "metric_count": 7,
  "window_size": 15
}
```

This avoids smuggling meaning into `unit` while keeping the flat `value_raw` field useful for dashboards and calibration.

### Canonical JSON example

```json
{
  "schema_version": 1,
  "run_id": "run_abc123",
  "event_id": "evt_01JMKX7V3QWERTY",
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
  "calibration_id": null,
  "confidence": 0.8,
  "severity": "warn",
  "actionability": "observe",
  "reason_codes": ["sigma_above_baseline"],
  "window": {
    "clock_kind": "step",
    "kind": "rolling",
    "size": 200,
    "agg": "slope",
    "sample_count": 180
  },
  "policy": null,
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
| `event_id` | `event_id` | Identical |
| `seq` | `seq` | Identical |
| `event_type` | `event_type` | Identical |
| `step` + `t_wall` | `clock: ClockVector` | Nest into struct, add `tokens` + `tool_calls` |
| `producer` | `producer` | Identical |
| `signal_id` | `signal_id` | Identical |
| `detector_version` + `code_hash` + ... | `provenance: Provenance` | Nest into struct |
| `value_raw` + `unit` + `direction` + `value_norm` + `calibration_id` | `value: SignalValue` | Nest into struct |
| `severity` + `actionability` + `reason_codes` | `assessment: Assessment` | Nest into struct |
| `window` | `window` | Identical (clock_kind already present) |
| `policy` | `policy` | Identical |
| `payload` + `payload_hash` | `payload` + `content_hash` | Rename hash field |
| `checkpoint` | `checkpoint` | Identical (both seq + step ranges) |
| `parent_event_id` | `parent_event_id` | Identical (always refs event_id) |
| `tenant_id` | `tenant_id` | Identical |
| — | `turn_id` | Added in v3 (nullable) |
| — | `integrity.sig` | Added in v3 (cryptographic signature) |

v3 promotion = nest flat fields into typed structs + add `turn_id` + add `integrity.sig` + bump `schema_version`. No payload changes. No field deletions. No adapters.

### Rules

1. **All v2 gap spec implementations MUST emit via SignalEnvelope.** No raw dicts, no bespoke event shapes.
2. **Payload schemas registered in a central dict** (not a runtime registry yet — just a Python dict mapping `signal_id` → expected keys). v3 promotes this to the SchemaRegistry.
3. **`local_only: true` signals** (if any) are exempt from envelope requirement but MUST be documented and WILL be deleted in v3. (See GAP_INVARIANTS.md §5.)
4. **PREDICT_REGIME_PREFLIGHT** emits into the same envelope as runtime detectors (event_type=`preflight_prediction`). Vector output in payload; `value_raw` = boundary proximity.
5. **Ordering is by `seq`, never by `t_wall`.** Timestamp jitter must not affect event ordering.
6. **`tenant_id` defaults to `"local"` in v2.** Never omit it — PaaS promotion must not require backfilling.
7. **`parent_event_id` always references `event_id`, never `seq`.** Lineage must survive resequencing.
8. **Every `warn` or `fail` event MUST include at least one `reason_code`.** Human text in payload; machine codes in `reason_codes`.
9. **`reason_codes` are append-only.** New codes can be added; existing codes are never renamed or removed.

### PR requirements (per-gap implementation)

Every gap spec PR must include:

1. **SignalEnvelope emission** — all new signals emitted via the envelope
2. **Invariant tests** — at least one test asserting the cross-cutting contracts (clock law, emission contract, severity fields)
3. **At least one replay/backtest assertion** — even crude; e.g. "emit 10 envelopes, replay, verify same reason_codes"
4. **Golden fixtures** — freeze 2-3 representative envelope sequences as JSON test fixtures. These catch "harmless refactor changed semantics" immediately. Store in `tests/fixtures/envelopes/`.

## Cross-Cutting Contracts

All specs honor the invariants in `GAP_INVARIANTS.md`:
1. **Clock law** — step clock is total-order within run; wall clock for cross-run
2. **Determinism contract** — receipts carry governor_version, param snapshot, window defs
3. **Emission contracts** — per-sensor expected counts; zero ≠ healthy unless declared
4. **Severity taxonomy** — info/warn/fail × confidence × actionability
5. **No temporary adapters** — v2 signals emit via SignalEnvelope or are marked `local_only` (deleted in v3)
6. **Receipt integrity** — content-addressed IDs, per-run hash chains, epoch roots at compaction boundaries

## v2.x — Threat Intelligence Hardening (Feb 2026)

From threat intelligence review mapping real-world LLM attack patterns to
governor controls. Three gaps need v2 hook points now (interface + receipt);
two are v3 roadmap items.

### v2 Hook Points Required

| Spec | What | Depends On |
|------|------|------------|
| GOV_PRIM_PROV_001 | Provenance labels on tool outputs | None (primitive) |
| GOV_GAP_CHAIN_001 | Composition-aware capability gating | Provenance labels (soft) |
| GOV_GAP_EGRESS_001 | Outbound data-flow policy gate | Provenance labels, chain gate (soft) |

Build order: provenance labels first (other gates consume them), then
chain gate (sequence-level), then egress gate (payload-level).

### v3 Roadmap

| Spec | What | Why Deferred |
|------|------|--------------|
| GOV_GAP_MCP_SUPPLY_001 | Signed tool manifests + hash pinning | MCP ecosystem immature |
| GOV_GAP_SESSION_001 | Cryptographic session binding | v2 is local-only; needs principal model |

### v2 Bake-In Checklist

Even for v3-deferred items, v2 must include placeholder fields:

- [ ] Receipt schema: `principal_ref` field (null in v2)
- [ ] Daemon config: `[security]` section (commented out in v2)
- [ ] `governor.hello` response: `auth_method` field (= "local" in v2)
- [ ] Capability taxonomy: enumerated capability classes for chain gate
- [ ] Policy engine: abstract interface (chain + egress share evaluation pattern)

---

## Files

```
specs/gaps/SILENT_SUPPRESSION_GAP.md        # v2.4 Phase A
specs/gaps/EXPOSURE_PROXY_GAP.md            # v2.4 Phase A
specs/gaps/SIGMA_RATE_GAP.md                # v2.4 Phase A
specs/gaps/CAPTURE_SELF_DIAGNOSTIC_GAP.md   # v2.4 Phase B
specs/gaps/REPLAY_HARNESS_GAP.md            # v2.4 Phase C
specs/gaps/CALIBRATION_LAYER_GAP.md         # v2.4 Phase C
specs/gaps/PREDICT_REGIME_PREFLIGHT_GAP.md  # v2.4 Phase D
specs/gaps/CROSS_DOMAIN_SCHEMA_GAP.md       # v3.0
specs/gaps/PAAS_SHARDING_GAP.md             # v3.0
specs/gaps/KAPPA_DIAL_GAP.md                # v3.1
specs/gaps/REGIME_CAPTURE_2D_GAP.md         # v3.2
specs/gaps/GOV_PRIM_PROV_001.md             # v2.x threat hardening (provenance labels)
specs/gaps/GOV_GAP_CHAIN_001.md             # v2.x threat hardening (composition gate)
specs/gaps/GOV_GAP_EGRESS_001.md            # v2.x threat hardening (egress gate)
specs/gaps/GOV_GAP_MCP_SUPPLY_001.md        # v3.x roadmap (tool supply chain)
specs/gaps/GOV_GAP_SESSION_001.md           # v3.x roadmap (session binding)
specs/gaps/GAP_BUILD_ORDER.md               # this file
specs/gaps/GAP_INVARIANTS.md                # cross-cutting contracts (clock, determinism, severity, emissions)
```
