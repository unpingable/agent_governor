---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator.v0_4_0
ontology_version: gov-doctrine-v1
supersedes: decision.validator.v0_3_0
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-22T00:00:00Z
validator_id: agent_gov.standing_chain_validator
validator_version: 0.4.0
expected_ruleset_hash: sha256:4d55046f9841d8aae3bb43e13dfc949ebbcbb38a44068b90cb2b0baf105712d4
prior_validation_receipt_path: _validations/decision.validator.v0_4_0.json
references:
  - decision.validator_integration.q1
  - decision.validator_integration.q2
  - decision.validator_integration.q3
  - decision.validator_integration.q4
  - decision.validator.v0_1_0
  - decision.validator.v0_2_0
  - decision.validator.v0_3_0
---

# Validator v0.4.0 — Continuity Basis (C5)

This declaration supersedes `decision.validator.v0_3_0` to introduce
the structured `continuity_basis` block on receipts that claim
continuity preservation (validator_contract §10). The validator's
enforced rules changed; per ratified Q4 that requires a new
`policy_declaration` carrying the new `expected_ruleset_hash`, with
`supersedes` populated.

This is the **third iteration** of the supersession ceremony.
v0.1.0→v0.2.0 was ritual; v0.2.0→v0.3.0 was repetition; v0.3.0→v0.4.0
is **routine**. The pattern is now infrastructure, not novelty.

This is also the first commit that crosses out of the *validator-core
phase* (C2–C4: making the validator itself coherent) and into the
*continuity-facing phase* (C5+: extending the validator to govern
substantive admissibility surfaces beyond its own bootstrap).

## Selection

`agent_gov.standing_chain_validator` at version `0.4.0` is declared
as the operative validator for receipts under the `gov-doctrine-v1`
ontology version, with `expected_ruleset_hash` as named in
frontmatter.

## What changed in 0.4.0

### Continuity basis becomes a structured block

`StandingReceipt` gains a `continuity_basis: ContinuityBasis | None`
field. When present, it is a presence-as-claim assertion that the
receipt preserves continuity. The block is governed
**all-or-nothing**: it must contain all four required sub-bases per
validator_contract §10:

- `identity_basis` — what makes this entity the same entity over time
- `provenance_basis` — what is the origin/lineage chain
- `evidence_basis` — what evidence supports the continuity claim
- `operator_confidence_basis` — what justifies operator confidence

Each sub-basis is a `BasisRecord` with the same `{summary, rule_id,
inspectable_refs}` shape as `CheckBasis` (C4) — distinct type, shared
structural validation helper.

### Role gate

Only roles in `CONTINUITY_CLAIMABLE_ROLES` may carry a
`continuity_basis`:

- `recommendation`
- `authorization`
- `action`

Receipts of role `observation`, `interpretation`, `policy_declaration`,
or `validation` that include `continuity_basis` are rejected with
`CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE`. Continuity preservation is a
substrate-level claim about action; observations, interpretations,
and policy declarations do not bear that claim.

### Operator confidence is descriptive only

The validator enforces that `operator_confidence_basis` is present
and structurally sound. It does **not** read its content as a
weighting signal. Promoting `operator_confidence_basis` to
adjudicative (verdict-influencing) would be a hotter seam and
requires its own Q4-style supersession.

### Hostile-input discipline extends to continuity_basis

Per chatty's "presence = loophole" warning, all of the following are
rejected at parse time:

- `continuity_basis: null` — explicit null is not omission
- `continuity_basis: {}` — empty block is not no-claim
- `continuity_basis: {identity_basis: ...}` — partial blocks are
  not admissible (all-or-nothing)
- Any sub-basis with empty `inspectable_refs`
- Any sub-basis missing `summary` or `rule_id`
- Any sub-basis with non-string ref entries

All produce `CONTINUITY_BASIS_MALFORMED`.

### Two new ViolationCodes

- `CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE` (structural) — the role gate
- `CONTINUITY_BASIS_MALFORMED` (structural) — bundles every
  structural failure of the block itself; per chatty
  "no taxonomy bloom"

These were forced — no existing code captures "field present on
wrong role" or "presence-as-claim block missing required sub-basis."

## What did NOT change

- Standing lattice, role-standing mapping, parentage transitions
- The four ratified Q1–Q4 anchors
- Empty initial exception-class registry
- Closed envelope key set (gained `continuity_basis`; the closure
  rule itself is unchanged)
- Hash format discipline (C3)
- Check.basis structure (C4) — distinct surface, not touched
- Subject_derivation `basis` field — Q2 ratification, descriptive
  prose, unchanged
- `from_dict` deserialization general path — extended to parse
  `continuity_basis`, but no change to the closed-envelope or
  required-fields rules

## Supersession ceremony — third iteration

Per the standing rule from `decision.validator.v0_1_0`:

> Every successor — including any that supersedes a successor —
> carries one of these files. The bootstrap exemption is not
> transitive.

The attestation lives at `_validations/decision.validator.v0_4_0.json`
(relative to this directory), produced by v0.3.0 via the canonical
regen script (`scripts/standing/regenerate_supersession_receipt.py`).

The v0.4.0 validator at startup walks the chain v0.4.0 → v0.3.0 →
v0.2.0 → v0.1.0 and verifies the v0.3.0-attestation receipt. Any
failure → `BootstrapError`.

## Acceptance criteria (frozen)

These criteria become test assertions in
`tests/test_standing_schema.py` `TestContinuityBasisDiscipline`:

1. `compute_ruleset_hash()` returns the value declared in
   `expected_ruleset_hash`. Mismatch → `BootstrapError`.
2. Walking the supersession chain from v0.4.0 terminates at v0.1.0;
   chain has no cycles.
3. `continuity_basis` on a receipt with role in
   `CONTINUITY_CLAIMABLE_ROLES` and a fully populated structured
   block → `VALID`.
4. `continuity_basis` on a receipt with role
   `observation`/`interpretation`/`policy_declaration`/`validation` →
   `INVALID_STRUCTURAL` keyed
   `CONTINUITY_BASIS_ROLE_NOT_ELIGIBLE`.
5. Parsing `continuity_basis: null` raises `EnvelopeParseError` with
   `CONTINUITY_BASIS_MALFORMED`.
6. Parsing `continuity_basis: {}` raises `EnvelopeParseError` with
   `CONTINUITY_BASIS_MALFORMED`.
7. Parsing partial `continuity_basis` (missing one or more required
   sub-bases) raises `EnvelopeParseError` with
   `CONTINUITY_BASIS_MALFORMED`.
8. Each sub-basis must be a structured
   `{summary, rule_id, inspectable_refs}` block; freeform string
   sub-basis → `CONTINUITY_BASIS_MALFORMED`.
9. The supersession receipt at
   `_validations/decision.validator.v0_4_0.json` reproduces
   byte-identically when `regenerate_supersession_receipt.py` is run
   with the same `--validated-at`.

## Open sub-decisions still deferred

Q1.A, Q1.B, Q2.A, Q2.B, Q3.A, Q3.B, Q3.C, Q4.A, Q4.B remain open as
implementation choices. C5 introduces no new sub-decisions — no
``BasisKind`` enum, no constraint on ``inspectable_refs`` content,
no adjudicative semantics for ``operator_confidence_basis``. Those
are explicit non-goals at this layer; future ratification can promote
any of them if field experience demands.

## What this does NOT ratify

- Per-role payload field schemas (validator_contract §7 catalogue)
- Gap survival/resolution (validator_contract §7) — still deferred
- Adjudicative semantics for `operator_confidence_basis` — descriptive
  only at this layer
- A taxonomy of `inspectable_refs` shapes
- Any specific `rule_id` namespace — convention may emerge before
  being constitutionalized
- Any sub-basis content semantics beyond presence + structure
- Receipt envelope extensions beyond the new `continuity_basis` key

## How to supersede

A successor `policy_declaration` with
`supersedes: decision.validator.v0_4_0` + `status: ratified`,
ratified by the constitutional ratifier. Successor must satisfy the
non-transitive-bootstrap rule: carry an attested validation receipt
produced by v0.4.0 via the canonical regen script.

## Compressed lines

- Continuity preservation is a claim, not a vibe.
- The block is all-or-nothing — partial basis is folklore through the
  service entrance.
- Three supersessions in: ceremony is now infrastructure.
- Validator-core phase complete; continuity-facing phase begins here.
