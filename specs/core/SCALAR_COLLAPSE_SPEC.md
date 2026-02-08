# Scalar Collapse Detection Specification

## Version 0.1 — Eigenstructure Evaporation in Governance Chains

```yaml
status: implemented
implemented: true
depends_on:
  - auto_tuning.py         # ThresholdTuner, Pareto analysis
  - convergence_tuning.py  # ConvergenceAnalyzer, ProposalStore
  - routing.py             # Router, ModelRegistry, adaptive routing
  - regime.py              # RegimeDetector, operational signals
  - telemetry.py           # TelemetryCollector, StructuredLogger
  - CONSTRAINT_COMPILER_SPEC.md
  - SPECTRAL_STABILITY_SPEC.md
blocking: safe auto-tuning, diversity-preserving optimization
estimated_scope: medium
source_paper: "03-scalar-reward-collapse (Beck 2025)"
```

### Companion to: SPECTRAL_STABILITY_SPEC.md, COMMITMENT_TRANSPORT_SPEC.md

---

## Executive Summary

Paper 03 (Scalar Reward Collapse) proves that closed-loop optimization via scalar reward causes **inevitable** exponential decay of non-maximal modes — this is mathematical necessity, not a design flaw. The governor's `auto_tuning.py` already uses Pareto analysis to avoid single-metric optimization, but does not detect when governance chains **secretly converge** to scalar behavior despite multi-objective framing.

The Scalar Collapse Detector monitors the effective dimensionality of the governor's decision space over time. When metrics that should be independent start moving together, when action distributions narrow, when "everything improves at once" — the detector flags eigenstructure evaporation before the system collapses to a single-metric cult.

**Core insight**: Scalar collapse looks like improvement. Every dashboard metric goes up. The failure is invisible until the suppressed modes matter — and by then, recovery requires exogenous forcing, not tuning.

---

## 1. The Problem

### 1.1 Where Scalar Collapse Can Occur

| Subsystem | Scalar Trap | Consequence |
|-----------|------------|-------------|
| `auto_tuning.py` | Threshold suggestions optimize for approval rate | Security/evidence thresholds erode because approvals are "good" |
| `convergence_tuning.py` | Convergence proposals optimize for convergence speed | Anchor diversity drops; everything converges to one style |
| `routing.py` | Model selection optimizes for latency or cost | Capability diversity collapses; one model handles everything |
| `boil.py` | Control mode selection optimizes for throughput | Safety margins erode; system runs hot |
| `regime.py` | Regime signals optimize for stability | System avoids WARM/DUCTILE by suppressing signal diversity |
| Profile selection | Usage patterns converge to one profile | Governance becomes homogeneous; situational adaptation lost |

### 1.2 The Eigenvalue Decay Mechanism

From Paper 03, Lemma 2.1: under multiplicative reweighting T(p) = p·e^{ηr(x)}/Z, non-maximal modes decay as p_t(x) ∝ e^{-ηtΔr}. Applied to governance:

- Each tuning cycle acts as T: amplifies what "worked," suppresses what didn't
- "Worked" is measured by some metric (even if the system claims to be multi-objective)
- Over cycles, the metric that dominates the tuning signal eliminates the others
- Result: the system converges to a fixed point concentrated on the reward maximum

This is Corollary 2.7 (Irreversibility): the same operator T cannot restore suppressed modes. Once diversity is lost, only exogenous forcing (new constraints, manual intervention) can recover it.

---

## 2. The Solution

### 2.1 Detection Signals

Four practical proxies for eigenstructure evaporation, computed from telemetry history:

```python
@dataclass
class CollapseSignals:
    """Proxy signals for scalar collapse."""
    effective_dimension: float     # Rank of metric covariance matrix
    variance_concentration: float  # PC1 explained variance ratio (0.0–1.0)
    action_entropy: float          # Entropy of action distribution (approvals, rejections, modes)
    metric_agreement: float        # Mean pairwise correlation between metrics (0.0–1.0)
```

#### 2.1.1 Effective Dimension

Track the metric vector per governance decision (approval rate, evidence quality, convergence speed, security score, etc.). Compute the covariance matrix over a sliding window. The effective dimension is the number of eigenvalues above a noise threshold.

- **Healthy**: effective_dimension ≈ number of tracked metrics (5-8)
- **Warning**: effective_dimension drops below half of tracked metrics
- **Collapse**: effective_dimension ≈ 1 (all metrics move together)

#### 2.1.2 Variance Concentration

PCA on the metric covariance matrix. If PC1 explains > 70% of variance, the system is effectively scalar — one hidden dimension drives all visible metrics.

#### 2.1.3 Action Entropy

Measure the distribution of governance actions (approve, reject, require-review, escalate, override). Compute Shannon entropy. Collapse manifests as entropy approaching 0 (system always takes the same action).

#### 2.1.4 Metric Agreement

Compute pairwise Pearson correlation between all tracked metrics. If metrics that should be independent (e.g., security score and convergence speed) become highly correlated, something is forcing them onto the same axis.

### 2.2 Collapse Risk Score

```python
@dataclass
class CollapseReport:
    """Aggregate collapse detection result."""
    signals: CollapseSignals
    risk_score: float              # 0.0 (healthy) to 1.0 (collapsed)
    dominant_metric: str | None    # Which metric is eating the others
    suppressed_modes: list[str]    # Metrics losing independent variance
    window_turns: int              # Analysis window size
    content_hash: str              # For receipts

def compute_collapse_risk(signals: CollapseSignals) -> float:
    """
    Weighted combination of collapse signals.

    risk = w1 * (1 - dim/max_dim) + w2 * variance_conc + w3 * (1 - action_entropy/max_entropy) + w4 * metric_agreement
    """
```

### 2.3 Detection Function

```python
def detect_collapse(
    telemetry_window: list[TelemetryEvent],
    metric_names: list[str],
    window_size: int = 50,
) -> CollapseReport:
    """
    Analyze recent governance telemetry for scalar collapse.

    Pure function. Reads telemetry, computes signals, produces report.
    No side effects. No mutations.
    """
```

---

## 3. Gating Behavior

### 3.1 Response Actions

| Risk Score | Action |
|-----------|--------|
| < 0.3 | Pass — healthy diversity |
| 0.3–0.5 | Warn — "effective dimension declining; check auto-tuning" |
| 0.5–0.7 | Freeze auto-tuning. Require multi-objective justification for threshold changes. |
| > 0.7 | Freeze auto-tuning + inject diversity constraints. Alert: "governance converging to scalar behavior." |

### 3.2 Diversity Injection

When collapse risk exceeds 0.7, the detector recommends (or enforces, in strict mode):

- **Widen exploration budget** — force `homeostat.py` to increase exploration allocation
- **Metric independence constraint** — "no single metric may account for > 50% of threshold adjustment weight"
- **Action diversity floor** — require minimum entropy in governance action distribution
- **Suppressed mode protection** — temporarily exempt suppressed metrics from auto-tuning (prevent further decay)

### 3.3 Irreversibility Warning

Per Corollary 2.7: if collapse is advanced (risk > 0.8 sustained over 20+ turns), emit a specific warning:

```
⚠ SCALAR COLLAPSE: Irreversibility threshold approaching.
  Dominant metric: approval_rate (PC1 = 83% variance)
  Suppressed: security_score, evidence_quality, diversity_index
  Recovery requires exogenous forcing (manual constraint injection),
  not parameter tuning. Auto-tuning is frozen.
```

---

## 4. Integration Points

### 4.1 Auto-Tuning

`auto_tuning.py` threshold proposals are checked against collapse signals before application:

```python
# Before applying threshold suggestion
report = detect_collapse(recent_telemetry, metric_names)
if report.risk_score > 0.5:
    reject_proposal("Collapse risk too high; threshold change would reduce diversity")
```

### 4.2 Convergence Tuning

`convergence_tuning.py` proposals are similarly gated. If the convergence analyzer is producing proposals that increase metric agreement, the collapse detector flags them.

### 4.3 Routing

When `routing.py` model selection converges to always choosing the same model, the collapse detector flags this as action entropy loss. Routing must maintain model diversity above a floor.

### 4.4 Regime Detection

Collapse signals feed into `regime.py` as a new signal class. A collapsing governance system may appear ELASTIC (all metrics "good") while actually being UNSTABLE (no independent variance = no self-correction capacity).

### 4.5 Telemetry

Emit `COLLAPSE_CHECK` events with risk score, effective dimension, and suppressed modes. Enables trend analysis and retrospective auditing.

### 4.6 Constraint Compiler

The compiled constraint block includes a collapse annotation when risk is elevated:

```
DIVERSITY: collapse_risk=0.45 (WARN — effective_dimension=3/7)
  Dominant: approval_rate. Declining: security_score, evidence_quality.
```

---

## 5. CLI Surface

```bash
# Check current collapse risk
governor collapse status

# Show metric covariance analysis
governor collapse analyze

# Show suppressed modes
governor collapse modes

# Show collapse history
governor collapse history

# Force diversity injection
governor collapse inject --metric security_score
```

---

## 6. Design Constraints

1. **Telemetry-dependent.** Requires sufficient governance history (minimum ~50 decisions) for meaningful covariance estimation. Reports "insufficient data" below threshold.
2. **Pure detection.** The detector reads telemetry and produces a report. Gating/injection is the caller's responsibility (auto-tuning, convergence tuner, etc.).
3. **No numpy required.** Covariance and PCA can be computed with pure Python for small metric vectors (5-10 dimensions). Numpy optional for performance.
4. **Monotonic response.** Higher collapse risk can only tighten constraints (freeze tuning, inject diversity), never loosen them.
5. **Irreversibility-aware.** The detector explicitly warns when collapse has progressed beyond the point where parameter tuning can recover. This prevents the "just tune harder" anti-pattern.

---

## 7. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `SPECTRAL_STABILITY_SPEC.md` | Spectral instability and scalar collapse are complementary failure modes (topology vs. optimization) |
| `CONSTRAINT_COMPILER_SPEC.md` | Collapse annotation in compiled block; diversity constraints as projected constraints |
| `COMMITMENT_TRANSPORT_SPEC.md` | Compression-induced commitment shear accelerates collapse (fewer constraints = narrower objective) |
| `DETECTOR_INTEGRATION_SPEC.md` | Detector coherence scores could become a collapse-resistant metric (external, not auto-tuned) |

---

## 8. Open Questions

1. **Window size.** How many governance decisions constitute a meaningful window for covariance estimation? Too short = noisy, too long = misses rapid collapse. Candidate: adaptive window based on decision rate.

2. **Which metrics to track.** The metric vector needs to be defined per deployment. Should there be a standard set (approval rate, evidence quality, convergence speed, security score, action diversity, constraint count, override rate)?

3. **Exogenous forcing mechanism.** When collapse is irreversible via tuning, what does "exogenous forcing" look like concretely? Candidate: human-injected anchors, mandatory profile rotation, forced exploration epochs.

4. **Relationship to regime.** A collapsing system in ELASTIC regime is a specific pathology — "false stability." Should this be a named regime state (COLLAPSED) or a modifier on existing regimes?
