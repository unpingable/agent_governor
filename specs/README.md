# Agent Governor Specifications

The theoretical foundation and design contracts for the governor system.

---

## How to Read These

**If you're a user**: You don't need these. See `docs/user/` for mode-specific guides (Fiction, Code, Nonfiction).

**If you're implementing**: Start with the core specs in reading order below. The UX specs tell you how surfaces should behave. The interferometry specs describe the multi-model subsystem.

**If you're Claude Code**: Read the relevant spec before building. If implementation diverges from spec, either fix the code or update the spec — but never silently diverge.

---

## Status Key

| Status | Meaning |
|--------|---------|
| `canonical` | Spec matches implementation. Source of truth. |
| `ahead` | Spec describes features not yet implemented. Roadmap. |
| `behind` | Implementation evolved past spec. Spec needs update. |
| `gap` | Feature doesn't exist yet. Spec defines what to build. |
| `stale` | Spec is outdated and may contradict reality. Use with caution. |

---

## Directory Structure

```
specs/
├── core/              Theory and system design (rarely changes)
├── interferometry/    Multi-model subsystem (growing)
├── ux/                Surface specifications (changes often)
└── README.md          You are here
```

---

## Core Specs

The governor's theoretical foundation. Read in this order.

| # | Spec | What It Covers |
|---|------|----------------|
| 1 | **AUTHORIAL_CONTROL_SYSTEM_SPEC.md** | Core theory. Governance invisibility. Neutral default. Start here. |
| 2 | **TONE_MODULATION_SPEC.md** | How fear leaks through surface texture. Impedance matching. |
| 3 | **STRUCTURAL_CONSTRAINTS_SPEC.md** | The meta-invariant. Exit shapes. Institutional narration resistance. |
| 4 | **CODE_SRE_CONTROLLER_SPEC.md** | The polarity flip: prose hides governance, code surfaces it. Custody scoring (Aₚ, Iₚ, Fₚ). |
| 5 | **PUPPET_MODE_INTEGRATION_SPEC.md** | Constraints through voice. How character profiles carry governance. |
| 6 | **GOVERNOR_VOICE_PROFILE_SPEC.md** | The governor's default voice. Behavioral contracts. Footer conventions. |
| 7 | **KERNEL_CONSTRAINTS_SPEC.md** | The non-negotiable invariants. What cannot be disabled. The floor. |
| 8 | **TICKETING_LAYER_SPEC.md** | Failures as first-class objects. Detection → ticket → resolution. |
| 9 | **ANCILLARY_REGIMES_SPEC.md** | All 17 regimes. Reference catalog. |
| 10 | **NONFICTION_CONTROLLER_SPEC.md** | Epistemic control for factual writing. Evidence gating. |
| 11 | **ARCHITECTURAL_COHERENCE_SPEC.md** | Meta-layer preventing silent divergence. How specs and code stay in sync. |
| 12 | **WRITING_MODULES_SPEC.md** | W5 implementation reference. 11 modules, 922 tests, pattern banks, scorers, constraint checkers. |
| 13 | **EPISTEMIC_STACK_SPEC.md** | Claim lifecycle infrastructure. 11 modules, 983 tests, provenance, quorum, TTL, audit, drift. |
| 14 | **QA_HARNESS_SPEC.md** | Self-validating test infrastructure. CLI smoke, self-governance, roundtrip, lifecycle. `status: gap` |
| 15 | **GIT_GOVERNANCE_SPEC.md** | Integrity invariants at commit boundaries. Artifact, cross-index, tagging, pre-commit. `status: gap` |
| 16 | **PERFORCE_SUPPORT_SPEC.md** | P4 substrate for integrity invariants. Changelist, locks, immutable releases, DOI mapping. `status: gap` |
| 17 | **EXTERNAL_CONSTRAINT_SPEC.md** | External substrate binding (Wikidata/Wikipedia/Scholar). Constraint attachment, not truth oracle. `status: gap` |
| 18 | **MCP_SAFETY_SPEC.md** | Self-protective MCP server controls. Rate limits, backpressure, circuit breakers, idempotency. `status: gap` |
| 19 | **SDK_MIDDLEWARE_SPEC.md** | Drop-in governor enforcement for Anthropic SDK. `GovernorMiddleware(Anthropic())`. `status: gap` |

### Reading Guidance

- **Specs 1–4** give you the theory. Read these to understand *why* things work the way they do.
- **Specs 5–7** give you the surface. Read these to understand *how* the system talks to users.
- **Specs 8–13** give you the mechanics. Read these when you need to work on specific subsystems.
- **Specs 14–19** are gap specs — features that don't exist yet but are designed.
- You don't need all 19 to start building. Specs 1, 4, and 7 cover 80% of what matters.

---

## Interferometry Specs

Multi-model divergence as instrumentation.

| Spec | What It Covers |
|------|----------------|
| **INTERFEROMETRY_SPEC.md** | Core theory. Divergence as signal. When to use interferometry vs when not to. |
| **INTERFEROMETRY_CODE_ADDENDUM.md** | Code-specific interferometry. Risk markers, anchor compatibility, progressive disclosure tiers, UX contract. |

### Not Yet Written

| Planned | What It Would Cover |
|---------|---------------------|
| Nonfiction addendum | Research-mode interferometry. Claim-layer diffing. Evidence quality triangulation. |
| Fiction addendum | Canon violation detection across models. Timeline consistency. |

---

## UX Specs

How surfaces behave. These reference core and interferometry specs for policy — they render, they don't decide.

| Spec | What It Covers |
|------|----------------|
| **WEBUI_UX_SPEC.md** | Fiction and code mode panels. Violation modal. Corrections log. Empty states. Voice guidelines. |
| **CLI_UX_SPEC.md** | Layered command structure. `governor fiction` / `governor code` / `governor advanced`. Bare command experience. |
| **VSCODE_UX_SPEC.md** | Gutter indicators, inline resolution, status bar, governor panel, Quick Fix integration. |

### Design Principles (All Surfaces)

- Outcome first, explanation later
- "Could a helpful person say this out loud?"
- The system remembers, the user decides
- Progressive disclosure: dashboard → autopilot → service mode

---

## Templates

Reusable patterns for human-facing documentation. See `docs/templates/README.md`.

| Template | Use For |
|----------|---------|
| **ARCHITECTURE_TEMPLATE.md** | System architecture docs |
| **PRODUCT_DESIGN_TEMPLATE.md** | Product/feature design docs |
| **REQUIREMENTS_TEMPLATE.md** | Requirements tracking with traceability |

---

## User Guides

Plain-language guides for each mode. See `docs/user/`.

| Guide | Audience |
|-------|----------|
| **FICTION_MODE.md** | Writers. Characters, world rules, canon management. |
| **CODE_MODE.md** | Developers. Decisions, constraints, verification, receipts. |
| **NONFICTION_MODE.md** | Researchers and writers. Claims, evidence, citations, provenance. |

---

## Key Concepts (Quick Reference)

| Concept | Where It's Defined | One-Line Summary |
|---------|--------------------|-----------------|
| Governance invisibility | AUTHORIAL_CONTROL_SYSTEM | In prose, governance must not leak. In code, it must be visible. |
| The polarity flip | CODE_SRE_CONTROLLER | Same governor, opposite visibility rules depending on domain. |
| Meta-invariant | STRUCTURAL_CONSTRAINTS | Don't solve unfelt problems. Constraint on constraints. |
| Custody scoring | CODE_SRE_CONTROLLER | Aₚ (accountability) × Iₚ (invariant coupling) × Fₚ (failure explicitness) |
| Kernel constraints | KERNEL_CONSTRAINTS | The five non-negotiables that define what the governor *is*. |
| Claim-evidence coupling | KERNEL_CONSTRAINTS | Claims require support. No exceptions. |
| Contradiction persistence | KERNEL_CONSTRAINTS | Conflicts are recorded, not erased. |
| Interferometry | INTERFEROMETRY | Multi-model divergence as instrumentation, not selection. |
| Progressive disclosure | All UX specs | Dashboard → autopilot → service mode. |
| Proposal/commit split | GOVERNOR_VOICE_PROFILE | Proposal is cheap. Commitment isn't. |

---

## Known Contradictions

Track these. Fix them. Don't let them linger.

| Contradiction | Spec Says | Implementation Does | Resolution |
|---------------|-----------|---------------------|------------|
| Detection vs gating | Block at generation time | Flag after generation | TBD |
| MCP deployment modes | Advisory / gateway / commit-gate | Advisory only | TBD |
| Reset type vocabulary | CONTEXT / MODE / GOAL / CHAIN | CONTINUE / TIGHTEN / RESET / EMERGENCY_STOP | TBD |
| Build ordering | Careful phasing prescribed | Shipped in parallel | Accept reality, update specs |

---

## Contributing a Spec

### Format

Every spec should have:

1. **Version and date**
2. **Executive summary** (what and why in 3 sentences)
3. **Status** (canonical / ahead / behind / gap / stale)
4. **Companion specs** (what else to read)
5. **The actual content**
6. **Version history**

### Rules

- Changes must either **conform to spec** or **update spec** — but cannot silently diverge
- Gap specs are welcome — mark them clearly with `status: gap`
- If implementation evolves past a spec, update the spec or flag it as `behind`
- Specs are design contracts, not documentation. They say what *must* be true, not what *is* true.

### Gap Spec Format

For features that don't exist yet:

```yaml
status: gap
implemented: false
depends_on: [list of specs/modules]
blocking: [what can't work without this]
estimated_scope: small | medium | large
```

---

## The Invariant

> Changes must either conform to spec, or update spec — but cannot silently diverge.

That's the one rule. Everything else follows.

---

*"Specs are design contracts, not documentation."*

*"If the code contradicts the spec, one of them is wrong. Figure out which."*

*"The theory is your moat. The UX is your drawbridge."*
