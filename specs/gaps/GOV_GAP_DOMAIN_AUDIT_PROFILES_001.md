# GOV_GAP_DOMAIN_AUDIT_PROFILES_001

## Title

Build success is not domain adequacy — per-domain AUDIT receipt profiles, where
"green" can mean "compiles AND satisfies the domain's load-bearing checks."

## Status

**Candidate — abstraction record, authorizes no build.** Filed 2026-06-17 from an
external forcing case: the overnight Lean-loop field report
(`working/field-report-verify-run-2026-06-16.md`, §"Domain receipts"). For Lean,
the load-bearing audit signal is the **axiom footprint** (`#print axioms` showing
no `sorryAx` / `Classical` / `native`) plus a `sorry` grep — *not* the build exit
alone. `lake build` can exit 0 over a module that type-checks but smuggles a
`sorry` or an unwanted axiom. Build exit is necessary but not sufficient for the
claim the domain actually cares about ("this proof is axiom-clean").

## Doctrine (load-bearing — belongs verbatim in any implementation)

> A verifier receipt attests execution and exit status. Coverage and domain
> adequacy remain explicit non-discharge claims unless separately witnessed.

Lean's axiom/sorry checks are **one profile, not a universal redefinition of
"green."** Domain adequacy is an additional witness layered onto the exit receipt
for a named domain — it does not change what exit honesty means for every other
command, and it must not put domain-specific logic in the core verifier.

## What exists

- `src/governor/verify.py` / `ci.py` — exit-honest receipts; `ci_kind` is a closed
  8-value vocabulary (`unit_tests`, `lint`, `typecheck`, `build`, `security_scan`,
  `integration_tests`, `e2e_tests`, `coverage`). None of these carry domain
  semantics; none express "axiom-clean."
- No Lean (or any domain) audit profile anywhere in the verifier path.
- The field report manually borrowed the discipline (build exit + axiom sweep +
  sorry guard as the AUDIT gate) and it worked — *as a discipline*, without the
  governor enforcing it. That is the forcing case for templating it.

## What needs framing (not building)

A **domain AUDIT profile**: a named bundle of checks whose conjunction defines
"green" for that domain, each check producing its own witness, composed onto (not
fused into) the exit receipt. Candidate shape (not ratified):

- Profile id + version (e.g. `lean_axiom_clean@v0`).
- An ordered set of checks, each: id, the command/probe that produces evidence,
  and the admit predicate over that evidence (e.g. `#print axioms` output contains
  none of `sorryAx|Classical|native`; `grep -rn 'sorry'` empty).
- A composed verdict: `audit_pass` iff exit passes AND every profile check passes;
  otherwise the failing check is named (no flattening to a generic "denied").
- Profiles live as data/config consumed by a thin domain runner — **not** as
  branchy domain logic inside `verify.py`/`ci.py`.

## Acceptance criteria / negative tests (NOT implemented here)

- AC1: a Lean module that `lake build`-passes but contains a `sorry` yields
  `audit_fail`, naming the sorry-guard check — the build green does not carry.
- AC2: a module importing `Classical` (when the profile forbids it) yields
  `audit_fail` naming the axiom check, not a generic failure.
- AC3: each profile check's evidence comes from the tool's own output (NLAI); the
  agent cannot assert axiom-cleanliness.
- AC4: domains without a registered profile fall back to plain exit honesty with
  domain adequacy = `unknown` — never silently `audit_pass`.
- AC5: the core verifier (`verify.py`/`ci.py`) gains no Lean-specific (or any
  domain-specific) conditional; profiles are external data + a generic runner.
- AC6: a profile's composed verdict cannot weaken the exit receipt — it can only
  add a `not adequate` claim on top of a passing exit, or report adequacy unknown.

## Non-goals

- Shipping the Lean profile as the only/blessed profile. Lean is instance #1 that
  motivates the seam; the gap names the class.
- Putting domain knowledge in the core verifier. The whole point is to keep
  `verify-run` domain-agnostic and exit-honest.
- Auto-discovering domains. Profiles are explicitly registered.

## Open questions

- Is a profile a `ci_kind` extension, a separate receipt kind, or a composition
  over multiple `verify-run` calls + an audit aggregator?
- Relationship to `GOV_GAP_VERIFIER_COVERAGE_PROVENANCE_001`: a domain profile is
  the natural home for "what counts as exercised / adequate" in that domain — the
  two gaps share the "exit honesty does not discharge X" doctrine but split on the
  axis (coverage = did the change participate; adequacy = did it meet the domain
  bar).
- Does the symbolic-instrument family (`GOV_GAP_SYMBOLIC_INSTRUMENT_WITNESS_001`)
  subsume the Lean profile, since `#print axioms` is a symbolic-ish witness over
  the kernel? Likely related, not identical — axiom sweep is a property check on a
  build artifact, not a solver verdict over an encoding.
