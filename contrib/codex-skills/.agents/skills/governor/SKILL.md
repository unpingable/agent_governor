---
name: governor
description: Use this skill when a task involves code edits, shell commands, protected files, risky operations, or completion verification in a repository governed by policy receipts.
---

# Governor workflow

Use the governor MCP tools to enforce policy and create receipts.

## Before risky actions

Run a governor policy check before:
- shell commands that mutate repo state
- edits under protected paths
- dependency changes
- git commit / push
- release, CI, migration, or config changes

## After material changes

Emit a receipt summarizing:
- files changed (paths and content hashes)
- commands run (command and exit code)
- policy lane and regime
- any violations or exceptions
- justification for protected-path changes

## Before marking work complete

Verify:
- no unresolved governor violations
- required receipts exist for material changes
- repo state satisfies local policy gates

## MCP tools

Use these governor MCP tools when available:
- `governor.check_policy` — evaluate action against policy
- `governor.write_receipt` — emit receipt for completed action
- `governor.list_violations` — show unresolved violations
- `governor.explain_denial` — explain why an action was denied
- `governor.appeal` — file exception with justification
- `governor.verify_completion` — check task completion conditions

## On denial

If governor denies an action:
1. Summarize the denial plainly
2. Propose the least-invasive compliant alternative
3. Appeal only with specific justification and bounded scope
4. Never bypass or ignore a governor denial
