---
audience: publication-candidate
status: active
---

# State-space atlas, not general machine

Status: doctrine
Audience: Governor implementers; anyone reaching for a state machine inside a Governor surface; anyone designing corrective, re-entry, or recovery primitives
Companion: [advisory_vs_constitutional_power.md](advisory_vs_constitutional_power.md) — the authority-side cut. This note is the operating-posture-side cut at right angles.

## Core thesis

**Mechanical validation belongs at constitutional authority boundaries. Everywhere else, the state-space map is an atlas, not an actuator.**

Governor uses state-machine discipline where constitutional validation requires it: standing, scope, basis, supersession, receipt roles and authority transitions must be mechanically checked at the boundary.

That discipline must not be generalized into the operating posture for everything Governor touches.

Outside the constitutional standing layer, state-space models are diagnostic atlases. They help identify what kind of judgment is being demanded, what inspection surface is required, and where observability, authority or standing could be laundered.

Governor's role is not to operate every state space mechanically. It is to prevent state-space claims from laundering observability, authority or standing they do not actually have.

Use the map to locate judgment. Do not let the map perform judgment.

## Where the machine layer is legitimate

The constitutional standing chain (validator C2–C5):

- Standing class × receipt role mapping
- Subject derivation enum (`same_subject` / `scope_narrowing` / `aggregation_of`)
- Authorization check completeness (standing / admissibility / scope / budget)
- Check basis structure (`Check.basis` as `CheckBasis`, not freeform string)
- Continuity basis presence-as-claim, role-gated
- Supersession ceremony (vN → vN+1 attestation chain)

These must be mechanical. Validation cannot be left to interpretation, and the supersession ceremony is exactly state-machine ritual at that boundary. The Q4 ratification protocol exists precisely because this layer needs machine-discipline.

## Where the atlas posture applies

Almost everywhere else:

- Receipt schemas — inspection surface, not dispatch table
- Signal envelopes — observe-only, missing≠zero
- Refuse-laundering tripwires — provider substitution, altitude axis
- Corrective primitives — `CorrectiveEffect` kinds, `RecoveryEnv`, re-entry surfaces
- Gap specs — candidate primitives named for review, not built

In each of these, state-space vocabulary names *what kind of object* is in play so that claims about it carry the right inspection surface. The vocabulary does not authorize Governor to dispatch on it.

## Drift surface

Symptoms of standing-layer machine-discipline drifting outward:

- Reaching for "build the X state machine" instead of "name X so the laundering surfaces"
- Treating a candidate primitive as operational rather than diagnostic
- Filing a gap spec framed "build X" rather than "name X for review"
- Importing state-space vocabulary as dispatch surface rather than inspection surface
- Extending C2–C5 standing-layer machine-discipline outward into general Governor posture

When this happens, Governor begins to authorize what it was built to refuse. Atlas behavior IS refusal-of-laundering; machine behavior pretends regulability that isn't there.

## Connection to P25

P25 (`papers/preprint/25-epistemic-border-control/`) is this same collapse seen from the controller side: when the target is unsensed, treating yourself as a state-space machine is exactly the substitution that fails. The paper formalizes the failure mode for sincere controllers facing observability asymmetry. This note is the agent-side architectural commitment that prevents Governor from being one of those sincere controllers.

The pithy form, for posting on a wall:

> Mechanical validation belongs at constitutional authority boundaries. Everywhere else, the state-space map is an atlas, not an actuator.
