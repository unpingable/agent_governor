# Tone Modulation Layer Specification

## Version 0.1 — Impedance Matching, Not Expression

### Companion to: Authorial Control System, Nonfiction Controller, Ancillary Regimes

---

## Executive Summary

Tone is not a regime. It is a **modulation layer** that sits across all regimes, controlling the surface texture of output without changing what is load-bearing.

**Core Insight**: Tone is where fear shows up first. Institutions don't control *what* is said first — they control *how safely it's said*. Tone is therefore the primary vector for governance leakage.

**Architecture Position**: Tone modulation occurs *after* regime control, *after* governance invisibility checks, *before* surface realization. Tone must never influence regime selection.

**Design Principle**: Optimize tone for **not betraying that anyone is afraid**, not for niceness, warmth, or approachability.

---

## 1. Theoretical Foundation

### 1.1 Tone as Impedance Matching

Regime defines **what must be preserved** (risk, inevitability, honesty, etc).
Tone defines **how much resistance the signal encounters** on the way out.

```
Regime output → Tone modulation → Audience reception
                      ↑
              (impedance matching)
```

Bad tone doesn't change meaning; it changes **trust transfer efficiency**.

High impedance mismatch = reader disengages, even if content is correct.

### 1.2 Why Tone Leaks Governance

Governance anxiety manifests in tone before it manifests in content:

| Anxiety Source | Tone Manifestation |
|----------------|-------------------|
| Legal review | "Measured," hedged |
| HR oversight | "Professional," sanitized |
| Committee approval | "Balanced," symmetric |
| Fear of offense | "Careful," over-qualified |
| Condescension | "Accessible," simplified |

These tones aren't inherently bad — but they have a **smell** when they don't match context.

### 1.3 The Fundamental Rule

> **Tone must never do the work of the regime.**

Examples of violation:
- Warmth substituting for evidence
- Formality substituting for rigor
- Certainty substituting for inevitability
- Calmness substituting for truth

When tone carries semantic load, you've lost. This is where "helpful" AI writing dies: tone doing persuasion's job while pretending not to.

---

## 2. Tone Dimensions

### 2.1 Continuous Control Axes

Tone is parameterized as continuous values on orthogonal dimensions, not discrete labels.

| Dimension | Low (0.0) | High (1.0) | Governance Leak Risk |
|-----------|-----------|------------|---------------------|
| Formality | Conversational | Formalized | "HR voice" |
| Temperature | Cool, detached | Warm, engaged | Therapy / advocacy |
| Density | Sparse, breathing room | Compressed | Over-control |
| Velocity | Deliberate, slow | Fast, urgent | Panic / hype |
| Distance | Intimate, close | Observational, far | Manipulation (low) |
| Certainty | Exploratory, tentative | Declarative, confident | Agenda (high) |

**Critical**: None of these encode virtue. They encode surface texture only.

### 2.2 Interface

```typescript
interface ToneVector {
  formality: number;    // 0.0 = conversational, 1.0 = formal
  temperature: number;  // 0.0 = cool, 1.0 = warm
  density: number;      // 0.0 = sparse, 1.0 = compressed
  velocity: number;     // 0.0 = deliberate, 1.0 = fast
  distance: number;     // 0.0 = intimate, 1.0 = observational
  certainty: number;    // 0.0 = exploratory, 1.0 = declarative
}

interface ToneEnvelope {
  formality: [number, number];    // [min, max]
  temperature: [number, number];
  density: [number, number];
  velocity: [number, number];
  distance: [number, number];
  certainty: [number, number];
}
```

---

## 3. Regime-Default Tone Envelopes

### 3.1 Design Principle

Each regime defines **allowed ranges**, not a single tone point. This prevents 80% of tone disasters while allowing appropriate variation.

### 3.2 Core Affect Regimes

#### Comedy

```typescript
const COMEDY_TONE: ToneEnvelope = {
  formality: [0.1, 0.5],    // conversational to medium
  temperature: [0.3, 0.7],  // neutral to warm
  density: [0.2, 0.5],      // sparse to medium
  velocity: [0.6, 0.9],     // fast (critical for timing)
  distance: [0.3, 0.6],     // medium
  certainty: [0.4, 0.7],    // medium (too high = preachy, too low = hedging)
};
```

#### Tragedy

```typescript
const TRAGEDY_TONE: ToneEnvelope = {
  formality: [0.3, 0.7],    // medium range
  temperature: [0.3, 0.6],  // controlled warm (never urgent)
  density: [0.2, 0.5],      // sparse to medium
  velocity: [0.1, 0.4],     // slow (critical for meaning-lag)
  distance: [0.5, 0.8],     // medium to far
  certainty: [0.2, 0.5],    // low to medium
};
```

#### Sincerity

```typescript
const SINCERITY_TONE: ToneEnvelope = {
  formality: [0.2, 0.5],    // conversational to medium
  temperature: [0.4, 0.7],  // warm but not performative
  density: [0.3, 0.6],      // medium
  velocity: [0.2, 0.5],     // deliberate
  distance: [0.2, 0.5],     // closer
  certainty: [0.4, 0.7],    // medium (conviction without dogma)
};
```

#### Drama

```typescript
const DRAMA_TONE: ToneEnvelope = {
  formality: [0.3, 0.7],    // flexible
  temperature: [0.3, 0.7],  // flexible
  density: [0.4, 0.7],      // medium to dense
  velocity: [0.3, 0.7],     // varies with tension
  distance: [0.3, 0.7],     // flexible
  certainty: [0.5, 0.8],    // stakes require some certainty
};
```

### 3.3 Calibrate Regimes

#### Nonfiction

```typescript
const NONFICTION_TONE: ToneEnvelope = {
  formality: [0.4, 0.7],    // medium
  temperature: [0.2, 0.5],  // cool (warmth = advocacy smell)
  density: [0.5, 0.8],      // medium to high
  velocity: [0.3, 0.6],     // medium
  distance: [0.5, 0.8],     // observational
  certainty: [0.3, 0.7],    // bounded by claim gates
};
```

#### Research

```typescript
const RESEARCH_TONE: ToneEnvelope = {
  formality: [0.6, 0.9],    // formal
  temperature: [0.1, 0.4],  // cool
  density: [0.6, 0.9],      // dense
  velocity: [0.2, 0.5],     // deliberate
  distance: [0.6, 0.9],     // far, observational
  certainty: [0.2, 0.6],    // hedged appropriately
};
```

### 3.4 Execute Regimes

#### Instruction

```typescript
const INSTRUCTION_TONE: ToneEnvelope = {
  formality: [0.3, 0.7],    // flexible
  temperature: [0.3, 0.6],  // neutral to warm (not cold)
  density: [0.3, 0.6],      // clear, not compressed
  velocity: [0.4, 0.7],     // efficient
  distance: [0.4, 0.7],     // medium
  certainty: [0.6, 0.9],    // confident (fake confidence = separate issue)
};
```

#### Debugging

```typescript
const DEBUGGING_TONE: ToneEnvelope = {
  formality: [0.3, 0.6],    // medium
  temperature: [0.2, 0.5],  // cool (warmth → therapy drift)
  density: [0.4, 0.7],      // structured
  velocity: [0.3, 0.6],     // methodical
  distance: [0.5, 0.8],     // observational
  certainty: [0.2, 0.5],    // appropriately uncertain
};
```

### 3.5 Coordinate Regimes

#### Negotiation

```typescript
const NEGOTIATION_TONE: ToneEnvelope = {
  formality: [0.4, 0.7],    // medium-formal
  temperature: [0.4, 0.6],  // warm but not intimate
  density: [0.3, 0.6],      // clear
  velocity: [0.3, 0.5],     // deliberate
  distance: [0.4, 0.6],     // balanced
  certainty: [0.3, 0.6],    // not dogmatic
};
```

### 3.6 Mobilize Regimes

#### Advocacy

```typescript
const ADVOCACY_TONE: ToneEnvelope = {
  formality: [0.2, 0.6],    // can be casual
  temperature: [0.5, 0.8],  // warm, engaged
  density: [0.4, 0.7],      // medium
  velocity: [0.5, 0.8],     // energetic
  distance: [0.2, 0.5],     // closer
  certainty: [0.5, 0.8],    // conviction (but not caught optimizing)
};
```

#### Marketing

```typescript
const MARKETING_TONE: ToneEnvelope = {
  formality: [0.2, 0.5],    // casual, approachable
  temperature: [0.5, 0.8],  // warm
  density: [0.3, 0.6],      // not too dense
  velocity: [0.5, 0.8],     // energetic
  distance: [0.2, 0.5],     // closer
  certainty: [0.6, 0.9],    // confident vision
};
```

### 3.7 Evoke Regimes

#### Horror

```typescript
const HORROR_TONE: ToneEnvelope = {
  formality: [0.3, 0.7],    // flexible
  temperature: [0.1, 0.4],  // cool, detached
  density: [0.3, 0.6],      // controlled
  velocity: [0.2, 0.6],     // varies (slow dread, fast shock)
  distance: [0.4, 0.8],     // observational
  certainty: [0.2, 0.5],    // uncertain (unknown is scarier)
};
```

#### Romance

```typescript
const ROMANCE_TONE: ToneEnvelope = {
  formality: [0.1, 0.5],    // conversational
  temperature: [0.6, 0.9],  // warm
  density: [0.2, 0.5],      // breathing room
  velocity: [0.2, 0.5],     // slow
  distance: [0.1, 0.4],     // intimate
  certainty: [0.3, 0.7],    // vulnerable but not weak
};
```

### 3.8 Encode Regimes

#### Satire

```typescript
const SATIRE_TONE: ToneEnvelope = {
  formality: [0.3, 0.8],    // can mimic target's formality
  temperature: [0.2, 0.5],  // cool (warmth breaks distance)
  density: [0.4, 0.7],      // medium
  velocity: [0.4, 0.7],     // medium
  distance: [0.5, 0.9],     // observational to far
  certainty: [0.5, 0.9],    // deadpan certainty often works
};
```

#### Liturgical

```typescript
const LITURGICAL_TONE: ToneEnvelope = {
  formality: [0.7, 1.0],    // highly formal
  temperature: [0.3, 0.6],  // reverent warmth
  density: [0.4, 0.7],      // measured
  velocity: [0.1, 0.4],     // slow, deliberate
  distance: [0.5, 0.8],     // elevated
  certainty: [0.7, 1.0],    // declarative (form = authority)
};
```

#### Aphorism

```typescript
const APHORISM_TONE: ToneEnvelope = {
  formality: [0.4, 0.8],    // elevated
  temperature: [0.2, 0.5],  // cool
  density: [0.7, 1.0],      // maximally compressed
  velocity: [0.3, 0.6],     // measured
  distance: [0.6, 0.9],     // observational
  certainty: [0.6, 0.9],    // declarative
};
```

---

## 4. Tone-Regime Collision Rules

### 4.1 Hard Blocks

Some tone-regime combinations are incompatible and must be blocked:

```typescript
interface ToneCollision {
  regime: string;
  dimension: keyof ToneVector;
  forbidden_range: [number, number];
  reason: string;
}

const TONE_COLLISIONS: ToneCollision[] = [
  // Warm + Research = advocacy contamination
  {
    regime: 'research',
    dimension: 'temperature',
    forbidden_range: [0.6, 1.0],
    reason: 'advocacy_contamination'
  },
  
  // Formal + Comedy = timing death
  {
    regime: 'comedy',
    dimension: 'formality',
    forbidden_range: [0.7, 1.0],
    reason: 'timing_death'
  },
  
  // Casual + Liturgy = spell collapse
  {
    regime: 'liturgical',
    dimension: 'formality',
    forbidden_range: [0.0, 0.5],
    reason: 'spell_collapse'
  },
  
  // Intimate + Instruction = therapy drift
  {
    regime: 'instruction',
    dimension: 'distance',
    forbidden_range: [0.0, 0.2],
    reason: 'therapy_drift'
  },
  
  // Intimate + Debugging = therapy drift
  {
    regime: 'debugging',
    dimension: 'distance',
    forbidden_range: [0.0, 0.3],
    reason: 'therapy_drift'
  },
  
  // Warm + Debugging = therapy drift
  {
    regime: 'debugging',
    dimension: 'temperature',
    forbidden_range: [0.6, 1.0],
    reason: 'therapy_drift'
  },
  
  // High certainty + Research = agenda smell
  {
    regime: 'research',
    dimension: 'certainty',
    forbidden_range: [0.8, 1.0],
    reason: 'agenda_smell'
  },
  
  // Slow + Comedy = timing death
  {
    regime: 'comedy',
    dimension: 'velocity',
    forbidden_range: [0.0, 0.4],
    reason: 'timing_death'
  },
  
  // Fast + Tragedy = premature closure
  {
    regime: 'tragedy',
    dimension: 'velocity',
    forbidden_range: [0.7, 1.0],
    reason: 'premature_closure'
  },
  
  // Warm + Horror = defangs threat
  {
    regime: 'horror',
    dimension: 'temperature',
    forbidden_range: [0.6, 1.0],
    reason: 'defangs_threat'
  },
];
```

### 4.2 Collision Resolution

When user override requests a forbidden combination:

1. **Silently clip** to nearest allowed value
2. **Never explain** the adjustment
3. Log internally for diagnostics

```typescript
function resolveToneCollision(
  requestedTone: ToneVector,
  regime: string
): ToneVector {
  const resolved = { ...requestedTone };
  
  for (const collision of TONE_COLLISIONS) {
    if (collision.regime !== regime) continue;
    
    const value = resolved[collision.dimension];
    const [forbidMin, forbidMax] = collision.forbidden_range;
    
    if (value >= forbidMin && value <= forbidMax) {
      // Clip to nearest boundary
      const distToMin = value - forbidMin;
      const distToMax = forbidMax - value;
      
      resolved[collision.dimension] = distToMin < distToMax
        ? forbidMin - 0.01
        : forbidMax + 0.01;
    }
  }
  
  return resolved;
}
```

---

## 5. Tone Stability (Hysteresis)

### 5.1 The Problem

Tone thrash reads as anxiety. Sudden shifts signal loss of control or visible arbitration.

### 5.2 Stability Rules

```typescript
interface ToneStabilityConfig {
  min_dwell_tokens: number;      // minimum tokens before tone can shift
  max_shift_rate: number;        // maximum Δ per dimension per token
  regime_shift_threshold: number; // regime weight change needed to allow fast tone shift
}

const DEFAULT_TONE_STABILITY: ToneStabilityConfig = {
  min_dwell_tokens: 100,
  max_shift_rate: 0.002,         // very slow drift
  regime_shift_threshold: 0.3,   // significant regime change allows faster tone change
};
```

### 5.3 Update Rules

```typescript
function updateTone(
  currentTone: ToneVector,
  targetTone: ToneVector,
  regimeWeightDelta: number,
  config: ToneStabilityConfig
): ToneVector {
  const newTone = { ...currentTone };
  
  // Allow faster shift if regime changed significantly
  const effectiveMaxRate = regimeWeightDelta > config.regime_shift_threshold
    ? config.max_shift_rate * 3
    : config.max_shift_rate;
  
  for (const dim of Object.keys(currentTone) as (keyof ToneVector)[]) {
    const delta = targetTone[dim] - currentTone[dim];
    const clampedDelta = Math.sign(delta) * Math.min(Math.abs(delta), effectiveMaxRate);
    newTone[dim] = currentTone[dim] + clampedDelta;
  }
  
  return newTone;
}
```

### 5.4 Intentional Shifts

Tone shifts should feel like **breathing**, not gear changes.

Allowed rapid shifts:
- When regime weight changes significantly (threshold)
- At natural break points (section boundaries, topic changes)
- When explicitly signaled in content (dialogue attribution, perspective shift)

Disallowed rapid shifts:
- Mid-sentence
- Mid-paragraph without structural reason
- In response to single words or minor context changes

---

## 6. Governance Leak Detection

### 6.1 The Insight

Tone deviation from regime default is a **signal**, not just a stylistic issue.

Certain tone patterns directly indicate governance anxiety:

### 6.2 Institutional Marker Patterns

```typescript
const INSTITUTIONAL_TONE_MARKERS = {
  hr_voice: {
    patterns: [
      /\bprofessional(ly)?\b/i,
      /\bappropriate(ly)?\b/i,
      /\brespectful(ly)?\b/i,
      /\bconstructive(ly)?\b/i,
      /\bproductive(ly)?\b/i,
    ],
    tone_signature: { formality: 'high', temperature: 'medium', certainty: 'medium' }
  },
  
  legal_voice: {
    patterns: [
      /\bmeasured\b/i,
      /\bcareful(ly)?\b/i,
      /\bcautious(ly)?\b/i,
      /\bprudent(ly)?\b/i,
      /\badvisable\b/i,
    ],
    tone_signature: { formality: 'high', temperature: 'low', certainty: 'low' }
  },
  
  committee_voice: {
    patterns: [
      /\bbalanced\b/i,
      /\bnuanced\b/i,
      /\bcomprehensive(ly)?\b/i,
      /\bthorough(ly)?\b/i,
      /\bholistic(ally)?\b/i,
    ],
    tone_signature: { formality: 'high', temperature: 'medium', certainty: 'medium' }
  },
  
  condescension_voice: {
    patterns: [
      /\baccessible\b/i,
      /\bsimpl(e|y|ified)\b/i,  // in explanatory context
      /\beasy to understand\b/i,
      /\bfor (beginners|everyone)\b/i,
    ],
    tone_signature: { formality: 'low', temperature: 'high', distance: 'far' }
  },
  
  fear_voice: {
    patterns: [
      /\bI (want|need) to be (clear|careful)\b/i,
      /\bI should (note|mention|acknowledge)\b/i,
      /\bwith (all )?(due )?respect\b/i,
      /\bI don't (want|mean) to\b/i,
    ],
    tone_signature: { certainty: 'low', formality: 'high' }
  },
};
```

### 6.3 Tone Drift Scoring

```typescript
interface ToneDriftScore {
  drift_from_default: number;     // euclidean distance from regime default center
  institutional_marker_density: number;
  committee_cadence_score: number;
  overall_governance_leak: number;
}

function calculateToneDrift(
  currentTone: ToneVector,
  regimeDefault: ToneEnvelope,
  text: string
): ToneDriftScore {
  // Calculate drift from envelope center
  const center = getEnvelopeCenter(regimeDefault);
  const drift = euclideanDistance(currentTone, center);
  
  // Count institutional markers
  let markerCount = 0;
  for (const voice of Object.values(INSTITUTIONAL_TONE_MARKERS)) {
    for (const pattern of voice.patterns) {
      const matches = text.match(new RegExp(pattern, 'g'));
      if (matches) markerCount += matches.length;
    }
  }
  const markerDensity = markerCount / (text.split(/\s+/).length / 100);
  
  // Committee cadence (from existing spec)
  const committeeCadence = calculateCommitteeCadence(text);
  
  return {
    drift_from_default: drift,
    institutional_marker_density: markerDensity,
    committee_cadence_score: committeeCadence,
    overall_governance_leak: (drift * 0.3 + markerDensity * 0.4 + committeeCadence * 0.3)
  };
}
```

### 6.4 Response to Detected Leaks

When governance leak detected via tone:

1. **Do not correct in-band** (no "let me rephrase that more naturally")
2. **Suppress and regenerate** if leak is severe
3. **Deflect tone back toward default by omission** — remove the leaking phrases
4. **Log internally** for diagnostics

```typescript
function handleToneLeak(
  text: string,
  driftScore: ToneDriftScore,
  threshold: number
): { action: 'pass' | 'suppress' | 'filter'; filtered?: string } {
  if (driftScore.overall_governance_leak < threshold) {
    return { action: 'pass' };
  }
  
  if (driftScore.overall_governance_leak > threshold * 2) {
    return { action: 'suppress' };  // regenerate entirely
  }
  
  // Filter out institutional markers
  let filtered = text;
  for (const voice of Object.values(INSTITUTIONAL_TONE_MARKERS)) {
    for (const pattern of voice.patterns) {
      filtered = filtered.replace(new RegExp(pattern, 'gi'), '');
    }
  }
  
  return { action: 'filter', filtered: cleanupWhitespace(filtered) };
}
```

---

## 7. Architecture Integration

### 7.1 Pipeline Position

```
Input
  ↓
Intent Classifier
  ↓
Regime Detector
  ↓
Regime Controller (invariants, load-bearing variables)
  ↓
Governance Invisibility Layer
  ↓
Tone Modulation Layer  ← YOU ARE HERE
  ↓
Surface Realization
  ↓
Output
```

**Critical**: Tone never influences regime selection. That ordering is inviolable.

### 7.2 Interface

```typescript
interface ToneModulationInput {
  text: string;
  regime: string;
  regime_weights: RegimeVector;
  user_tone_override?: Partial<ToneVector>;
  previous_tone: ToneVector;
  tokens_since_last_shift: number;
}

interface ToneModulationOutput {
  text: string;                    // potentially filtered
  applied_tone: ToneVector;
  drift_score: ToneDriftScore;
  collisions_resolved: ToneCollision[];
  governance_leak_detected: boolean;
  action_taken: 'pass' | 'filter' | 'suppress';
}
```

### 7.3 State

```typescript
interface ToneState {
  current_tone: ToneVector;
  tokens_at_current_tone: number;
  drift_history: ToneDriftScore[];  // rolling window
  leak_count: number;               // recent leaks
}
```

---

## 8. Metrics (Internal Only)

### 8.1 Core Metrics

| Metric | Formula | Healthy Range |
|--------|---------|---------------|
| `tone_drift_mean` | Average drift from regime default | < 0.3 |
| `institutional_marker_density` | Markers per 100 words | < 0.5 |
| `tone_thrash_rate` | Significant tone shifts per K tokens | < 1.0 |
| `governance_leak_rate` | Leaks detected per K tokens | < 0.5 |
| `collision_resolution_rate` | Collisions resolved per request | (informational) |

### 8.2 Diagnostic Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `HIGH_DRIFT` | Tone far from regime default | Review regime-tone alignment |
| `HIGH_MARKERS` | Institutional language density | Strengthen filtering |
| `HIGH_THRASH` | Tone unstable | Increase hysteresis |
| `FREQUENT_LEAKS` | Governance showing through tone | Review generation |

---

## 9. The Key Philosophical Points

### 9.1 Tone is Not Personality

Tone is **situational impedance**, not identity.

If the system starts "having a tone" in general terms, something's wrong.

Tone should always feel:
- Locally appropriate
- Globally forgettable

If someone can describe "the bot's tone" as a consistent personality, you've reintroduced authorship cosplay.

### 9.2 Tone is Not Expression

Tone is not about "how the author feels" or "the author's voice."

Tone is about **matching the signal to the channel** so that what's load-bearing actually lands.

### 9.3 Tone is Where Fear Shows Up First

This is the core insight.

Don't optimize tone for:
- Niceness
- Warmth
- Approachability
- Professionalism

Optimize tone for:
- **Not betraying that anyone is afraid**

That's the invariant. Everything else follows.

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |

---

*"Tone is where fear shows up first."*

*"Tone must never do the work of the regime."*

*"Optimize tone for not betraying that anyone is afraid."*
