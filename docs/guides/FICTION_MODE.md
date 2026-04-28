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

Open **http://localhost:3001** in your browser.

### 2. Create Your First Character Anchor

An anchor is a constraint the AI must respect. Let's create one for a character:

```bash
governor continuity anchor add \
  --id "elena-eyes" \
  --type assertion \
  --content "Elena has green eyes, not blue"
```

Or for something the character would never do:

```bash
governor continuity anchor add \
  --id "marcus-no-violence" \
  --type prohibition \
  --forbidden-patterns "Marcus attacked" "Marcus hit" "Marcus struck"
```

### 3. Start Writing

Chat with Claude through the WebUI. Write your scenes. When the AI tries to give Elena blue eyes or make Marcus violent, you'll see:

```
[Governor] Blocked — choose an action:
  • [elena-eyes] Contradicts: "Elena has green eyes, not blue"

1. Fix — Rewrite to comply with canon
2. Revise — Update the canon (maybe you changed your mind)
3. Proceed — Log as intentional deviation (dream sequence, flashback, etc.)

Reply with 1, 2, 3 or: governor fix | governor revise | governor proceed
```

### 4. Resolve and Continue

- Type **1** (or "governor fix") → AI rewrites the passage to match your canon
- Type **2** (or "governor revise") → Canon updates to match the new direction
- Type **3** (or "governor proceed") → Exception logged, continues as-is (for intentional rule-breaking)

That's it. Your story stays consistent.

---

## Core Concepts

### Anchors

An anchor is something that must remain true (or false) in your story.

**Types of anchors:**

| Type | What It Does | Example |
|------|--------------|---------|
| `assertion` | Something that IS true | "Elena has green eyes" |
| `prohibition` | Something that must NOT happen | "Marcus never uses violence" |
| `character` | Voice/personality constraints | "Vera speaks in short, clipped sentences" |
| `world` | Setting rules | "Magic requires spoken words in this world" |
| `relationship` | How characters relate | "Jin and Nora are siblings, not romantic" |

### Violations

A violation happens when the AI output contradicts an anchor.

**Severity levels:**

| Level | What Happens |
|-------|--------------|
| `warn` | You see a warning, but output continues |
| `reject` | Output blocked until you resolve it |

Most anchors default to `reject` because the whole point is to catch problems.

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
  --type assertion \
  --content "Elena: tall, green eyes, black hair with grey streak, missing left pinky finger"

# Personality/voice
governor continuity anchor add \
  --id "char-elena-voice" \
  --type character \
  --content "Elena speaks formally, never uses contractions, occasionally slips into her native Spanish when emotional"

# Boundaries
governor continuity anchor add \
  --id "char-elena-limits" \
  --type prohibition \
  --forbidden-patterns "Elena smiled warmly" "Elena laughed easily" \
  --content "Elena rarely shows positive emotion openly — she smirks, she nods approval, but doesn't beam or gush"
```

### World Rules

```bash
# Magic system
governor continuity anchor add \
  --id "world-magic-rules" \
  --type world \
  --content "Magic requires: spoken incantation, physical gesture, and emotional focus. Silent magic is impossible. Unconscious people cannot cast."

# Technology level
governor continuity anchor add \
  --id "world-tech" \
  --type world \
  --content "Setting is roughly 1920s technology. No computers, no plastics, no antibiotics. Electricity exists but is uncommon outside cities."
```

### Relationships

```bash
# Established dynamic
governor continuity anchor add \
  --id "rel-elena-marcus" \
  --type relationship \
  --content "Elena and Marcus: professional respect, some romantic tension, but neither has acknowledged it. They use formal address (surnames) in public."

# Family
governor continuity anchor add \
  --id "rel-vera-family" \
  --type relationship \
  --content "Vera's mother is dead (died when Vera was 12). Father is alive but estranged. Brother Tomás is her only close family."
```

### Plot Points (Spoiler Protection)

```bash
# Things that haven't been revealed yet
governor continuity anchor add \
  --id "plot-secret-elena" \
  --type prohibition \
  --forbidden-patterns "Elena is the killer" "Elena murdered" "Elena was responsible for the death" \
  --content "Elena being the killer is not revealed until chapter 15. No hints before chapter 12."
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

### Updating Canon (Intentionally)

Your story evolves. Characters change. That's fine.

```bash
# Update an anchor
governor continuity anchor update \
  --id "char-elena-voice" \
  --content "After the trauma in chapter 8, Elena's speech becomes fragmented. She now uses contractions and shorter sentences."

# Or remove one entirely
governor continuity anchor remove --id "plot-secret-elena"  # After the reveal
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
- What the context was

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
  --type prohibition \
  --severity warn \
  --forbidden-patterns "ly said" "ly walked" "ly ran" \
  --content "Avoid adverbs in dialogue tags — prefer action beats"
```

This warns you but doesn't block. Good for guidelines you sometimes ignore.

### Session Continuity

Starting a new writing session? The WebUI remembers your anchors, but you might want to remind the AI where you left off:

```bash
# Get a summary of recent canon
governor continuity status

# Or export for your system prompt
governor continuity export --format prompt
```

### Bulk Import

Have a story bible already? You can import anchors from a file:

```bash
governor continuity anchor import --file story-bible.yaml
```

Format:
```yaml
anchors:
  - id: char-elena-physical
    type: assertion
    content: "Elena: tall, green eyes, black hair..."
    
  - id: world-magic
    type: world
    content: "Magic requires spoken words..."
```

---

## Common Scenarios

### "The AI keeps forgetting my character's name"

Add an assertion anchor for the character's full name and any nicknames:

```bash
governor continuity anchor add \
  --id "char-names-elena" \
  --type assertion \
  --content "Character's full name is Elena Vasquez-Morrison. Called 'Elena' by friends, 'Vasquez' by colleagues, 'Lena' only by her brother (who is dead)."
```

### "The AI makes my villain too sympathetic"

Add a character anchor for their limits:

```bash
governor continuity anchor add \
  --id "char-antagonist-tone" \
  --type character \
  --content "Director Hollis: never shows genuine remorse, never questions his methods, never bonds with protagonists. Any apparent warmth is manipulation."
```

### "The AI spoils my twist"

Prohibition anchor until the reveal:

```bash
governor continuity anchor add \
  --id "plot-twist-protect" \
  --type prohibition \
  --forbidden-patterns "was actually dead" "ghost" "died in the fire" \
  --content "Do not reveal or hint that Jin died in the prologue fire until chapter 20."
```

Remove it when you reach the reveal.

### "The AI uses modern slang in my historical fiction"

```bash
governor continuity anchor add \
  --id "style-period-language" \
  --type prohibition \
  --severity warn \
  --forbidden-patterns "okay" "cool" "got it" "no problem" "stuff" "thing" "gonna" "wanna" \
  --content "Avoid modern casual language. Setting is 1890s England."
```

### "I want different rules for different POV characters"

Create character-specific anchors and use the `--scope` flag:

```bash
# Elena's chapters are formal
governor continuity anchor add \
  --id "pov-elena-style" \
  --type character \
  --scope "pov:elena" \
  --content "Elena's POV: formal prose, long sentences, introspective"

# Marcus's chapters are punchy
governor continuity anchor add \
  --id "pov-marcus-style" \
  --type character \
  --scope "pov:marcus" \
  --content "Marcus's POV: short sentences, action-focused, minimal introspection"
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

## Troubleshooting

### "The governor is blocking things that aren't really violations"

Your forbidden patterns might be too broad. Check:

```bash
governor continuity anchor show <anchor-id>
```

Narrow the patterns or switch to `warn` severity while you tune it.

### "The AI rewrote the passage but it's worse now"

**Fix** asks the AI to regenerate while respecting the constraint. Sometimes the result is awkward. You can:
- Edit manually
- Type "try again" to get another attempt
- Choose **Proceed** and fix it yourself

### "I want to turn off governance temporarily"

You can bypass for a session:

```bash
# In the WebUI, start your message with:
[no-governance] Write whatever you want here...
```

Or disable specific anchors:

```bash
governor continuity anchor disable --id "strict-anchor-id"
# Re-enable later
governor continuity anchor enable --id "strict-anchor-id"
```

### "How do I see what the AI was trying to say before it got blocked?"

The blocked content is in the violation details:

```bash
governor lite pending
```

This shows the original output and exactly what triggered the violation.

---

## Getting Help

```bash
# See all continuity commands
governor continuity --help

# See all anchor commands  
governor continuity anchor --help

# Check system status
governor status
```

---

*"The AI is a tool. You are the author. Don't let it forget that."*
