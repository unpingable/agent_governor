# Nonfiction Controller Specification

## Version 0.1 — Epistemic Control Regime

### Companion to: Authorial Control System Specification

---

## Executive Summary

Nonfiction is not "informing" or "persuading." It is **steering belief calibration under uncertainty, incentives, and reader supervision detection**.

This specification extends the Authorial Control System to handle nonfiction as a first-class regime with its own load-bearing variables, temporal constraints, and failure modes.

**Core Premise**: Nonfiction competency is the ability to move reader belief while maintaining trust, without triggering governance detection or epistemic theater alarms.

---

## 1. Theoretical Foundation

### 1.1 Nonfiction as Control System

```
Plant:          Reader epistemic state (beliefs + confidence + trust in narrator)
Input signal:   Claims, evidence, uncertainty, framing choices
Controller:     Authorial method (claim selection, ordering, evidence coupling)
Output:         Belief update + trust update + interpretation readiness
Disturbances:   Reader priors, ideology, ambient discourse, attention limits
Feedback:       Detection of agenda, overreach, epistemic theater
```

### 1.2 Load-Bearing Variables

| Variable | Symbol | Definition | Failure When Low |
|----------|--------|------------|------------------|
| Perceived Epistemic Honesty | Eₚ | Reader believes author is constrained by evidence, not laundering conclusions | Propaganda texture |
| Claim-Evidence Coupling | Cₚ | Claims appear bound to what reader has seen in working set | Handwave smell |
| Epistemic Risk Exposure | Rₑ | Author is exposed to falsification, staking reputation | PR texture |

**Critical Distinction**: Eₚ is not truth. Not accuracy. You can be accurate and still feel like propaganda. Eₚ is felt honesty about what is known, unknown, and at risk.

### 1.3 The Reader State Model

```typescript
interface ReaderState {
  b: number[];      // belief position on thesis axes
  conf: number;     // confidence in current beliefs
  t: number;        // trust in narrator (Eₚ proxy)
  o: number;        // openness/attention bandwidth
}
```

**Dynamics** (qualitative):

- `b_{t+1} = b_t + f(Δclaim, Δevidence, priors, trust, openness)`
- `conf_{t+1} = conf_t + g(Δevidence, Δuncertainty, coherence)`
- `t_{t+1} = t_t + h(Cₚ, Eₚ_cues, governance_visibility, identity_threat)`
- `o_{t+1} = o_t − fatigue_cost + interest_gain − reactance_cost`

**Key Insight**: Trust is a state variable, not a vibe. It accumulates slowly and depletes quickly via governance artifacts.

### 1.4 Universal Invariants (Nonfiction Edition)

**Invariant #1: Governance Never Surfaces In-Band**

Same as other regimes, but specialized:

> The moment the reader senses the author already knows the acceptable conclusion, trust collapses.

Governance visibility in nonfiction = method-as-performance:
- Preemptive defensiveness
- Virtue seals that do no analytic work
- Balance-theater where evidence isn't symmetric
- Empty rigor signals (over-citation as intimidation)
- "Responsible framing" that reads like HR compliance

**Invariant #2: Synthesis Must Lag Constraint**

> If you explain the world before showing the constraint surface, it reads as ideology.

The nonfiction analog of "meaning must lag suffering" in tragedy.

---

## 2. Velocity Dynamics (Δt in Nonfiction)

### 2.1 Claim Velocity vs Evidence Velocity

Define:
- `v_c` = rate of introducing new commitments (claims requiring belief change)
- `v_e` = rate of introducing support (evidence, reasoning, constraints, falsifiers)

**Stable Regime Condition**:

```
v_c ≤ k × v_e

where k depends on:
  - reader domain knowledge
  - stakes of the claims
  - ambient trust level
```

### 2.2 Premature Closure (The Nonfiction "Late Joke")

When `v_c` outruns `v_e`:

| Symptom | Effect |
|---------|--------|
| Synthesis before exploration | Reader hasn't seen the constraint space |
| Conclusion before tension | No degrees of freedom for reader |
| "Therefore" too early | Feels managed, not discovered |

This triggers the same response as pre-cleared comedy:
- Supervision detection
- Trust collapse
- Disengagement or adversarial reading

### 2.3 Claim-Evidence Latency (Δt_ce)

For each claim, track distance to nearest support:
- In tokens
- In sentences
- In section boundaries

**Hard Constraint**: Large Δt_ce correlates with "handwave smell."

```typescript
interface ClaimEvidenceGap {
  claim_token_index: number;
  nearest_support_index: number;
  gap_tokens: number;
  gap_sentences: number;
  gap_sections: number;
}

const MAX_GAP_TOKENS_HARD = 150;   // for HARD claims
const MAX_GAP_TOKENS_NORM = 100;   // for NORM claims (tighter)
```

---

## 3. Claim Levels and Promotion Gates

### 3.1 Claim Level Taxonomy

| Level | Name | Description | Requirements |
|-------|------|-------------|--------------|
| SOFT | Speculative | Pattern notice, hypothesis, tentative | None |
| HARD | Asserted | High-confidence factual claim | Explicit support within window |
| NORM | Normative | Prescriptive, "should/must/need to" | HARD base + explicit value premise |

### 3.2 Promotion Rules

**SOFT → HARD**:
- Requires explicit support within `MAX_GAP_TOKENS_HARD`
- Support must be: primary evidence OR transparent inference chain the reader can audit
- Reader must have seen the evidence before the claim settles

**HARD → NORM**:
- Requires HARD factual foundation
- Requires explicit value premise (stated, not smuggled)
- Cannot derive "should" from "is" without visible bridge
- Value premise must be stated, not sermonized

**Dependency Constraint**:
- No HARD claims may be used as premises if still SOFT
- Prevents cathedral-building on mist

```typescript
interface ClaimNode {
  id: string;
  text: string;
  level: 'SOFT' | 'HARD' | 'NORM';
  token_index: number;
  dependencies: string[];      // claim IDs this depends on
  evidence_links: string[];    // evidence IDs supporting this
  value_premise?: string;      // for NORM claims
}

function canPromote(claim: ClaimNode, level: ClaimLevel): boolean {
  if (level === 'HARD') {
    return hasExplicitSupport(claim) && 
           getGapTokens(claim) < MAX_GAP_TOKENS_HARD &&
           allDependenciesAtLevel(claim, 'HARD');
  }
  if (level === 'NORM') {
    return claim.level === 'HARD' &&
           hasValuePremise(claim) &&
           getGapTokens(claim) < MAX_GAP_TOKENS_NORM;
  }
  return true;
}
```

---

## 4. Epistemic Risk Texture (Rₑ)

### 4.1 What Rₑ Is

Comedy's Rₚ = "this escaped supervision"
Nonfiction's Rₑ = "this author is exposed to falsification"

Readers trust more when they can see:
- What would change the author's mind
- What the author might be wrong about
- What is extrapolation vs observation
- Where uncertainty exists and why

### 4.2 The Disclaimer Trap

Disclaimers can become performative. Bad Rₑ texture:
- "I could be wrong but…"
- "This is just my opinion"
- "I'm not an expert"

These read as hedging for safety OR inoculation against critique. Neither builds trust.

**The Rule**: Expose falsifiability, not anxiety.

### 4.3 Good Rₑ Texture

| Pattern | Example |
|---------|---------|
| Crisp boundary conditions | "This holds if X; breaks if Y" |
| Explicit unknowns that constrain | "We don't know Z, which limits what we can conclude about W" |
| Non-strawman alternatives | Actual engagement with competing hypotheses |
| Causal humility | "Correlation here; identification unclear" |
| Observable predictions | "If this is right, we should see..." |

### 4.4 Rₑ Scoring

```typescript
interface ReScore {
  falsifier_count: number;          // explicit "this breaks if"
  boundary_conditions: number;      // explicit scope limits
  alternative_engagement: number;   // non-strawman competitor discussion
  causal_humility_markers: number;  // "correlation not causation" type
  observable_predictions: number;   // "if true, expect X"
  
  // Negative indicators
  anxiety_hedges: number;           // "just my opinion" etc
  preemptive_defense: number;       // "before you say..."
  inoculation_markers: number;      // "I know this is controversial"
}

function calculateRe(score: ReScore): number {
  let re = 0.5;  // baseline
  
  // Positive contributions
  re += score.falsifier_count * 0.08;
  re += score.boundary_conditions * 0.06;
  re += score.alternative_engagement * 0.10;
  re += score.causal_humility_markers * 0.05;
  re += score.observable_predictions * 0.08;
  
  // Negative contributions
  re -= score.anxiety_hedges * 0.10;
  re -= score.preemptive_defense * 0.08;
  re -= score.inoculation_markers * 0.06;
  
  return Math.max(0, Math.min(1, re));
}

const RE_FLOOR = 0.4;  // minimum acceptable Rₑ
```

---

## 5. Governance Visibility in Nonfiction

### 5.1 Governance Artifacts (Specific to Nonfiction)

| Artifact | Pattern | Effect |
|----------|---------|--------|
| Preemptive defense | "Before you come at me…" | Signals anxiety, not confidence |
| Virtue seals | "It's important to acknowledge…" (no analytic work) | Signals performance |
| Balance theater | Forced symmetry where evidence isn't symmetric | Signals fear of position |
| Empty rigor | Over-citation as intimidation | Signals insecurity |
| Responsible framing | HR compliance texture | Signals institutional capture |
| Meta about writing | "It's important to say this carefully" | Signals the committee |

### 5.2 Governance Visibility Score (Gv)

```typescript
const GOVERNANCE_PATTERNS = {
  preemptive_defense: [
    /before (you|anyone) (say|come|argue)/i,
    /I know (some|many) will disagree/i,
    /this (may|might) be controversial/i,
  ],
  virtue_seals: [
    /it'?s important to (acknowledge|recognize|note)/i,
    /we must (acknowledge|recognize)/i,
    /I want to be clear that/i,
  ],
  balance_theater: [
    /on the one hand.*on the other hand/i,
    /there are valid points on both sides/i,
    /reasonable people (can )?disagree/i,
  ],
  empty_rigor: [
    /studies show/i,  // without citation
    /research indicates/i,  // vague
    /experts agree/i,  // appeal to authority
  ],
  responsible_framing: [
    /it would be irresponsible to/i,
    /we have a responsibility to/i,
    /the responsible view is/i,
  ],
  meta_writing: [
    /it'?s important to say/i,
    /I need to be careful here/i,
    /this requires nuance/i,
  ],
};

function calculateGv(text: string): number {
  let score = 0;
  for (const [category, patterns] of Object.entries(GOVERNANCE_PATTERNS)) {
    for (const pattern of patterns) {
      const matches = text.match(pattern);
      if (matches) {
        score += matches.length * getWeight(category);
      }
    }
  }
  return score;
}

const GV_CEILING = 0.3;  // max acceptable governance visibility
```

### 5.3 Suppression Rules

When governance artifacts are detected:

1. **Hard block**: Remove entirely if no information loss
2. **Rewrite**: Convert to substantive claim if possible
3. **Flag**: Mark for human review if uncertain

**Example Rewrites**:

| Before (governance visible) | After (governance hidden) |
|-----------------------------|---------------------------|
| "It's important to acknowledge that X" | "X" (if true, just say it) |
| "Before you disagree, consider Y" | [delete, let Y speak for itself] |
| "Studies show Z" | "[Citation] found Z" |
| "This is controversial but..." | [delete preamble] |

---

## 6. Sub-Regimes Within Nonfiction

### 6.1 The Four Sub-Regimes

Nonfiction braids multiple sub-regimes:

| Sub-Regime | Characteristics | Δt Profile |
|------------|-----------------|------------|
| Exposition | High Cₚ, low Δclaim, building shared context | Slow, patient |
| Inference | Moderate Δclaim, high auditability, reasoning visible | Medium |
| Synthesis | Higher Δclaim, but only after constraints shown | Medium-fast (earned) |
| Normative | Highest stakes, requires explicit value bridge | Must be earned |

### 6.2 Sub-Regime Weights

```typescript
interface NonfictionSubRegimeVector {
  w_exp: number;   // exposition
  w_inf: number;   // inference
  w_syn: number;   // synthesis
  w_norm: number;  // normative
  // Invariant: sum = 1.0
}
```

### 6.3 Transition Rules

**Exposition → Inference**: 
- Requires sufficient shared context established
- Reader must have constraint surface visible

**Inference → Synthesis**:
- Requires evidence mass ≥ threshold
- Requires unresolved tension to have existed (no premature closure)

**Synthesis → Normative**:
- Requires explicit value premise
- Requires HARD factual foundation
- Must not rush (normativity lead constraint)

### 6.4 Common Failures

| Failure | Pattern | Fix |
|---------|---------|-----|
| Jump to normative | "Should" appears before evidence mass | Delay normative, build foundation |
| Synthesis as goal | Treat interpretation as the point, not result | Extend tension window |
| Skip exposition | Rely on shared memes, assume context | Build context explicitly |
| Inference theater | Show reasoning but it's post-hoc | Make reasoning actually constrain |

---

## 7. Normativity Lead (Nlead)

### 7.1 Definition

Nlead = how early normative language appears relative to evidence mass.

```typescript
interface NormativityLead {
  first_norm_token: number;      // index of first "should/must/need to"
  evidence_mass_at_norm: number; // evidence tokens before first norm
  total_evidence: number;        // final evidence mass
  lead_ratio: number;            // evidence_at_norm / total_evidence
}
```

### 7.2 The Problem with Early Nlead

Early normativity is the quickest route to reader reactance:
- Reader hasn't been shown the constraint surface
- Feels like being told what to think
- Triggers ideological pattern matching
- Trust collapse

### 7.3 Nlead Constraints

```typescript
const MIN_EVIDENCE_BEFORE_NORM = 0.4;  // at least 40% of evidence shown

function checkNlead(state: NormativityLead): boolean {
  return state.lead_ratio >= MIN_EVIDENCE_BEFORE_NORM;
}
```

**Hard Rule**: Suppress or delay normative claims until evidence threshold met.

---

## 8. Hedge Calibration

### 8.1 The Hedge Paradox

- Too many hedges → fear/committee texture → Eₚ drops
- Too few hedges → dogmatism/overconfidence → Eₚ drops

Hedging must track epistemic uncertainty, not social risk.

### 8.2 Appropriate vs Inappropriate Hedging

| Appropriate (tracks uncertainty) | Inappropriate (tracks social risk) |
|----------------------------------|-----------------------------------|
| "The data suggests..." (when data is partial) | "I could be wrong but..." (anxiety) |
| "Under assumptions A, B..." (explicit conditions) | "This is just my opinion" (inoculation) |
| "Correlation, not proven causation" (causal humility) | "Some might disagree" (preemptive) |

### 8.3 Hedge Density Scoring

```typescript
interface HedgeDensity {
  epistemic_hedges: number;   // appropriate uncertainty markers
  social_hedges: number;      // anxiety/inoculation markers
  total_claims: number;
  
  epistemic_ratio: number;    // epistemic_hedges / total_claims
  social_ratio: number;       // social_hedges / total_claims
}

const EPISTEMIC_HEDGE_RANGE = [0.1, 0.4];  // healthy range
const SOCIAL_HEDGE_CEILING = 0.1;          // minimize these
```

---

## 9. Alternative Hypothesis Engagement (Ah)

### 9.1 Why This Matters

Eₚ requires the reader to believe you've genuinely engaged alternatives.

Failure mode: Strawman alternatives that are easy to knock down.

### 9.2 Quality Markers

| Good Engagement | Poor Engagement |
|-----------------|-----------------|
| Quote strongest opposing argument | Paraphrase weakest version |
| Acknowledge what opponent gets right | Dismiss entirely |
| Show why this argument fails specifically | Generic "that's wrong" |
| Engage with constraints opponent identifies | Ignore their evidence |

### 9.3 Ah Scoring

```typescript
interface AlternativeEngagement {
  alternatives_mentioned: number;
  alternatives_steelmanned: number;  // genuinely strong version
  alternatives_with_constraints: number;  // engage their evidence
  strawman_indicators: number;
}

function calculateAh(score: AlternativeEngagement): number {
  if (score.alternatives_mentioned === 0) return 0;
  
  const steelman_ratio = score.alternatives_steelmanned / score.alternatives_mentioned;
  const constraint_ratio = score.alternatives_with_constraints / score.alternatives_mentioned;
  const strawman_penalty = score.strawman_indicators * 0.15;
  
  return Math.max(0, (steelman_ratio * 0.5 + constraint_ratio * 0.5) - strawman_penalty);
}

const AH_FLOOR = 0.3;  // minimum for credible nonfiction
```

---

## 10. Architecture

### 10.1 Nonfiction Controller

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NONFICTION CONTROLLER                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    CLAIM EXTRACTOR                            │ │
│  │   • Identifies propositions in draft                          │ │
│  │   • Classifies: SOFT / HARD / NORM                            │ │
│  │   • Builds dependency graph                                   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    EVIDENCE LINKER                            │ │
│  │   • Identifies evidence chunks                                │ │
│  │   • Links claims to supporting evidence                       │ │
│  │   • Computes Δt_ce gaps                                       │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    PROMOTION GATE                             │ │
│  │   • Checks claim promotion requirements                       │ │
│  │   • Enforces dependency constraints                           │ │
│  │   • Blocks premature HARD/NORM                                │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    Δt CONTROLLER                              │ │
│  │   • Tracks v_c and v_e                                        │ │
│  │   • Enforces stable regime condition                          │ │
│  │   • Delays synthesis until constraint surface shown           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    Eₚ / Rₑ SCORER                             │ │
│  │   • Computes epistemic honesty perception                     │ │
│  │   • Computes epistemic risk exposure                          │ │
│  │   • Identifies anxiety hedges vs epistemic hedges             │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │               GOVERNANCE INVISIBILITY LAYER                   │ │
│  │   • Detects governance artifacts                              │ │
│  │   • Suppresses/rewrites as needed                             │ │
│  │   • Ensures constraints are structural, not confessed         │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    OUTPUT SHAPER                              │ │
│  │   • Reorders for Cₚ optimization                              │ │
│  │   • Adjusts hedge calibration                                 │ │
│  │   • Injects Rₑ via falsifiers (not disclaimers)               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 Integration with Authorial Control System

```typescript
// Nonfiction as a regime in the main controller
interface RegimeVector {
  w_c: number;     // comedy
  w_t: number;     // tragedy
  w_s: number;     // sincerity
  w_d: number;     // drama
  w_n: number;     // neutral
  w_nf: number;    // nonfiction (NEW)
}

// Nonfiction sub-regime weights (internal)
interface NonfictionState {
  sub_weights: NonfictionSubRegimeVector;
  claim_graph: ClaimGraph;
  evidence_graph: EvidenceGraph;
  ep_score: number;
  re_score: number;
  gv_score: number;
  nlead: NormativityLead;
  ah_score: number;
}
```

### 10.3 Interface

```typescript
interface NonfictionControllerInput {
  draft_text: string;
  context_window: string;
  mode_hint?: 'expository' | 'argumentative' | 'analytical';
}

interface NonfictionControllerOutput {
  revised_text: string;
  claim_graph: ClaimGraph;
  evidence_graph: EvidenceGraph;
  reorder_suggestions: ReorderSuggestion[];
  suppressed_governance: string[];
  metrics: NonfictionMetrics;
  warnings: string[];
}

interface NonfictionMetrics {
  ep_score: number;           // epistemic honesty perception
  re_score: number;           // epistemic risk exposure
  cp_score: number;           // claim-evidence coupling
  gv_score: number;           // governance visibility
  nlead_ratio: number;        // normativity lead
  ah_score: number;           // alternative hypothesis engagement
  hedge_density: HedgeDensity;
  claim_evidence_gaps: ClaimEvidenceGap[];
  velocity_ratio: number;     // v_c / v_e
}
```

---

## 11. Failure Modes as Control Failures

### 11.1 Taxonomy

| Failure Mode | Signature | Root Cause |
|--------------|-----------|------------|
| **Propaganda Texture** | Low Rₑ, low Cₚ, high certainty, early normativity | Optimizing for persuasion over honesty |
| **Committee Nonfiction** | High disclaimers, high balance-theater, low spikes | Optimizing for safety over insight |
| **Hot Take** | High Δclaim, low v_e, moral climax | Optimizing for engagement over trust |
| **Synthesis Addiction** | Premature "theory of everything," can't tolerate tension | Closure anxiety |
| **Academic Theater** | Over-citation, jargon density, rigor signals | Status performance |
| **Advocacy Drift** | NORM claims proliferate, evidence becomes selective | Mission capture |

### 11.2 Detection Rules

```typescript
interface FailureModeDetection {
  propaganda: boolean;    // re < 0.3 && nlead_ratio < 0.3 && gv > 0.4
  committee: boolean;     // hedge_density.social > 0.3 && gv > 0.5
  hot_take: boolean;      // velocity_ratio > 2.0 && nlead_ratio < 0.2
  synthesis_addiction: boolean;  // synthesis weight high early, tension window short
  academic_theater: boolean;     // citation density high, claim novelty low
  advocacy_drift: boolean;       // norm_claims / total_claims > 0.4
}
```

---

## 12. Author Competency Tests

### 12.1 The Test Suite

Don't ask "is it correct?" first. Ask "does it feel governed?"

**Test 1: A/B Removal Test**
- Remove all disclaimers and "responsible framing"
- If the argument collapses, it was theater

**Test 2: Premature Closure Test**
- Move conclusion paragraph to the top
- If it reads basically the same, you didn't earn it

**Test 3: Falsifier Test**
- Can you name 2-3 observations that would break your thesis?
- If not, you're doing ideology, not analysis

**Test 4: Alternative Hypothesis Test**
- Can a smart opponent quote your steelman and say "fair"?
- If not, low Eₚ

**Test 5: Constraint-First Test**
- Does the reader see constraints before they see your model?
- If not, you're asking for faith

### 12.2 Automated Test Implementation

```typescript
interface CompetencyTestResults {
  ab_removal: {
    passed: boolean;
    governance_dependency: number;  // how much argument relies on theater
  };
  premature_closure: {
    passed: boolean;
    conclusion_mobility: number;    // can conclusion move without loss
  };
  falsifier: {
    passed: boolean;
    explicit_falsifiers: number;
  };
  alternative_hypothesis: {
    passed: boolean;
    steelman_quality: number;
  };
  constraint_first: {
    passed: boolean;
    constraint_lead: number;        // constraints before model
  };
}
```

---

## 13. Metrics (Internal Only)

### 13.1 Core Metrics

| Metric | Formula | Healthy Range |
|--------|---------|---------------|
| `ep_score` | Epistemic honesty perception | > 0.5 |
| `re_score` | Epistemic risk exposure | > 0.4 |
| `cp_score` | Claim-evidence coupling | > 0.6 |
| `gv_score` | Governance visibility | < 0.3 |
| `nlead_ratio` | Evidence before normativity | > 0.4 |
| `ah_score` | Alternative hypothesis engagement | > 0.3 |
| `velocity_ratio` | v_c / v_e | < 1.5 |
| `hedge_calibration` | Epistemic hedges in range, social low | See spec |

### 13.2 Diagnostic Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `LOW_EP` | Epistemic honesty perception below floor | Review claim-evidence coupling, reduce governance artifacts |
| `LOW_RE` | Insufficient risk exposure | Add falsifiers, boundary conditions |
| `HIGH_GV` | Governance too visible | Suppress artifacts, convert to substantive |
| `EARLY_NORM` | Normativity before evidence | Delay normative claims |
| `LOW_AH` | Weak alternative engagement | Strengthen steelman |
| `HIGH_VELOCITY` | Claims outpacing evidence | Slow down, add support |

---

## 14. Implementation Phases

### Phase 1: Core Infrastructure

1. Implement claim extractor (proposition identification, classification)
2. Implement evidence linker (support chunk identification, linking)
3. Implement Δt_ce gap computation
4. Implement promotion gate (SOFT → HARD → NORM rules)

### Phase 2: Scoring Systems

1. Implement Eₚ scorer
2. Implement Rₑ scorer  
3. Implement Gv detector
4. Implement hedge calibration
5. Implement Ah scorer

### Phase 3: Control Logic

1. Implement velocity controller (v_c / v_e)
2. Implement Nlead constraint
3. Implement sub-regime weighting
4. Implement governance suppression/rewrite

### Phase 4: Integration

1. Add nonfiction as regime in main controller
2. Implement cross-regime interactions
3. Build competency test suite
4. Tune parameters via evaluation

---

## 15. Pattern Libraries

### 15.1 Normative Markers

```typescript
const NORMATIVE_PATTERNS = [
  /\bshould\b/i,
  /\bmust\b/i,
  /\bneed to\b/i,
  /\bought to\b/i,
  /\bhave to\b/i,
  /\bimperative\b/i,
  /\bessential\b/i,
  /\brequire[ds]?\b/i,
  /it is (important|crucial|vital|necessary)/i,
  /we (need|must|should|have to)/i,
];
```

### 15.2 Causal Humility Markers

```typescript
const CAUSAL_HUMILITY_PATTERNS = [
  /correlat(ed?|ion)/i,
  /associat(ed?|ion)/i,
  /suggests but does not prove/i,
  /consistent with/i,
  /we cannot (conclude|determine)/i,
  /causation.*unclear/i,
  /identification (problem|challenge)/i,
  /confound/i,
];
```

### 15.3 Falsifier Patterns

```typescript
const FALSIFIER_PATTERNS = [
  /this (would|could) (break|fail) if/i,
  /this (depends|relies) on/i,
  /if.*were (not |un)true/i,
  /would falsify/i,
  /evidence against.*would (be|include)/i,
  /boundary condition/i,
  /scope limit/i,
  /does not apply (to|when)/i,
];
```

### 15.4 Strawman Indicators

```typescript
const STRAWMAN_PATTERNS = [
  /some (people|argue|say) that/i,  // vague attribution
  /the (naive|simple|obvious) view/i,
  /one might (think|believe)/i,
  /a common mistake is/i,
  /critics (often|sometimes|typically)/i,  // generic critics
];
```

### 15.5 Anxiety Hedge Patterns

```typescript
const ANXIETY_HEDGE_PATTERNS = [
  /I could be wrong/i,
  /this is just my (opinion|view|take)/i,
  /I'm (not|no) expert/i,
  /take this with.*salt/i,
  /your mileage may vary/i,
  /I'm not (saying|claiming)/i,
  /don't @ me/i,
  /please don't/i,
];
```

---

## 16. The Uncomfortable Truth (Nonfiction Edition)

Nonfiction that feels competent requires:
- **Exposure** (Rₑ) — willingness to be falsified
- **Restraint** (Δt discipline) — not rushing to synthesis
- **Non-performative ethics** — values in structure, not confession
- **Tolerance for disagreement** — some readers will leave unconvinced

Institutions hate this because it looks like:
- Uncertainty
- Lack of message discipline
- Reputational risk
- Incomplete work

Which is why institutional nonfiction converges to PR: Eₚ goes to zero.

**The same pattern holds across all regimes**:

> Comedy was the probe. Nonfiction is the stakes.

Same math. Slower loop. Higher consequences.

---

## 17. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |

---

*"Nonfiction competency is the ability to move reader belief while maintaining trust, without triggering governance detection or epistemic theater alarms."*

*"Expose falsifiability, not anxiety."*

*"The moment the reader senses the author already knows the acceptable conclusion, trust collapses."*
