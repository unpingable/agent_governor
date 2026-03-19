# Dogfood Report 001: Runtime Supervisor

**Date:** 2026-03-16 through 2026-03-19
**Subject:** Supervised Claude Code sessions via `src/governor/runtime/`
**Backend:** Claude Code 2.1.76, `--print` mode, `--dangerously-skip-permissions`
**Operator mode:** interactive (write tools require approval)

## Summary

Five supervised sessions were run against real Claude Code instances. The runtime supervisor successfully intercepted tool calls, created interventions for write-capable tools, auto-approved reads, honored operator approve/deny decisions, enforced timeouts, and maintained a canonical event stream throughout.

**Verdict: The membrane works.**

## Test Matrix

| # | Scenario | Interventions | Outcome |
|---|----------|--------------|---------|
| 1 | Trivial (echo hello) | 0 (autonomous mode) | Clean exit, output captured |
| 2 | Real coding (add function + tests) | 2 approve (Edit, Write) | Working code, tests pass |
| 3 | Mixed policy (deny Bash, approve Write) | 1 deny, 1 approve | Claude adapted, used Read instead of Bash |
| 4 | Deny everything | 1 deny (Edit) | Claude explained denial, exited cleanly, no workspace mutation |
| 5 | Timeout (10s) | 2 timeouts (Edit × 2) | Both timed out, denied, Claude exited cleanly |

## Event Traces

### Test 2: Real Coding Task (19 events)
```
session_created → launching → attached → running
→ tool_call_proposed [Read]     (auto-approved)
→ tool_call_completed [Read]
→ tool_call_proposed [Edit]     → operator_prompted → APPROVED → completed
→ tool_call_proposed [Write]    → operator_prompted → APPROVED → completed
→ agent_output "Done."
→ session_exited
```

### Test 3: Mixed Policy — Bash Denied (25 events)
```
→ tool_call_proposed [Read] × 2 (auto-approved)
→ tool_call_proposed [Bash]     → operator_prompted → DENIED "not permitted"
→ tool_call_proposed [Write]    → operator_prompted → APPROVED → completed
→ agent_output "The cat .env bash command was blocked... I verified via Read tool"
→ session_exited
```

### Test 5: Timeout (18 events)
```
→ tool_call_proposed [Read]     (auto-approved)
→ tool_call_proposed [Edit]     → 10s countdown → DENIED "Intervention timeout"
→ tool_call_proposed [Edit]     → 10s countdown → DENIED "Intervention timeout"
→ agent_output "The edit is being repeatedly blocked..."
→ session_exited
```

## Bugs Found and Fixed

### During initial dogfooding (2026-03-16)

| Bug | Severity | Fix |
|-----|----------|-----|
| stdin must be closed for `--print` mode | Critical — Claude hangs indefinitely | Close stdin after launch when task is provided |
| Hook keys must be PascalCase | Critical — hooks don't fire | `PreToolUse`/`PostToolUse` not `preToolUse`/`postToolUse` |
| Hook format requires matcher nesting | Critical — hooks don't register | `{matcher, hooks: [{type, command, timeout}]}` |
| Socket listener race condition | High — hooks connect before listener ready | Bind socket BEFORE launching Claude |
| Settings merge clobbers existing | Medium — breaks current session | Merge governor hooks into existing settings, restore on shutdown |
| Exit event yield in finally | Medium — exit not detected | Move yield after finally block (generators can't yield in finally) |
| Stale hooks accumulate | Low — cosmetic | Tag with `_governor_supervised`, clean on shutdown |

### During CI fix (2026-03-18)

| Bug | Severity | Fix |
|-----|----------|-----|
| `runtime` CLI group after `_populate_advanced()` | Test failure | Move definition before `_populate_advanced()` |
| 3 spec files missing `status:` line | Test failure | Add `status: draft` metadata |
| f-string without placeholder | Lint failure | Remove extraneous `f` prefix |

## What Works

- **Session lifecycle**: created → launching → attached → running → exited/failed
- **Tool interception**: PreToolUse hooks fire, connect to supervisor socket, receive decisions
- **Auto-approve**: Read-only tools (Read, Glob, Grep) approved without intervention
- **Intervention queue**: Write tools (Bash, Write, Edit) create interventions with countdown
- **Approve**: Operator approval resumes execution, tool completes
- **Deny**: Operator denial blocks tool, Claude receives rejection and adapts
- **Timeout**: Unanswered interventions auto-deny after configurable timeout
- **Graceful recovery**: Claude handles denials and timeouts without crashing or looping
- **Workspace integrity**: Denied operations produce no file changes
- **Event stream**: Monotonic seq, correct pairing, all events persisted to JSONL
- **Post-tool hooks**: PostToolUse fires and records tool completion

## What Doesn't Work Yet

- **Permission model**: Currently requires `--dangerously-skip-permissions` because Claude Code can't grant tool permissions non-interactively in `--print` mode
- **Settings cleanup on crash**: If the supervisor process dies without shutdown, governor hooks persist in `.claude/settings.local.json`
- **Multi-tool-in-flight**: Not tested — Claude Code appears to serialize tool calls in `--print` mode
- **Long sessions**: Not tested beyond ~30s tasks. Memory/event accumulation untested at scale
- **Promotion queue**: Not implemented yet (Phase 1)
- **Edit-resubmit**: Not implemented yet (Phase 1)

## Architecture Observations

1. **Claude handles denial intelligently.** When Bash was denied, Claude fell back to the Read tool. When Edit was denied, Claude explained the situation and exited. No infinite retry loops.

2. **The hook socket design works but is fragile.** Unix domain sockets with JSON framing are reliable for the happy path. Crash cleanup is the weakness — see "stale hooks" bug above.

3. **`--print` mode is the right fit for supervised sessions.** Non-interactive, captures output, exits when done. But it requires `--dangerously-skip-permissions` which is not ideal for real use.

4. **Event stream is readable.** The canonical event taxonomy (proposed → prompted → allowed/denied → completed) maps cleanly to what the operator needs to know. No noise.

5. **Timeout-default-deny is correct for writes.** Both timeout tests resulted in no workspace changes. The conservative default prevents unattended sessions from making unsupervised modifications.

## Metrics

| Metric | Value |
|--------|-------|
| Total dogfood sessions | 5 |
| Total events produced | ~75 |
| Total interventions | 7 |
| Approvals | 3 |
| Denials | 2 |
| Timeouts | 2 |
| Bugs found | 10 |
| Bugs fixed | 10 |
| Runtime tests | 49 |
| Workspace mutations from denied ops | 0 |

## Next Steps

1. **Harden settings cleanup** — atexit handler or `governor runtime cleanup` command
2. **Permission model** — explore `--permission-mode` options for supervised print mode
3. **Dogfood longer sessions** — multi-file refactoring, 5+ minute tasks
4. **Phase 1: Promotions** — git diff workspace detection, diff view, operator approve/reject of accumulated changes
5. **Maude integration testing** — run supervised commands through Maude → daemon → supervisor → Claude
