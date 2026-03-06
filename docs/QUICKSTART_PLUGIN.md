# Quickstart: Govern Your Claude Code Sessions

Get receipt-producing governance on every Claude Code action in under 5 minutes.
No config files to write. No daemon to manage. Just install and go.

## What You Get

Every time Claude Code runs a shell command, writes a file, or edits code,
governor silently emits a receipt: what happened, when, content hash, session
correlation. You get an audit trail with zero friction.

Later, you can opt into enforcement: blocking dangerous commands, gating task
completion on clean governance state, appealing denials.

## Prerequisites

- Python 3.10+
- Claude Code CLI (`claude`)
- A project directory (any repo works)

## Step 1: Install Governor

```bash
git clone https://github.com/unpingable/agent_governor.git
cd agent_governor
pip install -e .
```

Verify it works:

```bash
governor --version
```

## Step 2: Initialize Your Project

In your project directory (not the governor repo):

```bash
cd /path/to/your/project
governor init
```

This creates a `.governor/` directory for receipts and state.

## Step 3: Launch Claude Code with the Plugin

```bash
claude --plugin-dir /path/to/agent_governor/contrib/claude-code-plugin
```

That's it. You're governed.

## What Happens Now

Every `Bash`, `Write`, and `Edit` action Claude Code takes emits a receipt.
You can inspect them:

```
/governor:check       # Current governance state
/governor:receipts    # View session receipts
```

Or from the terminal:

```bash
governor receipts --last 10
governor receipts --last 5 --json
governor receipts --gate plugin_post_tool
```

## Example Output

After Claude Code writes a file and runs some tests, your receipt log looks like:

```
RECEIPT  a7f3c91e  plugin_post_tool  observe  file_write   2026-03-06T23:20:32Z
RECEIPT  5818430b  plugin_post_tool  observe  bash_command  2026-03-06T23:20:25Z
RECEIPT  c2d4e6f8  plugin_post_tool  observe  file_edit    2026-03-06T23:19:11Z
```

Every action, receipted. Content-addressed, hash-chained, tamper-evident.

## Optional: Enable Enforcement (Pass 2)

When you're ready for governor to actually block things, edit
`contrib/claude-code-plugin/hooks/hooks.json` and add:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "governor hook pre-tool 2>/dev/null || true"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "governor hook post-tool 2>/dev/null || true"
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
            "command": "governor hook task-complete"
          }
        ]
      }
    ]
  }
}
```

Now:
- **PreToolUse**: governor checks policy before Claude runs commands or writes files.
  Violations are blocked with a reason.
- **TaskCompleted**: Claude can't declare "done" while violations are unresolved.

## Optional: Add Anchors for Real Enforcement

Governor enforces *anchors* — statements that must remain true. Add some:

```bash
governor continuity anchor add \
  --id "no-force-push" \
  --type "decision" \
  --description "Never force-push to main" \
  --severity "error" \
  --class "invariant"

governor continuity anchor add \
  --id "tests-required" \
  --type "decision" \
  --description "All changes must include tests" \
  --severity "warning" \
  --class "preference"
```

Now when Claude Code tries to force-push or skip tests, the pre-tool hook
blocks the action and explains why.

## Also Works with Codex

For OpenAI Codex, copy the skill and config from `contrib/codex-skills/`:

```bash
cp -r contrib/codex-skills/.agents/ /your/project/.agents/
cp -r contrib/codex-skills/.codex/ /your/project/.codex/
```

Codex uses skills + MCP rather than hooks, so enforcement is convention-based
rather than hard-blocking. See `contrib/codex-skills/README.md` for details.

## MCP Tools

The plugin exposes governor's full MCP tool surface (21 tools). Claude Code
can call them directly for richer queries:

```
governor_status          # Full governance state
governor_propose         # Create proposals with claims
governor_verify          # Verify proposals, produce receipts
governor_facts           # Query recorded facts
governor_decisions       # Query recorded decisions
governor_gate_check      # Run evidence gate
governor_receipts        # Query receipt history
```

## Next Steps

- **Add more anchors** for your project's invariants (`governor continuity anchor list`)
- **Set a profile** for your workflow (`governor intent set --profile production`)
- **Inspect receipts** after incidents (`governor receipts --verdict block`)
- **Appeal denials** when needed (`/governor:appeal`)

## Architecture

```
Claude Code ──► hooks ──► governor CLI ──► receipts + verdicts
     │
     └──► MCP server ──► full governance RPC surface
```

Hook scripts are thin adapters. All policy logic lives in governor.
If governor isn't installed or `.governor/` doesn't exist, everything fails open.
Governor never breaks your workflow — it just makes it auditable.
