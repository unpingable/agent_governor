# Status — nightshift-functional-mvp

Card ratified 2026-07-05. Gap assessment done (65% of lane exists; 6+1 packets).

## Done

- **NS-0 DONE (2026-07-05):** the model pin threads end-to-end — maude
  `run <plan.md> --model X` (maude `442703e`, tests + refusal path) →
  `runtime.session.create` `harness_args` (strings-only, fail-closed; AG
  `f51e866`) → `SessionRecord` → `LaunchConfig.args` → claude CLI argv
  (adapter already extended cmd). Model choice = operator's run-time spend
  decision, never plan-envelope content. Both suites green.

- **NS-1 STAGED (2026-07-05, candidate — AG `f00386f`, local):**
  `specimens/ns-1-refusal-registry/` — the first governed build packet,
  staged for operator flip. All artifacts authored + digested via the REAL
  landed classes; staging receipts (all verified):
  - playbook.yaml → `parse_playbook` = `PlaybookSpec` (`sha256:0c0f0973…`)
  - ration_card.json → `RationCard`, locked axes hold, shell allowlist
    `cargo test`/`cargo build` (`sha256:90ea2a86…`)
  - queue.json → `PlaybookQueue.from_manifest_dict` **REFUSES**
    `not_operator_approved` ("provenance does not grant approval") — the
    staging receipt
  - plan.md → parses in maude's envelope parser; admission **REFUSES**
    `governance_not_approved` even with the witness resolver pointed at the
    dir (born-candidate rule holds — only the operator's flip clears it)

## Awaiting operator (NS-1 flip)

Flip procedure in `specimens/ns-1-refusal-registry/README.md`: latch queue
(`operator_approved: true`) → witness file → promote plan
(`governance_status: approved` + `approval_ref` + `queued_playbook_ref`) →
`maude run …/ns-1-refusal-registry/plan.md --model claude-haiku-4-5` →
approve/deny tool calls → `report <sid>` → keep/discard. If haiku fails the
packet twice, escalate the MODEL (sonnet), never the authority.

## Queued

NS-2..6 to be authored as maude governed plans (`specimens/ns-*/`) after the
NS-1 flip proves the loop. NS-3 and NS-5 carry the adversarial sandwich
(fail-closed gate refactor; vocabulary-boundary plan-envelope exporter).
