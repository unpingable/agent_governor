# Kernel Constraints Specification

## Version 0.2 — Minimum Viable Governance

### Companion to: Governor Voice Profile, Code/SRE Controller, Authorial Control System

---

## Executive Summary

The kernel constraints are the **non-negotiable invariants** that define what the governor is. Everything else — voice, UI, modes, integrations — is surface. This is the floor.

**What it is**: An evidence-gated coding harness. A structural hallucination brake. A claim validator for agent outputs.

**What it isn't**: A persona. A philosophy engine (even though it secretly is one). An "agent development environment."

**Tagline**: "Claims need evidence. Contradictions persist. Failures are loud."

---

## 1. Design Principle

### 1.1 Kernel, Not Surface

The kernel defines the constraints. Surfaces decide how to present them.

| Surface (Varies) | Kernel (Fixed) |
|-------------------|----------------|
| Voice/personality | Claim-evidence coupling |
| Tone envelope | Contradiction persistence |
| Regime detection | Accountability clarity |
| Ticketing layer | Failure surface explicitness |
| Journal integration | Governance locality |
| Footer conventions | |
| Domain affinities | |

Surfaces can be swapped, configured, disabled. Kernel constraints cannot.

### 1.2 The Adoption Path

Users adopt the kernel as a "linter for agent outputs" or "hallucination brake."

They don't need to understand:
- Governance invisibility theory
- Regime vectors
- Temporal consistency models
- The meta-invariant

They just see: claims get checked, contradictions persist, failures are explicit.

The philosophy is below the UX line. It works without being understood.

### 1.3 The Non-Negotiables

These constraints are **always active** — they're laws, not features:

1. **Claim-evidence coupling**: Claims require support
2. **Contradiction persistence**: Conflicts are recorded, not erased
3. **Accountability clarity**: Who owns this? What are the assumptions?
4. **Failure surface explicitness**: How does this fail?
5. **Governance locality**: Constraints are visible, not hidden

If these get disabled, it's not the governor anymore. It's just autocomplete.

---

## 2. What's Active

### 2.1 Kernel Constraints

```yaml
active_constraints:
  # From CODE_SRE_CONTROLLER
  - accountability_clarity      # Aₚ scoring
  - invariant_implementation_coupling  # Iₚ scoring  
  - failure_surface_explicitness  # Fₚ scoring
  - governance_locality         # constraints visible and local
  - complexity_rate_limit       # no premature abstraction
  
  # From STRUCTURAL_CONSTRAINTS
  - meta_invariant              # don't solve unfelt problems
  - exit_shape                  # no bad endings
  - temporal_consistency        # don't contradict yourself
  
  # From AUTHORIAL_CONTROL (universal only)
  - governance_invisibility     # don't leak the machinery
  - no_visible_negotiation      # no "on the one hand"
```

### 2.2 Scoring Functions

All scoring from CODE_SRE_CONTROLLER_SPEC applies:

```typescript
// Custody score must pass threshold
const KERNEL_CUSTODY_THRESHOLD = 0.5;

interface KernelCustodyCheck {
  Ap: number;  // accountability clarity
  Ip: number;  // invariant coupling
  Fp: number;  // failure explicitness
  
  passed: boolean;
  blocking_reasons: string[];
}
```

### 2.3 What Gets Blocked

| Condition | Action |
|-----------|--------|
| Claim without evidence | BLOCKED |
| Contradiction with prior output | WARN (recorded) |
| Accountability unclear | BLOCKED |
| Failure modes hidden | BLOCKED |
| Premature abstraction | WARN |
| Magic behavior detected | WARN |
| Exception smear detected | BLOCKED |

---

## 3. What Can Be Disabled

### 3.1 Surface Features (Configurable)

```yaml
configurable_features:
  - voice_profile         # governor voice, custom, or none
  - tone_modulation       # tone envelope
  - regime_detection      # beyond custody
  - ticketing_layer       # ticket creation
  - journal               # knowledge base
  - footer_conventions    # status footers
  - domain_deflections    # domain-specific refusals
  - drift_interruption    # conversation management
  - receipt_keeping       # cross-session history
```

### 3.2 Why These Are Optional

| Feature | Why Optional |
|---------|--------------|
| Voice profile | Adoption friction — some users don't want a "voice" |
| Tone modulation | Unnecessary for code — just be clear |
| Regime detection | Only custody matters for minimal use |
| Ticketing | Overhead — add if needed |
| Journal | Requires buy-in |
| Receipt keeping | Stateless is simpler for integration |

### 3.3 What Cannot Be Disabled

```yaml
permanent_constraints:
  - claim_evidence_coupling
  - contradiction_persistence
  - accountability_clarity
  - failure_surface_explicitness
  - governance_locality
```

These are the kernel. Disable them and you don't have a governor.

---

## 4. Interface

### 4.1 Input

```typescript
interface KernelInput {
  // Required
  task: string;              // what to do
  context: string;           // repo state, files, etc.
  
  // Optional
  constraints?: string[];    // additional constraints
  prior_claims?: Claim[];    // for contradiction checking
  strict?: boolean;          // fail closed (default: true)
}
```

### 4.2 Output

```typescript
interface KernelOutput {
  // The work
  patch?: string;            // code changes (if any)
  response?: string;         // explanation (if needed)
  
  // The accountability
  rationale: string;         // why this approach
  claims: Claim[];           // claims made, with evidence status
  citations: Citation[];     // sources referenced
  
  // The status
  status: 'OK' | 'BLOCKED' | 'WARN';
  blocking_reasons?: string[];
  warnings?: string[];
  
  // For contradiction tracking
  claim_ids: string[];       // IDs for future reference
}

interface Claim {
  id: string;
  text: string;
  level: 'SOFT' | 'HARD';
  evidence?: string;
  conflicts_with?: string[]; // prior claim IDs
}

interface Citation {
  source: string;
  relevance: string;
}
```

### 4.3 CLI Interface

```bash
# Basic usage
governor check --task "fix the null pointer in auth.py" --context ./src/

# With constraints
governor check --task "add caching" --constraint "no Redis" --context ./

# Strict mode (default)
governor check --strict --task "refactor" --context ./

# Output formats
governor check --format json --task "..." > output.json
governor check --format patch --task "..." > changes.patch
```

### 4.4 Log Format

JSONL for easy parsing:

```jsonl
{"timestamp": "2026-02-03T12:00:00Z", "event": "task_start", "task": "fix null pointer"}
{"timestamp": "2026-02-03T12:00:01Z", "event": "claim", "id": "c001", "text": "auth.py line 47 can receive None", "level": "HARD", "evidence": "traceback shows NoneType"}
{"timestamp": "2026-02-03T12:00:02Z", "event": "claim", "id": "c002", "text": "adding null check is safe", "level": "SOFT", "evidence": null}
{"timestamp": "2026-02-03T12:00:02Z", "event": "warn", "reason": "claim c002 lacks evidence", "claim_id": "c002"}
{"timestamp": "2026-02-03T12:00:03Z", "event": "output", "status": "WARN", "patch": "...", "warnings": ["claim c002 lacks evidence"]}
```

---

## 5. Minimal Status Output

### 5.1 Status Codes

| Status | Meaning |
|--------|---------|
| `OK` | Output passes all checks |
| `WARN` | Output produced, but with concerns |
| `BLOCKED` | Output suppressed, cannot proceed |

### 5.2 Blocking Reasons

```
BLOCKED: claim lacks evidence
BLOCKED: contradicts prior claim (c047)
BLOCKED: accountability unclear — who owns this?
BLOCKED: failure mode not specified
BLOCKED: exception handling too broad
```

### 5.3 Warning Reasons

```
WARN: claim c002 lacks evidence (SOFT, proceeding)
WARN: premature abstraction detected
WARN: magic behavior (implicit config)
WARN: conflicts with prior claim c047 (recorded)
```

---

## 6. Integration Patterns

### 6.1 Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

DIFF=$(git diff --cached)
RESULT=$(echo "$DIFF" | governor check --format json --task "review changes" --context .)

STATUS=$(echo "$RESULT" | jq -r '.status')

if [ "$STATUS" = "BLOCKED" ]; then
  echo "Commit blocked:"
  echo "$RESULT" | jq -r '.blocking_reasons[]'
  exit 1
fi

if [ "$STATUS" = "WARN" ]; then
  echo "Warnings:"
  echo "$RESULT" | jq -r '.warnings[]'
  # Allow commit but show warnings
fi

exit 0
```

### 6.2 CI Pipeline

```yaml
# .github/workflows/governor.yml
name: Governor Check

on: [pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Governor
        run: |
          DIFF=$(git diff origin/main)
          RESULT=$(echo "$DIFF" | governor check --format json --task "review PR" --context .)
          
          STATUS=$(echo "$RESULT" | jq -r '.status')
          
          if [ "$STATUS" = "BLOCKED" ]; then
            echo "::error::PR blocked by Governor"
            echo "$RESULT" | jq -r '.blocking_reasons[]'
            exit 1
          fi
```

### 6.3 Agent Wrapper

```python
# Wrap any agent with kernel validation

def governor_wrapper(agent_fn):
    def wrapped(task, context, **kwargs):
        # Get agent output
        output = agent_fn(task, context, **kwargs)
        
        # Validate with kernel
        result = governor.check(
            task=task,
            context=context,
            output=output,
            strict=True
        )
        
        if result.status == 'BLOCKED':
            raise BlockedError(result.blocking_reasons)
        
        # Attach claims for future contradiction checking
        output.claims = result.claims
        
        return output
    
    return wrapped
```

---

## 7. Configuration

### 7.1 Minimal Config

```yaml
# governor.config.yaml
version: "1.0"
mode: "strict"  # or "permissive"

# Thresholds
custody_threshold: 0.5
evidence_required_for_hard_claims: true
contradiction_action: "warn"  # or "block"
```

### 7.2 Strict Mode (Default)

```yaml
mode: "strict"

# In strict mode:
# - HARD claims without evidence → BLOCKED
# - Contradictions → BLOCKED  
# - Accountability unclear → BLOCKED
# - Broad exception handling → BLOCKED
```

### 7.3 Permissive Mode

```yaml
mode: "permissive"

# In permissive mode:
# - HARD claims without evidence → WARN
# - Contradictions → WARN (recorded)
# - Accountability unclear → WARN
# - Broad exception handling → WARN

# Still blocked:
# - Nothing passes through without logging
```

---

## 8. What Users See

### 8.1 The Pitch (Boring Version)

> "An evidence-gated coding harness. It validates that agent outputs have supporting evidence, tracks contradictions, and ensures failure modes are explicit. Think of it as a linter for agent reasoning."

### 8.2 The Experience

User runs their agent → agent produces code → governor checks it:

```
$ my-agent --task "add caching to user service" | governor check

OK: output validated
  - 3 claims made, all supported
  - no contradictions with prior outputs
  - failure modes documented
  - accountability clear

Patch ready: ./output.patch
```

Or:

```
$ my-agent --task "optimize database" | governor check

BLOCKED: claim lacks evidence
  - claim: "this index improves query performance by 10x"
  - required: benchmark data, query plan, or profiler output
  - to proceed: provide evidence or downgrade to SOFT claim

No output produced.
```

### 8.3 The Learning Moment

User asks: "Why did it block that?"

Answer is in the log:

```jsonl
{"event": "claim", "id": "c001", "text": "this index improves query performance by 10x", "level": "HARD", "evidence": null}
{"event": "blocked", "reason": "HARD claim without evidence", "claim_id": "c001"}
```

User realizes: the agent made a confident claim without support.

---

## 9. The Kernel Below

### 9.1 What's Actually Happening

The governor is a constraint layer over any agent output:

```
Agent Output
    ↓
┌─────────────────────────────────────┐
│           KERNEL                    │
│                                     │
│  • Claim extraction                 │
│  • Evidence linking                 │
│  • Contradiction detection          │
│  • Custody scoring (Aₚ, Iₚ, Fₚ)    │
│  • Promotion gates                  │
│  • Temporal consistency             │
│                                     │
└─────────────────────────────────────┘
    ↓
Status + Validated Output
```

### 9.2 The Kernel Is the Point

The kernel can be used directly as a library:

```python
from governor.kernel import (
    extract_claims,
    check_evidence,
    detect_contradictions,
    score_custody,
    check_promotion_gates
)

# Use directly in any system
claims = extract_claims(agent_output)
for claim in claims:
    if claim.level == 'HARD' and not check_evidence(claim):
        raise InsufficientEvidence(claim)
```

CLI, WebUI, VS Code, CI — these are all surfaces over the same kernel.

### 9.3 The Constraint That Matters

> **Contradiction persistence and evidence gating live below the UX line. The moment those become "features" rather than "laws," domestication begins.**

The kernel enforces this by not exposing its constraints as toggles.

You can disable the voice. You can disable ticketing. You can disable tone modulation.

You cannot disable evidence gating. You cannot disable contradiction persistence.

Those are the kernel.

---

## 10. Comparison

### 10.1 Kernel vs Full Governor

| Aspect | Kernel Only | Full Governor |
|--------|-------------|---------------|
| Voice | None | Configurable |
| Tone | None | Envelope-controlled |
| Footers | Bare status | Formatted |
| Regimes | Custody only | Full detection |
| Ticketing | Disabled | Available |
| Journal | None | Integration ready |
| Receipts | Stateless | Cross-session |
| Domains | Code only | Multiple modes |

### 10.2 Kernel vs "Just a Linter"

| Aspect | Kernel | Typical Linter |
|--------|--------|----------------|
| Checks syntax | No | Yes |
| Checks claims | Yes | No |
| Tracks contradictions | Yes | No |
| Requires evidence | Yes | No |
| Scores accountability | Yes | No |
| Stateful across runs | Optional | No |
| Understands agent reasoning | Yes | No |

---

## 11. The Non-Homer Test

The kernel exists to prove the system isn't The Homer:

1. ✅ **Runs in minimal mode** — no UI, no journal, still provides value
2. ✅ **Core invariants are library-usable** — kernel is importable
3. ✅ **Weird parts are opt-in** — voice, ticketing, tone are disabled by default

If you can ship the kernel standalone and it works, you didn't build The Homer.

---

## 12. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec (as "Maude Lite Profile") |
| 0.2 | 2026-02-05 | Renamed to Kernel Constraints Spec. Excised persona naming. Kernel is the kernel. |

---

*"Claims need evidence. Contradictions persist. Failures are loud."*

*"The kernel is the law. Everything else is surface."*

*"The moment constraints become 'features' rather than 'laws,' domestication begins."*
