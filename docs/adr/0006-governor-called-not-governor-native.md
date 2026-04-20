---
audience: repo-local
status: active
---

# 0006 — Governor-Called, Not Governor-Native

## Status

Accepted

## Context

As Governor gained more integration points (Night Shift, NQ, the runtime supervisor, external diagnostic pipelines), a design question surfaced: should Governor *reason* — decomposing tasks, diagnosing failures, synthesizing repair plans — or should it only *adjudicate* proposals that reasoning produced elsewhere?

The tempting answer is "a little of both." Reasoning inside Governor feels efficient: no extra hop, no inter-service contract, the policy and the interpretation live in the same process.

But reasoning inside the authority layer has a predictable failure shape:

1. **Policy stops being the hard boundary.** The system starts "helpfully" interpreting around the rules.
2. **Receipts get muddy.** You can no longer tell whether an outcome came from explicit policy, operator standing, or latent model judgment.
3. **Override pressure becomes unreadable.** You lose the ability to distinguish bad policy from bad evidence from bad interpretation from a model freelancing under institutional cover.

This is the same failure mode as the NLAI principle already articulated in CLAUDE.md ("Language is a proposal, not an authority"), extended one level up: *reasoning* is also a proposal, not an authority, even when the reasoner is well-intentioned and sophisticated.

## Decision

**Reasoning is advisory power. Governor is constitutional power.**

Open-ended reasoning — diagnosis, decomposition, planning, ambiguity resolution, repair proposal generation — belongs outside the authority layer. Governor may consume reasoning artifacts, but it treats them as **claims with standing limits**, not as latent policy.

The layer roles:

- **NQ / evidence producers** — observe and accuse, do not authorize
- **Night Shift / reasoners** — interpret and recommend, do not bind
- **Governor** — authorize under declared policy, does not freelance
- **Tools / runtimes** — execute under explicit authorization parents, do not self-authorize

Standing is typed and the transitions are gated by receipts. Standing classes are closed: `OBSERVE`, `INTERPRET`, `RECOMMEND`, `AUTHORIZE`, `EXECUTE`, `POLICY_DECLARE`. Each transition requires an explicit new receipt; no artifact may acquire higher standing by implication.

See:

- [doctrine/advisory_vs_constitutional_power.md](../doctrine/advisory_vs_constitutional_power.md) — layer roles, invariants, failure modes
- [doctrine/standing_and_receipts.md](../doctrine/standing_and_receipts.md) — standing classes, receipt roles, parentage contract, required fields
- [doctrine/validator_contract.md](../doctrine/validator_contract.md) — the constitutional checks that make these rules operative

## Consequences

- **Governor does not natively reason.** It performs clerical cognition with closed consequence surfaces: schema validation, policy lookup, standing check, scope check, budget accounting, receipt normalization, closed-set routing. Uncertainty fails closed.
- **Reasoning artifacts enter Governor as proposals.** Night Shift produces interpretation and recommendation receipts; Governor adjudicates. This preserves the transition from evidence to verdict as a visible object rather than a model judgment.
- **Ontology drift is policy drift.** Any closed set Governor enforces — risk classes, action classes, exception classes, standing vocabulary — is a versioned policy artifact. Changes require `policy_declaration` lineage, not config edits.
- **The validator is itself governed.** Validator versions, rulesets, and registry interpretation are policy artifacts. Validation receipts carry validator identity, ruleset hash, and policy registry hash so historical chains cannot be silently reinterpreted under new semantics.
- **Deny on boundary uncertainty is a correctness condition, not a failure mode.** Operators will treat denial as operational failure. It is often the proof that the authority boundary is still alive.
- **This is structural, not advisory.** The validator catches violations at three levels: structural (missing parent, wrong role), semantic (ontology mismatch, gap paving), chain (content hash mismatch, forged parentage). The validator is the wall; types and envelopes are subordinate.

## Open integration questions

These are flagged in the validator contract and should be resolved before the first validator lands:

1. **Composition with `receipt_kernel`.** The existing `libs/receipt_kernel` provides an append-only hash-chained ledger with six constitutional invariants. Standing-class chains should emit through this ledger rather than building a parallel one — one hash chain per session, one audit surface. Decide the integration shape before writing the validator.
2. **`subject_derivation` must be a closed enum.** §5.2 of the validator contract permits subject transformations with a `basis` field. If `basis` is free text, Governor is doing interpretation through the back door. Constrain to a closed enum (`same_subject`, `instance_of`, `aggregation_of`, `scope_narrowing`) at first pass.
3. **Exception-class registry.** The `exception_class` field used by compressed authorization paths is itself an ontology. Additions must bump `ontology_version` and produce a `policy_declaration`.

## Source

- CLAUDE.md — "NLAI: Language is a proposal, not an authority"
- Design conversation establishing the advisory-vs-constitutional-power frame
- Receipt kernel stage graph (`docs/RECEIPT_KERNEL_CONTRACT.md`) — the existing lower-level analog of the standing-class lattice
- Compressed doctrine lines: "Make illegible discretion harder, not smarter." / "The prompt is not the policy."
