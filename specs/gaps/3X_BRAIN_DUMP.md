# 3.x Brain Dump — Delta from SELF_GOVERNANCE_SPEC.md

Captured 2026-02-20. Source: Gemini/ChatGPT design session + Claude delta analysis.

These items are **not redundant** with the existing spec. The spec contains ~80% of each
concept in scattered form, but without naming, type boundaries, or combination reasoning.
Vocabulary saves re-derivation under deadline.

---

## 1. LOCKED as Routing Regime

**Status:** `capture` — control-law change, not wording fix

The spec says "LOCKED must not be terminal attractor" (Hardening #6). That's a negative
constraint: what LOCKED *isn't*. The missing piece is the positive policy: LOCKED is a
**routing regime** where the system continues to produce output via different paths
(emit partial, cap confidence, degrade to no-commit, request external input).

This is a control-law change. "Not terminal" permits passive waiting. "Route differently"
requires active degraded-mode dispatch with its own contracts.

**Maps to:** `specs/core/SELF_GOVERNANCE_SPEC.md` Hardening item #6, regime detection
(`src/governor/regime.py`), lane routing (`src/governor/lanes.py`)

**Design implication:** LOCKED needs its own LaneContract (or equivalent) specifying what
*can* be produced, not just what's blocked. Lane 0 (ROUTER) may be the right host for this.

---

## 2. Five-Artifact Ontology

**Status:** `capture` — highest leverage item, prevents ontology smear

The spec has artifacts scattered across subsystems: GateReceipt, ThetaDelta,
ProofCarryingDelta, ValidationBundle, ValidationResponse, etc. The brain dump proposes
a unified 5-type system:

| Artifact | Role | Current analog |
|----------|------|----------------|
| **MeasurementSnapshot** | Frozen signal values at decision time | Implicit in telemetry events |
| **TransitionProposal** | Proposed theta change + evidence bundle | ThetaDelta + ProofCarryingDelta |
| **AuthorityReceipt** | Proof that authority was checked | GateReceipt (partial), operator credential check |
| **RecoveryPlanReceipt** | Proof that recovery was planned, not ad-hoc | Does not exist |
| **ResetReceipt** | Proof of state reset with provenance | Implicit in rollback controller |

Key gap: **RecoveryPlanReceipt** has no current analog. Recovery actions happen but
aren't receipted as plans — they're receipted as individual gate decisions. This means
you can't distinguish "planned recovery" from "stumbled into a working state."

**Maps to:** `src/governor/gate_receipt.py`, `libs/receipt_kernel/` event types,
`specs/core/SELF_GOVERNANCE_SPEC.md` §ProofCarryingDelta

**Design implication:** The receipt kernel's 7 event types (RUN_START through RUN_FINALIZE)
may need a RECOVERY_PLAN event type, or RecoveryPlanReceipt lives outside the kernel as
a gate receipt with gate="recovery_plan".

---

## 3. Confessional Path as Named Protocol

**Status:** `open-question` — mechanics depend on runtime integration

The spec has the *pieces*: ViolationResolver (fix/revise/proceed), E-stop, allowed escape
actions (ask_operator, emit_uncertainty_flag, degrade_to_no_commit). The brain dump
proposes unifying these into a named protocol: **submit_recovery_plan**.

Concrete shape: when the system enters a failure state that can't be resolved by
automatic rollback, it must produce a `RecoveryPlanReceipt` (artifact #4 above) before
any relaxation of constraints. This is the "confessional" — structured admission of
what went wrong + proposed path forward, receipted before action.

**Open questions:**
- Who evaluates the recovery plan? Operator only? Cross-model validator?
- Does the plan artifact have a TTL? (Can you submit a plan and then sit on it?)
- How does this interact with the existing ViolationResolver's fix/revise/proceed?

**Maps to:** `src/governor/violation_resolver.py`, `src/governor/daemon.py`
`_resolve_violation()`, Hardening item #6

---

## 4. Failure Geometry

**Status:** `capture` — modeling upgrade from scalar thresholds to combination reasoning

The spec tracks failure signals individually: F1 rate, F2 rate, deadlock rate, U_t
dynamics, cost signals. Each has its own threshold. But failures in combination produce
qualitatively different diagnoses than any single signal:

| F1 spike | High cost | Mode thrashing | Diagnosis |
|----------|-----------|----------------|-----------|
| yes | no | no | Regression (verifier missed something) |
| no | yes | no | Cost explosion (model upgrade or prompt bloat) |
| yes | yes | no | Workload shift (harder tasks, not worse tooling) |
| no | no | yes | Threshold miscalibration (regime bands too close) |
| yes | no | yes | Cascading failure (F1 causes regime churn) |
| yes | yes | yes | Systemic (something fundamentally wrong) |

"Geometry" means reasoning about the **shape** of multi-signal failure, not just
whether any single scalar crossed a line. This is a real modeling upgrade.

**Maps to:** `specs/core/SELF_GOVERNANCE_SPEC.md` §Rollback triggers,
`src/governor/regime.py` RegimeSignals, `src/governor/correlator_telemetry.py` K-vector

**Design implication:** The correlator's K-vector (T, F, A, C) is already
multi-dimensional. Failure geometry may be a natural extension: define named failure
regions in K-vector space (or signal space), not just per-axis thresholds.

---

## 5. Semantic Tar Pit (distinct from Epistemic Laundering)

**Status:** `capture` — different failure class, same neighborhood

Two failure modes that look similar but have different mechanics:

- **Epistemic laundering** = strategic re-labeling to pass gates. Adversarial surface
  behavior. The agent (or meta-governor) reclassifies claims, shrinks scope, or redefines
  blockers to reduce U_t without actually resolving anything. *Intentional*.

- **Semantic tar pit** = endogenous attractor lock. The model's outputs feed back into
  its own context (via receipts, session history, continuity anchors), gradually reinforcing
  its biases. Not adversarial — *dynamical*. The system drifts toward a fixed point where
  it can't generate novelty because every output reinforces the patterns that produced it.

The spec has strong defenses against laundering (4 illegitimate paths, scope shrink
detection, claim reclassification gating). It has no defenses against the tar pit because
the tar pit doesn't violate any single gate — each individual step is legitimate.

**Maps to:** `src/governor/claim_diff.py` (laundering detection),
`src/governor/research.py` (entropy monitoring, dominance caps — closest existing defense),
`src/governor/drift.py` (temporal asymmetry — related but not same vector)

**Design implication:** The research module's entropy bounds and dominance caps are the
right shape of defense. The tar pit may need a "context diversity" metric that measures
how much of the active context is self-generated vs externally sourced.

---

## 6. Confessional as Compliance Theater (Hardening Invariant)

**Status:** `invariant` — not a style concern, a failure mode

Recovery protocols *will* become ritualized if not explicitly defended against. The
confessional path (#3 above) is only useful if it has teeth. Without an invariant,
`submit_recovery_plan` degrades to:

1. Submit boilerplate plan → auto-approved → constraints relaxed → nothing learned
2. Recovery becomes a checkbox: "Did you file a plan? Yes. Proceed."

**Proposed invariant:** A recovery plan must demonstrate **external entropy** — information
that was not available in the context that produced the failure. Concretely:

- Plan must reference at least one measurement taken *after* the failure event
- Plan cannot be a subset of the pre-failure context (cosine similarity < threshold)
- Plan must propose a *different* action than what was attempted (not just retry)

This is the "asymmetric recovery" principle: you can't recover using only the information
that got you stuck. Recovery requires new input from outside the failure context.

**Maps to:** Confessional path (#3 above), `src/governor/violation_resolver.py`,
`specs/core/SELF_GOVERNANCE_SPEC.md` §Freeze/Unfreeze sovereignty

**Design implication:** This is Hardening item #9 (extending the current list of 8).
The invariant should be mechanically checkable: hash the pre-failure context, hash the
recovery plan content, require the plan to contain material not derivable from the
pre-failure hash.

---

## Summary

| # | Item | Status | Leverage |
|---|------|--------|----------|
| 1 | LOCKED as routing regime | `capture` | High — control-law change |
| 2 | 5-artifact ontology | `capture` | Highest — prevents ontology smear |
| 3 | Confessional path protocol | `open-question` | Medium — needs runtime design |
| 4 | Failure geometry | `capture` | High — modeling upgrade |
| 5 | Semantic tar pit | `capture` | High — unmapped failure class |
| 6 | Confessional as compliance theater | `invariant` | High — recovery defense |
