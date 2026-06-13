# Cross-tool design note: symbolic instruments are un-pleadable witnesses

## Status

**PROVISIONAL design note — names an abstraction, authorizes no build.** Filed
2026-06-13 (operator + interferometry). The verifier (`~/git/verifier`, Z3) is the
first instance of a class this note names: a **symbolic instrument**. Records the
abstraction and its authority rule BEFORE the system invents `symbolic_allowed =
True` and treats a proof of the wrong problem as reality. Composes with
`decomposition-capability-closure-note.md` (symbolic instruments are the
coverage-completeness evidence there) and the receipt-sovereignty note (the
solver is a service, never a principal). The capability-kernel / multi-engine
integration is FUTURE; this note installs the *authority split* and the *receipt
discipline* now.

## The reframe: authority, not intelligence

The neurosymbolic question is usually posed as "which paradigm gives better
answers." This architecture reposes it as an **authority** question, and the
answer flips. You do not reach for a symbolic solver because it is smarter — the
LLM is the better reasoner in the open world. You reach for it because it is
**un-pleadable**: a solver is not a principal you can persuade, so there is no
"model is not principal / model has no standing" problem when the thing isn't a
model.

```
neural  (LLM):       judgment-bearing — open-world, framing, analogy,
                     decomposition PROPOSALS. Pleadable. Not principal. Not authority.
symbolic (solver):   rule/constraint-bearing — closed-world admissibility,
                     satisfiability, contradiction, reachability. Un-pleadable
                     once encoded. Authority-bearing ONLY over the encoded problem.
```

> **Symbolic = authority-bearing. Neural = judgment-bearing.** That is the split
> the whole stack has been driving at, now drawn across the AI methods themselves.

A symbolic instrument is therefore a **judgment-surface shrinker**: every problem
you can move from "operator decides" to "solver decides" loses its standing
problem and gets a clean receipt.

## The entire war: the encoding boundary

The judgment does not vanish — it **relocates** to the encoding boundary, the
map–territory seam. The solver is sound about the problem you *encoded*, never
about whether it is your *actual* problem.

```
solver verdict:    "given THESE facts/rules, this follows"   (solver owns this)
encoding authority: "these are the right facts/rules/boundary" (Standing/operator owns this)
```

> **A proof of the wrong formalization is more dangerous than a hunch, because it
> arrives wearing a proof** (a little mortarboard). The solver can close a gate; it
> cannot decide the gate was the right gate.

So the encoding boundary is the new ratification surface — assert-standing again:
who had standing to classify this as programmatic and to fix this encoding?

## The class (verifier is instance #1)

```
SymbolicInstrument:
  input:   cooked, typed IR (never fetches; cooked-not-fetched)
  engine:  z3 | smt | lean_citation | datalog | asp/clingo | alloy | tla+/model-check
  output:  a typed verdict (sat | unsat | valid | invalid | unknown)
  properties:
    stateless · offline · un-pleadable over the encoded problem
    NO authority over facts · NO action force by itself
```

Engines by job (the abstraction should exist; not all engines need to):

| Engine | Good for |
|---|---|
| Z3 / SMT | bounded constraints, cap-subset, contradiction, arithmetic/resource gates |
| Lean | theorem-cited refusal classes, invariant kernels, inductive properties |
| Datalog | reachability, dependency closure, provenance graphs ("what depends on what") |
| ASP / clingo | admissible configurations, choice under constraints, alternative decompositions |
| Alloy | small-scope structural counterexamples, bridge/authority topology |
| TLA+ / model checking | temporal liveness/safety across transitions |

## The independence-class payoff (interferometry)

Current interferometry is all neural — four pleadable oracles (Claude, ChatGPT,
DeepSeek, Grok) that correlate in exactly the way the loop's epistemic-backoff
warns about (`docs/loop-protocol.md` §11.1 — model agreement is not independence).
Even when the models differ, they are soft reasoners over language with correlated
failure modes.

A symbolic leg is the **one witness uncorrelated by construction** — the
`independence_class: tool` leg the classification floor wanted, the thing
model-agreement can never stand in for:

```
model agreement      = evidence        (correlated; neural family)
symbolic check       = tool-class witness (uncorrelated by construction)
operator ratification = authority over the encoding
```

A future consequence-bearing classification floor:

```
- at least one NEURAL judgment may propose
- at least one SYMBOLIC/tool witness checks it IF the sub-problem is programmatic
- operator/assert-standing ratifies the non-programmatic residue AND the encoding
```

## Do not let symbolic become the new laundering machine

```
failure mode:  planner invents a bad formalization
               -> solver proves it
               -> system treats the proof as reality
```

Worse than vibes, because it wears a mortarboard. Every symbolic call needs a
receipt that SEPARATES the encoding basis from the solver verdict, so the
map–territory seam stays auditable:

```
encoding_basis:                          solver_verdict:
  encoded_by      (who)                    result: sat|unsat|valid|invalid|unknown
  source_facts    (from what)              engine + version
  policy / scope  (under what)             input_hash
  excluded        (what was left out)      proof|model|counterexample_hash
  programmatic_classifier_standing
```

## Authority rule (the load-bearing line)

> **Symbolic instruments are un-pleadable witnesses over cooked typed inputs. They
> may discharge bounded programmatic gates. They may NOT fetch facts, authorize
> actors, mint capacity, assert freshness, or decide that an ambiguous judgment is
> programmatic.**

## Acceptance markers (future — NOT implemented here)

1. A symbolic verdict cannot become authority (`verifier.allowed` is evidence; an
   upstream authority kernel reserves `authorized`).
2. A symbolic verdict cannot repair stale facts (no `solver_valid → freshness`).
3. A symbolic verdict over an unknown/unsanctioned encoding emits evidence only.
4. `programmatic_gate` classification requires assert-standing / operator
   ratification (the planner may propose, not self-certify).
5. neural agreement + symbolic check still requires source/freshness ownership by
   the owning office (the symbolic leg does not absolve provenance).
6. `solver unknown` does NOT silently degrade to allow (unknown is not pass).

## Doctrine lines

- Symbolic tools are valuable here not because they are smarter, but because they
  are less pleadable.
- The solver can close a gate. It cannot decide the gate was the right gate.
- Neural proposes the map. Symbolic checks the map's math. Standing decides who was
  allowed to call it the territory.
- A proof of the wrong formalization arrives wearing a mortarboard.
- The judgment never vanishes; it relocates to the encoding boundary.
