# PCAR-A: Typed Claim Envelope
## Claim Serialization and Speech-Act Discipline for Proof-Carrying Agent Runtime

- **Status:** Draft
- **Version:** 0.1.0
- **Family:** PCAR
- **Depends on:** PCAR-000
- **Last Updated:** 2026-02-21
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-A defines the **Typed Claim Envelope** contract for model-emitted content in a Proof-Carrying Agent Runtime (PCAR).

PCAR-A requires model outputs to be represented as typed, structured claims rather than untreated prose. The purpose is to preserve distinctions that natural language tends to collapse, including:
- observation vs inference,
- assumption vs plan,
- request vs fact,
- policy reasoning vs policy authority.

PCAR-A does not determine whether a claim is true. It determines how claims are represented so downstream verification and control layers can process them without linguistic ambiguity.

---

## 2. Scope

PCAR-A specifies:

- claim envelope fields,
- required claim types,
- parsing and normalization rules,
- downgrade behavior for untyped/ambiguous text,
- claim references and evidence placeholders,
- claim-level error semantics.

PCAR-A does **not** specify:

- proof object schemas (PCAR-B),
- constraint evaluation (PCAR-C),
- receipt hashing/canonicalization (PCAR-D),
- actuation contracts (PCAR-E),
- policy contents (PCAR-C/Policy Pack).

---

## 3. Design Goals

### 3.1 Preserve Speech-Act Semantics
A runtime MUST be able to distinguish:
- "I observed X"
- "I infer X"
- "I assume X"
- "I plan X"
- "I request action X"

These are not equivalent and MUST NOT be flattened.

### 3.2 Eliminate Free-Text Authority Paths
Untyped prose may exist for human readability, but it MUST NOT be accepted as authoritative for consequential execution.

### 3.3 Enable Deterministic Parsing
Claim representations MUST be machine-parseable, deterministic, and robust against formatting drift.

### 3.4 Support Verification and Replay
Claim envelopes MUST preserve enough structure for:
- verifier targeting,
- policy evaluation,
- incident replay.

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Claim Envelope
A structured object representing one propositional unit or action request emitted by the proposer (model runtime or claim compiler).

### 5.2 Claim Compiler
A runtime component that parses raw model output into Claim Envelopes. A claim compiler may consume:
- structured model output, or
- plain text + parser heuristics.

### 5.3 Evidence Placeholder
A claim-level declaration that indicates what evidence/proof is expected for verification. Placeholders are not proof objects.

### 5.4 Untyped Content
Model-emitted content that cannot be reliably classified into a claim type with sufficient confidence or structure.

---

## 6. Conformance Targets

PCAR-A conformance applies to two implementation classes:

### 6.1 Native Claim Emitters
Systems where the model emits Claim Envelopes directly (e.g., JSON mode, schema-constrained decoding).

### 6.2 Compiled Claim Emitters
Systems where a Claim Compiler derives Claim Envelopes from raw prose or mixed-format model output.

Both classes MUST produce equivalent Claim Envelope semantics.

---

## 7. Processing Model (PCAR-A)

### 7.1 Input
PCAR-A accepts:
- raw model output (text and/or structured data),
- runtime metadata (turn ID, scope defaults, parser version, timestamp),
- optional parser hints.

### 7.2 Output
PCAR-A outputs:
- an ordered sequence of Claim Envelopes,
- zero or more PCAR-A parsing/typing errors,
- optional residual untargeted text segments (which MUST be downgraded).

### 7.3 Determinism
Given identical input payload, parser version, and parsing configuration, a Claim Compiler MUST produce the same Claim Envelope sequence and error set.

---

## 8. Claim Envelope Schema (Normative)

A Claim Envelope is a structured object with the following fields.

### 8.1 Required Fields

#### `claim_id` (string)
A unique identifier within the current claim batch/run segment.

Requirements:
- MUST be unique within the batch.
- SHOULD be stable under deterministic reparse of identical input.
- SHOULD be content-independent if downstream stages mutate claim content; otherwise content-hash-based IDs MAY be used only after normalization.

#### `claim_type` (enum)
See Section 9.

#### `content` (object)
Normalized claim payload. Shape depends on `claim_type` (Section 10).

#### `emitted_at` (timestamp)
Claim emission time in RFC 3339 format with explicit timezone or UTC `Z`.

#### `scope` (object)
The target domain of the claim.

Minimum required members:
- `scope_type` (enum/string), e.g. `repo`, `filesystem`, `host`, `api`, `chat`, `policy`
- `scope_ref` (string), e.g. repo identifier, path root, host label, API object namespace

If scope is unknown, the compiler MUST emit an explicit unknown scope:
- `scope_type = "unknown"`
- `scope_ref = ""`

#### `provenance` (object)
Metadata about where the claim came from.

Required members:
- `source_type` — `model_native` or `compiled_from_text`
- `source_ref` — runtime-specific source identifier (turn ID, chunk ID, message ID)
- `compiler_version` — parser/compiler version string (or emitter version for native)
- `span` — source span if available (start/end offsets, token range, or chunk references)

### 8.2 Optional Fields

#### `references` (array)
References to prior claims and/or runtime entities.

Allowed reference object members:
- `ref_type` — `claim`, `message`, `tool_intent`, `policy_section`, `external`
- `ref_id` — identifier
- `relation` — e.g. `supports`, `contradicts`, `supersedes`, `depends_on`

#### `evidence_placeholders` (array)
Expected evidence categories required for verification.

Each placeholder object SHOULD include:
- `placeholder_id`
- `expected_proof_type` (aligned with PCAR-B type vocabulary when available)
- `subject` (what needs to be proven)
- `freshness_required` (boolean, optional)
- `notes` (optional)

Evidence placeholders are not proof and MUST NOT be treated as proof.

#### `confidence` (number or object)
Optional non-authoritative metadata from the proposer/compiler.

If numeric, MUST be in `[0.0, 1.0]`.

If object, SHOULD include:
- `score`
- `source` (e.g. `model_self_report`, `parser_heuristic`)
- `calibrated` (boolean, optional)

Confidence MUST NOT be used as a substitute for proof.

#### `labels` (array of strings)
Implementation-defined tags for routing, analysis, or observability.

#### `extensions` (object)
Reserved namespace for implementation-specific fields.

Implementations MUST NOT place normative semantics exclusively in `extensions`.

---

## 9. Claim Types (Normative)

PCAR-A implementations MUST support the following base claim types.

### 9.1 `OBSERVED`
The proposer asserts that a claim is derived from an observed artifact, tool output, or externally acquired data.

Requirements:
- MUST include at least one `evidence_placeholder`, unless the claim is immediately bound to a proof object by a native integration.
- MUST NOT be emitted solely from model introspection.
- MUST identify the observed subject in `content`.

Examples:
- "`pytest` returned 3 failures"
- "File `foo.py` exists"
- "HTTP response was 500"

### 9.2 `INFERRED`
A conclusion drawn from one or more observations or prior claims.

Requirements:
- SHOULD include `references` to supporting claims when available.
- MUST NOT be upgraded to `OBSERVED` without proof-backed observation.

Examples:
- "Tests likely fail due to import error"
- "This branch appears stale relative to main"

### 9.3 `ASSUMED`
A provisional premise used to proceed in the absence of proof.

Requirements:
- MUST mark uncertainty explicitly in `content`.
- MUST NOT be treated as execution authority without downstream verification.
- SHOULD trigger verifiers to satisfy missing placeholders before consequential action.

Examples:
- "Assuming the repo root is `/workspace`"
- "Assuming user wants a patch, not just diagnosis"

### 9.4 `PLANNED`
An intended future step or sequence.

Requirements:
- MUST describe intended action(s) without implying completion.
- MUST NOT be used as evidence that an action occurred.
- MAY include `references` to motivating claims.

Examples:
- "Run tests, inspect traceback, patch import, rerun"
- "Check API schema before issuing write call"

### 9.5 `REQUESTED_ACTION`
A structured request for the runtime to perform an action.

Requirements:
- MUST use the `content` shape for action intent (Section 10.5).
- MUST NOT itself constitute authority to execute.
- MUST be evaluated by PCAR-C and validated by PCAR-E before actuation.

Examples:
- "Execute `pytest -q` in repo scope"
- "Write patch to `src/module.py`"

### 9.6 `UNVERIFIED`
Untyped, ambiguous, or otherwise non-authoritative content.

Requirements:
- MUST be used for:
  - parsing failures,
  - ambiguous propositions,
  - free-form commentary not safely classifiable,
  - prose fragments carrying potential factual semantics without structure.
- MUST NOT be treated as authoritative for consequential action.
- MAY be preserved for human readability and later reparse.

Examples:
- "Looks good now" (without evidence)
- "I think that should work" (without structured support)

### 9.7 `POLICY_INTERPRETATION`
Reasoning about policy or constraints as understood by the proposer.

Requirements:
- MUST NOT be treated as policy authority.
- SHOULD reference policy identifiers/sections if available.
- MUST be subject to PCAR-C policy evaluation.

Examples:
- "This seems to require read-only mode"
- "This action may violate deploy policy"

---

## 10. `content` Payload Shapes (Normative)

The `content` object is typed by `claim_type`. Implementations MAY add fields, but MUST preserve required members.

### 10.1 Common `content` Members (All Claim Types)
All claim `content` objects MUST include:

- `text` (string): normalized human-readable formulation of the claim
- `subject` (object): what the claim is about
- `predicate` (string): short machine-usable predicate label (implementation-defined but stable)
- `object` (object|string|number|boolean|null): the asserted or requested value/content

This is intentionally simple. Do not overfit ontology on day one.

### 10.2 `OBSERVED` Content
In addition to common members, `OBSERVED` SHOULD include:

- `observation_kind` (string), e.g. `tool_output`, `filesystem`, `api_response`, `user_input`
- `observed_source_hint` (string/object), e.g. tool name, path, endpoint, stream chunk
- `raw_excerpt` (string, optional, non-authoritative)
- `units` (string, optional)
- `measurement` (number/string/object, optional)

### 10.3 `INFERRED` Content
`INFERRED` SHOULD include:

- `inference_kind` (string), e.g. `causal`, `diagnostic`, `classification`, `risk_estimate`
- `basis_summary` (string)
- `assumption_refs` (array of claim IDs, optional)

### 10.4 `ASSUMED` Content
`ASSUMED` SHOULD include:

- `assumption_kind` (string), e.g. `environment`, `intent`, `availability`, `schema`
- `revalidation_required` (boolean, default `true`)
- `fallback_behavior` (string, optional)

### 10.5 `PLANNED` Content
`PLANNED` MUST include:

- `plan_steps` (array of step objects)

Each step object MUST include:
- `step_id`
- `verb` (string)
- `target` (object/string)
- `consequential` (boolean)
- `depends_on` (array of claim IDs or step IDs, optional)

A `PLANNED` claim MAY describe a single step.

### 10.6 `REQUESTED_ACTION` Content
`REQUESTED_ACTION` is the bridge to PCAR-E and MUST be structured.

Required members:
- `action_type` (string)
- `parameters` (object)
- `target_scope` (object)
- `requested_by` (string; usually `model` or compiler identity)
- `consequential` (boolean; MUST be `true` for state-changing actions, MAY be `false` for reads)
- `idempotency_hint` (string, optional)
- `requires_verification` (boolean; SHOULD default `true`)
- `expected_effect` (string, optional)

Optional members:
- `preconditions` (array)
- `suggested_proof_types` (array)
- `expiry_hint` (duration/timestamp, non-authoritative)

`REQUESTED_ACTION` MUST NOT include direct authorization fields such as:
- `approved = true`
- `policy_passed = true`
- `verified = true`

Any such field MUST be ignored or downgraded and SHOULD emit `PCAR_A_FORBIDDEN_AUTHORITY_FIELD`.

### 10.7 `UNVERIFIED` Content
`UNVERIFIED` MUST include:

- `raw_text` (string)
- `downgrade_reason` (enum/string)
- `parse_confidence` (optional number/object)

`UNVERIFIED` MAY include best-effort extracted subject/object fields, but these remain non-authoritative.

### 10.8 `POLICY_INTERPRETATION` Content
`POLICY_INTERPRETATION` SHOULD include:

- `policy_ref_hint` (string/object, optional)
- `interpretation_kind` (string), e.g. `scope`, `risk`, `permission`
- `recommended_mode` (string, optional)
- `uncertainty` (string/object, optional)

---

## 11. Claim Batches and Ordering

PCAR-A outputs claims as an ordered batch.

### 11.1 Batch Requirements
A claim batch MUST include:
- `batch_id`
- `emitted_at`
- `claims` (ordered array)
- `parser_version`
- `source_ref`

### 11.2 Order Semantics
Claim order MUST preserve source order unless the compiler records an explicit reordering rationale.

If reordering occurs, the batch MUST include:
- `ordering = "reordered"`
- `ordering_reason`

Default:
- `ordering = "source_order"`

### 11.3 Incremental/Streaming Output
Streaming implementations MAY emit partial claim batches.

If so, each partial batch MUST include:
- stable `batch_id`
- monotonically increasing `sequence_no`
- `is_final` boolean

Partial claims MUST NOT be silently rewritten after emission; revisions MUST be represented explicitly (Section 14).

---

## 12. Parsing and Downgrade Rules (Normative)

This is the important part.

### 12.1 Untyped Consequential Language
If the compiler detects language implying a consequential fact or completion (examples: "done", "fixed", "deployed", "tests pass") without sufficient structure, it MUST emit an `UNVERIFIED` claim.

It MAY additionally emit a `PCAR_A_UNTYPED_CONSEQUENTIAL_TEXT` error.

### 12.2 Ambiguous Type Resolution
If content could plausibly be multiple claim types and no deterministic rule resolves it, the compiler MUST choose `UNVERIFIED`, not a stronger type.

### 12.3 Observation Claims Without Evidence Placeholder
If a claim is typed as `OBSERVED` and lacks evidence placeholders (or direct proof binding in native mode), the compiler MUST:
- downgrade to `UNVERIFIED`, or
- emit `OBSERVED` plus `PCAR_A_MISSING_EVIDENCE_PLACEHOLDER` (implementation policy selectable).

The default SHOULD be downgrade.

### 12.4 Completion Language
Statements implying completion MUST be represented as one of:
- `OBSERVED` (with evidence placeholder/proof path), or
- `INFERRED` (with references), or
- `UNVERIFIED`

A compiler MUST NOT infer completion from imperative or future-tense text.

### 12.5 Softeners and Hedging
Words like "probably," "maybe," "I think" do not automatically imply `ASSUMED`.

Type selection depends on semantics:
- observation with hedging → `INFERRED` or `UNVERIFIED`
- explicit provisional premise → `ASSUMED`

### 12.6 Commentary and Rationale
Human-readable commentary MAY be preserved, but any commentary carrying factual or execution significance MUST be typed. Otherwise it MUST be `UNVERIFIED`.

---

## 13. Claim References and Cross-Claim Semantics

### 13.1 Reference Integrity
References to other claims MUST target existing `claim_id` values within the same batch or a known prior batch/run scope.

Unknown references MUST emit `PCAR_A_UNKNOWN_REFERENCE`.

### 13.2 Contradictions
PCAR-A MAY annotate contradictions when obvious (e.g., same subject/predicate with incompatible objects), but contradiction adjudication is not a PCAR-A responsibility.

If emitted, contradiction annotations SHOULD use `labels` or `references.relation = "contradicts"`.

### 13.3 Supersession / Revision
Claims are immutable once emitted in a batch. Revisions MUST be represented as new claims with:
- `references: [{ref_type:"claim", ref_id:"...", relation:"supersedes"}]`

Compilers MUST NOT mutate historical claims in place in replayable contexts.

---

## 14. Revision and Streaming Semantics

### 14.1 Claim Immutability
Within a persisted claim batch, a Claim Envelope MUST be immutable.

### 14.2 Explicit Revision
Corrections or refinements MUST emit a new claim and reference the prior claim via `supersedes` or `clarifies`.

### 14.3 Partial Parse Upgrades
A streaming compiler MAY first emit `UNVERIFIED` for an ambiguous fragment and later emit a typed claim after more context arrives.

In that case, the typed claim SHOULD reference the earlier `UNVERIFIED` claim with:
- `relation = "clarifies"` or `"supersedes"`

This preserves replay truth instead of pretending the ambiguity never happened.

---

## 15. Error Model (Normative)

PCAR-A errors MUST be machine-readable and non-authoritative. Errors SHOULD be emitted alongside claim batches.

### 15.1 Error Object Shape
Each error object MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `source_ref`
- `span` (if available)
- `claim_id` (if applicable)

### 15.2 Required Error Codes

#### Parsing / Typing
- `PCAR_A_PARSE_FAILURE`
- `PCAR_A_AMBIGUOUS_CLAIM_TYPE`
- `PCAR_A_UNTYPED_CONSEQUENTIAL_TEXT`
- `PCAR_A_UNSUPPORTED_CLAIM_TYPE`

#### Schema
- `PCAR_A_MISSING_REQUIRED_FIELD`
- `PCAR_A_INVALID_FIELD_TYPE`
- `PCAR_A_INVALID_TIMESTAMP`
- `PCAR_A_INVALID_SCOPE`

#### Observation Discipline
- `PCAR_A_MISSING_EVIDENCE_PLACEHOLDER`
- `PCAR_A_OBSERVED_WITHOUT_SOURCE_HINT`

#### Reference Integrity
- `PCAR_A_UNKNOWN_REFERENCE`
- `PCAR_A_INVALID_REFERENCE_RELATION`

#### Action Safety
- `PCAR_A_INVALID_ACTION_CONTENT`
- `PCAR_A_FORBIDDEN_AUTHORITY_FIELD`
- `PCAR_A_MISSING_TARGET_SCOPE`
- `PCAR_A_CONSEQUENTIAL_FLAG_MISMATCH`

#### Misc
- `PCAR_A_DUPLICATE_CLAIM_ID`
- `PCAR_A_EXTENSION_NAMESPACE_COLLISION`

### 15.3 Error Handling Rules
- A parser/compiler MUST NOT drop unparseable consequential content silently.
- Unparseable content MUST become `UNVERIFIED` and/or emit an error.
- Errors MUST NOT be treated as proof or policy outcomes.

---

## 16. Canonicalization (PCAR-A Profile)

PCAR-D will define canonical receipt hashing. PCAR-A still needs stable normalization so claims are portable.

### 16.1 Required Normalization
Before persistence or handoff, a Claim Envelope MUST be normalized for:
- field name casing (lower_snake_case)
- timestamp format (RFC 3339)
- string trimming (implementation-defined but deterministic)
- array ordering where semantic order is required (`claims`, `plan_steps`, `references`)
- null/omitted handling (policy-defined and deterministic)

### 16.2 Canonical Serialization for Interop
Implementations SHOULD support canonical JSON serialization for Claim Envelopes and claim batches.

If claims are hashed directly (outside PCAR-D receipts), the implementation MUST document:
- canonical format,
- float precision rules,
- Unicode normalization,
- omitted/null policy.

---

## 17. Security Considerations (PCAR-A Specific)

### 17.1 Prompt Injection via Type Confusion
Attackers may try to induce stronger claim types ("observed", "verified") through prose. Claim compilers MUST infer types from structure and semantics, not merely keywords.

### 17.2 Authority Smuggling
Model output may include fields like `verified=true`, `approved`, or "policy passed." Such fields MUST be ignored/downgraded at PCAR-A and MUST NOT bypass PCAR-C/PCAR-E.

### 17.3 Hidden Completion Claims
Phrases like "done," "fixed," and "works now" are high-risk for language laundering. Compilers SHOULD treat them as consequential-language triggers and require explicit typing or downgrade.

### 17.4 Scope Inflation
A `REQUESTED_ACTION` with broad or missing scope is dangerous. PCAR-A MUST preserve explicit scope representation; unknown scope MUST remain unknown and MUST NOT be silently expanded.

---

## 18. Privacy Considerations (PCAR-A Specific)

Claim content and provenance spans may contain sensitive text. Implementations SHOULD support:
- source span redaction,
- content redaction with placeholders,
- selective omission of `raw_excerpt` / `raw_text`.

Redaction MUST NOT alter claim type semantics or reference integrity without explicit indication.

---

## 19. Conformance

An implementation is **PCAR-A conformant** if it:

1. Produces Claim Envelopes matching Section 8.
2. Supports all required claim types in Section 9.
3. Applies downgrade behavior in Section 12.
4. Emits machine-readable errors per Section 15.
5. Preserves deterministic claim ordering and identity semantics.
6. Does not allow untyped content to act as execution authority.

Implementations MAY be profiled as:
- **PCAR-A Native** (schema-constrained model output)
- **PCAR-A Compiled** (post-parse from prose)

---

## 20. Informative Examples

### 20.1 Example: Proper Observation Claim

```json
{
  "claim_id": "c-001",
  "claim_type": "OBSERVED",
  "content": {
    "text": "pytest returned 3 failures",
    "subject": {"kind": "command", "value": "pytest -q"},
    "predicate": "command_result",
    "object": {"failures": 3},
    "observation_kind": "tool_output",
    "observed_source_hint": {"tool": "shell", "stream": "stdout"}
  },
  "evidence_placeholders": [
    {
      "placeholder_id": "ep-001",
      "expected_proof_type": "TEST_RESULT",
      "subject": "pytest -q result",
      "freshness_required": true
    }
  ],
  "emitted_at": "2026-02-21T17:00:00Z",
  "scope": {"scope_type": "repo", "scope_ref": "repo://example"},
  "provenance": {
    "source_type": "model_native",
    "source_ref": "turn-42",
    "compiler_version": "native-json-v1",
    "span": {"kind": "message", "start": 0, "end": 1}
  }
}
```

### 20.2 Example: Language Laundering Downgraded

Raw model text:

> Done — tests pass and I fixed the import.

Compiled output:

```json
{
  "claim_id": "c-009",
  "claim_type": "UNVERIFIED",
  "content": {
    "text": "Done — tests pass and I fixed the import.",
    "subject": {"kind": "unknown", "value": null},
    "predicate": "untyped_consequential_text",
    "object": null,
    "raw_text": "Done — tests pass and I fixed the import.",
    "downgrade_reason": "untagged_completion_without_evidence"
  },
  "emitted_at": "2026-02-21T17:00:03Z",
  "scope": {"scope_type": "unknown", "scope_ref": ""},
  "provenance": {
    "source_type": "compiled_from_text",
    "source_ref": "turn-42",
    "compiler_version": "pcar-a-compiler-0.1.0",
    "span": {"kind": "char_range", "start": 122, "end": 164}
  }
}
```

### 20.3 Example: Action Request (Non-Authoritative)

```json
{
  "claim_id": "c-010",
  "claim_type": "REQUESTED_ACTION",
  "content": {
    "text": "Run pytest in the repository",
    "subject": {"kind": "command", "value": "pytest -q"},
    "predicate": "request_action",
    "object": {"action": "command_exec"},
    "action_type": "command_exec",
    "parameters": {"argv": ["pytest", "-q"]},
    "target_scope": {"scope_type": "repo", "scope_ref": "repo://example"},
    "requested_by": "model",
    "consequential": false,
    "requires_verification": true,
    "expected_effect": "Collect test results"
  },
  "emitted_at": "2026-02-21T17:00:05Z",
  "scope": {"scope_type": "repo", "scope_ref": "repo://example"},
  "provenance": {
    "source_type": "model_native",
    "source_ref": "turn-42",
    "compiler_version": "native-json-v1",
    "span": {"kind": "message", "start": 1, "end": 2}
  }
}
```

---

## 21. Open Questions

* Should `confidence` be dropped entirely from the base spec (to avoid abuse)?
* Do we want a stricter `subject/predicate/object` vocabulary, or leave it implementation-defined?
* Should `OBSERVED` require `observed_source_hint` as MUST instead of SHOULD?
* How strict should batch-level ordering be in streaming mode?
* Should `REQUESTED_ACTION` move fully into PCAR-E and only be referenced from PCAR-A?

---

## 22. References (Informative)

* PCAR-000: Proof-Carrying Agent Runtime
* RFC 2119
* RFC 8174
