---
audience: publication-candidate
status: active
---

# Governor Standing Classes and Receipt Roles

Status: doctrine
Audience: Governor / Night Shift / NQ implementers
Purpose: define the constitutional boundary between advisory reasoning and binding authority
Position in chain: 2 of 3
Previous: [advisory_vs_constitutional_power.md](advisory_vs_constitutional_power.md) — posture and invariants
Next: [validator_contract.md](validator_contract.md) — constitutional checks
Open questions: [`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md`](../../specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md)

## 1. Core rule

**Reasoning is advisory power. Governor is constitutional power.**

Advisory artifacts may inform a decision, but they must not silently acquire binding standing. The system must preserve a visible transition from:

- observation
- interpretation
- recommendation
- authorization
- execution

Every transition that changes force, standing, or consequence must be represented as an explicit receipt with typed parentage.

## 2. Design goals

This document exists to ensure that:

- evidence can accuse without authorizing
- reasoning can propose without binding
- policy can bind without freelancing
- execution can act only under explicit authority
- ontology drift is treated as policy drift
- uncertainty at the authority boundary fails closed

Compressed design line:

**Make illegible discretion harder, not smarter.**

## 3. Standing classes

Standing class describes what kind of force an artifact may carry. It is not a confidence score and it is not an importance ranking. It is a limit on what the artifact is allowed to do.

### 3.1 `OBSERVE`

May assert that something was seen, measured, captured, or directly derived from a bounded observational process.

Examples:
- a persisted NQ finding
- a metrics snapshot
- a log excerpt
- a WAL growth detector result
- a direct state capture from a runtime

`OBSERVE` standing may support later interpretation, but it cannot explain, permit, or execute.

### 3.2 `INTERPRET`

May assert that a bounded inference, diagnosis, or hypothesis has been drawn from observation.

Examples:
- likely cause analysis
- continuity-risk interpretation
- regime hint explanation
- ambiguity statement
- competing hypothesis ranking

`INTERPRET` standing may not authorize actions.

### 3.3 `RECOMMEND`

May propose one or more bounded actions, plans, or routes for consideration under policy.

Examples:
- quarantine host
- run repair sequence B
- restore from snapshot N
- escalate to operator
- reject restore as continuity-breaking

`RECOMMEND` standing may not bind the system. It may only place candidate force on the record.

### 3.4 `AUTHORIZE`

May bind the system to a permit / deny / escalate / require-human verdict under a declared policy artifact.

This standing belongs to Governor.

`AUTHORIZE` is where admissibility, scope, standing, continuity doctrine, and policy ontology must be checked. Uncertainty here fails closed.

### 3.5 `EXECUTE`

May carry out a previously authorized action.

This standing belongs to the tool/runtime layer operating under an `AUTHORIZE` parent.

`EXECUTE` may not self-authorize, expand scope, or infer missing authority.

### 3.6 `POLICY_DECLARE`

May define or supersede the policy artifacts against which `AUTHORIZE` receipts are evaluated.

Policy artifacts are governed substrate. They must themselves carry receipt lineage (see §8.3).

## 4. Receipt roles

Receipt role describes what kind of statement the receipt makes. Standing class and receipt role are related but not identical. In the normal case they align.

Canonical roles:

- `observation`
- `interpretation`
- `recommendation`
- `authorization`
- `action`
- `policy_declaration`
- `validation` (meta-governance; see [validator_contract.md](validator_contract.md) §16)

### 4.1 `observation`

Statement form: **X was observed.**

Normal standing class: `OBSERVE`

### 4.2 `interpretation`

Statement form: **Y is inferred from X.**

Normal standing class: `INTERPRET`

### 4.3 `recommendation`

Statement form: **Z is proposed because of Y.**

Normal standing class: `RECOMMEND`

### 4.4 `authorization`

Statement form: **Z is permitted / denied / escalated under policy P.**

Normal standing class: `AUTHORIZE`

### 4.5 `action`

Statement form: **Z′ was executed.**

Normal standing class: `EXECUTE`

### 4.6 `policy_declaration`

Statement form: **Policy P at version V is declared / supersedes prior policy.**

Normal standing class: `POLICY_DECLARE`

## 5. Parentage contract

Every consequential receipt must carry explicit parent references.

### 5.1 Normal chain

- `observation` -> root or prior evidence chain
- `interpretation` -> one or more `observation` receipts
- `recommendation` -> one or more `interpretation` and/or `observation` receipts
- `authorization` -> one `recommendation` receipt, plus policy artifact reference
- `action` -> one `authorization` receipt

### 5.2 Allowed compression

Compression should be rare and explicit.

Allowed:
- a trivial `recommendation` may cite `observation` directly if no interpretive step was needed
- an `authorization` may cite multiple parent recommendations if the policy decision truly adjudicates among them

Not allowed:
- `action` without an `authorization` parent
- treating an `interpretation` receipt as if it were an `authorization`
- treating `observation` as sufficient authority for action
- silently synthesizing missing parents inside Governor

See [validator_contract.md](validator_contract.md) §5.3 for the explicit compression exception path and its anomaly-counting requirements.

### 5.3 Standing escalation rule

No artifact may gain a higher standing class by implication.

Examples:
- `INTERPRET` does not become `RECOMMEND` because the recommendation seems obvious
- `RECOMMEND` does not become `AUTHORIZE` because the policy would probably allow it
- `AUTHORIZE` does not become `EXECUTE` because the runtime can reach the tool

Standing changes must be represented by a new receipt.

## 6. Required common fields

Every receipt should carry at least:

- `receipt_id`
- `receipt_role`
- `standing_class`
- `subject`
- `created_at`
- `producer`
- `parent_receipts` (list of `{id, content_hash}`)
- `evidence_refs`
- `uncertainty`
- `gaps`
- `gaps_resolved` (list of `{gap_id, resolution_basis, evidence_refs, resolver, resolution_timestamp}`)
- `policy_artifact_id` (nullable except where required)
- `policy_artifact_hash` (nullable except where required)
- `ontology_version`
- `content_hash`

Notes:
- `uncertainty` is descriptive, not permission-granting
- `gaps` from parent receipts must either survive into child `gaps` or be explicitly addressed in `gaps_resolved` with cited evidence
- `ontology_version` is mandatory even when the role does not directly enforce policy, because downstream interpretation depends on the vocabulary in force
- `parent_receipts` binds by content hash, not ID alone — this gives Merkle-style tamper detection without a separate chain structure

## 7. Role-specific required fields

### 7.1 Observation receipt

Required extras:
- `source_type`
- `collection_method`
- `authenticity_basis`
- `observed_at`
- `admissibility_notes`

### 7.2 Interpretation receipt

Required extras:
- `inference_type`
- `hypotheses`
- `selected_hypothesis`
- `confidence_basis`
- `unresolved_ambiguities`
- `model_or_method`

### 7.3 Recommendation receipt

Required extras:
- `proposed_actions`
- `intended_effect`
- `risk_class`
- `rollback_notes`
- `continuity_implications`
- `requires_operator_confirmation`

### 7.4 Authorization receipt

Required extras:
- `policy_decision`
- `verdict` (`permit` | `deny` | `escalate` | `require_human`)
- `standing_check` (structured: `{result, basis}`)
- `admissibility_check` (structured: `{result, basis}`)
- `scope_check` (structured: `{result, basis}`)
- `budget_check` (structured: `{result, basis}`)
- `denial_reason` (required when verdict is deny)
- `escalation_reason` (required when verdict is escalate or require_human)

Check results must be structured so that denial reasoning is legible — boolean-only or ID-only check fields are insufficient.

### 7.5 Action receipt

Required extras:
- `tool_name`
- `tool_invocation`
- `executor_identity`
- `execution_result`
- `state_delta`
- `deviations_from_authorized_plan`

### 7.6 Policy declaration receipt

Required extras:
- `policy_artifact_id`
- `policy_artifact_hash`
- `ontology_version`
- `effective_scope`
- `ratifier`
- `supersedes` (nullable — prior policy declaration reference)
- `rationale`

## 8. Fail-closed rules

### 8.1 Boundary uncertainty

At the authority boundary, unresolved uncertainty requires one of:

- `deny`
- `escalate`
- `require_human`

It must not trigger creative reinterpretation.

### 8.2 Missing parentage

If required parent receipts are missing, corrupted, or unverifiable:

- deny execution
- preserve the gap in the receipt trail
- do not reconstruct force from prose or memory

### 8.3 Missing ontology version

If a receipt omits `ontology_version`, downstream consumers must treat it as non-binding.

### 8.4 Policy hash mismatch

If a receipt cites a policy artifact whose hash does not resolve, the receipt may remain observable but not binding.

## 9. Ontology drift is policy drift

Risk classes, action classes, admissibility categories, standing vocabularies, and continuity doctrines are not mere configuration.

Any change to:
- class names
- class membership rules
- allowed transitions
- required checks
- role meanings

must be treated as a policy change with its own versioning and receipt lineage.

Minimum rule:

- ontology changes must bump `ontology_version`
- policy changes must produce a policy declaration receipt
- old receipts remain interpretable under their original ontology version

## 10. Continuity-specific rule

Continuity may not be inferred by convenience.

Any recommendation or authorization that claims continuity preservation should make the basis legible against the continuity doctrine in force. Missing evidence, broken provenance, ambiguous identity, or unwarranted operator confidence cannot be smoothed over by narrative optimism.

Required continuity basis fields when continuity is claimed:
- `identity_basis`
- `provenance_basis`
- `evidence_basis`
- `operator_confidence_basis`

## 11. Minimal enums

These are the closed sets worth checking in first.

### 11.1 Standing class enum

```text
OBSERVE
INTERPRET
RECOMMEND
AUTHORIZE
EXECUTE
POLICY_DECLARE
```

### 11.2 Receipt role enum

```text
observation
interpretation
recommendation
authorization
action
policy_declaration
validation
```

### 11.3 Authorization verdict enum

```text
permit
deny
escalate
require_human
```

## 12. Example chain

```json
{
  "receipt_id": "rcpt_obs_001",
  "receipt_role": "observation",
  "standing_class": "OBSERVE",
  "subject": "nq:wal_bloat:host123",
  "parent_receipts": [],
  "producer": "nq",
  "ontology_version": "gov-ontology-v1",
  "uncertainty": "low",
  "gaps": [],
  "source_type": "metric_window",
  "collection_method": "sqlite_generation_scan",
  "authenticity_basis": "direct_capture"
}
```

```json
{
  "receipt_id": "rcpt_int_001",
  "receipt_role": "interpretation",
  "standing_class": "INTERPRET",
  "subject": "nq:wal_bloat:host123",
  "parent_receipts": [{"id": "rcpt_obs_001", "content_hash": "sha256:..."}],
  "producer": "night_shift",
  "ontology_version": "gov-ontology-v1",
  "selected_hypothesis": "checkpoint starvation likely",
  "unresolved_ambiguities": ["reader pin not yet confirmed"]
}
```

```json
{
  "receipt_id": "rcpt_rec_001",
  "receipt_role": "recommendation",
  "standing_class": "RECOMMEND",
  "subject": "host123",
  "parent_receipts": [{"id": "rcpt_int_001", "content_hash": "sha256:..."}],
  "producer": "night_shift",
  "ontology_version": "gov-ontology-v1",
  "proposed_actions": ["collect reader list", "delay checkpoint reset", "escalate if wal continues for 3 gens"],
  "risk_class": "bounded_diagnostic",
  "requires_operator_confirmation": false
}
```

```json
{
  "receipt_id": "rcpt_auth_001",
  "receipt_role": "authorization",
  "standing_class": "AUTHORIZE",
  "subject": "host123",
  "parent_receipts": [{"id": "rcpt_rec_001", "content_hash": "sha256:..."}],
  "producer": "governor",
  "ontology_version": "gov-ontology-v1",
  "policy_artifact_id": "policy.runtime.diagnostics",
  "policy_artifact_hash": "sha256:...",
  "verdict": "permit",
  "standing_check": {"result": "pass", "basis": "night_shift has recommendatory standing for diagnostic scope"},
  "admissibility_check": {"result": "pass", "basis": "evidence chain complete, no gaps"},
  "scope_check": {"result": "pass", "basis": "within runtime.diagnostics scope"},
  "budget_check": {"result": "pass", "basis": "under per-session budget"}
}
```

```json
{
  "receipt_id": "rcpt_act_001",
  "receipt_role": "action",
  "standing_class": "EXECUTE",
  "subject": "host123",
  "parent_receipts": [{"id": "rcpt_auth_001", "content_hash": "sha256:..."}],
  "producer": "runtime",
  "ontology_version": "gov-ontology-v1",
  "tool_name": "bash",
  "executor_identity": "night-shift-runner",
  "execution_result": "success",
  "deviations_from_authorized_plan": []
}
```

## 13. Validation rules worth enforcing first

First-pass validator rules (see [validator_contract.md](validator_contract.md) for the full contract):

1. `receipt_role` must be in the closed enum.
2. `standing_class` must be in the closed enum.
3. `authorization` requires `policy_artifact_id`, `policy_artifact_hash`, and a valid `verdict`.
4. `action` requires at least one parent `authorization` receipt.
5. standing may only move upward through a new receipt, never by field mutation.
6. missing `ontology_version` makes a receipt non-binding.
7. unknown parent receipts make downstream force invalid.
8. parent gaps must either survive into child `gaps` or be cited in `gaps_resolved` with evidence.
9. parent references must be content-bound (id + content_hash); hash mismatches invalidate the child.

## 14. Suggested follow-on artifacts

After this document and [validator_contract.md](validator_contract.md), the next useful objects are:

1. a machine-readable schema for the common receipt envelope
2. enum definitions in the Governor codebase
3. a parentage validator
4. a policy artifact schema that includes ontology version/hash
5. a continuity-claim extension for receipts that assert continuity preservation
6. integration with the existing `receipt_kernel` event ledger (so standing-class chains emit through the hash-chained store rather than building a parallel one — see `docs/RECEIPT_KERNEL_CONTRACT.md`)

## 15. Compressed doctrine lines

- Reasoning is advisory power. Governor is constitutional power.
- Make illegible discretion harder, not smarter.
- Deny on uncertainty at the authority boundary.
- Ontology drift is policy drift.
- Continuity cannot be inferred by convenience.
- The prompt is not the policy.
