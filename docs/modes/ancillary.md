# Ancillary Modes & Governance Layers

These aren't full "modes" like Fiction, Code, Nonfiction, or Ops. They're governance *layers* that work alongside or within those modes to provide additional control.

---

## Overview

| Layer | Purpose | Works With |
|-------|---------|------------|
| **Puppet Mode** | Pin AI to a specific persona/voice | Any mode |
| **Strict Mode** | Fail-closed governance preset | Any mode |
| **Research Mode** | Non-convergent epistemic exploration | Nonfiction, Code |
| **Docket & Adjudicator** | Time-bounded verification, rulings | Any mode |

> **On "Maude"**: In chat/interactive mode, you can prefix resolution commands with "maude" (e.g., `maude fix`). The CLI commands are `governor lite *`.

---

## Puppet Mode

### What It Does

Puppet Mode pins the AI to a specific persona with constrained voice, epistemic posture, and semantic boundaries. It's for when you need consistent character voice (fiction) or consistent expert persona (nonfiction/code).

### Why It Exists

AI tends to drift toward a generic "helpful assistant" voice. When you need:
- A character who speaks a certain way
- An expert who stays in their lane
- A persona with specific knowledge boundaries

Puppet Mode enforces these constraints with a semantic diff guard.

### How to Use It

```bash
# List available puppets
governor puppet list

# Activate a builtin puppet
governor puppet activate technical-writer

# Create a custom puppet
governor puppet create grumpy-sysadmin --file persona.json

# Check active puppet
governor puppet status

# Test text against puppet constraints
governor puppet test grumpy-sysadmin "I'd be happy to help you with that!"
# → Violation: persona never uses "happy to help"

# Render text through active puppet
governor puppet render "Here's how to fix it"
```

### Puppet Profile Structure

```json
{
  "id": "grumpy-sysadmin",
  "name": "Grumpy Sysadmin",
  "voice": {
    "tone": "terse, slightly annoyed",
    "vocabulary": ["RTFM", "have you tried rebooting", "that's a Layer 8 problem"],
    "forbidden": ["I'd be happy to", "Great question!", "Absolutely!"]
  },
  "epistemic_posture": {
    "certainty_default": "high for infrastructure, low for business logic",
    "hedging_style": "minimal"
  },
  "boundaries": {
    "will_discuss": ["linux", "networking", "databases", "monitoring"],
    "will_not_discuss": ["frontend", "management", "feelings"]
  }
}
```

### Semantic Diff Guard

Puppet Mode includes 7 rules and 2 warnings that prevent persona drift:

**Rules (block on violation):**
1. Forbidden phrases cannot appear
2. Required ticks must appear (catchphrases, verbal habits)
3. Epistemic posture must match (certainty levels)
4. Topic boundaries must be respected
5. Tone must stay within envelope
6. Vocabulary must match register
7. Response structure must match skeleton

**Warnings:**
- Hedging level drift
- Formality level drift

---

## Strict Mode

### What It Does

Strict Mode is a fail-closed governance preset. When enabled, claims require explicit evidence, decisions must be committed, and ambiguity triggers rejection rather than warning.

### Why It Exists

Default governance is permissive — it warns rather than blocks, allows exploration, trusts reasonable defaults. Strict Mode flips this:

- **Permissive**: "Probably fine, but I'll warn you"
- **Strict**: "Prove it or I block it"

Use Strict Mode for:
- Production deployments
- High-stakes decisions
- Audit-sensitive environments
- When you can't afford "probably fine"

### How to Use It

```bash
# Check current status
governor strict status

# Evaluate a claim
governor strict evaluate empirical "The tests pass"
# → BLOCKED: empirical claims require TEST_RESULT evidence

# See requirements for a category
governor strict requirements empirical

# View evaluation history
governor strict history
```

### Claim Categories

| Category | Default | Strict |
|----------|---------|--------|
| EMPIRICAL | Warn if no evidence | Block if no evidence |
| NORMATIVE | Allow with decision | Require committed decision |
| ARCHITECTURAL | Allow with rationale | Require ADR reference |
| SECURITY | Block without evidence | Block + require review |

### Activation

Strict Mode is a profile, not a toggle:

```bash
# Activate strict profile
governor profile use strict

# Check active profile
governor profile status

# Deactivate
governor profile off
```

---

## Research Mode

### What It Does

Research Mode enables non-convergent epistemic exploration. Instead of forcing claims toward consensus, it maintains multiple hypotheses with explicit uncertainty and allows entropy.

### Why It Exists

Normal governance wants convergence — resolve conflicts, reach decisions, commit facts. Research Mode recognizes that early-stage inquiry shouldn't converge prematurely:

- Multiple hypotheses should coexist
- Uncertainty should be explicit, not collapsed
- Evidence should accumulate without forcing conclusions
- Dead ends should be preserved, not deleted

### How to Use It

```bash
# Activate research mode profile
governor profile use research

# Create a hypothesis
governor research hypothesis add \
  --id "hyp-1" \
  --claim "The bottleneck is in the database layer" \
  --confidence 0.3

# Add competing hypothesis
governor research hypothesis add \
  --id "hyp-2" \
  --claim "The bottleneck is in the network layer" \
  --confidence 0.4

# Record evidence
governor research evidence add \
  --supports "hyp-1" \
  --description "Query profiling shows 80% of latency in DB calls" \
  --weight 0.6

# Check hypothesis states
governor research status
```

### Hypothesis Lifecycle

```
PROBE → TENTATIVE → SUPPORTED → (terminal)
                  ↘ ABANDONED → (terminal)
```

- **PROBE**: Initial speculation, low confidence
- **TENTATIVE**: Some evidence, competing alternatives
- **SUPPORTED**: Strong evidence, no fatal contradictions
- **ABANDONED**: Contradicted or superseded

### Constraints

Research Mode still has constraints:
- **Entropy bounds**: Can't have unlimited hypotheses
- **Dominance caps**: No single hypothesis can have >80% weight without evidence
- **Timescale invariant (Δt)**: Hypotheses must remain stable for minimum time
- **Evidence decay**: Old evidence loses weight without refresh

---

## Docket & Adjudicator

### What It Does

The Docket presents governance issues as cases requiring rulings, not linting warnings. It treats verification as a **time-bounded relation** between artifact, context, and evidence.

Key concept: *Verification is not a property of artifacts. It is a time-bounded relation.*

### Why It Exists

Claims decay. Evidence becomes stale. Constraints get violated. Instead of treating these as errors to fix, the Docket frames them as cases requiring adjudication:

- **Contested cases**: Anchor violations (output conflicts with constraint)
- **Stale cases**: Claim confidence decayed below threshold

### How to Use It

```bash
# View the docket (pending cases)
governor docket list

# Show a specific case
governor docket show 4721

# Issue rulings on contested cases
governor rule sustain 4721    # Regenerate compliant output
governor rule amend 4721      # Update the anchor instead
governor rule except 4721     # Log as intentional exception

# Issue rulings on stale cases
governor rule reverify 4721   # Re-run verification
governor rule dismiss 4721    # Accept current state

# View past rulings
governor precedent list
governor precedent search "elena"

# View claim health (weather report)
governor status --claims

# View specific claim
governor claim show gc_abc123
```

### Case Types

| Type | Trigger | Rulings Available |
|------|---------|-------------------|
| **CONTESTED** | Anchor violation | Sustain, Amend, Grant Exception |
| **STALE** | Confidence decay | Reverify, Dismiss |

### Staleness Detection

Claims decay over time based on:

- **Freshness window**: How long before decay begins (default: 7 days)
- **Decay rate**: How fast confidence drops (default: 0.1/day)
- **Artifact mutation**: File hash changed since verification
- **Assumption violation**: Stated assumptions no longer hold

### Weather Report

`governor status --claims` shows a health summary:

```
CLAIM STATUS SUMMARY
==================================================
Live Claims:          47  ████████████████░░░░
Degrading:            12  ████░░░░░░░░░░░░░░░░  (confidence 0.5-0.8)
Stale:                 3  █░░░░░░░░░░░░░░░░░░░  (confidence <0.5)
Contested:             1  ░░░░░░░░░░░░░░░░░░░░  (awaiting ruling)

Health Score: 82/100

ATTENTION REQUIRED:
  * 1 contested claim(s) awaiting ruling
  * 3 stale claim(s) need reverification or dismissal

Run `governor docket` to adjudicate.
```

### Precedent Record

Rulings are logged as precedents that inform future decisions:

```bash
governor precedent list
# prec_abc123  #4721  GRANT_EXCEPTION  gc_xyz  elena-eyes  session  "Intentional deviation for dramatic effect"
```

---

## Evidence-Gated Kernel

### What It Does

The `governor lite` commands provide an evidence-gated kernel for coding workflows — the minimal governance surface. It enforces:

- HARD claims require evidence
- Contradictions persist (no silent overwrites)
- Failures are loud (explicit exit codes)

### Why It Exists

The full governor has many subsystems. The lite commands extract the core invariants for coding workflows:

1. **Claims must be typed** (HARD vs SOFT)
2. **HARD claims need evidence** (test results, file checks)
3. **Contradictions don't disappear** (you must resolve them)
4. **Exit shape is checked** (did you actually finish?)

It's the minimum viable governance for agent coding (the "lite" kernel).

### How to Use It

```bash
# Check agent output
governor lite check "I've updated the login function to use bcrypt"
# → SOFT claim (no evidence), status: WARN

governor lite check "Tests pass: pytest returns 0"
# → HARD claim with evidence, status: OK

# Validate a file
governor lite validate src/auth.py

# Score custody metrics
governor lite score "Fixed the bug by updating the regex"
# → Ap: 0.4, Ip: 0.2, Fp: 0.3 (low accountability)

# Extract claims from content
governor lite extract "The API now returns JSON. Tests pass."
# → Claim 1: SOFT "API returns JSON"
# → Claim 2: HARD "Tests pass" (needs evidence)
```

### Custody Scoring

The lite kernel scores output on three dimensions:

| Metric | What It Measures |
|--------|------------------|
| **Ap** (Accountability) | Can we trace who did what? |
| **Ip** (Invariant coupling) | Are constraints being respected? |
| **Fp** (Failure explicitness) | Are failures surfaced clearly? |

Low scores trigger warnings or blocks.

### Claim Levels

| Level | Evidence Required | Example |
|-------|-------------------|---------|
| HARD | Yes | "Tests pass", "File exists", "Build succeeds" |
| SOFT | No | "I think this is better", "Should work", "Updated the code" |

SOFT claims are allowed but flagged. Too many SOFT claims without HARD evidence triggers warnings.

### Exit Shape Checking

The lite kernel verifies that agent output has a proper "exit shape":

- Did the agent complete the task?
- Is the final state clear?
- Are there dangling TODOs?
- Did they claim completion without evidence?

```bash
governor lite check --strict "Done! Everything works now."
# → BLOCKED: no evidence for completion claim
```

---

## Combining Layers

These layers compose:

```bash
# Fiction mode + Puppet (character voice)
governor puppet activate elena-vasquez
# Now fiction mode enforces Elena's voice

# Code mode + Strict (high-stakes deploy)
governor profile use strict
# Now code mode requires evidence for all claims

# Nonfiction mode + Research (early exploration)
governor profile use research
# Now nonfiction mode allows competing hypotheses

# Code mode + lite kernel (agent wrapper)
governor wrap --mode code -- agent "implement feature X"
# Lite kernel checks agent output before commit
```

---

## When to Use What

| Situation | Layer |
|-----------|-------|
| Need consistent character voice | Puppet Mode |
| Need consistent expert persona | Puppet Mode |
| Production deployment | Strict Mode |
| Audit-sensitive environment | Strict Mode |
| Early research, multiple hypotheses | Research Mode |
| Exploratory coding, uncertain direction | Research Mode |
| Wrapping coding agents | `governor lite` / `governor wrap` |
| CI/CD integration | `governor lite check` |
| Claim decay / stale verification | Docket & Adjudicator |
| Logging intentional deviations | Docket (precedent record) |

---

## CLI Reference

### Puppet Mode

```bash
governor puppet list
governor puppet show <id>
governor puppet activate <id>
governor puppet deactivate
governor puppet status
governor puppet create <id> [--file <json>]
governor puppet delete <id>
governor puppet test <id> <text>
governor puppet render <text>
```

### Strict Mode

```bash
governor strict status
governor strict evaluate <category> <claim>
governor strict requirements <category>
governor strict history
governor strict reset --confirm
```

### Research Mode

```bash
governor profile use research
governor research hypothesis add --id <id> --claim <claim> --confidence <0-1>
governor research hypothesis list
governor research evidence add --supports <id> --description <desc> --weight <0-1>
governor research status
```

### Docket & Adjudicator

```bash
governor docket list
governor docket show <case>
governor rule sustain <case>
governor rule amend <case>
governor rule except <case>
governor rule reverify <case>
governor rule dismiss <case>
governor precedent list
governor precedent search <query>
governor claim show <id>
governor status --claims
```

### Lite Kernel

```bash
governor lite check <text>
governor lite check --stdin
governor lite check -f <file>
governor lite validate <path>
governor lite config
governor lite score <text>
governor lite extract <text>
governor lite pending
governor lite fix
governor lite revise
governor lite proceed
governor lite exceptions
```

---

*"Modes define what you're doing. Layers define how carefully you're doing it."*
