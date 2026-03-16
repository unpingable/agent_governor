# Supervised Mode

Governor can launch and supervise external agent runtimes (currently Claude Code) with tool-level interception and operator approval.

## What it is

A supervised session is one agent runtime (e.g., Claude Code) launched as a child process, with governor hooks intercepting tool calls in real time. The operator sees a canonical event stream and can approve, deny, pause, or kill the session.

## Quick start

```bash
# Via CLI
governor runtime launch --task "Fix the failing test in test_claims.py"
governor runtime list
governor runtime events <session_id>
governor runtime interventions <session_id>
governor runtime approve <session_id> <tool_call_id>

# Via Maude
supervised launch Fix the failing test
supervised list
supervised interventions <session_id>
supervised approve <session_id> <tool_call_id>
```

## What counts as an intervention

In **interactive** mode (default), write-capable tools create interventions:
- `Bash`, `Write`, `Edit`, `NotebookEdit`

Read-only tools are auto-approved:
- `Read`, `Glob`, `Grep`, etc.

In **autonomous** mode, all tools are auto-approved.

## Timeout behavior

- Default intervention timeout: **300 seconds**
- On timeout: **deny** for write tools, **allow** for read tools
- Pause freezes the timeout countdown
- Maude shows remaining time on pending interventions

## Operator actions

| Action | What it does |
|--------|-------------|
| approve | Allow the tool call to proceed |
| deny | Block the tool call (agent sees rejection) |
| pause | Soft pause — block all tool approvals, freeze timers |
| resume | Resume from pause |
| kill | Terminate the agent process |

## Event stream

Every supervised session produces a canonical event stream:

```
session_created → launching → attached → running
→ tool_call_proposed [Bash]           ← agent wants to use a tool
→ operator_prompted                    ← intervention created
→ tool_call_allowed / denied           ← operator decision
→ operator_decision                    ← decision recorded
→ tool_call_completed                  ← tool executed
→ agent_output                         ← agent's response
→ session_exited                       ← clean exit
```

Events are persisted to JSONL, queryable by sequence cursor.

## Invariants

1. **Backend is not trusted.** Agent claims are proposals, not authority.
2. **Canonical events are authoritative.** UI renders canonical events, not raw agent output.
3. **No invisible control actions.** Every operator action produces a canonical event.
4. **Capabilities are declared truth.** If the backend doesn't support pause, the UI shows kill.
5. **Tool calls are paired.** Every `tool_call_proposed` gets an `allowed`/`denied` and a `completed`/`failed`.
6. **Lifecycle is bookended.** First event is `session_created`, last is `session_exited` or `session_failed`.
7. **Sequences are monotonic.** Event seq is strictly increasing within a session.

## Claude Code adapter notes

- Hooks use **PascalCase** keys: `PreToolUse`, `PostToolUse`
- Hook format: `{"matcher": "", "hooks": [{"type": "command", "command": "...", "timeout": N}]}`
- Deny output: `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}`
- `--print` mode requires stdin closed after launch
- Settings injected into `.claude/settings.local.json` (merged, not clobbered)
- Settings restored on shutdown; tagged with `_governor_supervised` for cleanup
