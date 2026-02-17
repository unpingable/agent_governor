# Gap: predict_regime Preflight

**Branch:** v2.x
**Status:** gap (advisory)
**Depends on:** CALIBRATION_LAYER_GAP (for calibrated risk scores), REPLAY_HARNESS_GAP (for validation), SCALAR_COLLAPSE_GAP.md §1, regime.py, auto_tuning.py
**Build phase:** v2.4 (preflight as lint — last v2 item)

## The Problem

The regime detector is purely reactive — it watches telemetry windows and classifies after the fact. There's no way to ask "given this metric configuration, will it collapse?" before starting a session.

SCALAR_COLLAPSE_GAP.md §1 specifies the interface:

```python
predict_regime(metric_names, window_size, noise_estimate) → regime_classification
```

This gap spec tracks the implementation status and integration plan.

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| Full spec | SCALAR_COLLAPSE_GAP.md §1 | Interface, two failure modes, parametric sketch |
| CollapseDetector (runtime) | auto_tuning.py | Empirical detection: 4 signals, risk classification |
| RegimeDetector | regime.py | ELASTIC/WARM/DUCTILE/UNSTABLE from live signals |

## What Needs Building

### 1. Parametric Model

The spec identifies two failure modes:
1. **First-interval kill**: Collapse on first observation, D-dependent, W-irrelevant
2. **Drift-cycle collapse**: Gradual metastable decay, both D and W matter

The implementation needs a function mapping (D, W, noise) → {stable, metastable, unstable} with confidence. This is a pure function — no telemetry, no persistence.

### 2. Integration Points

- **Session start**: `governor session create` calls `predict_regime()` against the session's metric config. If unstable, warn (don't block).
- **Profile activation**: `governor profile use <name>` checks the profile's signal configuration.
- **Auto-tuning proposals**: `governor tune convergence propose` validates proposed parameter changes don't push into unstable regime.

### 3. Validation

Once deployed, compare `predict_regime()` output against `CollapseDetector` observations. If the predictor is wrong more than 20% of the time, the parametric model needs calibration data (which is why this is v2 — needs runtime observations first).

## Why Advisory

This is a static analysis tool. It tells you "this configuration looks fragile" before you run it. It doesn't gate anything — bad configurations still run, they just get a warning. The runtime detector is the enforcer.

## Build Estimate

~60 lines (pure function + tests) + ~20 lines CLI wiring. The SCALAR_COLLAPSE_GAP spec says "100-150 lines + tests" for items 1-3; this is item 1 only.

## Acceptance Criteria

1. `predict_regime(metric_names, window_size, noise_estimate)` returns regime + confidence
2. Called at session creation and profile activation (warning only)
3. Visible in `governor regime status --json` under `preflight` key
4. Tests: known-unstable configs (D>10, W<5) classified correctly
