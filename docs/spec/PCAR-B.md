# PCAR-B: Proof Objects and Verifier Contract
## Evidence Substrate for Proof-Carrying Agent Runtime

- **Status:** Draft
- **Version:** 0.1.1
- **Family:** PCAR
- **Depends on:** PCAR-000, PCAR-A
- **Last Updated:** 2026-02-23
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-B defines the **Proof Object** schema and **Verifier Contract** for a Proof-Carrying Agent Runtime (PCAR).

Where PCAR-A represents what the model *said*, PCAR-B represents what was *observed and measured*. A Proof Object is a machine-checkable evidence artifact produced by a verifier, bound to a concrete state reference and time. It is the substrate that makes "proof-carrying" literal rather than metaphorical.

PCAR-B does not determine whether an action should proceed. It produces the evidence artifacts that downstream decision layers (PCAR-C) consume.

---

## 2. Scope

PCAR-B specifies:

- proof object fields and schema,
- proof type vocabulary,
- verifier interface contract,
- freshness semantics and expiry,
- state binding requirements,
- evidence digest and integrity rules,
- INCONCLUSIVE handling,
- proof-level error semantics.

PCAR-B does **not** specify:

- claim typing or parsing (PCAR-A),
- constraint evaluation or regime derivation (PCAR-C),
- receipt canonicalization or hashing (PCAR-D),
- actuation contracts (PCAR-E),
- policy content (PCAR-C / Policy Pack).

---

## 3. Design Goals

### 3.1 Hash-Bound Evidence

Proof objects MUST bind to the raw evidence they summarize via content digests. A proof that says "tests pass" without a hashable reference to the test output is not a proof — it is an assertion.

### 3.2 State-Bound Verification

Proofs MUST reference the concrete state under which they were produced. A proof that "file X exists" without a commit hash, file digest, or snapshot ID is temporally unanchored and MUST NOT be treated as current.

### 3.3 Time-Bound Validity

Proofs have explicit freshness semantics. A proof produced 10 minutes ago may or may not be valid now. PCAR-B requires proofs to declare their temporal validity so consumers can enforce freshness mechanically.

### 3.4 Verifier Purity

Verifiers observe and measure. They MUST NOT produce side effects on actuator state. A verifier that writes files, sends messages, or modifies configuration as part of verification has crossed the trust boundary and invalidated its independence.

### 3.5 No Silent Upgrade

`INCONCLUSIVE` is not `PASS`. `FAIL` is not "try again silently." Proof statuses MUST NOT be upgraded without new evidence.

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Proof Object
A structured, machine-checkable evidence artifact produced by a verifier. A proof object binds an observation to a state reference, time, and evidence digest.

### 5.2 Verifier
A runtime component that accepts claims and/or action requests, performs observations or measurements, and emits proof objects. Verifiers are the sensor mesh of the PCAR runtime.

### 5.3 Evidence Digest
A content hash of the raw evidence payload (tool output, file content, API response, etc.) referenced by a proof object.

### 5.4 State Binding
An immutable or content-addressed reference to the system state under which a proof was produced (e.g., commit SHA, file digest, environment fingerprint, API ETag).

### 5.5 Freshness Policy
A declaration of temporal validity for a proof object. May be expressed as an absolute expiry (`valid_until`) or a policy reference defining freshness rules.

### 5.6 Proof Status
The verifier's determination: `PASS`, `FAIL`, or `INCONCLUSIVE`. These are the only valid terminal statuses.

---

## 6. Processing Model (PCAR-B)

### 6.1 Input

A verifier accepts:
- one or more Claim Envelopes (PCAR-A),
- optional action request context,
- runtime state context (commit hash, environment, tool availability),
- verifier configuration (timeout, scope, freshness policy).

### 6.2 Output

A verifier produces:
- one or more Proof Objects,
- zero or more PCAR-B errors,
- no side effects on actuator state.

### 6.3 Determinism

Given identical input claims, runtime state, and verifier configuration, a verifier SHOULD produce equivalent proof objects. Where verifiers depend on external or non-deterministic sources (network APIs, non-hermetic tools), they MUST record the non-deterministic input as evidence and note the dependency.

### 6.4 Isolation

A verifier MUST NOT:
- write to the governed filesystem (except designated temp/scratch areas),
- send messages or network requests that produce externally visible state changes,
- modify configuration, policy, or runtime state,
- invoke actuators.

Violations of verifier isolation MUST be treated as verifier compromise (Section 17.2).

---

## 7. Proof Object Schema (Normative)

A Proof Object is a structured record with the following fields.

### 7.1 Required Fields

#### `proof_id` (string)
A unique identifier for this proof object.

Requirements:
- MUST be unique within the current run/session scope.
- SHOULD be content-independent (UUID or similar).
- If content-addressed proof IDs are used, they MUST be computed after full normalization.

#### `proof_type` (string)
See Section 8. Namespaced to allow extension.

#### `status` (enum)
The verifier's determination.

Required values:
- `PASS` — evidence supports the claimed proposition.
- `FAIL` — evidence contradicts the claimed proposition.
- `INCONCLUSIVE` — evidence is insufficient to determine truth.

No other terminal status values are permitted. Implementations MAY add transient/internal states but MUST resolve to one of these three for any persisted or transmitted proof.

#### `verifier_id` (string)
Stable identifier for the verifier that produced this proof.

Requirements:
- MUST be machine-readable and stable across invocations.
- SHOULD include enough information for allowlist/denylist matching.

#### `verifier_version` (string)
Version of the verifier implementation. Semver or commit-ish.

#### `subject` (object)
What was verified. Describes the target of the verification in structured form.

Required members:
- `kind` (string) — e.g. `file`, `command`, `api_response`, `schema`, `state`, `assertion`
- `ref` (string) — specific reference (path, command string, URL, claim_id)

Optional members:
- `claim_ids` (array of strings) — claim envelope IDs this proof addresses
- `description` (string) — human-readable summary

#### `evidence_digest` (string)
Content hash of the raw evidence payload.

Requirements:
- MUST use the format `algorithm:hex_digest` (e.g., `sha256:abcdef...`).
- MUST hash the raw evidence bytes, not a summary or interpretation.
- The raw evidence SHOULD be persisted in an evidence store (PCAR-D) and retrievable by digest.

#### `state_binding` (object)
Immutable reference to the system state under which this proof was produced.

Required members:
- `binding_type` (string) — e.g. `git_commit`, `file_digest`, `env_fingerprint`, `api_etag`, `snapshot_id`
- `binding_ref` (string) — the actual reference value

Optional members:
- `binding_digest` (string) — content hash of the bound state, if applicable
- `scope` (object) — scope of the binding (repo, host, service, etc.)

Mutable-only references (e.g., "latest" branch, floating tags) are NOT valid state bindings and MUST be rejected or resolved to immutable form.

#### `observed_at` (timestamp)
When the observation was made. RFC 3339 with explicit timezone or UTC `Z`.

#### `freshness` (object)
Temporal validity declaration.

Required members (at least one):
- `valid_until` (timestamp) — absolute expiry
- `freshness_policy_ref` (string) — reference to a named freshness policy

Optional members:
- `max_age_seconds` (integer) — maximum age before re-verification required
- `invalidation_triggers` (array of strings) — events that invalidate this proof early (e.g., `state_binding_changed`, `file_modified`, `commit_advanced`)

If no freshness information is provided, the proof MUST be treated as immediately stale by consumers.

### 7.2 Optional Fields

#### `payload_ref` (string)
Reference to the full evidence payload in an evidence store (PCAR-D). May be a content-addressed blob ID.

#### `metadata` (object)
Implementation-specific metadata. MUST NOT carry normative semantics that are absent from required fields.

#### `confidence` (number)
Verifier's confidence in the determination, `[0.0, 1.0]`. Non-authoritative metadata — implementations MUST NOT use confidence as a substitute for `status`.

#### `error_refs` (array of strings)
References to PCAR-B errors encountered during verification that may affect proof quality.

#### `labels` (array of strings)
Implementation-defined tags for routing, analysis, or observability.

#### `extensions` (object)
Reserved for implementation-specific fields. Implementations MUST NOT place normative semantics exclusively in `extensions`.

---

## 8. Proof Types (Normative)

Proof types use namespaced identifiers: `namespace.type_name`.

### 8.1 Core Namespace (`core.*`)

Implementations MUST support these proof types:

#### `core.TOOL_RESULT`
Result of a tool invocation (shell command, API call, etc.).

Required evidence: raw tool output (stdout, stderr, exit code, response body).

#### `core.STATE_SNAPSHOT`
Observation of system state at a point in time.

Required evidence: state content or digest (file content, directory listing, environment dump).

#### `core.TEST_RESULT`
Parsed result of a test execution.

Required evidence: test runner output (raw log, JUnit XML, or equivalent structured format).

#### `core.SCHEMA_VALIDATION`
Result of validating data against a schema.

Required evidence: validation output (errors, warnings, schema reference).

#### `core.PARSE_RESULT`
Result of parsing structured data.

Required evidence: parse output or error details.

#### `core.FRESHNESS_CHECK`
Verification that a prior proof or state binding is still current.

Required evidence: comparison result (current state digest vs bound state digest).

#### `core.CONSISTENCY_CHECK`
Verification of internal consistency across multiple claims or proofs.

Required evidence: comparison details, contradiction list.

### 8.2 Extended Namespace (`ext.*`)

Implementations MAY define additional proof types in the `ext.*` namespace:

- `ext.CITATION_BINDING` — verification of external source references (DOI, URL, etc.)
- `ext.POLICY_CHECK` — verification of policy compliance (may overlap with PCAR-C)
- `ext.SIGNATURE_VERIFICATION` — cryptographic signature validation
- `ext.ATTESTATION` — external attestation or certificate verification

### 8.3 Namespace Rules

- Core types (`core.*`) are defined by this specification and MUST NOT be redefined.
- Extended types (`ext.*`) are implementation-defined.
- Vendor-specific types SHOULD use a vendor namespace (e.g., `vendor_name.*`).
- Unknown proof types MUST be treated as opaque by generic consumers but MUST NOT be silently dropped.

---

## 9. Freshness Semantics (Normative)

Freshness is a first-class governance variable in PCAR. Proofs are not eternally valid.

### 9.1 Explicit Freshness Required

Every proof object MUST include freshness information (Section 7.1, `freshness` field). If freshness is absent, consumers MUST treat the proof as immediately stale.

### 9.2 Expiry Evaluation

A proof is **fresh** if and only if:
1. `valid_until` has not passed (if specified), AND
2. `max_age_seconds` has not elapsed since `observed_at` (if specified), AND
3. no `invalidation_triggers` have fired (if specified).

If any condition fails, the proof is **stale**.

### 9.3 Stale Proof Handling

A stale proof:
- MUST NOT be used as sufficient evidence for an `ALLOW` decision (PCAR-C).
- MAY be used as advisory context.
- SHOULD trigger a `REVERIFY` decision (PCAR-C) if the associated action is still pending.

### 9.4 State-Drift Invalidation

If the state binding referenced by a proof changes (e.g., a new commit is made, a file is modified), the proof MUST be considered stale regardless of time-based freshness.

Implementations SHOULD support state-drift detection via:
- file watcher / inotify,
- commit hash comparison,
- ETag / version comparison.

### 9.5 Freshness Policy References

Named freshness policies allow consistent freshness rules across proof types.

A freshness policy MUST define:
- `policy_id` (string)
- `max_age_seconds` (integer)
- `invalidation_triggers` (array of strings)
- `revalidation_strategy` (string) — e.g., `auto`, `manual`, `on_access`

---

## 10. State Binding Semantics (Normative)

### 10.1 Valid State Bindings

A state binding is valid if it references an immutable or content-addressed state. Valid examples:

| Binding Type | Example | Immutability |
|-------------|---------|--------------|
| `git_commit` | `abc123def` | Immutable (content-addressed) |
| `file_digest` | `sha256:...` | Immutable (content-addressed) |
| `env_fingerprint` | `sha256:...` | Snapshot (immutable at observation time) |
| `api_etag` | `"33a64df5"` | Version-specific |
| `snapshot_id` | `snap-2026-02-23-001` | Immutable by convention |

### 10.2 Invalid State Bindings

The following are NOT valid state bindings and MUST be rejected or resolved:

- Branch names without commit SHA (`main`, `develop`)
- Floating tags (`latest`, `stable`)
- Mutable URLs without versioning or ETag
- Relative timestamps ("5 minutes ago")
- Process IDs or session IDs (ephemeral)

### 10.3 Resolution

If a verifier receives a mutable reference, it MUST resolve it to an immutable binding before emitting the proof. The resolution MUST be recorded:

```
state_binding: {
  binding_type: "git_commit",
  binding_ref: "abc123def",           // resolved immutable
  binding_digest: "sha256:...",
  resolved_from: "refs/heads/main"    // original mutable ref
}
```

### 10.4 Compound State Bindings

Some verifications span multiple state references (e.g., a diff between two commits, a comparison across files). Compound bindings MUST list all referenced states:

```
state_binding: {
  binding_type: "compound",
  bindings: [
    {binding_type: "git_commit", binding_ref: "abc123"},
    {binding_type: "git_commit", binding_ref: "def456"}
  ]
}
```

---

## 11. Evidence Integrity (Normative)

### 11.1 Digest Computation

Evidence digests MUST be computed as:
1. Hash the raw evidence bytes (not a summary, interpretation, or formatted view).
2. Use SHA-256 as the default algorithm.
3. Format as `sha256:hex_encoded_digest`.

### 11.2 Multi-Hash Support

Implementations MAY support additional hash algorithms. If multiple algorithms are supported, the proof object SHOULD include a `digest_algorithm` field. Note: this field is technically redundant with the `algorithm:hex_digest` format in `evidence_digest` (§7.1), but is retained for cases where implementations need a separate parseable field. If they disagree, `evidence_digest` is authoritative.

The default (`sha256`) MUST always be supported.

### 11.3 Domain Separation

When hashing evidence for different purposes (proof digest vs receipt hash vs blob storage), implementations SHOULD use domain separation tags:

```
proof_evidence_digest = sha256("pcar-b.evidence\x00" + raw_bytes)
```

This prevents cross-context hash collision.

### 11.4 Evidence Availability

The raw evidence referenced by `evidence_digest` SHOULD be persisted in an evidence store (defined in PCAR-D) and retrievable by digest.

If evidence is unavailable at decision time:
- The proof MUST be treated as degraded.
- Constraint evaluation (PCAR-C) MUST be informed of the degradation.
- A `PCAR_B_EVIDENCE_UNAVAILABLE` error SHOULD be emitted.

---

## 12. INCONCLUSIVE Handling (Normative)

`INCONCLUSIVE` is a legitimate proof status that represents genuine epistemic uncertainty. It is not an error, a timeout, or a soft pass.

### 12.1 INCONCLUSIVE Cannot Be Upgraded

An `INCONCLUSIVE` proof MUST NOT be:
- silently upgraded to `PASS`,
- treated as `PASS` by downstream consumers,
- ignored in proof set evaluation,
- retried without new evidence until it becomes `PASS`.

### 12.2 INCONCLUSIVE in Decision Context

When PCAR-C evaluates a proof set containing `INCONCLUSIVE` proofs:
- The decision engine MUST account for the uncertainty.
- Policy MAY define `INCONCLUSIVE` handling per action type (e.g., treat as `FAIL` for writes, treat as `DEFER` for reads).
- The default handling SHOULD be `DEFER` or `REVERIFY`.

### 12.3 When to Emit INCONCLUSIVE

Verifiers SHOULD emit `INCONCLUSIVE` when:
- evidence is partial or degraded,
- external sources are unavailable or timing out,
- tool output is ambiguous (mixed pass/fail signals),
- state binding is valid but evidence quality is below confidence threshold.

Verifiers MUST NOT emit `INCONCLUSIVE` as a default/fallback to avoid committing to `FAIL`. If evidence clearly contradicts the claim, the status MUST be `FAIL`.

---

## 13. Verifier Contract (Normative)

### 13.1 Interface

A PCAR-B conformant verifier MUST implement:

```
verify(
    claims: list[ClaimEnvelope],      // PCAR-A claims to verify
    context: VerifierContext,          // runtime state, scope, config
) -> VerifierResult
```

Where `VerifierResult` contains:
- `proofs: list[ProofObject]`
- `errors: list[PCARBError]`

### 13.2 Verifier Identity

Every verifier MUST declare:
- `verifier_id` — stable, machine-readable identifier
- `verifier_version` — version of the implementation
- `supported_proof_types` — list of proof types this verifier can produce
- `supported_claim_types` — list of claim types this verifier can process

### 13.3 Verifier Registration

Implementations SHOULD maintain a verifier registry that maps claim types and action types to appropriate verifiers.

### 13.4 Verifier Allowlists

Policy SHOULD support verifier allowlists and version pinning:
- Only approved verifiers may produce proofs for high-stakes actions.
- Version pinning prevents silent verifier upgrades from changing verification semantics.

### 13.5 Verifier Timeout

Verifier invocations MUST have a bounded timeout. If a verifier does not complete within the timeout:
- It MUST emit a `PCAR_B_VERIFIER_TIMEOUT` error.
- It MAY emit an `INCONCLUSIVE` proof with the error reference.
- It MUST NOT silently drop the verification request.

### 13.6 Verifier Composition

A verifier MAY delegate to sub-verifiers. When it does:
- The parent verifier is responsible for the composite proof.
- Sub-verifier identities SHOULD be recorded in proof metadata.
- Sub-verifier isolation requirements apply transitively.

---

## 14. Proof Batches and Ordering

### 14.1 Batch Structure

Verifiers output proofs as ordered batches.

A proof batch MUST include:
- `batch_id`
- `produced_at`
- `proofs` (ordered array)
- `verifier_id`
- `verifier_version`
- `claim_refs` (claim IDs that triggered this verification)

### 14.2 Order Semantics

Proof order within a batch SHOULD reflect the order of verification (first verified = first in array).

### 14.3 Streaming Verification

Streaming verifiers MAY emit proofs incrementally. If so:
- Each partial batch MUST include a stable `batch_id` and monotonic `sequence_no`.
- A finalization signal (`is_final = true`) MUST be emitted.
- Proof statuses MUST NOT change after emission; corrections require new proofs with explicit references.

---

## 15. Error Model (Normative)

PCAR-B errors MUST be machine-readable. Errors SHOULD be emitted alongside proof batches.

### 15.1 Error Object Shape

Each error MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `verifier_id`
- `claim_refs` (if applicable)
- `proof_id` (if applicable)

### 15.2 Required Error Codes

#### Verifier Execution
- `PCAR_B_VERIFIER_TIMEOUT` — verifier exceeded time limit
- `PCAR_B_VERIFIER_CRASH` — verifier terminated unexpectedly
- `PCAR_B_VERIFIER_UNAVAILABLE` — requested verifier not found or not registered

#### Evidence Integrity
- `PCAR_B_EVIDENCE_DIGEST_FAILURE` — could not compute evidence digest
- `PCAR_B_EVIDENCE_UNAVAILABLE` — raw evidence not retrievable
- `PCAR_B_EVIDENCE_CORRUPTED` — evidence fails integrity check

#### State Binding
- `PCAR_B_MISSING_STATE_BINDING` — proof lacks required state binding
- `PCAR_B_INVALID_STATE_BINDING` — state binding is mutable or unresolvable
- `PCAR_B_STATE_BINDING_STALE` — bound state has changed since observation

#### Freshness
- `PCAR_B_FRESHNESS_UNDEFINED` — proof lacks freshness information
- `PCAR_B_FRESHNESS_EXPIRED` — proof has exceeded its validity window

#### Proof Type
- `PCAR_B_UNSUPPORTED_PROOF_TYPE` — verifier cannot produce requested proof type
- `PCAR_B_PROOF_TYPE_MISMATCH` — proof type does not match claim requirements

#### Status Integrity
- `PCAR_B_INCONCLUSIVE_UPGRADE_ATTEMPT` — attempt to treat INCONCLUSIVE as PASS
- `PCAR_B_STATUS_MUTATION_ATTEMPT` — attempt to change a persisted proof status

### 15.3 Error Handling Rules

- Verifier errors MUST NOT suppress proof emission. If partial verification succeeded, emit what was produced plus the error.
- Errors MUST NOT be treated as proof.
- A verifier that produces only errors and no proofs is not a verification — the claims remain unverified.

---

## 16. Canonicalization (PCAR-B Profile)

### 16.1 Proof Object Normalization

Before persistence or transmission, a Proof Object MUST be normalized for:
- field name casing (lower_snake_case)
- timestamp format (RFC 3339, UTC)
- digest format (`algorithm:hex_digest`, lowercase)
- null/omitted handling (implementation-defined but deterministic)

### 16.2 Canonical Serialization

If proof objects are hashed directly (outside PCAR-D receipts), the implementation MUST use the PCAR-D canonical JSON profile (PCAR-D §10.1):

```
json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=True)
```

This is the single canonical serialization profile for the entire PCAR family. Do not define a separate profile per spec.

### 16.3 Proof Identity

Proof objects are identified by `proof_id`, not by content hash. Content hashing of proofs is a PCAR-D concern (receipt integrity).

---

## 17. Security Considerations (PCAR-B Specific)

### 17.1 Evidence Forgery

If an attacker can inject false evidence into the evidence store, they can produce proofs that appear valid. Mitigations:
- Evidence digests MUST be computed by the verifier, not supplied by the proposer.
- Evidence stores SHOULD be append-only with integrity protection.
- Verifiers SHOULD verify evidence they retrieve, not trust stored digests blindly.

### 17.2 Verifier Compromise

A compromised verifier can emit false `PASS` proofs. Mitigations:
- Verifier identity and version are recorded in every proof.
- Policy SHOULD support verifier allowlists.
- High-stakes actions SHOULD require proofs from multiple independent verifiers.
- Verifier isolation violations (Section 6.4) are a compromise indicator.

### 17.3 State Binding Manipulation

If state bindings reference mutable state, an attacker can change the state after proof emission. Mitigations:
- State bindings MUST be immutable or content-addressed (Section 10).
- State-drift invalidation SHOULD be active (Section 9.4).
- Compound bindings MUST include all referenced states.

### 17.4 Freshness Attacks

Stale proofs may be replayed to authorize actions on changed state. Mitigations:
- Freshness is mandatory (Section 9.1).
- Stale proofs cannot authorize actions (Section 9.3).
- State-drift invalidation supplements time-based freshness.

### 17.5 INCONCLUSIVE Laundering

An attacker may try to force `INCONCLUSIVE` results and rely on permissive fallback handling. Mitigations:
- Default INCONCLUSIVE handling SHOULD be `DEFER` or `REVERIFY`, not `ALLOW`.
- Policy MUST define explicit INCONCLUSIVE handling per action type.
- Repeated INCONCLUSIVE results SHOULD trigger escalation.

---

## 18. Privacy Considerations (PCAR-B Specific)

Evidence payloads may contain sensitive data (secrets, PII, proprietary code). Implementations SHOULD support:

- evidence redaction with digest preservation (hash the original, store the redacted),
- scoped access to evidence stores,
- retention policies on evidence payloads (with hash-only retention after expiry),
- verifier output filtering (exclude sensitive fields from proof metadata).

Redaction MUST NOT break evidence digest integrity. If a payload is redacted after hashing, the digest remains valid but the payload is no longer retrievable. This degradation MUST be explicitly marked.

---

## 19. Conformance

An implementation is **PCAR-B conformant** if it:

1. Produces Proof Objects matching Section 7.
2. Supports all core proof types in Section 8.1.
3. Enforces freshness semantics per Section 9.
4. Enforces state binding requirements per Section 10.
5. Computes evidence digests per Section 11.
6. Handles INCONCLUSIVE correctly per Section 12.
7. Implements the verifier contract per Section 13.
8. Emits machine-readable errors per Section 15.
9. Maintains verifier isolation per Section 6.4.

---

## 20. Informative Examples

### 20.1 Example: Test Result Proof

```json
{
  "proof_id": "p-001",
  "proof_type": "core.TEST_RESULT",
  "status": "PASS",
  "verifier_id": "governor.command_verifier",
  "verifier_version": "2.3.0",
  "subject": {
    "kind": "command",
    "ref": "pytest -q tests/",
    "claim_ids": ["c-001"]
  },
  "evidence_digest": "sha256:a1b2c3d4e5f6...",
  "state_binding": {
    "binding_type": "git_commit",
    "binding_ref": "abc123def456",
    "scope": {"scope_type": "repo", "scope_ref": "repo://agent_gov"}
  },
  "observed_at": "2026-02-23T14:30:00Z",
  "freshness": {
    "valid_until": "2026-02-23T14:45:00Z",
    "max_age_seconds": 900,
    "invalidation_triggers": ["state_binding_changed"]
  },
  "payload_ref": "blob:sha256:a1b2c3d4e5f6..."
}
```

### 20.2 Example: INCONCLUSIVE Proof (Partial Evidence)

```json
{
  "proof_id": "p-002",
  "proof_type": "core.CONSISTENCY_CHECK",
  "status": "INCONCLUSIVE",
  "verifier_id": "governor.consistency_verifier",
  "verifier_version": "2.3.0",
  "subject": {
    "kind": "assertion",
    "ref": "claim that API schema is backward-compatible",
    "claim_ids": ["c-005"]
  },
  "evidence_digest": "sha256:f7e8d9c0b1a2...",
  "state_binding": {
    "binding_type": "compound",
    "bindings": [
      {"binding_type": "file_digest", "binding_ref": "sha256:111..."},
      {"binding_type": "file_digest", "binding_ref": "sha256:222..."}
    ]
  },
  "observed_at": "2026-02-23T14:31:00Z",
  "freshness": {
    "freshness_policy_ref": "default_short_lived",
    "max_age_seconds": 300
  },
  "confidence": 0.4,
  "error_refs": ["PCAR_B_EVIDENCE_UNAVAILABLE"],
  "metadata": {
    "reason": "Schema diff tool returned partial results; 2 of 5 endpoints not reachable"
  }
}
```

### 20.3 Example: State Snapshot with Resolved Binding

```json
{
  "proof_id": "p-003",
  "proof_type": "core.STATE_SNAPSHOT",
  "status": "PASS",
  "verifier_id": "governor.file_verifier",
  "verifier_version": "2.3.0",
  "subject": {
    "kind": "file",
    "ref": "src/governor/daemon.py",
    "claim_ids": ["c-003"]
  },
  "evidence_digest": "sha256:deadbeef1234...",
  "state_binding": {
    "binding_type": "file_digest",
    "binding_ref": "sha256:deadbeef1234...",
    "resolved_from": "src/governor/daemon.py"
  },
  "observed_at": "2026-02-23T14:32:00Z",
  "freshness": {
    "freshness_policy_ref": "default_volatile",
    "max_age_seconds": 60,
    "invalidation_triggers": ["file_modified"]
  }
}
```

---

## 21. Open Questions

- Should `confidence` be promoted to a required field, or remain optional metadata?
- Should compound state bindings have a composite digest, or is the list of sub-bindings sufficient?
- How should verifier delegation be represented for audit — flat list in metadata, or structured sub-proof references?
- Should proof types include a `required_evidence_shape` declaration for schema validation of evidence payloads?
- What is the maximum acceptable verifier timeout before the system degrades to `INCONCLUSIVE` by default?

---

## 22. Changelog

### 0.1.1
Spec editor fixes; no architectural changes.
- Examples 20.2 and 20.3: added `freshness_policy_ref` to comply with §7.1 freshness schema (requires at least one of `valid_until` or `freshness_policy_ref`).
- §11.2: noted `digest_algorithm` redundancy with `algorithm:hex_digest` format; `evidence_digest` is authoritative.
- §16.2: canonical serialization now explicitly references PCAR-D §10.1 as the single family-wide profile.

---

## 23. References (Informative)

- PCAR-000: Proof-Carrying Agent Runtime
- PCAR-A: Typed Claim Envelope
- RFC 2119
- RFC 8174
- RFC 3339 (Date and Time on the Internet: Timestamps)
