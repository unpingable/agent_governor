# Status — public-mvp ("First Visitors")

As of 2026-07-05. Campaign card ratified by operator (plan approved this
session). Canonical plan: `CAMPAIGN.md` (this dir). Sprint queue: S1 hygiene →
S2 stranger path → S3 refusal gallery + non-grant list + NQ flagship → S4
contract v1 + maude M-4 → S5 front door + Fable doc-coherence pass; parallel
lanes P (porter v0.1), S (spine read-plane v0), U (gov-webui desk mode).

## Sprint 1 — "Truth on disk"

- **1.1 Push AG local commits — CLOSED, NO-OP (2026-07-05).** Reality check:
  `origin/main..main` = 0 ahead / 0 behind at `3c9b1d3`, tree clean. The
  REENTRY "13 commits LOCAL/unpushed" claim was stale (work landed 2026-07-04).
  REENTRY push-state note should be refreshed in the S2 doc pass.
- **1.2 Land maude allow_dirty fix — CLOSED, NO-OP (2026-07-05).** maude main
  `6501016` clean, 0/0 vs origin. The CD-4B "uncommitted harness fix" was
  already landed as the plan-runner governance-binding commit.
- **1.3 Porter initial commit — DONE (2026-07-05).** Survey correction: porter
  was NOT design-only — `porterlib/` (ssh/serial/recipe/runner/record/cli/api,
  ~2.4k lines) + 13-test suite existed untracked. Suite verified bare:
  `PYTEST_EXIT=0` (masked-exit discipline observed). `.gitignore` extended to
  exclude `.claude/settings.local.json`; NOTICE already carried
  "Copyright 2026 James Beck" (no `{{YEAR}}` placeholder found — survey claim
  wrong). Committed + pushed: **`235c33a`** → github.com/unpingable/porter
  (Sunday push window, operator-approved). Two ag-bwrap-substrate cage
  attestation specimens included (lab evidence, `confirms_isolation=false`
  honest). Committing ≠ ratifying record.v0 for external consumers.
- **1.4 NQ posture reconciliation — DONE (2026-07-05).** Project memory
  updated: "SECRET" label removed from index + visibility ruling recorded in
  `nq_governor_steals.md` (PUBLIC, flagship, **optional for AG — never a hard
  requirement**). Campaign memory pointer created (`campaign_public_mvp.md`).
  The public-facing relationship note itself is S3 packet 9.
- **1.5 Campaign card + STATUS — DONE (2026-07-05).** This dir.

**Sprint 1 exit ticket:** all five packets closed (two as verified no-ops —
the packet shape caught stale survey claims before they became public story,
which is the point). Pushed heads: AG `3c9b1d3`, maude `6501016`, porter
`235c33a`. Receipts: porter suite bare exit 0 (pre-commit); no other test
surfaces touched. **Cargo verdict:** every repo the MVP will cite has a public
HEAD. **Dogfood verdict:** packet shapes worked; discovery-vs-reality drift
(1.1/1.2/1.3 all wrong in surveys) says S2's fresh-clone verification must
trust nothing but exit codes.

## Sprint 2 — "Stranger path" (CLOSED 2026-07-05)

- **2.1 Fresh-clone demo verification — DONE.** Clean clone + fresh venv,
  README followed literally. ONE obstruction: bare `pip install -e .` broke the
  demo (`ModuleNotFoundError: yaml` — pyyaml lived only in the `[webui]`
  extra while the demo imports `playbooks/spec.py`). **Fixed** (pyyaml →
  base deps, `a784364`), re-verified in a fresh venv (install 0, import 0).
  After fix: all three demo scripts exit 0 on a fresh clone.
- **2.2 TOUR.md — DONE** (`a784364`). Stranger-facing three-act walkthrough;
  linked docs + clone URL verified; CANDIDATE, not minted.
- **2.3 GOVERNED_WORKFLOW.md — DONE** (`303486b`). propose→verify→apply +
  two refusal modes, every command executed. One grade-inflation fixed at
  review ("cannot forge" → tamper-evident-not-tamper-proof, bootstrap limit
  stated). Doc-pass backlog (S5): `governor receipts` doesn't surface
  proposal receipts; `receipts --evidence` undocumented in --help.
- **2.4 specimens/README.md — DONE** (`0b42cb0`). All 5 digests +
  admission_ref/receipt_id cross-check re-verified live. **Adversarial
  sandwich fired a real BLOCK:** witness verification was mis-attributed to
  the queue parser (static boolean, no filesystem — `playbook_queue.py`);
  actual seam is plan admission (`work_container.py` approval_ref → witness
  file, `governance_approval_unverified`). Rewritten as the two-seam split.
- **2.5 Maude live-daemon smoke — DONE, both layers PASS**
  (`receipts-s2-maude-smoke.md`). Real daemon (99 RPC methods), five RPCs
  exit 0; QUEUE/SESSIONS/ADAPTERS mounted via maude's Pilot harness against
  the live socket, zero exceptions; adapters rows mirror the raw RPC payload
  (live data, not fixture); maude live-integration suite 32 pass/1 skip.
  **Risk R6 retired.** Friction filed: `governor serve --socket <deep path>`
  → raw `OSError: AF_UNIX path too long` (serve-lane hardening candidate).

**Obstruction (tooling, campaign-wide):** codex-exec's read-only sandbox is
DEAD on this host (`bwrap: loopback: Failed RTM_NEWADDR` — same AppArmor
userns wall as AGY-1); codex honestly refused to review. Substitute: Opus
refute-mode subagent (used for 2.4) or inline-content prompts. Memory updated.

**Sprint 2 exit ticket — cargo:** all five packets closed; four docs live on
main as CANDIDATE; demo path verified stranger-runnable end-to-end; maude
desk surfaces have a live-daemon receipt. **Dogfood:** the packet shapes
carried — fresh-clone verification caught a real Track-B killer (pyyaml),
and the adversarial sandwich caught a real narration-as-authority BLOCK;
neither would have surfaced from happy-path review.

## Lane re-scopes (from S2-wave audits)

- **Lane P (porter) — much smaller than planned.** Audit verdict: all three
  substrates + record.v0 + refusal semantics IMPLEMENTED+TESTED (13 tests,
  exit 0). Remaining: **P11-R** (M: `--env KEY=VAL` injection recording keys
  never values + dirty-worktree annotation at push), **P12-R** (S: scrub
  `outputs/ag-bwrap-substrate/` — AG vocabulary violates porter's own
  domain-separation charter, F6 — + golden fixture full-shape pin), **P13-R**
  (S: `demo/refused-exit.sh` recipe-substrate refusal specimen + README
  quickstart verification vs a real ssh host). F4/F5 stay soft-fenced.
- **Lane S (spine) — engine already BUILT.** 141 tests green at `16ef81f`;
  README "not yet started"/"build system TBD" is stale. Design note landed
  (spine `c26576e`, CANDIDATE): plan collapses to S-A (de-stale docs),
  S-B (public-mvp specimen manifest + edition), S-C (stranger runbook),
  S-D (packaging, conditional). **5 operator questions parked** — OQ-1
  distribution naming gates S-D; OQ-2 status-sourcing gates S-B; OQ-3
  edition timestamp; OQ-4 stele scope; OQ-5 ingress framing.

## Sprint 3 — "Refusal gallery + non-grant list + NQ flagship" (CLOSED 2026-07-05)

- **6+7 Refusal gallery — DONE** (`9f19a23`, `docs/REFUSAL_GALLERY.md`).
  EIGHT organs live-verified same-day (AG, NQ, Nightshift, Wicket, Standing,
  Continuity, Porter, Verifier) — verbatim excerpts, typed reasons, honest
  exit-code semantics (verdict tools exit 0 on refusal; blocking tools
  nonzero). All runnable by a stranger, no network/LLM/live infra.
- **8 NON_GRANTS.md — DONE** (`9d6e7b4`). Nine entries (7 planned + drills
  fence + fail-closed pre-tool gate), 25+ pinning tests run green.
  **Adversarial sandwich BLOCKed with 4 pointer-precision defects, all
  applied** (test node-id qualifier; nested hookSpecificOutput wire shape;
  hook error-path line range; outer-cage re-caveated — ration card is the
  binding seam, cage is defense-in-depth). Substance of all nine held.
- **9 NQ_RELATIONSHIP.md — DONE** (`bff54d0`). Optional-witness rule pinned;
  wire-only coupling documented with read-verified pointers; integrator
  caught two errors pre-commit (constant-name vs wire value
  `origin_unrecognized`; Night Shift repo moved scheduler→nightshift —
  memory pointer fixed too).
- **9b NQ flagship evidence — DONE** (in `bff54d0`). Stranger run: build
  exit 0, live findings, and the hero specimen — `preflight disk-state`
  verifies disk occupancy while refusing SEVEN consequence claims in one
  receipt. Verdict: "usable by a normal SRE today." 4 friction items = NQ
  docs gaps (ports-in-use, /api/query endpoint, receipt-check flag,
  hostname WARN) — NQ's lane.

## Lane status after S3 wave

- **Lane P (porter) — COMPLETE except P11-R.** `e64b3f6` (P12-R: AG-vocab
  specimens scrubbed — porter's own charter F6 — golden fixture full-shape
  pin + no-AG-vocab tree test) + `6986914` (P13-R: `demo/refused-exit.sh`,
  exits 1 with `outcome: refused` / `exit_code_observed: false`). Suite 14
  green, pushed. Remaining: P11-R (env injection + dirty-tree annotation, M).
- **Lane S (spine) — S-A DONE** (`e198390` + `c435cf4` pushed: README/
  REENTRY/CLAUDE/AGENTS de-staled, specimen-at-front commands live-verified,
  doctrine verbatim). S-B/S-D still gated on operator OQ-1/OQ-2.
- **Lane U (gov-webui) — U1 audit DONE** (report in transcript). Better than
  feared: all 19 governor imports OK on 2.8.1, webui's own 481 tests exit 0,
  live curl smoke mostly 200s. U2 fix list (5 bounded items: version string,
  optional chat model field, COMPAT.md staleness, /api/state 404, one
  daemon-side bug). U3 desk-mode design ready: DaemonShellClient over the
  SAME socket framing + ag_shell_client typed models, /desk/* routes with
  the GS-3 one-mutation-door invariant, desk.html three panels, parity pin +
  live smoke, nav entry. 5 packets (U3-A..E).

## New AG-lane bug (filed by U1 audit, NOT fixed inline)

**intent-compiler receipt_hash non-determinism:** daemon injects
`datetime.now().isoformat()` into `IntentFormResponse.timestamp` which is
included in `_compilation_receipt_hash` — same compile input → different
hash per call, contradicting the "content-addressed" comment and breaking
contract tests. Authority-adjacent (receipt hashing) → needs its own packet
with Opus review + pinning test. Also: maude contract-test drift (stub
lacks `list_runs()`; `RPCError` vs `httpx.HTTPStatusError` expectations) —
maude's lane.

## Sprint 4 — "Contract v1 + Maude M-4" (build work CLOSED 2026-07-05;
ratification act pending)

- **14 Ratification memo — DONE** (`68eae6e`,
  `ratification-memo-work-container-v1.md`). Binds 4 docs + 4 schemas by
  digest; evidence chain (CD-4B → S4 projection → S4b resolvable admission →
  structural registry); names the honest wrinkle (projection direction
  proven, consumption direction gated) and recommends **Option A: graded
  ratification** (v1; claude_code STRUCTURALLY conformant + live supervised
  evidence; runtime consumption explicitly gated). ~~**OPERATOR ACT PENDING.**~~
  **RATIFIED 2026-07-05 — executed `74dcf86`** ("RATIFY: work-container
  contract v1 — Option A (operator act, 2026-07-05)", contained in
  `origin/main`). Audit correction 2026-07-15: the pending claim was stale
  against this campaign's own `launch-checklist.md:15` (☑ RATIFIED, same
  commit) and against the commit itself. Operator act 1 is DONE; the other
  operator acts (mint, spine OQ-1/OQ-2, repo-visibility, fresh-clone run)
  are unaffected.
- **15 Maude M-4 run report — DONE** (maude `afc2a68`+`704f86b`, pushed).
  Pure composer over existing reads only (session.get/events, promotion.get,
  plan envelope, co-located ReviewPacket); surface/detail/law disclosure via
  labels.py; `report <session_id> [plan.md]` command + law layer one `why`
  away. Disciplines pinned by test: honest absence ("not recorded", never
  inferred), testimony-not-admission (exit 0 is a report, never "passed";
  used>granted renders OVERRUN, never "authorized"; criteria render
  UNCHECKED). 301 pass/24 skip, ruff clean, integrator re-verified bare.
  v0 exclusions recorded (no auto-trigger, no export, no auto-judging).
- **16 M-3 harness picker — DELIBERATELY DROPPED** by the worker: correct
  M-3 touches the launch path + fake-client tests across several files —
  a separate packet's care; half-shipping would under-close. Re-queue post-S5.
- **17 maude harness fix** — pre-closed in Sprint 1 (already landed).
- **AG intent-compiler hash fix — DONE** (`97e29d7`, pushed). Invariant:
  same input → same compilation receipt hash; timestamp is metadata
  (gate_receipt precedent; payload-exclusion, field kept). Two injection
  sites found (daemon.py:1276+1304). Stored-artifact impact: none (hash not
  chained/persisted). New pins green; **full suite 16727 pass/49 skip
  EXIT=0**; targeted re-verify by integrator.

## Lanes after S4 wave

- **Lane P — COMPLETE** (`6f8441a` pushed): P11-R env injection (keys
  recorded, values proven absent from record+transcripts via sentinel test)
  + dirty-worktree annotation (note, not verdict) + `--worktree`. Suite 19
  green. Porter v0.1 charter commitments: all closed except the two
  deliberately soft-fenced items (F4 transcript volume, F5 run-state locks).
- **Lane S** — S-A done; **OQ-1..OQ-5 RULED 2026-07-16** (spine `739fa0f`:
  rulings recorded + rebar applied — `status_quote` schema fix from the
  failed stele falsification pass, loud provisional-ingress callout; 148
  green). S-B/S-C/S-D unblocked, in that order; S-D opens with the
  `spine-readplane` dist rename.
- **Lane U** — U2 DONE (webui `b0c99e4`: version single-sourced, model
  optional, /api/state wired, COMPAT current) + U3-A DONE (`d70a673`:
  DaemonShellClient over the same framing; 12 daemon methods
  name-verified; ag_shell_client models VENDORED with drift-risk header —
  packaging: no PyPI release of the lib; one-mutation-door pin
  `test_resolve_passes_args_verbatim`). Suite 513 pass/3 skip. Remote fixed
  to SSH + pushed. Remaining: U3-B (/desk routes — codex/Opus sandwich
  mandatory), U3-C (desk.html), U3-D (parity pin + live smoke), U3-E (nav
  + docs).

## Sprint 5 — "Front door + coherence + launch" (build work CLOSED 2026-07-05)

- **18 Constellation map page — DONE** (unpingable-site `e829b38` +
  story-pass `d98b3ad` + `cea34a0`; **4 commits LOCAL — deploy is the
  operator's act**). NQ first, composition-not-prerequisite up front, grades
  sourced; Fable pass caught vscode grade inflation (then U5 ran and
  verified for real) + trimmed an unverified NQ capability.
- **19 Cross-links** — folded into 18 (map links all repos) + AG README
  "go deeper" line (item 4). Per-repo reverse links deferred to post-launch
  (low value vs. spend).
- **20 Coherence pass — DONE** (`d2f615f`, `coherence-pass.md`): per-repo
  fix lists; items 2–6, 11–13, 18 ALL APPLIED same-day (AG `590bd6e`,
  maude `3b68a1a`, AG integration `65a39a8` — contract suite 8-fail → 50
  green; porter `7d4a686`; vscode `43f283e` — U5 verified vs 2.8.1, 176
  tests; site limits paragraph `d4b61e3`). NQ items 7–10 remain offers.
- **20b Reconciliation sweep — DONE 2026-07-05** (superseding the earlier
  PARTIAL note below; reconciled 2026-07-14). The independent-eyes re-run
  completed: 7 findings, all applied; site pushed `52413b4` (positioning intro
  + sweep fixes). See launch-checklist act 6. _(Historical: the first Opus
  sweep died on the monthly spend limit; a mechanical grep-class sweep ran
  inline — gemini-as-live/NQ-required/site-links CLEAN, two residues fixed
  `006bfeb`; the owed independent re-run then landed at 52413b4.)_
- **21 Launch checklist + DoD walk — DONE** (`launch-checklist.md`, this
  commit): 8 of 10 DoD criteria ☑; remaining ☐ are operator acts
  (ratification; operator fresh-clone run; desk live smoke; 20b re-run;
  repo-visibility check; site deploy; mint) + spine OQs.
- **22 Demo script** — CAMPAIGN §13 Tracks A–D stand as the script; site
  demo.html verified consistent with TOUR (item 18). Recording = operator
  option.
- **Desk adversarial sandwich (lane U) — BLOCK → FIXED:** F1 "one mutation
  door" wording false (three mutating routes) → corrected everywhere;
  F2 proceed scope/expiry laundering → daemon-side hardening `2990ed6`
  (forged scope pinned inert). F5/F6 notes (desk GET/SSE unauthenticated by
  app-wide posture; UI sends no bearer token, fails safe) → post-launch
  follow-ups.

## 20b independent sweep — RE-RUN COMPLETE (2026-07-05, post-RC-0)

Independent Opus sweep over the full stranger set (6 site pages, 7 AG docs,
6 README fronts; re-derived the integrator's pre-pass rather than trusting
it). **Verdict: NOT LAUNCH-COHERENT — narrowly; 7 findings, all text edits,
ALL APPLIED same-day:**
- **F1 (blocking, stale):** README hero listed Gemini CLI as a live governed
  backend — fixed per the existing "gemini defunct" ruling (AG `f38e3d3`).
- **F2 (blocking, grade inflation):** index.html badged nightshift
  `operational`, the exact maturity-parity-with-NQ the operator forbade →
  `specimen` (site `52413b4`).
- **F3/F4 (blocking, stale):** README advertised the deleted mcp_safety
  module and linked retired Guvnah → fixed (AG `f38e3d3`).
- **F5:** maude README claimed M-3 shipped (a coherence-applier error the
  integrator's review missed) → back to planned (maude `6f4b7d5`).
- **F6/F7 (low):** constellation one-door residual clarified; hub badges
  aligned to constellation grades (site `52413b4`).

**Clean classes (explicit):** admission-language leaks EMPTY; vocabulary
imports EMPTY; internal link rot EMPTY; positioning coherence EMPTY
(front-door claim matched by every linked doc); exit-code semantics,
two-seam approval split, and NQ-optionality all consistent. With the seven
fixes applied, the blocking subset is clear — **launch-checklist act 6 is
CLOSED**; the sweep's full report is in the session transcript, summary
here is the record.

**Note for the operator:** F1's fix implements your 2026-07-04 ruling; if
Gemini CLI is ever meant to return as a supported backend, that's a new
ruling + the GAP-M fail-open fix first.

## Campaign state: BUILD WORK COMPLETE — operator acts remain

Everything model-side is done and pushed. The launch path is
`launch-checklist.md` §Operator acts (8 steps, in order: ratify → spine
OQs → repo-visibility check → operator fresh-clone → desk live smoke →
20b re-run → site deploy → mint). Nothing armed anywhere; all public docs
CANDIDATE until the mint.
