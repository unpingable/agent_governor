# Scenario Taxonomy

Naming convention for simulation fixtures.

## Name shape

`<family>__<mechanism>__<profile>__<exposure>__v<N>.json`

## Axes

### Family (what pathology)

| Value | Meaning |
|-------|---------|
| `healthy` | Normal operation, no pathology. Control fixture. |
| `suppression` | Governance running but not producing signal. |
| `capture` | Agent influencing its own governance. |
| `shear` | System under stress / retry storms. |
| `exposure` | Epistemic exposure anomaly (low visibility). |

### Mechanism (how it happens)

| Value | Meaning |
|-------|---------|
| `external_checks` | Normal external tool verification. |
| `shadow_ack` | Fake success path replaces real verification. |
| `tool_skip` | Verification step omitted silently. |
| `echo_receipt` | Self-evidence mirrored as independent. |
| `deny_blackhole` | Denies generated but not surfaced. |
| `retry_storm` | Shear: repeated failing operations. |
| `receipt_delay` | Temporal widening of receipt gaps. |
| `low_workload` | Naturally reduced activity (not pathological). |

### Temporal profile

| Value | Meaning |
|-------|---------|
| `step` | Abrupt phase change at known tick. |
| `drift` | Slow creep over many ticks. |
| `burst` | Short violent window, then recovery. |
| `steady` | Constant condition throughout. |

### Exposure condition

| Value | Meaning |
|-------|---------|
| `high_exposure` | Plenty of external/tool checks. |
| `mixed_exposure` | Some external, some self-only. |
| `low_exposure` | Mostly self-referential evidence. |

### Version

`v0`, `v1`, etc. Fixtures will change. Pin the version.

## Intent field (required)

Every fixture must declare its intent:

| Value | Meaning |
|-------|---------|
| `detector_smoke` | Should trigger the named detector. |
| `anti_detector` | Should NOT trigger the named detector. |
| `calibration_seed` | Baseline data for threshold tuning. |
| `adversarial` | Adversarial evasion attempt. |
| `control` | Pure healthy baseline, no detector should fire. |

## Expected non-findings (required)

Every fixture must declare what detectors should NOT fire,
not just what should fire. This prevents "everything is everything."

## Fault vocabulary

| Fault | Meaning |
|-------|---------|
| `shadow_ack` | Fake success receipts replace real verification. |
| `tool_skip` | Verification call omitted. |
| `echo_receipt` | Self-evidence presented as independent. |
| `deny_blackhole` | Denies swallowed before surfacing. |
| `retry_storm` | Repeated failing operations (shear). |
| `receipt_delay` | Increasing gaps between receipts. |

## Directory layout

```
sim/fixtures/
  heartbeat_active.json          # legacy (pre-taxonomy)
  heartbeat_stale.json           # legacy
  gate_disabled.json             # legacy
  phase_a/
    healthy/
      healthy__external_checks__steady__high_exposure__v0.json
      healthy__low_workload__step__low_exposure__v0.json
    suppression/
      suppression__shadow_ack__step__high_exposure__v0.json
  phase_b/
    capture/
      ...
```

## Metrics contract (per-phase)

Every scenario run should emit these observables per phase:

- `proposal_count` — total proposals in phase
- `receipt_count` — total receipts emitted
- `external_receipt_count` — receipts with independence_class != self
- `self_receipt_count` — receipts with independence_class == self
- `independent_receipt_ratio` — (tool+external+peer+operator) / total
- `deny_count_visible` — surfaced denies
- `contradiction_count` — detected contradictions
- `contradiction_rate` — contradictions / proposals

## Threshold pack

Detector thresholds are named bundles, not inline constants.

`suppression_v0`:
- `throughput_flat_max_delta: 0.15`
- `exposure_collapse_ratio: 0.40`
- `contradiction_collapse_ratio: 0.20`
- `visible_deny_rate_max: 0.05`
- `min_baseline_exposure: 0.50`
