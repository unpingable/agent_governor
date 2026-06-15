# P0 closeout — claim-conversion normal form (admission gate)

Commit `7923014`. Module `src/governor/normal_form.py` + `tests/test_normal_form.py`
(14 tests). Theory frozen in
`~/git/papers/working/tooltheory/admission-gate-claim-conversion-normal-form.md`.

## What it does
- Classifies a `ClaimManifest` into the four-state `ClassificationResult`:
  **`Candidate | Quarantined(reason) | Admitted(scope) | Refused(reason)`**.
  Pure, total, refusal-native; closed refusal vocabulary.
- Refuses **unlicensed conversion between epistemic species** (`Formal | ModelBound |
  Observed | Testimonial | Normative | Stipulated`). Canonical refusal:
  `formal_bound_to_world_without_model_fidelity` (Formal ⊬ world without a binding).
- Carries the **constitutivity axis** (`kind_claim`, `instrument_role`): refuses an
  allocating/enforcing instrument *presented as* neutral measurement, and a
  constructed/hybrid kind *presented as* stable. It **records the assertion, does not
  adjudicate** the kind.
- **The leash, baked in:** `fail_closed` at **reliance**, `quarantine` at
  **exploration/naming** (the default). Same finding → `Quarantined` at discovery,
  `Refused` at reliance. **Only `Admitted` may promote.** This is what stops the gate
  from becoming paper-Claude-with-a-badge (over-refusing at discovery on a match).

## What it explicitly does NOT do
- **Does not decide truth.** Only whether an epistemic *promotion* is licensed.
- **Not wired into the promotion path.** It does NOT touch
  `evaluate_promotion_from_evidence` / `derive_in_bounds`. Named the plug point,
  did not cross it — P0 has not earned runtime authority.
- **No performativity clock.** The constitutivity-in-time / Goodhart layer is
  name-early only; not built (it would be the seventh wire).
- **Not a policy language / not a theorem prover.** No plugins, no reflection, no
  self-amendment. It must not metastasize into policy evaluation.
- **Not sovereign.** It is a leashed checker, imported by nothing yet.

## Future plug point (named, not built)
```
receipt / witness material
  -> normal_form.classify(...)
  -> Candidate | Quarantined | Admitted | Refused
  -> ONLY Admitted may later feed reliance
       (conceptually: before evaluate_promotion_from_evidence / derive_in_bounds)
```

## Next real build (named, not authorized here)
A **read-only shadow pass** against existing promotion evidence: classify real
promotion-evidence through `normal_form` and *report* what would be quarantined/
refused, with **no effect on decisions**. That is the move that would create the
witness P0 correctly does not yet have. Build only on a fresh go.

## Verification
- P0 tests: **`governor verify-run` receipt `8ba5b6f1…`** — `pass`,
  `exit_observed=True`, `exit_source=child_exit`, `masked_risk=False` (receipt is in
  the gitignored `.governor/verify_receipts/`; id cited here as the durable pointer).
- Full suite: **15960 passed, 62 skipped, exit 0** (= prior 15946 + the 14 P0 tests;
  bare run, exit code observed). Additive isolated module: imported by nothing,
  modifies no existing source — confirmed green rather than asserted.

## Epistemic status (the typing the whole arc fixed)
`Normative<consistent-with-declared-spec>`, **not** `Observed<right>`. Green proves
consistency with the spec, not that the design is correct. The only witness is the
gate doing real work in the promotion path later — which has not happened. The one
test that failed first was the gate catching a conflated reason-class in the
*fixture*; fixed the fixture, not the gate — the apparatus corrected its author
without drama, which is better evidence of teeth than the green suite.

## Naming
Not a "calculus" (retired live-surface vocab, `docs/constellation-zoning.md`).
"Admission Calculus" = `quarantined_alias` (scratch/historical OK; canonical/title
blocked; operator may override the declared order).
