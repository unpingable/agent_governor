# Gap Spec: Upstream Regime Detection (Δm Reclassification)

**Status:** proposed (v3 — do not build now)
**Affects:** regime detection, correlator telemetry
**Date:** 2026-03-31
**Origin:** cybernetic failure taxonomy — Δm reclassified from perception to transmission

## Problem

The taxonomy reclassified model drift (Δm) from a perception failure to a transmission failure — it's usually downstream of signal corruption (Δs) or observability failure (Δo), not an independent root cause. Currently Governor's regime detection is model-centric: it measures the model's behavior (tool churn, gain, fidelity) without looking upstream at signal health.

This means the regime detector can detect *that* the model is misbehaving, but not *why* — whether it's the model drifting independently or whether corrupted/missing signals are causing the model to miscalibrate.

## Proposed (v3)

Add upstream signal health as an input to regime detection:

- Signal completeness (are expected signals arriving?)
- Signal freshness (are signals stale?)
- Signal contradiction rate (are signals disagreeing with each other?)

If upstream signals are degraded, the regime classification should reflect "signal-degraded" rather than "model-unstable" — different diagnosis, different intervention.

## Why Not Now

Regime detection and the signal plane are both mature subsystems. Coupling them requires careful design to avoid circular dependencies (regime detection consuming signals that are themselves regime-dependent). This is architecture work, not a quick feature.

## Dependencies

- `regime.py` (RegimeDetector, RegimeSignals)
- `correlator_telemetry.py` (capture detection)
- `signals/` (signal plane)
