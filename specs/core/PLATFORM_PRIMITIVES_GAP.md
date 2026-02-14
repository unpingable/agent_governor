# Platform Primitives Gap Analysis

## Don't Roll Your Own Crypto (or Governance Substrate)

```yaml
status: gap
relates_to:
  - ARTIFACT_BINDING_GAP.md (receipt schema evolution, substrate binding)
  - SELF_GOVERNANCE_SPEC.md (admissibility, quorum, dual ledger)
  - PHASE_GATING_GAP.md (stage register, capability elevation)
  - gate_receipt.py (GateReceipt, current receipt primitive)
  - mcp_server.py (MCP safety controls)
blocking: nothing
priority: v3
```

---

## Principle

The governor's novelty is **binding safety claims to model state and policy**.
Everything below that layer — signing, attestation formats, policy engines,
capability tokens, identity, transparency logs — is solved supply-chain and
security plumbing.

The moment you find yourself designing signature schemes, key rotation
protocols, token formats, or registry replication, you've drifted.

Stay at the level of:

- Receipt schema
- Subject binding
- Regime hash
- Verification semantics

Then choose existing plumbing to implement it.

---

## The Plumbing Map

What already exists, battle-tested, that v3 should use instead of inventing:

### 1. Receipt Container: DSSE / in-toto Attestations

**What it is:** Dead Simple Signing Envelope (DSSE) is a format for signing
arbitrary payloads without canonicalization footguns. in-toto attestations
wrap a subject + predicate in DSSE.

**Governor mapping:** The receipt becomes an in-toto attestation:

- **subject** = model artifact hash (+ optional runtime image digest)
- **predicate** = policy assertion + TTL + regime hash + evidence digest
- **signature** = attester identity

**Why not JWT?** JWT invites header bloat, accidental PII claims, confused
semantics. If you must use JWT, make it JWS only (no encryption), keep it
tiny. DSSE/CBOR + detached signature is cleaner.

**Reference:** [in-toto attestation spec](https://github.com/in-toto/attestation)

### 2. Signing + Transparency: Sigstore

**What it is:** Keyless signing (Fulcio CA), transparency log (Rekor),
verification tooling. sigstore-python exists for Python signing/verifying.
Cosign already speaks in-toto attestation.

**Governor mapping:** Sign receipts with Sigstore instead of bespoke key
distribution. Rekor gives you "append-only, timestamped, can't quietly
rewrite history" for free.

**When to adopt:** Not day 1. Start with local Ed25519 keypair. Move to
Sigstore when the governor runs as a shared service and needs distributed
trust.

**Reference:** [sigstore-python](https://docs.sigstore.dev/language_clients/python/),
[Rekor](https://docs.sigstore.dev/logging/overview/)

### 3. Policy Engine: OPA (Open Policy Agent)

**What it is:** Policy-as-code evaluation engine. Rego language for
writing admission rules. Built for gateway/service/CI enforcement.

**Governor mapping:** The "witness compares evidence to policy thresholds
and signs or refuses" step becomes an OPA decision. Policy assertions
become Rego rules. Policy diffing, versioning, and "why denied?" come
for free.

**When to adopt:** When policy complexity exceeds what inline Python
checks can handle cleanly. Or when multiple services need to evaluate
the same policy bundle.

**Reference:** [OPA docs](https://www.openpolicyagent.org/docs/)

### 4. Capability Tokens: Biscuit

**What it is:** Offline-attenuable authorization tokens with logic-based
checks. Unlike JWT, supports delegation and attenuation (narrow scope
without re-signing). Python bindings exist.

**Governor mapping:** Governor mints a capability token for each tool
call. Token encodes:

- Tool name
- Allowed args / scope
- Cost budget
- Expiry
- Nonce / replay protection

Tool gateway verifies token before executing. Agent cannot call tool
directly — prevents bypass.

**Alternative:** Macaroons (caveats, attenuation; older but well-understood).

**When to adopt:** When tool calls become a trust boundary (multi-tenant,
or agent has network access to tool endpoints).

**Reference:** [Biscuit](https://www.biscuitsec.org/),
[Macaroons paper](https://theory.stanford.edu/~ataly/Papers/macaroons.pdf)

### 5. Artifact Allowlist Integrity: TUF

**What it is:** The Update Framework. Signed metadata roles for publishing
"these are the approved artifacts." Survives compromised infrastructure
via threshold signing + snapshot/timestamp discipline.

**Governor mapping:** The "approved model artifact set" that admission
control checks against. TUF ensures the allowlist itself hasn't been
tampered with.

**When to adopt:** When the governor manages artifact promotion across
environments or tenants.

**Reference:** [TUF spec](https://theupdateframework.github.io/specification/latest/)

### 6. Workload Identity: SPIFFE/SPIRE

**What it is:** Attest workloads and issue short-lived identities for
mTLS. Standard pattern for "who is allowed to sign / enforce" in
multi-service deployments.

**Governor mapping:** If the governor becomes multi-service (sidecar,
gateway, witness), SPIFFE handles identity between components without
shared secrets.

**When to adopt:** Multi-service deployment only. Irrelevant for single
binary.

**Reference:** [SPIFFE](https://spiffe.io/docs/latest/spire-about/use-cases/)

---

## What the Governor Owns vs. What It Delegates

| Layer | Governor owns | Delegates to |
|-------|--------------|-------------|
| **What to bind** | Receipt schema, subject/regime/evidence semantics | Nothing — this is the novel part |
| **How to sign** | Nothing | DSSE + Sigstore (or local Ed25519) |
| **How to evaluate policy** | Claim types, admission rules | OPA (when complexity warrants) |
| **How to delegate capability** | Scope + budget + expiry semantics | Biscuit / Macaroons |
| **How to trust artifact lists** | Promotion criteria | TUF |
| **How to identify services** | Authority roles | SPIFFE/SPIRE |
| **How to log immutably** | What goes in the log | Rekor (or local hash chain) |

The governor is a **reference monitor for mutating systems**, not a
crypto toolkit or a blockchain.

---

## Interfaces to Lock In Now (Deployment-Shape-Independent)

Even before choosing any of the above, define these in the governor repo:

### Canonical Identifiers

How each hash is computed. Decide once, use everywhere:

```python
model_artifact_id:  H(weights_or_package_manifest)
                    # For API models: H(provider + model_id + version)
policy_hash:        H(canonical_json(policy_bundle))
regime_hash:        H(tool_schemas + endpoint_versions + corpus_digest + routing_config)
evidence_digest:    H(eval_manifest + results_summary + dataset_ids)
```

### Verification API

One function signature to keep forever:

```python
def verify(
    claim: Claim,
    subject: ArtifactSubject,
    regime: RegimeSnapshot,
) -> VerificationResult:
    """Returns decision + receipt_id + reasons."""
```

Where "subject" can be: model artifact, tool call request, memory write,
retrieval result. This keeps you from coupling to "weights updating"
specifically.

### Capability Token Shape

Even if not implemented yet, define the fields:

```python
@dataclass
class CapabilityToken:
    tool: str               # tool name
    scope: dict             # allowed args/parameters
    budget: float           # cost ceiling
    expires_at: datetime    # hard expiry
    nonce: str              # replay protection
    issuer_receipt_id: str  # which receipt authorized this
```

Enough to later choose Biscuit/Macaroons/JWT without refactoring.

---

## What to Explicitly NOT Decide Yet

- Microservices vs single binary vs sidecar
- Sigstore vs local keys
- OPA vs inline Python policy
- Where receipts live (DB / log / registry)
- Rekor vs local hash chain

These are deployment decisions. The governor isn't there yet.

---

## Smallest Viable Combo (When Ready)

For a single-binary governor that needs real teeth:

1. **DSSE receipts** with local Ed25519 signing (no Sigstore dependency)
2. **OPA** for policy evaluation (if policy complexity warrants; otherwise
   inline Python is fine)
3. **Biscuit tokens** for tool capability delegation

Add Sigstore + Rekor when moving to distributed/multi-tenant.
Add TUF when managing artifact promotion across environments.
Add SPIFFE when the governor becomes multi-service.

---

## The Split

**Governor's job:** epistemic rigor at the edges. What to bind, when it
expires, what's admissible.

**Plumbing's job:** boring enforcement underneath. How to sign, how to
verify, how to delegate, how to log.

That split scales without turning the governor into AWS.
