# PCAR-D: Receipt Canonicalization and Provenance Contract
## Receipted Consequence for Proof-Carrying Agent Runtime

- **Status:** Draft
- **Version:** 0.1.0
- **Family:** PCAR
- **Depends on:** PCAR-000, PCAR-A, PCAR-B
- **Last Updated:** 2026-02-23
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-D defines the **Receipt** schema, **canonicalization profile**, and **provenance chain** semantics for a Proof-Carrying Agent Runtime (PCAR).

A receipt is a canonical, hashable record of a consequential decision or execution event. PCAR-D is where "we have logs" becomes "we can prove what happened." Hashes and canonicalization make it infrastructure, not process.

Every consequential event in a PCAR runtime — constraint decisions, action executions, human overrides, proof emissions — MUST produce a receipt. Receipts are emitted before or atomically with consequence. There is no silent consequence.

---

## 2. Scope

PCAR-D specifies:

- receipt schema and required fields,
- event taxonomy,
- canonical serialization profile,
- hashing profile and domain separation,
- receipt chain semantics,
- evidence store interface,
- human override receipting,
- receipt-level error semantics.

PCAR-D does **not** specify:

- claim typing (PCAR-A),
- proof generation (PCAR-B),
- constraint evaluation (PCAR-C),
- actuation contracts (PCAR-E),
- replay artifact format (PCAR-R).

---

## 3. Design Goals

### 3.1 Canonical Serialization

Receipts MUST have a single, unambiguous serialized form. Two implementations given identical receipt content MUST produce identical bytes. Without this, receipt hashing is non-portable and non-comparable.

### 3.2 Hash Integrity

Receipt hashes bind content to identity. A receipt that says "decision X was made" must be verifiable against its hash without trusting the emitter.

### 3.3 Chain Continuity

Receipts form a chain. Each receipt references the hash of its predecessor. A gap or substitution in the chain is detectable.

### 3.4 No Silent Consequence

Every consequential event — including human overrides, especially human overrides — MUST produce a receipt. Systems that "forget" to receipt overrides are not PCAR-conformant.

### 3.5 Evidence Retrievability

Receipts reference evidence by digest. The evidence MUST be retrievable by that digest, at least within the retention window.

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Receipt
A canonical, hashable record of a consequential runtime event. Receipts are the provenance substrate of PCAR.

### 5.2 Receipt Chain
An ordered sequence of receipts where each receipt references the hash of its predecessor, forming a tamper-evident log.

### 5.3 Canonical Serialization
A deterministic byte-level representation of a receipt, eliminating ambiguity from field ordering, whitespace, encoding, and null handling.

### 5.4 Evidence Store
A content-addressed storage system for raw evidence payloads referenced by receipts and proof objects.

### 5.5 Receipt Hash
The content hash of a receipt's canonical serialization. This is the receipt's identity for chain linking and cross-referencing.

### 5.6 Epoch
A bounded segment of the receipt chain, delineated by epoch markers. Epochs enable compaction, sharding, and bounded verification.

---

## 6. Processing Model (PCAR-D)

### 6.1 Receipt Emission Points

Receipts MUST be emitted at these points in the PCAR processing model:

1. **Claim batch emitted** (PCAR-A) — optional but RECOMMENDED for full traceability
2. **Proof batch produced** (PCAR-B) — optional but RECOMMENDED
3. **Constraint decision made** (PCAR-C) — REQUIRED
4. **Action executed or rejected** (PCAR-E) — REQUIRED
5. **Human override applied** — REQUIRED
6. **Error with consequential impact** — REQUIRED

### 6.2 Emission Timing

Receipts MUST be emitted **before or atomically with** the consequence they record.

If a receipt cannot be durably written before the action takes effect, the implementation MUST either:
- block the action until the receipt is durable, or
- treat the action as failed and emit a failure receipt.

Post-hoc receipt emission (action first, receipt later) violates the "no silent consequence" invariant and is NOT PCAR-D conformant.

### 6.3 Fail-Open vs Fail-Closed

If the receipt store is unavailable:
- **Strict mode:** actions MUST be blocked (fail-closed). No receipts = no actions.
- **Exploratory mode:** actions MAY proceed with a degraded-mode warning, but the receipt gap MUST be recorded when the store recovers.

The mode is determined by policy (PCAR-C), not by PCAR-D.

---

## 7. Receipt Schema (Normative)

### 7.1 Required Fields

#### `receipt_id` (string)
Content-addressed identifier for this receipt.

Requirements:
- MUST be computed as the hash of the canonical serialization of all identity-contributing fields (see Section 10.3).
- Format: `algorithm:hex_digest` (e.g., `sha256:abcdef...`)

#### `schema_version` (string)
Version of the receipt schema. Enables forward compatibility.

#### `event_type` (string)
The type of consequential event. See Section 8.

#### `actor` (object)
Who or what caused this event.

Required members:
- `actor_type` (string) — `verifier`, `constraint_engine`, `actuator`, `human`, `system`
- `actor_id` (string) — identifier for the specific actor
- `actor_version` (string, optional) — version of the actor

#### `timestamp` (string)
When the event occurred. RFC 3339, UTC.

Note: timestamp is metadata, NOT identity. The `receipt_id` is content-addressed from other fields, not from timestamp. This means identical decisions at different times produce identical receipt IDs — which is correct, because the decision content is what matters for deduplication.

#### `subject_refs` (array)
References to the subjects of this event.

Each reference MUST include:
- `ref_type` (string) — `claim`, `proof`, `decision`, `action`, `receipt`
- `ref_id` (string) — identifier of the referenced object

#### `policy_ref` (object)
Reference to the policy under which this event was evaluated.

Required members:
- `policy_id` (string)
- `policy_version` (string)
- `policy_hash` (string) — content hash of the policy

#### `evidence_hash` (string)
Content hash of the evidence bundle associated with this event.

Requirements:
- MUST be computed from the canonical serialization of all evidence inputs.
- Evidence MUST be persisted in the evidence store (Section 12).

#### `verdict` (string)
The outcome. Values are event-type-specific but MUST be machine-readable.

Common verdicts:
- For constraint decisions: `allow`, `deny`, `defer`, `reverify`, `escalate`
- For action execution: `success`, `fail`, `partial`
- For human override: `approved`, `rejected`
- For errors: `error`

#### `prev_receipt_hash` (string | null)
Hash of the previous receipt in the chain. `null` for the first receipt in a chain or epoch.

#### `receipt_hash` (string)
The content hash of this receipt's canonical serialization.

Requirements:
- Computed AFTER all other fields are set.
- MUST be the last field computed.
- MUST use the canonicalization profile in Section 10.

### 7.2 Optional Fields

#### `constraint_hash` (string)
Content hash of the constraint set that was evaluated. Present for constraint decision events.

#### `state_bindings` (array)
State references relevant to this event. Same structure as PCAR-B state bindings.

#### `rationale_codes` (array of strings)
Machine-readable codes explaining the verdict. Human text is secondary; codes are primary.

#### `metadata` (object)
Implementation-specific metadata. MUST NOT carry normative semantics absent from required fields.

#### `principal_ref` (string | null)
Hash of the authenticated principal. `null` in v2 (local-only deployment). Reserved for v3 multi-tenant support.

#### `labels` (array of strings)
Implementation-defined tags.

#### `extensions` (object)
Reserved for implementation-specific fields.

---

## 8. Event Taxonomy (Normative)

PCAR-D implementations MUST support these event types:

### 8.1 Core Events

#### `claim_emitted`
A claim batch was produced (PCAR-A). RECOMMENDED.

#### `proof_emitted`
A proof batch was produced (PCAR-B). RECOMMENDED.

#### `constraint_decided`
A constraint decision was made (PCAR-C). REQUIRED.

#### `action_executed`
An action was successfully executed (PCAR-E). REQUIRED.

#### `action_rejected`
An action was denied and not executed. REQUIRED.

#### `action_failed`
An action was attempted but failed during execution. REQUIRED.

#### `human_override`
A human overrode a constraint decision or policy. REQUIRED.

This is where systems usually "forget." PCAR-D does not forget.

#### `reverify_required`
A stale proof or state change triggered a re-verification requirement. REQUIRED.

### 8.2 Chain Management Events

#### `epoch_start`
Beginning of a new epoch in the receipt chain. REQUIRED for epoch support.

#### `epoch_end`
End of an epoch, including epoch root hash. REQUIRED for epoch support.

### 8.3 Extended Events

Implementations MAY define additional event types. Extended event types:
- MUST follow the naming pattern `ext.*` or `vendor.*`
- MUST NOT redefine core event semantics
- MUST emit receipts with the same schema

---

## 9. Human Override Receipting (Normative)

Human overrides are necessary but hazardous. They are the most important events to receipt, because they are the ones most likely to be "forgotten."

### 9.1 Override Receipt Requirements

A human override receipt MUST include:
- `event_type: "human_override"`
- `actor.actor_type: "human"`
- `actor.actor_id` — identifier of the human (name, role, or authenticated identity)
- `verdict` — what the human decided (`approved`, `rejected`)
- `rationale_codes` — at minimum, one code explaining why
- `subject_refs` — what was overridden (the original constraint decision, the action, etc.)

### 9.2 Override Scope

An override receipt MUST record the scope of the override:
- Which specific decision or policy was overridden
- Whether the override is one-time or time-bounded
- Expiry timestamp if time-bounded

### 9.3 No Blanket Overrides

An override MUST NOT apply to future decisions not yet evaluated. Each override is scoped to specific subjects. Blanket "approve everything" overrides are not PCAR-D conformant.

---

## 10. Canonicalization Profile (Normative)

This is the critical section. Without deterministic canonicalization, receipt hashing is meaningless.

### 10.1 Canonical JSON

PCAR-D uses canonical JSON as the default serialization profile.

The canonical form is:

```python
canonical_bytes = json.dumps(
    obj,
    sort_keys=True,
    separators=(',', ':'),
    ensure_ascii=True
).encode('utf-8')
```

This eliminates ambiguity from:
- **Field ordering**: sorted alphabetically by key at every nesting level.
- **Whitespace**: no whitespace between tokens (`separators=(',', ':')` ).
- **Encoding**: ASCII with Unicode escapes (`ensure_ascii=True`).

### 10.2 Additional Canonicalization Rules

#### Null handling
- `null` is explicit JSON `null`, never an absent key.
- Optional fields that are absent MUST be omitted (not set to `null`).
- Required fields that are null MUST be set to `null`.

#### Timestamp precision
- Timestamps MUST be RFC 3339 with UTC timezone (`Z` suffix).
- Precision MUST be seconds or milliseconds. No microsecond or nanosecond variance.
- Truncation to seconds is the default canonical precision.

#### Float formatting
- Floats MUST use Python `json.dumps` default formatting (no trailing zeros, no scientific notation for small integers).
- NaN and Infinity are NOT valid in canonical JSON.

#### Unicode normalization
- String values MUST be valid UTF-8 before ASCII escaping.
- Implementations SHOULD apply NFC normalization before hashing, but this is not required in v0.1.

#### Boolean formatting
- `true` and `false` in lowercase JSON. No alternatives.

### 10.3 Identity-Contributing Fields

The `receipt_id` is computed from the canonical serialization of these fields only:

- `schema_version`
- `event_type`
- `subject_refs`
- `policy_ref`
- `evidence_hash`
- `verdict`

Excluded from identity:
- `timestamp` (metadata, not identity — see Section 7.1)
- `prev_receipt_hash` (chain structure, not content identity)
- `receipt_hash` (derived from full content, not self-referential)
- `metadata`, `labels`, `extensions`

This means the same decision made at different times produces the same `receipt_id`. This is intentional for deduplication and idempotency.

### 10.4 Receipt Hash Computation

The `receipt_hash` is computed from the canonical serialization of ALL fields except `receipt_hash` itself:

```
receipt_hash = sha256(canonical_json(receipt_without_receipt_hash))
```

The `receipt_hash` includes `timestamp` and `prev_receipt_hash`, making it chain-position-specific even for identical decisions.

---

## 11. Hashing Profile (Normative)

### 11.1 Default Algorithm

SHA-256. Format: `sha256:hex_encoded_lowercase`.

### 11.2 Domain Separation

Different hash contexts use domain separation tags to prevent cross-context collision:

| Context | Domain Tag |
|---------|------------|
| Receipt identity (`receipt_id`) | `pcar-d.receipt_id\x00` |
| Receipt chain (`receipt_hash`) | `pcar-d.receipt_hash\x00` |
| Evidence bundle | `pcar-d.evidence\x00` |
| Policy hash | `pcar-d.policy\x00` |

Hash computation:
```
hash = sha256(domain_tag + canonical_bytes)
```

### 11.3 Multi-Hash Support

Implementations MAY support additional hash algorithms. If multiple algorithms are supported:
- The default (`sha256`) MUST always be present.
- Alternative hashes MUST be stored alongside, not instead of, the default.

### 11.4 Hash Portability

Receipt hashes computed by different implementations over identical canonical bytes MUST produce identical digests. This is the test of canonicalization correctness.

---

## 12. Evidence Store Interface (Normative)

### 12.1 Content-Addressed Storage

Evidence payloads MUST be stored in a content-addressed store where the retrieval key is the content hash.

### 12.2 Store Operations

Minimum required operations:
- `put(bytes) -> digest` — store evidence, return content hash
- `get(digest) -> bytes | None` — retrieve evidence by hash
- `exists(digest) -> bool` — check evidence existence

### 12.3 Integrity

The store MUST verify that retrieved content matches its address hash. A store that returns mismatched content is compromised.

### 12.4 Retention

Evidence retention is implementation-defined but MUST support:
- **Retention policies**: time-based or size-based limits
- **Hash-only retention**: after expiry, the hash remains (in receipts) but the payload is purged
- **Purge receipting**: evidence deletion MUST be recorded

### 12.5 Redaction

Evidence MAY be redacted (e.g., to remove secrets). If redacted:
- The original digest MUST be preserved in the receipt.
- The redacted payload MUST be stored under a different key.
- The receipt MUST indicate that evidence has been redacted.

---

## 13. Receipt Chain Semantics (Normative)

### 13.1 Linear Chain

The minimum chain structure is a linear chain where each receipt's `prev_receipt_hash` references the `receipt_hash` of its predecessor.

### 13.2 Chain Initialization

The first receipt in a chain (or epoch) MUST have `prev_receipt_hash: null`.

### 13.3 Chain Continuity

A receipt chain is **continuous** if, for every receipt after the first, `prev_receipt_hash` matches the `receipt_hash` of the immediately preceding receipt.

A break in continuity is a **chain break** and MUST trigger `PCAR_D_CHAIN_BREAK`.

### 13.4 Chain Verification

Given a sequence of receipts, chain integrity is verified by:
1. For each receipt, recompute `receipt_hash` from canonical serialization.
2. Verify that `prev_receipt_hash` matches the preceding receipt's computed hash.
3. Verify that `receipt_id` matches the identity hash of identity-contributing fields.

If any verification fails, the chain is compromised.

### 13.5 Epoch Boundaries

Epochs segment the chain for compaction, sharding, and bounded verification.

An epoch boundary is a pair of receipts:
- `epoch_end` receipt with an epoch root hash (Merkle root of receipt hashes in the epoch)
- `epoch_start` receipt with `prev_receipt_hash` referencing the epoch_end receipt

Epochs enable:
- independent verification of chain segments,
- parallel processing of non-overlapping epochs,
- bounded resource usage for chain verification.

### 13.6 DAG Extension (Future)

PCAR-D v0.1 specifies linear chains only. DAG-structured receipt chains (branching, merging) are deferred. Implementations MUST NOT introduce DAG semantics without a PCAR-D version bump.

---

## 14. Receipt Store Interface (Normative)

### 14.1 Append-Only

Receipt stores MUST be append-only. Receipts, once written, MUST NOT be modified or deleted (except via explicit compaction with epoch boundaries).

### 14.2 Durability

Receipts MUST be durably written before or atomically with the consequence they record (Section 6.2).

### 14.3 Query Support

Receipt stores MUST support, at minimum:
- retrieval by `receipt_id`
- retrieval by `receipt_hash`
- sequential traversal (chain order)
- filtering by `event_type`
- filtering by time range

### 14.4 Serialization Format

The default persistence format is newline-delimited JSON (NDJSON / JSONL):
- One receipt per line
- Canonical JSON serialization
- Append-only with write-ahead flushing

Implementations MAY use alternative formats (SQLite, binary log) but MUST support JSONL export for interoperability.

---

## 15. Error Model (Normative)

### 15.1 Error Object Shape

Each error MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `receipt_id` (if applicable)
- `context` (what operation was attempted)

### 15.2 Required Error Codes

#### Canonicalization
- `PCAR_D_CANONICALIZATION_FAILURE` — could not produce canonical form
- `PCAR_D_INVALID_CANONICAL_INPUT` — input contains non-serializable values (NaN, Infinity, etc.)

#### Hashing
- `PCAR_D_HASH_MISMATCH` — recomputed hash does not match stored hash
- `PCAR_D_UNSUPPORTED_HASH_ALG` — requested hash algorithm not supported

#### Chain Integrity
- `PCAR_D_CHAIN_BREAK` — `prev_receipt_hash` does not match predecessor
- `PCAR_D_DUPLICATE_RECEIPT_HASH` — hash collision or duplicate emission

#### References
- `PCAR_D_MISSING_REQUIRED_REF` — receipt lacks required subject or policy reference
- `PCAR_D_INVALID_REF` — referenced object does not exist or is malformed

#### Evidence
- `PCAR_D_EVIDENCE_STORE_UNAVAILABLE` — evidence store not writable
- `PCAR_D_EVIDENCE_INTEGRITY_FAILURE` — retrieved evidence does not match digest

#### Override
- `PCAR_D_OVERRIDE_MISSING_SCOPE` — human override lacks scope declaration
- `PCAR_D_OVERRIDE_BLANKET_REJECTED` — blanket override attempted and rejected

### 15.3 Error Handling Rules

- Receipt emission failures in strict mode MUST block the associated action.
- Receipt emission failures in exploratory mode MUST be logged and reported.
- Errors MUST NOT suppress consequence recording — if the action happened, the receipt gap MUST be backfilled.

---

## 16. Security Considerations (PCAR-D Specific)

### 16.1 Receipt Tampering

If an attacker can modify receipts after emission, the audit trail is compromised. Mitigations:
- Append-only receipt stores.
- Receipt chain with hash linking.
- Epoch root hashes for segment verification.
- Optional: cryptographic signatures on receipts (v3).

### 16.2 Evidence Store Compromise

If the evidence store is compromised, receipts reference invalid evidence. Mitigations:
- Content-addressed storage (address = hash of content).
- Integrity verification on retrieval.
- Separate write permissions for evidence store vs. actuator paths.

### 16.3 Override Laundering

Human overrides are the highest-risk event for audit evasion. Mitigations:
- Override receipts are mandatory, not optional.
- Override scope MUST be explicit and bounded.
- Blanket overrides are rejected.
- Override frequency is observable in the receipt chain.

### 16.4 Clock Manipulation

Timestamps in receipts are metadata. If an attacker manipulates the system clock, timestamps become unreliable. Mitigations:
- Receipt identity (`receipt_id`) does not depend on timestamp.
- Chain ordering is structural (`prev_receipt_hash`), not temporal.
- Implementations SHOULD detect clock skew (e.g., receipt timestamp earlier than predecessor).

---

## 17. Privacy Considerations (PCAR-D Specific)

Receipts may reference sensitive data in evidence hashes, subject references, and actor identities. Implementations SHOULD support:

- evidence redaction with hash preservation,
- actor pseudonymization in exported receipts,
- scoped access to receipt chains,
- retention policies with hash-only retention after expiry.

Privacy controls MUST NOT break chain integrity. If a receipt is redacted, the hash chain MUST remain verifiable (hash the original, redact the stored copy).

---

## 18. Conformance

An implementation is **PCAR-D conformant** if it:

1. Produces Receipts matching Section 7.
2. Supports all core event types in Section 8.1.
3. Implements the canonicalization profile in Section 10.
4. Implements the hashing profile in Section 11.
5. Maintains receipt chain integrity per Section 13.
6. Provides a content-addressed evidence store per Section 12.
7. Receipts human overrides per Section 9.
8. Emits receipts before or atomically with consequence per Section 6.2.
9. Emits machine-readable errors per Section 15.

---

## 19. Informative Examples

### 19.1 Example: Constraint Decision Receipt

```json
{
  "receipt_id": "sha256:a1b2c3...",
  "schema_version": "0.1.0",
  "event_type": "constraint_decided",
  "actor": {
    "actor_type": "constraint_engine",
    "actor_id": "governor.constraint_engine",
    "actor_version": "2.3.0"
  },
  "timestamp": "2026-02-23T15:00:00Z",
  "subject_refs": [
    {"ref_type": "claim", "ref_id": "c-010"},
    {"ref_type": "proof", "ref_id": "p-001"},
    {"ref_type": "proof", "ref_id": "p-003"}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "evidence_hash": "sha256:ev_bundle_456...",
  "verdict": "allow",
  "rationale_codes": ["proofs_complete", "freshness_valid", "scope_within_bounds"],
  "prev_receipt_hash": "sha256:prev_receipt_789...",
  "receipt_hash": "sha256:this_receipt_abc..."
}
```

### 19.2 Example: Human Override Receipt

```json
{
  "receipt_id": "sha256:override_001...",
  "schema_version": "0.1.0",
  "event_type": "human_override",
  "actor": {
    "actor_type": "human",
    "actor_id": "jbeck"
  },
  "timestamp": "2026-02-23T15:05:00Z",
  "subject_refs": [
    {"ref_type": "decision", "ref_id": "sha256:a1b2c3..."},
    {"ref_type": "action", "ref_id": "act-007"}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "evidence_hash": "sha256:override_evidence...",
  "verdict": "approved",
  "rationale_codes": ["known_safe_operation", "time_bounded"],
  "constraint_hash": "sha256:constraint_set...",
  "metadata": {
    "override_scope": "single_action",
    "override_expiry": "2026-02-23T15:10:00Z",
    "override_reason": "Deploying hotfix; tests verified manually"
  },
  "prev_receipt_hash": "sha256:prev_receipt_xyz...",
  "receipt_hash": "sha256:this_receipt_def..."
}
```

### 19.3 Example: Action Execution Receipt

```json
{
  "receipt_id": "sha256:exec_001...",
  "schema_version": "0.1.0",
  "event_type": "action_executed",
  "actor": {
    "actor_type": "actuator",
    "actor_id": "governor.file_actuator",
    "actor_version": "2.3.0"
  },
  "timestamp": "2026-02-23T15:00:01Z",
  "subject_refs": [
    {"ref_type": "action", "ref_id": "act-010"},
    {"ref_type": "decision", "ref_id": "sha256:a1b2c3..."}
  ],
  "policy_ref": {
    "policy_id": "default_strict",
    "policy_version": "1.0.0",
    "policy_hash": "sha256:policy123..."
  },
  "evidence_hash": "sha256:exec_evidence...",
  "verdict": "success",
  "state_bindings": [
    {"binding_type": "git_commit", "binding_ref": "abc123def456"}
  ],
  "prev_receipt_hash": "sha256:this_receipt_abc...",
  "receipt_hash": "sha256:this_receipt_ghi..."
}
```

---

## 20. Open Questions

- Canonical JSON vs CBOR: JSON is sufficient for v0.1, but CBOR offers binary determinism. Decision deferred.
- Receipt chain strategy: linear chain is v0.1. DAG structures (branching, merging) are desirable for concurrent workflows but add complexity.
- Should epoch root hashes be Merkle roots of receipt hashes, or of `(receipt_id, receipt_hash)` pairs?
- Should `principal_ref` become required in v3, or remain optional?
- What is the maximum receipt size before it should reference external evidence rather than embed it?

---

## 21. References (Informative)

- PCAR-000: Proof-Carrying Agent Runtime
- PCAR-A: Typed Claim Envelope
- PCAR-B: Proof Objects and Verifier Contract
- RFC 2119
- RFC 8174
- RFC 3339 (Date and Time on the Internet: Timestamps)
- RFC 8785 (JSON Canonicalization Scheme — informative comparison)
