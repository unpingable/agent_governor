# Domain/Mode Detection Specification

```yaml
status: implemented
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, PHASE_CONTROL_SPEC]
```

## Overview

Detect when solving the wrong kind of problem. Treat domain/profile as discrete mode in a hybrid controller — mode mismatch is a real failure class.

## Domain Modes

```python
class DomainMode(Enum):
    CODE = "code"           # Software development
    RESEARCH = "research"   # Nonfiction, analysis, citations matter
    FICTION = "fiction"      # Creative writing, continuity matters
    TASK = "task"           # General task completion
```

## Mode Posterior

Maintain belief over modes:

```
p_{t+1}(m) ∝ p_t(m) · exp(β · φ(o_t, m))
```

Where φ scores features of observation o_t under mode m:

```python
def compute_mode_features(observation: Observation, mode: DomainMode) -> float:
    features = {
        DomainMode.CODE: [
            observation.has_code_blocks,
            observation.mentions_programming_language,
            observation.requests_implementation,
            observation.has_error_traces,
        ],
        DomainMode.RESEARCH: [
            observation.requests_citations,
            observation.asks_factual_questions,
            observation.mentions_sources,
            observation.analytical_language,
        ],
        DomainMode.FICTION: [
            observation.creative_prompt,
            observation.character_names,
            observation.narrative_language,
            observation.requests_story,
        ],
    }
    return sum(features.get(mode, []))

def update_mode_posterior(prior: Dict[DomainMode, float], observation: Observation, beta: float = 1.0) -> Dict[DomainMode, float]:
    scores = {m: prior[m] * math.exp(beta * compute_mode_features(observation, m)) for m in DomainMode}
    total = sum(scores.values())
    return {m: s / total for m, s in scores.items()}
```

## Drift Detection

```python
def compute_drift(current: Dict[DomainMode, float], initial: Dict[DomainMode, float]) -> float:
    """1 - dot product of distributions."""
    return 1 - sum(current[m] * initial[m] for m in DomainMode)

def check_mode_drift(state: RunState) -> Optional[Alert]:
    drift = compute_drift(state.mode_posterior, state.initial_mode_posterior)
    if drift > DRIFT_THRESHOLD and state.phase in [Phase.VERIFY, Phase.COMMIT]:
        return Alert(
            type="mode_drift",
            drift_score=drift,
            initial_mode=max(state.initial_mode_posterior, key=state.initial_mode_posterior.get),
            current_mode=max(state.mode_posterior, key=state.mode_posterior.get),
            action="warn" if state.phase == Phase.VERIFY else "block"
        )
    return None
```

## Mode-Specific Profiles

Different modes have different verification priorities:

```python
MODE_PROFILES = {
    DomainMode.CODE: {
        "verification_focus": ["syntax", "tests", "types", "security"],
        "severity_gates": {Severity.S3: "block", Severity.S2: "warn"},
        "late_novelty_penalty": 2.0,  # High penalty for late scope changes
        "critic_role": "veto_on_errors",
    },
    DomainMode.RESEARCH: {
        "verification_focus": ["citations", "factual_claims", "contradictions"],
        "severity_gates": {Severity.S3: "block", Severity.S2: "evidence_required"},
        "late_novelty_penalty": 1.0,
        "critic_role": "contradiction_first",
    },
    DomainMode.FICTION: {
        "verification_focus": ["continuity", "voice", "constraints"],
        "severity_gates": {Severity.S3: "warn"},  # More permissive
        "late_novelty_penalty": 0.5,  # Allow late creative changes
        "critic_role": "continuity_check",
    },
}
```

## Events

```json
{"event": "mode_posterior_update", "posterior": {"code": 0.72, "research": 0.15, "fiction": 0.08, "task": 0.05}, "drift": 0.12, "timestamp": "..."}
{"event": "mode_drift_alert", "drift_score": 0.45, "initial_mode": "code", "current_mode": "research", "action": "warn", "timestamp": "..."}
{"event": "mode_profile_activated", "mode": "code", "verification_focus": ["syntax", "tests", "types", "security"], "timestamp": "..."}
```

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Mode drift blocks COMMIT in late phases
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Mode drift feeds CBI M5 (drift rate)
- **Existing context_drift.py**: Extends fiction-specific drift to cross-domain detection
- **Existing jurisdictions.py**: Mode maps to jurisdiction selection
- **Hysteresis** (HYSTERESIS_SPEC): Mode transitions use hysteresis to prevent chatter
