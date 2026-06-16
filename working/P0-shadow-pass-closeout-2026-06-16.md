# P0 shadow pass — closeout (2026-06-16)

The read-only move named (and explicitly *not authorized*) at the foot of
`working/P0-normal-form-closeout-2026-06-15.md`: classify real promotion-evidence
through `normal_form` and **report** what would be quarantined/refused at the promotion
reliance point, **with no effect on decisions**. This is the behavioral witness P0
(`76497ab`) correctly did not yet have.

## What shipped (additive; imported by nothing yet, like `normal_form`)
- `src/governor/promotion_shadow.py` — projects each promotion-evidence receipt into a
  `normal_form.ClaimManifest` (structural species table), classifies beside the gate,
  returns a `ShadowReport` (`would_refuse` / `would_quarantine` / `shadow_errors`).
- `tests/test_promotion_shadow.py` — 12 tests, the five acceptance boundaries.
- Zero existing source modified.

## The projection table (the load-bearing distinction: projection, NOT evaluation)
Species is fixed by receipt **type**, not inferred from contents:

| receipt | species | why |
|---|---|---|
| `ActivationReceipt` | `OBSERVED` | a witnessed act occurred |
| `LiveSurvivalObservationReceipt` | `OBSERVED` | a witnessed in-bounds sample (freshness-required) |
| `ReplayHoldoutReceipt` | `OBSERVED` | a witnessed mechanical replay — **`is_proof=False`**, NOT presented as system safety (honest non-promotion) |
| `OperatorBasisReceipt` | `NORMATIVE` | valid under the operator's declared authority, not a world-fact |

The shadow judges only **legitimacy of the conversion**. Whether the evidence is good /
fresh / in-bounds / sufficient stays the gate's (`evaluate_promotion_from_evidence` /
`derive_in_bounds`). The operator-flagged hazard — "quietly turning the adapter into a
second evaluator" — is held off by construction: the shadow imports no write path and
**never calls the gate** (a passed-in eligibility is mirrored verbatim, never recomputed).

## Acceptance (five boundaries, all green)
1. **Alters nothing** — `decision_effect="none"` on report + every finding; passed-in
   gate eligibility mirrored verbatim and untouched; static test: source contains no
   `ControlBaselineStore` / `mint_promotion` / `operational_promote` / `.write(` /
   `open(` / `to_dict(`.
2. **Adapter failure is data, not a refusal** — a raising projector yields a
   `shadow_error` finding (`classification=None`), never an exception, never a promotion
   refusal; gate verdict untouched.
3. **Leash survives projection** — same overclaiming manifest → `QUARANTINED` under
   EXPLORATION, `REFUSED` under RELIANCE.
4. **Clean real-shaped bundle → all `ADMITTED`** — the licensed-conversion witness.
5. **Empty chamber → recorded `absent`, refuses nothing** — absence is the gate's to
   refuse, not the shadow's.

## Live specimen (real `.governor/`, empty chamber)
Discovery over a nonexistent trial → all four pieces `absent`; shadow `would_refuse=()`;
gate refusals mirrored verbatim (`promotion_evidence_insufficient`,
`…_not_walkable`, `…_replay_holdout_missing`, `…_operator_basis_absent`).
Write-surface (`control_baselines/`, `promotion_evidence/`) **absent before AND after** —
zero writes. The side-by-side reads: *the gate refuses absence; the shadow refuses
nothing.*

## Verification
- **Verifier receipt `ace79d36…`** — `pass`, `exit_observed=True`,
  `exit_source=child_exit`, `masked_risk=False` (`.governor/verify_receipts/`).
- Full suite **bare**: `15972 passed, 62 skipped, exit 0` (= 15960 + 12). Additive,
  imported by nothing — confirmed green, not asserted.

## Two-verdict
- **Cargo verdict: PASS.** 12 new tests, full suite green, exit 0 observed (not eyeballed).
- **Dogfood verdict: HELD.** Read-only by construction; the live specimen refused nothing
  and wrote nothing; the leash (exploration↔reliance) held through projection. No
  fail-open: an adapter error becomes observable data, not a silent pass.

## Reachability audit — the shadow falsified its own load-bearing hypothesis
The follow-on reachability audit (`working/P0-shadow-matrix-2026-06-16.md`) ran the shadow
over **every distinct promotion-evidence bundle shape** the suite contains. Result: across
all 11 shapes — including the 9 the gate refuses for domain reasons — **every present
receipt classifies `ADMITTED`**. The shadow refuses 0/11; the gate refuses 9/11. All eight
production-facing refusal rules are **unreachable** from any current AG promotion-evidence
shape (no receipt emits `MODEL_BOUND`/`TESTIMONIAL`, sets `kind_claim`/`instrument_role`,
or is marked `is_proof`; scope/freshness/consumer are always supplied by the adapter).

This is the strong outcome: the slice was a **reachability audit that falsified its own
load-bearing hypothesis** — that `normal_form` observes a live epistemic-conversion seam in
AG. It does not. On current shapes it restates doctrine over a charitably-shaped adapter and
returns a constant `ADMITTED`. This is *true, not a bug*: AG's promotion path does not mix
epistemic species; its live risk is domain admissibility (the gate's), not species
laundering. Recording this here so a later session does not rediscover "it only returns
ADMITTED" the hard way.

## Epistemic status (corrected — supersedes any earlier "toward Observed" framing)
- `Observed<projection integrity and noninterference>` — the shadow projects, classifies
  beside the gate, mirrors the gate verdict verbatim, and writes nothing; this is
  behaviorally witnessed (12 tests + live specimen + reachability sweep).
- `Not observed<live epistemic-conversion seam>` — no current AG receipt attempts an
  illegitimate species conversion, so the seam `normal_form` describes is not load-bearing
  in AG today. The earlier "toward Observed" claim was inflated and is retracted.
- `normal_form` remains **isolated and prospective** — a dormant tripwire for a future
  evidence type that overclaims across species. Do not promote the tripwire into
  architecture merely because it was built.
- **No reliance wiring authorized.** The gate's plug point stays named, not crossed.
- **All current production-facing rules unreachable** from AG promotion evidence.

## Next (P0 is deleted from the active queue — do NOT open on momentum)
P0 has earned deletion from the active queue. The code stays as a dormant tripwire; it is
not promoted into architecture. The next move is **not more P0** — it is a fresh cold
admission for **P4's real trial-evidence path**, where AG's live risk actually sits (not
epistemic-species laundering, but whether a trial can manufacture an *apparently complete*
promotion record from weak, stale, or circular domain evidence):

1. Run an actual bounded `max_slices=4` self-governance trial.
2. Produce on-disk activation, observation/survival, replay-holdout, and operator-basis
   receipts.
3. Verify lineage, freshness, replay, and expiry against real artifacts — not the accepted
   config-hash fixtures.
4. STOP before promotion; inspect whether the chamber is genuinely sufficient.

That is its own cold admission (operator-present / HIGH), opened only on a fresh go.
