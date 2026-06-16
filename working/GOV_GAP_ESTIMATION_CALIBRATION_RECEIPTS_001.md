# GOV_GAP_ESTIMATION_CALIBRATION_RECEIPTS_001

## Title

Three-station estimation receipts where **calibration, not confidence, is the
execution authority** — the estimator earns the right to bind execution by
reconciliation history, not by feeling sure.

## Status

**Candidate — captured, NOT ratified, NOT scheduled, NOT part of P4.0b.** Filed as a
handle so the converged design survives. Sibling of (not part of)
`GOV_GAP_PLAN_DECOMPOSITION_PROTOCOL_001`: that gap governs *jurisdiction and debt* on
the decomposition seam; this one governs *estimation and calibration* on the same seam.
(Operator + ChatGPT + Claude, converged 2026-06-15.)

## The spine (the kernel line)

> Pre-decomposition estimate authorizes **decomposition**. Slice estimate authorizes
> **execution** only when backed by earned **calibration** for its risk class.
> Reconciliation updates **calibration** only with *attributed* misses or hits, and may
> neither bless a bad estimate nor scar an estimate for unrelated failure.

The circuit (the wire between the stations is the point — three disconnected receipts
were the earlier draft's bug):

```
request
  → AdmissionEstimateReceipt        gates planning only (coarse, explicitly weak)
  → decompose
  → SliceEstimateReceipt            gates execution ONLY via CalibrationStateReceipt
  → execute
  → EstimateReconciliationReceipt   compares estimate vs actuals, attributed
  → CalibrationUpdateReceipt / ScarReceipt
  → feeds the NEXT slice gate        ← closes the loop
```

## The three receipts

1. **AdmissionEstimateReceipt** (pre-decomposition). Answers *"is this admissible to
   plan?"* — blast radius, suspected complexity class, whether decomposition is required,
   risk flags, a `re_admit_if_exceeds` ceiling. **Coarse and explicitly weak.** It does
   NOT become execution authority (the "first guess becomes the schedule" pathology).
2. **SliceEstimateReceipt** (post-decomposition). Per-slice: risk_class, expected files
   touched, verifier cost, rollback difficulty, coupling. **The authority-bearing field
   is `calibration_basis.status == eligible_to_bind`, NOT `confidence`.** `confidence` is
   carried but `confidence_role: "advisory"`.
3. **EstimateReconciliationReceipt** (post-execution). Compares pre-decomp vs decomposed
   vs actual; emits calibration update or scar; **cannot retroactively bless a bad
   estimate.**

## Two load-bearing doctrine moves

**A. Confidence is telemetry; calibration is authority.**
`"confidence": "high"` is a phenomenological stamp — the estimator can be confidently
wrong (this repo's `confidence ≠ fidelity` scar, one layer up). What may bind execution
is the estimator's **calibration for this risk class** — its reconciliation track record
(`within_file_delta_1_rate`, `recent_miss_rate`, `reconciliation_count` →
`eligible_to_bind`). "I feel this is a 3-file slice" cannot bind; "this estimator landed
within ±1 file on low-risk slices across 200 reconciliations" can. Calibration is a
*diachronic* state reconciliation builds; confidence is a *synchronic* stamp. Gate on the
diachronic state.

**B. No retroactive blessing — and no false scars (attribution, both directions).**
`wrong estimate → recorded miss → calibration scar`, never `good outcome → estimate was
fine actually` (post-validation laundering in a project-manager hat — the same shape as
the P4 fence: *later validation does not authorize the earlier act*). Mirror: an estimate
must NOT be scarred for a miss that wasn't its fault, or calibration becomes
garbage-in/garbage-out. Closed attribution vocabulary:

```
estimation_error · decomposition_error · execution_error · operator_scope_change
· environment_change · dependency_drift · verifier_instability · preexisting_repo_inconsistency
```

Only `estimation_error` (and `decomposition_error`, scoped) scar the estimator.

**C. The admission ceiling is a refusal trigger, not a bound.**
`re_admit_if_exceeds` does NOT hard-truncate the work and is NOT ignorable. A breach is a
categorical event → `AdmissionEstimateExceeded → re-admit` (the blast-radius guess was
wrong; back to the gate). A weak first guess that silently caps execution IS binding
execution — the pathology the pre-decomp estimate exists to avoid.

## The live residue (the swamp — named, not solved)

The circuit is sound; the open adversarial seam is **calibration-history farming**:
earning `eligible_to_bind` *pre-earned* by farming trivial slices in a risk class, then
spending that status on a slice that is nominally the same class but actually harder.

This is **not a new failure class** — it is Goodhart-on-the-grader, which the repo already
has doctrine for. The defense is to *reuse* it, not invent:
- **Canary/holdout** (`SELF_GOVERNANCE_SPEC.md` § Canary Rotation): calibration earned on a
  farmed/stale distribution must not bind a shifted one; a held-out reconciliation slice
  the estimator can't see.
- **Evidence walkability + freshness** (P4 promotion-evidence discipline): each
  reconciliation that feeds calibration must be **walkable to a real executed slice**, not
  synthesizable — same as `evidence_count` only moves off zero through receipts that bind,
  are in-bounds, and are fresh.

**Sharpest point (the gate behind the gate):** binding keys on `risk_class`, so farming
reduces to **misclassification** — declaring a hard slice as a class the estimator is
calibrated on. The real gate behind the calibration gate is **risk-class integrity**:
`risk_class` must be *checked*, not self-asserted (allowlist-authority — is the slice
actually in the class it claims?). Calibration-as-authority is only as sound as
risk-class assignment is honest. Resolve risk-class integrity before trusting
`eligible_to_bind` to bind anything.

## Non-goals

- NOT a PM system / time-tracker. Docs/spec first; maybe a checker later; no runtime PM
  engine (inherits `PLAN_DECOMPOSITION_PROTOCOL` non-goals).
- NOT P4.0b. P4.0b is the promotion mint; this is the estimation/calibration surface. Do
  not let it bleed into the mint slice.
- NOT the full receipt schemas in v1 — they fall out of the spine once risk-class
  integrity and the farming defense are settled.

## Cross-links

- `working/GOV_GAP_PLAN_DECOMPOSITION_PROTOCOL_001.md` — sibling (jurisdiction/debt on the
  same seam); `DebtLedger` / `NonDischargeClaim` substrate.
- `specs/core/SELF_GOVERNANCE_SPEC.md` § Canary Rotation, § No Epistemic Laundering — the
  farming defense and the no-blessing rule are the same doctrine, applied to calibration.
- `specs/governor/promotion-evidence.md` — evidence walkability/freshness, reused for
  reconciliation-feeds-calibration integrity.
