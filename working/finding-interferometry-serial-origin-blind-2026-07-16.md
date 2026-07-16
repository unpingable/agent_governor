# Finding: serial interferometry confidence is origin-blind

**Filed:** 2026-07-16
**Status:** FINDING, unruled. Names a defect class; authorizes no edit.
**Formal instrument:** `~/git/skunkworks/formalization/Calculi/Scratch/JudgmentOrientation.lean`
(`OrientationLaundering.source_blind_relay_amplifies_orientation`,
`orientation_laundering_violates_origin_bound`) — **[scratch] tier: recon,
cannot ratify** (per lean citation tiers). The countermodel names the class;
the AG evidence below stands on its own.

## Evidence

`src/governor/interferometry.py`:

- `run_serial` (:366) — deliberation chain: step N's prompt embeds step N-1's
  response verbatim and solicits agreement ("Where you agree, say so"). Every
  claim extracted at step N is causally downstream of step 0. One origin,
  N relabeled deliveries.
- `align_claims` / `compute_signals` (:181, :280) — shared between parallel
  and serial modes with **no mode discrimination**. `confidence =
  len(sources) / model_count` (:231) counts each chain echo as an independent
  source.
- `promote_to_ledger` (:470) — mode-blind: serial-mode `shared` claims enter
  the epistemic ledger as `Provenance.DERIVED` at the laundered confidence.
  A claim seeded by model A and echoed by three downstream models promotes at
  confidence 1.0.

The defect is exactly the orientation-laundering shape: relabeled relays of
one origin counted as fresh corroborative increments. Parallel mode is the
independent-origins case and is not implicated. The anti-cheat machinery that
would catch this (`independence.py` method signatures, `sybil.py` Neff /
per-origin budgets) sits at the **quorum** seam and is never consulted on the
interferometry promotion path.

## Severity

LATENT with a live edge. Interferometry is candidate substrate (user-invoked
CLI, not auto-firing) and promotion requires an explicit
`governor interferometry accept --shared`. But nothing at the accept boundary
discloses that serial-mode confidence is chain-echo, not corroboration — the
operator invoking accept on a serial run is being shown a laundered number.
Same meta-shape as the 2026-07-15 sweep findings: safe defaults, disciplined
callers, expressible violation.

## Options (drafted, none authorized)

1. **Discount at source** — serial mode computes confidence from round-0
   sources only, or caps `len(sources)` contribution at 1 per chain
   (accumulator-side repair: refuse to count, not to remember — see
   `JudgmentOrientationAttribution.AccumulatorRepair`).
2. **Type the split** — serial runs promote at a distinct provenance/floor
   (chain-agreement is orientation, not corroboration); parallel unchanged.
3. **Disclose at the boundary** — `accept` on serial runs surfaces
   `origin_count=1` next to confidence; number unchanged, laundering named.
4. **Rule it acceptable** and record at the promote boundary that serial
   confidence measures chain persuasiveness, not independence.

## Stop lines

- No edit to `interferometry.py`, alignment, or promotion on the strength of
  this record.
- The scratch-tier Lean names the class; it does not adjudicate the fix.
