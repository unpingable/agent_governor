# PARKED lane — backburner residents and revive triggers

**Status:** LIVE REGISTER (2026-07-02; roster updated same day after operator
cleanup — gov-webui duplicate removed; witness-stack graveyarded; receipt_kernel
moved in; wlp fossil renamed `witness-ledger-protocol`; clerk + vscode-governor
moved OUT to `~/git/agent_gov_ui/` with the other UI shells). Source:
`~/git/backburner` inventory — **9 residents**.

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
| custody | 2026-04-10 | prototype+tests | chain-of-custody control surface for sensitive refs (`secretctl`, default-deny) |
| dossier | 2026-04-10 | prototype+tests | code-review forensics (stale approvals, review theater; scar catalog defined) |
| nlai | 2026-03-07 | working v0.3.0 | claim extraction + anchors + receipts; PyPI self-promotion experiment; stays parked (operator, 2026-07-02) |
| receipt_kernel | 2026-03-14 | working, frozen | standalone/PyPI experiment; **in-tree `libs/receipt_kernel` is canonical** (operator, 2026-07-02) |
| resonance | 2026-04-13 | v0 prototype | cross-scope adjacency discovery; advisory-only by design |
| sorry (pysorry) | 2026-05-01 | **on PyPI** | unfinished-code debt markers + CI refusal |
| thinkulator | spec-only | no .git | research-writing Electron app blueprint (nonfiction gov + CFI + interferometry) |
| witness-ledger-protocol | 2026-07-02 (`ee88cf5`) | spec + ref impl | formerly `wlp` — renamed to resolve the name collision with live `~/git/wlp`; LINEAGE.md in-repo |

## Revive triggers

- **cadence** — a temporal-admissibility check becomes load-bearing outside AG's
  clock-witness/freshness seam (e.g. analytics/dashboard governance).
- **custody** — first real secret/key mediation need in the constellation (e.g.
  standing/AG needing governed SSH or signing); composes with Standing rather than
  competing (custody governs *use of refs*, Standing governs *who has standing*).
- **dossier** — a code-review-grant forcing case (e.g. governed PR approval flow
  in AG or dogfooding on this repo's own PRs).
- **nlai** — only a fresh forcing case naming a capability AG's in-tree
  claim_signals/evidence_gate lacks (operator closed the harvest question
  2026-07-02: stays parked).
- **receipt_kernel** — never revives as a separate authority; the only future is
  re-extraction FROM `libs/receipt_kernel` if an external consumer appears.
- **resonance** — a cross-repo discovery need (e.g. the CONSOLIDATION audit itself
  wanting mechanical adjacency evidence — C1 may use it read-only without reviving).
- **sorry (pysorry)** — existing tripwire holds: no AG dependency until a live
  materially-misleading stub exists in AG (memory: pysorry_dogfood_rule).
- **thinkulator** — nonfiction-lane product pull (Q-C2-1 reclassified it out of
  the Governor-shell family 2026-07-02; it revives on research-writing demand,
  not on shell politics).
- **witness-ledger-protocol** — its own forcing case only (it is a historical
  spec, not superseded by the live wire protocol — convergent name, different
  design; see its LINEAGE.md).

## Other holding pens (for completeness; not roadmap surfaces)

`~/git/graveyard/` (dead projects; **witness-stack moved here 2026-07-02** — no
remote, spec-only) · `~/git/bad-ideas/` (documented rejections, has LINEAGE.md) ·
`~/git/not_mine/` (third-party) · `~/git/historical/` (empty). Nothing in these
pens gets a roadmap; moving something OUT of graveyard would be a new decision,
not a revive.

## Naming note

AG uses "cadence" and "custody" as **concept vocabulary** in code and doctrine
(convergent naming, not imports). A parked repo sharing a concept's name does not
own the concept; the memory-index correction (slice A5) records this so future
sessions don't re-infer phantom dependencies.
