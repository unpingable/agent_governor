---
plan_version: 0
goal: "Normalize terminology/help wording across docs/playbooks/* per the landed glossary (zero semantic changes)"
workspace: "/home/jbeck/git/agent_gov"
submitter_kind: human
plan_origin: imported_from_review
provenance:
  author: "operator"
  ref: "conveyor-dogfood CD-4"
harness: claude_code
scope_allowlist:
  - "docs/playbooks/**"
  - "docs/campaigns/conveyor-dogfood/specimens/cd4-docs-normalize/**"
steps:
  - "Read docs/playbooks/glossary.md; it is the vocabulary authority for this pass"
  - "Normalize term usage across docs/playbooks/*.md (PlaybookSpec, CertifiedPlaybook, RunRequest, ReviewPacket, RationCard used consistently)"
  - "Reconcile the duplicated live-adapter-allowlist-review content from the two branch lineages"
acceptance_criteria:
  - "Zero semantic changes to any contract or exit ticket's meaning"
  - "pytest tests/playbooks stays green"
  - "Diff confined to docs/playbooks/* (+ this specimen dir)"
stop_conditions:
  budget_tokens: 150000
  forbidden_paths: ["src/**", "tests/**", "specs/**", ".governor/**", "docs/roadmaps/**"]
  halt_if: "a wording change would alter a contract's meaning, or the glossary itself needs semantic amendment"
governance:
  authority_system: ag
  playbook_id: "chore.docs-playbooks-normalize"
  playbook_digest: "sha256:a8e2caf97e59bdacf988a3a2f73ef1f347b37dcacf513634e667c75aed481524"
  ration_card_digest: "sha256:c55509c5049ce7c826833c2b07101342e1225f139da05735f3615416b9249bd0"
  governance_status: approved
  approval_ref: "operator_queued_playbook.operator_approved_2026-07-04"
  queued_playbook_ref: "sha256:45741e3a6600b80bf47bf0e6d5d00ee953524b6dfea1460a486337fdc225eee3"
  projected:
    scope_allowlist: "ration_card:sha256:c55509c5049ce7c826833c2b07101342e1225f139da05735f3615416b9249bd0"
    stop_conditions.forbidden_paths: "queued_playbook:conveyor-dogfood-cd4/chore.docs-playbooks-normalize"
---

Specimen 2 of the conveyor-dogfood campaign — the two-receipt-surface run.
This plan was compiled by the session (maude-lane structure) and is therefore
**born `candidate`** per the M-1 admission rule: a compiler cannot approve its
own plan by writing the word.

The AG conveyor surface (queue.json in this directory, currently
`operator_approved: false`) answers whether this work SHAPE is admissible.
This envelope answers what exact run instance executes it. Neither certifies
the other; the run must emit both receipt surfaces separately.

Flip procedure at operator approval (documented in README.md here): latch the
queue item, record the approval act as a witness file, set
`governance_status: approved` + `approval_ref` + `queued_playbook_ref` (the
post-latch queue digest), and run `run <this file>` in maude with the witness
resolver pointed at this directory.
