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
│
# Autonomous Execution (Phase A1-A4):
├── spine.py          # Spine, SpineManager, locked project structure, proposal verification
├── invariants.py     # InvariantType, Invariant, InvariantSet, InvariantLibrary, mechanically verifiable rules
├── execution.py      # ExecutionBudget, ExecutionUsage, ExecutionState, SessionManager, checkpoint/resume
├── executor.py       # AutonomousExecutor, StepResult, ExecutorConfig, ExecutionEvent, step-function loop
├── adapters.py       # Governor adapter invariants, thin wrappers (security, CFI, fiction, nonfiction, custom)
├── invariant_store.py # InvariantSpec, InvariantStore, VALID_KINDS, persistent invariant management
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
# Intent Compiler:
├── intent_compiler.py     # IntentFormPolicy, IntentFormSchema, compile_intent, BUILTIN_TEMPLATES, receipt emission
│
# Receipt Kernel Bridge (parallel audit trail):
├── receipt_bridge.py      # ReceiptKernelBridge: emit hash-chained events to receipt_kernel SQLite store
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
│   └── invariants/
│       ├── __init__.py             # All 6 invariant exports
│       ├── ledger_chain_valid.py   # Hash chain integrity (seq contiguity, prev_hash, event_hash)
│       ├── receipt_completeness.py # Required evidence keys present + blobs retrievable
│       ├── evaluation_completeness.py  # Attested evaluation, no silent downgrade
│       ├── finalization_completeness.py # Clean endings, decision ref, last event
│       └── run_shape.py            # single_finalize + stage_required_path
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
```
