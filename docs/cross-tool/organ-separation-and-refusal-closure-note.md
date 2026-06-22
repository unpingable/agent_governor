# Organ separation as a design test + planner as refusal-closure

**Status:** candidate, doc-only, NOT build authorization. Captured 2026-06-22 from a
five-round interferometry exchange (operator + ChatGPT + Claude). Most of what that
exchange "designed" AG already has — this note records only the residue that is genuinely
additive, and maps the rest onto existing modules so it is not re-derived a fourth time.
Composes with `weak_property_strong_property.md` (laundering conservation) and
`closure-authority-incumbency-note.md` (itself an instance of the invariant below).

## Already built — do not re-file

The exchange converged on a "five-organ" architecture. Net of the repo, the organs exist:

| Organ (exchange term) | AG home |
|---|---|
| Witness *observes* (enacted-side, snapshots) | `standing_spendability.py` ("witnesses expose the murder hallway; policy decides the gap"), `clock_witness.py`, NQ adapter |
| Kernel *adjudicates* given inputs | `activation.py` Office 1 (admissibility), `standing/` chain validator, `gate_receipt.py` |
| Ledger *spends* (reserve/commit/abort, exactly-once) | `activation.py` Office 3 (exactly-once replay-guarded spend), `reservations.py`, `storage.py` leases |
| Custody *persists* | `activation.py` Office 4 (durable receipt store), `receipt_kernel` |
| Operator *waives* | `admissibility.py` `Waiver`, `overrides.py` `OverrideReceipt` (scoped/expiring/receipted) |

The four-office activation transaction (`activation.py`) *is* the kernel+standing+spend+custody
choreography, including effect-only-at-the-end-via-receipt. Work-packet dispatch with
forbidden-moves + exit receipts + deps is `docs/reference/task-packet-template.md`. The
witness≠kernel split is `constellation-zoning.md` et al. "AG plans work but does not invent
authority" is the existing loop-protocol dispatch-and-verify model. None of this is new.

## Additive #1 — Organ fusion is the recurring bug; the five-row table is a design-time test

The reusable artifact from the exchange is not the architecture (we have it) but the
**failure-mode test** it kept tripping on. Across the rounds the same bug wore three costumes:
the compositor tried to be the witness; the planner tried to be a second kernel; the kernel
tried to be the witness ("witness-aware kernel"). One bug — **organ fusion** — a component
reaching across the declared/enacted line to do another organ's job.

The test, runnable at design time on any proposed component:

> **judge reads · witness sees · planner projects · ledger spends · operator waives —
> and no organ does another organ's job.**

Two corollaries worth pinning because they are *why* the separation is load-bearing, not
just tidy:

- **The kernel must be pure over witness snapshots, not witness-aware.** If the kernel
  fetches world-state it is non-deterministic across time and its receipt certifies nothing
  reproducible (re-run next week, it disagrees with itself). The witness produces
  timestamped single-shot snapshots; the kernel consumes them purely. Already honored by the
  standing_spendability "gate decides, witness exposes" split — this generalizes it to a rule.
- **Organ separation is also the build-independence graph.** Organs that don't do each
  other's jobs can be *built* without each other. Ledger needs no kernel (tracks spendables
  by id); typed refusal antecedents need no kernel (naming a reason ≠ the thing that
  refuses); closure needs no kernel (invents no rules). The separation enforced for
  soundness hands you the parallel build DAG for free.

## Additive #2 — Planner = constructive refusal read backwards (the dual)

The one genuinely new *mechanism*. A refusal that names its missing antecedent (which AG
already emits via closed `ViolationCode` vocab) is an obligation, inverted: "refused:
missing fresh in-bounds evidence under P3.1" read backward is the subgoal "obtain fresh
in-bounds evidence under P3.1." So a generative planner is not a second authority — it is
the transitive closure of the refusal function:

```
plan(goal) = closure(obligations(refuse(goal)))
```

Zero admissibility logic of its own. Diagnostic and generative are **duals**, same kernel.
Building it any other way (a separate proof-search engine with its own rules) reinstates a
soundness hole, because two things would decide admissibility and could disagree. This is
bounded by AG's existing unconstructability guarantee: the planner can only assemble inputs
for an already-admissible graph; it never enlarges the admissible set.

Three guards are mandatory or "constructive" overclaims — **do not build without all three**:

1. **Well-founded rank** — every projected obligation must be strictly lower-rank than its
   goal, or closure loops (authority cycles: to get supersession auth, promote Y; to promote
   Y, route back through X). No decreasing measure → not a plan → `Escalate`. "Bounded" must
   mean *finite*, not merely *scoped*.
2. **Permissioned disclosure (antecedent ≠ projection)** — the truth-condition and what an
   actor is *told* are different objects. A refusal that emits the nearest admissible path to
   an unauthorized actor is a counterfeit-hat blueprint generator ("next legal move" = "next
   move an attacker must forge"). Plan-synthesis needs its own authority surface, distinct
   from admission authority.
3. **Deadlined obligations (staleness window is built, not incidental)** — spreading
   gather→use across plan steps manufactures a TOCTOU window by construction under perishable
   evidence. Every obligation carries `fresh_by`/`valid_until`/`revalidate_at`; final
   admission always re-checks; the plan is a bounded work order with no standing, never a
   cached liveness probe.

**Forcing case to build:** an actual demand for "what's the next legal move?" beyond the
diagnostic refusal AG already emits. None present today. Name it, don't build it. The
strong (paper-grade rank function) vs practical (depth+cycle-detection, honestly marked
partial) split is noted but premature.

## Additive #3 — Fresh and spent are orthogonal axes; don't collapse into "perishable"

The exchange initially over-sold "linear/perishable evidence." Two independent axes:

- **Freshness** — valid only within `[earliest, latest]`; a *clock* bound;
  witness-observable (NQ sees a timestamp). Home: `clock_witness.py`.
- **Use-linearity** — spendable once; a *count* bound; needs a spend ledger (NQ does not see
  a use-count). Home: `activation.py` exactly-once spend.

A 90-day cert is reusable-but-fresh-bounded; a nonce is use-once-but-unexpiring. Collapsing
them hides that re-admission-at-every-boundary is fine under freshness (re-check the clock)
and *fatal* under consumption (resource spent at boundary 1, nothing left at boundary 2).
AG already has both organs; the additive part is the explicit rule: **the kernel reads
snapshots non-consumingly; spending lives in the ledger.**

## The one open completeness item (already-open surface)

Waiver/override exists (`admissibility.Waiver`, `overrides.OverrideReceipt`) but appears to
stop short on three points the exchange correctly flagged — and these are *completeness*
debt on an opened surface, not new scope:

- **Distinct, downstream-visible receipt type** — `AdmittedViaWaiver` must not be
  indistinguishable from a clean admission, or it launders "refused-then-overridden" into
  "this is fine" (`naked_lift` with a badge).
- **The load-bearing non-claim** — the waiver receipt must carry *"does not certify the
  clean antecedents were satisfied."*
- **Consumer refusal of waiver-admitted acts** — a consumer must be able to say
  `accepts_waiver_admitted: false` and emit `WaiverAdmissionNotAcceptedByConsumer`.

Plus: a waiver is single-use → it is a ledger spendable (reusable waiver = standing
exception = baseline amendment, a different path). The substrate (`overrides.py` +
`activation.py` ledger) exists; the wiring does not. This is the highest-value concrete next
step *if* the operator wants build, because it closes an open surface rather than opening a
new one — but it is kernel-coupled (waiver routes *through* admission as an admitted act,
two-organ choreography), so it waits on a stable admission interface.
