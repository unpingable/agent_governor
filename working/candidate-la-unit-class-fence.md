# Candidate: LA unit-class fence (Wall 2 of the simulated-evidence fence)

**Status: candidate / NOT built. Cross-repo contract change — requires
coordination with `~/git/linearaccountant`.** Filed 2026-06-12.

Reserved refusal kind: `unit_origin_mismatch` (NOT yet added to any closed set).

## What this is

The second wall of the simulated-evidence fence, ratified decision-grade
2026-06-12 alongside Wall 1. Wall 1 (the operational-consequence type split +
`confer_operational_effect` spend seam) **shipped** in this slice
(`cooked_context_orchestrator.py`). Wall 2 is the arithmetic complement and is
**named here, not built**, because it reaches into capacity semantics that
`~/git/linearaccountant` owns.

The operator's framing:

> What units did the drill consume? If drill chains draw from the operational
> pool, drills deplete real capacity and the labeling question gets harder. But
> units carry provenance — so drill chains spend *drill-class units*, deposited
> under drill origin, and the spend-time check is class-matching: operational
> spends name operational units, drill spends name drill units, cross-class
> refused as `unit_origin_mismatch`. Then a drill chain mechanically, genuinely
> consumes — exactly-once fully exercised, conservation holds per-class, the
> all-green test stays green because the consumption is real consumption *of
> simulated capacity* — and operational effect is unreachable not because a flag
> said so but because the drill literally cannot name an operational unit as
> input. The fence stops being a checkpoint and becomes arithmetic.

## Why it is not built in the Wall 1 slice

Three reasons, each independently sufficient:

1. **Ownership.** Unit provenance, unit class, and per-class conservation are
   Linear Accountant internals. In the AG SPEC-harness the unit is opaque
   (`CookedConsumeRequest.token_id: Any`, "opaque; LA owns the type"). AG is a
   named consumer that **never mints** capacity (cf.
   `memory/linearaccountant_repo`, `docs/constellation-zoning.md` §Linear
   Accountant). AG cannot unilaterally define what a "drill-class unit" is.

2. **Vocabulary.** `unit_origin_mismatch` is **not** one of LA's seven
   `ConsumptionDecision` variants (Consumed / AlreadyConsumed /
   InsufficientCapacity / Expired / Revoked / UnknownToken / ScopeMismatch).
   Adding it is a change to LA's `lib.rs` decision enum **and** to AG's mirrored
   `CLOSED_REFUSAL_KINDS` (`linear_accountant_client.py`). That is a coordinated
   two-sided migration, exactly the kind the wiring invariant forbids slipping
   into an adapter change (see `docs/constellation-wire-plan.md` §wiring
   invariant: a live transport needing a new refusal kind is a *seam change*,
   not a wiring change).

3. **Redundancy for the launch need.** The operator's own words: Wall 2 "makes
   the first one almost redundant." Wall 1 already makes a non-operational spend
   *unrepresentable* at the AG seam (type wall + runtime `isinstance` + negative
   pinning tests). Wall 2 is defense-in-depth via arithmetic — strictly stronger
   (it removes the *possibility* of even naming an operational unit), but not
   launch-blocking. The launch-blocking fence is shipped.

## The one-way door (record before it costs anything)

Per zoning §Linear Accountant, unit individuation vs. pooling is a **one-way
door**: a fungible pool destroys deposit provenance permanently at deposit, and
with it the very class-matching Wall 2 needs. So Wall 2 is only buildable if LA
units are **individuated and carry deposit-origin provenance** (UTXO-shaped).
If LA ever pools capacity, Wall 2 becomes impossible to retrofit. This is the
load-bearing zoning constraint to preserve on the LA side regardless of when
Wall 2 is built.

## Forcing case to build

Wall 2 earns construction when a real refusal cannot be expressed without it —
concretely: **a path exists where a drill/synthetic chain could draw from the
operational capacity pool** (deplete real budget, or — worse — name an
operational unit as a consume input and slip past Wall 1's type seam via some
future non-orchestrator spend path). Until such a path exists, Wall 1 holds the
boundary and Wall 2 stays a named handle.

## Build sketch (when thawed, LA-side-led)

- LA deposits carry `origin_class` provenance on each unit (drill / synthetic /
  replay / observed / …), set at deposit time from the depositing chain's
  origin_mode. (LA `lib.rs`.)
- LA `consume` checks the consuming request's declared class against the unit's
  deposit class; cross-class → new `ConsumptionDecision::UnitOriginMismatch`.
- AG mirrors the variant: add `unit_origin_mismatch` to `CLOSED_REFUSAL_KINDS`
  and the S3 decision→refusal mapping in `linear_accountant_client.py`.
- Per-class conservation invariant: the partition sum holds within each origin
  class, never across (a drill consume cannot reduce the observed-class balance).
- Negative pinning test (Wall 2's teeth): a consume request naming an
  operational unit under a drill chain MUST return `unit_origin_mismatch`.

## Cross-references

- `docs/constellation-wire-plan.md` — Wall 1/2 live in the Codex/LA seam rows;
  the wiring invariant governs the vocabulary-change discipline.
- `docs/constellation-zoning.md` §Linear Accountant — unit individuation
  one-way door; `memory/linearaccountant_repo` — packet boundary, never-mints.
- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — eligibility ≠
  capacity; Wall 2 is the per-class form of "capacity is individuated".
- Wall 1 (shipped): `src/governor/cooked_context_orchestrator.py`
  (`OperationalConsumed` / `DemonstratedConsumed` / `confer_operational_effect`),
  `tests/test_operational_spend_fence.py`.
