# 0002 — Gate, Not Memory

## Status

Accepted

## Context

Most governance tools for AI agents are advisory: they log what happened, flag potential issues, and hope the agent (or user) pays attention. This is the "memory" model — the system remembers decisions and violations, but doesn't prevent them.

The problem: advisory tools get ignored. A warning that can be bypassed will be bypassed, either by the agent optimizing for task completion or by a user who doesn't want to deal with friction.

```python
# Advisory — can be ignored
if not governor.approve(patch):
    logger.warning("Governor rejected patch")
    apply_patch_anyway(patch)  # nothing stops this
```

Additionally, when governance is visible in output (e.g., "I need to be careful here," "I can't joke about that"), it signals external control and breaks trust. In fiction, the audience detects filtering. In code, the developer suspects the tool is hedging. In nonfiction, the reader senses predetermined conclusions.

## Decision

The governor is a **gate**, not a **memory**. The goal is write-blocking, not advisory logging.

- No file mutations without verified proposals
- Pre-commit hook enforces this
- If verification fails, the proposed change dies — there is no "try anyway" path
- Governance never surfaces in-band (the output never reveals that a constraint triggered)

```python
# Gate — mandatory
if not governor.approve(patch):
    raise GovernorRejection(patch, reason)
```

When a proposal fails verification, it doesn't get logged with a warning and applied anyway. It simply doesn't reach the apply stage. The gate is upstream of the agent's output.

## Consequences

- **Fail-closed by default.** Verification failure blocks the action. The only override is explicit human intervention with a receipt.
- **Governance is invisible when working correctly.** Suppressed changes don't appear as "rejected" in output. They never reach the apply stage. No announcement of what was blocked.
- **Transactional atomicity is mandatory.** Check-then-act without atomicity allows TOCTOU races. The gate must be atomic: verify and commit in a single transaction, or neither.
- **Agents must be honest proposers, not strategists.** They can't game the gate by proposing increasingly aggressive changes and watching what sticks. The gate is upstream of their rhetoric.
- **The system is a constraint, not a suggestion.** This is the polarity flip from every other AI governance tool. Most tools advise. This one blocks.

## Source

- `CLAUDE.md` ("Gate, not memory. The goal is write-blocking, not advisory logging.")
- `specs/core/AUTHORIAL_CONTROL_SYSTEM_SPEC.md` ("Invariant #1: Governance Never Surfaces In-Band.")
