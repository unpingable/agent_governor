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

Every v2 signal emission (σ-rate observations, capture diagnostics, heartbeat events, calibrated signals, replay results) uses this envelope:

```python
@dataclass
class SignalEnvelope:
    # Identity (content-addressed, same scheme as gate_receipt.py)
    envelope_id: str                  # H(canonical_json(content fields))
    schema_version: str               # "v2.1" — will promote to TemplateInst version

    # Source
    source: str                       # e.g. "governor.sigma_rate", "governor.capture_diag"
    run_id: str                       # ties to receipt kernel run

    # Clock vector (see GAP_INVARIANTS.md §1)
    step: int                         # monotonic per run (authoritative for ordering)
    wall_utc: str                     # ISO 8601 UTC (authoritative for cross-run)
    tokens: int | None                # cumulative tokens (derived, optional)
    tool_calls: int | None            # cumulative tool invocations (derived, optional)

    # Observation
    observation_type: str             # "measurement", "alert", "heartbeat", "replay_result"
    severity: str                     # "info" | "warn" | "fail" (see GAP_INVARIANTS.md §4)
    confidence: float                 # [0, 1]

    # Payload (source-specific, schema registered)
    payload: dict                     # the actual signal data
    payload_hash: str                 # H(canonical_json(payload))

    # Provenance (see GAP_INVARIANTS.md §2)
    governor_version: str             # git commit or package version
    parameter_snapshot_hash: str      # H(frozen params) — full snapshot stored separately
```

### Field Mapping to v3 TemplateInst

| v2 SignalEnvelope | v3 TemplateInst | Notes |
|-------------------|-----------------|-------|
| `envelope_id` | `content_hash` | Same computation |
| `schema_version` | `schema_version` | Promote "v2.1" → "v3.0" |
| `source` | `source` | Identical |
| `run_id` | `run_id` | Identical |
| `step` + `wall_utc` + ... | `ClockVector` | Promote flat fields to nested struct |
| `observation_type` | `observation_type` | Identical |
| `payload` | `payload` | Identical |
| `payload_hash` | `content_hash` | Identical |
| — | `turn_id` | Added in v3 (nullable in v2) |

v3 promotion = add `turn_id` field + nest clock fields into `ClockVector` + bump `schema_version`. No payload changes. No adapters.

### Rules

1. **All v2 gap spec implementations MUST emit via SignalEnvelope.** No raw dicts, no bespoke event shapes.
2. **Payload schemas registered in a central dict** (not a runtime registry yet — just a Python dict mapping source → expected keys). v3 promotes this to the SchemaRegistry.
3. **`local_only: true` signals** (if any) are exempt from envelope requirement but MUST be documented and WILL be deleted in v3. (See GAP_INVARIANTS.md §5.)
4. **PREDICT_REGIME_PREFLIGHT** emits into the same envelope as runtime detectors, even though it's advisory. This avoids wrapping it later.

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
