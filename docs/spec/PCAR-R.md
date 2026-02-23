# PCAR-R: Replay Artifact and Differential Replay
## Replayable Governance for Proof-Carrying Agent Runtime

- **Status:** Draft
- **Version:** 0.1.0
- **Family:** PCAR
- **Depends on:** PCAR-000, PCAR-A, PCAR-B, PCAR-C, PCAR-D, PCAR-E
- **Last Updated:** 2026-02-23
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-R defines the **Replay Artifact** format and **Differential Replay** semantics for a Proof-Carrying Agent Runtime (PCAR).

A replay artifact is a self-contained bundle that preserves enough structure to reconstruct the decision path of a governed run. PCAR-R is the difference between "we have logs" and "we can prove what happened, and test whether policy X would have prevented it."

Replay is the audit primitive. Without it, governance is assertion. With it, governance is verifiable.

PCAR-R is RECOMMENDED, not REQUIRED, for base PCAR conformance. However, any system that claims auditability without replay support is overstating its capabilities.

---

## 2. Scope

PCAR-R specifies:

- replay bundle format and manifest,
- replay modes (exact, policy-diff, verifier-diff, counterfactual),
- determinism semantics and divergence handling,
- artifact integrity requirements,
- redaction-compatible replay,
- replay-level error semantics.

PCAR-R does **not** specify:

- claim typing (PCAR-A),
- proof generation (PCAR-B),
- constraint evaluation (PCAR-C),
- receipt canonicalization (PCAR-D),
- actuation contracts (PCAR-E).

PCAR-R consumes all of A through E. It is the capstone that makes the family auditable.

---

## 3. Design Goals

### 3.1 Decision Path Reconstruction

A replay artifact MUST preserve enough information to reconstruct the sequence of claims, proofs, decisions, and actions that occurred during a governed run.

### 3.2 Differential Analysis

Replay MUST support "what if" analysis: what would have happened under a different policy, a different verifier version, or a different set of claims?

### 3.3 Integrity Verification

Replay artifacts MUST be verifiable against their manifest. A tampered artifact MUST be detectable.

### 3.4 Graceful Degradation

Missing evidence (due to redaction, retention expiry, or corruption) MUST be handled explicitly. Silent gaps are worse than declared gaps.

### 3.5 Redaction Compatibility

Replay MUST remain useful even when evidence payloads have been redacted. Hash integrity is preserved; payload availability is not guaranteed.

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Replay Artifact
A self-contained bundle of governance artifacts sufficient to reconstruct the decision path of a governed run.

### 5.2 Replay Bundle
The container format for a replay artifact, including manifest and all referenced objects.

### 5.3 Replay Mode
The type of replay analysis being performed: exact, policy-diff, verifier-diff, or counterfactual.

### 5.4 Divergence Point
A point in the replay where the replayed outcome differs from the original. Divergence points are the primary output of differential replay.

### 5.5 Governed Run
A bounded sequence of governance events (claims, proofs, decisions, actions) that forms a coherent unit for replay purposes.

---

## 6. Replay Bundle Format (Normative)

### 6.1 Bundle Structure

A replay bundle is a directory or archive containing:

```
replay-bundle/
├── manifest.json           # Bundle manifest (Section 6.2)
├── claims/                 # PCAR-A claim batches
│   ├── batch-001.json
│   └── batch-002.json
├── proofs/                 # PCAR-B proof batches
│   ├── batch-001.json
│   └── batch-002.json
├── decisions/              # PCAR-C constraint decisions
│   ├── d-001.json
│   └── d-002.json
├── receipts/               # PCAR-D receipt chain
│   └── receipts.jsonl
├── actions/                # PCAR-E action contracts and results
│   ├── act-001.json
│   └── act-001-result.json
├── evidence/               # Evidence store (content-addressed)
│   ├── a1/
│   │   └── a1b2c3d4...
│   └── de/
│       └── deadbeef...
├── policy/                 # Policy pack snapshots
│   └── default_strict-1.0.0.json
└── runtime/                # Runtime metadata
    ├── verifier-versions.json
    ├── runtime-config.json
    └── environment.json
```

### 6.2 Manifest Schema

The manifest is the entry point. It describes the bundle contents and enables integrity verification.

Required fields:

#### `manifest_version` (string)
Version of the manifest schema.

#### `bundle_id` (string)
Unique identifier for this replay bundle.

#### `run_id` (string)
Identifier of the governed run this bundle represents.

#### `created_at` (timestamp)
When the bundle was created. RFC 3339, UTC.

#### `manifest_hash` (string)
Content hash of the manifest (excluding this field). Computed last.

#### `artifacts` (object)
Inventory of all artifacts in the bundle.

Required members:
- `claim_batches` (array) — list of `{batch_id, path, hash}`
- `proof_batches` (array) — list of `{batch_id, path, hash}`
- `decisions` (array) — list of `{decision_id, path, hash}`
- `receipt_chain` (object) — `{path, hash, count, first_hash, last_hash}`
- `action_contracts` (array) — list of `{action_request_id, path, hash}`
- `action_results` (array) — list of `{action_request_id, path, hash}`
- `evidence_blobs` (array) — list of `{digest, path, available}` (`available` may be `false` if redacted)
- `policy_packs` (array) — list of `{policy_id, policy_version, path, hash}`

#### `verifier_versions` (object)
Map of `verifier_id` → `verifier_version` for all verifiers active during the run.

#### `runtime_metadata` (object)
Runtime environment information relevant to replay.

Required members:
- `governor_version` (string)
- `platform` (string)
- `start_time` (timestamp)
- `end_time` (timestamp)

Optional members:
- `environment_hash` (string) — hash of relevant environment state
- `config_hash` (string) — hash of runtime configuration

#### `integrity` (object)
Bundle-level integrity information.

Required members:
- `artifact_count` (integer) — total number of artifacts
- `evidence_available_count` (integer) — evidence blobs actually present
- `evidence_redacted_count` (integer) — evidence blobs redacted (hash preserved, payload absent)
- `chain_continuous` (boolean) — receipt chain integrity verified at bundle creation
- `epoch_roots` (array) — epoch root hashes, if epochs are present

### 6.3 Artifact References

All references within the bundle (claim → proof, decision → proof, receipt → evidence) MUST use the same IDs as the original run. The bundle is a snapshot, not a re-keyed copy.

---

## 7. Replay Modes (Normative)

### 7.1 EXACT Replay

Reconstruct the original decision path and verify consistency.

Purpose:
- Verify that the receipt chain matches the actual artifacts.
- Detect tampering or corruption.
- Confirm that the declared decisions are consistent with the declared proofs and policy.

Process:
1. Load the policy pack from the bundle.
2. For each claim batch, re-evaluate through the constraint engine with the original proofs.
3. Compare replayed decisions against original decisions.
4. Divergence = audit finding.

Requirements:
- All non-redacted artifacts MUST be present.
- Deterministic components MUST produce identical results.
- Non-deterministic components (external tool outputs) are compared by digest, not re-executed.

### 7.2 DIFF_POLICY Replay

Re-evaluate the run under a different policy pack.

Purpose:
- Test whether a policy change would have caught a missed issue.
- Validate policy updates before deployment.
- Compare strictness between policy versions.

Process:
1. Load the alternative policy pack.
2. For each claim batch, re-evaluate through the constraint engine with the original proofs but the new policy.
3. Record divergence points (decisions that differ from the original).

Output:
- List of divergence points: `{claim_id, original_decision, replayed_decision, rationale_diff}`
- Summary statistics: decisions changed, new denials, new allows, regime differences.

### 7.3 DIFF_VERIFIER Replay

Re-evaluate the run with different verifier versions.

Purpose:
- Test whether a verifier update changes proof outcomes.
- Validate verifier upgrades before deployment.

Process:
1. For each claim batch, re-verify with the alternative verifier.
2. New proofs may differ from originals.
3. Re-evaluate decisions with the new proof set.
4. Record divergence points.

Requirements:
- Raw evidence MUST be available (not redacted) for re-verification.
- If evidence is redacted, the verification step is skipped and marked as `PCAR_R_REDACTION_BREAKS_REPLAY`.

### 7.4 COUNTERFACTUAL Replay

Re-evaluate the run with modified claims.

Purpose:
- Test "what if the model had said X instead of Y?"
- Explore alternative decision paths.
- Training and educational use.

Process:
1. Load modified claim batches (user-supplied).
2. Run through verification and constraint evaluation.
3. Record the complete alternative decision path.

Requirements:
- Modified claims MUST be valid PCAR-A envelopes.
- Counterfactual replay MUST be clearly labeled — it is not an audit of the original run.

---

## 8. Determinism Semantics (Normative)

### 8.1 Deterministic Components

The following components MUST replay exactly given identical inputs:
- Claim compilers (PCAR-A) — same input → same claim envelopes
- Constraint engines (PCAR-C) — same claims + proofs + policy → same decisions
- Receipt hashing (PCAR-D) — same receipt content → same hash

### 8.2 Non-Deterministic Components

The following components may produce different results on replay:
- External tool execution (command output, API responses)
- Network-dependent verifiers
- Time-dependent operations

Non-deterministic components are handled by:
- **EXACT mode**: compare by stored digest, do not re-execute.
- **DIFF modes**: flag non-deterministic components and note that divergence may be from the component, not from the changed variable.

### 8.3 Divergence Recording

Every divergence point MUST include:
- `divergence_id` (string)
- `artifact_type` (string) — `claim`, `proof`, `decision`, `action_result`
- `artifact_id` (string) — ID of the diverging artifact
- `original_digest` (string) — hash of the original artifact
- `replayed_digest` (string) — hash of the replayed artifact
- `divergence_kind` (string) — `deterministic` (unexpected) or `nondeterministic` (expected)
- `details` (object) — implementation-specific details (field-level diff, etc.)

---

## 9. Artifact Integrity (Normative)

### 9.1 Manifest Verification

Bundle integrity is verified by:
1. Recompute the `manifest_hash` (excluding the field itself).
2. For each artifact listed in `artifacts`, verify that the file exists at the declared path and matches the declared hash.
3. Verify receipt chain continuity.
4. Verify epoch roots (if present) against the receipt hashes in their range.

### 9.2 Missing Artifact Handling

If an artifact referenced in the manifest is not present in the bundle:

| Mode | Handling |
|------|----------|
| `hard_fail` | Replay aborts. Missing artifacts are fatal. |
| `partial_replay` | Replay continues with a gap. Missing artifacts are logged and the gap is reported. |
| `skip_and_warn` | Missing artifacts are skipped with warnings. Replay results are degraded. |

The default SHOULD be `partial_replay`. The mode is declared in the replay request.

### 9.3 Evidence vs Non-Evidence Artifacts

- **Non-evidence artifacts** (claims, decisions, receipts, policy): MUST be present for any replay mode. Absence is always a defect.
- **Evidence artifacts** (raw evidence blobs): MAY be absent due to redaction or retention expiry. Absence is expected and handled per Section 10.

---

## 10. Redaction-Compatible Replay (Normative)

### 10.1 Redaction Model

Evidence payloads may be redacted (removed) while preserving their digest in receipts and proof objects. This allows:
- Privacy compliance (remove PII, secrets).
- Size reduction (evidence may be large).
- Partial archiving (keep digests for integrity, discard payloads).

### 10.2 Impact on Replay Modes

| Mode | Redaction Impact |
|------|-----------------|
| EXACT | Digest comparison still works. Payload inspection is degraded. |
| DIFF_POLICY | Fully functional (only needs decisions + proofs, not raw evidence). |
| DIFF_VERIFIER | Degraded — cannot re-verify without raw evidence. MUST emit `PCAR_R_REDACTION_BREAKS_REPLAY`. |
| COUNTERFACTUAL | Partially degraded — new claims can be evaluated, but re-verification of modified claims requires evidence. |

### 10.3 Redaction Metadata

Redacted evidence MUST be marked in the manifest:

```json
{
  "digest": "sha256:original_evidence_hash...",
  "path": "evidence/a1/a1b2c3d4...",
  "available": false,
  "redacted_at": "2026-03-01T00:00:00Z",
  "redaction_reason": "retention_policy"
}
```

### 10.4 Replay Degradation Reporting

When replay is degraded by redaction or missing artifacts, the replay result MUST include:
- `degradation_level` (string) — `none`, `minor`, `significant`, `severe`
- `unavailable_artifacts` (array) — list of missing/redacted artifact digests
- `affected_replay_steps` (array) — which replay steps were impacted
- `confidence_reduction` (string) — qualitative assessment of how degradation affects replay conclusions

---

## 11. Error Model (Normative)

### 11.1 Error Object Shape

Each error MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `artifact_ref` (if applicable)
- `replay_mode` (which mode was active)

### 11.2 Required Error Codes

#### Bundle Integrity
- `PCAR_R_MISSING_ARTIFACT` — artifact listed in manifest not found in bundle
- `PCAR_R_DIGEST_MISMATCH` — artifact content does not match declared hash
- `PCAR_R_MANIFEST_INVALID` — manifest fails schema validation
- `PCAR_R_CHAIN_BREAK` — receipt chain integrity verification failed

#### Replay Execution
- `PCAR_R_VERSION_INCOMPATIBLE` — verifier or engine version incompatible with replay
- `PCAR_R_NONDETERMINISTIC_COMPONENT` — deterministic component produced different output on replay
- `PCAR_R_POLICY_LOAD_FAILURE` — could not load policy pack for replay
- `PCAR_R_EVIDENCE_UNAVAILABLE` — evidence needed for re-verification not available

#### Redaction
- `PCAR_R_REDACTION_BREAKS_REPLAY` — redacted evidence prevents a replay step
- `PCAR_R_DEGRADED_REPLAY` — replay completed but with reduced confidence due to missing artifacts

### 11.3 Error Handling Rules

- Integrity errors (digest mismatch, chain break) MUST be reported prominently — they indicate tampering or corruption.
- Non-deterministic divergence in EXACT mode SHOULD be reported as `WARN` (expected for external tools) or `ERROR` (unexpected for deterministic components).
- Redaction-related degradation MUST be explicitly declared, never silently absorbed.

---

## 12. Security Considerations (PCAR-R Specific)

### 12.1 Replay Bundle Tampering

An attacker may modify a replay bundle to hide or alter governance events. Mitigations:
- Manifest hash covers all artifact hashes.
- Receipt chain provides independent integrity verification.
- Epoch roots provide segment-level verification.
- Optional: bundle-level cryptographic signature (v3).

### 12.2 Selective Evidence Removal

An attacker may selectively remove evidence to hide specific events while preserving apparent integrity. Mitigations:
- Missing evidence is explicitly declared in the manifest.
- Replay degradation is reported.
- Evidence digests in receipts and proofs remain, enabling detection of unexplained gaps.

### 12.3 Counterfactual Misrepresentation

Counterfactual replay results may be presented as actual audit results. Mitigations:
- Counterfactual replays MUST be clearly labeled in their output.
- Counterfactual replay results MUST include the original run results for comparison.
- Replay mode is recorded in all output artifacts.

### 12.4 Version Skew

Replay with a different governor/verifier/engine version may produce subtly different results that are misinterpreted as policy findings. Mitigations:
- Version information is recorded in the manifest and in replay output.
- DIFF_VERIFIER mode is explicitly for version comparison.
- EXACT mode SHOULD warn if the replaying version differs from the original.

---

## 13. Privacy Considerations (PCAR-R Specific)

Replay bundles may contain sensitive data across all artifact types. Implementations SHOULD support:

- evidence redaction before bundling (Section 10),
- claim content redaction (with type and reference preservation),
- action parameter redaction,
- actor identity pseudonymization,
- scoped access to replay bundles.

Redaction MUST preserve hash integrity where possible. When it cannot (e.g., claim content changes affect claim hash), the degradation MUST be documented in the manifest.

---

## 14. Conformance

An implementation is **PCAR-R conformant** if it:

1. Produces replay bundles matching Section 6.
2. Supports EXACT replay mode (Section 7.1).
3. Supports at least one differential replay mode (Section 7.2, 7.3, or 7.4).
4. Verifies artifact integrity per Section 9.
5. Handles redaction per Section 10.
6. Records divergence points per Section 8.3.
7. Emits machine-readable errors per Section 11.

PCAR-R conformance is RECOMMENDED for PCAR-family conformance but not REQUIRED.

---

## 15. Informative Examples

### 15.1 Example: Replay Manifest (Excerpt)

```json
{
  "manifest_version": "0.1.0",
  "bundle_id": "replay-2026-02-23-001",
  "run_id": "run-abc123",
  "created_at": "2026-02-23T16:00:00Z",
  "artifacts": {
    "claim_batches": [
      {"batch_id": "cb-001", "path": "claims/batch-001.json", "hash": "sha256:..."}
    ],
    "proof_batches": [
      {"batch_id": "pb-001", "path": "proofs/batch-001.json", "hash": "sha256:..."}
    ],
    "decisions": [
      {"decision_id": "d-001", "path": "decisions/d-001.json", "hash": "sha256:..."},
      {"decision_id": "d-002", "path": "decisions/d-002.json", "hash": "sha256:..."}
    ],
    "receipt_chain": {
      "path": "receipts/receipts.jsonl",
      "hash": "sha256:...",
      "count": 12,
      "first_hash": "sha256:first...",
      "last_hash": "sha256:last..."
    },
    "evidence_blobs": [
      {"digest": "sha256:a1b2...", "path": "evidence/a1/a1b2...", "available": true},
      {"digest": "sha256:dead...", "path": "evidence/de/dead...", "available": false,
       "redacted_at": "2026-03-01T00:00:00Z", "redaction_reason": "retention_policy"}
    ],
    "policy_packs": [
      {"policy_id": "default_strict", "policy_version": "1.0.0",
       "path": "policy/default_strict-1.0.0.json", "hash": "sha256:..."}
    ]
  },
  "verifier_versions": {
    "governor.command_verifier": "2.3.0",
    "governor.file_verifier": "2.3.0"
  },
  "runtime_metadata": {
    "governor_version": "2.3.1",
    "platform": "linux-x86_64",
    "start_time": "2026-02-23T14:00:00Z",
    "end_time": "2026-02-23T15:30:00Z"
  },
  "integrity": {
    "artifact_count": 18,
    "evidence_available_count": 5,
    "evidence_redacted_count": 1,
    "chain_continuous": true,
    "epoch_roots": []
  },
  "manifest_hash": "sha256:manifest_hash..."
}
```

### 15.2 Example: DIFF_POLICY Divergence Point

```json
{
  "divergence_id": "div-001",
  "artifact_type": "decision",
  "artifact_id": "d-002",
  "original_digest": "sha256:original_decision...",
  "replayed_digest": "sha256:replayed_decision...",
  "divergence_kind": "deterministic",
  "details": {
    "original_decision": "ALLOW",
    "replayed_decision": "DENY",
    "original_rationale": ["proofs_complete", "freshness_valid"],
    "replayed_rationale": ["proof_missing"],
    "policy_diff": "New policy requires core.CONSISTENCY_CHECK for file_write actions",
    "claim_ref": "c-011"
  }
}
```

---

## 16. Open Questions

- Should replay bundles be a single archive file (tar.gz) or a directory? Archive is portable; directory is tool-friendly.
- Should PCAR-R define a standard replay CLI interface, or leave it to implementations?
- How should replay handle runs that span multiple sessions or daemon restarts?
- Should counterfactual replay support branching (explore multiple alternative paths from a divergence point)?
- What is the minimum evidence retention window that qualifies as "replayable"?

---

## 17. References (Informative)

- PCAR-000: Proof-Carrying Agent Runtime
- PCAR-A: Typed Claim Envelope
- PCAR-B: Proof Objects and Verifier Contract
- PCAR-C: Constraint Decisions and Regime Derivation
- PCAR-D: Receipt Canonicalization and Provenance Contract
- PCAR-E: Actuator Contract and Execution Semantics
- RFC 2119
- RFC 8174
