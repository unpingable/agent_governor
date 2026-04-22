---
audience: repo-local
status: active
---

# Validator Temporal Model

Status: doctrine (interpretive)
Audience: validator implementers, anyone deciding whether to re-run a validator over old chains
Purpose: state explicitly the rules governing validator versions over time, so the temporal model is not discovered accidentally
Relationship to ratified doctrine: this document interprets and makes explicit a model that is implicit in `decisions/Q4-validator-provenance.md` and `validator_contract.md` §16. It is **not** a `policy_declaration` and adds no new ratified rule. If conflict ever arises between this doc and Q4, Q4 wins.

## The three rules

### 1. Validation receipts are point-in-time and immutable

A `validation` receipt produced by validator `v_N` against receipt
chain `C` is the validity-of-`C`-as-of-`v_N`. Forever. New validator
versions do not retroactively invalidate that record.

This is the literal text of Q4 ratification §"Historical reinterpretation":

> Validation receipts are point-in-time. A new validator version may
> produce a new validation receipt for a historical chain, but must
> not replace or invalidate the prior one.

The repo treats validation receipts as an append-only ledger.
Re-validation under a new version produces a *new* receipt; the prior
one is preserved untouched.

### 2. New validators do not silently re-validate historical chains

A successor validator (`v_M` where `M > N`) may *choose* to re-validate
a historical chain. It must produce a fresh validation receipt under
its own version. There is no implicit re-evaluation: an existing
chain's validity-as-of-`v_N` does not become validity-as-of-`v_M` by
default.

This protects against silent semantic drift: if Q3-style ontology
rules tighten between versions, an old chain that was VALID under the
old rules does not silently become INVALID under the new ones unless
somebody explicitly asks the new validator to re-evaluate it.

### 3. Standing receipts remain interpretable under their original ontology_version

Standing receipts carry `ontology_version` (per
`standing_and_receipts.md` §6). A receipt produced under
`gov-doctrine-v1` is interpreted under `gov-doctrine-v1`'s rules,
even after a successor ontology is ratified. This is the same
property as ratified policy artifacts: the past is read in its own
language, not retro-translated.

This is the explicit text of Q2 ratification §"Acceptance criteria":

> Adding a new kind requires a `policy_declaration` receipt
> referencing the prior enum version as `supersedes`. Retrofitting
> the new kind to prior receipts is not allowed; receipts are
> interpreted under the `ontology_version` in force when they were
> written.

The same rule applies to the standing class set, the receipt role
set, and any future closed-set extension via `policy_declaration`
lineage.

## Practical consequences

These three rules together imply the following operator-level
behaviors. They are observations, not new policy.

- **Replays must pin the validator version.** A reproducibility
  pipeline that re-runs validation receipts must use the validator
  version named in each receipt, not the latest installed version.
  "What did v0.1.0 say about chain C?" is a fixed historical
  question with a fixed answer.

- **Audit queries can be version-stratified.** "Show me every chain
  validated under `v0.1.0`" is a meaningful query because validation
  receipts carry `validator_version` as a mandatory field (Q4).

- **Successor validators may re-validate at any time.** Initiating a
  re-validation pass under `v_M` against historical chains is
  legitimate operator action. It produces new receipts. It does not
  invalidate the old ones.

- **Conflicting verdicts across versions are normal.** If `v_N`
  said VALID and `v_M` says INVALID, both receipts are true: the
  chain was valid under `v_N`'s rules and invalid under `v_M`'s. No
  reconciliation is required. The temporal model is the
  reconciliation.

- **Validator startup never silently reinterprets.** The startup
  bootstrap check (`_verify_bootstrap` /
  `_verify_supersession`) only verifies that *this* validator's
  declaration is admissible against its predecessor's. It does not
  re-validate any standing receipts. Re-validation is a separate,
  explicit operator action.

## What this model does not address

- **Receipt deletion.** Whether old receipts may ever be purged
  (vs. retained forever) is not decided here. The receipt_kernel
  retention policy applies to *blob* expiry, not to receipt
  envelopes themselves; envelopes are append-only by kernel
  contract. If garbage collection of historical envelopes ever
  becomes operationally necessary, it requires its own
  `policy_declaration` and is a separate temporal-model question.

- **Validator deprecation.** Whether old validator versions may ever
  be removed from the codebase is also not decided. Validation
  receipts under `v_N` remain interpretable as long as `v_N`'s rule
  surface can be reconstructed (from source, from a snapshot, from
  the policy_declaration metadata). Permanent removal of the source
  for `v_N` would make the temporal claim unfalsifiable, which is
  itself a constitutional concern. Deferred.

- **Cross-version equivalence claims.** "v0.2.0 returns the same
  verdict as v0.1.0 for chain C" is a queryable empirical question
  but not a constitutional guarantee. The temporal model says
  nothing about backward compatibility of verdicts across versions.

## Compressed lines

- The past is read in its own language.
- Validation receipts are point-in-time, append-only, immutable.
- Re-validation is explicit operator action, not implicit upgrade.
- 3am does not get to re-litigate yesterday's verdicts.
