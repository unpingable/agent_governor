# GOV_GAP_PROMOTION_SURFACE_001: Promotion Surface Sharpening

## Status
Proposed (v3)

## Origin
Paper 18 ("Unauthorized Durability"), crosswalk analysis.

## Summary
Five sharpening gaps between Paper 18's formal model and Governor's
current implementation. These are not "the repo is missing the thesis"
gaps — they're v3 refinements where the paper exposed the next missing
interfaces.

## Gap Inventory

### 1. Downgrade Verdict (highest practical impact)
- **Current:** pass | warn | block
- **Target:** pass | downgrade | warn | block
- **Downgrade carries:** effective_persistence, effective_scope, downgrade_rationale
- **Touches:** evidence_gate, scope governor, gate_receipt, verdict enum
- **Paper §5.3:** "A durable request may be granted as session-only."

### 2. Predicate Trace
- **Current:** provenance labels on inputs (source_class, sensitivity_hint)
- **Target:** per-predicate provenance on claims (name, confidence, provenance_class, evidence_refs)
- **Touches:** claims.py (Claim dataclass), evidence_gate (per-predicate eval)
- **Paper §5.2:** "user explicitly said X" vs "model inferred X" vs "model invented X"

### 3. Durability Class on Claims
- **Current:** durability_class on entrainment receipt only
- **Target:** requested_persistence on Claim (transient | session | durable | constitutional)
- **Touches:** claims.py, gate evaluation (compare requested vs granted)
- **Depends on:** Gap 1 (downgrade needs requested vs granted comparison)
- **Paper §5.2:** requested_persistence field

### 4. Ontological Spoofing Detection
- **Current:** evidence gate checks predicates but no explicit effect classification
- **Target:** effect classification layer (requested action → actual effect class), discrepancy triggers scrutiny
- **Touches:** evidence_gate, claim_signals (extraction), new effect_classifier module
- **Paper §7.1 T6:** "the SQL injection of promotion gates"

### 5. External Witness (research territory)
- **Current:** correlator telemetry is self-assessment
- **Target:** cryptographically anchored external witnesses
- **Partial answer:** receipt kernel hash chain (append-only, observer can't retroactively modify)
- **Full answer:** open research question, not v3 backlog
- **Paper §10.2:** "observer must be monitored by something the observer does not control"

## Build Order
3 → 1 → 2 → 4 → 5

Durability class (3) is a data model addition. Downgrade (1) consumes it.
Predicate trace (2) enriches claims for downgrade evaluation. Ontological
spoofing (4) uses predicate traces + effect classification. External witness
(5) is research, not sprint work.

## Non-Goals
- This gap spec does not propose implementation. Each gap gets its own
  design doc when work begins.
- This does not change v2 interfaces. All changes are additive.
- External witness (5) may never be "done" — it's a hard theorem-shaped
  constraint, not an engineering task.

## References
- Paper 18 crosswalk: `specs/core/PAPER_18_CROSSWALK.md`
- Entrainment spec: `specs/core/ENTRAINMENT_CONTROL_MODEL.md`
- Self-governance spec: `specs/core/SELF_GOVERNANCE_SPEC.md`
