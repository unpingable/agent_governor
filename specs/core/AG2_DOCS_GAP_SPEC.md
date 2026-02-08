# Documentation Gap Specification

## Version 0.1 — Closing Reference Gaps

```yaml
status: implemented
implemented: true
depends_on: []
blocking: documentation credibility
estimated_scope: medium
```

---

## Executive Summary

The codebase has documentation references that point to files and directories that don't exist. This spec tracks those gaps as first-class work items rather than leaving them as silent landmines.

Two categories:

1. **Architecture Decision Records (ADRs)** — Recording *why* decisions were made. The governor's core purpose is decision tracking; the project itself should dogfood this.
2. **Subsystem documentation** — High-level guides for major subsystems that exist in code but lack standalone docs.

---

## 1. Architecture Decision Records

### 1.1 Purpose

ADRs record significant architectural decisions with context and rationale. The governor already enforces decision recording for *users* — the project should do the same for *itself*.

### 1.2 Location

`docs/adr/NNNN-title.md`

### 1.3 Format

Standard ADR format:

```markdown
# NNNN — Title

## Status
Accepted | Superseded by NNNN | Deprecated

## Context
What is the issue that we're seeing that motivates this decision?

## Decision
What is the change that we're proposing/doing?

## Consequences
What becomes easier or more difficult because of this change?
```

### 1.4 Initial ADRs

These decisions already exist in the codebase history and specs. They need to be extracted into ADR format:

| # | Decision | Where the rationale lives today |
|---|----------|-------------------------------|
| 0001 | Proposal/commit split | `specs/core/GOVERNOR_VOICE_PROFILE_SPEC.md`, `BUILD_SPEC.md` |
| 0002 | Gate, not memory (polarity flip) | `CLAUDE.md`, `specs/core/AUTHORIAL_CONTROL_SYSTEM_SPEC.md` |
| 0003 | Fiction/code/nonfiction modes | `specs/core/CODE_SRE_CONTROLLER_SPEC.md` |
| 0004 | SQLite over Postgres | `MULTI_AGENT.md` |
| 0005 | Self-contained WebUI | `specs/ux/WEBUI_UX_SPEC.md` |

### 1.5 Scope

Small — these are extraction tasks, not design tasks. The rationale already exists; it just needs to be surfaced in a standard format.

---

## 2. Subsystem Documentation

### 2.1 Purpose

Standalone guides for major subsystems. Not specs (those exist), not API docs — human-readable overviews for onboarding and orientation.

### 2.2 Gap Analysis

The following subsystem docs were referenced in `docs/architecture/OVERVIEW.md` but never created:

| Document | Subsystem | Existing coverage |
|----------|-----------|-------------------|
| Governor kernel | Verification, receipts, claims | `BUILD_SPEC.md`, `CLAUDE.md` |
| Adapters | WebUI, backend abstraction | `specs/ux/WEBUI_UX_SPEC.md`, `.claude/rules/webui.md` |
| Continuity | Anchors, violations, resolution | `specs/core/KERNEL_CONSTRAINTS_SPEC.md` |
| Ledgers | Facts vs decisions | `BUILD_SPEC.md`, `CLAUDE.md` |
| Modes | Fiction/code/nonfiction | `docs/modes/`, `specs/user/` |
| CLI | Command structure | `.claude/rules/cli-reference.md` |
| Epistemic | Provenance, confidence | `specs/core/EPISTEMIC_STACK_SPEC.md` |

### 2.3 Assessment

Most of these are already covered by existing specs and rules files. The gap is not *missing information* but *missing entry points* — a reader doesn't know where to look.

### 2.4 Recommendation

Rather than creating 7 new files, add a "Where to find it" section to `docs/architecture/OVERVIEW.md` that maps subsystems to their actual documentation locations. This has already been done as part of the v1.0.1 reference cleanup.

If standalone subsystem docs are still desired, they should be concise orientation guides (~1 page each) pointing to the authoritative specs, not duplicating them.

---

## 3. Other Tracked Gaps

| Gap | Source | Resolution |
|-----|--------|------------|
| `ARCHITECTURE.md` (coherence spec output) | `specs/core/ARCHITECTURAL_COHERENCE_SPEC.md` | Create when coherence tooling is built |
| `SPEC_INDEX.md` (coherence spec output) | `specs/core/ARCHITECTURAL_COHERENCE_SPEC.md` | `specs/README.md` serves this role today |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-02-06 | Initial gap spec from reference audit |
