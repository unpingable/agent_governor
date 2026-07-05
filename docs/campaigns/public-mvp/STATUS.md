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

## Next

**Sprint 2 — "Stranger path"** (see CAMPAIGN.md §9): fresh-clone demo
verification in a clean container; TOUR.md; smallest-governed-workflow guide;
specimen corpus README; maude live-daemon smoke. Parallel lanes may start:
P (porter — note: implementation partially exists, re-scope P11/P12 against
reality), S (spine blueprint), U (gov-webui currency audit).

**Operator acts pending:** none blocking Sprint 2. Contract ratification (S4)
and public claim minting (S5) remain operator-gated.
