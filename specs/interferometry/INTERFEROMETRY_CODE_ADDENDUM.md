# Code Interferometry Addendum

## Version 0.1 — Instrumentation, Not Selection

### Addendum to: INTERFEROMETRY_SPEC.md
### Referenced by: docs/reference/WEBUI_UX_SPEC.md

---

## 0. Scope

Code interferometry is **instrumentation, not selection**.

The "best" output is already adjudicated by tests/types/build. The oracle exists. Interferometry exists to surface what the oracle can't catch:

- **Security footguns** one model spots and others miss
- **Edge-case coverage gaps** in error handling, boundaries, concurrency
- **Architectural drift** against recorded decisions and constraints
- **Candidate diversity** when you're stuck and need different approaches

**The rule:** Any "winner" UX language is forbidden. The UI can show "most compatible with decisions" or "lowest risk markers" but never "best."

---

## 1. Design Principle: Progressive Disclosure

Left alone, this will collapse into "neat but unused." The fix is: **the easiest path already uses interferometry, and the advanced stuff is there when needed, not up front.**

### The Litmus Test

> "If I were slightly tired and slightly annoyed, would I still let this run?"

If yes, you're fine. You're not building a cockpit. You're building a check engine light that sometimes opens the hood.

### Tier 0: Invisible (Default)

For single-model or low-risk code paths:

- User hits "Generate"
- System **may silently run N models** in background
- User sees:
  - The chosen patch
  - Inline warnings if any model raised a marker
  - Normal test results
- No compare UI. No session. No ceremony.

**Interferometry is already running — but hidden.**

This is critical. If the default experience adds friction, it dies.

### Tier 1: "Something Smells" (Auto-Triggered)

Triggered automatically when:
- `divergence_entropy` > threshold
- Risk marker union is non-empty
- Anchor conflict detected
- Tests fail inconsistently across runs

User sees:

```
⚠️ Models disagreed in 3 places. One flagged a security risk.
[View Details]
```

Click → opens Compare Session, **landing on Markers, not diffs.**

This feels like:
- Compiler warnings
- Static analysis
- Linter nags

Not "advanced research tooling."

### Tier 2: "I Want Options" (Explicit)

User intentionally requests it:
- "Show alternatives"
- "Compare approaches"
- Command palette: "Run Compare"

Now they get:
- Full structural diff
- Merge workspace
- Novelty tags
- Candidate diversity analysis

This is when the user is already slow-thinking. They asked for depth.

---

## 2. Core Objects

### ModelRun

```typescript
interface ModelRun {
  model_id: string;
  prompt_id: string;
  context_fingerprint: string;  // hash of anchors + repo state
  output_artifact: Artifact;
  tooling_results?: {           // optional preflight
    format: PassFail;
    lint: PassFail;
    static_scan: ScanResult;
  };
  notes?: string;               // model self-report, UNTRUSTED
}
```

### Artifact

```typescript
interface Artifact {
  kind: 'patch' | 'file_tree' | 'snippet';
  files: {
    path: string;
    content?: string;
    diff?: string;    // unified diff
  }[];
  build_intent: 'edit_existing' | 'new_feature' | 'refactor' | 'fix_bug';
}
```

### DivergenceReport

```typescript
interface DivergenceReport {
  // Structural
  structural_divergence: StructuralDiff[];
  
  // Risk
  security_markers: RiskMarker[];
  edge_case_markers: RiskMarker[];
  
  // Architecture
  anchor_conflicts: AnchorConflict[];
  
  // Coverage
  test_surface_delta: string[];  // what new tests/behavior implied
  
  // Diversity
  novelty_tags: string[];        // approach classification
  
  // Signals
  divergence_entropy: number;    // 0 = identical
  risk_marker_union: RiskMarker[];     // spotted by ANY model
  risk_marker_unique: Map<string, RiskMarker[]>;  // per-model uniques
}
```

---

## 3. Normalized Comparison

**Don't diff raw text.** Format-normalize first, then compare at two levels:

### Primary: Structural Diff

- Per-file change summaries
- Symbol-level changes (functions/classes touched)
- Dependency/import changes
- API contract shifts (signature/return type changes)

### Secondary: Textual Diff

- Unified diff for inspection
- Formatting-normalized (run formatter before diff where possible)

**Rule:** Structural diff is what users see first. Textual diff is for drilling down.

---

## 4. Risk Marker Extraction

This is where "divergence as signal" becomes real for code.

### Security Footgun Markers

| Marker | What It Catches |
|--------|-----------------|
| `SQL_INJECTION` | String concatenation in SQL, unparameterized queries |
| `SHELL_EXEC` | Shell execution without quoting/sanitization |
| `UNSAFE_DESER` | Unsafe deserialization of external input |
| `AUTH_BYPASS` | Auth/ACL bypass patterns |
| `INPUT_UNSANITIZED` | External input reaching sensitive sinks |
| `CRYPTO_MISUSE` | Homebrew crypto, insecure modes, weak algorithms |
| `SSRF_CANDIDATE` | URL construction from user input |
| `PATH_TRAVERSAL` | File path construction from user input |

### Edge-Case Markers

| Marker | What It Catches |
|--------|-----------------|
| `NULL_UNHANDLED` | Missing None/null handling vs other runs |
| `PARTIAL_ERROR` | One model catches exceptions, another doesn't |
| `BOUNDARY` | Off-by-one, empty list, zero-length conditions |
| `CONCURRENCY` | Different assumptions about locks, async ordering |
| `TIMEOUT_MISSING` | No timeout/retry/backoff where others have it |
| `RESOURCE_LEAK` | Unclosed handles, connections, files |

### Architectural Drift Markers

| Marker | What It Catches |
|--------|-----------------|
| `ANCHOR_VIOLATION` | Imports forbidden modules, bypasses service boundaries |
| `INTERFACE_BREAK` | Changes stable interfaces without migration |
| `NEW_COUPLING` | Introduces new dependency edge |
| `PATTERN_BYPASS` | Ignores existing patterns (bypasses factory, writes direct calls) |
| `DECISION_CONFLICT` | Contradicts recorded architectural decision |

---

## 5. Anchor Compatibility

**Anchors win. Always.**

Compute `anchor_conflicts` for each run:

| Conflict Type | Meaning | Consequence |
|---------------|---------|-------------|
| **Hard** | Violates invariant (forbidden coupling, security policy, "must not") | Cannot apply without explicit override + logged decision |
| **Soft** | Style/pattern divergence ("prefer," "should," consistency) | Warning, can apply freely |

**Hard conflict outputs can still be viewed** — divergent approaches have diagnostic value even when they can't be applied.

---

## 6. Adjudication Pipeline (Oracle-First)

Order matters:

```
1. Normalize output (format, minimal lint)
       ↓
2. Compare against anchors (conflicts)
       ↓
3. Run static checks (typecheck/lint/security scan)
       ↓
4. Run targeted tests (or full suite)
       ↓
5. Produce DivergenceReport + per-run risk profile
```

**Key point:** Tests/types are not the report. They're an input to divergence interpretation.

A run that passes tests but has unique security markers is still interesting.
A run that fails tests but spotted an edge case others missed is still valuable diagnostic data.

---

## 7. Convergence Telemetry

You're building a "conceptual spectrometer." Log the spectrum.

### Per Prompt/Session

| Metric | What It Measures |
|--------|------------------|
| `divergence_entropy` | How far outputs differ structurally (0 = identical) |
| `anchor_conflict_rate` | Per-run, hard vs soft |
| `risk_marker_union` | Markers spotted by at least one model (safety lift) |
| `risk_marker_disagreement` | Markers unique to one model (highest value) |
| `oracle_outcome` | Which outputs pass/fail tests/types and why |
| `decision_trace` | What user applied: single run, merge, or manual |

### Do Not Surface Numbers by Default

Surface:
- Plain language summaries
- Counts ("3 issues spotted by one model only")
- Simple labels ("high disagreement," "anchor conflict")

**Metrics are for tuning, not users.**

---

## 8. UX Contract

Any UI integration (WebUI, VS Code, CLI, CI) **must** support:

### Required

| Capability | What It Does |
|------------|--------------|
| **Run set** | Choose N models + settings per model |
| **Artifact view** | Structural diff + unified diff |
| **Markers view** | Risk markers + anchor conflicts with file/line references |
| **Oracle view** | Test/type/lint results per run |
| **Union lens** | Show "issues spotted by any model" — this IS instrumentation |
| **Apply with logging** | Every apply/override logged in ledger |

### Optional (Advanced)

| Capability | What It Does |
|------------|--------------|
| **Merge workspace** | Compose final patch from parts of multiple runs |
| **Novelty tags** | Classify approach diversity |
| **Telemetry dashboard** | View convergence metrics over time |

### Forbidden

| Anti-pattern | Why |
|--------------|-----|
| **"Winner" badge** | Interferometry is instrumentation, not selection |
| **Auto-apply "best"** | User always decides what to apply |
| **Hide disagreement** | The whole point is divergence as signal |

---

## 9. Apply Semantics

Applying code is a **separate step** from viewing.

### Default: Single-Run Apply

- User reviews the primary output (or Tier 1 warnings)
- Applies if oracle passes and no hard anchor conflicts

### Advanced: Merge Apply

- User opens merge workspace
- Picks run A for file X, run B for function Y
- Produces composite patch
- Oracle validates the composite

### Apply Gates

Apply is allowed only if:
- No hard anchor conflicts (or explicit override with logged decision)
- Oracle gate passes (or user explicitly bypasses with logging)

---

## 10. Failure Modes

| Failure Mode | What Happens | Guard |
|--------------|--------------|-------|
| **Selection collapse** | UI nudges user to pick "winner" and ignore union lens | Forbidden "best" language, markers-first landing |
| **Diff noise** | Formatting churn dominates the diff | Auto-format normalization before diffing |
| **Anchor bypass** | User creates "greenfield profile" to dodge invariants | Not allowed. Anchors apply to all runs. |
| **Overlogging** | Full proprietary code stored in telemetry | Store hashes + structured summaries; full diffs local-only |
| **Tier 0 cost creep** | Silent multi-model runs burn API credits | Configurable: Tier 0 can use local models only, or be disabled |
| **Alert fatigue** | Too many "something smells" triggers | Tune thresholds based on decision_trace patterns |

---

## 11. WebUI Integration Notes

Add a **Compare** action in code-generation views:

- Runs N models → produces a "Compare Session"
- Tabs: **Markers** | Structure | Oracle | Diff | Merge
- **Default landing tab: Markers** (forces instrumentation-first)
- "Union lens" sidebar: "Spotted by any model" items pinned at top

### Tier 0 (Invisible)

- No UI change
- Inline warnings appear if background interferometry flagged something:

```
⚠️ Another model flagged: unchecked input at line 23
[Details]
```

### Tier 1 (Auto-Triggered)

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠️ Models disagreed on this change                         │
│                                                             │
│  3 structural differences                                   │
│  1 security marker (only Claude caught it)                  │
│  No anchor conflicts                                        │
│                                                             │
│  [View Compare Session] [Dismiss]                           │
└─────────────────────────────────────────────────────────────┘
```

### Tier 2 (Explicit)

Full compare session with all tabs. Merge workspace available.

---

## 12. VS Code Integration Notes

### Tier 0 (Invisible)

Inline markers only:

```
  8 │     return db.execute(f"SELECT * FROM {table}")
    │     
    │     ⚠️ Another model flagged: possible SQL injection
    │     [Details]
```

No compare UI. No extra buttons. Just warnings.

### Tier 1 (Auto-Triggered)

Notification:

```
⚠️ Models disagreed in 3 places. One flagged a security risk.
[Open Compare] [Dismiss]
```

Gutter indicators on divergent lines:

```
  5 │ ≠ def authenticate(user, token):     # models differ here
  6 │     if not verify_token(token):
  7 │ !     return None                     # risk marker
  8 │   return user
```

- **≠** lines where models diverge structurally
- **!** risk markers (any model)
- **⛔** hard anchor conflict (cannot apply without override)

### Tier 2 (Explicit)

Command palette:
- `Governor: Compare with Other Models`
- `Governor: Open Compare Session`
- `Governor: Apply from Run...`
- `Governor: Merge from Runs...`

Opens side-by-side view with structural diff and markers panel.

---

## 13. CLI Integration Notes

```bash
# Run interferometry on a task
governor code compare "Add authentication endpoint" \
  --models claude,ollama,gpt

# View divergence report
governor code compare --last

# View markers only (union lens)
governor code compare --last --markers

# Apply a specific run
governor code compare --last --apply run-2

# Merge from multiple runs
governor code compare --last --merge
```

### CI Integration

```yaml
# Run in CI for security-sensitive paths
- name: Multi-model security check
  run: |
    governor code compare "$PR_DESCRIPTION" \
      --models claude,ollama \
      --markers-only \
      --fail-on security
```

---

## 14. Configuration

```yaml
interferometry:
  # Tier 0: background runs
  background:
    enabled: true
    models: [ollama]           # cheap local model for background
    trigger: on_generate       # when AI generates code
  
  # Tier 1: auto-trigger thresholds
  auto_compare:
    divergence_threshold: 0.3  # entropy above this triggers Tier 1
    risk_markers: true         # any risk marker triggers Tier 1
    anchor_conflicts: true     # any anchor conflict triggers Tier 1
  
  # Tier 2: explicit compare
  explicit:
    models: [claude, ollama, gpt]
    default_tab: markers
  
  # Cost control
  cost:
    tier_0_models: [ollama]    # only local models for background
    tier_1_models: [ollama]    # local for auto-trigger
    tier_2_models: [claude, ollama, gpt]  # all models for explicit
    max_parallel: 3
    budget_per_day: null       # optional daily spend limit
```

---

## 15. What Makes People Actually Use This

1. **Markers inline, not in a panel** — Red underline for "model flagged risk." Hover → "Claude flagged unchecked input; GPT didn't."

2. **Union lens as default** — First thing users see: "Here's everything any model was worried about." That feels like free safety.

3. **Zero extra steps when things are easy** — If outputs converge and tests pass, nothing special happens. No new buttons.

4. **Compare opens only when justified** — Don't ask users to choose rigor. Detect when rigor is needed.

---

## 16. Three User Stories (Validation)

### Boring Refactor

1. User asks AI to rename a module
2. Tier 0 runs silently, models converge
3. User sees normal output, no warnings
4. Tests pass, applies

**Interferometry was invisible. Correct behavior.**

### Security-Sensitive Change

1. User asks AI to add authentication
2. Tier 0 catches: Ollama's version has no input sanitization
3. User sees inline warning: "⚠️ Another model flagged: unsanitized input on line 12"
4. User clicks, sees the specific difference
5. Adds sanitization, applies

**Interferometry caught a real issue. User barely noticed the machinery.**

### Architectural Crossroads

1. User asks AI "how should I structure the data layer?"
2. User explicitly runs Compare (Tier 2)
3. Claude suggests repository pattern, GPT suggests active record, Ollama suggests raw queries
4. User sees structural diff: three genuinely different approaches
5. Reviews against anchors: repository pattern aligns with existing decisions
6. Applies Claude's approach, notes the reasoning

**User explicitly asked for depth. Got it.**

---

## 17. The Single Best Behavior

If you implement only one thing:

> **Make Tier 0 + Tier 1 work seamlessly.**

Background interferometry with a cheap local model, surfacing inline warnings only when something smells.

That alone turns every code generation into a silently-audited event, with zero extra friction for the user.

The compare workspace, merge tools, and telemetry dashboard can come later. The invisible safety net comes first.

---

*"Interferometry is instrumentation, not selection."*

*"Any 'winner' UX language is forbidden."*

*"If I were slightly tired and slightly annoyed, would I still let this run?"*
