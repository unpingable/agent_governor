# Hysteresis and Anti-Churn Specification

```yaml
status: planning
layer: 2.1
depends_on: [PHASE_CONTROL_SPEC, RISK_FUNCTION_SPEC, METRICS_SPEC]
```

## Overview

Prevent controller chatter — limit replans, regressions, and mode oscillation.

## Mode Transition Hysteresis

Different thresholds for entering vs exiting strict mode:

```python
def check_mode_transition(current_mode: Mode, admissibility: float, history: List[float]) -> Mode:
    if current_mode == Mode.STRICT:
        # Higher threshold to exit strict mode
        if admissibility > A_HIGH:
            return Mode.NORMAL
    else:
        # Lower threshold to enter strict mode
        if admissibility < A_LOW:
            return Mode.STRICT
    return current_mode
```

## Replan Limiting

```python
@dataclass
class ReplanTracker:
    max_replans: int = 3
    replan_count: int = 0
    last_plan_hash: str = ""

    def allow_replan(self, new_plan_hash: str) -> bool:
        if new_plan_hash == self.last_plan_hash:
            return False  # No-op replan
        if self.replan_count >= self.max_replans:
            return False  # Budget exhausted
        return True

    def record_replan(self, new_plan_hash: str):
        self.replan_count += 1
        self.last_plan_hash = new_plan_hash
```

## Regression Detection

Flag when verified claims become unverified:

```python
def detect_regression(old_claims: List[Claim], new_claims: List[Claim]) -> List[Alert]:
    alerts = []
    old_verified = {c.id for c in old_claims if c.status == ClaimStatus.VERIFIED}
    new_verified = {c.id for c in new_claims if c.status == ClaimStatus.VERIFIED}

    regressions = old_verified - new_verified
    for claim_id in regressions:
        alerts.append(Alert(type="verification_regression", claim_id=claim_id))

    return alerts
```

## Events

```json
{"event": "mode_transition_suppressed", "from": "STRICT", "would_go_to": "NORMAL", "reason": "hysteresis_band", "admissibility": 0.68, "threshold_needed": 0.75, "timestamp": "..."}
{"event": "replan_denied", "replan_count": 3, "max_replans": 3, "reason": "budget_exhausted", "timestamp": "..."}
{"event": "verification_regression", "claim_id": "c_015", "was": "verified", "now": "unknown", "timestamp": "..."}
```

## Relationship to Existing Modules

- **Existing regime.py + boil.py**: Already implement regime hysteresis (ELASTIC/WARM/DUCTILE/UNSTABLE with dwell times). This spec generalizes the pattern to all mode transitions.
- **Existing drift.py**: Premise quarantine already uses hysteresis. This spec adds replan limiting and regression detection.
- **Existing research.py**: Hypothesis lifecycle has terminal states. This spec adds anti-churn to non-terminal transitions.

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Phase regression blocked by hysteresis
- **Risk Function** (RISK_FUNCTION_SPEC): Risk-driven mode changes use asymmetric thresholds
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Regressions degrade CBI M1 (switching health)
- **Mode Detection** (MODE_DETECTION_SPEC): Mode drift transitions use hysteresis
