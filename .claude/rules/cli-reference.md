# CLI Reference

Complete command reference for all governor CLIs.

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
governor receipts                # List gate receipts (newest first)
governor receipts --gate evidence_gate  # Filter by gate
governor receipts --verdict block --last 10  # Last 10 blocks
governor receipts --id <receipt_id> --evidence  # Show receipt + evidence bundle
governor receipts --json         # Machine-readable output

# Configuration
governor envelope                # Get/set operating mode (strict/exploratory)
governor decay                   # Check for stale facts

# Daemon (JSON-RPC control plane)
governor serve                           # Unix socket (default)
governor serve --stdio                   # Stdio mode (for Electron/Guvnah)
governor serve --socket /path/to/sock    # Custom socket path
governor serve --print-socket-path       # Print default socket path and exit
governor serve --mode fiction            # Set governor mode

# Integration
governor hook install            # Install git pre-commit hook
governor hook status             # Check hook status
governor hook pre-commit         # Run pre-commit check (called by git hook)
governor hook pre-commit --check-continuity  # Also check staged files for violations
governor hook pre-commit -c -i   # Interactive mode: offer fix/revise/proceed
governor hook post-tool          # Claude Code PostToolUse handler (stdin JSON, emits receipt)
governor hook pre-tool           # Claude Code PreToolUse handler (stdin JSON, stdout deny/allow)
governor hook task-complete      # Claude Code TaskCompleted handler (exit 0=allow, 2=reject)
governor wrap -- <cmd>           # Wrap agent command with enforcement
governor wrap --auto-approve -- <cmd>  # Auto-approve in exploratory mode
governor wrap --check-continuity -- <cmd>  # Check file changes for violations
governor wrap -c -i -- <cmd>     # Interactive mode: offer fix/revise/proceed
governor wrap --receipt-out <path> --ci-kind <kind> -- <cmd>  # CI receipt mode
    # ci-kind: unit_tests, lint, typecheck, build, security_scan,
    #          integration_tests, e2e_tests, coverage
governor changes                 # Show file approval status

# CI Lane (receipt policy verification)
governor ci verify <receipt_path>          # Verify receipts against default policy
governor ci verify <receipt_path> --policy <file>  # Custom JSON policy
governor ci verify <receipt_path> --receipt-out <path>  # Write meta-receipt
governor ci verify <receipt_path> --json   # JSON output

# MCP Server
governor mcp serve               # Run MCP server for Claude integration
governor mcp tools               # List available MCP tools
governor mcp call <tool>         # Test MCP tools directly

# Lane Routing (capability-based cascade)
governor lanes status                    # Show contracts, autopilot, budgets, artifact stats (--json)
governor lanes route "task description"  # Route a task, show RoutePlan
    [--risk standard|elevated|critical]
    [--side-effects] [--format-strict] [--context-heavy]
    [--force-lane 1|2|3] [--json]
governor lanes explain                   # Explain last route decision (--json)
governor lanes artifacts                 # Show artifact reuse store stats (--json, --evict-expired)

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
governor epistemic promote <id> retrieved                    # Promote provenance
governor epistemic retract <id>                              # Retract a claim
governor epistemic decay                                     # Decay ungrounded confidence

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

# Correlator Telemetry (capture detection)
governor correlator status            # Show regime, K-vector, active indicators (--json)
governor correlator history           # Show diagnostic history (--limit, --json)
governor correlator thresholds        # Show detection thresholds (--json)
governor correlator reset --confirm   # Reset correlator state

# Semantic Stability (perturbation-based conditioning audit)
governor conditioning status         # Show config, last audit, distribution stats (--json)
governor conditioning history        # Show audit history (--limit, --json)
governor conditioning config         # Show configuration (--json)
governor conditioning reset --confirm  # Reset audit history

# Scope Governor (locality-first policy)
governor scope status              # Run scope, grants, contracts (--json)
governor scope contracts           # List tool scope contracts (--json)
governor scope grants              # List active grants (--json, --all for expired)
governor scope history             # Escalation history (--limit, --json)
governor scope usages              # Grant usage log (--grant-id, --json)
governor scope check <tool_id>     # Check if tool within scope (--axis key=value)
governor scope set                 # Set run scope (--axis key=value, repeatable)
governor scope reset --confirm     # Reset scope governor state

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
governor claim-signals extract <text> # Extract signals from provided text
governor claim-signals scan <path>    # Scan a file for claim signals
governor claim-signals register <text> # Extract signals AND register as ASSUMED claims
governor claim-signals score <text>   # Show assertiveness score only

# Instrumentation Signals (Signal Plane v1)
governor signals list                 # List signals with filters
    [--name X] [--phase X] [--quality X] [--session X]
    [--since ISO] [--until ISO] [--limit N] [--after-seq N] [--json]
governor signals tail                 # Show newest signals
    [--limit N] [--name X] [--poll-ms N] [--json]
governor signals explain <hash>       # Full envelope details [--json]
governor signals stats                # Index health and counts [--json]
governor signals rebuild [--confirm]  # Drop and rebuild SQLite from JSONL
governor signals preflight           # Predict regime from latest signals [--json]

# Config Profiles (named governance presets)
governor profile list                 # List available profiles (builtin + custom)
governor profile use <name>           # Activate profile and apply settings
governor profile status               # Show active profile
governor profile off                  # Deactivate current profile
governor profile create <name>        # Create custom profile
governor profile delete <name>        # Delete custom profile

# Code Autopilot (intent-based governance)
governor intent show                  # Show resolved intent with provenance (--json)
governor intent set --profile <name>  # Set session intent (greenfield|established|production|hotfix|refactor)
governor intent set --profile <name> --scope "src/**" --timebox 90 --because "reason"  # Full options
governor intent clear                 # Clear session intent
governor code --profile <name>        # Shortcut: set profile from code command
governor code --status                # Show autopilot status

# Override Management (scoped exceptions for invariant anchors)
governor override create --anchor <id> --scope "..." --expires 2h --because "reason"
governor override list                # List active overrides (--json)
governor override show <id>           # Show override details
governor override revoke <id> --because "reason"  # Revoke early
governor override cleanup             # Remove expired overrides

# Interferometry (multi-model claim comparison)
governor interferometry run "prompt" --backends ollama:llama3,anthropic:claude-3-haiku  # Parallel mode (default)
governor interferometry run "prompt" -b ollama:m1,ollama:m2 --mode serial --rounds 2   # Serial deliberation chain
governor interferometry results                # List all runs
governor interferometry results --last         # Show most recent run
governor interferometry results --id <run_id>  # Show specific run (--json)
governor interferometry divergence             # Signal summary (disagreement rate, conflicts)
governor interferometry divergence --id <id>   # Divergence for specific run
governor interferometry accept --shared        # Promote shared claims to epistemic ledger
governor interferometry accept --all           # Also promote unique claims at low confidence
governor interferometry compare "prompt" --backends ollama:m1,claude:sonnet  # Code compare (risk markers + anchors)
governor interferometry compare --last [--markers] [--json]                  # Analyze last run
governor interferometry compare --id <run_id> [--json]                       # Analyze specific run
governor code compare "prompt" --backends ollama:m1,claude:sonnet            # Alias for interferometry compare
governor code compare --last [--markers] [--json]                            # Alias for interferometry compare --last

# External Constraint Attachment (claim grounding via Wikidata/Wikipedia/Scholar)
governor external substrates                         # List available substrates with trust profiles
governor external query wikidata Q42                 # Query Wikidata entity
governor external query wikidata "Douglas Adams" -a search  # Search Wikidata
governor external query wikipedia "Douglas Adams"    # Query Wikipedia article
governor external query scholar "10.1000/xyz" -a doi # Query DOI via CrossRef
governor external attach <claim_id> -s wikidata -q Q42  # Attach substrate snapshot to claim
governor external attach <claim_id> -s wikipedia -q "Douglas Adams" -v "claim value"  # With claim value
governor external bindings <claim_id>                # List external bindings for a claim
governor external discrepancies                      # Show all claim-substrate discrepancies
governor external discrepancies --pending            # Show only unresolved discrepancies
governor external resolve <disc_id> -r claim_retained --reason "Context differs"  # Resolve discrepancy

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

# Evidence Gate (evidence-gated coding harness)
governor gate check <text>       # Check agent output against kernel constraints
governor gate check --stdin      # Read from stdin
governor gate check -f <file>    # Read from file (--strict/--permissive, --format json)
governor gate validate <path>    # Validate file contents
governor gate config             # Show configuration and kernel constraints
governor gate score <text>       # Score custody metrics (Ap, Ip, Fp)
governor gate extract <text>     # Extract claims from content
governor gate pending            # Show pending violation requiring resolution (--format json)
governor gate fix                # Resolve pending violation by fixing the response
governor gate revise             # Resolve pending violation by updating the anchor
governor gate proceed            # Resolve pending violation by logging an exception (--scope, --expiry)
governor gate exceptions         # List logged exceptions (--format json)
governor gate heartbeat          # Show when the evidence gate last fired (--json)

# Continuity Enforcement (Deferred 5: closed-loop generation control)
governor continuity status              # Registry stats, anchor count by type
governor continuity anchor add          # --id, --type, --description, --required, --forbidden, --severity, --class
governor continuity anchor upgrade <id> --class <class>  # Upgrade anchor constraint class (invariant|preference)
governor continuity anchor list         # All anchors with type and severity
governor continuity anchor show <id>    # Full anchor details (JSON)
governor continuity anchor remove <id>  # Remove anchor
governor continuity check <text>        # Check text against all anchors, show report
governor continuity import <path>       # Import anchors from JSON file

# Session Continuity (capsule-based session management)
governor session create <name>          # Create a new session (--mode fiction|code|nonfiction)
governor session list                   # List all sessions (--mode, --json)
governor session resume <id>            # Resume a session by ID
governor session resume --last          # Resume most recent session
governor session show <id>              # Show session details (--json)
governor session fork <name>            # Fork current session (--from <id>)
governor session checkpoint <name>      # Create named checkpoint (--session <id>)
governor session checkpoints            # List checkpoints for current session
governor session promote <id> --confirm # Promote fork to mainline
governor session delete <id> --confirm  # Delete a session

# Context Compact (loss-aware compaction with receipts)
governor context status               # Show compaction config and status (--json)
governor context config               # Show/update compaction settings (--threshold, --min-turns, --keep-turns, --show)
governor context receipts             # List compaction receipts (--json, --last, --id)
governor context recover <rid> <hash> # Recover dropped content by hash
governor context cleanup              # Clean up old recovery stores (--max-age, --dry-run)
governor context manifest             # Show context manifest (what went into system prompt)
governor context manifest --json      # JSON output
governor context manifest --limit N   # Show N most recent manifests
governor context manifest --id <id>   # Lookup by build_id or manifest_hash prefix

# Git Governance (integrity invariants at commit boundaries)
governor git-gov status               # Show config and severity by check type (--json)
governor git-gov check                # Run all checks, exit 1 if blocking (--json)
governor git-gov artifacts            # Check artifact integrity for staged files (--json)
governor git-gov cross-index          # Check cross-index references (DOI, version tags) (--json)
governor git-gov pre-commit           # Run pre-commit checks (metadata, secrets) (--json)
governor git-gov verify-tag <tag>     # Verify tag conditions (--type, --json)
governor git-gov set-profile <name>   # Set profile (greenfield/established/production/hotfix)
governor git-gov allowlist list       # Show current allowlist
governor git-gov allowlist add <path> # Add path to allowlist
governor git-gov allowlist remove <p> # Remove path from allowlist

# Perforce Governance (integrity invariants on explicit authority)
governor p4 status                    # Show P4 availability and governance config
governor p4 check <cl>                # Run all integrity checks on changelist (--profile, --json)
governor p4 pre-submit <cl>           # Pre-submit hook for P4 triggers
governor p4 locks <file>              # Check lock status for a file (--json)
governor p4 release tag <cl> <tag>    # Mark changelist as immutable release
governor p4 release check <cl>        # Check if changelist is immutable (--json)
governor p4 doi map <doi> <depot> <cl>  # Create DOI to depot path mapping
governor p4 doi verify <doi>          # Verify DOI mapping integrity
governor p4 doi list                  # List all DOI mappings (--json)

# Unified Check (VS Code extension integration)
governor check <path>                  # Check a file for security + continuity issues
governor check <path> --format json    # JSON output for tooling
governor check --stdin --format json   # Read from stdin (JSON or plain text)
governor check <path> --no-security    # Skip security scanning
governor check <path> --no-continuity  # Skip continuity checking
governor check <path> --interactive    # Interactive mode: offer fix/revise/proceed on errors
governor check <path> -i --mode fiction  # Interactive with fiction-mode resolution options
```

## Fiction Governor CLI

```bash
fiction-gov drift status               # Show drift detector state
fiction-gov drift classify <text>      # Classify text register/mode
fiction-gov drift set <mode>           # Force narrative mode
fiction-gov drift check <text>         # Check text for drift
fiction-gov drift reset --confirm      # Reset drift detector

fiction-gov guardrails check <text>    # Check text against all guardrails
fiction-gov guardrails consent <a> <b> <scope> <level>  # Update consent state
fiction-gov guardrails profiles        # List validity profiles
fiction-gov guardrails dsi <text>      # Check text for DSI
fiction-gov guardrails aii <text>      # Check text for AII
fiction-gov guardrails config          # Show guardrail config
```
