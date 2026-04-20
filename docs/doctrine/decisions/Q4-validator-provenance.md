---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator_integration.q4
ontology_version: gov-doctrine-v1
supersedes: null
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-19T18:05:18Z
---

# Q4 Ratification Candidate — Validator Provenance

## Selection

**Option A.** Every validator version is a `policy_declaration`. Validator rules *are* policy. Bumping the validator version requires a ratified `policy_declaration` receipt with `supersedes` referencing the prior version. Bug fixes and semantic changes are not distinguished — both are policy changes.

Every validator run emits a `validation` receipt carrying full provenance. Historical chains are not silently re-validated under new rules; new rules produce new validation receipts, the prior ones remain immutable.

## Source

`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md` §Q4.

## Basis

This is a doctrine-level question, not a code-level one. The falsification pass for Q1 confirmed kernel composition; Q4 picks the governance rule for the validator itself. The argument for A is structural:

- The validator is constitutional infrastructure. Without governed change records, it becomes the new ungoverned root the rest of the doctrine just eliminated (`validator_contract.md` §16, `advisory_vs_constitutional_power.md` Invariant 3).
- Option B (committer judgment for "bug vs. semantic") is exactly the kind of illegible discretion the validator exists to prevent. The doctrine's failure mode "Just a little interpretation" applies to its own change process.
- Option C (no governance) is the explicit failure mode the doctrine names.

By inheritance from Q1: validation receipts emit through `receipt_kernel`, sharing the same hash chain and parent-binding semantics as other standing-class receipts.

## What this ratifies

- Option A: validator versions are policy_declarations; rule changes require ratified declaration lineage.
- Every validator run emits a `validation` receipt with the mandatory field set below.
- Validation receipts are point-in-time and immutable. Re-validation under a new validator version produces a *new* validation receipt, never mutates a prior one.
- `validation` receipts inherit from Q1: they ride the receipt_kernel ledger, content-addressed, parent-bound by hash.
- Validator startup must verify `ruleset_hash` matches the rules actually loaded. Mismatch → fail-closed, validator refuses to run.

## Mandatory fields on every `validation` receipt (frozen)

The validator implementation must populate all of these on every emission:

- `validator_id` — stable identifier for the validator implementation
- `validator_version` — semver, not a git sha (sha goes in `ruleset_hash`)
- `ruleset_hash` — content hash of the rules actually applied
- `policy_registry_hash` — snapshot of the registry at validation time
- `validated_at` — UTC timestamp (ISO 8601)
- `target_receipts` — list of `{id, content_hash}` references being validated
- `outcome` — one of `VALID | INVALID_STRUCTURAL | INVALID_SEMANTIC | INVALID_CHAIN | VALID_WITH_EXCEPTION`
- `violations` — list (empty on `VALID`)
- `exceptions` — list (empty unless `VALID_WITH_EXCEPTION`)

Any validation receipt missing any of these fields is itself invalid and must be rejected by downstream consumers.

## Acceptance criteria (frozen for validator implementation)

These criteria become test assertions when validator implementation begins (gap spec C2). They must be committed as executable assertions, not prose, before this ratification's effects are considered fully active.

1. Every validator run produces a `validation` receipt with all mandatory fields populated.
2. `validator_version` changes land with a `policy_declaration` receipt referencing the prior version as `supersedes`. A `ruleset_hash` change without a corresponding `validator_version` bump is invalid — startup must refuse, and any validation receipt emitted under such a state is non-binding. (Closes the "hotfix the rules under the same version and pretend nothing happened" back door.)
3. A chain re-validated under a new validator version produces a *new* validation receipt; the prior one is not mutated, deleted, or marked superseded — it remains the chain's validity-as-of-validator-vN, forever.
4. `ruleset_hash` mismatch between declaration and actual rules loaded → validator refuses to run (fail-closed at startup).
5. `validation` receipts must not serve as sole authority parents for `authorization` or `action` receipts (per `validator_contract.md` §4).

## Open sub-decisions (deferred follow-on ratifications)

These are implementation choices, not constitutional ones, and may be ratified separately as Q4.A and Q4.B without re-opening Q4:

- **Q4.A — `validator_id` format.** Free-form string (e.g. `"agent_gov.validator.standing_chain"`) **vs.** URI **vs.** UUID. Affects identifier stability and registry lookup but not constitutional structure.
- **Q4.B — Validation receipt event type.** Inherits from Q1.A — if Q1.A picks "new event types," `validation` becomes a new `VALIDATION` event; if Q1.A picks "payload overload," `validation` rides on an existing event type with `receipt_role: "validation"` in payload. Q4.B should be settled in the same artifact as Q1.A to avoid drift.

## What this does NOT ratify

- Q2 (`subject_derivation` enum)
- Q3 (exception-class registry)
- Q1.A, Q1.B, Q4.A, Q4.B (above)
- The bootstrap policy for the *first* validator version (chicken-and-egg: how does v1.0.0 get a `policy_declaration` when no validator exists yet to validate the declaration?). This is a one-time bootstrap problem; the gap spec's Q5 pre-ratification fallbacks cover it but the bootstrap mechanics need their own short note before C2.
- Receipt envelope schema (gap spec C3)
- Validator implementation (gap spec C2)

## How to ratify

The ratifier — and only the ratifier — flips this candidate to active by:

1. Setting `status: ratified`
2. Filling `ratifier: <name>`
3. Filling `ratified_at: <ISO 8601 UTC>`
4. Committing the change

Editing any other field after ratification requires a successor decision artifact with `supersedes: decision.validator_integration.q4`. The ratified record is immutable; corrections are made by superseding, not by mutation.
