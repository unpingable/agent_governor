# Campaign — AG governed self-build (ag-admit)

Stable campaign card. Reproducibility capsule for cold-start discovery: a future
Claude/Codex/gov-loop run reads this directory, replays state, and applies ratified
decisions **without re-asking the operator**. This is inert discovery metadata, NOT live
WIP state (that is `.governor/loop.json`, which this capsule never touches).

Capsule files: [DECISIONS.md](DECISIONS.md) · [GRANTS.yaml](GRANTS.yaml) ·
[REPLAY.md](REPLAY.md) · [STATUS.md](STATUS.md) · [NEXT.md](NEXT.md).
Working-notes lineage (historical): `working/campaign-ag-admit-self-build.md`,
`working/promotion-ag-admit-to-waiver-completeness.md`,
`working/EXIT_2026-06-23_ag-admit-slice3-needs-human.md`,
`working/doctrine-ag-admit-throttle-ladder.md`.

## Question

> Can a candidate change be represented, preflighted, refused, repaired, admitted,
> executed, receipted, and committed — without moving planning, generation, or
> admissibility logic into the conductor?

## Invariant — the conductor stays dumb

It carries a `CandidateStep`, calls `ag_admit`, branches **only** on the returned
`StepVerdict`, runs the allowed path, and writes receipts. It must not decide
admissibility, synthesize authority, parse diffs, reinterpret a verdict by substring, or
rewrite `CANNOT_TESTIFY` into `NEEDS_HUMAN`. The **gate** observes touched paths from the
diff; the conductor never does. Intelligence lives at the two ends (generator proposes,
gate refuses); the middle stays mechanical (`docs/doctrine/specs_do_not_bootstrap.md`).

## Allowed

Thin `ag_admit` adapter over the `PreflightClient` Protocol; a typed `StepVerdict` enum
with a centralized projection in `ag_admit`; narrow in-process gates beside it; a
disposable conductor; throwaway toy repos; receipts for every step event; one promoted
real packet at a time, each behind a witnessed promotion note.

## Forbidden

Self-hosting-first; conductor-side policy/planning; a planner in the middle; silent waiver
synthesis; "best effort" commit after refusal; widening without a witnessed promotion
note; treating execution as admissibility or absence-of-refusal as approval; daemon
rewrite; changes to `governed_dispatch` / `PreflightClient` / the closed verdict/role/kind
enums / the `StepVerdict` projection / conductor authority. (See [GRANTS.yaml](GRANTS.yaml)
for the live forbidden-surface list.)

## Exit conditions

A promoted packet is complete when its trace is reproducible from receipts alone, the
final commit is causally linked to the admission receipt, and all its acceptance criteria
are pinned. Stop with a recorded hand-back when a step cannot be grounded, a repair would
change admission semantics, or a change hits a forbidden surface.

## Current boundary (the live edge)

**Path authority is necessary but not sufficient — it is not semantic authority.** Slice 3
proved it: `gate_receipt.py` sat *inside* the path grant, but the *kind* of change (a
closed-enum widening) was forbidden. `DiffPathScopeGate` cannot see that. The next build
(`ForbiddenSurfaceGate`, see [NEXT.md](NEXT.md)) is the semantic companion that closes this
gap — but the reproducibility capsule (this directory) lands first so that build has
cold-start context instead of a séance.
