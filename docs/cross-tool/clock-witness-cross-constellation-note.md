# Cross-tool invariant note: a gap is not a subtraction

## Status

**Cross-constellation candidate invariant — non-binding, no implementation
authorized.** Filed 2026-06-18 under AG custody as cross-repo governor (see
`managed-repo-candidate-filing-note.md`). This note declares an *admissibility-grammar
invariant* and maps its consumers; it does not implement anything, does not declare
the primitive shipped constellation-wide, and does not appoint a time authority.

This is the constellation handle for the same demon two local notes already pin:

- nq: `nq/docs/working/decisions/CLOCK_WITNESS_PRIMITIVE_CANDIDATE.md` — the local
  scar / first-home Rust candidate (opaque `ClockInstant`, `LicensedGap`,
  `ClockRefusal`; PREFLIGHT_CORE clock-injection).
- standing: `~/git/standing/docs/standing-clock-witness-candidate.md` — the witness
  type + the anti-mechanization fence.

AG is the office *furthest along*: it already implements the seed in
`src/governor/clock_witness.py` (`MonotonicReading` / `WallWitness`; `elapsed_ns`
the **only** licensed subtraction; `GapBasisMismatch` / `MonotonicEpochMismatch`
refusals) and consumes it in `standing_spendability.py`. This note does not invent —
it generalizes what AG typed internally into an invariant the constellation shares.

## The invariant

> **A gap is not a subtraction. It is a licensed comparison between clock witnesses
> with compatible bases.**

Any office that uses elapsed time, freshness, expiry, lapse, observation windows,
standing gaps, receipt-sequence gaps, or projection-read freshness for an
**admissibility-relevant comparison** must operate on declared **clock witnesses**,
not bare timestamps.

Unknown or incompatible clock basis **refuses the comparison.** It does not collapse
to PASS. (This is the time-shaped instance of the constellation's one universal —
*UNKNOWN poisons PASS*: no office converts an unverifiable, incompatible, or
unwitnessed gap into a clean affirmative result merely because the local path lacks
a refusal branch.)

Two further pins carried up from the local notes:

- **Comparability, not truth.** A witness asserts only *"these two endpoints are
  comparable under declared basis X."* It never certifies the clock source is
  correct — a wall-clock witness can still be wrong. The primitive governs whether a
  comparison *may be used*, not whether UTC came down from the mountain.
- **Basis-aware gaps, not always a Duration.** A wall/monotonic comparison yields a
  duration; a receipt-sequence comparison yields an ordinal/logical gap. Do not
  coerce a logical sequence into fake seconds — that is how a time crime becomes an
  accounting crime.

## Consumer map (where the demon lives per office)

```text
NQ:         preflight freshness; observed_at vs generated_at; evaluator windows
Standing:   standing_observed_at vs exercise_attempted_at (the spendability lapse)
Continuity: stored-record time vs projection/read time (read-freshness on a
            ProjectionReceipt — see continuity docs/candidates/PROJECTION_RECEIPT.md)
LA:         lapse / window math (cf. the named Wall-2 unit_origin_mismatch seam)
AG / kernel: expiry, promotion windows, survival bounds, receipt-sequence comparisons
            (already live in standing_spendability.py / clock_witness.py)
```

## The fence (what this note must NOT be read to say)

- **Not** "ClockWitness is implemented constellation-wide." AG implements it in
  Python for its own use; each other office types its own *local* manifestation when
  its scar forces it. NQ in Rust, Standing in Rust — independently.
- **Not** "NQ owns time for the constellation." No office owns time. The witness
  governs *whether a comparison may be used*, not the clock.
- **Not** authorization to build a shared crate. First home stays local; promotion to
  a shared crate (`receipt_kernel` / admissibility kernel) is triggered only by a
  genuine **second consumer**, per the local notes' promotion rule. Same discipline
  as `receipt-sovereignty-microkernel-note.md`: *co-locate the repos; never merge the
  authorities.*

What it **does** say: once this primitive is adopted at an office, **bare timestamp
arithmetic is not admissible for that office's governed comparisons.** Adoption is
per-office and forcing-case-gated; this note reserves the invariant, it does not
schedule the work.

**Wire-format pin (carried up):** even while every type stays local, the *basis tag*
that rides in receipts crossing office boundaries must be stable from day one. A tag
like `basis: "wallish"` is a retrofit-hell IOU. The cross-office vocabulary is the
one part that cannot be casually local.

## Doctrine lines

- A gap is not a subtraction.
- Clock witnesses do not govern time. They govern whether a time comparison may be used.
- Opaque instants, licensed gaps, typed refusals. No cape.
- Unknown or incompatible basis refuses the comparison; it does not collapse to PASS.
