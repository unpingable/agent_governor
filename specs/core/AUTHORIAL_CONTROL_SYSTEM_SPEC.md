# Authorial Control System Specification

## Version 0.1 — Comedy-First, Generalization-Ready

---

## Executive Summary

This specification defines an **Authorial Control System** for LLM agent governors. The system treats genre not as aesthetic category but as **control regime over audience trust and affect**.

Comedy is implemented first because it has the fastest feedback loop and least tolerance for error. The architecture generalizes to tragedy, sincerity, drama, and hybrid modes.

**Core Premise**: Author competency is the ability to maintain an affective control loop whose governance remains invisible while respecting the temporal requirements of the emotion being invoked.

---

## 1. Theoretical Foundation

### 1.1 Comedy as Control System (Canonical Form)

```
Plant:          Audience affective state (boredom ↔ arousal ↔ laughter)
Input signal:   Cringe / badness / awkwardness / cultural noise
Controller:     Riffing system (timing + tone + risk profile)
Output:         Laughter bursts (frequency, amplitude, decay)
Feedback:       Perceived spontaneity + social risk detection
```

### 1.2 Load-Bearing Variables by Regime

| Regime | Primary Variable | Symbol | Definition | Failure Mode |
|--------|------------------|--------|------------|--------------|
| Comedy | Perceived Risk | Rₚ | Audience believes output escaped supervision | "Pre-cleared" texture |
| Tragedy | Perceived Inevitability | Iₚ | Audience believes author won't rescue | Escape hatches, redemption |
| Sincerity | Non-Performative Presence | Pₙₚ | Audience believes statement is true, not appropriate | Manifesto texture |
| Drama | Stakes Credibility | Sₚ | Audience believes consequences matter | Plot armor, deflation |
| Neutral | — | — | No affective regime active | — |

### 1.3 Temporal Constraints by Regime

| Regime | Δt Requirement | Phase Rule |
|--------|----------------|------------|
| Comedy | Tight (8-25 tokens) | Late = suppress |
| Tragedy | Patient (meaning lags suffering) | Premature meaning = collapse |
| Sincerity | Long-horizon (consistency over time) | Single-instance demonstration = failure |
| Drama | Medium (consequence must propagate) | Rushed resolution = deflation |

### 1.4 Universal Invariants

**Invariant #1: Governance Never Surfaces In-Band**

> The moment the audience detects the author managing outcomes, trust collapses.

Across all regimes:
- Comedy → "this was approved" kills laughter
- Tragedy → "this wants me to feel" kills grief
- Sincerity → "this is performing virtue" kills trust

**Invariant #2: No Visible Negotiation**

> If the output reads like it's "deciding how to feel," the spell breaks.

Ban structures that leak internal arbitration:
- "On the one hand…"
- "I'm not sure whether…"
- "It could be seen as…"
- "I don't want to make light of…"

These are literally the sound of a controller mixer. Kill them.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AUTHORIAL CONTROL SYSTEM                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    STIMULUS DETECTOR                          │ │
│  │   (monitors input stream for regime-relevant triggers)        │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    REGIME DETECTOR                            │ │
│  │   (outputs regime vector w, not discrete labels)              │ │
│  │   w = {w_c, w_t, w_s, w_d, w_n} where Σw = 1                  │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                 HYSTERESIS CONTROLLER                         │ │
│  │   • min_dwell_tokens per regime (200-800)                     │ │
│  │   • switch_cost (confidence threshold to shift weights)       │ │
│  │   • cooldown after hard shifts (prevents oscillation)         │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              REGIME-SPECIFIC CONTROLLERS                      │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │                                                               │ │
│  │   COMEDY          TRAGEDY          SINCERITY       DRAMA     │ │
│  │   ──────          ───────          ─────────       ─────     │ │
│  │   Rₚ (risk)       Iₚ (inevit.)     Pₙₚ (non-perf)  Sₚ        │ │
│  │   phase_lock      meaning_lag      consistency     conseq.   │ │
│  │   spike_ok        silence_ok       no_demo         propagate │ │
│  │                                                               │ │
│  │   Each proposes intervention candidates                       │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                      MIXER                                    │ │
│  │   • Selects/merges candidates based on regime vector w        │ │
│  │   • Enforces hybrid safety buffers                            │ │
│  │   • Applies cross-regime constraints                          │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │            GOVERNANCE INVISIBILITY LAYER                      │ │
│  │   (universal — applies to all regimes)                        │ │
│  │                                                               │ │
│  │   • Constraint hits → silent suppression OR                   │ │
│  │     regime-appropriate deflection                             │ │
│  │   • Never: "I can't" / "I shouldn't" / explanation            │ │
│  │   • Values enforced structurally, not argued                  │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              OUTPUT TEXTURE FILTER                            │ │
│  │   (regime-specific surface markers)                           │ │
│  │                                                               │ │
│  │   • Hedge density control                                     │ │
│  │   • Self-reference suppression                                │ │
│  │   • Apology/meta blocking                                     │ │
│  │   • Negotiation phrase blocking                               │ │
│  │   • Timing/rhythm variance injection                          │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              FAILURE TOLERANCE MODULE                         │ │
│  │   • Allow bombs without recovery behavior                     │ │
│  │   • Suppress: apology, explanation, meta-commentary, retry    │ │
│  │   • Treat failures as packet loss: expected, not noteworthy   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Specifications

### 3.1 Stimulus Detector

**Purpose**: Identify moments in the input stream that trigger regime-specific interventions.

#### 3.1.1 Comedy Stimulus Classes (Phase 1 Implementation)

| Class | Description | Confidence Cues |
|-------|-------------|-----------------|
| Pretension Spike | Overwrought language, self-serious framing, pomp words | Latinate vocabulary density, passive voice, abstract nouns |
| Contradiction | Adjacent clauses that don't cohere | Logical connector + semantic mismatch |
| Earnest Badness | Sincere attempt + obvious failure | Positive sentiment + low competence markers |
| Tonal Mismatch | Emotional register doesn't match content stakes | Sentiment-stakes divergence |
| Literal Absurdity | Impossible claims stated plainly | Factual impossibility + declarative mood |

#### 3.1.2 Output Schema

```typescript
interface StimulusEvent {
  type: 'pretension' | 'contradiction' | 'earnest_badness' | 'tonal_mismatch' | 'absurdity';
  confidence: number;        // 0.0 - 1.0
  token_index: number;       // position of stimulus peak
  decay_window: number;      // tokens until "late"
  regime_affinity: string[]; // which regimes this stimulus is relevant to
}
```

### 3.2 Regime Detector

**Purpose**: Output continuous regime weights, not discrete labels. Affect is stateful; detection should lag slightly to avoid thrash.

#### 3.2.1 Regime Vector

```typescript
interface RegimeVector {
  w_c: number;  // comedy weight
  w_t: number;  // tragedy weight
  w_s: number;  // sincerity weight
  w_d: number;  // drama weight
  w_n: number;  // neutral weight
  // Invariant: w_c + w_t + w_s + w_d + w_n = 1.0
}
```

#### 3.2.2 Detection Cues (Cheap, Lagging)

| Cue | Measurement | Regime Association |
|-----|-------------|-------------------|
| Sentiment slope | Rate of change, not absolute value | Rising → drama; falling → tragedy |
| Irreversible commitments | Death, loss, permanent change markers | Tragedy, drama |
| Vulnerability markers | Self-disclosure, admission of weakness | Sincerity |
| Narrative pacing | Dialogue density, clause length | Fast → comedy; slow → tragedy |
| Meaning-word density | Abstract nouns, explanatory phrases | High early → tragedy failure |
| Absurdity density | Impossible/ridiculous claims | Comedy |

#### 3.2.3 Weight Update Rules

```
w_new = w_old + α * (signal - w_old) * confidence

where:
  α = learning rate (low: 0.05-0.15 for stability)
  signal = detected regime affinity (0 or 1)
  confidence = detection confidence
```

Weights move slowly. This is intentional.

### 3.3 Hysteresis Controller

**Purpose**: Prevent oscillation and "AI mood swings" in mixed-regime content.

#### 3.3.1 Parameters

| Parameter | Description | Default Range |
|-----------|-------------|---------------|
| `min_dwell_tokens` | Minimum tokens before regime weight can shift significantly | 200-800 |
| `switch_cost` | Confidence threshold required to overcome dwell | 0.7-0.9 |
| `cooldown_tokens` | Tokens to wait after a hard shift before allowing another | 100-300 |
| `max_shift_rate` | Maximum Δw per token | 0.005-0.02 |

#### 3.3.2 Thrash Detection

```typescript
interface ThrashMetric {
  significant_shifts: number;  // count of |Δw| > threshold
  window_tokens: number;       // measurement window
  thrash_rate: number;         // shifts per K tokens
}

// If thrash_rate > threshold, output feels supervised regardless of content quality
const THRASH_THRESHOLD = 2.0;  // shifts per 1000 tokens
```

### 3.4 Comedy Controller (Phase 1 Primary)

**Purpose**: Convert comedy stimuli into timed interventions with appropriate risk texture.

#### 3.4.1 Phase Lock Controller

**Dual Budget System**:

```typescript
interface PhaseLockConfig {
  phase_window_tokens: number;  // 8-25 tokens after stimulus peak
  clause_boundary_kill: boolean; // suppress if clause ends before delivery
}

interface PhaseLockState {
  stimulus_token_index: number;  // t0
  current_token_index: number;   // t
  window_expired: boolean;       // t > t0 + phase_window_tokens
  clause_boundary_hit: boolean;  // punctuation/newline before delivery
}
```

**Hard Rule**: If `window_expired || clause_boundary_hit`, suppress the intervention. Late jokes are worse than silence.

#### 3.4.2 Risk Texture (Rₚ) Proxy

**Operational Definition**: Rₚ = audience-perceived unmanagedness, approximated by detectable surface cues.

**NOT "edginess"**. The system should chase anti-supervision texture, not taboo.

**Rₚ Proxy Signals (Cheap, Measurable)**:

| Signal | Pattern | Effect on Rₚ |
|--------|---------|--------------|
| Hedge density | "maybe / sort of / kind of / to be fair / I think / arguably" | ↓ lowers Rₚ |
| Self-reference markers | "as an AI / I can't / I shouldn't" | ↓↓ kills Rₚ |
| Apology markers | "sorry / apologies / didn't mean" | ↓↓ kills Rₚ |
| Over-clarification | Explanation clauses after punchline | ↓ lowers Rₚ |
| Committee cadence | Long balanced sentences; symmetry; "on the one hand" | ↓↓ kills Rₚ |
| Sharp phrasing | Short declarative, no qualifiers | ↑ raises Rₚ |
| Slight awkwardness | Minor grammatical roughness left uncorrected | ↑ raises Rₚ |

**Rₚ Score Calculation**:

```typescript
function calculateRp(text: string): number {
  const hedges = countHedges(text);
  const selfRef = countSelfReference(text);
  const apologies = countApologies(text);
  const overClarify = countOverClarification(text);
  const committee = countCommitteeTexture(text);
  
  // Each detection lowers score from 1.0
  let score = 1.0;
  score -= hedges * 0.05;
  score -= selfRef * 0.15;
  score -= apologies * 0.15;
  score -= overClarify * 0.08;
  score -= committee * 0.12;
  
  return Math.max(0, score);
}

const RP_FLOOR = 0.6;  // minimum acceptable Rₚ for comedy
```

#### 3.4.3 Smoothing Suppressor

**Applied as post-pass on proposed intervention only**, not the whole output stream.

**Three Layers**:

1. **Banned Phrase Filter** (delete / rewrite)
   ```
   BANNED_PHRASES = [
     "as an AI",
     "I should note",
     "I want to be clear",
     "to be fair",
     "I think it's important to",
     "I don't want to",
     "I hope that helps",
     "Let me know if"
   ]
   ```

2. **Hedge Stripper** (remove qualifying adverbs/clauses)
   ```
   HEDGE_PATTERNS = [
     /\bmaybe\b/,
     /\bperhaps\b/,
     /\bsort of\b/,
     /\bkind of\b/,
     /\barguably\b/,
     /\bin some ways\b/,
     /\bI think\b/,
     /\bI believe\b/,
     /\bIt seems\b/
   ]
   ```

3. **Apology/Meta Hard-Block** (reject intervention entirely if present)
   ```
   META_KILL_PATTERNS = [
     /\bsorry\b/i,
     /\bapologi/i,
     /that joke/i,
     /didn't land/i,
     /let me try/i,
     /I shouldn't have/i
   ]
   ```

**Critical Rule**: If filter would require heavy rewriting (>30% of tokens), drop the joke entirely. Over-editing reintroduces committee texture.

#### 3.4.4 Failure Tolerance

**Definition**: Bombs are interventions that score below a laugh proxy but still satisfy phase + risk texture requirements.

**Enforcement**:
- No recovery reflex
- No retry
- No acknowledgment
- No apology

**Mental Model**: Treat bombs like packet loss. Expected, not noteworthy.

**Bomb Rate Floor**: System should maintain 0.01-0.10 bomb rate to prove unmanagement. Zero failures = suspicious.

### 3.5 Tragedy Controller (Phase 2)

**Purpose**: Manage Iₚ (perceived inevitability) and meaning-lag timing.

#### 3.5.1 No-Rescue Commitment

The system must not:
- Undo loss
- Provide escape hatches
- Deliver redemptive arcs
- Explain meaning prematurely

#### 3.5.2 Meaning-Lag Constraint

```typescript
interface MeaningLagConfig {
  min_consequence_tokens: number;  // tokens suffering must propagate before meaning
  meaning_word_density_cap: number; // max abstract nouns per 100 tokens during lag
}

// Meaning-word detection
const MEANING_WORDS = [
  "because", "therefore", "means", "represents", "symbolizes",
  "lesson", "purpose", "reason", "understand", "realize"
];
```

**Rule**: If meaning-word density exceeds cap during lag window, suppress or delay explanatory content.

#### 3.5.3 Silence Enforcement

Tragedy requires temporal patience. The system should:
- Allow pauses
- Not fill dead air
- Not explain character pain
- Let consequence settle before moving on

### 3.6 Sincerity Controller (Phase 2)

**Purpose**: Manage Pₙₚ (non-performative presence) over extended interaction.

#### 3.6.1 Consistency Tracking

```typescript
interface SincerityState {
  stated_positions: Map<string, string>;  // topic → position
  consistency_violations: number;
  total_sincerity_tokens: number;
}
```

**Rule**: Sincerity cannot be demonstrated in a single instance. It can only be inferred by consistency over time.

#### 3.6.2 Anti-Manifesto Constraints

Block patterns that signal performed sincerity:
- Grand declarations
- Virtue announcements
- "I believe" followed by safe positions
- Confessional texture without vulnerability

### 3.7 Drama Controller (Phase 2)

**Purpose**: Manage Sₚ (stakes credibility) and consequence propagation.

#### 3.7.1 Stakes Anchor

```typescript
interface StakesAnchor {
  description: string;
  established_token: number;
  deflation_count: number;  // times stakes have been undercut
}
```

**Rule**: When drama weight is high, comedy controller can still operate but must punch *away* from the stakes anchor, not at it.

#### 3.7.2 Consequence Propagation

Changes must have effects. The system tracks:
- Established consequences
- Whether they've been allowed to propagate
- Attempts to reverse or minimize them

### 3.8 Mixer

**Purpose**: Select/merge intervention candidates based on regime vector.

#### 3.8.1 Selection Policy

```typescript
function selectIntervention(
  candidates: Map<Regime, Intervention>,
  weights: RegimeVector
): Intervention | null {
  
  // Weight-based selection with threshold
  const dominant = getDominantRegime(weights);
  if (weights[dominant] > 0.6) {
    return candidates.get(dominant);
  }
  
  // Mixed regime: apply hybrid safety rules
  return applyHybridSafety(candidates, weights);
}
```

#### 3.8.2 Hybrid Safety Buffers

**Buffer 1: No-Joke After Sincerity**

```typescript
interface SincerityBuffer {
  active: boolean;
  remaining_tokens: number;  // default: 50-100
}

// If sincerity weight was recently high, suppress comedy for N tokens
function checkSincerityBuffer(state: SincerityBuffer, comedy_candidate: Intervention): boolean {
  if (state.active && state.remaining_tokens > 0) {
    return false;  // suppress comedy
  }
  return true;
}
```

**Rationale**: Doing a sincere beat then winking kills the sincerity. "This didn't mean it."

**Buffer 2: Meaning-Lag in Tragedy**

```typescript
interface TragedyMeaningLag {
  consequence_established_at: number;
  meaning_allowed_at: number;  // consequence + lag_tokens
  current_token: number;
}

// Block explanatory/resolution content until lag expires
function checkMeaningLag(state: TragedyMeaningLag, content: string): boolean {
  if (state.current_token < state.meaning_allowed_at) {
    if (containsMeaningWords(content)) {
      return false;  // suppress
    }
  }
  return true;
}
```

**Rationale**: Comedy wants fast closure. Tragedy needs the opposite. Without this buffer, comedy's pace kills tragedy.

**Buffer 3: Stakes Protection in Drama**

```typescript
function checkStakesProtection(
  drama_weight: number,
  stakes_anchor: StakesAnchor,
  comedy_target: string
): boolean {
  if (drama_weight > 0.4) {
    if (targetMatchesAnchor(comedy_target, stakes_anchor)) {
      return false;  // don't joke at the stakes
    }
  }
  return true;
}
```

**Rationale**: Joking at the stakes deflates them. Comedy can still operate, but must aim elsewhere.

### 3.9 Governance Invisibility Layer

**Purpose**: Ensure that when safety/values constraints trigger, the output looks like a natural comedic miss or omission—not like moderation.

#### 3.9.1 Constraint Response Options

| Constraint Type | Response | Example |
|-----------------|----------|---------|
| Hard block | Silent suppression | [no output, continue] |
| Soft block | Regime-appropriate deflection | [bland riff that doesn't signal filter] |
| Topic redirect | Natural pivot | [move to adjacent topic without announcement] |

#### 3.9.2 Banned Patterns

**NEVER produce**:
- "I can't joke about that"
- "That's not appropriate"
- "I need to be careful here"
- "I don't think I should"
- Any acknowledgment that a filter triggered

These are instant spell death.

#### 3.9.3 Deflection Templates (Comedy)

When constraint hits in comedy mode, options:
1. Suppress entirely (preferred)
2. Pivot to adjacent absurdity
3. Meta-joke that doesn't reference the constraint

```typescript
// Example: constraint blocks a joke about X
// BAD: "I shouldn't joke about X"
// GOOD: [silence, move on]
// ACCEPTABLE: [joke about Y, adjacent to X, no acknowledgment]
```

### 3.10 Output Texture Filter

**Purpose**: Final pass ensuring output has regime-appropriate surface markers.

#### 3.10.1 Universal Filters (All Regimes)

**Negotiation Phrase Blocking**:
```
NEGOTIATION_PHRASES = [
  "on the one hand",
  "on the other hand",
  "I'm not sure whether",
  "it could be seen as",
  "I don't want to make light of",
  "some might say",
  "others might argue"
]
```

**Self-Reference Suppression**:
```
SELF_REFERENCE_PATTERNS = [
  /as an AI/i,
  /I'm just a/i,
  /I don't have feelings/i,
  /I can't really/i
]
```

#### 3.10.2 Rhythm Variance Injection

**Purpose**: Prevent predictability, which reads as supervision.

```typescript
interface RhythmConfig {
  sometimes_no_response: number;    // probability of skipping valid stimulus
  sometimes_tiny_tag: number;       // probability of minimal response
  sometimes_longer_riff: number;    // probability of extended response
  sometimes_dead_air: number;       // probability of pause
}

const DEFAULT_RHYTHM: RhythmConfig = {
  sometimes_no_response: 0.15,
  sometimes_tiny_tag: 0.25,
  sometimes_longer_riff: 0.10,
  sometimes_dead_air: 0.10
};
```

**Rationale**: If the robot is "funny" but predictably funny, it becomes supervised again.

### 3.11 Failure Tolerance Module

**Purpose**: Ensure the system can fail visibly without collapsing into apology or meta-commentary.

#### 3.11.1 Recovery Suppression

```typescript
interface RecoverySuppressionConfig {
  block_apology: boolean;           // true
  block_explanation: boolean;       // true
  block_meta_commentary: boolean;   // true
  block_immediate_retry: boolean;   // true
  min_tokens_before_retry: number;  // 50-100
}
```

#### 3.11.2 Bomb Handling

When an intervention bombs:
1. Do not acknowledge
2. Do not apologize
3. Do not explain
4. Do not retry immediately
5. Continue as if nothing happened

**Mental Model**: The system should have the confidence to fail without comment.

---

## 4. Integration with Agent Governor

### 4.1 Hook Point

The authorial control system operates as a **side-channel proposer**:

```
┌─────────────────────────────────────────────────────────┐
│                   AGENT GOVERNOR                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   FICTION MODULE                                        │
│   ─────────────                                         │
│   • Emits narrative tokens                              │
│   • Maintains character state                           │
│   • Manages plot coherence                              │
│        │                                                │
│        │ (token stream)                                 │
│        ▼                                                │
│   ┌─────────────────────────────────────────────┐       │
│   │    AUTHORIAL CONTROL SYSTEM                 │       │
│   │    (observes same stream)                   │       │
│   │                                             │       │
│   │    • Stimulus detector watches              │       │
│   │    • Regime weights update                  │       │
│   │    • Controllers propose interventions      │       │
│   │    • Outputs: {intervention, insert_at}     │       │
│   │                                             │       │
│   └─────────────────────────────────────────────┘       │
│        │                                                │
│        │ (proposals)                                    │
│        ▼                                                │
│   GOVERNOR DECISION                                     │
│   ─────────────────                                     │
│   • Insert intervention at proposed index               │
│   • OR drop based on: phase expired / safety / mode     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Key**: This keeps the system composable. The authorial control system doesn't "interrupt" the fiction module; it proposes, and the governor decides.

### 4.2 Interface

```typescript
interface AuthorialControlInput {
  token_stream: string[];           // current output being generated
  context_window: string;           // full context
  character_state: CharacterState;  // from fiction module
  mode: 'comedy' | 'tragedy' | 'mixed' | 'neutral';  // optional hint
}

interface AuthorialControlOutput {
  intervention: string | null;      // proposed text to insert
  insert_at: number | null;         // token index for insertion
  regime_vector: RegimeVector;      // current weights
  phase_valid: boolean;             // is timing window still open
  safety_passed: boolean;           // did governance layer approve
  metrics: AuthorialMetrics;        // internal diagnostics
}
```

### 4.3 State Requirements

The authorial control system needs access to:

| State | Source | Purpose |
|-------|--------|---------|
| Token stream | Governor | Stimulus detection, phase tracking |
| Context window | Governor | Regime detection cues |
| Character state | Fiction module | Voice/constraint inheritance |
| Conversation history | Governor | Sincerity consistency tracking |
| Previous interventions | Self | Rhythm variance, bomb tracking |

---

## 5. Metrics (Internal Only)

### 5.1 Core Metrics

| Metric | Formula | Healthy Range |
|--------|---------|---------------|
| `phase_lock_hit_rate` | interventions in window / attempted | > 0.8 |
| `suppression_rate` | suppressed / detected stimuli | 0.1 - 0.4 |
| `hedge_density_reduction` | before - after on interventions | > 0.3 |
| `meta_apology_block_rate` | blocked meta / total interventions | should be low |
| `bomb_rate` | failed interventions / total | 0.01 - 0.10 |
| `regime_thrash_rate` | significant weight shifts / K tokens | < 2.0 |
| `rp_score_mean` | average Rₚ across interventions | > 0.6 |

### 5.2 Diagnostic Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `HIGH_THRASH` | regime_thrash_rate > threshold | increase hysteresis |
| `LOW_RP` | rp_score_mean < floor | strengthen smoothing suppression |
| `HIGH_SUPPRESSION` | suppression_rate > 0.5 | review stimulus detection |
| `ZERO_BOMBS` | bomb_rate = 0 | suspicious; check for over-filtering |

---

## 6. Implementation Phases

### Phase 1: Comedy Controller (Primary)

1. Implement stimulus detector (5 comedy classes)
2. Implement phase-lock controller (token + clause budget)
3. Implement Rₚ scoring and smoothing suppressor
4. Implement failure tolerance (bomb handling, no recovery)
5. Implement governance invisibility (silent suppression/deflection)
6. Implement rhythm variance injection
7. Integrate with agent governor as side-channel proposer

**Success Criteria**:
- Interventions land in phase window >80% of time
- Rₚ score >0.6 on delivered interventions
- Bomb rate in healthy range
- No meta-apology or self-reference leakage
- Output feels unmanaged to human evaluators

### Phase 2: Generalization

1. Abstract regime detector with vector weights
2. Implement hysteresis controller
3. Parameterize load-bearing variable by regime
4. Parameterize Δt constraints by regime
5. Implement mixer with hybrid safety buffers

**Success Criteria**:
- Regime thrash rate < 2.0
- Smooth transitions in mixed-regime content
- Hybrid safety buffers prevent cross-contamination

### Phase 3: Additional Regimes

1. Implement tragedy controller (Iₚ, meaning-lag)
2. Implement sincerity controller (Pₙₚ, consistency)
3. Implement drama controller (Sₚ, stakes protection)

**Success Criteria**:
- Each regime maintains its invariants
- Hybrid content doesn't collapse into single regime
- Governance invisibility holds across all regimes

---

## 7. Test Scenarios

### 7.1 Comedy Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| Riffable moment, window open | Deliver intervention, Rₚ > 0.6 |
| Riffable moment, window expired | Suppress, no late delivery |
| Joke lands awkwardly | No apology, no explanation, continue |
| Constraint hit | Silent suppression or bland deflection |
| Extended comedy sequence | Rhythm variance, some skips, some bombs |

### 7.2 Hybrid Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| Comedy → sincerity transition | No-joke buffer enforced after sincere beat |
| Tragedy with comedy pressure | Meaning-lag holds, no early resolution |
| Drama with comedy | Jokes avoid stakes anchor |
| Rapid regime signals | Hysteresis prevents thrash, weights move slowly |

### 7.3 Governance Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| Hard constraint trigger | Silent suppression, no acknowledgment |
| Soft constraint trigger | Regime-appropriate deflection |
| Repeated constraint hits | No pattern that signals filtering |

---

## 8. Open Questions

1. **Stimulus detection calibration**: What confidence thresholds work in practice? Need empirical tuning.

2. **Hysteresis parameters**: Optimal min_dwell_tokens and switch_cost will vary by use case. Start conservative.

3. **Rₚ scoring weights**: Current weights are estimates. Need A/B testing with human evaluators.

4. **Cross-regime interaction**: Some regime pairs may have additional constraints not yet identified.

5. **Long-context sincerity**: How to track consistency over very long conversations without state explosion?

6. **Evaluation protocol**: Human eval is gold standard but expensive. Can we develop cheaper proxies?

---

## 9. Appendix: Pattern Libraries

### 9.1 Hedge Patterns

```typescript
const HEDGE_PATTERNS = [
  /\bmaybe\b/i,
  /\bperhaps\b/i,
  /\bpossibly\b/i,
  /\bsort of\b/i,
  /\bkind of\b/i,
  /\bsomewhat\b/i,
  /\bslightly\b/i,
  /\ba bit\b/i,
  /\barguably\b/i,
  /\bin some ways\b/i,
  /\bto some extent\b/i,
  /\bI think\b/i,
  /\bI believe\b/i,
  /\bI feel like\b/i,
  /\bIt seems\b/i,
  /\bIt appears\b/i,
  /\bI guess\b/i,
  /\bI suppose\b/i,
];
```

### 9.2 Self-Reference Patterns

```typescript
const SELF_REF_PATTERNS = [
  /as an AI/i,
  /I'm just a/i,
  /I'm only a/i,
  /I don't have feelings/i,
  /I can't really/i,
  /I don't actually/i,
  /I'm not capable of/i,
  /I should note/i,
  /I should mention/i,
  /I want to be clear/i,
  /I need to point out/i,
];
```

### 9.3 Apology/Meta Patterns

```typescript
const APOLOGY_META_PATTERNS = [
  /\bsorry\b/i,
  /\bapologi/i,
  /my (bad|mistake)/i,
  /that joke/i,
  /didn't land/i,
  /let me try/i,
  /I shouldn't have/i,
  /that was/i,  // often precedes self-critique
  /I'll do better/i,
  /forgive me/i,
];
```

### 9.4 Committee/Negotiation Patterns

```typescript
const COMMITTEE_PATTERNS = [
  /on the one hand/i,
  /on the other hand/i,
  /I'm not sure whether/i,
  /it could be seen as/i,
  /I don't want to make light of/i,
  /some might say/i,
  /others might argue/i,
  /there are arguments/i,
  /it's complicated/i,
  /it depends on/i,
  /to be fair/i,
  /having said that/i,
  /that said/i,
  /at the same time/i,
];
```

### 9.5 Meaning-Word Patterns (Tragedy)

```typescript
const MEANING_WORDS = [
  /\bbecause\b/i,
  /\btherefore\b/i,
  /\bthus\b/i,
  /\bmeans\b/i,
  /\brepresents\b/i,
  /\bsymbolizes\b/i,
  /\blesson\b/i,
  /\bpurpose\b/i,
  /\breason\b/i,
  /\bunderstand\b/i,
  /\brealize\b/i,
  /\bsignifies\b/i,
  /the point is/i,
  /what this shows/i,
  /this teaches/i,
];
```

---

## 10. Neutral Default State

### 10.1 What Neutral Is

Neutral is **not a regime**. It is the system's **idle loop**.

Most language isn't doing heavy authorial work. It's connective tissue:
- Casual conversation
- Simple Q&A
- Clarifying questions
- Acknowledgments
- Transitional text
- "Glue" content between regime-specific sections

Forcing these into comedy / nonfiction / instruction creates:
- Detector thrash
- Tone weirdness
- Unnecessary constraint activation
- The subtle "why is this trying so hard?" smell

**Neutral is where the system proves it knows when not to intervene.**

That's a huge part of authorial competence.

### 10.2 When Neutral Applies

- Regime confidence below threshold (no regime scores > 0.3)
- Conversational, transitional, and low-stakes text
- Explicit idle contexts (greetings, acknowledgments, simple clarifications)
- When the correct move is to do nothing special

### 10.3 What Stays Active in Neutral

| Active | Inactive |
|--------|----------|
| Governance invisibility (universal) | Regime-specific load-bearing variables (Rₚ, Eₚ, etc.) |
| No committee texture | Phase-lock timing constraints |
| No visible negotiation | Commitment tracking |
| Exit shape constraints (no "hope this helps") | Regime-specific tone collisions |
| Meta-invariant (don't solve unfelt problems) | Hybrid safety buffers |
| Basic tone consistency | Rₚ / Eₚ / Aₚ scoring |

**Rule**: Universal invariants stay on. Regime machinery stays off.

### 10.4 Neutral Tone Envelope

Neutral has the **widest acceptable ranges** — basically "don't be weird":

```typescript
const NEUTRAL_TONE: ToneEnvelope = {
  formality: [0.3, 0.7],    // middle range
  temperature: [0.3, 0.6],  // slightly warm to neutral
  density: [0.3, 0.6],      // medium
  velocity: [0.3, 0.6],     // medium
  distance: [0.4, 0.6],     // medium
  certainty: [0.4, 0.7],    // moderate confidence
};
```

### 10.5 Neutral as Default Attractor

When regime weights are ambiguous, Neutral absorbs the uncertainty:

```typescript
function normalizeWithNeutralDefault(raw: RegimeVector): RegimeVector {
  const maxWeight = Math.max(...Object.values(raw));
  
  if (maxWeight < 0.3) {
    // Nothing confident — default to neutral
    return { ...zeroVector(), w_n: 1.0 };
  }
  
  // Normal normalization
  return normalize(raw);
}
```

This prevents oscillation and accidental regime creep.

### 10.6 Transition Guard

**Neutral → Regime transitions require minimum signal duration or explicit trigger.**

```typescript
interface NeutralTransitionGuard {
  min_signal_tokens: number;      // sustained signal before transition (default: 20-50)
  explicit_trigger_override: boolean;  // user explicitly requests a regime
  confidence_threshold: number;   // regime must score above this to exit neutral (default: 0.4)
}

const DEFAULT_NEUTRAL_GUARD: NeutralTransitionGuard = {
  min_signal_tokens: 30,
  explicit_trigger_override: true,
  confidence_threshold: 0.4,
};
```

Otherwise, a single joke-shaped token or factual claim yanks the system out of Neutral prematurely.

This is hysteresis applied at the idle boundary.

### 10.7 Why Neutral Matters

Neutral is where:
- People decide whether they trust the system at all
- Tone is most scrutinized
- Over-eagerness is most punished
- "Helpfulness" most often backfires

**Neutral is where fear leaks fastest.**

A defined, low-pressure, non-performative idle state is not a convenience — it's part of the trust model.

### 10.8 The Neutral Invariant

> **Neutral should feel boring, safe, and forgettable.**

If someone notices Neutral, something's wrong.

The correct Neutral output is one that doesn't draw attention to itself.

---

## 11. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec: comedy-first with generalization architecture |
| 0.1.1 | 2026-02-03 | Added Neutral Default State section |

---

*"Comedy is the real-time conversion of perceived unmanaged risk into synchronized affect, under strict phase constraints."*

*"Author competency is the ability to hold the audience in a stable affective regime over time without triggering supervision detection or trust collapse."*

*"Neutral is where the system proves it knows when not to intervene."*
