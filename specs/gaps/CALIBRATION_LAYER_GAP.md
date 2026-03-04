# Gap: Calibration Layer — Normalizing Signals to Comparable Risk Scores

**Branch:** v2.x
**Status:** shipped (v2.5.0 — `signals/calibration_layer.py` + `signals/calibration_methods.py`; retained as design rationale per V2_4A_SPINE.md §8)
**Depends on:** REPLAY_HARNESS_GAP (validation), DETECTOR_INTEGRATION_SPEC.md, SELF_GOVERNANCE_SPEC.md (baselines), regime.py, correlator_telemetry.py
**Build phase:** v2.3 (make it measurable — build after replay harness)
**Blocks:** KAPPA_DIAL_GAP (hard), REGIME_CAPTURE_2D_GAP (hard)

## The Problem

The governor has ~15 independent signal sources (regime, correlator, drift, scope, evidence gate, etc.), each with its own scale, threshold semantics, and calibration assumptions. They don't talk to each other. When a new signal source is added, its thresholds are hand-tuned against the others.

This makes it impossible to:
1. Compare risk across subsystems ("is this drift signal more concerning than that scope violation?")
2. Combine signals without ad-hoc weighting
3. Validate that threshold changes in one subsystem don't break another's assumptions

## What Already Exists

| Component | Location | Calibration Method |
|-----------|----------|--------------------|
| Signal collapse (5 dims) | DETECTOR_INTEGRATION_SPEC §2 | Detector's own z-scores |
| Significance testing | SELF_GOVERNANCE_SPEC §2 | Cohen's d, CI width, min samples |
| Stratified baselines | SELF_GOVERNANCE_SPEC §3 | EWMA, per-task-class |
| Monotonic influence | DETECTOR_INTEGRATION_SPEC §4.2 | Only tighten, never loosen |
| Auto-tuning | auto_tuning.py | Threshold learning from distributions |
| Correlator K-vector | correlator_telemetry.py | Raw dimensions, never scalarized |

**The partial implementations that don't talk to each other:**
- Auto-tuning learns thresholds per-subsystem but doesn't cross-calibrate
- Detector has z-scores but the governor may re-normalize (open question in spec)
- Stratified baselines exist for rollback but not for signal comparison
- Monotonic influence rule is correct but doesn't help with inter-signal comparison

## What Needs Building

### 1. Risk Score Normalization

Each signal source emits a raw value. The calibration layer maps it to a common [0, 1] risk score:

```python
@dataclass
class CalibratedSignal:
    source: str                  # e.g. "drift.coherence_gradient"
    raw_value: float
    risk_score: float            # [0, 1], calibrated against baseline
    baseline_mean: float
    baseline_std: float
    regime: str                  # calibration is per-regime
    confidence: float            # how much data backs this calibration
```

The mapping is: `risk_score = Φ((raw - baseline_mean) / baseline_std)` where Φ is the normal CDF. This gives a probabilistic interpretation: "what fraction of normal observations are less extreme than this?"

### 2. Baseline Collection Per Regime

Different regimes have different baselines. ELASTIC drift looks different from DUCTILE drift. The calibration layer maintains per-regime baselines updated via EWMA:

```python
@dataclass
class SignalBaseline:
    source: str
    regime: str
    mean: float
    std: float
    sample_count: int
    last_updated: datetime
```

Baselines require minimum 50 observations before they're trusted. Until then, the raw signal is passed through uncalibrated (with a `confidence: 0.0` flag).

### 3. Cross-Signal Comparison

Once calibrated, signals can be compared and combined without ad-hoc weights:

```bash
governor calibration status          # show all signal baselines + confidence
governor calibration compare         # rank current signals by risk score
governor calibration drift           # show signals whose baselines are shifting
```

### 4. Detector Signal Merge

DETECTOR_INTEGRATION_SPEC leaves an open question: should the governor re-normalize detector signals? Answer: yes, using the calibration layer. Detector signals enter the same normalization pipeline as internal signals.

## Design Constraints

- **Monotonic influence preserved**: Calibration normalizes scale but doesn't change the DETECTOR_INTEGRATION rule that signals only tighten constraints.
- **No scalarization of K-vector**: The correlator K-vector stays 4D. Calibration normalizes each dimension independently.
- **Per-regime**: Baselines are per-regime. Regime transitions reset calibration confidence (but not the baselines — those decay via EWMA).
- **Fail-safe**: Missing calibration data → treat signal as maximum risk (same principle as detector crash → tighten).

## Build Estimate

~200 lines (normalization + baseline management + CLI) + ~120 tests. This is the foundation for v3 cross-domain integration.

## Acceptance Criteria

1. Every signal source can register with the calibration layer
2. Per-regime baselines computed and persisted (JSONL or SQLite)
3. `CalibratedSignal` includes raw, risk_score, baseline, confidence
4. `governor calibration status` shows all signals with calibration state
5. Minimum 50 observations before baseline is trusted
6. Missing calibration → risk_score = 1.0 (fail-safe)
