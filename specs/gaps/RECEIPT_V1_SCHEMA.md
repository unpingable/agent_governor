# TODO: Receipt v1 Schema — Gap Spec (Patched)

## What This Is

The stable contract for tool governance audit trails. Runtime-agnostic,
transport-agnostic, copyable by any project that wants auditable tool execution.

**Design principle:** The receipt format is the invariant. Everything else —
MCP adapters, gateway implementations, policy engines — are downstream of this
schema. If the receipt format is right, other projects will emit it because
it's the easiest way to answer "what did your agent do and why?"

**Non-goals:** This is not a policy language. It is not a tool protocol. It is
the *output* of a policy decision about a tool invocation — the audit record
that survives after execution.

---

## Receipt v1 Schema

### Core Fields

```jsonc
{
  // === Identity ===
  "receipt_id": "string",           // Unique ID (UUIDv7 recommended: time-sortable + random)
  "receipt_version": "1.0",         // Schema version (semver, always present)
  "receipt_hash": "string",         // SHA-256 of canonical form (see Canonicalization)

  // === Chain ===
  "chain": {
    "parent_receipt_id": "string",    // Previous receipt's receipt_id (indexing)
    "parent_receipt_hash": "string",  // Previous receipt's receipt_hash (integrity)
    "seq": 0                          // Integer sequence number within scope (see Ordering)
  },
  // Chain block omitted entirely for first receipt in a session.
  // If present, BOTH parent_receipt_id and parent_receipt_hash are required.

  // === Timestamp ===
  "timestamp_wall": "string",       // ISO 8601 UTC (human-readable)
  "timestamp_mono": 0,              // Monotonic counter, optional sugar (see Ordering)

  // === Actor ===
  "actor": {
    "agent_id": "string",           // What agent initiated this (opaque ID, not PII)
    "session_id": "string",         // Session/conversation scope
    "runtime": "string",            // Optional: which runtime (e.g. "claude-code", "custom")
    "issuer": "string",             // Optional: who asserted this identity (for multi-tenant)
    "auth_context": "string"        // Optional: how identity was established
                                     //   values: "stdio" | "oauth" | "mtls" | "api_key" | "none"
  },

  // === Tool Call ===
  "tool": {
    "tool_id": "string",            // Tool name / identifier
    "tool_version": "string",       // Optional: tool version if known
    "call_id": "string",            // Optional: idempotency key for retry dedup
    "args_hash": "string",          // Domain-separated hash of canonical args (see Hashing)
    "args_summary": "string",       // Optional: human-readable summary (MUST be sanitized)
    "capability_asserted": "string", // Optional: what permission/scope the agent claimed
    "origin": {                      // Optional: where the tool lives (for aggregated/proxied setups)
      "server_id": "string",        // Config name of upstream server
      "transport": "string",        // "stdio" | "http"
      "instance": "string"          // Optional: disambiguate replicas
    }
  },

  // === Policy Decision ===
  "decision": {
    "action": "allow | deny | transform | escalate",
    "reason_code": "string",        // Machine-readable reason (namespaced, see Reason Codes)
    "reason_human": "string",       // Human-readable explanation (max 256 chars, sanitized)
    "policy_id": "string",          // Optional: which policy rule triggered this decision
    "policy_version": "string",     // Optional: version of policy set applied
    "policy_path": [                // Optional: compositional decision trace
      { "id": "string", "version": "string", "outcome": "string" }
    ],
    "transformed_args_hash": "string", // If action=transform, domain-separated hash of modified args
    "budget": {                     // Optional: present when budget is a factor in the decision
      "rate_remaining": 0,
      "cost_remaining": 0,
      "retries_remaining": 0
    }
  },

  // === Execution (present only if action=allow or action=transform) ===
  "execution": {
    "status": "success | failure | timeout | skipped",
    "attempt": 1,                    // Attempt number (1-indexed; >1 means retry)
    "effect_summary": "string",      // Optional: what changed (max 256 chars, sanitized)
    "side_effects": ["string"],      // Observed side effects (sorted, unique; see Effects Vocab)
    "effects_confidence": "string",  // "none" | "coarse" | "instrumented"
    "result_hash": "string",        // Optional: SHA-256 of redacted/normalized result
    "result_summary": "string",     // Optional: short summary of result (max 256 chars, sanitized)
    "duration_ms": 0,               // Optional: how long execution took
    "error": "string"               // Optional: error message if status=failure (max 256 chars, sanitized)
  },

  // === Provenance ===
  "provenance": {
    "deployment_id": "string",       // Stable across replicas of the same governor deployment
    "instance_id": "string",         // Unique per process (disambiguates replicas)
    "governor_version": "string",    // Governor software version
    "hash_alg": "sha-256",          // Hash algorithm used throughout this receipt
    "hash_encoding": "hex",         // Encoding of all hash values: "hex" (lowercase)
    "signature": "string",          // Optional: signature over receipt_hash
    "signature_alg": "string",      // Optional: e.g. "ed25519"
    "signature_encoding": "string", // Optional: "base64url"
    "signing_key_id": "string"      // Optional: key identifier for verification
  },

  // === Extension ===
  "ext": {}
  // Vendor/project-specific fields. Keys MUST be namespaced: "vendor.field"
  // e.g. "acme.trace_id": "abc123"
  // Ext fields are INCLUDED in canonical form and hashing.
  // Schema uses additionalProperties: false at top level; ext is the only escape hatch.
}
```

### Schema Constraints

- **`additionalProperties: false`** at the top level. No ad-hoc keys.
  All extensions go in `ext` with namespaced keys.
- **Unset optional fields are omitted, not null.** If a field is not
  applicable, do not include it. Do not set it to `null`. Hash and
  canonicalize only what is present. (See Canonicalization.)
- **String length caps on human-readable fields:**
  - `reason_human`: max 256 characters
  - `args_summary`: max 256 characters
  - `effect_summary`: max 256 characters
  - `result_summary`: max 256 characters
  - `error`: max 256 characters
  These are the "oops we logged the secret" fields. Keep them short and
  sanitized. Emitters MUST NOT echo raw args or raw output into these fields.

---

## Field Semantics

### `decision.action` enum
- **`allow`**: Tool call permitted as-is. Execution proceeds with original args.
- **`deny`**: Tool call rejected. No execution. Receipt records why.
- **`transform`**: Tool call permitted with modified args (e.g., scope narrowed,
  sensitive params redacted, timeout injected). `transformed_args_hash` records
  what actually executed.
- **`escalate`**: Decision deferred to human or higher-authority policy layer.
  Execution blocked pending resolution. A follow-up receipt records the outcome.

### `decision.reason_code` (namespaced, extensible)

Built-in codes use the `gov.` namespace. Third-party codes MUST use their
own namespace (e.g., `acme.custom_deny`).

```
gov.scope_exceeded          # Agent claimed capability it doesn't have
gov.budget_exhausted        # Cost/rate/retry budget depleted
gov.policy_deny             # Explicit deny rule matched
gov.no_capability           # No capability token presented
gov.transform_applied       # Args modified to fit policy constraints
gov.escalate_required       # Policy requires human/elevated review
gov.tool_unknown            # Tool not in approved registry
gov.tool_deprecated         # Tool version known-vulnerable or sunset
gov.tool_unavailable        # Tool was removed/unreachable from upstream
gov.passthrough             # No policy matched; default-allow applied (WARN-worthy)
```

### `args_hash` vs raw args
**CRITICAL:** Receipts MUST NEVER contain raw tool arguments. Tool args
frequently contain secrets, tokens, PII, file contents, credentials.

The receipt stores:
- `args_hash`: Domain-separated hash of canonical args (see Hashing)
- `args_summary`: Optional human-readable gloss ("read file: /etc/config")
  MUST be sanitized — no raw arg values echoed.
- Raw args are stored separately in a local secure log if needed, never in
  the receipt chain itself.

### `side_effects` vocabulary (initial set, extensible)

Values in `side_effects` MUST be unique and sorted lexicographically before
inclusion in the receipt. This ensures hash stability across emitters.

```
cred:access              # Credential store accessed
env:read                 # Environment variable accessed
env:write                # Environment variable modified
fs:delete                # File/directory deleted
fs:read                  # File/directory read
fs:write                 # File/directory created or modified
msg:send                 # Message sent (email, chat, etc.)
net:listen               # Network listener opened
net:outbound             # Outbound network request made
proc:signal              # Signal sent to process
proc:spawn               # Subprocess created
state:modify             # Internal agent state modified
```

Custom effect codes MUST be namespaced: `acme:custom_effect`.

### `effects_confidence`
- **`none`**: No observation mechanism; effects are best-guess or declared by
  the tool server (untrusted).
- **`coarse`**: Effects inferred from tool metadata or operator-supplied
  registry (not directly observed).
- **`instrumented`**: Effects observed by the governor via syscall/network
  monitoring or sandbox telemetry.

---

## Ordering and Sequencing

### `chain.seq`
- Integer sequence number, 1-indexed, monotonically increasing.
- **Scope:** per `(actor.session_id, provenance.deployment_id)` pair.
- Resets are allowed across sessions. Within a session, gaps indicate
  missing receipts.
- Auditors prefer "receipt #347" over timestamp comparison. `seq` is the
  primary ordering field.

### `timestamp_mono`
- Optional monotonic counter (e.g., `time.monotonic_ns()` in Python).
- Scope: per `provenance.instance_id`.
- Useful for ordering within a single process; NOT reliable across processes
  or restarts. Not used for chain verification.
- If present, must be non-decreasing within an instance.

### `timestamp_wall`
- ISO 8601 UTC. Human-readable. Subject to clock skew.
- Required for human audit trails. Not used for chain verification.

### Restart behavior
- `chain.seq` continues from last known value if session persists across
  restart. If session is new, seq starts at 1.
- `timestamp_mono` may reset on process restart (it's per-instance).
  This is expected and not a chain integrity violation.

---

## Hashing

### Domain Separation

All hashes include a domain prefix to prevent cross-context collisions.

```
args_hash = SHA-256("args-v1\0" + tool.tool_id + "\0" + JCS(args))

transformed_args_hash = SHA-256("args-v1\0" + tool.tool_id + "\0" + JCS(transformed_args))

result_hash = SHA-256("result-v1\0" + tool.tool_id + "\0" + JCS(redacted_result))

receipt_hash = SHA-256("receipt-v1\0" + JCS(receipt_without_hash_and_signature))
```

- `\0` is the null byte, used as an unambiguous separator.
- `tool.tool_id` in the args hash means the same args to different tools
  produce different hashes. This is intentional.

### Hash Algorithm and Encoding
- **Algorithm:** SHA-256 (recorded in `provenance.hash_alg`)
- **Encoding:** Lowercase hexadecimal (recorded in `provenance.hash_encoding`)
- Future versions may support other algorithms. v1 mandates SHA-256 + hex.

### What is excluded from `receipt_hash`
The following fields are computed from or over the receipt and therefore
cannot be included in the hash of the receipt:
- `receipt_hash` (self-referential)
- `provenance.signature` (signs the hash)
- `provenance.signature_alg` (part of signature metadata)
- `provenance.signature_encoding` (part of signature metadata)
- `provenance.signing_key_id` (part of signature metadata)

All other fields (including `ext`) ARE included in the canonical form and
therefore in the hash.

---

## Canonicalization Rules

### JSON Canonicalization
- Use RFC 8785 (JCS — JSON Canonicalization Scheme)
- All fields sorted lexicographically by key at each nesting level
- No whitespace between tokens
- Numbers as shortest representation (no trailing zeros)
- Strings as UTF-8 with minimal escaping

### Optional Field Handling
- **Unset optional fields are omitted.** Do not include them. Do not set
  them to `null`.
- Hash and canonicalize exactly what is present in the receipt.
- Two receipts with the same present fields and values MUST produce the
  same canonical form regardless of emitter implementation.

### Array Handling
- Arrays with set semantics (e.g., `side_effects`) MUST be deduplicated
  and sorted lexicographically before inclusion.
- Arrays with ordered semantics (e.g., `decision.policy_path`) preserve
  their order.
- The schema should document which arrays are sets and which are ordered.

### Chain Integrity Verification
```
For each receipt R[i] where i > 0:
  assert R[i].chain.parent_receipt_id == R[i-1].receipt_id
  assert R[i].chain.parent_receipt_hash == R[i-1].receipt_hash
  assert R[i].chain.seq == R[i-1].chain.seq + 1  (within same session)
  recompute R[i].receipt_hash from canonical form; assert match
```

Verification walks **hash pointers**, not IDs. The hash chain is integrity;
`receipt_id` is indexing. A valid ID with a mismatched hash is a tamper signal.

---

## Signature Story (v1: optional; v2: mandatory)

### What is signed
`provenance.signature` covers `receipt_hash` (not raw JSON).

```
signature = Sign(signing_key, "receipt-sig-v1\0" + receipt_hash)
```

Domain prefix prevents signature reuse across contexts.

### Metadata fields (present when signature is present)
- `provenance.signature_alg`: e.g., `"ed25519"`
- `provenance.signature_encoding`: `"base64url"`
- `provenance.signing_key_id`: opaque key identifier for lookup

### v1 posture
Signing is optional in v1. Mandating it blocks adoption (key management
complexity). Ship with the fields defined; make signing mandatory in v2
once key distribution patterns emerge from real usage.

---

## Redaction Rules

Receipts will be read by security teams, compliance officers, and audit
tools. They must be safe to store, transmit, and aggregate.

### MUST redact (never in receipt)
- Raw tool arguments
- Secrets, tokens, API keys, passwords, bearer tokens
- PII (names, emails, phone numbers, SSNs)
- File contents
- Raw model outputs / prompts

### MAY include (operator discretion)
- File paths (may reveal project structure — configurable)
- Tool names and versions
- Arg summaries (MUST be sanitized, max 256 chars)
- Error messages (MUST be sanitized, max 256 chars)

### Redaction is the emitter's responsibility
The receipt schema defines what CAN appear. The emitter (governor
implementation) is responsible for ensuring nothing else leaks in.
A receipt that contains raw secrets is a bug in the emitter, not a
schema problem.

---

## Deliverables

### 1. Schema file
`receipt.schema.json` — JSON Schema (draft 2020-12) for Receipt v1.
- `additionalProperties: false` at top level
- `ext` is the only open object
- Must be usable for validation by any JSON Schema library

### 2. Golden examples (10)
```
examples/
  01_allow_simple.json          # Basic allow: read a file, no issues
  02_deny_scope.json            # Deny: agent exceeded declared scope
  03_deny_budget.json           # Deny: retry budget exhausted
  04_transform_narrow.json      # Transform: args narrowed to allowed scope
  05_escalate_human.json        # Escalate: requires human approval
  06_allow_with_effects.json    # Allow with side effects + confidence level
  07_chain_two.json             # Two receipts chained (hash + ID linkage)
  08_deny_unknown_tool.json     # Deny: tool not in approved set
  09_allow_passthrough_warn.json # Allow via default-allow (WARN)
  10_execution_failure.json     # Allowed but execution failed + retry
```

Each example must:
- Validate against the schema
- Have a correct `receipt_hash` (verifiable by the verification script)
- Have correct `parent_receipt_hash` chain (where applicable)
- Have `side_effects` sorted and deduplicated
- Omit (not null) all inapplicable optional fields

### 3. Emitter libraries (minimal)

**Python:**
```python
from agent_gov.receipt import Receipt, emit

r = Receipt(
    tool_id="fs.read",
    args={"path": "/etc/config"},  # hashed with domain separation internally
    decision="allow",
    reason_code="gov.passthrough",
    effects=["fs:read"],
    effects_confidence="coarse",
)
emit(r)  # writes to configured sink; auto-chains to previous receipt
```

**TypeScript:**
```typescript
import { Receipt, emit } from '@agent-gov/receipt';

const r = new Receipt({
    toolId: 'fs.read',
    args: { path: '/etc/config' },  // hashed internally
    decision: 'allow',
    reasonCode: 'gov.passthrough',
    effects: ['fs:read'],
    effectsConfidence: 'coarse',
});
await emit(r);
```

Both libs must:
- Canonicalize per RFC 8785
- Domain-separate all hashes
- Auto-sort set-semantic arrays
- Chain to previous receipt automatically (hash + ID + seq)
- Omit unset optional fields (never emit null)
- Never serialize raw args into the receipt
- Enforce string length caps on human-readable fields
- Be < 500 LOC each (this is a format lib, not a framework)

### 4. Verification script
```bash
# Verify a single receipt
$ gov-receipt verify receipt.json
✓ Schema valid
✓ Hash matches (domain-separated, recomputed)
✓ No raw secrets detected (heuristic)
✓ Side effects sorted and unique
✓ String length caps respected

# Verify a chain
$ gov-receipt verify-chain receipts/
✓ 47 receipts
✓ Chain integrity: all parent hash pointers valid
✓ Sequence numbers: monotonic, no gaps
✗ Gap detected: seq 23 → 25 (receipt 24 missing)

# Verify signature (if present)
$ gov-receipt verify-sig receipt.json --keyring keys/
✓ Signature valid (ed25519, key: gov-prod-2026-02)
```

---

## Open Questions

1. **Receipt storage/transport:** Schema defines the format. Where receipts
   *go* (local file, syslog, SIEM, S3, etc.) is an operator concern, not
   a schema concern. Emitter libs should support pluggable sinks but ship
   with file + stdout.

2. **Receipt size budget:** With hashing instead of raw args, receipts
   should be small (< 2KB typical). Set a soft ceiling at 4KB and WARN
   if exceeded — bloated receipts usually mean something is leaking in
   that shouldn't be.

3. **Aggregation / query:** Out of scope for v1. Once receipts exist in
   the wild, query patterns will emerge. Don't prematurely build a
   dashboard.

4. **Multi-tool transactions:** Some agent actions involve multiple tool
   calls as a logical unit. v1 handles this via chain (each call gets
   its own receipt, linked by parent hash + seq). Explicit transaction
   grouping is a v2 concern.

5. **Interop with existing audit formats:** OCSF, CEF, STIX — these
   exist and enterprises use them. v1 should be *mappable* to these
   but not constrained by them. Ship a mapping doc, not a native
   dual-format emitter.

6. **Identity federation:** `actor.issuer` + `actor.auth_context` are
   placeholders for multi-tenant identity. Full identity federation
   (OIDC discovery, key rotation, trust chains) is a v2 concern. v1
   ships with stdio single-tenant as the default.

7. **The meta-risk:** Receipt v1 is itself a reconciliation mechanism.
   It can enter capture if receipts become performative — emitted but
   never read, never verified, never used to make decisions. Mitigation:
   the verification tooling ships with the schema, not as an afterthought.
   If you can emit but not verify, the receipts are incense.
