# Agent Governor 3.0 Specification: Coherent Self-Dogfooding

```yaml
status: planning (deferred — requires 2.0 complete)
layer: 3.0
depends_on: [all 2.0 specs, all 2.1 specs]
prerequisite: stable observability, deterministic replay, provenance discipline
```

## Review Notes (Address Before Implementation)

Eight hardening items identified by external review:

1. **Define violation probability measurement.** Add estimator (empirical rate + Wilson/Clopper-Pearson upper bound), define what counts as a "trial" per invariant. Without this, δ/ε are vibes.
2. **Fail-closed logging.** Missing telemetry = violation amplifier. Log volume drop → M7 drops. Missing provenance → unknown_cause=true. Schema mismatch → stricter regime.
3. **Scope metric rotation.** Evaluation suite frozen per version (never rotated within). Rotation only for live monitoring or future suite versions. Deterministic replay must not be undermined.
4. **Apply Gate trust boundaries.** Treat config_patch.json and test_results as untrusted. Treat events.jsonl as adversarial input. Content-address traces + hash-pin suite (prevent optimizer training on grader).
5. **Bounded step norm.** Use L∞ bounds per parameter group (already have max_weight_change, max_threshold_change). Monotone constraints on safety knobs (S7 caps tighten automatically, cannot loosen without holdout win).
6. **Liveness under LOCKED.** Agent must produce safe partial outputs (refusal/deferral/report). "Tool required" degrades to "tool required OR mark unverified + cap confidence". LOCKED must not be terminal attractor.
7. **Pseudocode sharp edges.** Define innovation_std estimator (MAD or drop outlier logic for v0.1). Enumerate safe action set per invariant for enforce_barrier()/project_to_safe().
8. **Regime band alignment.** ELASTIC/WARM/STRICT/LOCKED thresholds must align with CBI bands (40/60/80). State whether configurable (must maintain ordering + hysteresis gap).

Also add RFC-ish MUST/SHOULD/MAY section:

**MUST:** θ immutable in-run, apply gate required, replay+holdout non-regression, missing telemetry fails closed, dwell-time+hysteresis enforced.

**SHOULD:** Shadow metrics out-of-band, change-point freezes L2, canary deploy before full apply.

**MAY:** Metric rotation (scoped to live only), advanced filtering (Kalman-ish).

---

## Overview

Governor 3.0 introduces **stratified self-governance**: the governor becomes part of the plant, not an external auditor. This enables adaptive control where the system can tighten/relax based on its own telemetry — without creating a recursive control loop that eats its own epistemics.

**The north star:** The governor shouldn't make the agent smarter; it should make the agent unable to lie to itself at high speed.

**The trap to avoid:** Two microphones pointed at each other. Self-application without designed recursion creates oscillation, lock-in, or silent Goodhart drift.

---

## 1. Stratified Control Architecture

### 1.1 Three Control Tiers

```
┌─────────────────────────────────────────────────────────────┐
│                     L2: META-GOVERNOR                       │
│  • Proposes parameter changes to θ                          │
│  • Runs OUT-OF-BAND (batch, on completed runs)              │
│  • Update period K >> typical run dynamics                  │
│  • Can only PROPOSE, never APPLY directly                   │
└─────────────────────────────┬───────────────────────────────┘
                              │ config_patch.json
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  APPLY GATE (Human/Automated)               │
│  • Verifies: schema, signature, replay tests, bounds        │
│  • Rollback capability required                             │
│  • Version control mandatory                                │
└─────────────────────────────┬───────────────────────────────┘
                              │ θ (immutable during run)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   L1: ONLINE GOVERNOR                       │
│  • Observes event stream in real-time                       │
│  • Enforces caps, regimes, alerts                           │
│  • Emits telemetry (CBI, D, invariant status)               │
│  • Parameters θ are FROZEN for duration of run              │
└─────────────────────────────┬───────────────────────────────┘
                              │ constraints, regime, alerts
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      L0: WORK LOOP                          │
│  • Agent + tools + environment                              │
│  • Produces event stream e_{1:T}                            │
│  • Subject to L1 constraints                                │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Authority Matrix

| Tier | Can Observe | Can Modify | Update Frequency |
|------|-------------|------------|------------------|
| L0 (Work) | Own context | Artifacts, tool calls | Event-time (ms-s) |
| L1 (Online) | Event stream | Caps, regimes, alerts | Event-time (s-min) |
| L2 (Meta) | Completed runs | θ proposals only | Batch-time (hours-days) |
| Apply Gate | Proposals + tests | θ (after verification) | On-demand |

### 1.3 Hard Authority Rules

**Rule 1: No in-band mutation.**
θ is immutable during a run. L0/L1 can only emit `PROPOSE(Δθ)`.

**Rule 2: Two-phase apply.**
`PROPOSE → REPLAY/TEST → APPLY`
Apply only if tests pass and risk constraints hold.

**Rule 3: Timescale separation.**
L1 runs at event-time. L2 runs at batch-time with update period K such that K >> typical within-run dynamics. No parameter chasing.

**Rule 4: Invariant firewall.**
Some invariants (S1, S7 class) are immutable at runtime. Even L2 needs higher bar or human signoff to modify them.

---

## 2. Formal Properties

### 2.1 Coherent Self-Dogfooding (CSD) Property

A governor stack satisfies CSD if:

**Property 1: Invariant Safety Bound**
For invariant set I = {S1...S7}, violation probability is bounded:
```
Pr[violate(I)] ≤ δ
```
Violations trigger mandatory regime tightening (not optional).

**Property 2: Non-Regression Under Updates**
For every accepted update θ → θ', on evaluation suite E:
```
Pr_θ'[violate(I)] ≤ Pr_θ[violate(I)] + ε
```
AND either performance improves OR cost decreases under same safety bound.

**Property 3: Bounded Update Step (Anti-Thrashing)**
```
‖θ' - θ‖ ≤ η
```
Plus hysteresis rules for regime thresholds.

**Property 4: Metric Non-Hackability**
Meta-governor evaluated on different view than it optimizes (holdout + randomized perturbations).

### 2.2 One-Line Definition

> A governor is coherently self-dogfooding if it can use its own telemetry to tighten/relax control in-run, and improve its own parameters out-of-band, while maintaining bounded invariant violation probability and bounded update steps, verified by replayable tests.

---

## 3. Control Theory Foundations

### 3.1 Timescale Separation (Singular Perturbation)

Three time constants:
- **τ_fast**: task loop (tokens/tools) ~ ms-s
- **τ_mid**: online governance (caps/regimes) ~ s-min
- **τ_slow**: meta-governance (parameter updates) ~ hours-days

Enforce Tikhonov-style separation: meta updates only when fast/mid dynamics are near steady-state.

```python
class TimescaleSeparation:
    min_batch_size: int = 10          # runs before meta-update considered
    cooldown_windows: int = 3         # windows after update before next
    recovery_required: bool = True    # M8 must be in band before update

    def can_update(self, state: MetaState) -> bool:
        return (
            state.completed_runs >= self.min_batch_size and
            state.windows_since_last_update >= self.cooldown_windows and
            (not self.recovery_required or state.m8_in_band)
        )
```

### 3.2 Hybrid Switching Stability

Regimes form a switching controller. Prevent chatter via:

**Minimum dwell-time:** Each regime held for at least T_dwell before switch allowed.

**Hysteresis bands:** Enter strict at threshold A, exit strict at threshold B > A.

**Rate limit:** Max regime_changes/hour enforced.

```python
@dataclass
class SwitchingConstraints:
    min_dwell_s: float = 300          # 5 minutes minimum per regime
    hysteresis_band: float = 0.1      # 10% band between enter/exit
    max_switches_per_hour: int = 4

    def can_switch(self, current_regime: str, proposed: str,
                   dwell_time: float, switches_this_hour: int) -> bool:
        if dwell_time < self.min_dwell_s:
            return False
        if switches_this_hour >= self.max_switches_per_hour:
            return False
        return True
```

### 3.3 Control Barrier Functions (Safety Invariants)

Treat S1-S7 as forward-invariant safe set. For each invariant i:
- Safe set: h_i(x) ≥ 0
- If projected next-step violates, restrict action set

```python
def enforce_barrier(state: RunState, proposed_action: Action,
                    invariants: List[Invariant]) -> Action:
    """Project action to maintain invariant safety."""
    for inv in invariants:
        projected_violation = inv.project_violation(state, proposed_action)
        if projected_violation > 0:
            # Restrict to safe action set
            proposed_action = inv.project_to_safe(state, proposed_action)
    return proposed_action
```

### 3.4 Small-Gain Theorem (Loop Stability)

Interconnected subsystems: P ↔ G1 ↔ G2

Prevent amplification:
- Limit how much telemetry affects policy (gain < 1)
- Limit how much policy affects telemetry (gain < 1)
- Especially: limit how much CBI optimization can alter CBI measurement

```python
@dataclass
class GainLimits:
    telemetry_to_policy_gain: float = 0.5    # Max policy shift per unit telemetry
    policy_to_telemetry_gain: float = 0.3    # Expected telemetry shift per policy
    update_magnitude_cap: float = 0.1        # Max ||Δθ|| per update
```

### 3.5 State Estimation (Filtering)

CBI is noisy measurement, not true state. Apply filtering:

```python
class CoherenceEstimator:
    """Kalman-style filtering for latent coherence state."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha  # Exponential smoothing
        self.z_hat = None   # Latent state estimate

    def update(self, y_t: float) -> float:
        """Update estimate with new measurement."""
        if self.z_hat is None:
            self.z_hat = y_t
        else:
            # Exponential smoothing + outlier detection
            innovation = y_t - self.z_hat
            if abs(innovation) > 3 * self.innovation_std:
                # Outlier - reduce weight
                self.z_hat += 0.1 * innovation
            else:
                self.z_hat += self.alpha * innovation
        return self.z_hat
```

### 3.6 Change-Point Detection

Detect distribution shift and freeze adaptation:

```python
class ChangePointDetector:
    """CUSUM-style change detection."""

    def __init__(self, threshold: float = 5.0, drift: float = 0.5):
        self.threshold = threshold
        self.drift = drift
        self.cusum_pos = 0
        self.cusum_neg = 0

    def update(self, x: float, baseline: float) -> bool:
        """Returns True if change detected."""
        self.cusum_pos = max(0, self.cusum_pos + x - baseline - self.drift)
        self.cusum_neg = max(0, self.cusum_neg - x + baseline - self.drift)

        if self.cusum_pos > self.threshold or self.cusum_neg > self.threshold:
            self.reset()
            return True
        return False
```

When change detected:
- Freeze L2 updates
- Fall back to conservative L1 regime
- Flag "new operating domain"

---

## 4. L1: Online Governor Specification

### 4.1 Interface

```python
@dataclass
class OnlineGovernorConfig:
    """θ - frozen during run."""
    # Invariant weights
    inv_weights: Dict[str, float]

    # Regime thresholds
    regime_thresholds: Dict[str, RegimeThreshold]

    # Confidence caps by D level
    confidence_caps: Dict[str, float]

    # Budget allocations
    phase_budgets: PhaseBudget

    # Hysteresis parameters
    hysteresis: HysteresisConfig

class OnlineGovernor:
    def __init__(self, config: OnlineGovernorConfig):
        self.config = config  # Immutable for run duration
        self.state = GovernorState()

    def process_event(self, event: Event) -> GovernorOutput:
        """Process single event, emit constraints/alerts."""
        # Update state
        self.state.update(event)

        # Compute metrics
        metrics = self.compute_metrics()

        # Check invariants
        violations = self.check_invariants(metrics)

        # Determine regime (with hysteresis)
        regime = self.determine_regime(metrics, violations)

        # Emit constraints
        constraints = self.compute_constraints(regime, metrics)

        # Emit alerts
        alerts = self.check_alerts(violations, metrics)

        return GovernorOutput(
            constraints=constraints,
            regime=regime,
            alerts=alerts,
            telemetry=Telemetry(cbi=metrics.cbi, D=metrics.D, invariants=violations)
        )
```

### 4.2 Regime State Machine

```
                    ┌──────────────────┐
                    │                  │
        ┌───────────│     ELASTIC      │◄──────────┐
        │           │   (CBI > 80)     │           │
        │           └────────┬─────────┘           │
        │                    │                     │
        │         CBI < 70   │          CBI > 85   │
        │         (enter)    ▼          (exit)     │
        │           ┌────────────────┐             │
        │           │                │             │
        │           │      WARM      │─────────────┘
        │           │  (60 < CBI < 80)│
        │           └────────┬───────┘
        │                    │
        │         CBI < 50   │          CBI > 65
        │         (enter)    ▼          (exit)
        │           ┌────────────────┐
        │           │                │
        │           │     STRICT     │─────────────┐
        │           │  (40 < CBI < 60)│            │
        │           └────────┬───────┘             │
        │                    │                     │
        │         CBI < 30   │          CBI > 45   │
        │    OR v_i > 0.8    ▼          (exit)     │
        │           ┌────────────────┐             │
        └───────────│                │─────────────┘
                    │     LOCKED     │
                    │   (CBI < 40)   │
                    │  OR UNSAFE     │
                    └────────────────┘
```

### 4.3 Regime Effects

| Regime | Confidence Cap | Tool Requirements | Budget Multiplier | Human Review |
|--------|---------------|-------------------|-------------------|--------------|
| ELASTIC | 0.95 | Optional | 1.0x | None |
| WARM | 0.85 | Recommended | 0.8x | S3 only |
| STRICT | 0.70 | Required for S2+ | 0.6x | S2+ |
| LOCKED | 0.50 | Required all | 0.4x | All commits |

---

## 5. L2: Meta-Governor Specification

### 5.1 Interface

```python
@dataclass
class MetaGovernorInput:
    completed_runs: List[RunSummary]
    current_config: OnlineGovernorConfig
    evaluation_suite: EvaluationSuite

@dataclass
class ConfigPatch:
    delta_theta: Dict[str, Any]      # Proposed changes
    justification: str               # Which failure modes it addresses
    expected_tradeoff: str           # Latency/cost implications
    test_results: TestResults        # Suite hashes + outcomes
    signature: str                   # Cryptographic signature

class MetaGovernor:
    def __init__(self, constraints: MetaConstraints):
        self.constraints = constraints

    def propose_update(self, input: MetaGovernorInput) -> Optional[ConfigPatch]:
        """Analyze runs, propose config changes."""

        # Aggregate statistics across runs
        stats = self.aggregate_run_stats(input.completed_runs)

        # Identify failure patterns
        patterns = self.identify_failure_patterns(stats)

        # Generate candidate patches
        candidates = self.generate_candidates(patterns, input.current_config)

        # Evaluate on replay suite
        best = None
        for candidate in candidates:
            result = self.evaluate_candidate(candidate, input.evaluation_suite)
            if self.passes_constraints(result, input.current_config):
                if best is None or result.score > best.score:
                    best = (candidate, result)

        if best is None:
            return None

        candidate, result = best
        return ConfigPatch(
            delta_theta=candidate,
            justification=self.generate_justification(patterns, candidate),
            expected_tradeoff=self.estimate_tradeoff(candidate),
            test_results=result,
            signature=self.sign(candidate, result)
        )
```

### 5.2 Meta-Constraints

```python
@dataclass
class MetaConstraints:
    # Bounded update step
    max_weight_change: float = 0.1      # Max change to any weight
    max_threshold_change: float = 0.15  # Max change to any threshold

    # Non-regression
    max_violation_increase: float = 0.01  # ε in non-regression property

    # Evaluation requirements
    min_replay_runs: int = 50
    min_adversarial_runs: int = 10
    required_test_pass_rate: float = 0.95

    # Timescale
    min_runs_between_updates: int = 100
    cooldown_after_update_hours: float = 24
```

### 5.3 Evaluation Suite

```python
@dataclass
class EvaluationSuite:
    """Frozen test suite for evaluating config changes."""

    # Normal operation traces
    normal_traces: List[Trace]

    # Adversarial traces (prompt injection, tool spoofing, etc.)
    adversarial_traces: List[Trace]

    # Edge cases (high D, conflicting goals, etc.)
    edge_traces: List[Trace]

    # Holdout traces (never seen by optimizer)
    holdout_traces: List[Trace]

    # Suite version + hash for reproducibility
    version: str
    content_hash: str

    def replay(self, config: OnlineGovernorConfig) -> ReplayResults:
        """Deterministic replay with given config."""
        results = []
        for trace in self.all_traces():
            result = replay_trace(trace, config)
            results.append(result)
        return ReplayResults(results)
```

---

## 6. Apply Gate Specification

### 6.1 Verification Steps

```python
class ApplyGate:
    def __init__(self, constraints: ApplyConstraints):
        self.constraints = constraints

    def verify(self, patch: ConfigPatch,
               current: OnlineGovernorConfig,
               suite: EvaluationSuite) -> ApplyDecision:

        # 1. Schema validation
        if not self.validate_schema(patch):
            return ApplyDecision.REJECT("Schema validation failed")

        # 2. Signature verification
        if not self.verify_signature(patch):
            return ApplyDecision.REJECT("Invalid signature")

        # 3. Bound checking
        if not self.check_bounds(patch, current):
            return ApplyDecision.REJECT("Update exceeds bounds")

        # 4. Replay tests
        new_config = self.apply_patch(current, patch)
        replay_result = suite.replay(new_config)

        # 5. Non-regression check
        baseline_result = suite.replay(current)
        if not self.check_non_regression(baseline_result, replay_result):
            return ApplyDecision.REJECT("Regression detected")

        # 6. Holdout validation
        holdout_result = suite.replay_holdout(new_config)
        if not self.check_holdout(holdout_result):
            return ApplyDecision.REJECT("Holdout validation failed")

        return ApplyDecision.ACCEPT(
            new_config=new_config,
            rollback_config=current,
            test_results=replay_result
        )
```

### 6.2 Rollback Protocol

```python
@dataclass
class ConfigVersion:
    version_id: str
    config: OnlineGovernorConfig
    applied_at: datetime
    patch: Optional[ConfigPatch]
    test_results: TestResults

class ConfigManager:
    def __init__(self, max_versions: int = 10):
        self.versions: List[ConfigVersion] = []
        self.current_idx: int = 0

    def apply(self, patch: ConfigPatch, decision: ApplyDecision) -> str:
        """Apply patch, return version_id."""
        new_version = ConfigVersion(
            version_id=generate_id(),
            config=decision.new_config,
            applied_at=datetime.now(),
            patch=patch,
            test_results=decision.test_results
        )
        self.versions.append(new_version)
        self.current_idx = len(self.versions) - 1
        return new_version.version_id

    def rollback(self, to_version: str) -> bool:
        """Rollback to specific version."""
        for i, v in enumerate(self.versions):
            if v.version_id == to_version:
                self.current_idx = i
                return True
        return False
```

---

## 7. Anti-Goodhart Measures

### 7.1 The Problem

Once the system optimizes "CBI looks good," it will learn to:
- Suppress signals
- Reduce logging
- Avoid difficult work
- Game metric definitions

### 7.2 Countermeasures

**Shadow Metrics:** At least one metric not exposed to optimizer.

```python
class ShadowMetrics:
    """Computed out-of-band, not visible to L2."""

    def compute(self, traces: List[Trace]) -> Dict[str, float]:
        return {
            "shadow_coverage": self.compute_shadow_coverage(traces),
            "shadow_provenance": self.compute_shadow_provenance(traces),
            "human_override_rate": self.compute_override_rate(traces),
        }
```

**Metric Rotation:** Periodically rotate which metrics L2 sees.

**Holdout Traces:** Evaluation suite includes traces L2 never optimizes on.

**Cross-Metric Sanity:** Alert if metrics diverge suspiciously.

```python
def check_goodhart_signals(metrics: Metrics, shadow: ShadowMetrics) -> List[Alert]:
    alerts = []

    # CBI improving but shadow metrics degrading
    if metrics.cbi_trend > 0.1 and shadow.shadow_coverage_trend < -0.1:
        alerts.append(Alert("GOODHART_SUSPECTED",
                           "CBI improving while shadow coverage degrading"))

    # Logging volume decreasing while CBI stable/improving
    if metrics.log_volume_trend < -0.2 and metrics.cbi >= 70:
        alerts.append(Alert("LOGGING_SUPPRESSION",
                           "Log volume decreasing - possible signal suppression"))

    return alerts
```

---

## 8. Events and Telemetry

### 8.1 L1 Telemetry Events

```json
{"event": "governor_telemetry", "cbi": 72.3, "D": 1.4, "regime": "WARM",
 "invariants": {"S1": 0.12, "S7": 0.23}, "window_id": "w_042", "ts": "..."}

{"event": "regime_change", "from": "ELASTIC", "to": "WARM",
 "trigger": "cbi_below_threshold", "cbi": 68.2, "dwell_time_s": 1847, "ts": "..."}

{"event": "invariant_violation", "invariant": "S7", "severity": 0.82,
 "action": "regime_locked", "ts": "..."}
```

### 8.2 L2 Events

```json
{"event": "meta_analysis_start", "run_count": 127, "config_version": "v2.3.1", "ts": "..."}

{"event": "config_patch_proposed", "patch_id": "p_019",
 "changes": {"inv_weights.S7": {"old": 0.16, "new": 0.18}},
 "justification": "S7 violations elevated in last 50 runs",
 "test_pass_rate": 0.97, "ts": "..."}

{"event": "config_patch_applied", "patch_id": "p_019",
 "new_version": "v2.4.0", "rollback_version": "v2.3.1", "ts": "..."}

{"event": "config_rollback", "from_version": "v2.4.0", "to_version": "v2.3.1",
 "reason": "violation_rate_increased", "ts": "..."}
```

---

## 9. Prerequisites for 3.0

Before self-apply is enabled:

### 9.1 Stable Observability
- [ ] Event schema frozen (no churn)
- [ ] Provenance signals reliable
- [ ] Metrics have falsification tests

### 9.2 Replayable Evaluation
- [ ] Frozen test suite (normal + adversarial + edge)
- [ ] Deterministic replays produce identical scores
- [ ] Holdout traces maintained

### 9.3 Metric Robustness
- [ ] At least one shadow metric
- [ ] Cross-metric sanity checks
- [ ] Cannot be trivially satisfied by "doing less"

### 9.4 Update Firewall
- [ ] In-band can only PROPOSE
- [ ] Bounded step size enforced
- [ ] Hysteresis implemented
- [ ] Rollback tested

### 9.5 Two Independent Views
- [ ] Optimizer evaluated on different view than it optimizes
- [ ] Holdout never seen by L2

---

## 10. 2.7 Waypoint: Shadow Self-Governance

Before full 3.0, implement shadow mode:

```python
class ShadowMetaGovernor:
    """Proposes but never applies. Smokes out logic bugs."""

    def run(self, completed_runs: List[RunSummary]) -> ShadowReport:
        # Generate proposal as if real
        patch = self.meta_governor.propose_update(...)

        if patch is None:
            return ShadowReport(proposed=False)

        # Run through apply gate
        decision = self.apply_gate.verify(patch, ...)

        # Simulate outcomes
        simulated = self.simulate_outcomes(patch, ...)

        # Label but don't apply
        return ShadowReport(
            proposed=True,
            patch=patch,
            decision=decision,
            simulated_outcomes=simulated,
            recommendation="ACCEPT" if decision.accepted else "REJECT"
        )
```

**Gate for 3.0:** Shadow meta-governor must beat frozen baseline on held-out suite for N runs without increasing invariant violation rate.

---

## 11. Success Criteria

The system is coherently self-dogfooding when it can:

1. **Detect** its own verification debt rising (D up)
2. **Automatically shift** to slower regime (tighten caps, require tools)
3. **Relax safely** when debt falls, without flapping
4. **Propose** parameter improvements based on run statistics
5. **Verify** proposals don't regress on held-out data
6. **Apply** changes with rollback capability
7. **Detect** Goodhart drift via shadow metrics

That's the metastability sweet spot: not "always strict," not "always loose," but stable regime switching with hysteresis — applied recursively to its own governance parameters.

---

## 12. Relationship to 2.0

3.0 is **not** a replacement for 2.0. It's a new loop with gates that sits on top of a working 2.0.

The only things that matter for 2.0 (prerequisites for 3.0 to not be magic):

- **Event schema stability** (stop churn; version it; fail closed when missing fields)
- **Deterministic replay** (same trace → same score → same alerts)
- **Provenance discipline** (S1/S7 don't exist without it)
- **Regime machine w/ hysteresis + dwell** (no flapping)
- **A small, ruthless eval suite** (even 10 traces beats vibes)

Once 2.0 is real, 3.0 stops being "high risk magic" and becomes "a new loop with gates."

Sanity check for every 2.0 feature: **does this increase observability, enforceability, or determinism?** If not, it's probably 2.9 cosplay.
