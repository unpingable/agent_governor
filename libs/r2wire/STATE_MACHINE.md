# R2-WIRE vs receipt_kernel: same state machine, different granularity

receipt_kernel is the enforcement kernel (admissibility + stage progression).
R2-WIRE is the typed event language (what can be said / committed / executed).

## Stage mapping

| receipt_kernel stage | R2-WIRE opcodes            | Notes                              |
|---------------------|----------------------------|------------------------------------|
| START / COLLECT     | PROPOSE                    | Plan + preconditions + asks        |
| EVALUATE / DECIDE   | COMMIT or VETO             | Scoped approval or rejection       |
| (execution)         | TOOL + RESULT              | Invocation + outcome               |
| REMEDIATE           | PROPOSE (revised)          | Loop back with new plan            |
| FINALIZE            | CHECKPOINT (future opcode) | Receipt finalization               |

## Shared invariants

1. **No TOOL without COMMIT.** Maps to receipt_kernel's "no execution without
   DECIDE stage." The COMMIT is the decision receipt.

2. **Canonical JSON bytes must match.** `r2wire.canonical.canonical_json_bytes(obj, nfc=False)`
   must produce byte-identical output to `receipt_kernel.envelope.canonical_json(obj)`.
   Golden vectors in `tests/data/canonical_vectors.json` enforce this.

3. **Hash refs are content-addressed and immutable.** Both use `sha256:{hex}`.

## What R2-WIRE adds (not present in receipt_kernel)

- **Typed bodies per opcode** (PROPOSE has steps/preconds, COMMIT has scope/budget/expiry).
- **Budget enforcement on COMMIT** (token limits, tool_call limits, expiry).
- **Scope grants** (COMMIT.scope_grant must cover PROPOSE.preconds[kind=SCOPE].need).
- **No floats** (timestamps are epoch ints, budgets are ints, no IEEE-754 ambiguity).

## What receipt_kernel adds (not present in R2-WIRE)

- **Hash-chained event ledger** (prev_event_hash linking).
- **Stage graph with hard-fail transitions** (illegal stage sequences rejected).
- **Content-addressed blob store with redaction hooks**.
- **6 constitutional invariants** (chain_valid, receipt_completeness, etc.).
- **Retention policy** (TTL-based expiry, sealed evidence classes).

## Design intent

R2-WIRE is the wire format. receipt_kernel is the audit backend. An event
expressed as R2-WIRE can be *recorded* in receipt_kernel. The two should
converge on shared primitives (canonical JSON, hash refs) but remain
separately usable.
