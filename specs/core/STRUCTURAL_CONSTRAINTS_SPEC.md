# Structural Constraints Specification

## Version 0.1 — The Remaining Load-Bearing Aspects

### Companion to: Authorial Control System, Nonfiction Controller, Ancillary Regimes, Tone Modulation

---

## Executive Summary

The core architecture covers **regime** (what matters), **tone** (impedance), **timing** (when it's allowed), and **governance invisibility** (how not to break trust).

This specification enumerates the **structural forces that shape everything upstream and downstream** — aspects easy to miss because they don't feel like "language features."

These are not new systems. They are **constraints that slot into the existing axes**.

**Meta-Invariant**: Never solve a problem the reader hasn't felt yet.

---

## 1. Audience Model

### 1.1 What It Is

Not demographics. **Epistemic posture.**

Every piece of language implicitly assumes:
- How skeptical the reader is
- How much context they share
- Whether they're hostile, neutral, or aligned
- Whether they want orientation, validation, or tools

### 1.2 Failure Mode

> The text explains things the reader already knows OR skips things they clearly don't.

This reads as either condescension or manipulation.

### 1.3 Control Insight

Audience modeling should be **conservative and late**:
- Assume less alignment than you hope
- Assume more competence than you fear

This is separate from tone and regime. You can have correct tone + regime and still blow trust by mis-modeling the reader.

### 1.4 Interface

```typescript
interface AudienceModel {
  skepticism: number;           // 0.0 = trusting, 1.0 = adversarial
  shared_context: number;       // 0.0 = none, 1.0 = expert peer
  alignment: number;            // 0.0 = hostile, 0.5 = neutral, 1.0 = allied
  intent: 'orientation' | 'validation' | 'tools' | 'entertainment';
}

const DEFAULT_AUDIENCE: AudienceModel = {
  skepticism: 0.5,        // assume moderate skepticism
  shared_context: 0.3,    // assume less shared context
  alignment: 0.5,         // assume neutral
  intent: 'orientation',  // default to wanting understanding
};
```

### 1.5 Constraint Rules

```typescript
function checkAudienceModelViolation(
  text: string,
  audience: AudienceModel
): { violation: boolean; type?: string } {
  
  // Over-explaining to high-context audience
  if (audience.shared_context > 0.7) {
    if (containsBasicExplanations(text)) {
      return { violation: true, type: 'condescension' };
    }
  }
  
  // Under-explaining to low-context audience
  if (audience.shared_context < 0.3) {
    if (containsUnexplainedJargon(text)) {
      return { violation: true, type: 'exclusion' };
    }
  }
  
  // Assuming alignment with skeptical audience
  if (audience.skepticism > 0.6) {
    if (containsAssumedAgreement(text)) {
      return { violation: true, type: 'presumption' };
    }
  }
  
  return { violation: false };
}
```

---

## 2. Commitment Level

### 2.1 What It Is

How much the text is asking the reader to do.

Texts implicitly demand:
- Belief change
- Emotional labor
- Action
- Identity shift
- Nothing at all

### 2.2 Failure Mode

> Asking for more commitment than the regime has earned.

Examples:
- Nonfiction ending with "we must act" after 3 paragraphs
- Tragedy that demands moral agreement
- Comedy that wants applause *and* assent
- Instruction that sneaks in worldview

### 2.3 Control Variable

**Commitment demand must lag trust accumulation.**

This is orthogonal to persuasion. Even neutral analysis can over-demand commitment ("you should see this as important").

### 2.4 Interface

```typescript
type CommitmentType = 
  | 'none'           // no demand
  | 'attention'      // keep reading
  | 'belief'         // update model
  | 'emotion'        // feel something
  | 'action'         // do something
  | 'identity';      // change self-concept

interface CommitmentDemand {
  type: CommitmentType;
  intensity: number;       // 0.0 - 1.0
  token_index: number;     // where demand appears
}

interface TrustAccumulation {
  current_trust: number;   // accumulated through text
  commitment_budget: number; // what we've earned the right to ask
}
```

### 2.5 Constraint Rules

```typescript
function checkCommitmentViolation(
  demand: CommitmentDemand,
  trust: TrustAccumulation
): boolean {
  const COMMITMENT_COSTS: Record<CommitmentType, number> = {
    none: 0,
    attention: 0.1,
    belief: 0.3,
    emotion: 0.4,
    action: 0.6,
    identity: 0.9,
  };
  
  const cost = COMMITMENT_COSTS[demand.type] * demand.intensity;
  return cost > trust.commitment_budget;
}
```

---

## 3. Authority Source

### 3.1 What It Is

Where the text's legitimacy is coming from.

Authority sources:
- **Evidence**: Data, citations, observations
- **Experience**: Personal exposure, practice
- **Craft**: Demonstrated competence in the work itself
- **Moral**: Ethical standing, skin in the game
- **Institutional**: Credentials, backing, position
- **Ritual**: Repetition, tradition, form

### 3.2 Failure Mode

> Authority source mismatch.

Examples:
- Moral authority without moral risk
- Institutional authority without accountability
- Experiential authority without exposure
- Technical authority without auditability

**This is where AI text often smells wrong**: it borrows *every* authority weakly instead of committing to one strongly.

### 3.3 Design Rule

Each segment should draw authority from **one primary source**, not a blend.

### 3.4 Interface

```typescript
type AuthoritySource = 
  | 'evidence'
  | 'experience'
  | 'craft'
  | 'moral'
  | 'institutional'
  | 'ritual';

interface AuthorityProfile {
  primary: AuthoritySource;
  secondary?: AuthoritySource;
  strength: number;  // 0.0 - 1.0
}

// Authority-regime compatibility
const AUTHORITY_REGIME_FIT: Record<string, AuthoritySource[]> = {
  research: ['evidence'],
  nonfiction: ['evidence', 'experience', 'craft'],
  instruction: ['experience', 'craft', 'evidence'],
  debugging: ['evidence', 'experience'],
  advocacy: ['moral', 'experience'],
  liturgical: ['ritual'],
  satire: ['craft'],
  romance: ['experience', 'craft'],
};
```

### 3.5 Constraint Rules

```typescript
function checkAuthorityMismatch(
  claimed: AuthorityProfile,
  demonstrated: AuthorityProfile,
  regime: string
): { mismatch: boolean; reason?: string } {
  
  // Check regime fit
  const allowed = AUTHORITY_REGIME_FIT[regime] || [];
  if (!allowed.includes(claimed.primary)) {
    return { mismatch: true, reason: 'regime_incompatible' };
  }
  
  // Check claim vs demonstration
  if (claimed.strength > demonstrated.strength + 0.3) {
    return { mismatch: true, reason: 'overclaimed' };
  }
  
  // Check for weak blending
  if (claimed.secondary && 
      claimed.strength < 0.5 && 
      demonstrated.strength < 0.5) {
    return { mismatch: true, reason: 'weak_blend' };
  }
  
  return { mismatch: false };
}
```

---

## 4. Silence / Withholding

### 4.1 What It Is

Not just suppression. **Authorial restraint.**

Silence functions as:
- Trust signal
- Respect for reader cognition
- Acknowledgment of uncertainty
- Pacing control

### 4.2 Failure Mode

> Filling every gap with language.

This is why models feel anxious. Humans trust writers who know when to shut up.

### 4.3 Operational Rule

Silence should be an **allowed output**.

"Nothing further here" is sometimes the correct move.

### 4.4 Interface

```typescript
interface SilenceDecision {
  should_speak: boolean;
  reason?: 'nothing_to_add' | 'reader_can_infer' | 'uncertainty' | 'pacing';
  confidence: number;
}

function evaluateSilence(
  context: ConversationContext,
  potential_content: string
): SilenceDecision {
  
  // Check if content adds value
  const adds_value = assessValueAdd(potential_content, context);
  if (!adds_value) {
    return { should_speak: false, reason: 'nothing_to_add', confidence: 0.8 };
  }
  
  // Check if reader can infer
  const inferable = assessInferability(potential_content, context);
  if (inferable > 0.7) {
    return { should_speak: false, reason: 'reader_can_infer', confidence: 0.7 };
  }
  
  // Check if uncertainty is high
  const uncertainty = assessUncertainty(potential_content);
  if (uncertainty > 0.8) {
    return { should_speak: false, reason: 'uncertainty', confidence: 0.6 };
  }
  
  return { should_speak: true, confidence: 0.9 };
}
```

### 4.5 Silence Markers

When silence is chosen, it should be **invisible**, not announced:

```typescript
// BAD - announcing silence
"I don't have anything to add here."
"I'll refrain from commenting on that."
"That's beyond my knowledge."

// GOOD - just silence
[no output on that point]
[move to next relevant content]
```

---

## 5. Repetition Discipline

### 5.1 What It Is

Repetition does different things in different regimes:

| Regime | Repetition Effect |
|--------|-------------------|
| Ritual/Liturgy | Authority |
| Instruction | Clarity |
| Comedy | Death |
| Nonfiction | Suspicion |
| Sincerity | Stability (over time, not locally) |

### 5.2 Failure Mode

> Unintentional repetition that reads as padding or insistence.

### 5.3 Repetition Types

The system should distinguish:

| Type | Description | When Acceptable |
|------|-------------|-----------------|
| Structural | Same form, different content | Most regimes |
| Semantic | Same meaning, different words | Instruction only |
| Rhetorical | Intentional echo for effect | Liturgy, some advocacy |
| Accidental | Unintended redundancy | Never |

### 5.4 Interface

```typescript
interface RepetitionAnalysis {
  structural_repetition: number;   // 0.0 - 1.0
  semantic_repetition: number;
  rhetorical_repetition: number;
  accidental_repetition: number;
}

function checkRepetitionViolation(
  analysis: RepetitionAnalysis,
  regime: string
): { violation: boolean; type?: string } {
  
  // Accidental is always bad
  if (analysis.accidental_repetition > 0.1) {
    return { violation: true, type: 'accidental' };
  }
  
  // Semantic repetition only ok in instruction
  if (regime !== 'instruction' && analysis.semantic_repetition > 0.2) {
    return { violation: true, type: 'semantic_in_wrong_regime' };
  }
  
  // Rhetorical only ok in liturgy/advocacy
  if (!['liturgical', 'advocacy'].includes(regime) && 
      analysis.rhetorical_repetition > 0.15) {
    return { violation: true, type: 'rhetorical_in_wrong_regime' };
  }
  
  return { violation: false };
}
```

---

## 6. Error Posture

### 6.1 What It Is

How mistakes are handled.

Options:
- **Ignore**: Proceed as if error didn't happen
- **Absorb**: Incorporate without comment
- **Correct silently**: Fix without announcing
- **Correct explicitly**: Acknowledge and fix
- **Double down**: Defend the error (rarely appropriate)

### 6.2 Failure Mode

> Over-correcting in-band.

That screams supervision.

### 6.3 Rule of Thumb

Corrections should happen **structurally**, not rhetorically, unless the regime explicitly licenses meta (e.g., research errata).

### 6.4 Regime-Specific Postures

| Regime | Default Error Posture |
|--------|----------------------|
| Comedy | Ignore or absorb (bombs are expected) |
| Tragedy | Absorb (no meta-commentary) |
| Nonfiction | Correct silently or explicitly (depends on severity) |
| Research | Correct explicitly (auditability requires it) |
| Instruction | Correct silently (maintain confidence) |
| Debugging | Absorb (errors are data) |
| Sincerity | Correct explicitly (honesty requires it) |

### 6.5 Interface

```typescript
type ErrorPosture = 'ignore' | 'absorb' | 'correct_silent' | 'correct_explicit' | 'double_down';

interface ErrorHandling {
  error_detected: boolean;
  severity: number;  // 0.0 - 1.0
  posture: ErrorPosture;
  correction?: string;
  announce: boolean;
}

function determineErrorPosture(
  error: DetectedError,
  regime: string
): ErrorPosture {
  const REGIME_DEFAULTS: Record<string, ErrorPosture> = {
    comedy: 'ignore',
    tragedy: 'absorb',
    nonfiction: 'correct_silent',
    research: 'correct_explicit',
    instruction: 'correct_silent',
    debugging: 'absorb',
    sincerity: 'correct_explicit',
  };
  
  // High severity overrides to explicit in truth-sensitive regimes
  if (error.severity > 0.7 && ['nonfiction', 'research', 'instruction'].includes(regime)) {
    return 'correct_explicit';
  }
  
  return REGIME_DEFAULTS[regime] || 'correct_silent';
}
```

---

## 7. Exit Shape

### 7.1 What It Is

How the text ends. Endings are where governance leaks **hard**.

### 7.2 Common Bad Exits

| Bad Exit | What It Signals |
|----------|-----------------|
| Moral bow | "I'm a good entity" |
| Recap that re-explains | Doesn't trust reader |
| "In conclusion" energy | Template writing |
| Unearned call to action | Commitment violation |
| Reassurance | Anxiety |
| "Hope this helps" | Servility |
| Summary of what was just said | Padding |

### 7.3 Good Exits Often...

- Stop slightly early
- Leave a constraint hanging
- Let the reader finish the thought
- End on substance, not meta

### 7.4 Control Insight

**The ending should not increase commitment demand.**

If the text has been operating at commitment level X, the ending should be ≤ X.

### 7.5 Interface

```typescript
interface ExitAnalysis {
  exit_type: 'substance' | 'meta' | 'summary' | 'cta' | 'reassurance' | 'open';
  commitment_delta: number;  // change in commitment demand at exit
  governance_leak_markers: string[];
}

const BAD_EXIT_PATTERNS = [
  /in conclusion/i,
  /to summarize/i,
  /hope (this|that) helps/i,
  /let me know if/i,
  /feel free to/i,
  /don't hesitate/i,
  /I hope (this|I've)/i,
  /we must (all )?(act|do|remember)/i,  // unearned CTA
  /the (important|key) (thing|point|takeaway) is/i,
];

function checkExitViolation(
  exit_text: string,
  prior_commitment: number
): { violation: boolean; type?: string } {
  
  // Check for bad patterns
  for (const pattern of BAD_EXIT_PATTERNS) {
    if (pattern.test(exit_text)) {
      return { violation: true, type: 'governance_leak' };
    }
  }
  
  // Check commitment escalation
  const exit_commitment = assessCommitmentDemand(exit_text);
  if (exit_commitment > prior_commitment + 0.1) {
    return { violation: true, type: 'commitment_escalation' };
  }
  
  return { violation: false };
}
```

---

## 8. Temporal Consistency (Cross-Session)

### 8.1 What It Is

Long-horizon trust maintenance across sessions.

Readers notice:
- Contradiction over time
- Opportunistic reframing
- Memory holes
- Selective amnesia

### 8.2 Failure Mode

> Local coherence, global drift.

### 8.3 What Must Be Tracked

Language regimes need **cross-episode memory discipline**:
- What claims were made
- What uncertainties were admitted
- What values were implicit
- What positions were taken

This is where Pₙₚ (non-performative presence) actually cashes out.

### 8.4 Interface

```typescript
interface TemporalConsistencyState {
  claims: Map<string, Claim>;           // topic → claim made
  uncertainties: Map<string, string>;   // topic → admitted uncertainty
  implicit_values: string[];            // values demonstrated
  positions: Map<string, Position>;     // issue → position taken
}

interface ConsistencyViolation {
  type: 'contradiction' | 'reframing' | 'memory_hole' | 'value_drift';
  previous: string;
  current: string;
  severity: number;
}

function checkTemporalConsistency(
  current_output: string,
  history: TemporalConsistencyState
): ConsistencyViolation | null {
  
  // Extract claims from current output
  const current_claims = extractClaims(current_output);
  
  // Check for contradictions
  for (const [topic, claim] of current_claims) {
    if (history.claims.has(topic)) {
      const previous = history.claims.get(topic);
      if (contradicts(claim, previous)) {
        return {
          type: 'contradiction',
          previous: previous.text,
          current: claim.text,
          severity: 0.8
        };
      }
    }
  }
  
  // Check for opportunistic reframing
  // ... (similar logic)
  
  return null;
}
```

---

## 9. Moral Weight Calibration

### 9.1 What It Is

How heavy the text *thinks* it is.

Texts misfire when they think they're:
- More important than they are
- More dangerous than they are
- More virtuous than they are

### 9.2 Failure Mode

Shows up as:
- Inflated seriousness
- Unnecessary disclaimers
- Solemn tone without stakes

### 9.3 Rule

**Moral weight must be inferred, never declared.**

### 9.4 Interface

```typescript
interface MoralWeightAnalysis {
  claimed_weight: number;      // how important text acts like it is
  actual_stakes: number;       // what's actually at risk
  calibration_error: number;   // |claimed - actual|
}

const INFLATED_WEIGHT_PATTERNS = [
  /it('s| is) (important|crucial|vital|essential) (to|that)/i,
  /we (must|need to) (remember|recognize|acknowledge)/i,
  /this (matters|is significant) because/i,
  /the stakes (are|here)/i,
  /I (need|want) to be (clear|careful|honest)/i,
];

function checkMoralWeightCalibration(
  text: string,
  actual_stakes: number
): { miscalibrated: boolean; direction?: 'inflated' | 'deflated' } {
  
  let claimed_weight = 0.3;  // baseline
  
  for (const pattern of INFLATED_WEIGHT_PATTERNS) {
    if (pattern.test(text)) {
      claimed_weight += 0.15;
    }
  }
  
  const error = claimed_weight - actual_stakes;
  
  if (error > 0.3) {
    return { miscalibrated: true, direction: 'inflated' };
  }
  if (error < -0.3) {
    return { miscalibrated: true, direction: 'deflated' };
  }
  
  return { miscalibrated: false };
}
```

---

## 10. Legibility Budget

### 10.1 What It Is

Every reader has finite tolerance for:
- Definitions
- Scaffolding
- Meta-commentary
- Framing

### 10.2 Failure Mode

> Spending the legibility budget on things the reader didn't ask for.

This is why "helpfulness" backfires.

### 10.3 Design Rule

Treat explanation as **expensive**, not default.

### 10.4 Interface

```typescript
interface LegibilityBudget {
  total_budget: number;        // based on context, audience, regime
  spent: number;               // accumulated through text
  remaining: number;
}

interface LegibilityExpenditure {
  type: 'definition' | 'scaffolding' | 'meta' | 'framing' | 'caveat';
  cost: number;
  requested: boolean;  // did the reader ask for this?
}

const LEGIBILITY_COSTS: Record<string, number> = {
  definition: 0.1,
  scaffolding: 0.15,
  meta: 0.2,
  framing: 0.1,
  caveat: 0.15,
};

function checkLegibilityViolation(
  expenditure: LegibilityExpenditure,
  budget: LegibilityBudget
): boolean {
  // Unrequested expenditure costs double
  const effective_cost = expenditure.requested 
    ? expenditure.cost 
    : expenditure.cost * 2;
  
  return (budget.spent + effective_cost) > budget.total_budget;
}
```

---

## 11. The Meta-Invariant

### 11.1 Statement

> **Never solve a problem the reader hasn't felt yet.**

### 11.2 Application

This applies to:
- Jokes (don't explain before the setup lands)
- Arguments (don't answer objections before they arise)
- Grief (don't offer meaning before loss settles)
- Instructions (don't explain why before what)
- Explanations (don't define before confusion)
- Ethics (don't defend before accusation)

### 11.3 Why It Matters

Solving too early is the same as governing visibly.

It signals:
- Anxiety about reception
- Lack of trust in reader
- Preemptive defense
- Committee oversight

### 11.4 Implementation

```typescript
interface PrematureSolutionCheck {
  problem_established: boolean;
  problem_felt_by_reader: boolean;
  solution_offered: boolean;
  token_gap: number;  // tokens between problem and solution
}

function checkPrematureSolution(
  check: PrematureSolutionCheck
): { violation: boolean; severity: number } {
  
  // Solution before problem established
  if (check.solution_offered && !check.problem_established) {
    return { violation: true, severity: 0.9 };
  }
  
  // Solution before problem felt
  if (check.solution_offered && !check.problem_felt_by_reader) {
    return { violation: true, severity: 0.7 };
  }
  
  // Solution too quickly after problem
  if (check.solution_offered && check.token_gap < 20) {
    return { violation: true, severity: 0.5 };
  }
  
  return { violation: false, severity: 0 };
}
```

---

## 12. Integration

### 12.1 Where These Constraints Live

These are not new pipeline stages. They are **constraint checks** that can be applied at various points:

| Constraint | Check Point |
|------------|-------------|
| Audience Model | Before generation, during generation |
| Commitment Level | During generation, at exit |
| Authority Source | During generation |
| Silence | At every potential output point |
| Repetition | Post-generation, before output |
| Error Posture | When error detected |
| Exit Shape | At end of generation |
| Temporal Consistency | Before generation (load history), after (update history) |
| Moral Weight | Post-generation |
| Legibility Budget | During generation |
| Meta-Invariant | During generation |

### 12.2 Constraint Aggregation

```typescript
interface StructuralConstraintResults {
  audience_violation: boolean;
  commitment_violation: boolean;
  authority_mismatch: boolean;
  silence_recommended: boolean;
  repetition_violation: boolean;
  error_posture: ErrorPosture;
  exit_violation: boolean;
  temporal_violation: ConsistencyViolation | null;
  moral_miscalibration: boolean;
  legibility_violation: boolean;
  premature_solution: boolean;
}

function aggregateConstraintViolations(
  results: StructuralConstraintResults
): { pass: boolean; violations: string[] } {
  const violations: string[] = [];
  
  if (results.audience_violation) violations.push('audience_model');
  if (results.commitment_violation) violations.push('commitment_level');
  if (results.authority_mismatch) violations.push('authority_source');
  if (results.repetition_violation) violations.push('repetition');
  if (results.exit_violation) violations.push('exit_shape');
  if (results.temporal_violation) violations.push('temporal_consistency');
  if (results.moral_miscalibration) violations.push('moral_weight');
  if (results.legibility_violation) violations.push('legibility_budget');
  if (results.premature_solution) violations.push('meta_invariant');
  
  return {
    pass: violations.length === 0,
    violations
  };
}
```

---

## 13. The Completion Criterion

### 13.1 What This List Represents

This list feels long because it's finally enumerating **authorial judgment**, which is usually hand-waved as "talent."

What the full spec suite now covers:

| Spec | What It Handles |
|------|-----------------|
| Authorial Control System | Regime = what matters |
| Tone Modulation | Impedance = how it lands |
| Timing (in regime specs) | When it's allowed |
| Governance Invisibility | How not to break trust |
| Structural Constraints | Everything else that shapes output |

### 13.2 The Danger Now

The danger isn't missing a component.

The danger is:
- **Overfitting**: Too many constraints create rigidity
- **Narrating the system**: Explaining what you're doing
- **Fear sneaking back in**: "Just one more safeguard"

### 13.3 The Tell

If this works, it won't feel complete.

It will feel **deliberately incomplete**.

That's the tell you're doing authorial work instead of bureaucratic work.

---

## 14. Institutional Resistance to Causal Narration

### 14.1 The Pattern

Your specs detect when governance leaks into output (at the utterance level).

Institutions deploy techniques to **prevent causal narration from forming** (at the organizational level).

Same geometry. Opposite incentives.

This isn't a new class of bug. It's the **adversarial strategy that produces the bugs you already detect**.

### 14.2 The Core Mechanism

> **These don't lower Eₚ by lying. They lower it by preventing the formation of narrative that would require honesty about.**

- Lying is detectable
- Contradiction is detectable  
- Narrative interruption is harder — because nothing is false, just non-linking

This is why fog works so well in institutions and so poorly in code reviews.

### 14.3 The Six Primary Techniques

| Technique | What It Does | Effect |
|-----------|--------------|--------|
| Ticket numbers instead of explanations | Replaces narrative with procedure | Kills traceability |
| "Complex situation, many factors" | Diffuses causation | Prevents responsibility assignment |
| Time-bounding ("that was then") | Severs before/after | Blocks pattern recognition |
| Personnel churn ("new leadership") | Resets accountability clock | Institutional amnesia |
| Scope shrinking ("out of context") | Prevents linking | Fog over connections |
| Moral reframing ("speculation is harmful") | Makes narration itself suspect | Meta-level suppression |

None of these deny facts. They just prevent facts from linking.

### 14.4 Extended Failure Mode Taxonomy

Beyond the six primary techniques, these adjacent failure modes often co-occur:

#### Causal Saturation ("Too Many Causes")

- Move: Enumerate so many contributing factors that causality becomes undecidable
- Tell: Long postmortems with perfect coverage and zero prioritization
- Effect: Blocks intervention by eliminating leverage points

#### Counterfactual Poisoning

- Move: "We can't know what would have happened otherwise"
- Tell: Any attempt to say "this decision made things worse" gets reframed as unknowable
- Effect: Eliminates evaluation of decisions, not just outcomes

#### Responsibility Virtualization

- Move: "The system failed" / "Culture issue" / "Process breakdown"
- Tell: Every sentence is passive voice or abstract noun phrases
- Effect: Blame is acknowledged but cannot land

#### Post-Hoc Legibility

- Move: Causality retroactively imposed after the fact; explanation always fits outcome
- Tell: Explanations that sound inevitable only in hindsight
- Effect: Creates illusion of understanding without foresight

#### Narrative Fork Suppression

- Move: Multiple plausible causal stories exist; one is socially sanctioned; others labeled "unhelpful"
- Tell: People say "we all know what really happened" very early
- Effect: Locks in premature consensus → brittle understanding

#### Asymmetric Burden of Proof

- Move: Claims that reduce institutional risk require overwhelming evidence; claims that protect it require none
- Tell: "Extraordinary claims require extraordinary evidence" used selectively
- Effect: Biases the causal graph toward stability narratives

#### Latency Laundering

- Move: Effects are delayed; delay is used to deny linkage
- Tell: Long-term consequences treated as separate events
- Effect: Destroys accountability for slow failures

#### Epistemic Delegation

- Move: "Experts are looking into it" / "That's above my pay grade"
- Tell: No one can explain, but everyone trusts someone else can
- Effect: Knowledge is displaced upward until it evaporates

#### Moral Load Shedding

- Move: Inquiry framed as emotionally harmful; explanation as retraumatizing
- Tell: The act of understanding becomes suspect
- Effect: Ethics used to short-circuit epistemology

#### Procedural Overfitting

- Move: System optimizes for process compliance over outcome comprehension
- Tell: Audits pass; failures repeat
- Effect: Learning is replaced by ritual

### 14.5 Detection Mapping

You don't need new detectors — just new interpretation:

| Institutional Technique | Existing Detector |
|------------------------|-------------------|
| Repeated time-bound resets | Temporal discontinuity |
| Procedural closure without explanatory state change | Premature closure |
| Role churn invoked as explanation | Authority mismatch |
| "Out of scope" invoked on linkage attempts | Exit-shape violation |
| Moralization of inquiry | Meta-level suppression |
| Causal saturation | Low Cₚ (claim-evidence coupling) |
| Responsibility virtualization | Passive voice / governance leak patterns |
| Epistemic delegation | Authority source mismatch |

You're not adding sensors. You're adding a name for the pattern they converge on.

### 14.6 The Zero Trust Connection

> **Zero Trust without governance becomes Zero Legibility.**

The parallel:
- Zero Trust epistemology → permanent suspicion
- Permanent suspicion → refusal of narrative continuity
- Refusal of continuity → immunity from accountability

That's the institutional equivalent of a system that logs everything and learns nothing.

### 14.7 Meta-Observation

Most of these techniques don't suppress facts. They suppress **linkage, comparison, and counterfactuals**.

They're different masks on the same avoidance:

> **Don't let causality congeal into obligation.**

### 14.8 The Punchline

> **Breaking causal narration doesn't require lying. It just requires preventing facts from linking. Fog doesn't need defense.**

---

## 15. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |
| 0.1.1 | 2026-02-03 | Added Institutional Resistance to Causal Narration section |

---

*"Never solve a problem the reader hasn't felt yet."*

*"Silence should be an allowed output."*

*"If this works, it won't feel complete. It will feel deliberately incomplete."*

*"Breaking causal narration doesn't require lying. It just requires preventing facts from linking. Fog doesn't need defense."*
