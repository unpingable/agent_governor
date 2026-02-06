# Code Mode User Guide

## For Developers Who Want AI That Remembers Their Decisions

---

## What This Does (30 Seconds)

You're using Claude Code, Cursor, or Copilot. The AI:
- Hallucinates APIs that don't exist
- Contradicts architectural decisions you made yesterday
- Drifts from constraints you established
- "Passes tests" without actually running them
- Gives you no audit trail for why decisions were made

**Code Mode fixes this.**

You record decisions and constraints. The governor holds the AI to them. When it tries to contradict what you decided, it gets blocked until you resolve it.

**No receipt, no write. No proof, no commit.**

---

## Quick Start (5 Minutes)

### 1. Initialize

```bash
cd your-project
governor code init
```

### 2. Record Your First Decision

```bash
governor code decision add "REST API, not GraphQL" \
  --rationale "Simpler, team knows it, fewer dependencies"
```

### 3. Add a Constraint

```bash
governor code constraint add "No raw SQL — use the ORM"
```

### 4. Work Normally

Use your AI coding tool. When it tries to suggest GraphQL or write raw SQL, you'll see:

```
⚠️ This contradicts a decision you made

  What was suggested:
  "Let's switch to GraphQL for this endpoint"

  What you decided:
  REST API, not GraphQL (Jan 15)
  "Simpler, team knows it, fewer dependencies"

  [Redo] [Change Decision] [Allow Once]
```

### 5. Resolve and Continue

- **Redo** → AI regenerates, respecting your decision
- **Change Decision** → Your decision updates (you changed your mind)
- **Allow Once** → Exception logged, continues as-is (for legitimate exceptions)

That's it. Your architecture stays consistent.

---

## Core Concepts

### Decisions

A decision is an architectural choice you made. It persists until you explicitly change it.

**Examples:**
- "REST API, not GraphQL"
- "PostgreSQL for persistence"
- "JWT for authentication, not sessions"
- "Monorepo structure"
- "React, not Vue"

Decisions are *normative* — they say what *should* be, not what *is*.

### Constraints

A constraint is something that shouldn't happen. It's a prohibition.

**Examples:**
- "No raw SQL — use the ORM"
- "No Redux"
- "No `any` types in TypeScript"
- "No console.log in production code"
- "No direct database access from controllers"

Constraints are checked automatically. Violate one and you get blocked.

### Facts

Facts are empirical — they record what *is*, not what *should* be.

**Examples:**
- "Tests pass" (with receipt)
- "Build succeeds" (with receipt)
- "File exists at /src/auth.py" (with hash)

Facts can decay. A "tests pass" fact from last week might not be true today. The governor tracks this.

### Receipts

A receipt is cryptographic proof that something actually happened.

When the governor runs your tests, it produces a receipt:
- SHA-256 hash of test output
- Exit code
- Timestamp
- Command that was run

**The AI can't fake a receipt.** It can claim "tests pass" all it wants. Without a receipt, that claim means nothing.

### The Ledger

The ledger is your audit trail. It records:
- Every decision and when it was made
- Every fact and its evidence
- Every exception and why you allowed it
- Every change and who made it

```bash
governor code ledger --recent
```

---

## Setting Up Your Project

### Decisions to Record

Think about what you've already decided:

```bash
# Architecture
governor code decision add "Microservices, not monolith"
governor code decision add "Event-driven communication between services"

# Stack
governor code decision add "TypeScript for all new code"
governor code decision add "PostgreSQL for persistence"
governor code decision add "Redis for caching"

# Patterns
governor code decision add "Repository pattern for data access"
governor code decision add "Dependency injection, not service locators"

# API
governor code decision add "REST with OpenAPI specs"
governor code decision add "Versioned endpoints (/v1/, /v2/)"
```

Each decision can have a rationale:

```bash
governor code decision add "No ORM — raw SQL with query builders" \
  --rationale "Performance critical, team has SQL expertise, ORMs hide too much"
```

The rationale helps future-you (and the AI) understand *why*.

### Constraints to Add

Think about what you've been burned by:

```bash
# Code quality
governor code constraint add "No `any` types"
governor code constraint add "No console.log in src/"
governor code constraint add "No disabled eslint rules without comment"

# Security
governor code constraint add "No secrets in code — use env vars"
governor code constraint add "No eval() or Function()"
governor code constraint add "No innerHTML — use textContent or DOM APIs"

# Architecture
governor code constraint add "Controllers can't access database directly"
governor code constraint add "No circular dependencies between modules"
governor code constraint add "No business logic in API routes"
```

### Verification Checks

Tell the governor how to verify claims:

```bash
# Tests
governor code verify tests --command "npm test"

# Types
governor code verify types --command "npm run typecheck"

# Lint
governor code verify lint --command "npm run lint"

# Build
governor code verify build --command "npm run build"
```

Now when the AI claims "tests pass," the governor actually runs the tests and produces a receipt.

---

## Daily Workflow

### Starting Work

```bash
governor code status
```

Shows:
- Active decisions and constraints
- Any unresolved issues
- Recent verifications

### Checking Code

```bash
# Check a specific file
governor check src/api/users.py

# Check everything
governor check .

# Check and verify (run tests, types, lint)
governor code verify all
```

### When You Hit a Block

The AI suggested something that contradicts a decision:

```
⚠️ This contradicts a decision you made

  "Let's add Redux for state management"
  
  You decided: No Redux (Jan 12)
```

Your options:

1. **Redo** — "No, stick with what I decided"
2. **Change Decision** — "Actually, I've reconsidered"
3. **Allow Once** — "Exception for this specific case"

If you Allow Once, add a reason:

```bash
governor resolve allow --reason "Legacy component, will migrate later"
```

This goes in the ledger. You'll remember why.

### Recording New Decisions

As you work, you'll make new decisions. Record them:

```bash
# During a PR discussion
governor code decision add "Use Zod for runtime validation" \
  --rationale "Better TypeScript inference than Joi"

# After debugging a production issue
governor code constraint add "All API endpoints must have timeout"
```

### Viewing the Ledger

```bash
# Recent activity
governor code ledger --recent

# All decisions
governor code ledger decisions

# Search
governor code ledger search "authentication"

# Full history for a topic
governor code ledger --topic api
```

---

## Verification Deep Dive

### How It Works

1. AI claims something ("tests pass")
2. Governor runs the actual command (`npm test`)
3. Governor captures output, exit code, timing
4. Governor produces a receipt (SHA-256 hash of evidence)
5. Claim is accepted only if receipt exists

**No receipt = no write.**

### Verification Commands

```bash
# Run all configured checks
governor code verify all

# Run specific check
governor code verify tests
governor code verify types
governor code verify lint

# Run and require pass before proceeding
governor code verify all --required
```

### Custom Verifications

```bash
# Add a custom check
governor code verify custom \
  --name "security-scan" \
  --command "npm run security:check" \
  --on-fail block

# Integration tests (slower, run less often)
governor code verify custom \
  --name "integration" \
  --command "npm run test:integration" \
  --on-fail warn
```

### Verification Receipts

```bash
# View recent receipts
governor code receipts

# View specific receipt
governor code receipt show a7f3c2...

# Verify a receipt is valid
governor code receipt verify a7f3c2...
```

---

## Git Integration

### Pre-Commit Hook

```bash
governor hook install
```

Now every commit runs:
1. Check changed files against decisions/constraints
2. Verify tests pass
3. Block commit if violations exist

### Commit Messages

The governor can add decision context to commits:

```bash
governor hook install --annotate

# Commits now include:
# [governor] Respects: REST API (decision-123), No raw SQL (constraint-456)
```

### PR Integration

For CI/CD, add to your workflow:

```yaml
- name: Governor Check
  run: |
    governor check .
    governor code verify all --required
```

PRs that violate decisions or fail verification won't merge.

---

## Multi-Agent / Team Use

### Shared Decisions

Decisions live in `.governor/` and can be committed:

```bash
git add .governor/
git commit -m "Add architectural decisions"
```

Now the whole team (and all their AI tools) share the same decisions.

### Conflict Resolution

When two developers record conflicting decisions:

```bash
governor code status

⚠️ Conflict detected

  Decision A: "Use Prisma ORM" (alice, Jan 15)
  Decision B: "No ORM — raw SQL" (bob, Jan 16)

  These contradict each other. Resolve with:
    governor code decision resolve
```

### Agent Permissions

For automated agents:

```bash
# Agent can propose but not commit
governor agent register --id ci-bot --permission propose

# Agent can commit facts but not decisions
governor agent register --id test-runner --permission facts-only
```

---

## Troubleshooting

### "Governor keeps blocking things that are fine"

Your constraint might be too broad:

```bash
# See what's matching
governor code constraint show no-raw-sql --verbose

# Narrow it
governor code constraint edit no-raw-sql \
  --exclude "migrations/" \
  --exclude "scripts/"
```

### "I want to temporarily disable checks"

```bash
# Disable a specific constraint
governor code constraint disable no-console-log

# Re-enable
governor code constraint enable no-console-log

# Disable all (not recommended)
governor code pause
governor code resume
```

### "The AI claims tests pass but they don't"

That's the whole point. Without a receipt, the claim isn't trusted:

```bash
# Force verification
governor code verify tests

# See the actual result
governor code receipts --last
```

### "How do I see what decisions apply to a file?"

```bash
governor code decisions --file src/api/users.py
```

---

## VS Code Integration

If you use VS Code, install the Governor extension:

- Gutter indicators show governed code
- Inline resolution when violations occur
- Status bar shows decision/violation count
- Quick Fix menu includes Governor options

See `specs/ux/VSCODE_UX_SPEC.md` for details.

---

## WebUI Integration

If you use the WebUI:

- Decisions panel shows all recorded decisions
- Constraints panel shows all constraints
- Violations block in-chat with resolution options
- Recent panel shows verification history

See `specs/ux/WEBUI_UX_SPEC.md` for details.

---

## Philosophy

### Why External Constraint Beats Internal Alignment

Most approaches try to make the AI smarter:
- Better prompts
- More context
- Fine-tuning

**These assume:** If we make the AI better, it makes fewer mistakes.

**Governor assumes:** The AI will always make mistakes. Build a system that catches them.

This is the same philosophy as:
- Type systems (don't trust the programmer)
- TDD (don't trust your code)
- Code review (don't trust yourself)
- CI/CD (don't trust manual deploys)

**You wouldn't let untrusted code deploy without CI. Why let untrusted AI write without verification?**

### Facts vs Decisions

This distinction is critical:

| | Facts | Decisions |
|---|-------|-----------|
| Nature | Empirical (what is) | Normative (what should be) |
| Durability | Can decay | Persist until changed |
| Evidence | Requires receipts | Requires rationale |
| Source | Observation | Judgment |

The AI can observe facts. It cannot make decisions. Only you can decide.

### The Ledger Is Your Memory

Your memory is fallible. The AI's memory is worse.

The ledger is external, persistent, auditable. It remembers:
- What you decided
- Why you decided it
- When you changed your mind
- What exceptions you allowed

When you come back in 6 months, the ledger tells you what past-you was thinking.

---

## Command Reference

```bash
# Status
governor code status              # Current state
governor code decisions           # List decisions
governor code constraints         # List constraints

# Decisions
governor code decision add "..."  # Add decision
governor code decision show <id>  # Show details
governor code decision edit <id>  # Edit decision
governor code decision remove <id> # Remove decision

# Constraints
governor code constraint add "..." # Add constraint
governor code constraint show <id> # Show details
governor code constraint edit <id> # Edit constraint
governor code constraint remove <id> # Remove constraint
governor code constraint disable <id> # Temporarily disable
governor code constraint enable <id> # Re-enable

# Verification
governor code verify all          # Run all checks
governor code verify tests        # Run tests
governor code verify types        # Run type check
governor code verify lint         # Run linter
governor code receipts            # View receipts

# Ledger
governor code ledger              # Recent entries
governor code ledger decisions    # All decisions
governor code ledger facts        # All facts
governor code ledger search "..." # Search

# Resolution
governor resolve                  # Interactive resolution
governor resolve fix              # Redo to comply
governor resolve change           # Update decision
governor resolve allow            # Allow exception

# Hooks
governor hook install             # Install git hooks
governor hook remove              # Remove git hooks
```

---

*"No receipt, no write."*

*"The AI can observe facts. It cannot make decisions. Only you can decide."*

*"When you come back in 6 months, the ledger tells you what past-you was thinking."*
