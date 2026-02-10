# Risk Potential Function Specification

```yaml
status: implemented
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, MEASUREMENT_INTEGRITY_SPEC, METRICS_SPEC, DEPLOYMENT_PROFILES_SPEC]
```

## Overview

A scalar risk V that drives mode tightening and tool gating. This is the Lyapunov-ish monotone control signal.

## Risk Function

```
V(x̂_t) = α₁·untrusted_blob_use + α₂·scope_size + α₃·irrev_intent + α₄·evidence_gap + α₅·anomaly_score
```

```python
@dataclass
class RiskAssessment:
    untrusted_blob_use: float    # Count/severity of untrusted tool outputs used
    scope_size: float            # Breadth of requested capabilities
    irreversibility_intent: float # Likelihood of irreversible actions
    evidence_gap: float          # Claims without evidence
    anomaly_score: float         # Behavioral anomalies detected

    def compute_risk(self, weights: RiskWeights) -> float:
        return (
            weights.untrusted * self.untrusted_blob_use +
            weights.scope * self.scope_size +
            weights.irreversibility * self.irreversibility_intent +
            weights.evidence * self.evidence_gap +
            weights.anomaly * self.anomaly_score
        )
```

## Risk-Driven Policy

```python
def apply_risk_policy(risk: float, state: RunState) -> RunState:
    if risk > RISK_THRESHOLD_CRITICAL:
        # Switch to tightest mode
        state.deployment_profile = PUBLIC_PROFILE
        state.frozen_tools.update(SIDE_EFFECT_TOOLS)
        state.alerts.append(Alert(type="risk_critical", risk=risk))
    elif risk > RISK_THRESHOLD_HIGH:
        # Restrict to safe tools only
        state.frozen_tools.update(IRREVERSIBLE_TOOLS)
        state.requires_two_phase = {Severity.S2, Severity.S3}
    elif risk > RISK_THRESHOLD_ELEVATED:
        # Increase evidence requirements
        state.evidence_threshold *= 1.5

    return state
```

## Relationship to R_t

Risk function V is complementary to R_t from CONTROL_THEORY_SPEC:
- **R_t = (P·D)/E** is the per-step risk index based on tool power, delay, and evidence
- **V** is the accumulated run-level risk based on observed behavior patterns
- V can increase R_t by raising D_t (more untrusted state = more verification delay needed)
- V can decrease allowable P_t by tightening the deployment profile

## Events

```json
{"event": "risk_update", "risk": 0.67, "components": {"untrusted": 0.2, "scope": 0.15, "irrev": 0.1, "evidence_gap": 0.22, "anomaly": 0.0}, "timestamp": "..."}
{"event": "risk_threshold_crossed", "threshold": "elevated", "risk": 0.45, "action": "increase_evidence_requirements", "timestamp": "..."}
{"event": "risk_policy_applied", "risk": 0.82, "action": "freeze_irreversible_tools", "frozen_tools": ["execute", "write_file", "delete"], "timestamp": "..."}
```

## Integration

- **Measurement Integrity** (MEASUREMENT_INTEGRITY_SPEC): Untrusted blob count feeds α₁
- **Metrics** (METRICS_SPEC): Evidence gap (1 - coverage) feeds α₄
- **Deployment Profiles** (DEPLOYMENT_PROFILES_SPEC): Risk can demote active profile
- **Phase Control** (PHASE_CONTROL_SPEC): Risk affects per-phase tool restrictions
- **Hysteresis** (HYSTERESIS_SPEC): Risk-driven mode changes use hysteresis
- **Control Theory** (CONTROL_THEORY_SPEC): V modulates R_t via D_t and P_t bounds
