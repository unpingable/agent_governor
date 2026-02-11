# Gap Spec: Privacy & Compliance Architecture for Governor 3.0

**Date:** 2026-02-10
**Status:** Design constraint for 3.0 planning
**Source:** ChatGPT compliance analysis + architectural synthesis

---

## The Core Tension

> **Immutability vs Erasure**: The witness layer wants permanent proof. Privacy law wants controllable data lifecycle.

This is not a contradiction if you architect correctly. The trick:

**Make receipts prove that a procedure happened, not who it happened to.**

---

## The Two-Layer Architecture

### Layer A: Ledger (Public, Append-Only, Non-Personal)

Keep forever. Safe to be immutable.

| Field | Example | Notes |
|-------|---------|-------|
| `receipt_id` | UUIDv7 | Not identifying |
| `timestamp` | ISO 8601 | When, not who |
| `gate_id` | `"admissibility"` | Which control |
| `subject_digest` | HMAC-SHA256 | **Salted** - see below |
| `policy_digest` | SHA-256 | Constitution hash (public) |
| `verdict` | `"ALLOW"` | Outcome |
| `reason_codes` | `["APPROVED"]` | **Codes only, not strings** |
| `evidence_digests` | [HMAC-SHA256, ...] | **Salted** - see below |
| `witness_key_id` | `"key-abc123"` | Pseudonymous |
| `purpose_id` | `"deploy-gate"` | Purpose binding |

**Rule**: No PII, no content, no identifying data, no free-form strings.

### Critical: Linkability Prevention

> **"Hash-only" is not automatically "non-personal."**

If `subject_digest` is a hash of something low-entropy (email, username, short prompt), it's still linkable via dictionary attack. Same for `evidence_digests`.

**Fix: All digests MUST be salted/HMAC'd:**

```python
# Bad - enumerable, linkable
subject_digest = sha256(content)

# Good - non-enumerable
subject_digest = hmac_sha256(tenant_salt, content)
# OR
subject_digest = sha256(content || per_period_salt)
```

**Salt storage:**
- Salt stored in Layer B (evidence store)
- Per-tenant or per-retention-period
- If Layer B is deleted, digests become computationally useless for re-ID

**Document this explicitly in implementation:**
> "All content digests must use HMAC or salted hashing to prevent offline dictionary attacks against the ledger."

### Layer B: Evidence Store (Private, Controlled, Deletable)

Subject to retention policies, access controls, deletion requests.

| Content | Retention | Deletion |
|---------|-----------|----------|
| Raw evidence blobs | Policy-defined | On request |
| Prompt/response text | 30-90 days | On request |
| Actor → identity mapping | Scoped | Rotatable |
| Re-ID salt/keys | Time-limited | Destroyable |

**Rule**: If you must delete for GDPR/CCPA, delete Layer B. Layer A still proves the control happened.

---

## Framework Alignment Matrix

| Framework | Wants | Governor Provides | Gap/Risk |
|-----------|-------|-------------------|----------|
| **GDPR** | Erasure, minimization, purpose limits | Layer A/B split, hash-only receipts | Art. 22 if "significant effects" |
| **SOX** | Tamper-evident logs, SoD, retention | Append-only receipts, witness separation | Need role-based keys for SoD |
| **PCI DSS** | Audit logs, no secrets in logs, 12mo retention | Hash commitments, evidence pointers | Scope creep if touching CDE |
| **FedRAMP** | Continuous evidence, reproducible controls | Receipts as ConMon artifacts | Need control family mapping |
| **SOC 2** | Evidence of controls | Receipts are auditor candy | Just works |
| **HIPAA** | PHI protection | No PHI in Layer A | Same as GDPR |

---

## Design Principles (Bake In Now)

### 1. Data Minimization by Default

```python
class GateReceipt:
    # Layer A (ledger) - keep forever
    receipt_id: str           # UUIDv7
    timestamp: datetime
    gate_id: str
    subject_digest: str       # HMAC'd, not raw hash
    verdict: Verdict
    reason_codes: list[str]   # CODES ONLY: ["EVID_MISSING", "POLICY_X3"]
    policy_digest: str
    evidence_digests: list[str]  # HMAC'd, not raw hashes
    witness_key_id: str       # Pseudonymous
    purpose_id: str           # Purpose binding
    signature: bytes

    # Layer B (evidence store) - separate, deletable
    # evidence_blobs: NOT HERE
    # actor_email: NOT HERE
    # raw_content: NOT HERE
    # human_readable_reasons: NOT HERE - store separately
    # salt: stored here, enables digest verification
```

**Reason codes, not reason strings:**

```python
# Bad - can leak PII
reasons: ["Rejected because user John asked for SSN"]

# Good - codes only
reason_codes: ["INPUT_VALIDATION_FAIL", "PII_PATTERN_DETECTED"]
# Human explanation in Layer B: {"PII_PATTERN_DETECTED": "SSN-like pattern in field X"}
```

### 2. Identity is Key Material, Not PII

```
Witness identity in receipt: "witness-key-7f3a2b"
Mapping to human: { "witness-key-7f3a2b": "james@example.com" }
                   ↑ Stored separately, deletable, rotatable
```

### 3. Evidence Pointers, Not Evidence

```python
# Bad (evidence in receipt)
receipt.evidence = {"test_output": "PASSED: all 47 tests..."}

# Good (pointer to evidence)
receipt.evidence_digests = ["sha256:a1b2c3..."]
# Actual evidence in .governor/evidence/a1b2c3... (Layer B)
```

### 4. Retention is a Policy Surface

```yaml
# constitution.yaml
retention:
  receipts: "indefinite"      # Layer A - keep forever
  evidence:
    default: "90d"            # Layer B - 90 days
    pii_containing: "30d"     # Tighter for PII
    on_erasure_request: "delete"  # GDPR compliance
  identity_mappings:
    rotation: "yearly"
    on_erasure_request: "delete"
  legal_hold:
    enabled: false            # Override when litigation/investigation
    affected_items: []        # List of evidence_digests under hold
```

**Legal hold**: When `legal_hold.enabled: true`, deletion is suspended for affected items. This handles SOX/litigation requirements without breaking erasure architecture.

### 5. Deletion Proof (Tombstone Receipts)

Delete Layer B content, but prove the deletion happened:

```python
# Tombstone receipt in Layer A
TombstoneReceipt = {
    "receipt_id": UUIDv7,
    "event_type": "EVIDENCE_DELETE",
    "evidence_digest": "hmac-sha256:...",  # What was deleted
    "policy_digest": "sha256:...",          # Under what policy
    "deleter_key_id": "key-abc123",
    "reason_code": "RETENTION_EXPIRED" | "ERASURE_REQUEST" | "LEGAL_HOLD_RELEASE",
    "timestamp": datetime,
    "signature": bytes
}
```

**Rule**: No content in tombstone. Just proof of lifecycle transition.

### 6. Identity Rotation as Governance Event

Don't treat rotation as a cron job. Make it evented:

```python
KeyRotationReceipt = {
    "receipt_id": UUIDv7,
    "event_type": "WITNESS_KEY_ROTATE",
    "old_key_id": "key-abc123",
    "new_key_id": "key-def456",
    "rotation_reason": "SCHEDULED" | "COMPROMISE" | "POLICY",
    "timestamp": datetime,
    "signature": bytes  # Signed by old key (proves continuity)
}
```

Key continuity chain lives in Layer A. Mapping to human identity lives in Layer B (deletable).

### 7. Contestability Window (Article 22 Support)

```yaml
contest_window:
  duration: "24h"
  human_review: true          # Art. 22 "human intervention"
  escalation: "operator"
```

> **Note**: Article 22 applies specifically to *solely automated decisions with legal or similarly significant effects*. Contestability + human override are **supporting controls** for Article 22-like obligations when the governor gates significant actions. Don't overclaim full compliance without legal review.

### 8. Purpose Binding

Receipts carry a `purpose_id` to prove you didn't reuse logs for unrelated purposes:

```python
receipt.purpose_id = "deploy-gate"  # Non-PII, auditable
```

Purpose limitation matters for GDPR audits and enterprise trust. The purpose registry lives in the constitution:

```yaml
purposes:
  deploy-gate:
    description: "Gating deployment decisions"
    lawful_basis: "legitimate_interest"
  access-control:
    description: "Gating resource access"
    lawful_basis: "contract"
```

---

## What to Avoid (Anti-Patterns)

| Anti-Pattern | Why It Hurts | Fix |
|--------------|--------------|-----|
| Raw SHA-256 of low-entropy content | Dictionary attack → re-identification | HMAC with Layer B salt |
| Free-form reason strings | PII leaks into ledger | Reason codes only |
| Full prompt/response in receipt | GDPR erasure nightmare | Hash only, store separately |
| Email as witness ID | Ties identity to ledger | Use key-based pseudonyms |
| Treating ledger as data lake | Unbounded retention of PII | Layer A/B split |
| "Convenient" logging | Scope creep, audit trail becomes exfil channel | Policy-controlled fields |
| Single principal closure | SOX/FedRAMP SoD violation | Role-based witness separation |
| Deletion without tombstone | Can't prove you complied with erasure | Tombstone receipts |
| Rotation as cron job | Loses audit trail of key lifecycle | Key rotation events |

---

## Deployment Mode Implications

### Mode 1: Local Tool (Current)

- **Controller**: User (if personal use) or Employer (if work use)
- **Processor**: N/A (no third party)
- **GDPR**: Architecture supports minimization/erasure regardless of use context
- **Note**: "Household exemption" only applies to purely personal use. Work use on endpoints is not exempt.
- **Focus**: Build the split architecture now - it works for all modes

### Mode 2: Enterprise Library

- **Controller**: Customer org
- **Processor**: N/A (runs on their infra)
- **GDPR**: Customer's problem, but architecture must support it
- **Focus**: Provide retention hooks, deletion APIs, purpose binding

### Mode 3: Hosted Witness Service (Future)

- **Controller**: Customer org (for their data)
- **Processor**: You (for operating the service)
- **GDPR**: Full exposure - DPAs, breach duties, transfers
- **Focus**: Full compliance architecture, SOC 2, etc.

---

## Scope Boundary (PCI/FedRAMP)

Explicit "in-scope boundary" config to prevent scope creep:

```yaml
scope:
  touches_cde: false          # Does governor gate CDE systems?
  touches_keys: false         # Does governor manage crypto keys?
  touches_phi: false          # Does governor process health data?

  # If any true, apply heightened controls:
  heightened_controls:
    least_privilege: true
    centralized_logging: true
    immutability: true
    encryption_at_rest: true
```

If governor is "adjacent" to sensitive systems, treat its logs as sensitive.

---

## Implementation Checklist for 2.x → 3.0

### Critical (Do First)
- [ ] **Salt/HMAC all content digests** - kills linkability/dictionary attacks
- [ ] **Reason codes only in Layer A** - no free-form strings in receipts

### Already Have (Verify)
- [ ] Receipts use content hashes, not content
- [ ] Evidence stored separately from receipts
- [ ] Witness identity is key-based, not email

### Need to Add
- [ ] Retention policy surface in constitution
- [ ] Evidence pruning based on retention
- [ ] Identity mapping rotation mechanism (as governance event)
- [ ] Deletion API for Layer B content
- [ ] Tombstone receipts for deletion proof
- [ ] Legal hold flag to suspend deletion
- [ ] Purpose binding (`purpose_id` in receipts)
- [ ] Scope boundary config (CDE adjacency)

### Future (3.x+)
- [ ] Role-based witness keys for SoD
- [ ] Control family mapping for FedRAMP
- [ ] SOC 2 evidence export format
- [ ] Multi-tenant isolation with per-tenant salts

---

## The One-Liner

> **Make the ledger about legitimacy, not about people.**

If you do this, every compliance framework becomes an engineering constraint, not an existential contradiction.

---

## References

- GDPR Articles 5, 17, 22, 25
- SOX Section 404
- PCI DSS 4.0.1 Requirements 10.x
- NIST 800-53 AU, CM families
- FedRAMP ConMon requirements

---

*"Governance isn't paperwork. It's just systems we refused to automate."*
