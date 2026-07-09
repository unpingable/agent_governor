# NS-1 specimen — refusal registry (staged, unapproved)

Everything here is **candidate**. Nothing in this directory approves
anything; the operator's approval act below is the approval.

NS-1 is a **live maude-supervised run** — the first governed build packet
carried by a SMALLER MODEL under supervision (the dogfood). Its pipeline is
`maude run plan.md` → admission → `runtime.session.create` → the claude_code
adapter runs `cargo test` in the nightshift workspace. It is **not** a
synthetic-conveyor review-packet job, so there is no `queue.json` here:
`maude run` never invokes the synthetic-conveyor queue parser (a dry-run
against a mismatched queue caught that conflation before the flip — see the
history note at the bottom).

## The authority envelope

| File | Role | Digest |
|---|---|---|
| `playbook.yaml` | the packet spec (what to do) | `sha256:0c0f0973…` |
| `ration_card.json` | the resource envelope (what it may use) | `sha256:90ea2a86…` |
| `plan.md` | the governed maude plan envelope (born **candidate**) | cites the two digests above + an approval witness |

## Staging receipts (verified 2026-07-09, integrator-staged)

| Check | Result |
|---|---|
| `playbook.yaml` parses via `governor.playbooks.spec.parse_playbook` | PASS → `PlaybookSpec`; digest `sha256:0c0f0973…` |
| `ration_card.json` constructs via `RationCard(**…)` | PASS (locked axes hold: git/doctrine/network False, observe-only True; shell allowlist exactly `cargo test`, `cargo build`); digest `sha256:90ea2a86…` |
| `plan.md` parses in maude's envelope parser | PASS → `PlanEnvelope`, `governed: True` |
| `plan.md` admission (maude `admit_for_execution`, resolver → this dir) | **REFUSES** `governance_not_approved`: "candidate plans are compilable and inspectable, never executable" — the born-candidate rule holds *even with the witness resolver pointed here*; only the operator's approval act clears it. **This refusal is the staging receipt.** |
| **Post-flip path (dry-run on a throwaway copy)** | PASS — with `governance_status: approved` + `approval_ref` naming a present witness file, admission returns `governed=True` with `playbook_digest`, `ration_card_digest`, `approval_ref` all `verified`. The operator's act will admit; the loop's post-approval path is sound. |

## The flip (operator acts, in order)

1. **Record the act.** Create the witness file
   `operator_plan_approved_<date>` in this directory (content: one line
   naming what you approved and when). This is the external evidence the
   plan's `approval_ref` will cite — a status field is never its own
   evidence.
2. **Promote the plan.** In `plan.md`, set `governance_status: approved`
   and add `approval_ref: "<witness filename>"` under `governance:`.
3. **Run it, pinning the model** (your run-time spend choice — deliberately
   NOT a field in the envelope):

   ```
   maude run docs/campaigns/nightshift-functional-mvp/specimens/ns-1-refusal-registry/plan.md --model claude-haiku-4-5
   ```

   The witness resolver defaults to this directory (CD-4 layout). Approve
   or deny tool calls from the queue screen; `cargo test` inside the
   session is the mechanical verdict.
4. **Review.** `report <session_id> <plan.md path>` in maude → keep/discard.
   If haiku fails the packet twice, escalate the **model** (sonnet), never
   the authority.

Dogfood verdict to record in the campaign STATUS afterward: did the small
model carry the Rust work; where did maude's surface bind.

---

### History note (why there is no queue.json)

The first staging of NS-1 included a `queue.json` (synthetic-conveyor
`PlaybookQueue`) and a queue-latch step. A pre-flip dry-run on a throwaway
copy found it was a dead limb: (a) `maude run` never calls the queue
parser, so it was off the execution path; and (b) it was internally
impossible — it declared `subprocess: true` (needed for `cargo test`)
under `mode: synthetic_conveyor`, which requires fully-closed authority, so
latching `operator_approved: true` would not have cleared it (a second
`authority_not_closed` refusal waited underneath). The queue and its latch
step were removed. The synthetic-conveyor queue seam is a real organ,
demonstrated by the CD-4B corpus and the refusal gallery — it just does not
belong on a live-run specimen. The born-candidate discipline for *this*
run is the plan-admission refusal above, which is the correct on-path seam.
