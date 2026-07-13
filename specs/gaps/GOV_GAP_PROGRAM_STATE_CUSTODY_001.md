# GOV_GAP_PROGRAM_STATE_CUSTODY_001 — Governed Program State / Project-State Custody

> STATUS: CANDIDATE (named, not built — 2026-07-13). Recognition record per the
> name-early / ratify-lazily discipline. Authorizes NOTHING to build; it is a
> handle for review. Deliberately **not** titled "compiler" — that invites the
> assumption that raw commits deterministically yield project truth. A compiler
> may later be *one mechanism inside* this, not the frame.

## What this is

Custody for **project state** — the same law the constellation already applies
to code (*language is a proposal, not an authority*) applied to the unit of
program work (the slice). "Done" is a claim over symbolic artifacts; it decays
and gets re-narrated by whichever agent is most optimistic. This gap names a
governed artifact that makes program state **adjudicated from evidence** rather
than **reconstructed from narrative or git sediment**.

Today the discipline is carried by hand in `docs/PROGRAM_LEDGER.md` under the
one-`NEXT` / propose-don't-narrate rules. This gap is the recognition that the
*mechanization* is a real architectural surface — and that if built, it is an
**AG consumer** (status is a receipt-gated claim), never a standalone
project-manager agent. The forcing case is documented (the grant-use S1–S7
program: two repos, a testimony detour, findings that would have evaporated
without hand-promotion into durable gap docs). YAGNI still governs the build: the
Markdown ledger + disciplines capture most of the value; mechanize only when
hand-maintenance recurs across 2–3 programs and genuinely hurts.

## What exists

- `docs/PROGRAM_LEDGER.md` — the hand-maintained canonical ledger (seeded
  2026-07-13).
- AG primitives that a build would consume (NOT a new subsystem):
  - **evidence ledger** → `receipt_kernel` (hash-chained, append-only).
  - **program state** (typed items / status / deps / rulings) → `claim_status` +
    the ClaimStatus FSM + `docket` (adjudicates ambiguous transitions).
  - **human projection** → `status_rollup` / `viewmodel`.
- Composing nodes, each with a bounded role (no node becomes the whole system):
  - **Continuity** preserves standing across sessions.
  - **Spine** locates / indexes artifacts.
  - **AG** adjudicates status transitions.
  - **Maude** governs bounded execution (a playbook's completion ReviewPacket is
    *evidence proposing* a ledger transition, not the transition itself).

## What needs building (only when a forcing case ratifies it)

The eventual flow — never the anti-pattern:

```
work packet closes
  → agent PROPOSES a ledger transition + named receipts
  → AG adjudicates
  → accepted transition updates canonical state
  → rollup renders the human projection
```

NOT: `agent scans git → develops a vibe → marks three things complete`.

Transition FSM (each edge requires named evidence):
`OPEN → BUILT → INTEGRATION-PROVEN → ADVERSARIALLY-TESTED → CORRECTED → CLOSED`.

Three layers:
1. **Evidence ledger** — receipts + references (immutable-ish).
2. **Program state** — normalized items, statuses, dependencies, ownership,
   rulings; layers 2/3 derived from layer 1.
3. **Human projection** — current position, what changed, what is NEXT, what is
   parked, which artifacts prove it.

## Binding constraints (put here now so a future build inherits them)

- `CLOSED` requires **named receipts**, not prose confidence.
- Gaps discovered during adjudication become **explicit ledger items before the
  parent slice closes** (no orphaned findings).
- Exactly **one `NEXT`**, or an explicit "no next item ruled."
- Historical transitions are **append-only in meaning** even if the Markdown
  projection is rewritten (a slice does not silently un-close; rulings extend,
  never overwrite).
- External systems (Jira, GitHub issues, dashboards) are **projections or intake
  channels, never authority**. Inverting this — an external tool as source of
  truth — is the fog this gap exists to prevent.
- Automatic extraction may **propose evidence links; it may not decide semantic
  completion**. The hot-context agent decides whether a finding changes program
  state; automation only checks consistency against explicit artifacts.

## Non-goals

- A "project-manager agent" / synthetic Jira / status-shaped fog.
- Inferring program truth deterministically from commit sediment.
- A new subsystem parallel to AG — this is AG's claim-status/receipt/docket
  machinery with the **program-slice** as the subject type.
- Centering on ticket churn.

## Open questions

1. **First automation = a cold-context backlog auditor** (separate, LATER —
   after the hand-ledger has survived ordinary use). Narrow job: scan the
   ledger + gap notes + recent receipts + design docs; flag items with missing
   evidence, stale `NEXT`, contradictory statuses, orphaned findings, or commits
   not reflected in the ledger; **propose** transitions/cleanup; **never mark
   anything `CLOSED` itself.** Good fit for Codex / lighter Claude (consistency
   checking, not architectural judgment). Division of labor:
   > hot-context agent proposes meaning · cold-context auditor checks sediment ·
   > AG adjudicates transitions · ledger records accepted state.
   Do NOT build until the ledger exists and has survived use — else we automate
   a schema we have not proven we want (how one accidentally invents ServiceNow
   in a lab coat).
2. **Ops-facing profile?** Ordinary incident work has externally legible state
   (the world rudely emits evidence). But long migrations, deprecations, fleet
   programs, and multi-quarter reliability work develop the SAME symbolic-state
   problem ("the migration is complete except for six undocumented exceptions
   and one team that stopped replying"). So this may eventually have an
   ops-facing profile — not centered on tickets. Do not build it in yet.
3. Where does the canonical program-state artifact physically live once
   mechanized — an AG store keyed by receipt, projected to Markdown? (The
   Markdown is the projection; the store is the authority.)
4. Relationship to Continuity's standing store — does the ledger's standing
   ride Continuity, or does AG hold it and Continuity only persist? (Composition
   TBD; neither should absorb the other.)

## Provenance

Recognized 2026-07-13 in a design conversation (operator + chatty) after the
grant-use S1–S7 program made the hand-maintenance cost legible. Seeded artifact:
`docs/PROGRAM_LEDGER.md`. This spec captures the recognition without
commemorating it by building another subsystem.
