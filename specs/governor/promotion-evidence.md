# Promotion evidence substrate (P4.0b-prep)

Status: **landed** (model + tests), 2026-06-14. Module: `src/governor/promotion_evidence.py`.
Tests: `tests/test_promotion_evidence.py`. Composes with the P4.0a gate
(`src/governor/promotion_gate.py`), which is **untouched**.

## Why this exists

The P4.0a gate is pure and honest but *trusts* the booleans a caller hands it:
`walkable_from_activation`, `fresh`, `operator_basis_present`, and a raw
`evidence_count`. Correct for a gate ("witnesses expose; policy decides") — but it
means the gate can only ever **refuse** until something *produces* those facts from
real receipts. The cold-start audit (2026-06-14) proved exactly this: the real
`max_slices=4` trial refused with `evidence_count=0` because no evidence substrate
existed. This module is the substrate.

> The move is **checked, not typed.** Walkability is a hash chain that binds or does
> not — not a flag a caller asserts (NLAI). Freshness is `clock_witness.elapsed_ns`
> over compatible monotonic readings, which *refuses* incompatible bases rather than
> subtracting confidently. Evidence count is the number of observations that bind,
> are in-bounds, and are fresh — not a number a caller picks.

## Receipt types

| Type | Role | Key fields |
|---|---|---|
| `ActivationReceipt` | chain root (P3.1 activation) | trial_id, tunable_name, trial_value, prior_baseline_value, activated_at (`MonotonicReading`); `content_hash` (content-addressed) |
| `LiveSurvivalObservationReceipt` | "did it survive reality?" | trial_id, observation_id, observed_at (`MonotonicReading`), in_bounds, disqualifying_events, **activation_receipt_hash** (binding claim) |
| `ReplayHoldoutReceipt` | "does promotion avoid known regression?" | trial_id, passed, corpus_hash, frozen_corpus_hash, harness_version, comparator_baseline_id, falsification_basis |
| `OperatorBasisReceipt` | the classed authority act | trial_id, operator_actor, promotion_basis, scope, **explicitly_not_auto_baseline** |

`PromotionCandidate` (trial_id, tunable_name, trial_value) + `PromotionEvidenceBundle`
(the four receipt groups + `required_count` N + `evaluation_reading` + horizon +
allowed surface + open-claim ids + side-effect flag) are the inputs.

## Pipeline

```
PromotionEvidenceBundle --assemble_promotion_inputs--> PromotionInputs
                                                            |
                                       evaluate_promotion_eligibility (P4.0a)
                                                            |
                          evaluate_promotion_from_evidence --> PromotionEligibility
```

`assemble_promotion_inputs` walks the bundle into a faithfully-degraded
`PromotionInputs` (walkable/fresh/count all **computed**). `evaluate_promotion_from_evidence`
runs the gate on those inputs and unions the one evidence-native refusal.

## Validity predicate (what makes evidence promotable)

```
promotion evidence is valid iff:
  activation exists AND matches the candidate (trial_id, tunable, value)
  every observation binds: obs.activation_receipt_hash == activation.content_hash  (computed)
  every observation is for the candidate's trial                                   (else not walkable)
  count of {bound, in-bounds, fresh} observations  >= N                            (N supplied, not ratified)
  freshness computed on a compatible monotonic basis (incompatible -> not fresh)
  replay/holdout exists, is for this trial, passes, corpus-hash matches, harness walkable
  operator basis exists, is for this trial, and explicitly_not_auto_baseline is True
```

The two live/replay witnesses stay **never folded** end-to-end (a perfect replay
cannot rescue missing live evidence, and vice versa).

## Refusals (operator-named, mapped)

| Evidence condition | Refusal kind | Source |
|---|---|---|
| missing activation | `promotion_evidence_not_walkable` | gate (computed) |
| observation without activation | `promotion_evidence_not_walkable` | gate (computed) |
| observation for wrong trial | `promotion_evidence_not_walkable` | gate (computed) |
| orphan binding hash (lied-about) | `promotion_evidence_not_walkable` | gate (computed) |
| zero in-bounds observations | `promotion_evidence_insufficient` | gate (computed) |
| stale / incompatible-clock observation | `promotion_evidence_stale` | gate (computed) |
| missing / wrong-trial replay holdout | `promotion_replay_holdout_missing` | gate (computed) |
| failed replay holdout | `promotion_replay_holdout_failed` | gate (computed) |
| missing / wrong-trial operator basis | `promotion_operator_basis_absent` | gate (computed) |
| **operator basis claims auto-promote** | `promotion_operator_basis_claims_auto` | **evidence (new)** |

Only one new refusal kind — the red-line fence the gate cannot express: an operator
basis asserting auto-promotion is not a valid basis. Promotion stays a separate,
classed act.

## Scope fences (P4.0b-prep)

- Mints no `ControlBaseline`; promotes nothing; persists nothing (no IO).
- Ratifies no threshold `N` — `required_count` is a supplied input.
- Does not weaken `promotion_gate`; the gate is imported, not modified.
- Cold-start preserved: empty bundle → `evidence_count=0` → refused (insufficient +
  not-walkable + replay-missing + operator-absent), and **not** stale (nothing to age).

## Storage (P4.0c — first producer landed)

`src/governor/promotion_evidence_store.py` persists the chain root only:

```
<root>/promotion_evidence/activations/<trial_key>.json    (trial_key = sha256(trial_id))
```

`ActivationReceiptStore.put/get` — atomic temp+rename writes, integrity-checked
loads. Each file carries the receipt's `content_hash`; on load it is recomputed from
the fields and compared (`ActivationReceiptTamperError` on mismatch), and the stored
`trial_id` is checked against the requested key (swap guard). A clean miss returns
`None` (the walk layer treats a missing activation as not-walkable). The self-hash
refuses a file whose declared hash disagrees with its content; a *fully* rewritten
but internally-consistent activation is caught downstream (its hash changes, so
observations bound to the original no longer walk). Tests:
`tests/test_promotion_evidence_store.py`.

## Still ahead (not P4.0c)

The remaining producers: a live-survival observation emitter, a `ReplayHoldoutReceipt`
producer wired to the C1 `REPLAY_HARNESS`, and `OperatorBasisReceipt` capture. Then
P4.0b proper (mint `ControlBaseline` via the supersession ceremony) — HIGH /
operator-present, gated on Checkpoint 3.
