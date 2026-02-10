# Spectral Stability Specification

## Version 0.1 — Coupling Matrix Verification for Governance Topology

```yaml
status: implemented
implemented: true
depends_on:
  - regime.py            # RegimeDetector, RegimeSignals
  - coupling.py          # GovernorCoupling, Homeostat→Ultrastability
  - ultrastability.py    # UltrastabilityController, ParameterSpec
  - homeostat.py         # Homeostat, ExplorationBudget
  - execution.py         # ExecutionBudget, ExecutionState
  - CONSTRAINT_COMPILER_SPEC.md
blocking: safe autonomy configuration
estimated_scope: medium
source_paper: "01-coherence-criterion (Beck 2025)"
```

### Companion to: CONSTRAINT_COMPILER_SPEC.md, DETECTOR_INTEGRATION_SPEC.md

---

## Executive Summary

The governor manages a multi-layer control hierarchy: agent proposals (fast) → governor verification (medium) → human review (slow) → policy updates (slowest). Paper 01 (Coherence Criterion) proves that stability of such hierarchies requires ρ(M) < 1, where M is the coupling matrix of inter-layer feedback. Violations guarantee runaway — either rigidity (the system locks up) or acceleration (oscillation → chaos).

The Spectral Stability Gate computes ρ(M) from declared rates, latencies, and feedback strengths, and blocks autonomy configurations that are unstable by construction. This is a preflight check — it catches bad topology before it produces bad behavior.

**Core insight**: Culture cannot stabilize an unstable topology. If ρ(M) ≥ 1, no amount of "be careful" prevents runaway. The gate makes this a hard constraint.

---

## 1. The Problem

### 1.1 Governance Layers Have Timescales

| Layer | Typical Rate | Role |
|-------|-------------|------|
| Agent proposals | Seconds | Generate patches, suggest changes |
| Governor verification | Seconds–minutes | Check claims, produce receipts |
| Human review | Minutes–hours | Approve, reject, override |
| Policy updates | Hours–days | Change profiles, update anchors |
| Architecture decisions | Days–weeks | Modify spines, change invariants |

### 1.2 Coupling Creates Feedback

Each layer influences adjacent layers:
- Agent proposal rate increases → governor queue grows → verification latency increases → agent retries increase → proposal rate increases further (positive feedback)
- Human review backlog → auto-approval pressure → governance weakening → more violations → more review needed (positive feedback)
- Strict policy → high rejection rate → agent frustration → override requests → policy erosion (positive feedback)

### 1.3 When Feedback Exceeds Unity

Paper 01 proves: if the product of feedback gains around any loop exceeds 1 (ρ(M) ≥ 1), the system is **structurally unstable**. No tuning of individual parameters can fix it — only topology changes (adding buffer layers, reducing coupling, changing feedback signs).

The governor currently has regime detection (`regime.py`) that observes *symptoms* of instability. It does not have a *predictive* check that catches unstable configurations before they run.

---

## 2. The Solution

### 2.1 Coupling Matrix Construction

Build M from the governance topology's declared rates and feedback strengths:

```python
@dataclass
class GovernanceLayer:
    """A layer in the governance hierarchy."""
    name: str
    rate: float              # Actions per unit time (proposals/sec, reviews/hour, etc.)
    latency: float           # Processing time per action
    capacity: float          # Max throughput before queuing
    feedback_up: float       # Influence on layer above (0.0–1.0)
    feedback_down: float     # Influence on layer below (0.0–1.0)

@dataclass
class CouplingMatrix:
    """Inter-layer feedback matrix."""
    layers: list[GovernanceLayer]
    matrix: list[list[float]]  # M[i][j] = feedback strength from layer j to layer i
    spectral_radius: float     # ρ(M) — must be < 1
    dominant_eigenvalue: complex
    sensitivity: dict[str, float]  # Per-edge sensitivity (∂ρ/∂M_ij)
```

### 2.2 Spectral Radius Computation

```python
def compute_stability(layers: list[GovernanceLayer]) -> StabilityReport:
    """
    Build coupling matrix from layer declarations and compute ρ(M).

    Uses numpy for eigenvalue computation — the only numerical
    dependency. No torch, no ML.
    """
```

The matrix M is constructed from:
- **Diagonal**: layer self-feedback (retry rates, queue-driven acceleration)
- **Off-diagonal**: inter-layer coupling (rejection → retry, backlog → pressure, override → erosion)

Feedback strengths are estimated from:
- Declared rates and capacities
- Historical telemetry (if available)
- Profile defaults (conservative estimates for new configurations)

### 2.3 Stability Report

```python
@dataclass
class StabilityReport:
    """Preflight stability check result."""
    stable: bool                    # ρ(M) < 1
    spectral_radius: float          # ρ(M)
    margin: float                   # 1 - ρ(M) — stability margin
    dominant_mode: str              # Which feedback loop dominates
    hotspots: list[CouplingHotspot] # Edges closest to instability
    adjacency_violations: list[str] # Layer pairs with κ > 100
    recommendations: list[str]      # Suggested mitigations

@dataclass
class CouplingHotspot:
    """An edge in the coupling matrix close to instability."""
    from_layer: str
    to_layer: str
    strength: float
    sensitivity: float  # How much ρ changes if this edge changes
    mitigation: str     # Suggested fix
```

### 2.4 Adjacency Enforcement

Paper 01's Temporal Adjacency Principle: adjacent layers cannot exceed ~100:1 timescale ratio (κ < 100). Violations mean the layers are effectively decoupled — the fast layer can complete entire cycles before the slow layer observes one state change.

```python
def check_adjacency(layers: list[GovernanceLayer]) -> list[AdjacencyViolation]:
    """Flag layer pairs where rate ratio > 100."""
```

---

## 3. Gating Behavior

### 3.1 Preflight Check

The stability gate runs before enabling or changing autonomy configurations:

| Trigger | What's Checked |
|---------|---------------|
| `governor profile use <name>` | New profile's implied rates/feedback vs current topology |
| `governor autonomous run` | Execution loop rates vs review capacity |
| `governor boil set <mode>` | Mode's control gains vs layer coupling |
| `governor explore enter <ctx>` | Exploration budget vs evidence accumulation rate |

### 3.2 Gating Rules

| ρ(M) | Margin | Action |
|-------|--------|--------|
| < 0.7 | > 0.3 | Pass — stable with comfortable margin |
| 0.7–0.9 | 0.1–0.3 | Warn — stable but approaching limit. Show hotspots. |
| 0.9–1.0 | < 0.1 | Block unless override warrant. Show dominant mode + mitigation. |
| ≥ 1.0 | ≤ 0 | **Hard block** — unstable by construction. No override. |

ρ(M) ≥ 1.0 is a hard block because instability is a mathematical guarantee, not a risk estimate. No warrant can override physics.

### 3.3 Five Kinetic Regions

Map ρ(M) and adjacency metrics to the five kinetic regions from Paper 05 (Control Laws):

| Region | Condition | Governor State |
|--------|-----------|---------------|
| I — Coherent | ρ(M) < 0.7, no adjacency violations | Normal operation |
| II — Strained | 0.7 ≤ ρ(M) < 0.9 | Regime: WARM |
| III — Metastable | 0.9 ≤ ρ(M) < 1.0 | Regime: DUCTILE. Warn. |
| IV — Flicker | ρ(M) ≈ 1.0, oscillation detected | Regime: UNSTABLE. Block. |
| V — Decoherent | ρ(M) > 1.0 or adjacency κ > 100 | Hard block. Topology change required. |

---

## 4. Integration Points

### 4.1 Regime Detection

`regime.py` currently uses signals (tool gain, verification rate, etc.) to classify operational regime. The spectral stability gate provides a *structural* signal — ρ(M) feeds directly into regime classification as a leading indicator (predicts instability before symptoms appear).

### 4.2 Constraint Compiler

The compiled constraint block (CONSTRAINT_COMPILER_SPEC.md) includes a stability annotation:

```
TOPOLOGY: ρ(M) = 0.73 (Region II — Strained)
HOTSPOT: agent_proposal → governor_verify (sensitivity: 0.4)
```

This tells the executor "the system is operating near its stability boundary; produce fewer, higher-quality proposals rather than many speculative ones."

### 4.3 Telemetry

Emit `STABILITY_CHECK` events with ρ(M), margin, region, and hotspots. Enables trend analysis: "stability margin decreasing over time" = topology slowly drifting toward instability.

### 4.4 Auto-Tuning

`auto_tuning.py` proposes threshold changes. The stability gate validates that proposed changes don't push ρ(M) toward 1.0. If they do, the proposal is flagged with a stability warning.

---

## 5. CLI Surface

```bash
# Preflight stability check
governor stability check

# Check with specific profile
governor stability check --profile production

# Show coupling matrix details
governor stability matrix

# Show hotspots and recommendations
governor stability hotspots

# Show region classification
governor stability region
```

---

## 6. Design Constraints

1. **Preflight, not runtime.** The gate checks topology declarations, not live behavior. Live behavior monitoring is regime detection's job.
2. **Conservative defaults.** If feedback strengths are unknown, assume worst-case (high coupling). Overestimating instability is safe; underestimating is not.
3. **Minimal numerical dependency.** Uses numpy for eigenvalue computation. No torch, no ML, no optimization.
4. **Hard block at ρ ≥ 1.** No override, no warrant, no exception. Unstable topology is not a policy choice — it's a mathematical guarantee of failure.

---

## 7. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `CONSTRAINT_COMPILER_SPEC.md` | Stability annotation in compiled constraint block |
| `DETECTOR_INTEGRATION_SPEC.md` | Detector signal quality modulates coupling estimates |
| `COMMITMENT_TRANSPORT_SPEC.md` | Compression shear interacts with layer coupling (lossy summaries increase effective Δt) |
| `AG2_TEMPORAL_ATTACK_SURFACE_SPEC.md` | Race windows correlate with adjacency violations |

---

## 8. Open Questions

1. **Empirical coupling estimation.** How to estimate M entries from telemetry when no explicit rates are declared? Candidate: measure proposal-to-verification turnaround times and queue depths over a calibration window.

2. **Dynamic topology.** The coupling matrix changes as the governor's configuration changes (new profiles, new agents, different review cadence). How often should ρ(M) be recomputed? Candidate: on every configuration change + periodic background check.

3. **Numpy dependency.** The governor currently has no numpy dependency. Is eigenvalue computation worth the dependency, or should we use a power iteration approximation (slower convergence but pure Python)?
