# Constraint Compiler Specification

## Version 0.1 — Pre-Execution Constraint Projection

```yaml
status: implemented
implemented: true
depends_on:
  - continuity.py          # AnchorRegistry, ContinuityChecker
  - profiles.py            # ProfileManager, ProfileSettings
  - spine.py               # Spine, SpineManager
  - invariant_store.py     # InvariantSpec, InvariantStore
  - continuity_bridges.py  # Mode-specific anchor factories
  - routing.py             # Router, ModelRegistry
  - security.py            # SecurityVerifier (pattern catalog)
  - scars.py               # ScarLedger (action restrictions)
  - envelopes.py           # Operating mode (strict/exploratory)
blocking: governed multi-LLM codegen pipeline
estimated_scope: medium
```

### Companion to: SDK_MIDDLEWARE_SPEC.md, KERNEL_CONSTRAINTS_SPEC.md

---

## Executive Summary

The governor gates output — it checks proposed actions after generation and refuses those that violate constraints. This works, but it creates a **generate-reject-regenerate** loop that wastes tokens, time, and user patience.

The Constraint Compiler resolves all applicable constraints for a given intent + scope **before** generation begins, and emits a portable constraint block that any executor LLM can consume as a prompt prefix. The governor still gates output afterward (belt and suspenders), but projection reduces rejection churn by giving the executor the law before it speaks.

**One-liner**: `governor constraints resolve --intent production --scope "src/auth/**" --format prompt`

**Core principle**: The governor already decides what's admissible. This adds the constraint set — compiled, projected, and hashed — so the executor can see the rules upfront instead of discovering them by refusal.

---

## 1. The Problem

### 1.1 The Generate-Reject Loop

Binary gating alone produces this workflow:

1. Executor generates code
2. Governor rejects (anchor violation, invariant failure, security pattern)
3. Executor regenerates with rejection feedback
4. Governor rejects again (different violation)
5. Repeat until pass or user gives up

This trains users into adversarial prompt games and burns tokens on predictable rejections.

### 1.2 Scattered Constraint Sources

Constraints that should inform generation currently live in separate subsystems:

| Source | What It Knows | Where It Lives |
|--------|--------------|----------------|
| Anchors | Required/forbidden text patterns, severity | `continuity.py` |
| Profiles | Named governance presets (strict, production, etc.) | `profiles.py` |
| Spines | Locked project structure, file/dir rules | `spine.py` |
| Invariants | Mechanically verifiable rules (tests, file-exists, etc.) | `invariant_store.py` |
| Scars | Action restrictions from prior failures (hard/soft/procedural) | `scars.py` |
| Intent | Profile + scope + timebox from user | `cli.py` (intent commands) |
| Envelope | Operating mode (strict/exploratory) | `envelopes.py` |
| Security patterns | Known vulnerability signatures | `security.py` |
| Decisions | Normative choices in the ledger | `ledgers.py` |

No single call resolves "what constraints apply to this intent + scope?" across all sources.

### 1.3 Mode-Specific Bridges Are Not General

`continuity_bridges.py` already compiles fiction bible / nonfiction corpus / puppet profiles into anchors, and `GovernorHooks` injects these into system prompts. But this is:

- Tied to the chat bridge / WebUI path
- Mode-specific (fiction, nonfiction, puppet)
- Not available as a standalone compilation step
- Not content-addressed or receipt-producing

---

## 2. The Solution

### 2.1 The Compilation Primitive

A single **pure function** that resolves all applicable constraints and emits a portable block.

```python
@dataclass
class ConstraintBlock:
    """Compiled constraints for executor consumption."""
    # Human-readable prompt prefix
    prompt_prefix: str
    # Machine-readable constraint payload
    constraints: list[ResolvedConstraint]
    # Content hash of the resolved set (for receipts)
    content_hash: str
    # Provenance: what sources contributed
    sources: list[ConstraintSource]
    # Timestamp of compilation
    compiled_at: datetime

@dataclass
class ResolvedConstraint:
    """Single resolved constraint."""
    constraint_id: str  # Stable hash of (kind, source, scope, pattern, description)
    kind: str           # "anchor", "invariant", "scar", "decision", "spine_rule", "security_pattern"
    severity: str       # "reject", "warn", "info"
    description: str    # Human-readable
    pattern: str | None # Regex or glob, if applicable
    scope: str | None   # File scope, if applicable
    source: str         # Which subsystem produced this
    projection_priority: float  # Ranking for prefix truncation (higher = more prominent)

@dataclass
class ConstraintSource:
    """Provenance for a constraint."""
    subsystem: str      # "anchors", "scars", "spine", etc.
    count: int          # How many constraints from this source
    hash: str           # Hash of source state at compilation time
```

### 2.2 The Compilation Function

```python
def compile_constraints(
    intent: str | None = None,
    scope: str | list[str] | None = None,
    mode: str | None = None,           # code, fiction, nonfiction, ops
    backend: str | None = None,        # for backend-specific formatting
    governor_dir: Path | None = None,
) -> ConstraintBlock:
    """
    Resolve all applicable constraints for intent + scope.

    Pure function. No side effects. No backend calls.
    Deterministic on inputs. Content-addressed output.
    """
```

Properties:
- **Pure**: No side effects, no backend calls, no network
- **Deterministic**: Same inputs → same output (modulo ledger state, which is hashed)
- **Content-addressed**: Output includes hash of resolved constraint set
- **Backend-agnostic**: Prompt prefix is plain text; any LLM can consume it

### 2.3 Constraint Resolution Order

Resolution proceeds in layers, each narrowing the constraint set:

1. **Envelope** — strict vs exploratory (sets baseline strictness)
2. **Profile** — named preset (overrides envelope defaults)
3. **Intent** — user-declared intent (further narrows)
4. **Mode** — domain-specific constraints (fiction bible, nonfiction corpus, etc.)
5. **Scope** — file/directory filtering (only constraints relevant to target paths)
6. **Spine** — structural locks (if active spine, apply file/dir rules)
7. **Invariants** — mechanically verifiable rules (scoped to target)
8. **Scars** — prior failure restrictions, classified as hard/soft/procedural (scoped to target; warrants checked here)
9. **Decisions** — normative choices from the decision ledger
10. **Anchors** — required/forbidden patterns (scoped to target)
11. **Security** — vulnerability patterns relevant to file types in scope

Each layer can only **narrow** (add constraints), never widen. This is monotonic — more context means more constraints, never fewer.

### 2.4 Prompt Prefix Format

The compiled prompt prefix is structured but human-readable:

```
[GOVERNOR CONSTRAINTS — hash:a3f7c2...]

INTENT: production codegen
SCOPE: src/auth/**
MODE: code
ENVELOPE: strict

HARD CONSTRAINTS (violation = rejection):
- Decision: "Authentication uses JWT" (framework:auth)
- Anchor: Must not contain "password" in plaintext string literals
- Scar: src/auth/login.py — no direct DB queries (failed 2025-05-12)
- Invariant: tests/test_auth.py must pass after changes
- Spine: src/auth/ — no new files without .py extension

SOFT CONSTRAINTS (violation = warning):
- Anchor: Prefer async handlers in src/auth/
- Decision: "Prefer dataclasses over dicts for DTOs"

SECURITY (known patterns to avoid):
- No SQL string interpolation (SQL injection)
- No subprocess with shell=True (command injection)

[END CONSTRAINTS — 11 resolved, 5 sources]
```

### 2.5 CLI Surface

```bash
# Resolve constraints for intent + scope
governor constraints resolve \
  --intent production \
  --scope "src/auth/**" \
  --format prompt           # prompt | json | summary

# Resolve with mode
governor constraints resolve \
  --scope "chapter-3.md" \
  --mode fiction \
  --format prompt

# JSON output (for programmatic use / receipts)
governor constraints resolve \
  --intent hotfix \
  --scope "src/api/**" \
  --format json

# Diff: what changed since last compilation
governor constraints diff \
  --scope "src/auth/**"
```

### 2.6 Library API

```python
from governor.constraint_compiler import compile_constraints

# Compile
block = compile_constraints(
    intent="production",
    scope=["src/auth/**"],
    mode="code",
)

# Use as prompt prefix
executor_prompt = block.prompt_prefix + "\n\n" + user_task

# Use hash for receipts
receipt = Receipt(
    constraint_hash=block.content_hash,
    sources=block.sources,
)
```

---

## 3. Integration Points

### 3.1 With `governor wrap`

```bash
# Current: wrap gates output only
governor wrap -- claude "refactor auth"

# Future: wrap compiles + projects + gates
governor wrap --project -- claude "refactor auth"
```

The `--project` flag compiles constraints from current intent/scope and injects the prompt prefix before the executor runs.

### 3.2 With SDK Middleware

```python
client = GovernorMiddleware(Anthropic(), project_constraints=True)
# Automatically compiles constraints and prepends to system prompt
```

### 3.3 With WebUI / Chat Bridge

`GovernorHooks` already enriches system prompts. The constraint compiler replaces the ad-hoc mode-specific logic in `continuity_bridges.py` with a unified call:

```python
# Before (mode-specific)
anchors = fiction_bridge.build_anchors(bible)
prompt = inject_anchors(base_prompt, anchors)

# After (unified)
block = compile_constraints(mode="fiction", scope=current_file)
prompt = block.prompt_prefix + "\n\n" + base_prompt
```

### 3.4 With Interferometry

When comparing models, each executor receives the same constraint block. Divergence analysis can then distinguish:
- Violations of projected constraints (executor ignored the law)
- Violations of non-projected constraints (compiler missed something)

### 3.5 Constraint Diffs

Post-execution, the governor can report:

| Constraint | Status | Detail |
|-----------|--------|--------|
| JWT auth decision | Respected | No contradictions found |
| No plaintext passwords | Respected | — |
| No direct DB queries (scar) | **Violated** | Line 42: `db.execute(...)` |
| Async handlers (soft) | Irrelevant | No handler code in output |

This turns rejection from "you failed" into "here's what you were told and here's what you did."

---

## 4. Design Constraints

### 4.1 Must Be Pure

The compiler reads ledger/spine/invariant state but does not mutate it. No side effects. This means:
- Safe to call speculatively
- Safe to call multiple times
- Output is cacheable (keyed on content hash of inputs)

### 4.2 Must Be Fast

Constraint compilation must complete in <100ms for typical projects. This rules out:
- Running any external commands
- Network calls
- File hashing (use cached state from ledger)

### 4.3 Must Be Monotonic

More specific intent/scope can only add constraints, never remove them. A `production` profile cannot disable a `reject`-severity anchor. This preserves the invariant that the governor never weakens its own gates.

Override warrants do not violate monotonicity — they tag constraints as overruled rather than removing them, and monotonically increase accountability cost (see Section 7.5). The constraint is still present in the compiled block; it just doesn't block execution.

Exception: `exploratory` envelope explicitly relaxes receipt requirements. This is the one case where the envelope layer widens. The compiler should emit a clear warning when operating in exploratory mode.

### 4.4 Must Be Content-Addressed

The output hash covers the full resolved constraint set. This enables:
- Receipts that prove what constraints were active at generation time
- Diff detection between compilations
- Cache invalidation when constraints change

---

## 5. What This Is Not

- **Not an orchestration framework.** No dispatcher, no pipeline, no agent coordination.
- **Not a prompt engineering tool.** The prefix is structured constraint projection, not persuasion.
- **Not a replacement for gating.** The governor still verifies output. Projection reduces churn; gating preserves authority.
- **Not mode-specific.** Works across code, fiction, nonfiction, ops. Mode just selects which bridges contribute constraints.

---

## 6. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `KERNEL_CONSTRAINTS_SPEC.md` | Compiler resolves kernel constraints as one source |
| `SDK_MIDDLEWARE_SPEC.md` | Middleware calls compiler for `project_constraints=True` |
| `INTERFEROMETRY_SPEC.md` | All executors receive same compiled block |
| `SESSION_CONTINUITY_SPEC.md` | Compiled constraints are part of session capsule |
| `AG2_TEMPORAL_ATTACK_SURFACE_SPEC.md` | Temporal patterns become compilable constraints |

---

## 7. Override Warrants (Scars vs Hotfix Intent)

### 7.1 The Problem

Scars encode failure memory. Hotfix intent demands action in scar-restricted regions. If all scars are equally immovable, hotfixes become impossible theater. If all scars are bypassable, failure memory means nothing.

### 7.2 The Invariant

> **Overrides must be explicit, scoped, expiring, attributable, and cost-increasing. They may bypass scars; they may not erase them.**

Emergency powers don't repeal the constitution — they burn political capital and leave a paper trail.

### 7.3 Scar Taxonomy

Not all scars are equal. The compiler must distinguish:

| Scar Class | Overridable? | Examples |
|-----------|-------------|----------|
| **Hard** | Never | Provenance breaks, tamper detection, missing receipts, unknown tool execution |
| **Soft** | With warrant | Risky refactors, broadened scope, touching sensitive paths |
| **Procedural** | With warrant + mandatory review | Bypassed approvals, disabled checks |

Hard scars are constitutional — no override, no exception, no emergency. The compiler treats them as `reject`-severity constraints that cannot be overruled.

### 7.4 Override Warrant as First-Class Artifact

Overrides are not a `--force` flag. They are content-addressed, receipt-producing artifacts:

```python
@dataclass
class OverrideWarrant:
    """Explicit, scoped, expiring override of soft/procedural scars."""
    warrant_id: str             # Content hash
    invoked_by: str             # Principal (human identity)
    reason: str                 # Required, free text
    scope: list[str]            # Paths/commands/resources
    constraints_overruled: list[str]  # Explicit list, no wildcards
    expires_at: datetime        # Hard expiry
    risk_ack: bool              # Explicit acknowledgment
    required_followup: str | None     # Issue URL / ticket ID
    quorum_signers: list[str] | None  # Optional second signer(s)
```

The warrant already exists as `governor override create` (see CLI reference). This spec formalizes its role in constraint compilation.

### 7.5 Monotonic Cost

The compiler's monotonicity property survives overrides if overrides are **monotonic in accountability cost**:

- Constraints monotonically **narrow** action space by default
- Overrides monotonically **increase** accountability cost

When a warrant overrides a soft scar, the compiler:

1. **Raises required evidence tier** for the overruled constraint's scope
2. **Forces post-run review** (procedural scars always require this)
3. **Reduces future action budget** until the `required_followup` is recorded
4. **Tags the constraint as overruled** in the compiled block (not removed)

### 7.6 Compiler Output With Warrants

When an active warrant exists, the compiler emits two additional sections:

```
OVERRULED CONSTRAINTS (active warrant W-a3f7c2, expires 2025-06-01T14:00Z):
- Scar [SOFT]: src/auth/login.py — no direct DB queries
  Overruled by: jbeck, reason: "hotfix CVE-2025-1234"
  Cost: evidence tier raised to TOOL_TRACE, post-run review required

⚠ WARRANT BANNER: Operating under emergency warrant W-a3f7c2.
  Do not broaden scope beyond src/auth/login.py.
  Produce explicit evidence for all mutations.
  Warrant expires in 1h47m.
```

The constraint block also splits output into:

1. `effective_constraints` — what the executor must obey
2. `overruled_constraints` — what *would* block, with warrant provenance attached

### 7.7 Loud Receipts

When an override is exercised, the compiler and post-execution gate must make it impossible to miss:

- Run summary includes `OVERRIDE USED` status
- Exit status changes to `success_with_override` (distinct from clean `success`)
- Receipts include a top-level `override_receipt` linked to the warrant
- Per-constraint receipts include `overruled_by` field
- Constraint diff tooling highlights overrides as their own category
- Telemetry emits `OVERRIDE_EXERCISED` event

---

## 8. Constraint Block Size (Prefix Budget)

### 8.1 The Invariant

> **HARD constraints must be complete in-prefix. Soft/security may be summarized but must remain referentially complete by ID + full-set hash.**

This prevents "we optimized the prompt and now the law is vibes again."

### 8.2 Constraint IDs

Every resolved constraint gets a stable `constraint_id`:

```python
constraint_id = hash(kind + source + scope + pattern + description)
```

This enables:
- Referential completeness when soft constraints are summarized
- Post-execution diff ("which constraint was violated?") without re-resolving
- Cache key stability

### 8.3 Prefix Rendering Rules

The prompt prefix is rendered in three tiers:

1. **HARD section** — always complete, full text, for the requested scope. No summarization.
2. **SOFT section** — top-K by projection priority (see 8.4), with remainder available by reference.
3. **SECURITY section** — category summaries + "full catalog available via `governor constraints resolve --format json`"

Footer always includes:

```
FULL_CONSTRAINT_SET: hash=<content_hash>; count=<N>; resolve via governor constraints resolve --format json
```

### 8.4 Projection Priority (Deterministic, Not Vibes)

When the SOFT section must be truncated, priority is computed deterministically:

1. **In-scope** > out-of-scope (constraints matching target paths rank higher)
2. **Scar-adjacent** > never violated (recently violated constraints rank higher)
3. **File-specific** > global (narrow scope ranks higher)
4. **Decision ledger** > style preferences (normative choices rank higher)

Priority is computed at resolution time and stored on `ResolvedConstraint`. The compiler does not make judgment calls — it applies the ranking function.

---

## 9. Feedback Loop (Compiler Stays Pure)

### 9.1 The Rule

The compiler does not learn. It does not accumulate state. It is a deterministic function over ledger state.

### 9.2 How Adaptation Happens Without Statefulness

When an executor violates a projected constraint:

1. Post-execution gate emits a **violation receipt** (constraint ID + violation detail)
2. A separate post-run step can optionally:
   - Mint a new scar (if the violation was dangerous)
   - Increase the violated constraint's projection priority in the ledger
   - Escalate the constraint's severity

The compiler remains pure. But the ledger evolves via audited receipts, so the *next* compilation reflects the violation — the constraint appears higher in the SOFT ranking, or has been promoted to HARD.

**Projection prominence is data-driven via ledger/scars, not via compiler memory.**

---

## 10. Caching

### 10.1 Split Compilation From Rendering

The resolved constraint set is deterministic and content-addressed. Rendering to prompt text is backend-specific and may include relative time formatting. These are two steps:

1. **Resolve** → `ConstraintBlock` (cacheable, content-addressed)
2. **Render** → prompt prefix string (computed at display time from cached block)

This means "expires in 1h47m" is never baked into the cache — the warrant's absolute `expires_at` timestamp is cached, and the renderer computes the human-readable countdown.

### 10.2 Cache Key

Input fingerprint, not output hash:

```python
cache_key = hash(
    intent,
    envelope,
    profile_hash,
    sorted(normalized_scope_globs),
    mode,
    spine_hash,
    invariant_store_hash,
    anchor_registry_hash,
    scar_ledger_hash,
    decision_ledger_epoch,
    active_warrant_set_hash,
)
```

Plus a `nearest_warrant_expiry` field: if the cache entry references a warrant that has since expired, the entry is invalid and the compiler recompiles.

### 10.3 Invalidation

- **Epoch-based**: any ledger mutation bumps the epoch, invalidating cache entries that included that ledger's hash
- **Warrant-aware**: entries with expired warrants are stale
- **Scope-independent**: cache entries for different scopes don't interfere (scope is part of the key)

---

## 11. Warrant Quorum Policy

### 11.1 Policy Function, Not Hard-Coded Rule

Quorum requirements are a function of `(profile, envelope, scar_class)`, not a global constant:

| Scar Class | `strict` + `production` | Otherwise |
|-----------|------------------------|-----------|
| **Hard** | Never overridable | Never overridable |
| **Soft** | 1 signer | 1 signer |
| **Procedural** | 2 signers required | 1 signer |

### 11.2 Identity Verification

Quorum requires **verifiable identity**, not "someone typed a name."

If identity plumbing is not available (no SSO, no GPG, no verified git identity):
- Required quorum **cannot be satisfied**
- Warrant is **invalid**
- Constraint remains **blocking**

This is the safe degradation: unverifiable quorum = no quorum = no override. The compiler emits a first-class receipt:

```python
@dataclass
class QuorumUnsatisfiedReceipt:
    """Warrant rejected: quorum could not be verified."""
    warrant_id: str
    required_signers: int
    verified_signers: int
    reason: str  # "identity verification unavailable" / "insufficient signers"
    constraint_id: str  # The constraint that remains blocking
```

This prevents the "quorum field that everyone ignores" — if the field exists and can't be satisfied, the warrant fails loudly rather than degrading silently.

### 11.3 Future Integration

The quorum state machine (`quorum.py`) already implements multi-agent consensus with fingerprint gating and risk levels. Warrant quorum should eventually delegate to the same policy engine, but for initial implementation, the simple table in 11.1 is sufficient.
