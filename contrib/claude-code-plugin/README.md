# Governor Plugin for Claude Code

Policy enforcement and receipt-producing governance for agentic coding workflows.

## Quick Start

```bash
# Install governor
pip install -e /path/to/agent_gov

# Initialize governance in your project
cd /your/project
governor init

# Test the plugin locally
claude --plugin-dir /path/to/agent_gov/contrib/claude-code-plugin
```

Then in Claude Code:

```
/governor:check      # Check current governance state
/governor:receipts   # View session receipts
/governor:appeal     # Appeal a denial
```

## What This Plugin Does

### Pass 1 (current): Observe

- **PostToolUse receipts**: Every `Bash`, `Write`, and `Edit` action emits a
  governor receipt with tool name, content hash, and session correlation.
- **Skills**: `/governor:check` and `/governor:receipts` for inspection.
- **MCP tools**: Governor's full MCP tool surface is available to Claude.

No blocking. Observation and audit trail only.

### Pass 2 (opt-in): Enforce

To enable enforcement, add `PreToolUse` and `TaskCompleted` entries to
`hooks/hooks.json`:

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash|Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "python3 scripts/pretool_gate.py"
        }
      ]
    }
  ],
  "TaskCompleted": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "python3 scripts/task_completed_gate.py"
        }
      ]
    }
  ]
}
```

This adds:

- **PreToolUse gating**: Blocks tool calls that violate governor policy.
- **TaskCompleted gating**: Refuses task completion with unresolved violations.

## Architecture

```
Claude Code ──► hooks (dumb adapters) ──► governor CLI ──► receipts/verdicts
     │
     └──► MCP server (governor mcp serve) ──► full RPC surface
```

Hook scripts are thin adapters. All policy logic lives in governor.
If governor is not installed or `.governor/` doesn't exist, hooks fail open.

## Requirements

- Python 3.10+
- `agent-governor` package installed (`governor` CLI available on PATH)
- `.governor/` directory initialized in the project (`governor init`)

## License

Apache-2.0
