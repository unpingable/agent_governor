# NS-1 specimen — refusal registry (staged, unapproved)

Everything here is **candidate**. Nothing in this directory approves
anything; the operator's flip below is the approval act.

## Staging receipts (2026-07-05, integrator-staged)

| Check | Result |
|---|---|
| `playbook.yaml` parses via `governor.playbooks.spec.parse_playbook` | PASS → `PlaybookSpec`; digest `sha256:0c0f0973…` |
| `ration_card.json` constructs via `RationCard(**…)` | PASS (locked axes hold: git/doctrine/network False, observe-only True; shell allowlist exactly `cargo test`, `cargo build`); digest `sha256:90ea2a86…` |
| `queue.json` refused by `PlaybookQueue.from_manifest_dict` | PASS (the refusal IS the receipt): `QueueValidationError [not_operator_approved] item 'feat.nightshift-refusal-registry' is not operator_approved (missing or false); provenance does not grant approval` |
| `plan.md` parses in maude's envelope parser | PASS → `PlanEnvelope`, `governed: True` |
| `plan.md` admission (maude `admit_for_execution`, resolver → this dir) | REFUSES `governance_not_approved`: "candidate plans are compilable and inspectable, never executed" — the born-candidate rule holds *even with the witness resolver pointed here*; only the operator's flip clears it |

## The flip (operator acts, in order)

1. Latch the queue: set `operator_approved: true` in `queue.json` (the
   parser will then construct it; its post-latch digest becomes
   `queued_playbook_ref`).
2. Record the act: create the witness file
   `operator_queued_playbook.operator_approved_<date>` in this directory
   (content: one line naming what you approved and when).
3. Promote the plan: in `plan.md` set `governance_status: approved`, add
   `approval_ref: "<witness filename>"` and
   `queued_playbook_ref: "sha256:<post-latch queue.json digest>"`.
4. Run it, pinning the model (your run-time spend choice):

   ```
   maude run docs/campaigns/nightshift-functional-mvp/specimens/ns-1-refusal-registry/plan.md --model claude-haiku-4-5
   ```

   The witness resolver defaults to this directory (CD-4 layout). Approve
   or deny tool calls from the queue screen; `cargo test` inside the
   session is the mechanical verdict.
5. Review: `report <session_id> <plan.md path>` in maude → keep/discard.
   If haiku fails the packet twice, escalate the MODEL (sonnet), never
   the authority.

Dogfood verdict to record in the campaign STATUS afterward: did the small
model carry the Rust work; where did maude's surface bind.
