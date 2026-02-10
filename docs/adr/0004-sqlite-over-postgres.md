# 0004 — SQLite over Postgres

## Status

Accepted

## Context

The multi-agent governor needs a database for shared state: claims, receipts, leases, epochs, task reservations. The choice is between an embedded database (SQLite) and a server-side database (Postgres, MySQL, etc.).

Requirements:
- ACID transactions for atomic proposal verification
- Concurrent read access for multiple agents
- Serialized writes (only one proposal applies at a time)
- No external dependencies for single-developer use
- Portable across environments (local, Docker, CI)

## Decision

SQLite with WAL (Write-Ahead Logging) mode.

```
Multi-agent = shared ledger + transactional commits + deterministic conflict rules.

- Agents are stateless workers
- Ledger is the only shared state
- SQLite WAL for concurrency
- Leases prevent collision during verification
- Epochs enable optimistic concurrency
- Permissions scope blast radius
- Orchestration is external (your dispatcher, your rules)

Not Gas Town. Not Race Condition Village. Just a database with receipts.
```

WAL mode provides:
- **Multiple concurrent readers** without blocking writers
- **Single writer serialization** preventing write conflicts
- **ACID transactions** out of the box

Application-level constructs compensate for the single-writer limitation:
- **Leases** (TTL-scoped locks) prevent collision during verification
- **Epochs** enable optimistic concurrency (`UPDATE ... WHERE epoch = N`)
- **Transactions** ensure atomic-or-nothing proposal application

## Consequences

- **Zero deployment dependencies.** No database server to install, configure, or maintain. The governor runs anywhere Python runs.
- **File-based = git-trackable schema.** The database is a file. Schema migrations are versioned. The database can be inspected with standard SQLite tools.
- **Single writer is sufficient.** The governor's concurrency model is intentionally serialized at the write boundary. Multiple agents can read concurrently, but proposals apply one at a time. This is a feature, not a limitation — it prevents partial commits.
- **No clustering or sharding.** The governor is per-project, not per-organization. A single SQLite file handles the expected scale (tens of agents, thousands of claims, not millions).
- **Portable across Docker, CI, local.** No connection strings, no credentials, no database provisioning. `pip install -e .` and you're done.

## Source

- `MULTI_AGENT.md` ("Why SQLite: ACID transactions out of the box, multiple readers/single writer (WAL mode), no external dependencies, file-based = git-trackable schema, portable")
