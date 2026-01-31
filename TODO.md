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
  - 5 builtins: strict, permissive, research, production, audit
  - Custom profile creation/deletion, activation/deactivation
  - Applies envelope, boil, jurisdiction, and strict mode in one command
  - Module: `src/governor/profiles.py` (45 tests)
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
- `multi2.md` - Δt quorum governor (semantic enforcement gaps, ~75% done)
- `regime.md` - Grounding audit pipeline (assertion/cascade/roles gaps, ~85% done)
- `next.md` - Semantic entropy (conceptual, fiction guardrails portion complete)
- `next2.md` - Nonfiction CFI (not started, requires human authority decisions)
- `vscode.md` - VS Code integration (deferred, UI last)

---

## Unfinished Work: Semantic Enforcement Layer

These items close the gaps identified in `multi2.md` and `regime.md`. Ordered by
dependency — each step unblocks the ones below it. Design constraint: **extend
existing types, don't create parallel structures**. We already have Claim,
GroundedClaim, EvidenceRef, CommitLevel, etc. Wire them through, don't duplicate.

### Layer 1: Evidence Persistence (foundation — everything else reads from this)

- [ ] **Evidence table in SQLite** — `storage.py`
  - Promote `EvidenceRef` from in-memory pointer to persistent record
  - Schema: evidence_id, claim_id, kind (EvidenceType), content_hash, locator, scope,
    confidence, collected_by (agent_id), timestamp
  - Append-only invariant (immutable once written)
  - Query: by claim_id, by kind, by agent_id
  - **Do not** create a new Evidence dataclass — extend `EvidenceRef` with persistence methods
  - Spec ref: `multi2.md` §1.2

- [ ] **Run provenance table** — `storage.py`
  - Schema: run_id, agent_id, model_id, prompt_hash, tool_path_hash, source_urls, timestamp
  - Links to evidence (run_id on evidence rows)
  - Enables audit query: "what tools did agent X use for claim Y?"
  - Currently tracked ad-hoc via Vote fields — consolidate, don't duplicate
  - Spec ref: `multi2.md` §1.4

### Layer 2: Commit Level on Claims (wiring — connects strict.py to the ledger)

- [ ] **Add `commit_level` field to `GroundedClaim`** — `epistemic.py`
  - Use existing `CommitLevel` enum from `strict.py` (HARD/SOFT/REFUSED)
  - Default: None (unclassified, for backward compat)
  - Set during verification or strict-mode evaluation
  - Persisted to ledger (fact/decision tables need column)
  - **Do not** create a separate Assertion type — `GroundedClaim` already carries
    provenance, confidence, evidence, status. Adding commit_level completes it.
  - Spec ref: `multi2.md` §6.1

- [ ] **Add `assumptions` field to `GroundedClaim`** — `epistemic.py`
  - `assumptions: list[str]` — explicit ungrounded dependencies
  - Populated when claim depends on SOFT/unverified premises
  - Surfaced in CLI and audit output
  - Spec ref: `multi2.md` §1.1

### Layer 3: Evidence Type Validation (enforcement — gates on Layer 1 data)

- [ ] **Evidence kind requirements per claim type** — `audit.py` / `quorum.py`
  - MATH claims require CALC_RESULT evidence
  - CODE claims require TEST_RESULT evidence
  - STATIC_FACT claims require WEB_SOURCE or DOCUMENT evidence
  - VOLATILE_FACT claims require live retrieval evidence
  - Enforce before STABILIZING transition in quorum
  - Wire into `PolicyStore` (already has claim-type policies)
  - Spec ref: `regime.md` §5.1, `multi2.md` §5.1

### Layer 4: Premise Rule & Dependency Tracking

- [ ] **Premise rule enforcement** — `epistemic.py` or `quorum.py`
  - SOFT/STALE claims cannot serve as premises for HARD claims
  - If a HARD claim's dependency is SOFT → downgrade to SOFT or block
  - Requires dependency graph (which claims depend on which)
  - Can use `BeliefGraph` from `direction.py` (REQUIRES/IMPLIES edges) — don't rebuild
  - Spec ref: `multi2.md` §6.2

- [ ] **Dependency invalidation cascade** — `audit.py`
  - When POST_COMMIT audit marks claim UNGROUNDED/CONTRADICTED:
    force dependent HARD claims to re-enter review
  - Traverse dependency edges, downgrade or flag
  - Log cascade events for audit trail
  - Spec ref: `regime.md` §6.2

### Layer 5: Roles & Scheduling (higher-level policy)

- [ ] **Agent role assignment** — `quorum.py` or new thin layer
  - Roles: proposer, retriever, falsifier, synthesizer
  - Per-proposal role tracking (which agent filled which role)
  - Policy: HIGH-risk claims require at least one falsifier attempt
  - Budget per role (max_tool_calls, max_rounds)
  - Consider whether this extends `Vote` (add role field) vs separate table
  - Spec ref: `multi2.md` §2

- [ ] **Periodic revalidation scheduling** — `ttl.py` integration
  - TTL expiry triggers PERIODIC_REVALIDATION audit automatically
  - Currently: TTLManager has policies and schedules but no automation hook
  - Wire: TTLManager.get_revalidation_schedule() → AuditPipeline.periodic_audit()
  - Spec ref: `regime.md` §2.3

### Layer 6: Claim Status on GroundedClaim (optional — evaluate need)

- [ ] **Claim-level status field** — evaluate before building
  - multi2.md spec wants: PROPOSED → IN_REVIEW → STABILIZING → COMMITTED → STALE
  - QuorumState already tracks proposal lifecycle (9 states)
  - Question: is claim-level status redundant with quorum status?
  - If claims can exist outside quorum (single-agent mode), they need their own status
  - If quorum is always the authority, claim status = projection of quorum state
  - **Decision needed**: separate FSM or derived view?

---

## Unfinished Work: Nonfiction CFI (Separate Workstream)

From `ingest/next2.md`. This is the nonfiction analogue of fiction's DSI/context-drift
detection. The spec explicitly warns: **do not delegate value choices to code**.
Human authority needed for definitions, thresholds, and hard/soft classification.

- [ ] **Frame taxonomy** — human-authored, not generated
  - Define nonfiction frames: foundational, theoretical, applied, controversial,
    pedagogical, etc.
  - These are the bins. Whoever defines the bins defines the system behavior.
  - This is product philosophy, not engineering.

- [ ] **Contextual Frame Intrusion (CFI) detector** — `nonfiction_governor/`
  - Nonfiction analogue of fiction DSI
  - Detect when model introduces frames not demanded by the text
  - Examples: uninvited "capitalism", "trauma", "experts say", "both sides"
  - Same architecture as fiction context_drift.py: hysteresis, risk tiers, transition validation

- [ ] **Nonfiction state vector** — `[D_t, F_t, E_t, P_t, N_t]`
  - Domain, active frames, evidentiary grounding, perspective, narrative load
  - Most nonfiction bugs are unconstrained drift in F_t or P_t

- [ ] **Nonfiction hard constraints**
  - Epistemic mismatch: don't answer normative as descriptive (or vice versa) unless asked
  - Δt violations: no confident claims about time-sensitive facts without retrieval
  - Scope violations: don't generalize case → population unless asked

- [ ] **Nonfiction soft penalties**
  - Frame overuse (uninvited interpretive frames)
  - Moral coloration when mechanism was asked for
  - "Both sides" balancing when no dispute was specified
  - Excess metaphor/narrative when precision was requested

---

## Cross-Cutting (Deferred)

- [ ] **Web UI** - Dashboard showing claim history, rejection rates, regime status
- [ ] **VS Code Integration** - Governor support in VS Code (spec: `ingest/vscode.md`)
- [ ] **Telemetry dashboard** - Real-time regime visualization
- [ ] **Minor: CLI bug** - `src/governor/cli.py` line 7388: `bank.seed_defaults()` doesn't exist on PhraseBank
- [ ] **Minor: Profile boil presets** - `profiles.py` references DARJEELING/CHAI which don't exist in ControlMode enum
