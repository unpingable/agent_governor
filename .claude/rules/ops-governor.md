---
paths:
  - "src/ops_governor/**"
  - "tests/test_ops_*"
---
# Ops Governor

SRE/Operations governance: runbook verification, time window enforcement, blast radius limits, precondition chains.

## Modules

- **types.py** — Runbook, TimeWindow, BlastRadius, Precondition
- **verifiers.py** — RunbookVerifier, TimeWindowVerifier, BlastRadiusVerifier, PreconditionChainVerifier
- **policy.py** — PolicyRegistry, operational policy enforcement
- **cli.py** — ops-gov CLI

**Total: 58 tests**
