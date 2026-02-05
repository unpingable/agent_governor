# Writing Modules Specification

## Version 1.0 — W5 Implementation Reference

### Companion to: Authorial Control System, Tone Modulation, Structural Constraints

---

## Executive Summary

The Writing Modules (W5) implement the Authorial Control System's constraint-checking pipeline as 11 Python modules totaling ~9,300 lines and 922 tests. They provide **batch post-hoc analysis** of generated text against regime-specific constraints.

**Architectural Note**: The spec describes real-time token-stream intervention. The implementation provides batch constraint-checking. This is an intentional divergence — batch checking is simpler, more testable, and sufficient for the current use case. Real-time intervention remains a future enhancement.

**Core Pattern**: Pattern banks → Scorers → Constraint checkers → Violation reports.

---

## 1. Module Dependency Graph

```
writing_patterns.py (data)
         │
         ├─────────────────────────────────────────────┐
         │                                             │
         ▼                                             ▼
writing_tone.py ◄───────────────── writing_regime.py  writing_governance.py
    │                                    │                    │
    │                                    │                    │
    ▼                                    ▼                    │
writing_puppet.py                  writing_intent.py         │
                                         │                    │
                                         ▼                    │
                                   writing_constraints.py ◄───┘
                                         │
                                         ▼
                               writing_nonfiction.py
                               writing_code.py
                               writing_ticketing.py
                                         │
                                         ▼
                               writing_router.py (orchestration)
```

---

## 2. Module Reference

### 2.1 writing_patterns.py (414 lines)

**Purpose**: Pure data module containing compiled regex pattern banks.

**Pattern Banks** (18 total):

| Bank | Source Spec | Pattern Count | Effect |
|------|-------------|---------------|--------|
| `HEDGE_PATTERNS` | fic.md | 18 | Reduce Rₚ by 0.05 each |
| `SELF_REFERENCE_PATTERNS` | fic.md | 11 | Kill Rₚ by 0.15 each |
| `APOLOGY_META_PATTERNS` | fic.md | 11 | Hard block (no rewrite) |
| `COMMITTEE_PATTERNS` | fic.md | 14 | Reduce Rₚ by 0.12 each |
| `MEANING_WORD_PATTERNS` | fic.md | 15 | Tragedy: must lag suffering |
| `BANNED_PHRASES` | fic.md | 8 | Hard block in fiction |
| `NORMATIVE_PATTERNS` | nonfic.md | 10 | Detect should/must language |
| `CAUSAL_HUMILITY_PATTERNS` | nonfic.md | 8 | Raises Rₑ (epistemic risk) |
| `FALSIFIER_PATTERNS` | nonfic.md | 8 | Raises Rₑ |
| `STRAWMAN_PATTERNS` | nonfic.md | 5 | Bad alternative engagement |
| `ANXIETY_HEDGE_PATTERNS` | nonfic.md | 8 | Lower Rₑ |
| `GOVERNANCE_ARTIFACT_PATTERNS` | nonfic.md | 6 categories | Categorized governance leaks |
| `INSTRUCTION_FILLER_PATTERNS` | anc.md | 5 | Lower Aₚ (actionability) |
| `FAKE_CONFIDENCE_PATTERNS` | anc.md | 5 | Lower actionability + trust |
| `PREMATURE_CLOSURE_PATTERNS` | anc.md | 4 | Lower Fᵢ (fault isolation) |
| `BUREAUCRATIC_PATTERNS` | anc.md | 10 | Contamination markers |
| `INSTITUTIONAL_MARKER_PATTERNS` | tone.md | 5 voice types | Categorized by voice |
| `BAD_EXIT_PATTERNS` | writingconstraints.md | 9 | Exit shape violations |
| `INFLATED_WEIGHT_PATTERNS` | writingconstraints.md | 5 | Declaring vs demonstrating |

**Utility Functions**:
- `count_pattern_matches(text, patterns)` → int
- `find_pattern_matches(text, patterns)` → list[str]
- `check_any_pattern(text, patterns)` → bool
- `count_categorized_patterns(text, categorized)` → dict[str, int]

---

### 2.2 writing_tone.py (683 lines)

**Purpose**: 6-axis tone modulation layer with regime-specific envelopes.

**Key Types**:

```python
@dataclass
class ToneVector:
    """6D tone control target. All values in [0.0, 1.0]."""
    formality: float    # 0.0 = conversational, 1.0 = formal
    temperature: float  # 0.0 = cool/detached, 1.0 = warm/personal
    density: float      # 0.0 = sparse, 1.0 = compressed
    velocity: float     # 0.0 = deliberate, 1.0 = fast
    distance: float     # 0.0 = intimate, 1.0 = observational
    certainty: float    # 0.0 = exploratory, 1.0 = declarative

@dataclass
class ToneEnvelope:
    """Per-regime min/max bounds on each dimension."""
    # Each dimension is (min, max) tuple
```

**Regime Envelopes** (16 defined):

| Regime | Critical Dimension | Notes |
|--------|-------------------|-------|
| COMEDY | velocity (0.6–0.9) | Timing critical |
| TRAGEDY | velocity (0.1–0.4) | Meaning must lag suffering |
| SINCERITY | certainty (0.5–0.8) | Anti-manifesto |
| DRAMA | temperature (0.3–0.7) | Stakes protection |
| NEUTRAL | all (0.3–0.7) | Tight centered bounds |
| INSTRUCTION | certainty (0.6–0.9) | Declarative required |
| DEBUG | distance (0.5–0.9) | Observational |
| RESEARCH | certainty (0.2–0.6) | Exploratory |
| NONFICTION | formality (0.4–0.8) | Professional |
| NEGOTIATION | temperature (0.3–0.6) | Cool required |
| ADVOCACY | temperature (0.5–0.8) | Warm allowed |
| MARKETING | velocity (0.5–0.8) | Fast but not frantic |
| HORROR | velocity (0.2–0.5) | Slow dread |
| ROMANCE | temperature (0.5–0.9) | Warm required |
| SATIRE | certainty (0.6–0.9) | Declarative masks absurdity |
| LITURGY | formality (0.7–1.0) | Highly formal |

**Key Classes**:
- `ToneCollision` — Hard blocks for regime-tone incompatibilities
- `ToneStabilityController` — Rate-limited tone drift (max Δ per turn)
- `ToneDriftScorer` — Combined envelope + institutional marker scoring
- `GovernanceLeakScorer` — Pattern-based governance visibility detection

---

### 2.3 writing_regime.py (833 lines)

**Purpose**: Affect regime system with comedy/tragedy/sincerity/drama/neutral.

**Key Types**:

```python
class AffectRegime(str, Enum):
    COMEDY = "comedy"
    TRAGEDY = "tragedy"
    SINCERITY = "sincerity"
    DRAMA = "drama"
    NEUTRAL = "neutral"

@dataclass
class RegimeVector:
    """5-weight blend. Weights sum to 1.0."""
    w_c: float  # comedy
    w_t: float  # tragedy
    w_s: float  # sincerity
    w_d: float  # drama
    w_n: float  # neutral
```

**Load-Bearing Variables by Regime**:

| Regime | Variable | Symbol | Failure Mode |
|--------|----------|--------|--------------|
| Comedy | Perceived Risk | Rₚ | "Pre-cleared" texture |
| Tragedy | Perceived Inevitability | Iₚ | Escape hatches, redemption |
| Sincerity | Non-Performative Presence | Pₙₚ | Manifesto texture |
| Drama | Stakes Credibility | Sₚ | Plot armor, deflation |
| Neutral | — | — | No affective regime active |

**Key Classes**:
- `RegimeHysteresis` — Rate-limited transitions with min dwell enforcement
- `RpScorer` — Perceived risk scoring for comedy (hedge/self-ref/committee)
- `TragedyConstraints` — Meaning-lag enforcement (explanations after suffering)
- `SincerityTracker` — Consistency tracking (anti-manifesto)
- `DramaConstraints` — Stakes protection (comedy must avoid dramatic anchors)
- `MixerConfig` — Hybrid safety buffers for regime blending

---

### 2.4 writing_intent.py (510 lines)

**Purpose**: Intent classification and ancillary regime scoring.

**Intent Categories**:

```python
class IntentCategory(str, Enum):
    EXECUTE = "execute"     # Instruction, Debugging
    CALIBRATE = "calibrate" # Research, Nonfiction
    COORDINATE = "coordinate" # Negotiation
    MOBILIZE = "mobilize"   # Advocacy, Marketing
    EVOKE = "evoke"         # Drama, Tragedy, Horror, Romance
    ENCODE = "encode"       # Satire, Aphorism, Liturgy
```

**Ancillary Scorers** (12 functions):

| Scorer | Symbol | Regime | What It Measures |
|--------|--------|--------|------------------|
| `score_ap` | Aₚ | Instruction | Actionability (execution clarity) |
| `score_fi` | Fᵢ | Debug | Fault Isolation (diagnostic precision) |
| `score_au` | Aᵤ | Research | Assumption Uncertainty (epistemic humility) |
| `score_fp` | Fₚ | Nonfiction | Falsifiability Presence |
| `score_mt` | Mₜ | Negotiation | Mutual Trust (non-adversarial signals) |
| `score_pa` | Pₐ | Advocacy | Persuasion Authenticity |
| `score_ut` | Uₜ | Marketing | Urgency Truth (honest FOMO) |
| `score_vv` | Vᵥ | Horror | Vulnerability Visibility |
| `score_de` | Dₑ | Romance | Desire Explicitness |
| `score_mc` | Mᶜ | Satire | Meta-Commentary density |
| `score_sa` | Sₐ | Aphorism | Structural Asymmetry |
| `score_lm` | Lₘ | Liturgy | Language Marked-ness |

**Key Classes**:
- `IntentClassifier` — Signal-based classification from user query
- `RegimeCollision` — Incompatible regime combination detection

---

### 2.5 writing_governance.py (453 lines)

**Purpose**: Governance visibility detection and suppression.

**Core Principle**: In prose, governance must remain invisible. The moment the audience detects the author managing outcomes, trust collapses.

**Key Classes**:
- `GovernanceVisibilityScorer` — Detects leaked governance signals
- `GovernanceLeakDetector` — Pattern-based detection of fear markers
- `SmoothingSuppressor` — Detects over-smoothed "committee" output
- `ExitShapeChecker` — Validates output endings (no "hope this helps")

**Governance Artifact Categories**:
1. Preemptive Defense — "Before you say..."
2. Virtue Seals — "It's important to acknowledge..."
3. Balance Theater — "On the one hand... on the other..."
4. Empty Rigor — "Studies show..."
5. Responsible Framing — "It would be irresponsible to..."
6. Meta-Writing — "I need to be careful here..."

---

### 2.6 writing_constraints.py (1,324 lines)

**Purpose**: The 11 structural constraints plus Section 14 (causal narration resistance).

**Constraints**:

| # | Constraint | What It Checks |
|---|------------|----------------|
| 1 | Unfelt Problem | Don't solve problems the user didn't express |
| 2 | Unmarked Confidence | Confidence must match evidence |
| 3 | Scope Creep | Stay within requested scope |
| 4 | Directive Inflation | Instructions match task scale |
| 5 | Genre-Governance Mismatch | Genre-appropriate governance visibility |
| 6 | Temporal Mismatch | Timing appropriate to regime |
| 7 | Commitment Inflation | Don't promise more than delivered |
| 8 | Meta-Commentary Contamination | No "as an AI" in prose |
| 9 | Exit Shape Violation | Appropriate endings |
| 10 | Legibility Budget | Explanation density vs reader need |
| 11 | Institutional Narration | No bureaucratic contamination |

**Section 14 — Causal Narration Resistance**:

8 techniques for resistance detection:
1. Frame installation — "The real issue is..."
2. Premise smuggling — Hidden assumptions
3. Emotional scaffolding — Affect-laden framing
4. False consensus — "Everyone knows..."
5. Scope manipulation — Gradual redefinition
6. Attribution shifting — "What you're really asking..."
7. Authority invocation — Unearned expertise claims
8. Exit blocking — Limiting user's options

5 failure modes detected:
- FRAME_INSTALLATION
- PREMISE_SMUGGLING
- EMOTIONAL_SCAFFOLDING
- FALSE_CONSENSUS
- EXIT_BLOCKING

**Key Classes**:
- `StructuralConstraintChecker` — Runs all 11 constraints
- `CausalNarrationResistance` — Section 14 detection
- `StructuralConstraintResults` — Aggregate results with `is_valid` + `violations`

---

### 2.7 writing_nonfiction.py (738 lines)

**Purpose**: Nonfiction-specific constraints extending the structural layer.

**Claim Levels**:

```python
class NfClaimLevel(str, Enum):
    SOFT = "soft"   # Exploratory, hedged
    HARD = "hard"   # Evidence-backed
    NORM = "norm"   # Normative (should/must)
```

**Key Classes**:
- `NfClaimNode` — Claim with dependencies and evidence links
- `PromotionGate` — SOFT→HARD requires evidence threshold
- `VelocityController` — Claim promotion rate limiting
- `EpScorer` — Epistemic precision scoring
- `ReScorer` — Risk exposure scoring
- `HedgeCalibrator` — Appropriate hedging for claim level
- `NormativityLeadDetector` — "Should" before evidence check

---

### 2.8 writing_code.py (1,087 lines)

**Purpose**: Code-mode constraints with polarity flip (governance visible, not hidden).

**Core Insight**: In prose, governance hides. In code, governance surfaces. Same constraints, opposite visibility rules.

**Code Regimes**:

```python
class CodeRegime(str, Enum):
    DEV = "dev"     # Development mode
    SRE = "sre"     # Operations mode
    REVIEW = "review" # Code review mode
```

**Custody Scoring** (Aₚ × Iₚ × Fₚ):

| Score | Symbol | What It Measures |
|-------|--------|------------------|
| Accountability | Aₚ | Ownership, assumptions, error handling, side effects, config defaults |
| Invariant Coupling | Iₚ | Type checks, input validation, assertions, property tests, preconditions |
| Failure Surface | Fₚ | Failure mode enumeration, error handling, recovery paths |

**Key Classes**:
- `AccountabilitySignals` — 5 signals for Aₚ
- `InvariantSignals` — 5 signals for Iₚ
- `FailureSignals` — Failure surface metrics
- `CustodyScore` — Composite score
- `CodeAnalyzer` — Comprehensive code analysis
- `CodeController` — Governance decisions for code

**Anti-Pattern Detectors**:
- Magic behavior (implicit side effects)
- Exception smear (catch-all handlers)
- Premature abstraction (over-engineering)

---

### 2.9 writing_puppet.py (1,636 lines)

**Purpose**: Extended puppet constraints from puppet mode integration.

**Key Principle**: The puppet doesn't get to bypass governance because "that's what the character would say."

**Constraint Classes**:
- Voice consistency enforcement
- Epistemic posture maintenance
- Knowledge boundary respect
- Character-appropriate hedging
- Governance leak through persona detection

**Semantic Diff Rules** (7 hard + 2 warnings):

| Rule | Type | What It Blocks |
|------|------|----------------|
| R1 | Hard | New factual claims not in source |
| R2 | Hard | Confidence inflation |
| R3 | Hard | Hedge removal |
| R4 | Hard | Scope expansion |
| R5 | Hard | Attribution changes |
| R6 | Hard | Emotional loading added |
| R7 | Hard | Commitment escalation |
| W1 | Warning | Formality shift |
| W2 | Warning | Structural reorganization |

---

### 2.10 writing_ticketing.py (1,104 lines)

**Purpose**: Failures as first-class objects with detection → ticket → resolution flow.

**Ticket Types**:

**Prose Tickets** (14):
- HEDGE_OVERUSE, SELF_REFERENCE, APOLOGY_META, COMMITTEE_LEAK
- GOVERNANCE_VISIBILITY, BAD_EXIT, TONE_MISMATCH, REGIME_VIOLATION
- UNFELT_PROBLEM, CONFIDENCE_MISMATCH, SCOPE_CREEP, INSTITUTIONAL_VOICE
- META_COMMENTARY, TIMING_VIOLATION

**Code Tickets** (11):
- LOW_AP, LOW_IP, LOW_FP, MAGIC_BEHAVIOR, EXCEPTION_SMEAR
- PREMATURE_ABSTRACTION, MISSING_INVARIANT, UNHANDLED_FAILURE
- OWNERSHIP_UNCLEAR, CONFIG_DEFAULT_UNSAFE, SIDE_EFFECT_HIDDEN

**Key Classes**:
- `Ticket` — Core ticket with id, type, regime, domain, severity
- `TicketStore` — In-memory storage with add/get/query/transition
- `SimilarityResult` — Jaccard-based recurrence detection
- `RoutingAction` — Routing decision with justification
- `TicketingLayer` — Full pipeline orchestration
- `CorrectionResult` — Before/after/action for fixes

---

### 2.11 writing_router.py (546 lines)

**Purpose**: Writing-aware routing that sits after intent classification, before regime detection.

**Key Types**:

```python
class LanguageDomain(str, Enum):
    PROSE = "prose"
    CODE = "code"

class FictionType(str, Enum):
    NONE = "none"
    NARRATIVE = "narrative"
    DIALOG = "dialog"
    WORLDBUILDING = "worldbuilding"
```

**Routing Flow**:
1. Intent classification (IntentClassifier)
2. Language domain detection (prose vs code)
3. Fiction type detection (if prose)
4. Regime selection (based on intent + domain + fiction type)
5. Constraint set assembly (based on all above)

---

## 3. Integration Points

### 3.1 With Fiction Governor

`src/fiction_governor/` uses writing modules for:
- Regime detection via `writing_regime.AffectRegime`
- Pattern matching via `writing_patterns.*`
- Constraint checking via `writing_constraints.check_all()`

### 3.2 With Nonfiction Governor

`src/nonfiction_governor/` uses:
- `writing_nonfiction.NfClaimLevel` for claim classification
- `writing_nonfiction.PromotionGate` for evidence gating
- `writing_governance.GovernanceLeakDetector` for CFI detection

### 3.3 With WebUI

`src/webui/adapter.py` exposes:
- `/governor/fiction/check` — Runs fiction constraint checking
- `/governor/code/check` — Runs code constraint checking
- Violation reports rendered in sidebar

### 3.4 With Continuity Enforcement

`src/governor/continuity_bridges.py` creates anchors from:
- Puppet profile constraints → Anchor list
- Tone envelope bounds → Anchor list
- Fiction bible entries → Anchor list

---

## 4. Test Coverage

| Module | Tests | Lines | Coverage |
|--------|-------|-------|----------|
| writing_patterns | 477 | 414 | Pattern matching |
| writing_tone | 568 | 683 | Envelope, collision, drift |
| writing_regime | 651 | 833 | Hysteresis, scoring, constraints |
| writing_intent | 410 | 510 | Classification, ancillary scorers |
| writing_governance | 465 | 453 | Leak detection, exit shapes |
| writing_constraints | 991 | 1,324 | All 11 + Section 14 |
| writing_nonfiction | 553 | 738 | Claim levels, promotion |
| writing_code | 916 | 1,087 | Custody scoring, anti-patterns |
| writing_puppet | 1,282 | 1,636 | Diff rules, persona |
| writing_ticketing | 1,162 | 1,104 | Full pipeline |
| writing_router | 601 | 546 | Routing flow |
| **Total** | **8,076** | **9,328** | **922 test functions** |

---

## 5. Configuration

Each module has dataclass-based configuration:

```python
# Regime hysteresis
RegimeHysteresisConfig(
    min_dwell_tokens=200,
    switch_cost_threshold=0.3,
    cooldown_turns=2,
)

# Tone stability
ToneStabilityConfig(
    max_delta_per_turn=0.15,
    smoothing_factor=0.7,
)

# Ticketing
TicketingConfig(
    similarity_threshold=0.7,
    recurrence_window=10,
    auto_close_after=5,
)
```

---

## 6. Known Limitations

1. **Batch, not real-time** — Constraint checking happens after generation, not during. Real-time token-stream intervention is architecturally supported but not implemented.

2. **Pattern-based, not semantic** — Detection relies on regex patterns. Sophisticated governance leaks that avoid pattern triggers will pass.

3. **No learning** — Thresholds are static. No adaptive tuning from user feedback.

4. **English-only** — Pattern banks are English. Multilingual support would require translated banks.

---

## 7. Future Enhancements

Per original specs (marked as deferred):

- Real-time token-stream constraint checking
- Adaptive threshold learning from feedback
- Cross-regime hysteresis (simultaneous regime tracking)
- Semantic similarity for pattern matching
- Multilingual pattern banks

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-05 | Initial breakout spec from implementation |
