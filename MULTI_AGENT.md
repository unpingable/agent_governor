# Multi-Agent Specification

## Core Principle

**Agents don't talk to each other. They talk to the ledger.**

The ledger is the coordination substrate. Agents are stateless workers. Orchestration is external (your job). The governor constrains; it doesn't coordinate.

This is not Gas Town. There's no Mayor. There's no emergent consensus. There's shared ground truth with transactional commits and deterministic conflict rules.

---

## Concurrency Model

### Storage Backend

The ledger uses SQLite with WAL mode for concurrent access:

```
.governor/
├── governor.db          # SQLite database (WAL mode)
├── receipts/            # Receipt blobs (content-addressed)
└── config.toml
```

Why SQLite:
- ACID transactions out of the box
- Multiple readers, single writer (WAL mode)
- No external dependencies
- File-based = git-trackable schema, portable

### Transaction Semantics

Every proposal goes through a transaction:

```python
def propose(claim: Claim, pointers: list[str]) -> ProposalResult:
    with db.transaction():
        # 1. Check conflicts against current state
        conflicts = check_conflicts(claim)
        if conflicts:
            return Rejection(conflicts)
        
        # 2. Acquire lease on affected resources
        lease = acquire_lease(claim.scope)
        if not lease:
            return Rejection("resource locked by another agent")
        
        # 3. Run verification, produce receipts
        receipts = verify(claim, pointers)
        if not receipts:
            return Rejection("verification failed")
        
        # 4. Atomic commit
        commit(claim, receipts)
        release_lease(lease)
        return Committed(claim.id)
```

Key invariant: **No partial commits.** Either the whole proposal lands or nothing does.

### Locking Model

Resources are locked at the *scope* level during verification:

| Claim Type | Lock Scope |
|------------|------------|
| `DECISION` | `decisions/{topic}` |
| `FILE_EXISTS` | `facts/files/{path}` |
| `CHANGESET` | `facts/files/{path}` for each touched file |
| `TESTS_PASS` | `facts/tests/{command_hash}` |

Locks are leases with TTL (default 5 minutes). If an agent dies mid-verification, the lease expires and another agent can proceed.

```sql
CREATE TABLE leases (
    scope TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    acquired_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
```

---

## Conflict Detection

### Conflict Classes

| Class | Detection | Resolution |
|-------|-----------|------------|
| **Decision conflict** | Same topic, different choice | Hard reject. Human must revise existing decision first. |
| **Fact contradiction** | Same assertion, different receipt | Newer receipt wins (facts can be re-verified). |
| **Changeset collision** | Overlapping file paths | Hard reject. First-committed wins. |
| **Stale base** | Changeset based on outdated tree hash | Hard reject. Agent must rebase. |

### Namespace + Keying

Decisions are keyed by topic:
```
decisions/framework = {choice: "react", epoch: 3, ...}
decisions/api_style = {choice: "rest", epoch: 1, ...}
```

Facts are keyed by assertion type + identifier:
```
facts/files/src/api.py = {blob_hash: "abc123", epoch: 7, ...}
facts/tests/pytest:-q = {exit_code: 0, epoch: 12, ...}
```

### Epochs

Every ledger entry has an epoch (monotonic counter). This enables:
- **Optimistic concurrency**: "Update X if epoch = N" 
- **Staleness detection**: Agent's view of state vs current epoch
- **Audit trail**: Which version of truth was current when

```sql
CREATE TABLE decisions (
    topic TEXT PRIMARY KEY,
    choice TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    supersedes_epoch INTEGER,  -- if this revises a prior decision
    receipt_id TEXT NOT NULL
);
```

---

## Coordination as State

Agents don't message each other, but they can signal via ledger entries.

### Work Reservations

Before starting expensive work, an agent can claim a task:

```python
class ClaimType(Enum):
    # ... existing types ...
    WORK_RESERVATION = "work_reservation"  # "I'm working on X"

@dataclass
class WorkReservation:
    task: str              # "implementing /users endpoint"
    scope: list[str]       # files/paths this will touch
    agent_id: str
    started_at: datetime
    eta_minutes: int | None
```

Other agents query reservations before proposing overlapping work:

```python
def should_start_task(task_scope: list[str]) -> bool:
    active = query_reservations(scope_overlaps=task_scope)
    if active:
        # Someone's already on it
        return False
    # Claim it
    propose(Claim(type=ClaimType.WORK_RESERVATION, scope=task_scope))
    return True
```

Reservations expire (default 30 min) or are released on commit/abandon.

### Intent Records

For longer-running work, agents can declare intent without locking:

```python
class ClaimType(Enum):
    # ... existing types ...
    INTENT = "intent"  # "I plan to do X" (advisory, no lock)
```

Intents are visible to other agents and to humans. They're advisory - they don't block, but they help avoid duplicate work.

---

## Agent Permissions

### Permission Model

```toml
# .governor/config.toml

[permissions.default]
# Default for unspecified agents
can_propose_decisions = false
can_propose_changesets = true
can_propose_facts = true
max_files_per_changeset = 10
allowed_paths = ["src/**", "tests/**"]
denied_paths = [".governor/**", "*.toml", ".github/**"]

[permissions.architect]
# For architecture/design agents (e.g., Claude)
can_propose_decisions = true
can_propose_changesets = true
allowed_decision_topics = ["framework", "api_style", "database", "auth"]

[permissions.implementer]
# For code generation agents (e.g., Codex)
can_propose_decisions = false
can_propose_changesets = true
max_files_per_changeset = 20
allowed_paths = ["src/**", "tests/**", "docs/**"]

[permissions.docs]
# For documentation agents
can_propose_decisions = false
can_propose_changesets = true
allowed_paths = ["docs/**", "*.md"]
denied_paths = ["CLAUDE.md", ".governor/**"]
```

### Scope Enforcement

Every proposal is checked against the agent's permissions:

```python
def check_permissions(agent_id: str, claim: Claim) -> bool:
    perms = get_permissions(agent_id)
    
    if claim.type == ClaimType.DECISION:
        if not perms.can_propose_decisions:
            return False
        if claim.topic not in perms.allowed_decision_topics:
            return False
    
    if claim.type == ClaimType.CHANGESET:
        for path in claim.paths_touched:
            if not matches_glob(path, perms.allowed_paths):
                return False
            if matches_glob(path, perms.denied_paths):
                return False
        if len(claim.paths_touched) > perms.max_files_per_changeset:
            return False
    
    return True
```

### Blast Radius Limits

No agent can:
- Modify `.governor/**` (governor config/state)
- Modify CI/CD config unless explicitly allowed
- Touch more than `max_files_per_changeset` in one proposal
- Propose decisions outside their topic whitelist

---

## Dispatcher Protocol

Orchestration is external. The governor provides a thin protocol for dispatchers.

### Agent Registration

```python
# Agent announces itself on startup
governor agent register \
    --id "codex-worker-1" \
    --class "implementer" \
    --capabilities "changeset,fact"

# Returns agent's effective permissions
{
    "agent_id": "codex-worker-1",
    "permissions": { ... },
    "lease_ttl_seconds": 300
}
```

### Task Claiming

```python
# Dispatcher assigns task, agent claims it
governor task claim \
    --agent-id "codex-worker-1" \
    --task "implement /users endpoint" \
    --scope "src/api/users.py,tests/test_users.py"

# Returns claim status
{
    "claimed": true,
    "lease_expires": "2025-01-19T04:30:00Z"
}
```

### Heartbeat

```python
# Agent pings to extend lease while working
governor task heartbeat --agent-id "codex-worker-1" --task-id "abc123"
```

### Completion

```python
# Agent completes task (triggers proposal flow)
governor task complete \
    --agent-id "codex-worker-1" \
    --task-id "abc123" \
    --proposal-id "def456"
```

---

## Putting It Together

### Example: Two Agents, One Repo

```
Human: "Add a /users endpoint with tests"

Dispatcher:
  1. Queries decisions ledger → api_style=rest, framework=fastapi
  2. Creates subtasks:
     - "implement /users endpoint" → assigns to Codex
     - "write tests for /users" → assigns to Codex (after #1)
  
Codex Worker 1:
  1. Claims task #1
  2. Queries facts ledger → sees existing endpoints in src/api/
  3. Proposes changeset: add src/api/users.py
  4. Governor verifies: file doesn't conflict, tests pass
  5. Commits fact: "src/api/users.py exists" with receipt
  6. Releases task #1

Codex Worker 2 (or same worker):
  1. Claims task #2
  2. Queries facts ledger → sees "src/api/users.py exists"
  3. Proposes changeset: add tests/test_users.py
  4. Governor verifies: tests pass
  5. Commits fact: "tests/test_users.py exists"
  6. Done
```

At no point did the agents "talk." They read the ledger, proposed changes, got verified.

### What This Prevents

| Failure Mode | How Governor Stops It |
|--------------|----------------------|
| Two agents implement same feature | Work reservation / lease prevents overlap |
| Agent contradicts architecture decision | Decision conflict detection, hard reject |
| Agent modifies files outside its scope | Permission check on allowed_paths |
| Agent's changeset based on stale state | Base tree hash mismatch, must rebase |
| Race condition on ledger write | SQLite transaction + lease |
| Agent dies mid-work, blocks others | Lease TTL expires, resource unlocks |

---

## Summary

**Multi-agent = shared ledger + transactional commits + deterministic conflict rules.**

- Agents are stateless workers
- Ledger is the only shared state  
- SQLite WAL for concurrency
- Leases prevent collision during verification
- Epochs enable optimistic concurrency
- Permissions scope blast radius
- Orchestration is external (your dispatcher, your rules)

Not Gas Town. Not Race Condition Village. Just a database with receipts.
