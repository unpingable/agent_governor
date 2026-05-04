# GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001

## Title
`AUTHORIZE_REQUIRED_CHECKS["admissibility_check"]` enforces form, not basis-for-binding semantics: a structurally well-formed admissibility check can be semantically meaningless.

## Status
Gap spec — containment vessel. **No schema, validator, or enforcement behavior is ratified by this filing.** Names the laundering path; future forcing cases promote.

## Origin

Filed 2026-04-30 after a session in which:

1. The Lean four-module Admissibility kernel (`Authority.lean`, `StateTransition.lean`, `Derivation.lean`, `Execution.lean` in `~/git/lean/LeanProofs/Admissibility/`) closed the formal seam between verdict and mutation layers. The load-bearing bridge theorem `revoked_basis_cannot_be_authorized_step` now formally warrants: stale/revoked basis cannot produce an `AuthorizedStep` at the execution layer.
2. A commercial-framing pass surfaced the wedge sentence: *"agents are not allowed to treat a claim as binding without an admissible basis."*
3. An audit of `src/governor/standing/` confirmed that the receipt validator currently checks the *form* of `admissibility_check` (presence + `result` + structured `basis`) but does not specify, validate, or enforce what that check must actually inspect.

The gap is one-sided: the formal kernel proves the desired shape; the AG receipt validator does not yet enforce it at the content layer.

## Problem Statement

Today an AUTHORIZE receipt can carry a check like:

```json
"admissibility_check": {
  "result": "pass",
  "basis": {
    "summary": "looks fine",
    "rule_id": "ad_hoc_judgment",
    "inspectable_refs": ["nothing"]
  }
}
```

…and pass C3 schema validation cleanly. The validator confirms the check is *declared*. It does not confirm the check is *admissible*.

This means the wedge sentence — that agents may not treat stale prose, ambiguous authority, or unranked context as binding — is enforced at the form layer (ID-only / boolean-only checks rejected) but not at the content layer (structurally well-formed `Check` with vacuous content accepted).

The keeper diagnosis:

> **AG can currently validate that an admissibility check exists. It cannot yet validate that the check is admissible.**

## Three Distinct "Admissibility" Layers

The word "admissibility" is overloaded in this codebase. The gap is in #1 only.

| # | Where | What it is | Status |
|---|-------|-----------|--------|
| 1 | `AUTHORIZE_REQUIRED_CHECKS["admissibility_check"]` (`src/governor/standing/types.py:148`) | Receipt-schema requirement: AUTHORIZE receipts must carry a structured `Check` named `admissibility_check` | **Form enforced; content semantics undefined — this gap** |
| 2 | `Admissibility.Authority.admissibleBasis` (Lean) | Verdict-algebra atom on `BasisVerdict`; gates `decideAuthority` and (via `Execution.lean`) `AuthorizedStep` | Formally warranted — see below |
| 3 | `src/governor/admissibility.py` | Task-well-specifiedness gate (`PushbackMode` S1/S2/S3), Layer 2.1-A admissibility | Out of scope; different concept |

The spec does not propose changes to #2 (lives in another repo) or #3 (different concept). It names the laundering path in #1.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `AUTHORIZE_REQUIRED_CHECKS` (`types.py:145-152`) | Frozenset enforces presence of four checks | No semantics on what each check must inspect |
| `Check` / `CheckBasis` (C3, C4) | `result ∈ {pass, fail, escalate}`; `basis = {summary, rule_id, inspectable_refs}`; non-empty refs required | `inspectable_refs` is a list of non-empty strings — not validated as resolvable refs to evidence/policy/revocation state |
| `_check_authorize_checks` (`schema.py:131`) | Rejects missing or malformed checks | Does not interpret `rule_id` against any registry; does not require `inspectable_refs` to point at admissibility-relevant artifacts |
| `validator_contract.md §9` | Specifies `result` + `basis` for each required check | Does not define what `admissibility_check` semantically asserts |
| Lean `Authority.lean` + `Derivation.lean` + `Execution.lean` | Formal kernel: `revoked_basis_cannot_be_authorized_step` proven | Formal target only; AG implementation has not connected `admissibility_check` content to this standard |

## Formal Witness (Target, Not Seam)

The Lean four-module kernel in `~/git/lean/LeanProofs/Admissibility/` proves the desired shape:

- `Authority.lean` — verdict algebra: `authorized ⇔ admissibleBasis ∧ resolved precedence ∧ standing`.
- `StateTransition.lean` — partitioned `GovState`, `StepAllowed` mutation gating, store-isolation trapdoors (only `amendPolicy` touches `PolicyStore`).
- `Derivation.lean` — read-side: `decideAuthority` reads `GovState` into the three component verdicts; `revoked_basis_never_authorized` is the first content-semantic theorem.
- `Execution.lean` — `AuthorizedStep` requires *both* a `StepAllowed` proof (mutation standing) and an `Authorized` verdict (claim admissibility). Bridge theorem: `revoked_basis_cannot_be_authorized_step`.

This kernel is not the gap. It is the standard the AG receipt validator has not yet caught up to. The gap is that AG accepts a structurally well-formed `admissibility_check` whose `basis.inspectable_refs` does not actually establish that the basis is admissible for the operation, state-kind, or scope being authorized.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Defines that an `admissibility_check` with `result: "pass"` is **not sufficient** unless its `basis` is inspectable and semantically tied to the operation, state-kind, and scope being authorized.
2. Explicitly rejects, as binding admissibility, any `Check` whose `basis` consists of:
   - `rule_id` referring to nothing in any registered rule registry (e.g., `ad_hoc_judgment`, `looks_fine`, freeform prose IDs)
   - `inspectable_refs` pointing at non-existent, non-resolvable, or admissibility-irrelevant artifacts
   - `summary` text without corresponding inspectable substrate
3. States that unranked prose, stale context, revoked basis, and unresolved precedence must not pass as binding admissibility on AUTHORIZE receipts.
4. Identifies the future validator work that would close the gap: validating `basis.rule_id` against a registered rule registry; validating `basis.inspectable_refs` resolve to admissibility-relevant artifacts (revocation store, policy declaration, evidence ledger); tying check content to the authority tuple (operation × state-kind × scope) being authorized.
5. Records that no schema mutation, validator extension, or rule-registry construction is ratified by the doctrine record itself.
6. Identifies forcing cases that would justify promotion to validator behavior (e.g., a recurrent class of AUTHORIZE receipts with vacuous admissibility checks; a discovered laundering path that bypasses the form discipline; a downstream binding action whose postmortem traces to a meaningless admissibility check).

## Doctrine (proposed; not yet ratified)

> **A receipt's `admissibility_check` is admissible only when its `basis` is inspectable, resolvable, and semantically tied to the operation, state-kind, and scope being authorized.**

> **Form discipline is necessary but not sufficient. Vacuous content in a structurally well-formed check does not warrant binding action.**

The first line is the rule. The second is the structural shape. Both are candidate doctrine until a forcing case promotes.

## Non-goals

- **Not a schema migration.** No new field on `Check`, `CheckBasis`, or `StandingReceipt` is proposed.
- **Not a rule-registry implementation.** No concrete schema for what counts as a registered admissibility rule. The gap names the absence; it does not specify the registry.
- **Not a precedence-graph construction.** Precedence is its own axis in the formal kernel; this spec does not model it on the AG side.
- **Not a Lean-side specification.** The Lean kernel is referenced as a formal target; this spec does not draft Lean changes. (The Lean repo's own roadmap covers concrete `claimForStep` resolvers and `AuthorityClaim` schema.)
- **Not a rewrite of `src/governor/admissibility.py`.** Layer 2.1-A admissibility (PushbackMode) is a different concept; not in scope.
- **Not RPP.** No pointer-resolution-proof schema proposed by this filing.
- **Not a refactor of existing AUTHORIZE receipts.** This gap names the hole; it does not migrate existing receipts.

## Relationship to Other Gaps / Specs

- **C3 (Standing Schema Discipline)** — Form discipline at the receipt layer. This gap is its content-semantic complement: form alone is insufficient.
- **C4 (Standing Check Basis Discipline)** — Structures `Check.basis` to require `summary + rule_id + inspectable_refs`. C4 makes the *shape* of basis non-laundering. This gap names the *content* still being launderable.
- **GOV_GAP_INBOUND_CONTEXT_AUTHORITY_001** — Sibling: classifies inbound context surfaces before they enter the binding path. That gap is at the intake valve; this one is at the AUTHORIZE-receipt issuance valve. Same NLAI principle, different chokepoints.
- **GOV_GAP_LLM_PROVIDER_EGRESS_001** — Outbound twin to inbound classification; orthogonal to this gap.
- **`receipt_kernel`** — Already distinguishes evidence (content-addressed blobs) from decisions (RECEIPT events). The admissibility-check content semantics could later cash out as a constraint on which `inspectable_refs` resolve to evidence-class blobs vs. policy-declaration receipts vs. revocation records.

## Implementation Sketch (deferred)

Deliberately empty. Implementation requires a forcing case beyond the audit witness. Candidate ratification paths if forced:

- A registered admissibility-rule registry (parallel to the policy-declaration ratification path in C2): each `rule_id` resolves to a registered rule with declared scope, declared evidence kind, declared revocation pointer.
- An `admissibility_check` validator extension that requires `inspectable_refs` to resolve to a tuple of (rule registry entry, evidence ref, revocation-store query result) appropriate to the operation being authorized.
- A `claimForStep`-shaped resolver in the AG runtime, mirroring the Lean kernel's `Execution.lean` deferred work, tying receipts to the steps they authorize.

None of these are ratified. None should be built until a recurrent failure mode with a mechanical fix justifies it.

## Open Questions

1. Is `admissibility_check` semantics best expressed as a constraint on `basis` content (rule registry + ref resolution) or as a separate validation pass that runs after C3 schema validation?
2. How does the rule registry, if introduced, relate to existing artifacts: policy declarations (C2), `decisions/` ledger entries, doctrine docs in `docs/doctrine/`?
3. Is "admissibility for binding" axis-decomposable in the same way the Lean kernel decomposes (basis × precedence × standing), or does AG's four-axis schema (standing × admissibility × scope × budget) reflect a different cut? If different, which decomposition is canonical, and is the divergence material?
4. Where does operator override (CLAUDE.md's "Operator override" section) fit? Operator reaffirmation may be a legitimate admissibility basis for some operation classes, but it is currently undeclared.
5. Should `inspectable_refs` failing to resolve degrade `result` from `pass` to `escalate` automatically, or hard-fail validation? Likely escalate-not-block until forcing cases accumulate.

## Provenance

Filed 2026-04-30 during a session in which the Lean four-module Admissibility kernel (`Authority.lean` 14:58, `StateTransition.lean` 15:08, `Derivation.lean` 15:19, `Execution.lean` 15:27) closed the formal verdict↔mutation seam, after which a commercial-framing pass — "agents are not allowed to treat a claim as binding without admissible basis" — surfaced that the corresponding AG-side enforcement gap is one-sided: form discipline (C3) exists, content semantics does not. Filed as a containment vessel before any rule-registry or validator-extension work — preserves correct attribution (the laundering path is independent of any single proposed mechanism) and prevents the gap from being conflated with whatever specific schema or validator eventually closes it.
