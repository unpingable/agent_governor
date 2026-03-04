# GOV-PRIM-PROV-001: Provenance Labels for Tool Outputs

Status: `shipped` (v2.5.0 — `provenance_labels.py`, 53 tests)

## Problem

Tool outputs enter the governor's world unlabeled. A file read, a web fetch,
a shell command result — they all arrive as undifferentiated text. The governor
cannot distinguish "output from reading secrets.env" from "output from reading
README.md" once the tool call completes.

Without provenance labels, downstream gates (egress, chain, evidence) cannot
make informed decisions about data sensitivity, trust level, or appropriate
handling.

This is the plumbing that makes GOV-GAP-CHAIN-001 and GOV-GAP-EGRESS-001
effective. Without labels, those gates are blind.

## What This Is

Lightweight taint tracking. Tool outputs carry provenance labels that
propagate through the action chain. Not information-flow control (no
formal lattice). Not DLP. Just enough metadata to make downstream gates
useful.

## Label Schema

```python
class ProvenanceLabel:
    source_class: str       # "repo" | "email" | "web" | "secret_store" | "user_input" | "generated"
    sensitivity_hint: str   # "none" | "internal" | "secret_candidate" | "unknown"
    tool_id: str            # which tool produced this output
    timestamp: str          # ISO 8601 UTC
    content_hash: str       # H(output_content) for dedup/tracking
```

### Source classes

| Class | Meaning | Default sensitivity |
|-------|---------|-------------------|
| `repo` | Local repository file | `internal` |
| `email` | Email content | `internal` |
| `web` | Public web content | `none` |
| `secret_store` | Credentials, env vars, key files | `secret_candidate` |
| `user_input` | Direct human input | `none` |
| `generated` | Model-generated content | `none` |
| `unknown` | Cannot determine source | `unknown` (treated as sensitive) |

### Sensitivity hints

Tools may add sensitivity hints based on mechanical inspection:

- File path matches secret patterns (`.env`, `credentials.*`, `*_key.*`) → `secret_candidate`
- File path in restricted scope → `internal`
- URL is internal hostname → `internal`
- Otherwise → source class default

Hints are *metadata*, not policy decisions. Policy is in the egress/chain gates.

## Propagation Rules

### v1: Simple taint propagation

1. Tool output gets a label at creation time (mechanical, based on tool + args)
2. If model transforms labeled data → output inherits the **highest sensitivity**
   of all inputs (conservative propagation)
3. Labels are carried in the action log (same structure as chain gate's ActionStep)
4. Egress gate reads labels to classify payload

### What propagation does NOT do in v1

- No taint declassification (only human override can lower sensitivity)
- No formal information-flow lattice
- No cross-session label tracking
- No label on model-internal reasoning (only tool I/O boundaries)

## Integration Points

### Chain gate (GOV-GAP-CHAIN-001)

ActionStep annotation includes provenance labels. The chain gate's
`data_sensitivity` field is derived from the provenance label's
`sensitivity_hint`.

### Egress gate (GOV-GAP-EGRESS-001)

EgressRequest's `payload_class` is derived from the provenance labels
of the data being sent. If any input label has `secret_candidate` →
payload_class = `secret`.

### Evidence gate

Evidence blobs can carry provenance labels. When the evidence gate
evaluates a claim, the label on the supporting evidence affects
confidence (evidence from `secret_store` has different trust properties
than evidence from `repo`).

### Receipt emission

Labels appear in receipts as metadata. Receipt identity (content-addressed
hash) does NOT include labels — labels are annotation, not identity.

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| Receipt kernel redaction | 13 secret patterns — reuse for sensitivity hint assignment |
| Evidence store | Content-addressed blobs — labels attach as sidecar metadata |
| Scope governor | Axis-based containment — labels are orthogonal (content vs location) |
| Input provenance (ETHICAL_HARDENING §2) | Broader classification — labels are the primitive |

## v2 vs v3

**v2 (now):** Label schema. Mechanical assignment at tool output boundary.
Simple taint propagation (highest sensitivity wins). Labels in action log.
Egress gate consumes labels.

**v3 (later):** Cross-session label tracking. Label declassification workflow.
Formal sensitivity lattice. Aggregate label analytics. Integration with
organizational data classification systems.

## Implementation Sketch

1. `src/governor/provenance_labels.py` — ProvenanceLabel, LabelAssigner, PropagationRule
2. LabelAssigner: tool_id + args → ProvenanceLabel (mechanical, rule-based)
3. Wire into ActionStep (chain gate) and EgressRequest (egress gate)
4. Reuse `receipt_kernel/redact.py` patterns for secret detection
5. Labels stored as sidecar in action log, not in receipt identity hash

## Tests (minimum)

- File read of `.env` → sensitivity_hint = `secret_candidate`
- File read of `README.md` → sensitivity_hint = `internal` (repo default)
- Web fetch → sensitivity_hint = `none`
- Unknown tool → sensitivity_hint = `unknown`
- Propagation: `secret_candidate` input + `none` input → output = `secret_candidate`
- Label assignment is deterministic (same tool + args → same label)
- Labels round-trip through serialization
- Labels do not affect receipt identity hash
