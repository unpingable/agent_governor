# GOV_GAP_SCHEDULED_TASKS_001: Cron for Governed Agents

## Status
Proposed (v3, daemon-side)

## Summary
Scheduled task execution for governed agents. The daemon runs agent
tasks on a cron-like schedule — nightly test sweeps, weekly repo audits,
periodic anchor checks — producing receipts and building temporal
baselines for drift detection, regime analysis, and coverage tracking.

Not "background chat." **Recurring governed observations over time.**

## Why This Matters

Governor's temporal machinery (drift detection, regime signals, claim
diff, staleness tracking) is currently fed per-session data. Scheduled
tasks produce **longitudinal data** — the same observations repeated
over time, building baselines that make drift, decay, and coverage
changes visible.

A single session shows you a snapshot. A month of nightly runs shows
you a trend.

## Use Cases

### Observation / baseline tasks
- Nightly test suite run → receipt chain, pass/fail trend
- Weekly repo health audit → security scan, stale fact detection, anchor coverage
- Periodic `governor drift update` → temporal asymmetry baseline
- Daily `governor regime status` → regime stability over time
- Scheduled `governor correlator status` → capture indicator trends

### Maintenance tasks
- `governor decay` on schedule → stale fact cleanup
- `governor scar anneal` with fresh evidence → periodic scar relaxation
- `governor context cleanup` → recovery store hygiene
- Receipt retention enforcement → purge expired blobs

### Agent tasks (requires daemon runtime)
- "Summarize what changed in the repo this week" → scheduled agent with
  read-only scope, receipted output
- "Run the grounding audit on all SUPPORTED claims" → periodic
  hallucination detection sweep
- "Check all external bindings for discrepancies" → Wikidata/DOI freshness

## Design Shape

### Task definition
```
scheduled_task:
  id: "nightly-tests"
  schedule: "0 2 * * *"          # cron syntax
  command: "governor wrap --receipt-out .governor/scheduled/ --ci-kind unit_tests -- pytest tests/ -v"
  scope:
    max_duration: 600s
    max_token_budget: 0          # zero = no LLM, pure CLI
    worktree: false
  on_failure: receipt            # always emit receipt, even on failure
  retention: 90d                 # keep receipts for 90 days
```

### Agent task definition
```
scheduled_task:
  id: "weekly-repo-summary"
  schedule: "0 9 * * 1"         # Monday 9am
  agent:
    backend: claude-code
    identity: "You are a repo auditor. Summarize changes since last Monday."
    scope:
      read_only: true
      max_turns: 20
      max_tokens: 50000
  on_failure: receipt
  retention: 30d
```

### What the daemon manages
- Schedule evaluation (cron parser, next-run tracking)
- Process lifecycle (spawn, supervise, timeout, kill)
- Receipt emission (every run produces a receipt, pass or fail)
- Result storage (receipts + artifacts, retention-managed)
- Event stream (scheduled task events visible in Maude)

### What it does NOT manage
- Complex task DAGs (that's the planner/archboard layer, later)
- Multi-agent coordination (that's swarm orchestration, later)
- Approval flows (scheduled tasks are pre-authorized by definition)

## Temporal Baseline Value

The receipts from scheduled tasks feed directly into:

| Module | What scheduled data provides |
|---|---|
| `drift.py` | Repeated observations → drift baseline, trend detection |
| `regime.py` | Periodic signal snapshots → regime stability over time |
| `correlator_telemetry.py` | Regular K-vector samples → capture trend analysis |
| `claim_diff.py` | Periodic ledger snapshots → confidence drift, evidence erosion trends |
| `scars.py` | Repeated test runs → scar anneal evidence, failure recurrence data |
| `ci.py` | Receipted test runs → CI-grade evidence chain over time |
| `signal_store.py` | Regular signal emission → richer preflight predictions |

This is where governor's temporal thesis actually gets tested against
real longitudinal data instead of single-session snapshots.

## Relationship to Existing Infrastructure

- `governor wrap` already does receipt-producing command execution
- `governor ci verify` already does policy checking on receipt bundles
- The daemon already manages process lifecycle
- Receipt kernel already does append-only hash-chained storage
- Signal store already does time-series projection over JSONL

Scheduled tasks are mostly **glue** — connecting existing pieces on a
timer.

## Minimum Viable Shape

1. Cron-syntax schedule parser
2. Task config (YAML or JSON, in `.governor/scheduled/`)
3. Process spawn + supervise + timeout
4. Receipt emission per run
5. Simple persistence (last run time, next run time, last result)
6. CLI: `governor scheduled list`, `governor scheduled run <id>`,
   `governor scheduled history <id>`

No agent tasks in v1. Just governed CLI commands on a schedule. Agent
tasks come when the daemon runtime exists.

## What This Is NOT

- Not a CI system (no pipeline DAGs, no artifact promotion)
- Not a task queue (no distributed workers, no retry backoff)
- Not ChatGPT's scheduled tasks (those are reminder-shaped, these are
  observation-shaped)
- Not autonomous execution (tasks are pre-authorized, scoped, budgeted)

## The Short Version

> Cron for governed agents. Every run produces a receipt. The receipts
> build temporal baselines. The baselines make drift visible.

## References
- `src/governor/ci.py` — receipt-producing command wrapper
- `src/governor/daemon.py` — process lifecycle management
- `src/governor/drift.py` — temporal asymmetry defense
- `src/governor/regime.py` — regime signal tracking
- `libs/receipt_kernel/` — append-only receipt storage
- `specs/gaps/GOV_GAP_SWARM_ORCHESTRATION_001.md` — larger orchestration context
