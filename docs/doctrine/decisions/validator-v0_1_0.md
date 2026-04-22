---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator.v0_1_0
ontology_version: gov-doctrine-v1
supersedes: null
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-22T00:00:00Z
validator_id: agent_gov.standing_chain_validator
validator_version: 0.1.0
expected_ruleset_hash: sha256:b8b96ecfaa595d07deb90d049861806486e3108e2a9514a8a31164dd744e7bdb
references:
  - decision.validator_integration.q1
  - decision.validator_integration.q2
  - decision.validator_integration.q3
  - decision.validator_integration.q4
---

# Validator v0.1.0 — Bootstrap Policy Declaration

This is the **bootstrap** policy_declaration for the standing-class
chain validator. It is, by construction, the one declaration that
cannot have been validated by a prior validator run, because the
validator it ratifies is the first one. Read this document with that
asymmetry in mind.

## Selection

`agent_gov.standing_chain_validator` at version `0.1.0` is declared as
the operative validator for receipts under the `gov-doctrine-v1`
ontology version, with `expected_ruleset_hash` as named in the
frontmatter.

## Why this artifact cannot be validated by a prior validator receipt

Q4 of `GOV_GAP_VALIDATOR_INTEGRATION_001` ratifies that "every validator
version is a `policy_declaration` … bumping the version requires
ratified declaration with `supersedes`." Applied to the *first* validator,
this generates a chicken-and-egg: there is no prior validator to validate
the declaration, and `supersedes` is `null` because there is no prior
version to supersede.

This is the bootstrap problem Q4 explicitly defers: "the bootstrap
mechanics need their own short note before C2." This document is that
note, in artifact form.

## What makes this artifact admissible anyway

Three constraints, named so the hole is **bounded** rather than
folkloric:

1. **It cites the ratified Q1–Q4 anchors as its constitutional basis.**
   The four `decision.validator_integration.q*` artifacts in this same
   directory were ratified before this declaration was written. They
   are the doctrine the validator obeys; this declaration only pins the
   implementation that obeys them. The basis chain is:

   ```
   doctrine (advisory_vs_constitutional_power, standing_and_receipts,
             validator_contract)
     → ADR 0006 (Governor-Called, Not Governor-Native)
     → Q1–Q4 ratifications (constitutional integration questions
                            resolved as policy_declarations)
     → THIS document (validator implementation pinned to ratified
                      resolutions)
     → all subsequent receipts (validated by the validator this
                                document declares)
   ```

2. **It carries `expected_ruleset_hash`, against which the validator
   itself fails closed at startup.** The validator computes its own
   ruleset hash from a canonical snapshot of role/standing mappings,
   transition rules, the subject-derivation enum, and the validation
   outcome enum (see `compute_ruleset_hash` in
   `src/governor/standing/validator.py`). On startup it compares the
   computed value against this declaration's
   `expected_ruleset_hash`; mismatch raises `BootstrapError` and the
   validator refuses to run. Editing the validator's rules without
   superseding this declaration breaks the system loudly and
   immediately — the back door Q4 §"closes the hotfix the rules under
   the same version and pretend nothing happened" door.

3. **It is the only declaration in this directory permitted to lack a
   prior validation receipt.** Every `policy_declaration` ratified
   *after* this document — including any successor that supersedes it
   — is admissible only if a validator run produced a `validation`
   receipt against it. This declaration carries the bootstrap exemption
   by virtue of being first; no future declaration may.

## What future validators must do

This is one sanctioned hole. It does not enlarge.

- A new validator version (e.g. `0.2.0`) requires its own
  `policy_declaration` with `supersedes:
  decision.validator.v0_1_0` populated.
- The new declaration's `expected_ruleset_hash` must reflect the new
  validator's actual computed `ruleset_hash`, or the new validator
  will refuse to run.
- The new declaration must itself be admitted via a validation receipt
  produced by the *prior* validator (this one, v0.1.0). The bootstrap
  exemption is not transitive.
- This document remains in the repository as the historical bootstrap
  artifact, immutable like every other ratified decision. Corrections
  happen via supersession, not mutation.

## Acceptance criteria (frozen)

These criteria become test assertions in `tests/test_standing_validator.py`:

1. The validator constructor raises `BootstrapError` when this
   declaration is missing from the loaded `PolicyRegistry`.
2. The validator constructor raises `BootstrapError` when the
   declared `expected_ruleset_hash` differs from the computed
   `ruleset_hash`.
3. The validator constructor raises `BootstrapError` when the
   declared `validator_version` differs from the in-code
   `VALIDATOR_VERSION`.
4. The four `decision.validator_integration.q*` anchors are required
   in the registry; missing any one raises `BootstrapError`.

## What this does NOT ratify

- Any sub-decision left open by Q1–Q4 (Q1.A/Q1.B/Q2.A/Q2.B/Q3.A/Q3.B/Q3.C/Q4.A/Q4.B).
  Working choices made in the v0.1.0 implementation are documented in
  module docstrings as **working choices** pending follow-on
  ratification, not as constitutional facts.
- Any specific exception class (the registry remains empty per Q3).
- Receipt envelope schema (gap spec C3, blocked on this commit
  landing).
- The seat-vs-occupant successor schema flagged in
  [`decisions/README.md`](README.md). The current `ratifier` field
  remains the transitional convenience.

## How to supersede

A successor `policy_declaration` in this directory with
`supersedes: decision.validator.v0_1_0` and `status: ratified`,
ratified by the constitutional ratifier, replaces this artifact going
forward. The replacement must satisfy the four "what future validators
must do" rules above.

## Compressed lines

- One sanctioned bootstrap hole, named, bounded, not folkloric.
- The validator fails closed against its own declaration.
- 3am still votes for monarchy. This is the padlock holding the
  padlock.
