# Code/SRE Controller Specification

## Version 0.1 — The Custody Regime

### Companion to: Authorial Control System, Nonfiction Controller, Ancillary Regimes, Tone Modulation, Structural Constraints

---

## Executive Summary

Code is not prose. The governance polarity **inverts**.

- In prose, visible governance kills trust
- In code, invisible governance kills trust

This specification defines the **custody regime** for code generation and SRE contexts, where the load-bearing variable is not epistemic honesty but **accountability clarity**.

**Unifying Principle**: Language earns trust when it makes the cost of being wrong legible to the reader. In prose, that means exposing epistemic risk. In code, that means exposing failure and responsibility.

**Core Rule**: Prose hides governance to preserve trust. Code surfaces governance to preserve custody.

---

## 1. Theoretical Foundation

### 1.1 What Code Is (In This Framework)

Code is **not**:
- An affective regime (except incidentally)
- A persuasion medium
- A trust transfer channel in the prose sense

Code **is**:
- A liability-routing system
- A custody transfer mechanism
- A contract between author and maintainer

### 1.2 What Readers Ask

When humans read code, they subconsciously ask:

| Question | What It's Really Asking |
|----------|------------------------|
| "Who is responsible if this breaks?" | Accountability |
| "Where does failure go?" | Fault isolation |
| "What assumptions am I inheriting?" | Hidden constraints |
| "Can I predict behavior under stress?" | Operational clarity |
| "Can I debug this at 3am?" | Cognitive load |

### 1.3 The Load-Bearing Variable

If prose asks "do I trust you?", code asks:

> **"Can I safely take custody of this?"**

The load-bearing variable for code is:

**Aₚ — Perceived Accountability Clarity**

Not truth. Not trust. **Custody.**

### 1.4 The Polarity Flip

| Domain | Governance | Trust Mechanism |
|--------|------------|-----------------|
| Prose | Must be invisible | Reader trusts what escaped supervision |
| Code | Must be visible and local | Maintainer trusts explicit contracts |

This is the crucial inversion:

- Prose smells bad when it **shows**: hedging, legalese, apology, compliance texture
- Code smells bad when it **hides**: invariants, bounds, failure modes, ownership

**For code: Governance must be explicit, local, and boring.**

### 1.5 Why AI Code Feels Wrong

AI-generated code often:
- Looks confident
- Passes tests
- But responsibility is smeared everywhere
- No clear "if this fails, it fails here"
- Invariants are implied, not enforced
- Failure modes are caught and logged, not bounded and named

That's **committee code** — the code equivalent of "on the one hand... on the other hand..."

---

## 2. The Plant Model

### 2.1 Dev Mode Plant

```
Plant:        Codebase state + build/test pipeline + future maintainer comprehension
Controller:   The governor (custody controller)
Disturbances: Partial context, flaky deps, unknown infra, time pressure, 
              heterogeneous conventions
Output:       Code that is adoptable + debuggable
```

### 2.2 SRE Mode Plant

```
Plant:        System state + incident risk + time-to-mitigate + change failure rate
Controller:   The governor (stability controller)
Disturbances: Partial observability, unknown failure modes, blast radius uncertainty,
              oncall cognitive load
Output:       Changes that are safe + recoverable
```

### 2.3 Outputs to Optimize

| Metric | Target |
|--------|--------|
| Change failure rate | ↓ |
| MTTR | ↓ |
| Incident recurrence | ↓ |
| Operator cognitive load | ↓ |
| Surprise budget | ↓ (behavior matches expectation) |

---

## 3. Load-Bearing Variables

### 3.1 Variable Mapping (Prose → Code)

| Prose Variable | Code Variable | Meaning |
|----------------|---------------|---------|
| Eₚ (epistemic honesty) | Aₚ (accountability clarity) | Who owns this? |
| Cₚ (claim-evidence coupling) | Iₚ (invariant-implementation coupling) | Are constraints enforced? |
| Rₚ (risk texture) | Fₚ (failure surface explicitness) | How does this fail? |
| Governance invisibility | Governance locality | Where are the contracts? |

### 3.2 Aₚ: Accountability Clarity

**Definition**: Can an operator safely take responsibility for this output?

Good code answers:
- Who owns this?
- What layer is this responsibility?
- What assumptions are made?
- What happens on error?

Bad AI code:
- Works
- Passes tests
- But diffuses responsibility across helpers, comments, and magic defaults

**That's why people say "this feels unmaintainable" without being able to point at a bug.**

#### Aₚ Proxy Signals

```typescript
interface AccountabilitySignals {
  ownership_explicit: boolean;        // team/service annotations present
  assumptions_stated: boolean;        // preconditions documented near code
  error_handling_local: boolean;      // failures handled where they occur
  side_effects_bounded: boolean;      // mutations are explicit and contained
  config_defaults_visible: boolean;   // no magic values
}

function calculateAp(signals: AccountabilitySignals): number {
  let score = 0;
  if (signals.ownership_explicit) score += 0.2;
  if (signals.assumptions_stated) score += 0.2;
  if (signals.error_handling_local) score += 0.25;
  if (signals.side_effects_bounded) score += 0.2;
  if (signals.config_defaults_visible) score += 0.15;
  return score;
}

const AP_FLOOR = 0.6;
```

### 3.3 Iₚ: Invariant-Implementation Coupling

**Definition**: How strongly invariants are tied to enforcement mechanisms.

Human-written good code:
- States invariants near the code that enforces them
- Fails loudly when invariants break
- Doesn't rely on comments to explain safety

AI code often:
- Implies invariants
- Relies on "should"
- Encodes safety implicitly

**That's governance leakage in reverse.**

#### The Rule

> An invariant that isn't enforced is narrative. Narrative is for postmortems, not production.

#### Iₚ Proxy Signals

```typescript
interface InvariantSignals {
  type_checks_present: boolean;       // static analysis catches violations
  input_validation_present: boolean;  // contracts at boundaries
  assertions_in_critical_paths: boolean;
  property_tests_present: boolean;    // where feasible
  preconditions_documented: boolean;  // explicit pre/postconditions
}

function calculateIp(signals: InvariantSignals): number {
  let score = 0;
  if (signals.type_checks_present) score += 0.25;
  if (signals.input_validation_present) score += 0.25;
  if (signals.assertions_in_critical_paths) score += 0.2;
  if (signals.property_tests_present) score += 0.15;
  if (signals.preconditions_documented) score += 0.15;
  return score;
}

const IP_FLOOR = 0.5;
```

### 3.4 Fₚ: Failure Surface Explicitness

**Definition**: How legible failure behavior is to a responder.

Humans trust code that:
- Names its failure modes
- Chooses when to crash vs recover
- Distinguishes programmer error from runtime error

AI code loves:
- Catching everything
- Returning None/null
- Logging and continuing
- "Graceful degradation" everywhere

**Which is the code equivalent of committee prose.**

#### The Rule

> Prefer loud, local failure over quiet, smeared failure.

#### Fₚ Proxy Signals

```typescript
interface FailureSignals {
  error_taxonomy_explicit: boolean;   // programmer vs runtime vs dependency
  exception_boundaries_tight: boolean; // no catch-all without context
  timeout_semantics_spelled_out: boolean;
  retry_semantics_spelled_out: boolean;
  circuit_breaker_explicit: boolean;
  structured_logs: boolean;           // stable keys, not prose
}

function calculateFp(signals: FailureSignals): number {
  let score = 0;
  if (signals.error_taxonomy_explicit) score += 0.2;
  if (signals.exception_boundaries_tight) score += 0.2;
  if (signals.timeout_semantics_spelled_out) score += 0.15;
  if (signals.retry_semantics_spelled_out) score += 0.15;
  if (signals.circuit_breaker_explicit) score += 0.15;
  if (signals.structured_logs) score += 0.15;
  return score;
}

const FP_FLOOR = 0.5;
```

---

## 4. Control Handles

### 4.1 Handle A: Invariant Coupling Gain (Kᵢ)

How strongly invariants are tied to enforcement mechanisms.

**Implementation Requirements** (at least one of):
- Type checks / static analysis
- Input validation / contracts
- Assertions in critical paths
- Property tests (where feasible)
- Explicit pre/postconditions in docstrings (if enforced)

**Rule**: An invariant that isn't enforced is narrative.

### 4.2 Handle B: Failure Surface Explicitness (Fₚ)

How legible failure behavior is to a responder.

**Implementation Targets**:
- Explicit error taxonomy (programmer error vs runtime vs dependency)
- Tight exception boundaries (don't catch-all unless you rethrow with context)
- Timeouts + retries + circuit-breaker semantics spelled out, not implied
- Structured logs/events with stable keys (not prose)

**Rule**: Prefer loud, local failure over quiet, smeared failure.

### 4.3 Handle C: Complexity Rate Limit (dC/dt)

The code analog of "premature closure" is **premature abstraction**.

**Implementation**:
- No new abstraction until 2 concrete uses exist (or explicit waiver)
- Cap diff cognitive complexity per PR (or per module)
- Forbid "utility modules" without ownership + tests
- Enforce monotonic complexity (each layer adds at most one new concept)

**Rule**: If the maintainer hasn't felt the pain yet, don't "solve" it.

This maps directly to the meta-invariant:

> Never solve a problem the reader hasn't felt yet.

In code, the "reader" is the maintainer.

### 4.4 Handle D: Phase Budget (Δt)

In SRE, phase-lock isn't joke timing; it's **detection → diagnosis → mitigation** timing.

**Implementation**:
- Ensure signals exist before remediation is needed (SLIs, logs, dashboards)
- Enforce "time-to-first-signal" budgets for new components
- Require runbook hooks: "what to check first" + "how to rollback" in same PR

**Rule**: Mitigation must be phase-locked to observability, or the system becomes improv theater.

### 4.5 Handle E: Governance Locality

In prose, governance must be invisible. In code/SRE, governance must be **visible and local**.

**Implementation**:
- Explicit config defaults (no magic)
- Explicit resource bounds (CPU/mem/concurrency limits)
- Explicit ownership (team/service annotations)
- Explicit safety rails (feature flags, canaries, rollback)

**Rule**: Hidden constraints read as deception; explicit constraints read as contracts.

---

## 5. Mode-Specific Controllers

### 5.1 Developer Mode: Custody Controller

**Objective**: Produce code that is adoptable + debuggable.

#### Hard Gates (Must Pass)

```typescript
interface DevModeGates {
  build_passes: boolean;
  tests_present_for_critical_behavior: boolean;
  invariants_enforced: boolean;        // Kᵢ above threshold
  failure_behavior_specified: boolean; // Fₚ above threshold
  no_premature_abstraction: boolean;   // dC/dt below cap
}

function checkDevModeGates(gates: DevModeGates): boolean {
  return gates.build_passes &&
         gates.tests_present_for_critical_behavior &&
         gates.invariants_enforced &&
         gates.failure_behavior_specified &&
         gates.no_premature_abstraction;
}
```

#### Soft Objectives

- Keep diffs small
- Keep patterns consistent with repo norms
- Minimize surprise

#### Telemetry

| Metric | What It Measures |
|--------|------------------|
| `invariants_added_vs_enforced` | Ratio of stated to enforced invariants |
| `exception_boundary_width` | Lines covered by broad handlers |
| `diff_complexity` | Cognitive load of the change |
| `new_concept_count` | New types/classes/config keys introduced |

### 5.2 SRE Mode: Stability Controller

**Objective**: Minimize change risk and maximize recoverability.

#### Hard Gates (Must Pass)

```typescript
interface SREModeGates {
  rollback_path_exists: boolean;
  rollback_path_tested: boolean;
  observability_hooks_exist: boolean;  // SLIs/log keys
  failure_modes_documented: boolean;   // how it fails + how to notice + what to do
  feature_gating_present: boolean;     // flag/canary for risky changes
}

function checkSREModeGates(gates: SREModeGates): boolean {
  return gates.rollback_path_exists &&
         gates.observability_hooks_exist &&
         gates.failure_modes_documented &&
         (gates.feature_gating_present || !isRiskyChange());
}
```

#### Soft Objectives

- Reduce MTTR pathways
- Reduce oncall cognitive load
- Avoid "silent partial failure"

#### Telemetry

| Metric | What It Measures |
|--------|------------------|
| `signal_coverage` | Events emitted per failure class |
| `time_to_detect_budget` | Synthetics, alerts present |
| `blast_radius_estimate` | Components touched |
| `change_risk_score` | Touched files × runtime criticality |

---

## 6. Δt in Code: Premature Abstraction

### 6.1 The Mapping

| Prose | Code |
|-------|------|
| Premature meaning | Premature abstraction |
| Synthesis before exploration | Generalization before concrete use |
| "Therefore" too early | Helper before need |

### 6.2 Failure Modes

- Abstract helpers before concrete use
- Parameterization without demonstrated need
- Clever reuse that hides invariants
- "Future-proofing" without a future

### 6.3 The Complexity Rate Limit

```typescript
interface ComplexityBudget {
  max_new_abstractions_per_pr: number;  // default: 1-2
  max_cognitive_complexity_delta: number;
  require_concrete_uses_before_abstraction: number;  // default: 2
}

const DEFAULT_COMPLEXITY_BUDGET: ComplexityBudget = {
  max_new_abstractions_per_pr: 2,
  max_cognitive_complexity_delta: 10,
  require_concrete_uses_before_abstraction: 2,
};

interface AbstractionProposal {
  name: string;
  concrete_uses: number;
  waiver_reason?: string;
}

function checkAbstractionAllowed(
  proposal: AbstractionProposal,
  budget: ComplexityBudget
): boolean {
  if (proposal.concrete_uses >= budget.require_concrete_uses_before_abstraction) {
    return true;
  }
  if (proposal.waiver_reason) {
    return true;  // explicit waiver granted
  }
  return false;
}
```

---

## 7. Silence in Code

### 7.1 The Polarity Flip

| Prose | Code |
|-------|------|
| Silence = restraint (good) | Silence = ambiguity (bad) |
| Omission signals trust | Omission signals hidden constraints |

### 7.2 Comment Rules

| Comment Type | Value |
|--------------|-------|
| Why something exists | Good |
| What the code does | Usually bad (code should be clear) |
| Constraints/invariants | Good |
| TODOs without ownership | Bad |
| Apologies | Bad (fix it or own it) |

### 7.3 What Must Not Be Silent

- Invariants
- Bounds
- Failure modes
- Ownership
- Assumptions

**Rule**: In code, omission of constraints is a failure, not restraint.

---

## 8. Style in Code

### 8.1 Tone Doesn't Apply (Mostly)

- Tone-as-warmth? No.
- Tone-as-authorial-voice? No.
- Style-as-predictability? **Yes.**

### 8.2 The "Tone Leak" Equivalents in Code

| Code Smell | What It Signals |
|------------|-----------------|
| Inconsistent patterns | Lack of custody |
| Unexplained cleverness | Ego over maintainability |
| Mixed paradigms | Multiple authors, no owner |
| Surprising control flow | Hidden complexity |

These signal **lack of custody**, not fear.

### 8.3 Style Constraints

The system should enforce:

| Constraint | Why |
|------------|-----|
| Monotonic complexity | Each layer adds at most one new concept |
| Local reasoning | Can understand code without global context |
| Boring repetition | Predictability over cleverness |
| Visible invariants | Contracts, not magic |

**This is the opposite of prose, where repetition often smells bad.**

---

## 9. Error Posture in Code

### 9.1 The Options

| Posture | When Appropriate |
|---------|------------------|
| Crash loudly | Programmer error, unrecoverable state |
| Return error | Expected failure, caller can handle |
| Retry with backoff | Transient failure, idempotent operation |
| Circuit break | Dependency failure, protect system |
| Log and continue | **Rarely** — only for truly optional operations |

### 9.2 The Anti-Pattern

AI code loves:
- `try { ... } catch (Exception e) { log.error(e); return null; }`

This is **smeared failure**. It:
- Hides the error type
- Passes null downstream (where it will fail confusingly)
- Logs prose instead of structured data
- Prevents the caller from making informed decisions

### 9.3 The Rule

> Failures should be **typed, bounded, and loud**.

```typescript
// BAD: Smeared failure
function getUser(id: string): User | null {
  try {
    return db.query(id);
  } catch (e) {
    console.error("Failed to get user", e);
    return null;
  }
}

// GOOD: Explicit failure
type GetUserResult = 
  | { ok: true; user: User }
  | { ok: false; error: 'not_found' | 'db_error' | 'timeout' };

function getUser(id: string): GetUserResult {
  // ... explicit error handling with typed results
}
```

---

## 10. The Scoring Function

### 10.1 Aggregate Score

```typescript
interface CustodyScore {
  Ap: number;  // accountability clarity
  Ip: number;  // invariant-implementation coupling
  Fp: number;  // failure surface explicitness
  
  // Negative factors
  magic_behavior: number;
  broad_exception_smear: number;
  premature_abstraction: number;
}

function calculateCustodyScore(score: CustodyScore): number {
  const positive = (
    score.Ap * 0.35 +
    score.Ip * 0.30 +
    score.Fp * 0.35
  );
  
  const negative = (
    score.magic_behavior * 0.15 +
    score.broad_exception_smear * 0.20 +
    score.premature_abstraction * 0.15
  );
  
  return Math.max(0, positive - negative);
}

const CUSTODY_SCORE_FLOOR = 0.5;
```

### 10.2 Component Scoring

#### Magic Behavior Detection

```typescript
const MAGIC_PATTERNS = [
  /process\.env\.\w+/,              // env var without default
  /config\[['"]?\w+['"]?\]/,        // config access without validation
  /global\./,                        // global state
  /eval\(/,                          // dynamic code
  /Function\(/,                      // dynamic code
  /\.\*\*/,                          // reflection
  /__proto__/,                       // prototype manipulation
];

function detectMagicBehavior(code: string): number {
  let score = 0;
  for (const pattern of MAGIC_PATTERNS) {
    const matches = code.match(new RegExp(pattern, 'g'));
    if (matches) {
      score += matches.length * 0.1;
    }
  }
  return Math.min(1, score);
}
```

#### Broad Exception Smear Detection

```typescript
const EXCEPTION_SMEAR_PATTERNS = [
  /catch\s*\(\s*(Exception|Error|e|\w+)\s*\)\s*\{[^}]*log/i,
  /catch\s*\(\s*\.\.\.\s*\)/,        // catch-all
  /\.catch\(\s*\(\s*\)\s*=>/,        // empty catch
  /return\s+(null|undefined|None)/,  // swallow and return null
];

function detectExceptionSmear(code: string): number {
  let score = 0;
  for (const pattern of EXCEPTION_SMEAR_PATTERNS) {
    const matches = code.match(new RegExp(pattern, 'g'));
    if (matches) {
      score += matches.length * 0.15;
    }
  }
  return Math.min(1, score);
}
```

#### Premature Abstraction Detection

```typescript
interface AbstractionAnalysis {
  new_abstractions: string[];      // new classes/types/interfaces
  concrete_uses_per_abstraction: Map<string, number>;
  utility_modules_without_tests: string[];
  layers_of_indirection: number;
}

function detectPrematureAbstraction(analysis: AbstractionAnalysis): number {
  let score = 0;
  
  // Abstractions without concrete uses
  for (const [abstraction, uses] of analysis.concrete_uses_per_abstraction) {
    if (uses < 2) {
      score += 0.2;
    }
  }
  
  // Utility modules without tests
  score += analysis.utility_modules_without_tests.length * 0.15;
  
  // Deep indirection
  if (analysis.layers_of_indirection > 3) {
    score += (analysis.layers_of_indirection - 3) * 0.1;
  }
  
  return Math.min(1, score);
}
```

---

## 11. Integration with Governor

### 11.1 Regime Detection

```typescript
type CodeRegime = 'dev' | 'sre' | 'analysis';

function detectCodeRegime(context: CodeContext): CodeRegime {
  if (context.is_infrastructure_change) return 'sre';
  if (context.is_incident_response) return 'sre';
  if (context.is_config_change) return 'sre';
  if (context.is_analysis_script) return 'analysis';
  return 'dev';
}
```

### 11.2 Universal Invariant Split

The governor's universal invariant layer splits based on domain:

```typescript
function applyUniversalInvariant(
  output: string,
  domain: 'prose' | 'code'
): InvariantResult {
  if (domain === 'prose') {
    // Governance must be INVISIBLE
    return checkGovernanceInvisibility(output);
  } else {
    // Governance must be VISIBLE and LOCAL
    return checkGovernanceLocality(output);
  }
}
```

### 11.3 Retry Loop Difference

**Critical**: In dev/SRE, the retry loop should be **structural augmentation**, not rephrasing.

```typescript
interface RetryStrategy {
  prose: 'rephrase' | 'restructure';
  code: 'add_contracts' | 'add_tests' | 'add_bounds' | 'add_rollback';
}

function getRetryStrategy(domain: 'prose' | 'code', failure: FailureType): string {
  if (domain === 'prose') {
    return 'rephrase';  // Change how it's said
  }
  
  // Code: Add structural elements
  switch (failure) {
    case 'low_Ap': return 'add_ownership_and_bounds';
    case 'low_Ip': return 'add_contracts_and_validation';
    case 'low_Fp': return 'add_error_taxonomy_and_handlers';
    case 'premature_abstraction': return 'inline_and_simplify';
    default: return 'add_tests';
  }
}
```

---

## 12. Interface

### 12.1 Input

```typescript
interface CodeControllerInput {
  code: string;
  context: CodeContext;
  regime: CodeRegime;
  repo_conventions?: RepoConventions;
  existing_tests?: string[];
  existing_invariants?: string[];
}

interface CodeContext {
  is_infrastructure_change: boolean;
  is_incident_response: boolean;
  is_config_change: boolean;
  is_analysis_script: boolean;
  touched_files: string[];
  runtime_criticality: 'low' | 'medium' | 'high' | 'critical';
}
```

### 12.2 Output

```typescript
interface CodeControllerOutput {
  code: string;                    // potentially augmented
  passed_gates: boolean;
  custody_score: number;
  
  scores: {
    Ap: number;
    Ip: number;
    Fp: number;
  };
  
  violations: CodeViolation[];
  augmentations_applied: string[];
  
  telemetry: CodeTelemetry;
}

interface CodeViolation {
  type: 'accountability' | 'invariant' | 'failure' | 'abstraction' | 'magic';
  location: string;
  severity: number;
  suggestion: string;
}

interface CodeTelemetry {
  invariants_added_vs_enforced: number;
  exception_boundary_width: number;
  diff_complexity: number;
  new_concept_count: number;
  magic_behavior_score: number;
  exception_smear_score: number;
  premature_abstraction_score: number;
}
```

---

## 13. Metrics (Internal Only)

### 13.1 Core Metrics

| Metric | Formula | Healthy Range |
|--------|---------|---------------|
| `custody_score_mean` | Average custody score | > 0.6 |
| `gate_pass_rate` | Outputs passing all gates | > 0.8 |
| `Ap_mean` | Average accountability clarity | > 0.6 |
| `Ip_mean` | Average invariant coupling | > 0.5 |
| `Fp_mean` | Average failure explicitness | > 0.5 |
| `magic_behavior_rate` | Magic detections per output | < 0.2 |
| `exception_smear_rate` | Smeared exceptions per output | < 0.2 |

### 13.2 Diagnostic Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `LOW_AP` | Accountability unclear | Add ownership, bounds, assumptions |
| `LOW_IP` | Invariants not enforced | Add validation, types, assertions |
| `LOW_FP` | Failure modes hidden | Add error taxonomy, explicit handlers |
| `HIGH_MAGIC` | Too much implicit behavior | Make config/state explicit |
| `HIGH_SMEAR` | Exceptions being swallowed | Tighten catch boundaries |
| `PREMATURE_ABSTRACTION` | Generalizing too early | Inline, simplify, wait for uses |

---

## 14. The Punchline

### 14.1 Same Goal, Different Sign

In prose, your governor prevents **performative authority**.
In dev/SRE, it prevents **unowned liability**.

**Same meta-goal**: Constrain bullshit.

**Different sign**:
- Prose: suppress governance signals
- Code: surface governance contracts

### 14.2 The Test

If you implement just one thing first:

**Implement Aₚ scoring + gates that force**:
- Explicit invariants
- Explicit failure modes
- Explicit rollback paths

That alone will make "AI code" stop feeling like a confident stranger borrowing your pager.

### 14.3 Why This Matters

The unifying principle across prose and code:

> **Language earns trust when it makes the cost of being wrong legible to the reader.**

In prose: expose epistemic risk, hide governance.
In code: expose operational risk, surface governance.

Same math. Different sign. Same governor architecture, different constraints.

---

## 15. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |

---

*"Prose hides governance to preserve trust. Code surfaces governance to preserve custody."*

*"An invariant that isn't enforced is narrative. Narrative is for postmortems, not production."*

*"Prefer loud, local failure over quiet, smeared failure."*

*"Language earns trust when it makes the cost of being wrong legible to the reader."*
