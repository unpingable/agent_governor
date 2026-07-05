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

## Next

**Sprint 3 — "Refusal gallery + non-grant list + NQ flagship"** (CAMPAIGN §9
packets 6–9b). Lane U (gov-webui currency audit) may start in parallel;
lanes P/S have re-scoped packet lists above (S-B/S-D blocked on operator
OQs; P packets unblocked).

**Operator acts pending:** spine OQ-1..OQ-5 rulings (gate S-B/S-D only);
contract ratification (S4) and public claim minting (S5) remain
operator-gated. Nothing blocks Sprint 3.
