# Claim↔Receipt Correlation

Status is derived, not authoritative.

## What is a "claim"?

A lightweight assertion extracted by the evidence gate (or another gate)
during output validation. Not the full epistemic ledger — just what the
gate saw and what receipts it produced.

## How linkage works

Claims and receipts are stored in separate JSONL files:
- `{gov_dir}/claims/claims.jsonl` — claim records
- `{gov_dir}/claims/links.jsonl` — claim↔receipt junction

Receipts are NOT modified. Linkage is external (junction store).
Same receipt can link to multiple claims with different roles.

## Idempotency

- **claim_key** = H(source_gate + run_id + normalized_text + level) — dedup on replay
- **link triple** = (claim_id, receipt_id, role) — dedup on re-link

## Verification statuses (derived)

| Status | Meaning |
|--------|---------|
| UNVERIFIED | No receipts linked |
| PARTIAL | Some support but incomplete (warn-only, bad chain, unresolved) |
| VERIFIED | Supporting receipt with verdict=pass AND chain OK |
| CONTRADICTED | Explicit contradiction role OR receipt verdict=block |

## Role semantics

- `supports`: receipt verdict is "pass" or "warn" for this claim
- `contradicts`: receipt conflicts (explicit contradiction or verdict "block")
- `neutral`: receipt is related but doesn't speak to truth value

## Sort order contract

- `claims.list`: newest first
- `get_links`: oldest first (causal order)
- `window` claims: newest first; receipt stubs: oldest first

## Retention

Claims/links follow receipt lifecycle. No independent rotation in v1.
When receipts age out, linked refs become unresolved (counted, not crashed).

## RPC methods (daemon)

| Method | Description |
|--------|-------------|
| `claims.list` | Filterable list with verification summaries |
| `claims.detail` | Single claim + links + receipt stubs |
| `claims.for_receipt` | Reverse lookup: claims for a receipt |
| `claims.window` | Time-window bundle for timeline rendering |
| `claims.stats` | Quick rollup (total, by level, links) |

## What this is NOT

- Not the full epistemic ledger (GroundedClaim, provenance, etc.)
- Not a trust score or confidence metric
- Not NLP-based claim extraction — uses evidence gate's existing patterns
- Not a modification to receipt identity (receipts untouched)
