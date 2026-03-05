# Implementation Summary

## Feature Status

**Phase 1-3 COMPLETE** — All 14 steps from BUILD_SPEC.md.
**Multi-Agent v2** — SQLite backend, leases, epochs, permissions, dispatcher protocol.
**Epistemic Governance** — Provenance tracking, confidence modeling, dangerous claim detection.
**Regime Detection** — Operational health monitoring (ELASTIC/WARM/DUCTILE/UNSTABLE).
**Boil Control** — Named presets (GREEN_TEA → BOIL), dwell time enforcement, tripwires.
**Jurisdictions** — Context-aware governance (FACTUAL, SPECULATIVE, ADVERSARIAL, etc.).
**Security Verifier** — Secret detection, SQL/command injection, XSS, path traversal.
**Watch Mode** — Continuous file monitoring with automatic security scanning.
**Claude Code Hooks** — Integration with Claude CLI via pre/post tool hooks.
**Direction Tracking** — Commitments, anchors, Δt measurement, belief graph triangulation.
**Fiction Governor** — Plot threads, scene proposals, prompt generation, narrative constraints, manuscript scanning, similarity matching, context drift detection, fiction guardrails (consent tracking, DSI, AII).
**Non-Fiction Governor** — Corpus management, DOI fetching, citation verification, CFI v0 (contextual frame intrusion detection, 12-frame taxonomy, perspective tracking, normative creep, scope violations).
**Multi-Agent Routing** — Task complexity estimation, model tiers, adaptive routing.
**Failure Provenance** — Scars (constraint hysteresis), shields (input gating), surprise ratio classification. Scar fingerprints: `failure_kind` + `action_type` for action-level novelty gating, separate evidence lifecycles per failure mode.
**Grounding Audit** — Closed-loop hallucination detection, failure mode taxonomy, adaptive policy thresholds.
**Ultrastability** — Ashby-style S₁ adaptation, bounded parameters, pathology detection, freeze/unfreeze.
**Homeostat** — Exploration budgets, adaptive gain scheduling, domain-specific setpoints, 7 exploration contexts.
**Coupling** — Homeostat→Ultrastability one-way protocol, TuningIntent gate, S₁ bounds enforcement, deadband, accumulator, freeze feedback.
**Strict Mode** — Fail-closed governance preset, claim categories, risk-adjusted requirements, commit levels.
**Drift Detection** — Temporal asymmetry defense, premise quarantine, attention skew, coherence gradient.
**Ops Governor** — Runbook verification, time window enforcement, blast radius limits, precondition chains.
**Claim Diff** — Epistemic state change detection, confidence drift, provenance laundering, evidence erosion, silent retraction.
**Claim Signals** — Implicit claim extraction from text, date/entity/quantity/assertive detection, assertiveness scoring, ledger integration.
**Config Profiles** — Named governance presets (strict, permissive, research, production, audit, research_mode), custom profiles, one-command switching.
**Dissent Ledger** — Contradiction persistence, first-class objections, commit gating, confidence trajectories.
**TTL Enforcement** — Recency decay, volatility classes (PERMANENT→EPHEMERAL), revalidation scheduling.
**Quorum State Machine** — Multi-agent consensus protocol, Δt stability windows, claim-type policies, dissent/TTL integration, risk levels, fingerprint gating, escalation/resolution states.
**Cooperative Redundancy** — Independence scoring, method signatures, Jaccard similarity, anti-cheat (source URL overlap), quorum integration.
**Semantic Variety** — Post-commit text transform, phrase bank with meaning tags, cooldown tracking, semantic diff guard, no-rewrite zones, burst repetition detection.
**Auto-Tuning** — Threshold learning from signal distributions, reset effectiveness tracking, setpoint calibration from baselines, budget sweep with Pareto analysis.
**Puppet Mode** — Persona pinning, voice constraints, epistemic posture, semantic diff guard (7 rules + 2 warnings), answer skeleton, 3 builtin profiles, registry.
**Tainted Claim Similarity** — Token-set Jaccard fingerprinting, inverted index candidate retrieval, exact/near-duplicate detection, audit events, configurable thresholds.
**Context Drift Detection** — Narrative mode tracking with hysteresis, genre escalation gating, register shift detection, mode chatter warnings.
**Fiction Guardrails** — Consent tracking (pairwise, scoped), DSI detection, AII with validity profiles, hard constraints (C1-C3), soft penalties (P1-P4).
**Sybil Resistance** — Bloc detection, effective voter count (Neff), per-origin budget coupling, quorum Gate 5 integration, escalation triggers.
**Research Mode** — Non-convergent epistemic control, hypothesis lifecycle (PROBE→TENTATIVE→SUPPORTED→ABANDONED), entropy bounds, dominance caps, evidence impulses with decay, Δt invariant, terminal states.
**ClaimStatus + Epistemic Persistence** — ClaimStatus enum (PROPOSED→SUPPORTED→CONTESTED→…), QuorumStatus mapping, EpistemicLedger SQLite persistence (Schema V4), write-through on mutations, from_dict/from_json deserialization.
**Evidence Type Validation** — Layer 3 evidence kind gating, 4 new EvidenceType values (CALC_RESULT, TEST_RESULT, WEB_SOURCE, LIVE_RETRIEVAL), WRONG_EVIDENCE_TYPE audit failure mode, required_evidence_kinds on PolicyEntry, quorum Gate 6, COLLECTING→STABILIZING evidence gate.
**Premise Rule & Dependencies** — Layer 4 dependency tracking, `depends_on` field on GroundedClaim, cycle-checked DAG, premise rule (HARD claims cannot depend on SOFT/STALE/INVALIDATED), BFS invalidation cascade (HARD→SOFT downgrade), CascadeEvent audit trail, Schema V5, quorum Gate 7.
**Agent Roles & Revalidation** — Layer 5 agent role assignment (PROPOSER/RETRIEVER/FALSIFIER/SYNTHESIZER), role budgets per risk level, quorum Gate 8, periodic revalidation orchestrator wiring TTL→AuditPipeline.
**ClaimStatus FSM Enforcement** — Layer 6 transition table (PROPOSED→SUPPORTED↔CONTESTED→{INVALIDATED|EXPIRED|REFUSED}), 9 TransitionReasons, guard validation, transition history, cascade SUPPORTED→STALE, terminal state HUMAN-only recovery.
**Tone Profiling** — ToneProfile dataclass (28 dimensions), text analysis, ToneChecker with violation detection, tone guidance generation for system prompts, ToneManager persistence, corpus analysis (extract_tone_profile), profile comparison (compare_profiles, ProfileDeviation), CLI commands.
**Autonomous Execution (A1-A4)** — Spine (locked project structure), SpineManager, InvariantType/Invariant/InvariantSet/InvariantLibrary (mechanically verifiable rules), ExecutionBudget/ExecutionUsage/ExecutionState (resource tracking), SessionManager (multi-session persistence), AutonomousExecutor (step-function loop with spine+invariant enforcement, budget checking, checkpointing, resume), Spine CLI (lock/unlock/list/show/activate/check), Session CLI (list/show/delete/handoff), Governor adapters (security, CFI, fiction, nonfiction citation, tone, generic content → Invariant).
**Invariant Store (Deferred 1)** — InvariantSpec (serializable invariant definitions), InvariantStore (file-per-item persistence), VALID_KINDS (6 factory mappings), materialization to live Invariant objects, CLI (add/list/show/remove/check), autonomous run command (noop step execution shell).
**Strategic Test Suites** — Golden-file tests (JSON schema locking for all serialized types), no-laundering regression tests (structural integrity invariants), failure-injection tests (executor fault tolerance), property-based invariant tests (combinatoric fuzzing), contract tests for adapters (interface locking).
**Web UI (Deferred 2, W1-W3)** — GovernorContextManager (isolated per-user/project contexts), ChatBridge (Anthropic/Ollama backend abstraction), GovernorHooks (mode-specific system prompts), refactored FastAPI adapter (OpenAI-compatible API with governor endpoints), Docker multi-user deployment (fiction + code stacks).
**Structured Telemetry (Deferred 4, B2)** — TelemetryCollector (pluggable backends, fail-safe), StructuredLogger (JSONL, date-partitioned, size/retention rotation), TelemetryEvent with typed field helpers, cost/performance/convergence analysis, CSV/JSON export, CLI, executor integration. Convergence telemetry: CONTINUITY_TRACE/CONTINUITY_RESULT events, ConvergenceExecutor + one-shot gate instrumentation, ConvergenceReport.
**Continuity Enforcement (Deferred 5)** — Closed-loop generation control. AnchorRegistry, ContinuityChecker, CorrectionLadder, ConvergenceExecutor, GenerationProvider Protocol, adapter integration, CLI. Continuity Bridges: mode-specific anchor factories, GovernorHooks integration (one-shot gating with telemetry, system prompt enrichment).
**Convergence Auto-Tuning (Deferred 6)** — Offline system identification over convergence traces. ConvergenceAnalyzer, TuningProposal artifacts (28 dataclass types, HardGuards forced-True, Approval forced-requires_human), ProposalStore, 5 admissibility checks, ConvergenceTuner orchestrator, 10 footgun guardrails.
**VS Code Extension (Deferred 3, V1-V4)** — Extracted to [github.com/unpingable/vscode-governor](https://github.com/unpingable/vscode-governor). CLI `governor check` command remains in core. Extension uses CLI wrapper (CLI-based, not daemon-dependent).
**Telemetry Dashboard** — Rich TUI for real-time regime visualization. Phase space plot, regime gauge, energy sparkline, event log, budget panel. Live/replay/demo modes.
**Prometheus Metrics** — Optional Prometheus metrics export at /metrics. Counters, histograms, gauges. TelemetryCollector backend integration.
**Evidence Gate** — Evidence-gated coding harness — kernel-only surface. HARD claims require evidence, contradictions persist, failures are loud. Custody scoring, claim extraction, evidence linking, contradiction detection, exit shape checking.
**W5 Writing Modules (Deferred 2, W5)** — 11 modules: writing_patterns (18 banks), writing_governance, writing_tone (ToneVector 6D, 16 regime envelopes), writing_regime (AffectRegime, RegimeHysteresis), writing_nonfiction (NfClaimLevel, PromotionGate), writing_intent (IntentClassifier, 12 scorers), writing_constraints (11 constraints + Section 14), writing_ticketing (14 prose + 11 code ticket types), writing_puppet, writing_code, writing_router.
**Interactive Violation Resolution (W4)** — Author-friendly chat. Blocking violations present 3 choices: fix/revise/proceed. ViolationResolver with persistent state, resolution command detection, exception logging.
**Code Autopilot** — Intent-based governance. 5 profiles (greenfield/established/production/hotfix/refactor), intent resolution from 6 layers, constraint classes (invariant vs preference), scoped time-limited overrides with receipts, branch heuristics.
**Interferometry** — Multi-model claim comparison with parallel + serial ("yes, and") modes. Claim extraction via SignalExtractor, Jaccard fingerprinting via taint module, claim alignment (shared/unique/conflicting), ledger promotion. JSON persistence.
**Code Interferometry** — Code-specific divergence analysis (Tier 1 + Tier 2). 19 risk marker types (8 security, 6 edge-case, 5 architectural), anchor compatibility (hard/soft conflicts), tier determination, CheckFinding bridge for VS Code. CLI `governor interferometry compare` + `governor code compare` alias. WebUI compare card + Tier 1 warning banner. VS Code `governor.compareModels` command + TreeView Compare section.
**WebUI Backend Toggle** — Runtime backend switching via sidebar dropdown. `GET /v1/backends`, `POST /v1/backends/switch`.
**External Constraint Attachment** — Bind claims to external substrate snapshots (Wikidata/Wikipedia/Scholar). NOT fact verification — structural constraint logging. Discrepancies surfaced, never auto-corrected. Human-only resolution. CLI `governor external {query,attach,bindings,discrepancies,resolve,substrates}`.
**MCP Safety Controls** — Self-protective infrastructure for MCP server. RateLimiter (per-client with backoff), BackpressureController (queue depth limits), CircuitBreaker (fail-fast with recovery), IdempotencyLayer (duplicate request caching), LatencyEnforcer (budget per tool), FaultHandler (sensor vs actuator classification), SafetyController (unified).
**SDK Middleware** — Drop-in governor enforcement for Anthropic SDK. `client = GovernorMiddleware(Anthropic())`. Advisory/blocking/strict modes, claim extraction, anchor checking, security scanning, ledger integration, streaming support, async support.
**Session Continuity** — Capsule-based session management. Resume intent + constraints + authority, NOT chat replay. Three-layer model (Ledger/Workspace/Transcript), fork/promote semantics, checkpoints, content hashing, YAML ledger persistence.
**QA Harness** — Self-validating test infrastructure. CLI smoke tests (all commands), self-governance (governor passes own gates), serialization roundtrip sweep, cross-module lifecycle tests.
**Git Governance** — Integrity invariants at commit boundaries. Artifact integrity, cross-index validation (DOI/version tags), tagging discipline, pre-commit provenance. Profile-based severity (greenfield→production), YAML config, secrets check integration. CLI `governor git-gov {status,check,artifacts,cross-index,pre-commit,verify-tag,set-profile,allowlist}`.
**Context Manifest (Phase 1)** — Prompt assembly as governed artifact. ContextRegion, ContextManifest (three identity kinds: prompt_hash, manifest_hash, build_id), ManifestStore (JSONL with fcntl.flock), build_manifest (pure function, region metadata lookup table), gate receipt emission (verdict=observe, hashes only). Wired into GovernorHooks._build_system_prompt(). CLI `governor context manifest [--json] [--limit N] [--id ID]`.
**Context Compact** — Loss-aware context compaction with receipts. ContextCompactor, CompactionReceipt, DroppedItem, Turn, Conversation types. SimpleSummarizer, RecoveryStore (dropped content retrieval), ReceiptStore (compaction history). Preserves decisions/anchors/constraints/authority, emits explicit loss records. CLI `governor context {status,config,receipts,recover,cleanup}`.
**Perforce Support** — Integrity invariants on explicit authority substrate. P4Client (CLI wrapper, graceful fallback), P4Governor (changelist integrity, lock semantics, immutable releases, DOI mapping). Profile-based severity. P4 trigger integration. CLI `governor p4 {status,check,pre-submit,locks,release tag/check,doi map/verify/list}`.
**Gate Receipt System (receipt_v1)** — Content-addressed decision receipts for governor gates. GateReceipt (8 fields: receipt_id, schema_version, timestamp, gate, verdict, subject_hash, evidence_hash, policy_hash). receipt_id = H(schema_v + gate + subject_hash + evidence_hash + policy_hash) — truly content-addressed, timestamp is metadata. Canonical JSON serialization. Split store: ReceiptStore (JSONL) + EvidenceStore (content-addressed blobs, sharded by hash[:2]). All gates wired: evidence_gate, intent_compiler, pre_commit, wrapper, continuity_checker. CLI `governor receipts {--gate,--verdict,--last,--json,--id,--evidence}`.
**Maude Contract Tests** — Provider-side contract tests verifying Maude's Pydantic models deserialize Governor daemon's actual RPC responses. Docker-compose setup (daemon + test runner, shared Unix socket volume). 19 active tests: health (3), sessions (6), governor (4), dashboard stubs (3), intent compiler (via daemon RPC), streaming (1 skipped). Backend smoke stubs for Claude/Codex/Ollama (skipped by default). Run via `cd integration && bash run.sh`.
**Intent Compiler** — Structured hypothesis-collapse for governance sessions. IntentFormPolicy (TEMPLATE_ONLY/VALIDATED_CUSTOM/CUSTOM_OK), IntentFormSchema (content-addressed), 3 built-in templates (session_start/task_scope/verification_config), mode-gated form policy (blast radius proportional), deterministic compilation (response + schema → Intent + ConstraintBlock), escape classification (4 heuristic categories), gate receipt emission. WebUI: modal overlay with dynamic form rendering, branch visualization, confidence bars. API: `/v2/intent/{templates,schema,validate,compile,policy}`.
**Governor Daemon** — JSON-RPC 2.0 control plane over stdio or Unix socket. Content-Length framing (same as MCP server), async dispatcher, DaemonState (lazy-initialized subsystems), 36 RPC methods: governor.{hello,now,status,selfcheck}, sessions.{list,create,delete,get}, intent.{templates,schema,validate,compile,policy}, receipts.{list,detail}, scars.{list,history}, correlator.{status,history,kvector}, scope.{status,check,escalate,grants}, stability.{status,audit,history}, commit.{pending,fix,revise,proceed,exceptions}, chat.{send,stream,models,backend}. ChatBridge integration with backend auto-detection (env → config file → detection order), streaming via JSON-RPC notifications (chat.delta), GovernorHooks for governed generation, gate receipt emission. Config file support ($GOVERNOR_DIR/daemon.conf, INI format). CLI `governor serve {--stdio,--socket,--print-socket-path,--mode}`. Guvnah integration via child process stdio. Maude integration via Unix socket (RPC client replaces HTTP client). Dockerfile.daemon for containerized deployment.
**Correlator Telemetry** — Capture detection for the governor-as-correlator. K-vector (Throughput, Fidelity, Authority, Cost) — never scalarized. Four capture indicators (Prop 4.2): mode_per_exposure declining, entropy non-increasing under exposure, generated contradiction suppression (Prop 5.3 inversion), commitment loss ratio at representation boundaries. All indicators use hysteresis (consecutive windows). Indicators always computed pre-gate (non-binding context for dashboard); T/A gate controls binding declaration. SHEAR requires low throughput under blocking authority (cost budget → DEGRADED_CAPACITY flag, not SHEAR). Atomic persistence (tmp+rename). CLI `governor correlator {status,history,thresholds,reset}`. Daemon RPC: `correlator.{status,history,kvector}`. Telemetry event types: CORRELATOR_OBSERVATION, CAPTURE_DETECTED.
**Scope Governor** — Locality-first policy with escalation receipts. Constrains *where* agents act, not just *what*. Absence-restrictive containment (missing axis = locked, wildcard must be explicit `"*"`). Expanding rings ladder (`resource→service→region→environment→tenant`), `scope_level()` computes rung from pinned/wildcard pattern. Escalation = widen exactly one axis per request, bridging requirements gate evidence count. Tool contracts bind scope (required/allowed axes, axis smuggling rejected). Time axis uses real timestamps (ISO 8601 UTC, interval inclusion). Write/execute grants log every usage. ScopeGovernor coordinator with persistence (`scope.json`). Gate receipt integration (`scope_escalation` gate). CLI `governor scope {status,contracts,grants,history,usages,check,set,reset}`. Daemon RPC: `scope.{status,check,escalate,grants}`.
**Semantic Stability** — Perturbation-based conditioning audit. Measures how stable the prompt→output mapping is via mechanical perturbations (format jitter, clause reorder, role rewrap, hedge insert, negation probe). Four signals: stiffness (excess_divergence/magnitude, dimensionless), anisotropy (p90/p10 directional sensitivity), basin entropy (output cluster count), commutator drift (perturbation order dependence). Noise floor baseline (intrinsic temperature variance subtracted). Negation probe as positive control (excluded from stiffness). Three divergence proxies (token-set Jaccard, shingled Jaccard, normalized Levenshtein). Dual divergence (raw + boilerplate-stripped). Atomic segment preservation (code blocks, JSON, XML). Call budget guardrail (partial results, never raises). Observational receipts (verdict always "observe"). Deterministic sampling (sha256, never Python hash). JSONL persistence (O_APPEND + fcntl.flock). CLI `governor conditioning {status,history,config,reset}`. Daemon RPC: `stability.{status,audit,history}`.
**Receipt Kernel (libs/receipt_kernel)** — In-repo extracted library for auditable, bounded execution. Append-only hash-chained event ledger (SQLite, WAL mode), 7 event types (RUN_START, STAGE_ADVANCE, EVIDENCE_PUT, EVALUATION, DECISION, REMEDIATION, RUN_FINALIZE), content-addressed blob store with pre-write redaction hook (13 secret patterns) and retention policy (public/sealed evidence classes, TTL-based expiry, hash-only retention after purge, BLOB_EXPIRE receipting). StageGraph with hard-fail on illegal transitions, DEFAULT_STAGE_GRAPH (START→COLLECT→EVALUATE→DECIDE→FINALIZE with REMEDIATE loop). 6 constitutional invariants: ledger.chain_valid (hash chain verification), receipt.completeness (evidence key + blob presence), evaluation.completeness (no silent downgrade), finalization.completeness (clean endings), run.single_finalize (exactly one), run.stage_required_path (required stages in order). Verdict enum (PASS/WARN/FAIL/UNKNOWN, UNKNOWN is failure). Bridge adapter (`receipt_bridge.py`) for parallel event emission from agent_gov workflows. Zero third-party dependencies (stdlib only). See `docs/RECEIPT_KERNEL_CONTRACT.md` and `specs/gaps/RECEIPT_KERNEL_ROADMAP.md`.
**Lane Routing** — Capability-based lane routing with artifact reuse. Lane 0 (ROUTER, no model), Lane 1 (FAST), Lane 2 (GENERAL), Lane 3 (DEEP). LaneContract with must_have/nice_to_have strengths, hard_disallow conditions, ProbePolicy per lane. CascadeExecutor: generate → validate → mitigate-once → re-validate → escalate. ArtifactReuseStore: content-addressed file-per-artifact, default TTLs by kind, final answer reuse OFF by default. Vary key includes model, prompts, tool schemas, doc hashes, policy/config versions. LaneRouter wraps existing Router for complexity estimation, adds lane contracts + probe policy + artifact reuse. ClaimType-based routing internally, task_hint is CLI convenience. Autopilot levels 0 (manual pin), 1 (auto-escalate), 2 (auto-select within lane). Daemon RPC: `lanes.{route,explain,status}`, `chat.send` with `use_lanes` opt-in. CLI `governor lanes {status,route,explain,artifacts}`. routing.py enhanced with capability filter (must_have_strengths, nice_to_have_strengths, min_context_window) on `_select_model_by_strategy()`.
**v2.4 Instrumentation Spine (Phase A)** — Windowed capture detection substrate. SignalEnvelope (23-field frozen dataclass, schema v0.4.0) with quality semantics (ok/partial/unavailable/invalid), canonical JSON hashing, JSONL emission. Three Phase A signals: EXPOSURE_PROXY (weighted denominator from tool dispatch, chat generation, evidence checks, violation evaluations), SILENT_SUPPRESSION (in-path health from multi-source indicators), SIGMA_RATE (endorsement→invalidation pair matching with lag statistics). Shared invariants: observe-only (no blocking), missing≠zero, versioned semantics, receipt-linkable provenance, window boundary semantics (inclusive start, exclusive end). All signals pure derivation (no IO).
**Phase B1 CAPTURE_SELF_DIAGNOSTIC** — Advisory windowed diagnostic consuming Phase A signal envelopes only (layering invariant). Six classifications: normal, watch, warning, instrumentation_compromised, insufficient_history, indeterminate. Suppression precedence (A2 gates all capture scoring). Weighted scoring: sigma rate (0.7) + coverage gap (0.3) → capture_decline_score [0.0, 1.0]. Threshold config versioned as capture-selfdiag-v1 (pre-calibration heuristics, pending Phase C). Completeness = min of input completeness. Input content hashes in annotations for replay provenance. B2 and B3 shipped.
**Phase B2 DECISION_EVIDENCE_LAG** — Per-decision timing classification from gate receipt pairs (receipt-native, parallel to B1, not layered on A signals). Four classifications: SUPPORTED_AS_OF (evidence before decision), BACKFILLED (evidence after), UNSUPPORTED (no linked evidence), POLICY_EXEMPT (gate in exempt list). Tie-break: same-timestamp → SUPPORTED_AS_OF. Multiple evidence → earliest wins. Policy-exempt excluded from rate denominator. value = backfill_rate [0.0, 1.0] or None. Config versioned as decision-evidence-lag-v1 (pre-calibration). Windowed aggregate with lag statistics (mean/p95 backfill delay and support staleness). B3 shipped.
**Phase B3 POSTERIOR_SHIFT_ATTRIBUTION** — Leave-one-out (LOO) influence at the A-signal level. Answers "how much does each Phase A signal influence B1?" by removing each signal and recomputing the entire B1 derivation — no shortcuts. Influence dataclass (signal_id, score_full, score_minus, delta_raw, direction, rank, optional calibration fields). compute_loo_influences() performs n+1 B1 derivations. Non-conservation by design (influences, not partitions). Ranking by |delta_raw| descending, ties broken alphabetically. Optional calibration pass-through (monotone preserves sign). Suppression precedence: removing A2 makes B1 unscoreable, so A2 is always highest influence when present. value = influence_mass (sum of |delta_raw|), unit = "influence". 41 tests.
**Phase C1 REPLAY_HARNESS** — Deterministic offline replay of signal derivations under alternative thresholds or matching rules. Two explicit modes: envelope replay (for layered signals like B1 CAPTURE_SELF_DIAGNOSTIC) and receipt replay (for parallel signals like B2 DECISION_EVIDENCE_LAG). ReplaySpec (frozen config), ReplayManifest (content-addressed input inventory, order-independent hash), DerivationEntry registry keyed on (signal_id, signal_version). Deterministic window ordering (window_start, signal_id). Five skip reasons: missing_inputs, suppressed_excluded, quality_filtered, alignment_failure, derivation_error. Per-window outputs preserve original signal_id and carry replay provenance (phase="2.4C", replay_run_id, source_signal_hash). Summary REPLAY_HARNESS envelope with drift statistics (mean/p95/max abs delta), classification/quality change counts, value direction counts, error messages (capped at 10). Replay sources: prepare_envelope_windows (groups by window, separates inputs from originals) and prepare_receipt_windows (groups receipts with pre-window inclusion). Key invariants: observe-only, no mutation of source artifacts, deterministic (same inputs + same spec → same outputs), provenance closure, missing≠zero.
**Phase C2 CALIBRATION_LAYER** — Apply-only calibration for raw A/B signals. Normalizes signal values to [0,1] using frozen, versioned parameter sets. Three transform methods: identity_clip (pass-through with clamping), linear_minmax (linear rescaling from observed range), log_minmax (log-space rescaling with explicit epsilon_shift — user-pinned policy). CalibrationParamSet (frozen dataclass, MappingProxyType copy+wrap for true immutability, content-addressed param_set_hash). CalibrationMismatchError (exception, not degraded output). Bounds validation: clip bounds enforced in [0,1], inverted bounds refused, bool excluded from numeric check. Quality propagation: ok/partial calibrated normally, unavailable/invalid → value=None. Companion envelope builder (phase="2.4C", unit="normalized", rich provenance in values + annotations). Missing≠zero preserved.
**Phase C2 CALIBRATION_FITTING** — Offline param-set fitting from replay corpus. CalibrationFitSpec (frozen config with content-addressed hash), deterministic sample extraction with explicit exclusion reason taxonomy (8 reasons, one per dropped item, no silent drops). Three method fits: identity_clip (fixed clip bounds), linear_minmax (corpus min/max), log_minmax (domain-filtered with explicit epsilon_shift). FitResult structured return (param_set on success, summary_envelope always). Fit summary as SignalEnvelope (CALIBRATION_FIT_SUMMARY, phase="2.4C") with corpus stats, exclusion counts, provenance hashes, degenerate_fit flag. Suppression-aware by default. No param set emitted on failure. Integration gate: fitted param sets accepted by apply_calibration().
**Phase D PREDICT_REGIME_PREFLIGHT** — Observe-only pre-session regime prediction from calibrated A/B signal envelopes. Pure function, no IO, no hidden state. 6-regime taxonomy (normal, watch, warning, instrumentation_compromised, insufficient_history, indeterminate). Weighted heuristic: capture_diagnostic (0.40) + sigma_rate (0.30) + decision_lag (0.20) + exposure_proxy (0.10). Threshold-based classification with configurable boundaries. Suppression precedence (SILENT_SUPPRESSION + CAPTURE_SELF_DIAGNOSTIC gate all scoring). Confidence from input completeness + quality + hard caps. Missing≠zero (unavailable → value=None). Provenance closure (input envelope hashes, config version, quality statuses). Goldens for all 4 primary regimes. 72 tests.
**Verified Kernel 2.x Hygiene** — Canonicalization monoculture sweep. HashRef value type (`hash_ref.py`) for cross-module hash comparison — parses both `sha256:<hex>` (signals, receipt_kernel) and raw hex (gate_receipt), compares by `(alg, digest)`. Non-canonical `content_hash()` renamed to `dedup_fingerprint()` in 4 modules (session_continuity, scalar_collapse, webui_demo, commitment_transport) to prevent accidental promotion into content-addressing. Canonical implementations (gate_receipt, signals/envelope, receipt_kernel) left unchanged — stored hashes not rewritten. 25 tests.
**Verifier Gate** — Composition boundary for mechanical verification. VerifierSuite (frozen, content-addressed policy_version), Candidate (subject under test), CheckOutcome (tri-state with detail), RunStatus/SuiteVerdict enums. run_suite() executes checks with timeout enforcement, flake detection (quarantine after N consecutive failures), environment fingerprint gating. Gate receipt emission (fail-open). Monotonicity property: superset of checks cannot weaken verdict. VERIFY_SUMMARY signal emission (one envelope per suite run, value = count_block + count_error, timing fragment, source_receipt_ids). 124 tests.
**Governed Activities** — Drift-gated retry substrate. FactObservation (ops-native observation), PreconditionBundle (sorted, fingerprinted), AttemptRecord (per-attempt with etag snapshot), DriftCheckResult (tiered verdict). Tiered drift detection: etag overlap first → fingerprint fallback. DriftVerdict enum (no_drift, etag_diverged, fingerprint_diverged, no_prior, continuity_lost). JSONL store with receipt emission tracking. Etag key = fact_type:subject:source (excludes request_fingerprint by design). 110 tests.
**Signal Plane v1** — SQLite projection cache over instrumentation JSONL. SignalStore with byte-offset cursor, inode/shrink detection, transactional ingest (BEGIN IMMEDIATE), fcntl.flock write exclusivity. project_envelope() pure function. Query/get/tail/stats/rebuild. CLI: `governor signals list|tail|explain|stats|rebuild`, renamed `signals` → `claim-signals` for claim extraction. Daemon RPC: signals.query/get/tail/stats. Tail with --name filter and --poll-ms follow mode. SIGNAL_EMIT_FAILED self-diagnostic (emission failures queryable in same plane, no recursion). 104 tests.
**Process Session Identity** — Canonical process-scoped session_id for signal/receipt correlation. get_session_id() (lazy, stable per process), set_session_id() (override), new_session_id() (fresh without setting global). "gov_{uuid12}" format. DaemonState owns one for its lifetime, exposed in governor.hello RPC. JsonlSink threads session_id into SIGNAL_EMIT_FAILED. 9 tests.
**GATE_CHECK_SUMMARY (first live signal)** — One SignalEnvelope per `gate.check()` invocation. build_gate_check_summary (pure) + build_gate_check_error_summary (for exceptions) + try_emit_gate_check_summary (fail-open wrapper). Wired into CLI `lite_check` with timing. Values: verdict, claims_count, violations_count, warnings_count, has_oracle, timing_ms. Quality: ok for successful checks, unavailable for exceptions. Provenance: source_versions via default_source_versions(), session_id from get_session_id(). 21 tests.
**Signal Provenance Tightening** — source_versions populated with default_source_versions() (governor pkg version + envelope_schema version) across all signal builders. source_receipt_ids monotonic propagation: Phase A accepts, B1 unions from A inputs, C calibration preserves, D unions from all inputs. session_id in Phase D: explicit parameter or inferred from most recent input envelope. 22 tests.
**Provenance Labels** — Lightweight taint tracking for tool outputs. ProvenanceLabel (frozen dataclass, validated source_class + sensitivity_hint). 7 source classes (repo, email, web, secret_store, user_input, generated, unknown), 4 sensitivity hints (none, internal, secret_candidate, unknown). max_sensitivity() conservative propagation (output inherits highest of all inputs). LabelAssigner: mechanical rule-based assignment from tool_id + context, 19 known tool mappings, 15 secret path patterns, 8 internal URL patterns, extensible via extra_tool_map and extra_secret_patterns. Wired into evidence gate as thin annotation layer: labels assigned per check() invocation, included in evidence bundle, never affect gate verdict. 53 tests.
**Egress Gate** — Outbound data-flow policy gate. Policy bridge: classify → populate existing policy types → evaluate → emit gate receipt. PayloadClassifier (monotone: label sensitivity > path patterns > regex > default, never downgrades). DestinationClassifier (URL/IP/hostname parsing, internal TLD detection, RFC 1918, normalization). 6 rules in explicit precedence order: R1 secret deny, R3 unknown dest, R5 allowlisted, R4 internal allow, R2 sensitive external, R6 default. Strict mode = WARN→BLOCK upgrade only. Allowlist = exact or suffix match (leading dot), UNCLASSIFIED only. No USER_REQUESTED bypass (justification recorded, verdict unchanged). Receipt redaction: hashes + classes only, no raw destinations/content/paths. Content probe opt-in (regex secret scan, can only upgrade). Stateless, observe-only. 66 tests.
**CI Lane** — Receipt-producing CI wrapper and policy verifier. `ci_wrap()` runs commands via temp-file capture (no pipe deadlock), emits self-contained `CiReceiptBundle` (evidence inlined). `ci_verify()` checks policy: required kinds, all-pass, SHA consistency, clean state, conflicting-ID detection (identical-bundle dedupe OK). Closed ci_kind vocabulary (8 kinds). Fail-open wrap (exit code always child's), fail-closed verify. CLI: `governor wrap --receipt-out --ci-kind`, `governor ci verify`. 43 tests.
**Sim→Signal SIGMA_RATE** — Second Phase A signal derived from sim receipts alongside EXPOSURE_PROXY. Receipts mapped to ReceiptEvent, match_sigma_pairs() finds endorsement→invalidation pairs, derive_sigma_rate() uses EXPOSURE_PROXY value as preferred denominator. Contradiction scenarios produce nonzero sigma rate. Deterministic (pinned emitted_at). 5 SIGMA_RATE-specific tests.
**Operational SLA Gap Spec** — Two-path availability contracts for governor as control plane. Decision path (fast, p99 budget in ms, fail-closed or fail-open+debt receipt) vs evidence path (slower, accountable, debt tracking). Per-lane SLO routing. Temporal coherence constraints (policy freshness, index lag). Timing fragment on gate receipts (make_timing with monotonic_ns). Gap spec at specs/gaps/OPERATIONAL_SLA.md.
**Test Hardening (v2.0.2)** — Fresh-clone smoke tests (CLI happy path + daemon stdio via subprocess, @smoke marker). Adversarial hook bypass tests (symlinks, script tampering, malformed payloads, unicode tricks, --no-verify documentation). Upgrade path tests (SQLite V1/V3/V5→V6 migration, receipt forward compat, session capsule compat, from_dict robustness). Scale/performance tests (10k receipts, 1k claims, SQLite concurrency with 20 threads, 1MB security scan, 100-anchor continuity check, @scale marker). CI matrix expanded to macOS + Python 3.13.

## Test Counts by Module

### Phase 1-3 — The Gate + Hardening + Integration
| Module | Tests |
|--------|-------|
| receipts.py | 22 |
| producers.py | 32 |
| claims.py | 42 |
| ledgers.py | 35 |
| fsm.py | 33 |
| verifiers.py | 37 |
| cli.py (core) | 25 |
| Fact decay | 11 |
| Conflicts | 12 |
| Envelopes | 15 |
| Feedback | 18 |
| Git hooks | 37 |
| Wrapper | 33 |
| MCP server | 22 |
| **Subtotal** | **389** |

### Subsystems
| Subsystem | Tests |
|-----------|-------|
| Multi-Agent v2 (storage, ledgers_v2, permissions, dispatcher) | 119 |
| Audit Graph | 48 |
| Task Management | 63 |
| Epistemic Governance | 48 |
| Regime Detection | 42 |
| Boil Control | 40 |
| Jurisdictions | 62 |
| Security/Watch/Hooks | 76 |
| Direction Tracking | 57 |
| Multi-Agent Routing | 91 |
| Failure Provenance & Scars | 161 |
| Grounding Audit | 164 |
| Ultrastability | 113 |
| Homeostat | 114 |
| Coupling | 83 |
| Strict Mode | 99 |
| Drift Detection | 107 |
| Ops Governor | 58 |
| Claim Diff | 91 |
| Claim Signals | 75 |
| Config Profiles | 46 |
| Dissent Ledger | 59 |
| TTL Enforcement | 45 |
| Quorum State Machine | 119 |
| Cooperative Redundancy | 38 |
| Semantic Variety | 56 |
| Auto-Tuning | 117 |
| Puppet Mode | 128 |
| Tainted Claim Similarity | 81 |
| Sybil Resistance | 75 |
| Research Mode | 137 |
| ClaimStatus + Persistence | 75 |
| Evidence Type Validation | 86 |
| Premise Rule & Dependencies | 88 |
| Agent Roles & Revalidation | 67 |
| ClaimStatus FSM | 106 |
| Autonomous Execution | 232 |
| Strategic Test Suites | 521 |
| Invariant Store | 79 |
| Web UI (W1-W3) | 91 |
| Structured Telemetry | 151 |
| Continuity Enforcement | 196 |
| Convergence Auto-Tuning | 145 |
| VS Code Extension (extracted repo) | 176 |
| Evidence Gate | 101 |
| Interactive Violation Resolution | 82 |
| W5 Writing Modules | 922 |
| Fiction Governor | 376 |
| Non-Fiction Governor | 281 |
| Interferometry | 47 |
| Code Interferometry | 43 |
| WebUI Backend Toggle | 6 |
| External Constraint Attachment | 63 |
| MCP Safety Controls | 70 |
| SDK Middleware | 36 |
| Session Continuity | 57 |
| QA Harness | 108 |
| Git Governance | 99 |
| Context Manifest | 49 |
| Context Compact | 49 |
| Perforce Support | 71 |
| Gate Receipt System | 70 |
| Maude Contract Tests | 19 (+7 skipped) |
| Intent Compiler | 131 |
| Governor Daemon | 265 |
| Correlator Telemetry | 140 |
| Scope Governor | 182 |
| Semantic Stability | 181 |
| Fresh-Clone Smoke (test_fresh_clone.py) | 8 |
| Hook Bypass (test_hook_bypass.py) | 19 |
| Upgrade Path (test_upgrade_path.py) | 18 |
| Scale / Performance (test_scale.py) | 12 |
| Lane Routing | 149 |
| Receipt Kernel (libs/receipt_kernel) | 89 |
| v2.4 Instrumentation Spine (A0-A3 + B1-B3 + C1-C2 + D) | 908 |
| Verifier Gate | 124 |
| Governed Activities | 110 |
| Signal Plane (signal_store + CLI + RPC) | 104 |
| Gate Check Summary (first live signal) | 21 |
| Signal Provenance (source_versions, receipt_ids, session_id) | 22 |
| Sim→Signal Pipeline (full A→B chain, 5 signal kinds) | 25 |
| Process Session Identity | 9 |
| HashRef (cross-module hash comparison) | 25 |
| Provenance Labels (taint tracking + evidence gate wiring) | 53 |
| Egress Gate (outbound data-flow policy gate) | 66 |
| CI Lane (ci_wrap + ci_verify + CLI) | 43 |

**Total: ~14,559 tests** (14,559 unit + 83 sim + 36 skipped + 24 integration)
