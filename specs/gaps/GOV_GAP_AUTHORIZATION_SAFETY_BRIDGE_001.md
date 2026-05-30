# GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001

## Title

Agent Governor can verify that a transition is *authorized* (standing present, receipt minted, verdict positive) but does not certify that the resulting transition is *safe* (value-preserving, non-contaminating, non-poisoning). The bridge between authorized verdict and safe consequence is unstated. Lean's recent safety-bridge family (12 modules) makes the gap formal; AG has the constitutional surfaces but no named bridge.

## Status

Gap spec — containment vessel. **No bridge selected, no implementation authorized, no refactor proposed.** Names the cut, the four candidate bridges, the existing AG surfaces under audit, and the forcing-case posture. Candidate, non-binding.

## Filed

2026-05-30. Forcing context: sweep of `~/git/papers/working/tooltheory/` and `~/git/lean/LeanProofs/Admissibility/` surfaced 12 Lean modules formalizing authorization ≠ safety at verdict layer, with concrete witness (clean evidence store, value 1 → poison receipt admitted by authorized actor, value 0). The gap is no longer adjacent paper-side theory; it is a named hole in AG's stated competence.

## Origin

The Lean safety-bridge family (`SafetyBridge.lean`, `SafetyBridgeWitness.lean`, `SafetyTrajectory.lean`, `AttestationLedger.lean`, `AuthorizedStepNotSafe.lean`, `AuthorizedStepNotSafeWitness.lean`, `AuthorizedNotSafe.lean`, `AuthorizedNotSafeWitness.lean`) closes the formal cut:

> **Safety := authorization ∧ bridge.**
> **Bridge entails value non-decrease. Authorization never entails safety.**

The witness module proves the slot is non-vacuous: a `StepAllowed` predicate at maximum value (standing maximal, verdict positive) does not entail defended-value preservation. Concrete miniature: clean evidence store (value 1) → authorized actor admits poison receipt → state changes, authorization holds, value falls to 0. No axioms required.

The `AuthorizedStepNotSafe*.lean` pair lifts this to the verdict layer: an all-green kernel-legible verdict (every component positive in `Authority.authorityVerdict`) still admits an unsafe witness. **Verdict authorization is orthogonal to safety bridge.**

The operator-side keeper from the 2026-05-30 sweep review:

> **AG should not become the recovery priest. But it absolutely needs to know that an authorized receipt can still be poison.**

This is the operationally-grippy version of the formal cut. AG already has the constitutional surfaces (receipt kernel, authority kernel, scope governor, egress gate, evidence gate, runtime supervisor). What is missing is the *named* bridge that closes the authorization → safety gap.

## Problem Statement

AG's gate stack today:

1. **Authorization layer** — intent compiler, scope governor, validator chain (C2/C3/C4/C5), gate receipts. Confirms standing, scope, policy binding, role eligibility.
2. **Verdict layer** — gate evaluation produces a verdict (allow / block / observe) with receipts (`subject_hash`, `evidence_hash`, `policy_hash`).
3. **Execution layer** — wrapper, hooks, runtime supervisor mediate the mutation.

A gate receipt with `verdict: allow` testifies that the gate ran with that evidence and produced that verdict at that time. It does not testify that the mutation that follows preserves the defended value.

The structural risk:

| Step | What AG verifies | What AG does not verify |
|------|------------------|-------------------------|
| Receipt minting | subject_hash, evidence_hash, policy_hash, standing chain | value-preservation of the action the receipt authorizes |
| Verdict computation | claim categories, evidence kinds, policy thresholds | bridge between the authorized step and the defended-value floor |
| Mutation execution | scope grant, policy version, drift verdict at attempt time | post-mutation value preservation |
| Trajectory | individual hops are authorized | end-to-end defended-value floor is preserved across hops |

The Lean kernel makes the cut explicit: `Authority.authorityVerdict` is a verdict-layer predicate; `SafetyBridge.lean` requires a separate value-blind structural predicate (the bridge) that the verdict does *not* imply. The bridge must do real discriminating work — `SafetyBridgeWitness.lean` shows a bridge candidate (non-contamination via receipt genuineness) that rejects a poison receipt even when both poison and genuine paths are fully authorized.

AG does not currently name this bridge. The closest existing surfaces are partial:

| Surface | What it does | Why it is not the bridge |
|---------|--------------|--------------------------|
| `gate_receipt.py` | Content-addressed receipts (subject/evidence/policy hash) | Testifies *that* the gate ran with that evidence; does not certify the receipt itself is non-poisoned |
| `evidence_gate.py` | Custody scoring, claim extraction, evidence linking | Custody is a property of evidence collection; does not pin value preservation across the step |
| `egress_gate.py` | Outbound classification + policy bridge | Refuses sensitive outbound flow; does not certify the *received* artifact preserves value |
| `scope.py` | Locality-first policy, escalation receipts | Constrains *where* mutation may happen; does not constrain *whether the resulting state* preserves value |
| `governed_activity.py` | FactObservation + DriftCheckResult at attempt time | Drift detection is a *signal*, not a value-preservation predicate |
| Validator chain (C2/C3/C4/C5) | Standing / schema / basis / continuity discipline | Authorization-layer predicates; explicitly *not* safety per the Lean cut |

Each surface is correct on its own axis. None is the safety bridge. The gap is the missing *named* predicate that AG must ratify in order to claim "the authorized step was safe."

## Failure Mode

The laundering path:

1. AG emits a gate receipt with `verdict: allow` for an action whose evidence chain checks all four C2-C5 boundaries: standing chain valid, schema valid, basis structured, continuity basis present where required.
2. The receipt is consumed downstream (an operator action, a supervisor approval, a session capsule resume, a continuity bridge).
3. The downstream consumer treats the receipt as testimony that the action was *safe* — value-preserving, non-contaminating, non-poisoning.
4. The receipt testifies only to authorization. The Lean witness (`AuthorizedNotSafeWitness.lean`) is the lived form: clean evidence store value 1 → authorized actor admits a poison receipt → state changes, authorization holds, value falls to 0.
5. AG has no surface that refuses this laundering at the verdict→execution boundary.

The structural risk is not that any gate is wrong on its own axis. The risk is that **authorization is treated as a sufficient gate** when the formal kernel says it is necessary but not sufficient. The downstream consumer's mental model — "if AG authorized it, it is safe to act on" — is a category error AG's existing surface does not refuse.

This is a different shape from `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` (which names receipt_kernel ≠ authority_kernel at the *attestation* boundary). Sealed-outcome names that *the seal does not certify the outcome*. This gap names that *the authority does not certify the safety of the transition.* Adjacent, not identical. Both are needed; neither subsumes the other.

## Bridge Candidates (Not Selected)

The Lean modules name four candidate bridge shapes. AG has primitive forms of each; none is currently wired as *the* bridge:

### 1. Receipt persistence

The bridge is: the receipt that authorized the step is the same receipt that was actually written to the receipt store, retrievable by hash, with its blob intact at the time of consequence. Poisoning by post-hoc receipt mutation is refused.

AG primitive: `ReceiptStore` (content-addressed, JSONL append-only). What's missing: a predicate that consumers of a receipt verify *the receipt they hold is the receipt that was minted*, not a poisoned overlay.

### 2. Witness encapsulation

The bridge is: the witness underlying the authorization is qualified for the perturbation regime in which the action is taken. Poisoning by perturbation-class widening is refused.

AG primitive: partial — `GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001` names the qualification primitive; no implementation. The safety-bridge would consume the qualification predicate when it lands.

### 3. Non-contamination

The bridge is: the action constructor (the function applied to state) does not admit poison receipts as inputs. The bridge inspects the *structure* of what is being admitted, not the value of the actor admitting it.

AG primitive: `evidence_gate.py` claim extraction + custody scoring, `provenance_labels.py` (taint tracking, sensitivity propagation). What's missing: a step-layer predicate that says "this admit operation refuses any receipt without intact provenance label chain."

### 4. Value-decay preservation

The bridge is: the defended-value floor at step end is at least the defended-value floor at step start, measured by a value-blind predicate that the actor cannot influence. Poisoning by silent value erosion is refused.

AG primitive: absent. The TTL / volatility class machinery is recency-based, not value-based. The drift detector tracks *change*, not *value loss*. This is the candidate furthest from AG's existing surface.

Each candidate is coherent. The Lean witness (`SafetyBridgeWitness.lean`) shows that **non-contamination** is non-vacuous and discriminates correctly on a toy substrate. AG's selection is not committed by this filing.

## Existing Governor Coverage (Sibling Surfaces)

| Surface | Carries part of the bridge? |
|---------|------------------------------|
| `gate_receipt.py` — content-addressed receipts | Yes — receipt persistence candidate's substrate |
| `evidence_gate.py` — custody scoring, claim extraction | Yes — non-contamination candidate's substrate |
| `provenance_labels.py` — taint tracking, sensitivity propagation | Yes — non-contamination candidate's substrate |
| `egress_gate.py` — classification + policy bridge | Adjacent — refuses sensitive outbound, but inbound poisoning is the safety-bridge concern |
| `scope.py` — locality-first policy | Adjacent — constrains *where*, not *whether-safe* |
| `governed_activity.py` — drift-gated retry | Adjacent — drift signals value change but does not encode the floor |
| Standing validator chain (C2-C5) | No — explicitly authorization-layer per the Lean cut |
| `semantic_stability.py` — perturbation audit | Adjacent — measures drift continuously; does not produce a binary safety verdict |
| `correlator_telemetry.py` — K-vector capture indicators | Adjacent — observes capture failure modes; does not certify safety of a single step |

None of these is wrong. The gap is the missing *named* bridge predicate that composes them at the verdict→execution boundary.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Names the cut — authorization ≠ safety at the verdict layer — and refuses the laundering path explicitly.
2. Identifies the four bridge candidates (receipt persistence / witness encapsulation / non-contamination / value-decay preservation) and what existing AG surface partially carries each.
3. Records that the Lean safety-bridge family is *the formal target*, not a binding import. AG's instantiation, if forced, would not port the Lean definitions.
4. Identifies forcing cases that would justify selecting a bridge: a postmortem where an authorized verdict was treated as testimony for safety and the resulting transition failed value preservation; a supervisor session in which a `verdict: allow` was consumed across boundaries that change the relevant perturbation regime; an evidence-gate pass that admitted a poisoned receipt while custody scoring was nominally positive.
5. Does not specify implementation. Bridge selection waits on forcing case. Wire-level changes (a `bridge_hash` axis on gate receipts, a step-layer safety predicate in the runtime supervisor, a non-contamination guard in evidence gate) are implementation territory and not drafted here.

## Doctrine (proposed; not yet ratified)

> **Authorization is necessary for safety. Authorization is not sufficient for safety.**
>
> **An authorized receipt can still be poison.**
>
> **AG verifies authorization. The safety bridge is the predicate that closes the gap between authorized verdict and safe consequence. Without a named bridge, downstream consumers will launder authorization into safety.**

Candidate doctrine until a forcing case selects a bridge.

## Non-goals

- **Not a bridge selection.** The four candidates (receipt persistence / witness encapsulation / non-contamination / value-decay preservation) are named, not chosen.
- **Not a refactor of `gate_receipt.py`, `evidence_gate.py`, `provenance_labels.py`, or any existing surface.** Each is correct on its axis; the gap is the composition predicate, not the underlying axes.
- **Not a port of the Lean safety-bridge family.** AG's eventual instantiation, if forced, will be a typed primitive over `(GovState, Step, Actor)`, not a port of `SafetyBridge.lean` definitions.
- **Not an absorption of recovery-topology vocabulary.** `GOV_GAP_RECOVERY_TOPOLOGY_LOCK_001` (candidate, pointer-only) is a *sibling* gap, not subsumed by safety-bridge. Safety-bridge is about per-step value preservation; recovery-topology is about the governor's role in cross-step recovery paths. Both belong; neither subsumes the other.
- **Not a global health verdict.** AG does not certify "the system is safe." The bridge predicate operates per-step at the verdict→execution boundary.
- **Not ratification of the Lean cut as AG doctrine.** The cut is the *forcing observation* that this gap exists. AG's doctrine waits on the bridge selection.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Sibling. Names receipt_kernel ≠ authority_kernel at the *attestation* boundary. This gap names authorization ≠ safety at the *consequence* boundary. Adjacent, both needed.
- **`GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001`** — Sibling. Names qualification-vs-drift at the per-witness level. Composes with this gap at the **witness encapsulation** bridge candidate.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Sibling. Names missing content-semantic enforcement on `admissibility_check`. Composes with this gap at the **non-contamination** bridge candidate (basis-semantic content is what non-contamination would inspect).
- **`GOV_GAP_PHASE_WITNESS_MAPPING_001`** — Adjacent. Phase witnesses testify to what gates observed. Safety-bridge is what closes the gap between gate-ran (phase-witness territory) and action-was-safe (this gap).
- **`GOV_GAP_RECOVERY_TOPOLOGY_LOCK_001`** — Candidate sibling (pointer-only, not yet filed). Recovery topology is the cross-step structural analog; safety-bridge is the per-step value-preservation analog. Both belong.
- **Lean `SafetyBridge.lean` + family** — Formal target. 12 modules; AG's instantiation would not port their definitions, but consume the cut they formalize.
- **`gate_receipt.py`, `evidence_gate.py`, `provenance_labels.py`, `egress_gate.py`, `governed_activity.py`, `scope.py`, validator chain** — The existing AG surfaces under audit. None is wrong; the gap is the missing composition predicate.

## Open Questions

1. Which bridge candidate (receipt persistence / witness encapsulation / non-contamination / value-decay preservation) does AG's existing surface mass best support, and which would require the most retrofit? Non-contamination has the most existing substrate (provenance labels + custody scoring); value-decay preservation has the least.
2. Where in the stack does the bridge live? Three coherent positions: (a) per-step at the wrapper / runtime supervisor; (b) per-receipt at gate_receipt.py emission; (c) per-trajectory at session capsule promotion. Lean treats the bridge as step-level; AG's deployment may want trajectory-level for some surfaces.
3. Does the bridge produce its own receipt, or annotate the existing gate receipt? A separate `safety_bridge_receipt` is purest; annotation is most retrofittable.
4. Does the bridge interact with the standing validator chain, or operate purely after it? The Lean modules treat them as orthogonal (verdict authorization is C2-C5 territory; safety is bridge territory). AG's surface should preserve that orthogonality unless a forcing case demands coupling.
5. How does this gap compose with `GOV_GAP_PHASE_WITNESS_MAPPING_001`'s eight authority-bearing phases? Safety-bridge is the predicate; phase witnesses are the testimony. The mapping table in the phase-witness gap may need a safety-bridge column when both ratify.
6. Does the bridge inherit the operating-envelope distinction (strict vs exploratory)? In strict mode, missing bridge → block; in exploratory, missing bridge → log + warn. Coherent; not committed.

## Provenance

Filed 2026-05-30 after a parallel sweep of `~/git/papers/working/tooltheory/` (May 28-30) and `~/git/lean/LeanProofs/Admissibility/` (modules added since `RefusalKernel.lean` on 2026-05-25). The Lean safety-bridge family (8 modules: `SafetyBridge.lean`, `SafetyBridgeWitness.lean`, `SafetyTrajectory.lean`, `AttestationLedger.lean`, `AuthorizedStepNotSafe.lean`, `AuthorizedStepNotSafeWitness.lean`, `AuthorizedNotSafe.lean`, `AuthorizedNotSafeWitness.lean`) formalizes the cut authorization ≠ safety with a concrete witness on a toy substrate.

The operator review of the sweep called this the AG-live cluster: "twelve Lean modules plus AG's existing egress/authority boundary is enough. This is not 'interesting paper-side vocabulary.' It is a hole in AG's stated competence: it can authorize a transition without yet proving the transition is safe."

The pointer for the recovery-topology cluster is filed separately at `~/.claude/projects/-home-jbeck-git-agent-gov/memory/recovery_topology_candidate.md` (reserves the name `GOV_GAP_RECOVERY_TOPOLOGY_LOCK_001`, blocked on AG recovery-coordination forcing case). The remaining tooltheory + Lean material (`ProjectionLaundering.lean`, `Conductance.lean`, `ConsequencePartition.lean`, `RefusalPropagation.lean`, `projection-laundering.md`, etc.) is filed as cite-don't-extract — vocabulary-grade, no retrofit pressure.

The asymmetric landing (one gap + one pointer + cite-don't-extract for the rest) is the operating principle for this sweep: file where AG-live pressure exists, reserve names where the cluster is real but the AG surface is not yet pressured, cite the rest. See `~/.claude/projects/-home-jbeck-git-agent-gov/memory/feedback_asymmetric_recognition_landing.md` for the rule.

This gap is a containment vessel. It does not authorize a build, ratify a bridge, or commit AG to a specific implementation. It names the cut, the four candidates, the existing partial surfaces, and the forcing-case posture. Bridge selection waits.
