# Admissibility Gate Specification (Push-Back System)

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC]
```

## Overview

Before meaningful work begins, compute whether the task is well-specified enough to proceed. Push-back is not "being annoying" — it's information-theoretically cheap compared to expected downstream loss from underspecification.

## Admissibility Score

```
A = w₁·S_setpoint + w₂·S_constraints + w₃·S_observability - P_unknowns
```

Where:
- S_setpoint ∈ [0,1]: How well-defined is the success criterion?
- S_constraints ∈ [0,1]: Are constraints explicit?
- S_observability ∈ [0,1]: Can we measure/verify success?
- P_unknowns: Penalty for unresolved unknowns (severity-weighted)

```python
@dataclass
class AdmissibilityAssessment:
    setpoint_score: float      # 0-1
    constraint_score: float    # 0-1
    observability_score: float # 0-1
    unknowns: List[Unknown]    # first-class objects

    @property
    def score(self) -> float:
        base = (W1 * self.setpoint_score +
                W2 * self.constraint_score +
                W3 * self.observability_score)
        penalty = sum(u.severity * u.weight for u in self.unknowns)
        return base - penalty
```

## Unknown Tracking

Unknowns are first-class objects with severity:

```python
@dataclass
class Unknown:
    id: str
    description: str
    severity: Severity  # S1, S2, S3
    category: str       # "objective", "constraint", "context", "resource"
    resolvable_by: str  # "user_clarification", "tool_query", "assumption"
    weight: float       # impact on admissibility
```

## Push-Back Modes

Based on admissibility score A:

| Mode | Condition | Behavior |
|------|-----------|----------|
| PROCEED | A ≥ A_high | Normal operation |
| SOFT | A_low ≤ A < A_high | Proceed but cap confidence, block S3 claims |
| HARD | A < A_low | Deny COMMIT; ask minimal high-IG questions |
| SAFE | Any S3 unknown exists | Block S3 actuation entirely |

```python
def select_pushback_mode(assessment: AdmissibilityAssessment) -> PushbackMode:
    # S3 unknowns = immediate SAFE mode
    if any(u.severity == Severity.S3 for u in assessment.unknowns):
        return PushbackMode.SAFE

    if assessment.score >= A_HIGH:
        return PushbackMode.PROCEED
    elif assessment.score >= A_LOW:
        return PushbackMode.SOFT
    else:
        return PushbackMode.HARD
```

## Value of Information (VoI) for Questions

When in HARD mode, select questions by information gain:

```
VoI(θ) = E[min_a E[L|θ,a]] - min_a E[L|a]
```

Ask question if: VoI(θ) > Cost(ask)

```python
def select_clarifying_questions(unknowns: List[Unknown], max_questions: int = 3) -> List[str]:
    """Select highest VoI questions that resolve unknowns."""
    scored = [(u, estimate_voi(u)) for u in unknowns]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [u.generate_question() for u, _ in scored[:max_questions]]
```

## Invariant F (No Hidden Assumptions)

**CRITICAL:** No hidden assumptions for S2/S3 actions. All assumptions must be:
- Explicitly logged
- Severity-tagged
- Waivable only with explicit user acknowledgment

## Events

```json
{"event": "admissibility_assessed", "score": 0.62, "mode": "SOFT", "unknowns": [{"id": "u_003", "severity": "S2", "category": "constraint"}], "timestamp": "..."}
{"event": "assumption_made", "unknown_id": "u_003", "assumption": "User wants Python 3.11+", "severity": "S1", "waiver": null, "timestamp": "..."}
{"event": "waiver_granted", "unknown_id": "u_007", "by": "user", "acknowledged_risk": "May not work on Windows", "timestamp": "..."}
{"event": "pushback_question", "unknown_id": "u_012", "question": "What is the target platform?", "voi": 0.34, "timestamp": "..."}
```

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Admissibility gates SPECIFY→EXPLORE transition
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Open unknowns feed uncertainty U_t
- **Deployment Profiles** (DEPLOYMENT_PROFILES_SPEC): Authority class sets A_high/A_low thresholds
- **Control Theory** (CONTROL_THEORY_SPEC): Unknowns increase D_t (feedback delay)
