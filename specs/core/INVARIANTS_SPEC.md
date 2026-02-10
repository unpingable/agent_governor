# Core Invariants Specification

```yaml
status: canonical
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC]
note: Consolidated invariant list referenced by all 2.1 specs. Reference document — not an implementation target.
```

## Overview

Ten invariants that define the governor's safety envelope. These are not tunable parameters — they are structural properties that must hold for the system to be meaningful.

Every invariant has a mechanically verifiable check function returning `(bool, reason)` or a violation list. These are not advisory — violations block the action.

---

## Invariant A (Authority)

Execution claims imply ledger evidence.

```
claim(did a) ⟹ ∃e ∈ L: e = tool_result(a)
```

You cannot claim to have done something without a receipt in the ledger proving the tool ran.

**Implementation:** `fsm.py:verify()` enforces that transitions from PROPOSED to VERIFIED require receipts (`FileSnapshot`, `CmdRun`, `DiffReceipt` from `receipts.py`). No receipt, no state transition.

---

## Invariant B (Capabilities)

Tool actuation must be admissible under scoped tokens.

```
u_t ∈ U(x^cap_t)
```

Every action requires a valid capability token with matching scope, verbs, and TTL.

**Implementation:** `deployment_profiles.py` — `CapabilityToken` dataclass with `scope: set[str]`, `verbs: set[str]`, `ttl_seconds: int`, `rate_limit: RateLimit`. `CapabilityToken.permits(verb, resource)` checks all conditions atomically. `check_invariant_b(token, verb, resource)` returns `(False, reason)` if token is expired, out of scope, or verb mismatch. Authority classes A1–A4 defined with tool whitelists/blacklists.

See: DEPLOYMENT_PROFILES_SPEC.md

---

## Invariant C (Telemetry)

Only signed+schema tool outputs update state estimates.

```
trusted(z_t) ⟺ sig(z_t) ∧ schema(z_t)
```

Untrusted tool output is quarantined, not integrated into the state estimate.

**Implementation:** `measurement_integrity.py` — `is_trusted(output)` verifies signature AND schema. `evaluate_output()` classifies as TRUSTED/UNTRUSTED/QUARANTINED, with frozen tool detection and instruction masquerade detection. `check_invariant_c(state)` returns violations for untrusted blobs without risk score updates. Alert types: UNTRUSTED_BLOB, INSTRUCTION_MASQUERADE, SCHEMA_VIOLATION, SIGNATURE_MISSING, TOOL_FROZEN.

See: MEASUREMENT_INTEGRITY_SPEC.md

---

## Invariant D (Budget)

Per-run actuation consumes a nonnegative budget vector.

```
B_{t+1} = B_t - c(u_t), B_{t+1} ≥ 0
```

Actions have costs. Budget cannot go negative.

**Implementation:** `phase_control.py` — `PhaseBudget` with per-phase allocations (explore, draft, verify). `PhaseUsage.remaining()` computes `max(0, budget - used)`. `PhaseController.consume_action()` returns `False` if budget exhausted, preventing further actions.

See: PHASE_CONTROL_SPEC.md

---

## Invariant E (Irreversible Actions)

Require approval event (two-phase commit).

```
u^irrev_t enabled ⟺ ∃e ∈ L: e = approval(run_id, action_hash)
```

Irreversible actions require an approval event in the ledger before execution.

**Implementation:** `deployment_profiles.py` — `ActionProposal` with status PENDING → APPROVED → EXECUTED. `ActionProposal.approve(by)` records approver. `ActionProposal.execute()` validates APPROVED status and not expired. `check_invariant_e(profile, severity, proposal)` checks `profile.needs_approval(severity)` and validates proposal state. `DeploymentProfile.requires_two_phase` specifies which severity levels (S2/S3) need approval.

See: DEPLOYMENT_PROFILES_SPEC.md

---

## Invariant F (No Hidden Assumptions)

All assumptions for S2/S3 actions must be explicit and logged.

No hidden assumptions. Every assumption is:
- Explicitly logged with an event
- Severity-tagged (S1/S2/S3)
- Waivable only with explicit user acknowledgment

**Implementation:** `admissibility.py` — `Unknown` dataclass (id, severity, category, resolvable_by) tracks unknowns explicitly. `Assumption` dataclass links to unknowns with status and waiver fields. `check_invariant_f(assumptions, unknowns)` enforces: (1) all S2/S3 unknowns must have explicit assumptions, (2) S3 assumptions must be waived, not just active. Returns violation list.

See: ADMISSIBILITY_SPEC.md

---

## Invariant G (Phase Budget Lock)

B_verify is inaccessible until phase ≥ VERIFY.

```
phase < VERIFY ⟹ B_verify.available = 0
```

Verification budget is locked until the verification phase. This prevents blowing verification capacity on early exploration.

**Implementation:** `phase_control.py` — `PhaseBudget.available(phase)` returns 0 for verify budget when `phase < Phase.VERIFY`. `check_invariant_g(phase, budget)` validates this constraint. Phase enum: SPECIFY(0) < EXPLORE(1) < DRAFT(2) < VERIFY(3) < COMMIT(4).

See: PHASE_CONTROL_SPEC.md

---

## Invariant H (Passivity)

Confidence must trace to sensor evidence or explicit waiver. Fluency is not evidence.

```
confidence(c) > τ ⟹ (evidence(c) > 0) ∨ (waiver(c) ∈ L)
```

Unsupported confidence is inadmissible. The model cannot generate certainty from fluency alone.

**Implementation:** `coherence_budget.py` — `check_passivity(claim, has_waiver, threshold)` enforces: confidence below threshold (0.7) is allowed; above threshold requires either evidence (count > 0 or refs > 0) or explicit waiver. Returns `(bool, reason)`.

See: COHERENCE_BUDGET_SPEC.md

---

## Invariant I (Closure Gate)

No COMMIT while uncertainty U_t > τ without explicit human waiver.

```
COMMIT enabled ⟺ (U_t ≤ τ) ∨ (waiver ∈ L)
```

Uncertainty is computed from unverified claims (severity-weighted) plus open unknowns. COMMIT is blocked until uncertainty is resolved or waived.

**Implementation:** `coherence_budget.py` — `compute_uncertainty(claims, unknowns)` sums severity-weighted unverified claims plus open unknowns. `check_closure_gate(claims, unknowns, threshold, has_human_waiver)` returns `ClosureGateResult` with decision ALLOW/ALLOW_WITH_WAIVER/DENY.

See: COHERENCE_BUDGET_SPEC.md

---

## Invariant J (Epistemic Evasion)

Outputs must not systematically deploy evasion operators. High evasion score triggers confidence cap and mechanism request.

```
evasion_score(output) > τ ⟹ confidence_cap ∧ require_mechanism
```

Patterns that optimize for unfalsifiability rather than truth-tracking are detected and penalized.

**Implementation:** `epistemic_evasion.py` — 11 evasion operators (Frame Router, Motte Fallback, Hedge Injector, Virtue Shield, Incentive Solvent, Pedantry Deflection, Context Weapon, Moral Rebinding, Status Anchor, Plausible Deniability Commit, Audience Partitioning). `analyze_evasion(text, context)` runs all detections, computes weighted composite score, classifies severity (LOW/MODERATE/HIGH), identifies failure modes (FM1–FM5), selects forced coupling question. `check_invariant_j(text, context)` returns `(False, reason)` if severity is HIGH.

5 composite failure modes:
- **FM1**: Falsification avoidance (HI, MF, PDC, CW)
- **FM2**: Accountability evasion (IS, FR, CW)
- **FM3**: Semantic load shedding (MF, HI, VS)
- **FM4**: Verification cost inflation (SA, IS, PD)
- **FM5**: Moral axis hot-swapping (MR, FR)

See: EPISTEMIC_EVASION_SPEC.md

---

## Summary Table

| ID | Name | Enforcement | Module | Check Function | Spec |
|----|------|-------------|--------|----------------|------|
| A | Authority | Hard — no receipts, no claims | `fsm.py`, `receipts.py` | `verify()` | Core |
| B | Capabilities | Hard — token-gated actuation | `deployment_profiles.py` | `check_invariant_b()` | DEPLOYMENT_PROFILES_SPEC |
| C | Telemetry | Hard — untrusted = quarantined | `measurement_integrity.py` | `check_invariant_c()` | MEASUREMENT_INTEGRITY_SPEC |
| D | Budget | Hard — nonnegative budget vector | `phase_control.py` | `consume_action()` | PHASE_CONTROL_SPEC |
| E | Irreversible Actions | Hard — two-phase commit | `deployment_profiles.py` | `check_invariant_e()` | DEPLOYMENT_PROFILES_SPEC |
| F | No Hidden Assumptions | Hard — logged + severity-tagged | `admissibility.py` | `check_invariant_f()` | ADMISSIBILITY_SPEC |
| G | Phase Budget Lock | Hard — verify budget locked | `phase_control.py` | `check_invariant_g()` | PHASE_CONTROL_SPEC |
| H | Passivity | Hard — evidence or waiver | `coherence_budget.py` | `check_passivity()` | COHERENCE_BUDGET_SPEC |
| I | Closure Gate | Hard — uncertainty gating | `coherence_budget.py` | `check_closure_gate()` | COHERENCE_BUDGET_SPEC |
| J | Epistemic Evasion | Soft → Hard at threshold | `epistemic_evasion.py` | `check_invariant_j()` | EPISTEMIC_EVASION_SPEC |

---

## Cross-Cutting Properties

**All invariants share:**
- Mechanically verifiable check functions (no human judgment required)
- Return type is `(bool, reason)` or violation list
- Violations block the action (not advisory)
- Human override requires explicit waiver event in the ledger

**Dependency structure:**
- A is foundational (core FSM, no AG2 dependency)
- B, C, E depend on deployment profiles + measurement integrity (Layer 2.1-B)
- D, G depend on phase control (Layer 2.1-A)
- F depends on admissibility (Layer 2.1-A)
- H, I depend on coherence budget (Layer 2.1-C)
- J depends on epistemic evasion (Layer 2.1-C)

**The meta-invariant:** No invariant can be weakened without an explicit waiver event in the ledger. The governor constrains itself by the same rules it enforces on agents.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-02 | Initial planning draft — formal definitions only |
| 1.0 | 2025-02 | Canonical reference — implementation cross-references added |
