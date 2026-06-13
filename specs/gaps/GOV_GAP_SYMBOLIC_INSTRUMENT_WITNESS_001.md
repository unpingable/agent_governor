# GOV_GAP_SYMBOLIC_INSTRUMENT_WITNESS_001

## Title

Symbolic instruments as un-pleadable witnesses — generalize the verifier's
dispatch pattern into a class, and draw the authority split (symbol =
authority-bearing over the encoding, neural = judgment-bearing) across the AI
methods themselves.

## Status

**Candidate — abstraction record, authorizes no build.** Filed 2026-06-13
(operator + interferometry). Companion to
`docs/cross-tool/symbolic-instrument-witness-note.md`. The verifier (`~/git/verifier`,
Z3) is instance #1; this gap names the class so future engines (Lean citation,
Datalog, ASP, Alloy, TLA+) plug into one provider interface with one authority
rule, rather than each re-deriving "is a solver result authority?" Composes with
`GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001` (symbolic instruments
are its coverage-completeness evidence) and `docs/loop-protocol.md` §11.1 (the
symbolic leg is the `independence_class: tool` witness model-agreement can't be).

## What exists

- `verifier` sibling repo (Z3 admissibility sidecar) — checks proposals against
  grounded facts + constraint rules; "missing evidence is denial, not imagination";
  reserves `authorized` for upstream authority kernels.
- `constraint_gate.py` / `constraint_compiler.py` (AG-side Z3 integration points).
- Lean admissibility kernel (`~/git/lean`) — cited refusal classes.

## What needs framing (not building)

A `SymbolicInstrument` class: typed-IR in, typed verdict
(`sat|unsat|valid|invalid|unknown`) out; stateless; offline (cooked-not-fetched);
un-pleadable over the *encoded* problem; no authority over facts; no action force.
The engine is a field (`z3|smt|lean_citation|datalog|asp|alloy|tla`).

The load-bearing authority split: a symbolic verdict owns the *encoded* problem; it
does NOT own whether the encoding matches reality. The judgment relocates to the
encoding boundary (map–territory seam), which becomes the new assert-standing
ratification surface.

## Acceptance criteria / negative tests (NOT implemented here)

- AC1: a symbolic verdict cannot become authority (`verifier.allowed` is evidence;
  `authorized` is an upstream authority kernel's word).
- AC2: a symbolic verdict cannot repair stale facts (no `solver_valid → freshness`).
- AC3: a verdict over an unknown/unsanctioned encoding emits evidence only.
- AC4: `programmatic_gate` classification requires assert-standing / operator
  ratification — the planner may propose, not self-certify (shared with the
  decomposition gap's AC8).
- AC5: neural agreement + symbolic check still requires source/freshness ownership
  by the owning office.
- AC6: `solver unknown` does not silently degrade to allow.
- AC7: every symbolic call emits a receipt separating `encoding_basis`
  (encoded_by / source_facts / policy / scope / excluded / classifier_standing)
  from `solver_verdict` (result / engine+version / input_hash / proof-or-model-or-
  counterexample_hash).

## Non-goals

- NOT building a multi-engine dispatcher now (Z3 is the only live engine; Lean is
  citation-only).
- NOT putting any solver on a live latency path beyond what verifier already does
  (Z3 synchronous-at-prep is fine; Lean is cited, never live-proven).
- NOT making the symbolic leg a required interferometry witness yet (it is the
  named floor candidate, ratified lazily when a consequence-bearing classification
  needs the tool-class independence).

## Open questions

1. Does the `SymbolicInstrument` abstraction live AG-side (adapter over verifier)
   or as a verifier-repo contract AG consumes? (Lean tier ruling: cite, don't run.)
2. How does the `encoding_basis` receipt compose with the existing gate_receipt /
   evidence-class fields without duplicating canonicalization?
3. Interferometry integration: a symbolic leg as an `independence_class: tool`
   witness vs a separate witness floor — where does §11.1 want it?

## Doctrine line

> Symbolic tools are valuable here not because they are smarter, but because they
> are less pleadable. The solver can close a gate; it cannot decide the gate was
> the right gate. Neural proposes the map; symbolic checks the map's math; Standing
> decides who was allowed to call it the territory.
