# Gap: σ-rate — Proxy/True Divergence Rate

**Branch:** v2.x
**Status:** gap (observe-first)
**Depends on:** correlator_telemetry.py, SELF_GOVERNANCE_SPEC.md (contradiction_rate config)
**Build phase:** v2.1 (instrumentation spine — build third, after SILENT_SUPPRESSION + EXPOSURE_PROXY)

## The Problem

The governor tracks many signals but has no single metric that answers: "how far is the governor's model of the world from reality?"

`contradiction_rate` exists in SELF_GOVERNANCE_SPEC as a significance config entry (min 100 samples, effect size 0.2) but has no measurement mechanism. The correlator tracks K-vector fidelity but collapses it into regime classification. Neither provides a continuous, interpretable divergence rate.

## What σ-rate Is

σ-rate = the rate at which governor-endorsed claims are later contradicted by trusted evidence.

```
σ = contradictions_in_window / endorsed_claims_in_window
```

Where:
- **Endorsed** = claim reached SUPPORTED status (not PROPOSED or CONTESTED)
- **Contradicted** = claim moved to INVALIDATED via evidence (not user retraction)
- **Window** = sliding, configurable (default: last 50 endorsed claims)

This is the governor's "lying rate" — higher σ means the governor's gating is leaking bad claims through.

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| `contradiction_rate` config | SELF_GOVERNANCE_SPEC §2 | Significance thresholds only — no measurement |
| K-vector Fidelity | correlator_telemetry.py | Collapsed into regime; not independently surfaced |
| ClaimStatus FSM | epistemic.py | SUPPORTED→INVALIDATED transitions exist but aren't counted |
| Evidence Gate | evidence_gate.py | Contradictions detected at check time but not aggregated |

## What's Missing

### 1. Measurement (observe-first)

Track SUPPORTED→INVALIDATED transitions in a sliding window. No gating action — just record and surface.

```python
@dataclass
class SigmaObservation:
    window_size: int                    # claim count, not time
    endorsed_count: int
    contradiction_count: int
    sigma_rate: float                   # contradiction_count / endorsed_count
    timestamp: datetime
    contributing_claim_ids: list[str]   # for audit trail
```

### 2. Baseline Estimation

σ-rate means nothing without a baseline. First deployment phase is pure observation:
- Collect σ over 500+ endorsed claims
- Compute mean, p95, p99
- These become the regime-specific baselines (different baselines for code vs fiction vs research)

### 3. Dashboard Surfacing

σ-rate should appear on the dashboard and in `governor regime status` output. No alert — just visibility.

### 4. Integration with Existing Signals

Once baseline exists, σ-rate feeds into:
- Correlator K-vector Fidelity dimension (currently hand-coded)
- Regime detector as an additional signal (high σ → WARM or DUCTILE)
- Ultrastability as an S₁ input

## What This Does NOT Do

- Does not gate claims (that's evidence_gate's job)
- Does not trigger regime changes (that requires the calibration layer, see CALIBRATION_LAYER_GAP.md)
- Does not distinguish contradiction types (legitimate revision vs hallucination) — that's deferred to v3

## Build Estimate

~80 lines of measurement code + ~40 lines CLI/dashboard wiring + ~60 tests. No new dependencies.

## Acceptance Criteria

1. `SigmaObservation` emitted on every SUPPORTED→INVALIDATED transition
2. Sliding window configurable (default 50)
3. Visible in `governor regime status --json` under `sigma_rate` key
4. JSONL persistence for baseline computation
5. No gating or alerting in v2 — observe only
