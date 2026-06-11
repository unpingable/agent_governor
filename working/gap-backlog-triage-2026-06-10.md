# Gap-Backlog Triage — 2026-06-10

Validation pass over `~/git/gap-backlog-inventory.codex.jsonl` (234 entries, codex audit,
LOW/MEDIUM self-confidence). 10 Sonnet validators (per-repo, chunked), each verdict
grounded in an actual repo check (file existence, status header, shipped-code
corroboration). Opus synthesis. **Full coverage — all 234 entries.**

## Aggregate (corrected)

| Verdict | Count | % | Meaning |
|---|---|---|---|
| **CONFIRMED** | 140 | 60% | inventory's status/action assessment matches repo reality |
| **STALE** | 70 | 30% | inventory out of date or mislabeled (mostly: it flagged "needs sweep" on gaps that are *verifiably shipped*, or misread sibling cross-references) |
| **WRONG** | 20 | 9% | inventory factually misread the file |
| **NEEDS-HUMAN** | 4 | 2% | genuinely ambiguous — partial-ship lifecycle, operator call |

**Headline: the operator's doubt was justified — ~40% of inventory labels (94/234) are
off.** The inventory is a useful "what to check" prompt, but its specific status/action
labels are unreliable. Do NOT action gaps off the codex inventory directly; this
validation is the corrected layer.

## Systematic inventory error classes (the real signal)

The 94 STALE+WRONG entries fail in characterizable ways — useful if the inventory is
ever regenerated:

1. **Cross-reference contamination** (most common). "mentions closed/shipped language"
   fired on references to *sibling* shipped gaps in the body, not the gap itself.
   Examples: nq FEDERATION, INSTANCE_WITNESS, LOW_TOIL, OBSERVATION_PLANE,
   OPERATOR_ATTESTATION, EVIDENCE_FORGETTING; agent_gov DISCLOSURE_STANDING,
   NIGHTSHIFT_ADAPTER, OPENCODE_ADAPTER, STRUCTURED_EVIDENCE.
2. **Closure-CRITERIA misread as closure-CLAIM.** "This gap is closed when X"
   (acceptance criteria) read as "this gap is closed." Examples: agent_gov
   BASIS_FOR_BINDING, INBOUND_CONTEXT_AUTHORITY, STATE_REENTRY_PROTOCOL.
3. **Garbled claimed_status** — type annotations / body text misparsed into the status
   field. Examples: RECEIPT_V1_SCHEMA ("modify # Internal agent state modified"),
   RUNTIME_SUPERVISOR ("str # pending|approved|rejected"), nq TESTIMONY_DEPENDENCY,
   scheduler GAP-nq-nightshift-contract ("active|pending|resolving|clear"), GAP-parallel-ops
   ("observed").
4. **Domain-vocabulary false positives** — "fail closed" (security posture), incident-state
   enums, status-vocabulary *definitions* in README/index files read as closure claims.
   Examples: nq DASHBOARD_RED_TEAM, scheduler GAP-incident-modes, GAP-temporal-obligation.
5. **Under-verification of real ships** — many gaps flagged "suspect closed, needs sweep"
   are in fact cleanly shipped with code corroboration; the validation confirms closure
   the inventory wouldn't commit to (the v2.4/2.5 signals/* phases; nq's shipped V1 gaps).

## Actionable output

- **NEEDS-HUMAN (4) — operator lifecycle calls:**
  - `agent_gov GOV_GAP_CONTEXT_MANIFEST_001` — Phase 1 shipped, phases 2–3 open: treat as
    closed or open?
  - `agent_gov GOV_GAP_FRONT_DOOR_001` — packaging done, "do not publish to PyPI yet": closed?
  - `agent_gov GOV_GAP_NLAI_GATE_001` — external ship only (nlai 0.3.0 on PyPI); in-repo
    extraction + governor consumption never happened.
  - `atproto facts-export-duckdb-snapshot-001` — ratified + implemented same day; no closure note.
- **STALE-shipped → low-value status-doc cleanup (NOT urgent, they're done):** ~40 gaps
  whose code is verifiably shipped but whose gap-spec status header or the inventory lags.
  feature-history.md is the source of truth; the gap docs can be closed at leisure. The
  bulk are nq's shipped V1 gaps (FINDING_DIAGNOSIS/EXPORT, FLEET_INDEX, GENERATION_LINEAGE,
  GENERALIZED_MASKING, MAINTENANCE_DECLARATION, OPERATIONAL_INTENT, STABILITY_AXIS,
  EVIDENCE_LAYER, REGIME_FEATURES, SENTINEL_LIVENESS, DOMINANCE_PROJECTION,
  DURABLE_ARTIFACT, DISK_STATE_CUTOVER) and agent_gov's v2.4/2.5 signals spine
  (CALIBRATION_*, CAPTURE_SELF_DIAGNOSTIC, EXPOSURE_PROXY, SIGMA_RATE, SILENT_SUPPRESSION,
  REPLAY_HARNESS, PREDICT_REGIME, SCAR_FINGERPRINT, V2_4*, POLICY_IR, MCP_GOVERNOR_GATEWAY,
  OVERRIDE_ACCUMULATION, VALIDATOR_INTEGRATION) + continuity's V1 ships (TIME_DISCIPLINE,
  ISLANDS_OF_CONTINUITY, PREMISE_CONSISTENCY_DOCTOR, WLP_PERSISTENCE, CROSS_COMPONENT_RELIANCE,
  CROSS_SCOPE_REFERENCE) + scheduler's landed slices (deferred-run-split,
  imported-basis-freshness, silence-aware-posture, governor-contract pipe-through).
- **WRONG (20) → inventory corrections only** (no repo action; the gap is fine, the
  inventory mislabeled it).
- **CONFIRMED-open** = the genuine live backlog. Grooming/prioritizing those is a separate
  effort (NOT done here — that would be the "fix everything" overreach).

## Disposition (operator-ratified 2026-06-10)

This pass **decontaminated the instrument**; it did not groom the backlog. What to do
with each bucket:

- **STALE-shipped (~40) → `status-doc-sweep-candidate`. Walk away.** Janitorial gravity.
  Do NOT sweep the status docs now — feature-history is source of truth and the code is
  shipped. Touch one only if a stale status blocks a consumer / README / release path.
- **WRONG (20) → regression exhibits, not chores.** They are evidence of the inventory
  generator's failure modes (the five classes above). Keep for calibrating the next
  generator; no repo action.
- **NEEDS-HUMAN (4) → the only judgment surface.** `GOV_GAP_CONTEXT_MANIFEST`,
  `GOV_GAP_FRONT_DOOR`, `GOV_GAP_NLAI_GATE`, atproto `facts-export-snapshot-001`.
- **CONFIRMED-open (~140) → the genuine backlog.** Mostly v3-deferred / candidate /
  containment-vessel (recognition records, not active blockers). The next artifact is the
  **dependency skeleton** (which open gap blocks which) — sparse-allowed, real-artifact
  edges only, unknown→NEEDS-HUMAN. NOT done here.

## Method notes / caveats

- Read-only; no repo files were modified by this pass.
- Verdict semantics: STALE was used broadly by validators for "inventory's label is off in
  any direction" (out-of-date OR mislabeled), so STALE ≠ "needs work" — many STALE entries
  are *more done* than the inventory thought. Read the per-entry evidence, not the bare label.
- NQ entries validated against the moved path `~/git/nq-root/nq` (the inventory's `nq/…`
  paths are stale post-move; every nq gap_file still resolved, so no WRONG-for-missing).
- This is a *map*, not a grooming. No gap was implemented, prioritized, or rewritten.

## Per-entry verdicts

Format: `gap_file — VERDICT — evidence`. Grouped by repo.

### agent_gov (92): C=55 S=24 W=10 NH=3

3X_BRAIN_DUMP — CONFIRMED — open brain-dump, no single status, candidate-non-binding accurate
CALIBRATION_LAYER_GAP — STALE — shipped (signals/calibration_layer.py + tests); inventory unsure but verifiably closed
CANON_AUTHORITY_PROMPT — CONFIRMED — Status: gap (open)
CANON_CAPTURE_SPEC — STALE — phase-1-implemented (fiction_governor/canon_capture.py); partial ship
CAPTURE_SELF_DIAGNOSTIC_GAP — STALE — shipped (signals/capture_self_diagnostic.py)
CONTEXT_USAGE_TELEMETRY — CONFIRMED — daemon-side shipped, client UI pending; partial open
CONTINUITY_BEARING_SYSTEMS — CONFIRMED — Status: Proposed
CROSS_DOMAIN_SCHEMA_GAP — CONFIRMED — Status: gap (architectural), v3
ETHICAL_HARDENING — CONFIRMED — Status: deferred (v3) matches exactly
EXPOSURE_PROXY_GAP — STALE — shipped (signals/exposure_proxy.py)
GAP_BUILD_ORDER — STALE — instrumentation phases all SHIPPED incl B3
GAP_INVARIANTS — CONFIRMED — cross-cutting, signatures deferred to v3; open
GOVERNED_ACTIVITIES — CONFIRMED — shipped (110 tests, governed_activity.py) matches
GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001 — CONFIRMED — containment vessel, open
GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001 — CONFIRMED — containment vessel, open
GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001 — WRONG — open containment vessel; inventory misread as closed
GOV_GAP_BUDGETED_EXECUTION_001 — STALE — partial ship (runtime/budget.py, 15 tests), open remainder
GOV_GAP_CHAIN_001 — CONFIRMED — shipped (governed_activity + verifier_gate) matches
GOV_GAP_CI_LANE_001 — CONFIRMED — shipped (ci.py, 43 tests) matches
GOV_GAP_CODEX_ADAPTER_001 — WRONG — parked/open; inventory said closed
GOV_GAP_CONTEXT_MANIFEST_001 — NEEDS-HUMAN — Phase 1 shipped, phases 2–3 open
GOV_GAP_CONTINUITY_HYGIENE_001 — CONFIRMED — status: draft (open)
GOV_GAP_COPILOT_ADAPTER_001 — WRONG — Proposed (v3); "CI status check" misread as closure
GOV_GAP_CORRECTIVE_TRANSITION_BOUNDARY_001 — CONFIRMED — containment vessel, open
GOV_GAP_DECISION_CONTEXT_001 — CONFIRMED — proposed (v3)
GOV_GAP_DISCLOSURE_STANDING_001 — WRONG — design spec (v3 prereq); "shipped" refs were dependencies
GOV_GAP_EGRESS_001 — CONFIRMED — shipped (egress_gate.py, 66 tests) matches
GOV_GAP_FEATURE_HISTORY_LIFECYCLE_001 — STALE — closure criteria met 2026-05-26; inventory said draft
GOV_GAP_FRAME_CAPTURE_001 — CONFIRMED — Proposed (v3)
GOV_GAP_FRONT_DOOR_001 — NEEDS-HUMAN — packaging shipped, PyPI publish withheld
GOV_GAP_GATE_DOCTRINE_SPEC_001 — CONFIRMED — methodology record, open
GOV_GAP_GOAL_PROMOTION_001 — CONFIRMED — Proposed (v3), no code
GOV_GAP_GOVERNED_LESSONS_SCOPE_001 — CONFIRMED — active/draft, no subsystem code
GOV_GAP_HYSTERESIS_REPAIR_001 — CONFIRMED — Draft
GOV_GAP_INBOUND_CONTEXT_AUTHORITY_001 — WRONG — open vessel; "closed when" is criteria not claim
GOV_GAP_INTERFEROMETRY_IDENTIFIABILITY_001 — CONFIRMED — draft; no identifiab* impl
GOV_GAP_LLM_PROVIDER_EGRESS_001 — STALE — partial ship (egress wired, subprocess open)
GOV_GAP_LOCAL_SUPERVISOR_001 — CONFIRMED — gap spec (no code) matches
GOV_GAP_MCP_SUPPLY_001 — CONFIRMED — deferred (v3) matches
GOV_GAP_NIGHTSHIFT_ADAPTER_001 — WRONG — open 3.x; "closed enum" ≠ gap closure
GOV_GAP_NLAI_GATE_001 — NEEDS-HUMAN — external ship only (PyPI), in-repo phases not done
GOV_GAP_OPENCODE_ADAPTER_001 — WRONG — Proposed (v3 blocked); "fails closed" misread
GOV_GAP_OVERRIDE_ACCUMULATION_001 — STALE — core shipped (compute_pressure, 17 tests); CLI actually shipped too
GOV_GAP_PHASE_WITNESS_MAPPING_001 — CONFIRMED — containment vessel, candidate
GOV_GAP_PLUGIN_001 — CONFIRMED — active dev (contrib/claude-code-plugin/)
GOV_GAP_PROMOTION_SURFACE_001 — CONFIRMED — Proposed (v3)
GOV_GAP_PUBLIC_GATE_CONFORMANCE_001 — CONFIRMED — candidate inventory, open
GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001 — CONFIRMED — containment vessel, open
GOV_GAP_RUNTIME_SUPERVISOR_001 — STALE — Shipped 2.8.0 (runtime/, dogfood); inventory status garbled
GOV_GAP_SCHEDULED_TASKS_001 — CONFIRMED — Proposed (v3)
GOV_GAP_SCOPE_AWARE_SIGNALS_001 — CONFIRMED — proposed (v3)
GOV_GAP_SEALED_OUTCOME_BOUNDARY_001 — CONFIRMED — containment vessel, candidate
GOV_GAP_SESSION_001 — CONFIRMED — deferred (v3, placeholder fields in v2) matches
GOV_GAP_SLSA_001 — CONFIRMED — open 3.x (principal_ref/auth_method stubs)
GOV_GAP_STATE_REENTRY_PROTOCOL_001 — WRONG — open vessel; "closed when" is criteria
GOV_GAP_SUBSTRATE_CUSTODY_001 — CONFIRMED — proposed
GOV_GAP_SWARM_ORCHESTRATION_001 — CONFIRMED — Proposed (v3)
GOV_GAP_TEMPO_AWARE_GOVERNANCE_001 — CONFIRMED — 3.x, open
GOV_GAP_TOLERABILITY_HORIZON_001 — CONFIRMED — 3.x, open
GOV_GAP_UPSTREAM_REGIME_001 — CONFIRMED — proposed (v3)
GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001 — CONFIRMED — proposed/audit-required
GOV_GAP_VOCABULARY_EROSION_001 — CONFIRMED — proposed (v3)
GOV_GAP_WATCH_POLICY_001 — CONFIRMED — v3 candidate
GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001 — CONFIRMED — containment vessel
GOV_PRIM_PROV_001 — CONFIRMED — shipped (provenance_labels.py, 53 tests) matches
KAPPA_DIAL_GAP — CONFIRMED — gap (operator-facing)
MCP_GOVERNOR_GATEWAY — STALE — shipped (libs/mcp_governor/, ~89 tests); inventory unsure
OPERATIONAL_SLA — CONFIRMED — partial ship (timing fragment shipped, 3.x SLA open)
PAAS_SHARDING_GAP — CONFIRMED — gap (architectural, long-horizon)
POLICY_IR — STALE — Phase 1 shipped (chat_bridge wiring); inventory said candidate-no-action
POLYGLOT_FINDINGS — CONFIRMED — benchmark doc, non-binding
PREDICT_REGIME_PREFLIGHT_GAP — STALE — shipped (signals/predict_regime.py, 72 tests)
PROBLEM_SOLVING_MODE — CONFIRMED — spec (not building yet)
RECEIPT_KERNEL_ROADMAP — CONFIRMED — canonical; 13 invariants wired
RECEIPT_V1_SCHEMA — WRONG — garbled claimed_status; libs/receipt_v1/ shipped, no status field
REGIME_CAPTURE_2D_GAP — CONFIRMED — gap (conceptual + dashboard)
RELATIONAL_INVARIANTS — CONFIRMED — deferred (names category, no machinery)
REPLAY_HARNESS_GAP — STALE — shipped (signals/replay_harness.py + sources)
SCAR_FINGERPRINT_SPEC — STALE — implemented (scars.py, 161 tests)
SESSION_LINEAGE — CONFIRMED — gap spec, open
SIGMA_RATE_GAP — STALE — shipped (signals/sigma_rate.py)
SILENT_SUPPRESSION_GAP — STALE — shipped (signals/silent_suppression.py)
STRUCTURED_EVIDENCE_AND_PROMOTION_GAP — WRONG — Proposed; "shipped" ref was sibling gap
TEXT_ADMISSIBILITY_GAP — CONFIRMED — Proposed
V2_4A_SPINE — STALE — Phase A shipped (A0–A3); inventory said candidate-no-action
V2_4B_CAPTURE_SELF_DIAGNOSTIC — STALE — shipped (signals/capture_self_diagnostic.py)
V2_4B_DECISION_EVIDENCE_LAG — STALE — shipped (signals/decision_evidence_lag.py)
V2_4C_CALIBRATION_FITTING — STALE — shipped (signals/calibration_fitting.py)
V2_4C_SPINE — STALE — Phases A–C all shipped
V2_4D_PREDICT_REGIME_PREFLIGHT — STALE — shipped (signals/predict_regime.py, 72 tests)
VERIFIED_KERNEL — CONFIRMED — v2 shipped (HashRef), v3 remaining; partial matches

### nq (85): C=51 S=28 W=6 NH=0  [validated against ~/git/nq-root/nq]

ACTION_OVERLAY_GAP — CONFIRMED — stub (open)
AGENTIC_CI_WITNESS_FAMILIES_GAP — CONFIRMED — proposed
AGGREGATOR_SELF_INTEGRITY_GAP — WRONG — proposed; closure lang was sibling crash_atomicity refs
ALERT_DIRECTNESS_GAP — CONFIRMED — Proposed
ALERT_INTERPRETATION_GAP — CONFIRMED — Proposed
ANTI_LAUNDERING_DOCTRINE_MAP — CONFIRMED — index/navigation, non-binding
ATPROTO_FEED_CONSUMER_STATE_GAP — CONFIRMED — proposed
ATPROTO_FEED_PUBLISHER_PIPELINE_STATE_GAP — CONFIRMED — candidate (slice)
CANNOT_TESTIFY_STATUS — CONFIRMED — proposed
CLAIM_KIND_DISK_STATE_GAP — CONFIRMED — proposed
CLAIM_PREFLIGHT_REGISTRY_SHAPE_GAP — CONFIRMED — proposed
CLAIM_STATE_CONSOLE_BOUNDARY_GAP — WRONG — candidate; "slice closed" was a different gap
CLAIM_VISUALIZATION_LINT_GAP — CONFIRMED — OPEN matches exactly
COMPLETENESS_PROPAGATION_GAP — WRONG — proposed, no closure language present
COVERAGE_HONESTY_GAP — CONFIRMED — shipped V1 (migration 038, 15 tests) matches
CUSTODIAN_BINDING_ACCOUNTABILITY_CANDIDATE — CONFIRMED — candidate, non-binding
DASHBOARD_MODE_SEPARATION_GAP — CONFIRMED — proposed
DASHBOARD_RED_TEAM_SMOKE_GAP — WRONG — candidate; "fail closed"/SQL literal misread
DASHBOARD_SQL_INSPECTION_GAP — CONFIRMED — candidate, non-binding
DECLARED_CONTEXT_GAP — CONFIRMED — candidate (name surface, don't build)
DECLARED_EXPECTED_OBSERVED_RECONCILIATION_GAP — CONFIRMED — proposed, no build auth
DESKTOP_FORENSICS_GAP — CONFIRMED — proposed
DISK_BUDGET_ENFORCEMENT_GAP — WRONG — proposed; "config exists, behavior doesn't"; shipped refs were siblings
DISK_STATE_CUTOVER_TO_SHARED_SPINE — CONFIRMED — landed/retired (6 commits + projectors) matches
DNS_WITNESS_FAMILY_GAP — CONFIRMED — proposed (V0 spec)
DOMINANCE_PROJECTION_GAP — CONFIRMED — shipped (HostStateVm, 10/9 tests) matches
DRIFTWATCH_LABELWATCH_PUBLICATION_STATE_GAP — CONFIRMED — candidate
DURABLE_ARTIFACT_SUBSTRATE_GAP — CONFIRMED — built/shipped V1 (import.rs + tests) matches
EVIDENCE_FORGETTING_GAP — WRONG — candidate; "shipped" was sibling EVIDENCE_RETIREMENT
EVIDENCE_LAYER_GAP — STALE — shipped (migration 025, compute_finding_key); garbled status
EVIDENCE_RETIREMENT_GAP — CONFIRMED — partial (V1 substrate shipped, follow-on open)
FEDERATION_GAP — STALE — candidate/recognition; "shipped" was sibling refs
FINDING_DIAGNOSIS_GAP — STALE — shipped (migration 027, FailureClass enums); correctly closed
FINDING_EXPORT_GAP — STALE — shipped (export.rs FindingSnapshot DTO); correctly closed
FINDING_LIFECYCLE_MUTATION_SURFACE_GAP — STALE — candidate; live risk closed by Caddy but gap open
FLEET_INDEX_GAP — STALE — shipped (fleet.rs); correctly closed
GENERALIZED_MASKING_GAP — STALE — shipped (source_error masking, publish.rs)
GENERATION_LINEAGE_GAP — STALE — shipped (migration 026)
HISTORY_COMPACTION_GAP — CONFIRMED — proposed, no impl (needs implementation window)
HOST_TRUST_BOUNDARY — CONFIRMED — doc-only constitutional note, no build
HUMAN_PROCEDURE_OVERLAY_GAP — CONFIRMED — stub
INSTANCE_WITNESS_GAP — STALE — stub; "shipped" was SENTINEL_LIVENESS cross-ref
LATER_AUDIT_RECEIPTS_GAP — CONFIRMED — proposed, calibration record
LOW_TOIL_SELF_OBSERVATION_GAP — STALE — proposed; "shipped" was FINDING_EXPORT dependency
MAINTENANCE_DECLARATION_GAP — STALE — shipped V1 (migration 045, overlay)
NON_WITNESS_AUXILIARY_TABLES_GAP — CONFIRMED — candidate, non-binding
NOTIFICATION_INHIBITION_GAP — CONFIRMED — stub
NOTIFICATION_ROUTING_GAP — CONFIRMED — stub
NQ_CLAIM_SUPPORT_RECOGNITION — CONFIRMED — resolved as recognition (no code), stale_closed apt
NQ_NS_CHANNEL_SPLIT_NQ_SIDE — CONFIRMED — candidate, non-binding
NQ_ON_NQ_OPERATIONAL_CLAIMS_GAP — CONFIRMED — proposed-candidate
OBSERVATION_PLANE_GAP — STALE — candidate; "shipped" was EVIDENCE_LAYER cross-ref
OBSERVER_DISTORTION_GAP — CONFIRMED — proposed
OPERATIONAL_INTENT_DECLARATION_GAP — STALE — shipped V1 (migrations 041–043, overlay)
OPERATION_IDENTITY_CANDIDATE — CONFIRMED — candidate, non-binding
OPERATOR_ATTESTATION_GAP — STALE — candidate; "shipped" was sibling refs
PORTABILITY_GAP — CONFIRMED — proposed, no cfg gating
PREMISE_DEGRADED_GAP — STALE — proposed; inventory said closed (no impl)
PRESSURE_HARM_LOSS_RECOVERABILITY_GAP — CONFIRMED — candidate, non-binding
PRIOR_ART_IMPORT_GAP — STALE — candidate; inventory said closed (nothing shipped)
PROOF_CARRYING_DENIAL_CANDIDATE — STALE — candidate; inventory said closed
PROPAGATION_SCOPE_CANDIDATE — CONFIRMED — candidate, non-binding
QUERY_TARGET_PRIMITIVE_GAP — CONFIRMED — candidate, non-binding
README — CONFIRMED — index/vocabulary doc, non-binding
REGIME_FEATURES_GAP — CONFIRMED — shipped (migration 030, 97 tests) matches
REMOTE_SURFACE_AUTH_AND_STANDING_GAP — CONFIRMED — candidate, non-binding
SENTINEL_LIVENESS_GAP — CONFIRMED — shipped (liveness.rs) matches
SILENCE_UNIFICATION_GAP — STALE — proposed, only partial substrate; inventory said closed
SPENDABILITY_TESTIMONY_GAP — STALE — candidate; inventory said closed (no code)
SQL_DERIVED_FINDINGS_GAP — STALE — proposed; closure lang was README vocabulary
STABILITY_AXIS_GAP — CONFIRMED — shipped (migration 028, 7 tests) matches
STORAGE_BACKEND_GAP — CONFIRMED — proposed (contract only)
SUBSTRATE_COVERAGE_DECLARATION_GAP — CONFIRMED — candidate, non-binding
SUBSTRATE_PRIOR_ART_NEIGHBORS — CONFIRMED — candidate, recognition-only
SURFACE_TYPED_REVOCATION_CANDIDATE — CONFIRMED — candidate, non-binding
TABULAR_DECLARED_CONTEXT_INPUT_GAP — STALE — candidate; inventory said closed
TESTIMONY_DEPENDENCY_GAP — STALE — shipped V1 (masking rules); status field garbled
TESTIMONY_OBSERVABLE_NOT_CONSTRUCTIBLE_GAP — CONFIRMED — containment vessel, open
TIME_BASIS_POISONING_GAP — STALE — proposed; inventory said closed (no code)
WITNESS_CLAIM_SCOPE_GAP — STALE — partial (preflight migrated, rest open); not closed
WITNESS_EVALUATOR_BOUNDARY_GAP — STALE — partially resolved (crate split); rest open
WITNESS_IDENTITY_AND_ABSENCE_GAP — STALE — candidate; inventory said closed
WITNESS_PATH_ASSURANCE_GAP — STALE — candidate/parked; inventory said closed
WRITE_TX_INSTRUMENTATION_GAP — CONFIRMED — proposed, no impl
ZFS_COLLECTOR_GAP — STALE — partial (5/9 detectors, migrations 031–032); not fully closed

### atproto-nutrition (21): C=13 S=7 W=0 NH=1

driftwatch atproto-labeler-backport — CONFIRMED — candidate, non-binding
driftwatch cold-path-parquet-duckdb — STALE — candidate; "in flight" was Phase 0 only
driftwatch cold-path-phase-3.5-forward-parquet — STALE — candidate; "just closed" was WAL fixes
driftwatch cold-path-update-2026-05-07 — CONFIRMED — still candidate, per-tripwire status
driftwatch facts-export-consumer-inventory — CONFIRMED — scoping doc, open
driftwatch facts-export-duckdb-productionization — CONFIRMED — proposed, prod flag off
driftwatch facts-export-duckdb-snapshot-001 — NEEDS-HUMAN — ratified+implemented same day, no closure note
driftwatch formal-claim-admissibility-pipeline — STALE — candidate; "closed in two phases" was criteria
driftwatch log-structured-artifact-system — CONFIRMED — planning sketch, candidate
driftwatch off-host-backup — CONFIRMED — Open gap (no backup exists)
driftwatch single-writer-invariant — CONFIRMED — candidate; naive impl failed acceptance
driftwatch storage-layout — STALE — Open gap; "resolved" was acceptance criteria
labelwatch KNOWN_GAPS — CONFIRMED — protocol-limitation doc, non-actionable
labelwatch forward-note-authority-effect-report-lenses — CONFIRMED — forward note, candidate
labelwatch authority-effect-inference-v0 — CONFIRMED — ratified shape + companion impl
labelwatch authority-effect-triage-001 — CONFIRMED — ratified spec, impl in progress
labelwatch derive-workload-isolation — STALE — structural fix shipped; spec not updated
labelwatch report-generation-workload-isolation — CONFIRMED — partial closure, candidates open
labelwatch reference-role-taxonomy — STALE — candidate; claimed_status factually wrong (no closure lang)
labelwatch rejection-note-social-function-axis — STALE — REJECTED (decided/closed), not open
reference-labeler single-writer-invariant — CONFIRMED — candidate; naive impl failed

### scheduler (16): C=8 S=4 W=4 NH=0

GAP-attention-state — CONFIRMED — identified (open)
GAP-backup-restore — CONFIRMED — Draft, 17 open questions
GAP-deferred-run-split — STALE — landed (tests + capture/reconcile verbs); shipped
GAP-escalation — CONFIRMED — identified, partially specified
GAP-governor-contract — STALE — top open, but pipe-through subsection landed (commit 61a5789)
GAP-imported-basis-freshness — STALE — landed (3 commits, 8 tests green); shipped
GAP-incident-modes — WRONG — open; closure words were incident-state enum vocabulary
GAP-mcp-authority — CONFIRMED — identified, partially specified
GAP-nightshift-coordination-mode — CONFIRMED — proposed matches
GAP-nq-activation — CONFIRMED — identified, partially specified
GAP-nq-nightshift-contract — WRONG — open; claimed_status was NQ finding-status schema values
GAP-parallel-ops — WRONG — open; "observed" was a reliance-class example value
GAP-silence-aware-posture — STALE — Slice C.1 landed (posture_class.rs, 8 tests)
GAP-storage — CONFIRMED — stance fixed, impl deferred
GAP-temporal-obligation-tracking — WRONG — working gap, no impl; closure words were incident labels
NQ_NS_CHANNEL_SPLIT_NS_SIDE — CONFIRMED — candidate, non-binding

### continuity (13): C=7 S=6 W=0 NH=0

CONTINUITY_ORIENT_HOOK — CONFIRMED — proposed, no impl
CONTINUITY_STORAGE_GAP — CONFIRMED — proposed, no tiering impl
CONTINUITY_TIME_DISCIPLINE — STALE — V1 implemented (commit 1d01b91); inventory missed status
CROSS_COMPONENT_RELIANCE_GAP — STALE — proposed but memory_verify_reliance wired; partial ship
CROSS_ISLAND_BRIDGES_GAP — CONFIRMED — proposed, no bridge impl
CROSS_SCOPE_REFERENCE_GAP — STALE — proposed but import_memory landed (1d01b91); partial
ISLANDS_OF_CONTINUITY — STALE — proposed but island warnings/doctor shipped
ISLAND_DISCIPLINE — CONFIRMED — proposed, no DomainPurpose
MEMORY_AUTHORING_TIER_GAP — CONFIRMED — proposed, no AuthoringTier
PREMISE_CONSISTENCY_DOCTOR — STALE — proposed but doctor/premise_consistency.py shipped (5b02650)
README — CONFIRMED — index, statuses consistent
USEFUL_REFUSAL_EXPLAIN — CONFIRMED — proposed, rely_reason still string
WLP_PERSISTENCE_ADAPTER_GAP — STALE — V1 shipped (adapters/wlp.py, 7d9be70); inventory missed corroboration

### rpp (5): C=5

GAP-001-ARCHIVAL — CONFIRMED — Status: open, no impl
GAP-002-OPERATOR-EVIDENCE — CONFIRMED — open, no impl
GAP-003-FEDERATION — CONFIRMED — open, no impl
GAP-004-RECURSIVE-CONTAINMENT — CONFIRMED — open, no impl
GAP-005-BRIDGE-PROJECTION-PROVENANCE — CONFIRMED — open, no impl

### nq-witness (2): C=1 S=1  [validated against ~/git/nq-root/nq-witness]

LIBRARY_NATIVE_WITNESS_GAP — CONFIRMED — candidate (don't build yet); "closed when" is criteria
REMOTE_SUBSTRATE_WITNESS_GAP — STALE — candidate; "shipped" was DURABLE_ARTIFACT dependency, status field exists
