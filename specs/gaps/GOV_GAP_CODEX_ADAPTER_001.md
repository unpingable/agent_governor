# GOV_GAP_CODEX_ADAPTER_001

## Title
Codex CLI Adapter: Generic Tool Hooks via Private Fork

## Status
Gap spec (parked — requires Rust fork of openai/codex)

## Problem Statement

Codex CLI has hooks, but they're Bash-only. `PreToolUse` and `PostToolUse` exist in the config schema and engine, but the runtime only emits `tool_name: "Bash"`. File edits (`Write`, `Edit`, `replace`) and MCP tool calls are invisible to the hook system. The docs even show `Edit|Write` as matcher examples while noting they match nothing today.

A feature request for an optional blocking pre-write hook (openai/codex#12683) was closed "not planned." A separate user independently forked Codex to add a blocking stop hook for automation integrity (openai/codex#14203) — also closed.

Governor cannot supervise Codex without tool-generic lifecycle hooks.

## What Codex Has

- **Hooks framework**: `PreToolUse`/`PostToolUse` config, matcher engine, discovery, JSON stdin/stdout
- **Generic post-tool path**: `AfterToolUse` in `registry.rs` already converts any `ToolPayload` into `HookToolInput` with `tool_kind`, `mutating`, `success`, `duration_ms`, `output_preview`
- **Mutation predicate**: `handler.is_mutating(&invocation)` already computed before execution
- **Tool input conversion**: `HookToolInput::from(&invocation.payload)` + `hook_tool_kind()` already generic
- **Approval system**: granular policies, categories, sandbox modes — but all internal

## What Codex Lacks

1. **Pre-mutation hook**: No generic blocking checkpoint before file writes, patch application, or MCP mutations. `PreToolUse` only intercepts Bash commands.
2. **Pre-completion hook**: No blocking checkpoint before turn completion. `notify` exists but doesn't block.
3. **Tool-generic hook payloads**: Both `PreToolUseRequest` and `PostToolUseRequest` are command-centric (`tool_name: "Bash"`, `command` field). Generic tool metadata exists internally but doesn't reach hooks.

## Observed Demand

Two independent users hit the same wall:

- **#12683**: Blocking pre-write hook for multi-agent governance. Closed "not planned."
- **#14203**: Blocking stop hook for automation integrity. User patched a local fork with synchronous `stop_hook` that aborts turn completion on nonzero exit. Also closed.

Both are variants of the same missing abstraction: first-class synchronous policy checkpoints, not just sandboxing, notify callbacks, or advisory rules.

## Why Sandbox + Approvals Are Insufficient

Codex's security model centers sandbox mode and approval policy. These answer:
- "What can this agent technically reach?" (sandbox)
- "When should the UI ask the user?" (approval)

They do not answer:
- "What exact state transitions are allowed, under which external policy, at which lifecycle boundary?" (governance)

A pre-write hook is not a nicer approval dialog — it's a deterministic veto point. A stop hook is not a prettier notification — it's a deterministic completion gate.

## Patch Plan (Private Fork)

### Phase 1: Expose generic post-tool hooks

Touch points:
- `codex-rs/hooks/src/engine/discovery.rs` (already discovers `post_tool_use`)
- `codex-rs/hooks/src/engine/mod.rs`
- `codex-rs/hooks/src/events/post_tool_use.rs`

What: Make `PostToolUse` carry real tool names and generic input, not just `"Bash"` + `command`. The internal `AfterToolUse` path already computes this — wire it through.

### Phase 2: Add generic pre-mutation hook

Touch points:
- `codex-rs/core/src/tools/registry.rs` — the main cut point
- `codex-rs/core/src/hook_runtime.rs` — where `"Bash"` is hardcoded

What: In `dispatch_any()`, after `is_mutating` is computed and before `handle_any()`:
1. Convert invocation to generic `HookToolInput` (already exists)
2. If mutating, dispatch pre-mutation hook with real tool identity
3. On deny, return model-facing block reason before execution

### Phase 3: Generalize hook payload schema

Touch points:
- `codex-rs/hooks/src/schema.rs` — currently constrains to `"Bash"`
- `codex-rs/hooks/src/events/pre_tool_use.rs`

What: Widen request structs to accept real tool metadata. Tagged union for `tool_input` matching internal `HookToolInput` variants (Function, Custom, LocalShell, Mcp). Backward-compatible: LocalShell variant preserves current `command` field shape.

### Do NOT touch:
- `discovery.rs` — already ahead of the runtime
- Matcher logic — already works on `tool_name`, just needs real names to match against
- Event naming — reuse `PreToolUse`/`PostToolUse`, don't invent `PreMutation`

## Upstream Compatibility

- 658 releases, v0.117.0 as of 2026-03-26. Fast-moving target.
- Blocking pre-write hook explicitly "not planned"
- Treat as private fork, not upstreamable PR
- Rebase cost: medium (core dispatch path changes slowly; schema/event types change faster)

## Relationship to Governor Adapter

Once the fork exists with generic tool hooks:
- Adapter structure mirrors Claude Code / Gemini CLI adapters
- `PreToolUse` → `tool_call_proposed` with real tool names
- `PostToolUse` → `tool_call_completed`
- Same supervisor, same events, same promotions, same budget
- Hook scripts use same Unix socket communication pattern

## Decision

Parked. Two-backend story (Claude Code + Gemini CLI) is sufficient for now. Revisit when:
- Upstream fixes hooks (unlikely given "not planned")
- A specific use case requires governed Codex
- Someone else maintains a generic-hooks fork we can adopt
