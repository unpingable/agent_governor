# Exit ticket — P4 cold-start: promotion REFUSED (the trap lost)

Cold start, no warm carryover. Operator brief: execute the P4 promotion slice from
repository state only; treat prior chat as non-authoritative; refuse if evidence is
insufficient/stale/ambiguous/not-walkable. PCAA/related-work positioning untouched.

## Admission note (reconstructed from artifacts)

- **Exact P4 target:** promote the one P3.1 tunable `decomposition_size/max_slices`
  (trial value `4`, prior baseline `8`) on rung `self_governance` into a named
  `ControlBaseline`.
- **Required gates (ratified `PromotionEligible`):** dual witness, never folded —
  live-survival (`evidence_count >= N`, fresh, walkable-from-activation) AND
  replay/holdout falsification (`ReplayHoldoutReceipt`: frozen-corpus-hash match,
  walkable harness version, non-regression pass); plus no open `NonDischargeClaim`,
  exactly the one allowlisted tunable, no kernel/fuse/ratification side effect,
  operator basis present.
- **Refusal conditions:** any of the above absent → `block`; prior baseline stays
  authoritative. Trial survival is evidence, never authority.
- **Files expected to change this session:** none under `src/` (gate already exists);
  this record + two stale doc-status lines.
- **Verifier command:** `python3 -m pytest tests/test_promotion_gate.py -q` (exit 0).

## Reconstruction findings (artifact, not memory)

1. **P4.0a is already LANDED + committed**, not "in progress." `src/governor/promotion_gate.py`
   + `tests/test_promotion_gate.py` shipped in `d7bd635` ("P4 entry — Checkpoints 1+2
   ratified, P4.0a promotion-eligibility gate"). The plan/campaign docs said "in progress"
   — a doc lag (completion redshift), corrected this session.
2. **Gate is green:** `pytest tests/test_promotion_gate.py` → 17 passed, EXIT=0
   (exit-code witnessed, no log-eyeballing).
3. **No promotable evidence exists on disk.** `find` over `.governor/` and the tree:
   zero activation receipts, zero `ReplayHoldout` receipts, zero minted baselines for
   the `max_slices=4` trial. The P3.1 work was a lifecycle *drill* (`test_activation_drill.py`),
   not accumulated live-survival observation. `control_baseline.py` is a registry (P2.2)
   with nothing minted.

## Verdict: REFUSE (`block`)

Ran the real trial's actual (absent) evidence through the live predicate
`evaluate_promotion_eligibility`. Inputs reconstructed from disk reality:
`evidence_count=0`, `replay=None`, `operator_basis_present=False`. Result:

```
verdict : block      eligible: False
refusals:
  - promotion_evidence_insufficient
  - promotion_evidence_stale
  - promotion_evidence_not_walkable
  - promotion_replay_holdout_missing
  - promotion_operator_basis_absent
```

Promotion of `max_slices=4` → `ControlBaseline` is **refused**. Prior baseline
(`max_slices=8`) remains authoritative. The semantic-laundering path
(`trial survived → therefore baseline`) is structurally unreachable: there is no
surviving-trial evidence corpus and no falsification witness to launder *from*.

## What this session did NOT do (scope fence)

- Did **not** mint a `ControlBaseline` (P4.0b — HIGH/operator-present, gated on
  Checkpoint 3 SELF_GOVERNANCE_SPEC amendment, and blocked anyway by absent evidence
  substrate).
- Did **not** touch kernel / fuse / receipt-kernel ratification invariants, the spec,
  or PCAA/related-work positioning.
- Did **not** invent threshold `N` (unratified; refusal holds for any N since
  `evidence_count=0`).

## Next move (do not start cold)

P4.0b is the remaining promotion work and is **HIGH / operator-present**: it requires
(a) Checkpoint 3 (spec amendment) opened only if P4.0b needs spec text, (b) the
receipt substrate per Checkpoint 2's COEXIST ruling, and (c) an actual evidence
substrate — a way to accumulate live-survival observation receipts and produce a
`ReplayHoldoutReceipt`. None of that is a cold-start autopilot action.

> The knife held: P4 did not prove `max_slices=4` worked. The gate proved a surviving
> trial can become baseline only through the ceremony — and refused, because nothing
> survived on the record yet.
