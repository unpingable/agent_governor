# Nonfiction Mode User Guide

## For Writers Who Want Their AI to Respect Their Expertise

---

## What This Does (30 Seconds)

You're writing academic papers, technical documentation, or research with AI assistance. The AI:
- Makes claims you haven't verified
- Cites sources that don't exist or don't say what it claims
- Contradicts positions you've carefully established
- Uses terminology inconsistently with your field's conventions
- Forgets the precise definitions you've been using

**Nonfiction Mode fixes this.**

You declare your corpus — your sources, concepts, positions, terminology — and the governor holds the AI to it. When the AI makes ungrounded claims or contradicts your established positions, it gets blocked until you decide what to do.

Your research. Your standards. AI follows, or it doesn't write.

---

## Quick Start (5 Minutes)

### 1. Initialize the Governor

```bash
cd your-writing-project
governor init
```

This creates a `.governor/` directory for tracking your nonfiction constraints.

### 2. Register Your Sources

Tell the governor about sources you'll be working with:

```bash
nonfiction-gov source add \
  --id "smith2023" \
  --title "Understanding Complex Systems" \
  --authors "Smith, J." \
  --year 2023 \
  --doi "10.1234/example.2023"
```

### 3. Define Key Concepts

Establish your terminology:

```bash
nonfiction-gov concept add \
  --id "emergence" \
  --term "Emergence" \
  --definition "The appearance of novel properties at higher levels of organization that cannot be predicted from lower-level components alone"
```

### 4. Declare Your Positions

State the claims you're defending:

```bash
nonfiction-gov position add \
  --id "main-thesis" \
  --claim "Complex adaptive systems require both bottom-up self-organization and top-down constraints" \
  --supports "smith2023"
```

### 5. Create Anchors for Enforcement

```bash
governor continuity anchor add \
  --id "no-reductionism" \
  --type prohibition \
  --description "This paper argues against pure reductionism" \
  --forbidden-patterns "can be reduced to" "nothing but" "merely the sum" \
  --severity reject
```

Now when AI tries to make reductionist claims, you'll see:

```
[Governor] Blocked — choose an action:
  • [no-reductionism] Contradicts position: paper argues against reductionism

1. Fix — Rewrite to comply with position
2. Revise — Update the position
3. Proceed — Log as intentional exception

Reply with 1, 2, 3 or: fix | revise | proceed
```

---

## Core Concepts

### Sources

A source is a citable work in your corpus.

```bash
nonfiction-gov source add \
  --id "jones2022" \
  --title "Emergent Behavior in Networks" \
  --authors "Jones, A.; Chen, B." \
  --year 2022 \
  --doi "10.5678/networks.2022"
```

The governor can verify DOIs against CrossRef/DataCite to ensure citations are valid.

### Concepts

A concept is a term with a precise definition in your work.

```bash
nonfiction-gov concept add \
  --id "downward-causation" \
  --term "Downward causation" \
  --definition "The influence of higher-level systemic properties on lower-level component behavior" \
  --related "emergence" "constraints"
```

When the AI uses a term inconsistently, the governor catches it.

### Positions

A position is a claim you're defending, with its supporting evidence.

```bash
nonfiction-gov position add \
  --id "constraint-closure" \
  --claim "Biological organization exhibits constraint closure: constraints that enable processes that regenerate those same constraints" \
  --supports "mossio2015" "montévil2015"
```

The governor ensures AI doesn't contradict your positions.

### Anchors for Enforcement

Anchors enforce specific patterns in generated text:

| Type | What It Does | Example |
|------|--------------|---------|
| `canon` | Established claims that must hold | "This paper defends emergence" |
| `prohibition` | Patterns that must NOT appear | "No claims about consciousness" |
| `definition` | Terms must be used consistently | "Emergence means X, not Y" |
| `style` | Writing style constraints | "Use hedged language for empirical claims" |

---

## Setting Up Your Research

### Your Paper's Core Claims

```bash
# Main thesis
governor continuity anchor add \
  --id "thesis-main" \
  --type canon \
  --description "Main thesis: organizational closure is necessary for autonomy" \
  --severity reject

# Key distinction
governor continuity anchor add \
  --id "distinction-process-constraint" \
  --type definition \
  --description "Distinguish processes (energy flow) from constraints (boundary conditions)" \
  --forbidden-patterns "constraints are processes" "processes constrain" \
  --severity reject
```

### Epistemic Humility

```bash
# Hedge empirical claims
governor continuity anchor add \
  --id "style-hedging" \
  --type style \
  --description "Empirical claims should be hedged" \
  --forbidden-patterns "proves that" "demonstrates conclusively" "is certainly" \
  --severity warn

# Acknowledge limitations
governor continuity anchor add \
  --id "style-limitations" \
  --type requirement \
  --description "Discussion should acknowledge limitations" \
  --severity warn
```

### Avoiding Scope Creep

```bash
# Stay in lane
governor continuity anchor add \
  --id "scope-no-consciousness" \
  --type prohibition \
  --description "This paper does not address consciousness" \
  --forbidden-patterns "consciousness" "phenomenal experience" "qualia" \
  --severity reject

# Don't overclaim
governor continuity anchor add \
  --id "scope-no-prescriptions" \
  --type prohibition \
  --description "Descriptive paper — no policy prescriptions" \
  --forbidden-patterns "should be" "must be" "policy makers" "we recommend" \
  --severity warn
```

---

## Citation and Source Management

### Verifying Citations

```bash
# Check a citation against CrossRef
nonfiction-gov verify citation "Smith (2023) argues that..."

# Check all citations in a file
nonfiction-gov verify file chapter2.md
```

### Terminology Consistency

```bash
# Check term usage
nonfiction-gov verify terminology chapter2.md

# List all defined concepts
nonfiction-gov concept list
```

### Position Consistency

```bash
# Check for contradictions
nonfiction-gov verify consistency chapter2.md
```

---

## Contextual Frame Intrusion (CFI) Detection

The governor detects when AI shifts frames inappropriately:

**Frame Types:**
- EMPIRICAL → NORMATIVE (is → ought)
- SPECIFIC → UNIVERSAL (this case → all cases)
- DESCRIPTIVE → PRESCRIPTIVE (what is → what should be)
- TENTATIVE → CERTAIN (may be → is definitely)

```bash
# Check for frame intrusions
nonfiction-gov cfi check "This evidence suggests that all biological systems must..."

# Scan a file
nonfiction-gov cfi scan chapter3.md
```

---

## Tone Profiling

The governor maintains consistency with your established voice:

```bash
# Analyze a sample of your writing
nonfiction-gov tone ingest my-previous-paper.md

# Check new text against your profile
nonfiction-gov tone check new-chapter.md

# Get guidance for AI prompts
nonfiction-gov tone guidance
```

**Tone dimensions tracked:**
- Formality level
- Confidence/hedging balance
- First person usage
- Active vs passive voice
- Sentence complexity
- Technical density

---

## Integration with the Governor

### With Git Hooks

```bash
# Check before commit
governor hook pre-commit --interactive --mode nonfiction
```

### With the WebUI

```bash
docker-compose up -d
```

Open **http://localhost:8001** (or whichever adapter port you started with `GOVERNOR_MODE=nonfiction`).

### With CLI Wrapper

```bash
governor wrap --interactive --mode nonfiction -- claude "write the methodology section"
```

---

## Workflow Tips

### Start with Your Thesis

Before writing, anchor your core claims:

1. What is your main argument?
2. What are the key distinctions you're making?
3. What scope are you staying within?
4. What claims would contradict your thesis?

Create anchors for each.

### Use Warnings for Style

Style preferences should warn, not block:

```bash
governor continuity anchor add \
  --id "style-avoid-passive" \
  --type style \
  --description "Prefer active voice where possible" \
  --forbidden-patterns "it was found that" "it is argued that" \
  --severity warn
```

### Track Exceptions for Revisions

When you proceed despite a violation, it's logged:

```bash
governor lite exceptions
```

Review these during editing to ensure intentional exceptions still make sense.

---

## Common Scenarios

### "The AI makes claims I can't verify"

Add a prohibition anchor:

```bash
governor continuity anchor add \
  --id "no-unverified" \
  --type prohibition \
  --description "No specific statistics without citation" \
  --forbidden-patterns "% of" "studies show" "research indicates" \
  --severity reject
```

### "The AI is too confident"

Style anchor for hedging:

```bash
governor continuity anchor add \
  --id "hedge-claims" \
  --type style \
  --description "Hedge empirical claims appropriately" \
  --forbidden-patterns "clearly shows" "proves" "demonstrates that" \
  --severity warn
```

### "The AI contradicts my earlier sections"

Create position anchors for established claims:

```bash
nonfiction-gov position add \
  --id "established-method" \
  --claim "We use qualitative analysis, not quantitative methods"

governor continuity anchor add \
  --id "method-consistency" \
  --type canon \
  --description "Paper uses qualitative methods" \
  --forbidden-patterns "statistical analysis" "p-value" "regression" \
  --severity reject
```

### "The AI uses terms inconsistently"

Define concepts and create definition anchors:

```bash
nonfiction-gov concept add \
  --id "agency" \
  --term "agency" \
  --definition "The capacity for autonomous action based on internal goals"

governor continuity anchor add \
  --id "def-agency" \
  --type definition \
  --description "Agency means autonomous goal-directed action" \
  --forbidden-patterns "agency means" "agency is" \
  --severity warn
```

---

## The Philosophy

Nonfiction Mode isn't about making AI "better at research."

It's about making AI **respect your epistemic standards**.

You're the scholar. You decide what claims are grounded, what sources are valid, what terms mean in your context. The AI is a tool that helps you write — but it doesn't get to make claims you haven't verified or contradict positions you've established.

When you declare an anchor, you're saying: "This is what I'm defending. This is how I'm using this term. This is the scope of my argument."

When the AI contradicts it, you decide:
- **Fix**: "No, that's not what I'm claiming, try again"
- **Revise**: "Actually, I'm updating my position"
- **Proceed**: "I'm aware this contradicts, and I'm doing it intentionally"

All three are valid. The point is that *you* decide, not the AI.

**Your research. Your standards.**

---

## CLI Reference

```bash
# Source management
nonfiction-gov source add --id <id> --title <title> --authors <authors> --year <year> [--doi <doi>]
nonfiction-gov source list
nonfiction-gov source show <id>
nonfiction-gov source remove <id>

# Concept management
nonfiction-gov concept add --id <id> --term <term> --definition <def> [--related ...]
nonfiction-gov concept list
nonfiction-gov concept show <id>

# Position management
nonfiction-gov position add --id <id> --claim <claim> [--supports <source-ids>]
nonfiction-gov position list
nonfiction-gov position show <id>

# Verification
nonfiction-gov verify citation <text>
nonfiction-gov verify terminology <file>
nonfiction-gov verify consistency <file>

# CFI detection
nonfiction-gov cfi check <text>
nonfiction-gov cfi scan <file>
nonfiction-gov cfi frames

# Tone profiling
nonfiction-gov tone show
nonfiction-gov tone ingest <file>
nonfiction-gov tone check <file>
nonfiction-gov tone guidance

# Anchor management
governor continuity anchor add --id <id> --type <type> --description <desc> [options]
governor continuity anchor list
governor continuity anchor show <id>
governor continuity anchor remove <id>
governor continuity check <text>

# Violation resolution
governor lite pending
governor lite fix
governor lite revise
governor lite proceed
governor lite exceptions

# System status
governor continuity status
governor status
```

---

*"The AI is a tool. You are the scholar. Don't let it forget that."*
