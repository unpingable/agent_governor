# GOV_GAP_SEALED_OUTCOME_BOUNDARY_001

## Title
`AuthorizationVerdict` is a defined type with no production minter: the bridge from "well-formed AUTHORIZE-class chain" to "action proceeds" is structurally implicit because no code path emits the verdict that would carry the authorization.

## Status
Gap spec — containment vessel. **No schema, validator, refactor, or sealing of `StandingReceipt` is ratified by this filing.** Names the construction-discipline gap and the keeper phrasing; future forcing cases promote.

## Origin

Filed 2026-05-06 after a parallel-session Ada probe (`standing_spark`, gnat compile of a small standing/admissibility algebra) surfaced an architectural distinction the AG-side stack had vocabulary for but no enforcement primitive against:

> **Authority should be observable by consumers, not constructible by consumers.**

Ada expressed the boundary by declaring `Outcome` as a private type: consumers can pattern-match on it but cannot mint one. Translated to the AG topology, the question is whether `AuthorizationVerdict` is similarly mintable only by an admissibility decision path, or freely constructible by any module with the import. An audit of `src/governor/standing/` answered: there is currently *no* construction path. The type is defined, parsed on deserialization, accepted as a passive field on `StandingReceipt`, and used in five test fixtures. No production code mints it.

This is the construction-discipline complement to `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`. That gap names the missing content-semantic enforcement of the Lean bridge theorem `revoked_basis_cannot_be_authorized_step`. This gap names the structural reason that bridge cannot be enforced today: there is no value the bridge could constrain — the type has no minter at all.

## Problem Statement

Today the AG standing topology is:

| Component | Role | Construction discipline |
|-----------|------|-------------------------|
| `StandingReceipt` (`types.py`) | Evidence: an actor *claims* a standing class | Freely constructible — any module with the import can write `StandingReceipt(standing_class=AUTHORIZE, ...)` |
| `ValidationReceipt` | Attestation: chain is well-formed | Sealed — only `StandingChainValidator.validate()` produces it |
| `AuthorizationVerdict` enum (`types.py:125`) | Decision: PERMIT / DENY / ESCALATE / REQUIRE_HUMAN | **No production minter exists.** Defined, parsed in `from_dict` (`types.py:972`), accepted as `verdict: AuthorizationVerdict \| None = None` field on receipts. Never returned from a function. |

The middle row is the Ada move, in Python — the validator-only factory pattern is exactly what `private` does in Ada for `Outcome`. The first row is correct as-is for evidence. The third row is the gap.

The bridge a consumer might reach for —

```text
well-formed AUTHORIZE-class StandingReceipt chain
        ↓
therefore action may proceed
```

— is currently *only* a bridge in the consumer's head. Nothing emits the verdict that would make the bridge type-checkable. `StandingChainValidator.validate()` returns `ValidationOutcome` (chain shape: `VALID`, `INVALID_STRUCTURAL`, `INVALID_SEMANTIC`, `INVALID_CHAIN`, `VALID_WITH_EXCEPTION`). It never returns or accepts an `AuthorizationVerdict`. Chain validity and action authority are different questions, and only one of them has a production answering surface.

The keeper diagnosis:

> **AG has authorization vocabulary without an authority mint.**

## Verified Evidence

Two-grep falsification, performed against `~/git/agent_gov` at filing time:

1. **`AuthorizationVerdict.PERMIT`/`.DENY`/etc. enum-member references in production code: zero.** The five sites that exist are all in `tests/test_standing_validator.py` (lines 190, 506, 562, 607) and `tests/test_standing_schema.py:110`, where receipts are constructed as fixtures with verdicts pre-set. No production module instantiates an enum member.

2. **`AuthorizationVerdict` constructor calls in production code: one, on the deserialization path.** `src/governor/standing/types.py:972`: `verdict = AuthorizationVerdict(verdict_raw)` inside a `from_dict`-style path. This reconstructs a verdict from already-serialized bytes; it does not mint one from basis + standing + scope + effect.

3. **`StandingChainValidator.validate()` return values:** `validator.py:353-362` — returns `ValidationOutcome.VALID`, `VALID_WITH_EXCEPTION`, `INVALID_CHAIN`, `INVALID_STRUCTURAL`, or `INVALID_SEMANTIC`. Never returns or constructs an `AuthorizationVerdict`.

The grep evidence is the cheapest available falsification. If a future audit finds a production minter the audit missed, this spec is wrong and should be retired or rewritten.

## Laundering Vector

State carefully:

- **`StandingReceipt` being freely constructible is correct as-is for an evidence/attestation artifact.** Receipts often need to be constructible — they are how an actor *claims* a standing class. The validator's job is to attest that the chain is well-formed, not to gate construction.
- **`ValidationReceipt` being sealed is correct.** Chain validity is something only the validator can pronounce, and that is enforced by the validator-only factory.
- **The laundering vector lives at the third position.** A consumer that has a chain of `StandingReceipt` instances with `standing_class=AUTHORIZE`, plus a `ValidationReceipt(outcome=VALID)`, may bridge — implicitly, in code or in head — to "action may proceed." Nothing in the type system or the validator surface makes that bridge explicit. There is no value of type `AuthorizationVerdict` that the consumer is required to obtain, and no function that would emit one.

The vocabulary collapse:

| Question | Answering surface today |
|----------|------------------------|
| Did this actor *claim* AUTHORIZE-class standing? | `StandingReceipt.standing_class == AUTHORIZE` (freely constructible) |
| Is the chain well-formed? | `StandingChainValidator.validate(chain) → ValidationOutcome` (sealed) |
| **May this actor act?** | **No production answering surface.** |

The third question is the one a consumer that wants to mutate state must answer. The first two are necessary inputs but not sufficient.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `StandingClass` enum (`types.py`) | Six classes including AUTHORIZE | — |
| `AuthorizationVerdict` enum (`types.py:125`) | Four verdicts: PERMIT, DENY, ESCALATE, REQUIRE_HUMAN | No function emits one |
| `StandingReceipt` | Frozen dataclass; `verdict: AuthorizationVerdict \| None` field | Field is only ever set via construction or deserialization, never via a mint |
| `StandingChainValidator.validate()` | Returns `ValidationOutcome` | Does not return or construct `AuthorizationVerdict` |
| `ValidationReceipt` | Validator-only factory pattern (the Ada move) | Same pattern not extended to `AuthorizationVerdict` |
| Lean `Authority.lean` | Verdict algebra: `authorized ⇔ admissibleBasis ∧ resolved precedence ∧ standing` | Formally specifies what a mint *should* compute; AG-side mint does not exist |

## Doctrine (proposed; not yet ratified)

> **Authority is not a data shape. Authority is the emitted result of a governed decision path.**

> **A receipt may claim an authorization-class role as evidence, but only the admissibility/authorization mint may emit an `AuthorizationVerdict`.**

The first line is the rule. The second line is the structural shape it implies. Both are candidate doctrine until a forcing case promotes.

The guardrail (load-bearing — do not lose):

> **The fix is not to seal `StandingReceipt`.** Sealing the receipt would conflate evidence with decision. Receipts must remain constructible as claimed evidence. The missing primitive is the mint that emits `AuthorizationVerdict` — the function with type roughly `(basis, standing_chain, scope, effect) → AuthorizationVerdict` whose body refuses to return a verdict unless basis is admissible, standing is sufficient, scope is honored, and (per the Lean kernel) precedence is resolved.

## Substrate Caveat (Refinement, 2026-05-07)

> **Frozen ≠ sealed. Validity ≠ construction discipline. The observable-not-constructible doctrine is anti-laundering, not perfect same-process unforgeability.**

The doctrine's structural shape — that `AuthorizationVerdict` values are emitted only by a mint path — relies on the substrate's enforcement of construction discipline. The strength of that enforcement varies sharply by substrate:

| Substrate | Construction discipline |
|-----------|------------------------|
| Ada (private types) | **Structural.** Consumers cannot syntactically construct an `Outcome` value. |
| Rust (private constructors) | **Structural.** Consumers cannot construct private-fielded structs without a mint function. |
| Lean (opaque types) | **Structural.** Opaque definitions hide constructors at the type-system level. |
| Python | **Conventional.** `frozen=True` dataclasses, factory functions, leading-underscore conventions, and `__init__` discipline are all bypassable by direct attribute access, `object.__setattr__`, monkey-patching, and arbitrary instantiation. |
| Common Lisp | **Conventional and protocol-mimicable.** Even lexical-closure / capability-mint patterns can be spoofed by a stateful fake that imitates the expected protocol shape — the fake does not need the mint, it only needs to mimic the conversation. (Independent finding from a parallel CL probe, 2026-05-07.) |

The AG implementation language is Python. The mint cannot, in Python, be made structurally unforgeable. What it can be made is **visibly violable**: unauthorized construction must require an explicit, grep-able boundary crossing — not accidental construction in normal use.

The implementation bar in dynamic substrates:

- **Anti-laundering** (the achievable bar). Authority-shaped values do not enter normal circulation as if they were earned. Code paths that produce or consume `AuthorizationVerdict` are grep-visible, deliberately structured so that a forgery requires a noticeable abuse — private-attribute access, monkey-patching, deliberate test-fixture leakage into production paths. The forgery is *recognizable*, not *impossible*.
- **Same-process unforgeability** (not the bar). A sufficiently determined Python module can construct anything the type system permits, and Python's type system is not strong enough to prevent it. Pretending otherwise is a category error.

**Audit warning.** Do not call a Python primitive "sealed" merely because it is `frozen=True`, has a leading-underscore factory, uses a callback or closure pattern, or routes through a `validate()` method. Those are conventional construction discipline, not structural sealing. When describing the mint's properties, name the substrate guarantee precisely:

- "Mint-only construction (Python, by convention)" — anti-laundering, not unforgeability.
- "Mint-only construction (Rust / Ada / Lean)" — structural, type-system-enforced.

Calling the first by the second's name will eventually mislead a future audit. The Common Lisp probe specifically shows that even closure/capability-mint patterns — which feel sealed because the closure is unreachable — fall to a stateful fake that mimics the protocol. That class of "sealed" is not the Ada/Rust/Lean sense.

This refinement does not change the doctrine or the acceptance criteria below. It refines what closing the gap means in the AG substrate: a Python mint with grep-visible construction sites is the achievable bar; a Rust or Ada port (e.g., across the `~/git/standing` boundary, or any process/substrate boundary the value chain crosses) could go further when stronger guarantees are warranted.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. States the construction-discipline rule: `AuthorizationVerdict` values are not consumer-constructible; they are emitted only by a designated mint path.
2. Names the laundering vector: chain validity (`ValidationOutcome.VALID`) plus claimed standing class (`StandingReceipt.standing_class == AUTHORIZE`) is *not* sufficient for a consumer to treat action as authorized; the consumer must obtain an `AuthorizationVerdict.PERMIT` from the mint.
3. Explicitly preserves the guardrail: `StandingReceipt` is not sealed; receipts remain constructible as claimed evidence.
4. Identifies the future work that would close the gap mechanically (deferred, not ratified by this filing): a mint function or factory pattern that produces `AuthorizationVerdict`; a refusal of `verdict` field assignment outside that mint; a consumer-side requirement that mutation paths obtain a verdict from the mint, not from receipt inspection.
5. Records that no construction of the mint, no sealing of `StandingReceipt`, and no schema migration is ratified by the doctrine record itself.
6. Identifies forcing cases that would justify promotion to validator behavior or type-system enforcement (e.g., a discovered code path that bridges from chain validity directly to mutation; a downstream binding action whose postmortem traces to receipt inspection rather than mint output; recurrent confusion in consumer code between asserted-standing and minted-authority).

## Non-goals

- **Not implementing the mint tonight.** This filing is a containment vessel; the mint is deferred work.
- **Not sealing `StandingReceipt`.** Explicit non-goal — overcorrects, conflates evidence with decision.
- **Not a schema migration.** No new field, no field removed, no constructor signature change to existing types.
- **Not a refactor of `StandingChainValidator`.** The validator's role (chain shape attestation) is correct; this gap names a sibling primitive, not a replacement.
- **Not a Lean-side specification.** Lean already specifies the algebra (`Authority.lean`); this gap names the AG-side construction-discipline absence.
- **Not a sealing of `verdict` field assignment.** Field-level enforcement is one candidate close-out, not the only one, and this filing does not pick.
- **Not "while here" cleanup of `StandingReceipt` deserialization, the test fixtures that pre-set verdicts, or the public re-exports.** Those are downstream of the mint design and out of scope until that design exists.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Formal/Lean sibling. That gap names the missing content-semantic enforcement: the bridge theorem `revoked_basis_cannot_be_authorized_step` is not honored at the AG layer. This gap names the structural reason it cannot be honored: the value the bridge would constrain has no production minter. The two gaps were derived independently — one from the Lean four-module kernel, one from an Ada-side construction-discipline probe — and arrived at the same hole from different formal substrates. Filing them as siblings (rather than merging) preserves the independent-derivation signal.
- **C3 (Standing Schema Discipline)** — Form discipline at the receipt-envelope layer. C3 makes receipts hostile-input-resistant. It does not make verdicts mint-only.
- **C4 (Standing Check Basis Discipline)** — Structures `Check.basis` to require `summary + rule_id + inspectable_refs`. C4 is form discipline on basis content; this gap is construction discipline on verdict emission. Different surfaces.
- **`receipt_kernel`** — Distinguishes evidence (content-addressed blobs) from decisions (RECEIPT events). The same evidence/decision split applies here at a different layer: `StandingReceipt` is evidence; `AuthorizationVerdict` is decision. The category error worth not repeating: `receipt_kernel` is *attestation* — it answers "what happened / did invariant pass?" — not *authorization* ("may this actor act?"). Standing/admissibility flows downward (evidence → mint → verdict); receipt_kernel flows upward (action → invariant check → attestation). Complementary, not parallel; not interchangeable.
- **`GOV_GAP_INBOUND_CONTEXT_AUTHORITY_001`** — Sibling at the intake valve (classification of inbound context before the binding path). This gap is at the verdict-emission valve. Both express NLAI ("language is a proposal, not an authority") at different chokepoints.

## Implementation Sketch (deferred)

Deliberately empty. Implementation requires a forcing case beyond the audit witness. Candidate ratification paths if forced:

- A mint function (e.g., `decide_authorization(basis, chain, scope, effect) → AuthorizationVerdict`) located adjacent to `StandingChainValidator`, mirroring the Lean `decideAuthority` derivation. Refuses to emit `PERMIT` unless all four axes of `validator_contract.md §9` resolve favorably.
- A factory-pattern enforcement on `verdict` field assignment in `StandingReceipt` (consumer constructions accepted; consumer-set `verdict` field disallowed or rewritten). Risk: this is partial sealing of `StandingReceipt`, which the guardrail forbids. Likely the mint is structurally separate from the receipt entirely.
- A consumer-side enforcement: any AG mutation path that consumes a chain of `StandingReceipt` instances must explicitly call the mint and check its verdict, not inspect the receipts directly. Type-system shape: `apply_mutation` requires an `AuthorizationVerdict` argument; only the mint produces it.

None of these are ratified. None should be built until a recurrent failure mode with a mechanical fix justifies it.

## Open Questions

1. Should the mint live inside `src/governor/standing/` (alongside the validator) or in a separate `src/governor/admissibility/` package that consumes standing as one input among several? The Lean kernel suggests the latter (admissibility is its own module with `decideAuthority`); the AG codebase has not picked.
2. What is the canonical decomposition of mint inputs: the Lean kernel uses `(basis × precedence × standing)`; the AG `AUTHORIZE_REQUIRED_CHECKS` uses `(standing × admissibility × scope × budget)`. Are these equivalent presentations or genuinely different cuts? If different, which is canonical for the AG mint?
3. Is the mint pure (basis + chain + scope + effect → verdict) or stateful (consults policy registry, revocation store, evidence ledger at mint time)? Pure is simpler to type-check; stateful is what `validator_contract.md §9` actually requires for `admissibility_check`.
4. Should the `verdict` field on `StandingReceipt` be deprecated entirely, since receipts are evidence and verdicts are decisions? Or kept as a record of what verdict was minted at receipt-issuance time (immutable once set, never overwritten)?
5. How does operator override (`~/.claude/CLAUDE.md` "Operator override" section) interact with the mint? Operator reaffirmation is currently undeclared in the verdict algebra; if it is a legitimate input, the mint must consume it explicitly.

## Provenance

Filed 2026-05-06 during a session in which a parallel Ada probe (`standing_spark`, gnat-compiled, tonight) surfaced the sealed-outcome boundary by declaring `Outcome` as a private type. Translation back to the AG Python topology revealed that `AuthorizationVerdict` is a defined enum with no production construction path — the same hole `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001` (filed 2026-04-30 from the Lean side) names from the formal-theorem direction. Two independent derivations, one substrate each, converging on a single missing primitive: the authority mint. Filed as a containment vessel before any mint construction or `StandingReceipt` sealing — preserves correct attribution (the gap is the absence of the mint, not the constructibility of receipts) and prevents the construction-discipline finding from being conflated with whatever specific factory or function eventually closes it.

The Ada probe is independent-derivation evidence, not an implementation seam. `standing_spark` does not become the AG mint; it is a small spec object for what shape the mint should take. The keeper from ChatGPT's framing (independent of the Ada code itself):

> **Authority observable, not constructible.**

**Refinement, 2026-05-07.** A parallel Common Lisp probe surfaced the substrate caveat above: even lexical-closure / capability-mint patterns can be spoofed by a stateful fake mimicking the expected protocol shape, so closure-mint tricks are not "sealed" in the Ada/Rust/Lean sense. This refinement does not alter the doctrine; it pins the implementation bar in dynamic substrates (Python, Lisp) at *anti-laundering* (grep-visible construction sites, recognizable forgery) rather than *unforgeability*. Three-substrate convergence: Lean (formal-theorem side), Ada (structural-sealing demonstration), Common Lisp (negative result that named the substrate-guarantee distinction). The doctrine is substrate-independent; the achievable enforcement is substrate-specific.
