# Active Constellation Seam — LA Fidelity Pools

Filed 2026-06-12 (Phase 0 of `working/campaign-workflow-kernel-annealing.md`, operator
decision D4 + amendment A3). Status: **ACTIVE SEAM, NOT A BUILD.** This is deliberately not
a parked candidate ("parked is too inert" — operator) and deliberately not an LA change
("don't make LA juridical prematurely"). It is instrumentation: AG wires itself so it can
discover exactly what LA must know, before LA's dashboard is welded shut.

Counterpart caution: `working/candidate-la-unit-class-fence.md` (Wall 2,
`unit_origin_mismatch`) remains its own separately-parked candidate. Different axis —
Wall 2 is unit *origin* provenance; this seam is spend *fidelity* partitioning. Do not
merge them.

## Doctrine

> **Fidelity is declared at intent, judged at recomposition, and only echoed by LA until a
> real forcing case proves spend pools need semantic typing.**

> **LA enriches AG's metabolic accounting; it is not the root of AG's jurisdiction.**
> AG may run poor without LA. It must not run blind, and it must not fake being rich.

Intent fidelity is **juridical**; LA is **metabolic** (zoning §Standing/LA: the dual
failure modes never collapse). LA never interprets prose, never applies semantic policy,
matches scope by `==` only (LA V0_BOUNDARY). So: AG declares fidelity
(intent_compiler receipt), AG judges fidelity (recomposition: losses_declared vs declared
budget), LA records what was spent and may echo the label.

## Standalone invariant (operator-pinned, 2026-06-12)

```text
Standalone invariant:
  AG self-governance must continue to run without Linear Accountant.

LA availability modes:
  - absent:         local budget ledger + receipt-only spend summaries
  - present_opaque: LA records/echoes uninterpreted fidelity metadata
  - present_typed:  future ratified fidelity/spend pools, if forced

Degradation rule:
  Loss of LA reduces available authority/capability; it must not disable core
  recomposition, refusal, checkpoint, or baseline semantics.

Refusal rule:
  Any action requiring LA-backed spend custody must refuse or downgrade when LA
  is absent. The refusal must say "requires_la_custody", not pretend local
  accounting is equivalent.
```

Architecture: *AG kernel/recomposition: mandatory; LA adapter: optional capability
provider.* Not *AG → LA → permission to breathe.* Concretely, in `absent` mode AG can
still declare fidelity, account losses, refuse laundering, checkpoint, roll back to
baselines, and emit receipts — it just cannot claim LA-backed spend custody, and annealing
runs with **reduced authority** (no cross-run metabolic budgets, no LA-backed trial spend).

## What AG needs LA to echo NOW (present_opaque mode)

- `fidelity_class` (exact | bounded | heuristic | exploratory) and `loss_budget_ref` as
  opaque, uninterpreted metadata on related receipts — only where LA's generic metadata
  already supports it. **Zero LA API/struct change.** LA decision logic remains
  capacity/scope/expiry only.

## What AG can enforce WITHOUT LA understanding fidelity

- Declaration: intent_compiler receipt carries fidelity_class + loss posture (campaign
  P1.4).
- Judgment: recomposition shadow-assesses (later enforces) whether losses_declared stayed
  within the declared fidelity budget (`RecompositionReceipt`).
- Refusal: `refused_laundering` for unaccounted boundaries; verdict
  `admissible_partial_progress` for in-budget declared loss.
- Local metering: AG-side budget ledger (receipt-only spend summaries) in `absent` mode.

## Forcing observations (any of these promotes LA-side work to a live proposal)

1. AG recomposition repeatedly needs to distinguish spend by fidelity class and the
   receipt-side join is insufficient.
2. Opaque LA metadata proves insufficient to prevent **budget laundering** (e.g.
   exploratory-class work draining capacity that bounded-class obligations rely on, with
   no mechanical way to refuse).
3. Loss-budget exhaustion needs to become a **metabolic refusal** (LA-side `Denied` /
   `InsufficientCapacity` by class), not just a juridical recomposition failure after the
   spend already happened.
4. Cross-run annealing needs LA balances partitioned by fidelity posture (trial budgets
   per class).

Each observation must arrive as receipts (cite ids), not vibes — same admission standard
as everything else.

## What LA-side work would look like IF forced (recorded so the retrofit is named, not improvised)

- `CapacityRequest`/`ConsumeRequest` gain a typed `fidelity_class`; per-class capacity
  pools with per-class conservation; new `ConsumptionDecision` variant(s) for class-bounded
  refusal. Two-sided migration: LA struct change + AG `CLOSED_REFUSAL_KINDS` mirror +
  S2/S3 seam mapping — same heaviness class as Wall 2 (medium).
- Preserved one-way door that keeps this possible at all: **units stay individuated, never
  pooled** (LA V0_BOUNDARY). If units ever blend into a fungible pool, per-class matching
  becomes unretrofittable. This seam note is part of why that door stays shut.
- Ratification evidence required: forcing-observation receipts; a drill showing the
  laundering LA-side typing prevents; AG-side tests proving `requires_la_custody`
  degradation already worked correctly before the upgrade (the upgrade adds capability,
  it must not paper over a broken degradation path).

## Promotion ceremony

When a forcing observation lands: file `GOV_GAP_LA_FIDELITY_POOLS_001` citing this note +
the receipts; cross-repo ratification with LA (spec-led, V0_BOUNDARY amendment); until
then **LA remains metabolic and uninterpreted.**
