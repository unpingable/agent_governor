---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator.v0_2_0
ontology_version: gov-doctrine-v1
supersedes: decision.validator.v0_1_0
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-22T00:00:00Z
validator_id: agent_gov.standing_chain_validator
validator_version: 0.2.0
expected_ruleset_hash: sha256:4494deb9d8ce06334338355206c8f2258ca61e72c559b96d5810f993c65cc289
prior_validation_receipt_path: _validations/decision.validator.v0_2_0.json
references:
  - decision.validator_integration.q1
  - decision.validator_integration.q2
  - decision.validator_integration.q3
  - decision.validator_integration.q4
  - decision.validator.v0_1_0
---

# Validator v0.2.0 — Schema-Discipline Successor (C3)

This declaration supersedes `decision.validator.v0_1_0` to introduce
envelope schema discipline (gap spec C3 in
`GAP_BUILD_ORDER.md`). The validator's *enforced rules* changed; per
ratified Q4 that requires a new `policy_declaration` carrying the new
`expected_ruleset_hash`, with `supersedes` populated.

This is also the first non-bootstrap declaration in the validator
lineage — the bootstrap exemption that v0.1.0 carried is **not
transitive**. v0.2.0's admissibility depends on a validation receipt
produced by v0.1.0 against this very document.

## Selection

`agent_gov.standing_chain_validator` at version `0.2.0` is declared
as the operative validator for receipts under the `gov-doctrine-v1`
ontology version, with `expected_ruleset_hash` as named in
frontmatter.

## What changed in 0.2.0

The validator's rule surface gained:

1. **Strict content-hash format.** Every `parent_receipts[].content_hash`,
   `policy_artifact_hash`, and self-`content_hash` must match the
   `^sha256:[0-9a-f]{64}$` pattern. Anything else is
   `HASH_FORMAT_INVALID` (chain class).

2. **Structured AUTHORIZE checks** (validator_contract §9). AUTHORIZE
   receipts must carry the four required checks
   (`standing_check`, `admissibility_check`, `scope_check`,
   `budget_check`) as `{result, basis}` structures. Boolean-only or
   ID-only check fields are insufficient. New violation codes
   `AUTHORIZATION_CHECK_MISSING` and `AUTHORIZATION_CHECK_MALFORMED`.

3. **Closed envelope on deserialization.**
   `StandingReceipt.from_dict` rejects unknown keys, missing required
   common fields, and wrong-type structured fields with typed
   :class:`Violation` instances bundled in `EnvelopeParseError`.
   Hostile input fails fast at the boundary; there is no
   best-effort normalization.

4. **Schema pre-pass in `validate()`.** Schema violations surface
   alongside (not in place of) parentage / chain / policy checks;
   operators see the full picture, not just the first failure.

What did **not** change: the standing lattice, role-standing mapping,
the four ratified Q1–Q4 anchors, the empty initial exception-class
registry, or any pre-ratification fallback (still none).

## Supersession ceremony — non-transitive bootstrap

Per `decision.validator.v0_1_0`'s "what future validators must do":

> The new declaration must itself be admitted via a validation
> receipt produced by the prior validator (this one, v0.1.0). The
> bootstrap exemption is not transitive.

The attestation lives at `_validations/decision.validator.v0_2_0.json`
(relative to this directory). It is a `ValidationReceipt` produced by
v0.1.0 with:

- `validator_id: agent_gov.standing_chain_validator`
- `validator_version: 0.1.0`
- `ruleset_hash: <decision.validator.v0_1_0.expected_ruleset_hash>`
- `outcome: VALID`
- `target_receipts: [{ id: decision.validator.v0_2_0, content_hash: <this file's hash> }]`

The v0.2.0 validator at startup loads the receipt, verifies it
targets *this exact document* (by id + content_hash), and verifies
the receipt's `validator_id` / `validator_version` / `ruleset_hash` /
`outcome` claims. **Any failure → `BootstrapError` at construction
time.** No interpretive dance.

Tamper-evidence: the receipt's `target_receipts.content_hash` binds
to this declaration's bytes. Replacing either file invalidates the
chain at startup.

## Acceptance criteria (frozen)

These criteria become test assertions in
`tests/test_standing_validator.py` and `tests/test_standing_schema.py`:

1. `compute_ruleset_hash()` returns the value declared in
   `expected_ruleset_hash`. Mismatch → `BootstrapError`.
2. The validator constructor raises `BootstrapError` if the prior
   validation receipt is missing, malformed JSON, has the wrong
   `validator_id`/`validator_version`/`ruleset_hash`/`outcome`, or
   does not target this declaration's content_hash.
3. AUTHORIZE receipts without the four required checks produce
   `AUTHORIZATION_CHECK_MISSING` and outcome
   `INVALID_STRUCTURAL`.
4. AUTHORIZE receipts with malformed `Check` entries produce
   `AUTHORIZATION_CHECK_MALFORMED`.
5. Parent refs with non-`sha256:[64-hex]` content_hash produce
   `HASH_FORMAT_INVALID` and outcome `INVALID_CHAIN`.
6. `StandingReceipt.from_dict` rejects unknown envelope keys with
   `UNKNOWN_FIELD_IN_ENVELOPE`, missing common fields with
   `MISSING_REQUIRED_COMMON_FIELD`, wrong types with
   `INVALID_FIELD_TYPE`. All raise `EnvelopeParseError` carrying the
   typed :class:`Violation` list.
7. `from_dict(to_dict(receipt))` produces a value whose
   `canonical_body()` is byte-identical to the original's.

## Open sub-decisions still deferred

Q1.A, Q1.B, Q2.A, Q2.B, Q3.A, Q3.B, Q3.C, Q4.A, Q4.B remain open as
implementation choices. The v0.2.0 validator continues the working
choices documented in module docstrings (payload-overload for kernel
events, free-form `validator_id`, prefix-only `scope_narrowing`
containment).

## What this does NOT ratify

- Per-role payload field schemas (validator_contract §7 catalogue) —
  follow-on as we accumulate field experience.
- Continuity-claim basis fields (validator_contract §10) — separate
  follow-on.
- Gap survival/resolution (validator_contract §7) — still deferred.
- Receipt envelope extensions (e.g. cryptographic signatures,
  cross-run citation shape per Q1.B) — the closed key set
  :data:`STANDING_RECEIPT_ENVELOPE_KEYS` is the operative envelope.

## How to supersede

A successor `policy_declaration` with
`supersedes: decision.validator.v0_2_0` + `status: ratified`,
ratified by the constitutional ratifier. Successor must satisfy the
same non-transitive-bootstrap rule: carry an attested validation
receipt produced by *this* validator (v0.2.0).

## Compressed lines

- Ratified rules became ratified enforcement.
- The bootstrap exemption holds for v0.1.0 only.
- Hostile input fails at the boundary, not in the validator.
- Q4 supersession is now an exercised mechanism, not a paper promise.
