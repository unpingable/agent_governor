# Ticketing / Issue Instantiation Layer Specification

## Version 0.1 — Making Failures First-Class Citizens

### Companion to: Authorial Control System, Code/SRE Controller, Structural Constraints

---

## Executive Summary

Ticketing is the **shared abstraction between discourse and code**. It transforms governance failures, trust collapses, and constraint violations from vibes into **explicit, trackable objects**.

**Core Insight**: If something keeps failing but we never instantiate it as an object, the system can't learn.

**Design Principle**: No correction without a ticket. If it isn't worth naming, it isn't worth fixing.

**Default State**: Disabled. Ticketing is infrastructure, not mandatory process. Enable when accountability tracking, learning loops, or cross-session memory matter.

---

## 1. What Ticketing Is (In This Architecture)

### 1.1 Not Task Management

This is not "Jira for bugs."

This is:

> **Turning discourse failures, trust collapses, or governance violations into explicit, trackable objects** instead of vibes, arguments, or recursive debate.

**Epistemic tickets**, not task tickets.

### 1.2 Why It Exists

Problems ticketing solves:
- Endless argument with no convergence
- Repeated failure modes with no memory
- No record of *why* something failed last time
- Governance violations that get re-argued instead of referenced
- Discourse loops where the same ill-typed move recurs forever

The insight:

> If something keeps failing, but we never instantiate it as an object, the system can't learn.

### 1.3 The Unifying Abstraction

| Domain | What a Ticket Represents |
|--------|-------------------------|
| Prose/Discourse | Governance leak, regime collision, premature closure, constraint violation |
| Code/SRE | Unowned liability, missing invariant, scope violation, rollback gap |

Same object. Different regimes.

---

## 2. Architecture Placement

### 2.1 Pipeline Position

Ticketing sits **after detection, before correction**:

```
Signal detected
      ↓
Constraint / regime / custody violation identified
      ↓
┌─────────────────────────────────────────┐
│     TICKETING LAYER (if enabled)        │
│                                         │
│  • Instantiate violation as ticket      │
│  • Classify type                        │
│  • Capture context slice                │
│  • Record reproduction hint             │
│  • Link to prior tickets if recurring   │
│                                         │
└─────────────────────────────────────────┘
      ↓
Routing decision
      ↓
┌─────────────┬─────────────┬─────────────┐
│  Suppress   │   Adjust    │  Escalate   │
│  output     │  controller │  to human   │
└─────────────┴─────────────┴─────────────┘
```

### 2.2 Enable/Disable Toggle

```typescript
interface TicketingConfig {
  enabled: boolean;              // default: false
  auto_create: boolean;          // create tickets automatically on violation
  require_ticket_for_fix: boolean; // no correction without ticket
  link_recurring: boolean;       // detect and link similar violations
  retention_policy: 'session' | 'persistent' | 'ephemeral';
}

const DEFAULT_TICKETING_CONFIG: TicketingConfig = {
  enabled: false,
  auto_create: true,
  require_ticket_for_fix: true,
  link_recurring: true,
  retention_policy: 'session',
};
```

### 2.3 When to Enable

| Context | Enable Ticketing? |
|---------|-------------------|
| Casual conversation | No |
| Single-shot generation | No |
| Iterative refinement | Maybe |
| Long-running project | Yes |
| Code generation with review | Yes |
| SRE/incident context | Yes |
| Learning/improvement loops | Yes |
| Cross-session memory needed | Yes |

---

## 3. Ticket Structure

### 3.1 Core Schema

```typescript
interface Ticket {
  // Identity
  id: string;                    // unique identifier
  created_at: timestamp;
  updated_at: timestamp;
  
  // Classification
  type: TicketType;
  regime: string;                // which regime was active
  domain: 'prose' | 'code';
  severity: 'info' | 'warning' | 'violation' | 'critical';
  
  // Content
  violated_invariant: string;    // which rule was broken
  description: string;           // human-readable summary
  context_slice: string;         // relevant portion of input/output
  reproduction_hint?: string;    // how to trigger this again
  
  // Relationships
  parent_ticket?: string;        // if this is a recurrence
  related_tickets: string[];     // similar violations
  
  // Resolution
  status: 'open' | 'acknowledged' | 'fixed' | 'wont_fix' | 'duplicate';
  resolution?: string;           // how it was resolved
  closed_at?: timestamp;
  
  // Metadata
  tags: string[];
  source: 'auto' | 'manual';
}
```

### 3.2 Ticket Types

#### Prose/Discourse Types

```typescript
type ProseTicketType =
  | 'GOV_VISIBILITY_LEAK'      // governance showed in-band
  | 'REGIME_COLLISION'         // incompatible regimes active
  | 'PREMATURE_CLOSURE'        // synthesis before constraint surface
  | 'TONE_GOVERNANCE_LEAK'     // fear leaked through tone
  | 'COMMITMENT_VIOLATION'     // asked for more than earned
  | 'AUDIENCE_MISMATCH'        // wrong model of reader
  | 'EXIT_SHAPE_VIOLATION'     // bad ending pattern
  | 'PHASE_LOCK_FAILURE'       // timing window missed
  | 'UNJUSTIFIED_NORMATIVITY'  // should/must without foundation
  | 'TYPE_ERROR'               // category mismatch in discourse
  | 'AUTHORITY_MISMATCH'       // claimed vs demonstrated authority
  | 'REPETITION_VIOLATION'     // wrong repetition for regime
  | 'LEGIBILITY_OVERRUN'       // spent budget on unrequested explanation
  | 'META_INVARIANT_VIOLATION';// solved problem reader hadn't felt
```

#### Code/SRE Types

```typescript
type CodeTicketType =
  | 'UNOWNED_LIABILITY'        // accountability unclear
  | 'MISSING_INVARIANT'        // constraint not enforced
  | 'HIDDEN_GOVERNANCE'        // constraints not visible/local
  | 'FAILURE_SURFACE_HIDDEN'   // error handling smeared
  | 'PREMATURE_ABSTRACTION'    // generalized before concrete uses
  | 'MAGIC_BEHAVIOR'           // implicit config/state
  | 'EXCEPTION_SMEAR'          // broad catch, swallowed errors
  | 'SCOPE_VIOLATION'          // output exceeds ticket scope
  | 'ROLLBACK_GAP'             // no rollback path defined
  | 'OBSERVABILITY_GAP'        // no signals for failure mode
  | 'PHASE_LOCK_FAILURE';      // observability→mitigation timing broken
```

#### Combined Type

```typescript
type TicketType = ProseTicketType | CodeTicketType;
```

---

## 4. Ticket Creation

### 4.1 Automatic Creation

When a violation is detected and ticketing is enabled:

```typescript
interface ViolationDetection {
  type: TicketType;
  regime: string;
  domain: 'prose' | 'code';
  invariant: string;
  context: string;
  severity: number;
}

function createTicketFromViolation(
  detection: ViolationDetection,
  config: TicketingConfig
): Ticket | null {
  
  if (!config.enabled) return null;
  if (!config.auto_create) return null;
  
  // Check for duplicates/recurrences
  const similar = findSimilarTickets(detection);
  
  const ticket: Ticket = {
    id: generateId(),
    created_at: now(),
    updated_at: now(),
    
    type: detection.type,
    regime: detection.regime,
    domain: detection.domain,
    severity: mapSeverity(detection.severity),
    
    violated_invariant: detection.invariant,
    description: generateDescription(detection),
    context_slice: truncateContext(detection.context),
    reproduction_hint: generateReproHint(detection),
    
    parent_ticket: similar.length > 0 ? similar[0].id : undefined,
    related_tickets: similar.map(t => t.id),
    
    status: 'open',
    tags: inferTags(detection),
    source: 'auto',
  };
  
  return ticket;
}
```

### 4.2 Manual Creation

For human-identified issues not caught by detection:

```typescript
interface ManualTicketInput {
  type: TicketType;
  description: string;
  context?: string;
  tags?: string[];
}

function createManualTicket(
  input: ManualTicketInput,
  context: ConversationContext
): Ticket {
  return {
    id: generateId(),
    created_at: now(),
    updated_at: now(),
    
    type: input.type,
    regime: context.current_regime,
    domain: context.domain,
    severity: 'warning',  // manual tickets default to warning
    
    violated_invariant: 'manual_report',
    description: input.description,
    context_slice: input.context || '',
    
    parent_ticket: undefined,
    related_tickets: [],
    
    status: 'open',
    tags: input.tags || [],
    source: 'manual',
  };
}
```

---

## 5. Ticket Routing

### 5.1 Routing Rules

Once a ticket is created, the system decides what to do:

```typescript
type RoutingAction = 
  | { action: 'suppress'; reason: string }
  | { action: 'adjust'; adjustment: ControllerAdjustment }
  | { action: 'escalate'; to: 'human' | 'review_queue' }
  | { action: 'log'; for: 'learning' | 'audit' }
  | { action: 'retry'; with: RetryStrategy };

function routeTicket(ticket: Ticket): RoutingAction {
  
  // Critical violations always escalate
  if (ticket.severity === 'critical') {
    return { action: 'escalate', to: 'human' };
  }
  
  // Recurring violations escalate
  if (ticket.parent_ticket && countRecurrences(ticket) > 3) {
    return { action: 'escalate', to: 'review_queue' };
  }
  
  // Known fixable violations get auto-adjustment
  if (hasAutoFix(ticket.type)) {
    return { action: 'adjust', adjustment: getAutoFix(ticket.type) };
  }
  
  // Default: suppress and log
  return { action: 'log', for: 'learning' };
}
```

### 5.2 Routing by Type

| Ticket Type | Default Route |
|-------------|---------------|
| `GOV_VISIBILITY_LEAK` | Adjust (suppress governance markers) |
| `REGIME_COLLISION` | Adjust (enforce dominant regime) |
| `PREMATURE_CLOSURE` | Adjust (delay synthesis) |
| `TONE_GOVERNANCE_LEAK` | Adjust (filter institutional markers) |
| `UNOWNED_LIABILITY` | Escalate (needs human ownership decision) |
| `MISSING_INVARIANT` | Retry (add enforcement) |
| `SCOPE_VIOLATION` | Suppress (out of scope) |
| `ROLLBACK_GAP` | Escalate (needs human review) |

---

## 6. The Key Rule

> **No correction without a ticket.**

If ticketing is enabled with `require_ticket_for_fix: true`:

```typescript
function attemptCorrection(
  violation: ViolationDetection,
  config: TicketingConfig
): CorrectionResult {
  
  if (config.enabled && config.require_ticket_for_fix) {
    const ticket = createTicketFromViolation(violation, config);
    
    if (!ticket) {
      // Can't create ticket = can't fix
      return { 
        corrected: false, 
        reason: 'ticketing_required_but_failed' 
      };
    }
    
    // Correction is now linked to ticket
    return applyCorrection(violation, ticket);
  }
  
  // Ticketing disabled: fix without record
  return applyCorrection(violation, null);
}
```

**Why this matters**: It prevents the system from silently "fixing" things without accountability. Every fix has a trail.

---

## 7. Recurrence Detection

### 7.1 Why It Matters

The same ill-typed move recurring forever is discourse death. Ticketing breaks the loop:

> *"We already rang the bell for this. Here's the ticket."*

### 7.2 Similarity Matching

```typescript
interface SimilaritySignals {
  same_type: boolean;
  same_regime: boolean;
  same_invariant: boolean;
  context_similarity: number;  // 0.0 - 1.0
  time_proximity: number;      // closer = more likely related
}

function findSimilarTickets(
  detection: ViolationDetection,
  history: Ticket[]
): Ticket[] {
  
  return history
    .filter(t => t.status !== 'fixed')
    .map(t => ({
      ticket: t,
      similarity: calculateSimilarity(detection, t)
    }))
    .filter(({ similarity }) => similarity > 0.7)
    .sort((a, b) => b.similarity - a.similarity)
    .map(({ ticket }) => ticket);
}

function calculateSimilarity(
  detection: ViolationDetection,
  ticket: Ticket
): number {
  let score = 0;
  
  if (detection.type === ticket.type) score += 0.4;
  if (detection.regime === ticket.regime) score += 0.2;
  if (detection.invariant === ticket.violated_invariant) score += 0.3;
  
  // Context similarity (simplified)
  const contextSim = jaccard(
    tokenize(detection.context),
    tokenize(ticket.context_slice)
  );
  score += contextSim * 0.1;
  
  return score;
}
```

### 7.3 Recurrence Escalation

```typescript
function checkRecurrenceEscalation(ticket: Ticket): boolean {
  const recurrenceCount = countRecurrences(ticket);
  
  // Thresholds by severity
  const thresholds = {
    info: 10,
    warning: 5,
    violation: 3,
    critical: 1,
  };
  
  return recurrenceCount >= thresholds[ticket.severity];
}
```

---

## 8. Integration with Code/SRE

### 8.1 Ticket as Accountability Source

In the Code/SRE controller, tickets provide Aₚ signals:

```typescript
interface TicketContext {
  id: string;
  owner: string;
  scope: string;
  acceptance_criteria: string[];
  rollback_path?: string;
  risk_assessment?: string;
  linked_systems: string[];
}

function extractApSignalsFromTicket(
  ticket: TicketContext
): Partial<AccountabilitySignals> {
  return {
    ownership_explicit: !!ticket.owner,
    assumptions_stated: ticket.acceptance_criteria.length > 0,
    // ... derived from ticket metadata
  };
}
```

### 8.2 Scope Validation

```typescript
function validateOutputAgainstTicket(
  output: string,
  ticket: TicketContext
): ScopeValidation {
  
  // Check if output stays within ticket scope
  const scopeViolations = detectScopeCreep(output, ticket.scope);
  
  // Check if acceptance criteria are addressed
  const criteriaGaps = findUnaddressedCriteria(
    output, 
    ticket.acceptance_criteria
  );
  
  return {
    in_scope: scopeViolations.length === 0,
    criteria_met: criteriaGaps.length === 0,
    violations: scopeViolations,
    gaps: criteriaGaps,
  };
}
```

### 8.3 Traceability

Every code output can link back to its authorizing ticket:

```typescript
interface CodeOutput {
  code: string;
  ticket_id?: string;           // if ticketing enabled
  accountability_source: 'ticket' | 'context' | 'none';
}
```

---

## 9. Ticket Lifecycle

### 9.1 States

```
┌────────┐
│  open  │ ← created
└────┬───┘
     │
     ▼
┌──────────────┐
│ acknowledged │ ← human saw it
└──────┬───────┘
       │
       ├─────────────────┬──────────────────┐
       ▼                 ▼                  ▼
┌───────────┐     ┌───────────┐     ┌───────────┐
│   fixed   │     │ wont_fix  │     │ duplicate │
└───────────┘     └───────────┘     └───────────┘
```

### 9.2 Transitions

```typescript
type TicketTransition = {
  from: TicketStatus;
  to: TicketStatus;
  requires: 'auto' | 'human';
  side_effects?: () => void;
};

const ALLOWED_TRANSITIONS: TicketTransition[] = [
  { from: 'open', to: 'acknowledged', requires: 'human' },
  { from: 'open', to: 'fixed', requires: 'auto' },
  { from: 'open', to: 'duplicate', requires: 'auto' },
  { from: 'acknowledged', to: 'fixed', requires: 'auto' },
  { from: 'acknowledged', to: 'wont_fix', requires: 'human' },
  { from: 'acknowledged', to: 'duplicate', requires: 'auto' },
];
```

---

## 10. Learning Loops

### 10.1 What Tickets Enable

Closed tickets become learning data:

```typescript
interface LearningSignal {
  ticket_type: TicketType;
  regime: string;
  resolution: string;
  recurrence_count: number;
  time_to_fix: number;
  effective: boolean;  // did the fix prevent recurrence?
}

function extractLearningSignals(
  closedTickets: Ticket[]
): LearningSignal[] {
  return closedTickets
    .filter(t => t.status === 'fixed')
    .map(t => ({
      ticket_type: t.type,
      regime: t.regime,
      resolution: t.resolution || '',
      recurrence_count: countRecurrences(t),
      time_to_fix: t.closed_at - t.created_at,
      effective: !hasRecurredAfterFix(t),
    }));
}
```

### 10.2 Pattern Detection

Over time, tickets reveal:
- Which violations recur most
- Which fixes are effective
- Which regimes have the most collisions
- Where the spec has gaps

This is how the system improves without re-arguing.

---

## 11. Interface

### 11.1 Ticketing Layer Input

```typescript
interface TicketingLayerInput {
  violation: ViolationDetection | null;
  context: ConversationContext;
  config: TicketingConfig;
  history: Ticket[];
}
```

### 11.2 Ticketing Layer Output

```typescript
interface TicketingLayerOutput {
  ticket_created: boolean;
  ticket?: Ticket;
  routing: RoutingAction;
  similar_tickets: Ticket[];
  recurrence_detected: boolean;
}
```

---

## 12. Metrics (When Enabled)

| Metric | What It Measures |
|--------|------------------|
| `tickets_created_per_session` | Volume of violations |
| `recurrence_rate` | How often same issue returns |
| `mean_time_to_fix` | How quickly violations resolve |
| `fix_effectiveness` | Do fixes prevent recurrence? |
| `escalation_rate` | How often humans needed |
| `top_violation_types` | Where the system struggles |

---

## 13. The Punchline

### 13.1 What Ticketing Does

Ticketing makes governance failures **first-class citizens**:

- Finite (has an ID)
- Inspectable (has context)
- Comparable (has type)
- Closeable (has resolution)

That alone kills 70% of discourse loops.

### 13.2 Why Disabled by Default

Ticketing is infrastructure, not process. It adds overhead. Only enable when:
- Accountability matters
- Learning matters
- Cross-session memory matters
- You're tired of re-arguing the same failures

### 13.3 The Invariant

> *"We already rang the bell for this. Here's the ticket."*

No more recursive debate. No more vibes. No more "but what about—"

The ticket exists. Reference it or close it.

---

## 14. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-02 | Initial spec |

---

*"If something keeps failing, but we never instantiate it as an object, the system can't learn."*

*"No correction without a ticket. If it isn't worth naming, it isn't worth fixing."*

*"We already rang the bell for this. Here's the ticket."*
