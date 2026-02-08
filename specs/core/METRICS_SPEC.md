# Coverage and Efficiency Metrics Specification

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC]
```

## Overview

Severity-weighted coverage and verification efficiency metrics. These drive phase transitions, risk assessment, and CBI computation.

## Severity-Weighted Coverage

```
Coverage = Σ(w_i · v_i) / Σ(w_i)
```

Where:
- w_i = severity weight for claim i
- v_i = 1 if VERIFIED, 0 otherwise

```python
SEVERITY_WEIGHTS = {
    Severity.S1: 1.0,
    Severity.S2: 3.0,
    Severity.S3: 10.0,
}

def compute_coverage(claims: List[Claim]) -> float:
    total_weight = sum(SEVERITY_WEIGHTS[c.severity] for c in claims)
    verified_weight = sum(SEVERITY_WEIGHTS[c.severity] for c in claims if c.status == ClaimStatus.VERIFIED)
    return verified_weight / total_weight if total_weight > 0 else 1.0
```

## Verification Efficiency

```
η = ΔCoverage / verification_actions
```

"How much certainty did we buy per check?"

```python
def compute_efficiency(coverage_before: float, coverage_after: float, actions: int) -> float:
    if actions == 0:
        return 0.0
    return (coverage_after - coverage_before) / actions
```

## Claim Status Tracking

```python
class ClaimStatus(Enum):
    UNKNOWN = "unknown"
    VERIFIED = "verified"
    WAIVED = "waived"
    REFUTED = "refuted"
    PENDING = "pending"

@dataclass
class ClaimCoverage:
    total_claims: int
    by_status: Dict[ClaimStatus, int]
    by_severity: Dict[Severity, Dict[ClaimStatus, int]]
    weighted_coverage: float

    def summary(self) -> str:
        return f"Coverage: {self.weighted_coverage:.1%} | S3: {self.s3_coverage():.1%} | S2: {self.s2_coverage():.1%}"
```

## Events

```json
{"event": "coverage_update", "coverage": 0.73, "delta": 0.08, "actions_taken": 2, "efficiency": 0.04, "timestamp": "..."}
{"event": "claim_status_change", "claim_id": "c_015", "from": "unknown", "to": "verified", "evidence_id": "e_042", "timestamp": "..."}
```

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Coverage threshold gates VERIFY→COMMIT
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Coverage feeds uncertainty U_t
- **Risk Function** (RISK_FUNCTION_SPEC): Evidence gap (1 - coverage) feeds risk V
- **Control Theory** (CONTROL_THEORY_SPEC): Coverage approximates E_t
- **Existing epistemic.py**: Extends grounded claim confidence with severity weighting
