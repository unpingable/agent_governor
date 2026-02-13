# Scalar Collapse Gap Analysis

## What the Research Proved vs. What the Governor Has

```yaml
status: gap
relates_to:
  - scalar_collapse.py (CollapseDetector, CollapseSignals, CollapseReport)
  - github.com/unpingable/scalar (v0.3 — empirical regimes + analytic predictor)
blocking: nothing
priority: deferred
```

---

## Current State: `scalar_collapse.py`

The governor's CollapseDetector is a **runtime anomaly detector**. It watches
live telemetry windows and computes four signals:

| Signal | What it measures |
|--------|-----------------|
| `effective_dimension` | Rank of metric covariance matrix |
| `variance_concentration` | PC1 explained variance ratio |
| `action_entropy` | Shannon entropy of action distribution |
| `metric_agreement` | Mean pairwise correlation between metrics |

These feed a risk score (0.0-1.0) and a risk level (HEALTHY → WARNING →
ELEVATED → CRITICAL). The detector recommends actions: pass, warn,
freeze_tuning, inject_diversity.

This works. It catches collapse **as it happens** by watching the telemetry
darken. It's a smoke detector.

---

## What the Scalar Research Added

The scalar project (v0.3) ran controlled experiments on proxy-target divergence
under systematically varied conditions: dimensionality (D), observation window
(W), and noise level. Three findings that the governor doesn't have:

### 1. Analytic Regime Predictor

`predict_regime(D, W, noise)` computes whether a configuration is
stable/metastable/unstable **from parameters alone**, no simulation required.

The governor's detector is purely empirical — it needs telemetry samples before
it can say anything. The analytic predictor answers a different question:

> "Given this metric configuration, **will** it collapse?"

vs. the current:

> "Given this telemetry window, **is** it collapsing?"

**Gap:** Structural prediction before runtime. The governor could reject a
metric configuration at setup time if the analytic predictor says it's
structurally unstable.

### 2. Two-Mechanism Decomposition

The research found two distinct failure modes:

| Mode | Signature | D dependence | W dependence |
|------|-----------|-------------|-------------|
| **First-interval kill** | Collapse on first observation | D > D_crit | None (W irrelevant) |
| **Drift-cycle collapse** | Gradual metastable decay | D < D_crit | W matters |

The governor's detector doesn't distinguish these. It reports a single risk
score regardless of mechanism. Distinguishing them matters because:

- First-interval kill means the metric set is structurally broken. No amount
  of window tuning helps. The fix is fewer/different metrics.
- Drift-cycle collapse means the metric set is viable but the observation
  window is wrong. The fix is adjusting W, not D.

**Gap:** Mechanism-aware diagnostics. When the detector fires, it should say
*why* — "your metrics are over-dimensioned" vs. "your window is too short" —
not just "risk is high."

### 3. Policy Cost Frontier (κ)

The research produces a curve: for three intervention policies (dimension
reduction, window extension, noise injection), how much proxy fidelity do you
sacrifice for how much safety gain?

The governor currently has no concept of intervention cost. `CollapseAction`
says "freeze tuning" or "inject diversity" but doesn't quantify the tradeoff.
The κ frontier answers:

> "Reducing from 7 metrics to 4 costs you 12% proxy accuracy but moves you
> from CRITICAL to HEALTHY."

**Gap:** Cost-aware recommendations. Instead of "inject diversity," the
governor could say "here are three options ranked by cost/benefit."

---

## What Doesn't Need to Change

The existing runtime detector is fine as-is for its purpose. It's a live
telemetry monitor. The scalar research doesn't invalidate it — it extends it
with structural prediction and mechanism decomposition.

The runtime path stays:

```
telemetry → CollapseDetector.observe() → CollapseReport → action
```

The structural path (if built) would be:

```
metric config → predict_regime() → accept/reject/recommend before runtime
```

These are complementary, not competing.

---

## If Built: What Changes

### Minimal (tighten existing module)

Add to `scalar_collapse.py`:

1. **`predict_regime(metric_names, window_size, noise_estimate)`**
   - Pure function, no telemetry needed.
   - Returns regime classification + confidence.
   - Called at metric registration time, not at runtime.

2. **`classify_mechanism(report: CollapseReport)`**
   - Takes an existing CollapseReport.
   - Returns `"first_interval"` or `"drift_cycle"` based on signal patterns.
   - Adds a `mechanism` field to CollapseReport.
   - Enables targeted fix recommendations.

3. **`CollapseReport.recommended_fix`** (new field)
   - Instead of generic `CollapseAction`, provide mechanism-specific guidance:
     - First-interval: "Reduce metric count from D to D_crit"
     - Drift-cycle: "Extend window from W to W_min"

### Extended (cost frontier)

4. **`cost_frontier(metric_names, policies)`**
   - Returns ranked interventions with cost/benefit estimates.
   - Depends on κ computation from the scalar research.
   - This is heavier — requires porting the frontier computation.
   - Probably not worth it unless the governor is actively used for
     multi-metric governance tuning.

---

## Recommendation

**Don't build this yet.** The runtime detector works. The structural predictor
is a nice-to-have that matters when:

- Someone is configuring a new governor deployment and wants to know upfront
  if their metric set is viable.
- The detector fires and the operator needs to know *which* mechanism is
  causing it, not just that risk is high.

If those situations come up in practice, items 1-3 above are a clean,
small addition (~100-150 lines + tests). Item 4 is only worth it if cost-aware
recommendations actually change operator behavior.

The scalar research is cited in the paper. The findings are validated. The code
is at `github.com/unpingable/scalar` tag v0.3. The governor can absorb what it
needs when it needs it.
