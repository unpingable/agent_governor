# The Borrow Ledger

> **Status: descriptive doctrine, non-binding.** A custody ledger for *concepts* — where
> AG's primitives were borrowed from, and (mandatory) where each analogy breaks. Its job is
> provenance and anti-novelty-laundering, **not** a design gate. The load-bearing extraction
> (a boundary-review checklist) is named at the bottom as a candidate, deliberately *not*
> ratified here — collapsing the two makes the doctrine performative. (2026-06-24)

## Thesis

AG is not inventing admissibility from vibes. Every mature discipline that had to operate under
the same two constraints — **no trusted global state** and a **genuine adversary or failure
mode** — independently evolved the *same* family of boundary defenses: separate the observer
from the adjudicator, make state expire, carry provenance inside the record, treat absence as
ambiguous, refuse to promote what doesn't reconcile. AG's contribution is to state those
primitives **once**, abstractly, with a type system, so they stop being re-derived per domain.

That convergence is the actual argument for the project. The risk is that a convergence argument
is one cherry-pick away from being a crank's mood board. So this ledger has a firewall (below).

## Inclusion filter (the engine)

A domain belongs here only if it operated under **all three**:

1. **No trusted global state** — no oracle, no authoritative complete view.
2. **A real adversary or failure mode** — parties lie, nodes drop, fraud is the design premise.
3. **Real consequences for promoting a bad claim** — a mistaken "this is true/authorized/fresh"
   costs something.

Miss any one and the analogy is decoration, not evidence.

## The crank firewall (mandatory)

**Every row must name where the analogy breaks.** A row that only confirms is incense. The
disanalogy is what converts "another field agrees with me" into "I borrowed X but not Y, and
here's the Y that doesn't transfer." No break named → the row is not admissible here.

## Six families

| Family | Domains (under fire) | Primitive learned |
| --- | --- | --- |
| **Evidence** | law, intelligence analysis, science, incident investigation | testimony is scoped and defeasible; the witness ≠ the adjudicator |
| **Ledger** | accounting, finance, databases | a transition requires a *balanced custody protocol*, not intent + a log line |
| **Authority** | standing, object-capabilities, access control | possession / name / signature is not permission |
| **Measurement** | RF & distributed routing, metrology, monitoring | an observation carries its instrument and medium limits |
| **Control** | cybernetics, aviation safety, ops | an admitted signal may actuate; a raw signal may not |
| **Provenance** | PKI / CT, SLSA, build systems, supply chain | artifacts need lineage; lineage is not truth |

The other domains are **suspects in a lineup — guilty-looking but uncharged.** One row is fully
worked below; the rest are named, not elaborated, until a forcing case charges them.

## The one fully-worked row — Measurement / distributed routing

*(Worked because AG already shipped its convergence case, by accident, this week.)*

- **Primitive borrowed.** Soft state with expiry (freshness). Sequence numbers (ordering carried
  *inside* the testimony, because arrival order ≠ event order). **Path-carried advertisement**
  (path-vector / link-state) so a loop is detectable. Relay provenance.
- **Native failure mode — count-to-infinity.** A *distance-vector* failure: a node advertises a
  summary metric ("distance 3") with **no path**, so it can't tell the path loops through
  itself; stale state then propagates as fresh truth, and relayed state reflected back
  masquerades as independent confirmation (split horizon / poisoned reverse exist entirely to
  stop this). It is a chronopolitics failure: commitment outran verification.
- **AG equivalent — AG is path-vector, not distance-vector.** AG chains carry their derivation:
  `parent_receipt_ids` + the `governor why` walk are the AS-path, so a loop is *detectable* —
  the reason count-to-infinity can't happen in a why-walkable chain. Shipped instances:
  - `resolve_closure` (playbooks Slice 2, `closure.py`) refuses `ImportCycleError` by checking
    whether a spec's digest is already on the resolution **path** — split-horizon by construction,
    not a generic no-loops check.
  - `playbook_spec_digest` (authored ref — "I reference X") vs `dependency_closure_digest`
    (resolved content — "X resolved to these bytes") is direct-vs-relay testimony kept separate:
    changing X's content moves the closure digest but not the root's claim. *No free smoothie.*
  - NQ freshness / "not heard ≠ absent" is soft-state expiry: silence is ambiguous information,
    encoded distinctly from "gone."
- **Forbidden collapse.** "heard via relay" → "directly observed"; a digest/summary without its
  path treated as self-confirming; silence treated as absence.
- **Where the analogy breaks.** Routing optimizes for **convergence to a single answer** — all
  nodes agree on one route, and metric minimization picks "best." AG does the opposite on
  purpose: it does **not** seek global convergence, has no "best," and treats two observers
  disagreeing as an *admissibility event*, not an error to converge away. Borrow the
  loop-detection-via-carried-path discipline; do **not** borrow the converge-to-one-truth
  objective or the metric.
- **Keeper.** *No witness smuggles omniscience through a map pin.* / *Bad governance chains fail
  like distance-vector; admissible chains behave like path-vector.*

## Charged later, not now (suspects)

Named so the recognition isn't lost; **not** elaborated until a forcing case (each must pass the
inclusion filter *and* produce a named break):

- **Accounting** — double-entry as a 500-year admissibility kernel (unbalanced = refusal). Break:
  it assumes a single trusted ledger operator AG explicitly refuses.
- **PKI / SLSA** — *signed is not witnessed*; revocation is a freshness problem. Break: lineage
  proves who held a key, not what happened.
- **Object-capabilities** — *addressability is not authority*; attenuation, no ambient authority.
- **Databases** — reserve/commit/abort, fencing tokens, idempotency; *a log entry is not a commit
  unless the protocol says so*. (Already partly in the substrate.)
- **Metrology** — calibration, uncertainty, traceability; *a reading without calibration is a
  rumor with decimals*.
- **Control / aviation** — *a signal is not a control signal until admitted*; a sensor may not
  self-promote into an actuator. Break: control theory wants stable convergence; AG wants
  admissible refusal.
- **Intelligence analysis** — source reliability vs information credibility; corroboration ≠
  summation. Break: politically/ethically radioactive — take the type system, not the tradecraft.
- **Insurance adjudication** — *denied, uncovered, and insufficiently-evidenced are different
  verdicts* (the refusal taxonomy in a cheap suit).

## The extracted discipline (candidate — NOT ratified, NOT a gate)

The *load-bearing* version of this ledger is **not** this document. It is a narrow boundary-review
checklist, deferred until a forcing case appears (likely `docs/review/boundary-review-checklist.md`).
Recorded here so it isn't re-derived, explicitly non-binding — making the borrow-ledger itself
normative would turn it into a theology checkpoint ("identify your ancient-discipline Pokémon
before adding an organ"). The candidate questions, for any proposed new organ/boundary:

1. What claim is being promoted?
2. What witness/custody **path** supports it?
3. What stale / relayed / summary state could masquerade as fresh / direct / pathful?
4. What forbidden collapse does this design refuse?
5. Where does the analogy to prior art break?

Promote to a gate only when an organ actually tries to smuggle summary state across a boundary
and this checklist would have caught it. Until then: descriptive provenance, anti-crank hygiene.
