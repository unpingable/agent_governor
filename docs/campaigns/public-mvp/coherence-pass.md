# Constellation doc coherence pass — per-repo fix lists

> **STATUS: Fable editorial pass (public-mvp S5 packet 20), 2026-07-05.**
> Reference idiom = AG's standards-work (status markers, specimen-at-front,
> candidate/landed discipline, wired-vs-specified honesty). Conventions
> propagate; vocabulary does NOT (local-grammar rule). Fixes are for Sonnet
> appliers; the reconciliation sweep (20b) runs AFTER these land.
> Sources: S1–S4 wave findings (each item carries its provenance) + targeted
> reads. Items marked ✅ were already applied during the campaign.

## agent_gov

1. ✅ REENTRY.md — live-thread pointer + push-state correction (LOCAL tags
   are history, not disk-SPOF). Applied this commit.
2. `.claude/rules/cli-reference.md` — two discrepancies (found by the
   GOVERNED_WORKFLOW run): (a) `governor receipts` is documented in the core
   workflow but surfaces only *gate* receipts — proposal receipts
   (FileSnapshot/CmdRun) have no CLI surface; either document that split or
   add a `--proposals` view; (b) `receipts --id <id> --evidence` works but
   `--evidence` is absent from `receipts --help` — document or remove.
   [Sonnet, S]
3. `.governor/loop.json` — REENTRY says it's stale; either retire it or
   repoint its re_entry_probes at the public-mvp campaign. [Sonnet, S]
4. README.md — add one line under the demo section linking TOUR.md,
   REFUSAL_GALLERY.md, NON_GRANTS.md, GOVERNED_WORKFLOW.md, specimens/
   (the S2/S3 docs are currently reachable only by browsing docs/).
   [Sonnet, S]

## maude

5. README — mention the M-4 `report <session_id>` command + the three-layer
   disclosure (surface/detail/law) in the feature list; currently undersells
   the run-report surface that CD-4/M-4 built. [Sonnet, S]
6. Contract tests (agent_gov integration/ drift, found by U1 audit): stub
   lacks `list_runs()`; two tests expect `httpx.HTTPStatusError` where
   ag_shell_client now raises `RPCError`; `create_run` returns "stub" not
   "not_implemented". Maude-lane repair packet. [Sonnet, M]

## nq (docs gaps from the stranger run — NQ's lane, offer don't impose)

7. Quickstart: note port-conflict behavior (9847/9848 in use → "Address
   already in use") and how to pick alternates. [S]
8. Document the SQL HTTP endpoint (`GET /api/query?sql=...`); `/api/sql`
   POST 404s but the quickstart mentions a "SQL console" without the path. [S]
9. `receipt check` — clarify it takes a receipt file, not `--db`. [S]
10. Hostname WARN (config `name` ≠ machine hostname) — one line saying it's
    benign. [S]

## porter

11. README — add `demo/refused-exit.sh` as the 30-second specimen at front
    (specimen-at-front convention; the demo exists and is pushed, the README
    predates it). Also document `--env` key-only recording and
    `dirty_worktree` annotation (P11-R landed after the README). [Sonnet, S]
12. Quickstart's `ssh:<host>` path has never been stranger-run against a
    REAL ssh host (P13-R verified the recipe/fake path only). One live run +
    receipt, or a README caveat. [Sonnet, S]

## vscode-governor

13. **U5 never executed** — the compat+smoke pass against AG 2.8.x is
    queued, not done (map page corrected to say so). Run it: version bump,
    `governor check` contract smoke, README cross-link. [Sonnet, S]

## gov-webui

14. README desk-mode section + COMPAT shell-contract table land with U3-E
    (in flight). After it lands: screenshot refresh (U4). [Sonnet, S]

## spine

15. ✅ README/REENTRY/CLAUDE/AGENTS de-staled (S-A + follow-up).
16. S-B/S-C/S-D per design note — gated on operator OQ-1/OQ-2, not on docs.

## unpingable-site

17. ✅ constellation.html + nav link (committed local, unpushed — deploy is
    the operator's act).
18. demo.html / limits.html — verify neither contradicts the new pages:
    limits must still say "live cage refused by construction" (constellation
    links it for that claim); demo page should point at the same three-act
    path TOUR.md narrates. [Sonnet, S — read-and-diff, fix only real
    contradictions]
19. **Launch-gate link check (operator-adjacent):** constellation.html links
    github.com/unpingable/{agent_governor, nq, maude, porter, spine,
    standing, wicket, continuity, verifier, nightshift, linearaccountant,
    lean, governor_webui, vscode-governor, clerk, governor-atlas}. Every
    repo's VISIBILITY must be verified public before site deploy — a 404 on
    the flagship link is the worst first impression available. Mechanical
    check (curl per URL) + operator decision for any repo still private.

## Cross-cutting conventions (propagate, don't import vocabulary)

- **Specimen-at-front**: nq ✅, verifier ✅, nightshift ✅, standing ✅,
  continuity ✅, spine ✅ (S-A), porter ← item 11, AG README ← item 4.
- **Status-marker discipline**: candidate docs carry "STATUS: CANDIDATE —
  not minted" (AG S2/S3 docs ✅); other repos need nothing new — do NOT
  export AG's marker vocabulary into repos with their own conventions.
- **Exit-code honesty in READMEs**: where a README shows a refusal demo,
  it should say whether refusal exits nonzero (blocking tool) or 0 (verdict
  tool) — the gallery established the pattern; repos can adopt locally.

## Reconciliation sweep (20b) — run AFTER items 2–14, 18 land

Contradiction hunt across all public text: grade inflation, admission
language applied to testimony, stale provider claims (anything calling
gemini live), vocabulary imports across repo grammars, and the §19 link
check. Output: contradiction list → fix packets or obstruction notes.
