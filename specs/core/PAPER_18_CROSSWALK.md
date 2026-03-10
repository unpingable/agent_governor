# Paper 18 Crosswalk: Unauthorized Durability → Governor

## Status
Living document. Updated as v3 work lands.

## Purpose
Map between Paper 18 ("Unauthorized Durability," Δt Framework Paper 18)
and the Governor codebase. This is the paper-to-implementation crosswalk:
what's already native, what's missing, and what belongs in v3.

The paper is the *why*. Governor is the *how*. This document is the bridge.

## Already Implemented

| Paper Concept | Section | Governor Module | Notes |
|---|---|---|---|
| Invariant 1: lower layers can't silently mutate higher | §4.2 | NLAI principle, `evidence_gate.py` | Core design axiom since v1 |
| Invariant 2: repetition ≠ authorization | §4.2 | `taint.py` (token-set Jaccard) | Recurrence detection, not authority accumulation |
| Invariant 3: context is not constitution | §4.2 | Two-ledger split (`ledgers.py`) | Facts decay, decisions persist |
| Invariant 4: observer integrity auditable | §4.2 | `correlator_telemetry.py` (K-vector) | Fidelity component tracks observer health |
| Invariant 5: durable updates require provenance | §4.2 | `gate_receipt.py`, `provenance_labels.py` | Content-addressed receipts, source classification |
| Invariant 6: reversibility decreases with depth | §4.2 | `scars.py` (hysteresis), `scope.py` | Deeper changes require more evidence to anneal |
| Write Barrier 1: L0→L2 denied | §4.3 | `evidence_gate.py` | Claims require evidence, not just assertion |
| Write Barrier 2: L1→L2 attested promotion | §4.3 | Two-ledger split, `session_continuity.py` | Session→durable requires explicit promotion |
| Write Barrier 3: L2→L3 constitutional procedure | §4.3 | `SELF_GOVERNANCE_SPEC.md` (v3) | Spec exists, enforcement TBD |
| Write Barrier 4: repetition can't bypass barriers | §4.3 | `taint.py` | Structural enforcement of INV-2 |
| Write Barrier 5: observer-affecting = high risk | §4.3 | `correlator_telemetry.py` | Capture indicators with hysteresis |
| Promotion ceremony (5 phases) | §5.1 | `fsm.py` (DRAFT→PROPOSED→VERIFIED→APPLIED) | Receipt chain is the audit trail |
| Typed claims | §5.2 | `claims.py` (ClaimType enum) | Structured, machine-checkable |
| Decision outcomes | §5.3 | Verdict enum (pass/warn/block) | See gap: downgrade not yet first-class |
| Observer integrity metric (M5) | §8 | Correlator K-vector fidelity | Self-assessed; see gap: external witness |
| Cross-layer gain (M3) | §8 | `claim_diff.py` | Silent state change detection |
| Reference drift (M2) | §8 | `drift.py` | Temporal asymmetry defense |
| Phase-lock index (M1) | §8 | `regime.py`, `boil.py` | Regime detection tracks phase-layer dynamics |
| Promotion legitimacy ratio (M7) | §8 | `gate_receipt.py` | Receipted vs unreceipted changes queryable |
| Recursive governance (§6) | §6 | `SELF_GOVERNANCE_SPEC.md` | v3 territory |
| Normalization of deviance (§9.4) | §9.4 | `scars.py` (hysteresis ratchet) | Failure provenance prevents silent norm erosion |

## v3 Gaps

Five gaps identified. Ordered by practical impact.

### Gap 1: Downgrade as First-Class Decision

**Paper reference:** §5.3 — allow/deny/**downgrade**.

**What's missing:** Governor has pass/warn/block. The paper's downgrade is
different: you grant the promotion at lower persistence or narrower scope
than requested. "You asked for durable; I'm granting session-only."

**Why it matters:** Allow/deny is too blunt. Real governed systems need a
middle lane between permissive mush and blanket bans. This is also the
mechanism that makes the MCP gateway usable — external tools request broad
scope, governor narrows it.

**Where it lands:** Scope governor already does axis-level containment.
Extend verdict from `pass|warn|block` to `pass|downgrade|warn|block`,
with downgrade carrying effective_persistence and effective_scope fields.

### Gap 2: Predicate Trace on Claims

**Paper reference:** §5.2 — `claimed_predicates` with evidence references.

**What's missing:** The distinction between "user explicitly said X," "model
inferred X," and "model invented X" exists at the input level (provenance
labels) but not at the predicate level inside each claim.

**Why it matters:** Without predicate-level provenance, a claim that mixes
explicit evidence with model inference looks the same as a claim backed
entirely by evidence. The contamination path hides inside the claim object.

**Where it lands:** Extend `Claim` dataclass with a `predicates` field,
each carrying `(name, confidence, provenance_class, evidence_refs)`.
Evidence gate evaluates per-predicate, not just per-claim.

### Gap 3: Durability Class on Claims

**Paper reference:** §5.2 — `requested_persistence` (transient/session/
durable/constitutional).

**What's missing:** The entrainment spec receipt has `durability_class`
(added last night). Governor's `Claim` dataclass doesn't carry a persistence
request. Promotion decisions can't reason about what was *requested* vs
what was *granted*.

**Where it lands:** Add `requested_persistence` to Claim. The promotion
gate compares requested vs granted. Downgrade decisions (Gap 1) use this
to explain what changed.

### Gap 4: Ontological Spoofing Detection

**Paper reference:** §7.1 (T6) — lower-tier signal seeks promotion by
expressing prohibited effect in admitted vocabulary.

**What's missing:** Governor's evidence gate does predicate checking but
doesn't have explicit ontological spoofing detection. The attack is: relabel
"delete all logs" as "archive with zero retention" to bypass the type gate.

**Why it matters:** This is the SQL injection of promotion gates. Typed
claims are only as strong as the mapping from natural language to claim
types. If the mapping itself is gamed, the gate enforces categories
faithfully while the categories are wrong.

**Where it lands:** Effect classification layer between claim extraction
and gate evaluation. Maps requested action → actual effect class.
Discrepancy between label and effect triggers elevated scrutiny.

### Gap 5: External Witness for Observer Integrity

**Paper reference:** §10.2 — observer cannot self-assess.

**What's missing:** Correlator telemetry is self-assessment. The paper
requires cryptographically anchored external witnesses — something the
observer doesn't control.

**Why it matters:** This is the hardest gap because it's a theorem-shaped
discomfort, not an engineering backlog item. A system cannot be the sole
authority on whether its own observer has been compromised.

**Where it lands:** Receipt kernel's append-only hash chain is a partial
answer (the observer's outputs are committed to a store it can't
retroactively modify). Full external witness architecture is research
territory, not v3 backlog.

## Not Gaps (Paper Claims Already Backed by Code)

- The core triad (feed/propaganda/inculcation → phase/reference/controller)
  is already the implicit design of regime detection + drift detection +
  correlator telemetry. The paper named it; the code already enforced it.

- Recursive governance (Section 6) is already specced in
  `SELF_GOVERNANCE_SPEC.md`. The paper's framing is cleaner but the
  architectural commitment is the same.

- The worked attack path (§7.2) is essentially a test case for the
  evidence gate + promotion ceremony. Could be turned into a literal
  integration test.

## References

- Paper 18: `~/git/papers/preprint/18-unauthorized-durability/unauthorized_durability.md`
- Entrainment spec: `specs/core/ENTRAINMENT_CONTROL_MODEL.md`
- Self-governance spec: `specs/core/SELF_GOVERNANCE_SPEC.md`
- v3 roadmap: `specs/gaps/` (this crosswalk feeds into gap spec creation)
