# Ops Mode User Guide

## For SREs Who Want Their AI to Follow the Runbook

---

## What This Does (30 Seconds)

You're managing infrastructure with AI assistance. The AI:
- Suggests changes outside maintenance windows
- Proposes actions with unbounded blast radius
- Skips precondition checks you've defined
- Forgets the runbook steps you've established
- Makes changes without verifying rollback capability

**Ops Mode fixes this.**

You declare your operational constraints — runbooks, time windows, blast radius limits, precondition chains — and the governor enforces them. When the AI tries to make changes outside your operational boundaries, it gets blocked.

Your infrastructure. Your procedures. AI follows the runbook, or it doesn't execute.

---

## Quick Start (5 Minutes)

### 1. Initialize the Governor

```bash
cd your-ops-project
governor init
```

### 2. Define a Runbook

```bash
ops-gov runbook add \
  --id "db-migration" \
  --name "Database Migration Procedure" \
  --steps "backup" "validate-schema" "apply-migration" "verify" "announce"
```

### 3. Set Time Windows

```bash
ops-gov window add \
  --id "maintenance" \
  --name "Weekly Maintenance Window" \
  --schedule "Sunday 02:00-06:00 UTC" \
  --allowed-actions "db-migration" "deploy" "restart"
```

### 4. Define Blast Radius Limits

```bash
ops-gov blast-radius add \
  --id "prod-limit" \
  --environment "production" \
  --max-instances 10 \
  --max-percentage 25 \
  --requires-approval-above 5
```

### 5. Create Precondition Chains

```bash
ops-gov precondition add \
  --id "deploy-checks" \
  --action "deploy" \
  --requires "tests-pass" "staging-verified" "rollback-tested"
```

Now when AI suggests a production deploy at 3pm on a Tuesday without running tests:

```
[Governor] Blocked — operational constraint violated:
  • [maintenance] Action "deploy" not allowed outside maintenance window
  • [deploy-checks] Missing preconditions: tests-pass, staging-verified

1. Fix — Regenerate compliant action plan
2. Revise — Update operational constraints
3. Proceed — Log as emergency exception

Reply with 1, 2, 3 or: fix | revise | proceed
```

---

## Core Concepts

### Runbooks

A runbook is a sequence of steps that must be followed for an operation.

```bash
ops-gov runbook add \
  --id "incident-response" \
  --name "Production Incident Response" \
  --steps "acknowledge" "assess" "mitigate" "communicate" "resolve" "postmortem"
```

The governor ensures AI follows the steps in order and doesn't skip any.

### Time Windows

A time window defines when certain actions are permitted.

```bash
ops-gov window add \
  --id "change-freeze" \
  --name "Holiday Change Freeze" \
  --schedule "2024-12-20 to 2025-01-02" \
  --blocked-actions "deploy" "migrate" "upgrade"
```

Actions outside the window are blocked.

### Blast Radius

Blast radius limits constrain the scope of changes.

```bash
ops-gov blast-radius add \
  --id "canary-deploy" \
  --max-instances 2 \
  --max-percentage 5 \
  --cooldown-minutes 30
```

The governor prevents changes that exceed these limits.

### Preconditions

Precondition chains ensure dependencies are satisfied before actions.

```bash
ops-gov precondition add \
  --id "prod-deploy" \
  --action "deploy-production" \
  --requires "deploy-staging" "smoke-tests" "load-tests" "security-scan"
```

The action is blocked until all preconditions are verified.

---

## Setting Up Your Operations

### Deployment Pipeline

```bash
# Staging must happen before production
ops-gov precondition add \
  --id "deploy-order" \
  --action "deploy-production" \
  --requires "deploy-staging" "staging-smoke-test"

# Production deploys limited to 25% at a time
ops-gov blast-radius add \
  --id "prod-rollout" \
  --environment "production" \
  --max-percentage 25 \
  --cooldown-minutes 15

# Only during maintenance windows
ops-gov window add \
  --id "deploy-window" \
  --schedule "Tuesday,Thursday 14:00-18:00 UTC" \
  --allowed-actions "deploy-production"
```

### Database Operations

```bash
# Migration runbook
ops-gov runbook add \
  --id "db-migrate" \
  --steps "backup" "test-migration-staging" "announce-maintenance" \
         "apply-migration" "verify-data" "update-docs"

# Backup verification required
ops-gov precondition add \
  --id "migrate-safety" \
  --action "apply-migration" \
  --requires "backup-verified" "rollback-script-tested"
```

### Incident Response

```bash
# Incident runbook
ops-gov runbook add \
  --id "incident" \
  --steps "acknowledge-page" "open-bridge" "assess-impact" \
         "identify-cause" "implement-mitigation" "verify-resolution" \
         "communicate-status" "schedule-postmortem"

# Severity determines response time
ops-gov policy add \
  --id "sev1-response" \
  --trigger "severity=1" \
  --max-response-minutes 15 \
  --requires-roles "incident-commander" "subject-matter-expert"
```

### Change Management

```bash
# Change freeze periods
ops-gov window add \
  --id "freeze-holidays" \
  --schedule "December 15 - January 5" \
  --blocked-actions "deploy" "migrate" "upgrade" "scale-down"

ops-gov window add \
  --id "freeze-earnings" \
  --schedule "Q1-earnings-week, Q2-earnings-week, Q3-earnings-week, Q4-earnings-week" \
  --blocked-actions "deploy" "migrate"

# Emergency override requires approval
ops-gov policy add \
  --id "freeze-override" \
  --requires-approval "vp-engineering" \
  --audit-trail required
```

---

## Verification Flow

### Checking an Action

```bash
# Verify action is permitted
ops-gov verify action "deploy to production"

# Check with specific context
ops-gov verify action "restart database" \
  --environment production \
  --time "2024-03-15T15:00:00Z"
```

### Checking Runbook Compliance

```bash
# Verify steps are being followed
ops-gov verify runbook "db-migrate" \
  --completed-steps "backup" "test-migration-staging"

# See what's next
ops-gov runbook next "db-migrate"
```

### Checking Preconditions

```bash
# See what's required
ops-gov precondition check "deploy-production"

# Mark a precondition as satisfied
ops-gov precondition satisfy "staging-smoke-test" \
  --evidence "https://ci.example.com/runs/12345"
```

---

## Integration

### With CI/CD Pipelines

```bash
# In your deployment script
if ! ops-gov verify action "deploy-production" --environment prod; then
  echo "Deployment blocked by operational constraints"
  exit 1
fi
```

### With ChatOps

```bash
# Wrap your bot commands
governor wrap --mode ops -- chatbot deploy production
```

### With the WebUI

```bash
docker-compose up -d
```

Select "Ops Mode" for operational workflows.

---

## Common Scenarios

### "AI suggests a 3am deploy on a weekday"

Time window catches it:

```bash
ops-gov window add \
  --id "business-hours-only" \
  --schedule "Monday-Friday 09:00-17:00 local" \
  --allowed-actions "deploy" "migrate"
```

### "AI wants to deploy to all instances at once"

Blast radius limits:

```bash
ops-gov blast-radius add \
  --id "gradual-rollout" \
  --max-percentage 10 \
  --cooldown-minutes 30 \
  --require-health-check true
```

### "AI skips the backup step"

Runbook enforcement:

```bash
ops-gov runbook add \
  --id "deploy-with-backup" \
  --steps "backup" "deploy" "verify" \
  --strict true  # Cannot skip steps
```

### "Emergency change during freeze"

Proceed with audit:

```bash
# When blocked during freeze
governor lite proceed \
  --scope "emergency-change-12345" \
  --reason "P1 incident requires immediate fix" \
  --approved-by "vp-engineering"
```

The exception is logged with full audit trail.

---

## The Philosophy

Ops Mode isn't about making AI "better at operations."

It's about making AI **follow your operational procedures**.

You're the operator. You've defined runbooks for a reason. Time windows exist for a reason. Blast radius limits exist for a reason. The AI is a tool that helps you operate — but it doesn't get to skip steps or ignore constraints.

When you define a runbook, you're saying: "This is the procedure. These steps matter."

When the AI tries to shortcut it, you decide:
- **Fix**: "No, follow the runbook"
- **Revise**: "Actually, updating the procedure"
- **Proceed**: "Emergency override, logging for audit"

All three are valid. The point is that *you* control the blast radius, not the AI.

**Your infrastructure. Your procedures.**

---

## CLI Reference

```bash
# Runbooks
ops-gov runbook add --id <id> --name <name> --steps <step1> <step2> ...
ops-gov runbook list
ops-gov runbook show <id>
ops-gov runbook next <id>
ops-gov runbook remove <id>

# Time windows
ops-gov window add --id <id> --schedule <schedule> --allowed-actions <actions>
ops-gov window list
ops-gov window show <id>
ops-gov window active  # Show currently active windows

# Blast radius
ops-gov blast-radius add --id <id> --max-instances <n> --max-percentage <p>
ops-gov blast-radius list
ops-gov blast-radius check <action>

# Preconditions
ops-gov precondition add --id <id> --action <action> --requires <prereqs>
ops-gov precondition check <action>
ops-gov precondition satisfy <prereq> --evidence <url>

# Verification
ops-gov verify action <action> [--environment <env>] [--time <time>]
ops-gov verify runbook <id> --completed-steps <steps>

# Policy
ops-gov policy list
ops-gov policy show <id>

# Resolution
governor lite pending
governor lite fix
governor lite revise
governor lite proceed --reason <reason> --approved-by <approver>
governor lite exceptions
```

---

*"The AI is a tool. You are the operator. The runbook is the law."*
