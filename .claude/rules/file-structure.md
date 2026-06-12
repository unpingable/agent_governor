# File Structure

```
src/governor/
├── __init__.py       # Public API exports
├── receipts.py       # FileSnapshot, CmdRun, DiffReceipt dataclasses
├── producers.py      # Receipt-producing functions
├── claims.py         # ClaimType enum, Claim dataclass with validation
├── ledgers.py        # FactLedger, DecisionLedger with decay/conflict detection
├── fsm.py            # State machine: DRAFT→PROPOSED→VERIFIED→APPLIED
├── verifiers.py      # FileVerifier, CommandVerifier, DiffVerifier, etc.
├── envelopes.py      # Operating modes: exploratory vs strict
├── hooks.py          # Git pre-commit hook integration
├── wrapper.py        # Agent wrapper for file write interception
├── mcp_server.py     # MCP protocol server for Claude integration
├── cli.py            # Click CLI with all commands
│
# Multi-Agent v2 (SQLite-backed):
├── storage.py        # SQLite backend with WAL mode, leases, epochs
├── ledgers_v2.py     # SQLiteFactLedger, SQLiteDecisionLedger
├── permissions.py    # AgentPermissions, PermissionManager, profiles
│
# Audit & Task Subsystems:
├── graph.py          # AuditGraph, GraphBuilder, Maltego-style transforms
├── tasks.py          # TaskManager, priorities, labels, milestones, time tracking
│
# Epistemic Governance:
├── epistemic.py      # Provenance, confidence, EvidenceRef, EpistemicLedger
├── regime.py         # OperationalRegime, RegimeSignals, RegimeDetector
├── boil.py           # ControlMode, BoilPreset, BoilController, tripwires
├── jurisdictions.py  # Jurisdiction, JurisdictionManager, context-aware rules
│
# Security, Watch, Claude Integration:
├── security.py       # SecurityVerifier, vulnerability patterns, diff scanning
├── watch.py          # FileWatcher, WatchSession, continuous monitoring
├── claude_hooks.py   # HookConfig, pre/post tool hooks for Claude CLI
├── direction.py      # DirectionLedger, BeliefGraph, commitments, anchors, Δt
├── routing.py        # Router, ModelRegistry, ComplexityEstimator, adaptive routing
├── scars.py          # ScarLedger, failure provenance, scars/shields, hysteresis
├── audit.py          # AuditPipeline, PolicyStore, failure mode classification, adaptive thresholds
├── ultrastability.py # UltrastabilityController, ParameterSpec, PathologyDetector, S₁ adaptation
├── homeostat.py      # Homeostat, ExplorationBudget, EpistemicVitals, TuningDelta, gain scheduling
├── coupling.py       # GovernorCoupling, TuningIntent, one-way Homeostat→Ultrastability protocol
├── strict.py         # StrictModeGate, ClaimCategory, CommitLevel, fail-closed governance
├── drift.py          # DriftDetector, PremiseQuarantine, temporal asymmetry defense
├── claim_diff.py     # ClaimDiffer, ClaimSnapshot, LedgerSnapshot, confidence drift, provenance laundering
├── ci.py             # CI lane: ci_wrap, ci_verify, CiReceiptBundle, CiPolicy, GitState
├── claim_signals.py  # SignalExtractor, SignalMatch, ExtractionResult, implicit claim detection
├── profiles.py       # ProfileManager, ProfileSettings, named governance presets
├── dissent.py        # DissentLedger, Objection, commit gating, confidence trajectories
├── ttl.py            # TTLManager, VolatilityClass, recency decay, revalidation scheduling
├── quorum.py         # QuorumManager, QuorumState, multi-agent consensus, Δt stability, dissent/TTL integration, risk levels, fingerprint gating
├── independence.py   # IndependenceScorer, MethodSignature, Jaccard similarity, anti-cheat, quorum integration
├── semvar.py         # SemVarEngine, PhraseBank, CooldownTracker, SemanticDiffGuard, no-rewrite zones, burst detection
├── auto_tuning.py    # ThresholdTuner, ResetTracker, SetpointCalibrator, BudgetSweeper, AutoTuner, Pareto analysis
├── puppet.py         # PuppetProfile, PuppetRenderer, PuppetDiffGuard, PuppetRegistry, persona pinning, semantic diff guard
├── taint.py          # TaintIndex, Fingerprint, token-set Jaccard, inverted index, recurrence detection
├── sybil.py          # BlocDetector, SybilDetector, NeffResult, ProvenanceVector, OriginBudgetTracker
├── research.py       # ResearchLedger, Hypothesis, EntropyMonitor, DominanceMonitor, TimescaleMonitor
├── egress_gate.py    # EgressGate, EgressRequest, EgressResult, PayloadClassifier, DestinationClassifier, policy bridge
│
# Autonomous Execution (Phase A1-A4):
├── spine.py          # Spine, SpineManager, locked project structure, proposal verification
├── invariants.py     # InvariantType, Invariant, InvariantSet, InvariantLibrary, mechanically verifiable rules
├── execution.py      # ExecutionBudget, ExecutionUsage, ExecutionState, SessionManager, checkpoint/resume
├── executor.py       # AutonomousExecutor, StepResult, ExecutorConfig, ExecutionEvent, step-function loop
├── adapters.py       # Governor adapter invariants, thin wrappers (security, CFI, fiction, nonfiction, custom)
├── invariant_store.py # InvariantSpec, InvariantStore, VALID_KINDS, persistent invariant management
├── context_manifest.py # ContextRegion, ContextManifest, ManifestStore, build_manifest, prompt-as-governed-artifact
├── context_manager.py # GovernorContext, GovernorContextManager, isolated per-user/project contexts
├── chat_bridge.py     # ChatBridge, OllamaBackend, AnthropicBackend, GovernorHooks, backend abstraction
├── telemetry.py       # TelemetryCollector, StructuredLogger, TelemetryEvent, cost/performance analysis, JSONL export
├── continuity.py      # AnchorRegistry, ContinuityChecker, CorrectionLadder, ConvergenceExecutor, closed-loop generation control
├── continuity_bridges.py # Mode-specific anchor factories: fiction bible, nonfiction corpus, puppet profile → Anchor lists
├── convergence_tuning.py # ConvergenceAnalyzer, ConvergenceTuner, ProposalStore, TuningProposal, admissibility checks
├── check.py          # Position, Range, CheckFinding, CheckResult, run_check (unified check aggregation for VS Code)
├── viewmodel.py      # GovernorViewModel (schema v2), 8 section builders, read-only state derivation, V1 compat
├── evidence_gate.py  # EvidenceGate, evidence-gated coding harness, claim extraction, evidence linking, custody scoring
├── gate_receipt.py   # GateReceipt, content-addressed decision receipts, EvidenceStore, ReceiptStore, canonical JSON
├── hash_ref.py       # HashRef: cross-module hash comparison (prefixed vs raw hex normalization)
├── provenance_labels.py # ProvenanceLabel, LabelAssigner, sensitivity propagation, secret/internal URL patterns
├── violation_resolver.py # ViolationResolver, PendingViolation, ResolutionAction, ExceptionRecord, fix/revise/proceed actions
├── interferometry.py  # Interferometry: parallel + serial multi-model claim comparison, alignment, signals, ledger promotion, store
├── code_interferometry.py # Code interferometry: risk markers (19 types), anchor conflicts, tier determination, CheckFinding bridge
├── correlator_telemetry.py # Correlator telemetry: capture detection, K-vector (T,F,A,C), regime classification, hysteresis
├── session_continuity.py # Session continuity: capsule-based session management, fork/promote, checkpoints, ledger/workspace persistence
├── git_governance.py     # Git governance: artifact integrity, cross-index validation, tagging discipline, pre-commit provenance
├── context_compact.py    # Context compact: loss-aware compaction with receipts, recovery store, summarizer
├── perforce.py           # Perforce governance: P4Client, changelist integrity, lock semantics, immutable releases, DOI mapping
├── daemon.py             # Governor daemon: JSON-RPC 2.0 over stdio/Unix socket, 36 RPC methods, DaemonState
├── scope.py              # Scope Governor: locality-first policy, escalation receipts, tool contracts, absence-restrictive containment
├── semantic_stability.py # Semantic stability: perturbation-based conditioning audit, 4 signals, noise floor, basin clustering, JSONL store
├── session.py            # Process-scoped session identity: get_session_id, set_session_id, new_session_id
├── signal_store.py       # Signal Plane v1: SQLite projection cache, byte-offset cursor, query/tail/stats/rebuild
├── verifier_gate.py      # Verifier gate: composition boundary, VerifierSuite, VERIFY_SUMMARY signal emission
├── governed_activity.py  # Governed activities: drift-gated retry, FactObservation, PreconditionBundle, AttemptRecord
│
# Runtime Supervisor (supervised agent sessions):
├── runtime/
│   ├── __init__.py                  # Public API exports
│   ├── events.py                    # CanonicalEvent, EventBus, EventKind, JSONL persistence
│   ├── adapter.py                   # RuntimeAdapter protocol, AdapterCapabilities, LaunchConfig
│   ├── supervisor.py                # SessionSupervisor, SessionRecord, Intervention, RuntimeFacet
│   ├── promotion.py                 # Promotion, detect_workspace_changes, approve/reject/revert
│   └── adapters/
│       ├── __init__.py
│       ├── claude_code.py           # ClaudeCodeAdapter: supervised mode, Unix socket hooks
│       └── gemini_cli.py            # GeminiCliAdapter: supervised mode, BeforeTool/AfterTool hooks
│
# v2.4 Instrumentation Spine (Phase A + B + C):
├── signals/
│   ├── __init__.py                  # Public API: SignalEnvelope, derivation functions
│   ├── envelope.py                  # SignalEnvelope, QualityStatus, DerivationType, canonical_json
│   ├── emit.py                      # SignalEmitter + JsonlSink + SIGNAL_EMIT_FAILED self-diagnostic
│   ├── exposure_proxy.py            # A1: EXPOSURE_PROXY weighted denominator
│   ├── silent_suppression.py        # A2: SILENT_SUPPRESSION in-path health
│   ├── sigma_rate.py                # A3: SIGMA_RATE endorsement→invalidation matching
│   ├── capture_self_diagnostic.py   # B1: CAPTURE_SELF_DIAGNOSTIC advisory diagnostic
│   ├── decision_evidence_lag.py     # B2: DECISION_EVIDENCE_LAG per-decision timing
│   ├── replay_harness.py            # C1: REPLAY_HARNESS deterministic offline replay
│   ├── replay_sources.py            # C1: Replay source adapters (envelope + receipt grouping)
│   ├── calibration_methods.py       # C2: CALIBRATION_LAYER transform functions (identity_clip, linear_minmax, log_minmax)
│   ├── calibration_layer.py         # C2: CalibrationParamSet, apply_calibration, companion envelope builder
│   ├── calibration_fitting.py       # C2: CalibrationFitSpec, extract_fit_samples, fit_param_set_from_corpus, FitResult
│   ├── posterior_shift.py           # B3: POSTERIOR_SHIFT_ATTRIBUTION LOO influence
│   ├── gate_check_summary.py       # GATE_CHECK_SUMMARY live signal (first production emission)
│   └── predict_regime.py           # D: PREDICT_REGIME_PREFLIGHT observe-only regime prediction
│
# W5 Writing Modules (Deferred 2, W5):
├── writing_patterns.py    # 18 pattern banks for governance/tone/regime detection
├── writing_governance.py  # GovernanceVisibilityScorer, GovernanceLeakDetector, SmoothingSuppressor, ExitShapeChecker
├── writing_tone.py        # ToneVector (6D), ToneEnvelope, 16 regime envelopes, ToneCollision, ToneStabilityController
├── writing_regime.py      # AffectRegime, RegimeVector, RegimeHysteresis, RpScorer, TragedyConstraints
├── writing_nonfiction.py  # NfClaimLevel, PromotionGate, VelocityController, EpScorer, ReScorer, HedgeCalibrator
├── writing_intent.py      # IntentClassifier (6 categories), 12 ancillary regime scorers, RegimeCollision
├── writing_constraints.py # 11 structural constraints + Section 14 causal narration resistance
├── writing_ticketing.py   # Ticketing layer: 14 prose + 11 code ticket types, recurrence, routing
├── writing_puppet.py      # Extended puppet constraints from puppet.md spec
├── writing_code.py        # Code-specific constraints from code.md spec
├── writing_router.py      # Writing-aware routing from specs
│
# Lane Routing:
├── lanes.py               # Lane enum, LaneContract, RoutePlan, ArtifactReuseStore, CascadeExecutor, LaneRouter
│
# Intent Compiler:
├── intent_compiler.py     # IntentFormPolicy, IntentFormSchema, compile_intent, BUILTIN_TEMPLATES, receipt emission
│
# Receipt Kernel Bridge (parallel audit trail):
├── receipt_bridge.py      # ReceiptKernelBridge: emit hash-chained events to receipt_kernel SQLite store
│
# Surface inventory (indexed 2026-06-11 doc-sync; grouped by concern).
# These shipped + tested before the module map caught up; see working/doc-sync-triage-2026-06-11.md.
#
# Constellation adapters (AG → sibling repos):
├── standing_client.py     # StandingClient: request standing receipts from ~/git/standing (SPEC harness)
├── wicket_client.py       # WicketClient: admissibility preflight via ~/git/wicket (ActorStanding, ScopeAssertion, Revocation)
├── linear_accountant_client.py # CapacityRequest/Consume against ~/git/linearaccountant; never mints (SPEC harness)
├── nightshift_adapter.py  # Night Shift Governor adapter: AuthorityLevel, BlastRadius, ToolClass, event→ReceiptRole
├── codex_hooks.py         # Codex CLI hooks: parse/classify codex events, extract response/usage/error
├── governed_dispatch.py   # Enforcement membrane for composition governance: PreflightRequest/Decision, DispatchContext
├── cooked_context_orchestrator.py # SPEC harness orchestrator: chain admission→capacity→consume receipts; origin fence (OperationalConsumed/DemonstratedConsumed/confer_operational_effect)
├── standing_spendability.py # StandingSpendabilityGate: two-clock temporal-lapse seam (standing→spendability edge); StandingWindow (gap on a typed monotonic basis), standing_before_spendability_not_bounded
├── clock_witness.py       # MonotonicReading/WallWitness + elapsed_ns (the only licensed subtraction; refuses incompatible source/epoch/backwards). "A gap is a difference between compatible clock witnesses, not numbers."
│
# Governance core (extensions):
├── admissibility.py       # Admissibility Gate push-back: Unknown/Severity/ResolvableBy, assumption status (`admit`)
├── chain_gate.py          # Composition-aware capability gating (GOV-GAP-CHAIN-001): CapabilityClass, TrustDomain, DataSensitivity
├── constraint_compiler.py # Pre-execution constraint projection: ConstraintKind/Severity, ScarClass, ResolvedConstraint
├── constraint_gate.py     # Formal admissibility via Z3 verifier sidecar: ConstraintGate, ConstraintGateResult
├── policy_engine.py       # Abstract policy-evaluation substrate: PolicyVerdict, Capability, ObligationKind (deep dep)
├── policy_ir.py           # Policy Intermediate Representation: ControlSlot, ControlVocabulary, SlotSet, RenderResult
├── claim_status.py        # Claim Status Dashboard: ClaimStatusSummary/Detail, claim-health weather report
├── claim_correlation.py   # Claim↔Receipt correlation layer: verification status, claim keys/fingerprints
├── docket.py              # Adjudicator framing for violation resolution: DocketCase, PrecedentRecord, DocketManager
├── doctrine.py            # Read-only Governor→Continuity doctrine consultation: DoctrineEntry, consult, emit receipt (`doctrine`)
├── doc_governance.py      # Docs as governed artifacts: GovDoc, DocLink, scope/status/link checks (`doc`)
├── overrides.py           # Code Autopilot overrides: OverrideManager, OverrideReceipt, scoped pressure
├── reservations.py        # Work-reservation primitives (CLI+daemon): scope conflict, lease ownership
├── risk_function.py       # Risk potential function (scalar V): RiskSignal/Weights/Components, PolicyAction (`risk`)
├── mode_detection.py      # Bayesian mode posterior + drift: DomainMode, ModePosterior, DriftAlert
├── preflight.py           # Governor preflight checks: dir/envelope/regime/approved-files (`preflight`)
├── phase_control.py       # Run phases with budget locks + novelty debt: Phase, PhaseBudget, NoveltyDebt (`phase`)
├── quorum_ext.py          # Severity-based quorum gating (AG2 2.1-D): QuorumRequirement, Confirmation (`quorum-ext`)
├── plan_review.py         # Authority boundary between speech and action: Proposal, Agenda, SectionDecision
├── detector_handoff.py    # Detector decision → gate receipt: ControllerAction, HandoffRecommendation, OracleResult
├── deployment_profiles.py # Authority classes with capability tokens: AuthorityClass, CapabilityToken, RateLimit (`deploy`)
├── config_effective.py    # Registry-driven effective config: ConfigKeySpec, ConfigSource/Entry, redaction class
├── slim_mode.py           # Single-developer governance for high-iteration work: SlimMode, anchor/spine inference (`slim`)
├── external.py            # External Constraint Attachment: bind claims to Wikidata/Wikipedia/Scholar (structural, not fact-check)
│
# Control / tuning / health:
├── control_theory.py      # Risk formalization R_t=(P_t·D_t)/E_t: Regime, ToolPowerMetrics, Feedback/Evidence components
├── autopilot.py           # Code Autopilot profile config: ViolationDefault, ApprovalPath, AnchorStrictness, ChangeLimit
├── coherence_budget.py    # Coherence Budget Index (CBI) health metric: CBIStatus, ClosureDecision, InvariantID (`cbi`)
├── hysteresis.py          # Anti-churn / controller-chatter prevention (AG2 2.1-C): mode-transition + replan tracking (`hysteresis`)
├── scalar_collapse.py     # Eigenstructure-evaporation detection in governance chains: CollapseSignals/Report (`collapse`)
│
# Observability / telemetry / diagnostics:
├── instrument.py          # Instrumented execution (AG2 Layer 0): EventKind, ClaimModality, DiffFinding (`instrument`)
├── metrics.py             # Severity-weighted coverage/efficiency metrics: MetricClaim, ClaimCoverage, CoverageSnapshot (`metrics`)
├── prometheus.py          # Prometheus metrics export: GovernorMetrics, MetricsServer, PrometheusTelemetryBackend
├── measurement_integrity.py # Tidepool defense / measurement trust: ToolOutput, TrustResult, Alert, freeze reasons (`measure`)
├── gate_heartbeat.py      # Detect when the evidence gate stops being called: HeartbeatStatus, missed-call computation
├── staleness.py           # Time-bounded verification + artifact-mutation tracking: ClaimFreshness, StalenessDetector
├── detector_integration.py # Temporal-coherence signals as governor evidence: RawDetectorSignal, CollapsedSignal (`detector`)
├── status_rollup.py       # Single truth object for the operator one-pager: build/render StatusRollup
├── operator_snapshot.py   # Shared operator doctor+trace logic: CheckItem, TraceEvent, receipt-event collection
├── dashboard_ux.py        # Run-centric governance dashboard backend: StreamEvent, RunVerdict/State (`dashboard-ux`)
├── trace_recorder.py      # Poll gate-receipt JSONL → run artifacts: ReceiptRecorder
├── replay.py              # Replay run artifacts under different knobs, diff outputs: ReplayAPI, RunArtifact, ReplayClock
├── capture.py             # Detect structured intent in chat, stage for promotion: CaptureClassifier, CaptureReceipt
├── selfcheck.py           # Automated deployment health verification: run_selfcheck + structure/store checks (`selfcheck`)
│
# Evidence / receipts / provenance:
├── evidence_store.py      # SQLite evidence + agent-run provenance store: RunProvenance, EvidenceStore
├── oracle_pytest.py       # Non-linguistic evidence from real pytest runs: OraclePytestLog, JUnit parse, env/git capture
├── receipt_v1_bridge.py   # Dual-emit receipt_v1 alongside gate_receipt: ReceiptV1Bridge, chain tracking
├── release_taint.py       # Publish-boundary taint assessment for kernel runs: TaintReason, RunTaint, PublishThreshold
├── commitment_transport.py # Representational invariance under compression: Commitment, CommitmentTransport, ShearReport (`transport`)
│
# Content grounding helpers:
├── chrono.py              # Temporal grounding for generated content: ChronoFinding, current-year/chrono invariant checks
├── identity.py            # Name grounding for generated content: IdentityFinding, match types, normalization
├── clud.py                # CLUD clarity sensor: compression-based precision detection (ClaimKind, DeltaClass, ThresholdSet)
│
# CLI infrastructure:
├── cli_backend.py         # Sync RPC client CLI→daemon: frame read/write, sync_rpc_call (`backend`)
├── cli_chat.py            # Governed conversational CLI with backend switching: ChatConfig, backend probes (`chat`)
├── cli_operator.py        # Operator front-door commands: doctor/trace surfaces, envelope/regime probes
├── cli_group.py           # CuratedGroup: Click group with categorized help
├── cli_friendly.py        # Friendly CLI layer: mode/story helpers, fiction shortcuts
│
# Session / context:
├── session_store.py       # Persistent chat-session management: ChatSession, SessionMessage (≠ session.py / session_continuity.py)
│
# Demo / SDK:
├── webui_demo.py          # Scripted reproducible WebUI screenshots: DemoScenario, DemoStep, DemoManifest
├── sdk.py                 # Anthropic SDK drop-in enforcement middleware: GovernorMiddleware, EnforcementMode
├── mcp_safety.py          # MCP server self-protection: RateLimiter, ShedPolicy, backpressure (feature: MCP Safety Controls)
│
# Experimental / research (reachable via CLI but pre-stable — not platform-guaranteed):
├── epistemic_evasion.py   # Discourse-pattern evasion detection: EvasionOperator, FailureMode, EvasionResult (`evasion`)
├── temporal_attack.py     # Δt-aware security surface scanner: TemporalMarker, ScanResult (`temporal`)
├── spectral_stability.py  # Coupling-matrix verification for governance topology: CouplingMatrix, hotspots (`stability`)
├── why.py                 # `why <receipt-id>` join surface: ChainLink, WhyResult, refusal-kind/origin-mode chains
├── research_store.py      # Epistemic-debt tracking for research writing: ResearchClaim, assumption/uncertainty status
├── research_why.py        # Per-turn injected-vs-referenced analysis: WhyOverlay, source-ref extraction
├── drill_runner.py        # Drill harness consuming genuine NQ FindingSnapshot (D0-Origin)
├── drill_poster.py        # Show-surface poster for drills (D0e): seven-invocation runs, assertion aggregation
├── demo_refused_spend.py  # Demo Act-1 depth surface (W1 item 3): temporal-lapse contrast (twin passes / impostor refused), receipt-forward render + integrity tripwire; `demo/refused-spend.sh` entry
├── proof_seam.py          # Proof seam (W1 item 4): refusal class → verified Lean PUBLIC-SHIPPED class-boundary theorem (hero → Freshness.expired_not_fresh, adjudicated clock-agnostic w/ monotonic instantiation recorded); honest class-not-instance framing; NO_KERNEL_THEOREM gaps marked, not borrowed
├── demo_opa_contrast.py   # Demo Act-2.5 OPA contrast shim (W1 item 5): same incident, OPA allows the unwitnessed input / custody refuses upstream; verdict persisted at <root>/opa_verdict_receipt.json; `demo/opa-contrast.sh` entry
├── demo_interrogate.py    # Demo Act-2 receipt interrogation (GOV_GAP_ACT_TWO_RECEIPT_INTERROGATION_001): six-question transcript cross-examining the Act-1 corpse (why chain-walk, evidence bundle, clock witness, OPA verdict, honest absence); `demo/interrogate.sh` entry
│
# Legacy (v0.1, kept for reference):
├── core.py           # Original AgentGovernor class
├── ledger.py         # Original CodebaseLedger
├── validators.py     # Original validators
└── types.py          # Original type definitions

# WebUI extracted to separate repo: ~/git/gov-webui (github.com/unpingable/governor_webui)

src/fiction_governor/
├── __init__.py       # Public API exports
├── types.py          # Character, WorldRule, BannedTrope, CanonEvent, PlotThread, SceneProposal
├── bible.py          # Bible ledger (characters, world rules, tone, tropes)
├── canon.py          # Canon ledger (events, relationships, threads, proposals)
├── state.py          # CharacterState (motivations, beliefs, constraints)
├── verifiers.py      # InCharacterVerifier, TropeVerifier, ToneVerifier, NarrativeVerifier
├── manuscript.py     # ManuscriptScanner for auto-populating canon from text
├── similarity.py     # TF-IDF/embedding similarity for trope, voice, tone matching
├── context_drift.py  # Context drift detection with hysteresis-based mode transitions
├── guardrails.py     # Consent tracking, DSI, AII, hard constraints, soft penalties
└── cli.py            # fiction-gov CLI (thread, proposal, prompt, drift, guardrails commands)

src/nonfiction_governor/
├── __init__.py       # Public API exports
├── types.py          # Source, Concept, Position, WritingClaim
├── doi.py            # DOI metadata fetching (CrossRef/DataCite)
├── corpus.py         # Corpus ledger (your papers, concepts, positions)
├── verifiers.py      # CitationVerifier, TerminologyVerifier, ConsistencyVerifier
├── tone.py           # ToneProfile, ToneChecker, ToneManager, corpus analysis, profile comparison
├── cfi.py            # CFI v0: NonfictionFrame (12), Perspective, CFIDetector, frame intrusion detection
└── cli.py            # nonfiction-gov CLI (source, concept, position, verify, tone, cfi commands)

src/ops_governor/
├── __init__.py       # Public API exports
├── types.py          # Runbook, TimeWindow, BlastRadius, Precondition
├── verifiers.py      # RunbookVerifier, TimeWindowVerifier, BlastRadiusVerifier, PreconditionChainVerifier
├── policy.py         # PolicyRegistry, operational policy enforcement
└── cli.py            # ops-gov CLI

# End-to-end / hardening tests (v2.0.2):
# tests/test_fresh_clone.py      # 8 tests: CLI happy path + daemon smoke (@smoke)
# tests/test_hook_bypass.py      # 19 tests: symlink, tampering, malformed, unicode, --no-verify
# tests/test_upgrade_path.py     # 18 tests: SQLite migration, receipt compat, from_dict robustness
# tests/test_scale.py            # 12 tests: 10k receipts, 1k claims, SQLite concurrency, 1MB scan (@scale)

integration/
├── docker-compose.contract.yml  # Governor + test runner services
├── Dockerfile.contract           # Test runner image (installs maude at runtime)
├── pytest.ini                    # asyncio_mode = auto
├── conftest.py                   # GovernorClient fixture, wait_for_governor
├── run.sh                        # One-command entry point
├── test_contract_health.py       # 3 tests: HealthResponse shape
├── test_contract_sessions.py     # 7 tests: session CRUD + message append
├── test_contract_governor.py     # 4 tests: /governor/now + /governor/status
├── test_contract_dashboard.py    # 7 tests: v2 dashboard + runs
├── test_contract_streaming.py    # 1 test: SSE streaming (skipped by default)
├── test_backend_claude.py        # 2 tests: Claude Code smoke (skipped by default)
├── test_backend_codex.py         # 2 tests: Codex smoke (skipped by default)
└── test_backend_ollama.py        # 2 tests: Ollama smoke (skipped by default)

# Receipt Kernel (in-repo extracted library):
libs/receipt_kernel/
├── pyproject.toml                  # Standalone package (stdlib-only deps)
├── README.md
├── src/receipt_kernel/
│   ├── __init__.py                 # Public API: Verdict, BlobRef, RetentionPolicy, etc.
│   ├── types.py                    # Verdict, BlobState, EvidenceClass, RetentionPolicy, InvariantResult, Reason
│   ├── envelope.py                 # Event envelope: make_envelope, seal_envelope, canonical_json, compute_hash
│   ├── stages.py                   # StageGraph (hard-fail on illegal transitions), DEFAULT_STAGE_GRAPH
│   ├── store_sqlite.py             # SqliteReceiptStore: append-only, hash-chained, WAL mode, redaction hook
│   ├── redact.py                   # Redaction hook: pattern-based secret detection, RedactionReport
│   ├── retention.py                # RetentionPolicy enforcement, find_expired_blobs, purge_expired
│   └── invariants/                 # 13 invariants in 3 groups (structural 6 / hallucination 6 / oracle 1)
│       ├── __init__.py             # All 13 invariant exports
│       │   # --- structural (6) ---
│       ├── ledger_chain_valid.py   # Hash chain integrity (seq contiguity, prev_hash, event_hash)
│       ├── receipt_completeness.py # Required evidence keys present + blobs retrievable
│       ├── evaluation_completeness.py  # Attested evaluation, no silent downgrade
│       ├── finalization_completeness.py # Clean endings, decision ref, last event
│       ├── run_shape.py            # single_finalize + stage_required_path (2 invariants)
│       │   # --- hallucination (6) ---
│       ├── claims_evidence_binding.py    # HARD claims must bind evidence
│       ├── tool_trace_consistency.py     # tool-trace claims match recorded calls
│       ├── epistemic_mode_requirements.py # mode-gated evidence requirements
│       ├── refs_closed_world.py          # cited refs resolve in-world
│       ├── output_bound_to_claims.py     # output traces to extracted claims
│       ├── confidence_sanity.py          # confidence vs evidence sanity
│       │   # --- oracle (1) ---
│       ├── oracle_independence.py        # oracle independent of subject under test
│       └── _helpers.py             # shared invariant helpers
└── tests/
    ├── test_canonical_json.py      # 12 tests: determinism, hash stability
    ├── test_ledger_chain.py        # 7 tests: chain integrity, tamper detection
    ├── test_invariants_smoke.py    # 17 tests: all 6 invariants pass/fail cases + verdict semantics
    ├── test_redaction.py           # 17 tests: secret patterns, store integration, custom redactor
    ├── test_retention.py           # 13 tests: TTL computation, expiry, purge lifecycle
    └── test_smoke_run.py           # 23 tests: full lifecycle, stage enforcement, blob/event store

# Extracted repos (separate GitHub repositories):
# vscode-governor → github.com/unpingable/vscode-governor
# gov-webui       → github.com/unpingable/governor_webui
# clerk           → github.com/unpingable/clerk (Electron desktop app, depends on agent_gov)
```
