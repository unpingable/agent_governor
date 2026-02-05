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
**Failure Provenance** — Scars (constraint hysteresis), shields (input gating), surprise ratio classification.
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
**VS Code Extension (Deferred 3, V1-V4)** — Unified check aggregation, CLI `governor check` command, TypeScript VS Code extension (CLI wrapper, diagnostic provider, TreeView, hover tooltips, code actions, real-time checking).
**Telemetry Dashboard** — Rich TUI for real-time regime visualization. Phase space plot, regime gauge, energy sparkline, event log, budget panel. Live/replay/demo modes.
**Prometheus Metrics** — Optional Prometheus metrics export at /metrics. Counters, histograms, gauges. TelemetryCollector backend integration.
**Maude Lite** — Evidence-gated coding harness — kernel-only surface. HARD claims require evidence, contradictions persist, failures are loud. Custody scoring, claim extraction, evidence linking, contradiction detection, exit shape checking.
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
| Git hooks | 33 |
| Wrapper | 29 |
| MCP server | 22 |
| **Subtotal** | **381** |

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
| Failure Provenance & Scars | 89 |
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
| Continuity Enforcement | 190 |
| Convergence Auto-Tuning | 145 |
| VS Code Extension | 176 |
| Maude Lite | 101 |
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

**Total: ~7770 tests**
