---
audience: publication-candidate
status: active
---

# Governor posture: advisory reasoning, constitutional authority

Status: doctrine
Audience: Governor / Night Shift / NQ implementers, anyone touching authority boundaries in this ecosystem
Position in chain: 1 of 3 — **start here**
Next: [standing_and_receipts.md](standing_and_receipts.md) — formal taxonomy
Then: [validator_contract.md](validator_contract.md) — constitutional checks
Open questions: [`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md`](../../specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md)

## Core thesis

**Reasoning is advisory power. Governor is constitutional power.**
Advisory power may inform authority, but it must not silently become authority.

The system exists to ensure that:

- language can **propose**
- evidence can **accuse**
- policy can **bind**
- tools can **act**
- receipts can **show the lineage of each transition**

The point is not to make discretion smarter.
The point is to **make illegible discretion harder**.

## Architectural rule

**Governor-called, not Governor-native.**

Open-ended reasoning, diagnosis, decomposition, planning, ambiguity resolution, and repair proposal generation belong outside the authority layer.

Governor may consume reasoning artifacts, but it must treat them as **claims with standing limits**, not as latent policy.

## Layer roles

### NQ

Role: **observation / accusation**

NQ detects conditions, anomalies, persistence, co-occurrence, and regime hints.
It produces findings, not permissions.

NQ may say:

- this condition exists
- this pattern persisted
- this regime signature is present
- this evidence bundle supports an operational claim

NQ may not say:

- therefore action X is authorized
- continuity holds
- operator intent can be inferred
- policy should be relaxed

### Night Shift

Role: **interpretation / recommendation**

Night Shift interprets findings, proposes hypotheses, generates repair options, identifies continuity risks, and suggests candidate action plans.

Night Shift may say:

- these are plausible explanations
- these are candidate actions
- this path likely preserves continuity better than that one
- these ambiguities remain unresolved

Night Shift does not have binding standing.

### Governor

Role: **constitutional gate / authority**

Governor enforces standing, admissibility, scope, policy, budget, and tool boundaries.
It does not perform open-ended interpretation as a substitute for policy.

Governor may say:

- this proposal is admissible
- this actor has standing
- this action falls within policy
- this request exceeds scope or budget
- uncertainty at this boundary requires denial, escalation, or operator confirmation

Governor should not say:

- I infer this is probably safe
- I reinterpret the policy in light of likely intent
- continuity is close enough
- the missing evidence can be socially reconstructed

### Tool / runtime

Role: **execution**

Tools do the thing. They do not authorize themselves.

## Standing classes

Standing is explicit and typed. See [standing_and_receipts.md](standing_and_receipts.md) for the formal taxonomy. Summary:

1. **Observational standing** — can assert what was seen, measured, captured
2. **Interpretive standing** — can offer hypotheses, diagnoses, decompositions
3. **Recommendatory standing** — can propose a bounded action or plan
4. **Constitutional standing** — can bind the system to permit/deny/escalate under policy (Governor only)
5. **Executory standing** — can carry out an already-authorized action (tools/runtimes only)

## Invariants

These are the hard rules.

### Invariant 1: no silent standing escalation

An artifact produced with observational, interpretive, or recommendatory standing must not be treated as if it has constitutional standing.

No implicit upgrades. No "helpful" reinterpretation.

### Invariant 2: deny on boundary uncertainty

If Governor cannot determine admissibility, scope, policy fit, or standing with sufficient confidence, it must **deny, downgrade, or escalate**.

Uncertainty at the authority boundary is not a cue for creativity.

### Invariant 3: ontology changes are policy changes

Any risk class, action class, admissibility class, or other closed ontology used by Governor is a **versioned policy artifact**.

Adding, removing, splitting, or renaming classes is not config churn. It is a constitutional change and must carry receipt lineage.

### Invariant 4: continuity cannot be inferred by convenience

Missing evidence, broken provenance, ambiguous identity, or unwarranted operator confidence cannot be smoothed over by interpretive optimism.

Continuity must be demonstrated against doctrine, not socially hallucinated under time pressure.

### Invariant 5: tool execution requires explicit parent authority

No tool action without a parent authorization artifact.

No execution on the basis of prose, implication, or model confidence.

## What Governor may do natively

Only bounded clerical cognition with closed consequence surfaces.

Acceptable:

- schema validation
- policy lookup
- standing check
- scope check
- budget accounting
- receipt normalization
- closed-set routing
- deterministic or tightly constrained classification

Even here, two constraints:

1. outputs should be typed and narrow
2. uncertainty should fail closed

## What Governor must not do natively

No native open-ended:

- diagnosis
- repair planning
- ambiguity resolution
- continuity interpretation
- risk invention
- policy interpolation beyond declared rules
- "common sense" exception handling

That is how prompt-shaped discretion becomes sovereign.

## Failure modes to name explicitly

These are the rot points.

### "Just a little interpretation"

Classic constitutional corrosion. Usually arrives under urgency, with the best intentions, carrying a wrench.

### Closed ontology drift

The class set expands informally until it becomes an invisible policy substrate. Then nobody remembers when the constitution became vibes.

### Receipt collapse

Interpretation, recommendation, and authorization get compressed into one artifact. This saves time and destroys legibility.

### Continuity laundering

A restore or repair is treated as continuity-bearing because it is narratively convenient, not because identity, provenance, evidence, and operator confidence survived.

### Operator pressure against denial

People will treat denial as operational failure. It is often the proof that the authority boundary is still alive.

## Symmetry with claimant transition

Night Shift is a **claimant** in the weak sense.
It can speak, propose, and be heard.

Governor has **binding standing**.
It can decide whether the claim crosses the threshold into force.

That symmetry generalizes beyond this stack:

- not everything that can speak can bind
- not everything that can observe can interpret
- not everything that can recommend can execute

## Minimal implementation shape

First pass:

- NQ emits **finding receipts**
- Night Shift consumes finding receipts and emits:
  - **interpretation receipts**
  - **recommendation receipts**
- Governor consumes recommendation receipts plus policy artifacts and emits:
  - **authorization receipts**
- Tool/runtime consumes authorization receipts and emits:
  - **action receipts**

Mandatory fields on every transition:

- `role`
- `standing_class`
- `policy_artifact_id`
- `policy_artifact_hash`
- `ontology_version`
- `parent_receipt_ids`
- `subject`
- `verdict`
- `uncertainty`
- `gaps`

See [standing_and_receipts.md](standing_and_receipts.md) for full field specifications and [validator_contract.md](validator_contract.md) for the constitutional checks that make these rules operative.

## Compressed doctrine lines

- **Reasoning is advisory power. Governor is constitutional power.**
- **Make illegible discretion harder, not smarter.**
- **Deny on uncertainty at the authority boundary.**
- **Ontology drift is policy drift.**
- **The prompt is not the policy.**
- **Continuity cannot be inferred by convenience.**
- **3am always votes for monarchy.**
