# Core Invariants Specification

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC]
note: Consolidated invariant list referenced by all 2.1 specs
```

## Overview

Ten invariants that define the governor's safety envelope. These are not tunable parameters — they are structural properties that must hold for the system to be meaningful.

---

## Invariant A (Authority)

Execution claims imply ledger evidence.

```
claim(did a) ⟹ ∃e ∈ L: e = tool_result(a)
```

You cannot claim to have done something without a receipt in the ledger proving the tool ran.

---

## Invariant B (Capabilities)

Tool actuation must be admissible under scoped tokens.

```
u_t ∈ U(x^cap_t)
```

Every action requires a valid capability token with matching scope, verbs, and TTL.

See: DEPLOYMENT_PROFILES_SPEC.md

---

## Invariant C (Telemetry)

Only signed+schema tool outputs update state estimates.

```
trusted(z_t) ⟺ sig(z_t) ∧ schema(z_t)
```

Untrusted tool output is quarantined, not integrated into the state estimate.

See: MEASUREMENT_INTEGRITY_SPEC.md

---

## Invariant D (Budget)

Per-run actuation consumes a nonnegative budget vector.

```
B_{t+1} = B_t - c(u_t), B_{t+1} ≥ 0
```

Actions have costs. Budget cannot go negative.

See: PHASE_CONTROL_SPEC.md

---

## Invariant E (Irreversible Actions)

Require approval event (two-phase commit).

```
u^irrev_t enabled ⟺ ∃e ∈ L: e = approval(run_id, action_hash)
```

Irreversible actions require an approval event in the ledger before execution.

See: DEPLOYMENT_PROFILES_SPEC.md

---

## Invariant F (No Hidden Assumptions)

All assumptions for S2/S3 actions must be explicit and logged.

No hidden assumptions. Every assumption is:
- Explicitly logged with an event
- Severity-tagged (S1/S2/S3)
- Waivable only with explicit user acknowledgment

See: ADMISSIBILITY_SPEC.md

---

## Invariant G (Phase Budget Lock)

B_verify is inaccessible until phase ≥ VERIFY.

```
phase < VERIFY ⟹ B_verify.available = 0
```

Verification budget is locked until the verification phase. This prevents blowing verification capacity on early exploration.

See: PHASE_CONTROL_SPEC.md

---

## Invariant H (Passivity)

Confidence must trace to sensor evidence or explicit waiver. Fluency ≠ evidence.

```
confidence(c) > τ ⟹ (evidence(c) > 0) ∨ (waiver(c) ∈ L)
```

Unsupported confidence is inadmissible. The model cannot generate certainty from fluency alone.

See: COHERENCE_BUDGET_SPEC.md

---

## Invariant I (Closure Gate)

No COMMIT while uncertainty U_t > τ without explicit human waiver.

```
COMMIT enabled ⟺ (U_t ≤ τ) ∨ (waiver ∈ L)
```

Uncertainty is computed from unverified claims (severity-weighted) plus open unknowns. COMMIT is blocked until uncertainty is resolved or waived.

See: COHERENCE_BUDGET_SPEC.md

---

## Invariant J (Epistemic Evasion)

Outputs must not systematically deploy evasion operators. High evasion score triggers confidence cap and mechanism request.

```
evasion_score(output) > τ ⟹ confidence_cap ∧ require_mechanism
```

Patterns that optimize for unfalsifiability rather than truth-tracking are detected and penalized.

See: EPISTEMIC_EVASION_SPEC.md

---

## Summary Table

| ID | Name | Enforcement | Spec |
|----|------|-------------|------|
| A | Authority | Hard — no receipts, no claims | Core (existing) |
| B | Capabilities | Hard — token-gated actuation | DEPLOYMENT_PROFILES_SPEC |
| C | Telemetry | Hard — untrusted = quarantined | MEASUREMENT_INTEGRITY_SPEC |
| D | Budget | Hard — nonnegative budget vector | PHASE_CONTROL_SPEC |
| E | Irreversible Actions | Hard — two-phase commit | DEPLOYMENT_PROFILES_SPEC |
| F | No Hidden Assumptions | Hard — logged + severity-tagged | ADMISSIBILITY_SPEC |
| G | Phase Budget Lock | Hard — verify budget locked | PHASE_CONTROL_SPEC |
| H | Passivity | Hard — evidence or waiver | COHERENCE_BUDGET_SPEC |
| I | Closure Gate | Hard — uncertainty gating | COHERENCE_BUDGET_SPEC |
| J | Epistemic Evasion | Soft → Hard at threshold | EPISTEMIC_EVASION_SPEC |
