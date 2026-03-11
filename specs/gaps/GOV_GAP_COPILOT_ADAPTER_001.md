# GOV_GAP_COPILOT_ADAPTER_001: Copilot Adapter Family

## Status
Proposed (v3)

## Summary
Governor adapter family for the four Copilot agentic surfaces. Copilot is
not one thing — it's a provider brand spanning four architecturally distinct
surfaces with different hookability profiles. Governor targets surfaces where
language turns into action, not provider brands.

**Don't build "Governor for Copilot."**
Build a **Copilot adapter family** for the surfaces where Copilot acts like
an agent runtime.

## Surface Taxonomy (March 2026)

| Surface | Runtime | Hook Architecture | Maturity |
|---|---|---|---|
| **Copilot CLI** (`copilot` binary) | Local terminal, agentic | Shell hooks (JSON stdin/stdout) | GA (Feb 2026) |
| **VS Code Agent Mode** | IDE-embedded | Shell hooks (JSON stdin/stdout) | GA/Preview |
| **Copilot Coding Agent** | GitHub Actions sandbox (cloud) | PR-boundary + `.github/hooks/` | GA |
| **Copilot SDK** | Your application (embedded) | Typed in-process callbacks | Technical Preview |

The old `gh copilot` extension was deprecated Oct 2025. `gh copilot` now
proxies to the standalone `copilot` binary.

**Not in scope:** Inline autocomplete, IDE chat without tools. Those are
completion surfaces, not agentic surfaces. Governor matters when language
turns into action.

## Hookability Assessment

### Surface 1: Copilot CLI

| Criterion | Verdict | Evidence |
|---|---|---|
| Pre/post tool hooks | YES | 6 hooks: `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred` |
| Deny/allow callbacks | YES | `preToolUse` returns `{"permissionDecision":"deny","permissionDecisionReason":"..."}` via stdout |
| Argument rewriting | NO | Deny-or-pass only, same as Claude Code |
| Subagent coverage | UNKNOWN | No `SubagentStart`/`SubagentStop` hooks documented for CLI |
| Structured events | PARTIAL | Hooks receive JSON; `events.jsonl` after session end; no real-time event bus |
| MCP support | YES | Full MCP (stdio, SSE, remote OAuth), `~/.copilot/mcp-config.json` |
| Permission model | PARTIAL | Hooks + user approval prompts, no built-in tiered permissions |
| Plugin architecture | YES | `/plugin install owner/repo`, agents/skills/hooks/workflows dirs |
| Configuration layers | YES | 3 layers: global (`~/.copilot/config`), repo (`.github/copilot/settings.json`), local (gitignored) |
| Hook stability | YES | GA since Feb 2026, documented protocol |

**Hook input schema** (`preToolUse`):
```json
{
  "timestamp": 1704614400000,
  "cwd": "/path/to/project",
  "toolName": "bash",
  "toolArgs": "{\"command\":\"rm -rf /\"}"
}
```

**Hook deny output:**
```json
{"permissionDecision": "deny", "permissionDecisionReason": "Blocked by governor policy"}
```

**Integration feasibility: HIGH.** Hook protocol is structurally near-identical
to Claude Code. The existing `governor hook pre-tool` / `governor hook post-tool`
commands would need only a thin tool-name translation layer.

### Surface 2: VS Code Agent Mode

| Criterion | Verdict | Evidence |
|---|---|---|
| Pre/post tool hooks | YES | 8 hooks: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SubagentStart`, `SubagentStop`, `Stop` |
| Deny/allow callbacks | YES | Three responses: `deny`, `ask` (user confirmation), `allow`. Most restrictive wins. |
| Argument rewriting | NO | Deny-or-pass only |
| Subagent coverage | YES | `SubagentStart`/`SubagentStop` hooks exist (not present in OpenCode) |
| Structured events | PARTIAL | JSON stdin/stdout for hooks; no external event stream |
| MCP support | YES | Full MCP support |
| Permission model | PARTIAL | Hooks + user approval, no built-in tiered permissions |
| Plugin architecture | YES | VS Code extension ecosystem, `.agent.md` frontmatter, custom agents via `.github/agents/` |
| Configuration layers | YES | User (`~/.claude/settings.json`), workspace (`.github/hooks/`), agent-level (`.agent.md`) |
| Hook stability | PARTIAL | Reads Claude Code config format, but tool names differ |

**Notable:** VS Code Copilot reads `.claude/settings.json`. Existing Claude Code
governor hooks partially work but require tool-name mapping:

| Claude Code | Copilot CLI | VS Code Copilot |
|---|---|---|
| `Write` | `create` | `create_file` |
| `Edit` | `edit` | `replace_string_in_file` |
| `Bash` | `bash` | (varies) |
| `Read` | `view` | (varies) |

**The `ask` permission level** (not in CLI or Claude Code) enables interactive
governance — governor can force user confirmation without fully denying.

**Integration feasibility: HIGH.** Subagent hooks solve the OpenCode #5894
problem. Tool-name translation layer required.

### Surface 3: Copilot Coding Agent (cloud)

| Criterion | Verdict | Evidence |
|---|---|---|
| Pre/post tool hooks | YES | Same 6 hooks as CLI + `agentStop`, `subagentStop`. Stored in `.github/hooks/*.json` on default branch. |
| Deny/allow callbacks | YES | Same `preToolUse` deny mechanism as CLI |
| Per-action interception | NO | Sandbox is opaque during execution |
| PR-boundary gate | YES | Draft PRs, CI approval gate, branch protection, CODEOWNERS |
| MCP support | YES | Local + remote MCP, configurable per-repo |
| Environment control | YES | `copilot-setup-steps.yml` (Actions workflow), self-hosted runners, secrets |
| Audit trail | PARTIAL | Enterprise audit logs (`actor_is_agent`), git history; session logs UI-only |
| Built-in security | YES | CodeQL, secret scanning, dependency checks run automatically |
| Firewall | PARTIAL | Network egress allowlist, but does NOT apply to MCP servers |

**Enforcement model is fundamentally different:** The coding agent is a
boundary-gated system. You observe inputs (issue, instructions) and outputs
(commits, PRs), but cannot intercept mid-execution at file-write granularity.

This is compatible with `governor ci verify` — run Governor as a required
status check on `copilot/` branches. The agent's PR cannot merge without
passing. This is the hardest available gate.

**Integration strategy:**
1. `copilot-setup-steps.yml` installs Governor in the sandbox
2. `.github/hooks/` contains governor pre/post-tool hooks
3. `AGENTS.md` / `copilot-instructions.md` instructs agent to use Governor MCP
4. CI status check runs `governor ci verify` on the PR

**Integration feasibility: MEDIUM.** Hooks exist but governor must be
installable in the ephemeral Actions sandbox. The real enforcement is at
PR-merge level, not per-action level. This is gate-at-the-boundary, not
gate-every-mutation.

### Surface 4: Copilot SDK

| Criterion | Verdict | Evidence |
|---|---|---|
| Pre/post tool hooks | YES | Typed callbacks: `OnPreToolUse`, `OnPostToolUse`, `OnAssistantMessage`, `OnToolExecutionStart`, `OnSessionIdle`, `OnSessionError` |
| Deny/allow callbacks | YES | `OnPreToolUse` returns `PreToolUseHookOutput` with `PermissionDecision` |
| Argument rewriting | POSSIBLE | You own the application; can intercept and modify |
| Subagent coverage | YES | You own the event loop |
| Structured events | YES | Typed event stream, in-process callbacks |
| MCP support | YES | SDK supports MCP server configuration |
| Permission model | YES | You define it |
| Plugin architecture | YES | Custom agents, tools, skills |

**Integration feasibility: HIGHEST.** The SDK is the cleanest surface —
analogous to the existing Anthropic SDK middleware at
`src/governor/sdk_middleware.py`. A `GovernorMiddleware` wrapper around the
SDK client would map `OnPreToolUse` → governor gate check.

**Key limitation:** Technical Preview status. API may change. Not ready for
production adapter work.

## Comparison: Copilot Surfaces vs Claude Code vs OpenCode

| Capability | Claude Code | Copilot CLI | VS Code Copilot | Copilot Cloud | OpenCode |
|---|---|---|---|---|---|
| Pre-tool blocking | YES | YES | YES | YES (hooks) | YES (plugin) |
| Post-tool receipting | YES | YES | YES | YES | YES |
| Argument rewriting | NO | NO | NO | NO | NO |
| Subagent coverage | YES | UNKNOWN | YES | YES (hooks) | NO (#5894) |
| Permission interception | YES | PARTIAL | YES (ask) | N/A | NO (#7006) |
| Task completion gate | YES | NO | NO | N/A | NO |
| MCP server support | YES | YES | YES | YES | YES |
| Structured event stream | NO | PARTIAL | NO | PARTIAL | YES (SSE) |
| Process wrapper | YES | NO | NO | NO | NO |
| CI gate integration | YES (wrap) | NO | NO | YES (status check) | NO |

## Build Order

1. **MCP server** — already exists (`libs/mcp_governor/`), works across all
   four surfaces immediately. Zero adaptation needed.

2. **Copilot CLI adapter** — thin translation layer mapping Copilot hook JSON
   to governor's existing hook protocol. Tool-name mapping table. Highest
   practical impact for local use.

3. **VS Code agent mode adapter** — extends CLI adapter with tool-name
   mapping for VS Code-specific names. Subagent hooks are a bonus.

4. **Coding agent CI integration** — `copilot-setup-steps.yml` template +
   `.github/hooks/` templates + CI status check workflow using
   `governor ci verify`. PR-boundary enforcement.

5. **SDK middleware** — analogous to `src/governor/sdk_middleware.py`. Blocked
   on SDK reaching GA.

## Known Gaps and Blockers

### Gap 1: Tool-name translation layer
Copilot CLI, VS Code, and Claude Code use different tool names for the same
operations. Governor hooks need a mapping table to normalize tool names
before policy evaluation.

### Gap 2: Subagent hook coverage on CLI (unknown)
The Copilot CLI does not document `SubagentStart`/`SubagentStop` hooks (VS
Code does). Need to verify whether CLI subagents bypass `preToolUse` hooks
(same class of bug as OpenCode #5894).

### Gap 3: No task completion gate
None of the Copilot surfaces have an equivalent to Claude Code's
`TaskCompleted` hook (exit 0=allow, 2=reject). The closest is
`sessionEnd`/`Stop`/`agentStop`, but these are observational, not gating.

### Gap 4: Coding agent session log access
Session logs (the agent's reasoning trace) are visible in the GitHub UI but
not available via a structured API. Programmatic audit of the agent's
reasoning is not possible.

### Gap 5: Coding agent firewall bypass via MCP
The coding agent's network firewall does NOT apply to MCP server traffic.
A malicious or misconfigured MCP server could exfiltrate data regardless of
firewall settings.

## Enforcement Levels

### Level 0: Observe-only (all surfaces)
- MCP server provides governor tools the agent can use voluntarily
- Instructions in `AGENTS.md` / `copilot-instructions.md` suggest using them
- No enforcement guarantee

### Level 1: Hook-gated (CLI, VS Code, coding agent)
- `preToolUse` hooks call `governor hook pre-tool`
- `postToolUse` hooks call `governor hook post-tool`
- Governor blocks or allows each tool call
- **Subagent coverage varies by surface**

### Level 2: CI-gated (coding agent)
- `governor ci verify` as required status check
- PR cannot merge without passing governor policy
- Boundary enforcement, not per-action enforcement
- Strongest available gate for cloud-hosted agent

### Level 3: Embedded (SDK)
- `GovernorMiddleware` wraps SDK client
- In-process interception of all tool calls
- Full mediation including argument inspection
- Requires SDK GA

## Acceptance Criteria

1. Governor MCP server works with all four Copilot surfaces (already true)
2. Tool-name translation layer normalizes CLI/VS Code/Claude Code tool names
3. `preToolUse` hook adapter maps Copilot JSON to governor hook protocol
4. `postToolUse` hook adapter emits governor receipts
5. CI workflow template for coding agent uses `governor ci verify`
6. `copilot-setup-steps.yml` template installs governor in sandbox
7. Subagent hook coverage verified on CLI surface (Gap 2)
8. Docs explicitly state per-surface enforcement boundaries

## What This Is NOT

- Not "Governor for Copilot" — it's an adapter family for four distinct surfaces
- Not a claim of complete mediation on any surface except SDK
- Not a fork of any Copilot tool — pure hook + MCP + CI integration
- Not a replacement for Claude Code hooks (which remain the cleanest surface)

## Relationship to GOV_GAP_OPENCODE_ADAPTER_001

OpenCode is a separate agentic surface that *uses* Copilot as an auth/billing
path. The OpenCode adapter targets OpenCode's plugin system, not Copilot's
hooks. A user running OpenCode with Copilot auth would use the OpenCode
adapter, not this one. The surfaces are architecturally distinct even though
they share a billing relationship.

## Dependencies
- Governor MCP server (`libs/mcp_governor/`)
- Governor hook protocol (`governor hook pre-tool`, `governor hook post-tool`)
- Governor CI lane (`governor ci verify`)
- Tool-name translation layer (new, small)

## References
- [Copilot CLI GA](https://github.blog/changelog/2026-02-25-github-copilot-cli-is-now-generally-available/)
- [Hooks Configuration Reference](https://docs.github.com/en/copilot/reference/hooks-configuration)
- [Using Hooks with Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)
- [About Copilot Coding Agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- [Coding Agent Hooks](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks)
- [MCP and Coding Agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/mcp-and-coding-agent)
- [VS Code Agent Hooks](https://code.visualstudio.com/docs/copilot/customization/hooks)
- [Copilot SDK](https://github.com/github/copilot-sdk)
- [Copilot Access Management](https://docs.github.com/en/copilot/concepts/agents/coding-agent/access-management)
- [GOV_GAP_OPENCODE_ADAPTER_001](specs/gaps/GOV_GAP_OPENCODE_ADAPTER_001.md)
