# NS-1R — v1 successor specimen (S6)

The **v1 reference specimen** and the cross-repo integration witness for S6
(first-class `execution_request` block). It is the successor to
`../ns-1-refusal-registry/` — same intended operation, **fresh identity**.

## Why a successor, not a rewrite

NS-1 was compiled and executed under the **v0 inferred-request contract** (write
scope from top-level `scope_allowlist`, shell commands pulled from the RationCard
at projection time). Its bytes are frozen and untouched; the historical fact
"NS-1 ran under v0" stays true. Per the S6 doctrine —

> **Approval attaches to plan bytes, not reconstructed intent; schema migration
> creates a successor artifact rather than revising an approved predecessor.**

— migrating the schema produces NS-1R, a new artifact with its own `plan_ref` and
its own approval act. NS-1R inherits NS-1's intent, not NS-1's approval. (The
frozen v0 allowlist holds NS-1's exact hash so it is never reinterpreted as an
"unversioned" plan; see the AG S6 design note.)

## What v1 changed (vs `../ns-1-refusal-registry/plan.md`)

- top-level `scope_allowlist` → `execution_request.write_paths`.
- commands, previously **inferred** from the RationCard at projection time, are
  now **declared** in `execution_request.commands` as structured
  `{program, argv_prefix}` — legible in the bytes the operator approves.
- `network`/`git`/`horizon` are explicit (all conservative here).
- `governance.projected` cites `execution_request.write_paths` /
  `execution_request.commands` against the same RationCard (`sha256:90ea2a86…`),
  so §7 copy-with-citation still binds the request to its AG source.

The RationCard (`ration_card.json`) and playbook (`playbook.yaml`) are unchanged
from NS-1 (same digests) — same authority shape, new request surface.

## Approval + run procedure (born-candidate)

This envelope is `governance_status: candidate`; maude's admission REFUSES it
(`governance_not_approved`) until an operator act promotes it. To run:

1. create a witness file (e.g. `operator_plan_approved_<date>`) beside this plan;
2. promote the plan: set `governance_status: approved` and add
   `approval_ref: "<name of the witness file>"`;
3. `maude run …/ns-1r-refusal-registry-v1/plan.md --model claude-haiku-4-5`;
4. approve/deny tool calls; the approved `execution_request` becomes a grant so
   in-envelope actions do not re-prompt (approval compression);
5. `report <sid>`; keep or discard the diff.

If haiku fails the packet twice, escalate the MODEL (sonnet), never the
authority.

## Integration evidence (S6, verified 2026-07-13)

`integration_check.py` (this dir) drives the full cross-repo chain — v1
specimen → maude parse → admission → projection → AG mint — with **zero AG
daemon edits** (S6 changed how the request becomes explicit, not what the daemon
receives):

```
1. candidate admission refused: governance_not_approved            (born-candidate holds)
2. promoted admission: playbook_digest/ration_card_digest/approval_ref all verified
3. projected execution_request FROM THE BLOCK:
     write_paths: ['crates/nightshiftd/src/*', 'crates/nightshiftd/tests/*']
     commands:    [cargo test, cargo build]   (declared, not inferred)
   AG minted grant: sgr_969f042a617c  enforcement=declared-effects-only  unmet_axes=()
```

The mint used the existing `governor.runtime.execution_grant.activate_execution_grant`
unchanged — evidence the wire boundary was correctly placed.
