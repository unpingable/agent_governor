# GOV_GAP_INBOUND_CONTEXT_AUTHORITY_001

## Title
Inbound context surfaces have no doctrine for what kind of authority they carry: classify before they enter the binding path.

## Status
Gap spec — containment vessel. **No schema, validator, or enforcement behavior is ratified by this filing.** Names the hole; future forcing cases promote.

## Origin

Filed 2026-04-30 after a session-level audit of `.claude/rules/implementation-summary.md` and `MEMORY.md`. Two concrete witnesses surfaced during that audit:

1. `implementation-summary.md` had grown to ~47k chars of shipped-feature recitals. The file was always-loaded and being read as "current project state" when its contents were historical inventory. The pathology was not "the file was wrong" — every line was factually accurate. The pathology was that **historical inventory was being treated as binding state simply because it was in context.**
2. `MEMORY.md` Active Design section contained the entry `validator C2 next code task` after C2/C3/C4/C5 had all shipped. The same shape: a once-true statement persisting as if it were a current task pointer.

Neither file declared its authority class. Both were read as if they had one.

The egress companion to this is `GOV_GAP_LLM_PROVIDER_EGRESS_001` (outbound: payload classification before transmission). This gap is its inbound twin: **classification of context surfaces before they acquire binding force.**

## Problem Statement

Agent_gov has rich machinery for what to do *with* a typed claim:
- `ReceiptRole` closed enum (observation < interpretation < recommendation < authorization < action) gates which receipts can do what.
- `AUTHORIZE_REQUIRED_CHECKS` (standing/admissibility/scope/budget) gates the AUTHORIZE transition.
- C5 `continuity_basis` is role-gated to `{recommendation, authorization, action}` — already enforces "binding requires standing" for one field.
- Evidence Gate, Premise Rule (HARD/SOFT), TTL volatility classes, Scope Governor tool contracts — all in place.

What does **not** exist is a doctrine for what authority *prose surfaces* carry by default when they enter agent context. README content, MEMORY.md entries, comments, issue text, generated summaries, tool output, hidden agent/session state, repo tree itself — all are **inbound context surfaces**. Some are prose, some are not. None of them currently declare what kind of claim, if any, they make.

The result: a stale summary, a once-true memory entry, a comment that no longer matches the code, can vote alongside live evidence with no ranking. NLAI says language is a proposal, not authority. This gap names the **intake valve** where that rule must operationalize: classify before the binding path.

## Non-goals

- **Not a validator.** No enforcement obligations created by this filing. Future forcing cases may promote.
- **Not a schema.** No `@authority` field, no frontmatter requirement, no metadata standard ratified. (Future work may explore one.)
- **Not a refactor of existing always-loaded rules.** This gap names the hole; it does not prescribe migration of existing files.
- **Not a continuity-system extension.** Continuity may eventually carry classification metadata, but originating it is Governor-shaped (admissibility), not continuity-shaped (preservation).
- **Not a context-manifest expansion.** `ContextManifest` already content-addresses what enters the prompt. This gap is orthogonal: classification of *kind*, not hashing of *bytes*.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `ReceiptRole` closed enum | Five roles ordered by binding strength; AUTHORIZE_REQUIRED_CHECKS gates promotion | No mapping from prose-surface kind to default role |
| `provenance_labels.py` | 7 source classes (repo/email/web/secret_store/user_input/generated/unknown), sensitivity hints | Source class is for *outbound* sensitivity, not *inbound* authority |
| `context_manifest.py` | ContextRegion, hash-stable manifest of system-prompt assembly | Manifests what entered; doesn't classify *kind of authority* of regions |
| `egress_gate.py` | Outbound classifier (destination + payload + rules) | No inbound twin; no classifier on what kind of context can bind |
| C5 `continuity_basis` role gate | Continuity claims role-gated to {recommendation, authorization, action} | Field-specific, not surface-general |
| CLAUDE.md NLAI principle | "Language is a proposal, not an authority" | Stated; not operationalized as an inbound-classification rule |

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Names the set of inbound context surfaces (README, MEMORY, session memory, spec/ADR/doctrine docs, receipts, operator commands, repo tree, CI output, issue/ticket text, generated summaries, tool output, hidden agent state — non-exhaustive).
2. Distinguishes the authority kinds an inbound surface may carry: **orientation**, **prior context**, **evidence**, **intent**, **scoped authority**, **admissible basis**.
3. States the default rule: **unclassified inbound context defaults to orientation/advisory.** It may inform inference; it must not bind action.
4. Distinguishes the operations clearly:
   - `infer_from`: allowed for any context
   - `bind_from`: requires named authority for the relevant state-kind
   - `act_from`: requires authority + evidence + standing
5. Explicitly records that no schema, validator, or enforcement behavior is ratified by the doctrine record itself.
6. Identifies the forcing cases that would justify promotion to schema/enforcement (e.g., a recurrent class of failure where unclassified prose binds incorrectly and a mechanical fix exists).

## Candidate Default Table (non-binding)

Filed as candidate-only per YAGNI-scope: name early, ratify lazily.

| Surface | Candidate default class |
|---------|------------------------|
| README / overview docs | orientation only |
| MEMORY.md / session memory | prior context only |
| Spec / ADR / doctrine doc | possible scoped authority |
| Receipt | evidence, not decision |
| Operator command | intent-state input |
| Repo tree | existence-state evidence |
| CI result | test-result evidence, not safety |
| Issue / ticket | coordination or intent, not completion |
| Generated summary | advisory compression only |
| Tool output | observed evidence within tool scope |

The candidate table is illustrative. It is not the doctrine; it is the shape the doctrine would take if ratified.

## Doctrine (proposed; not yet ratified)

> **Inbound context MUST NOT acquire binding force merely by being available to an agent.**

> **Authority is scoped by state-kind, operation, time, precedence, and evidence. Inbound context surfaces declare — explicitly or by default — what kind of authority they carry, if any.**

The first line is the rule. The second is the structural shape. Both are candidate doctrine until a forcing case promotes.

## Relationship to Other Gaps / Specs

- **NLAI (CLAUDE.md)**: Inbound classification is NLAI's intake valve. NLAI says language is a proposal; this gap operationalizes "proposal of *what kind*."
- **GOV_GAP_LLM_PROVIDER_EGRESS_001**: Outbound twin. Egress classifies before transmission; this gap classifies before binding. Same axis, opposite direction.
- **C5 Standing Continuity Basis**: Already enforces role-gated binding for one field (`continuity_basis`). The general rule this gap names is the same rule applied at intake.
- **`context_manifest.py`**: Hashes what entered. Could later carry classification metadata per region, but that is implementation, not doctrine.
- **`receipt_kernel`**: Already distinguishes evidence (content-addressed blobs) from decisions (RECEIPT events). The inbound side has no analogous distinction yet.

## Implementation Sketch (deferred)

Deliberately empty. Implementation requires a forcing case beyond the audit witnesses. Candidate ratification paths if forced:

- Frontmatter declaration on rules/spec files (`authority: scoped | orientation | evidence | …`).
- A classifier in the bootloader/context-assembler that tags inbound regions before the model sees them.
- Extension of `ContextRegion` to carry an `authority_class` field.

None of these are ratified. None should be built until a recurrent failure mode with a mechanical fix justifies it.

## Open Questions

1. Is "inbound context surface" a useful unit, or does the granularity need to drop to per-region (per-section, per-line)? The egress side classifies per-payload; the inbound side may need per-region.
2. Does a surface's authority class derive from its identity (path, file kind), its content (declared frontmatter), or both? Mixed-mode is likely but raises precedence questions.
3. How does this compose with `provenance_labels`? Provenance is outbound-sensitivity-shaped; authority is inbound-binding-shaped. Same primitive or distinct?
4. Where does session memory sit? It is generated content with prior-conversation provenance; ChatGPT's recommended default is "prior context only," but operator-issued memory entries (`feedback_*` files) may legitimately carry scoped feedback authority.
5. What is the right response to a binding attempt from unclassified prose? Hard refuse, downgrade to inference, or annotate and proceed? Likely downgrade-with-annotation, but unratified.

## Provenance

Filed 2026-04-30 during a session that audited `.claude/rules/implementation-summary.md` and restructured `MEMORY.md`'s Active Design section. The audit surfaced two concrete witnesses (47k-char feature-recital file voting as current state; "validator C2 next code task" entry voting after C2-C5 shipped) of the same pattern: prose acquiring binding force merely by being available. Filing this as a containment vessel before any inbound-classification work — preserves correct attribution (the failure mode is independent of any single proposed implementation) and prevents the gap from being conflated with whatever specific schema or validator eventually closes it.
