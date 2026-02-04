# Fiction Mode User Guide

## For Writers Who Want Their AI to Remember Their Story

---

## What This Does (30 Seconds)

You're writing a novel with AI assistance. The AI:
- Forgets your character's eye color between sessions
- Contradicts backstory you established in chapter 2
- Drifts your protagonist's voice into generic territory
- Makes your villain suddenly sympathetic when they shouldn't be
- Forces you to re-explain your world every single time

**Fiction Mode fixes this.**

You declare your canon — characters, rules, established facts — and the governor holds the AI to it. When the AI tries to contradict your story, it gets blocked until you decide what to do.

Your story. Your rules. AI follows, or it doesn't write.

---

## Quick Start (5 Minutes)

### 1. Launch the WebUI

```bash
cd agent_gov
docker-compose up -d
```

Open **http://localhost:3001** (Erin's Writing Studio) in your browser.

For local LLM instead of API:
```bash
docker-compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```

Or to use your Claude Max subscription (no API charges):
```bash
docker-compose -f docker-compose.yml -f docker-compose.claude-code.yml up -d
```

### 2. Create Your First Anchor

An anchor is a constraint the AI must respect. Create one for a character:

```bash
governor continuity anchor add \
  --id "elena-eyes" \
  --type canon \
  --description "Elena has green eyes, not blue" \
  --forbidden-patterns "Elena's blue eyes" "her blue eyes" \
  --severity reject
```

Or for something the character would never do:

```bash
governor continuity anchor add \
  --id "marcus-no-violence" \
  --type prohibition \
  --description "Marcus is a pacifist" \
  --forbidden-patterns "Marcus attacked" "Marcus hit" "Marcus struck" \
  --severity reject
```

### 3. Start Writing

Chat with the AI through the WebUI. Write your scenes. When the AI tries to give Elena blue eyes or make Marcus violent, you'll see:

```
[Governor] Blocked — choose an action:
  • [elena-eyes] Forbidden pattern found: 'Elena's blue eyes'

1. Fix — Rewrite to comply with canon
2. Revise — Update the canon anchor
3. Proceed — Log as intentional deviation

Reply with 1, 2, 3 or: maude fix | maude revise | maude proceed
```

### 4. Resolve and Continue

- Type **1** (or "maude fix") → AI rewrites the passage to match your canon
- Type **2** (or "maude revise") → Canon updates to match the new direction
- Type **3** (or "maude proceed") → Exception logged, continues as-is

That's it. Your story stays consistent.

---

## Core Concepts

### Anchors

An anchor is something that must remain true (or false) in your story.

**Anchor types:**

| Type | What It Does | Example |
|------|--------------|---------|
| `canon` | Established facts that must hold | "Elena has green eyes" |
| `prohibition` | Patterns that must NOT appear | "Marcus never uses violence" |
| `persona` | Voice/character constraints | "Vera speaks in short, clipped sentences" |
| `definition` | Term/concept must be used consistently | "Magic requires spoken words" |
| `requirement` | Patterns that MUST appear | "Every scene mentions the weather" |
| `style` | Writing style constraints | "No adverbs in dialogue tags" |

### Violations

A violation happens when the AI output contradicts an anchor.

**Severity levels:**

| Level | What Happens |
|-------|--------------|
| `warn` | You see a warning, but output continues |
| `correct` | System attempts automatic correction |
| `reject` | Output blocked until you resolve it |

Most anchors should use `reject` because the whole point is to catch problems.

### Resolution Options

When something gets blocked, you have three choices:

| Option | When to Use | What Happens |
|--------|-------------|--------------|
| **Fix** | AI made a mistake | AI regenerates, respecting the anchor |
| **Revise** | You're changing canon | Anchor updates to new reality |
| **Proceed** | Intentional deviation | Exception logged, output allowed |

**Proceed** is for things like:
- Unreliable narrators lying
- Dream sequences with wrong details
- Flashbacks before a character changed
- Deliberate continuity breaks for effect

The exception gets logged so you remember *why* you broke the rule.

---

## Setting Up Your Story

### Characters

For each major character, consider anchoring:

```bash
# Physical description
governor continuity anchor add \
  --id "char-elena-physical" \
  --type canon \
  --description "Elena: tall, green eyes, black hair with grey streak" \
  --forbidden-patterns "Elena's blue eyes" "Elena's brown eyes" "short Elena" \
  --severity reject

# Personality/voice
governor continuity anchor add \
  --id "char-elena-voice" \
  --type persona \
  --description "Elena speaks formally, never uses contractions" \
  --forbidden-patterns "Elena said \"don't\"" "Elena said \"can't\"" "Elena said \"won't\"" \
  --severity warn

# Boundaries
governor continuity anchor add \
  --id "char-elena-limits" \
  --type prohibition \
  --description "Elena rarely shows positive emotion openly" \
  --forbidden-patterns "Elena smiled warmly" "Elena laughed easily" "Elena beamed" \
  --severity reject
```

### World Rules

```bash
# Magic system
governor continuity anchor add \
  --id "world-magic-rules" \
  --type definition \
  --description "Magic requires spoken incantation. Silent magic is impossible." \
  --forbidden-patterns "silently cast" "wordless spell" "thought the incantation" \
  --severity reject

# Technology level
governor continuity anchor add \
  --id "world-tech" \
  --type prohibition \
  --description "Setting is 1920s - no modern technology" \
  --forbidden-patterns "computer" "smartphone" "internet" "plastic" \
  --severity reject
```

### Plot Points (Spoiler Protection)

```bash
# Things that haven't been revealed yet
governor continuity anchor add \
  --id "plot-secret-elena" \
  --type prohibition \
  --description "Elena being the killer is not revealed until chapter 15" \
  --forbidden-patterns "Elena is the killer" "Elena murdered" "Elena was responsible" \
  --severity reject
```

---

## Managing Canon Over Time

### Viewing Your Anchors

```bash
# List all anchors
governor continuity anchor list

# See details of one
governor continuity anchor show elena-eyes
```

### Removing Anchors

When the story evolves:

```bash
# Remove an anchor (e.g., after plot reveal)
governor continuity anchor remove plot-secret-elena
```

### Viewing Exceptions

See all the times you deliberately broke the rules:

```bash
governor lite exceptions
```

This shows:
- What anchor was violated
- What you chose (proceed)
- When it happened
- The scope of the exception

Useful for: continuity reviews, finding where you might need to add foreshadowing, tracking intentional unreliable narrator moments.

---

## Workflow Tips

### Start Loose, Tighten Later

You don't need to anchor everything before you start writing. Many writers:

1. Write the first few chapters freely
2. Notice what details matter
3. Add anchors for those things
4. Let the governor catch drift from there

### Use Warnings for Soft Constraints

Not everything needs to block. For stylistic preferences:

```bash
governor continuity anchor add \
  --id "style-no-adverbs" \
  --type style \
  --description "Avoid adverbs in dialogue tags" \
  --forbidden-patterns "ly said" "ly asked" "ly replied" \
  --severity warn
```

This warns you but doesn't block. Good for guidelines you sometimes ignore.

### Import from a Story Bible

Have existing world-building notes? Create a JSON file:

```json
{
  "anchors": [
    {
      "id": "char-elena-physical",
      "anchor_type": "canon",
      "description": "Elena: tall, green eyes, black hair",
      "forbidden_patterns": ["Elena's blue eyes"],
      "severity": "reject"
    }
  ]
}
```

Then import:
```bash
governor continuity import anchors.json
```

---

## Common Scenarios

### "The AI keeps contradicting my character"

Add a prohibition anchor for the specific patterns:

```bash
governor continuity anchor add \
  --id "char-elena-memory" \
  --type prohibition \
  --description "Elena's parents died when she was young" \
  --forbidden-patterns "Elena's mother said" "Elena's father told" "visited her parents" \
  --severity reject
```

### "The AI makes my villain too sympathetic"

Add a persona anchor:

```bash
governor continuity anchor add \
  --id "char-hollis-tone" \
  --type persona \
  --description "Director Hollis never shows genuine remorse" \
  --forbidden-patterns "Hollis felt guilty" "Hollis regretted" "Hollis apologized sincerely" \
  --severity reject
```

### "The AI spoils my twist"

Prohibition anchor until the reveal:

```bash
governor continuity anchor add \
  --id "plot-twist-protect" \
  --type prohibition \
  --description "Jin's death is not revealed until chapter 20" \
  --forbidden-patterns "Jin was dead" "Jin's ghost" "Jin died" \
  --severity reject
```

Remove it when you reach the reveal.

### "I want to turn off governance temporarily"

Disable specific anchors:

```bash
# View pending violations
governor lite pending

# Log as exception and continue
governor lite proceed --scope session
```

---

## The Philosophy

Fiction Mode isn't about making AI "better at writing."

It's about making AI **respect your authority over your own story**.

You're the author. You decide what's true in your world. The AI is a tool that helps you write — but it doesn't get to overwrite your decisions.

When you declare an anchor, you're saying: "This is canon. This is true. This matters."

When the AI contradicts it, you decide:
- **Fix**: "No, you're wrong, try again"
- **Revise**: "Actually, I'm changing my mind"
- **Proceed**: "I'm breaking this rule on purpose"

All three are valid. The point is that *you* decide, not the AI.

**Your story. Your rules.**

---

## CLI Reference

```bash
# Anchor management
governor continuity anchor add --id <id> --type <type> --description <desc> [--forbidden-patterns ...] [--required-patterns ...] [--severity warn|correct|reject]
governor continuity anchor list
governor continuity anchor show <id>
governor continuity anchor remove <id>
governor continuity check <text>
governor continuity import <file>

# Violation resolution
governor lite pending          # View pending violation
governor lite fix              # Regenerate compliant (needs backend)
governor lite revise           # Update the anchor
governor lite proceed          # Log exception and continue
governor lite exceptions       # View logged exceptions

# System status
governor continuity status
governor status
```

---

*"The AI is a tool. You are the author. Don't let it forget that."*
