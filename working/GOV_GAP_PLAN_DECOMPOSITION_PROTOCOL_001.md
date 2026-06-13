# GOV_GAP_PLAN_DECOMPOSITION_PROTOCOL_001

## Title

A governed plan-decomposition protocol — a *plan compiler* for governed execution
that lets the governor run with reduced operator interrupts WITHOUT increasing
bad-build risk, by making jurisdiction (not just tasks) first-class.

## Status

**Candidate — design deferred to its own session.** NOT ratified, NOT scheduled.
This file captures the doctrine kernel so it survives; the schema is elaboration
that falls out of the kernel and is explicitly out of scope until the dedicated
session. (Operator + recursive ChatGPT/Claude critique, 2026-06-13.)

## Origin / forcing example

The workflow-kernel/self-annealing campaign is the forcing case:
- Phase 1 observation rung chained P1.2→P1.3→P1.4 cleanly (loop §11.2).
- Phase 2 P2.1 *halted* on a Codex finding that was partly future-rung debt, not
  current-rung unsafety — the v1 chain fuse ("2nd refinement pass → halt") was
  too blunt; loop §11.3 ("validator findings are rung-scoped; a halt needs
  jurisdiction") was the fix.
- A recursive critique pass then ran the framework over *itself* and found the
  holes below.

The one-line thesis: **plans fail when they name tasks but not jurisdictions.**
A slice with allowed surfaces but no authority boundary is a bridge with no
witness — the refusal-provenance discipline ("no free-standing bridge") applied
one layer up, to plans.

> A plan is executable only when its decomposition states what kind of mistake
> each validator is allowed to find. A finding is only classifiable by an
> authority above the rung that produced it; debt is only deferrable if it binds
> a rung obligated to collect it.

## The doctrine kernel (the law; schema comes later)

1. **Rules do not get permissive stubs.** A stub is a *typed refusal that fails
   closed*, never a pass-through placeholder. Stub mechanisms (capabilities);
   never stub rules. `stub == typed refusal`, `stub != permissive placeholder`.
2. **A finding classification is an authority-bearing act.** Not "Codex says
   future-slice," not "the builder agrees." Classification changes whether
   execution continues, so it must sit at strictly higher authority than the
   rung being executed (No Negative Clearance at the classification layer:
   signed ≠ witnessed).
3. **Future-rung debt must bind a named future rung.** Recording debt so
   execution can continue is permission laundering UNLESS the debt is a standing
   obstacle to a named later rung. "Later lol" is not admissible.
4. **A scope-expanding remedy halts by identity, not heuristic.** If fixing a
   finding requires authority the current rung does not hold, the fix crosses the
   rung boundary — so it can never be auto-fixed. Forced halt-and-ratify by
   construction.
5. **Slice admissibility does not imply seam admissibility.** Two locally-clean
   slices can compose into an inadmissible join (N writes a surface N+1's
   forbidden list assumed untouched). The seam gets its own receipt; it is not
   derived from the two slice receipts. (no-free-standing-bridge, for composition.)
6. **Debt is carried by a ledger; seams witness that it was not dropped.** One
   source of truth for obligation state (the DebtLedger). The SeamReceipt
   references the ledger before/after and refuses if a binding debt was dropped,
   mutated, or discharged without authority. (Two debt stores → divergence → the
   database is haunted by episode three.)

## Core objects (minimum viable; not the full schema)

```
RungContract:
  authority this rung holds; what it may / may not mutate;
  what counts as current-rung-unsafe; what future-rung debts it may record.

FindingClassification (closed):
  current_rung_blocker | future_rung_debt | defense_in_depth
  | scope_expanding_remedy | false_positive

ClassificationAuthority:
  who/what may classify findings for a rung. MUST be above the rung executed.
  builder: may NOT classify. validator: may recommend, not ratify.
  adjudicator/plan-authority: classifies against the admitted rung contract.
  operator: fallback classifier when no higher automation exists, and ratifies
  ambiguous / rung-changing cases. Absent automation, the safe default is
  `unknown_nontrivial_finding → operator` (never agent self-classification).

DebtBinding (admissibility rule for future_rung_debt):
  debt_id | collecting_rung | blocks_before | discharge_condition | owner
  — invalid unless all present AND the debt blocks the named rung until paid.

DebtLedger:
  owns debt records; carries obligation state across rungs
  (bind / discharge / supersede / block). The thing that must survive every join.

SeamReceipt (order-1; per join, not per slice):
  from_slice | to_slice | rung | pre/post_state_hash
  | pre/post_debt_ledger_head | required_carried_debt_ids
  | discharged_debt_ids | new_debt_ids
  | verdict: admissible | refused_dropped_debt | refused_surface_join
            | refused_rung_crossing
  Rule: a seam is inadmissible if a binding debt required to cross it is absent
  from the post-seam ledger head, unless a collector with authority discharged it
  at that seam.
```

Layering: `ledger carries · seam witnesses · collector discharges · binder admits
· operator/classifier ratifies when automation is absent`.

## Stub doctrine (what may be absent on day one, and how it must fail)

- **Stub the debt COLLECTOR** (the future rung that discharges) — downstream,
  may be absent. **Do NOT stub the debt BINDER** (the admission check that
  refuses to record debt without a named collecting rung) — live from day one or
  you launder before writing collection code.
- **Stub the automated CLASSIFIER** (none exists) — but its only safe setting is
  *every nontrivial finding routes to the operator.* Do NOT stub
  classification AUTHORITY (the rule about who may classify).
- **Do NOT stub `scope_expanding_remedy → halt`** — it is an identity, pure spec,
  no mechanism behind it; "stubbing" it just leaves the unsafe path open.

## Order-0 vs order-1 (chain vs seam)

- **chain-eligibility (order-0):** predicate on a single slice — within-rung,
  has verify, passed → may auto-continue. Local.
- **seam-admissibility (order-1):** predicate on the join — does N's post-state
  satisfy N+1's preconditions; does the union of surface claims stay within rung;
  did binding debt traverse the seam. Relational. **The asymmetric case justifies
  the whole separation:** both slices chain-eligible, seam inadmissible.

**Open question (resolve before the schema hardens):** does the SeamReceipt
*carry* debt forward, or only *assert* that carried debt is intact? Operator
lean: **assert; the ledger carries.** (Otherwise the seam becomes a second debt
store and obligation state can diverge.)

## How this composes with the constellation (recognition, not new metaphysics)

- It is refusal-provenance / "no free-standing bridge" applied to *plans*.
- A finding-classification is a typed act needing a witness (custody/receipt
  discipline at the planning layer).
- Debt-binding is a Continuity/Nightshift problem: deferral is safe only when the
  deferred thing has a place it is *forced* to land.
- A compiler *rejects* programs that don't type-check: an under-decomposed plan
  should get a typed refusal at *admission* (Wicket's job) and decline to start —
  not run-with-warnings. Keeps plan-checking federated, not bolted into runtime.

## Non-goals

- NOT a giant PM system. Docs/spec first; maybe a checker later; no runtime PM
  engine.
- NOT the full plan/slice schemas in v1 — they fall out of the kernel. The first
  design session nails only: **finding taxonomy · classification authority ·
  debt-binding rule · the P2.1 worked example.** Everything else is elaboration.

## Worked example (P2.1, to seed the design session)

```
finding: genesis string-detector leetspeak evasion
classification: future_rung_debt
why current rung may continue: P2.1 has no apply/write path; authority boundary
  is the closed tunable-surface allowlist; target labels are non-effective
  candidate metadata.
binding: blocks Phase 3 activation until per-surface target allowlists exist
  (debt P2_GENESIS_TARGET_ALLOWLIST_001 — see GOV_GAP_ANNEALING_DELTA_001).

finding: hard_guards forgery
classification: current_rung_blocker / defense-in-depth hardening
why: P2.1 claims forced-True HardGuards as a construction invariant.
action: fix before commit (done).
```

## Next-session prompt (compressed — do NOT expand to a PM system)

Design the four load-bearing items only: (1) FindingClassification taxonomy,
(2) ClassificationAuthority (where the classifier sits relative to builder /
validator / operator), (3) the DebtBinding admissibility rule, (4) the P2.1
worked example. Plan/slice/rung schemas and SeamReceipt fields are derived
elaboration once those four are settled. Keep it docs/spec-first.
