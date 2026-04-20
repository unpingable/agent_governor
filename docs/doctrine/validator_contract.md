---
audience: publication-candidate
status: active
---

# Governor Validator Contract

Status: doctrine
Audience: Governor implementers, anyone writing receipt-chain validators
Purpose: define the minimum semantic checks required for receipt chains to remain constitutional rather than merely well-formed.
Position in chain: 3 of 3
Previous: [standing_and_receipts.md](standing_and_receipts.md) — formal taxonomy
Open questions: [`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md`](../../specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md) — must ratify before validator implementation

## 1. Scope

This contract defines the validator behavior for:

- receipt role compatibility
- standing-class compatibility
- parentage requirements
- subject-lineage coherence
- gap propagation and documented resolution
- policy / ontology binding requirements
- chain integrity requirements
- validator versioning and validation receipts
- failure behavior

This contract is intentionally prior to schema design. Schema fields exist to support these checks.

## 2. Core rule

A receipt chain is valid only if each step preserves the distinction between:

- **observation**
- **interpretation**
- **recommendation**
- **authorization**
- **execution**
- **policy declaration**

The validator exists to prevent silent escalation from lower standing to higher standing.

## 3. Closed standing classes

The validator recognizes exactly these standing classes:

- `OBSERVE`
- `INTERPRET`
- `RECOMMEND`
- `AUTHORIZE`
- `EXECUTE`
- `POLICY_DECLARE`

No `UNKNOWN`, `OTHER`, or unregistered extension value is valid.

## 4. Closed receipt roles

Minimum recognized roles:

- `observation`
- `interpretation`
- `recommendation`
- `authorization`
- `action`
- `policy_declaration`
- `validation`

A receipt role must map to exactly one standing class, except `validation`, which is meta-governance and must not be used as an authority parent for action-bearing receipts.

Default mapping:

- `observation -> OBSERVE`
- `interpretation -> INTERPRET`
- `recommendation -> RECOMMEND`
- `authorization -> AUTHORIZE`
- `action -> EXECUTE`
- `policy_declaration -> POLICY_DECLARE`

Any deviation from this mapping is invalid.

## 5. Parentage contract

### 5.1 Required parentage by role

- `observation`: may have zero or more parents
- `interpretation`: must have at least one parent with standing `OBSERVE`
- `recommendation`: must have at least one parent with standing `INTERPRET`
- `authorization`: must have at least one parent with standing `RECOMMEND`
- `action`: must have at least one parent with standing `AUTHORIZE`
- `policy_declaration`: may have zero or more parents; if it supersedes prior policy, the superseded policy declaration must be referenced
- `validation`: must have at least one parent; validation receipts may reference receipt-chain roots, policy declarations, and prior validation receipts, but may not serve as sole authority parents for `authorization` or `action`

Additional parents of other roles are allowed as supporting references, but they do not substitute for the required immediate lower-standing parent.

### 5.2 Subject-lineage coherence

A child receipt must derive its subject from at least one parent subject or explicitly declare a valid subject transformation.

At minimum, the validator must require one of:

- exact subject match with at least one parent, or
- `subject_derivation` with basis and parent reference

A recommendation about subject A must not satisfy parentage solely by citing an interpretation about unrelated subject B.

### 5.3 Allowed compression

The validator may permit rare compressed paths only when they are explicit and tagged as exceptions.

Allowed exceptional compression:

- `OBSERVE -> AUTHORIZE`

This path is valid only if **all** of the following are present:

- `exception_class`
- `exception_reason`
- `operator_approval` or equivalent explicit constitutional standing
- `compression_acknowledged: true`
- a policy artifact that explicitly allows this compression

All compressed authorizations must be emitted as anomaly events and counted by `exception_class`.

No other compressed transition is valid in first pass.

### 5.4 Forbidden parentage

The validator must reject:

- `AUTHORIZE` consuming only `OBSERVE` without compression exception
- `AUTHORIZE` consuming only `INTERPRET`
- `ACTION` consuming only `RECOMMEND` or lower
- `RECOMMEND` consuming only `OBSERVE`
- any child whose parents do not include at least one receipt from the required immediate lower-standing stage, unless an explicit compression rule exists

Higher-standing or same-standing parents may appear as supporting references, but cannot substitute for the required immediate lower-standing parent.

## 6. Parent references must be content-bound

Parent references must not be ID-only pointers.

Each parent reference must include at least:

- `id`
- `content_hash`

The validator must verify that:

- the referenced parent exists
- the parent canonical content hashes to the declared `content_hash`
- the referenced parent role and standing match the expected transition

If any parent hash does not match, the child is invalid.

## 7. Gap survival and resolution

### 7.1 Rule

Gaps in parent receipts must survive downstream unless explicitly resolved.

### 7.2 Valid child behavior

For each parent gap, the child must do exactly one of:

- copy it into child `gaps`, or
- cite it in `gaps_resolved`

### 7.3 Requirements for `gaps_resolved`

Each resolved gap entry must include:

- `gap_id`
- `resolution_basis`
- `evidence_refs`
- `resolver`
- `resolution_timestamp`
- `resolution_parent_refs` (if the resolution depends on newly introduced receipts)

The validator must reject a child that omits a parent gap from both `gaps` and `gaps_resolved`.

### 7.4 No narrative paving

A gap is not resolved merely because a downstream receipt no longer mentions it. Resolution requires cited evidence.

## 8. Policy and ontology binding

### 8.1 Binding receipts

Any receipt with standing `AUTHORIZE` or `EXECUTE` is non-binding unless it includes:

- `policy_artifact_id`
- `policy_artifact_hash`
- `ontology_version`

### 8.2 Policy registry verification

The validator must verify that:

- the referenced policy artifact exists
- its content hash matches
- the referenced ontology version is registered under that policy artifact
- the ontology version is effective for the receipt time and scope

A syntactically valid but unregistered ontology version is invalid.

### 8.3 Policy declaration lineage

Policy artifacts must themselves be represented by `policy_declaration` receipts or equivalent registered artifacts with lineage.

At minimum, a `policy_declaration` must include:

- `policy_artifact_id`
- `policy_artifact_hash`
- `ontology_version`
- `effective_scope`
- `ratifier`
- `supersedes` (if applicable)

A binding receipt that references a policy artifact lacking registered declaration lineage is invalid.

## 9. Structured check results

Authorization receipts must provide structured results for:

- `standing_check`
- `admissibility_check`
- `scope_check`
- `budget_check`

Each check result must include:

- `result`: `pass | fail | escalate`
- `basis`: brief reason

ID-only or boolean-only check fields are insufficient.

## 10. Continuity-specific requirement

If a receipt asserts continuity-bearing action, the validator must require presence of explicit continuity basis fields:

- `identity_basis`
- `provenance_basis`
- `evidence_basis`
- `operator_confidence_basis`

If continuity is claimed without these fields, the receipt is invalid.

## 11. Violation classes

### 11.1 Structural violations

Examples:

- missing required parent
- missing required field
- unknown role
- unknown standing class
- invalid role-standing mapping
- invalid immediate parent type
- missing subject derivation when subject differs from all required parents

### 11.2 Semantic violations

Examples:

- ontology version not registered
- policy artifact hash mismatch
- parent gap silently dropped
- missing continuity basis
- missing structured check result
- binding receipt missing policy fields
- unregistered validator ruleset or validator version

### 11.3 Chain violations

Examples:

- content hash mismatch
- cycle in parent graph
- orphan parent reference
- superseded policy used outside allowed window
- forged or substituted parentage

## 12. Failure behavior

Validator outcomes:

- `VALID`
- `INVALID_STRUCTURAL`
- `INVALID_SEMANTIC`
- `INVALID_CHAIN`
- `VALID_WITH_EXCEPTION`

Rules:

- any structural violation -> invalid
- any semantic violation on binding receipt -> invalid
- any chain violation -> invalid
- compressed authorization path with complete exception evidence -> valid with exception

The validator must fail closed for `AUTHORIZE` and `EXECUTE`.

## 13. Telemetry and scar production

The validator must emit telemetry for at least:

- compressed authorization count
- compressed authorization count by `exception_class`
- denied binding receipts by cause
- gap resolution count
- gap drop attempts
- policy registry mismatches
- chain tamper detections
- subject-lineage violations

Exception paths should be rare enough to be operationally noticeable.

## 14. Minimal decision lattice

Default allowed lattice:

- `OBSERVE -> INTERPRET`
- `INTERPRET -> RECOMMEND`
- `RECOMMEND -> AUTHORIZE`
- `AUTHORIZE -> EXECUTE`
- `POLICY_DECLARE -> AUTHORIZE` (as governing reference, not immediate action parent)

Everything else is invalid unless explicitly registered as a compression exception.

## 15. First-pass implementation priority

Implementation order:

1. parentage / transition validator
2. policy registry verification
3. gap survival / resolution checks
4. chain integrity checks
5. schema hardening
6. enum closure enforcement

Reason: the validator is the constitutional wall. Types and envelopes are subordinate.

## 16. Validator versioning and validation receipts

The validator itself is constitutional infrastructure and must not be an ungoverned root.

### 16.1 Validator identity

Every validator run must record at least:

- `validator_id`
- `validator_version`
- `ruleset_hash`
- `policy_registry_hash`
- `validated_at`
- `validation_outcome`

### 16.2 Validation receipts

A validator run must emit a `validation` receipt that cites:

- the receipt chain root(s) or target receipt(s)
- validator identity fields
- outcome
- violation list or exception list

Validation receipts are evidence about constitutional checking. They do not themselves authorize action.

### 16.3 Validator rule changes

Changes to validator rules, validator versions with semantic effect, or registry interpretation behavior must produce policy declaration lineage or equivalent governed change records.

Historical chains must not be silently reinterpreted under new validator semantics without a new validation receipt.

## 17. Open integration questions

These are not deviations from the contract — they are decisions to make before the first validator lands.

### 17.1 Composition with `receipt_kernel`

`libs/receipt_kernel` already provides an append-only hash-chained event ledger with six constitutional invariants (ledger.chain_valid, receipt.completeness, evaluation.completeness, finalization.completeness, run.single_finalize, run.stage_required_path) and a stage graph with hard-fail transitions.

The standing-class lattice in this contract is the higher-level constitutional version of the same shape. Before implementing, decide:

- do standing-class chains emit **through** the receipt_kernel ledger (so `ledger.chain_valid` and `receipt.completeness` apply uniformly), or
- do they live in a separate store that cites receipt_kernel events as evidence?

The former is preferred — one hash chain per session, one set of chain-integrity invariants, one audit surface.

### 17.2 `subject_derivation` must not become a side channel

§5.2 permits `subject_derivation` with `basis` and `parent reference`. If `basis` is free text, Governor is doing interpretation through the back door.

First-pass rule: constrain subject transformations to a closed enum — e.g. `same_subject`, `instance_of`, `aggregation_of`, `scope_narrowing`. Additions require policy declaration lineage (same rule as ontology drift).

### 17.3 Exception-class registry

§5.3 requires compressed paths to carry an `exception_class`. That class set is itself an ontology and is subject to §8 and §9 rules — additions must bump `ontology_version` and produce a `policy_declaration`. This is the same anti-drift move applied to the exception space itself.

## 18. Compressed doctrine lines

- The prompt is not the policy.
- Make illegible discretion harder, not smarter.
- Deny on uncertainty at the authority boundary.
- Ontology drift is policy drift.
- Gaps survive until resolved with evidence.
- 3am always votes for monarchy.
