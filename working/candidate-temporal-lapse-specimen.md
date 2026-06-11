# Candidate: two-clock temporal-lapse specimen (the demo's hero case)

**Status: candidate / NOT built. Next W1 slice after the golden-corpus freeze.**
Filed 2026-06-12.

## Why this is filed

The launch plan (`working/launch-plan-2026-06-11.md`) designates the **two-clock
temporal lapse** as the demo's single best specimen — "everyone's been bitten by
a stale yes":

> standing checked at t=40, horizon expires t=50, spend at t=51; naive auth says
> yes, custody says no; receipt shows both clocks and the gap. Dodges
> philosophical fog; maps to every cache / lease / session / CI-status /
> deploy-approval in the industry.

When building the golden corpus (W1 item 2) I verified — by grep over
`drill_runner.py` — that **no scenario produces this receipt shape today**. There
are zero `standing_observed_at` / `capacity_committed_at` / `clock_basis` / `gap`
fields anywhere. The existing `standing-expired` scenario refuses because the
standing digest is *unverifiable* (resolves to no minted receipt) — a different
refusal class from *valid-when-observed, expired-in-the-gap*. The corpus labels
that case honestly (`03-standing-unverifiable-refused`) rather than dress it up
as the temporal case.

So the demo's centerpiece does not exist yet. This note is the handle.

## The shape (from `docs/constellation-zoning.md` §Standing)

Zoning already spec'd the receipt the specimen needs — this is not a fresh
design, it is a build against an existing zoning record:

```
standing_observed_at = T1 ; model_age = Δ1
capacity_committed_at = T2 ; model_age = Δ2
exercise_at = T3
gap(T1,T2,T3) visible
clock_basis = ntp_bounded(±x)  | unbounded → gap_check: advisory
```

And the demo-shaped refusal (zoning §Standing, line ~402):

> `refuse spend: standing_before_spendability_not_bounded` — because clock_basis
> unbounded / chain was grant-time-only / lapse coverage missing / class standing
> exists but instance membership unproven.

The load-bearing distinction zoning insists on: **standing-before-spendability
must be bounded, not merely ordered** — two clocks and a clock basis, or the gap
math is decoration. Witnesses expose the murder hallway; *policy* (downstream)
decides the acceptable gap.

## Why it is its own slice (not folded into the corpus freeze)

1. **New refusal kind.** `standing_before_spendability_not_bounded` is not in any
   current closed set. Adding it is a vocabulary change (S4-lite / standing seam)
   — the kind of change the wiring invariant and register discipline say to do
   deliberately, not slip into a "freeze the corpus" slice.
2. **Receipt-shape change.** The standing-seam receipt (or the proposal packet)
   must carry two timestamps + clock_basis + gap. That touches what the standing
   seam emits — closer to custody-affecting than the pure-Python corpus freeze.
3. **Standing semantics brush.** Two-clock / lapse-vs-expiry / clock_basis are
   standing-repo concepts (`~/git/standing` owns standing semantics). The AG-side
   *demo scenario* is AG's to build, but the vocabulary should not drift from the
   standing repo's lapse model. Worth a glance at `memory/standing_integration`
   before minting names.

## Build sketch (when taken)

- New scenario `SCENARIO_STANDING_LAPSED` (or similar) in `drill_runner`: a
  finding whose standing was valid at observation (T1) but whose horizon expired
  (T2 < T3 spend). Distinct from `standing-expired` (unverifiable digest).
- The standing seam (or a thin policy check at the spend edge) compares
  `standing_observed_at` + horizon against `exercise_at`; on lapse, refuse with
  the new typed kind, the receipt carrying both clocks + the gap.
- `clock_basis`: if unbounded, the gap check is advisory (mark it), not a hard
  refusal — per zoning, witnesses expose, policy decides.
- Add a golden corpus case `08-temporal-lapse-refused.json` freezing the verdict
  (`refused` / `standing_before_spendability_not_bounded` / standing_seam /
  effect 0), and promote it to `demo_role: temporal_lapse` (the hero beat).
- This is the receipt the demo's Act 1 ("Columbo: the observation was forty
  seconds old, and the spend happened at second fifty-one") points at.

## Cross-references

- `golden/README.md` — "Known gap" section points here.
- `golden/corpus/03-standing-unverifiable-refused.json` — the honestly-labeled
  near-neighbor that is NOT this.
- `docs/constellation-zoning.md` §Standing — the two-clock shape + refusal name.
- `working/launch-plan-2026-06-11.md` — "Best specimen = temporal"; Columbo beat.
- `specs/gaps/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` /
  `GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001.md` — post-validated ≠
  pre-authorized; the two-clocks gap these obligate.
- `memory/feedback_basis_dependency_over_chronology` — frame the gap as
  basis-dependency direction, not wall-clock, when naming the refusal.
