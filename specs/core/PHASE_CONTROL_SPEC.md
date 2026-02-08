# Phase Control System Specification

```yaml
status: implemented
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC, ADMISSIBILITY_SPEC]
```

## Overview

Agent runs are treated as controlled processes with explicit phases and budgets. The "bell lap" insight: spend verification effort where it matters (late phase), not uniformly.

## Phase Sequence

```
SPECIFY → EXPLORE → DRAFT → VERIFY → COMMIT
```

| Phase | Purpose | Allowed Actions | Budget Access |
|-------|---------|-----------------|---------------|
| SPECIFY | Clarify objectives, surface unknowns | Query user, analyze constraints | None consumed |
| EXPLORE | Generate candidates, research | Tools (read), retrieval, ideation | B_explore |
| DRAFT | Produce artifacts | Write, synthesize | B_draft |
| VERIFY | Validate claims, test artifacts | Verification tools, checks | B_verify (reserved) |
| COMMIT | Finalize output | Commit to ledger, present to user | Minimal |

## Reserve Budgets

Total budget B is partitioned:
```
B = B_explore + B_draft + B_verify
```

**Critical constraint:** B_verify is LOCKED until phase = VERIFY.

```python
class PhaseBudget:
    explore: int      # tool calls allowed in EXPLORE
    draft: int        # tool calls allowed in DRAFT
    verify: int       # RESERVED - unlocks at VERIFY phase

    def available(self, phase: Phase) -> int:
        if phase == Phase.VERIFY:
            return self.verify
        elif phase == Phase.DRAFT:
            return self.draft
        elif phase == Phase.EXPLORE:
            return self.explore
        return 0
```

This prevents the agent from "blowing" verification capacity on early exploration.

## Commit Window and Novelty Debt

After entering VERIFY phase, scope changes incur "novelty debt":

```
N_t = N_{t-1} + λ · d(S_t, S_{t-1}) · 𝟙[t ≥ t_verify]
```

Where:
- S_t = current claim/plan set
- d(·) = distance metric (claim diff count, AST diff, dependency-graph affected nodes)
- λ = novelty penalty coefficient

**Confidence cap under novelty:**
```
q_t ≤ q_max - α·N_t
```

**Re-verification trigger:** If d(S_t, S_{t-1}) > threshold after commit window opens, require re-verification of affected claims.

## Phase Transitions

```python
class PhaseTransition:
    @staticmethod
    def can_advance(current: Phase, state: RunState) -> bool:
        match current:
            case Phase.SPECIFY:
                return state.admissibility >= A_min
            case Phase.EXPLORE:
                return state.candidates_generated > 0
            case Phase.DRAFT:
                return state.artifact_exists
            case Phase.VERIFY:
                return state.coverage >= coverage_threshold
            case Phase.COMMIT:
                return True  # terminal
```

## Events

```json
{"event": "phase_transition", "from": "EXPLORE", "to": "DRAFT", "budget_remaining": {"explore": 3, "draft": 10, "verify": 5}, "timestamp": "..."}
{"event": "novelty_debt", "delta": 2.3, "total": 4.7, "confidence_cap": 0.76, "timestamp": "..."}
{"event": "budget_exhausted", "phase": "EXPLORE", "action": "force_transition_to_DRAFT", "timestamp": "..."}
```

## Invariant G (Phase Budget Lock)

B_verify is inaccessible until phase ≥ VERIFY. This is a hard constraint — no override, no waiver.

## Integration

- **Admissibility Gate** (ADMISSIBILITY_SPEC): SPECIFY→EXPLORE transition requires A ≥ A_min
- **Metrics** (METRICS_SPEC): Coverage computation gates VERIFY→COMMIT
- **Risk Function** (RISK_FUNCTION_SPEC): Risk V drives phase-specific tool restrictions
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Novelty debt feeds CBI uncertainty computation
- **Control Theory** (CONTROL_THEORY_SPEC): Phase budgets map to R_t capability envelope
