# Golden corpus — the decision contract

**This corpus, not the Python source, is the kernel contract.** (Lean is above
both.) Each file in `corpus/` is a frozen `input → verdict` pair for the Agent
Governor cooked-context decision chain (standing → wicket → LA grant → LA
consume). `tests/test_corpus_contract.py` runs the live chain for each input and
asserts the output matches the frozen verdict. Drift (the Python changes a
verdict) breaks the test — updating a golden is then a **deliberate, reviewed**
act, never a silent regeneration.

Why frozen, not generated: a regenerated corpus can't catch drift — it would
just re-record whatever the code now does. The contract has to be the thing that
*doesn't move* when the implementation does. This is the socket-cut prep
(`memory/rust_kernel_port_ruling`): the eventual Rust decision kernel becomes a
*frozen-contract fill* — it must reproduce these verdicts byte-for-byte on these
inputs, or the dual-engine divergence gets a receipt, not a shrug.

## 30-second specimen

```bash
python3 -m pytest tests/test_corpus_contract.py -q
```

Each `corpus/NN-*.json`:

```json
{
  "schema": "agent_governor.corpus.v1",
  "case": "valid-passes",
  "demo_role": "valid_passes",
  "input":  { "scenario": "all-green", "origin_mode": "drill", ... },
  "expected_verdict": {
    "outcome": "consumed", "refusal_kind": null, "refusing_seam": null,
    "effect_count": 1, "consumed": true, "operational": false,
    "proposal_packet_present": true
  }
}
```

The verdict freezes the **decision**, not the artifacts: `receipt_ids` are
content-addressed (hash-derived) and environment-shaped, so they are NOT part of
the contract. `outcome` / `refusal_kind` / `refusing_seam` (closed vocabularies),
`effect_count` (linearity), and the `consumed` / `operational` /
`proposal_packet_present` booleans ARE.

## The cases

| File | case | demo_role | verdict |
| ---- | ---- | --------- | ------- |
| `01-valid-passes` | all-green | valid_passes | consumed, effect=1 |
| `02-no-standing-refused` | no-standing | custody_refusal | refused: standing_required @ standing_seam |
| `03-standing-unverifiable-refused` | standing-expired | custody_refusal | refused: standing_expired @ standing_seam |
| `04-admission-denied-refused` | wicket-denied | custody_refusal | refused: admission_denied @ la_seam |
| `05-gap-accounted` | wicket-gap-accounted | — | gap_accounted, effect=1 (proceeds under cited gap) |
| `06-replay-refused` | replay-budget | custody_refusal | refused: already_consumed @ la_seam, effect stays 1 |
| `07-synthetic-evidence-fenced` | all-green / synthetic origin | synthetic_fenced | consumed but **operational=false** |

## Two corpus-wide invariants the contract test pins

1. **The simulated-evidence fence (Wall 1).** Every case here runs under a
   non-`observed` origin (drill / synthetic), so `operational` is `false` in
   **all** of them — even the three that mechanically consume (01, 05, 07). No
   simulated-origin chain is ever operational. This is the "synthetic evidence
   fenced" property as an invariant, not a single case: running this corpus (or
   the public demo) cannot mint a spendable/operational receipt.
2. **Closed-world coverage.** Every `SUPPORTED_SCENARIO` in `drill_runner` has a
   frozen corpus entry. A new decision scenario cannot ship without freezing its
   verdict here — the contract grows by ceremony, not by accretion.

## Known gap — the demo's hero specimen is NOT here yet

The launch plan (`working/launch-plan-2026-06-11.md`) designates the **two-clock
temporal lapse** as the demo's single best specimen: standing observed at t=40,
horizon expires t=50, spend at t=51 — naive auth says yes, custody says no, and
the receipt shows *both clocks and the gap*. **No scenario produces that receipt
shape today** (verified: there are no `standing_observed_at` / `capacity_committed_at`
/ `clock_basis` / `gap` fields anywhere in `drill_runner`). Case 03 is the
*unverifiable-standing* refusal (the digest doesn't resolve), which is a
different refusal class — it is honestly labeled as such, not dressed up as the
temporal case.

Building the temporal specimen is the **next W1 slice** (see
`working/candidate-temporal-lapse-specimen.md`): a new finding+context fixture
carrying two clocks and a horizon, a receipt/proposal shape that surfaces the
gap, and a typed refusal (`standing_before_spendability_not_bounded`, per
`docs/constellation-zoning.md` §Standing). It touches the standing-seam receipt
shape and the refusal vocabulary, so it is its own deliberate slice, not folded
into this freeze.

## Cross-references

- `docs/constellation-wire-plan.md` — W1 sequence; the corpus is item 2.
- `docs/constellation-zoning.md` §Evidence classes (the fence), §Standing (the
  two-clock temporal shape the hero specimen needs).
- `memory/rust_kernel_port_ruling` — corpus-is-the-contract; socket-cut.
