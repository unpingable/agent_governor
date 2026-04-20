---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator_integration.q2
ontology_version: gov-doctrine-v1
supersedes: null
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-19T18:10:49Z
---

# Q2 Ratification Candidate — `subject_derivation` Enum

## Selection

**Option B.** `subject_derivation.kind` is a closed enum with four values. Additions to the enum require a ratified `policy_declaration` (same rule as ontology drift). Any value not in the registered set makes the receipt `INVALID_STRUCTURAL`. Free-text `basis` is not a substitute and does not unlock unrecognized kinds.

The four ratified values:

- `same_subject`
- `instance_of`
- `aggregation_of`
- `scope_narrowing`

## Source

`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md` §Q2.

## Basis

This is a doctrine-level question, like Q4. The argument for B is structural:

- A free-text `basis` field (Option C) is exactly the back door the doctrine closes at `advisory_vs_constitutional_power.md` §3.1 — it lets Governor smuggle interpretation through subject lineage.
- A closed enum without extension (Option A) is too brittle for evolution; new transformations would require either rule-bending or doctrine breakage.
- B treats the enum itself as governed ontology: the four values are ratified now, and any addition is a `policy_declaration` event subject to `validator_contract.md` §9 ("ontology drift is policy drift").

No empirical falsification pass is possible yet — there are no standing-class receipts in production, so no existing chain exercises the enum. The first receipts written are also the first test of whether the four values cover the known cases. If they don't, the answer per the gap spec is to widen deliberately via `policy_declaration`, not to add `other`.

## Semantics (frozen)

The validator must implement these checks for each kind. A `subject_derivation` whose declared kind cannot pass its mechanical check is `INVALID_STRUCTURAL`.

- **`same_subject`** — child `subject` byte-equals at least one parent's `subject`. No derivation record required (the equality *is* the derivation).
- **`instance_of`** — child references a parent by hash via `parent_receipts` and declares itself a concrete member of that parent. The mechanical check at this layer is the hash-linked parentage; verifying that the parent is itself "class-shaped" depends on Q2.B and is not enforceable until Q2.B ratifies. Until then, the validator enforces the linkage and accepts the kind on that basis alone.
- **`aggregation_of`** — child subject is the aggregate of N named parent subjects. All N parents must appear in `parent_receipts` (no implicit aggregation).
- **`scope_narrowing`** — child subject is a strictly contained sub-scope of a parent subject. "Strictly contained" means child ≠ parent — an equal subject must be declared `same_subject`, not narrowed to itself. Containment must be mechanically checkable.

## Derivation failure conditions (frozen)

A `subject_derivation` is invalid when any of these hold:

1. `kind` is not in the registered set
2. The required parent relationship cannot be verified against `parent_receipts`
3. The containment claim (for `scope_narrowing`) cannot be checked mechanically
4. The child subject has no relation to any parent subject that fits the declared kind

## What this ratifies

- The four-value closed enum.
- The rule that additions require a ratified `policy_declaration` with `supersedes` referencing the prior version of the enum.
- The four mechanical check semantics above.
- The four failure conditions above.
- The principle that `subject_derivation.basis` (if present as a descriptive field) is **not** a validator input — it does not affect admissibility. Removing or changing `basis` post-hoc must not change the validator verdict.

## Acceptance criteria (frozen for validator implementation)

These criteria become test assertions when validator implementation begins (gap spec C2):

1. Every `subject_derivation` on a valid chain has a `kind` in the registered set; unknown kinds → `INVALID_STRUCTURAL`.
2. For each kind, there is a mechanical check the validator runs — no human judgment in the loop, no LLM call, no string-matching prose.
3. Adding a new kind requires a `policy_declaration` receipt referencing the prior enum version as `supersedes`. Retrofitting the new kind to prior receipts is not allowed; receipts are interpreted under the `ontology_version` in force when they were written.
4. A receipt whose declared kind cannot pass its mechanical check is `INVALID_STRUCTURAL`, not `VALID_WITH_EXCEPTION`. (Subject lineage is not in the compression-exception path.)

## Open sub-decisions (deferred follow-on ratifications)

These are implementation choices, not constitutional ones, and may be ratified separately as Q2.A and Q2.B without re-opening Q2:

- **Q2.A — `scope_narrowing` mechanical check.** Prefix match **vs.** set-membership **vs.** declared scope-axis narrowing (or a combination, with the kind disambiguated by an inner sub-field). Affects what counts as a "scope" subject and how the validator tests containment.
- **Q2.B — `instance_of` parent-class typing.** Does this require a typed-subject system (subjects carry a `type` tag), or is hash-only reference sufficient? Affects whether the validator can detect "instance of the wrong class" or only "instance of the wrong parent."

## What this does NOT ratify

- Q3 (exception-class registry)
- Q1.A, Q1.B, Q4.A, Q4.B, Q2.A, Q2.B (above)
- The `subject` field's internal structure or typing system (subjects remain opaque strings/hashes at this layer)
- Whether `subject_derivation` is a separate kernel field or lives inside `payload`. (Inherits from Q1.A — same event-type strategy applies.)
- Receipt envelope schema (gap spec C3)
- Validator implementation (gap spec C2)

## How to ratify

The ratifier — and only the ratifier — flips this candidate to active by:

1. Setting `status: ratified`
2. Filling `ratifier: <name>`
3. Filling `ratified_at: <ISO 8601 UTC>`
4. Committing the change

Editing any other field after ratification requires a successor decision artifact with `supersedes: decision.validator_integration.q2`. The ratified record is immutable; corrections are made by superseding, not by mutation.
