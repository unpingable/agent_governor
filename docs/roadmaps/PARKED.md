# PARKED lane — backburner residents and revive triggers

**Status:** LIVE REGISTER (2026-07-02). Source: `~/git/backburner` inventory,
2026-07-02 exploration sweep.

**Doctrine (operator, 2026-07-02):** parked = **focus/resource constraint only** —
never a judgment of worth. Every entry names its revive triggers: the forcing case
or dependency that pulls it back into drive. If a live roadmap slice lands on a
parked repo, the repo comes out of park — no ceremony beyond noting it here.

Entries are *observed_state* testimony about what the parked repos contain; they
mint nothing. Consolidation questions raised here are adjudicated in
[CONSOLIDATION.md](CONSOLIDATION.md) (slices C1/C2), not in this file.

| repo | HEAD | maturity | purpose (one line) |
|---|---|---|---|
| cadence | 2026-04-09 | prototype+tests | temporal-admissibility linter for queries/models/dashboards |
| clerk | 2026-04-10 | **working v0.1.0**, E2E tests | governed AI desktop assistant (Electron+Svelte over AG) |
| custody | 2026-04-10 | prototype+tests | chain-of-custody control surface for sensitive refs (`secretctl`, default-deny) |
| dossier | 2026-04-10 | prototype+tests | code-review forensics (stale approvals, review theater; scar catalog defined) |
| gov-webui | 2026-03-28 | working (dup) | ⚠ same HEAD as `~/git/gov-webui` — duplicate/moved copy; disambiguate (C1) |
| nlai | 2026-03-07 | working v0.3.0 | claim extraction + anchors + receipts; architectural position never settled |
| resonance | 2026-04-13 | v0 prototype | cross-scope adjacency discovery; advisory-only by design |
| sorry (pysorry) | 2026-05-01 | **on PyPI** | unfinished-code debt markers + CI refusal |
| thinkulator | spec-only | no .git | research-writing Electron app blueprint (nonfiction gov + CFI + interferometry) |
| vscode-governor | 2026-03-09 | working v2.7.0 | IDE frontend over `governor` CLI |
| witness-stack | spec-only | no .git | public-draft grammar for receipted operations (observed→…→receipted) |
| wlp (spec) | 2026-04-01 | spec + ref impl | "Witness Ledger Protocol" ⚠ name collision with live `~/git/wlp` (C1) |

## Revive triggers

- **cadence** — a temporal-admissibility check becomes load-bearing outside AG's
  clock-witness/freshness seam (e.g. analytics/dashboard governance).
- **clerk** — operator wants a daily-driver governed desktop surface; or the
  UI-shell consolidation (C2) elects clerk as a survivor. Note: clerk is the most
  mature parked artifact (working product, E2E tests) — cheapest revive in the pen.
- **custody** — first real secret/key mediation need in the constellation (e.g.
  standing/AG needing governed SSH or signing); composes with Standing rather than
  competing (custody governs *use of refs*, Standing governs *who has standing*).
- **dossier** — a code-review-grant forcing case (e.g. governed PR approval flow
  in AG or dogfooding on this repo's own PRs).
- **gov-webui (backburner copy)** — never revives independently; resolved by C1
  disambiguation (canonical path is `~/git/gov-webui`; this copy is testimony).
- **nlai** — only if C2 finds capability in nlai that AG's in-tree
  claim_signals/evidence_gate lacks AND wants; otherwise absorb-or-retire.
- **resonance** — a cross-repo discovery need (e.g. the CONSOLIDATION audit itself
  wanting mechanical adjacency evidence — C1 may use it read-only without reviving).
- **sorry (pysorry)** — existing tripwire holds: no AG dependency until a live
  materially-misleading stub exists in AG (memory: pysorry_dogfood_rule).
- **thinkulator** — nonfiction-lane product pull; blocked behind any UI-shell
  consolidation verdict (don't build a 7th shell while 6 are unadjudicated).
- **vscode-governor** — an IDE-surface user shows up, or AG CLI contract changes
  enough that v2.7.0 breaks (then either revive-and-bump or retire explicitly).
- **witness-stack** — external-facing positioning need for the receipted-ops
  grammar; or C2 rules its vocabulary should fold into AG receipt doctrine / wlp.
- **wlp (spec)** — never revives under this name; C1 adjudicates lineage vs the
  live Rust `~/git/wlp` (rename, absorb as historical spec, or retire to
  graveyard with a LINEAGE note).

## Other holding pens (for completeness; not roadmap surfaces)

`~/git/graveyard/` (13 dead projects) · `~/git/bad-ideas/` (documented rejections,
has LINEAGE.md) · `~/git/not_mine/` (third-party) · `~/git/historical/` (empty).
Nothing in these pens gets a roadmap; moving something OUT of graveyard would be a
new decision, not a revive.

## Naming note

AG uses "cadence" and "custody" as **concept vocabulary** in code and doctrine
(convergent naming, not imports). A parked repo sharing a concept's name does not
own the concept; the memory-index correction (slice A5) records this so future
sessions don't re-infer phantom dependencies.
