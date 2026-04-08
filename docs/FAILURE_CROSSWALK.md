# Δ-Failure Crosswalk

Which admissibility system blocks which failure modes.

This is case law and test doctrine, not constitution. The constitution is [SHARED_INVARIANTS.md](SHARED_INVARIANTS.md). This document maps each system to the cybernetic failure taxonomy (15 Δ-domains) so we can see coverage, gaps, and scope boundaries.

Legend: **blk** = the system contains or prevents that failure mode **within its governed boundary**, not that the failure becomes impossible everywhere. **det** = the system surfaces the failure visibly but does not prevent it. **·** = out of scope.

Reference: `~/git/papers/working/cybernetic-failure-taxonomy/`

---

## The Taxonomy (compressed)

| Domain | Label | One-liner |
|--------|-------|-----------|
| **Δo** | Observability failure | Can't see own state, or sees a fake proxy |
| **Δs** | Signal corruption | Channel between world and controller is distorted |
| **Δn** | Namespace/semantic failure | Can't name the thing happening; vocabulary lags reality |
| **Δm** | Model drift | Internal model no longer matches environment |
| **Δg** | Gain mismatch | Controller too hot or too cold for environment |
| **Δa** | Actuation mismatch | Knows what's wrong, interventions too weak/blunt/wrong layer |
| **Δk** | Coupling mismatch | Too tight (cascade) or too loose (no coherent response) |
| **Δw** | Write-authority drift | Temporary exceptions gain durable power without legitimate promotion |
| **Δc** | Consequence detachment | Authority, action, and consequence stop cohabiting |
| **Δh** | Hysteresis/return failure | Can't return to sane baseline after trigger is gone |
| **Δb** | Boundary error | Regulating the wrong system boundary |
| **Δx** | Scale inversion | What stabilizes one scale destabilizes another |
| **Δr** | Recursion capture | Feedback loops feeding mostly on own outputs |
| **Δe** | Energy/maintenance deficit | Knows what to do, lacks surplus to do it |
| **Δp** | Polarity inversion | System punishes correction, rewards concealment |

---

## Coverage Map

### Continuity — remembered state

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | · | det | det | · | · | · | · | **blk** | **blk** | det | · | · | det | · | · |

- **Blocks Δw**: No silent promotion. observed → committed requires explicit transition and policy check. Default reliance_class is `none`.
- **Blocks Δc**: Premises tracked as first-class links. `explain()` computes rely_ok dynamically — taint propagates from revoked premises to dependents.
- **Detects Δh**: Blocks return-failure by erasure — revoked links preserved in graph, history additive, `explain()` reads taint. But continuity does not itself restore sane baseline; it prevents silent forgetting, not hysteresis broadly.
- **Detects Δs**: Premise invalidation surfaces when upstream memory is revoked or expired.
- **Detects Δn**: `reliance_class` and `basis` enums force explicit vocabulary for what you're relying on and why.
- **Detects Δr**: Repeated retrieval from low-reliance or inference-based memories is observable in event log.
- **Out of scope**: Live infrastructure truth, review freshness, data temporality, gain control.

### Custody — review/approval state

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | · | det | · | · | · | · | · | **blk** | **blk** | · | det | · | det | · | det |

- **Blocks Δw**: Grants expire (default 24h). Stale diffs mechanically invalidate approvals via content-addressed diff hashing.
- **Blocks Δc**: diff_hash ties approval to specific content. If the code changed, the approval is void — no gap between what was reviewed and what ships.
- **Detects Δs**: `review_theater` scar — large PR, fast approval, no comments. Signal corruption via rubber-stamping.
- **Detects Δb**: `risk_mismatch` scar — critical-tier files with lightweight review. Wrong boundary of scrutiny.
- **Detects Δr**: `self_merge` scar — only approval from PR author. Feedback loop feeding on own outputs.
- **Detects Δp**: `suppression_pressure` scoring — accumulation of `# noqa`, `@SuppressWarnings`, skipped tests. System rewarding concealment over correction.
- **Out of scope**: Memory reliance, data freshness, live infrastructure, gain/actuation control.

### Cadence — data in time

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | det | det | · | · | det | · | · | **blk** | **blk** | · | · | · | · | · | · |

- **Blocks Δw**: Prevents present-tense authority from being claimed without temporal admissibility. `claims_current` flag triggers stricter checks — you don't get to claim "now" for free.
- **Blocks Δc**: `staleness_budget = cadence + lag` enforced at query time. Temporal gap between evidence and decision is explicit and bounded.
- **Detects Δo**: `missing-contract` is an ERROR. If you can't see a source's temporal properties, it's inadmissible.
- **Detects Δs**: `semantics-mismatch` — incompatible time semantics in joins (event-time mixed with ingest-time). Distorted signal.
- **Detects Δg**: `unsafe-use-class` — source safe for monitoring used for allocation decisions. Wrong intensity of reliance.
- **Out of scope**: Review legitimacy, memory reliance, live infrastructure, entitlement.

### Standing — workload entitlement

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | · | · | · | · | · | · | · | **blk** | **blk** | det | **blk** | · | det | · | · |

- **Blocks Δw**: Grants have explicit lifecycle (request → issue → activate → use → expire/revoke). Duration is mandatory. No permanent approvals. Sweep removes expired grants.
- **Blocks Δc**: Identity verified at every step — request, activate, use. The entity taking action must be the entity that was authorized. Evidence recorded per use.
- **Blocks Δb**: Grants scoped to action + target. A deploy grant doesn't authorize reads. Scope is not inherited or broadened without new grant.
- **Detects Δh**: Receipt chain via `query chain` makes it visible when a system has been living on a grant that should have expired or been revoked. Abandoned grants persist as evidence.
- **Detects Δr**: Grant sweep catches accumulation patterns — same workload repeatedly requesting and abandoning grants is observable.
- **Out of scope**: Memory reliance, data freshness, review quality, infrastructure state, gain/actuation control.

### NQ — infrastructure state claims

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | **det** | **det** | det | · | **det** | · | · | · | · | **det** | · | · | · | · | · |

- **Detects Δo**: Missing sources appear in `collection_log`. Gaps are queryable, not invisible. Generation status (complete/partial/failed) is first-class.
- **Detects Δs**: Skewed data — impossible values, corrupt metrics, exporter health failures. Domain Δs is the literal detector category.
- **Detects Δn**: Four failure domains (Δo/Δs/Δg/Δh) force vocabulary for what kind of failure, not just severity. Classification prevents unnamed degradation.
- **Detects Δg**: Resource exhaustion, operational bounds breaches. Domain Δg is a literal detector category (unstable substrate).
- **Detects Δh**: Trend-based degradation detection. Severity escalates with persistence (info → warning → critical over generations). Domain Δh is a literal detector category.
- **Note**: NQ is primarily diagnostic — it **accuses** rather than **gates**. Detection, not prevention. Downstream systems (Governor, standing) enforce.
- **Out of scope**: Normative authorization, review quality, memory reliance, data temporal coherence (cadence's domain).

### Governor — post-verdict action authorization

| | Δo | Δs | Δn | Δm | Δg | Δa | Δk | Δw | Δc | Δh | Δb | Δx | Δr | Δe | Δp |
|-|----|----|----|----|----|----|----|----|----|----|----|----|----|----|-----|
| | det | det | det | · | **blk** | · | · | **blk** | **blk** | **blk** | **blk** | · | det | **blk** | det |

- **Blocks Δw**: Override system with sunset clauses (`--expires`). Strict FSM (DRAFT → PROPOSED → VERIFIED → APPLIED). No silent authority accumulation.
- **Blocks Δc**: Receipt-producing gates. Every action requires verified proposal with evidence. No gap between claim and proof.
- **Blocks Δg**: Regime detection (ELASTIC/WARM/DUCTILE/UNSTABLE), boil control, gain scheduling via homeostat. Controller intensity matched to environment.
- **Blocks Δh**: Scar ledger with hysteresis. Constraint stiffening after failure. Annealing requires evidence. External repair distinguished from internal recovery.
- **Blocks Δb**: Scope Governor — locality-first policy, absence-restrictive containment, escalation receipts. Agents constrained to declared scope.
- **Blocks Δe**: Execution budget. Bounded resource consumption with checkpoint/resume. Knows what to do AND has budget to do it.
- **Detects Δo**: Signal plane, telemetry, instrumentation spine. Observability of governor's own state.
- **Detects Δs**: Drift detection, claim diff, semantic stability auditing. Signal corruption in epistemic state.
- **Detects Δn**: Claim diff vocabulary monitoring. Continuity anchors preserve naming. Puppet mode pins semantic identity.
- **Detects Δr**: Correlator telemetry, capture detection. Recursion capture signals. K-vector tracking.
- **Detects Δp**: Correlator capture indicators. Suppression detection (silent_suppression signal). Polarity inversion in governance loop.
- **Out of scope**: Independently establishing truth in every domain. Governor depends on upstream verdict integrity from the rest of the family.

---

## Gap Analysis

### Failure modes with thin or no coverage

| Domain | Coverage | Notes |
|--------|----------|-------|
| **Δm** (model drift) | None explicit | No system currently tracks whether its own internal model matches environment. Governor's regime detector is closest but looks at operational signals, not model fidelity. The family currently governs evidence admissibility more than model adequacy — a precise and intentional boundary, but one worth acknowledging. |
| **Δa** (actuation mismatch) | None explicit | All systems assume their interventions are effective at the right layer. No system currently measures whether its actions actually produce intended effects. |
| **Δk** (coupling mismatch) | None explicit | The family is loosely coupled by design (separate repos, separate verdicts). No system monitors whether coupling between systems is too tight or too loose. |
| **Δx** (scale inversion) | None explicit | What stabilizes one system could destabilize another. No cross-system coherence monitoring exists yet. |

### Failure modes with detection but no blocking

| Domain | Who detects | Gap |
|--------|------------|-----|
| **Δs** (signal corruption) | NQ, Custody, Cadence, Continuity, Governor | Widely detected but only blocked indirectly (via downstream action gating). No system prevents a corrupted signal from entering the evidence chain — they catch it after the fact. |
| **Δn** (namespace failure) | NQ, Continuity, Governor | Detection via forced vocabulary (enums, claim types, domain classification). But vocabulary erosion over time (the Δh↔Δn loop) has no active monitor. |
| **Δr** (recursion capture) | NQ, Custody, Standing, Governor | Detected via self-merge scars, correlator telemetry, grant patterns. But no system actively breaks recursion loops — they report them. |

### The Δh↔Δn edge (the killer loop)

Normalization erases vocabulary for baseline; lost vocabulary makes non-return invisible. This is the most dangerous gap because it's self-concealing:

- **Continuity** partially addresses it: revoked links preserve history, `explain()` reads taint. But if the vocabulary for "what was normal" was never captured, there's nothing to read.
- **Governor** partially addresses it: claim_diff snapshots, continuity anchors. But anchors can silently drift if descriptions change without explicit revision.
- **Mitigation shape**: Periodic anchor/memory inventory with content hash. Detect when descriptions change without explicit revision event. Neither system does this yet.

---

## Using This Document

**As a scope-control device**: When tempted to add a new failure detector to a system, check this map first. If another system already covers that Δ-domain, the new detector probably belongs there, not here.

**As a test-plan generator**: For each "blk" cell, there should be at least one test proving the system actually prevents that failure mode under adversarial conditions. For each "det" cell, there should be a test proving the system surfaces the failure visibly.

**As a gap detector**: The empty columns (Δm, Δa, Δk, Δx) are not necessarily problems — they may be out of scope for the entire family. But they should be acknowledged, not accidentally ignored.

**What this is not**: A commitment to fill every cell. Some gaps are architectural choices. A family of six focused systems beats one system that claims to cover everything.
