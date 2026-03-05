# GOV_GAP_DISCLOSURE_STANDING_001 — Gradients, Cliffs, and Standing

**Status:** Design spec (v3 prerequisite)
**Track:** Governance ethics → mechanical enforcement
**Depends on:** gate_receipt (shipped), provenance_labels (shipped), egress_gate (shipped), context_manifest Phase 1 (shipped), receipt_kernel (shipped)
**Companion specs:** PRIVACY_COMPLIANCE_SPEC.md (two-layer architecture), HUMAN_TELEMETRY_BOUNDARY_SPEC.md (structural boundary), GOVERNANCE_ABUSE_AUDIT.md (abuse rubric), ETHICAL_HARDENING.md (testable invariants)

---

## Problem

The existing ethics specs say *what not to be*. The abuse audit rubric asks
the right questions per-feature. The privacy spec designs the two-layer
architecture. But none of them produce **schema fields, default values, and
mechanical invariants** that enforce the principles at runtime.

Without mechanical enforcement, "not a panopticon" is a readme promise.
With v3/SaaS, the incentive gradient points toward exactly the abuse shape
the specs warn against.

**This spec translates values into defaults, invariants, and structural friction.**

The meta-principle: **Governor ships gradients, not god-mode.**

- Make the emancipatory path the default (low effort).
- Make the panopticon path expensive, loud, and policy-invalid (high effort + visible).

---

## 1. Standing Model

### 1.1 Roles (minimum viable set)

```python
class StandingRole(str, Enum):
    SUBJECT = "subject"            # Entity the receipt is "about"
    OPERATOR = "operator"          # Runs the agent session
    TENANT_ADMIN = "tenant_admin"  # Manages tenant policy
    AUDITOR = "auditor"            # Independent review (external or internal)
    SYSTEM_MAINTAINER = "maintainer"  # Governor infrastructure
```

Not an org chart. Roles are **claims about relationship to a receipt chain**,
not job titles. One person may hold multiple roles. Roles are scoped to a
tenant, not global.

### 1.2 Rights per role

| Right | subject | operator | tenant_admin | auditor | maintainer |
|-------|---------|----------|-------------|---------|------------|
| `read` (own receipts) | YES | scoped | scoped | scoped | NO* |
| `export` | redacted | redacted | tenant-scoped | audit-scoped | NO |
| `challenge` | YES | NO | NO | YES | NO |
| `redact_request` | YES | NO | YES (own tenant) | NO | NO |
| `resolve` (challenges) | NO | NO | YES | YES | NO |

\* Maintainer sees service health telemetry (anonymized, no tenant data).
Cross-tenant correlation identifiers are structurally forbidden.

### 1.3 Invariants

- **I1: Subject readability.** Any receipt "about" a subject MUST be
  subject-readable, or include an explicit `standing_exemption` field with
  reason code + expiry. Exemptions are themselves receipted.

- **I2: Appeal route.** Every blocking verdict MUST include a
  `challenge_route` field (even if it's just `"manual_review"`).
  Receipts without appeal routes fail the abuse audit (Q3).

- **I3: No ambient standing.** Roles are not inherited from org charts.
  Standing is asserted per-chain, and the assertion is receipted.

---

## 2. Field-Level Classification

### 2.1 Classification vocabulary

```python
class FieldVisibility(str, Enum):
    PUBLIC = "public"      # Anyone with chain access
    TENANT = "tenant"      # Tenant members only
    SUBJECT = "subject"    # Subject + explicit grantees
    SEALED = "sealed"      # Requires cryptographic capability
```

### 2.2 Schema annotations

Every schema field in receipt/manifest/signal types gets a classification.
Classification is metadata on the *schema*, not per-instance.

```python
# Example: GateReceipt field classifications
RECEIPT_FIELD_VISIBILITY = {
    "receipt_id": FieldVisibility.PUBLIC,
    "schema_version": FieldVisibility.PUBLIC,
    "timestamp": FieldVisibility.PUBLIC,
    "gate": FieldVisibility.PUBLIC,
    "verdict": FieldVisibility.PUBLIC,
    "subject_hash": FieldVisibility.TENANT,     # ← not public
    "evidence_hash": FieldVisibility.TENANT,     # ← not public
    "policy_hash": FieldVisibility.PUBLIC,
    "principal_id": FieldVisibility.SUBJECT,     # ← only the subject
    "tenant_id": FieldVisibility.SEALED,         # ← cross-tenant leak prevention
}
```

### 2.3 Invariants

- **I4: No field without classification.** Schema migration that adds a
  field without a visibility annotation fails CI.

- **I5: Classification monotonicity.** A field's visibility can be
  *tightened* (public → tenant) but never *loosened* without a
  `DisclosureEscalation` receipt.

---

## 3. Disclosure Policy (the core mechanical layer)

### 3.1 DisclosurePolicy

```python
@dataclass(frozen=True)
class DisclosurePolicy:
    """What a viewer with a given role can see from a receipt chain."""
    viewer_role: StandingRole
    max_visibility: FieldVisibility    # Ceiling
    redaction_mode: str                # "hash" | "omit" | "summary"
    include_evidence: bool             # Bodies or just hashes
    include_timing: bool               # Timing metadata
    include_chain_refs: bool           # prev_hash links
```

### 3.2 Redacted export

```python
def export(
    receipts: list[GateReceipt],
    viewer_role: StandingRole,
    policy: DisclosurePolicy,
) -> RedactedBundle:
    """Export receipts redacted to viewer's standing.

    Fields above the viewer's max_visibility are replaced per
    redaction_mode (hash, omit, or bounded summary).
    """
```

### 3.3 Gradients

The **resolution gradient** (what level of detail is visible):

| Level | What's included | Who gets it | Friction to escalate |
|-------|----------------|-------------|---------------------|
| 0: commitment | verdict + gate + timestamp | public | none |
| 1: summary | + reason codes + policy_hash | tenant | none |
| 2: evidence refs | + evidence_hash + subject_hash | tenant + auditor | policy assertion |
| 3: sealed evidence | + evidence bodies | subject + auditor | capability token |
| 4: raw content | + region bodies + raw prompts | nobody by default | DisclosureEscalation receipt + justification + expiry |

**Level 4 should feel radioactive.** It requires:
- Explicit `DisclosureEscalation` receipt
- Justification field (not free-form — reason code enum)
- Expiry (default 72h, max configurable per tenant)
- The escalation itself is visible to the subject (I1)

### 3.4 Invariants

- **I6: Raw export requires capability.** No export at Level 4 without a
  cryptographic capability that isn't mintable by the same actor who benefits
  from the disclosure.

- **I7: Export is receipted.** Every `export()` call emits a
  `disclosure_export` gate receipt with viewer_role + level + scope.

- **I8: No silent escalation.** Moving from Level N to Level N+1 requires
  an explicit step that lands in the chain.

---

## 4. Contestation Protocol

### 4.1 Challenge/Response as receipts

Contestability can't be a support ticket. It lives in the same chain.

```python
@dataclass(frozen=True)
class ChallengeReceipt:
    """Subject or auditor challenges a verdict."""
    challenge_id: str
    target_receipt_id: str           # What's being challenged
    challenger_role: StandingRole    # subject or auditor
    basis: str                       # Enum: "factual_error" | "policy_dispute" |
                                     #        "standing_violation" | "procedural"
    evidence_hash: str | None        # Counter-evidence, if any
    timestamp: str

@dataclass(frozen=True)
class ResponseReceipt:
    """Operator/system response to a challenge."""
    response_id: str
    challenge_id: str
    responder_role: StandingRole
    action: str                      # "upheld" | "revised" | "deferred" | "denied"
    reason_code: str
    revised_verdict: str | None      # If action == "revised"
    timestamp: str

@dataclass(frozen=True)
class ResolutionReceipt:
    """Final resolution (may involve independent review)."""
    resolution_id: str
    challenge_id: str
    resolver_role: StandingRole      # tenant_admin or auditor
    outcome: str                     # "accepted" | "denied" | "escalated"
    reason_code: str
    timestamp: str
```

### 4.2 Invariants

- **I9: Unresolved challenges downgrade trust.** Any receipt with an open
  challenge gets `trust_state: "provisional"` in derived views. This isn't
  cosmetic — it affects downstream gating decisions that reference the
  challenged receipt.

- **I10: No unchallengeable receipts about a subject.** If a receipt's
  `subject_hash` links to a known subject, that subject MUST be able to
  file a ChallengeReceipt. Blocking the challenge path is a P5 abuse
  (Appeals Theater).

- **I11: Challenges are append-only.** A challenge cannot be silently
  deleted. Resolution can mark it resolved, but the challenge itself
  persists.

---

## 5. Retention Classes

### 5.1 Vocabulary

```python
class RetentionClass(str, Enum):
    EPHEMERAL = "ephemeral"        # Default for operational receipts. Short TTL.
    OPERATIONAL = "operational"    # Medium TTL. Service health.
    AUDIT = "audit"                # Long TTL. Compliance evidence.
    LEGAL_HOLD = "legal_hold"      # Indefinite. Explicit policy. Scarred.
```

### 5.2 Defaults

| Receipt type | Default retention | Escalation to extend |
|-------------|-------------------|---------------------|
| Gate receipts (observe) | ephemeral (24h) | reason code |
| Gate receipts (pass/warn) | operational (30d) | policy assertion |
| Gate receipts (block) | audit (1y) | automatic |
| Challenge/Response | audit (1y) | automatic |
| Manifest (context_build) | operational (30d) | reason code |
| Disclosure export | audit (1y) | automatic (receipting the receipt) |

### 5.3 Invariants

- **I12: No silent retention extension.** Extending retention beyond
  default requires a `RetentionExtension` receipt with reason code.
  Extensions are visible to the subject (I1).

- **I13: Deletion is receipted.** When ephemeral/operational receipts
  expire, a tombstone receipt replaces them (hash + metadata, no content).
  Proves "something was here and was properly deleted."

- **I14: Key erasure as practical deletion.** For sealed fields,
  key rotation / key erasure provides cryptographic deletion.
  The ciphertext persists (chain integrity) but becomes unreadable.

---

## 6. SaaS Hard Mode

### 6.1 Structural constraints for multi-tenant deployment

- **I15: Per-tenant encryption keys.** Operator staff cannot decrypt
  tenant or subject scopes. Service health telemetry is structurally
  separated from customer ledger data.

- **I16: No cross-tenant correlation.** No identifier (receipt_id,
  session_id, hash) appears in more than one tenant's chain.
  Implementation: per-tenant HMAC salt (already in PRIVACY_COMPLIANCE_SPEC).

- **I17: No admin god-mode.** No single credential grants read access
  to all tenant data. Maintenance operations use anonymized aggregates.

### 6.2 The vendor-can't-browse invariant

If the vendor can browse everyone's receipts, you're one product pivot
away from Judge-but-enterprise. The structural constraint:

```
vendor_staff_access ∩ tenant_receipt_content = ∅
```

Vendor sees: aggregate health metrics, anonymized error rates, capacity
signals. Vendor does NOT see: verdicts about specific subjects, evidence
bodies, challenge content, disclosure exports.

---

## 7. Tripwires (Non-Goals as Tests)

These are not just "we don't do that." They're **tests that fail when
someone tries.**

| Tripwire | What it catches | Test shape |
|----------|----------------|------------|
| T1: No ambient capture | Background monitoring streams | Assert: no receipt emission without explicit gate invocation |
| T2: No behavioral scoring | "Score the user" primitives | Assert: no receipt field computes over operator identity |
| T3: No bulk deanonymization | Export that makes correlation cheap | Assert: export() never includes both subject_hash and content in same bundle |
| T4: No continuous monitoring | Streams that outlive sessions | Assert: no open-ended subscription on receipt chains |
| T5: No unreceipted authority | Power without audit trail | Assert: every state mutation emits a receipt (abuse audit Q2) |
| T6: No silent policy change | Threshold edits without receipts | Assert: policy_hash changes emit `policy_mutation` receipt (abuse audit Q4) |

---

## 8. Mapping to Existing Specs

| This spec | Existing spec | Relationship |
|-----------|--------------|-------------|
| Standing model (§1) | GOVERNANCE_ABUSE_AUDIT Q3 | Mechanizes "appeal surface" |
| Field classification (§2) | PRIVACY_COMPLIANCE_SPEC Layer A/B | Adds per-field granularity |
| Disclosure policy (§3) | Egress gate (shipped) | Extends egress to receipt export |
| Contestation (§4) | GOVERNANCE_ABUSE_AUDIT P5 | Prevents "Appeals Theater" |
| Retention (§5) | receipt_kernel retention (shipped) | Adds reason codes + subject visibility |
| SaaS constraints (§6) | PRIVACY_COMPLIANCE_SPEC HMAC salts | Adds structural separation invariants |
| Tripwires (§7) | HUMAN_TELEMETRY_BOUNDARY_SPEC | Turns constraints into tests |

---

## 9. Implementation Phases

### Phase A: Schema + Defaults (v3-adjacent, smallest useful increment)

- Add `FieldVisibility` annotations to all receipt/manifest/signal schemas
- Add `retention_class` field to GateReceipt (default from lookup table)
- Add `challenge_route` field to blocking verdicts
- Implement `DisclosurePolicy` + `export()` with redacted bundles
- Tests: field classification coverage, redaction correctness, retention defaults
- **This is the "one concrete next step" — it forces formalization of standing,
  minimization, and "what can be known."**

### Phase B: Contestation + Standing (v3)

- `ChallengeReceipt` / `ResponseReceipt` / `ResolutionReceipt` types
- `StandingRole` assertion + receipting
- Provisional trust state on challenged receipts
- CLI: `governor challenge`, `governor standing`

### Phase C: SaaS Hardening (v3 proper)

- Per-tenant encryption + key management
- Cross-tenant correlation prevention (salted identifiers)
- Vendor access structural separation
- Tripwire tests as CI invariants

---

## 10. The Gradients (Summary)

Pre-baked gradients with cliffs:

| Gradient | Low end (default) | High end (requires friction) | Cliff (impossible without capability) |
|----------|-------------------|------------------------------|--------------------------------------|
| **Resolution** | hashes → summaries | sealed blobs | raw content (Level 4) |
| **Audience** | subject | tenant → auditor | vendor ops (near-blind by design) |
| **Time** | ephemeral (24h) | operational (30d) → audit (1y) | legal hold (scarred, receipted) |
| **Export** | redacted bundle | richer bundle + policy assertion | raw export (capability-gated) |
| **Authority** | operator asserts | counterparty challenges | independent review resolves |

Defaults are low-resolution, low-retention, subject-readable, contestable.
Escalation is explicit cost + explicit justification + explicit visibility.
Cliffs are impossible without capabilities you don't hand out.

---

## Open Questions

1. **Capability token shape.** JWT? HMAC? Opaque + expiry? Phase A can
   defer this (use simple string tokens), but Phase C needs real crypto.

2. **Challenge routing.** Where do challenges land? Separate chain?
   Same chain with type tag? Probably same chain (contestation is
   evidence about the receipt, not separate from it).

3. **Anonymized aggregates.** What's the minimum viable aggregate set
   for vendor service health? Needs to be defined concretely to prevent
   scope creep ("we need just one more field for debugging").

4. **Backward compatibility.** Existing receipts lack retention_class
   and challenge_route. Migration: treat missing fields as
   `operational` retention and `manual_review` challenge route.
