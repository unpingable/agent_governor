# Fiction Governor: Sketch

**Problem**: LLMs writing fiction produce lowest-common-denominator mush. They:
- Forget character traits mid-story
- Contradict established world rules
- Default to lazy tropes (chosen one, love triangle, magical pregnancy)
- Flatten distinctive voice into generic "AI prose"
- Hallucinate events that didn't happen in the story

**Core insight**: These are the same problems the code governor solves, just in a different domain.

---

## Architecture Translation

| Code Governor | Fiction Governor |
|---------------|------------------|
| `facts/` - "file X exists" | `canon/` - "Elena met Marcus in Ch3" |
| `decisions/` - "we use React" | `bible/` - "Elena is cynical but privately romantic" |
| `ClaimType.FILE_EXISTS` | `ClaimType.SCENE_CONTINUES` |
| `ClaimType.TESTS_PASS` | `ClaimType.CONSISTENT_WITH_CANON` |
| `ClaimType.DECISION` | `ClaimType.STYLE_CHOICE` |
| Verifier checks file hash | Verifier checks against manuscript |
| Reject: "file not found" | Reject: "contradicts Ch3 - Elena already met Marcus" |

---

## The Two Ledgers

### `canon/` - What Has Happened (Facts)

Empirical claims about the story that can be verified against the manuscript.

```yaml
# canon/chapter_03.yaml
events:
  - id: evt_001
    chapter: 3
    summary: "Elena meets Marcus at the docks"
    characters: [elena, marcus]
    location: docks
    manuscript_ref: "chapter_03.md:45-78"
    quote: "She saw him before he saw her—leaning against the rusted bollard..."

  - id: evt_002
    chapter: 3
    summary: "Elena lies about her name, says she's 'Maria'"
    characters: [elena, marcus]
    establishes: elena_alias_maria
    manuscript_ref: "chapter_03.md:92-95"

relationships:
  - id: rel_001
    characters: [elena, marcus]
    status: "strangers, first meeting"
    as_of_chapter: 3
```

**Decay**: If the manuscript is edited and the referenced lines change, these facts become stale.

### `bible/` - What We've Decided (Decisions)

Normative choices about characters, world, tone that persist until explicitly revised.

```yaml
# bible/characters/elena.yaml
name: Elena Vance
role: protagonist
traits:
  - trait: cynical
    but: "privately romantic, hides it"
    established_in: chapter_1

  - trait: competent
    note: "Never make her stupid for plot convenience"

  - trait: guarded
    note: "Doesn't share feelings easily. NO sudden emotional confessions."

voice:
  internal_monologue: "sardonic, self-deprecating"
  dialogue: "clipped, deflects with humor"
  avoid: ["earnest declarations", "explaining her feelings unprompted"]

anti_patterns:
  - "Elena would NOT apologize first in a conflict"
  - "Elena would NOT cry in front of others"
  - "Elena would NOT trust authority figures easily"
```

```yaml
# bible/world.yaml
magic_system:
  cost: "physical pain proportional to effect"
  limits: "cannot create life, cannot reverse death"
  aesthetic: "visceral, body-horror adjacent"

tone:
  genre: "literary fantasy"
  not: ["YA", "cozy", "grimdark"]
  prose_style: "precise, sensory, no purple prose"
  pacing: "slow burn, earned payoffs"

banned_tropes:
  - name: "chosen_one"
    reason: "Protagonist earns their role, not destined"

  - name: "love_at_first_sight"
    reason: "Relationships develop through conflict and time"

  - name: "magical_pregnancy"
    reason: "No."

  - name: "bury_your_gays"
    reason: "Queer characters get happy endings or meaningful deaths, not tragic clichés"

  - name: "noble_savage"
    reason: "No exoticized 'wise indigenous' characters"

  - name: "women_in_refrigerators"
    reason: "Female characters don't exist to motivate male characters"
```

---

## Claim Types

```python
class FictionClaimType(Enum):
    # Scene claims
    SCENE_CONTINUES = "scene_continues"       # This scene follows from established events
    CHARACTER_PRESENT = "character_present"   # Character X is in this scene (verify location)
    TIMELINE_CONSISTENT = "timeline_consistent"  # Events don't violate temporal order

    # Character claims
    IN_CHARACTER = "in_character"             # Dialogue/action matches character bible
    RELATIONSHIP_ACCURATE = "relationship_accurate"  # Characters interact per established relationship

    # World claims
    MAGIC_VALID = "magic_valid"               # Magic use follows established rules
    WORLD_CONSISTENT = "world_consistent"     # Setting details match established world

    # Style claims
    TONE_APPROPRIATE = "tone_appropriate"     # Prose matches tone decisions
    NO_BANNED_TROPE = "no_banned_trope"       # Content doesn't match banned patterns

    # Meta claims
    STYLE_CHOICE = "style_choice"             # New decision about style/character/world
    CANON_UPDATE = "canon_update"             # Recording what happened in new content
```

---

## Verification

### Canon Verifier

```python
class CanonVerifier:
    """Verify claims against the manuscript and canon ledger."""

    def verify_character_present(self, claim: Claim) -> VerificationResult:
        """Check that a character can plausibly be in this scene."""
        character = claim.character
        scene_location = claim.location

        # Where was this character last seen?
        last_seen = self.canon.get_last_location(character)

        if last_seen and not self.plausible_travel(last_seen, scene_location):
            return VerificationResult.fail(
                f"{character} was last seen at {last_seen.location} in Ch{last_seen.chapter}. "
                f"Cannot be at {scene_location} without transition."
            )

        return VerificationResult.ok()

    def verify_timeline(self, claim: Claim) -> VerificationResult:
        """Check that events don't violate temporal order."""
        # e.g., "It was Tuesday" when we established it's Wednesday
        pass
```

### Bible Verifier

```python
class BibleVerifier:
    """Verify claims against character/world bible."""

    def verify_in_character(self, claim: Claim, proposed_content: str) -> VerificationResult:
        """Check that dialogue/action matches character bible."""
        character = claim.character
        bible = self.bible.get_character(character)

        # Check against anti-patterns
        for anti in bible.anti_patterns:
            if self.matches_pattern(proposed_content, anti):
                return VerificationResult.fail(
                    f"Out of character for {character}: {anti}"
                )

        # Check voice
        if claim.content_type == "dialogue":
            if not self.voice_matches(proposed_content, bible.voice):
                return VerificationResult.fail(
                    f"Dialogue doesn't match {character}'s voice. "
                    f"Expected: {bible.voice.dialogue}"
                )

        return VerificationResult.ok()

    def verify_no_banned_trope(self, claim: Claim, proposed_content: str) -> VerificationResult:
        """Check that content doesn't match banned tropes."""
        for trope in self.bible.banned_tropes:
            if self.detect_trope(proposed_content, trope):
                return VerificationResult.fail(
                    f"Banned trope detected: {trope.name}. Reason: {trope.reason}"
                )

        return VerificationResult.ok()
```

### Trope Detection

This is the hard part. Options:

1. **Keyword/pattern matching** - Simple but brittle
2. **Embedding similarity** - Compare to examples of the trope
3. **LLM-as-judge** - Ask a model "does this contain [trope]?" (ironic but effective)
4. **Human in the loop** - Flag for human review when uncertain

Probably: start with patterns, escalate to LLM-as-judge for ambiguous cases, always allow human override.

---

## Workflow

### Setup (Once per project)

```bash
# Initialize fiction governor
fiction-gov init --project "The Red Door"

# Define characters
fiction-gov bible add character elena --trait "cynical" --trait "guarded"
fiction-gov bible add character marcus --trait "optimistic" --trait "persistent"

# Define world rules
fiction-gov bible add rule magic_cost "Magic causes proportional physical pain"

# Define banned tropes
fiction-gov bible ban "chosen_one" --reason "Protagonist earns their role"
fiction-gov bible ban "love_triangle" --reason "We're not doing this"

# Define tone
fiction-gov bible set tone "literary fantasy, slow burn, precise prose"
```

### Writing Session

```bash
# Author (or LLM) proposes new scene
fiction-gov propose scene \
  --chapter 4 \
  --characters elena,marcus \
  --location "the red door tavern" \
  --summary "Elena confronts Marcus about the lie" \
  --content-file scene_draft.md

# Governor verifies
fiction-gov verify <proposal-id>

# Output:
# ✗ IN_CHARACTER failed: Elena apologizes first (anti-pattern)
# ✗ NO_BANNED_TROPE warning: Scene has "instant forgiveness" pattern
# ✓ CHARACTER_PRESENT: Elena and Marcus both plausibly at tavern
# ✓ TIMELINE_CONSISTENT: Follows Ch3 events
#
# REJECTED: 2 failures, 1 warning
#
# Suggestions:
#   - Elena would deflect or attack, not apologize
#   - Forgiveness should be earned over multiple scenes

# Author revises, resubmits
fiction-gov propose scene --content-file scene_draft_v2.md

# Governor verifies
fiction-gov verify <proposal-id>
# VERIFIED

# Apply (updates canon with new events)
fiction-gov apply <proposal-id>
# Canon updated: elena_marcus_confrontation added to Ch4
```

### Querying

```bash
# What do we know about Elena?
fiction-gov bible show elena

# What happened in Chapter 3?
fiction-gov canon show --chapter 3

# What's the current relationship between Elena and Marcus?
fiction-gov canon relationship elena marcus

# Has the "red door" been described?
fiction-gov canon search "red door"
```

---

## The LLM Integration

When using an LLM to generate content:

```python
# System prompt includes bible context
system = f"""
You are writing Chapter 4 of "The Red Door."

## Character Bible
{fiction_gov.bible.format_for_prompt()}

## Recent Canon (Ch 3)
{fiction_gov.canon.format_chapter(3)}

## Active Decisions
{fiction_gov.decisions.format_active()}

## Constraints
- All content will be verified against the bible
- Out-of-character content will be rejected
- Banned tropes: {fiction_gov.bible.banned_tropes}

Write the next scene. Elena confronts Marcus at the tavern.
"""

# LLM generates
response = llm.generate(system + user_prompt)

# Automatically create proposal and verify
result = fiction_gov.propose_and_verify(
    content=response,
    claims=[
        Claim(type=FictionClaimType.IN_CHARACTER, character="elena"),
        Claim(type=FictionClaimType.IN_CHARACTER, character="marcus"),
        Claim(type=FictionClaimType.NO_BANNED_TROPE),
        Claim(type=FictionClaimType.TONE_APPROPRIATE),
    ]
)

if result.rejected:
    # Feed rejection back to LLM
    retry_prompt = f"""
    Your draft was rejected:
    {result.format_rejections()}

    Please revise addressing these issues.
    """
    response = llm.generate(system + retry_prompt)
```

---

## Why This Works

1. **Persistent memory**: Bible decisions don't drift. "Elena is cynical" stays true until explicitly changed.

2. **Verified canon**: LLM can't hallucinate that "Elena and Marcus kissed in Ch2" if it didn't happen.

3. **Explicit anti-patterns**: Banned tropes are checked, not just hoped-against.

4. **Structured feedback**: "This is out of character because X" is actionable, unlike "try again."

5. **Human authority**: Author makes bible decisions. LLM proposes content. Governor enforces consistency.

---

## MVP Scope

Start small:

1. **Character bible** - Name, traits, voice, anti-patterns
2. **Canon tracker** - What happened, when, where, who
3. **In-character verifier** - Check against anti-patterns
4. **Banned trope checker** - Pattern matching for common offenders
5. **CLI** - `fiction-gov init`, `bible add`, `propose`, `verify`, `apply`

Skip for now:
- Embedding-based similarity
- LLM-as-judge (use patterns first)
- Automatic canon extraction from manuscript
- Timeline reasoning beyond simple ordering

---

## Open Questions

1. **Canon extraction**: Should the system read the manuscript and auto-populate canon? Or require explicit logging?

2. **Trope detection**: How sophisticated? Patterns miss subtle tropes. LLM-as-judge is recursive.

3. **Collaboration**: If multiple authors, how do bible changes get proposed/approved?

4. **Revision**: When author intentionally contradicts bible (character growth), how to revise cleanly?

5. **Tone verification**: How do you verify "literary, not YA"? This is hard.

---

## The Pitch

**For authors using LLMs**:

> Your characters have a bible. Your world has rules. Your story has canon.
> The fiction governor remembers what you've decided and what's happened.
> When the LLM drifts, it gets pulled back.
> When it reaches for a lazy trope, it gets caught.
> You stay in control. The LLM stays consistent.
