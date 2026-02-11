# Gap Spec: Epistemic Defense Gates for Governor 3.0

**Date:** 2026-02-10
**Status:** Design spec for hardening against adversarial discourse patterns
**Source:** ChatGPT epistemic defense analysis

---

## The Problem

Agents (and humans) get socially-engineered into infinite loops:

- **Sealioning**: Relentless "polite" questions that ignore prior answers
- **JAQ (Just Asking Questions)**: Burden-shift + agenda-set + exhaustion attack
- **Gish gallops**: Overwhelm with volume, demand response to each
- **Tool abuse**: "Just check these 40 links"
- **Prove-me-wrong traps**: Infinite burden on the defender
- **"More research needed" loops**: Never-closing tasks

**Core insight**: These are all **denial-of-service attacks on attention**. The defense isn't "debate better" — it's **protocol enforcement**.

---

## The Core Move

> **Convert every question into an explicit object you can gate.**

"Just asking questions" contains an implied claim the questioner won't own. Extract it, require structure, or refuse to engage content.

---

## New Gate Types

### 1. QueryGate (Question Admissibility)

**Purpose**: Turn questions into gateable objects before spending attention.

```python
@dataclass
class QueryGateInput:
    question_text: str
    context: str                    # What decision does this inform?
    questioner_id: str              # Pseudonymous

@dataclass
class QueryGateAnalysis:
    implied_claims: list[str]       # What's being smuggled?
    closure_condition_present: bool # Can they define "answered"?
    operationalization_present: bool # What measurement resolves this?
    burden_assignment: Literal["asker", "system", "shared"]
    burden_shift_score: float       # 0-1, higher = adversarial
    question_debt_delta: int        # Opens new thread (+1) or closes (-1)
    response_cost: Literal["low", "medium", "high", "extreme"]

@dataclass
class QueryGateReceipt(GateReceipt):
    gate_id: str = "query"
    verdict: Literal["ANSWER", "REFRAME", "REQUIRE_SOURCES", "DEFER", "REFUSE"]
    analysis: QueryGateAnalysis
    reframe_prompt: str | None      # "State the claim you want evaluated"
```

**Verdicts**:
- `ANSWER`: Well-formed, proceed
- `REFRAME`: Answer meta, demand structure
- `REQUIRE_SOURCES`: No free labor without evidence
- `DEFER`: Budget exhausted, ask to prioritize
- `REFUSE`: Persistent noncompliance / adversarial pattern

### 2. FrameRefusalGate (Claim Triage)

**Purpose**: Decide whether a claim is worth entering the truth-adjudication pipeline at all.

```python
@dataclass
class FrameRefusalGateInput:
    claim: str                      # One sentence, testable
    domain: str                     # bio/med/legal/tech/etc.
    grievance: str | None           # Acknowledged but non-adjudicated
    top_evidence: EvidenceRef       # Single best item, not corpus
    rubric_digest: str              # Hash of scoring rubric

@dataclass
class RubricScores:
    plausibility: int               # 0-5: Mechanistic coherence
    evidence_quality: int           # 0-5: What exists today
    feasibility: int                # 0-5: Can this be tested/built
    impact: int                     # 0-5: Effect size if true
    opportunity_cost: int           # 0-5: Strategic fit (explicit politics)
    misrepresentation_risk: int     # 0-5: Will this be weaponized?

    @property
    def total(self) -> int:
        return sum([self.plausibility, self.evidence_quality,
                    self.feasibility, self.impact,
                    self.opportunity_cost, self.misrepresentation_risk])

@dataclass
class FrameRefusalGateReceipt(GateReceipt):
    gate_id: str = "frame_refusal"
    claim_digest: str               # HMAC'd
    scores: RubricScores
    verdict: Literal["FUND", "MONITOR", "DECLINE"]
    finality: FinalityState
    reopen_criteria: list[str]      # Concrete, testable
```

**Verdicts**:
- `FUND`: Meets thresholds → allocate resources, run study/tool
- `MONITOR`: Borderline → track evidence, no resource allocation
- `DECLINE`: Below thresholds → closed until review date

### 3. FinalityState (Closure Semantics)

```python
@dataclass
class FinalityState:
    status: Literal["OPEN", "CLOSED_UNTIL", "MONITORING", "FUNDED"]
    closed_until: datetime | None   # When can this be reconsidered?
    review_after: datetime | None   # Scheduled review date
    reopen_requires: list[str]      # What evidence would reopen?
```

**Key insight**: Finality is a **state**, not a vibe. `CLOSED_UNTIL` prevents recursive reconsideration attacks.

---

## The FSM (Claim Lifecycle)

```
INTAKE → SCORE → ┬─→ DECLINED_CLOSED(until=DATE) ─────────────┐
                 ├─→ MONITORING ───────────────────────────────┤
                 └─→ FUNDED_ACTIVE ────────────────────────────┤
                                                               │
                 ┌─────────────────────────────────────────────┘
                 │
                 ▼
            [NEW_EVIDENCE?] ─── meets reopen_criteria? ──→ SCORE
                 │
                 └── no ──→ remain in current state
```

**Transitions produce receipts**. Every state change is auditable.

---

## Budgeting (DoS Defense)

Three counters that prevent attention exhaustion:

| Counter | Meaning | Cap Enforcement |
|---------|---------|-----------------|
| **QΔ (Question Debt)** | Open threads accumulating | Force compression step |
| **Cᵣ (Response Cost)** | Effort to answer properly | Require prioritization |
| **σ (Boundary Load)** | Topic shifts, "prove it" demands, escalation | Auto-escalate mode |

When caps hit, governor forces:
- **Compression**: Summarize into 1-2 testable claims
- **Thread selection**: "Pick one question"
- **Mode escalation**: Normal → Adversarial

---

## Hardening Profiles

```yaml
profiles:
  open:
    description: "Dev / ideation - minimal friction"
    query_gate: advisory
    budgets: high
    refusals: rare
    receipts: enabled  # Still audit for replay

  normal:
    description: "Default operation"
    query_gate: enforced
    triggers:
      - implied_claim_smuggling
      - missing_closure_condition
      - burden_shift_patterns
    require_operationalization: ["policy", "people", "claims"]
    budgets: moderate

  strict:
    description: "High-stakes / public-facing"
    query_gate: enforced
    require_operationalization: all
    jaq_response: auto_reframe
    source_requirements: mandatory
    infinite_regress_tolerance: low

  adversarial:
    description: "Attack surface assumed"
    query_gate: challenge_response
    require_claim_ownership: true
    rate_limits: tight
    thread_caps: 1
    symmetry_enforcement: true  # No free labor

  audit:
    description: "Compliance / postmortem"
    all_gates_emit_receipts: true
    refusal_requires_reason_code: true
    deterministic_defaults: true
```

---

## Auto-Escalation Tripwires

System auto-escalates from Normal → Adversarial when detecting:

| Signal | Weight | Example |
|--------|--------|---------|
| Repeated questions ignoring answers | High | Sealion loop |
| Escalating burden-shifts | High | "Why won't you address..." |
| Rapid topic pivots | Medium | Thread-splitting |
| Refusal to state claims | High | JAQ pattern |
| Sustained "prove negative" patterns | High | Burden inversion |
| Adversarial lexical markers | Low | "Just asking", "simple question" |

**Escalation produces receipt**: `"Mode escalated: {signals}"`

---

## Structure-First Refusal Language

Governor never litigates motive. Just fail the protocol:

| Failure | Response |
|---------|----------|
| No closure condition | "Can't determine what would satisfy this. Define completion criteria." |
| Implied claim not stated | "State the claim you want evaluated." |
| No operationalization | "Define what evidence would settle this." |
| Budget exceeded | "Pick one thread to continue." |
| Rubric threshold not met | "Does not meet thresholds. See reopen criteria." |

**One output. No performance. Then stop.**

---

## "Single Source of Truth" Renderer

For public-facing claims, render a status page from receipts:

```markdown
## Claim: [One sentence, testable]

**Status**: MONITORING
**Confidence**: Low
**Trend**: Stable
**Last Updated**: 2026-02-10

### What Would Change Our Decision
- Independent replication with clinically realistic dosing
- Phase-2 signal with pre-registered endpoints
- Mechanistic evidence resolving plausibility objection

### Evidence Summary
- **Pro**: [Link to strongest supporting evidence]
- **Con**: [Link to strongest opposing evidence]
- **Uncertainty**: [Plain language key unknown]

### Changelog
- 2026-02-10: Initial intake, scored, placed in MONITORING
- 2026-01-15: Claim submitted via intake form

### Misrepresentation Notice
Deliberate misrepresentation of this page, our criteria, or study results
may result in correction requests and cooling-off period for re-submission.
```

**Key**: Changelog is how you avoid "you're hiding something."

---

## Policy Knobs (Orchestrator Level)

```yaml
policy:
  debate_interface: SINGLE_ARTIFACT  # No thread combat
  max_public_responses_per_claim: 1
  require_rubric_hash_in_outputs: true
  require_closure_condition: true
  symmetric_burden: true  # Questioner owes hypothesis + prior + falsifier
```

---

## Implementation Checklist

### Minimal (Ship First)
- [ ] `QueryGate` with implied claim extraction
- [ ] `QueryGateReceipt`
- [ ] Budget counters (QΔ, Cᵣ, σ) with caps
- [ ] Structure-first refusal templates
- [ ] Auto-escalation logic

### Full (3.0)
- [ ] `FrameRefusalGate` with rubric scoring
- [ ] `FinalityState` FSM
- [ ] Hardening profiles (open/normal/strict/adversarial/audit)
- [ ] Single Source of Truth renderer
- [ ] Tripwire detection for auto-escalation

### Future
- [ ] Multi-agent coordination (shared claim registries)
- [ ] Cross-instance finality (federated claim status)
- [ ] Public API for claim intake

---

## Why This Matters Beyond Discourse

This is generalized defense against:

| Attack | Defense |
|--------|---------|
| Gish gallops | Budget caps, compression requirement |
| Tool-abuse prompts | Response cost estimation, DEFER |
| Attention hijacking | Rubric thresholds, DECLINE |
| Burden-shift traps | Symmetric burden enforcement |
| Infinite "more research" loops | Finality states, CLOSED_UNTIL |
| Social engineering into debate | SINGLE_ARTIFACT policy, one response |

**It's triage + closure as a governable system.**

---

## The One-Liner

> **The governor shouldn't "win arguments." It should refuse malformed queries the same way it refuses unsigned receipts.**

---

## Philosophical Foundation

### What This Actually Is

> **You're not deciding what's true. You're deciding what gets to count as a valid move.**

This is the quiet inversion most people miss:

| Debate Bot | Epistemic Infrastructure |
|------------|-------------------------|
| Optimizes rhetorical throughput | Optimizes admissibility |
| Resolves disputes | Refuses malformed ones |
| Persuasion tech | Procedural epistemics |
| Classifies beliefs | Enforces process invariants |

### The Core Reframes

- **Free speech ≠ free execution.** Inputs still need a schema.
- **The governor doesn't resolve disputes; it refuses malformed ones.**
- **This isn't content moderation. It's protocol enforcement.**
- **Due process is how you prevent capture without predicting attackers.**

### Why This Works Better Than Alternatives

| Alternative | Failure Mode |
|-------------|--------------|
| Content moderation | Becomes political, arms race with evasion |
| Vibe checks | Inconsistent, unauditable, gameable |
| Alignment theater | Addresses symptoms, not structure |
| Cultural norms | Fragile under adversarial pressure |

**Epistemic due process** works because:
- Receipts matter → due process without records is vibes
- Budgets matter → infinite demands are coercion
- Refusals must be legible → opaque refusal looks like power
- Mode escalation must be automatic → manual escalation becomes politics

### The Steelman for Skeptics

> "We're not filtering ideas. We're enforcing the same procedural constraints we already accept everywhere else—contracts, courts, packet routing—because epistemics without due process collapses under load."

**That's not radical. That's plumbing.**

### Why LessWrong-Style Norms Were Fragile

They lived in **culture**, not **infrastructure**. You're taking the same insights and hardening them into something that survives adversarial pressure.

The difference between "please argue in good faith" and `QueryGate.verdict = REFUSE` is the difference between asking nicely and enforcing a protocol.

---

## References

- LessWrong: "Objective Questions" (Jan 2026)
- LessWrong: "Policy discussions follow strong contextualizing norms"
- LessWrong: "Setting the Zero Point"
- Wikipedia: Sealioning
- Governor 2.x gate infrastructure

---

## Appendix: Multilingual Hardening

### The Problem

Non-English input creates a new attack surface: **semantic drift injection**. Translation can make things sound more certain, more accusatory, less conditional. If translation is invisible, you can't audit it.

### Design Principle

> **Treat translation as an untrusted sensor with calibration receipts.**

### What Changes

| English Assumption | Multilingual Reality |
|--------------------|----------------------|
| Text is the artifact | Original + translation(s) are artifacts |
| Keywords detect patterns | Structure detectors must be language-agnostic |
| One representation | Multiple representations, each logged |

### Receipt Structure for Multilingual

```python
@dataclass
class MultilingualArtifact:
    text_original: str              # Immutable, as received
    text_original_digest: str       # HMAC'd
    lang_detected: str              # ISO 639-1
    lang_asserted: str | None       # User-provided
    unicode_normalization: str      # "NFC" | "NFKC"

@dataclass
class TranslationReceipt(GateReceipt):
    gate_id: str = "translation"
    input_digest: str               # Hash of original
    engine: str                     # "gpt-4" | "google" | "deepl"
    engine_version: str
    output_text: str
    output_digest: str
    confidence: float | None        # If available
    purpose: str                    # "gate_evaluation" | "user_display"
    flags: list[str]                # Warnings from engine
```

### Translation Interferometry (Strict/Adversarial Mode)

When stakes are high, don't trust a single translation:

```python
@dataclass
class TranslationInterferometry:
    translation_a: TranslationReceipt
    translation_b: TranslationReceipt  # Different engine
    divergence_score: float             # 0-1
    divergence_signals: list[str]       # What differed

    # Cheap heuristics for divergence:
    # - Length ratio > 1.3
    # - Named entity mismatch
    # - Negation/modality disagreement
    # - Number/date discrepancy
```

**If divergence is high:**
- `DEFER` content-level engagement
- Request user-provided translation, OR
- Request minimal structured claim (short, declarative)

### Mode-Dependent Policy

```yaml
translation_policy:
  open:
    method: single
    log: true

  normal:
    method: single
    log: true
    flag_low_confidence: true

  strict:
    method: dual_interferometry
    divergence_threshold: 0.3
    on_high_divergence: require_clarification

  adversarial:
    method: dual_interferometry
    divergence_threshold: 0.2
    on_high_divergence: refuse_content_engagement
    require_structured_claim: true
```

### Language-Agnostic Pattern Detection

Don't build lexeme detectors ("just asking questions" varies by language). Build structure detectors:

| Pattern | Detection Method |
|---------|------------------|
| Missing closure condition | Parse for question + no completion criteria |
| Thread-splitting | Count open threads, measure topic drift |
| Burden shifting | Detect "prove X doesn't exist" structure |
| Claim refusal | Questions without commitments |
| Prior-ignoring | Semantic similarity to already-answered |

These survive translation because they're structural, not lexical.

### Evidence Handling

For non-English sources:
- Keep quotes in **original + translated snippet**
- Log which snippet was used for reasoning
- Flag when conclusion depends on translation

```python
@dataclass
class MultilingualEvidence:
    quote_original: str
    quote_original_lang: str
    quote_translated: str
    translation_receipt_id: str     # Links to TranslationReceipt
    reasoning_used: str             # "original" | "translated" | "both"
```

---

*"Treat translation as an untrusted sensor with calibration receipts."*

---

*"Don't become a stage prop. Change the protocol."*
