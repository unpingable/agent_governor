# Provenance

This project is human-directed and AI-assisted. Final design authority,
acceptance criteria, and editorial control rest with the human author.
AI contributions were material and are categorized below by function.

## Human authorship

The author defined the project direction, requirements, and design intent.
AI systems contributed proposals, drafts, implementation, and critique under
author supervision; they did not independently determine project goals or
deployment decisions. The author reviewed, revised, or rejected AI-generated
output throughout development.

## AI-assisted collaboration

### Architectural design, invariants, and failure-mode analysis

Lead collaboration: ChatGPT (OpenAI). Heavy involvement in boundary design,
invariant identification, footgun avoidance, spec language, naming, and
"what not to build" decisions.
Also contributed substantially to written papers and theoretical framing.

### Implementation, tests, and integration

Lead collaboration: Claude (Anthropic) via Claude Code. Heavy contributions to
source code, test suites, CLI/daemon wiring, module integration, and CI/CD,
including assembly of architectural decisions into working code.

### Validation and adversarial review

Gemini (Google) and DeepSeek were used as secondary validators, particularly
for control theory, mathematical reasoning, and logic verification during
the design of adaptive subsystems.

### Governor-in-the-loop development

Agent Governor was used as a tool during its own development: evidence
gate checks on generated code, pre-commit hooks, receipt emission, and
continuity enforcement. Included because it is unusual and directly relevant
to the project's thesis.

## Provenance basis and limits

This document is a functional attribution record based on commit history,
co-author trailers (where present), project notes/specs, and documented
working sessions. It is not a complete forensic account of all contributions.

Some AI contributions (especially design critique, rejected alternatives,
and footguns avoided) may not appear in repository artifacts or commit
metadata.

Model names/tools are recorded at the platform level (e.g., ChatGPT,
Claude Code, Gemini, DeepSeek); exact model versions may vary across
sessions and are not exhaustively reconstructed here.

## What this document does not claim

- No exact proportional attribution. Contributions are categorized by
  function, not quantified by token count or lines of code.
- Design and implementation were not cleanly sequential. Architecture
  informed code, code revealed design gaps, and the feedback loop was
  continuous.
- "Footguns avoided" and "ideas that didn't ship" are real contributions
  that leave no artifact. This document cannot fully account for them.

---

This document reflects the project state as of 2026-02-21 and may be revised.
