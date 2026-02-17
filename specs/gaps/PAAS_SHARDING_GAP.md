# Gap: PaaS Sharding — Partitioning, Replay, and Schema Versioning for Distributed Deployment

**Branch:** v3.x
**Status:** gap (architectural, long-horizon)
**Depends on:** CROSS_DOMAIN_SCHEMA_GAP (hard), REPLAY_HARNESS_GAP (epoch roots — hard), receipt_kernel, daemon.py
**Build phase:** v3.0 (platform — build after cross-domain schema)

## The Problem

The governor currently runs as a single-process daemon with local SQLite storage. This is correct for single-user and small-team deployments. But if governance-as-a-service is ever a deployment model — multiple projects, multiple teams, shared infrastructure — several assumptions break:

1. **SQLite per-project**: Each project has its own `.governor/` directory with its own SQLite DB. No cross-project queries.
2. **No schema versioning**: Receipt kernel uses hardcoded schema. Upgrading a running deployment requires migration.
3. **No deterministic replay**: Replay harness (v2) works per-project. Cross-project replay needs deterministic environment control.
4. **No partitioning**: All receipts for a project are in one JSONL file. At scale, this doesn't shard.

## What Already Exists

| Component | Location | Covers |
|-----------|----------|--------|
| SQLite with WAL | storage.py | Single-process concurrency |
| Receipt kernel | libs/receipt_kernel/ | Append-only, hash-chained, single-file store |
| Context manager | context_manager.py | Per-context isolation via directory |
| Daemon | daemon.py | JSON-RPC over Unix socket — single daemon per project |
| Schema V6 | epistemic.py | Current schema version, no migration framework |

## What Needs Building (Architectural Sketch)

### 1. Receipt Partitioning

Receipts partitioned by `(project_id, time_bucket)`:
- Within a bucket: append-only, hash-chained (existing semantics)
- Across buckets: chain continues (prev_event_hash links to last event of previous bucket)
- Enables: time-range queries without scanning full history, bucket-level archival

### 2. Schema Versioning Framework

Receipt kernel and epistemic store need forward-compatible schema evolution:
- Envelope includes `schema_version` (already exists in gate receipts, not in kernel events)
- Migration: old events readable with new code (add fields with defaults)
- Immutability: old events never rewritten — new fields only appear on new events
- Schema registry (from CROSS_DOMAIN_SCHEMA_GAP.md) tracks active versions

### 3. Multi-Daemon Coordination

If multiple daemons serve different projects on shared infrastructure:
- Shared receipt store (PostgreSQL or similar) replaces per-project SQLite
- Daemon discovery: registry or DNS-based
- Cross-project queries: "show all FAIL receipts across my projects"
- Isolation: project A cannot read project B's receipts without explicit grant

### 4. Deterministic Replay for Compliance

Regulatory or audit scenarios may require bit-exact replay:
- Receipt kernel events + sealed evidence blobs = complete input
- Replay runner (from REPLAY_HARNESS_GAP.md Tier B/C) re-executes with pinned random seeds
- Output hash compared against stored hash
- Failure = evidence of tampering or non-determinism

## Why v3 (and Possibly Later)

This is infrastructure for a deployment model that doesn't exist yet. The single-daemon, per-project model works for all current users. This spec exists to:
1. Document the known scaling limitations
2. Ensure v2 decisions don't preclude distributed deployment
3. Provide a target architecture if PaaS becomes a real requirement

## PaaS-Specific Landmines

### Partitioning Contract

**`run_id` is the total-order key.** This is non-negotiable.

- Within a run: events are totally ordered by step clock (seq field).
- Across runs: ordering is eventually consistent by wall clock.
- Capture detection must accept eventual consistency for cross-run signals. If it needs total order, it must operate within a single run.

Everything that needs cross-run aggregation (dashboard summaries, σ-rate trends, κ cost curves) operates on eventually-consistent views. Design them to tolerate stale data.

### Dual-Write / Promotion Plan

When `TemplateInst` / `RunSummary` becomes the v3 wire format, transition via dual-write:

1. **Phase 1**: Emit both legacy receipts AND v3 envelopes. Consumers read legacy.
2. **Phase 2**: Consumers migrate to v3 envelopes. Legacy still emitted.
3. **Phase 3**: Legacy emission removed. v3 is sole format.

No flag day. No "temporary adapters." If replay breaks during transition, the dual-write period extends until it doesn't.

### κ as Quota Surface

In PaaS, κ is not an abstract aggressiveness dial — it's resource policy:

| κ action | Resource cost |
|----------|--------------|
| Sampling frequency | Compute (more checks = more CPU) |
| Retention depth | Storage (longer history = more disk) |
| Replay depth | Compute + I/O (deeper sweeps = more $) |
| Multi-model quorum | API cost (more validators = more tokens) |

κ must map to budgeted actions per tenant. Per-tenant caps prevent "infinite cost dial." This means KAPPA_DIAL_GAP must define its cost model in resource units, not just abstract "block rate vs false positive rate."

### Authn/Authz

v2 relies on filesystem permissions (Unix socket, `.governor/` directory ownership). v3 needs:
- Cryptographic signing on receipts (content-addressed IDs survive, but need origin attestation)
- Tenant isolation at the store level (not just directory separation)
- API tokens for daemon access (GOVERNOR_AUTH_TOKEN exists but isn't enforced in RPC)

Design receipt format now so signatures can be added later without schema breaks. The current gate_receipt.py pattern (hash over immutable content, timestamp is metadata) is correct — don't change it.

## Design Constraints (From Current Architecture)

These constraints should be preserved in any distributed design:
- **Hash chains are immutable**: Receipts are append-only. No rewriting history.
- **Content addressing is global**: Receipt IDs are content hashes, so they're naturally dedup-safe across projects.
- **Verdicts are local**: A receipt's verdict is computed from local evidence. Cross-project queries aggregate but don't re-evaluate.
- **The daemon is the authority**: Even in multi-daemon setups, each project has exactly one authoritative daemon. No consensus protocol for governance decisions.

## Build Estimate

This is a multi-quarter effort if actually built. The spec is ~200 lines of architecture. Implementation depends on whether PaaS becomes a real deployment target.

## Acceptance Criteria (For the Spec, Not Implementation)

1. Receipt partitioning scheme defined with cross-bucket chain continuity
2. Schema versioning rules documented (forward-compat, no rewrites)
3. Multi-daemon isolation model defined (per-project authority, explicit grants)
4. Deterministic replay requirements specified (Tier C from REPLAY_HARNESS_GAP.md)
5. No v2 decisions that preclude this architecture
