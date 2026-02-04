# VS Code Extension Guide

The Governor VS Code extension provides real-time constraint checking, diagnostics, and state visualization directly in your editor.

---

## Installation

### From Source

```bash
cd vscode-governor
npm install
npm run compile
```

Then in VS Code:
1. Open the `vscode-governor` folder
2. Press F5 to launch Extension Development Host
3. The extension activates in the new window

### From VSIX (when packaged)

```bash
cd vscode-governor
npm run package
code --install-extension governor-0.0.1.vsix
```

---

## Features

### Real-Time Checking

The extension checks your code as you type, showing violations inline.

**Enable/Disable:**
- Command Palette: "Governor: Toggle Realtime Checking"
- Keyboard: `Ctrl+Shift+Alt+G`
- Status bar: Click the Governor indicator

**Configuration:**
```json
// settings.json
{
  "governor.realtimeCheck": true,
  "governor.realtimeDelay": 500  // ms debounce
}
```

### Diagnostics

Violations appear as VS Code diagnostics:
- **Errors** (red squiggle): REJECT severity violations
- **Warnings** (yellow squiggle): WARN severity violations
- **Info** (blue squiggle): Style suggestions

Hover over a diagnostic to see details.

### Check Commands

| Command | Keyboard | Description |
|---------|----------|-------------|
| Check File | `Ctrl+Shift+G` | Check current file |
| Check Selection | — | Check selected text |
| Check Now | — | Force immediate check |

Access via Command Palette (`Ctrl+Shift+P`).

### Hover Tooltips

Hover over code to see governor context:
- **"You decided:"** — Relevant architectural decisions with Edit/Remove actions
- **"Tracked:"** — Active claims about this code
- **"You said:"** — Why this code was flagged with Fix/Change Rule/Allow Here actions

### Code Actions

Quick fixes appear as lightbulb suggestions:
- **Governor: Fix —** Attempt automatic correction (preferred action)
- **Governor: Allow here** — Suppress this check with inline comment
- **Governor: Change rule** — Modify the constraint
- **Governor: Mark as reviewed** — For security findings

### Code Autopilot (Profiles & Intent)

Quickly switch between enforcement profiles without manual configuration.

**Set Profile:**
- Command Palette: "Governor: Set Profile"
- Keyboard: `Ctrl+Shift+P Ctrl+Shift+G` (chord)
- State Panel: Click the profile button in the title bar

**Available Profiles:**

| Profile | Icon | Description |
|---------|------|-------------|
| greenfield | $(beaker) | New project, experimenting (warn only) |
| established | $(shield) | Normal development (default) |
| production | $(lock) | High-stakes changes (strict) |
| hotfix | $(flame) | Urgent targeted fix (narrow scope) |
| refactor | $(tools) | Restructuring code (soft anchors) |

**Profile Selection Flow:**
1. Select profile from QuickPick
2. For hotfix: prompted for scope pattern (e.g., `src/auth/**`)
3. Optionally provide a reason

**Status Bar:**
- Shows profile if non-default: `$(shield) Governor [hotfix]: Pass`
- Tooltip includes profile name

**Commands:**

| Command | Description |
|---------|-------------|
| Governor: Set Profile | Open profile selector |
| Governor: Clear Intent | Reset to default (established) |
| Governor: Show Intent | Show full intent + provenance in output |

### State Panel

The Activity Bar shows a Governor icon. Click it for the State Panel:

```
GOVERNOR STATE
├── Problems (2)  ← Shown first, expanded if any
│   ├── Missing evidence for claim
│   └── Hardcoded secret detected
├── Intent: HOTFIX  ← Code Autopilot section
│   ├── Profile: HOTFIX (cli)
│   ├── Scope: src/auth/**
│   ├── Timebox: 45m remaining
│   ├── Reason: fixing login bug
│   └── Overrides (1)
│       └── no-eval (30m) - migrations/**
├── Decisions (3)
│   ├── framework: React
│   ├── database: PostgreSQL
│   └── api-style: REST
├── Claims (12)
│   ├── [STABILIZED] Tests pass (0.92)
│   ├── [PROPOSED] API is RESTful (0.45)
│   └── ...
├── Evidence (3)
├── Execution
│   └── Pending: 1
├── Session
│   ├── Mode: STRICT
│   └── Authority: Balanced
├── Regime: ELASTIC
│   └── Boil: OOLONG
└── Stability
    ├── Rejection rate: 0.18
    └── Drift: NONE
```

Click items to see details.

---

## Configuration

### Settings

```json
// settings.json
{
  // Enable real-time checking
  "governor.realtimeCheck": true,

  // Debounce delay for real-time (ms)
  "governor.realtimeDelay": 500,

  // Check on file save
  "governor.checkOnSave": true,

  // Path to governor CLI
  "governor.cliPath": "governor",

  // Governor directory (relative to workspace)
  "governor.governorDir": ".governor",

  // Enable security scanning
  "governor.securityCheck": true,

  // Enable continuity checking
  "governor.continuityCheck": true
}
```

### Workspace Settings

Per-project configuration in `.vscode/settings.json`:

```json
{
  "governor.mode": "code",
  "governor.profile": "strict",
  "governor.checkOnSave": true
}
```

---

## Commands

Access via Command Palette (`Ctrl+Shift+P`):

| Command | Description |
|---------|-------------|
| Governor: Check File | Check current file for violations |
| Governor: Check Selection | Check selected text |
| Governor: Check Now | Force immediate check |
| Governor: Toggle Realtime | Enable/disable real-time checking |
| Governor: Show Output | Open governor output channel |
| Governor: Refresh State | Refresh state panel |
| Governor: Show Detail | Show details for selected item |
| Governor: Set Profile | Select enforcement profile (Code Autopilot) |
| Governor: Clear Intent | Reset to default profile |
| Governor: Show Intent | Show current intent with provenance |

---

## Keybindings

Default keybindings:

| Key | Command |
|-----|---------|
| `Ctrl+Shift+G` | Check current file |
| `Ctrl+Shift+Alt+G` | Toggle real-time checking |
| `Ctrl+Shift+P Ctrl+Shift+G` | Set profile (chord) |

Customize in `keybindings.json`:

```json
[
  {
    "key": "ctrl+alt+c",
    "command": "governor.checkFile"
  },
  {
    "key": "ctrl+alt+r",
    "command": "governor.toggleRealtime"
  },
  {
    "key": "ctrl+alt+p",
    "command": "governor.setProfile"
  }
]
```

---

## Diagnostics Deep Dive

### Severity Mapping

| Governor Severity | VS Code Severity | Appearance |
|-------------------|------------------|------------|
| REJECT | Error | Red squiggle |
| WARN | Warning | Yellow squiggle |
| INFO | Information | Blue squiggle |

### Diagnostic Structure

Each diagnostic includes:
- **Message**: What's wrong
- **Source**: "Governor" + check type
- **Code**: Anchor ID or check ID
- **Range**: Exact location in file

### Problem Panel Integration

Violations appear in the Problems panel (`Ctrl+Shift+M`):

```
PROBLEMS
  file.ts
    ⊗ [security-no-secrets] Possible hardcoded secret detected (line 15)
    ⚠ [style-no-any] Avoid 'any' type (line 23)
```

Click to jump to location.

---

## Code Actions

### Available Actions

When you hover over a diagnostic, the lightbulb offers:

**For all findings:**
- **Governor: Fix —** [description] — Attempt auto-fix (preferred action)
- **Governor: Allow here** — Add `// governor-allow: <code>` comment

**For continuity findings:**
- **Governor: Change rule** — Opens rule editing command

**For security findings:**
- **Governor: Mark as reviewed** — Add `// @security-reviewed: <code>` comment
- **Governor: Fix —** Use environment variable (for secrets)

### Suppression Comments

Add inline suppression:

```typescript
// governor-allow: style-no-any
const config: any = loadConfig();

// @security-reviewed: SEC003
const API_KEY = "sk-test-...";  // This is a documented test key
```

---

## State Panel Details

### Intent Section (Code Autopilot)

Shows current enforcement intent:
- **Profile**: Active autopilot profile (greenfield/established/production/hotfix/refactor)
- **Scope**: Path patterns where enforcement applies (if set)
- **Deny**: Path patterns explicitly forbidden (if set)
- **Timebox**: Remaining time if session is time-limited
- **Reason**: Why this intent was set
- **Overrides**: Active overrides for invariant anchors (with remaining time)

Profile icons indicate enforcement level:
- $(beaker) greenfield — experimenting
- $(shield) established — normal
- $(lock) production — strict
- $(flame) hotfix — urgent
- $(tools) refactor — restructuring

### Session Section

Shows current governor configuration:
- **Mode**: Active mode (fiction/code/nonfiction/ops)
- **Profile**: Active profile (strict/permissive/etc)
- **Uptime**: Time since governor initialized

### Regime Section

Shows operational health:
- **Status**: ELASTIC, WARM, DUCTILE, or UNSTABLE
- **Stress**: Current stress level (0-1)

### Decisions Section

Lists recorded architectural decisions:
- Click to see full decision record
- Shows supporting evidence if available

### Claims Section

Shows epistemic state:
- **SUPPORTED**: Verified claims
- **PROPOSED**: Awaiting verification
- **CONTESTED**: Conflicting evidence

### Problems Section

Active problems requiring attention (shown first in tree, expanded if any):
- Click to see full problem details
- Shows the rule breached and detail
- Icons indicate severity: info, warning, error, alert

### Execution Section

Active autonomous execution sessions:
- Session ID and status
- Budget usage
- Recent steps

---

## Integration with Governor CLI

The extension calls the governor CLI for operations:

```bash
# What the extension runs
governor check <file> --format json
governor state --json --schema v2
governor continuity anchor list --json

# Code Autopilot commands
governor intent show --json
governor intent set --profile hotfix --scope "src/**" --because "reason"
governor intent clear
governor override list --json
```

Ensure `governor` is in your PATH, or set `governor.cliPath`.

### Testing CLI Integration

```bash
# Verify CLI works
governor status

# Verify JSON output
governor state --json

# Verify check works
governor check src/example.ts --format json
```

---

## Troubleshooting

### "Governor not found"

Extension can't find the CLI.

```bash
# Check if installed
which governor

# Set explicit path in settings
{
  "governor.cliPath": "/home/user/.local/bin/governor"
}
```

### "No diagnostics appearing"

Check that:
1. Governor is initialized in workspace (`governor init`)
2. Real-time checking is enabled
3. Anchors exist (`governor continuity anchor list`)

### "State panel empty"

```bash
# Verify state command works
governor state --json

# Check for errors
governor status
```

### "Slow performance"

Increase debounce delay:

```json
{
  "governor.realtimeDelay": 1000
}
```

Or disable real-time, use manual checks:

```json
{
  "governor.realtimeCheck": false,
  "governor.checkOnSave": true
}
```

---

## Development

### Building

```bash
cd vscode-governor
npm install
npm run compile
```

### Testing

```bash
npm test
```

### Debugging

1. Open `vscode-governor` in VS Code
2. Press F5 to launch Extension Development Host
3. Set breakpoints in TypeScript source

### Architecture

```
vscode-governor/
├── src/
│   ├── extension.ts          # Entry point, command registration
│   ├── governor/
│   │   ├── client.ts         # CLI wrapper, JSON parsing
│   │   └── types.ts          # TypeScript interfaces
│   ├── views/
│   │   └── governorTree.ts   # State panel TreeDataProvider
│   └── diagnostics/
│       └── provider.ts       # DiagnosticCollection management
└── package.json              # Extension manifest
```

---

*"Your constraints, visible. Your violations, obvious."*
