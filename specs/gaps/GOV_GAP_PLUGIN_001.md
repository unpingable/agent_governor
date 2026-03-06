# GOV_GAP_PLUGIN_001: Governor Plugin Distribution

**Status**: Active development (v0 skeleton in `contrib/claude-code-plugin/`)
**Category**: Distribution / integration
**Priority**: High — dogfooding vector, no new governor code required

## Problem

Governor produces receipts, enforces gates, and exposes a rich RPC surface —
but all of this requires manual CLI invocation or daemon wiring. There is no
drop-in integration for the two dominant agentic coding platforms (Claude Code,
OpenAI Codex). Users must configure hooks, MCP servers, and workflows by hand.

Both platforms now support plugin/skill/MCP integration surfaces that map
directly onto governor's existing capabilities. The gap is packaging, not
capability.

## Strategic Picture

**One governor service, multiple agent clients.** The daemon's stdio JSON-RPC
and MCP server are the shared backend. Distribution differs by platform.

### Claude Code: Plugin (strongest enforcement story)

Claude Code plugins bundle skills, MCP servers, hooks, and settings into a
single distributable artifact with a manifest. Key surfaces:

| Component | Governor mapping |
|-----------|-----------------|
| `.mcp.json` | `governor mcp serve --stdio` or `governor serve --stdio` |
| `hooks/hooks.json` | PreToolUse → `governor gate check`, PostToolUse → receipt emission |
| `skills/` | `/governor:check`, `/governor:receipts`, `/governor:appeal` |
| `settings.json` | Default permission configuration |

**Unique advantage:** `PreToolUse` hooks can return `permissionDecision: "deny"`
to hard-block tool calls. This is real enforcement, not advisory. `PostToolUse`
hooks emit receipts. `TaskCompleted` hooks can refuse completion (exit 2) until
governance conditions are met.

**Distribution:** Official marketplace (`plugins.claude.ai`), GitHub, or local
plugin directory (`claude --plugin-dir`).

**Cowork compatibility:** Anthropic's docs indicate file-based plugins can work
across both Claude Code and Cowork (Claude Desktop). Same artifact, two surfaces.

**Remote MCP connector:** Separately, Claude/Claude Desktop supports remote MCP
custom connectors for chat-side access to governor as a service. Different from
the plugin — useful for querying policy/receipts from non-coding sessions.

### OpenAI Codex: Skills + MCP (no equivalent plugin bundle)

Codex does NOT have a Claude-style plugin manifest/marketplace. The integration
surfaces are:

| Component | Governor mapping |
|-----------|-----------------|
| MCP server (stdio or HTTP) | `governor mcp serve --stdio` |
| Skills (`SKILL.md` + scripts) | `$governor-check`, `$governor-receipts` |
| Rules/approvals | Codex-native `allow`/`prompt`/`forbidden` for risky commands |
| App-server | Deeper integration for rich clients (future) |

**Key difference:** Codex has sandboxing, approval policies, and rules — but
these are platform-native enforcement, not hook-based. Governor integrates as
a service (MCP) and behavioral guide (skills), not as an enforcement hook.

**Ownership boundary:** Codex rules own coarse shell bans (`rm -rf`, `git push`).
Governor owns rich adjudication, receipts, and appeal state. Skills provide
workflow discipline ("before risky action, check governor"). AGENTS.md provides
the ambient contract ("this repo uses governor").

**Practical shape:** Repo-native skill in `.agents/skills/governor/`, required
MCP server in `.codex/config.toml`, AGENTS.md contract at repo root, shell
rules for obvious danger only.

### Standalone MCP Server

For any MCP-compatible client. Already exists: `governor mcp serve`.

## Architecture

**Hook scripts are dumb adapters.** They translate Claude/Codex hook JSON
into governor CLI calls and translate results back. All policy logic stays
in governor. No split-brain compliance.

Three faces of the same service:

- **Hooks** = enforcement plane (PreToolUse deny, TaskCompleted gate)
- **MCP** = query/control plane (receipts, policy, regime, appeal)
- **Skills** = human-friendly entry points (slash commands)

## Two-Pass Rollout

### Pass 1: Receipt Plugin (observe only)

- MCP server providing query tools
- PostToolUse hook emitting receipts for writes and shell commands
- `/governor:check` and `/governor:receipts` skills
- No blocking — observation and audit trail only

### Pass 2: Enforcement Plugin

- PreToolUse hook denying policy violations
- TaskCompleted hook refusing completion without receipt coverage
- `/governor:appeal` skill for filing exceptions
- Graduated enforcement (warn → ask → deny)

This ordering prevents "surprise compliance officer" UX on first install.

## Policy Surface (v0)

Start narrow:

### PreToolUse (Pass 2)

| Tool | What to gate |
|------|-------------|
| Bash | Destructive commands, `curl \| sh`, `git push` without receipts |
| Write/Edit | Protected paths, generated-file mutation |
| Agent | (future) Subagent spawning constraints |

### PostToolUse (Pass 1)

| Tool | What to receipt |
|------|----------------|
| Bash | Command, exit code, timing |
| Write/Edit | File path, content hash, diff hash |
| All | Session correlation, regime/lane context |

### TaskCompleted (Pass 2)

| Condition | Gate |
|-----------|------|
| Open violations | Block completion |
| Receipt coverage | Minimum threshold |
| Repo cleanliness | Clean working tree |

## File Layout

### Claude Code Plugin

```
contrib/claude-code-plugin/
├── .claude-plugin/
│   └── plugin.json              # Manifest (name, version, author)
├── .mcp.json                    # Governor MCP server config
├── hooks/
│   └── hooks.json               # PostToolUse (Pass 1), PreToolUse/TaskCompleted (Pass 2)
├── skills/
│   ├── check/
│   │   └── SKILL.md             # /governor:check
│   ├── receipts/
│   │   └── SKILL.md             # /governor:receipts
│   └── appeal/
│       └── SKILL.md             # /governor:appeal
├── scripts/
│   ├── pretool_gate.py          # PreToolUse → governor gate check
│   ├── posttool_receipt.py      # PostToolUse → receipt emission
│   └── task_completed_gate.py   # TaskCompleted → coverage check
└── README.md
```

### Codex Skills + MCP

```
contrib/codex-skills/
├── AGENTS.md                    # Ambient contract ("this repo uses governor")
├── .agents/
│   └── skills/
│       └── governor/
│           └── SKILL.md         # Workflow discipline (check/receipt/verify)
├── .codex/
│   └── config.toml              # MCP server wiring + sandbox + approvals
└── README.md
```

## Relationship to Existing Code

No new governor code required for v0. The plugin shells out to:

- `governor gate check --json` (PreToolUse evaluation)
- `governor receipts --json` (receipt queries)
- `governor status --json` (regime/state queries)
- `governor wrap --receipt-out` (receipt emission)

Future passes may use the daemon RPC directly for lower latency.

## Open Questions

1. **Codex skill pack:** Ship as separate `contrib/codex-skills/` or unified?
2. **Remote MCP connector:** Worth packaging for Claude Desktop chat access?
3. **Marketplace submission:** When is the plugin stable enough for `plugins.claude.ai`?
4. **Latency budget:** Is shelling out to `governor` CLI fast enough for PreToolUse,
   or does the daemon need a lightweight check endpoint?

## Origin

Identified during v2.7.0 session. Claude Code plugins, Codex skills/MCP, and
remote MCP connectors all map onto governor's existing RPC surface. The gap is
packaging and distribution, not capability.
