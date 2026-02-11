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

## References

- LessWrong: "Objective Questions" (Jan 2026)
- LessWrong: "Policy discussions follow strong contextualizing norms"
- LessWrong: "Setting the Zero Point"
- Wikipedia: Sealioning
- Governor 2.x gate infrastructure

---

*"Don't become a stage prop. Change the protocol."*
