# GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001

## Title

Decomposition completeness via capability closure — recomposition is only as
sound as the decomposition it accounts, and AG-alone cannot prove the boundary
*set* is closed while boundaries are *declared* rather than *granted*.

## Status

**Candidate — doctrine + blocker; NOT a build.** Filed 2026-06-13 (operator +
interferometry, after P3.2 landed enforcing recomposition). Companion to
`docs/cross-tool/decomposition-capability-closure-note.md` (the front-end mirror
to `rung-activation-four-office-note.md`). This gap installs the *refusal*, the
*receipt-shape discipline*, and the *blocker* now; the capability-kernel
integration is future work composing with
`GOV_GAP_OFFICE_COLLAPSE_AND_RECEIPT_SOVEREIGNTY_001` and the receipt-sovereignty
note. **This gap blocks further decompose/recompose feature work** (incl. campaign
P4) until the enumeration/coverage split is preserved in the receipt shape.

## What exists

- `pipeline_types.account_boundaries(admitted, accounted)` (P1.1): pure + total
  over the *admitted* set. Proves every admitted boundary got a disposition.
- `RecompositionReceipt` + enforcing recomposition at the orchestrator seam
  (P3.2): `refused_laundering` blocks a dropped *admitted* boundary.
- The four-office activation transaction (P3.1) and its receipts — the back-half
  ledger this gap names the front half of.

## The hole (what needs building, eventually)

`account_boundaries` is structurally blind to a real boundary that was **never
admitted** at decompose. The two laundering modes are duals:

```
CLOSED (P3.2):  admitted boundary silently dropped at recompose.
OPEN  (this):   real boundary never admitted at decompose -> invisible.
```

Confirmed: `account_boundaries(['A','B'], {all completed}) -> admissible`,
regardless of an undeclared real boundary `C`
(`tests/test_decomposition_closure_limit.py` pins this). You cannot audit the
absence of an omitted boundary; you can only make omission **unexecutable** —
which requires boundaries to be **kernel-granted capabilities**, not plan-declared
surfaces. Then the boundary set is the grant set, closed by construction.

Two completeness layers (only the first is mechanical for AG-alone):

1. **Enumeration completeness** — admitted boundary set == kernel grant set.
   AG-alone owns it fully when boundaries are caps.
2. **Coverage completeness** — granted caps/rules close over plan intent with no
   gaps, contradictions, or out-of-scope composition. AG-alone is **best-effort**;
   completeness evidence is Z3 (bounded) or Lean (cited theorem).

## Acceptance criteria / negative-test matrix (NOT implemented here)

Receipt-shape discipline (the cheap hardener wiring will target these):
- AC1: a decomposition check emits `enumeration` and `coverage` fields separately;
  AG-alone may emit `enumeration: complete` but only `coverage: best_effort`
  (with `verifier: absent`, `proof_tier: ag_only`).
- AC2: **no AG-alone receipt may emit `coverage: complete` or
  `decomposition: complete`** without solver / theorem / operator evidence. A
  unit test asserts the constructor/guard refuses it.

Closure + composition refusals (capability-kernel era):
- AC3: an omitted declared boundary cannot be treated as clean merely because
  `account_boundaries` passes — recomposition over a cap ledger accounts the
  *grant set*, not the *declared set*.
- AC4: a slice attempting an ungranted cap → hard refusal + receipt.
- AC5: composition of A and B without a `seam(A,B)` cap → refused (composition is
  not conjunction; the seam is its own cap/rule).
- AC6: a granted cap exercised without a disposition → recomposition denied;
  a granted-not-exercised cap → pass-with-warning (decomposition pressure).

Prep-before-ingest:
- AC7: a plan with an indecomposable gate emits an ingest-blocking
  `NonDischargeClaim(kind=indecomposable_gate, blocks=plan_ingest)`.
- AC8: re-running prep cannot clear `indecomposable_gate` without an authorized
  discharge receipt (the planner may propose a decomposition; it may not
  self-certify that judgment disappeared — assert-standing).

Verifier placement:
- AC9: Z3 may discharge bounded programmatic cap/rule constraints synchronously at
  prep; `verifier.allowed` is evidence, never authority (cannot become
  `decomposition legitimate`).
- AC10: Lean appears only as a cited, already-proven theorem/refusal-class
  artifact — never a live ingest-path proof. A gate needing a new proof is
  flagged/deferred to the operator, not blocked-on.

## Non-goals

- NOT building the capability kernel / typed cap IPC now (that is the microkernel
  integration — future, partly custody-affecting).
- NOT wiring the verifier (`~/git/verifier`) on the ingest path now.
- NOT a runtime prep/ingest pass yet. This gap names the refusals; the wiring
  order is: document → audit → receipt-shape fields + guards + negative tests →
  shadow stubs → real wiring.

## Open questions

1. Where does the prep/ingest rung-transition live in AG's existing machinery
   (intent_compiler? a new prep pass?) — reuse the rung-activation gate, don't
   mint a new mechanism.
2. Decision-cap representation: how do "may classify in venue V"-style decision
   caps share the grant ledger with resource caps?
3. Grant-vs-exercise accounting shape (granted/exercised/denied/seam) — receipt
   fields vs a separate cap-ledger artifact.

## Doctrine line

> You cannot audit the absence of an omitted boundary. You can only make omission
> unexecutable. Declared boundaries are pleadable; granted capabilities are
> accountable.
