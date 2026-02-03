# CLAUDE.md - Instructions for Claude Code

## Project Overview

This is the **Agent Governor** - a constraint system for agentic coding tools. The core principle: **Language is a proposal, not an authority (NLAI)**.

**Status: Phase 1-3 COMPLETE** - All 14 steps from BUILD_SPEC.md implemented.
**Multi-Agent v2**: SQLite backend, leases, epochs, permissions, dispatcher protocol.
**Epistemic Governance**: Provenance tracking, confidence modeling, dangerous claim detection.
**Regime Detection**: Operational health monitoring (ELASTIC/WARM/DUCTILE/UNSTABLE).
**Boil Control**: Named presets (GREEN_TEA → BOIL), dwell time enforcement, tripwires.
**Jurisdictions**: Context-aware governance (FACTUAL, SPECULATIVE, ADVERSARIAL, etc.).
**Security Verifier**: Secret detection, SQL/command injection, XSS, path traversal.
**Watch Mode**: Continuous file monitoring with automatic security scanning.
**Claude Code Hooks**: Integration with Claude CLI via pre/post tool hooks.
**Direction Tracking**: Commitments, anchors, Δt measurement, belief graph triangulation.
**Fiction Governor**: Plot threads, scene proposals, prompt generation, narrative constraints, manuscript scanning, similarity matching, context drift detection, fiction guardrails (consent tracking, DSI, AII).
**Non-Fiction Governor**: Corpus management, DOI fetching, citation verification, CFI v0 (contextual frame intrusion detection, 12-frame taxonomy, perspective tracking, normative creep, scope violations).
**Multi-Agent Routing**: Task complexity estimation, model tiers, adaptive routing.
**Failure Provenance**: Scars (constraint hysteresis), shields (input gating), surprise ratio classification.
**Grounding Audit**: Closed-loop hallucination detection, failure mode taxonomy, adaptive policy thresholds.
**Ultrastability**: Ashby-style S₁ adaptation, bounded parameters, pathology detection, freeze/unfreeze.
**Homeostat**: Exploration budgets, adaptive gain scheduling, domain-specific setpoints, 7 exploration contexts.
**Coupling**: Homeostat→Ultrastability one-way protocol, TuningIntent gate, S₁ bounds enforcement, deadband, accumulator, freeze feedback.
**Strict Mode**: Fail-closed governance preset, claim categories, risk-adjusted requirements, commit levels.
**Drift Detection**: Temporal asymmetry defense, premise quarantine, attention skew, coherence gradient.
**Ops Governor**: Runbook verification, time window enforcement, blast radius limits, precondition chains.
**Claim Diff**: Epistemic state change detection, confidence drift, provenance laundering, evidence erosion, silent retraction.
**Claim Signals**: Implicit claim extraction from text, date/entity/quantity/assertive detection, assertiveness scoring, ledger integration.
**Config Profiles**: Named governance presets (strict, permissive, research, production, audit, research_mode), custom profiles, one-command switching.
**Dissent Ledger**: Contradiction persistence, first-class objections, commit gating, confidence trajectories.
**TTL Enforcement**: Recency decay, volatility classes (PERMANENT→EPHEMERAL), revalidation scheduling.
**Quorum State Machine**: Multi-agent consensus protocol, Δt stability windows, claim-type policies, dissent/TTL integration, risk levels, fingerprint gating, escalation/resolution states.
**Cooperative Redundancy**: Independence scoring, method signatures, Jaccard similarity, anti-cheat (source URL overlap), quorum integration.
**Semantic Variety**: Post-commit text transform, phrase bank with meaning tags, cooldown tracking, semantic diff guard, no-rewrite zones, burst repetition detection.
**Auto-Tuning**: Threshold learning from signal distributions, reset effectiveness tracking, setpoint calibration from baselines, budget sweep with Pareto analysis.
**Puppet Mode**: Persona pinning, voice constraints, epistemic posture, semantic diff guard (7 rules + 2 warnings), answer skeleton, 3 builtin profiles, registry.
**Tainted Claim Similarity**: Token-set Jaccard fingerprinting, inverted index candidate retrieval, exact/near-duplicate detection, audit events, configurable thresholds.
**Context Drift Detection**: Narrative mode tracking with hysteresis, genre escalation gating, register shift detection, mode chatter warnings.
**Fiction Guardrails**: Consent tracking (pairwise, scoped), DSI detection, AII with validity profiles, hard constraints (C1-C3), soft penalties (P1-P4).
**Sybil Resistance**: Bloc detection, effective voter count (Neff), per-origin budget coupling, quorum Gate 5 integration, escalation triggers.
**Research Mode**: Non-convergent epistemic control, hypothesis lifecycle (PROBE→TENTATIVE→SUPPORTED→ABANDONED), entropy bounds, dominance caps, evidence impulses with decay, Δt invariant, terminal states.
**ClaimStatus + Epistemic Persistence**: ClaimStatus enum (PROPOSED→SUPPORTED→CONTESTED→…), QuorumStatus mapping, EpistemicLedger SQLite persistence (Schema V4), write-through on mutations, from_dict/from_json deserialization.
**Evidence Type Validation**: Layer 3 evidence kind gating, 4 new EvidenceType values (CALC_RESULT, TEST_RESULT, WEB_SOURCE, LIVE_RETRIEVAL), WRONG_EVIDENCE_TYPE audit failure mode, required_evidence_kinds on PolicyEntry, quorum Gate 6, COLLECTING→STABILIZING evidence gate.
**Premise Rule & Dependencies**: Layer 4 dependency tracking, `depends_on` field on GroundedClaim, cycle-checked DAG, premise rule (HARD claims cannot depend on SOFT/STALE/INVALIDATED), BFS invalidation cascade (HARD→SOFT downgrade), CascadeEvent audit trail, Schema V5, quorum Gate 7.
**Agent Roles & Revalidation**: Layer 5 agent role assignment (PROPOSER/RETRIEVER/FALSIFIER/SYNTHESIZER), role budgets per risk level, quorum Gate 8, periodic revalidation orchestrator wiring TTL→AuditPipeline.
**ClaimStatus FSM Enforcement**: Layer 6 transition table (PROPOSED→SUPPORTED↔CONTESTED→{INVALIDATED|EXPIRED|REFUSED}), 9 TransitionReasons, guard validation, transition history, cascade SUPPORTED→STALE, terminal state HUMAN-only recovery.
**Tone Profiling**: ToneProfile dataclass (28 dimensions), text analysis, ToneChecker with violation detection, tone guidance generation for system prompts, ToneManager persistence, corpus analysis (extract_tone_profile), profile comparison (compare_profiles, ProfileDeviation), CLI commands.
**Autonomous Execution (A1-A4)**: Spine (locked project structure), SpineManager, InvariantType/Invariant/InvariantSet/InvariantLibrary (mechanically verifiable rules), ExecutionBudget/ExecutionUsage/ExecutionState (resource tracking), SessionManager (multi-session persistence), AutonomousExecutor (step-function loop with spine+invariant enforcement, budget checking, checkpointing, resume), Spine CLI (lock/unlock/list/show/activate/check), Session CLI (list/show/delete/handoff), Governor adapters (security, CFI, fiction, nonfiction citation, tone, generic content → Invariant).
**Invariant Store (Deferred 1)**: InvariantSpec (serializable invariant definitions), InvariantStore (file-per-item persistence), VALID_KINDS (6 factory mappings), materialization to live Invariant objects, CLI (add/list/show/remove/check), autonomous run command (noop step execution shell).
**Strategic Test Suites**: Golden-file tests (JSON schema locking for all serialized types), no-laundering regression tests (structural integrity invariants), failure-injection tests (executor fault tolerance), property-based invariant tests (combinatoric fuzzing), contract tests for adapters (interface locking).
**Web UI (Deferred 2, W1-W3)**: GovernorContextManager (isolated per-user/project contexts), ChatBridge (Anthropic/Ollama backend abstraction), GovernorHooks (mode-specific system prompts), refactored FastAPI adapter (OpenAI-compatible API with governor endpoints), Docker multi-user deployment (Erin fiction + James code stacks).
**Structured Telemetry (Deferred 4, B2)**: TelemetryCollector (pluggable backends, fail-safe), StructuredLogger (JSONL, date-partitioned, size/retention rotation), TelemetryEvent with typed field helpers, cost/performance/convergence analysis, CSV/JSON export, CLI (enable/disable/status/logs/analyze/export/rotate-logs), executor integration. Convergence telemetry: CONTINUITY_TRACE/CONTINUITY_RESULT events, ConvergenceExecutor + one-shot gate instrumentation, ConvergenceReport (acceptance rate, efficiency, monotone/oscillation rates, windup, per-anchor stats, interference graph).
**Continuity Enforcement (Deferred 5)**: Closed-loop generation control. AnchorRegistry (semantic constraint setpoints), ContinuityChecker (lexical deviation measurement), CorrectionLadder (escalating interventions), ConvergenceExecutor (iterate-until-convergence with budget enforcement, telemetry instrumented), GenerationProvider Protocol, adapter integration, CLI (anchor CRUD, check, import). Continuity Bridges: mode-specific anchor factories (fiction bible, nonfiction corpus, puppet profile), GovernorHooks integration (one-shot gating with telemetry, system prompt enrichment).
**Convergence Auto-Tuning (Deferred 6)**: Offline system identification over convergence traces. ConvergenceAnalyzer (per-anchor decomposition, action effectiveness matrices, deadzone detection, interference tracking, opportunity identification). TuningProposal artifacts (28 dataclass types, HardGuards forced-True, Approval forced-requires_human). ProposalStore (file-per-item JSON persistence). 5 admissibility checks (regime match, strength non-regression, objective constraints, trial requirements, determinism hygiene). ConvergenceTuner orchestrator (propose/apply/rollback). 10 footgun guardrails. CLI (governor tune convergence {status,propose,apply,rollback,proposals,show}).
**VS Code Extension (Deferred 3, Phase V1)**: Unified check aggregation (check.py: Position, Range, CheckFinding, CheckResult, run_check). CLI `governor check` command (file/stdin, JSON/text output, security/continuity toggles). TypeScript VS Code extension (vscode-governor/: CLI client wrapper, diagnostic provider, Check File/Check Selection commands, status bar, on-save handler).
**VS Code Extension (Deferred 3, Phase V2)**: TreeView side panel. `governor state --json` aggregation command, `--json` flags on 7 existing commands (status, facts, decisions, task list, regime status, boil status, autonomous list). GovernorTreeProvider (activity bar, state tree with regime/boil/proposals/decisions/facts/tasks/autonomous, refresh command, click-to-detail). GovernorState TypeScript types, generic CLI runner refactor, fetchState client method.
**VS Code Extension (Deferred 3, Phase V2-3)**: GovernorViewModel canonical schema v2. 8 top-level sections: Session, Regime, Decisions, Claims, Evidence, Violations, Execution, Stability. Read-only derivation from existing subsystems. `--schema v1|v2` backward compat on `governor state --json`. V2 TypeScript types (GovernorViewModelV2), TreeView rewrite with claim/decision/violation/evidence builders, icon mappings for claim states and violation severities.
**Telemetry Dashboard**: Rich TUI for real-time regime visualization. Phase space plot (λ arrival vs μ resolution), regime gauge (ELASTIC→UNSTABLE), energy sparkline, event log, budget panel. Live mode (reads from telemetry logs), replay mode (trace playback), demo mode. CLI (governor dashboard {live,replay,demo,stats}).
**Prometheus Metrics**: Optional Prometheus metrics export at /metrics. Counters (proposals, verifications, llm_calls, tokens, cost, errors, claims, security_scans, continuity_checks, regime_transitions), histograms (verification_duration, llm_call_duration, continuity_iterations, complexity_score), gauges (regime, stress, budget_spent/remaining, active_sessions, open_proposals, anchors). TelemetryCollector backend integration. CLI (governor prometheus {enable,disable,status,metrics}).
**Maude Lite**: Evidence-gated coding harness — kernel-only surface. HARD claims require evidence, contradictions persist, failures are loud. Custody scoring (Ap accountability, Ip invariant coupling, Fp failure explicitness). Claim extraction (HARD/SOFT patterns), evidence linking, contradiction detection, exit shape checking. Status codes (OK/WARN/BLOCKED). Agent wrapper integration, JSONL logging. CLI (governor lite {check,validate,config,score,extract}).
**W5 Writing Modules (Deferred 2, W5)**: Spec application from fic.md, nonfic.md, anc.md, tone.md, writingconstraints.md. writing_patterns.py (18 pattern banks), writing_governance.py (GovernanceVisibilityScorer, GovernanceLeakDetector, SmoothingSuppressor, ExitShapeChecker), writing_tone.py (ToneVector 6D, ToneEnvelope, 16 regime envelopes, ToneCollision, ToneStabilityController), writing_regime.py (AffectRegime, RegimeVector, RegimeHysteresis, RpScorer, TragedyConstraints), writing_nonfiction.py (NfClaimLevel, PromotionGate, VelocityController, EpScorer, ReScorer, HedgeCalibrator, AhScorer, NleadChecker), writing_intent.py (IntentClassifier, 12 ancillary regime scorers, RegimeCollision), writing_constraints.py (11 structural constraints + Section 14 causal narration resistance), writing_ticketing.py (14 prose + 11 code ticket types, recurrence, routing), writing_puppet.py (extended puppet constraints), writing_code.py (code-specific constraints), writing_router.py (writing-aware routing). 922 tests.
**VS Code Extension (Deferred 3, Phase V4)**: Hover tooltips (GovernorHoverProvider — decision/claim/violation context on hover), code actions (GovernorCodeActionProvider — quick fixes, suppress comments, security actions), real-time checking (RealtimeChecker — debounced on-type, configurable delay). New commands: Toggle Realtime, Check Now. Keybindings: Ctrl+Shift+G (check file), Ctrl+Shift+Alt+G (toggle realtime). 36 new TypeScript tests.
**Interactive Violation Resolution (Deferred 2, W4)**: Erin-ready chat. Blocking violations present 3 choices: fix (rewrite compliant), revise (update anchor), proceed (log exception). State machine (PENDING_RESOLUTION→FIX/REVISE/PROCEED→NORMAL). ViolationResolver with persistent pending state. Resolution command detection (1/2/3, maude fix/revise/proceed). Mode-specific choices (fiction: canon, code: decisions). Exception logging with scope/expiry. ChatBridge check_response_blocking(), ViolationPendingResponse. Adapter integration with resolution handling. CLI (governor lite {pending,fix,revise,proceed,exceptions}). Main CLI integration: `governor check --interactive`, `governor wrap --check-continuity --interactive`, `governor hook pre-commit --check-continuity --interactive`.
**Total: 7144 tests**

## Key Documents

- `BUILD_SPEC.md` - Step-by-step build guide, receipt types, claim types, FSM
- `MULTI_AGENT.md` - Concurrency model, conflict detection, permissions, dispatcher protocol
- `TODO.md` - Future enhancements

## Quick Start

```bash
# Install in dev mode
pip install -e .

# Initialize governor in a project
governor init

# Run tests
pytest tests/ -v
```

## CLI Commands

```bash
# Core workflow
governor init                    # Initialize .governor/ directory
governor propose --claim "..."   # Create proposal with claims
governor verify <id>             # Verify proposal, produce receipts
governor apply <id>              # Apply verified proposal

# Query state
governor facts                   # List recorded facts (--json)
governor decisions               # List recorded decisions (--json)
governor status                  # Show proposal statuses (--json)
governor state --json            # Aggregated state as JSON (schema v2 default)
governor state --json --schema v1  # Legacy v1 format (proposals/facts/decisions/tasks/regime/boil/autonomous)
governor state --json --schema v2  # Canonical ViewModel (session/regime/decisions/claims/evidence/violations/execution/stability)
governor rejections              # Show rejection history

# Configuration
governor envelope                # Get/set operating mode (strict/exploratory)
governor decay                   # Check for stale facts

# Integration
governor hook install            # Install git pre-commit hook
governor hook status             # Check hook status
governor hook pre-commit         # Run pre-commit check (called by git hook)
governor hook pre-commit --check-continuity  # Also check staged files for violations
governor hook pre-commit -c -i   # Interactive mode: offer fix/revise/proceed
governor wrap -- <cmd>           # Wrap agent command with enforcement
governor wrap --auto-approve -- <cmd>  # Auto-approve in exploratory mode
governor wrap --check-continuity -- <cmd>  # Check file changes for violations
governor wrap -c -i -- <cmd>     # Interactive mode: offer fix/revise/proceed
governor changes                 # Show file approval status

# MCP Server
governor mcp serve               # Run MCP server for Claude integration
governor mcp tools               # List available MCP tools
governor mcp call <tool>         # Test MCP tools directly

# Multi-Agent Dispatcher Protocol (v2)
governor init --v2               # Initialize with SQLite backend
governor agent register --id X   # Register agent with governor
governor agent list              # List registered agents
governor agent permissions X     # Show permissions for agent
governor agent heartbeat --id X  # Keep agent registration active
governor task claim --agent-id X --task "..." --scope "..."  # Claim task
governor task heartbeat --agent-id X --task-id Y             # Extend task
governor task complete --agent-id X --task-id Y              # Complete task
governor task list               # List tasks/reservations (--json)
governor task cancel --agent-id X --task-id Y                # Cancel task

# Epistemic Governance (provenance, confidence, evidence)
governor epistemic status                                    # Show ledger status
governor epistemic claims                                    # List grounded claims
governor epistemic dangerous                                 # List dangerous claims (high confidence, no evidence)
governor epistemic create "claim" --provenance assumed       # Create a claim
governor epistemic evidence <id> --type tool_trace -l X -s Y # Attach evidence

# Regime Detection (operational health monitoring)
governor regime status                # Show current regime and signals (--json)
governor regime history               # Show regime transition history
governor regime signals               # Show current signal values
governor regime update --tool-gain X  # Update signals and check regime
governor regime thresholds            # Show detection thresholds
governor regime reset --confirm       # Reset to default ELASTIC state

# Boil Control (named presets with dwell time)
governor boil status                  # Show current mode, regime, dwell state (--json)
governor boil set <mode>              # Change preset (green_tea, oolong, boil, etc.)
governor boil presets                 # List all presets with parameters
governor boil events                  # Show recent boil control events
governor boil process --tool-gain X   # Process a turn with given signals
governor boil reset --confirm         # Reset to default OOLONG mode

# Jurisdictions (context-aware governance)
governor jurisdiction status          # Show current jurisdiction and budget
governor jurisdiction list            # List all available jurisdictions
governor jurisdiction set <name>      # Switch to jurisdiction (factual, speculative, etc.)
governor jurisdiction info <name>     # Detailed info about a jurisdiction
governor jurisdiction tick            # Advance turn, refill budget
governor jurisdiction claim           # Make a claim (consumes budget)
governor jurisdiction export          # Export claim to factual jurisdiction
governor jurisdiction reset --confirm # Reset to default FACTUAL jurisdiction

governor epistemic promote <id> retrieved                    # Promote provenance
governor epistemic retract <id>                              # Retract a claim
governor epistemic decay                                     # Decay ungrounded confidence

# Security Verifier (vulnerability detection)
governor security scan <path>         # Scan file or directory for vulnerabilities
governor security diff                # Scan staged git changes

# Watch Mode (continuous monitoring)
governor watch start                  # Start watching current directory
governor watch check                  # Check for changes once

# Claude Code Hooks (Claude CLI integration)
governor claude-hooks install         # Install hook scripts
governor claude-hooks uninstall       # Remove hook scripts
governor claude-hooks status          # Check hook installation status
governor claude-hooks approve <file>  # Add file to approved list
governor claude-hooks block <cmd>     # Add command to blocked list

# Multi-Agent Routing (task sizing and model selection)
governor routing status               # Show routing config and model registry
governor routing models               # List registered models
governor routing estimate "task"      # Estimate complexity and recommended tier
governor routing route "task"         # Route task to model
governor routing register <name>      # Register custom model
governor routing available <name>     # Set model availability

# Failure Provenance & Scars (constraint hysteresis)
governor scar list                    # List all scars (action restrictions)
governor scar list --hard             # Show only hard scars (full veto)
governor scar shields                 # List active shields (input gating)
governor scar history                 # Show failure history with provenance
governor scar stats                   # Scar/shield statistics and system health
governor scar record <region>         # Record a failure event
governor scar anneal --region <r>     # Record evidence and relax stiffness
governor scar check <region>          # Check if action is admissible

# Grounding Audit Pipeline (hallucination detection)
governor audit run <assertion_id>     # Run grounding audit on assertion
governor audit history                # Show recent audit history
governor audit history --problematic  # Show only problematic audits
governor audit policy                 # Show current policy thresholds
governor audit stats                  # Show pipeline statistics
governor audit adapt                  # Run adaptive threshold tuning
governor audit rates                  # Show failure mode rates

# Ultrastability (S₁ adaptive control)
governor adapt status                 # Show ultrastability state
governor adapt params                 # Show S₁ regulatory parameters
governor adapt history                # Show adaptation history
governor adapt consider               # Observe epoch and consider adaptation
governor adapt consider --apply       # Observe, consider, and apply if ADAPT
governor adapt unfreeze "reason"      # Unfreeze after human review
governor adapt metrics                # Show adaptation metrics

# Homeostat (exploration budgets, adaptive gain scheduling)
governor explore status               # Show homeostat state (mode, context, budget, urgency)
governor explore enter <context>      # Enter exploration context (research, brainstorm, etc.)
governor explore exit                 # Return to standard context
governor explore budget               # Show exploration budget status
governor explore profiles             # List all exploration profiles
governor explore observe              # Observe vitals and compute tuning deltas
governor vitals                       # Show current vitals and setpoint deviations

# Strict Programmer Mode (fail-closed governance)
governor strict status                # Show gate status and statistics
governor strict evaluate <category>   # Evaluate a claim under strict mode
governor strict requirements <cat>    # Show requirements for a claim category
governor strict history               # Show recent evaluation history
governor strict reset --confirm       # Reset evaluation history

# Drift Detection (temporal asymmetry defense)
governor drift status                # Show detector status and alert level
governor drift update                # Compute signals and update alert level
governor drift record "claim"        # Record an assertion for drift tracking
governor drift quarantined           # List quarantined premises
governor drift agents                # Show agent activity tracking
governor drift history               # Show alert transition history
governor drift tick                  # Advance turn counter
governor drift reset --confirm       # Reset drift detector state

# Claim Diff (epistemic state change detection)
governor claim-diff status            # Show diff tracking state, violation counts
governor claim-diff snapshot          # Take snapshot of current epistemic ledger
governor claim-diff run               # Diff current ledger vs last snapshot
governor claim-diff violations        # List violations (--all, --type filter)
governor claim-diff history           # Show diff history
governor claim-diff trend             # Show trend analysis
governor claim-diff laundering        # Shortcut: run + show only laundering
governor claim-diff reset --confirm   # Clear history and snapshots

# Claim Signal Extraction (implicit claim detection)
governor signals extract <text>       # Extract signals from provided text
governor signals scan <path>          # Scan a file for claim signals
governor signals register <text>      # Extract signals AND register as ASSUMED claims
governor signals score <text>         # Show assertiveness score only

# Config Profiles (named governance presets)
governor profile list                 # List available profiles (builtin + custom)
governor profile use <name>           # Activate profile and apply settings
governor profile status               # Show active profile
governor profile off                  # Deactivate current profile
governor profile create <name>        # Create custom profile
governor profile delete <name>        # Delete custom profile

# Quorum State Machine (multi-agent consensus)
governor quorum status <proposal_id>  # Show quorum state for a proposal
governor quorum vote <proposal_id>    # Cast a vote on a proposal
governor quorum policy <claim_type>   # Show policy for a claim type
governor quorum policies              # List all quorum policies
governor quorum history               # Show recent quorum activity

# Independence Scoring (cooperative redundancy)
governor independence score <id>      # Score independence of votes on a proposal
governor independence check <id>      # Check if proposal meets independence threshold

# Semantic Variety (post-commit text transform)
governor semvar transform <text>      # Transform text with variety substitutions
governor semvar phrases               # List phrases in the phrase bank
governor semvar config                # Show semantic variety configuration

# Auto-Tuning (threshold learning, reset tracking, calibration, sweep)
governor tune status                           # Show tuning state
governor tune thresholds --analyze             # Report threshold suggestions
governor tune thresholds --apply               # Apply confident suggestions
governor tune resets --report                  # Reset effectiveness stats
governor tune resets --pending                 # Show pending reset tracking
governor tune calibrate --begin-baseline       # Start baseline collection
governor tune calibrate --end-baseline         # End baseline, compute profile
governor tune calibrate --run                  # Compute calibrated setpoints
governor tune budget --parameter <name>        # Show sweep results
governor tune reset --confirm                  # Clear all tuning state

# Convergence Auto-Tuning (offline system identification + proposal engine)
governor tune convergence status              # Store state: counts by proposal status
governor tune convergence propose             # Generate proposals from telemetry
    --window 30d --mode fiction --namespace fiction
governor tune convergence apply <proposal_id> # Apply with admissibility checks
    --by <user>
governor tune convergence rollback <trial_id> # Mark trial as rolled back
governor tune convergence proposals           # List proposals (--status filter)
governor tune convergence show <proposal_id>  # Show proposal details (--json)

# Tainted Claim Similarity (recurrence detection)
governor taint status                   # Show taint index stats
governor taint list                     # List tainted claims
governor taint add <id> <text>          # Add claim to taint index
governor taint remove <id>              # Remove claim from taint index
governor taint check <text>             # Check text against taint index
governor taint events                   # Show taint similarity events
governor taint events --clear           # Show and clear events
governor taint reset --confirm          # Clear taint index

# Puppet Mode (persona pinning, semantic safety)
governor puppet list                    # List available puppet profiles
governor puppet show <puppet_id>        # Show profile details
governor puppet activate <puppet_id>    # Activate a puppet
governor puppet deactivate              # Deactivate current puppet
governor puppet status                  # Show active puppet status
governor puppet create <puppet_id>      # Create custom profile (from JSON stdin or --file)
governor puppet delete <puppet_id>      # Delete custom profile
governor puppet test <puppet_id>        # Test profile with sample text
governor puppet render <text>           # Render text through active puppet

# Spine Management (Phase A2: project structure locking)
governor spine lock <id> [-rf file] [-rd dir] [--forbid pattern]  # Lock a spine
governor spine unlock <id> --confirm    # Unlock (remove) a spine
governor spine list                     # List all locked spines
governor spine show <id>                # Show spine details
governor spine activate <id>            # Set spine as active constraint
governor spine deactivate               # Deactivate current spine
governor spine check [-m file] [-c file] [-d file]  # Check proposal against active spine

# Invariant Management (Deferred 1: persistent invariant specs)
governor invariant add <kind>           # Add invariant (test, file-exists, dir-exists, forbidden, no-secrets, max-file-size)
governor invariant list                 # List all invariant specs
governor invariant show <id>            # Show invariant spec details
governor invariant remove <id>          # Remove an invariant spec
governor invariant check [--id X]       # Run invariant checks (all or specific)

# Autonomous Execution Sessions (Phase A3: session lifecycle)
governor autonomous list [--active]     # List execution sessions (--json)
governor autonomous show <id>           # Show session details
governor autonomous delete <id> --confirm  # Delete a session
governor autonomous handoff <id>        # Show handoff summary for human review
governor autonomous run --task "..."    # Run execution session (noop step, --budget, --spine-id, --dry-run)

# Structured Telemetry (Deferred 4, B2)
governor telemetry enable              # Enable telemetry, create config + logs dir (--logging/--no-logging, --retention-days, --redact-prompts, --redact-contents)
governor telemetry disable             # Disable logging (preserves existing logs)
governor telemetry status              # Show config + log statistics
governor telemetry logs                # Query events (--last N, --type, --level, --since, --json)
governor telemetry analyze costs       # Cost breakdown by model/operation (--since, --json)
governor telemetry analyze performance # Verification latency percentiles, approval rate (--since, --json)
governor telemetry analyze convergence # Convergence loop stats: acceptance rate, efficiency, oscillation, per-anchor (--since, --json)
governor telemetry export              # Export events (--format csv|json, --output, --since, --type)
governor telemetry rotate-logs         # Delete old logs (--dry-run)

# Telemetry Dashboard (real-time visualization)
governor dashboard live                # Live dashboard (reads from telemetry logs, --refresh)
governor dashboard replay <path>       # Replay trace file through dashboard (--speed)
governor dashboard demo                # Generate and play demo trace (--speed)
governor dashboard stats <path>        # Print trace file statistics

# Prometheus Metrics (optional, requires prometheus-client)
governor prometheus enable             # Enable metrics, start server (--port 9090)
governor prometheus disable            # Disable metrics server
governor prometheus status             # Show config and server status
governor prometheus metrics            # Print current metrics in Prometheus text format

# Maude Lite (evidence-gated coding harness)
governor lite check <text>       # Check agent output against kernel constraints
governor lite check --stdin      # Read from stdin
governor lite check -f <file>    # Read from file (--strict/--permissive, --format json)
governor lite validate <path>    # Validate file contents
governor lite config             # Show configuration and kernel constraints
governor lite score <text>       # Score custody metrics (Ap, Ip, Fp)
governor lite extract <text>     # Extract claims from content
governor lite pending            # Show pending violation requiring resolution (--format json)
governor lite fix                # Resolve pending violation by fixing the response
governor lite revise             # Resolve pending violation by updating the anchor
governor lite proceed            # Resolve pending violation by logging an exception (--scope, --expiry)
governor lite exceptions         # List logged exceptions (--format json)

# Continuity Enforcement (Deferred 5: closed-loop generation control)
governor continuity status              # Registry stats, anchor count by type
governor continuity anchor add          # --id, --type, --description, --required, --forbidden, --severity
governor continuity anchor list         # All anchors with type and severity
governor continuity anchor show <id>    # Full anchor details (JSON)
governor continuity anchor remove <id>  # Remove anchor
governor continuity check <text>        # Check text against all anchors, show report
governor continuity import <path>       # Import anchors from JSON file

# Unified Check (VS Code extension integration)
governor check <path>                  # Check a file for security + continuity issues
governor check <path> --format json    # JSON output for tooling
governor check --stdin --format json   # Read from stdin (JSON or plain text)
governor check <path> --no-security    # Skip security scanning
governor check <path> --no-continuity  # Skip continuity checking
governor check <path> --interactive    # Interactive mode: offer fix/revise/proceed on errors
governor check <path> -i --mode fiction  # Interactive with fiction-mode resolution options

# Fiction Governor - Context Drift Detection
fiction-gov drift status               # Show drift detector state
fiction-gov drift classify <text>      # Classify text register/mode
fiction-gov drift set <mode>           # Force narrative mode
fiction-gov drift check <text>         # Check text for drift
fiction-gov drift reset --confirm      # Reset drift detector

# Fiction Governor - Guardrails (consent, DSI, AII)
fiction-gov guardrails check <text>    # Check text against all guardrails
fiction-gov guardrails consent <a> <b> <scope> <level>  # Update consent state
fiction-gov guardrails profiles        # List validity profiles
fiction-gov guardrails dsi <text>      # Check text for DSI
fiction-gov guardrails aii <text>      # Check text for AII
fiction-gov guardrails config          # Show guardrail config
```

## Architecture Rules (Non-Negotiable)

1. **NLAI: Language is a proposal, not an authority.**
   - Agents provide *pointers* (file paths, commands to run)
   - Governor produces *receipts* (hashed proof of verification)
   - Never trust agent-provided "evidence"

2. **Gate, not memory.**
   - The goal is write-blocking, not advisory logging
   - No file mutations without verified proposals
   - Pre-commit hook enforces this

3. **Two ledgers: facts vs decisions.**
   - `facts/` = empirical, auto-decays when files change
   - `decisions/` = normative, persists until explicitly revised
   - "Tests pass" is a fact. "We use React" is a decision.

4. **Typed claims, not prose.**
   - Claims are structured: `ClaimType.FILE_EXISTS`, `ClaimType.TESTS_PASS`, etc.
   - No free-form string assertions
   - If the claim type doesn't exist, add it to the enum first

5. **Agents don't talk to each other. They talk to the ledger.**
   - No agent-to-agent messaging
   - No "Mayor" or coordinator agent
   - Ledger is the only shared state
   - Conflicts are structural, not political

6. **Concurrency is transactional.** (see MULTI_AGENT.md)
   - SQLite with WAL mode for concurrent access
   - Leases prevent collision during verification
   - Epochs enable optimistic concurrency
   - No partial commits - atomic or nothing

## File Structure

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

## Implementation Summary

### Phase 1 - The Gate (Core Primitives)
| Step | Module | Description | Tests |
|------|--------|-------------|-------|
| 1 | receipts.py | FileSnapshot, CmdRun, DiffReceipt | 22 |
| 2 | producers.py | Receipt production from real inputs | 32 |
| 3 | claims.py | ClaimType enum, Claim validation | 42 |
| 4 | ledgers.py | FactLedger, DecisionLedger | 35 |
| 5 | fsm.py | State machine with guards | 33 |
| 6 | verifiers.py | Receipt-producing verifiers | 37 |
| 7 | cli.py | Core CLI commands | 25 |

### Phase 2 - Production Hardening
| Step | Feature | Description | Tests |
|------|---------|-------------|-------|
| 8 | Fact decay | Auto-invalidate when files change | 11 |
| 9 | Conflicts | Key-value conflict detection | 12 |
| 10 | Envelopes | exploratory vs strict modes | 15 |
| 11 | Feedback | Machine-readable rejection errors | 18 |

### Phase 3 - Integration
| Step | Feature | Description | Tests |
|------|---------|-------------|-------|
| 12 | Git hooks | Pre-commit enforcement | 33 |
| 13 | Wrapper | Agent file write interception | 29 |
| 14 | MCP server | Claude Desktop integration | 22 |

**Phase 1-3 tests: 381**

### Multi-Agent v2 (SQLite Backend)
| Module | Description | Tests |
|--------|-------------|-------|
| storage.py | SQLite with WAL, leases, epochs | 26 |
| ledgers_v2.py | SQLiteFactLedger, SQLiteDecisionLedger | 29 |
| claims.py | WORK_RESERVATION, INTENT claim types | 13 |
| permissions.py | AgentPermissions, PermissionManager | 27 |
| cli.py | Dispatcher protocol (agent/task commands) | 24 |

**Multi-Agent v2 tests: 119**

### Audit Graph
| Module | Description | Tests |
|--------|-------------|-------|
| graph.py | Node, Edge, AuditGraph, GraphBuilder, Maltego-style transforms | 48 |

**Audit Graph tests: 48**

### Task Management
| Module | Description | Tests |
|--------|-------------|-------|
| tasks.py | Task, TaskManager, priorities, labels, milestones, time tracking, sessions | 63 |

**Task Management tests: 63**

### Epistemic Governance
| Module | Description | Tests |
|--------|-------------|-------|
| epistemic.py | Provenance, confidence, EvidenceRef, EpistemicLedger | 48 |

**Epistemic Governance tests: 48**

### Regime Detection (Health Monitoring)
| Module | Description | Tests |
|--------|-------------|-------|
| regime.py | OperationalRegime, RegimeSignals, RegimeDetector | 42 |

**Regime Detection tests: 42**

### Boil Control (Named Presets)
| Module | Description | Tests |
|--------|-------------|-------|
| boil.py | ControlMode, BoilPreset, BoilController, dwell, tripwires | 40 |

**Boil Control tests: 40**

### Jurisdictions (Context-Aware Governance)
| Module | Description | Tests |
|--------|-------------|-------|
| jurisdictions.py | Jurisdiction, JurisdictionManager, 8 standard jurisdictions | 62 |

**Jurisdictions tests: 62**

### Security, Watch, and Claude Hooks
| Module | Description | Tests |
|--------|-------------|-------|
| security.py | SecurityVerifier, vulnerability patterns, diff scanning | 32 |
| watch.py | FileWatcher, WatchSession, change detection | 18 |
| claude_hooks.py | HookConfig, hook scripts, Claude CLI integration | 26 |

**Security/Watch/Hooks tests: 76**

### Direction Tracking (Landmarks & Orientation)
| Module | Description | Tests |
|--------|-------------|-------|
| direction.py | DirectionLedger, BeliefGraph, Δt, commitments, anchors, trajectory | 57 |

**Direction Tracking tests: 57**

### Multi-Agent Routing
| Module | Description | Tests |
|--------|-------------|-------|
| routing.py | Router, ModelRegistry, ComplexityEstimator, TaskHistory, adaptive routing, RoutingStrategy, BudgetManager, routing explainability | 91 |

**Multi-Agent Routing tests: 91**

### Failure Provenance & Scars
| Module | Description | Tests |
|--------|-------------|-------|
| scars.py | ScarLedger, FailureProvenance, Scar, Shield, surprise ratio, annealing | 89 |

**Failure Provenance tests: 89**

### Grounding Audit Pipeline
| Module | Description | Tests |
|--------|-------------|-------|
| audit.py | AuditPipeline, PolicyStore, DetectionSignals, failure mode taxonomy, adaptive thresholds | 164 |

**Grounding Audit tests: 164**

### Ultrastability (S₁ Adaptive Control)
| Module | Description | Tests |
|--------|-------------|-------|
| ultrastability.py | UltrastabilityController, ParameterSpec, PathologyDetector, bounded S₁ adaptation | 113 |

**Ultrastability tests: 113**

### Homeostat (Exploration Budgets)
| Module | Description | Tests |
|--------|-------------|-------|
| homeostat.py | Homeostat, ExplorationBudget, EpistemicVitals, TuningDelta, adaptive gain scheduling | 114 |

**Homeostat tests: 114**

### Coupling (Homeostat → Ultrastability)
| Module | Description | Tests |
|--------|-------------|-------|
| coupling.py | GovernorCoupling, TuningIntent, IntentOutcome, S₁ bounds enforcement, one-way protocol | 47 |
| coupling (adversarial) | Deadband, accumulator, freeze feedback, deterministic plant sims, convergence/oscillation | 36 |

**Coupling tests: 83**

### Strict Programmer Mode (Fail-Closed Governance)
| Module | Description | Tests |
|--------|-------------|-------|
| strict.py | StrictModeGate, ClaimCategory, CommitLevel, RiskLevel, ClaimRequirement, StrictPolicy, risk adjustment | 99 |

**Strict Mode tests: 99**

### Drift Detection (Temporal Asymmetry Defense)
| Module | Description | Tests |
|--------|-------------|-------|
| drift.py | DriftDetector, PremiseQuarantine, DriftSignals, AgentActivity, temporal coherence, attention skew | 107 |

**Drift Detection tests: 107**

### Ops Governor (SRE/Operations)
| Module | Description | Tests |
|--------|-------------|-------|
| ops_governor/ | RunbookVerifier, TimeWindowVerifier, BlastRadiusVerifier, PreconditionChainVerifier, PolicyRegistry | 58 |

**Ops Governor tests: 58**

### Claim Diff (Epistemic State Change Detection)
| Module | Description | Tests |
|--------|-------------|-------|
| claim_diff.py | ClaimDiffer, ClaimSnapshot, LedgerSnapshot, confidence drift, provenance laundering, evidence erosion, silent retraction | 91 |

**Claim Diff tests: 91**

### Claim Signal Extraction (Implicit Claim Detection)
| Module | Description | Tests |
|--------|-------------|-------|
| claim_signals.py | SignalExtractor, SignalMatch, ExtractionResult, date/entity/quantity/assertive detection, assertiveness scoring, ledger integration | 75 |

**Claim Signal Extraction tests: 75**

### Config Profiles (Named Governance Presets)
| Module | Description | Tests |
|--------|-------------|-------|
| profiles.py | ProfileManager, ProfileSettings, 5 builtins (strict/permissive/research/production/audit), apply_profile | 45 |

**Config Profiles tests: 46**

### Dissent Ledger (Contradiction Persistence)
| Module | Description | Tests |
|--------|-------------|-------|
| dissent.py | DissentLedger, Objection, EvidencePointer, commit gating, confidence trajectories, severity/verdict logic | 59 |

**Dissent Ledger tests: 59**

### TTL Enforcement (Recency Decay)
| Module | Description | Tests |
|--------|-------------|-------|
| ttl.py | TTLManager, VolatilityClass (PERMANENT→EPHEMERAL), TTLPolicy, decay enforcement, revalidation scheduling | 45 |

**TTL Enforcement tests: 45**

### Quorum State Machine (Multi-Agent Consensus)
| Module | Description | Tests |
|--------|-------------|-------|
| quorum.py | QuorumManager, QuorumState, ClaimType (6 types with Δt budgets), VoteVerdict, QuorumStatus (9 states), stability windows, dissent/TTL integration, risk levels, fingerprint gating, escalation/resolution | 119 |

**Quorum State Machine tests: 119**

### Cooperative Redundancy (Independence Scoring)
| Module | Description | Tests |
|--------|-------------|-------|
| independence.py | MethodSignature, IndependenceScorer, pairwise Jaccard similarity, anti-cheat (source URL overlap), quorum integration | 38 |

**Cooperative Redundancy tests: 38**

### Semantic Variety (Post-Commit Text Transform)
| Module | Description | Tests |
|--------|-------------|-------|
| semvar.py | SemVarEngine, PhraseBank (12 seed phrases), CooldownTracker, SemanticDiffGuard, TextInvariants, no-rewrite zones, burst repetition detection | 56 |

**Semantic Variety tests: 56**

### Auto-Tuning (Phase E8)
| Module | Description | Tests |
|--------|-------------|-------|
| auto_tuning.py | ThresholdTuner, ResetTracker, SetpointCalibrator, BudgetSweeper, AutoTuner, Pareto frontier, percentile analysis | 117 |

**Auto-Tuning tests: 117**

### Puppet Mode (Persona Pinning)
| Module | Description | Tests |
|--------|-------------|-------|
| puppet.py | PuppetProfile, PuppetRenderer, PuppetDiffGuard (7 rules + 2 warnings), PuppetRegistry, 3 builtins, AnswerSkeleton, certainty helpers | 128 |

**Puppet Mode tests: 128**

### Tainted Claim Similarity (Recurrence Detection)
| Module | Description | Tests |
|--------|-------------|-------|
| taint.py | TaintIndex, Fingerprint, token-set Jaccard, inverted index candidate retrieval, normalization, audit events | 81 |

**Tainted Claim Similarity tests: 81**

### Fiction Governor (Complete)
| Module | Description | Tests |
|--------|-------------|-------|
| types.py | Character, WorldRule, BannedTrope, CanonEvent, PlotThread, SceneProposal | 20 |
| bible.py | Bible ledger (decisions about story) | 12 |
| canon.py | Canon ledger (facts, threads, proposals) | 30 |
| verifiers.py | In-character, trope, tone, narrative verification | 32 |
| state.py | Character state (motivations, beliefs, constraints) | 18 |
| manuscript.py | Manuscript scanner, character/location/event/thread extraction | 36 |
| similarity.py | TF-IDF similarity, trope detection, voice/tone analysis | 41 |
| context_drift.py | Context drift detection, hysteresis-based mode transitions, genre escalation | 64 |
| guardrails.py | Consent tracking, DSI, AII, hard constraints (C1-C3), soft penalties (P1-P4) | 123 |

**Fiction Governor tests: 376**

### Non-Fiction Governor (Academic Writing)
| Module | Description | Tests |
|--------|-------------|-------|
| types.py | Source, Concept, Position, WritingClaim | 40 |
| corpus.py | Corpus ledger, conflict detection | 26 |
| verifiers.py | Citation, terminology, consistency verification | 25 |
| doi.py | DOI metadata fetching (CrossRef/DataCite) | -- |
| tone.py | ToneProfile (28 dimensions), analyze_text, ToneChecker, ToneViolation, ToneManager, generate_tone_guidance, format_system_prompt, extract_tone_profile (corpus analysis), compare_profiles (ProfileDeviation), CLI (show/create/edit/check/guidance/lock/unlock/delete/ingest/compare) | 122 |
| cfi.py | CFI v0: NonfictionFrame (12 frames), Perspective (4 types), CFIFaultType (4 faults), CFIDetector (classify_frames, classify_perspective, check_scope, check, record, stats), pattern-based detection, frame overuse tracking, normative creep windowed detection, scope violation detection, CLI (check/scan/frames/perspectives) | 68 |

**Non-Fiction Governor tests: 281**

### Sybil Resistance (Bloc Detection, Neff)
| Module | Description | Tests |
|--------|-------------|-------|
| sybil.py | ProvenanceVector, BlocDetector, NeffResult, OriginBudgetTracker, SybilDetector, quorum Gate 5 | 75 |

**Sybil Resistance tests: 75**

### Research Mode (Non-Convergent Epistemic Control)
| Module | Description | Tests |
|--------|-------------|-------|
| research.py | HypothesisState, ResearchConfig, EvidenceImpulse, Hypothesis, EntropyMonitor, DominanceMonitor, TimescaleMonitor, ResearchLedger, TerminalState | 137 |

**Research Mode tests: 137**

### ClaimStatus + Epistemic Persistence (L1/L2 Wiring)
| Module | Description | Tests |
|--------|-------------|-------|
| epistemic.py | ClaimStatus enum, QuorumStatus mapping, epistemic_status field, from_dict/from_json, storage wiring | 40 |
| storage.py | Schema V4 (epistemic_claims + epistemic_ledger_meta), migration | 35 |

**ClaimStatus + Epistemic Persistence tests: 75**

### Evidence Type Validation (Layer 3)
| Module | Description | Tests |
|--------|-------------|-------|
| epistemic.py | 4 new EvidenceType values (CALC_RESULT, TEST_RESULT, WEB_SOURCE, LIVE_RETRIEVAL), 4 factory methods | — |
| audit.py | WRONG_EVIDENCE_TYPE failure mode, required_evidence_kinds on PolicyEntry, default matrix | — |
| quorum.py | required_evidence_types on QuorumPolicy, _check_evidence_types helper, Gate 6 in can_proceed, COLLECTING→STABILIZING gate | — |
| jurisdictions.py | New types in admissible_evidence sets (FACTUAL, SPECULATIVE, ADVERSARIAL, FORENSIC, AUDIT) | — |
| test_evidence_types.py | Enum, factories, policy, audit, quorum, jurisdiction, backward compat | 86 |

**Evidence Type Validation tests: 86**

### Premise Rule & Dependency Tracking (Layer 4)
| Module | Description | Tests |
|--------|-------------|-------|
| epistemic.py | `depends_on` field, CascadeEvent, PremiseCheckResult, add/remove dependency, cycle detection, premise rule check/enforce, invalidation cascade, hooks in retract/block/set_epistemic_status | — |
| storage.py | Schema V5: depends_on_json column, claim_dependencies table, cascade_events table, V4→V5 migration | — |
| quorum.py | Gate 7 (premise rule), epistemic_ledger param on QuorumManager | — |
| test_premise_rules.py | Field, dependency, dependents, premise check, enforce, cascade events, cascade triggers, schema migration, Gate 7, backward compat | 88 |

**Premise Rule & Dependency Tracking tests: 88**

### Agent Roles & Revalidation Scheduling (Layer 5)
| Module | Description | Tests |
|--------|-------------|-------|
| quorum.py | AgentRole enum (PROPOSER/RETRIEVER/FALSIFIER/SYNTHESIZER), RoleBudget dataclass, DEFAULT_ROLE_BUDGETS per RiskLevel, required_roles on QuorumPolicy, agent_role on Vote, role_assignments/roles_filled/missing_roles on QuorumState, Gate 8 (role requirements), HIGH risk auto-adds FALSIFIER | — |
| ttl.py | RevalidationOrchestrator (TTL→AuditPipeline wiring), RevalidationResult, RevalidationRun, _build_signals from epistemic ledger, _update_epistemic_status on audit outcome, create_revalidation_orchestrator convenience | — |
| test_roles_revalidation.py | AgentRole enum, RoleBudget, vote role field, policy roles, state roles, Gate 8, role budgets, revalidation result/run, orchestrator lifecycle, mock audit integration, backward compat | 67 |

**Agent Roles & Revalidation tests: 67**

### ClaimStatus FSM Enforcement (Layer 6)
| Module | Description | Tests |
|--------|-------------|-------|
| epistemic.py | TransitionReason enum (9 values), StatusTransition dataclass, TransitionResult dataclass, VALID_TRANSITIONS table (~25 legal edges), is_valid_transition() validator, transition_epistemic_status() with FSM enforcement, set_epistemic_status() backward-compat wrapper (HUMAN override), transition history tracking, fsm_enforced toggle, block()/retract() wired to epistemic transitions, invalidation cascade SUPPORTED→STALE | — |
| ttl.py | RevalidationOrchestrator updated to use transition_epistemic_status() with proper TransitionReason (TTL_EXPIRY/REVALIDATION) | — |
| test_claim_fsm.py | TransitionReason enum, StatusTransition serialization, TransitionResult, VALID_TRANSITIONS table, is_valid_transition, transition lifecycle, history, FSM toggle, block/retract integration, cascade integration, all valid paths, blocked transitions, backward compat | 106 |

**ClaimStatus FSM Enforcement tests: 106**

### Autonomous Execution (Phase A1-A4: Core Types + Executor + Adapters)
| Module | Description | Tests |
|--------|-------------|-------|
| spine.py | Spine (locked project structure), SpineViolation, SpineCheckResult, SpineManager, glob pattern matching, proposal verification | 41 |
| invariants.py | InvariantType (6 types), Invariant, InvariantResult, InvariantSet, InvariantLibrary (tests_must_pass, file/dir exists, forbidden patterns, no_secrets, max_file_size) | 36 |
| execution.py | ExecutionBudget (tokens/iterations/time/cost), ExecutionUsage, ExecutionState, StopReason, ExecutionStatus, SessionManager, checkpoint/resume | 34 |
| executor.py | AutonomousExecutor (step-function loop), StepResult, ExecutorConfig, ExecutionEvent, spine compliance, invariant verification, budget enforcement, checkpointing, resume | 45 |
| adapters.py | Governor adapter invariants: security_invariant, cfi_invariant, fiction_invariant, nonfiction_citation_invariant, tone_invariant, content_invariant, AdapterConfig, build_adapter_set | 76 |

**Autonomous Execution tests: 232**

### Strategic Test Suites (govtests)
| Module | Description | Tests |
|--------|-------------|-------|
| test_golden_files.py | Golden-file tests for JSON artifact shapes: receipts, execution state, spine, invariants, ledger entries, epistemic claims, quorum types, claim diff, adapters, continuity types, telemetry reports. Locks serialization schemas. | 150 |
| test_no_laundering.py | No-laundering regression tests: money rule, provenance rule, premise rule, silent retraction prevention, PEER_ASSERTED cap, envelope mode retrograde, evidence type gating, ClaimStatus FSM invariants, continuity rule (converged=False cannot be silently accepted) | 46 |
| test_failure_injection.py | Failure-injection for executor: timeouts, checkpoint write failures, corrupted checkpoint resume, consecutive failure threshold, budget exhaustion, spine checks during recovery, state persistence under faults | 27 |
| test_property_invariants.py | Property-based invariant tests: confidence bounds, provenance properties, ClaimStatus FSM properties, budget enforcement, execution state transitions, fail-closed patterns, InvariantSet blocking/warning partitioning, cascade termination, serialization roundtrips | 158 |
| test_contract_adapters.py | Contract tests for adapters: Invariant interface shape, InvariantResult shape, empty input safety, finding detection, AdapterFinding schema, on_violation/invariant_id forwarding, no input mutation, disabled invariant bypass, build_adapter_set composition, content_invariant escape hatch, severity thresholds, fault tolerance, extension filtering, InvariantSet integration, verifier exception handling, continuity adapter | 140 |

**Strategic Test Suite tests: 521**

### Invariant Store (Deferred 1: Invariant Management + Execution Shell)
| Module | Description | Tests |
|--------|-------------|-------|
| invariant_store.py | InvariantSpec, InvariantStore, VALID_KINDS (6 kinds), file-per-item persistence, materialization to live Invariant objects | 44 |
| cli.py (invariant + autonomous run) | `governor invariant add/list/show/remove/check`, `governor autonomous run` (noop step execution shell, dry-run, budget, spine) | 35 |

**Invariant Store tests: 79**

### Web UI (Deferred 2: W1-W3)
| Module | Description | Tests |
|--------|-------------|-------|
| context_manager.py | GovernorContext, GovernorContextManager, isolated contexts, fiction/code/nonfiction modes | 30 |
| chat_bridge.py | ChatBridge, OllamaBackend, AnthropicBackend, GovernorHooks, create_backend factory | 40 |
| webui/adapter.py | Refactored FastAPI adapter with ChatBridge, governor endpoints, backend selection | 21 |

**Web UI tests: 91**

### Structured Telemetry (Deferred 4, B2)
| Module | Description | Tests |
|--------|-------------|-------|
| telemetry.py | TelemetryEventType/Level enums (10 types), TelemetryConfig, TelemetryEvent, field helpers (Proposal/Verification/LLMCall/AutonomousIteration/Error/ContinuityTrace/ContinuityResult), StructuredLogger (JSONL, date-partitioned, rotation), TelemetryBackend/LoggingBackend, TelemetryCollector (pluggable, fail-safe), analyze_costs/analyze_performance/analyze_convergence, AnchorStats, ConvergenceReport, CSV/JSON export | 91 |
| test_convergence_telemetry.py | ContinuityTraceFields/ResultFields, collector methods, ConvergenceExecutor instrumentation, one-shot gate telemetry, analyze_convergence, ConvergenceReport, enum update | 60 |

**Structured Telemetry tests: 151**

### Continuity Enforcement (Deferred 5)
| Module | Description | Tests |
|--------|-------------|-------|
| continuity.py | AnchorType/Severity/RecommendedAction/CorrectionLevel enums, Anchor, Violation, ContinuityReport, AttemptLog, CorrectionConfig, ConvergenceBudget, ConvergenceResult, AnchorRegistry (JSON persistence), ContinuityChecker (lexical pattern matching, custom checks, action recommendation), CorrectionLadder (escalating correction with DEFAULT_LADDER), ConvergenceExecutor (closed-loop generation with budget enforcement, telemetry instrumented), GenerationProvider Protocol, convenience factories | 107 |
| continuity_bridges.py | Mode-specific anchor factories: fiction (characters, banned tropes, world rules, tone), nonfiction (concepts, positions), puppet (forbidden phrases, required ticks), GovernorHooks integration (check_response with telemetry, _load_mode_anchors, system prompt enrichment) | 83 |

**Continuity Enforcement tests: 190**

### Convergence Auto-Tuning (Deferred 6)
| Module | Description | Tests |
|--------|-------------|-------|
| convergence_tuning.py | TuningMode/TuningConfidence/ProposalStatus/ChangeSetType/RefactorSuggestionType/RollbackMetric/RollbackOperator enums, 28 dataclass types (Regime, Scope, TimeRange, EvidenceWindow, ChangeParameterUpdate, ChangePatternUpdate, ChangeRefactorSuggestion, ChangeSet, HardGuards, ObjectiveConstraints, Constraints, MetricsBlock, PredictedImpact, SummaryTable, ExampleEpisode, InterferenceEdge, SupportingEvidence, RollbackTrigger, TrialScope, EvaluationSet, TrialPlan, Approval, TuningProposal, TuningApply, ActionEffectiveness, PerAnchorAnalysis, TuningOpportunity, AdmissibilityResult), ProposalStore (file-per-item JSON), ConvergenceAnalyzer (per-anchor decomposition, action effectiveness, deadzone detection, interference, opportunities), 5 admissibility checks, ConvergenceTuner orchestrator | 145 |

**Convergence Auto-Tuning tests: 145**

### VS Code Extension (Deferred 3, Phase V1-V4)
| Module | Description | Tests |
|--------|-------------|-------|
| check.py | Position, Range, CheckFinding, CheckResult, security_finding_to_check, continuity_violation_to_check, run_check (unified aggregation) | 34 |
| viewmodel.py | GovernorViewModel (schema v2), SessionView, RegimeView, DecisionView, ClaimView, EvidenceView, ViolationView, ExecutionView, StabilityView, 8 section builders, build_viewmodel, build_v1_state, claim state mapping | 65 |
| test_state_cmd.py | `governor state --json` aggregation (v1+v2), `--json` flags on 7 existing commands | 22 |
| vscode-governor/ | VS Code extension: CLI client wrapper, diagnostic provider, GovernorTreeProvider (TreeView side panel, V2 schema), GovernorHoverProvider (decision/claim/violation context on hover), GovernorCodeActionProvider (quick fixes, suppress comments, security actions), RealtimeChecker (debounced on-type checking), commands (Check File, Check Selection, Show Output, Refresh State, Show Detail, Toggle Realtime, Check Now), keybindings (Ctrl+Shift+G, Ctrl+Shift+Alt+G), status bar, activity bar, on-save handler | 89 |

**VS Code Extension tests: 176 (87 Python + 89 TypeScript)**

### Maude Lite (Evidence-Gated Coding Harness)
| Module | Description | Tests |
|--------|-------------|-------|
| maude_lite.py | MaudeLite, MaudeLiteStatus, ClaimLevel, MaudeLiteClaim, CustodyScore, claim extraction, evidence linking, contradiction detection, custody scoring, exit shape checking, agent wrapper, JSONL logging | 101 |

**Maude Lite tests: 101**

### Interactive Violation Resolution (W4)
| Module | Description | Tests |
|--------|-------------|-------|
| violation_resolver.py | ViolationResolver, PendingViolation, ResolutionAction, ResolutionResult, ExceptionRecord, fix/revise/proceed actions, command detection, exception logging | 62 |
| chat_bridge.py (+) | ViolationPendingResponse, check_response_blocking, blocking severity filtering | +8 |
| adapter.py (+) | Resolution handling, pending check, format helpers | — |
| cli.py (+) | `check --interactive`, `wrap --check-continuity -i`, `hook pre-commit -c -i`, CLI integration tests | +12 |

**Interactive Violation Resolution tests: 82**

### W5 Writing Modules (Deferred 2, W5)
| Module | Description | Tests |
|--------|-------------|-------|
| writing_patterns.py | 18 pattern banks: hedge, self-reference, apology/meta, committee, meaning-word, normative, causal humility, falsifier, strawman, anxiety hedge, governance artifacts, institutional markers, bad exit, inflated weight, instruction filler, fake confidence, premature closure, bureaucratic | 68 |
| writing_governance.py | GovernanceVisibilityScorer (6 artifact categories), GovernanceLeakDetector (5 institutional voice types), SmoothingSuppressor, ExitShapeChecker | 82 |
| writing_tone.py | ToneVector (6D), ToneEnvelope, 16 regime envelopes, ToneCollision, ToneStabilityController, ToneDriftScorer | 95 |
| writing_regime.py | AffectRegime enum, RegimeVector, RegimeHysteresis, RpScorer, TragedyConstraints, SincerityTracker, DramaConstraints, MixerConfig | 112 |
| writing_nonfiction.py | NfClaimLevel, NfClaimNode, PromotionGate, VelocityController, EpScorer, ReScorer, HedgeCalibrator, AhScorer, NleadChecker, NonfictionFailureDetector | 89 |
| writing_intent.py | IntentCategory, IntentClassifier, 12 ancillary regime scorers (Ap, Fi, Au, Fp, Mt, Pa, Ut, Vv, De, Mc, Sa, Lm), RegimeCollision matrix | 72 |
| writing_constraints.py | 11 structural constraints + Section 14 causal narration resistance (6 techniques, 10 failure modes) | 118 |
| writing_ticketing.py | 14 prose + 11 code ticket types, recurrence detection, routing actions, auto-triage | 102 |
| writing_puppet.py | Extended puppet constraints from puppet.md spec | 98 |
| writing_code.py | Code-specific constraints from code.md spec | 86 |

**W5 Writing Modules tests: 922**

**Total: 6988 tests**

## Common Mistakes to Avoid

1. **Don't let agents provide evidence directly.**
   ```python
   # WRONG - agent can lie
   def propose(claim: str, evidence: Evidence): ...

   # RIGHT - agent provides pointers, governor verifies
   def propose(claim: Claim, pointers: list[str]): ...
   ```

2. **Don't use free-form strings for claims.**
   ```python
   # WRONG - unstructured, hard to validate
   propose(claim="I think the tests pass")

   # RIGHT - typed, machine-checkable
   propose(claim=Claim(type=ClaimType.TESTS_PASS, command=["pytest"]))
   ```

3. **Don't mix facts and decisions.**
   ```python
   # WRONG - treating preference as theorem
   facts.add("we use React")

   # RIGHT - normative choice in decisions ledger
   decisions.add(Decision(topic="framework", choice="react"))
   ```

4. **Don't make it advisory.**
   ```python
   # WRONG - can be ignored
   if not governor.approve(patch):
       logger.warning("Governor rejected patch")
       apply_patch_anyway(patch)  # oops

   # RIGHT - gate is mandatory
   if not governor.approve(patch):
       raise GovernorRejection(patch, reason)
   ```

5. **Don't let agents coordinate directly.**
   ```python
   # WRONG - direct agent-to-agent messaging bypasses the ledger
   agent_a.tell(agent_b, "I'm working on /users")

   # RIGHT - coordination as state in ledger
   propose(Claim(type=ClaimType.WORK_RESERVATION, scope=["src/api/users.py"]))
   ```

6. **Don't skip the transaction.**
   ```python
   # WRONG - TOCTOU: check-then-act without atomicity
   if not has_conflict(claim):
       commit(claim)  # another agent could have committed between check and write

   # RIGHT - atomic transaction
   with db.transaction():
       if not has_conflict(claim):
           commit(claim)
   ```

## Claim Types

```python
ClaimType.FILE_EXISTS      # path exists
ClaimType.SYMBOL_DEFINED   # symbol at path:span
ClaimType.API_SURFACE      # endpoint/signature at location
ClaimType.TESTS_PASS       # command exits 0
ClaimType.DECISION         # normative choice (framework, style)
ClaimType.CHANGESET        # proposed file mutations

# Multi-agent coordination (v2):
ClaimType.WORK_RESERVATION # reserve scope for task (locks resources)
ClaimType.INTENT           # declare intent (advisory, no lock)
```

## Receipt Types

```python
FileSnapshot   # Proves file state at verification time
CmdRun         # Proves command execution result
DiffReceipt    # Proves changeset content
```

## Operating Envelopes

- **strict** (default): All claims require receipts, decisions committed, conflicts blocked
- **exploratory**: Receipts optional, decisions not committed, conflicts allowed

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_claims.py -v

# Run with coverage
pytest tests/ --cov=governor
```

## Code Conventions

- Python 3.10+ (use `|` for union types)
- Dataclasses for all data objects
- Type hints everywhere
- Tests in `tests/test_<module>.py`

## The Meta-Constraint

You are using a tool designed to constrain AI coding agents. Apply its principles:
- Don't claim a file exists without checking
- Don't claim tests pass without running them
- Don't contradict architectural decisions
- Cite your receipts.
