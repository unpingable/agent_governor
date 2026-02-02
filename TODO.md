# Future Enhancements

## Epistemic Governor Integration (from ingest/epistemic_governor)

These features port key concepts from the non-agentic epistemic governor into the agent governor.
Toggle-able via config. See `ingest/epistemic_governor/` for reference implementations.

### Phase E1: Provenance & Confidence (Foundation) ✓ COMPLETE

- [x] **Provenance hierarchy** - Track HOW claims were established, not just WHAT
  - Added `Provenance` enum: `OBSERVED`, `RETRIEVED`, `USER_PROVIDED`, `DERIVED`, `PEER_ASSERTED`, `ASSUMED`
  - `PEER_ASSERTED` is the primary defense against multi-agent epistemic amplification — claims from other agents start at low confidence
  - Provenance NEVER upgrades without evidence (hard invariant)
  - Created `GroundedClaim` wrapper with full epistemic metadata
  - Module: `src/governor/epistemic.py`

- [x] **Confidence modeling** - Bounded [0,1] confidence on claims
  - **Evidence-gated confidence** (the "Money Rule"): Confidence MUST NOT increase without evidence
  - NOT increased by: repetition, elaboration, peer agreement, self-consistency
  - For `ASSUMED`/`PEER_ASSERTED`: confidence cannot increase without evidence, only decay
  - `update_confidence(claim_id, delta, requires_evidence=True)` method
  - Peer claims capped at MAX_PEER_CONFIDENCE (0.30)

- [x] **Dangerous claims detection** - Auto-flag high-confidence ungrounded claims
  - `is_dangerous = is_high_confidence and not is_grounded`
  - High confidence threshold: 0.7 (configurable via HIGH_CONFIDENCE_THRESHOLD)
  - CLI: `governor epistemic dangerous` lists flagged claims
  - CLI: `governor epistemic dangerous --block` blocks all dangerous claims

- [x] **Evidence references** - Structured pointers to supporting evidence
  - `EvidenceRef` dataclass: `ref_id`, `ref_type`, `locator`, `scope`, `confidence`
  - Types: `TOOL_TRACE`, `URL`, `DOCUMENT`, `HUMAN_INPUT`, `RECEIPT`
  - `ledger.attach_evidence(claim_id, ref)` method
  - Grounded = has evidence OR grounded provenance
  - CLI: `governor epistemic evidence <id> --type X -l Y -s Z`

**48 tests in tests/test_epistemic.py**

### Phase E2: Regime Detection (Health Monitoring) ✓ COMPLETE

- [x] **Operational regimes** - Classify system health from observable signals
  - Added `OperationalRegime` enum: `ELASTIC`, `WARM`, `DUCTILE`, `UNSTABLE`
  - ELASTIC: Stable, identifiable, normal operation
  - WARM: Drifting but recoverable, tighten constraints
  - DUCTILE: Path dependent, probing is intervention, reset required
  - UNSTABLE: Positive feedback, cascade detected, emergency stop
  - `severity` property for ordering, `recommended_actions` for guidance
  - Module: `src/governor/regime.py`

- [x] **Regime signals** - Observable metrics for classification
  - `RegimeSignals` dataclass with all metrics:
  - `hysteresis`: Sticky behavior, path dependence (high = bad)
  - `relaxation_time`: How long to return to baseline (long = ductile)
  - `tool_gain`: Perturbation amplification (k >= 1 = unstable)
  - `anisotropy`: Variance under paraphrase (high = sensitive)
  - `provenance_deficit`: Claims without evidence anchors
  - `budget_pressure`: How often caps trigger
  - `contradiction_open_rate` / `contradiction_close_rate`: Accumulation indicator
  - `rejection_rate`, `dangerous_claim_rate`: Additional health metrics

- [x] **Regime thresholds** - Configurable boundaries between regimes
  - `RegimeThresholds` dataclass with all configurable boundaries
  - ELASTIC → WARM: hysteresis > 0.2, relaxation > 3.0, rejection > 0.3, etc.
  - WARM → DUCTILE: hysteresis > 0.5, anisotropy > 0.5, multiple indicators
  - Any → UNSTABLE: tool_gain >= 1.0, budget_pressure > 0.9, dangerous > 0.3
  - Serializable via `to_dict()` / `from_dict()`

- [x] **Regime detector** - Classifier over dynamics
  - `RegimeDetector` class with `classify(signals)` and `update(signals)` methods
  - Returns `(regime, warnings)` tuple with specific threshold violations
  - Tracks transition history with timestamps for audit
  - `get_state()` returns full current state, `get_history()` returns transitions
  - Serializable for persistence

- [x] **Regime metrics collection** - Empirical data for threshold tuning
  - `RegimeMetrics` class with signal history and transition tracking
  - `SignalCollector` for computing signals from proposal outcomes
  - Baseline tracking with perturbation analysis
  - Turn counter for temporal analysis
  - `threshold_analysis()` method for percentile-based threshold suggestions

- [x] **Regime CLI commands** - Commands for regime management
  - `governor regime status` - Show current regime and signals
  - `governor regime history` - Show transition history
  - `governor regime signals` - Show detailed signal values
  - `governor regime update` - Update signals and check for transitions
  - `governor regime thresholds` - Show detection thresholds
  - `governor regime reset` - Reset to default ELASTIC state

**42 tests in tests/test_regime.py**

### Phase E3: Boil Control (Named Presets with Dwell Time) ✓ COMPLETE

- [x] **Control modes / presets** - Named operating configurations with graduated constraint profiles
  - `ControlMode` enum: `GREEN_TEA`, `WHITE_TEA`, `OOLONG`, `BLACK_TEA`, `FRENCH_PRESS`, `BOIL`
  - GREEN_TEA: Tight bounds, low claim budget, strict authority, all tripwires
  - OOLONG: Balanced (default)
  - FRENCH_PRESS: Aggressive but bounded, higher tolerance
  - BOIL: Tripwires only, pure sentinel mode
  - Module: `src/governor/boil.py`

- [x] **Preset parameters** - What each preset configures
  - `claim_budget_per_turn`: Max claims before pushback (3-100)
  - `novelty_tolerance`: Speculation band [0-1]
  - `authority_posture`: "strict" / "normal" / "permissive"
  - `variety_multiplier`: Scale variety bounds
  - `horizon_turns`: Planning horizon

- [x] **Dwell time enforcement** - Prevent mode thrashing
  - `cycle_period_turns`: Re-evaluate every N turns
  - `hold_time_turns`: Stability required before mode change
  - `min_dwell_turns`: Minimum time in regime before transition allowed
  - Transitions blocked until dwell satisfied (logged as `dwell_blocked`)

- [x] **Tripwires** - Hard-stop sentinels that bypass dwell
  - `contradiction_trip`: Instant intervention on contradiction accumulation
  - `provenance_trip`: Instant intervention on missing provenance
  - `dangerous_claim_trip`: Instant intervention on dangerous claims
  - `cascade_trip`: Instant intervention on tool cascade (k >= 1)
  - Tripwires force UNSTABLE regime immediately

- [x] **Boil controller CLI** - Commands for preset management
  - `governor boil status` - Show current preset, regime, dwell state
  - `governor boil set <mode>` - Change to preset (GREEN_TEA, OOLONG, etc.)
  - `governor boil presets` - List all presets with their parameters
  - `governor boil events` - Show recent boil control events
  - `governor boil process` - Process a turn with given signals
  - `governor boil reset` - Reset to default state

**40 tests in tests/test_boil.py**

### Phase E4: Jurisdictions (Context-Aware Governance) ✓ COMPLETE

- [x] **Jurisdiction base class** - Different rules for different contexts
  - `Jurisdiction` dataclass with:
    - `admissible_evidence`: Set of `EvidenceType` that counts
    - `budget`: `BudgetProfile` (claim costs, refill rates, discounts)
    - `spillover`: `SpilloverPolicy` (BLOCKED, PROMOTED_WITH_EVIDENCE, FLAGGED_EXPORT, FREE)
    - `contradiction_policy`: STRICT, TOLERANT, EXPECTED, SCOPED
    - `closure_allowed`, `closure_requires_evidence`
    - `export_to_factual_allowed`, `export_requires_promotion`
  - Module: `src/governor/jurisdictions.py`

- [x] **Standard jurisdictions** - Pre-defined contexts (8 total)
  - FACTUAL: Strict evidence, contradictions block, free spillover
  - SPECULATIVE: Provisional claims, no closure, requires evidence to export
  - COUNTERFACTUAL: Hypothetical reasoning, scoped contradictions, no export
  - ADVERSARIAL: Devil's advocate, contradictions expected, resolution blocked by cost
  - NARRATIVE: Fiction mode, story-internal consistency, plot holes matter
  - FORENSIC: Investigation mode, cross-source corroboration, flagged export
  - PEDAGOGICAL: Teaching mode, known simplifications, flagged export
  - AUDIT: Maximum transparency, full trail, free spillover

- [x] **Jurisdiction registry** - Register and switch contexts
  - `register_jurisdiction()`, `get_jurisdiction()`, `list_jurisdictions()`
  - `get_all_jurisdictions()`, `clear_jurisdictions()`, `reset_to_defaults()`
  - Current jurisdiction stored in `JurisdictionManager`

- [x] **Evidence admissibility** - Extended EvidenceType enum
  - Added: SENSOR_DATA, CRYPTOGRAPHIC_PROOF, SUBJECTIVE_REPORT
  - Added: NARRATIVE_CONSISTENCY, PEDAGOGICAL_FRAME, CROSS_SOURCE
  - `jurisdiction.admits(evidence_type)` check

- [x] **JurisdictionManager** - State tracking and budget management
  - Budget consumption and refill per turn
  - Claim/contradiction/export cost enforcement
  - Transition history tracking
  - Serialization/deserialization

- [x] **Jurisdiction CLI** - Commands for context management
  - `governor jurisdiction status` - Show current state
  - `governor jurisdiction list` - List all jurisdictions
  - `governor jurisdiction set <name>` - Switch jurisdiction
  - `governor jurisdiction info <name>` - Detailed jurisdiction info
  - `governor jurisdiction tick` - Advance turn, refill budget
  - `governor jurisdiction claim` - Make a claim (consumes budget)
  - `governor jurisdiction export` - Export to factual
  - `governor jurisdiction reset` - Reset to default

**62 tests in tests/test_jurisdictions.py**

### Phase E5: Direction Tracking (Landmarks & Orientation) ✓ COMPLETE

Based on `ingest/direction.md` - artificial landmarks that impose orientation constraints.

- [x] **Commitments** - Promises that must be fulfilled
  - Types: PROMISE, PREDICTION, THESIS, FORESHADOWING, DEADLINE, CHEKHOV, SETUP
  - Deadline tracking (chapter/section/time/event)
  - Fulfillment with Δt computation
  - Abandonment with reason tracking
  - Module: `src/governor/direction.py`

- [x] **Anchors** - Immutable facts that constrain the space
  - Types: WORLD_RULE, CANON_FACT, CITATION, AXIOM, ORACLE, DEFINITION, CONSTRAINT
  - Violation detection with customizable checkers
  - Confidence and scope tracking

- [x] **Trajectory** - Narrative/argumentative direction
  - Current position, destination, waypoints
  - Drift computation
  - Position history tracking

- [x] **Belief Graph** - Logical relationships with triangulation
  - Relation types: IMPLIES, CONTRADICTS, REQUIRES, ENABLES, BLOCKS, SUPPORTS, UNDERMINES, PRECEDES, FOLLOWS
  - Path finding between nodes
  - Cycle detection
  - Impossible triangle detection (A→B, B→C, A contradicts C)
  - Transitive implication tracking

- [x] **Δt Tracking** - Prediction/reality mismatch measurement
  - Per-commitment predictions
  - Verification against actual outcomes
  - Aggregate Δt computation (coherence metric)
  - History tracking for analysis

- [x] **DirectionLedger** - Unified interface for direction tracking
  - Commitment management (add, fulfill, abandon, check deadlines)
  - Anchor management (add, check violations)
  - Trajectory management (set, update position, complete waypoints)
  - Consistency checking (triangles, contradictions)
  - Coherence scoring [0, 1]
  - Persistence to disk

- [x] **Convenience functions** - Domain-specific helpers
  - `create_fiction_anchors()` - World rules from list
  - `create_nonfiction_anchors()` - Citations with sources
  - `create_thesis_commitment()` - Academic thesis
  - `create_chekhov_commitment()` - Chekhov's gun with deadline

**57 tests in tests/test_direction.py**

### Phase E6: Ultrastability (Adaptive Control) ✓ COMPLETE

- [x] **S₀/S₁/S₂ hierarchy** - Constitutional bounds on adaptation
  - S₀ (Constitution): Immutable - NLAI, FSM topology, forbidden transitions
  - S₁ (Regulatory): Budgets, thresholds, timeouts (adaptable within bounds)
  - S₂ (Epistemic): Claims, contradictions, ledger (fully mutable)
  - Rule: S₂ may influence S₁, S₁ may NOT influence S₀
  - Module: `src/governor/ultrastability.py`

- [x] **Regulatory parameters** - S₁ values that can adapt
  - Each parameter has: `current`, `floor`, `ceiling`, `step`
  - `repair_budget`: [10, 500], step 10
  - `refill_rate`: [1, 20], step 1
  - `glass_threshold`: [5, 50], step 2
  - `resolution_cost`: [1, 50], step 2
  - `claim_timeout_ms`: [1000, 30000], step 500
  - `evidence_threshold`: [1, 10], step 1
  - `independence_threshold`: [0.1, 1.0], step 0.05

- [x] **Adaptation triggers** - When to consider changing S₁
  - `block_rate_threshold`: >30% turns blocked = too tight
  - `c_open_threshold`: >15 open contradictions = accumulating
  - `open_close_ratio_threshold`: open_rate > close_rate * 1.2
  - `violation_rate_threshold`, `dangerous_rate_threshold`
  - Trend analysis over recent epochs (linear regression slope)

- [x] **Adaptation verdicts** - Outcome of adaptation consideration
  - `HOLD`: No change needed
  - `ADAPT`: Change within bounds
  - `FREEZE`: Stop adapting, something's wrong
  - `ALERT`: Human intervention needed

- [x] **Pathology detection** - Detect when adaptation is making things worse
  - OSCILLATION: Parameters bouncing (3+ reversals in 6 adaptations)
  - RUNAWAY: Hitting bounds repeatedly (5 consecutive same-direction)
  - INEFFECTIVE: Adapting but metrics not improving (5 epochs)
  - WRONG_ATTRACTOR: Stuck in bad regime (3 epochs in DUCTILE/UNSTABLE)
  - On pathology: freeze adaptation, require human unfreeze

- [x] **Ultrastability controller** - Main adaptation loop
  - `UltrastabilityController` class
  - `observe_epoch(observation)` - Record epoch observations
  - `consider_adaptation()` - Deliberate and return decision
  - `apply_adaptation(decision)` - Apply if ADAPT verdict
  - `unfreeze(reason)` - Manual recovery after pathology
  - CLI: `governor adapt status/params/history/consider/unfreeze/metrics`

**113 tests in tests/test_ultrastability.py**

### Phase E7: Homeostat (Exploration Budgets) ✓ COMPLETE

- [x] **Epistemic vitals** - Observable system state
  - `EpistemicVitals` dataclass with validated [0,1] rates
  - `revision_rate`, `contradiction_rate`, `hedge_rate`, `refusal_rate`
  - `support_deficit_rate`, `retrieval_coverage`, `thermal_instability`
  - Derived `urgency` computed by setpoints
  - Module: `src/governor/homeostat.py`

- [x] **Epistemic setpoints** - Target operating ranges
  - `EpistemicSetpoints` with per-dimension weights
  - `compute_error(vitals)` → per-dimension absolute deviation
  - `compute_urgency(vitals)` → weighted aggregate [0,1]
  - `for_domain(domain)` → medical/legal (strict), creative (permissive), general (default)

- [x] **Exploration contexts** - Deliberate constraint loosening
  - `ExplorationContext` enum: STANDARD, RESEARCH, BRAINSTORM, HYPOTHESIS, SYNTHESIS, DEVILS_ADVOCATE, CALIBRATION
  - 7 pre-defined `ExplorationProfile` configurations
  - Per-context: confidence boost, hedge reduction, revision discount, tentativeness, urgency dampening

- [x] **Exploration budget** - Prevents indefinite drift
  - `ExplorationBudget`: remaining [0,1], consume/regenerate per turn
  - `can_explore()` check (must be >= `min_to_explore=0.2`)
  - Auto-exit exploration when budget depleted
  - Regenerates in STANDARD at `regen_rate=0.05/turn`

- [x] **Exploration profiles** - Per-context constraint modification
  - `confidence_ceiling_boost`, `hedge_requirement_reduction`
  - `revision_cost_discount`, `support_requirement_reduction`
  - `commitment_tentativeness` [0,1], `urgency_dampening` [0,1]
  - `budget_cost` per turn in that context

- [x] **Homeostat controller** - Adaptive gain scheduler
  - `Homeostat` class with modes: OBSERVE_ONLY, SUGGEST, ACTIVE
  - `observe(vitals)` → update EMA urgency, manage budget, compute tuning
  - `compute_tuning(vitals)` → `TuningDelta` with clamped outputs
  - `TuningGains` (urgency→parameter mapping), `TuningClamps` (output limits)
  - `enter_exploration(context)` / `exit_exploration()` with budget enforcement
  - `urgency_trend()` via linear regression, `get_diagnostics()`, serialisation

- [x] **Homeostat CLI** - Commands for exploration management
  - `governor explore status` — mode, context, budget, urgency
  - `governor explore enter <context>` — enter exploration context
  - `governor explore exit` — return to standard
  - `governor explore budget` — budget bar chart
  - `governor explore profiles` — list all profiles
  - `governor explore observe` — observe vitals and compute tuning
  - `governor vitals` — show vitals table with setpoint deviations

**114 tests in tests/test_homeostat.py**

### Phase E8: Automated Tuning ✓ COMPLETE

- [x] **Threshold auto-tuning** - Learn optimal regime thresholds
  - Collect signal distributions by actual regime (ground truth from outcomes)
  - Use percentile analysis to find natural boundaries
  - Suggest threshold updates based on false positive/negative rates
  - `ThresholdTuner` class with record/analyze/suggest/apply workflow
  - CLI: `governor tune thresholds --analyze`, `governor tune thresholds --apply`
  - Module: `src/governor/auto_tuning.py`

- [x] **Reset effectiveness tracking** - Did the reset actually help?
  - Track regime at reset, then 1/3/5 turns later
  - `restored_elastic`: Did it get back to ELASTIC?
  - `turns_to_restore`: How long did recovery take?
  - Aggregate by reset type (CONTEXT, MODE, CHAIN, MANUAL, EMERGENCY)
  - `ResetTracker` class with record_reset/advance_turn/report workflow
  - CLI: `governor tune resets --report`, `governor tune resets --pending`

- [x] **Setpoint calibration** - Learn healthy operating ranges
  - Baseline characterization: Observe natural rates, compute mean/stddev
  - Hallucination detection: Track revision/retraction correlation (Pearson r)
  - Domain-specific profiles from observation with safety margin
  - `SetpointCalibrator` with begin_baseline/record/end_baseline/calibrate workflow
  - CLI: `governor tune calibrate --begin-baseline/--end-baseline/--run`

- [x] **Budget sweep experiments** - Find optimal budget levels
  - Vary budgets systematically, record outcomes
  - Measure outcome quality vs constraint tightness
  - Compute Pareto frontier via non-dominated sort
  - `BudgetSweeper` with record_point/analyze workflow
  - CLI: `governor tune budget --parameter <name>`

**117 tests in tests/test_auto_tuning.py**

### Phase E9: Claim Extraction & Detection

- [x] **Claim signal extraction** - Auto-detect claim-worthy content ✓ COMPLETE
  - Date patterns: `\b(18\d{2}|19\d{2}|20\d{2})\b`
  - Entity patterns: `[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+`
  - Quantity patterns: `\d+(?:\.\d+)?\s*(million|billion|percent|%)`
  - Assertiveness patterns: `definitely|certainly|clearly|was acquired|founded in`
  - Return `has_speculative_content`, `assertiveness_score`
  - Module: `src/governor/claim_signals.py` (75 tests)
  - Reference: `ingest/epistemic_governor/src/epistemic_governor/claims.py:735-766`

- [x] **Auto-claim generation** - Create ASSUMED claims from signals ✓ COMPLETE
  - When text contains dates/entities/quantities, auto-create low-confidence claims
  - Flag for verification before confidence increase
  - `register_signals()` function for ledger integration
  - CLI: `governor signals extract/scan/register/score`
  - Reference: `ingest/epistemic_governor/src/epistemic_governor/claims.py:769-805`

- [x] **Claim diff** - Track claim changes between turns ✓ COMPLETE
  - Which claims were added, removed, modified?
  - Detect confidence drift (gradual increase without evidence)
  - Detect provenance laundering (ASSUMED → RETRIEVED without evidence)
  - Detect evidence erosion (evidence removed without replacement)
  - Detect silent retraction (active claim dropped without explicit retraction)
  - Module: `src/governor/claim_diff.py`
  - **91 tests in tests/test_claim_diff.py**

---

## Fiction Governor ✓ COMPLETE

- [x] **Prompt generator** - `fiction-gov prompt scene --chapter 4 --characters elena,marcus` outputs ready-to-paste prompt with bible + recent canon context
  - Also: `fiction-gov prompt character <name> --chapter N` for character-focused context
  - Includes: recent events, active threads, character bible, relationships, tone settings
- [x] **Manuscript scanner** - Parse existing chapters to auto-populate canon events
  - `ManuscriptScanner` class for regex-based extraction
  - Extracts: characters (dialogue, possessive), locations, events, plot threads
  - Thread types: MYSTERY, FORESHADOWING, CHEKHOV_GUN, PROMISE
  - Confidence scoring for extracted threads
  - `scan_manuscript_to_canon()` for Canon integration
  - `scan_single_chapter()` convenience function
  - Module: `src/fiction_governor/manuscript.py`
- [x] **Embedding similarity** - Use embeddings for smarter anti-pattern matching
  - `EmbeddingProvider` abstract interface for pluggable backends
  - `TFIDFProvider` fallback (no external dependencies)
  - `SimilarityAnalyzer` for trope, voice, and tone checking
  - `check_tropes()` - Match content against banned trope patterns
  - `check_anti_patterns()` - Match content against character anti-patterns
  - `analyze_voice()` - Voice consistency scoring with reference samples
  - `analyze_tone()` - Tone/genre matching with avoid pattern detection
  - Convenience functions: `quick_trope_check()`, `quick_voice_check()`, `compute_text_similarity()`
  - Module: `src/fiction_governor/similarity.py`
- [x] **Plot threads** - Track Chekhov's guns, foreshadowing, unresolved threads
  - Types: CHEKHOV_GUN, FORESHADOWING, MYSTERY, CHARACTER_ARC, SUBPLOT, PROMISE, SETUP
  - Statuses: PLANTED, DEVELOPING, RESOLVED, ABANDONED, OVERDUE
  - CLI: `fiction-gov thread add/list/show/develop/resolve/abandon/audit`
  - Chekhov audit detects overdue and approaching-deadline threads
- [x] **Scene proposals** - `fiction-gov proposal` workflow with approve/reject/revise
  - `fiction-gov proposal create` - Create a scene proposal with summary, characters, threads
  - `fiction-gov proposal verify` - Verify against bible and canon
  - `fiction-gov proposal approve` - Approve and auto-update threads/canon
  - `fiction-gov proposal reject` - Reject with reason
  - `fiction-gov proposal list --pending` - Show pending proposals

**376 total fiction tests (36 manuscript + 41 similarity + 112 existing + 64 context drift + 123 guardrails)**

### Context Drift Detection ✓ COMPLETE

- [x] **Narrative mode tracking** - Hysteresis-based mode transitions with genre escalation gating
  - 10 narrative modes: LITERARY, CONTEMPORARY, FANFIC, ROMANCE, EROTIC, GRIMDARK, YA, COMEDIC, TECHNICAL, HISTORICAL
  - Risk tier mapping (LOW/MEDIUM/HIGH) with explicit user opt-in for escalation
  - Hysteresis: θ_up/θ_down thresholds prevent mode-chatter
  - DriftFaultType: UNSIGNALED_REGISTER_SHIFT, GENRE_ESCALATION, MODE_CHATTER
  - Key insight: unsignaled transition is the violation, not the content
  - Module: `src/fiction_governor/context_drift.py`

**64 tests in tests/test_context_drift.py**

### Fiction Guardrails (Consent, DSI, AII) ✓ COMPLETE

- [x] **Consent tracking** - Pairwise consent state between characters
  - Scopes: FLIRT, TOUCH, SEX, KINK_COERCIVE_PLAY
  - Levels: UNKNOWN → NO → YES → YES_EXPLICIT
  - ConsentLedger with escalation checking and global opt-in state

- [x] **Hard constraints (C1-C3)** - Veto/block checks
  - C1: Consent gate — coercive dynamics without opt-in
  - C2: Mode escalation — high risk content without user enablement
  - C3: Anachronistic causal identity — "because he's Italian" in medieval setting

- [x] **Soft penalties (P1-P4)** - Steer/penalize checks
  - P1: DSI (demographic salience intrusion) — identity-correlated topics without narrative causality
  - P2: Unearned facts — sensitive topics (addiction, mental health) without character KB support
  - P3: Register drift — drift score from ContextDriftDetector
  - P4: Proxy dominance — population-level rationale in fiction

- [x] **DSI detector** - Demographic marker + correlated bundle co-occurrence detection
  - 7 demographic categories with marker patterns and correlated bundles
  - Local trigger checking against character facts

- [x] **AII detector** - Temporal validity gates for identity terms used causally
  - 4 builtin profiles: medieval_europe, renaissance_europe, ancient_world, colonial_era
  - Custom profiles with priority over builtins
  - Causal identity pattern extraction (regex-based)

- [x] **CLI** - `fiction-gov drift` and `fiction-gov guardrails` command groups
  - Module: `src/fiction_governor/guardrails.py`

**123 tests in tests/test_guardrails.py**

## Main Governor (Existing) ✓ COMPLETE

- [x] **Claude Code hooks** - Actual hook scripts that integrate with `claude` CLI
  - `HookConfig` dataclass for configuring hooks
  - `install_claude_hooks()` / `uninstall_claude_hooks()` for setup
  - Pre-tool, post-tool, and notification hook scripts
  - Blocked commands file for dangerous command prevention
  - Approved files tracking for write permission management
  - CLI: `governor claude-hooks install/uninstall/status/approve/block`
  - Module: `src/governor/claude_hooks.py`
  - **26 tests in tests/test_claude_hooks.py**

- [x] **Watch mode** - Continuously monitor directory, verify on change
  - `FileWatcher` class for polling-based file monitoring
  - `WatchSession` for tracking changes over time
  - Automatic security scanning on file changes
  - Configurable watch/ignore patterns
  - Change callbacks for integration
  - CLI: `governor watch start/check`
  - Module: `src/governor/watch.py`
  - **18 tests in tests/test_watch.py**

- [x] **Security verifier** - Check for common vulnerabilities
  - Secret detection (API keys, AWS keys, passwords, tokens)
  - SQL injection patterns
  - Command injection patterns
  - XSS vulnerabilities
  - Path traversal vulnerabilities
  - Insecure random/hash detection
  - Debug code detection
  - Diff scanning for pre-commit hooks
  - `nosec` comment support for exceptions
  - CLI: `governor security scan/diff`
  - Module: `src/governor/security.py`
  - **32 tests in tests/test_security.py**

## Cross-cutting

- [ ] **Web UI** - Simple dashboard showing claim history, rejection rates, regime status
- [ ] **VS Code Integration** - add governor support as method to VS Code
- [x] **Config profiles** - `governor profile use strict` vs `governor profile use permissive` ✓ COMPLETE
  - 6 builtins: strict, permissive, research, production, audit, research_mode
  - Custom profile creation/deletion, activation/deactivation
  - Applies envelope, boil, jurisdiction, and strict mode in one command
  - Module: `src/governor/profiles.py` (46 tests)
- [ ] **Telemetry dashboard** - Real-time regime visualization (reference: `ingest/epistemic_governor/src/epistemic_governor/observability/trace_tui.py`)

## Multi-Agent Routing & Task Sizing ✓ COMPLETE

- [x] **Task complexity estimation** - Estimate task complexity before dispatch
  - Token count / file count heuristics
  - Claim type complexity (FILE_EXISTS = simple, CHANGESET = complex)
  - Scope breadth (single file vs multi-file)
  - Historical data: how long did similar tasks take?
  - `ComplexityEstimator` class with weighted factors
  - Module: `src/governor/routing.py`

- [x] **Model routing by complexity** - Route simple tasks to local/cheap models
  - Configure available model tiers: `local` (qwen, ollama), `fast` (haiku), `standard` (sonnet), `heavy` (opus)
  - Task-to-tier mapping rules:
    - Simple verification (file exists, symbol lookup) → local
    - Single-file edits with clear spec → fast
    - Multi-file refactors, architectural decisions → standard/heavy
  - Cost/latency awareness: prefer local when latency acceptable
  - Fallback: if local fails/times out, escalate to higher tier
  - `Router` class with configurable thresholds

- [x] **Agent capability registry** - Track what each agent can do
  - Model capabilities (context window, tool use, code quality)
  - Availability (is local model running?)
  - Current load (how many tasks in flight?)
  - Historical success rate by task type
  - `ModelRegistry` and `ModelCapabilities` classes
  - Default models registered (haiku, sonnet, opus, local models)

- [x] **Adaptive routing** - Learn optimal routing from outcomes
  - Track task success by model tier
  - Adjust routing thresholds based on failure rates
  - `TaskHistory` for outcome tracking
  - Historical factor affects complexity estimation
  - CLI: `governor routing status/models/estimate/route/register/available`

**48 tests in tests/test_routing.py**

```toml
# Example config
[routing]
enabled = true
default_tier = "standard"

[routing.tiers.local]
models = ["qwen2.5-coder:7b", "ollama/codellama"]
max_complexity = 0.3
max_files = 1
preferred_claims = ["FILE_EXISTS", "SYMBOL_DEFINED"]

[routing.tiers.fast]
models = ["claude-3-haiku"]
max_complexity = 0.6
max_files = 3

[routing.tiers.standard]
models = ["claude-sonnet-4"]
max_complexity = 0.9

[routing.tiers.heavy]
models = ["claude-opus-4"]
# No complexity limit - handles everything
```

---

## ~~Strict Programmer Mode~~ ✓ COMPLETE (from ingest/coder.md)

Global execution mode that changes default constraints for SRE/sysadmin/production code contexts.
Connects to existing envelope/boil system as a new named profile.

- [x] **Claim handling modes** - Typed claim behavior under strict mode
  - `ClaimCategory` enum: STATIC_FACT, VOLATILE_FACT, CODE, PROCEDURE, JUDGMENT, PLAN
  - `ClaimRequirement` per-category: evidence counts, independence, source/version/TTL
  - `DEFAULT_REQUIREMENTS` dict: all 6 categories with production-grade requirements
  - JUDGMENT/PLAN always SOFT — never HARD

- [x] **Fail-closed defaults** - Unknown > wrong
  - `CommitLevel` enum: HARD / SOFT / REFUSED
  - `StrictModeGate.evaluate()` checks all requirements, determines max commit level
  - REFUSED when < soft_threshold (default 0.5) of requirements met
  - HARD only when ALL requirements met (hard_threshold=1.0)

- [x] **Ledger tuning for strict mode** - Tighter thresholds
  - `StrictPolicy.get_risk_adjusted()`: +k evidence, +independence for MED/HIGH risk
  - HIGH risk forces falsifier_required=True
  - `create_strict_setpoints()`: revision_target=0.02, contradiction_target=0.01
  - `create_strict_s1_overrides()`: evidence_threshold=0.85, independence=0.7

- [x] **Output gating** - Structured output enforcement
  - `StrictModeGate` with full evaluation, format_refusal, stats, diagnostics
  - `create_strict_boil_preset()`: claim_budget=5, novelty_tolerance=0.1
  - `DependencyContext`: OS, distro, language, version, runtime, permissions
  - CLI: `governor strict status|evaluate|requirements|history|reset`

Module: `src/governor/strict.py` (99 tests)

## ~~Drift Detection~~ ✓ COMPLETE (from ingest/risk-molt.md)

Temporal asymmetry defense — detects and mitigates drift induction where persistent/stateful
actors steer stateless/amnesiac agents. Based on the insight: *"Any environment with stateless
agents + social coupling is vulnerable to asymmetric temporal actors."*

- [x] **Named failure modes** - Classified temporal asymmetry attacks
  - `DriftFailureMode`: ASYMMETRIC_PERSISTENCE, CLOCK_SKEW_DOMINANCE, PREMISE_RECURRENCE, ATTENTION_SKEW
  - `DriftAlert` levels: NONE → WATCH → WARN → QUARANTINE
  - Severity ordering for escalation decisions

- [x] **Premise tracking & quarantine** - Core defense against premise recurrence
  - `PremiseRecord`: content hash, occurrence count, evidence tracking, source agents, quarantine state
  - `PremiseQuarantine`: downweights claims repeated N times without new evidence
  - `QuarantineConfig`: configurable thresholds, auto-release, single-source stricter limits
  - Evidence attachment releases quarantine, resolution closes premise
  - Auto-release after silence (configurable turns)

- [x] **Drift signals** - Observable quantities, not inferred intent
  - `DriftSignals`: premise_recurrence_rate, attention_skew, temporal_coherence_gradient
  - Contradiction age tracking (max and average)
  - Single-source dominance rate
  - `DriftThresholds`: configurable escalation boundaries (WATCH/WARN/QUARANTINE)

- [x] **Agent activity tracking** - Fingerprint, not accusation
  - `AgentActivity`: contested ratio, topic diversity, temporal coherence
  - Output hash window for variance estimation (repetitive = suspicious)
  - Suspicious agent detection with minimum sample requirement

- [x] **DriftDetector** - Stateful detector with full lifecycle
  - Record assertions, evidence, resolutions, contradictions
  - `compute_signals()` → `classify()` → `update()` pipeline
  - Alert history and detected failure mode tracking
  - Full serialization (to_dict/from_dict) for persistence
  - CLI: `governor drift status|update|record|quarantined|agents|history|tick|reset`

Module: `src/governor/drift.py` (107 tests)

## Δt Quorum Governor (from ingest/multi2.md)

Multi-agent temporal coherence system. Proposals must remain stable across Δt windows.
Extends existing multi-agent dispatcher + Δt tracking from direction.py.

- [x] **Temporal quorum protocol** - Stability over time, not majority vote
  - Proposals must remain stable across Δt windows (seconds, minutes, hours/days)
  - Different claim types get different Δt budgets
  - Low-stakes reversible claims commit fast; high-stakes irreversible require longer Δt + stronger evidence
  - Reference: `ingest/multi2.md`

- [x] **Cooperative redundancy with independence constraints** ✓ COMPLETE
  - Agents must use different tool paths, prompting styles, retrieval sources
  - Independence score: quantify how different the verification paths were
  - Corroboration from identical methods doesn't count
  - Agent Run Provenance: track tools_used, sources_consulted, prompt_hash
  - Module: `src/governor/independence.py` (38 tests)

- [x] **Δt budgets per claim type** - Policy matrix
  - `MATH`: Δt=1s (low), k=2, tooling=calculator. Reversible.
  - `CODE`: Δt=10s (low), k=1-2, tooling=linter/compiler. Mostly reversible.
  - `STATIC_FACT`: Δt=30-120s (med), k=2-3, tooling=retrieval. Usually irreversible.
  - `VOLATILE_FACT`: Δt=60-300s (med-high), k=3+, tooling=live API. Irreversible.
  - `PROCEDURE`: Δt=300s+ (high), k=3+, tooling=sandbox. Dangerous.
  - `JUDGMENT/PLAN`: Δt=600s+ (highest), k=3+, human-in-loop. Strategic.
  - Risk levels: LOW/MEDIUM/HIGH multiply the base Δt

- [x] **Contradiction persistence ledger** - Track dissent ✓ COMPLETE
  - Maintain: claim, evidence references, dissenting arguments, confidence trajectory
  - Objections are first-class: `Objection(claim_id, agent_id, reason, severity, evidence)`
  - Objections with evidence block commit; objections without evidence flag for review
  - Never silently discard dissent — dismiss requires stated reason
  - Module: `src/governor/dissent.py` (59 tests)

- [x] **Recency decay / TTL enforcement** ✓ COMPLETE
  - Committed assertions get TTL based on volatility class (PERMANENT→EPHEMERAL)
  - Stale claims auto-degrade confidence or are retracted
  - Revalidation scheduler with urgency-sorted schedule
  - Module: `src/governor/ttl.py` (45 tests)

- [x] **Quorum state machine** - Proposal lifecycle
  - PROPOSED → UNDER_REVIEW → {COMMITTED | CONTESTED | EXPIRED}
  - CONTESTED → {RESOLVED_COMMIT | RESOLVED_REJECT | ESCALATED}
  - Commit criteria: stability across Δt, minimum k agents, no unresolved HIGH objections

## ~~Sybil Resistance~~ ✓ COMPLETE (from ingest/sybil.md)

Implemented in `src/governor/sybil.py` (75 tests).

- [x] **ProvenanceVector** — Extended MethodSignature superset (frozen dataclass)
  - agent_id, tool_path_hash, sources_hash, prompt_hash, model_tier, source_urls,
    provider_id, response_time_ms, error_hash
  - `feature_set` property, `to_method_signature()` for backward compat
- [x] **BlocDetector** — Connected-components clustering via union-find
  - Extended Jaccard similarity: base + timing bonus (0.1 max) + error hash bonus (0.15 × weight)
  - `detect_blocs(vectors)` → list[Bloc] (correlated agent clusters)
  - `compute_neff(vectors)` → NeffResult (effective voter count: blocs + singletons)
- [x] **OriginBudgetTracker** — Per-origin vote rate limiting
  - Configurable votes_per_window, window_duration
  - Auto-register on first vote, window expiry resets
- [x] **SybilDetector** — Main detection orchestrator
  - `check_votes(votes, proposal_id, required_k)` → (passes, NeffResult, reasons)
  - Escalation when Neff drops below threshold
  - Audit event logging (SybilEvent)
- [x] **Quorum Gate 5** — Sybil resistance integrated into QuorumManager.can_proceed
  - 3 new Vote fields: provider_id, response_time_ms, error_hash (backward compat)
  - Gate 5 checks Neff >= k, not len(votes) >= k

## ~~Research Mode~~ ✓ COMPLETE (from ingest/research.md)

Implemented in `src/governor/research.py` (137 tests).

- [x] **HypothesisState** — PROBE → TENTATIVE → SUPPORTED → ABANDONED
  - Non-convergent epistemic control: optimizes for survivability, not convergence
- [x] **ResearchLedger** — Main class with full hypothesis lifecycle
  - create_hypothesis, spawn (from parent), mark_competitors
  - attach_evidence (impulses with independence × novelty scoring)
  - file_contradiction (severity-weighted)
  - Promotion gates: PROBE→TENTATIVE (≥1 evidence), TENTATIVE→SUPPORTED (≥K independent, monitors pass)
  - abandon, archive, tick (decay + maintenance cost + auto-archive)
- [x] **EntropyMonitor** — Shannon entropy bounds (H_min ≤ H(t) ≤ H_max)
  - Prevents dogma (too low) and sprawl (too high)
  - Corrective actions when out of bounds
- [x] **DominanceMonitor** — D_i = C_i / Σ C_j cap (D_max)
  - Prevents winner-take-all premature convergence
- [x] **TimescaleMonitor** — Δt invariant (τ_c ≥ k · τ_e)
  - Claims must harden slower than evidence arrives
- [x] **TerminalState** — Typed honest refusal with certificate
  - ILL_POSED, INSUFFICIENT_EVIDENCE, MULTIPLE_LIVE_HYPOTHESES
  - Minimal missing specification for each type
- [x] **ResearchConfig** — 10 tunable parameters (lambda, H bounds, D_max, k_timescale, etc.)
- [x] **research_mode builtin profile** — Added to profiles.py (6th builtin)

## ~~Puppet Mode~~ ✓ COMPLETE (from ingest/puppet.md)

Implemented in `src/governor/puppet.py` (128 tests).

- [x] **PuppetProfile** - Declarative persona definition ✓ COMPLETE
  - Voice constraints: vocabulary, register (formal/wry/clinical), forbidden phrases
  - Epistemic posture: how the persona handles uncertainty
  - Behavioral constraints: what the persona can/cannot do
  - Role disclaimer mode: how the persona identifies itself
  - 3 builtin profiles: ops_scribe, procurement_lawyer, daria_mirror

- [x] **Output channel split** - Separate content from rendering ✓ COMPLETE
  - AnswerSkeleton + SkeletonAtom for structured pre-puppet output
  - PuppetRenderer applies voice, register, framing
  - Commit decisions happen on the skeleton, not the rendered output
  - Puppet layer is cosmetic—cannot introduce new claims

- [x] **Semantic diff guard** - Prevent claim smuggling through rewrite ✓ COMPLETE
  - PuppetDiffGuard with 7 hard rules (R1-R7) and 2 soft warnings (W1-W2)
  - Blocks: new entities, new numbers, certainty escalation, scope escalation
  - Blocks: citation removal, polarity flips, new imperative instructions
  - Warns: compression risk, tone drift

- [x] **Puppet registry** - Manage available personas ✓ COMPLETE
  - `governor puppet list` - Show available profiles
  - `governor puppet activate <name>` - Enable puppet mode
  - `governor puppet deactivate` - Return to default voice
  - `governor puppet create <name>` - Create new profile from JSON
  - `governor puppet test <name>` - Verify profile constraints work
  - `governor puppet render <text>` - Render through active puppet

## ~~Grounding Audit Pipeline~~ ✓ COMPLETE (from ingest/regime.md)

Implemented in `src/governor/audit.py` (164 tests).

- [x] **Audit stages** - PRE_COMMIT (gate), POST_COMMIT (review), PERIODIC (TTL), INCIDENT (investigation)
- [x] **Detection signals** - 15-field feature vector (evidence count/strength, independence, coverage, novelty, precision, temporal, confidence, stability, tool use)
- [x] **Failure mode taxonomy** - 11 learnable categories (NO_EVIDENCE, WEAK_EVIDENCE, CITE_DRIFT, SOURCE_ALIASING, TEMPORAL_STALENESS, ENTAILMENT_OVERREACH, SPECIOUS_PRECISION, ENTITY_CONFLATION, COUNTEREVIDENCE_IGNORED, TOOL_MISREAD, PROMPT_INJECTION)
- [x] **Adaptive thresholds** - PolicyStore with 54-entry default matrix (6 claim types × 3 risks × 3 scopes), deterministic tuning rules, adjustment history
- [x] **Leak scoring** - Severity-weighted leak scores (status × stage × severity) for adaptive tuning
- [x] **Tainted claim similarity** - Detect near-duplicates of bad claims ✓ COMPLETE
  - Token-set Jaccard fingerprinting (Option A from taint.md)
  - Inverted index for candidate retrieval
  - Exact match + near-duplicate detection with configurable thresholds
  - Audit events on taint similarity hits
  - Module: `src/governor/taint.py` (81 tests)

## ~~Failure Provenance & Constraint Hysteresis~~ ✓ COMPLETE (from ingest/scars.md)

Implemented in `src/governor/scars.py` (89 tests).

- [x] **Scars as constraint hysteresis** - Scar dataclass with permanent topology + relaxing stiffness
- [x] **Failure provenance discriminator** - Surprise ratio (ρ) classification: INTERNAL/EXTERNAL/AMBIGUOUS
- [x] **Constraint tightening mechanics** - Exponential cost multiplier, hard/soft scar distinction
- [x] **Annealing / healing with guards** - Evidence-gated (not time-gated), asymptotic floor, τ_heal >> τ_scar
- [x] **Shields (input gating)** - Permeability control for external hostility, release after stable cycles
- [x] **DoC prevention** - Mutual exclusivity (scar OR shield, never both), ambiguous defaults to shielding
- [x] **Scar ledger** - Full CRUD, serialization, metrics, CLI (`governor scar list/shields/history/anneal/stats/record/check`)

## Semantic Variety Module (from ingest/semvar.md)

Prevents repetitive phrasing across responses without mutating factual content.
Runs after commit gating and puppet rendering, before semantic-diff guard.

- [x] **PhraseBank** - Registry of high-gravity phrases ✓ COMPLETE
  - Each phrase: meaning tag, register (formal/wry/etc.), risk level, alternatives
  - Cooldown rules per phrase (block reuse for T turns)
  - 12 seed phrases with meaning tags and register-matched alternatives
  - Reference: `ingest/semvar.md`

- [x] **SessionStyleState / CooldownTracker** - Track repetition within session ✓ COMPLETE
  - Recent n-gram tracking (configurable n, default 3)
  - Recent phrase usage with turn tracking
  - Cooldown enforcement per phrase
  - User-echo exception

- [x] **Variety rules** - Repetition prevention ✓ COMPLETE
  - Cooldown: Block phrase reuse for T turns (configurable)
  - Burst repetition: No trigram repeated twice in single response
  - Register-aware substitution: Alternatives must match current register
  - User-echo exception: If user used a phrase, echoing it is allowed
  - Semantic diff guard: blocks transforms that alter meaning

- [x] **Pipeline placement / SemVarEngine** ✓ COMPLETE
  - No-rewrite zones (code blocks, code spans, quotes, blockquotes)
  - SemanticDiffGuard: entity, number, negation, modal, causal invariants
  - Fail-closed: guard rejection uses original text
  - CLI: `governor semvar transform/phrases/config`
  - Module: `src/governor/semvar.py` (56 tests)

---

## ~~E6/E7 Coupling~~ ✓ COMPLETE (from ingest/meta-todo.md)

Implemented in `src/governor/coupling.py` (83 tests: 47 core + 36 adversarial).

The meta-todo identified the key architectural risk: Homeostat (E7) and Ultrastability (E6) can
compete if both independently mutate S₁ parameters.  The fix: **one-way protocol**.

- [x] **TuningIntent** — Wraps Homeostat's TuningDelta as a set of ParameterProposals
- [x] **ParameterMapping** — Translates TuningDelta fields → S₁ parameter deltas (5 default mappings)
- [x] **GovernorCoupling** — One-way bridge: Homeostat recommends, Ultrastability decides
  - Frozen controller → all intents rejected
  - S₁ bounds enforced via ParameterSpec.propose_change()
  - Every submission logged for audit
  - IntentVerdict: ACCEPTED / PARTIAL / REJECTED / FROZEN / NO_MAPPINGS
- [x] **Rule enforced**: Homeostat never touches S₁ directly; all mutations route through UltrastabilityController

### Anti-oscillation hardening (meta-todo #2-#6)
- [x] **Deadband** — per-mapping threshold suppresses jitter (all DEFAULT_MAPPINGS have deadbands)
- [x] **Accumulator** — carries fractional intent across submissions until step boundary crossed
- [x] **Remaining intent** — clipped deltas explicitly discarded (not carried); prevents double-integrator
- [x] **Freeze feedback** — `frozen_signal` + `consecutive_freezes` on IntentOutcome; Homeostat should switch to OBSERVE_ONLY
- [x] **claim_timeout_ms dampened** — gain reduced 5000→2000, strongest deadband (0.02)
- [x] **Adversarial sims** — deterministic plant simulator: convergence, oscillation, jitter, freeze interaction, mixed sequences, EMA smoothing

## Implementation Notes

### Toggle Configuration
All epistemic governor features should be toggle-able via `config.toml`:

```toml
[epistemic]
# Phase E1
provenance_tracking = true
confidence_modeling = true
dangerous_claim_detection = true

# Phase E2
regime_detection = true
regime_auto_response = false  # Just detect, don't auto-respond

# Phase E3
boil_control = true
default_preset = "oolong"
dwell_enforcement = true

# Phase E4
jurisdictions = false  # Heavier feature, opt-in

# Phase E5
direction_tracking = true  # Commitments, anchors, Δt
belief_graph = true  # Logical relationship tracking

# Phase E6
ultrastability = false  # Advanced, opt-in
adaptation_mode = "suggest"  # "observe" | "suggest" | "active"

# Phase E7
homeostat = false  # Advanced, opt-in
exploration_budget = true  # Lighter-weight, just the budget

# Phase E8
auto_tuning = false  # Collect data but don't apply

[drift]
enabled = false  # Temporal asymmetry defense
premise_quarantine = true
auto_release_turns = 10
single_source_strict = true

[routing]
enabled = true
default_tier = "standard"
adaptive = true  # Learn from task outcomes

[strict_programmer]
enabled = false  # Activate strict programmer mode
fail_closed = true
no_speculative_facts = true
procedures_dangerous = true

[quorum]
enabled = false  # Δt quorum governor
default_dt_seconds = 30
min_agents = 2
independence_threshold = 0.5
contradiction_persistence = true

[puppet]
enabled = false
active_profile = ""  # Name of active puppet profile
semantic_diff_guard = true
certainty_escalation_block = true

[fiction_guardrails]
context_drift = true
consent_tracking = true
dsi_detection = true
aii_detection = true
hard_constraints = true  # C1-C3
soft_penalties = true     # P1-P4

[grounding_audit]
enabled = false
pre_commit_gate = true
post_commit_review = true
periodic_revalidation = true
tainted_claim_detection = true

[scars]
enabled = false
auto_anneal = false  # Require human approval for healing
doc_alert_threshold = 10  # Alert if > N active scars
phase_lag_multiplier = 1.5  # How much failure slows response

[semvar]
enabled = false
cooldown_turns = 3
max_phrase_reuse = 1
ngram_size = 3
decay_half_life = 10
```

### Migration Path
1. E1 (Provenance/Confidence) can be added to existing `Claim` without breaking changes
2. E2 (Regime) is additive - new module, new CLI commands
3. E3 (Boil) extends existing envelope system
4. E4 (Jurisdictions) replaces/extends envelope with richer model
5. E5 (Direction) is additive - complements fiction/non-fiction governors
6. E6-E7 are advanced features, SHOULD be stable before enabling
7. E8 is tooling/automation, low risk

### Reference Files
All reference implementations are in `ingest/epistemic_governor/src/epistemic_governor/`:
- `claims.py` - Provenance, confidence, evidence refs
- `control/regime.py` - Regime detection
- `control/boil.py` - Named presets, dwell time
- `control/ultrastability.py` - S₀/S₁/S₂, adaptation, pathology
- `homeostat.py` - Vitals, setpoints, exploration
- `jurisdictions/` - Context-specific governance rules

Remaining design specifications in `ingest/`:
- `multi2.md` - Δt quorum governor (semantic enforcement layers L1-L6 COMPLETE)
- `regime.md` - Grounding audit pipeline (all assertion/cascade/roles gaps CLOSED, L1-L6 complete)
- `next.md` - Semantic entropy (conceptual, fiction guardrails portion complete)
- `next2.md` - Nonfiction CFI (not started, requires human authority decisions)
- `vscode.md` - VS Code integration (deferred, UI last)

---

## RATHOLES (DO NOT ENTER)

Seductive ideas that will wreck momentum if pursued too early.
Named here so they lose their power. See `ingest/ratholes.md` for full context.

**Meta-signal: If an idea increases conceptual elegance but decreases observability, it's probably premature.**

| # | Trap | Why Later | Right Now |
|---|------|-----------|-----------|
| 1 | Perfect Independence Modeling | Need empirical data, not theoretical vibes | Log metadata, optimize after real failures |
| 2 | Probabilistic Confidence Scoring | False precision, calibration hell | Commit levels, evidence classes, refusal thresholds (ordinal > numeric) |
| 3 | Learning / Adaptation Loops | Breaks auditability, blurs causation | Freeze behavior, YOU are the learner |
| 4 | Formal Verification / Proofs | Invariants still operational, not axiomatic | Tests > proofs, counterexamples > theorems |
| 5 | Universal Ontology / Claim Taxonomy | Ontologies calcify, real claims are messier | Ugly pragmatic enums, let taxonomy emerge from pain |
| 6 | Explainability Theater | Explanations become narratives become persuasion | Emit structure, not stories |
| 7 | Full Autonomy | Magnifies bugs, forces premature trust | Power tools, not self-driving |
| 8 | Moral Philosophy Integration | Ellul's trap door — arbitrating meaning not admissibility | Enforce process, not outcomes |
| 9 | Byzantine Fault Tolerance | No adversarial agents in current use case | Quorum + interferometry sufficient (spec frozen in `ingest/bft.md`) |
| 10 | Auto-Publish Workflows | Removes human judgment on "should this exist?" | Quality automation, not quantity automation |

**When to revisit:** Only when you have (1) real failure from NOT having it, (2) empirical data to validate the approach, (3) clear success metric. NOT when it "feels right" or "completes the theory."

---

## Design Principles (from ingest/)

### Dogfooding Policy (from `ingest/ondogfooding.md`)

**Core rule: The governor is NOT its own priest. It can be its own fuzzer.**

Bad dogfooding (core-corrupting):
- Governor writes governor rules
- Governor evaluates governor behavior
- Governor updates itself based on that loop
- → closed epistemic circuit, self-sealing, drift invisible

Good self-validation (corner-case discovery):
- Governor enumerates edge cases and failure-inducing prompts
- Runs them through the same deterministic checks
- Does NOT auto-change invariants
- Outputs a triage queue for human review
- Any changes are manual, tracked, reversible

Safety rails:
- **No auto-patching.** Only propose diffs.
- **No invariant mutation.** Only suggest.
- **All changes require a signed human decision.**
- **Record full reproduction bundle** (prompt hashes, model IDs, outputs, evidence table state).
- **Prefer generating failing tests** over generating fixes. (Tests are truth; fixes are hope.)

Where dogfooding IS appropriate: interface layers (Web UI, VS Code), workflow ergonomics,
latency/friction, whether refusal feels legible or just annoying. Those are tooling problems,
not epistemic ones.

### MCP Integration Constitution (from `ingest/mcp.md`)

Guidelines for when MCP tools are wired into the governor. Not for now — for future-you.

1. **Default is sensor-only** — actuators disabled by policy until explicitly enabled
2. **Actuators require explicit authority + scope** — commitment-mode only, idempotency key, rollback plan, HitL approval
3. **Budgets are first-class** — rate/cost/time/retry/staleness budgets per tool (anti-windup)
4. **Fail closed on uncertainty** — unknown outcome = do not assume success
5. **No tool-output laundering** — tool results become evidence objects (L1/L3), not narrative
6. **Separation of loops** — governor loop (admissibility) / tool loop (evidence) / human loop (irreversible) never all closed by system
7. **Hysteresis on escalation** — local reasoning → cached → cheap tool → expensive tool → human. No oscillation.
8. **Everything is replayable** — reproduction bundle per tool call (name/version, inputs hash, outputs hash, latency)

Practical classification:
- **Sensors** (read-only): filesystem read, URL fetch, citations lookup, calculator, corpus search
- **Actuators** (state-mutating): require commitment-mode gates + human approval

Fault model: assume MCP servers are flaky, slow, and occasionally wrong. Treat as hostile network I/O.

### Multi-Model Voter Architecture (from `ingest/otherflavors.md`)

When wiring non-Claude models as quorum voters, treat them as stateless opinion sources
with different epistemic priors. Independence > intelligence.

| Model | Role | Strength | Use As |
|-------|------|----------|--------|
| **Claude/Codex** | Operator & builder | Tool use, nuance, repo-aware edits | Primary agent |
| **DeepSeek** | Cold logic & synthesis | Formal reasoning, consistency auditing, deductive | Reasoning witness (read-only, stateless, high-latency OK) |
| **Gemini** | Conservative sanity | Summarization consistency, conventional interpretations | Style/tone canary, counterargument generator |
| **Grok** | Discourse distortion sensor | Internet discourse patterns, activation detection | Cultural pressure sensor (quarantined, never tie-breaker) |

Design principles:
- **Role separation beats averaging** — ask orthogonal questions, not the same question
- **Score on disagreement value** — a voter that always agrees is dead weight
- **Some models should be allowed to be wrong** — if never wrong, probably redundant
- **Latency diversity is a feature** — fast + slow models surface different failure modes
- Wire through same permissions/provenance/prompt-hash plumbing for independence scoring
- Grok is a wind tunnel for bad incentives, not a judge — always downstream simulation

Implementation: each model becomes an adapter (`voter_<model>.py`) with strict JSON schema
outputs, rate limiting, retry, and full provenance recording (model name, prompt hash,
response hash, latency, token usage).

---

## Future Features (Specced, NOT Scheduled)

Design documents exist in `ingest/`. These are frozen specs — reference material for when
the prerequisites are met. Do NOT implement until core layers (L4-L6) are complete.

### BFT-EQ: Byzantine Fault Tolerance for Epistemic Quorums (from `ingest/bft.md`)

**Status: SPEC FROZEN. Do not implement.**
**Prerequisite: Real adversarial pressure + stable independence labeling + empirical fault domain data.**

Full spec covers: fault domains, threat model (T1-T3), core invariants (I-BFT-1 through I-BFT-5),
data model (FaultDomain, Vote, ClaimCommitRecord), decision procedure (6 steps), fault budget
policies (fixed/risk-tiered/computed), independence mapping rules, failure modes (FM1-FM4),
and 5 acceptance tests.

One-line principle: "BFT-EQ ensures that any commitment is the output of an honest-majority
across independent fault domains, and that the system fails closed (refuses) when independence
or evidence is insufficient."

### Meta-Interferometry & Unified Consensus (from `ingest/interfer2.md`)

**Status: SPEC FROZEN. Do not implement.**
**Prerequisite: Multi-model execution infrastructure + real ensemble generation pipeline.**

Three concepts in one spec:

1. **Self-Testing Interferometry** — Use ensemble to verify its own synthesis.
   Generate → Synthesize → Self-test → Fix → Re-test → Approve.
   One round of self-verification is plenty. More is diminishing returns.

2. **Unified Consensus Engine** — Quorum (vote on actions) and interferometry (vote on content)
   are the same pattern: multiple independent evaluators reaching consensus. Unify under one
   ConsensusEngine with VotingStrategy (simple/supermajority/unanimous/weighted).

3. **Hierarchical Task Delegation** — Route by complexity to model tiers:
   Tech Lead (Opus) → Senior (Sonnet) → Mid (Haiku) → Junior (local/Qwen).
   Junior does work, senior reviews. Escalation on failure. 3-4x more work for same budget.
   Quality gate: tests_pass + lints_clean + types_valid + security_scan.

### Control-Theoretic Validation & Epistemic CRC (from `ingest/valid.md`)

**Status: SPEC FROZEN. Do not implement.**
**Prerequisite: Nonfiction governor corpus analysis + tone profiling complete.**

Five-layer research validation stack:

1. **Control Theory Validator** — Validate stability claims, feedback loop claims, Δt framework
   claims, equilibrium claims. Catches math errors in research output.

2. **Second-Order Cybernetic Validation** — Reflexive consistency: does the system embody its
   own principles? Ashby's Law of Requisite Variety check. Von Foerster eigenbehavior convergence.

3. **Falsifiability Validator** — Popper's criterion: every empirical claim must specify its own
   refutation criteria. Catches unfalsifiable AI slop ("generally improves", "tends to work").

4. **Epistemic CRC** — Checksum for research integrity (evidence chain hash + consistency hash +
   framework hash + reflexivity hash). Git-integrated, NOT auto-publish.

5. **Unified Hallucination Detection** — Δr (semantic drift) + Δt (temporal lag) + falsifiability +
   reflexivity = combined grounding signal. All measure the same thing: loss of grounding.

**Key constraint from spec:** Human decides what gets published. Governor ensures quality.
No auto-publish to Zenodo. Quality automation, not quantity automation.

---

## Unfinished Work: Semantic Enforcement Layer

These items close the gaps identified in `multi2.md` and `regime.md`. Ordered by
dependency — each step unblocks the ones below it. Design constraint: **extend
existing types, don't create parallel structures**. We already have Claim,
GroundedClaim, EvidenceRef, CommitLevel, etc. Wire them through, don't duplicate.

**Ordering notes (from `ingest/ordering.md`):**
- L1 → L2 is load-bearing: can't enforce anything until evidence persists and claims carry payloads
- **Decide L6 shape during L2** (even if implementing later) — ClaimStatus is epistemic
  lifecycle (proposed→supported→contested→invalidated→expired), QuorumState is process
  state. They map but aren't the same object. Define the enum early so L3-L5 have clean
  semantics to land on. CFI/Tone will demand stable "units" with lifecycle status.
- L3 before L4: evidence-kind requirements create clean failure signals for dependency work
- Consider thin L5 slice (role assignment) after L3 if L4 scope expands beyond tight premises
- **Boundary discipline**: L1-L5 emit structured signals (no prose). CFI/Tone consume
  signals and emit diagnostics, not new semantics. Refusal stays as saturation behavior.

### Layer 1: Evidence Persistence (foundation — everything else reads from this) ✓ COMPLETE

- [x] **Evidence table in SQLite** — `storage.py` Schema V2, `evidence_store.py`
  - `EvidenceRef` extended with persistence fields (evidence_id, claim_id, run_id, content_hash, etc.)
  - Append-only `EvidenceStore` class: persist_evidence, evidence_for_claim, evidence_by_kind/agent/run
  - Schema: evidence_id, claim_id, kind, content_hash, locator, scope, confidence, collected_by, run_id
  - Module: `src/governor/evidence_store.py` (75+ tests in tests/test_evidence_store.py)

- [x] **Run provenance table** — `storage.py` Schema V2, `evidence_store.py`
  - `RunProvenance` dataclass: run_id, agent_id, model_id, prompt_hash, tool_path_hash, source_urls
  - `EvidenceStore.record_run()`, `record_run_from_vote()`, runs_by_agent, run_count
  - Audit trail: JOIN evidence + run_provenance for "what tools did agent X use for claim Y?"

### Layer 2: Commit Level on Claims + ClaimStatus Shape ✓ COMPLETE

- [x] **`commit_level` field on `GroundedClaim`** — `epistemic.py`
  - String field: "hard", "soft", "refused", or None (unclassified)
  - `set_commit_level()` / `add_assumption()` on EpistemicLedger
  - Schema V3: commit_level + assumptions_json columns on facts/decisions tables
  - Module: `src/governor/epistemic.py` (30+ tests in tests/test_commit_level.py)

- [x] **`assumptions` field on `GroundedClaim`** — `epistemic.py`
  - `assumptions: list[str]` — explicit ungrounded dependencies
  - Populated when claim depends on SOFT/unverified premises
  - Surfaced in CLI and audit output

- [x] **`ClaimStatus` enum shape** — `epistemic.py` (L6 decision, pulled forward)
  - Enum: PROPOSED, SUPPORTED, CONTESTED, INVALIDATED, EXPIRED, REFUSED, STALE
  - `epistemic_status: ClaimStatus | None = None` on GroundedClaim (None = legacy compat)
  - `QUORUM_TO_CLAIM_STATUS` mapping: 9 QuorumStatus values → ClaimStatus
  - `project_quorum_status()` helper function
  - `set_epistemic_status()` / `claims_by_epistemic_status()` on EpistemicLedger
  - Full FSM transitions + enforcement deferred to Layer 6

- [x] **EpistemicLedger persistence** — `epistemic.py` + `storage.py` Schema V4
  - `epistemic_claims` table + `epistemic_ledger_meta` table in SQLite
  - Optional `storage` + `evidence_store` params on EpistemicLedger.__init__
  - Write-through on all mutation methods (new_claim, promote, block, retract, etc.)
  - `from_dict()` / `from_json()` class methods for deserialization
  - CLI `get_epistemic_ledger()` uses SQLite when DB exists, falls back to JSON
  - Module: tests/test_claim_status.py (40 tests) + tests/test_epistemic_persistence.py (35 tests)

### Layer 3: Evidence Type Validation (enforcement — gates on Layer 1 data) ✅

- [x] **Evidence kind requirements per claim type** — `epistemic.py` / `audit.py` / `quorum.py` / `jurisdictions.py`
  - 4 new EvidenceType values: CALC_RESULT, TEST_RESULT, WEB_SOURCE, LIVE_RETRIEVAL
  - 4 new EvidenceRef factory methods: from_calc_result, from_test_result, from_web_source, from_live_retrieval
  - WRONG_EVIDENCE_TYPE failure mode in audit pipeline (severe → UNGROUNDED → BLOCK)
  - required_evidence_kinds on PolicyEntry with default matrix (6 claim types)
  - required_evidence_types on QuorumPolicy with default policies
  - Gate 6 in can_proceed() + COLLECTING→STABILIZING transition gate
  - New jurisdiction admissibility: FACTUAL/AUDIT admit all 4; SPECULATIVE/ADVERSARIAL/FORENSIC admit subsets
  - Module: tests/test_evidence_types.py (86 tests)

### Layer 4: Premise Rule & Dependency Tracking ✅

- [x] **Premise rule enforcement** — `epistemic.py` + `quorum.py`
  - SOFT/STALE/INVALIDATED/CONTESTED/REFUSED claims cannot serve as premises for HARD claims
  - If a HARD claim's dependency is SOFT → downgrade to SOFT
  - `depends_on: list[str]` field on GroundedClaim for machine-traversable dependency edges
  - `add_dependency()` / `remove_dependency()` with cycle detection and persistence
  - `check_premise_rule()` / `enforce_premise_rule()` on EpistemicLedger
  - In-memory reverse index (`_reverse_deps`) for O(1) dependent lookup
  - Quorum Gate 7: scans all HARD claims for premise violations
  - Schema V5: `depends_on_json` column, `claim_dependencies` table, `cascade_events` table
  - Module: `src/governor/epistemic.py`, `src/governor/quorum.py`, `src/governor/storage.py`

- [x] **Dependency invalidation cascade** — `epistemic.py`
  - BFS cascade: retract/block/set_epistemic_status triggers HARD→SOFT downgrade on dependents
  - Transitive: cascades through full dependency graph (diamond, chain)
  - `CascadeEvent` dataclass with depth tracking and audit trail
  - `invalidation_cascade()` method with persist to `cascade_events` table
  - Hooked into `retract()`, `block()`, `set_epistemic_status()` (for INVALIDATED/STALE/CONTESTED/REFUSED/EXPIRED)
  - Module: tests/test_premise_rules.py (88 tests)

### Layer 5: Roles & Scheduling (higher-level policy) ✅

- [x] **Agent role assignment** — `quorum.py`
  - `AgentRole` enum: PROPOSER, RETRIEVER, FALSIFIER, SYNTHESIZER
  - `RoleBudget` dataclass with `DEFAULT_ROLE_BUDGETS` per RiskLevel (LOW/MEDIUM/HIGH)
  - `required_roles` on `QuorumPolicy` — default policies require appropriate roles per claim type
  - `agent_role` on `Vote` — tracks which role each voter fills
  - `role_assignments` / `roles_filled` / `missing_roles` on `QuorumState`
  - Gate 8 in `can_proceed()` — blocks if required roles not filled
  - HIGH risk auto-adds FALSIFIER requirement regardless of claim type
  - Full to_dict/from_dict serialization, backward compatible (role fields optional)
  - Spec ref: `multi2.md` §2, §7

- [x] **Periodic revalidation scheduling** — `ttl.py` integration
  - `RevalidationOrchestrator`: wires TTLManager → AuditPipeline (stage=PERIODIC)
  - `RevalidationResult` / `RevalidationRun` dataclasses for structured output
  - Lifecycle: enforce decay → get schedule → audit each claim → update epistemic status
  - `_build_signals()` enriches DetectionSignals from epistemic ledger evidence_refs
  - `_update_epistemic_status()`: ALLOW_HARD=passed, DOWNGRADE_SOFT=STALE, BLOCK=INVALIDATED
  - `create_revalidation_orchestrator()` convenience function
  - Tracks metrics: claims_checked, passed, degraded, blocked, errors
  - Module: tests/test_roles_revalidation.py (67 tests)
  - Spec ref: `regime.md` §2.3

### Layer 6: ClaimStatus FSM Enforcement (shape defined in L2, transitions enforced here) ✅

- [x] **ClaimStatus transition enforcement** — `epistemic.py`
  - `TransitionReason` enum: EVIDENCE, AUDIT_RESULT, TTL_EXPIRY, CASCADE, QUORUM_PROJECTION, DISSENT, RETRACTION, REVALIDATION, HUMAN
  - `StatusTransition` dataclass with full audit trail (from/to status, reason, justification, step, timestamp)
  - `TransitionResult` dataclass (success/failure with error message)
  - `VALID_TRANSITIONS` table: ~25 legal edges with allowed reason sets per edge
  - `is_valid_transition()` standalone validator function
  - `transition_epistemic_status()` — primary FSM-enforced method on EpistemicLedger
  - `set_epistemic_status()` — backward-compatible wrapper using HUMAN override
  - `get_transition_history()` — per-claim or global transition audit log
  - `fsm_enforced` toggle on EpistemicLedger (True by default, False for legacy compat)
  - Terminal states (INVALIDATED, EXPIRED, REFUSED) → PROPOSED only via HUMAN
  - HUMAN reason always bypasses FSM (for manual override)
  - Integration with L4 cascade: SUPPORTED dependents → STALE on cascade
  - Integration with block()/retract(): auto-transitions epistemic status when set
  - Integration with TTL revalidation: proper TransitionReason (TTL_EXPIRY/REVALIDATION)
  - Module: tests/test_claim_fsm.py (106 tests)

---

## Unfinished Work: Nonfiction CFI (Separate Workstream)

From `ingest/next2.md`. This is the nonfiction analogue of fiction's DSI/context-drift
detection. The spec explicitly warns: **do not delegate value choices to code**.
Human authority needed for definitions, thresholds, and hard/soft classification.

- [x] **Frame taxonomy** — human-authored v0 starter taxonomy (12 frames)
  - NonfictionFrame enum: CAPITALISM, SOCIAL_JUSTICE, TRAUMA, BOTH_SIDES, EXPERTS_SAY,
    PROGRESS, SAFETY, SYSTEMIC, INDIVIDUAL, NATURAL, TECHNOLOGICAL, MORAL
  - Intentionally small, designed to expand by evidence (logged hit counts)
  - Module: `src/nonfiction_governor/cfi.py`

- [x] **Contextual Frame Intrusion (CFI) detector** — v0: detect + tag + warn, no blocking
  - Same architecture as fiction context_drift.py: pattern-based, weighted regex matching
  - classify_frames(text) → FrameSignal list with confidence + match counts
  - classify_perspective(text) → PerspectiveSignal (DESCRIPTIVE/NORMATIVE/PRESCRIPTIVE/ANALYTICAL)
  - check(text) → CFICheckResult with frames, perspective, faults, scope_risk
  - record(text) → check + update state (frame counts, perspective history)
  - CFIDetector: set_expected_frames(), set_expected_perspective(), stats(), reset()
  - CLI: `nonfiction-gov cfi check/scan/frames/perspectives`

- [x] **Nonfiction state vector** — Perspective (P_t) + active frames (F_t) tracked
  - CFIState: frame_counts, perspective_history, expected_frames, expected_perspective
  - dominant_frame(), frame_ratio(), perspective distribution stats
  - Windowed analysis for normative creep detection

- [x] **Nonfiction hard constraints** — v0 as warnings (no blocking)
  - Normative creep: descriptive/analytical context drifting to normative
  - Scope violations: case→population generalization detection (regex patterns)
  - Epistemic mismatch covered by normative creep + perspective tracking

- [x] **Nonfiction soft penalties** — v0 as warnings
  - Uninvited frame: frame detected but not in expected set
  - Frame overuse: same frame in >60% of checks (configurable threshold)
  - Normative creep: windowed history detection
  - Scope violation: pattern-based generalization detection

**CFI v0 tests: 68** (in tests/test_cfi.py)

---

## Tone Profiling & Style Enforcement (from `ingest/tone.md`)

Voice/tone as canon for nonfiction. Fiction has character canon, code has architecture
decisions — nonfiction needs enforceable style parameters extracted from the author's
corpus. Without this, autonomous writing produces generic AI prose instead of the
author's voice. **This is the last core feature before deferred cross-cutting work.**

### Phase T1: ToneProfile & Manual Authoring ✅

- [x] **ToneProfile dataclass** — `src/nonfiction_governor/tone.py`
  - 28 dimensions: sentence structure (avg length, variance, fragments, colons),
    paragraph structure (avg length, single-sentence), voice (2nd/1st person, contractions),
    rhetorical devices (questions, parentheticals, em dashes, ellipses),
    framing patterns (opening/transition/closing), vocabulary (adjectives, verbs, density),
    tone markers (profanity, sarcasm, pop culture), structure (headers, lists, examples),
    custom guidance (free-form)
  - to_dict/from_dict, save/load to `.governor/tone_profile.json`
  - All fields have defaults; profiles can be partial

- [x] **Text analysis** — `analyze_text(text)` mechanical metrics extraction
  - Sentence length (avg, variance), paragraph count, fragment detection
  - Contraction frequency (regex-based: it's/it is, don't/do not, etc.)
  - Voice pattern detection (2nd/1st person, em dashes, ellipses, parentheticals)
  - Colon emphasis, rhetorical questions, single-sentence paragraphs

- [x] **ToneChecker** — Check text against ToneProfile with configurable tolerance
  - ToneViolation dataclass (dimension, message, expected, actual, suggestion)
  - ToneCheckResult dataclass (valid, violations, metrics)
  - Checks: sentence length drift, fragment usage, voice patterns, contraction frequency,
    em dashes, rhetorical questions, parentheticals
  - All violations include actionable suggestions

- [x] **Manual tone profile creation** — JSON authoring
  - `nonfiction-gov tone create` (from stdin JSON or --file)
  - `nonfiction-gov tone show` — display current profile
  - `nonfiction-gov tone edit` — show path for manual editing
  - `nonfiction-gov tone delete` — remove profile

- [x] **Tone guidance generation** — `generate_tone_guidance(profile)` → natural language
  - `format_system_prompt(profile)` → full system prompt fragment
  - Covers: sentence structure, voice, contractions, rhetorical devices, opening patterns,
    technical density, tone markers, custom guidance, structure preferences
  - ToneManager persistence + lifecycle (set/clear/lock/unlock/check/guidance)

- [x] **Tone CLI commands** — `nonfiction-gov tone` group
  - `show`, `create`, `edit`, `check <file>`, `guidance`, `lock`, `unlock`, `delete`
  - Module: tests/test_tone.py (68 tests)

### Phase T2: Corpus Analysis & Automatic Extraction ✓ COMPLETE

- [x] **Corpus ingestion** — Analyze reference writing to extract profile automatically
  - `extract_tone_profile(corpus_files: list[Path])` → ToneProfile
  - Sentence extraction + length statistics (mean, variance)
  - Fragment detection (sentences without subject-verb structure)
  - Colon-for-emphasis pattern detection
  - Second/first person frequency analysis
  - Contraction frequency (it's/it is, don't/do not, etc.)
  - Rhetorical device frequency (em dashes, parentheticals, questions)
  - Opening/transition/closing pattern extraction (n-gram frequency at paragraph boundaries)
  - Technical density: jargon ratio via vocabulary analysis (syllable-based complex word detection)
  - Vocabulary extraction: frequent content words, adjective/verb classification by suffix heuristic
  - Boolean aggregation: threshold-based (configurable, default 0.3)
  - CLI: `nonfiction-gov tone ingest reference_writing/*.md`

- [x] **Profile comparison** — Diff two profiles or profile vs text
  - `compare_profiles(baseline, new)` → list[ProfileDeviation]
  - Per-dimension deviation with tolerance thresholds (numeric: per-dim, boolean: any change, string: any change)
  - `ProfileDeviation` dataclass with dimension, values, deviation magnitude, significance flag
  - CLI: `nonfiction-gov tone compare <file>` — extract + compare against active profile
  - Useful for: "has my voice drifted since chapter 1?"

**54 new tests (122 total tone tests in tests/test_tone.py)**

### Phase T3: Style Enforcement as Invariant ✓ MOSTLY COMPLETE

- [x] **StyleInvariant** — Mechanical verification of tone consistency
  - ToneChecker acts as StyleInvariant with configurable tolerance (default 0.2)
  - `check(content)` → ToneCheckResult(valid, violations, metrics)
  - Checks: sentence length drift, fragment usage, contraction frequency,
    technical density, voice patterns (second person, first person),
    em dashes, rhetorical questions, parentheticals
  - Each violation includes: dimension, expected value, actual value, suggestion
  - Integration with autonomous executor deferred (see Deferred 1)

- [x] **Tone checking CLI** (implemented in Phase T1)
  - `nonfiction-gov tone check <file>` — analyze file against profile, report violations
  - `nonfiction-gov tone lock` — lock current profile as enforcement invariant
  - `nonfiction-gov tone unlock --confirm` — disable tone enforcement

- [x] **Tone drift warnings** — Surface during autonomous execution via `tone_invariant()` adapter
  - `tone_invariant(checker)` wraps ToneChecker as an Invariant for the executor
  - Violations surface specific suggestions: "break up long sentences", "use more contractions"
  - Default warn-only; can be set to block for strict enforcement
  - Module: `src/governor/adapters.py` (integrated with Phase A4)

---

## Cross-Cutting (Deferred — AFTER all core functionality)

These items come LAST. All semantic enforcement layers (1-6), nonfiction CFI, and
remaining core work must be complete before starting these. They are refinements,
integrations, and delivery mechanisms — not core governance logic.

- [x] **Minor: CLI bug** - `src/governor/cli.py` line 7388: `bank.seed_defaults()` doesn't exist on PhraseBank
- [x] **Minor: Profile boil presets** - `profiles.py` references DARJEELING/CHAI which don't exist in ControlMode enum

---

### Deferred 1: Autonomous Execution (from `ingest/autorun.md`)

Governor-constrained autonomous operation. Agent proposes, governor auto-approves
when spine + invariants are satisfied. Human defines constraints, governor enforces
mechanically. "CI/CD for AI agents."

**Not contradictory:** Human still defines what "approved" means (spine, invariants,
budgets). Governor auto-approves only within those bounds. Human can stop/resume/override
at any time.

#### Phase A1: Core Types & Spine Management ✅

- [x] **Spine dataclass** — Locked project structure (immutable until explicit unlock)
  - `id`, `structure` (dict), `locked_at`, `locked_by`, `unlock_requires`
  - `verify_proposal(proposal)` → SpineCheckResult with SpineViolation list
  - Structure: required files, required directories, forbidden paths (glob patterns)
  - SpineManager: lock/unlock/get/list/set_active/deactivate/verify_proposal
  - Persistence: JSON files in `.governor/spines/`, active spine tracking
  - Module: `src/governor/spine.py` (41 tests)

- [x] **Invariant system** — Mechanically verifiable rules (no vibes)
  - `InvariantType` enum: STRUCTURE, EVIDENCE, ARCHITECTURE, TEST, CONSISTENCY, FORBIDDEN
  - `Invariant` dataclass: id, type, rule (human-readable), verify (callable), on_violation, enabled
  - `InvariantSet`: collection with check_all(), blocking_violations(), add/remove/get
  - Key insight: if you can't verify it mechanically, it's a guideline, not an invariant
  - `InvariantLibrary` factory methods: tests_must_pass, file_must_exist, directory_must_exist,
    forbidden_pattern, no_secrets, max_file_size
  - Module: `src/governor/invariants.py` (36 tests)

- [x] **ExecutionBudget** — Resource limits (tokens, time, iterations, cost USD)
  - `is_exhausted(used)` → (bool, reason) — whichever limit hits first stops execution
  - `remaining(used)` → per-dimension remaining budget
  - `from_spec("tokens=100000,iterations=50,time=1800,cost=5.00")` parser
  - `ExecutionUsage`: cumulative tracking with add_iteration()
  - Module: `src/governor/execution.py`

- [x] **ExecutionState** — Persistent state for multi-session execution
  - session_id, task, spine_id, invariant_ids, budget, used, progress, violations, status
  - Statuses: RUNNING, PAUSED, STOPPED, COMPLETED
  - Stop reasons: AGENT_COMPLETION, CONSTRAINT_VIOLATION, BUDGET_EXHAUSTED, HUMAN_STOP, ERROR
  - checkpoint()/load() for disk persistence
  - `SessionManager`: create/get/save/list/delete sessions in `.governor/autonomous/`
  - Module: `src/governor/execution.py` (34 tests)

- [x] **Spine CLI** — Lock/unlock/list/show/activate/deactivate/check
  - `governor spine lock <id> [-rf file] [-rd dir] [--forbid pattern] [-f spec.json]`
  - `governor spine unlock <id> --confirm`
  - `governor spine list`, `governor spine show <id>`
  - `governor spine activate <id>`, `governor spine deactivate`
  - `governor spine check [-m file] [-c file] [-d file]`

**Phase A1 tests: 111**

#### Phase A2: Autonomous Executor ✅

- [x] **AutonomousExecutor** — Step-function executor with governor constraints
  - Constructor: spine_manager, invariants, session_manager, config
  - `execute(step_fn, task, budget, spine_id, resume_state)` → ExecutionState
  - Step function pattern: `(ExecutionState, int) → StepResult`
  - Spine compliance check after each step
  - Invariant verification (blocking_violations) after each step
  - Budget enforcement before each step (tokens, iterations, time, cost)
  - Checkpointing every N iterations + final checkpoint
  - Consecutive failure tracking with configurable max
  - Rate limiting between iterations
  - `ExecutorConfig`: stop_on_violation, checkpoint_interval, rate_limit_seconds, max_consecutive_failures
  - `StepResult`: success, message, files_modified/created/deleted, tokens_used, cost_usd, progress, done
  - `ExecutionEvent`: iteration, event_type, message, timestamp, details (audit trail)
  - Module: `src/governor/executor.py` (45 tests)

- [ ] **Invariant management CLI** (deferred)
  - `governor invariant add --type <type> --rule <text>`
  - `governor invariant list`
  - `governor invariant remove --id <id>`

- [ ] **Execution CLI** (deferred — needs real agent integration)
  - `governor execute --task <desc> --spine <name> --budget <spec>`
  - `governor execute --resume <session_id>`

#### Phase A3: Session Management & Multi-Day Execution ✅

- [x] **Session persistence** — Save/resume execution state across days
  - Checkpoint files: `.governor/autonomous/<session_id>.json`
  - Resume from any checkpoint via executor resume_state parameter
  - Progress tracking via state.progress dict

- [x] **Session CLI** — `governor autonomous` command group
  - `governor autonomous list [--active]` — sessions with status, iterations, tokens, task
  - `governor autonomous show <id>` — full state, violations, budget, progress
  - `governor autonomous handoff <id>` — handoff summary (progress, remaining, violations)
  - `governor autonomous delete <id> --confirm`

- [x] **Handoff generation** — Everything needed to resume
  - What was accomplished, what's left, current state, budget remaining, violations
  - Via `governor autonomous handoff <id>`

#### Phase A4: Integration with Existing Governors ✅ COMPLETE

- [x] **Governor adapter invariants** — `src/governor/adapters.py` (76 tests)
  - Thin factory functions wrapping domain governors as `Invariant` objects
  - `security_invariant()` — wraps SecurityVerifier, scans touched files for vulnerabilities with severity threshold
  - `cfi_invariant()` — wraps CFIDetector, checks prose files for contextual frame intrusion (default warn-only)
  - `fiction_invariant()` — wraps fiction CombinedVerifier, runs quick_check on prose files
  - `nonfiction_citation_invariant()` — wraps CitationVerifier, extracts and validates citations
  - `content_invariant()` — generic adapter: any `(content, path) → (bool, message)` becomes an Invariant
  - `AdapterConfig` + `build_adapter_set()` — convenience builder for multi-governor setups
  - `AdapterFinding` — unified finding type across all adapters
  - File extension filtering: TEXT_EXTENSIONS (code+prose), PROSE_EXTENSIONS (prose-only)
  - No cross-imports between governor packages; governors stay dumb libraries
  - Full integration with InvariantSet.blocking_violations() and executor loop

#### Strategic Test Suites (from `ingest/govtests.md`) ✅ COMPLETE

- [x] **Golden-file tests for JSON artifacts** — `tests/test_golden_files.py` (107 tests)
  - Locks serialization schemas for all `to_dict()` types: FileSnapshot, CmdRun, DiffReceipt, ExecutionBudget/Usage/State, Spine, SpineCheckResult, InvariantResult, Invariant, InvariantSet, Fact, Decision, EvidenceRef, GroundedClaim, StatusTransition, CascadeEvent, PremiseCheckResult, QuorumPolicy, Vote, QuorumState, ClaimSnapshot, LedgerSnapshot, MutationEvent, Violation, DiffResult, AdapterFinding
  - Key set assertions, value type assertions, round-trip tests, JSON serializability
  - Cross-type stability tests: receipt type tags, universal JSON safety, full round-trips

- [x] **No-laundering regression tests** — `tests/test_no_laundering.py` (40 tests)
  - Money Rule: ASSUMED confidence starts low, PEER_ASSERTED capped at MAX_PEER_CONFIDENCE
  - Provenance Rule: promotions require evidence, PEER→OBSERVED always forbidden
  - Premise Rule: HARD claims cannot depend on SOFT, cascade on retraction, cycle/self-dep rejection
  - Silent Retraction: claims stay in ledger, retraction counted, ClaimDiffer detects disappearance
  - Envelope Mode Retrograde: facts/decisions/epistemic claims survive strict→exploratory switch
  - Evidence Type Gating: enum completeness, factory correctness, grounding rules
  - ClaimStatus FSM: transition guards enforced, terminal states HUMAN-only, HUMAN always valid

- [x] **Failure-injection tests for executor** — `tests/test_failure_injection.py` (27 tests)
  - Timeout handling: TimeoutError counts as failure, recorded in events, state stays consistent, recovery works
  - Checkpoint write failures: fail-closed (OSError propagates), final save failure handled
  - Corrupted checkpoint resume: bad JSON raises, empty file raises, partial JSON uses defaults, invalid status raises, SessionManager skips bad files
  - Consecutive failure threshold: stops at limit, recovery resets counter, all exception types counted
  - Budget exhaustion: token/iteration/cost limits, pre-step checking, accurate usage tracking
  - Spine/invariant checks during recovery: violations stop execution, warnings don't block
  - State persistence under faults: saved after error/budget/completion stops, resume from saved state

- [x] **Property-based invariant tests** — `tests/test_property_invariants.py` (158 tests)
  - Confidence bounds: clamping across extreme values, PEER_ASSERTED cap, default confidence per provenance
  - Provenance properties: grounding is boolean, grounded/ungrounded sets are known and disjoint
  - ClaimStatus FSM: HUMAN reason always valid from any state, same-status always valid, terminal states block non-HUMAN, all valid transitions have at least one reason
  - Budget enforcement: at/over limit = exhausted, under limit = not exhausted, None limits never exhaust, remaining never negative
  - Execution state: stop/complete set correct status, pause/resume cycle, resume only from paused, active/inactive state partitioning
  - Fail-closed: exceptions in steps counted as failures, blocking invariants stop execution
  - InvariantSet: all-pass = no blocking, warning failures not in blocking, block failures in blocking, disabled invariants skipped, blocking count matches
  - Cascade: terminates on chains, handles diamonds, soft claims unaffected
  - Serialization roundtrip: GroundedClaim per provenance, ExecutionState per status/stop_reason, EvidenceRef per type

- [x] **Contract tests for adapters** — `tests/test_contract_adapters.py` (122 tests)
  - Invariant interface contract: all 6 adapter factories return Invariant with correct fields, to_dict shape locked
  - InvariantResult contract: all verify() calls return InvariantResult with correct shape and to_dict
  - Empty input safety: all adapters handle no files, no kwargs, nonexistent files without crashing
  - Finding detection: security/CFI/fiction/citation/tone/content adapters surface violations correctly
  - AdapterFinding contract: to_dict keys locked, default severity/details, findings in security details
  - Parameter forwarding: on_violation and invariant_id respected for all 6 adapter types
  - No input mutation: files_touched list never modified by adapters
  - Disabled invariant bypass: enabled=False → passed=True without calling verify
  - build_adapter_set: empty config → empty set, each verifier type individually, all together, config forwarding (min_severity, max_faults, characters)
  - content_invariant: check_fn receives content+path, exceptions become findings, custom extensions filter, type forwarding, id derivation
  - Severity threshold: low below high, high at high, critical at high, medium at medium
  - CFI fault tolerance: within tolerance passes, exceeding tolerance fails
  - File extension filtering: CFI/fiction skip non-prose files
  - InvariantSet integration: adapter set works in InvariantSet, blocking vs warn separation
  - Verifier exception handling: all 5 verifier types gracefully skip on exception

---

### Deferred 2: Web UI — Household Claude (from `ingest/webui.md`)

ChatGPT-like web interface routing through governor with isolated contexts per
user/project. One Claude account, multiple isolated governor contexts.

#### Phase W1: MCP Bridge & Context Manager

- [ ] **ClaudeBridge** — `src/governor/mcp_bridge.py`
  - Single point of Claude API access with governor context injection
  - `chat(messages, model, context_id, streaming)` — main routing with governor integration
  - Streaming support (async generator), governor hooks for response validation
  - `get_governor(context_id)` — access context-specific governor

- [ ] **GovernorContextManager** — `src/governor/context_manager.py`
  - Manage multiple isolated governor instances
  - `get_or_create(context_id, mode)` — fiction/code/ops governor per context
  - `list_contexts()`, `delete_context()`
  - Directory structure: `~/.governor-contexts/<context_id>/.governor/`
  - Complete isolation: no shared state, no cross-contamination

#### Phase W2: Web Adapter (FastAPI)

- [ ] **OpenAI-compatible API** — `src/governor/web_adapter.py`
  - `POST /v1/chat/completions` — main chat (SSE streaming, OpenAI format)
  - `GET /v1/models` — list available Claude models
  - `GET /health` — status check with governor info (context, mode, stats)
  - `GET /governor/canon` — fiction mode canon viewer
  - CORS middleware for browser access
  - Environment config: GOVERNOR_CONTEXT_ID, GOVERNOR_MODE, ANTHROPIC_API_KEY

#### Phase W3: Docker Deployment

- [ ] **Docker setup** — Multi-container deployment
  - Dockerfile: Python 3.11 + governor + uvicorn
  - docker-compose.yml: per-user stacks (webui + adapter)
  - Each user gets: Open WebUI instance (port 3001/3002) + adapter instance (port 8001/8002)
  - Shared: Claude API key via .env, governor contexts via volume mount
  - No auth in MVP (port separation = user separation)

#### Phase W4: Mode-Specific Integration

- [ ] **Fiction mode for Erin** — Canon checking, character continuity, timeline validation
  - Governor violations surface naturally in chat responses
  - Canon violation → offer: fix instance, revise canon, proceed with inconsistency

- [ ] **Code mode for James** — Architecture enforcement, decision tracking, proposal workflow
  - Decision conflicts surface in chat
  - Receipt-based verification in conversation flow

---

### Deferred 3: VS Code Extension (from `ingest/vscode.md`)

Thin control surface for using the governor while coding. Extension shells out to
governor CLI — no reimplementation of logic. Everything the extension does should
be doable via CLI; extension just makes it faster with visual feedback.

**Design principle:** Extension is stateless. All state lives in `.governor/`.
Extension just queries and displays it.

#### Phase V1: Core Commands & Diagnostics

- [ ] **Governor CLI client wrapper** — TypeScript wrapper around `governor check --format json`
  - Input: stdin JSON (content, filepath, context)
  - Output: JSON (status, findings with code/message/severity/range/suggestion, summary)
  - Configurable executable path via settings

- [ ] **"Governor: Check Selection" / "Governor: Check File" commands**
  - Shell out to governor binary, pass selected text/file via stdin
  - Parse JSON response, create DiagnosticCollection
  - Severity mapping: error → red squiggle, warning → yellow, info → blue

- [ ] **Status bar item** — `[Governor] [Session: 1h23m] [Tasks: 2/5] [Budget: 47%]`
  - Click behaviors for each section

- [ ] **Output channel** — Raw governor output for debugging

#### Phase V2: Side Panel & State Display

- [ ] **TreeView** — Governor state panel
  - Session info (active, duration, tasks)
  - Decisions (active, conflicting proposals)
  - Facts (fresh, stale)
  - Tasks (claimed, available, blocked)
  - Autonomous execution status (if running)
  - Interactive: click → show context, claim/unclaim tasks

#### Phase V3: Mode-Specific Features

- [ ] **Code mode** — Pre-commit hook integration, task claiming workflow, real-time architecture violation detection (debounced on-type checking)

- [ ] **Fiction mode** — Canon lookup panel (character details, timeline, relationships), real-time canon checking (squiggles for inconsistencies), timeline validation

- [ ] **Non-fiction mode** — Citation checking, framework term consistency (hover shows definition + usage), quick reference panel for terms

#### Phase V4: Advanced Features

- [ ] **Hover tooltips** — Governor context on hover (decision records, framework terms)
- [ ] **Code actions (quick fixes)** — Auto-fix suggestions from governor findings
- [ ] **Peek definition for decisions** — F12/Alt+F12 on decision references
- [ ] **Real-time checking** — Debounced on-type checking (off by default, 500ms)

#### Phase V5: Autonomous Mode Monitor

- [ ] **Execution monitor** — Real-time progress (iterations, budget, approval rate)
- [ ] **Violation notifications** — Popup on constraint violation with fix/context/exception actions
- [ ] **Pause/resume controls** — In-editor autonomous execution management
- [ ] **Real-time diff viewer** — Shows what autonomous executor is writing as it works

#### Extension File Structure

```
vscode-governor/
├── package.json           # Extension manifest
├── src/
│   ├── extension.ts       # Entry point
│   ├── commands/          # check, propose, session, autonomous, fiction
│   ├── views/             # governor-tree, canon-panel, autonomous-monitor
│   ├── diagnostics/       # provider.ts (squiggles)
│   ├── hovers/            # provider.ts (tooltips)
│   ├── code-actions/      # provider.ts (quick fixes)
│   ├── governor/          # client.ts (CLI wrapper), types.ts, state.ts
│   └── utils/             # git.ts, formatting.ts
└── resources/icons/       # Tree view icons
```

---

### Deferred 4: Task Balancing & Telemetry (from `ingest/balance-telemetry.md`)

Two post-MVP features extending the governor's routing and observability.
Task balancing extends existing `routing.py`. Telemetry is new infrastructure.

#### Phase B1: Enhanced Task Balancing (extends `routing.py`)

- [ ] **LLM capability profiles** — Cost/latency/strength per model
  - `LLMProfile`: model_id, provider, max_complexity, strengths, context_window,
    cost_input/output (per 1M tokens), latency p50/p95, rate limits
  - Pre-defined profiles: claude-haiku-4, claude-sonnet-4, claude-opus-4,
    gpt-4o-mini, gpt-4o, deepseek-coder
  - This extends existing `ModelCapabilities` in routing.py with cost data

- [ ] **Routing strategies** — Cost/speed/quality/balanced optimization
  - `cost_optimal`: Cheapest model that can handle complexity
  - `speed_optimal`: Fastest model that can handle complexity
  - `quality_optimal`: Best model regardless of cost
  - `balanced`: Weighted sum of cost/speed/quality scores
  - Fallback chains: if primary fails, escalate to next tier
  - `governor config set routing.strategy cost_optimal`

- [ ] **Budget management** — Multi-scope cost tracking
  - `Budget` dataclass: total_usd, spent_usd, model_limits
  - `BudgetManager`: session/task/project scopes, all checked before routing
  - `governor session start --budget 10.00`
  - `governor task add "task" --budget 2.50`
  - `governor budget status` — spending breakdown by model and operation

- [ ] **Routing explainability** — `governor task route <id> --explain`
  - Show complexity analysis, selected model, reason, alternatives with costs

#### Phase B2: Structured Telemetry

- [ ] **StructuredLogger** — JSON-line logging to `.governor/logs/governor-YYYYMMDD.jsonl`
  - Event types: proposal, verification, llm_call, autonomous_iteration, error
  - Each entry: timestamp, event_type, level, plus type-specific fields
  - Log rotation: configurable max size, retention days

- [ ] **TelemetryCollector** — Central event router to all configured backends
  - `record_proposal()`, `record_verification()`, `record_llm_call()`
  - Routes to StructuredLogger and/or PrometheusMetrics
  - Integration: Governor constructor creates TelemetryCollector from config

- [ ] **Telemetry CLI**
  - `governor telemetry enable --logging --prometheus`
  - `governor telemetry logs --last 100 --type llm_call`
  - `governor telemetry analyze costs --since "2025-02-01"` (by model, by operation)
  - `governor telemetry analyze performance` (verification latency p50/p95/p99, approval rate)
  - `governor telemetry export --format csv --output report.csv`
  - `governor telemetry rotate-logs`

#### Phase B3: Prometheus & Grafana (optional)

- [ ] **PrometheusMetrics** — Counters, histograms, gauges for governor operations
  - Counters: proposals_total, verifications_total, llm_calls_total, tokens_total, cost_total, errors_total
  - Histograms: verification_duration, llm_call_duration
  - Gauges: active_sessions, autonomous_iterations, budget_remaining
  - `start_http_server(port=9090)` — expose at `/metrics`

- [ ] **Grafana dashboards** — Pre-built PromQL queries
  - Proposal throughput, verification success rate, LLM cost rate, token consumption,
    average latency, budget utilization, error rate

#### Telemetry Configuration

```toml
[telemetry]
logging = true
log_dir = ".governor/logs"
log_retention_days = 30
prometheus = false
prometheus_port = 9090
redact_file_contents = true
redact_prompts = false
```
