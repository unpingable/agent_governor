# Code Mode User Guide

## For Developers Who Want Their AI to Remember Their Decisions

---

## What This Does (30 Seconds)

You're building software with AI assistance. The AI:
- Forgets architectural decisions you made last week
- Contradicts coding patterns you established in the codebase
- Drifts from your tech stack choices into whatever it thinks is "better"
- Makes inconsistent API design choices across files
- Forces you to re-explain your project conventions every single time

**Code Mode fixes this.**

You declare your decisions — tech stack, patterns, conventions, constraints — and the governor holds the AI to them. When the AI tries to contradict your decisions, it gets blocked until you decide what to do.

Your codebase. Your rules. AI follows, or it doesn't code.

---

## Quick Start (5 Minutes)

### 1. Initialize the Governor

```bash
cd your-project
governor init
```

This creates a `.governor/` directory for tracking decisions and anchors.

### 2. Create Your First Anchor

An anchor is a constraint the AI must respect. Create one for a technology decision:

```bash
governor continuity anchor add \
  --id "stack-react" \
  --type canon \
  --description "Frontend uses React, not Vue or Angular" \
  --forbidden-patterns "import Vue" "from 'vue'" "import { Component } from '@angular" \
  --severity reject
```

Or for a coding pattern you want enforced:

```bash
governor continuity anchor add \
  --id "no-any-types" \
  --type prohibition \
  --description "No 'any' types in TypeScript code" \
  --forbidden-patterns ": any" "as any" "<any>" \
  --severity reject
```

For security rules that should **never** be bypassed by profile settings, mark them as invariant:

```bash
governor continuity anchor add \
  --id "no-eval" \
  --type prohibition \
  --description "Never use eval() - security risk" \
  --forbidden-patterns "eval(" \
  --severity reject \
  --class invariant
```

### 3. Start Coding

Use the WebUI, Claude Code with hooks, or the CLI wrapper. When the AI tries to use Vue or sneak in `any` types, you'll see:

```
[Governor] Blocked — choose an action:
  • [stack-react] Forbidden pattern found: "import Vue"

1. Fix — Generate compliant patch
2. Revise — Update decision record
3. Proceed — Record waiver

Reply with 1, 2, 3 or: fix | revise | proceed
```

### 4. Resolve and Continue

- Type **1** or **fix** → AI regenerates code that respects your decisions
- Type **2** or **revise** → Decision record updates (you changed your mind)
- Type **3** or **proceed** → Waiver logged, continues as-is (intentional exception)

That's it. Your codebase stays consistent.

---

## Code Autopilot (Profiles & Intent)

Instead of configuring enforcement settings manually, declare *what you're doing* and let the system configure itself.

### Setting Your Intent

```bash
# Quick: set profile for your session
governor code --profile hotfix --scope "src/auth/**" --timebox 90 --because "fixing login bug"

# Or use the full command
governor intent set --profile hotfix --scope "src/auth/**" --timebox 90 --because "fixing login bug"

# Check current state
governor code --status
governor intent show
```

### Profiles

| Profile | Violations | Scope | Use Case |
|---------|------------|-------|----------|
| `greenfield` | Warn only | Unlimited | New projects, experiments |
| `established` | Block | Unlimited | Normal development (default) |
| `production` | Block + evidence | Limited (20 files) | Critical paths, releases |
| `hotfix` | Block outside, warn inside | Narrow | Urgent targeted fixes |
| `refactor` | Warn | Unlimited | Restructuring, cleanup |

### Profile Behavior

**greenfield** — Maximum freedom for exploration
- Violations produce warnings, not blocks
- No evidence requirements
- No file count limits
- Soft anchor enforcement (preferences only)

**established** — Balanced development (default)
- Violations block until resolved
- Tests required before commit
- Scope warnings but not enforced

**production** — High-stakes changes
- All violations block
- Tests + static analysis + review required
- Max 20 files per change
- Hard anchor enforcement
- Human approval required for commits

**hotfix** — Urgent targeted fixes
- Violations BLOCK outside scope, WARN inside scope
- Narrowly scoped (must specify `--scope`)
- Timebox enforced (expires after duration)
- Zero exploration budget

**refactor** — Restructuring code
- Violations warn but don't block
- Soft anchor enforcement
- Higher exploration budget

### Branch Heuristics

The system can suggest profiles based on your git branch:

| Branch Pattern | Suggested Profile | Auto-Apply |
|----------------|-------------------|------------|
| `main`, `master` | production | No (too risky) |
| `hotfix/*`, `fix/*` | hotfix | No (too risky) |
| `feature/*` | established | Yes |
| `wip/*`, `experiment/*` | greenfield | Yes |
| `refactor/*` | refactor | Yes |

```bash
# See what's suggested for current branch
governor intent show
```

### Overrides for Invariant Constraints

Some anchors are marked as **invariant** (can't be disabled by profile). For these, you can create time-limited, scoped overrides:

```bash
# Check which anchors are invariant
governor continuity anchor list

# Create a 2-hour override for migrations
governor override create \
  --anchor no-sql-injection \
  --scope "migrations/**" \
  --expires 2h \
  --because "Legacy data migration requires raw SQL"

# List active overrides
governor override list

# Revoke early when done
governor override revoke abc123 --because "Migration complete"
```

Overrides are:
- **Scoped** — Only apply to specific paths
- **Expiring** — Auto-expire after duration
- **Receipted** — Logged with reason, operator, timestamp
- **Revocable** — Can be ended early

### Intent Resolution

Intent is resolved from multiple layers (first match wins):

1. **CLI override** (`--profile hotfix`)
2. **Environment variable** (`GOV_PROFILE=hotfix`)
3. **Session state** (`.git/governor/intent.json`)
4. **Repo config** (`.governor.toml` `[defaults]`)
5. **Branch heuristic** (suggestion only for high-risk)
6. **System default** (`established`)

```bash
# See full provenance chain
governor intent show --json
```

---

## Core Concepts

### Anchors

An anchor is a constraint that must remain true in your codebase.

**Anchor types:**

| Type | What It Does | Example |
|------|--------------|---------|
| `canon` | Established decisions that must hold | "We use React for frontend" |
| `prohibition` | Patterns that must NOT appear | "No console.log in production code" |
| `definition` | Terms/APIs must be used consistently | "User ID is always a UUID string" |
| `requirement` | Patterns that MUST appear | "All API endpoints return JSON" |
| `style` | Code style constraints | "Use arrow functions for callbacks" |

### Violations

A violation happens when the AI output contradicts an anchor.

**Severity levels:**

| Level | What Happens |
|-------|--------------|
| `warn` | You see a warning, but output continues |
| `correct` | System attempts automatic correction |
| `reject` | Output blocked until you resolve it |

Most anchors should use `reject` because the whole point is to catch problems.

### Resolution Options

When something gets blocked, you have three choices:

| Option | When to Use | What Happens |
|--------|-------------|--------------|
| **Fix** | AI made a mistake | AI regenerates, respecting the anchor |
| **Revise** | You're changing the decision | Anchor updates to new reality |
| **Proceed** | Intentional deviation | Exception logged, output allowed |

**Proceed** is for things like:
- Legacy code that hasn't been migrated yet
- Third-party code you can't change
- Temporary workarounds with a plan to fix
- Experiments in a feature branch

The exception gets logged so you remember *why* you broke the rule.

---

## Setting Up Your Project

### Technology Stack

```bash
# Frontend framework
governor continuity anchor add \
  --id "stack-frontend" \
  --type canon \
  --description "Frontend: React 18 with TypeScript" \
  --forbidden-patterns "import Vue" "from 'vue'" "angular" "import Svelte" \
  --severity reject

# Backend framework
governor continuity anchor add \
  --id "stack-backend" \
  --type canon \
  --description "Backend: Python FastAPI" \
  --forbidden-patterns "from flask" "from django" "express(" \
  --severity reject

# Database
governor continuity anchor add \
  --id "stack-database" \
  --type canon \
  --description "Database: PostgreSQL via SQLAlchemy" \
  --forbidden-patterns "import pymongo" "from motor" "import mysql" \
  --severity reject
```

### Coding Patterns

```bash
# Error handling
governor continuity anchor add \
  --id "pattern-errors" \
  --type requirement \
  --description "All API endpoints must have try/except with proper error responses" \
  --forbidden-patterns "raise Exception(" \
  --severity warn

# No magic strings
governor continuity anchor add \
  --id "pattern-no-magic" \
  --type prohibition \
  --description "Use constants/enums, not magic strings" \
  --forbidden-patterns '"admin"' '"user"' '"pending"' '"approved"' \
  --severity warn
```

### Security Constraints

```bash
# No hardcoded secrets
governor continuity anchor add \
  --id "security-no-secrets" \
  --type prohibition \
  --description "No hardcoded API keys, passwords, or secrets" \
  --forbidden-patterns "api_key = \"" "password = \"" "secret = \"" "token = \"" \
  --severity reject

# SQL injection prevention
governor continuity anchor add \
  --id "security-sql" \
  --type prohibition \
  --description "No string formatting in SQL queries" \
  --forbidden-patterns "f\"SELECT" "f'SELECT" '% "SELECT' "+ \"SELECT" \
  --severity reject
```

### API Design

```bash
# RESTful conventions
governor continuity anchor add \
  --id "api-rest" \
  --type style \
  --description "REST endpoints: plural nouns, no verbs in paths" \
  --forbidden-patterns "/getUser" "/createItem" "/deleteRecord" \
  --severity warn

# Consistent response format
governor continuity anchor add \
  --id "api-response" \
  --type requirement \
  --description "All API responses include 'data' and 'error' fields" \
  --severity warn
```

---

## Managing Decisions Over Time

### Viewing Your Anchors

```bash
# List all anchors
governor continuity anchor list

# See details of one
governor continuity anchor show stack-frontend
```

### Removing Anchors

When decisions change:

```bash
# Remove an anchor (e.g., migrating to a new framework)
governor continuity anchor remove stack-frontend
```

### Viewing Exceptions

See all the times you deliberately broke the rules:

```bash
governor lite exceptions
```

This shows:
- What anchor was violated
- What you chose (proceed)
- When it happened
- The scope of the exception

Useful for: tech debt tracking, migration progress, finding code that needs cleanup.

---

## Integration Points

### With Git Hooks

```bash
# Install pre-commit hook
governor hook install

# Check staged changes before commit
governor hook pre-commit --interactive --mode code
```

### With Claude Code

```bash
# Install Claude hooks
governor claude-hooks install

# Wrap Claude Code execution
governor wrap --interactive --mode code -- claude "implement login endpoint"
```

### With the WebUI

```bash
# Start the WebUI (uses your Claude Max subscription)
docker-compose -f docker-compose.yml -f docker-compose.claude-code.yml up -d
```

Open **http://localhost:3001** and select "Code Mode" from the settings.

---

## Workflow Tips

### Start with Critical Decisions

You don't need to anchor everything. Focus on:

1. **Tech stack choices** — Framework, language, database
2. **Security constraints** — What must never happen
3. **Breaking patterns** — Things that cause bugs or tech debt

Add more anchors as you notice AI drift.

### Use Warnings for Preferences

Not everything needs to block. For "nice to have" patterns:

```bash
governor continuity anchor add \
  --id "style-prefer-const" \
  --type style \
  --description "Prefer const over let when possible" \
  --forbidden-patterns "let " \
  --severity warn
```

This warns you but doesn't block. Good for guidelines you sometimes ignore.

### Import from Existing Rules

Have ESLint, Prettier, or other config? Create anchors from them:

```json
{
  "anchors": [
    {
      "id": "lint-no-console",
      "anchor_type": "prohibition",
      "description": "No console.log (use logger instead)",
      "forbidden_patterns": ["console.log", "console.warn", "console.error"],
      "severity": "warn"
    }
  ]
}
```

Then import:
```bash
governor continuity import anchors.json
```

---

## Common Scenarios

### "The AI keeps using the wrong library"

Add a prohibition anchor:

```bash
governor continuity anchor add \
  --id "lib-dates" \
  --type canon \
  --description "Use date-fns for date handling, not moment.js" \
  --forbidden-patterns "import moment" "from 'moment'" "require('moment')" \
  --severity reject
```

### "The AI generates inconsistent API responses"

Add a requirement anchor:

```bash
governor continuity anchor add \
  --id "api-format" \
  --type requirement \
  --description "All API responses must use ApiResponse wrapper" \
  --required-patterns "ApiResponse" \
  --severity warn
```

### "The AI uses deprecated patterns"

Prohibition anchor:

```bash
governor continuity anchor add \
  --id "no-deprecated" \
  --type prohibition \
  --description "Don't use deprecated React lifecycle methods" \
  --forbidden-patterns "componentWillMount" "componentWillReceiveProps" "componentWillUpdate" \
  --severity reject
```

### "The AI keeps adding dependencies we don't want"

```bash
governor continuity anchor add \
  --id "no-lodash" \
  --type prohibition \
  --description "No lodash — use native methods or our utils" \
  --forbidden-patterns "import _ from 'lodash'" "from 'lodash'" "require('lodash')" \
  --severity reject
```

### "I want to turn off governance for a prototype"

Disable specific anchors:

```bash
# View pending violations
governor lite pending

# Log as exception and continue
governor lite proceed --scope session
```

Or use the permissive profile:

```bash
governor profile use permissive
```

---

## The Philosophy

Code Mode isn't about making AI "better at coding."

It's about making AI **respect your authority over your own codebase**.

You're the architect. You decide what technologies, patterns, and conventions matter. The AI is a tool that helps you code — but it doesn't get to overwrite your decisions.

When you declare an anchor, you're saying: "This is how we do things here. This matters."

When the AI contradicts it, you decide:
- **Fix**: "No, that's wrong, try again"
- **Revise**: "Actually, I'm changing this decision"
- **Proceed**: "I'm breaking this rule on purpose"

All three are valid. The point is that *you* decide, not the AI.

**Your codebase. Your rules.**

---

## CLI Reference

```bash
# Autopilot (profiles and intent)
governor code --profile <name> --scope "..." --timebox 90 --because "reason"
governor code --status              # Show current autopilot state
governor intent show                # Resolved intent with provenance
governor intent set --profile <name> [--scope ...] [--timebox N] [--because "..."]
governor intent clear               # Clear session intent

# Override management (for invariant anchors)
governor override create --anchor <id> --scope "..." --expires 2h --because "reason"
governor override list              # List active overrides
governor override show <id>         # Override details
governor override revoke <id> --because "reason"
governor override cleanup           # Remove expired

# Anchor management
governor continuity anchor add --id <id> --type <type> --description <desc> [--forbidden-patterns ...] [--required-patterns ...] [--severity warn|correct|reject] [--class invariant|preference]
governor continuity anchor upgrade <id> --class invariant  # Upgrade constraint class
governor continuity anchor list
governor continuity anchor show <id>
governor continuity anchor remove <id>
governor continuity check <text>
governor continuity import <file>

# Violation resolution
governor lite pending          # View pending violation
governor lite fix              # Regenerate compliant
governor lite revise           # Update the anchor
governor lite proceed          # Log exception and continue
governor lite exceptions       # View logged exceptions

# Integration
governor check <file> --interactive --mode code
governor wrap --interactive --mode code -- <command>
governor hook pre-commit --interactive --mode code

# System status
governor continuity status
governor status
```

---

*"The AI is a tool. You are the architect. Don't let it forget that."*
