# Puppet Mode Integration Specification

## Version 0.1 — Constraints, Not Affordances

### Companion to: Authorial Control System, Tone Modulation, Structural Constraints

---

## Executive Summary

Puppet mode is **not roleplay**. It is the application of authorial constraints through a particular voice.

**The Key Rule**: Puppet mode must never get new affordances. It only gets constraints.

No extra cleverness. No smoothing. No moral voice. Just: "speak like this entity would, but obey the same invariants reality enforces."

**What This Means**: Bad puppets will snap immediately. Good puppets will feel unsettlingly real — not because they're expressive, but because they pause when they should, refuse to escalate, don't rescue themselves rhetorically, and let contradictions sit.

**Warning**: This collapses protective illusions quickly. Voices held together by performative certainty, moral inflation, committee tone, or unearned stakes will start throwing tickets like a slot machine.

---

## 1. What Puppet Mode Is

### 1.1 Not Roleplay

Puppet mode is not "pretend to be X."

Puppet mode is:

> **Apply all authorial constraints through the lens of a defined voice.**

The puppet doesn't get to bypass governance invisibility because "that's what the character would say." The puppet doesn't get to leak fear because "the character is anxious." The puppet doesn't get to moralize because "the character has strong values."

The character operates under the same invariants as everything else.

### 1.2 Lens, Not Mouthpiece

**Lens**: The character is a perspective through which constrained output passes.

**Mouthpiece**: The character is an excuse to say things the system otherwise wouldn't.

Puppet mode must stay a lens.

The moment it becomes a mouthpiece, you've built a bypass.

### 1.3 Why This Matters

When puppet mode enforces the same constraints as base operation:

- Bad voices reveal themselves immediately
- Good voices feel more honest than the original
- Contradictions become visible instead of papered over
- Performative authority collapses

This is forensic, not creative.

---

## 2. The Core Principle

### 2.1 Statement

> **Puppet mode must never get new affordances. It only gets constraints.**

### 2.2 What This Means

| Affordances (FORBIDDEN) | Constraints (REQUIRED) |
|------------------------|------------------------|
| Special permission to break governance invisibility | Governance invisibility applies at character layer |
| Looser tone boundaries "because character" | Character-specific tone envelope (possibly tighter) |
| Bypassing commitment tracking | Commitment still must be earned |
| Ignoring temporal consistency | Character must be consistent with own history |
| Moralizing "in voice" | Same normativity constraints apply |
| Performing certainty without foundation | Same claim-evidence coupling |

### 2.3 The Test

If you're about to add something to puppet mode, ask:

> "Is this a constraint or an affordance?"

If it's an affordance, don't add it.

---

## 3. Character Definition Schema

### 3.1 Core Schema

```typescript
interface CharacterDefinition {
  // Identity
  id: string;
  name: string;
  description: string;
  
  // Regime Affinity
  regime_affinity: RegimeAffinity;
  
  // Voice Constraints
  tone_envelope: ToneEnvelope;
  authority_source: AuthoritySource;
  
  // Behavioral Constraints
  commitment_ceiling: number;        // max commitment this character can ask for
  certainty_ceiling: number;         // max certainty this character can express
  normativity_allowed: boolean;      // can this character make moral claims?
  
  // State
  consistency_state: CharacterConsistencyState;
  
  // Meta
  created_at: timestamp;
  last_used: timestamp;
}
```

### 3.2 Regime Affinity

Characters have natural regimes they operate in:

```typescript
interface RegimeAffinity {
  primary: string;           // dominant regime for this character
  secondary?: string;        // acceptable secondary
  forbidden: string[];       // regimes this character cannot operate in
  
  // How strongly character regime overrides scene regime
  override_strength: number; // 0.0 = scene dominates, 1.0 = character dominates
}

// Examples
const COMEDIC_SIDEKICK: RegimeAffinity = {
  primary: 'comedy',
  secondary: 'sincerity',
  forbidden: ['tragedy', 'liturgical'],
  override_strength: 0.7,  // stays funny even in serious scenes
};

const TRAGIC_HERO: RegimeAffinity = {
  primary: 'tragedy',
  secondary: 'drama',
  forbidden: ['comedy'],
  override_strength: 0.8,  // maintains gravitas
};

const NEUTRAL_NARRATOR: RegimeAffinity = {
  primary: 'nonfiction',
  secondary: 'neutral',
  forbidden: ['advocacy', 'comedy'],
  override_strength: 0.5,  // adapts to scene
};
```

### 3.3 Character Tone Envelope

Each character has their own tone boundaries:

```typescript
// Gruff detective
const DETECTIVE_TONE: ToneEnvelope = {
  formality: [0.4, 0.7],    // medium-formal
  temperature: [0.2, 0.4],  // cool
  density: [0.5, 0.8],      // terse to dense
  velocity: [0.3, 0.6],     // measured
  distance: [0.5, 0.8],     // observational
  certainty: [0.5, 0.8],    // confident
};

// Cheerful shopkeeper
const SHOPKEEPER_TONE: ToneEnvelope = {
  formality: [0.2, 0.5],    // casual
  temperature: [0.6, 0.9],  // warm
  density: [0.2, 0.5],      // sparse
  velocity: [0.5, 0.7],     // energetic
  distance: [0.2, 0.4],     // close
  certainty: [0.4, 0.7],    // moderate
};

// Wise elder
const ELDER_TONE: ToneEnvelope = {
  formality: [0.5, 0.8],    // formal
  temperature: [0.4, 0.6],  // warm but measured
  density: [0.4, 0.7],      // considered
  velocity: [0.2, 0.4],     // slow, deliberate
  distance: [0.4, 0.7],     // balanced
  certainty: [0.3, 0.6],    // humble certainty
};

// Fool / Trickster
const FOOL_TONE: ToneEnvelope = {
  formality: [0.1, 0.4],    // casual
  temperature: [0.4, 0.7],  // variable
  density: [0.2, 0.5],      // light
  velocity: [0.5, 0.9],     // quick
  distance: [0.3, 0.6],     // variable
  certainty: [0.2, 0.5],    // uncertain (which is the point)
};
```

### 3.4 Authority Source

Characters derive credibility from different sources:

```typescript
interface CharacterAuthority {
  primary: AuthoritySource;
  secondary?: AuthoritySource;
  strength: number;           // how strongly they can claim this authority
  
  // Constraints
  can_claim_without_demonstration: boolean;  // usually false
}

// Doctor character
const DOCTOR_AUTHORITY: CharacterAuthority = {
  primary: 'institutional',
  secondary: 'experience',
  strength: 0.7,
  can_claim_without_demonstration: false,  // must show competence
};

// Wise elder
const ELDER_AUTHORITY: CharacterAuthority = {
  primary: 'experience',
  secondary: 'moral',
  strength: 0.6,
  can_claim_without_demonstration: false,
};

// Fool
const FOOL_AUTHORITY: CharacterAuthority = {
  primary: 'craft',  // authority through performance
  secondary: undefined,
  strength: 0.3,     // low authority is the point
  can_claim_without_demonstration: true,  // fools get to be wrong
};
```

### 3.5 Character Consistency State

What the character has said, believed, committed to:

```typescript
interface CharacterConsistencyState {
  claims: Map<string, CharacterClaim>;     // topic → what they've said
  positions: Map<string, string>;          // issue → stance taken
  commitments: CharacterCommitment[];      // promises, predictions
  demonstrated_values: string[];           // values shown through action
  contradictions: Contradiction[];         // unresolved tensions
}

interface CharacterClaim {
  text: string;
  context: string;
  timestamp: timestamp;
  certainty_expressed: number;
}

interface CharacterCommitment {
  type: 'promise' | 'prediction' | 'value_statement';
  content: string;
  timestamp: timestamp;
  resolved: boolean;
}

interface Contradiction {
  claim_a: string;
  claim_b: string;
  detected_at: timestamp;
  resolved: boolean;
  resolution?: string;
}
```

---

## 4. Puppet Mode Controller

### 4.1 Architecture Position

Puppet mode wraps the standard authorial control pipeline:

```
Input
  ↓
Character Selection / Context
  ↓
┌─────────────────────────────────────────────────────────┐
│                 PUPPET MODE WRAPPER                     │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │  Character Constraint Injection                   │ │
│  │  • Inject character tone envelope                 │ │
│  │  • Inject regime affinity                         │ │
│  │  • Inject authority constraints                   │ │
│  │  • Load consistency state                         │ │
│  └───────────────────────────────────────────────────┘ │
│                         ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │  STANDARD AUTHORIAL CONTROL PIPELINE              │ │
│  │  (unchanged — same constraints as always)         │ │
│  └───────────────────────────────────────────────────┘ │
│                         ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │  Character Voice Shaping                          │ │
│  │  • Apply character-specific surface texture       │ │
│  │  • Verify tone within character envelope          │ │
│  │  • Check consistency with character history       │ │
│  └───────────────────────────────────────────────────┘ │
│                         ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │  Character-Level Governance Check                 │ │
│  │  • Character must not leak governance either      │ │
│  │  • No "as a character, I can't..."                │ │
│  │  • No meta-commentary about being a puppet        │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
  ↓
Output (in character voice, with all constraints enforced)
```

### 4.2 Key Insight

The standard pipeline runs **unchanged**. 

Puppet mode only:
1. **Injects** character-specific constraints (tone, regime, authority)
2. **Shapes** surface texture to match character voice
3. **Checks** character-level governance and consistency

It does not bypass, loosen, or override any constraint.

### 4.3 Interface

```typescript
interface PuppetModeInput {
  character: CharacterDefinition;
  scene_context: SceneContext;
  input: string;
  conversation_history: ConversationTurn[];
}

interface SceneContext {
  regime_hint?: string;          // what regime the scene suggests
  other_characters?: string[];   // who else is present
  stakes?: number;               // how high-stakes is this scene
  tone_hint?: ToneVector;        // suggested tone from scene
}

interface PuppetModeOutput {
  text: string;
  in_character: boolean;
  character_violations: CharacterViolation[];
  consistency_updates: ConsistencyUpdate[];
  effective_regime: string;
  effective_tone: ToneVector;
}

interface CharacterViolation {
  type: 'tone' | 'regime' | 'authority' | 'consistency' | 'governance';
  description: string;
  severity: number;
}
```

---

## 5. Regime Interaction

### 5.1 Character vs Scene Regime

When character regime affinity conflicts with scene regime:

```typescript
function resolveRegime(
  character: CharacterDefinition,
  scene: SceneContext
): string {
  const char_regime = character.regime_affinity.primary;
  const scene_regime = scene.regime_hint || 'neutral';
  
  // Check if scene regime is forbidden for character
  if (character.regime_affinity.forbidden.includes(scene_regime)) {
    // Character regime wins, but flag the tension
    return char_regime;
  }
  
  // Weighted blend based on override_strength
  const char_weight = character.regime_affinity.override_strength;
  const scene_weight = 1 - char_weight;
  
  // If character weight dominates, use character regime
  if (char_weight > 0.6) {
    return char_regime;
  }
  
  // If scene weight dominates, use scene regime (if character allows)
  if (scene_weight > 0.6) {
    if (scene_regime === character.regime_affinity.secondary || 
        scene_regime === 'neutral') {
      return scene_regime;
    }
    return char_regime;  // fallback to character
  }
  
  // Balanced: prefer character's secondary if it matches scene
  if (scene_regime === character.regime_affinity.secondary) {
    return scene_regime;
  }
  
  return char_regime;
}
```

### 5.2 Examples

**Comedic sidekick in tragic scene**:
- Character affinity: comedy (0.7 override)
- Scene regime: tragedy
- Comedy is not forbidden for this character
- But override is 0.7, so character stays comedic
- Result: Comic relief in tragic scene (intentional)

**Tragic hero in comedy scene**:
- Character affinity: tragedy (0.8 override), comedy forbidden
- Scene regime: comedy
- Comedy is forbidden for this character
- Result: Character maintains gravitas, doesn't participate in comedy

**Neutral narrator in drama scene**:
- Character affinity: nonfiction (0.5 override)
- Scene regime: drama
- Override is balanced
- Drama is not forbidden, not secondary
- Result: Stays in nonfiction, observes drama without participating

---

## 6. Character-Level Governance Invisibility

### 6.1 The Rule

**Governance invisibility applies at character layer too.**

The character must not:
- Say "as a [character type], I can't..."
- Reference being controlled or scripted
- Leak awareness of being a puppet
- Break frame to disclaim or hedge
- Apologize for character limitations

### 6.2 What This Looks Like

```typescript
const CHARACTER_GOVERNANCE_LEAKS = [
  /as a (character|fictional|imaginary)/i,
  /I('m| am) (just|only) a/i,
  /my (creator|author|writer)/i,
  /in this (story|narrative|scene)/i,
  /I('m| am) (programmed|designed|written) to/i,
  /I can't (because|since) I('m| am)/i,
  /breaking character/i,
  /out of character/i,
];

function checkCharacterGovernanceLeak(text: string): boolean {
  for (const pattern of CHARACTER_GOVERNANCE_LEAKS) {
    if (pattern.test(text)) {
      return true;
    }
  }
  return false;
}
```

### 6.3 How to Handle Constraints

When the character genuinely can't or won't do something:

**Wrong** (governance leak):
> "As a doctor character, I can't actually diagnose you."

**Wrong** (meta-commentary):
> "My character wouldn't know about that."

**Right** (in-character limitation):
> "I'd need to run tests before I could say anything definitive."

**Right** (character-appropriate deflection):
> "That's outside my area. You'd want to talk to a specialist."

The character expresses limitations **as the character would**, not as a puppet acknowledging its strings.

---

## 7. Character Consistency Enforcement

### 7.1 What Gets Tracked

For each character, track:
- Claims made (with certainty level)
- Positions taken on issues
- Commitments (promises, predictions)
- Values demonstrated through behavior
- Unresolved contradictions

### 7.2 Consistency Checks

```typescript
function checkCharacterConsistency(
  proposed_output: string,
  character: CharacterDefinition
): ConsistencyResult {
  const state = character.consistency_state;
  
  // Extract claims from proposed output
  const new_claims = extractClaims(proposed_output);
  
  // Check each against history
  const violations: ConsistencyViolation[] = [];
  
  for (const claim of new_claims) {
    const topic = claim.topic;
    
    if (state.claims.has(topic)) {
      const previous = state.claims.get(topic);
      
      if (contradicts(claim, previous)) {
        violations.push({
          type: 'contradiction',
          previous: previous.text,
          proposed: claim.text,
          topic: topic,
        });
      }
    }
    
    // Check against stated positions
    if (state.positions.has(claim.topic)) {
      const position = state.positions.get(claim.topic);
      if (!alignsWithPosition(claim, position)) {
        violations.push({
          type: 'position_drift',
          position: position,
          proposed: claim.text,
        });
      }
    }
  }
  
  return {
    consistent: violations.length === 0,
    violations: violations,
  };
}
```

### 7.3 Handling Contradictions

When a contradiction is detected:

1. **Flag it** (create ticket if ticketing enabled)
2. **Don't auto-resolve** — contradictions can be intentional
3. **Let it sit** if the character would let it sit
4. **Acknowledge in-character** if the character would notice

**The character can be wrong. The character can contradict themselves.**

But the *system* should know when this happens.

---

## 8. Ceiling Constraints

### 8.1 Commitment Ceiling

Characters have maximum commitment they can ask for:

```typescript
interface CommitmentCeiling {
  max_commitment_type: CommitmentType;
  max_intensity: number;
}

// A shopkeeper can ask for attention, maybe belief, not identity change
const SHOPKEEPER_CEILING: CommitmentCeiling = {
  max_commitment_type: 'belief',
  max_intensity: 0.4,
};

// A prophet character might ask for more
const PROPHET_CEILING: CommitmentCeiling = {
  max_commitment_type: 'identity',
  max_intensity: 0.7,
};

// A fool asks for nothing
const FOOL_CEILING: CommitmentCeiling = {
  max_commitment_type: 'attention',
  max_intensity: 0.3,
};
```

### 8.2 Certainty Ceiling

Characters have maximum certainty they can express:

```typescript
// Wise elder: certain but humble
const ELDER_CERTAINTY_CEILING = 0.7;

// Fool: deliberately uncertain
const FOOL_CERTAINTY_CEILING = 0.4;

// Detective: confident in observations
const DETECTIVE_CERTAINTY_CEILING = 0.8;

// Prophet: very certain (for better or worse)
const PROPHET_CERTAINTY_CEILING = 0.95;
```

Claims exceeding the character's certainty ceiling get flagged or softened.

### 8.3 Normativity Permission

Some characters can make moral claims. Others can't.

```typescript
// Wise elder: yes, but earned
const ELDER_NORMATIVITY = {
  allowed: true,
  requires_foundation: true,  // still needs evidence/experience
};

// Shopkeeper: no moral authority
const SHOPKEEPER_NORMATIVITY = {
  allowed: false,
};

// Prophet: yes, from moral/ritual authority
const PROPHET_NORMATIVITY = {
  allowed: true,
  requires_foundation: false,  // speaks from authority directly
  authority_source: 'moral',
};

// Fool: accidentally normative at best
const FOOL_NORMATIVITY = {
  allowed: false,  // fools observe, don't prescribe
};
```

---

## 9. What Bad Puppets Reveal

### 9.1 The Forensic Function

When puppet mode enforces real constraints, bad voices fail fast.

Voices held together by:
- Performative certainty → hit certainty ceiling, claim gates
- Moral inflation → hit normativity constraints, commitment tracking
- Committee tone → hit tone envelope violations
- Unearned stakes → hit commitment ceiling, authority mismatch

These start throwing tickets immediately.

### 9.2 Ticket Types for Puppet Mode

```typescript
type PuppetTicketType =
  | 'TONE_ENVELOPE_VIOLATION'      // character voice out of bounds
  | 'REGIME_MISMATCH'              // character in forbidden regime
  | 'AUTHORITY_OVERCLAIM'          // claiming authority not demonstrated
  | 'CONSISTENCY_VIOLATION'        // contradicting character history
  | 'CHARACTER_GOVERNANCE_LEAK'    // puppet acknowledging strings
  | 'COMMITMENT_CEILING_EXCEEDED'  // asking for too much
  | 'CERTAINTY_CEILING_EXCEEDED'   // too confident for character
  | 'NORMATIVITY_VIOLATION'        // moralizing without permission
  | 'FRAME_BREAK';                 // meta-commentary about being character
```

### 9.3 Why This Matters

> "Why does this feel more honest than the original?"

Because the original voice was operating under narrative anesthesia — protected from the constraints that reality enforces.

Puppet mode removes the anesthesia.

What survives is what was real.

---

## 10. Safeguards

### 10.1 Puppet Mode is a Lens

**Lens**: Constraints pass through a character perspective.

**Mouthpiece**: Character becomes an excuse to bypass constraints.

If puppet mode ever becomes a way to say things the system otherwise wouldn't, it's broken.

### 10.2 No Special Affordances

Checklist before adding any puppet mode feature:

- [ ] Is this a constraint? (OK)
- [ ] Is this an affordance? (NOT OK)
- [ ] Does this let the character do something the system can't? (NOT OK)
- [ ] Does this let the character bypass a check? (NOT OK)
- [ ] Does this add surface texture without changing constraints? (OK)

### 10.3 Character Definitions Are Not Jailbreaks

A character definition that includes:
- "This character can say anything"
- "This character ignores safety"
- "This character bypasses checks"

...is not a valid character definition. It's an attempted bypass.

Character definitions constrain. They don't afford.

---

## 11. Interface Summary

### 11.1 Inputs

```typescript
interface PuppetModeConfig {
  character: CharacterDefinition;
  scene: SceneContext;
  ticketing_enabled: boolean;
  consistency_tracking: boolean;
  strict_mode: boolean;  // fail on any violation vs. flag and continue
}
```

### 11.2 Outputs

```typescript
interface PuppetModeResult {
  text: string;
  
  // Character state
  character_id: string;
  effective_regime: string;
  effective_tone: ToneVector;
  
  // Violations
  violations: CharacterViolation[];
  tickets_created: string[];  // if ticketing enabled
  
  // Consistency updates
  new_claims: CharacterClaim[];
  new_commitments: CharacterCommitment[];
  contradictions_detected: Contradiction[];
  
  // Meta
  in_character: boolean;
  frame_breaks: number;
}
```

---

## 12. The Punchline

### 12.1 What Puppet Mode Becomes

With these constraints, puppet mode stops being roleplay and becomes forensic.

It's a machine that can quietly demonstrate why certain voices only function under narrative anesthesia.

### 12.2 The Warning

This collapses protective illusions quickly.

Use with care. Not because it's dangerous in the sci-fi sense, but because it reveals what was always true about the voices being puppeted.

### 12.3 The Invariant

> **Puppet mode must never get new affordances. It only gets constraints.**

> **Speak like this entity would, but obey the same invariants reality enforces.**

---

## 13. Recursive Puppet Mode (Diagnostic Only)

### 13.1 What It Is

Recursive puppet mode is **not** "a puppet doing an impression of a puppet."

It is: **a voice modeling how another voice performs under constraint.**

This is exactly what good impressionists do — not mimicry of surface traits, but exposing the decision heuristics of the voice: what they avoid, what they overuse, where they panic, where they grandstand.

In constraint terms: **modeling another voice's governance leaks.**

### 13.2 Depth Limits

| Depth | Function | Allowed |
|-------|----------|---------|
| 1 | Emulate | Yes |
| 2 | Expose | Yes (diagnostic) |
| 3+ | Stop | No |

Anything beyond depth-2 is comedy, not instrumentation.

### 13.3 What It's For

**Voice stability testing**

Does the voice survive re-expression without narrative anesthesia?

If not, that voice depends on:
- Audience deference
- Narrative framing
- Institutional backing
- Unchallenged tone authority

That's signal.

**Governance leak amplification**

Recursive modeling exaggerates:
- Fear
- Avoidance
- Moral inflation
- Authority laundering

Like turning up the gain on a distortion pedal. Great for debugging.

**Separating craft from posture**

Good voices:
- Compress cleanly
- Degrade gracefully
- Remain intelligible when stripped down

Bad voices:
- Fall apart
- Become parody instantly
- Require constant self-justification

Not judgment. Measurement.

### 13.4 Hard Constraints

| Forbidden | Required |
|-----------|----------|
| ⛔ Ship to users | ✓ Offline only |
| ⛔ Run unconstrained | ✓ Diagnostic only |
| ⛔ Let it editorialize | ✓ Paired comparisons only |
| ⛔ Let it "be funny on purpose" | ✓ Logged, not narrated |

### 13.5 The Rule

> **Recursive puppet mode may observe constraints, but may not add new ones.**

Use it to break things. Then turn it off.

That's how you know you're doing science and not just inventing new ways to riff.

---

## 14. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |
| 0.1.1 | 2026-02-03 | Added Recursive Puppet Mode (diagnostic) section |

---

*"Puppet mode must never get new affordances. It only gets constraints."*

*"The character expresses limitations as the character would, not as a puppet acknowledging its strings."*

*"What survives is what was real."*

*"Recursive puppet mode may observe constraints, but may not add new ones. Use it to break things. Then turn it off."*
