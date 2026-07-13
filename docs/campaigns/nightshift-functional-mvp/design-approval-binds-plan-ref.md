# Design spec_slice: approval binds plan_ref

**Status:** spec_slice — filed 2026-07-13. **CUSTODY-AFFECTING; NOT ratified.**
The contract shape below is presented for operator ruling, not chosen. No
build_slice admits until the shape + migration story are ratified (§8: operator
ratification required for custody-affecting slices). This is the ruled NEXT
authority slice per `docs/PROGRAM_LEDGER.md`.

**Source finding:** `GAP-s6-sandwich-authority-findings.md` Finding 2 (codex
Critical, 2026-07-13). **Backlog stub:** `.governor/backlog/approval-binds-plan-ref.json`.

## The Problem (pre-existing v0 behavior, not S6/S7 regression)

A governed plan cites `approval_ref`. Admission checks that the ref *resolves*
to witness bytes (and, if `sha256:`, that they hash to it) — but **never that
the approval act names `env.plan_ref`**. So Plan B can cite Plan A's approval
witness and admit: **approval replay.** The doctrine "approval attaches to plan
bytes" is literally violated — today the witness attaches to nothing verifiable
about the plan it is admitting.

This is a distinct threat model from S6/S7. S7 made *ration citation* mean what
it already claimed (`execution_request ⊆ cited_ration`). This slice changes what
*approval* means. It must not be disguised as S7 cleanup.

## Candidate contract shapes (operator picks; do not pre-commit)

Both come from the finding; a third may emerge in ratification.

- **(i) Witness-carries-plan_ref.** The approval witness *content* includes the
  `plan_ref` it approves; admission checks `witness.plan_ref == env.plan_ref`.
  Approval bytes name their plan. Replay against another plan fails the equality
  check.
- **(ii) approval_ref-format-carries-plan_ref.** The `approval_ref` string
  encodes the plan_ref; admission requires it to equal `env.plan_ref`. No
  witness-content change, but the ref format becomes load-bearing.

Trade to be ruled: (i) puts the binding in attested bytes (stronger, but changes
what an operator mints); (ii) puts it in the ref grammar (lighter, but a string
convention is easier to forge/mis-mint than attested content). The choice is an
**approval-witness contract change**, hence custody-affecting.

## Ripple (why this is its own slice, not a patch)

- The NS-1 / NS-1R approval procedure (README steps) changes — a witness minted
  the old way won't carry the binding.
- Operator tooling that mints witnesses changes.
- **Migration story required:** existing approved plans (NS-1 frozen v0 bytes,
  NS-1R) must either be re-approved under the new contract or grandfathered by
  an explicit, receipted exemption. Grandfathering is itself custody-affecting —
  ruled, not assumed. (Composes with the S6 ruling: migration creates a
  *successor* artifact rather than revising an approved predecessor.)

## Acceptance criteria (to finalize AFTER the shape is ruled)

1. A plan citing an approval witness that names a *different* plan_ref is
   **refused at admission** with a typed refusal (closed vocabulary — this slice
   mints/exercises the refusal kind; naming it is part of ratification, e.g.
   `approval_plan_ref_mismatch`).
2. A plan whose approval correctly names its own plan_ref admits (positive twin).
3. The NS-1 replay specimen that motivated the finding is refused after the fix
   (regression pins the threat).
4. Migration: every previously-approved plan is either re-approved under the new
   contract or carries an explicit receipted grandfather exemption — no silent
   admission of a plan whose approval predates the binding.
5. Sandwich: mandatory codex-exec adversarial review of the admission change
   (the finding came from codex; the fix faces the same knife). Exit codes
   observed; no ceremonial green.

## Non-goals

- Not a general approval ontology. Not ration-schema expansion. Not supervisor /
  execution arming. Not testimony adapters. Not rewriting NS-1's history (frozen
  v0 bytes stay frozen; migration makes successors).

## Validation provenance

_(Two gates before build. FIRST: operator ratifies the contract shape (i/ii/other)
+ the migration disposition (re-approve vs grandfather) — custody-affecting, §8.
THEN: escape-count pass over this spec with the shape filled in; zero escapes
admits the build_slice.)_
