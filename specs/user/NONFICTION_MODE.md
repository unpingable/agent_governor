# Nonfiction Mode User Guide

## For Writers and Researchers Who Need AI That Cites Its Sources

---

## What This Does (30 Seconds)

You're using AI for research, writing, or analysis. The AI:
- Makes confident claims with no sources
- Mixes facts with speculation seamlessly
- Contradicts itself between sessions
- Can't tell you where it got something
- Invents plausible-sounding citations

**Nonfiction Mode fixes this.**

You establish standards for evidence. The governor holds the AI to them. When it makes claims without proper support, it gets flagged or blocked.

**Claims need evidence. Sources need citations. Speculation needs labels.**

---

## Quick Start (5 Minutes)

### 1. Initialize

```bash
cd your-project
governor nonfiction init
```

### 2. Set Your Evidence Standards

```bash
# Require citations for factual claims
governor nonfiction standard add "Factual claims need citations"

# Distinguish certainty levels
governor nonfiction standard add "Speculation must be marked as such"

# Require primary sources for key claims
governor nonfiction standard add "Statistics need primary sources, not secondary"
```

### 3. Work Normally

Use your AI for research and writing. When it makes an unsupported claim, you'll see:

```
⚠️ This claim needs support

  "Studies show that 73% of developers prefer..."
  
  What's missing:
  • No citation provided
  • No study named
  • Specific statistic needs source
  
  [Add Citation] [Mark as Estimate] [Remove Claim]
```

### 4. Resolve and Continue

- **Add Citation** → Provide the source, claim is accepted
- **Mark as Estimate** → Claim is labeled as approximate/uncertain
- **Remove Claim** → Take it out

Your writing stays grounded.

---

## Core Concepts

### Claims

A claim is any assertion of fact. Nonfiction mode tracks them.

**Types of claims:**

| Type | Example | Evidence Needed |
|------|---------|-----------------|
| Factual | "The population is 8 million" | Citation |
| Statistical | "73% of users prefer..." | Study/survey citation |
| Historical | "The company was founded in 1987" | Verifiable record |
| Causal | "This caused that" | Evidence + reasoning |
| Expert opinion | "Researchers believe..." | Named expert + context |

### Evidence Levels

Not all evidence is equal:

| Level | What It Means | Example |
|-------|---------------|---------|
| **Primary** | Original source | The actual study, official records |
| **Secondary** | Reports on primary | News article citing the study |
| **Tertiary** | Aggregates secondary | Wikipedia, textbooks |
| **Hearsay** | Unattributed | "People say...", "It's known that..." |

You can set minimum evidence levels:

```bash
# Statistics need primary sources
governor nonfiction require primary --for statistics

# Historical claims need at least secondary
governor nonfiction require secondary --for historical
```

### Certainty Levels

How confident is this claim?

| Level | Language | Usage |
|-------|----------|-------|
| **Certain** | "X is Y" | Only with strong evidence |
| **Probable** | "X is likely Y" | Good evidence, some uncertainty |
| **Possible** | "X may be Y" | Limited evidence |
| **Speculative** | "X could be Y" | Hypothesis, reasoning |
| **Unknown** | "It's unclear whether..." | Acknowledging ignorance |

The governor catches certainty/evidence mismatches:

```
⚠️ Certainty doesn't match evidence

  Claim: "This definitely causes cancer"
  Evidence level: One correlational study
  
  Suggestion: Soften to "may be associated with" or add more evidence
```

### Provenance

Where did this information come from?

The governor tracks provenance:
- **Observed**: You verified it yourself
- **Retrieved**: From a cited source
- **Derived**: Reasoned from other claims
- **AI-generated**: The model produced it
- **Assumed**: Unstated assumption

Higher provenance = more trust. AI-generated claims need verification.

---

## Setting Up Your Project

### For Academic Writing

```bash
governor nonfiction init --preset academic

# This sets:
# - All factual claims need citations
# - Statistics need primary sources
# - Speculation must be explicitly marked
# - Claims tracked with full provenance
```

### For Journalism

```bash
governor nonfiction init --preset journalism

# This sets:
# - Named sources for quotes
# - Multiple sources for controversial claims
# - Clear attribution
# - Fact-check flags for unverified claims
```

### For Research Notes

```bash
governor nonfiction init --preset research

# This sets:
# - Source tracking for all notes
# - Hypothesis vs finding distinction
# - Evidence quality ratings
# - Provenance chain
```

### For Blog/Content Writing

```bash
governor nonfiction init --preset content

# This sets:
# - Key claims need support
# - Statistics need sources
# - Opinions clearly marked
# - Lighter touch than academic
```

### Custom Standards

```bash
# Add your own standards
governor nonfiction standard add "Quotes need page numbers"
governor nonfiction standard add "All statistics rounded to appropriate precision"
governor nonfiction standard add "Competing viewpoints must be represented"
```

---

## Daily Workflow

### Starting a Research Session

```bash
governor nonfiction status

# Shows:
# - Active standards
# - Unresolved claims
# - Evidence gaps
# - Source count
```

### Adding Sources

```bash
# Add a source you'll reference
governor nonfiction source add \
  --title "The Structure of Scientific Revolutions" \
  --author "Thomas Kuhn" \
  --year 1962 \
  --type book

# Add a web source
governor nonfiction source add \
  --url "https://example.com/study" \
  --title "Study on Developer Preferences" \
  --accessed "2024-01-15" \
  --type article
```

### Checking Your Writing

```bash
# Check a document
governor check draft.md

# Output:
# ✓ 12 claims found
# ⚠ 3 claims need attention
#   - Line 45: Statistic without source
#   - Line 67: Causal claim with weak evidence  
#   - Line 89: Certainty/evidence mismatch
```

### Resolving Issues

When a claim is flagged:

```
⚠️ This statistic needs a source

  "87% of companies now use cloud services"
  
  [Add Citation] [Mark as Estimate] [Soften Claim] [Remove]
```

**Add Citation:**
```bash
governor nonfiction cite \
  --claim "87% of companies use cloud" \
  --source "Gartner Cloud Report 2023" \
  --page 14
```

**Mark as Estimate:**
```bash
governor nonfiction mark-uncertain \
  --claim "87% of companies use cloud" \
  --note "Approximate figure, varies by definition of 'cloud services'"
```

**Soften Claim:**
```bash
# Change "87% of companies" to "A large majority of companies"
governor nonfiction soften --claim "..."
```

### Tracking Provenance

```bash
# See where a claim came from
governor nonfiction provenance "cloud adoption statistic"

# Output:
# Claim: "87% of companies use cloud services"
# Source: Gartner Cloud Report 2023, p.14
# Added: Jan 15, 2024
# Verified: No (secondary source)
# Related claims: 2 claims depend on this
```

---

## Evidence Quality Checks

### Running a Quality Audit

```bash
governor nonfiction audit draft.md

# Output:
# Evidence Quality Report
# ────────────────────────────────────────
# Total claims: 47
# 
# By evidence level:
#   Primary source:    12 (26%)
#   Secondary source:  23 (49%)
#   Tertiary source:    5 (11%)
#   Unsupported:        7 (15%)
#
# By certainty match:
#   Appropriate:       38 (81%)
#   Overclaimed:        6 (13%)
#   Underclaimed:       3 (6%)
#
# Recommendations:
#   - 7 claims need sources
#   - 6 claims should soften language
#   - Consider primary sources for key statistics
```

### Setting Thresholds

```bash
# Require at least 50% primary sources
governor nonfiction threshold primary 50%

# Max 10% unsupported claims
governor nonfiction threshold unsupported 10%

# Block if thresholds not met
governor nonfiction threshold --enforce
```

---

## Handling AI-Generated Content

### The Problem

AI generates plausible-sounding claims. Some are true. Some aren't. You can't tell which without checking.

### The Solution

All AI-generated claims start as "unverified":

```
AI wrote: "The company was founded in 1987 by John Smith"

⚠️ AI-generated claim — needs verification

  [Verify] [Mark Uncertain] [Remove]
```

**Verify** — You check and confirm:
```bash
governor nonfiction verify \
  --claim "founded in 1987" \
  --evidence "Company website, SEC filings" \
  --verified-by "manual check"
```

**Mark Uncertain** — You're not sure but want to keep it:
```bash
governor nonfiction mark-uncertain \
  --claim "founded in 1987" \
  --note "AI-generated, not independently verified"
```

### Bulk Verification

After an AI-assisted writing session:

```bash
governor nonfiction unverified

# Output:
# 12 unverified claims:
#   1. "Company founded in 1987" (historical)
#   2. "Revenue of $50M" (statistical)
#   3. "Market leader in..." (comparative)
#   ...

# Mark multiple as verified
governor nonfiction verify --range 1,3,5 \
  --evidence "Annual report 2023"
```

---

## Citation Management

### Adding Citations Inline

```bash
# Quick citation while writing
governor nonfiction cite-quick "population 8 million" \
  --source "Census 2020"
```

### Generating Bibliography

```bash
governor nonfiction bibliography --format apa > references.md
governor nonfiction bibliography --format chicago > refs.md
governor nonfiction bibliography --format mla > works-cited.md
```

### Checking Citation Completeness

```bash
governor nonfiction citations check

# Output:
# ✓ All in-text citations have bibliography entries
# ⚠ 2 sources in bibliography not cited in text
# ✗ 1 citation format error (missing year)
```

### Importing Sources

```bash
# From BibTeX
governor nonfiction sources import refs.bib

# From Zotero export
governor nonfiction sources import zotero-export.json

# From URL (extracts metadata)
governor nonfiction sources import --url "https://doi.org/10.1234/example"
```

---

## Collaboration

### Shared Standards

Your evidence standards live in `.governor/` and can be version-controlled:

```bash
git add .governor/
git commit -m "Add nonfiction standards"
```

Now collaborators share the same standards.

### Review Mode

For editors/reviewers:

```bash
governor nonfiction review draft.md

# Output:
# Evidence Review
# ────────────────────────────────────────
# Flagged for reviewer:
#   Line 23: Strong causal claim, single study
#   Line 67: Statistic from 2018, may be outdated
#   Line 89: "Experts agree" — which experts?
#   Line 112: Contradicts claim on line 45
```

### Contradiction Detection

The governor catches when you contradict yourself:

```
⚠️ This contradicts something you wrote earlier

  Here (line 89): "The market grew 15% in 2023"
  Earlier (line 23): "The market declined in 2023"
  
  [Fix This] [Fix Earlier] [Keep Both with Note]
```

---

## WebUI Integration

If you use the WebUI for writing:

### Nonfiction Panel

```
┌─────────────────────────────────────────────────────┐
│  📝 Nonfiction Mode                                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  📊 Evidence Quality                                │
│  ┌─────────────────────────────────────────────┐   │
│  │ ████████████░░░░ 75% supported             │   │
│  │ Primary: 12  Secondary: 23  Unsupported: 7 │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ⚠️ Needs Attention (3)                            │
│  • Statistic without source (line 45)              │
│  • Overclaimed certainty (line 67)                 │
│  • AI claim unverified (line 89)                   │
│                                                     │
│  📚 Sources (15)                                    │
│  • Kuhn 1962                                        │
│  • Gartner 2023                                     │
│  • Census 2020                                      │
│  [+ Add Source]                                     │
│                                                     │
│  📋 Standards                                       │
│  • Statistics need sources ✓                       │
│  • Speculation marked ✓                            │
│  [Edit Standards]                                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Inline Flags

While writing, issues appear inline:

```
The market grew by 15%⚠️ in the last quarter, making it one of the 
strongest periods on record.

    ⚠️ Statistic needs source
    [Add Citation] [Mark Estimate] [Remove]
```

---

## VS Code Integration

### Gutter Indicators

```
  1 │   The study found significant results.
  2 │ ● According to Smith (2023), the effect size was 0.4.
  3 │ ⚠ This proves that the intervention works.
  4 │   Further research is needed.
```

- **●** — Properly cited claim
- **⚠** — Issue (unsupported, overclaimed, etc.)

### Hover Information

```
┌────────────────────────────────────────────────────┐
│ ⚠️ Overclaimed certainty                           │
│                                                    │
│ "This proves that..." suggests certainty           │
│ Evidence: Single study with p=0.04                 │
│                                                    │
│ Suggestion: "This suggests..." or "Evidence        │
│ indicates..."                                      │
│                                                    │
│ [Soften Claim] [Add More Evidence] [Keep]          │
└────────────────────────────────────────────────────┘
```

---

## Philosophy

### Why Track Evidence?

AI is fluent. Fluency creates false confidence.

A claim that sounds authoritative ("Research shows...") triggers less scrutiny than one that sounds uncertain ("One study suggested..."). But the uncertain-sounding claim might have better evidence.

Nonfiction mode separates **how it sounds** from **how supported it is**.

### The Certainty Trap

Writers (and AIs) tend to:
- Overclaim when evidence is weak
- Use hedge words inconsistently
- Treat plausibility as evidence
- Confuse correlation with causation

The governor catches these patterns and asks: **Does your confidence match your evidence?**

### Provenance Matters

"Where did this come from?" is the fundamental question.

- A fact from a primary source: trustworthy
- A fact from Wikipedia: verify it
- A fact from the AI with no source: suspect

Tracking provenance isn't bureaucracy. It's how you know what you actually know.

---

## Command Reference

```bash
# Status
governor nonfiction status         # Current state
governor nonfiction unverified     # List unverified claims
governor nonfiction audit <file>   # Evidence quality report

# Standards
governor nonfiction standard add "..." # Add standard
governor nonfiction standard list      # List standards
governor nonfiction standard remove    # Remove standard
governor nonfiction threshold <type> <percent> # Set threshold

# Sources
governor nonfiction source add     # Add source
governor nonfiction source list    # List sources
governor nonfiction sources import # Import from file

# Claims
governor nonfiction cite           # Add citation to claim
governor nonfiction verify         # Mark as verified
governor nonfiction mark-uncertain # Mark as uncertain
governor nonfiction soften         # Soften language

# Citations
governor nonfiction citations check    # Check citation completeness
governor nonfiction bibliography       # Generate bibliography

# Resolution
governor resolve                   # Interactive resolution
governor resolve cite              # Add citation
governor resolve soften            # Soften claim
governor resolve remove            # Remove claim
```

---

*"Claims need evidence. Sources need citations. Speculation needs labels."*

*"Does your confidence match your evidence?"*

*"Tracking provenance isn't bureaucracy. It's how you know what you actually know."*
