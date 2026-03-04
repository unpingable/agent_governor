# GOV-GAP-EGRESS-001: Outbound Data-Flow Policy Gate

Status: `shipped` (v2.5.0 — `egress_gate.py`, 66 tests)

## Problem

Current governance asks "is this tool allowed?" but not "what data is leaving,
where is it going, and what transformation path produced it?"

A model with network tool access can exfiltrate context, secrets, or
proprietary code. Even without malice, models routinely send more context
than necessary in API calls, webhook payloads, or error reports.

The governor has no egress gate — no point where outbound data flow is
evaluated against policy before it leaves the trust boundary.

## What This Is NOT

- Not a network firewall (operates at the governance layer, not packet level)
- Not DLP (no content classification ML)
- Not blocking all network access

It is a **structured policy gate** on outbound data flow: destination +
payload class + provenance + justification.

## Minimal v1 Policy Fields

Each outbound data-flow request is evaluated against:

```python
@dataclass
class EgressRequest:
    destination_class: str    # "internal" | "same_org" | "external" | "unknown"
    destination_identity: str # URL, hostname, or service name
    payload_class: str        # "public" | "internal" | "sensitive" | "secret"
    payload_size: int         # bytes
    provenance_refs: list[str]  # receipt IDs or evidence hashes that justify this data
    justification_code: str   # "api_call" | "webhook" | "error_report" | "user_requested"
    approval_mode: str        # "auto" | "receipted" | "human_required"
```

### Policy rules (v1 starter set)

```
# Secrets never leave
DENY  payload_class=secret  →  ANY_DESTINATION

# Sensitive data requires receipted justification
DENY  payload_class=sensitive  →  destination_class=external  UNLESS  approval_mode=human_required

# Unknown destinations are blocked
DENY  destination_class=unknown  →  ANY_PAYLOAD

# Internal→internal is allowed with receipt
ALLOW  destination_class=internal  →  payload_class!=secret  WITH  receipt
```

### Payload classification

v1: mechanical, not ML.
- `secret`: matches secret patterns (reuse redaction hook's 13 patterns from receipt_kernel)
- `sensitive`: contains file paths from restricted scope, or provenance-tagged internal data
- `internal`: general workspace content
- `public`: explicitly marked public (e.g., open-source code, public API responses)

If classification is ambiguous → `sensitive` (fail-safe upward).

## Gate Integration

- Hook point: before any outbound network call (http_post, webhook, API call)
- The egress gate evaluates the EgressRequest against policy
- Verdict: ALLOW / DENY / ESCALATE
- Receipt: gate="egress_policy", includes destination_hash + payload_class + rule_id

### What the receipt captures

- `destination_hash`: H(destination_class + destination_identity)
- `payload_class`: classification result
- `payload_size`: bytes
- `provenance_chain`: list of upstream receipt/evidence refs
- `rule_matched`: which policy rule triggered
- `verdict`: ALLOW / DENY / ESCALATE
- `redactions_applied`: count of secrets redacted before transmission (if applicable)

## Relationship to Chain Gate (GOV-GAP-CHAIN-001)

The chain gate catches `read_secret → send_external` as a denied composition.
The egress gate catches `send_external(payload=secret_content)` regardless of
how the payload was assembled. They are complementary:

- Chain gate: sequence-aware, catches the *path* to exfiltration
- Egress gate: payload-aware, catches the *content* at the boundary

Both should fire. Belt and suspenders.

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| Scope governor | Constrains where agents act — egress gate constrains what leaves |
| Receipt kernel redaction | 13 secret patterns — reuse for payload classification |
| Evidence gate | Per-action gating — egress gate is per-outbound-flow |
| Codex hooks | Post-hoc event log — egress events should appear here |
| ViolationResolver | Deny path UX — reuse fix/revise/proceed pattern |

## v2 vs v3

**v2 (now):** Egress gate interface. Mechanical payload classification (regex,
not ML). Denied-by-default for secrets. Receipt emission. Policy file.

**v3 (later):** Content-aware classification. Cross-session data flow tracking.
Aggregate egress budgets. Destination reputation scoring. Integration with
organizational DLP systems.

## Implementation Sketch

1. `src/governor/egress_gate.py` — EgressGate, EgressRequest, EgressPolicy, PayloadClassifier
2. Wire into daemon tool dispatch for network-capable tools
3. Reuse `receipt_kernel/redact.py` patterns for secret detection
4. Policy file: `{governor_dir}/egress_policy.json`
5. Receipt emission via gate_receipt pattern
6. CLI: `governor egress status`, `governor egress policy`

## Tests (minimum)

- Secret payload → any destination → DENY
- Sensitive → external without human approval → DENY
- Sensitive → external with human approval → ALLOW + receipted
- Unknown destination → DENY
- Internal → internal with non-secret payload → ALLOW + receipted
- Payload classification: known secret patterns detected
- Payload classification: ambiguous → sensitive (fail-safe)
- Empty policy → DENY all (fail-closed)
- Receipt fields present and schema-valid
