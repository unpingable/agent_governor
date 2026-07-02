# Roadmap of Roadmaps — the constellation integration program

**Status:** LIVE HUB (2026-07-02). Supersedes root `ROADMAP.md` (frozen 2026-02-16,
retained as fossil). AG is the coordination hub: cross-repo integration plans live
here; each sibling repo keeps its own internal roadmap.

What this is: an index over per-tool integration roadmaps plus two execution
campaigns, decomposed into slices that smaller models can execute as work orders
(see [ROUTING.md](ROUTING.md) — normative). What this is **not**: authority.
A roadmap entry is a proposal with evidence; ratification happens per-slice in the
campaigns, and custody-affecting moves (repo boundaries, authority seams) require
operator rulings recorded in campaign DECISIONS files.

## Program structure

| surface | file(s) | role |
|---|---|---|
| Routing doctrine | [ROUTING.md](ROUTING.md) | NORMATIVE: tiers, six-field slice shape, sandwich rule |
| Per-tool roadmaps | [tools/](tools/) — 17 files | contract snapshot · drift · gaps · slices per tool |
| Parked lane | [PARKED.md](PARKED.md) | 12 backburner residents + revive triggers |
| Consolidation lane | [CONSOLIDATION.md](CONSOLIDATION.md) | overlap register; absorption criteria; operator rules |
| Packet A campaign | [../campaigns/constellation-reconciliation/](../campaigns/constellation-reconciliation/CAMPAIGN.md) | handoff-language reconciliation (slices A1–A9, C1–C2) |
| Packet B campaign | [../campaigns/transition-kernel-pickup/](../campaigns/transition-kernel-pickup/CAMPAIGN.md) | Lean→Rust transition-kernel resume (slices B0–B7) |
| Machine legibility | `.governor/backlog/roadmap-*.json` | one backlog stub per tool roadmap (exporter-visible) |
| Exporter gap | `specs/gaps/GOV_GAP_ROADMAP_INDEX_LEGIBILITY_001.md` | docs/roadmaps/ not yet scanned; filed, not built |

## Membership fence

Constellation membership is **explicit**: the repos named in this program
(ACTIVE lane below + PARKED.md) are the members. Other repositories under
`~/git` are independent projects — some in adjacent lanes — and this program
makes no claims about them. **Directory adjacency is not membership.** Audits,
consolidation candidates, and drift findings must not sweep non-members in;
if membership itself is in question, that is an operator ruling, not an
inference.

## Constellation table — ACTIVE lane (17)

HEADs as verified 2026-07-02 during the six-agent exploration sweep; each roadmap
carries its own citations. Ratification: DRAFT roadmaps for the five tools Packet A
audits (nq, standing, wicket, lean, transition-kernel) ratify after the A8 report;
the rest may ratify from exploration evidence alone.

| tool | repo | HEAD seen | drift severity | roadmap |
|---|---|---|---|---|
| nq | ~/git/nq-root/nq | 2026-07-02 | **HIGH** — basis lifecycle advanced past AG adapters | [tools/nq.md](tools/nq.md) |
| standing | ~/git/standing | 2026-06-25 | MED — grant-use shipped, unpushed; AG stub pending 1b | [tools/standing.md](tools/standing.md) |
| wicket | ~/git/wicket | 2026-06-25 | LOW — SPEC v0.3 stable; corpus thin | [tools/wicket.md](tools/wicket.md) |
| wicket-guard | ~/git/wicket-guard | 2026-05-13 | n/a — pre-alpha | [tools/wicket-guard.md](tools/wicket-guard.md) |
| linearaccountant | ~/git/linearaccountant | 2026-06-25 | NONE — v0 frozen, client matches | [tools/linearaccountant.md](tools/linearaccountant.md) |
| wlp | ~/git/wlp | 2026-06-03 | LOW — healthy, v7-aligned | [tools/wlp.md](tools/wlp.md) |
| continuity | ~/git/continuity | 2026-06-28 | MED — reliance queries unwired from AG | [tools/continuity.md](tools/continuity.md) |
| spine | ~/git/spine | 2026-06-28 | LOW — not blocking | [tools/spine.md](tools/spine.md) |
| claimc | ~/git/claimc | 2026-06-28 | NONE — slices 1–3 complete, consumer-pull | [tools/claimc.md](tools/claimc.md) |
| nightshift | ~/git/nightshift | 2026-06-12 | MED — unsettled-claim kinds partially wired | [tools/nightshift.md](tools/nightshift.md) |
| verifier | ~/git/verifier | 2026-06-11 | LOW — schema 0.3.0 tracked | [tools/verifier.md](tools/verifier.md) |
| maude | ~/git/maude | 2026-04-07 | MED — 3 months behind daemon, silent-drift risk | [tools/maude.md](tools/maude.md) |
| phosphor (gov-webui) | ~/git/gov-webui | 2026-03-28 | HIGH — pinned >=2.3.0 vs AG 2.8.1 | [tools/phosphor.md](tools/phosphor.md) |
| guvnah | ~/git/guvnah | 2026-02-24 | **BREAKING** — pin <2.4.0 vs AG 2.8.1 | [tools/guvnah.md](tools/guvnah.md) |
| porter | ~/git/porter | design-only | n/a — no commits; no AG client yet | [tools/porter.md](tools/porter.md) |
| transition-kernel | ~/git/transition-kernel | 2026-06-18 | MED — three worlds to reconcile (B0/B1) | [tools/transition-kernel.md](tools/transition-kernel.md) |
| lean | ~/git/lean | 2026-07-02 | **HIGH** — v6.0.0 + v7 gap spec, way past AG scoping | [tools/lean.md](tools/lean.md) |

Docket note: `~/git/governor-atlas` (claim graph of AG architecture) already maps
AG↔sibling edges as **specified vs wired** — the tool roadmaps cite atlas cases as
docket and do not restate the edge inventory. Atlas's own honest finding stands:
most constellation edges are *specified, not wired*.

## PARKED lane (12) — see [PARKED.md](PARKED.md)

cadence · clerk · custody · dossier · gov-webui(backburner dup) · nlai · resonance
· sorry/pysorry · thinkulator · vscode-governor · witness-stack · wlp(spec,
name-collision). **Parked = focus/resource constraint only, never a worth
judgment** (operator, 2026-07-02). Every entry carries revive triggers; a live
slice landing on a parked repo pulls it into drive.

## Program dependency graph

```
ROUTING.md ─→ {Packet A capsule, Packet B updates, tool drafts, PARKED, CONSOLIDATION}
README hub ←─ ROUTING + capsule paths
Packet A:  A1 → A2 ;  A3a → A3b ;  {A2,A3b,A4,A5,A6,A7,C1} → C2 → A8 → A9
           A8 ratifies roadmaps for nq/standing/wicket/lean/transition-kernel
Packet B:  B0 → B1 → B2 → {B3, B5..Bn} ;  B6, B7 after B2
           B4 (AG Slice 1b) ⊥ Packet A — gated ONLY by operator confirm+push of
           Standing 1e62ba9/f101c55 (see pickup DECISIONS)
exporter-extension slice: after hub exists; blocks nothing
```

## Standing hard constraints (program-wide, verbatim from the packets)

- No bounded autopilot. No promoting sandbox playbooks to operational use.
- Governor handoff is not authorization; receipts are not authority; generated
  text (including these roadmaps) is not self-authorizing; memory continuity is
  not doctrine admission.
- Rust enforces declared contracts — it does not mint truth. Python AG remains
  the orchestration/reference/fallback layer; Rust→Python fallback is explicit
  and observable, never silent.
- Prefer doc patches and named gaps over new machinery. New doctrine only when a
  concrete mismatch requires it.
