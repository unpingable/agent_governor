# Commitment Transport Specification

## Version 0.1 — Representational Invariance Under Compression

```yaml
status: gap
implemented: false
depends_on:
  - context_compact.py      # CompactionReceipt, DroppedItem, SimpleSummarizer
  - continuity.py            # AnchorRegistry, ContinuityChecker
  - continuity_bridges.py    # Mode-specific anchor factories
  - claim_diff.py            # ClaimDiffer, diffing primitives
  - claim_signals.py         # SignalExtractor (commitment extraction base)
  - CONSTRAINT_COMPILER_SPEC.md
blocking: compaction safety, summary-to-spec fidelity
estimated_scope: medium
source_paper: "11-representational-invariance (Beck 2025)"
```

### Companion to: GOVERNED_COMPACT_SPEC.md, CONSTRAINT_COMPILER_SPEC.md

---

## Executive Summary

Compaction, summarization, and formalization are lossy transforms. The governor's `context_compact.py` tracks what was dropped and provides recovery, but does not measure **what obligations survived**. Paper 11 (Representational Invariance) demonstrates that compression drops 55% of edge-case commitments and formalization drops 45% — silently weakening the constraint surface.

The Commitment Transport Validator extracts structured obligations from text before and after any lossy transform, classifies each as PRESERVED/WEAKENED/DROPPED/CONTRADICTED, and gates on the result. This makes the "anchors always win" rule mechanically enforceable across compression.

**Core insight**: Temporal coherence (Δt) is orthogonal to representational coherence (ΔR). A system can be internally consistent while losing critical constraints under transformation. The governor must enforce both.

---

## 1. The Problem

### 1.1 Lossy Transforms in the Governor Pipeline

Several operations compress or transform constraint-bearing text:

| Operation | Where | Risk |
|-----------|-------|------|
| Context compaction | `context_compact.py` | Conversation history summarized; edge-case commitments dropped |
| Continuity bridge compilation | `continuity_bridges.py` | Fiction bible / nonfiction corpus → anchor list; nuance lost |
| Constraint projection | `CONSTRAINT_COMPILER_SPEC.md` | Full constraint set → prompt prefix; soft constraints summarized |
| Claim canonicalization | `claim_diff.py` | Claims normalized for comparison; modality shifts |
| Session checkpoint | `session_continuity.py` | Session state serialized; implicit commitments lost |

### 1.2 What Gets Lost

From Paper 11, the highest-risk commitment types under compression:

- **Negative commitments** ("this does NOT do X") — 70% drop rate under compression
- **Scope boundaries** ("only applies to src/auth/") — 60% drop rate
- **Edge-case handling** ("except when user is admin") — 55% drop rate
- **Safety constraints** ("never store plaintext passwords") — 40% drop rate
- **Invariant couplings** ("if A changes, B must also change") — 45% drop rate

These are exactly the commitments the governor exists to protect.

---

## 2. The Solution

### 2.1 Commitment Extraction

Extract structured obligations from text using an "obligation lens" on top of existing claim signal extraction:

```python
@dataclass
class Commitment:
    """A semantic obligation extracted from text."""
    commitment_id: str        # Content hash
    text: str                 # Original text span
    modality: Modality        # MUST, SHOULD, MAY, MUST_NOT
    kind: CommitmentKind      # INVARIANT, PROHIBITION, BOUNDARY, DEPENDENCY, EXCLUSION, REQUIREMENT
    scope: str | None         # Scope restriction, if any
    source_span: tuple[int, int]  # Byte offsets in source text

class Modality(Enum):
    MUST = "must"             # Hard obligation
    SHOULD = "should"         # Soft preference
    MAY = "may"               # Permission
    MUST_NOT = "must_not"     # Hard prohibition

class CommitmentKind(Enum):
    INVARIANT = "invariant"           # "X must always be true"
    PROHIBITION = "prohibition"       # "never do X"
    BOUNDARY = "boundary"             # "only applies to X"
    DEPENDENCY = "dependency"         # "if X then Y"
    EXCLUSION = "exclusion"           # "X and Y are mutually exclusive"
    REQUIREMENT = "requirement"       # "X is required"
```

Extraction uses `claim_signals.py` patterns extended with obligation-specific markers:
- MUST/SHALL/NEVER/ALWAYS/REQUIRED → modality classification
- Scope markers (only, except, within, limited to) → boundary detection
- Conditional markers (if, when, unless, provided that) → dependency detection
- Negation markers (not, never, must not, forbidden) → prohibition detection

### 2.2 Transport Classification

After a lossy transform, re-extract commitments and classify transport:

```python
class TransportOutcome(Enum):
    PRESERVED = "preserved"       # Same modality, same content, same scope
    WEAKENED = "weakened"          # Modality softened (MUST→SHOULD), scope widened, exceptions added
    DROPPED = "dropped"           # No corresponding commitment in output
    CONTRADICTED = "contradicted" # Output contains negation or exception that nullifies

@dataclass
class CommitmentTransport:
    """Transport result for a single commitment."""
    commitment: Commitment
    outcome: TransportOutcome
    detail: str                   # Human-readable explanation
    after_commitment: Commitment | None  # Matched commitment in output, if any
    similarity: float             # Alignment score (0.0–1.0)
```

Alignment uses existing primitives:
- `claim_diff.py` diffing for content matching
- `taint.py` Jaccard fingerprinting for near-duplicate detection
- Modality comparison (MUST→SHOULD = WEAKENED, not PRESERVED)

### 2.3 Shear Metric

```python
@dataclass
class ShearReport:
    """Aggregate transport result."""
    transports: list[CommitmentTransport]
    shear_score: float            # Weighted (DROPPED + CONTRADICTED + 0.5*WEAKENED) / total
    hard_shear: float             # Shear on MUST/MUST_NOT commitments only
    content_hash: str             # Hash of full report (for receipts)

    @property
    def blocking(self) -> bool:
        """Any DROPPED or CONTRADICTED MUST/MUST_NOT commitment blocks."""
        return any(
            t.outcome in (TransportOutcome.DROPPED, TransportOutcome.CONTRADICTED)
            and t.commitment.modality in (Modality.MUST, Modality.MUST_NOT)
            for t in self.transports
        )
```

Shear weights by modality criticality: MUST/MUST_NOT = 1.0, SHOULD = 0.7, MAY = 0.3.

### 2.4 Gating Rules

| Transport Outcome | On MUST/MUST_NOT | On SHOULD | On MAY |
|-------------------|-----------------|-----------|--------|
| PRESERVED | Pass | Pass | Pass |
| WEAKENED | Require quorum or human review | Warn | Pass |
| DROPPED | **Block** | Warn | Pass |
| CONTRADICTED | **Block** | **Block** | Warn |

---

## 3. Integration Points

### 3.1 Context Compaction

`context_compact.py` currently emits `CompactionReceipt` with `DroppedItem` lists. The transport validator wraps compaction:

```python
# Before compaction
commitments_before = extract_commitments(conversation)

# Compact
receipt = compactor.compact(conversation)

# Validate transport
commitments_after = extract_commitments(receipt.summary)
report = validate_transport(commitments_before, commitments_after)

if report.blocking:
    # Recompact with protected commitments
    compactor.compact(conversation, protect=report.hard_commitments)
```

### 3.2 Constraint Compiler

When the compiler summarizes SOFT constraints (CONSTRAINT_COMPILER_SPEC.md Section 8), the transport validator ensures no MUST-modality constraints were weakened in the summary.

### 3.3 Continuity Bridges

When fiction bible / nonfiction corpus are compiled into anchors, the transport validator checks that prohibitions and invariants survive the bridge transform.

### 3.4 Telemetry

Emit `COMMITMENT_TRANSPORT` events with shear score, per-outcome counts, and blocking status. Enables trend analysis: "compaction shear increasing over time" = systematic obligation loss.

---

## 4. CLI Surface

```bash
# Check transport across a specific transform
governor transport check --before before.txt --after after.txt

# Check compaction transport
governor transport compact --session <id>

# Show transport history
governor transport history

# Show aggregate shear statistics
governor transport stats
```

---

## 5. Design Constraints

1. **Pure extraction.** Commitment extraction is regex + heuristic pattern matching, not LLM-based. Keeps the validator fast and deterministic.
2. **No false completeness.** The extractor will miss implicit commitments. That's acceptable — it catches the explicit ones that compression most commonly drops.
3. **Monotonic gating.** Transport failures can only tighten constraints (block or require review), never loosen them.
4. **Receipt-producing.** Every transport validation produces a content-addressed `ShearReport` for audit.

---

## 6. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `GOVERNED_COMPACT_SPEC.md` | Transport validator wraps compaction step |
| `CONSTRAINT_COMPILER_SPEC.md` | Validates SOFT constraint summarization |
| `KERNEL_CONSTRAINTS_SPEC.md` | MUST/MUST_NOT commitments map to kernel constraints |
| `SESSION_CONTINUITY_SPEC.md` | Checkpoint serialization validated for transport |
| `DETECTOR_INTEGRATION_SPEC.md` | Shear score becomes a signal input to constraint compiler |

---

## 7. Open Questions

1. **LLM-assisted extraction.** Pure regex misses implicit commitments ("we agreed to use React" is a commitment but has no MUST marker). Should extraction optionally use the constraint compiler's claim signal extractor as a second pass?

2. **Shear threshold tuning.** What aggregate shear score triggers blocking vs. warning? Initial values: block at hard_shear > 0.0 (any MUST dropped), warn at shear_score > 0.3.

3. **Protected compaction.** When transport fails, the validator tells the compactor to re-compact with protected commitments. How does the compactor prioritize what else to drop to stay within budget?
