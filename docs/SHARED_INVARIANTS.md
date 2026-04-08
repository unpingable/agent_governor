# Shared Invariants

Constitutional common ground across the admissibility family.

These projects are **different admissibility regimes** over the same core problem:
is this evidence good enough to act on?

| System | What it governs | Evidence type | Status |
|--------|----------------|---------------|--------|
| **Continuity** | Remembered state | Cross-session memory objects | Public |
| **Custody** | Review/approval state | Code review grants | Public |
| **Cadence** | Data in time | Temporal source contracts | Public |
| **Standing** | Workload entitlement | Identity-verified grants | Public |
| **NQ** | Infrastructure state claims | Live operational observations | Private |
| **Governor** | Post-verdict action authorization | Evidence-backed action proposals | Public |

Governor is downstream. It consumes verdicts from the others; it doesn't replace them. These systems produce admissibility verdicts under domain-specific rules; downstream consumers may act on those verdicts but not silently reinterpret them.

---

## The Seven Invariants

### 1. Possession is not permission

Having evidence does not entitle you to rely on it. Every system enforces a gap between "I can retrieve this" and "I may act on this."

- **Continuity**: `reliance_class` (none → retrieve_only → advisory → actionable)
- **Custody**: grants expire (default 24h); stale diffs invalidate approvals
- **Cadence**: `safe_for` use classes; a source safe for monitoring may be inadmissible for allocation
- **Standing**: grants have explicit lifecycle (request → issue → activate → use → expire/revoke); possession of a grant doesn't mean it's active
- **NQ**: measurement age determines what claims can be made; stale evidence is inadmissible
- **Governor**: receipts prove verification happened; proposals without receipts are blocked

### 2. No silent promotion

State must not quietly harden from observation into something downstream actions depend on. Transitions are explicit, receipted, and governable.

- **Continuity**: observed → committed requires deliberate action and policy check
- **Custody**: review_theater detection; fast approval of large PRs is a scar, not a grant
- **Cadence**: `claims_current` flag triggers stricter checks; you don't get to claim "now" for free
- **Standing**: request → issue → activate is explicit; no silent escalation from "requested" to "entitled"
- **NQ**: stale state preserved on failure; prior readings stay visible rather than silently aging
- **Governor**: DRAFT → PROPOSED → VERIFIED → APPLIED; no skipping stages

### 3. Every governing mutation is receipted

All governing state changes produce auditable records. The receipt form varies by subsystem — hash-chained mutation logs, content-addressed grant hashes, decision receipts, generation metadata — but the principle is uniform: no unattested transitions.

- **Continuity**: hash-chained receipt per observe/commit/revoke; SHA-256 with prev_hash
- **Custody**: `receipt_hash` on every grant; deterministic from grant payload
- **Cadence**: decision receipts documenting source snapshots, violations, and grade at eval time
- **Standing**: content-addressed receipt (canonical JSON + SHA-256) at every state transition; WLP-compatible
- **NQ**: generation metadata (started_at, sources_ok, sources_failed, status) per atomic batch
- **Governor**: gate receipts (content-addressed: H(schema + gate + subject + evidence + policy))

### 4. Validity decay is explicit, never silent

Evidence can lose validity through age (staleness), elapsed windows (expiry), or upstream invalidation (taint). All three are surfaced, never hidden.

- **Continuity**: `expires_at` on memories; `rely_ok` computed dynamically from premise freshness
- **Custody**: diff_hash comparison; if the diff changed since review, the grant is stale — mechanical, no judgment
- **Cadence**: `staleness_budget = cadence + lag`; present-tense claims checked against budget
- **Standing**: grants carry explicit duration; expired grants swept; revocation is an event, not disappearance
- **NQ**: `as_of_generation` on every row; failed sources leave prior rows with visible staleness
- **Governor**: fact decay; facts auto-expire when underlying files change

### 5. Fail closed on missing evidence

Absence of evidence is treated as a problem, not a default. Unknown state is restrictive, not permissive.

- **Continuity**: default reliance_class is `none`; must be explicitly promoted
- **Custody**: no_approval scar; merged without review is a finding
- **Cadence**: missing-contract is an ERROR; unlinted sources are inadmissible
- **Standing**: identity verification at every step (request, activate, use); unverified identity = denied
- **NQ**: missing sources appear in collection_log; gaps are queryable, not invisible
- **Governor**: strict mode requires receipts for all claims; exploratory mode is opt-in relaxation

### 6. History is preserved, not overwritten

Revocation, expiration, and invalidation are recorded as events. Prior state remains available for audit.

- **Continuity**: revoked links stay in graph; `explain()` reads taint from source status
- **Custody**: revoked grants carry reason; suppression pressure tracked across scan generations
- **Cadence**: receipts are append-only; violation history is the audit trail
- **Standing**: `query chain` walks full receipt history; revoked/expired grants remain in store with reason
- **NQ**: history tables (append-only, narrow) alongside current-state tables; generation diffs are possible
- **Governor**: decisions persist until explicitly revised; the ledger is the shared memory

### 7. Admissibility is context-dependent

The same evidence may be admissible for one purpose and inadmissible for another. Context is not optional.

- **Continuity**: `basis` (direct_capture vs inference) constrains what reliance_class is reachable
- **Custody**: risk tiers (critical/structural/standard/low); auth files need more scrutiny than READMEs
- **Cadence**: `UseClass` (monitoring/reporting/allocation/escalation/audit/exploratory) per source
- **Standing**: grants scoped to action + target; a deploy grant doesn't authorize reads
- **NQ**: four failure domains (Δo/Δs/Δg/Δh) orthogonal to severity; domain is static, severity is temporal
- **Governor**: operating envelopes (strict/exploratory); jurisdictions (factual/speculative/adversarial)

---

## Shared Primitives (observed, not yet extracted)

These patterns recur across the family. They are not shared code yet — extraction should wait until duplication is concrete, not just structural.

| Pattern | Where it appears |
|---------|-----------------|
| Content-addressed hashing (SHA-256, deterministic JSON) | All six |
| SQLite with WAL mode, local-first | All six |
| Append-only event/receipt log | Continuity, Custody, Standing, NQ, Governor |
| Typed enum for evidence/finding classification | All six |
| Tiered severity/grade (not boolean pass/fail) | All six |
| Temporal contracts or TTLs on evidence | Continuity, Custody, Cadence, Standing, NQ |
| Explicit idempotency (keys or content-addressing) | Continuity, Standing, Governor |

---

## What This Document Is Not

- **Not a proposal to merge repos.** These are different admissibility regimes, not clones.
- **Not a shared library spec.** Shared code comes after concrete duplication, not structural resemblance.
- **Not an ontology.** Each system names its own domain concepts. Forced alignment would be worse than duplication.

The common law is: **separate possession of evidence from permission to rely on it.** Each system applies that principle to a different evidence type, at a different layer, with different temporal semantics. That's architecture, not branding.
