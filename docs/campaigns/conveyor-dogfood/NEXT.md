# Next — conveyor-dogfood slices

Six-field shape per `docs/roadmaps/ROUTING.md`. Order: CD-0 → CD-1 → CD-2 →
CD-3 → CD-4; CD-1a (maude spec) may run parallel to CD-2.

### CD-0 — land the conveyor on main
tier: mechanical · executor: fable (this session; merge custody) · prereq: []
- purpose: the dogfood program may cite only main-line law — land both playbook
  branches with surface classification, no operational promotion.
- files: merges of `feat/playbooks-gov-loop` + `feat/playbooks-synthetic-conveyor`;
  LANDING.md; REENTRY.md; feature-history entry.
- tests: full suite via `governor verify-run -- python3 -m pytest tests/ -q`
  after EACH merge (real exit code); `pytest tests/playbooks tests/harness -q`;
  ruff clean.
- refusal mode: n/a (adoption of reviewed work; the branches carried their own
  per-slice sandwiches).
- receipt shape: two merge commits + verify-run receipts + LANDING.md mapping
  branch refs → main commits; tags `landing/playbooks-*` preserve tips.
- stop condition: a merge step requires treating unresolved C11/seccomp/H2
  gates as operationally complete → land only inert/citable substrate or stop.

### CD-1 — campaign capsule (this doc set)
tier: conceptual · executor: fable · prereq: []
- purpose: rulings + invariants + specimen ladder on the record BEFORE slice 1
  (campaign-card discipline).
- files: CAMPAIGN.md, NEXT.md, STATUS.md, DECISIONS.md, LANDING.md.
- tests: doc-only; cross-references resolve.
- refusal mode: n/a. · receipt shape: capsule commit.
- stop condition: none.

### CD-1a — M-1 governance binding (maude repo)
tier: conceptual · executor: fable · prereq: [CD-0]
- purpose: amend `docs/specs/plan-envelope-v0.md` with the `governance:` block
  (authority_system, playbook_id, playbook_digest, ration_card_digest,
  review_packet_ref, queued_playbook_ref [conveyor-routed only], approval_ref,
  governance_status: candidate|approved|refused|obstructed), the constraint-
  projection rule, and the two-receipt-surface invariant. Digest/ref binding
  ONLY — import-coupling to AG internals forbidden until AG mints an exported
  projection.
- files: maude `docs/specs/plan-envelope-v0.md` (+ ROADMAP note).
- tests: doc-only; spec examples parse (`python3 -m json.tool` /yaml check as
  applicable).
- refusal mode: spec adds `governance_status` vocabulary (maude-side law,
  CANDIDATE; no daemon/kernel vocabulary minted).
- receipt shape: maude commit citing this campaign + the ruling; **sandwich:**
  codex-exec review (authority vocabulary touched), BLOCKs adjudicated.
- stop condition: the amendment starts requiring daemon-side support → that is
  CT-1, file and stop.

### CD-2 — dogfood specimen 1: `state-index-roadmap-kind` (pure AG, conveyor-driven)
tier: mechanical (work) + review (packet) · executor: fable-driven via conveyor · prereq: [CD-0, CD-1]
- purpose: first governed meal — extend `state_index_export` to scan
  `docs/roadmaps/` as the named roadmap kind, executed THROUGH the landed
  conveyor law (QueuedPlaybook → operator_approved latch → bounded work →
  ReviewPacket → ReviewPacketValidator).
- files: state_index_export implementation + tests + roadmap/index docs ONLY
  (path fence); `.governor/backlog/state-index-roadmap-kind.json` is the
  objective source; specimen artifacts under the campaign dir.
- tests: acceptance test proves docs/roadmaps/ scanned/exported as intended
  kind; ReviewPacketValidator pass; full suite + ruff via verify-run.
- refusal mode: exercises the conveyor's existing refusals (path-fence
  violation, used>granted, unapproved item) — adds none.
- receipt shape: conveyor artifacts (queued item, approval latch, review
  packet) + work commit citing the queued item digest; STATUS records what the
  run proved about the conveyor and what it did NOT prove (no maude claims).
- stop condition: drift into roadmap taxonomy redesign → STOP, obstruction note.

### CD-3 — maude M-2: plan ingestion, human path, with governance binding
tier: conceptual design + mechanical build · executor: fable · prereq: [CD-1a]
- purpose: `run <plan.md>` per the existing M-series M-2 definition — parse/
  validate M-1 envelopes incl. governance block; client-side digest
  (`plan_ref`); refuse `invalid_plan_envelope` / `submitter_limits_missing` /
  unapproved-when-conveyor-routed; map execution to the EXISTING daemon
  surface (`runtime.session.create` + supervisor intervention/promotion
  gates); obstruction note instead of improvisation.
- files: maude `src/maude/plan/` (new), `src/maude/commands/`, tests (fakes).
- tests: maude pytest green (239-suite + new); no daemon contract changes.
- refusal mode: maude-side envelope refusals (client-side, closed set from
  M-1 + governance_status gate).
- receipt shape: maude commits; run artifacts carry plan_ref + projected-
  constraint record.
- stop condition: any need for a new daemon RPC or feed decision kind →
  CT-1/M-7 lane, stop.

### CD-4 — dogfood specimen 2: playbook docs normalization (two surfaces)
tier: mechanical via governed run · executor: maude M-2 + conveyor · prereq: [CD-2, CD-3]
- purpose: maude executes an approved M-1 envelope whose governance block cites
  a landed playbook digest; task = normalize `docs/playbooks/*` terminology/
  help wording (boring, bounded); emit the TWO receipt surfaces separately.
- files: docs/playbooks/* (bounded), specimen artifacts, campaign STATUS.
- tests: both receipt surfaces present and disjoint; docs diffs within path
  fence; suite + lint green.
- refusal mode: exercises both systems' existing refusals; adds none.
- receipt shape: AG conveyor receipts ∥ maude envelope-enforcement record —
  separate, neither cited as proof of the other.
- stop condition: either surface's success being narrated as evidence for the
  other → STOP.

## Future fuel (recorded, not scoped)

`ag-spec-slice-decomposer` (backlog→envelope front end; composes with M-7
zero-resolve synthetic submitter) · Night Shift R-NS-1/2 (first cross-repo
specimen) · maude GS-13 (overlays; retires nav-key sprawl) / GS-12 (session
view + diff) · CT-1 + candidate-plans-as-feed-decisions (own ratification
gates) · dossier revive ("dogfood on AG's own PRs").
