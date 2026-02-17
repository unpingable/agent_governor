# Gap: Exposure Proxy — Non-Gameable Exposure Measurement

**Branch:** v2.x
**Status:** gap (foundational for capture detection)
**Depends on:** correlator_telemetry.py, telemetry.py, evidence_gate.py
**Build phase:** v2.1 (instrumentation spine — build second, after SILENT_SUPPRESSION)
**Blocks:** CAPTURE_SELF_DIAGNOSTIC_GAP (hard)

## The Problem

Capture detection requires knowing "how much has the model influenced the governor?" But exposure is currently measured by counting model-turns, which the model can game by being verbose (more tokens = same exposure but different count) or terse (fewer turns = lower measured exposure, same actual influence).

The correlator's `mode_per_exposure` indicator uses turn count as the exposure denominator. If the denominator is gameable, the indicator is gameable.

## What Already Exists

| Component | Location | Exposure Measure |
|-----------|----------|-----------------|
| Correlator exposure | correlator_telemetry.py | Turn count (gameable) |
| Telemetry events | telemetry.py | Event count + timestamps |
| Evidence Gate checks | evidence_gate.py | Claim count per check |
| Token counting | chat_bridge.py | Token counts from API responses |

## What Needs Building

### 1. Multi-Dimensional Exposure

Replace turn count with a vector that's harder to game:

```python
@dataclass
class ExposureVector:
    turn_count: int                # number of model turns
    token_count: int               # total tokens generated
    claim_count: int               # claims extracted from model output
    decision_influence: int        # decisions where model output was a factor
    elapsed_time_seconds: float    # wall clock time under model influence
    unique_files_touched: int      # file paths mentioned in model output
```

No single dimension is authoritative. The capture diagnostic uses the **most conservative** (highest exposure) dimension for its denominator.

### 2. External Anchoring

At least one exposure dimension should be hard for the model to influence:
- **Wall clock time**: The model can't slow down the clock
- **Unique files touched**: Bounded by the project, not the model's verbosity
- **Human-initiated turn ratio**: Turns started by user vs model-initiated follow-ups

### 3. Integration

The exposure vector replaces the scalar turn count in:
- Correlator's `mode_per_exposure` indicator
- Capture self-diagnostic's exposure-adjusted expectation (CAPTURE_SELF_DIAGNOSTIC_GAP.md)
- σ-rate's window sizing (SIGMA_RATE_GAP.md)

## Design Constraint

Exposure measurement must be **outside** the model's control path. It's computed from metadata (timestamps, token counts, file paths) not from model-generated content. The model can influence what files are mentioned, but it can't inflate the count without the evidence gate detecting the claims.

## Build Estimate

~60 lines (dataclass + collection) + ~30 lines integration + ~40 tests.

## Acceptance Criteria

1. `ExposureVector` computed per correlator observation window
2. Most-conservative dimension used as capture detection denominator
3. Wall clock time included as non-gameable anchor
4. Visible in `governor correlator status --json` under `exposure` key
5. Backward-compatible: turn_count still available as one dimension
