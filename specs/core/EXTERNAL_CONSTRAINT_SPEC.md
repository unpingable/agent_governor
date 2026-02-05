# External Constraint Attachment Specification

## Version 0.1 — External Substrate Binding for Claim Grounding

```yaml
status: gap
implemented: false
depends_on:
  - EPISTEMIC_STACK_SPEC.md
  - KERNEL_CONSTRAINTS_SPEC.md
blocking:
  - Defensible factual claims in nonfiction mode
  - Research mode external grounding
  - Citation verification beyond DOI metadata
estimated_scope: medium
```

---

## Executive Summary

External constraint attachment binds claims to external state snapshots. This is **not fact verification** — it is structural logging of what the system believed vs what external substrates reported at specific moments.

**Core principle**: Mismatch between claim and external state is a **signal**, not an error. You don't "fix" disagreement — you surface it and ledger it.

---

## 1. The Problem

Current claim grounding is internal:

- Claims reference files, commands, or prior claims
- No binding to external world state
- No way to say "Wikipedia reported X at time T"

This creates:

1. **Credibility gap** — No external anchoring for factual claims
2. **Temporal blindness** — No record of when external state was consulted
3. **Authority substitution risk** — Easy to launder "I checked" as "verified"

---

## 2. What This Is NOT

| Anti-pattern | Why it fails |
|--------------|--------------|
| Search + vibes | "Sources were consulted" proves nothing |
| Citation laundering | URLs as moral cover, not evidence |
| Authority substitution | "Wikipedia says X" ≠ "X is true" |
| Automatic correction | Replacing claims based on external state |

This system **does not verify facts**. It **attaches constraints** from external substrates and logs discrepancies.

---

## 3. Architecture

### 3.1 Core Types

```python
@dataclass
class ExternalSubstrate:
    """An external source that can be queried for state."""
    substrate_id: str          # wikidata, wikipedia, scholar, etc.
    query_affordances: list[str]  # What can be asked
    trust_profile: TrustProfile   # How to weight responses

@dataclass
class SubstrateSnapshot:
    """Immutable record of external state at query time."""
    substrate_id: str
    query: str                 # What was asked
    response: str              # What came back
    queried_at: datetime       # When (UTC)
    response_hash: str         # SHA-256 of response
    affordance_used: str       # Which affordance

@dataclass
class ConstraintBinding:
    """Binding between a claim and external snapshot."""
    claim_id: str
    snapshot_id: str
    binding_type: BindingType  # SUPPORTS, CONTRADICTS, TANGENTIAL, SILENT
    delta_t: timedelta         # Time between claim and query
    notes: str | None

class BindingType(str, Enum):
    SUPPORTS = "supports"      # External state aligns with claim
    CONTRADICTS = "contradicts"  # External state conflicts
    TANGENTIAL = "tangential"  # Related but not directly relevant
    SILENT = "silent"          # External source has no information
```

### 3.2 Trust Profiles

```python
@dataclass
class TrustProfile:
    """How to interpret responses from a substrate."""
    volatility: Volatility     # How often the source changes
    authority_type: AuthorityType  # Institutional, crowd, algorithmic
    citation_required: bool    # Must we cite the source?
    snapshot_ttl: timedelta    # How long is a snapshot valid?

class Volatility(str, Enum):
    IMMUTABLE = "immutable"    # DOIs, archived pages
    STABLE = "stable"          # Wikidata, peer-reviewed
    DYNAMIC = "dynamic"        # Wikipedia, news
    EPHEMERAL = "ephemeral"    # Social media, live APIs

class AuthorityType(str, Enum):
    INSTITUTIONAL = "institutional"  # Journal, government
    CROWD = "crowd"            # Wikipedia, Stack Overflow
    ALGORITHMIC = "algorithmic"  # Search results, embeddings
    PRIMARY = "primary"        # Original source
```

---

## 4. Substrate Hierarchy

Query in this order (most to least structured):

| Priority | Substrate | Why |
|----------|-----------|-----|
| 1 | **Wikidata** | Structured, stable, machine-readable |
| 2 | **Wikipedia** | Human-readable, crowd-sourced, dynamic |
| 3 | **Scholar** | Academic authority, but access-gated |
| 4 | **Archive.org** | Immutable snapshots of dynamic sources |

### 4.1 Wikidata Interface

```python
class WikidataSubstrate(ExternalSubstrate):
    """Structured knowledge graph queries."""

    def query_entity(self, qid: str) -> SubstrateSnapshot:
        """Get entity properties by Q-ID."""
        ...

    def query_claim(self, qid: str, property_id: str) -> SubstrateSnapshot:
        """Get specific claim value."""
        ...

    def search_entity(self, label: str) -> SubstrateSnapshot:
        """Find entity by label."""
        ...
```

### 4.2 Wikipedia Interface

```python
class WikipediaSubstrate(ExternalSubstrate):
    """Article content queries with revision tracking."""

    def query_article(self, title: str, lang: str = "en") -> SubstrateSnapshot:
        """Get article content."""
        ...

    def query_section(self, title: str, section: str) -> SubstrateSnapshot:
        """Get specific section."""
        ...

    def query_revision(self, title: str, rev_id: int) -> SubstrateSnapshot:
        """Get specific revision (immutable)."""
        ...
```

### 4.3 Scholar Interface

```python
class ScholarSubstrate(ExternalSubstrate):
    """Academic paper metadata and citations."""

    def query_doi(self, doi: str) -> SubstrateSnapshot:
        """Get paper metadata by DOI."""
        ...

    def query_citations(self, doi: str) -> SubstrateSnapshot:
        """Get citing papers."""
        ...

    def search_papers(self, query: str) -> SubstrateSnapshot:
        """Search for papers."""
        ...
```

---

## 5. Binding Workflow

```
Claim C asserted at t₀
        │
        ▼
┌─────────────────────────────┐
│  Select appropriate substrate │
│  based on claim domain        │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  Query substrate at t₁       │
│  Create immutable snapshot   │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  Classify binding type       │
│  SUPPORTS / CONTRADICTS / etc│
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  Record binding with Δt      │
│  (t₁ - t₀)                   │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  If CONTRADICTS:             │
│  - Do NOT auto-correct       │
│  - Surface discrepancy       │
│  - Let human decide          │
└─────────────────────────────┘
```

---

## 6. Discrepancy Handling

**Critical**: Contradictions are **surfaced**, not resolved.

```python
@dataclass
class Discrepancy:
    """Record of claim-substrate mismatch."""
    claim_id: str
    binding_id: str
    claim_value: str           # What the system claimed
    substrate_value: str       # What the substrate said
    delta_t: timedelta         # Time gap
    resolution: Resolution | None

class Resolution(str, Enum):
    CLAIM_UPDATED = "claim_updated"      # Human revised claim
    CLAIM_RETAINED = "claim_retained"    # Human kept claim despite contradiction
    SUBSTRATE_STALE = "substrate_stale"  # Substrate was out of date
    CONTEXT_DIFFERS = "context_differs"  # Different contexts, both valid
    PENDING = "pending"                  # Not yet resolved
```

The governor **never** automatically updates a claim based on external state. It:

1. Records the discrepancy
2. Surfaces it to the user
3. Waits for human resolution
4. Logs the resolution and rationale

---

## 7. Temporal Invariants

```python
class TemporalInvariants:
    """Rules about time relationships."""

    # Snapshot must be younger than TTL to bind
    MAX_BINDING_AGE: timedelta = timedelta(hours=24)

    # Warn if claim predates snapshot by too much
    RETROACTIVE_THRESHOLD: timedelta = timedelta(days=7)

    # Flag if substrate is too volatile for claim type
    VOLATILITY_MISMATCH_THRESHOLD: float = 0.7
```

### 7.1 Δt Significance

The time delta between claim and substrate query matters:

| Δt | Interpretation |
|----|----------------|
| < 1 hour | Strong binding |
| 1-24 hours | Normal binding |
| 1-7 days | Weak binding, warn |
| > 7 days | Retroactive binding, flag |

---

## 8. Integration Points

### 8.1 Epistemic Ledger

```python
class EpistemicLedger:
    def attach_external_constraint(
        self,
        claim_id: str,
        substrate: ExternalSubstrate,
        query: str,
    ) -> ConstraintBinding:
        """Query substrate and bind result to claim."""
        ...

    def get_bindings(self, claim_id: str) -> list[ConstraintBinding]:
        """Get all external bindings for a claim."""
        ...

    def get_discrepancies(
        self,
        status: Resolution | None = None,
    ) -> list[Discrepancy]:
        """Get discrepancies, optionally filtered."""
        ...
```

### 8.2 Nonfiction Governor

```python
class NonfictionVerifier:
    def verify_with_external(
        self,
        claim: WritingClaim,
        substrates: list[str] = ["wikidata", "wikipedia"],
    ) -> VerificationResult:
        """Verify claim against external substrates."""
        ...
```

### 8.3 Research Mode

```python
class ResearchLedger:
    def ground_hypothesis(
        self,
        hypothesis_id: str,
        substrates: list[str],
    ) -> list[ConstraintBinding]:
        """Attach external constraints to hypothesis."""
        ...
```

---

## 9. CLI Interface

```bash
# Attach external constraint to claim
governor external attach <claim_id> --substrate wikidata --query "Q42"
governor external attach <claim_id> --substrate wikipedia --query "Douglas Adams"

# List bindings for a claim
governor external bindings <claim_id>

# Show discrepancies
governor external discrepancies
governor external discrepancies --pending
governor external discrepancies --contradicts

# Resolve discrepancy
governor external resolve <discrepancy_id> --resolution claim_retained --reason "Context differs"

# Query substrate directly (for exploration)
governor external query wikidata "Q42"
governor external query wikipedia "Douglas Adams" --section "Bibliography"
```

---

## 10. Success Criteria

| Criterion | Test |
|-----------|------|
| Wikidata binding | Query Q-ID, get snapshot, bind to claim |
| Wikipedia binding | Query article, get snapshot with revision |
| Contradiction detection | Claim X, substrate says Y, logged |
| No auto-correction | Contradiction never modifies claim |
| Δt recorded | Time between claim and query tracked |
| Immutable snapshots | Snapshot hash stable after creation |
| Human resolution | Discrepancy resolved only by human |

---

## 11. What This Enables

When implemented correctly:

> "Here is what this system believed, and here is what the world interface said at that moment."

This provides:

1. **Defensibility** — Claims have external anchors
2. **Transparency** — Disagreements are visible
3. **Temporal awareness** — When was external state consulted?
4. **No authority substitution** — External state is constraint, not truth

---

## 12. Implementation Notes

### What Exists

- `epistemic.py` — Claim lifecycle, evidence attachment
- `nonfiction_governor/doi.py` — DOI metadata fetching
- `ttl.py` — Temporal validity tracking

### What Needs Building

| Component | Effort |
|-----------|--------|
| `external.py` module | Medium |
| Wikidata substrate | Small |
| Wikipedia substrate | Small |
| Scholar substrate | Small |
| Binding logic | Small |
| Discrepancy tracking | Small |
| CLI commands | Small |
| Tests | Medium |

Total: ~800 lines of new code.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
