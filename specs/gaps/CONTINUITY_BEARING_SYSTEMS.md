# CONTINUITY_BEARING_SYSTEMS

## Status
Proposed (2026-04-17)

## Origin
Surfaced during nq/labelwatch integration work — the forcing function for
Night Shift promotion/authority design. Phoenix-pattern critique drafted
in session against an external model ("chatty"). Captured here because
the distinction sharpens Governor's constitutional grammar, not because
it requires immediate implementation.

## Thesis

Service resurrection is not object preservation. Three capabilities get
routinely conflated:

| Property | Question | Domain |
|----------|----------|--------|
| Rebuildability | Can I make a fresh instance? | Infrastructure |
| Recoverability | Can I restore the thing that mattered? | State |
| Continuity | Is this the same system across failure? | Identity / lineage |

Phoenix workflows deliver the first and rhetorically smuggle in the
other two. For systems where historical accumulation is part of the
object being governed, that's not recovery. It's amputation.

## Definition: Continuity-Bearing System

A system whose historical accumulation, lineage, or state trajectory
is part of the object being governed or observed — where past state
is **constitutive, not incidental**.

Examples in the Agent Governor constellation:
- Receipt ledgers (hash-chained, append-only)
- Gate receipt store + evidence store
- Scar / shield provenance
- Session continuity capsules
- NQ histories and findings
- Observatories (Labelwatch, Driftwatch)
- Schedulers with standing/intent (Night Shift)
- Continuity cross-session memory
- ATProto / PDS-style record streams

## The Rule

1. **Classification precedes recovery policy.** Each governed system
   must be classified continuity-bearing or stateless before failure
   handling is specified.

2. **Rebuildability MUST NOT be treated as a substitute for
   recoverability or continuity** on continuity-bearing systems.

3. **A restart that does not preserve the lineage required to
   establish sameness MUST be treated as a visible rupture**, not
   as transparent recovery.

4. **Recovery claims on continuity-bearing systems MUST carry proof
   of preserved lineage** (hash-chain continuity, receipt lineage,
   capsule resume, etc.). Absent such proof, the event is a rupture,
   and downstream consumers are entitled to treat the post-restart
   system as a new instance for standing purposes.

## Lemma

> If failure handling erases the evidence needed to understand the
> failure, it is not recovery. It is amputation.

## Dual with `authority_plane=degraded`

Phoenix and `degraded` are dual failure shapes of the same refusal
to observe:

- `degraded` = present-but-wrong; language claims "fine" while
  evidence says otherwise.
- phoenix = absent-dressed-as-present; language claims "recovered"
  while the evidence was erased.

Both require mechanical refusal to accept the narrated version.
Both are NLAI cases at the infrastructure layer.

## Where This Already Lives (existing enforcement surfaces)

| Surface | What it already enforces |
|---------|--------------------------|
| Gate receipt chain | Hash-chained lineage — a break is mechanically visible. |
| Scars / shields | Failures leave marks with hysteresis. |
| Session continuity capsules | Resume = intent + constraints + authority, not chat replay. |
| Append-only ledgers (FactLedger, DecisionLedger, EpistemicLedger) | No silent erasure. |
| Receipt kernel (libs/receipt_kernel) | Append-only, WAL-mode, content-addressed. |

The rule names what these collectively already enforce: phoenix
semantics on a continuity-bearing system is a constitutional
violation, not a maintenance choice.

## What's Genuinely New

- A **named classification** (continuity-bearing vs stateless) that
  downstream specs can declare against.
- A **rupture-visibility requirement** distinct from scar emission:
  rupture is about lineage breaks across restart boundaries, not
  action-level failures.
- A **standing consequence**: post-rupture, the system is a new
  instance for standing purposes unless lineage is explicitly
  preserved.

## Non-Goals

- Does not specify a receipt schema for "rupture event." Implementation
  detail; depends on which substrate records the boundary.
- Does not enumerate classification for every governed system.
  Classification happens per-system at spec time.
- Does not forbid phoenix patterns for genuinely stateless systems
  (stateless cache layers, scratch compute, etc.).
- Does not define how much lineage must survive — "enough to
  establish sameness" is deliberately left to per-system spec.
- Does not commit to enforcement mechanism. The rule lands when
  downstream specs start declaring against it.

## Open Questions

- Is continuity-bearing classification a declaration on the system's
  spec, or derivable from the presence of append-only / hash-chain
  structures?
- What is the minimum evidence for "preserved lineage" at a rupture
  boundary? Hash of prior tail? Signed checkpoint? Depends on
  substrate.
- Does this rule interact with Night Shift's `authority_plane=absent`
  — i.e., is a phoenix-style Governor restart that reports `present`
  a constitutional violation if the receipt chain didn't survive?

## References

- `STRUCTURED_EVIDENCE_AND_PROMOTION_GAP.md` §7 — `authority_plane`
  enum; degraded as dual failure shape.
- `src/governor/session_continuity.py` — capsule-based session
  resumption, existing pattern for continuity preservation.
- `src/governor/scars.py` — failure provenance with hysteresis.
- `libs/receipt_kernel/` — hash-chained append-only substrate.
- `specs/gaps/RELATIONAL_INVARIANTS.md` — cross-trace properties
  (adjacent but distinct — relational invariants compare traces;
  this spec classifies subjects).
