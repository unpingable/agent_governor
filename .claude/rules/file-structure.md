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
├── maude_lite.py     # MaudeLite, evidence-gated coding harness, claim extraction, evidence linking, custody scoring
├── violation_resolver.py # ViolationResolver, PendingViolation, ResolutionAction, ExceptionRecord, fix/revise/proceed actions
├── interferometry.py  # Interferometry: parallel + serial multi-model claim comparison, alignment, signals, ledger promotion, store
├── code_interferometry.py # Code interferometry: risk markers (19 types), anchor conflicts, tier determination, CheckFinding bridge
├── session_continuity.py # Session continuity: capsule-based session management, fork/promote, checkpoints, ledger/workspace persistence
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
# Legacy (v0.1, kept for reference):
├── core.py           # Original AgentGovernor class
├── ledger.py         # Original CodebaseLedger
├── validators.py     # Original validators
└── types.py          # Original type definitions

src/webui/
├── adapter.py        # FastAPI adapter with OpenAI-compatible API, governor endpoints, backend switching
└── static/
    └── index.html    # Combined chat + governor sidebar UI

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

vscode-governor/
├── package.json              # Extension manifest, commands, settings, TreeView contributions
├── tsconfig.json             # TypeScript config
├── esbuild.mjs               # Bundler (esbuild, not webpack)
├── .vscodeignore              # Publish ignore
├── src/
│   ├── extension.ts           # Entry point: activate, commands, status bar, TreeView, on-save
│   ├── governor/
│   │   ├── client.ts          # CLI wrapper: spawn governor, parse JSON, fetchState
│   │   └── types.ts           # TypeScript interfaces for CheckResult/CheckFinding/GovernorState
│   ├── views/
│   │   └── governorTree.ts    # GovernorTreeProvider: TreeDataProvider for state panel
│   └── diagnostics/
│       └── provider.ts        # DiagnosticCollection management
└── src/test/
    └── suite/
        ├── client.test.ts     # Client unit tests (mock child_process)
        ├── provider.test.ts   # Provider unit tests (mock vscode API)
        └── governorTree.test.ts # TreeDataProvider tests (mock fetchState)
```
