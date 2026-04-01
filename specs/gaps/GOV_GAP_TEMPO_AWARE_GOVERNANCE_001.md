# GOV_GAP_TEMPO_AWARE_GOVERNANCE_001

## Title
Tempo-Aware Governance: Ratio-Normalized Temporal Failure Model

## Status
Gap spec — 3.x (new governing dimension, not a 2.x feature)

## Origin
Paper 22 (Δt Framework): "No Universal Plant Clock: Temporal Failure Geometry in Distributed Control Systems"

## Problem Statement

Governor already implements local temporal defenses — staleness detection, recency decay, freshness gating, hysteresis, regime detection, dwell time, temporal windows, contract rot handling. These mechanisms work. They are also **context-blind about tempo**: every threshold is absolute, not normalized against how fast the governed system is actually changing.

A fixed 100ms observation threshold means nothing in a system evolving over hours, is catastrophic in a system evolving in microseconds, and is performative rigor in a system that hasn't changed in weeks.

**Governor has temporal mechanisms without a unified temporal model.**

The gap is not "build staleness." The gap is:

1. No first-class plant timescale (T_p)
2. No ratio-based diagnostics
3. No unified four-layer temporal failure taxonomy
4. No four-timestamp event model
5. No actuation-lag accounting

## Objective

Introduce tempo-aware governance by modeling plant timescale, normalizing temporal thresholds by ratio to system dynamics, and surfacing dominant temporal failure modes across observation, synchronization, clocking, and actuation.

## Paper 22 Foundation

### Four Temporal Failure Layers

| Layer | Assumption violated | Failure mode |
|-------|-------------------|--------------|
| Gauge mismatch | Universal plant clock exists | Ordering ambiguity, split-brain, conflicting decisions |
| Clock divergence | Local clocks are interchangeable | Contract rot — leases, deadlines, validity windows mean different things to different parties |
| Retarded-state estimation | Remote current state is directly accessible | Acting on stale state, model-reality divergence, systematic overshoot |
| Delayed actuation | Control is instantaneous | Oscillation, overcorrection, induced volatility |

### Five Characteristic Timescales

- **T_p** — plant timescale: how fast the governed system evolves
- **T_s** — synchronization uncertainty: how well nodes agree on "now"
- **T_c** — clock divergence horizon: how long before local clocks invalidate temporal contracts
- **T_o** — observation latency: delay between event and controller receiving measurement
- **T_u** — actuation latency: delay between controller emitting command and plant experiencing effect

### Diagnostic Ratios

| Ratio | What it measures | When it breaks |
|-------|-----------------|----------------|
| T_o / T_p | Estimator quality | Controller operates on state ≥1 plant-evolution old. Estimate is fiction. |
| T_u / T_p | Control viability | Action addresses a plant state that no longer exists. Oscillation risk. |
| T_s / T_p | Coordination viability | Timestamp-based coordination becomes ambiguous. Temporal fencing fails. |
| T_c / T_contract | Contract soundness | Temporal contracts (leases, TTLs, deadlines) rot silently. |

### Dominance Principle

The largest ratio determines the system's primary temporal failure mode. Diagnose the largest ratio first. Fixing the wrong layer is wasted effort.

## Existing Governor Coverage

### Direct correspondence (mechanism exists, ratio normalization absent)

| Paper 22 concept | Governor module(s) | What exists |
|---|---|---|
| Observation staleness | `drift.py`, `correlator_telemetry.py` | Temporal asymmetry defense, premise quarantine |
| Contract rot | `ttl.py` | Volatility classes, revalidation scheduling, recency decay |
| Retarded-state estimation | `regime.py`, `epistemic.py` | Regime detection from lagged signals, confidence decay |
| Coherence budgets | `boil.py`, `homeostat.py` | Exploration budgets, gain scheduling, dwell time enforcement |
| Freshness gating | `evidence_gate.py`, `gate_receipt.py` | Evidence staleness in custody scoring |
| Revalidation triggers | `auto_tuning.py`, `governed_activity.py` | Reset tracking, drift-gated retry, etag divergence |
| Timescale separation | `coupling.py` | Homeostat→Ultrastability deadband, accumulator |
| Temporal windows | `signals/envelope.py` | `window_start`/`window_end`, `emitted_at`, quality status |
| Synchronization / coordination | `quorum.py` | Δt stability windows, fingerprint gating |
| Overcorrection prevention | `scars.py` | Hysteresis — scars prevent oscillation |

### Partially present (concept exists, not framed as temporal failure)

| Paper 22 concept | What governor has | What's missing |
|---|---|---|
| Four-layer decomposition | Scattered across modules | No unified temporal failure taxonomy |
| Timescale ratio analysis | Individual absolute thresholds | No ratio relative to plant dynamics |
| "Which ratio exceeds critical first" | Regime detection does triage | Not framed as temporal dominance |
| Observation age as metadata | `emitted_at` on signals | Not systematic `measurement_age` propagated through pipeline |
| Four-timestamp model | Decision timestamps on receipts | Not event/observation/decision/effect as distinct fields |

### Genuinely absent

1. **Plant timescale (T_p) as a first-class parameter**
2. **Ratio-based threshold normalization**
3. **Dominant temporal failure mode classification**
4. **Actuation lag measurement** (delay between gate decision and agent compliance)
5. **Four-timestamp event schema** (event_time, observation_time, decision_time, effect_time)

## Design

### Phase A — Instrumentation

**A1: T_p estimation.** Estimate plant dynamics rate from observable signals:
- File change frequency (from `watch.py`, git history)
- Commit velocity (commits per unit time)
- Claim churn rate (from `claim_diff.py`)
- Evidence turnover (from `evidence_gate.py`)
- Signal emission rate (from `signal_store.py`)

T_p is the characteristic timescale of the fastest relevant change. Multiple estimators, conservative (shortest) wins. Windowed — T_p itself changes over time.

**A2: Measurement age.** Add `measurement_age_ms` (or `observed_at` + `event_at` pair) to:
- Signal envelopes (already have `emitted_at` and `window_end`, need `observed_at`)
- Gate receipts (already have `timestamp`, need `subject_observed_at`)
- Evidence bundles (when was the evidence actually gathered vs when was it attached)

Propagation rule: `measurement_age` at any node is max of all input measurement ages (conservative, like `max_sensitivity` in provenance labels).

**A3: Actuation lag probes.** Measure the delay between governor emitting a decision and the agent acting on it:
- Hook response time (pre-tool hook emit → agent tool execution start)
- Gate-to-compliance delay (gate blocks → agent acknowledges/retries)
- Requires cooperation from daemon or wrapper — instrument the round-trip

**A4: Four-timestamp model.** Where feasible, distinguish:
- `event_at`: when the thing actually happened (file changed, test ran)
- `observed_at`: when the governor observed/measured it
- `decided_at`: when the governor made a decision about it
- `effected_at`: when the decision took effect on the agent

Not all four are available everywhere. Schema should allow None for unknown timestamps. The point is to stop conflating them where they're distinct.

### Phase B — Derived Diagnostics

**B1: Ratio computation.** Given T_p from A1 and the four lag measurements:
```
observation_ratio = T_o / T_p
actuation_ratio = T_u / T_p
sync_ratio = T_s / T_p  (relevant in multi-agent / quorum)
divergence_ratio = T_c / T_contract  (relevant for TTL / lease contracts)
```

**B2: Dominant failure mode classification.** Identify which ratio is largest and classify:
- `observation_dominated`: stale state is the primary risk
- `actuation_dominated`: enforcement lag is the primary risk
- `sync_dominated`: coordination ambiguity is the primary risk
- `contract_dominated`: temporal contract rot is the primary risk
- `coherent`: all ratios below critical thresholds

This is a system-level readout — one interpretable regime statement from a pile of local signals.

**B3: Signal emission.** Emit as a signal envelope (observe-only, like all v2.4 signals):
- `TEMPORAL_DOMINANCE` signal with ratios, dominant mode, T_p estimate
- Feeds into signal plane for historical query and dashboard

### Phase C — Policy Integration

Feed ratio-aware thresholds into existing modules. The key move: thresholds become functions of T_p, not constants.

| Module | Current | With T_p |
|--------|---------|----------|
| `ttl.py` | Fixed volatility class TTLs | TTL scaled by T_p — fast-changing systems get shorter TTLs |
| `drift.py` | Fixed drift thresholds | Drift alarm when observation_ratio exceeds critical |
| `regime.py` | Fixed signal thresholds | Regime transitions gated by ratio exceedance |
| `boil.py` | Fixed dwell times | Dwell time proportional to T_p — fast plants need faster mode switches |
| `homeostat.py` | Fixed exploration budgets | Budget burn rate scaled by plant tempo |
| `quorum.py` | Fixed Δt stability windows | Stability window = f(T_s / T_p) |
| `scars.py` | Fixed stiffness decay | Annealing rate proportional to T_p |

**Important constraint:** Phase C is opt-in per module. Each module can consume T_p or ignore it. No big-bang rewrite. Existing absolute thresholds remain as fallback when T_p is unavailable.

### Phase D — Receipts and Reporting

- Gate receipts include temporal failure classification when relevant
- `governor regime status` reports dominant temporal failure mode
- Dashboard shows T_p estimate and ratio gauges
- Receipt explains *why* a threshold fired relative to plant tempo, not just that it fired

## Module Touchpoints

New module: `src/governor/tempo.py`
- `PlantTimescaleEstimator`: windowed T_p estimation from multiple sources
- `TemporalRatios`: dataclass with the four ratios + dominant mode
- `TemporalDominance`: enum (observation, actuation, sync, contract, coherent)
- `compute_ratios(t_p, t_o, t_u, t_s, t_c, t_contract) -> TemporalRatios`
- Signal builder for `TEMPORAL_DOMINANCE` envelope

Touched modules (Phase C, opt-in):
- `ttl.py`: accept optional T_p for scaled TTLs
- `drift.py`: accept optional T_p for ratio-based thresholds
- `regime.py`: consume TEMPORAL_DOMINANCE signal
- `boil.py`: scale dwell times by T_p
- `homeostat.py`: scale budget burn by T_p
- `quorum.py`: scale Δt windows by T_p
- `scars.py`: scale annealing by T_p

## Schema Changes

### Signal envelope (additive, non-breaking)
```python
# Optional fields on SignalEnvelope.values
"observed_at": str | None      # ISO 8601, when the measurement was taken
"event_at": str | None          # ISO 8601, when the underlying event occurred
"measurement_age_ms": float | None  # observed_at - event_at in ms
```

### Gate receipt (additive, non-breaking)
```python
# Optional fields on GateReceipt or timing fragment
"subject_observed_at": str | None   # when the subject was observed
"actuation_lag_ms": float | None    # decision → effect delay
"temporal_dominance": str | None    # dominant failure mode at decision time
```

## Invariants

1. **T_p is estimated, never asserted.** No agent provides T_p. Governor derives it from observable signals.
2. **Ratios are diagnostic, not gating (Phase A-B).** Observe-only until Phase C opts modules in.
3. **Absent T_p degrades to current behavior.** If T_p cannot be estimated, all modules use their existing absolute thresholds. No regression.
4. **measurement_age propagation is conservative.** Output measurement_age = max(input measurement_ages).
5. **Four timestamps allow None.** Not all four are knowable everywhere. The schema tolerates partial information.
6. **Dominant mode is the largest ratio, not a weighted blend.** No scalarization. Triage, not scoring.

## Relationship to Paper 22

Paper 22 provides: framework, definitions, justification, cross-domain transfer.
This gap spec provides: exact Governor deltas, module touchpoints, schema changes, rollout order.

Paper 22 is upstream theory. Governor is proof the problem is real. This spec bridges them.

> Governor already knows time matters. Paper 22 explains what kind of temporal failure is happening, why, and relative to what.

## Open Questions

1. **T_p estimation granularity.** One global T_p or per-scope T_p? A monorepo might have fast-changing frontend and stable backend. Per-scope is more accurate but more complex.
2. **Critical ratio thresholds.** What value of T_o/T_p constitutes "observation-dominated"? Paper 22 says ≥1, but operational systems may need earlier warning (0.5? 0.3?). Likely needs calibration from telemetry (Phase C2 calibration layer could help).
3. **Multi-agent T_p.** In multi-agent scenarios, each agent may be operating on a different plant timescale. The quorum needs the fastest T_p (most demanding) for its synchronization window.
4. **T_p for non-code domains.** Fiction governor, nonfiction governor — what is "plant timescale" for a manuscript? Probably chapter/scene evolution rate during active editing. Needs domain-specific estimators.
