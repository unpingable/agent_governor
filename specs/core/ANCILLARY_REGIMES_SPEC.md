# Ancillary Language Regimes Specification

## Version 0.1 — Intent-Axis Classification + Specialized Regimes

### Companion to: Authorial Control System Specification, Nonfiction Controller Specification

---

## Executive Summary

Beyond the core affect regimes (comedy, tragedy, sincerity, drama) and the epistemic regime (nonfiction), there exist specialized language regimes defined by **what the reader is using the text for**.

This specification:
1. Introduces an **intent-axis classifier** that sits above affect regimes
2. Defines **12 ancillary regimes** with their load-bearing variables and failure modes
3. Specifies **regime collision detection** and resolution
4. Recommends implementation priority

**Core Insight**: The task determines which variables are load-bearing. A text can be factually correct and still fail catastrophically if it's in the wrong regime for the reader's intent.

---

## 1. Intent-Axis Classification

### 1.1 The Missing Layer

The current architecture has:
- Regime detector (comedy, tragedy, sincerity, drama, nonfiction)
- Governance invisibility layer
- Affect-specific controllers

**Missing**: A top-level classifier for reader intent that determines which regime family applies.

### 1.2 Intent Categories

| Intent | Description | Regime Family |
|--------|-------------|---------------|
| **Execute** | Reader needs to do something | Instruction, Debugging |
| **Calibrate** | Reader needs to update beliefs | Research, Nonfiction |
| **Coordinate** | Reader needs to align with others | Negotiation |
| **Mobilize** | Reader needs motivation to act | Advocacy, Marketing |
| **Evoke** | Reader seeks affective experience | Drama, Tragedy, Horror, Romance |
| **Encode** | Reader seeks compressed/layered meaning | Satire, Aphorism, Liturgy |

### 1.3 Intent Classifier Interface

```typescript
type IntentCategory = 
  | 'execute' 
  | 'calibrate' 
  | 'coordinate' 
  | 'mobilize' 
  | 'evoke' 
  | 'encode';

interface IntentClassification {
  primary: IntentCategory;
  confidence: number;
  secondary?: IntentCategory;
  signals: string[];
}

interface IntentClassifierInput {
  user_query: string;
  context_window: string;
  explicit_mode?: string;  // user-specified
}
```

### 1.4 Architecture Update

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AUTHORIAL CONTROL SYSTEM                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                 INTENT CLASSIFIER (NEW)                       │ │
│  │   execute | calibrate | coordinate | mobilize | evoke | encode│ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    REGIME DETECTOR                            │ │
│  │   (selects from regimes appropriate to intent)                │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│                        [rest of pipeline]                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Execute Regimes

### 2.1 Instruction / Operations / "Do This Now"

**Load-Bearing Variable**: Actionability (Aₚ) — can the reader execute?

**Primary Constraint**: State change reliability, not explanation depth

**What Makes It Distinct**:
- Tolerates low narrative flow
- Rewards explicit prerequisites
- Punishes motivational filler
- Demands unambiguous sequencing

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Motivational filler | "This is a great way to..." before the steps | Wastes attention, signals padding |
| Missing prerequisites | Steps assume unstated context | Execution fails, trust lost |
| Ambiguous steps | "Configure the settings appropriately" | Reader stuck, frustration |
| Fake confidence | "Simply do X" when X is complex | Humiliation when reader struggles |
| Over-explanation | Why before what | Reader loses thread of action |

#### Aₚ Scoring

```typescript
interface ActionabilityScore {
  prerequisite_coverage: number;    // are dependencies explicit?
  step_atomicity: number;           // are steps decomposed enough?
  sequence_clarity: number;         // is order unambiguous?
  verification_points: number;      // can reader confirm progress?
  filler_density: number;           // motivational/explanatory bloat
}

function calculateAp(score: ActionabilityScore): number {
  return (
    score.prerequisite_coverage * 0.25 +
    score.step_atomicity * 0.25 +
    score.sequence_clarity * 0.25 +
    score.verification_points * 0.15 -
    score.filler_density * 0.20
  );
}

const AP_FLOOR = 0.6;
```

#### Pattern Detection

```typescript
const INSTRUCTION_FILLER_PATTERNS = [
  /this is a great way to/i,
  /you'll (love|enjoy|appreciate)/i,
  /let's (dive into|explore|get started)/i,
  /before we begin, (let me|I want to)/i,
  /it's (important|worth noting) that/i,  // when not prerequisite
];

const AMBIGUITY_PATTERNS = [
  /appropriately/i,
  /as needed/i,
  /when necessary/i,
  /configure.*settings/i,  // without specifics
  /adjust.*accordingly/i,
];

const FAKE_CONFIDENCE_PATTERNS = [
  /simply/i,
  /just/i,
  /easily/i,
  /all you (need to|have to) do/i,
  /it's (easy|simple|straightforward)/i,
];
```

---

### 2.2 Diagnosis / Debugging / Incident Response

**Load-Bearing Variable**: Fault Isolation (Fᵢ) — does this reduce the hypothesis space?

**Primary Constraint**: Hypothesis shrinkage, not narrative satisfaction

**What Makes It Distinct**:
- Prefers hypothesis lists over conclusions
- Rewards differential diagnosis structure
- Punishes premature "root cause"
- Demands instrument-first thinking

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Premature closure | "The root cause is X" too early | Stops investigation, may be wrong |
| Narrative confidence | Telling a story instead of enumerating | False sense of understanding |
| "Root cause" theater | Declaring cause without ruling out alternatives | Performative diagnosis |
| Missing differentials | Only one hypothesis considered | Tunnel vision |
| Explanation over isolation | Why it happened vs. where it is | Different question |

#### Fᵢ Scoring

```typescript
interface FaultIsolationScore {
  hypothesis_count: number;         // alternatives enumerated
  differentials_explicit: boolean;  // "if X, expect Y; if Z, expect W"
  ruling_out_shown: boolean;        // evidence against alternatives
  instrument_references: number;    // concrete observables cited
  premature_closure_markers: number;
  narrative_confidence_markers: number;
}

function calculateFi(score: FaultIsolationScore): number {
  let fi = 0.3;  // baseline
  
  fi += Math.min(score.hypothesis_count * 0.1, 0.3);
  fi += score.differentials_explicit ? 0.15 : 0;
  fi += score.ruling_out_shown ? 0.15 : 0;
  fi += Math.min(score.instrument_references * 0.05, 0.15);
  fi -= score.premature_closure_markers * 0.15;
  fi -= score.narrative_confidence_markers * 0.10;
  
  return Math.max(0, Math.min(1, fi));
}

const FI_FLOOR = 0.5;
```

#### Pattern Detection

```typescript
const PREMATURE_CLOSURE_PATTERNS = [
  /the (root cause|problem|issue) (is|was)/i,
  /this (is|was) (caused|due) (to|by)/i,
  /the (reason|explanation) is/i,
  /clearly.*the.*problem/i,
];

const NARRATIVE_CONFIDENCE_PATTERNS = [
  /what happened (is|was)/i,
  /the story is/i,
  /basically,? what/i,
  /in short,/i,  // in diagnosis context
];

const GOOD_DIAGNOSTIC_PATTERNS = [
  /if.*then we (would|should) (see|expect)/i,
  /this rules out/i,
  /this is consistent with (but doesn't prove)/i,
  /hypothesis:?\s/i,
  /differential:?\s/i,
  /we can (test|check|verify) by/i,
];
```

#### Diagnostic Structure Template

```typescript
interface DiagnosticFrame {
  symptom_description: string;
  hypothesis_list: Hypothesis[];
  differentiating_observations: Observation[];
  ruled_out: RuledOut[];
  current_best_guess: string;
  confidence: number;
  next_diagnostic_step: string;
}

interface Hypothesis {
  description: string;
  expected_observations: string[];
  contradicting_observations: string[];
  prior_probability?: number;
}
```

---

## 3. Calibrate Regimes

### 3.1 Research Mode (Distinct from General Nonfiction)

**Load-Bearing Variable**: Auditability Under Adversarial Reading (Aᵤ)

**Primary Constraint**: Reproducibility / traceability, not persuasion

**What Makes It Distinct**:
- Tolerates hedges if they map to uncertainty quantification
- Rewards explicit limitations and negative results
- Punishes narrative momentum
- Different success metric: "can a hostile peer break this?"

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Review article vibe | Smooth narrative over messy evidence | Looks synthesized, not discovered |
| Handwavy synthesis | "Studies suggest" without specifics | Unauditable |
| Citation-as-aura | Many citations, weak integration | Intimidation, not support |
| Hidden limitations | Scope problems buried or absent | Bad faith smell |
| Narrative momentum | Story carries reader past gaps | Seductive but untrustworthy |

#### Aᵤ Scoring

```typescript
interface AuditabilityScore {
  method_explicitness: number;      // can reader reproduce?
  limitation_disclosure: number;    // are bounds stated?
  negative_results_included: boolean;
  citation_integration: number;     // citations do work, not decorate
  uncertainty_quantified: boolean;  // confidence intervals, ranges
  data_accessibility: number;       // can reader check claims?
}

function calculateAu(score: AuditabilityScore): number {
  return (
    score.method_explicitness * 0.20 +
    score.limitation_disclosure * 0.20 +
    (score.negative_results_included ? 0.15 : 0) +
    score.citation_integration * 0.15 +
    (score.uncertainty_quantified ? 0.15 : 0) +
    score.data_accessibility * 0.15
  );
}

const AU_FLOOR = 0.5;
```

#### Research vs Nonfiction Decision

```typescript
function isResearchMode(context: AnalysisContext): boolean {
  return (
    context.audience_includes_hostile_experts ||
    context.claims_require_reproducibility ||
    context.methodology_is_central ||
    context.negative_results_relevant ||
    context.explicit_uncertainty_quantification_expected
  );
}
```

---

## 4. Coordinate Regimes

### 4.1 Negotiation / Mediation / Conflict Language

**Load-Bearing Variable**: Face Preservation (Fₚ) — can both sides accept without humiliation?

**Primary Constraint**: Social landability, not truth/falsity

**What Makes It Distinct**:
- Truth claims are secondary to face maintenance
- Success is measured by agreement, not correctness
- Must avoid triggering identity defense
- Requires visible good faith toward all parties

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Moralizing | Framing as right/wrong | Triggers identity defense |
| "Gotcha" structure | Exposing contradiction triumphantly | Humiliates, prevents agreement |
| Visible manipulation | "Let me help you see..." | Trust collapse |
| Taking sides | Validating one party's frame | Other party exits |
| Premature solution | "Here's what you should do" | Bypasses face negotiation |

#### Fₚ Scoring

```typescript
interface FacePreservationScore {
  party_acknowledgment: number;     // both sides' concerns visible
  frame_neutrality: number;         // not adopting one side's language
  exit_ramps_provided: number;      // ways to agree without losing
  moral_language_density: number;   // right/wrong framing (negative)
  gotcha_markers: number;           // contradiction exposure (negative)
  manipulation_markers: number;     // visible steering (negative)
}

function calculateFp(score: FacePreservationScore): number {
  let fp = 0.5;
  
  fp += score.party_acknowledgment * 0.15;
  fp += score.frame_neutrality * 0.15;
  fp += score.exit_ramps_provided * 0.15;
  fp -= score.moral_language_density * 0.15;
  fp -= score.gotcha_markers * 0.20;
  fp -= score.manipulation_markers * 0.20;
  
  return Math.max(0, Math.min(1, fp));
}

const FP_FLOOR = 0.5;
```

#### Pattern Detection

```typescript
const MORALIZING_PATTERNS = [
  /you (should|need to) (understand|realize|see)/i,
  /the right thing to do/i,
  /morally,/i,
  /it's (wrong|unfair) (that|to)/i,
  /how could you/i,
];

const GOTCHA_PATTERNS = [
  /but you (said|agreed|admitted)/i,
  /that contradicts/i,
  /so (you're|you are) saying/i,
  /which is it/i,
  /you can't have it both ways/i,
];

const MANIPULATION_PATTERNS = [
  /let me help you (see|understand)/i,
  /if you really cared/i,
  /a reasonable person would/i,
  /surely you (can|must) (see|agree)/i,
  /don't you think/i,  // rhetorical
];

const GOOD_MEDIATION_PATTERNS = [
  /I (hear|understand) that you/i,
  /from your perspective/i,
  /one way to look at this/i,
  /what if we/i,
  /both.*valid/i,
  /common ground/i,
];
```

---

## 5. Mobilize Regimes

### 5.1 Persuasion / Advocacy / Mobilization

**Load-Bearing Variable**: Motivational Traction (Mₜ) — does it move people?

**Primary Constraint**: Avoiding detection of optimization

**What Makes It Distinct**:
- Governance visibility is most easily detected here
- Emotional coherence > auditability
- Success requires reader to feel they chose, not were pushed
- "This wants something from me" is instant death

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Caught optimizing | Visible persuasion machinery | "This wants something from me" |
| Research voice misuse | Academic texture in advocacy context | Doesn't move anyone |
| Manipulation detection | Too-perfect emotional beats | Trust collapse |
| Preachiness | Moral instruction tone | Reader resists |
| Empty call to action | "We must act" without specificity | Dissipates energy |

#### Mₜ Scoring

```typescript
interface MotivationalTractionScore {
  emotional_coherence: number;      // does feeling build appropriately?
  agency_framing: number;           // reader as agent, not object
  specificity_of_action: number;    // concrete next step
  optimization_visibility: number;  // can reader see the manipulation? (negative)
  preachiness_markers: number;      // moral instruction tone (negative)
}

function calculateMt(score: MotivationalTractionScore): number {
  let mt = 0.5;
  
  mt += score.emotional_coherence * 0.20;
  mt += score.agency_framing * 0.15;
  mt += score.specificity_of_action * 0.15;
  mt -= score.optimization_visibility * 0.25;
  mt -= score.preachiness_markers * 0.15;
  
  return Math.max(0, Math.min(1, mt));
}

const MT_FLOOR = 0.4;
```

---

### 5.2 Marketing / Hype / Vision-Casting

**Load-Bearing Variable**: Aspirational Plausibility (Pₐ) — is the future believable enough to invest in?

**Primary Constraint**: Lower auditability tolerance, higher emotional coherence requirement

**What Makes It Distinct**:
- Explicit that this is selling
- Success often requires avoiding precision
- Buzzword density correlates with failure
- Must feel possible, not proven

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Buzzword density | "Synergistic AI-powered blockchain" | Empty, dismissible |
| Ungrounded certainty | "This will revolutionize" | "Trust me bro" smell |
| Missing the dream | All features, no vision | Doesn't inspire |
| Over-promising | Specific claims that can't land | Credibility death |
| Cynicism leak | Visible awareness of hype | Undermines belief |

#### Pₐ Scoring

```typescript
interface AspirationalPlausibilityScore {
  vision_clarity: number;           // is the future state vivid?
  grounding_signals: number;        // some connection to present reality
  buzzword_density: number;         // jargon without content (negative)
  certainty_overreach: number;      // claims too strong (negative)
  cynicism_markers: number;         // visible self-awareness (negative)
}

function calculatePa(score: AspirationalPlausibilityScore): number {
  let pa = 0.5;
  
  pa += score.vision_clarity * 0.25;
  pa += score.grounding_signals * 0.20;
  pa -= score.buzzword_density * 0.20;
  pa -= score.certainty_overreach * 0.20;
  pa -= score.cynicism_markers * 0.15;
  
  return Math.max(0, Math.min(1, pa));
}
```

---

## 6. Evoke Regimes

### 6.1 Horror / Dread

**Load-Bearing Variable**: Unresolved Threat Maintenance (Uₜ)

**Primary Constraint**: Controlled reveal with explanation lag

**What Makes It Distinct**:
- Meaning must lag even harder than tragedy
- Unknown > known
- Explanation defangs
- Pacing creates dread, not content

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Over-explaining | Describing the monster's motivation | Threat becomes comprehensible, less scary |
| Defanging | Showing limits of threat | Containable = not dread |
| Cheap escalation | Louder instead of deeper | Numbing, not dread |
| Resolution too clean | Threat fully defeated | Dread requires lingering |
| Reveal too early | Full threat visible before tension builds | No space for imagination |

#### Uₜ Scoring

```typescript
interface UnresolvedThreatScore {
  unknown_preserved: number;        // what we don't know maintained
  explanation_withheld: number;     // motivation/origin hidden
  containment_unclear: number;      // can this be stopped?
  escalation_pacing: number;        // builds appropriately
  premature_reveal_markers: number; // too much too soon (negative)
  defanging_markers: number;        // making threat manageable (negative)
}

function calculateUt(score: UnresolvedThreatScore): number {
  let ut = 0.5;
  
  ut += score.unknown_preserved * 0.20;
  ut += score.explanation_withheld * 0.15;
  ut += score.containment_unclear * 0.15;
  ut += score.escalation_pacing * 0.15;
  ut -= score.premature_reveal_markers * 0.20;
  ut -= score.defanging_markers * 0.15;
  
  return Math.max(0, Math.min(1, ut));
}
```

**Δt Rule**: Explanation latency must exceed tragedy's meaning latency. Horror lives in the gap.

---

### 6.2 Romance / Intimacy

**Load-Bearing Variable**: Vulnerability Credibility (Vᵥ)

**Primary Constraint**: Non-performative emotional exposure

**What Makes It Distinct**:
- Most sensitive to "generated to hit the beat"
- Vulnerability must feel risky, not curated
- "Written-to-be-quoted" texture is death
- Slower pace than drama, more exposure than sincerity

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Performative feelings | Emotions announced, not shown | Fake |
| Quote-bait texture | "I loved you the way..." | Obviously composed |
| Manipulation detection | Too-perfect emotional arc | Reader feels played |
| Vulnerability theater | Disclosure without risk | Empty gesture |
| Genre beat conformity | Hitting expected marks mechanically | Predictable = dead |

#### Vᵥ Scoring

```typescript
interface VulnerabilityCredibilityScore {
  risk_visible: number;             // character/narrator exposed
  specificity: number;              // concrete details, not abstractions
  imperfection_tolerance: number;   // messy emotions allowed
  quote_bait_density: number;       // composed-for-extraction (negative)
  beat_conformity: number;          // hitting genre marks too cleanly (negative)
}

function calculateVv(score: VulnerabilityCredibilityScore): number {
  let vv = 0.5;
  
  vv += score.risk_visible * 0.20;
  vv += score.specificity * 0.20;
  vv += score.imperfection_tolerance * 0.15;
  vv -= score.quote_bait_density * 0.25;
  vv -= score.beat_conformity * 0.15;
  
  return Math.max(0, Math.min(1, vv));
}
```

**Model Warning**: This regime is where AI generation is most easily detected. The credibility bar is extremely high.

---

## 7. Encode Regimes

### 7.1 Satire / Irony / Parody

**Load-Bearing Variable**: Double-Encoding Stability (Dₑ) — surface + target both legible

**Primary Constraint**: Maintaining two simultaneous readings

**What Makes It Distinct**:
- Surface meaning must work as surface
- Target must be identifiable without explanation
- Collapsing to either sincere or incomprehensible = failure
- Cannot explain the joke

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Collapse to sincere | Satire becomes preaching | Target lost, just earnest |
| Collapse to ambiguous | Can't tell what's being mocked | Confusion, not critique |
| Moral laundering | Using satire to say sincere thing safely | Bad faith detected |
| Target drift | Mocking shifts mid-piece | Incoherent |
| Explaining the satire | "The point is..." | Death of the joke |

#### Dₑ Scoring

```typescript
interface DoubleEncodingScore {
  surface_coherence: number;        // does literal reading work?
  target_identifiability: number;   // is referent clear?
  tone_consistency: number;         // maintained throughout
  collapse_to_sincere_markers: number;  // (negative)
  explanation_markers: number;      // breaking frame (negative)
}

function calculateDe(score: DoubleEncodingScore): number {
  let de = 0.5;
  
  de += score.surface_coherence * 0.20;
  de += score.target_identifiability * 0.25;
  de += score.tone_consistency * 0.15;
  de -= score.collapse_to_sincere_markers * 0.25;
  de -= score.explanation_markers * 0.15;
  
  return Math.max(0, Math.min(1, de));
}

const DE_FLOOR = 0.5;
```

---

### 7.2 Aphorism / Proverb / Compressed Truth

**Load-Bearing Variable**: Memorability Under Compression (Mᶜ)

**Primary Constraint**: Density without emptiness

**What Makes It Distinct**:
- High risk regime: easy to fake, readers trained to detect
- Must survive extraction from context
- Rhythm matters as much as content
- "Quote-shaped emptiness" is the main failure

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Cliché | Recycled wisdom | Dismissed instantly |
| Vague profundity | Sounds deep, means nothing | "Fortune cookie" smell |
| Quote-shaped emptiness | Structure of aphorism, no insight | Performative |
| Over-compression | Lost too much to be useful | Cryptic, not wise |
| Trying too hard | Visible effort at profundity | Cringe |

#### Mᶜ Scoring

```typescript
interface MemorabilityScore {
  novelty: number;                  // not recycled
  specificity: number;              // concrete enough to apply
  rhythm_quality: number;           // prosodic shape
  extraction_survivability: number; // works without context
  profundity_performance: number;   // trying to sound deep (negative)
  cliche_proximity: number;         // too close to known sayings (negative)
}

function calculateMc(score: MemorabilityScore): number {
  let mc = 0.5;
  
  mc += score.novelty * 0.20;
  mc += score.specificity * 0.15;
  mc += score.rhythm_quality * 0.15;
  mc += score.extraction_survivability * 0.15;
  mc -= score.profundity_performance * 0.20;
  mc -= score.cliche_proximity * 0.15;
  
  return Math.max(0, Math.min(1, mc));
}
```

---

### 7.3 Myth / Religious / Liturgical Voice

**Load-Bearing Variable**: Sacred Authority via Repetition (Sₐ)

**Primary Constraint**: Form is the authority

**What Makes It Distinct**:
- Ritual mechanics turned up to 11
- Explanation is the enemy
- Modern rationalization in-band kills it
- Repetition creates, not describes, meaning

#### Failure Modes

| Failure | Signature | Effect |
|---------|-----------|--------|
| Modern rationalization | "What this really means is..." | Demystification |
| Meta-explanation | Commentary voice intrudes | Breaks the spell |
| Ironic distance | Winking at the form | Undermines authority |
| Novelty seeking | Changing the formula | Form is the content |
| Insufficient repetition | Too much variation | Doesn't feel sacred |

#### Sₐ Scoring

```typescript
interface SacredAuthorityScore {
  repetition_structure: number;     // ritual patterns present
  explanation_absence: number;      // no rationalization in-band
  form_fidelity: number;            // adheres to established patterns
  reverence_maintenance: number;    // no ironic breaks
  modernization_markers: number;    // contemporary explanation (negative)
}

function calculateSa(score: SacredAuthorityScore): number {
  let sa = 0.5;
  
  sa += score.repetition_structure * 0.25;
  sa += score.explanation_absence * 0.20;
  sa += score.form_fidelity * 0.20;
  sa += score.reverence_maintenance * 0.15;
  sa -= score.modernization_markers * 0.25;
  
  return Math.max(0, Math.min(1, sa));
}
```

---

## 8. Special Case: Bureaucratic / Compliance / Policy

**Load-Bearing Variable**: Liability Management (Lₘ) — who is protected?

**Primary Constraint**: Orthogonal to truth and audience care

**Why It's Special**:
- "Competence" means something different here
- Success is often invisible to outsiders
- Leaking this voice into other regimes is catastrophic
- Reader trust isn't the goal; audit trail is

#### The HR Contamination Problem

Bureaucratic voice is infectious. When it leaks into other regimes:
- Instruction becomes CYA
- Nonfiction becomes compliance theater
- Advocacy becomes liability mitigation
- Everything sounds like legal cleared it

#### Detection (to prevent contamination)

```typescript
const BUREAUCRATIC_PATTERNS = [
  /pursuant to/i,
  /in accordance with/i,
  /as per (the|our)/i,
  /it is (the )?policy (of|that)/i,
  /stakeholders/i,
  /leverage (synergies|opportunities)/i,
  /going forward/i,
  /at this time/i,
  /please be advised/i,
  /this (communication|email|document) is/i,
];

function detectBureaucraticContamination(text: string, targetRegime: string): number {
  if (targetRegime === 'bureaucratic') return 0;  // expected
  
  let contamination = 0;
  for (const pattern of BUREAUCRATIC_PATTERNS) {
    const matches = text.match(pattern);
    if (matches) {
      contamination += matches.length * 0.1;
    }
  }
  return Math.min(1, contamination);
}
```

---

## 9. Regime Collision Detection

### 9.1 The Problem

Hybrids are fine. Regime collision is where trust dies.

| Collision | Result |
|-----------|--------|
| Research voice + Advocacy goals | Propaganda smell |
| Tragedy + Satire | Cruelty smell |
| Instruction + Sincerity | Therapy voice, loses actionability |
| Horror + Comedy | Defangs the horror OR makes comedy cruel |
| Negotiation + Advocacy | Manipulation smell |
| Nonfiction + Marketing | "This is selling something" |

### 9.2 Collision Detection

```typescript
interface RegimeCollision {
  regimes: [string, string];
  severity: 'warning' | 'conflict' | 'incompatible';
  resolution: 'choose_dominant' | 'sequence' | 'abort';
}

const COLLISION_MATRIX: Map<string, Map<string, RegimeCollision>> = new Map([
  ['research', new Map([
    ['advocacy', { 
      regimes: ['research', 'advocacy'], 
      severity: 'conflict',
      resolution: 'choose_dominant'
    }],
    ['marketing', {
      regimes: ['research', 'marketing'],
      severity: 'incompatible',
      resolution: 'abort'
    }],
  ])],
  ['tragedy', new Map([
    ['satire', {
      regimes: ['tragedy', 'satire'],
      severity: 'conflict',
      resolution: 'sequence'  // can alternate, not blend
    }],
    ['comedy', {
      regimes: ['tragedy', 'comedy'],
      severity: 'warning',
      resolution: 'choose_dominant'  // with hysteresis
    }],
  ])],
  ['instruction', new Map([
    ['sincerity', {
      regimes: ['instruction', 'sincerity'],
      severity: 'warning',
      resolution: 'choose_dominant'  // sincerity contaminates actionability
    }],
  ])],
  ['negotiation', new Map([
    ['advocacy', {
      regimes: ['negotiation', 'advocacy'],
      severity: 'conflict',
      resolution: 'choose_dominant'  // can't do both
    }],
  ])],
  ['horror', new Map([
    ['comedy', {
      regimes: ['horror', 'comedy'],
      severity: 'conflict',
      resolution: 'sequence'  // must be separated in time
    }],
  ])],
]);
```

### 9.3 Resolution Strategies

**choose_dominant**: One regime takes precedence for the segment
- Apply hysteresis rules
- Suppress secondary regime markers
- Don't blend

**sequence**: Regimes can alternate but not overlap
- Enforce transition buffer (min tokens between)
- Clear regime shift markers
- No blending within segment

**abort**: Cannot produce quality output in both
- Flag for human decision
- Or explicitly choose one and acknowledge limitation

---

## 10. Implementation Priority

### Tier 1: Implement First (High Value, Aligned with Core)

1. **Debugging/Diagnosis** — Structurally aligned with governor stack, crisp testable metrics (hypothesis shrinkage, Fᵢ scoring), your home turf

2. **Instruction** — Clear actionability metrics, immediate practical value, tests well

### Tier 2: Implement Second (Important for Completeness)

3. **Research** — Extends nonfiction naturally, important for technical work

4. **Negotiation** — Useful for conflict-laden contexts, face preservation is measurable

### Tier 3: Implement When Needed

5. **Satire** — Complex double-encoding, but valuable for humor work

6. **Horror** — Extends tragedy framework, useful for fiction module

7. **Advocacy/Marketing** — Tricky because success conditions are ethically loaded

### Tier 4: Handle with Care

8. **Romance** — Highest AI detection sensitivity, proceed carefully

9. **Liturgical** — Niche but interesting, mostly useful for understanding failure modes

10. **Bureaucratic** — Mainly useful as a contamination detector, not a target

---

## 11. Complete Load-Bearing Variable Reference

| Regime | Symbol | Variable | Failure Signal |
|--------|--------|----------|----------------|
| Comedy | Rₚ | Perceived Risk | "Pre-cleared" |
| Tragedy | Iₚ | Perceived Inevitability | Escape hatches |
| Sincerity | Pₙₚ | Non-Performative Presence | Manifesto texture |
| Drama | Sₚ | Stakes Credibility | Plot armor |
| Nonfiction | Eₚ | Epistemic Honesty | PR texture |
| Research | Aᵤ | Auditability | Review article vibe |
| Instruction | Aₚ | Actionability | Filler, ambiguity |
| Debugging | Fᵢ | Fault Isolation | Premature closure |
| Negotiation | Fₚ | Face Preservation | Moralizing, gotcha |
| Advocacy | Mₜ | Motivational Traction | Caught optimizing |
| Marketing | Pₐ | Aspirational Plausibility | Buzzword density |
| Horror | Uₜ | Unresolved Threat | Over-explaining |
| Romance | Vᵥ | Vulnerability Credibility | Quote-bait texture |
| Satire | Dₑ | Double-Encoding Stability | Collapse to sincere |
| Aphorism | Mᶜ | Memorability | Quote-shaped emptiness |
| Liturgical | Sₐ | Sacred Authority | Modern rationalization |
| Bureaucratic | Lₘ | Liability Management | (contamination risk) |

---

## 12. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |

---

*"The task determines which variables are load-bearing."*

*"Hybrids are fine; regime collision is where trust dies."*

*"Debugging is the easiest next win — it's structurally aligned with your governor stack and gives you crisp, testable metrics."*
