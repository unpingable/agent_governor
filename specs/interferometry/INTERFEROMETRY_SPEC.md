# Interferometry Specification

## Version 0.1 — Divergence as Instrumentation

### Companion to: All mode specs, Autopilot, Maude

---

## Executive Summary

You've been doing this manually: running the same question through multiple models and using agreement/divergence as signal.

This spec turns that into repeatable instrumentation.

**Interferometry is not "pick the smartest model."**

It's: run multiple generators, extract claims, diff at the claim layer, and feed agreement/divergence into the governor as a signal family.

**What you get that you don't get from one model:**
- Divergence detects hidden assumptions, ambiguity, and hallucination
- Consensus is a weak form of evidence (not truth, but robustness)
- You can separate reasoning quality from knowledge coverage
- Autopilot gets something to tune against that isn't vibes

---

## 1. The Core Insight

Without interferometry, a single model's fluent answer can stabilize your thinking prematurely.

With it, the governor can say:

> "This paragraph is solidifying a claim that only one model made, with no support."

That prevents fluency from impersonating truth.

---

## 2. When to Use It

### Use interferometry when the evaluation function is human judgment.

### Don't bother when the evaluation function is a compiler.

| Mode | Interferometry Value | Why |
|------|---------------------|-----|
| **Research** | High | No oracle. Human judgment is the evaluator. Multi-model disagreement is the best error detector you have. |
| **Nonfiction** | High | Same reasoning. Claims need evidence. Divergence flags where evidence is weak. |
| **Fiction** | Medium | Useful for canon violation detection and timeline inconsistencies. Otherwise creative variance is noise. |
| **Code** | Low | You already have a godlike arbiter: tests/types/build. Interferometry is marginal when an oracle exists. |

### Code: When It Does Help

- **Idea diversity**: Different models propose different approaches when you're stuck
- **Second opinion on risky changes**: Security footguns, edge cases
- **Diff selection when tests are slow/weak**: Consensus as weak proxy for sanity
- **Failed attempt fallback**: "Show me alternatives"

But these are narrow cases, not the default pipeline.

---

## 3. Architecture

### 3.1 The Flow

```
Prompt
  │
  ├──→ Model A (Claude)        ──→ Output A
  ├──→ Model B (Local Ollama)  ──→ Output B
  └──→ Model C (GPT via API)   ──→ Output C
         │
         ▼
┌─────────────────────────────────────┐
│        CLAIM EXTRACTION             │
│                                     │
│  Extract from each output:          │
│  • Claims (assertions of fact)      │
│  • Specifics (dates, numbers, names)│
│  • Uncertainties (hedges, unknowns) │
│  • Assumptions (unstated premises)  │
│  • Scope markers ("in the US", etc) │
│  • Refusals (what it won't answer)  │
│                                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        CLAIM-LAYER DIFF             │
│                                     │
│  • Shared claims (≥2 models agree)  │
│  • Unique claims (only 1 model)     │
│  • Conflicting specifics            │
│  • Uncertainty divergence           │
│  • Refusal asymmetry                │
│                                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        GOVERNOR SIGNALS             │
│                                     │
│  Feed into autopilot as telemetry:  │
│  • disagreement_rate                │
│  • specifics_conflict               │
│  • uncertainty_divergence           │
│  • refusal_asymmetry                │
│  • hallucination_suspect            │
│                                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        TRIAGE + OUTPUT              │
│                                     │
│  • Agreement core (merged draft)    │
│  • Disagreement report (deltas)     │
│  • Autopilot actions (raise/lower   │
│    friction based on signals)       │
│                                     │
└─────────────────────────────────────┘
```

### 3.2 Important: Diff at the Claim Layer, Not the Prose Layer

Comparing raw text is mostly noise (stylistic differences).

Comparing extracted claims is signal (substantive differences).

Even a crude claim extractor ("sentences with verbs like is/are/causes/leads") is enough to spot divergences that matter.

---

## 4. Signal Family

### 4.1 New Signals

| Signal | What It Measures | High Value Means |
|--------|-----------------|------------------|
| `disagreement_rate` | % of extracted claims not shared across models | Prompt is ambiguous or domain is unstable |
| `specifics_conflict` | Numbers, dates, entities differ across models | Hallucination likely, or data is genuinely contested |
| `uncertainty_divergence` | One model asserts, another hedges | Confidence isn't warranted |
| `refusal_asymmetry` | One refuses, others answer | Safety/policy boundary, not truth boundary |
| `hallucination_suspect` | Claim appears in only one model with high specificity | Model is inventing details |

### 4.2 These Are Telemetry, Not Truth

High disagreement doesn't mean "all models are wrong."

It means: **this needs more scrutiny than a single confident answer would suggest.**

---

## 5. Autopilot Integration

### 5.1 When Models Agree

Autopilot lowers friction:

- Auto-register shared claims (still floating until supported)
- Propose merged draft from the intersection
- Suppress redundant warnings
- Speed up without lying

### 5.2 When Models Disagree

Autopilot raises friction selectively:

- Hold outlier claims as "contested by model variance"
- Prompt for scope/assumption clarification
- Force uncertainty preservation (don't let one confident model "settle it")
- Don't pick a winner — force legibility

### 5.3 When a Single Model Produces Spicy Specifics

Autopilot marks it immediately:

> "Unique high-specificity claim (only in Ollama output, contains date/amount). Require citation or downgrade to hypothesis."

Teeth without pretending to know truth.

### 5.4 Autopilot Policies by Mode

**Research mode: Intersection-first**
- Default draft = intersection of claims shared by ≥2 models
- Outliers become floating claims tagged `origin=model_X` + `status=needs_support`
- Any conflict in specifics triggers scope check before letting prose harden

**Nonfiction mode: Evidence-gated**
- Multi-model agreement is weak evidence (better than single model, worse than citation)
- Disagreement triggers "needs source" flag
- Provenance tracking includes which models supported the claim

**Fiction mode: Canon-first**
- If canon rules exist: enforce "no violations" across all models
- Interferometry used mainly for continuity drift and timeline conflicts
- Otherwise, treat divergence as creative variance and keep autopilot in observer-only

**Code mode: Oracle-first**
- Run multiple models → generate candidate diffs
- Autopilot selects by test/type oracle, not agreement
- Disagreement just means "more candidate patches," not epistemic conflict

---

## 6. Autotune

### 6.1 What It Learns

Because you can log outcomes:

| Pattern | What Autopilot Learns |
|---------|-----------------------|
| You usually accept Claude's framing but reject its specifics | Trust Claude structure, verify Claude facts |
| You trust local model's bluntness but it invents numbers | Use Ollama for framing, don't trust its data |
| You override refusals with other model outputs | Refusal asymmetry = "try another model" |
| You accept intersection claims without checking | Shared claims are safe to auto-register |
| You always reject high-specificity unique claims | Flag these aggressively |

### 6.2 What It Adjusts

- How aggressively to demand support on unique claims
- When to escalate to "clarify scope first"
- Which merge strategy you tend to prefer (intersection / best-single / blended)
- Per-model trust profiles (not fixed — learned from your behavior)

This is operator modeling based on behavior, not psychology.

---

## 7. Implementation

### 7.1 Minimal Wedge (Start Here)

Don't build a whole subsystem. Start with:

1. **One command/button**: "Run N models"
2. **Store**: Raw outputs + model + settings
3. **Run a dead-simple extractor**: Sentences with `is/are/causes/leads` → candidate claims. Anything with dates/numbers → specifics.
4. **Produce a diff**: Unique claims per model + conflicting specifics

That's enough to get value without building an epistemic graph on day one.

### 7.2 Next Step

Promote "unique claims" into "floating claims" in the ledger automatically (still marked as model-originated), so the disagreement report becomes actual epistemic debt you can resolve.

### 7.3 Full Integration

```typescript
interface InterferometryRun {
  id: string;
  prompt: string;
  timestamp: string;
  
  models: ModelRun[];
  
  // Extracted
  shared_claims: Claim[];
  unique_claims: Map<string, Claim[]>;  // model_id → claims
  conflicts: Conflict[];
  
  // Signals
  disagreement_rate: number;
  specifics_conflict_count: number;
  uncertainty_divergence: number;
  refusal_asymmetry: boolean;
  hallucination_suspects: Claim[];
  
  // Output
  agreement_core: string;         // merged from shared claims
  disagreement_report: string;    // deltas only
  autopilot_actions: Action[];
}

interface ModelRun {
  model_id: string;
  model_name: string;
  settings: Record<string, any>;
  
  raw_output: string;
  extracted_claims: Claim[];
  extracted_specifics: Specific[];
  uncertainties: string[];
  assumptions: string[];
  refusals: string[];
}

interface Conflict {
  topic: string;
  claims: Map<string, Claim>;  // model_id → their version
  resolution?: string;
}
```

### 7.4 CLI Interface

```bash
# Run interferometry
governor interferometry run "What caused the 2008 financial crisis?" \
  --models claude,ollama,gpt

# View results
governor interferometry results --last

# View disagreement report only
governor interferometry divergence --last

# Promote shared claims to ledger
governor interferometry accept --shared

# Flag unique claims for review
governor interferometry flag --unique
```

### 7.5 WebUI Interface

```
┌─────────────────────────────────────────────────────────────┐
│  🔬 Interferometry                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Models: Claude ✓  Ollama ✓  GPT ✓                         │
│                                                             │
│  Agreement (3/3 models):                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • Financial crisis triggered by subprime mortgages  │   │
│  │ • Lehman Brothers collapse was pivotal moment       │   │
│  │ • Deregulation played a role                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Disagreement:                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ⚠ Claude says CDS market was $62T                   │   │
│  │   GPT says $45T                                     │   │
│  │   Ollama doesn't specify                            │   │
│  │   → Needs citation                                  │   │
│  │                                                     │   │
│  │ ⚠ Only Claude mentions Gramm-Leach-Bliley          │   │
│  │   → Unique claim, may be relevant                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Accept Shared] [Review Divergence] [Rerun]                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Why Three Models

With two models, you only know "disagree."

With three, you can do "majority + outlier analysis," which is far more actionable:

| Scenario | Signal | Action |
|----------|--------|--------|
| 3/3 agree | Robust (not proven, but resilient) | Lower friction, auto-register |
| 2/1 split | Outlier needs inspection | Check the lone claim — hallucination or insight? |
| 1/1/1 split | Prompt is underspecified | Force scope/assumption clarification |

### Model Selection Strategy

| Model | Strength | Weakness | Role |
|-------|----------|----------|------|
| Claude | Structure, careful reasoning | Cautious, sometimes over-refuses | Framework builder |
| Local Ollama | Blunt, less PR-sanitized | Weaker recall, invents numbers | Honesty check |
| GPT | Synthesis, implementation detail | Sometimes smooths over uncertainty | Coverage |

The specific models don't matter as much as having **different failure modes**.

---

## 9. The Punchline

You've been doing interferometry manually — running prompts through multiple models and using your judgment to triangulate.

This spec automates the boring parts:
- Extraction
- Diffing
- Signal generation
- Triage

Your judgment is still the final arbiter. But now it's instrumented, logged, and repeatable.

> **Interferometry doesn't make the system smarter. It makes the system less able to bullshit you by giving you a second and third opinion with structured deltas.**

---

## 10. What This Enables

### 10.1 "Reasoning stabilizes vs degrades over time"

Without interferometry: you can't tell if a claim is stabilizing (real) or calcifying (premature consensus).

With it: if the claim appears in all models consistently across runs, it's stabilizing. If it only appears in one model and keeps changing, it's unstable.

### 10.2 Per-Model Drift Detection

Over time, you can see:
- "Claude got more refusal-y after update X"
- "Local model started inventing dates when context length grew"
- "GPT lost nuance on topic Y after fine-tuning"

That's model evaluation as a side effect of normal usage.

### 10.3 Epistemic Debt Pipeline

Disagreement Report → Floating Claims → Epistemic Debt → Resolution

Multi-model divergence becomes *actual tracked debt* in the ledger, not "hmm, interesting, moving on."

---

## 11. The Simple Rule

**Use interferometry when the evaluation function is human judgment.**

**Don't bother when the evaluation function is a compiler.**

---

## 12. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |

---

*"Interferometry doesn't make the system smarter. It makes the system less able to bullshit you."*

*"Divergence is a detector. Consensus is weak evidence. Neither is truth."*

*"Use interferometry when the evaluation function is human judgment."*
