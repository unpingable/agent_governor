# Checkpoint 2 — convergence_tuning disposition (RESOLVED 2026-06-13, operator fiat)

P4 entry HIGH checkpoint #2. **Decision: coexist, with a one-way external bridge.**
Recorded by operator ruling 2026-06-13 (from a read of `annealing.py` +
`convergence_tuning.py`). This doc is the disposition record; it authorizes **no build of
P4.0b** (no ControlBaseline mint, no PromotionReceipt, no supersession). Cold session
tomorrow.

## Decision

> `convergence_tuning` and `annealing` **coexist**, connected by a **one-way external
> adapter/bridge**.
>
> - `convergence_tuning` remains a **domain-specific proposal/evidence producer**.
> - `annealing` remains the **generic custody substrate** for tunable authority changes.
> - `annealing.py` **must never import** `convergence_tuning.py`.
> - `PromotionReceipt` and `ControlBaseline` mint from **annealing/promotion custody**,
>   NOT from `TuningProposal` or `TuningApply`.
> - A separate bridge may translate an **admissible** `TuningProposal` into an
>   `AnnealingDelta` **only when** it maps onto an allowlisted tunable surface and
>   supplies baseline, expiry, rollback, source observations, and human-approval custody.

## Why (grounded in the two files)

- `annealing.py` is already the **generic candidate-delta custody substrate**: closed
  tunable allowlist (lines 13–15, 41), `AnnealingDelta` requires a `ControlBaseline`
  reference + expiry + rollback trigger + forced human approval (lines 20, 215–253),
  off-allowlist construction refused (`REFUSE_TARGET_OFF_ALLOWLIST`, line 90), **no apply
  path**, and the import pin in its own module docstring: *"generic annealing must not
  depend on a domain module"* (lines 26–30). Verified: no `convergence_tuning` import in
  the module (pin holds structurally, not just by comment).
- `convergence_tuning.py` is a **domain auto-tuner**: offline system identification over
  convergence traces emitting `TuningProposal` (line 752); never mutates enforcement
  without human approval. Good citizen, wrong layer for authority custody.
- `TuningApply` (line 803) is **provenance for applying a proposal**, NOT a
  `ControlBaseline` supersession witness. "Apply record" must not cosplay as promotion
  receipt.

The shape:

```text
convergence_tuning.TuningProposal
  -> external bridge (imports BOTH; lives OUTSIDE both modules)
  -> annealing.AnnealingDelta        (only if admissible + allowlisted + custody-complete)
  -> trial activation
  -> promotion gate (promotion_gate.py, P4.0a — landed)
  -> ControlBaseline + PromotionReceipt   (P4.0b — NOT built)
```

Bridge home (when built): `src/governor/tuning_proposal_bridge.py` (doctrine-correct
name). It may import both; `annealing.py` imports neither the domain module nor its
private semantics. **The bridge is a translator at the border, not a straw that lets the
domain module sip from the authority substrate.** An "adapter" that reversed the
dependency would defeat the pin.

## DispositionReceipt (the record)

```text
DispositionReceipt:
  subject: convergence_tuning
  verdict: coexist_with_external_adapter
  ratified_by: operator_fiat (2026-06-13)
  not_substrate_for:
    - ControlBaseline
    - PromotionReceipt
    - supersession authority
  may_produce:
    - TuningProposal            # convergence_tuning.py:752
    - evidence summaries
    - source_observation_ids
  adapter_direction:
    convergence_tuning.TuningProposal -> annealing.AnnealingDelta   # one-way only
  adapter_admission_preconditions:   # ALL required before a TuningProposal may cross
    - maps onto an allowlisted tunable surface
    - supplies baseline
    - supplies expiry
    - supplies rollback
    - supplies source observations
    - supplies human-approval custody
  forbidden:
    - annealing imports convergence_tuning          # pin: annealing.py:26-30
    - TuningApply  treated as PromotionReceipt       # apply-record != promotion witness
    - TuningProposal treated as ControlBaseline      # proposal != baseline
```

## The likely future laundering path (guardrail — say it out loud)

> **`TuningApply` is NOT `PromotionReceipt`. `TuningProposal` is NOT `ControlBaseline`.**

This is the path a tired model will absolutely try, because it looks so reasonable (the
shapes are rich and adjacent). It is an instance of the `weak_property_strong_property`
enemy shape: *apply-record → promotion authority*, *proposal → baseline*. Refuse it at the
bridge by construction (the bridge mints an `AnnealingDelta`, never a baseline or
promotion receipt); the promotion receipt/baseline mint only out of promotion custody on
an eligible `evaluate_promotion_eligibility` verdict.

## State after this checkpoint

- Checkpoint 1 RESOLVED (dual gate). Checkpoint 2 RESOLVED (this doc).
- Checkpoint 3 (SELF_GOVERNANCE_SPEC amendment) OPEN — open it tomorrow **only if** P4.0b
  requires spec-text amendment at that point; otherwise start P4.0b refusal tests /
  PromotionReceipt substrate.
- **STOP before P4.0b.** No "just inspect P4.0b a little" — that is how the ghost
  government gets zoning approval. Pin and resume cold tomorrow.

## Tomorrow's clean (cold) entry

```text
1. cold-read pins (.governor/loop.json re_entry_probes)
2. confirm Checkpoint 1 + Checkpoint 2 resolved (this doc + crosswalk + P4 plan)
3. open Checkpoint 3 only if P4.0b requires spec-text amendment now
4. otherwise start P4.0b: tuning_proposal_bridge.py (one-way) + PromotionReceipt
   substrate + refusal tests, on top of promotion_gate.py (P4.0a, landed green)
```
