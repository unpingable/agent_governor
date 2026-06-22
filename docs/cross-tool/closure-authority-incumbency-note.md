# Closure authority needs incumbency proof (fencing tokens)

**Status:** candidate, doc-only, NOT built, NOT authorization to build. Named 2026-06-22
from the same exchange that crystallized the laundering-conservation law-form
(`docs/doctrine/weak_property_strong_property.md` § "Laundering is conserved"). This note
is a handle for review, per the YAGNI-record discipline (name early, ratify lazily,
implement only on a forcing case).

## The gap

AG checks the freshness of an *observation* before a spend — that is the two-clock seam
`standing_spendability.py` closes (*valid when observed ≠ valid when exercised*). It has
**no** equivalent check on the *closure authority itself*.

A closure authority is whatever pays the coordination tax to assert that a causal frontier
is complete: a sequencer, a quorum, a lease-holder, a single-writer regime. Naming it
(`AuthorityId`, `Regime`) is not proving it is *still seated* at issue time. The classic
hole (Kleppmann, *How to do distributed locking*): a lease-holder GC-pauses past its lease,
or a primary is fenced and does not notice, and then signs a perfectly well-formed closure
receipt. That receipt carries maximal apparent authority and is issued by a deposed judge.

This is `authorized once ≠ authorized forever` (already a row in the weak→strong table),
relocated one layer up — onto the very layer trusted to terminate that failure. The
laundering-conservation ladder predicts it: once read-time, sink-check, and check→commit
are closed, the next unreceipted rung is authority incumbency.

## The shape of the missing primitive (sketch, not spec)

A closure receipt would need to carry a monotonic incumbency witness — a term number /
fencing token — that the **sink or protected resource** checks against a high-water mark,
not an `AuthorityId` taken on faith:

```
token <  high_water[authority, scope]  -> refuse: stale authority (deposed / paused)
token == a token already spent          -> refuse: replay
token >  high_water[authority, scope]   -> may proceed, then advance the high-water mark
```

The check lives at the resource (the part everyone skips). An admission service in front of
a side door everyone else also uses enforces nothing.

## Why not build it now

No forcing case. AG is single-host, SQLite-WAL, single-writer-linearizable today
(see `GOV_GAP_MULTIGOV_DEADLOCK_CUSTODY_001` — "observations plural, custody singular";
CAS-lease consensus is explicitly out of scope until a real multi-node closer exists).
Fencing tokens are a primitive for *contended incumbency across nodes*. With one writer
there is no deposed-leader race to lose, so building the token machinery now would be
speculative expansion, not coverage of an admitted seam.

## Forcing case that would license building

Any of:
- A second process/host can act as a closure authority for the same scope (multi-writer,
  failover, or a real distributed lease enters the spend path).
- `GOV_GAP_MULTIGOV_DEADLOCK_CUSTODY_001` moves from spec to build (leader election for the
  deadlock detector is exactly an incumbency surface).
- An external closer (NQ sequencer, a Standing/LA authority that can be re-elected) becomes
  a load-bearing input to an AG spend.

Until then: this note is the record. Composes with `standing_spendability.py` (sibling seam
on the freshness axis), `clock_witness.py` (the monotonic-basis discipline a token would
reuse), and the conservation law that found it.
