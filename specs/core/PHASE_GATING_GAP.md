# Phase Gating Gap Analysis

## Target-State Misread as Current-State

```yaml
status: gap
relates_to:
  - invariants.py (Invariant, InvariantSet, InvariantStore)
  - invariant_store.py (VALID_KINDS, InvariantSpec)
  - git_governance.py (Profile: greenfield/established/production/hotfix)
  - execution.py (SessionManager, ExecutionState)
  - spine.py (Spine, SpineManager)
blocking: nothing
priority: deferred for v2, required for v3
v2.0.3: stage register + basic gating (minor)
v2.1+: lattice, multi-axis, SaaS implications (major)
```

---

## Problem

The governor has spec documents that describe target-state architecture. Some of
these specs describe systems that don't exist yet (`status: gap`). An LLM reading
the codebase — or an autonomous executor running against the spec tree — can
misread a target-state document as a description of current-state capability.

This produces two failure modes:

1. **Capability hallucination.** The agent claims it can do something the system
   doesn't support yet, because a spec describes it.
2. **Cathedral build.** The agent starts building toward a target state that
   hasn't been authorized for the current stage, pulling in dependencies and
   structural commitments that are premature.

The governor has profiles (`greenfield`, `established`, `production`, `hotfix`)
which control severity of checks. It has invariants that gate file changes. It
has spines that lock project structure. What it does **not** have is a concept
of *current development stage* as a first-class primitive that conditionally
activates or deactivates invariants and constraints.

---

## What Exists Today

### Profiles (git_governance.py)

Profiles set check severity:

```python
class Profile(str, Enum):
    GREENFIELD = "greenfield"    # Warns, doesn't block
    ESTABLISHED = "established"  # Default
    PRODUCTION = "production"    # Strictest
    HOTFIX = "hotfix"            # Emergency bypass
```

These are about *how strict* checks are, not *which checks apply*. A production
profile doesn't know whether the project is in "alpha" or "v3 launched."

### Invariants (invariants.py, invariant_store.py)

Invariants are unconditional:

```python
@dataclass
class Invariant:
    id: str
    type: InvariantType
    rule: str
    verify: Callable[..., InvariantResult]
    on_violation: str = "block"
    enabled: bool = True
```

An invariant is either enabled or disabled. There's no conditional: "this
invariant applies only when the project reaches stage X."

### Spines (spine.py)

Spines lock project structure. They're binary: active or not. No stage
conditioning.

---

## The Gap: Stage as a First-Class Primitive

### What's Missing

A **stage register**: explicit, receipted state that says "this project is
currently at stage X." Invariants, spines, and constraints can be conditioned
on the current stage.

```
spec tree              stage register          invariant set
┌──────────────┐      ┌───────────────┐       ┌──────────────┐
│ SPEC_A (gap) │      │ current: v2   │       │ inv_1: v1+   │
│ SPEC_B (impl)│ ───> │ history: [v1] │ ───>  │ inv_2: v3+   │  (dormant)
│ SPEC_C (gap) │      │ next: v3      │       │ inv_3: v2+   │
└──────────────┘      └───────────────┘       └──────────────┘
```

### Two Separate Problems

**Problem 1: Which invariants apply now?**

An invariant like "all API endpoints must have integration tests" makes sense
in `v2+` but not during initial scaffolding (`v1`). Today, the only toggle is
`enabled: bool`. The stage register adds `active_from_stage`.

**Problem 2: Which specs describe current state?**

A spec with `status: gap` is aspirational. An agent reading it should not treat
it as implemented. The stage register doesn't solve this directly — specs
already have `status` fields — but stage-gated invariants can prevent an agent
from *building toward* a gap spec unless the stage register says it's time.

---

## v2.0.3 Scope (Minor)

### 1. Stage Register

New file: `src/governor/stages.py`

```python
@dataclass
class Stage:
    """A named development stage."""
    name: str               # "v1", "v2", "alpha", "mvp", etc.
    ordinal: int            # For comparison: stage_a >= stage_b
    description: str = ""

@dataclass
class StageRegister:
    """Tracks current project stage. Receipted advancement."""
    current: Stage
    history: list[StageTransition]  # Append-only
    stages: list[Stage]             # Ordered list of valid stages

    def advance(self, to: str, reason: str) -> StageTransition: ...
    def retreat(self, to: str, reason: str) -> StageTransition: ...
    def current_ordinal(self) -> int: ...
```

Persistence: `.governor/stage.json` — single file, small.

**Ordering semantics (v2.0.3):**

- Stage comparisons are by `ordinal` only. No string parsing, no semver.
- `active_from_stage` must exactly match a registered `Stage.name`.
- Unknown stage names in `ordinal_for()` raise `ValueError` (hard error, not
  silent skip). If the stage isn't registered, the spec is broken.
- No boolean expressions (`AND`, `OR`, `>=`) until v2.1+ lattice. The v2.0.3
  stage sequence is a total order: one axis, ordinal comparison.
- Shorthand like `"v3+"` is prose convention only; it is not valid in code.

Stage transitions emit gate receipts:

```python
gate = "stage_register"
verdict = "pass"
subject_kind = "stage_transition"
```

### 2. Stage-Gated Invariants

Add `active_from_stage` to `InvariantSpec`:

```python
@dataclass
class InvariantSpec:
    id: str
    kind: str
    params: dict
    description: str
    active_from_stage: str | None = None  # NEW: None = always active
```

During invariant check, if `active_from_stage` is set:

```python
if spec.active_from_stage:
    current = stage_register.current_ordinal()
    required = stage_register.ordinal_for(spec.active_from_stage)
    if current < required:
        return InvariantResult(
            passed=True,
            message=f"dormant (requires stage {spec.active_from_stage})",
            invariant_id=spec.id,
            details={"classification": "dormant"},
        )
```

**Dormancy is a first-class classification**, not just a message string.
`InvariantResult.details["classification"]` can be `"pass"`, `"fail"`, or
`"dormant"`. This matters for reporting: dashboards and CI summaries can
separate "X checks active, Y dormant" rather than counting dormant as pass.
SaaS tiering (v3) will depend on this distinction.

Dormant invariants are visible in `governor invariant list` but marked as
`(dormant until stage X)`.

### 3. CLI

```bash
governor stage status              # Show current stage
governor stage list                # Show all stages + which is current
governor stage advance <name>      # Advance to next stage (--reason required)
governor stage retreat <name>      # Retreat (--reason required, emits warning)
governor stage history              # Show transition log
```

### 4. Anti-Cathedral Guard

A simple invariant (built-in, not user-configured):

> If a file references a spec with `status: gap` and the current stage
> doesn't include that spec's target version, warn.

This is a lint-level check, not a hard block. It catches the case where an
agent starts building toward a gap spec before its stage is authorized.

Implementation: scan `specs/` for YAML frontmatter, build a map of
spec → `target_stage`. Compare against stage register during
`governor invariant check`.

### Estimated Size

~200-250 lines for `stages.py` + ~50 lines of changes to `invariant_store.py`
+ CLI additions + ~40-50 tests in `tests/test_stages.py` (unit) +
2-3 integration tests in `tests/test_fresh_clone.py` (CLI smoke). Small.

---

## v2.1+ Scope (Major)

### 5. Multi-Axis Stage Lattice

v2.0.3 has a single linear stage sequence. Real projects have multiple axes:

```
code_maturity:  scaffolding → alpha → beta → production
test_coverage:  none → unit → integration → e2e
docs_maturity:  none → api_docs → user_guide → full
deployment:     local → staging → production
```

A stage lattice tracks multiple axes. Invariants can depend on any axis:

```python
active_from_stage: "test_coverage >= integration AND code_maturity >= beta"
```

This is a partial order, not a total order. The lattice doesn't require every
axis to advance in lockstep.

### 6. Stage Plans

A **stage plan** defines what advancing to the next stage requires:

```yaml
stage: beta
requires:
  - invariant: all_tests_pass
  - invariant: no_critical_security_findings
  - metric: test_coverage >= 80%
  - approval: human
```

The stage register refuses to advance unless the plan's requirements are met.
This makes stage advancement a governance event, not just a label change.

### 7. SaaS / Multi-Tenant Implications

If the governor becomes a platform service (v3 direction), stages become
per-tenant:

- **Tenant isolation.** Each tenant has their own stage register. Tenant A at
  `production` doesn't affect Tenant B at `alpha`.
- **Contractual SLOs.** A tenant's subscription tier might require minimum stage
  invariants: "production tier requires all security invariants active."
- **Platform vs. tenant stages.** The platform itself has a stage register
  (which features are shipped). Tenant stages are independent.

This intersects with the self-governance spec (3.x) because stage advancement
for the platform itself requires the admissibility checks described there.

### 7a. Stage Advancement as Governed Action (v3)

In v2.0.3, `governor stage advance` is receipted but permissive — any human
with CLI access can advance. For v3, stage advancement itself becomes a
governed action with:

- **Required authority (role).** Only operators with `stage_admin` role can
  advance. Agents cannot self-advance.
- **Receipt.** Already present in v2.0.3, but v3 receipts include the
  authority chain (who authorized, under what policy).
- **Cooldown / quorum (optional).** Stage advancement can require a dwell
  period (e.g., "must stay in `beta` for 7 days before advancing to
  `production`") or a quorum vote from multiple stakeholders.
- **Activation summary.** On advancement, the system emits a manifest:
  "advancing to stage X enables templates [A, B], activates invariants
  [C, D, E], and unlocks constraint blocks [F, G]." This makes the
  capability elevation explicit and auditable.

This is where phase gating stops being project management and becomes
**capability elevation control**: the system doesn't just track where you
are, it governs what transitions are admissible and makes the consequences
of each transition visible before it happens.

### 8. Domain-Specific Stage Axes

Different governor modes need different axes:

| Mode | Relevant Axes |
|------|--------------|
| Code | code_maturity, test_coverage, deployment |
| Fiction | draft_stage (outline → first_draft → revision → final), world_building |
| Nonfiction | research_stage, citation_coverage, peer_review |
| Ops | runbook_coverage, incident_response_maturity |

The stage lattice is generic. Domain-specific axes are registered by the
mode-specific governors (fiction_governor, nonfiction_governor, ops_governor).

### 9. Template and Intent Compiler Integration

The intent compiler has built-in templates (`session_start`, `task_scope`,
`verification_config`) that today produce complete blueprints. A `task_scope`
template for architecture work currently emits the full target-state scope —
but if the project is at stage `alpha`, only stage-appropriate work should
appear in the compiled intent.

Two changes needed:

**Stage-filtered templates.** Templates gain a `stages` field:

```python
@dataclass
class IntentTemplate:
    template_id: str
    fields: list[FormField]
    stages: list[str] | None = None  # None = all stages
```

When the stage register is at `v2`, templates whose `stages` list doesn't
include `v2` (or any stage with ordinal <= current) don't appear in
`intent_templates()`. The agent never sees options it can't act on.

**Phased architecture constraints.** The architecture-style constraint blocks
(spine locks, forbidden patterns, required structure) emitted by `compile_intent`
get stage annotations:

```python
constraint_block = [
    Constraint(rule="src/ must have __init__.py", active_from_stage="v1"),
    Constraint(rule="all public APIs must have OpenAPI spec", active_from_stage="v2"),
    Constraint(rule="all endpoints must have integration tests", active_from_stage="beta"),
    Constraint(rule="deployment manifests must exist", active_from_stage="production"),
]
```

The executor only enforces constraints where `active_from_stage <= current`.
The rest are visible as "upcoming constraints" in `governor intent show`, so
the team knows what's coming without being blocked by it now.

This prevents the Rome-in-a-day problem: an agent given an architecture spec
builds everything at once because the constraint block doesn't distinguish
between "must have now" and "must have by v3." Phase-gated constraints make
the build order explicit.

### 10. Spec Status Integration

Today specs have `status: gap | implemented | deferred`. With stage gating:

```yaml
status: gap
target_stage: v3
```

The governor can mechanically verify: "this spec's target_stage has not been
reached in the stage register, so any code that implements this spec is
premature." This closes the loop between spec authoring and stage-gated builds.

---

## What This Does NOT Do

1. **Replace profiles.** Profiles control severity (how strict). Stages control
   applicability (which checks). They're orthogonal.
2. **Auto-advance.** Stage advancement is a human decision, receipted. The
   governor can tell you whether advancement requirements are met, but it
   doesn't auto-advance.
3. **Block reading specs.** The agent can read any spec. The guard is on
   *building toward* a spec that's out-of-stage, not on understanding it.
4. **Solve the 3.x governance problem.** Stage gating is infrastructure that
   3.x builds on, but it's not the admissibility/quorum machinery from
   SELF_GOVERNANCE_SPEC.md.

---

## Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `SELF_GOVERNANCE_SPEC.md` | Stage gating is infrastructure; self-governance uses it for platform-level advancement |
| `INVARIANTS_SPEC.md` | Extended with `active_from_stage` field |
| `GIT_GOVERNANCE_SPEC.md` | Profiles become orthogonal to stages; `verify-tag` could check stage requirements |
| `DEPLOYMENT_PROFILES_SPEC.md` | Stage axes for deployment track (local → staging → production) |
| `SCALAR_COLLAPSE_GAP.md` | Analytic predictor (item 1) could gate on `code_maturity >= beta` |
| `SEMANTIC_DIFFUSION_SPEC.md` | Diffusion detector activation could be stage-gated |

---

## Definition of Done (v2.0.3)

Mechanically testable acceptance criteria:

1. **Stage register is receipted state.** `governor stage advance v2 --reason "x"`
   creates a gate receipt (`gate=stage_register`, `subject_kind=stage_transition`).
   Stage persists in `.governor/stage.json`; restart governor and it's still there.

2. **Dormant invariants never block, but are visible.** An invariant with
   `active_from_stage="v3"` returns `passed=True` with
   `details["classification"] == "dormant"` when current stage < v3.
   `governor invariant list` includes it, marked dormant.

3. **Stage-filtered templates shrink option space.** At stage `v2`, templates
   whose `stages` list excludes `v2` do not appear in `intent_templates()`.
   No cathedral by menu.

4. **Phased constraint blocks are stage-enforced.** Only constraints with
   `active_from_stage <= current` are enforced. The rest appear as "upcoming"
   in `governor intent show` but do not produce violations.

5. **Anti-cathedral guard warns on gap-spec builds.** When code references a
   spec with `status: gap` whose `target_stage` is beyond the current stage,
   the guard emits a warning (not a block). Testable with a toy spec tree in
   `tmp_path`.

6. **Unknown stage names are hard errors.** `ordinal_for("nonexistent")` raises
   `ValueError`, not silent pass or "never activates."

7. **Retreat is receipted and logged.** `governor stage retreat` requires
   `--reason`, emits a receipt, and appears in `governor stage history`.

8. **All stage state roundtrips.** `StageRegister.to_dict()` / `from_dict()`
   preserves full state including history.

---

## Recommendation

**v2.0.3: Build the stage register + basic gating.** This is small, useful
immediately (the spec tree already has gap/implemented status), and provides
the primitive that v2.1+ builds on. The anti-cathedral guard alone justifies
it — it prevents agents from building toward gap specs.

**v2.1+: Build incrementally.** Multi-axis lattice and stage plans are
additive. They don't change the stage register's interface, they extend it.
SaaS implications are v3 concerns that the stage register makes possible but
doesn't require upfront.
