# Clock Witness — build-ready spec (revises the hero specimen)

**Status: RATIFIED build spec (operator decision-grade, 2026-06-12), NOT yet
built.** This re-opens the temporal-lapse hero specimen (item 2.5,
`standing_spendability.py`): the current `StandingWindow` uses bare integer
seconds + a `clock_basis: str` — which is **a clock costume, not a clock witness**
(Fable amendment 3). The gap must run on *monotonic* readings (same source, same
epoch), not wall time; uncertainty must be measured or honestly `unknown`, never
fiat; and the freshness gray zone must be a first-class verdict. This spec is the
upgrade. Source: operator + ChatGPT + Fable relay (relay caveat: ratified, not
independently verified).

## Doctrine (goes in the doc file next to the LA glyph)

> **Time is not ambient. Time is a witnessed input.**
> **A timestamp is testimony, not authority. A gap is computed only over
> compatible monotonic witnesses.**
> **The evaluator may use a claim's validity interval, but never the claim's own
> clock, to decide whether the claim is current.** (the anti-laundering rule)

A clock is **not LA**. A clock does not exhaust; it testifies. Freshness/expiry/
gap/ordering all depend on clock testimony; the crime is treating "now" as ambient
truth. (Throughput of a sealer/query CPU *is* metabolic — but sealing windows and
deadlines are temporal obligations, not fuel. Don't give deadlines a wallet.)

## The clock-kind split (the assignment is load-bearing)

| use | clock source | why |
| --- | ------------ | --- |
| freshness / expiry | wall clock + uncertainty policy | validity intervals are civil/absolute |
| **gap / elapsed bound** | **monotonic, same-source same-epoch** | subtraction must survive NTP steps |
| ordering | sequence / log clock | order is not freshness |
| human display | wall timestamp marked `display_only` | useful, not load-bearing |

## The D0 ClockWitness object (`clock.witness.v0`)

```json
{
  "clock_witness_schema": "clock.witness.v0",
  "actor": "standing-evaluator",
  "wall": {
    "observed_at": "2026-06-11T04:12:45Z",
    "source": "system_clock_unsynced",   // or "ntp_tracked"
    "uncertainty": "unknown",             // or {"measured_ms": 7}
    "role": "display_only"                // or "freshness_basis" when ntp_tracked
  },
  "monotonic": {
    "source": "process_monotonic",
    "monotonic_ns": 123456789000,
    "monotonic_epoch": "boot:<id>"        // one cheap field now vs cross-reboot garbage later
  }
}
```

**Uncertainty is measured or unknown — never fiat (amendment 1).** `uncertainty_ms:
500` is astrology with milliseconds. A system clock cannot testify to its own
uncertainty without an external reference. Honest rule: `measured(ms, source=
ntp_tracked)` (value from chrony/NTP tracking) **or** `unknown(source=
system_clock_unsynced)`, and the skew policy must handle `unknown` explicitly, not
default it to a flattering number. For the single-host demo, wall `unknown` is fine
— because the gap runs on monotonic, not wall.

## Freshness is THREE-valued (amendment 2 — don't round the gray zone)

Given `observed_at = t`, `uncertainty = ε`, `valid_until = T`:

| condition | verdict |
| --------- | ------- |
| `t + ε < T` | `current_under_clock_policy` |
| `t − ε > T` | `expired_under_clock_policy` |
| interval straddles `T` | `indeterminate_under_clock_policy` |

The straddle is first-class, NOT collapsed into expired (false refusals) or current
(the actual crime). It's the dual-failure non-collapse rule applied temporally:
when the witness genuinely can't distinguish stale from current, the receipt says
so. Demo policy may *refuse* on indeterminate (refuse-conservative), but the verdict
layer preserves the trichotomy — so later someone can ask "refused because stale, or
because the witness couldn't tell?"

## The hero gap predicate runs on MONOTONIC (amendment 3 — the actual fix)

The murder hallway's predicate is the *gap*, not the freshness check:

```
exercise_at.monotonic_ns − standing_observed_at.monotonic_ns <= bound_ns
```

Legal ONLY between two readings from the **same monotonic source AND same
monotonic_epoch**. Wall subtraction is forbidden (NTP steps make it garbage with an
ISO 8601 smile). The specimen receipt carries **both**: monotonic readings (shared
source/epoch) for the gap, wall timestamps riding along `display_only`. Mismatches
refuse rather than subtract confidently:

- different sources → `gap_basis_mismatch`
- different monotonic epochs (boot-id) → `monotonic_epoch_mismatch`

Single host, single process, same epoch → the demo's gap is *sound*, and the receipt
can prove it's sound. That is the entire point.

## Anti-laundering pair (amendment 4 — pin both)

- `blocked_timestamp_laundering` — a receipt timestamp testifies "this actor claimed
  to observe time t when signing"; it does NOT testify the claim was valid at
  *evaluation* time. Signed is not witnessed, in temporal clothing.
- `blocked_self_attested_freshness` — the evaluator consulting the **claim's own**
  timestamps as the clock ("the claim says it's still fresh"). The claim is not its
  own clock.

Both refuse; both get pinning tests. Together: *no evaluator accepts a time-bounded
claim without naming the clock witness and policy used to judge it current — where
"clock witness" is an evaluator-side observation, never a field the claim brought to
its own trial.*

## Refusal vocabulary (new kinds)

```
blocked_expired              (measured wall clock, t−ε > T)
blocked_not_yet_valid        (issued−skew > now)
blocked_missing_clock_witness
indeterminate_under_clock_policy   (straddle; demo policy then refuses conservatively)
blocked_clock_uncertain      (clock outside allowed skew, distinct from straddle)
gap_basis_mismatch           (two readings, different sources)
monotonic_epoch_mismatch     (two readings, different boot epochs)
blocked_timestamp_laundering
blocked_self_attested_freshness
```

Tier check before wiring: which of these join AG's S4-lite `CLOSED_REFUSAL_KINDS`
vs. live only in the clock-witness module's own closed set. The hero's existing
`standing_before_spendability_not_bounded` stays; the gap-basis/epoch ones are
clock-internal guards.

## What this revises in the shipped hero

1. `standing_spendability.py` — `StandingWindow` gains structured clock readings:
   monotonic (ns + source + epoch) for the gap; wall (observed_at + uncertainty +
   role) `display_only`. `clock_basis: str` → the structured witness.
2. The gate computes the gap on monotonic_ns; refuses `gap_basis_mismatch` /
   `monotonic_epoch_mismatch` when readings are incompatible.
3. Freshness verdict (if the gate also does validity-interval checking) becomes
   three-valued.
4. Golden corpus `08`/`09` receipt shape updates to the clock-witness block (the
   gap is monotonic; wall is display_only). Re-freeze the pair.
5. `demo_refused_spend.py` surface renders the clock witness honestly (monotonic
   gap + display-only wall + "sound gap, same epoch").
6. The proof seam still cites `Freshness.expired_not_fresh` — but note the lean
   theorem is about validity intervals (wall/civil), while the gap predicate is
   monotonic. Reconcile: the hero refusal is *standing-before-spendability bound
   exceeded* (gap, monotonic), and `expired_not_fresh` is the *freshness* class
   boundary (interval, wall). They are TWO temporal boundaries — check whether the
   hero cites the gap boundary, the freshness boundary, or both. (Open question to
   resolve at build: is there a lean theorem for the monotonic-gap bound, or is the
   gap an AG-side policy over a clock witness with the freshness theorem as the
   nearest class?) Do NOT overclaim the citation — exhibit the distinction.

   **RESOLVED 2026-06-12 (proof-seam-citation-reconciliation, audit-gated slice;
   receipt: `.governor/loop-receipts/`).** The "wall vs monotonic" premise was a
   misreading of the *canonical consumer* (Standing's chrono `DateTime<Utc>`) as
   the *kernel's* semantics. Freshness.lean's `Time` is an OPAQUE axiom — abstract
   le/add/sub, **no order axioms**, "the kernel proves invariants of the shape,
   not of the underlying type." There are not two temporal boundaries in the
   kernel; there is one shape, and wall/monotonic are consumer instantiations.
   The monotonic single-epoch instantiation (Time := ns within one (source,
   epoch); now := exercise; issued := observed; expires := observed + bound;
   skew := 0) makes the hero's `gap_ns > bound_ns` *definitionally* the theorem's
   hypothesis `¬(now ≤ expires + skew)` — the citation stands, match DIRECT, and
   the monotonic basis is the stronger instantiation (the axiom-free Time is the
   kernel demanding the consumer supply coherent time; `elapsed_ns`'s refusals
   are that obligation discharged). Honest residue, recorded in
   `TheoremRef.instantiation` and rendered on the Act-3 surface: the
   compatible-witness discipline itself (source/epoch mismatch refusals) is
   AG-side mechanics with NO kernel theorem.

## Bounded implementation order (relay's, 8 steps)

1. Define `ClockWitness`.
2. `WallUncertainty = measured(ms, source) | unknown(source)`.
3. `MonotonicBasis = source + monotonic_epoch + monotonic_ns`.
4. `freshness_verdict(claim_interval, wall_witness, policy)` → trichotomy.
5. `gap_verdict(start_monotonic, end_monotonic, bound_ns)` → ok | gap_basis_mismatch
   | monotonic_epoch_mismatch | exceeded.
6. Emit receipts with failed predicate + clock basis.
7. Pinning tests (the crime table below).
8. Re-freeze the hero pair (corpus 08/09).

## Test crimes (must-pin)

| crime | expected |
| ----- | -------- |
| expired claim under measured wall clock | `blocked_expired` |
| not-yet-valid claim | `blocked_not_yet_valid` |
| uncertainty straddles validity edge | `indeterminate_under_clock_policy` |
| demo policy refuses indeterminate | explicit conservative refusal |
| missing evaluator-side clock witness | `blocked_missing_clock_witness` |
| gap computed from wall timestamps | refused |
| monotonic readings, different epochs | `monotonic_epoch_mismatch` |
| monotonic readings, different sources | `gap_basis_mismatch` |
| receipt timestamp used as freshness proof | `blocked_timestamp_laundering` |
| claim's own timestamp used as clock | `blocked_self_attested_freshness` |

## Placement / not-this

Real project (`src/governor/clock_witness.py`), NOT playground — this is the demo's
load-bearing seam. NO LA. No confidence tokens. No clock "budget." No fake
precision. No ambient `now`. Leave the six-ledger taxonomy in the drawer.

## Cross-refs

- `src/governor/standing_spendability.py` — the hero this revises.
- `golden/corpus/08-temporal-lapse-refused.json` / `09-*` — re-freeze after.
- `docs/constellation-zoning.md` §LA time-axis glyph ("three time budgets") — the
  doctrine this implements; the gap is temporal (clock), not metabolic (ledger).
- `~/git/lean` Freshness.lean (`expired_not_fresh`, `not_yet_valid_not_fresh`) —
  the freshness class boundary; reconcile gap-vs-freshness citation at build.

## Ratification pass 2026-07-14 — NOT build-ready (5 escapes, 2 design-level)

Escape-count against the current `clock_witness.py`, scoped to LAYER A
(`freshness_verdict` + anti-laundering refusals; the hero-revision layer B was
out of scope). The 2026-06-12 "operator decision-grade" status was relay-authored
and never independently verified; this pass found layer A does NOT teach its own
boundaries. **Do not build until resolved.**

**Engineering pins (patchable at build):**
1. **Units undefined.** `observed_at` is an ISO-8601 `str`, `uncertainty_ms` is
   ms, `valid_until` ISO — the spec never says how they combine. Pin: parse ISO
   → epoch ms (or ns), uncertainty in ms, one common unit; a raw-ms-vs-seconds
   mix is silently wrong by 1000×.
4. **`policy` shape + precedence undeclared.** "allowed skew" is never a defined
   field; precedence when ε both straddles T *and* exceeds max-skew is unstated.
5. **`blocked_not_yet_valid` off-table.** Needs a claim `valid_from`/`issued`
   not in the (t, ε, T) table; uses a point `now` vs the `t±ε` interval used
   elsewhere; ordering vs the trichotomy unstated.

**Design decisions (need a ruling before build — authority-relevant):**
2. **`unknown` uncertainty → which verdict?** `t ± ε` is uncomputable when ε is
   `unknown`. Spec prohibits a flattering default but names no verdict. Proposed
   (fail-honest): `unknown` → `indeterminate_under_clock_policy` (the witness
   cannot distinguish; that is what the gray zone is for), never `current`;
   `blocked_clock_uncertain` stays for a *measured* ε wider than allowed skew.
   Operator ruling wanted.
3. **Anti-laundering needs a MECHANISM, not prose (the crux).**
   `blocked_timestamp_laundering` / `blocked_self_attested_freshness` require the
   evaluator to know a timestamp's provenance, but `freshness_verdict(claim_interval,
   wall_witness, policy)` has no provenance field and a `WallWitness` is a struct
   any caller can build from the claim's own `observed_at`. Proposed: add an
   `actor`/provenance field to the evaluator's clock witness (or take the
   evaluator witness as a distinct typed input the claim cannot populate) so the
   refusal is type-enforceable — "the claim is not its own clock" becomes a
   compile/type fact, not a comment. Operator ruling wanted (it changes the
   `WallWitness` type / the function contract).

**Verdict: RATIFICATION HELD.** Layer A returns to `filed` pending the two design
rulings; the three engineering pins fold in at build. Layer B (hero revision +
corpus 08/09 re-freeze) remains a separate later slice.
