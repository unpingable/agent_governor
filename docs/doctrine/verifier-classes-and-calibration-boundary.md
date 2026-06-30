---
audience: governor implementers
status: candidate
---

# Verifier classes & the calibration boundary

Status: candidate (non-binding). Two small clarifications, not new mechanism.
Position in chain: refinement under
[advisory_vs_constitutional_power.md](advisory_vs_constitutional_power.md) —
"advisory power may inform authority, but must not silently become authority."

Provenance: surfaced 2026-06-30 comparing AG against a sibling NLAI build
(`~/git/nrol-alpha-omega`, a governor-gated Bayesian forecasting engine). The
comparison produced confirmation, not redesign — both laws below name distinctions
AG already honors in code but had not stated crisply.

---

## Law 1 — "Verifier" is a category, not a tool

AG uses one word for three different guarantees. Keep them distinct:

| Class | Question it answers | AG instance |
| --- | --- | --- |
| **Recomputation verifier** | "Does this output follow from these inputs, *re-run now*?" | `verify-run` trusting a child exit code; `oracle_pytest`; a deterministic Bayes update |
| **Constraint verifier** | "Do these facts + rules *permit* this action?" | `constraint_gate.py` (Z3 sidecar) |
| **Custody ledger** | "Has the recorded history been altered?" | `receipt_kernel` (hash-chained), `gate_receipt` |

The trap: mapping a recomputation question onto the constraint verifier (or
vice-versa). You do not SMT-solve `normalize(L·P)` — the arithmetic *is* the
proof. Z3 is for admissibility, not numeric correctness.

The sharper line: **a hash chain is not a verifier.** A verifier re-runs and
checks a *transition*; the chain binds *history*. A perfectly verifiable
computation can still sit on a freely-editable audit log. Verification proves the
step; custody proves nobody rewrote the sequence of steps.

> append-only log = testimony · content-addressed chain = custody. Never confuse
> the two — but don't overbuild the chain before a publish/adversary boundary
> exists (it is YAGNI until a posterior is relied upon as authority).

## Law 2 — Calibration may weight; it may not authorize

A reliability / trust / calibration score is **testimony**, not standing. A
history of being right does not mint authority.

- calibration **may** weight already-admitted evidence (a production-side knob)
- calibration **may not** admit evidence, confer standing, satisfy quorum,
  define schema, or excuse a missing witness

This is why a source-reputation oracle is a **signal**, never a kernel:
auto-converting "confirmed N times" → "believe now" is exactly the laundering
that `standing_auto_only_mechanizes_existing_promises` forbids — green history is
not permission. AG's `CALIBRATION_LAYER` / `CalibrationParamSet` is already the
correct shape (apply-only, versioned, content-addressed signal). This law pins it
so it cannot drift into an admission gate if AG ever grows source/domain trust.

The kernel-shaped object adjacent to trust is **not** trust — it is
**independence**: how many *decorrelated* witness lines a claim rests on. That
already lives near quorum / Sybil / `independence.py`. Repeated coverage of one
causal event is corroboration, not independent evidence.

Borrowed handle (cleaner than some existing provenance-laundering prose):
**rhetoric treated as event = evidence laundering.**

### Formal warrant — annex-tier, class-boundary only

`[annex]` Formal analogue: `no_free_lift` /
`empty_floor_empty_context_derives_nothing` (LeanProofs.Witnessed, ANNEX /
Mathlib-free) show that a claim cannot be derived from an empty/admissionless
floor and cannot cross an unwitnessed bridge. The doctrine mapping is:
calibration / testimony may weight or inform review, but unless admitted as floor
membership or carried by a paid (witnessed) bridge, it cannot satisfy standing.
This citation is **class-boundary support only; it does not ratify any specific
calibration receipt.**

Two fences on that citation:

1. **Modeling correspondence, not the theorem knowing what "calibration" means.**
   The theorem says *if `c` is derivable, it came from `K` or was reached by paid
   `B`.* The doctrine sentence is valid exactly when calibration/testimony is
   modeled as `not K ∧ not paid B`. The theorem enforces the class boundary once
   the roles are encoded; it does not define the roles.
2. **Public surface = no-free-lift; the linear-spend mirror is scratch.** The
   promoted ANNEX layer proves *no-free-lift* (structural; weakening + contraction
   collapse to context inclusion — it cannot yet express `spend`). The fenced
   SCRATCH resource layer (`LeanProofs.Scratch.WitnessedResourceSequent`,
   Custody-Class SCRATCH) already has first contrast specimens — one-use bridge
   tokens, occurrence consumption, frame-carry, residue preservation — but those
   are **compile-contact only and cannot ratify AG spend doctrine.** So
   `spendability` / `standing_before_spendability_not_bounded` is formally *one
   substructural layer past* what is landed: the structural calculus proves
   no-free-lift, the (unlanded) linear one will prove no-double-spend. Different
   theorems; only the first is public.

> **The Lean theorems prove the class boundaries; the receipt attests the
> instance.** Keep this visible before a future reader turns an annex into
> scripture and starts selling indulgences — annex citations support a class
> boundary, they never ratify an instance.

### Code obligation — scope is constellation, not AG-local

This invariant is **guarantee-typed and conjunctive**: it must hold at *every*
seam, so the altitude to check is the widest boundary — the cross-repo adapters,
not AG's own gates. It is the calibration-side view of the existing constellation
doctrine `predicate_witness_infrastructure` ("no authority from predicate
satisfaction; signed ≠ witnessed").

Finding (2026-06-30, after grepping the AG-owned adapters): the AG side is clean
**by construction**, which is *why* a `calibration_signal_cannot_satisfy_standing`
unit test in AG would still be a strawman —

- `nightshift_adapter`: authority is a closed `AuthorityLevel` enum and the
  receipt role derives from `event_kind`, never from a score/health/confidence
  field. No graded input reaches authority.
- `standing_client` / `wicket_client`: standing is a **content-addressed receipt
  verified by digest** against the authoritative standing service — not a computed
  score. A calibration hash passed as a `standing_receipt_id` fails verification →
  `dangling_receipt_reference`. The leak is already refused by the existing path.

So a graded signal is structurally unable to satisfy standing here; the test would
assert against a coupling the adapter contract makes inexpressible (it is the
existing `dangling_reference` refusal wearing a calibration hat).

The adapter-boundary half — `graded_signal_is_not_a_standing_reference` — is
**already enforced and tested today**. `standing_client.verify()` accepts only a
digest the authoritative standing service verifies; everything else refuses with a
closed kind. A reliability score or calibration hash is, from the standing service's
view, just a string that does not verify → it dangles like any other non-receipt.
Pinned by:

- `tests/test_standing_client.py::test_unknown_id_raises_dangling` — any
  non-witnessed reference → `dangling_receipt_reference`. This *is*
  `testimony_cannot_satisfy_standing`; the refusal is type-agnostic, so no
  calibration-specific fixture adds coverage, only framing (this note).
- `…::test_none_id_raises_standing_required` — absent standing → `standing_required`.

The genuinely **owed** fixture is the *other* half — and it lives in a sibling, not
AG: the moment NQ / wicket / nightshift wires a health/calibration signal *into* a
standing or admission decision, that wire owes
`calibration_score_cannot_satisfy_a_standing_or_quorum_requirement`. AG's side is
the contract naming the refusal; it is already closed.

---

## Already covered — do not re-file

The same comparison sketched receipts AG already ships. Recorded here so they are
not re-proposed:

- **"Clock debt" / elapsed-time-as-typed-evidence** → `staleness.py`
  (`ClaimFreshness`, `StalenessDetector`), `ttl.py`, `gate_heartbeat.py`,
  `standing_spendability.py` (two-clock lapse). The typed-temporal-pressure seam
  is built; do not add a new receipt.
- **`OperatorStandingReceipt`** → `overrides.py::OverrideReceipt` (scoped,
  expiring, reason, `PressureRecord`). A signed override is already typed standing,
  not an invisible bypass.
- **"Shadow can accuse, shadow cannot rule"** → already
  [advisory_vs_constitutional_power.md](advisory_vs_constitutional_power.md):
  *"evidence can accuse, policy can bind."* The observe-only verdict is an existing
  invariant across ~10 modules (egress_gate, coupling, governed_activity,
  plan_review, …).

`nrol-alpha-omega` itself is worth remembering as a **worked vertical instance of
NLAI** — what the doctrine looks like as a shipped product in one domain — if
launch positioning ever needs an existence proof that isn't AG.
