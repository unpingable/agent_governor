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

**Last updated:** 2026-07-15 (evening — push window)

> **The rule that makes this real:** an agent PROPOSES a transition backed by
> named receipts; it does not narrate completion. `CLOSED` requires linked
> receipts, never prose confidence. "Basically done" without a receipt is an
> unverified claim — the same thing AG refuses for code. See
> `specs/gaps/GOV_GAP_PROGRAM_STATE_CUSTODY_001.md` for the candidate that would
> mechanize this; today it is maintained by hand under this discipline.

## Current position

- **Active road:** grant-use / plan-admission authority
- **Last closed slice:** **2026-07-15 — a four-item operator-sequenced
  selection, all four closed**, plus a security slice, an audit, a ruling, and
  a sweep. `operator_mode` closed-domain (`443ff63`, A-7 CLOSED) · six-axis
  audit (`5916f14`) · closed axis vocabulary + mechanical checker (`9166f02`;
  live-record coverage 0% → 100%) · cli-ref closed (`42d432f`) · NS-2 staged
  (`464efeb`) · **A-1 RULED and built** (`09104ba` packet → `401ba69` Option 4b
  lane labeling, observe-only; 4a filed blocked) · epistemic backoff
  mechanized (`9ed3ed7`, §11.1) · fiction knowledge paths (`7f49fa6` — a real
  author's canon-loss failure is now a typed finding) · composer penciled
  (`264d1a0`..`5e670a0`) · lean sweep + four rulings named (`f7c1854`,
  `9e558ee`). Suite 17021 passed / 0 failed, exit 0 observed bare.
- **NEXT (exactly one, ruled):** none ruled. The 2026-07-15 four-item operator
  selection act is fully consumed (all four closed). **The largest named-and-
  unruled thing on the estate is now the inexpressibility family** — R1–R4,
  from the first lean sweep since 2026-07-02 (AG was citing v7 while lean
  shipped v10; v11 in flight). Each is separately rulable, all are
  custody-affecting, none is authorized:
  `working/rulings-pending-inexpressibility-2026-07-15.md`. R4 is doctrine,
  not a slice, and if ruled first it decides the shape of R1–R3.
  Operator-only besides: NS-2 approval act + run; public-mvp launch acts;
  A-2..A-6; the Standing expired-materialized-active grant.
- **Push state: CLEAR** (measured post-push 2026-07-15 evening). AG
  `9e558ee` · maude `e5fd7f1` · nightshift `e71303f` all pushed on an explicit
  operator go; **all 14 constellation repos measure `ahead=0`.** Pushed
  **intact** — no squash: the implementation → adversarial finding →
  correction history is preserved on origin, including the A-1 packet's two
  FATAL refutations and this session's own laundering defect and its repair.
  The no-push-during-work-hours rule stands; this clears the backlog, it
  grants nothing.
  > Correction 2026-07-15: the prior line named continuity and "yesterday's
  > cross-repo chains" as unpushed. Direct measurement showed continuity at 0
  > ahead; `.governor/loop.json` `historical_push_claim` had already
  > superseded that claim with "only maude remains ahead". The stale claim was
  > carried forward by `84e8c43` and is retracted.

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
