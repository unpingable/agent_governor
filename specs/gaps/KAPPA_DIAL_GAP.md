# Gap: κ Dial — Tunable Aggressiveness Backed by Cost Curve

**Branch:** v3.x
**Status:** gap (operator-facing)
**Depends on:** CALIBRATION_LAYER_GAP (hard), REPLAY_HARNESS_GAP (hard — cost curve needs backtesting), SCALAR_COLLAPSE_GAP.md §3, auto_tuning.py
**Build phase:** v3.1 (grounded policy knobs)

## The Problem

The governor's aggressiveness (how readily it blocks, how tight thresholds are) is currently set by profile presets and individual parameter tuning. There's no single "how aggressive should I be?" control, and more importantly, there's no cost model showing what you pay for each level of aggressiveness.

SCALAR_COLLAPSE_GAP.md §3 specifies the policy cost frontier concept: "Reducing from 7 metrics to 4 costs you 12% proxy accuracy but moves you from CRITICAL to HEALTHY." This gap spec extends that from metric configuration to overall governance aggressiveness.

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| Policy cost frontier concept | SCALAR_COLLAPSE_GAP.md §3 | Metric reduction tradeoffs |
| CollapseAction | auto_tuning.py | "Freeze tuning" / "inject diversity" — no cost quantification |
| Config profiles | profiles.py | Named presets (strict, permissive, research, production) |
| Boil control | boil.py | Named presets with dwell time (GREEN_TEA → BOIL) |
| Operating envelopes | envelopes.py | strict vs exploratory — binary, no gradient |

**What's missing**: A continuous aggressiveness dial with a cost curve showing the tradeoff.

## What Needs Building

### 1. Cost Model

For each governance parameter that affects blocking rate, compute the marginal cost of tightening:

```python
@dataclass
class AggressivenessCost:
    parameter: str                    # e.g. "evidence_gate.hard_threshold"
    current_value: float
    proposed_value: float
    estimated_block_rate_delta: float  # additional blocks per 100 claims
    estimated_false_positive_delta: float  # additional false blocks per 100 claims
    confidence: float                 # based on replay/historical data
```

The cost curve is: `Σ(estimated_block_rate_delta)` vs `Σ(estimated_false_positive_delta)` across all parameters.

### 2. κ as a Single Scalar

κ ∈ [0, 1] maps to a point on the cost curve:
- κ = 0: maximally permissive (block only on hard evidence)
- κ = 0.5: balanced (default)
- κ = 1.0: maximally aggressive (block on any suspicion)

Internally, κ maps to a vector of parameter values via the cost curve. The operator sees one dial; the governor adjusts multiple parameters.

### 3. Operator Interface

```bash
governor kappa                        # show current κ + cost curve summary
governor kappa set 0.7                # tighten governance
governor kappa set 0.3 --simulate     # show what would change without applying
governor kappa curve                  # show full cost curve (block rate vs false positive rate)
governor kappa history                # show κ changes over time
```

### 4. Cost Curve Estimation

The cost curve requires historical data. Sources:
- **Replay harness** (REPLAY_HARNESS_GAP.md): replay past runs with different κ → compute block/false-positive rates
- **σ-rate** (SIGMA_RATE_GAP.md): higher κ should reduce σ; if it doesn't, the cost model is wrong
- **Auto-tuning telemetry**: threshold changes and their observed effects

Without historical data, the cost curve is estimated from parameter ranges and domain knowledge. It improves as replay data accumulates.

## Why v3

κ requires:
1. Calibration layer (v2) — signals must be on comparable scales
2. Replay harness (v2) — cost curve needs backtesting data
3. σ-rate (v2) — validation that aggressiveness actually reduces divergence

Building κ without these foundations means guessing the cost curve. v3 has the data.

## Relationship to Boil Control

Boil control is discrete presets (GREEN_TEA, OOLONG, BOIL). κ is continuous. They can coexist: boil presets map to κ ranges, and κ provides finer-grained control within a preset.

## Build Estimate

~150 lines (cost model + CLI) + ~100 tests. Depends heavily on replay harness quality.

## Acceptance Criteria

1. κ ∈ [0, 1] maps to governance parameter vector
2. Cost curve computed from replay data (or estimated from defaults)
3. `governor kappa set` changes aggressiveness atomically
4. `governor kappa --simulate` shows projected impact without applying
5. Cost curve includes block rate and estimated false positive rate
6. κ changes produce gate receipts
