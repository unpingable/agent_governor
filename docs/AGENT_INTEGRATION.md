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

## Step 0: Prove It Works

Run `governor preflight --strict` and do not proceed until it's green.

```bash
governor preflight --strict          # Human-readable report
governor preflight --strict --json   # Machine-readable for CI
governor preflight --agent claude    # Force Claude-specific checks
governor preflight --agent codex     # Force Codex-specific checks
```

Exit code 0 = all pass. Exit code 2 = something failed. The smoke test
actually runs the pre-tool hook with a synthetic unapproved write and
verifies it blocks (exit 2 + JSON `"decision": "block"`).

**For CI / bootstrap scripts:**

```bash
#!/bin/bash
set -e
governor preflight --strict
echo "Governor enforcement verified."
```

---

## Support Matrix

| Agent | Chat Backend | Hooks | Pre-Tool Gating | Audit Trail | Preflight |
|-------|-------------|-------|-----------------|-------------|-----------|
| Claude Code | N/A | native | exit-code blocking | tool_audit.jsonl | `--agent claude` |
| Codex CLI | CodexBackend | event stream | post-hoc only | tool_audit.jsonl | `--agent codex` |
| Generic CLI | N/A | wrapper | snapshot-diff | via wrapper | basic |

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

Codex CLI does not have a native pre-tool hook system like Claude Code.
Two integration paths: **governed exec** (NDJSON event stream parsing +
snapshot diff) and **wrapper** (generic filesystem gating).

**Governed exec (recommended):**

```bash
governor init
governor codex-hooks install          # Write config, check binary
governor codex-exec "your prompt"     # Run with audit + snapshot diff
governor codex-exec "task" -m o3      # Override model
```

`governor codex-exec` parses the NDJSON event stream, logs every event to
`tool_audit.jsonl` and `notifications.jsonl`, snapshots the filesystem
before and after, and emits a gate receipt with the verdict.

No pre-tool blocking (Codex doesn't support it), but full post-hoc
accountability. Unapproved file changes are flagged in the receipt.

**Wrapper (generic, with rollback):**

```bash
governor wrap -- codex exec -m o4-mini "your prompt"
```

What `governor wrap` does:

1. Takes a filesystem snapshot before the agent runs
2. Runs the agent command
3. Diffs the filesystem after the agent completes
4. Routes changes through the governor FSM (propose -> verify -> apply)
5. Emits gate receipts for every verdict
6. Rolls back unapproved changes

**Wrapper options:**

```bash
governor wrap -- codex exec ...                  # Full gating (default)
governor wrap --auto-approve -- codex exec ...   # Auto-approve in exploratory mode
governor wrap --check-continuity -- codex exec ...  # Also check for continuity violations
governor wrap -c -i -- codex exec ...            # Interactive: offer fix/revise/proceed
```

**Codex as a chat backend** (via governor daemon):

```bash
BACKEND_TYPE=codex governor serve
governor chat "your prompt"           # Routes through codex CLI
```

This uses `CodexBackend` in `chat_bridge.py`, which calls
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
governor codex-hooks install           # Codex CLI
# OR: governor wrap -- <cmd>           # Generic wrapper

# 4. (Optional) Set up approved files and blocked commands
governor claude-hooks approve src/main.py tests/
governor claude-hooks block "rm -rf"

# 5. Prove enforcement is live
governor preflight --strict            # Must be green before proceeding
```

**For CI / bootstrap scripts:**

```bash
#!/bin/bash
set -e
governor preflight --strict
echo "Governor enforcement verified."
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

## Known Enforcement Gaps

These are bypass channels we know about but can't close at the current layer.
They are documented so you don't discover them the hard way.

### 1. Symlink escape (v3 / MCP proxy territory)

If an agent creates a symlink `src/main.py -> /etc/passwd` and then writes
to `src/main.py` (an approved path), the hook sees the approved path but the
write hits the symlink target. The hook does literal string matching against
the approved list — it does not resolve symlinks.

**Status:** Won't fix at the hook layer. Resolving symlinks in the hook
would require a filesystem monitor or MCP proxy. Tracked for v3.

### 2. Agent not calling hooks (session lifecycle)

We can prove hooks *would* block if called (preflight smoke test), but we
can't prove the agent's runtime actually invokes them. Claude Code loads
hooks at startup; if you install hooks mid-session, they're inert until
restart.

**Mitigation:** The pre-tool hook writes to `.governor/hook_invocations.jsonl`
every time it fires. Preflight compares this file's mtime against
`settings.local.json`. If settings are newer than the last invocation, it
warns that hooks are stale. This turns "restart advisory" from a guess into
observable signal.

### 3. Codex direct-write bypass

If Claude delegates to Codex and Codex writes files directly (not through
Claude's Write/Edit tools), Claude's pre-tool hook never fires. The files
appear on disk ungoverned.

**Mitigation:** `governor codex-exec` provides post-hoc audit (snapshot diff
+ receipts), but no rollback. `governor wrap` provides rollback but requires
wrapping the entire command. Both are labeled `enforcement: posthoc` in
receipts so you never mistake audit for gating.

**Closure path:** MCP proxy (v3) that intercepts all filesystem writes
regardless of which agent issued them.

### 4. Fail-open on invalid input

If the pre-tool hook receives invalid or empty JSON on stdin, it exits 0
(allow). This is intentional — a broken hook shouldn't brick the agent — but
it's also a silent bypass if the hook runner ever corrupts the payload.

**Mitigation:** The hook now logs fail-open events to
`hook_invocations.jsonl` with `"detail": "fail-open: invalid/empty stdin"`.
If these accumulate, something is wrong with the hook runner.

### 5. Exploratory mode = no file enforcement

Exploratory mode allows all file writes. This is intentional (it's audit-only
mode), but users may not realize it. If you're in exploratory mode, hooks
will never block a Write — they'll only log it.

**Locked in tests:** `TestExploratoryBoundary` in `tests/agent_integration/`.

---

## The Principle

Instruction files (CLAUDE.md, AGENTS.md, `.codex/instructions.md`) are travel
guides. They shape behavior through social contract. An agent that ignores them
is rude.

Hooks are physics. They block the write tool until prerequisites are satisfied.
An agent that bypasses them is broken.

**If your enforcement depends on the agent reading a markdown file and feeling
compelled to comply, your enforcement is not enforcement.**
