---
audience: repo-local
status: active
---

# Validator Supersession Validation Receipts

This directory holds the validation receipts that each successor
validator's bootstrap declaration must cite. They are constitutional
artifacts, not test debris. Read this before editing.

## What lives here

One JSON file per successor validator version:

- `decision.validator.v0_2_0.json` — v0.1.0's attestation that the
  v0.2.0 bootstrap declaration is admissible.
- (future: `decision.validator.v0_3_0.json`, etc.)

Each file is canonical JSON (sorted keys, compact separators, ASCII-safe)
matching the `ValidationReceipt` shape from
`governor.standing.types`.

## The supersession ceremony

Per ratified Q4 (`docs/doctrine/decisions/Q4-validator-provenance.md`)
and the founding bootstrap declaration
(`docs/doctrine/decisions/validator-v0_1_0.md`):

> The new declaration must itself be admitted via a validation receipt
> produced by the prior validator. The bootstrap exemption is not
> transitive.

In four steps:

1. **Old validator admits the new declaration.** Operator (or the
   regen script) takes the structurally-complete successor
   declaration and produces a `ValidationReceipt` with
   `validator_version` = prior version, `ruleset_hash` = prior
   declaration's `expected_ruleset_hash`, `outcome` = `VALID`, and
   `target_receipts` containing one entry for the successor
   declaration's id + content_hash.
2. **Receipt lands on disk.** Saved as canonical JSON at the path
   the successor declaration names in `prior_validation_receipt_path`
   (relative to the declarations directory).
3. **New validator verifies it at startup.** When constructed
   against a registry containing a successor bootstrap, the
   validator reads the receipt, confirms it targets *this* declaration
   (id + content_hash), and checks `validator_id` /
   `validator_version` / `ruleset_hash` / `outcome` against the prior
   declaration's frontmatter. Any mismatch → `BootstrapError`. No
   interpretive dance.
4. **Bootstrap exemption stays at v0.1.0.** Only the founding
   validator may declare itself without a prior validation receipt.
   Every successor — including any that supersedes a successor —
   carries one of these files.

## Tamper-evidence model

The receipt's `target_receipts[0].content_hash` binds to the
successor declaration's exact bytes. The successor declaration carries
the relative path of the receipt. Either tampered → startup fails:

- Edit the declaration → its content_hash changes → receipt no longer
  targets it.
- Edit the receipt → either it no longer hashes the right declaration
  (target mismatch) or its claims (validator_id, ruleset_hash,
  outcome) drift away from the prior declaration's frontmatter.

There is intentionally no separate `prior_validation_receipt_hash`
field on the declaration. That would create a hash-cycle (declaration
contains receipt's hash; receipt's target contains declaration's
hash). The chain above is sufficient.

## How to mint a successor receipt

Use the canonical regeneration script:

```bash
python scripts/standing/regenerate_supersession_receipt.py \
    docs/doctrine/decisions/validator-v0_2_0.md
```

The script reads the successor declaration's frontmatter, hashes the
declaration file, looks up the prior declaration in the registry, and
writes the receipt to the path the successor names. Output is
byte-deterministic when `--validated-at` is pinned.

If you change the successor declaration after minting the receipt,
re-run the script. The receipt's `target_receipts.content_hash` must
match the declaration's current bytes or startup fails.

## Operator checklist before running the script

The script does not run the prior validator's logic — it produces a
structural attestation. Before invoking it for a real successor,
confirm by hand or by tooling:

- [ ] Successor declaration parses as valid frontmatter + body
- [ ] `policy_artifact_id` is unique and follows
  `decision.validator.v<MAJOR>_<MINOR>_<PATCH>` convention
- [ ] `supersedes` points at the immediately prior validator
  declaration
- [ ] `validator_version` strictly greater than the prior version
- [ ] `expected_ruleset_hash` matches the new validator's
  `compute_ruleset_hash()` output (run the new code to confirm)
- [ ] All four ratified Q1–Q4 anchors still loaded
- [ ] Successor declaration is at `status: ratified` (or accept that
  the receipt will need to be re-minted on ratification timestamp
  change)

## Where else this is documented

- `docs/doctrine/validator_contract.md` §16 — validator versioning
- `docs/doctrine/decisions/Q4-validator-provenance.md` — ratification
- `docs/doctrine/decisions/validator-v0_1_0.md` — bootstrap rule
- `docs/doctrine/validator_temporal_model.md` — compatibility posture
  (which receipts remain valid under which validator versions)
- `src/governor/standing/validator.py` `_verify_supersession()` — the
  actual startup check
- `tests/test_standing_schema.py` `TestSupersessionCeremony` —
  forged-receipt rejection tests
