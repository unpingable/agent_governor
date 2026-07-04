# Status — conveyor dogfood

As of 2026-07-04 evening. **CD-0..CD-3 DONE; CD-4 STAGED at the execution
seam** (one operator-driven live run from closing). Pushed heads: **AG
`c3e95c0`**, **maude `015de38`** (both `origin/main`, clean). Maude remote
fixed 2026-07-04 → github.com/unpingable/maude (was local-only; 22 commits
now safe).

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

- **CD-3 DONE (2026-07-04):** maude M-2 landed (`dc71045`). `src/maude/plan/`
  — M-1 parser with all five refusal classes; three-valued strict admission
  (governed plans fail CLOSED without a resolved witness);
  `run <plan.md>` maps to the existing daemon surface, zero contract changes.
  ROADMAP M-2 checked. **Witness-default wired (`015de38`):** the
  TUI-registered runner defaults its resolver to the plan file's own
  directory (the CD-4 co-located layout) — without this a promoted governed
  plan would still have refused `governance_approval_unverified`; fail-closed
  preserved. maude suite 276 green + ruff clean.

## Staged (awaiting operator acts + live daemon)

- **CD-4 STAGED (2026-07-04):** `specimens/cd4-docs-normalize/` — playbook
  spec (parses via landed parser) + ration card (landed class, locked axes) +
  unapproved queue item + **born-candidate** governed plan envelope. Witness
  resolver landed in maude (`plan/witness.py`: content-addressed digest
  lookup — filenames carry no authority; missing dir fails closed).
  End-to-end verified: the real plan parses in maude M-2; admission refuses
  `governance_not_approved` even WITH witnesses present; both digest
  citations resolve against the real artifacts. Remaining: the operator's
  two acts (queue latch + plan promotion w/ approval witness) and a live
  daemon for the supervised run — which doubles as the owed M-2 + desk-screen
  live smoke. Flip procedure: specimen README.md.

## Next (ratified sequence, 2026-07-04)

1. **CD-4 live run — the OPERATOR's seat, not an agent's.** The hypothesis
   under test is "a human can drive governed infrastructure work without
   speaking fluent internal AG vocabulary" — an agent puppeting the TUI would
   skip exactly that. Steps: daemon up → open maude desk → latch the queue
   item → promote the plan (approval witness file) → `run …/cd4-docs-normalize/plan.md`
   → approve/refuse supervised tool calls from the queue screen → review the
   packet. **Record where the UI was legible vs. ontology-heavy** — that log
   is M-4 fuel. Stop-and-obstruct if: witness resolution still fails; approval/
   promotion is ambiguous; any synthetic/generated actor appears able to
   self-approve; a plan says "approved" with no independent latch; tool-call
   approval feels like hidden execution; or the ReviewPacket is valid-but-
   human-hostile.
2. **M-4 — run report** against the real CD-4 packet: the card-plus-expandable-
   law-view pattern (CAMPAIGN §UI pattern seed) becoming code — "precise law
   underneath, ordinary work language on top." The first artifact rendered as
   product, not substrate dump.
3. **GS-13** — why/help/command-palette overlays; retires maude's nav-key
   sprawl (flagged at GS-10b leg 3c) once there's a real report to navigate.

**Bigger AG planning item, named not started — "make the law portable":** a
stable EXPORTED conveyor projection (QueuedPlaybookRef / RationCardRef /
ReviewPacket / ApprovalWitness / ConstraintProjection / GovernedPlanBinding +
refusal classes + digest/citation rules + authority axes) so maude / Night
Shift / NQ consume a serialized surface, never AG internals. This is the
CD-1a "no import coupling" rule graduating from prose to a real artifact;
gate it after CD-4 proves the shape. Do NOT start before the live run.

**Parked operator rulings (from the morning, dependency-ordered for later):**
C2 read-plane trio → C2 wicket-guard absorption → GS-2b admissibility/HELD →
B5 stale-basis mapping → B5 request-side linearity / LA fence → Q-B7 v7
profile promotion. None block CD-4.
