# Gap Spec: Context Usage Telemetry

**Status:** daemon side shipped (ChatChunk.usage on all 4 backends). Client-side UI (Maude/Clerk) pending.
**Affects:** daemon RPC, Maude, Clerk
**Date:** 2026-03-27

## Problem

Clients (Maude, Clerk) have no way to show users how full their context window
is, when to clear, or how much they'd save by starting fresh. Claude Code ships
this as a first-class feature (`/context`, `/statusline`, idle-return nudge)
and it meaningfully improves UX for long sessions.

## What Claude Code Does (reverse-engineered)

Claude Code tracks context capacity using input-side tokens from the API:

    context_used = input_tokens + cache_creation_input_tokens + cache_read_input_tokens

Output tokens are excluded. Auto-compaction triggers at ~95% of the model's
context window (200K standard, 1M extended). The `/clear to save Xm tokens`
nudge appears to be a **projected savings estimate** — something like:

    avoidable_resend = current_context - fresh_baseline
    projected_savings = avoidable_resend × estimated_remaining_turns

This is a heuristic, not an exact accounting. Anthropic's own token counting
API is documented as an estimate.

Recent Claude Code changes (v2.1.84+):
- Token counts ≥1M formatted as `1.5m` instead of `1512.6k`
- Idle-return prompt after 75+ minutes specifically nudges `/clear`
- Context capacity shown in configurable status line

## Proposed: Daemon-Side Token Exposure

Add optional `usage` block to `chat.stream` end-of-stream result:

```json
{
  "response": "...",
  "receipt": { ... },
  "violations": [],
  "usage": {
    "input_tokens": 48210,
    "output_tokens": 1832,
    "cache_creation_input_tokens": 12400,
    "cache_read_input_tokens": 35810,
    "context_tokens": 48210,
    "model_context_window": 200000
  }
}
```

The daemon already proxies through to the backend API. Most backends return
usage stats in their response:
- Anthropic API: `usage.input_tokens`, `usage.output_tokens`, cache fields
- Ollama: `eval_count`, `prompt_eval_count` (partial)
- Claude Code CLI / Codex: may not expose (passthrough limitation)

The daemon's `chat_bridge` would extract whatever the backend provides and
normalize it into the `usage` block. Missing fields are omitted (not zeroed).

## Proposed: Client-Side Features (Maude + Clerk)

### Status line / context gauge
Persistent display of context fill percentage:
```
ctx: 48k/200k (24%) │ fresh baseline: 12k │ clearable: 36k
```

### Clear nudge
When context exceeds a threshold (configurable, default 70%), show:
```
New task? /clear to reclaim ~36k tokens (~180k over 5 turns)
```

The "over N turns" projection uses a simple multiplier — each turn re-sends
the full context, so clearing saves `clearable × remaining_turns`.

### Idle-return nudge
If the user returns after N minutes of inactivity (configurable, default 30),
prompt:
```
Welcome back. Current context: 142k. New task? /clear to start fresh.
```

### Maude-specific: show the receipt, not the aura
Rather than Claude Code's vague savings number, Maude should show the
breakdown:
```
Current live context:        182k
Fresh-session baseline:       24k
Avoidable next-turn resend: ~158k
10-turn projected savings:  ~1.58M
```

## Non-Goals

- Client-side tokenization (use API response, not local estimates)
- Exact cost calculations (that's billing, not UX)
- Auto-clear (always user-initiated)

## Dependencies

- Backend API must return usage stats (Anthropic does, Ollama partially)
- Daemon `chat_bridge` needs to extract and normalize usage from response
- Clients need to accumulate session baseline vs current context
