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

## Observation admissibility (P4.0d — `in_bounds` is derived, landed)

`src/governor/observation_admissibility.py` defines what counts as in-bounds, so the
live-survival witness cannot ride a writer-stamped vibe field.

> bad: `in_bounds: true` (the writer says so) · good:
> `in_bounds = derive_in_bounds(facts, bound)` (the evaluator decides)

- `ObservationFacts` — raw facts (trial_id, clock reading, `(metric, value)` pairs,
  disqualifying events). **No `in_bounds` field** — there is no slot to stamp (the
  headline refusal test: constructing with `in_bounds=` raises `TypeError`).
- `SurvivalBound` — the evaluable form of the trial's rollback trigger
  (`metric`, `trip_comparator` ∈ {gt,ge,lt,le}, `threshold`); trips when
  `observed <cmp> threshold`. Promotion-path-native (does **not** import
  `convergence_tuning` — ground rule 6); a future `tuning_proposal_bridge` may
  translate a `RollbackTrigger` into it with custody.
- `derive_in_bounds(facts, bound, expected_basis=None)` — pure: in-bounds requires no
  disqualifying events, the bound's metric actually observed (no survival claim on an
  unmeasured metric), the trigger not tripped, and (optionally) a compatible clock
  basis. All failing reasons surface (never collapse). Tests:
  `tests/test_observation_admissibility.py`.

P4.0d is admissibility only: no producer, no receipt, no store; `promotion_evidence`'s
`evidence_count` derivation is untouched.

## Observation producer/store (P4.0e — landed; the first slice that can lift `evidence_count` off zero)

`ObservationReceiptStore` (`promotion_evidence_store.py`) persists live-survival
observations under `<root>/promotion_evidence/observations/<trial_key>/<observation_id>.json`.

**Producer-derived is not producer-trusted.** `put()` derives `in_bounds` via
`derive_in_bounds(facts, bound)` and persists the *inputs* (facts + bound + activation
binding) plus the derived conclusion. The `content_hash` covers **inputs only**. On
`load_for_trial()` the evaluator: (1) recomputes `content_hash` over the inputs →
refuses a mismatch (tampered facts); (2) checks the stored `trial_id` (swap guard); (3)
**re-derives `in_bounds` from the stored facts+bound and refuses if it disagrees with
the stored conclusion** — so a tripped observation re-stamped `in_bounds: true` is
caught even though editing only the conclusion leaves `content_hash` intact. It then
emits plain `LiveSurvivalObservationReceipt`s (carrying the *re-derived* `in_bounds`)
for the existing walk/assembler, which independently enforces activation binding, trial
match, and freshness. `evidence_count` therefore moves off zero **only** through
observations that are tamper-clean, walked, fresh, and derived-in-bounds. Tests:
`tests/test_promotion_evidence_store.py` (P4.0e block) — incl. the re-stamp refusal and
the end-to-end "evidence_count off zero" path on synthetic fixtures (not the real
`max_slices=4` trial, which still has no evidence).

## Replay/holdout producer (P4.0f — landed; the second witness)

`replay_holdout.py` (pure) + `ReplayHoldoutReceiptStore` (`promotion_evidence_store.py`).
Answers exactly one question: *did this trial/candidate non-regress against this prior
baseline on this frozen corpus, using this witnessed harness run?*

**Design call resolved: C1 `REPLAY_HARNESS` is a semantic mismatch, not wrapped.** The
C1 harness (`signals/replay_harness.py`) replays *signal derivations* under alternative
thresholds (drift statistics) — not trial-vs-baseline non-regression over a frozen
corpus. So P4.0f neither wraps C1 nor invents a second replay semantics: it is a
**receipting/attestation layer** that records facts about a witnessed run (harness named
by `replay_harness_id`/`version`) and binds them. Live invocation of a real
non-regression harness is later wiring.

- `ReplayHoldoutFacts` — raw facts (trial/candidate/comparator-baseline bindings, corpus
  id + hash + frozen hash, monotonic `started_at`/`completed_at` with `duration_ns()` via
  the licensed subtraction, `child_exit`/`exit_observed`, `raw_result_hash`, and the
  harness's own `result_non_regression`). No trusted verdict field.
- `derive_replay_verdict(facts)` — `non_regression_passed` requires all bindings, a
  frozen-and-matching corpus, observed+zero exit, and the harness pass; else `refused`
  with all reasons (closed vocab). The harness's pass is one gate, not the authority.
- `ReplayHoldoutReceiptStore.put/load_for_trial` — same trust boundary as observations:
  `content_hash` over inputs only; on load, recompute hash (tampered facts), check
  trial_id (swap), and **re-derive the verdict, refusing a disagreement** (a refused run
  re-stamped passed is caught). Emits the existing `promotion_evidence.ReplayHoldoutReceipt`
  (re-derived pass/fail) for the walk/assembler. A legitimately-refused run loads as
  `passed=False`; only integrity failures raise. Tests: `tests/test_replay_holdout.py`,
  incl. the re-stamp refusal and end-to-end gate plug-in (valid replay → eligible on
  synthetic fixtures; missing/failed → gate still refuses).

## Operator-basis producer (P4.0g — landed; the last producer)

`operator_basis.py` (pure) + `OperatorBasisReceiptStore`. Captures "a qualified operator
reviewed THIS bundle before THIS transition" without turning operator mood into evidence
and without ever becoming a promotion verdict.

`operator_basis_present` is **derived structurally**, never a detached bool (Lean:
`OperatorBasisGateInput.bare_bool_ignores_bundle`). `derive_operator_basis_present(facts,
consumed_bundle_hash, promote_reading, horizon)` requires: every binding present; the
operator's `reviewed_verdict == basis_reviewed` and not auto-claiming; **the reviewed
bundle equals the consumed bundle** (pre-state binding); the review clock compatible and
**strictly before** promote (post-attestation refused); and the review fresh within the
horizon. Closed refusal vocab.

**Consume-relative by design** (the one asymmetry): unlike `in_bounds`/replay-verdict
(facts-only), `operator_basis_present` cannot be derived without the consumed bundle +
promote clock — the Lean's consumer-relativity (`no_global_section_when_consumers_disagree`)
in the type. So `OperatorBasisReceiptStore.put` persists facts (integrity only) and
`load_for_trial(trial_id, *, consumed_bundle_hash, promote_reading, freshness_horizon_ns)`
runs the structural derivation, **emitting the existing simple
`promotion_evidence.OperatorBasisReceipt` only if it passes** — else `None` (gate sees
basis absent → refused). The detached `operator_basis_present=True` has no path: no
receipt comes out without a matching consumed bundle and an in-time, fresh review. The
deriver is the real gate; the assembler's bool is its shadow. `reviewed_verdict` is an
attested INPUT (in the content hash), so re-stamping it is a content tamper (caught by
integrity, not re-derivation — the honest difference from observations/replay). Tests:
`tests/test_operator_basis.py`. `promotion_gate.py` and `promotion_evidence.py` untouched.

## All three witnesses now have producers — next is the HIGH gate

The pipeline can now return `eligible` on real evidence (live survival + replay/holdout +
operator basis, all loaded + re-validated). The next step is **not** another producer:
it is **P4.0b** — mint `ControlBaseline` via the supersession ceremony — which is **HIGH /
operator-present**, gated on **Checkpoint 3** (SELF_GOVERNANCE_SPEC amendment). That line
is not crossed cold. Also still required before a *real* `max_slices=4` promotion: a
canonical "basis bundle hash" computation (P4.0g binds with opaque hashes; how the bundle
hash is computed is P4.0b wiring) and the freshness-window ops policy from the P4.0g spike
(operator-review window vs replay duration).
