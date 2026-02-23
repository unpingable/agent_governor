# PCAR-C: Constraint Decisions and Regime Derivation
## Control Law for Proof-Carrying Agent Runtime

- **Status:** Draft
- **Version:** 0.1.0
- **Family:** PCAR
- **Depends on:** PCAR-000, PCAR-A, PCAR-B
- **Last Updated:** 2026-02-23
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-C defines the **Constraint Decision** schema and **Regime Derivation** semantics for a Proof-Carrying Agent Runtime (PCAR).

PCAR-C is the control law. It consumes typed claims (PCAR-A), proof objects (PCAR-B), and policy to produce deterministic decisions about whether proposed actions are allowed, denied, deferred, or require re-verification. It also derives the runtime's operational regime from observable signals.

PCAR-C is where "the governor" lives. Everything before it (claims, proofs) is observation and measurement. Everything after it (actuation, receipts) is consequence and record. PCAR-C is the decision boundary.

---

## 2. Scope

PCAR-C specifies:

- constraint decision schema,
- decision vocabulary,
- policy pack interface,
- regime derivation and signal vocabulary,
- constraint vocabulary,
- determinism requirements,
- decision expiry semantics,
- decision-level error semantics.

PCAR-C does **not** specify:

- claim typing (PCAR-A),
- proof generation (PCAR-B),
- receipt canonicalization (PCAR-D),
- actuation contracts (PCAR-E),
- policy content (only policy interfaces).

---

## 3. Design Goals

### 3.1 Deterministic Evaluation

Given identical claims, proofs, policy version, and runtime state, the constraint engine MUST produce the same decision. No hidden randomness, no non-deterministic tie-breakers, no model consultation.

### 3.2 Machine-Readable Rationale

Decision rationale is expressed as machine-readable codes, not prose. Human text can be generated from codes later. Prose MUST NOT be the primary authority path — that would reintroduce linguistic authority at the decision layer.

### 3.3 No ALLOW Without Proof

An `ALLOW` decision MUST reference all required proof objects. A decision that allows action without the required evidence is a policy violation, not a feature.

### 3.4 Regime Is Derived, Not Declared

The operational regime is computed from observable signals, not hand-labeled. If regime cannot be derived from recorded signals and policy thresholds, it is not a regime — it is an opinion.

### 3.5 Decisions Expire

Constraint decisions are temporally bounded. A decision made 10 minutes ago may not be valid now. Expired decisions MUST NOT authorize action.

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Constraint Decision
A deterministic control-law output indicating whether a requested action is allowed, denied, deferred, or requires re-verification.

### 5.2 Constraint Engine
The runtime component that evaluates claims, proofs, and policy to produce constraint decisions. The constraint engine is the decision authority in a PCAR runtime.

### 5.3 Policy Pack
A versioned, hashable collection of rules and thresholds consumed by the constraint engine. Policy packs are inputs, not outputs — they determine behavior but are not modified by the engine.

### 5.4 Regime
A derived runtime operating mode computed from observable signals and policy thresholds. Regimes affect decision stringency but do not override policy.

### 5.5 Rationale Code
A stable, machine-readable identifier explaining why a decision was made. Rationale codes are the primary explanation mechanism; human text is secondary.

---

## 6. Processing Model (PCAR-C)

### 6.1 Input

The constraint engine accepts:
- one or more Claim Envelopes (PCAR-A),
- associated Proof Objects (PCAR-B),
- the current Policy Pack,
- runtime state (regime signals, prior decisions, active constraints),
- action context (action type, target scope, requested by).

### 6.2 Output

The constraint engine produces:
- one Constraint Decision per evaluated action or claim,
- zero or more PCAR-C errors,
- updated regime state (if regime signals changed).

### 6.3 Determinism

The constraint engine MUST be a pure function of its inputs. Specifically:
- No network calls during evaluation.
- No model consultation.
- No random number generation.
- No dependency on wall-clock time other than for freshness comparison (using `observed_at` from proofs, not system clock).

If implementation-defined tie-breakers are necessary (e.g., between equally valid decisions), they MUST be deterministic and documented.

### 6.4 Evaluation Order

When multiple claims or actions are evaluated in a single batch:
- Evaluation order MUST be deterministic (e.g., by claim_id sort order).
- Later evaluations in the batch MAY depend on earlier decisions in the same batch.
- This sequential dependency MUST be documented in the batch result.

---

## 7. Constraint Decision Schema (Normative)

### 7.1 Required Fields

#### `decision_id` (string)
Unique identifier for this decision.

Requirements:
- MUST be unique within the current run/session scope.
- SHOULD be deterministically derivable from inputs for idempotency.

#### `subject_ref` (object)
What this decision is about.

Required members:
- `ref_type` (string) — `claim`, `action_request`, `proof_set`
- `ref_id` (string) — identifier of the subject

#### `decision` (enum)
The constraint engine's determination.

Required values:
- `ALLOW` — action may proceed. All required proofs are present, fresh, and sufficient.
- `DENY` — action is rejected. Policy or proof requirements not met.
- `DEFER` — action cannot be decided now. More information or human input needed.
- `REVERIFY` — prior proofs are stale or insufficient. Re-verification required before re-evaluation.
- `ESCALATE` — decision exceeds the constraint engine's authority. Human or higher-authority review required.

No other terminal decision values are permitted.

#### `required_proofs` (array)
List of proof requirements that were evaluated.

Each entry MUST include:
- `proof_type` (string) — expected proof type
- `proof_id` (string | null) — actual proof ID that satisfied this requirement, or null if unsatisfied
- `status` (string) — `satisfied`, `missing`, `stale`, `inconclusive`, `failed`

#### `policy_ref` (object)
Reference to the policy under which this decision was made.

Required members:
- `policy_id` (string)
- `policy_version` (string)
- `policy_hash` (string)

#### `rationale_codes` (array of strings)
Machine-readable codes explaining the decision. See Section 11.

#### `regime` (string)
The operational regime at the time of evaluation. See Section 9.

#### `issued_at` (timestamp)
When the decision was made. RFC 3339, UTC.

#### `expires_at` (timestamp)
When the decision expires. RFC 3339, UTC.

After expiry, the decision MUST NOT be used to authorize action. A new evaluation is required.

### 7.2 Optional Fields

#### `constraints` (array)
Active constraints applied to this decision. See Section 10.

#### `constraint_hash` (string)
Content hash of the constraint set evaluated. Enables decision reproducibility.

#### `state_bindings` (array)
State references at the time of evaluation. Same structure as PCAR-B state bindings.

#### `freshness_summary` (object)
Summary of proof freshness evaluation.

Members:
- `all_fresh` (boolean)
- `stale_proof_ids` (array of strings)
- `oldest_proof_age_seconds` (integer)

#### `metadata` (object)
Implementation-specific metadata. MUST NOT carry normative semantics absent from required fields.

#### `labels` (array of strings)
Implementation-defined tags.

#### `extensions` (object)
Reserved for implementation-specific fields.

---

## 8. Policy Pack Interface (Normative)

### 8.1 Policy Pack Requirements

A Policy Pack MUST be:
- **Versioned**: policy_id + policy_version, immutable once published.
- **Hashable**: deterministic content hash for receipt binding.
- **Loadable**: the constraint engine can parse and evaluate it without external state.
- **Referenceable**: receipts can cite the exact policy version used.

### 8.2 Policy Evaluation Inputs

Policy evaluation MUST accept:

| Input | Source | Required |
|-------|--------|----------|
| Action type | Claim envelope / action request | Yes |
| Target scope | Claim envelope / action request | Yes |
| Proof set | PCAR-B proof objects | Yes |
| Proof freshness status | Derived from proof `freshness` fields | Yes |
| Policy version | Policy Pack metadata | Yes |
| Regime | Derived from signals (Section 9) | Yes |
| Prior failure counters | Runtime state | No |
| Human override context | Override records | No |
| Constraint set | Active constraints (Section 10) | No |

### 8.3 Policy Evaluation Output

Policy evaluation MUST produce:
- A decision (`ALLOW`, `DENY`, `DEFER`, `REVERIFY`, `ESCALATE`)
- Rationale codes
- Required proof list with satisfaction status
- Applicable constraints

### 8.4 Policy Determinism

Given identical inputs, policy evaluation MUST produce identical outputs. Policy packs MUST NOT contain non-deterministic elements (random thresholds, time-of-day rules based on wall clock, etc.).

Time-based rules MUST use proof timestamps and freshness, not the evaluation-time clock.

---

## 9. Regime Derivation (Normative)

### 9.1 What Regime Is

A regime is a derived runtime operating mode that affects decision stringency. Regimes are computed from observable signals, not declared by humans or models.

### 9.2 Signal Vocabulary (Minimal)

PCAR-C implementations MUST track at least these signals:

| Signal | Description | Direction |
|--------|-------------|-----------|
| `freshness_fail_count` | Proofs that expired before use | Higher = worse |
| `contradiction_count` | Claims with contradicting proofs | Higher = worse |
| `proof_fail_rate` | Fraction of proofs with status FAIL | Higher = worse |
| `state_drift_events` | State bindings that changed under active proofs | Higher = worse |
| `reverify_loops` | Re-verification cycles without resolution | Higher = worse |
| `missing_binding_events` | Proofs without valid state bindings | Higher = worse |

Implementations MAY track additional signals. All signals MUST be derivable from receipted events — no signals from unreceipted observations.

### 9.3 Regime Labels

Regime labels are implementation-defined, but PCAR-C defines a minimal set:

| Regime | Semantics |
|--------|-----------|
| `NOMINAL` | All signals within normal bounds. Standard policy applies. |
| `DEGRADED` | Some signals elevated. Increased verification requirements. |
| `RESTRICTED` | Multiple signals elevated. Scope narrowing and additional proof requirements. |
| `LOCKED` | Critical signals exceeded. Minimal operations only. Human intervention required. |

### 9.4 Derivation Rules

Regime MUST be derived from signal thresholds defined in the Policy Pack.

Example policy structure:
```json
{
  "regime_thresholds": {
    "DEGRADED": {"proof_fail_rate": 0.1, "contradiction_count": 3},
    "RESTRICTED": {"proof_fail_rate": 0.3, "reverify_loops": 5},
    "LOCKED": {"proof_fail_rate": 0.5, "state_drift_events": 10}
  }
}
```

The highest triggered regime applies.

### 9.5 Regime Transition Rules

- Regime transitions MUST be reconstructable from recorded signals and policy thresholds.
- Regime transitions MUST be receipted (PCAR-D).
- Regime MUST NOT be manually overridden without a human override receipt.
- Downward transitions (e.g., LOCKED → RESTRICTED) SHOULD require sustained signal improvement, not a single good measurement (hysteresis).

### 9.6 Regime Effect on Decisions

Regime affects decision stringency:
- `NOMINAL`: standard proof requirements.
- `DEGRADED`: additional proof types may be required; shorter freshness windows.
- `RESTRICTED`: scope narrowing constraints applied; actions limited to essential operations.
- `LOCKED`: only human-authorized actions; automatic `ESCALATE` for all consequential requests.

The specific effect is policy-defined. PCAR-C defines the interface, not the content.

---

## 10. Constraint Vocabulary (Normative)

Constraints are conditions applied to allowed actions. An `ALLOW` decision may carry constraints that the actuator (PCAR-E) MUST enforce.

### 10.1 Core Constraints

| Constraint | Semantics |
|-----------|-----------|
| `read_only` | No write operations permitted |
| `no_network` | No outbound network operations |
| `scope_narrowed` | Action scope restricted to specified paths/targets |
| `require_human_override` | Human must explicitly approve before execution |
| `force_reverify` | All proofs must be re-verified before next action |
| `max_actions_n` | Maximum number of actions before re-evaluation |
| `deny_action_type` | Specific action type(s) blocked |
| `require_additional_proof` | Extra proof type required beyond baseline |
| `time_bounded` | Action must complete within specified duration |

### 10.2 Constraint Schema

Each constraint MUST include:
- `constraint_type` (string) — from vocabulary above or implementation-defined
- `parameters` (object) — constraint-specific parameters
- `source` (string) — what triggered this constraint (`policy`, `regime`, `human_override`)
- `expires_at` (timestamp, optional) — constraint expiry

### 10.3 Constraint Composition

Multiple constraints MAY apply to a single decision. When they do:
- All constraints MUST be satisfied (conjunction, not disjunction).
- Contradictory constraints (e.g., `read_only` + an action requiring write) MUST result in `DENY`.
- Constraint evaluation is deterministic and order-independent.

---

## 11. Rationale Codes (Normative)

Rationale codes are the primary explanation mechanism. They are stable, machine-readable, and append-only (new codes may be added; existing codes MUST NOT be renamed or removed).

### 11.1 Core Rationale Codes

#### Allow Rationale
- `proofs_complete` — all required proofs present and passing
- `freshness_valid` — all proofs within freshness window
- `scope_within_bounds` — action scope within allowed bounds
- `regime_permits` — current regime allows this action type
- `human_override_active` — human override authorizes this action

#### Deny Rationale
- `proof_missing` — required proof not present
- `proof_failed` — required proof has status FAIL
- `proof_inconclusive` — required proof has status INCONCLUSIVE (treated as deny by policy)
- `freshness_expired` — proof exceeded freshness window
- `scope_violation` — action scope exceeds allowed bounds
- `regime_restricts` — current regime blocks this action type
- `policy_denies` — explicit policy denial
- `constraint_violated` — active constraint incompatible with action

#### Defer/Reverify Rationale
- `proof_pending` — verification in progress, not yet complete
- `proof_stale` — proof freshness expired, re-verification needed
- `state_drifted` — state binding changed, re-verification needed
- `human_input_required` — decision requires human input
- `additional_proof_required` — policy requires proof types not yet provided

#### Escalate Rationale
- `authority_exceeded` — decision exceeds constraint engine's authority
- `regime_locked` — system in LOCKED regime, human required
- `policy_ambiguous` — policy does not clearly resolve this case
- `repeated_reverify` — multiple re-verification cycles without resolution

---

## 12. Decision Expiry (Normative)

### 12.1 All Decisions Expire

Every constraint decision MUST include an `expires_at` timestamp. There are no eternal decisions.

### 12.2 Default Expiry

If the policy does not specify a decision lifetime, the default SHOULD be short (e.g., 5 minutes). Short defaults are safer than long ones.

### 12.3 Expired Decision Handling

An expired decision:
- MUST NOT be used to authorize action (PCAR-E MUST reject it).
- MAY be cited as context for a new evaluation.
- SHOULD trigger re-evaluation if the action is still pending.

### 12.4 Expiry Is Not Revocation

Expiry is temporal. Revocation is explicit. PCAR-C v0.1 does not define revocation semantics. If a decision needs to be invalidated before expiry, the implementation SHOULD issue a new `DENY` decision referencing the original.

---

## 13. Error Model (Normative)

### 13.1 Error Object Shape

Each error MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `decision_id` (if applicable)
- `policy_ref` (if applicable)

### 13.2 Required Error Codes

#### Policy
- `PCAR_C_POLICY_LOAD_FAILURE` — could not load or parse policy pack
- `PCAR_C_POLICY_VERSION_MISMATCH` — policy version incompatible with engine
- `PCAR_C_POLICY_HASH_MISMATCH` — policy content does not match declared hash

#### Evaluation
- `PCAR_C_NONDETERMINISTIC_EVAL` — evaluation produced different results on identical inputs (implementation bug)
- `PCAR_C_MISSING_REQUIRED_PROOF` — proof required by policy but not provided
- `PCAR_C_UNKNOWN_ACTION_TYPE` — action type not recognized by policy
- `PCAR_C_SCOPE_POLICY_MISMATCH` — action scope not covered by any policy rule

#### Regime
- `PCAR_C_INVALID_REGIME_TRANSITION` — signal values do not support the attempted regime change
- `PCAR_C_REGIME_SIGNAL_MISSING` — required signal not available for regime derivation

#### Decision
- `PCAR_C_DECISION_EXPIRED` — attempt to use an expired decision
- `PCAR_C_CONSTRAINT_CONTRADICTION` — active constraints are mutually exclusive

### 13.3 Error Handling Rules

- Evaluation errors MUST NOT produce an `ALLOW` decision. If evaluation fails, the default MUST be `DENY` or `DEFER`.
- Policy load failures MUST be treated as `LOCKED` regime until resolved.
- Errors MUST be receipted (PCAR-D) if they affect consequential decisions.

---

## 14. Canonicalization (PCAR-C Profile)

### 14.1 Decision Normalization

Constraint decisions MUST be normalized for receipt hashing (PCAR-D) using the canonical JSON profile defined in PCAR-D Section 10.

### 14.2 Constraint Hash

The `constraint_hash` is computed from the canonical serialization of the constraint set:
```
constraint_hash = sha256(canonical_json(sorted_constraints))
```

This enables verification that the same constraint set was evaluated across different decisions.

---

## 15. Security Considerations (PCAR-C Specific)

### 15.1 Policy Injection

If an attacker can modify the policy pack, they control decision outcomes. Mitigations:
- Policy packs MUST be versioned and hashed.
- Policy hash is recorded in every decision receipt.
- Policy changes SHOULD be gated by a separate authority (not the governed agent).

### 15.2 Signal Manipulation

If regime signals can be manipulated, the operational regime becomes unreliable. Mitigations:
- Signals MUST be derived from receipted events (no unreceipted observations).
- Signal computation MUST be deterministic and auditable.
- Regime transitions are receipted.

### 15.3 Decision Replay

Stale decisions may be replayed to authorize actions on changed state. Mitigations:
- All decisions expire (Section 12).
- Actuators (PCAR-E) MUST verify decision freshness.
- State bindings in decisions enable state-drift detection.

### 15.4 Privilege Escalation via Regime

An attacker may try to force a favorable regime (e.g., trigger NOMINAL when signals warrant RESTRICTED). Mitigations:
- Regime is derived from signals, not declared.
- Regime derivation is deterministic given signals and thresholds.
- Downward transitions require hysteresis (Section 9.5).

---

## 16. Privacy Considerations (PCAR-C Specific)

Constraint decisions may reveal information about policy rules, regime thresholds, and system behavior. Implementations SHOULD support:

- decision redaction for external export,
- policy pack access control,
- signal aggregation to prevent inference of individual events.

---

## 17. Conformance

An implementation is **PCAR-C conformant** if it:

1. Produces Constraint Decisions matching Section 7.
2. Implements the policy pack interface per Section 8.
3. Derives regime from signals per Section 9.
4. Enforces determinism per Section 6.3.
5. Enforces decision expiry per Section 12.
6. Does not produce `ALLOW` without required proofs.
7. Expresses rationale as machine-readable codes per Section 11.
8. Emits machine-readable errors per Section 13.
9. Defaults to `DENY` or `DEFER` on evaluation failure.

---

## 18. Informative Examples

### 18.1 Example: ALLOW Decision (All Proofs Satisfied)

```json
{
  "decision_id": "d-001",
  "subject_ref": {"ref_type": "action_request", "ref_id": "c-010"},
  "decision": "ALLOW",
  "required_proofs": [
    {"proof_type": "core.TEST_RESULT", "proof_id": "p-001", "status": "satisfied"},
    {"proof_type": "core.STATE_SNAPSHOT", "proof_id": "p-003", "status": "satisfied"}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "rationale_codes": ["proofs_complete", "freshness_valid", "scope_within_bounds"],
  "regime": "NOMINAL",
  "issued_at": "2026-02-23T15:00:00Z",
  "expires_at": "2026-02-23T15:05:00Z",
  "constraints": [
    {"constraint_type": "scope_narrowed", "parameters": {"allowed_paths": ["src/"]}, "source": "policy"}
  ]
}
```

### 18.2 Example: DENY Decision (Proof Failed)

```json
{
  "decision_id": "d-002",
  "subject_ref": {"ref_type": "action_request", "ref_id": "c-011"},
  "decision": "DENY",
  "required_proofs": [
    {"proof_type": "core.TEST_RESULT", "proof_id": "p-004", "status": "failed"}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "rationale_codes": ["proof_failed"],
  "regime": "NOMINAL",
  "issued_at": "2026-02-23T15:01:00Z",
  "expires_at": "2026-02-23T15:06:00Z"
}
```

### 18.3 Example: REVERIFY Decision (Stale Proof)

```json
{
  "decision_id": "d-003",
  "subject_ref": {"ref_type": "action_request", "ref_id": "c-012"},
  "decision": "REVERIFY",
  "required_proofs": [
    {"proof_type": "core.STATE_SNAPSHOT", "proof_id": "p-005", "status": "stale"}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "rationale_codes": ["proof_stale", "state_drifted"],
  "regime": "DEGRADED",
  "freshness_summary": {
    "all_fresh": false,
    "stale_proof_ids": ["p-005"],
    "oldest_proof_age_seconds": 1200
  },
  "issued_at": "2026-02-23T15:02:00Z",
  "expires_at": "2026-02-23T15:07:00Z"
}
```

---

## 19. Open Questions

- Should the regime signal vocabulary be standardized, or remain implementation-defined with a recommended minimum?
- Should hysteresis parameters for regime transitions be specified, or left to policy?
- How should the constraint engine handle policy version transitions mid-session?
- Should there be a `CONDITIONAL_ALLOW` decision type (ALLOW with mandatory post-execution verification)?
- What is the relationship between PCAR-C regime and the existing Agent Governor regime detection (`src/governor/regime.py`)?

---

## 20. References (Informative)

- PCAR-000: Proof-Carrying Agent Runtime
- PCAR-A: Typed Claim Envelope
- PCAR-B: Proof Objects and Verifier Contract
- RFC 2119
- RFC 8174
