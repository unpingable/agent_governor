---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator.v0_3_0
ontology_version: gov-doctrine-v1
supersedes: decision.validator.v0_2_0
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-22T00:00:00Z
validator_id: agent_gov.standing_chain_validator
validator_version: 0.3.0
expected_ruleset_hash: sha256:94b6d542b620d7f85b42f95da0beff0c7a57fd748f310e4cb48cda6216d3544c
prior_validation_receipt_path: _validations/decision.validator.v0_3_0.json
references:
  - decision.validator_integration.q1
  - decision.validator_integration.q2
  - decision.validator_integration.q3
  - decision.validator_integration.q4
  - decision.validator.v0_1_0
  - decision.validator.v0_2_0
---

# Validator v0.3.0 — Check Basis Structure (C4)

This declaration supersedes `decision.validator.v0_2_0` to tighten
`Check.basis` from a freeform string into a structured
:class:`CheckBasis` (summary + rule_id + inspectable_refs). The
validator's enforced rules changed; per ratified Q4 that requires a
new `policy_declaration` carrying the new `expected_ruleset_hash`,
with `supersedes` populated.

This is the **second** non-bootstrap declaration in the validator
lineage and the **first repeat exercise** of the supersession
ceremony. v0.1.0 → v0.2.0 proved the ceremony was possible; v0.2.0
→ v0.3.0 proves it is repeatable as a routine pattern, not a
one-shot move.

## Selection

`agent_gov.standing_chain_validator` at version `0.3.0` is declared
as the operative validator for receipts under the `gov-doctrine-v1`
ontology version, with `expected_ruleset_hash` as named in
frontmatter.

## What changed in 0.3.0

`Check.basis` is no longer a freeform `str`. It is a structured
:class:`CheckBasis` with three required fields:

- `summary` — non-empty brief reason (the human-readable bit that
  used to be the entire `basis` string)
- `rule_id` — non-empty identifier of the rule that produced the
  verdict (e.g. `"validator_contract.5.1"`); makes the basis
  cite-able
- `inspectable_refs` — non-empty list of non-empty strings; each
  entry is a handle to inspectable state (parent receipt id, scope
  axis name, policy_artifact_id, etc.)

Failure mode this prevents:

```json
{"result": "pass", "basis": "seemed fine"}
```

Before C4: parsed and accepted under C3's "schema enforces presence
and shape, not content depth" rule. After C4: rejected with
`AUTHORIZATION_CHECK_MALFORMED` and the message "freeform string
basis is not admissible (C4)".

## What did NOT change

- Standing lattice, role-standing mapping, parentage transitions
- The four ratified Q1–Q4 anchors
- Empty initial exception-class registry
- ViolationCode set (no new codes — `AUTHORIZATION_CHECK_MALFORMED`
  was reused; ChatGPT's "no taxonomy bloom" rule held)
- Closed envelope key set
- Hash format discipline
- `from_dict` deserialization path (extended internally to delegate
  basis parsing to `CheckBasis.from_dict`, but no new envelope keys)
- Subject derivation `basis` field — Q2 explicitly ratified that
  field as descriptive prose, NOT a validator input. C4 does **not**
  touch it.

## Supersession ceremony — second iteration

Per `decision.validator.v0_1_0`'s "what future validators must do"
and `decision.validator.v0_2_0`'s "how to supersede":

> A successor `policy_declaration` must satisfy the same
> non-transitive-bootstrap rule: carry an attested validation
> receipt produced by *this* validator (v0.2.0).

The attestation lives at `_validations/decision.validator.v0_3_0.json`
(relative to this directory). It is a `ValidationReceipt`-shaped
artifact produced by v0.2.0 with:

- `validator_id: agent_gov.standing_chain_validator`
- `validator_version: 0.2.0`
- `ruleset_hash: <decision.validator.v0_2_0.expected_ruleset_hash>`
- `outcome: VALID`
- `target_receipts: [{ id: decision.validator.v0_3_0, content_hash:
  <this file's hash> }]`

The v0.3.0 validator at startup verifies the receipt targets *this
exact document* and that its identity / ruleset / outcome claims
match the v0.2.0 declaration's frontmatter. Any failure →
`BootstrapError`. The ceremony is now operated through the canonical
regeneration script (`scripts/standing/regenerate_supersession_receipt.py`),
documented at `docs/doctrine/decisions/_validations/README.md`.

This second iteration confirms that the bootstrap exemption holds at
v0.1.0 *only*. v0.2.0 → v0.3.0 is non-transitive too.

## Acceptance criteria (frozen)

These criteria become test assertions in `tests/test_standing_schema.py`:

1. `compute_ruleset_hash()` returns the value declared in
   `expected_ruleset_hash`. Mismatch → `BootstrapError`.
2. The validator constructor raises `BootstrapError` if the prior
   v0.2.0 validation receipt is missing or claims the wrong
   identity/ruleset/outcome/target.
3. Parsing `{"result":"pass","basis":"seemed fine"}` raises
   `EnvelopeParseError` with `AUTHORIZATION_CHECK_MALFORMED`.
4. AUTHORIZE checks with structured basis (summary + rule_id +
   non-empty inspectable_refs) parse cleanly.
5. CheckBasis missing any required field → `EnvelopeParseError`
   with `AUTHORIZATION_CHECK_MALFORMED`.
6. CheckBasis with empty `inspectable_refs` →
   `AUTHORIZATION_CHECK_MALFORMED`.
7. The supersession receipt at
   `_validations/decision.validator.v0_3_0.json` is reproducible
   byte-identically by re-running the regen script with the same
   `--validated-at` value.

## Open sub-decisions still deferred

Q1.A, Q1.B, Q2.A, Q2.B, Q3.A, Q3.B, Q3.C, Q4.A, Q4.B remain open as
implementation choices. C4 introduces no new sub-decisions: no
`BasisKind` enum, no constraint on `inspectable_refs` content, no
adjudication of whether a given basis is sufficient. Those would be
follow-on ratifications if and when field experience demands them.

## What this does NOT ratify

- Per-role payload field schemas (validator_contract §7 catalogue)
- Continuity-claim basis fields (validator_contract §10) — the
  `identity_basis`, `provenance_basis`, `evidence_basis`,
  `operator_confidence_basis` fields are a *different* surface from
  `Check.basis` and remain a separate follow-on
- A taxonomy of `inspectable_refs` shapes (parent receipt id vs.
  policy artifact id vs. scope axis name) — strings only at this
  layer; convention may emerge before being constitutionalized
- Gap survival/resolution (validator_contract §7) — still deferred
- Receipt envelope extensions

## How to supersede

A successor `policy_declaration` with
`supersedes: decision.validator.v0_3_0` + `status: ratified`,
ratified by the constitutional ratifier. Successor must satisfy the
same non-transitive-bootstrap rule: carry an attested validation
receipt produced by v0.3.0.

## Compressed lines

- Basis is now a structure, not a vibe.
- Same falsification target as ever: a verdict that points at
  nothing should fail loudly, and now it does.
- Two supersessions in: the ceremony is a pattern, not a relic.
