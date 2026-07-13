# Design — S7: Ration Citation Containment

> STATUS: SPEC (operator-scoped, 2026-07-13). The bounded completion of S6's
> contract: an explicit `execution_request` must not merely *cite* a RationCard,
> it must be *contained by* it. Promoted from `GAP-s6-sandwich-authority-
> findings.md` finding 1. Sibling finding 2 (approval-binds-plan-bytes) stays
> parked — a separate threat model, NOT this slice.

## The one sentence

**Citing a ration is not being bounded by it.** S6 made the request legible in
the plan bytes; S7 makes the citation load-bearing: `execution_request ⊆
cited_ration` on every dimension the RationCard actually models.

## In scope

- Admission verifies the cited RationCard **bytes and digest** (already true for
  the digest; S7 adds that the *same verified bytes* are consumed downstream).
- On **every dimension the current RationCard actually models**, require
  `execution_request ⊆ cited_ration`:
  - `execution_request.write_paths ⊆ allowed_write_paths` (path-glob containment
    using the **existing** `grant_use_gate` path semantics — `dir/*` single
    level, `dir/**` any depth; no new glob dialect).
  - `execution_request.commands ⊆ allowed_shell_commands` (argv-structured
    containment using the **existing** `grant_use_gate` command-match semantics,
    including the effect-escaping-flag denylist — the ration strings parse to
    `(program, argv_prefix)` the same way the v0 decoder already parses them).
  - `execution_request.network` may be `requested` only if `network_allowed` is
    true in the ration; likewise `git` vs `git_allowed`. A request for a
    ration-denied axis **refuses** (axis broadening), it does not silently ride
    to `unmet_axes`.
- **Narrower requests admit; broader requests refuse.**
- **Missing citation refuses where containment cannot otherwise be established:**
  a governed v1 plan whose `execution_request` is not cited against a resolvable
  RationCard in `governance.projected` refuses (`ration_citation_required`) —
  you cannot bound against a source you did not name.
- Admission and projection consume the **same verified artifact bytes**. One
  resolver read; the verified ration bytes are threaded from admission to
  projection. This *structurally* closes the S6 TOCTOU (finding 3) — supersedes
  the defensive rehash with single-read custody.

## Explicitly out of scope (classified, not waved through)

- **Dimensions the RationCard cannot presently express** are OUT, named here so
  no fictitious comparison is smuggled in:
  - `horizon` — the ration models no horizon; it stays capped at mint, not
    containment-checked.
  - `doctrine_writes_allowed`, `output_is_observe_only`, `task_kind`,
    `agent_id` — not expressed in `execution_request`; no containment relation.
- **No RationCard schema expansion.** Compare against the fields that exist.
- **No approval-witness changes** (that is finding 2, parked — its own threat
  model and migration).
- **No AG daemon / grant / supervisor / execution-semantics changes.** Maude-
  side admission only.
- **Frozen NS-1 stays frozen.** S7 is not an excuse to re-open the v0 decoder;
  v0 behavior must remain byte-identical.

## Refusal vocabulary

Reuse existing classes; discriminate by detail token. No new refusal class.
- `execution_request_exceeds_ration` — a modeled dimension is broader than the
  cited ration.
- `ration_citation_required` — a governed request with no citable ration to be
  contained by.

## Required adversarial cases (the acceptance pins)

1. Command narrowing **admits** (request ⊆ ration commands).
2. Command broadening **refuses** (a command not in the ration).
3. Prefix / trailing-argument smuggling **refuses** per the existing
   `grant_use_gate` command-match semantics (an allowed prefix must not launder
   an effect-escaping or scope-relocating invocation).
4. Axis broadening **refuses** wherever the ration models that axis
   (`network`/`git` requested against a ration that denies it).
5. Correct citation *identity* with **substituted bytes refuses** (digest names
   ration A, resolver returns bytes B → refuse, not silently accept).
6. A stateful resolver **cannot** supply different admission/projection
   artifacts (single verified read; the projection uses admission's bytes).
7. Citation to an **unrelated but valid** RationCard refuses when the request is
   not contained by *that* card (a real card is not a blank check).
8. Frozen v0 behavior remains **byte-identical** (no regression to the retired
   decoder; its tests unchanged and green).

## Design notes (non-binding, for the builder)

- The containment predicate belongs at **admission** (it needs the resolver and
  is the authority gate); projection then consumes the same verified bytes and
  becomes a pure copy. Candidate shape: `admit_for_execution` returns (or
  caches on the `AdmissionRecord`) the verified ration bytes; the runner passes
  them to `project_execution_request`; the projector no longer calls the
  resolver for the ration at all.
- Reuse `grant_use_gate`'s matching functions directly — do not re-implement
  path or command containment. If they are not import-clean from the plan layer,
  that seam (not a new dialect) is the thing to fix.
- Sandwich this slice too (the adversarial cases above are the refuter's target
  list); land only after it is clean.
