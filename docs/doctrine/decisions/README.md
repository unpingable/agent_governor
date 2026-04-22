---
audience: repo-local
status: active
---

# Doctrine Decisions

This directory holds ratified decisions referenced by gap specs and validator code as `policy_artifact_id` values. Each file is a `policy_declaration`-shaped artifact: it pins an option, records the basis, freezes acceptance criteria for downstream tests, and names what it does and does not ratify.

## Frontmatter schema (current)

```yaml
audience: repo-local
status: candidate | ratified
policy_artifact_id: decision.<scope>.<id>
ontology_version: gov-doctrine-v1
supersedes: null | <prior policy_artifact_id>
ratifier: <name + identifier>
ratified_at: <ISO 8601 UTC>
```

## Lifecycle

1. **Candidate.** AG (or any drafter) writes the file with `status: candidate` and `<pending>` in `ratifier` and `ratified_at`. The file is reviewable, editable, and uncommitted to force.
2. **Ratification.** The ratifier — the only constitutional actor for this step — flips `status: ratified`, fills `ratifier`, fills `ratified_at`, and commits.
3. **Immutable thereafter.** Ratified records are not edited. Corrections happen via a successor decision artifact with `supersedes: <prior policy_artifact_id>`. The prior record stays as the historical truth of what was ratified when.

## Open future work: seat-based authority

The current `ratifier` field collapses *who* and *from what seat*. That is acceptable while the project is effectively single-maintainer. It will not survive multi-maintainer use — at that point, doctrine should distinguish:

- `ratifier_principal` — the person who pulled the lever
- `ratifier_seat` — the office that carries the binding standing (e.g. `policy_authority`, `validator_maintainer`, `release_authority`, `operator_of_record`)
- `authority_basis` — the artifact that grants the seat its standing (ADR, charter, delegation receipt, repo ownership rule)

The principle:

> **Authority belongs to the seat. Accountability belongs to the occupant.**

Why this matters:
- **Succession.** When a seat changes hands, doctrine doesn't have to pretend the old occupant still *is* the office.
- **Multi-maintainer governance.** Different decisions belong to different seats; the schema should make that legible.
- **Advisory vs. constitutional separation.** A field named `architect` (or similar interpretive title) would muddy this — what gets recorded here is *binding standing*, not design influence.
- **Auditability.** Future readers can ask separately: which seat made this binding decision? Which person held that seat then?

The `ratifier` field stays as a transitional convenience. When the project gains a second maintainer or external user with binding authority over any part of the doctrine, this directory's schema should be extended (via its own `policy_declaration`) to include the three-field model. Existing ratified records are not retroactively rewritten — they stay valid under the original schema and `ontology_version` they were ratified under.

This note is not itself a ratification. It is an open future-work flag.

## Index of ratified decisions

| ID | File | Ratified |
|----|------|----------|
| `decision.validator_integration.q1` | [Q1-kernel-composition.md](Q1-kernel-composition.md) | 2026-04-19 |
| `decision.validator_integration.q2` | [Q2-subject-derivation.md](Q2-subject-derivation.md) | 2026-04-19 |
| `decision.validator_integration.q3` | [Q3-exception-class-registry.md](Q3-exception-class-registry.md) | 2026-04-19 |
| `decision.validator_integration.q4` | [Q4-validator-provenance.md](Q4-validator-provenance.md) | 2026-04-19 |
| `decision.validator.v0_1_0` | [validator-v0_1_0.md](validator-v0_1_0.md) | 2026-04-22 |

All four Q1–Q4 constitutional blockers are ratified. Validator implementation
(gap spec C2) shipped against them; the validator's own bootstrap
policy_declaration is `decision.validator.v0_1_0` (the first sanctioned
bootstrap hole, bounded by `expected_ruleset_hash` and Q4 supersession
rules). Q5 pre-ratification fallbacks were never introduced — the
validator landed with the ratified rules as final.
