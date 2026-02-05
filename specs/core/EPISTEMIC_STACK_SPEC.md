# Epistemic Stack Specification

## Version 1.0 — Claim Lifecycle and Governance Infrastructure

### Companion to: Authorial Control System, Kernel Constraints, Grounding Audit

---

## Executive Summary

The Epistemic Stack implements **claim-level governance**: provenance tracking, confidence modeling, multi-agent consensus, temporal decay, and hallucination detection. It provides the infrastructure that makes "Language is a proposal, not an authority" (NLAI) mechanically enforceable.

**Core Insight**: Hallucination is not "a bad answer" — it is a failed commit or a leak. The epistemic stack records HOW claims fail, and the governor tightens gates specifically against observed failure modes.

**Test Coverage**: ~983 tests across 11 modules (~10,200 lines).

---

## 1. Module Dependency Graph

```
                    epistemic.py (core)
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    claim_status.py  dissent.py      ttl.py
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
                    quorum.py
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
     audit.py       drift.py       strict.py
         │
         ▼
    research.py

    claim_diff.py ◄── epistemic.py (snapshot diffing)
    claim_signals.py ── (signal extraction, feeds epistemic)
```

---

## 2. The Claim Lifecycle

### 2.1 ClaimStatus FSM

```
PROPOSED ──(evidence attached)──→ SUPPORTED
    │                                │
    │                           ◄────┘
    │                                │
    └──(quorum rejects)──→ REFUSED   ▼
                              CONTESTED
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
         INVALIDATED       EXPIRED           STALE
         (counter-evidence) (TTL)           (decay)
```

**Terminal States**: REFUSED, INVALIDATED, EXPIRED — require HUMAN-only recovery.

### 2.2 Transition Rules (9 reasons)

| From | To | Reason |
|------|----|----|
| PROPOSED | SUPPORTED | EVIDENCE_ATTACHED |
| PROPOSED | REFUSED | QUORUM_REJECTED |
| SUPPORTED | CONTESTED | DISSENT_FILED |
| SUPPORTED | STALE | TTL_WARNING |
| CONTESTED | SUPPORTED | DISSENT_RESOLVED |
| CONTESTED | INVALIDATED | COUNTER_EVIDENCE |
| STALE | EXPIRED | TTL_EXPIRED |
| STALE | SUPPORTED | REVALIDATED |
| Any | INVALIDATED | CASCADE (dependency failed) |

---

## 3. Module Reference

### 3.1 epistemic.py (2,169 lines, 48 tests)

**Purpose**: Core provenance, confidence, and evidence tracking.

**Key Types**:

```python
class Provenance(str, Enum):
    """HOW claims were established (not just WHAT)."""
    OBSERVED = "observed"      # Direct observation (rare)
    RETRIEVED = "retrieved"    # Tool with trace (verifiable)
    USER_PROVIDED = "user_provided"  # Human input
    DERIVED = "derived"        # Inferred from other claims
    PEER_ASSERTED = "peer_asserted"  # From another agent
    ASSUMED = "assumed"        # Hypothetical (lowest trust)

class EvidenceType(str, Enum):
    TOOL_TRACE = "tool_trace"
    URL = "url"
    DOCUMENT = "document"
    HUMAN_INPUT = "human_input"
    RECEIPT = "receipt"
    # Extended types
    SENSOR_DATA = "sensor_data"
    CRYPTOGRAPHIC_PROOF = "cryptographic_proof"
    SUBJECTIVE_REPORT = "subjective_report"
    NARRATIVE_CONSISTENCY = "narrative_consistency"

@dataclass
class GroundedClaim:
    """A claim with provenance, confidence, and evidence."""
    id: str
    content: str
    provenance: Provenance
    confidence: float  # [0.0, 1.0]
    evidence_refs: list[EvidenceRef]
    depends_on: list[str]  # Claim IDs (DAG)
    status: ClaimStatus
    created_at: datetime
    verified_at: datetime | None
```

**Key Invariants**:
1. Provenance NEVER upgrades without evidence
2. Confidence can ONLY increase with evidence (not repetition/elaboration/peer agreement)
3. PEER_ASSERTED claims start low confidence, cannot increase without evidence

**EpistemicLedger**: SQLite-backed persistence (Schema V5) with write-through on mutations.

---

### 3.2 claim_status.py (330 lines, 39 tests)

**Purpose**: Weather report for claim health — at-a-glance epistemic state.

**Key Types**:

```python
@dataclass
class ClaimStatusSummary:
    """High-level claim health."""
    live_count: int
    live_confidence_avg: float
    degrading_count: int    # confidence 0.5-0.8
    stale_count: int        # confidence < 0.5
    contested_count: int    # awaiting ruling
    health_score: float     # 0-100, penalizes stale/contested

@dataclass
class ClaimDetail:
    """Detailed view of single claim."""
    claim_id: str
    content: str
    status: str
    confidence: float
    provenance: str
    freshness_remaining: timedelta | None
    evidence_summary: str
    depends_on: list[str]
```

---

### 3.3 quorum.py (1,164 lines, 119 tests)

**Purpose**: Multi-agent consensus protocol with Δt stability windows.

**State Machine**:

```
COLLECTING ──(threshold met)──→ STABILIZING
STABILIZING ──(Δt elapsed)──→ REACHED
STABILIZING ──(new REJECT)──→ COLLECTING (reset clock)
REACHED ──(dissent filed)──→ CONTESTED
CONTESTED ──(resolved)──→ RESOLVED_COMMIT | RESOLVED_REJECT
CONTESTED ──(stuck)──→ ESCALATED
COLLECTING ──(timeout)──→ FAILED
REACHED ──(TTL expired)──→ EXPIRED
```

**Claim Types with Δt Budgets**:

| Type | Δt | Min Voters (k) | Notes |
|------|-----|----------------|-------|
| MATH | Short | 2 | Fast consensus |
| CODE | Short | 2 | Quick consensus |
| STATIC_FACT | Medium | 3 | Stable facts |
| VOLATILE_FACT | Long | 4 | Time-sensitive |
| PROCEDURE | Long | 5 | High stakes |
| JUDGMENT | Longest | Human | Value judgments |

**Risk Multipliers**: LOW (×1.0), MEDIUM (×1.5), HIGH (×2.0) — scales effective Δt.

**8 Gates**:
1. Minimum voters (k)
2. Approval threshold
3. Δt stability window
4. TTL not expired
5. Sybil resistance (effective voter count)
6. Evidence type validation
7. Premise rule (no HARD on SOFT/STALE)
8. Agent role budgets

**Agent Roles**:
- PROPOSER: Creates claim + rationale
- RETRIEVER: Gathers corroborating evidence
- FALSIFIER: Attempts disconfirmation
- SYNTHESIZER: Produces final statement with uncertainty

---

### 3.4 ttl.py (699 lines, 45 tests)

**Purpose**: Recency decay and temporal validity enforcement.

**Volatility Classes**:

| Class | TTL | Decay Rate | Example |
|-------|-----|------------|---------|
| PERMANENT | ∞ | 0% | Mathematical facts, arch decisions |
| STABLE | 30 days | 5%/week | Library versions, API contracts |
| MODERATE | 7 days | 10%/day | Test results, build status |
| VOLATILE | 1 hour | 20%/hour | Runtime metrics, live API |
| EPHEMERAL | 5 min | 50%/min | Cache values, session state |

**Decay Actions**:
- NONE: Still fresh
- DEGRADE: Reduce confidence (stale but not retracted)
- RETRACT: Auto-retract (too old to trust)

**Key Classes**:
- `TTLPolicy` — Configuration per volatility class
- `TTLManager` — Tracks expiry, schedules revalidation
- `RevalidationScheduler` — Produces schedule of claims needing re-check

---

### 3.5 dissent.py (483 lines, 59 tests)

**Purpose**: Contradiction persistence — dissent as first-class state.

**Core Principle**: Objections are structural signals, not noise. They are never silently discarded.

**Objection Severity**:
- LOW: Minor concern — does not block
- MEDIUM: Significant — flags for review
- HIGH: Critical — blocks commit if evidence attached
- CRITICAL: Must resolve before progress — always blocks

**Objection Status**:
- OPEN → ACCEPTED | DISMISSED | ESCALATED | SUPERSEDED

**Block Verdicts**:
- BLOCKS: Hard block — cannot proceed
- FLAGS: Soft flag — proceed with caution
- CLEAR: Resolved or insufficient severity

**Key Classes**:
- `Objection` — First-class disagreement record
- `DissentLedger` — Stores objections, tracks confidence trajectories
- `EvidencePointer` — Lightweight evidence reference

---

### 3.6 audit.py (1,295 lines, 164 tests)

**Purpose**: Grounding audit pipeline — closed-loop hallucination detection.

**Pipeline**:
1. Assertion enters
2. Detection signals computed (evidence count, independence, novelty)
3. Failure modes classified
4. Audit decision issued
5. Adaptive thresholds tuned from outcomes

**Grounding Status**:
- GROUNDED: Sufficient evidence, all requirements met
- WEAK: Evidence exists but insufficient
- UNGROUNDED: No adequate evidence (floating)
- CONTRADICTED: Counter-evidence invalidates
- UNKNOWN: Cannot determine

**Failure Modes** (10):
| Mode | Description |
|------|-------------|
| NO_EVIDENCE | Claim has no supporting evidence |
| CITE_DRIFT | Citation doesn't support claim |
| SPECIOUS_PRECISION | False specificity without basis |
| CONFIDENCE_INFLATION | Confidence exceeds evidence warrant |
| SOURCE_SINGLE | Only one source (independence failure) |
| STALE_EVIDENCE | Evidence too old |
| CIRCULAR_SUPPORT | Claim supports itself |
| WRONG_EVIDENCE_TYPE | Evidence kind doesn't match claim type |
| PREMISE_LAUNDERING | Provenance concealed |
| SILENT_RETRACTION | Claim vanished without audit trail |

**Audit Stages**:
- PRE_COMMIT: Synchronous gate before HARD commit
- POST_COMMIT: Async review same turn
- PERIODIC: TTL enforcement / revalidation
- INCIDENT: Post-fact investigation

**Leak Weights**: PRE_COMMIT (1.0), POST_COMMIT (3.0), PERIODIC (2.0), INCIDENT (5.0)

---

### 3.7 drift.py (1,061 lines, 107 tests)

**Purpose**: Defense against temporal asymmetry attacks.

**Core Insight**: Environments with stateless agents + social coupling are vulnerable to asymmetric temporal actors. This isn't an attack — it's what naturally happens when persistent actors interact with amnesiac collectives.

**Failure Modes**:
- ASYMMETRIC_PERSISTENCE: One actor retains state others lose
- CLOCK_SKEW_DOMINANCE: Temporal advantage for steering
- PREMISE_RECURRENCE: Same premise repeated without new evidence
- ATTENTION_SKEW: Disproportionate engagement on bad threads

**Detection Signals**:
- `premise_recurrence_rate`: Fraction recurring without evidence
- `attention_skew`: Max contested-engagement ratio
- `temporal_coherence_gradient`: Variance differential across agents
- `unresolved_contradiction_age`: Persistence of contradictions

**Alert Levels**: NONE → WATCH → ELEVATED → HIGH → CRITICAL

**Defenses**:
- Premise quarantine (repeated without evidence → downweight)
- Dissent persistence (contradictions tracked, don't vanish)
- Single-source detection (flag single-agent premises)
- Auto-release (quarantine lifts after silence or new evidence)

---

### 3.8 strict.py (746 lines, 99 tests)

**Purpose**: Fail-closed governance preset.

**Claim Categories**:
- OPERATIONAL: Runtime facts, low ceremony
- EMPIRICAL: Evidence-backed assertions
- ARCHITECTURAL: Decisions with commitment weight
- NORMATIVE: Value judgments, highest bar

**Commit Levels**:
- PROVISIONAL: Can be retracted freely
- SOFT: Retraction logged
- HARD: Retraction requires justification + audit
- PERMANENT: Cannot be retracted without human override

**Requirements by Category**:

| Category | Min Evidence | Min Independence | Human Review |
|----------|--------------|------------------|--------------|
| OPERATIONAL | 1 | No | No |
| EMPIRICAL | 2 | Yes | No |
| ARCHITECTURAL | 3 | Yes | Recommended |
| NORMATIVE | 3 | Yes | Required |

---

### 3.9 research.py (1,047 lines, 137 tests)

**Purpose**: Non-convergent epistemic control for research mode.

**Core Principle**: Research is adversarial to its own premises. Convergence is suspicious; ambiguity is signal.

**Hypothesis Lifecycle**:
```
PROBE → TENTATIVE → SUPPORTED → ABANDONED
```

**Control Parameters**:
- `H_min`, `H_max`: Entropy bounds (below = dogma, above = sprawl)
- `D_max`: Dominance cap (no hypothesis > 70%)
- `k_timescale`: Δt invariant (claims harden slower than evidence arrives)

**Terminal States** (honest research endings):
- ILL_POSED: Question presupposes invalid construct
- INSUFFICIENT_EVIDENCE: Cannot discriminate between hypotheses
- MULTIPLE_LIVE_HYPOTHESES: Several survive without dominance

**Promotion Block Reasons**:
- INSUFFICIENT_EVIDENCE
- DOMINANCE_CAP
- ENTROPY_FLOOR
- DELTA_T_VIOLATION
- UNRESOLVED_CONTRADICTION
- CRYSTALLIZATION_TOO_FAST

---

### 3.10 claim_diff.py (771 lines, 91 tests)

**Purpose**: Epistemic state change detection across snapshots.

**Violation Types**:
- CONFIDENCE_DRIFT: Confidence changed without evidence
- PROVENANCE_LAUNDERING: Provenance upgraded without justification
- EVIDENCE_EROSION: Evidence removed without explanation
- SILENT_RETRACTION: Claim vanished without audit trail
- DEPENDENCY_BREAK: Dependency chain invalidated

**Key Classes**:
- `ClaimSnapshot` — Point-in-time claim state
- `LedgerSnapshot` — Full ledger state
- `ClaimDiffer` — Computes diff between snapshots
- `DiffViolation` — Detected violation with details

---

### 3.11 claim_signals.py (426 lines, 75 tests)

**Purpose**: Extract implicit claims from natural language text.

**Signal Types**:
- DATE: Temporal references
- ENTITY: Named entities
- QUANTITY: Numeric claims
- ASSERTIVE: Strong assertions

**Key Classes**:
- `SignalExtractor` — Regex + heuristic extraction
- `SignalMatch` — Individual signal with position
- `ExtractionResult` — All signals from text
- `assertiveness_score()` — Confidence of assertion

**Integration**: Extracted signals can auto-register as ASSUMED claims in epistemic ledger.

---

## 4. Integration Points

### 4.1 With Core Governor

- `claims.py` defines base `Claim` and `ClaimType`
- `fsm.py` uses quorum status for state transitions
- `receipts.py` provides `Receipt` as evidence type

### 4.2 With Writing Modules

- `writing_nonfiction.py` uses claim levels (SOFT/HARD/NORM)
- `writing_constraints.py` checks claim-evidence coupling
- Promotion gates enforce evidence before HARD claims

### 4.3 With Continuity Enforcement

- `continuity.py` creates anchors from claim constraints
- Anchors can require specific evidence types
- Violations feed back to epistemic ledger

### 4.4 With Interferometry

- Multi-model runs produce claims with PEER_ASSERTED provenance
- Shared claims get promoted with higher confidence
- Conflicting claims create dissent objections

---

## 5. Configuration

```python
# Epistemic config
EpistemicConfig(
    provenance_tracking=True,
    confidence_modeling=True,
    dangerous_claim_detection=True,
)

# Quorum config
QuorumConfig(
    default_k=3,
    default_delta_t=timedelta(minutes=5),
    approval_threshold=0.6,
)

# Audit config
AuditConfig(
    grounding_audit=True,
    adaptive_thresholds=True,
    pre_commit_gate=True,
    post_commit_review=True,
)

# Research config
ResearchConfig(
    H_min=0.5,
    H_max=3.0,
    D_max=0.7,
    k_timescale=1.5,
)
```

---

## 6. Test Coverage

| Module | Tests | Lines | Coverage Focus |
|--------|-------|-------|----------------|
| epistemic | 48 | 2,169 | Provenance, confidence, evidence |
| claim_status | 39 | 330 | Health scoring, summaries |
| quorum | 119 | 1,164 | Consensus, Δt, gates |
| ttl | 45 | 699 | Decay, revalidation |
| dissent | 59 | 483 | Objections, blocking |
| audit | 164 | 1,295 | Failure modes, adaptive |
| drift | 107 | 1,061 | Temporal attacks |
| strict | 99 | 746 | Fail-closed governance |
| research | 137 | 1,047 | Non-convergent control |
| claim_diff | 91 | 771 | Snapshot diffing |
| claim_signals | 75 | 426 | Signal extraction |
| **Total** | **983** | **10,191** | |

---

## 7. Known Limitations

1. **No real-time claim extraction** — Signals extracted batch, not streaming
2. **SQLite single-node** — Ledger persistence doesn't support distributed consensus
3. **Heuristic independence** — Method signature comparison, not semantic analysis
4. **English-only signals** — Claim extraction patterns are English

---

## 8. Future Enhancements

Per original specs (marked as deferred):

- Distributed ledger replication
- Semantic independence scoring (embedding-based)
- Real-time claim stream processing
- Cryptographic evidence verification
- Cross-session claim persistence

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-05 | Initial breakout spec from implementation |
