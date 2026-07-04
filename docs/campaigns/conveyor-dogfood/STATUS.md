# Status — conveyor dogfood

As of 2026-07-04 (campaign filed; CD-0 landing in progress).

## Done

- **CD-0 LANDED (2026-07-04):** merges `a803b7b` (gov-loop) + `57b383e`
  (synthetic conveyor) on main; tips preserved at `refs/preserve/playbooks-*`.
  Receipts: merge 1 full suite `[pass]` `bb380cbe`; merge 2 full suite
  `[pass]` `01a9bfaa` after the curated-CLI repair (state-index taxonomy +
  `_populate_advanced` ordering — see LANDING.md; two guardrail catches, both
  the gates working). playbooks+harness 311 passed; ruff clean; REENTRY +
  feature-history updated. Landing ≠ operational promotion — classification
  in LANDING.md; C11/seccomp + H2 stay unarmed.
- **CD-1 capsule filed** (this doc set): rulings CD-D1..D4 recorded before
  slice 1 per campaign-card discipline.

- **CD-1a DONE (2026-07-04):** M-1 governance binding landed in maude
  (`ab1e30c`, `docs/specs/plan-envelope-v0.md` §7 + field table + 2 new
  refusals). Sandwiched: codex BLOCK caught approval-by-narration (a written
  `approved` is prose until the act is independently witnessed →
  `governance_approval_unverified`, no downgrade-to-ungoverned path) and the
  unverified-citation leak (governed execution requires every load-bearing
  citation VERIFIED); re-review PASS. Projection made exhaustive;
  review_packet_ref back-fill report-side only.

- **CD-2 DONE (2026-07-04) — the first governed conveyor run.** Specimen
  artifacts: `specimens/cd2-state-index-roadmap-kind/` (queue.json,
  approval.md, review_packet.json, validation.json, required_test_receipt
  `33805137` [pass], fullsuite_receipt `ad422772` [pass]).
  Work: state_index_export scans docs/roadmaps/ — tools/*.md → the ONE new
  kind `tool_roadmap` (17 live records); hub files fall through
  kind_ambiguous honestly; determinism + existing kinds pinned unchanged;
  backlog stub → done.

  **What the run PROVED about the conveyor:** the queue parser refuses
  invented source vocabulary (`unknown_source_kind` caught `backlog_item`)
  and refuses to even construct an unapproved item
  (`not_operator_approved` — "provenance does not grant approval"), so a
  queue file is definitionally a record of approved work and candidate
  staging belongs to the M-1 envelope lane; the fence is write-only
  (validator checks `files_changed`), verified before execution per the
  operator's approval condition; `validate_review_packet_for_queue_item`
  passed the packet (valid + ready_for_operator_apply, zero issues)
  including the used≤granted authority accounting with the test run
  attributed to the harness lane via the independent verify-run receipt.

  **What the run did NOT prove:** nothing about maude (no envelope, no M-2 —
  receipt-separation clause unexercised); nothing about the sealed-handoff /
  actor-normalizer path (the actor was this session, not an external sealed
  actor — HandoffRenderer/ActorOutputNormalizer remain exercised only by
  their tests); nothing about live cage execution (inert per LANDING).
  Commit authority was session-lane (operator direct), not conveyor-granted
  — recorded in approval.md.

- **CD-3 DONE (2026-07-04):** maude M-2 landed (`dc71045`, maude repo —
  local-only by remote config). `src/maude/plan/` — M-1 parser with all five
  refusal classes; three-valued strict admission (governed plans fail CLOSED
  with no witness resolver — CD-4 wires the conveyor projection);
  `run <plan.md>` maps to the existing daemon surface, zero contract changes.
  maude suite 272 green + ruff clean; ROADMAP M-2 checked. Live-daemon smoke
  owed at next daemon-up.

## Not started

- CD-4 (specimen 2: playbook docs normalization via maude M-2 + conveyor,
  two receipt surfaces — includes wiring the v0 witness resolver to the
  conveyor artifacts).
