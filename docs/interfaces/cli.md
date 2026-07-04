# CLI Reference

The `governor` command-line interface provides full access to all governor functionality.

---

## Installation

```bash
# Install from source
pip install -e .

# Verify installation
governor --version
governor --help
```

---

## Quick Start (Human-Friendly)

Running `governor` with no arguments shows a friendly status overview:

```bash
governor              # Shows status, not a man page
```

### For Fiction Writers

```bash
# Initialize fiction project
governor fiction init

# Add characters, world rules, forbidden elements
governor fiction character add elena --description "The protagonist"
governor fiction world add "Magic requires sacrifice"
governor fiction forbid "time travel"

# Check status
governor fiction status
```

### For Code Developers

```bash
# Initialize code project
governor code init

# Record decisions and constraints
governor code decision add "We use React for UI"
governor code constraint add "No eval() calls"

# Verify code follows decisions
governor code verify src/
```

### Resolving Violations

When Governor catches something:

```bash
governor resolve fix      # Regenerate compliant output
governor resolve change   # Update the rule
governor resolve allow    # Record operator's allow decision for this instance (logs exception)
```

---

## Core Workflow

### Initialize

```bash
# Create .governor/ directory
governor init

# Initialize with SQLite v2 backend
governor init --v2
```

### Propose → Verify → Apply

```bash
# Create a proposal
governor propose --claim "FILE_EXISTS:src/api.py"

# Verify proposal (produces receipts)
governor verify <proposal-id>

# Apply a verified proposal (the FSM gate enforces; apply executes, it does not authorize)
governor apply <proposal-id>
```

### Query State

```bash
# Operator dashboard (one-pager: regime, scars, scope, lanes, violations, receipts)
governor status
governor status --json             # Machine-readable dashboard

# Proposal list (old default, now opt-in)
governor status --proposals

# Claim health weather report
governor status --claims

# List recorded facts / decisions
governor facts
governor decisions

# Aggregated state (JSON)
governor state --json
governor state --json --schema v2  # Canonical ViewModel
```

---

## Command Reference

### Proposals & Verification

| Command | Description |
|---------|-------------|
| `governor propose --claim <claim>` | Create proposal with typed claim |
| `governor verify <id>` | Verify proposal, produce receipts |
| `governor apply <id>` | Execute a verified proposal (FSM gate enforces) |
| `governor status` | Operator dashboard (one-pager) |
| `governor status --proposals` | Show proposal list |
| `governor status --claims` | Claim health weather report |
| `governor status --json` | Machine-readable dashboard |
| `governor rejections` | Show rejection history |

### Ledgers

| Command | Description |
|---------|-------------|
| `governor facts` | List recorded facts |
| `governor facts --json` | JSON output |
| `governor decisions` | List recorded decisions |
| `governor decisions --json` | JSON output |
| `governor decay` | Check for stale facts |

### Configuration

| Command | Description |
|---------|-------------|
| `governor envelope` | Get/set operating mode (strict/exploratory) |
| `governor profile list` | List governance profiles |
| `governor profile use <name>` | Activate profile |
| `governor profile status` | Show active profile |
| `governor profile off` | Deactivate profile |

### Intent (Code Autopilot)

Control session intent — what you're trying to accomplish and how strictly to enforce it.

| Command | Description |
|---------|-------------|
| `governor intent show` | Show resolved intent with provenance |
| `governor intent show --json` | JSON output |
| `governor intent set --profile <name>` | Set session intent |
| `governor intent set --profile <name> --scope "src/**"` | With path scope |
| `governor intent set --profile <name> --timebox 90` | With time limit (minutes) |
| `governor intent set --profile <name> --because "reason"` | With reason |
| `governor intent clear` | Clear session intent |

**Profiles:**
- `greenfield` — New project, experimenting (warn only)
- `established` — Normal development (block violations)
- `production` — High-stakes changes (strict, requires evidence)
- `hotfix` — Urgent fix with narrow scope (block outside scope)
- `refactor` — Restructuring code (warn, soft anchors)

**Shortcut (from `governor code`):**
```bash
governor code --profile hotfix --scope "src/net/**" --timebox 90 --because "fixing auth bug"
governor code --status  # Show current autopilot state
```

### Override (Scoped Exceptions)

Record operator-authorized, time-limited exceptions for invariant constraints
(each override carries a receipt naming its authority and reason).

| Command | Description |
|---------|-------------|
| `governor override create` | Record operator-authorized scoped override |
| `governor override list` | List active overrides |
| `governor override list --json` | JSON output |
| `governor override show <id>` | Show override details |
| `governor override revoke <id> --because "reason"` | Revoke early |
| `governor override cleanup` | Remove expired overrides |

**Create override:**
```bash
governor override create \
  --anchor no-sql-injection \
  --scope "migrations/**" \
  --expires 2h \
  --because "Legacy migration script"
```

**Duration formats:** `30m` (minutes), `2h` (hours), `1d` (days), `2h30m` (combined)

### Continuity (Anchors)

| Command | Description |
|---------|-------------|
| `governor continuity status` | Anchor registry status |
| `governor continuity anchor add` | Create anchor (see options below) |
| `governor continuity anchor list` | List all anchors |
| `governor continuity anchor show <id>` | Show anchor details |
| `governor continuity anchor remove <id>` | Remove anchor |
| `governor continuity check <text>` | Check text against anchors |
| `governor continuity import <file>` | Import anchors from JSON |

**Anchor add options:**
```bash
governor continuity anchor add \
  --id <unique-id> \
  --type <canon|prohibition|persona|definition|requirement|style> \
  --description "What this anchor enforces" \
  --forbidden-patterns "pattern1" "pattern2" \
  --required-patterns "must-have" \
  --severity <warn|correct|reject> \
  --class <invariant|preference>  # Optional: constraint class
```

> `--type canon` names the anchor's *category*; adding an anchor records a
> constraint to check text against — it does not ratify the described content
> as canon (canon lives in the fiction bible/canon ledgers, not in anchor
> registration).

**Constraint classes:**
- `invariant` — Cannot be disabled by profile (e.g., security rules)
- `preference` — Profile can relax enforcement (default)

**Upgrade anchor constraint class:**
```bash
governor continuity anchor upgrade <id> --class invariant
```

### Violation Resolution

| Command | Description |
|---------|-------------|
| `governor lite pending` | View pending violation |
| `governor lite fix` | Regenerate compliant response |
| `governor lite revise` | Update the anchor |
| `governor lite proceed` | Log exception, continue |
| `governor lite exceptions` | View logged exceptions |
| `governor lite check <text>` | Check text against kernel |
| `governor lite validate <path>` | Validate file |
| `governor lite score <text>` | Score custody metrics |
| `governor lite extract <text>` | Extract claims |

> **Chat alias**: In interactive mode, you can also type `1`/`2`/`3` or `fix`/`revise`/`proceed` (or prefix with "governor", e.g., `governor fix`).

### Docket & Rulings (Adjudicator)

| Command | Description |
|---------|-------------|
| `governor docket list` | View pending cases on the docket |
| `governor docket show <case>` | Show details of a specific case |
| `governor rule sustain <case>` | Sustain constraint, regenerate compliant |
| `governor rule amend <case>` | Record operator's anchor amendment (output re-checked under it) |
| `governor rule except <case>` | Record operator-granted exception, log as precedent |
| `governor rule reverify <case>` | Re-verify stale claim |
| `governor rule dismiss <case>` | Dismiss stale claim |
| `governor precedent list` | View past rulings (precedent record) |
| `governor precedent search <query>` | Search precedents |
| `governor claim show <id>` | View claim details |
| `governor status --claims` | Claim health weather report |

### Integration

| Command | Description |
|---------|-------------|
| `governor check <path>` | Check file for violations |
| `governor check <path> --interactive --mode <mode>` | Interactive mode |
| `governor wrap -- <command>` | Wrap command with enforcement |
| `governor hook install` | Install git pre-commit hook |
| `governor hook pre-commit` | Run pre-commit check |
| `governor hook pre-commit --interactive --mode <mode>` | Interactive pre-commit |
| `governor changes` | Show file approval status |

### Multi-Agent

| Command | Description |
|---------|-------------|
| `governor agent register --id <id>` | Register agent |
| `governor agent list` | List registered agents |
| `governor agent permissions <id>` | Show agent permissions |
| `governor agent heartbeat --id <id>` | Keep registration active |
| `governor task claim --agent-id <id> --task "..."` | Claim task |
| `governor task list` | List tasks |
| `governor task complete --agent-id <id> --task-id <id>` | Complete task |

### Epistemic Governance

| Command | Description |
|---------|-------------|
| `governor epistemic status` | Ledger status |
| `governor epistemic claims` | List grounded claims |
| `governor epistemic dangerous` | List dangerous claims |
| `governor epistemic create <claim> --provenance <type>` | Create claim |
| `governor epistemic evidence <id> --type <type>` | Attach evidence |
| `governor epistemic promote <id> <provenance>` | Promote provenance |
| `governor epistemic retract <id>` | Retract claim |
| `governor epistemic decay` | Decay ungrounded confidence |

### Regime Detection

| Command | Description |
|---------|-------------|
| `governor regime status` | Current regime and signals |
| `governor regime history` | Regime transition history |
| `governor regime signals` | Current signal values |
| `governor regime update --tool-gain <x>` | Update signals |
| `governor regime thresholds` | Detection thresholds |
| `governor regime reset --confirm` | Reset to ELASTIC |

### Boil Control

| Command | Description |
|---------|-------------|
| `governor boil status` | Current mode and dwell state |
| `governor boil set <mode>` | Change preset |
| `governor boil presets` | List all presets |
| `governor boil events` | Recent boil events |
| `governor boil process --tool-gain <x>` | Process turn |
| `governor boil reset --confirm` | Reset to OOLONG |

### Security

| Command | Description |
|---------|-------------|
| `governor security scan <path>` | Scan for vulnerabilities |
| `governor security diff` | Scan staged git changes |
| `governor watch start` | Start continuous monitoring |
| `governor watch check` | Check for changes once |

### Telemetry

| Command | Description |
|---------|-------------|
| `governor telemetry enable` | Enable telemetry |
| `governor telemetry disable` | Disable telemetry |
| `governor telemetry status` | Show config and stats |
| `governor telemetry logs` | Query events |
| `governor telemetry analyze costs` | Cost breakdown |
| `governor telemetry analyze performance` | Latency stats |
| `governor telemetry analyze convergence` | Convergence stats |
| `governor telemetry export` | Export events |

### Operator Surface

These read-only commands collapse subsystem state into obvious workflows.

| Command | Description |
|---------|-------------|
| `governor status` | One-pager: regime, scars, scope, lanes, violations, receipts |
| `governor status --json` | Machine-readable dashboard (StatusRollup schema v1) |
| `governor doctor` | Walk subsystems, report non-nominal, suggest next commands |
| `governor doctor --json` | Machine-readable checks + counts |
| `governor doctor --strict` | Exit 1 on warnings (not just errors) |
| `governor explain <CODE>` | Diagnostic code → plain English (e.g. `DUCTILE`, `CAPTURE`) |
| `governor explain --list` | List all diagnostic codes |
| `governor trace` | Unified timeline of receipts, scars, scope, violations |
| `governor trace --last 20` | Limit to N events |
| `governor trace --source receipt` | Filter by source |
| `governor lanes status` | Lane contracts, autopilot level, budgets, artifacts |
| `governor lanes route "task"` | Route a task, show RoutePlan |
| `governor lanes explain` | Explain last route decision |
| `governor lanes artifacts` | Artifact reuse store stats |

### Dashboard (Rich TUI)

| Command | Description |
|---------|-------------|
| `governor dashboard live` | Live regime visualization |
| `governor dashboard replay <path>` | Replay trace file |
| `governor dashboard demo` | Demo mode |
| `governor dashboard stats <path>` | Trace statistics |

### Autonomous Execution

| Command | Description |
|---------|-------------|
| `governor spine lock <id>` | Lock project structure |
| `governor spine unlock <id> --confirm` | Unlock spine |
| `governor spine list` | List locked spines |
| `governor spine check` | Check against active spine |
| `governor invariant add <kind>` | Add invariant |
| `governor invariant list` | List invariants |
| `governor invariant check` | Run invariant checks |
| `governor autonomous list` | List sessions |
| `governor autonomous show <id>` | Show session |
| `governor autonomous run --task "..."` | Drive a governed execution session (spine + invariants enforce) |
| `governor autonomous handoff <id>` | Show handoff summary |

### Puppet Mode

| Command | Description |
|---------|-------------|
| `governor puppet list` | List puppet profiles |
| `governor puppet show <id>` | Show profile details |
| `governor puppet activate <id>` | Activate puppet |
| `governor puppet deactivate` | Deactivate puppet |
| `governor puppet status` | Active puppet status |
| `governor puppet create <id>` | Create custom profile |
| `governor puppet test <id> <text>` | Test against profile |
| `governor puppet render <text>` | Render through puppet |

### Claim Tracking

| Command | Description |
|---------|-------------|
| `governor claim-diff status` | Diff tracking state |
| `governor claim-diff snapshot` | Take snapshot |
| `governor claim-diff run` | Diff vs snapshot |
| `governor claim-diff violations` | List violations |
| `governor claim-diff laundering` | Show laundering only |
| `governor signals extract <text>` | Extract claim signals |
| `governor signals scan <path>` | Scan file for signals |
| `governor signals register <text>` | Extract + register |
| `governor taint status` | Taint index stats |
| `governor taint check <text>` | Check against taint index |

### Quorum & Consensus

| Command | Description |
|---------|-------------|
| `governor quorum status <id>` | Quorum state |
| `governor quorum vote <id>` | Cast vote |
| `governor quorum policies` | List policies |
| `governor independence score <id>` | Score vote independence |
| `governor independence check <id>` | Check threshold |

### Auto-Tuning

| Command | Description |
|---------|-------------|
| `governor tune status` | Tuning state |
| `governor tune thresholds --analyze` | Threshold suggestions |
| `governor tune thresholds --apply` | Write confident threshold suggestions to config |
| `governor tune convergence status` | Convergence tuning state |
| `governor tune convergence propose` | Generate proposals |
| `governor tune convergence apply <id>` | Apply proposal |

### Claude Integration

| Command | Description |
|---------|-------------|
| `governor claude-hooks install` | Install hook scripts |
| `governor claude-hooks uninstall` | Remove hooks |
| `governor claude-hooks status` | Check installation |
| `governor claude-hooks approve <file>` | Approve file |
| `governor claude-hooks block <cmd>` | Block command |

### MCP Server

| Command | Description |
|---------|-------------|
| `governor mcp serve` | Run MCP server |
| `governor mcp tools` | List MCP tools |
| `governor mcp call <tool>` | Test MCP tool |

**Intent/Override MCP tools:**
- `governor_get_intent` — Get resolved intent with provenance
- `governor_set_intent` — Set session intent (profile, scope, timebox)
- `governor_suggest_profile` — Get profile suggestion for branch/files
- `governor_override` — Create scoped override
- `governor_override_list` — List active overrides

---

## Persona Commands (Human-Friendly)

### Fiction (governor fiction)

| Command | Description |
|---------|-------------|
| `governor fiction init` | Initialize fiction project with sample canon |
| `governor fiction status` | Show characters, world rules, forbidden |
| `governor fiction character add <name>` | Add a character |
| `governor fiction character list` | List all characters |
| `governor fiction character show <id>` | Show character details |
| `governor fiction character remove <id>` | Remove a character |
| `governor fiction world add <rule>` | Add a world-building rule |
| `governor fiction world list` | List world rules |
| `governor fiction forbid <pattern>` | Add forbidden element |

### Code (governor code)

| Command | Description |
|---------|-------------|
| `governor code init` | Initialize code project |
| `governor code status` | Show decisions and constraints |
| `governor code decision add <text>` | Add architectural decision |
| `governor code decision list` | List decisions |
| `governor code constraint add <text>` | Add a constraint |
| `governor code constraint list` | List constraints |
| `governor code verify [path]` | Verify code against decisions |

### Resolve (governor resolve)

| Command | Description |
|---------|-------------|
| `governor resolve fix` | Regenerate compliant response |
| `governor resolve change` | Update the rule/anchor |
| `governor resolve allow` | Record operator's allow decision (logs exception) |

---

## Domain-Specific CLIs

### Fiction Governor

```bash
fiction-gov thread list          # List plot threads
fiction-gov thread show <id>     # Thread details
fiction-gov proposal create      # Create scene proposal
fiction-gov prompt <scene>       # Generate writing prompt
fiction-gov drift status         # Context drift state
fiction-gov drift check <text>   # Check for drift
fiction-gov guardrails check <text>  # Check guardrails
```

### Nonfiction Governor

```bash
nonfiction-gov source add        # Add source
nonfiction-gov source list       # List sources
nonfiction-gov concept add       # Add concept
nonfiction-gov position add      # Add position
nonfiction-gov verify citation   # Verify citation
nonfiction-gov tone show         # Show tone profile
nonfiction-gov tone check <file> # Check tone
nonfiction-gov cfi check <text>  # Check for frame intrusion
```

### Ops Governor

```bash
ops-gov runbook add              # Add runbook
ops-gov runbook list             # List runbooks
ops-gov window add               # Add time window
ops-gov blast-radius add         # Add blast radius limit
ops-gov precondition add         # Add precondition
ops-gov verify action <action>   # Verify action permitted
```

---

## Common Patterns

### Interactive Violation Resolution

```bash
# Check with interactive resolution
governor check src/api.py --interactive --mode code

# Wrap command with interactive resolution
governor wrap --interactive --mode fiction -- claude "write chapter 3"

# Pre-commit with interactive resolution
governor hook pre-commit --interactive --mode code
```

### JSON Output for Scripting

Most commands support `--json` for machine consumers:

```bash
governor status --json              # StatusRollup (dashboard)
governor status --proposals --json  # Proposal list
governor doctor --json              # Subsystem health checks
governor trace --json               # Unified event timeline
governor facts --json
governor decisions --json
governor state --json               # Canonical ViewModel
governor regime status --json
governor lanes status --json
```

### Piping and Stdin

```bash
# Check stdin
echo "some text" | governor continuity check --stdin
cat file.md | governor lite check --stdin

# Pipe to other tools
governor state --json | jq '.regime.status'
```

### Batch Operations

```bash
# Import anchors from file
governor continuity import anchors.json

# Scan directory
governor security scan src/

# Check multiple files
for f in src/*.py; do governor check "$f" --format json; done
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Violation found (blocking) |
| 3 | Invalid arguments |
| 4 | Governor not initialized |
| 5 | Permission denied |

Use in scripts:

```bash
governor check src/api.py
if [ $? -eq 2 ]; then
  echo "Violations found, resolve before continuing"
  exit 1
fi
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOVERNOR_DIR` | Path to .governor directory |
| `GOVERNOR_MODE` | Default mode (fiction/code/nonfiction/ops) |
| `GOVERNOR_PROFILE` | Default profile |
| `GOV_PROFILE` | Autopilot profile override (greenfield/established/production/hotfix/refactor) |
| `ANTHROPIC_API_KEY` | API key for Anthropic backend |
| `OLLAMA_HOST` | Ollama server URL |
| `CLAUDE_PATH` | Path to Claude Code CLI |

---

## Configuration File

Create `.governor/config.json`:

```json
{
  "mode": "code",
  "profile": "strict",
  "telemetry": {
    "enabled": true,
    "logging": true
  },
  "security": {
    "scan_on_commit": true
  },
  "continuity": {
    "interactive": true
  }
}
```

---

*"Everything is a command. Every command is documented."*
