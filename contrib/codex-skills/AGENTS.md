# Governor contract

This repository uses governor for policy checks and receipts.

## Requirements

- Before risky shell actions, run a governor policy check.
- After material edits, emit a governor receipt.
- Do not modify protected paths without explicit justification.
- Do not claim completion if governor reports unresolved violations.

## Protected paths (examples)

Edits to these paths require governor justification:
- `migrations/`
- `ci/`
- `policy/`
- `release/`
- `.governor/`

## Principle

Language is a proposal, not an authority (NLAI). Agents provide pointers;
governor produces receipts. Never claim evidence — let governor verify.
