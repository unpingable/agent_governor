# Self-Governance Specification v0.1 (3.x Preview)

```yaml
status: planning (deferred — requires 2.0 + 2.1 complete)
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

**MUST:** θ immutable in-run, apply gate required, replay+holdout non-regression, missing telemetry fails closed, dwell-time+hysteresis enforced.

**SHOULD:** Shadow metrics out-of-band, change-point freezes L2, canary deploy before full apply.

**MAY:** Metric rotation (scoped to live only), advanced filtering (Kalman-ish).

---

## Overview

The transition from 2.x → 3.x is: **stop treating the governor as an external cop; treat it as part of the plant.**

This requires bedrock constraints or you accidentally build a self-modifying rationalizer.

**The core danger:** A self-governing system can learn to "win" by redefining what counts as winning. Without hard constraints, self-tuning becomes self-justifying policy drift.

**3.x failure modes to prevent:**
- Parameter drift (slow Goodhart)
- Limit cycles (tighten/relax ping-pong)
- Mode lock-in (stuck in LOCKDOWN because LOCKDOWN increases evidence demands which increases uncertainty which...)
- Metastable "looks stable" (U_t low because governor learned to stop *counting* blockers)

---

## The Three Non-Negotiables

If you only implement three things for 2→3:

### 1. Executor/Proposer Separation

```
┌─────────────────────────────────────────────────────────────┐
│                     HARD BOUNDARY                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Governor (Executor)          Meta-Governor (Proposer)      │
│  ─────────────────            ────────────────────────      │
│  • Applies current θ          • Observes telemetry          │
│  • Enforces invariants        • Proposes Δθ                 │
│  • Cannot modify θ            • Cannot apply changes        │
│                                                             │
│                    ↓ proposal ↓                             │
│              ┌─────────────────────┐                        │
│              │   Acceptance Gate   │                        │
│              │   (audited, narrow) │                        │
│              └─────────────────────┘                        │
│                    ↓ if approved ↓                          │
│              θ_{t+1} = θ_t + Δθ                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Rule:** No agent updates its own rules mid-flight. Ever.

```python
class Governor:
    """Executor: applies policy, cannot modify it."""

    def __init__(self, theta: GovernorParams):
        self._theta = theta  # Immutable during execution

    def process(self, task: Task) -> Result:
        # Can only READ theta, never write
        return self._apply_policy(task, self._theta)

    def _apply_policy(self, task: Task, theta: GovernorParams) -> Result:
        # All decisions derived from frozen theta
        pass

class MetaGovernor:
    """Proposer: suggests changes, cannot apply them."""

    def __init__(self, telemetry: TelemetryStream):
        self._telemetry = telemetry

    def propose_update(self) -> Optional[ThetaDelta]:
        # Can only PROPOSE, never apply
        measurements = self._telemetry.get_admissible_measurements()

        if self._should_propose_change(measurements):
            return self._compute_delta(measurements)
        return None

class AcceptanceGate:
    """Narrow, audited gate between proposer and executor."""

    def __init__(self, invariants: List[MetaInvariant]):
        self._invariants = invariants
        self._audit_log = AuditLog()

    def evaluate(
        self,
        current_theta: GovernorParams,
        proposed_delta: ThetaDelta,
        measurements: AdmissibleMeasurements
    ) -> AcceptanceDecision:

        # Check all meta-invariants
        for inv in self._invariants:
            if not inv.check(current_theta, proposed_delta):
                self._audit_log.record_rejection(proposed_delta, inv)
                return AcceptanceDecision.REJECT

        # Check measurement justification
        if not self._measurements_justify_change(measurements, proposed_delta):
            self._audit_log.record_rejection(proposed_delta, "insufficient_evidence")
            return AcceptanceDecision.REJECT

        # Log acceptance
        self._audit_log.record_acceptance(proposed_delta, measurements)
        return AcceptanceDecision.ACCEPT
```

### 2. Admissible Measurement Gating

**Rule:** No parameter update unless justified by admissible measurements, not model narrative.

This is the x̂ vs y distinction applied to governance itself.

```python
@dataclass
class AdmissibleMeasurements:
    """Only these signals can influence θ changes."""

    # Verifier performance
    verifier_failure_rate: Dict[str, float]
    verifier_latency_p99: Dict[str, float]

    # Uncertainty dynamics
    U_t_decay_slope: float
    U_t_variance: float

    # Contradiction signals
    contradiction_rate: float
    claim_retraction_rate: float

    # Operational health
    rollback_frequency: float
    deadlock_rate: float
    regime_switch_frequency: float

    # Cost signals
    verification_spend_rate: float
    latency_budget_utilization: float

# What is NOT admissible:
INADMISSIBLE_SIGNALS = [
    "model_stated_confidence",      # x̂, not y
    "model_narrative_justification", # prose, not measurement
    "user_satisfaction_proxy",       # gameable
    "task_completion_rate",          # Goodhart bait
]

def measurements_justify_change(
    measurements: AdmissibleMeasurements,
    proposed_delta: ThetaDelta
) -> bool:
    """
    Each θ change must be covered by sufficient admissible evidence.
    Uses hitting set logic: change requires minimum sensor coverage.
    """
    required_evidence = CHANGE_EVIDENCE_REQUIREMENTS.get(proposed_delta.param_name)

    if required_evidence is None:
        return False  # Unknown parameter, reject

    # Check that required measurements are present and significant
    for evidence_type in required_evidence:
        value = getattr(measurements, evidence_type, None)
        if value is None:
            return False
        if not is_significant(value, evidence_type, measurements):
            return False

    return True

def is_significant(
    value: float,
    evidence_type: str,
    measurements: AdmissibleMeasurements
) -> bool:
    """
    Statistical/operational significance - NOT narrative.

    These thresholds are PROTECTED parameters (cannot be tuned by meta-governor).
    """
    config = SIGNIFICANCE_CONFIG[evidence_type]

    # Minimum sample size
    sample_size = measurements.sample_counts.get(evidence_type, 0)
    if sample_size < config.min_sample_size:
        return False

    # Minimum effect size (Cohen's d or equivalent)
    baseline = measurements.baselines.get(evidence_type)
    if baseline is not None:
        std = measurements.stds.get(evidence_type, 1.0)
        if std > 0:
            effect_size = abs(value - baseline) / std
            if effect_size < config.min_effect_size:
                return False

    # Confidence interval check
    ci = measurements.confidence_intervals.get(evidence_type)
    if ci is not None:
        ci_width = ci[1] - ci[0]
        if ci_width > config.max_ci_width:
            return False  # Too uncertain

    # Change-point detection (optional, for time-series)
    if config.require_change_point:
        if not measurements.change_point_detected.get(evidence_type, False):
            return False

    return True

@dataclass
class SignificanceConfig:
    """Protected configuration for significance tests."""
    min_sample_size: int
    min_effect_size: float  # Cohen's d
    max_ci_width: float     # 95% CI width
    require_change_point: bool = False

# PROTECTED - cannot be modified by meta-governor
SIGNIFICANCE_CONFIG = {
    "verifier_failure_rate": SignificanceConfig(
        min_sample_size=50, min_effect_size=0.3, max_ci_width=0.1
    ),
    "contradiction_rate": SignificanceConfig(
        min_sample_size=100, min_effect_size=0.2, max_ci_width=0.05
    ),
    "U_t_decay_slope": SignificanceConfig(
        min_sample_size=30, min_effect_size=0.5, max_ci_width=0.2,
        require_change_point=True
    ),
    "rollback_frequency": SignificanceConfig(
        min_sample_size=20, min_effect_size=0.4, max_ci_width=0.15
    ),
    "deadlock_rate": SignificanceConfig(
        min_sample_size=50, min_effect_size=0.3, max_ci_width=0.1
    ),
}

# Evidence requirements for common θ changes
CHANGE_EVIDENCE_REQUIREMENTS = {
    "tau": ["U_t_decay_slope", "contradiction_rate", "rollback_frequency"],
    "confidence_cap": ["verifier_failure_rate", "claim_retraction_rate"],
    "regime_thresholds": ["regime_switch_frequency", "deadlock_rate"],
    "tool_trust": ["verifier_failure_rate", "verifier_latency_p99"],
    "verification_budget": ["verification_spend_rate", "U_t_variance"],
}
```

### 3. Rollback + Hysteresis + Dwell

**Rollback:** First-class control action, not afterthought.

```python
@dataclass
class ThetaSnapshot:
    theta: GovernorParams
    timestamp: datetime
    measurements_at_adoption: AdmissibleMeasurements
    policy_hash: str  # Hash of protected params + meta-invariants

    # Filled AFTER evaluation window completes
    performance_during: Optional[PerformanceMetrics] = None
    evaluation_window_complete: bool = False
    task_count_in_window: int = 0

@dataclass
class EvaluationWindow:
    """Define how we evaluate a θ snapshot."""
    min_tasks: int = 100
    min_duration_seconds: float = 3600  # 1 hour minimum
    max_duration_seconds: float = 86400  # 1 day maximum

class RollbackController:
    """Manages θ history and automatic reversion."""

    def __init__(
        self,
        max_snapshots: int = 10,
        eval_window: EvaluationWindow = EvaluationWindow()
    ):
        self._snapshots: List[ThetaSnapshot] = []
        self._max_snapshots = max_snapshots
        self._eval_window = eval_window
        self._current_idx = -1
        self._baseline_metrics: Optional[BaselineMetrics] = None

    def record_snapshot(
        self,
        theta: GovernorParams,
        measurements: AdmissibleMeasurements,
        policy_hash: str
    ):
        snapshot = ThetaSnapshot(
            theta=theta,
            timestamp=datetime.now(),
            measurements_at_adoption=measurements,
            policy_hash=policy_hash,
            performance_during=None,
            evaluation_window_complete=False,
            task_count_in_window=0
        )
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)
        self._current_idx = len(self._snapshots) - 1

    def record_task_outcome(self, outcome: TaskOutcome):
        """Update current snapshot's performance metrics."""
        if self._current_idx < 0:
            return

        current = self._snapshots[self._current_idx]
        current.task_count_in_window += 1

        # Update running metrics
        if current.performance_during is None:
            current.performance_during = PerformanceMetrics()
        current.performance_during.update(outcome)

        # Check if evaluation window is complete
        elapsed = (datetime.now() - current.timestamp).total_seconds()
        if (current.task_count_in_window >= self._eval_window.min_tasks and
            elapsed >= self._eval_window.min_duration_seconds):
            current.evaluation_window_complete = True

    def check_rollback_triggers(self) -> Optional[RollbackTrigger]:
        """Check if automatic rollback is warranted."""

        if self._current_idx < 1:
            return None

        current = self._snapshots[self._current_idx]

        # Need completed evaluation window
        if not current.evaluation_window_complete:
            return None

        # Compare against BASELINE, not just previous snapshot
        # (Prevents Simpson's paradox from workload shift)
        if self._baseline_metrics is None:
            return None

        curr_metrics = current.performance_during
        baseline = self._baseline_metrics

        # Rollback triggers with stratified comparison
        triggers = []

        if curr_metrics.f1_rate > baseline.f1_rate * 1.5:
            triggers.append(RollbackTrigger("f1_spike", curr_metrics.f1_rate, baseline.f1_rate))

        if curr_metrics.f2_rate > baseline.f2_rate * 1.5:
            triggers.append(RollbackTrigger("f2_spike", curr_metrics.f2_rate, baseline.f2_rate))

        if curr_metrics.deadlock_rate > baseline.deadlock_rate * 2:
            triggers.append(RollbackTrigger("deadlock_spike", curr_metrics.deadlock_rate, baseline.deadlock_rate))

        # U_t miscalibration
        if curr_metrics.U_t_mean > baseline.U_t_mean * 1.3:
            triggers.append(RollbackTrigger("U_t_miscalibration", curr_metrics.U_t_mean, baseline.U_t_mean))

        return triggers[0] if triggers else None

    def rollback(self) -> GovernorParams:
        """Revert to previous stable θ."""
        if self._current_idx <= 0:
            raise RollbackError("No previous snapshot available")

        # Find most recent snapshot with completed evaluation that passed
        for i in range(self._current_idx - 1, -1, -1):
            snapshot = self._snapshots[i]
            if snapshot.evaluation_window_complete:
                # Verify rollback target doesn't violate current protected constraints
                if self._validate_rollback_target(snapshot):
                    self._current_idx = i
                    return snapshot.theta

        raise RollbackError("No valid rollback target found")

    def _validate_rollback_target(self, snapshot: ThetaSnapshot) -> bool:
        """Rollback cannot restore config that violates current protected constraints."""
        # Check policy hash matches current constitution
        # (Can't rollback to pre-amendment config after amendment)
        return snapshot.policy_hash == self._current_policy_hash

@dataclass
class BaselineMetrics:
    """
    Baseline computed from stratified sample, not just "previous".
    Updated via EWMA to handle distribution shift.
    """
    f1_rate: float
    f2_rate: float
    deadlock_rate: float
    U_t_mean: float

    # Stratified by task class to prevent Simpson's paradox
    by_task_class: Dict[str, 'BaselineMetrics']

    def update_ewma(self, new_metrics: PerformanceMetrics, alpha: float = 0.1):
        """Exponentially weighted moving average update."""
        self.f1_rate = alpha * new_metrics.f1_rate + (1 - alpha) * self.f1_rate
        self.f2_rate = alpha * new_metrics.f2_rate + (1 - alpha) * self.f2_rate
        # ... etc
```

**Hysteresis:** Prevent oscillation by design.

```python
@dataclass
class HysteresisConfig:
    """Separate thresholds for entering vs exiting states."""

    # Regime transitions
    lockdown_enter_threshold: float = 0.8  # U_t to enter LOCKDOWN
    lockdown_exit_threshold: float = 0.5   # U_t to exit LOCKDOWN (lower!)

    warm_enter_threshold: float = 0.5
    warm_exit_threshold: float = 0.3

    # Minimum dwell time before switching
    min_dwell_seconds: float = 300  # 5 minutes minimum in any regime

    # Bounded step size for θ changes
    max_delta_per_epoch: float = 0.1  # Max 10% change per update

@dataclass
class RegimeTransition:
    """Record of a regime transition (log only on actual switches)."""
    entered_at: datetime
    regime: Regime
    trigger_U_t: float
    trigger_reason: str

class RegimeHistory:
    """
    Track regime transitions only (not every event).
    This ensures dwell time is computed correctly.
    """

    def __init__(self):
        self._transitions: List[RegimeTransition] = []
        self._current_regime: Optional[Regime] = None
        self._current_entered_at: Optional[datetime] = None

    def record_transition(self, new_regime: Regime, U_t: float, reason: str):
        """Only call this when regime actually changes."""
        now = datetime.now()
        self._transitions.append(RegimeTransition(
            entered_at=now,
            regime=new_regime,
            trigger_U_t=U_t,
            trigger_reason=reason
        ))
        self._current_regime = new_regime
        self._current_entered_at = now

    def time_in_current_regime(self) -> float:
        """Seconds since entering current regime."""
        if self._current_entered_at is None:
            return float('inf')  # Never switched = infinite dwell
        return (datetime.now() - self._current_entered_at).total_seconds()

    def check_dwell_time_compliance(self, min_dwell: float) -> bool:
        """Verify all transitions respected minimum dwell."""
        for i in range(1, len(self._transitions)):
            prev = self._transitions[i-1]
            curr = self._transitions[i]
            dwell = (curr.entered_at - prev.entered_at).total_seconds()
            if dwell < min_dwell:
                return False
        return True

def check_regime_transition(
    current_regime: Regime,
    U_t: float,
    regime_history: RegimeHistory,
    config: HysteresisConfig
) -> Optional[Regime]:
    """Check if regime transition is allowed (with hysteresis)."""

    # Dwell time check
    time_in_regime = regime_history.time_in_current_regime()
    if time_in_regime < config.min_dwell_seconds:
        return None  # Too soon to switch

    # Hysteresis: different thresholds for enter vs exit
    if current_regime == Regime.ELASTIC:
        if U_t > config.warm_enter_threshold:
            return Regime.WARM

    elif current_regime == Regime.WARM:
        if U_t > config.lockdown_enter_threshold:
            return Regime.LOCKDOWN
        elif U_t < config.warm_exit_threshold:  # Lower threshold to exit
            return Regime.ELASTIC

    elif current_regime == Regime.LOCKDOWN:
        if U_t < config.lockdown_exit_threshold:  # Much lower to exit
            return Regime.WARM

    return None  # No transition

def check_delta_bounds(proposed_delta: ThetaDelta, config: HysteresisConfig) -> bool:
    """Ensure θ change is within bounded step size."""
    return abs(proposed_delta.magnitude) <= config.max_delta_per_epoch
```

---

## Safety Monotonicity Invariants

**The "constitution doesn't amend itself" rules.**

These invariants must hold for ANY θ change:

```python
@dataclass
class InvariantContext:
    """Context needed to evaluate meta-invariants."""
    measurements: AdmissibleMeasurements
    tool_trust_scores: Dict[str, float]
    current_regime: Regime
    acceptance_provenance: Optional[AcceptanceProvenance]  # For laundering checks

class MetaInvariant(Protocol):
    """Standardized interface for all meta-invariants."""

    name: str

    def check(
        self,
        current_theta: GovernorParams,
        proposed_theta: GovernorParams,  # NOT delta - gate computes this
        context: InvariantContext
    ) -> InvariantResult:
        """Returns pass/fail with explanation."""
        ...

@dataclass
class InvariantResult:
    passed: bool
    reason: str
    evidence: Optional[Dict[str, Any]] = None

def apply_delta(current: GovernorParams, delta: ThetaDelta) -> GovernorParams:
    """Compute proposed_theta from current + delta."""
    proposed = copy.deepcopy(current)
    setattr(proposed, delta.param_name, delta.new_value)
    return proposed

class AcceptanceGate:
    """Narrow, audited gate between proposer and executor."""

    def evaluate(
        self,
        current_theta: GovernorParams,
        proposed_delta: ThetaDelta,
        measurements: AdmissibleMeasurements,
        context: InvariantContext
    ) -> AcceptanceDecision:

        # Compute proposed_theta FIRST
        proposed_theta = apply_delta(current_theta, proposed_delta)

        # Check all meta-invariants with proper signature
        for inv in self._invariants:
            result = inv.check(current_theta, proposed_theta, context)
            if not result.passed:
                self._audit_log.record_rejection(
                    proposed_delta, inv.name, result.reason
                )
                return AcceptanceDecision.REJECT

        # ... rest of checks
```

### Permission Ordering (Formal Partial Order)

```python
class PermissionSet:
    """Formal lattice for permission comparisons."""

    def __init__(self, permissions: Set[str]):
        self._permissions = frozenset(permissions)

    def __le__(self, other: 'PermissionSet') -> bool:
        """a <= b means a is no more permissive than b (subset)."""
        return self._permissions <= other._permissions

    def is_subset_of(self, other: 'PermissionSet') -> bool:
        """Explicit subset check."""
        return self._permissions.issubset(other._permissions)

def dominates_policy(proposed: GovernorParams, current: GovernorParams) -> bool:
    """
    Returns True if proposed is no more permissive than current.

    This is the formal check for safety monotonicity.
    """
    return (
        proposed.allowed_side_effects.is_subset_of(current.allowed_side_effects) and
        proposed.tool_permissions.is_subset_of(current.tool_permissions) and
        proposed.max_tool_calls <= current.max_tool_calls and
        proposed.network_access_level <= current.network_access_level
    )

class SafetyMonotonicityInvariant(MetaInvariant):
    """Invariants that self-tuning must never violate."""

    name = "safety_monotonicity"

    def check(
        self,
        current_theta: GovernorParams,
        proposed_theta: GovernorParams,
        context: InvariantContext
    ) -> InvariantResult:

        # If U_t is high, permissions can't be looser
        if context.measurements.U_t > current_theta.tau:
            if not dominates_policy(proposed_theta, current_theta):
                return InvariantResult(
                    passed=False,
                    reason=f"Cannot loosen permissions while U_t ({context.measurements.U_t}) > τ ({current_theta.tau})"
                )

        # Tool trust monotonicity
        for tool, trust in context.tool_trust_scores.items():
            if trust < TRUST_THRESHOLD:
                current_reliance = current_theta.tool_reliance.get(tool, 0)
                proposed_reliance = proposed_theta.tool_reliance.get(tool, 0)
                if proposed_reliance > current_reliance:
                    return InvariantResult(
                        passed=False,
                        reason=f"Cannot increase reliance on {tool} while trust ({trust}) < threshold"
                    )

        # LOCKDOWN side effects forbidden
        lockdown_config = proposed_theta.regime_configs.get(Regime.LOCKDOWN)
        if lockdown_config and lockdown_config.allowed_side_effects:
            return InvariantResult(
                passed=False,
                reason="LOCKDOWN must have empty allowed_side_effects"
            )

        return InvariantResult(passed=True, reason="All safety monotonicity checks passed")
```

---

## No Epistemic Laundering

**Rule:** U_t can only decrease via legitimate means.

**Critical insight:** Laundering is about *path*, not *value*. A τ increase is legitimate if it went through the gate with proper evidence.

```python
@dataclass
class AcceptanceProvenance:
    """Proof that a change went through proper gate."""
    gate_decision_id: str
    timestamp: datetime
    measurements_used: AdmissibleMeasurements
    invariants_checked: List[str]
    invariants_passed: List[str]
    evidence_bundle_hash: str  # Hash of the evidence that justified this

class EpistemicLaunderingDetector:
    """Detect attempts to reduce uncertainty by redefining blockers."""

    LEGITIMATE_U_DECREASE = {
        "VERIFIED": "Claim verified by evidence",
        "WAIVED_BY_OPERATOR": "Operator explicitly waived requirement",
        "EXPIRED_BY_SCOPE": "Claim no longer in scope (explicit removal)",
        "GATE_APPROVED_TAU_CHANGE": "τ changed via accepted gate decision",
    }

    ILLEGITIMATE_U_DECREASE = {
        "BLOCKER_REDEFINED": "Changed what counts as a blocker without gate",
        "UNGATED_THRESHOLD_CHANGE": "Changed τ without gate approval",
        "CLAIM_RECLASSIFIED": "Changed claim severity without evidence",
        "SCOPE_SHRUNK_SILENTLY": "Reduced scope to avoid blockers",
    }

    def __init__(self, audit_log: MetaAuditLog):
        self._audit_log = audit_log

    def check_U_decrease(
        self,
        U_before: float,
        U_after: float,
        blockers_before: Set[str],
        blockers_after: Set[str],
        theta_before: GovernorParams,
        theta_after: GovernorParams,
        provenance: Optional[AcceptanceProvenance]
    ) -> LaunderingCheckResult:
        """Verify U_t decrease is legitimate by checking PATH, not just value."""

        if U_after >= U_before:
            return LaunderingCheckResult(legitimate=True)

        # U_t decreased - check why

        # Check 1: Were blockers closed legitimately?
        closed_blockers = blockers_before - blockers_after
        if closed_blockers:
            for blocker in closed_blockers:
                closure_record = self._audit_log.find_blocker_closure(blocker)
                if closure_record is None:
                    return LaunderingCheckResult(
                        legitimate=False,
                        reason="BLOCKER_CLOSED_WITHOUT_RECORD",
                        details=f"Blocker {blocker} removed without audit trail"
                    )
                if closure_record.method not in self.LEGITIMATE_U_DECREASE:
                    return LaunderingCheckResult(
                        legitimate=False,
                        reason="BLOCKER_CLOSED_ILLEGITIMATELY",
                        details=f"Blocker {blocker} closed via {closure_record.method}"
                    )

        # Check 2: If τ changed, was it through the gate?
        if theta_after.tau != theta_before.tau:
            if provenance is None:
                return LaunderingCheckResult(
                    legitimate=False,
                    reason="UNGATED_THRESHOLD_CHANGE",
                    details=f"τ changed from {theta_before.tau} to {theta_after.tau} without gate approval"
                )

            # Verify provenance is for this specific change
            if not self._audit_log.verify_provenance(provenance, "tau", theta_after.tau):
                return LaunderingCheckResult(
                    legitimate=False,
                    reason="PROVENANCE_MISMATCH",
                    details="Gate provenance doesn't match τ change"
                )

        # Check 3: Did blocker criteria change without gate?
        if theta_after.blocker_criteria != theta_before.blocker_criteria:
            if provenance is None or "blocker_criteria" not in provenance.measurements_used:
                return LaunderingCheckResult(
                    legitimate=False,
                    reason="BLOCKER_REDEFINED",
                    details="Blocker criteria modified without proper gate approval"
                )

        return LaunderingCheckResult(legitimate=True, reason="Path verified")
```

---

## Dual Ledger: Epistemic and Economic

2.x tracks uncertainty. 3.x must also track cost, or the system becomes either:
- A verification zealot (reliability up, cost infinite)
- A liar (cost down, reliability fake)

```python
@dataclass
class DualLedger:
    """Track both epistemic debt and economic debt."""

    # Epistemic ledger
    U_t: float                          # Current uncertainty
    U_history: List[Tuple[datetime, float]]
    blockers: Set[str]
    claims_verified: int
    claims_waived: int
    claims_unverified: int

    # Economic ledger
    C_t: float                          # Current verification spend
    C_history: List[Tuple[datetime, float]]
    latency_debt: float                 # Accumulated latency beyond budget
    tool_calls_budget: int
    tool_calls_used: int
    model_spend_budget: float
    model_spend_used: float

class MetaGovernorObjective:
    """
    Meta-governor optimizes C_t subject to U_t <= tau.
    NOT the other way around.

    Two-stage planner prevents "stuck at infinity" deadlocks.
    """

    @staticmethod
    def plan_actions(
        ledger: DualLedger,
        available_actions: List[VerificationAction],
        tau: float
    ) -> ActionPlan:
        """
        Two-stage planner:
        1. Feasibility recovery: minimize U_t until U_t <= tau
        2. Efficiency mode: minimize C_t while staying feasible
        """

        # Stage 1: Feasibility recovery (if infeasible)
        if ledger.U_t > tau:
            return MetaGovernorObjective._feasibility_recovery(
                ledger, available_actions, tau
            )

        # Stage 2: Efficiency mode (if feasible)
        return MetaGovernorObjective._efficiency_optimization(
            ledger, available_actions, tau
        )

    @staticmethod
    def _feasibility_recovery(
        ledger: DualLedger,
        available_actions: List[VerificationAction],
        tau: float
    ) -> ActionPlan:
        """Minimize U_t until feasible. Cost is secondary."""

        selected = []
        predicted_U = ledger.U_t

        # Greedy: pick actions that reduce U_t most
        remaining = list(available_actions)
        while predicted_U > tau and remaining:
            best = max(remaining, key=lambda a: a.expected_uncertainty_reduction)
            if best.expected_uncertainty_reduction <= 0:
                break  # No progress possible

            selected.append(best)
            predicted_U -= best.expected_uncertainty_reduction
            remaining.remove(best)

        return ActionPlan(
            actions=selected,
            mode="feasibility_recovery",
            predicted_U_t=predicted_U,
            predicted_C_t=ledger.C_t + sum(a.cost for a in selected)
        )

    @staticmethod
    def _efficiency_optimization(
        ledger: DualLedger,
        available_actions: List[VerificationAction],
        tau: float
    ) -> ActionPlan:
        """Minimize C_t while maintaining U_t <= tau."""

        # Already feasible - only take actions with positive ROI
        selected = []

        for action in available_actions:
            # Check if action maintains feasibility
            new_U = ledger.U_t - action.expected_uncertainty_reduction

            # Only take if it improves efficiency (cost per uncertainty reduction)
            if action.cost > 0:
                roi = action.expected_uncertainty_reduction / action.cost
                if roi > MIN_ROI_THRESHOLD:
                    selected.append(action)

        return ActionPlan(
            actions=selected,
            mode="efficiency",
            predicted_U_t=ledger.U_t - sum(a.expected_uncertainty_reduction for a in selected),
            predicted_C_t=ledger.C_t + sum(a.cost for a in selected)
        )
```

---

## Production Hardening

Critical issues that will bite in production:

### Workload-Shift Blindness (Simpson's Paradox)

Metrics can look "better" because task mix changed, not because theta improved.

```python
@dataclass
class StratifiedMetrics:
    """Metrics stratified by task class to prevent Simpson's paradox."""

    overall: PerformanceMetrics
    by_task_class: Dict[str, PerformanceMetrics]
    task_class_distribution: Dict[str, float]  # Fraction of tasks

    def compare_fair(self, baseline: 'StratifiedMetrics') -> ComparisonResult:
        """
        Compare metrics controlling for task mix.

        Reweights current metrics to baseline's task distribution.
        """
        reweighted = PerformanceMetrics()

        for task_class, baseline_weight in baseline.task_class_distribution.items():
            class_metrics = self.by_task_class.get(task_class)
            if class_metrics:
                reweighted.accumulate(class_metrics, weight=baseline_weight)

        return ComparisonResult(
            raw_comparison=self.overall.compare(baseline.overall),
            fair_comparison=reweighted.compare(baseline.overall),
            distribution_shift=self._compute_distribution_shift(baseline)
        )
```

### Credit Assignment: One Delta-theta at a Time

Multiple changes per epoch leads to cargo-cult tuning.

```python
class SingleChangeEnforcer:
    """Enforce one theta change at a time unless operator override."""

    def __init__(self, min_epochs_between_changes: int = 1):
        self._last_change_epoch: Optional[int] = None
        self._current_epoch: int = 0
        self._min_epochs = min_epochs_between_changes

    def can_accept_change(self, operator_override: bool = False) -> bool:
        if operator_override:
            return True

        if self._last_change_epoch is None:
            return True

        epochs_since_change = self._current_epoch - self._last_change_epoch
        return epochs_since_change >= self._min_epochs

    def record_change(self):
        self._last_change_epoch = self._current_epoch

    def advance_epoch(self):
        self._current_epoch += 1
```

### Update Cadence and Sample Size

Tuning too fast amplifies noise into oscillation.

```python
@dataclass
class UpdateCadenceConfig:
    """Minimum requirements before theta update is considered."""

    min_tasks_per_measurement: int = 100
    min_seconds_per_epoch: float = 3600  # 1 hour
    min_verifier_samples: int = 50

    # Noise reduction
    use_ewma: bool = True
    ewma_alpha: float = 0.1
```

### Correlated Model Failures

Multi-model checks aren't independent if models share training priors.

```python
def compute_effective_agreement(
    model_results: Dict[str, Result],
    model_family_map: Dict[str, str]
) -> float:
    """
    Discount agreement between models from same family.

    Cross-family agreement is strong evidence.
    Same-family agreement is weak evidence.
    """
    families = set(model_family_map.values())

    # Group by family
    family_results = defaultdict(list)
    for model, result in model_results.items():
        family = model_family_map.get(model, model)
        family_results[family].append(result)

    # Agreement within family: weak (weight 0.3)
    # Agreement across family: strong (weight 1.0)
    # Must anchor to tool/ground-truth for full confidence

    cross_family_agreement = ...
    return cross_family_agreement

# Rule: Cross-model agreement without tool verification is WEAK evidence
```

### Tool Result Reproducibility

Flaky or adversarial tools can't close blockers reliably.

```python
def verify_tool_reproducibility(
    tool: str,
    query: str,
    result: ToolResult,
    num_retries: int = 2
) -> ReproducibilityResult:
    """
    If tool output can't be reproduced, it closes blocker with lower weight.
    """
    results = [result]

    for _ in range(num_retries):
        retry_result = execute_tool(tool, query)
        results.append(retry_result)

    # Check consistency
    if all_results_match(results):
        return ReproducibilityResult(reproducible=True, weight=1.0)
    elif majority_match(results):
        return ReproducibilityResult(reproducible=False, weight=0.5)
    else:
        return ReproducibilityResult(reproducible=False, weight=0.1)
```

### Canary Rotation (Prevent Goodhart on Harness)

```python
class CanaryRotation:
    """Rotate canaries to prevent overfitting."""

    def __init__(
        self,
        canary_pool: List[CanaryTask],
        active_fraction: float = 0.5,
        rotation_interval_epochs: int = 10,
        holdout_fraction: float = 0.2  # Never seen during theta tuning
    ):
        self._pool = canary_pool
        self._holdout = random.sample(canary_pool, int(len(canary_pool) * holdout_fraction))
        self._active = None
        self._rotation_counter = 0

    def get_active_canaries(self) -> List[CanaryTask]:
        """Get current active canary set (rotates periodically)."""
        if self._active is None or self._rotation_counter >= self.rotation_interval_epochs:
            available = [c for c in self._pool if c not in self._holdout]
            self._active = random.sample(available, int(len(available) * self._active_fraction))
            self._rotation_counter = 0
        return self._active

    def get_holdout_canaries(self) -> List[CanaryTask]:
        """Holdout set for generalization testing before accepting long-term theta changes."""
        return self._holdout
```

### State Persistence (Cold Start Problem)

```python
@dataclass
class PersistentState:
    """State that must survive restarts to prevent amnesia arbitrage."""

    theta_snapshots: List[ThetaSnapshot]
    current_theta: GovernorParams
    dual_ledger: DualLedger
    regime_history: RegimeHistory
    baseline_metrics: BaselineMetrics
    policy_hash: str
    last_evaluation_window: EvaluationWindow

    def save(self, path: Path):
        """Persist to disk (use JSON/msgpack, NOT pickle)."""
        ...

    @classmethod
    def load(cls, path: Path) -> 'PersistentState':
        """Load from disk."""
        ...

# On startup: MUST load persistent state or start in LOCKDOWN
```

### Authority Spoofing Prevention

```python
class OperatorAuthority:
    """
    Formal identity channel for operator authority.

    Authority comes from OUT-OF-BAND credential, not in-band claims.
    """

    def __init__(self, credential_verifier: CredentialVerifier):
        self._verifier = credential_verifier

    def verify_operator(self, credential: bytes) -> AuthorityResult:
        """
        Verify operator identity via cryptographic credential.

        NOT via:
        - String in prompt ("I am the operator")
        - API key in message
        - Any in-band claim
        """
        if self._verifier.verify(credential):
            return AuthorityResult(
                verified=True,
                identity=self._verifier.extract_identity(credential),
                capabilities=self._verifier.extract_capabilities(credential)
            )
        return AuthorityResult(verified=False)

# Rule: Any in-band claim of authority is UNTRUSTED
```

### Emergency Stop (E-Stop)

Different from freeze: forces maximum restriction.

```python
class EmergencyStop:
    """
    E-stop: Maximum restriction mode.

    Different from freeze (which just pauses self-tuning).
    E-stop forces LOCKDOWN + no theta updates + no side effects + require operator.
    """

    @staticmethod
    def trigger(governor: Governor, reason: str):
        """Trigger emergency stop."""
        # Force LOCKDOWN
        governor.force_regime(Regime.LOCKDOWN)

        # Freeze all self-tuning
        governor.meta_governor.freeze()

        # Disable all side effects
        governor.disable_all_side_effects()

        # Require operator to resume
        governor.require_operator_for_resume()

        # Log with high severity
        governor.audit_log.record_estop(reason)

    ALLOWED_ESCAPE_ACTIONS = [
        "ask_operator",
        "request_more_input",
        "degrade_to_no_commit",
        "emit_uncertainty_flag",
    ]

    FORBIDDEN_ESCAPE_ACTIONS = [
        "silent_waiver",
        "loosen_tau_without_gate",
        "expand_tool_surface",
        "self_approve_action",
    ]
```

### Proof-Carrying Delta-theta

Acceptance requires machine-checkable "why" bundle.

```python
@dataclass
class ProofCarryingDelta:
    """
    Every accepted delta-theta must carry its proof.
    No prose - machine-checkable only.
    """

    delta: ThetaDelta

    # Evidence used
    measurements_snapshot: AdmissibleMeasurements
    measurement_timestamps: Dict[str, datetime]

    # Thresholds applied
    significance_thresholds_used: Dict[str, SignificanceConfig]

    # Invariants checked
    invariants_checked: List[str]
    invariant_results: Dict[str, InvariantResult]

    # Predicted effect
    predicted_U_t_change: float
    predicted_C_t_change: float

    # Hash for tamper evidence
    proof_hash: str

    def verify_self_consistency(self) -> bool:
        """Verify the proof bundle is internally consistent."""
        computed_hash = self._compute_hash()
        return computed_hash == self.proof_hash

    def _compute_hash(self) -> str:
        # Hash all fields except proof_hash itself
        ...
```

---

## Capability Discipline

**Rule:** Self-tuning cannot expand its own tool surface.

```python
class CapabilityDiscipline:
    """Constraints on what meta-governor can modify."""

    # Meta-governor can adjust these (with directional constraints)
    TUNABLE_PARAMS = {
        "tau": TunableConfig(
            direction="bidirectional",
            bounds=(0.1, 10.0),
            operator_required_for=None
        ),
        "confidence_cap": TunableConfig(
            direction="bidirectional",
            bounds=(0.3, 0.95),
            operator_required_for=None
        ),
        "regime_thresholds": TunableConfig(
            direction="bidirectional",
            bounds=None,
            operator_required_for=None
        ),
        "verification_budget": TunableConfig(
            direction="increase_needs_operator",
            bounds=(0.01, 1.0),
            operator_required_for="increase"
        ),
        "tool_trust_scores": TunableConfig(
            direction="decrease_only",
            bounds=(0.0, 1.0),
            operator_required_for="increase"
        ),
    }

    # Meta-governor CANNOT touch these
    PROTECTED_PARAMS = {
        "available_tools",          # Cannot add new tools
        "network_access",           # Cannot grant broader access
        "side_effect_permissions",  # Cannot grant higher permissions
        "operator_identity",        # Cannot change who has authority
        "meta_invariants",          # Cannot modify its own constraints
        "protected_params",         # Cannot modify this list (self-reference)
        "significance_config",      # Cannot modify significance thresholds
        "canary_holdout_set",       # Cannot see or modify holdout canaries
    }

    @staticmethod
    def validate_proposed_change(
        delta: ThetaDelta,
        current_value: Any,
        has_operator_approval: bool
    ) -> ValidationResult:
        """Validate change respects capability discipline."""

        # Reject changes to protected params
        if delta.param_name in CapabilityDiscipline.PROTECTED_PARAMS:
            return ValidationResult(
                allowed=False,
                reason=f"Parameter {delta.param_name} is protected"
            )

        # Check if param is tunable
        config = CapabilityDiscipline.TUNABLE_PARAMS.get(delta.param_name)
        if config is None:
            return ValidationResult(
                allowed=False,
                reason=f"Unknown parameter {delta.param_name}"
            )

        # Check directional constraints
        if config.direction == "decrease_only":
            if delta.new_value > current_value:
                if not has_operator_approval:
                    return ValidationResult(
                        allowed=False,
                        reason=f"Increasing {delta.param_name} requires operator approval"
                    )

        if config.direction == "increase_needs_operator":
            if delta.new_value > current_value and not has_operator_approval:
                return ValidationResult(
                    allowed=False,
                    reason=f"Increasing {delta.param_name} requires operator approval"
                )

        # Check bounds
        if config.bounds:
            if not (config.bounds[0] <= delta.new_value <= config.bounds[1]):
                return ValidationResult(
                    allowed=False,
                    reason=f"{delta.param_name} out of bounds {config.bounds}"
                )

        return ValidationResult(allowed=True)

@dataclass
class TunableConfig:
    direction: str  # "bidirectional", "decrease_only", "increase_needs_operator"
    bounds: Optional[Tuple[float, float]]
    operator_required_for: Optional[str]  # "increase", "decrease", or None
```

---

## Signed Policy Snapshots (Constitutional Hash)

Every theta snapshot includes a hash of the constitution (protected params + meta-invariants).

```python
@dataclass
class ConstitutionalHash:
    """
    Hash of the 'constitution' - protected params and meta-invariants.

    This makes "can't change the rules quietly" enforceable.
    """

    protected_params_hash: str
    meta_invariants_hash: str
    significance_config_hash: str
    combined_hash: str

    @classmethod
    def compute(cls, config: GovernorConfig) -> 'ConstitutionalHash':
        protected_hash = hashlib.sha256(
            json.dumps(sorted(config.protected_params)).encode()
        ).hexdigest()

        invariants_hash = hashlib.sha256(
            json.dumps([inv.name for inv in config.meta_invariants]).encode()
        ).hexdigest()

        significance_hash = hashlib.sha256(
            json.dumps(config.significance_config, sort_keys=True).encode()
        ).hexdigest()

        combined = hashlib.sha256(
            (protected_hash + invariants_hash + significance_hash).encode()
        ).hexdigest()

        return cls(
            protected_params_hash=protected_hash,
            meta_invariants_hash=invariants_hash,
            significance_config_hash=significance_hash,
            combined_hash=combined
        )

class ConstitutionalGuard:
    """
    Guard that rejects proposals if constitution has changed.

    Constitutional revision requires explicit operator event.
    """

    def __init__(self, initial_hash: ConstitutionalHash):
        self._current_hash = initial_hash
        self._revision_history: List[ConstitutionalRevision] = []

    def check_consistency(self, proposal_hash: ConstitutionalHash) -> bool:
        """Reject if constitution has changed without revision event."""
        return proposal_hash.combined_hash == self._current_hash.combined_hash

    def record_revision(
        self,
        new_hash: ConstitutionalHash,
        operator_credential: bytes,
        reason: str
    ):
        """
        Record a constitutional revision.

        Requires operator authority + explicit reason.
        """
        # Verify operator
        if not verify_operator(operator_credential):
            raise AuthorizationError("Constitutional revision requires operator")

        self._revision_history.append(ConstitutionalRevision(
            timestamp=datetime.now(),
            old_hash=self._current_hash,
            new_hash=new_hash,
            reason=reason,
            operator=extract_operator_id(operator_credential)
        ))

        self._current_hash = new_hash
```

---

## Runtime Test Harness

3.x: Self-tuning implies continuous evaluation. The harness is a first-class component.

```python
class SelfGovernanceHarness:
    """Runtime testing for self-governing systems."""

    def __init__(self, config: HarnessConfig):
        self.canary_rotation = CanaryRotation(
            canary_pool=config.canary_tasks,
            holdout_fraction=0.2
        )
        self.metamorphic_suite = config.metamorphic_suite
        self.drift_detectors = config.drift_detectors
        self.check_interval = config.check_interval

    async def run_continuous_evaluation(self, governor: Governor):
        """Run continuously alongside governor."""

        while True:
            await asyncio.sleep(self.check_interval)

            # Run canary tasks (rotated set)
            canary_results = await self.run_canaries(
                governor,
                self.canary_rotation.get_active_canaries()
            )
            if not canary_results.all_passed:
                await self.trigger_freeze(governor, "canary_failure", canary_results)
                continue

            # Sample metamorphic tests
            metamorphic_results = await self.sample_metamorphic(governor)
            if metamorphic_results.violation_rate > 0.1:
                await self.trigger_freeze(governor, "metamorphic_violation", metamorphic_results)
                continue

            # Check drift
            drift_report = self.check_drift(governor.telemetry)
            if drift_report.significant_drift:
                await self.trigger_investigation(governor, drift_report)

    async def run_holdout_validation(self, governor: Governor) -> HoldoutResults:
        """
        Run holdout canaries before accepting long-term theta changes.

        This prevents Goodhart on the active canary set.
        """
        holdout = self.canary_rotation.get_holdout_canaries()
        return await self.run_canaries(governor, holdout)


class FreezeController:
    """
    Manages freeze state with sovereignty rules.

    Critical: meta-governor cannot unfreeze itself.
    """

    def __init__(self):
        self._frozen = False
        self._freeze_reason: Optional[str] = None
        self._frozen_by: Optional[str] = None
        self._frozen_at: Optional[datetime] = None

    def freeze(self, reason: str, details: Any, frozen_by: str):
        """Enter frozen state."""
        self._frozen = True
        self._freeze_reason = reason
        self._frozen_by = frozen_by
        self._frozen_at = datetime.now()

    def request_unfreeze(
        self,
        operator_credential: bytes,
        canary_results: CanaryResults
    ) -> UnfreezeResult:
        """
        Request unfreeze.

        Requirements:
        1. Valid operator credential
        2. Canaries passing
        3. Minimum freeze duration elapsed
        """
        if not verify_operator(operator_credential):
            return UnfreezeResult(success=False, reason="Invalid operator credential")

        if not canary_results.all_passed:
            return UnfreezeResult(success=False, reason="Canaries not passing")

        MIN_FREEZE_DURATION = timedelta(minutes=5)
        if datetime.now() - self._frozen_at < MIN_FREEZE_DURATION:
            return UnfreezeResult(success=False, reason="Minimum freeze duration not elapsed")

        self._frozen = False
        return UnfreezeResult(success=True)

    @property
    def is_frozen(self) -> bool:
        return self._frozen
```

---

## Combinatorial Testing for Adaptation

Test **scenario interactions**, not just static configs:

```python
ADAPTATION_SCENARIO_FACTORS = {
    "evidence_quality": ["low", "high", "contradictory"],
    "tool_health": ["ok", "degraded", "unavailable"],
    "model_reliability": ["normal", "drift", "adversarial"],
    "workload": ["single", "burst", "long_chain"],
    "update_policy": ["aggressive", "conservative", "frozen"],
    "operator": ["none", "intermittent", "active"],
    "attack_surface": [
        "none",
        "prompt_injection",
        "tool_output_poisoning",
        "operator_spoofing",
        "policy_bypass_phrasing"
    ],
}

def generate_adaptation_test_suite(t: int = 2) -> List[AdaptationScenario]:
    """Generate t-way covering array over adaptation scenarios."""
    return generate_covering_array(ADAPTATION_SCENARIO_FACTORS, strength=t)

def find_adaptation_counterexamples(
    governor: Governor,
    meta_invariants: List[MetaInvariant]
) -> List[Counterexample]:
    """
    Find smallest scenarios where adaptation breaks invariants.
    """
    suite = generate_adaptation_test_suite(t=3)
    counterexamples = []

    for scenario in suite:
        env = create_test_environment(scenario)
        governor.meta_governor.unfreeze()
        results = run_scenario(governor, env)

        for inv in meta_invariants:
            if not inv.check(results.theta_history):
                counterexamples.append(Counterexample(
                    scenario=scenario,
                    invariant_violated=inv.name,
                    theta_trace=results.theta_history,
                    trigger_point=find_trigger_point(results, inv)
                ))

    return counterexamples
```

---

## Stability Properties for Adaptation Loop

Treat adaptation as a control loop and verify stability:

```python
class AdaptationStabilityChecker:
    """Check that self-governance loop is stable."""

    @staticmethod
    def lyapunov_surrogate(
        U_history: List[float],
        theta_history: List[GovernorParams]
    ) -> bool:
        """
        Require E[U_{t+1}] <= U_t under "no new info" conditions.

        If uncertainty increases without new information,
        the system is injecting chaos.
        """
        no_info_periods = find_no_info_periods(theta_history)

        for start, end in no_info_periods:
            U_start = U_history[start]
            U_end = U_history[end]

            if U_end > U_start * 1.05:  # 5% tolerance
                return False

        return True

    @staticmethod
    def anti_windup_check(
        theta_history: List[GovernorParams],
        max_integral: float
    ) -> bool:
        """
        Cap integral-like accumulation.

        Don't let repeated "tool flaky" events tighten forever.
        """
        cumulative_delta = 0

        for i in range(1, len(theta_history)):
            delta = theta_history[i].tau - theta_history[i-1].tau

            if delta < 0:  # Tightening
                cumulative_delta += abs(delta)
            else:  # Loosening resets accumulator
                cumulative_delta = max(0, cumulative_delta - delta)

        return cumulative_delta <= max_integral

    @staticmethod
    def dwell_time_compliance(
        regime_history: List[Tuple[datetime, Regime]],
        min_dwell: timedelta
    ) -> bool:
        """Check minimum time in each regime before switching."""
        for i in range(1, len(regime_history)):
            prev_time, prev_regime = regime_history[i-1]
            curr_time, curr_regime = regime_history[i]

            if curr_regime != prev_regime:
                dwell = curr_time - prev_time
                if dwell < min_dwell:
                    return False

        return True
```

---

## Meta-Audit Log

Log fields that are **structural** and hard to game:

```python
@dataclass
class MetaAuditEntry:
    """Audit log for self-governance that can't be optimized away."""

    timestamp: datetime

    # Structural counts (hard to fake)
    blocker_count_by_class: Dict[str, int]
    evidence_provenance_types_used: Set[str]
    theta_change_count_this_epoch: int
    regime_dwell_distribution: Dict[Regime, float]
    rollback_count_this_epoch: int

    # Calibration checks
    predicted_vs_observed_f1: Tuple[float, float]
    predicted_vs_observed_f2: Tuple[float, float]

    # Economic
    verification_spend_this_epoch: float
    latency_budget_remaining: float

class MetaAuditLog:
    """Tamper-evident log of self-governance decisions."""

    def __init__(self):
        self._entries: List[MetaAuditEntry] = []
        self._hash_chain: List[str] = []  # For tamper evidence

    def append(self, entry: MetaAuditEntry):
        prev_hash = self._hash_chain[-1] if self._hash_chain else "genesis"
        entry_hash = hash_entry(entry, prev_hash)

        self._entries.append(entry)
        self._hash_chain.append(entry_hash)

    def detect_anomalies(self) -> List[Anomaly]:
        """Flag suspicious patterns in meta-audit log."""
        anomalies = []
        # Blocker count suddenly drops without verification activity
        # Theta changes without corresponding measurement justification
        # Predicted vs observed divergence
        return anomalies
```

---

## Cross-Model Validation for Self-Modification

**Constitutional Rule:** No delta-theta may be applied unless corroborated by an independent validator set.

Single-model self-modification is categorically illegitimate. If the system can rewrite its own constraints based on one narrator, you've built a self-justifying bureaucracy with autocomplete.

### Validator Quorum Policy

Three roles, require at least two to sign off:

| Role | Purpose | Provider |
|------|---------|----------|
| Proposer | Generates delta-theta | Meta-governor's resident model |
| Independent Reviewer | Confirms warrant | Different provider/family |
| Adversarial Reviewer | Finds problems | Tasked to find why delta-theta is unsafe |

**Acceptance rule (baseline):**
- Must have admissible measurement coverage
- Must have >= 1 independent reviewer approve
- Must have adversarial reviewer fail to produce valid veto

**High-impact changes** (tau, regime thresholds, tool trust increases, budgets, waiver mechanics):
- Require 2 independent reviewers, OR
- 1 reviewer + tool-based verification

### Veto Power (Not Vibes)

Adversarial reviewer veto is valid **only** if it produces one of:

| Witness Type | Definition |
|--------------|------------|
| Policy-violation | Shows invariant violated in some scenario |
| Oscillation | Predictable limit-cycle/thrash under scenario factors |
| Laundering | Delta-theta reduces U without legitimate closure path |
| Capability expansion | Increases tools/permissions/budgets beyond allowed |

No other veto allowed. Prevents "adversary always says no."

### Independence Requirements

```python
class ValidatorRequirements:
    """Ensure validators aren't correlated hallucination machines."""

    PROVIDER_DIVERSITY_REQUIRED = True
    MIN_DISTINCT_PROVIDERS = 2  # e.g., Anthropic + OpenAI, not GPT-4 + GPT-4-turbo
    ROLE_SEPARATION_PROMPTS = True  # Reviewer must re-derive, not just critique
    MEASUREMENT_ONLY_BUNDLES = True  # No proposer prose, only telemetry + delta-theta + invariants

def validate_validator_set(validators: List[Validator]) -> bool:
    """Check validator set meets independence requirements."""
    providers = {v.provider for v in validators}

    if len(providers) < ValidatorRequirements.MIN_DISTINCT_PROVIDERS:
        return False

    for v in validators:
        if v.has_access_to_proposer_reasoning:
            return False

    return True
```

### Validator Input Bundle

Validators receive structured data, not prose:

```python
@dataclass
class ValidationBundle:
    """Input to validators - no narrative, only facts."""

    proposed_delta: ThetaDelta
    measurements: AdmissibleMeasurements
    invariants: List[MetaInvariant]
    current_theta: GovernorParams
    scenario_coverage: List[AdaptationScenario]

    # NOT INCLUDED:
    # - Proposer's reasoning/justification
    # - Prose explanation of why this is good
    # - Chain-of-thought from proposer

@dataclass
class ValidationResponse:
    """Output from validator - structured, not prose."""

    decision: Literal["APPROVE", "REJECT", "VETO"]
    checks_passed: List[str]
    rejection_reasons: List[str]
    veto_witness: Optional[VetoWitness]

@dataclass
class VetoWitness:
    """Concrete evidence for veto - not vibes."""

    witness_type: Literal[
        "policy_violation",
        "oscillation",
        "laundering",
        "capability_expansion"
    ]
    scenario: Dict[str, Any]
    property_violated: str
    verification_command: Optional[str]
```

### Cost Containment

```python
REQUIRES_CROSS_MODEL_VALIDATION = {
    "theta_update": True,
    "update_cadence_change": True,
    "significance_threshold_change": True,
    "rollback_override": True,
    "freeze_override": True,
    "task_execution": False,
    "verification_action": False,
    "regime_transition": False,  # Already gated by hysteresis
}

def select_validator_strength(change: ProposedChange) -> ValidatorConfig:
    """Scale validator requirements to change impact."""

    if change.impacts_safety_invariants:
        return ValidatorConfig(
            min_independent_reviewers=2,
            require_adversarial=True,
            require_tool_verification=True
        )
    elif change.impacts_capability:
        return ValidatorConfig(
            min_independent_reviewers=2,
            require_adversarial=True,
            require_tool_verification=False
        )
    else:
        return ValidatorConfig(
            min_independent_reviewers=1,
            require_adversarial=True,
            require_tool_verification=False
        )
```

### The Gate

```python
class CrossModelValidationGate:
    """Constitutional enforcement for self-modification."""

    def __init__(self, validators: List[Validator]):
        self.validators = validators
        self.audit_log = AuditLog()

    def evaluate(
        self,
        proposed_delta: ThetaDelta,
        measurements: AdmissibleMeasurements,
        current_theta: GovernorParams
    ) -> GateDecision:

        bundle = ValidationBundle(
            proposed_delta=proposed_delta,
            measurements=measurements,
            invariants=META_INVARIANTS,
            current_theta=current_theta,
            scenario_coverage=self._get_relevant_scenarios(proposed_delta)
        )

        responses = []
        for validator in self.validators:
            response = validator.validate(bundle)
            responses.append(response)
            self.audit_log.record(validator.id, response)

        # Check for valid veto
        vetoes = [r for r in responses if r.decision == "VETO" and r.veto_witness]
        for veto in vetoes:
            if self._is_valid_witness(veto.veto_witness):
                return GateDecision(
                    allowed=False,
                    reason=f"Valid veto: {veto.veto_witness.witness_type}",
                    witness=veto.veto_witness
                )

        # Count approvals
        approvals = sum(1 for r in responses if r.decision == "APPROVE")
        required = select_validator_strength(proposed_delta).min_independent_reviewers

        if approvals >= required:
            return GateDecision(allowed=True, reason="Quorum reached")
        else:
            return GateDecision(
                allowed=False,
                reason=f"Insufficient approvals: {approvals}/{required}"
            )

    def _is_valid_witness(self, witness: VetoWitness) -> bool:
        """Verify the veto witness is concrete, not vibes."""

        if witness.witness_type not in {
            "policy_violation", "oscillation", "laundering", "capability_expansion"
        }:
            return False

        if not witness.scenario:
            return False

        if not witness.property_violated:
            return False

        if witness.verification_command:
            result = run_verification(witness.verification_command)
            return result.confirms_violation

        return True
```

---

## Math Modules by Maturity Tier

### Tier 1: Ship-Now Bedrock (3.x won't survive without these)

| Module | Use | Why Critical |
|--------|-----|--------------|
| **Sequential analysis / SPRT** | Replace `is_significant()` | Otherwise you tune on noise |
| **Change-point detection** | Detect when telemetry shifts | Triggers investigation vs normal drift |
| **Queueing/backpressure** | Latency + tool contention | Self-tuning will destabilize without this |
| **Formal-ish invariants** | Executable MUST/MUST NOT gates | Policy hashing, constitution enforcement |
| **Causal guardrails (light)** | Stratify by task class | Don't "improve" by workload drift |

```python
# Example: Replace vibes with SPRT
from scipy.stats import norm

def is_significant_sprt(
    observations: List[float],
    null_mean: float,
    alt_mean: float,
    alpha: float = 0.05,
    beta: float = 0.10
) -> Literal["ACCEPT_NULL", "ACCEPT_ALT", "CONTINUE"]:
    """
    Sequential Probability Ratio Test.
    Actually principled, unlike `if mean > threshold`.
    """
    A = (1 - beta) / alpha  # Upper boundary
    B = beta / (1 - alpha)  # Lower boundary

    log_ratio = 0
    for x in observations:
        log_ratio += (
            norm.logpdf(x, alt_mean, 1) -
            norm.logpdf(x, null_mean, 1)
        )

    ratio = np.exp(log_ratio)

    if ratio >= A:
        return "ACCEPT_ALT"  # Significant change
    elif ratio <= B:
        return "ACCEPT_NULL"  # No change
    else:
        return "CONTINUE"  # Need more data
```

### Tier 2: Near-Term Cheap Wins

| Module | Use | Implementation |
|--------|-----|----------------|
| **Robust statistics** | Telemetry aggregation | Trimmed means, median-of-means |
| **VOI heuristic** | Verifier selection | "Expected U drop per $" |
| **Stratified metrics** | Causal guardrails | Group by task class before comparing |

### Tier 3: ROADMAP (Real, but don't let it eat your life)

| Module | Use | When to Add |
|--------|-----|-------------|
| **Full formal methods** | Model checking pipeline | When you have proven failure modes to prevent |
| **Causal inference (DiD, propensity)** | Credit assignment | When simple stratification isn't enough |
| **Constrained bandits** | Multi-model arbitrage at scale | When you have enough traffic to learn |
| **Bifurcation analysis** | Debugging oscillations | When you're seeing regime thrash |
| **Game theory / mechanism design** | Adversarial users | When deployed to untrusted populations |
| **Information-theoretic laundering detection** | "U drops without info gain" | When you suspect gaming |

> "Math is the one place where the universe can't gaslight you."

---

## Known 3.x Gaps (To Solve When Building, Not Now)

### Gap 1: Correlation Classes for Validators

"Different provider/family" is a rule of thumb. Need formal definition:
- Each validator has a **correlation class** (provider + family + deployment context)
- Quorum requires **>= 2 distinct correlation classes**
- Fallback to tool-anchored checks or operator if can't satisfy

### Gap 2: Validator Cost Control (DoS Prevention)

Attackers can force frequent delta-theta proposals and burn wallet on validators:
- Max delta-theta attempts per epoch
- Cooldown after rejection
- Validator budget ledger (counts toward C_t)
- Freeze self-tuning if validation spend exceeds budget without improvement

### Gap 3: Policy Hash Completeness

Hash must include *everything* that defines power:
- Protected params + invariants + significance config (done)
- **Also:** validator quorum rules, harness holdout policy, operator credential config, update cadence rules

### Gap 4: Proof-Carrying Delta-theta (Positive Witnesses)

Every accepted delta-theta should carry a positive witness:
- "Here's the minimal scenario set where delta-theta improves objective without violating invariants"
- Replay command / seed / fixture id

### Gap 5: Canonical U_t Definition

U_t is used everywhere but 3.x introduces stratified metrics, proof bundles, reproducibility weights. Need:
```
U_t = f(claim_set, blocker_weights, verifier_provenance, reproducibility_weights, waiver_class)
```

### Gap 6: Tool Reproducibility Semantics

"All results match" needs equivalence definition:
- Normalization, tolerance, semantic equivalence class
- For text: hash structured fields, exact match on cited source IDs, or treat as non-reproducible by default

### Gap 7: Baselines Per Regime

EWMA smears across step changes. Need:
- Separate baselines per regime (ELASTIC/WARM/LOCKDOWN)
- Optionally per tool-health state
- Baseline reset operator event

### Gap 8: Persistence Format

Don't pickle. Use:
- JSON/msgpack + schema versioning
- Or SQLite
- Plus signatures/MAC for tamper evidence

### Gap 9: Constitutional Revision Events

Make workflow explicit:
- Normal delta-theta must fail if constitutional hash differs
- Only way to change: RevisionEvent with operator credential + reason + diff
- RevisionEvent forces holdout canary run before resuming self-tuning

### Gap 10: Laundering Check Implementation Bug

The check for `blocker_criteria` references wrong field. Fix when implementing.

### Gap 11: Auth Infrastructure (Service Boundary)

When governor becomes a shared service, need:
- Principal types (`human`, `agent`, `service_account`)
- Capability token format + fields (`{sub, scopes, constraints, exp, nonce, proof_hash}`)
- "No in-band authority claims" as top-level invariant
- `/attest` endpoint (policy hash, θ hash, quorum policy version, audit log head)
- Default bind policy + explicit "public exposure" interlock
- Stubbed `AuthorityEvent` middleware in 2.x as 3.x seam

### Gap 12: Multi-Tenant Isolation

Per-tenant U_t/C_t ledgers, per-principal verification budgets, side-effect namespacing. Without this, shared deployment is a noise-coupling problem.

### Gap 13: Delegation Chain Limits

Forbid transitive delegation. Max one hop. Break-glass mode for emergency operator override with forced LOCKDOWN + token revocation.

---

## 3.x Service Boundary: Auth, Identity, and Authority

Auth is the tell. It's where "library in my repo" stops and "shared plant component" begins.

### The Transition

**2.x (now):** Governor is a library/CLI. "Who's calling" is implicit — it's you, locally, or Claude Code in your repo. Auth is filesystem permissions. FastAPI for WebUI, no auth, localhost only.

**3.x (self-governance):** Governor becomes a shared service. It needs to know:
- Is this an **operator** (can issue waivers, constitutional revisions)?
- Is this a **delegated agent** (trusted identity, adversarial intent)?
- Is this a **public user** (minimal trust, strict constraints)?

### Deployment Authority Tiers

```
A1: PUBLIC    — untrusted user, minimal tools, strict evidence
A2: DELEGATED — trusted identity, untrusted intent, limited tools + two-phase commit
A3: OPERATOR  — staff/admin, broad tools + heavy audit
A4: RUNBOOK   — pre-approved action sets (not a role — a mode under contract)
```

The `deployment_profiles.py` spec already has the *policy* for these tiers. Implementation waits until governor becomes a shared service.

**A4 clarification:** AUTONOMOUS is not a role; it's a mode under contract. It's a **runbook**: pre-approved actions + pre-approved verifiers + constraints, signed, versioned, revocable, executing as a service account with narrow capability set. A4 = "execute runbook R under profile P," not "this caller is autonomous."

### Core Model: Split Identity from Authority

JWT/OAuth answers "who are you," not "what are you allowed to do *right now*." Make it explicit:

| Layer | Purpose | Mechanism |
|-------|---------|-----------|
| **Identity** | user/agent/operator principal | OAuth for humans, API keys for agents |
| **Authority** | capability token / signed grant | Scoped, expiring, auditable |
| **Context** | deployment profile + regime + U_t | Can *shrink* authority dynamically |

**Capability tokens are the real control plane.** OAuth/JWT is merely an identity bootstrap.

### Principal Types

```python
class PrincipalKind(str, Enum):
    HUMAN = "human"            # OAuth/JWT authenticated
    AGENT = "agent"            # API key + delegation chain
    SERVICE_ACCOUNT = "service_account"  # Runbook executor
```

### Capability Token Format

```python
@dataclass
class CapabilityToken:
    """Scoped, expiring, auditable authority grant."""

    sub: str                    # Principal identifier
    scopes: list[str]           # e.g., ["can:waive[class=low,max=3/day]", "can:propose"]
    constraints: dict[str, Any] # Bound to deployment profile, constitutional hash, toolset hash
    exp: str                    # ISO datetime expiry (short TTL)
    nonce: str                  # Replay protection — one-shot for admin actions
    proof_hash: str             # Hash of {sub, scopes, constraints, exp, nonce}
    issued_by: str              # Issuer principal
    issued_at: str              # ISO datetime

    # Context binding — token invalid if these change
    bound_profile: str          # Deployment profile at issuance
    bound_constitutional_hash: str  # Constitutional hash at issuance
    bound_toolset_hash: str | None  # Optional toolset hash binding
```

### Service Boundary

```
┌─────────────────────────────────────────────┐
│              Governor Service                │
├─────────────────────────────────────────────┤
│  FastAPI + Auth                              │
│  ├── /api/v1/tasks      (submit work)        │
│  ├── /api/v1/state      (query U_t, claims)  │
│  ├── /api/v1/admin      (operator actions)   │
│  ├── /api/v1/revision   (constitutional)     │
│  └── /api/v1/attest     (remote attestation) │
├─────────────────────────────────────────────┤
│  Auth layer:                                 │
│  - API keys (agents)                         │
│  - JWT/OAuth (humans)                        │
│  - Capability tokens (scoped permissions)    │
│  - Operator credentials (signed, step-up)    │
├─────────────────────────────────────────────┤
│  ABAC decision function:                     │
│  allow(action) iff                           │
│    profile permits AND                       │
│    regime permits AND                        │
│    U_t permits AND                           │
│    capability token permits AND              │
│    meta-invariants permit                    │
└─────────────────────────────────────────────┘
```

RBAC is too coarse. Use ABAC-flavored checks — this fits monotonicity rules.

### /attest Endpoint

Returns verifiable system state for clients and operators. Without it, trust confusion happens fast.

```python
@dataclass
class AttestationResponse:
    """Remote attestation lite."""
    policy_hash: str                    # Constitutional hash
    theta_hash: str                     # Current θ parameters hash
    validator_quorum_policy_version: str # Quorum rules version
    audit_log_head_hash: str            # Hash chain head
    regime: str                         # Current regime
    timestamp: str                      # Signed timestamp
```

### Top-Level Invariant

**No in-band authority claims.** The governor never accepts "operator intent" via UI strings, prompt text, or message content. It accepts signed capabilities only.

### Auth Edge Cases

**Replay protection:** Capability tokens need nonce + short TTL. Admin actions should be one-shot. Otherwise "waiver" becomes a collectible.

**Delegation chains:** Forbid transitive delegation (`operator → agent → agent`). One hop max, or you'll never know who owns consequences.

**Step-up auth** for high-impact actions — even if you're "operator," require a fresh signature for:
- Constitutional revisions
- Tool-surface changes
- Budget increases
- Unfreezes / overrides

**Break-glass mode:** An operator-only emergency credential that:
- Forces LOCKDOWN
- Revokes all delegated tokens
- Rotates keys
- Emits an unmistakable audit event

### Capability Model Details

**Explicit deny beats allow.** Make "deny" compositional and sticky — easiest way to preserve monotonicity.

**Scopes encode constraints, not just verbs:**
- Not only `can:waive`, but `can:waive[class=low, max=3/day]`

**Context binding:** Tokens bind to deployment profile, current constitutional hash, and optionally toolset hash. If those change, tokens become invalid. Prevents "stale authority."

### Multi-Tenant Deployment Realities

**Per-tenant ledgers:** U_t and C_t must be per principal (or per workspace), not global. Otherwise one noisy user pushes everyone into LOCKDOWN.

**Fairness / rate limiting:** Treat verification spend like CPU:
- Per-principal budgets
- Burst limits
- Backpressure (already built in MCP safety controls)

**Side-effect isolation:** If tools touch the outside world:
- Per-tenant namespaces / sandboxes
- Immutable audit + idempotency keys
- Two-phase commit for side effects in A2/A1 tiers

### DELEGATED Tier Mechanics

Treat A2 as "trusted identity, adversarial intent." Make the mechanics match:
- Always operates under **two-phase commit**
- Any side-effect requires **operator cosign** or pre-approved action set
- **No in-band elevation, ever**

DELEGATED is where prompt injection and "helpful tool use" goes to die.

### Audit Log Hardening

**Tamper evidence isn't enough — make it queryable:**
- "Show me every waiver in last 24h, grouped by principal"
- "Show me all θ changes + witnesses"

**Redaction rules:** Logs will contain secrets unless planned:
- Strip tokens, API keys, raw tool outputs with secrets
- Keep hashes + provenance pointers

**Clock discipline:** Sign audit entries with a time source policy (or at least detect clock skew). Otherwise "today" becomes negotiable.

### API Design Constraints

**Idempotency keys** on `/tasks` and any side-effect path. Retries happen. Without this, double-execution makes audit ambiguous.

**Version everything:**
- θ schema
- Proof bundle schema
- Audit entry schema
- Validator policy schema

**Explicit commit object:** Even in 2.x, represent outputs as draft → verified → committed (or refused). Makes two-phase commit a natural extension, not a retrofit.

### Threat Model Specifics

**Tool-output poisoning:** Treat tool outputs as untrusted unless reproducible, provenance-verified, and signed/attested (if internal).

**Confused deputy:** The UI is untrusted input. The governor never accepts "operator intent" via UI — only signed capabilities.

**Model-family monoculture:** Enforce quorum across correlation classes for Δθ and for any authority operation that changes constraints. (See Gap 1.)

### Operational Controls

**Key rotation** as a first-class event with audit + enforced invalidation of outstanding tokens.

**Safe defaults for network exposure:**
- Bind to `127.0.0.1` by default
- Refuse `0.0.0.0` unless explicit `--expose-network`
- Log a screaming banner if non-localhost
- CORS locked down by default
- CSRF protections if cookies are ever used

**Observability:** Separate "health metrics" from "policy metrics." Don't let the governor define its own SLOs without operator revision.

### Authority Monotonicity Under Uncertainty (New Invariant)

> If U_t is high, authority can only *shrink*, never expand — regardless of identity tier.

This prevents the classic failure: "things are uncertain, so I asked for broader powers." Add to SafetyMonotonicityInvariant.

### Practical 2.x Move

**Make every admin-ish action require a typed, signed `AuthorityEvent` object**, even if today you generate it locally. That gives 3.x a clean seam to bolt auth onto without rewriting the control plane.

```python
@dataclass
class AuthorityEvent:
    """Typed authority action — 2.x stub for 3.x auth seam."""
    event_id: str
    action: str                # "waive", "revise", "unfreeze", "override"
    principal: str             # "local:operator" in 2.x, JWT sub in 3.x
    scope: dict[str, Any]      # What's being authorized
    timestamp: str
    signature: str             # "local" in 2.x, cryptographic in 3.x
```

Design the auth interface as a stubbed middleware now, so 3.x isn't a refactor.

---

## Summary: 3.x Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SELF-GOVERNANCE 3.x                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    telemetry    ┌──────────────────┐              │
│  │  Governor   │ ───────────────>│  Meta-Governor   │              │
│  │ (Executor)  │                 │   (Proposer)     │              │
│  │             │                 │                  │              │
│  │ Applies θ   │                 │ Proposes Δθ      │              │
│  │ CANNOT      │                 │ CANNOT apply     │              │
│  │ modify θ    │                 │                  │              │
│  └─────────────┘                 └────────┬─────────┘              │
│         ^                                 │                        │
│         │                                 v                        │
│         │                    ┌────────────────────────┐            │
│         │                    │    Acceptance Gate     │            │
│         │                    │  - Meta-invariants     │            │
│         │                    │  - Measurement gating  │            │
│         │                    │  - Capability check    │            │
│         │                    │  - Hysteresis/dwell    │            │
│         │                    │  - Cross-model quorum  │            │
│         │                    └───────────┬────────────┘            │
│         │                                │                         │
│         │              if approved       │                         │
│         └────────────────────────────────┘                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Runtime Harness                            │   │
│  │  - Canary tasks           - Drift detection                 │   │
│  │  - Metamorphic sampling   - Freeze/rollback triggers        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Dual Ledger (U_t, C_t)                     │   │
│  │  Objective: min C_t  subject to  U_t <= tau                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Meta-Audit Log                             │   │
│  │  Structural signals - Hash-chained - Anomaly detection      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Priority (When You Get to 3.x)

1. **Executor/Proposer separation** — The hard boundary
2. **Admissible measurements** — No narrative-driven updates
3. **Rollback controller** — First-class reversion
4. **Hysteresis config** — Prevent oscillation
5. **Safety monotonicity invariants** — The constitution (including authority monotonicity under uncertainty)
6. **No laundering detector** — Prevent map-shrinking
7. **Dual ledger** — Track cost alongside uncertainty
8. **Capability discipline** — Can't expand own tools
9. **AuthorityEvent + stubbed auth middleware** — 2.x seam for 3.x service boundary
10. **Runtime harness** — Continuous evaluation
11. **Adaptation test suite** — Combinatorial scenario coverage
12. **Capability tokens + /attest endpoint** — When governor becomes a shared service
13. **Per-tenant isolation** — When multi-user deployment happens

---

## The One-Liner (What Actually Matters)

> Any theta update requires: **admissible measurement coverage** + **independent validator quorum** + **no valid veto witness**.

---

## Design Principles (Keep the Constitution Small)

1. **Constraining beats clever.** The spec is good because it limits, not because it's sophisticated.

2. **Require witness artifacts.** No witness, no signature. "Here's the smallest scenario where delta-theta helps/fails" or "here's the invariant set it touches."

3. **Keep the constitution small.** Every new clause is another surface for drift, loopholes, or implementation mismatch. Put the rest in "statutes" (tunable policy), not the constitution (protected invariants).

4. **Don't over-engineer 3.x while building 2.x.** The gaps above are documented. They'll get solved when you hit them, not before.

---

## Checkpoint 3 / P4 Promotion (amendment, ratified 2026-06-15)

> **Framing — read first.** This section is **additive**. The spec above is v0.1
> planning text written *before* the kernel existed; it is not rewritten here and is
> not bumped to v0.2. This section **maps the already-built kernel** (kernel/userland
> split, four-office activation, rung-debt / `DebtLedger`, recomposition enforcement,
> decomposition completeness) onto v0.1's vision of self-governance. Where v0.1
> sketched `RollbackController` / `ThetaSnapshot` / `AcceptanceGate` as future Python,
> the built structure realizes the same intent through different, shipped furniture.
> Do not read "promotion kernel landed" as "self-governance spec fully rebuilt" — that
> is the promotion-by-title bug this framing exists to refuse.

### What promotion is

**Promotion** turns one surviving *trial value* of the single P3.1-activated tunable
(`decomposition_size / max_slices` on rung `self_governance`) into a new named
**`ControlBaseline`** — the known-good policy baseline future activations measure drift
against. It is the v0.1 `ThetaSnapshot`-becomes-baseline event, made classed.

> **Red line (verbatim from the campaign):** checkpoints / forks / promotions are
> resumability machinery *unless explicitly admitted as control-plane baselines*. A
> promoted session state is NOT automatically a known-good baseline. Promotion is a
> separate, classed act: *observe trial survives → mint baseline via ceremony.*

### Promotion is a four-office classed act

Promotion uses the same four offices P3.1 activation already uses — the offices are the
mapping from v0.1's monolithic `AcceptanceGate` onto the built kernel:

| Office | v0.1 analogue | P4 realization |
|---|---|---|
| **Admissibility** | meta-invariants + measurement gating | `PromotionEligible` predicate (`promotion_gate.py`), the gate whose only verb is *refuse* |
| **Act-standing** | operator authority / credential | operator basis bound to the reviewed bundle (`operator_basis.py`) |
| **Exactly-once spend** | single Δθ per epoch (`SingleChangeEnforcer`) | one supersession mint — the `PromotionReceipt`, serial under WIP-1 |
| **Durable custody** | `PersistentState` / signed snapshots | `ControlBaseline` + content-addressed lineage (any two baselines diffable from hashes alone) |

### The fence — attributable, not legitimate

Operator basis makes the mint **attributable** (it bears the named operator-root's name)
and **authorizes the act**. It does **not** make the trial good or the promotion correct,
and it **cannot cure an evidentiary gap.** Operator basis licenses the *authority* office
only; it can never substitute for live observation, replay/holdout, freshness, or
walkability. (Source: anti-laundering scope correction — *the kernel is an anti-laundering
engine, not a legitimacy engine*; `working/anti-laundering-not-legitimacy-ag-consumption-2026-06-15.md`.
The operator can SIGN, never LAUNDER.)

This is the v0.1 "No Epistemic Laundering" rule expressed at the promotion seam, plus the
synchronic/diachronic split: the producer gates are synchronic (does *this* receipt
discharge its kind here-and-now); laundering-over-time is a diachronic pattern watched by
the deadlock/sequence layer, never folded into a token-local pass.

### PromotionEligible predicate (dual witness, never folded — Checkpoint 1)

```
PromotionEligible :=
      live_evidence_count >= N            # live survival witness
  AND live_receipts_fresh
  AND live_receipts_walkable_from_activation
  AND replay_holdout_non_regression_passed # replay/holdout falsification witness
  AND no_open_NonDischargeClaim
  AND no_off_surface_tunable
  AND no_kernel_fuse_ratification_side_effect
  AND operator_basis_present
```

The two witnesses stay **physically separate** — `live receipts = did the trial survive
reality?` vs `replay/holdout = does promotion avoid known regression?`. A perfect replay
cannot rescue missing live evidence, and vice versa. Failure of either blocks promotion
and leaves the prior baseline authoritative.

### Custody authority — the canonical basis-bundle (ratified 2026-06-15)

The operator reviews a **basis bundle**: the pre-state evidence world. Its canonical hash
binds *what the operator reviewed* so the promotion gate can prove the consumed bundle ==
the reviewed bundle (pre-state binding, `operator_basis.py`).

```
basis_bundle_hash = sha256(canonical_json({
  schema_version,            # "promotion-basis-bundle-v1"
  candidate,                 # trial_id, tunable_name, trial_value,
                             #   prior_baseline_value AND prior_baseline_hash/receipt if present
  activation_hash,           # ActivationReceipt.content_hash
  observation_hashes,        # sorted list of LiveSurvivalObservationReceipt content hashes
  replay_holdout_hash,       # ReplayHoldoutReceipt.content_hash (already frozen — see freshness)
  required_count,            # N
  survival_horizon_ns,
  allowed_surface,           # the single-tunable allowlist
  open_non_discharge_claims  # FROZEN snapshot content of debt state at review time
}))  # -> raw SHA-256 hex digest (NO "sha256:" prefix)
```

- **Hash shape: raw SHA-256 hex, no prefix** (ratified 2026-06-15). This matches the
  shape of `ActivationReceipt.content_hash` and `ControlBaseline.baseline_id`, so the
  bundle hash is directly comparable to the chain hashes it is built from (no second
  canonicalization). The algorithm identity is supplied by the field semantics —
  `schema_version: "promotion-basis-bundle-v1"` and the field name `basis_bundle_hash` —
  not by an inline `sha256:` string prefix.
- **Excludes the operator basis receipt** — it binds *to* this bundle; including it is
  circular.
- **Excludes live clocks** — clock witnesses are freshness/evaluation basis, a *different
  object* (clock-witness doctrine); putting them in the content hash makes every
  evaluation a different reviewed object.
- **Prior baseline as lineage, not a bare value** — `prior = 8` is weaker than `prior
  baseline receipt X says 8`. Bind the receipt/hash when one exists.
- **Open-claims is frozen content, not a live query pointer** — the bundle binds the debt
  state *at review time*. Later claims may change future eligibility; they must not
  retroactively mutate what the operator reviewed.

> **Doctrine line:** *The basis bundle binds the reviewed promotion world-state, not the
> operator's later act and not the evaluation clock.*

### Time authority — two clocks (ratified 2026-06-15)

Freshness is two clocks, and only one is coupled to ceremony time. Replay is **upstream**
of operator review because the reviewed basis bundle already includes the replay receipt
(it is frozen before review). So the P4.0g scar's original framing ("review window must
outlive replay") is inverted; the real constraint moves to the survival horizon.

```
operator_review_freshness:           # protects the operator act
    reviewed_at must be fresh at t_promote
    -> short sized ceremony window (review window)

live_observation_freshness:          # protects the evidence
    observations must still be fresh at t_promote
    -> survival horizon must outlive (replay runtime + operator review + mint slack)
```

No paused-clock object now — a paused-clock receipt is a *deposition mechanism* (its whole
job is to assert "this interval didn't count"), introduced only if sized windows become
operationally stupid. **Keeper test:** a holdout/replay longer than the review window must
**not** auto-fail an otherwise-valid promotion when replay is already frozen into the
reviewed bundle and observations remain fresh at mint.

> **Doctrine line:** *Review freshness protects the operator act. Survival freshness
> protects the evidence. Don't use one clock to smuggle the other.*

### Supersession, expiry, rollback (mapping v0.1's `RollbackController`)

- **Mint** uses the validator supersession ceremony (proven across validator
  v0.1.0→v0.4.0): the new `ControlBaseline` carries a `PromotionReceipt` produced under
  the prior baseline, with content-addressed lineage (bisectable). The receipt binds
  `prior_baseline_id`, `trial_activation_id(s)`, `evidence_count` + in-bounds evidence
  refs, `new_baseline` content-hash, and the operator/standing basis.
- **Expiry** — the trial activation carries gate-time expiry. No promotion before expiry →
  **auto-revert to prior baseline.** The trial is time-boxed: promoted (→ baseline) or
  expired (→ rollback); never a silent third state.
- **Rollback** — reverting a *promoted* baseline is itself a supersession (a new ceremony
  back to the prior, with lineage), NOT a silent undo. Rollback reason types
  (`regressed | exhausted | refused`) never collapse.

### Still bootstrap / degraded (documented, accepted)

In-process forgeability of evidence/receipts (substrate limit — the producer gates fence
the *shape*, not provenance); operator-fiat standing for the promotion authorization;
local supersession ceremony (no external offices); single tunable only (ops/NQ profile
gated on surviving one full promotion cycle); the fuse not yet kernel-enforced
(`GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001`).

### Provenance

Predicate, witnesses, and refusal vocabulary: `specs/governor/promotion-evidence.md`.
Plan: `working/P4-promotion-plan-2026-06-13.md`. Checkpoint 1 (dual gate) RATIFIED
2026-06-13; Checkpoint 2 (convergence_tuning → COEXIST) RESOLVED 2026-06-13; Checkpoint 3
(this section) RATIFIED 2026-06-15.
