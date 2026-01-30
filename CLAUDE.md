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
**Fiction Governor**: Plot threads, scene proposals, prompt generation, narrative constraints, manuscript scanning, similarity matching.
**Non-Fiction Governor**: Corpus management, DOI fetching, citation verification.
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
**Total: 2182 tests**

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
governor facts                   # List recorded facts
governor decisions               # List recorded decisions
governor status                  # Show proposal statuses
governor rejections              # Show rejection history

# Configuration
governor envelope                # Get/set operating mode (strict/exploratory)
governor decay                   # Check for stale facts

# Integration
governor hook install            # Install git pre-commit hook
governor hook status             # Check hook status
governor wrap -- <cmd>           # Wrap agent command with enforcement
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
governor task list               # List tasks/reservations
governor task cancel --agent-id X --task-id Y                # Cancel task

# Epistemic Governance (provenance, confidence, evidence)
governor epistemic status                                    # Show ledger status
governor epistemic claims                                    # List grounded claims
governor epistemic dangerous                                 # List dangerous claims (high confidence, no evidence)
governor epistemic create "claim" --provenance assumed       # Create a claim
governor epistemic evidence <id> --type tool_trace -l X -s Y # Attach evidence

# Regime Detection (operational health monitoring)
governor regime status                # Show current regime and signals
governor regime history               # Show regime transition history
governor regime signals               # Show current signal values
governor regime update --tool-gain X  # Update signals and check regime
governor regime thresholds            # Show detection thresholds
governor regime reset --confirm       # Reset to default ELASTIC state

# Boil Control (named presets with dwell time)
governor boil status                  # Show current mode, regime, dwell state
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
└── cli.py            # fiction-gov CLI (thread, proposal, prompt commands)

src/nonfiction_governor/
├── __init__.py       # Public API exports
├── types.py          # Source, Concept, Position, WritingClaim
├── doi.py            # DOI metadata fetching (CrossRef/DataCite)
├── corpus.py         # Corpus ledger (your papers, concepts, positions)
├── verifiers.py      # CitationVerifier, TerminologyVerifier, ConsistencyVerifier
└── cli.py            # nonfiction-gov CLI

src/ops_governor/
├── __init__.py       # Public API exports
├── types.py          # Runbook, TimeWindow, BlastRadius, Precondition
├── verifiers.py      # RunbookVerifier, TimeWindowVerifier, BlastRadiusVerifier, PreconditionChainVerifier
├── policy.py         # PolicyRegistry, operational policy enforcement
└── cli.py            # ops-gov CLI
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
| routing.py | Router, ModelRegistry, ComplexityEstimator, TaskHistory, adaptive routing | 48 |

**Multi-Agent Routing tests: 48**

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

**Fiction Governor tests: 189**

### Non-Fiction Governor (Academic Writing)
| Module | Description | Tests |
|--------|-------------|-------|
| types.py | Source, Concept, Position, WritingClaim | 40 |
| corpus.py | Corpus ledger, conflict detection | 26 |
| verifiers.py | Citation, terminology, consistency verification | 25 |
| doi.py | DOI metadata fetching (CrossRef/DataCite) | -- |

**Non-Fiction Governor tests: 91**

**Total: 2091 tests**

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
