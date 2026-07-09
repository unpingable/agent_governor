# Status — nightshift-functional-mvp

Card ratified 2026-07-05. Gap assessment done (65% of lane exists; 6+1 packets).

## Done

- **NS-0 DONE (2026-07-05):** the model pin threads end-to-end — maude
  `run <plan.md> --model X` (maude `442703e`, tests + refusal path) →
  `runtime.session.create` `harness_args` (strings-only, fail-closed; AG
  `f51e866`) → `SessionRecord` → `LaunchConfig.args` → claude CLI argv
  (adapter already extended cmd). Model choice = operator's run-time spend
  decision, never plan-envelope content. Both suites green.

- **NS-1 STAGED (2026-07-05 staged; 2026-07-09 REPAIRED, candidate):**
  `specimens/ns-1-refusal-registry/` — the first governed build packet, a
  **live maude-supervised run**, staged for operator approval. All artifacts
  authored + digested via the REAL landed classes; staging receipts
  (re-verified 2026-07-09):
  - playbook.yaml → `parse_playbook` = `PlaybookSpec` (`sha256:0c0f0973…`)
  - ration_card.json → `RationCard`, locked axes hold, shell allowlist
    `cargo test`/`cargo build` (`sha256:90ea2a86…`)
  - plan.md → parses in maude's envelope parser; admission **REFUSES**
    `governance_not_approved` even with the witness resolver pointed at the
    dir (born-candidate rule holds — only the operator's approval act clears
    it). This refusal is the on-path staging receipt.
  - **post-flip dry-run (throwaway copy):** `governance_status: approved` +
    `approval_ref` → admission PASSES, `governed=True`, three citations
    (`playbook_digest`/`ration_card_digest`/`approval_ref`) all `verified`.
    The operator's act will admit; the post-approval path is proven sound.

- **NS-1 dry-run caught a real defect (2026-07-09), specimen repaired.**
  A pre-flip dry-run on a throwaway copy found the original `queue.json`
  (synthetic-conveyor `PlaybookQueue`) was a dead limb on a live-run
  specimen: (a) `maude run` never calls the queue parser — off the execution
  path entirely; (b) internally impossible — `subprocess: true` (needed for
  `cargo test`) under `mode: synthetic_conveyor` requires fully-closed
  authority, so latching `operator_approved: true` would NOT have cleared it
  (`authority_not_closed` waited underneath the reported `not_operator_
  approved`). The documented flip would have broken in the operator's hands.
  Fix: `queue.json` removed, the `queued_playbook_ref` projection dropped
  from `plan.md`, README staging receipts + flip procedure rewritten to the
  pure live-run path. The synthetic-conveyor queue seam stays demonstrated
  by the CD-4B corpus + refusal gallery — it just doesn't belong here.

## Awaiting operator (NS-1 approval)

Approval procedure in `specimens/ns-1-refusal-registry/README.md`: create
witness file (`operator_plan_approved_<date>`) → promote plan
(`governance_status: approved` + `approval_ref` naming the witness) →
`maude run …/ns-1-refusal-registry/plan.md --model claude-haiku-4-5` →
approve/deny tool calls → `report <sid>` → keep/discard. If haiku fails the
packet twice, escalate the MODEL (sonnet), never the authority.

## Queued

NS-2..6 to be authored as maude governed plans (`specimens/ns-*/`) after the
NS-1 flip proves the loop. NS-3 and NS-5 carry the adversarial sandwich
(fail-closed gate refactor; vocabulary-boundary plan-envelope exporter).
