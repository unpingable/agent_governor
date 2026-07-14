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

## Design rulings (operator, 2026-07-14) — build-ready; supersedes the HELD verdict

Both design escapes ruled; the three engineering pins fold in with the interval
semantics below. Layer A is build-ready pending an escape-count re-run to zero.

### Ruling 1 — `unknown` uncertainty is OUTSIDE the freshness trichotomy

`indeterminate_under_clock_policy` means precisely: a **measured, policy-admissible**
uncertainty interval **straddles a validity boundary**. It is NOT the catch-all for
"can't tell." `unknown` uncertainty is a different epistemic failure — there is no
interval to classify — so it refuses, it does not render a freshness verdict.

Interval semantics (explicit, symmetric):
- claim validity is `[valid_from, valid_until)` — from inclusive, until exclusive.
- evaluator observation is the closed interval `[t−ε, t+ε]`.

Verdict order (first match wins):
1. no evaluator observation supplied → `blocked_missing_clock_witness`.
2. `ε` is `unknown` → `blocked_clock_uncertain`, reason `uncertainty_unknown`.
3. `ε` measured but `> policy.max_skew_ms` → `blocked_clock_uncertain`, reason
   `uncertainty_exceeds_policy`.
4. measured, admissible `ε` (the ONLY domain that yields a freshness verdict):
   - `t − ε ≥ valid_until` → `expired_under_clock_policy`.
   - `t + ε < valid_from` → `blocked_not_yet_valid`.
   - `valid_from ≤ t − ε` AND `t + ε < valid_until` → `current_under_clock_policy`.
   - otherwise (observation straddles `valid_from` or `valid_until`) →
     `indeterminate_under_clock_policy`.

So the trichotomy is genuinely three-valued **within its measured-admissible
domain**; `unknown`/`exceeds-policy`/`missing` are refusals of the *prerequisites*,
kept distinct. (Resolves escapes #2, #4, #5.)

### Ruling 2 — anti-laundering by CUSTODY + TYPE SEPARATION, not a field

An `actor`/provenance field is evidence, not enforcement — a claim can fill out the
evaluator's form correctly (a better clock costume). Enforce structurally instead:

- `ClaimInterval` (`valid_from`, `valid_until`) — the ONLY thing derived from claim
  data.
- `EvaluatorWallObservation` — a **distinct internal type**, produced ONLY by an
  evaluator-owned `ClockSampler` (factory) at evaluation time. **No `from_dict` /
  deserialization path** — untrusted/claim data has no route to become one.
- `freshness_verdict(claim_interval, evaluator_observation, policy)` accepts that
  internal observation, never an arbitrary serialized `WallWitness` handed in
  alongside the claim.
- `actor` / `source` / provenance live in the **emitted receipt** — they document
  the custody path; they do not create it.
- Consequence: `blocked_timestamp_laundering` and `blocked_self_attested_freshness`
  become **UNREPRESENTABLE** (the claim never receives the evaluator's form), not
  runtime refusals. The pinning "crimes" become *type/API* tests: a claim's
  timestamp cannot be passed as the evaluator observation; the fake evaluator clock
  is injected through the `ClockSampler` interface, never via constructed "trusted"
  JSON. (Resolves escape #3 — the crux.)
- **Out of scope (separate seam):** if a clock witness ever crosses a process
  boundary, authenticity/attestation is its own seam — do NOT invent a provenance
  enum / miniature temporal PKI here.

### Engineering pin 1 — units

Parse ISO-8601 (`observed_at`, `valid_from`, `valid_until`) → epoch **milliseconds**
(int); `uncertainty_ms` is already ms; one unit (ms) internally. No raw-ms-vs-seconds
mixing. (The gap predicate stays on `monotonic_ns` — unaffected; this is the wall/
civil freshness side only.)

**Build order:** bank rulings (done) → rerun escape-count → build Layer A only if 0.

### Build pins 2 (escape-count pass 2 → 3, 2026-07-14) — 4 residual holes closed

Pass 2 (post-ruling) found 4 buildability escapes; patched here (engineering
realizations of the rulings, no new ruling needed):

- **P1 — validity bounds are mandatory (open-ended is out of Layer A).**
  `ClaimInterval` requires BOTH `valid_from_ms` and `valid_until_ms` (ints).
  Open-ended validity (`valid_until = None`, "valid forever after issue") is NOT
  Layer A — a consumer needing it passes a far-future `valid_until`, or it lands
  in a later slice. This keeps `freshness_verdict` total (no `None < t+ε` crash).
  Degenerate `valid_until ≤ valid_from` falls to `expired` by first-match, which
  is harmless and acceptable.
- **P2 — `evaluator_observation` is `EvaluatorWallObservation | None`.** Branch 1
  (`None → blocked_missing_clock_witness`) is live: an evaluator with no
  configured/successful sampler passes `None`. The type is Optional; the missing
  branch is not dead code.
- **P3 — custody is a construction TOKEN, and the honest scope of "custody".**
  Python has no private constructors, so "unrepresentable / compile fact"
  OVERCLAIMS — a plain dataclass is directly instantiable and would let
  `freshness_verdict(ci, EvaluatorWallObservation(observed_at=claim.observed_at,…))`
  launder. Buildable mechanism: `EvaluatorWallObservation.__init__` requires a
  module-private `_SAMPLER_TOKEN` sentinel that ONLY `ClockSampler` implementations
  hold; direct construction without it raises. No `from_dict`/deserialization path
  exists. **Honest threat scope (this is what custody delivers, stated plainly):**
  this closes (a) untrusted/serialized *claim* data becoming an observation — the
  real threat, since a claim arrives as data and deserializes to `ClaimInterval`
  only, and (b) *accidental* in-process construction. It does NOT prevent the
  trusted evaluator from *deliberately* importing the token and laundering — no
  Python mechanism does, and that is out of the threat model (the evaluator is
  trusted; the claim is not). So the two "crimes" are: untrusted-path-closed +
  accidental-construction-fails-at-`__init__`; NOT a compile-time impossibility.
  (Cross-process authenticity remains a separate seam, unchanged.)
- **P4 — `ClockSampler` interface.** `class ClockSampler(Protocol): def sample(self)
  -> EvaluatorWallObservation`. Concrete `SystemClockSampler(source: str,
  uncertainty_ms: int | None = None)` stamps `observed_at_ms = int(time()*1000)`,
  carries `source` + `uncertainty_ms` (None = honestly unknown), and mints the
  observation with `_SAMPLER_TOKEN`. Test doubles implement the Protocol to inject
  a fixed/fake clock — never by constructing "trusted" JSON.

### Build pins 3 (escape-count pass 3 → 4, 2026-07-14) — return contract + closed enum

Pass 3 confirmed P1–P4 close (custody scope honest, no overclaim). Two API-shape
gaps, pinned from the spec's own doctrine (no new ruling):

- **P5 — `freshness_verdict` RETURNS, never raises.** Signature:
  `freshness_verdict(claim: ClaimInterval, obs: EvaluatorWallObservation | None,
  policy: FreshnessPolicy) -> FreshnessResult`, where
  `FreshnessResult(verdict: str, reason: str | None)` (frozen). It never raises
  for any of the outcomes below — the *verdict layer preserves the trichotomy*
  (spec doctrine: "so later someone can ask 'refused because stale, or because the
  witness couldn't tell?'"); the GATE/policy layer decides which verdicts refuse.
  `reason` is populated ONLY for `blocked_clock_uncertain`
  (`uncertainty_unknown` | `uncertainty_exceeds_policy`); `None` otherwise.
  (Distinct from the existing monotonic-gap functions, which DO raise
  `GapBasisMismatch`/`MonotonicEpochMismatch` — the gap is a different surface.)
- **P6 — one closed verdict enum; Ruling 1 names are authoritative.** The
  complete, closed output set of `freshness_verdict.verdict`:
  `current_under_clock_policy`, `expired_under_clock_policy`,
  `blocked_not_yet_valid`, `indeterminate_under_clock_policy`,
  `blocked_clock_uncertain`, `blocked_missing_clock_witness`. The pre-ruling
  "Refusal vocabulary" / "Test crimes" tables above are HISTORICAL; where they
  conflict, Ruling 1 wins — specifically `blocked_expired` is **superseded by
  `expired_under_clock_policy`**. (`blocked_timestamp_laundering` /
  `blocked_self_attested_freshness` are NOT in this enum — per P3 they are
  prevented by construction custody, not returned as verdicts.)

## Build outcome — Layer A BUILT (2026-07-14)

Escape-count converged 5→4→2→0 (four passes; the two design escapes resolved by
operator ruling 2026-07-14, the rest folded as pins). Built into
`src/governor/clock_witness.py`:

- `freshness_verdict(claim, observation, policy) -> FreshnessResult` — total,
  never raises; the closed 6-verdict enum; `reason` only on
  `blocked_clock_uncertain`. `unknown` uncertainty refuses (NOT `indeterminate`);
  `indeterminate` reserved for a measured-admissible interval that straddles a
  boundary; intervals `[valid_from, valid_until)` half-open vs `[t±ε]` closed.
- `ClaimInterval` (claim-derived; `from_iso` → epoch ms), `FreshnessPolicy`
  (`max_skew_ms`), `FreshnessResult`.
- **Anti-laundering by custody:** `EvaluatorWallObservation` is token-gated
  (`_SAMPLER_TOKEN`), minted only by a `ClockSampler` (`SystemClockSampler` +
  Protocol), no deserialization path — so claim-as-data has no route to become
  the evaluator's clock. Honest scope: closes the untrusted path + accidental
  construction; deliberate in-process token import by the trusted evaluator is
  out of the threat model (no compile-time impossibility claimed).
- Hardening from the adversarial pass: negative `uncertainty_ms` refused at
  construction (analogous to `elapsed_ns` refusing backwards readings).

**Gates:** escape-count 0 (pass 4); adversarial sandwich **0 exploitable
findings** (verdict logic sound, custody honest-not-overclaimed); tests
`tests/test_clock_witness_freshness.py` (16, the crime table incl. the custody
pins) + existing clock/standing/drill green (30 + 47). The monotonic gap surface
(`elapsed_ns`) is untouched.

**Layer B — CLOSED, previously implemented, independently reverified 2026-07-14.**
Not built as a fresh slice: on reverification every Layer B obligation was already
satisfied. The hero migration to the structured clock witness landed incrementally
in June — `1a0e6a5` (monotonic gap basis for the temporal-lapse seam) and `1ddd781`
(typed `freshness_subcase` on the spendability receipt) — plus the demo/interrogate
commits. What was genuinely new on 2026-07-14 was Layer A (wall-freshness trichotomy
+ custody), which is correctly **NOT** wired into the hero: the hero's predicate is
the monotonic *gap* (`standing exercised within the allowed gap?`), a deliberately
separate temporal boundary from Layer A's civil-time validity question (`is a
validity interval current under an evaluator-owned wall observation?`). Conflating
them would quietly change the refusal semantics — that would be a new seam ("Layer C")
requiring its own ruling, not completion of this slice (operator ruling 2026-07-14).

Reverification receipts (each Layer B item, from §"What this revises in the shipped
hero"):

1. `StandingWindow` carries structured clock readings — `standing_spendability.py`
   uses `MonotonicReading`/`WallWitness`; the live drill builds it at
   `drill_runner.py:408` (`_mono` monotonic readings + display-only `WallWitness`,
   `uncertainty_ms=None` honestly unknown). No `clock_basis`/bare-seconds costume
   remains.
2. Gap on monotonic ns, refuses `gap_basis_mismatch`/`monotonic_epoch_mismatch` —
   `elapsed_ns` is the only licensed subtraction.
3. Three-valued freshness *if the gate does validity-interval checking* — the gate
   does the gap, not a validity check; correctly N/A (see the proof-seam
   reconciliation, §6 RESOLVED).
4. Corpus 08/09 clock-witness block + re-freeze — on-disk sha256 == MANIFEST
   (`9ee6639…` / `8fbd696…`); `test_corpus_contract` reproduces 08's
   `expected_receipt_block` **exactly against the live cooked-context chain** with an
   attested monotonic `gap_basis`. Corpus deliberately **not** churned.
5. `demo_refused_spend.py` renders the clock witness honestly — `gap_basis:
   monotonic, source, epoch (sound: one source, one epoch)` + `wall [display_only]`.
6. Proof citation reconciled — §6 RESOLVED (`expired_not_fresh` via the monotonic
   single-epoch instantiation; honest residue recorded).

Verification: `test_corpus_contract + test_clock_witness + test_clock_witness_freshness
+ test_standing_spendability + test_drill_temporal_lapse` → 91 passed, 12 skipped,
exit 0. No ceremonial escape-count was run: escape-count gates a spec_slice
*modification*, and there is no modification — the frozen artifacts already match the
live chain. (A completion-redshift event: this spec text itself carried a false
future obligation for work already shipped.)
