# Governed Work — Program Ledger

**Canonical record — scope declared.** Source of truth for the governed
multi-repo **program(s) this file enumerates** (currently: the grant-use /
plan-admission road and its testimony detour) — their active, parked,
deferred, and closed slices. It is **not** the universal backlog: constellation
posture/wake/membership lives in `docs/roadmaps/`; authority topology lives in
`docs/CONSTELLATION_MAP.md`; campaigns outside the enumerated program(s) keep
their own `STATUS.md` and owe this file nothing. Campaigns *inside* the
program cite it. Detailed design lives in slice documents; this file answers
only: *where are we, what is actually closed, what is NEXT, what remains real
but deliberately unbuilt, and which receipts prove it.* Maude/NQ keep one-line
pointers to this file, not divergent copies. (Scope declaration added
2026-07-13 per census defect D7 — see
`working/constellation-census-2026-07-13.md`.)

**Last updated:** 2026-07-15

> **The rule that makes this real:** an agent PROPOSES a transition backed by
> named receipts; it does not narrate completion. `CLOSED` requires linked
> receipts, never prose confidence. "Basically done" without a receipt is an
> unverified claim — the same thing AG refuses for code. See
> `specs/gaps/GOV_GAP_PROGRAM_STATE_CUSTODY_001.md` for the candidate that would
> mechanize this; today it is maintained by hand under this discipline.

## Current position

- **Active road:** grant-use / plan-admission authority
- **Last closed slice:** **Approval binds `plan_ref` (seam B)** — CLOSED
  2026-07-14 (AG `5a0bca3`, maude `e5fd7f1`). AG re-hashes the exact plan bytes
  and requires `source_plan_digest == sha256(plan_bytes) == witness.plan_ref`;
  a plan citing another plan's witness refuses even when the caller lies about
  `source_plan_digest`. Built via the gov-loop with all gates (escape-count
  6→0, adversarial sandwich 0 findings, suites bare AG 16875 / maude 360).
- **NEXT (exactly one, ruled):** none ruled — the two operator-selected
  portfolio slices (continuity repair, approval-binds-plan_ref) are both
  CLOSED. Await operator selection; `python3 scripts/portfolio_report.py` for
  the queue (hot fronts: governed-shell remainder, public-mvp Sprint 5).
- **Push state:** AG + maude + continuity + nightshift (`e71303f`, NS-1 landed
  2026-07-15) + yesterday's cross-repo chains UNPUSHED (operator: no pushes
  during work hours). Push **intact** — preserve implementation → adversarial
  finding → correction history; do not squash.

## Status vocabulary

| Status | Meaning |
|---|---|
| `NEXT` | Ruled and ready to build (exactly one at a time) |
| `OPEN` | Accepted work, not yet ordered |
| `PARKED` | Real gap requiring a future ruling or separate slice |
| `DEFERRED` | Ordered behind prerequisites |
| `DESIGN-ONLY` | Contract exists; runtime integration intentionally absent |
| `CLOSED` | Built, tested, sandwiched, and recorded with receipts |
| `RETIRED` | Superseded while preserving lineage |

## Immediate backlog

| # | Status | Item | Boundary | Completion condition |
|--:|---|---|---|---|
| 1 | `CLOSED` | Approval binds `plan_ref` (seam B) | approval-witness model | DONE 2026-07-14 — AG re-hashes exact plan bytes; `source_plan_digest == sha256(plan_bytes) == witness.plan_ref`; replay refuses even on a lying caller digest. AG `5a0bca3`, maude `e5fd7f1` |
| 2 | `DEFERRED` | NQ testimony authorization adapter | NQ owns `authorized` ceiling | NQ receipts → explicit authorized relation-strength; no causal inflation, no absence inference |
| 3 | `DEFERRED` | Maude testimony requirement adapter | Maude owns `required` floor | plans declare required relation + strength; insufficient testimony refuses before inference |
| 4 | `DEFERRED` | Governed-inquiry integration specimen | cross-repo bounded specimen | `required ≤ asserted ≤ authorized` exercised end-to-end with retained receipts |
| 5 | `DEFERRED` | Testimony LeanProofs annex | formal annex only | runtime types + ownership seams survive integration before formal promotion |

## Parked gaps

### Approval-witness replay → promoted to NEXT (#1 above)

Admission does not prove `approval_ref` names an act over the current
`plan_ref`; a plan may replay another plan's approval witness. **Changes what
approval MEANS** — a distinct threat model, not S6/S7 cleanup. Record:
`docs/campaigns/nightshift-functional-mvp/GAP-s6-sandwich-authority-findings.md`
(finding 2). Out of scope unless ruled: ration-schema expansion, supervisor /
execution arming, testimony adapters, a general approval ontology, rewriting
NS-1's history.

### Project-state custody (this ledger's own mechanization)

`OPEN` — `specs/gaps/GOV_GAP_PROGRAM_STATE_CUSTODY_001.md`. Governed program
state as an AG-consumer artifact (adjudicate proposed transitions backed by
receipts; never infer state from git sediment). Named, not built.

## Closed — grant-use track (S1–S7)

| Slice | Status | Result | Primary receipts |
|---|---|---|---|
| S1–S5 | `CLOSED` | grant-use + projection foundation (classify → mint → supervisor gate → daemon RPC → maude projection/attach → lease lifecycle) | slice records in `design-grant-use-gate.md`; on origin/main + local |
| S6 | `CLOSED` | first-class `execution_request`; `plan_version`-discriminated v1; frozen exact-hash v0; NS-1R successor; sandwiched | maude `6a35965`,`a48df3b`; AG `dc0a383`,`4a63032` |
| S7 | `CLOSED` | citation made load-bearing (`execution_request ⊆ cited_ration`); one immutable digest-verified witness; sandwiched | maude `ae4cf8a`,`f35f0da`; AG `16f1b9f`,`b1bfdd9` |

**S6 ruling retained:** *approval attaches to plan bytes, not reconstructed
intent; migration creates a successor artifact rather than revising an approved
predecessor.* NS-1 v0 bytes frozen; only the registered NS-1 `plan_ref` uses the
v0 decoder; NS-1R inherits intent, not approval; missing/unknown plan versions
refuse.

**S7 ruling retained:** governed v1 plans must cite a RationCard; every modelled
request dimension must be contained by it; narrowing admits, broadening refuses;
admission + projection share one immutable digest-verified witness; frozen v0
byte-identical; Maude's predicate is an explicit, property-pinned, drift-disclosed
mirror of AG's gate (not shared implementation).

## Testimony-admissibility detour (CLOSED / DESIGN-ONLY)

| Layer | Status | Artifact | Receipt |
|---|---|---|---|
| Instrument | `CLOSED` | `unpingable/windtunnel` frozen science (private) | `4f4f2dd` |
| AG court | `CLOSED` | pure adjudicator + tests + integration note | AG `027e0a3` |
| NQ adapter contract | `DESIGN-ONLY` | `TESTIMONY_AUTHORIZATION_ADAPTER.md` | NQ `56bd6c1` |
| Maude adapter contract | `DESIGN-ONLY` | `testimony-contract-compilation.md` | maude `3382027` |

Ownership seam: NQ → `authorized`, Maude → `required`, model+extractor →
`asserted`, AG adjudicates `required ≤ asserted ≤ authorized`. No runtime
adapter or cross-repo specimen built. Deferred (explicitly): scaling N, model
sweeps, relation ontology, promoting `windtunnel/analyze.py`, premature Lean.

## Push backlog

Before pushing (when the window opens):
- confirm AG, maude, NQ, windtunnel trees clean;
- windtunnel `4f4f2dd` is already remote;
- push AG, maude, NQ local chains **without squashing** adversarial corrections;
- record remote branch / merge receipts here;
- remove this section only when every listed local commit is reachable remotely.

## Update rule

Every completed work session updates this ledger by doing exactly four things:
1. move completed work to `CLOSED` and record its receipts;
2. name exactly one `NEXT`, or state that no next item has been ruled;
3. record every newly discovered gap as `OPEN` / `PARKED` / `DEFERRED` — never
   leave it implied in a narrative report;
4. **propose the matching `.governor/backlog/` stub transition** (with the
   receipts from step 1) for any campaign or slice that changed state — the
   stubs are the cross-constellation projection behind
   `scripts/portfolio_report.py`, and they went weeks stale the one time this
   was left implicit (census D9/D7, reconciled 2026-07-13). An auditor may
   flag stub drift; it never marks work closed.

The Markdown projection may be rewritten, but transitions are **append-only in
meaning**: a slice does not silently un-close, and a ruling is extended, not
overwritten. External systems (Jira, GitHub issues, dashboards) are downstream
projections or intake channels, never authority.
