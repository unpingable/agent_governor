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

- **CD-4-pre DONE (2026-07-04) — maude legibility pass (V1 vocab + V2 law
  view + bounded polish).** Surfaced because CD-4 partly measures operator
  legibility; old ontology labels would contaminate that signal. maude
  `f094571` (3 commits, pushed: `9f93d3e` V1 core, `a05a2e1` supervised flow,
  `f094571` polish).

  **Cargo verdict:** new `src/maude/labels.py` presentation layer (three-layer
  disclosure — surface / detail / law) keyed on the CONTRACT codes, which are
  only rendered, never renamed. Plain-ops rewrite across the whole live-run
  path: plan runner (`Plan refused→Blocked`, `admitted→OK — starting run`,
  `witnessed citations→verified references`, `projected→limit enforced from`,
  `ungoverned→plain run`), status bar (`MODE=/SPEC=/GOV=→mode:/spec:/policy:`),
  supervised flow (`promotion→changes`, `promote/reject→keep/discard` w/ new
  aliases incl. `supervised keep|discard <id>`; `Session created/exited→Run
  started/finished`; `Pending Violation→Blocked — needs your call`;
  `Anchor:→Rule:`; `COMMUNICATE→External send`), headers (`Governor
  Status→Status`, `violations→blocked`, `Session Lineage→Where am I`, `Session
  Tree→Run tree`, `Operator Snapshot→Now — what's happening`). **V2 law view:**
  raw cybernetics off the surface, one `why` away (plan-block drilldown wired +
  tested). RPC method names + wire contract untouched. **281 passed, 24
  skipped; ruff clean** (+6 tests: law-view disclosure, keep/discard aliases).

  **Dogfood verdict (feeds M-4):** the three-layer disclosure holds — a human
  reads plain ops first, drills to the law only on `why`. Two findings banked:
  (1) the **queue-desk decision cards** render AG *daemon* vocab verbatim by
  design ("the daemon's vocabulary IS the keymap"), so plainer wording there is
  an AG-side change to `operator.decisions`, NOT a maude rename — left as-is so
  CD-4 can measure whether it actually bites; (2) **External send** is
  channel-generic (email = current specimen) → recorded, not stubbed:
  `docs/candidates/COMMUNICATION_ADAPTERS.md`. Deferred (non-blocking):
  queue-desk law-view expand, full run/session vocabulary split, the
  CommunicationIntent object, lower-priority maude surfaces (session-mgmt /
  history). Backlog: none opened.

  **CD-4 is now teed up on the plainer surface.** Backend reality: the two
  supervised adapters are `claude_code` and `gemini_cli`, but **gemini is
  defunct** (2026-07-04), so `claude_code` is the only live supervised backend.
  The run therefore spends from the general Claude pool — bounded by the
  specimen's 150k token budget. Operator call: spend it now, or defer the live
  run to the weekly reset. (A local/ollama supervised adapter does not exist —
  ollama is a chat backend only — so "run CD-4 on qwen" would be net-new
  adapter work, out of this slice's scope.)

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

**"Make the law portable" — CONTRACT ARTIFACT STARTED (2026-07-04); live
wiring still gated on CD-4.** A stable EXPORTED conveyor projection
(QueuedPlaybookRef / RationCardRef / ReviewPacket / ApprovalWitness /
ConstraintProjection / GovernedPlanBinding + refusal classes + digest/citation
rules + authority axes) so maude / Night Shift / NQ / Antigravity consume a
serialized surface, never AG internals. Forced forward by gemini's death (the
`gemini_cli` adapter is defunct) + the intent to be usable by others: AG talks
to a **provider/agent contract**, not to Maude directly. **Landed this slice
(contract artifacts only, mints nothing):** `docs/api/work-container-contract.md`
(deepest) + `agent-integration.md` + `provider-integration.md`, and
`schemas/{work_container,provider_descriptor,provider_run_receipt,provider_obstruction}.v1.json`
(DRAFT). Build vector: Slice 2 ProviderRegistry primitive (gated on contract
review) → Slice 3 conforming descriptors → **Slice 4 live governed_dispatch
wiring (gated on CD-4)** → Slice 5 Antigravity spike. Playbooks demoted to one
origin format (compiles into WorkContainer), not the spine. Plan:
`~/.claude/plans/okay-two-things-1-luminous-bee.md`.

**Parked operator rulings (from the morning, dependency-ordered for later):**
C2 read-plane trio → C2 wicket-guard absorption → GS-2b admissibility/HELD →
B5 stale-basis mapping → B5 request-side linearity / LA fence → Q-B7 v7
profile promotion. None block CD-4.
