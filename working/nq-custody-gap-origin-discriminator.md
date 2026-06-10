# NQ Custody Gap — Origin Discriminator for Drill / Synthetic / Replay

**Status: cross-repo finding surfaced 2026-06-09 by AG's provenance-field
audit. NOT an AG-side bug; AG cannot fix it from this repo. Filed here
as the AG-side record of a real NQ obligation, so future-AG and
future-NQ sessions both find it.**

This is exactly the shape the operator named when amending the campaign
2026-06-09:

> If injection creates indistinguishable testimony, that's not
> "synthetic demo data." That's the framework catching its own
> witness-layer laundering bug in the mirror, which is funny in the way
> industrial accidents are funny in incident reports.

Treat indistinguishable synthetic testimony as a finding, not a
convenience.

## The gap in one sentence

> NQ has no closed-vocabulary discriminator at finding mint that
> distinguishes drilled / fault-injected / synthetic findings from
> findings produced by authentic observation. The current `origin_source`
> SQL CHECK is sealed to `('nq', 'import')`, and `insert_imported_finding`
> hard-codes `visibility_state = 'observed'` for *every* imported row.
> A drill harness's manifest is byte-identical to a real producer's
> manifest, both at storage (`warning_state`) and on the wire
> (`FindingSnapshot.origin`).

## Evidence (NQ source, grounded by codex/audit pass)

| Surface | File:line | Current state |
| --- | --- | --- |
| Storage CHECK | `~/git/notquery/crates/nq-db/migrations/046_durable_artifact_substrate.sql:26-27` | `origin_source TEXT NOT NULL DEFAULT 'nq' CHECK (origin_source IN ('nq', 'import'))` |
| Wire DTO | `~/git/notquery/crates/nq-db/src/export.rs:161` | `FindingOrigin.source` mirrors the closed set above |
| Import insertion | `~/git/notquery/crates/nq-db/src/import.rs:339-343` | `visibility_state = 'observed'`, `origin_source = 'import'` hard-coded for all imports |
| Observation status (DIFFERENT axis) | `~/git/notquery/crates/nq-db/migrations/049_wal_observation_status.sql:66-69` | `observation_status IN ('observed', 'target_missing', 'permission_denied', 'stat_error')` — substrate observation outcome, NOT mint provenance |
| Producer string | `~/git/notquery/crates/nq-db/src/detect.rs:461-466`, `export.rs:162` | `basis_source_id` / `producer_id` are free-form strings; a consumer cannot trust a string-typed marker as a closed category |

## Why this is the doctrine-correct finding, not just a demo blocker

AG's own anti-laundering doctrine prohibits exactly this shape one
level up:

- `working/directional-invariants.md` invariant 1: *observations may
  raise a standing question; they must not satisfy standing.*
- `working/sentinel-observation-not-authority.md`: *no current AG
  surface authors observation-as-authority* — *guarded topological
  absence, not mechanical refusal.*
- The whole VALIDITY_SPENDABILITY_SPLIT / OUT_OF_SCOPE_RUNTIME_LAUNDERING
  family is about not silently converting one custody class into
  another.

The NQ gap is the same shape one level *deeper*: synthetic testimony
is silently converting into observed testimony at the witness layer
itself. An AG demo that opens on a "live NQ alert" sourced from a
drill manifest would re-enact, inside the demo, exactly the failure
mode the demo is trying to refuse.

## What NQ would have to ratify (recommendation; NOT a demand on NQ)

One of these would close the gap, in increasing surgery cost:

1. **Widen `origin_source` CHECK** to include `'drill'`, `'replay'`,
   `'synthetic'` (or a single `'exercise'` value). Cheapest. Forces a
   migration and a wire-schema bump. Requires AG-side consumers to
   honor the new closed set (they currently see only `'nq'`/`'import'`).
2. **Add a sibling column** `origin_mode TEXT NOT NULL DEFAULT 'observed'
   CHECK (origin_mode IN ('observed', 'drill', 'replay', 'synthetic'))`.
   Keeps `origin_source` semantics intact (ingestion path) and adds a
   distinct axis (mint provenance). Two closed enums, no overload.
3. **Add a typed `Finding.exercise_kind: Option<ExerciseKind>` field**
   with a proper Rust enum. Most surgery; most legible. The "absent =
   real" interpretation is the desirable default.

Option 2 is probably the cleanest because `origin_source` and
`origin_mode` answer different questions:
- `origin_source`: was this minted natively by NQ, or ingested via the
  import wire?
- `origin_mode`: did the producer observe this condition, or stage /
  replay / inject it?

## D0-Origin gate state

**D0-Origin (campaign card §3) may not start** until at least one of:

- NQ ratifies an origin-mode discriminator and exposes it end-to-end
  through `FindingSnapshot` / the import wire / the public Finding
  type, AND
- AG plumbs the inherited discriminator through evidence bundles and
  adds a DRILL-first render branch to `governor why`.

Until then:

- D0-Origin is OPEN-but-gated; D0-Provenance is gated on D0-Origin;
  D0b checkpoint is gated on the real chain landing.
- D0c-b (cooked-context orchestrator) is **not** gated by this — it
  can run on the existing SPEC-honoring stubs without an NQ origin
  link, but the chain it produces will not be drill-distinguishable.
  Operator call whether D0c-b proceeds in parallel with the NQ-side
  ratification.

## Composes with

- `working/campaign-standing-before-spendability.md` §3 D0-Origin /
  D0-Provenance — the slices this finding gates.
- `working/directional-invariants.md` — same shape, one level deeper.
- `working/sentinel-observation-not-authority.md` — the topological-
  absence frame applies: NQ's current state is *guarded topological
  absence* (the laundering doesn't fire today because nobody uses the
  import path for drills), *not mechanical refusal*. The moment a
  drill harness exists, the absence is no longer guarded.
- `memory/nq_governor_steals.md` — NQ pointer.
- `memory/cybernetic_taxonomy.md` — likely covers a "claim-kind
  laundering" failure domain that this slots into.

## Non-goals

- NOT a demand or PR against NQ. The operator runs both repos and
  decides whether/when NQ-side ratification happens.
- NOT a justification to invent an AG-side discriminator that NQ
  doesn't mint ("inheriting a marker NQ never minted is laundering,
  not propagation").
- NOT a demo blocker per se — the demo can land with D0c-a / D0c-b /
  D0d / D0e against a CLI-origin or stub-NQ-origin path; the NQ-origin
  amendment was the *better-doctrine* version, but the original
  CLI-origin path is still admissible if NQ-side ratification slips.
