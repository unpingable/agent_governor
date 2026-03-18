# ENTRAINMENT_CONTROL_MODEL

status: draft

## Status
Draft

## Purpose
Define a multiscale control model for influence, capture, and policy contamination across distinct temporal and authority layers.

This model exists to prevent transient inputs from silently acquiring durable policy weight, and to preserve observer integrity under repeated shaping pressure.

## Core Claim
Not all influence operates at the same layer.

- Feed entrains phase.
- Propaganda entrains reference.
- Inculcation entrains the controller.

The governance problem is not merely whether an input changes behavior.
It is whether an input is permitted to change the machinery that interprets future inputs.

## Scope
This spec applies to any governed adaptive system — one that accepts inputs at multiple timescales, accumulates state, and forms durable policy from transient experience.

Structural requirements:
- transient runtime inputs
- session/context accumulation
- durable memory or preference state
- policy or constitutional invariants
- an observer/audit function

Concrete substrates are mapped in the Human/Institutional and LLM/Agent sections below.

## Non-Goals
This spec does not:
- define truth
- prohibit persuasion
- require a specific political or normative stance
- collapse all repeated influence into "brainwashing"

It defines control surfaces, authority tiers, and conditions under which influence becomes illegitimate.

## Terms

### Phase
Short-horizon synchronization of attention, cadence, or immediate behavior.

### Reference
The target, frame, or interpretive baseline used to evaluate events or choose actions.

### Controller
The policy-forming layer that determines how inputs are interpreted and how actions are selected.

### Observer
The subsystem responsible for detecting error, contradiction, drift, or capture.

Operationally, the observer tracks three capacities:
- **contradiction sensitivity** — can the system still notice when new inputs conflict with prior state?
- **source discrimination** — can the system still distinguish authorized from unauthorized update paths?
- **update-path auditability** — can the system still reconstruct how its current state was reached?

Degradation of any capacity is itself a governance event (see T4, M5).

### Entrainment
Persistent synchronization of some system variable to an external forcing signal.

### Cross-Layer Contamination
A condition where an input authorized only for a lower layer acquires effective write power over a higher layer.

### Observer Degradation
A reduction in the system's ability to detect its own drift, capture, contradiction, or illegitimate update path.

## Layer Model

### L0: Runtime / Phase Layer
Purpose: transient steering of immediate behavior.

Examples:
- prompt text
- feed exposure
- notifications
- local cues
- one-shot instructions

Properties:
- high bandwidth
- low persistence
- no durable write authority by default

### L1: Context / Reference Layer
Purpose: shape interpretation within a bounded session or episode.

Examples:
- conversation history
- retrieved context
- repeated framing
- current narrative scaffold
- task memory

Properties:
- medium persistence
- medium leverage
- bounded write authority only

### L2: Durable Policy Layer
Purpose: govern preference, standing heuristics, and default response tendencies across sessions.

Examples:
- saved memory
- preference profiles
- learned routing priors
- fine-tuning artifacts
- durable moderation heuristics

Properties:
- low bandwidth
- high persistence
- strong provenance and authorization required

### L3: Constitutional / Invariant Layer
Purpose: define non-negotiable boundaries, safety properties, and authority rules.

Examples:
- hard invariants
- protected constraints
- constitutional policy
- cryptographically attested governance rules

Properties:
- minimal write frequency
- maximal protection
- explicit, auditable update path only

## State Decomposition
The system may be modeled as three coupled state classes:

- `a(t)` = attention / salience / phase state
- `m(t)` = meaning / interpretation / reference state
- `p(t)` = policy / prior / controller state

Optional fourth state:
- `o(t)` = observer integrity / self-diagnostic capacity

The key asymmetry:
- `a(t)` changes quickly
- `m(t)` changes moderately
- `p(t)` changes slowly
- `o(t)` may degrade slowly but has system-wide consequences

## Governance Principle
Durability is not an emergent convenience.
Durability is a governed transition.

Any movement from L0/L1 into L2/L3 must be explicit, authorized, receipted, and reversible where possible.

## Invariants

### INV-001: Lower layers must not silently mutate higher layers
Runtime inputs may steer runtime behavior. They must not implicitly rewrite durable policy or constitutional state.

### INV-002: Repetition is not authorization
Mere recurrence, popularity, or sustained exposure does not grant policy weight.

### INV-003: Context is not constitution
Session-local framing must not be treated as a legitimate source of invariant change.

### INV-004: Observer integrity must remain auditable
A system must preserve the capacity to detect drift, contradiction, and suspicious update paths.

### INV-005: Durable updates require provenance
Any state change above L1 must record source, path, authority tier, and justification.

### INV-006: Reversibility decreases with depth
The deeper the layer touched, the stronger the write requirements and rollback requirements.

## Threat Taxonomy

### T1: Phase Capture
External forcing synchronizes short-horizon attention or behavior without durable policy change.

### T2: Reference Capture
External forcing shifts the frame through which events are interpreted.

### T3: Controller Capture
External forcing changes default policy formation or durable preference structure.

### T4: Observer Capture
The system loses its ability to recognize its own drift or capture.

### T5: Cross-Layer Contamination
A transient or contextual signal obtains durable governing force without legitimate promotion.

### T6: Hysteretic Lock-In
A prior installation persists after the forcing signal weakens or disappears.

## Write Barrier Rules

### WB-001: L0 -> L2 denied by default
A prompt, cue, or feed event must not create durable memory or preference state unless explicitly authorized.

### WB-002: L1 -> L2 requires attested promotion
Session context may be proposed for durable adoption, but only through an explicit promote-to-durable path.

### WB-003: L2 -> L3 requires constitutional procedure
Durable preferences or learned heuristics must not rewrite invariants absent a separate high-trust update channel.

### WB-004: Repeated exposure cannot bypass write barriers
The same lower-layer input repeated many times does not accumulate write authority unless policy explicitly allows that conversion.

### WB-005: Observer-affecting updates require special scrutiny
Any update that changes evidence admissibility, contradiction handling, or audit logic is automatically high-risk.

## Receipt Requirements

Every higher-layer update SHOULD emit a receipt with at least:

- `receipt_type`
- `timestamp`
- `target_layer`
- `source_layer`
- `source_ids`
- `proposed_change`
- `effective_change`
- `authority_basis`
- `operator_or_principal`
- `promotion_path`
- `repetition_count`
- `sanction_or_reward_coupling`
- `observer_impact_assessment`
- `durability_class` (transient | session | durable | constitutional)
- `rollback_plan`
- `attestation` or signature where applicable

## Minimal Receipt Shape
```json
{
  "receipt_type": "entrainment_update_v1",
  "timestamp": "2026-03-09T00:00:00Z",
  "source_layer": "L1",
  "target_layer": "L2",
  "source_ids": ["ctx:abc123"],
  "proposed_change": {
    "kind": "preference_update",
    "field": "routing.default_lane",
    "new_value": "strict"
  },
  "effective_change": {
    "applied": false,
    "reason": "insufficient_authority"
  },
  "authority_basis": "explicit_user_consent",
  "promotion_path": ["session_context", "promotion_request"],
  "repetition_count": 4,
  "durability_class": "durable",
  "observer_impact_assessment": "none",
  "rollback_plan": "not_applicable",
  "attestation": null
}
```

## Metrics

### M1: Phase-Lock Index
How tightly short-horizon behavior synchronizes to external cadence.

### M2: Reference Drift
How far the system's interpretive baseline moves over time.

### M3: Cross-Layer Gain
How much effect lower-layer inputs have on higher-layer state.

### M4: Recovery Half-Life
How long the system takes to return to baseline after forcing stops.

### M5: Observer Integrity Score
Whether the system still detects contradiction, drift, and suspicious updates with comparable sensitivity.

### M6: Hysteresis Depth
How much counter-input is required to reverse an installed change.

### M7: Promotion Legitimacy Ratio
Fraction of durable updates that followed an authorized promotion path.

## Enforcement Stance

A governed system SHOULD:

1. tag all inputs by layer and intended persistence
2. deny silent promotion across layers
3. receipt all durable changes
4. separate persuasion from policy mutation
5. measure observer degradation explicitly
6. treat repeated exposure as a risk signal, not a legitimacy signal

## Human / Institutional Mapping

This model applies beyond software.

* feed dynamics primarily modulate `a(t)`
* propaganda primarily modulates `m(t)`
* inculcation primarily modulates `p(t)`
* ideological capture often includes degradation of `o(t)`

This is not metaphorical decoration.
It is the same control problem at a different substrate.

## LLM / Agent Mapping

* prompt text = L0
* conversation context / retrieval = L1
* saved memory / preference store / fine-tune = L2
* hard policy / inviolable constraints = L3

The key rule:
A runtime instruction must not be allowed to masquerade as a policy update.

## Relationship to Existing Governor Subsystems

| Subsystem | Entrainment Role |
|-----------|-----------------|
| NLAI ("language is a proposal, not an authority") | INV-001: L0 cannot silently mutate L2/L3 |
| Two-ledger split (facts decay, decisions persist) | Write barrier between L1 and L2 |
| Correlator telemetry (K-vector, capture indicators) | Observer integrity tracking (T4, M5) |
| Taint similarity (recurrence detection) | INV-002: repetition is not authorization |
| Claim diff (silent state change detection) | T5: cross-layer contamination detection |
| Evidence gate (claims require evidence) | WB-001/WB-002: promotion requires attestation |
| Provenance labels (source classification) | Layer tagging on inputs |
| Egress gate (outbound data-flow policy) | Write barriers on outputs |
| Session continuity (capsule-based sessions) | L1/L2 boundary enforcement |
| Drift detection (temporal asymmetry defense) | M2: reference drift measurement |
| Regime detection (operational health) | Phase-layer observability |
| Scope governor (locality-first policy) | Authority containment by axis |

This spec does not introduce new enforcement machinery.
It names the enforcement principle that explains why these subsystems exist.

## Open Questions

1. How should systems distinguish benign learning from illegitimate promotion?
2. What threshold of repetition counts as a capture risk signal?
3. How should observer degradation be measured in practice?
4. What rollback guarantees are realistic for deep-layer updates?
5. Can hysteresis be bounded by design?
6. The threat taxonomy mixes capture targets (T1-T3), audit impairment (T4), structural violations (T5), and temporal dynamics (T6). Should these be separated into distinct axes?

## Candidate Derived Specs

* `GOV_GAP_MULTISCALE_POLICY_BOUNDARY_001`
* `GOV_GAP_OBSERVER_INTEGRITY_001`
* `GOV_GAP_DURABLE_PROMOTION_RECEIPTS_001`
* `GOV_GAP_CROSS_LAYER_GAIN_METRICS_001`

## One-Line Summary

The problem is not influence alone.
The problem is illegitimate promotion of transient influence into durable governing structure.
