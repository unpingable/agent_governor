# Gap: Capture Self-Diagnostic

**Branch:** v2.x
**Status:** gap (warn-first)
**Depends on:** EXPOSURE_PROXY_GAP (hard), SILENT_SUPPRESSION_GAP (hard), SIGMA_RATE_GAP (soft), correlator_telemetry.py, evidence_gate.py
**Build phase:** v2.2 (after instrumentation spine)

## The Problem

If the governor is captured (its policy shaped by the model it governs), its contradiction rate should approach zero under sustained exposure — not because the model got better, but because the governor stopped catching things.

This is Prop 5.3 inversion from the correlator spec: "generated contradiction suppression." The correlator tracks it as one of four capture indicators, but only emits a regime flag. There's no self-diagnostic that directly answers: "is my contradiction rate suspiciously low given my exposure level?"

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| Prop 5.3 (contradiction suppression) | correlator_telemetry.py | Indicator: is contradiction rate declining under exposure? |
| K-vector Authority dimension | correlator_telemetry.py | High authority + declining fidelity = capture signal |
| Capture regime flags | correlator_telemetry.py | CAPTURED/SHEAR/DEGRADED classification |
| Evidence Gate contradictions | evidence_gate.py | Contradictions detected per-check but not trended |

## What's Missing

### 1. Contradiction Trend Monitor

The correlator checks "is contradiction rate declining under exposure" but uses consecutive-window hysteresis, which is coarse. Need a proper trend test:

```python
@dataclass
class ContradictionTrend:
    window_contradiction_rates: list[float]  # last N windows
    exposure_level: float                     # cumulative model-turns
    slope: float                              # linear regression slope
    is_suspicious: bool                       # slope < threshold AND exposure > minimum
    confidence: float                         # how certain we are about the slope
```

**Suspicious** = slope is negative (contradictions declining) while exposure is increasing. This is the "too quiet" signal.

### 2. Exposure-Adjusted Expectation

Raw contradiction rate is meaningless without an exposure model. If the model is generating fewer claims, lower contradictions are expected. Need:

```
expected_contradiction_rate = f(exposure_level, claim_volume, baseline_σ)
actual_vs_expected = actual_σ / expected_σ
```

When `actual_vs_expected < 0.3` for sustained windows → warn.

### 3. Warning (Not Gating)

In v2, this is advisory. The self-diagnostic surfaces in:
- `governor correlator status` output (new `self_diagnostic` section)
- Dashboard warning banner when suspicious
- Telemetry event: `CAPTURE_SELF_DIAGNOSTIC` with severity WARN

It does NOT block claims, change regime, or freeze parameters. The human decides what to do.

## Why Not Just Use the Correlator?

The correlator is a **regime classifier** — it maps 4 indicators to a state label. The self-diagnostic is a **specific hypothesis test**: "is my contradiction detector being silenced?" The correlator uses the output of this test as one input; the test itself needs to be more rigorous than a consecutive-window check.

## Relationship to σ-rate

σ-rate (SIGMA_RATE_GAP.md) measures the divergence. This spec monitors the **trend** of σ-rate under exposure. If σ-rate is the thermometer, this is the "thermometer health check."

## Build Estimate

~100 lines (trend monitor + exposure model) + ~30 lines dashboard/CLI wiring + ~50 tests.

## Acceptance Criteria

1. `ContradictionTrend` computed per correlator observation cycle
2. `is_suspicious` fires when slope < -0.02/window AND exposure > 200 turns
3. Warning emitted as telemetry event (never blocks)
4. Visible in `governor correlator status --json`
5. Tests: synthetic declining-rate series triggers warning; flat series does not
