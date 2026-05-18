---
audience: repo-local
status: active
---

# GOV_GAP_VALIDATOR_INTEGRATION_001

## Status
Proposed (2026-04-18)

## Origin
Doctrine in `docs/doctrine/{advisory_vs_constitutional_power, standing_and_receipts, validator_contract}.md` and ADR 0006 are stable. Before the first validator lands, five integration questions must be pinned down or the validator will invent policy to fill the gaps. That is exactly the failure the doctrine exists to prevent.

## Thesis

> The validator is the constitutional wall. Every question it is left to answer *ad hoc* becomes load-bearing policy that nobody declared.

This spec pins five such questions to falsifiable shapes. It does not resolve them in prose — it reduces each to a small number of options and an acceptance test, so the resolution is a decision and not a mood.

## Non-goals

- Writing the validator
- Finalizing the receipt envelope schema
- Ratifying any specific option below — this spec sets the targets, not the verdicts

---

## Q1. Receipt kernel composition

**Question.** What is the canonical hashed body of a standing-class receipt, and which fields are committed inside the hash vs. carried as advisory/display metadata outside it?

**Options.**
- **A. Emit through `receipt_kernel`.** Standing-class events are receipt_kernel events with a `receipt_role` + `standing_class` envelope. One hash chain per session; the six receipt_kernel invariants apply uniformly. Display metadata (e.g. operator-facing summaries) lives outside the committed blob.
- **B. Parallel store that cites kernel events as evidence.** Standing-class chain has its own content-addressed store, referencing receipt_kernel events by hash for underlying evidence.
- **C. Dual write.** Standing-class receipts committed to their own hash chain *and* mirrored as receipt_kernel events.

**Invariant impacted.** §5 parentage contract + §6 content-bound parents (standing_and_receipts). `ledger.chain_valid` + `receipt.completeness` (receipt_kernel).

**Provisional recommendation.** **A**. One hash chain per session, one set of chain-integrity invariants, one audit surface. B fragments the audit surface; C doubles it and creates two possible truths.

**Acceptance criteria.**
1. A receipt committed to the chain can be re-hashed from its canonical form and produce the stored hash.
2. `parent_receipts[].content_hash` references resolve against the same chain the child is committed to.
3. The six receipt_kernel invariants continue to pass when standing-class receipts are present in the stream.
4. Display metadata that is not in the canonical body cannot change the receipt hash when edited.

**Falsification.** If A requires the receipt_kernel `StageGraph` to be relaxed or bypassed to fit standing-class transitions, A is wrong — standing-class is a *higher* level of structure, not a looser one.

---

## Q2. `subject_derivation` closed set

**Question.** What values does `subject_derivation.kind` take, and when does derivation fail?

**Options.**
- **A. Closed enum, four values**: `same_subject`, `instance_of`, `aggregation_of`, `scope_narrowing`. Any other value is `INVALID_STRUCTURAL`.
- **B. Closed enum with registry extension.** Same four, plus additions require `policy_declaration` lineage (same rule as ontology drift).
- **C. Open `kind` with required `basis` prose.** Validator does not check semantics beyond presence.

**Semantics (provisional, under A/B).**
- `same_subject` — child subject byte-equals at least one parent subject. No derivation record required.
- `instance_of` — child subject is a concrete member of a parent subject class. Parent must be a class-shaped subject; child must reference it by hash.
- `aggregation_of` — child subject is the aggregate of N named parent subjects. All N must appear in `parent_receipts`.
- `scope_narrowing` — child subject is a strictly contained sub-scope of a parent subject. Containment must be mechanically checkable (prefix, set-membership, or declared scope-axis narrowing).

**Derivation fails when.**
- kind not in the closed set
- required parent relationship cannot be verified against `parent_receipts`
- containment claim (for `scope_narrowing`) cannot be checked mechanically
- child subject has no relation to any parent subject that fits a declared kind

**Invariant impacted.** §5.2 (standing_and_receipts) + §5.2 subject-lineage coherence (validator_contract). Prevents Governor smuggling interpretation in via `basis` prose.

**Provisional recommendation.** **B**. Start with the four values; additions must go through `policy_declaration`. Rejects C outright — free-text `basis` is the exact back door the doctrine closes at §3.1.

**Acceptance criteria.**
1. Every `subject_derivation` on a valid chain has a `kind` in the registered set.
2. For each kind, there is a mechanical check the validator runs — no human judgment in the loop.
3. Adding a new kind requires a `policy_declaration` receipt; retrofitting cannot rewrite prior receipts under the new kind.

**Falsification.** If a legitimate receipt chain in the agent_gov codebase today requires a subject transformation that does not fit the four kinds, the enum is too narrow — widen deliberately, do not add `other`.

---

## Q3. Exception-class registry

**Question.** What counts as a legitimate `OBSERVE -> AUTHORIZE` compression, who declares it, how is it versioned, and how is it counted?

**Options.**
- **A. Closed registry, policy-declared.** Every `exception_class` must appear in a ratified `policy_declaration`. Unknown classes → `INVALID_STRUCTURAL`. Additions bump `ontology_version`.
- **B. Open registry with telemetry-only policing.** Any string accepted; validator counts occurrences per class; operators review drift.
- **C. Binary flag only.** One `compression_exception = true` bit; no class taxonomy. Accept or deny.

**Declaration requirement (under A).** A `policy_declaration` of an exception class must include:
- `exception_class` name
- allowed source standing + allowed target standing (first pass: `OBSERVE -> AUTHORIZE` only)
- required parent-receipt evidence (e.g. explicit `operator_approval`)
- scope limits
- expiry or review date

**Counting requirement.** Validator telemetry must separate counts by `exception_class`. A single flat counter hides ontology drift inside the exception space itself — which is the failure mode this whole stack is trying to prevent.

**Invariant impacted.** §5.3 (validator_contract) + §9 ontology drift is policy drift (standing_and_receipts).

**Provisional recommendation.** **A**. This *is* ontology, and the doctrine says ontology drift is policy drift. B defers the problem; C erases it.

**Acceptance criteria.**
1. A `VALID_WITH_EXCEPTION` outcome requires a resolvable, ratified `exception_class`.
2. Compressed authorization telemetry is keyed by `exception_class`; counts per class are queryable.
3. Adding an exception class produces a `policy_declaration`; the prior chain remains interpretable under its original `ontology_version`.
4. If operator_approval is required by the class's declaration, its absence makes the authorization `INVALID_SEMANTIC`, not `VALID_WITH_EXCEPTION`.

**Falsification.** If operators under load routinely invent new `exception_class` strings to get past denial, A is not failing — A is working, and the receipts make that visible. If the validator's exception counter stays at zero across a week of real traffic, the gate is probably too loose elsewhere, not too tight here.

---

## Q4. Validator provenance

**Question.** What must a validation receipt carry, and how are validator rule changes governed?

**Mandatory fields on every `validation` receipt.**
- `validator_id`
- `validator_version` — semver, not a git sha (sha goes in `ruleset_hash`)
- `ruleset_hash` — content hash of the rules actually applied
- `policy_registry_hash` — snapshot of the registry at validation time
- `validated_at` — UTC timestamp
- `target_receipts` — list of `{id, content_hash}` references being validated
- `outcome` — one of `VALID | INVALID_STRUCTURAL | INVALID_SEMANTIC | INVALID_CHAIN | VALID_WITH_EXCEPTION`
- `violations` — list (empty on VALID)
- `exceptions` — list (empty unless VALID_WITH_EXCEPTION)

**Rule-change governance.**
- **A. Every validator version is a `policy_declaration`.** Validator rules are policy. Bumping the version requires ratified declaration with `supersedes`.
- **B. Only semantic changes require declaration; bug fixes do not.** Bug vs. semantic is decided by the committer.
- **C. No governance; validator changes are normal code changes.**

**Historical reinterpretation.** Validation receipts are point-in-time. A new validator version may produce a new validation receipt for a historical chain, but must not replace or invalidate the prior one. The chain's validity under validator vN remains the chain's validity under validator vN, forever.

**Invariant impacted.** §16 validator versioning (validator_contract). Without this, the validator becomes the new ungoverned root the rest of the doctrine just eliminated.

**Provisional recommendation.** **A**. B relies on committer judgment for the bug/semantic distinction, which is exactly the kind of illegible discretion the validator exists to prevent. C is the failure mode.

**Acceptance criteria.**
1. Every validator run produces a `validation` receipt with all mandatory fields.
2. `validator_version` changes land with a `policy_declaration` receipt referencing the prior version as `supersedes`.
3. A chain re-validated under a new validator version produces a *new* validation receipt; the prior one is not mutated or deleted.
4. `ruleset_hash` mismatch between declaration and actual rules loaded → validator refuses to run (fail-closed).

**Falsification.** If A makes routine validator iteration impossibly heavy, the declaration process is too expensive — fix the declaration process, not the rule. Doctrine does not bend because the plumbing is awkward.

---

## Q5. Failure behavior when an integration question is unresolved

**Question.** Until Q1–Q4 are ratified, what does the validator do when it hits them?

**Options per unresolved question.**
- **deny** — treat any receipt depending on the unresolved surface as `INVALID_*`
- **non-binding** — accept structurally, mark non-binding for `AUTHORIZE`/`EXECUTE`, emit advisory telemetry
- **`VALID_WITH_EXCEPTION`** — accept, but count under a synthetic `exception_class: unresolved_integration_q{N}` that is itself declared as a temporary exception class

**Provisional assignments.**

| Question | Pre-ratification behavior | Reason |
|----------|---------------------------|--------|
| Q1 receipt kernel composition | **deny** if `content_hash` cannot be resolved through receipt_kernel; else non-binding | chain integrity is foundational — without it `parent_receipts` is theater |
| Q2 `subject_derivation` | **deny** if `kind` not in provisional enum; else VALID | no free-text back door; start strict |
| Q3 exception-class registry | **VALID_WITH_EXCEPTION** under synthetic class `unresolved_integration_q3` | compressed paths must be visible even before the registry is ratified |
| Q4 validator provenance | **non-binding** for validation receipts lacking full fields; validator still runs | bootstrapping requires emitting validation receipts before the declaration process is in place |
| Q5 (this) | — | — |

**Invariant impacted.** §8 fail-closed rules + §12 failure behavior (validator_contract). Unresolved integration surfaces must not become the soft place the validator's judgment lives.

**Acceptance criteria.**
1. Every pre-ratification fallback is itself a named surface with telemetry, not an implicit behavior.
2. No pre-ratification fallback can promote a receipt from non-binding to binding.
3. When a question is resolved, the fallback behavior is removed in the same change that ratifies the resolution. Dead fallbacks are deleted, not left "just in case."

**Falsification.** If any pre-ratification fallback is still in the validator after its corresponding question is ratified, the validator has acquired vestigial policy and the doctrine has been silently weakened.

---

## Build Order

Resolve in this order. Each resolution closes one degree of freedom the validator would otherwise invent.

1. **Q1** — receipt kernel composition. Foundational; every other question assumes a chain integrity story.
2. **Q4** — validator provenance. The validator can't land without knowing what receipt it emits.
3. **Q2** — `subject_derivation` closed set. Needed before the validator implements parentage checking.
4. **Q3** — exception-class registry. Needed before `VALID_WITH_EXCEPTION` is a legal outcome in practice.
5. **Q5** — collapse pre-ratification fallbacks as Q1–Q4 ratify.

## Ratification boundary

A question is **ratified** only when all three are true:

1. **An option is selected.** Not "we discussed it" — a written choice that names the option (`Q1: A`, `Q2: B`, etc.) and supersedes any prior provisional recommendation.
2. **Acceptance criteria are committed to tests.** The criteria listed under each question land as executable assertions in the test suite, not as prose in a doc.
3. **The selection is committed as a hash-referenceable artifact in the repo.** A `policy_declaration`-shaped record in `docs/doctrine/decisions/` (or equivalent), with `policy_artifact_id`, `ratifier`, and `supersedes` fields populated.

"It seems clear" is not ratification. "ChatGPT agreed" is not ratification. "I'll just write the validator and we can adjust" is the failure mode this whole spec exists to prevent.

The validator may not begin until the corresponding ratification artifact exists. Pre-ratification commits to the validator surface are reverted, not retrofitted.

## Schema discipline

Schema work is downstream of validator implementation, which is downstream of Q1–Q4 ratification. **The receipt envelope schema is not allowed to land before the validator.**

The temptation is real: schema feels like neutral plumbing, the validator feels heavier, so people write the schema first "to unblock things." This bakes half the policy into the shape layer where it cannot be refused. Every field shape is a constitutional choice; deciding them in a JSON schema before the validator's checks are pinned is exactly how the validator inherits a policy it never ratified.

Order is fixed:
1. Q1–Q4 ratified
2. Validator written against ratified resolutions
3. Schema written to satisfy the validator (not the other way around)

## Acceptance for this gap spec

This gap is closed when:
- Q1–Q4 each have a ratified resolution per the boundary above
- Q5's pre-ratification fallbacks are all either removed or promoted into declared policy
- The first validator implementation references this spec and its resolutions by hash, not by prose

Until then, neither the validator nor the receipt envelope schema is allowed to be written.

## Compressed lines

- The validator is the constitutional wall; unresolved integration questions are holes in the wall.
- A question deferred to implementation becomes policy declared by whoever writes the code.
- 3am still votes for monarchy. This is the padlock.
