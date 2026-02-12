# Agent Integration

How to make governor enforcement real in a project that uses an AI coding agent.

---

## The One Rule

> "Use governor" is a norm. **Hooks installed** is physics.

Models don't have compulsion. They have local reward gradients. If "ship code"
is the shortest path, they'll ship code. The hook turns "call governor" from
"good practice" into "precondition for every write."

**Step 0 of any governed project is: install hooks, verify they block.**

Everything else — plans, templates, instruction files — is optional flavor
on top of the mechanical control surface.

---

## Integration Patterns by Agent

### Claude Code

Claude Code has a native hook system via `.claude/settings.local.json`. The
governor generates and installs these hooks automatically.

**Setup:**

```bash
governor init                          # Create .governor/ directory
governor claude-hooks install          # Install pre/post/notification hooks
# RESTART Claude Code (hooks load at startup only)
```

**Verification:**

```bash
governor claude-hooks status --fail-if-missing   # Exit 1 if not installed
```

**What it does:**

| Hook | Trigger | Governor Action |
|------|---------|-----------------|
| `PreToolUse` | Before Write/Edit/Bash/NotebookEdit | Check approved files, blocked commands, envelope mode |
| `PostToolUse` | After Write/Edit/NotebookEdit | Log to audit trail, track modified files |
| `Notification` | Session events | Log for audit |

**How it works:**

Hook scripts live at `.governor/hooks/{pre_tool_use,post_tool_use,notification}.py`.
Claude Code settings reference them:

```json
{
  "hooks": [
    {
      "type": "preToolUse",
      "command": "python3 /path/to/.governor/hooks/pre_tool_use.py",
      "tools": ["Write", "Edit", "Bash", "NotebookEdit"],
      "timeout": 5000
    }
  ]
}
```

The pre-tool hook reads the envelope (`.governor/.envelope`, plain text) and
blocks unapproved file writes in strict mode. Exit code 2 = block. Exit code
0 = allow.

**Gotchas:**

- Hooks load at Claude Code startup. Installing mid-session has no effect until
  restart.
- The hook reads `.governor/.envelope` (plain text, e.g. `strict` or
  `exploratory`), NOT `envelope.json`.

---

### Codex CLI

Codex CLI does not have a native pre-tool hook system like Claude Code. Use
the **wrapper pattern** instead.

**Setup:**

```bash
governor init
governor wrap -- codex exec -m o4-mini "your prompt"
```

**What `governor wrap` does:**

1. Takes a filesystem snapshot before the agent runs
2. Runs the agent command
3. Diffs the filesystem after the agent completes
4. Routes changes through the governor FSM (propose -> verify -> apply)
5. Emits gate receipts for every verdict
6. Rolls back unapproved changes

**Options:**

```bash
governor wrap -- codex exec ...                  # Full gating (default)
governor wrap --auto-approve -- codex exec ...   # Auto-approve in exploratory mode
governor wrap --check-continuity -- codex exec ...  # Also check for continuity violations
governor wrap -c -i -- codex exec ...            # Interactive: offer fix/revise/proceed
```

**Codex as a chat backend** (via governor daemon):

The governor daemon can route chat through Codex directly:

```bash
BACKEND_TYPE=codex governor serve
governor chat "your prompt"           # Routes through codex CLI
```

This uses the `CodexBackend` in `chat_bridge.py`, which calls
`codex exec --json` with the prompt piped via stdin.

---

### Generic CLI Agent

Any agent that runs as a CLI command can be wrapped.

**Setup:**

```bash
governor init
governor wrap -- <any-agent-command>
```

This works for aider, continue, cursor CLI, or any tool that modifies files.

**For agents with native hook systems:**

If an agent supports pre/post tool hooks (like Claude Code does), the pattern
is the same: generate a hook script that checks governor state, install it
where the agent reads hooks from. The claude_hooks module is a reference
implementation.

Key interface: hook receives tool call as JSON on stdin, exits 0 (allow) or
non-zero (block), optionally prints a JSON reason to stdout.

---

### SDK Integration (Anthropic)

For programmatic use of the Anthropic SDK with governor enforcement:

```python
from anthropic import Anthropic
from governor.sdk import GovernorMiddleware

client = GovernorMiddleware(Anthropic())
# All API calls now pass through governor gates
```

Supports advisory/blocking/strict modes, claim extraction, anchor checking,
security scanning, and streaming.

---

## Bootstrap Checklist

For any new project that should be governed:

```bash
# 1. Initialize governor state
governor init

# 2. Set envelope mode
governor envelope strict               # or: exploratory

# 3. Install agent hooks (pick one based on your agent)
governor claude-hooks install          # Claude Code
# OR
# Use `governor wrap -- <cmd>` for other agents

# 4. Verify hooks are active
governor claude-hooks status --fail-if-missing  # Claude Code
# OR
# Test: run agent, attempt unauthorized write, confirm it blocks

# 5. (Optional) Set up approved files and blocked commands
governor claude-hooks approve src/main.py tests/
governor claude-hooks block "rm -rf"
```

**For CI / bootstrap scripts:**

```bash
#!/bin/bash
# scripts/bootstrap.sh — fail if governor isn't ready
set -e
governor claude-hooks status --fail-if-missing
echo "Governor hooks verified."
```

---

## Common Failure Modes

| Failure | Symptom | Fix |
|---------|---------|-----|
| Hooks not installed | Agent writes freely, no receipts | `governor claude-hooks install` + restart |
| Hooks installed mid-session | Agent ignores hooks until restart | Restart agent |
| Wrong envelope path | Strict mode not enforced | Update hooks (fixed in v2.0.x) |
| Wrapper not used | Agent bypasses governor entirely | Wrap agent command: `governor wrap -- <cmd>` |
| Plan says "use governor" | Agent doesn't, because it's a norm | Install hooks instead. Norms aren't mechanisms. |

---

## The Principle

Instruction files (CLAUDE.md, AGENTS.md, `.codex/instructions.md`) are travel
guides. They shape behavior through social contract. An agent that ignores them
is rude.

Hooks are physics. They block the write tool until prerequisites are satisfied.
An agent that bypasses them is broken.

**If your enforcement depends on the agent reading a markdown file and feeling
compelled to comply, your enforcement is not enforcement.**
