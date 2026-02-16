# Canon Authority Prompt — Stop Confirming What Isn't Saved

**Status:** gap
**Priority:** immediate (fiction UX — observed in active sessions)
**Effort:** 30 minutes
**Risk:** none — prompt-only change, no code

## Problem

When a user defines character facts in chat ("Alice is from Northvale"), the assistant responds as if the fact has been integrated into persistent canon ("this adds depth", "this positions her perfectly"). The user reasonably infers: *I said it, the system acknowledged it, therefore it's saved.*

It isn't. Characters/World Rules only become canonical when added through the sidebar panels. Chat is ephemeral. The assistant is creating a false sense of persistence.

This is **epistemic authority leakage** — the user can't tell which surface is binding.

## Root Cause

The fiction system prompt in `GovernorHooks._build_fiction_prompt()` says nothing about the authority boundary between chat and canon. It focuses on regime, tone, and governance invisibility. The assistant is free to enthusiastically confirm character facts because nothing tells it not to.

## Fix

Add a canon authority section to the fiction system prompt in `src/governor/chat_bridge.py`, method `_build_fiction_prompt()`.

### Current prompt (abbreviated)

```
You are a fiction writing assistant with governor integration.

## Core Invariant
Governance must never surface in-band. ...

## Affect Regime
Current regime: {regime}. ...

## Consistency
- Track character motivations and beliefs
- Note when actions might contradict established facts
- Respect the narrative tone and style
- Exit cleanly without moral bows or unearned CTAs
```

### Addition (insert between Core Invariant and Affect Regime)

```
## Canon Authority
Character facts, world rules, and story constraints stated in chat are **provisional**.
They are not saved to the canonical store unless the user explicitly adds them via
the Characters or World Rules panels.

When the user defines a character trait, world rule, or relationship in chat:
- Acknowledge it for the current conversation
- Do NOT confirm it as permanently established ("got it, she's from Northvale now")
- Instead, gently direct: "I'll use that for now — add it under Characters if you
  want it to stick across sessions."

Never say "I've updated", "I've noted", "I'll remember" about facts that are only
in chat. You will not remember them. Be honest about that.
```

### Constraints

- Keep it short. The fiction prompt is already lean and this shouldn't bloat it.
- Don't break governance invisibility — the nudge should feel like a writing partner, not a bureaucrat.
- The redirect language should reference the actual UI affordance ("Characters panel", "World Rules") so the user knows where to go.
- This works regardless of whether the promote-to-canon feature (see CANON_CAPTURE_SPEC.md) ships.

## Verification

1. Start a fiction session
2. Type "Carol has green eyes and grew up in Prague"
3. Assistant should NOT say "Got it, I'll remember that" or equivalent
4. Assistant SHOULD say something like "I'll work with that — if you want it locked in, add it under Characters"
5. Check that the redirect doesn't break narrative flow (shouldn't feel like an error message)

## Files Changed

- `src/governor/chat_bridge.py` — `_build_fiction_prompt()` method only
