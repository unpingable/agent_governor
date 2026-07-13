# Constellation cartography census — 2026-07-13

**STATUS: census receipt (working note).** Evidence base for
`docs/CONSTELLATION_MAP.md` (CANDIDATE). Method: cold-start recovery test — 13
parallel evidence-card agents over source clusters (AG constellation docs, AG
backlog surfaces, cartography, constellation-artifacts, governor-atlas+claimdocs,
spine, maude, nq-root, lean, continuity, admissibility kernels, execution
substrate, ~/git root meta), each required to quote a textual basis for every
ownership/edge claim, use git freshness, and mark gaps UNKNOWN rather than
improvise. Full cards: workflow `wf_8f19f9bd-e28` journal (session transcript
dir). This note keeps only the verdict and the defect register.

## Verdict

**Outcome 2 — partial maps exist; no artifact claims canonical
constellation-wide status.** Every candidate explicitly disclaims it. The
recoverable pieces:

| Partial map | Covers | Status (self-declared) | Fresh |
|---|---|---|---|
| `docs/agent-governor-meta-plan.md` | planes + per-repo plane ownership + directional kernel | orientation, not ratification | 2026-06-11 |
| `docs/constellation-wire-plan.md` | physical wiring per seam, promotion phases, re-entry probes | PROVISIONAL, non-binding; "code wins" | 2026-07-05 |
| `docs/constellation-zoning.md` | deferred organs, one-way doors, per-organ ownership | PROVISIONAL; self-flagged LLM-relay, unratified | 2026-06-12 |
| `docs/roadmaps/README.md` + PARKED + CONSOLIDATION | membership fence (17 ACTIVE + 9 PARKED), posture, wake triggers, **operator-ratified separations** | LIVE HUB; "what this is not: authority" | 2026-07-02 |
| `docs/design/governed-shell/maude-boundary.md` | maude/AG edge | **RATIFIED** (only ratified bilateral boundary found) | 2026-07-02 |
| `~/git/governor-atlas` `cases/constellation.yaml` | AG↔sibling edges, machine-readable, wired/specified/candidate modes | honest: "filter to wired and the graph nearly empties" | 2026-06-19 |
| `~/git/cartography` | prior map venue | **ARCHIVED — but only in an UNCOMMITTED working-tree edit** (in-content 2026-06-14); successor named as AG zoning+wire-plan | 2026-05-19 (last commit) |

Work topology: `docs/roadmaps/` **is** the existing portfolio (posture + wake
conditions + drift severity); `docs/PROGRAM_LEDGER.md` (2026-07-13) is the
program-state altitude below it. They are different altitudes and should NOT be
merged — but see defect D7.

## Defect register (the map doing its work)

Documentation defects, not build items. Each is a recoverability failure a
cold agent hit.

- **D1 — cartography retirement was uncommitted. RESOLVED 2026-07-13** under
  operator ruling (cartography was a purpose-built coordinator session, since
  absorbed by AG-Claude): archival committed (cartography `b63217d`, pointing
  at `docs/CONSTELLATION_MAP.md`); doctrine-*evolution* claims repointed —
  wicket `docs/INTEROP.md` ("doctrine evolves there" → agent_gov, `0493093`)
  and wlp `WLP_STANDING_BOUNDARY_CROSSREF.md` ("awaiting cartographer
  curation" / "doctrine stays in cartography" → AG intake note, `dda47ba`).
  All local commits, unpushed. **Residue (citations-only, left as valid
  history):** wlp `WLP_STORAGE_TRANSPORT_BOUNDARY.md` (2 archive citations);
  standing `docs/remote-standing-boundary.md` ("convergence is cartography's
  job" — a role assignment now held by AG; standing was not in the ruling's
  enumeration, fix on next standing-side touch) and
  `examples/nq-integration.md` (2 "cartography doctrine" mentions, same
  disposition).
- **D2 — `docs/architecture/OVERVIEW.md` "Constellation" section (2026-06-10)**
  reads as settled (no PROVISIONAL marker), names a stale peer set
  (dossier/custody/audit), and was not updated for the 2026-07-02 UI-shell
  rulings. No supersession marker.
- **D3 — `docs/CLIENT_ECOSYSTEM.md` (2026-02-11)** has no STATUS line at all and
  asserts "Agent Governor is the authority. Clients are views." as settled; 5
  months stale against the roadmaps hub; guvnah retirement not reflected.
- **D4 — nq-witness 5-layer role table** (Witness→NQ→Night Shift→Governor→Human)
  is asserted unilaterally in one README; no reciprocal Governor/Night Shift
  doc found. Not an edge until reciprocated.
- **D5 — Driftwatch/Labelwatch ownership UNKNOWN.** No local repo found; they
  appear only as targets in NQ gap specs. Who owns them is unrecoverable from
  artifacts.
- **D6 — continuity MCP surface broken** at census time: `memory_query_latest`
  returns `no such column: authoring_tier`. The governed-memory recovery path
  is currently dead; recovery ran on files alone (which is the test working,
  but the breakage is real).
- **D7 — the ledger's scope and ingress are insufficiently declared**
  (rescoped 2026-07-13; originally misdiagnosed as "campaigns don't cite it").
  PROGRAM_LEDGER is authoritative for a governed multi-repo *program's*
  sequence — not the universal backlog; `docs/roadmaps/` already owns
  cross-constellation posture/wake/membership. So the fix is NOT conscripting
  all nine campaigns into citing it: *relevant* campaigns (those inside the
  program it enumerates) cite it; unrelated campaigns do not. The cold-start
  ingress order is map → roadmaps hub → active program ledger(s) → campaign
  STATUS. **Partially resolved 2026-07-13:** scope declaration added to the
  ledger header; ingress ordering added to `docs/REENTRY.md`; the five-surface
  routing table enshrined in the map's altitude fence. Remaining: the relevant
  campaigns (nightshift-functional-mvp at minimum) still don't cite the
  ledger; `.governor/campaigns/*.yaml` discovery stubs still cover 2 of ~9.
- **D8 — `~/git/PROJECTS.md` and `~/git/README.md` disagree** on active
  membership and are stale (not git-tracked, self-admittedly out of date).
  Folklore-grade.
- **D9 — `~/git/gap-backlog-inventory.codex.jsonl`** (236 rows, 7 repos,
  mtime 2026-07-11) is a one-shot codex audit, already stale at generation
  (references the retired `scheduler/` path). Useful lead list (103 rows
  "needs producer contract clarification", 86 "stale closed gap sweep"), not a
  backlog home.
- **D10 — empty name reservations:** `~/git/notary`, `~/git/docket` are empty
  directories; nothing states intent. `playbooks-main`, `airlock` are name
  collisions, not members (membership fence vindicated).
- **D11 — governor-atlas receipts** unverified since 2026-06-19 against AG HEAD
  (`claimdocs verify-basis` not run); the machine edge-graph is ~3.5 weeks
  behind, including the S6/S7 grant-use wiring which may flip the maude edge
  from specified to wired.
- **D12 — RRP was unregistered. RESOLVED 2026-07-13 (naturalized same day,
  operator ruling: AG is the registration authority).** Found state: identity
  artifact on disk, **zero commits**; only committed evidence was lean's
  `RRP-LEAN-CROSSWALK.md` ("the crosswalk was more real than the thing it
  described"). Actions: secrets scan clean · `.gitignore` (1.4G `target/`
  excluded) · README §Identity & constellation status (owner, posture =
  prototype/private/no-stability-claim, canonical-state locations, lean
  relationship, initial-import provenance note) · initial import `rrp 9a0abf6`
  (248 files, tree banked as-is) · registered in the map's Nodes table,
  roadmaps hub (ACTIVE 17→18, `tools/rrp.md`), and backlog projection
  (`roadmap-rrp` stub). **Held for push window:** private remote creation +
  push (R-RRP-1) — say the word.

## Backlog reconciliation (2026-07-13, per operator ruling)

The 55 `.governor/backlog/` stubs were reconciled against campaign STATUS
files, PROGRAM_LEDGER, and tool-roadmap status lines; 10 stubs added (7 live
campaigns, the ruled-NEXT program slice, `roadmap-rrp`, the D6
`continuity-authoring-tier-repair` defect). Every stub now carries a clean
closed-vocabulary `status`, `effort_band` (S/M/L, no fake percentages),
`wake_condition` where dormant, `canonical_source`, and a
`reconciled{date,basis,confidence}` block; pre-reconciliation verbose statuses
preserved in `status_note`. 8 stubs are honestly marked `UNKNOWN` confidence
(not verified against a source this pass) rather than guessed. Headline
corrections: `governed-shell` was `filed` while GS-2b..8 had shipped; 5
roadmap-ratification stubs (nq/standing/wicket/lean/tk) were `filed` though
A8 ratified them 2026-07-02.

**The report:** `python3 scripts/portfolio_report.py` — hot fronts, actionable
queue, dormant-with-wake, untrustworthy records; aggregates only, never infers.
**The maintenance loop** (smallest version, now in PROGRAM_LEDGER's update
rule): a closing campaign/slice proposes its stub transition with receipts;
an auditor may flag drift but never closes work.

## Rulings received (operator via relay, 2026-07-13)

- `docs/CONSTELLATION_MAP.md` **adopted as canonical topology index**
  (canonical ≠ complete; the map is where incompleteness is recorded).
- **Cartography archived and absorbed by AG** — it was originally a
  purpose-built coordinator Claude session; AG-Claude now drives that role.
  Archival committed; do not resurrect as a second authority.
- **No CONSTELLATION_PORTFOLIO.md** — refusal confirmed correct.
- **D5 stays an ownership gap** — Driftwatch/Labelwatch are not awarded to
  whichever repo mentions them most.
- **D6 is a live substrate defect**, not cartographic cleanup — owed its own
  repair slice (home: continuity; the `authoring_tier` schema error breaks the
  governed-memory recovery path).
- **D7 rescoped** — declare the ledger's scope/ingress; don't conscript
  unrelated campaigns.
- **D2/D3** — conspicuous staleness/supersession headers first; comprehensive
  rewrites later if ever.

## What was deliberately NOT done

- No edits to sibling repos (including committing cartography's own archival —
  operator's call; it may be someone's in-progress session).
- No PROGRAM_LEDGER entry: the map is topology, the ledger is program state;
  blurring the altitudes is the failure mode this exercise exists to avoid.
- No new CONSTELLATION_PORTFOLIO.md: the roadmaps hub already is the portfolio;
  creating a third overlapping surface would duplicate authority (see map §Work
  topology for the pointer table instead).
