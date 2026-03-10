# GOV_GAP_OPENCODE_ADAPTER_001: OpenCode Adapter (Degraded Enforcement)

## Status
Proposed (v3, blocked by upstream)

## Summary
Governor adapter for the OpenCode runtime, with Copilot as one provider
path. Degraded enforcement until upstream subagent hook mediation exists.

Copilot is the billing/auth path. OpenCode is the agentic surface.
Governor targets agentic surfaces that cross from language into action,
not provider brands.

## Upstream Target
- **OpenCode**: https://github.com/opencode-ai/opencode (anomalyco/opencode)
- **Architecture**: Go core (Bubble Tea TUI), TypeScript/Bun plugin layer
- **Copilot auth**: `/connect` → GitHub device login, any paid Copilot sub

## Hookability Assessment (March 2026)

| Surface | Verdict | Evidence |
|---|---|---|
| Pre/post tool hooks | YES | `tool.execute.before` / `after` in plugin system |
| Deny/allow callbacks | PARTIAL | Deny via throw only, no argument rewrite |
| Command wrappers | PARTIAL | Bash tool goes through hooks, no process-level interception |
| Provider middleware | NO | No LLM response interceptor |
| Structured events | YES | SSE stream (`GET /event`) + JSON CLI output |
| MCP support | YES | stdio + remote, permission-integrated |
| Permission model | YES | 3-state (allow/ask/deny), per-tool, glob patterns |
| Plugin architecture | YES | 40+ hooks, custom tools, TypeScript/Bun |
| Configuration | YES | 6-layer precedence, per-tool, per-agent |
| Hook stability | PARTIAL | Documented but active bypass bugs, rebranding history |

## Known External Blockers

### Blocker 1: Subagent hook bypass (#5894, OPEN)
`tool.execute.before` does NOT fire for subagent tool calls spawned via
the `task` tool. An agent can delegate restricted operations to a subagent
and evade all plugin hooks. PR #7473 exists but issue remains open.

**Impact**: Plugin-based gate is not a complete enforcement boundary.
Any governed action can be bypassed by delegating to a subagent.

**Mitigation (degraded mode)**: Disable subagent/task tool use in
permission config (`"task": "deny"`) until #5894 is fixed. Accept that
this limits agent capability.

### Blocker 2: permission.ask hook dead code (#7006, OPEN)
The `permission.ask` plugin hook is defined in the type system but never
triggered. The active permission path emits `permission.asked` on the
event bus instead of calling the plugin hook.

**Impact**: Governor cannot programmatically intercept the user permission
prompt to auto-allow or auto-deny. Cannot replace the permission flow.

**Mitigation**: Observe permission events via SSE stream (receipt-only,
not enforcement). Use `tool.execute.before` for blocking instead.

## Integration Strategy (Triple-Surface)

### Surface 1: Plugin gate (primary enforcement)
`.opencode/plugins/governor.ts` using `tool.execute.before`:
- Call `governor gate check` or daemon RPC before each tool action
- Deny by throwing (blocks execution)
- Cannot rewrite arguments (deny-or-pass only)
- **Does not cover subagent calls** (Blocker 1)

### Surface 2: MCP server (governor tools for the LLM)
`governor mcp serve` registered as MCP server in `opencode.json`:
- Exposes governor tools (propose, verify, receipts, check)
- MCP tool calls visible in event stream
- MCP calls go through `tool.execute.before` (same dispatch)
- Provides LLM-accessible governance surface

### Surface 3: SSE consumer (observe-all telemetry)
Sidecar process consuming SSE event stream at `GET /event`:
- Receipts all tool executions including subagent calls
- Captures permission events (asked/replied)
- Observe-only — cannot block, only receipt
- Fallback coverage for Blocker 1 gap

## Enforcement Levels

### Level 0: Observe-only
- SSE consumer receipts everything
- No blocking, no plugin gate
- Useful for: understanding what OpenCode does before governing it

### Level 1: Primary-agent enforcement (degraded)
- Plugin gate blocks primary-agent tool calls
- SSE consumer receipts everything (including subagent calls)
- Subagent/task tool denied in permission config
- **This is the maximum safe enforcement level until #5894 is fixed**

### Level 2: Full enforcement (requires upstream fixes)
- Plugin gate blocks all tool calls (primary + subagent)
- Permission hook intercepts approval flow
- Requires: #5894 fixed, #7006 fixed
- **Not achievable today**

## Acceptance Criteria

1. Governor can block primary-agent tool calls before execution
2. Governor can receipt tool proposals/results and permission events
3. Governor marks subagent-originated actions as **untrusted enforcement path**
4. Governor fails closed or degrades loudly when subagents are enabled
5. Docs explicitly state the upstream trust boundary hole
6. No fork of OpenCode required — pure plugin + MCP + SSE consumer

## What This Is NOT

- Not "Governor for Copilot" — Copilot is a provider, not the target
- Not a claim of complete mediation of all tool calls
- Not a replacement for Claude Code hooks (which have full mediation)

## Comparison: OpenCode vs Claude Code Governability

| Capability | Claude Code | OpenCode |
|---|---|---|
| Pre-tool blocking | YES (PreToolUse hook) | YES (plugin, primary agent only) |
| Post-tool receipting | YES (PostToolUse hook) | YES (plugin + SSE) |
| Argument rewriting | NO | NO |
| Subagent coverage | YES (hooks fire for all) | NO (#5894) |
| Permission interception | YES (pre-tool deny/allow) | NO (#7006) |
| Task completion gate | YES (TaskCompleted hook) | NO |
| MCP server support | YES | YES |
| Structured event stream | NO (hooks only) | YES (SSE) |
| Process wrapper | YES (`governor wrap`) | NO |
| Fork pressure | None (hooks are stable API) | Low (plugin system, but churn risk) |

## Dependencies
- OpenCode plugin system (TypeScript/Bun)
- Governor daemon (Unix socket RPC) or CLI
- Governor MCP server

## References
- [OpenCode Plugins](https://opencode.ai/docs/plugins/)
- [OpenCode Permissions](https://opencode.ai/docs/permissions/)
- [OpenCode MCP Servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode Server/SSE](https://opencode.ai/docs/server/)
- [Issue #5894: Subagent hook bypass](https://github.com/anomalyco/opencode/issues/5894)
- [Issue #7006: permission.ask not triggered](https://github.com/anomalyco/opencode/issues/7006)
- [GitHub Copilot supports OpenCode (Jan 2026)](https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/)
