# 0001 — Proposal/Commit Split

## Status

Accepted

## Context

The governor needs to enforce constraints on AI agent behavior. The fundamental question: when should enforcement happen?

Two models exist:

1. **Advisory logging**: Agent acts, governor logs approval/rejection after the fact. Agent can ignore rejections.
2. **Write-blocking gate**: Agent proposes, governor verifies independently, only verified proposals can be applied.

Advisory logging fails because warnings can be ignored:

```python
# Advisory — agent can override
if not governor.approve(patch):
    logger.warning("Governor rejected patch")
    apply_patch_anyway(patch)  # oops
```

The agent can claim "tests pass" and immediately write code. Without a mandatory verification step, the governor is just a suggestion engine.

## Decision

Proposals and commits are separate stages enforced by a four-state FSM:

```
DRAFT ──propose──> PROPOSED ──verify──> VERIFIED ──apply──> APPLIED
  ^                    |                    |
  |                    | reject             | conflict
  +--------------------+--------------------+
```

- **DRAFT**: Agent speculation. Nothing persistent. Expires.
- **PROPOSED**: Structured claims + pointers submitted. Waiting for governor verification.
- **VERIFIED**: Governor has run checks and produced receipts. Ready to apply.
- **APPLIED**: Patch written to working tree. Facts/decisions updated.

The FSM enforces that you cannot skip VERIFY to reach APPLIED. The governor produces receipts (FileSnapshot, CmdRun, DiffReceipt) as cryptographic proof of verification. Agents provide pointers (file paths, commands to run), never evidence.

**"Proposal is cheap. Commitment isn't."**

## Consequences

- **Claims must be typed, not prose.** `ClaimType.TESTS_PASS` with a command pointer, not "I think the tests pass." Machine-checkable claims enable independent verification.
- **Two ledgers emerge.** Facts (empirical, auto-decay when files change) vs decisions (normative, persist until revised). The split separates what can be re-verified from what requires deliberate change.
- **Every action has a receipt.** No action occurs without a receipt in the ledger proving it happened. This is the foundation of accountability.
- **The governor is a choke point.** All mutations flow through the governor. This is the design intent — not a bottleneck, but the enforcement boundary.
- **Reversibility is visible.** The propose/preview/confirm/commit chain makes every step explicit. Users see what will happen before it happens.

## Source

- `BUILD_SPEC.md` (FSM definition, receipt types, "agent provides pointers, governor produces receipts")
- `specs/core/GOVERNOR_VOICE_PROFILE_SPEC.md` (voice contract: "Proposal is cheap. Commitment isn't.")
