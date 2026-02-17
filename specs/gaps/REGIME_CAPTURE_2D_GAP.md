# Gap: Regime × Capture — Orthogonal Health Axes

**Branch:** v3.x
**Status:** gap (conceptual + dashboard)
**Depends on:** CALIBRATION_LAYER_GAP (hard — axes must be on comparable scale), regime.py, correlator_telemetry.py
**Build phase:** v3.2 (operator surface)

## The Problem

Regime (ELASTIC/WARM/DUCTILE/UNSTABLE) and capture state (NOMINAL/SHEAR/CAPTURED/DEGRADED) are currently independent classifications. But they interact: a system can be operationally stable (ELASTIC) but epistemically compromised (CAPTURED), or operationally stressed (DUCTILE) but epistemically sound (NOMINAL).

The current dashboard shows them separately. There's no combined health view that answers: "where am I in the stability × integrity space?"

## What Already Exists

| Component | Location | Axis |
|-----------|----------|------|
| RegimeDetector | regime.py | Operational stability: ELASTIC → UNSTABLE |
| Correlator regime | correlator_telemetry.py | Epistemic integrity: NOMINAL → CAPTURED |
| Dashboard | telemetry dashboard | Shows each separately |
| K-vector | correlator_telemetry.py | 4D, never scalarized (Throughput, Fidelity, Authority, Cost) |

## What Needs Building

### 1. 2D Health Map

A 4×4 matrix of (regime, capture) states with distinct operational meanings:

```
                    NOMINAL     SHEAR       CAPTURED    DEGRADED
ELASTIC             GREEN       YELLOW      RED         ORANGE
WARM                YELLOW      ORANGE      RED         RED
DUCTILE             ORANGE      RED         RED         RED
UNSTABLE            RED         RED         RED         RED
```

Each cell has a specific interpretation:
- **ELASTIC × NOMINAL**: Healthy — governor working as designed
- **ELASTIC × CAPTURED**: Dangerous — looks healthy but governor is compromised
- **WARM × NOMINAL**: Expected under load — governor stressed but honest
- **DUCTILE × SHEAR**: Crisis — governor stressed AND losing epistemic ground

### 2. Transition Semantics

Transitions between cells are directional and have different urgency:
- Moving right (toward CAPTURED) is always more urgent than moving down (toward UNSTABLE)
- Capture under ELASTIC is more dangerous than instability under NOMINAL (the captured system looks fine)
- Recovery: must move left (epistemic) before moving up (operational) — restore integrity before restoring throughput

### 3. Dashboard Visualization

The 2D map replaces the separate regime/capture displays:
- Current position highlighted
- Historical trajectory shown as a path through the grid
- Color intensity reflects dwell time in each cell

### 4. Alert Escalation

Combine the two axes into a single alert level:

```python
def combined_alert(regime: Regime, capture: CaptureState) -> AlertLevel:
    # Capture dominates: CAPTURED in any regime is CRITICAL
    if capture == CAPTURED:
        return CRITICAL
    # ELASTIC × NOMINAL is the only GREEN
    if regime == ELASTIC and capture == NOMINAL:
        return GREEN
    # Capture + stress compounds
    severity = regime_severity[regime] + capture_severity[capture]
    return AlertLevel.from_severity(severity)
```

## Why v3

- v2 ships the individual axes (regime detector + correlator)
- v2 ships calibration layer (so signals are comparable)
- v3 combines them into a unified health model

Building this before calibration means the axes aren't on comparable scales, so the 2D map's thresholds would be arbitrary.

## Why Capture Dominates

A captured system in ELASTIC regime is the worst outcome: it looks healthy by every operational metric, but its constraints have been shaped by the model it governs. Instability is visible; capture is not. The 2D map makes this asymmetry explicit.

## Build Estimate

~100 lines (2D health model + alert escalation) + ~80 lines dashboard rendering + ~60 tests.

## Acceptance Criteria

1. 4×4 (regime, capture) health matrix defined with per-cell semantics
2. Combined alert level computed from both axes
3. Capture dominates: any CAPTURED state → CRITICAL regardless of regime
4. Dashboard shows 2D map with current position + historical trajectory
5. Recovery ordering enforced: epistemic recovery before operational recovery
6. Transition events emitted as telemetry
