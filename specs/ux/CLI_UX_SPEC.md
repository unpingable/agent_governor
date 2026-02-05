# CLI UX Specification

## Version 0.1 — Layered Commands by Mode

### Companion to: WebUI UX Spec, Maude Profile Specs

---

## Executive Summary

The CLI currently has 50+ commands in a flat namespace. Service-mode and user-mode commands are mixed together. Users face a wall of options when they just want to do one thing.

**Target State:** Layered CLI with mode-specific entry points. The 80% case is 5-10 commands. Advanced functionality exists but is explicitly separated.

**Success Metric:** A fiction user can set up characters and rules without ever seeing "epistemic" or "regime" in their terminal.

---

## 1. Design Principles

### 1.1 Three Audiences, Three Depths

| Audience | Entry Point | Commands Visible |
|----------|-------------|------------------|
| Fiction writer | `governor fiction` | ~10 commands |
| Developer | `governor code` | ~15 commands |
| Power user / debugger | `governor advanced` | 50+ commands |

### 1.2 Progressive Disclosure

- Running bare `governor` shows status + hints, not help dump
- Mode commands (`fiction`, `code`) show only relevant subcommands
- `advanced` is explicitly opt-in

### 1.3 Plain Language by Default

| Internal Term | User-Facing Term |
|---------------|------------------|
| assertion anchor | character trait / world rule |
| prohibition anchor | boundary / constraint |
| regime envelope | tone |
| hysteresis | (never shown) |
| provenance hierarchy | (never shown) |

### 1.4 Consistent Verbs

| Verb | Meaning |
|------|---------|
| `add` | Create new item |
| `list` | Show all items |
| `show` | Show one item in detail |
| `edit` | Modify existing item |
| `remove` | Delete item |
| `enable` / `disable` | Toggle without deleting |

---

## 2. Command Structure

### 2.1 Top Level

```
governor
├── fiction          # Fiction-specific commands
├── code             # Code-specific commands  
├── check            # Check content (universal)
├── resolve          # Resolve pending violation
├── status           # Quick status overview
├── init             # Initialize new project
├── help             # Help with progressive disclosure
└── advanced         # Power user commands (50+)
```

### 2.2 Bare `governor` Command

Running `governor` with no arguments shows contextual status:

```
$ governor

Governor v1.0.0 — Fiction Mode

Story: "The Midnight Garden"
  Characters: 3 (Elena, Marcus, Vera)
  World Rules: 5
  Boundaries: 2

Recent:
  ✓ No pending violations
  Last catch: 2 hours ago (fixed)

Quick commands:
  governor fiction character add    Add a character
  governor fiction status           Full status
  governor check <file>             Check content

Run 'governor help' for more options.
```

### 2.3 `governor help` Command

Progressive help, not dump:

```
$ governor help

Governor - Keep your AI consistent

MODES (start here):
  fiction     Commands for creative writing
  code        Commands for software development

COMMON COMMANDS:
  status      Show current state
  check       Check content for violations
  resolve     Handle pending violations
  init        Set up governor for a project

ADVANCED:
  advanced    Power user commands (50+ options)

Run 'governor <command> --help' for details.
Run 'governor help <topic>' for guides.

TOPICS:
  characters  How to set up characters (fiction)
  decisions   How to record decisions (code)
  violations  How violation resolution works
```

---

## 3. Fiction Mode Commands

### 3.1 Structure

```
governor fiction
├── character
│   ├── add         # Add a character
│   ├── list        # List all characters
│   ├── show        # Show character details
│   ├── edit        # Edit a character
│   ├── remove      # Remove a character
│   ├── enable      # Re-enable disabled character
│   └── disable     # Disable without removing
│
├── world
│   ├── add         # Add a world rule
│   ├── list        # List all rules
│   ├── show        # Show rule details
│   ├── edit        # Edit a rule
│   └── remove      # Remove a rule
│
├── boundary
│   ├── add         # Add a boundary
│   ├── list        # List all boundaries
│   ├── edit        # Edit a boundary
│   └── remove      # Remove a boundary
│
├── tone
│   ├── set         # Set tone profile
│   ├── show        # Show current tone
│   └── presets     # List available presets
│
├── catches         # Show recent violations
├── history         # Full violation history
├── status          # Complete story status
├── export          # Export story bible
└── import          # Import story bible
```

### 3.2 Command Examples

**Adding a character:**

```
$ governor fiction character add

Name: Elena Vasquez
Physical description: Tall, green eyes, black hair with grey streak
Personality/voice: Formal speech, never uses contractions
Things they would never do: Show emotion openly, trust easily

✓ Character "Elena Vasquez" added

Quick check — I've set up these constraints:
  • Elena has green eyes (not blue, brown, etc.)
  • Elena has black hair with grey streak
  • Elena speaks formally without contractions
  • Elena won't show emotion openly or trust easily

Edit anytime with: governor fiction character edit "Elena Vasquez"
```

Or non-interactive:

```
$ governor fiction character add "Elena Vasquez" \
    --physical "Tall, green eyes, black hair" \
    --personality "Formal, no contractions" \
    --never "show emotion openly"

✓ Character "Elena Vasquez" added
```

**Adding a world rule:**

```
$ governor fiction world add "Magic requires spoken words"

✓ World rule added

The AI will be blocked if it shows:
  • Silent magic
  • Magic without incantation
  • Unconscious people casting spells

Add details with: governor fiction world edit <id>
```

**Setting tone:**

```
$ governor fiction tone set --preset literary

✓ Tone set to "Literary"
  • Dense prose
  • Measured pacing
  • Moderate darkness
  • Observational distance

Adjust with sliders: governor fiction tone set --dark 0.7 --dense 0.8
```

**Checking recent catches:**

```
$ governor fiction catches

Recent Violations (last 7 days):

1. "Elena's blue eyes sparkled" (2 hours ago)
   Conflicts with: Elena has green eyes
   Resolution: Fixed — AI rewrote with green eyes

2. "Marcus punched the wall in anger" (yesterday)
   Conflicts with: Marcus never uses violence
   Resolution: Allowed — noted as dream sequence

3. "She cast the spell silently" (3 days ago)
   Conflicts with: Magic requires spoken words
   Resolution: Canon updated — some elders can cast silently

View full history: governor fiction history
```

**Exporting story bible:**

```
$ governor fiction export --format yaml > story-bible.yaml

✓ Exported 3 characters, 5 world rules, 2 boundaries
```

### 3.3 Fiction Status

```
$ governor fiction status

Story: "The Midnight Garden"
Mode: Fiction
Strictness: Standard (block contradictions)

Characters (3):
  ● Elena Vasquez — protagonist, formal speech
  ● Marcus Chen — no violence, protective
  ● Vera Okonkwo — sarcastic, hides vulnerability

World Rules (5):
  • Magic requires spoken words
  • Technology: 1920s level
  • The Veil separates mortal/immortal realms
  • Immortals cannot lie directly
  • Silver burns magical creatures

Boundaries (2):
  🚫 No graphic violence
  🚫 No explicit sexual content

Tone: Literary (dark: 0.6, dense: 0.7)

Recent Catches: 3 this week (2 fixed, 1 allowed)

Health: ✓ All systems normal
```

---

## 4. Code Mode Commands

### 4.1 Structure

```
governor code
├── decision
│   ├── add         # Record a decision
│   ├── list        # List all decisions
│   ├── show        # Show decision details
│   ├── edit        # Edit a decision
│   └── remove      # Remove a decision
│
├── constraint
│   ├── add         # Add a constraint
│   ├── list        # List all constraints
│   ├── edit        # Edit a constraint
│   └── remove      # Remove a constraint
│
├── verify
│   ├── run         # Run verification
│   ├── config      # Configure verifiers
│   └── status      # Show verifier status
│
├── ledger
│   ├── show        # Show ledger entries
│   ├── facts       # Show facts only
│   ├── decisions   # Show decisions only
│   └── rejections  # Show rejections only
│
├── receipt
│   ├── show        # Show receipt details
│   └── verify      # Verify a receipt
│
├── status          # Complete project status
├── export          # Export decisions
└── import          # Import decisions
```

### 4.2 Command Examples

**Recording a decision:**

```
$ governor code decision add

Decision: Using REST API, not GraphQL

Rationale (why this choice): 
Team has REST experience, simpler debugging, sufficient for our scale

Alternatives considered:
GraphQL, gRPC

✓ Decision recorded: "Using REST API, not GraphQL"

The AI will be blocked if it tries to:
  • Introduce GraphQL
  • Add Apollo Client
  • Create .graphql files

Edit anytime with: governor code decision edit <id>
```

Or non-interactive:

```
$ governor code decision add "Using REST API" \
    --rationale "Team experience, simpler" \
    --alternatives "GraphQL, gRPC" \
    --scope "src/api/**"

✓ Decision recorded
```

**Adding a constraint:**

```
$ governor code constraint add "No Redux" \
    --patterns "redux,createStore,useDispatch" \
    --scope "src/**"

✓ Constraint added: "No Redux"

Blocked patterns:
  • "redux"
  • "createStore"
  • "useDispatch"

Applies to: src/**
```

**Running verification:**

```
$ governor code verify run

Running verifiers...

  ✓ Tests: 47 passed (12.3s)
  ✓ Types: No errors (3.1s)
  ✓ Lint: No warnings (1.2s)

All verifications passed.
Receipts generated:
  • test-run-a7f3c2d8
  • typecheck-b8e4d1f9
  • lint-c9f5e2a0
```

**Viewing the ledger:**

```
$ governor code ledger show --recent 10

Ledger (most recent 10):

2024-01-20 14:32 │ DECISION │ Using REST API
                 │          │ Rationale: Team experience, simpler
                 │          │ Scope: project-wide

2024-01-20 15:01 │ FACT     │ Created: src/api/routes.py
                 │          │ Receipt: a7f3c2d8
                 │          │ Hash: sha256:9f86d08...

2024-01-20 15:45 │ REJECTED │ "Using GraphQL for efficiency"
                 │          │ Contradicts: REST API decision
                 │          │ Resolution: Fixed

Filter: --facts, --decisions, --rejections
Export: --format json
```

### 4.3 Code Status

```
$ governor code status

Project: agent-governor
Mode: Code
Verification: Tests + Types + Lint

Decisions (4):
  ● REST API (not GraphQL) — 2024-01-15
  ● PostgreSQL for persistence — 2024-01-10
  ● Monorepo structure — 2024-01-08
  ● Python 3.11+ required — 2024-01-05

Constraints (2):
  🚫 No Redux
  🚫 No raw SQL (use ORM)

Verification Status:
  ✓ Tests: passing (last run: 10 min ago)
  ✓ Types: clean
  ✓ Lint: clean

Ledger: 47 facts, 4 decisions, 3 rejections

Health: ✓ All systems normal
```

---

## 5. Universal Commands

### 5.1 `governor check`

Check content for violations:

```
$ governor check chapter-3.txt

Checking chapter-3.txt...

Found 2 violations:

1. Line 47: "Elena's blue eyes"
   Conflicts with: Elena has green eyes
   Severity: BLOCK

2. Line 112: "He cast the spell with a thought"  
   Conflicts with: Magic requires spoken words
   Severity: BLOCK

Run 'governor resolve' to handle these.
```

Or for code:

```
$ governor check src/api/graphql.py

Checking src/api/graphql.py...

Found 1 violation:

1. Line 1: import graphql
   Conflicts with: REST API decision (no GraphQL)
   Severity: BLOCK

Run 'governor resolve' to handle this.
```

### 5.2 `governor resolve`

Interactive resolution:

```
$ governor resolve

Pending violation:

  "Elena's blue eyes sparkled in the lamplight"
  
  Conflicts with: Elena has green eyes

Choose:
  [1] Fix — Rewrite to match canon
  [2] Update — Change canon (Elena now has blue eyes)
  [3] Allow — Let this through (log as exception)
  [q] Quit — Handle later

Choice: 
```

Or non-interactive:

```
$ governor resolve --fix
$ governor resolve --update
$ governor resolve --allow --reason "dream sequence"
```

### 5.3 `governor init`

Initialize governor for a project:

```
$ governor init

What type of project?
  [1] Fiction (novel, stories, creative writing)
  [2] Code (software development)
  [3] Both

Choice: 1

Story name: The Midnight Garden

✓ Initialized .governor/ directory
✓ Created story: "The Midnight Garden"

Next steps:
  governor fiction character add    Add your first character
  governor fiction world add        Add a world rule
  governor fiction status           See current setup
```

---

## 6. Advanced Commands

### 6.1 Structure

All existing 50+ commands live under `governor advanced`:

```
governor advanced
├── continuity       # Full anchor system
│   ├── anchor      # CRUD for anchors
│   ├── check       # Continuity checks
│   └── status      # Continuity status
│
├── epistemic        # Provenance and confidence
│   ├── provenance  # View provenance chains
│   ├── confidence  # Confidence scoring
│   └── status      # Epistemic status
│
├── regime           # Stability monitoring
│   ├── status      # Current regime
│   ├── history     # Regime transitions
│   └── config      # Regime thresholds
│
├── drift            # Drift detection
│   ├── status      # Current drift
│   ├── quarantine  # Quarantined premises
│   └── config      # Drift settings
│
├── multi-agent      # Coordination
│   ├── register    # Register agent
│   ├── lease       # Lease management
│   └── status      # Agent status
│
├── ledger           # Raw ledger access
│   ├── query       # Query ledger
│   ├── export      # Export ledger
│   └── repair      # Repair ledger
│
├── hook             # Git hooks
│   ├── install     # Install hooks
│   ├── uninstall   # Remove hooks
│   └── status      # Hook status
│
├── mcp              # MCP server
│   ├── serve       # Start server
│   └── config      # Configure MCP
│
└── debug            # Debugging tools
    ├── dump        # Dump state
    ├── replay      # Replay events
    └── trace       # Trace execution
```

### 6.2 Accessing Advanced Commands

```
$ governor advanced

⚠️  Advanced commands — for debugging and power users

These commands expose internal systems. Most users don't need them.

SUBSYSTEMS:
  continuity   Anchor and constraint system
  epistemic    Provenance and confidence tracking
  regime       Stability regime monitoring
  drift        Temporal drift detection
  multi-agent  Agent coordination
  ledger       Raw ledger operations
  hook         Git hook management
  mcp          MCP server for Claude
  debug        Debugging and diagnostics

Run 'governor advanced <subsystem>' to see commands.

Prefer 'governor fiction' or 'governor code' for normal use.
```

### 6.3 Example Advanced Usage

```
$ governor advanced regime status

Regime Status:
  Current: ELASTIC (healthy)
  Stability: 0.87
  Last transition: WARM → ELASTIC (3 days ago)

Indicators:
  • Contradiction rate: 0.02 (low)
  • Drift velocity: 0.01 (stable)
  • Anchor coherence: 0.94 (high)

Thresholds:
  ELASTIC: stability > 0.8
  WARM: stability 0.6-0.8
  DUCTILE: stability 0.4-0.6
  UNSTABLE: stability < 0.4

History: governor advanced regime history
Config: governor advanced regime config
```

---

## 7. Output Formatting

### 7.1 Defaults

- Color output when TTY detected
- No color when piped
- UTF-8 symbols (✓, ✗, ●, 🚫) with ASCII fallback

### 7.2 Machine-Readable Output

All commands support:

```
--format json     # JSON output
--format yaml     # YAML output
--quiet           # Minimal output (for scripts)
--no-color        # Force no color
```

Example:

```
$ governor fiction character list --format json

[
  {
    "id": "elena-vasquez",
    "name": "Elena Vasquez",
    "type": "character",
    "physical": "Tall, green eyes, black hair",
    "personality": "Formal, no contractions",
    "prohibitions": ["show emotion openly"]
  }
]
```

### 7.3 Verbosity

```
--verbose         # More detail
--debug           # Debug output (for troubleshooting)
```

---

## 8. Configuration

### 8.1 Config File

`~/.governor/config.yaml` or `.governor/config.yaml`:

```yaml
# Default mode
mode: fiction

# Default story/project
default_story: "the-midnight-garden"

# Output preferences
color: auto  # auto, always, never
symbols: unicode  # unicode, ascii

# Strictness
fiction:
  strictness: standard  # strict, standard, relaxed
  
code:
  verification:
    tests: true
    types: true
    lint: true
```

### 8.2 Environment Variables

```
GOVERNOR_MODE=fiction
GOVERNOR_COLOR=never
GOVERNOR_DEBUG=1
```

---

## 9. Error Messages

### 9.1 Principles

- Say what went wrong
- Say what to do about it
- Link to help if complex

### 9.2 Examples

**Good:**
```
Error: Character "Elena" not found

Did you mean:
  • Elena Vasquez

List all characters: governor fiction character list
```

**Good:**
```
Error: Cannot remove character with active references

"Elena Vasquez" is referenced by:
  • 3 world rules
  • 2 relationship anchors

To remove anyway: governor fiction character remove "Elena Vasquez" --force
To see references: governor fiction character show "Elena Vasquez" --refs
```

**Bad:**
```
Error: ANCHOR_NOT_FOUND: elena
```

---

## 10. Shell Completions

### 10.1 Installation

```
$ governor completions bash >> ~/.bashrc
$ governor completions zsh >> ~/.zshrc
$ governor completions fish > ~/.config/fish/completions/governor.fish
```

### 10.2 What Completes

- Subcommands at each level
- Character/rule/decision names
- File paths where appropriate
- Flag values

```
$ governor fiction character ed<TAB>
$ governor fiction character edit <TAB>
Elena Vasquez    Marcus Chen    Vera Okonkwo
```

---

## 11. Migration Path

### 11.1 Existing Users

Old commands still work but show deprecation:

```
$ governor continuity anchor add ...

⚠️  This command has moved to: governor advanced continuity anchor add

For fiction writing, try: governor fiction character add
For code projects, try: governor code constraint add

This alias will be removed in v2.0.
```

### 11.2 Mapping Old → New

| Old Command | New Command (Fiction) | New Command (Code) |
|-------------|----------------------|-------------------|
| `governor continuity anchor add --type assertion` | `governor fiction character add` | `governor code decision add` |
| `governor continuity anchor add --type prohibition` | `governor fiction boundary add` | `governor code constraint add` |
| `governor continuity anchor list` | `governor fiction status` | `governor code status` |
| `governor check` | `governor check` (unchanged) | `governor check` (unchanged) |
| `governor lite pending` | `governor resolve` | `governor resolve` |

---

## 12. Success Metrics

| Metric | Target |
|--------|--------|
| Commands needed for basic fiction setup | ≤ 5 |
| Commands visible to fiction user | ≤ 15 |
| Time to first character (new user) | < 2 minutes |
| Users who discover `advanced` | < 20% (most don't need it) |
| Error messages with actionable fix | 100% |

---

## 13. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |

---

*"Running bare `governor` shows status + hints, not help dump."*

*"If a fiction user sees 'epistemic' in their terminal, something went wrong."*

*"Advanced is explicitly opt-in."*
