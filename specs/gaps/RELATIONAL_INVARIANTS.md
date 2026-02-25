# Relational Invariants

Constraints on the *space of possible traces*, not on any single trace.

status: deferred (gap spec — names the category, does not build machinery)

---

## Problem

The receipt kernel has 6 constitutional invariants. All are single-trace:
they check properties of one receipt chain in isolation (hash integrity,
evidence completeness, stage ordering, etc.).

Some of the real constraints cannot be expressed as single-trace checks:

- "Every decision has a justifying evidence chain" — single-trace checkable.
- "Every decision would *still* have a justifying evidence chain under a
  slightly different policy" — requires comparing traces. That's relational.

The missing category is **relational invariants**: properties that hold over
*sets* of traces, not individual traces. In formal terms, these are
hyperproperties — specifically ∀∃-safety hyperproperties, where refutation
requires finding a trace AND proving no admissible witness trace exists.

This spec names the category, carves out the initial patterns, and maps them
to existing Governor substrate. It does not propose new machinery.

---

## Prior Art

**Hyperproperties** (Clarkson & Schneider, 2010): properties of sets of
traces, not individual traces. Subsumes noninterference, observational
determinism, and generalized information flow.

**OHyperLTLsafe** (Beutner & Finkbeiner, 2025): fragment of HyperLTL with
observation-point synchronization. Makes ∀∃ checking tractable for
infinite-state systems by aligning trace comparisons at explicit sync points.

**hyena0** (tniessen/hyena0, MIT): prototype implementation using symbolic
execution + SMT for ∀∃ hyperbug detection. Research companion, not production
tooling. Demonstrates the approach is mechanizable.

We steal the pattern. We do not import the machinery.

---

## The Four Patterns

### R1. Decision Accountability (∀∃ witness existence)

**Shape:**

```
∀ decision trace τ₁ with verdict V
∃ evidence trace τ₂
  such that τ₂ explains τ₁ under policy P
```

**In Governor terms:** For every BLOCK or PASS receipt, there exists an
evidence chain that, under the active policy at decision time, produces the
same verdict. The evidence chain is the *witness* for the decision.

**Single-trace coverage:** `receipt_completeness` and
`evaluation_completeness` check that evidence *exists* and is *referenced*.
They do not check that the evidence *actually produces the stated verdict
under the stated policy*. That's the relational gap.

**Observation points:** gate decision, evidence attachment, policy snapshot.

**Violation:** A decision receipt with no admissible evidence witness under
the recorded policy. The receipt looks complete (passes single-trace
invariants) but the evidence doesn't actually support the verdict.

**Abuse path:** P1 (legitimacy laundering) — receipts that look like
verification but don't verify anything.

### R2. Counterfactual Policy Stability (∀∃ perturbation)

**Shape:**

```
∀ trace τ under config C
∃ trace τ' under config C' (perturbed)
  such that decision equivalence holds at observation points
```

**In Governor terms:** For every decision made under the current policy
configuration, the same decision would hold under a slightly perturbed
configuration (threshold ± ε, different risk budget, stricter evidence
requirements). If a decision flips under small perturbation, it's
structurally unstable — dependent on a specific threshold value rather
than on the evidence.

**Why this is the architecturally lethal one:** It exposes hidden
dependence on threshold tuning, envelope configuration, and risk budgets.
A decision that passes under `threshold=0.49` but fails under
`threshold=0.51` is not a robust decision — it's a boundary artifact.
The replay harness (C1) already does "same inputs, different thresholds."
This pattern names what that *means* constitutionally.

**Observation points:** policy application, gate decision, regime
classification.

**Violation:** A decision that flips under ε-perturbation of any single
policy parameter. The original trace is well-formed; the perturbed trace
reveals structural fragility.

**Existing substrate:** Replay harness (C1) generates perturbed traces.
Calibration layer (C2) normalizes signals. Phase D (predict_regime)
classifies regimes from calibrated signals. The pieces exist.

**Abuse path:** P2 (selective enforcement) — decisions that depend on
threshold tuning rather than evidence. Also P3 (policy capture via
definitions) — changing a threshold by ε should not flip verdicts on
well-evidenced decisions.

### R3. Provenance Non-Laundering (∀∃ witness existence)

**Shape:**

```
∀ output trace τ₁ marked high-confidence
∃ provenance trace τ₂ of sufficient strength
  such that τ₂ explains τ₁ under provenance policy
```

**In Governor terms:** For every claim at confidence > threshold, there
exists an upstream evidence chain with provenance classification at or
above the required strength (oracle independence class, evidence type
gate, source verification).

**Single-trace gap:** A single trace can have provenance *present* but
provenance *insufficient*. receipt_completeness checks presence. This
pattern checks sufficiency under the declared policy.

**Cross-trace version:** Compare the high-confidence output against an
alternative run with stricter evidence requirements. If no admissible
provenance trace exists under slightly elevated standards, the
high-confidence mark is structurally unstable.

**Observation points:** claim assertion, evidence attachment, confidence
assignment, provenance classification.

**Violation:** High-confidence output with no admissible provenance
witness under ε-stricter policy. Looks clean in single-trace; fragile
in trace space.

**Abuse path:** P1 (legitimacy laundering) + P6 (provenance asymmetry).

### R4. Correction Availability (∀∃ witness existence)

**Shape:**

```
∀ claim propagation trace τ₁ reaching threshold N
∃ correction trace τ₂
  such that τ₂ retracts or corrects τ₁ within Δt at reachable observation points
```

**In Governor terms:** For every claim that propagated past count N (e.g.,
cited by 3+ downstream decisions), there exists a correction or retraction
event for the same claim fingerprint, arriving within Δt of the propagation
threshold crossing, and reachable via the same graph edges.

**Why this matters:** A claim that spreads without a correction path is
structurally unfalsifiable within the system. If the only way to correct a
claim is to never have made it, the system has no error-correction capacity
at runtime.

**Observation points:**
- `claim_assert`: claim asserted (fingerprint, author, timestamp)
- `propagation_threshold`: claim reaches count N
- `correction_assert`: correction/retraction asserted for same fingerprint
- `correction_visible`: correction reachable via required graph edges

**Violation:** A claim propagation trace where no correction trace exists
within the bounded window. The claim is irrefutable not because it's true,
but because the system has no correction path.

**Existing substrate:** Claim diff (retraction detection), taint index
(fingerprint matching), dissent ledger (objection tracking). The pieces
exist but aren't wired as a relational check.

**Abuse path:** P5 (appeals theater) — the system offers contestability
in theory but corrections can't reach the propagation surface in practice.

---

## What This Is Not

- **Not a solver.** No SMT, no quantifiers in code, no logic DSL.
- **Not a new architecture.** Uses existing substrate: replay harness,
  sim runner, receipt kernel, calibration layer.
- **Not a formalization exercise.** The patterns above are expressible as
  "replay under perturbation, check if witness exists." That's a bounded
  search, not a proof.

The implementation shape (when/if built) is:

```python
def check_relational_invariant(
    primary_trace: list[GateReceipt],
    perturbation: PolicyPerturbation,
    witness_predicate: Callable[[list[GateReceipt]], bool],
) -> bool:
    """Replay primary trace under perturbation, check witness exists."""
    perturbed_trace = replay_under(primary_trace, perturbation)
    return witness_predicate(perturbed_trace)
```

Pure function. Bounded window. JSONL in, bool out. No solvers.

---

## Observation Points (shared vocabulary)

Relational invariants compare traces at explicit sync points. These are
the Governor-native observation points:

| Point | What triggers it | What it captures |
|-------|-----------------|-----------------|
| `gate_decision` | Evidence gate check completes | verdict, evidence_hash, policy_hash |
| `policy_apply` | Policy snapshot taken at decision time | config state, threshold values |
| `evidence_attach` | Evidence linked to claim | evidence_kind, oracle_class, timestamp |
| `regime_classify` | Regime detection fires | regime, signals, confidence |
| `heartbeat_tick` | Gate heartbeat interval | timestamp, liveness |
| `propagation_threshold` | Claim reaches propagation count N | claim_id, count, timestamp |

These map directly to the "observation-point synchronization" in
OHyperLTLsafe. The alignment semantics: two traces are compared at the
same observation-point type, matched by subject (claim_id, receipt_id,
or policy version).

---

## Relationship to Existing Specs

| Spec | Connection |
|------|-----------|
| Receipt kernel invariants | Single-trace. R1-R4 are the cross-trace extension. |
| Replay harness (C1) | Trace generator for perturbation. Already does threshold mutation. |
| Calibration layer (C2) | Normalizes signals before comparison. Required for ε-perturbation to be meaningful. |
| Phase D (predict_regime) | Classifies regime from calibrated signals. R2 tests regime stability. |
| Governance abuse audit | R1 mechanizes P1 detection. R2 mechanizes P2/P3 detection. R3 mechanizes P6 detection. |
| SELF_GOVERNANCE_SPEC | 3.x executor/proposer separation. Relational invariants could become constitutional requirements for θ updates. |
| Sim harness | Trace generator. Scenario DSL → receipt chains → relational checks. |
| ETHICAL_HARDENING §3 | Oracle independence classes. R3 refines "sufficient provenance" into a checkable property. |

---

## Complexity Budget

The risk pattern:

1. Name ∀∃.
2. Get tempted to formalize.
3. Write a mini-HyperLTL interpreter.
4. Six months disappear.
5. Nobody cares except you and three grad students.

The correct scope:

- **Name the category** (this spec). Done.
- **Pick one pattern** (R2 recommended — most architectural leverage).
- **Express it as replay + predicate** (no new language, no solver).
- **Wire through sim harness** (trace generator already exists).
- **Emit results as SignalEnvelope** (observe-only, consistent with v2.4).

Everything stays in: deterministic replay, bounded windows, pure functions,
JSONL receipts. The invariant is:

> "This decision requires at least one alternate-trace witness under
> ε-perturbation of config parameter X."

That's it. No quantifiers in code.

---

## Deferred Decisions

1. **Which pattern first?** R2 (counterfactual stability) has the most
   leverage — it uses the replay harness you already built. R1 (decision
   accountability) is the most obvious. R3 (provenance non-laundering) is
   the most abuse-relevant. R4 (correction availability) is the most
   socially visible.

2. **Trace universe.** What's the quantification boundary for ∀? Per
   session? Per artifact build? Per policy epoch? Per dataset? The
   answer determines how expensive the bounded search is and what
   "no witness exists" means operationally.

3. **Perturbation budget.** How many ε-variants per trace? Bounded by
   replay cost. Sim harness throughput is the constraint.

4. **Failure semantics.** When a relational invariant fails, is that a
   WARN or a BLOCK? Observe-only initially (consistent with v2.4 spine).
   Promotion to gating is a separate decision requiring the rubric audit.

5. **Witness representation.** How are witness traces referenced in
   receipts? Hash links? Replay spec IDs? Provenance chains? Needs a
   receipt schema extension.

6. **3.x integration.** R2 in particular upgrades the Governor from
   "receipt kernel" to "counterfactual governor" — decisions are not just
   recorded and justified, but proven stable under perturbation. That's
   a new constitutional class. Relational invariants could become
   prerequisites for self-governance θ updates ("your proposed parameter
   change must not flip any R2-stable decisions"). That's a 3.x
   constitutional question, not a 2.x implementation question.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-25 | Initial gap spec. Names category, 4 patterns (R1-R4), observation points. Cites hyena0. |
