# Architectural Coherence Specification

## Version 0.1 — Preventing Silent Divergence

### Companion to: All specs (meta-layer)

---

## Executive Summary

Once the codebase passes a certain mass, "paste me a chunk" stops working. You need **structured compression**: a living map of the system that can be refreshed on demand.

This specification defines:
1. A reproducible "architectural overview" job
2. A coherence anchor for the governor
3. A drift detection mechanism

**Core Principle**: Changes must either conform to the spec, or update the spec — but they can't silently diverge.

**The failure mode we're killing**: Silent divergence.

---

## 1. The Problem

### 1.1 Context Collapse

As the system grows:
- "Paste me a chunk" stops working
- New contributors (including future-you) can't onboard
- Models need full repo dumps to understand anything
- Specs rot because nothing enforces them

### 1.2 The Real Failure Mode

Not "code doesn't match spec" — that's visible.

The real failure: **specs and code drift apart silently**, and no one notices until something breaks.

### 1.3 The Solution

Make the system **self-describing** and then **check changes against that description**.

Same proposal/commit logic, applied to architecture.

---

## 2. Architectural Overview Job

### 2.1 Purpose

One command that produces a current overview you can hand to any model (or your future self) without dumping the repo.

### 2.2 Outputs

| File | Purpose | Format |
|------|---------|--------|
| `ARCHITECTURE.md` | Module map + invariants + dataflows | Markdown |
| `SPEC_INDEX.md` | What specs exist, status, reading order | Markdown |
| `ADR/` | Decision records for major choices | Markdown (numbered) |
| `SYSTEM_MAP.json` | Machine-readable component graph | JSON |

### 2.3 ARCHITECTURE.md Structure

```markdown
# Architecture

## Purpose
[One paragraph: what this system does]

## Core Invariants
- [Invariant 1]
- [Invariant 2]
- ...

## Component Diagram
[Text-based boxes/arrows showing major components]

## Module Inventory

| Module | Responsibility | Key Types | External Deps |
|--------|---------------|-----------|---------------|
| ... | ... | ... | ... |

## Runtime Flows

### CLI Flow
1. [Step]
2. [Step]
...

### WebUI Adapter Flow
...

### Puppet Mode Flow
...

## State Model

| State | Location | Persistence | Why |
|-------|----------|-------------|-----|
| ... | ... | ... | ... |

## Known Mismatches
[List any contradictions between docs and code]
```

### 2.4 SPEC_INDEX.md Structure

```markdown
# Spec Index

## Status Key
- **Canonical**: Source of truth, actively maintained
- **Informative**: Useful context, may lag
- **Stale**: Needs update or removal

## Specs

| Spec | Status | Last Updated | Notes |
|------|--------|--------------|-------|
| AUTHORIAL_CONTROL_SYSTEM_SPEC.md | Canonical | 2026-02-03 | Core architecture |
| ... | ... | ... | ... |

## Reading Order (Must-Read to Understand System)

1. [Spec] — [Why first]
2. [Spec] — [What it adds]
...
```

### 2.5 ADR Structure

Lightweight Architecture Decision Records:

```markdown
# ADR-0001: [Title]

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
[What prompted this decision]

## Decision
[What we decided]

## Consequences
[What this enables/constrains]

## Alternatives Considered
[What we didn't do and why]
```

### 2.6 SYSTEM_MAP.json Structure

```json
{
  "version": "1.0",
  "generated": "2026-02-03T12:00:00Z",
  "nodes": [
    {
      "id": "authorial_controller",
      "type": "module",
      "responsibility": "Core regime detection and control",
      "key_types": ["RegimeVector", "ControllerOutput"],
      "path": "src/authorial/"
    }
  ],
  "edges": [
    {
      "from": "puppet_mode",
      "to": "authorial_controller",
      "type": "depends_on"
    },
    {
      "from": "authorial_controller",
      "to": "state_store",
      "type": "writes_state_to"
    }
  ]
}
```

Edge types:
- `depends_on`: Import/call dependency
- `calls_into`: Runtime invocation
- `writes_state_to`: State mutation
- `reads_state_from`: State access
- `implements`: Interface implementation

---

## 3. Generation Prompt

### 3.1 Claude Code Prompt

Run from repo root:

```
You are generating an architectural overview for this repo.

Constraints:
- Do not refactor code
- Do not change behavior  
- Only add/update documentation files listed below

First, read:
- README.md
- TODO.md (if exists)
- CLAUDE.md (if exists)
- pyproject.toml / package.json / Cargo.toml (whichever exists)
- Top-level package/module directories

Then produce:

1. ARCHITECTURE.md containing:
   - One-paragraph purpose
   - "Core invariants" (bullet list)
   - High-level component diagram in text (boxes/arrows)
   - Module inventory table: module → responsibility → key types → external deps
   - Main runtime flows (sequence bullets)
   - State model: what persists, where, and why

2. SPEC_INDEX.md:
   - List of spec/docs files with "canonical / informative / stale?" flags
   - Top 10 "must-read to understand system" list

3. ADR/0001-*.md (only if missing):
   - Create 3-6 short ADRs for the most consequential architectural decisions you infer

4. SYSTEM_MAP.json:
   - nodes: components/modules with id, type, responsibility, key_types, path
   - edges: depends_on, calls_into, writes_state_to, reads_state_from

Validate that the overview matches the code.
If you find contradictions between docs and code, list them explicitly under "Known Mismatches" in ARCHITECTURE.md.
```

### 3.2 Refresh Schedule

| Trigger | Action |
|---------|--------|
| Weekly (cron) | Regenerate, diff against previous |
| Major PR merged | Regenerate affected sections |
| New spec added | Update SPEC_INDEX.md |
| On demand | Full regeneration |

---

## 4. Coherence Anchor

### 4.1 The Concept

ARCHITECTURE.md + SYSTEM_MAP.json become the **spec snapshot** that the governor checks against.

New changes are validated against this snapshot:
- Does this violate any invariants?
- Does this introduce new dependencies?
- Does it change persistence semantics?
- Does it add components not in the map?

### 4.2 Drift Detection Rules

```typescript
interface DriftCheck {
  // Invariant violations
  invariants_violated: string[];
  
  // Structural changes
  new_dependencies: Dependency[];
  removed_dependencies: Dependency[];
  new_components: Component[];
  removed_components: Component[];
  
  // State changes
  persistence_changes: PersistenceChange[];
  
  // Verdict
  requires_architecture_update: boolean;
  requires_adr: boolean;
}

interface DriftCheckInput {
  git_diff: string;
  architecture_md: string;
  system_map: SystemMap;
}
```

### 4.3 CI/Pre-Commit Gate

Minimal version:

```yaml
# .github/workflows/architecture-check.yml
name: Architecture Coherence Check

on:
  pull_request:
    paths:
      - 'src/**'
      - 'lib/**'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Check for architecture update
        run: |
          # If core modules touched, require ARCHITECTURE.md update or ADR
          CORE_MODULES="src/authorial src/puppet src/governor"
          TOUCHED=$(git diff --name-only origin/main | grep -E "^($CORE_MODULES)" || true)
          
          if [ -n "$TOUCHED" ]; then
            ARCH_UPDATED=$(git diff --name-only origin/main | grep -E "^(ARCHITECTURE.md|ADR/)" || true)
            if [ -z "$ARCH_UPDATED" ]; then
              echo "ERROR: Core modules touched but no ARCHITECTURE.md or ADR update"
              echo "Touched: $TOUCHED"
              echo "Either update ARCHITECTURE.md or add an ADR explaining why no update needed"
              exit 1
            fi
          fi
```

### 4.4 Maude-Powered Review

Fancier version — have Maude do a diff-based coherence review:

**Input**:
- `git diff`
- `ARCHITECTURE.md`
- `SYSTEM_MAP.json`

**Prompt**:
```
Review this diff against the current architecture.

Check:
1. Does this change violate any stated invariants?
2. Does it introduce new dependencies not in SYSTEM_MAP?
3. Does it change persistence semantics?
4. Does it add/remove components?

If any of the above: require ADR or ARCHITECTURE.md update.

Output:
- PASS: No architectural changes detected
- UPDATE_REQUIRED: [list what needs updating]
- ADR_REQUIRED: [describe the decision that needs documenting]
```

**Output**:
```
Maude: UPDATE_REQUIRED

Changes detected:
- New dependency: puppet_mode → ticketing_layer (not in SYSTEM_MAP)
- New state: ticket_history persisted to SQLite (not in State Model)

Required actions:
1. Add edge to SYSTEM_MAP.json: puppet_mode → ticketing_layer (depends_on)
2. Add row to State Model in ARCHITECTURE.md
3. Consider ADR if ticketing integration is a major decision

Maude: BLOCKED — architecture drift detected. To proceed: update docs or add ADR.
```

---

## 5. Design Constraints

### 5.1 Evolution, Not Ossification

**Don't make "remaining in spec" mean "never evolving."**

Make it mean:
- Changes must either conform, OR
- Update the spec/ADR

But they can't **silently diverge**.

### 5.2 Lightweight by Default

The architecture job should:
- Run in < 2 minutes
- Produce < 1000 lines total
- Be readable by humans without tooling
- Be parseable by machines for automation

### 5.3 Single Source of Truth

- `ARCHITECTURE.md` is the human-readable truth
- `SYSTEM_MAP.json` is the machine-readable truth
- They must stay in sync
- If they conflict, `ARCHITECTURE.md` wins (human-curated)

---

## 6. Integration with Existing Specs

### 6.1 Spec Hierarchy

```
ARCHITECTURE.md (system level)
    ↓
SPEC_INDEX.md (spec inventory)
    ↓
Individual Specs (domain level)
    ↓
ADRs (decision level)
    ↓
Code (implementation level)
```

### 6.2 What Gets Indexed

All specs from this project:

| Spec | Category |
|------|----------|
| AUTHORIAL_CONTROL_SYSTEM_SPEC.md | Core |
| NONFICTION_CONTROLLER_SPEC.md | Regime |
| ANCILLARY_REGIMES_SPEC.md | Regime |
| TONE_MODULATION_SPEC.md | Modulation |
| STRUCTURAL_CONSTRAINTS_SPEC.md | Constraints |
| CODE_SRE_CONTROLLER_SPEC.md | Domain |
| TICKETING_LAYER_SPEC.md | Infrastructure |
| PUPPET_MODE_INTEGRATION_SPEC.md | Integration |
| MAUDE_DEFAULT_PROFILE_SPEC.md | Profile |
| ARCHITECTURAL_COHERENCE_SPEC.md | Meta |

### 6.3 Recommended Reading Order

1. **AUTHORIAL_CONTROL_SYSTEM_SPEC.md** — Core concepts, regime vectors, universal invariants
2. **TONE_MODULATION_SPEC.md** — How fear leaks through surface texture
3. **STRUCTURAL_CONSTRAINTS_SPEC.md** — The meta-invariant and remaining load-bearing aspects
4. **CODE_SRE_CONTROLLER_SPEC.md** — The polarity flip for custody contexts
5. **PUPPET_MODE_INTEGRATION_SPEC.md** — How constraints apply through character voice
6. **MAUDE_DEFAULT_PROFILE_SPEC.md** — The governor made legible
7. **TICKETING_LAYER_SPEC.md** — Making failures first-class (optional, enable when needed)
8. **ANCILLARY_REGIMES_SPEC.md** — Reference for specific regimes
9. **NONFICTION_CONTROLLER_SPEC.md** — Deep dive on epistemic control
10. **ARCHITECTURAL_COHERENCE_SPEC.md** — This document (meta)

---

## 7. Bootstrap Sequence

### 7.1 Initial Setup

1. Run architecture generation prompt
2. Review and correct ARCHITECTURE.md
3. Verify SYSTEM_MAP.json matches reality
4. Create initial ADRs for existing major decisions
5. Set up CI gate

### 7.2 Ongoing Maintenance

| Frequency | Action |
|-----------|--------|
| Per PR | CI gate checks for drift |
| Weekly | Regenerate and diff |
| Per major feature | New ADR |
| Per spec change | Update SPEC_INDEX.md |

---

## 8. Example ADRs

### 8.1 ADR-0001: Proposal/Commit Split

```markdown
# ADR-0001: Proposal/Commit Split for All State Changes

## Status
Accepted

## Context
Early versions allowed silent state changes, leading to:
- Difficulty debugging
- No audit trail
- User surprise

## Decision
All state-changing operations follow proposal → preview → confirm → commit.

Applies to:
- File operations
- Config changes
- Constraint modifications
- Ticket operations

## Consequences
- More explicit UX
- Better audit trail
- Slightly more friction for simple operations
- Enables undo/rollback

## Alternatives Considered
- Silent operations with undo: Rejected (users often don't notice until too late)
- Confirmation only for destructive: Rejected (inconsistent UX)
```

### 8.2 ADR-0002: Governance Polarity Flip

```markdown
# ADR-0002: Inverted Governance Visibility for Code vs Prose

## Status
Accepted

## Context
Initial design assumed governance should always be invisible.
Code/SRE contexts revealed this breaks trust — engineers need to see constraints.

## Decision
- Prose: Governance must be invisible
- Code: Governance must be visible and local

Same governor, different constraint sets based on domain.

## Consequences
- Requires domain detection early in pipeline
- Different constraint libraries for prose vs code
- Unified architecture with parameterized behavior

## Alternatives Considered
- Separate systems for prose/code: Rejected (duplication, drift)
- Always visible governance: Rejected (kills prose trust)
```

---

## 9. The Punchline

### 9.1 What This Gives You

- Hand the project to "you guys" without context dumps
- Keep the repo's self-model from rotting
- Catch drift before it becomes bugs
- Make architecture decisions explicit and traceable

### 9.2 The Minimal Version

If you do only one thing:

**Generate ARCHITECTURE.md and keep it current via an ADR gate.**

That alone kills silent divergence.

### 9.3 The Invariant

> **Changes must either conform to the spec, or update the spec — but they can't silently diverge.**

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |

---

*"The failure mode we're killing: silent divergence."*

*"Changes must either conform to the spec, or update the spec — but they can't silently diverge."*

*"If you do only one thing: generate ARCHITECTURE.md and keep it current via an ADR gate."*
