---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator_integration.q1
ontology_version: gov-doctrine-v1
supersedes: null
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-19T17:56:47Z
---

# Q1 Ratification Candidate — Kernel Composition

## Selection

**Option A.** Standing-class receipts emit through `libs/receipt_kernel`'s existing event ledger. One hash chain per session; the six receipt_kernel invariants apply uniformly. Display metadata (operator-facing summaries, UI hints, telemetry sidecars) lives outside the canonical event body.

## Source

`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md` §Q1.

## Basis

Falsification pass on 2026-04-19 confirmed that A holds without StageGraph relaxation:

- `DEFAULT_STAGE_GRAPH` (`libs/receipt_kernel/src/receipt_kernel/stages.py:72-84`) does not need modification. The standing lattice (OBSERVE → INTERPRET → RECOMMEND → AUTHORIZE → EXECUTE) composes orthogonally onto the run lifecycle (COLLECT → EVALUATE → DECIDE → FINALIZE).
- `OBSERVE → EVIDENCE_PUT@COLLECT` and `AUTHORIZE → DECISION@DECIDE` map cleanly to native kernel event types and stages.
- The kernel hash chain (`event_hash = sha256(canonical_json(envelope - event_hash))`, `prev_event_hash` linking) provides Merkle-style parent integrity for free.
- `payload` (`envelope.py:97-101`) is a generic dict and absorbs `receipt_role`, `standing_class`, `subject`, `gaps`/`gaps_resolved`, and role-specific fields without envelope schema changes.

The falsification condition stated in the gap spec — "if A requires StageGraph relaxation or bypass, A is wrong" — did not trigger.

## What this ratifies

- Option A: standing-class receipts ride the receipt_kernel ledger.
- StageGraph stays as-is. No transitions added, removed, or relaxed.
- Receipt envelope hash semantics and parent-binding behavior are inherited from receipt_kernel, not re-invented.

## Acceptance criteria (frozen for validator implementation)

These criteria become test assertions when validator implementation begins (gap spec C2). They must be committed as executable assertions, not prose, before this ratification's effects are considered fully active.

1. A receipt committed to the chain can be re-hashed from its canonical form and produce the stored hash.
2. `parent_receipts[].content_hash` references resolve against the same chain the child is committed to.
3. The six receipt_kernel invariants continue to pass when standing-class receipts are present in the stream.
4. Display metadata that is not in the canonical body cannot change the receipt hash when edited.

## Open sub-decisions (deferred follow-on ratifications)

The falsification pass isolated two sub-decisions A confirms but does not resolve. These are implementation choices, not constitutional ones, and may be ratified separately as Q1.A and Q1.B without re-opening Q1:

- **Q1.A — Event-type strategy.** Add new event types (`INTERPRETATION`, `RECOMMENDATION`, `ACTION`, `POLICY_DECLARATION`) to `VALID_EVENT_TYPES` and bump `EVENT_SCHEMA_VERSION` **vs.** carry `receipt_role` in `payload` of existing event types.
- **Q1.B — Cross-run citation shape.** Reuse `refs.events` for cross-run AUTHORIZE → EXECUTE citation **vs.** add a new `parent_runs` field. The kernel models a governance run; execution naturally lives in the executor's own run, citing the authorization run's `DECISION` event.

## What this does NOT ratify

- Q2 (`subject_derivation` enum)
- Q3 (exception-class registry)
- Q4 (validator provenance)
- Q1.A, Q1.B (above)
- Receipt envelope schema (gap spec C3)
- Validator implementation (gap spec C2)

## How to ratify

The ratifier — and only the ratifier — flips this candidate to active by:

1. Setting `status: ratified`
2. Filling `ratifier: <name>`
3. Filling `ratified_at: <ISO 8601 UTC>`
4. Committing the change

Editing any other field after ratification requires a successor decision artifact with `supersedes: decision.validator_integration.q1`. The ratified record is immutable; corrections are made by superseding, not by mutation.
