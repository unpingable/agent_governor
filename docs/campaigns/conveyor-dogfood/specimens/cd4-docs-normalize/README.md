# CD-4 specimen — STAGED, awaiting the operator's two acts + a live daemon

Everything up to the execution seam is built and verified (2026-07-04):

- `playbook.yaml` — `governed-playbook.v0`, parses via the landed
  `parse_playbook` (digest `sha256:a8e2caf9…`).
- `ration_card.json` — constructed via the landed `RationCard` (locked axes
  hold), serialized deterministically (digest `sha256:c55509c5…`).
- `queue.json` — the CD-4 conveyor item, `operator_approved: false`. Per the
  CD-2 finding it will not even PARSE until latched — by design.
- `plan.md` — the M-1 governed envelope, **born `candidate`**. Verified
  end-to-end against maude M-2: parses; admission refuses
  `governance_not_approved` even with witnesses present; both digest
  citations RESOLVE against the real artifact files via
  `file_witness_resolver(this directory)`.

## Flip procedure (operator acts — nothing here executes without them)

1. **Latch the queue item:** set `operator_approved: true` in `queue.json`,
   citing your act (as in CD-2's `approval.md`).
2. **Record the approval witness:** write the act record to a file in this
   directory named `sanitize_ref(approval_ref)` (e.g.
   `operator_queued_playbook.operator_approved_2026-07-XX`).
3. **Promote the plan:** set `governance_status: approved`, add
   `approval_ref` matching the witness filename's original ref, and
   `queued_playbook_ref` = sha256 of the post-latch `queue.json` bytes.
4. **Run it** (needs a live governor daemon): in maude,
   `run docs/campaigns/conveyor-dogfood/specimens/cd4-docs-normalize/plan.md`
   with the witness resolver pointed at this directory. This is also the
   owed live-daemon smoke for M-2 and the GS-10b desk screens.
5. **Two receipt surfaces, separately:** the conveyor artifacts (queue,
   latch, ReviewPacket from the run) witness the AG governance exercise; the
   maude run record (plan_ref, projected constraints, session receipts)
   witnesses envelope enforcement. Neither cites the other as proof.

Stop-lines from the queue item and `halt_if` apply verbatim.
