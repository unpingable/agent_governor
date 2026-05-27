# GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001

## Title
AG has stability/conditioning audit machinery (continuous, drift-oriented) but no explicit primitive for **witness qualification under a perturbation regime** (binary, boundary-oriented). Lean's `WitnessInvariance.lean` formalizes the missing rung; AG has no analogue.

## Status
Gap spec — containment vessel. **No rewrite of `semantic_stability.py`, no four-tier ladder import, and no enforcement behavior is ratified by this filing.** Names the qualification-vs-drift distinction and a candidate audit posture; future forcing cases promote.

## Origin

Filed 2026-05-08 after `LeanProofs/Admissibility/WitnessInvariance.lean` landed (same day) in the lean repo. The module formalizes a four-tier ladder distilled from McGee/Zhang/Blank 2026 (*Cognitive Science* 50(3), "Evidence Against Syntactic Encapsulation in Large Language Models") — *selectivity / specialization / encapsulation / modularity* — and the lean repo names Governor explicitly as one of six consumers needing the invariance-discipline rung that the existing admissibility apparatus does not yet supply.

The operational keeper from the lean module:

> **A witness that moves when the wrong variable moves is not lying. It is unqualified.**

This sharpens a boundary AG already had vocabulary for (semantic stability, conditioning audit, perturbation kinds) but no typed enforcement against. Stability machinery measures *how much* an output drifts under perturbation. The witness-invariance primitive cuts a different question: *under which perturbation regime does this witness remain qualified to bind?* Drift amount is continuous; qualification is binary at the regime boundary.

This is one-sided in the same shape as `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`: the formal kernel pins the desired shape; AG's existing machinery is adjacent but does not enforce the binary qualification cut.

## Problem Statement

AG's `semantic_stability.py` already runs mechanical perturbations and measures four signals (stiffness, anisotropy, basin entropy, commutator drift). Its outputs are *observational* (verdict always "observe") and continuous: noise floor subtracted, p10/p90 ratios, divergence magnitudes.

The witness-invariance primitive cuts orthogonal:

| Question | Answering surface today |
|----------|------------------------|
| How much does this witness drift under perturbation? | `semantic_stability.audit()` — continuous metrics, observe-only |
| Is this witness qualified under perturbation class X? | **No production answering surface.** |

The second question — qualification under a typed perturbation regime — has no AG primitive. The lean module makes the cut three ways:

- **Relational** (`Encapsulated`, `MovesUnderExcludedPerturbation`): does the witness change when an irrelevant variable changes?
- **Typed perturbation-bounded** (`EncapsulatedWrt`): qualified under an *allowed-perturbation relation* on the disturbance class — not just a type.
- **Regime-bounded** (`EncapsulatedWithinRegime`): qualified within an operating regime (predicate on `ProductWorld`).

The keeper claim is that **specialization is a gain pattern; encapsulation is an invariance claim; modularity is an earned boundary.** AG's current machinery measures gain (responsiveness to right input). It does not separately certify invariance (immunity to wrong input).

The keeper diagnosis:

> **AG can measure how its witnesses move. AG cannot currently certify what its witnesses are qualified for.**

## Failure Mode

The laundering path:

1. A check, validator, oracle, or verifier produces a witness (e.g., a `CheckOutcome`, a `ValidationOutcome`, an evidence-gate `verdict`).
2. The witness is locally useful: it discriminates on cases the system cares about.
3. The witness is reused at a downstream boundary where the perturbation regime is broader than the one the witness was earned under.
4. The witness moves when the wrong variable moves at the broader boundary — but the system does not detect the move *as* a qualification failure, because the move is small, observational, and inside the existing stability noise floor.
5. The witness is treated as authority-bearing in the broader regime.

The structural risk is not that the witness is wrong. The structural risk is **scope creep on what the witness was qualified for** — a specialization (gain) being treated as a modularity (earned invariance boundary). The lean module's keeper makes this precise: a witness that moves under wrong-variable perturbation is not lying; it is unqualified. Treating it as authority-bearing in the broader regime is the laundering.

This is a different shape from `semantic_stability.py`'s existing concerns (stability says "this output is shaky"); it is the prior question of *what the output is allowed to be a witness for*.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `semantic_stability.py` | Mechanical perturbations (5 kinds), four signals, noise floor baseline, observational verdict | No typed perturbation regime; no qualification predicate; no boundary between "drifts a lot" and "not qualified for this question" |
| Evidence Gate (`evidence_gate.py`) | Custody scoring, claim extraction, evidence linking | No certification of which perturbation regime each evidence kind is qualified for |
| Verifier Gate (`verifier_gate.py`) | `VerifierSuite`, content-addressed `policy_version`, monotonicity property | Suite verdict is monotonic over check supersets; not over perturbation regimes |
| Oracle / `CheckOutcome` (in `verifier_gate.py`) | Tri-state outcomes with detail | No regime-binding on the outcome |
| `correlator_telemetry.py` | K-vector capture indicators, hysteresis | Capture indicators aggregate over windows; not regime-conditional witness-qualification |
| `gate_receipt.py` | Content-addressed receipts with `subject_hash + evidence_hash + policy_hash` | No `regime_hash` axis; receipts do not declare the perturbation regime under which their evidence was qualified |
| Lean `WitnessInvariance.lean` | `EncapsulatedWrt`, `EncapsulatedWithinRegime`, `moves_implies_not_encapsulated`, refinement-monotonicity | Formal target only; AG has no instantiation |

## Formal Witness (Target, Not Seam)

The Lean module in `~/git/lean/LeanProofs/Admissibility/WitnessInvariance.lean` provides the relevant handles:

- **Relational form:** `Encapsulated witness wrt sameAdmittedBasis`; `MovesUnderExcludedPerturbation`; boundary theorem `moves_implies_not_encapsulated`.
- **Typed perturbation-bounded form:** `EncapsulatedWrt witness perturbationRel` (parameterized on an allowed-perturbation relation, not just a type); refinement-monotonicity corollary `encapsulated_wrt_mono` (narrowing the perturbation class preserves encapsulation; widening can break it); bridge theorem `encapsulated_wrt_iff_relational`.
- **Regime-bounded form:** `EncapsulatedWithinRegime witness regime`; boundary theorem `moves_within_regime_implies_not_encapsulated_within_regime`; universal-regime collapse theorem `encapsulated_within_universal_regime_iff_encapsulated_wrt` (regime layer is a strict generalization); regime-monotonicity `encapsulated_within_regime_mono`.
- **Toy counterexample:** `selectivity_does_not_imply_encapsulation` — a `synBit / semBit` two-bit world where a witness selective on one bit moves under the other. Operational keeper: **selectivity is a gain pattern; encapsulation is an invariance claim; modularity is an earned boundary.**

The AG-side instantiation, if ever built, would not be a port of these definitions. It would be a typed primitive — minimally, a way to state "this evidence kind / check / oracle is qualified under perturbation regime R" — wired into existing surfaces (evidence gate, verifier suite, gate receipt) without rewriting them.

## Qualification vs Drift (Why Adjacency Is Not Equivalence)

`semantic_stability.py` and `WitnessInvariance.lean` are easy to conflate. They are not the same primitive.

| Axis | `semantic_stability.py` | `WitnessInvariance.lean` |
|------|------------------------|--------------------------|
| Output type | Continuous metrics (stiffness, anisotropy, basin entropy, commutator drift) | Binary qualification predicate |
| Verdict | "observe" only | Boundary claim: encapsulated or not |
| Cuts | Drift magnitude relative to noise floor | Movement under wrong-variable perturbation |
| Generalizes? | Across perturbation kinds (mechanical) | Across allowed-perturbation relations (typed); across regimes (predicate) |
| Right question | "How sensitive is this output?" | "What is this witness qualified to bind?" |

The two are complementary, not redundant. Stability says *how much* the output moves; invariance says *whether the move disqualifies the witness for the question being asked*. A stable witness can be unqualified (selective, not encapsulated). An unstable witness can be qualified within the regime it was earned under (high local drift, but the right invariances under wrong-variable perturbation).

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Names the qualification-vs-drift distinction and warns against treating stability metrics as a substitute for typed witness qualification.
2. Identifies AG's actual witness surfaces — the specific places where evidence, checks, or validator outcomes are reused at downstream boundaries — and asks whether the perturbation regime narrows or widens at the reuse boundary.
3. Records that the Lean four-tier ladder (selectivity / specialization / encapsulation / modularity) is *vocabulary*, not *taxonomy* — does not import as binding AG type.
4. Identifies forcing cases that would justify promotion: a postmortem in which a stable witness was treated as authoritative under a perturbation regime broader than the one it was earned under; a recurring class of receipts whose evidence kinds were wired across boundaries that change the disturbance class; a constellation event in which "selective" was conflated with "encapsulated" in a downstream consumer.
5. Does not specify implementation. The candidate primitive — a `regime_hash` axis on gate receipts, a perturbation-class declaration on evidence kinds, a regime-binding on `CheckOutcome` — is implementation territory and should not be drafted by this filing.

## Doctrine (proposed; not yet ratified)

> **A witness that moves when the wrong variable moves is not lying. It is unqualified.**

> **Specialization is a gain pattern. Encapsulation is an invariance claim. Modularity is an earned boundary. AG's existing machinery measures gain; it does not certify invariance.**

The first line is the operational keeper (lifted directly from the lean module's primitive note). The second names the cut. Both are candidate doctrine until a forcing case promotes.

## Non-goals

- **Not a rewrite of `semantic_stability.py`.** The continuous-drift surface is correct as a stability primitive; the gap is the missing binary qualification primitive sitting alongside it.
- **Not a universalization of the four-tier ladder as AG doctrine.** Vocabulary borrowed; taxonomy not imported.
- **Not a binding import of constellation structure** (NQ / Cadence / Continuity / Custody / Standing / Governor as a six-system taxonomy). The lean module names six consumers; AG's taxonomy is its own.
- **Not an invention of implementation before audit.** This filing does not propose `regime_hash`, evidence-kind regime declarations, or `EncapsulatedWrt`-style predicates in AG. It names the gap; it does not specify the fix.
- **Not a refactor of evidence gate, verifier gate, oracle, or gate receipt.** Each is a candidate audit target if forcing cases promote; none is committed by this filing.
- **Not a Wiley-paper claim.** Per the lean module's doctrine: *prove the boundary claim, not the Wiley paper.* This gap inherits that posture.

## Relationship to Other Gaps / Specs

- **`semantic_stability.py`** — Adjacent, not equivalent. Continuous drift surface; this gap names the binary qualification primitive sitting alongside it.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Sibling-shaped. That gap names the missing content-semantic enforcement on `admissibility_check` (form valid, content vacuous). This gap names the missing invariance-discipline enforcement on witness reuse (witness valid in regime R, reused in regime R' ⊃ R).
- **`GOV_GAP_CORRECTIVE_TRANSITION_BOUNDARY_001`** — Filed same session. Recovery-axis complement; this is the witness-axis complement. Both pick up Lean primitives AG had vocabulary for but no typed surface against.
- **`GOV_GAP_INTERFEROMETRY_IDENTIFIABILITY_001`** — Adjacent at the multi-model claim-comparison boundary. The witness-qualification cut is at the per-witness level; identifiability is at the comparison level. Different chokepoints, related discipline.
- **Lean `WitnessInvariance.lean`** — Formal target. Three forms (relational, typed perturbation-bounded, regime-bounded) provide the abstract shape. AG instantiation, if forced, would not port the definitions.
- **Evidence Gate, Verifier Gate, Oracle, `gate_receipt`** — The AG-side surfaces under audit. None is wrong as it stands; the gap is in how their outputs are reused across perturbation-regime boundaries.

## Open Questions

1. Where in the AG codebase does evidence / a check / an oracle outcome get *reused* at a boundary where the perturbation regime is broader than where it was earned? An audit pass before any typed-primitive work would name those boundaries concretely.
2. Is the right cut on the witness-emitter side (each evidence kind declares its allowed perturbation class) or on the receipt-consumer side (each gate receipt carries the regime under which it is binding)? Both are coherent; neither is committed.
3. Does `gate_receipt.py`'s existing tuple `(subject_hash, evidence_hash, policy_hash)` already implicitly bound the regime, in the sense that policy_hash names the perturbation regime under which the evidence kind is admissible? If so, the gap is closer to "name the implicit and require receipt consumers to honor it" than "add a new axis."
4. Is `correlator_telemetry.py`'s K-vector (Throughput, Fidelity, Authority, Cost) a regime, or a measurement *within* a regime? The lean module's regime predicate is on `ProductWorld`; the AG K-vector is observational. If the K-vector reading conditions which regime applies, the regime layer is implicit in correlator output.
5. Does the lean module's *non-laundering across regime widening* claim (regime monotonicity: narrowing preserves encapsulation; widening can break it) suggest where to look first in AG? Specifically: where does AG today widen the perturbation class on a witness's reuse path without re-deriving qualification?

## Provenance

Filed 2026-05-08 during a sweep of `~/git/lean` after the May-2026 additions to `LeanProofs/Admissibility/`. `WitnessInvariance.lean` landed the same day with three siblings of refinement (relational, typed, regime-bounded) and explicitly names Governor as a consumer needing the invariance-discipline rung. The lean keeper — *a witness that moves when the wrong variable moves is not lying; it is unqualified* — sharpens a cut AG had adjacent machinery for (`semantic_stability.py`) but no binary primitive against. Filed as a containment vessel before any audit pass identifies AG's actual witness-reuse boundaries — preserves correct attribution (the missing primitive is qualification under perturbation regime, not drift sensitivity) and prevents the gap from being conflated with whatever specific mechanism eventually closes it.
