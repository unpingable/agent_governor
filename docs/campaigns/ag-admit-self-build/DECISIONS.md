# Ratified decisions — ag-admit self-build

Reusable operator decision records. **This file is the ping-pong killer.**

## The rule (binding on future agents)

> If a question matches a ratified decision below, **apply the recorded `default_action`
> and cite the decision ID** — do not ask the operator again. Ask only when the current
> case falls **outside** the recorded `applies_when`, or hits a `requires_human_if`
> clause. Decisions are defaults with stated edges, not blanket permission.

Each record: `decision` · `applies_when` · `default_action` · `forbidden` ·
`requires_human_if` · `evidence`.

---

### D001 — Toy/first gate is path authority, before content/security

- **decision:** The first/primary admission gate tests *authority* (is the change inside
  the grant), not hygiene. Security/content scanning is a later, separate gate.
- **applies_when:** choosing what an admission gate checks first for a new lane.
- **default_action:** path-authority (`DiffPathScopeGate`) before any content/security scan.
- **forbidden:** leading with a security scan and calling it admission; "it's dirty" is not
  "it's outside the grant."
- **requires_human_if:** a lane genuinely has no authority surface, only content.
- **evidence:** operator 2026-06-23; `fb4322d`.

### D002 — Touched paths observed from the diff, never the declared field

- **decision:** The gate derives touched paths from the diff/worktree. `CandidateStep.touched_paths`
  is a *declared* claim, recorded for cross-check, never the authority basis.
- **applies_when:** any gate that decides on which paths a change touches.
- **default_action:** parse the diff; decide on observed paths; record declared-vs-observed mismatch.
- **forbidden:** trusting `touched_paths` for the decision ("JSON cosplay").
- **requires_human_if:** the diff cannot be observed → `CANNOT_TESTIFY` (not a human ask per se).
- **evidence:** operator 2026-06-23; `fb4322d`; `tests/test_ag_admit.py::test_gate_ignores_declared_touched_paths_for_decision`.

### D003 — `StepVerdict` is a typed enum (ratified)

- **decision:** `StepVerdict = ADMIT | REJECT | CANNOT_TESTIFY | NEEDS_HUMAN`, lowercase wire values.
- **applies_when:** representing the four-verdict admission union.
- **default_action:** use the enum; projection lives **only** in `ag_admit.project_source_verdict`.
- **forbidden:** branching on raw verdict strings in the conductor; a second projection site.
- **requires_human_if:** a genuinely new verdict category is proposed (enum change = ratification).
- **evidence:** operator 2026-06-23; `fb4322d`; `src/governor/ag_admit.py`.

### D004 — Unknown/unmapped verdict → `CANNOT_TESTIFY`

- **decision:** Any source verdict not recognized projects to `CANNOT_TESTIFY`.
- **applies_when:** projecting a gate's `raw.source_verdict` to `StepVerdict`.
- **default_action:** unknown/missing/`would_block`/ambiguous → `CANNOT_TESTIFY`.
- **forbidden:** best-effort projection to `REJECT` or `NEEDS_HUMAN`; "close enough" string parsing.
- **requires_human_if:** never — this is the conservative default itself.
- **evidence:** operator 2026-06-23; `tests/test_ag_admit.py::test_unknown_never_projects_to_reject_or_needs_human`.

### D005 — `NEEDS_HUMAN` only on an explicit `REQUIRE_HUMAN`

- **decision:** Runtime `NEEDS_HUMAN` arises *only* when the source explicitly carries
  `REQUIRE_HUMAN`. The conductor never mints it; it never rewrites `CANNOT_TESTIFY` →
  `NEEDS_HUMAN`. Campaign-level human halts are a separate, out-of-band concern.
- **applies_when:** deciding whether a step escalates to a human at runtime.
- **default_action:** `CANNOT_TESTIFY` is terminal (halt + request evidence); `NEEDS_HUMAN`
  needs explicit `REQUIRE_HUMAN`.
- **forbidden:** a gate inventing escalation (e.g. a custody-path heuristic); conductor re-projection.
- **requires_human_if:** N/A.
- **evidence:** operator 2026-06-23; `tests/test_ag_admit.py::test_missing_source_verdict_cannot_testify_not_needs_human`.

### D006 — Waiver criterion 2 uses Model A (reuse the bypassed kind)

- **decision:** "Clean antecedents not certified" is a `NonDischargeClaim` of the **specific
  existing** `VALID_NON_DISCHARGE_KIND` the waiver bypasses. No new `clean_antecedents` kind.
- **applies_when:** expressing what a waiver/override admission leaves unsettled.
- **default_action:** Model A — reuse the existing kind; meaning rides in prose `reason`.
- **forbidden:** adding to `VALID_NON_DISCHARGE_KINDS` (that is Model B = a separate
  closed-enum-authority campaign); any change to `gate_receipt.py` closed enums.
- **requires_human_if:** evidence shows multiple consumers genuinely need a general
  antecedent-cleanliness kind → open Model B as its own grant.
- **evidence:** operator 2026-06-23; `8a76306`; `src/governor/admissibility.py`.

### D007 — `ci_verify` refuses waiver admissions by default; explicit opt-in only

- **decision:** A waiver-admission (`verdict=proceed` + non-empty existing-kind unsettled)
  is refused by `ci_verify` unless `accepts_waiver_admitted` is explicitly set, and even
  then only on the structurally valid waiver shape — never on `proceed` generally.
- **applies_when:** a consumer relies on (or refuses) gate receipts.
- **default_action:** refuse-by-default; opt-in relies only on the validated shape;
  malformed `proceed` refused even with the flag; `proceed` is never `pass`.
- **forbidden:** treating `proceed` as `pass`; global receipt-verdict reinterpretation.
- **requires_human_if:** widening the opt-in beyond the single consumer edge.
- **evidence:** operator 2026-06-23 (Slice 3b micro-grant); `8a76306`; `src/governor/ci.py`.

### D008 — Build order: reproducibility capsule → ForbiddenSurfaceGate → self-correction

- **decision:** Build the reproducibility capsule (this directory) first; then
  `ForbiddenSurfaceGate` (semantic-surface gate); then self-correction-within-scope.
- **applies_when:** choosing the next ag-admit build.
- **default_action:** follow this order. Self-correction must not precede the semantic gate
  ("an obedient burglar"); more building must not precede reproducibility ("oral tradition").
- **forbidden:** jumping to self-correction or ForbiddenSurfaceGate before its predecessor lands.
- **requires_human_if:** the operator re-orders explicitly.
- **evidence:** operator 2026-06-23; this capsule; [NEXT.md](NEXT.md).
