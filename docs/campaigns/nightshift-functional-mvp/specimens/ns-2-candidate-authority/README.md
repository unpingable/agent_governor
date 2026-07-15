# NS-2 specimen — Candidate authority level (staged, unapproved)

Everything here is **candidate**. Nothing in this directory approves
anything; the operator's approval act below is the approval.

NS-2 is the second governed build packet for a small model under maude
supervision. Deliverable: an explicit `Candidate` authority level in
nightshift between `Advise` and `Stage` — naming the split *fresh enough to
run* vs *approved to promote* — with the ungoverned ceiling capped at
`Candidate` and the docs line "fresh → candidate; Governor approval →
stage/apply". This is the vocabulary NS-5's plan-envelope exporter will map
onto maude's `candidate` posture.

Authored as **plan_version 1 from birth** (S6 `execution_request` +
S7 ration-citation containment). Unlike NS-1 there is no v0 anywhere in this
packet's lineage.

## The authority envelope

| File | Role | Digest (raw file bytes) |
|---|---|---|
| `playbook.yaml` | the packet spec (what to do) | `sha256:b0f87b91…3a097b` |
| `ration_card.json` | the resource envelope (what it may use) | `sha256:c7b487ac…c7d19d0` |
| `plan.md` | the governed v1 plan envelope (born **candidate**) | cites the two digests above + an approval witness |

## Staging receipts (verified 2026-07-15, integrator-staged)

| Check | Result |
|---|---|
| `playbook.yaml` parses via `governor.playbooks.spec.parse_playbook` | PASS → `PlaybookSpec` `nightshift-candidate-authority` |
| `ration_card.json` constructs via `RationCard(**…)` | PASS (locked axes hold: git/doctrine/network False, observe-only True; shell allowlist exactly `cargo test`, `cargo build`) |
| `plan.md` parses in maude's envelope parser | PASS → `PlanEnvelope`, `plan_version: 1`, `execution_request` present |
| `plan.md` admission (maude `admit_for_execution`, resolver → this dir) | **REFUSES** `governance_not_approved`: "candidate plans are compilable and inspectable, never executable" — the born-candidate rule holds. **This refusal is the staging receipt.** |
| **Post-flip path (dry-run on a throwaway copy)** | PASS — with `governance_status: approved` + `approval_ref` naming a witness whose content binds the flipped plan bytes, admission returns `governed=True` with `playbook_digest` / `ration_card_digest` / `approval_ref` all `verified`, and the S7 `verified_ration_bytes` snapshot taken. The post-approval path is proven sound end-to-end, including the seam-B plan-bytes binding. |

## The flip (operator acts, IN THIS ORDER — the order is load-bearing)

NS-1's approval custody was never verifiable afterwards: its plan stayed
`candidate` in the tree and its witness file was not retained. This
procedure closes both gaps. **Promote first, then witness** — promoting the
status changes the plan's bytes, and the witness must bind the bytes that
will actually run.

1. **Promote the plan.** In `plan.md`, set `governance_status: approved`
   and add `approval_ref: "operator_plan_approved_<date>"` under
   `governance:`.
2. **Record the act, binding the exact bytes.** Compute
   `sha256(plan.md bytes)` of the NOW-PROMOTED file and create the witness
   file `operator_plan_approved_<date>` in this directory with content:

   ```json
   {"witness_version": 1, "decision": "approved", "plan_ref": "sha256:<that hash>"}
   ```

   The witness carries the digest of the plan it approves (seam B:
   approval attaches to plan bytes, not reconstructed intent). A status
   field is never its own evidence.
3. **Commit both files** (promoted plan + witness) before the run. The
   witness is a permanent record — it is never deleted, and the plan is
   never edited after promotion. A later schema migration mints an NS-2R
   successor; it does not revise these bytes (S6 ruling).
4. **Run it, pinning the model** (your run-time spend choice — deliberately
   NOT a field in the envelope):

   ```
   maude run docs/campaigns/nightshift-functional-mvp/specimens/ns-2-candidate-authority/plan.md --model <small-model>
   ```

   Approve or deny tool calls from the queue screen; in-envelope
   `cargo test` / `cargo build` calls are grant-compressed (S2b) so you are
   only prompted on material change. `cargo test` inside the session is the
   mechanical verdict.
5. **Review.** `report <session_id> <plan.md path>` in maude →
   keep/discard. If the small model fails the packet twice, escalate the
   **model**, never the authority.

Dogfood verdict to record in the campaign STATUS afterward: did the small
model carry the semantic rename (ungoverned ceiling Advise → Candidate)
without touching anything at or above Stage; did approval compression keep
the prompt count proportional to material change rather than invocation
count.
